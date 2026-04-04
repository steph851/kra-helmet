import { useParams, useLocation, useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { CheckCircle, Clock, Phone, MessageCircle, Copy, ArrowRight, Shield, RefreshCw } from 'lucide-react';
import { useState } from 'react';

export default function WelcomePage() {
  const { pin } = useParams();
  const location = useLocation();
  const navigate = useNavigate();
  const signupData = location.state;
  const [copied, setCopied] = useState('');

  const { data: sub, isLoading, refetch } = useQuery({
    queryKey: ['subscription', pin],
    queryFn: async () => {
      const res = await fetch(`/subscription/${pin}`);
      if (!res.ok) throw new Error('Not found');
      return res.json();
    },
    refetchInterval: 30000,
  });

  const { data: plans } = useQuery({
    queryKey: ['plans'],
    queryFn: async () => {
      const res = await fetch('/plans');
      return res.json();
    },
  });

  const copyText = (text, label) => {
    navigator.clipboard.writeText(text);
    setCopied(label);
    setTimeout(() => setCopied(''), 2000);
  };

  const isActive = sub?.active;
  const subscription = sub?.subscription || signupData?.subscription;
  const payment = sub?.payment || signupData?.payment;
  const daysLeft = subscription ? Math.max(0, Math.ceil(
    (new Date(subscription.expires_at) - new Date()) / (1000 * 60 * 60 * 24)
  )) : 0;

  return (
    <div className="landing">
      <div className="welcome-container">
        {/* Status Banner */}
        <div className={`welcome-banner ${isActive ? 'active' : 'expired'}`}>
          <div className="banner-icon">
            {isActive ? <CheckCircle size={32} /> : <Clock size={32} />}
          </div>
          <div>
            <h1 className="welcome-title">
              {signupData && !sub ? 'Welcome to KRA Deadline Tracker!' :
               isActive ? 'Your Subscription is Active' : 'Subscription Expired'}
            </h1>
            <p className="welcome-subtitle">
              {isActive
                ? `${subscription?.plan_name || 'Trial'} plan — ${daysLeft} day${daysLeft !== 1 ? 's' : ''} remaining`
                : 'Pay via M-Pesa to continue receiving WhatsApp reports'}
            </p>
          </div>
        </div>

        {/* What you get */}
        {signupData && (
          <div className="welcome-card">
            <h2>Your Tax Obligations</h2>
            <p style={{ color: 'var(--text-muted)', marginBottom: '1rem' }}>
              Based on your business profile, here's what KRA Deadline Tracker tracks for you:
            </p>
            <div className="obligation-tags">
              {(signupData.obligations || []).map(ob => (
                <span key={ob} className="ob-tag">{ob.replace(/_/g, ' ')}</span>
              ))}
            </div>
          </div>
        )}

        {/* Subscription details */}
        <div className="welcome-card">
          <div className="card-header">
            <h2>Subscription</h2>
            <button className="refresh-btn" onClick={() => refetch()} title="Refresh">
              <RefreshCw size={16} />
            </button>
          </div>
          <div className="sub-details">
            <div className="sub-row">
              <span className="sub-label">PIN</span>
              <span className="sub-value mono">{pin}</span>
            </div>
            <div className="sub-row">
              <span className="sub-label">Plan</span>
              <span className="sub-value">{subscription?.plan_name || 'None'}</span>
            </div>
            <div className="sub-row">
              <span className="sub-label">Status</span>
              <span className={`status-pill ${isActive ? 'active' : 'expired'}`}>
                {isActive ? 'Active' : subscription?.status || 'Inactive'}
              </span>
            </div>
            <div className="sub-row">
              <span className="sub-label">Expires</span>
              <span className="sub-value">
                {subscription?.expires_at
                  ? new Date(subscription.expires_at).toLocaleDateString('en-KE', { dateStyle: 'medium' })
                  : '—'}
              </span>
            </div>
            {subscription?.amount_paid_kes > 0 && (
              <div className="sub-row">
                <span className="sub-label">Total Paid</span>
                <span className="sub-value">KES {subscription.amount_paid_kes.toLocaleString()}</span>
              </div>
            )}
          </div>
        </div>

        {/* M-Pesa Payment Instructions */}
        {(!isActive || daysLeft <= 7) && (
          <div className="welcome-card payment-card">
            <h2>
              <Phone size={20} />
              {isActive ? 'Renew via M-Pesa' : 'Pay via M-Pesa to Activate'}
            </h2>

            {/* Plan selection */}
            <div className="plan-selector">
              {plans?.plans && Object.entries(plans.plans).map(([key, plan]) => (
                <div key={key} className={`plan-option ${key === 'monthly' ? 'recommended' : ''}`}>
                  <div className="plan-name">{plan.name}</div>
                  <div className="plan-price">KES {plan.price_kes.toLocaleString()}</div>
                  <div className="plan-duration">{plan.duration_days} days</div>
                </div>
              ))}
            </div>

            <div className="mpesa-steps">
              <div className="mpesa-step">
                <span className="step-num">1</span>
                <span>Open <strong>M-Pesa</strong> on your phone</span>
              </div>
              <div className="mpesa-step">
                <span className="step-num">2</span>
                <span>Select <strong>Send Money</strong></span>
              </div>
              <div className="mpesa-step">
                <span className="step-num">3</span>
                <div>
                  Enter number: <strong className="copy-target" onClick={() => copyText('0114179880', 'number')}>
                    0114179880 {copied === 'number' ? <CheckCircle size={14} /> : <Copy size={14} />}
                  </strong>
                </div>
              </div>
              <div className="mpesa-step">
                <span className="step-num">4</span>
                <span>Enter amount: <strong>KES 500</strong> (monthly)</span>
              </div>
              <div className="mpesa-step">
                <span className="step-num">5</span>
                <div>
                  In reference, type: <strong className="copy-target" onClick={() => copyText(`KRADTC-${pin}`, 'ref')}>
                    KRADTC-{pin} {copied === 'ref' ? <CheckCircle size={14} /> : <Copy size={14} />}
                  </strong>
                </div>
              </div>
              <div className="mpesa-step">
                <span className="step-num">6</span>
                <span>Enter your M-Pesa PIN and confirm</span>
              </div>
            </div>

            <div className="mpesa-note">
              Your subscription activates once payment is confirmed. This usually takes a few minutes.
            </div>
          </div>
        )}

        {/* What happens next */}
        <div className="welcome-card">
          <h2><MessageCircle size={20} /> What Happens Next</h2>
          <div className="next-steps">
            <div className="next-step">
              <div className="next-icon green"><CheckCircle size={18} /></div>
              <div>
                <strong>Compliance report generated</strong>
                <p>We map all your tax obligations based on your business profile</p>
              </div>
            </div>
            <div className="next-step">
              <div className="next-icon blue"><Clock size={18} /></div>
              <div>
                <strong>Deadline alerts via WhatsApp</strong>
                <p>You'll get notified 7 days, 3 days, and 1 day before each deadline</p>
              </div>
            </div>
            <div className="next-step">
              <div className="next-icon yellow"><Shield size={18} /></div>
              <div>
                <strong>Risk scoring & penalty warnings</strong>
                <p>Know your audit risk and exact penalty exposure in KES</p>
              </div>
            </div>
            <div className="next-step">
              <div className="next-icon whatsapp"><MessageCircle size={18} /></div>
              <div>
                <strong>File via KRA Shuru</strong>
                <p>Use KRA's WhatsApp bot to file returns and pay taxes directly</p>
              </div>
            </div>
          </div>
        </div>

        <div className="welcome-footer">
          <a href="https://wa.me/254711099999" target="_blank" rel="noopener noreferrer" className="shuru-link">
            <MessageCircle size={16} />
            File taxes via KRA Shuru WhatsApp
          </a>
        </div>
      </div>
    </div>
  );
}
