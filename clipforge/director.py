"""Claude-authored shot lists. Claude picks shot boundaries (as word indices), types and props;
Python turns them into frames, repairs pacing, fetches B-roll, and validates. Any failure -> caller falls back."""
from __future__ import annotations

from pathlib import Path

from . import broll, sfx
from .config import settings
from .llm import structured
from .schemas import DirectedShot, Script, ShotPlan, Word
from .shots import CARD_TYPES, base_doc, validate
from .timing import W, beat_word_ranges, ms_to_frame, split_beat

PROMPT = (Path(__file__).parent / "prompts" / "direct.md").read_text(encoding="utf-8")
ALL_CARDS = CARD_TYPES | {"diagram", "cve", "reaction", "popups"}
MOTIONS = ["pop", "punch_in", "drift"]


def direct(script: Script, words: list[Word], short_id: str) -> ShotPlan:
    listing = "\n".join(f"{i}: {w.word}  ({w.start_ms / 1000:.2f}s)" for i, w in enumerate(words))
    ranges = beat_word_ranges([b.text for b in script.beats], len(words))
    beats = "\n".join(f"- {b.kind} (words {lo}-{hi - 1}), planned visual: {b.visual.model_dump_json(exclude_none=True)}"
                      for b, (lo, hi) in zip(script.beats, ranges))
    user = (f"Title: {script.title}\nHook on-screen text options: {[h.on_screen for h in script.hooks]}\n\n"
            f"Beats:\n{beats}\n\nNarration words (index: word (start time)):\n{listing}\n\n"
            f"Total length: {words[-1].end_ms / 1000:.1f}s")
    return structured(PROMPT, user, ShotPlan, stage="direct", ref=short_id, effort="high", max_tokens=16000)


def _props(s: DirectedShot) -> dict:
    t = s.type
    if t == "kinetic":
        return {"text": s.text}
    if t == "headline":
        return {"headline": s.text, "kicker": s.kicker}
    if t == "stat":
        return {"value": s.value, "label": s.label}
    if t == "code":
        return {"language": s.code_language or "code", "lines": s.lines, "highlight": s.highlight or None}
    if t == "terminal":
        return {"lines": s.lines}
    if t == "diagram":
        return {"nodes": s.lines[:4], "label": s.label, "danger": s.highlight if s.highlight >= 0 else None}
    if t == "cve":
        sev = s.kicker.upper() if s.kicker.upper() in {"LOW", "MEDIUM", "HIGH", "CRITICAL"} else ""
        return {"cve_id": s.value, "cvss": s.score if s.score > 0 else None, "severity": sev, "product": s.label}
    if t == "reaction":
        return {"emoji": s.emoji.strip(), "text": s.text, "kicker": s.kicker}
    if t == "popups":
        return {"lines": [m for m in s.lines if m.strip()][:5], "title": s.kicker or "ALERT"}
    return {}


def _usable(s: DirectedShot) -> bool:
    p = _props(s)
    return {
        "kinetic": bool(p.get("text")), "headline": bool(p.get("headline")), "stat": bool(p.get("value")),
        "code": bool(p.get("lines")), "terminal": bool(p.get("lines")), "diagram": len(p.get("nodes", [])) >= 2,
        "cve": bool(p.get("cve_id")), "broll": bool(s.broll_query),
        "reaction": bool(p.get("emoji")), "popups": bool(p.get("lines")),
    }[s.type]


def to_doc(plan: ShotPlan, script: Script, words: list[Word], short_id: str, workdir: Path) -> tuple[dict, list[str]]:
    cfg, fps = settings()["video"], settings()["video"]["fps"]
    ws = [W(w.word, w.start_ms, w.end_ms) for w in words]
    n = len(ws)
    notes: list[str] = []
    end_ms = ws[-1].end_ms + settings()["voice"]["tail_ms"]
    duration = ms_to_frame(end_ms, fps)
    ranges = beat_word_ranges([b.text for b in script.beats], n)
    beat_of = lambda wi: next(script.beats[i].kind for i, (lo, hi) in enumerate(ranges) if lo <= wi < hi)  # noqa: E731

    # 1. clean: keep usable shots, valid increasing word indices, first at 0
    picked: list[DirectedShot] = []
    for s in sorted(plan.shots, key=lambda s: s.start_word):
        if not 0 <= s.start_word < n or not _usable(s):
            notes.append(f"dropped unusable {s.type} at word {s.start_word}")
            continue
        if picked and s.start_word <= picked[-1].start_word:
            continue
        picked.append(s)
    if len(picked) < 2:
        raise ValueError("director returned fewer than 2 usable shots")
    picked[0].start_word = 0

    def start_ms(wi: int) -> float:
        return 0.0 if wi == 0 else ws[wi].start_ms

    # 2. drop shots shorter than ~0.7s (except the hook's second shot), then split anything over the max
    spans = []
    for k, s in enumerate(picked):
        nxt = picked[k + 1].start_word if k + 1 < len(picked) else n
        spans.append([s, s.start_word, nxt])
    span_ms = lambda sp: (start_ms(sp[2]) if sp[2] < n else end_ms) - start_ms(sp[1])  # noqa: E731
    merged = list(spans)
    k = 0
    while k < len(merged):
        sp = merged[k]
        hook_fast = k == 1 and start_ms(sp[1]) <= 3000  # the hook's quick second shot is allowed to be short
        if span_ms(sp) < 700 and not hook_fast and len(merged) > 2:
            if k + 1 < len(merged):  # too short: keep this shot's content, absorb the next shot's time
                notes.append(f"merged a {span_ms(sp):.0f}ms {sp[0].type} shot with the next {merged[k + 1][0].type}")
                sp[2] = merged.pop(k + 1)[2]
                continue
            notes.append(f"merged a {span_ms(sp):.0f}ms {sp[0].type} shot into the previous one")
            merged[k - 1][2] = sp[2]
            merged.pop(k)
            continue
        k += 1
    final: list[tuple[DirectedShot, int, int]] = []
    for idx, (s, lo, hi) in enumerate(merged):
        a, b = start_ms(lo), (start_ms(hi) if hi < n else end_ms)
        starts = split_beat(ws, lo, hi, a, b, cfg["min_shot_ms"], cfg["max_shot_ms"], force_two=(idx == 0 and len(merged) > 1 and merged[1][1] and start_ms(merged[1][1]) > 3000))
        for j, wi in enumerate(starts):
            final.append((s, wi, j))
        if len(starts) > 1:
            notes.append(f"split a {(b - a) / 1000:.1f}s {s.type} shot into {len(starts)}")

    # 3. frames, props, card continuity, B-roll
    shots, card_start, broll_n = [], {}, 0
    for k, (s, wi, sub) in enumerate(final):
        sf = ms_to_frame(start_ms(wi), fps)
        ef = ms_to_frame(start_ms(final[k + 1][1]), fps) if k + 1 < len(final) else duration
        if ef <= sf:
            continue
        typ, props = s.type, _props(s)
        if typ == "broll":
            src = broll.fetch(s.broll_query, workdir / f"broll_{broll_n}.mp4")
            if src:
                props = {"src": src.name, "text": s.text, "credit": broll.last_credit()}
                broll_n += 1
            else:
                typ, props = "kinetic", {"text": s.text or s.broll_query}
                notes.append(f"no B-roll for '{s.broll_query}', used kinetic")
        if typ in ALL_CARDS:
            key = s.card_key or f"{typ}-{id(s)}"
            card_start.setdefault(key, sf)
            props["anim_start_frame"] = card_start[key]
        if s.lower_title and sub == 0:
            props["lower"] = {"title": s.lower_title, "sub": s.lower_sub or ""}
        if sub == 0:  # effects, stickers and sound hit on the shot's first cut only
            if s.fx != "none":
                props["fx"] = s.fx
                if s.fx == "alarm" and s.kicker and typ not in {"headline", "cve", "popups", "reaction"}:
                    props["alert_text"] = s.kicker
            if s.emoji.strip() and typ != "reaction":
                props["emoji"] = s.emoji.strip()
            src = sfx.file_for(s.sfx) if s.sfx != "none" else None
            if src:
                props["sfx_src"], props["sfx_volume"] = src, sfx.VOLUME.get(s.sfx, 0.4)
        motion = s.motion if sub == 0 else MOTIONS[(MOTIONS.index(s.motion) + sub) % 3 if s.motion in MOTIONS else sub % 3]
        shots.append({"id": f"s{len(shots):02d}", "type": typ, "beat": beat_of(wi), "start_frame": sf, "end_frame": ef,
                      "motion": motion, "props": props})
    shots[0]["start_frame"] = 0
    for a, b in zip(shots, shots[1:]):
        a["end_frame"] = b["start_frame"]
    shots[-1]["end_frame"] = duration

    doc = base_doc(script, ws, short_id, duration, shots)
    doc["planner"] = "claude"
    validate(doc)
    return doc, notes
