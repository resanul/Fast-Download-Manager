from datetime import datetime, timedelta, timezone

from fastdm.scheduler import Schedule, Scheduler


def test_one_shot_schedule_is_due_and_disables_after_trigger():
    schedule = Schedule.once("task-1", datetime.now(timezone.utc) - timedelta(seconds=1))
    scheduler = Scheduler()
    scheduler.add(schedule)

    due = scheduler.due()
    assert due == [schedule]
    assert schedule.advance() is False
    assert not schedule.enabled


def test_recurring_schedule_advances_past_now():
    schedule = Schedule.recurring(
        "task-1", datetime.now(timezone.utc) - timedelta(seconds=10), interval=5
    )
    assert schedule.advance() is True
    assert schedule.enabled
    assert schedule.run_at > datetime.now(timezone.utc).timestamp()


def test_scheduler_add_remove_and_enable():
    scheduler = Scheduler()
    schedule = Schedule.once("task-1", datetime.now(timezone.utc))
    scheduler.add(schedule)
    assert scheduler.enable(schedule.id, False)
    assert scheduler.due() == []
    assert scheduler.remove(schedule.id)
    assert not scheduler.remove(schedule.id)
