# Architecture

```text
PySide6 UI
   |
Application services
   |
Download engine ---- Network/HTTPX
   |
SQLite persistence
```

The engine contains `DownloadTask`, `Segment`, `DownloadEngine`, retry handling and pause/cancel controls. The UI communicates with the engine through Qt worker threads so network I/O does not block the event loop.

Future services should remain decoupled from the UI: queue scheduling, bandwidth limiting, network monitoring, browser IPC, notifications and update management.
