// KRA HELMET Dashboard JavaScript

const API_BASE = window.location.origin;

// Initialize dashboard
document.addEventListener('DOMContentLoaded', function() {
    loadDashboard();
    setupEventListeners();
});

// Load dashboard data
async function loadDashboard() {
    try {
        await Promise.all([
            loadStats(),
            loadSMEs(),
            loadActivity(),
            loadProactiveRecommendations(),
            checkSystemStatus()
        ]);
    } catch (error) {
        console.error('Error loading dashboard:', error);
        showNotification('Error loading dashboard data', 'error');
    }
}

// Load statistics
async function loadStats() {
    try {
        const response = await fetch(`${API_BASE}/api/stats`);
        const data = await response.json();

        document.getElementById('totalSMEs').textContent = data.total_smes || 0;
        document.getElementById('compliantSMEs').textContent = data.compliant_smes || 0;
        document.getElementById('atRiskSMEs').textContent = data.at_risk_smes || 0;
        document.getElementById('nonCompliantSMEs').textContent = data.non_compliant_smes || 0;
    } catch (error) {
        console.error('Error loading stats:', error);
    }
}

// Load SMEs
async function loadSMEs() {
    try {
        const response = await fetch(`${API_BASE}/api/smes`);
        const data = await response.json();

        const smeList = document.getElementById('smeList');
        smeList.innerHTML = '';

        if (data.smes && data.smes.length > 0) {
            data.smes.forEach(sme => {
                const smeItem = createSMEItem(sme);
                smeList.appendChild(smeItem);
            });
        } else {
            smeList.innerHTML = '<p class="no-data">No SMEs found. Add your first SME to get started.</p>';
        }
    } catch (error) {
        console.error('Error loading SMEs:', error);
    }
}

// Create SME item element
function createSMEItem(sme) {
    const div = document.createElement('div');
    div.className = 'sme-item';

    const statusClass = getStatusClass(sme.compliance_status);
    const statusText = getStatusText(sme.compliance_status);

    div.innerHTML = `
        <div class="sme-info">
            <h3>${sme.name || 'Unknown'}</h3>
            <p>PIN: ${sme.pin} | ${sme.business_name || 'No business name'}</p>
        </div>
        <span class="sme-status ${statusClass}">${statusText}</span>
    `;

    div.onclick = () => viewSMEDetails(sme.pin);
    return div;
}

// Get status class
function getStatusClass(status) {
    switch (status) {
        case 'compliant': return 'status-compliant';
        case 'at_risk': return 'status-at-risk';
        case 'non_compliant': return 'status-non-compliant';
        default: return 'status-at-risk';
    }
}

// Get status text
function getStatusText(status) {
    switch (status) {
        case 'compliant': return 'Compliant';
        case 'at_risk': return 'At Risk';
        case 'non_compliant': return 'Non-Compliant';
        default: return 'Unknown';
    }
}

// Load activity
async function loadActivity() {
    try {
        const response = await fetch(`${API_BASE}/api/activity`);
        const data = await response.json();

        const activityList = document.getElementById('activityList');
        activityList.innerHTML = '';

        if (data.activities && data.activities.length > 0) {
            data.activities.forEach(activity => {
                const activityItem = createActivityItem(activity);
                activityList.appendChild(activityItem);
            });
        } else {
            activityList.innerHTML = '<p class="no-data">No recent activity.</p>';
        }
    } catch (error) {
        console.error('Error loading activity:', error);
    }
}

// Load proactive recommendations
async function loadProactiveRecommendations() {
    try {
        const response = await fetch(`${API_BASE}/api/proactive`);
        const data = await response.json();

        const proactiveList = document.getElementById('proactiveList');
        proactiveList.innerHTML = '';

        if (data.recommendations && data.recommendations.length > 0) {
            data.recommendations.forEach(rec => {
                const recItem = createProactiveItem(rec);
                proactiveList.appendChild(recItem);
            });
        } else {
            proactiveList.innerHTML = '<p class="no-data">No proactive recommendations at this time.</p>';
        }
    } catch (error) {
        console.error('Error loading proactive recommendations:', error);
    }
}

// Create proactive recommendation item
function createProactiveItem(rec) {
    const div = document.createElement('div');
    div.className = 'proactive-item';

    const urgencyClass = `urgency-${rec.urgency || 'green'}`;
    const autoIcon = rec.autonomous ? '🤖' : '👤';

    div.innerHTML = `
        <div class="proactive-header">
            <span class="proactive-icon">${autoIcon}</span>
            <span class="proactive-title">${rec.title}</span>
            <span class="proactive-urgency ${urgencyClass}">${rec.urgency || 'green'}</span>
        </div>
        <div class="proactive-detail">${rec.detail}</div>
        <div class="proactive-reasoning">Reasoning: ${rec.reasoning || 'N/A'}</div>
    `;

    return div;
}

// Create activity item element
function createActivityItem(activity) {
    const div = document.createElement('div');
    div.className = 'activity-item';

    const time = new Date(activity.timestamp).toLocaleString();

    div.innerHTML = `
        <div class="activity-time">${time}</div>
        <div class="activity-text">${activity.description}</div>
    `;

    return div;
}

// Check system status
async function checkSystemStatus() {
    try {
        const response = await fetch(`${API_BASE}/health`);
        const data = await response.json();

        updateStatusIndicator('apiStatus', data.status === 'healthy');
        updateStatusIndicator('dbStatus', data.database === 'connected');
        updateStatusIndicator('schedulerStatus', data.scheduler === 'running');
        updateStatusIndicator('monitoringStatus', data.monitoring === 'active');
    } catch (error) {
        console.error('Error checking system status:', error);
        updateStatusIndicator('apiStatus', false);
        updateStatusIndicator('dbStatus', false);
        updateStatusIndicator('schedulerStatus', false);
        updateStatusIndicator('monitoringStatus', false);
    }
}

// Update status indicator
function updateStatusIndicator(elementId, isOnline) {
    const element = document.getElementById(elementId);
    if (element) {
        element.className = `status-indicator ${isOnline ? 'online' : 'offline'}`;
    }
}

// Setup event listeners
function setupEventListeners() {
    // Refresh button
    document.getElementById('refreshBtn').onclick = loadDashboard;

    // Settings button
    document.getElementById('settingsBtn').onclick = showSettings;

    // Add SME button
    document.getElementById('addSMEBtn').onclick = showAddSMEModal;

    // Search input
    document.getElementById('searchSME').oninput = filterSMEs;

    // Form submission
    document.getElementById('addSMEForm').onsubmit = addSME;
}

// Show add SME modal
function showAddSMEModal() {
    document.getElementById('addSMEModal').style.display = 'block';
}

// Close modal
function closeModal() {
    document.getElementById('addSMEModal').style.display = 'none';
    document.getElementById('addSMEForm').reset();
}

// Add SME
async function addSME(event) {
    event.preventDefault();

    const formData = new FormData(event.target);
    const smeData = {
        pin: formData.get('pin'),
        name: formData.get('name'),
        business_name: formData.get('businessName'),
        phone: formData.get('phone'),
        email: formData.get('email')
    };

    try {
        const response = await fetch(`${API_BASE}/api/smes`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(smeData)
        });

        if (response.ok) {
            showNotification('SME added successfully', 'success');
            closeModal();
            loadSMEs();
            loadStats();
        } else {
            const error = await response.json();
            showNotification(error.detail || 'Error adding SME', 'error');
        }
    } catch (error) {
        console.error('Error adding SME:', error);
        showNotification('Error adding SME', 'error');
    }
}

// Filter SMEs
function filterSMEs() {
    const searchTerm = document.getElementById('searchSME').value.toLowerCase();
    const smeItems = document.querySelectorAll('.sme-item');

    smeItems.forEach(item => {
        const text = item.textContent.toLowerCase();
        item.style.display = text.includes(searchTerm) ? 'flex' : 'none';
    });
}

// View SME details
function viewSMEDetails(pin) {
    window.open(`${API_BASE}/api/smes/${pin}`, '_blank');
}

// Run compliance check
async function runComplianceCheck() {
    try {
        showNotification('Running compliance check...', 'info');
        const response = await fetch(`${API_BASE}/api/check`, {
            method: 'POST'
        });

        if (response.ok) {
            showNotification('Compliance check completed', 'success');
            loadDashboard();
        } else {
            showNotification('Error running compliance check', 'error');
        }
    } catch (error) {
        console.error('Error running compliance check:', error);
        showNotification('Error running compliance check', 'error');
    }
}

// View reports
function viewReports() {
    window.open(`${API_BASE}/api/reports`, '_blank');
}

// Check monitoring
async function checkMonitoring() {
    try {
        showNotification('Checking monitoring...', 'info');
        const response = await fetch(`${API_BASE}/api/monitoring/status`);

        if (response.ok) {
            const data = await response.json();
            showNotification(`Monitoring status: ${data.status}`, 'success');
        } else {
            showNotification('Error checking monitoring', 'error');
        }
    } catch (error) {
        console.error('Error checking monitoring:', error);
        showNotification('Error checking monitoring', 'error');
    }
}

// View audit trail
function viewAuditTrail() {
    window.open(`${API_BASE}/api/audit`, '_blank');
}

// Show settings
function showSettings() {
    showNotification('Settings feature coming soon', 'info');
}

// Show notification
function showNotification(message, type) {
    // Create notification element
    const notification = document.createElement('div');
    notification.className = `notification notification-${type}`;
    notification.textContent = message;

    // Style the notification
    notification.style.cssText = `
        position: fixed;
        top: 20px;
        right: 20px;
        padding: 1rem 1.5rem;
        border-radius: 5px;
        color: white;
        font-weight: bold;
        z-index: 10000;
        animation: slideIn 0.3s ease;
    `;

    // Set background color based on type
    switch (type) {
        case 'success':
            notification.style.backgroundColor = '#4CAF50';
            break;
        case 'error':
            notification.style.backgroundColor = '#f44336';
            break;
        case 'info':
            notification.style.backgroundColor = '#2196F3';
            break;
        default:
            notification.style.backgroundColor = '#9e9e9e';
    }

    // Add to page
    document.body.appendChild(notification);

    // Remove after 3 seconds
    setTimeout(() => {
        notification.remove();
    }, 3000);
}
