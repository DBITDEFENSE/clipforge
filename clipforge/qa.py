"""Automatic QA on a finished short. Never raises for a bad video; returns a report."""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

from .config import settings


def _probe(path: Path) -> dict:
    r = subprocess.run(["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)],
                       capture_output=True, text=True, check=True)
    return json.loads(r.stdout)


def check(path: Path) -> dict:
    q, vcfg = settings()["qa"], settings()["video"]
    target, tp_max = settings()["finish"]["target_lufs"], settings()["finish"]["true_peak"]
    checks = []

    def add(name, ok, detail):
        checks.append({"name": name, "ok": bool(ok), "detail": detail})

    info = _probe(path)
    v = next((s for s in info["streams"] if s["codec_type"] == "video"), {})
    a = next((s for s in info["streams"] if s["codec_type"] == "audio"), {})
    dur = float(info["format"]["duration"])
    add("duration", q["min_duration_s"] <= dur <= q["max_duration_s"], f"{dur:.1f}s")
    add("video", v.get("codec_name") == "h264" and v.get("width") == vcfg["width"] and v.get("height") == vcfg["height"]
        and v.get("r_frame_rate") == f"{vcfg['fps']}/1", f"{v.get('codec_name')} {v.get('width')}x{v.get('height')} @ {v.get('r_frame_rate')}")
    add("audio", a.get("codec_name") == "aac" and a.get("sample_rate") == "48000", f"{a.get('codec_name')} {a.get('sample_rate')} Hz")

    r = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(path), "-vf", "blackdetect=d=0.3:pix_th=0.02", "-an", "-f", "null", "-"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    blacks = re.findall(r"black_start:([\d.]+)", r.stderr)
    add("no_black_frames", not blacks, f"black segments at {blacks}" if blacks else "none")

    r = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(path), "-af", "ebur128=peak=true", "-vn", "-f", "null", "-"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    summary = r.stderr[r.stderr.rfind("Summary:"):]
    i_m = re.search(r"I:\s+(-?[\d.]+) LUFS", summary)
    p_m = re.search(r"Peak:\s+(-?[\d.]+) dBFS", summary)
    lufs = float(i_m.group(1)) if i_m else None
    peak = float(p_m.group(1)) if p_m else None
    add("loudness", lufs is not None and abs(lufs - target) <= q["lufs_tolerance"], f"{lufs} LUFS (target {target})")
    add("no_clipping", peak is not None and peak <= tp_max + 0.5, f"true peak {peak} dBTP")

    return {"passed": all(c["ok"] for c in checks), "checks": checks}
