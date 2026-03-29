"""Tests for workflow components — filing tracker, audit trail, human gate."""
import json
import tempfile
import pytest
from pathlib import Path
from workflow.filing_tracker import FilingTracker
from workflow.audit_trail import AuditTrail


# ── Filing Tracker ──────────────────────────────────────────────

class TestFilingTracker:
    @pytest.fixture
    def tracker(self, tmp_path):
        t = FilingTracker()
        t.filings_dir = tmp_path / "filings"
        t.filings_dir.mkdir()
        return t

    def test_record_filing(self, tracker):
        entry = tracker.record_filing("A123456789B", "turnover_tax", "2026-03", 105000, "REF001")
        assert entry["pin"] == "A123456789B"
        assert entry["tax_type"] == "turnover_tax"
        assert entry["amount_kes"] == 105000

    def test_get_filings(self, tracker):
        tracker.record_filing("A123456789B", "turnover_tax", "2026-03", 100000)
        tracker.record_filing("A123456789B", "paye", "2026-03", 25000)

        filings = tracker.get_filings("A123456789B")
        assert len(filings) == 2

    def test_filter_by_tax_type(self, tracker):
        tracker.record_filing("A123456789B", "turnover_tax", "2026-03", 100000)
        tracker.record_filing("A123456789B", "paye", "2026-03", 25000)

        filings = tracker.get_filings("A123456789B", tax_type="paye")
        assert len(filings) == 1
        assert filings[0]["tax_type"] == "paye"

    def test_is_filed(self, tracker):
        tracker.record_filing("A123456789B", "turnover_tax", "2026-03", 100000)
        assert tracker.is_filed("A123456789B", "turnover_tax", "2026-03")
        assert not tracker.is_filed("A123456789B", "turnover_tax", "2026-04")
        assert not tracker.is_filed("A123456789B", "paye", "2026-03")

    def test_filing_summary(self, tracker):
        tracker.record_filing("A123456789B", "turnover_tax", "2026-01", 100000)
        tracker.record_filing("A123456789B", "turnover_tax", "2026-02", 110000)
        tracker.record_filing("A123456789B", "paye", "2026-01", 25000)

        summary = tracker.get_filing_summary("A123456789B")
        assert summary["total_filings"] == 3
        assert summary["total_paid_kes"] == 235000
        assert "turnover_tax" in summary["tax_types"]
        assert summary["tax_types"]["turnover_tax"]["count"] == 2

    def test_empty_filings(self, tracker):
        filings = tracker.get_filings("DOESNOTEXIST")
        assert filings == []

    def test_empty_summary(self, tracker):
        summary = tracker.get_filing_summary("DOESNOTEXIST")
        assert summary["total_filings"] == 0


# ── Audit Trail ─────────────────────────────────────────────────

class TestAuditTrail:
    @pytest.fixture
    def trail(self, tmp_path):
        t = AuditTrail()
        t.log_path = tmp_path / "audit.jsonl"
        return t

    def test_record_event(self, trail):
        trail.record("ONBOARD", "orchestrator", {"pin": "A123456789B"}, sme_pin="A123456789B")
        assert trail.log_path.exists()

        entries = trail.get_history()
        assert len(entries) == 1
        assert entries[0]["event_type"] == "ONBOARD"

    def test_filter_by_pin(self, trail):
        trail.record("ONBOARD", "orch", {}, sme_pin="A123456789B")
        trail.record("CHECK", "orch", {}, sme_pin="B987654321A")
        trail.record("CHECK", "orch", {}, sme_pin="A123456789B")

        entries = trail.get_history(sme_pin="A123456789B")
        assert len(entries) == 2

    def test_limit(self, trail):
        for i in range(10):
            trail.record("EVENT", "agent", {"i": i})

        entries = trail.get_history(limit=5)
        assert len(entries) == 5

    def test_immutability(self, trail):
        """Audit trail should only append, never overwrite."""
        trail.record("FIRST", "agent", {})
        trail.record("SECOND", "agent", {})

        entries = trail.get_history()
        assert len(entries) == 2
        assert entries[0]["event_type"] == "FIRST"
        assert entries[1]["event_type"] == "SECOND"

    def test_handles_corrupt_lines(self, trail):
        """Should skip malformed JSON lines."""
        trail.log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(trail.log_path, "w", encoding="utf-8") as f:
            f.write('{"event_type": "GOOD", "agent": "x", "sme_pin": null, "details": {}}\n')
            f.write('THIS IS NOT JSON\n')
            f.write('{"event_type": "ALSO_GOOD", "agent": "x", "sme_pin": null, "details": {}}\n')

        entries = trail.get_history()
        assert len(entries) == 2
