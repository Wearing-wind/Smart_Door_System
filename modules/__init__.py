"""
Smart Door Security System - Modules Package
"""

try:
    from modules.face_recognition_module import (
        FaceRecognitionEngine,
        FaceEnrollment,
        FaceResult,
        FaceStatus,
        CameraManager
    )
except ImportError:
    FaceRecognitionEngine = None
    FaceEnrollment = None
    FaceResult = None
    FaceStatus = None
    CameraManager = None

from modules.door_control import (
    DoorController,
    DoorMonitor,
    DoorState,
    DoorStatus
)

from modules.auth_engine import (
    AuthenticationEngine,
    AuthSession,
    AuthState
)

__all__ = [
    'FaceRecognitionEngine',
    'FaceEnrollment',
    'FaceResult',
    'FaceStatus',
    'CameraManager',
    'DoorController',
    'DoorMonitor',
    'DoorState',
    'DoorStatus',
    'AuthenticationEngine',
    'AuthSession',
    'AuthState'
]
