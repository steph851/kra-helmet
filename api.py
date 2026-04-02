"""
KRA HELMET — REST API
Usage: uvicorn api:app --reload --port 8000
"""
import sys
import os
import json
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

from fastapi import FastAPI, HTTPException, Depends, Security, Request
from fastapi.security import APIKeyHeader
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, field_validator
import re

from agents.orchestrator import Orchestrator
from agents.dashboard import DashboardGenerator
from agents.report_generator import ReportGenerator
from agents.validation.input_validator import InputValidator
from workflow.filing_tracker import FilingTracker
from workflow.audit_trail import AuditTrail
from config.loader import get_settings

settings = get_settings()

app = FastAPI(
    title="KRA HELMET API",
    description=(
        "Tax Compliance Autopilot for Kenyan SMEs.\n\n"
        "KRA Helmet maps your tax obligations, tracks every KRA deadline, "
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
        {"name": "Brain", "description": "The Brain — learning, patterns, feedback, model updates"},
    ],
)

orch = Orchestrator()
tracker = FilingTracker()
audit = AuditTrail()
validator = InputValidator()


# ── Authentication ──────────────────────────────────────────────

API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)
API_KEY = os.getenv("HELMET_API_KEY", "")


async def verify_api_key(api_key: str = Security(API_KEY_HEADER)):
    """Verify API key if auth is required."""
    if not settings["api"].get("require_auth", True):
        return True
    if not API_KEY:
        import logging
        logging.getLogger("kra_helmet.api").warning(
            "HELMET_API_KEY not set — all endpoints are unauthenticated. "
            "Set HELMET_API_KEY in .env to enable authentication."
        )
        return True  # no key configured = auth disabled
    if api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid or missing API key. Set X-API-Key header.")
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


# ── Endpoints ───────────────────────────────────────────────────

@app.get("/", tags=["System"], summary="Web dashboard", response_class=HTMLResponse)
def root():
    """Serve the web dashboard at the root URL."""
    dashboard_path = ROOT / "dashboard" / "index.html"
    if not dashboard_path.exists():
        # Fallback to JSON if dashboard not built
        return {
            "service": settings["system"]["name"],
            "version": settings["system"]["version"],
            "status": "running",
            "auth_required": settings["api"].get("require_auth", True) and bool(API_KEY),
            "endpoints": {
                "health": "/health",
                "smes": "/smes",
                "check": "/check/{pin}",
                "onboard": "POST /onboard",
                "filing": "POST /file/{pin}",
                "dashboard": "/dashboard",
                "report": "/report/{pin}",
                "audit": "/audit",
                "guides": "/guides",
            }
        }
    return dashboard_path.read_text(encoding="utf-8")


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

    # Overall
    all_ok = all(
        c.get("status") in ("ok", "enabled", "disabled", "not_started")
        for c in checks.values()
    )

    return {
        "status": "healthy" if all_ok else "degraded",
        "timestamp": datetime.now().isoformat(),
        "checks": checks,
    }


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


@app.get("/report/{pin}", tags=["Reports"], summary="SME report", response_class=HTMLResponse, dependencies=[Depends(verify_api_key)])
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
async def start_pulse():
    """Start The Pulse scheduler when the API starts (if enabled)."""
    global _pulse
    if settings.get("scheduler", {}).get("start_with_api", True):
        _pulse = Heartbeat()
        _pulse.start(daemon=True)


@app.on_event("shutdown")
async def stop_pulse():
    """Stop The Pulse on shutdown."""
    if _pulse and _pulse.is_running:
        _pulse.stop()


# Mount webhook router
_webhook_router = create_webhook_router(_pulse_queue)
app.include_router(_webhook_router)


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

@app.get("/ui", tags=["Dashboard"], summary="Web dashboard", response_class=HTMLResponse)
def web_dashboard():
    """Serve the web dashboard HTML page."""
    dashboard_path = ROOT / "dashboard" / "index.html"
    if not dashboard_path.exists():
        raise HTTPException(status_code=404, detail="Dashboard not found")
    return dashboard_path.read_text(encoding="utf-8")


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


@app.get("/api/stats", tags=["Dashboard"], summary="Dashboard statistics", dependencies=[Depends(verify_api_key)])
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


@app.get("/api/activity", tags=["Dashboard"], summary="Recent activity", dependencies=[Depends(verify_api_key)])
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


@app.get("/api/smes", tags=["Dashboard"], summary="List all SMEs", dependencies=[Depends(verify_api_key)])
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


@app.get("/api/reports", tags=["Dashboard"], summary="List reports", dependencies=[Depends(verify_api_key)])
def api_list_reports():
    """Get list of available reports."""
    reports_dir = ROOT / "output" / "reports"
    reports = []
    
    if reports_dir.exists():
        for report_file in reports_dir.glob("*.html"):
            reports.append({
                "filename": report_file.name,
                "path": f"/output/reports/{report_file.name}",
                "size": report_file.stat().st_size,
            })
    
    return {"reports": reports, "count": len(reports)}


@app.get("/api/monitoring/status", tags=["Dashboard"], summary="Monitoring status", dependencies=[Depends(verify_api_key)])
def api_monitoring_status():
    """Get monitoring system status."""
    try:
        from agents.monitoring.monitoring_orchestrator import MonitoringOrchestrator
        monitor = MonitoringOrchestrator()
        status = monitor.get_status()
        return status
    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.get("/api/audit", tags=["Dashboard"], summary="Audit trail", dependencies=[Depends(verify_api_key)])
def api_audit_trail(limit: int = 50):
    """Get audit trail entries."""
    entries = audit.get_history(limit=limit)
    return {"entries": entries, "count": len(entries)}


@app.post("/api/check", tags=["Dashboard"], summary="Run compliance check", dependencies=[Depends(verify_api_key)])
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


@app.get("/api/proactive", tags=["Dashboard"], summary="Proactive recommendations", dependencies=[Depends(verify_api_key)])
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
