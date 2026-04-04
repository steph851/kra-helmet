"""
STK PUSH — M-Pesa Lipa Na M-Pesa Online integration.
BOUNDARY: Initiates STK push requests. Never stores card data.
Uses Safaricom Daraja API for payment initiation.
"""
import base64
from datetime import datetime, timedelta, timezone

from integrations.base import HardenedIntegration, IntegrationConfig, with_retry
from integrations.mpesa.config import MpesaConfig

EAT = timezone(timedelta(hours=3))


class STKPush(HardenedIntegration):
    """M-Pesa STK Push (Lipa Na M-Pesa Online)."""

    def __init__(self, config: MpesaConfig | None = None):
        mpesa_config = IntegrationConfig(
            timeout=30,
            max_retries=3,
            retry_delay=2.0,
            retry_backoff=2.0,
            rate_limit_calls=10,
            rate_limit_period=60,
        )
        super().__init__(mpesa_config)
        self.mpesa = config or MpesaConfig()
        self._access_token: str | None = None
        self._token_expiry: datetime | None = None

    @property
    def is_configured(self) -> bool:
        return self.mpesa.is_configured

    @with_retry(max_retries=3, delay=2.0)
    def _get_access_token(self) -> str:
        """Get OAuth access token from Daraja API."""
        if self._access_token and self._token_expiry and datetime.now(EAT) < self._token_expiry:
            return self._access_token

        url = f"{self.mpesa.base_url}/oauth/v1/generate?grant_type=client_credentials"
        response = self.get(
            url,
            auth=(self.mpesa.consumer_key, self.mpesa.consumer_secret),
        )
        data = response.json()

        self._access_token = data["access_token"]
        self._token_expiry = datetime.now(EAT) + timedelta(seconds=int(data.get("expires_in", 3599)))

        return self._access_token

    def _generate_password(self) -> str:
        """Generate STK push password."""
        timestamp = datetime.now(EAT).strftime("%Y%m%d%H%M%S")
        password_str = f"{self.mpesa.shortcode}{self.mpesa.passkey}{timestamp}"
        return base64.b64encode(password_str.encode()).decode()

    @staticmethod
    def _normalize_phone(phone: str) -> str:
        """Normalize Kenya phone to 254XXXXXXXXX format."""
        phone = phone.strip().replace(" ", "").replace("-", "")
        if phone.startswith("0"):
            phone = "254" + phone[1:]
        elif phone.startswith("+"):
            phone = phone[1:]
        return phone

    @with_retry(max_retries=3, delay=2.0)
    def initiate(
        self,
        phone: str,
        amount: float,
        account_reference: str,
        transaction_desc: str = "Tax Payment",
        callback_url: str | None = None,
    ) -> dict:
        """Initiate STK push request.

        Args:
            phone: Customer phone (07XXXXXXXX or +254XXXXXXXXX)
            amount: Amount in KES
            account_reference: Reference for the transaction
            transaction_desc: Description shown to customer
            callback_url: Override callback URL

        Returns:
            Dict with MerchantRequestID, CheckoutRequestID, ResponseCode, etc.
        """
        if not self.is_configured:
            return {
                "status": "dry_run",
                "message": "M-Pesa not configured — set MPESA_CONSUMER_KEY, MPESA_CONSUMER_SECRET, MPESA_PASSKEY, MPESA_SHORTCODE",
                "phone": phone,
                "amount": amount,
                "account_reference": account_reference,
            }

        phone = self._normalize_phone(phone)
        token = self._get_access_token()
        password = self._generate_password()
        timestamp = datetime.now(EAT).strftime("%Y%m%d%H%M%S")

        payload = {
            "BusinessShortCode": self.mpesa.shortcode,
            "Password": password,
            "Timestamp": timestamp,
            "TransactionType": "CustomerPayBillOnline",
            "Amount": int(amount),
            "PartyA": phone,
            "PartyB": self.mpesa.shortcode,
            "PhoneNumber": phone,
            "CallBackURL": callback_url or self.mpesa.callback_url,
            "AccountReference": account_reference[:12],
            "TransactionDesc": transaction_desc[:13],
        }

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

        url = f"{self.mpesa.base_url}/mpesa/stkpush/v1/processrequest"
        response = self.post(url, json=payload, headers=headers)

        result = response.json()
        result["status"] = "initiated" if result.get("ResponseCode") == "0" else "failed"
        result["phone"] = phone
        result["amount"] = amount
        result["account_reference"] = account_reference
        result["environment"] = self.mpesa.environment
        result["initiated_at"] = datetime.now(EAT).isoformat()

        return result

    @with_retry(max_retries=3, delay=2.0)
    def query_status(self, checkout_request_id: str) -> dict:
        """Query STK push transaction status."""
        if not self.is_configured:
            return {"status": "dry_run", "checkout_request_id": checkout_request_id}

        token = self._get_access_token()
        password = self._generate_password()
        timestamp = datetime.now(EAT).strftime("%Y%m%d%H%M%S")

        payload = {
            "BusinessShortCode": self.mpesa.shortcode,
            "Password": password,
            "Timestamp": timestamp,
            "CheckoutRequestID": checkout_request_id,
        }

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

        url = f"{self.mpesa.base_url}/mpesa/stkpushquery/v1/query"
        response = self.post(url, json=payload, headers=headers)

        return response.json()

    def register_c2b_urls(self, validation_url: str = "", confirmation_url: str = "") -> dict:
        """Register C2B validation and confirmation URLs with Safaricom.
        Required before Safaricom will send C2B webhooks to your server.

        Args:
            validation_url: URL Safaricom calls to validate a transaction (optional)
            confirmation_url: URL Safaricom calls to confirm a transaction

        Returns:
            Safaricom API response dict
        """
        if not self.is_configured:
            return {
                "status": "dry_run",
                "message": "M-Pesa not configured — cannot register C2B URLs",
            }

        token = self._get_access_token()

        payload = {
            "ShortCode": self.mpesa.shortcode,
            "ResponseType": "Completed",  # or "Cancelled"
            "ConfirmationURL": confirmation_url or self.mpesa.callback_url,
            "ValidationURL": validation_url or self.mpesa.callback_url,
        }

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

        url = f"{self.mpesa.base_url}/mpesa/c2b/v1/registerurl"
        response = self.post(url, json=payload, headers=headers)

        result = response.json()
        result["environment"] = self.mpesa.environment
        result["registered_at"] = datetime.now(EAT).isoformat()
        return result
