"""
M-PESA CONFIG — Daraja API configuration.
BOUNDARY: Configuration only. Never executes API calls.
"""
import os
from dataclasses import dataclass


@dataclass
class MpesaConfig:
    """M-Pesa Daraja API configuration."""

    # API endpoints
    SANDBOX_URL = "https://sandbox.safaricom.co.ke"
    PRODUCTION_URL = "https://api.safaricom.co.ke"

    # Environment
    environment: str = "sandbox"  # sandbox | production

    # Credentials (from env vars)
    consumer_key: str = ""
    consumer_secret: str = ""
    passkey: str = ""
    shortcode: str = ""
    till_number: str = ""

    # Callback URLs
    callback_url: str = ""
    timeout_url: str = ""
    result_url: str = ""

    def __post_init__(self):
        self.consumer_key = os.getenv("MPESA_CONSUMER_KEY", self.consumer_key)
        self.consumer_secret = os.getenv("MPESA_CONSUMER_SECRET", self.consumer_secret)
        self.passkey = os.getenv("MPESA_PASSKEY", self.passkey)
        self.shortcode = os.getenv("MPESA_SHORTCODE", self.shortcode)
        self.till_number = os.getenv("MPESA_TILL_NUMBER", self.till_number)
        self.callback_url = os.getenv("MPESA_CALLBACK_URL", self.callback_url)
        self.timeout_url = os.getenv("MPESA_TIMEOUT_URL", self.timeout_url)
        self.result_url = os.getenv("MPESA_RESULT_URL", self.result_url)
        self.environment = os.getenv("MPESA_ENVIRONMENT", self.environment)

    @property
    def base_url(self) -> str:
        """Get base URL for current environment."""
        return self.PRODUCTION_URL if self.environment == "production" else self.SANDBOX_URL

    @property
    def is_configured(self) -> bool:
        """Check if all required credentials are set."""
        return all([
            self.consumer_key,
            self.consumer_secret,
            self.passkey,
            self.shortcode,
        ])

    @property
    def is_production(self) -> bool:
        """Check if running in production."""
        return self.environment == "production"
