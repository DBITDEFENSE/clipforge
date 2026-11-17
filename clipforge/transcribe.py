"""WhisperX transcription (word timestamps) on the local GPU, plus forced alignment of known text."""
from __future__ import annotations

import gc
import json
from functools import lru_cache
from pathlib import Path

from rich.console import Console

from .config import settings

console = Console()


def _device() -> tuple[str, str]:
    import torch

    return ("cuda", "float16") if torch.cuda.is_available() else ("cpu", "int8")


@lru_cache
def _align_model(lang: str):
    import whisperx

    device, _ = _device()
    return whisperx.load_align_model(language_code=lang, device=device)


def transcribe(audio_path: Path, out_path: Path) -> dict:
    """audio -> {"segments": [{start,end,text,words:[{word,start,end}]}], "language": ...}"""
    if out_path.exists():
        return json.loads(out_path.read_text(encoding="utf-8"))
    import whisperx

    cfg = settings()["transcribe"]
    device, compute = _device()
    audio = whisperx.load_audio(str(audio_path))
    try:
        model = whisperx.load_model(cfg["model"], device, compute_type=compute, language=cfg.get("language"))
    except Exception as e:  # e.g. CTranslate2 build without kernels for this GPU
        console.print(f"[yellow]GPU ASR failed ({e}); falling back to CPU int8[/]")
        device, compute = "cpu", "int8"
        model = whisperx.load_model(cfg["model"], device, compute_type=compute, language=cfg.get("language"))
    result = model.transcribe(audio, batch_size=cfg["batch_size"] if device == "cuda" else 4)
    del model
    gc.collect()
    lang = result.get("language") or cfg.get("language") or "en"
    model_a, meta = _align_model(lang)
    aligned = whisperx.align(result["segments"], model_a, meta, audio, _device()[0], return_char_alignments=False)
    out = {
        "language": lang,
        "segments": [
            {"start": s.get("start"), "end": s.get("end"), "text": s.get("text", "").strip(),
             "words": [{"word": w.get("word"), "start": w.get("start"), "end": w.get("end")} for w in s.get("words", [])]}
            for s in aligned["segments"]
        ],
    }
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    return out


def align_known_text(audio_path: Path, text: str, lang: str = "en") -> list[dict]:
    """Force-align a known script to audio. Returns one {word,start,end} per whitespace token of `text`."""
    import whisperx

    audio = whisperx.load_audio(str(audio_path))
    dur = len(audio) / 16000
    model_a, meta = _align_model(lang)
    res = whisperx.align([{"start": 0.0, "end": dur, "text": text}], model_a, meta, audio, _device()[0],
                         return_char_alignments=False)
    aligned = [w for s in res["segments"] for w in s.get("words", [])]
    tokens = text.split()
    if len(aligned) != len(tokens):
        raise RuntimeError(f"alignment produced {len(aligned)} words for {len(tokens)} tokens")
    out = [{"word": t, "start": a.get("start"), "end": a.get("end")} for t, a in zip(tokens, aligned)]
    _interpolate_missing(out, dur)
    return out


def _interpolate_missing(words: list[dict], dur: float) -> None:
    """Numbers/symbols sometimes come back without times; spread them between known neighbours."""
    n = len(words)
    i = 0
    while i < n:
        if words[i]["start"] is not None and words[i]["end"] is not None:
            i += 1
            continue
        j = i
        while j < n and (words[j]["start"] is None or words[j]["end"] is None):
            j += 1
        lo = words[i - 1]["end"] if i > 0 else 0.0
        hi = words[j]["start"] if j < n else dur
        step = (hi - lo) / (j - i)
        for k in range(i, j):
            words[k]["start"] = lo + step * (k - i)
            words[k]["end"] = lo + step * (k - i + 1)
        i = j


def transcript_for_prompt(video_id: str, title: str, tr: dict) -> str:
    """Compact, timestamped transcript block for Claude."""
    lines = [f'[VIDEO {video_id}] "{title}"']
    for s in tr["segments"]:
        t = int(s["start"] or 0)
        lines.append(f"[{t // 60:02d}:{t % 60:02d}] {s['text']}")
    return "\n".join(lines)
