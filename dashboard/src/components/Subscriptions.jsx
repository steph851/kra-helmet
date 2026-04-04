import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { CreditCard, CheckCircle, XCircle, Clock, RefreshCw, Plus } from 'lucide-react';

const API_BASE = '/api';

export default function Subscriptions() {
  const queryClient = useQueryClient();
  const [showConfirm, setShowConfirm] = useState(false);
  const [confirmForm, setConfirmForm] = useState({
    pin: '', mpesa_ref: '', amount_kes: 500, plan: 'monthly', phone: '',
  });
  const [msg, setMsg] = useState('');

  const { data, isLoading, refetch } = useQuery({
    queryKey: ['subscriptions'],
    queryFn: async () => {
      const res = await fetch(`${API_BASE}/subscriptions`);
      return res.json();
    },
    refetchInterval: 30000,
  });

  const confirmMutation = useMutation({
    mutationFn: async (payload) => {
      const res = await fetch(`${API_BASE}/subscriptions/confirm`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      if (!res.ok) throw new Error((await res.json()).detail || 'Failed');
      return res.json();
    },
    onSuccess: () => {
      setMsg('Payment confirmed!');
      setShowConfirm(false);
      setConfirmForm({ pin: '', mpesa_ref: '', amount_kes: 500, plan: 'monthly', phone: '' });
      queryClient.invalidateQueries(['subscriptions']);
      setTimeout(() => setMsg(''), 3000);
    },
    onError: (err) => setMsg(`Error: ${err.message}`),
  });

  const deactivateMutation = useMutation({
    mutationFn: async (pin) => {
      const res = await fetch(`${API_BASE}/subscriptions/${pin}/deactivate`, { method: 'POST' });
      if (!res.ok) throw new Error((await res.json()).detail || 'Failed');
      return res.json();
    },
    onSuccess: () => {
      queryClient.invalidateQueries(['subscriptions']);
      setMsg('Subscription deactivated');
      setTimeout(() => setMsg(''), 3000);
    },
  });

  const subs = data?.subscriptions || [];
  const active = subs.filter(s => s.status === 'active');
  const expired = subs.filter(s => s.status !== 'active');

  return (
    <div>
      {/* Stats */}
      <div className="stats-grid" style={{ marginBottom: '1.5rem' }}>
        <div className="stat-card">
          <div className="stat-value">{data?.total || 0}</div>
          <div className="stat-label">Total Subscribers</div>
        </div>
        <div className="stat-card compliant">
          <div className="stat-value" style={{ color: 'var(--success)' }}>{data?.active || 0}</div>
          <div className="stat-label">Active</div>
        </div>
        <div className="stat-card non-compliant">
          <div className="stat-value" style={{ color: 'var(--danger)' }}>{data?.expired || 0}</div>
          <div className="stat-label">Expired / Cancelled</div>
        </div>
      </div>

      {msg && (
        <div className="form-success" style={{ marginBottom: '1rem', padding: '0.75rem 1rem', background: 'rgba(34,197,94,0.1)', border: '1px solid var(--success)', borderRadius: '8px', color: 'var(--success)' }}>
          {msg}
        </div>
      )}

      {/* Actions */}
      <div style={{ display: 'flex', gap: '0.75rem', marginBottom: '1.5rem' }}>
        <button className="btn btn-primary" onClick={() => setShowConfirm(!showConfirm)}>
          <Plus size={16} style={{ marginRight: '0.5rem', verticalAlign: 'middle' }} />
          Confirm Payment
        </button>
        <button className="btn" onClick={() => refetch()} style={{ background: 'var(--bg-elevated)', color: 'var(--text)' }}>
          <RefreshCw size={16} style={{ marginRight: '0.5rem', verticalAlign: 'middle' }} />
          Refresh
        </button>
      </div>

      {/* Confirm Payment Form */}
      {showConfirm && (
        <div className="stat-card" style={{ marginBottom: '1.5rem' }}>
          <h3 style={{ marginBottom: '1rem' }}>
            <CreditCard size={18} style={{ marginRight: '0.5rem', verticalAlign: 'middle' }} />
            Confirm M-Pesa Payment
          </h3>
          <form onSubmit={(e) => { e.preventDefault(); confirmMutation.mutate(confirmForm); }}
                className="signup-form" style={{ maxWidth: '100%' }}>
            <div className="form-row">
              <div className="form-group">
                <label>KRA PIN</label>
                <input value={confirmForm.pin}
                  onChange={e => setConfirmForm(p => ({ ...p, pin: e.target.value }))}
                  placeholder="A123456789B" required />
              </div>
              <div className="form-group">
                <label>M-Pesa Reference</label>
                <input value={confirmForm.mpesa_ref}
                  onChange={e => setConfirmForm(p => ({ ...p, mpesa_ref: e.target.value }))}
                  placeholder="e.g. SLK1234567" required />
              </div>
            </div>
            <div className="form-row">
              <div className="form-group">
                <label>Amount (KES)</label>
                <input type="number" value={confirmForm.amount_kes}
                  onChange={e => setConfirmForm(p => ({ ...p, amount_kes: Number(e.target.value) }))}
                  required />
              </div>
              <div className="form-group">
                <label>Plan</label>
                <select value={confirmForm.plan}
                  onChange={e => setConfirmForm(p => ({ ...p, plan: e.target.value }))}>
                  <option value="monthly">Monthly (KES 500)</option>
                  <option value="quarterly">Quarterly (KES 1,200)</option>
                  <option value="annual">Annual (KES 4,000)</option>
                </select>
              </div>
              <div className="form-group">
                <label>Phone</label>
                <input value={confirmForm.phone}
                  onChange={e => setConfirmForm(p => ({ ...p, phone: e.target.value }))}
                  placeholder="0712345678" />
              </div>
            </div>
            <button type="submit" className="btn btn-primary" disabled={confirmMutation.isPending}>
              {confirmMutation.isPending ? 'Confirming...' : 'Confirm Payment'}
            </button>
          </form>
        </div>
      )}

      {/* Active Subscriptions */}
      <h3 style={{ marginBottom: '0.75rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
        <CheckCircle size={18} style={{ color: 'var(--success)' }} />
        Active ({active.length})
      </h3>
      {active.length === 0 ? (
        <div className="empty" style={{ marginBottom: '1.5rem' }}>No active subscriptions</div>
      ) : (
        <div className="sme-grid" style={{ marginBottom: '1.5rem' }}>
          {active.map(s => (
            <SubCard key={s.pin} sub={s} onDeactivate={() => deactivateMutation.mutate(s.pin)} />
          ))}
        </div>
      )}

      {/* Expired */}
      {expired.length > 0 && (
        <>
          <h3 style={{ marginBottom: '0.75rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <XCircle size={18} style={{ color: 'var(--danger)' }} />
            Expired / Cancelled ({expired.length})
          </h3>
          <div className="sme-grid">
            {expired.map(s => <SubCard key={s.pin} sub={s} />)}
          </div>
        </>
      )}
    </div>
  );
}

function SubCard({ sub, onDeactivate }) {
  const daysLeft = Math.max(0, Math.ceil(
    (new Date(sub.expires_at) - new Date()) / (1000 * 60 * 60 * 24)
  ));

  return (
    <div className="sme-card" style={{ flexDirection: 'column', alignItems: 'stretch', gap: '0.5rem' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div className="sme-info">
          <span className="sme-name">{sub.name || sub.pin}</span>
          <span className="sme-pin">{sub.pin}</span>
        </div>
        <span className={`status-badge ${sub.status === 'active' ? 'compliant' : 'non-compliant'}`}>
          {sub.status}
        </span>
      </div>
      <div style={{ display: 'flex', gap: '1.5rem', fontSize: '0.8rem', color: 'var(--text-muted)' }}>
        <span>Plan: <strong style={{ color: 'var(--text)' }}>{sub.plan_name}</strong></span>
        {sub.status === 'active' && (
          <span>Expires: <strong style={{ color: daysLeft <= 3 ? 'var(--danger)' : 'var(--text)' }}>
            {daysLeft}d left
          </strong></span>
        )}
        <span>Paid: <strong style={{ color: 'var(--text)' }}>KES {(sub.amount_paid_kes || 0).toLocaleString()}</strong></span>
        <span>Payments: <strong style={{ color: 'var(--text)' }}>{(sub.payments || []).length}</strong></span>
      </div>
      {sub.status === 'active' && onDeactivate && (
        <button onClick={onDeactivate} className="btn"
          style={{ alignSelf: 'flex-end', background: 'rgba(239,68,68,0.1)', color: 'var(--danger)', fontSize: '0.75rem', padding: '0.3rem 0.75rem' }}>
          Deactivate
        </button>
      )}
    </div>
  );
}
