"""
MODEL UPDATER — proposes and applies risk model weight adjustments.
BOUNDARY: Proposes weight changes to staging/review for human approval.
Never auto-applies changes without human gate. All updates are:
  1. Proposed with reasoning
  2. Written to staging/review for approval
  3. Applied only after Steph approves
  4. Logged in audit trail
"""
import json
import copy
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ..base import BaseAgent
from .feedback_loop import FeedbackLoop
from .pattern_miner import PatternMiner

import sys
ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

from workflow.audit_trail import AuditTrail

EAT = timezone(timedelta(hours=3))

# Guardrails — no single weight can exceed these bounds
WEIGHT_BOUNDS = {
    "overdue_filings": (15, 45),
    "no_etims": (5, 25),
    "high_turnover_tot": (5, 20),
    "missing_employees": (5, 20),
    "inconsistent_income": (5, 20),
    "new_business": (0, 15),
    "cash_heavy_industry": (5, 20),
    "never_filed": (5, 20),
}

# Maximum change per update cycle
MAX_DELTA_PER_WEIGHT = 5
MAX_TOTAL_WEIGHT = 100


class ModelUpdater(BaseAgent):
    name = "model_updater"
    boundary = "Proposes weight changes for human review. Never auto-applies."

    def __init__(self):
        super().__init__()
        self.feedback = FeedbackLoop()
        self.miner = PatternMiner()
        self.audit = AuditTrail()
        self._proposals_dir = self.data_dir / "learning" / "proposals"
        self._proposals_dir.mkdir(parents=True, exist_ok=True)
        self._history_path = self.data_dir / "learning" / "update_history.jsonl"

    # ── Propose ──────────────────────────────────────────────────

    def propose_update(self) -> dict:
        """Analyze feedback + patterns and propose weight adjustments.
        Writes proposal to staging/review for human gate."""
        current_weights = dict(self._settings.get("risk", {}).get("weights", {}))

        # Get feedback report
        feedback = self.feedback.evaluate_all()
        patterns = self.miner.mine_all()

        # Calculate proposed adjustments
        adjustments = self._calculate_adjustments(current_weights, feedback, patterns)

        # Apply guardrails
        proposed_weights = self._apply_guardrails(current_weights, adjustments)

        # Build proposal
        proposal = {
            "type": "model_update_proposal",
            "status": "pending_review",
            "current_weights": current_weights,
            "proposed_weights": proposed_weights,
            "adjustments": adjustments,
            "reasoning": self._build_reasoning(adjustments, feedback, patterns),
            "guardrails_applied": self._check_guardrails(current_weights, proposed_weights),
            "feedback_summary": {
                "risk_accuracy": feedback.get("risk_accuracy", {}).get("accuracy"),
                "alert_lift": feedback.get("alert_effectiveness", {}).get("alert_lift"),
                "filing_on_time_rate": feedback.get("filing_timeliness", {}).get("on_time_rate"),
            },
            "proposed_at": datetime.now(EAT).isoformat(),
            "proposed_by": self.name,
        }

        # Save to proposals directory
        ts = datetime.now(EAT).strftime("%Y%m%d_%H%M%S")
        proposal_path = self._proposals_dir / f"proposal_{ts}.json"
        self.save_json(proposal_path, proposal)

        # Route to human gate
        self.write_staging("review", f"model_update_{ts}.json", proposal)

        self.log(f"Model update proposed: {len(adjustments)} adjustment(s)")
        self.audit.record("MODEL_UPDATE_PROPOSED", self.name, {
            "adjustments": len(adjustments),
            "proposal_file": proposal_path.name,
        })

        return proposal

    # ── Apply (after human approval) ─────────────────────────────

    def apply_proposal(self, proposal_file: str) -> dict:
        """Apply an approved proposal. Called only after human review."""
        # Load proposal
        proposal_path = self._proposals_dir / proposal_file
        if not proposal_path.exists():
            # Try staging
            proposal = self.read_staging("review", proposal_file)
            if not proposal:
                return {"status": "error", "message": f"Proposal not found: {proposal_file}"}
        else:
            proposal = self.load_json(proposal_path)

        if not proposal:
            return {"status": "error", "message": "Empty proposal"}

        proposed_weights = proposal.get("proposed_weights", {})
        current_weights = dict(self._settings.get("risk", {}).get("weights", {}))

        if not proposed_weights:
            return {"status": "error", "message": "No proposed weights in proposal"}

        # Update settings.json
        settings_path = self.config_dir / "settings.json"
        settings = self.load_json(settings_path)
        old_weights = dict(settings.get("risk", {}).get("weights", {}))
        settings["risk"]["weights"] = proposed_weights
        self.save_json(settings_path, settings)

        # Log the change
        self._record_update(old_weights, proposed_weights, proposal_file)

        # Mark proposal as applied
        proposal["status"] = "applied"
        proposal["applied_at"] = datetime.now(EAT).isoformat()
        proposal["applied_by"] = "human_approved"
        self.save_json(proposal_path, proposal)

        self.log(f"Model weights updated from proposal {proposal_file}")
        self.audit.record("MODEL_UPDATE_APPLIED", self.name, {
            "old_weights": old_weights,
            "new_weights": proposed_weights,
            "proposal_file": proposal_file,
        })

        return {
            "status": "applied",
            "old_weights": old_weights,
            "new_weights": proposed_weights,
            "proposal_file": proposal_file,
        }

    # ── Rollback ─────────────────────────────────────────────────

    def rollback_last(self) -> dict:
        """Rollback to previous weights. Returns result."""
        history = self._load_history()
        if not history:
            return {"status": "error", "message": "No update history to rollback"}

        last = history[-1]
        old_weights = last.get("old_weights", {})
        if not old_weights:
            return {"status": "error", "message": "No old weights in history"}

        settings_path = self.config_dir / "settings.json"
        settings = self.load_json(settings_path)
        current = dict(settings.get("risk", {}).get("weights", {}))
        settings["risk"]["weights"] = old_weights
        self.save_json(settings_path, settings)

        self.log("Model weights rolled back to previous version", "WARN")
        self.audit.record("MODEL_ROLLBACK", self.name, {
            "rolled_back_from": current,
            "rolled_back_to": old_weights,
        })

        return {
            "status": "rolled_back",
            "current_weights": current,
            "restored_weights": old_weights,
        }

    # ── Status ───────────────────────────────────────────────────

    def status(self) -> dict:
        """Get model updater status."""
        current_weights = dict(self._settings.get("risk", {}).get("weights", {}))
        history = self._load_history()
        pending = self._get_pending_proposals()

        return {
            "current_weights": current_weights,
            "total_weight": sum(current_weights.values()),
            "update_count": len(history),
            "last_update": history[-1].get("applied_at") if history else None,
            "pending_proposals": len(pending),
        }

    def get_pending_proposals(self) -> list[dict]:
        """Get all pending (unapproved) proposals."""
        return self._get_pending_proposals()

    # ── Weight Calculation ───────────────────────────────────────

    def _calculate_adjustments(self, current: dict, feedback: dict,
                                patterns: dict) -> list[dict]:
        """Calculate weight adjustments based on feedback and patterns."""
        adjustments = []

        # 1. Feedback-driven: from weight_recommendations
        recs = feedback.get("weight_recommendations", {}).get("recommendations", [])
        for rec in recs:
            action = rec.get("action", "")
            targets = rec.get("targets", [])
            magnitude = rec.get("magnitude", "small")

            delta = {"small": 2, "moderate": 3, "large": 5}.get(magnitude, 0)
            if action == "increase":
                for t in targets:
                    if t in current:
                        adjustments.append({
                            "weight": t,
                            "delta": delta,
                            "source": "feedback",
                            "reason": rec.get("reason", ""),
                        })
            elif action == "decrease":
                for t in targets:
                    if t in current:
                        adjustments.append({
                            "weight": t,
                            "delta": -delta,
                            "source": "feedback",
                            "reason": rec.get("reason", ""),
                        })

        # 2. Pattern-driven: if a risk factor is very prevalent but
        #    compliance is still poor, its weight may need increasing
        rf = patterns.get("risk_factor_frequency", {})
        ic = patterns.get("industry_compliance", {})

        if rf.get("status") == "ok":
            factors = rf.get("factors", [])
            for f in factors:
                factor_name = f.get("factor", "")
                prevalence = f.get("prevalence", 0)
                # If a factor appears in >60% of SMEs, it may be too broadly triggered
                if prevalence > 0.6 and factor_name in current:
                    # Check if we already have an adjustment for this
                    if not any(a["weight"] == factor_name for a in adjustments):
                        adjustments.append({
                            "weight": factor_name,
                            "delta": -2,
                            "source": "pattern",
                            "reason": f"{factor_name} triggers for {prevalence*100:.0f}% of SMEs — may be too broad",
                        })

        # 3. Filing pattern-driven: if certain tax types are chronically late,
        #    boost overdue_filings weight
        lfp = patterns.get("late_filing_patterns", {})
        if lfp.get("status") == "ok":
            overall_late_rate = lfp.get("overall_late_rate", 0)
            if overall_late_rate > 0.4 and not any(a["weight"] == "overdue_filings" for a in adjustments):
                adjustments.append({
                    "weight": "overdue_filings",
                    "delta": 3,
                    "source": "pattern",
                    "reason": f"Overall late filing rate {overall_late_rate*100:.0f}% — increase overdue weight",
                })

        return adjustments

    def _apply_guardrails(self, current: dict, adjustments: list[dict]) -> dict:
        """Apply adjustments with guardrails. Returns new weights dict."""
        proposed = dict(current)

        for adj in adjustments:
            weight = adj["weight"]
            delta = adj["delta"]
            if weight not in proposed:
                continue

            # Clamp delta
            delta = max(-MAX_DELTA_PER_WEIGHT, min(MAX_DELTA_PER_WEIGHT, delta))

            new_val = proposed[weight] + delta

            # Apply bounds
            lower, upper = WEIGHT_BOUNDS.get(weight, (0, 50))
            new_val = max(lower, min(upper, new_val))

            proposed[weight] = new_val

        # Normalize: total must equal MAX_TOTAL_WEIGHT
        total = sum(proposed.values())
        if total != MAX_TOTAL_WEIGHT and total > 0:
            scale = MAX_TOTAL_WEIGHT / total
            proposed = {k: round(v * scale) for k, v in proposed.items()}
            # Fix rounding drift
            diff = MAX_TOTAL_WEIGHT - sum(proposed.values())
            if diff != 0:
                # Add/subtract from the largest weight
                largest = max(proposed, key=proposed.get)
                proposed[largest] += diff

        return proposed

    def _check_guardrails(self, current: dict, proposed: dict) -> list[str]:
        """Check what guardrails were applied."""
        notes = []
        for weight, (lower, upper) in WEIGHT_BOUNDS.items():
            if weight in proposed:
                if proposed[weight] == lower:
                    notes.append(f"{weight} hit lower bound ({lower})")
                elif proposed[weight] == upper:
                    notes.append(f"{weight} hit upper bound ({upper})")

        total = sum(proposed.values())
        if total != MAX_TOTAL_WEIGHT:
            notes.append(f"Weights normalized: sum was {total}, adjusted to {MAX_TOTAL_WEIGHT}")

        if not notes:
            notes.append("No guardrails triggered — all adjustments within bounds")

        return notes

    def _build_reasoning(self, adjustments: list[dict], feedback: dict,
                          patterns: dict) -> list[str]:
        """Build human-readable reasoning for the proposal."""
        reasons = []

        if not adjustments:
            reasons.append("No adjustments needed — current weights are performing well.")
            return reasons

        for adj in adjustments:
            direction = "increase" if adj["delta"] > 0 else "decrease"
            reasons.append(
                f"{direction.capitalize()} '{adj['weight']}' by {abs(adj['delta'])} "
                f"({adj['source']}): {adj['reason']}"
            )

        risk_acc = feedback.get("risk_accuracy", {})
        if risk_acc.get("accuracy") is not None:
            reasons.append(f"Current risk model accuracy: {risk_acc['accuracy']*100:.0f}%")

        return reasons

    # ── History ──────────────────────────────────────────────────

    def _record_update(self, old_weights: dict, new_weights: dict, proposal_file: str):
        """Record an update in history."""
        entry = {
            "old_weights": old_weights,
            "new_weights": new_weights,
            "proposal_file": proposal_file,
            "applied_at": datetime.now(EAT).isoformat(),
        }
        with open(self._history_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def _load_history(self) -> list[dict]:
        """Load update history."""
        if not self._history_path.exists():
            return []
        entries = []
        try:
            with open(self._history_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            entries.append(json.loads(line))
                        except json.JSONDecodeError:
                            continue
        except OSError:
            return []
        return entries

    def _get_pending_proposals(self) -> list[dict]:
        """Get pending proposals from proposals directory."""
        if not self._proposals_dir.exists():
            return []
        pending = []
        for f in sorted(self._proposals_dir.glob("proposal_*.json")):
            try:
                data = self.load_json(f)
                if data.get("status") == "pending_review":
                    data["_filename"] = f.name
                    pending.append(data)
            except Exception:
                continue
        return pending

    # ── Console Output ───────────────────────────────────────────

    def print_status(self):
        """Print model updater status to console."""
        s = self.status()

        print(f"\n{'='*65}")
        print(f"  THE BRAIN — Model Updater")
        print(f"{'='*65}")

        print(f"\n  Current Weights (sum={s['total_weight']}):")
        for weight, value in s["current_weights"].items():
            bounds = WEIGHT_BOUNDS.get(weight, (0, 50))
            print(f"    {weight:30s} {value:3d}  (bounds: {bounds[0]}-{bounds[1]})")

        print(f"\n  Updates applied: {s['update_count']}")
        print(f"  Last update: {s['last_update'] or 'never'}")
        print(f"  Pending proposals: {s['pending_proposals']}")
        print()
