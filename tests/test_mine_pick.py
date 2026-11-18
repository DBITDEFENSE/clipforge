from clipforge import mine
from clipforge.schemas import Story


def _story(i, vid, cluster=None, hook=8):
    return Story(topic=f"t{i}", cluster=cluster or f"c{i}", category="cyber", key_facts=["f"], angle="a", who_affected="w",
                 how_it_works="h", sources=[{"video_id": vid, "timestamp": "00:01:00"}],
                 scores={"hook": hook, "clarity": 7, "curiosity": 7, "niche_fit": 9})


def test_pick_spreads_across_videos_and_dedupes(monkeypatch):
    monkeypatch.setattr(mine.db, "save_story", lambda *a, **k: None)
    # video A has 6 strong stories, video B has 2 weaker ones; one A story duplicates a cluster
    stories = [_story(i, "A", hook=9) for i in range(6)] + [_story(6, "A", cluster="c0", hook=10)] + [_story(7 + i, "B", hook=5) for i in range(2)]
    picks = mine.pick("b", stories, n_videos=2)
    srcs = [st.sources[0].video_id for _, st, _ in picks]
    assert srcs.count("A") <= mine.settings()["plan"].get("per_video", 3)
    assert srcs.count("B") == 2                                   # weaker video still gets its shorts
    assert len({st.cluster for _, st, _ in picks}) == len(picks)  # no duplicate events
    per_day = mine.settings()["plan"]["per_day"]
    days = [d for *_, d in picks]
    assert max(days.count(d) for d in set(days)) <= per_day


def test_groups_split_large_batches(monkeypatch):
    monkeypatch.setattr(mine, "GROUP_CHARS", 100)
    groups = mine._groups(["x" * 60, "y" * 60, "z" * 30])
    assert [len(g) for g in groups] == [1, 2]
