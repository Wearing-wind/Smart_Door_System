"""
Smart Door Security System - Email Notifier
Handles sending email alerts when unknown faces are detected.
"""

import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.image import MIMEImage
import time
import threading
import logging
import cv2
from datetime import datetime

from config.settings import (
    SMTP_SERVER, SMTP_PORT, SMTP_USERNAME, SMTP_PASSWORD, EMAIL_RECIPIENT,
    UNKNOWN_FACE_EMAIL_THRESHOLD, EMAIL_COOLDOWN
)
from database.db_manager import SystemLogRepository, AdminRepository

logger = logging.getLogger(__name__)

class EmailNotifier:
    """Manages email alerts for consecutive unknown face detections."""
    
    def __init__(self):
        self.consecutive_unknowns = 0
        self.last_email_time = 0
        self.system_log = SystemLogRepository()
        self.admin_repo = AdminRepository()
        self._lock = threading.Lock()
        
    def _get_receiver_email(self):
        """Get the receiver email from the active admin or fallback to config."""
        try:
            cursor = self.admin_repo.db.execute("SELECT email FROM admin WHERE is_active = 1 LIMIT 1")
            row = cursor.fetchone()
            if row and row['email']:
                return row['email']
        except Exception as e:
            logger.warning(f"Failed to fetch receiver email from DB, using fallback: {e}")
        return EMAIL_RECIPIENT

    def process_unknown_face(self, frame=None):
        """Process an unknown face detection event."""
        with self._lock:
            current_time = time.time()
            
            # If still in cooldown period, just return (could optionally reset count)
            if current_time - self.last_email_time < EMAIL_COOLDOWN:
                return

            self.consecutive_unknowns += 1
            logger.info(f"Unknown face detected. Count: {self.consecutive_unknowns}/{UNKNOWN_FACE_EMAIL_THRESHOLD}")
            
            if self.consecutive_unknowns >= UNKNOWN_FACE_EMAIL_THRESHOLD:
                # Reset counter and set last email time
                self.consecutive_unknowns = 0
                self.last_email_time = current_time
                
                # Send email in a background thread to avoid blocking face recognition
                threading.Thread(
                    target=self._send_alert_email,
                    args=(frame,),
                    daemon=True
                ).start()

    def reset_unknowns(self):
        """Reset the consecutive unknown face counter."""
        with self._lock:
            if self.consecutive_unknowns > 0:
                self.consecutive_unknowns = 0

    def _send_alert_email(self, frame):
        """Send the alert email securely using smtplib."""
        try:
            msg = MIMEMultipart()
            msg['From'] = SMTP_USERNAME
            msg['To'] = self._get_receiver_email()
            
            current_time_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            msg['Subject'] = f"[ALERT] Security Alert: Unknown Face Detected Multiple Times - {current_time_str}"
            
            body = (
                "Security Notification,\n\n"
                f"An unknown face has been detected {UNKNOWN_FACE_EMAIL_THRESHOLD} times consecutively at the smart door.\n"
                f"Time: {current_time_str}\n\n"
                "This is an automated security alert. Please check the dashboard or logs immediately."
            )
            msg.attach(MIMEText(body, 'plain'))
            
            # Attach the face frame if provided
            if frame is not None:
                # Convert BGR to RGB if needed, but cv2.imencode handles BGR fine
                ret, buffer = cv2.imencode('.jpg', frame)
                if ret:
                    img_data = buffer.tobytes()
                    image = MIMEImage(img_data, name="unknown_face.jpg")
                    msg.attach(image)

            # Connect and send
            server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
            server.starttls()
            server.login(SMTP_USERNAME, SMTP_PASSWORD)
            server.send_message(msg)
            server.quit()
            
            logger.info(f"Security alert email sent successfully to {msg['To']}.")
            self.system_log.info("EmailNotifier", f"Security alert email sent to {msg['To']}.")
        except Exception as e:
            logger.error(f"Failed to send email: {e}")
            self.system_log.error("EmailNotifier", f"Failed to send email: {str(e)}")

# Singleton instance
_email_notifier_instance = None
def get_email_notifier():
    global _email_notifier_instance
    if _email_notifier_instance is None:
        _email_notifier_instance = EmailNotifier()
    return _email_notifier_instance
