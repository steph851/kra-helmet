import { useQuery } from '@tanstack/react-query';

const API_BASE = '/api';

export default function ActivityFeed() {
  const { data, isLoading, error } = useQuery({
    queryKey: ['activity'],
    queryFn: async () => {
      const res = await fetch(`${API_BASE}/activity?limit=20`);
      return res.json();
    },
  });

  if (isLoading) return <div className="loading">Loading...</div>;
  if (error) return <div className="error">Error loading activity</div>;

  const activities = data?.activities || [];

  return (
    <div className="stat-card">
      <h3 style={{ marginBottom: '1rem' }}>Activity Timeline</h3>
      {activities.length === 0 ? (
        <div className="empty">No activity recorded yet</div>
      ) : (
        <div>
          {activities.map((item, idx) => (
            <div 
              key={idx} 
              style={{ 
                padding: '0.75rem 0', 
                borderBottom: '1px solid var(--border)',
                display: 'flex',
                gap: '1rem'
              }}
            >
              <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', minWidth: '140px' }}>
                {item.timestamp?.replace('T', ' ').slice(0, 16)}
              </div>
              <div style={{ flex: 1 }}>
                <div>{item.description}</div>
                <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                  {item.agent}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}