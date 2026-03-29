"""Tests for centralized configuration."""
import os
import pytest
from config.loader import get_settings, get, _apply_env_overrides


class TestConfigLoader:
    def test_loads_settings(self):
        settings = get_settings()
        assert isinstance(settings, dict)
        assert "system" in settings
        assert "api" in settings
        assert "claude" in settings

    def test_system_version(self):
        settings = get_settings()
        assert settings["system"]["version"] == "1.0.0"

    def test_get_helper(self):
        port = get("api", "port")
        assert isinstance(port, int)
        assert port > 0

    def test_get_missing_returns_default(self):
        val = get("nonexistent", "key", default="fallback")
        assert val == "fallback"

    def test_penalty_config_present(self):
        settings = get_settings()
        assert "penalties" in settings
        assert settings["penalties"]["income_tax_late_filing_flat_kes"] == 20000

    def test_risk_weights_present(self):
        settings = get_settings()
        weights = settings["risk"]["weights"]
        assert "overdue_filings" in weights
        assert weights["overdue_filings"] == 30

    def test_confidence_thresholds(self):
        settings = get_settings()
        assert settings["confidence"]["auto_proceed"] == 0.7
        assert settings["confidence"]["human_review"] == 0.5

    def test_env_override(self):
        """Environment variables should override settings."""
        settings = {
            "api": {"port": 8000, "host": "0.0.0.0"},
            "claude": {"model": "claude-sonnet-4-6"},
        }
        os.environ["HELMET_API_PORT"] = "9000"
        _apply_env_overrides(settings)
        assert settings["api"]["port"] == 9000
        # Clean up
        del os.environ["HELMET_API_PORT"]


class TestIntelligenceFiles:
    """Verify intelligence data files are valid and complete."""

    def test_tax_knowledge_graph_loads(self):
        import json
        from pathlib import Path
        ROOT = Path(__file__).parent.parent
        data = json.loads((ROOT / "intelligence" / "tax_knowledge_graph.json").read_text(encoding="utf-8"))
        assert "taxes" in data
        assert len(data["taxes"]) >= 10

    def test_industry_profiles_loads(self):
        import json
        from pathlib import Path
        ROOT = Path(__file__).parent.parent
        data = json.loads((ROOT / "intelligence" / "industry_profiles.json").read_text(encoding="utf-8"))
        assert "industries" in data
        assert len(data["industries"]) >= 10

    def test_deadline_calendar_loads(self):
        import json
        from pathlib import Path
        ROOT = Path(__file__).parent.parent
        data = json.loads((ROOT / "intelligence" / "deadline_calendar.json").read_text(encoding="utf-8"))
        assert "public_holidays_2026" in data
        assert len(data["public_holidays_2026"]) >= 10

    def test_filing_guides_loads(self):
        import json
        from pathlib import Path
        ROOT = Path(__file__).parent.parent
        data = json.loads((ROOT / "intelligence" / "filing_guides.json").read_text(encoding="utf-8"))
        assert "filing_guides" in data
        assert len(data["filing_guides"]) >= 10
        for g in data["filing_guides"]:
            assert "tax_key" in g
            assert "title" in g
            assert "steps" in g
            assert len(g["steps"]) >= 5
