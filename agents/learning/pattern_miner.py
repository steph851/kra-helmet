"""
PATTERN MINER — discovers compliance patterns across SMEs.
BOUNDARY: Analyzes data and reports patterns. Never changes scores or takes action.
Mines decision memory and obligation reports to find:
  - Industry-level compliance trends
  - Tax types most often filed late
  - Seasonal filing patterns
  - Risk factor correlations
  - Escalation frequency by tier
"""
import json
from datetime import datetime, timedelta, timezone
from collections import defaultdict, Counter
from pathlib import Path

from ..base import BaseAgent
from .memory import DecisionMemory

EAT = timezone(timedelta(hours=3))


class PatternMiner(BaseAgent):
    name = "pattern_miner"
    boundary = "Analyzes data and reports patterns. Never changes models or takes action."

    def __init__(self):
        super().__init__()
        self.memory = DecisionMemory()

    def mine_all(self) -> dict:
        """Run all pattern analyses. Returns combined insights report."""
        return {
            "type": "pattern_report",
            "late_filing_patterns": self.safe_run(
                self.late_filing_patterns, context="late_filings", fallback={}),
            "industry_compliance": self.safe_run(
                self.industry_compliance, context="industry", fallback={}),
            "seasonal_patterns": self.safe_run(
                self.seasonal_patterns, context="seasonal", fallback={}),
            "risk_factor_frequency": self.safe_run(
                self.risk_factor_frequency, context="risk_factors", fallback={}),
            "escalation_patterns": self.safe_run(
                self.escalation_patterns, context="escalations", fallback={}),
            "sme_risk_trends": self.safe_run(
                self.sme_risk_trends, context="risk_trends", fallback={}),
            "mined_at": datetime.now(EAT).isoformat(),
            "mined_by": self.name,
        }

    # ── Late Filing Patterns ─────────────────────────────────────

    def late_filing_patterns(self) -> dict:
        """Which tax types are filed late most often?"""
        filings = self.memory.get_outcomes("filing")
        if not filings:
            return {"status": "no_data", "patterns": []}

        by_tax = defaultdict(lambda: {"total": 0, "late": 0})
        for f in filings:
            tax_type = f.get("context", {}).get("tax_type", "unknown")
            by_tax[tax_type]["total"] += 1
            if f.get("outcome") == "late":
                by_tax[tax_type]["late"] += 1

        patterns = []
        for tax_type, counts in sorted(by_tax.items(), key=lambda x: x[1]["late"], reverse=True):
            total = counts["total"]
            late = counts["late"]
            rate = round(late / total, 2) if total else 0
            patterns.append({
                "tax_type": tax_type,
                "total_filings": total,
                "late_filings": late,
                "late_rate": rate,
                "severity": "high" if rate > 0.5 else "medium" if rate > 0.2 else "low",
            })

        return {
            "status": "ok",
            "total_filings": sum(p["total_filings"] for p in patterns),
            "total_late": sum(p["late_filings"] for p in patterns),
            "overall_late_rate": round(
                sum(p["late_filings"] for p in patterns) /
                max(sum(p["total_filings"] for p in patterns), 1), 2
            ),
            "patterns": patterns,
        }

    # ── Industry Compliance ──────────────────────────────────────

    def industry_compliance(self) -> dict:
        """How do different industries compare on compliance?"""
        smes = self.list_smes()
        if not smes:
            return {"status": "no_data", "industries": []}

        # Load profiles and latest compliance for each
        industry_stats = defaultdict(lambda: {
            "sme_count": 0, "compliant": 0, "at_risk": 0,
            "critical": 0, "total_risk_score": 0,
        })

        for sme in smes:
            pin = sme["pin"]
            profile = self.load_sme(pin)
            if not profile:
                continue

            industry = profile.get("industry", "unknown")
            report_path = self.data_dir / "processed" / "obligations" / f"{pin}.json"
            if not report_path.exists():
                industry_stats[industry]["sme_count"] += 1
                continue

            report = self.load_json(report_path)
            compliance = report.get("compliance", {}).get("overall", "unknown")
            risk_score = report.get("risk", {}).get("risk_score", 0)

            stats = industry_stats[industry]
            stats["sme_count"] += 1
            stats["total_risk_score"] += risk_score
            if compliance == "compliant":
                stats["compliant"] += 1
            elif compliance == "at_risk":
                stats["at_risk"] += 1
            elif compliance in ("critical", "non_compliant"):
                stats["critical"] += 1

        industries = []
        for industry, stats in sorted(industry_stats.items(),
                                       key=lambda x: x[1]["total_risk_score"] / max(x[1]["sme_count"], 1),
                                       reverse=True):
            count = stats["sme_count"]
            avg_risk = round(stats["total_risk_score"] / count) if count else 0
            compliance_rate = round(stats["compliant"] / count, 2) if count else 0
            industries.append({
                "industry": industry,
                "sme_count": count,
                "compliant": stats["compliant"],
                "at_risk": stats["at_risk"],
                "critical": stats["critical"],
                "compliance_rate": compliance_rate,
                "avg_risk_score": avg_risk,
            })

        return {"status": "ok", "industries": industries}

    # ── Seasonal Patterns ────────────────────────────────────────

    def seasonal_patterns(self) -> dict:
        """Do filing behaviors change by month?"""
        filings = self.memory.get_outcomes("filing")
        if not filings:
            return {"status": "no_data", "months": []}

        by_month = defaultdict(lambda: {"total": 0, "late": 0})
        for f in filings:
            period = f.get("context", {}).get("period", "")
            if len(period) >= 7:
                month = int(period[5:7])
                by_month[month]["total"] += 1
                if f.get("outcome") == "late":
                    by_month[month]["late"] += 1

        month_names = [
            "", "January", "February", "March", "April", "May", "June",
            "July", "August", "September", "October", "November", "December",
        ]

        months = []
        for m in range(1, 13):
            stats = by_month.get(m, {"total": 0, "late": 0})
            total = stats["total"]
            late = stats["late"]
            rate = round(late / total, 2) if total else 0
            months.append({
                "month": m,
                "month_name": month_names[m],
                "total_filings": total,
                "late_filings": late,
                "late_rate": rate,
            })

        # Find peak late months
        peak_months = sorted(
            [m for m in months if m["total_filings"] > 0],
            key=lambda x: x["late_rate"], reverse=True
        )[:3]

        return {
            "status": "ok",
            "months": months,
            "peak_late_months": [m["month_name"] for m in peak_months],
        }

    # ── Risk Factor Frequency ────────────────────────────────────

    def risk_factor_frequency(self) -> dict:
        """Which risk factors appear most often across SMEs?"""
        smes = self.list_smes()
        if not smes:
            return {"status": "no_data", "factors": []}

        factor_counts = Counter()
        total_smes = 0

        for sme in smes:
            pin = sme["pin"]
            report_path = self.data_dir / "processed" / "obligations" / f"{pin}.json"
            if not report_path.exists():
                continue

            report = self.load_json(report_path)
            risk = report.get("risk", {})
            factors = risk.get("factors", [])
            total_smes += 1

            for factor in factors:
                if isinstance(factor, dict):
                    factor_counts[factor.get("factor", "unknown")] += 1
                elif isinstance(factor, str):
                    factor_counts[factor] += 1

        factors = []
        for factor, count in factor_counts.most_common():
            factors.append({
                "factor": factor,
                "count": count,
                "prevalence": round(count / total_smes, 2) if total_smes else 0,
            })

        return {"status": "ok", "total_smes_analyzed": total_smes, "factors": factors}

    # ── Escalation Patterns ──────────────────────────────────────

    def escalation_patterns(self) -> dict:
        """How often do escalations occur and at what tiers?"""
        escalations = self.memory.get_by_type("escalation")
        if not escalations:
            return {"status": "no_data", "tiers": {}}

        by_tier = Counter()
        by_pin = Counter()
        for e in escalations:
            tier = e.get("context", {}).get("tier", "unknown")
            by_tier[tier] += 1
            by_pin[e.get("pin", "unknown")] += 1

        repeat_offenders = [
            {"pin": pin, "escalation_count": count}
            for pin, count in by_pin.most_common(5)
            if count > 1
        ]

        return {
            "status": "ok",
            "total_escalations": len(escalations),
            "tiers": dict(by_tier),
            "repeat_offenders": repeat_offenders,
        }

    # ── SME Risk Trends ──────────────────────────────────────────

    def sme_risk_trends(self) -> dict:
        """Track how risk scores change over time for each SME."""
        risk_changes = self.memory.get_by_type("risk_change")
        if not risk_changes:
            return {"status": "no_data", "trends": []}

        by_pin = defaultdict(list)
        for r in risk_changes:
            pin = r.get("pin", "")
            ctx = r.get("context", {})
            by_pin[pin].append({
                "timestamp": r.get("timestamp"),
                "old_score": ctx.get("old_score", 0),
                "new_score": ctx.get("new_score", 0),
                "delta": ctx.get("delta", 0),
            })

        trends = []
        for pin, changes in by_pin.items():
            changes.sort(key=lambda x: x.get("timestamp", ""))
            net_delta = sum(c["delta"] for c in changes)
            direction = "improving" if net_delta < 0 else "worsening" if net_delta > 0 else "stable"
            trends.append({
                "pin": pin,
                "changes": len(changes),
                "net_delta": net_delta,
                "direction": direction,
                "latest_score": changes[-1]["new_score"],
            })

        # Sort: worsening first
        trends.sort(key=lambda t: t["net_delta"], reverse=True)

        return {"status": "ok", "trends": trends}

    # ── Console Output ───────────────────────────────────────────

    def print_report(self):
        """Print pattern report to console."""
        report = self.mine_all()

        print(f"\n{'='*65}")
        print(f"  THE BRAIN — Pattern Mining Report")
        print(f"{'='*65}")

        # Late filing patterns
        lfp = report.get("late_filing_patterns", {})
        if lfp.get("status") == "ok":
            print(f"\n  Late Filing Patterns:")
            print(f"    Overall late rate: {lfp['overall_late_rate']*100:.0f}%")
            for p in lfp.get("patterns", [])[:5]:
                print(f"    {p['tax_type']:30s} {p['late_rate']*100:5.1f}% late ({p['late_filings']}/{p['total_filings']})")

        # Industry compliance
        ic = report.get("industry_compliance", {})
        if ic.get("status") == "ok":
            print(f"\n  Industry Compliance:")
            for ind in ic.get("industries", [])[:5]:
                print(f"    {ind['industry']:30s} compliance={ind['compliance_rate']*100:.0f}% risk={ind['avg_risk_score']}")

        # Seasonal
        sp = report.get("seasonal_patterns", {})
        if sp.get("status") == "ok" and sp.get("peak_late_months"):
            print(f"\n  Peak Late Months: {', '.join(sp['peak_late_months'])}")

        # Risk factors
        rf = report.get("risk_factor_frequency", {})
        if rf.get("status") == "ok":
            print(f"\n  Top Risk Factors:")
            for f in rf.get("factors", [])[:5]:
                print(f"    {f['factor']:30s} {f['prevalence']*100:.0f}% of SMEs")

        # Escalations
        ep = report.get("escalation_patterns", {})
        if ep.get("status") == "ok":
            print(f"\n  Escalation Tiers: {ep.get('tiers', {})}")
            for ro in ep.get("repeat_offenders", []):
                print(f"    Repeat: {ro['pin']} ({ro['escalation_count']} escalations)")

        print()
