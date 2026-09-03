from pathlib import Path
from fastdm.engine import DownloadEngine, DownloadTask

def test_engine_constructs():
    e = DownloadEngine()
    assert 1 <= e.connections <= 32

def test_task_defaults():
    t = DownloadTask('1', 'https://example.com/a', Path('a'))
    assert t.status == 'queued'
