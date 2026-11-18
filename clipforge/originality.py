"""Originality check (never blocks): how much of the script's wording also appears verbatim in the source transcripts."""
from __future__ import annotations

import json
import re

from . import db
from .config import WORK

N = 7  # a shared run of 7+ words is almost never coincidence


def _words(t: str) -> list[str]:
    return re.findall(r"[a-z0-9']+", t.lower())


def check(spoken: str, source_ids: list[str]) -> dict:
    src = []
    for vid in source_ids:
        p = WORK / vid / "transcript.json"
        if p.exists():
            tr = json.loads(p.read_text(encoding="utf-8"))
            src += _words(" ".join(seg.get("text", "") for seg in tr.get("segments", [])))
    grams = {tuple(src[i:i + N]) for i in range(len(src) - N + 1)}
    w = _words(spoken)
    hit = [False] * len(w)
    runs = []
    for i in range(len(w) - N + 1):
        if tuple(w[i:i + N]) in grams:
            for k in range(i, i + N):
                hit[k] = True
    i = 0
    while i < len(w):  # collect the copied stretches for the report
        if hit[i]:
            j = i
            while j < len(w) and hit[j]:
                j += 1
            runs.append(" ".join(w[i:j]))
            i = j
        else:
            i += 1
    share = sum(hit) / len(w) if w else 0.0
    return {"copied_share": round(share, 3), "copied_runs": runs[:5], "ok": share < 0.08 and not any(len(r.split()) >= 12 for r in runs),
            "checked_against": len(source_ids)}


def for_story(spoken: str, story) -> dict:
    return check(spoken, sorted({s.video_id for s in story.sources}))
