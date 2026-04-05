# KRA Deadline Tracker

**Tax Compliance Autopilot for Kenyan SMEs**

KRA Deadline Tracker figures out which taxes your business owes, tracks every deadline, calculates penalties if you're late, and tells you exactly how to file — on iTax or via KRA's WhatsApp bot (Shuru). Step by step.

Built for small business owners in Kenya who don't want to get surprised by KRA demand letters.

## What It Does

| Feature | Description |
|---|---|
| **Onboarding** | Tell it your business type, industry, turnover, employees — it maps your tax obligations |
| **Deadline Tracking** | Knows every filing date, adjusts for weekends and Kenya public holidays, warns 3 days early |
| **Risk Scoring** | 8-factor audit risk score (0-100) based on real KRA patterns |
| **Penalty Calculator** | Shows exact KES exposure if you're late (filing penalties + 1% monthly compound interest) |
| **Filing Guides** | Step-by-step iTax instructions for all 11 tax types |
| **Filing Tracker** | Record what you've filed, track compliance history |
| **Reports** | Professional HTML reports per SME — print-ready, shareable |
| **React Dashboard** | Dark-themed futuristic UI with system diagnostics, SME management, activity feed, and real-time status |
| **KRA Shuru Integration** | File returns, pay taxes, and get compliance certificates via KRA's WhatsApp bot (+254 711 099 999) |
| **Subscriptions** | Public signup with 7-day free trial, M-Pesa payments (0114179880), subscription gating on WhatsApp alerts |
| **Alerts** | WhatsApp/SMS/email messages with Shuru deep links, quiet hours, and rate limits — only for active subscribers |
| **Human Gate** | Low-confidence items routed to human review before proceeding |
| **Audit Trail** | Immutable JSONL log of every decision |
| **System Health** | Real-time diagnostics: API, database, scheduler (The Pulse), and monitoring (The Eyes) |

## Quick Start

### Option 1: Web Dashboard (Recommended)

```bash
# Clone
git clone https://github.com/steph851/kra-helmet.git
cd kra-helmet

# Install Python dependencies
pip install -r requirements.txt

# Build the React dashboard
cd dashboard && npm install && npx vite build && cd ..

# Start the web dashboard
python start_website.py
```

**Access from any device:**
- **This device:** http://localhost:8000
- **Other devices (phone/tablet):** http://YOUR_IP_ADDRESS:8000
- The script shows your IP address automatically

### Option 2: Command Line

```bash
# Configure
cp .env.example .env
# Edit .env with your ANTHROPIC_API_KEY (optional — system works without it)

# Run
python run.py demo          # Full end-to-end demo
python run.py onboard       # Onboard your business
python run.py check --all   # Check all SMEs
python run.py dashboard     # Generate HTML dashboard
```

## Web Dashboard (React)

KRA Deadline Tracker includes a futuristic React dashboard built with Vite, React Query, and Lucide icons:

- **Overview** — Stats cards, recent SMEs, activity feed, KRA Shuru WhatsApp quick action
- **SME Management** — Search, filter, and manage all onboarded SMEs
- **SME Detail** — Full profile, obligations table, risk factors, Shuru file/pay/cert buttons
- **Activity Feed** — Real-time log of all system activity
- **System Status** — Futuristic diagnostics with status ring, uptime counter, subsystem cards, and health checks
- **Reports** — Per-SME HTML compliance reports
- **Audit Trail** — Immutable decision log

**Tech stack:** React 18 + Vite + React Router + TanStack React Query + Lucide React

## KRA Shuru WhatsApp Integration

KRA launched **Shuru** (April 2026) — a WhatsApp chatbot that lets taxpayers file returns, pay taxes, and get compliance certificates in 3 steps.

KRA Deadline Tracker integrates Shuru throughout the system:

| Integration Point | What Happens |
|---|---|
| **Alerts (WhatsApp/SMS/Email)** | Every notification includes Shuru as a filing/payment option alongside iTax |
| **Recommendations** | Action lists include "File via WhatsApp" with deep links pre-filled with SME PIN |
| **Payment instructions** | Both M-Pesa paybill and Shuru WhatsApp payment option |
| **Dashboard — Overview** | Green Shuru banner with "Open Shuru" quick action |
| **Dashboard — SME Detail** | File Returns / Pay Taxes / Compliance Cert buttons that open WhatsApp |
| **API** | `GET /shuru/{pin}` returns deep links, instructions, and payment links |

**KRA Shuru number:** +254 711 099 999

## CLI Commands

```
python run.py onboard              # Interactive SME onboarding
python run.py import <csv_file>    # Batch import from CSV
python run.py import --template    # Generate CSV template
python run.py check <PIN>          # Full compliance check
python run.py check --all          # Check all SMEs
python run.py file <PIN>           # Record a tax filing (interactive)
python run.py filings <PIN>        # View filing history
python run.py status               # System status dashboard
python run.py review               # Human gate — approve/reject pending items
python run.py audit [PIN]          # View audit trail
python run.py guide --list         # List filing guides
python run.py guide <tax_type>     # Step-by-step filing instructions
python run.py report <PIN>         # Generate per-SME HTML report
python run.py report --all         # Generate all reports
python run.py dashboard            # Generate HTML dashboard
python run.py pulse                # Start The Pulse (background scheduler)
python run.py eyes                 # Run full monitoring scan (The Eyes)
python run.py actions <PIN>        # Show action list with Shuru links
python run.py brain                # Run Brain analysis (patterns + feedback)
python run.py api                  # Start REST API server
python run.py demo                 # Demo with sample SME
```

## REST API

```bash
python run.py api
# Opens at http://localhost:8000
# Swagger docs at http://localhost:8000/docs
```

**Endpoints:**

| Method | Path | Description |
|---|---|---|
| GET | `/health` | System health (API, database, scheduler, monitoring) |
| GET | `/smes` | List all SMEs |
| GET | `/smes/{pin}` | Get SME profile |
| POST | `/onboard` | Onboard new SME |
| GET | `/check/{pin}` | Run compliance check |
| GET | `/check` | Check all SMEs |
| POST | `/file/{pin}` | Record a filing |
| GET | `/filings/{pin}` | Filing history |
| GET | `/dashboard` | Live HTML dashboard |
| GET | `/report/{pin}` | Per-SME HTML report |
| GET | `/audit` | Audit trail |
| GET | `/guides` | List filing guides |
| GET | `/guides/{tax_key}` | Specific filing guide |
| GET | `/pulse` | Scheduler status |
| GET | `/eyes` | Monitoring status |
| GET | `/actions/{pin}` | Action list with Shuru + M-Pesa links |
| GET | `/shuru/{pin}` | KRA Shuru WhatsApp deep links and instructions |
| GET | `/shuru/{pin}/pay` | Shuru payment link with amount |
| GET | `/proactive/{pin}` | Proactive recommendations |
| POST | `/proactive/execute` | Execute autonomous action |
| POST | `/signup` | **Public** — Sign up SME + start free trial |
| GET | `/plans` | **Public** — List subscription plans and pricing |
| GET | `/subscription/{pin}` | **Public** — Check subscription status |
| GET | `/pay/{pin}` | **Public** — M-Pesa payment instructions |
| GET | `/api/subscriptions` | Admin — list all subscriptions |
| POST | `/api/subscriptions/confirm` | Admin — confirm M-Pesa payment |
| POST | `/api/subscriptions/{pin}/deactivate` | Admin — deactivate subscription |

**Authentication:** Set `HELMET_API_KEY` in `.env` and pass `X-API-Key` header. Public endpoints (`/signup`, `/plans`, `/subscription/*`, `/pay/*`) do not require auth.

## Architecture

Multi-agent system with a 9-step pipeline:

```
Onboard -> Map Obligations -> Calculate Deadlines -> Score Risk -> Check Compliance
    -> Calculate Penalties -> Validate Confidence -> Frame Urgency
    -> Queue Notifications -> Generate Explanation
```

Each agent has a single responsibility and a hard boundary — the obligation mapper can't send alerts, the penalty calculator can't score risk. The orchestrator coordinates everything with error recovery on every step.

```
agents/
  orchestrator.py           # 9-step pipeline with safe_run() error recovery
  onboarding/               # Profile builder, industry classifier, batch CSV import
  intelligence/             # Obligation mapper, deadlines, risk, compliance, penalties
  validation/               # Input validator, confidence engine, disclaimers
  communication/            # Explainer (EN/SW), urgency framer, notification engine
  monitoring/               # KRA monitor, gazette monitor, eTIMS monitor, source health
  action/                   # Alert engine, escalation, recommendations, workflow, proactive
  learning/                 # Decision memory, pattern miner, feedback loop, model updater
  dashboard.py              # HTML dashboard generator
  report_generator.py       # Per-SME HTML reports
```

### The Pulse (Scheduler)

Background scheduler that drives automated compliance monitoring:

```
scheduler/
  heartbeat.py              # Main loop: tick -> scan -> queue -> dispatch -> sleep
  trigger_engine.py         # Reads state, decides what needs checking
  priority_queue.py         # Urgency-ranked task queue (red/orange/yellow/green)
  event_listener.py         # Webhook handler for external events
  cron_config.json          # Check intervals and batch schedules
```

### The Eyes (Monitoring)

Watches external sources for tax changes:

```
agents/monitoring/
  monitoring_orchestrator.py  # Coordinates all monitors
  kra_monitor.py              # KRA announcements, rate changes, deadline updates
  gazette_monitor.py          # Kenya Gazette tax-related legal notices
  etims_monitor.py            # eTIMS invoice compliance tracking
  source_health.py            # External source reachability checks
```

### The Brain (Learning)

Learns from outcomes to improve risk predictions:

```
agents/learning/
  memory.py                 # Decision history storage and querying
  pattern_miner.py          # Discovers compliance patterns across SMEs
  feedback_loop.py          # Compares predictions to actual outcomes
  model_updater.py          # Proposes risk model weight adjustments
```

### The Hands (Actions)

Takes action based on intelligence:

```
agents/action/
  alert_engine.py           # Sends messages through configured channels
  escalation_engine.py      # Routes missed deadlines to human gate
  recommendation_engine.py  # Generates action lists with Shuru + M-Pesa links
  workflow_engine.py        # Prepares filing packages with checklists
  proactive_engine.py       # Anticipates needs, suggests early filing
```

### The Shield (Security)

Protects sensitive data:

```
security/
  encryption.py             # AES-256 at rest encryption
  pii_handler.py            # Anonymizes PII in logs
  access_control.py         # Role-based access control
```

### Tools

```
tools/
  kra_shuru.py              # KRA Shuru WhatsApp deep links and payment instructions
  mpesa_caller.py           # M-Pesa STK push, paybill instructions
  whatsapp_sender.py        # WhatsApp Business API (dry-run mode)
  sms_sender.py             # SMS via Africa's Talking / Twilio
  phone_utils.py            # Kenya phone normalization (+254)
```

### Integrations

External service connectors:

```
integrations/
  mpesa/                    # STK push, C2B, B2C, webhooks
  kra/                      # iTax guides, eTIMS compliance, gazette monitoring
  communication/            # WhatsApp Business, SMS (Africa's Talking/Twilio), email
```

## Kenya Tax Coverage

12 tax types with real rates, penalties, and deadlines:

| Tax | Rate | Deadline | Late Filing/Payment Penalty |
|---|---|---|---|
| Turnover Tax (TOT) | 1.5% of gross turnover | 20th monthly | KES 1,000/month + 5% penalty + 1% interest |
| VAT | 16% | 20th monthly | Higher of 5% of tax due or KES 10,000 + 1% interest |
| PAYE | 10-35% progressive | 9th monthly | Higher of 25% of tax or KES 10,000 |
| NSSF | 6% (employer + employee) | 9th monthly | 5% penalty + interest |
| SHIF | 2.75% of gross salary | 9th monthly | 5% penalty + interest |
| Housing Levy | 1.5% (employer + employee) | 9th monthly | 3% of unpaid amount/month |
| Income Tax (Resident) | 10-35% | June 30 | Higher of 5% of tax due or KES 2,000 |
| Income Tax (Corporate) | 30% | June 30 | Higher of 5% of tax due or KES 20,000 |
| Withholding Tax | 3-20% (varies by type) | 20th monthly | 10% of tax due + 1% interest |
| MRI (Rental) | 7.5% (final tax) | 20th monthly | Higher of 5% of tax or KES 2,000/20,000 |
| Presumptive Tax | 15% of business permit fee | Dec 31 | -- |
| Excise Duty | Varies (15-35%) | 20th monthly | Higher of 5% of tax or KES 10,000 |

12 industries supported: retail, professional services, food/hospitality, transport, manufacturing, rental income, digital/online, construction, agriculture, salon/beauty, education, healthcare.

## Configuration

All settings in `config/settings.json`. Override with environment variables:

| Env Variable | What It Controls |
|---|---|
| `HELMET_API_KEY` | API authentication key |
| `HELMET_API_PORT` | API port (default: 8000) |
| `HELMET_API_AUTH` | Enable/disable auth (true/false) |
| `HELMET_CLAUDE_MODEL` | Claude model for AI calls |
| `HELMET_CONFIDENCE_AUTO` | Auto-proceed threshold (default: 0.7) |
| `HELMET_ITAX_BUFFER` | Days before deadline to file (default: 3) |
| `HELMET_ALERT_MAX` | Max alerts per SME per day (default: 3) |
| `HELMET_ENCRYPTION_KEY` | AES-256 encryption key |
| `HELMET_ENCRYPTION_SALT` | Encryption salt for key derivation |

## Testing

```bash
python -m pytest tests/ -v
```

408 tests across 12 test files:
- **test_input_validator.py** -- PIN, phone, email, period, amount, profile, filing validation
- **test_intelligence.py** -- Obligation mapping, deadlines, risk scoring, compliance, penalties
- **test_communication.py** -- Urgency framing, message generation, SMS/WhatsApp/email formatting
- **test_workflow.py** -- Filing tracker, audit trail immutability
- **test_config.py** -- Settings loading, env overrides, intelligence data integrity
- **test_error_recovery.py** -- safe_run(), file I/O recovery, error logging
- **test_scheduler.py** -- Priority queue, trigger engine, heartbeat, event listener
- **test_monitoring.py** -- Source health, KRA monitor, gazette monitor, eTIMS monitor
- **test_hands.py** -- Alert engine, escalation engine, recommendation engine, workflow engine
- **test_learning.py** -- Decision memory, pattern miner, feedback loop, model updater
- **test_subscription.py** -- Plans, trial, payments, subscription gating, M-Pesa instructions

## Project Structure

```
kra-helmet/
  run.py                          # CLI (20+ commands)
  api.py                          # REST API (FastAPI)
  start_website.py                # Web dashboard launcher
  requirements.txt                # Pinned dependencies
  Dockerfile                      # Production container
  config/
    settings.json                 # All tunable values
    loader.py                     # Config loader + env overrides
    alert_rules.json              # Urgency levels, quiet hours, rate limits
    smes.json                     # SME registry
  intelligence/
    tax_knowledge_graph.json      # 12 taxes
    industry_profiles.json        # 12 industries
    deadline_calendar.json        # 2026 holidays
    filing_guides.json            # 11 iTax guides
  agents/                         # Multi-agent system
    orchestrator.py               # 9-step pipeline
    onboarding/                   # Profile builder, classifier, batch import
    intelligence/                 # Obligations, deadlines, risk, compliance, penalties
    validation/                   # Input validator, confidence, disclaimers
    communication/                # Explainer, urgency, notifications (with Shuru CTAs)
    monitoring/                   # KRA, gazette, eTIMS, source health
    action/                       # Alerts, escalation, recommendations, workflow, proactive
    learning/                     # Memory, patterns, feedback, model updater
  scheduler/                      # The Pulse
  security/                       # The Shield
  tools/
    kra_shuru.py                  # KRA Shuru WhatsApp integration
    mpesa_caller.py               # M-Pesa payment integration
    whatsapp_sender.py            # WhatsApp messaging
    sms_sender.py                 # SMS messaging
  integrations/                   # External services (M-Pesa, KRA, comms)
  dashboard/                      # React frontend (Vite + React Query)
    src/
      App.jsx                     # Router and overview page
      components/
        SystemStatus.jsx          # Futuristic system diagnostics
        SMEDetail.jsx             # SME profile with Shuru buttons
        SMEList.jsx               # SME management grid
        StatsCards.jsx            # Compliance statistics
        ActivityFeed.jsx          # Real-time activity log
        Reports.jsx               # Per-SME reports
        AuditLog.jsx              # Audit trail viewer
        Sidebar.jsx               # Navigation sidebar
  workflow/                       # Human gate, audit trail, filing tracker
  tests/                          # 357 tests
  data/                           # SME profiles, reports, filings
  output/                         # Built dashboard + per-SME reports
  logs/                           # Agent runs, audit trail, errors
```

## Docker

```bash
# Build
docker build -t kra-helmet .

# Run
docker run -p 8000:8000 \
  -e ANTHROPIC_API_KEY=your-key \
  -e HELMET_API_KEY=your-api-key \
  -v kra-helmet-data:/app/data \
  kra-helmet
```

## Disclaimer

This system is for **guidance only**. It does not constitute legal, tax, or financial advice. Tax laws change frequently. Always verify with KRA or a registered tax advisor before making filing or payment decisions.

## License

MIT
