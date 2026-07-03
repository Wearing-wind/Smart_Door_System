"""
Smart Door Security System - QR Code Scanner Engine
Integrates with CameraManager to scan, decode, and visually highlight QR Passes.
"""

import cv2
import numpy as np
import time
import logging
from typing import Optional, Tuple, Dict, Any
from dataclasses import dataclass
from enum import Enum

from modules.face_recognition_module import CameraManager
from database.qr_repository import QRRepository

logger = logging.getLogger(__name__)

class QRStatus(Enum):
    NO_QR = "Scanning for QR Pass..."
    QR_DETECTED = "QR Code Detected"
    VALIDATING = "Validating Token..."
    ACCESS_GRANTED = "Access Granted"
    ACCESS_DENIED = "Access Denied"
    CAMERA_ERROR = "Camera Error"


@dataclass
class QRResult:
    """Represents the outcome of a frame scan."""
    status: QRStatus
    qr_token: Optional[str] = None
    user_id: Optional[int] = None
    user_name: Optional[str] = None
    employee_id: Optional[str] = None
    frame: Optional[np.ndarray] = None
    points: Optional[np.ndarray] = None
    message: str = ""


class QRScannerEngine:
    """QR Code scanning engine processing frames in real-time."""
    
    def __init__(self):
        self.camera = CameraManager()
        self.detector = cv2.QRCodeDetector()
        self.qr_repo = QRRepository()
        
        # Scanner configurations & tracking
        self.scan_cooldown = 4.0  # seconds to ignore the same token
        self.last_scans: Dict[str, float] = {}  # token -> timestamp
        
        # Last validation result cache for UI bounding box color feedback
        self.last_validation_token: Optional[str] = None
        self.last_validation_time = 0.0
        self.last_validation_status = QRStatus.NO_QR
        self.last_validation_msg = ""
        self.last_validation_user_id: Optional[int] = None
        self.last_validation_user_name: Optional[str] = None
        self.last_validation_employee_id: Optional[str] = None

    def start(self) -> bool:
        """Start the background camera manager."""
        return self.camera.start()

    def stop(self):
        """Stop the camera manager."""
        self.camera.stop()

    def process_frame(self) -> QRResult:
        """
        Grab a camera frame, run the QR code detector, draw boundaries, and decode tokens.
        
        Returns:
            QRResult detailing the current frame's status.
        """
        frame = self.camera.get_frame()
        if frame is None:
            return QRResult(status=QRStatus.CAMERA_ERROR, message="No camera feed available.")

        frame_copy = frame.copy()
        
        try:
            # 1. Detect and decode QR Code in frame
            val, pts, _ = self.detector.detectAndDecode(frame_copy)
            
            current_time = time.time()
            
            # If visual cache expired (older than 3 seconds), clear it
            if current_time - self.last_validation_time > 3.0:
                self.last_validation_token = None
                self.last_validation_status = QRStatus.NO_QR
                self.last_validation_msg = ""

            if val:
                qr_token = val.strip()
                
                # Check scan cooldown to prevent double scans
                is_in_cooldown = False
                if qr_token in self.last_scans:
                    if current_time - self.last_scans[qr_token] < self.scan_cooldown:
                        is_in_cooldown = True
                
                if not is_in_cooldown:
                    # Update scan timestamp
                    self.last_scans[qr_token] = current_time
                    self.last_validation_token = qr_token
                    self.last_validation_time = current_time
                    
                    # Validate against database
                    # Importing inside method to avoid circular reference issues if any
                    from modules.access_controller import AccessController
                    ac = AccessController(door_controller=None) # We just use it for validation
                    is_valid, user, reason = self.qr_repo.validate_token(qr_token, "Main Entrance")
                    
                    if is_valid:
                        self.last_validation_status = QRStatus.ACCESS_GRANTED
                        user_name = f"{user['first_name']} {user['last_name']}"
                        self.last_validation_user_id = user['id']
                        self.last_validation_user_name = user_name
                        self.last_validation_employee_id = user['employee_id']
                        self.last_validation_msg = f"ACCESS GRANTED: {user_name}"
                        logger.info(f"QR Scan successful: {user_name} ({qr_token})")
                    else:
                        self.last_validation_status = QRStatus.ACCESS_DENIED
                        self.last_validation_user_id = None
                        self.last_validation_user_name = None
                        self.last_validation_employee_id = None
                        self.last_validation_msg = f"ACCESS DENIED: {reason}"
                        logger.warning(f"QR Scan rejected: {reason} ({qr_token})")
                
                # Draw bounding box for the detected QR code
                if pts is not None and len(pts) > 0:
                    pts_int = pts.astype(int)
                    if pts_int.ndim == 3:
                        pts_int = pts_int[0]
                    
                    # Pick box color based on validation status
                    if self.last_validation_status == QRStatus.ACCESS_GRANTED:
                        color = (0, 255, 0)  # Green
                    elif self.last_validation_status == QRStatus.ACCESS_DENIED:
                        color = (0, 0, 255)  # Red
                    else:
                        color = (0, 255, 255)  # Yellow
                        
                    cv2.polylines(frame_copy, [pts_int], True, color, 3)
                    
                    # Label text
                    label = self.last_validation_user_name or "QR Code"
                    if self.last_validation_status == QRStatus.ACCESS_DENIED:
                        label = "Unauthorized"
                    cv2.putText(
                        frame_copy, label, (pts_int[0][0], pts_int[0][1] - 10),
                        cv2.FONT_HERSHEY_DUPLEX, 0.7, color, 2
                    )

                # Return the result
                return QRResult(
                    status=self.last_validation_status,
                    qr_token=qr_token,
                    user_id=self.last_validation_user_id,
                    user_name=self.last_validation_user_name,
                    employee_id=self.last_validation_employee_id,
                    frame=frame_copy,
                    points=pts,
                    message=self.last_validation_msg
                )

            # If no QR detected, but we are displaying the cached validation status
            if self.last_validation_token:
                return QRResult(
                    status=self.last_validation_status,
                    qr_token=self.last_validation_token,
                    user_id=self.last_validation_user_id,
                    user_name=self.last_validation_user_name,
                    employee_id=self.last_validation_employee_id,
                    frame=frame_copy,
                    message=self.last_validation_msg
                )

            # Standard state when no QR detected
            return QRResult(
                status=QRStatus.NO_QR,
                frame=frame_copy,
                message="Show QR Pass to the camera"
            )

        except Exception as e:
            logger.error(f"Error scanning QR frame: {e}")
            return QRResult(
                status=QRStatus.CAMERA_ERROR,
                frame=frame_copy,
                message=f"Scan error: {str(e)}"
            )

    def get_current_frame(self) -> Optional[np.ndarray]:
        """Fetch frame directly from the camera."""
        return self.camera.get_frame()
