"""
KRA HELMET — REST API
Usage: uvicorn api:app --reload --port 8000
"""
import sys
import os
from pathlib import Path

# Fix Windows console encoding
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, FileResponse
from pydantic import BaseModel

from agents.orchestrator import Orchestrator
from agents.dashboard import DashboardGenerator
from agents.report_generator import ReportGenerator
from workflow.filing_tracker import FilingTracker
from workflow.audit_trail import AuditTrail

app = FastAPI(
    title="KRA HELMET API",
    description="Tax Compliance Autopilot for Kenyan SMEs",
    version="1.0.0",
)

orch = Orchestrator()
tracker = FilingTracker()
audit = AuditTrail()


# ── Models ──────────────────────────────────────────────────────

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


class FilingRequest(BaseModel):
    tax_type: str
    period: str
    amount_kes: float = 0
    reference: str = ""


# ── Endpoints ───────────────────────────────────────────────────

@app.get("/")
def root():
    return {
        "service": "KRA HELMET",
        "version": "1.0.0",
        "status": "running",
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


@app.get("/smes")
def list_smes():
    """List all onboarded SMEs."""
    smes = orch.list_smes()
    return {"count": len(smes), "smes": smes}


@app.get("/smes/{pin}")
def get_sme(pin: str):
    """Get SME profile."""
    profile = orch.load_sme(pin.upper())
    if not profile:
        raise HTTPException(status_code=404, detail=f"SME not found: {pin}")
    return profile


@app.post("/onboard")
def onboard_sme(req: OnboardRequest):
    """Onboard a new SME."""
    data = req.model_dump()
    data["pin"] = data["pin"].upper()
    if not data.get("business_name"):
        data["business_name"] = data["name"]

    existing = orch.load_sme(data["pin"])
    if existing:
        raise HTTPException(status_code=409, detail=f"SME already onboarded: {data['pin']}")

    profile = orch.onboard(interactive=False, data=data)
    if not profile:
        raise HTTPException(status_code=500, detail="Onboarding failed")

    return {
        "status": "onboarded",
        "pin": profile["pin"],
        "name": profile["name"],
        "obligations": profile.get("classification", {}).get("obligations", []),
    }


@app.get("/check/{pin}")
def check_sme(pin: str):
    """Run full compliance check for an SME."""
    pin = pin.upper()
    result = orch.check_sme(pin)
    if not result:
        raise HTTPException(status_code=404, detail=f"SME not found: {pin}")
    return {
        "pin": pin,
        "name": result["profile"]["name"],
        "compliance": result["compliance"],
        "risk": result["risk"],
        "penalties": result.get("penalties", {}),
        "urgency": result["urgency"],
        "obligations": result["obligations"],
        "message": result["message"],
        "alerts_queued": result.get("alerts_queued", 0),
    }


@app.get("/check")
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


@app.post("/file/{pin}")
def record_filing(pin: str, req: FilingRequest):
    """Record a tax filing for an SME."""
    pin = pin.upper()
    profile = orch.load_sme(pin)
    if not profile:
        raise HTTPException(status_code=404, detail=f"SME not found: {pin}")

    entry = tracker.record_filing(
        pin=pin,
        tax_type=req.tax_type,
        period=req.period,
        amount_kes=req.amount_kes,
        reference=req.reference,
    )
    return {"status": "recorded", "filing": entry}


@app.get("/filings/{pin}")
def get_filings(pin: str, tax_type: str | None = None):
    """Get filing history for an SME."""
    pin = pin.upper()
    filings = tracker.get_filings(pin, tax_type)
    summary = tracker.get_filing_summary(pin)
    return {"pin": pin, "summary": summary, "filings": filings}


@app.get("/dashboard", response_class=HTMLResponse)
def dashboard():
    """Generate and serve the HTML dashboard."""
    gen = DashboardGenerator()
    output_path = gen.generate()
    return output_path.read_text(encoding="utf-8")


@app.get("/report/{pin}", response_class=HTMLResponse)
def report(pin: str):
    """Generate and serve a per-SME HTML report."""
    pin = pin.upper()
    gen = ReportGenerator()
    output_path = gen.generate(pin)
    if not output_path:
        raise HTTPException(status_code=404, detail=f"SME not found: {pin}")
    return output_path.read_text(encoding="utf-8")


@app.get("/audit")
def audit_log(pin: str | None = None, limit: int = 50):
    """Get audit trail."""
    entries = audit.get_history(sme_pin=pin.upper() if pin else None, limit=limit)
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
