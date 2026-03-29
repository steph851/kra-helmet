"""Tests for communication agents — explainer, urgency, notifications."""
import pytest
from agents.communication.urgency_framer import UrgencyFramer
from agents.communication.explainer import Explainer
from agents.communication.notification_engine import NotificationEngine


# ── Urgency Framer ──────────────────────────────────────────────

class TestUrgencyFramer:
    def test_green_when_all_upcoming(self, sample_obligations):
        framer = UrgencyFramer()
        result = framer.frame(sample_obligations)
        assert result["urgency_level"] == "green"
        assert result["should_alert"] is False

    def test_red_when_overdue(self, overdue_obligations):
        framer = UrgencyFramer()
        result = framer.frame(overdue_obligations)
        assert result["urgency_level"] in ("red", "black")
        assert result["should_alert"] is True

    def test_has_emoji(self, sample_obligations):
        framer = UrgencyFramer()
        result = framer.frame(sample_obligations)
        assert "emoji" in result
        assert len(result["emoji"]) > 0

    def test_has_action(self, sample_obligations):
        framer = UrgencyFramer()
        result = framer.frame(sample_obligations)
        assert "action" in result

    def test_counts_overdue(self, overdue_obligations):
        framer = UrgencyFramer()
        result = framer.frame(overdue_obligations)
        assert result["overdue_count"] == 2


# ── Explainer ───────────────────────────────────────────────────

class TestExplainer:
    def test_generates_message(self, sample_profile, sample_obligations):
        validated = {
            "profile": sample_profile,
            "obligations": sample_obligations,
            "compliance": {
                "overall": "compliant",
                "next_action": "All on track.",
                "disclaimer": "Test disclaimer.",
            },
            "risk": {
                "risk_score": 15,
                "risk_level": "low",
                "factors": ["[+10] Cash-heavy industry"],
            },
            "urgency": {"urgency_level": "green", "emoji": "🟢"},
        }
        explainer = Explainer()
        message = explainer.explain(validated)
        assert isinstance(message, str)
        assert len(message) > 50
        assert sample_profile["name"] in message

    def test_includes_disclaimer(self, sample_profile, sample_obligations):
        validated = {
            "profile": sample_profile,
            "obligations": sample_obligations,
            "compliance": {
                "overall": "compliant",
                "next_action": "All on track.",
                "disclaimer": "IMPORTANT DISCLAIMER TEXT",
            },
            "risk": {"risk_score": 10, "risk_level": "low", "factors": []},
            "urgency": {"urgency_level": "green"},
        }
        explainer = Explainer()
        message = explainer.explain(validated)
        assert "DISCLAIMER" in message.upper()


# ── Notification Engine ─────────────────────────────────────────

class TestNotificationEngine:
    def test_no_alerts_when_green(self, sample_profile, sample_obligations):
        engine = NotificationEngine()
        urgency = {"urgency_level": "green", "should_alert": False, "action": "no_alert"}
        alerts = engine.generate_alerts(sample_profile, sample_obligations, urgency)
        assert len(alerts) == 0

    def test_format_sms_under_160_chars(self, sample_profile, sample_obligations):
        engine = NotificationEngine()
        urgency = {"urgency_level": "red", "emoji": "🔴", "prefix": "URGENT"}
        sms = engine.format_sms(sample_profile, sample_obligations, urgency)
        assert len(sms) <= 160

    def test_format_whatsapp_has_content(self, sample_profile, sample_obligations):
        engine = NotificationEngine()
        urgency = {"urgency_level": "yellow", "emoji": "🟡", "prefix": "ATTENTION"}
        msg = engine.format_whatsapp(sample_profile, sample_obligations, urgency)
        assert isinstance(msg, str)
        assert len(msg) > 10

    def test_format_email_structure(self, sample_profile, sample_obligations):
        engine = NotificationEngine()
        urgency = {"urgency_level": "orange", "emoji": "🟠", "prefix": "ACTION NEEDED"}
        email = engine.format_email(sample_profile, sample_obligations, urgency)
        assert "subject" in email
        assert "body_html" in email or "body_text" in email
