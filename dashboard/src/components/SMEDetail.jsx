import { useQuery } from '@tanstack/react-query';
import { useParams, useNavigate } from 'react-router-dom';
import { ArrowLeft, AlertTriangle, Calendar, DollarSign, Users, Building, MapPin, Phone, Mail, TrendingUp, MessageCircle, ExternalLink } from 'lucide-react';

const API_BASE = '/api';

function InfoGrid({ items }) {
  return (
    <dl style={{ 
      display: 'grid', 
      gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', 
      gap: '0.5rem 2rem',
      background: 'var(--bg-card)',
      padding: '1rem',
      borderRadius: '8px',
      border: '1px solid var(--border)'
    }}>
      {items.map((item) => (
        <>
          <dt style={{ fontSize: '0.75rem', textTransform: 'uppercase', color: 'var(--text-muted)' }}>
            {item.label}
          </dt>
          <dd style={{ margin: '0 0 0.75rem 0', fontWeight: 600 }}>{item.value}</dd>
        </>
      ))}
    </dl>
  );
}

function RiskBadge({ score, level }) {
  const colors = {
    low: 'var(--success)',
    medium: 'var(--warning)',
    high: 'var(--danger)',
  };
  return (
    <div style={{ 
      padding: '0.5rem 1rem', 
      background: `${colors[level] || colors.low}20`, 
      color: colors[level] || colors.low,
      borderRadius: '8px',
      fontWeight: 600,
      fontSize: '1.3rem'
    }}>
      {score}/100 <span style={{ fontSize: '0.8rem', opacity: 0.8 }}>({level})</span>
    </div>
  );
}

export default function SMEDetail() {
  const { pin } = useParams();
  const navigate = useNavigate();
  
  const { data: sme, isLoading } = useQuery({
    queryKey: ['sme', pin],
    queryFn: async () => {
      const res = await fetch(`${API_BASE}/smes/${pin}`);
      if (!res.ok) throw new Error('SME not found');
      return res.json();
    },
  });

  const { data: shuru } = useQuery({
    queryKey: ['shuru', pin],
    queryFn: async () => {
      const res = await fetch(`${API_BASE}/shuru/${pin}`);
      return res.json();
    },
    enabled: !!pin,
  });

  if (isLoading) return <div className="loading">Loading...</div>;
  if (!sme) return <div className="error">SME not found</div>;

  const profile = sme;
  const report = sme.latest_report || {};
  const compliance = report.compliance || {};
  const risk = report.risk || {};
  const obligations = report.obligations || [];
  const penalties = report.penalties || {};

  const statusColors = {
    compliant: 'var(--success)',
    at_risk: 'var(--warning)',
    non_compliant: 'var(--danger)',
  };

  const oblStatusColors = {
    overdue: 'var(--danger)',
    due_soon: 'var(--warning)',
    upcoming: 'var(--success)',
  };

  return (
    <div>
      <div style={{ marginBottom: '1.5rem' }}>
        <button 
          onClick={() => navigate('/reports')} 
          className="nav-item"
          style={{ background: 'transparent', border: 'none', paddingLeft: 0 }}
        >
          <ArrowLeft size={18} />
          <span>Back to Reports</span>
        </button>
      </div>

      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: '1rem', marginBottom: '1.5rem' }}>
        <div>
          <h2 style={{ margin: 0 }}>{profile.name}</h2>
          <div style={{ color: 'var(--text-muted)' }}>
            {profile.business_name} · {pin}
          </div>
        </div>
        <div style={{ 
          padding: '0.5rem 1rem', 
          borderRadius: '8px',
          background: `${statusColors[compliance.overall] || 'var(--text-muted)'}20`,
          color: statusColors[compliance.overall] || 'var(--text-muted)',
          fontWeight: 600,
          fontSize: '0.9rem',
          textTransform: 'uppercase'
        }}>
          {compliance.overall?.replace('_', ' ') || 'Unknown'}
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '1rem', marginBottom: '1.5rem' }}>
        <div className="stat-card">
          <div style={{ fontSize: '0.75rem', textTransform: 'uppercase', color: 'var(--text-muted)', marginBottom: '0.25rem' }}>
            Risk Score
          </div>
          <RiskBadge score={risk.risk_score || '?'} level={risk.risk_level || 'unknown'} />
        </div>
        <div className="stat-card">
          <div style={{ fontSize: '0.75rem', textTransform: 'uppercase', color: 'var(--text-muted)', marginBottom: '0.25rem' }}>
            Obligations
          </div>
          <div style={{ fontSize: '1.3rem', fontWeight: 700 }}>
            {compliance.obligations_met || 0}/{compliance.obligations_total || 0} met
          </div>
        </div>
        <div className="stat-card">
          <div style={{ fontSize: '0.75rem', textTransform: 'uppercase', color: 'var(--text-muted)', marginBottom: '0.25rem' }}>
            Penalty Exposure
          </div>
          <div style={{ fontSize: '1.3rem', fontWeight: 700, fontFamily: 'monospace' }}>
            KES {(penalties.total_penalty_exposure_kes || 0).toLocaleString()}
          </div>
        </div>
        <div className="stat-card">
          <div style={{ fontSize: '0.75rem', textTransform: 'uppercase', color: 'var(--text-muted)', marginBottom: '0.25rem' }}>
            Severity
          </div>
          <div style={{ fontSize: '1.3rem', fontWeight: 700, textTransform: 'capitalize' }}>
            {penalties.severity || 'None'}
          </div>
        </div>
      </div>

      <div className="section" style={{ marginBottom: '1.5rem' }}>
        <h3 style={{ marginBottom: '0.75rem', color: 'var(--primary)' }}>Business Profile</h3>
        <InfoGrid items={[
          { label: 'Type', value: (profile.business_type || '').replace('_', ' ').replace(/\b\w/g, l => l.toUpperCase()) },
          { label: 'Industry', value: (profile.industry || '').replace('_', ' ').replace(/\b\w/g, l => l.toUpperCase()) },
          { label: 'County', value: profile.county || '-' },
          { label: 'Annual Turnover', value: `KES ${(profile.annual_turnover_kes || 0).toLocaleString()}` },
          { label: 'Employees', value: profile.employee_count || 0 },
          { label: 'VAT Registered', value: profile.is_vat_registered ? 'Yes' : 'No' },
          { label: 'eTIMS', value: profile.has_etims ? 'Yes' : 'No' },
          { label: 'Phone', value: profile.phone || '-' },
          { label: 'Email', value: profile.email || '-' },
        ]} />
      </div>

      {compliance.next_action && (
        <div style={{ marginBottom: '1.5rem', padding: '1rem', background: 'var(--bg-card)', borderRadius: '8px', border: '1px solid var(--border)' }}>
          <strong>Next Action:</strong> {compliance.next_action}
        </div>
      )}

      <div className="section" style={{ marginBottom: '1.5rem' }}>
        <h3 style={{ marginBottom: '0.75rem', color: 'var(--primary)' }}>Tax Obligations</h3>
        {obligations.length > 0 ? (
          <table style={{ 
            width: '100%', 
            borderCollapse: 'collapse', 
            background: 'var(--bg-card)', 
            borderRadius: '8px', 
            overflow: 'hidden',
            border: '1px solid var(--border)'
          }}>
            <thead>
              <tr style={{ background: 'var(--primary)', color: 'white' }}>
                <th style={{ padding: '0.6rem 0.8rem', textAlign: 'left', fontWeight: 600, fontSize: '0.85rem' }}>Tax</th>
                <th style={{ padding: '0.6rem 0.8rem', textAlign: 'left', fontWeight: 600, fontSize: '0.85rem' }}>Freq</th>
                <th style={{ padding: '0.6rem 0.8rem', textAlign: 'left', fontWeight: 600, fontSize: '0.85rem' }}>Next Deadline</th>
                <th style={{ padding: '0.6rem 0.8rem', textAlign: 'left', fontWeight: 600, fontSize: '0.85rem' }}>Days</th>
                <th style={{ padding: '0.6rem 0.8rem', textAlign: 'left', fontWeight: 600, fontSize: '0.85rem' }}>Status</th>
                <th style={{ padding: '0.6rem 0.8rem', textAlign: 'left', fontWeight: 600, fontSize: '0.85rem' }}>Rate</th>
              </tr>
            </thead>
            <tbody>
              {obligations.map((o, idx) => (
                <tr key={idx} style={{ borderBottom: '1px solid var(--border)' }}>
                  <td style={{ padding: '0.55rem 0.8rem', fontSize: '0.85rem' }}><strong>{o.tax_name}</strong></td>
                  <td style={{ padding: '0.55rem 0.8rem', fontSize: '0.85rem' }}>{o.frequency}</td>
                  <td style={{ padding: '0.55rem 0.8rem', fontSize: '0.85rem' }}>{o.next_deadline || '-'}</td>
                  <td style={{ padding: '0.55rem 0.8rem', fontSize: '0.85rem' }}>{o.days_until_deadline != null ? `${o.days_until_deadline}d` : '-'}</td>
                  <td style={{ padding: '0.55rem 0.8rem', fontSize: '0.85rem' }}>
                    <span style={{ 
                      padding: '3px 10px', 
                      borderRadius: '12px', 
                      fontSize: '0.75rem', 
                      fontWeight: 600,
                      background: `${oblStatusColors[o.status] || 'var(--text-muted)'}20`,
                      color: oblStatusColors[o.status] || 'var(--text-muted)'
                    }}>
                      {o.status || 'unknown'}
                    </span>
                  </td>
                  <td style={{ padding: '0.55rem 0.8rem', fontSize: '0.85rem' }}>{o.rate || '-'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <div className="empty">No obligations data available</div>
        )}
      </div>

      <div className="section" style={{ marginBottom: '1.5rem' }}>
        <h3 style={{ marginBottom: '0.75rem', color: 'var(--primary)' }}>Risk Factors</h3>
        {risk.factors && risk.factors.length > 0 ? (
          <ul style={{ listStyle: 'none', padding: 0 }}>
            {risk.factors.map((f, idx) => (
              <li key={idx} style={{ padding: '0.3rem 0', fontSize: '0.85rem', color: 'var(--text-muted)' }}>
                • {f}
              </li>
            ))}
          </ul>
        ) : (
          <div style={{ color: 'var(--text-muted)', fontSize: '0.85rem' }}>No risk factors identified</div>
        )}
      </div>

      {/* KRA Shuru WhatsApp Section */}
      <div className="section" style={{ marginBottom: '1.5rem' }}>
        <h3 style={{ marginBottom: '0.75rem', color: 'var(--primary)', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          <MessageCircle size={18} />
          Pay via KRA WhatsApp (Shuru)
        </h3>
        <div style={{
          background: 'var(--bg-card)',
          border: '1px solid var(--border)',
          borderRadius: '8px',
          padding: '1.25rem'
        }}>
          <p style={{ margin: '0 0 1rem', fontSize: '0.9rem', color: 'var(--text-muted)' }}>
            File returns, pay taxes, and get compliance certificates in 3 easy steps via KRA's official WhatsApp bot.
          </p>

          <div style={{ display: 'flex', gap: '0.75rem', flexWrap: 'wrap', marginBottom: '1.25rem' }}>
            <a
              href={shuru?.links?.filing?.deeplink || 'https://wa.me/254711099999'}
              target="_blank"
              rel="noopener noreferrer"
              style={{
                display: 'inline-flex', alignItems: 'center', gap: '0.5rem',
                padding: '0.6rem 1.2rem', background: '#25D366', color: '#fff',
                borderRadius: '8px', textDecoration: 'none', fontWeight: 600, fontSize: '0.85rem'
              }}
            >
              <MessageCircle size={16} />
              File Returns
              <ExternalLink size={14} />
            </a>
            <a
              href={shuru?.links?.payment?.deeplink || 'https://wa.me/254711099999'}
              target="_blank"
              rel="noopener noreferrer"
              style={{
                display: 'inline-flex', alignItems: 'center', gap: '0.5rem',
                padding: '0.6rem 1.2rem', background: '#128C7E', color: '#fff',
                borderRadius: '8px', textDecoration: 'none', fontWeight: 600, fontSize: '0.85rem'
              }}
            >
              <DollarSign size={16} />
              Pay Taxes
              <ExternalLink size={14} />
            </a>
            <a
              href={shuru?.links?.compliance_certificate?.deeplink || 'https://wa.me/254711099999'}
              target="_blank"
              rel="noopener noreferrer"
              style={{
                display: 'inline-flex', alignItems: 'center', gap: '0.5rem',
                padding: '0.6rem 1.2rem', background: '#075E54', color: '#fff',
                borderRadius: '8px', textDecoration: 'none', fontWeight: 600, fontSize: '0.85rem'
              }}
            >
              <Calendar size={16} />
              Compliance Cert
              <ExternalLink size={14} />
            </a>
          </div>

          {shuru?.instructions?.steps && (
            <div style={{ fontSize: '0.85rem' }}>
              <strong style={{ display: 'block', marginBottom: '0.5rem' }}>How to use:</strong>
              <ol style={{ margin: 0, paddingLeft: '1.25rem', color: 'var(--text-muted)' }}>
                {shuru.instructions.steps.map((step, i) => (
                  <li key={i} style={{ marginBottom: '0.3rem' }}>{step}</li>
                ))}
              </ol>
            </div>
          )}

          <div style={{
            marginTop: '1rem', padding: '0.5rem 0.75rem',
            background: 'rgba(37, 211, 102, 0.1)', borderRadius: '6px',
            fontSize: '0.8rem', color: 'var(--text-muted)'
          }}>
            Official KRA WhatsApp: <strong>+254 711 099 999</strong> (Shuru)
          </div>
        </div>
      </div>

      <div style={{
        marginTop: '2rem',
        padding: '1rem',
        background: '#fff8e1',
        borderLeft: '4px solid #ffc107',
        borderRadius: '4px',
        fontSize: '0.75rem',
        color: '#666'
      }}>
        DISCLAIMER: This information is generated by an automated system for guidance purposes only.
        It does NOT constitute legal, tax, or financial advice. Always verify with KRA or a registered tax advisor.
      </div>
    </div>
  );
}