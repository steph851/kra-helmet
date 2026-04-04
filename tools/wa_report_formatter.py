"""
WhatsApp Report Formatter — turns compliance check results into WhatsApp-friendly messages.
"""


def format_compliance_report(result: dict) -> str:
    """Format a full compliance check result for WhatsApp delivery."""
    profile = result.get("profile", {})
    name = profile.get("name", "there").split()[0]
    pin = profile.get("pin", "?")
    compliance = result.get("compliance", {})
    risk = result.get("risk", {})
    obligations = result.get("obligations", [])
    penalties = result.get("penalties", {})
    urgency = result.get("urgency", {})

    status = compliance.get("overall", "unknown")
    status_emoji = {"compliant": "\u2705", "at_risk": "\u26a0\ufe0f", "non_compliant": "\u274c"}.get(status, "\u2753")
    risk_score = risk.get("risk_score", 0)
    risk_level = risk.get("risk_level", "unknown")

    lines = [
        f"*KRA Deadline Tracker — Compliance Report*",
        f"*{name}* ({pin})",
        "",
        f"{status_emoji} Status: *{status.replace('_', ' ').upper()}*",
        f"Risk: *{risk_score}/100* ({risk_level})",
        "",
        "*Upcoming Deadlines:*",
    ]

    for ob in obligations:
        days = ob.get("days_until_deadline")
        dl = ob.get("next_deadline", "?")
        tax = ob.get("tax_name", ob.get("tax_type", "Tax"))

        if days is not None and days < 0:
            lines.append(f"  \u274c {tax} — *OVERDUE* by {abs(days)} day(s)!")
        elif days is not None and days == 0:
            lines.append(f"  \u26a0\ufe0f {tax} — *DUE TODAY!*")
        elif days is not None and days <= 3:
            lines.append(f"  \U0001f534 {tax} — {days} day(s) left (by {dl})")
        elif days is not None and days <= 7:
            lines.append(f"  \U0001f7e0 {tax} — {days} day(s) left (by {dl})")
        else:
            lines.append(f"  \u2705 {tax} — due {dl}")

    # Penalties
    total_penalty = penalties.get("total_penalty_exposure_kes", 0)
    if total_penalty > 0:
        lines.append("")
        lines.append(f"*Penalty Exposure:* KES {total_penalty:,.0f}")
        severity = penalties.get("severity", "")
        if severity:
            lines.append(f"Severity: {severity}")

    # Risk factors
    factors = risk.get("factors", [])
    if factors:
        lines.append("")
        lines.append("*Risk Factors:*")
        for f in factors[:5]:
            lines.append(f"  - {f}")

    # Next action
    next_action = compliance.get("next_action", "")
    if next_action:
        lines.append("")
        lines.append(f"*Next Action:* {next_action}")

    lines.append("")
    lines.append("*Two ways to file:*")
    lines.append("1\ufe0f\u20e3 iTax: https://itax.kra.go.ke")
    lines.append("2\ufe0f\u20e3 WhatsApp: Send 'Hi' to +254711099999")
    lines.append("")
    lines.append("_This is automated guidance only. Verify with KRA._")

    return "\n".join(lines)


def format_deadline_alert(profile: dict, obligation: dict) -> str:
    """Format a single deadline alert for WhatsApp."""
    name = profile.get("name", "there").split()[0]
    tax = obligation.get("tax_name", obligation.get("tax_type", "Tax"))
    days = obligation.get("days_until_deadline", 0)
    dl = obligation.get("next_deadline", "?")

    if days < 0:
        emoji = "\u274c"
        status = f"OVERDUE by {abs(days)} day(s)"
    elif days == 0:
        emoji = "\u26a0\ufe0f"
        status = "DUE TODAY"
    elif days <= 3:
        emoji = "\U0001f534"
        status = f"{days} day(s) left"
    else:
        emoji = "\u23f3"
        status = f"{days} day(s) left"

    return (
        f"{emoji} *{tax} — {status}*\n\n"
        f"Hi {name}, your {tax} is due by *{dl}*.\n\n"
        f"File now:\n"
        f"- iTax: https://itax.kra.go.ke\n"
        f"- WhatsApp: Send 'Hi' to +254711099999\n\n"
        f"_KRA Deadline Tracker — keeping you compliant_"
    )


def format_payment_confirmation(profile: dict, plan_name: str, expires_at: str) -> str:
    """Format payment confirmation message."""
    name = profile.get("name", "there").split()[0]
    return (
        f"\u2705 *Payment Received!*\n\n"
        f"Hi {name}, your *{plan_name}* subscription is now active.\n"
        f"Expires: {expires_at[:10]}\n\n"
        f"You'll receive:\n"
        f"- Deadline alerts before due dates\n"
        f"- Compliance reports with risk scoring\n"
        f"- Filing instructions via WhatsApp\n\n"
        f"_KRA Deadline Tracker — taxes payment made easy_"
    )
