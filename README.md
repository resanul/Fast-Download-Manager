# Fast Download Manager

Modern Windows download manager built with Python and PySide6.

## Current release

This repository is being developed phase-by-phase. The current foundation includes a Windows desktop UI and a real HTTP/HTTPS download engine with range-aware segmented downloading, pause/resume state, retries, and a local SQLite store.

## Run

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m fastdm
```

## Build Windows EXE

```powershell
pip install -r requirements.txt pyinstaller
pyinstaller --noconfirm --clean --onefile --windowed --name Fast-Download-Manager fastdm/__main__.py
```

The GitHub Actions Windows workflow builds the executable automatically on pushes to `main`.

## Architecture

The download engine is independent of the Qt UI. It validates URLs, analyzes server metadata, uses HTTP Range requests when supported, splits sufficiently large files into segments, retries transient failures, writes streaming data to disk, and assembles segments safely.

## Roadmap

- Persistent UI download list and recovery
- Queue/priority/bandwidth scheduler
- Network monitoring and proxy profiles
- Notifications and system tray
- Browser native-messaging integration
- Statistics and diagnostics
- Installer, signed releases, and update channel

## Security

Downloads are never executed automatically. TLS certificate verification remains enabled. Credentials and sensitive request data must not be placed in logs or source control.
