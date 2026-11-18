"""Growth loop: tell the writer what has actually performed on this channel (from posted shorts' metrics)."""
from __future__ import annotations

import json

from . import db
from .config import WORK


def ranked(account: str) -> list[dict]:
    with db.connect() as con:
        rows = con.execute("""
            SELECT s.id, SUM(m.views) views, SUM(COALESCE(m.likes,0)+COALESCE(m.comments,0)+COALESCE(m.shares,0)) eng
            FROM shorts s JOIN metrics m ON m.short_id=s.id
            JOIN (SELECT short_id, platform, MAX(ts) ts FROM metrics GROUP BY short_id, platform) l
              ON l.short_id=m.short_id AND l.platform=m.platform AND l.ts=m.ts
            WHERE s.account=? GROUP BY s.id ORDER BY views DESC""", (account,)).fetchall()
    out = []
    for r in rows:
        p = WORK / "shorts" / r["id"] / "script.json"
        if p.exists():
            s = json.loads(p.read_text(encoding="utf-8"))
            out.append({"id": r["id"], "views": r["views"] or 0, "eng": r["eng"] or 0, "title": s["title"], "hook": s["beats"][0]["text"]})
    return out


def summary(account: str, min_posts: int = 3) -> str:
    rows = ranked(account)
    if len(rows) < min_posts:
        return ""
    top, bottom = rows[:3], rows[-2:] if len(rows) >= 5 else []
    fmt = lambda r: f'- "{r["hook"]}" ({r["title"]}): {r["views"]:,} views'  # noqa: E731
    txt = "\n## What has performed on this channel (real numbers; learn from it, don't copy it)\nBest:\n" + "\n".join(map(fmt, top))
    if bottom:
        txt += "\nWeakest:\n" + "\n".join(map(fmt, bottom))
    return txt + "\nLean into the hook styles and topics that won; avoid what flopped.\n"
