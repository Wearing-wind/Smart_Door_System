# SMS Notification Module for Smart Door Security System

"""
SMS Notification Service
Sends SMS alerts when unknown faces are detected at the door.
Uses Twilio SMS API for reliable message delivery.
"""

import logging
import threading
from typing import Optional, List
from datetime import datetime
from twilio.rest import Client
from twilio.base.exceptions import TwilioRestException

logger = logging.getLogger(__name__)


class SMSNotificationService:
    """
    Handles SMS notifications for unknown face detection and access events.
    Thread-safe implementation for concurrent notifications.
    """

    def __init__(
        self,
        account_sid: str,
        auth_token: str,
        from_number: str,
        enabled: bool = True,
    ):
        """
        Initialize SMS Notification Service.

        Args:
            account_sid (str): Twilio Account SID
            auth_token (str): Twilio Auth Token
            from_number (str): Sender phone number (from Twilio)
            enabled (bool): Enable/disable SMS notifications
        """
        self.enabled = enabled
        self.from_number = from_number
        self.client = None
        self.send_queue = []
        self.lock = threading.Lock()

        if self.enabled:
            try:
                self.client = Client(account_sid, auth_token)
                logger.info("SMS Notification Service initialized successfully")
            except Exception as e:
                logger.error(f"Failed to initialize Twilio client: {e}")
                self.enabled = False

    def send_unknown_face_alert(
        self, phone_number: str, face_confidence: float = None, image_path: str = None
    ) -> bool:
        """
        Send SMS alert for unknown face detection.

        Args:
            phone_number (str): Recipient phone number
            face_confidence (float): Face detection confidence score
            image_path (str): Path to captured face image

        Returns:
            bool: True if message queued/sent successfully
        """
        if not self.enabled or not self.client:
            logger.warning("SMS service not enabled or not initialized")
            return False

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        confidence_text = (
            f" (Confidence: {face_confidence:.2%})" if face_confidence else ""
        )

        message_body = (
            f"🚨 SECURITY ALERT 🚨\n"
            f"Unknown face detected at your door!\n"
            f"Time: {timestamp}{confidence_text}\n"
            f"Location: Main Entrance\n"
            f"Action: Please review the security footage.\n"
            f"Status: Door remains LOCKED"
        )

        return self._send_sms(phone_number, message_body)

    def send_access_granted_notification(
        self, phone_number: str, user_name: str, timestamp: str = None
    ) -> bool:
        """
        Send SMS notification for successful access.

        Args:
            phone_number (str): Recipient phone number
            user_name (str): Name of authorized user
            timestamp (str): Access timestamp

        Returns:
            bool: True if message queued/sent successfully
        """
        if not self.enabled or not self.client:
            return False

        timestamp = timestamp or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        message_body = (
            f"✅ ACCESS GRANTED\n"
            f"User: {user_name}\n"
            f"Time: {timestamp}\n"
            f"Status: Door unlocked successfully"
        )

        return self._send_sms(phone_number, message_body)

    def send_access_denied_notification(
        self, phone_number: str, reason: str, timestamp: str = None
    ) -> bool:
        """
        Send SMS notification for failed access attempt.

        Args:
            phone_number (str): Recipient phone number
            reason (str): Reason for denial
            timestamp (str): Attempt timestamp

        Returns:
            bool: True if message queued/sent successfully
        """
        if not self.enabled or not self.client:
            return False

        timestamp = timestamp or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        message_body = (
            f"❌ ACCESS DENIED\n"
            f"Reason: {reason}\n"
            f"Time: {timestamp}\n"
            f"Status: Door remains LOCKED"
        )

        return self._send_sms(phone_number, message_body)

    def send_system_alert(
        self, phone_number: str, alert_type: str, details: str
    ) -> bool:
        """
        Send SMS for system alerts (errors, malfunction, etc).

        Args:
            phone_number (str): Recipient phone number
            alert_type (str): Type of alert (e.g., 'CAMERA_ERROR', 'LOCK_FAILURE')
            details (str): Alert details

        Returns:
            bool: True if message queued/sent successfully
        """
        if not self.enabled or not self.client:
            return False

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        message_body = (
            f"⚠️ SYSTEM ALERT ⚠️\n"
            f"Type: {alert_type}\n"
            f"Details: {details}\n"
            f"Time: {timestamp}\n"
            f"Action: Check system logs immediately"
        )

        return self._send_sms(phone_number, message_body)

    def _send_sms(self, phone_number: str, message_body: str) -> bool:
        """
        Internal method to send SMS via Twilio API.

        Args:
            phone_number (str): Recipient phone number
            message_body (str): Message content

        Returns:
            bool: True if sent successfully
        """
        if not self.client:
            logger.error("Twilio client not initialized")
            return False

        try:
            # Validate phone number format
            if not self._validate_phone_number(phone_number):
                logger.error(f"Invalid phone number format: {phone_number}")
                return False

            # Send message asynchronously
            threading.Thread(
                target=self._send_async, args=(phone_number, message_body)
            ).start()

            logger.info(f"SMS queued for {phone_number}")
            return True

        except Exception as e:
            logger.error(f"Error queuing SMS: {e}")
            return False

    def _send_async(self, phone_number: str, message_body: str):
        """
        Send SMS asynchronously to avoid blocking main thread.

        Args:
            phone_number (str): Recipient phone number
            message_body (str): Message content
        """
        try:
            with self.lock:
                message = self.client.messages.create(
                    body=message_body, from_=self.from_number, to=phone_number
                )

            logger.info(
                f"SMS sent successfully to {phone_number} (SID: {message.sid})"
            )

        except TwilioRestException as e:
            logger.error(f"Twilio API error sending SMS: {e}")
        except Exception as e:
            logger.error(f"Unexpected error sending SMS: {e}")

    @staticmethod
    def _validate_phone_number(phone_number: str) -> bool:
        """
        Validate phone number format.

        Args:
            phone_number (str): Phone number to validate

        Returns:
            bool: True if valid format
        """
        # Remove common formatting characters
        clean_number = phone_number.replace("+", "").replace("-", "").replace(" ", "")

        # Check if it's numeric and reasonable length (10-15 digits)
        return clean_number.isdigit() and 10 <= len(clean_number) <= 15

    def send_bulk_alert(self, phone_numbers: List[str], message_body: str) -> int:
        """
        Send bulk SMS to multiple recipients.

        Args:
            phone_numbers (List[str]): List of recipient phone numbers
            message_body (str): Message content

        Returns:
            int: Number of successfully queued messages
        """
        success_count = 0

        for phone_number in phone_numbers:
            if self._send_sms(phone_number, message_body):
                success_count += 1

        logger.info(
            f"Bulk SMS sent to {success_count}/{len(phone_numbers)} recipients"
        )
        return success_count

    def get_sms_status(self, message_sid: str) -> Optional[dict]:
        """
        Check the delivery status of a sent message.

        Args:
            message_sid (str): Twilio Message SID

        Returns:
            dict: Message status information or None if error
        """
        if not self.client:
            return None

        try:
            message = self.client.messages(message_sid).fetch()
            return {
                "sid": message.sid,
                "status": message.status,
                "to": message.to,
                "sent_at": message.date_sent,
                "error_code": message.error_code,
                "error_message": message.error_message,
            }
        except TwilioRestException as e:
            logger.error(f"Error fetching SMS status: {e}")
            return None


class SMSContactManager:
    """
    Manages SMS contact list for alerts.
    Stores and manages authorized phone numbers for notifications.
    """

    def __init__(self):
        """Initialize contact manager."""
        self.contacts = {}  # {user_id: phone_number}
        self.emergency_contacts = []
        self.lock = threading.Lock()

    def add_contact(self, user_id: str, phone_number: str):
        """
        Add a contact for notifications.

        Args:
            user_id (str): User identifier
            phone_number (str): Phone number to notify
        """
        with self.lock:
            if SMSNotificationService._validate_phone_number(phone_number):
                self.contacts[user_id] = phone_number
                logger.info(f"Contact added: {user_id} -> {phone_number}")
            else:
                logger.warning(f"Invalid phone number rejected: {phone_number}")

    def remove_contact(self, user_id: str):
        """
        Remove a contact from notifications.

        Args:
            user_id (str): User identifier
        """
        with self.lock:
            if user_id in self.contacts:
                del self.contacts[user_id]
                logger.info(f"Contact removed: {user_id}")

    def add_emergency_contact(self, phone_number: str):
        """
        Add emergency contact (always receives alerts).

        Args:
            phone_number (str): Emergency contact phone number
        """
        with self.lock:
            if SMSNotificationService._validate_phone_number(phone_number):
                if phone_number not in self.emergency_contacts:
                    self.emergency_contacts.append(phone_number)
                    logger.info(f"Emergency contact added: {phone_number}")

    def remove_emergency_contact(self, phone_number: str):
        """
        Remove emergency contact.

        Args:
            phone_number (str): Emergency contact phone number
        """
        with self.lock:
            if phone_number in self.emergency_contacts:
                self.emergency_contacts.remove(phone_number)
                logger.info(f"Emergency contact removed: {phone_number}")

    def get_all_contacts(self) -> List[str]:
        """
        Get all unique phone numbers for alerts.

        Returns:
            List[str]: List of all phone numbers
        """
        with self.lock:
            all_numbers = list(set(self.contacts.values()))
            all_numbers.extend(self.emergency_contacts)
            return list(set(all_numbers))

    def get_contact_for_user(self, user_id: str) -> Optional[str]:
        """
        Get phone number for specific user.

        Args:
            user_id (str): User identifier

        Returns:
            str: Phone number or None
        """
        with self.lock:
            return self.contacts.get(user_id)

    def is_empty(self) -> bool:
        """
        Check if any contacts are registered.

        Returns:
            bool: True if no contacts
        """
        with self.lock:
            return len(self.contacts) == 0 and len(self.emergency_contacts) == 0
