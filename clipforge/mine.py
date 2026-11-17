"""Story mining: transcripts -> stories (merged across videos) -> ranked picks for N days."""
from __future__ import annotations

import json
from pathlib import Path

from . import db
from .config import WORK, settings
from .llm import structured
from .schemas import Story, StoryList
from .transcribe import transcript_for_prompt

PROMPT = (Path(__file__).parent / "prompts" / "mine.md").read_text(encoding="utf-8")


def score(story: Story) -> float:
    s = story.scores
    base = 0.30 * s.hook + 0.25 * s.curiosity + 0.20 * s.clarity + 0.25 * s.niche_fit
    return round(base * settings()["plan"]["niche_weights"].get(story.category, 0.3), 3)


def mine(batch_id: str, videos: list[dict]) -> list[Story]:
    """videos: [{hash, title, transcript}] -> stories (also saved to work/<batch>/stories.json)."""
    need = settings()["plan"]["per_day"] * settings()["plan"]["days"]
    blocks = "\n\n".join(transcript_for_prompt(v["hash"], v["title"], v["transcript"]) for v in videos)
    user = (f"Transcripts ({len(videos)} video(s)):\n\n{blocks}\n\n"
            f"We need at least {need} usable shorts from this batch, so be thorough, but don't pad with weak stories.")
    result = structured(PROMPT, user, StoryList, stage="mine", ref=batch_id,
                        effort=settings()["claude"]["effort_mine"], max_tokens=32000)
    out = WORK / batch_id / "stories.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(result.model_dump_json(indent=2), encoding="utf-8")
    return result.stories


def pick(batch_id: str, stories: list[Story]) -> list[tuple[str, Story, int]]:
    """Rank, de-duplicate by cluster, and spread across days. Returns [(story_id, story, day)]."""
    plan = settings()["plan"]
    need = plan["per_day"] * plan["days"]
    ranked = sorted(enumerate(stories), key=lambda t: score(t[1]), reverse=True)
    seen, picks = set(), []
    for i, st in ranked:
        sid = f"{batch_id}-{i:02d}"
        chosen = st.cluster not in seen and len(picks) < need
        day = None
        if chosen:
            seen.add(st.cluster)
            day = len(picks) % plan["days"]  # round-robin so every day gets a mix of strong stories
            picks.append((sid, st, day))
        db.save_story(sid, batch_id, json.loads(st.model_dump_json()), score(st), chosen, day)
    return picks
