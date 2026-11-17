"""Get videos into inbox/ (from URLs or files), hash them, extract 16 kHz mono audio."""
from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import yt_dlp

from . import db
from .config import INBOX, VIDEO_EXTS, WORK


def download(url: str) -> Path:
    """Download a link into inbox/ (<=1080p is plenty for research input). Records the source URL."""
    opts = {
        "outtmpl": str(INBOX / "%(title).120B [%(id)s].%(ext)s"),
        "format": "bv*[height<=1080]+ba/b[height<=1080]/b",
        "format_sort": ["res:1080", "vcodec:h264", "acodec:aac"],
        "merge_output_format": "mp4",
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "js_runtimes": {"deno": {}, "node": {}},
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)
        path = Path(info.get("requested_downloads", [{}])[0].get("filepath") or ydl.prepare_filename(info))
    meta = {"url": info.get("webpage_url") or url, "title": info.get("title"), "uploader": info.get("uploader"),
            "upload_date": info.get("upload_date"), "duration": info.get("duration")}
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
