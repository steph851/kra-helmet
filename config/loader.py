"""
CONFIG LOADER — single source of truth for all settings.
Reads from config/settings.json, overridable by environment variables.
"""
import json
import os
from pathlib import Path

ROOT = Path(__file__).parent.parent
_settings = None


def get_settings() -> dict:
    """Load settings (cached after first call)."""
    global _settings
    if _settings is None:
        path = ROOT / "config" / "settings.json"
        _settings = json.loads(path.read_text(encoding="utf-8"))
        _apply_env_overrides(_settings)
    return _settings


def _apply_env_overrides(settings: dict):
    """Override settings with environment variables when present."""
    env_map = {
        "HELMET_API_PORT":       ("api", "port", int),
        "HELMET_API_HOST":       ("api", "host", str),
        "HELMET_API_AUTH":       ("api", "require_auth", _bool),
        "HELMET_CLAUDE_MODEL":   ("claude", "model", str),
        "HELMET_CLAUDE_TOKENS":  ("claude", "max_tokens", int),
        "HELMET_CONFIDENCE_AUTO":("confidence", "auto_proceed", float),
        "HELMET_ITAX_BUFFER":    ("deadlines", "itax_buffer_days", int),
        "HELMET_ALERT_MAX":      ("alerts", "max_per_sme_per_day", int),
        "HELMET_REFRESH_SEC":    ("dashboard", "auto_refresh_seconds", int),
    }

    for env_var, (section, key, cast) in env_map.items():
        val = os.getenv(env_var)
        if val is not None:
            try:
                settings[section][key] = cast(val)
            except (ValueError, KeyError):
                pass


def _bool(val: str) -> bool:
    return val.lower() in ("true", "1", "yes")


def get(section: str, key: str, default=None):
    """Get a specific setting value."""
    settings = get_settings()
    return settings.get(section, {}).get(key, default)
