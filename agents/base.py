"""
BASE AGENT — shared by every agent in the system.
Provides: logging, file I/O, memory, boundary enforcement, error recovery.
"""
import json
import os
import time
import traceback
from datetime import datetime
from pathlib import Path

import anthropic
from anthropic import Anthropic

from .logging import StructuredLogger, generate_request_id, set_request_id, get_request_id

ROOT = Path(__file__).parent.parent


class AgentError(Exception):
    """Recoverable agent error — logged and surfaced to caller."""
    def __init__(self, message: str, agent: str = "", recoverable: bool = True):
        super().__init__(message)
        self.agent = agent
        self.recoverable = recoverable


class BaseAgent:
    name: str = "base"
    boundary: str = "No boundary defined."

    def __init__(self):
        # Load centralized config
        from config.loader import get_settings
        self._settings = get_settings()

        self._api_key = os.getenv("ANTHROPIC_API_KEY")
        self._client = None
        self.model = self._settings.get("claude", {}).get("model", "claude-sonnet-4-6")

        self.data_dir   = ROOT / "data"
        self.config_dir = ROOT / "config"
        self.intel_dir  = ROOT / "intelligence"
        self.memory_dir = ROOT / "memory"
        self.staging    = ROOT / "staging"
        self.logs_dir   = ROOT / "logs"
        
        # Initialize structured logger
        self.logger = StructuredLogger(self.name, self.logs_dir)

    @property
    def client(self):
        """Lazy-initialize Anthropic client on first use."""
        if self._client is None and self._api_key and self._api_key != "your-key-here":
            self._client = Anthropic(
                api_key=self._api_key,
                timeout=120.0,
            )
        return self._client

    # ── Logging ──────────────────────────────────────────────────────

    def log(self, msg: str, level: str = "INFO", request_id: str = None, **kwargs):
        """Structured logging with request_id support."""
        rid = request_id or get_request_id()
        
        if level == "INFO":
            self.logger.info(msg, request_id=rid, **kwargs)
        elif level == "WARNING" or level == "WARN":
            self.logger.warning(msg, request_id=rid, **kwargs)
        elif level == "ERROR":
            self.logger.error(msg, request_id=rid, **kwargs)
        elif level == "DEBUG":
            self.logger.debug(msg, request_id=rid, **kwargs)
        elif level == "CRITICAL":
            self.logger.critical(msg, request_id=rid, **kwargs)
        else:
            self.logger.info(msg, request_id=rid, **kwargs)

    def log_decision(self, decision: str, reason: str, request_id: str = None, **kwargs):
        """Log a decision with structured data."""
        rid = request_id or get_request_id()
        self.logger.log_decision(
            decision_type=decision,
            pin=kwargs.get("pin", "unknown"),
            context={"reason": reason, **kwargs},
            request_id=rid
        )

    # ── Error recovery ──────────────────────────────────────────────

    def safe_run(self, func, *args, fallback=None, context: str = "", request_id: str = None, **kwargs):
        """Run a function with error recovery. Returns fallback on failure."""
        rid = request_id or get_request_id()
        try:
            return func(*args, **kwargs)
        except AgentError:
            raise  # let agent errors propagate
        except Exception as e:
            ctx = f" during {context}" if context else ""
            self.log(f"ERROR{ctx}: {type(e).__name__}: {e}", "ERROR", request_id=rid)
            self._log_error(e, context, request_id=rid)
            if fallback is not None:
                return fallback
            raise AgentError(
                f"{self.name} failed{ctx}: {e}",
                agent=self.name,
                recoverable=True,
            )

    def _log_error(self, error: Exception, context: str = "", request_id: str = None):
        """Log error details for debugging."""
        rid = request_id or get_request_id()
        self.logger.log_error_with_context(error, context, request_id=rid)
        
        # Also write to legacy errors.jsonl for backward compatibility
        error_entry = {
            "timestamp": datetime.now().isoformat(),
            "agent": self.name,
            "context": context,
            "error_type": type(error).__name__,
            "error_message": str(error),
            "traceback": traceback.format_exc(),
            "request_id": rid,
        }
        error_log = self.logs_dir / "errors.jsonl"
        error_log.parent.mkdir(exist_ok=True)
        try:
            with open(error_log, "a", encoding="utf-8") as f:
                f.write(json.dumps(error_entry, ensure_ascii=False) + "\n")
        except OSError:
            pass  # can't log the error — don't crash

    # ── File I/O ─────────────────────────────────────────────────────

    def load_json(self, path: Path) -> dict:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            self.log(f"File not found: {path}", "ERROR")
            raise AgentError(f"File not found: {path}", agent=self.name)
        except json.JSONDecodeError as e:
            self.log(f"Invalid JSON in {path}: {e}", "ERROR")
            raise AgentError(f"Invalid JSON in {path}: {e}", agent=self.name)

    def save_json(self, path: Path, data: dict):
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            # Write to temp file first, then rename (atomic-ish write)
            tmp = path.with_suffix(".tmp")
            tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
            tmp.replace(path)
            try:
                self.log(f"Wrote {path.relative_to(ROOT)}")
            except ValueError:
                self.log(f"Wrote {path}")
        except OSError as e:
            self.log(f"Failed to write {path}: {e}", "ERROR")
            raise AgentError(f"Failed to write {path}: {e}", agent=self.name)

    def load_config(self, name: str) -> dict:
        return self.load_json(self.config_dir / name)

    def load_intel(self, name: str) -> dict:
        return self.load_json(self.intel_dir / name)

    # ── SME Profile I/O ─────────────────────────────────────────────

    def load_sme(self, pin: str) -> dict | None:
        path = self.data_dir / "confirmed" / "sme_profiles" / f"sme_{pin}.json"
        if path.exists():
            return self.load_json(path)
        return None

    def save_sme(self, pin: str, profile: dict):
        path = self.data_dir / "confirmed" / "sme_profiles" / f"sme_{pin}.json"
        self.save_json(path, profile)

    def list_smes(self) -> list[dict]:
        registry = self.load_config("smes.json")
        return registry.get("smes", [])

    def register_sme(self, pin: str, name: str):
        registry = self.load_config("smes.json")
        for s in registry["smes"]:
            if s["pin"] == pin:
                return  # already registered
        registry["smes"].append({
            "pin": pin,
            "name": name,
            "onboarded_at": datetime.now().isoformat(),
            "active": True,
        })
        self.save_json(self.config_dir / "smes.json", registry)

    # ── Staging I/O ──────────────────────────────────────────────────

    def write_staging(self, subfolder: str, filename: str, data: dict):
        path = self.staging / subfolder / filename
        self.save_json(path, data)

    def read_staging(self, subfolder: str, filename: str) -> dict | None:
        path = self.staging / subfolder / filename
        if not path.exists():
            return None
        return self.load_json(path)

    # ── Memory ───────────────────────────────────────────────────────

    def read_memory(self, key: str) -> dict:
        path = self.memory_dir / f"{key}.json"
        if not path.exists():
            return {}
        return self.load_json(path)

    def write_memory(self, key: str, data: dict):
        self.save_json(self.memory_dir / f"{key}.json", data)

    # ── Boundary enforcement ─────────────────────────────────────────

    def check_boundary(self, action: str):
        """Log that an agent is respecting its boundary."""
        self.log(f"BOUNDARY CHECK: {action} — {self.boundary}")

    # ── Claude call (for API pipeline — optional in v1) ──────────────

    def call_claude(self, system: str, user: str, max_tokens: int | None = None, request_id: str = None) -> str:
        rid = request_id or get_request_id()
        if not self.client:
            self.log("No API key configured — skipping Claude call", "WARN", request_id=rid)
            return ""

        claude_cfg = self._settings.get("claude", {})
        max_tokens = max_tokens or claude_cfg.get("max_tokens", 4096)
        retries = claude_cfg.get("retry_attempts", 4)
        waits = claude_cfg.get("retry_wait_seconds", [60, 120, 180])

        for attempt in range(retries):
            try:
                resp = self.client.messages.create(
                    model=self.model,
                    max_tokens=max_tokens,
                    system=system,
                    messages=[{"role": "user", "content": user}],
                )
                return resp.content[0].text
            except anthropic.RateLimitError:
                wait = waits[min(attempt, len(waits) - 1)]
                self.log(f"Rate limit — waiting {wait}s (attempt {attempt+1}/{retries})", "WARN", request_id=rid)
                if attempt == retries - 1:
                    raise
                time.sleep(wait)
            except anthropic.APIError as e:
                self.log(f"API error: {e}", "ERROR", request_id=rid)
                self._log_error(e, "call_claude", request_id=rid)
                if attempt == retries - 1:
                    raise AgentError(f"Claude API failed after {retries} attempts: {e}", agent=self.name)
                time.sleep(waits[min(attempt, len(waits) - 1)])
        return ""

    def call_claude_json(self, system: str, user: str, max_tokens: int = 4096, request_id: str = None) -> dict:
        raw = self.call_claude(system, user + "\n\nReturn ONLY valid JSON.", max_tokens, request_id=request_id)
        if not raw:
            return {}
        text = raw.strip()
        if text.startswith("```"):
            lines = text.splitlines()
            text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            start = text.find("{")
            if start == -1:
                return {}
            depth, end = 0, start
            for i, ch in enumerate(text[start:], start):
                if ch == "{": depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        end = i + 1
                        break
            try:
                return json.loads(text[start:end])
            except json.JSONDecodeError:
                self.log(f"JSON parse failed: {text[:200]}", "ERROR", request_id=request_id)
                return {}
