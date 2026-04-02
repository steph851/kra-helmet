"""
PRIORITY QUEUE — urgency-ranked task queue for The Pulse.
Thread-safe. Deduplicates by SME PIN. Most urgent items dispatched first.
"""
import heapq
import threading
from datetime import datetime
from dataclasses import dataclass, field


# Priority levels (lower number = higher priority)
PRIORITY_MAP = {
    "red": 1,       # Overdue — dispatch immediately
    "orange": 2,    # Critical — due within 3 days
    "yellow": 3,    # Upcoming — due within 7 days
    "green": 4,     # Clear — routine check
    "unknown": 5,   # Never checked
}


@dataclass(order=True)
class Task:
    priority: int
    scheduled_at: str = field(compare=False)
    pin: str = field(compare=False)
    reason: str = field(compare=False)
    retries: int = field(default=0, compare=False)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat(), compare=False)

    def to_dict(self) -> dict:
        return {
            "priority": self.priority,
            "priority_label": next(
                (k for k, v in PRIORITY_MAP.items() if v == self.priority), "unknown"
            ),
            "pin": self.pin,
            "reason": self.reason,
            "retries": self.retries,
            "scheduled_at": self.scheduled_at,
            "created_at": self.created_at,
        }


class PriorityQueue:
    """Thread-safe priority queue with deduplication by PIN."""

    def __init__(self):
        self._heap: list[Task] = []
        self._pins: set[str] = set()  # track queued PINs for dedup
        self._lock = threading.Lock()
        self._processed: int = 0
        self._dropped: int = 0

    def push(self, pin: str, urgency_level: str, reason: str, scheduled_at: str | None = None) -> bool:
        """Add a task. Returns False if PIN already queued (dedup)."""
        with self._lock:
            if pin in self._pins:
                self._dropped += 1
                return False

            priority = PRIORITY_MAP.get(urgency_level, PRIORITY_MAP["unknown"])
            task = Task(
                priority=priority,
                scheduled_at=scheduled_at or datetime.now().isoformat(),
                pin=pin,
                reason=reason,
            )
            heapq.heappush(self._heap, task)
            self._pins.add(pin)
            return True

    def pop(self) -> Task | None:
        """Pop the highest-priority task. Returns None if empty."""
        with self._lock:
            if not self._heap:
                return None
            task = heapq.heappop(self._heap)
            self._pins.discard(task.pin)
            self._processed += 1
            return task

    def peek(self) -> Task | None:
        """Look at the highest-priority task without removing it."""
        with self._lock:
            return self._heap[0] if self._heap else None

    def requeue(self, task: Task, max_retries: int = 3) -> bool:
        """Re-add a failed task with incremented retry count. Returns False if max retries exceeded."""
        with self._lock:
            if task.retries >= max_retries:
                return False
            task.retries += 1
            # Demote priority slightly on retry
            task.priority = min(task.priority + 1, PRIORITY_MAP["unknown"])
            heapq.heappush(self._heap, task)
            self._pins.add(task.pin)
            return True

    def remove(self, pin: str) -> bool:
        """Remove a PIN from the queue. Returns True if found."""
        with self._lock:
            if pin not in self._pins:
                return False
            self._heap = [t for t in self._heap if t.pin != pin]
            heapq.heapify(self._heap)
            self._pins.discard(pin)
            return True

    def clear(self):
        """Clear all tasks."""
        with self._lock:
            self._heap.clear()
            self._pins.clear()

    @property
    def size(self) -> int:
        with self._lock:
            return len(self._heap)

    @property
    def is_empty(self) -> bool:
        with self._lock:
            return len(self._heap) == 0

    def contains(self, pin: str) -> bool:
        with self._lock:
            return pin in self._pins

    def stats(self) -> dict:
        """Queue statistics."""
        with self._lock:
            by_priority = {}
            for task in self._heap:
                label = next((k for k, v in PRIORITY_MAP.items() if v == task.priority), "unknown")
                by_priority[label] = by_priority.get(label, 0) + 1

            return {
                "queued": len(self._heap),
                "processed": self._processed,
                "dropped_duplicates": self._dropped,
                "by_priority": by_priority,
            }

    def list_tasks(self) -> list[dict]:
        """Return all queued tasks as dicts, sorted by priority."""
        with self._lock:
            return [t.to_dict() for t in sorted(self._heap)]
