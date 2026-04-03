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
            dot_color = {"upcoming": "#34d399", "due_soon": "#fbbf24", "urgent": "#fb923c", "critical": "#f87171", "overdue": "#ef4444"}.get(status, "#5a6070")

            obl_rows += f"""
            <tr>
                <td><span class="obl-dot" style="background:{dot_color}"></span>{ob.get('tax_name', '-')}</td>
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

        # Status colors for dark theme
        dark_status_colors = {
            "compliant": ("#34d399", "rgba(52,211,153,0.1)", "rgba(52,211,153,0.2)"),
            "at_risk": ("#fbbf24", "rgba(251,191,36,0.1)", "rgba(251,191,36,0.2)"),
            "non_compliant": ("#f87171", "rgba(248,113,113,0.1)", "rgba(248,113,113,0.2)"),
            "not_checked": ("#9aa0b0", "rgba(154,160,176,0.08)", "rgba(154,160,176,0.15)"),
        }
        neon_color, neon_bg, neon_border = dark_status_colors.get(overall, dark_status_colors["not_checked"])
        risk_bar_color = '#34d399' if risk_score <= 25 else '#fbbf24' if risk_score <= 50 else '#fb923c' if risk_score <= 75 else '#f87171'

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>KRA HELMET Report — {name} ({pin})</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
<style>
*, *::before, *::after {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
    background: #0f1117; color: #e8eaed; line-height: 1.6;
    -webkit-font-smoothing: antialiased; min-height: 100vh;
}}

.report-container {{
    max-width: 900px; margin: 0 auto; padding: 32px 24px;
}}

.report-card {{
    background: #1a1d2e; border: 1px solid #2a2d3e; border-radius: 10px;
    overflow: hidden; margin-bottom: 20px;
}}

.report-header {{
    display: flex; align-items: center; justify-content: space-between;
    padding: 20px 24px; border-bottom: 1px solid #2a2d3e;
}}
.report-header h1 {{ font-size: 1.1rem; font-weight: 700; color: #e8eaed; }}
.report-meta {{
    font-size: 0.72rem; color: #5a6070;
    padding: 10px 24px; border-bottom: 1px solid #2a2d3e;
}}

.section-header {{
    display: flex; align-items: center; gap: 10px;
    padding: 12px 24px; border-bottom: 1px solid #2a2d3e;
}}
.section-header h2 {{ font-size: 0.85rem; font-weight: 600; color: #e8eaed; }}
.section-body {{ padding: 18px 24px; }}

.profile-grid {{
    display: grid; grid-template-columns: 1fr 1fr; gap: 8px 32px; font-size: 0.88rem;
}}
.profile-grid dt {{ color: #5a6070; font-size: 0.78rem; font-weight: 500; }}
.profile-grid dd {{ font-weight: 600; color: #e8eaed; margin-bottom: 2px; }}

.status-badge {{
    display: inline-flex; align-items: center; gap: 6px;
    padding: 5px 14px; border-radius: 20px;
    font-size: 0.7rem; font-weight: 600; text-transform: uppercase;
    background: {neon_bg}; color: {neon_color}; border: 1px solid {neon_border};
}}
.status-dot {{
    width: 6px; height: 6px; border-radius: 50%; background: {neon_color};
}}
.next-action {{ font-size: 0.82rem; color: #9aa0b0; }}

.risk-row {{
    display: flex; justify-content: space-between; align-items: center;
    font-size: 0.85rem; color: #9aa0b0; margin-bottom: 8px;
}}
.risk-row strong {{ color: #e8eaed; }}
.risk-meter {{
    height: 8px; background: #222538; border-radius: 6px;
    overflow: hidden; margin: 8px 0;
}}
.risk-fill {{ height: 100%; border-radius: 6px; }}
.risk-factors {{
    list-style: none; padding: 0; margin-top: 10px;
}}
.risk-factors li {{ font-size: 0.8rem; color: #5a6070; padding: 3px 0; }}

table {{ width: 100%; border-collapse: collapse; font-size: 0.82rem; }}
th {{
    text-align: left; padding: 9px 12px; background: #161822;
    color: #5a6070; font-weight: 600; font-size: 0.7rem;
    text-transform: uppercase; letter-spacing: 0.04em;
    border-bottom: 1px solid #2a2d3e;
}}
td {{ padding: 9px 12px; border-bottom: 1px solid #222538; color: #9aa0b0; }}
tr:hover td {{ background: #222538; }}
.obl-dot {{
    display: inline-block; width: 7px; height: 7px; border-radius: 50%; margin-right: 8px;
}}

.disclaimer {{
    padding: 14px 20px; background: rgba(251,191,36,0.06);
    border: 1px solid rgba(251,191,36,0.15); border-radius: 10px;
    font-size: 0.78rem; color: #fbbf24;
}}

.report-footer {{
    text-align: center; padding: 18px 0 8px; font-size: 0.7rem; color: #5a6070;
}}

@media print {{
    body {{ background: #fff; color: #1a1a1a; }}
    .report-card {{ background: #fff; border: 1px solid #e5e7eb; }}
    .report-header h1, .section-header h2 {{ color: #1a1a1a; }}
    .report-meta {{ color: #666; }}
    .profile-grid dt {{ color: #666; }}
    .profile-grid dd {{ color: #1a1a1a; }}
    .risk-row, .risk-row strong, td {{ color: #1a1a1a; }}
    .next-action, .risk-factors li {{ color: #666; }}
    th {{ background: #f9fafb; color: #666; }}
    td {{ border-bottom-color: #f3f4f6; }}
    .disclaimer {{ background: #fef3c7; border-color: #f59e0b; color: #92400e; }}
    .report-footer {{ color: #999; }}
    .no-print {{ display: none; }}
}}
</style>
</head>
<body>

<div class="report-container">
    <div class="report-card">
        <div class="report-header">
            <h1>KRA HELMET — Tax Compliance Report</h1>
        </div>
        <div class="report-meta">Generated: {now} | PIN: {pin}</div>

        <div class="section-header"><h2>SME Profile</h2></div>
        <div class="section-body">
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

        <div class="section-header"><h2>Compliance Status</h2></div>
        <div class="section-body" style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:12px">
            <span class="status-badge"><span class="status-dot"></span>{overall.replace('_', ' ')}</span>
            <span class="next-action">{compliance.get('next_action', '-')}</span>
        </div>

        <div class="section-header"><h2>Risk Assessment</h2></div>
        <div class="section-body">
            <div class="risk-row">
                <span>Score: <strong>{risk_score}/100</strong> ({risk_level})</span>
                <span>Audit Probability: <strong>{audit_prob}%</strong></span>
            </div>
            <div class="risk-meter">
                <div class="risk-fill" style="width:{risk_score}%;background:{risk_bar_color}"></div>
            </div>
            {'<ul class="risk-factors">' + ''.join(f'<li>{f}</li>' for f in risk.get('factors', [])) + '</ul>' if risk.get('factors') else ''}
        </div>

        <div class="section-header"><h2>Tax Obligations ({len(obligations)})</h2></div>
        <div style="padding:0">
            <table>
                <thead><tr><th>Tax Type</th><th>Rate</th><th>Frequency</th><th>Next Deadline</th><th>Days Left</th><th>File By</th><th>Status</th></tr></thead>
                <tbody>{obl_rows if obl_rows else '<tr><td colspan="7" style="color:#5a6070;text-align:center;padding:20px">No compliance check run yet</td></tr>'}</tbody>
            </table>
        </div>

{f"""        <div class="section-header"><h2>Penalty Exposure — KES {penalty_total:,.0f} ({penalty_severity})</h2></div>
        <div style="padding:0">
            <table>
                <thead><tr><th>Tax Type</th><th>Days Overdue</th><th>Penalty</th><th>Interest</th><th>Total</th></tr></thead>
                <tbody>{penalty_html}</tbody>
            </table>
        </div>""" if penalty_total > 0 else ""}

        <div class="section-header"><h2>Filing History</h2></div>
        <div {"style='padding:0'" if filing_rows else "class='section-body'"}>
            {f"""<table>
                <thead><tr><th>Date</th><th>Tax Type</th><th>Period</th><th>Amount</th><th>Reference</th></tr></thead>
                <tbody>{filing_rows}</tbody>
            </table>""" if filing_rows else f'<div style="color:#5a6070;font-size:0.82rem">No filings recorded yet. Use <code style="color:#34d399">python run.py file {pin}</code> to record.</div>'}
        </div>
    </div>

    <div class="disclaimer">
        <strong>DISCLAIMER:</strong> This report is generated by an automated system for guidance purposes only.
        It does NOT constitute legal, tax, or financial advice. Tax laws change frequently.
        Always verify with the Kenya Revenue Authority (KRA) or a registered tax advisor before making filing or payment decisions.
    </div>

    <div class="report-footer">
        KRA HELMET v2.0 — Tax Compliance Autopilot for Kenyan SMEs<br>
        Report generated {now}
    </div>
</div>

</body>
</html>"""
