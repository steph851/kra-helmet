"""
M-PESA WEBHOOKS — receives and processes M-Pesa callbacks.
BOUNDARY: Receives callbacks and routes to audit trail. Never modifies payment data.
Handles: STK push results, C2B confirmations, B2C results, timeout notifications.

RENDER FREE-TIER RESILIENCE:
- Responds to Safaricom instantly (< 100ms) before doing any processing
- Buffers raw webhooks to disk first, then processes async
- Retry queue picks up any unprocessed webhooks on next startup
"""
import json
import asyncio
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Request, HTTPException, BackgroundTasks

EAT = timezone(timedelta(hours=3))

# Plan mapping for subscription amounts
PLAN_AMOUNTS = {
    500: "monthly",
    1200: "quarterly",
    4000: "annual",
}


class MpesaWebhookHandler:
    """Handles M-Pesa webhook callbacks with buffer-first resilience."""

    def __init__(self, subscription_tracker=None):
        self._root = Path(__file__).parent.parent.parent
        self._logs_dir = self._root / "logs"
        self._logs_dir.mkdir(exist_ok=True)
        self._callbacks_path = self._logs_dir / "mpesa_callbacks.jsonl"
        # Buffer: raw webhooks saved before processing
        self._buffer_path = self._logs_dir / "mpesa_buffer.jsonl"
        self._subs = subscription_tracker

    def set_subscription_tracker(self, tracker):
        """Set the subscription tracker for auto-confirming payments."""
        self._subs = tracker

    def create_router(self) -> APIRouter:
        """Create FastAPI router for M-Pesa webhooks."""
        router = APIRouter(prefix="/webhooks/mpesa", tags=["M-Pesa"])
        handler = self  # capture for closures

        @router.on_event("startup")
        async def _process_buffered_webhooks():
            """On startup, process any webhooks that were buffered but not yet confirmed."""
            handler._retry_buffered()

        @router.post("/stk-result")
        async def stk_result(request: Request, bg: BackgroundTasks):
            """STK push result callback."""
            body = await request.json()
            # Buffer to disk FIRST (survives crashes)
            handler._buffer_webhook("stk_result", body)
            # Process in background — Safaricom gets instant 200
            bg.add_task(handler._process_stk_async, body)
            return {"ResultCode": 0, "ResultDesc": "Accepted"}

        @router.post("/c2b-confirmation")
        async def c2b_confirmation(request: Request, bg: BackgroundTasks):
            """C2B payment confirmation — responds instantly, processes async."""
            body = await request.json()
            # Buffer to disk FIRST
            entry_id = handler._buffer_webhook("c2b_confirmation", body)
            # Process in background — Safaricom gets instant 200
            bg.add_task(handler._process_c2b_async, body, entry_id)
            return {"ResultCode": 0, "ResultDesc": "Accepted"}

        @router.post("/b2c-result")
        async def b2c_result(request: Request, bg: BackgroundTasks):
            """B2C disbursement result."""
            body = await request.json()
            handler._buffer_webhook("b2c_result", body)
            bg.add_task(handler._process_b2c_async, body)
            return {"ResultCode": 0, "ResultDesc": "Accepted"}

        @router.post("/timeout")
        async def timeout(request: Request, bg: BackgroundTasks):
            """Transaction timeout notification."""
            body = await request.json()
            handler._buffer_webhook("timeout", body)
            bg.add_task(handler._process_timeout_async, body)
            return {"ResultCode": 0, "ResultDesc": "Accepted"}

        @router.get("/buffer-status")
        async def buffer_status():
            """Check how many webhooks are pending in the buffer."""
            pending = handler._count_pending()
            return {"pending": pending, "buffer_file": str(handler._buffer_path)}

        return router

    # ── Buffer: save raw webhook to disk before anything else ──

    def _buffer_webhook(self, callback_type: str, raw_body: dict) -> str:
        """Save raw webhook to buffer file. Returns entry ID."""
        entry_id = f"{callback_type}_{datetime.now(EAT).strftime('%Y%m%d_%H%M%S_%f')}"
        entry = {
            "id": entry_id,
            "callback_type": callback_type,
            "raw": raw_body,
            "buffered_at": datetime.now(EAT).isoformat(),
            "processed": False,
        }
        with open(self._buffer_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        return entry_id

    def _mark_processed(self, entry_id: str):
        """Mark a buffered webhook as processed."""
        if not self._buffer_path.exists():
            return
        lines = self._buffer_path.read_text(encoding="utf-8").strip().split("\n")
        updated = []
        for line in lines:
            if not line.strip():
                continue
            try:
                entry = json.loads(line)
                if entry.get("id") == entry_id:
                    entry["processed"] = True
                    entry["processed_at"] = datetime.now(EAT).isoformat()
                updated.append(json.dumps(entry, ensure_ascii=False))
            except json.JSONDecodeError:
                updated.append(line)
        self._buffer_path.write_text("\n".join(updated) + "\n", encoding="utf-8")

    def _count_pending(self) -> int:
        """Count unprocessed buffered webhooks."""
        if not self._buffer_path.exists():
            return 0
        count = 0
        for line in self._buffer_path.read_text(encoding="utf-8").strip().split("\n"):
            if not line.strip():
                continue
            try:
                entry = json.loads(line)
                if not entry.get("processed"):
                    count += 1
            except json.JSONDecodeError:
                continue
        return count

    def _retry_buffered(self):
        """Process any unprocessed webhooks from the buffer (called on startup)."""
        if not self._buffer_path.exists():
            return
        retried = 0
        for line in self._buffer_path.read_text(encoding="utf-8").strip().split("\n"):
            if not line.strip():
                continue
            try:
                entry = json.loads(line)
                if entry.get("processed"):
                    continue
                cb_type = entry.get("callback_type")
                body = entry.get("raw", {})
                entry_id = entry.get("id", "")

                if cb_type == "c2b_confirmation":
                    result = self._process_c2b(body)
                    self._confirm_subscription(result)
                    self._log_callback("c2b_confirmation", body, result)
                elif cb_type == "stk_result":
                    result = self._process_stk_result(body)
                    self._log_callback("stk_result", body, result)
                elif cb_type == "b2c_result":
                    result = self._process_b2c(body)
                    self._log_callback("b2c_result", body, result)
                elif cb_type == "timeout":
                    result = self._process_timeout(body)
                    self._log_callback("timeout", body, result)

                self._mark_processed(entry_id)
                retried += 1
            except Exception:
                continue

        if retried > 0:
            print(f"[M-Pesa] Retried {retried} buffered webhook(s) from previous session")

    # ── Async processing (runs after instant 200 response) ──

    def _process_stk_async(self, body: dict):
        result = self._process_stk_result(body)
        self._log_callback("stk_result", body, result)

    def _process_c2b_async(self, body: dict, entry_id: str):
        result = self._process_c2b(body)
        self._log_callback("c2b_confirmation", body, result)
        self._confirm_subscription(result)
        self._mark_processed(entry_id)

    def _process_b2c_async(self, body: dict):
        result = self._process_b2c(body)
        self._log_callback("b2c_result", body, result)

    def _process_timeout_async(self, body: dict):
        result = self._process_timeout(body)
        self._log_callback("timeout", body, result)

    # ── Subscription auto-confirm (extracted for reuse) ──

    def _confirm_subscription(self, result: dict):
        """Auto-confirm subscription if reference matches KRADTC-*."""
        if not self._subs or not result.get("bill_ref"):
            return
        ref = result["bill_ref"]
        if not ref.startswith("KRADTC-"):
            return

        pin = ref.replace("KRADTC-", "")
        amount = result.get("amount", 0)
        phone = result.get("phone", "")
        mpesa_ref = result.get("transaction_id", "")

        plan = self._amount_to_plan(amount)
        if not plan:
            return

        try:
            sub = self._subs.record_payment(pin, amount, plan, mpesa_ref, phone)
            # Send WhatsApp confirmation
            from tools.whatsapp_sender import WhatsAppSender
            wa = WhatsAppSender()
            wa.send(
                phone,
                f"✅ Payment confirmed! KES {amount} received.\n\n"
                f"Plan: *{plan.title()}*\n"
                f"Active until: *{sub.get('expires_at', 'N/A')[:10]}*\n\n"
                f"You'll now receive compliance reports via WhatsApp.\n"
                f"Reply STOP to unsubscribe.",
                pin
            )
            result["subscription_confirmed"] = True
            result["subscription"] = sub
        except Exception as e:
            result["subscription_error"] = str(e)

    def _amount_to_plan(self, amount_kes: float) -> str | None:
        """Map payment amount to subscription plan."""
        return PLAN_AMOUNTS.get(int(amount_kes))

    # ── Core processors (unchanged) ──

    def _process_stk_result(self, body: dict) -> dict:
        """Process STK push result."""
        stk_callback = body.get("Body", {}).get("stkCallback", {})
        result_code = stk_callback.get("ResultCode")
        result_desc = stk_callback.get("ResultDesc")
        checkout_request_id = stk_callback.get("CheckoutRequestID")
        merchant_request_id = stk_callback.get("MerchantRequestID")

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
