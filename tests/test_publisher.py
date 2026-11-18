"""Publish lifecycle against fake platform clients (no network, temp DB)."""
import datetime as dt
import json

import pytest

from clipforge import db, publisher, schedule


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "t.db")
    monkeypatch.setattr(schedule, "OUT", tmp_path / "out")
    for mod in (publisher, schedule):
        monkeypatch.setattr(mod, "WORK", tmp_path / "work")
    sdir = tmp_path / "work" / "shorts" / "s1"
    sdir.mkdir(parents=True)
    (sdir / "script.json").write_text(json.dumps({"title": "T", "post": {"caption": "cap", "hashtags": ["#a"], "pinned_comment": ""}}))
    out = tmp_path / "out" / "d" / "s1"
    out.mkdir(parents=True)
    (out / "final.mp4").write_bytes(b"x" * 100)
    db.upsert_short("s1", "s1", "b", "done", out_dir=str(out))
    calls = {"yt": [], "tt": [], "status": "PROCESSING_UPLOAD"}

    class YT:
        connected = staticmethod(lambda: True)

        @staticmethod
        def upload(mp4, title, desc, tags, when, synthetic_media=True):
            calls["yt"].append((title, when))
            return {"id": "v1", "url": "https://youtube.com/shorts/v1", "scheduled": when > dt.datetime.now(dt.timezone.utc)}

    class TT:
        connected = staticmethod(lambda: True)
        creator_info = staticmethod(lambda: {"privacy_level_options": ["SELF_ONLY", "PUBLIC_TO_EVERYONE"]})

        @staticmethod
        def post(mp4, caption, privacy, *a):
            calls["tt"].append((caption, privacy))
            return "pub1"

        status = staticmethod(lambda pid: {"status": calls["status"], "publicaly_available_post_id": [123]})

    monkeypatch.setattr(publisher, "youtube", YT)
    monkeypatch.setattr(publisher, "tiktok", TT)
    return calls


def targets():
    return {"youtube": {"title": "YT title", "description": "d"},
            "tiktok": {"caption": "tt cap", "privacy": "SELF_ONLY", "consent": True}}


def test_future_slot_youtube_uploads_now_tiktok_waits(env):
    slot = (schedule.now() + dt.timedelta(hours=3)).replace(microsecond=0).isoformat()
    publisher.approve("s1", slot, targets())
    publisher.tick()
    p = publisher.posts_for("s1")
    assert env["yt"] and p["youtube"]["status"] == "scheduled"      # uploaded with publishAt
    assert not env["tt"] and p["tiktok"]["status"] == "queued"      # not due yet
    assert "YT title" not in (schedule.OUT / "queue.csv").read_text() and "scheduled" in (schedule.OUT / "queue.csv").read_text()


def test_due_tiktok_posts_then_goes_live(env):
    slot = (schedule.now() - dt.timedelta(minutes=1)).replace(microsecond=0).isoformat()
    publisher.approve("s1", slot, {"tiktok": targets()["tiktok"]})
    publisher.tick()
    assert env["tt"] == [("tt cap", "SELF_ONLY")]
    assert publisher.posts_for("s1")["tiktok"]["status"] == "uploading"
    env["status"] = "PUBLISH_COMPLETE"
    publisher.tick()
    t = publisher.posts_for("s1")["tiktok"]
    assert t["status"] == "posted" and t["url"].endswith("/123")
    publisher.tick()
    assert len(env["tt"]) == 1                                       # never double-posts


def test_tiktok_requires_consent_and_privacy(env):
    slot = schedule.next_free().isoformat()
    with pytest.raises(ValueError):
        publisher.approve("s1", slot, {"tiktok": {"privacy": "SELF_ONLY"}})
    with pytest.raises(ValueError):
        publisher.approve("s1", slot, {"tiktok": {"consent": True, "privacy": ""}})
    with pytest.raises(ValueError):
        publisher.approve("s1", slot, {"tiktok": {"consent": True, "privacy": "SELF_ONLY", "branded_content": True}})


def test_unapprove_reports_already_uploaded(env):
    slot = (schedule.now() + dt.timedelta(hours=3)).replace(microsecond=0).isoformat()
    publisher.approve("s1", slot, targets())
    publisher.tick()
    notes = publisher.unapprove("s1")
    assert any("youtube" in n for n in notes)                         # can't silently un-upload
    assert publisher.posts_for("s1")["tiktok"]["status"] == "canceled"
