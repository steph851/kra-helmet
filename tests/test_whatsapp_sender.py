"""Tests for WhatsApp sender — bot provider, fallback, bulk send."""
import pytest
from unittest.mock import patch, MagicMock
from tools.whatsapp_sender import WhatsAppSender


class TestWhatsAppSenderInit:
    def test_default_provider_is_bot(self):
        sender = WhatsAppSender()
        assert sender.provider == "bot"

    @patch.dict("os.environ", {"HELMET_WA_PROVIDER": "dry_run"})
    def test_dry_run_provider(self):
        sender = WhatsAppSender()
        assert sender.provider == "dry_run"


class TestDryRunSend:
    @patch.dict("os.environ", {"HELMET_WA_PROVIDER": "dry_run"})
    def test_dry_run_returns_result(self):
        sender = WhatsAppSender()
        result = sender.send("254711419880", "Hello", "A123456789B")
        assert result["provider"] == "none"
        assert result["status"] == "dry_run"
        assert "254711419880" in result["phone"]

    @patch.dict("os.environ", {"HELMET_WA_PROVIDER": "dry_run"})
    def test_dry_run_bulk(self):
        sender = WhatsAppSender()
        messages = [
            {"phone": "254711419880", "message": "Hello 1", "pin": "A123456789B"},
            {"phone": "254711419881", "message": "Hello 2", "pin": "A000000001B"},
        ]
        results = sender.send_bulk(messages)
        assert results["total"] == 2
        assert len(results["results"]) == 2


class TestBotFallback:
    @patch("tools.whatsapp_sender.WhatsAppSender._send_via_bot")
    def test_bot_failure_falls_back_to_dry_run(self, mock_bot):
        mock_bot.return_value = {"success": False, "error": "Bot not running"}
        sender = WhatsAppSender()
        result = sender.send("254711419880", "Test", "A123456789B")
        # Should fall back to dry_run
        assert result["status"] == "dry_run"
        assert result["provider"] == "none"

    @patch("tools.whatsapp_sender.WhatsAppSender._send_via_bot")
    def test_bot_success(self, mock_bot):
        mock_bot.return_value = {"success": True, "provider": "whatsapp_bot", "messageId": "123"}
        sender = WhatsAppSender()
        result = sender.send("254711419880", "Test", "A123456789B")
        assert result["success"] is True
        assert result["provider"] == "whatsapp_bot"


class TestBotStatus:
    @patch("urllib.request.urlopen")
    def test_bot_status_connected(self, mock_urlopen):
        mock_response = MagicMock()
        mock_response.read.return_value = b'{"connected": true, "phone": "254711419880"}'
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_response

        sender = WhatsAppSender()
        status = sender.bot_status()
        assert status["connected"] is True

    @patch("urllib.request.urlopen")
    def test_bot_status_unreachable(self, mock_urlopen):
        mock_urlopen.side_effect = Exception("Connection refused")
        sender = WhatsAppSender()
        status = sender.bot_status()
        assert status["connected"] is False


class TestPhoneCrypto:
    def test_encrypt_decrypt_roundtrip(self):
        from subscription.crypto import encrypt_phone, decrypt_phone
        phone = "254711419880"
        encrypted = encrypt_phone(phone)
        assert encrypted.startswith("enc:")
        assert encrypted != phone
        decrypted = decrypt_phone(encrypted)
        assert decrypted == phone

    def test_decrypt_plaintext_passthrough(self):
        from subscription.crypto import decrypt_phone
        assert decrypt_phone("254711419880") == "254711419880"

    def test_encrypt_empty(self):
        from subscription.crypto import encrypt_phone
        assert encrypt_phone("") == ""

    def test_encrypt_already_encrypted(self):
        from subscription.crypto import encrypt_phone
        val = "enc:already_encrypted_data"
        assert encrypt_phone(val) == val
