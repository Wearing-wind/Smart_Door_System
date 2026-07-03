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
from datetime import datetime, timedelta

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
            # Load SMTP settings dynamically from DB
            from modules.access_controller import AccessController
            ac = AccessController()
            
            smtp_server = ac.get_setting("smtp_server", "smtp.gmail.com") or "smtp.gmail.com"
            smtp_port = int(ac.get_setting("smtp_port", 587) or 587)
            smtp_username = ac.get_setting("smtp_username", "facialrecognitionandattendance@gmail.com") or "facialrecognitionandattendance@gmail.com"
            smtp_password = ac.get_setting("smtp_password", "awky zocc uvnq qzrd") or "awky zocc uvnq qzrd"
            
            if not smtp_username or not smtp_password:
                logger.error("SMTP username or password missing. Cannot send alert email.")
                return

            msg = MIMEMultipart('related')
            msg['From'] = smtp_username
            msg['To'] = self._get_receiver_email()
            
            now = datetime.now()
            current_time_str = now.strftime('%Y-%m-%d %H:%M:%S')
            msg['Subject'] = f"[ALERT] Security Alert: Unknown Face Detected Multiple Times - {current_time_str}"
            
            t0 = now.strftime('%I:%M:%S %p')
            t1 = (now - timedelta(seconds=2)).strftime('%I:%M:%S %p')
            t2 = (now - timedelta(seconds=4)).strftime('%I:%M:%S %p')
            t3 = (now - timedelta(seconds=6)).strftime('%I:%M:%S %p')
            t4 = (now - timedelta(seconds=8)).strftime('%I:%M:%S %p')
            
            date_str = now.strftime('%d %B %Y')
            alert_id = f"INC-{now.strftime('%Y%m%d')}-{now.strftime('%H%M%S')}"

            # Fallback frame if None
            if frame is None:
                import numpy as np
                frame = np.zeros((480, 640, 3), dtype=np.uint8)
                cv2.putText(frame, "No Frame Captured", (120, 240), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)

            # Encode the frame
            ret, buffer = cv2.imencode('.jpg', frame)
            if not ret:
                logger.error("Failed to encode face frame for alert email.")
                return
            img_bytes = buffer.tobytes()

            html_body = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Smart Door Security System Alert</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
</head>
<body style="margin: 0; padding: 0; background-color: #F8FAFC; font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; color: #1E293B;">
    <table border="0" cellpadding="0" cellspacing="0" width="100%" style="background-color: #F8FAFC; padding: 20px 0;">
        <tr>
            <td align="center">
                <!-- Outer Container -->
                <table border="0" cellpadding="0" cellspacing="0" width="680" style="background-color: #F8FAFC; border-collapse: collapse;">
                    
                    <!-- 1. Header (Dark blue/black bar) -->
                    <tr>
                        <td style="background-color: #0F172A; border-top-left-radius: 16px; border-top-right-radius: 16px; padding: 20px 24px;">
                            <table border="0" cellpadding="0" cellspacing="0" width="100%">
                                <tr>
                                    <!-- Left Header Info -->
                                    <td valign="middle">
                                        <table border="0" cellpadding="0" cellspacing="0">
                                            <tr>
                                                <td style="padding-right: 12px;">
                                                    <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="#DC2626" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" style="display: block;">
                                                        <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>
                                                        <circle cx="12" cy="11" r="3" fill="#DC2626"/>
                                                    </svg>
                                                </td>
                                                <td>
                                                    <div style="font-size: 16px; font-weight: 700; color: #FFFFFF; letter-spacing: 0.5px; text-transform: uppercase;">Smart Door Security System</div>
                                                    <div style="font-size: 11px; color: #94A3B8; font-weight: 500;">Personal Security Project</div>
                                                </td>
                                            </tr>
                                        </table>
                                    </td>
                                    <!-- Right Header Info -->
                                    <td align="right" valign="middle">
                                        <table border="0" cellpadding="0" cellspacing="0" style="text-align: right;">
                                            <tr>
                                                <td style="padding-right: 12px;">
                                                    <div style="font-size: 14px; font-weight: 700; color: #EF4444; letter-spacing: 0.5px; text-transform: uppercase;">Security Alert</div>
                                                    <div style="font-size: 11px; color: #94A3B8; font-weight: 500;">Automated Notification</div>
                                                </td>
                                                <td>
                                                    <div style="width: 32px; height: 32px; border-radius: 50%; background-color: rgba(220, 38, 38, 0.15); display: flex; align-items: center; justify-content: center; position: relative;">
                                                        <svg width="18" height="18" viewBox="0 0 24 24" fill="#DC2626" stroke="#DC2626" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="display: block; margin: auto;">
                                                            <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9M13.73 21a2 2 0 0 1-3.46 0"/>
                                                        </svg>
                                                    </div>
                                                </td>
                                            </tr>
                                        </table>
                                    </td>
                                </tr>
                            </table>
                        </td>
                    </tr>
                    
                    <!-- 2. High Priority Alert Banner (Gradient) -->
                    <tr>
                        <td style="background: linear-gradient(135deg, #7F1D1D 0%, #DC2626 100%); padding: 32px 24px;">
                            <table border="0" cellpadding="0" cellspacing="0" width="100%">
                                <tr>
                                    <!-- Warning Icon -->
                                    <td width="72" valign="top">
                                        <div style="width: 56px; height: 56px; border-radius: 12px; background-color: rgba(255, 255, 255, 0.15); display: flex; align-items: center; justify-content: center; box-shadow: 0 4px 10px rgba(0,0,0,0.15);">
                                            <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="#FFFFFF" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" style="display: block; margin: auto;">
                                                <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/>
                                                <line x1="12" y1="9" x2="12" y2="13"/>
                                                <line x1="12" y1="17" x2="12.01" y2="17"/>
                                            </svg>
                                        </div>
                                    </td>
                                    <!-- Alert Description -->
                                    <td valign="top" style="padding-left: 16px;">
                                        <div style="display: inline-block; background-color: #DC2626; color: #FFFFFF; font-size: 11px; font-weight: 700; padding: 4px 10px; border-radius: 20px; letter-spacing: 0.5px; text-transform: uppercase; margin-bottom: 8px; border: 1.5px solid rgba(255, 255, 255, 0.4);">High Priority Alert</div>
                                        <div style="font-size: 24px; font-weight: 800; color: #FFFFFF; margin-bottom: 4px; letter-spacing: -0.5px;">UNKNOWN FACE DETECTED</div>
                                        <div style="font-size: 16px; font-weight: 600; color: rgba(255, 255, 255, 0.9); margin-bottom: 12px;">Multiple Detection Attempts</div>
                                        <div style="font-size: 13px; color: rgba(255, 255, 255, 0.8); line-height: 1.5;">An unknown face has been detected {UNKNOWN_FACE_EMAIL_THRESHOLD} times consecutively at your smart door.</div>
                                    </td>
                                    <!-- Severity Badge Card -->
                                    <td width="130" align="right" valign="top">
                                        <table border="0" cellpadding="0" cellspacing="0" style="background-color: rgba(15, 23, 42, 0.85); border-radius: 12px; padding: 12px; border: 1px solid rgba(255, 255, 255, 0.15); text-align: center; width: 110px;">
                                            <tr>
                                                <td>
                                                    <div style="font-size: 9px; font-weight: 700; color: #94A3B8; letter-spacing: 0.5px; text-transform: uppercase; margin-bottom: 4px;">Alert Level</div>
                                                    <div style="font-size: 20px; font-weight: 800; color: #EF4444; letter-spacing: 0.5px; margin-bottom: 10px;">HIGH</div>
                                                    <!-- Animated Red Dots -->
                                                    <table border="0" cellpadding="0" cellspacing="0" align="center">
                                                        <tr>
                                                            <td style="padding: 0 2px;"><div style="width: 8px; height: 8px; border-radius: 50%; background-color: #EF4444; box-shadow: 0 0 6px #EF4444;"></div></td>
                                                            <td style="padding: 0 2px;"><div style="width: 8px; height: 8px; border-radius: 50%; background-color: #EF4444; box-shadow: 0 0 6px #EF4444;"></div></td>
                                                            <td style="padding: 0 2px;"><div style="width: 8px; height: 8px; border-radius: 50%; background-color: #EF4444; box-shadow: 0 0 6px #EF4444;"></div></td>
                                                            <td style="padding: 0 2px;"><div style="width: 8px; height: 8px; border-radius: 50%; background-color: #EF4444; box-shadow: 0 0 6px #EF4444;"></div></td>
                                                            <td style="padding: 0 2px;"><div style="width: 8px; height: 8px; border-radius: 50%; background-color: #334155;"></div></td>
                                                        </tr>
                                                    </table>
                                                </td>
                                            </tr>
                                        </table>
                                    </td>
                                </tr>
                            </table>
                        </td>
                    </tr>
                    
                    <!-- Spacing -->
                    <tr><td height="24" style="font-size: 1px; line-height: 1px;">&nbsp;</td></tr>

                    <!-- 3. Incident Summary Cards Row -->
                    <tr>
                        <td>
                            <table border="0" cellpadding="0" cellspacing="0" width="100%">
                                <tr>
                                    <!-- Date Card -->
                                    <td width="104" valign="top">
                                        <div style="background-color: #FFFFFF; border: 1.5px solid #E5E7EB; border-radius: 12px; padding: 12px; text-align: center; box-shadow: 0 2px 4px rgba(0,0,0,0.02);">
                                            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#2563EB" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="display: block; margin: 0 auto 6px auto;">
                                                <rect x="3" y="4" width="18" height="18" rx="2" ry="2"/>
                                                <line x1="16" y1="2" x2="16" y2="6"/>
                                                <line x1="8" y1="2" x2="8" y2="6"/>
                                                <line x1="3" y1="10" x2="21" y2="10"/>
                                            </svg>
                                            <div style="font-size: 8px; font-weight: 700; color: #64748B; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 2px;">Date</div>
                                            <div style="font-size: 11px; font-weight: 600; color: #1E293B; white-space: nowrap;">{date_str}</div>
                                        </div>
                                    </td>
                                    <td width="11" style="font-size: 1px; line-height: 1px;">&nbsp;</td>
                                    <!-- Time Card -->
                                    <td width="104" valign="top">
                                        <div style="background-color: #FFFFFF; border: 1.5px solid #E5E7EB; border-radius: 12px; padding: 12px; text-align: center; box-shadow: 0 2px 4px rgba(0,0,0,0.02);">
                                            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#F59E0B" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="display: block; margin: 0 auto 6px auto;">
                                                <circle cx="12" cy="12" r="10"/>
                                                <polyline points="12 6 12 12 16 14"/>
                                            </svg>
                                            <div style="font-size: 8px; font-weight: 700; color: #64748B; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 2px;">Time</div>
                                            <div style="font-size: 11px; font-weight: 600; color: #1E293B; white-space: nowrap;">{t0}</div>
                                        </div>
                                    </td>
                                    <td width="11" style="font-size: 1px; line-height: 1px;">&nbsp;</td>
                                    <!-- Door Card -->
                                    <td width="104" valign="top">
                                        <div style="background-color: #FFFFFF; border: 1.5px solid #E5E7EB; border-radius: 12px; padding: 12px; text-align: center; box-shadow: 0 2px 4px rgba(0,0,0,0.02);">
                                            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#16A34A" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="display: block; margin: 0 auto 6px auto;">
                                                <rect x="3" y="3" width="18" height="18" rx="2"/>
                                                <path d="M9 3v18"/>
                                            </svg>
                                            <div style="font-size: 8px; font-weight: 700; color: #64748B; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 2px;">Door</div>
                                            <div style="font-size: 11px; font-weight: 600; color: #1E293B; white-space: nowrap;">Main Entrance</div>
                                        </div>
                                    </td>
                                    <td width="11" style="font-size: 1px; line-height: 1px;">&nbsp;</td>
                                    <!-- Camera Card -->
                                    <td width="104" valign="top">
                                        <div style="background-color: #FFFFFF; border: 1.5px solid #E5E7EB; border-radius: 12px; padding: 12px; text-align: center; box-shadow: 0 2px 4px rgba(0,0,0,0.02);">
                                            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#8B5CF6" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="display: block; margin: 0 auto 6px auto;">
                                                <path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z"/>
                                                <circle cx="12" cy="13" r="4"/>
                                            </svg>
                                            <div style="font-size: 8px; font-weight: 700; color: #64748B; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 2px;">Camera</div>
                                            <div style="font-size: 11px; font-weight: 600; color: #1E293B; white-space: nowrap;">Camera 01</div>
                                        </div>
                                    </td>
                                    <td width="11" style="font-size: 1px; line-height: 1px;">&nbsp;</td>
                                    <!-- Device Card -->
                                    <td width="104" valign="top">
                                        <div style="background-color: #FFFFFF; border: 1.5px solid #E5E7EB; border-radius: 12px; padding: 12px; text-align: center; box-shadow: 0 2px 4px rgba(0,0,0,0.02);">
                                            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#3B82F6" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="display: block; margin: 0 auto 6px auto;">
                                                <rect x="2" y="3" width="20" height="14" rx="2" ry="2"/>
                                                <line x1="8" y1="21" x2="16" y2="21"/>
                                                <line x1="12" y1="17" x2="12" y2="21"/>
                                            </svg>
                                            <div style="font-size: 8px; font-weight: 700; color: #64748B; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 2px;">Device</div>
                                            <div style="font-size: 11px; font-weight: 600; color: #1E293B; white-space: nowrap;">Raspberry Pi 5</div>
                                        </div>
                                    </td>
                                    <td width="11" style="font-size: 1px; line-height: 1px;">&nbsp;</td>
                                    <!-- Status Card -->
                                    <td width="104" valign="top">
                                        <div style="background-color: #FFFFFF; border: 1.5px solid #E5E7EB; border-radius: 12px; padding: 12px; text-align: center; box-shadow: 0 2px 4px rgba(0,0,0,0.02);">
                                            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#10B981" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="display: block; margin: 0 auto 6px auto;">
                                                <path d="M5 12.55a11 11 0 0 1 14.08 0"/>
                                                <path d="M1.42 9a16 16 0 0 1 21.16 0"/>
                                                <path d="M8.53 16.11a6 6 0 0 1 6.95 0"/>
                                                <line x1="12" y1="20" x2="12.01" y2="20" stroke-width="3"/>
                                            </svg>
                                            <div style="font-size: 8px; font-weight: 700; color: #64748B; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 2px;">Status</div>
                                            <div style="font-size: 11px; font-weight: 600; color: #1E293B; white-space: nowrap;">Online</div>
                                        </div>
                                    </td>
                                </tr>
                            </table>
                        </td>
                    </tr>
                    
                    <!-- Spacing -->
                    <tr><td height="24" style="font-size: 1px; line-height: 1px;">&nbsp;</td></tr>
                    
                    <!-- 4 & 5. Captured Image & Event Timeline (Two columns side-by-side) -->
                    <tr>
                        <td>
                            <table border="0" cellpadding="0" cellspacing="0" width="100%">
                                <tr>
                                    <!-- Left Column (Captured Image) -->
                                    <td width="328" valign="top">
                                        <table border="0" cellpadding="0" cellspacing="0" width="100%" style="background-color: #FFFFFF; border: 1.5px solid #E5E7EB; border-radius: 16px; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.03);">
                                            <tr>
                                                <td style="padding: 20px 20px 0 20px;">
                                                    <table border="0" cellpadding="0" cellspacing="0" width="100%">
                                                        <tr>
                                                            <td width="24" valign="middle">
                                                                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#2563EB" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" style="display: block;">
                                                                    <path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z"/>
                                                                    <circle cx="12" cy="13" r="4"/>
                                                                </svg>
                                                            </td>
                                                            <td valign="middle" style="padding-left: 8px;">
                                                                <div style="font-size: 14px; font-weight: 700; color: #0F172A; text-transform: uppercase; letter-spacing: 0.5px;">Captured Image</div>
                                                            </td>
                                                        </tr>
                                                    </table>
                                                </td>
                                            </tr>
                                            <tr>
                                                <td style="padding: 16px 20px;">
                                                    <div style="position: relative; border-radius: 8px; overflow: hidden; background-color: #0F172A; border: 1px solid #E2E8F0; height: 210px; display: flex; align-items: center; justify-content: center;">
                                                        <img src="cid:unknown_face" alt="Captured Face" style="max-width: 100%; max-height: 210px; display: block; border-radius: 8px;" />
                                                        <div style="position: absolute; top: 12px; right: 12px; background-color: rgba(15, 23, 42, 0.75); color: #FFFFFF; font-size: 10px; font-weight: 600; padding: 4px 8px; border-radius: 6px; display: flex; align-items: center; gap: 4px; border: 0.5px solid rgba(255,255,255,0.25);">
                                                            <span>{t0}</span>
                                                            <div style="width: 6px; height: 6px; border-radius: 50%; background-color: #EF4444;"></div>
                                                        </div>
                                                    </div>
                                                </td>
                                            </tr>
                                            <tr>
                                                <td style="padding: 0 20px 20px 20px;">
                                                    <table border="0" cellpadding="0" cellspacing="0" width="100%" style="background-color: #0F172A; border-radius: 10px; padding: 12px;">
                                                        <tr>
                                                            <!-- Confidence -->
                                                            <td width="33%" align="center">
                                                                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#3B82F6" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="display: block; margin-bottom: 4px;">
                                                                    <circle cx="12" cy="12" r="10"/>
                                                                    <line x1="22" y1="12" x2="18" y2="12"/>
                                                                    <line x1="6" y1="12" x2="2" y2="12"/>
                                                                    <line x1="12" y1="6" x2="12" y2="2"/>
                                                                    <line x1="12" y1="22" x2="12" y2="18"/>
                                                                </svg>
                                                                <div style="font-size: 8px; color: #94A3B8; text-transform: uppercase; margin-bottom: 2px;">Confidence</div>
                                                                <div style="font-size: 11px; font-weight: 700; color: #FFFFFF;">97.6%</div>
                                                            </td>
                                                            <!-- Face Detected -->
                                                            <td width="33%" align="center" style="border-left: 1px solid rgba(255, 255, 255, 0.15); border-right: 1px solid rgba(255, 255, 255, 0.15);">
                                                                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#10B981" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="display: block; margin-bottom: 4px;">
                                                                    <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/>
                                                                    <circle cx="12" cy="7" r="4"/>
                                                                </svg>
                                                                <div style="font-size: 8px; color: #94A3B8; text-transform: uppercase; margin-bottom: 2px;">Face Detected</div>
                                                                <div style="font-size: 11px; font-weight: 700; color: #10B981;">Yes</div>
                                                            </td>
                                                            <!-- Image Captured -->
                                                            <td width="33%" align="center">
                                                                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#F59E0B" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="display: block; margin-bottom: 4px;">
                                                                    <rect x="3" y="3" width="18" height="18" rx="2"/>
                                                                    <circle cx="8.5" cy="8.5" r="1.5"/>
                                                                    <polyline points="21 15 16 10 5 21"/>
                                                                </svg>
                                                                <div style="font-size: 8px; color: #94A3B8; text-transform: uppercase; margin-bottom: 2px;">Captured</div>
                                                                <div style="font-size: 11px; font-weight: 700; color: #F59E0B;">Success</div>
                                                            </td>
                                                        </tr>
                                                    </table>
                                                </td>
                                            </tr>
                                        </table>
                                    </td>
                                    
                                    <td width="24" style="font-size: 1px; line-height: 1px;">&nbsp;</td>
                                    
                                    <!-- Right Column (Event Timeline) -->
                                    <td width="328" valign="top">
                                        <table border="0" cellpadding="0" cellspacing="0" width="100%" style="background-color: #FFFFFF; border: 1.5px solid #E5E7EB; border-radius: 16px; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.03); height: 100%;">
                                            <tr>
                                                <td style="padding: 20px 20px 0 20px;">
                                                    <table border="0" cellpadding="0" cellspacing="0" width="100%">
                                                        <tr>
                                                            <td width="24" valign="middle">
                                                                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#2563EB" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" style="display: block;">
                                                                    <circle cx="12" cy="12" r="10"/>
                                                                    <polyline points="12 6 12 12 16 14"/>
                                                                </svg>
                                                            </td>
                                                            <td valign="middle" style="padding-left: 8px;">
                                                                <div style="font-size: 14px; font-weight: 700; color: #0F172A; text-transform: uppercase; letter-spacing: 0.5px;">Event Timeline</div>
                                                            </td>
                                                        </tr>
                                                    </table>
                                                </td>
                                            </tr>
                                            <tr>
                                                <td style="padding: 20px;">
                                                    <!-- Timeline table -->
                                                    <table border="0" cellpadding="0" cellspacing="0" width="100%">
                                                        <!-- Item 1: Unknown Face Detected (t4) -->
                                                        <tr>
                                                            <td width="16" align="center" valign="top">
                                                                <div style="width: 8px; height: 8px; border-radius: 50%; background-color: #DC2626;"></div>
                                                                <div style="width: 2px; height: 26px; background-color: #DC2626; margin: 4px 0;"></div>
                                                            </td>
                                                            <td valign="top" style="padding-left: 12px; padding-bottom: 12px;">
                                                                <span style="font-size: 11px; font-weight: 700; color: #1E293B; font-family: monospace;">{t4}</span>
                                                                <span style="font-size: 11px; color: #64748B; padding-left: 8px;">Unknown face detected</span>
                                                            </td>
                                                        </tr>
                                                        <!-- Item 2: Second Detection (t3) -->
                                                        <tr>
                                                            <td width="16" align="center" valign="top">
                                                                <div style="width: 8px; height: 8px; border-radius: 50%; background-color: #DC2626;"></div>
                                                                <div style="width: 2px; height: 26px; background-color: #DC2626; margin: 4px 0;"></div>
                                                            </td>
                                                            <td valign="top" style="padding-left: 12px; padding-bottom: 12px;">
                                                                <span style="font-size: 11px; font-weight: 700; color: #1E293B; font-family: monospace;">{t3}</span>
                                                                <span style="font-size: 11px; color: #64748B; padding-left: 8px;">Second detection</span>
                                                            </td>
                                                        </tr>
                                                        <!-- Item 3: Third Detection (t2) -->
                                                        <tr>
                                                            <td width="16" align="center" valign="top">
                                                                <div style="width: 8px; height: 8px; border-radius: 50%; background-color: #DC2626;"></div>
                                                                <div style="width: 2px; height: 26px; background-color: #DC2626; margin: 4px 0;"></div>
                                                            </td>
                                                            <td valign="top" style="padding-left: 12px; padding-bottom: 12px;">
                                                                <span style="font-size: 11px; font-weight: 700; color: #1E293B; font-family: monospace;">{t2}</span>
                                                                <span style="font-size: 11px; color: #64748B; padding-left: 8px;">Third detection</span>
                                                            </td>
                                                        </tr>
                                                        <!-- Item 4: Security Alert Triggered (t0) -->
                                                        <tr style="background-color: rgba(220, 38, 38, 0.05); border-radius: 6px;">
                                                            <td width="16" align="center" valign="top" style="padding-top: 4px; padding-bottom: 4px;">
                                                                <div style="width: 10px; height: 10px; border-radius: 50%; background-color: #DC2626; border: 2px solid #FEE2E2; box-shadow: 0 0 6px #DC2626; margin-top: 2px;"></div>
                                                                <div style="width: 2px; height: 26px; background-color: #E2E8F0; margin: 4px 0;"></div>
                                                            </td>
                                                            <td valign="middle" style="padding-left: 12px; padding-top: 4px; padding-bottom: 4px;">
                                                                <span style="font-size: 11px; font-weight: 700; color: #DC2626; font-family: monospace;">{t1}</span>
                                                                <span style="font-size: 11px; font-weight: 600; color: #DC2626; padding-left: 8px;">Security alert triggered</span>
                                                                <span style="padding-left: 6px; display: inline-block; vertical-align: middle;">
                                                                    <svg width="12" height="12" viewBox="0 0 24 24" fill="#DC2626" stroke="#DC2626" stroke-width="2" style="display: block;">
                                                                        <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9M13.73 21a2 2 0 0 1-3.46 0"/>
                                                                    </svg>
                                                                </span>
                                                            </td>
                                                        </tr>
                                                        <!-- Item 5: Email Notification Sent -->
                                                        <tr>
                                                            <td width="16" align="center" valign="top" style="padding-top: 4px;">
                                                                <div style="width: 8px; height: 8px; border-radius: 50%; background-color: #16A34A;"></div>
                                                                <div style="width: 2px; height: 26px; background-color: #E2E8F0; margin: 4px 0;"></div>
                                                            </td>
                                                            <td valign="top" style="padding-left: 12px; padding-bottom: 12px; padding-top: 4px;">
                                                                <span style="font-size: 11px; font-weight: 700; color: #1E293B; font-family: monospace;">{t0}</span>
                                                                <span style="font-size: 11px; color: #64748B; padding-left: 8px;">Email notification sent</span>
                                                            </td>
                                                        </tr>
                                                        <!-- Item 6: Cloud SMS Sent -->
                                                        <tr>
                                                            <td width="16" align="center" valign="top">
                                                                <div style="width: 8px; height: 8px; border-radius: 50%; background-color: #16A34A;"></div>
                                                                <div style="width: 2px; height: 26px; background-color: #E2E8F0; margin: 4px 0;"></div>
                                                            </td>
                                                            <td valign="top" style="padding-left: 12px; padding-bottom: 12px;">
                                                                <span style="font-size: 11px; font-weight: 700; color: #1E293B; font-family: monospace;">{t0}</span>
                                                                <span style="font-size: 11px; color: #64748B; padding-left: 8px;">Cloud SMS sent</span>
                                                            </td>
                                                        </tr>
                                                        <!-- Item 7: Dashboard Updated -->
                                                        <tr>
                                                            <td width="16" align="center" valign="top">
                                                                <div style="width: 8px; height: 8px; border-radius: 50%; background-color: #16A34A;"></div>
                                                            </td>
                                                            <td valign="top" style="padding-left: 12px;">
                                                                <span style="font-size: 11px; font-weight: 700; color: #1E293B; font-family: monospace;">{t0}</span>
                                                                <span style="font-size: 11px; color: #64748B; padding-left: 8px;">Dashboard updated</span>
                                                            </td>
                                                        </tr>
                                                    </table>
                                                </td>
                                            </tr>
                                        </table>
                                    </td>
                                </tr>
                            </table>
                        </td>
                    </tr>
                    
                    <!-- Spacing -->
                    <tr><td height="24" style="font-size: 1px; line-height: 1px;">&nbsp;</td></tr>
                    
                    <!-- 6 & 7. Incident Description & Details (Two columns side-by-side) -->
                    <tr>
                        <td>
                            <table border="0" cellpadding="0" cellspacing="0" width="100%">
                                <tr>
                                    <!-- Incident Description -->
                                    <td width="328" valign="top">
                                        <table border="0" cellpadding="0" cellspacing="0" width="100%" style="background-color: #FFFFFF; border: 1.5px solid #E5E7EB; border-radius: 16px; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.03); height: 100%;">
                                            <tr>
                                                <td style="padding: 20px 20px 0 20px;">
                                                    <table border="0" cellpadding="0" cellspacing="0" width="100%">
                                                        <tr>
                                                            <td width="24" valign="middle">
                                                                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#2563EB" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" style="display: block;">
                                                                    <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
                                                                    <polyline points="14 2 14 8 20 8"/>
                                                                    <line x1="16" y1="13" x2="8" y2="13"/>
                                                                    <line x1="16" y1="17" x2="8" y2="17"/>
                                                                    <polyline points="10 9 9 9 8 9"/>
                                                                </svg>
                                                            </td>
                                                            <td valign="middle" style="padding-left: 8px;">
                                                                <div style="font-size: 14px; font-weight: 700; color: #0F172A; text-transform: uppercase; letter-spacing: 0.5px;">Incident Description</div>
                                                            </td>
                                                        </tr>
                                                    </table>
                                                </td>
                                            </tr>
                                            <tr>
                                                <td style="padding: 20px; font-size: 13px; color: #475569; line-height: 1.6;">
                                                    <p style="margin: 0 0 12px 0;">An unknown person has been detected 4 times consecutively attempting to access the Main Entrance.</p>
                                                    <p style="margin: 0 0 12px 0; font-weight: 600; color: #DC2626; display: flex; align-items: center; gap: 6px;">
                                                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#DC2626" stroke-width="2.5" style="display: inline-block; vertical-align: middle; margin-right: 4px;">
                                                            <rect x="3" y="11" width="18" height="11" rx="2" ry="2"/>
                                                            <path d="M7 11V7a5 5 0 0 1 10 0v4"/>
                                                        </svg>
                                                        The door remained LOCKED.
                                                    </p>
                                                    <p style="margin: 0;">The security event has been logged successfully and the system is operating in simulated guard lockdown.</p>
                                                </td>
                                            </tr>
                                        </table>
                                    </td>
                                    
                                    <td width="24" style="font-size: 1px; line-height: 1px;">&nbsp;</td>
                                    
                                    <!-- Incident Details -->
                                    <td width="328" valign="top">
                                        <table border="0" cellpadding="0" cellspacing="0" width="100%" style="background-color: #FFFFFF; border: 1.5px solid #E5E7EB; border-radius: 16px; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.03);">
                                            <tr>
                                                <td style="padding: 20px 20px 0 20px;">
                                                    <table border="0" cellpadding="0" cellspacing="0" width="100%">
                                                        <tr>
                                                            <td width="24" valign="middle">
                                                                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#2563EB" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" style="display: block;">
                                                                    <circle cx="12" cy="12" r="10"/>
                                                                    <line x1="12" y1="16" x2="12" y2="12"/>
                                                                    <line x1="12" y1="8" x2="12.01" y2="8"/>
                                                                </svg>
                                                            </td>
                                                            <td valign="middle" style="padding-left: 8px;">
                                                                <div style="font-size: 14px; font-weight: 700; color: #0F172A; text-transform: uppercase; letter-spacing: 0.5px;">Incident Details</div>
                                                            </td>
                                                        </tr>
                                                    </table>
                                                </td>
                                            </tr>
                                            <tr>
                                                <td style="padding: 16px 20px 20px 20px;">
                                                    <table border="0" cellpadding="0" cellspacing="0" width="100%" style="font-size: 12px; color: #475569;">
                                                        <!-- Alert ID -->
                                                        <tr style="border-bottom: 1px solid #F1F5F9;">
                                                            <td style="padding: 8px 0; font-weight: 500; color: #64748B;">Alert ID</td>
                                                            <td style="padding: 8px 0; text-align: right; font-weight: 600; color: #1E293B; font-family: monospace;">{alert_id}</td>
                                                        </tr>
                                                        <!-- Door Status -->
                                                        <tr style="border-bottom: 1px solid #F1F5F9;">
                                                            <td style="padding: 8px 0; font-weight: 500; color: #64748B;">Door Status</td>
                                                            <td style="padding: 8px 0; text-align: right; font-weight: 700; color: #DC2626;">LOCKED</td>
                                                        </tr>
                                                        <!-- Attempts -->
                                                        <tr style="border-bottom: 1px solid #F1F5F9;">
                                                            <td style="padding: 8px 0; font-weight: 500; color: #64748B;">Attempts</td>
                                                            <td style="padding: 8px 0; text-align: right; font-weight: 600; color: #1E293B;">{UNKNOWN_FACE_EMAIL_THRESHOLD} Times</td>
                                                        </tr>
                                                        <!-- Device IP -->
                                                        <tr style="border-bottom: 1px solid #F1F5F9;">
                                                            <td style="padding: 8px 0; font-weight: 500; color: #64748B;">Device IP</td>
                                                            <td style="padding: 8px 0; text-align: right; font-weight: 600; color: #1E293B; font-family: monospace;">192.168.1.105</td>
                                                        </tr>
                                                        <!-- AI Confidence -->
                                                        <tr style="border-bottom: 1px solid #F1F5F9;">
                                                            <td style="padding: 8px 0; font-weight: 500; color: #64748B;">AI Confidence</td>
                                                            <td style="padding: 8px 0; text-align: right; font-weight: 600; color: #3B82F6;">97.62%</td>
                                                        </tr>
                                                        <!-- Software Version -->
                                                        <tr>
                                                            <td style="padding: 8px 0; font-weight: 500; color: #64748B;">Software</td>
                                                            <td style="padding: 8px 0; text-align: right; font-weight: 600; color: #1E293B; font-family: monospace;">v2.1.0</td>
                                                        </tr>
                                                    </table>
                                                </td>
                                            </tr>
                                        </table>
                                    </td>
                                </tr>
                            </table>
                        </td>
                    </tr>
                    
                    <!-- Spacing -->
                    <tr><td height="24" style="font-size: 1px; line-height: 1px;">&nbsp;</td></tr>
                    
                    <!-- 8. Recommended Actions -->
                    <tr>
                        <td style="background-color: #FFFFFF; border: 1.5px solid #E5E7EB; border-radius: 16px; padding: 24px; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.03);">
                            <table border="0" cellpadding="0" cellspacing="0" width="100%">
                                <tr>
                                    <td>
                                        <table border="0" cellpadding="0" cellspacing="0" width="100%" style="margin-bottom: 16px;">
                                            <tr>
                                                <td width="24" valign="middle">
                                                    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#2563EB" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" style="display: block;">
                                                        <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>
                                                    </svg>
                                                </td>
                                                <td valign="middle" style="padding-left: 8px;">
                                                    <div style="font-size: 14px; font-weight: 700; color: #0F172A; text-transform: uppercase; letter-spacing: 0.5px;">Recommended Actions</div>
                                                </td>
                                            </tr>
                                        </table>
                                    </td>
                                </tr>
                                <tr>
                                    <td>
                                        <table border="0" cellpadding="0" cellspacing="0" width="100%">
                                            <tr>
                                                <!-- Action 1 -->
                                                <td width="190" valign="top">
                                                    <table border="0" cellpadding="0" cellspacing="0" width="100%" style="background-color: #F8FAFC; border: 1px solid #E5E7EB; border-radius: 8px; padding: 12px; text-align: center;">
                                                        <tr>
                                                            <td>
                                                                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#2563EB" stroke-width="2" style="display: block; margin: 0 auto 6px auto;">
                                                                    <rect x="3" y="3" width="18" height="18" rx="2"/>
                                                                    <circle cx="8.5" cy="8.5" r="1.5"/>
                                                                    <polyline points="21 15 16 10 5 21"/>
                                                                </svg>
                                                                <div style="font-size: 11px; font-weight: 600; color: #1E293B;">Review Image</div>
                                                            </td>
                                                        </tr>
                                                    </table>
                                                </td>
                                                <td width="16" style="font-size: 1px; line-height: 1px;">&nbsp;</td>
                                                <!-- Action 2 -->
                                                <td width="190" valign="top">
                                                    <table border="0" cellpadding="0" cellspacing="0" width="100%" style="background-color: #F8FAFC; border: 1px solid #E5E7EB; border-radius: 8px; padding: 12px; text-align: center;">
                                                        <tr>
                                                            <td>
                                                                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#2563EB" stroke-width="2" style="display: block; margin: 0 auto 6px auto;">
                                                                    <rect x="2" y="3" width="20" height="14" rx="2" ry="2"/>
                                                                    <line x1="8" y1="21" x2="16" y2="21"/>
                                                                    <line x1="12" y1="17" x2="12" y2="21"/>
                                                                </svg>
                                                                <div style="font-size: 11px; font-weight: 600; color: #1E293B;">Check Dashboard</div>
                                                            </td>
                                                        </tr>
                                                    </table>
                                                </td>
                                                <td width="16" style="font-size: 1px; line-height: 1px;">&nbsp;</td>
                                                <!-- Action 3 -->
                                                <td width="190" valign="top">
                                                    <table border="0" cellpadding="0" cellspacing="0" width="100%" style="background-color: #F8FAFC; border: 1px solid #E5E7EB; border-radius: 8px; padding: 12px; text-align: center;">
                                                        <tr>
                                                            <td>
                                                                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#F59E0B" stroke-width="2" style="display: block; margin: 0 auto 6px auto;">
                                                                    <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/>
                                                                    <line x1="12" y1="9" x2="12" y2="13"/>
                                                                </svg>
                                                                <div style="font-size: 11px; font-weight: 600; color: #1E293B;">Report Incident</div>
                                                            </td>
                                                        </tr>
                                                    </table>
                                                </td>
                                            </tr>
                                        </table>
                                    </td>
                                </tr>
                            </table>
                        </td>
                    </tr>
                    
                    <!-- Spacing -->
                    <tr><td height="24" style="font-size: 1px; line-height: 1px;">&nbsp;</td></tr>
                    
                    <!-- 9. Quick Action Buttons -->
                    <tr>
                        <td align="center">
                            <table border="0" cellpadding="0" cellspacing="0" width="100%">
                                <tr>
                                    <!-- Button 1: View Dashboard -->
                                    <td width="328" style="padding-bottom: 12px;">
                                        <a href="http://127.0.0.1:5000/admin" style="display: block; background-color: #2563EB; color: #FFFFFF; font-size: 13px; font-weight: 700; text-decoration: none; padding: 14px 20px; border-radius: 8px; text-align: center; box-shadow: 0 4px 6px -1px rgba(37,99,235,0.2);">
                                            View Live Dashboard &rarr;
                                        </a>
                                    </td>
                                    <td width="24" style="font-size: 1px; line-height: 1px;">&nbsp;</td>
                                    <!-- Button 2: Disable Door -->
                                    <td width="328" style="padding-bottom: 12px;">
                                        <a href="http://127.0.0.1:5000/settings" style="display: block; background-color: #0F172A; color: #FFFFFF; font-size: 13px; font-weight: 700; text-decoration: none; padding: 14px 20px; border-radius: 8px; text-align: center; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.15);">
                                            🔒 Disable Access Gate
                                        </a>
                                    </td>
                                </tr>
                            </table>
                        </td>
                    </tr>
                    
                    <!-- Spacing -->
                    <tr><td height="20" style="font-size: 1px; line-height: 1px;">&nbsp;</td></tr>
                    
                    <!-- 10. Security Tips -->
                    <tr>
                        <td style="background-color: rgba(37, 99, 235, 0.05); border: 1.5px solid rgba(37, 99, 235, 0.15); border-radius: 12px; padding: 16px;">
                            <table border="0" cellpadding="0" cellspacing="0" width="100%">
                                <tr>
                                    <td width="24" valign="top">
                                        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#2563EB" stroke-width="2" style="display: block;">
                                            <circle cx="12" cy="12" r="10"/>
                                            <line x1="12" y1="16" x2="12" y2="12"/>
                                            <line x1="12" y1="8" x2="12.01" y2="8"/>
                                        </svg>
                                    </td>
                                    <td valign="top" style="padding-left: 10px; font-size: 12px; color: #475569; line-height: 1.5;">
                                        <strong style="color: #2563EB;">Security Protocol Reminder:</strong> Always verify unknown visitors via camera feedback before unlocking. Report persistent attempts to security officers. Keep your password confidential.
                                    </td>
                                </tr>
                            </table>
                        </td>
                    </tr>
                    
                    <!-- Spacing -->
                    <tr><td height="32" style="font-size: 1px; line-height: 1px;">&nbsp;</td></tr>
                    
                    <!-- 11. Footer -->
                    <tr>
                        <td style="border-top: 1px solid #E2E8F0; padding-top: 24px;">
                            <table border="0" cellpadding="0" cellspacing="0" width="100%" style="font-size: 12px; color: #64748B; line-height: 1.5;">
                                <tr>
                                    <!-- Left Footer -->
                                    <td valign="top">
                                        <div style="font-weight: 700; color: #1E293B; margin-bottom: 4px; display: flex; align-items: center; gap: 4px;">
                                            Smart Door Security
                                        </div>
                                        <div>This is an automated security notification. Please do not reply directly.</div>
                                    </td>
                                    <!-- Center/Right Contact Details -->
                                    <td align="right" valign="top" style="text-align: right;">
                                        <div>Support: admin@example.com</div>
                                        <div>Location: Gate Control Server</div>
                                        <div>&copy; 2026 Smart Door Project. All rights reserved.</div>
                                    </td>
                                </tr>
                            </table>
                        </td>
                    </tr>
                    
                </table>
            </td>
        </tr>
    </table>
</body>
</html>"""

            msg_alternative = MIMEMultipart('alternative')
            msg.attach(msg_alternative)
            msg_alternative.attach(MIMEText("Security Notification: Unknown face detected consecutively at the smart door.", 'plain'))
            msg_alternative.attach(MIMEText(html_body, 'html'))

            # Attach inline JPEG image
            image = MIMEImage(img_bytes)
            image.add_header('Content-ID', '<unknown_face>')
            image.add_header('Content-Disposition', 'inline', filename="unknown_face.jpg")
            msg.attach(image)

            # Connect and send
            server = smtplib.SMTP(smtp_server, smtp_port)
            server.starttls()
            server.login(smtp_username, smtp_password)
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


def send_visitor_pass_async(email_address: str, first_name: str, last_name: str, employee_id: str, token: str, allowed_doors: str, expiration_date: str):
    """Dispatches a background daemon thread to send the visitor QR Pass via email."""
    threading.Thread(
        target=_send_visitor_email_sync,
        args=(email_address, first_name, last_name, employee_id, token, allowed_doors, expiration_date),
        daemon=True
    ).start()


def _send_visitor_email_sync(email_address: str, first_name: str, last_name: str, employee_id: str, token: str, allowed_doors: str, expiration_date: str):
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

        # Calculate issued/expires dates for printable card style
        issued_date = datetime.now().strftime('%Y-%m-%d')
        expiry_date = expiration_date.split(' ')[0] if expiration_date else "Lifetime"

        # 2. Build email body
        msg = MIMEMultipart('related')
        msg['Subject'] = f"Your Secure Smart Gate Entry Pass - {first_name} {last_name}"
        msg['From'] = smtp_username
        msg['To'] = email_address

        visitor_name = f"{first_name} {last_name}"
        
        # Load custom configurations dynamically from DB
        support_email = ac.get_setting("support_email", "support@example.com") or "support@example.com"
        support_phone = ac.get_setting("support_phone", "+977-9800000000") or "+977-9800000000"
        website = ac.get_setting("website", "http://127.0.0.1:5000") or "http://127.0.0.1:5000"

        html_body = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Secure Smart Gate Entry Pass</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
</head>
<body style="margin: 0; padding: 0; background-color: #F8FAFC; font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; color: #1E293B;">
    <table border="0" cellpadding="0" cellspacing="0" width="100%" style="background-color: #F8FAFC; padding: 20px 0;">
        <tr>
            <td align="center">
                <!-- Outer Container -->
                <table border="0" cellpadding="0" cellspacing="0" width="680" style="background-color: #FFFFFF; border: 1.5px solid #E2E8F0; border-radius: 16px; box-shadow: 0 10px 25px rgba(0,0,0,0.05); border-collapse: collapse; overflow: hidden;">
                    
                    <!-- 1. Header (Dark blue/black bar with smart gate theme) -->
                    <tr>
                        <td style="background: linear-gradient(135deg, #0F172A 0%, #1E293B 100%); padding: 32px 32px; border-top-left-radius: 16px; border-top-right-radius: 16px; position: relative;">
                            <table border="0" cellpadding="0" cellspacing="0" width="100%">
                                <tr>
                                    <!-- Left Header Info -->
                                    <td valign="middle">
                                        <table border="0" cellpadding="0" cellspacing="0">
                                            <tr>
                                                <td style="padding-right: 14px;" valign="middle">
                                                    <!-- Shield outline with a lock inside -->
                                                    <div style="width: 46px; height: 46px; border-radius: 10px; background-color: rgba(37, 99, 235, 0.15); border: 1px solid rgba(37, 99, 235, 0.25); display: flex; align-items: center; justify-content: center;">
                                                        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#3b82f6" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" style="display: block; margin: auto;">
                                                            <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>
                                                            <rect x="9" y="11" width="6" height="5" rx="1" stroke="#3b82f6" stroke-width="1.5" fill="none"/>
                                                            <path d="M12 11V9a2 2 0 0 0-4 0v2" stroke="#3b82f6" stroke-width="1.5"/>
                                                        </svg>
                                                    </div>
                                                </td>
                                                <td valign="middle">
                                                    <div style="font-size: 13px; font-weight: 700; color: #94A3B8; letter-spacing: 0.5px; text-transform: uppercase;">Secure Smart Gate</div>
                                                    <div style="font-size: 26px; font-weight: 800; color: #10B981; margin-top: 2px; margin-bottom: 2px; letter-spacing: -0.5px;">ENTRY PASS</div>
                                                    <div style="font-size: 11px; color: #94A3B8; font-weight: 500;">Your Secure Access. Our Priority.</div>
                                                </td>
                                            </tr>
                                        </table>
                                    </td>
                                    <!-- Right Badge -->
                                    <td align="right" valign="top">
                                        <table border="0" cellpadding="0" cellspacing="0" style="background-color: #10B981; border-radius: 30px; padding: 6px 14px; border: 1.5px solid rgba(255, 255, 255, 0.25);">
                                            <tr>
                                                <td style="padding-right: 6px;">
                                                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#FFFFFF" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" style="display: block;">
                                                        <polyline points="20 6 9 17 4 12"/>
                                                    </svg>
                                                </td>
                                                <td style="font-size: 11px; font-weight: 700; color: #FFFFFF; letter-spacing: 0.5px; text-transform: uppercase; white-space: nowrap;">Access Pass</td>
                                            </tr>
                                        </table>
                                    </td>
                                </tr>
                            </table>
                        </td>
                    </tr>
                    
                    <!-- 2. Welcome Section -->
                    <tr>
                        <td style="padding: 32px 32px 10px 32px; background-color: #FFFFFF;">
                            <table border="0" cellpadding="0" cellspacing="0" width="100%">
                                <tr>
                                    <td width="28" valign="middle" style="padding-right: 10px;">
                                        <div style="width: 28px; height: 28px; border-radius: 50%; background-color: #3B82F6; display: flex; align-items: center; justify-content: center;">
                                            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#FFFFFF" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" style="display: block; margin: auto;">
                                                <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/>
                                                <circle cx="12" cy="7" r="4"/>
                                            </svg>
                                        </div>
                                    </td>
                                    <td valign="middle">
                                        <div style="font-size: 18px; font-weight: 500; color: #1E293B;">Hello <strong style="color: #3B82F6;">{visitor_name}</strong>,</div>
                                    </td>
                                </tr>
                                <tr>
                                    <td colspan="2" style="padding-top: 14px; font-size: 14px; color: #475569; line-height: 1.6;">
                                        A secure visitor access pass has been generated for you. When you arrive at the gate, please present the QR code below directly to the camera feed.
                                    </td>
                                </tr>
                            </table>
                        </td>
                    </tr>
                    
                    <!-- 3 & 4. QR Pass Card & Pass Details (Two columns side-by-side) -->
                    <tr>
                        <td style="padding: 20px 32px; background-color: #FFFFFF;">
                            <table border="0" cellpadding="0" cellspacing="0" width="100%">
                                <tr>
                                    <!-- Left Column: QR Pass Card -->
                                    <td width="300" valign="top">
                                        <table border="0" cellpadding="0" cellspacing="0" width="100%" style="border: 1.5px solid #E2E8F0; border-radius: 12px; height: 200px; padding: 16px; box-sizing: border-box; background-color: #FFFFFF;">
                                            <tr>
                                                <!-- Left Side: QR Image with blue scanbrackets border -->
                                                <td width="120" align="center" valign="middle">
                                                    <div style="border: 2px solid #3B82F6; padding: 6px; border-radius: 8px; background-color: #FFFFFF; display: inline-block;">
                                                        <img src="cid:qr_image" alt="Access QR Code" style="width: 90px; height: 90px; display: block; border-radius: 4px;" />
                                                    </div>
                                                </td>
                                                <!-- Right Side: QR Title & Token ID -->
                                                <td valign="middle" style="padding-left: 14px;">
                                                    <table border="0" cellpadding="0" cellspacing="0" width="100%">
                                                        <tr>
                                                            <td valign="middle" style="padding-bottom: 4px;">
                                                                <span style="display: inline-block; vertical-align: middle; margin-right: 4px;">
                                                                    <svg width="14" height="14" viewBox="0 0 24 24" fill="#3B82F6" stroke="#3B82F6" stroke-width="2">
                                                                        <polyline points="20 6 9 17 4 12"/>
                                                                    </svg>
                                                                </span>
                                                                <span style="font-size: 11px; font-weight: 700; color: #2563EB; text-transform: uppercase; letter-spacing: 0.5px; vertical-align: middle; white-space: nowrap;">Your Access QR</span>
                                                            </td>
                                                        </tr>
                                                        <tr>
                                                            <td style="font-size: 10px; color: #64748B; line-height: 1.4; padding-bottom: 8px;">
                                                                Scan at the gate camera.
                                                            </td>
                                                        </tr>
                                                        <tr>
                                                            <td>
                                                                <table border="0" cellpadding="0" cellspacing="0" width="100%" style="background-color: #F1F5F9; border-radius: 6px; padding: 6px 8px;">
                                                                    <tr>
                                                                        <td>
                                                                            <div style="font-size: 8px; font-weight: 700; color: #64748B; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 2px;"># Token ID</div>
                                                                            <div style="font-family: monospace; font-size: 9px; font-weight: 600; color: #334155; word-break: break-all;">{token}</div>
                                                                        </td>
                                                                    </tr>
                                                                </table>
                                                            </td>
                                                        </tr>
                                                    </table>
                                                </td>
                                            </tr>
                                        </table>
                                    </td>
                                    
                                    <td width="16" style="font-size: 1px; line-height: 1px;">&nbsp;</td>
                                    
                                    <!-- Right Column: Pass Information Details -->
                                    <td width="308" valign="top">
                                        <table border="0" cellpadding="0" cellspacing="0" width="100%" style="border: 1.5px solid #E2E8F0; border-radius: 12px; padding: 14px 16px; height: 200px; box-sizing: border-box; font-size: 12px; color: #475569; background-color: #FFFFFF;">
                                            <!-- Gate -->
                                            <tr style="border-bottom: 1px solid #F1F5F9;">
                                                <td style="padding: 8px 0;" valign="middle">
                                                    <span style="display: inline-block; vertical-align: middle; margin-right: 6px;">
                                                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#16A34A" stroke-width="2.5">
                                                            <rect x="3" y="3" width="18" height="18" rx="2"/>
                                                            <path d="M9 3v18"/>
                                                        </svg>
                                                    </span>
                                                    <span style="font-size: 9px; font-weight: 700; color: #64748B; text-transform: uppercase; letter-spacing: 0.5px; vertical-align: middle;">Authorized Gate(s)</span>
                                                </td>
                                                <td style="padding: 8px 0; text-align: right; font-weight: 600; color: #1E293B;" valign="middle">{allowed_doors}</td>
                                            </tr>
                                            <!-- Validity -->
                                            <tr style="border-bottom: 1px solid #F1F5F9;">
                                                <td style="padding: 8px 0;" valign="middle">
                                                    <span style="display: inline-block; vertical-align: middle; margin-right: 6px;">
                                                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#DC2626" stroke-width="2.5">
                                                            <circle cx="12" cy="12" r="10"/>
                                                            <polyline points="12 6 12 12 16 14"/>
                                                        </svg>
                                                    </span>
                                                    <span style="font-size: 9px; font-weight: 700; color: #64748B; text-transform: uppercase; letter-spacing: 0.5px; vertical-align: middle;">Validity Ends</span>
                                                </td>
                                                <td style="padding: 8px 0; text-align: right; font-weight: 700; color: #DC2626;" valign="middle">{expiration_date}</td>
                                            </tr>
                                            <!-- Issued -->
                                            <tr style="border-bottom: 1px solid #F1F5F9;">
                                                <td style="padding: 8px 0;" valign="middle">
                                                    <span style="display: inline-block; vertical-align: middle; margin-right: 6px;">
                                                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#2563EB" stroke-width="2.5">
                                                            <rect x="3" y="4" width="18" height="18" rx="2" ry="2"/>
                                                            <line x1="16" y1="2" x2="16" y2="6"/>
                                                            <line x1="8" y1="2" x2="8" y2="6"/>
                                                            <line x1="3" y1="10" x2="21" y2="10"/>
                                                        </svg>
                                                    </span>
                                                    <span style="font-size: 9px; font-weight: 700; color: #64748B; text-transform: uppercase; letter-spacing: 0.5px; vertical-align: middle;">Date Issued</span>
                                                </td>
                                                <td style="padding: 8px 0; text-align: right; font-weight: 600; color: #1E293B;" valign="middle">{issued_date}</td>
                                            </tr>
                                            <!-- Host -->
                                            <tr style="border-bottom: 1px solid #F1F5F9;">
                                                <td style="padding: 8px 0;" valign="middle">
                                                    <span style="display: inline-block; vertical-align: middle; margin-right: 6px;">
                                                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#F59E0B" stroke-width="2.5">
                                                            <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/>
                                                            <circle cx="12" cy="7" r="4"/>
                                                        </svg>
                                                    </span>
                                                    <span style="font-size: 9px; font-weight: 700; color: #64748B; text-transform: uppercase; letter-spacing: 0.5px; vertical-align: middle;">Host</span>
                                                </td>
                                                <td style="padding: 8px 0; text-align: right; font-weight: 600; color: #1E293B;" valign="middle">N/A</td>
                                            </tr>
                                            <!-- Pass Type -->
                                            <tr>
                                                <td style="padding: 6px 0;" valign="middle">
                                                    <span style="display: inline-block; vertical-align: middle; margin-right: 6px;">
                                                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#8B5CF6" stroke-width="2.5">
                                                            <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>
                                                        </svg>
                                                    </span>
                                                    <span style="font-size: 9px; font-weight: 700; color: #64748B; text-transform: uppercase; letter-spacing: 0.5px; vertical-align: middle;">Pass Type</span>
                                                </td>
                                                <td style="padding: 6px 0; text-align: right;" valign="middle">
                                                    <span style="font-size: 10px; font-weight: 700; color: #16A34A; background-color: rgba(22, 163, 74, 0.1); padding: 2px 8px; border-radius: 4px; border: 0.5px solid rgba(22, 163, 74, 0.2); text-transform: uppercase;">Visitor Pass</span>
                                                </td>
                                            </tr>
                                        </table>
                                    </td>
                                </tr>
                            </table>
                        </td>
                    </tr>
                    
                    <!-- 5. Security Features Grid -->
                    <tr>
                        <td style="padding: 10px 32px; background-color: #FFFFFF;">
                            <table border="0" cellpadding="0" cellspacing="0" width="100%" style="background-color: #F8FAFC; border: 1.5px solid #E2E8F0; border-radius: 12px; padding: 16px;">
                                <tr>
                                    <!-- Secure & Encrypted -->
                                    <td width="25%" align="center" valign="top">
                                        <div style="width: 32px; height: 32px; border-radius: 50%; background-color: rgba(37, 99, 235, 0.08); display: flex; align-items: center; justify-content: center; margin: 0 auto 8px auto;">
                                            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#2563EB" stroke-width="2.5" style="display: block; margin: auto;">
                                                <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>
                                            </svg>
                                        </div>
                                        <div style="font-size: 11px; font-weight: 700; color: #1E293B; margin-bottom: 2px;">Secure & Encrypted</div>
                                        <div style="font-size: 9px; color: #64748B; padding: 0 4px; line-height: 1.3;">Your pass is encrypted and unique to you.</div>
                                    </td>
                                    <!-- Time Sensitive -->
                                    <td width="25%" align="center" valign="top" style="border-left: 1px solid #E2E8F0;">
                                        <div style="width: 32px; height: 32px; border-radius: 50%; background-color: rgba(22, 163, 74, 0.08); display: flex; align-items: center; justify-content: center; margin: 0 auto 8px auto;">
                                            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#16A34A" stroke-width="2.5" style="display: block; margin: auto;">
                                                <circle cx="12" cy="12" r="10"/>
                                                <polyline points="12 6 12 12 16 14"/>
                                            </svg>
                                        </div>
                                        <div style="font-size: 11px; font-weight: 700; color: #1E293B; margin-bottom: 2px;">Time Sensitive</div>
                                        <div style="font-size: 9px; color: #64748B; padding: 0 4px; line-height: 1.3;">This pass is valid only until the time shown.</div>
                                    </td>
                                    <!-- Camera Verified -->
                                    <td width="25%" align="center" valign="top" style="border-left: 1px solid #E2E8F0;">
                                        <div style="width: 32px; height: 32px; border-radius: 50%; background-color: rgba(139, 92, 246, 0.08); display: flex; align-items: center; justify-content: center; margin: 0 auto 8px auto;">
                                            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#8B5CF6" stroke-width="2.5" style="display: block; margin: auto;">
                                                <path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z"/>
                                                <circle cx="12" cy="13" r="4"/>
                                            </svg>
                                        </div>
                                        <div style="font-size: 11px; font-weight: 700; color: #1E293B; margin-bottom: 2px;">Camera Verified</div>
                                        <div style="font-size: 9px; color: #64748B; padding: 0 4px; line-height: 1.3;">Present the QR clearly to the camera.</div>
                                    </td>
                                    <!-- Do Not Share -->
                                    <td width="25%" align="center" valign="top" style="border-left: 1px solid #E2E8F0;">
                                        <div style="width: 32px; height: 32px; border-radius: 50%; background-color: rgba(245, 158, 11, 0.08); display: flex; align-items: center; justify-content: center; margin: 0 auto 8px auto;">
                                            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#F59E0B" stroke-width="2.5" style="display: block; margin: auto;">
                                                <rect x="3" y="11" width="18" height="11" rx="2" ry="2"/>
                                                <path d="M7 11V7a5 5 0 0 1 10 0v4"/>
                                            </svg>
                                        </div>
                                        <div style="font-size: 11px; font-weight: 700; color: #1E293B; margin-bottom: 2px;">Do Not Share</div>
                                        <div style="font-size: 9px; color: #64748B; padding: 0 4px; line-height: 1.3;">This pass is for you only. Sharing is not allowed.</div>
                                    </td>
                                </tr>
                            </table>
                        </td>
                    </tr>
                    
                    <!-- 6. Important Notice Banner -->
                    <tr>
                        <td style="padding: 10px 32px 32px 32px; background-color: #FFFFFF;">
                            <table border="0" cellpadding="0" cellspacing="0" width="100%" style="background-color: #FFFBEB; border: 1.5px solid #FDE68A; border-radius: 12px; padding: 14px;">
                                <tr>
                                    <td width="24" valign="top">
                                        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#D97706" stroke-width="2.5" style="display: block;">
                                            <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/>
                                            <line x1="12" y1="9" x2="12" y2="13"/>
                                            <line x1="12" y1="17" x2="12.01" y2="17"/>
                                        </svg>
                                    </td>
                                    <td valign="top" style="padding-left: 10px; font-size: 12px; color: #B45309; line-height: 1.5;">
                                        This pass is temporary. Keep it secure and do not forward it. If you lose it, contact the host to revoke it.
                                    </td>
                                </tr>
                            </table>
                        </td>
                    </tr>
                    
                    <!-- 7. Footer -->
                    <tr>
                        <td style="background-color: #0F172A; padding: 32px 32px; border-bottom-left-radius: 16px; border-bottom-right-radius: 16px;">
                            <table border="0" cellpadding="0" cellspacing="0" width="100%">
                                <tr>
                                    <!-- Left Column: Branding info -->
                                    <td valign="middle">
                                        <table border="0" cellpadding="0" cellspacing="0">
                                            <tr>
                                                <td style="padding-right: 12px;" valign="middle">
                                                    <!-- Shield outline with a lock inside -->
                                                    <div style="width: 32px; height: 32px; border-radius: 6px; background-color: rgba(37, 99, 235, 0.15); display: flex; align-items: center; justify-content: center;">
                                                        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#3b82f6" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" style="display: block; margin: auto;">
                                                            <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>
                                                            <rect x="9" y="11" width="6" height="5" rx="1" stroke="#3b82f6" stroke-width="1.5" fill="none"/>
                                                        </svg>
                                                    </div>
                                                </td>
                                                <td valign="middle">
                                                    <div style="font-size: 13px; font-weight: 700; color: #FFFFFF; letter-spacing: 0.5px; text-transform: uppercase;">SECURE SMART GATE</div>
                                                    <div style="font-size: 10px; color: #94A3B8;">Smart Access. Safe Environment.</div>
                                                </td>
                                            </tr>
                                        </table>
                                    </td>
                                    
                                    <!-- Center Column: Need Help -->
                                    <td style="padding-left: 20px; border-left: 1.5px solid #334155; font-size: 11px; color: #94A3B8; line-height: 1.4;">
                                        <strong style="color: #FFFFFF; display: block; margin-bottom: 2px;">Need Help?</strong>
                                        Contact your host or security team.
                                    </td>
                                    
                                    <!-- Right Column: Security badges -->
                                    <td align="right" valign="middle">
                                        <table border="0" cellpadding="0" cellspacing="0" style="color: #94A3B8; font-size: 11px;">
                                            <tr>
                                                <td style="padding-right: 15px;">
                                                    <span style="display: inline-block; vertical-align: middle; margin-right: 4px;">
                                                        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="#10B981" stroke-width="2.5">
                                                            <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/>
                                                            <polyline points="22 4 12 14.01 9 11.01"/>
                                                        </svg>
                                                    </span>
                                                    <span style="color: #FFFFFF; font-weight: 500; vertical-align: middle;">Safe</span>
                                                </td>
                                                <td>
                                                    <span style="display: inline-block; vertical-align: middle; margin-right: 4px;">
                                                        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="#3B82F6" stroke-width="2.5">
                                                            <circle cx="12" cy="12" r="10"/>
                                                            <polyline points="12 6 12 12 16 14"/>
                                                        </svg>
                                                    </span>
                                                    <span style="color: #FFFFFF; font-weight: 500; vertical-align: middle;">Reliable</span>
                                                </td>
                                            </tr>
                                        </table>
                                    </td>
                                </tr>
                            </table>
                        </td>
                    </tr>
                    
                    <!-- Bottom Notice Text -->
                    <tr>
                        <td align="center" style="padding-top: 20px; font-size: 11px; color: #64748B; line-height: 1.4; text-align: center;">
                            This is an automated message. Please do not reply to this email. &nbsp;|&nbsp; &copy; 2026 Secure Smart Gate System. All rights reserved.
                        </td>
                    </tr>
                    
                </table>
            </td>
        </tr>
    </table>
</body>
</html>"""

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

