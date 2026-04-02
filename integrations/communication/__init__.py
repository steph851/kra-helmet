"""
COMMUNICATION INTEGRATION — WhatsApp, SMS, and email delivery.
BOUNDARY: Sends messages through configured channels. Never decides content or urgency.
Supports: WhatsApp Business API, SMS (Africa's Talking/Twilio), Email (SMTP).
"""
from .whatsapp import WhatsAppSender
from .sms import SMSSender
from .email_sender import EmailSender

__all__ = ["WhatsAppSender", "SMSSender", "EmailSender"]
