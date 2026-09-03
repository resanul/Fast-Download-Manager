from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Awaitable, Callable


@dataclass
class Schedule:
    id: str
    task_id: str
    run_at: float
    interval: float | None = None
    enabled: bool = True

    @classmethod
    def once(cls, task_id: str, run_at: datetime, schedule_id: str | None = None) -> "Schedule":
        return cls(schedule_id or uuid.uuid4().hex, task_id, _timestamp(run_at))

    @classmethod
    def recurring(
        cls,
        task_id: str,
        run_at: datetime,
        interval: float,
        schedule_id: str | None = None,
    ) -> "Schedule":
        if interval <= 0:
            raise ValueError("interval must be greater than zero")
        return cls(schedule_id or uuid.uuid4().hex, task_id, _timestamp(run_at), interval)

    @property
    def due(self) -> bool:
        return self.enabled and self.run_at <= time.time()

    def advance(self, now: float | None = None) -> bool:
        if not self.interval:
            self.enabled = False
            return False
        now = time.time() if now is None else now
        while self.run_at <= now:
            self.run_at += self.interval
        return True


def _timestamp(value: datetime) -> float:
    if value.tzinfo is None:
        value = value.astimezone()
    return value.astimezone(timezone.utc).timestamp()


class Scheduler:
    """Small async scheduler for one-shot and recurring download triggers."""

    def __init__(self, poll_interval: float = 1.0):
        self.poll_interval = max(0.1, poll_interval)
        self._schedules: dict[str, Schedule] = {}
        self._runner: asyncio.Task | None = None
        self._stop = asyncio.Event()

    @property
    def schedules(self) -> tuple[Schedule, ...]:
        return tuple(sorted(self._schedules.values(), key=lambda item: item.run_at))

    def add(self, schedule: Schedule) -> Schedule:
        self._schedules[schedule.id] = schedule
        return schedule

    def remove(self, schedule_id: str) -> bool:
        return self._schedules.pop(schedule_id, None) is not None

    def enable(self, schedule_id: str, enabled: bool = True) -> bool:
        schedule = self._schedules.get(schedule_id)
        if not schedule:
            return False
        schedule.enabled = enabled
        return True

    def due(self, now: float | None = None) -> list[Schedule]:
        now = time.time() if now is None else now
        return [s for s in self._schedules.values() if s.enabled and s.run_at <= now]

    async def run(self, trigger: Callable[[Schedule], Awaitable[None] | None]):
        if self._runner and not self._runner.done():
            return
        self._stop.clear()
        self._runner = asyncio.current_task()
        try:
            while not self._stop.is_set():
                for schedule in list(self.due()):
                    result = trigger(schedule)
                    if asyncio.iscoroutine(result):
                        await result
                    schedule.advance()
                    if not schedule.enabled:
                        self._schedules.pop(schedule.id, None)
                try:
                    await asyncio.wait_for(self._stop.wait(), timeout=self.poll_interval)
                except asyncio.TimeoutError:
                    pass
        finally:
            self._runner = None

    async def stop(self):
        self._stop.set()
        runner = self._runner
        if runner and runner is not asyncio.current_task():
            await runner

    def close(self):
        self._stop.set()
