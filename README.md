# Fast Download Manager

**Fast Download Manager (FDM)** is a Windows-first, modern download manager built with Python and PySide6. It is being developed as a serious IDM alternative with a clean dark desktop UI, segmented HTTP/HTTPS downloading, persistent recovery, queues, scheduling, system-tray controls, IDM-style download dialogs, and automated Windows packaging.

> **Status:** Active development — phase-by-phase implementation with CI verification on every push.

## Download for Windows

### Recommended: Windows Installer

**[Download Fast Download Manager Setup (.exe)](https://github.com/resanul/Fast-Download-Manager/releases/latest/download/Fast-Download-Manager-Setup.exe)**

The installer provides a normal Windows installation with Start Menu and optional desktop/startup shortcuts. Fast Download Manager uses a stable Windows application identifier and single-instance guard, so launching the app repeatedly does **not** create additional application sessions or additional tray icons.

Installing a newer release upgrades the existing installation in the same application location instead of creating another parallel installation.

### Portable Windows EXE

**[Download Fast Download Manager for Windows (.exe)](https://github.com/resanul/Fast-Download-Manager/releases/latest/download/Fast-Download-Manager.exe)**

The portable executable is retained for advanced/testing use. The installer is recommended for normal Windows use.

### Latest automated Windows build

**[Open Windows Build workflow](https://github.com/resanul/Fast-Download-Manager/actions/workflows/windows-build.yml)**

From the latest successful run, open **Artifacts** and download `Fast-Download-Manager-windows`.

> GitHub Actions artifacts are intended for CI testing and may expire. Release assets are the preferred long-term download method.

## What is implemented

### Download engine

- HTTP and HTTPS downloads
- Redirect handling
- Server metadata analysis
- HTTP Range detection
- Multi-connection segmented downloading for supported large files
- Single-connection fallback when Range is unavailable
- Pause and resume state
- Per-segment recovery
- Streaming disk writes
- Retry with exponential backoff
- Collision-safe task-specific temporary workspaces
- Temporary `.part` recovery
- File-size validation
- Checksum verification through the engine verification API
- Current and peak throughput telemetry

### Download management

- Priority levels: High, Normal, Low
- Configurable concurrent downloads
- Persistent queue state
- SQLite-backed download history
- Persistent settings
- Scheduled downloads
- One-time and recurring schedule support
- Automatic queue continuation
- Retry of failed/cancelled items
- Multi-selection and persistent download deletion
- Automatic duplicate filename handling (`file (1).zip`, `file (2).zip`, etc.)

### Windows desktop experience

The UI is being redesigned around clean modern desktop references: a compact left navigation rail, dark neutral surfaces, clear statistics cards, a focused download table, inline actions, and low-noise status indicators.

Current UI direction includes:

- Clean Windows-first dark theme
- Left navigation for All, Active, Completed, Queued, Paused, Errors, Scheduler
- Library filters for Documents, Compressed, Music, and Videos
- Search/filter field
- Download statistics cards
- Inline progress bars
- Inline Pause / Resume / Delete controls
- Queue/concurrency control
- System tray controls
- Windows notifications
- IDM-style **Download File Info** dialog
- IDM-style **Download Status** dialog
- Segment/connection details
- Per-download speed-limiter UI
- Options on completion

### Single-instance behavior

Fast Download Manager is a single-instance Windows desktop application.

- Repeatedly launching the EXE activates the already-running window.
- A minimized-to-tray instance is restored instead of opening another session.
- Only one application process owns the Fast Download Manager Windows mutex.
- The installer uses the same application identity, preventing side-by-side installs.

### Scheduler and tray

- Start-at scheduling
- Recurring schedules by minute interval
- Persistent scheduled tasks
- System tray menu
- Minimize-to-tray behavior
- Pause All / Resume All
- Completion and failure notifications

### IDM-style download dialogs

The download flow supports a pre-download information dialog with:

- URL
- Category selection
- Save As path
- Browse button
- Remember path option
- Description
- Download Later
- Start Download

Double-clicking a download opens live status details with:

- URL and status
- File size and downloaded amount
- Transfer rate
- Remaining time
- Resume capability
- Segment/connection list
- Pause / Cancel controls
- Speed Limiter tab
- Options on completion

## Roadmap

The project is intentionally developed in gates rather than adding a large number of unverified features at once.

- [x] Foundation and SQLite persistence
- [x] Real HTTP/HTTPS download engine
- [x] Range-aware segmented downloading
- [x] Pause / resume / retry
- [x] Queue and priority handling
- [x] Persistent scheduled downloads
- [x] System tray and notifications
- [x] Automated Windows EXE build
- [x] Windows installer foundation
- [x] Single-instance application guard
- [x] IDM-style download dialogs
- [ ] Fully wired global and per-download bandwidth limiter
- [ ] Network connectivity awareness
- [ ] Proxy profiles and per-download proxy selection
- [ ] Advanced download diagnostics
- [ ] Download analytics and real-time charts
- [ ] Browser integration via Native Messaging
- [ ] Advanced categories and destination rules
- [ ] Automatic update channel
- [ ] Extended integration/performance tests
- [ ] Release hardening and code-signing support

## Architecture

```text
Fast Download Manager
│
├── PySide6 UI
│   ├── Navigation
│   ├── Download table
│   ├── Statistics
│   ├── IDM-style dialogs
│   ├── Scheduler
│   └── System tray
│
├── Application services
│   ├── Queue
│   ├── Scheduler
│   ├── Notifications
│   └── Single-instance guard
│
├── Download engine
│   ├── URL analyzer
│   ├── Connection manager
│   ├── Segment manager
│   ├── Retry/recovery
│   ├── Speed telemetry
│   └── Integrity verification
│
├── Persistence
│   └── SQLite
│
└── CI/CD
    ├── Ruff
    ├── Pytest
    ├── Windows PyInstaller build
    ├── Inno Setup installer
    └── GitHub Release packaging
```

The download engine is intentionally separated from the Qt UI so that networking, recovery, testing, and future integrations can evolve independently.

## Requirements

- Windows 10 or Windows 11 for the desktop application
- Python 3.12+ for development
- Git
- Inno Setup 6 for local installer builds

## Development setup

### PowerShell

```powershell
git clone https://github.com/resanul/Fast-Download-Manager.git
cd Fast-Download-Manager

py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1

python -m pip install --upgrade pip
pip install -r requirements.txt
pip install -e .
```

Run the application:

```powershell
python -m fastdm
```

## Build a Windows EXE locally

```powershell
pip install -r requirements.txt pyinstaller
pip install -e .
ruff check .
pytest
pyinstaller --noconfirm --clean --onefile --windowed --name Fast-Download-Manager fastdm/__main__.py
```

The executable is generated at:

```text
dist/Fast-Download-Manager.exe
```

## Build the Windows installer locally

Install **Inno Setup 6**, then build the application EXE first and run:

```powershell
& 'C:\Program Files (x86)\Inno Setup 6\ISCC.exe' '/DMyAppVersion=0.2.0' 'installer\FastDownloadManager.iss'
```

The installer is generated at:

```text
dist/installer/Fast-Download-Manager-Setup.exe
```

The installer uses a stable application identity and application mutex. Reinstalling a newer release upgrades the existing installation instead of creating another installation directory.

## GitHub Actions

### Tests

The test workflow installs Linux Qt runtime dependencies where required, runs Ruff, and executes Pytest on pushes to the repository.

[View Tests workflow](https://github.com/resanul/Fast-Download-Manager/actions/workflows/tests.yml)

### Windows build

The Windows workflow builds the one-file Windows EXE and uploads it as a workflow artifact.

[View Windows build workflow](https://github.com/resanul/Fast-Download-Manager/actions/workflows/windows-build.yml)

### Installer release

The Windows installer release pipeline:

1. Installs Python 3.12 and project dependencies
2. Runs Ruff
3. Runs Pytest
4. Builds the portable Windows EXE with PyInstaller
5. Installs Inno Setup
6. Builds `Fast-Download-Manager-Setup.exe`
7. Verifies installer size
8. Generates SHA-256 checksums
9. Publishes the installer and portable EXE to a GitHub Release

## Data and storage

User application data is stored under:

```text
%LOCALAPPDATA%\FastDownloadManager\downloads.db
```

Downloads themselves are never stored inside SQLite. Temporary download data is isolated under task-specific `.fastdm` workspaces near the destination file.

## Security principles

- TLS certificate verification remains enabled.
- Downloaded executables are never automatically launched.
- File paths must be treated as untrusted input.
- Sensitive request values must not be written to logs.
- Secrets must never be committed to Git.
- Local integration APIs, when added, must be localhost-only and authenticated.
- The project does not bypass DRM, authentication, authorization, or paywalls.

## Testing strategy

The project uses unit and integration testing for the download engine and management logic. Important cases include:

- Normal HTTP download
- Range-supported segmented download
- Range-unsupported fallback
- Pause/resume
- Retry and transient failure handling
- Persistent queue state
- Scheduler recurrence
- Checksum verification
- Duplicate temporary workspace isolation
- Persistent deletion
- UI startup/widget ownership
- Progress signal throttling
- Single-instance behavior

## UI design direction

The visual direction intentionally avoids the dense, dated utility look common to older download managers. The target is a clean Windows desktop experience with:

- restrained dark surfaces
- strong typography hierarchy
- compact controls
- clear status states
- high information density without visual noise
- consistent spacing and alignment
- real-time status and progress rather than decorative metrics
- focused modal dialogs for download setup and live transfer details

The supplied reference screens are used as visual inspiration for layout and density while the actual application remains purpose-built for Fast Download Manager.

## Versioning

Use semantic-style version tags:

```text
v0.2.0
v0.3.0
v1.0.0
```

Release assets include both the installer and the portable executable. The latest stable installer is always published as:

```text
https://github.com/resanul/Fast-Download-Manager/releases/latest/download/Fast-Download-Manager-Setup.exe
```

## License

Fast Download Manager is released under the **MIT License**.

Copyright (c) 2026 Mir Resanul Karim
