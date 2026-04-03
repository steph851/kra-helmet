"""
KRA SHURU — integration with KRA's WhatsApp chatbot for tax filing and payment.
Shuru (launched April 2026) allows taxpayers to file returns, pay taxes,
get compliance certificates, and access eTIMS — all via WhatsApp.

Official KRA WhatsApp: +254 711 099 999
Deep link: https://wa.me/254711099999
"""
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

EAT = timezone(timedelta(hours=3))
ROOT = Path(__file__).parent.parent

KRA_SHURU_NUMBER = "+254711099999"
KRA_SHURU_DEEPLINK = "https://wa.me/254711099999"


class KRAShuru:
    """Generate Shuru deep links and payment/filing instructions for SMEs."""

    def generate_filing_link(self, pin: str, tax_type: str = "") -> dict:
        """Generate a WhatsApp deep link to start filing via Shuru."""
        # Pre-fill message with PIN context
        if tax_type:
            prefill = f"Hi, I need to file {tax_type} for PIN {pin}"
        else:
            prefill = f"Hi, I need to file my tax returns for PIN {pin}"

        deeplink = f"{KRA_SHURU_DEEPLINK}?text={_url_encode(prefill)}"

        return {
            "channel": "kra_whatsapp_shuru",
            "number": KRA_SHURU_NUMBER,
            "deeplink": deeplink,
            "prefill_message": prefill,
            "pin": pin,
            "tax_type": tax_type or "general",
        }

    def generate_payment_link(self, pin: str, tax_type: str = "", amount: float = 0) -> dict:
        """Generate a WhatsApp deep link to pay taxes via Shuru."""
        if tax_type and amount > 0:
            prefill = f"Hi, I want to pay KES {amount:,.0f} for {tax_type}, PIN {pin}"
        elif tax_type:
            prefill = f"Hi, I want to pay {tax_type} for PIN {pin}"
        else:
            prefill = f"Hi, I want to make a tax payment for PIN {pin}"

        deeplink = f"{KRA_SHURU_DEEPLINK}?text={_url_encode(prefill)}"

        return {
            "channel": "kra_whatsapp_shuru",
            "number": KRA_SHURU_NUMBER,
            "deeplink": deeplink,
            "prefill_message": prefill,
            "pin": pin,
            "tax_type": tax_type or "general",
            "amount_kes": amount,
        }

    def generate_compliance_cert_link(self, pin: str) -> dict:
        """Generate a WhatsApp deep link to request a tax compliance certificate."""
        prefill = f"Hi, I need a tax compliance certificate for PIN {pin}"
        deeplink = f"{KRA_SHURU_DEEPLINK}?text={_url_encode(prefill)}"

        return {
            "channel": "kra_whatsapp_shuru",
            "number": KRA_SHURU_NUMBER,
            "deeplink": deeplink,
            "prefill_message": prefill,
            "pin": pin,
        }

    def generate_instructions(self, pin: str, tax_type: str = "", lang: str = "en") -> dict:
        """Generate step-by-step Shuru instructions for an SME."""
        filing_link = self.generate_filing_link(pin, tax_type)
        payment_link = self.generate_payment_link(pin, tax_type)

        if lang == "sw":
            steps = [
                f"Ongeza {KRA_SHURU_NUMBER} kwenye anwani zako za WhatsApp",
                "Fungua WhatsApp na tuma 'Hi' kwa nambari hiyo",
                "Chagua huduma unayohitaji (Kulipa Kodi / Kuwasilisha / eTIMS)",
                f"Weka PIN yako ya KRA: {pin}",
                "Fuata maelekezo kutoka kwa Shuru",
                "Thibitisha na uhifadhi risiti yako",
            ]
            title = "Lipa Kodi kupitia WhatsApp ya KRA (Shuru)"
        else:
            steps = [
                f"Save {KRA_SHURU_NUMBER} to your WhatsApp contacts",
                "Open WhatsApp and send 'Hi' to that number",
                "Choose your service (Pay Tax / File Returns / eTIMS / Compliance Cert)",
                f"Enter your KRA PIN: {pin}",
                "Follow the prompts from Shuru",
                "Confirm and save your receipt",
            ]
            title = "Pay Taxes via KRA WhatsApp (Shuru)"

        return {
            "title": title,
            "number": KRA_SHURU_NUMBER,
            "steps": steps,
            "filing_deeplink": filing_link["deeplink"],
            "payment_deeplink": payment_link["deeplink"],
            "services": [
                "Tax payments",
                "Return filing (prefilled data — 3 steps)",
                "eTIMS services",
                "Tax compliance certificates",
                "PIN verification",
                "Speak to KRA agent",
            ],
        }

    def format_whatsapp_cta(self, pin: str, tax_type: str = "", lang: str = "en") -> str:
        """Format a WhatsApp-ready call-to-action message for Shuru."""
        link = self.generate_filing_link(pin, tax_type)

        if lang == "sw":
            return (
                f"\n\U0001f4f1 *Njia Mpya: Lipa kupitia WhatsApp ya KRA*\n"
                f"Tuma 'Hi' kwa {KRA_SHURU_NUMBER} kwenye WhatsApp\n"
                f"au bonyeza: {link['deeplink']}"
            )
        return (
            f"\n\U0001f4f1 *New: Pay via KRA WhatsApp (Shuru)*\n"
            f"Send 'Hi' to {KRA_SHURU_NUMBER} on WhatsApp\n"
            f"or tap: {link['deeplink']}"
        )


def _url_encode(text: str) -> str:
    """Simple URL encoding for WhatsApp deep link prefill text."""
    return text.replace(" ", "%20").replace(",", "%2C").replace(":", "%3A")
