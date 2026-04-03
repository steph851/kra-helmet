import { useQuery } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { ArrowLeft, Clock, User, Hash, Activity } from 'lucide-react';

const API_BASE = '/api';

const statusColors = {
  compliant: { bg: 'rgba(34, 197, 94, 0.1)', color: '#22c55e' },
  at_risk: { bg: 'rgba(245, 158, 11, 0.1)', color: '#f59e0b' },
  non_compliant: { bg: 'rgba(239, 68, 68, 0.1)', color: '#ef4444' },
};

function formatDate(ts) {
  if (!ts) return '-';
  return ts.replace('T', ' ').slice(0, 19);
}

export default function AuditLog() {
  const navigate = useNavigate();
  
  const { data, isLoading } = useQuery({
    queryKey: ['audit'],
    queryFn: async () => {
      const res = await fetch(`${API_BASE}/audit?limit=100`);
      return res.json();
    },
  });

  if (isLoading) return <div className="loading">Loading...</div>;

  const entries = data?.entries || [];

  return (
    <div>
      <div style={{ marginBottom: '1.5rem' }}>
        <button 
          onClick={() => navigate('/')} 
          className="nav-item"
          style={{ background: 'transparent', border: 'none', paddingLeft: 0 }}
        >
          <ArrowLeft size={18} />
          <span>Back to Dashboard</span>
        </button>
      </div>
      
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.5rem' }}>
        <h2>Audit Trail</h2>
        <span style={{ color: 'var(--text-muted)', fontSize: '0.9rem' }}>
          {entries.length} entries
        </span>
      </div>
      
      <div className="stat-card">
        {entries.length === 0 ? (
          <div className="empty">No audit trail entries yet</div>
        ) : (
          <table style={{ 
            width: '100%', 
            borderCollapse: 'collapse' 
          }}>
            <thead>
              <tr style={{ background: 'var(--primary)', color: 'white' }}>
                <th style={{ padding: '0.6rem 0.8rem', textAlign: 'left', fontWeight: 600, fontSize: '0.85rem' }}>Time</th>
                <th style={{ padding: '0.6rem 0.8rem', textAlign: 'left', fontWeight: 600, fontSize: '0.85rem' }}>Event</th>
                <th style={{ padding: '0.6rem 0.8rem', textAlign: 'left', fontWeight: 600, fontSize: '0.85rem' }}>Agent</th>
                <th style={{ padding: '0.6rem 0.8rem', textAlign: 'left', fontWeight: 600, fontSize: '0.85rem' }}>PIN</th>
                <th style={{ padding: '0.6rem 0.8rem', textAlign: 'left', fontWeight: 600, fontSize: '0.85rem' }}>Status</th>
                <th style={{ padding: '0.6rem 0.8rem', textAlign: 'left', fontWeight: 600, fontSize: '0.85rem' }}>Risk</th>
              </tr>
            </thead>
            <tbody>
              {entries.map((entry, idx) => {
                const details = entry.details || {};
                const status = details.compliance_status || details.reason || '';
                const risk = details.risk_score;
                const colors = statusColors[status] || { bg: 'transparent', color: 'var(--text-muted)' };
                
                return (
                  <tr key={idx} style={{ borderBottom: '1px solid var(--border)' }}>
                    <td style={{ padding: '0.55rem 0.8rem', fontSize: '0.8rem', whiteSpace: 'nowrap', color: 'var(--text-muted)' }}>
                      {formatDate(entry.timestamp)}
                    </td>
                    <td style={{ padding: '0.55rem 0.8rem', fontSize: '0.85rem' }}>
                      <strong>{entry.event_type}</strong>
                    </td>
                    <td style={{ padding: '0.55rem 0.8rem', fontSize: '0.85rem', color: 'var(--text-muted)' }}>
                      {entry.agent || '-'}
                    </td>
                    <td style={{ padding: '0.55rem 0.8rem', fontSize: '0.85rem', fontFamily: 'monospace' }}>
                      {entry.sme_pin || '-'}
                    </td>
                    <td style={{ padding: '0.55rem 0.8rem', fontSize: '0.85rem' }}>
                      {status ? (
                        <span style={{ 
                          padding: '3px 10px', 
                          borderRadius: '12px', 
                          fontSize: '0.75rem', 
                          fontWeight: 600,
                          background: colors.bg,
                          color: colors.color
                        }}>
                          {status}
                        </span>
                      ) : '-'}
                    </td>
                    <td style={{ padding: '0.55rem 0.8rem', fontSize: '0.85rem', fontFamily: 'monospace' }}>
                      {risk != null ? `${risk}/100` : '-'}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}