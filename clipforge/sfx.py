"""Sound effects for cuts and reactions. Synthesized here (original, royalty-free) into assets/sfx/<name>.wav.

Drop your own file with the same name (wav/mp3) into assets/sfx/ to override any of them.
"""
from __future__ import annotations

import shutil
import wave
from pathlib import Path

import numpy as np

from .config import ROOT

SFX_DIR = ROOT / "assets" / "sfx"
SR = 48000
NAMES = ["whoosh", "boom", "ding", "alarm", "glitch", "pop", "cash", "riser"]
VOLUME = {"whoosh": 0.45, "boom": 0.7, "ding": 0.35, "alarm": 0.3, "glitch": 0.4, "pop": 0.5, "cash": 0.4, "riser": 0.35}


def _t(sec: float) -> np.ndarray:
    return np.arange(int(SR * sec)) / SR


def _bandpass_sweep(x: np.ndarray, f: np.ndarray, q: float = 1.2) -> np.ndarray:
    """State-variable band-pass with a per-sample centre frequency."""
    y, low, band = np.zeros_like(x), 0.0, 0.0
    damp = 1.0 / q
    for i in range(len(x)):
        g = 2 * np.sin(np.pi * min(f[i], SR / 6) / SR)
        high = x[i] - low - damp * band
        band += g * high
        low += g * band
        y[i] = band
    return y


def _env(n: int, attack: float, decay: float) -> np.ndarray:
    a = int(SR * attack)
    e = np.ones(n)
    if a:
        e[:a] = np.linspace(0, 1, a)
    e[a:] = np.exp(-np.arange(n - a) / (SR * decay))
    return e


def _norm(x: np.ndarray, peak: float = 0.9) -> np.ndarray:
    m = np.max(np.abs(x)) or 1.0
    return x / m * peak


def synth(name: str, rng: np.random.Generator) -> np.ndarray:
    if name == "whoosh":
        t = _t(0.6)
        f = 250 * (14 ** np.sin(np.pi * t / t[-1]) )  # up then down
        x = _bandpass_sweep(rng.standard_normal(len(t)), f, 1.6)
        return _norm(x * np.sin(np.pi * (t / t[-1]) ** 0.7) ** 2)
    if name == "boom":
        t = _t(1.3)
        f = 38 + 110 * np.exp(-t * 9)
        body = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 2.6)
        click = rng.standard_normal(len(t)) * np.exp(-t * 60) * 0.6
        rumble = _bandpass_sweep(rng.standard_normal(len(t)), np.full(len(t), 90.0), 0.8) * np.exp(-t * 4) * 0.8
        return _norm(np.tanh(2.2 * (body + click + rumble)))
    if name == "ding":
        t = _t(1.1)
        x = sum(a * np.sin(2 * np.pi * f * t) * np.exp(-t * d) for f, a, d in [(1318, 1, 3.2), (2637, .35, 5), (3637, .18, 7), (5274, .08, 9)])
        return _norm(x * _env(len(t), 0.002, 10))
    if name == "alarm":
        t = _t(0.95)
        f = np.where((t * 6.5).astype(int) % 2 == 0, 960.0, 720.0)
        x = np.tanh(4 * np.sin(2 * np.pi * np.cumsum(f) / SR))
        e = np.clip(t / 0.02, 0, 1) * np.clip((t[-1] - t) / 0.12, 0, 1)
        return _norm(x * e, 0.75)
    if name == "glitch":
        t = _t(0.42)
        out = np.zeros(len(t))
        sl = int(SR * 0.028)
        for k in range(0, len(t), sl):
            if rng.random() < 0.72:
                seg = len(out[k:k + sl])
                kind = rng.integers(3)
                if kind == 0:
                    s = rng.standard_normal(seg)
                elif kind == 1:
                    s = np.sign(np.sin(2 * np.pi * rng.uniform(200, 2400) * np.arange(seg) / SR))
                else:
                    s = np.repeat(rng.standard_normal(seg // 24 + 1), 24)[:seg]
                out[k:k + sl] = s * rng.uniform(.4, 1)
        return _norm(np.round(out * 6) / 6, 0.8)
    if name == "pop":
        t = _t(0.14)
        f = 300 + 900 * np.exp(-t * 40)
        return _norm(np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 32))
    if name == "cash":
        t = _t(0.9)
        rattle = _bandpass_sweep(rng.standard_normal(len(t)), np.full(len(t), 5200.0), 3) * np.exp(-t * 30) * 0.6
        bell = np.zeros(len(t))
        k = int(SR * 0.09)
        tb = t[: len(t) - k]
        bell[k:] = sum(a * np.sin(2 * np.pi * f * tb) * np.exp(-tb * d) for f, a, d in [(2093, 1, 4), (2637, .8, 4.5), (4186, .3, 7)])
        return _norm(rattle + bell)
    if name == "riser":
        t = _t(1.2)
        f = 180 * (12 ** (t / t[-1]))
        saw = 2 * ((np.cumsum(f) / SR) % 1) - 1
        noise = _bandpass_sweep(rng.standard_normal(len(t)), f * 3, 2)
        e = (t / t[-1]) ** 2
        return _norm((0.35 * saw + noise) * e)
    raise KeyError(name)


def _write_wav(path: Path, x: np.ndarray) -> None:
    pcm = (np.clip(x, -1, 1) * 32767).astype(np.int16)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())


def source(name: str) -> Path | None:
    for ext in (".wav", ".mp3"):
        p = SFX_DIR / f"{name}{ext}"
        if p.exists():
            return p
    return None


def ensure_library() -> None:
    SFX_DIR.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(7)
    for n in NAMES:
        if source(n) is None:
            _write_wav(SFX_DIR / f"{n}.wav", synth(n, rng))


def stage(names: set[str], workdir: Path) -> None:
    """Copy the SFX a render needs into <workdir>/sfx/ (Remotion's public dir), keeping the file name the doc references."""
    ensure_library()
    (workdir / "sfx").mkdir(exist_ok=True)
    for n in names:
        src = source(n)
        if src:
            shutil.copy2(src, workdir / "sfx" / f"{n}{src.suffix}")


def file_for(name: str) -> str | None:
    ensure_library()
    src = source(name)
    return f"sfx/{name}{src.suffix}" if src else None
