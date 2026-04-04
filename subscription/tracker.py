"""
SUBSCRIPTION TRACKER — manages SME subscription state and M-Pesa payments.
Persists to data/subscriptions.json.
"""
import json
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

EAT = timezone(timedelta(hours=3))
ROOT = Path(__file__).parent.parent
SUBS_FILE = ROOT / "data" / "subscriptions.json"
PAYMENTS_FILE = ROOT / "data" / "payments.jsonl"

# Subscription plans
PLANS = {
    "trial": {"name": "Free Trial", "duration_days": 7, "price_kes": 0},
    "monthly": {"name": "Monthly", "duration_days": 30, "price_kes": 500},
    "quarterly": {"name": "Quarterly", "duration_days": 90, "price_kes": 1200},
    "annual": {"name": "Annual", "duration_days": 365, "price_kes": 4000},
}

# M-Pesa payment details
MPESA_PAYBILL = "0114179880"  # Stephen's M-Pesa number (Buy Goods / Till)
MPESA_ACCOUNT_PREFIX = "KRADTC"


class SubscriptionTracker:
    """Thread-safe subscription state manager."""

    def __init__(self):
        self._lock = threading.Lock()
        self._subs: dict = self._load()

    # ── Public API ──────────────────────────────────────────────────

    def get(self, pin: str) -> dict | None:
        """Get subscription for a PIN."""
        with self._lock:
            return self._subs.get(pin)

    def is_active(self, pin: str) -> bool:
        """Check if a PIN has an active (non-expired) subscription."""
        sub = self.get(pin)
        if not sub:
            return False
        if sub["status"] == "active":
            expires = datetime.fromisoformat(sub["expires_at"])
            if datetime.now(EAT) < expires:
                return True
            # Auto-expire
            self._update_status(pin, "expired")
            return False
        return False

    def start_trial(self, pin: str, name: str = "") -> dict:
        """Start a free trial for a new SME."""
        plan = PLANS["trial"]
        now = datetime.now(EAT)
        sub = {
            "pin": pin,
            "name": name,
            "plan": "trial",
            "plan_name": plan["name"],
            "status": "active",
            "amount_paid_kes": 0,
            "started_at": now.isoformat(),
            "expires_at": (now + timedelta(days=plan["duration_days"])).isoformat(),
            "payments": [],
            "created_at": now.isoformat(),
        }
        with self._lock:
            self._subs[pin] = sub
            self._save()
        return sub

    def record_payment(
        self, pin: str, amount_kes: float, plan: str = "monthly",
        mpesa_ref: str = "", phone: str = "",
    ) -> dict:
        """Record an M-Pesa payment and activate/extend subscription.
        Idempotent: duplicate mpesa_ref for same PIN is silently ignored.
        """
        if plan not in PLANS:
            raise ValueError(f"Invalid plan: {plan}. Valid: {list(PLANS.keys())}")

        plan_info = PLANS[plan]
        now = datetime.now(EAT)

        payment = {
            "amount_kes": amount_kes,
            "mpesa_ref": mpesa_ref,
            "phone": phone,
            "plan": plan,
            "recorded_at": now.isoformat(),
        }

        with self._lock:
            sub = self._subs.get(pin)

            # Duplicate payment guard — Safaricom may retry webhooks
            if sub and mpesa_ref:
                if any(p.get("mpesa_ref") == mpesa_ref for p in sub.get("payments", [])):
                    return sub  # Already recorded — idempotent

            if not sub:
                sub = {
                    "pin": pin,
                    "name": "",
                    "plan": plan,
                    "plan_name": plan_info["name"],
                    "status": "active",
                    "amount_paid_kes": 0,
                    "started_at": now.isoformat(),
                    "expires_at": now.isoformat(),
                    "payments": [],
                    "created_at": now.isoformat(),
                }

            # Extend from current expiry or from now (whichever is later)
            current_expiry = datetime.fromisoformat(sub["expires_at"])
            base = max(now, current_expiry)
            new_expiry = base + timedelta(days=plan_info["duration_days"])

            sub["plan"] = plan
            sub["plan_name"] = plan_info["name"]
            sub["status"] = "active"
            sub["amount_paid_kes"] = sub.get("amount_paid_kes", 0) + amount_kes
            sub["expires_at"] = new_expiry.isoformat()
            sub["payments"].append(payment)

            self._subs[pin] = sub
            self._save()

        # Append to payments ledger
        self._log_payment(pin, payment)
        return sub

    def confirm_payment(self, pin: str, mpesa_ref: str, amount_kes: float,
                        plan: str = "monthly", phone: str = "") -> dict:
        """Admin confirms an M-Pesa payment (manual verification)."""
        return self.record_payment(pin, amount_kes, plan, mpesa_ref, phone)

    def deactivate(self, pin: str) -> dict | None:
        """Admin deactivates a subscription."""
        return self._update_status(pin, "cancelled")

    def list_all(self) -> list[dict]:
        """List all subscriptions."""
        with self._lock:
            subs = list(self._subs.values())
        # Update expired ones
        now = datetime.now(EAT)
        for s in subs:
            if s["status"] == "active":
                expires = datetime.fromisoformat(s["expires_at"])
                if now >= expires:
                    s["status"] = "expired"
                    self._update_status(s["pin"], "expired")
        return subs

    def list_active(self) -> list[dict]:
        """List only active subscriptions."""
        return [s for s in self.list_all() if s["status"] == "active"]

    def list_expired(self) -> list[dict]:
        """List expired subscriptions (renewal targets)."""
        return [s for s in self.list_all() if s["status"] == "expired"]

    def get_payment_instructions(self, pin: str, plan: str = "monthly") -> dict:
        """Generate M-Pesa payment instructions for an SME."""
        if plan not in PLANS:
            plan = "monthly"
        plan_info = PLANS[plan]
        account_ref = f"{MPESA_ACCOUNT_PREFIX}-{pin}"
        return {
            "mpesa_number": MPESA_PAYBILL,
            "account_reference": account_ref,
            "amount_kes": plan_info["price_kes"],
            "plan": plan,
            "plan_name": plan_info["name"],
            "duration_days": plan_info["duration_days"],
            "instructions_en": [
                "Open M-Pesa on your phone",
                "Select 'Send Money'",
                f"Enter number: {MPESA_PAYBILL}",
                f"Enter amount: KES {plan_info['price_kes']:,}",
                f"In the reference, type: {account_ref}",
                "Enter your M-Pesa PIN and confirm",
                "You'll receive an SMS confirmation",
                "Your subscription activates within minutes",
            ],
            "instructions_sw": [
                "Fungua M-Pesa kwenye simu yako",
                "Chagua 'Tuma Pesa'",
                f"Weka nambari: {MPESA_PAYBILL}",
                f"Weka kiasi: KES {plan_info['price_kes']:,}",
                f"Kwenye reference, andika: {account_ref}",
                "Weka PIN yako ya M-Pesa na uthibitishe",
                "Utapokea SMS ya uthibitisho",
                "Usajili wako utaanza ndani ya dakika chache",
            ],
            "plans": {k: {"name": v["name"], "price_kes": v["price_kes"],
                          "duration_days": v["duration_days"]}
                      for k, v in PLANS.items() if k != "trial"},
        }

    @staticmethod
    def get_plans() -> dict:
        """Return available plans (excluding trial)."""
        return {k: v for k, v in PLANS.items() if k != "trial"}

    # ── Internal ────────────────────────────────────────────────────

    def _update_status(self, pin: str, status: str) -> dict | None:
        with self._lock:
            sub = self._subs.get(pin)
            if not sub:
                return None
            sub["status"] = status
            self._save()
            return sub

    def _load(self) -> dict:
        if SUBS_FILE.exists():
            try:
                data = json.loads(SUBS_FILE.read_text(encoding="utf-8"))
                return {s["pin"]: s for s in data.get("subscriptions", [])}
            except (json.JSONDecodeError, KeyError):
                return {}
        return {}

    def _save(self):
        SUBS_FILE.parent.mkdir(parents=True, exist_ok=True)
        data = {"subscriptions": list(self._subs.values())}
        SUBS_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False),
                             encoding="utf-8")

    def _log_payment(self, pin: str, payment: dict):
        PAYMENTS_FILE.parent.mkdir(parents=True, exist_ok=True)
        entry = {"pin": pin, **payment}
        with open(PAYMENTS_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
