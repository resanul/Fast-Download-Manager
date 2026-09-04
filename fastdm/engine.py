from __future__ import annotations

import asyncio
import hashlib
import os
import shutil
import time
from collections import deque
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
class SpeedMeter:
    """Stable rolling throughput meter shared by single and segmented downloads."""

    window_seconds: float = 2.0
    baseline_bytes: int = 0
    baseline_time: float = field(default_factory=time.monotonic)
    samples: deque[tuple[float, int]] = field(default_factory=deque, repr=False)
    speed: float = 0.0
    peak: float = 0.0

    def reset(self, bytes_done: int = 0) -> None:
        now = time.monotonic()
        self.baseline_bytes = bytes_done
        self.baseline_time = now
        self.samples.clear()
        self.samples.append((now, bytes_done))
        self.speed = 0.0
        self.peak = 0.0

    def update(self, bytes_done: int) -> float:
        now = time.monotonic()
        if not self.samples:
            self.samples.append((now, bytes_done))
        elif bytes_done > self.samples[-1][1]:
            self.samples.append((now, bytes_done))

        cutoff = now - self.window_seconds
        while len(self.samples) > 1 and self.samples[1][0] <= cutoff:
            self.samples.popleft()

        if len(self.samples) >= 2:
            elapsed = max(now - self.samples[0][0], 0.001)
            delta = max(0, bytes_done - self.samples[0][1])
            if delta > 0:
                self.speed = delta / elapsed
                self.peak = max(self.peak, self.speed)
        return self.speed

    def average(self, bytes_done: int) -> float:
        elapsed = max(time.monotonic() - self.baseline_time, 0.001)
        return max(0, bytes_done - self.baseline_bytes) / elapsed


@dataclass
class DownloadTask:
    id: str
    url: str
    destination: Path
    total: int | None = None
    downloaded: int = 0
    speed: float = 0.0
    peak_speed: float = 0.0
    status: str = "queued"
    segments: list[Segment] = field(default_factory=list)
    created: float = field(default_factory=time.time)
    error: str | None = None
    checksum_algorithm: str | None = None
    expected_checksum: str | None = None
    actual_checksum: str | None = None
    speed_meter: SpeedMeter = field(default_factory=SpeedMeter, repr=False)


class DownloadEngine:
    """HTTP/HTTPS downloader with collision-safe resumable workspaces."""

    def __init__(self, connections: int = 8, chunk_size: int = 256 * 1024, retries: int = 5):
        self.connections = max(1, min(connections, 32))
        self.chunk_size = max(64 * 1024, chunk_size)
        self.retries = max(1, min(retries, 10))
        self._cancel: set[str] = set()
        self._pause: set[str] = set()

    @staticmethod
    def _workspace(task: DownloadTask) -> Path:
        return task.destination.parent / ".fastdm" / task.id

    async def analyze(self, url: str) -> dict:
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("Only valid HTTP/HTTPS URLs are supported")

        async with httpx.AsyncClient(follow_redirects=True, timeout=20) as client:
            response = await client.head(url)
            if response.status_code >= 400:
                response = await client.get(url, headers={"Range": "bytes=0-0"})
            content_range = response.headers.get("content-range", "")
            length = response.headers.get("content-length")
            if (not length or not length.isdigit()) and "/" in content_range:
                length = content_range.rsplit("/", 1)[-1]
            filename = Path(urlparse(str(response.url)).path).name or "download"
            disposition = response.headers.get("content-disposition", "")
            if "filename=" in disposition:
                candidate = disposition.split("filename=", 1)[1].strip(' \";\t')
                if candidate:
                    filename = candidate
            return {
                "url": str(response.url),
                "filename": filename,
                "size": int(length) if length and length.isdigit() else None,
                "mime": response.headers.get("content-type", "application/octet-stream"),
                "range": response.status_code == 206
                or response.headers.get("accept-ranges", "").lower() == "bytes",
                "etag": response.headers.get("etag"),
                "last_modified": response.headers.get("last-modified"),
            }

    async def download(self, task: DownloadTask, progress=None) -> DownloadTask:
        self._cancel.discard(task.id)
        self._pause.discard(task.id)
        task.status = "analyzing"
        task.error = None
        try:
            metadata = await self.analyze(task.url)
            task.url = metadata["url"]
            task.total = metadata["size"]
            task.status = "downloading"
            task.destination.parent.mkdir(parents=True, exist_ok=True)
            task.speed_meter.reset(task.downloaded)
            if task.total and metadata["range"] and task.total >= 4 * 1024 * 1024:
                await self._segmented(task, progress)
            else:
                await self._single(task, progress)
            if task.checksum_algorithm and task.expected_checksum:
                actual = await asyncio.to_thread(self._hash_file, task.destination, task.checksum_algorithm)
                task.actual_checksum = actual
                if actual.lower() != task.expected_checksum.lower():
                    task.destination.unlink(missing_ok=True)
                    raise RuntimeError("Checksum verification failed")
            task.speed = 0.0
            task.status = "completed"
            if progress:
                progress(task)
            return task
        except asyncio.CancelledError:
            task.speed = 0.0
            task.status = "cancelled"
            if progress:
                progress(task)
            raise
        except Exception as exc:
            task.speed = 0.0
            task.status = "failed"
            task.error = str(exc)
            if progress:
                progress(task)
            raise

    async def _single(self, task: DownloadTask, progress=None) -> None:
        workspace = self._workspace(task)
        workspace.mkdir(parents=True, exist_ok=True)
        temp = workspace / "download.part"
        existing = min(temp.stat().st_size if temp.exists() else 0, task.total or 2**63 - 1)
        task.downloaded = existing
        task.speed_meter.reset(existing)

        for attempt in range(self.retries):
            try:
                headers = {"Range": f"bytes={existing}-"} if existing else {}
                async with httpx.AsyncClient(follow_redirects=True, timeout=None) as client, client.stream("GET", task.url, headers=headers) as response:
                    response.raise_for_status()
                    if existing and response.status_code != 206:
                        existing = 0
                        temp.unlink(missing_ok=True)
                        task.downloaded = 0
                        task.speed_meter.reset(0)
                        continue
                    if existing and response.status_code == 206:
                        content_range = response.headers.get("content-range", "")
                        if not content_range.startswith(f"bytes {existing}-"):
                            existing = 0
                            temp.unlink(missing_ok=True)
                            task.downloaded = 0
                            task.speed_meter.reset(0)
                            continue
                    await self._write_stream(task, response, temp, existing, progress)

                if task.total is None:
                    task.total = temp.stat().st_size
                if temp.stat().st_size != task.total:
                    raise RuntimeError(f"Downloaded size mismatch: expected {task.total}, got {temp.stat().st_size}")
                os.replace(temp, task.destination)
                shutil.rmtree(workspace, ignore_errors=True)
                return
            except asyncio.CancelledError:
                raise
            except Exception:
                if attempt == self.retries - 1:
                    raise
                await asyncio.sleep(2**attempt)
                existing = temp.stat().st_size if temp.exists() else 0
        raise RuntimeError("Download failed")

    async def _write_stream(self, task, response, path: Path, initial: int, progress) -> None:
        mode = "ab" if initial else "wb"
        with path.open(mode) as output:
            async for chunk in response.aiter_bytes(self.chunk_size):
                while task.id in self._pause:
                    task.status = "paused"
                    task.speed = task.speed_meter.speed
                    if progress:
                        progress(task)
                    await asyncio.sleep(0.2)
                if task.id in self._cancel:
                    raise asyncio.CancelledError
                task.status = "downloading"
                output.write(chunk)
                output.flush()
                task.downloaded = output.tell() if not initial else initial + output.tell()
                task.speed = self._update_speed(task)
                task.peak_speed = max(task.peak_speed, task.speed_meter.peak)
                if progress:
                    progress(task)

    async def _segmented(self, task: DownloadTask, progress=None) -> None:
        total = int(task.total or 0)
        connections = min(self.connections, max(2, total // (8 * 1024 * 1024)))
        segment_size = total // connections
        workspace = self._workspace(task)
        workspace.mkdir(parents=True, exist_ok=True)
        task.segments = [Segment(i * segment_size, total - 1 if i == connections - 1 else (i + 1) * segment_size - 1) for i in range(connections)]

        for i, segment in enumerate(task.segments):
            part = workspace / f"segment-{i:04d}.part"
            segment.downloaded = min(part.stat().st_size if part.exists() else 0, segment.end - segment.start + 1)

        task.downloaded = sum(segment.downloaded for segment in task.segments)
        task.speed_meter.reset(task.downloaded)
        lock = asyncio.Lock()

        async def worker(index: int, segment: Segment) -> None:
            part = workspace / f"segment-{index:04d}.part"
            have = segment.downloaded
            start = segment.start + have
            if start > segment.end:
                segment.complete = True
                return

            async with httpx.AsyncClient(follow_redirects=True, timeout=None) as client:
                for attempt in range(self.retries):
                    try:
                        headers = {"Range": f"bytes={start}-{segment.end}"}
                        async with client.stream("GET", task.url, headers=headers) as response:
                            content_range = response.headers.get("content-range", "")
                            expected_prefix = f"bytes {start}-"
                            if response.status_code != 206 or not content_range.startswith(expected_prefix):
                                raise RuntimeError(f"Server did not honor Range request (HTTP {response.status_code})")
                            with part.open("ab" if have else "wb") as output:
                                async for chunk in response.aiter_bytes(self.chunk_size):
                                    while task.id in self._pause:
                                        task.status = "paused"
                                        task.speed = task.speed_meter.speed
                                        if progress:
                                            progress(task)
                                        await asyncio.sleep(0.2)
                                    if task.id in self._cancel:
                                        raise asyncio.CancelledError
                                    task.status = "downloading"
                                    output.write(chunk)
                                    output.flush()
                                    have += len(chunk)
                                    segment.downloaded = have
                                    async with lock:
                                        task.downloaded = sum(s.downloaded for s in task.segments)
                                        task.speed = self._update_speed(task)
                                        task.peak_speed = max(task.peak_speed, task.speed_meter.peak)
                                    if progress:
                                        progress(task)
                            if have != segment.end - segment.start + 1:
                                raise RuntimeError("Segment size mismatch")
                            segment.complete = True
                            return
                    except asyncio.CancelledError:
                        raise
                    except Exception:
                        if attempt == self.retries - 1:
                            raise
                        await asyncio.sleep(2**attempt)
                        have = min(part.stat().st_size if part.exists() else 0, segment.end - segment.start + 1)
                        start = segment.start + have

        await asyncio.gather(*(worker(i, segment) for i, segment in enumerate(task.segments)))

        output_temp = workspace / "assembled.part"
        with output_temp.open("wb") as output:
            for i in range(connections):
                part = workspace / f"segment-{i:04d}.part"
                with part.open("rb") as source:
                    while chunk := source.read(self.chunk_size):
                        output.write(chunk)

        if output_temp.stat().st_size != total:
            raise RuntimeError("Assembled file size mismatch")
        os.replace(output_temp, task.destination)
        shutil.rmtree(workspace, ignore_errors=True)

    @staticmethod
    def _hash_file(path: Path, algorithm: str) -> str:
        digest = hashlib.new(algorithm)
        with path.open("rb") as handle:
            while chunk := handle.read(1024 * 1024):
                digest.update(chunk)
        return digest.hexdigest()

    async def verify(self, path: Path, algorithm: str, expected: str) -> bool:
        actual = await asyncio.to_thread(self._hash_file, path, algorithm)
        return actual.lower() == expected.lower()

    @staticmethod
    def _update_speed(task: DownloadTask) -> float:
        rolling = task.speed_meter.update(task.downloaded)
        average = task.speed_meter.average(task.downloaded)
        if rolling > 0:
            return rolling
        if average > 0 and task.downloaded > task.speed_meter.baseline_bytes:
            return average
        return 0.0

    def pause(self, task_id: str) -> None:
        self._pause.add(task_id)

    def resume(self, task_id: str) -> None:
        self._pause.discard(task_id)

    def cancel(self, task_id: str) -> None:
        self._cancel.add(task_id)

    def cleanup(self, task: DownloadTask) -> None:
        shutil.rmtree(self._workspace(task), ignore_errors=True)
