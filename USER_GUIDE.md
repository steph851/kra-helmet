# KRA HELMET — User Guide

## How to Use KRA HELMET

KRA HELMET is a tax compliance autopilot for Kenyan SMEs. Here's how to use it:

---

## 🚀 Quick Start

### 1. Install & Run

```bash
# Clone the repository
git clone <your-repo-url>
cd kra-helmet

# Install dependencies
pip install -r requirements.txt

# Start the API server (includes dashboard)
python run.py api
```

Then open **http://localhost:8000** in your browser to see the dashboard.

---

## 📱 Three Ways to Use KRA HELMET

### Option 1: Web Dashboard (Easiest)

Open http://localhost:8000 in your browser. The dashboard shows:
- **Overview** — Total SMEs, compliance status, risk scores
- **Quick Actions** — Run checks, view reports, check monitoring
- **SME Management** — Add, search, view SMEs
- **Recent Activity** — What's happened recently
- **Proactive Recommendations** — AI suggestions to prevent problems
- **System Status** — API, database, scheduler, monitoring health

### option 2: Command Line (Power Users)

```bash
# Onboard a new SME
python run.py onboard

# Check compliance for one SME
python run.py check A000000001B

# Check all SMEs
python run.py check --all

# View system status
python run.py status

# Start the background scheduler
python run.py pulse

# Run monitoring scan
python run.py eyes

# Generate reports
python run.py report A000000001B
python run.py report --all

# View audit trail
python run.py audit
```

### option 3: REST API (For Integration)

```bash
# Start the API
python run.py api

# Then call endpoints:
curl http://localhost:8000/api/stats
curl http://localhost:8000/api/smes
curl http://localhost:8000/check/A000000001B
curl http://localhost:8000/api/proactive
```

Full API docs at: http://localhost:8000/docs

---

## 🤖 The Autonomous Agents

KRA HELMET uses 5 autonomous agent systems:

### 1. The Pulse (Scheduler)
**What it does:** Automatically checks compliance on schedule
**How to use:**
```bash
python run.py pulse          # Start background scheduler
python run.py pulse --once   # Run one check cycle
python run.py pulse --status # See what's happening
```

### 2. The Eyes (Monitoring)
**What it does:** Watches KRA website, Kenya Gazette, eTIMS for changes
**How to use:**
```bash
python run.py eyes              # Full scan
python run.py eyes --kra        # Just KRA announcements
python run.py eyes --gazette    # Just Kenya Gazette
python run.py eyes --etims      # Just eTIMS compliance
python run.py eyes --health     # Check if sources are reachable
```

### 3. The Brain (Learning)
**What it does:** Learns from outcomes, finds patterns, improves risk model
**How to use:**
```bash
python run.py brain              # Full analysis
python run.py brain --patterns   # Find compliance patterns
python run.py brain --feedback   # Check prediction accuracy
python run.py brain --propose    # Propose model improvements
python run.py brain --timeline A000000001B  # See SME history
```

### 4. The Hands (Actions)
**What it does:** Takes action — sends alerts, prepares filings, escalates
**How to use:**
```bash
python run.py actions A000000001B  # Get action list for SME
python run.py prepare A000000001B  # Prepare filing package
python run.py deliver              # Send pending alerts
python run.py escalate             # Check for escalations
```

### 5. The Voice (Communication)
**What it does:** Sends WhatsApp, SMS, email alerts
**How to use:**
```bash
python run.py deliver  # Process and send all pending alerts
```

---

## 📊 Understanding the Dashboard

### Stats Overview
- **Total SMEs** — How many businesses you're tracking
- **Compliant** — All obligations met
- **At Risk** — Deadlines approaching (within 7 days)
- **Non-Compliant** — Overdue filings

### Proactive Recommendations (🤖)
The AI analyzes patterns and suggests actions:
- **Autonomous (🤖)** — Low-risk actions taken automatically
- **Requires Human (👤)** — Needs your approval

### Risk Score
- **0-25** — Low risk (green)
- **26-50** — Medium risk (yellow)
- **51-75** — High risk (orange)
- **76-100** — Critical risk (red)

---

## 🔧 Configuration

### Environment Variables (.env file)

```bash
# API Authentication
HELMET_API_KEY=your-secret-key

# Claude AI (optional — for advanced features)
ANTHROPIC_API_KEY=your-claude-key

# M-Pesa (for payment integration)
MPESA_CONSUMER_KEY=your-key
MPESA_CONSUMER_SECRET=your-secret
MPESA_SHORTCODE=your-shortcode
MPESA_PASSKEY=your-passkey

# WhatsApp (for alerts)
WHATSAPP_API_KEY=your-key
WHATSAPP_PHONE_NUMBER_ID=your-id

# SMS (for alerts)
SMS_API_KEY=your-key
SMS_SENDER_ID=your-sender

# Email (for alerts)
EMAIL_SMTP_HOST=smtp.gmail.com
EMAIL_SMTP_USER=your-email
EMAIL_SMTP_PASSWORD=your-password
```

### Settings (config/settings.json)

All tunable values are in `config/settings.json`:
- Risk weights
- Penalty amounts
- Alert limits
- Scheduler intervals
- Confidence thresholds

---

## 📋 Common Workflows

### Workflow 1: New SME Onboarding

```bash
# 1. Onboard the SME
python run.py onboard

# 2. Check their compliance
python run.py check <PIN>

# 3. View their action list
python run.py actions <PIN>

# 4. Prepare their filing
python run.py prepare <PIN>
```

### Workflow 2: Daily Monitoring

```bash
# 1. Start the scheduler (runs in background)
python run.py pulse

# 2. Check what happened
python run.py status

# 3. Review any escalations
python run.py review

# 4. Send alerts
python run.py deliver
```

### Workflow 3: Monthly Reporting

```bash
# 1. Check all SMEs
python run.py check --all

# 2. Generate all reports
python run.py report --all

# 3. View dashboard
python run.py dashboard

# 4. Run learning analysis
python run.py brain
```

### Workflow 4: API Integration

```python
import requests

# Get all SMEs
smes = requests.get("http://localhost:8000/api/smes").json()

# Check one SME
result = requests.get("http://localhost:8000/check/A000000001B").json()

# Get proactive recommendations
recs = requests.get("http://localhost:8000/api/proactive").json()

# Run compliance check
requests.post("http://localhost:8000/api/check")
```

---

## 🐳 Docker Deployment

```bash
# Build the image
docker build -t kra-helmet .

# Run with environment variables
docker run -p 8000:8000 \
  -e HELMET_API_KEY=your-key \
  -e ANTHROPIC_API_KEY=your-claude-key \
  -v kra-data:/app/data \
  kra-helmet

# Or use docker-compose
docker-compose up -d
```

---

## 🔒 Security Notes

1. **Always set HELMET_API_KEY** in production
2. **Use HTTPS** in production (add nginx/caddy reverse proxy)
3. **Encrypt sensitive data** using the security module
4. **Review audit trail** regularly: `python run.py audit`
5. **Back up your data** directory regularly

---

## 🆘 Troubleshooting

### "Module not found" errors
```bash
pip install -r requirements.txt
```

### API won't start
```bash
# Check if port 8000 is in use
lsof -i :8000  # Mac/Linux
netstat -ano | findstr :8000  # Windows

# Use a different port
python run.py api --port 8080
```

### Dashboard not loading
- Make sure you're accessing http://localhost:8000 (not 127.0.0.1)
- Check browser console for errors
- Verify API is running: curl http://localhost:8000/health

### Tests failing
```bash
# Reinstall dependencies
pip install -r requirements.txt --force-reinstall

# Run tests
python -m pytest tests/ -v
```

---

## 📞 Support

- **Documentation:** See `docs/API.md` for full API reference
- **Issues:** Check `logs/` directory for error details
- **Audit:** Use `python run.py audit` to see what happened

---

**KRA HELMET** — Protecting Kenyan SMEs from tax penalties 🛡️
