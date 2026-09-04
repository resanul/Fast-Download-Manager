from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes


class SingleInstance:
    """Windows single-instance guard with foreground activation."""

    ERROR_ALREADY_EXISTS = 183

    def __init__(self, mutex_name: str, window_title: str) -> None:
        self.mutex_name = mutex_name
        self.window_title = window_title
        self._handle = None

    def acquire(self) -> bool:
        if sys.platform != "win32":
            return True

        kernel32 = ctypes.windll.kernel32
        kernel32.CreateMutexW.restype = wintypes.HANDLE
        kernel32.CreateMutexW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]
        self._handle = kernel32.CreateMutexW(None, False, self.mutex_name)
        if not self._handle:
            return False

        last_error = kernel32.GetLastError()
        if last_error == self.ERROR_ALREADY_EXISTS:
            self.activate_existing()
            kernel32.CloseHandle(self._handle)
            self._handle = None
            return False
        return True

    def activate_existing(self) -> None:
        if sys.platform != "win32":
            return

        user32 = ctypes.windll.user32
        hwnd = user32.FindWindowW(None, self.window_title)
        if not hwnd:
            return

        SW_RESTORE = 9
        user32.ShowWindow(hwnd, SW_RESTORE)
        user32.SetForegroundWindow(hwnd)
        user32.BringWindowToTop(hwnd)

    def release(self) -> None:
        if self._handle and sys.platform == "win32":
            ctypes.windll.kernel32.ReleaseMutex(self._handle)
            ctypes.windll.kernel32.CloseHandle(self._handle)
            self._handle = None
