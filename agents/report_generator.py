"""
REPORT GENERATOR — creates detailed per-SME compliance reports as HTML.
Can be printed or shared with SMEs as a professional document.
"""
import json
from datetime import datetime
from pathlib import Path
from .base import BaseAgent

ROOT = Path(__file__).parent.parent


class ReportGenerator(BaseAgent):
    name = "report_generator"
    boundary = "Generates read-only reports. Never modifies SME data."

    def generate(self, pin: str) -> Path | None:
        """Generate a detailed HTML report for a single SME."""
        self.log(f"Generating report for {pin}")

        profile = self.load_sme(pin)
        if not profile:
            self.log(f"SME not found: {pin}", "ERROR")
            return None

        report_path = self.data_dir / "processed" / "obligations" / f"{pin}.json"
        report = self.load_json(report_path) if report_path.exists() else None

        # Load filing history
        filings = self._load_filings(pin)

        html = self._build_report(profile, report, filings)

        output_dir = ROOT / "output" / "reports"
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / f"{pin}_report.html"
        output_path.write_text(html, encoding="utf-8")

        self.log(f"Report written to {output_path}")
        return output_path

    def generate_all(self) -> list[Path]:
        """Generate reports for all SMEs."""
        smes = self.list_smes()
        paths = []
        for sme in smes:
            path = self.generate(sme["pin"])
            if path:
                paths.append(path)
        return paths

    def _load_filings(self, pin: str) -> list[dict]:
        filings_path = ROOT / "data" / "filings" / f"{pin}.jsonl"
        if not filings_path.exists():
            return []
        entries = []
        with open(filings_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        entries.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
        return entries

    def _build_report(self, profile: dict, report: dict | None, filings: list[dict]) -> str:
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        pin = profile["pin"]
        name = profile.get("name", "Unknown")
        biz = profile.get("business_name", name)
        industry = profile.get("classification", {}).get("industry_label", profile.get("industry", "-"))
        county = profile.get("county", "-")
        bracket = profile.get("turnover_bracket", "-")
        btype = profile.get("business_type", "-").replace("_", " ").title()
        employees = profile.get("employee_count", 0) or 0
        phone = profile.get("phone", "-")

        # Report data
        obligations = report.get("obligations", []) if report else []
        compliance = report.get("compliance", {}) if report else {}
        risk = report.get("risk", {}) if report else {}
        penalties = report.get("penalties", {}) if report else {}
        urgency = report.get("urgency", {}) if report else {}
        overall = compliance.get("overall", "not_checked")
        risk_score = risk.get("risk_score", 0)
        risk_level = risk.get("risk_level", "-")
        audit_prob = risk.get("audit_probability_pct", 0)
        penalty_total = penalties.get("total_penalty_exposure_kes", 0)
        penalty_severity = penalties.get("severity", "none")

        # Status colors
        status_colors = {
            "compliant": ("#16a34a", "#dcfce7"),
            "at_risk": ("#ca8a04", "#fef9c3"),
            "non_compliant": ("#dc2626", "#fee2e2"),
            "not_checked": ("#6b7280", "#f3f4f6"),
        }
        sc, sbg = status_colors.get(overall, ("#6b7280", "#f3f4f6"))

        # Obligation rows
        obl_rows = ""
        for ob in obligations:
            days = ob.get("days_until_deadline", 0)
            if days is not None and days < 0:
                days_str = f'<span style="color:#ef4444;font-weight:700">{abs(days)}d OVERDUE</span>'
            elif days is not None and days <= 3:
                days_str = f'<span style="color:#f59e0b;font-weight:700">{days}d</span>'
            else:
                days_str = f'{days}d' if days is not None else '-'

            status = ob.get("status", "-")
            dot_color = {"upcoming": "#22c55e", "due_soon": "#eab308", "urgent": "#f97316", "critical": "#ef4444", "overdue": "#dc2626"}.get(status, "#9ca3af")

            obl_rows += f"""
            <tr>
                <td><span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:{dot_color};margin-right:6px"></span>{ob.get('tax_name', '-')}</td>
                <td>{ob.get('rate', '-')}</td>
                <td>{ob.get('frequency', '-')}</td>
                <td>{ob.get('next_deadline', '-')}</td>
                <td>{days_str}</td>
                <td>{ob.get('recommended_file_by', '-')}</td>
                <td style="text-transform:capitalize">{status}</td>
            </tr>"""

        # Risk factors
        risk_factors_html = ""
        for f in risk.get("factors", []):
            risk_factors_html += f"<li>{f}</li>"

        # Filing history
        filing_rows = ""
        for f in filings[-20:]:
            filing_rows += f"""
            <tr>
                <td>{f.get('filed_at', '-')[:16]}</td>
                <td>{f.get('tax_type', '-')}</td>
                <td>{f.get('period', '-')}</td>
                <td>KES {f.get('amount_kes', 0):,.0f}</td>
                <td>{f.get('reference', '-')}</td>
            </tr>"""

        # Penalty breakdown
        penalty_html = ""
        if penalty_total > 0:
            penalty_items = penalties.get("breakdown", [])
            for p in penalty_items:
                penalty_html += f"""
                <tr>
                    <td>{p.get('tax_name', '-')}</td>
                    <td>{p.get('days_overdue', 0)} days</td>
                    <td>KES {p.get('estimated_penalty_kes', 0):,.0f}</td>
                    <td>KES {p.get('estimated_interest_kes', 0):,.0f}</td>
                    <td>KES {p.get('total_exposure_kes', 0):,.0f}</td>
                </tr>"""

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>KRA HELMET Report — {name} ({pin})</title>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ font-family: 'Segoe UI', system-ui, sans-serif; background: #fff; color: #1a1a1a; max-width: 900px; margin: 0 auto; padding: 24px; }}

.report-header {{
    border-bottom: 3px solid #16a34a;
    padding-bottom: 16px; margin-bottom: 24px;
}}
.report-header h1 {{ font-size: 1.4rem; color: #16a34a; }}
.report-header .meta {{ color: #666; font-size: 0.85rem; margin-top: 4px; }}

.section {{ margin-bottom: 24px; }}
.section h2 {{
    font-size: 1rem; text-transform: uppercase; color: #444;
    border-bottom: 1px solid #e5e7eb; padding-bottom: 6px; margin-bottom: 12px;
    letter-spacing: 0.05em;
}}

.profile-grid {{
    display: grid; grid-template-columns: 1fr 1fr; gap: 8px 24px; font-size: 0.9rem;
}}
.profile-grid dt {{ color: #666; }}
.profile-grid dd {{ font-weight: 600; margin-bottom: 4px; }}

.status-badge {{
    display: inline-block; padding: 6px 16px; border-radius: 6px;
    font-weight: 700; font-size: 0.9rem; text-transform: uppercase;
    background: {sbg}; color: {sc}; border: 1px solid {sc};
}}

.risk-meter {{
    height: 12px; background: #e5e7eb; border-radius: 6px; overflow: hidden;
    margin: 8px 0;
}}
.risk-fill {{ height: 100%; border-radius: 6px; }}

table {{ width: 100%; border-collapse: collapse; font-size: 0.85rem; margin-top: 8px; }}
th {{ text-align: left; padding: 8px; background: #f9fafb; border-bottom: 2px solid #e5e7eb; font-size: 0.75rem; text-transform: uppercase; color: #666; }}
td {{ padding: 8px; border-bottom: 1px solid #f3f4f6; }}
tr:hover {{ background: #f9fafb; }}

.disclaimer {{
    margin-top: 32px; padding: 12px 16px; background: #fef3c7;
    border: 1px solid #f59e0b; border-radius: 6px; font-size: 0.8rem;
    color: #92400e;
}}

.footer {{
    margin-top: 24px; padding-top: 12px; border-top: 1px solid #e5e7eb;
    font-size: 0.75rem; color: #999; text-align: center;
}}

@media print {{
    body {{ padding: 12px; }}
    .no-print {{ display: none; }}
}}
</style>
</head>
<body>

<div class="report-header">
    <h1>KRA HELMET — Tax Compliance Report</h1>
    <div class="meta">Generated: {now} | PIN: {pin}</div>
</div>

<div class="section">
    <h2>SME Profile</h2>
    <dl class="profile-grid">
        <dt>Name</dt><dd>{name}</dd>
        <dt>Business</dt><dd>{biz}</dd>
        <dt>Type</dt><dd>{btype}</dd>
        <dt>Industry</dt><dd>{industry}</dd>
        <dt>County</dt><dd>{county}</dd>
        <dt>Turnover Bracket</dt><dd>{bracket}</dd>
        <dt>Employees</dt><dd>{employees}</dd>
        <dt>Phone</dt><dd>{phone}</dd>
    </dl>
</div>

<div class="section">
    <h2>Compliance Status</h2>
    <div style="display:flex;justify-content:space-between;align-items:center">
        <span class="status-badge">{overall.replace('_', ' ')}</span>
        <span style="font-size:0.9rem;color:#666">{compliance.get('next_action', '-')}</span>
    </div>
</div>

<div class="section">
    <h2>Risk Assessment</h2>
    <div style="display:flex;justify-content:space-between;align-items:center;font-size:0.9rem">
        <span>Score: <strong>{risk_score}/100</strong> ({risk_level})</span>
        <span>Audit Probability: <strong>{audit_prob}%</strong></span>
    </div>
    <div class="risk-meter">
        <div class="risk-fill" style="width:{risk_score}%;background:{'#22c55e' if risk_score <= 25 else '#eab308' if risk_score <= 50 else '#f97316' if risk_score <= 75 else '#ef4444'}"></div>
    </div>
    {'<ul style="font-size:0.85rem;color:#666;padding-left:20px;margin-top:8px">' + risk_factors_html + '</ul>' if risk_factors_html else ''}
</div>

<div class="section">
    <h2>Tax Obligations ({len(obligations)})</h2>
    <table>
        <thead><tr><th>Tax Type</th><th>Rate</th><th>Frequency</th><th>Next Deadline</th><th>Days Left</th><th>File By</th><th>Status</th></tr></thead>
        <tbody>{obl_rows if obl_rows else '<tr><td colspan="7" style="color:#999;text-align:center">No compliance check run yet</td></tr>'}</tbody>
    </table>
</div>

{f"""<div class="section">
    <h2>Penalty Exposure — KES {penalty_total:,.0f} ({penalty_severity})</h2>
    <table>
        <thead><tr><th>Tax Type</th><th>Days Overdue</th><th>Penalty</th><th>Interest</th><th>Total</th></tr></thead>
        <tbody>{penalty_html}</tbody>
    </table>
</div>""" if penalty_total > 0 else ""}

<div class="section">
    <h2>Filing History</h2>
    {f"""<table>
        <thead><tr><th>Date</th><th>Tax Type</th><th>Period</th><th>Amount</th><th>Reference</th></tr></thead>
        <tbody>{filing_rows}</tbody>
    </table>""" if filing_rows else '<div style="color:#999;font-size:0.85rem">No filings recorded yet. Use <code>python run.py file {pin}</code> to record.</div>'}
</div>

<div class="disclaimer">
    <strong>DISCLAIMER:</strong> This report is generated by an automated system for guidance purposes only.
    It does NOT constitute legal, tax, or financial advice. Tax laws change frequently.
    Always verify with the Kenya Revenue Authority (KRA) or a registered tax advisor before making filing or payment decisions.
</div>

<div class="footer">
    KRA HELMET v1.0 — Tax Compliance Autopilot for Kenyan SMEs<br>
    Report generated {now}
</div>

</body>
</html>"""
