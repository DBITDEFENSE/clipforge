import json

import pytest

from clipforge import launcher


def test_is_newer_compares_numerically():
    assert launcher.is_newer("0.10.0", "0.9.3")
    assert launcher.is_newer("1.0", "0.9.9")
    assert not launcher.is_newer("0.1.0", "0.1.0")
    assert not launcher.is_newer("0.1.0", "0.2.0")
    assert not launcher.is_newer("", "0.1.0")          # unknown latest never offers an update


def test_clean_news_drops_junk_and_sorts_newest_first():
    raw = {"news": [{"date": "2026-01-02", "title": "old"}, {"title": ""}, "nope", {"date": "2026-03-04", "title": "new", "body": 5}]}
    out = launcher.clean_news(raw)
    assert [n["title"] for n in out] == ["new", "old"]
    assert out[0]["body"] == "5" and set(out[0]) == {"date", "title", "body", "tag", "version"}
    assert launcher.clean_news("garbage") == [] and launcher.clean_news({"news": None}) == []


def test_fetch_remote_reads_version_and_news():
    pages = {"pyproject.toml": '[project]\nversion = "0.3.0"\n', "news.json": json.dumps({"news": [{"date": "2026-11-22", "title": "hi"}]})}
    got = launcher.fetch_remote("o/r", "main", get=lambda url: pages[url.rsplit("/", 1)[1]])
    assert got["latest"] == "0.3.0" and got["news"][0]["title"] == "hi"


def test_fetch_remote_survives_missing_news_but_not_missing_version():
    def only_version(url):
        if url.endswith("news.json"):
            raise RuntimeError("404")
        return '[project]\nversion = "0.3.0"\n'

    assert launcher.fetch_remote("o/r", "main", get=only_version) == {"latest": "0.3.0", "news": []}
    with pytest.raises(RuntimeError):
        launcher.fetch_remote("o/r", "main", get=lambda url: (_ for _ in ()).throw(RuntimeError("404")))


def test_source_rejects_malformed_repo(monkeypatch):
    monkeypatch.setattr(launcher, "settings", lambda: {"launcher": {"repo": "https://evil.example/x y", "branch": "main"}})
    assert launcher.source() == ("", "main")
    monkeypatch.setattr(launcher, "settings", lambda: {"launcher": {"repo": "owner/name", "branch": "master"}})
    assert launcher.source() == ("owner/name", "master")
    monkeypatch.setattr(launcher, "settings", lambda: {})
    assert launcher.source() == ("", "main")


def test_shipped_news_file_is_valid():
    assert launcher.local_news(), "news.json at the repo root should have at least one well-formed item"
