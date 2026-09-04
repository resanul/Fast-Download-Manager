from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QTableWidget

from .download_dialogs import DownloadFileInfoDialog, DownloadStatusDialog
from .engine import DownloadTask
from .queue import Priority


def install(main_window_cls):
    """Install the richer IDM-style interaction layer without replacing the core engine."""
    original_init = main_window_cls.__init__
    original_add_download = main_window_cls.add_download
    original_progress = main_window_cls.progress

    def _init(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        self._status_dialogs = {}
        self._advanced_metadata = {}
        self.table.cellDoubleClicked.connect(lambda row, column: self._show_status_for_row(row))

    def _show_status_for_row(self, row: int):
        task_id = None
        for candidate_id, candidate_row in self.rows.items():
            if candidate_row == row:
                task_id = candidate_id
                break
        if not task_id:
            return
        task = self.tasks.get(task_id)
        if not task:
            return
        dialog = self._status_dialogs.get(task_id)
        if dialog is None:
            dialog = DownloadStatusDialog(filename=task.destination.name, url=task.url, total=task.total, parent=self)
            dialog.pause_requested.connect(lambda tid=task_id: self._row_pause(tid))
            dialog.cancel_requested.connect(lambda tid=task_id: self._row_delete(tid))
            self._status_dialogs[task_id] = dialog
        self._refresh_status_dialog(task)
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()

    def _refresh_status_dialog(self, task):
        dialog = self._status_dialogs.get(task.id)
        if dialog is None:
            return
        remaining = None
        if task.total and task.speed > 0 and task.downloaded <= task.total:
            remaining = (task.total - task.downloaded) / task.speed
        dialog.update_download(
            downloaded=task.downloaded,
            total=task.total,
            speed=task.speed,
            status=self._pretty_status(task.status),
            remaining_seconds=remaining,
            segments=task.segments,
        )

    def _progress(self, task, *args, **kwargs):
        original_progress(self, task, *args, **kwargs)
        self._refresh_status_dialog(task)

    def _add_download(self):
        downloads = Path.home() / "Downloads"
        default_folder = downloads if downloads.exists() else Path.home()
        dialog = DownloadFileInfoDialog(url="", filename="download", default_folder=default_folder, parent=self)
        dialog.url_edit.setPlaceholderText("https://example.com/file.iso")

        def handle(payload):
            url = payload["url"]
            if not url:
                self.status.setText("Enter a download URL")
                return
            filename = Path(url.split("?", 1)[0]).name or "download"
            requested = Path(payload["save_as"]) if payload["save_as"] else default_folder / filename
            folder = requested.parent
            destination = self._unique_destination(folder, requested.name)
            task = DownloadTask(task_id=__import__("uuid").uuid4().hex, url=url, destination=destination)
            priority = Priority.NORMAL
            self.tasks[task.id] = task
            self.priorities[task.id] = priority
            self.rows[task.id] = self._insert_row(task.id, destination.name, "queued", 0, None, 0, priority)
            self.queue.enqueue(task.id, priority)
            self._advanced_metadata[task.id] = {
                "category": payload["category"],
                "description": payload["description"],
                "remember": payload["remember"],
            }
            self._save(task)
            self._apply_filters()
            if payload["later"]:
                self.status.setText(f"Added to queue: {destination.name}")
            else:
                self._pump_queue()
                self.status.setText(f"Started: {destination.name}")

        dialog.start_download.connect(handle)
        dialog.exec()

    main_window_cls.__init__ = _init
    main_window_cls.add_download = _add_download
    main_window_cls.progress = _progress
    main_window_cls._show_status_for_row = _show_status_for_row
    main_window_cls._refresh_status_dialog = _refresh_status_dialog

    return main_window_cls
