"""
EXPLAINER — converts agent output into plain language for the SME.
BOUNDARY: translates only. Never adds new information.
"""
from ..base import BaseAgent


class Explainer(BaseAgent):
    name = "explainer"
    boundary = "Translates only. Never adds new information."

    def explain(self, validated: dict) -> str:
        """Generate a plain-language summary for the SME."""
        profile = validated["profile"]
        obligations = validated["obligations"]
        compliance = validated["compliance"]
        risk = validated["risk"]
        lang = profile.get("preferred_language", "en")

        name = profile.get("name", "there")
        business = profile.get("business_name", "your business")

        if lang == "sw":
            return self._explain_sw(name, business, obligations, compliance, risk)
        return self._explain_en(name, business, obligations, compliance, risk)

    def _explain_en(self, name, business, obligations, compliance, risk) -> str:
        lines = [f"Hi {name},", f"Here's your tax compliance summary for {business}:", ""]

        # Compliance status
        status = compliance["overall"]
        if status == "compliant":
            lines.append("STATUS: All clear — you're on track.")
        elif status == "at_risk":
            lines.append("STATUS: Attention needed — you have deadlines coming up soon.")
        else:
            lines.append("STATUS: ACTION REQUIRED — you have overdue filings!")

        lines.append("")

        # Obligations breakdown
        lines.append(f"You have {len(obligations)} tax obligation(s):")
        for ob in obligations:
            dl = ob.get("next_deadline", "unknown")
            days = ob.get("days_until_deadline")
            status_tag = ob.get("status", "").upper()
            rate = ob.get("rate", "")

            line = f"  - {ob['tax_name']} ({rate})"
            if days is not None:
                if days < 0:
                    line += f" — OVERDUE by {abs(days)} day(s)!"
                elif days == 0:
                    line += " — DUE TODAY!"
                elif days <= 3:
                    line += f" — due in {days} day(s) [{status_tag}]"
                else:
                    line += f" — due {dl} ({days} days)"
            lines.append(line)

        lines.append("")

        # Risk
        risk_score = risk.get("risk_score", 0)
        risk_level = risk.get("risk_level", "low")
        lines.append(f"AUDIT RISK: {risk_score}/100 ({risk_level})")
        for factor in risk.get("factors", []):
            lines.append(f"  {factor}")

        lines.append("")

        # Next action
        lines.append(f"NEXT STEP: {compliance.get('next_action', 'No action needed.')}")
        lines.append("")
        lines.append(compliance.get("disclaimer", ""))

        return "\n".join(lines)

    def _explain_sw(self, name, business, obligations, compliance, risk) -> str:
        lines = [f"Habari {name},", f"Hii ni muhtasari wa kodi yako kwa {business}:", ""]

        status = compliance["overall"]
        if status == "compliant":
            lines.append("HALI: Sawa — uko sawa.")
        elif status == "at_risk":
            lines.append("HALI: Tahadhari — una tarehe za mwisho zinakaribia.")
        else:
            lines.append("HALI: HATUA INAHITAJIKA — una majalada yaliyochelewa!")

        lines.append("")
        lines.append(f"Una majukumu {len(obligations)} ya kodi:")

        for ob in obligations:
            days = ob.get("days_until_deadline")
            line = f"  - {ob['tax_name']}"
            if days is not None:
                if days < 0:
                    line += f" — IMECHELEWA kwa siku {abs(days)}!"
                elif days == 0:
                    line += " — INAISHA LEO!"
                elif days <= 3:
                    line += f" — siku {days} zimebaki"
                else:
                    line += f" — tarehe {ob.get('next_deadline', '?')} (siku {days})"
            lines.append(line)

        lines.append("")
        lines.append(f"HATARI YA UKAGUZI: {risk.get('risk_score', 0)}/100 ({risk.get('risk_level', 'chini')})")
        lines.append("")
        lines.append(f"HATUA INAYOFUATA: {compliance.get('next_action', 'Hakuna hatua inayohitajika.')}")
        lines.append("")
        lines.append(compliance.get("disclaimer", ""))

        return "\n".join(lines)
