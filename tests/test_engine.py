import asyncio
import hashlib
from collections import deque
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
    meter = task.speed_meter
    meter.reset(0)
    meter.samples = deque([(100.0, 0), (102.0, 4 * 1024 * 1024)])
    with patch("fastdm.engine.time.monotonic", return_value=102.0):
        speed = meter.update(4 * 1024 * 1024)
    assert speed == 2 * 1024 * 1024
    assert meter.peak == speed


def test_speed_meter_tracks_peak_rate():
    meter = SpeedMeter()
    meter.reset(0)
    with patch("fastdm.engine.time.monotonic", side_effect=[101.0, 103.0]):
        meter.samples = deque([(100.0, 0)])
        meter.update(8 * 1024 * 1024)
        meter.samples.append((102.0, 8 * 1024 * 1024))
        second = meter.update(12 * 1024 * 1024)
    assert second == 2 * 1024 * 1024
    assert meter.peak >= second


def test_speed_meter_never_reports_negative_rate():
    meter = SpeedMeter()
    meter.reset(100)
    assert meter.update(50) == 0.0


def test_task_has_independent_speed_meter(tmp_path):
    first = DownloadTask("one", "https://example.com/a", tmp_path / "a")
    second = DownloadTask("two", "https://example.com/b", tmp_path / "b")
    assert first.speed_meter is not second.speed_meter
    first.speed_meter.reset(0)
    assert first.speed_meter.update(1024 * 1024) >= 0
    assert second.speed_meter.speed == 0.0


def test_workspaces_are_unique_for_same_filename(tmp_path):
    first = DownloadTask("one", "https://example.com/file.zip", tmp_path / "file.zip")
    second = DownloadTask("two", "https://example.com/file.zip", tmp_path / "file.zip")
    assert DownloadEngine._workspace(first) != DownloadEngine._workspace(second)
    assert DownloadEngine._workspace(first).name == "one"
    assert DownloadEngine._workspace(second).name == "two"
