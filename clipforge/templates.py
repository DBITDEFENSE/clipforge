"""Short formats ("templates"): preset shapes a short can take, picked per story.

A template never changes the pipeline or the schema: every short still has the hook / what / how / why / punch beats and
the same shot types. A template is guidance for the writer (how to use those beats) and for the director (which
visuals to lean on, e.g. source gameplay for a gameplay short, step cards for a tutorial).

Per channel (visuals JSON -> "templates"): {"mode": "auto" | "fixed", "fixed": id, "enabled": [ids]}
  auto   pick the best-matching enabled template for each story (category + keywords), rotating between ties
  fixed  every short uses one template
The choice is saved to work/shorts/<id>/template.json so the director and later re-directs use the same one.
"""
from __future__ import annotations

import hashlib
import json
import re

from .config import WORK

# cats: story categories the format suits ([] = any). keys: words that pull a story towards it.
TEMPLATES: list[dict] = [
    {"id": "news_flash", "name": "News flash", "cats": ["cyber", "tech", "ai"],
     "desc": "Breaking-news recap: what happened, how, why you care. The default.",
     "keys": ["breach", "hack", "leak", "announced", "outage", "lawsuit", "zero-day", "ransomware", "patched", "exploited"],
     "write": "Classic news recap. Lead with the single most alarming or absurd fact, then who/what/when with exact names and numbers.",
     "direct": "News look: a `headline` card when the event is named, a `stat` or `cve` for the number, source clips of the real footage, article or screen being discussed."},
    {"id": "gameplay_commentary", "name": "Gameplay commentary", "cats": ["gaming"],
     "desc": "The game footage is the star; narration reacts to what's on screen.",
     "keys": ["gameplay", "game", "boss", "speedrun", "glitch", "trailer", "update", "patch notes", "dlc", "nerf", "buff", "esports", "console", "steam"],
     "write": "Write it as commentary over the footage: every line refers to something the viewer can SEE in the game (the move, the bug, the scene). `how` explains the mechanic or trick in plain words.",
     "direct": "Source gameplay carries the video: use as many `clip` shots as the cap allows, on every beat where the game shows what's being said, each as long as allowed. Between clips use `kinetic` punch words and `reaction` memes. No stock `broll`."},
    {"id": "tutorial_steps", "name": "Tutorial / how-to", "cats": [],
     "desc": "Do this, then this: numbered steps over the real screen recording.",
     "keys": ["how to", "tutorial", "guide", "step", "setup", "install", "configure", "walkthrough", "tips", "trick", "settings", "build"],
     "write": "Teach one thing. `hook` promises the result, `what` names the tool and the goal, `how` is 2-3 numbered steps said as 'First... Then... Finally...', `why` is the payoff or the mistake to avoid.",
     "direct": "Show the steps: `clip` shots of the source screen recording at the exact moment each step is done, with a `lower_title` naming the step ('STEP 1'). Use `code` or `terminal` for anything typed, and `kinetic` 'STEP 1/2/3' cards between."},
    {"id": "explainer", "name": "Explainer: how it works", "cats": ["cyber", "tech", "ai"],
     "desc": "One mechanism made obvious with a diagram and an analogy.",
     "keys": ["how it works", "explained", "protocol", "algorithm", "architecture", "under the hood", "mechanism", "works by", "model"],
     "write": "The `how` beat is the star: one vivid everyday analogy, then the real mechanism in one sentence. Spend less on `what`.",
     "direct": "Build around a `diagram` (2-4 nodes) that continues across several shots with the same `card_key`, plus `code`/`terminal` when something concrete can be shown. Clips only if the source shows the thing working."},
    {"id": "top_3", "name": "Top 3 countdown", "cats": [],
     "desc": "Three ranked items, fastest format to follow.",
     "keys": ["top", "best", "worst", "ranked", "list", "three", "five", "features", "reasons", "things"],
     "write": "Countdown. `hook` promises the list and teases number one. `what` is number 3, `how` is number 2, `why` is number 1 with the reason it wins. Say the numbers out loud.",
     "direct": "Each item opens with a `kinetic` '*#3*', '*#2*', '*#1*' card (pop, with `whoosh`), followed by a clip or stat that shows the item. `boom` and `shake` on number one."},
    {"id": "myth_vs_fact", "name": "Myth vs. fact", "cats": [],
     "desc": "What everyone believes, then what's actually true.",
     "keys": ["myth", "actually", "misconception", "wrong", "everyone thinks", "turns out", "debunk", "not true", "rumor"],
     "write": "`hook` states the common belief flatly. `what` says it's wrong and what is true instead. `how` gives the evidence. `why` says what to do differently.",
     "direct": "Open with a `kinetic` '*MYTH*' card, then a `reaction` (🤡 or 😬), then '*FACT*'. Use `glitch` fx on the turn. Evidence as a `stat`, a clip of the proof, or a `headline`."},
    {"id": "hot_take", "name": "Hot take", "cats": [],
     "desc": "An opinion with receipts. Built to start arguments in the comments.",
     "keys": ["controversial", "overrated", "underrated", "opinion", "backlash", "criticism", "debate", "drama", "fans", "review"],
     "write": "Take a clear side in the first line and never hedge. `what` is the receipt that backs it, `how` is the strongest counter-argument dismantled in one sentence, `why` is who should care. The pinned comment invites disagreement.",
     "direct": "Fast and loud: `kinetic` for the take, `reaction` memes on the roasts (3-4), clips or a `stat` for each receipt. `fire` on the harshest line."},
    {"id": "story_time", "name": "Story time", "cats": [],
     "desc": "A mini story with a setup, a twist and a payoff.",
     "keys": ["story", "happened", "discovered", "found", "years ago", "secret", "mystery", "turned out", "caught", "arrested", "heist"],
     "write": "Tell it as a story about a person or a team: setup in `what`, the turn in `how`, the consequence in `why`. Past tense, concrete details, and hold the twist until `how`.",
     "direct": "Cinematic pacing: `punch_in` motion for tension, AI or stock `broll` for scene-setting at the start, `riser` then `boom` on the twist, a `reaction` right after it."},
    {"id": "versus", "name": "Versus / comparison", "cats": [],
     "desc": "A vs. B with a clear winner.",
     "keys": [" vs ", "versus", "compared", "comparison", "better than", "faster than", "cheaper", "alternative", "benchmark", "beats"],
     "write": "Name both sides in the hook. `what` is side A's best number, `how` is side B's and why they differ, `why` declares the winner and for whom.",
     "direct": "Alternate sides shot by shot: a `stat` for each side's number, clips of each when the source shows them, a `diagram` 'A → B' only if it helps. End on a `kinetic` '*WINNER*' card with `boom`."},
    {"id": "by_the_numbers", "name": "By the numbers", "cats": [],
     "desc": "Three or four staggering numbers, back to back.",
     "keys": ["million", "billion", "percent", "%", "$", "record", "users", "revenue", "cost", "sold", "views", "statistics"],
     "write": "Stack numbers. Every beat except the punch contains one exact figure from the facts, each put next to something mundane for scale.",
     "direct": "`stat` cards are the spine (3-4, each a different number), `ding` or `cash` on each, `emoji_rain` 💸 for money. Break them up with one clip or `reaction`."},
    {"id": "timeline", "name": "Timeline", "cats": [],
     "desc": "How we got here: three dated moments in order.",
     "keys": ["timeline", "first", "then", "later", "since", "history", "2019", "2020", "2021", "2022", "2023", "2024", "2025", "2026", "months", "years"],
     "write": "Chronological. `what` is where it started (with the date), `how` is the turning point, `why` is where it stands today. Dates exact.",
     "direct": "Each moment opens with a `headline` whose `kicker` is the date, then a clip or stat for that moment. Use `drift` motion and `whoosh` between dates."},
    {"id": "reaction", "name": "Reaction", "cats": [],
     "desc": "Show the clip, react to it. Short clips, big memes.",
     "keys": ["clip", "viral", "moment", "interview", "said", "trailer", "reveal", "demo", "livestream", "stream", "on stage", "keynote"],
     "write": "React like someone watching it for the first time. `what` describes the moment plainly, `how` points out the detail most people missed, `why` is the verdict.",
     "direct": "Clip, then reaction, repeated: a `clip` shot of the moment followed immediately by a `reaction` meme (💀 😳 🤯). Use the clip cap fully. `pop` sfx on each reaction."},
    {"id": "tool_spotlight", "name": "Tool / product spotlight", "cats": ["tech", "ai", "cyber"],
     "desc": "One tool, what it does, who it's for.",
     "keys": ["tool", "app", "open source", "github", "release", "launch", "feature", "plugin", "extension", "library", "framework", "free", "new model"],
     "write": "`hook` is the one thing it does that sounds impossible or saves hours. `what` names it and who made it, `how` shows it in use in one concrete example, `why` says who should try it and the catch.",
     "direct": "Show the tool: clips of the source demo or UI, `terminal` or `code` for the one command or snippet, a `headline` with the tool name on first mention, a `stat` for the headline number (stars, speed, price)."},
    {"id": "warning_psa", "name": "Warning / PSA", "cats": ["cyber", "tech"],
     "desc": "Stop scrolling: this affects you and here is the fix.",
     "keys": ["scam", "phishing", "warning", "update now", "malware", "vulnerable", "exposed", "affected", "urgent", "recall", "fraud", "stolen"],
     "write": "Talk straight to the viewer ('if you use X'). `what` is the danger with the exact scope, `how` is how it gets you, `why` is the fix in one clear action. The punch stays funny, but the fix must be unmissable.",
     "direct": "`alarm` fx with the alert strip on the hook, `popups` when it escalates, a `cve` card if there is one, and a final `kinetic` card that states the fix in <= 5 words."},
    {"id": "what_if", "name": "What if / thought experiment", "cats": [],
     "desc": "Take one fact to its logical, absurd conclusion.",
     "keys": ["what if", "imagine", "could", "would", "future", "predict", "theory", "scenario", "someday", "possible"],
     "write": "`hook` poses the scenario as a statement, not a question. `what` is the real fact it rests on, `how` walks one step of consequences, `why` is how close this is to real. Keep speculation labelled as speculation.",
     "direct": "Imaginative: AI `broll` for the scenario shots (vivid `video_prompt`), `diagram` for the chain of consequences, `glitch` on the turn. Clips only for the real fact."},
    {"id": "behind_the_scenes", "name": "Behind the scenes / dev story", "cats": ["gaming", "tech", "ai"],
     "desc": "How it was made, and the thing that almost broke it.",
     "keys": ["developer", "studio", "behind the scenes", "making of", "engine", "cut content", "development", "team", "crunch", "budget", "postmortem", "designer"],
     "write": "`what` is the thing that got made and by whom, `how` is the clever trick or the near-disaster behind it, `why` is why it changes how you see the finished product.",
     "direct": "Mix the finished product (clips of the game or product in action) with the making-of: `code` or `diagram` for the trick, `stat` for budget or team size, `reaction` on the near-disaster."},
]
BY_ID = {t["id"]: t for t in TEMPLATES}
DEFAULT_ID = "news_flash"
DEFAULTS = {"mode": "auto", "fixed": DEFAULT_ID, "enabled": [t["id"] for t in TEMPLATES]}


def clean(cfg: dict | None) -> dict:
    """Validated settings: unknown ids dropped, an empty list means all."""
    cfg = cfg if isinstance(cfg, dict) else {}
    enabled = [i for i in cfg.get("enabled") or [] if i in BY_ID] or list(DEFAULTS["enabled"])
    return {"mode": "fixed" if cfg.get("mode") == "fixed" else "auto",
            "fixed": cfg.get("fixed") if cfg.get("fixed") in BY_ID else DEFAULT_ID, "enabled": enabled}


def config() -> dict:
    try:
        from .accounts import current

        return clean((current().get("visuals") or {}).get("templates"))
    except Exception:  # noqa: BLE001  (no account yet)
        return clean(None)


def _text(story) -> str:
    parts = [story.topic, story.angle, getattr(story, "how_it_works", "") or "", " ".join(story.key_facts or [])]
    return " " + re.sub(r"\s+", " ", " ".join(parts).lower()) + " "


def score(t: dict, story) -> int:
    text = _text(story)
    return 2 * sum(1 for k in t["keys"] if k in text) + (3 if story.category in t["cats"] else 0)


def choose(story, cfg: dict | None = None) -> dict:
    """The template for this story. Deterministic: same story + settings -> same template."""
    cfg = clean(cfg) if cfg is not None else config()
    if cfg["mode"] == "fixed":
        return BY_ID[cfg["fixed"]]
    pool = [BY_ID[i] for i in cfg["enabled"]]
    best = max(score(t, story) for t in pool)
    top = [t for t in pool if score(t, story) == best]
    # ties (and stories nothing matches) rotate by the story's cluster, so a batch gets a mix of formats
    return top[int(hashlib.sha256(story.cluster.encode()).hexdigest(), 16) % len(top)]


def _file(short_id: str):
    return WORK / "shorts" / short_id / "template.json"


def assign(short_id: str, story) -> dict:
    """Pick (or re-read) the template for a short and remember it."""
    f = _file(short_id)
    if f.exists():
        try:
            t = BY_ID.get(json.loads(f.read_text(encoding="utf-8")).get("id"))
            if t and (config()["mode"] == "auto" or t["id"] == config()["fixed"]):
                return t
        except ValueError:
            pass
    t = choose(story)
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps({"id": t["id"], "name": t["name"]}), encoding="utf-8")
    return t


def for_short(short_id: str) -> dict | None:
    try:
        return BY_ID.get(json.loads(_file(short_id).read_text(encoding="utf-8")).get("id"))
    except (OSError, ValueError):
        return None


def writer_note(t: dict) -> str:
    return (f"\n\n## Format for this short: {t['name']}\n{t['write']}\n"
            "Keep the five beats (hook, what, how, why, punch) and the word budget; the format decides what each beat does.")


def director_note(t: dict) -> str:
    return f"\n\nFORMAT: {t['name']}. {t['direct']} The pacing rules still apply."
