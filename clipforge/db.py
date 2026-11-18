"""SQLite state: which uploads are processed, mined stories, produced shorts."""
from __future__ import annotations

import json
import sqlite3
import time
from contextlib import contextmanager

from .config import DB_PATH, ensure_dirs

SCHEMA = """
CREATE TABLE IF NOT EXISTS videos (
    hash TEXT PRIMARY KEY,
    path TEXT NOT NULL,
    title TEXT,
    source_url TEXT,
    status TEXT NOT NULL DEFAULT 'new',      -- new | transcribed | mined | failed
    error TEXT,
    created REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS stories (
    id TEXT PRIMARY KEY,
    batch_id TEXT NOT NULL,
    data TEXT NOT NULL,
    score REAL NOT NULL,
    picked INTEGER NOT NULL DEFAULT 0,
    day INTEGER,
    created REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS shorts (
    id TEXT PRIMARY KEY,
    story_id TEXT NOT NULL,
    batch_id TEXT NOT NULL,
    status TEXT NOT NULL,                     -- writing | voiced | rendered | done | flagged | failed
    out_dir TEXT,
    qa TEXT,
    error TEXT,
    created REAL NOT NULL,
    updated REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS posts (
    short_id TEXT NOT NULL,
    platform TEXT NOT NULL,                   -- youtube | tiktok
    status TEXT NOT NULL,                     -- queued | uploading | scheduled | posted | failed | canceled
    scheduled_at TEXT,                        -- ISO 8601 with offset (America/New_York)
    options TEXT,                             -- JSON: title/caption/privacy/toggles chosen at approval
    remote_id TEXT,                           -- YouTube video id / TikTok publish_id
    url TEXT,
    error TEXT,
    updated REAL NOT NULL,
    PRIMARY KEY (short_id, platform)
);
CREATE TABLE IF NOT EXISTS metrics (
    short_id TEXT NOT NULL,
    platform TEXT NOT NULL,
    ts REAL NOT NULL,
    views INTEGER, likes INTEGER, comments INTEGER, shares INTEGER,
    PRIMARY KEY (short_id, platform, ts)
);
CREATE TABLE IF NOT EXISTS accounts (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    handle TEXT,
    persona TEXT,
    brand TEXT,                               -- JSON overrides of config/brand.yaml (colors, fonts)
    voice TEXT,                               -- JSON {voice_id, ...}
    slots TEXT,                               -- JSON ["09:00", ...] in plan.timezone
    password_hash TEXT,
    created REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS ads (
    short_id TEXT PRIMARY KEY,
    status TEXT NOT NULL,                     -- candidate | boosted | dismissed
    note TEXT,
    spend REAL,
    updated REAL NOT NULL
);
"""
MIGRATIONS = [
    "ALTER TABLE shorts ADD COLUMN review TEXT NOT NULL DEFAULT 'pending'",   # pending | approved | rejected
    "ALTER TABLE shorts ADD COLUMN slot TEXT",   # ISO post time (America/New_York)
    "ALTER TABLE shorts ADD COLUMN notes TEXT",
    "ALTER TABLE shorts ADD COLUMN account TEXT NOT NULL DEFAULT 'dbit-defense'",
    "ALTER TABLE videos ADD COLUMN account TEXT NOT NULL DEFAULT 'dbit-defense'",
    "ALTER TABLE stories ADD COLUMN account TEXT NOT NULL DEFAULT 'dbit-defense'",
]


@contextmanager
def connect():
    ensure_dirs()
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.executescript(SCHEMA)
    for m in MIGRATIONS:
        try:
            con.execute(m)
        except sqlite3.OperationalError:  # column already there
            pass
    try:
        yield con
        con.commit()
    finally:
        con.close()


def _acct() -> str:
    from .accounts import current_id  # lazy: accounts imports db

    return current_id()


def video_known(h: str) -> sqlite3.Row | None:
    with connect() as con:
        return con.execute("SELECT * FROM videos WHERE hash=?", (h,)).fetchone()


def add_video(h: str, path: str, title: str | None, url: str | None = None) -> None:
    with connect() as con:
        con.execute(
            "INSERT OR IGNORE INTO videos(hash,path,title,source_url,created) VALUES(?,?,?,?,?)",
            (h, path, title, url, time.time()),
        )


def set_video_status(h: str, status: str, error: str | None = None) -> None:
    with connect() as con:
        con.execute("UPDATE videos SET status=?, error=? WHERE hash=?", (status, error, h))


def videos_with_status(*statuses: str) -> list[sqlite3.Row]:
    q = ",".join("?" * len(statuses))
    with connect() as con:
        return con.execute(f"SELECT * FROM videos WHERE status IN ({q}) ORDER BY created", statuses).fetchall()


def save_story(story_id: str, batch_id: str, data: dict, score: float, picked: bool, day: int | None) -> None:
    with connect() as con:
        con.execute(
            "INSERT OR REPLACE INTO stories(id,batch_id,data,score,picked,day,created) VALUES(?,?,?,?,?,?,?)",
            (story_id, batch_id, json.dumps(data), score, int(picked), day, time.time()),
        )


def upsert_short(short_id: str, story_id: str, batch_id: str, status: str, **fields) -> None:
    now = time.time()
    with connect() as con:
        con.execute(
            "INSERT INTO shorts(id,story_id,batch_id,status,created,updated,account) VALUES(?,?,?,?,?,?,?) "
            "ON CONFLICT(id) DO UPDATE SET status=excluded.status, updated=excluded.updated",
            (short_id, story_id, batch_id, status, now, now, _acct()),
        )
        for k, v in fields.items():
            if k not in {"out_dir", "qa", "error"}:
                raise ValueError(k)
            con.execute(f"UPDATE shorts SET {k}=? WHERE id=?", (v if not isinstance(v, (dict, list)) else json.dumps(v), short_id))
