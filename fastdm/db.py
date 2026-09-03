from __future__ import annotations

import sqlite3
from pathlib import Path


class Database:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self.initialize()

    def initialize(self):
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS downloads (
              id TEXT PRIMARY KEY, url TEXT NOT NULL, filename TEXT NOT NULL,
              destination TEXT NOT NULL, total INTEGER, downloaded INTEGER DEFAULT 0,
              status TEXT NOT NULL, speed REAL DEFAULT 0, created REAL NOT NULL,
              priority INTEGER DEFAULT 20
            );
            CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS schedules (
              id TEXT PRIMARY KEY, task_id TEXT NOT NULL, run_at REAL NOT NULL,
              interval REAL, enabled INTEGER NOT NULL DEFAULT 1
            );
            CREATE INDEX IF NOT EXISTS idx_downloads_status ON downloads(status);
            CREATE INDEX IF NOT EXISTS idx_downloads_created ON downloads(created);
            CREATE INDEX IF NOT EXISTS idx_downloads_priority ON downloads(priority);
            CREATE INDEX IF NOT EXISTS idx_schedules_run_at ON schedules(run_at);
            """
        )
        columns = {row[1] for row in self.conn.execute("PRAGMA table_info(downloads)")}
        if "priority" not in columns:
            self.conn.execute("ALTER TABLE downloads ADD COLUMN priority INTEGER DEFAULT 20")
        self.conn.commit()

    def upsert(self, d: dict):
        self.conn.execute(
            """INSERT INTO downloads(id,url,filename,destination,total,downloaded,status,speed,created,priority)
            VALUES(?,?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET
            downloaded=excluded.downloaded,total=excluded.total,status=excluded.status,
            speed=excluded.speed,priority=excluded.priority""",
            (
                d["id"], d["url"], d["filename"], d["destination"], d.get("total"),
                d.get("downloaded", 0), d["status"], d.get("speed", 0), d["created"],
                d.get("priority", 20),
            ),
        )
        self.conn.commit()

    def list(self):
        return self.conn.execute("SELECT * FROM downloads ORDER BY created DESC").fetchall()

    def delete_download(self, task_id: str):
        self.conn.execute("DELETE FROM downloads WHERE id=?", (task_id,))
        self.conn.commit()

    def upsert_schedule(self, schedule: dict):
        self.conn.execute(
            """INSERT INTO schedules(id,task_id,run_at,interval,enabled) VALUES(?,?,?,?,?)
            ON CONFLICT(id) DO UPDATE SET task_id=excluded.task_id,run_at=excluded.run_at,
            interval=excluded.interval,enabled=excluded.enabled""",
            (
                schedule["id"], schedule["task_id"], schedule["run_at"],
                schedule.get("interval"), int(bool(schedule.get("enabled", True))),
            ),
        )
        self.conn.commit()

    def list_schedules(self):
        return self.conn.execute("SELECT * FROM schedules ORDER BY run_at").fetchall()

    def delete_schedule(self, schedule_id: str):
        self.conn.execute("DELETE FROM schedules WHERE id=?", (schedule_id,))
        self.conn.commit()

    def set_setting(self, key: str, value: str):
        self.conn.execute(
            "INSERT INTO settings(key,value) VALUES(?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value),
        )
        self.conn.commit()

    def get_setting(self, key: str, default: str | None = None):
        row = self.conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return row["value"] if row else default

    def close(self):
        self.conn.close()
