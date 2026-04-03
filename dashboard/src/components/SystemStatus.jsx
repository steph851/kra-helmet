import { useState, useEffect } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Server, Database, Clock, Eye, Shield, Wifi, Activity, Zap, ChevronRight } from 'lucide-react';

export default function SystemStatus() {
  const { data: health, isLoading, dataUpdatedAt } = useQuery({
    queryKey: ['health'],
    queryFn: async () => {
      const res = await fetch('/health');
      return res.json();
    },
    refetchInterval: 10000,
  });

  const [uptime, setUptime] = useState(0);
  useEffect(() => {
    const t = setInterval(() => setUptime(s => s + 1), 1000);
    return () => clearInterval(t);
  }, []);

  const pad = n => String(n).padStart(2, '0');
  const hours = pad(Math.floor(uptime / 3600));
  const mins = pad(Math.floor((uptime % 3600) / 60));
  const secs = pad(uptime % 60);

  const apiOk = health?.status === 'healthy';
  const dbOk = health?.database === 'connected';
  const schedOk = health?.scheduler === 'running';
  const monOk = health?.monitoring === 'active';
  const allOk = apiOk && dbOk && schedOk && monOk;

  const systems = [
    {
      id: 'api',
      icon: Server,
      label: 'API SERVER',
      online: apiOk,
      detail: apiOk ? 'Healthy' : 'Offline',
      sub: health?.checks?.config?.version || '',
    },
    {
      id: 'db',
      icon: Database,
      label: 'DATABASE',
      online: dbOk,
      detail: dbOk ? 'Connected' : 'Disconnected',
      sub: `${health?.checks?.sme_registry?.count ?? '?'} SMEs`,
    },
    {
      id: 'sched',
      icon: Clock,
      label: 'SCHEDULER',
      online: schedOk,
      detail: schedOk ? 'Running' : 'Stopped',
      sub: 'The Pulse',
    },
    {
      id: 'mon',
      icon: Eye,
      label: 'MONITORING',
      online: monOk,
      detail: monOk ? 'Active' : 'Inactive',
      sub: 'The Eyes',
    },
  ];

  const onlineCount = systems.filter(s => s.online).length;

  if (isLoading) {
    return (
      <div style={styles.container}>
        <div style={styles.loadingPulse}>
          <Zap size={32} style={{ animation: 'pulse 1.5s infinite' }} />
          <span>Initializing diagnostics...</span>
        </div>
      </div>
    );
  }

  return (
    <div style={styles.container}>
      {/* Hero status ring */}
      <div style={styles.heroSection}>
        <div style={{
          ...styles.statusRing,
          borderColor: allOk ? '#22c55e' : '#ef4444',
          boxShadow: `0 0 40px ${allOk ? 'rgba(34,197,94,0.25)' : 'rgba(239,68,68,0.25)'},
                       0 0 80px ${allOk ? 'rgba(34,197,94,0.08)' : 'rgba(239,68,68,0.08)'}`,
        }}>
          <div style={{
            ...styles.statusRingInner,
            background: allOk
              ? 'radial-gradient(circle, rgba(34,197,94,0.15) 0%, transparent 70%)'
              : 'radial-gradient(circle, rgba(239,68,68,0.15) 0%, transparent 70%)',
          }}>
            <Shield size={28} style={{ color: allOk ? '#22c55e' : '#ef4444', marginBottom: 4 }} />
            <span style={{
              ...styles.statusLabel,
              color: allOk ? '#22c55e' : '#ef4444',
            }}>
              {allOk ? 'ALL SYSTEMS' : 'DEGRADED'}
            </span>
            <span style={{
              fontSize: '0.65rem',
              color: 'var(--text-muted)',
              letterSpacing: '0.15em',
            }}>
              {onlineCount}/{systems.length} ONLINE
            </span>
          </div>
        </div>

        {/* Uptime display */}
        <div style={styles.uptimeContainer}>
          <div style={styles.uptimeLabel}>SESSION UPTIME</div>
          <div style={styles.uptimeValue}>
            <span style={styles.uptimeDigit}>{hours}</span>
            <span style={styles.uptimeSep}>:</span>
            <span style={styles.uptimeDigit}>{mins}</span>
            <span style={styles.uptimeSep}>:</span>
            <span style={styles.uptimeDigit}>{secs}</span>
          </div>
        </div>
      </div>

      {/* System grid */}
      <div style={styles.gridLabel}>SUBSYSTEMS</div>
      <div style={styles.systemGrid}>
        {systems.map(sys => (
          <SystemCard key={sys.id} {...sys} />
        ))}
      </div>

      {/* Health checks detail */}
      <div style={styles.gridLabel}>HEALTH CHECKS</div>
      <div style={styles.checksContainer}>
        {health?.checks && Object.entries(health.checks)
          .filter(([k]) => !['scheduler', 'monitoring', 'database'].includes(k))
          .map(([key, val]) => (
            <CheckRow key={key} name={key} check={val} />
          ))}
      </div>

      {/* Footer timestamp */}
      <div style={styles.footer}>
        <Wifi size={12} />
        <span>Last polled {health?.timestamp?.replace('T', ' ').slice(0, 19) || '—'}</span>
        <span style={{ opacity: 0.4 }}>|</span>
        <span>Auto-refresh 10s</span>
      </div>
    </div>
  );
}

function SystemCard({ icon: Icon, label, online, detail, sub }) {
  return (
    <div style={{
      ...cardStyles.card,
      borderColor: online ? 'rgba(34,197,94,0.3)' : 'rgba(239,68,68,0.3)',
    }}>
      {/* Glow bar */}
      <div style={{
        ...cardStyles.glowBar,
        background: online
          ? 'linear-gradient(90deg, #22c55e, #10b981, #22c55e)'
          : 'linear-gradient(90deg, #ef4444, #f87171, #ef4444)',
        opacity: online ? 1 : 0.6,
      }} />

      <div style={cardStyles.cardContent}>
        <div style={cardStyles.topRow}>
          <div style={{
            ...cardStyles.iconBox,
            background: online ? 'rgba(34,197,94,0.1)' : 'rgba(239,68,68,0.1)',
            color: online ? '#22c55e' : '#ef4444',
          }}>
            <Icon size={18} />
          </div>
          <div style={{
            ...cardStyles.dot,
            background: online ? '#22c55e' : '#ef4444',
            boxShadow: `0 0 8px ${online ? '#22c55e' : '#ef4444'}`,
          }} />
        </div>

        <div style={cardStyles.label}>{label}</div>

        <div style={{
          ...cardStyles.detail,
          color: online ? '#22c55e' : '#ef4444',
        }}>
          {detail}
        </div>

        <div style={cardStyles.sub}>{sub}</div>
      </div>
    </div>
  );
}

function CheckRow({ name, check }) {
  const ok = ['ok', 'enabled', 'disabled', 'not_started'].includes(check?.status);
  const label = name.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());

  return (
    <div style={checkStyles.row}>
      <div style={{
        ...checkStyles.dot,
        background: ok ? '#22c55e' : '#ef4444',
      }} />
      <span style={checkStyles.label}>{label}</span>
      <span style={{
        ...checkStyles.status,
        color: ok ? 'var(--text-muted)' : '#ef4444',
      }}>
        {check?.status || 'unknown'}
      </span>
      {check?.count != null && (
        <span style={checkStyles.badge}>{check.count}</span>
      )}
      {check?.version && (
        <span style={checkStyles.badge}>{check.version}</span>
      )}
      <ChevronRight size={14} style={{ color: 'var(--border)', marginLeft: 'auto' }} />
    </div>
  );
}


/* ── Styles ── */

const styles = {
  container: {
    maxWidth: 800,
    margin: '0 auto',
  },
  heroSection: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    gap: '3rem',
    marginBottom: '2.5rem',
    padding: '2rem 0',
  },
  statusRing: {
    width: 140,
    height: 140,
    borderRadius: '50%',
    border: '2px solid',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    position: 'relative',
  },
  statusRingInner: {
    width: 120,
    height: 120,
    borderRadius: '50%',
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 2,
  },
  statusLabel: {
    fontSize: '0.7rem',
    fontWeight: 800,
    letterSpacing: '0.2em',
    fontFamily: "'JetBrains Mono', monospace",
  },
  uptimeContainer: {
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'flex-start',
    gap: '0.25rem',
  },
  uptimeLabel: {
    fontSize: '0.6rem',
    color: 'var(--text-muted)',
    letterSpacing: '0.2em',
    fontWeight: 600,
  },
  uptimeValue: {
    display: 'flex',
    alignItems: 'baseline',
    gap: 2,
    fontFamily: "'JetBrains Mono', monospace",
  },
  uptimeDigit: {
    fontSize: '2rem',
    fontWeight: 700,
    color: 'var(--text)',
    minWidth: '2ch',
    textAlign: 'center',
  },
  uptimeSep: {
    fontSize: '1.5rem',
    fontWeight: 300,
    color: 'var(--text-muted)',
    opacity: 0.5,
  },
  gridLabel: {
    fontSize: '0.6rem',
    color: 'var(--text-muted)',
    letterSpacing: '0.2em',
    fontWeight: 700,
    marginBottom: '0.75rem',
  },
  systemGrid: {
    display: 'grid',
    gridTemplateColumns: 'repeat(auto-fit, minmax(170px, 1fr))',
    gap: '0.75rem',
    marginBottom: '2rem',
  },
  checksContainer: {
    background: 'var(--bg-card)',
    border: '1px solid var(--border)',
    borderRadius: '10px',
    overflow: 'hidden',
    marginBottom: '1.5rem',
  },
  footer: {
    display: 'flex',
    alignItems: 'center',
    gap: '0.5rem',
    fontSize: '0.7rem',
    color: 'var(--text-muted)',
    opacity: 0.6,
    fontFamily: "'JetBrains Mono', monospace",
  },
  loadingPulse: {
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    justifyContent: 'center',
    gap: '1rem',
    padding: '6rem 0',
    color: 'var(--text-muted)',
    fontSize: '0.85rem',
  },
};

const cardStyles = {
  card: {
    background: 'var(--bg-card)',
    border: '1px solid',
    borderRadius: '12px',
    overflow: 'hidden',
    position: 'relative',
    transition: 'all 0.3s',
  },
  glowBar: {
    height: 2,
    width: '100%',
    backgroundSize: '200% 100%',
    animation: 'shimmer 2s linear infinite',
  },
  cardContent: {
    padding: '1.25rem',
  },
  topRow: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: '0.75rem',
  },
  iconBox: {
    width: 36,
    height: 36,
    borderRadius: '8px',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
  },
  dot: {
    width: 8,
    height: 8,
    borderRadius: '50%',
    animation: 'pulse 2s infinite',
  },
  label: {
    fontSize: '0.6rem',
    fontWeight: 700,
    letterSpacing: '0.18em',
    color: 'var(--text-muted)',
    marginBottom: '0.25rem',
    fontFamily: "'JetBrains Mono', monospace",
  },
  detail: {
    fontSize: '1rem',
    fontWeight: 700,
    marginBottom: '0.15rem',
  },
  sub: {
    fontSize: '0.7rem',
    color: 'var(--text-muted)',
    opacity: 0.7,
  },
};

const checkStyles = {
  row: {
    display: 'flex',
    alignItems: 'center',
    gap: '0.75rem',
    padding: '0.65rem 1rem',
    borderBottom: '1px solid var(--border)',
    fontSize: '0.8rem',
  },
  dot: {
    width: 6,
    height: 6,
    borderRadius: '50%',
    flexShrink: 0,
  },
  label: {
    fontWeight: 500,
    color: 'var(--text)',
    minWidth: 140,
  },
  status: {
    fontFamily: "'JetBrains Mono', monospace",
    fontSize: '0.75rem',
  },
  badge: {
    padding: '2px 8px',
    borderRadius: '4px',
    background: 'var(--bg-elevated)',
    fontSize: '0.7rem',
    fontFamily: "'JetBrains Mono', monospace",
    color: 'var(--text-muted)',
  },
};
