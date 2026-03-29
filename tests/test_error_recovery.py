"""Tests for error recovery — the system should handle failures gracefully."""
import pytest
from agents.base import BaseAgent, AgentError


class TestAgentError:
    def test_agent_error_fields(self):
        err = AgentError("something broke", agent="test_agent", recoverable=True)
        assert str(err) == "something broke"
        assert err.agent == "test_agent"
        assert err.recoverable is True

    def test_non_recoverable_error(self):
        err = AgentError("fatal", agent="x", recoverable=False)
        assert err.recoverable is False


class TestSafeRun:
    def test_returns_result_on_success(self):
        agent = BaseAgent()
        result = agent.safe_run(lambda: 42, context="test")
        assert result == 42

    def test_returns_fallback_on_error(self):
        agent = BaseAgent()
        def bad():
            raise ValueError("boom")
        result = agent.safe_run(bad, fallback="safe_value", context="test")
        assert result == "safe_value"

    def test_raises_agent_error_without_fallback(self):
        agent = BaseAgent()
        def bad():
            raise ValueError("boom")
        with pytest.raises(AgentError):
            agent.safe_run(bad, context="test")

    def test_propagates_agent_error(self):
        agent = BaseAgent()
        def bad():
            raise AgentError("known error", agent="test")
        with pytest.raises(AgentError, match="known error"):
            agent.safe_run(bad, context="test")

    def test_logs_errors(self, tmp_path):
        agent = BaseAgent()
        agent.logs_dir = tmp_path
        def bad():
            raise RuntimeError("test error")
        # Use a non-None fallback so safe_run returns instead of raising
        result = agent.safe_run(bad, fallback="recovered", context="test_context")
        assert result == "recovered"
        error_log = tmp_path / "errors.jsonl"
        assert error_log.exists()
        import json
        entry = json.loads(error_log.read_text().strip())
        assert entry["error_type"] == "RuntimeError"
        assert "test error" in entry["error_message"]
        assert entry["context"] == "test_context"


class TestFileIORecovery:
    def test_load_json_missing_file(self):
        agent = BaseAgent()
        from pathlib import Path
        with pytest.raises(AgentError, match="File not found"):
            agent.load_json(Path("/nonexistent/file.json"))

    def test_load_json_invalid_json(self, tmp_path):
        agent = BaseAgent()
        bad_file = tmp_path / "bad.json"
        bad_file.write_text("NOT JSON {{{", encoding="utf-8")
        with pytest.raises(AgentError, match="Invalid JSON"):
            agent.load_json(bad_file)

    def test_save_json_creates_dirs(self, tmp_path):
        agent = BaseAgent()
        path = tmp_path / "deep" / "nested" / "file.json"
        agent.save_json(path, {"key": "value"})
        assert path.exists()
        import json
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["key"] == "value"

    def test_save_json_atomic_write(self, tmp_path):
        """Temp file should not remain after successful write."""
        agent = BaseAgent()
        path = tmp_path / "test.json"
        agent.save_json(path, {"ok": True})
        tmp_file = path.with_suffix(".tmp")
        assert not tmp_file.exists()
        assert path.exists()
