import { useQuery } from '@tanstack/react-query';
import { FileText, ArrowLeft } from 'lucide-react';
import { useNavigate } from 'react-router-dom';

const API_BASE = '/api';

export default function Reports() {
  const navigate = useNavigate();
  const { data, isLoading } = useQuery({
    queryKey: ['smes'],
    queryFn: async () => {
      const res = await fetch(`${API_BASE}/smes`);
      return res.json();
    },
  });

  if (isLoading) return <div className="loading">Loading...</div>;

  const smes = data?.smes || [];

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
      
      <h2 style={{ marginBottom: '1.5rem' }}>Reports</h2>
      
      <div className="stat-card">
        {smes.length === 0 ? (
          <div className="empty">No SMEs to generate reports for</div>
        ) : (
          <div className="sme-grid">
            {smes.map((sme) => (
              <div 
                key={sme.pin} 
                className="sme-card"
                onClick={() => navigate(`/sme/${sme.pin}`)}
              >
                <div className="sme-info">
                  <span className="sme-name">{sme.name}</span>
                  <span className="sme-pin">{sme.pin}</span>
                </div>
                <FileText size={20} style={{ color: 'var(--text-muted)' }} />
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}