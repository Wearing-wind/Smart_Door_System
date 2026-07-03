"""
Smart Door Security System - QR Pass Repository
Handles database operations, QR token validations, reporting, and statistics.
"""

import sqlite3
import json
import logging
from datetime import datetime, date, time
from typing import Optional, List, Dict, Any, Tuple
from database.db_manager import DatabaseManager, UserRepository, AccessLogRepository

logger = logging.getLogger(__name__)

class QRRepository:
    """Repository for QR Pass database operations."""
    
    def __init__(self):
        self.db = DatabaseManager()
        self.user_repo = UserRepository()
        self.access_log_repo = AccessLogRepository()

    def add_qr_pass(self, user_id: int, qr_token: str, access_level: str = 'Normal',
                    allowed_doors: str = 'Main Entrance', access_schedule: Optional[str] = None,
                    expiration_date: Optional[str] = None) -> int:
        """Create a new QR pass linked to a user."""
        cursor = self.db.execute(
            """INSERT INTO qr_passes 
               (user_id, qr_token, status, access_level, allowed_doors, access_schedule, expiration_date)
               VALUES (?, ?, 'Active', ?, ?, ?, ?)""",
            (user_id, qr_token, access_level, allowed_doors, access_schedule, expiration_date)
        )
        self.db.commit()
        return cursor.lastrowid

    def get_qr_pass_by_id(self, pass_id: int) -> Optional[Dict[str, Any]]:
        """Retrieve QR pass by its primary key ID."""
        cursor = self.db.execute(
            """SELECT qp.*, u.first_name, u.last_name, u.employee_id, u.department, u.email
               FROM qr_passes qp
               JOIN users u ON qp.user_id = u.id
               WHERE qp.id = ?""",
            (pass_id,)
        )
        row = cursor.fetchone()
        return dict(row) if row else None

    def get_qr_pass_by_token(self, qr_token: str) -> Optional[Dict[str, Any]]:
        """Retrieve QR pass by token string."""
        cursor = self.db.execute(
            """SELECT qp.*, u.first_name, u.last_name, u.employee_id, u.department, u.email, u.is_active as user_active
               FROM qr_passes qp
               JOIN users u ON qp.user_id = u.id
               WHERE qp.qr_token = ?""",
            (qr_token,)
        )
        row = cursor.fetchone()
        return dict(row) if row else None

    def get_qr_passes_by_user(self, user_id: int) -> List[Dict[str, Any]]:
        """Get all QR passes (active/inactive) linked to a user."""
        cursor = self.db.execute(
            "SELECT * FROM qr_passes WHERE user_id = ? ORDER BY created_at DESC",
            (user_id,)
        )
        return [dict(row) for row in cursor.fetchall()]

    def get_active_qr_pass_by_user(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Get currently active QR pass for a user, if any."""
        cursor = self.db.execute(
            "SELECT * FROM qr_passes WHERE user_id = ? AND status = 'Active' LIMIT 1",
            (user_id,)
        )
        row = cursor.fetchone()
        return dict(row) if row else None

    def get_all_passes(self, limit: int = 100, offset: int = 0, search: str = "", status: str = "") -> List[Dict[str, Any]]:
        """Retrieve all QR passes with pagination, search filter, and status filter."""
        query = """SELECT qp.*, u.first_name, u.last_name, u.employee_id, u.department
                   FROM qr_passes qp
                   JOIN users u ON qp.user_id = u.id
                   WHERE 1=1"""
        params: List[Any] = []

        if status:
            query += " AND qp.status = ?"
            params.append(status)
        
        if search:
            query += """ AND (u.first_name LIKE ? OR u.last_name LIKE ? 
                         OR u.employee_id LIKE ? OR qp.qr_token LIKE ? OR u.department LIKE ?)"""
            search_param = f"%{search}%"
            params.extend([search_param, search_param, search_param, search_param, search_param])

        query += " ORDER BY qp.created_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        cursor = self.db.execute(query, tuple(params))
        return [dict(row) for row in cursor.fetchall()]

    def delete_pass(self, pass_id: int) -> bool:
        """Permanently delete a QR pass from the database."""
        self.db.execute("DELETE FROM qr_passes WHERE id = ?", (pass_id,))
        self.db.commit()
        return True

    def update_qr_pass_status(self, pass_id: int, status: str) -> bool:
        """Update the status of a QR pass (e.g. Active, Disabled, Revoked, Lost, Replaced)."""
        allowed_statuses = ['Active', 'Disabled', 'Expired', 'Revoked', 'Lost', 'Replaced']
        if status not in allowed_statuses:
            logger.error(f"Invalid status: {status}")
            return False

        self.db.execute(
            "UPDATE qr_passes SET status = ?, updated_at = ? WHERE id = ?",
            (status, datetime.now(), pass_id)
        )
        self.db.commit()
        return True

    def disable_qr_pass(self, pass_id: int) -> bool:
        """Disable a QR pass."""
        return self.update_qr_pass_status(pass_id, 'Disabled')

    def revoke_qr_pass(self, pass_id: int) -> bool:
        """Revoke a QR pass."""
        return self.update_qr_pass_status(pass_id, 'Revoked')

    def regenerate_qr_pass(self, user_id: int, new_token: str, expiration_date: Optional[str] = None) -> int:
        """Disable existing active QR pass and create a new one for the user."""
        # 1. Disable active passes
        self.db.execute(
            "UPDATE qr_passes SET status = 'Replaced', updated_at = ? WHERE user_id = ? AND status = 'Active'",
            (datetime.now(), user_id)
        )
        
        # 2. Inherit details from user to generate a new pass
        user = self.user_repo.get_by_id(user_id)
        if not user:
            raise ValueError("User does not exist")
            
        access_level = user.get('access_level', 'Normal')
        allowed_doors = user.get('allowed_doors', 'Main Entrance')
        
        # 3. Create new pass
        return self.add_qr_pass(
            user_id=user_id,
            qr_token=new_token,
            access_level=access_level,
            allowed_doors=allowed_doors,
            expiration_date=expiration_date
        )

    def validate_token(self, qr_token: str, door_name: str) -> Tuple[bool, Optional[Dict[str, Any]], str]:
        """
        Validate QR token permissions against standard system rules.
        Returns (is_valid, user_data, failure_reason).
        """
        # 1. Check if QR pass exists
        qr_pass = self.get_qr_pass_by_token(qr_token)
        if not qr_pass:
            return False, None, "Invalid QR token"

        # 2. Check QR pass status
        if qr_pass['status'] != 'Active':
            return False, None, f"QR Pass is inactive ({qr_pass['status']})"

        # 3. Check expiration
        if qr_pass['expiration_date']:
            try:
                exp = datetime.strptime(qr_pass['expiration_date'], '%Y-%m-%d %H:%M:%S')
            except ValueError:
                try:
                    exp = datetime.strptime(qr_pass['expiration_date'], '%Y-%m-%d')
                except ValueError:
                    exp = None
            
            if exp and datetime.now() > exp:
                # Update status in db
                self.update_qr_pass_status(qr_pass['id'], 'Expired')
                return False, None, "QR Pass has expired"

        # 4. Check user status
        if not qr_pass['user_active']:
            return False, None, "User account is disabled"

        # 5. Check door permissions
        allowed_doors = [d.strip() for d in (qr_pass['allowed_doors'] or '').split(',') if d.strip()]
        if door_name not in allowed_doors:
            return False, None, f"Access denied for door: {door_name}"

        # 6. Check access schedule
        if qr_pass['access_schedule']:
            try:
                schedule = json.loads(qr_pass['access_schedule'])
                now = datetime.now()
                current_day = now.weekday()  # Monday = 0, ..., Sunday = 6
                current_time = now.time()

                # Check day
                if 'days' in schedule and current_day not in schedule['days']:
                    return False, None, "Outside scheduled access days"

                # Check time window
                if 'start_time' in schedule and 'end_time' in schedule:
                    start_t = datetime.strptime(schedule['start_time'], '%H:%M').time()
                    end_t = datetime.strptime(schedule['end_time'], '%H:%M').time()
                    if not (start_t <= current_time <= end_t):
                        return False, None, "Outside scheduled access hours"
            except Exception as e:
                logger.error(f"Error parsing access schedule: {e}")
                return False, None, "System error checking schedule"

        # Retrieve full user profile
        user_profile = self.user_repo.get_by_id(qr_pass['user_id'])
        return True, user_profile, "Success"

    def log_qr_access(self, user_id: Optional[int], qr_token: str, door: str,
                      result: str, camera: str = "Front Camera", reason: Optional[str] = None,
                      ip_address: Optional[str] = None) -> int:
        """Helper to log access entries directly into access_logs."""
        return self.access_log_repo.log_access(
            user_id=user_id,
            event_type='ENTRY',
            result=result,
            face_match=False,
            failure_reason=reason if result != 'SUCCESS' else None,
            ip_address=ip_address,
            qr_token=qr_token,
            door=door,
            camera=camera,
            reason=reason
        )

    def get_dashboard_stats(self) -> Dict[str, int]:
        """Aggregate stats for dashboard widgets."""
        stats = {}
        
        # 1. Total Users
        cursor = self.db.execute("SELECT COUNT(*) FROM users")
        stats['total_users'] = cursor.fetchone()[0]

        # 2. Active QR Passes
        cursor = self.db.execute("SELECT COUNT(*) FROM qr_passes WHERE status = 'Active'")
        stats['active_passes'] = cursor.fetchone()[0]

        # 3. Today's Entries (SUCCESS result)
        cursor = self.db.execute(
            "SELECT COUNT(*) FROM access_logs WHERE access_date = date('now') AND result = 'SUCCESS'"
        )
        stats['today_entries'] = cursor.fetchone()[0]

        # 4. Today's Visitors (User type 'Visitor' that accessed today)
        cursor = self.db.execute(
            """SELECT COUNT(DISTINCT al.user_id) 
               FROM access_logs al
               JOIN users u ON al.user_id = u.id
               WHERE al.access_date = date('now') AND u.user_type = 'Visitor'"""
        )
        stats['today_visitors'] = cursor.fetchone()[0]

        # 5. Failed Attempts (DENIED or FAILED logs today)
        cursor = self.db.execute(
            "SELECT COUNT(*) FROM access_logs WHERE access_date = date('now') AND result IN ('DENIED', 'FAILED')"
        )
        stats['failed_attempts'] = cursor.fetchone()[0]

        return stats

    def get_reports_data(self, report_type: str, start_date: Optional[date] = None,
                        end_date: Optional[date] = None) -> List[Dict[str, Any]]:
        """
        Generate access reports based on filters.
        report_type: 'daily', 'weekly', 'monthly', 'user', 'door', 'failed'
        """
        query = ""
        params: List[Any] = []

        if start_date is None:
            start_date = date.today()
        if end_date is None:
            end_date = date.today()

        if report_type == 'daily':
            query = """SELECT access_date, COUNT(*) as total_attempts,
                              SUM(CASE WHEN result = 'SUCCESS' THEN 1 ELSE 0 END) as successful,
                              SUM(CASE WHEN result IN ('DENIED', 'FAILED') THEN 1 ELSE 0 END) as failed
                       FROM access_logs
                       WHERE access_date BETWEEN ? AND ?
                       GROUP BY access_date
                       ORDER BY access_date DESC"""
            params = [start_date, end_date]

        elif report_type == 'weekly':
            query = """SELECT strftime('%W', access_date) as week_num, 
                              MIN(access_date) as week_start,
                              COUNT(*) as total_attempts,
                              SUM(CASE WHEN result = 'SUCCESS' THEN 1 ELSE 0 END) as successful,
                              SUM(CASE WHEN result IN ('DENIED', 'FAILED') THEN 1 ELSE 0 END) as failed
                       FROM access_logs
                       WHERE access_date BETWEEN ? AND ?
                       GROUP BY week_num
                       ORDER BY week_num DESC"""
            params = [start_date, end_date]

        elif report_type == 'monthly':
            query = """SELECT strftime('%m-%Y', access_date) as month_year,
                              COUNT(*) as total_attempts,
                              SUM(CASE WHEN result = 'SUCCESS' THEN 1 ELSE 0 END) as successful,
                              SUM(CASE WHEN result IN ('DENIED', 'FAILED') THEN 1 ELSE 0 END) as failed
                       FROM access_logs
                       WHERE access_date BETWEEN ? AND ?
                       GROUP BY month_year
                       ORDER BY access_date DESC"""
            params = [start_date, end_date]

        elif report_type == 'user':
            query = """SELECT u.employee_id, u.first_name || ' ' || u.last_name as user_name, u.user_type,
                              COUNT(al.id) as total_attempts,
                              SUM(CASE WHEN al.result = 'SUCCESS' THEN 1 ELSE 0 END) as successful,
                              SUM(CASE WHEN al.result IN ('DENIED', 'FAILED') THEN 1 ELSE 0 END) as failed
                       FROM access_logs al
                       JOIN users u ON al.user_id = u.id
                       WHERE al.access_date BETWEEN ? AND ?
                       GROUP BY u.id
                       ORDER BY total_attempts DESC"""
            params = [start_date, end_date]

        elif report_type == 'door':
            query = """SELECT door, COUNT(*) as total_attempts,
                              SUM(CASE WHEN result = 'SUCCESS' THEN 1 ELSE 0 END) as successful,
                              SUM(CASE WHEN result IN ('DENIED', 'FAILED') THEN 1 ELSE 0 END) as failed
                       FROM access_logs
                       WHERE access_date BETWEEN ? AND ?
                       GROUP BY door
                       ORDER BY total_attempts DESC"""
            params = [start_date, end_date]

        elif report_type == 'failed':
            query = """SELECT al.access_date, al.access_time, u.employee_id, 
                              al.user_name, al.door, al.qr_token, al.failure_reason, al.reason
                       FROM access_logs al
                       LEFT JOIN users u ON al.user_id = u.id
                       WHERE al.access_date BETWEEN ? AND ? AND al.result IN ('DENIED', 'FAILED')
                       ORDER BY al.access_date DESC, al.access_time DESC"""
            params = [start_date, end_date]

        if not query:
            return []

        cursor = self.db.execute(query, tuple(params))
        return [dict(row) for row in cursor.fetchall()]
