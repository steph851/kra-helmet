"""
Tests for The Pulse — scheduler system.
Tests priority queue, trigger engine, event listener, and heartbeat.
"""
import json
import time
import pytest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch, MagicMock

import sys
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from scheduler.priority_queue import PriorityQueue, Task, PRIORITY_MAP
from scheduler.heartbeat import Heartbeat
from scheduler.trigger_engine import TriggerEngine


# ── Priority Queue Tests ───────────────────────────────────────────


class TestPriorityQueue:
    def setup_method(self):
        self.q = PriorityQueue()

    def test_push_and_pop(self):
        self.q.push("A000000001B", "red", "test")
        assert self.q.size == 1
        task = self.q.pop()
        assert task is not None
        assert task.pin == "A000000001B"
        assert task.priority == PRIORITY_MAP["red"]
        assert self.q.size == 0

    def test_priority_ordering(self):
        """Higher urgency (lower number) pops first."""
        self.q.push("PIN_GREEN", "green", "routine")
        self.q.push("PIN_RED", "red", "overdue")
        self.q.push("PIN_YELLOW", "yellow", "upcoming")

        first = self.q.pop()
        assert first.pin == "PIN_RED"
        second = self.q.pop()
        assert second.pin == "PIN_YELLOW"
        third = self.q.pop()
        assert third.pin == "PIN_GREEN"

    def test_deduplication(self):
        """Same PIN can't be queued twice."""
        assert self.q.push("A000000001B", "red", "first") is True
        assert self.q.push("A000000001B", "orange", "second") is False
        assert self.q.size == 1

    def test_pop_empty(self):
        assert self.q.pop() is None

    def test_peek(self):
        self.q.push("A000000001B", "red", "test")
        task = self.q.peek()
        assert task is not None
        assert task.pin == "A000000001B"
        assert self.q.size == 1  # peek doesn't remove

    def test_remove(self):
        self.q.push("A000000001B", "red", "test")
        self.q.push("A000000002C", "green", "test")
        assert self.q.remove("A000000001B") is True
        assert self.q.size == 1
        assert self.q.remove("NONEXIST") is False

    def test_clear(self):
        self.q.push("A000000001B", "red", "test")
        self.q.push("A000000002C", "green", "test")
        self.q.clear()
        assert self.q.size == 0
        assert self.q.is_empty is True

    def test_contains(self):
        self.q.push("A000000001B", "red", "test")
        assert self.q.contains("A000000001B") is True
        assert self.q.contains("NONEXIST") is False

    def test_requeue_increments_retry(self):
        self.q.push("A000000001B", "red", "test")
        task = self.q.pop()
        assert self.q.requeue(task, max_retries=3) is True
        assert self.q.size == 1

        retried = self.q.pop()
        assert retried.retries == 1
        assert retried.priority > PRIORITY_MAP["red"]  # demoted

    def test_requeue_max_retries(self):
        task = Task(priority=1, scheduled_at="now", pin="TEST", reason="test", retries=3)
        assert self.q.requeue(task, max_retries=3) is False

    def test_stats(self):
        self.q.push("A000000001B", "red", "test")
        self.q.push("A000000002C", "green", "test")
        self.q.pop()  # process one

        stats = self.q.stats()
        assert stats["queued"] == 1
        assert stats["processed"] == 1
        assert "green" in stats["by_priority"]

    def test_stats_tracks_duplicates(self):
        self.q.push("A000000001B", "red", "test")
        self.q.push("A000000001B", "red", "test")  # duplicate
        stats = self.q.stats()
        assert stats["dropped_duplicates"] == 1

    def test_list_tasks(self):
        self.q.push("A000000001B", "red", "overdue")
        self.q.push("A000000002C", "green", "routine")
        tasks = self.q.list_tasks()
        assert len(tasks) == 2
        assert tasks[0]["pin"] == "A000000001B"  # red first
        assert tasks[0]["priority_label"] == "red"

    def test_task_to_dict(self):
        task = Task(priority=1, scheduled_at="2026-03-30T10:00:00", pin="TEST", reason="test")
        d = task.to_dict()
        assert d["pin"] == "TEST"
        assert d["priority_label"] == "red"
        assert d["retries"] == 0

    def test_thread_safety(self):
        """Push from multiple threads doesn't crash."""
        import threading
        errors = []

        def push_items(start):
            try:
                for i in range(50):
                    pin = f"P{start + i:09d}Z"
                    self.q.push(pin, "yellow", "thread_test")
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=push_items, args=(i * 50,)) for i in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        assert self.q.size == 200


# ── Trigger Engine Tests ───────────────────────────────────────────


class TestTriggerEngine:
    def setup_method(self):
        self.queue = PriorityQueue()
        self.engine = TriggerEngine(self.queue)

    def test_scan_queues_unchecked_smes(self):
        """SMEs that have never been checked should be queued."""
        mock_smes = [
            {"pin": "A000000001B", "name": "Test SME", "active": True},
        ]
        with patch.object(self.engine.orch, "list_smes", return_value=mock_smes):
            # Clear any existing check history
            self.engine._last_checked.clear()
            queued = self.engine.scan()

        assert queued >= 1
        assert self.queue.contains("A000000001B")

    def test_scan_skips_inactive(self):
        mock_smes = [
            {"pin": "A000000001B", "name": "Inactive", "active": False},
        ]
        with patch.object(self.engine.orch, "list_smes", return_value=mock_smes):
            queued = self.engine.scan()

        assert queued == 0

    def test_scan_skips_recently_checked(self):
        """Recently checked SMEs should not be re-queued."""
        mock_smes = [
            {"pin": "A000000001B", "name": "Recent", "active": True},
        ]
        # Pretend we just checked it
        self.engine._last_checked["A000000001B"] = datetime.now(
            timezone(timedelta(hours=3))
        ).isoformat()

        with patch.object(self.engine.orch, "list_smes", return_value=mock_smes):
            queued = self.engine.scan()

        assert queued == 0

    def test_trigger_check_queues_at_red(self):
        added = self.engine.trigger_check("A000000001B", "test_reason")
        assert added is True
        task = self.queue.peek()
        assert task.priority == PRIORITY_MAP["red"]

    def test_trigger_all(self):
        mock_smes = [
            {"pin": "A000000001B", "name": "SME1", "active": True},
            {"pin": "A000000002C", "name": "SME2", "active": True},
            {"pin": "A000000003D", "name": "Inactive", "active": False},
        ]
        with patch.object(self.engine.orch, "list_smes", return_value=mock_smes):
            count = self.engine.trigger_all()

        assert count == 2
        assert self.queue.size == 2

    def test_dispatch_next_empty(self):
        result = self.engine.dispatch_next()
        assert result is None

    def test_dispatch_next_success(self):
        self.queue.push("A000000001B", "red", "test")
        mock_result = {
            "profile": {"pin": "A000000001B", "name": "Test"},
            "compliance": {"overall": "compliant"},
            "risk": {"risk_score": 20},
        }
        with patch.object(self.engine.orch, "check_sme", return_value=mock_result):
            result = self.engine.dispatch_next()

        assert result is not None
        assert result["compliance"]["overall"] == "compliant"
        assert self.queue.is_empty

    def test_dispatch_requeues_on_none(self):
        self.queue.push("A000000001B", "red", "test")
        with patch.object(self.engine.orch, "check_sme", return_value=None):
            result = self.engine.dispatch_next()

        assert result is None
        # Should be requeued
        assert self.queue.size == 1

    def test_dispatch_requeues_on_error(self):
        self.queue.push("A000000001B", "red", "test")
        with patch.object(self.engine.orch, "check_sme", side_effect=RuntimeError("boom")):
            result = self.engine.dispatch_next()

        assert result is None
        assert self.queue.size == 1  # requeued

    def test_is_due_never_checked(self):
        assert self.engine._is_due("NEVER_SEEN", 60) is True

    def test_is_due_recent(self):
        self.engine._last_checked["RECENT"] = datetime.now(
            timezone(timedelta(hours=3))
        ).isoformat()
        assert self.engine._is_due("RECENT", 60) is False

    def test_is_due_old(self):
        old_time = (datetime.now(timezone(timedelta(hours=3))) - timedelta(hours=2)).isoformat()
        self.engine._last_checked["OLD"] = old_time
        assert self.engine._is_due("OLD", 60) is True  # 60 min interval, 2 hours ago

    def test_get_check_interval(self):
        assert self.engine._get_check_interval("red") == 30
        assert self.engine._get_check_interval("green") == 1440
        assert self.engine._get_check_interval("nonexistent") == 720  # falls back to unknown

    def test_status(self):
        status = self.engine.status()
        assert "queue" in status
        assert "tasks" in status
        assert "last_checked" in status
        assert "cron_config" in status


# ── Heartbeat Tests ────────────────────────────────────────────────


class TestHeartbeat:
    def test_init(self):
        pulse = Heartbeat()
        assert pulse.is_running is False
        assert pulse._tick_count == 0

    def test_run_once(self):
        pulse = Heartbeat()
        with patch.object(pulse.trigger, "scan", return_value=0), \
             patch.object(pulse.trigger, "dispatch_batch", return_value=[]):
            status = pulse.run_once()

        assert status["tick_count"] == 1
        assert status["alive"] is False  # not started as daemon

    def test_status(self):
        pulse = Heartbeat()
        status = pulse.status()
        assert "alive" in status
        assert "tick_count" in status
        assert "queue" in status
        assert "interval_seconds" in status

    def test_trigger_check_delegates(self):
        pulse = Heartbeat()
        with patch.object(pulse.trigger, "trigger_check", return_value=True) as mock:
            result = pulse.trigger_check("A000000001B", "test")
        assert result is True
        mock.assert_called_once_with("A000000001B", "test")

    def test_start_stop(self):
        pulse = Heartbeat()
        # Override interval to be very short for testing
        pulse._cron["heartbeat_interval_seconds"] = 1

        with patch.object(pulse.trigger, "scan", return_value=0), \
             patch.object(pulse.trigger, "dispatch_batch", return_value=[]):
            pulse.start(daemon=True)
            assert pulse.is_running is True

            time.sleep(0.5)  # let it tick once
            pulse.stop()
            assert pulse.is_running is False

    def test_double_start(self):
        pulse = Heartbeat()
        pulse._running = True
        pulse.start()  # should warn and return without creating thread
        assert pulse._thread is None


# ── Event Listener Tests ───────────────────────────────────────────


class TestEventListener:
    def setup_method(self):
        from fastapi.testclient import TestClient
        from fastapi import FastAPI

        self.queue = PriorityQueue()
        self.app = FastAPI()

        from scheduler.event_listener import create_webhook_router
        router = create_webhook_router(self.queue)
        self.app.include_router(router)
        self.client = TestClient(self.app)

    def test_filing_webhook(self):
        resp = self.client.post("/webhooks/filing", json={
            "pin": "A000000001B",
            "tax_type": "vat",
            "period": "2026-03",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["accepted"] is True
        assert data["queued"] is True
        assert self.queue.contains("A000000001B")

    def test_filing_webhook_dedup(self):
        self.client.post("/webhooks/filing", json={"pin": "A000000001B", "tax_type": "vat", "period": "2026-03"})
        resp = self.client.post("/webhooks/filing", json={"pin": "A000000001B", "tax_type": "paye", "period": "2026-03"})
        assert resp.json()["queued"] is False  # duplicate

    def test_sme_update_webhook(self):
        resp = self.client.post("/webhooks/sme-update", json={
            "pin": "A000000001B",
            "fields_changed": ["annual_turnover_kes"],
        })
        assert resp.status_code == 200
        assert resp.json()["queued"] is True

    def test_manual_trigger(self):
        resp = self.client.post("/webhooks/trigger", json={
            "pin": "A000000001B",
            "reason": "test_trigger",
        })
        assert resp.status_code == 200
        assert resp.json()["queued"] is True
        task = self.queue.peek()
        assert task.priority == PRIORITY_MAP["red"]

    def test_manual_trigger_no_pin(self):
        resp = self.client.post("/webhooks/trigger", json={"reason": "test"})
        assert resp.status_code == 400

    def test_priority_override(self):
        # Queue at green first
        self.queue.push("A000000001B", "green", "routine")
        resp = self.client.post("/webhooks/priority-override", json={
            "pin": "A000000001B",
            "urgency_level": "red",
            "reason": "kra_audit_notice",
        })
        assert resp.status_code == 200
        task = self.queue.peek()
        assert task.priority == PRIORITY_MAP["red"]

    def test_queue_status(self):
        self.queue.push("A000000001B", "red", "test")
        resp = self.client.get("/webhooks/queue")
        assert resp.status_code == 200
        data = resp.json()
        assert data["stats"]["queued"] == 1
        assert len(data["tasks"]) == 1

    def test_webhook_auth_rejected(self):
        """When secret is set, requests without it should be rejected."""
        with patch.dict("os.environ", {"HELMET_WEBHOOK_SECRET": "my-secret"}):
            # Recreate router with secret
            from scheduler.event_listener import create_webhook_router
            from fastapi import FastAPI
            from fastapi.testclient import TestClient

            app = FastAPI()
            q = PriorityQueue()
            router = create_webhook_router(q)
            app.include_router(router)
            client = TestClient(app)

            resp = client.post("/webhooks/filing", json={
                "pin": "A000000001B", "tax_type": "vat", "period": "2026-03"
            }, headers={"X-Webhook-Secret": "wrong-secret"})
            assert resp.status_code == 401
