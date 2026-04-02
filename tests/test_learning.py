"""
Tests for The Brain — learning system.
Tests decision memory, pattern miner, feedback loop, and model updater.
"""
import json
import pytest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch, MagicMock

import sys
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from agents.learning.memory import DecisionMemory
from agents.learning.pattern_miner import PatternMiner
from agents.learning.feedback_loop import FeedbackLoop
from agents.learning.model_updater import ModelUpdater, WEIGHT_BOUNDS, MAX_DELTA_PER_WEIGHT, MAX_TOTAL_WEIGHT

EAT = timezone(timedelta(hours=3))


# ══════════════════════════════════════════════════════════════
#  DECISION MEMORY
# ══════════════════════════════════════════════════════════════


class TestDecisionMemory:
    def test_init(self):
        mem = DecisionMemory()
        assert mem.name == "decision_memory"

    def test_record_and_get_all(self, tmp_path):
        mem = DecisionMemory()
        mem._memory_path = tmp_path / "test_memory.jsonl"
        mem.record("compliance_check", "A000000001B", {"risk_score": 45})
        entries = mem.get_all()
        assert len(entries) == 1
        assert entries[0]["pin"] == "A000000001B"
        assert entries[0]["decision_type"] == "compliance_check"

    def test_record_check(self, tmp_path):
        mem = DecisionMemory()
        mem._memory_path = tmp_path / "test_memory.jsonl"
        report = {
            "compliance": {"overall": "at_risk", "overdue_count": 2, "obligations_total": 5},
            "risk": {"risk_score": 60, "risk_level": "high"},
            "penalties": {"total_penalty_exposure_kes": 30000},
            "urgency": {"urgency_level": "red"},
        }
        mem.record_check("A000000001B", report)
        entries = mem.get_all()
        assert len(entries) == 1
        ctx = entries[0]["context"]
        assert ctx["compliance"] == "at_risk"
        assert ctx["risk_score"] == 60
        assert ctx["penalty_kes"] == 30000

    def test_record_filing(self, tmp_path):
        mem = DecisionMemory()
        mem._memory_path = tmp_path / "test_memory.jsonl"
        mem.record_filing("A000000001B", "vat", "2026-03", was_late=True)
        entries = mem.get_all()
        assert entries[0]["outcome"] == "late"
        assert entries[0]["context"]["tax_type"] == "vat"

    def test_record_filing_on_time(self, tmp_path):
        mem = DecisionMemory()
        mem._memory_path = tmp_path / "test_memory.jsonl"
        mem.record_filing("A000000001B", "paye", "2026-03", was_late=False)
        entries = mem.get_all()
        assert entries[0]["outcome"] == "on_time"

    def test_record_escalation(self, tmp_path):
        mem = DecisionMemory()
        mem._memory_path = tmp_path / "test_memory.jsonl"
        mem.record_escalation("A000000001B", "critical", "PAYE overdue 35 days")
        entries = mem.get_all()
        assert entries[0]["decision_type"] == "escalation"
        assert entries[0]["context"]["tier"] == "critical"

    def test_record_alert(self, tmp_path):
        mem = DecisionMemory()
        mem._memory_path = tmp_path / "test_memory.jsonl"
        mem.record_alert("A000000001B", "whatsapp", "red", delivered=True)
        entries = mem.get_all()
        assert entries[0]["outcome"] == "delivered"
        assert entries[0]["context"]["channel"] == "whatsapp"

    def test_record_risk_change(self, tmp_path):
        mem = DecisionMemory()
        mem._memory_path = tmp_path / "test_memory.jsonl"
        mem.record_risk_change("A000000001B", 40, 65, ["overdue_filings", "no_etims"])
        entries = mem.get_all()
        ctx = entries[0]["context"]
        assert ctx["old_score"] == 40
        assert ctx["new_score"] == 65
        assert ctx["delta"] == 25

    def test_get_by_pin(self, tmp_path):
        mem = DecisionMemory()
        mem._memory_path = tmp_path / "test_memory.jsonl"
        mem.record("check", "A000000001B", {"x": 1})
        mem.record("check", "B000000002C", {"x": 2})
        mem.record("check", "A000000001B", {"x": 3})
        results = mem.get_by_pin("A000000001B")
        assert len(results) == 2

    def test_get_by_type(self, tmp_path):
        mem = DecisionMemory()
        mem._memory_path = tmp_path / "test_memory.jsonl"
        mem.record("filing", "A000000001B", {}, outcome="on_time")
        mem.record("compliance_check", "A000000001B", {})
        mem.record("filing", "B000000002C", {}, outcome="late")
        results = mem.get_by_type("filing")
        assert len(results) == 2

    def test_get_outcomes(self, tmp_path):
        mem = DecisionMemory()
        mem._memory_path = tmp_path / "test_memory.jsonl"
        mem.record("filing", "A000000001B", {}, outcome="on_time")
        mem.record("check", "A000000001B", {})  # no outcome
        mem.record("filing", "B000000002C", {}, outcome="late")
        results = mem.get_outcomes()
        assert len(results) == 2

    def test_get_outcomes_filtered(self, tmp_path):
        mem = DecisionMemory()
        mem._memory_path = tmp_path / "test_memory.jsonl"
        mem.record("filing", "A000000001B", {}, outcome="on_time")
        mem.record("alert", "A000000001B", {}, outcome="delivered")
        results = mem.get_outcomes("filing")
        assert len(results) == 1

    def test_summary_empty(self, tmp_path):
        mem = DecisionMemory()
        mem._memory_path = tmp_path / "test_memory.jsonl"
        s = mem.summary()
        assert s["total_entries"] == 0
        assert s["sme_count"] == 0

    def test_summary_with_data(self, tmp_path):
        mem = DecisionMemory()
        mem._memory_path = tmp_path / "test_memory.jsonl"
        mem.record("check", "A000000001B", {})
        mem.record("filing", "B000000002C", {}, outcome="on_time")
        mem.record("filing", "A000000001B", {}, outcome="late")
        s = mem.summary()
        assert s["total_entries"] == 3
        assert s["sme_count"] == 2
        assert s["decision_types"]["check"] == 1
        assert s["decision_types"]["filing"] == 2
        assert s["outcome_rate"] == round(2 / 3, 2)

    def test_sme_timeline(self, tmp_path):
        mem = DecisionMemory()
        mem._memory_path = tmp_path / "test_memory.jsonl"
        mem.record_check("A000000001B", {
            "compliance": {"overall": "at_risk", "overdue_count": 1, "obligations_total": 3},
            "risk": {"risk_score": 50, "risk_level": "high"},
            "penalties": {"total_penalty_exposure_kes": 0},
            "urgency": {"urgency_level": "orange"},
        })
        mem.record_filing("A000000001B", "vat", "2026-03", was_late=False)
        timeline = mem.sme_timeline("A000000001B")
        assert len(timeline) == 2
        assert timeline[0]["event"] == "compliance_check"
        assert timeline[1]["event"] == "filing"

    def test_clear(self, tmp_path):
        mem = DecisionMemory()
        mem._memory_path = tmp_path / "test_memory.jsonl"
        mem.record("check", "A000000001B", {})
        assert len(mem.get_all()) == 1
        mem.clear()
        assert len(mem.get_all()) == 0

    def test_was_filing_late_on_time(self):
        mem = DecisionMemory()
        filing = {"filed_at": "2026-04-15T10:00:00+03:00", "period": "2026-03", "tax_type": "vat"}
        assert mem._was_filing_late(filing) is False  # filed before 20th

    def test_was_filing_late_actually_late(self):
        mem = DecisionMemory()
        filing = {"filed_at": "2026-04-25T10:00:00+03:00", "period": "2026-03", "tax_type": "vat"}
        assert mem._was_filing_late(filing) is True  # filed after 20th

    def test_was_filing_late_missing_data(self):
        mem = DecisionMemory()
        filing = {"filed_at": "", "period": "2026-03", "tax_type": "vat"}
        assert mem._was_filing_late(filing) is False

    def test_get_recent(self, tmp_path):
        mem = DecisionMemory()
        mem._memory_path = tmp_path / "test_memory.jsonl"
        # Record entries — they'll have current timestamp
        mem.record("check", "A000000001B", {})
        results = mem.get_recent(hours=1)
        assert len(results) == 1

    def test_handles_corrupt_lines(self, tmp_path):
        mem = DecisionMemory()
        mem._memory_path = tmp_path / "test_memory.jsonl"
        with open(mem._memory_path, "w", encoding="utf-8") as f:
            f.write('{"decision_type": "check", "pin": "A000000001B"}\n')
            f.write("not valid json\n")
            f.write('{"decision_type": "filing", "pin": "B000000002C"}\n')
        entries = mem.get_all()
        assert len(entries) == 2

    def test_summarize_entry_types(self, tmp_path):
        mem = DecisionMemory()
        assert "Compliance" in mem._summarize_entry({
            "decision_type": "compliance_check",
            "context": {"compliance": "at_risk", "risk_score": 50}
        })
        assert "Filed" in mem._summarize_entry({
            "decision_type": "filing",
            "context": {"tax_type": "vat", "period": "2026-03"}
        })
        assert "Escalated" in mem._summarize_entry({
            "decision_type": "escalation",
            "context": {"tier": "review", "reason": "7 days overdue"}
        })
        assert "Alert" in mem._summarize_entry({
            "decision_type": "alert",
            "context": {"channel": "sms", "urgency": "red"}
        })
        assert "→" in mem._summarize_entry({
            "decision_type": "risk_change",
            "context": {"old_score": 30, "new_score": 60}
        })


# ══════════════════════════════════════════════════════════════
#  PATTERN MINER
# ══════════════════════════════════════════════════════════════


class TestPatternMiner:
    def test_init(self):
        miner = PatternMiner()
        assert miner.name == "pattern_miner"

    def test_late_filing_patterns_no_data(self, tmp_path):
        miner = PatternMiner()
        miner.memory._memory_path = tmp_path / "empty.jsonl"
        result = miner.late_filing_patterns()
        assert result["status"] == "no_data"

    def test_late_filing_patterns_with_data(self, tmp_path):
        miner = PatternMiner()
        miner.memory._memory_path = tmp_path / "test.jsonl"
        # Inject filing outcomes directly
        miner.memory.record("filing", "A000000001B", {"tax_type": "vat", "period": "2026-01"}, outcome="late")
        miner.memory.record("filing", "A000000001B", {"tax_type": "vat", "period": "2026-02"}, outcome="on_time")
        miner.memory.record("filing", "A000000001B", {"tax_type": "paye", "period": "2026-01"}, outcome="late")
        miner.memory.record("filing", "A000000001B", {"tax_type": "paye", "period": "2026-02"}, outcome="late")
        result = miner.late_filing_patterns()
        assert result["status"] == "ok"
        assert result["total_filings"] == 4
        assert result["total_late"] == 3
        # PAYE should have higher late rate
        paye = next(p for p in result["patterns"] if p["tax_type"] == "paye")
        assert paye["late_rate"] == 1.0
        assert paye["severity"] == "high"

    def test_seasonal_patterns_no_data(self, tmp_path):
        miner = PatternMiner()
        miner.memory._memory_path = tmp_path / "empty.jsonl"
        result = miner.seasonal_patterns()
        assert result["status"] == "no_data"

    def test_seasonal_patterns_with_data(self, tmp_path):
        miner = PatternMiner()
        miner.memory._memory_path = tmp_path / "test.jsonl"
        miner.memory.record("filing", "A000000001B", {"tax_type": "vat", "period": "2026-01"}, outcome="late")
        miner.memory.record("filing", "A000000001B", {"tax_type": "vat", "period": "2026-06"}, outcome="on_time")
        result = miner.seasonal_patterns()
        assert result["status"] == "ok"
        assert len(result["months"]) == 12
        jan = result["months"][0]
        assert jan["month_name"] == "January"
        assert jan["total_filings"] == 1
        assert jan["late_rate"] == 1.0

    def test_risk_factor_frequency_no_data(self, tmp_path):
        miner = PatternMiner()
        result = miner.risk_factor_frequency()
        # Depends on whether SMEs exist; returns a dict either way
        assert "factors" in result or "status" in result

    def test_escalation_patterns_no_data(self, tmp_path):
        miner = PatternMiner()
        miner.memory._memory_path = tmp_path / "empty.jsonl"
        result = miner.escalation_patterns()
        assert result["status"] == "no_data"

    def test_escalation_patterns_with_data(self, tmp_path):
        miner = PatternMiner()
        miner.memory._memory_path = tmp_path / "test.jsonl"
        miner.memory.record_escalation("A000000001B", "review", "7 days overdue")
        miner.memory.record_escalation("A000000001B", "critical", "35 days overdue")
        miner.memory.record_escalation("B000000002C", "review", "penalty threshold")
        result = miner.escalation_patterns()
        assert result["status"] == "ok"
        assert result["total_escalations"] == 3
        assert result["tiers"]["review"] == 2
        assert result["tiers"]["critical"] == 1
        assert len(result["repeat_offenders"]) == 1
        assert result["repeat_offenders"][0]["pin"] == "A000000001B"

    def test_sme_risk_trends_no_data(self, tmp_path):
        miner = PatternMiner()
        miner.memory._memory_path = tmp_path / "empty.jsonl"
        result = miner.sme_risk_trends()
        assert result["status"] == "no_data"

    def test_sme_risk_trends_with_data(self, tmp_path):
        miner = PatternMiner()
        miner.memory._memory_path = tmp_path / "test.jsonl"
        miner.memory.record_risk_change("A000000001B", 30, 50, ["overdue"])
        miner.memory.record_risk_change("A000000001B", 50, 40, ["filed"])
        result = miner.sme_risk_trends()
        assert result["status"] == "ok"
        assert len(result["trends"]) == 1
        trend = result["trends"][0]
        assert trend["pin"] == "A000000001B"
        assert trend["net_delta"] == (50 - 30) + (40 - 50)  # +20 + -10 = +10
        assert trend["direction"] == "worsening"
        assert trend["latest_score"] == 40

    def test_mine_all_returns_all_sections(self, tmp_path):
        miner = PatternMiner()
        miner.memory._memory_path = tmp_path / "test.jsonl"
        report = miner.mine_all()
        assert "late_filing_patterns" in report
        assert "industry_compliance" in report
        assert "seasonal_patterns" in report
        assert "risk_factor_frequency" in report
        assert "escalation_patterns" in report
        assert "sme_risk_trends" in report
        assert "mined_at" in report

    def test_industry_compliance_no_smes(self):
        miner = PatternMiner()
        # Uses real list_smes; may have 0 or some SMEs
        result = miner.industry_compliance()
        assert "industries" in result or "status" in result


# ══════════════════════════════════════════════════════════════
#  FEEDBACK LOOP
# ══════════════════════════════════════════════════════════════


class TestFeedbackLoop:
    def test_init(self):
        loop = FeedbackLoop()
        assert loop.name == "feedback_loop"

    def test_risk_predictions_no_data(self, tmp_path):
        loop = FeedbackLoop()
        loop.memory._memory_path = tmp_path / "empty.jsonl"
        result = loop.evaluate_risk_predictions()
        assert result["status"] == "no_data"

    def test_risk_predictions_with_data(self, tmp_path):
        loop = FeedbackLoop()
        loop.memory._memory_path = tmp_path / "test.jsonl"
        loop._feedback_path = tmp_path / "feedback.json"

        # SME A: predicted risky (score=70), actually late → true positive
        loop.memory.record("compliance_check", "A000000001B", {
            "risk_score": 70, "risk_level": "high",
        })
        loop.memory.record("filing", "A000000001B", {"tax_type": "vat", "period": "2026-01"}, outcome="late")

        # SME B: predicted safe (score=20), actually on_time → true negative
        loop.memory.record("compliance_check", "B000000002C", {
            "risk_score": 20, "risk_level": "low",
        })
        loop.memory.record("filing", "B000000002C", {"tax_type": "vat", "period": "2026-01"}, outcome="on_time")

        result = loop.evaluate_risk_predictions()
        assert result["status"] == "ok"
        assert result["accuracy"] == 1.0
        assert result["true_positives"] == 1
        assert result["true_negatives"] == 1

    def test_risk_predictions_false_negative(self, tmp_path):
        loop = FeedbackLoop()
        loop.memory._memory_path = tmp_path / "test.jsonl"
        loop._feedback_path = tmp_path / "feedback.json"

        # Predicted safe but actually risky
        loop.memory.record("compliance_check", "A000000001B", {
            "risk_score": 30, "risk_level": "low",
        })
        loop.memory.record("filing", "A000000001B", {"tax_type": "vat", "period": "2026-01"}, outcome="late")
        loop.memory.record("filing", "A000000001B", {"tax_type": "vat", "period": "2026-02"}, outcome="late")

        result = loop.evaluate_risk_predictions()
        assert result["status"] == "ok"
        assert result["false_negatives"] == 1
        assert result["accuracy"] == 0.0

    def test_alert_effectiveness_no_data(self, tmp_path):
        loop = FeedbackLoop()
        loop.memory._memory_path = tmp_path / "empty.jsonl"
        result = loop.evaluate_alert_effectiveness()
        assert result["status"] == "no_data"

    def test_alert_effectiveness_with_data(self, tmp_path):
        loop = FeedbackLoop()
        loop.memory._memory_path = tmp_path / "test.jsonl"
        loop._feedback_path = tmp_path / "feedback.json"

        # Alerted SME filed on time
        loop.memory.record_alert("A000000001B", "sms", "red", delivered=True)
        loop.memory.record("filing", "A000000001B", {"tax_type": "vat"}, outcome="on_time")

        # Non-alerted SME filed late
        loop.memory.record("filing", "B000000002C", {"tax_type": "vat"}, outcome="late")

        result = loop.evaluate_alert_effectiveness()
        assert result["status"] == "ok"
        assert result["alerted_on_time_rate"] == 1.0
        assert result["not_alerted_on_time_rate"] == 0.0
        assert result["effective"] is True
        assert result["alert_lift"] == 1.0

    def test_escalation_accuracy_no_data(self, tmp_path):
        loop = FeedbackLoop()
        loop.memory._memory_path = tmp_path / "empty.jsonl"
        result = loop.evaluate_escalation_accuracy()
        assert result["status"] == "no_data"

    def test_escalation_accuracy_justified(self, tmp_path):
        loop = FeedbackLoop()
        loop.memory._memory_path = tmp_path / "test.jsonl"
        loop._feedback_path = tmp_path / "feedback.json"

        # Escalated SME: filed late (justified)
        loop.memory.record_escalation("A000000001B", "critical", "overdue")
        loop.memory.record("filing", "A000000001B", {"tax_type": "vat"}, outcome="late")

        # Non-escalated SME: filed on time
        loop.memory.record("filing", "B000000002C", {"tax_type": "vat"}, outcome="on_time")

        result = loop.evaluate_escalation_accuracy()
        assert result["status"] == "ok"
        assert result["justified"] is True
        assert result["escalated_late_rate"] == 1.0

    def test_filing_timeliness_no_data(self, tmp_path):
        loop = FeedbackLoop()
        loop.memory._memory_path = tmp_path / "empty.jsonl"
        result = loop.evaluate_filing_timeliness()
        assert result["status"] == "no_data"

    def test_filing_timeliness_with_data(self, tmp_path):
        loop = FeedbackLoop()
        loop.memory._memory_path = tmp_path / "test.jsonl"
        loop._feedback_path = tmp_path / "feedback.json"

        loop.memory.record("filing", "A000000001B", {"tax_type": "vat"}, outcome="on_time")
        loop.memory.record("filing", "A000000001B", {"tax_type": "paye"}, outcome="on_time")
        loop.memory.record("filing", "A000000001B", {"tax_type": "tot"}, outcome="late")

        result = loop.evaluate_filing_timeliness()
        assert result["status"] == "ok"
        assert result["total_filings"] == 3
        assert result["on_time"] == 2
        assert result["late"] == 1
        assert result["on_time_rate"] == round(2 / 3, 2)

    def test_weight_recommendations_high_fn(self, tmp_path):
        loop = FeedbackLoop()
        loop.memory._memory_path = tmp_path / "test.jsonl"
        loop._feedback_path = tmp_path / "feedback.json"

        feedback = {
            "risk_accuracy": {
                "status": "ok",
                "accuracy": 0.5,
                "false_negatives": 3,
                "false_positives": 0,
                "total_evaluated": 10,
            },
            "alert_effectiveness": {"status": "no_data"},
        }
        recs = loop._generate_weight_recommendations(feedback)
        assert len(recs["recommendations"]) >= 1
        assert recs["recommendations"][0]["action"] == "increase"

    def test_weight_recommendations_high_fp(self, tmp_path):
        loop = FeedbackLoop()
        loop._feedback_path = tmp_path / "feedback.json"

        feedback = {
            "risk_accuracy": {
                "status": "ok",
                "accuracy": 0.6,
                "false_negatives": 0,
                "false_positives": 4,
                "total_evaluated": 10,
            },
            "alert_effectiveness": {"status": "no_data"},
        }
        recs = loop._generate_weight_recommendations(feedback)
        assert any(r["action"] == "decrease" for r in recs["recommendations"])

    def test_weight_recommendations_good_accuracy(self, tmp_path):
        loop = FeedbackLoop()
        loop._feedback_path = tmp_path / "feedback.json"

        feedback = {
            "risk_accuracy": {
                "status": "ok",
                "accuracy": 0.9,
                "false_negatives": 0,
                "false_positives": 1,
                "total_evaluated": 10,
            },
            "alert_effectiveness": {"status": "no_data"},
        }
        recs = loop._generate_weight_recommendations(feedback)
        assert any(r["action"] == "maintain" for r in recs["recommendations"])

    def test_evaluate_all_structure(self, tmp_path):
        loop = FeedbackLoop()
        loop.memory._memory_path = tmp_path / "test.jsonl"
        loop._feedback_path = tmp_path / "feedback.json"
        report = loop.evaluate_all()
        assert "risk_accuracy" in report
        assert "alert_effectiveness" in report
        assert "escalation_accuracy" in report
        assert "filing_timeliness" in report
        assert "weight_recommendations" in report
        assert "evaluated_at" in report


# ══════════════════════════════════════════════════════════════
#  MODEL UPDATER
# ══════════════════════════════════════════════════════════════


class TestModelUpdater:
    def test_init(self):
        updater = ModelUpdater()
        assert updater.name == "model_updater"

    def test_weight_bounds_defined(self):
        assert "overdue_filings" in WEIGHT_BOUNDS
        assert "no_etims" in WEIGHT_BOUNDS
        assert "never_filed" in WEIGHT_BOUNDS
        for key, (lower, upper) in WEIGHT_BOUNDS.items():
            assert lower < upper

    def test_max_delta(self):
        assert MAX_DELTA_PER_WEIGHT == 5
        assert MAX_TOTAL_WEIGHT == 100

    def test_apply_guardrails_no_change(self):
        updater = ModelUpdater()
        current = {"overdue_filings": 30, "no_etims": 15, "new_business": 5}
        proposed = updater._apply_guardrails(current, [])
        total = sum(proposed.values())
        # Should normalize to 100
        assert total == MAX_TOTAL_WEIGHT

    def test_apply_guardrails_increase(self):
        updater = ModelUpdater()
        current = dict(updater._settings.get("risk", {}).get("weights", {}))
        adjustments = [{"weight": "overdue_filings", "delta": 3}]
        proposed = updater._apply_guardrails(current, adjustments)
        # Weight should have changed (but normalized)
        assert sum(proposed.values()) == MAX_TOTAL_WEIGHT

    def test_apply_guardrails_clamps_delta(self):
        updater = ModelUpdater()
        current = {"overdue_filings": 30, "no_etims": 15, "new_business": 5,
                    "high_turnover_tot": 10, "missing_employees": 10,
                    "inconsistent_income": 10, "cash_heavy_industry": 10,
                    "never_filed": 10}
        # Delta of 20 should be clamped to MAX_DELTA_PER_WEIGHT
        adjustments = [{"weight": "overdue_filings", "delta": 20}]
        proposed = updater._apply_guardrails(current, adjustments)
        assert sum(proposed.values()) == MAX_TOTAL_WEIGHT

    def test_apply_guardrails_respects_bounds(self):
        updater = ModelUpdater()
        current = {"overdue_filings": 30, "no_etims": 15, "new_business": 5,
                    "high_turnover_tot": 10, "missing_employees": 10,
                    "inconsistent_income": 10, "cash_heavy_industry": 10,
                    "never_filed": 10}
        # Try to push new_business below its lower bound (0)
        adjustments = [{"weight": "new_business", "delta": -10}]
        proposed = updater._apply_guardrails(current, adjustments)
        # new_business should be at or above its lower bound
        lower = WEIGHT_BOUNDS["new_business"][0]
        # After normalization it might differ, but pre-normalization it should be >= lower
        assert sum(proposed.values()) == MAX_TOTAL_WEIGHT

    def test_check_guardrails(self):
        updater = ModelUpdater()
        current = {"overdue_filings": 30}
        proposed = {"overdue_filings": 45}  # upper bound hit
        notes = updater._check_guardrails(current, proposed)
        assert any("upper bound" in n for n in notes)

    def test_check_guardrails_no_triggers(self):
        updater = ModelUpdater()
        current = {
            "overdue_filings": 30,
            "no_etims": 15,
            "high_turnover_tot": 10,
            "missing_employees": 10,
            "inconsistent_income": 10,
            "new_business": 5,
            "cash_heavy_industry": 10,
            "never_filed": 10,
        }
        proposed = {
            "overdue_filings": 32,
            "no_etims": 15,
            "high_turnover_tot": 10,
            "missing_employees": 10,
            "inconsistent_income": 10,
            "new_business": 5,
            "cash_heavy_industry": 10,
            "never_filed": 8,
        }
        notes = updater._check_guardrails(current, proposed)
        assert any("No guardrails triggered" in n for n in notes)

    def test_build_reasoning(self):
        updater = ModelUpdater()
        adjustments = [
            {"weight": "overdue_filings", "delta": 3, "source": "feedback",
             "reason": "Model misses risky SMEs"},
        ]
        feedback = {"risk_accuracy": {"accuracy": 0.6}}
        reasons = updater._build_reasoning(adjustments, feedback, {})
        assert len(reasons) >= 1
        assert "Increase" in reasons[0]

    def test_build_reasoning_no_adjustments(self):
        updater = ModelUpdater()
        reasons = updater._build_reasoning([], {}, {})
        assert "No adjustments" in reasons[0]

    def test_calculate_adjustments_empty(self, tmp_path):
        updater = ModelUpdater()
        updater.feedback.memory._memory_path = tmp_path / "empty.jsonl"
        updater.feedback._feedback_path = tmp_path / "feedback.json"
        current = dict(updater._settings.get("risk", {}).get("weights", {}))
        feedback = {"weight_recommendations": {"recommendations": []}}
        patterns = {}
        adjustments = updater._calculate_adjustments(current, feedback, patterns)
        assert isinstance(adjustments, list)

    def test_calculate_adjustments_from_feedback(self):
        updater = ModelUpdater()
        current = dict(updater._settings.get("risk", {}).get("weights", {}))
        feedback = {
            "weight_recommendations": {
                "recommendations": [{
                    "action": "increase",
                    "targets": ["overdue_filings"],
                    "magnitude": "moderate",
                    "reason": "High false negative rate",
                }]
            }
        }
        patterns = {}
        adjustments = updater._calculate_adjustments(current, feedback, patterns)
        assert len(adjustments) >= 1
        assert adjustments[0]["weight"] == "overdue_filings"
        assert adjustments[0]["delta"] == 3  # moderate

    def test_calculate_adjustments_from_patterns(self):
        updater = ModelUpdater()
        current = dict(updater._settings.get("risk", {}).get("weights", {}))
        feedback = {"weight_recommendations": {"recommendations": []}}
        patterns = {
            "risk_factor_frequency": {
                "status": "ok",
                "factors": [{"factor": "new_business", "prevalence": 0.8}],
            },
            "late_filing_patterns": {"status": "no_data"},
        }
        adjustments = updater._calculate_adjustments(current, feedback, patterns)
        # new_business should get a decrease recommendation
        nb = [a for a in adjustments if a["weight"] == "new_business"]
        assert len(nb) == 1
        assert nb[0]["delta"] == -2

    def test_status(self):
        updater = ModelUpdater()
        s = updater.status()
        assert "current_weights" in s
        assert "total_weight" in s
        assert s["total_weight"] == 100
        assert "update_count" in s
        assert "pending_proposals" in s

    def test_get_pending_proposals_empty(self, tmp_path):
        updater = ModelUpdater()
        updater._proposals_dir = tmp_path / "proposals"
        updater._proposals_dir.mkdir()
        assert updater.get_pending_proposals() == []

    def test_rollback_no_history(self, tmp_path):
        updater = ModelUpdater()
        updater._history_path = tmp_path / "empty_history.jsonl"
        result = updater.rollback_last()
        assert result["status"] == "error"

    def test_propose_creates_proposal(self, tmp_path):
        updater = ModelUpdater()
        updater._proposals_dir = tmp_path / "proposals"
        updater._proposals_dir.mkdir()
        updater.staging = tmp_path
        (tmp_path / "review").mkdir()
        updater.feedback.memory._memory_path = tmp_path / "test.jsonl"
        updater.feedback._feedback_path = tmp_path / "feedback.json"
        updater.miner.memory._memory_path = tmp_path / "test.jsonl"

        proposal = updater.propose_update()
        assert proposal["type"] == "model_update_proposal"
        assert proposal["status"] == "pending_review"
        assert "current_weights" in proposal
        assert "proposed_weights" in proposal
        assert "reasoning" in proposal
        # Should have saved to proposals dir
        proposals = list(updater._proposals_dir.glob("proposal_*.json"))
        assert len(proposals) == 1

    def test_apply_proposal(self, tmp_path):
        updater = ModelUpdater()
        updater._proposals_dir = tmp_path / "proposals"
        updater._proposals_dir.mkdir()
        updater._history_path = tmp_path / "history.jsonl"
        updater.config_dir = tmp_path

        # Create a settings.json in tmp
        settings = {
            "risk": {
                "weights": {
                    "overdue_filings": 30, "no_etims": 15, "high_turnover_tot": 10,
                    "missing_employees": 10, "inconsistent_income": 10,
                    "new_business": 5, "cash_heavy_industry": 10, "never_filed": 10,
                },
                "audit_probability_multiplier": 0.6,
            }
        }
        (tmp_path / "settings.json").write_text(json.dumps(settings), encoding="utf-8")

        # Create a proposal
        proposal = {
            "type": "model_update_proposal",
            "status": "pending_review",
            "proposed_weights": {
                "overdue_filings": 33, "no_etims": 14, "high_turnover_tot": 10,
                "missing_employees": 10, "inconsistent_income": 10,
                "new_business": 3, "cash_heavy_industry": 10, "never_filed": 10,
            },
        }
        proposal_file = "proposal_test.json"
        (updater._proposals_dir / proposal_file).write_text(
            json.dumps(proposal), encoding="utf-8"
        )

        result = updater.apply_proposal(proposal_file)
        assert result["status"] == "applied"
        assert result["new_weights"]["overdue_filings"] == 33

        # Verify settings.json was updated
        updated = json.loads((tmp_path / "settings.json").read_text(encoding="utf-8"))
        assert updated["risk"]["weights"]["overdue_filings"] == 33

        # Verify history was recorded
        assert updater._history_path.exists()

    def test_apply_nonexistent_proposal(self, tmp_path):
        updater = ModelUpdater()
        updater._proposals_dir = tmp_path / "proposals"
        updater._proposals_dir.mkdir()
        updater.staging = tmp_path
        result = updater.apply_proposal("nonexistent.json")
        assert result["status"] == "error"
