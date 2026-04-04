// KRA Deadline Tracker Dashboard — v4

const API_BASE = window.location.origin;
const _startTime = Date.now();

// ── Initialization ────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
    initSidebar();
    initNavigation();
    setupEventListeners();
    setCurrentDate();
    loadDashboard();
    startUptimeTimer();
});

// ── Sidebar ───────────────────────────────────────────────────
function initSidebar() {
    const toggle = document.getElementById('sidebarToggle');
    const sidebar = document.getElementById('sidebar');
    const overlay = document.getElementById('sidebarOverlay');

    toggle.addEventListener('click', () => {
        sidebar.classList.toggle('open');
        overlay.classList.toggle('visible');
    });

    overlay.addEventListener('click', () => {
        sidebar.classList.remove('open');
        overlay.classList.remove('visible');
    });
}

// ── Navigation ────────────────────────────────────────────────
function initNavigation() {
    document.querySelectorAll('[data-section]').forEach(el => {
        el.addEventListener('click', (e) => {
            e.preventDefault();
            const section = el.dataset.section;
            navigateTo(section);
        });
    });
}

function navigateTo(sectionId) {
    // Update nav active state
    document.querySelectorAll('.nav-item').forEach(item => item.classList.remove('active'));
    const activeNav = document.querySelector(`.nav-item[data-section="${sectionId}"]`);
    if (activeNav) activeNav.classList.add('active');

    // Show correct section
    document.querySelectorAll('.page-section').forEach(s => s.classList.remove('active'));
    const target = document.getElementById(`section-${sectionId}`);
    if (target) target.classList.add('active');

    // Update page title
    const titles = {
        overview: 'Overview',
        smes: 'SME Management',
        activity: 'Activity Log',
        recommendations: 'Recommendations',
        system: 'System Status'
    };
    document.getElementById('pageTitle').textContent = titles[sectionId] || 'Dashboard';

    // Close mobile sidebar
    document.getElementById('sidebar').classList.remove('open');
    document.getElementById('sidebarOverlay').classList.remove('visible');
}

function setCurrentDate() {
    const now = new Date();
    const options = { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' };
    document.getElementById('currentDate').textContent = now.toLocaleDateString('en-KE', options);
}

// ── Event Listeners ───────────────────────────────────────────
function setupEventListeners() {
    document.getElementById('refreshBtn').addEventListener('click', () => {
        const btn = document.getElementById('refreshBtn');
        btn.classList.add('spinning');
        loadDashboard().finally(() => {
            setTimeout(() => btn.classList.remove('spinning'), 300);
        });
    });

    document.getElementById('addSMEBtn').addEventListener('click', showAddSMEModal);
    document.getElementById('searchSME').addEventListener('input', filterSMEs);
    document.getElementById('addSMEForm').addEventListener('submit', addSME);
}

// ── Data Loading ──────────────────────────────────────────────
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

// ── Stats ─────────────────────────────────────────────────────
async function loadStats() {
    try {
        const response = await fetch(`${API_BASE}/api/stats`);
        const data = await response.json();

        animateValue('totalSMEs', data.total_smes || 0);
        animateValue('compliantSMEs', data.compliant_smes || 0);
        animateValue('atRiskSMEs', data.at_risk_smes || 0);
        animateValue('nonCompliantSMEs', data.non_compliant_smes || 0);
    } catch (error) {
        console.error('Error loading stats:', error);
    }
}

function animateValue(elementId, target) {
    const el = document.getElementById(elementId);
    if (!el) return;
    const current = parseInt(el.textContent) || 0;
    if (current === target) return;

    const duration = 400;
    const start = performance.now();

    function step(timestamp) {
        const progress = Math.min((timestamp - start) / duration, 1);
        const eased = 1 - Math.pow(1 - progress, 3); // ease-out cubic
        el.textContent = Math.round(current + (target - current) * eased);
        if (progress < 1) requestAnimationFrame(step);
    }
    requestAnimationFrame(step);
}

// ── SMEs ──────────────────────────────────────────────────────
async function loadSMEs() {
    try {
        const response = await fetch(`${API_BASE}/api/smes`);
        const data = await response.json();

        const smeList = document.getElementById('smeList');

        if (data.smes && data.smes.length > 0) {
            smeList.innerHTML = '';
            data.smes.forEach(sme => {
                smeList.appendChild(createSMEItem(sme));
            });
        } else {
            smeList.innerHTML = `
                <div class="empty-state">
                    <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" opacity="0.4">
                        <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/>
                        <path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/>
                    </svg>
                    <p>No SMEs found. Add your first SME to get started.</p>
                </div>`;
        }
    } catch (error) {
        console.error('Error loading SMEs:', error);
    }
}

function createSMEItem(sme) {
    const div = document.createElement('div');
    div.className = 'sme-item';

    const statusClass = getStatusClass(sme.compliance_status);
    const statusText = getStatusText(sme.compliance_status);

    div.innerHTML = `
        <div class="sme-info">
            <h3>${escapeHtml(sme.name || 'Unknown')}</h3>
            <p>${escapeHtml(sme.pin)} &middot; ${escapeHtml(sme.business_name || 'No business name')}</p>
        </div>
        <span class="sme-status ${statusClass}">${statusText}</span>
    `;

    div.addEventListener('click', () => viewSMEDetails(sme.pin));
    return div;
}

function getStatusClass(status) {
    switch (status) {
        case 'compliant': return 'status-compliant';
        case 'at_risk': return 'status-at-risk';
        case 'non_compliant': return 'status-non-compliant';
        default: return 'status-at-risk';
    }
}

function getStatusText(status) {
    switch (status) {
        case 'compliant': return 'Compliant';
        case 'at_risk': return 'At Risk';
        case 'non_compliant': return 'Non-Compliant';
        default: return 'Unknown';
    }
}

// ── Activity ──────────────────────────────────────────────────
async function loadActivity() {
    try {
        const response = await fetch(`${API_BASE}/api/activity`);
        const data = await response.json();

        // Full list
        renderActivityList('activityList', data.activities, false);
        // Compact overview list (max 5)
        renderActivityList('overviewActivityList', (data.activities || []).slice(0, 5), true);
    } catch (error) {
        console.error('Error loading activity:', error);
    }
}

function renderActivityList(containerId, activities, compact) {
    const container = document.getElementById(containerId);
    if (!container) return;

    if (activities && activities.length > 0) {
        container.innerHTML = '';
        activities.forEach(activity => {
            container.appendChild(createActivityItem(activity));
        });
    } else {
        container.innerHTML = `
            <div class="empty-state">
                ${compact ? '' : '<svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" opacity="0.4"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg>'}
                <p>No recent activity</p>
            </div>`;
    }
}

function createActivityItem(activity) {
    const div = document.createElement('div');
    div.className = 'activity-item';

    const time = new Date(activity.timestamp).toLocaleString('en-KE', {
        month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit'
    });

    div.innerHTML = `
        <div class="activity-dot"></div>
        <div class="activity-body">
            <div class="activity-text">${escapeHtml(activity.description)}</div>
            <div class="activity-time">${time}</div>
        </div>
    `;

    return div;
}

// ── Proactive Recommendations ─────────────────────────────────
async function loadProactiveRecommendations() {
    try {
        const response = await fetch(`${API_BASE}/api/proactive`);
        const data = await response.json();

        // Full list
        renderProactiveList('proactiveList', data.recommendations, false);
        // Compact overview list (max 3)
        renderProactiveList('overviewProactiveList', (data.recommendations || []).slice(0, 3), true);
    } catch (error) {
        console.error('Error loading proactive recommendations:', error);
    }
}

function renderProactiveList(containerId, recommendations, compact) {
    const container = document.getElementById(containerId);
    if (!container) return;

    if (recommendations && recommendations.length > 0) {
        container.innerHTML = '';
        recommendations.forEach(rec => {
            container.appendChild(createProactiveItem(rec));
        });
    } else {
        container.innerHTML = `
            <div class="empty-state">
                ${compact ? '' : '<svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" opacity="0.4"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg>'}
                <p>No recommendations at this time</p>
            </div>`;
    }
}

function createProactiveItem(rec) {
    const div = document.createElement('div');
    div.className = 'proactive-item';

    const urgencyClass = `urgency-${rec.urgency || 'green'}`;
    const autoIcon = rec.autonomous ? '&#9881;' : '&#128100;';

    div.innerHTML = `
        <div class="proactive-header">
            <span class="proactive-icon">${autoIcon}</span>
            <span class="proactive-title">${escapeHtml(rec.title)}</span>
            <span class="proactive-urgency ${urgencyClass}">${rec.urgency || 'green'}</span>
        </div>
        <div class="proactive-detail">${escapeHtml(rec.detail)}</div>
        <div class="proactive-reasoning">${escapeHtml(rec.reasoning || 'N/A')}</div>
    `;

    return div;
}

// ── Uptime Timer ─────────────────────────────────────────────
function startUptimeTimer() {
    function update() {
        const elapsed = Math.floor((Date.now() - _startTime) / 1000);
        const h = String(Math.floor(elapsed / 3600)).padStart(2, '0');
        const m = String(Math.floor((elapsed % 3600) / 60)).padStart(2, '0');
        const s = String(elapsed % 60).padStart(2, '0');
        const el = document.getElementById('pulseUptime');
        if (el) el.textContent = `Uptime: ${h}:${m}:${s}`;
    }
    update();
    setInterval(update, 1000);
}

// ── System Status ─────────────────────────────────────────────
async function checkSystemStatus() {
    try {
        const response = await fetch(`${API_BASE}/health`);
        const data = await response.json();

        const apiOk = data.status === 'healthy';
        const dbOk = data.database === 'connected';
        const schedOk = data.scheduler === 'running';
        const monOk = data.monitoring === 'active';

        updateStatusIndicator('apiStatus', apiOk);
        updateStatusIndicator('dbStatus', dbOk);
        updateStatusIndicator('schedulerStatus', schedOk);
        updateStatusIndicator('monitoringStatus', monOk);

        setText('apiStatusText', apiOk ? 'Healthy' : 'Offline');
        setText('dbStatusText', dbOk ? 'Connected' : 'Disconnected');
        setText('schedulerStatusText', schedOk ? 'Running' : 'Stopped');
        setText('monitoringStatusText', monOk ? 'Active' : 'Inactive');

        // Update sidebar pulse
        const allOk = apiOk && dbOk && schedOk && monOk;
        const pulseOrb = document.querySelector('.pulse-orb-core');
        const pulseText = document.getElementById('pulseStatusText');

        if (allOk) {
            if (pulseOrb) pulseOrb.style.background = '';
            if (pulseText) { pulseText.textContent = 'Systems Online'; pulseText.classList.remove('offline'); }
        } else {
            if (pulseOrb) pulseOrb.style.background = 'var(--red)';
            if (pulseText) { pulseText.textContent = 'Issues Detected'; pulseText.classList.add('offline'); }
        }
    } catch (error) {
        console.error('Error checking system status:', error);
        updateStatusIndicator('apiStatus', false);
        updateStatusIndicator('dbStatus', false);
        updateStatusIndicator('schedulerStatus', false);
        updateStatusIndicator('monitoringStatus', false);

        setText('apiStatusText', 'Unreachable');
        setText('dbStatusText', 'Unknown');
        setText('schedulerStatusText', 'Unknown');
        setText('monitoringStatusText', 'Unknown');

        const pulseOrb2 = document.querySelector('.pulse-orb-core');
        const pulseText2 = document.getElementById('pulseStatusText');
        if (pulseOrb2) pulseOrb2.style.background = 'var(--red)';
        if (pulseText2) { pulseText2.textContent = 'Cannot reach server'; pulseText2.classList.add('offline'); }
    }
}

function updateStatusIndicator(elementId, isOnline) {
    const el = document.getElementById(elementId);
    if (el) {
        el.className = `system-node-ring ${isOnline ? 'online' : 'offline'}`;
    }
}

function setText(elementId, text) {
    const el = document.getElementById(elementId);
    if (el) el.textContent = text;
}

// ── Modal ─────────────────────────────────────────────────────
function showAddSMEModal() {
    document.getElementById('addSMEModal').classList.add('visible');
}

function closeModal() {
    document.getElementById('addSMEModal').classList.remove('visible');
    document.getElementById('addSMEForm').reset();
}

// Close modal on Escape key
document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') closeModal();
});

// ── Add SME ───────────────────────────────────────────────────
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
            headers: { 'Content-Type': 'application/json' },
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

// ── Filter SMEs ───────────────────────────────────────────────
function filterSMEs() {
    const term = document.getElementById('searchSME').value.toLowerCase();
    document.querySelectorAll('.sme-item').forEach(item => {
        item.style.display = item.textContent.toLowerCase().includes(term) ? 'flex' : 'none';
    });
}

// ── Quick Actions ─────────────────────────────────────────────
function viewSMEDetails(pin) {
    window.location.href = `${API_BASE}/ui/sme/${encodeURIComponent(pin)}`;
}

async function runComplianceCheck() {
    showNotification('Running compliance check...', 'info');
    try {
        const response = await fetch(`${API_BASE}/api/check`, { method: 'POST' });
        if (response.ok) {
            showNotification('Compliance check completed', 'success');
            loadDashboard();
        } else {
            showNotification('Error running compliance check', 'error');
        }
    } catch (error) {
        console.error('Error:', error);
        showNotification('Error running compliance check', 'error');
    }
}

function viewReports() {
    window.location.href = `${API_BASE}/ui/reports`;
}

async function checkMonitoring() {
    showNotification('Checking monitoring...', 'info');
    try {
        const response = await fetch(`${API_BASE}/api/monitoring/status`);
        if (response.ok) {
            const data = await response.json();
            showNotification(`Monitoring: ${data.status || 'checked'}`, 'success');
        } else {
            showNotification('Error checking monitoring', 'error');
        }
    } catch (error) {
        console.error('Error:', error);
        showNotification('Error checking monitoring', 'error');
    }
}

function viewAuditTrail() {
    window.location.href = `${API_BASE}/ui/audit`;
}

// ── Toast Notifications ───────────────────────────────────────
function showNotification(message, type = 'info') {
    const container = document.getElementById('toastContainer');

    const icons = {
        success: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>',
        error: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>',
        info: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg>'
    };

    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.innerHTML = `
        <span class="toast-icon">${icons[type] || icons.info}</span>
        <span>${escapeHtml(message)}</span>
    `;

    container.appendChild(toast);

    setTimeout(() => {
        toast.classList.add('removing');
        toast.addEventListener('animationend', () => toast.remove());
    }, 3000);
}

// ── Utility ───────────────────────────────────────────────────
function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}
