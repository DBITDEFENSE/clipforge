"""Real clips from the source video, cut vertical and played muted under the narration, optionally restyled on the GPU.

Per channel (stored in the account's visuals JSON):
  footage            off | clips | restyled
  clip_style         restyle prompt ('' = the channel's default look)
  restyle_strength   0.2-0.8: how far Wan moves away from the source frames
  max_source_clips   cap per short
  max_clip_seconds   longest single clip (2-10 s)

Flow: moments(story) lists ~4-8 s windows of the source transcript around where the story is discussed, contact_sheet()
shows the director one frame per window, the director picks windows for `clip` shots, cut() renders each one as a
vertical clip (source frame centred in the layout's content zone on a blurred fill), with Wan 2.1 video-to-video in
between when restyled. Clips are kept short (<= MAX_CLIP_S): they back up the narration, they don't replace the video.
Every clip is credited on screen and in the post copy.
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
from pathlib import Path

from .config import DATA, WORK

CACHE = DATA / "footage_cache"
MODES = {
    "off": "No source footage: original graphics, memes and AI B-roll only",
    "clips": "Clips from the source video (muted under your narration, credited)",
    "restyled": "Source clips restyled on your GPU (Wan 2.1 video-to-video, ~1 min per clip; needs the Wan 2.1 1.3B model)",
}
STYLES = {
    "cyber-cowboy": "neo-western cyberpunk comic book illustration, cel shaded, bold ink outlines, dusty amber and neon teal palette",
    "default": "stylized animated illustration, cel shaded, bold ink outlines, rich saturated colors",
}
DEFAULTS = {"footage": "clips", "clip_style": "", "restyle_strength": 0.5, "max_source_clips": 4, "max_clip_seconds": 5.0}
CLIP_S_RANGE = (2.0, 10.0)
MAX_CLIPS = 10
V_W, V_H = 1080, 1920
FG_MAX_H = 810  # the source frame is at most a 4:3 centre crop, centred in the layout's content zone
MAX_CLIP_S = 5.0  # default longest single clip (per channel: max_clip_seconds); the rest of a longer beat falls back to a graphic
R_W, R_H, R_FPS, R_MAX = 832, 480, 16, 81  # Wan 2.1 1.3B landscape input; 81 frames = ~5 s


def config(account: str | None = None) -> dict:
    from . import accounts

    acc = accounts.get(account) if account else accounts.current()
    vis = acc.get("visuals") or {}
    c = DEFAULTS | {k: vis[k] for k in DEFAULTS if vis.get(k) is not None}
    if c["footage"] not in MODES:
        c["footage"] = DEFAULTS["footage"]
    c["max_clip_seconds"] = max(CLIP_S_RANGE[0], min(CLIP_S_RANGE[1], float(c["max_clip_seconds"])))
    c["style_effective"] = c["clip_style"] or STYLES.get(acc["id"], STYLES["default"])
    return c


# ---------- picking moments ----------
def parse_ts(ts: str) -> float | None:
    parts = [p for p in re.split(r"[:.]", (ts or "").strip()) if p.isdigit()]
    if not parts or len(parts) > 3:
        return None
    secs = 0.0
    for p in parts:
        secs = secs * 60 + int(p)
    return secs


def _segments(video_hash: str) -> list[dict]:
    f = WORK / video_hash / "transcript.json"
    return json.loads(f.read_text(encoding="utf-8")).get("segments", []) if f.exists() else []


def chunk(segments: list[dict], lo: float, hi: float, min_s: float = 3.5, max_s: float = 8.0) -> list[tuple[float, float, str]]:
    """Merge transcript segments inside [lo, hi] into ~min_s..max_s windows."""
    out, cur = [], None
    for s in segments:
        if s.get("start") is None or s.get("end") is None:  # WhisperX leaves the odd segment unaligned
            continue
        if s["end"] < lo or s["start"] > hi:
            continue
        if cur and (s["end"] - cur[0] > max_s or s["start"] - cur[1] > 2.0):
            out.append(cur)
            cur = None
        cur = [s["start"], s["end"], s["text"].strip()] if cur is None else [cur[0], s["end"], cur[2] + " " + s["text"].strip()]
        if cur[1] - cur[0] >= min_s:
            out.append(cur)
            cur = None
    if cur and cur[1] - cur[0] >= 1.5:
        out.append(cur)
    return [(a, b, t) for a, b, t in out]


def moments(story, max_n: int = 30, before: float = 20.0, after: float = 180.0) -> list[dict]:
    """Candidate clip windows around where the story is discussed in each source video."""
    from . import db

    found: list[dict] = []
    for ref in story.sources:
        t = parse_ts(ref.timestamp)
        row = db.video_known(ref.video_id)
        if t is None or not row or not Path(row["path"]).exists():
            continue
        for a, b, text in chunk(_segments(ref.video_id), max(0.0, t - before), t + after):
            if not any(m["hash"] == ref.video_id and abs(m["start"] - a) < 1 for m in found):
                found.append({"hash": ref.video_id, "start": round(a, 2), "end": round(b, 2), "text": text[:220]})
    if len(found) > max_n:  # spread evenly instead of keeping only the first minutes
        step = len(found) / max_n
        found = [found[int(i * step)] for i in range(max_n)]
    for i, m in enumerate(found):
        m["id"] = f"C{i + 1}"
    return found


def listing(ms: list[dict]) -> str:
    return "\n".join(f"{m['id']}  {int(m['start'] // 60)}:{m['start'] % 60:04.1f}-{int(m['end'] // 60)}:{m['end'] % 60:04.1f}  "
                     f"\"{m['text']}\"" for m in ms)


def _src(video_hash: str) -> dict:
    from . import db

    row = db.video_known(video_hash)
    path = Path(row["path"])
    meta_f = path.with_suffix(".source.json")
    meta = json.loads(meta_f.read_text(encoding="utf-8")) if meta_f.exists() else {}
    return {"path": path, "title": row["title"], "url": row["source_url"] or meta.get("url") or "",
            "uploader": meta.get("uploader") or ""}


def credit(video_hash: str) -> dict:
    s = _src(video_hash)
    return {"label": s["uploader"] or s["title"][:40], "title": s["title"], "url": s["url"]}


def contact_sheet(ms: list[dict], dst: Path, cols: int = 5) -> Path | None:
    """One labelled frame per moment so the director can see what's on screen (talking head vs. demo)."""
    if not ms:
        return None
    from PIL import Image, ImageDraw, ImageFont

    tw, th = 320, 180
    rows = (len(ms) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * tw, rows * th), (12, 12, 16))
    draw = ImageDraw.Draw(sheet)
    try:
        font = ImageFont.truetype("arialbd.ttf", 26)
    except OSError:
        font = ImageFont.load_default()
    for i, m in enumerate(ms):
        src = _src(m["hash"])["path"]
        t = m["start"] + min(1.5, (m["end"] - m["start"]) / 2)
        p = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t:.2f}", "-i", str(src), "-frames:v", "1", "-vf",
                            f"scale={tw}:{th}:force_original_aspect_ratio=decrease,pad={tw}:{th}:-1:-1",
                            "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True)
        x, y = (i % cols) * tw, (i // cols) * th
        if p.returncode == 0 and len(p.stdout) == tw * th * 3:
            sheet.paste(Image.frombytes("RGB", (tw, th), p.stdout), (x, y))
        draw.rectangle([x, y, x + 64, y + 34], fill=(0, 0, 0))
        draw.text((x + 6, y + 3), m["id"], fill=(255, 220, 60), font=font)
    sheet.save(dst, quality=82)
    return dst


# ---------- cutting ----------
def clip_seconds(m: dict, want: float, cap: float = MAX_CLIP_S) -> float:
    """How long a clip of moment `m` may run: what the shot wants, capped at `cap` and just past the moment's end."""
    return max(0.8, min(float(want), float(cap), max(2.0, m["end"] - m["start"] + 0.6)))


def frame_box(layout: dict | None) -> dict:
    """Where the clip sits for a shots.json layout: canvas height (the gameplay panel stays visible below it) and the
    source frame's y / height inside the content zone, so the frame never runs into the captions."""
    lay = layout or {"content_top": 250, "content_bottom": 1130}
    canvas = int(lay.get("gameplay_top") or V_H)
    zone_top, zone_h = int(lay["content_top"]), int(lay["content_bottom"]) - int(lay["content_top"])
    fg_h = min(FG_MAX_H, zone_h) // 2 * 2
    return {"canvas_h": canvas, "fg_y": zone_top + (zone_h - fg_h) // 2, "fg_h": fg_h}


def vertical_filter(box: dict, seconds: float) -> str:
    """Blurred fill + sharp source frame; tpad clones the last frame so the file is never shorter than asked."""
    ch, fy, fh = box["canvas_h"], box["fg_y"], box["fg_h"]
    return (f"[0:v]scale={V_W}:{ch}:force_original_aspect_ratio=increase,crop={V_W}:{ch},boxblur=28:4,"
            f"eq=brightness=-0.14:saturation=0.75[bg];"
            f"[0:v]scale={V_W}:{fh}:force_original_aspect_ratio=increase,crop={V_W}:{fh}[fg];"
            f"[bg][fg]overlay=0:{fy},fps=30,tpad=stop_mode=clone:stop_duration={seconds + 1:.2f},format=yuv420p")


def _ffmpeg(args: list[str]) -> None:
    p = subprocess.run(["ffmpeg", "-y", "-v", "error", *args], capture_output=True)
    if p.returncode != 0:
        raise RuntimeError(f"ffmpeg: {p.stderr.decode(errors='replace')[-300:]}")


def restyle_frames_needed(seconds: float) -> int:
    n = int(seconds * R_FPS) + 1
    n = ((n - 1 + 3) // 4) * 4 + 1  # Wan wants 4k+1 frames
    return max(17, min(R_MAX, n))


def _restyled_source(src: Path, start: float, seconds: float, prompt: str, strength: float) -> Path:
    """Landscape restyled clip (cached), at most ~5 s; the vertical step loops it if the shot runs longer."""
    import numpy as np
    from PIL import Image

    from . import videogen

    n = restyle_frames_needed(seconds)
    CACHE.mkdir(parents=True, exist_ok=True)
    key = hashlib.sha256(f"{src.name}|{start:.2f}|{n}|{prompt}|{strength:.2f}".encode()).hexdigest()[:20]
    out = CACHE / f"restyled_{key}.mp4"
    if out.exists():
        return out
    p = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{start:.2f}", "-i", str(src), "-an", "-vf",
                        f"fps={R_FPS},scale={R_W}:{R_H}:force_original_aspect_ratio=increase,crop={R_W}:{R_H}",
                        "-frames:v", str(n), "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True)
    raw = np.frombuffer(p.stdout, dtype=np.uint8)
    got = raw.size // (R_W * R_H * 3)
    if p.returncode != 0 or got < 17:
        raise RuntimeError(f"could not read source frames ({got})")
    arr = raw[: got * R_W * R_H * 3].reshape(got, R_H, R_W, 3)
    keep = ((got - 1) // 4) * 4 + 1
    frames = [Image.fromarray(f) for f in arr[:keep]]
    styled = videogen.restyle(frames, prompt, strength)
    tmp = out.with_suffix(".part.mp4")
    videogen._write_mp4(styled, tmp, R_FPS)
    tmp.replace(out)
    return out


def cut(video_hash: str, start: float, seconds: float, dst: Path, mode: str = "clips", style: str = "",
        strength: float = 0.5, layout: dict | None = None) -> dict:
    """Render a muted vertical clip of the source starting at `start`, exactly `seconds` long.
    mode 'restyled' runs Wan 2.1 v2v first (raises if that model isn't downloaded, so the caller can fall back).
    Returns {"path", "seconds", "box"}."""
    src = _src(video_hash)["path"]
    seconds = max(0.8, float(seconds))
    box = frame_box(layout)
    enc = ["-t", f"{seconds:.2f}", "-an", "-filter_complex", vertical_filter(box, seconds),
           "-c:v", "libx264", "-crf", "18", "-movflags", "+faststart", str(dst)]
    if mode == "restyled":
        from . import videogen

        if not videogen.local_ready(videogen.WAN21):
            raise RuntimeError("restyled clips need Wan 2.1 1.3B downloaded (pick it once under B-roll source)")
        styled = _restyled_source(src, start, seconds, style, strength)
        _ffmpeg(["-stream_loop", "-1", "-i", str(styled), *enc])
    else:
        _ffmpeg(["-ss", f"{start:.2f}", "-i", str(src), *enc])
    return {"path": dst, "seconds": seconds, "box": box}
