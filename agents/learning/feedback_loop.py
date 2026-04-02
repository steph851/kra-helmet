"""
FEEDBACK LOOP — compares predictions to actual outcomes.
BOUNDARY: Measures accuracy of past predictions. Never modifies models directly.
Correlates:
  - Risk scores at time of check → did the SME actually get a penalty?
  - Urgency level at alert time → did the SME file on time after being alerted?
  - Escalation tier → was the escalation justified by outcome?
Produces accuracy metrics that model_updater consumes.
"""
import json
from datetime import datetime, timedelta, timezone
from collections import defaultdict
from pathlib import Path

from ..base import BaseAgent
from .memory import DecisionMemory

EAT = timezone(timedelta(hours=3))


class FeedbackLoop(BaseAgent):
    name = "feedback_loop"
    boundary = "Measures prediction accuracy. Never modifies models or takes action."

    def __init__(self):
        super().__init__()
        self.memory = DecisionMemory()
        self._feedback_path = self.data_dir / "learning" / "feedback_scores.json"
        self._feedback_path.parent.mkdir(parents=True, exist_ok=True)

    def evaluate_all(self) -> dict:
        """Run all feedback evaluations. Returns combined accuracy report."""
        report = {
            "type": "feedback_report",
            "risk_accuracy": self.safe_run(
                self.evaluate_risk_predictions, context="risk", fallback={}),
            "alert_effectiveness": self.safe_run(
                self.evaluate_alert_effectiveness, context="alerts", fallback={}),
            "escalation_accuracy": self.safe_run(
                self.evaluate_escalation_accuracy, context="escalations", fallback={}),
            "filing_timeliness": self.safe_run(
                self.evaluate_filing_timeliness, context="timeliness", fallback={}),
            "weight_recommendations": {},
            "evaluated_at": datetime.now(EAT).isoformat(),
            "evaluated_by": self.name,
        }

        # Generate weight recommendations based on findings
        report["weight_recommendations"] = self._generate_weight_recommendations(report)

        # Save feedback scores
        self.save_json(self._feedback_path, report)

        return report

    # ── Risk Prediction Accuracy ─────────────────────────────────

    def evaluate_risk_predictions(self) -> dict:
        """Were high-risk SMEs actually the ones that ended up non-compliant?"""
        checks = self.memory.get_by_type("compliance_check")
        filings = self.memory.get_outcomes("filing")
        if not checks:
            return {"status": "no_data"}

        # Group checks by PIN — take the latest
        latest_check = {}
        for c in checks:
            pin = c.get("pin", "")
            if pin:
                latest_check[pin] = c

        # Group filing outcomes by PIN
        filing_outcomes = defaultdict(lambda: {"total": 0, "late": 0})
        for f in filings:
            pin = f.get("pin", "")
            filing_outcomes[pin]["total"] += 1
            if f.get("outcome") == "late":
                filing_outcomes[pin]["late"] += 1

        # Compare predictions vs outcomes
        predictions = []
        for pin, check in latest_check.items():
            ctx = check.get("context", {})
            risk_score = ctx.get("risk_score", 0)
            risk_level = ctx.get("risk_level", "unknown")
            predicted_risky = risk_score >= 50  # high or critical

            outcomes = filing_outcomes.get(pin)
            if not outcomes or outcomes["total"] == 0:
                continue

            actual_late_rate = outcomes["late"] / outcomes["total"]
            actually_risky = actual_late_rate > 0.3

            predictions.append({
                "pin": pin,
                "predicted_risk_score": risk_score,
                "predicted_risk_level": risk_level,
                "predicted_risky": predicted_risky,
                "actual_late_rate": round(actual_late_rate, 2),
                "actually_risky": actually_risky,
                "correct": predicted_risky == actually_risky,
            })

        if not predictions:
            return {"status": "insufficient_data", "note": "Need both checks and filing outcomes"}

        correct = sum(1 for p in predictions if p["correct"])
        total = len(predictions)
        accuracy = round(correct / total, 2) if total else 0

        # Breakdown
        true_positives = sum(1 for p in predictions if p["predicted_risky"] and p["actually_risky"])
        false_positives = sum(1 for p in predictions if p["predicted_risky"] and not p["actually_risky"])
        true_negatives = sum(1 for p in predictions if not p["predicted_risky"] and not p["actually_risky"])
        false_negatives = sum(1 for p in predictions if not p["predicted_risky"] and p["actually_risky"])

        precision = round(true_positives / max(true_positives + false_positives, 1), 2)
        recall = round(true_positives / max(true_positives + false_negatives, 1), 2)

        return {
            "status": "ok",
            "accuracy": accuracy,
            "precision": precision,
            "recall": recall,
            "total_evaluated": total,
            "true_positives": true_positives,
            "false_positives": false_positives,
            "true_negatives": true_negatives,
            "false_negatives": false_negatives,
            "details": predictions,
        }

    # ── Alert Effectiveness ──────────────────────────────────────

    def evaluate_alert_effectiveness(self) -> dict:
        """Do SMEs that receive alerts file more on time than those that don't?"""
        alerts = self.memory.get_by_type("alert")
        filings = self.memory.get_outcomes("filing")
        if not alerts or not filings:
            return {"status": "no_data"}

        # Which PINs were alerted?
        alerted_pins = set()
        for a in alerts:
            pin = a.get("pin", "")
            if pin and a.get("outcome") == "delivered":
                alerted_pins.add(pin)

        # Filing outcomes split by alerted/not-alerted
        alerted = {"total": 0, "on_time": 0}
        not_alerted = {"total": 0, "on_time": 0}

        for f in filings:
            pin = f.get("pin", "")
            bucket = alerted if pin in alerted_pins else not_alerted
            bucket["total"] += 1
            if f.get("outcome") == "on_time":
                bucket["on_time"] += 1

        alerted_rate = round(alerted["on_time"] / max(alerted["total"], 1), 2)
        not_alerted_rate = round(not_alerted["on_time"] / max(not_alerted["total"], 1), 2)
        lift = round(alerted_rate - not_alerted_rate, 2)

        return {
            "status": "ok",
            "alerted_smes": len(alerted_pins),
            "alerted_on_time_rate": alerted_rate,
            "not_alerted_on_time_rate": not_alerted_rate,
            "alert_lift": lift,
            "effective": lift > 0,
            "alerted_filings": alerted,
            "not_alerted_filings": not_alerted,
        }

    # ── Escalation Accuracy ──────────────────────────────────────

    def evaluate_escalation_accuracy(self) -> dict:
        """Were escalations justified? Did escalated SMEs have worse outcomes?"""
        escalations = self.memory.get_by_type("escalation")
        filings = self.memory.get_outcomes("filing")
        if not escalations:
            return {"status": "no_data"}

        escalated_pins = set()
        by_tier = defaultdict(set)
        for e in escalations:
            pin = e.get("pin", "")
            tier = e.get("context", {}).get("tier", "unknown")
            escalated_pins.add(pin)
            by_tier[tier].add(pin)

        # Filing outcomes for escalated SMEs
        escalated_late = 0
        escalated_total = 0
        non_escalated_late = 0
        non_escalated_total = 0

        for f in filings:
            pin = f.get("pin", "")
            is_late = f.get("outcome") == "late"
            if pin in escalated_pins:
                escalated_total += 1
                if is_late:
                    escalated_late += 1
            else:
                non_escalated_total += 1
                if is_late:
                    non_escalated_late += 1

        esc_late_rate = round(escalated_late / max(escalated_total, 1), 2)
        non_esc_late_rate = round(non_escalated_late / max(non_escalated_total, 1), 2)

        return {
            "status": "ok",
            "total_escalations": len(escalations),
            "escalated_smes": len(escalated_pins),
            "tiers": {tier: len(pins) for tier, pins in by_tier.items()},
            "escalated_late_rate": esc_late_rate,
            "non_escalated_late_rate": non_esc_late_rate,
            "justified": esc_late_rate >= non_esc_late_rate,
        }

    # ── Filing Timeliness ────────────────────────────────────────

    def evaluate_filing_timeliness(self) -> dict:
        """Overall filing timeliness across all SMEs."""
        filings = self.memory.get_outcomes("filing")
        if not filings:
            return {"status": "no_data"}

        total = len(filings)
        on_time = sum(1 for f in filings if f.get("outcome") == "on_time")
        late = sum(1 for f in filings if f.get("outcome") == "late")

        by_pin = defaultdict(lambda: {"total": 0, "late": 0})
        for f in filings:
            pin = f.get("pin", "")
            by_pin[pin]["total"] += 1
            if f.get("outcome") == "late":
                by_pin[pin]["late"] += 1

        # SMEs ranked by late rate
        sme_scores = []
        for pin, stats in by_pin.items():
            rate = round(stats["late"] / stats["total"], 2) if stats["total"] else 0
            sme_scores.append({"pin": pin, "late_rate": rate, "filings": stats["total"]})
        sme_scores.sort(key=lambda s: s["late_rate"], reverse=True)

        return {
            "status": "ok",
            "total_filings": total,
            "on_time": on_time,
            "late": late,
            "on_time_rate": round(on_time / max(total, 1), 2),
            "worst_performers": sme_scores[:5],
            "best_performers": sme_scores[-5:] if len(sme_scores) >= 5 else [],
        }

    # ── Weight Recommendations ───────────────────────────────────

    def _generate_weight_recommendations(self, report: dict) -> dict:
        """Based on feedback, recommend weight adjustments for model_updater."""
        recommendations = []
        current_weights = self._settings.get("risk", {}).get("weights", {})

        risk_acc = report.get("risk_accuracy", {})
        if risk_acc.get("status") == "ok":
            # High false negatives → risk model is too lenient
            fn = risk_acc.get("false_negatives", 0)
            fp = risk_acc.get("false_positives", 0)
            total = risk_acc.get("total_evaluated", 0)

            if total > 0:
                fn_rate = fn / total
                fp_rate = fp / total

                if fn_rate > 0.2:
                    recommendations.append({
                        "action": "increase",
                        "reason": f"False negative rate {fn_rate:.0%} — model misses risky SMEs",
                        "targets": ["overdue_filings", "never_filed"],
                        "magnitude": "moderate",
                    })
                elif fp_rate > 0.3:
                    recommendations.append({
                        "action": "decrease",
                        "reason": f"False positive rate {fp_rate:.0%} — model flags too many safe SMEs",
                        "targets": ["new_business", "cash_heavy_industry"],
                        "magnitude": "small",
                    })

            accuracy = risk_acc.get("accuracy", 0)
            if accuracy >= 0.8:
                recommendations.append({
                    "action": "maintain",
                    "reason": f"Risk accuracy {accuracy:.0%} — model performing well",
                    "targets": [],
                    "magnitude": "none",
                })

        alert_eff = report.get("alert_effectiveness", {})
        if alert_eff.get("status") == "ok":
            lift = alert_eff.get("alert_lift", 0)
            if lift <= 0:
                recommendations.append({
                    "action": "review_alerts",
                    "reason": "Alerts are not improving filing behavior — consider timing/content changes",
                    "targets": [],
                    "magnitude": "review",
                })

        return {
            "recommendations": recommendations,
            "current_weights": current_weights,
        }

    # ── Load last feedback ───────────────────────────────────────

    def get_last_feedback(self) -> dict | None:
        """Load the most recent feedback report."""
        if self._feedback_path.exists():
            return self.load_json(self._feedback_path)
        return None

    # ── Console Output ───────────────────────────────────────────

    def print_report(self):
        """Print feedback report to console."""
        report = self.evaluate_all()

        print(f"\n{'='*65}")
        print(f"  THE BRAIN — Feedback Loop Report")
        print(f"{'='*65}")

        # Risk accuracy
        ra = report.get("risk_accuracy", {})
        if ra.get("status") == "ok":
            print(f"\n  Risk Prediction Accuracy:")
            print(f"    Accuracy:  {ra['accuracy']*100:.0f}%")
            print(f"    Precision: {ra['precision']*100:.0f}%")
            print(f"    Recall:    {ra['recall']*100:.0f}%")
            print(f"    TP={ra['true_positives']} FP={ra['false_positives']} "
                  f"TN={ra['true_negatives']} FN={ra['false_negatives']}")
        else:
            print(f"\n  Risk Accuracy: {ra.get('status', 'no data')}")

        # Alert effectiveness
        ae = report.get("alert_effectiveness", {})
        if ae.get("status") == "ok":
            print(f"\n  Alert Effectiveness:")
            print(f"    Alerted on-time rate:     {ae['alerted_on_time_rate']*100:.0f}%")
            print(f"    Not-alerted on-time rate:  {ae['not_alerted_on_time_rate']*100:.0f}%")
            print(f"    Lift: {ae['alert_lift']*100:+.0f}pp {'(effective)' if ae['effective'] else '(not effective)'}")

        # Filing timeliness
        ft = report.get("filing_timeliness", {})
        if ft.get("status") == "ok":
            print(f"\n  Filing Timeliness:")
            print(f"    On-time rate: {ft['on_time_rate']*100:.0f}% ({ft['on_time']}/{ft['total_filings']})")

        # Weight recommendations
        wr = report.get("weight_recommendations", {})
        recs = wr.get("recommendations", [])
        if recs:
            print(f"\n  Weight Recommendations:")
            for r in recs:
                targets = ", ".join(r["targets"]) if r["targets"] else "—"
                print(f"    [{r['action'].upper()}] {r['reason']}")
                if r["targets"]:
                    print(f"      Targets: {targets} ({r['magnitude']})")

        print()
