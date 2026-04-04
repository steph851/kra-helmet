"""
THE SHIELD — Security layer for KRA Deadline Tracker.
Protects sensitive data with encryption, PII anonymization, and access control.
"""
from .encryption import DataEncryptor
from .pii_handler import PIIHandler
from .access_control import AccessControl, Role, Permission

__all__ = [
    "DataEncryptor",
    "PIIHandler",
    "AccessControl",
    "Role",
    "Permission",
]
