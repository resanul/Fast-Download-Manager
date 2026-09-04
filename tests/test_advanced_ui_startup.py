import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path

from PySide6.QtWidgets import QApplication

from fastdm.advanced_ui import install
from fastdm.ui import MainWindow


def test_advanced_ui_seeds_state_before_history_progress(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(MainWindow, "_db_path", staticmethod(lambda: Path(tmp_path) / "downloads.db"))
    installed = install(MainWindow)
    window = installed()
    assert hasattr(window, "_status_dialogs")
    assert isinstance(window._status_dialogs, dict)
    window.close()
    app.processEvents()
