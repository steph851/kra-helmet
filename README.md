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

```bash
# Clone
git clone https://github.com/steph851/kra-helmet.git
cd kra-helmet

# Install
pip install -r requirements.txt

# Configure
cp .env.example .env
# Edit .env with your ANTHROPIC_API_KEY (optional — system works without it)

# Run
python run.py demo          # Full end-to-end demo
python run.py onboard       # Onboard your business
python run.py check --all   # Check all SMEs
python run.py dashboard     # Generate HTML dashboard
```

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
  dashboard.py              # HTML dashboard generator
  report_generator.py       # Per-SME HTML reports
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

## Testing

```bash
python -m pytest tests/ -v
```

116 tests across 6 test files:
- **test_input_validator.py** — PIN, phone, email, period, amount, profile, filing validation
- **test_intelligence.py** — Obligation mapping, deadlines, risk scoring, compliance, penalties
- **test_communication.py** — Urgency framing, message generation, SMS/WhatsApp/email formatting
- **test_workflow.py** — Filing tracker, audit trail immutability
- **test_config.py** — Settings loading, env overrides, intelligence data integrity
- **test_error_recovery.py** — safe_run(), file I/O recovery, error logging

## Project Structure

```
kra-helmet/
├── run.py                          # CLI (16 commands)
├── api.py                          # REST API (FastAPI)
├── requirements.txt                # Pinned dependencies
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
├── workflow/                       # Human gate, audit trail, filing tracker
├── tests/                          # 116 tests
├── data/                           # SME profiles, reports, filings
├── output/                         # Dashboard + per-SME reports
└── logs/                           # Agent runs, audit trail, errors
```

## Disclaimer

This system is for **guidance only**. It does not constitute legal, tax, or financial advice. Tax laws change frequently. Always verify with KRA or a registered tax advisor before making filing or payment decisions.

## License

MIT
