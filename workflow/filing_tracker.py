"""
FILING TRACKER — records when an SME has filed a tax return.
Tracks filing history and updates compliance state.
"""
import json
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).parent.parent


class FilingTracker:
    def __init__(self):
        self.filings_dir = ROOT / "data" / "filings"
        self.filings_dir.mkdir(parents=True, exist_ok=True)

    def record_filing(self, pin: str, tax_type: str, period: str,
                      amount_kes: float = 0, reference: str = "",
                      recorder: str = "Steph") -> dict:
        """Record that an SME filed a specific tax return.

        Args:
            pin: KRA PIN
            tax_type: e.g. 'turnover_tax', 'paye', 'vat'
            period: Filing period e.g. '2026-03' for March 2026
            amount_kes: Amount paid
            reference: KRA receipt/reference number
            recorder: Who recorded this filing
        """
        entry = {
            "pin": pin,
            "tax_type": tax_type,
            "period": period,
            "amount_kes": amount_kes,
            "reference": reference,
            "filed_at": datetime.now().isoformat(),
            "recorded_by": recorder,
        }

        # Append to per-SME filing log
        log_path = self.filings_dir / f"{pin}.jsonl"
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

        print(f"  Filed: {tax_type} for {period} — KES {amount_kes:,.0f}")
        return entry

    def get_filings(self, pin: str, tax_type: str | None = None,
                    limit: int = 50) -> list[dict]:
        """Get filing history for an SME."""
        log_path = self.filings_dir / f"{pin}.jsonl"
        if not log_path.exists():
            return []

        entries = []
        with open(log_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    if tax_type is None or entry.get("tax_type") == tax_type:
                        entries.append(entry)
                except json.JSONDecodeError:
                    continue

        return entries[-limit:]

    def is_filed(self, pin: str, tax_type: str, period: str) -> bool:
        """Check if a specific filing has been made."""
        filings = self.get_filings(pin, tax_type)
        return any(f["period"] == period for f in filings)

    def get_filing_summary(self, pin: str) -> dict:
        """Get a summary of all filings for an SME."""
        filings = self.get_filings(pin)
        if not filings:
            return {"total_filings": 0, "total_paid_kes": 0, "tax_types": {}}

        by_type = {}
        total_paid = 0
        for f in filings:
            tt = f["tax_type"]
            if tt not in by_type:
                by_type[tt] = {"count": 0, "total_kes": 0, "last_period": None}
            by_type[tt]["count"] += 1
            by_type[tt]["total_kes"] += f.get("amount_kes", 0)
            by_type[tt]["last_period"] = f["period"]
            total_paid += f.get("amount_kes", 0)

        return {
            "total_filings": len(filings),
            "total_paid_kes": total_paid,
            "tax_types": by_type,
        }

    def print_history(self, pin: str, tax_type: str | None = None):
        """Print formatted filing history."""
        filings = self.get_filings(pin, tax_type)
        if not filings:
            print(f"\n  No filings recorded for {pin}.")
            print(f"  Use 'python run.py file {pin} <tax_type> <period>' to record one.\n")
            return

        print(f"\n{'='*70}")
        print(f"  FILING HISTORY — {pin}")
        if tax_type:
            print(f"  Filter: {tax_type}")
        print(f"{'='*70}")

        for f in filings:
            ts = f["filed_at"][:16]
            amt = f.get("amount_kes", 0)
            ref = f.get("reference", "")
            ref_str = f" | Ref: {ref}" if ref else ""
            print(f"  [{ts}] {f['tax_type']:25s} | {f['period']} | KES {amt:>12,.0f}{ref_str}")

        summary = self.get_filing_summary(pin)
        print(f"\n  Total filings: {summary['total_filings']} | Total paid: KES {summary['total_paid_kes']:,.0f}")
        print()

    def interactive_file(self, pin: str):
        """Interactive CLI for recording a filing."""
        print(f"\n{'='*60}")
        print(f"  Record Filing — {pin}")
        print(f"{'='*60}\n")

        # Load the SME's obligations to show options
        obligations_path = ROOT / "data" / "processed" / "obligations" / f"{pin}.json"
        if obligations_path.exists():
            report = json.loads(obligations_path.read_text(encoding="utf-8"))
            obligations = report.get("obligations", [])
            if obligations:
                print("  Your obligations:")
                for i, ob in enumerate(obligations, 1):
                    filed_mark = ""
                    if ob.get("filing_month"):
                        period = self._month_to_period(ob["filing_month"])
                        if self.is_filed(pin, ob["tax_type"], period):
                            filed_mark = " [FILED]"
                    print(f"    {i}. {ob['tax_name']} — due {ob.get('next_deadline', '?')}{filed_mark}")
                print()

                try:
                    choice = input("  Choose obligation number (or 'q' to quit): ").strip()
                    if choice.lower() == 'q':
                        return
                    idx = int(choice) - 1
                    ob = obligations[idx]
                except (ValueError, IndexError):
                    print("  Invalid choice.")
                    return

                tax_type = ob["tax_type"]
                period = self._month_to_period(ob.get("filing_month", ""))
            else:
                tax_type = input("  Tax type (e.g. turnover_tax): ").strip()
                period = input("  Period (e.g. 2026-03): ").strip()
        else:
            tax_type = input("  Tax type (e.g. turnover_tax): ").strip()
            period = input("  Period (e.g. 2026-03): ").strip()

        period = input(f"  Period [{period}]: ").strip() or period

        try:
            amount = float(input("  Amount paid (KES): ").strip() or "0")
        except ValueError:
            amount = 0

        reference = input("  KRA receipt/reference (or Enter to skip): ").strip()

        if self.is_filed(pin, tax_type, period):
            print(f"\n  Already filed: {tax_type} for {period}")
            overwrite = input("  Record again? (y/n): ").strip().lower()
            if not overwrite.startswith("y"):
                return

        self.record_filing(pin, tax_type, period, amount, reference)
        print(f"\n  Recorded: {tax_type} for {period} — KES {amount:,.0f}")

    def _month_to_period(self, filing_month: str) -> str:
        """Convert 'March 2026' to '2026-03'."""
        import calendar
        parts = filing_month.split()
        if len(parts) != 2:
            return filing_month
        month_name, year = parts
        try:
            month_num = list(calendar.month_name).index(month_name)
            return f"{year}-{month_num:02d}"
        except (ValueError, IndexError):
            return filing_month
