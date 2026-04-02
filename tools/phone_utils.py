"""
PHONE UTILS — shared phone number normalization.
Used by WhatsApp, SMS, and M-Pesa integrations.
"""


def normalize_phone(phone: str) -> str:
    """Normalize Kenya phone to +254 format.
    
    Handles formats:
    - 0712345678 → +254712345678
    - 254712345678 → +254712345678
    - +254712345678 → +254712345678
    - 0712-345 678 → +254712345678
    """
    phone = phone.strip().replace(" ", "").replace("-", "")
    if phone.startswith("0"):
        phone = "+254" + phone[1:]
    elif phone.startswith("254") and not phone.startswith("+"):
        phone = "+" + phone
    return phone


def normalize_phone_mpesa(phone: str) -> str:
    """Normalize Kenya phone for M-Pesa (no + prefix).
    
    Handles formats:
    - 0712345678 → 254712345678
    - +254712345678 → 254712345678
    - 254712345678 → 254712345678
    """
    phone = phone.strip().replace(" ", "").replace("-", "")
    if phone.startswith("+"):
        phone = phone[1:]
    if phone.startswith("0"):
        phone = "254" + phone[1:]
    return phone
