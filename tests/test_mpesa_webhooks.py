"""Tests for M-Pesa webhook handler — buffer, processing, subscription auto-confirm."""
import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from integrations.mpesa.webhooks import MpesaWebhookHandler, PLAN_AMOUNTS


@pytest.fixture
def handler(tmp_path):
    h = MpesaWebhookHandler()
    h._logs_dir = tmp_path
    h._callbacks_path = tmp_path / "mpesa_callbacks.jsonl"
    h._buffer_path = tmp_path / "mpesa_buffer.jsonl"
    return h


@pytest.fixture
def handler_with_subs(handler):
    mock_subs = MagicMock()
    mock_subs.record_payment.return_value = {
        "pin": "A123456789B",
        "status": "active",
        "expires_at": "2026-05-04T12:00:00+03:00",
    }
    handler._subs = mock_subs
    return handler, mock_subs


class TestPlanAmounts:
    def test_monthly(self):
        assert PLAN_AMOUNTS[500] == "monthly"

    def test_quarterly(self):
        assert PLAN_AMOUNTS[1200] == "quarterly"

    def test_annual(self):
        assert PLAN_AMOUNTS[4000] == "annual"

    def test_unknown_amount(self):
        handler = MpesaWebhookHandler()
        assert handler._amount_to_plan(999) is None


class TestWebhookBuffer:
    def test_buffer_creates_file(self, handler):
        entry_id = handler._buffer_webhook("c2b_confirmation", {"TransID": "ABC123"})
        assert handler._buffer_path.exists()
        assert entry_id.startswith("c2b_confirmation_")

    def test_buffer_entry_format(self, handler):
        handler._buffer_webhook("c2b_confirmation", {"TransID": "ABC123"})
        line = handler._buffer_path.read_text(encoding="utf-8").strip()
        entry = json.loads(line)
        assert entry["callback_type"] == "c2b_confirmation"
        assert entry["processed"] is False
        assert "id" in entry
        assert "buffered_at" in entry

    def test_buffer_multiple_entries(self, handler):
        handler._buffer_webhook("c2b_confirmation", {"TransID": "1"})
        handler._buffer_webhook("stk_result", {"Body": {}})
        handler._buffer_webhook("timeout", {})
        lines = handler._buffer_path.read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) == 3

    def test_mark_processed(self, handler):
        entry_id = handler._buffer_webhook("c2b_confirmation", {"TransID": "X"})
        handler._mark_processed(entry_id)
        line = handler._buffer_path.read_text(encoding="utf-8").strip()
        entry = json.loads(line)
        assert entry["processed"] is True
        assert "processed_at" in entry

    def test_count_pending(self, handler):
        handler._buffer_webhook("c2b_confirmation", {"TransID": "1"})
        id2 = handler._buffer_webhook("c2b_confirmation", {"TransID": "2"})
        handler._buffer_webhook("c2b_confirmation", {"TransID": "3"})
        handler._mark_processed(id2)
        assert handler._count_pending() == 2

    def test_buffer_rotation(self, handler):
        # Create oversized buffer
        handler._buffer_path.write_text("x" * (handler.MAX_BUFFER_BYTES + 1), encoding="utf-8")
        handler._buffer_webhook("c2b_confirmation", {"TransID": "new"})
        # Old buffer should be rotated
        rotated = list(handler._logs_dir.glob("mpesa_buffer_*.jsonl"))
        assert len(rotated) == 1
        # New buffer should have only the new entry
        lines = handler._buffer_path.read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) == 1


class TestC2BProcessing:
    def test_process_c2b(self, handler):
        body = {
            "TransID": "QCI79H3B71",
            "TransType": "Pay Bill",
            "TransAmount": "500",
            "MSISDN": "254711419880",
            "BillRefNumber": "KRADTC-A123456789B",
            "OrgAccountBalance": "5000",
        }
        result = handler._process_c2b(body)
        assert result["transaction_id"] == "QCI79H3B71"
        assert result["amount"] == "500"
        assert result["bill_ref"] == "KRADTC-A123456789B"
        assert result["phone"] == "254711419880"

    def test_auto_confirm_subscription(self, handler_with_subs):
        handler, mock_subs = handler_with_subs
        result = {
            "bill_ref": "KRADTC-A123456789B",
            "amount": 500,
            "phone": "254711419880",
            "transaction_id": "QCI79H3B71",
        }
        with patch("tools.whatsapp_sender.WhatsAppSender"):
            handler._confirm_subscription(result)
        mock_subs.record_payment.assert_called_once_with(
            "A123456789B", 500, "monthly", "QCI79H3B71", "254711419880"
        )
        assert result["subscription_confirmed"] is True

    def test_no_confirm_without_kradtc_prefix(self, handler_with_subs):
        handler, mock_subs = handler_with_subs
        result = {"bill_ref": "OTHER-REF", "amount": 500}
        handler._confirm_subscription(result)
        mock_subs.record_payment.assert_not_called()

    def test_no_confirm_unknown_amount(self, handler_with_subs):
        handler, mock_subs = handler_with_subs
        result = {"bill_ref": "KRADTC-A123456789B", "amount": 999}
        handler._confirm_subscription(result)
        mock_subs.record_payment.assert_not_called()


class TestSTKProcessing:
    def test_process_stk_success(self, handler):
        body = {
            "Body": {
                "stkCallback": {
                    "ResultCode": 0,
                    "ResultDesc": "Success",
                    "CheckoutRequestID": "ws_CO_123",
                    "MerchantRequestID": "mr_123",
                    "CallbackMetadata": {
                        "Item": [
                            {"Name": "Amount", "Value": 500},
                            {"Name": "MpesaReceiptNumber", "Value": "QCI123"},
                            {"Name": "PhoneNumber", "Value": 254711419880},
                        ]
                    }
                }
            }
        }
        result = handler._process_stk_result(body)
        assert result["success"] is True
        assert result["amount"] == 500
        assert result["mpesa_receipt"] == "QCI123"

    def test_process_stk_failure(self, handler):
        body = {
            "Body": {
                "stkCallback": {
                    "ResultCode": 1032,
                    "ResultDesc": "Cancelled by user",
                    "CheckoutRequestID": "ws_CO_456",
                    "MerchantRequestID": "mr_456",
                }
            }
        }
        result = handler._process_stk_result(body)
        assert result["success"] is False
        assert result["result_code"] == 1032


class TestCallbackLogging:
    def test_log_callback(self, handler):
        handler._log_callback("c2b_confirmation", {"raw": True}, {"processed": True})
        assert handler._callbacks_path.exists()
        entry = json.loads(handler._callbacks_path.read_text(encoding="utf-8").strip())
        assert entry["callback_type"] == "c2b_confirmation"

    def test_get_recent_callbacks_empty(self, handler):
        assert handler.get_recent_callbacks() == []

    def test_get_recent_callbacks(self, handler):
        for i in range(5):
            handler._log_callback("test", {"i": i}, {"i": i})
        recent = handler.get_recent_callbacks(limit=3)
        assert len(recent) == 3


class TestRetryBuffered:
    def test_retry_unprocessed(self, handler):
        # Buffer 2 entries, mark 1 processed
        id1 = handler._buffer_webhook("c2b_confirmation", {
            "TransID": "A", "TransAmount": "500", "MSISDN": "254711419880",
            "BillRefNumber": "TEST", "TransType": "Pay Bill", "OrgAccountBalance": "0",
        })
        handler._buffer_webhook("c2b_confirmation", {
            "TransID": "B", "TransAmount": "500", "MSISDN": "254711419880",
            "BillRefNumber": "TEST2", "TransType": "Pay Bill", "OrgAccountBalance": "0",
        })
        handler._mark_processed(id1)
        # Retry should process only the unprocessed one
        handler._retry_buffered()
        assert handler._count_pending() == 0
