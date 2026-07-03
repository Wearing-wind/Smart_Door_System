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
        """Get the receiver email from system settings or active admin, fallback to config."""
        try:
            from modules.access_controller import AccessController
            ac = AccessController()
            db_email = ac.get_setting("alert_receiver_email")
            if db_email:
                return db_email
                
            cursor = self.admin_repo.db.execute("SELECT email FROM admin WHERE is_active = 1 LIMIT 1")
            row = cursor.fetchone()
            if row and row['email']:
                return row['email']
        except Exception as e:
            logger.warning(f"Failed to fetch receiver email, using fallback: {e}")
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


def send_visitor_pass_async(email_address: str, first_name: str, last_name: str, token: str, allowed_doors: str, expiration_date: str):
    """Dispatches a background daemon thread to send the visitor QR Pass via email."""
    threading.Thread(
        target=_send_visitor_email_sync,
        args=(email_address, first_name, last_name, token, allowed_doors, expiration_date),
        daemon=True
    ).start()


def _send_visitor_email_sync(email_address: str, first_name: str, last_name: str, token: str, allowed_doors: str, expiration_date: str):
    """Synchronous sender for visitor passes. Generates QR image and posts via SMTP server."""
    try:
        # Load SMTP settings dynamically from DB
        from modules.access_controller import AccessController
        ac = AccessController()
        
        smtp_server = ac.get_setting("smtp_server", "smtp.gmail.com") or "smtp.gmail.com"
        smtp_port = int(ac.get_setting("smtp_port", 587) or 587)
        smtp_username = ac.get_setting("smtp_username", "facialrecognitionandattendance@gmail.com") or "facialrecognitionandattendance@gmail.com"
        smtp_password = ac.get_setting("smtp_password", "awky zocc uvnq qzrd") or "awky zocc uvnq qzrd"
        
        if not smtp_username or not smtp_password:
            logger.error("SMTP username or password missing. Cannot send visitor email.")
            return

        # 1. Generate QR Code PNG in memory (pure python, bypasses DLL blocks)
        import qrcode
        import zlib
        import struct
        
        qr = qrcode.QRCode(version=1, error_correction=qrcode.constants.ERROR_CORRECT_H)
        qr.add_data(token)
        qr.make(fit=True)
        matrix = qr.modules
        
        orig_size = len(matrix)
        box_size = 8
        border = 3
        size = (orig_size + 2 * border) * box_size
        
        img_data = bytearray()
        for y in range(size):
            img_data.append(0) # Filter byte
            my = (y // box_size) - border
            for x in range(size):
                mx = (x // box_size) - border
                if 0 <= my < orig_size and 0 <= mx < orig_size:
                    pixel = 0 if matrix[my][mx] else 1
                else:
                    pixel = 1 # White border
                img_data.append(pixel)
                
        compressed = zlib.compress(img_data, level=9)
        
        def make_chunk(tag, data):
            return struct.pack("!I", len(data)) + tag + data + struct.pack("!I", zlib.crc32(tag + data))

        png_bytes = bytearray(b"\x89PNG\r\n\x1a\n")
        ihdr_data = struct.pack("!IIBBBBB", size, size, 8, 3, 0, 0, 0)
        png_bytes.extend(make_chunk(b"IHDR", ihdr_data))
        png_bytes.extend(make_chunk(b"PLTE", b"\x00\x00\x00\xff\xff\xff"))
        png_bytes.extend(make_chunk(b"IDAT", compressed))
        png_bytes.extend(make_chunk(b"IEND", b""))
        img_bytes = bytes(png_bytes)

        # 2. Build email body
        msg = MIMEMultipart('related')
        msg['Subject'] = f"Your Secure Smart Gate Entry Pass - {first_name} {last_name}"
        msg['From'] = smtp_username
        msg['To'] = email_address

        html_body = f"""
        <html>
        <body style="font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif; background-color: #f1f5f9; padding: 20px; margin: 0;">
            <div style="max-width: 480px; margin: 0 auto; background-color: #ffffff; border: 1px solid #e2e8f0; border-radius: 12px; padding: 30px; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.05);">
                <div style="text-align: center; margin-bottom: 25px;">
                    <span style="font-size: 24px; font-weight: bold; color: #3b82f6;">🔑 SMART GATE PASS</span>
                </div>
                
                <p style="font-size: 16px; color: #334155; line-height: 1.5; margin-bottom: 20px;">
                    Hello <strong>{first_name} {last_name}</strong>,
                </p>
                <p style="font-size: 14px; color: #475569; line-height: 1.5; margin-bottom: 25px;">
                    A secure visitor access pass has been generated for you. When you arrive at the gate, please present the QR code below directly to the camera feed.
                </p>
                
                <div style="background-color: #f8fafc; border: 1.5px dashed #cbd5e1; border-radius: 8px; padding: 20px; text-align: center; margin-bottom: 25px;">
                    <img src="cid:qr_image" alt="Access QR Code" style="width: 180px; height: 180px; border-radius: 4px;" />
                    <p style="font-family: monospace; font-size: 12px; color: #94a3b8; margin: 10px 0 0 0;">Token ID: {token}</p>
                </div>
                
                <div style="background-color: #f8fafc; border-radius: 8px; padding: 15px; margin-bottom: 25px;">
                    <table style="width: 100%; border-collapse: collapse; font-size: 14px; color: #475569;">
                        <tr>
                            <td style="padding: 4px 0; font-weight: 500;">Authorized Gate(s):</td>
                            <td style="padding: 4px 0; text-align: right; font-weight: 600; color: #0f172a;">{allowed_doors}</td>
                        </tr>
                        <tr>
                            <td style="padding: 4px 0; font-weight: 500;">Validity Ends:</td>
                            <td style="padding: 4px 0; text-align: right; font-weight: 600; color: #ef4444;">{expiration_date}</td>
                        </tr>
                    </table>
                </div>
                
                <p style="font-size: 12px; color: #64748b; line-height: 1.5; text-align: center; margin: 0; border-top: 1px solid #f1f5f9; padding-top: 20px;">
                    This pass is temporary. Keep it secure and do not forward it. If you lose it, contact the host to revoke it.
                </p>
            </div>
        </body>
        </html>
        """

        msg_alternative = MIMEMultipart('alternative')
        msg.attach(msg_alternative)
        msg_alternative.attach(MIMEText("Please view in HTML format to retrieve your access QR Pass.", 'plain'))
        msg_alternative.attach(MIMEText(html_body, 'html'))

        # Attach image as PNG inline
        from email.mime.image import MIMEImage
        image = MIMEImage(img_bytes)
        image.add_header('Content-ID', '<qr_image>')
        image.add_header('Content-Disposition', 'inline', filename="qr_pass.png")
        msg.attach(image)

        # Dispatch SMTP
        server = smtplib.SMTP(smtp_server, smtp_port)
        server.starttls()
        server.login(smtp_username, smtp_password)
        server.send_message(msg)
        server.quit()
        
        logger.info(f"Visitor QR Pass email successfully dispatched to {email_address}.")
        SystemLogRepository().info("EmailNotifier", f"Visitor pass emailed to {email_address}")
        
    except Exception as e:
        logger.error(f"Failed to send visitor pass email to {email_address}: {e}")
        SystemLogRepository().error("EmailNotifier", f"Failed sending pass email to {email_address}: {str(e)}")

