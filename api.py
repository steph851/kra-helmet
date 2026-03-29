"""
KRA HELMET — REST API
Usage: uvicorn api:app --reload --port 8000
"""
import sys
import os
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
from fastapi.responses import HTMLResponse, JSONResponse
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
    description="Tax Compliance Autopilot for Kenyan SMEs",
    version=settings["system"]["version"],
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

@app.get("/")
def root():
    return {
        "service": settings["system"]["name"],
        "version": settings["system"]["version"],
        "status": "running",
        "auth_required": settings["api"].get("require_auth", True) and bool(API_KEY),
        "endpoints": {
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


@app.get("/smes", dependencies=[Depends(verify_api_key)])
def list_smes():
    """List all onboarded SMEs."""
    smes = orch.list_smes()
    return {"count": len(smes), "smes": smes}


@app.get("/smes/{pin}", dependencies=[Depends(verify_api_key)])
def get_sme(pin: str):
    """Get SME profile."""
    ok, msg = validator.validate_pin(pin)
    if not ok:
        raise HTTPException(status_code=400, detail=msg)

    profile = orch.load_sme(msg)  # msg is the cleaned PIN
    if not profile:
        raise HTTPException(status_code=404, detail=f"SME not found: {pin}")
    return profile


@app.post("/onboard", dependencies=[Depends(verify_api_key)])
def onboard_sme(req: OnboardRequest):
    """Onboard a new SME."""
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


@app.get("/check/{pin}", dependencies=[Depends(verify_api_key)])
def check_sme(pin: str):
    """Run full compliance check for an SME."""
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


@app.get("/check", dependencies=[Depends(verify_api_key)])
def check_all():
    """Run compliance check for all SMEs."""
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


@app.post("/file/{pin}", dependencies=[Depends(verify_api_key)])
def record_filing(pin: str, req: FilingRequest):
    """Record a tax filing for an SME."""
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


@app.get("/filings/{pin}", dependencies=[Depends(verify_api_key)])
def get_filings(pin: str, tax_type: str | None = None):
    """Get filing history for an SME."""
    ok, msg = validator.validate_pin(pin)
    if not ok:
        raise HTTPException(status_code=400, detail=msg)

    filings = tracker.get_filings(msg, tax_type)
    summary = tracker.get_filing_summary(msg)
    return {"pin": msg, "summary": summary, "filings": filings}


@app.get("/dashboard", response_class=HTMLResponse)
def dashboard():
    """Generate and serve the HTML dashboard (live, not static)."""
    gen = DashboardGenerator()
    output_path = gen.generate()
    return output_path.read_text(encoding="utf-8")


@app.get("/report/{pin}", response_class=HTMLResponse, dependencies=[Depends(verify_api_key)])
def report(pin: str):
    """Generate and serve a per-SME HTML report."""
    ok, msg = validator.validate_pin(pin)
    if not ok:
        raise HTTPException(status_code=400, detail=msg)

    gen = ReportGenerator()
    output_path = gen.generate(msg)
    if not output_path:
        raise HTTPException(status_code=404, detail=f"SME not found: {pin}")
    return output_path.read_text(encoding="utf-8")


@app.get("/audit", dependencies=[Depends(verify_api_key)])
def audit_log(pin: str | None = None, limit: int = 50):
    """Get audit trail."""
    if pin:
        ok, msg = validator.validate_pin(pin)
        if not ok:
            raise HTTPException(status_code=400, detail=msg)
        pin = msg
    entries = audit.get_history(sme_pin=pin, limit=limit)
    return {"count": len(entries), "entries": entries}


@app.get("/guides")
def list_guides():
    """List available filing guides."""
    import json
    guides_path = ROOT / "intelligence" / "filing_guides.json"
    data = json.loads(guides_path.read_text(encoding="utf-8"))
    return {
        "count": len(data["filing_guides"]),
        "guides": [{"tax_key": g["tax_key"], "title": g["title"]} for g in data["filing_guides"]],
    }


@app.get("/guides/{tax_key}")
def get_guide(tax_key: str):
    """Get a specific filing guide."""
    import json
    guides_path = ROOT / "intelligence" / "filing_guides.json"
    data = json.loads(guides_path.read_text(encoding="utf-8"))
    guide = next((g for g in data["filing_guides"] if g["tax_key"] == tax_key.lower()), None)
    if not guide:
        raise HTTPException(status_code=404, detail=f"Guide not found: {tax_key}")
    return guide
