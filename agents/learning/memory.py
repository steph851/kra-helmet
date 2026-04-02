"""
DECISION MEMORY — remembers every compliance decision and its context.
BOUNDARY: Stores and retrieves decision history. Never makes decisions itself.
Provides queryable, append-only memory that other Brain agents consume.
Sources: audit trail, obligation reports, filing records, escalations.
"""
import json
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from collections import defaultdict

from ..base import BaseAgent

EAT = timezone(timedelta(hours=3))


class DecisionMemory(BaseAgent):
    name = "decision_memory"
    boundary = "Stores and retrieves decision history. Never decides or acts."
    _lock = threading.Lock()

    def __init__(self):
        super().__init__()
        self._memory_path = self.data_dir / "learning" / "decision_memory.jsonl"
        self._memory_path.parent.mkdir(parents=True, exist_ok=True)

    # ── Record ───────────────────────────────────────────────────

    def record(self, decision_type: str, pin: str, context: dict,
               outcome: str | None = None) -> dict:
        """Record a decision event with full context. Returns the entry."""
        entry = {
            "timestamp": datetime.now(EAT).isoformat(),
            "decision_type": decision_type,
            "pin": pin,
            "context": context,
            "outcome": outcome,  # None until feedback_loop resolves it
        }
        with self._lock:
            with open(self._memory_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        return entry

    def record_check(self, pin: str, report: dict):
        """Record a compliance check result."""
        self.record("compliance_check", pin, {
            "compliance": report.get("compliance", {}).get("overall", "unknown"),
            "risk_score": report.get("risk", {}).get("risk_score", 0),
            "risk_level": report.get("risk", {}).get("risk_level", "unknown"),
            "overdue_count": report.get("compliance", {}).get("overdue_count", 0),
            "penalty_kes": report.get("penalties", {}).get("total_penalty_exposure_kes", 0),
            "urgency": report.get("urgency", {}).get("urgency_level", "unknown"),
            "obligations_total": report.get("compliance", {}).get("obligations_total", 0),
        })

    def record_filing(self, pin: str, tax_type: str, period: str, was_late: bool):
        """Record a filing outcome."""
        self.record("filing", pin, {
            "tax_type": tax_type,
            "period": period,
        }, outcome="late" if was_late else "on_time")

    def record_escalation(self, pin: str, tier: str, reason: str):
        """Record an escalation event."""
        self.record("escalation", pin, {
            "tier": tier,
            "reason": reason,
        })

    def record_alert(self, pin: str, channel: str, urgency: str, delivered: bool):
        """Record an alert delivery."""
        self.record("alert", pin, {
            "channel": channel,
            "urgency": urgency,
        }, outcome="delivered" if delivered else "failed")

    def record_risk_change(self, pin: str, old_score: int, new_score: int,
                           factors: list[str]):
        """Record a risk score change."""
        self.record("risk_change", pin, {
            "old_score": old_score,
            "new_score": new_score,
            "delta": new_score - old_score,
            "factors": factors,
        })

    # ── Query ────────────────────────────────────────────────────

    def get_all(self, limit: int = 500) -> list[dict]:
        """Get all decision entries, most recent first."""
        return self._load(limit=limit)

    def get_by_pin(self, pin: str, limit: int = 100) -> list[dict]:
        """Get decision history for a specific SME."""
        return [e for e in self._load() if e.get("pin") == pin][-limit:]

    def get_by_type(self, decision_type: str, limit: int = 200) -> list[dict]:
        """Get decisions of a specific type."""
        return [e for e in self._load() if e.get("decision_type") == decision_type][-limit:]

    def get_recent(self, hours: int = 24) -> list[dict]:
        """Get decisions from the last N hours."""
        cutoff = datetime.now(EAT) - timedelta(hours=hours)
        cutoff_str = cutoff.isoformat()
        return [e for e in self._load() if e.get("timestamp", "") >= cutoff_str]

    def get_outcomes(self, decision_type: str | None = None) -> list[dict]:
        """Get only entries that have resolved outcomes."""
        entries = self._load()
        if decision_type:
            entries = [e for e in entries if e.get("decision_type") == decision_type]
        return [e for e in entries if e.get("outcome") is not None]

    # ── Aggregate ────────────────────────────────────────────────

    def summary(self) -> dict:
        """Aggregate summary of all decision memory."""
        entries = self._load()
        if not entries:
            return {
                "total_entries": 0,
                "decision_types": {},
                "sme_count": 0,
                "outcome_rate": 0,
                "earliest": None,
                "latest": None,
            }

        by_type = defaultdict(int)
        pins = set()
        with_outcome = 0

        for e in entries:
            by_type[e.get("decision_type", "unknown")] += 1
            if e.get("pin"):
                pins.add(e["pin"])
            if e.get("outcome") is not None:
                with_outcome += 1

        return {
            "total_entries": len(entries),
            "decision_types": dict(by_type),
            "sme_count": len(pins),
            "outcome_rate": round(with_outcome / len(entries), 2) if entries else 0,
            "earliest": entries[0].get("timestamp"),
            "latest": entries[-1].get("timestamp"),
        }

    def sme_timeline(self, pin: str) -> list[dict]:
        """Build a chronological timeline for an SME's compliance journey."""
        entries = self.get_by_pin(pin)
        timeline = []
        for e in entries:
            timeline.append({
                "timestamp": e["timestamp"],
                "event": e["decision_type"],
                "detail": self._summarize_entry(e),
                "outcome": e.get("outcome"),
            })
        return timeline

    # ── Ingest from existing data ────────────────────────────────

    def ingest_audit_trail(self) -> int:
        """Pull relevant decisions from the audit trail into memory. Returns count ingested."""
        from workflow.audit_trail import AuditTrail
        trail = AuditTrail()
        existing_ts = {e.get("timestamp") for e in self._load()}
        entries = trail.get_history(limit=1000)
        count = 0

        for entry in entries:
            ts = entry.get("timestamp", "")
            if ts in existing_ts:
                continue

            event_type = entry.get("event_type", "")
            pin = entry.get("sme_pin", "")
            details = entry.get("details", {})

            # Map audit events to decision types
            if event_type in ("COMPLIANCE_CHECK", "CHECK_COMPLETE"):
                self.record("compliance_check", pin, details)
                count += 1
            elif event_type in ("FILING_RECORDED",):
                self.record("filing", pin, details)
                count += 1
            elif event_type in ("ESCALATION",):
                self.record("escalation", pin, details)
                count += 1
            elif event_type in ("ALERT_DELIVERED",):
                self.record("alert", pin, details,
                            outcome="delivered" if details.get("status") == "dry_run" else details.get("status"))
                count += 1

        if count:
            self.log(f"Ingested {count} entries from audit trail")
        return count

    def ingest_filing_history(self) -> int:
        """Pull filing records into memory with on_time/late outcomes. Returns count."""
        from workflow.filing_tracker import FilingTracker
        tracker = FilingTracker()
        smes = self.list_smes()
        existing_count = len(self._load())
        count = 0

        for sme in smes:
            pin = sme["pin"]
            filings = tracker.get_filings(pin)
            for filing in filings:
                period = filing.get("period", "")
                tax_type = filing.get("tax_type", "")
                if period and tax_type:
                    # Determine if filed late by comparing filed_at to deadline
                    was_late = self._was_filing_late(filing)
                    self.record_filing(pin, tax_type, period, was_late)
                    count += 1

        if count:
            self.log(f"Ingested {count} filing records")
        return count

    # ── Internal ─────────────────────────────────────────────────

    def _load(self, limit: int = 5000) -> list[dict]:
        """Load all memory entries from disk."""
        if not self._memory_path.exists():
            return []
        entries = []
        try:
            with open(self._memory_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            entries.append(json.loads(line))
                        except json.JSONDecodeError:
                            continue
        except OSError:
            return []
        return entries[-limit:]

    def _was_filing_late(self, filing: dict) -> bool:
        """Determine if a filing was made after its deadline."""
        filed_at = filing.get("filed_at", "")
        period = filing.get("period", "")
        tax_type = filing.get("tax_type", "")
        if not filed_at or not period:
            return False

        try:
            filed_dt = datetime.fromisoformat(filed_at)
            # Parse period YYYY-MM
            year, month = int(period[:4]), int(period[5:7])
            # Most KRA taxes due by 20th of following month
            deadline_month = month + 1
            deadline_year = year
            if deadline_month > 12:
                deadline_month = 1
                deadline_year += 1

            # Annual taxes: income_tax due by June 30
            if "income_tax" in tax_type:
                deadline = datetime(deadline_year, 6, 30, tzinfo=EAT)
            else:
                deadline = datetime(deadline_year, deadline_month, 20, tzinfo=EAT)

            if filed_dt.tzinfo is None:
                filed_dt = filed_dt.replace(tzinfo=EAT)
            return filed_dt > deadline
        except (ValueError, TypeError):
            return False

    def _summarize_entry(self, entry: dict) -> str:
        """One-line summary of a decision entry."""
        dt = entry.get("decision_type", "?")
        ctx = entry.get("context", {})

        if dt == "compliance_check":
            return f"Compliance: {ctx.get('compliance', '?')}, risk={ctx.get('risk_score', '?')}"
        elif dt == "filing":
            return f"Filed {ctx.get('tax_type', '?')} for {ctx.get('period', '?')}"
        elif dt == "escalation":
            return f"Escalated: {ctx.get('tier', '?')} — {ctx.get('reason', '?')}"
        elif dt == "alert":
            return f"Alert via {ctx.get('channel', '?')} ({ctx.get('urgency', '?')})"
        elif dt == "risk_change":
            return f"Risk {ctx.get('old_score', '?')} → {ctx.get('new_score', '?')}"
        return str(ctx)[:80]

    def clear(self):
        """Clear all decision memory. Use with caution."""
        if self._memory_path.exists():
            self._memory_path.unlink()
        self.log("Decision memory cleared", "WARN")
