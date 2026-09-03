import asyncio
import hashlib
from pathlib import Path

from fastdm.engine import DownloadEngine, DownloadTask


def test_engine_constructs():
    engine = DownloadEngine()
    assert 1 <= engine.connections <= 32
    assert engine.retries >= 1


def test_task_defaults():
    task = DownloadTask("1", "https://example.com/a", Path("a"))
    assert task.status == "queued"


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
