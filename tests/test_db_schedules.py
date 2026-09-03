from pathlib import Path

from fastdm.db import Database


def test_schedule_persistence(tmp_path: Path):
    db = Database(tmp_path / "downloads.db")
    db.upsert_schedule({"id": "s1", "task_id": "t1", "run_at": 123.5, "interval": 60, "enabled": True})
    row = db.list_schedules()[0]
    assert row["id"] == "s1"
    assert row["task_id"] == "t1"
    assert row["run_at"] == 123.5
    assert row["interval"] == 60
    assert row["enabled"] == 1
    db.delete_schedule("s1")
    assert db.list_schedules() == []
    db.close()
