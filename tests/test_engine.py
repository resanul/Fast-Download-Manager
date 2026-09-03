import asyncio
import hashlib
from pathlib import Path
from unittest.mock import patch

from fastdm.engine import DownloadEngine, DownloadTask, SpeedMeter


def test_engine_constructs():
    engine = DownloadEngine()
    assert 1 <= engine.connections <= 32
    assert engine.retries >= 1


def test_task_defaults():
    task = DownloadTask("1", "https://example.com/a", Path("a"))
    assert task.status == "queued"
    assert task.speed == 0.0
    assert task.peak_speed == 0.0


def test_hash_file(tmp_path):
    path = tmp_path / "payload.bin"
    path.write_bytes(b"fast-download-manager")
    expected = hashlib.sha256(path.read_bytes()).hexdigest()
    assert DownloadEngine._hash_file(path, "sha256") == expected


def test_verify(tmp_path):
    path = tmp_path / "payload.bin"
    path.write_bytes(b"verify-me")
    expected = hashlib.sha256(path.read_bytes()).hexdigest()
    assert asyncio.run(DownloadEngine().verify(path, "sha256", expected))
    assert not asyncio.run(DownloadEngine().verify(path, "sha256", "0" * 64))


def test_speed_reports_transferred_bytes():
    task = DownloadTask("1", "https://example.com/a", Path("a"))
    task.speed_started = 100.0
    task.speed_baseline = 0
    task.downloaded = 4 * 1024 * 1024
    task.speed_meter.reset(0)
    with patch("fastdm.engine.time.monotonic", return_value=102.0):
        task.speed_meter.baseline_time = 100.0
        task.speed_meter.last_time = 100.0
        speed = task.speed_meter.update(task.downloaded)
    assert speed == 2 * 1024 * 1024
    assert task.speed_meter.peak == speed


def test_speed_meter_tracks_peak_rate():
    meter = SpeedMeter()
    meter.reset(0)
    with patch("fastdm.engine.time.monotonic", side_effect=[101.0, 103.0]):
        first = meter.update(8 * 1024 * 1024)
        second = meter.update(12 * 1024 * 1024)
    assert first == 8 * 1024 * 1024
    assert second == 2 * 1024 * 1024
    assert meter.peak == first
