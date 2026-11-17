"""Stock B-roll from Pexels (free for commercial use, no attribution required). Cached per query."""
from __future__ import annotations

import re
import shutil
from pathlib import Path

import httpx

from .config import DATA, secret

CACHE = DATA / "broll_cache"
_last_credit = ""


def last_credit() -> str:
    return _last_credit


def _pick_file(video: dict) -> dict | None:
    files = [f for f in video.get("video_files", []) if f.get("file_type") == "video/mp4" and f.get("height") and f.get("width")]
    portrait = [f for f in files if f["height"] > f["width"] and 1000 <= f["height"] <= 2200]
    pool = portrait or [f for f in files if 720 <= f["height"] <= 2200]
    return min(pool, key=lambda f: abs(f["height"] - 1920)) if pool else None


def fetch(query: str, dest: Path) -> Path | None:
    """Download the best portrait clip for `query` to dest. Returns None if there's no key or no match."""
    global _last_credit
    key = secret("PEXELS_API_KEY", required=False)
    if not key or not query:
        return None
    slug = re.sub(r"[^a-z0-9]+", "-", query.lower()).strip("-")[:60]
    CACHE.mkdir(parents=True, exist_ok=True)
    cached = CACHE / f"{slug}.mp4"
    credit_file = cached.with_suffix(".txt")
    if not cached.exists():
        try:
            r = httpx.get("https://api.pexels.com/videos/search", headers={"Authorization": key},
                          params={"query": query, "orientation": "portrait", "size": "medium", "per_page": 10}, timeout=30)
            r.raise_for_status()
            videos = [v for v in r.json().get("videos", []) if (v.get("duration") or 0) >= 4]
            choice = next(((v, f) for v in videos if (f := _pick_file(v))), None)
            if not choice:
                return None
            v, f = choice
            with httpx.stream("GET", f["link"], timeout=120, follow_redirects=True) as resp:
                resp.raise_for_status()
                with open(cached, "wb") as out:
                    for chunk in resp.iter_bytes():
                        out.write(chunk)
            credit_file.write_text(f"{v.get('user', {}).get('name', 'Pexels')} via Pexels: {v.get('url', '')}", encoding="utf-8")
        except httpx.HTTPError:
            cached.unlink(missing_ok=True)
            return None
    _last_credit = credit_file.read_text(encoding="utf-8") if credit_file.exists() else "Pexels"
    shutil.copy2(cached, dest)
    return dest
