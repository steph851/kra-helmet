"""
SUBSCRIPTION TRACKER — manages SME subscription state and M-Pesa payments.
Uses PostgreSQL (Neon) when DATABASE_URL is set, falls back to JSON files.
Phone numbers encrypted at rest.
"""
import json
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from subscription.crypto import encrypt_phone, decrypt_phone

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
MPESA_PAYBILL = "0114179880"
MPESA_ACCOUNT_PREFIX = "KRADTC"


def _use_db():
    """Check if we should use PostgreSQL."""
    try:
        from database.connection import db_available
        return db_available()
    except Exception:
        return False


class SubscriptionTracker:
    """Subscription state manager. DB-first, JSON fallback."""

    def __init__(self):
        self._lock = threading.Lock()
        self._json_subs: dict = {}
        if not _use_db():
            self._json_subs = self._load_json()

    # ── Public API ──────────────────────────────────────────────────

    def get(self, pin: str) -> dict | None:
        """Get subscription for a PIN. Phone numbers are decrypted on read."""
        if _use_db():
            return self._db_get(pin)
        with self._lock:
            sub = self._json_subs.get(pin)
            if not sub:
                return None
            result = dict(sub)
            for p in result.get("payments", []):
                if p.get("phone"):
                    p["phone"] = decrypt_phone(p["phone"])
            return result

    def is_active(self, pin: str) -> bool:
        """Check if a PIN has an active (non-expired) subscription."""
        sub = self.get(pin)
        if not sub:
            return False
        if sub["status"] == "active":
            expires = datetime.fromisoformat(sub["expires_at"]) if isinstance(sub["expires_at"], str) else sub["expires_at"]
            if not expires.tzinfo:
                expires = expires.replace(tzinfo=EAT)
            if datetime.now(EAT) < expires:
                return True
            self._update_status(pin, "expired")
            return False
        return False

    def start_trial(self, pin: str, name: str = "") -> dict:
        """Start a free trial for a new SME."""
        plan = PLANS["trial"]
        now = datetime.now(EAT)
        expires = now + timedelta(days=plan["duration_days"])

        if _use_db():
            return self._db_start_trial(pin, name, now, expires)

        sub = {
            "pin": pin,
            "name": name,
            "plan": "trial",
            "plan_name": plan["name"],
            "status": "active",
            "amount_paid_kes": 0,
            "started_at": now.isoformat(),
            "expires_at": expires.isoformat(),
            "payments": [],
            "created_at": now.isoformat(),
        }
        with self._lock:
            self._json_subs[pin] = sub
            self._save_json()
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

        if _use_db():
            return self._db_record_payment(pin, amount_kes, plan, mpesa_ref, phone)

        plan_info = PLANS[plan]
        now = datetime.now(EAT)

        payment = {
            "amount_kes": amount_kes,
            "mpesa_ref": mpesa_ref,
            "phone": encrypt_phone(phone),
            "plan": plan,
            "recorded_at": now.isoformat(),
        }

        with self._lock:
            sub = self._json_subs.get(pin)

            # Duplicate payment guard
            if sub and mpesa_ref:
                if any(p.get("mpesa_ref") == mpesa_ref for p in sub.get("payments", [])):
                    return sub

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

            current_expiry = datetime.fromisoformat(sub["expires_at"])
            base = max(now, current_expiry)
            new_expiry = base + timedelta(days=plan_info["duration_days"])

            sub["plan"] = plan
            sub["plan_name"] = plan_info["name"]
            sub["status"] = "active"
            sub["amount_paid_kes"] = sub.get("amount_paid_kes", 0) + amount_kes
            sub["expires_at"] = new_expiry.isoformat()
            sub["payments"].append(payment)

            self._json_subs[pin] = sub
            self._save_json()

        self._log_payment_json(pin, payment)
        return sub

    def confirm_payment(self, pin: str, mpesa_ref: str, amount_kes: float,
                        plan: str = "monthly", phone: str = "") -> dict:
        """Admin confirms an M-Pesa payment (manual verification)."""
        return self.record_payment(pin, amount_kes, plan, mpesa_ref, phone)

    def deactivate(self, pin: str) -> dict | None:
        """Admin deactivates a subscription."""
        return self._update_status(pin, "cancelled")

    def delete(self, pin: str) -> bool:
        """Delete a subscription entirely (for data deletion requests)."""
        if _use_db():
            return self._db_delete(pin)
        with self._lock:
            if pin in self._json_subs:
                del self._json_subs[pin]
                self._save_json()
                return True
            return False

    def list_all(self) -> list[dict]:
        """List all subscriptions."""
        if _use_db():
            return self._db_list_all()

        with self._lock:
            subs = list(self._json_subs.values())
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

    # ── Database Operations ─────────────────────────────────────────

    def _db_get(self, pin: str) -> dict | None:
        from database.connection import get_session
        from database.models import Subscription, Payment
        session = get_session()
        try:
            sub = session.query(Subscription).filter(Subscription.pin == pin).first()
            if not sub:
                return None
            payments = [
                {
                    "amount_kes": p.amount_kes,
                    "mpesa_ref": p.mpesa_ref,
                    "phone": decrypt_phone(p.phone) if p.phone else "",
                    "plan": p.plan,
                    "recorded_at": p.recorded_at.isoformat() if p.recorded_at else "",
                }
                for p in sub.payments
            ]
            return {
                "pin": sub.pin,
                "name": sub.name or "",
                "plan": sub.plan,
                "plan_name": sub.plan_name or "",
                "status": sub.status,
                "amount_paid_kes": sub.amount_paid_kes or 0,
                "started_at": sub.started_at.isoformat() if sub.started_at else "",
                "expires_at": sub.expires_at.isoformat() if sub.expires_at else "",
                "payments": payments,
                "created_at": sub.created_at.isoformat() if sub.created_at else "",
            }
        finally:
            session.close()

    def _db_start_trial(self, pin: str, name: str, now, expires) -> dict:
        from database.connection import get_session
        from database.models import Subscription
        session = get_session()
        try:
            existing = session.query(Subscription).filter(Subscription.pin == pin).first()
            if existing:
                # Return existing sub
                result = self._db_get(pin)
                return result

            sub = Subscription(
                pin=pin, name=name, plan="trial", plan_name="Free Trial",
                status="active", amount_paid_kes=0,
                started_at=now, expires_at=expires, created_at=now,
            )
            session.add(sub)
            session.commit()
            return {
                "pin": pin, "name": name, "plan": "trial", "plan_name": "Free Trial",
                "status": "active", "amount_paid_kes": 0,
                "started_at": now.isoformat(), "expires_at": expires.isoformat(),
                "payments": [], "created_at": now.isoformat(),
            }
        finally:
            session.close()

    def _db_record_payment(self, pin: str, amount_kes: float, plan: str,
                           mpesa_ref: str, phone: str) -> dict:
        from database.connection import get_session
        from database.models import Subscription, Payment
        plan_info = PLANS[plan]
        now = datetime.now(EAT)
        session = get_session()
        try:
            sub = session.query(Subscription).filter(Subscription.pin == pin).first()

            # Duplicate guard
            if sub and mpesa_ref:
                dup = session.query(Payment).filter(
                    Payment.pin == pin, Payment.mpesa_ref == mpesa_ref
                ).first()
                if dup:
                    result = self._db_get(pin)
                    return result

            if not sub:
                sub = Subscription(
                    pin=pin, name="", plan=plan, plan_name=plan_info["name"],
                    status="active", amount_paid_kes=0,
                    started_at=now, expires_at=now, created_at=now,
                )
                session.add(sub)
                session.flush()

            # Extend from current expiry or now
            current_expiry = sub.expires_at
            if not current_expiry.tzinfo:
                current_expiry = current_expiry.replace(tzinfo=EAT)
            base = max(now, current_expiry)
            new_expiry = base + timedelta(days=plan_info["duration_days"])

            sub.plan = plan
            sub.plan_name = plan_info["name"]
            sub.status = "active"
            sub.amount_paid_kes = (sub.amount_paid_kes or 0) + amount_kes
            sub.expires_at = new_expiry

            payment = Payment(
                pin=pin, subscription_id=sub.id,
                amount_kes=amount_kes, mpesa_ref=mpesa_ref,
                phone=encrypt_phone(phone), plan=plan, recorded_at=now,
            )
            session.add(payment)
            session.commit()

            return self._db_get(pin)
        finally:
            session.close()

    def _db_delete(self, pin: str) -> bool:
        from database.connection import get_session
        from database.models import Subscription
        session = get_session()
        try:
            sub = session.query(Subscription).filter(Subscription.pin == pin).first()
            if not sub:
                return False
            session.delete(sub)
            session.commit()
            return True
        finally:
            session.close()

    def _db_list_all(self) -> list[dict]:
        from database.connection import get_session
        from database.models import Subscription
        session = get_session()
        try:
            now = datetime.now(EAT)
            subs = session.query(Subscription).all()
            results = []
            for sub in subs:
                if sub.status == "active" and sub.expires_at:
                    exp = sub.expires_at
                    if not exp.tzinfo:
                        exp = exp.replace(tzinfo=EAT)
                    if now >= exp:
                        sub.status = "expired"
                        session.commit()
                results.append({
                    "pin": sub.pin,
                    "name": sub.name or "",
                    "plan": sub.plan,
                    "plan_name": sub.plan_name or "",
                    "status": sub.status,
                    "amount_paid_kes": sub.amount_paid_kes or 0,
                    "started_at": sub.started_at.isoformat() if sub.started_at else "",
                    "expires_at": sub.expires_at.isoformat() if sub.expires_at else "",
                    "payments": [],
                    "created_at": sub.created_at.isoformat() if sub.created_at else "",
                })
            return results
        finally:
            session.close()

    def _update_status(self, pin: str, status: str) -> dict | None:
        if _use_db():
            from database.connection import get_session
            from database.models import Subscription
            session = get_session()
            try:
                sub = session.query(Subscription).filter(Subscription.pin == pin).first()
                if not sub:
                    return None
                sub.status = status
                session.commit()
                return self._db_get(pin)
            finally:
                session.close()

        with self._lock:
            sub = self._json_subs.get(pin)
            if not sub:
                return None
            sub["status"] = status
            self._save_json()
            return sub

    # ── JSON Fallback ───────────────────────────────────────────────

    def _load_json(self) -> dict:
        if SUBS_FILE.exists():
            try:
                data = json.loads(SUBS_FILE.read_text(encoding="utf-8"))
                return {s["pin"]: s for s in data.get("subscriptions", [])}
            except (json.JSONDecodeError, KeyError):
                return {}
        return {}

    def _save_json(self):
        SUBS_FILE.parent.mkdir(parents=True, exist_ok=True)
        data = {"subscriptions": list(self._json_subs.values())}
        SUBS_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False),
                             encoding="utf-8")

    # Alias for tests
    _save = _save_json

    def _log_payment_json(self, pin: str, payment: dict):
        PAYMENTS_FILE.parent.mkdir(parents=True, exist_ok=True)
        entry = {"pin": pin, **payment}
        with open(PAYMENTS_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
