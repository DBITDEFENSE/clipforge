from pathlib import Path

from clipforge.schemas import Script
from clipforge.write import problems

FIXTURE = Path(__file__).parent / "fixtures" / "uefi_script.json"


def test_fixture_script_passes_checks():
    s = Script.model_validate_json(FIXTURE.read_text(encoding="utf-8"))
    assert problems(s) == []
    assert s.hooks[0].spoken == s.beats[0].text


def test_checks_catch_length_and_structure():
    s = Script.model_validate_json(FIXTURE.read_text(encoding="utf-8"))
    s.beats = s.beats[:2]  # too short, no 'how', no punch
    errs = " ".join(problems(s))
    assert "words" in errs and "how" in errs and "punch" in errs
