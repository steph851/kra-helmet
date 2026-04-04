"""
PHONE ENCRYPTION — encrypts phone numbers at rest using Fernet symmetric encryption.
Key is derived from HELMET_API_KEY env var (or a default for dev).
"""
import os
import base64
import hashlib
from cryptography.fernet import Fernet


def _derive_key() -> bytes:
    """Derive a Fernet key from HELMET_API_KEY (or fallback for dev)."""
    secret = os.getenv("HELMET_API_KEY", "dev-key-not-for-production")
    # Fernet needs exactly 32 url-safe base64 bytes
    raw = hashlib.sha256(secret.encode()).digest()
    return base64.urlsafe_b64encode(raw)


_fernet = Fernet(_derive_key())


def encrypt_phone(phone: str) -> str:
    """Encrypt a phone number. Returns base64 string prefixed with 'enc:'."""
    if not phone or phone.startswith("enc:"):
        return phone  # already encrypted or empty
    return "enc:" + _fernet.encrypt(phone.encode()).decode()


def decrypt_phone(value: str) -> str:
    """Decrypt a phone number. Handles both encrypted and plaintext values."""
    if not value:
        return value
    if not value.startswith("enc:"):
        return value  # plaintext — backwards compatible
    try:
        return _fernet.decrypt(value[4:].encode()).decode()
    except Exception:
        return value  # decryption failed — return as-is
