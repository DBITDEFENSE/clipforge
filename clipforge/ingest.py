"""Get videos into inbox/ (from URLs or files), hash them, extract 16 kHz mono audio."""
from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import yt_dlp

from . import db
from .config import INBOX, VIDEO_EXTS, WORK, settings

SKIP_DEFAULT = ["sponsor", "selfpromo", "interaction"]  # SponsorBlock categories cut out of every download


def skip_categories() -> list[str]:
    cats = (settings().get("ingest") or {}).get("skip_segments", SKIP_DEFAULT)
    known = {"sponsor", "selfpromo", "interaction", "intro", "outro", "preview", "music_offtopic", "filler"}
    return [c for c in cats or [] if c in known]


def sponsor_postprocessors(cats: list[str]) -> list[dict]:
    """yt-dlp post-processors that look the video up on SponsorBlock and cut those parts out of the file, so in-video
    ads never reach the transcript, the stories or the clips. (Same as `yt-dlp --sponsorblock-remove`.)"""
    if not cats:
        return []
    return [{"key": "SponsorBlock", "categories": set(cats), "api": "https://sponsor.ajay.app", "when": "after_filter"},
            {"key": "ModifyChapters", "remove_chapters_patterns": [], "remove_sponsor_segments": set(cats), "remove_ranges": [],
             "sponsorblock_chapter_title": "[SponsorBlock]: %(category_names)l", "force_keyframes": False}]


def _auth() -> dict:
    """The active channel's YouTube sign-in, when it has one (also unlocks age-restricted and members videos)."""
    try:
        from . import accounts, algo

        return algo.auth_opts(accounts.current_id())
    except Exception:  # noqa: BLE001
        return {}


def download(url: str) -> Path:
    """Download a link into inbox/ (<=1080p is plenty for research input), with sponsor reads cut out. Records the
    source URL."""
    cats = skip_categories()
    try:
        return _download(url, sponsor_postprocessors(cats), cats)
    except Exception as e:  # noqa: BLE001
        if not cats:
            raise
        print(f"  ad removal failed ({str(e)[:120]}); downloading without it")
        return _download(url, [], [])


def _download(url: str, pps: list[dict], cats: list[str]) -> Path:
    opts = {
        "outtmpl": str(INBOX / "%(title).120B [%(id)s].%(ext)s"),
        "format": "bv*[height<=1080]+ba/b[height<=1080]/b",
        "format_sort": ["res:1080", "vcodec:h264", "acodec:aac"],
        "merge_output_format": "mp4",
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "js_runtimes": {"deno": {}, "node": {}},
        "postprocessors": pps,
        **_auth(),
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)
        path = Path(info.get("requested_downloads", [{}])[0].get("filepath") or ydl.prepare_filename(info))
    meta = {"url": info.get("webpage_url") or url, "title": info.get("title"), "uploader": info.get("uploader"),
            "upload_date": info.get("upload_date"), "duration": info.get("duration"), "video_id": info.get("id"),
            "ads_removed": [[round(c.get("start_time", 0), 1), round(c.get("end_time", 0), 1), c.get("category", "")]
                            for c in (info.get("sponsorblock_chapters") or []) if c.get("category") in cats]}
    path.with_suffix(".source.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return path


def file_hash(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


def scan_inbox() -> list[str]:
    """Register new inbox videos. Returns hashes of videos that still need processing."""
    pending = []
    for p in sorted(INBOX.iterdir()):
        if p.suffix.lower() not in VIDEO_EXTS or p.name.endswith(".part"):
            continue
        h = file_hash(p)
        row = db.video_known(h)
        if row is None:
            src = p.with_suffix(".source.json")
            meta = json.loads(src.read_text(encoding="utf-8")) if src.exists() else {}
            db.add_video(h, str(p), meta.get("title") or p.stem, meta.get("url"))
            row = db.video_known(h)
        if row["status"] in ("new", "transcribed", "failed"):
            pending.append(h)
    return pending


def extract_audio(video: Path, h: str) -> Path:
    out = WORK / h / "audio16k.wav"
    out.parent.mkdir(parents=True, exist_ok=True)
    if not out.exists():
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(video), "-vn", "-ac", "1", "-ar", "16000",
                        "-c:a", "pcm_s16le", str(out)], check=True)
    return out
