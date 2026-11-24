import base64

import pytest

from clipforge import accounts, algo, db, ingest, mine, templates, videogen
from clipforge.schemas import Story


def vid(i, feed="recommended", pos=0, channel="Chan", duration=600, **kw):
    return {"id": i, "title": kw.pop("title", f"video {i}"), "channel": channel, "channel_id": "", "duration": duration, "views": 1,
            "live": False, "short": False, "url": f"https://www.youtube.com/watch?v={i}", "feed": feed, "pos": pos} | kw


CFG = algo.clean({})


def test_clean_clamps_and_defaults():
    c = algo.clean({"browser": "netscape", "feeds": ["nope"], "shorts": 9999, "min_minutes": 50, "max_minutes": 10, "boost": "a, b ,", "daily": 1})
    assert c["browser"] == "" and c["feeds"] == algo.DEFAULTS["feeds"] and c["shorts"] == 200
    assert c["max_minutes"] > c["min_minutes"] and c["boost"] == ["a", "b"] and c["daily"] is True
    assert algo.clean(None)["shorts"] == 15


def test_rank_filters_and_orders():
    cands = [vid("a", pos=5), vid("b", pos=0), vid("short", short=True), vid("live", live=True), vid("tiny", duration=30),
             vid("long", duration=4 * 3600), vid("seen"), vid("blocked", title="3 hour PODCAST"), vid("nolen", duration=None, pos=9)]
    out = algo.rank(cands, {}, CFG | {"block": ["podcast"]}, {"seen"})
    assert [e["id"] for e in out] == ["b", "a", "nolen"]


def test_rank_prefers_channels_you_watch_and_boost_words():
    cands = [vid("top", pos=0, channel="Stranger"), vid("fav", pos=6, channel="Fav"), vid("kw", pos=8, channel="X", title="kernel exploit deep dive")]
    assert algo.rank(cands, {"channels": {"Fav": 30}}, CFG, set())[0]["id"] == "fav"
    assert algo.rank(cands, {}, CFG | {"boost": ["kernel"]}, set())[0]["id"] == "kw"
    both = algo.rank([vid("x", "recommended", 3), vid("x", "subscriptions", 3), vid("y", "recommended", 3)], {}, CFG, set())
    assert [e["id"] for e in both] == ["x", "y"]  # in two feeds: one entry, ranked higher


def test_spread_caps_one_channel():
    ranked = [vid(str(i), channel="Same") for i in range(5)] + [vid("o", channel="Other")]
    assert [e["id"] for e in algo.spread(ranked, 3)] == ["0", "1", "o"]


def test_cookies_are_validated_and_scoped_to_youtube(tmp_path, monkeypatch):
    monkeypatch.setattr(algo, "COOKIES", tmp_path)
    with pytest.raises(ValueError):
        algo.save_cookies("ch", "not a cookie file")
    txt = ("# Netscape HTTP Cookie File\n.youtube.com\tTRUE\t/\tTRUE\t0\tSID\tabc\n.bank.example\tTRUE\t/\tTRUE\t0\tsession\tsecret\n"
           "#HttpOnly_.google.com\tTRUE\t/\tTRUE\t0\tHSID\tdef\n")
    assert algo.save_cookies("ch", txt) == 2
    saved = algo.cookie_file("ch").read_text()
    assert "bank.example" not in saved and "SID\tabc" in saved
    assert algo.cookie_file("../../evil").parent == tmp_path  # account ids cannot escape the folder


def test_auth_opts_prefers_file_then_browser(tmp_path, monkeypatch):
    monkeypatch.setattr(algo, "COOKIES", tmp_path)
    assert algo.auth_opts("ch", CFG) == {}
    assert algo.auth_opts("ch", CFG | {"browser": "firefox", "profile": ""}) == {"cookiesfrombrowser": ("firefox", None, None, None)}
    algo.cookie_file("ch").write_text("x")
    assert algo.auth_opts("ch", CFG | {"browser": "firefox"}) == {"cookiefile": str(algo.cookie_file("ch"))}


def test_explain_turns_locked_cookies_into_advice():
    assert "Firefox" in algo.explain(RuntimeError("Failed to decrypt with DPAPI"))
    assert "signed in" in algo.explain(RuntimeError("ERROR: [youtube:tab] Sign in to confirm"))


def test_videos_needed(monkeypatch):
    monkeypatch.setattr(algo, "settings", lambda: {"plan": {"per_video": 3}})
    assert algo.videos_needed(15) == 5 and algo.videos_needed(1) == 1 and algo.videos_needed(16) == 6


def story(cat="tech", topic="t", angle="a", facts=(), cluster="c"):
    return Story.model_construct(topic=topic, cluster=cluster, category=cat, angle=angle, how_it_works="", key_facts=list(facts), sources=[])


def test_templates_catalog_is_well_formed():
    ids = [t["id"] for t in templates.TEMPLATES]
    assert len(ids) == len(set(ids)) >= 12
    for t in templates.TEMPLATES:
        assert all(t.get(k) for k in ("name", "desc", "write", "direct")) and isinstance(t["keys"], list)


def test_template_choice_matches_story_and_respects_settings():
    all_on = templates.clean(None)
    assert templates.choose(story("gaming", "Boss speedrun glitch found"), all_on)["id"] == "gameplay_commentary"
    assert templates.choose(story("tech", "How to install the tool", "step by step setup guide"), all_on)["id"] == "tutorial_steps"
    assert templates.choose(story("gaming", "Boss speedrun"), templates.clean({"mode": "fixed", "fixed": "top_3"}))["id"] == "top_3"
    only = templates.clean({"enabled": ["versus", "timeline", "bogus"]})
    assert only["enabled"] == ["versus", "timeline"] and templates.choose(story("gaming", "Boss speedrun"), only)["id"] in only["enabled"]
    picks = {templates.choose(story("other", "zzz", "qqq", cluster=f"c{i}"), all_on)["id"] for i in range(40)}
    assert len(picks) > 3  # stories nothing matches rotate through formats


def test_video_chain_falls_through_to_the_next_engine(tmp_path, monkeypatch):
    monkeypatch.setattr(videogen, "CACHE", tmp_path / "cache")
    monkeypatch.setattr(videogen, "COSTS", tmp_path / "costs.csv")
    monkeypatch.setattr(videogen, "_DOWN", set())
    for k in ("FAL_KEY", "GEMINI_API_KEY"):
        monkeypatch.setenv(k, "test")
    for k in ("HF_API_KEY_ID", "HF_API_KEY_SECRET"):
        monkeypatch.delenv(k, raising=False)
    tried = []

    def fal(model, prompt, dst, timeout_s=900):
        tried.append("fal")
        raise RuntimeError("fal submit 429: rate limit")

    def gemini(model, prompt, dst):
        tried.append("gemini")
        dst.write_bytes(b"mp4")
        return dst

    def higgs(*a, **k):
        raise AssertionError("no key: must be skipped")

    monkeypatch.setattr(videogen, "_fal", fal)
    monkeypatch.setattr(videogen, "_gemini", gemini)
    monkeypatch.setattr(videogen, "_higgsfield", higgs)
    c = videogen.DEFAULTS | {"engine": "fal", "model": "m", "fallbacks": ["higgsfield", "gemini", "pexels"]}
    assert [e for e, _ in videogen.chain(c)] == ["fal", "higgsfield", "gemini"]
    got = videogen.generate("a cowboy", tmp_path / "a.mp4", "s1", c)
    assert got and "Gemini" in got[1] and tried == ["fal", "gemini"]
    videogen.generate("another prompt", tmp_path / "b.mp4", "s1", c)
    assert tried == ["fal", "gemini", "gemini"]  # fal hit its limit: skipped for the rest of the run
    assert videogen.chain(videogen.DEFAULTS | {"engine": "pexels", "fallbacks": ["fal"]}) == []


def test_gemini_reads_inline_video(tmp_path, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    seen = {}

    class R:
        status_code = 200

        def json(self):
            return {"status": "completed", "steps": [{"type": "model_output", "content": [{"type": "video", "data": base64.b64encode(b"MP4!").decode()}]}]}

    def post(url, headers, json, timeout):
        seen.update(url=url, body=json, key=headers["x-goog-api-key"])
        return R()

    monkeypatch.setattr(videogen.httpx, "post", post)
    out = videogen._gemini("gemini-omni-1.2-flash", "p", tmp_path / "g.mp4")
    assert out.read_bytes() == b"MP4!" and seen["body"]["response_format"]["aspect_ratio"] == "9:16" and seen["key"] == "k"


def test_higgsfield_polls_then_downloads(tmp_path, monkeypatch):
    monkeypatch.setenv("HF_API_KEY_ID", "id")
    monkeypatch.setenv("HF_API_KEY_SECRET", "sec")
    monkeypatch.setattr(videogen.time, "sleep", lambda s: None)
    states = iter([{"status": "in_progress"}, {"status": "completed", "video": {"url": "https://cdn.example/v.mp4"}}])
    seen = {}

    class R:
        def __init__(self, d):
            self.status_code, self._d = 200, d

        def json(self):
            return self._d

    def post(url, headers, json, timeout):
        seen.update(url=url, auth=headers["Authorization"], body=json)
        return R({"status": "queued", "request_id": "r1", "status_url": "https://api.higgsfield.ai/requests/r1/status"})

    monkeypatch.setattr(videogen.httpx, "post", post)
    monkeypatch.setattr(videogen.httpx, "get", lambda url, headers, timeout: R(next(states)))
    monkeypatch.setattr(videogen, "_download", lambda url, dst, headers=None: seen.update(dl=url) or dst)
    videogen._higgsfield("bytedance/seedance-2.0/text-to-video", "p", tmp_path / "h.mp4")
    assert seen["auth"] == "Key id:sec" and seen["dl"] == "https://cdn.example/v.mp4"
    assert seen["url"].endswith("/bytedance/seedance-2.0/text-to-video") and seen["body"]["generate_audio"] is False


def test_sponsor_postprocessors_follow_settings(monkeypatch):
    pps = ingest.sponsor_postprocessors(["sponsor", "selfpromo"])
    assert [p["key"] for p in pps] == ["SponsorBlock", "ModifyChapters"] and pps[1]["remove_sponsor_segments"] == {"sponsor", "selfpromo"}
    assert ingest.sponsor_postprocessors([]) == []
    monkeypatch.setattr(ingest, "settings", lambda: {"ingest": {"skip_segments": ["sponsor", "made_up"]}})
    assert ingest.skip_categories() == ["sponsor"]
    monkeypatch.setattr(ingest, "settings", lambda: {})
    assert ingest.skip_categories() == ingest.SKIP_DEFAULT


def test_pick_hits_an_exact_target(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "t.db")
    accounts.ensure()
    monkeypatch.setattr(mine, "score", lambda st: 1.0)
    monkeypatch.setattr(db, "save_story", lambda *a, **k: None)
    monkeypatch.setattr(Story, "model_dump_json", lambda self, **k: "{}")
    from types import SimpleNamespace

    def st(i, v):
        s = story(cluster=f"c{i}")
        s.sources = [SimpleNamespace(video_id=v, timestamp="00:10")]
        return s

    stories = [st(i, f"v{i % 2}") for i in range(12)]
    assert len(mine.pick("b", stories, 2, target=8)) == 8      # 2 videos x 3 would cap at 6 without the target
    assert len(mine.pick("b", stories, 2)) == 6
    assert len(mine.pick("b", stories, 2, target=50)) == 12    # never more than the stories that exist
