import datetime as dt

from clipforge import accounts, autopilot, db, videogen


def test_find_video_url_shapes():
    assert videogen._find_video_url({"video": {"url": "https://fal.media/x/out.mp4"}}) == "https://fal.media/x/out.mp4"
    assert videogen._find_video_url("https://replicate.delivery/abc/output.mp4") == "https://replicate.delivery/abc/output.mp4"
    assert videogen._find_video_url(["https://replicate.delivery/a.mp4"]) == "https://replicate.delivery/a.mp4"
    assert videogen._find_video_url({"images": [{"url": "https://x/y.png"}]}) is None


def test_generate_caches_logs_cost_and_never_raises(tmp_path, monkeypatch):
    monkeypatch.setattr(videogen, "CACHE", tmp_path / "cache")
    monkeypatch.setattr(videogen, "COSTS", tmp_path / "costs.csv")
    calls = []

    def fake_fal(model, prompt, dst, timeout_s=900):
        calls.append(prompt)
        dst.write_bytes(b"mp4")
        return dst

    monkeypatch.setattr(videogen, "_fal", fake_fal)
    c = {"engine": "fal", "model": "fal-ai/kling-video/v2.1/standard/text-to-video", "max_clips": 2, "cost_per_clip": 0.5}
    a = videogen.generate("cowboy at dusk", tmp_path / "a.mp4", "s1", c)
    b = videogen.generate("cowboy at dusk", tmp_path / "b.mp4", "s1", c)  # cached: no second paid call
    assert a and b and len(calls) == 1 and "Kling" in a[1]
    assert len((tmp_path / "costs.csv").read_text().strip().splitlines()) == 2  # header + one paid clip

    def boom(*a, **k):
        raise RuntimeError("model down")

    monkeypatch.setattr(videogen, "_fal", boom)
    assert videogen.generate("something else", tmp_path / "c.mp4", "s1", c) is None
    assert videogen.generate("x", tmp_path / "d.mp4", "s1", {"engine": "pexels", "model": ""}) is None


def test_autopilot_follow_only_picks_up_new_uploads(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "t.db")
    accounts.ensure()
    feed = [{"id": f"v{i}", "title": f"t{i}", "url": f"https://youtu.be/v{i}"} for i in (3, 2, 1)]
    monkeypatch.setattr(autopilot, "latest", lambda url, n=8: ("Chan", list(feed)))
    autopilot.add_source("cyber-cowboy", "@chan")
    assert autopilot.new_uploads("cyber-cowboy", 5) == []          # existing uploads are not backfilled
    feed.insert(0, {"id": "v4", "title": "t4", "url": "https://youtu.be/v4"})
    new = autopilot.new_uploads("cyber-cowboy", 5)
    assert [x["id"] for x in new] == ["v4"]
    assert autopilot.new_uploads("cyber-cowboy", 5) == []          # never processed twice
    accounts.update("cyber-cowboy", autopilot={"enabled": True, "time": "07:00"})
    morning = dt.datetime(2030, 1, 1, 8, 0)
    assert autopilot.due("cyber-cowboy", morning)
    autopilot.mark_ran("cyber-cowboy", morning)
    assert not autopilot.due("cyber-cowboy", morning)              # once per day
    assert not autopilot.due("cyber-cowboy", dt.datetime(2030, 1, 2, 6, 0))  # not before the set time
