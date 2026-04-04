import { useNavigate, useLocation } from 'react-router-dom';
import { LayoutGrid, Users, Activity, Settings, Shield, FileText, ScrollText, CreditCard } from 'lucide-react';

const navItems = [
  { id: 'overview', label: 'Overview', icon: LayoutGrid },
  { id: 'smes', label: 'SME Management', icon: Users },
  { id: 'subscriptions', label: 'Subscriptions', icon: CreditCard },
  { id: 'activity', label: 'Activity Feed', icon: Activity },
  { id: 'reports', label: 'Reports', icon: FileText },
  { id: 'audit', label: 'Audit Trail', icon: ScrollText },
  { id: 'system', label: 'System Status', icon: Settings },
];

export default function Sidebar({ currentPage, onNavigate }) {
  const navigate = useNavigate();
  const location = useLocation();

  const handleNav = (itemId) => {
    if (itemId === 'overview') {
      onNavigate(itemId);
      navigate('/');
    } else if (itemId === 'reports') {
      onNavigate(itemId);
      navigate('/reports');
    } else if (itemId === 'audit') {
      onNavigate(itemId);
      navigate('/audit');
    } else {
      onNavigate(itemId);
    }
  };

  const isActive = (itemId) => {
    if (location.pathname === '/' && itemId === 'overview') return true;
    if (location.pathname === '/reports' && itemId === 'reports') return true;
    if (location.pathname === '/audit' && itemId === 'audit') return true;
    return currentPage === itemId;
  };

  return (
    <aside className="sidebar">
      <div className="sidebar-brand">
        <div className="brand-icon">
          <Shield size={24} />
        </div>
        <div className="brand-text">
          <span className="brand-name">KRA Deadline Tracker</span>
          <span className="brand-tagline">TAX COMPLIANCE</span>
        </div>
      </div>

      <nav className="sidebar-nav">
        <span className="nav-label">Navigation</span>
        {navItems.map((item) => (
          <div
            key={item.id}
            className={`nav-item ${isActive(item.id) ? 'active' : ''}`}
            onClick={() => handleNav(item.id)}
          >
            <item.icon size={18} />
            <span>{item.label}</span>
          </div>
        ))}
      </nav>

      <div style={{ marginTop: 'auto', paddingTop: '1rem', borderTop: '1px solid var(--border)' }}>
        <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>
          <div>Systems Online</div>
          <div style={{ fontFamily: 'monospace' }}>v1.0 // NAIROBI</div>
        </div>
      </div>
    </aside>
  );
}