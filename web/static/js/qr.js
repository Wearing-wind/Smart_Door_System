/**
 * Smart Door Security System - QR JavaScript Actions
 */

document.addEventListener('DOMContentLoaded', () => {
    // 1. Log Polling for Dashboard
    const dashboardLogsTable = document.getElementById('dashboard-recent-logs');
    if (dashboardLogsTable) {
        setInterval(async () => {
            try {
                const response = await fetch('/api/logs?limit=10');
                if (response.ok) {
                    const data = await response.json();
                    updateDashboardLogsTable(data.logs);
                }
            } catch (err) {
                console.error("Failed to poll recent logs:", err);
            }
        }, 3000); // Poll every 3 seconds
    }

    // 2. Realtime Widgets Polling
    const widgetTotalUsers = document.getElementById('widget-total-users');
    if (widgetTotalUsers) {
        setInterval(async () => {
            try {
                // Fetch stats directly
                const response = await fetch('/api/logs/stats');
                if (response.ok) {
                    const data = await response.json();
                    // We can also poll a custom endpoint or just update local values
                }
            } catch (err) {
                console.eror(err);
            }
        }, 5000);
    }

    // 3. Dynamic Schedule Toggle in Forms
    const forms = document.querySelectorAll('form');
    forms.forEach(form => {
        const checkboxes = form.querySelectorAll('.schedule-day-check');
        const timeRow = form.querySelector('[id^="schedule-time-row"]');
        if (checkboxes.length > 0 && timeRow) {
            const toggleTimeInputs = () => {
                let anyChecked = false;
                checkboxes.forEach(cb => {
                    if (cb.checked) anyChecked = true;
                });
                
                if (anyChecked) {
                    timeRow.style.display = 'flex';
                    timeRow.querySelectorAll('input').forEach(input => input.required = true);
                } else {
                    timeRow.style.display = 'none';
                    timeRow.querySelectorAll('input').forEach(input => {
                        input.required = false;
                        input.value = '';
                    });
                }
            };

            checkboxes.forEach(cb => cb.addEventListener('change', toggleTimeInputs));
            toggleTimeInputs(); // Initial call
        }
    });
});

/**
 * Updates the dashboard logs table with fresh rows.
 */
function updateDashboardLogsTable(logs) {
    const tbody = document.querySelector('#dashboard-recent-logs tbody');
    if (!tbody) return;

    if (!logs || logs.length === 0) {
        tbody.innerHTML = '<tr><td colspan="5" class="text-center text-muted">No recent activity</td></tr>';
        return;
    }

    let html = '';
    logs.forEach(log => {
        const badgeClass = log.result === 'SUCCESS' ? 'success' : (log.result === 'DENIED' ? 'danger' : 'warning');
        const userDisplay = log.user_name ? `${log.user_name} (${log.employee_id || 'N/A'})` : 'Unknown Attempt';
        const doorDisplay = log.door || 'Main Entrance';
        const reasonDisplay = log.failure_reason || log.reason || '-';
        
        html += `
            <tr>
                <td>${log.access_date} ${log.access_time}</td>
                <td><strong>${userDisplay}</strong></td>
                <td>${doorDisplay}</td>
                <td><span class="badge badge-${badgeClass}">${log.result}</span></td>
                <td>${reasonDisplay}</td>
            </tr>
        `;
    });
    tbody.innerHTML = html;
}

/**
 * Show a toast notification dynamically.
 */
function showToast(message, type = 'success') {
    const container = document.querySelector('.flash-messages');
    if (!container) {
        const main = document.querySelector('main');
        const newContainer = document.createElement('div');
        newContainer.className = 'flash-messages';
        main.insertBefore(newContainer, main.firstChild);
    }
    
    const flashMessages = document.querySelector('.flash-messages');
    const toast = document.createElement('div');
    toast.className = `flash-message flash-${type}`;
    
    let icon = 'fa-info-circle';
    if (type === 'success') icon = 'fa-check-circle';
    else if (type === 'error') icon = 'fa-exclamation-circle';
    else if (type === 'warning') icon = 'fa-exclamation-triangle';
    
    toast.innerHTML = `
        <i class="fas ${icon}"></i>
        <span>${message}</span>
        <button class="close-btn" onclick="this.parentElement.remove()">
            <i class="fas fa-times"></i>
        </button>
    `;
    
    flashMessages.appendChild(toast);
    
    // Auto remove after 5 seconds
    setTimeout(() => {
        toast.style.opacity = '0';
        toast.style.transition = 'opacity 0.5s';
        setTimeout(() => toast.remove(), 500);
    }, 5000);
}
