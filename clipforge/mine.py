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


GROUP_CHARS = 300_000  # ~75k tokens of transcript per mining call; bigger batches are split into parallel calls


def _groups(blocks: list[str]) -> list[list[str]]:
    groups, cur, size = [], [], 0
    for b in blocks:
        if cur and size + len(b) > GROUP_CHARS:
            groups.append(cur)
            cur, size = [], 0
        cur.append(b)
        size += len(b)
    return groups + ([cur] if cur else [])


def mine(batch_id: str, videos: list[dict], target: int | None = None) -> list[Story]:
    """videos: [{hash, title, transcript}] -> stories (also saved to work/<batch>/stories.json).
    Videos that fit together are mined in one call so the same event is merged across sources."""
    from concurrent.futures import ThreadPoolExecutor

    per_video = settings()["plan"].get("per_video", 3)
    if target:
        per_video = max(per_video, -(-target // max(1, len(videos))) + 1)
    blocks = [transcript_for_prompt(v["hash"], v["title"], v["transcript"]) for v in videos]

    def run(i: int, group: list[str]) -> list[Story]:
        need = max(per_video * len(group), 3)
        user = (f"Transcripts ({len(group)} video(s)):\n\n" + "\n\n".join(group) +
                f"\n\nWe want about {need} usable shorts from these, so be thorough, but don't pad with weak stories.")
        return structured(PROMPT, user, StoryList, stage="mine", ref=f"{batch_id}/{i}",
                          effort=settings()["claude"]["effort_mine"], max_tokens=32000).stories

    groups = _groups(blocks)
    with ThreadPoolExecutor(max_workers=settings()["claude"]["max_parallel"]) as pool:
        stories = [st for part in pool.map(run, range(len(groups)), groups) for st in part]
    out = WORK / batch_id / "stories.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(StoryList(stories=stories).model_dump_json(indent=2), encoding="utf-8")
    return stories


def pick(batch_id: str, stories: list[Story], n_videos: int = 1, target: int | None = None) -> list[tuple[str, Story, int]]:
    """Rank, de-duplicate by cluster, cap per source video, spread over posting days. Returns [(story_id, story, day)].
    Total = max(per_day * days, per_video * videos), so a big batch yields shorts from every video. With `target`, the
    total is exactly that many (when the stories exist): the per-video cap is loosened only as far as needed."""
    plan = settings()["plan"]
    per_video = plan.get("per_video", 3)
    need = target or max(plan["per_day"] * plan["days"], per_video * n_videos)
    if target and n_videos:
        per_video = max(per_video, -(-target // n_videos))
    ranked = sorted(enumerate(stories), key=lambda t: score(t[1]), reverse=True)
    seen, per_src, picks = set(), {}, []
    for i, st in ranked:
        sid = f"{batch_id}-{i:02d}"
        src = st.sources[0].video_id if st.sources else ""
        chosen = st.cluster not in seen and len(picks) < need and (n_videos == 1 or per_src.get(src, 0) < per_video)
        if chosen:
            seen.add(st.cluster)
            per_src[src] = per_src.get(src, 0) + 1
            picks.append((sid, st, 0))
        db.save_story(sid, batch_id, json.loads(st.model_dump_json()), score(st), chosen, None)
    # interleave so each day gets a mix: best story first each day, then the next tier
    days = max(plan["days"], -(-len(picks) // plan["per_day"]))
    out = []
    for k, (sid, st, _) in enumerate(picks):
        day = k % days
        out.append((sid, st, day))
        db.save_story(sid, batch_id, json.loads(st.model_dump_json()), score(st), True, day)
    return out
