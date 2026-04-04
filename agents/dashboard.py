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

        refresh_sec = self._settings.get("dashboard", {}).get("auto_refresh_seconds", 300)

        # Build SME cards JSON for JS
        cards_json = json.dumps(sme_data, default=str, ensure_ascii=False)

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta http-equiv="refresh" content="{refresh_sec}">
<title>KRA Deadline Tracker — Tax Compliance Dashboard</title>
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

.header {{
    background: #1a1d2e; padding: 20px 32px;
    border-bottom: 1px solid #2a2d3e;
    display: flex; align-items: center; justify-content: space-between;
    position: sticky; top: 0; z-index: 50;
}}
.header-left {{ display: flex; align-items: center; gap: 12px; }}
.brand-icon {{
    width: 36px; height: 36px; border-radius: 6px;
    background: rgba(52,211,153,0.1); border: 1px solid rgba(52,211,153,0.2);
    display: flex; align-items: center; justify-content: center;
    color: #34d399; flex-shrink: 0;
}}
.brand-icon svg {{ width: 20px; height: 20px; }}
.brand-name {{ font-weight: 800; font-size: 0.9rem; color: #e8eaed; letter-spacing: 0.04em; }}
.brand-sub {{ font-size: 0.6rem; color: #9aa0b0; letter-spacing: 0.06em; font-weight: 600; }}
.header-meta {{ font-size: 0.72rem; color: #5a6070; }}

.stats-row {{
    display: grid; grid-template-columns: repeat(5, 1fr); gap: 16px;
    padding: 20px 32px; border-bottom: 1px solid #2a2d3e;
}}
.stat-card {{
    background: #1a1d2e; border: 1px solid #2a2d3e; border-radius: 10px;
    padding: 16px 18px; transition: border-color 0.15s;
}}
.stat-card:hover {{ border-color: #353850; }}
.stat-card .label {{
    font-size: 0.62rem; font-weight: 600; letter-spacing: 0.08em;
    color: #5a6070; text-transform: uppercase;
}}
.stat-card .value {{
    font-size: 1.5rem; font-weight: 800; line-height: 1; margin-top: 6px;
}}
.stat-card.blue .value {{ color: #60a5fa; }}
.stat-card.green .value {{ color: #34d399; }}
.stat-card.amber .value {{ color: #fbbf24; }}
.stat-card.red .value {{ color: #f87171; }}
.stat-card.purple .value {{ color: #a78bfa; }}

.filters {{
    padding: 14px 32px; display: flex; gap: 8px; flex-wrap: wrap;
    border-bottom: 1px solid #2a2d3e;
}}
.filters button {{
    padding: 6px 14px; border-radius: 20px;
    border: 1px solid #2a2d3e; background: transparent;
    color: #9aa0b0; cursor: pointer; font-size: 0.78rem;
    font-weight: 600; transition: all 0.15s;
}}
.filters button.active {{
    background: rgba(52,211,153,0.1); color: #34d399;
    border-color: rgba(52,211,153,0.3);
}}
.filters button:hover {{ border-color: #353850; color: #e8eaed; }}

.cards {{ padding: 24px 32px; display: grid; gap: 20px; max-width: 1280px; }}

.card {{
    background: #1a1d2e; border-radius: 10px; overflow: hidden;
    border: 1px solid #2a2d3e; transition: border-color 0.15s;
}}
.card:hover {{ border-color: #353850; }}

.card-header {{
    display: flex; justify-content: space-between; align-items: center;
    padding: 14px 20px; border-bottom: 1px solid #2a2d3e;
}}
.card-header .name {{ font-size: 1rem; font-weight: 700; }}
.card-header .pin {{ color: #5a6070; font-size: 0.75rem; }}

.badge {{
    display: inline-flex; align-items: center; gap: 5px;
    padding: 4px 10px; border-radius: 20px;
    font-size: 0.65rem; font-weight: 600; text-transform: uppercase;
}}
.badge .bdot {{ width: 5px; height: 5px; border-radius: 50%; }}
.badge.compliant {{ background: rgba(52,211,153,0.1); color: #34d399; border: 1px solid rgba(52,211,153,0.2); }}
.badge.compliant .bdot {{ background: #34d399; }}
.badge.at_risk {{ background: rgba(251,191,36,0.1); color: #fbbf24; border: 1px solid rgba(251,191,36,0.2); }}
.badge.at_risk .bdot {{ background: #fbbf24; }}
.badge.non_compliant {{ background: rgba(248,113,113,0.1); color: #f87171; border: 1px solid rgba(248,113,113,0.2); }}
.badge.non_compliant .bdot {{ background: #f87171; }}
.badge.not_checked {{ background: rgba(154,160,176,0.08); color: #9aa0b0; border: 1px solid rgba(154,160,176,0.15); }}
.badge.not_checked .bdot {{ background: #9aa0b0; }}

.card-body {{ padding: 16px 20px; }}

.info-row {{
    display: flex; gap: 18px; flex-wrap: wrap; margin-bottom: 12px;
    font-size: 0.8rem; color: #9aa0b0;
}}
.info-row span {{ display: inline-flex; align-items: center; gap: 4px; }}

.risk-bar-container {{
    margin: 10px 0; background: #222538; border-radius: 6px;
    height: 6px; overflow: hidden;
}}
.risk-bar {{ height: 100%; border-radius: 6px; transition: width 0.5s; }}

.obligations-table {{
    width: 100%; border-collapse: collapse; margin-top: 12px; font-size: 0.82rem;
}}
.obligations-table th {{
    text-align: left; padding: 8px 12px; background: #161822;
    color: #5a6070; font-weight: 600; font-size: 0.7rem;
    text-transform: uppercase; letter-spacing: 0.04em;
    border-bottom: 1px solid #2a2d3e;
}}
.obligations-table td {{
    padding: 8px 12px; border-top: 1px solid #222538; color: #9aa0b0;
}}
.obligations-table tr:hover td {{ background: #222538; }}

.status-dot {{
    display: inline-block; width: 6px; height: 6px; border-radius: 50%; margin-right: 6px;
}}
.status-dot.upcoming {{ background: #34d399; }}
.status-dot.due_soon {{ background: #fbbf24; }}
.status-dot.urgent {{ background: #fb923c; }}
.status-dot.critical {{ background: #f87171; }}
.status-dot.overdue {{ background: #ef4444; animation: pulse 1.5s infinite; }}
@keyframes pulse {{ 0%,100% {{ opacity: 1; }} 50% {{ opacity: 0.4; }} }}

.card-footer {{
    padding: 10px 20px; border-top: 1px solid #2a2d3e;
    display: flex; justify-content: space-between; font-size: 0.72rem; color: #5a6070;
}}

.penalty-tag {{
    background: rgba(248,113,113,0.1); color: #f87171;
    border: 1px solid rgba(248,113,113,0.2);
    padding: 3px 10px; border-radius: 12px;
    font-size: 0.72rem; font-weight: 700;
}}

.page-footer {{
    text-align: center; padding: 24px 32px 16px;
    font-size: 0.7rem; color: #5a6070;
}}

@media (max-width: 768px) {{
    .stats-row {{ grid-template-columns: repeat(2, 1fr); }}
    .info-row {{ flex-direction: column; gap: 6px; }}
    .header, .cards, .filters, .stats-row {{ padding-left: 16px; padding-right: 16px; }}
    .header {{ flex-direction: column; gap: 10px; align-items: flex-start; }}
}}
@media (max-width: 480px) {{
    .stats-row {{ grid-template-columns: 1fr; }}
}}
</style>
</head>
<body>

<div class="header">
    <div class="header-left">
        <div class="brand-icon">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>
            </svg>
        </div>
        <div>
            <div class="brand-name">KRA Deadline Tracker</div>
            <div class="brand-sub">Tax Compliance Dashboard</div>
        </div>
    </div>
    <div class="header-meta">
        Generated: {now} | Auto-refresh {refresh_sec // 60}min
    </div>
</div>

<div class="stats-row">
    <div class="stat-card blue">
        <div class="label">Total SMEs</div>
        <div class="value">{total}</div>
    </div>
    <div class="stat-card green">
        <div class="label">Compliant</div>
        <div class="value">{compliant}</div>
    </div>
    <div class="stat-card amber">
        <div class="label">At Risk</div>
        <div class="value">{at_risk}</div>
    </div>
    <div class="stat-card red">
        <div class="label">Non-Compliant</div>
        <div class="value">{non_compliant}</div>
    </div>
    <div class="stat-card purple">
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

<div class="page-footer">
    KRA Deadline Tracker v2.0 — Tax Compliance Autopilot for Kenyan SMEs
</div>

<script>
const DATA = {cards_json};

function getStatus(sme) {{
    if (!sme.report) return 'not_checked';
    return sme.report.compliance?.overall || 'not_checked';
}}

function getRiskColor(score) {{
    if (score <= 25) return '#34d399';
    if (score <= 50) return '#fbbf24';
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
                <span class="badge ${{status}}"><span class="bdot"></span>${{status.replace('_', ' ')}}</span>
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

            <div style="display:flex;justify-content:space-between;align-items:center;font-size:0.82rem;color:#9aa0b0">
                <span>Risk Score: <strong style="color:#e8eaed">${{riskScore}}</strong>/100 (${{risk.risk_level || '-'}})</span>
                <span>${{urgency.emoji || ''}} ${{urgency.prefix || ''}}</span>
            </div>
            <div class="risk-bar-container">
                <div class="risk-bar" style="width:${{riskScore}}%;background:${{getRiskColor(riskScore)}}"></div>
            </div>

            ${{risk.factors ? `<div style="font-size:0.75rem;color:#5a6070;margin-bottom:8px">${{risk.factors.join(' | ')}}</div>` : ''}}

            ${{obligations.length > 0 ? `
            <table class="obligations-table">
                <thead><tr><th>Tax Type</th><th>Rate</th><th>Next Deadline</th><th>Days</th><th>Status</th></tr></thead>
                <tbody>${{oblRows}}</tbody>
            </table>` : '<div style="color:#5a6070;padding:12px;font-size:0.82rem">No compliance check run yet.</div>'}}
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
