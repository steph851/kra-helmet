"""
DASHBOARD GENERATOR — builds a self-contained HTML dashboard for all SMEs.
"""
import json
from datetime import datetime
from pathlib import Path
from .base import BaseAgent

ROOT = Path(__file__).parent.parent


class DashboardGenerator(BaseAgent):
    name = "dashboard_generator"
    boundary = "Generates read-only HTML reports. Never modifies SME data or compliance state."

    def generate(self) -> Path:
        """Generate the HTML dashboard and return the output path."""
        self.log("=== DASHBOARD GENERATION START ===")

        smes = self.list_smes()
        sme_data = []

        for sme in smes:
            pin = sme["pin"]
            profile = self.load_sme(pin)
            report_path = self.data_dir / "processed" / "obligations" / f"{pin}.json"

            entry = {
                "pin": pin,
                "name": sme["name"],
                "active": sme.get("active", True),
                "profile": profile,
                "report": None,
            }

            if report_path.exists():
                entry["report"] = self.load_json(report_path)

            sme_data.append(entry)

        html = self._build_html(sme_data)

        output_dir = ROOT / "output"
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / "dashboard.html"
        output_path.write_text(html, encoding="utf-8")

        self.log(f"Dashboard written to {output_path}")
        return output_path

    def _build_html(self, sme_data: list[dict]) -> str:
        now = datetime.now().strftime("%Y-%m-%d %H:%M")

        # Calculate summary stats
        total = len(sme_data)
        compliant = sum(1 for s in sme_data if s["report"] and s["report"].get("compliance", {}).get("overall") == "compliant")
        at_risk = sum(1 for s in sme_data if s["report"] and s["report"].get("compliance", {}).get("overall") == "at_risk")
        non_compliant = sum(1 for s in sme_data if s["report"] and s["report"].get("compliance", {}).get("overall") == "non_compliant")
        not_checked = total - compliant - at_risk - non_compliant
        total_penalty = sum(
            s["report"].get("penalties", {}).get("total_penalty_exposure_kes", 0)
            for s in sme_data if s["report"]
        )

        # Build SME cards JSON for JS
        cards_json = json.dumps(sme_data, default=str, ensure_ascii=False)

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>KRA HELMET — Tax Compliance Dashboard</title>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ font-family: 'Segoe UI', system-ui, -apple-system, sans-serif; background: #0f1117; color: #e0e0e0; }}

.header {{
    background: linear-gradient(135deg, #1a1d29 0%, #0d2137 100%);
    padding: 24px 32px;
    border-bottom: 2px solid #2a5a3a;
}}
.header h1 {{ font-size: 1.6rem; color: #4ade80; }}
.header .subtitle {{ color: #888; font-size: 0.9rem; margin-top: 4px; }}

.summary-bar {{
    display: flex; gap: 16px; padding: 16px 32px; flex-wrap: wrap;
    background: #161822; border-bottom: 1px solid #2a2d3a;
}}
.stat {{
    background: #1e2130; padding: 12px 20px; border-radius: 8px; min-width: 140px;
    border-left: 3px solid #444;
}}
.stat.green {{ border-left-color: #4ade80; }}
.stat.yellow {{ border-left-color: #facc15; }}
.stat.red {{ border-left-color: #f87171; }}
.stat.blue {{ border-left-color: #60a5fa; }}
.stat.purple {{ border-left-color: #c084fc; }}
.stat .label {{ font-size: 0.75rem; color: #888; text-transform: uppercase; }}
.stat .value {{ font-size: 1.5rem; font-weight: 700; margin-top: 2px; }}

.filters {{
    padding: 12px 32px; display: flex; gap: 8px; flex-wrap: wrap;
    background: #161822; border-bottom: 1px solid #2a2d3a;
}}
.filters button {{
    padding: 6px 16px; border-radius: 20px; border: 1px solid #3a3d4a;
    background: transparent; color: #aaa; cursor: pointer; font-size: 0.85rem;
}}
.filters button.active {{ background: #4ade80; color: #000; border-color: #4ade80; font-weight: 600; }}
.filters button:hover {{ border-color: #4ade80; }}

.cards {{ padding: 24px 32px; display: grid; gap: 20px; }}

.card {{
    background: #1e2130; border-radius: 12px; overflow: hidden;
    border: 1px solid #2a2d3a; transition: border-color 0.2s;
}}
.card:hover {{ border-color: #4ade80; }}

.card-header {{
    display: flex; justify-content: space-between; align-items: center;
    padding: 16px 20px; border-bottom: 1px solid #2a2d3a;
}}
.card-header .name {{ font-size: 1.1rem; font-weight: 600; }}
.card-header .pin {{ color: #888; font-size: 0.85rem; }}

.badge {{
    padding: 4px 12px; border-radius: 20px; font-size: 0.75rem; font-weight: 700;
    text-transform: uppercase;
}}
.badge.compliant {{ background: #16532d; color: #4ade80; }}
.badge.at_risk {{ background: #533e16; color: #facc15; }}
.badge.non_compliant {{ background: #531616; color: #f87171; }}
.badge.not_checked {{ background: #2a2d3a; color: #888; }}

.card-body {{ padding: 16px 20px; }}

.info-row {{
    display: flex; gap: 24px; flex-wrap: wrap; margin-bottom: 12px;
    font-size: 0.85rem; color: #aaa;
}}
.info-row span {{ display: inline-flex; align-items: center; gap: 4px; }}

.risk-bar-container {{
    margin: 12px 0; background: #2a2d3a; border-radius: 6px; height: 8px; overflow: hidden;
}}
.risk-bar {{
    height: 100%; border-radius: 6px; transition: width 0.5s;
}}

.obligations-table {{
    width: 100%; border-collapse: collapse; margin-top: 12px; font-size: 0.85rem;
}}
.obligations-table th {{
    text-align: left; padding: 8px 12px; background: #161822; color: #888;
    font-weight: 600; font-size: 0.75rem; text-transform: uppercase;
}}
.obligations-table td {{ padding: 8px 12px; border-top: 1px solid #2a2d3a; }}

.status-dot {{
    display: inline-block; width: 8px; height: 8px; border-radius: 50%; margin-right: 6px;
}}
.status-dot.upcoming {{ background: #4ade80; }}
.status-dot.due_soon {{ background: #facc15; }}
.status-dot.urgent {{ background: #fb923c; }}
.status-dot.critical {{ background: #f87171; }}
.status-dot.overdue {{ background: #ef4444; animation: pulse 1s infinite; }}

@keyframes pulse {{ 0%,100% {{ opacity: 1; }} 50% {{ opacity: 0.4; }} }}

.card-footer {{
    padding: 12px 20px; border-top: 1px solid #2a2d3a;
    display: flex; justify-content: space-between; font-size: 0.8rem; color: #666;
}}

.penalty-tag {{
    background: #3d1616; color: #f87171; padding: 2px 10px;
    border-radius: 12px; font-size: 0.8rem; font-weight: 600;
}}

@media (max-width: 768px) {{
    .summary-bar {{ flex-direction: column; }}
    .info-row {{ flex-direction: column; gap: 6px; }}
    .header, .cards, .filters {{ padding-left: 16px; padding-right: 16px; }}
}}
</style>
</head>
<body>

<div class="header">
    <h1>KRA HELMET — Tax Compliance Dashboard</h1>
    <div class="subtitle">Generated: {now} | Protecting Kenyan SMEs from tax penalties</div>
</div>

<div class="summary-bar">
    <div class="stat blue">
        <div class="label">Total SMEs</div>
        <div class="value">{total}</div>
    </div>
    <div class="stat green">
        <div class="label">Compliant</div>
        <div class="value">{compliant}</div>
    </div>
    <div class="stat yellow">
        <div class="label">At Risk</div>
        <div class="value">{at_risk}</div>
    </div>
    <div class="stat red">
        <div class="label">Non-Compliant</div>
        <div class="value">{non_compliant}</div>
    </div>
    <div class="stat purple">
        <div class="label">Penalty Exposure</div>
        <div class="value">KES {total_penalty:,.0f}</div>
    </div>
</div>

<div class="filters">
    <button class="active" onclick="filterCards('all')">All ({total})</button>
    <button onclick="filterCards('compliant')">Compliant ({compliant})</button>
    <button onclick="filterCards('at_risk')">At Risk ({at_risk})</button>
    <button onclick="filterCards('non_compliant')">Non-Compliant ({non_compliant})</button>
    <button onclick="filterCards('not_checked')">Not Checked ({not_checked})</button>
</div>

<div class="cards" id="cards-container"></div>

<script>
const DATA = {cards_json};

function getStatus(sme) {{
    if (!sme.report) return 'not_checked';
    return sme.report.compliance?.overall || 'not_checked';
}}

function getRiskColor(score) {{
    if (score <= 25) return '#4ade80';
    if (score <= 50) return '#facc15';
    if (score <= 75) return '#fb923c';
    return '#f87171';
}}

function renderCard(sme) {{
    const status = getStatus(sme);
    const profile = sme.profile || {{}};
    const report = sme.report || {{}};
    const risk = report.risk || {{}};
    const urgency = report.urgency || {{}};
    const penalties = report.penalties || {{}};
    const obligations = report.obligations || [];
    const riskScore = risk.risk_score || 0;

    let oblRows = '';
    obligations.forEach(ob => {{
        const days = ob.days_until_deadline;
        const daysText = days < 0 ? `${{Math.abs(days)}}d overdue` : `${{days}}d`;
        oblRows += `
            <tr>
                <td><span class="status-dot ${{ob.status}}"></span>${{ob.tax_name}}</td>
                <td>${{ob.rate || '-'}}</td>
                <td>${{ob.next_deadline || '-'}}</td>
                <td>${{daysText}}</td>
                <td>${{ob.status}}</td>
            </tr>`;
    }});

    const penaltyTag = (penalties.total_penalty_exposure_kes || 0) > 0
        ? `<span class="penalty-tag">KES ${{(penalties.total_penalty_exposure_kes || 0).toLocaleString()}} exposure</span>`
        : '';

    return `
    <div class="card" data-status="${{status}}">
        <div class="card-header">
            <div>
                <div class="name">${{sme.name}}</div>
                <div class="pin">${{sme.pin}}</div>
            </div>
            <div style="display:flex;gap:8px;align-items:center">
                ${{penaltyTag}}
                <span class="badge ${{status}}">${{status.replace('_', ' ')}}</span>
            </div>
        </div>
        <div class="card-body">
            <div class="info-row">
                <span>${{profile.business_type || '-'}}</span>
                <span>${{profile.classification?.industry_label || profile.industry || '-'}}</span>
                <span>${{profile.county || '-'}}</span>
                <span>Turnover: ${{profile.turnover_bracket || '-'}}</span>
                ${{profile.has_employees ? `<span>Employees: ${{profile.employee_count || 0}}</span>` : ''}}
            </div>

            <div style="display:flex;justify-content:space-between;align-items:center;font-size:0.85rem">
                <span>Risk Score: <strong>${{riskScore}}</strong>/100 (${{risk.risk_level || '-'}})</span>
                <span>${{urgency.emoji || ''}} ${{urgency.prefix || ''}}</span>
            </div>
            <div class="risk-bar-container">
                <div class="risk-bar" style="width:${{riskScore}}%;background:${{getRiskColor(riskScore)}}"></div>
            </div>

            ${{risk.factors ? `<div style="font-size:0.8rem;color:#888;margin-bottom:8px">${{risk.factors.join(' | ')}}</div>` : ''}}

            ${{obligations.length > 0 ? `
            <table class="obligations-table">
                <thead><tr><th>Tax Type</th><th>Rate</th><th>Next Deadline</th><th>Days</th><th>Status</th></tr></thead>
                <tbody>${{oblRows}}</tbody>
            </table>` : '<div style="color:#666;padding:12px">No compliance check run yet.</div>'}}
        </div>
        <div class="card-footer">
            <span>Last checked: ${{report.checked_at ? report.checked_at.substring(0,16).replace('T',' ') : 'Never'}}</span>
            <span>Audit prob: ${{risk.audit_probability_pct || 0}}%</span>
        </div>
    </div>`;
}}

function renderAll(filter) {{
    const container = document.getElementById('cards-container');
    const filtered = filter === 'all' ? DATA : DATA.filter(s => getStatus(s) === filter);
    container.innerHTML = filtered.map(renderCard).join('');
}}

function filterCards(status) {{
    document.querySelectorAll('.filters button').forEach(b => b.classList.remove('active'));
    event.target.classList.add('active');
    renderAll(status);
}}

renderAll('all');
</script>
</body>
</html>"""
