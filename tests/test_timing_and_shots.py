import copy

import pytest

from clipforge import shots
from clipforge.schemas import Beat, Hook, PostCopy, Script, Visual, Word
from clipforge.timing import W, beat_word_ranges, caption_chunks, ms_to_frame, split_beat


def make_script() -> Script:
    beats = [
        Beat(kind="hook", text="Your VPN was the front door, and nobody locked it.",
             visual=Visual(type="kinetic", screen_text=["Front door *open*"])),
        Beat(kind="what", text="Attackers hit an unpatched gateway, grabbed session tokens, and walked straight into the network without a password.",
             visual=Visual(type="headline", screen_text=["No password"], headline="VPN zero-day under attack", kicker="CVE-2025-0001 · CVSS 9.8")),
        Beat(kind="how", text="The bug lets a crafted request skip the login check entirely. The server trusts a header it should never trust, so the attacker just says they are already logged in.",
             visual=Visual(type="code", screen_text=["Trust *nothing*"], code_language="http",
                           code_lines=["GET /api/session HTTP/1.1", "X-Auth-Verified: true", "", "200 OK"], code_highlight=2)),
        Beat(kind="why", text="Every company with this box exposed is a target until it is patched.",
             visual=Visual(type="stat", screen_text=["Patch *today*"], stat_value="40K", stat_label="exposed devices")),
        Beat(kind="punch", text="Patch it, or explain it to legal.",
             visual=Visual(type="kinetic", screen_text=["Explain it to *legal*"])),
    ]
    return Script(
        title="VPN front door",
        hooks=[Hook(spoken=beats[0].text, on_screen="Front door *open*")] * 3,
        beats=beats,
        music_mood="tense",
        post=PostCopy(caption="c", hashtags=["#a", "#b", "#c"], pinned_comment="p", cover_title="t"),
    )


def make_words(script: Script, ms_per_word: int = 330, pause_ms: int = 120) -> list[Word]:
    out, t = [], 0
    for tok in script.spoken_text().split():
        out.append(Word(word=tok, start_ms=t, end_ms=t + ms_per_word - 40))
        t += ms_per_word + (pause_ms if tok.endswith((".", ",")) else 0)
    return out


def test_ms_to_frame_rounding():
    assert ms_to_frame(0) == 0
    assert ms_to_frame(1000) == 30
    assert ms_to_frame(16) == 0       # 0.48 frames
    assert ms_to_frame(17) == 1       # 0.51 frames
    assert ms_to_frame(1234) == 37    # 37.02


def test_beat_word_ranges_cover_everything_and_detect_mismatch():
    assert beat_word_ranges(["a b", "c", "d e f"], 6) == [(0, 2), (2, 3), (3, 6)]
    with pytest.raises(ValueError):
        beat_word_ranges(["a b"], 3)


def test_split_beat_respects_max_length():
    words = [W(f"w{i}", i * 300, i * 300 + 250) for i in range(40)]  # 12s beat
    starts = split_beat(words, 0, 40, 0, 12000, 1500, 3000)
    bounds = [words[i].start_ms for i in starts] + [12000]
    assert all(b - a <= 3300 for a, b in zip(bounds, bounds[1:]))
    assert all(b - a >= 1000 for a, b in zip(bounds, bounds[1:]))


def test_hook_gets_two_fast_shots_in_first_3s():
    s = make_script()
    doc = shots.build(s, make_words(s), "t1")
    hook_shots = [x for x in doc["shots"] if x["beat"] == "hook"]
    assert len(hook_shots) >= 2
    assert hook_shots[1]["start_frame"] <= 3 * 30


def test_shots_are_contiguous_and_valid():
    s = make_script()
    doc = shots.build(s, make_words(s), "t1")
    shots.validate(doc)
    assert doc["shots"][0]["start_frame"] == 0
    assert doc["shots"][-1]["end_frame"] == doc["duration_frames"]
    for a, b in zip(doc["shots"], doc["shots"][1:]):
        assert a["end_frame"] == b["start_frame"]


def test_shots_change_every_three_seconds_ish():
    s = make_script()
    doc = shots.build(s, make_words(s), "t1")
    for sh in doc["shots"]:
        assert sh["end_frame"] - sh["start_frame"] <= 3.2 * 30, sh


def test_shot_boundaries_snap_to_word_starts():
    s = make_script()
    words = make_words(s)
    doc = shots.build(s, words, "t1")
    word_frames = {ms_to_frame(w.start_ms) for w in words} | {0}
    for sh in doc["shots"]:
        assert sh["start_frame"] in word_frames


def test_caption_chunks_max_three_words_no_overlap():
    s = make_script()
    words = make_words(s)
    ws = [W(w.word, w.start_ms, w.end_ms) for w in words]
    chunks = caption_chunks(ws)
    assert all(1 <= len(c) <= 3 for c in chunks)
    assert sum(len(c) for c in chunks) == len(ws)
    doc = shots.build(s, words, "t1")
    for a, b in zip(doc["captions"], doc["captions"][1:]):
        assert a["end_frame"] <= b["start_frame"]


def test_validate_rejects_gap():
    s = make_script()
    doc = shots.build(s, make_words(s), "t1")
    bad = copy.deepcopy(doc)
    bad["shots"][1]["start_frame"] += 3
    with pytest.raises(ValueError, match="gap/overlap"):
        shots.validate(bad)


def test_validate_rejects_unsafe_caption_zone():
    s = make_script()
    doc = shots.build(s, make_words(s), "t1")
    bad = copy.deepcopy(doc)
    bad["layout"]["caption_bottom"] = 1800
    with pytest.raises(ValueError, match="bottom UI zone"):
        shots.validate(bad)


def test_validate_rejects_schema_violation():
    s = make_script()
    doc = shots.build(s, make_words(s), "t1")
    bad = copy.deepcopy(doc)
    del bad["shots"][0]["props"]["text"]
    with pytest.raises(Exception):
        shots.validate(bad)
