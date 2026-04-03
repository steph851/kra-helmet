import { useQuery } from '@tanstack/react-query';

const API_BASE = '/api';

export default function SMEList() {
  const { data, isLoading, error } = useQuery({
    queryKey: ['smes'],
    queryFn: async () => {
      const res = await fetch(`${API_BASE}/smes`);
      return res.json();
    },
  });

  if (isLoading) return <div className="loading">Loading...</div>;
  if (error) return <div className="error">Error loading SMEs</div>;

  const smes = data?.smes || [];

  return (
    <div className="stat-card">
      <h3 style={{ marginBottom: '1rem' }}>SME Registry</h3>
      {smes.length === 0 ? (
        <div className="empty">No SMEs registered</div>
      ) : (
        <div className="sme-grid">
          {smes.map((sme) => (
            <div key={sme.pin} className="sme-card">
              <div className="sme-info">
                <span className="sme-name">{sme.name}</span>
                <span className="sme-pin">{sme.pin}</span>
              </div>
              <span className={`status-badge ${sme.compliance_status || 'unknown'}`}>
                {sme.compliance_status || 'unknown'}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}