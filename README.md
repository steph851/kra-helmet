# KRA HELMET

**Tax Compliance Autopilot for Kenyan SMEs**

KRA Helmet figures out which taxes your business owes, tracks every deadline, calculates penalties if you're late, and tells you exactly how to file on iTax — step by step.

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
| **Dashboard** | Dark-themed overview of all SMEs with risk bars and status filters |
| **Alerts** | WhatsApp/SMS/email message formatting with quiet hours and rate limits |
| **Human Gate** | Low-confidence items routed to human review before proceeding |
| **Audit Trail** | Immutable JSONL log of every decision |

## Quick Start

### Option 1: Web Dashboard (Recommended)

```bash
# Clone
git clone https://github.com/steph851/kra-helmet.git
cd kra-helmet

# Install
pip install -r requirements.txt

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

## Web Dashboard

KRA HELMET includes a responsive web dashboard accessible from any device:

- **Desktop:** Full-featured dashboard with all controls
- **Tablet:** Optimized layout for medium screens
- **Mobile:** Touch-friendly interface for phones

**Features:**
- Real-time compliance statistics
- SME management with search
- Quick action buttons
- Recent activity feed
- Proactive AI recommendations
- System status monitoring
- Add new SME modal

**Access:** After starting the server, open http://localhost:8000 in any browser.

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
| GET | `/health` | System health check |
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
| GET | `/proactive/{pin}` | Proactive recommendations for SME |
| POST | `/proactive/execute` | Execute autonomous action |

**Authentication:** Set `HELMET_API_KEY` in `.env` and pass `X-API-Key` header.

## Architecture

Multi-agent system with a 9-step pipeline:

```
Onboard → Map Obligations → Calculate Deadlines → Score Risk → Check Compliance
    → Calculate Penalties → Validate Confidence → Frame Urgency
    → Queue Notifications → Generate Explanation
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
  action/                   # Alert engine, escalation engine, recommendation engine, workflow engine
  learning/                 # Decision memory, pattern miner, feedback loop, model updater
  dashboard.py              # HTML dashboard generator
  report_generator.py       # Per-SME HTML reports
```

### The Pulse (Scheduler)

Background scheduler that drives automated compliance monitoring:

```
scheduler/
  heartbeat.py              # Main loop: tick → scan → queue → dispatch → sleep
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
  recommendation_engine.py  # Generates "do this now" action lists
  workflow_engine.py        # Prepares filing packages with checklists
```

### The Shield (Security)

Protects sensitive data:

```
security/
  encryption.py             # AES-256 at rest encryption
  pii_handler.py            # Anonymizes PII in logs
  access_control.py         # Role-based access control
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

| Tax | Rate | Deadline | Late Filing Penalty |
|---|---|---|---|
| Turnover Tax (TOT) | 3% of gross turnover | 20th monthly | KES 20,000 or 5% |
| VAT | 16% | 20th monthly | KES 10,000 or 5% |
| PAYE | 10-35% progressive | 9th monthly | 25% of tax or KES 10,000 |
| NSSF | 6% | 9th monthly | 5%/month |
| SHIF | 2.75% | 9th monthly | 5%/month |
| Housing Levy | 1.5% + 1.5% | 9th monthly | 3%/month |
| Income Tax (Resident) | 10-35% | June 30 | KES 20,000 or 5% |
| Income Tax (Corporate) | 30% | June 30 | KES 20,000 or 5% |
| Withholding Tax | 3-20% | 20th monthly | KES 20,000 or 5% |
| MRI (Rental) | 7.5% | 20th monthly | KES 20,000 or 5% |
| Presumptive Tax | KES 15,000/year | Dec 31 | — |
| Excise Duty | Varies | 20th monthly | — |

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

357 tests across 11 test files:
- **test_input_validator.py** — PIN, phone, email, period, amount, profile, filing validation
- **test_intelligence.py** — Obligation mapping, deadlines, risk scoring, compliance, penalties
- **test_communication.py** — Urgency framing, message generation, SMS/WhatsApp/email formatting
- **test_workflow.py** — Filing tracker, audit trail immutability
- **test_config.py** — Settings loading, env overrides, intelligence data integrity
- **test_error_recovery.py** — safe_run(), file I/O recovery, error logging
- **test_scheduler.py** — Priority queue, trigger engine, heartbeat, event listener
- **test_monitoring.py** — Source health, KRA monitor, gazette monitor, eTIMS monitor
- **test_hands.py** — Alert engine, escalation engine, recommendation engine, workflow engine
- **test_learning.py** — Decision memory, pattern miner, feedback loop, model updater
- **test_learning.py** — Model updater guardrails and proposals

## Project Structure

```
kra-helmet/
├── run.py                          # CLI (16 commands)
├── api.py                          # REST API (FastAPI)
├── requirements.txt                # Pinned dependencies
├── Dockerfile                      # Production container
├── config/
│   ├── settings.json               # All tunable values
│   ├── loader.py                   # Config loader + env overrides
│   ├── smes.json                   # SME registry
│   └── ...
├── intelligence/
│   ├── tax_knowledge_graph.json    # 12 taxes
│   ├── industry_profiles.json      # 12 industries
│   ├── deadline_calendar.json      # 2026 holidays
│   └── filing_guides.json          # 11 iTax guides
├── agents/                         # Multi-agent system
│   ├── orchestrator.py             # 9-step pipeline
│   ├── onboarding/                 # Profile builder, classifier, batch import
│   ├── intelligence/               # Obligations, deadlines, risk, compliance, penalties
│   ├── validation/                 # Input validator, confidence, disclaimers
│   ├── communication/              # Explainer, urgency, notifications
│   ├── monitoring/                 # KRA, gazette, eTIMS, source health
│   ├── action/                     # Alerts, escalation, recommendations, workflow
│   └── learning/                   # Memory, patterns, feedback, model updater
├── scheduler/                      # The Pulse — heartbeat, trigger, queue, webhooks
├── security/                       # The Shield — encryption, PII, access control
├── integrations/                   # External services
│   ├── mpesa/                      # STK push, webhooks
│   ├── kra/                        # iTax, eTIMS, gazette
│   └── communication/              # WhatsApp, SMS, email
├── workflow/                       # Human gate, audit trail, filing tracker
├── tools/                          # Web reader, phone utils, agent caller
├── tests/                          # 357 tests
├── data/                           # SME profiles, reports, filings
├── output/                         # Dashboard + per-SME reports
└── logs/                           # Agent runs, audit trail, errors
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
