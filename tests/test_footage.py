from clipforge import footage
from clipforge.pipeline import clip_credit, with_clip_credit
from clipforge.schemas import DirectedShot


def test_parse_ts():
    assert footage.parse_ts("04:03") == 243
    assert footage.parse_ts("1:02:03") == 3723
    assert footage.parse_ts("") is None
    assert footage.parse_ts("soon") is None


def test_chunk_merges_short_segments_and_respects_window():
    segs = [{"start": i * 2.0, "end": i * 2.0 + 1.8, "text": f"s{i}"} for i in range(20)]
    out = footage.chunk(segs, 10, 30)
    assert out and all(10 - 2 <= a and b <= 32 for a, b, _ in out)
    assert all(b - a >= 1.5 for a, b, _ in out)
    assert all(b - a <= 8.0 for a, b, _ in out)


def test_chunk_splits_on_gap():
    segs = [{"start": 0, "end": 2, "text": "a"}, {"start": 10, "end": 14, "text": "b"}]
    out = footage.chunk(segs, 0, 20)
    assert [t for _, _, t in out] == ["a", "b"]


def test_restyle_frames_are_4k_plus_1_and_capped():
    for s in (0.5, 2.0, 3.3, 5.0, 9.0):
        n = footage.restyle_frames_needed(s)
        assert (n - 1) % 4 == 0 and 17 <= n <= footage.R_MAX


def test_clip_credit_lists_each_source_once():
    doc = {"shots": [
        {"type": "broll", "props": {"source": True, "credit": "Mad Hat", "credit_url": "https://y/1"}},
        {"type": "broll", "props": {"source": True, "credit": "Mad Hat", "credit_url": "https://y/1", "offset": 2}},
        {"type": "broll", "props": {"src": "broll_0.mp4", "credit": "AI-generated video (Wan)"}},
        {"type": "kinetic", "props": {"text": "x"}},
    ]}
    assert clip_credit(doc) == "Clips: Mad Hat - https://y/1"
    assert clip_credit({"shots": []}) == ""


def test_clip_is_a_director_shot_type():
    assert "clip" in DirectedShot.model_fields["type"].annotation.__args__
    assert "clip_id" in DirectedShot.model_fields


def test_chunk_skips_unaligned_segments():
    segs = [{"start": 0, "end": 4, "text": "a"}, {"start": None, "end": 6, "text": "lost"}, {"start": 7, "end": None, "text": "x"},
            {"start": 8, "end": 12, "text": "b"}]
    assert [t for _, _, t in footage.chunk(segs, 0, 20)] == ["a", "b"]


def test_clip_seconds_is_small():
    m = {"start": 10.0, "end": 16.0}
    assert footage.clip_seconds(m, 30) == footage.MAX_CLIP_S
    assert footage.clip_seconds({"start": 10.0, "end": 12.0}, 30) == 2.6  # just past the moment's end
    assert footage.clip_seconds(m, 1.5) == 1.5


def test_frame_box_stays_in_the_content_zone():
    from clipforge.shots import LAYOUT, LAYOUT_GAMEPLAY

    for lay in (LAYOUT, LAYOUT_GAMEPLAY):
        b = footage.frame_box(lay)
        assert lay["content_top"] <= b["fg_y"] and b["fg_y"] + b["fg_h"] <= lay["content_bottom"]
        assert b["fg_y"] + b["fg_h"] <= lay["caption_top"]
    assert footage.frame_box(LAYOUT)["canvas_h"] == 1920
    assert footage.frame_box(LAYOUT_GAMEPLAY)["canvas_h"] == LAYOUT_GAMEPLAY["gameplay_top"]


def test_unknown_footage_mode_falls_back_to_the_default(monkeypatch):
    from clipforge import accounts

    monkeypatch.setattr(accounts, "current", lambda: {"id": "x", "visuals": {"footage": "bogus"}})
    assert footage.config()["footage"] == footage.DEFAULTS["footage"]


def test_clip_credit_for_a_local_file_has_no_empty_url():
    doc = {"shots": [{"type": "broll", "props": {"source": True, "credit": "My Video", "credit_url": "",
                                                 "credit_title": "My Video"}},
                     {"type": "broll", "props": {"source": True, "credit": "Mad Hat", "credit_url": "",
                                                 "credit_title": "Worst week ever"}}]}
    assert clip_credit(doc) == "Clips: My Video; Mad Hat: Worst week ever"
    assert with_clip_credit("cap", "") == "cap"
    assert with_clip_credit("cap", "Clips: x", " | ") == "cap | Clips: x"
