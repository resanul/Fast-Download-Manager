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
        self.conn.executescript("""
        CREATE TABLE IF NOT EXISTS downloads (
          id TEXT PRIMARY KEY, url TEXT NOT NULL, filename TEXT NOT NULL,
          destination TEXT NOT NULL, total INTEGER, downloaded INTEGER DEFAULT 0,
          status TEXT NOT NULL, speed REAL DEFAULT 0, created REAL NOT NULL
        );
        CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS idx_downloads_status ON downloads(status);
        CREATE INDEX IF NOT EXISTS idx_downloads_created ON downloads(created);
        """)
        self.conn.commit()

    def upsert(self, d: dict):
        self.conn.execute("""INSERT INTO downloads(id,url,filename,destination,total,downloaded,status,speed,created)
        VALUES(?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET
        downloaded=excluded.downloaded,total=excluded.total,status=excluded.status,speed=excluded.speed""",
        (d['id'],d['url'],d['filename'],d['destination'],d.get('total'),d.get('downloaded',0),d['status'],d.get('speed',0),d['created']))
        self.conn.commit()

    def list(self):
        return self.conn.execute("SELECT * FROM downloads ORDER BY created DESC").fetchall()

    def close(self):
        self.conn.close()
