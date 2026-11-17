"""Build and validate shots.json: the single document the Remotion render consumes.

Phase 1 uses a deterministic planner (beats -> shots, snapped to words). Phase 2 swaps in
Claude-authored shot lists, validated by the same schema + checks.
"""
from __future__ import annotations

import json
from pathlib import Path

import jsonschema

from .config import brand, settings
from .schemas import Script, Word
from .timing import W, beat_word_ranges, caption_chunks, clean_caption_word, ms_to_frame, split_beat

SCHEMA = json.loads((Path(__file__).parent / "shots.schema.json").read_text(encoding="utf-8"))
MOTIONS = ["pop", "punch_in", "drift"]
CARD_TYPES = {"code", "terminal", "headline", "stat"}

# Layout (px, 1080x1920): where captions and cards live. Validated against the safe zones.
LAYOUT = {"content_top": 250, "content_bottom": 1130, "caption_top": 1170, "caption_bottom": 1440}


def _card_props(v) -> dict:
    if v.type == "code":
        return {"language": v.code_language or "code", "lines": v.code_lines or [], "highlight": v.code_highlight}
    if v.type == "terminal":
        return {"lines": v.terminal_lines or []}
    if v.type == "headline":
        return {"headline": v.headline or (v.screen_text[0] if v.screen_text else ""), "kicker": v.kicker or ""}
    if v.type == "stat":
        return {"value": v.stat_value or "", "label": v.stat_label or ""}
    return {}


def build(script: Script, words: list[Word], short_id: str, audio: str = "vo.mp3") -> dict:
    cfg = settings()["video"]
    fps = cfg["fps"]
    ws = [W(w.word, w.start_ms, w.end_ms) for w in words]
    ranges = beat_word_ranges([b.text for b in script.beats], len(ws))
    end_ms = ws[-1].end_ms + settings()["voice"]["tail_ms"]
    duration = ms_to_frame(end_ms, fps)

    # beat time spans: contiguous, beat 0 starts at 0, each next beat starts at its first word
    beat_starts = [0.0] + [ws[lo].start_ms for lo, _ in ranges[1:]]
    beat_ends = beat_starts[1:] + [end_ms]

    raw = []  # (start_ms, beat_idx, sub_idx, n_subs)
    for bi, ((lo, hi), b0, b1) in enumerate(zip(ranges, beat_starts, beat_ends)):
        starts = split_beat(ws, lo, hi, b0, b1, cfg["min_shot_ms"], cfg["max_shot_ms"], force_two=(bi == 0))
        for si, widx in enumerate(starts):
            raw.append((b0 if si == 0 else ws[widx].start_ms, bi, si, len(starts)))

    shots, card_start = [], {}
    for k, (s_ms, bi, si, n) in enumerate(raw):
        start_f = ms_to_frame(s_ms, fps)
        end_f = ms_to_frame(raw[k + 1][0], fps) if k + 1 < len(raw) else duration
        if end_f <= start_f:
            continue
        beat = script.beats[bi]
        v = beat.visual
        texts = v.screen_text or [beat.text.split(".")[0][:40]]
        if bi == 0 and si == 0:
            texts = [script.hooks[0].on_screen] + texts
        is_card = v.type in CARD_TYPES and not (n >= 3 and si == 0)  # long card beats open with a kinetic line
        if is_card:
            card_start.setdefault(bi, start_f)
            shot = {"type": v.type, "props": _card_props(v) | {"anim_start_frame": card_start[bi]}}
        else:
            shot = {"type": "kinetic", "props": {"text": texts[si % len(texts)]}}
        shot |= {
            "id": f"s{len(shots):02d}",
            "beat": beat.kind,
            "start_frame": start_f,
            "end_frame": end_f,
            "motion": "pop" if bi == 0 else MOTIONS[len(shots) % len(MOTIONS)],
        }
        shots.append(shot)
    # absorb any dropped zero-length shot so the track stays contiguous
    shots[0]["start_frame"] = 0
    for a, b in zip(shots, shots[1:]):
        a["end_frame"] = b["start_frame"]
    shots[-1]["end_frame"] = duration

    return base_doc(script, ws, short_id, duration, shots, audio)


def captions_for(ws: list[W], duration: int, fps: int) -> list[dict]:
    captions = []
    chunks = caption_chunks(ws)
    for ci, idxs in enumerate(chunks):
        c_start = ms_to_frame(ws[idxs[0]].start_ms, fps)
        nxt = ms_to_frame(ws[chunks[ci + 1][0]].start_ms, fps) if ci + 1 < len(chunks) else duration
        own_end = ms_to_frame(ws[idxs[-1]].end_ms, fps) + 6
        c_end = min(nxt, max(own_end, c_start + 1)) if nxt - own_end > 12 else nxt
        cw = []
        for j, wi in enumerate(idxs):
            w_start = ms_to_frame(ws[wi].start_ms, fps) if j else c_start
            w_end = ms_to_frame(ws[idxs[j + 1]].start_ms, fps) if j + 1 < len(idxs) else c_end
            cw.append({"text": clean_caption_word(ws[wi].word), "start_frame": w_start, "end_frame": max(w_end, w_start + 1)})
        captions.append({"start_frame": c_start, "end_frame": max(c_end, c_start + 1), "words": cw})
    return captions


def base_doc(script: Script, ws: list[W], short_id: str, duration: int, shots: list[dict], audio: str = "vo.mp3") -> dict:
    cfg = settings()["video"]
    return {
        "version": 1,
        "short_id": short_id,
        "title": script.title,
        "fps": cfg["fps"],
        "width": cfg["width"],
        "height": cfg["height"],
        "duration_frames": duration,
        "audio": audio,
        "layout": LAYOUT,
        "brand": brand(),
        "shots": shots,
        "captions": captions_for(ws, duration, cfg["fps"]),
    }


def validate(doc: dict) -> None:
    """Schema + semantic checks. Raises ValueError with every problem found."""
    jsonschema.validate(doc, SCHEMA)
    errs = []
    shots, dur = doc["shots"], doc["duration_frames"]
    if shots[0]["start_frame"] != 0:
        errs.append("first shot must start at frame 0")
    if shots[-1]["end_frame"] != dur:
        errs.append(f"last shot ends at {shots[-1]['end_frame']}, duration is {dur}")
    for a, b in zip(shots, shots[1:]):
        if a["end_frame"] != b["start_frame"]:
            errs.append(f"gap/overlap between {a['id']} (end {a['end_frame']}) and {b['id']} (start {b['start_frame']})")
    for s in shots:
        if s["end_frame"] <= s["start_frame"]:
            errs.append(f"{s['id']} has non-positive length")
    prev_end = 0
    for i, c in enumerate(doc["captions"]):
        if c["start_frame"] < prev_end:
            errs.append(f"caption {i} overlaps previous")
        if c["end_frame"] > dur:
            errs.append(f"caption {i} runs past the end")
        if not 1 <= len(c["words"]) <= 3:
            errs.append(f"caption {i} has {len(c['words'])} words")
        prev_end = c["end_frame"]
    h, lay, vc = doc["height"], doc["layout"], settings()["video"]
    top_px, bottom_px = h * vc["safe_top"], h * (1 - vc["safe_bottom"])
    for k in ("content_top", "caption_top"):
        if lay[k] < top_px:
            errs.append(f"{k}={lay[k]} is inside the top UI zone (<{top_px:.0f}px)")
    for k in ("content_bottom", "caption_bottom"):
        if lay[k] > bottom_px:
            errs.append(f"{k}={lay[k]} is inside the bottom UI zone (>{bottom_px:.0f}px)")
    if errs:
        raise ValueError("shots.json invalid:\n  " + "\n  ".join(errs))
