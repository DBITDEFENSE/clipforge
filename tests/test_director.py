from clipforge import director
from clipforge.schemas import DirectedShot, ShotPlan
from test_timing_and_shots import make_script, make_words


def test_director_repairs_a_sloppy_plan(tmp_path):
    s = make_script()
    words = make_words(s)
    n = len(words)
    plan = ShotPlan(shots=[
        DirectedShot(start_word=3, type="kinetic", motion="pop", text="Front door *open*"),   # doesn't start at 0
        DirectedShot(start_word=12, type="cve", motion="punch_in", card_key="c", cve_id="CVE-2025-0001", cvss=9.8),
        DirectedShot(start_word=13, type="kinetic", motion="pop", text="too short"),          # < 0.7s -> merged
        DirectedShot(start_word=30, type="terminal", motion="drift", card_key="t", terminal_lines=["$ x", "y"]),  # long -> split
        DirectedShot(start_word=31, type="code", motion="pop"),                               # unusable (no lines) -> dropped
        DirectedShot(start_word=n + 5, type="kinetic", motion="pop", text="out of range"),     # dropped
        DirectedShot(start_word=n - 6, type="broll", motion="drift", broll_query="server room", text="Patch *today*"),
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
    assert any("merged" in x for x in notes) and any("split" in x for x in notes)
