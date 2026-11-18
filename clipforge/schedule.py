"""Posting schedule: daily slots in America/New_York, approve -> next free slot, out/queue.csv mirror."""
from __future__ import annotations

import csv
import datetime as dt
import json
from zoneinfo import ZoneInfo

from . import db
from .config import OUT, WORK, settings

BUFFER_MIN = 20  # never schedule a slot that starts sooner than this


def tz() -> ZoneInfo:
    return ZoneInfo(settings()["plan"]["timezone"])


def now() -> dt.datetime:
    return dt.datetime.now(tz())


def _acct() -> str:
    from .accounts import current_id

    return current_id()


def slot_times() -> list[dt.time]:
    from .accounts import current

    raw = current().get("slots") or settings()["plan"].get("slots") or ["09:00", "12:00", "15:00", "18:00", "21:00"]
    return sorted(dt.time.fromisoformat(t) for t in raw)


def taken() -> set[str]:
    with db.connect() as con:
        return {r["slot"] for r in con.execute("SELECT slot FROM shorts WHERE review='approved' AND slot IS NOT NULL AND account=?", (_acct(),))}


def next_free(after: dt.datetime | None = None, exclude: set[str] | None = None) -> dt.datetime:
    after = after or now() + dt.timedelta(minutes=BUFFER_MIN)
    busy = taken() | (exclude or set())
    day = after.date()
    for _ in range(366):
        for t in slot_times():
            cand = dt.datetime.combine(day, t, tz())
            if cand >= after and cand.isoformat() not in busy:
                return cand
        day += dt.timedelta(days=1)
    raise RuntimeError("no free slot in the next year")


def upcoming(days: int = 7) -> list[dict]:
    """Every slot for the next N days with what's in it."""
    with db.connect() as con:
        rows = {r["slot"]: r["id"] for r in con.execute("SELECT id, slot FROM shorts WHERE review='approved' AND slot IS NOT NULL AND account=?", (_acct(),))}
    out, start = [], now().date()
    for d in range(days):
        day = start + dt.timedelta(days=d)
        for t in slot_times():
            s = dt.datetime.combine(day, t, tz())
            out.append({"slot": s.isoformat(), "short_id": rows.get(s.isoformat()), "past": s < now()})
    return out


def title_of(short_id: str) -> str:
    p = WORK / "shorts" / short_id / "script.json"
    return json.loads(p.read_text(encoding="utf-8"))["title"] if p.exists() else short_id


def write_queue() -> None:
    """out/queue.csv: every approved short in posting order with per-platform status (times in America/New_York)."""
    with db.connect() as con:
        shorts = con.execute("SELECT id, slot, out_dir FROM shorts WHERE review='approved' AND slot IS NOT NULL AND account=? ORDER BY slot", (_acct(),)).fetchall()
        posts = {(r["short_id"], r["platform"]): r for r in con.execute("SELECT * FROM posts")}
    OUT.mkdir(parents=True, exist_ok=True)
    with open(OUT / f"queue-{_acct()}.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["post_time_et", "short_id", "title", "file", "youtube", "youtube_url", "tiktok", "tiktok_url"])
        for s in shorts:
            yt, tt = posts.get((s["id"], "youtube")), posts.get((s["id"], "tiktok"))
            w.writerow([dt.datetime.fromisoformat(s["slot"]).strftime("%Y-%m-%d %H:%M"), s["id"], title_of(s["id"]),
                        f"{s['out_dir']}\\final.mp4" if s["out_dir"] else "",
                        yt["status"] if yt else "", (yt["url"] or "") if yt else "",
                        tt["status"] if tt else "", (tt["url"] or "") if tt else ""])


def set_review(short_id: str, review: str, slot: str | None = None, notes: str | None = None) -> None:
    with db.connect() as con:
        con.execute("UPDATE shorts SET review=?, slot=?, notes=COALESCE(?, notes) WHERE id=?", (review, slot, notes, short_id))
    write_queue()
