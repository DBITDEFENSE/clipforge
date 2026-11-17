from clipforge.voice import build_tts_text, spoken_alias, words_from_char_alignment


def test_alias_keeps_punctuation_and_applies_patterns():
    assert spoken_alias("CISA,") == "sissa,"
    assert spoken_alias("CVE-2025-1234.") == "C V E 2025 dash 1234."
    assert spoken_alias("hello") == "hello"


def _fake_alignment(text: str, char_ms: int = 50) -> dict:
    return {
        "characters": list(text),
        "character_start_times_seconds": [i * char_ms / 1000 for i in range(len(text))],
        "character_end_times_seconds": [(i + 1) * char_ms / 1000 for i in range(len(text))],
    }


def test_char_alignment_maps_back_to_original_tokens():
    tokens = ["CISA", "flagged", "CVE-2025-1234."]
    text, spans = build_tts_text(tokens)
    words = words_from_char_alignment(tokens, text, spans, _fake_alignment(text))
    assert [w.word for w in words] == tokens            # captions show the original spelling
    assert words[0].start_ms == 0
    assert all(a.start_ms <= b.start_ms for a, b in zip(words, words[1:]))
    # third token's span covers the whole spoken alias "C V E 2025 dash 1234."
    s, e = spans[2]
    assert words[2].start_ms == s * 50 and words[2].end_ms == e * 50


def test_char_alignment_tolerates_normalisation_drift():
    tokens = ["Patch", "it", "today."]
    text, spans = build_tts_text(tokens)
    drifted = _fake_alignment(text.replace("today.", "today"))  # provider dropped the period
    words = words_from_char_alignment(tokens, text, spans, drifted)
    assert len(words) == 3 and words[2].end_ms > words[2].start_ms
