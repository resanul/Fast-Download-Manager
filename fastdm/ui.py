from __future__ import annotations

import asyncio
import sys
import uuid
from pathlib import Path

from PySide6.QtCore import QObject, QThread, Signal, Slot
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .db import Database
from .engine import DownloadEngine, DownloadTask
from .queue import DownloadQueue, Priority


class Worker(QObject):
    progress = Signal(object)
    finished = Signal(object)
    failed = Signal(str)

    def __init__(self, engine: DownloadEngine, task: DownloadTask):
        super().__init__()
        self.engine = engine
        self.task = task

    @Slot()
    def run(self):
        try:
            result = asyncio.run(self.engine.download(self.task, self.progress.emit))
            self.finished.emit(result)
        except asyncio.CancelledError:
            self.finished.emit(self.task)
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc))


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Fast Download Manager")
        self.resize(1200, 760)
        self.engine = DownloadEngine()
        self.db = Database(self._db_path())
        saved_concurrency = int(self.db.get_setting("max_concurrent", "3") or 3)
        self.queue = DownloadQueue(max_concurrent=max(1, min(saved_concurrency, 8)))
        self.rows: dict[str, int] = {}
        self.tasks: dict[str, DownloadTask] = {}
        self.workers: dict[str, Worker] = {}
        self.threads: dict[str, QThread] = {}
        self.priorities: dict[str, Priority] = {}

        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)

        title = QLabel("Fast Download Manager")
        title.setObjectName("title")
        layout.addWidget(title)

        bar = QHBoxLayout()
        self.url = QLineEdit()
        self.url.setPlaceholderText("Paste a download URL…")
        self.url.returnPressed.connect(self.add_download)
        bar.addWidget(self.url, 1)
        self.priority = QComboBox()
        self.priority.addItem("High", Priority.HIGH)
        self.priority.addItem("Normal", Priority.NORMAL)
        self.priority.addItem("Low", Priority.LOW)
        bar.addWidget(self.priority)
        add = QPushButton("+ Add Download")
        add.clicked.connect(self.add_download)
        bar.addWidget(add)
        layout.addLayout(bar)

        controls = QHBoxLayout()
        for label, callback in (
            ("Pause", self.pause_selected),
            ("Resume", self.resume_selected),
            ("Cancel", self.cancel_selected),
            ("Retry", self.retry_selected),
            ("Open Folder", self.open_folder_selected),
        ):
            button = QPushButton(label)
            button.clicked.connect(callback)
            controls.addWidget(button)
        controls.addWidget(QLabel("Max concurrent:"))
        self.concurrency = QSpinBox()
        self.concurrency.setRange(1, 8)
        self.concurrency.setValue(self.queue.max_concurrent)
        self.concurrency.valueChanged.connect(self.set_concurrency)
        controls.addWidget(self.concurrency)
        controls.addStretch(1)
        layout.addLayout(controls)

        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(
            ["File", "Status", "Progress", "Speed", "Size", "Priority", "Destination"]
        )
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.table)

        self.status = QLabel("Ready")
        layout.addWidget(self.status)
        self.setStyleSheet(
            "QMainWindow{background:#101318;color:#eee}"
            "QLabel#title{font-size:28px;font-weight:700;margin:12px}"
            "QLineEdit,QTableWidget,QComboBox,QSpinBox{background:#181c23;color:#eee;border:1px solid #303744;border-radius:8px;padding:8px}"
            "QPushButton{background:#2563eb;color:white;border:0;border-radius:8px;padding:10px 16px;font-weight:600}"
            "QHeaderView::section{background:#222733;color:#bbb;padding:8px}"
        )
        self.load_history()
        self._update_queue_status()
        self._pump_queue()

    @staticmethod
    def _db_path() -> Path:
        base = Path.home() / "AppData" / "Local" / "FastDownloadManager"
        if sys.platform != "win32":
            base = Path.home() / ".local" / "share" / "fast-download-manager"
        return base / "downloads.db"

    def load_history(self):
        for item in self.db.list():
            try:
                priority = Priority(int(item["priority"] or Priority.NORMAL))
            except (ValueError, TypeError):
                priority = Priority.NORMAL
            status = item["status"]
            task = None
            if status in {"queued", "paused", "analyzing", "downloading"}:
                task = DownloadTask(
                    item["id"],
                    item["url"],
                    Path(item["destination"]),
                    total=item["total"],
                    downloaded=item["downloaded"] or 0,
                    status="queued",
                    created=item["created"],
                )
                self.tasks[task.id] = task
                self.priorities[task.id] = priority
                self.queue.enqueue(task.id, priority)
                status = "queued"
            row = self._insert_row(
                item["id"],
                item["filename"],
                status,
                item["downloaded"],
                item["total"],
                item["speed"],
                item["destination"],
                priority,
            )
            self.rows[item["id"]] = row

    def _insert_row(self, task_id, name, status, downloaded, total, speed, destination, priority):
        row = self.table.rowCount()
        self.table.insertRow(row)
        values = [
            name,
            status,
            self._percent(downloaded, total),
            f"{speed / 1048576:.2f} MB/s" if speed else "0.00 MB/s",
            self.fmt(total),
            priority.name.title(),
            destination,
        ]
        for col, value in enumerate(values):
            self.table.setItem(row, col, QTableWidgetItem(str(value)))
        return row

    def add_download(self):
        url = self.url.text().strip()
        if not url:
            self.status.setText("Enter a download URL")
            return
        folder = QFileDialog.getExistingDirectory(self, "Choose download folder")
        if not folder:
            return
        name = Path(url.split("?", 1)[0]).name or "download"
        task = DownloadTask(uuid.uuid4().hex, url, Path(folder) / name)
        priority = Priority(self.priority.currentData())
        self.tasks[task.id] = task
        self.priorities[task.id] = priority
        self.rows[task.id] = self._insert_row(
            task.id, name, "queued", 0, None, 0, str(task.destination), priority
        )
        self.queue.enqueue(task.id, priority)
        self._save(task)
        self.url.clear()
        self._pump_queue()

    def set_concurrency(self, value: int):
        self.queue.max_concurrent = max(1, value)
        self.db.set_setting("max_concurrent", str(self.queue.max_concurrent))
        self._pump_queue()
        self._update_queue_status()

    def _pump_queue(self):
        while self.queue.active_count < self.queue.max_concurrent:
            item = self.queue.next_ready()
            if not item or not self.queue.mark_started(item.task_id):
                break
            task = self.tasks.get(item.task_id)
            if not task:
                self.queue.mark_finished(item.task_id)
                continue
            task.status = "queued"
            self.progress(task)
            self._start(task)
        self._update_queue_status()

    def _start(self, task: DownloadTask):
        thread = QThread(self)
        worker = Worker(self.engine, task)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.progress.connect(self.progress)
        worker.finished.connect(self.done)
        worker.failed.connect(lambda error, task_id=task.id: self.fail(task_id, error))
        worker.finished.connect(thread.quit)
        worker.failed.connect(thread.quit)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        self.workers[task.id] = worker
        self.threads[task.id] = thread
        thread.finished.connect(lambda task_id=task.id: self._cleanup_thread(task_id))
        thread.start()

    def _cleanup_thread(self, task_id: str):
        self.workers.pop(task_id, None)
        self.threads.pop(task_id, None)

    def progress(self, task: DownloadTask):
        if task.id not in self.rows:
            return
        row = self.rows[task.id]
        total = task.total or 0
        self.table.item(row, 1).setText(task.status)
        self.table.item(row, 2).setText(self._percent(task.downloaded, total))
        self.table.item(row, 3).setText(f"{task.speed / 1048576:.2f} MB/s")
        self.table.item(row, 4).setText(self.fmt(total))
        self._save(task)
        self._update_queue_status()

    def done(self, task: DownloadTask):
        self.queue.mark_finished(task.id)
        self.progress(task)
        self.status.setText(f"Download {task.status}")
        self._pump_queue()

    def fail(self, task_id: str, error: str):
        self.queue.mark_finished(task_id)
        task = self.tasks.get(task_id)
        if task:
            task.status = "failed"
            task.error = error
            self._save(task)
            self.progress(task)
        self.status.setText("Download failed: " + error)
        self._pump_queue()

    def _selected_task(self):
        selected = self.table.selectionModel().selectedRows()
        if not selected:
            return None
        row = selected[0].row()
        for task_id, task_row in self.rows.items():
            if task_row == row:
                return self.tasks.get(task_id)
        return None

    def pause_selected(self):
        task = self._selected_task()
        if task:
            self.engine.pause(task.id)
            task.status = "paused"
            self.progress(task)

    def resume_selected(self):
        task = self._selected_task()
        if task:
            self.engine.resume(task.id)
            if task.status == "paused":
                task.status = "downloading"
            self.progress(task)

    def cancel_selected(self):
        task = self._selected_task()
        if task:
            self.engine.cancel(task.id)
            task.status = "cancelled"
            self.progress(task)

    def retry_selected(self):
        task = self._selected_task()
        if task and task.status in {"failed", "cancelled"}:
            self.engine.resume(task.id)
            self.engine._cancel.discard(task.id)
            self.queue.enqueue(task.id, self.priorities.get(task.id, Priority.NORMAL))
            task.status = "queued"
            self.progress(task)
            self._pump_queue()

    def open_folder_selected(self):
        task = self._selected_task()
        if not task:
            return
        import os
        os.startfile(task.destination.parent) if sys.platform == "win32" else None

    def _update_queue_status(self):
        self.status.setText(
            f"Queue {self.queue.pending_count} · Active {self.queue.active_count}/{self.queue.max_concurrent}"
        )

    def _save(self, task: DownloadTask):
        self.db.upsert(
            {
                "id": task.id,
                "url": task.url,
                "filename": task.destination.name,
                "destination": str(task.destination),
                "total": task.total,
                "downloaded": task.downloaded,
                "status": task.status,
                "speed": task.speed,
                "created": task.created,
                "priority": int(self.priorities.get(task.id, Priority.NORMAL)),
            }
        )

    @staticmethod
    def _percent(done, total):
        return f"{done * 100 / total:.1f}%" if total else "0.0%"

    @staticmethod
    def fmt(n):
        if not n:
            return "Unknown"
        for unit in ("B", "KB", "MB", "GB", "TB"):
            if n < 1024:
                return f"{n:.1f} {unit}"
            n /= 1024
        return f"{n:.1f} PB"

    def closeEvent(self, event):
        self.engine.shutdown()
        self.db.close()
        event.accept()


def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    return app.exec()
