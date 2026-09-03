import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path

from PySide6.QtWidgets import QApplication
from shiboken6 import isValid

from fastdm.ui import MainWindow


def test_main_window_startup_keeps_navigation_widgets_alive(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    db_path = tmp_path / "startup-test.db"
    monkeypatch.setattr(MainWindow, "_db_path", staticmethod(lambda: Path(db_path)))

    window = MainWindow()
    try:
        app.processEvents()
        assert isValid(window.sidebar)
        assert isValid(window.nav_status)
        window.set_filter("all")
        assert isValid(window.nav_status)
        assert window.nav_status.text().startswith("Showing ")
    finally:
        window._force_exit = True
        window.close()
        app.processEvents()
