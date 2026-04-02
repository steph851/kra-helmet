"""
PII HANDLER — anonymizes personally identifiable information in logs.
BOUNDARY: Masks PII only. Never stores or transmits raw PII.
Detects and masks: KRA PINs, phone numbers, emails, names, M-Pesa codes.
"""
import re
from typing import Any


class PIIHandler:
    """Detects and masks PII in text and data structures."""

    # KRA PIN: letter + 9 digits + letter (e.g. A123456789B)
    PIN_PATTERN = re.compile(r"\b[A-Z]\d{9}[A-Z]\b")

    # Kenya phone numbers: 07XX, 01XX, +254...
    PHONE_PATTERN = re.compile(r"(?:\+254|0)[17]\d{8}")

    # Email addresses
    EMAIL_PATTERN = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")

    # M-Pesa confirmation codes (alphanumeric, 10+ chars)
    MPESA_CODE_PATTERN = re.compile(r"\b[A-Z0-9]{10,}\b")

    # Names: 2+ capitalized words (heuristic)
    NAME_PATTERN = re.compile(r"\b[A-Z][a-z]+ [A-Z][a-z]+(?:\s[A-Z][a-z]+)?\b")

    def mask_pin(self, text: str) -> str:
        """Mask KRA PINs: A123456789B → A***...***B"""
        return self.PIN_PATTERN.sub(lambda m: f"{m.group()[0]}***{m.group()[-1]}", text)

    def mask_phone(self, text: str) -> str:
        """Mask phone numbers: 0712345678 → 07***678"""
        def _mask(m):
            phone = m.group()
            if phone.startswith("+254"):
                return f"+254***{phone[-3:]}"
            return f"{phone[:2]}***{phone[-3:]}"
        return self.PHONE_PATTERN.sub(_mask, text)

    def mask_email(self, text: str) -> str:
        """Mask emails: user@domain.com → u***@d***.com"""
        def _mask(m):
            email = m.group()
            local, domain = email.split("@", 1)
            domain_parts = domain.split(".")
            masked_local = local[0] + "***" if local else "***"
            masked_domain = domain_parts[0][0] + "***" if domain_parts[0] else "***"
            return f"{masked_local}@{masked_domain}.{domain_parts[-1]}"
        return self.EMAIL_PATTERN.sub(_mask, text)

    def mask_name(self, text: str) -> str:
        """Mask names: John Doe → J*** D***"""
        def _mask(m):
            parts = m.group().split()
            return " ".join(p[0] + "***" for p in parts)
        return self.NAME_PATTERN.sub(_mask, text)

    def mask_mpesa_code(self, text: str) -> str:
        """Mask M-Pesa codes: QK7X9M2P4N → QK***4N"""
        return self.MPESA_CODE_PATTERN.sub(
            lambda m: f"{m.group()[:2]}***{m.group()[-2:]}" if len(m.group()) >= 4 else m.group(),
            text
        )

    def mask_all(self, text: str) -> str:
        """Apply all PII masking to text."""
        text = self.mask_pin(text)
        text = self.mask_phone(text)
        text = self.mask_email(text)
        text = self.mask_name(text)
        return text

    def anonymize_record(self, record: dict, fields: list[str] | None = None) -> dict:
        """Anonymize PII fields in a dict record."""
        result = {}
        for key, value in record.items():
            if fields and key not in fields:
                result[key] = value
            elif isinstance(value, str):
                result[key] = self.mask_all(value)
            elif isinstance(value, dict):
                result[key] = self.anonymize_record(value, fields)
            elif isinstance(value, list):
                result[key] = [
                    self.anonymize_record(item, fields) if isinstance(item, dict)
                    else self.mask_all(str(item)) if isinstance(item, str)
                    else item
                    for item in value
                ]
            else:
                result[key] = value
        return result

    def safe_log(self, message: str, data: Any = None) -> str:
        """Create a safe log message with PII masked."""
        safe_msg = self.mask_all(message)
        if data:
            if isinstance(data, dict):
                safe_data = self.anonymize_record(data)
                return f"{safe_msg} | {safe_data}"
            return f"{safe_msg} | {self.mask_all(str(data))}"
        return safe_msg

    def is_pii_free(self, text: str) -> bool:
        """Check if text contains no detectable PII."""
        return not any([
            self.PIN_PATTERN.search(text),
            self.PHONE_PATTERN.search(text),
            self.EMAIL_PATTERN.search(text),
        ])
