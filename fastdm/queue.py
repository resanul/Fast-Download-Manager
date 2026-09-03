from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum


class Priority(IntEnum):
    LOW = 10
    NORMAL = 20
    HIGH = 30


@dataclass(order=True)
class QueueItem:
    sort_key: tuple[int, int] = field(init=False, repr=False)
    priority: Priority = field(default=Priority.NORMAL, compare=False)
    sequence: int = field(default=0, compare=False)
    task_id: str = field(default="", compare=False)

    def __post_init__(self):
        self.sort_key = (-int(self.priority), self.sequence)


class DownloadQueue:
    """In-memory priority queue with a configurable concurrency limit."""

    def __init__(self, max_concurrent: int = 3):
        self.max_concurrent = max(1, max_concurrent)
        self._items: dict[str, QueueItem] = {}
        self._sequence = 0
        self._active: set[str] = set()

    @property
    def active_count(self) -> int:
        return len(self._active)

    @property
    def pending_count(self) -> int:
        return len(self._items)

    def enqueue(self, task_id: str, priority: Priority = Priority.NORMAL) -> QueueItem:
        if task_id in self._items or task_id in self._active:
            return self._items.get(task_id) or QueueItem(priority, self._sequence, task_id)
        self._sequence += 1
        item = QueueItem(priority, self._sequence, task_id)
        self._items[task_id] = item
        return item

    def remove(self, task_id: str) -> bool:
        return self._items.pop(task_id, None) is not None

    def mark_started(self, task_id: str) -> bool:
        if task_id not in self._items or len(self._active) >= self.max_concurrent:
            return False
        self._items.pop(task_id)
        self._active.add(task_id)
        return True

    def mark_finished(self, task_id: str) -> bool:
        if task_id not in self._active:
            return False
        self._active.remove(task_id)
        return True

    def next_ready(self) -> QueueItem | None:
        if len(self._active) >= self.max_concurrent or not self._items:
            return None
        return min(self._items.values(), key=lambda item: item.sort_key)

    def snapshot(self) -> list[QueueItem]:
        return sorted(self._items.values(), key=lambda item: item.sort_key)
