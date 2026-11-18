"""Voice: script -> vo.mp3 + words.json (one entry per script token, original spelling).

Providers:
  elevenlabs  your voice clone via /with-timestamps (character alignment -> word times)
  take        your own recording at takes/<short_id>.(wav|mp3|m4a), force-aligned with WhisperX
  say         Windows built-in TTS, force-aligned. Offline pipeline testing only; sounds robotic.

Pronunciations (config/pronunciations.yaml) change what is SPOKEN; captions keep the original token.
"""
from __future__ import annotations

import base64
import difflib
import json
import re
import subprocess
from pathlib import Path

import httpx

from .config import TAKES, pronunciations, secret, settings
from .schemas import Script, Word

EDGE_PUNCT = ".,!?;:\"'“”‘’()[]—–"


def spoken_alias(token: str) -> str:
    core = token.strip(EDGE_PUNCT)
    if not core:
        return token
    lead = token[: token.index(core)]
    trail = token[token.index(core) + len(core):]
    pron = pronunciations()
    if core in (pron.get("words") or {}):
        return lead + str(pron["words"][core]) + trail
    for rule in pron.get("patterns") or []:
        m = re.match(rule["match"], core)
        if m:
            say = rule["say"]
            for gi, g in enumerate(m.groups(), 1):
                say = say.replace(f"{{g{gi}}}", g)
            return lead + say + trail
    return token


def build_tts_text(tokens: list[str]) -> tuple[str, list[tuple[int, int]]]:
    """Join aliases; return text and each original token's [start, end) char span in it."""
    parts, spans, pos = [], [], 0
    for t in tokens:
        a = spoken_alias(t)
        spans.append((pos, pos + len(a)))
        parts.append(a)
        pos += len(a) + 1
    return " ".join(parts), spans


def words_from_char_alignment(tokens: list[str], text: str, spans: list[tuple[int, int]], alignment: dict) -> list[Word]:
    chars = alignment["characters"]
    starts = alignment["character_start_times_seconds"]
    ends = alignment["character_end_times_seconds"]
    aligned_text = "".join(chars)
    if aligned_text == text:
        idx = {i: i for i in range(len(text))}
    else:  # tolerate small normalisation differences
        idx = {}
        for a, b, size in difflib.SequenceMatcher(None, text, aligned_text, autojunk=False).get_matching_blocks():
            for k in range(size):
                idx[a + k] = b + k
    raw = []
    for tok, (s, e) in zip(tokens, spans):
        mapped = [idx[i] for i in range(s, e) if i in idx and not text[i].isspace()]
        raw.append({"word": tok, "start": starts[mapped[0]] if mapped else None, "end": ends[mapped[-1]] if mapped else None})
    total = ends[-1] if ends else 0.0
    from .transcribe import _interpolate_missing

    _interpolate_missing(raw, total)
    return _to_words(raw)


def _to_words(raw: list[dict]) -> list[Word]:
    out, prev_end = [], 0
    for r in raw:
        s = max(int(round(r["start"] * 1000)), prev_end)
        e = max(int(round(r["end"] * 1000)), s + 40)
        out.append(Word(word=r["word"], start_ms=s, end_ms=e))
        prev_end = s
    return out


def _elevenlabs(text: str, out_mp3: Path) -> dict:
    cfg = settings()["voice"]
    from .accounts import voice_id as _vid

    voice_id = _vid() or secret("ELEVENLABS_VOICE_ID")
    r = httpx.post(
        f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}/with-timestamps",
        params={"output_format": cfg["output_format"]},
        headers={"xi-api-key": secret("ELEVENLABS_API_KEY"), "Content-Type": "application/json"},
        json={
            "text": text,
            "model_id": cfg["model_id"],
            "voice_settings": {"stability": cfg["stability"], "similarity_boost": cfg["similarity_boost"],
                               "style": cfg["style"], "speed": cfg["speed"], "use_speaker_boost": True},
        },
        timeout=180,
    )
    if r.status_code != 200:
        raise RuntimeError(f"ElevenLabs {r.status_code}: {r.text[:300]}")
    data = r.json()
    out_mp3.write_bytes(base64.b64decode(data["audio_base64"]))
    return data["alignment"]


def _say(text: str, out_wav: Path) -> None:
    txt = out_wav.with_suffix(".txt")
    txt.write_text(text, encoding="utf-8")
    ps = (
        "Add-Type -AssemblyName System.Speech; $s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
        f"$s.Rate = 2; $s.SetOutputToWaveFile('{out_wav}'); "
        f"$s.Speak([IO.File]::ReadAllText('{txt}')); $s.Dispose()"
    )
    subprocess.run(["powershell", "-NoProfile", "-Command", ps], check=True)


def _to_mp3(src: Path, dst: Path) -> None:
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(src), "-ac", "1", "-ar", "44100", "-b:a", "192k", str(dst)], check=True)


def _align_tokens(audio: Path, tokens: list[str]) -> list[Word]:
    """Force-align alias words, then fold back to original tokens."""
    from .transcribe import align_known_text

    alias_words, owner = [], []
    for ti, t in enumerate(tokens):
        for aw in spoken_alias(t).split():
            alias_words.append(aw)
            owner.append(ti)
    aligned = align_known_text(audio, " ".join(alias_words))
    raw = [{"word": t, "start": None, "end": None} for t in tokens]
    for a, ti in zip(aligned, owner):
        r = raw[ti]
        r["start"] = a["start"] if r["start"] is None else min(r["start"], a["start"])
        r["end"] = a["end"] if r["end"] is None else max(r["end"], a["end"])
    return _to_words(raw)


def synthesize(script: Script, short_id: str, workdir: Path, provider: str | None = None) -> list[Word]:
    provider = provider or settings()["voice"]["provider"]
    tokens = script.spoken_text().split()
    mp3 = workdir / "vo.mp3"
    if provider == "elevenlabs":
        text, spans = build_tts_text(tokens)
        alignment = _elevenlabs(text, mp3)
        words = words_from_char_alignment(tokens, text, spans, alignment)
    elif provider == "take":
        take = next((p for ext in (".wav", ".mp3", ".m4a") if (p := TAKES / f"{short_id}{ext}").exists()), None)
        if take is None:
            raise FileNotFoundError(f"no take found at {TAKES}/{short_id}.wav|mp3|m4a")
        _to_mp3(take, mp3)
        words = _align_tokens(mp3, tokens)
    elif provider == "say":
        wav = workdir / "vo_say.wav"
        _say(build_tts_text(tokens)[0], wav)
        _to_mp3(wav, mp3)
        words = _align_tokens(mp3, tokens)
    else:
        raise ValueError(f"unknown voice provider {provider!r}")
    if len(words) != len(tokens):
        raise RuntimeError(f"voice produced {len(words)} words for {len(tokens)} tokens")
    (workdir / "words.json").write_text(json.dumps([w.model_dump() for w in words], indent=1), encoding="utf-8")
    return words
