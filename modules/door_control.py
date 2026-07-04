"""
Smart Door Security System - Door Control Module
Controls door lock/unlock via positional servo and HC-SR04 proximity sensor.

Servo positions:
    0°   → SERVO_DUTY_MIN  (closed / locked stop)
    90°  → SERVO_DUTY_OPEN  (open stop, 90° clockwise from closed)
    180° → SERVO_DUTY_MAX  (unused reference / full sweep)
"""

import threading
import time
import logging
from typing import Optional, Callable
from dataclasses import dataclass
from enum import Enum
import sys
import random

import serial
import serial.tools.list_ports

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

try:
    from config.settings import (
        SERVO_PWM_PIN, SERVO_PWM_FREQUENCY,
        SERVO_DUTY_MIN, SERVO_DUTY_MAX,
        SERVO_DUTY_CLOSED, SERVO_TRANSITION_DELAY,
        SERVO_ANGLE_OPEN, SERVO_ANGLE_CLOSE,
        ULTRASONIC_TRIG_PIN, ULTRASONIC_ECHO_PIN,
        ULTRASONIC_ONE_WAY_FACTOR, ULTRASONIC_TIMEOUT,
        ULTRASONIC_RETRIES, ULTRASONIC_RETRY_DELAY,
        ULTRASONIC_POLL_US, ULTRASONIC_THRESHOLD,
        ULTRASONIC_REARM_DELAY,
        AUTO_LOCK_DELAY,
    )
    from database.db_manager import SystemLogRepository
except ImportError:
    sys.path.insert(0, str(PROJECT_ROOT))
    from config.settings import (  # type: ignore
        SERVO_PWM_PIN, SERVO_PWM_FREQUENCY,
        SERVO_DUTY_MIN, SERVO_DUTY_MAX,
        SERVO_DUTY_CLOSED, SERVO_TRANSITION_DELAY,
        SERVO_ANGLE_OPEN, SERVO_ANGLE_CLOSE,
        ULTRASONIC_TRIG_PIN, ULTRASONIC_ECHO_PIN,
        ULTRASONIC_ONE_WAY_FACTOR, ULTRASONIC_TIMEOUT,
        ULTRASONIC_RETRIES, ULTRASONIC_RETRY_DELAY,
        ULTRASONIC_POLL_US, ULTRASONIC_THRESHOLD,
        ULTRASONIC_REARM_DELAY,
        AUTO_LOCK_DELAY,
    )
    from database.db_manager import SystemLogRepository  # type: ignore

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

try:
    import RPi.GPIO as GPIO
    GPIO_AVAILABLE = True
except ImportError:
    GPIO_AVAILABLE = False
    logger.info("RPi.GPIO not available — running in simulation mode.")

# ────────────────────────────────────────────────────────────────────────
# DOOR STATE ENUMS
# ────────────────────────────────────────────────────────────────────────

class DoorState(Enum):
    LOCKED    = "Door Locked"
    UNLOCKED  = "Door Unlocked"
    UNLOCKING = "Unlocking…"
    LOCKING   = "Locking…"
    ERROR     = "Door Error"

class SensorEvent(Enum):
    NONE      = "No event"
    PROXIMITY = "Proximity detected"
    OBSTACLE  = "Obstacle detected"

@dataclass
class DoorStatus:
    state: DoorState
    time_until_lock: float = 0.0
    last_unlock_time: Optional[float] = None
    message: str = ""

# ────────────────────────────────────────────────────────────────────────
# HC-SR04 ULTRASONIC SENSOR MONITOR
# ────────────────────────────────────────────────────────────────────────

class UltrasonicSensorMonitor:
    """
    Background thread that polls an HC-SR04 sensor.

    Wiring (BCM):
        TRIG  → GPIO23  (OUTPUT, 10 us pulse)
        ECHO  → GPIO24  (INPUT; add 1 kΩ / 2 kΩ voltage divider from 5 V)

    Callbacks receive (event: SensorEvent, distance_cm: float).
    Only SensorEvent.PROXIMITY triggers the silent-unlock door sequence.
    """

    def __init__(
        self,
        trig_pin    = ULTRASONIC_TRIG_PIN,
        echo_pin    = ULTRASONIC_ECHO_PIN,
        threshold   = ULTRASONIC_THRESHOLD,
        poll_us     = ULTRASONIC_POLL_US,
        retries     = ULTRASONIC_RETRIES,
        retry_delay = ULTRASONIC_RETRY_DELAY,
        rearm_delay = ULTRASONIC_REARM_DELAY,
    ):
        self.trig_pin    = trig_pin
        self.echo_pin    = echo_pin
        self.threshold   = threshold
        self.poll_interval = poll_us / 1_000_000.0
        self.retries     = retries
        self.retry_delay = retry_delay
        self.rearm_delay = rearm_delay

        self._running  = False
        self._thread   = None
        self._callbacks = []

        self._last_trigger_time = 0.0
        self._armed   = True
        self._paused  = False

    def add_callback(self, cb: Callable):
        if cb not in self._callbacks:
            self._callbacks.append(cb)

    def remove_callback(self, cb: Callable):
        self._callbacks = [c for c in self._callbacks if c is not cb]

    def start(self) -> bool:
        if self._running:
            return True
        self._running = True
        if GPIO_AVAILABLE:
            self._init_gpio()
        self._thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._thread.start()
        logger.info(
            "UltrasonicSensorMonitor: trig=GPIO%d echo=GPIO%d threshold=%.1f cm",
            self.trig_pin, self.echo_pin, self.threshold)
        return True

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=2.0)
        if GPIO_AVAILABLE:
            try:
                GPIO.cleanup((self.trig_pin, self.echo_pin))
            except Exception:
                pass
        logger.info("UltrasonicSensorMonitor stopped.")

    def _init_gpio(self):
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(self.trig_pin, GPIO.OUT)
        GPIO.setup(self.echo_pin,  GPIO.IN)
        GPIO.output(self.trig_pin, GPIO.LOW)
        time.sleep(0.5)

    def pause(self):
        self._paused = True

    def resume(self):
        self._paused = False

    # ── Measurement ─────────────────────────────────────────────────────

    def _read_distance_cm(self) -> float:
        """
        Fire one HC-SR04 measurement cycle.

        Returns the one-way distance in cm on success, or -1.0 on failure.
        In simulation mode a random 5–40 cm value is returned on every call.
        """
        # ── Simulation fast-path ──────────────────────────────────────────
        if not GPIO_AVAILABLE:
            return random.uniform(3.0, 40.0)

        backoff = ULTRASONIC_RETRY_DELAY
        for attempt in range(ULTRASONIC_RETRIES):
            try:
                # 1. Pulse TRIG high for exactly 10 microseconds
                GPIO.output(self.trig_pin, GPIO.LOW)
                if backoff > 0:
                    time.sleep(backoff)
                GPIO.output(self.trig_pin, GPIO.HIGH)
                time.sleep(1e-5)
                GPIO.output(self.trig_pin, GPIO.LOW)

                # 2. Wait for ECHO to go HIGH
                t0 = time.monotonic()
                timeout = ULTRASONIC_TIMEOUT
                while GPIO.input(self.echo_pin) == GPIO.LOW:
                    if time.monotonic() - t0 > timeout:
                        raise TimeoutError("echo-sync timeout")
                    t0 = time.monotonic()

                # 3. Wait for ECHO to go LOW
                t1 = time.monotonic()
                while GPIO.input(self.echo_pin) == GPIO.HIGH:
                    if time.monotonic() - t1 > timeout:
                        raise TimeoutError("echo-pulse timeout")
                    t1 = time.monotonic()

                echo_us = (t1 - t0) * 1_000_000.0
                return echo_us * ULTRASONIC_ONE_WAY_FACTOR

            except Exception:
                if attempt < ULTRASONIC_RETRIES - 1:
                    time.sleep(backoff)
                    backoff *= 2
                else:
                    return -1.0
        return -1.0

    # ── Poll loop ───────────────────────────────────────────────────────

    def _monitor_loop(self):
        while self._running:
            if self._paused:
                time.sleep(0.1)
                continue

            distance = self._read_distance_cm()
            now = time.time()

            if not self._armed and (now - self._last_trigger_time) < self.rearm_delay:
                time.sleep(self.poll_interval)
                continue
            self._armed = True

            if 0.0 < distance <= self.threshold:
                self._armed = False
                self._last_trigger_time = now
                self._notify(SensorEvent.PROXIMITY, distance)
                logger.info(
                    "PROXIMITY: %.2f cm <= %.1f cm  (re-arm in %.0f s)",
                    distance, self.threshold, self.rearm_delay)
            else:
                self._notify(SensorEvent.NONE, distance)

            time.sleep(self.poll_interval)

    def _notify(self, event: SensorEvent, distance_cm: float):
        for cb in list(self._callbacks):
            try:
                cb(event, distance_cm)
            except Exception:
                logger.exception("UltrasonicSensorMonitor: callback error.")

# ────────────────────────────────────────────────────────────────────────
# DOOR CONTROLLER
# ────────────────────────────────────────────────────────────────────────

class DoorController:
    _instance = None
    _lock     = threading.Lock()

    def __new__(cls, servo_pin=None, simulation=False):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance     = super().__new__(cls)
                    cls._instance._initialized = False
                    cls._init_servo_pin = servo_pin
                    cls._init_simulation = simulation
        return cls._instance

    def __init__(self, servo_pin=None, simulation=False):
        if self._initialized:
            return

        self.servo_pin    = self._init_servo_pin or servo_pin or SERVO_PWM_PIN
        self.simulation   = (self._init_simulation or simulation or not GPIO_AVAILABLE)

        self._state      = DoorState.LOCKED
        self._state_lock = threading.RLock()

        self._auto_lock_timer    : Optional[threading.Timer] = None
        self._last_unlock_time   : Optional[float]           = None
        self._callbacks          : list                      = []

        self._pwm = None
        self._serial_conn = None
        self._serial_thread = None
        self._serial_running = False

        self._ultrasonic = UltrasonicSensorMonitor()
        self._ultrasonic.add_callback(self._on_ultrasonic_event)

        self.system_log = SystemLogRepository()
        self._initialized = True

        if not self.simulation:
            self._init_gpio()
        else:
            self._init_serial_fallback()

    def _init_serial_fallback(self):
        # Attempt to auto-detect Arduino COM port
        target_port = None
        for port in serial.tools.list_ports.comports():
            desc = port.description.lower()
            if "arduino" in desc or "ch340" in desc or "usb serial" in desc or "serial device" in desc:
                target_port = port.device
                break
        
        if target_port:
            try:
                self._serial_conn = serial.Serial(target_port, 115200, timeout=1)
                self.simulation = False
                logger.info(f"DoorController: Arduino detected on {target_port}. hardware mode active.")
                self.system_log.info("DoorController", f"Hardware mode active via Arduino on {target_port}")
                
                self._serial_running = True
                self._serial_thread = threading.Thread(target=self._serial_read_loop, daemon=True)
                self._serial_thread.start()
            except Exception as e:
                logger.error(f"DoorController: Failed to connect to Arduino on {target_port}: {e}")
                self.simulation = True
        else:
            logger.info("DoorController: No Arduino found. Running in pure simulation mode.")
            self.simulation = True
            # Start the dummy ultrasonic sensor anyway
            self._ultrasonic.start()

    def _serial_read_loop(self):
        while self._serial_running and self._serial_conn:
            try:
                if self._serial_conn.in_waiting:
                    line = self._serial_conn.readline().decode('utf-8', errors='ignore').strip()
                    if not line: continue
                    
                    if "Opening door" in line:
                        with self._state_lock:
                            self._state = DoorState.UNLOCKED
                            self._last_unlock_time = time.time()
                        self._notify()
                    elif "Closing door" in line:
                        with self._state_lock:
                            self._state = DoorState.LOCKED
                            self._last_unlock_time = None
                        self._notify()
                    elif line.startswith("dist="):
                        # Example: dist=12.3 cm  state=CLOSED  timer_left=0 s
                        parts = line.split()
                        if len(parts) >= 2 and parts[1] != "ERR":
                            try:
                                distance = float(parts[1])
                                if distance <= ULTRASONIC_THRESHOLD:
                                    # Forward proxy to callbacks
                                    self._ultrasonic._notify(SensorEvent.PROXIMITY, distance)
                            except ValueError:
                                pass
            except Exception as e:
                logger.error(f"DoorController serial read error: {e}")
                time.sleep(1)
                
    def _init_gpio(self):
        try:
            GPIO.setmode(GPIO.BCM)
            GPIO.setup(self.servo_pin, GPIO.OUT)
            self._pwm = GPIO.PWM(self.servo_pin, SERVO_PWM_FREQUENCY)
            self._pwm.start(0)
            GPIO.output(self.servo_pin, GPIO.LOW)

            self._servo_to_angle(SERVO_ANGLE_CLOSE)
            logger.info("DoorController: servo on GPIO%d  freq=%d Hz", self.servo_pin, SERVO_PWM_FREQUENCY)
            self.system_log.info("DoorController", f"GPIO ready: servo=GPIO{self.servo_pin} freq={SERVO_PWM_FREQUENCY} Hz")

            self._ultrasonic.start()
            logger.info("DoorController: HC-SR04 trig=GPIO%d echo=GPIO%d  threshold=%.1f cm", ULTRASONIC_TRIG_PIN, ULTRASONIC_ECHO_PIN, ULTRASONIC_THRESHOLD)

        except Exception as exc:
            logger.error("GPIO init failed: %s — simulation mode.", exc)
            self.simulation = True
            self._init_serial_fallback()

    def _angle_to_duty(self, angle: float) -> float:
        return SERVO_DUTY_MIN + (angle / 180.0) * (SERVO_DUTY_MAX - SERVO_DUTY_MIN)

    def _servo_to_angle(self, angle: float) -> None:
        duty = self._angle_to_duty(angle)
        if self._pwm:
            self._pwm.ChangeDutyCycle(duty)
        logger.debug("Servo → %.0f°  (duty=%.2f%%)", angle, duty)
        time.sleep(SERVO_TRANSITION_DELAY)
        if self._pwm:
            self._pwm.ChangeDutyCycle(0.0)

    def add_state_callback(self, cb: Callable):
        if cb not in self._callbacks:
            self._callbacks.append(cb)

    def remove_state_callback(self, cb: Callable):
        self._callbacks = [c for c in self._callbacks if c is not cb]

    def _notify(self):
        status = self.get_status()
        for cb in list(self._callbacks):
            try:
                cb(status)
            except Exception:
                logger.exception("DoorController: callback error.")

    def _on_ultrasonic_event(self, event: SensorEvent, distance_cm: float):
        if event is SensorEvent.PROXIMITY:
            self.door_open_proximity()
            logger.info("Ultrasonic proximity unlock: %.2f cm <= %.1f cm threshold", distance_cm, ULTRASONIC_THRESHOLD)

    @property
    def state(self) -> DoorState:
        with self._state_lock:
            return self._state

    @property
    def last_unlock_time(self) -> Optional[float]:
        with self._state_lock:
            return self._last_unlock_time

    def get_status(self) -> DoorStatus:
        with self._state_lock:
            remaining = 0.0
            if self._state is DoorState.UNLOCKED and self._last_unlock_time is not None:
                remaining = max(0.0, AUTO_LOCK_DELAY - (time.time() - self._last_unlock_time))
            return DoorStatus(
                state           = self._state,
                time_until_lock = remaining,
                last_unlock_time = self._last_unlock_time,
                message          = self._state.value,
            )

    def is_locked(self)  -> bool: return self.state is DoorState.LOCKED
    def is_unlocked(self)-> bool: return self.state is DoorState.UNLOCKED

    def _rotate_servo_open(self) -> None:
        logger.info("Servo → %d° (door open)", SERVO_ANGLE_OPEN)
        self._servo_to_angle(SERVO_ANGLE_OPEN)

    def _rotate_servo_close(self) -> None:
        logger.info("Servo → %d° (door closed/hold)", SERVO_ANGLE_CLOSE)
        self._servo_to_angle(SERVO_ANGLE_CLOSE)

    def _do_open_and_lock_sequence(self) -> None:
        def _seq():
            with self._state_lock:
                self._state = DoorState.UNLOCKING
            self._notify()

            self._rotate_servo_open()

            with self._state_lock:
                self._state           = DoorState.UNLOCKED
                self._last_unlock_time = time.time()
            self._notify()

            hold_end = time.time() + AUTO_LOCK_DELAY
            while time.time() < hold_end:
                slot = max(0.0, hold_end - time.time())
                if int(slot) % 5 == 0 and int(slot) != int(hold_end - time.time() + 1.0):
                    logger.info("[SEQUENCE] %.0f s remaining until auto-lock…", slot)
                time.sleep(0.5)

            with self._state_lock:
                self._state = DoorState.LOCKING
            self._notify()
            self._rotate_servo_close()

            with self._state_lock:
                self._state           = DoorState.LOCKED
                self._last_unlock_time = None
            self._notify()
            logger.info("[SEQUENCE] State=LOCKED — sequence complete.")

        threading.Thread(target=_seq, daemon=True).start()

    def door_open_proximity(self) -> None:
        with self._state_lock:
            if self._state is DoorState.UNLOCKED:
                logger.info("Proximity unlock skipped — door already unlocked.")
                return
        logger.info("PROXIMITY UNLOCK: silent open — %d° sweep. Relock in %.0f s.", SERVO_ANGLE_OPEN, AUTO_LOCK_DELAY)
        if self._serial_conn:
            self._serial_conn.write(b"UNLOCK\n")
        else:
            self._do_open_and_lock_sequence()

    def unlock(self, duration=None, reason="Manual") -> bool:
        with self._state_lock:
            if self._auto_lock_timer:
                self._auto_lock_timer.cancel()
                self._auto_lock_timer = None
        logger.info("DoorController.unlock() — reason: %s", reason)
        if self._serial_conn:
            self._serial_conn.write(b"UNLOCK\n")
        else:
            self._do_open_and_lock_sequence()
        return True

    def lock(self, reason="Manual") -> bool:
        with self._state_lock:
            if self._auto_lock_timer:
                self._auto_lock_timer.cancel()
                self._auto_lock_timer = None
            self._state = DoorState.LOCKING
        self._notify()
        
        if self._serial_conn:
            # Arduino firmware handles its own auto-locking, but if we wanted to force close, we could add a CLOSE command.
            # Currently arduino doesn't listen to CLOSE. So just simulate it on UI.
            with self._state_lock:
                self._state = DoorState.LOCKED
                self._last_unlock_time = None
            self._notify()
            return True
            
        try:
            self._rotate_servo_close()
            with self._state_lock:
                self._state         = DoorState.LOCKED
                self._last_unlock_time = None
            self._notify()
            logger.info("DoorController.lock() — reason: %s", reason)
            return True
        except Exception as exc:
            logger.error("DoorController.lock() error: %s", exc)
            with self._state_lock:
                self._state = DoorState.ERROR
            self._notify()
            return False

    def _cancel_timers(self):
        if self._auto_lock_timer:
            self._auto_lock_timer.cancel()
            self._auto_lock_timer = None

    def _auto_lock(self):
        self.lock(reason="Auto-lock timer")

    def set_unlock_duration(self, duration: float):
        pass

    def emergency_lock(self) -> bool:
        with self._state_lock:
            self._cancel_timers()
        if self._serial_conn:
             return True
        try:
            self._rotate_servo_close()
            with self._state_lock:
                self._state         = DoorState.LOCKED
                self._last_unlock_time = None
            logger.warning("Emergency lock — servo → %d° (door closed).", SERVO_ANGLE_CLOSE)
            self._notify()
            return True
        except Exception as exc:
            logger.error("Emergency lock failed: %s", exc)
            return False

    def cleanup(self):
        self._cancel_timers()
        self._serial_running = False
        if self._serial_conn:
            try:
                self._serial_conn.close()
            except: pass
        if self._pwm:
            try:
                self._servo_to_angle(SERVO_ANGLE_CLOSE)
                self._pwm.stop()
            except Exception:
                pass
            self._pwm = None
        self._ultrasonic.stop()
        if not self.simulation and GPIO_AVAILABLE:
            try:
                GPIO.cleanup((self.servo_pin, ULTRASONIC_TRIG_PIN, ULTRASONIC_ECHO_PIN))
            except Exception:
                pass

    def __del__(self):
        try:
            self.cleanup()
        except Exception:
            pass

# ────────────────────────────────────────────────────────────────────────
# DOOR MONITOR
# ────────────────────────────────────────────────────────────────────────

class DoorMonitor:
    """Polls DoorController at a fixed interval and fires callbacks."""

    def __init__(self, controller: DoorController, update_interval=0.5):
        self.controller        = controller
        self.update_interval   = update_interval
        self._running          = False
        self._thread           = None
        self._callbacks        : list = []

    def add_callback(self, cb: Callable):
        if cb not in self._callbacks:
            self._callbacks.append(cb)

    def remove_callback(self, cb: Callable):
        self._callbacks = [c for c in self._callbacks if c is not cb]

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=2.0)

    def _monitor_loop(self):
        while self._running:
            status = self.controller.get_status()
            for cb in list(self._callbacks):
                try:
                    cb(status)
                except Exception:
                    logger.exception("DoorMonitor: callback error.")
            time.sleep(self.update_interval)

def get_door_controller(simulation: bool = False):
    return DoorController(simulation=simulation)
