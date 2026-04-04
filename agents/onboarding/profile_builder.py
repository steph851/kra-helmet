"""
PROFILE BUILDER — interviews SME via CLI and builds their tax profile.
BOUNDARY: asks questions only. Never maps obligations.
"""
from datetime import datetime
from ..base import BaseAgent
from ..validation.input_validator import InputValidator


class ProfileBuilder(BaseAgent):
    name = "profile_builder"
    boundary = "Asks questions only. Never maps obligations or calculates tax."

    def build_profile_interactive(self) -> dict | None:
        """Run CLI interview to build an SME profile."""
        self.log("Starting SME onboarding interview")
        print("\n" + "=" * 60)
        print("  KRA Deadline Tracker — SME Onboarding")
        print("  Answer the questions below to set up your tax profile.")
        print("=" * 60 + "\n")

        validator = InputValidator()

        try:
            pin = self._ask("KRA PIN (e.g. A123456789B)").strip().upper()
            ok, msg = validator.validate_pin(pin)
            if not ok:
                print(f"Invalid PIN: {msg}")
                return None
            pin = msg  # Use cleaned PIN

            name = self._ask("Your full name")
            business_name = self._ask("Business name (or press Enter if same as above)") or name
            phone = self._ask("M-Pesa phone number (e.g. 0712345678)")

            print("\nBusiness type:")
            print("  1. Sole Proprietor (sole owner)")
            print("  2. Partnership (2+ owners)")
            print("  3. Limited Company (registered at RoC)")
            btype = self._ask("Choose (1/2/3)")
            business_type = {"1": "sole_proprietor", "2": "partnership", "3": "limited_company"}.get(btype, "sole_proprietor")

            print("\nWhat industry is your business in?")
            industries = [
                "retail_wholesale", "professional_services", "food_hospitality",
                "transport", "manufacturing", "rental_income", "digital_online",
                "construction", "agriculture", "salon_beauty", "education", "healthcare"
            ]
            for i, ind in enumerate(industries, 1):
                print(f"  {i:2}. {ind.replace('_', ' ').title()}")
            ind_choice = self._ask("Choose number")
            try:
                industry = industries[int(ind_choice) - 1]
            except (ValueError, IndexError):
                industry = "retail_wholesale"

            county = self._ask("County (e.g. Nairobi, Mombasa, Nakuru)")

            print("\nEstimated annual turnover (KES):")
            print("  1. Below 1 million")
            print("  2. 1M to 8M")
            print("  3. 8M to 25M")
            print("  4. Above 25M")
            turnover_choice = self._ask("Choose (1/2/3/4)")
            turnover_map = {"1": 500000, "2": 4000000, "3": 15000000, "4": 30000000}
            bracket_map = {"1": "below_1m", "2": "1m_to_8m", "3": "8m_to_25m", "4": "above_25m"}
            annual_turnover = turnover_map.get(turnover_choice, 500000)
            turnover_bracket = bracket_map.get(turnover_choice, "below_1m")

            has_employees = self._ask("Do you have employees? (y/n)").lower().startswith("y")
            employee_count = None
            if has_employees:
                try:
                    employee_count = int(self._ask("How many employees?"))
                except ValueError:
                    employee_count = 1

            is_vat = self._ask("Are you VAT registered? (y/n)").lower().startswith("y")
            has_etims = self._ask("Do you use eTIMS for invoicing? (y/n)").lower().startswith("y")

            rental = self._ask("Do you earn rental income? (y/n)").lower().startswith("y")
            rental_income = None
            if rental:
                try:
                    rental_income = float(self._ask("Annual rental income (KES)"))
                except ValueError:
                    rental_income = None

            email = self._ask("Email address (or press Enter to skip)") or None

            lang = self._ask("Preferred language — English (en) or Swahili (sw)?").lower()
            if lang not in ("en", "sw"):
                lang = "en"

            channel = self._ask("Preferred alerts — WhatsApp (w), SMS (s), or Email (e)?").lower()
            channel_map = {"w": "whatsapp", "s": "sms", "e": "email"}
            preferred_channel = channel_map.get(channel, "whatsapp")

        except (KeyboardInterrupt, EOFError):
            print("\nOnboarding cancelled.")
            return None

        profile = {
            "pin": pin,
            "name": name,
            "business_name": business_name,
            "business_type": business_type,
            "industry": industry,
            "county": county,
            "sub_county": None,
            "annual_turnover_kes": annual_turnover,
            "turnover_bracket": turnover_bracket,
            "has_employees": has_employees,
            "employee_count": employee_count,
            "is_vat_registered": is_vat,
            "has_etims": has_etims,
            "rental_income_annual_kes": rental_income,
            "phone": phone,
            "email": email,
            "preferred_language": lang,
            "preferred_channel": preferred_channel,
            "onboarded_at": datetime.now().isoformat(),
            "last_updated": datetime.now().isoformat(),
        }

        self.log(f"Profile built for {name} (PIN: {pin})")
        return profile

    def build_profile_from_data(self, data: dict) -> dict:
        """Build profile from a pre-filled dict (for batch/API onboarding)."""
        now = datetime.now().isoformat()
        defaults = {
            "sub_county": None,
            "employee_count": None,
            "rental_income_annual_kes": None,
            "email": None,
            "preferred_language": "en",
            "preferred_channel": "whatsapp",
            "onboarded_at": now,
            "last_updated": now,
        }
        profile = {**defaults, **data}
        self.log(f"Profile built for {profile.get('name', 'unknown')} (PIN: {profile.get('pin', '?')})")
        return profile

    def _ask(self, question: str) -> str:
        return input(f"  {question}: ")
