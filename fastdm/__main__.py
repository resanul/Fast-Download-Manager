from fastdm.advanced_ui import install
from fastdm.single_instance import SingleInstance
from fastdm.telemetry import install as install_telemetry
from fastdm.ui import MainWindow, main

install(MainWindow)
install_telemetry(MainWindow)


if __name__ == "__main__":
    guard = SingleInstance("Local\\FastDownloadManager.Singleton", "Fast Download Manager")
    if not guard.acquire():
        raise SystemExit(0)
    try:
        raise SystemExit(main())
    finally:
        guard.release()
