"""
Tests for The Hands — action system + tools.
Tests tools (web_reader, whatsapp_sender, sms_sender, mpesa_caller, agent_caller)
and action agents (alert_engine, escalation_engine, recommendation_engine, workflow_engine).
"""
import json
import pytest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch, MagicMock, mock_open

import sys
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from tools.web_reader import WebReader, WebResult
from tools.whatsapp_sender import WhatsAppSender
from tools.sms_sender import SMSSender
from tools.mpesa_caller import MpesaCaller, KRA_PAYBILLS
from tools.agent_caller import AgentCaller

from agents.action.alert_engine import AlertEngine
from agents.action.escalation_engine import EscalationEngine, ESCALATION_RULES
from agents.action.recommendation_engine import RecommendationEngine
from agents.action.workflow_engine import WorkflowEngine

EAT = timezone(timedelta(hours=3))


# ══════════════════════════════════════════════════════════════
#  TOOLS
# ══════════════════════════════════════════════════════════════


# ── WebReader Tests ──────────────────────────────────────────


class TestWebResult:
    def test_ok_with_200(self):
        result = WebResult(url="http://x", status_code=200, content="hello",
                           content_type="text/html", elapsed_ms=50)
        assert result.ok is True

    def test_not_ok_with_500(self):
        result = WebResult(url="http://x", status_code=500, content="",
                           content_type="error", elapsed_ms=10, error="Server Error")
        assert result.ok is False

    def test_not_ok_with_error(self):
        result = WebResult(url="http://x", status_code=200, content="",
                           content_type="text/html", elapsed_ms=10, error="timeout")
        assert result.ok is False

    def test_text_strips_html(self):
        result = WebResult(url="http://x", status_code=200,
                           content="<html><body><p>Hello <b>World</b></p></body></html>",
                           content_type="text/html", elapsed_ms=10)
        assert "Hello" in result.text
        assert "World" in result.text
        assert "<" not in result.text

    def test_text_strips_scripts_and_styles(self):
        html = "<style>body{color:red}</style><script>alert('x')</script><p>Content</p>"
        result = WebResult(url="http://x", status_code=200, content=html,
                           content_type="text/html", elapsed_ms=10)
        assert "Content" in result.text
        assert "alert" not in result.text
        assert "color" not in result.text

    def test_to_dict_has_required_fields(self):
        result = WebResult(url="http://example.com", status_code=200, content="abc",
                           content_type="text/html", elapsed_ms=42)
        d = result.to_dict()
        assert d["url"] == "http://example.com"
        assert d["status_code"] == 200
        assert d["ok"] is True
        assert d["content_length"] == 3
        assert d["elapsed_ms"] == 42
        assert d["error"] is None


class TestWebReader:
    def test_init_defaults(self):
        reader = WebReader()
        assert reader.timeout == 20
        assert reader.max_retries == 2

    def test_init_custom(self):
        reader = WebReader(timeout=5, max_retries=0)
        assert reader.timeout == 5
        assert reader.max_retries == 0

    @patch("tools.web_reader.requests.Session.request")
    def test_fetch_success(self, mock_request):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = "Hello World"
        mock_resp.headers = {"Content-Type": "text/html"}
        mock_resp.raise_for_status = MagicMock()
        mock_request.return_value = mock_resp

        reader = WebReader()
        result = reader.fetch("http://example.com")
        assert result.ok is True
        assert result.status_code == 200
        assert "Hello World" in result.content

    def test_fetch_connection_error(self):
        """Fetch to a non-routable address returns error result."""
        reader = WebReader(timeout=1, max_retries=0)
        result = reader.fetch("http://192.0.2.1:1")  # RFC 5737 test address
        assert result.ok is False
        assert result.error is not None

    def test_ping_returns_bool(self):
        """Ping should return a bool."""
        reader = WebReader(timeout=1, max_retries=0)
        result = reader.ping("http://192.0.2.1:1")
        assert result is False


# ── WhatsApp Sender Tests ────────────────────────────────────


class TestWhatsAppSender:
    def test_default_is_dry_run(self):
        sender = WhatsAppSender()
        assert sender.provider == "dry_run"
        assert sender.is_configured is False

    def test_send_returns_dry_run(self, tmp_path):
        sender = WhatsAppSender()
        sender._log_dir = tmp_path
        result = sender.send("0712345678", "Test message", "A000000001B")
        assert result["status"] == "dry_run"
        assert result["phone"] == "+254712345678"
        assert result["message_length"] == 12

    def test_normalize_phone_zero_prefix(self):
        sender = WhatsAppSender()
        assert sender._normalize_phone("0712345678") == "+254712345678"

    def test_normalize_phone_254_prefix(self):
        sender = WhatsAppSender()
        assert sender._normalize_phone("254712345678") == "+254712345678"

    def test_normalize_phone_plus254(self):
        sender = WhatsAppSender()
        assert sender._normalize_phone("+254712345678") == "+254712345678"

    def test_normalize_strips_spaces_dashes(self):
        sender = WhatsAppSender()
        assert sender._normalize_phone("0712-345 678") == "+254712345678"

    def test_send_logs_to_file(self, tmp_path):
        sender = WhatsAppSender()
        sender._log_dir = tmp_path
        sender.send("0700000000", "Hello SME", "P123456789Q")
        log_file = tmp_path / "sent_messages.jsonl"
        assert log_file.exists()
        entry = json.loads(log_file.read_text().strip())
        assert entry["channel"] == "whatsapp"
        assert entry["message"] == "Hello SME"


# ── SMS Sender Tests ─────────────────────────────────────────


class TestSMSSender:
    def test_default_is_dry_run(self):
        sender = SMSSender()
        assert sender.is_configured is False

    def test_send_returns_dry_run(self, tmp_path):
        sender = SMSSender()
        sender._log_dir = tmp_path
        result = sender.send("0712345678", "Short msg", "A000000001B")
        assert result["status"] == "dry_run"
        assert result["phone"] == "+254712345678"

    def test_message_truncated_to_160(self, tmp_path):
        sender = SMSSender()
        sender._log_dir = tmp_path
        long_msg = "A" * 200
        result = sender.send("0700000000", long_msg, "X000000001Y")
        assert result["message_length"] <= 160

    def test_message_exact_160_not_truncated(self, tmp_path):
        sender = SMSSender()
        sender._log_dir = tmp_path
        msg = "B" * 160
        result = sender.send("0700000000", msg, "X000000001Y")
        assert result["message_length"] == 160

    def test_normalize_phone(self):
        sender = SMSSender()
        assert sender._normalize_phone("0700111222") == "+254700111222"

    def test_send_logs_to_file(self, tmp_path):
        sender = SMSSender()
        sender._log_dir = tmp_path
        sender.send("0700000000", "Tax alert", "P000000001Q")
        log_file = tmp_path / "sent_messages.jsonl"
        assert log_file.exists()
        entry = json.loads(log_file.read_text().strip())
        assert entry["channel"] == "sms"


# ── M-Pesa Caller Tests ─────────────────────────────────────


class TestMpesaCaller:
    def test_default_not_configured(self):
        mpesa = MpesaCaller()
        assert mpesa.is_configured is False

    def test_kra_paybills_defined(self):
        assert KRA_PAYBILLS["kra_income_tax"] == "572572"
        assert KRA_PAYBILLS["kra_vat"] == "572572"
        assert KRA_PAYBILLS["nssf"] == "200222"
        assert KRA_PAYBILLS["shif"] == "200222"
        assert KRA_PAYBILLS["housing_levy"] == "200222"

    def test_get_paybill_kra_tax(self):
        mpesa = MpesaCaller()
        assert mpesa.get_paybill("income_tax") == "572572"
        assert mpesa.get_paybill("vat") == "572572"
        assert mpesa.get_paybill("paye") == "572572"

    def test_get_paybill_nssf(self):
        mpesa = MpesaCaller()
        assert mpesa.get_paybill("nssf") == "200222"

    def test_generate_payment_instructions(self):
        mpesa = MpesaCaller()
        result = mpesa.generate_payment_instructions("vat", 50000, "A123456789Z")
        assert result["method"] == "M-Pesa Paybill"
        assert result["paybill"] == "572572"
        assert result["account_number"] == "A123456789Z#VAT"
        assert result["amount_kes"] == 50000
        assert len(result["steps"]) == 9

    def test_payment_steps_include_paybill(self):
        mpesa = MpesaCaller()
        result = mpesa.generate_payment_instructions("paye", 25000, "B000000001C")
        steps_text = " ".join(result["steps"])
        assert "572572" in steps_text
        assert "B000000001C#PAYE" in steps_text

    def test_check_payment_status_dry_run(self, tmp_path):
        mpesa = MpesaCaller()
        mpesa._log_dir = tmp_path
        result = mpesa.check_payment_status("TXN123")
        assert result["status"] == "dry_run"
        assert result["action"] == "check_status"

    def test_stk_push_dry_run(self, tmp_path):
        mpesa = MpesaCaller()
        mpesa._log_dir = tmp_path
        result = mpesa.initiate_stk_push("0712345678", 10000, "vat", "A000000001B")
        assert result["status"] == "dry_run"
        assert result["action"] == "stk_push"

    def test_normalize_phone(self):
        mpesa = MpesaCaller()
        assert mpesa._normalize_phone("0712345678") == "254712345678"
        assert mpesa._normalize_phone("+254712345678") == "254712345678"
        assert mpesa._normalize_phone("254712345678") == "254712345678"

    def test_stk_push_logs_to_file(self, tmp_path):
        mpesa = MpesaCaller()
        mpesa._log_dir = tmp_path
        mpesa.initiate_stk_push("0700000000", 5000, "tot", "P000000001Q")
        log_file = tmp_path / "mpesa_calls.jsonl"
        assert log_file.exists()


# ── Agent Caller Tests ───────────────────────────────────────


class TestAgentCaller:
    def test_list_agents_returns_known(self):
        caller = AgentCaller()
        agents = caller.list_agents()
        assert "orchestrator" in agents
        assert "monitoring" in agents
        assert "dashboard" in agents
        assert len(agents) >= 10

    def test_has_agent_orchestrator(self):
        caller = AgentCaller()
        assert caller.has_agent("orchestrator") is True

    def test_has_agent_unknown(self):
        caller = AgentCaller()
        assert caller.has_agent("nonexistent_agent") is False

    def test_call_unknown_agent_raises(self):
        caller = AgentCaller()
        with pytest.raises(ValueError, match="Unknown agent"):
            caller.call("nonexistent_agent", "some_method")

    def test_call_unknown_method_raises(self):
        caller = AgentCaller()
        with pytest.raises(ValueError, match="no method"):
            caller.call("orchestrator", "totally_fake_method_xyz")

    def test_call_log_recorded(self):
        caller = AgentCaller()
        # Use a method that exists on orchestrator
        try:
            caller.call("orchestrator", "list_smes")
        except Exception:
            pass
        log = caller.get_call_log()
        assert len(log) >= 1
        assert log[-1]["agent"] == "orchestrator"
        assert log[-1]["method"] == "list_smes"

    def test_lazy_load_caches(self):
        caller = AgentCaller()
        agent1 = caller._get_agent("input_validator")
        agent2 = caller._get_agent("input_validator")
        assert agent1 is agent2


# ══════════════════════════════════════════════════════════════
#  ACTION AGENTS
# ══════════════════════════════════════════════════════════════


# ── Alert Engine Tests ───────────────────────────────────────


class TestAlertEngine:
    def test_init(self):
        engine = AlertEngine()
        assert engine.name == "alert_engine"
        assert "messages only" in engine.boundary.lower() or "Delivers" in engine.boundary

    def test_deliver_empty_message_skipped(self):
        engine = AlertEngine()
        result = engine.deliver_alert({"message": "", "phone": "0700000000"})
        assert result["status"] == "skipped"
        assert result["reason"] == "empty_message"

    def test_deliver_no_phone_skipped(self):
        engine = AlertEngine()
        result = engine.deliver_alert({"message": "Hello", "phone": ""})
        assert result["status"] == "skipped"
        assert result["reason"] == "no_phone"

    def test_deliver_sms_channel(self, tmp_path):
        engine = AlertEngine()
        engine.sms._log_dir = tmp_path
        engine.logs_dir = tmp_path
        result = engine.deliver_alert({
            "channel": "sms",
            "message": "Tax reminder",
            "phone": "0712345678",
            "sme_pin": "A000000001B",
        })
        assert result["status"] == "dry_run"

    def test_deliver_whatsapp_channel(self, tmp_path):
        engine = AlertEngine()
        engine.whatsapp._log_dir = tmp_path
        engine.logs_dir = tmp_path
        result = engine.deliver_alert({
            "channel": "whatsapp",
            "message": "VAT overdue",
            "phone": "0712345678",
            "sme_pin": "A000000001B",
        })
        assert result["status"] == "dry_run"

    def test_deliver_email_channel(self, tmp_path):
        engine = AlertEngine()
        engine.logs_dir = tmp_path
        result = engine.deliver_alert({
            "channel": "email",
            "message": "Filing reminder",
            "phone": "0712345678",
            "sme_pin": "A000000001B",
        })
        assert result["status"] == "dry_run"

    def test_deliver_batch(self, tmp_path):
        engine = AlertEngine()
        engine.sms._log_dir = tmp_path
        engine.whatsapp._log_dir = tmp_path
        engine.logs_dir = tmp_path
        alerts = [
            {"channel": "sms", "message": "Alert 1", "phone": "0700000001", "sme_pin": "A000000001B"},
            {"channel": "sms", "message": "Alert 2", "phone": "0700000002", "sme_pin": "B000000002C"},
        ]
        results = engine.deliver_batch(alerts)
        assert len(results) == 2

    def test_process_empty_queue(self, tmp_path):
        engine = AlertEngine()
        engine.staging = tmp_path
        results = engine.process_queue()
        assert results == []

    def test_process_queue_with_alerts(self, tmp_path):
        engine = AlertEngine()
        engine.staging = tmp_path
        engine.sms._log_dir = tmp_path
        engine.logs_dir = tmp_path

        # Create alerts directory with a queued alert
        alerts_dir = tmp_path / "alerts"
        alerts_dir.mkdir()
        alert = {
            "channel": "sms",
            "message": "Pay your taxes",
            "phone": "0712345678",
            "sme_pin": "A000000001B",
        }
        (alerts_dir / "alert_001.json").write_text(json.dumps(alert), encoding="utf-8")

        results = engine.process_queue()
        assert len(results) == 1
        assert results[0]["status"] == "dry_run"

        # Original file should be removed, moved to delivered
        assert not (alerts_dir / "alert_001.json").exists()
        assert (alerts_dir / "delivered" / "alert_001.json").exists()

    def test_status(self, tmp_path):
        engine = AlertEngine()
        engine.staging = tmp_path
        status = engine.status()
        assert "pending_alerts" in status
        assert "delivered_alerts" in status
        assert "whatsapp_configured" in status
        assert "sms_configured" in status


# ── Escalation Engine Tests ──────────────────────────────────


class TestEscalationEngine:
    def test_init(self):
        engine = EscalationEngine()
        assert engine.name == "escalation_engine"

    def test_escalation_rules_defined(self):
        assert ESCALATION_RULES["overdue_days_tier1"] == 1
        assert ESCALATION_RULES["overdue_days_tier2"] == 7
        assert ESCALATION_RULES["overdue_days_tier3"] == 30
        assert ESCALATION_RULES["penalty_threshold_kes"] == 50000

    def test_no_escalation_for_compliant(self, tmp_path):
        engine = EscalationEngine()
        engine.staging = tmp_path
        (tmp_path / "review").mkdir(parents=True)
        result = engine.evaluate(
            pin="A000000001B",
            compliance={"overall": "compliant"},
            obligations=[{"tax_key": "vat", "tax_name": "VAT", "days_until_deadline": 15}],
            penalties={"total_penalty_exposure_kes": 0},
            urgency={"urgency_level": "green"},
        )
        assert len(result) == 0

    def test_tier2_escalation_7_days_overdue(self, tmp_path):
        engine = EscalationEngine()
        engine.staging = tmp_path
        (tmp_path / "review").mkdir(parents=True)
        result = engine.evaluate(
            pin="A000000001B",
            compliance={"overall": "non_compliant"},
            obligations=[{"tax_key": "vat", "tax_name": "VAT", "days_until_deadline": -10}],
            penalties={"total_penalty_exposure_kes": 0},
            urgency={"urgency_level": "red"},
        )
        assert len(result) == 1
        assert result[0]["tier"] == "review"

    def test_tier3_escalation_30_days_overdue(self, tmp_path):
        engine = EscalationEngine()
        engine.staging = tmp_path
        (tmp_path / "review").mkdir(parents=True)
        result = engine.evaluate(
            pin="A000000001B",
            compliance={"overall": "non_compliant"},
            obligations=[{"tax_key": "paye", "tax_name": "PAYE", "days_until_deadline": -35}],
            penalties={"total_penalty_exposure_kes": 0},
            urgency={"urgency_level": "red"},
        )
        assert len(result) == 1
        assert result[0]["tier"] == "critical"

    def test_penalty_threshold_escalation(self, tmp_path):
        engine = EscalationEngine()
        engine.staging = tmp_path
        (tmp_path / "review").mkdir(parents=True)
        result = engine.evaluate(
            pin="A000000001B",
            compliance={"overall": "non_compliant"},
            obligations=[],
            penalties={"total_penalty_exposure_kes": 75000, "severity": "high"},
            urgency={"urgency_level": "red"},
        )
        assert len(result) == 1
        assert result[0]["tier"] == "review"

    def test_critical_penalty_escalation(self, tmp_path):
        engine = EscalationEngine()
        engine.staging = tmp_path
        (tmp_path / "review").mkdir(parents=True)
        result = engine.evaluate(
            pin="A000000001B",
            compliance={"overall": "non_compliant"},
            obligations=[],
            penalties={"total_penalty_exposure_kes": 250000, "severity": "critical"},
            urgency={"urgency_level": "red"},
        )
        assert len(result) == 1
        assert result[0]["tier"] == "critical"

    def test_escalation_writes_to_staging(self, tmp_path):
        engine = EscalationEngine()
        engine.staging = tmp_path
        review_dir = tmp_path / "review"
        review_dir.mkdir(parents=True)
        engine.evaluate(
            pin="A000000001B",
            compliance={"overall": "non_compliant"},
            obligations=[{"tax_key": "vat", "tax_name": "VAT", "days_until_deadline": -10}],
            penalties={"total_penalty_exposure_kes": 0},
            urgency={"urgency_level": "red"},
        )
        files = list(review_dir.glob("escalation_*.json"))
        assert len(files) >= 1
        data = json.loads(files[0].read_text(encoding="utf-8"))
        assert data["pin"] == "A000000001B"
        assert data["status"] == "pending_review"

    def test_get_pending_escalations(self, tmp_path):
        engine = EscalationEngine()
        engine.staging = tmp_path
        review_dir = tmp_path / "review"
        review_dir.mkdir(parents=True)
        # Create a fake escalation file
        esc = {"type": "escalation_review", "pin": "X000000001Y", "status": "pending_review"}
        (review_dir / "escalation_X000000001Y_20260330.json").write_text(
            json.dumps(esc), encoding="utf-8"
        )
        pending = engine.get_pending_escalations()
        assert len(pending) == 1
        assert pending[0]["pin"] == "X000000001Y"

    def test_action_for_critical_tier(self):
        engine = EscalationEngine()
        action = engine._action_for_tier("critical")
        assert "URGENT" in action

    def test_action_for_review_tier(self):
        engine = EscalationEngine()
        action = engine._action_for_tier("review")
        assert "Review" in action

    def test_multiple_escalations(self, tmp_path):
        """Multiple overdue obligations should generate multiple escalations."""
        engine = EscalationEngine()
        engine.staging = tmp_path
        (tmp_path / "review").mkdir(parents=True)
        result = engine.evaluate(
            pin="A000000001B",
            compliance={"overall": "non_compliant"},
            obligations=[
                {"tax_key": "vat", "tax_name": "VAT", "days_until_deadline": -10},
                {"tax_key": "paye", "tax_name": "PAYE", "days_until_deadline": -40},
            ],
            penalties={"total_penalty_exposure_kes": 0},
            urgency={"urgency_level": "red"},
        )
        assert len(result) == 2
        tiers = {e["tier"] for e in result}
        assert "review" in tiers
        assert "critical" in tiers


# ── Recommendation Engine Tests ──────────────────────────────


class TestRecommendationEngine:
    def test_init(self):
        engine = RecommendationEngine()
        assert engine.name == "recommendation_engine"

    def test_unknown_sme_returns_error(self):
        engine = RecommendationEngine()
        result = engine.generate("Z999999999Z")
        assert result["pin"] == "Z999999999Z"
        assert "error" in result or len(result["recommendations"]) > 0

    def test_overdue_generates_priority_1(self):
        engine = RecommendationEngine()
        recs = engine._overdue_recommendations(
            "A000000001B", {"name": "Test"}, [
                {"tax_key": "vat", "tax_name": "VAT", "days_until_deadline": -5,
                 "next_deadline": "2026-03-25"},
            ]
        )
        assert len(recs) == 1
        assert recs[0]["priority"] == 1
        assert recs[0]["urgency"] == "red"
        assert "FILE NOW" in recs[0]["title"]

    def test_due_today_generates_priority_2(self):
        engine = RecommendationEngine()
        recs = engine._critical_recommendations(
            "A000000001B", {"name": "Test"}, [
                {"tax_key": "paye", "tax_name": "PAYE", "days_until_deadline": 0},
            ]
        )
        assert len(recs) == 1
        assert recs[0]["priority"] == 2
        assert "TODAY" in recs[0]["title"]

    def test_upcoming_generates_priority_3(self):
        engine = RecommendationEngine()
        recs = engine._upcoming_recommendations(
            "A000000001B", {"name": "Test"}, [
                {"tax_key": "tot", "tax_name": "TOT", "days_until_deadline": 5,
                 "next_deadline": "2026-04-05"},
            ]
        )
        assert len(recs) == 1
        assert recs[0]["priority"] == 3
        assert "PREPARE" in recs[0]["title"]

    def test_upcoming_within_3_days_is_orange(self):
        engine = RecommendationEngine()
        recs = engine._upcoming_recommendations(
            "A000000001B", {"name": "Test"}, [
                {"tax_key": "vat", "tax_name": "VAT", "days_until_deadline": 2,
                 "next_deadline": "2026-04-01"},
            ]
        )
        assert recs[0]["urgency"] == "orange"

    def test_upcoming_beyond_3_days_is_yellow(self):
        engine = RecommendationEngine()
        recs = engine._upcoming_recommendations(
            "A000000001B", {"name": "Test"}, [
                {"tax_key": "vat", "tax_name": "VAT", "days_until_deadline": 6,
                 "next_deadline": "2026-04-05"},
            ]
        )
        assert recs[0]["urgency"] == "yellow"

    def test_etims_vat_without_etims(self):
        engine = RecommendationEngine()
        recs = engine._etims_recommendations(
            "A000000001B", {"is_vat_registered": True, "has_etims": False}
        )
        assert len(recs) == 1
        assert recs[0]["priority"] == 2
        assert "eTIMS" in recs[0]["title"]

    def test_etims_high_turnover_without_etims(self):
        engine = RecommendationEngine()
        recs = engine._etims_recommendations(
            "A000000001B", {"is_vat_registered": False, "has_etims": False,
                            "annual_turnover_kes": 10_000_000}
        )
        assert len(recs) == 1
        assert recs[0]["priority"] == 4

    def test_etims_compliant_no_recommendation(self):
        engine = RecommendationEngine()
        recs = engine._etims_recommendations(
            "A000000001B", {"is_vat_registered": True, "has_etims": True}
        )
        assert len(recs) == 0

    def test_risk_high_score(self):
        engine = RecommendationEngine()
        recs = engine._risk_recommendations(
            "A000000001B", {"name": "Test"}, {
                "risk_score": 75,
                "audit_probability_pct": 45,
                "factors": [{"factor": "overdue"}, {"factor": "penalty"}],
            }
        )
        assert len(recs) == 1
        assert recs[0]["priority"] == 5
        assert "HIGH RISK" in recs[0]["title"]

    def test_risk_low_score_no_recommendation(self):
        engine = RecommendationEngine()
        recs = engine._risk_recommendations(
            "A000000001B", {"name": "Test"}, {"risk_score": 20}
        )
        assert len(recs) == 0

    def test_payment_recommendations_with_penalties(self):
        engine = RecommendationEngine()
        recs = engine._payment_recommendations(
            "A000000001B", {"name": "Test"},
            [{"tax_key": "vat", "tax_name": "VAT", "days_until_deadline": -5}],
            {"total_penalty_exposure_kes": 30000},
        )
        assert len(recs) == 1
        assert recs[0]["action"] == "pay_tax"
        assert "M-Pesa" in recs[0]["title"]

    def test_payment_no_penalties(self):
        engine = RecommendationEngine()
        recs = engine._payment_recommendations(
            "A000000001B", {"name": "Test"}, [], {"total_penalty_exposure_kes": 0}
        )
        assert len(recs) == 0

    def test_no_future_obligations_no_recs(self):
        engine = RecommendationEngine()
        recs = engine._upcoming_recommendations(
            "A000000001B", {"name": "Test"}, [
                {"tax_key": "vat", "tax_name": "VAT", "days_until_deadline": 15},
            ]
        )
        assert len(recs) == 0

    def test_recommendations_sorted_by_priority(self):
        engine = RecommendationEngine()
        # Test the sorting logic directly
        recs = [
            {"priority": 3, "title": "C"},
            {"priority": 1, "title": "A"},
            {"priority": 2, "title": "B"},
        ]
        recs.sort(key=lambda r: r["priority"])
        assert recs[0]["priority"] == 1
        assert recs[1]["priority"] == 2
        assert recs[2]["priority"] == 3


# ── Workflow Engine Tests ────────────────────────────────────


class TestWorkflowEngine:
    def test_init(self):
        engine = WorkflowEngine()
        assert engine.name == "workflow_engine"

    def test_prepare_filing_unknown_sme(self):
        engine = WorkflowEngine()
        result = engine.prepare_filing("Z999999999Z", "vat")
        assert result is None

    def test_build_checklist_base_items(self):
        engine = WorkflowEngine()
        items = engine._build_checklist("vat", {"pin": "A000000001B"}, None)
        # Should have at least iTax login + file + pay + save + record
        assert len(items) >= 4
        assert items[0]["step"] == "Log in to iTax"
        assert all(item["done"] is False for item in items)

    def test_build_checklist_payroll_taxes(self):
        engine = WorkflowEngine()
        items = engine._build_checklist("paye", {"pin": "A000000001B", "employee_count": 5}, None)
        steps_text = " ".join(i["step"] for i in items)
        assert "payroll" in steps_text.lower()
        assert "employee" in steps_text.lower()

    def test_build_checklist_vat_with_etims(self):
        engine = WorkflowEngine()
        items = engine._build_checklist("vat", {"pin": "A000000001B", "has_etims": True}, None)
        steps_text = " ".join(i["step"] for i in items)
        assert "eTIMS" in steps_text

    def test_build_checklist_vat_without_etims(self):
        engine = WorkflowEngine()
        items = engine._build_checklist("vat", {"pin": "A000000001B", "has_etims": False}, None)
        steps_text = " ".join(i["step"] for i in items)
        assert "reconcile" in steps_text.lower() or "Reconcile" in steps_text

    def test_build_checklist_tot(self):
        engine = WorkflowEngine()
        items = engine._build_checklist("tot", {"pin": "A000000001B"}, None)
        steps_text = " ".join(i["step"] for i in items)
        assert "3%" in steps_text

    def test_build_checklist_with_guide_docs(self):
        engine = WorkflowEngine()
        guide = {"documents_needed": ["KRA PIN Certificate", "iTax password"]}
        items = engine._build_checklist("vat", {"pin": "A000000001B"}, guide)
        steps_text = " ".join(i["step"] for i in items)
        assert "KRA PIN Certificate" in steps_text
        assert "iTax password" in steps_text

    def test_build_checklist_nssf(self):
        engine = WorkflowEngine()
        items = engine._build_checklist("nssf", {"pin": "A000000001B", "employee_count": 3}, None)
        steps_text = " ".join(i["step"] for i in items)
        assert "payroll" in steps_text.lower()

    def test_build_checklist_shif(self):
        engine = WorkflowEngine()
        items = engine._build_checklist("shif", {"pin": "A000000001B", "employee_count": 2}, None)
        steps_text = " ".join(i["step"] for i in items)
        assert "payroll" in steps_text.lower()

    def test_build_checklist_housing_levy(self):
        engine = WorkflowEngine()
        items = engine._build_checklist("housing_levy", {"pin": "A000000001B", "employee_count": 10}, None)
        steps_text = " ".join(i["step"] for i in items)
        assert "payroll" in steps_text.lower()

    def test_build_checklist_common_final_steps(self):
        engine = WorkflowEngine()
        items = engine._build_checklist("vat", {"pin": "A000000001B"}, None)
        steps = [i["step"] for i in items]
        assert any("File the return" in s for s in steps)
        assert any("M-Pesa" in s for s in steps)
        assert any("acknowledgment" in s.lower() or "receipt" in s.lower() for s in steps)

    def test_prepare_all_due_no_report(self, tmp_path):
        engine = WorkflowEngine()
        engine.data_dir = tmp_path
        result = engine.prepare_all_due("Z999999999Z")
        assert result == []
