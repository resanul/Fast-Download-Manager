from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSlider,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)


class DownloadFileInfoDialog(QDialog):
    """IDM-style pre-download file information dialog."""

    start_download = Signal(dict)

    def __init__(self, *, url: str, filename: str, default_folder: Path, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Download File Info")
        self.resize(720, 430)
        self.setModal(True)

        root = QVBoxLayout(self)
        form = QFormLayout()

        self.url_edit = QLineEdit(url)
        self.url_edit.setReadOnly(False)
        form.addRow("URL", self.url_edit)

        category_row = QHBoxLayout()
        self.category = QComboBox()
        self.category.addItems(["Programs", "Documents", "Compressed", "Music", "Videos", "Other"])
        category_row.addWidget(self.category, 1)
        add_category = QPushButton("+")
        add_category.setFixedWidth(34)
        add_category.clicked.connect(lambda: self.category.addItem("Custom"))
        category_row.addWidget(add_category)
        form.addRow("Category", category_row)

        save_row = QHBoxLayout()
        self.save_as = QLineEdit(str(default_folder / filename))
        save_row.addWidget(self.save_as, 1)
        browse = QPushButton("…")
        browse.setFixedWidth(40)
        browse.clicked.connect(self._browse)
        save_row.addWidget(browse)
        form.addRow("Save As", save_row)

        self.remember = QCheckBox("Remember this path for selected category")
        form.addRow("", self.remember)

        self.description = QLineEdit()
        form.addRow("Description", self.description)
        root.addLayout(form)

        self.details = QLabel("Preparing download metadata…")
        self.details.setObjectName("downloadInfoDetails")
        root.addWidget(self.details)

        buttons = QDialogButtonBox(parent=self)
        self.later = buttons.addButton("Download Later", QDialogButtonBox.ButtonRole.ActionRole)
        self.start = buttons.addButton("Start Download", QDialogButtonBox.ButtonRole.AcceptRole)
        self.cancel = buttons.addButton(QDialogButtonBox.StandardButton.Cancel)
        self.later.clicked.connect(self._download_later)
        self.start.clicked.connect(self._start)
        self.cancel.clicked.connect(self.reject)
        root.addWidget(buttons)

    def set_metadata(self, *, size_text: str | None = None, mime: str | None = None, resumable: bool | None = None):
        parts = []
        if size_text:
            parts.append(size_text)
        if mime:
            parts.append(mime)
        if resumable is not None:
            parts.append("Resume supported" if resumable else "Resume unknown")
        self.details.setText("  •  ".join(parts) if parts else "Metadata unavailable")

    def _browse(self):
        from PySide6.QtWidgets import QFileDialog

        current = Path(self.save_as.text())
        selected, _ = QFileDialog.getSaveFileName(self, "Save As", str(current), "All Files (*.*)")
        if selected:
            self.save_as.setText(selected)

    def _payload(self, later: bool):
        return {
            "url": self.url_edit.text().strip(),
            "category": self.category.currentText(),
            "save_as": self.save_as.text().strip(),
            "remember": self.remember.isChecked(),
            "description": self.description.text().strip(),
            "later": later,
        }

    def _start(self):
        self.start_download.emit(self._payload(False))
        self.accept()

    def _download_later(self):
        self.start_download.emit(self._payload(True))
        self.accept()


class DownloadStatusDialog(QDialog):
    """IDM-style live download details with speed limiter and completion options."""

    pause_requested = Signal()
    cancel_requested = Signal()
    speed_limit_changed = Signal(int)
    completion_changed = Signal(dict)

    def __init__(self, *, filename: str, url: str, total: int | None, parent=None):
        super().__init__(parent)
        self.setWindowTitle(filename)
        self.resize(760, 560)
        root = QVBoxLayout(self)

        tabs = QTabWidget()
        status = QWidget()
        status_layout = QVBoxLayout(status)

        info_group = QGroupBox("Download status")
        info = QFormLayout(info_group)
        self.url_label = QLabel(url)
        self.status_label = QLabel("Receiving data…")
        self.size_label = QLabel(self._fmt(total))
        self.downloaded_label = QLabel("0 B (0.00%)")
        self.rate_label = QLabel("0 B/s")
        self.time_left_label = QLabel("—")
        self.resume_label = QLabel("Yes")
        info.addRow("URL", self.url_label)
        info.addRow("Status", self.status_label)
        info.addRow("File size", self.size_label)
        info.addRow("Downloaded", self.downloaded_label)
        info.addRow("Transfer rate", self.rate_label)
        info.addRow("Time left", self.time_left_label)
        info.addRow("Resume capability", self.resume_label)
        status_layout.addWidget(info_group)

        self.progress = QSlider(Qt.Orientation.Horizontal)
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setEnabled(False)
        status_layout.addWidget(self.progress)

        actions = QHBoxLayout()
        self.hide_details = QPushButton("<< Hide details")
        self.pause = QPushButton("Pause")
        self.cancel = QPushButton("Cancel")
        self.hide_details.clicked.connect(lambda: details.setVisible(not details.isVisible()))
        self.pause.clicked.connect(self.pause_requested.emit)
        self.cancel.clicked.connect(self.cancel_requested.emit)
        actions.addWidget(self.hide_details)
        actions.addStretch(1)
        actions.addWidget(self.pause)
        actions.addWidget(self.cancel)
        status_layout.addLayout(actions)

        details = QListWidget()
        details.setObjectName("segmentList")
        self.segment_list = details
        status_layout.addWidget(details, 1)
        tabs.addTab(status, "Download status")

        limiter = QWidget()
        limiter_layout = QFormLayout(limiter)
        self.limit_enabled = QCheckBox("Limit transfer rate")
        self.limit_slider = QSlider(Qt.Orientation.Horizontal)
        self.limit_slider.setRange(0, 1024)
        self.limit_slider.setValue(0)
        self.limit_value = QLabel("Unlimited")
        self.limit_slider.valueChanged.connect(self._limit_changed)
        limiter_layout.addRow("Enabled", self.limit_enabled)
        limiter_layout.addRow("Speed", self.limit_slider)
        limiter_layout.addRow("", self.limit_value)
        tabs.addTab(limiter, "Speed Limiter")

        completion = QWidget()
        completion_layout = QVBoxLayout(completion)
        self.close_after = QCheckBox("Close this window when download completes")
        self.shutdown_after = QCheckBox("Shut down PC after completion")
        self.open_folder_after = QCheckBox("Open download folder after completion")
        for widget in (self.close_after, self.open_folder_after, self.shutdown_after):
            widget.toggled.connect(self._completion_changed)
            completion_layout.addWidget(widget)
        completion_layout.addStretch(1)
        tabs.addTab(completion, "Options on completion")

        root.addWidget(tabs)
        self._total = total
        self._timer = QTimer(self)
        self._timer.start(1000)

    @staticmethod
    def _fmt(value):
        if value is None:
            return "Unknown"
        value = float(value)
        for unit in ("B", "KB", "MB", "GB", "TB"):
            if value < 1024:
                return f"{value:.2f} {unit}"
            value /= 1024
        return f"{value:.2f} PB"

    def update_download(self, *, downloaded: int, total: int | None, speed: float, status: str, remaining_seconds: float | None = None, segments=None):
        self._total = total
        pct = (downloaded * 100 / total) if total else 0
        self.progress.setValue(max(0, min(100, int(pct))))
        self.size_label.setText(self._fmt(total))
        self.downloaded_label.setText(f"{self._fmt(downloaded)} ({pct:.2f}%)")
        self.rate_label.setText(self._fmt(speed) + "/s")
        self.status_label.setText(status)
        if remaining_seconds is None or remaining_seconds < 0:
            self.time_left_label.setText("—")
        else:
            minutes, seconds = divmod(int(remaining_seconds), 60)
            hours, minutes = divmod(minutes, 60)
            self.time_left_label.setText(f"{hours}h {minutes:02d}m {seconds:02d}s" if hours else f"{minutes}m {seconds:02d}s")
        if segments is not None:
            self.segment_list.clear()
            for index, seg in enumerate(segments, 1):
                item = QListWidgetItem(f"{index:02d}    {self._fmt(seg.downloaded)}    Receiving data…")
                self.segment_list.addItem(item)

    def _limit_changed(self, value: int):
        enabled = self.limit_enabled.isChecked()
        self.limit_value.setText("Unlimited" if not enabled or value == 0 else self._fmt(value * 1024))
        self.speed_limit_changed.emit(value * 1024 if enabled else 0)

    def _completion_changed(self):
        self.completion_changed.emit({
            "close": self.close_after.isChecked(),
            "shutdown": self.shutdown_after.isChecked(),
            "open_folder": self.open_folder_after.isChecked(),
        })
