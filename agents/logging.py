"""
STRUCTURED LOGGING — JSON logs with request_id for tracing.
BOUNDARY: Provides structured logging only. Never modifies data.
"""
import json
import logging
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Optional
from contextvars import ContextVar

# Context variable for request_id tracing across async calls
request_id_var: ContextVar[Optional[str]] = ContextVar('request_id', default=None)

EAT = timezone(timedelta(hours=3))


class StructuredLogger:
    """Structured JSON logger with request_id tracing."""

    def __init__(self, name: str, log_dir: Path):
        self.name = name
        self.log_dir = log_dir
        self.log_dir.mkdir(parents=True, exist_ok=True)

        # Set up Python logger
        self.logger = logging.getLogger(name)
        self.logger.setLevel(logging.INFO)
        # Prevent messages from propagating to root logger (avoids duplicates)
        self.logger.propagate = False

        # Only add handlers if this logger doesn't already have them
        if not self.logger.handlers:
            # Console handler only — file writes are handled by _write_log()
            console_handler = logging.StreamHandler()
            console_handler.setLevel(logging.INFO)
            console_formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
            console_handler.setFormatter(console_formatter)
            self.logger.addHandler(console_handler)

    def _create_log_entry(
        self,
        level: str,
        message: str,
        request_id: Optional[str] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """Create a structured log entry."""
        entry = {
            "timestamp": datetime.now(EAT).isoformat(),
            "level": level,
            "logger": self.name,
            "message": message,
            "request_id": request_id or request_id_var.get(),
        }
        
        # Add any extra fields
        entry.update(kwargs)
        
        return entry

    def _write_log(self, entry: Dict[str, Any]):
        """Write log entry to file."""
        log_file = self.log_dir / f"{self.name}.jsonl"
        try:
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception as e:
            # Fallback to console if file write fails
            print(f"LOG WRITE ERROR: {e}")
            print(f"LOG ENTRY: {json.dumps(entry, ensure_ascii=False)}")

    def info(self, message: str, request_id: Optional[str] = None, **kwargs):
        """Log info level message."""
        entry = self._create_log_entry("INFO", message, request_id, **kwargs)
        self.logger.info(message)
        self._write_log(entry)

    def warning(self, message: str, request_id: Optional[str] = None, **kwargs):
        """Log warning level message."""
        entry = self._create_log_entry("WARNING", message, request_id, **kwargs)
        self.logger.warning(message)
        self._write_log(entry)

    def error(self, message: str, request_id: Optional[str] = None, **kwargs):
        """Log error level message."""
        entry = self._create_log_entry("ERROR", message, request_id, **kwargs)
        self.logger.error(message)
        self._write_log(entry)

    def debug(self, message: str, request_id: Optional[str] = None, **kwargs):
        """Log debug level message."""
        entry = self._create_log_entry("DEBUG", message, request_id, **kwargs)
        self.logger.debug(message)
        self._write_log(entry)

    def critical(self, message: str, request_id: Optional[str] = None, **kwargs):
        """Log critical level message."""
        entry = self._create_log_entry("CRITICAL", message, request_id, **kwargs)
        self.logger.critical(message)
        self._write_log(entry)

    def log_agent_action(
        self,
        agent_name: str,
        action: str,
        request_id: Optional[str] = None,
        **kwargs
    ):
        """Log an agent action with structured data."""
        entry = self._create_log_entry(
            "INFO",
            f"Agent action: {agent_name}.{action}",
            request_id,
            agent=agent_name,
            action=action,
            **kwargs
        )
        self.logger.info(f"{agent_name}.{action}")
        self._write_log(entry)

    def log_decision(
        self,
        decision_type: str,
        pin: str,
        context: Dict[str, Any],
        outcome: Optional[str] = None,
        request_id: Optional[str] = None,
    ):
        """Log a decision with full context."""
        entry = self._create_log_entry(
            "INFO",
            f"Decision: {decision_type} for {pin}",
            request_id,
            decision_type=decision_type,
            pin=pin,
            context=context,
            outcome=outcome,
        )
        self.logger.info(f"Decision: {decision_type} for {pin}")
        self._write_log(entry)

    def log_error_with_context(
        self,
        error: Exception,
        context: str,
        request_id: Optional[str] = None,
        **kwargs
    ):
        """Log an error with full context and traceback."""
        import traceback
        
        entry = self._create_log_entry(
            "ERROR",
            f"Error in {context}: {str(error)}",
            request_id,
            error_type=type(error).__name__,
            error_message=str(error),
            traceback=traceback.format_exc(),
            context=context,
            **kwargs
        )
        self.logger.error(f"Error in {context}: {str(error)}")
        self._write_log(entry)


def generate_request_id() -> str:
    """Generate a unique request ID for tracing."""
    return str(uuid.uuid4())


def set_request_id(request_id: str):
    """Set the request ID in context."""
    request_id_var.set(request_id)


def get_request_id() -> Optional[str]:
    """Get the current request ID from context."""
    return request_id_var.get()


def create_logger(name: str, log_dir: Path) -> StructuredLogger:
    """Factory function to create a structured logger."""
    return StructuredLogger(name, log_dir)
