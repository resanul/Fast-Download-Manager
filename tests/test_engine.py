from pathlib import Path

from fastdm.engine import DownloadEngine, DownloadTask


def test_engine_constructs():
    engine = DownloadEngine()
    assert 1 <= engine.connections <= 32


def test_task_defaults():
    task = DownloadTask("1", "https://example.com/a", Path("a"))
    assert task.status == "queued"
