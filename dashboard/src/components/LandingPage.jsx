import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Shield, CheckCircle, Clock, AlertTriangle, MessageCircle, ArrowRight, Phone } from 'lucide-react';

const INDUSTRIES = [
  { value: 'retail_wholesale', label: 'Retail / Wholesale' },
  { value: 'professional_services', label: 'Professional Services' },
  { value: 'food_hospitality', label: 'Food & Hospitality' },
  { value: 'transport', label: 'Transport' },
  { value: 'manufacturing', label: 'Manufacturing' },
  { value: 'rental_income', label: 'Rental Income' },
  { value: 'digital_online', label: 'Digital / Online' },
  { value: 'construction', label: 'Construction' },
  { value: 'agriculture', label: 'Agriculture' },
  { value: 'salon_beauty', label: 'Salon & Beauty' },
  { value: 'education', label: 'Education' },
  { value: 'healthcare', label: 'Healthcare' },
];

const TURNOVER_BRACKETS = [
  { value: 'below_1m', label: 'Below KES 1M' },
  { value: '1m_to_8m', label: 'KES 1M - 8M' },
  { value: '8m_to_25m', label: 'KES 8M - 25M' },
  { value: 'above_25m', label: 'Above KES 25M' },
];

export default function LandingPage() {
  const navigate = useNavigate();
  const [showForm, setShowForm] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [form, setForm] = useState({
    pin: '',
    name: '',
    business_name: '',
    business_type: 'sole_proprietor',
    industry: 'retail_wholesale',
    county: 'Nairobi',
    annual_turnover_kes: 0,
    turnover_bracket: 'below_1m',
    has_employees: false,
    employee_count: 0,
    is_vat_registered: false,
    has_etims: false,
    phone: '',
    email: '',
    preferred_language: 'en',
  });

  const handleChange = (e) => {
    const { name, value, type, checked } = e.target;
    setForm(prev => ({
      ...prev,
      [name]: type === 'checkbox' ? checked : value,
    }));
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError('');

    try {
      const res = await fetch('/signup', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          ...form,
          annual_turnover_kes: Number(form.annual_turnover_kes),
          employee_count: Number(form.employee_count),
        }),
      });
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || 'Signup failed');
      }
      navigate(`/welcome/${data.pin}`, { state: data });
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="landing">
      {/* Hero */}
      <div className="landing-hero">
        <div className="hero-badge">
          <Shield size={20} />
          KRA HELMET
        </div>
        <h1 className="hero-title">
          Never Miss a Tax Deadline Again
        </h1>
        <p className="hero-subtitle">
          KRA Helmet tracks your tax obligations, warns you before deadlines,
          calculates penalties, and sends reports straight to your WhatsApp.
        </p>
        <div className="hero-features">
          <div className="hero-feature">
            <CheckCircle size={18} className="feature-icon green" />
            <span>Know exactly what taxes you owe</span>
          </div>
          <div className="hero-feature">
            <Clock size={18} className="feature-icon yellow" />
            <span>Get reminded 7 days before every deadline</span>
          </div>
          <div className="hero-feature">
            <AlertTriangle size={18} className="feature-icon red" />
            <span>See penalty exposure before it hits</span>
          </div>
          <div className="hero-feature">
            <MessageCircle size={18} className="feature-icon whatsapp" />
            <span>Full reports delivered to your WhatsApp</span>
          </div>
        </div>
        {!showForm && (
          <button className="hero-cta" onClick={() => setShowForm(true)}>
            Get Started Free <ArrowRight size={18} />
          </button>
        )}
        <p className="hero-trial">7-day free trial. Then KES 500/month via M-Pesa.</p>
      </div>

      {/* Signup Form */}
      {showForm && (
        <div className="signup-section" id="signup">
          <div className="signup-card">
            <h2 className="signup-title">Sign Up Your Business</h2>
            <p className="signup-subtitle">
              Fill in your details below. You'll start a 7-day free trial immediately.
            </p>

            {error && <div className="form-error">{error}</div>}

            <form onSubmit={handleSubmit} className="signup-form">
              {/* Required fields */}
              <div className="form-row">
                <div className="form-group">
                  <label>KRA PIN *</label>
                  <input
                    name="pin" value={form.pin} onChange={handleChange}
                    placeholder="e.g. A123456789B" required
                    pattern="^[A-Za-z]\d{9}[A-Za-z]$"
                    title="KRA PIN: 1 letter + 9 digits + 1 letter"
                  />
                </div>
                <div className="form-group">
                  <label>Your Name *</label>
                  <input
                    name="name" value={form.name} onChange={handleChange}
                    placeholder="Full name" required
                  />
                </div>
              </div>

              <div className="form-row">
                <div className="form-group">
                  <label>Business Name</label>
                  <input
                    name="business_name" value={form.business_name} onChange={handleChange}
                    placeholder="Optional — defaults to your name"
                  />
                </div>
                <div className="form-group">
                  <label>Phone (M-Pesa / WhatsApp) *</label>
                  <input
                    name="phone" value={form.phone} onChange={handleChange}
                    placeholder="e.g. 0712345678" required
                  />
                </div>
              </div>

              <div className="form-row">
                <div className="form-group">
                  <label>Business Type</label>
                  <select name="business_type" value={form.business_type} onChange={handleChange}>
                    <option value="sole_proprietor">Sole Proprietor</option>
                    <option value="partnership">Partnership</option>
                    <option value="limited_company">Limited Company</option>
                  </select>
                </div>
                <div className="form-group">
                  <label>Industry</label>
                  <select name="industry" value={form.industry} onChange={handleChange}>
                    {INDUSTRIES.map(i => (
                      <option key={i.value} value={i.value}>{i.label}</option>
                    ))}
                  </select>
                </div>
              </div>

              <div className="form-row">
                <div className="form-group">
                  <label>Annual Turnover</label>
                  <select name="turnover_bracket" value={form.turnover_bracket} onChange={handleChange}>
                    {TURNOVER_BRACKETS.map(b => (
                      <option key={b.value} value={b.value}>{b.label}</option>
                    ))}
                  </select>
                </div>
                <div className="form-group">
                  <label>County</label>
                  <input
                    name="county" value={form.county} onChange={handleChange}
                    placeholder="e.g. Nairobi"
                  />
                </div>
              </div>

              <div className="form-row">
                <div className="form-group">
                  <label>Email</label>
                  <input
                    name="email" value={form.email} onChange={handleChange}
                    placeholder="Optional" type="email"
                  />
                </div>
                <div className="form-group">
                  <label>Language</label>
                  <select name="preferred_language" value={form.preferred_language} onChange={handleChange}>
                    <option value="en">English</option>
                    <option value="sw">Swahili</option>
                  </select>
                </div>
              </div>

              <div className="form-row checkboxes">
                <label className="checkbox-label">
                  <input type="checkbox" name="has_employees" checked={form.has_employees} onChange={handleChange} />
                  Has employees
                </label>
                {form.has_employees && (
                  <div className="form-group inline">
                    <label>How many?</label>
                    <input
                      name="employee_count" type="number" min="1"
                      value={form.employee_count} onChange={handleChange}
                      style={{ width: '80px' }}
                    />
                  </div>
                )}
                <label className="checkbox-label">
                  <input type="checkbox" name="is_vat_registered" checked={form.is_vat_registered} onChange={handleChange} />
                  VAT Registered
                </label>
                <label className="checkbox-label">
                  <input type="checkbox" name="has_etims" checked={form.has_etims} onChange={handleChange} />
                  Has eTIMS
                </label>
              </div>

              <button type="submit" className="hero-cta submit-btn" disabled={loading}>
                {loading ? 'Signing up...' : 'Start Free Trial'}
                {!loading && <ArrowRight size={18} />}
              </button>
            </form>
          </div>
        </div>
      )}

      {/* Pricing Section */}
      <div className="pricing-section">
        <h2 className="section-title">Simple Pricing</h2>
        <div className="pricing-grid">
          <div className="price-card trial">
            <div className="price-badge">FREE</div>
            <h3>Trial</h3>
            <div className="price-amount">KES 0</div>
            <div className="price-period">7 days</div>
            <ul className="price-features">
              <li><CheckCircle size={14} /> Full compliance report</li>
              <li><CheckCircle size={14} /> Obligation mapping</li>
              <li><CheckCircle size={14} /> Risk scoring</li>
              <li><CheckCircle size={14} /> WhatsApp alerts</li>
            </ul>
          </div>
          <div className="price-card popular">
            <div className="price-badge">POPULAR</div>
            <h3>Monthly</h3>
            <div className="price-amount">KES 500</div>
            <div className="price-period">per month</div>
            <ul className="price-features">
              <li><CheckCircle size={14} /> Everything in Trial</li>
              <li><CheckCircle size={14} /> Deadline alerts via WhatsApp</li>
              <li><CheckCircle size={14} /> Penalty warnings</li>
              <li><CheckCircle size={14} /> Filing guides</li>
            </ul>
          </div>
          <div className="price-card">
            <h3>Quarterly</h3>
            <div className="price-amount">KES 1,200</div>
            <div className="price-period">3 months (save 20%)</div>
            <ul className="price-features">
              <li><CheckCircle size={14} /> Everything in Monthly</li>
              <li><CheckCircle size={14} /> Priority support</li>
            </ul>
          </div>
          <div className="price-card">
            <h3>Annual</h3>
            <div className="price-amount">KES 4,000</div>
            <div className="price-period">12 months (save 33%)</div>
            <ul className="price-features">
              <li><CheckCircle size={14} /> Everything in Monthly</li>
              <li><CheckCircle size={14} /> Priority support</li>
            </ul>
          </div>
        </div>
        <div className="payment-note">
          <Phone size={16} />
          Pay via M-Pesa to <strong>0114179880</strong>
        </div>
      </div>
    </div>
  );
}
