"""Pure timing math: ms->frames, beat/word mapping, shot splitting, caption chunking.

Rules (from the spec):
  * start_frame = round(start_ms * fps / 1000)
  * shots are contiguous: no gaps, no overlaps, first starts at 0, last ends at duration
  * shot boundaries snap to word boundaries
  * a visual change every 1.5-3s; the hook gets 2 fast shots in the first 3s
"""
from __future__ import annotations

import math
from dataclasses import dataclass

PUNCT_BREAK = (".", ",", "!", "?", ";", ":", "—", "–")


def ms_to_frame(ms: float, fps: int = 30) -> int:
    return int(round(ms * fps / 1000.0))


@dataclass
class W:
    word: str
    start_ms: int
    end_ms: int


def beat_word_ranges(beat_texts: list[str], n_words: int) -> list[tuple[int, int]]:
    """Map each beat to its [start, end) slice of the flat word list."""
    ranges, i = [], 0
    for t in beat_texts:
        n = len(t.split())
        ranges.append((i, i + n))
        i += n
    if i != n_words:
        raise ValueError(f"beats have {i} words but voice track has {n_words}")
    return ranges


def _nearest_split(words: list[W], lo: int, hi: int, target_ms: float, window_ms: float = 280) -> int:
    """Index of the word (in lo+1..hi-1) whose start is nearest target_ms, preferring post-punctuation."""
    best, best_cost = None, math.inf
    for i in range(lo + 1, hi):
        cost = abs(words[i].start_ms - target_ms)
        if words[i - 1].word.endswith(PUNCT_BREAK) and cost <= window_ms:
            cost -= window_ms  # strong preference for natural phrase breaks
        if cost < best_cost:
            best, best_cost = i, cost
    return best if best is not None else lo


def split_beat(
    words: list[W], lo: int, hi: int, start_ms: float, end_ms: float,
    min_ms: int = 1500, max_ms: int = 3000, force_two: bool = False,
) -> list[int]:
    """Return word indices where sub-shots begin inside a beat (always includes lo)."""
    dur = end_ms - start_ms
    n = max(1, math.ceil(dur / max_ms))
    while n > 1 and dur / n < min_ms:
        n -= 1
    if force_two and n < 2 and hi - lo >= 2 and dur >= 1200:
        n = 2
    starts = [lo]
    for k in range(1, n):
        target = start_ms + dur * k / n
        if force_two and n == 2:
            target = start_ms + min(dur * 0.45, 1500)  # first hook shot is the fast one
        idx = _nearest_split(words, starts[-1], hi, target)
        if idx > starts[-1]:
            starts.append(idx)
    return starts


def caption_chunks(words: list[W], max_words: int = 3, max_ms: int = 1000, max_chars: int = 18, gap_ms: int = 250) -> list[list[int]]:
    """Group word indices into 1-3 word caption chunks."""
    chunks: list[list[int]] = []
    cur: list[int] = []
    for i, w in enumerate(words):
        if cur:
            first = words[cur[0]]
            chars = sum(len(words[j].word) + 1 for j in cur) + len(w.word)
            prev = words[cur[-1]]
            if (len(cur) >= max_words or w.end_ms - first.start_ms > max_ms or chars > max_chars
                    or prev.word.endswith(PUNCT_BREAK) or w.start_ms - prev.end_ms > gap_ms):
                chunks.append(cur)
                cur = []
        cur.append(i)
    if cur:
        chunks.append(cur)
    return chunks


def clean_caption_word(word: str) -> str:
    return word.strip(".,;:\"“”‘’()[]").replace("’", "'") or word
