"""
INPUT VALIDATOR — validates all user inputs before they enter the system.
Catches bad PINs, invalid phone numbers, out-of-range values, etc.
"""
import re
from ..base import BaseAgent


class InputValidator(BaseAgent):
    name = "input_validator"
    boundary = "Validates input only. Never modifies data or makes decisions."

    # KRA PIN format: letter + 9 digits + letter (e.g. A123456789B)
    # First letter must be valid KRA prefix (A, B, C, D, E, F, P, K)
    PIN_PATTERN = re.compile(r"^[A-Z]\d{9}[A-Z]$")
    VALID_PIN_PREFIXES = {"A", "B", "C", "D", "E", "F", "P", "K"}

    # Kenya phone: 07XX or 01XX, 10 digits — or +254...
    PHONE_PATTERN = re.compile(r"^(?:0[17]\d{8}|\+254[17]\d{8})$")

    # Period format: YYYY-MM
    PERIOD_PATTERN = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")

    VALID_BUSINESS_TYPES = {"sole_proprietor", "partnership", "limited_company"}

    VALID_INDUSTRIES = {
        "retail_wholesale", "professional_services", "food_hospitality",
        "transport", "manufacturing", "rental_income", "digital_online",
        "construction", "agriculture", "salon_beauty", "education", "healthcare",
    }

    VALID_BRACKETS = {"below_1m", "1m_to_8m", "8m_to_25m", "above_25m"}

    VALID_LANGUAGES = {"en", "sw"}

    VALID_CHANNELS = {"whatsapp", "sms", "email"}

    VALID_TAX_TYPES = {
        "turnover_tax", "vat", "paye", "income_tax_resident", "income_tax_corporate",
        "withholding_tax", "nssf", "shif", "housing_levy", "residential_rental_income",
        "presumptive_tax", "excise_duty", "digital_service_tax",
        "withholding_tax_rent_commercial", "withholding_tax_professional_fees",
        "withholding_tax_contractual_fees", "withholding_tax_management_fees",
    }

    def validate_pin(self, pin: str) -> tuple[bool, str]:
        """Validate a KRA PIN with strict format checking."""
        if not pin:
            return False, "PIN is required"
        pin = pin.strip().upper()
        if not self.PIN_PATTERN.match(pin):
            return False, f"Invalid KRA PIN format: '{pin}'. Expected: letter + 9 digits + letter (e.g. A123456789B)"
        # Check first letter is a valid KRA prefix
        if pin[0] not in self.VALID_PIN_PREFIXES:
            return False, f"Invalid KRA PIN prefix: '{pin[0]}'. Valid prefixes: {', '.join(sorted(self.VALID_PIN_PREFIXES))}"
        # Check last letter is alphabetic
        if not pin[-1].isalpha():
            return False, f"Invalid KRA PIN: last character must be a letter"
        return True, pin

    def validate_phone(self, phone: str) -> tuple[bool, str]:
        """Validate a Kenya phone number."""
        if not phone:
            return True, ""  # phone is optional
        phone = phone.strip().replace(" ", "").replace("-", "")
        if not self.PHONE_PATTERN.match(phone):
            return False, f"Invalid phone: '{phone}'. Expected: 07XXXXXXXX or 01XXXXXXXX"
        return True, phone

    def validate_email(self, email: str | None) -> tuple[bool, str]:
        """Validate email address."""
        if not email:
            return True, ""
        email = email.strip().lower()
        if not re.match(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$", email):
            return False, f"Invalid email: '{email}'"
        return True, email

    def validate_period(self, period: str) -> tuple[bool, str]:
        """Validate a filing period (YYYY-MM)."""
        if not period:
            return False, "Period is required (format: YYYY-MM)"
        period = period.strip()
        if not self.PERIOD_PATTERN.match(period):
            return False, f"Invalid period: '{period}'. Expected: YYYY-MM (e.g. 2026-03)"
        year = int(period[:4])
        if year < 2020 or year > 2030:
            return False, f"Period year out of range: {year}"
        return True, period

    def validate_amount(self, amount, field_name: str = "amount") -> tuple[bool, float]:
        """Validate a monetary amount."""
        try:
            val = float(amount)
        except (TypeError, ValueError):
            return False, f"Invalid {field_name}: must be a number"
        if val < 0:
            return False, f"Invalid {field_name}: cannot be negative"
        if val > 10_000_000_000:  # 10 billion KES sanity check
            return False, f"Invalid {field_name}: value seems unreasonably high"
        return True, val

    def validate_profile(self, data: dict) -> tuple[bool, list[str]]:
        """Validate a complete SME profile for onboarding. Returns (ok, errors)."""
        errors = []

        # PIN
        ok, msg = self.validate_pin(data.get("pin", ""))
        if not ok:
            errors.append(msg)

        # Name
        name = (data.get("name") or "").strip()
        if not name or len(name) < 2:
            errors.append("Name is required (at least 2 characters)")
        if len(name) > 200:
            errors.append("Name too long (max 200 characters)")

        # Business type
        btype = data.get("business_type", "")
        if btype and btype not in self.VALID_BUSINESS_TYPES:
            errors.append(f"Invalid business type: '{btype}'. Valid: {', '.join(sorted(self.VALID_BUSINESS_TYPES))}")

        # Industry
        industry = data.get("industry", "")
        if industry and industry not in self.VALID_INDUSTRIES:
            errors.append(f"Invalid industry: '{industry}'. Valid: {', '.join(sorted(self.VALID_INDUSTRIES))}")

        # Turnover bracket
        bracket = data.get("turnover_bracket", "")
        if bracket and bracket not in self.VALID_BRACKETS:
            errors.append(f"Invalid turnover bracket: '{bracket}'. Valid: {', '.join(sorted(self.VALID_BRACKETS))}")

        # Annual turnover
        turnover = data.get("annual_turnover_kes")
        if turnover is not None:
            ok, msg = self.validate_amount(turnover, "annual_turnover_kes")
            if not ok:
                errors.append(msg)

        # Phone
        ok, msg = self.validate_phone(data.get("phone", ""))
        if not ok:
            errors.append(msg)

        # Email
        ok, msg = self.validate_email(data.get("email"))
        if not ok:
            errors.append(msg)

        # Employee count
        if data.get("has_employees"):
            count = data.get("employee_count")
            if count is not None:
                try:
                    count = int(count)
                    if count < 0:
                        errors.append("Employee count cannot be negative")
                    if count > 100_000:
                        errors.append("Employee count seems unreasonably high")
                except (TypeError, ValueError):
                    errors.append("Employee count must be a number")

        # Language
        lang = data.get("preferred_language", "en")
        if lang not in self.VALID_LANGUAGES:
            errors.append(f"Invalid language: '{lang}'. Valid: {', '.join(self.VALID_LANGUAGES)}")

        # Channel
        channel = data.get("preferred_channel", "whatsapp")
        if channel not in self.VALID_CHANNELS:
            errors.append(f"Invalid channel: '{channel}'. Valid: {', '.join(self.VALID_CHANNELS)}")

        return len(errors) == 0, errors

    def validate_filing(self, pin: str, tax_type: str, period: str,
                        amount: float = 0) -> tuple[bool, list[str]]:
        """Validate filing input."""
        errors = []

        ok, msg = self.validate_pin(pin)
        if not ok:
            errors.append(msg)

        if not tax_type:
            errors.append("Tax type is required")
        elif tax_type not in self.VALID_TAX_TYPES:
            errors.append(f"Unknown tax type: '{tax_type}'")

        ok, msg = self.validate_period(period)
        if not ok:
            errors.append(msg)

        if amount < 0:
            errors.append("Amount cannot be negative")

        return len(errors) == 0, errors
