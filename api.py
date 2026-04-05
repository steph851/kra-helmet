"""
KRA Deadline Tracker — REST API
Usage: uvicorn api:app --reload --port 8000
"""
import sys
import os
import json
import asyncio
from pathlib import Path
from datetime import datetime

# Fix Windows console encoding
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

# Initialize Sentry for error tracking
SENTRY_DSN = os.getenv("SENTRY_DSN")
if SENTRY_DSN:
    import sentry_sdk
    from sentry_sdk.integrations.fastapi import FastApiIntegration
    sentry_sdk.init(
        dsn=SENTRY_DSN,
        integrations=[FastApiIntegration()],
        traces_sample_rate=0.1,
        environment="production" if os.getenv("RENDER") else "development",
    )
    print("[Sentry] Error tracking enabled")

from fastapi import FastAPI, HTTPException, Depends, Security, Request
from fastapi.security import APIKeyHeader
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.responses import Response
from fastapi.staticfiles import StaticFiles
import os
from pydantic import BaseModel, field_validator, Field
import re

from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

# Lazy imports to avoid startup hang
from config.loader import get_settings
settings = get_settings()

# These imports will be lazy-initialized when first used
from agents.orchestrator import Orchestrator
from agents.dashboard import DashboardGenerator
from agents.report_generator import ReportGenerator
from agents.validation.input_validator import InputValidator
from workflow.filing_tracker import FilingTracker
# AuditTrail imports from database - now lazy
from workflow.audit_trail import AuditTrail
from subscription.tracker import SubscriptionTracker
from tools.whatsapp_sender import WhatsAppSender
from integrations.mpesa.webhooks import MpesaWebhookHandler

app = FastAPI(
    title="KRA Deadline Tracker API",
    description=(
        "Tax Compliance Autopilot for Kenyan SMEs.\n\n"
        "KRA Deadline Tracker maps your tax obligations, tracks every KRA deadline, "
        "calculates penalties, scores audit risk, and gives step-by-step iTax filing instructions.\n\n"
        "**Authentication:** Set `HELMET_API_KEY` in `.env` and pass `X-API-Key` header on protected endpoints.\n\n"
        "**Docs:** [Full API Reference](https://github.com/steph851/kra-helmet/blob/master/docs/API.md)"
    ),
    version=settings["system"]["version"],
    openapi_tags=[
        {"name": "System", "description": "Health checks and service info"},
        {"name": "SMEs", "description": "Onboard and manage SME profiles"},
        {"name": "Compliance", "description": "Run compliance checks and risk assessments"},
        {"name": "Filings", "description": "Record and track tax filings"},
        {"name": "Reports", "description": "HTML dashboard and per-SME reports"},
        {"name": "Audit", "description": "Immutable audit trail"},
        {"name": "Guides", "description": "Step-by-step iTax filing guides"},
        {"name": "Pulse", "description": "The Pulse — scheduler status and control"},
        {"name": "Webhooks", "description": "External event webhooks for The Pulse"},
        {"name": "Monitoring", "description": "The Eyes — external source monitoring"},
        {"name": "Actions", "description": "The Hands — recommendations, filing prep, alerts, escalations"},
        {"name": "Shuru", "description": "KRA Shuru — WhatsApp tax filing and payment via +254 711 099 999"},
        {"name": "Brain", "description": "The Brain — learning, patterns, feedback, model updates"},
        {"name": "Subscriptions", "description": "Subscription management — plans, payments, M-Pesa"},
    ],
)

# ── CORS — allow dashboard + Render domain ────────────────────────
RENDER_URL = os.getenv("RENDER_EXTERNAL_URL", "")
CORS_ORIGINS = [
    "http://localhost:5173",   # Vite dev server
    "http://localhost:8000",   # Local API
]
if RENDER_URL:
    CORS_ORIGINS.append(RENDER_URL)
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["*"],
)

# ── Rate limiting — protect public endpoints ──────────────────────
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

orch = Orchestrator()
tracker = FilingTracker()
audit = AuditTrail()
validator = InputValidator()
subs = SubscriptionTracker()
_wa = WhatsAppSender()

# Serve React static assets
react_static_path = ROOT / "output" / "dashboard-react"


@app.get("/assets/{path:path}", include_in_schema=False)
async def serve_react_assets(path: str):
    """Serve React built assets from output/dashboard-react."""
    if not react_static_path.exists():
        raise HTTPException(status_code=404, detail="React assets not found")
    
    file_path = react_static_path / "assets" / path
    if not file_path.exists():
        raise HTTPException(status_code=404, detail=f"Asset not found: {path}")
    
    ext = file_path.suffix.lower()
    media_type = {
        ".js": "application/javascript",
        ".css": "text/css",
        ".map": "application/json",
        ".svg": "image/svg+xml",
        ".png": "image/png",
        ".jpg": "image/jpeg",
    }.get(ext, "application/octet-stream")
    
    return FileResponse(file_path, media_type=media_type)


# ── Authentication ──────────────────────────────────────────────

API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)
API_KEY = os.getenv("HELMET_API_KEY", "")


async def verify_api_key(api_key: str = Security(API_KEY_HEADER)):
    """Verify API key - required for all protected endpoints."""
    if not API_KEY:
        import logging
        logging.getLogger("kra_helmet.api").error("HELMET_API_KEY not configured - auth disabled!")
        raise HTTPException(status_code=500, detail="Server misconfigured: missing HELMET_API_KEY")
    if api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key. Use X-API-Key header.")
    return True


# ── Global error handler ────────────────────────────────────────

@app.exception_handler(Exception)
async def global_error_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={
            "error": type(exc).__name__,
            "detail": str(exc),
            "timestamp": datetime.now().isoformat(),
        }
    )


# ── Validated Models ────────────────────────────────────────────

class OnboardRequest(BaseModel):
    pin: str
    name: str
    business_name: str | None = None
    business_type: str = "sole_proprietor"
    industry: str = "retail_wholesale"
    county: str = "Nairobi"
    annual_turnover_kes: float = 0
    turnover_bracket: str = "below_1m"
    has_employees: bool = False
    employee_count: int = 0
    is_vat_registered: bool = False
    has_etims: bool = False
    phone: str = ""
    email: str | None = None
    preferred_language: str = "en"
    preferred_channel: str = "whatsapp"
    rental_income_annual_kes: float | None = None

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "pin": "A987654321Z",
                    "name": "Jane Wanjiru",
                    "business_name": "Wanjiru Consultants",
                    "business_type": "sole_proprietor",
                    "industry": "professional_services",
                    "county": "Nairobi",
                    "annual_turnover_kes": 3500000,
                    "turnover_bracket": "1m_to_8m",
                    "has_employees": True,
                    "employee_count": 4,
                    "is_vat_registered": False,
                    "has_etims": True,
                    "phone": "0712345678",
                    "email": "jane@example.com",
                    "preferred_language": "en",
                    "preferred_channel": "whatsapp",
                }
            ]
        }
    }

    @field_validator("pin")
    @classmethod
    def validate_pin(cls, v):
        v = v.strip().upper()
        if not re.match(r"^[A-Z]\d{9}[A-Z]$", v):
            raise ValueError(f"Invalid KRA PIN format: {v}")
        return v

    @field_validator("name")
    @classmethod
    def validate_name(cls, v):
        v = v.strip()
        if len(v) < 2:
            raise ValueError("Name must be at least 2 characters")
        return v

    @field_validator("business_type")
    @classmethod
    def validate_btype(cls, v):
        valid = {"sole_proprietor", "partnership", "limited_company"}
        if v not in valid:
            raise ValueError(f"Invalid business_type. Valid: {valid}")
        return v

    @field_validator("industry")
    @classmethod
    def validate_industry(cls, v):
        valid = {
            "retail_wholesale", "professional_services", "food_hospitality",
            "transport", "manufacturing", "rental_income", "digital_online",
            "construction", "agriculture", "salon_beauty", "education", "healthcare",
        }
        if v not in valid:
            raise ValueError(f"Invalid industry. Valid: {valid}")
        return v

    @field_validator("turnover_bracket")
    @classmethod
    def validate_bracket(cls, v):
        valid = {"below_1m", "1m_to_8m", "8m_to_25m", "above_25m"}
        if v not in valid:
            raise ValueError(f"Invalid turnover_bracket. Valid: {valid}")
        return v

    @field_validator("preferred_language")
    @classmethod
    def validate_lang(cls, v):
        if v not in ("en", "sw"):
            raise ValueError("Language must be 'en' or 'sw'")
        return v

    @field_validator("preferred_channel")
    @classmethod
    def validate_channel(cls, v):
        if v not in ("whatsapp", "sms", "email"):
            raise ValueError("Channel must be 'whatsapp', 'sms', or 'email'")
        return v

    @field_validator("annual_turnover_kes")
    @classmethod
    def validate_turnover(cls, v):
        if v < 0:
            raise ValueError("Turnover cannot be negative")
        return v


class FilingRequest(BaseModel):
    tax_type: str
    period: str
    amount_kes: float = 0
    reference: str = ""

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "tax_type": "vat",
                    "period": "2026-03",
                    "amount_kes": 125000,
                    "reference": "ACK-2026-0345",
                }
            ]
        }
    }

    @field_validator("period")
    @classmethod
    def validate_period(cls, v):
        if not re.match(r"^\d{4}-(0[1-9]|1[0-2])$", v):
            raise ValueError("Period must be YYYY-MM format (e.g. 2026-03)")
        return v

    @field_validator("amount_kes")
    @classmethod
    def validate_amount(cls, v):
        if v < 0:
            raise ValueError("Amount cannot be negative")
        return v


class SignupRequest(BaseModel):
    """Public signup — onboards SME and starts free trial."""
    pin: str
    name: str
    business_name: str | None = None
    business_type: str = "sole_proprietor"
    industry: str = "retail_wholesale"
    county: str = "Nairobi"
    annual_turnover_kes: float = 0
    turnover_bracket: str = "below_1m"
    has_employees: bool = False
    employee_count: int = 0
    is_vat_registered: bool = False
    has_etims: bool = False
    phone: str = ""
    email: str | None = None
    preferred_language: str = "en"

    @field_validator("pin")
    @classmethod
    def validate_pin(cls, v):
        v = v.strip().upper()
        if not re.match(r"^[A-Z]\d{9}[A-Z]$", v):
            raise ValueError(f"Invalid KRA PIN format: {v}")
        return v

    @field_validator("name")
    @classmethod
    def validate_name(cls, v):
        v = v.strip()
        if not (2 <= len(v) <= 200):
            raise ValueError("Name must be 2-200 characters")
        if re.search(r'[<>&\'\";]', v):
            raise ValueError("Name contains invalid characters")
        return v

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v):
        v = v.strip()
        if v and not re.match(r"^(\+?254|0)\d{9}$", v):
            raise ValueError("Invalid Kenya phone number")
        return v


class PaymentConfirmRequest(BaseModel):
    """Admin confirms M-Pesa payment."""
    pin: str
    mpesa_ref: str
    amount_kes: float
    plan: str = "monthly"
    phone: str = ""


# ── Endpoints ───────────────────────────────────────────────────

@app.get("/", tags=["System"], summary="Web dashboard")
def root():
    """Serve the React web dashboard at the root URL."""
    react_dashboard = ROOT / "output" / "dashboard-react" / "index.html"
    if react_dashboard.exists():
        return FileResponse(react_dashboard, media_type="text/html")
    dev_dashboard = ROOT / "dashboard" / "index.html"
    if dev_dashboard.exists():
        return FileResponse(dev_dashboard, media_type="text/html")


@app.get("/onboard", tags=["System"], summary="Web onboarding form")
def web_onboarding():
    """Serve the self-service onboarding form."""
    onboard_html = ROOT / "web-onboarding" / "index.html"
    if onboard_html.exists():
        return FileResponse(onboard_html, media_type="text/html")
    return HTMLResponse("""<html><body>
        <h1>KRA Deadline Tracker</h1>
        <p>Onboarding form not found. Contact support.</p>
    </body></html>""")


@app.get("/favicon.svg", include_in_schema=False)
async def favicon_svg():
    """Serve favicon SVG (prevents browser 404 noise)."""
    icon_path = ROOT / "output" / "dashboard-react" / "favicon.svg"
    if not icon_path.exists():
        icon_path = ROOT / "dashboard" / "favicon.svg"
    if icon_path.exists():
        return FileResponse(icon_path, media_type="image/svg+xml")
    return Response(status_code=204)


@app.get("/favicon.ico", include_in_schema=False)
async def favicon_ico():
    """Serve favicon ICO (prevents browser 404 noise)."""
    icon_path = ROOT / "dashboard" / "favicon.ico"
    if icon_path.exists():
        return FileResponse(icon_path, media_type="image/x-icon")
    return Response(status_code=204)


@app.get("/health", tags=["System"], summary="Health check")
def health_check():
    """System health check — verifies config, SME registry, intelligence data, directories, audit trail, and authentication."""
    checks = {}

    # Config
    try:
        from config.loader import get_settings
        s = get_settings()
        checks["config"] = {"status": "ok", "version": s["system"]["version"]}
    except Exception as e:
        checks["config"] = {"status": "error", "detail": str(e)}

    # SME registry
    try:
        smes = orch.list_smes()
        checks["sme_registry"] = {"status": "ok", "count": len(smes)}
    except Exception as e:
        checks["sme_registry"] = {"status": "error", "detail": str(e)}

    # Intelligence data
    intel_files = ["tax_knowledge_graph.json", "industry_profiles.json", "deadline_calendar.json", "filing_guides.json"]
    missing = [f for f in intel_files if not (ROOT / "intelligence" / f).exists()]
    checks["intelligence_data"] = {"status": "ok" if not missing else "error", "missing": missing}

    # Data directories
    dirs = {
        "confirmed_profiles": ROOT / "data" / "confirmed" / "sme_profiles",
        "processed_obligations": ROOT / "data" / "processed" / "obligations",
        "filings": ROOT / "data" / "filings",
        "staging": ROOT / "staging" / "review",
    }
    for name, path in dirs.items():
        checks[name] = {"status": "ok" if path.exists() else "missing"}

    # Audit trail
    audit_path = ROOT / "logs" / "audit_trail.jsonl"
    checks["audit_trail"] = {"status": "ok" if audit_path.exists() else "not_started"}

    # API key
    checks["authentication"] = {
        "status": "enabled" if API_KEY else "disabled",
    }

    # Scheduler (The Pulse)
    scheduler_running = _pulse is not None and _pulse.is_running
    checks["scheduler"] = {"status": "running" if scheduler_running else "stopped"}

    # Monitoring (The Eyes)
    try:
        _monitor.status()  # verify orchestrator is functional
        monitoring_active = True
    except Exception:
        monitoring_active = False
    checks["monitoring"] = {"status": "active" if monitoring_active else "inactive"}

    # Database (PostgreSQL via Neon or JSON fallback)
    try:
        from database.connection import db_available
        db_connected = db_available()
    except Exception as e:
        db_connected = False
    checks["database"] = {"status": "connected" if db_connected else "json_fallback"}

    # WhatsApp Bot
    bot_status = _wa.bot_status()
    bot_connected = bot_status.get("connected", False)
    checks["whatsapp_bot"] = {
        "status": "connected" if bot_connected else "disconnected",
        "phone": bot_status.get("phone"),
        "name": bot_status.get("name"),
    }

    # Overall
    all_ok = all(
        c.get("status") in ("ok", "enabled", "disabled", "not_started", "running", "active", "connected")
        for c in checks.values()
    )

    return {
        "status": "healthy" if all_ok else "degraded",
        "timestamp": datetime.now().isoformat(),
        "database": "connected" if db_connected else "json_fallback",
        "scheduler": "running" if scheduler_running else "stopped",
        "monitoring": "active" if monitoring_active else "inactive",
        "checks": checks,
    }


# ── Analytics & Feedback (public) ───────────────────────────────────────────────────────────

_analytics = {
    "page_views": 0,
    "onboarding_starts": 0,
    "onboarding_completes": 0,
    "subscription_starts": 0,
    "alerts_sent": 0,
}


def track_event(event: str, count: int = 1):
    """Track an analytics event."""
    if event in _analytics:
        _analytics[event] += count


@app.get("/analytics", tags=["System"], summary="Anonymous usage analytics")
def get_analytics():
    """Public analytics - counts of usage events (no personal data)."""
    return {"status": "ok", "timestamp": datetime.now().isoformat(), "data": dict(_analytics)}


class FeedbackInput(BaseModel):
    type: str  # bug | feature | compliment | complaint
    message: str
    email: str = ""
    pin: str = ""


@app.post("/feedback", tags=["System"], summary="Submit user feedback")
def submit_feedback(feedback: FeedbackInput):
    """Submit feedback - bug report, feature request, or compliment."""
    feedback_file = ROOT / "logs" / "user_feedback.jsonl"
    feedback_file.parent.mkdir(exist_ok=True)
    entry = {
        "timestamp": datetime.now().isoformat(),
        "type": feedback.type,
        "message": feedback.message,
        "email": feedback.email,
        "pin": feedback.pin,
    }
    with open(feedback_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return {"status": "received", "message": "Thank you for your feedback!"}


@app.get("/smes", tags=["SMEs"], summary="List all SMEs", dependencies=[Depends(verify_api_key)])
def list_smes():
    """List all onboarded SMEs with basic profile info."""
    smes = orch.list_smes()
    return {"count": len(smes), "smes": smes}


@app.get("/smes/{pin}", tags=["SMEs"], summary="Get SME profile", dependencies=[Depends(verify_api_key)])
def get_sme(pin: str):
    """Get full SME profile including classification, obligations, and contact details."""
    ok, msg = validator.validate_pin(pin)
    if not ok:
        raise HTTPException(status_code=400, detail=msg)

    profile = orch.load_sme(msg)  # msg is the cleaned PIN
    if not profile:
        raise HTTPException(status_code=404, detail=f"SME not found: {pin}")
    return profile


@app.post("/onboard", tags=["SMEs"], summary="Onboard new SME", dependencies=[Depends(verify_api_key)])
def onboard_sme(req: OnboardRequest):
    """Onboard a new SME. Automatically maps tax obligations based on business type, industry, and turnover."""
    data = req.model_dump()
    if not data.get("business_name"):
        data["business_name"] = data["name"]

    existing = orch.load_sme(data["pin"])
    if existing:
        raise HTTPException(status_code=409, detail=f"SME already onboarded: {data['pin']}")

    profile = orch.onboard(interactive=False, data=data)
    if not profile:
        raise HTTPException(status_code=500, detail="Onboarding failed — check server logs")

    # Track analytics
    track_event("onboarding_completes", 1)

    return {
        "status": "onboarded",
        "pin": profile["pin"],
        "name": profile["name"],
        "obligations": profile.get("classification", {}).get("obligations", []),
    }


@app.get("/check/{pin}", tags=["Compliance"], summary="Check one SME", dependencies=[Depends(verify_api_key)])
def check_sme(pin: str):
    """Run full 9-step compliance check: obligations, deadlines, risk scoring, compliance status, penalties, confidence validation, urgency framing, notifications, and explanation."""
    ok, msg = validator.validate_pin(pin)
    if not ok:
        raise HTTPException(status_code=400, detail=msg)

    result = orch.check_sme(msg)
    if not result:
        raise HTTPException(status_code=404, detail=f"SME not found or check failed: {pin}")
    return {
        "pin": msg,
        "name": result["profile"]["name"],
        "compliance": result["compliance"],
        "risk": result["risk"],
        "penalties": result.get("penalties", {}),
        "urgency": result["urgency"],
        "obligations": result["obligations"],
        "message": result["message"],
        "alerts_queued": result.get("alerts_queued", 0),
    }


@app.get("/check", tags=["Compliance"], summary="Check all SMEs", dependencies=[Depends(verify_api_key)])
def check_all():
    """Run compliance check for all onboarded SMEs. Returns summary with risk scores and urgency levels."""
    results = orch.check_all()
    return {
        "checked": len(results),
        "results": [
            {
                "pin": r["profile"]["pin"],
                "name": r["profile"]["name"],
                "compliance": r["compliance"]["overall"],
                "risk_score": r["risk"]["risk_score"],
                "urgency": r["urgency"]["urgency_level"],
            }
            for r in results
        ]
    }


@app.post("/file/{pin}", tags=["Filings"], summary="Record a filing", dependencies=[Depends(verify_api_key)])
def record_filing(pin: str, req: FilingRequest):
    """Record a tax filing for an SME. Validates the PIN, tax type, period, and amount before saving."""
    ok, msg = validator.validate_pin(pin)
    if not ok:
        raise HTTPException(status_code=400, detail=msg)

    profile = orch.load_sme(msg)
    if not profile:
        raise HTTPException(status_code=404, detail=f"SME not found: {pin}")

    ok, errors = validator.validate_filing(msg, req.tax_type, req.period, req.amount_kes)
    if not ok:
        raise HTTPException(status_code=400, detail=errors)

    entry = tracker.record_filing(
        pin=msg, tax_type=req.tax_type, period=req.period,
        amount_kes=req.amount_kes, reference=req.reference,
    )
    return {"status": "recorded", "filing": entry}


@app.get("/filings/{pin}", tags=["Filings"], summary="Filing history", dependencies=[Depends(verify_api_key)])
def get_filings(pin: str, tax_type: str | None = None):
    """Get filing history for an SME. Optionally filter by tax type."""
    ok, msg = validator.validate_pin(pin)
    if not ok:
        raise HTTPException(status_code=400, detail=msg)

    filings = tracker.get_filings(msg, tax_type)
    summary = tracker.get_filing_summary(msg)
    return {"pin": msg, "summary": summary, "filings": filings}


@app.get("/dashboard", tags=["Reports"], summary="Live dashboard", response_class=HTMLResponse)
def dashboard():
    """Generate and serve the live HTML dashboard with all SMEs, risk bars, and status filters."""
    gen = DashboardGenerator()
    output_path = gen.generate()
    return output_path.read_text(encoding="utf-8")


@app.get("/report/{pin}", tags=["Reports"], summary="SME report", response_class=HTMLResponse)
def report(pin: str):
    """Generate a print-ready HTML compliance report for a specific SME."""
    ok, msg = validator.validate_pin(pin)
    if not ok:
        raise HTTPException(status_code=400, detail=msg)

    gen = ReportGenerator()
    output_path = gen.generate(msg)
    if not output_path:
        raise HTTPException(status_code=404, detail=f"SME not found: {pin}")
    return output_path.read_text(encoding="utf-8")


@app.get("/audit", tags=["Audit"], summary="Audit trail", dependencies=[Depends(verify_api_key)])
def audit_log(pin: str | None = None, limit: int = 50):
    """Get the immutable audit trail. Filter by PIN and limit results."""
    if pin:
        ok, msg = validator.validate_pin(pin)
        if not ok:
            raise HTTPException(status_code=400, detail=msg)
        pin = msg
    entries = audit.get_history(sme_pin=pin, limit=limit)
    return {"count": len(entries), "entries": entries}


@app.get("/guides", tags=["Guides"], summary="List filing guides")
def list_guides():
    """List all available iTax filing guides covering 11 tax types."""
    import json
    guides_path = ROOT / "intelligence" / "filing_guides.json"
    data = json.loads(guides_path.read_text(encoding="utf-8"))
    return {
        "count": len(data["filing_guides"]),
        "guides": [{"tax_key": g["tax_key"], "title": g["title"]} for g in data["filing_guides"]],
    }


@app.get("/guides/{tax_key}", tags=["Guides"], summary="Get filing guide")
def get_guide(tax_key: str):
    """Get step-by-step iTax filing instructions for a specific tax type (e.g. vat, paye, tot)."""
    import json
    guides_path = ROOT / "intelligence" / "filing_guides.json"
    data = json.loads(guides_path.read_text(encoding="utf-8"))
    guide = next((g for g in data["filing_guides"] if g["tax_key"] == tax_key.lower()), None)
    if not guide:
        raise HTTPException(status_code=404, detail=f"Guide not found: {tax_key}")
    return guide


# ── The Pulse — Scheduler ──────────────────────────────────────

from scheduler.priority_queue import PriorityQueue
from scheduler.heartbeat import Heartbeat
from scheduler.event_listener import create_webhook_router

_pulse_queue = PriorityQueue()
_pulse: Heartbeat | None = None


@app.on_event("startup")
async def init_db():
    """Initialize database on startup (Neon PostgreSQL or JSON fallback)."""
    from database.connection import init_database, db_available
    try:
        init_database()
    except Exception as e:
        print(f"[DB] Initialization warning: {e}")


@app.on_event("startup")
async def start_pulse():
    """Start The Pulse scheduler when the API starts (if enabled)."""
    global _pulse
    if settings.get("scheduler", {}).get("start_with_api", True):
        try:
            _pulse = Heartbeat()
            _pulse.start(daemon=True)
        except Exception as e:
            print(f"[Pulse] Failed to start scheduler: {e} — API continues without it")

    # Keep-alive self-ping for free tier hosting (Render, Koyeb)
    # Prevents the service from sleeping after 15 min of inactivity
    render_url = os.getenv("RENDER_EXTERNAL_URL")
    if render_url:
        async def _keep_alive():
            import urllib.request
            while True:
                await asyncio.sleep(600)  # every 10 min
                try:
                    urllib.request.urlopen(f"{render_url}/health", timeout=10)
                except Exception:
                    pass
        asyncio.create_task(_keep_alive())


@app.on_event("shutdown")
async def stop_pulse():
    """Stop The Pulse on shutdown."""
    if _pulse and _pulse.is_running:
        _pulse.stop()


# Mount webhook router
_webhook_router = create_webhook_router(_pulse_queue)
app.include_router(_webhook_router)

# Mount M-Pesa webhook router (auto-confirm subscriptions)
_mpesa_webhook = MpesaWebhookHandler(subs)
app.include_router(_mpesa_webhook.create_router())


@app.get("/pulse", tags=["Pulse"], summary="Scheduler status", dependencies=[Depends(verify_api_key)])
def pulse_status():
    """Get The Pulse scheduler status: alive state, queue stats, last-checked times."""
    if _pulse:
        return _pulse.status()
    return {"alive": False, "message": "The Pulse is not running. Set scheduler.start_with_api=true in settings."}


@app.post("/pulse/trigger/{pin}", tags=["Pulse"], summary="Trigger check for SME", dependencies=[Depends(verify_api_key)])
def pulse_trigger(pin: str, reason: str = "api_trigger"):
    """Manually trigger an immediate compliance check for an SME via The Pulse."""
    ok, msg = validator.validate_pin(pin)
    if not ok:
        raise HTTPException(status_code=400, detail=msg)

    if not _pulse:
        raise HTTPException(status_code=503, detail="The Pulse is not running")

    queued = _pulse.trigger_check(msg, reason)
    result = _pulse.trigger.dispatch_next()

    return {
        "pin": msg,
        "queued": queued,
        "checked": result is not None,
        "compliance": result.get("compliance", {}).get("overall") if result else None,
        "risk_score": result.get("risk", {}).get("risk_score") if result else None,
        "timestamp": datetime.now().isoformat(),
    }


@app.post("/pulse/trigger-all", tags=["Pulse"], summary="Trigger check for all SMEs", dependencies=[Depends(verify_api_key)])
def pulse_trigger_all(reason: str = "api_batch_trigger"):
    """Queue all SMEs for compliance check via The Pulse."""
    if not _pulse:
        raise HTTPException(status_code=503, detail="The Pulse is not running")

    count = _pulse.trigger_all(reason=reason)
    results = _pulse.trigger.dispatch_batch()

    return {
        "queued": count,
        "dispatched": len(results),
        "results": [
            {
                "pin": r["profile"]["pin"],
                "compliance": r["compliance"]["overall"],
                "risk_score": r["risk"]["risk_score"],
            }
            for r in results
        ],
        "timestamp": datetime.now().isoformat(),
    }


# ── The Eyes — Monitoring ──────────────────────────────────────

from agents.monitoring import MonitoringOrchestrator

_monitor = MonitoringOrchestrator()


@app.get("/eyes", tags=["Monitoring"], summary="Monitoring status", dependencies=[Depends(verify_api_key)])
def eyes_status():
    """Get The Eyes monitoring status across all monitors (KRA, Gazette, eTIMS, sources)."""
    return _monitor.status()


@app.post("/eyes/scan", tags=["Monitoring"], summary="Run full monitoring scan", dependencies=[Depends(verify_api_key)])
def eyes_full_scan():
    """Run a full monitoring scan: source health, KRA announcements, gazette, eTIMS compliance."""
    return _monitor.run_full_scan()


@app.get("/eyes/health", tags=["Monitoring"], summary="Source health check")
def eyes_health():
    """Check if external data sources (KRA, iTax, eTIMS, Kenya Law) are reachable."""
    return _monitor.run_health_only()


@app.get("/eyes/etims/{pin}", tags=["Monitoring"], summary="eTIMS check for SME", dependencies=[Depends(verify_api_key)])
def eyes_etims(pin: str):
    """Check eTIMS compliance for a specific SME."""
    ok, msg = validator.validate_pin(pin)
    if not ok:
        raise HTTPException(status_code=400, detail=msg)
    return _monitor.check_etims_sme(msg)


# ── The Hands — Actions ──────────────────────────────────────

from agents.action import RecommendationEngine, WorkflowEngine, AlertEngine, EscalationEngine, ProactiveEngine

_recommend = RecommendationEngine()
_workflow = WorkflowEngine()
_alerts = AlertEngine()
_escalation = EscalationEngine()
_proactive = ProactiveEngine()


@app.get("/actions/{pin}", tags=["Actions"], summary="Get action list for SME", dependencies=[Depends(verify_api_key)])
def get_actions(pin: str):
    """Get prioritized 'do this now' action list for an SME: overdue filings, upcoming deadlines, eTIMS issues, payment instructions."""
    ok, msg = validator.validate_pin(pin)
    if not ok:
        raise HTTPException(status_code=400, detail=msg)
    return _recommend.generate(msg)


@app.post("/prepare/{pin}", tags=["Actions"], summary="Prepare filing package", dependencies=[Depends(verify_api_key)])
def prepare_filing(pin: str, tax_type: str | None = None):
    """Prepare a filing package with pre-filled data, iTax instructions, M-Pesa payment steps, and checklist. If tax_type is omitted, prepares all due filings."""
    ok, msg = validator.validate_pin(pin)
    if not ok:
        raise HTTPException(status_code=400, detail=msg)

    if tax_type:
        package = _workflow.prepare_filing(msg, tax_type.lower())
        if not package:
            raise HTTPException(status_code=404, detail=f"Could not prepare filing for {pin} / {tax_type}")
        return package
    else:
        packages = _workflow.prepare_all_due(msg)
        return {"pin": msg, "packages": packages, "count": len(packages)}


@app.post("/deliver", tags=["Actions"], summary="Deliver pending alerts", dependencies=[Depends(verify_api_key)])
def deliver_alerts():
    """Process and deliver all pending alerts from the queue (WhatsApp, SMS, or email)."""
    results = _alerts.process_queue()
    status = _alerts.status()
    return {
        "delivered": len(results),
        "results": results,
        "queue_status": status,
        "timestamp": datetime.now().isoformat(),
    }


@app.get("/alerts/status", tags=["Actions"], summary="Alert engine status", dependencies=[Depends(verify_api_key)])
def alert_status():
    """Get alert engine status: pending count, delivered count, channel configuration."""
    return _alerts.status()


@app.post("/escalate", tags=["Actions"], summary="Run escalation check", dependencies=[Depends(verify_api_key)])
def run_escalation():
    """Evaluate all SMEs for escalation: overdue filings, penalty thresholds. Routes to human gate."""
    escalations = _escalation.evaluate_all()
    pending = _escalation.get_pending_escalations()
    return {
        "new_escalations": len(escalations),
        "escalations": escalations,
        "total_pending": len(pending),
        "timestamp": datetime.now().isoformat(),
    }


@app.get("/proactive/{pin}", tags=["Actions"], summary="Get proactive recommendations", dependencies=[Depends(verify_api_key)])
def get_proactive_recommendations(pin: str):
    """Get proactive recommendations for an SME: anticipates needs, suggests early filing, predicts risk trajectory."""
    ok, msg = validator.validate_pin(pin)
    if not ok:
        raise HTTPException(status_code=400, detail=msg)
    return _proactive.analyze_and_recommend(msg)


@app.post("/proactive/execute", tags=["Actions"], summary="Execute autonomous action", dependencies=[Depends(verify_api_key)])
def execute_autonomous_action(pin: str, action: str):
    """Execute a low-risk autonomous action without human gate."""
    ok, msg = validator.validate_pin(pin)
    if not ok:
        raise HTTPException(status_code=400, detail=msg)
    return _proactive.execute_autonomous_action(action, msg, {"source": "api"})


# ── KRA Shuru — WhatsApp Tax Filing ─────────────────────────

from tools.kra_shuru import KRAShuru

_shuru = KRAShuru()


@app.get("/shuru/{pin}", tags=["Shuru"], summary="KRA Shuru links for SME", dependencies=[Depends(verify_api_key)])
def shuru_links(pin: str, tax_type: str = "", lang: str = "en"):
    """Generate KRA Shuru WhatsApp deep links for an SME: filing, payment, compliance certificate, and step-by-step instructions."""
    ok, msg = validator.validate_pin(pin)
    if not ok:
        raise HTTPException(status_code=400, detail=msg)

    instructions = _shuru.generate_instructions(msg, tax_type, lang)
    filing = _shuru.generate_filing_link(msg, tax_type)
    payment = _shuru.generate_payment_link(msg, tax_type)
    cert = _shuru.generate_compliance_cert_link(msg)

    return {
        "pin": msg,
        "shuru_number": "+254711099999",
        "instructions": instructions,
        "links": {
            "filing": filing,
            "payment": payment,
            "compliance_certificate": cert,
        },
        "timestamp": datetime.now().isoformat(),
    }


@app.get("/shuru/{pin}/pay", tags=["Shuru"], summary="Shuru payment link", dependencies=[Depends(verify_api_key)])
def shuru_payment(pin: str, tax_type: str = "", amount: float = 0):
    """Generate a KRA Shuru WhatsApp deep link for tax payment."""
    ok, msg = validator.validate_pin(pin)
    if not ok:
        raise HTTPException(status_code=400, detail=msg)
    return _shuru.generate_payment_link(msg, tax_type, amount)


# ── The Brain — Learning ─────────────────────────────────────

from agents.learning import DecisionMemory, PatternMiner, FeedbackLoop, ModelUpdater

_brain_memory = DecisionMemory()
_brain_miner = PatternMiner()
_brain_feedback = FeedbackLoop()
_brain_updater = ModelUpdater()


@app.get("/brain", tags=["Brain"], summary="Brain status", dependencies=[Depends(verify_api_key)])
def brain_status():
    """Get The Brain status: decision memory summary and model updater state."""
    return {
        "memory": _brain_memory.summary(),
        "model": _brain_updater.status(),
        "timestamp": datetime.now().isoformat(),
    }


@app.post("/brain/ingest", tags=["Brain"], summary="Ingest historical data", dependencies=[Depends(verify_api_key)])
def brain_ingest():
    """Ingest audit trail and filing history into decision memory for analysis."""
    audit_count = _brain_memory.ingest_audit_trail()
    filing_count = _brain_memory.ingest_filing_history()
    return {
        "audit_entries_ingested": audit_count,
        "filing_records_ingested": filing_count,
        "memory_summary": _brain_memory.summary(),
        "timestamp": datetime.now().isoformat(),
    }


@app.get("/brain/patterns", tags=["Brain"], summary="Mine compliance patterns", dependencies=[Depends(verify_api_key)])
def brain_patterns():
    """Mine decision memory for compliance patterns: late filings, industry trends, seasonal spikes, risk factors."""
    return _brain_miner.mine_all()


@app.get("/brain/feedback", tags=["Brain"], summary="Run feedback loop", dependencies=[Depends(verify_api_key)])
def brain_feedback():
    """Evaluate prediction accuracy: risk model, alert effectiveness, escalation justification."""
    return _brain_feedback.evaluate_all()


@app.post("/brain/propose", tags=["Brain"], summary="Propose model update", dependencies=[Depends(verify_api_key)])
def brain_propose():
    """Analyze feedback and patterns, then propose risk weight adjustments for human review."""
    return _brain_updater.propose_update()


@app.get("/brain/timeline/{pin}", tags=["Brain"], summary="SME compliance timeline", dependencies=[Depends(verify_api_key)])
def brain_timeline(pin: str):
    """Get chronological compliance journey for an SME: checks, filings, alerts, escalations."""
    ok, msg = validator.validate_pin(pin)
    if not ok:
        raise HTTPException(status_code=400, detail=msg)
    timeline = _brain_memory.sme_timeline(msg)
    return {"pin": msg, "timeline": timeline, "count": len(timeline)}


# ── Dashboard — Web UI ──────────────────────────────────────────

@app.get("/ui", tags=["Dashboard"], summary="Web dashboard")
def web_dashboard():
    """Serve the web dashboard HTML page."""
    dashboard_path = ROOT / "dashboard" / "index.html"
    if not dashboard_path.exists():
        raise HTTPException(status_code=404, detail="Dashboard not found")
    return FileResponse(dashboard_path, media_type="text/html")


@app.get("/ui/styles.css", tags=["Dashboard"], summary="Dashboard styles")
def dashboard_styles():
    """Serve the dashboard CSS file."""
    css_path = ROOT / "dashboard" / "styles.css"
    if not css_path.exists():
        raise HTTPException(status_code=404, detail="Styles not found")
    return FileResponse(css_path, media_type="text/css")


@app.get("/ui/dashboard.js", tags=["Dashboard"], summary="Dashboard JavaScript")
def dashboard_js():
    """Serve the dashboard JavaScript file."""
    js_path = ROOT / "dashboard" / "dashboard.js"
    if not js_path.exists():
        raise HTTPException(status_code=404, detail="JavaScript not found")
    return FileResponse(js_path, media_type="application/javascript")


@app.get("/ui/manifest.json", tags=["Dashboard"], summary="PWA manifest")
def dashboard_manifest():
    """Serve the PWA manifest file for mobile installation."""
    manifest_path = ROOT / "dashboard" / "manifest.json"
    if not manifest_path.exists():
        raise HTTPException(status_code=404, detail="Manifest not found")
    return FileResponse(manifest_path, media_type="application/json")


@app.get("/ui/reports", tags=["Dashboard"], summary="Reports page", response_class=HTMLResponse)
def reports_page():
    """Serve an HTML page listing all available reports."""
    reports_dir = ROOT / "output" / "reports"
    rows = ""
    if reports_dir.exists():
        for f in sorted(reports_dir.glob("*.html")):
            pin = f.stem.replace("_report", "")
            name = pin
            profile = orch.load_sme(pin)
            if profile:
                name = f"{profile.get('name', pin)} ({pin})"
            size_kb = f.stat().st_size / 1024
            rows += (
                f'<tr onclick="window.location=\'/report/{pin}\'" style="cursor:pointer">'
                f'<td><strong>{name}</strong></td>'
                f'<td>{size_kb:.1f} KB</td>'
                f'<td><a class="btn-sm" href="/report/{pin}">View</a></td>'
                f'</tr>'
            )
    if not rows:
        rows = '<tr><td colspan="3" style="text-align:center;padding:2rem;color:#888">No reports yet. Run a compliance check first.</td></tr>'

    return HTMLResponse(f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Reports - KRA Deadline Tracker</title>
<link rel="stylesheet" href="/ui/styles.css">
<style>
  .page {{ max-width:900px; margin:0 auto; padding:1.5rem }}
  .page h2 {{ margin-bottom:1rem }}
  table {{ width:100%; border-collapse:collapse; background:#fff; border-radius:8px; overflow:hidden; box-shadow:0 2px 8px rgba(0,0,0,.08) }}
  th {{ background:#1a5f2a; color:#fff; text-align:left; padding:.75rem 1rem; font-weight:600 }}
  td {{ padding:.75rem 1rem; border-bottom:1px solid #eee }}
  tr:hover td {{ background:#f0f9f2 }}
  .btn-sm {{ background:#2d8a3e; color:#fff; padding:6px 14px; border-radius:4px; text-decoration:none; font-size:.85rem }}
  .back {{ display:inline-block; margin-bottom:1rem; color:#1a5f2a; text-decoration:none; font-weight:600 }}
  .back:hover {{ text-decoration:underline }}
</style>
</head>
<body>
<div class="page">
  <a class="back" href="/">&larr; Back to Dashboard</a>
  <h2>Reports</h2>
  <table>
    <thead><tr><th>SME</th><th>Size</th><th></th></tr></thead>
    <tbody>{rows}</tbody>
  </table>
</div>
</body>
</html>""")


@app.get("/ui/audit", tags=["Dashboard"], summary="Audit trail page", response_class=HTMLResponse)
def audit_page(limit: int = 100):
    """Serve an HTML page showing the audit trail."""
    entries = audit.get_history(limit=limit)
    rows = ""
    for e in entries:
        ts = e.get("timestamp", "")[:19].replace("T", " ")
        event = e.get("event_type", "")
        agent = e.get("agent", "")
        pin = e.get("sme_pin") or ""
        details = e.get("details", {})
        status = details.get("compliance_status", details.get("reason", ""))
        risk = details.get("risk_score", "")
        risk_cell = f'{risk}/100' if risk != "" else ""

        badge_cls = ""
        if status == "compliant":
            badge_cls = "badge-green"
        elif status == "at_risk":
            badge_cls = "badge-yellow"
        elif status == "non_compliant":
            badge_cls = "badge-red"

        badge = f'<span class="badge {badge_cls}">{status}</span>' if status else ""

        rows += (
            f'<tr>'
            f'<td class="ts">{ts}</td>'
            f'<td><strong>{event}</strong></td>'
            f'<td>{agent}</td>'
            f'<td>{pin}</td>'
            f'<td>{badge}</td>'
            f'<td>{risk_cell}</td>'
            f'</tr>'
        )
    if not rows:
        rows = '<tr><td colspan="6" style="text-align:center;padding:2rem;color:#888">No audit trail entries yet.</td></tr>'

    return HTMLResponse(f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Audit Trail - KRA Deadline Tracker</title>
<link rel="stylesheet" href="/ui/styles.css">
<style>
  .page {{ max-width:1100px; margin:0 auto; padding:1.5rem }}
  .page h2 {{ margin-bottom:1rem }}
  table {{ width:100%; border-collapse:collapse; background:#fff; border-radius:8px; overflow:hidden; box-shadow:0 2px 8px rgba(0,0,0,.08) }}
  th {{ background:#1a5f2a; color:#fff; text-align:left; padding:.6rem .8rem; font-weight:600; font-size:.85rem; white-space:nowrap }}
  td {{ padding:.55rem .8rem; border-bottom:1px solid #eee; font-size:.85rem }}
  tr:hover td {{ background:#f0f9f2 }}
  .ts {{ white-space:nowrap; color:#666; font-size:.8rem }}
  .badge {{ padding:3px 10px; border-radius:12px; font-size:.75rem; font-weight:600 }}
  .badge-green {{ background:#d4edda; color:#155724 }}
  .badge-yellow {{ background:#fff3cd; color:#856404 }}
  .badge-red {{ background:#f8d7da; color:#721c24 }}
  .back {{ display:inline-block; margin-bottom:1rem; color:#1a5f2a; text-decoration:none; font-weight:600 }}
  .back:hover {{ text-decoration:underline }}
  .count {{ color:#888; font-weight:normal; font-size:.9rem }}
</style>
</head>
<body>
<div class="page">
  <a class="back" href="/">&larr; Back to Dashboard</a>
  <h2>Audit Trail <span class="count">({len(entries)} entries)</span></h2>
  <table>
    <thead><tr><th>Time</th><th>Event</th><th>Agent</th><th>PIN</th><th>Status</th><th>Risk</th></tr></thead>
    <tbody>{rows}</tbody>
  </table>
</div>
</body>
</html>""")


@app.get("/ui/sme/{pin}", tags=["Dashboard"], summary="SME detail page", response_class=HTMLResponse)
def sme_detail_page(pin: str):
    """Serve an HTML page with full SME profile and compliance details."""
    ok, clean_pin = validator.validate_pin(pin)
    if not ok:
        raise HTTPException(status_code=400, detail=clean_pin)

    profile = orch.load_sme(clean_pin)
    if not profile:
        raise HTTPException(status_code=404, detail=f"SME not found: {pin}")

    # Load compliance data
    report_path = ROOT / "data" / "processed" / "obligations" / f"{clean_pin}.json"
    report = {}
    if report_path.exists():
        try:
            report = json.loads(report_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass

    # Profile section
    name = profile.get("name", "Unknown")
    biz = profile.get("business_name", "")
    btype = profile.get("business_type", "").replace("_", " ").title()
    industry = profile.get("industry", "").replace("_", " ").title()
    county = profile.get("county", "")
    turnover = profile.get("annual_turnover_kes", 0)
    phone = profile.get("phone", "")
    email = profile.get("email", "")
    employees = profile.get("employee_count", 0)
    vat = "Yes" if profile.get("is_vat_registered") else "No"
    etims = "Yes" if profile.get("has_etims") else "No"

    # Compliance
    compliance = report.get("compliance", {})
    overall = compliance.get("overall", "unknown")
    badge_cls = {"compliant": "badge-green", "at_risk": "badge-yellow", "non_compliant": "badge-red"}.get(overall, "")
    next_action = compliance.get("next_action", "")
    met = compliance.get("obligations_met", 0)
    total = compliance.get("obligations_total", 0)

    # Risk
    risk = report.get("risk", {})
    risk_score = risk.get("risk_score", "?")
    risk_level = risk.get("risk_level", "unknown")
    risk_factors = risk.get("factors", [])
    factors_html = "".join(f"<li>{f}</li>" for f in risk_factors) if risk_factors else "<li>None</li>"

    # Obligations table
    obligations = report.get("obligations", [])
    obl_rows = ""
    for o in obligations:
        status = o.get("status", "")
        s_cls = {"overdue": "badge-red", "due_soon": "badge-yellow", "upcoming": "badge-green"}.get(status, "")
        days = o.get("days_until_deadline", "")
        days_str = f"{days}d" if days != "" else ""
        obl_rows += (
            f'<tr>'
            f'<td><strong>{o.get("tax_name", "")}</strong></td>'
            f'<td>{o.get("frequency", "")}</td>'
            f'<td>{o.get("next_deadline", "")}</td>'
            f'<td>{days_str}</td>'
            f'<td><span class="badge {s_cls}">{status}</span></td>'
            f'<td>{o.get("rate", "")}</td>'
            f'</tr>'
        )
    if not obl_rows:
        obl_rows = '<tr><td colspan="6" style="text-align:center;padding:1.5rem;color:#888">No obligations data yet.</td></tr>'

    # Penalties
    penalties = report.get("penalties", {})
    penalty_total = penalties.get("total_penalty_exposure_kes", 0)
    severity = penalties.get("severity", "")

    return HTMLResponse(f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{name} — KRA Deadline Tracker</title>
<link rel="stylesheet" href="/ui/styles.css">
<style>
  .page {{ max-width:1000px; margin:0 auto; padding:1.5rem }}
  .back {{ display:inline-block; margin-bottom:1rem; color:#1a5f2a; text-decoration:none; font-weight:600 }}
  .back:hover {{ text-decoration:underline }}
  .profile-header {{ display:flex; justify-content:space-between; align-items:flex-start; flex-wrap:wrap; gap:1rem; margin-bottom:1.5rem }}
  .profile-header h2 {{ margin:0 }}
  .profile-header .sub {{ color:#666; font-size:.9rem }}
  .cards {{ display:grid; grid-template-columns:repeat(auto-fit, minmax(200px,1fr)); gap:1rem; margin-bottom:1.5rem }}
  .card {{ background:#fff; border-radius:8px; padding:1rem; box-shadow:0 2px 8px rgba(0,0,0,.06) }}
  .card .label {{ font-size:.75rem; text-transform:uppercase; color:#888; margin-bottom:.25rem }}
  .card .value {{ font-size:1.3rem; font-weight:700 }}
  .section {{ margin-bottom:1.5rem }}
  .section h3 {{ margin-bottom:.75rem; color:#1a5f2a }}
  table {{ width:100%; border-collapse:collapse; background:#fff; border-radius:8px; overflow:hidden; box-shadow:0 2px 8px rgba(0,0,0,.06) }}
  th {{ background:#1a5f2a; color:#fff; text-align:left; padding:.6rem .8rem; font-weight:600; font-size:.85rem }}
  td {{ padding:.55rem .8rem; border-bottom:1px solid #eee; font-size:.85rem }}
  tr:hover td {{ background:#f0f9f2 }}
  .badge {{ padding:3px 10px; border-radius:12px; font-size:.75rem; font-weight:600 }}
  .badge-green {{ background:#d4edda; color:#155724 }}
  .badge-yellow {{ background:#fff3cd; color:#856404 }}
  .badge-red {{ background:#f8d7da; color:#721c24 }}
  .info-grid {{ display:grid; grid-template-columns:repeat(auto-fit, minmax(180px,1fr)); gap:.5rem 2rem; background:#fff; padding:1rem; border-radius:8px; box-shadow:0 2px 8px rgba(0,0,0,.06) }}
  .info-grid dt {{ font-size:.75rem; text-transform:uppercase; color:#888 }}
  .info-grid dd {{ margin:0 0 .75rem 0; font-weight:600 }}
  .risk-factors {{ list-style:none; padding:0 }}
  .risk-factors li {{ padding:.3rem 0; font-size:.85rem; color:#555 }}
  .disclaimer {{ margin-top:2rem; padding:1rem; background:#fff8e1; border-left:4px solid #ffc107; border-radius:4px; font-size:.75rem; color:#666 }}
</style>
</head>
<body>
<div class="page">
  <a class="back" href="/">&larr; Back to Dashboard</a>

  <div class="profile-header">
    <div>
      <h2>{name}</h2>
      <div class="sub">{biz} &middot; {clean_pin}</div>
    </div>
    <span class="badge {badge_cls}" style="font-size:.9rem;padding:6px 16px">{overall.replace("_"," ").upper()}</span>
  </div>

  <div class="cards">
    <div class="card">
      <div class="label">Risk Score</div>
      <div class="value">{risk_score}/100 <span style="font-size:.7rem;color:#888">({risk_level})</span></div>
    </div>
    <div class="card">
      <div class="label">Obligations</div>
      <div class="value">{met}/{total} met</div>
    </div>
    <div class="card">
      <div class="label">Penalty Exposure</div>
      <div class="value">KES {penalty_total:,.0f}</div>
    </div>
    <div class="card">
      <div class="label">Severity</div>
      <div class="value">{severity.title()}</div>
    </div>
  </div>

  <div class="section">
    <h3>Business Profile</h3>
    <dl class="info-grid">
      <dt>Type</dt><dd>{btype}</dd>
      <dt>Industry</dt><dd>{industry}</dd>
      <dt>County</dt><dd>{county}</dd>
      <dt>Annual Turnover</dt><dd>KES {turnover:,.0f}</dd>
      <dt>Employees</dt><dd>{employees}</dd>
      <dt>VAT Registered</dt><dd>{vat}</dd>
      <dt>eTIMS</dt><dd>{etims}</dd>
      <dt>Phone</dt><dd>{phone}</dd>
      <dt>Email</dt><dd>{email or '—'}</dd>
    </dl>
  </div>

  <div class="section">
    <h3>Tax Obligations</h3>
    {"<p style='margin-bottom:.75rem'><strong>Next action:</strong> " + next_action + "</p>" if next_action else ""}
    <table>
      <thead><tr><th>Tax</th><th>Freq</th><th>Next Deadline</th><th>Days</th><th>Status</th><th>Rate</th></tr></thead>
      <tbody>{obl_rows}</tbody>
    </table>
  </div>

  <div class="section">
    <h3>Risk Factors</h3>
    <ul class="risk-factors">{factors_html}</ul>
  </div>

  <div class="disclaimer">
    DISCLAIMER: This information is generated by an automated system for guidance purposes only.
    It does NOT constitute legal, tax, or financial advice. Always verify with KRA or a registered tax advisor.
  </div>
</div>
</body>
</html>""")


@app.get("/api/stats", tags=["Dashboard"], summary="Dashboard statistics")
def dashboard_stats():
    """Get statistics for the dashboard overview."""
    smes = orch.list_smes()
    total_smes = len(smes)
    
    # Count compliance statuses
    compliant = 0
    at_risk = 0
    non_compliant = 0
    
    for sme in smes:
        pin = sme.get("pin", "")
        report_path = ROOT / "data" / "processed" / "obligations" / f"{pin}.json"
        if report_path.exists():
            try:
                report = json.loads(report_path.read_text(encoding="utf-8"))
                status = report.get("compliance", {}).get("overall", "unknown")
                if status == "compliant":
                    compliant += 1
                elif status == "at_risk":
                    at_risk += 1
                elif status == "non_compliant":
                    non_compliant += 1
            except (json.JSONDecodeError, OSError):
                pass
    
    return {
        "total_smes": total_smes,
        "compliant_smes": compliant,
        "at_risk_smes": at_risk,
        "non_compliant_smes": non_compliant,
        "timestamp": datetime.now().isoformat(),
    }


@app.get("/api/activity", tags=["Dashboard"], summary="Recent activity")
def dashboard_activity(limit: int = 20):
    """Get recent activity for the dashboard."""
    entries = audit.get_history(limit=limit)
    activities = []
    
    for entry in entries:
        activities.append({
            "timestamp": entry.get("timestamp", ""),
            "description": f"{entry.get('event_type', 'Unknown')} - {entry.get('details', {}).get('pin', 'N/A')}",
            "agent": entry.get("agent", "unknown"),
        })
    
    return {"activities": activities, "count": len(activities)}


@app.get("/api/smes", tags=["Dashboard"], summary="List all SMEs")
def api_list_smes():
    """Get list of all SMEs for the dashboard."""
    smes = orch.list_smes()
    sme_list = []
    
    for sme in smes:
        pin = sme.get("pin", "")
        report_path = ROOT / "data" / "processed" / "obligations" / f"{pin}.json"
        compliance_status = "unknown"
        
        if report_path.exists():
            try:
                report = json.loads(report_path.read_text(encoding="utf-8"))
                compliance_status = report.get("compliance", {}).get("overall", "unknown")
            except (json.JSONDecodeError, OSError):
                pass
        
        sme_list.append({
            "pin": pin,
            "name": sme.get("name", "Unknown"),
            "business_name": sme.get("business_name", ""),
            "compliance_status": compliance_status,
            "active": sme.get("active", True),
        })
    
    return {"smes": sme_list, "count": len(sme_list)}


@app.get("/api/smes/{pin}", tags=["Dashboard"], summary="Get SME detail")
def api_get_sme(pin: str):
    """Get full SME profile for the dashboard."""
    ok, msg = validator.validate_pin(pin)
    if not ok:
        raise HTTPException(status_code=400, detail=msg)

    profile = orch.load_sme(msg)
    if not profile:
        raise HTTPException(status_code=404, detail=f"SME not found: {pin}")

    # Enrich with latest compliance data
    report_path = ROOT / "data" / "processed" / "obligations" / f"{msg}.json"
    compliance = {}
    if report_path.exists():
        try:
            compliance = json.loads(report_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass

    return {**profile, "latest_report": compliance}


@app.get("/api/reports", tags=["Dashboard"], summary="List reports")
def api_list_reports():
    """Get list of available reports."""
    reports_dir = ROOT / "output" / "reports"
    reports = []
    
    if reports_dir.exists():
        for report_file in reports_dir.glob("*.html"):
            pin = report_file.stem.replace("_report", "")
            reports.append({
                "filename": report_file.name,
                "path": f"/report/{pin}",
                "size": report_file.stat().st_size,
            })
    
    return {"reports": reports, "count": len(reports)}


@app.get("/api/monitoring/status", tags=["Dashboard"], summary="Monitoring status")
def api_monitoring_status():
    """Get monitoring system status."""
    try:
        from agents.monitoring.monitoring_orchestrator import MonitoringOrchestrator
        monitor = MonitoringOrchestrator()
        status = monitor.get_status()
        return status
    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.get("/api/audit", tags=["Dashboard"], summary="Audit trail")
def api_audit_trail(limit: int = 50):
    """Get audit trail entries."""
    entries = audit.get_history(limit=limit)
    return {"entries": entries, "count": len(entries)}


@app.post("/api/check", tags=["Dashboard"], summary="Run compliance check")
def api_run_check():
    """Run compliance check for all SMEs."""
    try:
        results = orch.check_all()
        return {
            "status": "completed",
            "results": results,
            "count": len(results),
            "timestamp": datetime.now().isoformat(),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/proactive", tags=["Dashboard"], summary="Proactive recommendations")
def api_proactive_recommendations():
    """Get proactive recommendations for all SMEs."""
    try:
        from agents.action.proactive_engine import ProactiveEngine
        engine = ProactiveEngine()
        smes = orch.list_smes()
        recommendations = []
        
        for sme in smes:
            pin = sme.get("pin", "")
            if pin:
                recs = engine.analyze_and_recommend(pin)
                if recs.get("recommendations"):
                    recommendations.extend(recs["recommendations"])
        
        return {
            "recommendations": recommendations,
            "count": len(recommendations),
            "timestamp": datetime.now().isoformat(),
        }
    except Exception as e:
        return {"recommendations": [], "count": 0, "error": str(e)}


@app.get("/api/shuru/{pin}", tags=["Dashboard"], summary="Shuru links for dashboard")
def api_shuru_links(pin: str, lang: str = "en"):
    """Get KRA Shuru WhatsApp links for the dashboard (no auth)."""
    ok, msg = validator.validate_pin(pin)
    if not ok:
        raise HTTPException(status_code=400, detail=msg)
    instructions = _shuru.generate_instructions(msg, lang=lang)
    filing = _shuru.generate_filing_link(msg)
    payment = _shuru.generate_payment_link(msg)
    cert = _shuru.generate_compliance_cert_link(msg)
    return {
        "pin": msg,
        "shuru_number": "+254711099999",
        "instructions": instructions,
        "links": {"filing": filing, "payment": payment, "compliance_certificate": cert},
    }


# ── Public Signup (no auth) ───────────────────────────────────────

@app.post("/signup", tags=["Subscriptions"], summary="Public signup")
@limiter.limit("5/minute")
def public_signup(request: Request, req: SignupRequest):
    """
    Public endpoint — onboard an SME and start a 7-day free trial.
    No API key required. After trial, pay via M-Pesa to continue receiving reports.
    """
    data = req.model_dump()
    if not data.get("business_name"):
        data["business_name"] = data["name"]
    data["preferred_channel"] = "whatsapp"

    existing = orch.load_sme(data["pin"])
    if existing:
        # Already onboarded — return current subscription (no new trial)
        sub = subs.get(data["pin"])
        if not sub:
            # First time — hasn't had a trial yet, start one
            sub = subs.start_trial(data["pin"], data["name"])
        elif sub["status"] == "expired" and sub.get("plan") == "trial":
            # Trial expired — don't give another free trial, ask them to pay
            return {
                "status": "trial_expired",
                "pin": data["pin"],
                "name": existing["name"],
                "message": "Your free trial has expired. Pay via M-Pesa to continue.",
                "subscription": sub,
                "payment": subs.get_payment_instructions(data["pin"]),
            }
        return {
            "status": "already_onboarded",
            "pin": data["pin"],
            "name": existing["name"],
            "subscription": sub,
            "payment": subs.get_payment_instructions(data["pin"]),
        }

    profile = orch.onboard(interactive=False, data=data)
    if not profile:
        raise HTTPException(status_code=500, detail="Onboarding failed")

    sub = subs.start_trial(data["pin"], data["name"])

    # Send welcome message via WhatsApp bot
    obligations = profile.get("classification", {}).get("obligations", [])
    ob_list = ", ".join(o.replace("_", " ").title() for o in obligations)
    welcome_msg = (
        f"*Welcome to KRA Deadline Tracker!* \n\n"
        f"Hi {profile['name'].split()[0]}, your business has been registered.\n\n"
        f"*Your tax obligations:*\n{ob_list}\n\n"
        f"You have a *7-day free trial*. "
        f"We'll send you deadline alerts, risk reports, and filing instructions right here on WhatsApp.\n\n"
        f"To continue after the trial, pay *KES 500/month* via M-Pesa:\n"
        f"Send to *0114179880*\n"
        f"Reference: *KRADTC-{profile['pin']}*\n\n"
        f"File taxes via KRA Shuru: https://wa.me/254711099999"
    )
    if data.get("phone"):
        _wa.send(data["phone"], welcome_msg, profile["pin"])

    return {
        "status": "signed_up",
        "pin": profile["pin"],
        "name": profile["name"],
        "obligations": obligations,
        "subscription": sub,
        "payment": subs.get_payment_instructions(profile["pin"]),
    }


# ── WhatsApp Onboarding Webhook ────────────────────────────────────────

class WhatsAppIncoming(BaseModel):
    sender: str
    text: str


@app.post("/webhook/whatsapp", tags=["Webhooks"], summary="WhatsApp incoming messages")
def whatsapp_webhook(msg: WhatsAppIncoming):
    """Handle incoming WhatsApp messages - send onboarding link."""
    phone = msg.sender
    
    # Send onboarding link
    app_url = os.getenv("APP_URL", "https://kra-deadline-tracker.onrender.com")
    onboarding_link = f"{app_url}/onboard"
    
    reply = (
        f"👋 *Welcome to KRA Deadline Tracker!*\n\n"
        f"I'll help you stay compliant with KRA tax deadlines.\n\n"
        f"To get started, click below:\n{onboarding_link}\n\n"
        f"It takes 2 minutes to set up your business profile."
    )
    
    try:
        _wa.send(phone, reply)
    except Exception:
        pass
    
    return {"status": "sent"}


@app.get("/bot/status", tags=["System"], summary="WhatsApp bot status")
def bot_status():
    """Check if the WhatsApp bot is connected and ready to send messages."""
    return _wa.bot_status()


@app.get("/plans", tags=["Subscriptions"], summary="Available plans")
@limiter.limit("30/minute")
def get_plans(request: Request):
    """Public endpoint — list subscription plans and pricing."""
    return {
        "mpesa_number": "0114179880",
        "plans": subs.get_plans(),
    }


@app.get("/subscription/{pin}", tags=["Subscriptions"], summary="Check subscription")
@limiter.limit("10/minute")
def check_subscription(request: Request, pin: str):
    """Public endpoint — check subscription status for a PIN."""
    ok, msg = validator.validate_pin(pin)
    if not ok:
        raise HTTPException(status_code=400, detail=msg)
    sub = subs.get(msg)
    if not sub:
        raise HTTPException(status_code=404, detail=f"No subscription found for {pin}")
    active = subs.is_active(msg)
    return {
        "pin": msg,
        "active": active,
        "subscription": sub,
        "payment": subs.get_payment_instructions(msg) if not active else None,
    }


@app.get("/pay/{pin}", tags=["Subscriptions"], summary="Payment instructions")
@limiter.limit("10/minute")
def payment_instructions(request: Request, pin: str, plan: str = "monthly"):
    """Public endpoint — get M-Pesa payment instructions for a PIN."""
    ok, msg = validator.validate_pin(pin)
    if not ok:
        raise HTTPException(status_code=400, detail=msg)
    return subs.get_payment_instructions(msg, plan)


# ── Admin subscription management (dashboard routes — no auth) ─────

@app.get("/api/subscriptions", tags=["Subscriptions"], summary="List all subscriptions")
def list_subscriptions():
    """List all subscriptions with status."""
    all_subs = subs.list_all()
    active = [s for s in all_subs if s["status"] == "active"]
    expired = [s for s in all_subs if s["status"] != "active"]
    return {
        "total": len(all_subs),
        "active": len(active),
        "expired": len(expired),
        "subscriptions": all_subs,
    }


@app.post("/api/subscriptions/confirm", tags=["Subscriptions"],
          summary="Confirm M-Pesa payment")
def confirm_payment(req: PaymentConfirmRequest):
    """Confirm an M-Pesa payment and activate subscription. Sends confirmation via WhatsApp."""
    ok, msg = validator.validate_pin(req.pin)
    if not ok:
        raise HTTPException(status_code=400, detail=msg)
    sub = subs.confirm_payment(msg, req.mpesa_ref, req.amount_kes, req.plan, req.phone)

    # Send payment confirmation via WhatsApp
    profile = orch.load_sme(msg)
    if profile and profile.get("phone"):
        from tools.wa_report_formatter import format_payment_confirmation
        confirm_msg = format_payment_confirmation(profile, sub["plan_name"], sub["expires_at"])
        _wa.send(profile["phone"], confirm_msg, msg)

    return {"status": "confirmed", "subscription": sub}


@app.post("/api/subscriptions/{pin}/deactivate", tags=["Subscriptions"],
          summary="Deactivate subscription")
def deactivate_subscription(pin: str):
    """Deactivate a subscription."""
    ok, msg = validator.validate_pin(pin)
    if not ok:
        raise HTTPException(status_code=400, detail=msg)
    sub = subs.deactivate(msg)
    if not sub:
        raise HTTPException(status_code=404, detail=f"No subscription found for {pin}")
    return {"status": "deactivated", "subscription": sub}


# ── M-Pesa STK Push (pay via API) ─────────────────────────────────

from integrations.mpesa import STKPush, MpesaConfig
_mpesa_config = MpesaConfig()
_stk = STKPush(_mpesa_config)


@app.post("/api/pay-stk/{pin}", tags=["Subscriptions"],
          summary="Initiate M-Pesa STK Push payment")
@limiter.limit("3/minute")
def initiate_stk_push(request: Request, pin: str, plan: str = "monthly"):
    """Trigger M-Pesa payment prompt on the customer's phone.
    The customer enters their M-Pesa PIN to complete payment.
    Result is delivered via webhook to /webhooks/mpesa/stk-result.
    """
    ok, msg = validator.validate_pin(pin)
    if not ok:
        raise HTTPException(status_code=400, detail=msg)

    profile = orch.load_sme(msg)
    if not profile:
        raise HTTPException(status_code=404, detail=f"SME not found: {pin}")
    if not profile.get("phone"):
        raise HTTPException(status_code=400, detail="No phone number on file for this SME")

    plan_info = subs.get_plans().get(plan)
    if not plan_info:
        raise HTTPException(status_code=400, detail=f"Invalid plan: {plan}. Use: monthly, quarterly, annual")

    account_ref = f"KRADTC-{msg}"
    result = _stk.initiate(
        phone=profile["phone"],
        amount=plan_info["price_kes"],
        account_reference=account_ref,
        transaction_desc=f"KRA {plan_info['name']}",
    )
    return result


@app.post("/api/mpesa/register-c2b", tags=["Subscriptions"],
          summary="Register C2B URLs with Safaricom",
          dependencies=[Depends(verify_api_key)])
def register_c2b_urls():
    """Register C2B validation and confirmation URLs with Safaricom.
    Required once before Safaricom will send C2B payment webhooks.
    Uses MPESA_CALLBACK_URL env var or constructs from RENDER_EXTERNAL_URL.
    """
    render_url = os.getenv("RENDER_EXTERNAL_URL", "")
    base = render_url or "http://localhost:8000"
    confirmation_url = f"{base}/webhooks/mpesa/c2b-confirmation"
    validation_url = f"{base}/webhooks/mpesa/c2b-validation"

    result = _stk.register_c2b_urls(
        validation_url=validation_url,
        confirmation_url=confirmation_url,
    )
    result["confirmation_url"] = confirmation_url
    result["validation_url"] = validation_url
    return result


@app.post("/api/mpesa/stk-query/{checkout_id}", tags=["Subscriptions"],
          summary="Query STK Push status",
          dependencies=[Depends(verify_api_key)])
def query_stk_status(checkout_id: str):
    """Query the status of an STK Push transaction."""
    return _stk.query_status(checkout_id)


# ── WhatsApp Bot Actions ──────────────────────────────────────────

@app.post("/api/send-report/{pin}", tags=["Actions"],
          summary="Send compliance report via WhatsApp")
def send_report_whatsapp(pin: str):
    """Run compliance check and send the full report to the SME's WhatsApp."""
    ok, msg = validator.validate_pin(pin)
    if not ok:
        raise HTTPException(status_code=400, detail=msg)

    # Check subscription
    if not subs.is_active(msg):
        raise HTTPException(status_code=402, detail=f"Subscription inactive for {pin}. Pay to receive reports.")

    profile = orch.load_sme(msg)
    if not profile:
        raise HTTPException(status_code=404, detail=f"SME not found: {pin}")
    if not profile.get("phone"):
        raise HTTPException(status_code=400, detail="No phone number on file")

    # Run compliance check
    result = orch.check_sme(msg)
    if not result:
        raise HTTPException(status_code=500, detail="Compliance check failed")

    # Format and send
    from tools.wa_report_formatter import format_compliance_report
    report_msg = format_compliance_report(result)
    send_result = _wa.send(profile["phone"], report_msg, msg)

    return {
        "status": "sent" if send_result.get("success") else "dry_run",
        "pin": msg,
        "phone": profile["phone"],
        "compliance": result["compliance"]["overall"],
        "delivery": send_result,
    }


@app.post("/api/send-reports-all", tags=["Actions"],
          summary="Send reports to all active subscribers")
def send_reports_all():
    """Run compliance check and send WhatsApp reports to all active subscribers."""
    active_subs = subs.list_active()
    results = []

    for sub in active_subs:
        pin = sub["pin"]
        try:
            profile = orch.load_sme(pin)
            if not profile or not profile.get("phone"):
                results.append({"pin": pin, "status": "skipped", "reason": "no_phone"})
                continue

            check = orch.check_sme(pin)
            if not check:
                results.append({"pin": pin, "status": "skipped", "reason": "check_failed"})
                continue

            from tools.wa_report_formatter import format_compliance_report
            report_msg = format_compliance_report(check)
            send_result = _wa.send(profile["phone"], report_msg, pin)
            results.append({
                "pin": pin,
                "name": profile["name"],
                "status": "sent" if send_result.get("success") else "dry_run",
            })
        except Exception as e:
            results.append({"pin": pin, "status": "error", "error": str(e)})

    sent = sum(1 for r in results if r["status"] == "sent")
    return {"total": len(active_subs), "sent": sent, "results": results}


@app.post("/api/deliver-alerts", tags=["Actions"],
          summary="Deliver pending alerts via WhatsApp")
def deliver_pending_alerts():
    """Process and deliver all pending alerts from the staging queue via WhatsApp bot."""
    from agents.action.alert_engine import AlertEngine
    engine = AlertEngine()
    results = engine.process_queue()
    return {
        "delivered": len(results),
        "results": results,
    }


# ── Data Rights (Kenya Data Protection Act / GDPR) ────────────────

@app.delete("/api/smes/{pin}", tags=["SMEs"],
            summary="Delete all SME data",
            dependencies=[Depends(verify_api_key)])
def delete_sme_data(pin: str):
    """Permanently delete all data for an SME (Kenya Data Protection Act compliance).
    Removes: profile, obligations, filings, subscription, audit entries, staging files.
    """
    ok, msg = validator.validate_pin(pin)
    if not ok:
        raise HTTPException(status_code=400, detail=msg)

    deleted = []
    # Profile
    profile_path = ROOT / "data" / "confirmed" / "sme_profiles" / f"sme_{msg}.json"
    if profile_path.exists():
        profile_path.unlink()
        deleted.append("profile")
    # Obligations
    ob_path = ROOT / "data" / "processed" / "obligations" / f"{msg}.json"
    if ob_path.exists():
        ob_path.unlink()
        deleted.append("obligations")
    # Staging files
    for f in (ROOT / "staging" / "review").glob(f"*{msg}*"):
        f.unlink()
        deleted.append(f"staging/{f.name}")
    # Subscription
    sub = subs.get(msg)
    if sub:
        subs.deactivate(msg)
        deleted.append("subscription")
    # Filings
    filing_path = ROOT / "data" / "filings" / f"{msg}.json"
    if filing_path.exists():
        filing_path.unlink()
        deleted.append("filings")
    # Remove from SME registry
    sme_registry = ROOT / "config" / "smes.json"
    if sme_registry.exists():
        try:
            reg = json.loads(sme_registry.read_text(encoding="utf-8"))
            original = len(reg.get("smes", []))
            reg["smes"] = [s for s in reg.get("smes", []) if s.get("pin") != msg]
            if len(reg["smes"]) < original:
                sme_registry.write_text(json.dumps(reg, indent=2, ensure_ascii=False), encoding="utf-8")
                deleted.append("registry")
        except (json.JSONDecodeError, KeyError):
            pass

    audit.record("DATA_DELETE", "api", {"pin": msg, "deleted": deleted})

    if not deleted:
        raise HTTPException(status_code=404, detail=f"No data found for {pin}")
    return {"status": "deleted", "pin": msg, "deleted_items": deleted}


@app.get("/api/smes/{pin}/export", tags=["SMEs"],
         summary="Export all SME data",
         dependencies=[Depends(verify_api_key)])
def export_sme_data(pin: str):
    """Export all data for an SME in machine-readable JSON (GDPR data portability)."""
    ok, msg = validator.validate_pin(pin)
    if not ok:
        raise HTTPException(status_code=400, detail=msg)

    export = {"pin": msg, "exported_at": datetime.now().isoformat()}

    profile = orch.load_sme(msg)
    if not profile:
        raise HTTPException(status_code=404, detail=f"SME not found: {pin}")
    export["profile"] = profile

    ob_path = ROOT / "data" / "processed" / "obligations" / f"{msg}.json"
    if ob_path.exists():
        export["obligations"] = json.loads(ob_path.read_text(encoding="utf-8"))

    filing_path = ROOT / "data" / "filings" / f"{msg}.json"
    if filing_path.exists():
        export["filings"] = json.loads(filing_path.read_text(encoding="utf-8"))

    sub = subs.get(msg)
    if sub:
        export["subscription"] = sub

    audit.record("DATA_EXPORT", "api", {"pin": msg})
    return export


# ── Legal Pages ────────────────────────────────────────────────────

@app.get("/privacy", tags=["System"], summary="Privacy policy",
         response_class=HTMLResponse, include_in_schema=False)
def privacy_policy():
    return HTMLResponse("""<!DOCTYPE html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Privacy Policy — KRA Deadline Tracker</title>
<style>body{font-family:Inter,system-ui,sans-serif;max-width:700px;margin:40px auto;padding:0 20px;line-height:1.7;color:#1a1a2e}
h1{color:#16213e}h2{color:#0f3460;margin-top:2em}a{color:#e94560}</style></head><body>
<h1>Privacy Policy</h1>
<p><strong>Last updated:</strong> April 2026</p>
<p>KRA Deadline Tracker & Compliance Tool ("we", "us") respects your privacy and complies with the Kenya Data Protection Act, 2019.</p>

<h2>1. Data We Collect</h2>
<ul>
<li><strong>KRA PIN</strong> — to identify your tax obligations</li>
<li><strong>Business name & type</strong> — to classify your obligations</li>
<li><strong>Phone number</strong> — to deliver WhatsApp alerts (encrypted at rest)</li>
<li><strong>M-Pesa transaction details</strong> — for subscription payments</li>
<li><strong>Email</strong> (optional) — for account recovery</li>
</ul>

<h2>2. How We Use Your Data</h2>
<ul>
<li>Map and track your KRA tax obligations and deadlines</li>
<li>Send deadline alerts and compliance reports via WhatsApp</li>
<li>Process M-Pesa subscription payments</li>
<li>Improve our tax compliance intelligence</li>
</ul>

<h2>3. Data Security</h2>
<ul>
<li>Phone numbers are <strong>encrypted at rest</strong> using industry-standard encryption (Fernet/AES)</li>
<li>All data transmitted over <strong>HTTPS</strong></li>
<li>API access protected by authentication keys</li>
<li>Rate limiting on all public endpoints</li>
</ul>

<h2>4. Your Rights (Kenya Data Protection Act)</h2>
<p>You have the right to:</p>
<ul>
<li><strong>Access</strong> your data — <code>GET /api/smes/{pin}/export</code></li>
<li><strong>Delete</strong> your data — <code>DELETE /api/smes/{pin}</code></li>
<li><strong>Correct</strong> inaccurate data — contact us</li>
<li><strong>Object</strong> to processing — unsubscribe via WhatsApp (reply STOP)</li>
</ul>

<h2>5. Data Retention</h2>
<p>We retain your data while your subscription is active. After expiry, data is retained for <strong>90 days</strong> then permanently deleted upon request.</p>

<h2>6. Third Parties</h2>
<p>We do not sell your data. We share data only with:</p>
<ul>
<li><strong>Safaricom M-Pesa</strong> — for payment processing</li>
<li><strong>WhatsApp</strong> — for delivering compliance alerts</li>
</ul>

<h2>7. Contact</h2>
<p>Data Controller: KRA Deadline Tracker<br>
Email: support@kradeadlinetracker.co.ke<br>
Phone: 0114179880</p>
</body></html>""")


@app.get("/terms", tags=["System"], summary="Terms of service",
         response_class=HTMLResponse, include_in_schema=False)
def terms_of_service():
    return HTMLResponse("""<!DOCTYPE html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Terms of Service — KRA Deadline Tracker</title>
<style>body{font-family:Inter,system-ui,sans-serif;max-width:700px;margin:40px auto;padding:0 20px;line-height:1.7;color:#1a1a2e}
h1{color:#16213e}h2{color:#0f3460;margin-top:2em}a{color:#e94560}</style></head><body>
<h1>Terms of Service</h1>
<p><strong>Last updated:</strong> April 2026</p>

<h2>1. Service Description</h2>
<p>KRA Deadline Tracker & Compliance Tool provides automated tax obligation tracking, deadline alerts, and compliance reporting for Kenyan SMEs. This service is for <strong>informational purposes only</strong>.</p>

<h2>2. Disclaimer</h2>
<p><strong>This service does NOT constitute legal, tax, or financial advice.</strong> Tax laws change frequently. Always verify with the Kenya Revenue Authority (KRA) or a registered tax advisor before making any filing or payment decisions. We are not liable for any penalties, losses, or decisions made based on this information.</p>

<h2>3. Subscription & Payments</h2>
<ul>
<li>Free trial: 7 days, no payment required</li>
<li>Monthly: KES 500 | Quarterly: KES 1,200 | Annual: KES 4,000</li>
<li>Payment via M-Pesa to 0114179880</li>
<li>Subscriptions auto-expire; no auto-renewal charges</li>
<li>No refunds after subscription activation</li>
</ul>

<h2>4. Acceptable Use</h2>
<p>You agree not to:</p>
<ul>
<li>Provide false KRA PINs or business information</li>
<li>Use the service for tax evasion or fraud</li>
<li>Abuse the API with excessive requests</li>
<li>Resell or redistribute compliance reports</li>
</ul>

<h2>5. Service Availability</h2>
<p>We aim for 99% uptime but do not guarantee uninterrupted service. KRA tax rates and deadlines may change without notice.</p>

<h2>6. Termination</h2>
<p>You may cancel at any time by replying STOP on WhatsApp or requesting data deletion. We may terminate accounts that violate these terms.</p>

<h2>7. Governing Law</h2>
<p>These terms are governed by the laws of Kenya. Disputes shall be resolved in Nairobi courts.</p>

<h2>8. Contact</h2>
<p>KRA Deadline Tracker<br>
Email: support@kradeadlinetracker.co.ke<br>
Phone: 0114179880</p>
</body></html>""")


# ── React Router catch-all (must be LAST) ─────────────────────────

@app.get("/{path:path}", include_in_schema=False)
def react_catch_all(path: str):
    """Serve React index.html for client-side routes (/signup, /welcome/*, etc.)."""
    react_dashboard = ROOT / "output" / "dashboard-react" / "index.html"
    if react_dashboard.exists():
        return FileResponse(react_dashboard, media_type="text/html")
    raise HTTPException(status_code=404, detail="Not found")
