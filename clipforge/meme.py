"""AI meme adder: a dedicated Claude pass writes one meme per short, and it is placed so it plays inside the first ~6 s."""
from __future__ import annotations

from pathlib import Path

from .llm import structured
from .schemas import MemeSpec, Script

PROMPT = (Path(__file__).parent / "prompts" / "meme.md").read_text(encoding="utf-8")
MULTI = {"nope_yep": 2, "expectation_reality": 2, "two_buttons": 2, "galaxy_brain": 3, "starter_pack": 4}


def write(script: Script, short_id: str) -> MemeSpec:
    from .accounts import current

    try:
        persona = current().get("persona") or ""
    except Exception:  # noqa: BLE001
        persona = ""
    beats = "\n".join(f"{b.kind.upper()}: {b.text}" for b in script.beats)
    user = f"Channel persona:\n{persona}\n\nScript title: {script.title}\n\n{beats}"
    recent = _recent_formats(short_id)
    if recent:
        user += ("\n\nFormats used on the last few shorts: " + ", ".join(recent) +
                 ". Pick a different format unless one of those is clearly the funniest fit for THIS joke.")
    spec = structured(PROMPT, user, MemeSpec, stage="meme", ref=short_id, effort="medium", max_tokens=3000)
    need = MULTI.get(spec.format, 0)
    if need and len(spec.panels) < need:  # malformed: fall back to a single-image format with the same joke
        spec.format, spec.emoji = "pov", spec.emoji or (spec.panels[0].emoji if spec.panels else "😳")
        spec.caption_top = spec.caption_top or "POV:"
    spec.panels = spec.panels[:4]
    return spec


def _recent_formats(exclude: str, n: int = 5) -> list[str]:
    import json

    from .config import WORK

    files = sorted((p for p in (WORK / "shorts").glob("*/meme.json") if p.parent.name != exclude),
                   key=lambda p: p.stat().st_mtime, reverse=True)[:n]
    out = []
    for p in files:
        try:
            out.append(json.loads(p.read_text(encoding="utf-8"))["format"])
        except Exception:  # noqa: BLE001
            pass
    return out


def props(spec: MemeSpec) -> dict:
    return {"format": spec.format, "top": spec.caption_top, "bottom": spec.caption_bottom, "emoji": spec.emoji,
            "panels": [p.model_dump() for p in spec.panels]}


def insert(doc: dict, meme_props: dict, fps: int = 30, latest_end_s: float = 6.0) -> dict:
    """Make the meme the second beat of the video: starts right after the hook's first shot (by ~1.2-3.5 s),
    holds long enough to read (2.2-3 s), and ends by `latest_end_s`. Shots it covers are trimmed or dropped."""
    shots = doc["shots"]
    if any(s["type"] == "meme" and s["start_frame"] < latest_end_s * fps for s in shots):
        return doc
    cand = [i for i, s in enumerate(shots) if i > 0 and int(1.0 * fps) <= s["start_frame"] <= int(3.5 * fps)]
    if not cand:  # hook shot runs long: cut into it at 1.5 s
        i0 = 0
        start = int(1.5 * fps)
    else:
        i0, start = cand[0], shots[cand[0]]["start_frame"]
    hold = int((2.9 if meme_props["format"] in MULTI else 2.4) * fps)
    end = min(start + hold, int(latest_end_s * fps), doc["duration_frames"])
    end = max(end, start + int(2.0 * fps))
    meme_shot = {"id": "meme", "type": "meme", "beat": "hook", "start_frame": start, "end_frame": end, "motion": "pop",
                 "props": meme_props | {"anim_start_frame": start}}
    out = []
    for s in shots:
        if s["end_frame"] <= start or s["start_frame"] >= end:
            out.append(s)
        elif s["start_frame"] < start:  # shot that runs into the meme: cut it at the meme's start
            out.append(s | {"end_frame": start})
        elif s["end_frame"] > end:  # shot that runs past the meme: start it after
            out.append(s | {"start_frame": end})
    out.append(meme_shot)
    out.sort(key=lambda s: s["start_frame"])
    out = [s for s in out if s["end_frame"] - s["start_frame"] >= 6]  # drop slivers
    for a, b in zip(out, out[1:]):
        a["end_frame"] = b["start_frame"]
    out[-1]["end_frame"] = doc["duration_frames"]
    for k, s in enumerate(out):
        s["id"] = f"s{k:02d}"
    doc["shots"] = out
    return doc
