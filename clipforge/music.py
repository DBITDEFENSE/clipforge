"""AI background music: a per-channel library of instrumental beds generated locally with ACE-Step 1.5 (MIT license).

Tracks land in assets/music/<account>/<mood>__ai-<n>.mp3 and finish.pick_music() prefers them over the shared
assets/music/ folder. One-time model download ~11 GB; a 45 s track takes a few seconds on an RTX 5090.
"""
from __future__ import annotations

import subprocess
import time
import zlib
from pathlib import Path

from .config import MUSIC

MODEL = "ACE-Step/acestep-v15-xl-turbo-diffusers"
MOODS = {
    "tense": "tense and suspenseful, ticking hi-hats, low pulsing bass, 100 BPM",
    "dark": "dark and ominous, minor key, heavy sub bass, slow menacing groove, 88 BPM",
    "driving": "driving and energetic, punchy kick, fast 128 BPM, relentless momentum",
    "curious": "curious and playful, plucky melody, quirky bounce, 108 BPM",
    "upbeat": "upbeat, bright and fun, bouncy groove, 120 BPM",
}
STYLES = {
    "cyber-cowboy": "dusty western twang electric guitar and whistle over dark synthwave pads and hard trap drums, "
                    "spaghetti-western meets cyberpunk",
    "default": "modern electronic tech beat, punchy drums, synth bass, glossy plucks",
}
SUFFIX = "instrumental, no vocals, loopable, mixed for background under a voiceover, clean mix"
DEFAULTS = {"music": "ai", "music_style": ""}  # stored in the account's visuals JSON; music: ai | none

_PIPE = None


def config(account: str | None = None) -> dict:
    from . import accounts

    acc = accounts.get(account) if account else accounts.current()
    v = DEFAULTS | {k: (acc.get("visuals") or {}).get(k) for k in DEFAULTS if (acc.get("visuals") or {}).get(k) is not None}
    v["style_effective"] = v["music_style"] or STYLES.get(acc["id"], STYLES["default"])
    v["account"] = acc["id"]
    return v


def folder(account: str) -> Path:
    return MUSIC / account


def tracks(account: str) -> list[Path]:
    from .finish import AUDIO_EXTS

    d = folder(account)
    return sorted((p for p in d.iterdir() if p.suffix.lower() in AUDIO_EXTS), key=lambda p: p.name) if d.exists() else []


def ready() -> bool:
    hub = Path.home() / ".cache" / "huggingface" / "hub" / ("models--" + MODEL.replace("/", "--"))
    return hub.exists() and (hub / "snapshots").exists() and not any((hub / "blobs").glob("*.incomplete")) \
        and sum(p.stat().st_size for p in hub.rglob("*") if p.is_file()) > 10e9


def prompt_for(mood: str, style: str) -> str:
    return f"{style}, {MOODS.get(mood, MOODS['driving'])}, {SUFFIX}"


def _pipe():
    global _PIPE
    if _PIPE is None:
        import torch
        from diffusers import AceStepPipeline

        _PIPE = AceStepPipeline.from_pretrained(MODEL, torch_dtype=torch.bfloat16).to("cuda")
        _PIPE.vae.enable_tiling()
    return _PIPE


def release() -> None:
    global _PIPE
    if _PIPE is not None:
        import torch

        _PIPE = None
        torch.cuda.empty_cache()


def make_track(prompt: str, dst: Path, seconds: float = 45.0, seed: int = 0) -> Path:
    import soundfile as sf
    import torch

    pipe = _pipe()
    out = pipe(prompt=prompt, lyrics="[Instrumental]", audio_duration=float(seconds),
               generator=torch.Generator(device="cuda").manual_seed(seed))
    wav = dst.with_suffix(".tmp.wav")
    sf.write(str(wav), out.audios[0].T.cpu().float().numpy(), pipe.sample_rate)
    # trim leading silence, gentle fades so the loop point doesn't click, mp3 for size
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(wav), "-af",
                    f"silenceremove=start_periods=1:start_threshold=-45dB,afade=t=in:d=0.05,"
                    f"afade=t=out:st={max(seconds - 1.5, 1):.2f}:d=1.2,loudnorm=I=-14:TP=-1.5:LRA=11,aresample=48000",
                    "-c:a", "libmp3lame", "-b:a", "192k", str(dst)], check=True)
    wav.unlink(missing_ok=True)
    return dst


def build_library(account: str, per_mood: int = 2, seconds: float = 45.0, moods: list[str] | None = None,
                  replace: bool = False) -> list[Path]:
    """Generate `per_mood` tracks for each mood into the channel's folder. Existing tracks are kept unless replace."""
    c = config(account)
    d = folder(account)
    d.mkdir(parents=True, exist_ok=True)
    if replace:
        for p in d.glob("*__ai-*.mp3"):
            p.unlink()
    made = []
    for mood in moods or list(MOODS):
        have = len(list(d.glob(f"{mood}__ai-*.mp3")))
        for i in range(have, per_mood):  # top up to per_mood tracks for this mood
            dst = d / f"{mood}__ai-{i + 1}.mp3"
            t = time.time()
            seed = zlib.crc32(f"{account}|{mood}|{i}|{c['style_effective']}".encode())
            make_track(prompt_for(mood, c["style_effective"]), dst, seconds, seed=seed)
            print(f"  {dst.name} in {time.time() - t:.0f}s", flush=True)
            made.append(dst)
    release()
    return made
