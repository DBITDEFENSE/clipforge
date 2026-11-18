"""B-roll engines ("video models"), chosen per channel in Studio > Settings > Visuals.

  none       motion graphics only (B-roll shots become kinetic text)
  pexels     licensed stock footage (PEXELS_API_KEY)
  local_wan  Wan 2.1 T2V 1.3B on your GPU via diffusers (Apache-2.0, free; ~29 GB one-time download, ~1-3 min per clip)
  fal        any fal.ai text-to-video model (FAL_KEY): Kling, Veo, Hailuo, Wan 2.2, LTX, Seedance...
  replicate  any Replicate text-to-video model (REPLICATE_API_TOKEN)

Clips are cached by (engine, model, prompt). Paid engines log an estimated cost per clip to data/costs.csv and are
capped by `max_clips` per short. Any failure returns None and the shot falls back to motion graphics.
"""
from __future__ import annotations

import csv
import datetime as dt
import hashlib
import shutil
import time
from pathlib import Path

import httpx

from .config import COSTS, DATA, secret

CACHE = DATA / "videogen_cache"
ENGINES = {
    "none": "Motion graphics only",
    "pexels": "Stock footage (Pexels)",
    "local_wan": "Local AI video: Wan 2.1 (free, your GPU)",
    "fal": "fal.ai video models (paid, your key)",
    "replicate": "Replicate video models (paid, your key)",
}
# Suggested model ids (providers rename/add models often; any text-to-video id works). tier is a rough price class.
MODELS = {
    "fal": [
        {"id": "fal-ai/kling-video/v2.1/standard/text-to-video", "name": "Kling 2.1 Standard", "tier": "$$"},
        {"id": "fal-ai/veo3/fast", "name": "Google Veo 3 Fast", "tier": "$$$"},
        {"id": "fal-ai/minimax/hailuo-02/standard/text-to-video", "name": "MiniMax Hailuo 02", "tier": "$$"},
        {"id": "fal-ai/wan/v2.2-a14b/text-to-video", "name": "Wan 2.2 A14B", "tier": "$"},
        {"id": "fal-ai/ltxv-13b-098-distilled", "name": "LTX-Video 13B distilled", "tier": "$"},
        {"id": "fal-ai/bytedance/seedance/v1/lite/text-to-video", "name": "Seedance 1 Lite", "tier": "$"},
    ],
    "replicate": [
        {"id": "google/veo-3-fast", "name": "Google Veo 3 Fast", "tier": "$$$"},
        {"id": "minimax/hailuo-02", "name": "MiniMax Hailuo 02", "tier": "$$"},
        {"id": "wan-video/wan-2.2-t2v-fast", "name": "Wan 2.2 fast", "tier": "$"},
        {"id": "bytedance/seedance-1-lite", "name": "Seedance 1 Lite", "tier": "$"},
    ],
    "local_wan": [{"id": "Wan-AI/Wan2.1-T2V-1.3B-Diffusers", "name": "Wan 2.1 T2V 1.3B (480p)", "tier": "free"}],
}
DEFAULTS = {"engine": "pexels", "model": "", "max_clips": 2, "cost_per_clip": 0.30, "quality": "fast"}
NEGATIVE = "text, captions, watermark, logo, subtitles, blurry, low quality, distorted face, extra fingers, static image"


def config() -> dict:
    try:
        from .accounts import current

        v = current().get("visuals") or {}
    except Exception:  # noqa: BLE001
        v = {}
    c = DEFAULTS | v
    if c["engine"] not in ENGINES:
        c["engine"] = "pexels"
    if not c["model"] and MODELS.get(c["engine"]):
        c["model"] = MODELS[c["engine"]][0]["id"]
    return c


def wants_ai(c: dict | None = None) -> bool:
    return (c or config())["engine"] in ("local_wan", "fal", "replicate")


def _cache_path(engine: str, model: str, prompt: str) -> Path:
    h = hashlib.sha256(f"{engine}|{model}|{prompt}".encode()).hexdigest()[:20]
    return CACHE / f"{engine}_{h}.mp4"


def _log_cost(engine: str, model: str, ref: str, usd: float) -> None:
    new = not COSTS.exists()
    COSTS.parent.mkdir(parents=True, exist_ok=True)
    with open(COSTS, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["ts", "stage", "ref", "model", "input_tokens", "cache_read", "output_tokens", "usd"])  # same as llm.log_cost
        w.writerow([dt.datetime.now().isoformat(timespec="seconds"), "video", ref, f"{engine}:{model}", 0, 0, 0, round(usd, 4)])


def _find_video_url(obj) -> str | None:
    if isinstance(obj, str):
        return obj if obj.startswith("http") and (".mp4" in obj or "video" in obj or "replicate.delivery" in obj) else None
    if isinstance(obj, dict):
        for k in ("video", "url", "output", "videos"):
            if k in obj and (u := _find_video_url(obj[k])):
                return u
        for v in obj.values():
            if u := _find_video_url(v):
                return u
    if isinstance(obj, list):
        for v in obj:
            if u := _find_video_url(v):
                return u
    return None


def _download(url: str, dst: Path, headers: dict | None = None) -> Path:
    with httpx.stream("GET", url, headers=headers or {}, timeout=300, follow_redirects=True) as r:
        r.raise_for_status()
        with open(dst, "wb") as f:
            for chunk in r.iter_bytes(1 << 20):
                f.write(chunk)
    return dst


def _fal(model: str, prompt: str, dst: Path, timeout_s: int = 900) -> Path:
    h = {"Authorization": f"Key {secret('FAL_KEY')}", "Content-Type": "application/json"}
    r = httpx.post(f"https://queue.fal.run/{model}", headers=h, json={"prompt": prompt, "aspect_ratio": "9:16"}, timeout=60)
    if r.status_code >= 300:
        raise RuntimeError(f"fal submit {r.status_code}: {r.text[:300]}")
    sub = r.json()
    t0 = time.time()
    while time.time() - t0 < timeout_s:
        st = httpx.get(sub["status_url"], headers=h, timeout=30).json()
        if st.get("status") == "COMPLETED":
            if st.get("error"):
                raise RuntimeError(f"fal: {st['error']}")
            break
        time.sleep(4)
    else:
        raise TimeoutError("fal generation timed out")
    res = httpx.get(sub["response_url"], headers=h, timeout=60).json()
    url = _find_video_url(res)
    if not url:
        raise RuntimeError(f"fal returned no video: {str(res)[:300]}")
    return _download(url, dst)


def _replicate(model: str, prompt: str, dst: Path, timeout_s: int = 900) -> Path:
    h = {"Authorization": f"Bearer {secret('REPLICATE_API_TOKEN')}", "Content-Type": "application/json", "Prefer": "wait=60"}
    r = httpx.post(f"https://api.replicate.com/v1/models/{model}/predictions", headers=h,
                   json={"input": {"prompt": prompt, "aspect_ratio": "9:16"}}, timeout=90)
    if r.status_code >= 300:
        raise RuntimeError(f"replicate {r.status_code}: {r.text[:300]}")
    p, t0 = r.json(), time.time()
    while p.get("status") not in ("succeeded", "failed", "canceled"):
        if time.time() - t0 > timeout_s:
            raise TimeoutError("replicate generation timed out")
        time.sleep(4)
        p = httpx.get(p["urls"]["get"], headers={"Authorization": h["Authorization"]}, timeout=30).json()
    if p["status"] != "succeeded":
        raise RuntimeError(f"replicate {p['status']}: {p.get('error')}")
    url = _find_video_url(p.get("output"))
    if not url:
        raise RuntimeError(f"replicate returned no video: {str(p.get('output'))[:300]}")
    return _download(url, dst, {"Authorization": h["Authorization"]})


_WAN = None


def _local_wan(model: str, prompt: str, dst: Path, quality: str = "fast") -> Path:
    global _WAN
    import torch
    from diffusers import AutoencoderKLWan, WanPipeline


    if _WAN is None:
        vae = AutoencoderKLWan.from_pretrained(model, subfolder="vae", torch_dtype=torch.float32)
        _WAN = WanPipeline.from_pretrained(model, vae=vae, torch_dtype=torch.bfloat16).to("cuda")
    steps = {"fast": 25, "normal": 40, "best": 50}.get(quality, 25)
    t = time.time()
    frames = _WAN(prompt=prompt, negative_prompt=NEGATIVE, height=832, width=480, num_frames=49,
                  guidance_scale=5.0, num_inference_steps=steps, output_type="np").frames[0]
    _write_mp4(frames, dst, 16)
    print(f"  wan clip in {time.time() - t:.0f}s")
    return dst


def _write_mp4(frames, dst: Path, fps: int) -> None:
    """(T, H, W, 3) float [0,1] -> H.264 mp4 via ffmpeg stdin (no OpenCV needed)."""
    import subprocess

    import numpy as np

    arr = (np.clip(np.asarray(frames), 0, 1) * 255).astype(np.uint8)
    t, h, w, _ = arr.shape
    p = subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{w}x{h}", "-r", str(fps), "-i", "-",
                        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "16", "-movflags", "+faststart", str(dst)],
                       input=arr.tobytes(), capture_output=True)
    if p.returncode != 0:
        raise RuntimeError(f"ffmpeg encode failed: {p.stderr.decode(errors='replace')[-300:]}")


def release() -> None:
    """Free the local model's VRAM (call after a short's clips are done)."""
    global _WAN
    if _WAN is not None:
        import torch

        _WAN = None
        torch.cuda.empty_cache()


def generate(prompt: str, dst: Path, ref: str = "", c: dict | None = None) -> tuple[Path, str] | None:
    """AI clip for `prompt` -> dst. Returns (path, credit label) or None. Cached; never raises."""
    c = c or config()
    engine, model = c["engine"], c["model"]
    if engine not in ("local_wan", "fal", "replicate") or not prompt.strip():
        return None
    CACHE.mkdir(parents=True, exist_ok=True)
    cached = _cache_path(engine, model, prompt)
    try:
        if not cached.exists():
            tmp = cached.with_suffix(".part.mp4")
            if engine == "fal":
                _fal(model, prompt, tmp)
            elif engine == "replicate":
                _replicate(model, prompt, tmp)
            else:
                _local_wan(model, prompt, tmp, c.get("quality", "fast"))
            tmp.replace(cached)
            _log_cost(engine, model, ref, 0.0 if engine == "local_wan" else float(c.get("cost_per_clip", 0.3)))
        shutil.copy2(cached, dst)
        name = next((m["name"] for m in MODELS.get(engine, []) if m["id"] == model), model)
        return dst, f"AI-generated video ({name})"
    except Exception as e:  # noqa: BLE001
        print(f"  video model failed ({engine}:{model}): {str(e)[:200]}")
        return None
