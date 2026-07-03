"""
Smart Door Security System - Access Controller
Handles token validation, door opening commands, encrypted configuration, and notifications.
"""

import json
import time
import base64
import logging
import requests
import threading
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from typing import Optional, Dict, Any, Tuple
HAS_CRYPTOGRAPHY = True
try:
    from cryptography.fernet import Fernet
except ImportError:
    HAS_CRYPTOGRAPHY = False
import hashlib

from config.settings import SECRET_KEY, SMTP_SERVER, SMTP_PORT, SMTP_USERNAME, SMTP_PASSWORD
from database.qr_repository import QRRepository
from modules.door_control import DoorController

logger = logging.getLogger(__name__)

class ConfigEncryptor:
    """Handles symmetric encryption for sensitive configuration options."""
    
    @staticmethod
    def _get_key() -> bytes:
        """Derive a valid 32-byte urlsafe Base64 key from Flask's SECRET_KEY."""
        h = hashlib.sha256(SECRET_KEY.encode('utf-8')).digest()
        return base64.urlsafe_b64encode(h)

    @classmethod
    def encrypt(cls, plaintext: str) -> str:
        """Encrypt plain text config value."""
        if not plaintext:
            return ""
        if not HAS_CRYPTOGRAPHY:
            logger.warning("cryptography module not available. Storing configuration in plaintext.")
            return plaintext
        try:
            f = Fernet(cls._get_key())
            return f.encrypt(plaintext.encode('utf-8')).decode('utf-8')
        except Exception as e:
            logger.error(f"Encryption failed: {e}")
            return ""

    @classmethod
    def decrypt(cls, ciphertext: str) -> str:
        """Decrypt cipher text config value."""
        if not ciphertext:
            return ""
        if not HAS_CRYPTOGRAPHY:
            logger.warning("cryptography module not available. Returning plaintext value.")
            return ciphertext
        try:
            f = Fernet(cls._get_key())
            return f.decrypt(ciphertext.encode('utf-8')).decode('utf-8')
        except Exception as e:
            # If decryption fails (e.g. if the value was saved in plaintext during fallback), return as-is
            logger.debug(f"Decryption failed, returning value in plaintext: {e}")
            return ciphertext


class AccessController:
    """Orchestrates QR verification and outputs (door unlocking, logging, notification)."""
    
    def __init__(self, door_controller: Optional[DoorController] = None):
        self.qr_repo = QRRepository()
        self.door_controller = door_controller or DoorController()

    def get_setting(self, key: str, default: Any = None) -> Any:
        """Fetch setting value from system_settings, with decrypt fallback."""
        try:
            cursor = self.qr_repo.db.execute(
                "SELECT value, is_encrypted FROM system_settings WHERE key = ?", (key,)
            )
            row = cursor.fetchone()
            if not row:
                return default
            val = row['value']
            if row['is_encrypted']:
                return ConfigEncryptor.decrypt(val)
            return val
        except Exception as e:
            logger.error(f"Error fetching setting {key}: {e}")
            return default

    def set_setting(self, key: str, value: str, encrypt: bool = False) -> bool:
        """Store setting value in system_settings, optionally encrypted."""
        try:
            stored_val = ConfigEncryptor.encrypt(value) if encrypt else value
            
            cursor = self.qr_repo.db.execute(
                "SELECT 1 FROM system_settings WHERE key = ?", (key,)
            )
            exists = cursor.fetchone()
            
            if exists:
                self.qr_repo.db.execute(
                    "UPDATE system_settings SET value = ?, is_encrypted = ?, updated_at = ? WHERE key = ?",
                    (stored_val, 1 if encrypt else 0, datetime.now(), key)
                )
            else:
                self.qr_repo.db.execute(
                    "INSERT INTO system_settings (key, value, is_encrypted) VALUES (?, ?, ?)",
                    (key, stored_val, 1 if encrypt else 0)
                )
            self.qr_repo.db.commit()
            return True
        except Exception as e:
            logger.error(f"Error saving setting {key}: {e}")
            return False

    def process_qr_scan(self, qr_token: str, door_name: str = "Main Entrance",
                        camera_id: str = "Scanner Camera", ip_address: Optional[str] = None) -> Tuple[bool, str]:
        """
        Validate QR token, logs access result, triggers door unlock, and fires notifications.
        
        Returns:
            Tuple: (is_valid: bool, status_message: str)
        """
        # Validate QR code with database engine
        is_valid, user, reason = self.qr_repo.validate_token(qr_token, door_name)
        
        result_status = "SUCCESS" if is_valid else "DENIED"
        user_id = user['id'] if user else None
        
        # Log to DB
        self.qr_repo.log_qr_access(
            user_id=user_id,
            qr_token=qr_token,
            door=door_name,
            result=result_status,
            camera=camera_id,
            reason=reason,
            ip_address=ip_address
        )
        
        if is_valid:
            user_name = f"{user['first_name']} {user['last_name']}"
            # Trigger Door Controller
            self.door_controller.unlock(reason=f"QR Code: {user_name} ({user['employee_id']})")
            
            # Send Notification asynchronously
            threading.Thread(
                target=self._dispatch_notifications,
                args=(user, qr_token, door_name, camera_id),
                daemon=True
            ).start()
            
            return True, f"Welcome, {user_name}!"
        else:
            # Send alert for failed/unauthorized access in background
            threading.Thread(
                target=self._dispatch_failure_alerts,
                args=(qr_token, door_name, camera_id, reason),
                daemon=True
            ).start()
            return False, f"Access Denied: {reason}"

    def _dispatch_notifications(self, user: Dict[str, Any], qr_token: str, door: str, camera: str):
        """Dispatches all configured notifications for a successful access event."""
        # 1. Webhook
        if self.get_setting("webhook_notifications_enabled") == "true":
            self._send_webhook(user, qr_token, door, camera, "access.granted")
            
        # 2. Email Notification
        if self.get_setting("email_notifications_enabled") == "true":
            self._send_email_notification(user, door, "Access Granted")

        # 3. Simulated SMS Gateway
        if self.get_setting("sms_notifications_enabled") == "true":
            phone = user.get('phone')
            if phone:
                user_name = f"{user['first_name']} {user['last_name']}"
                logger.info(f"[SMS SIMULATION] Sent SMS to {phone}: Access Granted at {door} for {user_name}.")

    def _dispatch_failure_alerts(self, qr_token: str, door: str, camera: str, reason: str):
        """Dispatches alerts for unauthorized or failed entry scans."""
        # 1. Webhook for security warning
        if self.get_setting("webhook_notifications_enabled") == "true":
            user_payload = {"employee_id": "Unknown", "first_name": "Visitor/Attempt", "last_name": ""}
            self._send_webhook(user_payload, qr_token, door, camera, "access.denied", reason=reason)

        # 2. Email alert if enabled
        if self.get_setting("email_notifications_enabled") == "true":
            self._send_email_alert_failure(qr_token, door, reason)

    def _send_webhook(self, user: Dict[str, Any], qr_token: str, door: str, camera: str, event_type: str, reason: str = ""):
        """Post JSON webhook payloads securely to external API URL."""
        webhook_url = self.get_setting("webhook_url")
        if not webhook_url:
            return
            
        payload = {
            "event": event_type,
            "timestamp": datetime.now().isoformat(),
            "door": door,
            "camera": camera,
            "qr_token": qr_token,
            "user": {
                "id": user.get("id"),
                "employee_id": user.get("employee_id"),
                "name": f"{user.get('first_name')} {user.get('last_name')}",
                "user_type": user.get("user_type", "Visitor"),
                "department": user.get("department")
            }
        }
        if reason:
            payload["reason"] = reason

        try:
            # Post with short timeout
            response = requests.post(webhook_url, json=payload, timeout=3)
            logger.info(f"Webhook {event_type} dispatched to {webhook_url}. Status: {response.status_code}")
        except Exception as e:
            logger.error(f"Failed to post webhook: {e}")

    def _send_email_notification(self, user: Dict[str, Any], door: str, subject_prefix: str):
        """Send standard alert email to administrator."""
        admin_email = self.get_setting("alert_recipient_email", SMTP_USERNAME)
        if not admin_email:
            return

        try:
            msg = MIMEMultipart()
            msg['From'] = SMTP_USERNAME
            msg['To'] = admin_email
            msg['Subject'] = f"[{subject_prefix}] Smart Door Entry Alert"
            
            user_name = f"{user['first_name']} {user['last_name']}"
            body = (
                f"Smart Door Entry Activity Notification:\n\n"
                f"User: {user_name} ({user.get('user_type', 'Visitor')})\n"
                f"Employee ID: {user.get('employee_id')}\n"
                f"Door: {door}\n"
                f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
                f"Access result: GRANTED."
            )
            msg.attach(MIMEText(body, 'plain'))

            server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
            server.starttls()
            server.login(SMTP_USERNAME, SMTP_PASSWORD)
            server.send_message(msg)
            server.quit()
            logger.info(f"Access notification email sent to {admin_email}.")
        except Exception as e:
            logger.error(f"Failed to send alert email: {e}")

    def _send_email_alert_failure(self, qr_token: str, door: str, reason: str):
        """Send alert email when access is denied."""
        admin_email = self.get_setting("alert_recipient_email", SMTP_USERNAME)
        if not admin_email:
            return

        try:
            msg = MIMEMultipart()
            msg['From'] = SMTP_USERNAME
            msg['To'] = admin_email
            msg['Subject'] = f"[WARNING] Smart Door Security Alert: Access Denied"
            
            body = (
                f"Security Alert: Access Denied at Smart Door\n\n"
                f"Token presented: {qr_token}\n"
                f"Door: {door}\n"
                f"Failure reason: {reason}\n"
                f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
                f"Please review the administrator logs immediately."
            )
            msg.attach(MIMEText(body, 'plain'))

            server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
            server.starttls()
            server.login(SMTP_USERNAME, SMTP_PASSWORD)
            server.send_message(msg)
            server.quit()
            logger.warning(f"Failure alert email sent to {admin_email}.")
        except Exception as e:
            logger.error(f"Failed to send failure alert email: {e}")
