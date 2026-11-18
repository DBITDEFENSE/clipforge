"""Script writing: story -> Script (hooks, beats with visual cues, post copy)."""
from __future__ import annotations

import json
from pathlib import Path

from .config import WORK, settings
from .llm import structured
from .schemas import Review, Script, Story

PROMPT_TMPL = (Path(__file__).parent / "prompts" / "write.md").read_text(encoding="utf-8")


def _excerpts(story: Story, window_s: int = 120) -> str:
    """Transcript text around each cited timestamp, so the writer can check facts in context."""
    parts = []
    for ref in story.sources:
        tr_path = WORK / ref.video_id / "transcript.json"
        if not tr_path.exists():
            continue
        try:
            mm, ss = ref.timestamp.split(":")[-2:]
            t = int(mm) * 60 + int(ss)
        except ValueError:
            t = 0
        tr = json.loads(tr_path.read_text(encoding="utf-8"))
        text = " ".join(s["text"] for s in tr["segments"] if t - window_s <= (s["start"] or 0) <= t + window_s)
        parts.append(f"[source {ref.video_id} around {ref.timestamp}]\n{text}")
    return "\n\n".join(parts) or "(no excerpts available)"


def problems(script: Script) -> list[str]:
    cfg = settings()["script"]
    errs = []
    n = script.word_count()
    if not cfg["min_words"] <= n <= cfg["max_words"]:
        errs.append(f"spoken length is {n} words; it must be {cfg['min_words']}-{cfg['max_words']}")
    kinds = [b.kind for b in script.beats]
    if not kinds or kinds[0] != "hook":
        errs.append("the first beat must be the hook")
    if kinds and kinds[-1] != "punch":
        errs.append("the last beat must be the punch")
    if "how" not in kinds:
        errs.append("missing the 'how' technical beat")
    if len(script.hooks) != 3:
        errs.append(f"need exactly 3 hooks, got {len(script.hooks)}")
    if script.beats and len(script.beats[0].text.split()) > 16:
        errs.append("hook beat is too long to land in 2 seconds")
    return errs


def write(story_id: str, story: Story) -> Script:
    cfg = settings()
    system = PROMPT_TMPL.replace("{min_words}", str(cfg["script"]["min_words"])).replace("{max_words}", str(cfg["script"]["max_words"]))
    user = (f"Story:\n{story.model_dump_json(indent=2)}\n\n"
            f"Source excerpts (research only; do not reuse wording):\n{_excerpts(story)}")
    script = structured(system, user, Script, stage="write", ref=story_id, effort=cfg["claude"]["effort_write"])
    errs = problems(script)
    if errs:
        fix = user + "\n\nYour previous draft had these problems; fix all of them:\n- " + "\n- ".join(errs) + \
              f"\n\nPrevious draft:\n{script.model_dump_json()}"
        script = structured(system, fix, Script, stage="write-fix", ref=story_id, effort=cfg["claude"]["effort_write"])
        errs = problems(script)
        if any("first beat" in e or "3 hooks" in e for e in errs):
            raise RuntimeError(f"script still invalid after a fix pass: {errs}")
    script.hooks[0].spoken = script.beats[0].text  # the spoken hook must be the one we narrate
    return script


REVIEW_TMPL = (Path(__file__).parent / "prompts" / "review.md").read_text(encoding="utf-8")


def review(story_id: str, story: Story, script: Script, notes: str = "") -> tuple[Script, list[str]]:
    """Separate editor pass: facts vs sources, 2-second hook, pacing, clarity. Keeps the draft if the revision breaks rules.
    `notes` = the host's own feedback; applied first, as long as the facts and rules still hold."""
    cfg = settings()
    system = REVIEW_TMPL.replace("{min_words}", str(cfg["script"]["min_words"])).replace("{max_words}", str(cfg["script"]["max_words"]))
    user = (f"Story facts:\n{story.model_dump_json(indent=2)}\n\nSource excerpts:\n{_excerpts(story)}\n\n"
            f"Draft script:\n{script.model_dump_json(indent=2)}")
    if notes.strip():
        user += ("\n\nNOTES FROM THE HOST (highest priority; apply them fully, rewriting as much as needed, "
                 f"but never break the facts or the rules):\n{notes.strip()}")
    result = structured(system, user, Review, stage="review", ref=story_id, effort=cfg["claude"]["effort_write"])
    revised = result.revised
    if problems(revised) and not problems(script):
        return script, result.issues + ["(revision broke structure/length rules; kept the draft)"]
    revised.hooks[0].spoken = revised.beats[0].text
    return revised, result.issues


def script_markdown(script: Script, story: Story) -> str:
    lines = [f"# {script.title}", "", f"**Topic:** {story.topic}  ", f"**Angle:** {story.angle}", ""]
    for b in script.beats:
        lines += [f"**{b.kind.upper()}** _(visual: {b.visual.type})_  ", b.text, ""]
    lines += [f"_{script.word_count()} words_"]
    return "\n".join(lines)
