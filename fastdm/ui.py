from __future__ import annotations

import asyncio
import os
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path

from PySide6.QtCore import QDateTime, QObject, QThread, QTimer, Signal, Slot
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDateTimeEdit,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QStyle,
    QSystemTrayIcon,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .db import Database
from .engine import DownloadEngine, DownloadTask
from .queue import DownloadQueue, Priority
from .scheduler import Schedule, Scheduler


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


class ScheduleDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Schedule Download")
        self.resize(440, 180)
        form = QFormLayout(self)
        self.when = QDateTimeEdit(QDateTime.currentDateTime().addSecs(60))
        self.when.setCalendarPopup(True)
        self.when.setDisplayFormat("yyyy-MM-dd HH:mm:ss")
        form.addRow("Start at", self.when)
        self.recurring = QCheckBox("Repeat automatically")
        form.addRow("Recurrence", self.recurring)
        self.interval = QSpinBox()
        self.interval.setRange(1, 10080)
        self.interval.setValue(60)
        self.interval.setSuffix(" minutes")
        self.interval.setEnabled(False)
        self.recurring.toggled.connect(self.interval.setEnabled)
        form.addRow("Every", self.interval)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def values(self) -> tuple[datetime, float | None]:
        run_at = datetime.fromtimestamp(self.when.dateTime().toSecsSinceEpoch(), tz=UTC)
        interval = self.interval.value() * 60.0 if self.recurring.isChecked() else None
        return run_at, interval


class StatCard(QFrame):
    def __init__(self, title: str, value: str, subtitle: str):
        super().__init__()
        self.setObjectName("statCard")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        label = QLabel(title.upper())
        label.setObjectName("statLabel")
        number = QLabel(value)
        number.setObjectName("statValue")
        detail = QLabel(subtitle)
        detail.setObjectName("statDetail")
        layout.addWidget(label)
        layout.addWidget(number)
        layout.addWidget(detail)
        self.value_label = number

    def set_value(self, value: str):
        self.value_label.setText(value)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Fast Download Manager")
        self.resize(1360, 860)
        self.setMinimumSize(1100, 700)
        self.engine = DownloadEngine()
        self.db = Database(self._db_path())
        self.queue = DownloadQueue(max_concurrent=self._get_concurrency())
        self.scheduler = Scheduler()
        self.schedules: dict[str, Schedule] = {}
        self.rows: dict[str, int] = {}
        self.tasks: dict[str, DownloadTask] = {}
        self.workers: dict[str, Worker] = {}
        self.threads: dict[str, QThread] = {}
        self.priorities: dict[str, Priority] = {}
        self._delete_after_finish: set[str] = set()
        self._force_exit = False
        self._filter = "all"
        self._build_shell()
        self._setup_tray()
        self.load_history()
        self.load_schedules()
        self._schedule_timer = QTimer(self)
        self._schedule_timer.setInterval(1000)
        self._schedule_timer.timeout.connect(self._process_schedules)
        self._schedule_timer.start()
        self._refresh_stats()
        self._pump_queue()

    @staticmethod
    def _db_path() -> Path:
        if sys.platform == "win32":
            return Path.home() / "AppData" / "Local" / "FastDownloadManager" / "downloads.db"
        return Path.home() / ".local" / "share" / "fast-download-manager" / "downloads.db"

    def _get_concurrency(self) -> int:
        try:
            return max(1, min(8, int(self.db.get_setting("max_concurrent", "3") or 3)))
        except ValueError:
            return 3

    def _build_shell(self):
        root = QWidget()
        self.setCentralWidget(root)
        main = QHBoxLayout(root)
        main.setContentsMargins(0, 0, 0, 0)
        main.setSpacing(0)

        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(215)
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(14, 18, 14, 18)
        brand = QLabel("FD  Fast Download\nManager")
        brand.setObjectName("brand")
        side.addWidget(brand)
        side.addSpacing(16)
        self.nav_buttons = {}
        for key, text in (("all", "All Downloads"), ("active", "Active"), ("completed", "Completed"), ("queued", "Queued"), ("paused", "Paused"), ("failed", "Errors"), ("scheduled", "Scheduler")):
            button = QPushButton(text)
            button.setCheckable(True)
            button.clicked.connect(lambda checked=False, k=key: self.set_filter(k))
            self.nav_buttons[key] = button
            side.addWidget(button)
        side.addSpacing(14)
        library = QLabel("LIBRARY")
        library.setObjectName("sectionLabel")
        side.addWidget(library)
        for key, text in (("documents", "Documents"), ("archives", "Compressed"), ("music", "Music"), ("videos", "Videos")):
            button = QPushButton(text)
            button.clicked.connect(lambda checked=False, k=key: self.set_filter(k))
            side.addWidget(button)
        side.addStretch(1)
        self.nav_status = QLabel("Ready")
        self.nav_status.setObjectName("navStatus")
        side.addWidget(self.nav_status)
        main.addLayout(side)

        content = QFrame()
        content.setObjectName("content")
        body = QVBoxLayout(content)
        body.setContentsMargins(24, 20, 24, 18)
        body.setSpacing(12)
        header = QHBoxLayout()
        title_box = QVBoxLayout()
        title = QLabel("Downloads")
        title.setObjectName("pageTitle")
        subtitle = QLabel("Fast, reliable and organized downloads")
        subtitle.setObjectName("pageSubtitle")
        title_box.addWidget(title)
        title_box.addWidget(subtitle)
        header.addLayout(title_box)
        header.addStretch(1)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search downloads...")
        self.search.setClearButtonEnabled(True)
        self.search.setFixedWidth(280)
        self.search.textChanged.connect(self._apply_filters)
        header.addWidget(self.search)
        body.addLayout(header)

        actions = QHBoxLayout()
        add = QPushButton("+  New Download")
        add.setObjectName("primary")
        add.clicked.connect(self.add_download)
        actions.addWidget(add)
        for text, callback in (("Start All", self.resume_all), ("Pause All", self.pause_all), ("Schedule", self.schedule_selected), ("Open Folder", self.open_folder_selected), ("Delete", self.delete_selected)):
            button = QPushButton(text)
            button.clicked.connect(callback)
            actions.addWidget(button)
        actions.addStretch(1)
        actions.addWidget(QLabel("Concurrent"))
        self.concurrency = QSpinBox()
        self.concurrency.setRange(1, 8)
        self.concurrency.setValue(self.queue.max_concurrent)
        self.concurrency.valueChanged.connect(self.set_concurrency)
        actions.addWidget(self.concurrency)
        body.addLayout(actions)

        stats = QHBoxLayout()
        self.stat_total = StatCard("Total", "0", "all downloads")
        self.stat_active = StatCard("Active", "0", "currently downloading")
        self.stat_queued = StatCard("Queued", "0", "waiting to start")
        self.stat_speed = StatCard("Speed", "0 B/s", "current aggregate")
        for card in (self.stat_total, self.stat_active, self.stat_queued, self.stat_speed):
            card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            stats.addWidget(card)
        body.addLayout(stats)

        tabs = QHBoxLayout()
        self.filter_buttons = {}
        for key, text in (("all", "All"), ("active", "Active"), ("completed", "Completed"), ("queued", "Queued"), ("failed", "Errors")):
            button = QPushButton(text)
            button.setObjectName("tabButton")
            button.setCheckable(True)
            button.clicked.connect(lambda checked=False, k=key: self.set_filter(k))
            self.filter_buttons[key] = button
            tabs.addWidget(button)
        tabs.addStretch(1)
        self.filter_hint = QLabel("All downloads")
        self.filter_hint.setObjectName("filterHint")
        tabs.addWidget(self.filter_hint)
        body.addLayout(tabs)

        self.table = QTableWidget(0, 7)
        self.table.setObjectName("downloadsTable")
        self.table.setHorizontalHeaderLabels(["File", "Progress", "Size", "Status", "Speed", "Priority", "Actions"])
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.ExtendedSelection)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.setShowGrid(False)
        header_view = self.table.horizontalHeader()
        header_view.setStretchLastSection(False)
        header_view.setSectionResizeMode(0, header_view.ResizeMode.Stretch)
        for index in range(1, 7):
            header_view.setSectionResizeMode(index, header_view.ResizeMode.ResizeToContents)
        body.addWidget(self.table, 1)

        footer = QHBoxLayout()
        self.status = QLabel("Ready")
        self.status.setObjectName("statusLine")
        footer.addWidget(self.status)
        footer.addStretch(1)
        self.connection_status = QLabel("●  System ready")
        self.connection_status.setObjectName("healthy")
        footer.addWidget(self.connection_status)
        body.addLayout(footer)
        main.addWidget(content, 1)
        self._apply_theme()
        self.set_filter("all")

    def _apply_theme(self):
        self.setStyleSheet(
            """
            QMainWindow, QWidget#content { background: #0f141a; color: #e8edf2; }
            QFrame#sidebar { background: #11171e; border-right: 1px solid #27303a; }
            QLabel#brand { color: #f4f7fa; font-size: 18px; font-weight: 700; }
            QLabel#pageTitle { color: #f6f8fa; font-size: 30px; font-weight: 750; }
            QLabel#pageSubtitle { color: #8e99a5; font-size: 13px; }
            QLabel#sectionLabel { color: #66727e; font-size: 10px; font-weight: 700; padding: 8px 3px 2px; }
            QLabel#navStatus, QLabel#filterHint, QLabel#statusLine { color: #778391; font-size: 12px; }
            QPushButton { background: #1a222b; border: 1px solid #2b3540; color: #cfd6de; border-radius: 8px; padding: 9px 12px; }
            QPushButton:hover { background: #202a35; }
            QPushButton:checked { background: #26323e; color: #ffffff; border-color: #3e4c59; }
            QPushButton#primary { background: #20aeb0; border-color: #20aeb0; color: white; font-weight: 700; }
            QPushButton#primary:hover { background: #25c0c2; }
            QPushButton#tabButton { border: 0; background: transparent; padding: 7px 11px; }
            QPushButton#tabButton:checked { background: #1b2833; color: #ffffff; }
            QLineEdit, QComboBox, QSpinBox, QDateTimeEdit { background: #161d25; border: 1px solid #2b3540; color: #e5ebf0; border-radius: 8px; padding: 8px 10px; }
            QTableWidget#downloadsTable { background: #11171e; border: 1px solid #27303a; border-radius: 10px; color: #e6ebef; }
            QTableWidget#downloadsTable::item { padding: 7px 6px; border-bottom: 1px solid #202932; }
            QTableWidget#downloadsTable::item:selected { background: #1c2b35; }
            QHeaderView::section { background: #141b23; color: #7f8b97; border: 0; border-bottom: 1px solid #27303a; padding: 8px; font-size: 11px; font-weight: 700; }
            QFrame#statCard { background: #141b22; border: 1px solid #27313b; border-radius: 10px; }
            QLabel#statLabel { color: #6f7b86; font-size: 10px; font-weight: 700; }
            QLabel#statValue { color: #f3f6f8; font-size: 23px; font-weight: 750; }
            QLabel#statDetail { color: #7f8a95; font-size: 11px; }
            QLabel#healthy { color: #62d28a; font-size: 12px; }
            QProgressBar { background: #232b34; border: 0; border-radius: 5px; text-align: center; color: #e8edf2; min-width: 160px; max-width: 240px; height: 11px; }
            QProgressBar::chunk { background: #1db4b6; border-radius: 5px; }
            """
        )

    def _setup_tray(self):
        self.tray = None
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return
        self.tray = QSystemTrayIcon(self)
        self.tray.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_ComputerIcon))
        self.tray.setToolTip("Fast Download Manager")
        menu = QMenu()
        show = menu.addAction("Show Fast Download Manager")
        show.triggered.connect(self._restore_from_tray)
        menu.addSeparator()
        menu.addAction("Pause All", self.pause_all)
        menu.addAction("Resume All", self.resume_all)
        menu.addSeparator()
        menu.addAction("Exit", self.exit_application)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(lambda reason: self._restore_from_tray())
        self.tray.show()

    def _restore_from_tray(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def _notify(self, title: str, message: str):
        if self.tray and QSystemTrayIcon.supportsMessages():
            self.tray.showMessage(title, message, QSystemTrayIcon.MessageIcon.Information, 4000)

    def set_filter(self, key: str):
        self._filter = key
        all_buttons = {**self.nav_buttons, **self.filter_buttons}
        for name, button in all_buttons.items():
            button.blockSignals(True)
            button.setChecked(name == key)
            button.blockSignals(False)
        labels = {"all": "All downloads", "active": "Active downloads", "completed": "Completed downloads", "queued": "Queued downloads", "paused": "Paused downloads", "failed": "Failed downloads", "scheduled": "Scheduled downloads", "documents": "Documents", "archives": "Compressed files", "music": "Music", "videos": "Videos"}
        self.filter_hint.setText(labels.get(key, "All downloads"))
        self._apply_filters()

    def _status_matches(self, task: DownloadTask) -> bool:
        key = self._filter
        if key == "all":
            return True
        if key == "active":
            return task.status in {"analyzing", "downloading"}
        if key == "completed":
            return task.status == "completed"
        if key == "queued":
            return task.status == "queued"
        if key == "paused":
            return task.status == "paused"
        if key == "failed":
            return task.status == "failed"
        if key == "scheduled":
            return task.status == "scheduled"
        categories = {"documents": {".pdf", ".doc", ".docx", ".txt", ".xlsx", ".csv"}, "archives": {".zip", ".rar", ".7z", ".tar", ".gz", ".bz2", ".xz"}, "music": {".mp3", ".wav", ".flac", ".aac", ".m4a"}, "videos": {".mp4", ".mkv", ".avi", ".mov", ".webm"}}
        return task.destination.suffix.lower() in categories.get(key, set())

    def _apply_filters(self):
        query = self.search.text().strip().lower()
        visible = 0
        for task_id, row in self.rows.items():
            task = self.tasks.get(task_id)
            if not task:
                continue
            show = self._status_matches(task) and (not query or query in task.destination.name.lower() or query in task.url.lower())
            self.table.setRowHidden(row, not show)
            visible += int(show)
        self.nav_status.setText(f"Showing {visible} download{'s' if visible != 1 else ''}")

    def load_history(self):
        for item in self.db.list():
            try:
                priority = Priority(int(item["priority"] or Priority.NORMAL))
            except (ValueError, TypeError):
                priority = Priority.NORMAL
            task = DownloadTask(item["id"], item["url"], Path(item["destination"]), total=item["total"], downloaded=item["downloaded"] or 0, status=item["status"], created=item["created"])
            if task.status in {"queued", "paused", "analyzing", "downloading"}:
                task.status = "queued"
                self.queue.enqueue(task.id, priority)
            self.tasks[task.id] = task
            self.priorities[task.id] = priority
            row = self._insert_row(task.id, task.destination.name, task.status, task.downloaded, task.total, task.speed, priority)
            self.rows[task.id] = row
        self._apply_filters()

    def load_schedules(self):
        for item in self.db.list_schedules():
            schedule = Schedule(item["id"], item["task_id"], float(item["run_at"]), float(item["interval"]) if item["interval"] is not None else None, bool(item["enabled"]))
            if schedule.task_id in self.tasks and schedule.enabled:
                self.scheduler.add(schedule)
                self.schedules[schedule.id] = schedule
                self.tasks[schedule.task_id].status = "scheduled"
                self.progress(self.tasks[schedule.task_id])

    def _insert_row(self, task_id, name, status, downloaded, total, speed, priority):
        row = self.table.rowCount()
        self.table.insertRow(row)
        self.table.setRowHeight(row, 58)
        self.table.setItem(row, 0, QTableWidgetItem(name))
        progress = QProgressBar()
        progress.setRange(0, 100)
        progress.setValue(min(100, int(downloaded * 100 / total)) if total else 0)
        progress.setFormat("%p%")
        progress_widget = QWidget()
        progress_layout = QHBoxLayout(progress_widget)
        progress_layout.setContentsMargins(7, 0, 7, 0)
        progress_layout.addWidget(progress)
        self.table.setCellWidget(row, 1, progress_widget)
        self.table.setItem(row, 2, QTableWidgetItem(self.fmt(total)))
        self.table.setItem(row, 3, QTableWidgetItem(self._pretty_status(status)))
        self.table.setItem(row, 4, QTableWidgetItem(self._format_rate(speed)))
        self.table.setItem(row, 5, QTableWidgetItem(priority.name.title()))
        action_widget = QWidget()
        action_layout = QHBoxLayout(action_widget)
        action_layout.setContentsMargins(2, 0, 2, 0)
        for symbol, tip, callback in (("Ⅱ", "Pause", self._row_pause), ("▶", "Resume / Retry", self._row_resume), ("🗑", "Delete", self._row_delete)):
            button = QPushButton(symbol)
            button.setToolTip(tip)
            button.setFixedSize(34, 32)
            button.clicked.connect(lambda checked=False, tid=task_id, func=callback: func(tid))
            action_layout.addWidget(button)
        self.table.setCellWidget(row, 6, action_widget)
        return row

    @staticmethod
    def _pretty_status(status: str) -> str:
        return {"analyzing": "Analyzing", "downloading": "Downloading", "completed": "Completed", "queued": "Queued", "paused": "Paused", "failed": "Error", "scheduled": "Scheduled", "cancelled": "Cancelled"}.get(status, status.title())

    def add_download(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("New Download")
        dialog.resize(640, 170)
        form = QFormLayout(dialog)
        url_edit = QLineEdit()
        url_edit.setPlaceholderText("https://example.com/file.iso")
        priority = QComboBox()
        priority.addItem("High", Priority.HIGH)
        priority.addItem("Normal", Priority.NORMAL)
        priority.addItem("Low", Priority.LOW)
        form.addRow("URL", url_edit)
        form.addRow("Priority", priority)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        form.addRow(buttons)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._create_download(url_edit.text().strip(), Priority(priority.currentData()))

    @staticmethod
    def _safe_filename(name: str) -> str:
        invalid = '<>:"/\\|?*'
        cleaned = "".join("_" if char in invalid else char for char in name).strip(" .")
        return cleaned or "download"

    def _unique_destination(self, folder: Path, name: str) -> Path:
        name = self._safe_filename(name)
        candidate = folder / name
        stem = candidate.stem
        suffix = candidate.suffix
        index = 1
        while candidate.exists():
            candidate = folder / f"{stem} ({index}){suffix}"
            index += 1
        return candidate

    def _create_download(self, url: str, priority: Priority):
        if not url:
            self.status.setText("Enter a download URL")
            return
        folder_name = QFileDialog.getExistingDirectory(self, "Choose download folder")
        if not folder_name:
            return
        parsed_name = Path(url.split("?", 1)[0]).name or "download"
        destination = self._unique_destination(Path(folder_name), parsed_name)
        task = DownloadTask(uuid.uuid4().hex, url, destination)
        self.tasks[task.id] = task
        self.priorities[task.id] = priority
        self.rows[task.id] = self._insert_row(task.id, destination.name, "queued", 0, None, 0, priority)
        self.queue.enqueue(task.id, priority)
        self._save(task)
        self._pump_queue()
        self._apply_filters()
        self.status.setText(f"Added {destination.name}")

    def set_concurrency(self, value: int):
        self.queue.max_concurrent = max(1, min(8, value))
        self.db.set_setting("max_concurrent", str(self.queue.max_concurrent))
        self._pump_queue()

    def _pump_queue(self):
        while self.queue.active_count < self.queue.max_concurrent:
            item = self.queue.next_ready()
            if not item or not self.queue.mark_started(item.task_id):
                break
            task = self.tasks.get(item.task_id)
            if not task:
                self.queue.mark_finished(item.task_id)
                continue
            task.status = "analyzing"
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
        worker.failed.connect(lambda error, tid=task.id: self.fail(tid, error))
        worker.finished.connect(thread.quit)
        worker.failed.connect(thread.quit)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        self.workers[task.id] = worker
        self.threads[task.id] = thread
        thread.finished.connect(lambda tid=task.id: self._cleanup_thread(tid))
        thread.start()

    def _cleanup_thread(self, task_id: str):
        self.workers.pop(task_id, None)
        self.threads.pop(task_id, None)

    def progress(self, task: DownloadTask):
        row = self.rows.get(task.id)
        if row is None:
            return
        bar_widget = self.table.cellWidget(row, 1)
        if bar_widget:
            bar = bar_widget.findChild(QProgressBar)
            if bar:
                bar.setValue(min(100, int(task.downloaded * 100 / task.total)) if task.total else 0)
        self.table.item(row, 2).setText(self.fmt(task.total))
        self.table.item(row, 3).setText(self._pretty_status(task.status))
        self.table.item(row, 4).setText(self._format_rate(task.speed))
        self.table.item(row, 5).setText(self.priorities.get(task.id, Priority.NORMAL).name.title())
        self._save(task)
        self._refresh_stats()
        self._apply_filters()

    def done(self, task: DownloadTask):
        self.queue.mark_finished(task.id)
        if task.id in self._delete_after_finish:
            self._delete_after_finish.discard(task.id)
            self._remove_task_from_ui(task.id, delete_files=True)
            self._pump_queue()
            return
        self.progress(task)
        if task.status == "completed":
            self._notify("Download complete", task.destination.name)
        self.status.setText(f"Download {task.status}")
        self._pump_queue()

    def fail(self, task_id: str, error: str):
        self.queue.mark_finished(task_id)
        task = self.tasks.get(task_id)
        if not task:
            return
        if task_id in self._delete_after_finish:
            self._delete_after_finish.discard(task_id)
            self._remove_task_from_ui(task_id, delete_files=True)
            self._pump_queue()
            return
        task.status = "failed"
        task.error = error
        task.speed = 0.0
        self._save(task)
        self.progress(task)
        self._notify("Download failed", f"{task.destination.name}: {error}")
        self.status.setText("Download failed")
        QMessageBox.warning(self, "Download failed", f"{task.destination.name}\n\n{error}")
        self._pump_queue()

    def _remove_task_from_ui(self, task_id: str, delete_files: bool):
        task = self.tasks.get(task_id)
        if not task:
            return
        for schedule_id, schedule in list(self.schedules.items()):
            if schedule.task_id == task_id:
                self.scheduler.remove(schedule_id)
                self.db.delete_schedule(schedule_id)
                self.schedules.pop(schedule_id, None)
        row = self.rows.pop(task_id, None)
        if row is not None:
            self.table.removeRow(row)
            for tid, current_row in list(self.rows.items()):
                if current_row > row:
                    self.rows[tid] = current_row - 1
        self.priorities.pop(task_id, None)
        self.tasks.pop(task_id, None)
        self.db.delete_download(task_id)
        if delete_files:
            self.engine.cleanup(task)

    def _row_delete(self, task_id: str):
        task = self.tasks.get(task_id)
        if not task:
            return
        answer = QMessageBox.question(self, "Delete download", f"Remove '{task.destination.name}' from Fast Download Manager?\n\nPartial files will also be removed.", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
        if answer != QMessageBox.StandardButton.Yes:
            return
        if task.status in {"downloading", "analyzing"}:
            self.engine.cancel(task.id)
            self.queue.remove(task.id)
            self._delete_after_finish.add(task.id)
            task.status = "cancelled"
            self.progress(task)
            return
        self.queue.remove(task.id)
        self._remove_task_from_ui(task_id, delete_files=True)
        self._refresh_stats()
        self.status.setText("Download deleted")

    def delete_selected(self):
        selected = list(self.table.selectionModel().selectedRows())
        task_ids = []
        for index in selected:
            for task_id, row in self.rows.items():
                if row == index.row():
                    task_ids.append(task_id)
                    break
        for task_id in task_ids:
            if task_id in self.tasks:
                self._row_delete(task_id)

    def _row_pause(self, task_id: str):
        task = self.tasks.get(task_id)
        if not task or task.status not in {"downloading", "analyzing"}:
            return
        self.engine.pause(task.id)
        task.status = "paused"
        self.queue.remove(task.id)
        self.progress(task)

    def _row_resume(self, task_id: str):
        task = self.tasks.get(task_id)
        if not task or task.status not in {"paused", "failed", "cancelled"}:
            return
        self.engine.resume(task.id)
        self.queue.enqueue(task.id, self.priorities.get(task.id, Priority.NORMAL))
        task.status = "queued"
        task.error = None
        self.progress(task)
        self._pump_queue()

    def pause_all(self):
        for task in list(self.tasks.values()):
            if task.status in {"downloading", "analyzing", "queued"}:
                self.engine.pause(task.id)
                self.queue.remove(task.id)
                task.status = "paused"
                self.progress(task)

    def resume_all(self):
        for task in list(self.tasks.values()):
            if task.status in {"paused", "failed", "cancelled"}:
                self.engine.resume(task.id)
                self.queue.enqueue(task.id, self.priorities.get(task.id, Priority.NORMAL))
                task.status = "queued"
                task.error = None
                self.progress(task)
        self._pump_queue()

    def schedule_selected(self):
        task = self._selected_task()
        if not task:
            self.status.setText("Select a download to schedule")
            return
        if task.status in {"downloading", "completed"}:
            self.status.setText("Only queued, paused, failed, or cancelled downloads can be scheduled")
            return
        dialog = ScheduleDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        run_at, interval = dialog.values()
        schedule = Schedule.recurring(task.id, run_at, interval) if interval else Schedule.once(task.id, run_at)
        self.scheduler.add(schedule)
        self.schedules[schedule.id] = schedule
        self.queue.remove(task.id)
        task.status = "scheduled"
        self.db.upsert_schedule({"id": schedule.id, "task_id": schedule.task_id, "run_at": schedule.run_at, "interval": schedule.interval, "enabled": schedule.enabled})
        self.progress(task)
        self._notify("Download scheduled", task.destination.name)

    def _process_schedules(self):
        now = datetime.now(UTC).timestamp()
        for schedule in list(self.scheduler.due(now)):
            task = self.tasks.get(schedule.task_id)
            if not task:
                self.scheduler.remove(schedule.id)
                self.db.delete_schedule(schedule.id)
                self.schedules.pop(schedule.id, None)
                continue
            self.queue.enqueue(task.id, self.priorities.get(task.id, Priority.NORMAL))
            task.status = "queued"
            self.progress(task)
            self._notify("Scheduled download started", task.destination.name)
            if schedule.interval:
                schedule.advance(now)
                self.db.upsert_schedule({"id": schedule.id, "task_id": schedule.task_id, "run_at": schedule.run_at, "interval": schedule.interval, "enabled": schedule.enabled})
            else:
                self.scheduler.remove(schedule.id)
                self.db.delete_schedule(schedule.id)
                self.schedules.pop(schedule.id, None)
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

    def open_folder_selected(self):
        task = self._selected_task()
        if task and sys.platform == "win32":
            os.startfile(task.destination.parent)

    def _update_queue_status(self):
        self.status.setText(f"Queue {self.queue.pending_count} · Active {self.queue.active_count}/{self.queue.max_concurrent}")

    def _refresh_stats(self):
        total = len(self.tasks)
        active = sum(1 for t in self.tasks.values() if t.status == "downloading")
        queued = sum(1 for t in self.tasks.values() if t.status == "queued")
        speed = sum(t.speed for t in self.tasks.values() if t.status == "downloading")
        self.stat_total.set_value(str(total))
        self.stat_active.set_value(str(active))
        self.stat_queued.set_value(str(queued))
        self.stat_speed.set_value(self._format_rate(speed))

    @staticmethod
    def _format_rate(value: float) -> str:
        value = max(0.0, float(value))
        for unit in ("B/s", "KB/s", "MB/s", "GB/s"):
            if value < 1024 or unit == "GB/s":
                return f"{value:.1f} {unit}"
            value /= 1024
        return f"{value:.1f} GB/s"

    @staticmethod
    def fmt(value) -> str:
        if value is None or value <= 0:
            return "Unknown"
        value = float(value)
        for unit in ("B", "KB", "MB", "GB", "TB"):
            if value < 1024:
                return f"{value:.1f} {unit}"
            value /= 1024
        return f"{value:.1f} PB"

    def _save(self, task: DownloadTask):
        self.db.upsert({"id": task.id, "url": task.url, "filename": task.destination.name, "destination": str(task.destination), "total": task.total, "downloaded": task.downloaded, "status": task.status, "speed": task.speed, "created": task.created, "priority": int(self.priorities.get(task.id, Priority.NORMAL))})

    def exit_application(self):
        self._force_exit = True
        self.close()

    def closeEvent(self, event):
        if self.tray and not self._force_exit:
            self.hide()
            self._notify("Fast Download Manager", "Still running in the system tray.")
            event.ignore()
            return
        self._schedule_timer.stop()
        if self.tray:
            self.tray.hide()
        self.scheduler.close()
        for task in self.tasks.values():
            self.engine.cancel(task.id)
        for thread in list(self.threads.values()):
            thread.quit()
            thread.wait(3000)
        self.db.close()
        event.accept()


def main():
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    window = MainWindow()
    window.show()
    return app.exec()
