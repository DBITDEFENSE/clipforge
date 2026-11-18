from clipforge import director
from clipforge.schemas import DirectedShot, ShotPlan
from test_timing_and_shots import make_script, make_words


def test_director_repairs_a_sloppy_plan(tmp_path):
    s = make_script()
    words = make_words(s)
    n = len(words)
    E = dict(card_key="", text="", kicker="", value="", label="", score=0, lines=[], code_language="", highlight=0,
             broll_query="", lower_title="", lower_sub="", emoji="", fx="none", sfx="none")
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
    assert not any(sh["type"] == "broll" for sh in shots)  # no Pexels key in tests -> falls back to kinetic
    assert any(sh["type"] == "cve" for sh in shots)        # the short CVE shot was kept (it absorbed the next one)
    assert not any(sh["props"].get("text") == "too short" for sh in shots)
    react = [sh for sh in shots if sh["type"] == "reaction"]
    assert react and react[0]["props"]["emoji"] == "💀" and react[0]["props"]["fx"] == "shake"
    assert react[0]["props"]["sfx_src"].startswith("sfx/boom")
    assert term[0]["props"]["fx"] == "glitch" and term[0]["props"]["emoji"] == "😬" and term[0]["props"].get("sfx_src")
    assert all("fx" not in sh["props"] and "sfx_src" not in sh["props"] for sh in term[1:])  # effects hit once, on the first cut
    assert any("merged" in x for x in notes) and any("split" in x for x in notes)
