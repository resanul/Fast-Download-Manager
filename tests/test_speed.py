from fastdm.engine import DownloadTask, SpeedMeter
from pathlib import Path


def test_speed_meter_uses_rolling_window():
    meter = SpeedMeter(window_seconds=2.0)
    meter.reset(0)
    first = meter.samples[0][0]
    meter.samples.append((first + 1.0, 4 * 1024 * 1024))
    meter.samples.append((first + 2.0, 8 * 1024 * 1024))
    speed = meter.update(12 * 1024 * 1024)
    assert speed > 0
    assert meter.peak >= speed


def test_speed_meter_never_reports_negative_rate():
    meter = SpeedMeter()
    meter.reset(100)
    assert meter.update(50) == 0.0


def test_task_has_independent_speed_meter(tmp_path):
    task = DownloadTask(id="speed-test", url="https://example.com/file", destination=Path(tmp_path) / "file")
    assert task.speed_meter is not None
    task.speed_meter.reset(0)
    assert task.speed_meter.update(1024 * 1024) >= 0
