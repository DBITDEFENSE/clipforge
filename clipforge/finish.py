"""FFmpeg finishing: music bed ducked under voice, two-pass loudness normalisation, final mux."""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
from pathlib import Path

from .config import MUSIC, settings

AUDIO_EXTS = {".mp3", ".wav", ".m4a", ".flac", ".ogg"}


def pick_music(mood: str, seed: str) -> Path | None:
    """assets/music/<mood>__anything.mp3 (or <mood>-...). Falls back to any track; None if the folder is empty."""
    tracks = sorted(p for p in MUSIC.iterdir() if p.suffix.lower() in AUDIO_EXTS) if MUSIC.exists() else []
    if not tracks:
        return None
    tagged = [p for p in tracks if re.match(rf"^{re.escape(mood)}[_\- ]", p.name, re.I)] or tracks
    return tagged[int(hashlib.md5(seed.encode()).hexdigest(), 16) % len(tagged)]


def probe_duration(path: Path) -> float:
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(path)],
                       capture_output=True, text=True, check=True)
    return float(json.loads(r.stdout)["format"]["duration"])


# Broadcast-style voice chain: tame peaks so loudnorm can reach -14 LUFS without hitting the true-peak ceiling.
VO_CHAIN = "aresample=48000,highpass=f=70,acompressor=threshold=-20dB:ratio=3:attack=5:release=90:makeup=2,alimiter=limit=0.89:level=false"


def _mix_graph(has_music: bool, dur: float) -> str:
    gain = settings()["finish"]["music_gain_db"]
    if not has_music:
        return f"[0:a]{VO_CHAIN}[mix]"
    return (
        f"[1:a]aloop=loop=-1:size=2000000000,atrim=0:{dur:.3f},aresample=48000,volume={gain}dB,"
        f"afade=t=in:d=0.4,afade=t=out:st={max(dur - 1.2, 0):.3f}:d=1.2[m];"
        f"[0:a]{VO_CHAIN},asplit=2[vo][sc];"
        "[m][sc]sidechaincompress=threshold=0.02:ratio=10:attack=15:release=350[duck];"
        "[vo][duck]amix=inputs=2:duration=first:normalize=0[mix]"
    )


def _master(inputs: list[str], graph: str, gain_db: float, tp: float) -> str:
    # gain, then a true-peak-ish limiter on 4x oversampled audio, back to 48 kHz
    lim = 10 ** ((tp - 0.3) / 20)
    return f"{graph};[mix]volume={gain_db:.2f}dB,aresample=192000,alimiter=limit={lim:.4f}:attack=2:release=60:level=false,aresample=48000[out]"


def finish(render_mp4: Path, out_mp4: Path, music: Path | None) -> dict:
    """Mix, then hit target LUFS: measure -> exact gain + limiter -> re-measure -> one correction if needed."""
    cfg = settings()["finish"]
    target, tp = cfg["target_lufs"], cfg["true_peak"]
    dur = probe_duration(render_mp4)
    inputs = ["-i", str(render_mp4)] + (["-i", str(music)] if music else [])
    graph = _mix_graph(music is not None, dur)

    def loudness_of(fc: str) -> float:
        r = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-y", *inputs, "-filter_complex", f"{fc};[out]ebur128[o2]",
                            "-map", "[o2]", "-f", "null", "-"], capture_output=True, text=True, encoding="utf-8", errors="replace")
        m = re.findall(r"I:\s+(-?[\d.]+) LUFS", r.stderr)
        if r.returncode != 0 or not m:
            raise RuntimeError(f"loudness measurement failed:\n{r.stderr[-1200:]}")
        return float(m[-1])

    raw = loudness_of(f"{graph};[mix]anull[out]")
    gain = target - raw
    got = loudness_of(_master(inputs, graph, gain, tp))
    if abs(got - target) > 0.4:  # limiter ate some loudness; push the gain by the shortfall once
        gain += target - got
        got = loudness_of(_master(inputs, graph, gain, tp))

    subprocess.run(["ffmpeg", "-hide_banner", "-v", "error", "-y", *inputs, "-filter_complex", _master(inputs, graph, gain, tp),
                    "-map", "0:v", "-map", "[out]", "-c:v", "copy", "-c:a", "aac", "-b:a", "256k", "-ar", "48000",
                    "-movflags", "+faststart", str(out_mp4)], check=True)
    return {"music": music.name if music else None, "mix_lufs": raw, "gain_db": round(gain, 2), "predicted_lufs": got}
