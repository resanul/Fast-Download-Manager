from pathlib import Path

from fastdm.db import Database


def test_database_round_trip(tmp_path: Path):
    db = Database(tmp_path / "downloads.db")
    db.upsert(
        {
            "id": "abc",
            "url": "https://example.com/file.bin",
            "filename": "file.bin",
            "destination": str(tmp_path / "file.bin"),
            "total": 100,
            "downloaded": 25,
            "status": "downloading",
            "speed": 12.5,
            "created": 1.0,
        }
    )
    rows = db.list()
    assert len(rows) == 1
    assert rows[0]["id"] == "abc"
    assert rows[0]["downloaded"] == 25
    db.close()


def test_database_upsert_updates_progress(tmp_path: Path):
    db = Database(tmp_path / "downloads.db")
    base = {
        "id": "abc",
        "url": "https://example.com/file.bin",
        "filename": "file.bin",
        "destination": str(tmp_path / "file.bin"),
        "total": 100,
        "downloaded": 25,
        "status": "downloading",
        "speed": 10,
        "created": 1.0,
    }
    db.upsert(base)
    base.update(downloaded=100, status="completed", speed=0)
    db.upsert(base)
    row = db.list()[0]
    assert row["downloaded"] == 100
    assert row["status"] == "completed"
    db.close()
