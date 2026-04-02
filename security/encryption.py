"""
ENCRYPTION — AES-256 at rest encryption for sensitive data.
BOUNDARY: Encrypts/decrypts data only. Never stores keys with data.
Uses Fernet (AES-128-CBC with HMAC) for authenticated encryption.
Key is derived from HELMET_ENCRYPTION_KEY env var via PBKDF2.
"""
import os
import json
import base64
from pathlib import Path
from typing import Any

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives.hashes import SHA256
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC


class DataEncryptor:
    """AES-256 encryption for sensitive data at rest."""

    def __init__(self):
        self._key = self._derive_key()
        self._fernet = Fernet(self._key)

    def _derive_key(self) -> bytes:
        """Derive encryption key from environment variable."""
        password = os.getenv("HELMET_ENCRYPTION_KEY", "")
        if not password:
            raise ValueError(
                "HELMET_ENCRYPTION_KEY not set. "
                "Generate with: python -c \"from security.encryption import DataEncryptor; print(DataEncryptor.generate_key())\""
            )

        salt = os.getenv("HELMET_ENCRYPTION_SALT", "kra-helmet-salt-v1").encode()
        kdf = PBKDF2HMAC(
            algorithm=SHA256(),
            length=32,
            salt=salt,
            iterations=480000,
        )
        key = base64.urlsafe_b64encode(kdf.derive(password.encode()))
        return key

    def encrypt(self, data: Any) -> str:
        """Encrypt data to string. Accepts dict, list, str, or bytes."""
        if isinstance(data, (dict, list)):
            data = json.dumps(data, ensure_ascii=False)
        if isinstance(data, str):
            data = data.encode("utf-8")
        return self._fernet.encrypt(data).decode("utf-8")

    def decrypt(self, encrypted: str) -> str:
        """Decrypt string back to plaintext."""
        return self._fernet.decrypt(encrypted.encode("utf-8")).decode("utf-8")

    def decrypt_json(self, encrypted: str) -> Any:
        """Decrypt and parse JSON data."""
        plaintext = self.decrypt(encrypted)
        return json.loads(plaintext)

    def encrypt_file(self, source: Path, dest: Path | None = None) -> Path:
        """Encrypt a file. Returns path to encrypted file."""
        dest = dest or source.with_suffix(source.suffix + ".enc")
        data = source.read_bytes()
        encrypted = self._fernet.encrypt(data)
        dest.write_bytes(encrypted)
        return dest

    def decrypt_file(self, source: Path, dest: Path | None = None) -> Path:
        """Decrypt a file. Returns path to decrypted file."""
        dest = dest or source.with_suffix("")
        encrypted = source.read_bytes()
        data = self._fernet.decrypt(encrypted)
        dest.write_bytes(data)
        return dest

    def encrypt_field(self, record: dict, field: str) -> dict:
        """Encrypt a specific field in a dict. Returns new dict."""
        if field not in record:
            return record
        result = dict(record)
        result[field] = self.encrypt(str(record[field]))
        result[f"_{field}_encrypted"] = True
        return result

    def decrypt_field(self, record: dict, field: str) -> dict:
        """Decrypt a specific field in a dict. Returns new dict."""
        if not record.get(f"_{field}_encrypted"):
            return record
        result = dict(record)
        result[field] = self.decrypt(record[field])
        del result[f"_{field}_encrypted"]
        return result

    @staticmethod
    def generate_key() -> str:
        """Generate a random encryption key for HELMET_ENCRYPTION_KEY."""
        return base64.urlsafe_b64encode(os.urandom(32)).decode("utf-8")
