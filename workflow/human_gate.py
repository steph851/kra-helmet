"""
HUMAN GATE — approve / reject / escalate interface.
Nothing high-risk happens without human eyes.
"""
import json
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).parent.parent


class HumanGate:
    def __init__(self):
        self.review_dir = ROOT / "staging" / "review"
        self.logs_dir = ROOT / "logs"

    def review_pending(self) -> list[str]:
        """List all items pending human review."""
        if not self.review_dir.exists():
            return []
        return [f.name for f in self.review_dir.glob("*.json")]

    def show_item(self, filename: str) -> dict | None:
        """Display an item for review."""
        path = self.review_dir / filename
        if not path.exists():
            print(f"Not found: {filename}")
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        print(json.dumps(data, indent=2, ensure_ascii=False))
        return data

    def approve(self, filename: str, reviewer: str = "Steph") -> bool:
        """Approve an item — move from staging to confirmed."""
        path = self.review_dir / filename
        if not path.exists():
            print(f"Not found: {filename}")
            return False

        data = json.loads(path.read_text(encoding="utf-8"))
        data["_approved"] = True
        data["_approved_by"] = reviewer
        data["_approved_at"] = datetime.now().isoformat()

        # Move to confirmed
        confirmed_path = ROOT / "data" / "confirmed" / filename
        confirmed_path.parent.mkdir(parents=True, exist_ok=True)
        confirmed_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

        # Remove from review
        path.unlink()

        self._log_decision(filename, "APPROVED", reviewer)
        print(f"APPROVED: {filename} by {reviewer}")
        return True

    def reject(self, filename: str, reason: str, reviewer: str = "Steph") -> bool:
        """Reject an item — log and remove from queue."""
        path = self.review_dir / filename
        if not path.exists():
            print(f"Not found: {filename}")
            return False

        path.unlink()
        self._log_decision(filename, f"REJECTED: {reason}", reviewer)
        print(f"REJECTED: {filename} — {reason}")
        return True

    def interactive_review(self):
        """CLI interface for reviewing pending items."""
        pending = self.review_pending()
        if not pending:
            print("No items pending review.")
            return

        print(f"\n{'='*60}")
        print(f"  HUMAN GATE — {len(pending)} item(s) pending review")
        print(f"{'='*60}\n")

        for i, filename in enumerate(pending, 1):
            print(f"  {i}. {filename}")

        print()
        choice = input("  Enter number to review (or 'q' to quit): ").strip()
        if choice.lower() == 'q':
            return

        try:
            idx = int(choice) - 1
            filename = pending[idx]
        except (ValueError, IndexError):
            print("Invalid choice.")
            return

        print(f"\n--- Reviewing: {filename} ---\n")
        self.show_item(filename)

        print("\n  [a] Approve  [r] Reject  [s] Skip")
        action = input("  Action: ").strip().lower()

        if action == "a":
            self.approve(filename)
        elif action == "r":
            reason = input("  Rejection reason: ").strip()
            self.reject(filename, reason)
        else:
            print("Skipped.")

    def _log_decision(self, item: str, decision: str, reviewer: str):
        entry = f"[{datetime.now().isoformat()}] {decision} | {item} | by {reviewer}\n"
        log_path = self.logs_dir / "human_gate.log"
        log_path.parent.mkdir(exist_ok=True)
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(entry)
