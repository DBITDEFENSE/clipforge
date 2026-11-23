from clipforge import voice, voice_lab


def test_el_clean_clamps_and_drops_unknown_keys():
    assert voice.el_clean({"speed": 9, "stability": "-1", "bogus": 1}) == {"speed": 1.2, "stability": 0.0}


def test_presets_are_within_range():
    for p in voice.EL_PRESETS.values():
        assert voice.el_clean(p) == p and set(p) == set(voice.EL_STYLE)


def test_custom_style_gets_its_own_sample_file():
    d = voice.el_defaults()
    assert voice_lab.sample_path("abc").name == "abc.mp3"
    assert voice_lab.sample_path("abc", d).name == "abc.mp3"
    assert voice_lab.sample_path("abc", d | {"style": 0.9 if d["style"] != 0.9 else 0.1}).name != "abc.mp3"


def test_voice_settings_merge_style_over_defaults():
    s = voice.el_voice_settings({"style": 0.9})
    assert s["style"] == 0.9 and s["stability"] == voice.el_defaults()["stability"] and s["use_speaker_boost"] is True
