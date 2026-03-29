"""
DEADLINE CALCULATOR — calculates exact filing deadlines per SME.
Accounts for public holidays, weekends, iTax downtime buffer.
BOUNDARY: calculates dates only. Never scores risk.
"""
from datetime import date, datetime, timedelta
from ..base import BaseAgent


class DeadlineCalculator(BaseAgent):
    name = "deadline_calculator"
    boundary = "Calculates dates only. Never scores risk."

    def __init__(self):
        super().__init__()
        cal = self.load_intel("deadline_calendar.json")
        self._holidays = set()
        for h in cal.get("public_holidays_2026", []):
            try:
                self._holidays.add(date.fromisoformat(h["date"]))
            except (ValueError, KeyError):
                pass
        self._itax_buffer = cal.get("itax_known_downtime", {}).get("recommendation_buffer_days", 3)
        self._monthly_deadlines = cal.get("filing_deadlines_monthly", {})

    def calculate_deadlines(self, obligations: list[dict], as_of: date | None = None) -> list[dict]:
        """Calculate next deadline for each obligation. Returns enriched obligation list."""
        today = as_of or date.today()
        self.log(f"Calculating deadlines as of {today}")

        results = []
        for ob in obligations:
            enriched = dict(ob)
            freq = ob.get("frequency", "unknown")

            if freq == "monthly":
                deadline_day = ob.get("deadline_day")
                if not deadline_day:
                    # Look up from calendar config
                    tax_key = ob["tax_type"].split("_withholding")[0]  # strip WHT suffix
                    cfg = self._monthly_deadlines.get(tax_key, {})
                    deadline_day = cfg.get("day", 20)

                next_dl = self._next_monthly_deadline(today, deadline_day)
                enriched["next_deadline"] = next_dl.isoformat()
                enriched["recommended_file_by"] = (next_dl - timedelta(days=self._itax_buffer)).isoformat()
                enriched["days_until_deadline"] = (next_dl - today).days
                enriched["filing_month"] = self._filing_month_label(next_dl, deadline_day)

            elif freq == "annual":
                next_dl = self._next_annual_deadline(today, ob)
                enriched["next_deadline"] = next_dl.isoformat()
                enriched["recommended_file_by"] = (next_dl - timedelta(days=self._itax_buffer)).isoformat()
                enriched["days_until_deadline"] = (next_dl - today).days

            else:
                enriched["next_deadline"] = None
                enriched["days_until_deadline"] = None

            # Set urgency status
            days = enriched.get("days_until_deadline")
            if days is not None:
                if days < 0:
                    enriched["status"] = "overdue"
                elif days <= 1:
                    enriched["status"] = "critical"
                elif days <= 3:
                    enriched["status"] = "urgent"
                elif days <= 7:
                    enriched["status"] = "due_soon"
                else:
                    enriched["status"] = "upcoming"

            results.append(enriched)

        self.log(f"Calculated {len(results)} deadlines")
        return results

    def _next_monthly_deadline(self, today: date, day: int) -> date:
        """Find the next filing deadline for a monthly obligation."""
        # Monthly filings are for the PREVIOUS month, due on day of CURRENT month
        # If today is past the deadline day this month, next deadline is next month
        try:
            this_month = today.replace(day=day)
        except ValueError:
            # Day doesn't exist in this month (e.g. Feb 30) — use last day
            import calendar
            last = calendar.monthrange(today.year, today.month)[1]
            this_month = today.replace(day=min(day, last))

        if today <= this_month:
            dl = this_month
        else:
            # Move to next month
            if today.month == 12:
                dl = date(today.year + 1, 1, day)
            else:
                import calendar
                next_m = today.month + 1
                last = calendar.monthrange(today.year, next_m)[1]
                dl = date(today.year, next_m, min(day, last))

        return self._adjust_for_holidays(dl)

    def _next_annual_deadline(self, today: date, ob: dict) -> date:
        """Find the next annual filing deadline."""
        deadline_str = ob.get("deadline_date", "")
        if "June 30" in str(deadline_str) or "30 June" in str(deadline_str):
            this_year = date(today.year, 6, 30)
            dl = this_year if today <= this_year else date(today.year + 1, 6, 30)
        else:
            # Default to end of year
            this_year = date(today.year, 12, 31)
            dl = this_year if today <= this_year else date(today.year + 1, 12, 31)

        return self._adjust_for_holidays(dl)

    def _adjust_for_holidays(self, dl: date) -> date:
        """If deadline falls on weekend or public holiday, push to next business day."""
        while dl.weekday() >= 5 or dl in self._holidays:  # 5=Sat, 6=Sun
            dl += timedelta(days=1)
        return dl

    def _filing_month_label(self, deadline: date, deadline_day: int) -> str:
        """Returns which month the filing covers (the month BEFORE the deadline)."""
        if deadline.month == 1:
            return f"December {deadline.year - 1}"
        else:
            import calendar
            return f"{calendar.month_name[deadline.month - 1]} {deadline.year}"
