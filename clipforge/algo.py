"""My algorithm: make shorts from what YouTube would show YOU.

Signs in as you with your browser's YouTube cookies (read by yt-dlp; nothing is typed into ClipForge), pulls your home
recommendations and subscriptions, ranks them with a taste profile built from your likes and watch history, and hands
the best videos to the normal pipeline. Each ClipForge channel has its own sign-in and settings, so several YouTube
accounts can each feed their own channel.

Per channel (autopilot JSON -> "algo"):
  browser, profile   read cookies live from this browser (firefox works best; Chrome/Edge lock theirs on Windows)
  feeds              which feeds to draw from (FEEDS keys)
  shorts             how many shorts a run aims for
  min_minutes, max_minutes   skip Shorts/clips and marathon streams
  boost, block       words or channel names to favour / never use
  daily              also run with Autopilot each day
Or upload a cookies.txt export instead of naming a browser: it is stored at data/cookies/<channel>.txt (gitignored,
never sent anywhere except to YouTube by yt-dlp, never returned by the studio API).
"""
from __future__ import annotations

import json
import math
import re
import time
from pathlib import Path

from . import db
from .config import DATA, settings

FEEDS = {
    "recommended": (":ytrec", "Home feed: what YouTube recommends you"),
    "subscriptions": (":ytsubs", "New uploads from your subscriptions"),
    "watch_later": (":ytwatchlater", "Your Watch Later list"),
    "liked": (":ytfav", "Videos you liked"),
}
TASTE = {"liked": ":ytfav", "history": ":ythistory"}  # only used to learn which channels you actually watch
FEED_WEIGHT = {"watch_later": 1.3, "recommended": 1.0, "subscriptions": 0.9, "liked": 0.7}
BROWSERS = ["firefox", "chrome", "edge", "brave", "opera", "vivaldi", "chromium"]
DEFAULTS = {"browser": "", "profile": "", "feeds": ["recommended", "subscriptions"], "shorts": 15, "min_minutes": 2,
            "max_minutes": 45, "boost": [], "block": [], "daily": False}
COOKIES = DATA / "cookies"
PROFILES = DATA / "algo"
PROFILE_TTL = 24 * 3600


# ---------- settings ----------
def clean(raw: dict | None) -> dict:
    raw = raw if isinstance(raw, dict) else {}
    words = lambda v: [str(x).strip()[:60] for x in (v if isinstance(v, list) else str(v or "").split(",")) if str(x).strip()][:40]  # noqa: E731
    c = dict(DEFAULTS)
    if raw.get("browser") in BROWSERS:
        c["browser"] = raw["browser"]
    if isinstance(raw.get("profile"), str) and re.fullmatch(r"[\w .@-]{0,80}", raw["profile"]):
        c["profile"] = raw["profile"].strip()
    feeds = [f for f in raw.get("feeds") or [] if f in FEEDS]
    c["feeds"] = feeds or list(DEFAULTS["feeds"])
    for k, lo, hi in (("shorts", 1, 200), ("min_minutes", 0, 600), ("max_minutes", 1, 720)):
        try:
            c[k] = max(lo, min(hi, int(raw.get(k, DEFAULTS[k]))))
        except (TypeError, ValueError):
            pass
    c["max_minutes"] = max(c["max_minutes"], c["min_minutes"] + 1)
    c["boost"], c["block"] = words(raw.get("boost")), words(raw.get("block"))
    c["daily"] = bool(raw.get("daily"))
    return c


def config(account: str) -> dict:
    from .accounts import get

    return clean((get(account).get("autopilot") or {}).get("algo"))


def save_config(account: str, raw: dict) -> dict:
    from .accounts import update

    c = clean(config(account) | {k: v for k, v in raw.items() if k in DEFAULTS})
    update(account, autopilot={"algo": c})
    return c


# ---------- sign-in ----------
def cookie_file(account: str) -> Path:
    return COOKIES / f"{re.sub(r'[^A-Za-z0-9_-]', '_', account)}.txt"


def save_cookies(account: str, text: str) -> int:
    """Store a Netscape-format cookies.txt export. Returns how many YouTube/Google cookies it holds."""
    rows = [ln for ln in text.splitlines() if ln.strip() and (not ln.startswith("#") or ln.startswith("#HttpOnly_"))]
    good = [ln for ln in rows if len(ln.split("\t")) >= 7]
    yt = [ln for ln in good if re.search(r"(youtube|google)\.com", ln.split("\t")[0])]
    if not yt:
        raise ValueError("That doesn't look like a cookies.txt export with YouTube cookies in it (Netscape format, tab-separated).")
    COOKIES.mkdir(parents=True, exist_ok=True)
    cookie_file(account).write_text("# Netscape HTTP Cookie File\n" + "\n".join(yt) + "\n", encoding="utf-8")
    return len(yt)


def forget_cookies(account: str) -> None:
    cookie_file(account).unlink(missing_ok=True)


def auth_opts(account: str, c: dict | None = None) -> dict:
    """yt-dlp options that sign in as the channel's YouTube user ({} when not connected)."""
    f = cookie_file(account)
    if f.exists():
        return {"cookiefile": str(f)}
    c = c or config(account)
    if c["browser"]:
        return {"cookiesfrombrowser": (c["browser"], c["profile"] or None, None, None)}
    return {}


def connected(account: str) -> str:
    """'file', 'browser' or ''."""
    return "file" if cookie_file(account).exists() else ("browser" if config(account)["browser"] else "")


def explain(e: Exception) -> str:
    """A yt-dlp sign-in failure in plain words."""
    m = str(e)
    low = m.lower()
    if m.startswith("Connect your YouTube"):
        return m
    if "dpapi" in low or "app-bound" in low or "failed to decrypt" in low or "could not copy" in low or "permission denied" in low:
        return ("That browser keeps its cookies locked on Windows. Use Firefox (sign in to YouTube there once), "
                "or upload a cookies.txt export instead.")
    if "could not find" in low and "cookies" in low:
        return "No cookies found for that browser/profile. Check that it's installed and you're signed in to YouTube in it."
    if "login" in low or "sign in" in low or "authentication" in low or "cookies" in low:
        return "YouTube says you're not signed in. Sign in to YouTube in that browser (or upload fresh cookies) and try again."
    return re.sub(r"\x1b\[[0-9;]*m", "", m)[:240]


# ---------- reading feeds ----------
def _entry(e: dict, feed: str, pos: int) -> dict | None:
    if not e or not e.get("id") or (e.get("ie_key") and e["ie_key"] != "Youtube"):
        return None
    url = str(e.get("url") or "")
    return {"id": e["id"], "title": e.get("title") or e["id"], "channel": e.get("channel") or e.get("uploader") or "",
            "channel_id": e.get("channel_id") or "", "duration": e.get("duration"), "views": e.get("view_count"),
            "live": e.get("live_status") in ("is_live", "is_upcoming"), "short": "/shorts/" in url,
            "url": f"https://www.youtube.com/watch?v={e['id']}", "feed": feed, "pos": pos}


def fetch(spec: str, feed: str, n: int, auth: dict) -> list[dict]:
    """Up to n videos from a yt-dlp feed keyword, without downloading anything."""
    import yt_dlp

    opts = {"extract_flat": "in_playlist", "playlistend": n, "quiet": True, "no_warnings": True, "skip_download": True, **auth}
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(spec, download=False)
    out = [_entry(e, feed, i) for i, e in enumerate((info or {}).get("entries") or [])]
    owner = (info or {}).get("channel") or ""  # a single channel's tab names the channel once, not per video
    return [e | {"channel": e["channel"] or owner} for e in out if e][:n]


def profile(account: str, auth: dict, refresh: bool = False) -> dict:
    """Taste profile: how often each channel shows up in your likes and history. Cached for a day."""
    f = PROFILES / f"{re.sub(r'[^A-Za-z0-9_-]', '_', account)}.json"
    if f.exists() and not refresh:
        try:
            p = json.loads(f.read_text(encoding="utf-8"))
            if time.time() - p.get("built", 0) < PROFILE_TTL:
                return p
        except ValueError:
            pass
    channels: dict[str, float] = {}
    for kind, spec in TASTE.items():
        try:
            for e in fetch(spec, kind, 150, auth):
                if e["channel"]:
                    channels[e["channel"]] = channels.get(e["channel"], 0) + (2.0 if kind == "liked" else 1.0)
        except Exception as ex:  # noqa: BLE001  (history can be paused/off; the feed still works without a profile)
            print(f"  taste profile: {kind} unavailable ({explain(ex)[:80]})")
    p = {"built": time.time(), "channels": dict(sorted(channels.items(), key=lambda kv: -kv[1])[:300])}
    PROFILES.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(p), encoding="utf-8")
    return p


# ---------- ranking ----------
def _hits(words: list[str], e: dict) -> int:
    text = f" {e['title']} {e['channel']} ".lower()
    return sum(1 for w in words if w.lower() in text)


def rank(cands: list[dict], prof: dict, c: dict, seen: set[str]) -> list[dict]:
    """Best first. Drops Shorts, live streams, out-of-range lengths, blocked words and videos already used; scores the
    rest by feed, position in the feed, how much you watch that channel, and boost words."""
    aff = prof.get("channels") or {}
    best: dict[str, dict] = {}
    for e in cands:
        mins = (e["duration"] or 0) / 60
        if e["id"] in seen or e["live"] or e["short"] or _hits(c["block"], e):
            continue
        if e["duration"] is not None and not c["min_minutes"] <= mins <= c["max_minutes"]:
            continue
        score = FEED_WEIGHT.get(e["feed"], 0.5) * (1.0 / (1.0 + 0.04 * e["pos"]))
        score += 0.35 * math.log1p(aff.get(e["channel"], 0)) + 0.6 * _hits(c["boost"], e)
        if e["id"] in best:  # in several feeds: keep the better entry, plus a small bonus for showing up twice
            score = max(score, best[e["id"]]["score"]) + 0.2
        best[e["id"]] = e | {"score": round(score, 3), "fan": aff.get(e["channel"], 0) > 0}
    return sorted(best.values(), key=lambda x: -x["score"])


def spread(ranked: list[dict], n: int, per_channel: int = 2) -> list[dict]:
    """Top n with at most `per_channel` videos from one channel, so a batch isn't all the same creator."""
    out, count = [], {}
    for e in ranked:
        k = e["channel"] or e["id"]
        if count.get(k, 0) < per_channel:
            out.append(e)
            count[k] = count.get(k, 0) + 1
        if len(out) >= n:
            break
    return out


# ---------- seen / used ----------
def _seen(account: str) -> set[str]:
    from . import autopilot

    with db.connect() as con:
        autopilot._init(con)
        return {r[0] for r in con.execute("SELECT video_id FROM seen_uploads WHERE account=?", (account,))}


def mark_used(account: str, e: dict) -> None:
    from . import autopilot

    with db.connect() as con:
        autopilot._init(con)
        con.execute("INSERT OR REPLACE INTO seen_uploads(account,video_id,title,queued,seen) VALUES(?,?,?,1,?)",
                    (account, e["id"], e["title"], time.time()))


# ---------- the feed ----------
def videos_needed(shorts: int) -> int:
    return max(1, math.ceil(shorts / max(1, int(settings()["plan"].get("per_video", 3)))))


def feed(account: str, limit: int = 60, refresh_profile: bool = False) -> dict:
    """Ranked candidates for this channel: {"videos": [...], "errors": [...], "profile_channels": n}."""
    c = config(account)
    auth = auth_opts(account, c)
    if not auth:
        raise RuntimeError("Connect your YouTube first (pick the browser you're signed in with, or upload cookies.txt).")
    cands, errors = [], []
    for name in c["feeds"]:
        try:
            cands += fetch(FEEDS[name][0], name, 120, auth)
        except Exception as e:  # noqa: BLE001
            errors.append(f"{name}: {explain(e)}")
    if not cands and errors:
        raise RuntimeError(errors[0].split(": ", 1)[1])
    prof = profile(account, auth, refresh_profile)
    ranked = rank(cands, prof, c, _seen(account))
    return {"videos": spread(ranked, limit, per_channel=4), "errors": errors, "profile_channels": len(prof.get("channels") or {}),
            "top_channels": list(prof.get("channels") or {})[:8]}
