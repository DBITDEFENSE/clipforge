from clipforge import accounts, db, finish, music, videogen


def test_pick_music_prefers_channel_library_and_respects_off(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "t.db")
    monkeypatch.setattr(finish, "MUSIC", tmp_path / "music")
    monkeypatch.setattr(music, "MUSIC", tmp_path / "music")
    accounts.ensure()
    (tmp_path / "music").mkdir()
    (tmp_path / "music" / "tense__shared.mp3").write_bytes(b"x")
    assert finish.pick_music("tense", "s1", "cyber-cowboy").name == "tense__shared.mp3"   # no channel library yet
    lib = tmp_path / "music" / "cyber-cowboy"
    lib.mkdir()
    (lib / "tense__ai-1.mp3").write_bytes(b"x")
    (lib / "upbeat__ai-1.mp3").write_bytes(b"x")
    assert finish.pick_music("tense", "s1", "cyber-cowboy").name == "tense__ai-1.mp3"
    assert finish.pick_music("dark", "s1", "cyber-cowboy").parent == lib                  # any channel track beats shared
    assert finish.pick_music("tense", "s1", "dbit-defense").name == "tense__shared.mp3"
    accounts.update("cyber-cowboy", visuals={"music": "none"})
    assert finish.pick_music("tense", "s1", "cyber-cowboy") is None


def test_music_prompt_and_style_defaults(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "t.db")
    accounts.ensure()
    c = music.config("cyber-cowboy")
    assert "western" in c["style_effective"] and c["music"] == "ai"
    accounts.update("cyber-cowboy", visuals={"music_style": "banjo drill"})
    p = music.prompt_for("tense", music.config("cyber-cowboy")["style_effective"])
    assert p.startswith("banjo drill") and "no vocals" in p and "suspense" in p


def test_local_video_specs_are_valid():
    for model, s in videogen.LOCAL.items():
        assert (s["frames"] - 1) % 4 == 0 and s["h"] % 32 == 0 and s["w"] % 32 == 0 and s["h"] > s["w"]
        assert any(m["id"] == model for m in videogen.MODELS["local_wan"])
