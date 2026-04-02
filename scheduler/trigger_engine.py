"""
TRIGGER ENGINE — reads system state, decides what needs checking, dispatches agents.
BOUNDARY: Decides WHEN to trigger. Never runs the pipeline itself — hands off to orchestrator.
"""
import json
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

import sys
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from agents.base import BaseAgent
from agents.orchestrator import Orchestrator
from workflow.audit_trail import AuditTrail
from .priority_queue import PriorityQueue, Task

EAT = timezone(timedelta(hours=3))


class TriggerEngine(BaseAgent):
    name = "trigger_engine"
    boundary = "Reads state and dispatches checks. Never modifies SME data directly."

    def __init__(self, queue: PriorityQueue):
        super().__init__()
        self.queue = queue
        self.orch = Orchestrator()
        self.audit = AuditTrail()
        self._cron = self._load_cron_config()
        self._last_checked: dict[str, str] = {}  # pin -> ISO timestamp
        self._load_check_history()

    def _load_cron_config(self) -> dict:
        path = ROOT / "scheduler" / "cron_config.json"
        return json.loads(path.read_text(encoding="utf-8"))

    def _load_check_history(self):
        """Load last-checked times from processed obligation reports."""
        obligations_dir = self.data_dir / "processed" / "obligations"
        if not obligations_dir.exists():
            return
        for f in obligations_dir.glob("*.json"):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                pin = data.get("pin", f.stem)
                checked_at = data.get("checked_at")
                if checked_at:
                    self._last_checked[pin] = checked_at
            except (json.JSONDecodeError, OSError):
                continue

    # ── Scan: decide what needs checking ────────────────────────────

    def scan(self) -> int:
        """Scan all SMEs. Queue those needing a check. Returns count queued."""
        smes = self.orch.list_smes()
        queued = 0

        for sme in smes:
            if not sme.get("active", True):
                continue

            pin = sme["pin"]
            urgency_level = self._get_current_urgency(pin)
            interval = self._get_check_interval(urgency_level)

            if self._is_due(pin, interval):
                added = self.queue.push(
                    pin=pin,
                    urgency_level=urgency_level,
                    reason=f"scheduled_{urgency_level}",
                    scheduled_at=datetime.now(EAT).isoformat(),
                )
                if added:
                    queued += 1
                    self.log(f"Queued {pin} — urgency={urgency_level}, interval={interval}min")

        return queued

    def _get_current_urgency(self, pin: str) -> str:
        """Read the last known urgency level for an SME from saved reports."""
        report_path = self.data_dir / "processed" / "obligations" / f"{pin}.json"
        if not report_path.exists():
            return "unknown"
        try:
            data = json.loads(report_path.read_text(encoding="utf-8"))
            return data.get("urgency", {}).get("urgency_level", "unknown")
        except (json.JSONDecodeError, OSError):
            return "unknown"

    def _get_check_interval(self, urgency_level: str) -> int:
        """Get check interval in minutes for an urgency level."""
        intervals = self._cron.get("check_intervals", {})
        entry = intervals.get(urgency_level, intervals.get("unknown", {}))
        return entry.get("minutes", 720)

    def _is_due(self, pin: str, interval_minutes: int) -> bool:
        """Check if enough time has passed since last check."""
        last = self._last_checked.get(pin)
        if not last:
            return True  # never checked
        try:
            last_dt = datetime.fromisoformat(last)
            # Make naive datetimes comparable
            now = datetime.now(EAT)
            if last_dt.tzinfo is None:
                last_dt = last_dt.replace(tzinfo=EAT)
            return (now - last_dt) >= timedelta(minutes=interval_minutes)
        except (ValueError, TypeError):
            return True

    # ── Dispatch: process the queue ──────────────────────────────────

    def dispatch_next(self) -> dict | None:
        """Pop the next task and run the compliance check. Returns result or None."""
        task = self.queue.pop()
        if task is None:
            return None

        rules = self._cron.get("dispatch_rules", {})
        max_retries = rules.get("max_retries", 3)

        self.log(f"Dispatching check for {task.pin} (priority={task.priority}, attempt={task.retries + 1})")

        self.audit.record("PULSE_DISPATCH", self.name, {
            "pin": task.pin,
            "reason": task.reason,
            "priority": task.priority,
            "retry": task.retries,
        }, sme_pin=task.pin)

        try:
            result = self.orch.check_sme(task.pin)

            if result:
                self._last_checked[task.pin] = datetime.now(EAT).isoformat()
                self.log(f"Check complete for {task.pin} — {result.get('compliance', {}).get('overall', '?')}")
                return result
            else:
                self.log(f"Check returned None for {task.pin}", "WARN")
                self.queue.requeue(task, max_retries)
                return None

        except Exception as e:
            self.log(f"Check failed for {task.pin}: {e}", "ERROR")
            self._log_error(e, f"dispatch({task.pin})")
            requeued = self.queue.requeue(task, max_retries)
            if not requeued:
                self.log(f"Max retries exceeded for {task.pin} — dropping", "ERROR")
                self.audit.record("PULSE_DROP", self.name, {
                    "pin": task.pin,
                    "reason": "max_retries_exceeded",
                    "retries": task.retries,
                    "error": str(e),
                }, sme_pin=task.pin)
            return None

    def dispatch_batch(self, max_count: int | None = None, max_workers: int = 3) -> list[dict]:
        """Dispatch up to max_count tasks from the queue in parallel. Returns results."""
        rules = self._cron.get("dispatch_rules", {})
        limit = max_count or rules.get("max_concurrent_checks", 5)
        cooldown = rules.get("cooldown_after_check_seconds", 10)

        # Collect tasks to dispatch
        tasks = []
        for _ in range(limit):
            if self.queue.is_empty:
                break
            task = self.queue.pop()
            if task:
                tasks.append(task)

        if not tasks:
            return []

        results = []

        def dispatch_one(task):
            try:
                self.log(f"Dispatching check for {task.pin} (priority={task.priority}, attempt={task.retries + 1})")
                self.audit.record("PULSE_DISPATCH", self.name, {
                    "pin": task.pin,
                    "reason": task.reason,
                    "priority": task.priority,
                    "retry": task.retries,
                }, sme_pin=task.pin)

                result = self.orch.check_sme(task.pin)
                if result:
                    self._last_checked[task.pin] = datetime.now(EAT).isoformat()
                    self.log(f"Check complete for {task.pin} — {result.get('compliance', {}).get('overall', '?')}")
                    return result
                else:
                    self.log(f"Check returned None for {task.pin}", "WARN")
                    self.queue.requeue(task, rules.get("max_retries", 3))
                    return None
            except Exception as e:
                self.log(f"Check failed for {task.pin}: {e}", "ERROR")
                self._log_error(e, f"dispatch({task.pin})")
                requeued = self.queue.requeue(task, rules.get("max_retries", 3))
                if not requeued:
                    self.log(f"Max retries exceeded for {task.pin} — dropping", "ERROR")
                    self.audit.record("PULSE_DROP", self.name, {
                        "pin": task.pin,
                        "reason": "max_retries_exceeded",
                        "retries": task.retries,
                        "error": str(e),
                    }, sme_pin=task.pin)
                return None

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(dispatch_one, task): task for task in tasks}
            for future in as_completed(futures):
                result = future.result()
                if result:
                    results.append(result)

        return results

    # ── Immediate triggers ───────────────────────────────────────────

    def trigger_check(self, pin: str, reason: str = "manual") -> bool:
        """Immediately queue a check for a specific SME. Returns True if queued."""
        added = self.queue.push(
            pin=pin,
            urgency_level="red",  # manual triggers get top priority
            reason=reason,
        )
        if added:
            self.log(f"Manual trigger queued for {pin} — reason: {reason}")
            self.audit.record("PULSE_MANUAL_TRIGGER", self.name, {
                "pin": pin,
                "reason": reason,
            }, sme_pin=pin)
        return added

    def trigger_all(self, reason: str = "manual_batch") -> int:
        """Queue all active SMEs for immediate check. Returns count queued."""
        smes = self.orch.list_smes()
        queued = 0
        for sme in smes:
            if sme.get("active", True):
                if self.queue.push(pin=sme["pin"], urgency_level="orange", reason=reason):
                    queued += 1
        self.log(f"Batch trigger: queued {queued} SMEs — reason: {reason}")
        return queued

    # ── Batch schedule checks ────────────────────────────────────────

    def is_batch_time(self, schedule_key: str) -> bool:
        """Check if current time matches a batch schedule (within 1-minute window)."""
        schedule = self._cron.get("batch_schedule", {})
        target_time = schedule.get(schedule_key)
        if not target_time:
            return False

        now = datetime.now(EAT)
        target_h, target_m = (int(x) for x in target_time.split(":"))
        return now.hour == target_h and now.minute == target_m

    # ── Status ───────────────────────────────────────────────────────

    def status(self) -> dict:
        """Current trigger engine state."""
        return {
            "queue": self.queue.stats(),
            "tasks": self.queue.list_tasks(),
            "last_checked": dict(sorted(
                self._last_checked.items(),
                key=lambda x: x[1],
                reverse=True,
            )),
            "cron_config": {
                "heartbeat_interval": self._cron.get("heartbeat_interval_seconds"),
                "check_intervals": {
                    k: v.get("minutes") for k, v in self._cron.get("check_intervals", {}).items()
                    if isinstance(v, dict)
                },
            },
        }
