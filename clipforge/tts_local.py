"""Local TTS (Kokoro-82M, Apache-2.0) on the GPU, with ElevenLabs-style controls and an optional Southern/country drawl.

Controls (all per channel, see voice.local_voice_config):
  kokoro_voice  narrator A            blend_voice / blend  optional narrator B and how much of it (0-1)
  speed         pace                  drawl                off | light | full (accent via phoneme rewrites)
  pitch         semitones (-4..+3)    warmth               0-1: low-mid body + gentle saturation ("grit")
  expressive    0-1: sentence-to-sentence pace/pause variation (like lowering ElevenLabs "stability")
  pause         seconds between sentences

The drawl is a set of misaki phoneme rewrites:
  - /aɪ/ ("I", "time", "ride") -> monophthong [aː]: "Ah", "tahm", "rahd"   (kept before voiceless consonants: "right")
  - "-ing" -> "-in'": "ridin'", "thinkin'"
  - /aʊ/ ("town", "out") -> [æʊ]
  - pin-pen merger: "ten" -> "tin", "them" -> "thim"
  - full: a little extra length on stressed short vowels (the drawl itself)
No credits, no network after the first model download (~330 MB from Hugging Face, cached).
"""
from __future__ import annotations

import random
import re
import subprocess
from functools import lru_cache
from pathlib import Path

import numpy as np

SR = 24000
VOICES = {  # Kokoro American English voices (quality per the model card: heart/bella best female; fenrir/michael/puck best male)
    "am_fenrir": "Fenrir: deep, gravelly (male)",
    "am_michael": "Michael: warm, steady (male)",
    "am_puck": "Puck: brighter, playful (male)",
    "am_onyx": "Onyx: very deep, slow (male)",
    "am_eric": "Eric: plain, conversational (male)",
    "am_echo": "Echo: soft, close (male)",
    "am_liam": "Liam: young, quick (male)",
    "am_adam": "Adam: firm (male)",
    "am_santa": "Santa: jolly, old (male)",
    "af_heart": "Heart: warm, natural (female)",
    "af_bella": "Bella: bright, expressive (female)",
    "af_nicole": "Nicole: breathy, intimate (female)",
    "af_sarah": "Sarah: clear, confident (female)",
    "af_nova": "Nova: crisp (female)",
    "af_sky": "Sky: light (female)",
    "af_river": "River: calm (female)",
    "af_jessica": "Jessica: friendly (female)",
    "af_kore": "Kore: steady (female)",
    "af_aoede": "Aoede: smooth (female)",
    "af_alloy": "Alloy: neutral (female)",
}
PRESETS = {  # one-click starting points for the studio
    "Radio cowboy": {"kokoro_voice": "am_michael", "blend_voice": "am_fenrir", "blend": 0.5, "drawl": "full", "speed": 0.95, "pitch": -1, "warmth": 0.4, "expressive": 0.3, "pause": 0.08},
    "Trail boss": {"kokoro_voice": "am_fenrir", "blend_voice": "am_onyx", "blend": 0.4, "drawl": "full", "speed": 0.9, "pitch": -2, "warmth": 0.6, "expressive": 0.2, "pause": 0.12},
    "Young ranch hand": {"kokoro_voice": "am_puck", "blend_voice": "am_michael", "blend": 0.3, "drawl": "full", "speed": 1.0, "pitch": 0, "warmth": 0.2, "expressive": 0.5, "pause": 0.06},
    "Front-porch storyteller": {"kokoro_voice": "am_onyx", "blend_voice": "am_michael", "blend": 0.5, "drawl": "full", "speed": 0.85, "pitch": -1, "warmth": 0.7, "expressive": 0.35, "pause": 0.15},
    "Country gal": {"kokoro_voice": "af_heart", "blend_voice": "af_bella", "blend": 0.3, "drawl": "full", "speed": 0.97, "pitch": 0, "warmth": 0.3, "expressive": 0.45, "pause": 0.08},
    "Straight news (no accent)": {"kokoro_voice": "am_michael", "blend_voice": "", "blend": 0.0, "drawl": "off", "speed": 1.02, "pitch": 0, "warmth": 0.1, "expressive": 0.2, "pause": 0.06},
}
DEFAULTS = {"kokoro_voice": "am_michael", "blend_voice": "am_fenrir", "blend": 0.5, "speed": 0.95, "drawl": "full",
            "pitch": 0.0, "warmth": 0.3, "expressive": 0.3, "pause": 0.08}
VOICELESS = set("ptkfsθʃʧ")
DRAWL_LEVELS = ("off", "light", "full")


@lru_cache
def _pipeline():
    import torch
    from kokoro import KPipeline

    return KPipeline(lang_code="a", repo_id="hexgrad/Kokoro-82M", device="cuda" if torch.cuda.is_available() else "cpu")


def clean(cfg: dict) -> dict:
    """Validate/clamp a voice config (used by the studio API and the pipeline)."""
    c = DEFAULTS | {k: v for k, v in cfg.items() if k in DEFAULTS}
    legacy = str(c["kokoro_voice"])
    if "," in legacy:  # old "a,b" equal-blend form
        a, b = legacy.split(",", 1)
        c["kokoro_voice"], c["blend_voice"], c["blend"] = a, b, 0.5
    if c["kokoro_voice"] not in VOICES:
        raise ValueError(f"unknown voice {c['kokoro_voice']}")
    if c["blend_voice"] and c["blend_voice"] not in VOICES:
        raise ValueError(f"unknown voice {c['blend_voice']}")
    if c["drawl"] not in DRAWL_LEVELS:
        raise ValueError("drawl must be off, light or full")
    clamp = lambda v, lo, hi: max(lo, min(hi, float(v)))  # noqa: E731
    c.update(blend=clamp(c["blend"], 0, 1), speed=clamp(c["speed"], 0.7, 1.3), pitch=clamp(c["pitch"], -4, 3),
             warmth=clamp(c["warmth"], 0, 1), expressive=clamp(c["expressive"], 0, 1), pause=clamp(c["pause"], 0, 0.4))
    return c


def drawl_phonemes(ps: str, text: str, level: str = "full") -> str:
    """Rewrite one word's misaki phonemes toward a Southern US accent."""
    if level == "off" or not ps:
        return ps
    out = []
    for i, ch in enumerate(ps):
        if ch == "I":  # /aɪ/
            nxt = next((c for c in ps[i + 1:] if c not in "ˈˌː"), "")
            out.append("I" if nxt in VOICELESS else "aː")
        elif ch == "W":  # /aʊ/
            out.append("æʊ")
        else:
            out.append(ch)
    s = "".join(out)
    if text.lower().rstrip(".,!?;:'\"").endswith("ing") and s.endswith("ɪŋ") and len(text) > 4:
        s = s[:-2] + "ɪn"
    s = re.sub(r"ɛ(?=[nm])", "ɪ", s)  # pin-pen merger
    if level == "full":
        s = re.sub(r"ˈ([æɛʌ])(?![ːʊ])", r"ˈ\1ː", s)  # stretch stressed short vowels a touch (not inside the æʊ diphthong)
    return s


def _voice_pack(c: dict):
    pipe = _pipeline()
    a = pipe.load_voice(c["kokoro_voice"])
    if c["blend_voice"] and c["blend"] > 0:
        b = pipe.load_voice(c["blend_voice"])
        return (a * (1 - c["blend"]) + b * c["blend"]).float()
    return a


def synth(text: str, out_wav: Path, cfg: dict | None = None, **legacy) -> Path:
    """Render `text` to a 24 kHz wav (before pitch/warmth; see finish())."""
    import soundfile as sf

    c = clean((cfg or {}) | legacy)
    pipe = _pipeline()
    _, tokens = pipe.g2p(text)
    for t in tokens:
        if t.phonemes:
            t.phonemes = drawl_phonemes(t.phonemes, t.text, c["drawl"])
    rng = random.Random(len(text))  # deterministic per script
    exp = c["expressive"]
    speed = lambda _n: c["speed"] * (1 + rng.uniform(-0.08, 0.08) * exp)  # noqa: E731
    pieces = []
    for r in pipe.generate_from_tokens(tokens, voice=_voice_pack(c), speed=speed):
        if r.audio is None:
            continue
        pieces.append(r.audio.detach().cpu().numpy())
        pieces.append(np.zeros(int(SR * c["pause"] * (1 + rng.uniform(-0.5, 0.5) * exp)), dtype=np.float32))
    if not pieces:
        raise RuntimeError("Kokoro produced no audio")
    sf.write(str(out_wav), np.concatenate(pieces), SR)
    return out_wav


def finish(wav: Path, out: Path, cfg: dict | None = None) -> Path:
    """Pitch + warmth, then encode (mp3 or wav by extension). Pitch shifts timing-neutrally (asetrate + atempo)."""
    c = clean(cfg or {})
    f = []
    if abs(c["pitch"]) >= 0.25:
        r = 2 ** (c["pitch"] / 12)
        f += [f"asetrate={SR * r:.0f}", f"aresample={SR}", f"atempo={1 / r:.5f}"]
    w = c["warmth"]
    if w > 0:
        f += [f"equalizer=f=180:t=q:w=1.1:g={2.5 * w:.2f}", f"equalizer=f=3200:t=q:w=1.4:g={1.2 * w:.2f}",
              f"highshelf=f=9000:g={-2.5 * w:.2f}", f"asoftclip=type=tanh:threshold={1 - 0.35 * w:.2f}"]
    cmd = ["ffmpeg", "-y", "-v", "error", "-i", str(wav)] + (["-af", ",".join(f)] if f else []) + ["-ac", "1", "-ar", "44100"]
    cmd += ["-b:a", "192k"] if out.suffix == ".mp3" else []
    subprocess.run(cmd + [str(out)], check=True)
    return out
