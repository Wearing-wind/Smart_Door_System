"""
Smart Door Security System - QR Pass Manager
Handles the high-level logic for creating, replacing, and managing QR Passes.
"""

import logging
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
from database.qr_repository import QRRepository
from modules.qr_generator import generate_secure_token

logger = logging.getLogger(__name__)

class QRManager:
    """Manager class for administrating QR passes."""
    
    def __init__(self):
        self.qr_repo = QRRepository()

    def create_pass_for_user(self, user_id: int, duration_days: Optional[int] = None,
                             allowed_doors: Optional[str] = None,
                             access_schedule: Optional[str] = None) -> Optional[str]:
        """
        Generate a secure QR pass for a user.
        
        Args:
            user_id: ID of the user.
            duration_days: Optional validity period in days.
            allowed_doors: Comma-separated list of allowed doors. Inherited from user if None.
            access_schedule: JSON schedule string.
            
        Returns:
            The generated QR token string if successful, None otherwise.
        """
        try:
            # 1. Fetch user to check access level & details
            user = self.qr_repo.user_repo.get_by_id(user_id)
            if not user:
                logger.error(f"User with ID {user_id} not found.")
                return None

            # 2. Establish defaults from user profile
            doors = allowed_doors if allowed_doors is not None else user.get('allowed_doors', 'Main Entrance')
            access_level = user.get('access_level', 'Normal')

            # 3. Calculate expiration date
            expiration_date = None
            if duration_days:
                expiration_date = (datetime.now() + timedelta(days=duration_days)).strftime('%Y-%m-%d %H:%M:%S')

            # 4. Deactivate any existing active passes for this user
            active_pass = self.qr_repo.get_active_qr_pass_by_user(user_id)
            if active_pass:
                self.qr_repo.update_qr_pass_status(active_pass['id'], 'Replaced')

            # 5. Generate secure token
            token = generate_secure_token()

            # 6. Save in database
            self.qr_repo.add_qr_pass(
                user_id=user_id,
                qr_token=token,
                access_level=access_level,
                allowed_doors=doors,
                access_schedule=access_schedule,
                expiration_date=expiration_date
            )
            
            logger.info(f"Generated QR pass for user {user['employee_id']} ({user['first_name']} {user['last_name']})")
            return token

        except Exception as e:
            logger.error(f"Error creating QR pass: {e}")
            return None

    def deactivate_user_passes(self, user_id: int) -> bool:
        """Revoke all active passes for a given user."""
        try:
            passes = self.qr_repo.get_qr_passes_by_user(user_id)
            for p in passes:
                if p['status'] == 'Active':
                    self.qr_repo.update_qr_pass_status(p['id'], 'Revoked')
            return True
        except Exception as e:
            logger.error(f"Failed to deactivate passes for user {user_id}: {e}")
            return False

    def disable_pass(self, pass_id: int) -> bool:
        """Mark a QR pass as Disabled."""
        return self.qr_repo.disable_qr_pass(pass_id)

    def revoke_pass(self, pass_id: int) -> bool:
        """Mark a QR pass as Revoked."""
        return self.qr_repo.revoke_qr_pass(pass_id)

    def mark_pass_lost(self, pass_id: int) -> bool:
        """Mark a QR pass as Lost."""
        return self.qr_repo.update_qr_pass_status(pass_id, 'Lost')

    def replace_pass(self, pass_id: int, new_expiration_days: Optional[int] = None) -> Optional[str]:
        """
        Mark an old pass as Replaced and generate a new QR pass.
        
        Args:
            pass_id: ID of the old pass to be replaced.
            new_expiration_days: Validity of the new pass in days.
            
        Returns:
            The new QR token string.
        """
        try:
            old_pass = self.qr_repo.get_qr_pass_by_id(pass_id)
            if not old_pass:
                logger.error(f"Pass with ID {pass_id} not found.")
                return None

            # Mark old pass as Replaced
            self.qr_repo.update_qr_pass_status(pass_id, 'Replaced')

            # Calculate expiration date
            exp_date = None
            if new_expiration_days:
                exp_date = (datetime.now() + timedelta(days=new_expiration_days)).strftime('%Y-%m-%d %H:%M:%S')

            # Generate new token
            new_token = generate_secure_token()

            # Insert new pass
            self.qr_repo.add_qr_pass(
                user_id=old_pass['user_id'],
                qr_token=new_token,
                access_level=old_pass['access_level'],
                allowed_doors=old_pass['allowed_doors'],
                access_schedule=old_pass['access_schedule'],
                expiration_date=exp_date
            )
            
            logger.info(f"Replaced pass {pass_id} for user {old_pass['employee_id']}. New token: {new_token}")
            return new_token
        except Exception as e:
            logger.error(f"Failed to replace pass: {e}")
            return None
