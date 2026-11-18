"""Ad candidates from real performance. Recommends only: nothing here spends money. Boosting happens in TikTok Ads
Manager / YouTube (Google Ads) where you set the budget; mark it "boosted" here to track spend next to results."""
from __future__ import annotations

import datetime as dt
import statistics
import time

from . import db, schedule
from .config import settings


def _latest() -> list[dict]:
    with db.connect() as con:
        return [dict(r) for r in con.execute("""
            SELECT m.short_id, m.platform, m.views, m.likes, m.comments, m.shares, m.ts, p.scheduled_at, p.url
            FROM metrics m JOIN (SELECT short_id, platform, MAX(ts) ts FROM metrics GROUP BY short_id, platform) last
              ON last.short_id=m.short_id AND last.platform=m.platform AND last.ts=m.ts
            JOIN posts p ON p.short_id=m.short_id AND p.platform=m.platform""")]


def candidates() -> list[dict]:
    cfg = settings().get("ads", {})
    min_age_h, min_views, min_eng, lift = cfg.get("min_age_hours", 24), cfg.get("min_views", 1500), cfg.get("min_engagement", 0.04), cfg.get("lift", 1.5)
    rows, now = _latest(), schedule.now()
    with db.connect() as con:
        ads = {r["short_id"]: dict(r) for r in con.execute("SELECT * FROM ads")}
    out = []
    for plat in ("tiktok", "youtube"):
        mine = [r for r in rows if r["platform"] == plat]
        for r in mine:
            r["age_h"] = (now - dt.datetime.fromisoformat(r["scheduled_at"])).total_seconds() / 3600
        mature = [r["views"] or 0 for r in mine if r["age_h"] >= min_age_h]
        base = statistics.median(mature) if mature else 0
        for r in mine:
            v = r["views"] or 0
            eng = ((r["likes"] or 0) + (r["comments"] or 0) + (r["shares"] or 0)) / v if v else 0
            why, score = [], 0.0
            if r["age_h"] < min_age_h:
                continue
            if v >= min_views:
                score += 1
            if base and v >= lift * base:
                why.append(f"{v / base:.1f}x your median views")
                score += 1
            if eng >= min_eng:
                why.append(f"{eng:.1%} engagement")
                score += 1
            st = ads.get(r["short_id"], {}).get("status", "candidate")
            if score >= 2 and st != "dismissed" or st == "boosted":
                out.append({"short_id": r["short_id"], "title": schedule.title_of(r["short_id"]), "platform": plat, "views": v,
                            "engagement": round(eng, 4), "age_hours": round(r["age_h"]), "why": why, "url": r["url"], "status": st,
                            "spend": ads.get(r["short_id"], {}).get("spend"),
                            "suggested": f"${cfg.get('test_daily_usd', 20)}/day for {cfg.get('test_days', 3)} days, as a Spark Ad on the organic post"})
    return sorted(out, key=lambda c: (c["status"] != "boosted", -c["views"]))


def mark(short_id: str, status: str, spend: float | None = None, note: str | None = None) -> None:
    with db.connect() as con:
        con.execute("INSERT INTO ads(short_id,status,note,spend,updated) VALUES(?,?,?,?,?) ON CONFLICT(short_id) DO UPDATE SET "
                    "status=excluded.status, note=COALESCE(excluded.note, ads.note), spend=COALESCE(excluded.spend, ads.spend), updated=excluded.updated",
                    (short_id, status, note, spend, time.time()))
