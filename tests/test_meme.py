import pytest

from clipforge import meme, shots
from test_timing_and_shots import make_script, make_words


@pytest.mark.parametrize("fmt", ["nope_yep", "pov"])
def test_meme_lands_in_first_six_seconds(fmt):
    s = make_script()
    doc = shots.build(s, make_words(s), "m1")
    props = {"format": fmt, "top": "POV:", "bottom": "it broke", "emoji": "💀",
             "panels": [{"emoji": "🙅", "text": "test it"}, {"emoji": "😎", "text": "ship it"}]}
    out = meme.insert(doc, props)
    shots.validate(out)                                   # contiguous, starts at 0, ends at duration
    m = [x for x in out["shots"] if x["type"] == "meme"]
    assert len(m) == 1
    assert 30 <= m[0]["start_frame"] <= 105 and m[0]["end_frame"] <= 180
    assert m[0]["end_frame"] - m[0]["start_frame"] >= 60  # long enough to read
    assert out["shots"][0]["start_frame"] == 0 and out["shots"][0]["type"] != "meme"  # hook still opens the video
    assert meme.insert(out, props)["shots"] == out["shots"]  # idempotent
