"""Structured-output contracts for Claude (Pydantic) and data passed between stages."""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

Category = Literal["cyber", "tech", "ai", "gaming", "other"]


# ---------- story mining ----------
class SourceRef(BaseModel):
    video_id: str = Field(description="The [VIDEO id] tag the fact came from")
    timestamp: str = Field(description="mm:ss in that transcript where the story is discussed")


class StoryScores(BaseModel):
    hook: int = Field(description="1-10: how hard the first line can hit")
    clarity: int = Field(description="1-10: understandable with zero context in under 60s")
    curiosity: int = Field(description="1-10: makes a scrolling viewer need the answer")
    niche_fit: int = Field(description="1-10: fit for a cybersecurity-first tech channel")


class Story(BaseModel):
    topic: str = Field(description="Short topic label, e.g. 'Ivanti VPN zero-day exploited'")
    cluster: str = Field(description="kebab-case key; two stories about the same event share a cluster")
    category: Category
    key_facts: list[str] = Field(description="Concrete, specific facts from the sources: names, numbers, dates, CVE IDs, versions")
    angle: str = Field(description="The 'holy shit' angle that makes this worth 45 seconds")
    who_affected: str
    how_it_works: str = Field(description="One plain-English technical mechanism worth visualizing (no exploit steps)")
    sources: list[SourceRef]
    scores: StoryScores


class StoryList(BaseModel):
    stories: list[Story]


# ---------- script writing ----------
class Hook(BaseModel):
    spoken: str = Field(description="First spoken line, lands in under 2 seconds (<= 14 words)")
    on_screen: str = Field(description="On-screen text for the first 1-2s, <= 6 words, *wrap* one word to accent it")


VisualType = Literal["kinetic", "code", "terminal", "headline", "stat"]


class Visual(BaseModel):
    type: VisualType
    screen_text: list[str] = Field(
        description="1-3 punchy on-screen phrases (<= 5 words each) for kinetic shots in this beat; *wrap* one word to accent it"
    )
    code_language: Optional[str] = Field(default=None, description="For type=code: language label, e.g. python, bash, http")
    code_lines: Optional[list[str]] = Field(default=None, description="For type=code: 3-9 short ILLUSTRATIVE lines, never a working exploit")
    code_highlight: Optional[int] = Field(default=None, description="For type=code: 1-based line to highlight")
    terminal_lines: Optional[list[str]] = Field(
        default=None, description="For type=terminal: 3-8 lines; prefix commands with '$ ', output lines without. Illustrative only."
    )
    headline: Optional[str] = Field(default=None, description="For type=headline: <= 9 word headline in our words")
    kicker: Optional[str] = Field(default=None, description="For type=headline: tag line, e.g. 'CVE-2025-1234 · CVSS 9.8'")
    stat_value: Optional[str] = Field(default=None, description="For type=stat: the number, e.g. '4.2M' or '97%'")
    stat_label: Optional[str] = Field(default=None, description="For type=stat: what it counts, <= 6 words")


BeatKind = Literal["hook", "what", "how", "why", "punch"]


class Beat(BaseModel):
    kind: BeatKind
    text: str = Field(description="Exactly what is spoken in this beat. Spoken English: spell nothing out phonetically.")
    visual: Visual


class PostCopy(BaseModel):
    caption: str = Field(description="<= 150 chars, curiosity-driven, no hashtags inside")
    hashtags: list[str] = Field(description="3-5 hashtags including the #")
    pinned_comment: str
    cover_title: str = Field(description="<= 6 words for the cover image")


Mood = Literal["tense", "dark", "driving", "curious", "upbeat"]


class Script(BaseModel):
    title: str
    hooks: list[Hook] = Field(description="Exactly 3 hook options; hooks[0] is the strongest and matches beats[0].text")
    beats: list[Beat] = Field(description="Ordered: hook, what, how, why, punch (what/why may repeat)")
    music_mood: Mood
    post: PostCopy

    def spoken_text(self) -> str:
        return " ".join(b.text.strip() for b in self.beats)

    def word_count(self) -> int:
        return len(self.spoken_text().split())


# ---------- self-review ----------
class Review(BaseModel):
    issues: list[str] = Field(description="Every problem found (facts, hook, pacing, clarity, length). Empty if none.")
    revised: Script = Field(description="The fixed script. Identical to the input if there were no issues.")


# ---------- director (Claude-authored shots) ----------
ShotKind = Literal["kinetic", "headline", "stat", "code", "terminal", "diagram", "cve", "broll"]
MotionKind = Literal["pop", "punch_in", "drift", "none"]


class DirectedShot(BaseModel):
    start_word: int = Field(description="Index of the word where this shot begins (shots must start on word boundaries; first shot = 0)")
    type: ShotKind
    motion: MotionKind
    card_key: Optional[str] = Field(default=None, description="Shots sharing a card_key continue the same card animation (e.g. one terminal typing across 3 shots)")
    text: Optional[str] = Field(default=None, description="kinetic: <= 5 words, *wrap* the accent word(s). broll: optional <= 4 word overlay")
    headline: Optional[str] = Field(default=None, description="headline: <= 9 words")
    kicker: Optional[str] = Field(default=None, description="headline: short tag line")
    stat_value: Optional[str] = None
    stat_label: Optional[str] = None
    code_language: Optional[str] = None
    code_lines: Optional[list[str]] = Field(default=None, description="code: 3-9 short illustrative lines, never a working exploit")
    code_highlight: Optional[int] = None
    terminal_lines: Optional[list[str]] = Field(default=None, description="terminal: 3-8 lines, commands prefixed '$ ', illustrative only")
    nodes: Optional[list[str]] = Field(default=None, description="diagram: 2-4 node labels in flow order, <= 2 words each (e.g. Attacker, VPN, Server)")
    flow_label: Optional[str] = Field(default=None, description="diagram: <= 4 word label for what moves along the arrows")
    danger_node: Optional[int] = Field(default=None, description="diagram: 0-based index of the compromised/victim node (drawn in warning color)")
    cve_id: Optional[str] = None
    cvss: Optional[float] = None
    severity: Optional[Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]] = None
    product: Optional[str] = Field(default=None, description="cve: affected product, <= 5 words")
    broll_query: Optional[str] = Field(default=None, description="broll: 2-4 word stock-footage search (concrete, filmable: 'server room lights', 'typing keyboard dark')")
    lower_title: Optional[str] = Field(default=None, description="Optional lower-third overlay title (a name, vendor, or source), <= 4 words")
    lower_sub: Optional[str] = Field(default=None, description="Optional lower-third subtitle, <= 6 words")


class ShotPlan(BaseModel):
    shots: list[DirectedShot]


# ---------- voice ----------
class Word(BaseModel):
    word: str
    start_ms: int
    end_ms: int
