"""
NOTIFICATION ENGINE — generates alert queue entries and formats messages.
BOUNDARY: Decides WHEN and WHAT to send. Never delivers messages (v2).
"""
import json
from datetime import datetime, timedelta, timezone

from ..base import BaseAgent

# EAT = UTC+3
EAT = timezone(timedelta(hours=3))


class NotificationEngine(BaseAgent):
    name = "notification_engine"
    boundary = "Generates and formats alerts only. Never delivers messages."

    # ── Core: generate alerts ───────────────────────────────────────

    def generate_alerts(
        self, profile: dict, obligations: list[dict], urgency: dict
    ) -> list[dict]:
        """
        Check each obligation against alert_rules.json thresholds and
        produce alert entries.  Respects quiet hours and max-per-day cap.
        """
        if not urgency.get("should_alert"):
            self.log(f"No alert needed for {profile.get('pin', '?')} — urgency green")
            return []

        rules = self.load_config("alert_rules.json")
        max_per_day = rules.get("max_alerts_per_sme_per_day", 3)
        quiet = rules.get("quiet_hours", {})

        pin = profile.get("pin", "UNKNOWN")
        channel = profile.get("preferred_channel", "sms")
        lang = profile.get("preferred_language", "en")

        # How many alerts did we already send today?
        sent_today = self._count_alerts_today(pin)
        remaining = max(0, max_per_day - sent_today)
        if remaining == 0:
            self.log(f"Rate limit reached for {pin} ({max_per_day}/day)", "WARN")
            self.log_decision(
                "alert_rate_limited",
                f"SME {pin} already received {max_per_day} alerts today",
            )
            return []

        # Build one alert per actionable obligation, capped at remaining quota
        alerts: list[dict] = []
        actionable = self._filter_actionable(obligations, rules)

        for ob in actionable:
            if len(alerts) >= remaining:
                break

            scheduled_at = self._resolve_schedule(quiet)
            message = self._build_message(profile, ob, urgency, channel, lang)

            alerts.append(
                {
                    "sme_pin": pin,
                    "channel": channel,
                    "message": message,
                    "urgency_level": urgency.get("urgency_level", "yellow"),
                    "scheduled_at": scheduled_at,
                    "obligation": ob.get("tax_name", "unknown"),
                    "days_until_deadline": ob.get("days_until_deadline"),
                    "created_at": datetime.now(EAT).isoformat(),
                }
            )

        self.log(f"Generated {len(alerts)} alert(s) for {pin}")
        self.log_decision(
            "alerts_generated",
            f"{len(alerts)} alert(s) for {pin} — level {urgency.get('urgency_level')}",
        )
        return alerts

    # ── Format: WhatsApp ────────────────────────────────────────────

    def format_whatsapp(
        self, profile: dict, obligations: list[dict], urgency: dict
    ) -> str:
        """WhatsApp-style message: short, actionable, with emojis."""
        name = profile.get("name", "there").split()[0]
        lang = profile.get("preferred_language", "en")
        emoji = urgency.get("emoji", "")
        prefix = urgency.get("prefix", "")

        if lang == "sw":
            return self._wa_sw(name, obligations, emoji, prefix)
        return self._wa_en(name, obligations, emoji, prefix)

    def _wa_en(self, name: str, obligations: list, emoji: str, prefix: str) -> str:
        lines = [f"{emoji} *{prefix}* — Hi {name}!", ""]
        for ob in obligations:
            days = ob.get("days_until_deadline")
            dl = ob.get("next_deadline", "?")
            tax = ob.get("tax_name", "Tax")
            if days is not None and days < 0:
                lines.append(f"  \u274c {tax} — OVERDUE by {abs(days)} day(s)!")
            elif days is not None and days == 0:
                lines.append(f"  \u26a0\ufe0f {tax} — *DUE TODAY!*")
            elif days is not None and days <= 7:
                lines.append(f"  \u23f3 {tax} — {days} day(s) left (by {dl})")
            else:
                lines.append(f"  \u2705 {tax} — due {dl}")
        lines.append("")
        lines.append("\U0001f449 File on iTax now to avoid penalties.")
        return "\n".join(lines)

    def _wa_sw(self, name: str, obligations: list, emoji: str, prefix: str) -> str:
        lines = [f"{emoji} *{prefix}* — Habari {name}!", ""]
        for ob in obligations:
            days = ob.get("days_until_deadline")
            dl = ob.get("next_deadline", "?")
            tax = ob.get("tax_name", "Kodi")
            if days is not None and days < 0:
                lines.append(f"  \u274c {tax} — IMECHELEWA kwa siku {abs(days)}!")
            elif days is not None and days == 0:
                lines.append(f"  \u26a0\ufe0f {tax} — *INAISHA LEO!*")
            elif days is not None and days <= 7:
                lines.append(f"  \u23f3 {tax} — siku {days} zimebaki (kabla ya {dl})")
            else:
                lines.append(f"  \u2705 {tax} — tarehe {dl}")
        lines.append("")
        lines.append("\U0001f449 Wasilisha kwenye iTax sasa ili kuepuka adhabu.")
        return "\n".join(lines)

    # ── Format: SMS (<=160 chars) ───────────────────────────────────

    def format_sms(
        self, profile: dict, obligations: list[dict], urgency: dict
    ) -> str:
        """Single SMS — most urgent obligation only, under 160 chars."""
        name = profile.get("name", "").split()[0] or "SME"
        lang = profile.get("preferred_language", "en")

        # Pick the most urgent obligation (lowest days_until_deadline)
        most_urgent = min(
            obligations,
            key=lambda o: o.get("days_until_deadline", 999),
            default=None,
        )
        if most_urgent is None:
            return f"{name}: No pending tax obligations."

        tax = most_urgent.get("tax_name", "Tax")
        days = most_urgent.get("days_until_deadline")
        dl = most_urgent.get("next_deadline", "?")

        if lang == "sw":
            if days is not None and days < 0:
                msg = f"{name}: {tax} IMECHELEWA siku {abs(days)}! Wasilisha iTax sasa."
            elif days is not None and days == 0:
                msg = f"{name}: {tax} INAISHA LEO! Wasilisha iTax sasa."
            else:
                msg = f"{name}: {tax} ina siku {days} ({dl}). Wasilisha iTax mapema."
        else:
            if days is not None and days < 0:
                msg = f"{name}: {tax} is OVERDUE by {abs(days)} day(s)! File on iTax now."
            elif days is not None and days == 0:
                msg = f"{name}: {tax} is DUE TODAY! File on iTax now."
            else:
                msg = f"{name}: {tax} due in {days} day(s) ({dl}). File on iTax."

        # Hard-truncate to 160 if needed
        if len(msg) > 160:
            msg = msg[:157] + "..."
        return msg

    # ── Format: Email ───────────────────────────────────────────────

    def format_email(
        self, profile: dict, obligations: list[dict], urgency: dict
    ) -> dict:
        """Professional email with all obligations. Returns {subject, body_html, body_text}."""
        name = profile.get("name", "SME")
        business = profile.get("business_name", "your business")
        pin = profile.get("pin", "")
        prefix = urgency.get("prefix", "Tax Update")

        subject = f"[KRA Helmet] {prefix}: Tax obligations for {business}"

        # ── Plain text body ──
        text_lines = [
            f"Dear {name},",
            "",
            f"This is your tax compliance update for {business} (PIN: {pin}).",
            "",
        ]
        for ob in obligations:
            days = ob.get("days_until_deadline")
            dl = ob.get("next_deadline", "TBD")
            tax = ob.get("tax_name", "Tax")
            rate = ob.get("rate", "")
            status = ob.get("status", "").upper()
            if days is not None and days < 0:
                text_lines.append(f"  * {tax} ({rate}) — OVERDUE by {abs(days)} day(s)  [Deadline: {dl}]")
            elif days is not None and days == 0:
                text_lines.append(f"  * {tax} ({rate}) — DUE TODAY  [Deadline: {dl}]")
            else:
                text_lines.append(f"  * {tax} ({rate}) — {days} day(s) remaining  [Deadline: {dl}]  [{status}]")

        text_lines += [
            "",
            "Please file via iTax (https://itax.kra.go.ke) before the deadline to avoid penalties.",
            "",
            "---",
            "DISCLAIMER: This is an automated reminder generated by KRA Helmet.",
            "It does not constitute official KRA communication. Always verify",
            "deadlines and amounts on iTax or with a licensed tax advisor.",
            "",
            "KRA Helmet — Protecting Kenyan SMEs from tax surprises.",
        ]
        body_text = "\n".join(text_lines)

        # ── HTML body ──
        rows_html = ""
        for ob in obligations:
            days = ob.get("days_until_deadline")
            dl = ob.get("next_deadline", "TBD")
            tax = ob.get("tax_name", "Tax")
            rate = ob.get("rate", "")
            if days is not None and days < 0:
                color = "#d32f2f"
                status_cell = f"OVERDUE by {abs(days)} day(s)"
            elif days is not None and days == 0:
                color = "#e65100"
                status_cell = "DUE TODAY"
            elif days is not None and days <= 3:
                color = "#f57c00"
                status_cell = f"{days} day(s) left"
            elif days is not None and days <= 7:
                color = "#fbc02d"
                status_cell = f"{days} day(s) left"
            else:
                color = "#388e3c"
                status_cell = f"{days} day(s) left" if days is not None else "N/A"

            rows_html += (
                f'<tr><td>{tax}</td><td>{rate}</td><td>{dl}</td>'
                f'<td style="color:{color};font-weight:bold">{status_cell}</td></tr>\n'
            )

        body_html = f"""\
<html><body style="font-family:sans-serif;color:#222">
<h2>Tax Compliance Update</h2>
<p>Dear {name},</p>
<p>Here is your tax compliance summary for <strong>{business}</strong> (PIN: {pin}).</p>
<table border="1" cellpadding="6" cellspacing="0" style="border-collapse:collapse;width:100%;max-width:600px">
<tr style="background:#f5f5f5"><th>Tax</th><th>Rate</th><th>Deadline</th><th>Status</th></tr>
{rows_html}</table>
<p>Please file via <a href="https://itax.kra.go.ke">iTax</a> before the deadline to avoid penalties.</p>
<hr>
<p style="font-size:0.85em;color:#888">
DISCLAIMER: This is an automated reminder generated by KRA Helmet.
It does not constitute official KRA communication. Always verify
deadlines and amounts on iTax or with a licensed tax advisor.
</p>
</body></html>"""

        return {"subject": subject, "body_html": body_html, "body_text": body_text}

    # ── Persist: save alert queue ───────────────────────────────────

    def save_alert_queue(self, alerts: list[dict]):
        """Save each alert as a JSON file under staging/alerts/."""
        if not alerts:
            self.log("No alerts to save")
            return

        for alert in alerts:
            pin = alert.get("sme_pin", "UNKNOWN")
            ts = datetime.now(EAT).strftime("%Y%m%d_%H%M%S_%f")
            filename = f"alert_{pin}_{ts}.json"
            self.write_staging("alerts", filename, alert)

        self.log(f"Saved {len(alerts)} alert(s) to staging/alerts/")

    # ── Private helpers ─────────────────────────────────────────────

    def _filter_actionable(self, obligations: list[dict], rules: dict) -> list[dict]:
        """Return obligations that warrant an alert, sorted most-urgent first."""
        levels = rules.get("urgency_levels", {})

        # Anything with days_until_deadline <= 7 (yellow threshold) is actionable
        yellow_threshold = levels.get("yellow", {}).get("days_before_deadline", 7)
        actionable = [
            o for o in obligations
            if o.get("days_until_deadline") is not None
            and o["days_until_deadline"] <= yellow_threshold
        ]
        # Most urgent first
        actionable.sort(key=lambda o: o.get("days_until_deadline", 999))
        return actionable

    def _resolve_schedule(self, quiet: dict) -> str:
        """
        If current time falls in quiet hours (21:00-07:00 EAT),
        schedule the alert for 07:00 next day.  Otherwise, schedule now.
        """
        now = datetime.now(EAT)
        quiet_start_h, quiet_start_m = (
            int(x) for x in quiet.get("start", "21:00").split(":")
        )
        quiet_end_h, quiet_end_m = (
            int(x) for x in quiet.get("end", "07:00").split(":")
        )

        current_minutes = now.hour * 60 + now.minute
        start_minutes = quiet_start_h * 60 + quiet_start_m
        end_minutes = quiet_end_h * 60 + quiet_end_m

        in_quiet = False
        if start_minutes > end_minutes:
            # Quiet hours span midnight (e.g. 21:00-07:00)
            in_quiet = current_minutes >= start_minutes or current_minutes < end_minutes
        else:
            in_quiet = start_minutes <= current_minutes < end_minutes

        if in_quiet:
            # Schedule for 07:00 next day (or today if before 07:00)
            next_send = now.replace(
                hour=quiet_end_h, minute=quiet_end_m, second=0, microsecond=0
            )
            if next_send <= now:
                next_send += timedelta(days=1)
            self.log(f"Quiet hours — alert scheduled for {next_send.isoformat()}")
            return next_send.isoformat()

        return now.isoformat()

    def _count_alerts_today(self, pin: str) -> int:
        """Count how many alerts were already queued today for this SME."""
        alerts_dir = self.staging / "alerts"
        if not alerts_dir.exists():
            return 0

        today_prefix = f"alert_{pin}_{datetime.now(EAT).strftime('%Y%m%d')}"
        count = 0
        for f in alerts_dir.iterdir():
            if f.name.startswith(today_prefix) and f.suffix == ".json":
                count += 1
        return count

    def _build_message(
        self,
        profile: dict,
        obligation: dict,
        urgency: dict,
        channel: str,
        lang: str,
    ) -> str:
        """Build a message string for a single obligation on the given channel."""
        if channel == "whatsapp":
            return self.format_whatsapp(profile, [obligation], urgency)
        elif channel == "email":
            email = self.format_email(profile, [obligation], urgency)
            return email.get("body_text", "")
        else:
            # Default to SMS for sms and any other channel
            return self.format_sms(profile, [obligation], urgency)
