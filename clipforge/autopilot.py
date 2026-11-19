"""Autopilot: follow source channels per account; on a daily schedule, new uploads are downloaded and turned into shorts
that land in Review. Nothing is posted without approval.

Per-account config (accounts.autopilot JSON): {enabled, time "HH:MM" (plan timezone), max_videos per run, last_run date}.
"""
from __future__ import annotations

import time

from . import db

SCHEMA = """
CREATE TABLE IF NOT EXISTS sources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account TEXT NOT NULL,
    url TEXT NOT NULL,
    label TEXT,
    enabled INTEGER NOT NULL DEFAULT 1,
    last_checked REAL,
    created REAL NOT NULL,
    UNIQUE(account, url)
);
CREATE TABLE IF NOT EXISTS seen_uploads (
    account TEXT NOT NULL,
    video_id TEXT NOT NULL,
    title TEXT,
    queued INTEGER NOT NULL DEFAULT 0,
    seen REAL NOT NULL,
    PRIMARY KEY (account, video_id)
);
"""
DEFAULTS = {"enabled": False, "time": "07:00", "max_videos": 2, "last_run": ""}


def _con():
    con = db.connect()
    return con


def _init(con) -> None:
    con.executescript(SCHEMA)


def _normalize(url: str) -> str:
    url = url.strip().rstrip("/")
    if url.startswith("@"):
        url = f"https://www.youtube.com/{url}"
    if "youtube.com/@" in url and not url.endswith(("/videos", "/shorts", "/streams")):
        url += "/videos"
    return url


def latest(url: str, n: int = 8) -> tuple[str, list[dict]]:
    """(channel name, [{id, title, url}] newest first) without downloading anything."""
    import yt_dlp

    opts = {"extract_flat": "in_playlist", "playlistend": n, "quiet": True, "no_warnings": True, "skip_download": True}
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)
    entries = [e for e in (info.get("entries") or []) if e and e.get("id")][:n]
    name = info.get("channel") or info.get("uploader") or info.get("title") or url
    return name, [{"id": e["id"], "title": e.get("title") or e["id"],
                   "url": e.get("url") if str(e.get("url", "")).startswith("http") else f"https://www.youtube.com/watch?v={e['id']}"}
                  for e in entries]


def config(account: str) -> dict:
    from .accounts import get

    return DEFAULTS | (get(account).get("autopilot") or {})


def sources(account: str) -> list[dict]:
    with _con() as con:
        _init(con)
        return [dict(r) for r in con.execute("SELECT * FROM sources WHERE account=? ORDER BY created", (account,))]


def add_source(account: str, url: str, backfill: int = 0) -> dict:
    """Follow a channel. Existing uploads are marked seen, except the newest `backfill` which get processed next run."""
    url = _normalize(url)
    name, items = latest(url)
    with _con() as con:
        _init(con)
        con.execute("INSERT OR IGNORE INTO sources(account,url,label,enabled,created) VALUES(?,?,?,1,?)", (account, url, name, time.time()))
        for i, it in enumerate(items):
            if i >= backfill:
                con.execute("INSERT OR IGNORE INTO seen_uploads(account,video_id,title,queued,seen) VALUES(?,?,?,0,?)",
                            (account, it["id"], it["title"], time.time()))
        row = con.execute("SELECT * FROM sources WHERE account=? AND url=?", (account, url)).fetchone()
    return dict(row) | {"latest": items[:3]}


def remove_source(account: str, source_id: int) -> None:
    with _con() as con:
        _init(con)
        con.execute("DELETE FROM sources WHERE id=? AND account=?", (source_id, account))


def toggle(account: str, source_id: int, enabled: bool) -> None:
    with _con() as con:
        _init(con)
        con.execute("UPDATE sources SET enabled=? WHERE id=? AND account=?", (int(enabled), source_id, account))


def new_uploads(account: str, max_videos: int, mark: bool = True) -> list[dict]:
    """Unseen uploads across enabled sources, newest first, capped. Marks them queued (unless mark=False: a peek)."""
    found = []
    for s in [x for x in sources(account) if x["enabled"]]:
        try:
            _, items = latest(s["url"])
        except Exception as e:  # noqa: BLE001  (one dead channel shouldn't stop the rest)
            print(f"  source failed {s['url']}: {e}")
            continue
        with _con() as con:
            _init(con)
            con.execute("UPDATE sources SET last_checked=? WHERE id=?", (time.time(), s["id"]))
            seen = {r[0] for r in con.execute("SELECT video_id FROM seen_uploads WHERE account=?", (account,))}
        found += [it | {"source": s["label"]} for it in items if it["id"] not in seen]
    picked, ids = [], set()
    for it in found:
        if it["id"] not in ids and len(picked) < max_videos:
            picked.append(it)
            ids.add(it["id"])
    with _con() as con:
        _init(con)
        for it in (picked if mark else []):
            con.execute("INSERT OR REPLACE INTO seen_uploads(account,video_id,title,queued,seen) VALUES(?,?,?,1,?)",
                        (account, it["id"], it["title"], time.time()))
    return picked


def due(account: str, now) -> bool:
    c = config(account)
    if not c["enabled"]:
        return False
    hh, mm = (int(x) for x in c["time"].split(":"))
    return now.strftime("%Y-%m-%d") != c.get("last_run") and (now.hour, now.minute) >= (hh, mm)


def mark_ran(account: str, now) -> None:
    from .accounts import update

    update(account, autopilot={"last_run": now.strftime("%Y-%m-%d")})
