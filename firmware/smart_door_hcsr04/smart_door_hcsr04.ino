/*
 * Smart Door – HC-SR04 Ultrasonic + Servo Door Controller
 * Target: Arduino Uno / Nano / ESP32 (PlatformIO-friendly)
 *
 * Core principle: work at any cost. No ISR portability issues.
 * Uses micros()-based polling with aggressive timeouts so the sketch
 * never hangs, never relies on pin-change interrupts, and never
 * depends on ESP32-specific APIs.
 *
 * Behavior:
 *   1. Measure distance every cycle using pure polling.
 *   2. If distance <= DETECTION_THRESHOLD_CM for OPEN_CONSECUTIVE readings,
 *      mark as DETECTED and open the door.
 *   3. While still detected, keep resetting the "last seen" timer.
 *   4. Once no detection for CLOSE_CONSECUTIVE readings, start a 10 s timer.
 *   5. If the timer expires with no new detection, close the door.
 *   6. A 30 s hard timeout (MAX_OPEN_TIME_MS) forces closure regardless
 *      of the sensor state as a safety fallback.
 */

// ────────────────────────────────────────────────────────────────────────
// CONFIGURATION – adjust these constants to match your hardware
// ────────────────────────────────────────────────────────────────────────

// HC-SR04 pins
const uint8_t  TRIG_PIN = 9;          // Output: 10 µs trigger pulse
const uint8_t  ECHO_PIN = 10;         // Input:  pulse width → distance

// Door actuator
const uint8_t  SERVO_PIN = 11;        // PWM pin for servo signal wire
const uint16_t OPEN_ANGLE  = 90;      // Degrees  – door open position
const uint16_t CLOSE_ANGLE = 0;       // Degrees  – door closed (locked) position

// Detection thresholds
const float     DETECTION_THRESHOLD_CM = 5.0f;   // Object considered "at door" if <= this
const uint8_t   OPEN_CONSECUTIVE   = 2;          // Readings needed to open (lowered for faster response)
const uint8_t   CLOSE_CONSECUTIVE  = 4;          // Readings needed to start close timer

// Timing
const unsigned long HOLD_OPEN_MS    = 10UL * 1000UL;   // 10 s after last detection
const unsigned long MAX_OPEN_MS     = 30UL * 1000UL;   // 30 s hard safety limit
const unsigned long DEBUG_INTERVAL  = 500UL;           // Serial output rate
const unsigned long MEASURE_INTERVAL = 80UL;           // Min ms between triggers

// Polling timeouts (microseconds) – these keep loop() non-blocking
const unsigned long ECHO_TIMEOUT_HIGH_US = 40000UL;      // 40 ms max wait for echo HIGH
const unsigned long ECHO_TIMEOUT_LOW_US  = 40000UL;      // 40 ms max wait for echo LOW

// ────────────────────────────────────────────────────────────────────────
// INCLUDES
// ────────────────────────────────────────────────────────────────────────
#include <Arduino.h>
#include <Servo.h>

// ────────────────────────────────────────────────────────────────────────
// STATE MACHINE
// ────────────────────────────────────────────────────────────────────────
enum DoorState : uint8_t {
  STATE_CLOSED,
  STATE_OPEN,
  STATE_CLOSING_PENDING   // detected nothing, counting down to close
};

DoorState  door_state     = STATE_CLOSED;
Servo      door_servo;

// Timing
unsigned long state_enter_ms    = 0;   // when we entered current STATE_OPEN
unsigned long last_detected_ms  = 0;   // most recent time an object was seen

// Detection debounce counters
uint8_t  detected_count      = 0;
uint8_t  not_detected_count  = 0;
bool     object_detected     = false;

// ────────────────────────────────────────────────────────────────────────
// NON-BLOCKING POLLING ECHO MEASUREMENT
// Pure digital polling with micros()-based timeouts.
// No ISRs, no pin-change hacks, no attachInterrupt portability issues.
// Works identically on AVR, ARM, ESP32, RP2040, etc.
// ────────────────────────────────────────────────────────────────────────

// Step 1: fire the 10 µs TRIG pulse
void trigger_measurement() {
  digitalWrite(TRIG_PIN, LOW);
  delayMicroseconds(2);
  digitalWrite(TRIG_PIN, HIGH);
  delayMicroseconds(10);
  digitalWrite(TRIG_PIN, LOW);
}

// Step 2: wait for ECHO HIGH with timeout, return start micros or 0 on fail
unsigned long wait_echo_high() {
  unsigned long deadline = micros() + ECHO_TIMEOUT_HIGH_US;
  while (digitalRead(ECHO_PIN) == LOW) {
    if (micros() > deadline) return 0;
  }
  return micros();
}

// Step 3: wait for ECHO LOW with timeout, return end micros or 0 on fail
unsigned long wait_echo_low(unsigned long start_us) {
  unsigned long deadline = micros() + ECHO_TIMEOUT_LOW_US;
  while (digitalRead(ECHO_PIN) == HIGH) {
    if (micros() > deadline) return 0;
  }
  return micros();
}

// Full distance read – returns cm, or -1.0 on any failure
float read_distance_cm() {
  trigger_measurement();

  unsigned long t_start = wait_echo_high();
  if (t_start == 0) return -1.0f;

  unsigned long t_end = wait_echo_low(t_start);
  if (t_end == 0) return -1.0f;

  unsigned long duration_us = t_end - t_start;

  // Sanity: reject pulses shorter than ~58 µs (≈1 cm) or longer than ~29 ms (≈500 cm)
  if (duration_us < 58UL || duration_us > 30000UL) return -1.0f;

  return (float)duration_us / 58.0f;
}

// ────────────────────────────────────────────────────────────────────────
// SERVO / DOOR ACTUATORS
// Swap these two helpers if you use a relay / motor driver instead.
// ────────────────────────────────────────────────────────────────────────
void open_door() {
  Serial.println(F("[ACTUATOR] Opening door"));
  door_servo.write(OPEN_ANGLE);
}

void close_door() {
  Serial.println(F("[ACTUATOR] Closing door"));
  door_servo.write(CLOSE_ANGLE);
}

// ────────────────────────────────────────────────────────────────────────
// SERIAL DEBUG HELPER
// ────────────────────────────────────────────────────────────────────────
void print_debug(float dist_cm, DoorState st, unsigned long timer_left_ms) {
  const char *state_str =
    (st == STATE_CLOSED)          ? "CLOSED" :
    (st == STATE_OPEN)            ? "OPEN"   :
                                   "CLOSING…";

  Serial.print(F("dist="));
  if (dist_cm < 0.0f) {
    Serial.print(F("ERR"));
  } else {
    Serial.print(dist_cm, 1);
    Serial.print(F(" cm"));
  }

  Serial.print(F("  state="));
  Serial.print(state_str);

  Serial.print(F("  timer_left="));
  Serial.print(timer_left_ms / 1000UL);
  Serial.println(F(" s"));
}

// ────────────────────────────────────────────────────────────────────────
// INITIALISATION
// ────────────────────────────────────────────────────────────────────────
void setup() {
  Serial.begin(115200);
  while (!Serial && millis() < 2000) { /* wait for USB-Serial */ }

  pinMode(TRIG_PIN, OUTPUT);
  digitalWrite(TRIG_PIN, LOW);

  pinMode(ECHO_PIN, INPUT);

  door_servo.attach(SERVO_PIN);
  door_servo.write(CLOSE_ANGLE);

  Serial.println(F("Smart Door Controller – initialised"));
  Serial.println(F("Ultrasonic polling mode – no ISR dependencies"));
}

// ────────────────────────────────────────────────────────────────────────
// MAIN LOOP
// ────────────────────────────────────────────────────────────────────────
void loop() {
  static unsigned long last_measure_ms = 0;
  static unsigned long last_debug_ms   = 0;

  unsigned long now = millis();

  // 0. Handle incoming commands from Python (e.g. Face Recognition)
  if (Serial.available() > 0) {
    String cmd = Serial.readStringUntil('\n');
    cmd.trim();
    if (cmd == "UNLOCK") {
      Serial.println(F("[CMD] Received UNLOCK command from Host"));
      open_door();
      door_state = STATE_OPEN;
      state_enter_ms = now;
      last_detected_ms = now;
      object_detected = true;
      detected_count = 0;
      not_detected_count = 0;
    }
  }

  // 1. Non-blocking measurement cadence
  if (now - last_measure_ms >= MEASURE_INTERVAL) {
    last_measure_ms = now;

    // Read distance (returns -1.0 on timeout / error)
    float dist = read_distance_cm();
    bool  detected_now = (dist >= 0.0f && dist <= DETECTION_THRESHOLD_CM);

    // 2. Debounce / hysteresis counters
    if (detected_now) {
      detected_count++;
      not_detected_count = 0;
    } else {
      not_detected_count++;
      detected_count = 0;
    }

    bool debounced_detection = (detected_count >= OPEN_CONSECUTIVE);
    bool debounced_clear      = (not_detected_count >= CLOSE_CONSECUTIVE);

    // 3. State machine
    switch (door_state) {

      case STATE_CLOSED:
        object_detected = false;
        if (debounced_detection) {
          open_door();
          door_state     = STATE_OPEN;
          state_enter_ms = now;
          object_detected = true;
          last_detected_ms = now;
          detected_count = 0;
          not_detected_count = 0;
        }
        break;

      case STATE_OPEN:
        object_detected = true;
        if (debounced_detection) {
          // Object still there – reset "keep-open" timer
          last_detected_ms = now;
          not_detected_count = 0;
        }

        // Safety watchdog: force close after MAX_OPEN_MS regardless of sensor
        if (now - state_enter_ms > MAX_OPEN_MS) {
          Serial.println(F("[SAFETY] Max open time reached – forcing close"));
          close_door();
          door_state = STATE_CLOSED;
          object_detected = false;
          detected_count = 0;
          not_detected_count = 0;
          break;
        }

        // Has the object been absent long enough to arm the close timer?
        if (debounced_clear) {
          door_state     = STATE_CLOSING_PENDING;
          state_enter_ms = now;
          not_detected_count = 0;
        }
        break;

      case STATE_CLOSING_PENDING:
        object_detected = false;
        if (debounced_detection) {
          // Object returned during countdown – reopen immediately
          open_door();
          door_state     = STATE_OPEN;
          state_enter_ms = now;
          last_detected_ms = now;
          object_detected = true;
          not_detected_count = 0;
          break;
        }

        // Safety watchdog still applies during countdown
        if (now - state_enter_ms > MAX_OPEN_MS) {
          Serial.println(F("[SAFETY] Max open time reached – forcing close from pending"));
          close_door();
          door_state = STATE_CLOSED;
          detected_count = 0;
          not_detected_count = 0;
          break;
        }

        // Check if 10 s have passed since the last confirmed detection
        if (now - last_detected_ms >= HOLD_OPEN_MS) {
          close_door();
          door_state = STATE_CLOSED;
          // Reset debounce counters so a fresh detection needs OPEN_CONSECUTIVE hits again
          detected_count = 0;
          not_detected_count = 0;
        }
        break;
    }
  }

  // 4. Debug output at DEBUG_INTERVAL
  if (now - last_debug_ms >= DEBUG_INTERVAL) {
    last_debug_ms = now;

    unsigned long timer_left_ms = 0;
    if (door_state == STATE_CLOSING_PENDING) {
      unsigned long elapsed = now - last_detected_ms;
      timer_left_ms = (elapsed < HOLD_OPEN_MS) ? (HOLD_OPEN_MS - elapsed) : 0;
    }

    // Use the most recent distance for debug (re-read if needed for status)
    float dist = read_distance_cm();
    print_debug(dist, door_state, timer_left_ms);
  }
}
