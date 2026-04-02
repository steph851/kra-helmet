"""
ITAX CONNECTOR — provides filing guidance and deadline information.
BOUNDARY: Reads public iTax pages and provides guidance. Never logs into iTax or submits filings.
Uses web scraping for public deadline pages and filing guides.
"""
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import sys
ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

from tools.web_reader import WebReader

EAT = timezone(timedelta(hours=3))


class ITaxConnector:
    """iTax filing guidance and deadline information."""

    # iTax public pages
    DEADLINES_URL = "https://www.kra.go.ke/individual/filing-paying/filing-deadlines"
    RATES_URL = "https://www.kra.go.ke/individual/filing-paying/types-of-taxes"

    def __init__(self):
        self.reader = WebReader(timeout=20, max_retries=3)
        self._guides_path = ROOT / "intelligence" / "filing_guides.json"
        self._calendar_path = ROOT / "intelligence" / "deadline_calendar.json"

    def get_filing_guide(self, tax_type: str) -> dict | None:
        """Get filing guide for a specific tax type."""
        if not self._guides_path.exists():
            return None

        try:
            data = json.loads(self._guides_path.read_text(encoding="utf-8"))
            for guide in data.get("filing_guides", []):
                if guide.get("tax_key") == tax_type:
                    return guide
        except (json.JSONDecodeError, KeyError):
            pass
        return None

    def get_all_guides(self) -> list[dict]:
        """Get all available filing guides."""
        if not self._guides_path.exists():
            return []

        try:
            data = json.loads(self._guides_path.read_text(encoding="utf-8"))
            return data.get("filing_guides", [])
        except (json.JSONDecodeError, KeyError):
            return []

    def get_deadline_calendar(self) -> dict:
        """Get deadline calendar with holidays and buffer days."""
        if not self._calendar_path.exists():
            return {}

        try:
            return json.loads(self._calendar_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, KeyError):
            return {}

    def fetch_deadlines_page(self) -> str | None:
        """Fetch current deadlines from KRA website."""
        result = self.reader.fetch(self.DEADLINES_URL)
        if result.ok:
            return result.text
        return None

    def fetch_rates_page(self) -> str | None:
        """Fetch current tax rates from KRA website."""
        result = self.reader.fetch(self.RATES_URL)
        if result.ok:
            return result.text
        return None

    def get_itax_steps(self, tax_type: str) -> list[str]:
        """Get iTax filing steps for a tax type."""
        guide = self.get_filing_guide(tax_type)
        if guide:
            return guide.get("steps", [])
        return []

    def get_documents_needed(self, tax_type: str) -> list[str]:
        """Get documents needed for filing a tax type."""
        guide = self.get_filing_guide(tax_type)
        if guide:
            return guide.get("documents_needed", [])
        return []

    def get_common_mistakes(self, tax_type: str) -> list[str]:
        """Get common mistakes for a tax type."""
        guide = self.get_filing_guide(tax_type)
        if guide:
            return guide.get("common_mistakes", [])
        return []

    def get_tips(self, tax_type: str) -> list[str]:
        """Get tips for filing a tax type."""
        guide = self.get_filing_guide(tax_type)
        if guide:
            return guide.get("tips", [])
        return []

    def get_itax_menu_path(self, tax_type: str) -> str:
        """Get iTax menu navigation path for a tax type."""
        guide = self.get_filing_guide(tax_type)
        if guide:
            return guide.get("itax_menu_path", "")
        return ""

    def get_estimated_time(self, tax_type: str) -> str:
        """Get estimated filing time for a tax type."""
        guide = self.get_filing_guide(tax_type)
        if guide:
            return guide.get("estimated_time", "")
        return ""

    def check_health(self) -> dict:
        """Check iTax connector health."""
        return {
            "guides_loaded": self._guides_path.exists(),
            "calendar_loaded": self._calendar_path.exists(),
            "guides_count": len(self.get_all_guides()),
            "deadlines_url": self.DEADLINES_URL,
            "rates_url": self.RATES_URL,
        }
