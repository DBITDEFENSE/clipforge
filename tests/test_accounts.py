import json

from clipforge import accounts, db, originality, schedule


def test_accounts_passwords_and_isolation(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "t.db")
    monkeypatch.delenv("CLIPFORGE_ACCOUNT", raising=False)
    accounts.ensure()
    ids = [a["id"] for a in accounts.all_accounts()]
    assert ids == ["dbit-defense", "cyber-cowboy"]
    a = accounts.update("cyber-cowboy", password="s3cret!")
    assert a["password_hash"].startswith("pbkdf2$") and "s3cret" not in a["password_hash"]
    assert accounts.check_password(a, "s3cret!") and not accounts.check_password(a, "nope")
    assert "password_hash" not in accounts.public(a) and accounts.public(a)["has_password"]
    # shorts and slots are per account
    tok = accounts.ACTIVE.set("cyber-cowboy")
    try:
        db.upsert_short("c1", "c1", "b", "done")
        schedule.set_review("c1", "approved", "2030-01-01T09:00:00-05:00")
        assert schedule.taken() == {"2030-01-01T09:00:00-05:00"}
    finally:
        accounts.ACTIVE.reset(tok)
    tok = accounts.ACTIVE.set("dbit-defense")
    try:
        assert schedule.taken() == set()          # the other channel's slot is free here
    finally:
        accounts.ACTIVE.reset(tok)
    with db.connect() as con:
        assert con.execute("SELECT account FROM shorts WHERE id='c1'").fetchone()[0] == "cyber-cowboy"


def test_originality_flags_copied_runs(tmp_path, monkeypatch):
    monkeypatch.setattr(originality, "WORK", tmp_path)
    (tmp_path / "v1").mkdir()
    src = "today microsoft pushed a network change that knocked out outlook for thirty six hours across the planet and nobody noticed"
    (tmp_path / "v1" / "transcript.json").write_text(json.dumps({"segments": [{"text": src}]}))
    own = originality.check("A config push at Microsoft took email down for a day and a half. Bold move, partner.", ["v1"])
    assert own["ok"] and own["copied_share"] == 0
    copied = originality.check("So microsoft pushed a network change that knocked out outlook for thirty six hours. Wild.", ["v1"])
    assert copied["copied_share"] > 0.5 and not copied["ok"] and copied["copied_runs"]
