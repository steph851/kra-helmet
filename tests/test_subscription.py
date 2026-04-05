"""Tests for subscription tracker — plans, payments, gating."""
import json
import pytest
from pathlib import Path
from datetime import datetime, timedelta, timezone

from subscription.tracker import SubscriptionTracker, PLANS, EAT


@pytest.fixture
def tracker(tmp_path):
    """Create a tracker with temp storage."""
    import subscription.tracker as mod
    orig_subs = mod.SUBS_FILE
    orig_pay = mod.PAYMENTS_FILE
    mod.SUBS_FILE = tmp_path / "subscriptions.json"
    mod.PAYMENTS_FILE = tmp_path / "payments.jsonl"
    t = SubscriptionTracker()
    yield t
    mod.SUBS_FILE = orig_subs
    mod.PAYMENTS_FILE = orig_pay


class TestPlans:
    def test_plans_exist(self):
        assert "trial" in PLANS
        assert "monthly" in PLANS
        assert "quarterly" in PLANS
        assert "annual" in PLANS

    def test_trial_is_free(self):
        assert PLANS["trial"]["price_kes"] == 0

    def test_monthly_price(self):
        assert PLANS["monthly"]["price_kes"] == 500

    def test_get_plans_excludes_trial(self):
        plans = SubscriptionTracker.get_plans()
        assert "trial" not in plans
        assert "monthly" in plans


class TestTrialSubscription:
    def test_start_trial(self, tracker):
        sub = tracker.start_trial("A123456789B", "Test User")
        assert sub["pin"] == "A123456789B"
        assert sub["plan"] == "trial"
        assert sub["status"] == "active"
        assert sub["amount_paid_kes"] == 0

    def test_trial_is_active(self, tracker):
        tracker.start_trial("A123456789B")
        assert tracker.is_active("A123456789B") is True

    def test_trial_expires(self, tracker):
        sub = tracker.start_trial("A123456789B")
        # Manually set expiry to the past
        past = (datetime.now(EAT) - timedelta(days=1)).isoformat()
        tracker._json_subs["A123456789B"]["expires_at"] = past
        tracker._save()
        assert tracker.is_active("A123456789B") is False

    def test_no_subscription_is_inactive(self, tracker):
        assert tracker.is_active("X000000000Y") is False


class TestPayments:
    def test_record_payment(self, tracker):
        tracker.start_trial("A123456789B")
        sub = tracker.record_payment(
            "A123456789B", amount_kes=500, plan="monthly",
            mpesa_ref="SLK1234567", phone="0712345678",
        )
        assert sub["plan"] == "monthly"
        assert sub["status"] == "active"
        assert sub["amount_paid_kes"] == 500
        assert len(sub["payments"]) == 1
        assert sub["payments"][0]["mpesa_ref"] == "SLK1234567"

    def test_payment_extends_subscription(self, tracker):
        tracker.start_trial("A123456789B")
        before = datetime.fromisoformat(tracker.get("A123456789B")["expires_at"])
        tracker.record_payment("A123456789B", 500, "monthly")
        after = datetime.fromisoformat(tracker.get("A123456789B")["expires_at"])
        assert after > before

    def test_payment_without_existing_sub(self, tracker):
        sub = tracker.record_payment("A999999999Z", 500, "monthly", "REF123")
        assert sub["status"] == "active"
        assert sub["plan"] == "monthly"

    def test_invalid_plan_raises(self, tracker):
        with pytest.raises(ValueError):
            tracker.record_payment("A123456789B", 500, "nonexistent")

    def test_confirm_payment(self, tracker):
        tracker.start_trial("A123456789B")
        sub = tracker.confirm_payment("A123456789B", "SLK999", 1200, "quarterly")
        assert sub["plan"] == "quarterly"
        assert sub["amount_paid_kes"] == 1200


class TestListAndManagement:
    def test_list_all(self, tracker):
        tracker.start_trial("A123456789B", "Test 1")
        tracker.start_trial("B123456789C", "Test 2")
        all_subs = tracker.list_all()
        assert len(all_subs) == 2

    def test_list_active(self, tracker):
        tracker.start_trial("A123456789B")
        tracker.start_trial("B123456789C")
        # Expire one
        tracker._json_subs["B123456789C"]["expires_at"] = (
            datetime.now(EAT) - timedelta(days=1)
        ).isoformat()
        tracker._save()
        active = tracker.list_active()
        assert len(active) == 1

    def test_deactivate(self, tracker):
        tracker.start_trial("A123456789B")
        sub = tracker.deactivate("A123456789B")
        assert sub["status"] == "cancelled"
        assert tracker.is_active("A123456789B") is False

    def test_deactivate_nonexistent(self, tracker):
        result = tracker.deactivate("X000000000Y")
        assert result is None


class TestPaymentInstructions:
    def test_instructions_format(self, tracker):
        instr = tracker.get_payment_instructions("A123456789B", "monthly")
        assert instr["mpesa_number"] == "0114179880"
        assert instr["account_reference"] == "KRADTC-A123456789B"
        assert instr["amount_kes"] == 500
        assert len(instr["instructions_en"]) >= 6
        assert len(instr["instructions_sw"]) >= 6
        assert "monthly" in instr["plans"]

    def test_plans_in_instructions(self, tracker):
        instr = tracker.get_payment_instructions("A123456789B")
        assert "trial" not in instr["plans"]
        assert "monthly" in instr["plans"]
        assert "quarterly" in instr["plans"]
        assert "annual" in instr["plans"]
