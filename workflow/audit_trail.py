"""
AUDIT TRAIL — immutable log of every decision. Legally defensible.
"""
import json
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).parent.parent


class AuditTrail:
    def __init__(self):
        self.log_path = ROOT / "logs" / "audit_trail.jsonl"
        self.log_path.parent.mkdir(exist_ok=True)

    def record(self, event_type: str, agent: str, details: dict, sme_pin: str | None = None):
        """Record an immutable audit entry."""
        entry = {
            "timestamp": datetime.now().isoformat(),
            "event_type": event_type,
            "agent": agent,
            "sme_pin": sme_pin,
            "details": details,
        }
        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def get_history(self, sme_pin: str | None = None, limit: int = 50) -> list[dict]:
        """Retrieve audit history, optionally filtered by SME PIN."""
        if not self.log_path.exists():
            return []

        entries = []
        with open(self.log_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    if sme_pin is None or entry.get("sme_pin") == sme_pin:
                        entries.append(entry)
                except json.JSONDecodeError:
                    continue

        return entries[-limit:]  # most recent

    def print_history(self, sme_pin: str | None = None, limit: int = 20):
        """Print formatted audit history."""
        entries = self.get_history(sme_pin, limit)
        if not entries:
            print("No audit history found.")
            return

        print(f"\n{'='*70}")
        print(f"  AUDIT TRAIL{f' — {sme_pin}' if sme_pin else ''}")
        print(f"{'='*70}")

        for e in entries:
            ts = e["timestamp"][:19]
            print(f"  [{ts}] {e['event_type']} | {e['agent']} | {e.get('sme_pin', '-')}")
            if e.get("details"):
                for k, v in e["details"].items():
                    print(f"    {k}: {v}")
            print()
