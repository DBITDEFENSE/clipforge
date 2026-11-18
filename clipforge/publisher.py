"""Approve -> schedule -> publish. YouTube: uploaded right away with publishAt (YouTube flips it public at the slot).
TikTok: no scheduling API, so the studio (or `clipforge publish-due`) posts it when the slot arrives, using the options
and consent captured when you approved it. Every transition is written to the posts table and out/queue.csv."""
from __future__ import annotations

import datetime as dt
import json
import time
import traceback
from pathlib import Path

from . import db, schedule
from .config import WORK
from .publish import NotConnected, tiktok, youtube

PLATFORMS = ("youtube", "tiktok")


def _script(short_id: str) -> dict:
    return json.loads((WORK / "shorts" / short_id / "script.json").read_text(encoding="utf-8"))


def defaults(short_id: str) -> dict:
    s = _script(short_id)
    p = s["post"]
    tags = " ".join(p["hashtags"])
    return {
        "youtube": {"title": s["title"][:95], "description": f"{p['caption']}\n\n{tags} #Shorts"},
        "tiktok": {"caption": f"{p['caption']} {tags}".strip()},
        "pinned_comment": p.get("pinned_comment", ""),
    }


def _set(short_id: str, platform: str, **f) -> None:
    f["updated"] = time.time()
    with db.connect() as con:
        exists = con.execute("SELECT 1 FROM posts WHERE short_id=? AND platform=?", (short_id, platform)).fetchone()
        if exists:
            con.execute(f"UPDATE posts SET {', '.join(k + '=?' for k in f)} WHERE short_id=? AND platform=?", (*f.values(), short_id, platform))
        else:
            f.setdefault("status", "queued")
            con.execute(f"INSERT INTO posts(short_id, platform, {', '.join(f)}) VALUES(?,?,{','.join('?' * len(f))})", (short_id, platform, *f.values()))


def posts_for(short_id: str) -> dict[str, dict]:
    with db.connect() as con:
        return {r["platform"]: dict(r) for r in con.execute("SELECT * FROM posts WHERE short_id=?", (short_id,))}


def approve(short_id: str, slot_iso: str, targets: dict) -> None:
    """targets: {"youtube": {title, description}, "tiktok": {caption, privacy, allow_comment, allow_duet, allow_stitch,
    brand_organic, branded_content, is_aigc, consent: true}}. Only platforms present are scheduled."""
    if "tiktok" in targets:
        t = targets["tiktok"]
        if not t.get("consent"):
            raise ValueError("TikTok needs your explicit consent to post")
        if not t.get("privacy"):
            raise ValueError("pick a TikTok privacy level")
        if t.get("branded_content") and t["privacy"] == "SELF_ONLY":
            raise ValueError("branded content can't be private on TikTok")
    with db.connect() as con:
        clash = con.execute("SELECT id FROM shorts WHERE review='approved' AND slot=? AND id!=?", (slot_iso, short_id)).fetchone()
    if clash:
        raise ValueError(f"that slot is already taken by {clash['id']}")
    schedule.set_review(short_id, "approved", slot_iso)
    for p in PLATFORMS:
        if p in targets:
            _set(short_id, p, status="queued", scheduled_at=slot_iso, options=json.dumps(targets[p]), error=None)
        elif p in posts_for(short_id) and posts_for(short_id)[p]["status"] == "queued":
            _set(short_id, p, status="canceled")
    schedule.write_queue()


def unapprove(short_id: str) -> list[str]:
    """Back to pending. Returns notes about anything already on a platform (those must be removed there)."""
    notes = []
    for p, row in posts_for(short_id).items():
        if row["status"] in ("queued", "failed"):
            _set(short_id, p, status="canceled")
        elif row["status"] in ("scheduled", "posted", "uploading"):
            notes.append(f"{p}: already uploaded ({row['url'] or row['remote_id']}); delete or reschedule it in {p.title()} Studio")
    schedule.set_review(short_id, "pending", None)
    return notes


def reject(short_id: str, notes: str = "") -> None:
    unapprove(short_id)
    schedule.set_review(short_id, "rejected", None, notes or None)


def post_now(short_id: str, platform: str) -> None:
    row = posts_for(short_id).get(platform)
    if not row:
        raise ValueError("approve it for this platform first")
    _set(short_id, platform, status="queued", scheduled_at=schedule.now().isoformat(), error=None)
    _publish_one(short_id, platform)


def _mp4(short_id: str) -> Path:
    with db.connect() as con:
        out = con.execute("SELECT out_dir FROM shorts WHERE id=?", (short_id,)).fetchone()["out_dir"]
    return Path(out) / "final.mp4"


def _publish_one(short_id: str, platform: str) -> None:
    row = posts_for(short_id)[platform]
    opts = json.loads(row["options"] or "{}")
    when = dt.datetime.fromisoformat(row["scheduled_at"])
    _set(short_id, platform, status="uploading", error=None)
    try:
        if platform == "youtube":
            r = youtube.upload(_mp4(short_id), opts.get("title") or schedule.title_of(short_id), opts.get("description", ""),
                               _script(short_id)["post"]["hashtags"], when, synthetic_media=opts.get("synthetic_media", True))
            _set(short_id, platform, status="scheduled" if r["scheduled"] else "posted", remote_id=r["id"], url=r["url"])
        else:
            info = tiktok.creator_info()  # re-check right before posting: account may have changed
            if opts["privacy"] not in info.get("privacy_level_options", []):
                raise RuntimeError(f"privacy {opts['privacy']} is no longer allowed for this account: {info.get('privacy_level_options')}")
            pid = tiktok.post(_mp4(short_id), opts.get("caption", ""), opts["privacy"], bool(opts.get("allow_comment")),
                              bool(opts.get("allow_duet")), bool(opts.get("allow_stitch")), bool(opts.get("brand_organic")),
                              bool(opts.get("branded_content")), bool(opts.get("is_aigc", True)))
            _set(short_id, platform, status="uploading", remote_id=pid)
    except NotConnected as e:
        _set(short_id, platform, status="queued", error=str(e))  # stays queued; posts once you reconnect
    except Exception as e:  # noqa: BLE001
        _set(short_id, platform, status="failed", error=f"{e}\n{traceback.format_exc(limit=2)}"[-1500:])
    schedule.write_queue()


def tick() -> list[str]:
    """Do whatever is due. Safe to call every minute. Returns a log of what happened."""
    log, now = [], schedule.now()
    with db.connect() as con:
        rows = [dict(r) for r in con.execute(
            "SELECT p.* FROM posts p JOIN shorts s ON s.id=p.short_id WHERE s.review='approved' AND p.status IN ('queued','uploading','scheduled')")]
    for r in rows:
        sid, plat, st = r["short_id"], r["platform"], r["status"]
        when = dt.datetime.fromisoformat(r["scheduled_at"])
        if st == "queued":
            ready = (plat == "youtube" and youtube.connected()) or (plat == "tiktok" and tiktok.connected() and when <= now)
            if ready:
                _publish_one(sid, plat)
                log.append(f"{plat}: published {sid}")
        elif st == "uploading" and plat == "tiktok" and r["remote_id"]:
            try:
                s = tiktok.status(r["remote_id"])
            except Exception as e:  # noqa: BLE001
                log.append(f"tiktok status {sid}: {e}")
                continue
            if s.get("status") == "PUBLISH_COMPLETE":
                ids = s.get("publicaly_available_post_id") or []
                _set(sid, plat, status="posted", url=f"https://www.tiktok.com/video/{ids[0]}" if ids else None,
                     remote_id=str(ids[0]) if ids else r["remote_id"])
                log.append(f"tiktok: live {sid}")
            elif s.get("status") == "FAILED":
                _set(sid, plat, status="failed", error=s.get("fail_reason") or "TikTok reported FAILED")
                log.append(f"tiktok: failed {sid}")
        elif st == "scheduled" and when <= now:
            _set(sid, plat, status="posted")
    if log:
        schedule.write_queue()
    return log


def refresh_metrics() -> int:
    """Pull view/like/comment/share counts for everything posted. Returns rows written."""
    with db.connect() as con:
        rows = [dict(r) for r in con.execute("SELECT short_id, platform, remote_id FROM posts WHERE status IN ('posted','scheduled') AND remote_id IS NOT NULL")]
    n, ts = 0, time.time()
    for plat, client in (("youtube", youtube), ("tiktok", tiktok)):
        mine = {r["remote_id"]: r["short_id"] for r in rows if r["platform"] == plat}
        if not mine or not client.connected():
            continue
        try:
            stats = client.stats(list(mine))
        except Exception:  # noqa: BLE001  (e.g. scope missing); metrics are best-effort
            continue
        with db.connect() as con:
            for rid, m in stats.items():
                if rid in mine:
                    con.execute("INSERT OR REPLACE INTO metrics VALUES(?,?,?,?,?,?,?)",
                                (mine[rid], plat, ts, m["views"], m["likes"], m["comments"], m["shares"]))
                    n += 1
    return n
