import { Users, CheckCircle, AlertTriangle, XCircle } from 'lucide-react';

export default function StatsCards({ stats }) {
  return (
    <div className="stats-grid">
      <div className="stat-card">
        <Users size={22} style={{ color: 'var(--text-muted)', marginBottom: '0.5rem' }} />
        <span className="stat-value">{stats?.total_smes || 0}</span>
        <span className="stat-label">Total SMEs</span>
      </div>

      <div className="stat-card compliant">
        <CheckCircle size={22} style={{ color: 'var(--success)', marginBottom: '0.5rem' }} />
        <span className="stat-value">{stats?.compliant_smes || 0}</span>
        <span className="stat-label">Compliant</span>
      </div>

      <div className="stat-card at-risk">
        <AlertTriangle size={22} style={{ color: 'var(--warning)', marginBottom: '0.5rem' }} />
        <span className="stat-value">{stats?.at_risk_smes || 0}</span>
        <span className="stat-label">At Risk</span>
      </div>

      <div className="stat-card non-compliant">
        <XCircle size={22} style={{ color: 'var(--danger)', marginBottom: '0.5rem' }} />
        <span className="stat-value">{stats?.non_compliant_smes || 0}</span>
        <span className="stat-label">Non-Compliant</span>
      </div>
    </div>
  );
}