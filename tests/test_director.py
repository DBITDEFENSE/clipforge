from clipforge import director
from clipforge.schemas import DirectedShot, ShotPlan
from test_timing_and_shots import make_script, make_words


def test_director_repairs_a_sloppy_plan(tmp_path, monkeypatch):
    from clipforge import videogen

    # don't depend on (or run) the live channel's B-roll engine
    monkeypatch.setattr(videogen, "config", lambda: videogen.DEFAULTS | {"engine": "none", "model": ""})
    s = make_script()
    words = make_words(s)
    n = len(words)
    E = dict(card_key="", text="", kicker="", value="", label="", score=0, lines=[], code_language="", highlight=0,
             broll_query="", video_prompt="", clip_id="", lower_title="", lower_sub="", emoji="", fx="none", sfx="none")
    S = lambda **kw: DirectedShot(**(E | kw))  # noqa: E731
    plan = ShotPlan(shots=[
        S(start_word=3, type="kinetic", motion="pop", text="Front door *open*"),   # doesn't start at 0
        S(start_word=12, type="cve", motion="punch_in", card_key="c", value="CVE-2025-0001", score=9.8, kicker="CRITICAL"),
        S(start_word=13, type="kinetic", motion="pop", text="too short"),          # < 0.7s -> merged
        S(start_word=20, type="reaction", motion="pop", emoji="💀", text="Nobody *noticed*", kicker="POV:", sfx="boom", fx="shake"),
        S(start_word=30, type="terminal", motion="drift", card_key="t", lines=["$ x", "y"], fx="glitch", sfx="glitch", emoji="😬"),  # long -> split
        S(start_word=31, type="code", motion="pop"),                               # unusable (no lines) -> dropped
        S(start_word=n + 5, type="kinetic", motion="pop", text="out of range"),    # dropped
        S(start_word=n - 6, type="broll", motion="drift", broll_query="server room", text="Patch *today*"),
    ])
    doc, notes = director.to_doc(plan, s, words, "t1", tmp_path)  # validate() runs inside
    shots = doc["shots"]
    assert shots[0]["start_frame"] == 0
    assert all(sh["end_frame"] - sh["start_frame"] <= 3.2 * 30 for sh in shots)
    term = [sh for sh in shots if sh["type"] == "terminal"]
    assert len(term) >= 2 and len({sh["props"]["anim_start_frame"] for sh in term}) == 1  # card continues across splits
    assert not any(sh["type"] == "broll" for sh in shots)  # engine "none" -> falls back to kinetic
    assert any(sh["type"] == "cve" for sh in shots)        # the short CVE shot was kept (it absorbed the next one)
    assert not any(sh["props"].get("text") == "too short" for sh in shots)
    react = [sh for sh in shots if sh["type"] == "reaction"]
    assert react and react[0]["props"]["emoji"] == "💀" and react[0]["props"]["fx"] == "shake"
    assert react[0]["props"]["sfx_src"].startswith("sfx/boom")
    assert term[0]["props"]["fx"] == "glitch" and term[0]["props"]["emoji"] == "😬" and term[0]["props"].get("sfx_src")
    assert all("fx" not in sh["props"] and "sfx_src" not in sh["props"] for sh in term[1:])  # effects hit once, on the first cut
    assert any("merged" in x for x in notes) and any("split" in x for x in notes)


E = dict(card_key="", text="", kicker="", value="", label="", score=0, lines=[], code_language="", highlight=0,
         broll_query="", video_prompt="", clip_id="", lower_title="", lower_sub="", emoji="", fx="none", sfx="none")


def _fake_footage(monkeypatch, cuts, max_clips=2):
    from clipforge import footage

    def fake_cut(h, start, secs, dst, mode="clips", style="", strength=0.5, layout=None):
        cuts.append((h, start, round(secs, 2), mode, layout))
        dst.write_bytes(b"x")
        return {"path": dst, "seconds": secs, "box": footage.frame_box(layout)}

    monkeypatch.setattr(footage, "cut", fake_cut)
    monkeypatch.setattr(footage, "credit", lambda h: {"label": "Mad Hat", "url": "https://y/1", "title": "t"})
    monkeypatch.setattr(footage, "config", lambda account=None: {"footage": "clips", "max_source_clips": max_clips,
                                                                 "style_effective": "", "restyle_strength": 0.5})


def test_clip_shot_becomes_source_broll_that_continues_across_cuts(tmp_path, monkeypatch):
    from clipforge import footage

    s = make_script()
    words = make_words(s)
    S = lambda **kw: DirectedShot(**(E | kw))  # noqa: E731
    cuts = []
    _fake_footage(monkeypatch, cuts)
    moments = [{"id": "C1", "hash": "abc", "start": 12.0, "end": 18.0, "text": "demo"}]
    plan = ShotPlan(shots=[
        S(start_word=0, type="kinetic", motion="pop", text="Hook *here*"),
        S(start_word=4, type="kinetic", motion="punch_in", text="second"),
        S(start_word=8, type="clip", motion="drift", clip_id="c1", text="Watch *this*"),  # lower-case id still resolves
        S(start_word=30, type="clip", motion="drift", clip_id="C9"),      # unknown id -> kinetic
        S(start_word=34, type="kinetic", motion="pop", text="end"),
    ])
    doc, notes = director.to_doc(plan, s, words, "t1", tmp_path, moments)
    clip_shots = [x for x in doc["shots"] if x["props"].get("source")]
    assert len(cuts) == 1 and cuts[0][:2] == ("abc", 12.0)
    assert cuts[0][2] <= footage.MAX_CLIP_S + 0.2  # small clips: never longer than the cap (+ the 0.2 s pad)
    assert clip_shots and clip_shots[0]["type"] == "broll" and clip_shots[0]["props"]["offset"] == 0
    for a, b in zip(clip_shots, clip_shots[1:]):  # later cuts keep playing the same clip, inside its length
        assert b["props"]["src"] == a["props"]["src"] and b["props"]["offset"] > a["props"]["offset"]
    fps = doc["fps"]
    assert all(c["props"]["offset"] + (c["end_frame"] - c["start_frame"]) / fps <= cuts[0][2] + 0.01 for c in clip_shots)
    assert any("unknown clip id" in n for n in notes)


def test_long_clip_beat_falls_back_to_its_text_after_the_cap(tmp_path, monkeypatch):
    from clipforge import footage

    s = make_script()
    words = make_words(s)
    S = lambda **kw: DirectedShot(**(E | kw))  # noqa: E731
    cuts = []
    _fake_footage(monkeypatch, cuts)
    moments = [{"id": "C1", "hash": "abc", "start": 12.0, "end": 14.0, "text": "demo"}]  # a 2 s moment
    plan = ShotPlan(shots=[
        S(start_word=0, type="kinetic", motion="pop", text="Hook"),
        S(start_word=4, type="kinetic", motion="pop", text="second"),
        S(start_word=8, type="clip", motion="drift", clip_id="C1", text="The *demo*"),  # runs to the end: long beat
    ])
    doc, _ = director.to_doc(plan, s, words, "t1", tmp_path, moments)
    clip_shots = [x for x in doc["shots"] if x["props"].get("source")]
    assert clip_shots and cuts[0][2] <= footage.clip_seconds(moments[0], 1e9) + 0.2
    after = [x for x in doc["shots"] if x["start_frame"] >= clip_shots[-1]["end_frame"]]
    assert after and all(x["type"] == "kinetic" and x["props"]["text"] == "The *demo*" for x in after)


def test_clip_uses_the_gameplay_layout(tmp_path, monkeypatch):
    from clipforge import director as d
    from clipforge import shots

    s = make_script()
    words = make_words(s)
    S = lambda **kw: DirectedShot(**(E | kw))  # noqa: E731
    cuts = []
    _fake_footage(monkeypatch, cuts)
    monkeypatch.setattr(d, "layout_for", lambda sid: shots.LAYOUT_GAMEPLAY)
    moments = [{"id": "C1", "hash": "abc", "start": 12.0, "end": 18.0, "text": "demo"}]
    plan = ShotPlan(shots=[S(start_word=0, type="kinetic", motion="pop", text="Hook"),
                           S(start_word=4, type="kinetic", motion="pop", text="x"),
                           S(start_word=8, type="clip", motion="drift", clip_id="C1"),
                           S(start_word=20, type="kinetic", motion="pop", text="end")])
    doc, _ = d.to_doc(plan, s, words, "t1", tmp_path, moments)
    clip = next(x for x in doc["shots"] if x["props"].get("source"))["props"]
    g = shots.LAYOUT_GAMEPLAY
    assert cuts[0][4] == g
    assert clip["canvas_h"] == g["gameplay_top"]
    assert g["content_top"] <= clip["fg_y"] and clip["fg_y"] + clip["fg_h"] <= g["content_bottom"]
