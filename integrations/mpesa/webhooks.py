"""
M-PESA WEBHOOKS — receives and processes M-Pesa callbacks.
BOUNDARY: Receives callbacks and routes to audit trail. Never modifies payment data.
Handles: STK push results, C2B confirmations, B2C results, timeout notifications.
"""
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Request, HTTPException

EAT = timezone(timedelta(hours=3))


class MpesaWebhookHandler:
    """Handles M-Pesa webhook callbacks."""

    def __init__(self):
        self._logs_dir = Path(__file__).parent.parent.parent / "logs"
        self._logs_dir.mkdir(exist_ok=True)
        self._callbacks_path = self._logs_dir / "mpesa_callbacks.jsonl"

    def create_router(self) -> APIRouter:
        """Create FastAPI router for M-Pesa webhooks."""
        router = APIRouter(prefix="/webhooks/mpesa", tags=["M-Pesa"])

        @router.post("/stk-result")
        async def stk_result(request: Request):
            """STK push result callback."""
            body = await request.json()
            result = self._process_stk_result(body)
            self._log_callback("stk_result", body, result)
            return {"ResultCode": 0, "ResultDesc": "Accepted"}

        @router.post("/c2b-confirmation")
        async def c2b_confirmation(request: Request):
            """C2B payment confirmation."""
            body = await request.json()
            result = self._process_c2b(body)
            self._log_callback("c2b_confirmation", body, result)
            return {"ResultCode": 0, "ResultDesc": "Accepted"}

        @router.post("/b2c-result")
        async def b2c_result(request: Request):
            """B2C disbursement result."""
            body = await request.json()
            result = self._process_b2c(body)
            self._log_callback("b2c_result", body, result)
            return {"ResultCode": 0, "ResultDesc": "Accepted"}

        @router.post("/timeout")
        async def timeout(request: Request):
            """Transaction timeout notification."""
            body = await request.json()
            result = self._process_timeout(body)
            self._log_callback("timeout", body, result)
            return {"ResultCode": 0, "ResultDesc": "Accepted"}

        return router

    def _process_stk_result(self, body: dict) -> dict:
        """Process STK push result."""
        stk_callback = body.get("Body", {}).get("stkCallback", {})
        result_code = stk_callback.get("ResultCode")
        result_desc = stk_callback.get("ResultDesc")
        checkout_request_id = stk_callback.get("CheckoutRequestID")
        merchant_request_id = stk_callback.get("MerchantRequestID")

        # Extract metadata if successful
        metadata = {}
        if result_code == 0:
            items = stk_callback.get("CallbackMetadata", {}).get("Item", [])
            for item in items:
                name = item.get("Name")
                value = item.get("Value")
                if name and value is not None:
                    metadata[name] = value

        return {
            "type": "stk_result",
            "result_code": result_code,
            "result_desc": result_desc,
            "checkout_request_id": checkout_request_id,
            "merchant_request_id": merchant_request_id,
            "success": result_code == 0,
            "metadata": metadata,
            "amount": metadata.get("Amount"),
            "mpesa_receipt": metadata.get("MpesaReceiptNumber"),
            "phone": metadata.get("PhoneNumber"),
            "transaction_date": metadata.get("TransactionDate"),
            "received_at": datetime.now(EAT).isoformat(),
        }

    def _process_c2b(self, body: dict) -> dict:
        """Process C2B payment confirmation."""
        return {
            "type": "c2b_confirmation",
            "transaction_id": body.get("TransID"),
            "transaction_type": body.get("TransType"),
            "amount": body.get("TransAmount"),
            "phone": body.get("MSISDN"),
            "bill_ref": body.get("BillRefNumber"),
            "org_balance": body.get("OrgAccountBalance"),
            "received_at": datetime.now(EAT).isoformat(),
        }

    def _process_b2c(self, body: dict) -> dict:
        """Process B2C disbursement result."""
        result = body.get("Result", {})
        return {
            "type": "b2c_result",
            "result_code": result.get("ResultCode"),
            "result_desc": result.get("ResultDesc"),
            "transaction_id": result.get("TransactionID"),
            "amount": result.get("ResultParameters", {}).get("ResultParameter", [{}])[0].get("Value"),
            "phone": result.get("ResultParameters", {}).get("ResultParameter", [{}])[1].get("Value"),
            "received_at": datetime.now(EAT).isoformat(),
        }

    def _process_timeout(self, body: dict) -> dict:
        """Process timeout notification."""
        return {
            "type": "timeout",
            "checkout_request_id": body.get("CheckoutRequestID"),
            "received_at": datetime.now(EAT).isoformat(),
        }

    def _log_callback(self, callback_type: str, raw_body: dict, processed: dict):
        """Log callback to JSONL file."""
        entry = {
            "callback_type": callback_type,
            "raw": raw_body,
            "processed": processed,
            "received_at": datetime.now(EAT).isoformat(),
        }
        with open(self._callbacks_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def get_recent_callbacks(self, limit: int = 50) -> list[dict]:
        """Get recent callbacks."""
        if not self._callbacks_path.exists():
            return []
        entries = []
        with open(self._callbacks_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        entries.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
        return entries[-limit:]
