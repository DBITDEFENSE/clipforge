from clipforge.tts_local import drawl_phonemes as d


def test_drawl_rules():
    assert d("tˈIm", "time") == "tˈaːm"          # /aɪ/ monophthong
    assert d("ɹˈIt", "Right") == "ɹˈIt"          # kept before voiceless consonants
    assert d("ɹˈIdɪŋ", "riding").endswith("ɪn")  # g-dropping
    assert d("tˈɛn", "ten") == "tˈɪn"            # pin-pen merger
    assert "æʊ" in d("tˈWn", "town")
    assert d("tˈIm", "time", "off") == "tˈIm"
    assert "ː" not in d("tˈɛn", "ten", "light")  # no stretch in light mode
