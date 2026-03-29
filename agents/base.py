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

        api_key = os.getenv("ANTHROPIC_API_KEY")
        self.client = Anthropic(api_key=api_key) if api_key and api_key != "your-key-here" else None
        self.model = self._settings.get("claude", {}).get("model", "claude-sonnet-4-6")
        self.data_dir   = ROOT / "data"
        self.config_dir = ROOT / "config"
        self.intel_dir  = ROOT / "intelligence"
        self.memory_dir = ROOT / "memory"
        self.staging    = ROOT / "staging"
        self.logs_dir   = ROOT / "logs"

    # ── Logging ──────────────────────────────────────────────────────

    def log(self, msg: str, level: str = "INFO"):
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        line = f"[{ts}] [{level}] [{self.name.upper()}] {msg}"
        print(line)
        log_file = self.logs_dir / "agent_runs.log"
        log_file.parent.mkdir(exist_ok=True)
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(line + "\n")

    def log_decision(self, decision: str, reason: str):
        entry = {
            "timestamp": datetime.now().isoformat(),
            "agent": self.name,
            "decision": decision,
            "reason": reason,
        }
        path = self.memory_dir / "decisions"
        path.mkdir(parents=True, exist_ok=True)
        log_file = path / f"{datetime.now().strftime('%Y-%m-%d')}.jsonl"
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    # ── Error recovery ──────────────────────────────────────────────

    def safe_run(self, func, *args, fallback=None, context: str = "", **kwargs):
        """Run a function with error recovery. Returns fallback on failure."""
        try:
            return func(*args, **kwargs)
        except AgentError:
            raise  # let agent errors propagate
        except Exception as e:
            ctx = f" during {context}" if context else ""
            self.log(f"ERROR{ctx}: {type(e).__name__}: {e}", "ERROR")
            self._log_error(e, context)
            if fallback is not None:
                return fallback
            raise AgentError(
                f"{self.name} failed{ctx}: {e}",
                agent=self.name,
                recoverable=True,
            )

    def _log_error(self, error: Exception, context: str = ""):
        """Log error details for debugging."""
        error_entry = {
            "timestamp": datetime.now().isoformat(),
            "agent": self.name,
            "context": context,
            "error_type": type(error).__name__,
            "error_message": str(error),
            "traceback": traceback.format_exc(),
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

    def call_claude(self, system: str, user: str, max_tokens: int | None = None) -> str:
        if not self.client:
            self.log("No API key configured — skipping Claude call", "WARN")
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
                self.log(f"Rate limit — waiting {wait}s (attempt {attempt+1}/{retries})", "WARN")
                if attempt == retries - 1:
                    raise
                time.sleep(wait)
            except anthropic.APIError as e:
                self.log(f"API error: {e}", "ERROR")
                self._log_error(e, "call_claude")
                if attempt == retries - 1:
                    raise AgentError(f"Claude API failed after {retries} attempts: {e}", agent=self.name)
                time.sleep(waits[min(attempt, len(waits) - 1)])
        return ""

    def call_claude_json(self, system: str, user: str, max_tokens: int = 4096) -> dict:
        raw = self.call_claude(system, user + "\n\nReturn ONLY valid JSON.", max_tokens)
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
                self.log(f"JSON parse failed: {text[:200]}", "ERROR")
                return {}
