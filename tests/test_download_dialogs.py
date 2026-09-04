import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path

from PySide6.QtWidgets import QApplication

from fastdm.download_dialogs import DownloadFileInfoDialog, DownloadStatusDialog


def test_download_file_info_dialog_payload(tmp_path):
    app = QApplication.instance() or QApplication([])
    dialog = DownloadFileInfoDialog(url="https://example.com/app.zip", filename="app.zip", default_folder=Path(tmp_path))
    emitted = []
    dialog.start_download.connect(emitted.append)
    dialog._emit(True, False)
    app.processEvents()
    assert emitted and emitted[0]["url"] == "https://example.com/app.zip"
    assert emitted[0]["save_as"].endswith("app.zip")


def test_download_status_dialog_updates_live_values():
    app = QApplication.instance() or QApplication([])
    dialog = DownloadStatusDialog(filename="app.zip", url="https://example.com/app.zip", total=1000)
    dialog.update_download(downloaded=500, total=1000, speed=250.0, status="Downloading", remaining_seconds=2.0)
    app.processEvents()
    assert dialog.progress.value() == 50
    assert "250" in dialog.rate_label.text()
    assert "50.00%" in dialog.downloaded_label.text()
