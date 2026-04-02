"""
M-PESA CALLER — integrates with Safaricom Daraja API for tax payment tracking.
BOUNDARY: Checks payment status and initiates STK push for tax payments.
Currently in DRY RUN mode — logs calls instead of hitting the API.
"""
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .phone_utils import normalize_phone_mpesa

EAT = timezone(timedelta(hours=3))
ROOT = Path(__file__).parent.parent

# KRA's M-Pesa paybill numbers
KRA_PAYBILLS = {
    "kra_income_tax": "572572",
    "kra_vat": "572572",
    "kra_paye": "572572",
    "kra_other": "572572",
    "nssf": "200222",
    "shif": "200222",
    "housing_levy": "200222",
}


class MpesaCaller:
    """M-Pesa API integration. Dry-run by default until Daraja credentials are configured."""

    def __init__(self):
        self.consumer_key = os.getenv("HELMET_MPESA_KEY", "")
        self.consumer_secret = os.getenv("HELMET_MPESA_SECRET", "")
        self.environment = os.getenv("HELMET_MPESA_ENV", "sandbox")  # sandbox | production
        self._log_dir = ROOT / "logs"
        self._log_dir.mkdir(exist_ok=True)

    def check_payment_status(self, transaction_id: str) -> dict:
        """Check status of an M-Pesa transaction."""
        if not self.is_configured:
            return self._dry_run("check_status", {"transaction_id": transaction_id})

        # Future: Daraja Transaction Status API
        return self._dry_run("check_status", {"transaction_id": transaction_id})

    def initiate_stk_push(
        self,
        phone: str,
        amount: float,
        tax_type: str,
        pin: str,
        account_reference: str = "",
    ) -> dict:
        """Initiate an STK push for tax payment."""
        phone = self._normalize_phone(phone)
        paybill = KRA_PAYBILLS.get(f"kra_{tax_type}", KRA_PAYBILLS["kra_other"])
        account_ref = account_reference or pin

        payload = {
            "phone": phone,
            "amount": amount,
            "paybill": paybill,
            "account_reference": account_ref,
            "tax_type": tax_type,
            "pin": pin,
        }

        if not self.is_configured:
            return self._dry_run("stk_push", payload)

        # Future: Daraja STK Push API
        return self._dry_run("stk_push", payload)

    def get_paybill(self, tax_type: str) -> str:
        """Get the correct paybill number for a tax type."""
        return KRA_PAYBILLS.get(f"kra_{tax_type}", KRA_PAYBILLS.get(tax_type, KRA_PAYBILLS["kra_other"]))

    def generate_payment_instructions(self, tax_type: str, amount: float, pin: str) -> dict:
        """Generate M-Pesa payment instructions for an SME."""
        paybill = self.get_paybill(tax_type)

        # Map tax type to account format
        account_formats = {
            "income_tax_resident": f"{pin}#IT",
            "income_tax_corporate": f"{pin}#IT",
            "vat": f"{pin}#VAT",
            "paye": f"{pin}#PAYE",
            "tot": f"{pin}#TOT",
            "withholding_tax": f"{pin}#WHT",
            "mri": f"{pin}#MRI",
            "excise_duty": f"{pin}#ED",
        }
        account_number = account_formats.get(tax_type, f"{pin}#{tax_type.upper()}")

        return {
            "method": "M-Pesa Paybill",
            "paybill": paybill,
            "account_number": account_number,
            "amount_kes": amount,
            "tax_type": tax_type,
            "steps": [
                "Go to M-Pesa menu on your phone",
                "Select 'Lipa na M-Pesa'",
                "Select 'Pay Bill'",
                f"Enter Business Number: {paybill}",
                f"Enter Account Number: {account_number}",
                f"Enter Amount: KES {amount:,.0f}",
                "Enter your M-Pesa PIN",
                "Confirm the payment",
                "Save the confirmation message as proof of payment",
            ],
        }

    def _dry_run(self, action: str, payload: dict) -> dict:
        result = {
            "status": "dry_run",
            "action": action,
            "environment": self.environment,
            "payload": payload,
            "timestamp": datetime.now(EAT).isoformat(),
            "note": "M-Pesa API not configured — configure HELMET_MPESA_KEY and HELMET_MPESA_SECRET",
        }

        log_entry = {"channel": "mpesa", "action": action, "payload": payload, "result": result}
        log_path = self._log_dir / "mpesa_calls.jsonl"
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")

        return result

    def _normalize_phone(self, phone: str) -> str:
        """Normalize Kenya phone for M-Pesa (no + prefix)."""
        return normalize_phone_mpesa(phone)

    @property
    def is_configured(self) -> bool:
        return bool(self.consumer_key and self.consumer_secret)
