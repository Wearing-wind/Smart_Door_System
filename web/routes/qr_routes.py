"""
Smart Door Security System - QR Routes
Flask Blueprint for handling QR Pass administration, reporting, and settings.
"""

import logging
import json
from datetime import datetime, date, timedelta
from functools import wraps
import csv
from io import StringIO

from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, session, g, Response

from config.settings import SMTP_USERNAME
from database.qr_repository import QRRepository
from database.db_manager import UserRepository, SystemLogRepository
from modules.qr_manager import QRManager
from modules.qr_generator import generate_qr_base64
from modules.access_controller import AccessController, ConfigEncryptor

logger = logging.getLogger(__name__)

# Create Blueprint
qr_bp = Blueprint('qr', __name__, template_folder='templates')
qr_repo = QRRepository()
user_repo = UserRepository()
qr_manager = QRManager()
system_log = SystemLogRepository()
access_controller = AccessController()

def login_required(f):
    """Blueprint-specific login checker to avoid circular imports."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'admin_id' not in session:
            flash('Please log in to access this page.', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function


@qr_bp.route('/admin/qr')
@login_required
def dashboard():
    """QR Module Dashboard."""
    # Get statistics
    stats = qr_repo.get_dashboard_stats()
    
    # Get recent entry logs
    recent_logs = qr_repo.access_log_repo.get_recent_logs(limit=10)
    
    # Door status mapping
    door_status = "UNKNOWN (Hardware managed by main.py)"
    
    # Retrieve system settings (SMTP, webhooks, SMS)
    email_enabled = access_controller.get_setting("email_notifications_enabled", "false") == "true"
    webhook_enabled = access_controller.get_setting("webhook_notifications_enabled", "false") == "true"
    
    return render_template(
        'qr/dashboard.html',
        stats=stats,
        recent_logs=recent_logs,
        door_state=door_status,
        email_enabled=email_enabled,
        webhook_enabled=webhook_enabled
    )


@qr_bp.route('/admin/qr/passes')
@login_required
def list_passes():
    """List and manage QR Passes."""
    search = request.args.get('search', '').strip()
    status = request.args.get('status', '').strip()
    page = int(request.args.get('page', 1))
    per_page = 20
    
    passes = qr_repo.get_all_passes(
        limit=per_page,
        offset=(page - 1) * per_page,
        search=search,
        status=status
    )
    
    return render_template(
        'qr/list.html',
        passes=passes,
        page=page,
        search=search,
        status_filter=status
    )


@qr_bp.route('/admin/qr/generate', methods=['POST'])
@login_required
def generate_pass():
    """Endpoint to generate a new QR Pass for a user."""
    try:
        user_id = int(request.form.get('user_id', 0))
        duration_days = request.form.get('duration_days')
        allowed_doors = request.form.getlist('allowed_doors')
        
        # Access Schedule JSON
        sched_days = request.form.getlist('schedule_days')
        start_time = request.form.get('start_time', '09:00').strip()
        end_time = request.form.get('end_time', '18:00').strip()
        
        schedule_json = None
        if sched_days:
            schedule_json = json.dumps({
                "days": [int(d) for d in sched_days],
                "start_time": start_time,
                "end_time": end_time
            })

        days = int(duration_days) if duration_days and duration_days.isdigit() else None
        doors_str = ",".join(allowed_doors) if allowed_doors else "Main Entrance"

        token = qr_manager.create_pass_for_user(
            user_id=user_id,
            duration_days=days,
            allowed_doors=doors_str,
            access_schedule=schedule_json
        )

        if token:
            user = user_repo.get_by_id(user_id)
            system_log.info('QRManager', f"Generated new QR Pass for: {user['first_name']} {user['last_name']}")
            flash('QR Pass generated successfully.', 'success')
        else:
            flash('Failed to generate QR Pass. Please verify user details.', 'error')
            
    except Exception as e:
        logger.error(f"Error in generate_pass: {e}")
        flash(f"Error: {str(e)}", 'error')
        
    return redirect(url_for('qr.list_passes'))


@qr_bp.route('/admin/qr/visitor/add', methods=['POST'])
@login_required
def add_visitor():
    """Register a new visitor, generate a QR Pass, and email it to them."""
    try:
        first_name = request.form.get('first_name', '').strip()
        last_name = request.form.get('last_name', '').strip()
        email = request.form.get('email', '').strip()
        phone = request.form.get('phone', '').strip()
        department = request.form.get('department', 'Visitor').strip()
        designation = request.form.get('designation', 'Guest').strip()
        
        duration_days_str = request.form.get('duration_days', '1')
        duration_days = int(duration_days_str) if duration_days_str.isdigit() else 1
        
        allowed_doors = request.form.getlist('allowed_doors')
        doors_str = ",".join(allowed_doors) if allowed_doors else "Main Entrance"
        
        # Access Schedule JSON
        sched_days = request.form.getlist('schedule_days')
        start_time = request.form.get('start_time', '09:00').strip()
        end_time = request.form.get('end_time', '18:00').strip()
        
        schedule_json = None
        if sched_days:
            schedule_json = json.dumps({
                "days": [int(d) for d in sched_days],
                "start_time": start_time,
                "end_time": end_time
            })
            
        if not first_name or not last_name or not email:
            flash('First Name, Last Name, and Email are required.', 'error')
            return redirect(url_for('qr.list_passes'))
            
        # 1. Create a unique visitor employee_id
        import random
        visitor_id_suffix = f"{datetime.now().strftime('%y%m%d')}-{random.randint(1000, 9999)}"
        employee_id = f"VIS-{visitor_id_suffix}"
        
        # 2. Expiration Date calculation
        expiration_date = datetime.now() + timedelta(days=duration_days)
        expiration_date_str = expiration_date.strftime('%Y-%m-%d %H:%M:%S')
        
        # 3. Create the user record in DB
        db = user_repo.db
        db.execute(
            """
            INSERT INTO users (
                employee_id, first_name, last_name, email, phone, department, designation, 
                user_type, access_level, allowed_doors, status, expiration_date, is_active
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                employee_id, first_name, last_name, email, phone, department, designation,
                "Visitor", "Guest", doors_str, "Active", expiration_date_str, 1
            )
        )
        db.commit()
        
        # Get the new user id
        cursor = db.execute("SELECT last_insert_rowid()")
        user_id = cursor.fetchone()[0]
        
        # 4. Generate the QR Pass
        token = qr_manager.create_pass_for_user(
            user_id=user_id,
            duration_days=duration_days,
            allowed_doors=doors_str,
            access_schedule=schedule_json
        )
        
        if token:
            system_log.info('QRManager', f"Registered Visitor {first_name} {last_name} and generated QR Pass.")
            
            # 5. Send email to the visitor asynchronously
            from modules.email_notifier import send_visitor_pass_async
            display_expiry = expiration_date.strftime('%Y-%m-%d %I:%M %p')
            send_visitor_pass_async(
                email_address=email,
                first_name=first_name,
                last_name=last_name,
                employee_id=employee_id,
                token=token,
                allowed_doors=doors_str,
                expiration_date=display_expiry
            )
            
            flash(f"Visitor registered and QR Pass has been sent to {email}.", 'success')
        else:
            # Rollback user creation if pass generation failed
            db.execute("DELETE FROM users WHERE id = ?", (user_id,))
            db.commit()
            flash('Failed to generate QR Pass for visitor.', 'error')
            
    except Exception as e:
        logger.error(f"Error in add_visitor: {e}")
        flash(f"Error registering visitor: {str(e)}", 'error')
        
    return redirect(url_for('qr.list_passes'))


@qr_bp.route('/admin/qr/toggle/<int:pass_id>', methods=['POST'])
@login_required
def toggle_pass_status(pass_id):
    """Toggle a pass status between Active and Disabled."""
    try:
        qr_pass = qr_repo.get_qr_pass_by_id(pass_id)
        if not qr_pass:
            flash('QR Pass not found.', 'error')
            return redirect(url_for('qr.list_passes'))
            
        current_status = qr_pass['status']
        new_status = 'Disabled' if current_status == 'Active' else 'Active'
        
        if qr_repo.update_qr_pass_status(pass_id, new_status):
            system_log.info('QRManager', f"QR Pass status updated: ID {pass_id} -> {new_status}")
            flash(f"QR Pass is now {new_status}.", 'success')
        else:
            flash('Failed to update QR Pass status.', 'error')
    except Exception as e:
        flash(f"Error: {str(e)}", 'error')
        
    return redirect(url_for('qr.list_passes'))


@qr_bp.route('/admin/qr/delete/<int:pass_id>', methods=['POST'])
@login_required
def delete_pass(pass_id):
    """Permanently delete a QR Pass and its associated visitor user (if applicable)."""
    try:
        qr_pass = qr_repo.get_qr_pass_by_id(pass_id)
        if not qr_pass:
            flash('QR Pass not found.', 'error')
            return redirect(url_for('qr.list_passes'))
            
        user_id = qr_pass['user_id']
        user = user_repo.get_by_id(user_id)
        
        # 1. Delete from qr_passes table
        qr_repo.delete_pass(pass_id)
        
        # 2. If the user is a Visitor, clean up their record in the users table too
        if user and user.get('user_type') == 'Visitor':
            user_repo.delete(user_id)
            
        system_log.info('QRManager', f"Permanently deleted QR Pass ID {pass_id} (User ID {user_id})")
        flash('QR Pass deleted successfully.', 'success')
    except Exception as e:
        flash(f"Error: {str(e)}", 'error')
        
    return redirect(url_for('qr.list_passes'))


@qr_bp.route('/admin/qr/regenerate/<int:user_id>', methods=['POST'])
@login_required
def regenerate_pass(user_id):
    """Revoke existing active pass and generate a brand new token for a user."""
    try:
        duration_days = request.form.get('duration_days')
        days = int(duration_days) if duration_days and duration_days.isdigit() else None
        
        from modules.qr_generator import generate_secure_token
        new_token = generate_secure_token()
        
        # Set expiration
        exp_date = None
        if days:
            exp_date = (datetime.now() + timedelta(days=days)).strftime('%Y-%m-%d %H:%M:%S')
            
        pass_id = qr_repo.regenerate_qr_pass(
            user_id=user_id,
            new_token=new_token,
            expiration_date=exp_date
        )
        
        if pass_id:
            user = user_repo.get_by_id(user_id)
            system_log.info('QRManager', f"Regenerated QR Pass for: {user['first_name']} {user['last_name']}")
            flash('QR Pass regenerated successfully.', 'success')
        else:
            flash('Failed to regenerate QR Pass.', 'error')
    except Exception as e:
        flash(f"Error: {str(e)}", 'error')
        
    return redirect(url_for('qr.list_passes'))


@qr_bp.route('/admin/qr/print/<int:pass_id>')
@login_required
def print_pass(pass_id):
    """Professional printable preview card layout."""
    qr_pass = qr_repo.get_qr_pass_by_id(pass_id)
    if not qr_pass:
        flash('QR Pass not found.', 'error')
        return redirect(url_for('qr.list_passes'))
        
    # Generate QR Base64 image
    qr_base64 = generate_qr_base64(qr_pass['qr_token'])
    
    # Schedule formatting helper
    schedule_text = "All Times"
    if qr_pass['access_schedule']:
        try:
            sched = json.loads(qr_pass['access_schedule'])
            days_map = {0:"Mon", 1:"Tue", 2:"Wed", 3:"Thu", 4:"Fri", 5:"Sat", 6:"Sun"}
            days_str = ", ".join([days_map[d] for d in sched.get('days', [])])
            schedule_text = f"{days_str} ({sched.get('start_time')} - {sched.get('end_time')})"
        except Exception:
            pass

    return render_template(
        'qr/print.html',
        card=qr_pass,
        qr_image=qr_image_url(qr_base64),
        schedule_text=schedule_text
    )


def qr_image_url(base64_str: str) -> str:
    """Pack base64 bytes into HTML inline tag URL."""
    return f"data:image/svg+xml;base64,{base64_str}"


@qr_bp.route('/admin/qr/reports')
@login_required
def reports():
    """Reports view dashboard."""
    report_type = request.args.get('type', 'daily')
    start_date_str = request.args.get('start_date')
    end_date_str = request.args.get('end_date')
    
    # Date defaults (last 30 days)
    today = date.today()
    start = today - timedelta(days=30)
    end = today
    
    if start_date_str:
        try:
            start = datetime.strptime(start_date_str, '%Y-%m-%d').date()
        except ValueError:
            pass
    if end_date_str:
        try:
            end = datetime.strptime(end_date_str, '%Y-%m-%d').date()
        except ValueError:
            pass
            
    reports_data = qr_repo.get_reports_data(report_type, start, end)
    
    return render_template(
        'qr/reports.html',
        data=reports_data,
        report_type=report_type,
        start_date=start.strftime('%Y-%m-%d'),
        end_date=end.strftime('%Y-%m-%d')
    )


@qr_bp.route('/admin/qr/reports/export')
@login_required
def export_csv():
    """Exports the filtered report as CSV file."""
    report_type = request.args.get('type', 'daily')
    start_date_str = request.args.get('start_date')
    end_date_str = request.args.get('end_date')
    
    today = date.today()
    start = today - timedelta(days=30)
    end = today
    
    if start_date_str:
        try:
            start = datetime.strptime(start_date_str, '%Y-%m-%d').date()
        except ValueError:
            pass
    if end_date_str:
        try:
            end = datetime.strptime(end_date_str, '%Y-%m-%d').date()
        except ValueError:
            pass
            
    data = qr_repo.get_reports_data(report_type, start, end)
    
    si = StringIO()
    cw = csv.writer(si)
    
    if not data:
        cw.writerow(["No logs found matching search criteria."])
    else:
        # Write headers dynamically based on reports structure
        headers = list(data[0].keys())
        cw.writerow(headers)
        for row in data:
            cw.writerow(list(row.values()))
            
    response = Response(si.getvalue(), mimetype='text/csv')
    response.headers['Content-Disposition'] = f'attachment; filename=report_{report_type}_{datetime.now().strftime("%Y%m%d")}.csv'
    return response


@qr_bp.route('/admin/qr/settings', methods=['GET', 'POST'])
@login_required
def settings():
    """Admin configuration settings for notifications and endpoints."""
    if request.method == 'POST':
        try:
            # 1. Email toggles and configurations
            email_enabled = request.form.get('email_enabled') == 'on'
            alert_recipient = request.form.get('alert_recipient_email', '').strip()
            
            # 2. Webhook toggles
            webhook_enabled = request.form.get('webhook_enabled') == 'on'
            webhook_url = request.form.get('webhook_url', '').strip()
            
            # Set settings in DB
            access_controller.set_setting("email_notifications_enabled", "true" if email_enabled else "false")
            access_controller.set_setting("alert_recipient_email", alert_recipient)
            access_controller.set_setting("webhook_notifications_enabled", "true" if webhook_enabled else "false")
            access_controller.set_setting("webhook_url", webhook_url)
            
            # Handle password / credentials updates (encrypted values)
            smtp_pass = request.form.get('smtp_password', '').strip()
            if smtp_pass:
                access_controller.set_setting("smtp_password", smtp_pass, encrypt=True)
                
            system_log.info('QRSettings', f"System notification parameters updated: {session.get('admin_username')}")
            flash('Settings updated successfully.', 'success')
            
        except Exception as e:
            flash(f"Error saving settings: {str(e)}", 'error')
            logger.error(f"Error in blueprint settings: {e}")
            
        return redirect(url_for('qr.settings'))
        
    # GET details
    email_enabled = access_controller.get_setting("email_notifications_enabled", "false") == "true"
    alert_recipient = access_controller.get_setting("alert_recipient_email", SMTP_USERNAME)
    webhook_enabled = access_controller.get_setting("webhook_notifications_enabled", "false") == "true"
    webhook_url = access_controller.get_setting("webhook_url", "")
    
    # Check if credential variables are set in DB (to display placeholders/saved indication)
    smtp_pass_exists = bool(access_controller.get_setting("smtp_password"))
    
    return render_template(
        'qr/settings.html',
        email_enabled=email_enabled,
        alert_recipient=alert_recipient,
        webhook_enabled=webhook_enabled,
        webhook_url=webhook_url,
        smtp_pass_exists=smtp_pass_exists
    )
