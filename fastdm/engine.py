from __future__ import annotations

import asyncio
import hashlib
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse

import httpx


@dataclass
class Segment:
    start: int
    end: int
    downloaded: int = 0
    complete: bool = False


@dataclass
class DownloadTask:
    id: str
    url: str
    destination: Path
    total: int | None = None
    downloaded: int = 0
    speed: float = 0.0
    status: str = "queued"
    segments: list[Segment] = field(default_factory=list)
    created: float = field(default_factory=time.time)
    error: str | None = None
    checksum_algorithm: str | None = None
    expected_checksum: str | None = None
    actual_checksum: str | None = None


class DownloadEngine:
    """Async HTTP downloader with range-aware segmented downloads and recovery."""

    def __init__(self, connections: int = 8, chunk_size: int = 1024 * 1024, retries: int = 5):
        self.connections = max(1, min(connections, 32))
        self.chunk_size = max(64 * 1024, chunk_size)
        self.retries = max(1, min(retries, 10))
        self._tasks: dict[str, asyncio.Task] = {}
        self._pause: set[str] = set()
        self._cancel: set[str] = set()

    async def analyze(self, url: str) -> dict:
        p = urlparse(url)
        if p.scheme not in {"http", "https"} or not p.netloc:
            raise ValueError("Only valid HTTP/HTTPS URLs are supported")
        async with httpx.AsyncClient(follow_redirects=True, timeout=20) as client:
            r = await client.head(url)
            if r.status_code >= 400:
                r = await client.get(url, headers={"Range": "bytes=0-0"})
            length = r.headers.get("content-length")
            cr = r.headers.get("content-range", "")
            if not length and "/" in cr:
                length = cr.rsplit("/", 1)[-1]
            cd = r.headers.get("content-disposition", "")
            name = Path(urlparse(str(r.url)).path).name or Path(p.path).name or "download"
            if "filename=" in cd:
                name = cd.split("filename=", 1)[1].strip(' \";') or name
            return {
                "url": str(r.url),
                "filename": name,
                "size": int(length) if length and length.isdigit() else None,
                "mime": r.headers.get("content-type", "application/octet-stream"),
                "range": r.headers.get("accept-ranges", "").lower() == "bytes" or r.status_code == 206,
                "etag": r.headers.get("etag"),
                "last_modified": r.headers.get("last-modified"),
            }

    async def download(self, task: DownloadTask, progress=None) -> DownloadTask:
        self._cancel.discard(task.id)
        task.status = "analyzing"
        task.error = None
        try:
            meta = await self.analyze(task.url)
            task.url = meta["url"]
            task.total = meta["size"]
            task.status = "downloading"
            task.destination.parent.mkdir(parents=True, exist_ok=True)
            if task.total and meta["range"] and task.total >= 4 * 1024 * 1024:
                await self._segmented(task, progress)
            else:
                await self._single(task, progress)
            if task.checksum_algorithm and task.expected_checksum:
                task.actual_checksum = await asyncio.to_thread(self._hash_file, task.destination, task.checksum_algorithm)
                if task.actual_checksum.lower() != task.expected_checksum.lower():
                    task.destination.unlink(missing_ok=True)
                    raise RuntimeError("Checksum verification failed")
            task.status = "completed"
            task.speed = 0.0
            if progress:
                progress(task)
            return task
        except asyncio.CancelledError:
            task.status = "cancelled"
            if progress:
                progress(task)
            raise
        except Exception as exc:
            task.status = "failed"
            task.error = str(exc)
            if progress:
                progress(task)
            raise

    async def _single(self, task: DownloadTask, progress=None):
        temp = task.destination.with_suffix(task.destination.suffix + ".part")
        existing = temp.stat().st_size if temp.exists() else 0
        for attempt in range(self.retries):
            try:
                headers = {"Range": f"bytes={existing}-"} if existing else {}
                async with httpx.AsyncClient(follow_redirects=True, timeout=None) as client, client.stream(
                    "GET", task.url, headers=headers
                ) as r:
                    r.raise_for_status()
                    if existing and r.status_code != 206:
                        existing = 0
                        temp.unlink(missing_ok=True)
                        headers = {}
                        continue
                    await self._write_stream(task, r, temp, existing, progress)
                if task.total is None:
                    task.total = temp.stat().st_size
                if task.total is None or temp.stat().st_size == task.total:
                    os.replace(temp, task.destination)
                    return
                raise RuntimeError("Downloaded file size does not match expected size")
            except asyncio.CancelledError:
                raise
            except Exception:
                if attempt == self.retries - 1:
                    raise
                await asyncio.sleep(2**attempt)
                existing = temp.stat().st_size if temp.exists() else 0
        raise RuntimeError("Download failed")

    async def _write_stream(self, task, response, path, initial, progress):
        mode = "ab" if initial else "wb"
        done = initial
        started = time.monotonic()
        with path.open(mode) as f:
            async for chunk in response.aiter_bytes(self.chunk_size):
                while task.id in self._pause:
                    task.status = "paused"
                    if progress:
                        progress(task)
                    await asyncio.sleep(0.2)
                if task.id in self._cancel:
                    raise asyncio.CancelledError
                task.status = "downloading"
                f.write(chunk)
                f.flush()
                done += len(chunk)
                task.downloaded = done
                elapsed = max(time.monotonic() - started, 0.001)
                task.speed = max(0.0, (done - initial) / elapsed)
                if progress:
                    progress(task)

    async def _segmented(self, task, progress):
        total = int(task.total)
        n = min(self.connections, max(2, total // (8 * 1024 * 1024)))
        size = total // n
        tempdir = task.destination.parent / (task.destination.name + ".segments")
        tempdir.mkdir(exist_ok=True)
        task.segments = [Segment(i * size, total - 1 if i == n - 1 else (i + 1) * size - 1) for i in range(n)]
        lock = asyncio.Lock()

        async def worker(i, seg):
            part = tempdir / f"{i:04d}.part"
            have = min(part.stat().st_size if part.exists() else 0, seg.end - seg.start + 1)
            seg.downloaded = have
            start = seg.start + have
            if start > seg.end:
                seg.complete = True
                return
            async with httpx.AsyncClient(follow_redirects=True, timeout=None) as client:
                for attempt in range(self.retries):
                    try:
                        headers = {"Range": f"bytes={start}-{seg.end}"}
                        async with client.stream("GET", task.url, headers=headers) as r:
                            if r.status_code != 206:
                                raise RuntimeError("Server did not honor Range request")
                            with part.open("ab" if have else "wb") as f:
                                async for chunk in r.aiter_bytes(self.chunk_size):
                                    while task.id in self._pause:
                                        task.status = "paused"
                                        if progress:
                                            progress(task)
                                        await asyncio.sleep(0.2)
                                    if task.id in self._cancel:
                                        raise asyncio.CancelledError
                                    task.status = "downloading"
                                    f.write(chunk)
                                    f.flush()
                                    have += len(chunk)
                                    seg.downloaded = have
                                    async with lock:
                                        task.downloaded = sum(s.downloaded for s in task.segments)
                                    if progress:
                                        progress(task)
                            if have != seg.end - seg.start + 1:
                                raise RuntimeError("Segment size mismatch")
                            seg.complete = True
                            return
                    except asyncio.CancelledError:
                        raise
                    except Exception:
                        if attempt == self.retries - 1:
                            raise
                        await asyncio.sleep(2**attempt)
                        have = min(part.stat().st_size if part.exists() else 0, seg.end - seg.start + 1)
                        start = seg.start + have

        await asyncio.gather(*(worker(i, s) for i, s in enumerate(task.segments)))
        with task.destination.with_suffix(task.destination.suffix + ".part").open("wb") as out:
            for i in range(n):
                part = tempdir / f"{i:04d}.part"
                with part.open("rb") as src:
                    while chunk := src.read(self.chunk_size):
                        out.write(chunk)
        os.replace(task.destination.with_suffix(task.destination.suffix + ".part"), task.destination)
        for p in tempdir.glob("*.part"):
            p.unlink(missing_ok=True)
        tempdir.rmdir()

    @staticmethod
    def _hash_file(path: Path, algorithm: str) -> str:
        digest = hashlib.new(algorithm)
        with path.open("rb") as f:
            while chunk := f.read(1024 * 1024):
                digest.update(chunk)
        return digest.hexdigest()

    async def verify(self, path: Path, algorithm: str, expected: str) -> bool:
        actual = await asyncio.to_thread(self._hash_file, path, algorithm)
        return actual.lower() == expected.lower()

    def pause(self, task_id: str):
        self._pause.add(task_id)

    def resume(self, task_id: str):
        self._pause.discard(task_id)

    def cancel(self, task_id: str):
        self._cancel.add(task_id)

    def shutdown(self):
        for t in self._tasks.values():
            t.cancel()
        self._tasks.clear()
