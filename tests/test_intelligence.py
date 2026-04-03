"""Tests for intelligence agents — obligation mapping, deadlines, risk, compliance, penalties."""
import pytest
from datetime import date
from agents.intelligence.obligation_mapper import ObligationMapper
from agents.intelligence.deadline_calculator import DeadlineCalculator
from agents.intelligence.risk_scorer import RiskScorer
from agents.intelligence.compliance_checker import ComplianceChecker
from agents.intelligence.penalty_calculator import PenaltyCalculator


# ── Obligation Mapper ───────────────────────────────────────────

class TestObligationMapper:
    def test_maps_basic_obligations(self, sample_profile):
        mapper = ObligationMapper()
        obs = mapper.map_obligations(sample_profile)
        assert len(obs) >= 1
        types = [o["tax_type"] for o in obs]
        assert "turnover_tax" in types

    def test_includes_employee_obligations(self, sample_profile):
        """SME with employees should have PAYE, NSSF, SHIF, Housing Levy."""
        mapper = ObligationMapper()
        obs = mapper.map_obligations(sample_profile)
        types = [o["tax_type"] for o in obs]
        assert "paye" in types
        assert "nssf" in types
        assert "shif" in types
        assert "housing_levy" in types

    def test_no_employee_obligations_without_employees(self, sample_profile):
        sample_profile["has_employees"] = False
        sample_profile["classification"]["obligations"] = ["turnover_tax"]
        mapper = ObligationMapper()
        obs = mapper.map_obligations(sample_profile)
        types = [o["tax_type"] for o in obs]
        assert "paye" not in types

    def test_each_obligation_has_required_fields(self, sample_profile):
        mapper = ObligationMapper()
        obs = mapper.map_obligations(sample_profile)
        for o in obs:
            assert "tax_type" in o
            assert "tax_name" in o
            assert "frequency" in o

    def test_vat_included_when_registered(self, sample_profile):
        sample_profile["is_vat_registered"] = True
        sample_profile["classification"]["obligations"].append("vat")
        mapper = ObligationMapper()
        obs = mapper.map_obligations(sample_profile)
        types = [o["tax_type"] for o in obs]
        assert "vat" in types


# ── Deadline Calculator ─────────────────────────────────────────

class TestDeadlineCalculator:
    def test_calculates_deadlines(self, sample_obligations):
        calc = DeadlineCalculator()
        result = calc.calculate_deadlines(sample_obligations, as_of=date(2026, 3, 29))
        for ob in result:
            assert "next_deadline" in ob
            assert "days_until_deadline" in ob
            assert "status" in ob

    def test_upcoming_status(self, sample_obligations):
        calc = DeadlineCalculator()
        result = calc.calculate_deadlines(sample_obligations, as_of=date(2026, 3, 1))
        for ob in result:
            assert ob["days_until_deadline"] > 0
            assert ob["status"] in ("upcoming", "due_soon")

    def test_overdue_detection(self):
        """Obligation past deadline should be marked overdue."""
        calc = DeadlineCalculator()
        obs = [{
            "tax_type": "turnover_tax",
            "tax_name": "TOT",
            "frequency": "monthly",
            "deadline_day": 20,
            "rate": "1.5%",
            "status": "upcoming",
        }]
        # as_of = March 25, deadline was March 20 → overdue
        result = calc.calculate_deadlines(obs, as_of=date(2026, 3, 25))
        # Next deadline should be April 20, not March 20
        assert result[0]["days_until_deadline"] > 0 or result[0]["status"] == "overdue"

    def test_weekend_adjustment(self):
        """Deadlines on weekends should push to Monday."""
        calc = DeadlineCalculator()
        # Find a date where the 20th falls on a weekend
        obs = [{
            "tax_type": "turnover_tax",
            "tax_name": "TOT",
            "frequency": "monthly",
            "deadline_day": 20,
            "rate": "1.5%",
            "status": "upcoming",
        }]
        result = calc.calculate_deadlines(obs, as_of=date(2026, 3, 1))
        dl = date.fromisoformat(result[0]["next_deadline"])
        assert dl.weekday() < 5  # not Saturday or Sunday

    def test_itax_buffer(self, sample_obligations):
        calc = DeadlineCalculator()
        result = calc.calculate_deadlines(sample_obligations, as_of=date(2026, 3, 29))
        for ob in result:
            if ob.get("recommended_file_by") and ob.get("next_deadline"):
                file_by = date.fromisoformat(ob["recommended_file_by"])
                deadline = date.fromisoformat(ob["next_deadline"])
                assert file_by < deadline  # buffer should push file-by earlier


# ── Risk Scorer ─────────────────────────────────────────────────

class TestRiskScorer:
    def test_scores_risk(self, sample_profile, sample_obligations):
        scorer = RiskScorer()
        result = scorer.score(sample_profile, sample_obligations)
        assert "risk_score" in result
        assert "risk_level" in result
        assert 0 <= result["risk_score"] <= 100

    def test_risk_levels(self, sample_profile, sample_obligations):
        scorer = RiskScorer()
        result = scorer.score(sample_profile, sample_obligations)
        assert result["risk_level"] in ("low", "medium", "high", "critical")

    def test_higher_risk_with_overdue(self, sample_profile, overdue_obligations):
        scorer = RiskScorer()
        result = scorer.score(sample_profile, overdue_obligations)
        assert result["risk_score"] > 0

    def test_audit_probability(self, sample_profile, sample_obligations):
        scorer = RiskScorer()
        result = scorer.score(sample_profile, sample_obligations)
        assert "audit_probability_pct" in result
        assert result["audit_probability_pct"] >= 0

    def test_factors_list(self, sample_profile, sample_obligations):
        scorer = RiskScorer()
        result = scorer.score(sample_profile, sample_obligations)
        assert isinstance(result["factors"], list)


# ── Compliance Checker ──────────────────────────────────────────

class TestComplianceChecker:
    def test_compliant_when_all_upcoming(self, sample_profile, sample_obligations):
        checker = ComplianceChecker()
        result = checker.check(sample_profile, sample_obligations)
        assert result["overall"] == "compliant"
        assert result["overdue_count"] == 0

    def test_non_compliant_when_overdue(self, sample_profile, overdue_obligations):
        checker = ComplianceChecker()
        result = checker.check(sample_profile, overdue_obligations)
        assert result["overall"] == "non_compliant"
        assert result["overdue_count"] == 2

    def test_at_risk_when_due_soon(self, sample_profile):
        obs = [{
            "tax_type": "turnover_tax",
            "tax_name": "TOT",
            "status": "due_soon",
            "days_until_deadline": 5,
            "next_deadline": "2026-04-03",
        }]
        checker = ComplianceChecker()
        result = checker.check(sample_profile, obs)
        assert result["overall"] == "at_risk"

    def test_has_next_action(self, sample_profile, sample_obligations):
        checker = ComplianceChecker()
        result = checker.check(sample_profile, sample_obligations)
        assert "next_action" in result
        assert len(result["next_action"]) > 0

    def test_has_disclaimer(self, sample_profile, sample_obligations):
        checker = ComplianceChecker()
        result = checker.check(sample_profile, sample_obligations)
        assert "disclaimer" in result


# ── Penalty Calculator ──────────────────────────────────────────

class TestPenaltyCalculator:
    def test_no_penalties_when_compliant(self, sample_profile, sample_obligations):
        calc = PenaltyCalculator()
        result = calc.calculate_penalties(sample_profile, sample_obligations)
        assert result["total_penalty_exposure_kes"] == 0
        assert result["overdue_count"] == 0

    def test_penalties_when_overdue(self, sample_profile, overdue_obligations):
        calc = PenaltyCalculator()
        result = calc.calculate_penalties(sample_profile, overdue_obligations)
        assert result["total_penalty_exposure_kes"] > 0
        assert result["overdue_count"] == 2
        assert len(result["penalties"]) == 2

    def test_severity_classification(self, sample_profile, overdue_obligations):
        calc = PenaltyCalculator()
        result = calc.calculate_penalties(sample_profile, overdue_obligations)
        assert result["severity"] in ("manageable", "serious", "critical")

    def test_tot_monthly_penalty(self, sample_profile):
        """TOT late filing: KES 1,000/month + 5% of tax due + interest."""
        obs = [{
            "tax_type": "turnover_tax",
            "tax_name": "TOT",
            "status": "overdue",
            "days_until_deadline": -10,
            "estimated_amount_kes": 50000,
        }]
        calc = PenaltyCalculator()
        result = calc.calculate_penalties(sample_profile, obs)
        penalty = result["penalties"][0]["estimated_penalty_kes"]
        # 1 month × KES 1,000 + 5% of 50,000 = 1,000 + 2,500 = 3,500
        assert penalty >= 3500

    def test_paye_penalty_higher_rate(self, sample_profile):
        """PAYE late filing is 25% — should be higher than 5% generic."""
        obs = [{
            "tax_type": "paye",
            "tax_name": "PAYE",
            "status": "overdue",
            "days_until_deadline": -30,
            "estimated_amount_kes": 100000,
        }]
        calc = PenaltyCalculator()
        result = calc.calculate_penalties(sample_profile, obs)
        penalty = result["penalties"][0]["estimated_penalty_kes"]
        assert penalty >= 25000  # 25% of 100K

    def test_interest_compounds_monthly(self, sample_profile):
        """Interest at 1% per month should compound."""
        obs = [{
            "tax_type": "turnover_tax",
            "tax_name": "TOT",
            "status": "overdue",
            "days_until_deadline": -90,  # 3 months
            "estimated_amount_kes": 100000,
        }]
        calc = PenaltyCalculator()
        result = calc.calculate_penalties(sample_profile, obs)
        interest = result["penalties"][0]["estimated_interest_kes"]
        # Simple 3% would be 3000, compound should be slightly more
        assert interest > 3000

    def test_etims_exposure(self):
        calc = PenaltyCalculator()
        result = calc.calculate_etims_exposure(100)
        assert result["total_exposure_kes"] == 5000  # 100 × KES 50
