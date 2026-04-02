"""
Tests for The Eyes — monitoring system.
Tests source health, KRA monitor, gazette monitor, eTIMS monitor, and orchestrator.
"""
import json
import pytest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch, MagicMock

import sys
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from agents.monitoring.source_health import SourceHealth, SOURCES
from agents.monitoring.kra_monitor import KRAMonitor, KRA_SOURCES
from agents.monitoring.gazette_monitor import GazetteMonitor, GAZETTE_SOURCES, TAX_PATTERNS
from agents.monitoring.etims_monitor import EtimsMonitor
from agents.monitoring.monitoring_orchestrator import MonitoringOrchestrator

EAT = timezone(timedelta(hours=3))


# ── Source Health Tests ────────────────────────────────────────────


class TestSourceHealth:
    def test_known_sources_defined(self):
        """All expected sources are defined."""
        assert "kra_website" in SOURCES
        assert "itax_portal" in SOURCES
        assert "etims_portal" in SOURCES
        assert "kenya_gazette" in SOURCES

    def test_source_has_required_fields(self):
        for key, source in SOURCES.items():
            assert "url" in source, f"{key} missing url"
            assert "label" in source, f"{key} missing label"
            assert "timeout" in source, f"{key} missing timeout"

    def test_check_unknown_source(self):
        health = SourceHealth()
        result = health.check_source("nonexistent_source")
        assert result["status"] == "unknown"
        assert "error" in result

    def test_check_source_returns_structure(self):
        """Mock a successful response and verify result structure."""
        health = SourceHealth()

        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_response):
            result = health.check_source("kra_website")

        assert result["source"] == "kra_website"
        assert result["status"] == "up"
        assert "response_ms" in result
        assert "checked_at" in result

    def test_check_source_handles_timeout(self):
        health = SourceHealth()

        with patch("urllib.request.urlopen", side_effect=TimeoutError("timed out")):
            result = health.check_source("kra_website")

        assert result["status"] == "down"
        assert "error" in result

    def test_check_source_handles_403_as_up(self):
        """Some sites block HEAD requests with 403 — still means they're reachable."""
        health = SourceHealth()

        import urllib.error
        err = urllib.error.HTTPError("url", 403, "Forbidden", {}, None)
        with patch("urllib.request.urlopen", side_effect=err):
            result = health.check_source("kra_website")

        assert result["status"] == "up"
        assert result["status_code"] == 403

    def test_check_all_returns_summary(self):
        health = SourceHealth()

        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_response):
            result = health.check_all()

        assert "overall" in result
        assert "total" in result
        assert "up" in result
        assert "sources" in result
        assert result["total"] == len(SOURCES)

    def test_history_tracking(self):
        health = SourceHealth()

        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_response):
            health.check_all()
            health.check_all()

        history = health.get_history()
        assert len(history) == 2


# ── KRA Monitor Tests ─────────────────────────────────────────────


class TestKRAMonitor:
    def test_sources_defined(self):
        assert len(KRA_SOURCES) >= 3
        for source in KRA_SOURCES:
            assert "key" in source
            assert "urls" in source
            assert isinstance(source["urls"], list)
            assert len(source["urls"]) > 0
            assert "watch_for" in source

    def test_extract_keywords(self):
        monitor = KRAMonitor()
        content = "The new VAT rate will be effective from January 2026. PAYE deadline extended."
        keywords = monitor._extract_keywords(content, ["VAT", "PAYE", "turnover tax"])
        assert "VAT" in keywords
        assert "PAYE" in keywords
        assert "turnover tax" not in keywords

    def test_extract_keywords_case_insensitive(self):
        monitor = KRAMonitor()
        content = "New vat regulations published today"
        keywords = monitor._extract_keywords(content, ["VAT"])
        assert "VAT" in keywords

    def test_extract_snippet(self):
        monitor = KRAMonitor()
        content = "Some text before. The new VAT rate is 16%. More text after."
        snippet = monitor._extract_snippet(content, ["VAT"], max_length=300)
        assert "VAT" in snippet

    def test_extract_snippet_no_keywords(self):
        monitor = KRAMonitor()
        content = "Just some regular content here."
        snippet = monitor._extract_snippet(content, [], max_length=50)
        assert len(snippet) <= 50

    def test_scan_baseline(self):
        """First scan should establish baselines, not report changes."""
        monitor = KRAMonitor()
        # Clear state
        monitor._state = {"pages": {}, "alerts": []}

        html = "<html><body>KRA Public Notice about tax deadline</body></html>"
        with patch.object(monitor, "_fetch_with_fallback", return_value=html), \
             patch.object(monitor, "_save_state"):
            changes = monitor.scan()

        # First scan = baseline, no changes reported
        assert len(changes) == 0
        assert len(monitor._state["pages"]) > 0

    def test_scan_detects_change(self):
        """Second scan with different content should detect a change."""
        monitor = KRAMonitor()

        # Set up existing baseline
        import hashlib
        old_content = "<html><body>Old content about tax rates</body></html>"
        old_hash = hashlib.sha256(old_content.encode("utf-8")).hexdigest()

        for source in KRA_SOURCES:
            monitor._state["pages"][source["key"]] = {
                "hash": old_hash,
                "last_checked": datetime.now(EAT).isoformat(),
                "last_changed": None,
            }

        new_content = "<html><body>NEW: VAT rate changed to 18%! deadline extended</body></html>"
        with patch.object(monitor, "_fetch_with_fallback", return_value=new_content), \
             patch.object(monitor, "_save_state"), \
             patch.object(monitor, "write_staging"):
            changes = monitor.scan()

        assert len(changes) > 0
        assert any("VAT" in c.get("keywords_found", []) for c in changes)

    def test_get_state(self):
        monitor = KRAMonitor()
        state = monitor.get_state()
        assert "sources_tracked" in state
        assert "last_scan" in state
        assert "recent_alerts" in state

    def test_route_to_review(self):
        monitor = KRAMonitor()
        change = {
            "source": "kra_notices",
            "label": "KRA Public Notices",
            "url": "https://test.com",
            "keywords_found": ["VAT"],
            "content_snippet": "VAT rate changed",
            "detected_at": datetime.now(EAT).isoformat(),
        }

        with patch.object(monitor, "write_staging") as mock_staging:
            monitor._route_to_review(change)

        mock_staging.assert_called_once()
        args = mock_staging.call_args
        assert args[0][0] == "review"
        assert "kra_change" in args[0][1]


# ── Gazette Monitor Tests ─────────────────────────────────────────


class TestGazetteMonitor:
    def test_sources_defined(self):
        assert len(GAZETTE_SOURCES) >= 2
        for source in GAZETTE_SOURCES:
            assert "key" in source
            assert "urls" in source
            assert isinstance(source["urls"], list)
            assert len(source["urls"]) > 0

    def test_extract_legal_notices(self):
        monitor = GazetteMonitor()
        content = """
        Legal Notice No. 45 — Tax Amendment 2026
        The Income Tax Act has been amended.
        Finance Act 2026 effective from 1st July 2026.
        Gazette Notice No. 1234
        """
        notices = monitor._extract_legal_notices(content)
        assert len(notices) > 0

    def test_tax_patterns_match(self):
        """Tax patterns should match known gazette formats."""
        import re
        test_cases = [
            "Legal Notice No. 45 relating to tax procedures",
            "Finance Act 2026",
            "effective date 1st January 2026",
            "Gazette Notice No. 789",
            "increase in VAT rate from 16% to 18%",
        ]
        for text in test_cases:
            matched = any(re.search(p, text) for p in TAX_PATTERNS)
            assert matched, f"Pattern should match: {text}"

    def test_scan_baseline(self):
        monitor = GazetteMonitor()
        monitor._state = {"pages": {}, "notices": []}

        html = "<html><body>Kenya Gazette content about tax</body></html>"
        with patch.object(monitor, "_fetch_with_fallback", return_value=html), \
             patch.object(monitor, "_save_state"):
            findings = monitor.scan()

        assert len(findings) == 0  # baseline

    def test_get_state(self):
        monitor = GazetteMonitor()
        state = monitor.get_state()
        assert "sources_tracked" in state
        assert "last_scan" in state


# ── eTIMS Monitor Tests ───────────────────────────────────────────


class TestEtimsMonitor:
    @pytest.fixture
    def sample_profile(self):
        return {
            "pin": "A000000001B",
            "name": "Test SME",
            "business_type": "sole_proprietor",
            "industry": "retail_wholesale",
            "annual_turnover_kes": 3500000,
            "is_vat_registered": True,
            "has_etims": False,
            "has_employees": True,
            "employee_count": 3,
        }

    def test_vat_without_etims_flagged(self, sample_profile):
        monitor = EtimsMonitor()
        result = monitor._check_sme_etims("A000000001B", sample_profile)

        assert result is not None
        assert any("VAT-registered but no eTIMS" in i for i in result["issues"])
        assert "missing_etims_vat" in result["risk_factors"]

    def test_high_turnover_without_etims(self, sample_profile):
        monitor = EtimsMonitor()
        sample_profile["is_vat_registered"] = False
        sample_profile["annual_turnover_kes"] = 10_000_000
        result = monitor._check_sme_etims("A000000001B", sample_profile)

        assert result is not None
        assert any("turnover" in i.lower() for i in result["issues"])

    def test_compliant_sme_returns_none(self):
        monitor = EtimsMonitor()
        profile = {
            "pin": "Z999999999Z",
            "name": "Compliant SME",
            "business_type": "sole_proprietor",
            "industry": "retail_wholesale",
            "annual_turnover_kes": 500000,
            "is_vat_registered": False,
            "has_etims": True,
            "has_employees": False,
            "employee_count": 0,
        }
        # Use a PIN with no filing history to avoid filing gap issues
        result = monitor._check_sme_etims("Z999999999Z", profile)
        assert result is None

    def test_limited_company_without_etims(self):
        monitor = EtimsMonitor()
        profile = {
            "pin": "A000000001B",
            "name": "Test Ltd",
            "business_type": "limited_company",
            "industry": "professional_services",
            "annual_turnover_kes": 2000000,
            "is_vat_registered": False,
            "has_etims": False,
        }
        result = monitor._check_sme_etims("A000000001B", profile)

        assert result is not None
        assert any("Limited company" in i for i in result["issues"])

    def test_estimate_missing_invoices_with_etims(self):
        monitor = EtimsMonitor()
        profile = {"has_etims": True, "annual_turnover_kes": 5000000}
        assert monitor._estimate_missing_invoices(profile) == 0

    def test_estimate_missing_invoices_without_etims(self):
        monitor = EtimsMonitor()
        profile = {
            "has_etims": False,
            "annual_turnover_kes": 6000000,
            "industry": "retail_wholesale",
        }
        estimate = monitor._estimate_missing_invoices(profile)
        assert estimate > 0

    def test_estimate_zero_turnover(self):
        monitor = EtimsMonitor()
        profile = {"has_etims": False, "annual_turnover_kes": 0}
        assert monitor._estimate_missing_invoices(profile) == 0

    def test_penalty_calculation(self, sample_profile):
        monitor = EtimsMonitor()
        result = monitor._check_sme_etims("A000000001B", sample_profile)
        if result and result["estimated_missing_invoices"] > 0:
            assert result["estimated_penalty_kes"] == result["estimated_missing_invoices"] * 50

    def test_check_sme_not_found(self):
        monitor = EtimsMonitor()
        result = monitor.check_sme("Z999999999Z")
        assert result["status"] == "not_found"

    def test_get_state(self):
        monitor = EtimsMonitor()
        state = monitor.get_state()
        assert "smes_tracked" in state
        assert "compliant" in state
        assert "non_compliant" in state


# ── Monitoring Orchestrator Tests ──────────────────────────────────


class TestMonitoringOrchestrator:
    def test_init(self):
        orch = MonitoringOrchestrator()
        assert orch.kra is not None
        assert orch.gazette is not None
        assert orch.etims is not None
        assert orch.health is not None

    def test_run_full_scan_structure(self):
        orch = MonitoringOrchestrator()

        mock_health = {
            "overall": "healthy",
            "total": 6,
            "up": 6,
            "down": 0,
            "degraded": 0,
            "sources": {},
            "checked_at": datetime.now(EAT).isoformat(),
        }

        with patch.object(orch.health, "check_all", return_value=mock_health), \
             patch.object(orch.kra, "scan", return_value=[]), \
             patch.object(orch.gazette, "scan", return_value=[]), \
             patch.object(orch.etims, "scan", return_value=[]):
            results = orch.run_full_scan()

        assert "source_health" in results
        assert "kra_changes" in results
        assert "gazette_findings" in results
        assert "etims_issues" in results
        assert "summary" in results
        assert results["summary"]["total_findings"] == 0

    def test_run_full_scan_counts_findings(self):
        orch = MonitoringOrchestrator()

        mock_health = {"overall": "healthy", "total": 6, "up": 6, "down": 0, "degraded": 0, "sources": {}, "checked_at": "now"}

        kra_changes = [{"source": "kra_notices", "keywords_found": ["VAT"]}]
        etims_issues = [{"pin": "A000000001B", "issues": ["no eTIMS"]}]

        with patch.object(orch.health, "check_all", return_value=mock_health), \
             patch.object(orch.kra, "scan", return_value=kra_changes), \
             patch.object(orch.gazette, "scan", return_value=[]), \
             patch.object(orch.etims, "scan", return_value=etims_issues):
            results = orch.run_full_scan()

        assert results["summary"]["total_findings"] == 2

    def test_run_health_only(self):
        orch = MonitoringOrchestrator()
        mock_result = {"overall": "healthy"}
        with patch.object(orch.health, "check_all", return_value=mock_result):
            result = orch.run_health_only()
        assert result["overall"] == "healthy"

    def test_status(self):
        orch = MonitoringOrchestrator()
        status = orch.status()
        assert "kra" in status
        assert "gazette" in status
        assert "etims" in status

    def test_error_recovery_in_scan(self):
        """If one monitor fails, others should still run."""
        orch = MonitoringOrchestrator()

        mock_health = {"overall": "healthy", "total": 6, "up": 6, "down": 0, "degraded": 0, "sources": {}, "checked_at": "now"}

        with patch.object(orch.health, "check_all", return_value=mock_health), \
             patch.object(orch.kra, "scan", side_effect=RuntimeError("KRA down")), \
             patch.object(orch.gazette, "scan", return_value=[]), \
             patch.object(orch.etims, "scan", return_value=[]):
            results = orch.run_full_scan()

        # Should recover via safe_run fallback
        assert results["kra_changes"] == 0
        assert results["gazette_findings"] == 0
