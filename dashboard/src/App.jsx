import { useState } from 'react';
import { BrowserRouter, Routes, Route, useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { Users, Activity, Settings, Shield, LayoutGrid, FileText, ScrollText, MessageCircle } from 'lucide-react';
import Sidebar from './components/Sidebar';
import StatsCards from './components/StatsCards';
import SMEList from './components/SMEList';
import ActivityFeed from './components/ActivityFeed';
import SystemStatus from './components/SystemStatus';
import Reports from './components/Reports';
import SMEDetail from './components/SMEDetail';
import AuditLog from './components/AuditLog';

const API_BASE = '/api';

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<DashboardLayout />} />
        <Route path="/reports" element={<DashboardLayout><Reports /></DashboardLayout>} />
        <Route path="/sme/:pin" element={<DashboardLayout><SMEDetail /></DashboardLayout>} />
        <Route path="/audit" element={<DashboardLayout><AuditLog /></DashboardLayout>} />
      </Routes>
    </BrowserRouter>
  );
}

function DashboardLayout({ children }) {
  const [currentPage, setCurrentPage] = useState('overview');

  return (
    <div className="app">
      <Sidebar currentPage={currentPage} onNavigate={setCurrentPage} />
      <main className="main">
        <header className="topbar">
          <h1 className="page-title">
            {currentPage === 'overview' && 'Overview'}
            {currentPage === 'smes' && 'SME Management'}
            {currentPage === 'activity' && 'Activity Feed'}
            {currentPage === 'system' && 'System Status'}
            {currentPage === 'reports' && 'Reports'}
            {currentPage === 'audit' && 'Audit Trail'}
          </h1>
        </header>

        {currentPage === 'overview' && <OverviewPage />}
        {currentPage === 'smes' && <SMEList />}
        {currentPage === 'activity' && <ActivityFeed />}
        {currentPage === 'system' && <SystemStatus />}
        {currentPage === 'reports' && <Reports />}
        {currentPage === 'audit' && <AuditLog />}
        
        {children}
      </main>
    </div>
  );
}

function OverviewPage() {
  const navigate = useNavigate();
  
  const { data: stats, isLoading: statsLoading } = useQuery({
    queryKey: ['stats'],
    queryFn: async () => {
      const res = await fetch(`${API_BASE}/stats`);
      return res.json();
    },
  });

  const { data: smes, isLoading: smesLoading } = useQuery({
    queryKey: ['smes'],
    queryFn: async () => {
      const res = await fetch(`${API_BASE}/smes`);
      return res.json();
    },
  });

  const { data: activity, isLoading: activityLoading } = useQuery({
    queryKey: ['activity'],
    queryFn: async () => {
      const res = await fetch(`${API_BASE}/activity?limit=5`);
      return res.json();
    },
  });

  if (statsLoading || smesLoading) {
    return <div className="loading">Loading...</div>;
  }

  return (
    <>
      <StatsCards stats={stats} />
      
      {/* KRA Shuru Quick Action */}
      <div className="stat-card" style={{ marginBottom: '1.5rem', background: 'linear-gradient(135deg, #075E54 0%, #25D366 100%)', color: '#fff', borderColor: 'transparent' }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '1rem' }}>
          <div>
            <h3 style={{ margin: '0 0 0.25rem', display: 'flex', alignItems: 'center', gap: '0.5rem', color: '#fff' }}>
              <MessageCircle size={20} />
              KRA WhatsApp (Shuru)
            </h3>
            <p style={{ margin: 0, opacity: 0.9, fontSize: '0.85rem' }}>
              Your SMEs can now file returns, pay taxes & get compliance certs via WhatsApp in 3 steps.
            </p>
          </div>
          <a
            href="https://wa.me/254711099999"
            target="_blank"
            rel="noopener noreferrer"
            style={{
              display: 'inline-flex', alignItems: 'center', gap: '0.5rem',
              padding: '0.6rem 1.5rem', background: 'rgba(255,255,255,0.2)', color: '#fff',
              borderRadius: '8px', textDecoration: 'none', fontWeight: 600, fontSize: '0.85rem',
              backdropFilter: 'blur(4px)', border: '1px solid rgba(255,255,255,0.3)'
            }}
          >
            Open Shuru +254 711 099 999
          </a>
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1.5rem' }}>
        <div className="stat-card">
          <h3 style={{ marginBottom: '1rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <Users size={18} />
            Recent SMEs
          </h3>
          {smesLoading ? (
            <div className="loading">Loading...</div>
          ) : smes?.smes?.slice(0, 5).map((sme) => (
            <div 
              key={sme.pin} 
              className="sme-card" 
              style={{ marginBottom: '0.5rem' }}
              onClick={() => navigate(`/sme/${sme.pin}`)}
            >
              <div className="sme-info">
                <span className="sme-name">{sme.name}</span>
                <span className="sme-pin">{sme.pin}</span>
              </div>
              <span className={`status-badge ${sme.compliance_status}`}>
                {sme.compliance_status || 'unknown'}
              </span>
            </div>
          ))}
        </div>

        <div className="stat-card">
          <h3 style={{ marginBottom: '1rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <Activity size={18} />
            Recent Activity
          </h3>
          {activityLoading ? (
            <div className="loading">Loading...</div>
          ) : activity?.activities?.length > 0 ? (
            activity.activities.map((item, idx) => (
              <div key={idx} style={{ padding: '0.5rem 0', borderBottom: '1px solid var(--border)' }}>
                <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
                  {item.timestamp?.replace('T', ' ').slice(0, 16)}
                </div>
                <div>{item.description}</div>
              </div>
            ))
          ) : (
            <div className="empty">No recent activity</div>
          )}
        </div>
      </div>
    </>
  );
}

export default App;