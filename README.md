# Fast Download Manager

**Fast Download Manager (FDM)** is a Windows-first, modern download manager built with Python and PySide6. The project is being developed as a serious IDM alternative with a clean dark desktop UI, segmented HTTP/HTTPS downloading, persistent recovery, queues, scheduling, system-tray controls, and automated Windows packaging.

> **Status:** Active development — phase-by-phase implementation with CI verification on every push.

## Download for Windows

### Latest release EXE

**[Download Fast Download Manager for Windows (.exe)](https://github.com/resanul/Fast-Download-Manager/releases/latest/download/Fast-Download-Manager.exe)**

This is the stable release URL used by the README. The release workflow publishes the EXE under this exact filename whenever a version tag such as `v0.2.0` is created.

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
- Temporary `.part` recovery
- File-size validation
- Checksum verification through the engine verification API

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

### Windows desktop experience

The UI is being redesigned around the supplied clean desktop references: a compact left navigation rail, dark neutral surfaces, clear statistics cards, a focused download table, inline actions, and low-noise status indicators.

Current UI direction includes:

- Clean Windows-first dark theme
- Left navigation for All, Active, Completed, Queued, Paused, Errors, Scheduler
- Library filters for Documents, Compressed, Music, and Videos
- Search/filter field
- Download statistics cards
- Inline progress bars
- Inline Pause / Resume / Cancel controls
- Queue/concurrency control
- System tray controls
- Windows notifications

### Scheduler and tray

- Start-at scheduling
- Recurring schedules by minute interval
- Persistent scheduled tasks
- System tray menu
- Minimize-to-tray preference
- Pause All / Resume All
- Completion and failure notifications

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
- [ ] Global and per-download bandwidth limiter
- [ ] Network connectivity awareness
- [ ] Proxy profiles and per-download proxy selection
- [ ] Advanced download details and diagnostics
- [ ] Download analytics and real-time charts
- [ ] Browser integration via Native Messaging
- [ ] Advanced categories and destination rules
- [ ] Windows installer
- [ ] Versioned GitHub releases
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
│   ├── Scheduler
│   └── System tray
│
├── Application services
│   ├── Queue
│   ├── Scheduler
│   └── Notifications
│
├── Download engine
│   ├── URL analyzer
│   ├── Connection manager
│   ├── Segment manager
│   ├── Retry/recovery
│   └── Integrity verification
│
├── Persistence
│   └── SQLite
│
└── CI/CD
    ├── Ruff
    ├── Pytest
    ├── Windows PyInstaller build
    └── GitHub Release packaging
```

The download engine is intentionally separated from the Qt UI so that networking, recovery, testing, and future integrations can evolve independently.

## Requirements

- Windows 10 or Windows 11 for the desktop application
- Python 3.12+ for development
- Git

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

## GitHub Actions

### Tests

The test workflow installs dependencies, runs Ruff, and executes Pytest on pushes to the repository.

[View Tests workflow](https://github.com/resanul/Fast-Download-Manager/actions/workflows/tests.yml)

### Windows build

The Windows workflow:

1. Checks out the repository
2. Installs Python 3.12
3. Installs project dependencies
4. Runs Ruff
5. Runs Pytest
6. Builds the one-file Windows EXE with PyInstaller
7. Uploads the EXE as a workflow artifact

[View Windows build workflow](https://github.com/resanul/Fast-Download-Manager/actions/workflows/windows-build.yml)

### Release build

When a version tag matching `v*` is pushed, the release workflow builds the Windows EXE, generates a SHA-256 checksum file, and publishes:

```text
Fast-Download-Manager.exe
SHA256SUMS.txt
```

to a GitHub Release.

The release asset is intended to be downloaded through:

```text
https://github.com/resanul/Fast-Download-Manager/releases/latest/download/Fast-Download-Manager.exe
```

## Data and storage

User application data is stored under:

```text
%LOCALAPPDATA%\FastDownloadManager\downloads.db
```

On non-Windows development environments, the project uses:

```text
~/.local/share/fast-download-manager/downloads.db
```

Downloads themselves are never stored inside SQLite.

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
- Crash/recovery behavior

A future test lab will add controlled HTTP endpoints for slow responses, partial responses, connection resets, rate limiting, and common HTTP error codes.

## UI design direction

The visual direction intentionally avoids the dense, dated utility look common to older download managers. The target is a clean Windows desktop experience with:

- restrained dark surfaces
- strong typography hierarchy
- compact controls
- clear status states
- high information density without visual noise
- consistent spacing and alignment
- real-time status and progress rather than decorative metrics

The supplied reference screens are used as visual inspiration for layout and density while the actual application remains purpose-built for Fast Download Manager.

## Versioning

Use semantic-style version tags:

```text
v0.1.0
v0.2.0
v1.0.0
```

Release assets are produced automatically by GitHub Actions for tagged versions.

## Contributing

1. Create a focused branch.
2. Make one logical change at a time.
3. Run `ruff check .`.
4. Run `pytest`.
5. Verify the Windows build when the change affects packaging or UI.
6. Use a meaningful commit message.

## License

Add the project license before the first public production release.
