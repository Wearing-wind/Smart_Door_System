# Smart Door Security System

A comprehensive smart door unlock security system with face recognition authentication, ultrasonic proximity sensing, and real-time monitoring. Built with Python and integrated with web-based controls and firmware support.

## 🎯 Features

- **Face Recognition Authentication**: AI-powered facial identification for secure access control
- **Ultrasonic Proximity Sensing**: HC-SR04 sensor for motion-based silent unlock
- **Real-time GUI Monitoring**: Live camera preview with system status display
- **Access Logging**: Comprehensive audit trail of all door events
- **Multi-Platform Support**: Runs on Raspberry Pi and desktop systems
- **Simulation Mode**: Full simulation for development and testing without hardware
- **Web Interface**: Remote monitoring and control capabilities
- **Database Integration**: SQLite backend for user management and access logs
- **Auto-lock Timer**: Configurable automatic re-locking after access

## 📋 System Requirements

- **Python**: 3.7+
- **Hardware** (optional):
  - Raspberry Pi 3B+ or newer
  - HC-SR04 Ultrasonic Sensor
  - Servo Motor for door lock
  - Webcam or Pi Camera

## 🚀 Quick Start

### Installation

1. **Clone the repository**:
   ```bash
   git clone https://github.com/Wearing-wind/Smart_Door_System.git
   cd Smart_Door_System
   ```

2. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

3. **For Raspberry Pi with GPIO support** (optional):
   ```bash
   sudo apt-get install python3-pil python3-pil.imagetk
   sudo pip install RPi.GPIO
   ```

### Running the System

**Development/Simulation mode** (no hardware required):
```bash
python main.py --simulation
```

**Production mode** (with hardware):
```bash
python main.py
```

**With debug logging**:
```bash
python main.py --debug
```

### User Enrollment

Enroll new users with facial recognition:
```bash
python enroll_user.py              # CLI interface
python enroll_user_gui.py          # GUI interface
```

## 📁 Project Structure

```
Smart_Door_System/
├── main.py                        # Main GUI application
├── enroll_user.py                 # User enrollment CLI
├── enroll_user_gui.py             # User enrollment GUI
├── requirements.txt               # Python dependencies
├── config/
│   └── settings.py               # Configuration settings
├── database/
│   └── db_manager.py             # Database management
├── modules/
│   ├── face_recognition_module.py # Face recognition engine
│   ├── door_control.py           # Door & sensor control
│   └── auth_engine.py            # Authentication logic
├── firmware/                      # Embedded system code (C++)
├── web/                          # Web interface
└── logs/
    └── system.log                # System logs
```

## 🔧 Configuration

Edit `config/settings.py` to customize:
- GUI window dimensions
- Ultrasonic sensor threshold
- Auto-lock delay
- Face recognition sensitivity
- Database location

## 📊 Key Components

### Face Recognition Engine
- Real-time face detection using OpenCV
- Facial encoding matching using dlib
- Confidence scoring for authentication
- Support for multiple faces per user

### Door Control Module
- Servo motor control
- Door state management (LOCKED, UNLOCKED, LOCKING, UNLOCKING)
- Automatic re-locking with configurable delay
- GPIO pin configuration for Raspberry Pi

### Ultrasonic Sensor Monitor
- HC-SR04 sensor polling
- Configurable distance threshold
- Background thread operation
- Event-based triggering for silent unlock

### Database Layer
- SQLite database for reliability
- User management (registration, activation)
- Access logging (entry/exit events)
- System logging

## 🎮 GUI Features

The main GUI displays:
- **Camera Preview**: Live video feed with face detection overlay
- **Face Status**: Real-time face detection and matching results
- **Authentication Result**: ACCESS GRANTED/DENIED with username
- **Door Status**: Current lock state with visual indicator
- **Proximity Sensor**: Distance readings and threshold status
- **Recent Activity**: Log of recent system events

## 🔐 Security Features

- Face encoding comparison for authentication
- Configurable confidence threshold
- Access event logging with timestamps
- User activation/deactivation
- Audit trail for all door operations
- Secure password hashing (bcrypt)

## 📝 Access Logging

All access events are logged with:
- User ID
- Timestamp
- Event type (ENTRY/EXIT)
- Result (SUCCESS/DENIED)
- Face match confidence
- Failure reasons

View logs in:
- GUI Recent Activity panel
- `logs/system.log` file
- Database access_log table

## 🌐 Web Interface

The system includes a web portal for:
- Remote monitoring
- User management
- Access history review
- System configuration

Located in the `web/` directory.

## 🔌 Hardware Connections (Raspberry Pi)

### HC-SR04 Ultrasonic Sensor
- TRIG → GPIO 17
- ECHO → GPIO 27
- GND → GND
- VCC → 5V

### Servo Motor (Door Lock)
- Signal → GPIO 26 (PWM)
- GND → GND
- VCC → 5V

### Camera
- USB webcam or Pi Camera module

## 🐛 Troubleshooting

### Camera not detected
```bash
sudo apt-get install python3-pil python3-pil.imagetk
pip install pillow
```

### Face recognition errors
- Ensure adequate lighting
- Position face 30-60 cm from camera
- Complete user enrollment with multiple angles

### GPIO errors (Raspberry Pi)
- Run with sudo for GPIO access
- Check GPIO pin configuration in `config/settings.py`

### Database errors
- Delete `database/smart_door.db` to reset
- Check write permissions in database directory

## 📜 License

This project is open source and available under the MIT License.

## 👥 Contributors

- **Wearing-wind** - Project Lead

## 🤝 Contributing

Contributions are welcome! Please feel free to submit pull requests or open issues for bugs and feature requests.

## 📧 Support

For issues, questions, or suggestions, please open an issue on the GitHub repository.

---

**Status**: Active Development  
**Last Updated**: July 2026

