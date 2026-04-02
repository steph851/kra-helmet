"""
HEARTBEAT — the soul of The Pulse.
Background loop that drives the entire scheduler:
  tick → scan → queue → dispatch → sleep → repeat

Runs as a daemon thread alongside the API, or standalone via CLI.
"""
import json
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import sys
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from agents.base import BaseAgent
from workflow.audit_trail import AuditTrail
from .priority_queue import PriorityQueue
from .trigger_engine import TriggerEngine

EAT = timezone(timedelta(hours=3))


class Heartbeat(BaseAgent):
    name = "heartbeat"
    boundary = "Orchestrates the scheduler loop. Never touches SME data directly."

    def __init__(self):
        super().__init__()
        self.audit = AuditTrail()
        self.queue = PriorityQueue()
        self.trigger = TriggerEngine(self.queue)
        self._cron = self._load_cron_config()

        # State
        self._running = False
        self._thread: threading.Thread | None = None
        self._tick_count = 0
        self._started_at: str | None = None
        self._last_tick: str | None = None
        self._last_batch_date: str | None = None  # track daily batch to avoid repeats

    def _load_cron_config(self) -> dict:
        path = ROOT / "scheduler" / "cron_config.json"
        return json.loads(path.read_text(encoding="utf-8"))

    # ── Lifecycle ────────────────────────────────────────────────────

    def start(self, daemon: bool = True):
        """Start the heartbeat loop in a background thread."""
        if self._running:
            self.log("Already running", "WARN")
            return

        self._running = True
        self._started_at = datetime.now(EAT).isoformat()
        self._thread = threading.Thread(target=self._loop, daemon=daemon, name="pulse-heartbeat")
        self._thread.start()

        self.log(f"The Pulse is alive — interval={self._cron.get('heartbeat_interval_seconds', 60)}s")
        self.audit.record("PULSE_START", self.name, {
            "interval_seconds": self._cron.get("heartbeat_interval_seconds", 60),
            "daemon": daemon,
        })

    def stop(self):
        """Stop the heartbeat loop."""
        if not self._running:
            return

        self._running = False
        self.log("Stopping The Pulse...")
        self.audit.record("PULSE_STOP", self.name, {
            "ticks": self._tick_count,
            "uptime_started": self._started_at,
        })

        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=10)
        self._thread = None
        self.log("The Pulse has stopped.")

    @property
    def is_running(self) -> bool:
        return self._running

    # ── Core loop ────────────────────────────────────────────────────

    def _loop(self):
        """Main heartbeat loop — runs until stopped."""
        interval = self._cron.get("heartbeat_interval_seconds", 60)

        while self._running:
            try:
                self._tick()
            except Exception as e:
                self.log(f"Tick failed: {e}", "ERROR")
                self._log_error(e, "heartbeat_tick")

            # Sleep in small increments so stop() is responsive
            for _ in range(interval):
                if not self._running:
                    break
                time.sleep(1)

    def _tick(self):
        """Single heartbeat tick: scan, check batch schedule, dispatch, monitor."""
        self._tick_count += 1
        now = datetime.now(EAT)
        self._last_tick = now.isoformat()

        # 1. Scan all SMEs — queue those needing a check
        queued = self.trigger.scan()

        # 2. Check batch schedule (daily check, reports, dashboard, monitoring)
        self._check_batch_schedule(now)

        # 3. Dispatch queued tasks
        results = []
        if not self.queue.is_empty:
            results = self.trigger.dispatch_batch()

        # 4. Run monitoring on schedule
        self._check_monitoring_schedule(now)

        # 5. Log the tick
        if queued > 0 or results:
            self.log(f"Tick #{self._tick_count}: queued={queued}, dispatched={len(results)}, remaining={self.queue.size}")

    def _check_batch_schedule(self, now: datetime):
        """Run daily batch operations at configured times."""
        today = now.strftime("%Y-%m-%d")

        # Only run batch once per day
        if self._last_batch_date == today:
            return

        # Daily compliance check
        if self.trigger.is_batch_time("daily_check_time"):
            self.log("Batch schedule: daily compliance check")
            self.trigger.trigger_all(reason="daily_batch")
            self._last_batch_date = today

            self.audit.record("PULSE_BATCH", self.name, {
                "type": "daily_check",
                "date": today,
                "smes_queued": self.queue.size,
            })

        # Report generation
        if self.trigger.is_batch_time("report_generation_time"):
            self.log("Batch schedule: generating reports")
            self._generate_reports()

        # Dashboard refresh
        if self.trigger.is_batch_time("dashboard_refresh_time"):
            self.log("Batch schedule: refreshing dashboard")
            self._refresh_dashboard()

    def _generate_reports(self):
        """Generate reports for all SMEs."""
        try:
            from agents.report_generator import ReportGenerator
            gen = ReportGenerator()
            paths = gen.generate_all()
            self.log(f"Generated {len(paths)} report(s)")
        except Exception as e:
            self.log(f"Report generation failed: {e}", "ERROR")
            self._log_error(e, "batch_reports")

    def _refresh_dashboard(self):
        """Regenerate the HTML dashboard."""
        try:
            from agents.dashboard import DashboardGenerator
            gen = DashboardGenerator()
            gen.generate()
            self.log("Dashboard refreshed")
        except Exception as e:
            self.log(f"Dashboard refresh failed: {e}", "ERROR")
            self._log_error(e, "batch_dashboard")

    def _check_monitoring_schedule(self, now: datetime):
        """Run The Eyes monitoring at configured intervals."""
        monitoring_config = self._cron.get("monitoring", {})
        scan_interval = monitoring_config.get("full_scan_interval_hours", 6)

        # Check if it's time for a monitoring scan (every N hours at the top of the hour)
        if now.minute == 0 and now.hour % scan_interval == 0:
            today_hour = f"{now.strftime('%Y-%m-%d')}_{now.hour}"
            # Avoid running twice in the same hour
            if getattr(self, "_last_monitor_hour", None) != today_hour:
                self._last_monitor_hour = today_hour
                self.log("Scheduled monitoring scan (The Eyes)")
                self._run_monitoring()

    def _run_monitoring(self):
        """Execute a full monitoring scan."""
        try:
            from agents.monitoring import MonitoringOrchestrator
            monitor = MonitoringOrchestrator()
            results = monitor.run_full_scan()
            total = results.get("summary", {}).get("total_findings", 0)
            self.log(f"Monitoring complete: {total} finding(s)")
        except Exception as e:
            self.log(f"Monitoring scan failed: {e}", "ERROR")
            self._log_error(e, "monitoring_scan")

    # ── Manual operations ────────────────────────────────────────────

    def run_once(self) -> dict:
        """Run a single tick manually (no background thread). Returns status."""
        self._tick()
        return self.status()

    def trigger_check(self, pin: str, reason: str = "manual") -> bool:
        """Queue an immediate check for an SME."""
        return self.trigger.trigger_check(pin, reason)

    def trigger_all(self, reason: str = "manual_batch") -> int:
        """Queue all SMEs for immediate check."""
        return self.trigger.trigger_all(reason)

    # ── Status ───────────────────────────────────────────────────────

    def status(self) -> dict:
        """Full pulse status."""
        return {
            "alive": self._running,
            "started_at": self._started_at,
            "last_tick": self._last_tick,
            "tick_count": self._tick_count,
            "interval_seconds": self._cron.get("heartbeat_interval_seconds", 60),
            "queue": self.queue.stats(),
            "tasks": self.queue.list_tasks(),
            "last_checked": self.trigger._last_checked,
        }

    def print_status(self):
        """Print pulse status to console."""
        s = self.status()
        print(f"\n{'='*60}")
        print(f"  THE PULSE — Scheduler Status")
        print(f"  {datetime.now(EAT).strftime('%Y-%m-%d %H:%M:%S')} EAT")
        print(f"{'='*60}")
        print(f"  Alive:    {'YES' if s['alive'] else 'NO'}")
        print(f"  Started:  {s['started_at'] or 'never'}")
        print(f"  Last tick: {s['last_tick'] or 'never'}")
        print(f"  Ticks:    {s['tick_count']}")
        print(f"  Interval: {s['interval_seconds']}s")
        print()

        q = s["queue"]
        print(f"  Queue:     {q['queued']} pending, {q['processed']} processed, {q['dropped_duplicates']} deduped")
        if q["by_priority"]:
            for level, count in q["by_priority"].items():
                print(f"    {level}: {count}")
        print()

        if s["tasks"]:
            print(f"  Pending tasks:")
            for t in s["tasks"]:
                print(f"    [{t['priority_label']}] {t['pin']} — {t['reason']}")
            print()

        if s["last_checked"]:
            print(f"  Last checked:")
            for pin, ts in list(s["last_checked"].items())[:10]:
                print(f"    {pin} — {ts[:19]}")
            print()


# ── Standalone runner ────────────────────────────────────────────

def run_pulse():
    """Run The Pulse as a standalone process."""
    print("\n  Starting The Pulse...")
    print("  Press Ctrl+C to stop.\n")

    pulse = Heartbeat()
    pulse.start(daemon=False)

    try:
        while pulse.is_running:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n  Shutting down...")
        pulse.stop()
        print("  The Pulse has stopped.\n")
