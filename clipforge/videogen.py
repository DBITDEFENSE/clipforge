"""B-roll engines ("video models"), chosen per channel in Studio > Settings > Visuals.

  none       motion graphics only (B-roll shots become kinetic text)
  pexels     licensed stock footage (PEXELS_API_KEY)
  local_wan  Wan on your GPU via diffusers (Apache-2.0, free): 2.1 1.3B (480p, ~75 s/clip) or 2.2 5B (720p, sharper)
  fal        any fal.ai text-to-video model (FAL_KEY): Kling, Veo, Hailuo, Wan 2.2, LTX, Seedance...
  replicate  any Replicate text-to-video model (REPLICATE_API_TOKEN)
  gemini     Google Gemini Omni Flash via the Interactions API (GEMINI_API_KEY)
  higgsfield Higgsfield text-to-video models (HF_API_KEY_ID + HF_API_KEY_SECRET): Seedance, Kling...

The channel picks one engine plus an ordered list of backups (`fallbacks`). When the first one fails (out of credits,
rate limited, model down) the next one that has a key is tried, so a short still gets its clips. An engine that fails
with an auth/quota/rate-limit error is skipped for the rest of the run.

Clips are cached by (engine, model, prompt). Paid engines log an estimated cost per clip to data/costs.csv and are
capped by `max_clips` per short. If every engine fails the shot falls back to motion graphics.
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
    "local_wan": "Local AI video: Wan (free, your GPU)",
    "fal": "fal.ai video models (paid, your key)",
    "replicate": "Replicate video models (paid, your key)",
    "gemini": "Google Gemini video (paid, your key)",
    "higgsfield": "Higgsfield video models (paid, your key)",
}
AI_ENGINES = ("local_wan", "fal", "replicate", "gemini", "higgsfield")
# .env names each engine needs (all must be set). local_wan needs none.
KEYS = {"pexels": ["PEXELS_API_KEY"], "fal": ["FAL_KEY"], "replicate": ["REPLICATE_API_TOKEN"], "gemini": ["GEMINI_API_KEY"],
        "higgsfield": ["HF_API_KEY_ID", "HF_API_KEY_SECRET"]}
CLIP_SECONDS = 5  # asked of the hosted models that take a duration
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
    "gemini": [
        {"id": "gemini-omni-1.2-flash", "name": "Gemini Omni Flash 1.2 (720p)", "tier": "$$"},
    ],
    "higgsfield": [
        {"id": "bytedance/seedance-2.0/text-to-video", "name": "Seedance 2.0", "tier": "$$"},
        {"id": "kling-video/v3.0/std/text-to-video", "name": "Kling 3.0 Standard", "tier": "$$"},
        {"id": "kling-video/v3.0-turbo/text-to-video", "name": "Kling 3.0 Turbo", "tier": "$"},
        {"id": "kling-video/v3.0/pro/text-to-video", "name": "Kling 3.0 Pro", "tier": "$$$"},
    ],
    "local_wan": [
        {"id": "Wan-AI/Wan2.1-T2V-1.3B-Diffusers", "name": "Wan 2.1 1.3B: 480p, fast (~75 s/clip)", "tier": "free"},
        {"id": "Wan-AI/Wan2.2-TI2V-5B-Diffusers", "name": "Wan 2.2 5B: 720p, sharper (~3-5 min/clip)", "tier": "free"},
    ],
}
WAN21 = "Wan-AI/Wan2.1-T2V-1.3B-Diffusers"
# Per local model: output size (vertical), frames (4k+1), fps, guidance, offload. The 5B reuses the 1.3B's text encoder
# (same umt5-xxl) when that is already downloaded, which saves an 11 GB download.
LOCAL = {
    WAN21: {"h": 832, "w": 480, "frames": 49, "fps": 16, "guidance": 5.0, "offload": False, "min_gb": 28},
    "Wan-AI/Wan2.2-TI2V-5B-Diffusers": {"h": 1280, "w": 704, "frames": 61, "fps": 24, "guidance": 5.0, "offload": True,
                                        "min_gb": 22, "shared_te": WAN21},
}
DEFAULTS = {"engine": "pexels", "model": "", "max_clips": 2, "cost_per_clip": 0.30, "quality": "fast",
            "fallbacks": [], "engine_models": {}}
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
    c["fallbacks"] = [e for e in (c.get("fallbacks") or []) if e in ENGINES and e not in ("none", c["engine"])]
    c["engine_models"] = dict(c.get("engine_models") or {})
    return c


def wants_ai(c: dict | None = None) -> bool:
    return (c or config())["engine"] in AI_ENGINES


def has_keys(engine: str) -> bool:
    return all(secret(k, False) for k in KEYS.get(engine, []))


def model_for(engine: str, c: dict) -> str:
    """The model this channel uses on `engine`: the selected one, the one last picked there, or the first suggestion."""
    if engine == c["engine"] and c.get("model"):
        return c["model"]
    return (c.get("engine_models") or {}).get(engine) or (MODELS[engine][0]["id"] if MODELS.get(engine) else "")


def chain(c: dict | None = None) -> list[tuple[str, str]]:
    """AI engines to try in order, as (engine, model): the selected engine, then the backups. Empty when the channel's
    engine isn't an AI one (stock or graphics only)."""
    c = c or config()
    if c["engine"] not in AI_ENGINES:
        return []
    return [(e, model_for(e, c)) for e in [c["engine"], *(c.get("fallbacks") or [])] if e in AI_ENGINES]


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


def _gemini(model: str, prompt: str, dst: Path) -> Path:
    """Gemini Omni Flash through the Interactions API: one request, the MP4 comes back base64 in the response."""
    import base64

    r = httpx.post("https://generativelanguage.googleapis.com/v1beta/interactions",
                   headers={"x-goog-api-key": secret("GEMINI_API_KEY"), "Content-Type": "application/json"},
                   json={"model": model, "input": prompt, "store": False,
                         "response_format": {"type": "video", "aspect_ratio": "9:16", "duration": f"{CLIP_SECONDS}s", "resolution": "720p"}},
                   timeout=900)
    if r.status_code >= 300:
        raise RuntimeError(f"gemini {r.status_code}: {r.text[:300]}")
    res = r.json()
    if res.get("status") in ("failed", "cancelled", "incomplete"):
        raise RuntimeError(f"gemini {res.get('status')}: {str(res.get('errors'))[:300]}")
    for step in res.get("steps") or []:
        for part in (step.get("content") or []) if isinstance(step, dict) else []:
            if isinstance(part, dict) and part.get("type") == "video":
                if part.get("data"):
                    dst.write_bytes(base64.b64decode(part["data"]))
                    return dst
                if part.get("uri"):
                    return _download(part["uri"], dst, {"x-goog-api-key": secret("GEMINI_API_KEY")})
    raise RuntimeError(f"gemini returned no video: {str(res)[:300]}")


def _higgsfield(model: str, prompt: str, dst: Path, timeout_s: int = 900) -> Path:
    h = {"Authorization": f"Key {secret('HF_API_KEY_ID')}:{secret('HF_API_KEY_SECRET')}", "Content-Type": "application/json"}
    body = {"prompt": prompt, "duration": CLIP_SECONDS, "aspect_ratio": "9:16"}
    if model.startswith("bytedance/seedance"):  # schemas are strict per model; only Seedance's extra fields are known
        body |= {"resolution": "720p", "generate_audio": False}
    r = httpx.post(f"https://api.higgsfield.ai/{model.strip('/')}", headers=h, json=body, timeout=60)
    if r.status_code >= 300:
        raise RuntimeError(f"higgsfield submit {r.status_code}: {r.text[:300]}")
    sub, t0 = r.json(), time.time()
    st = sub
    while st.get("status") in ("queued", "in_progress"):
        if time.time() - t0 > timeout_s:
            raise TimeoutError("higgsfield generation timed out")
        time.sleep(4)
        st = httpx.get(sub["status_url"], headers=h, timeout=30).json()
    if st.get("status") != "completed":
        raise RuntimeError(f"higgsfield {st.get('status')}: {st.get('error') or st.get('detail')}")
    url = (st.get("video") or {}).get("url") or _find_video_url(st)
    if not url:
        raise RuntimeError(f"higgsfield returned no video: {str(st)[:300]}")
    return _download(url, dst)


_WAN = None
_WAN_ID = None


def _hub(model: str) -> Path:
    return Path.home() / ".cache" / "huggingface" / "hub" / ("models--" + model.replace("/", "--"))


def local_ready(model: str) -> bool:
    """Fully downloaded (no partial blobs, roughly the expected size)."""
    hub, spec = _hub(model), LOCAL.get(model, {})
    if not (hub / "snapshots").exists() or any((hub / "blobs").glob("*.incomplete")):
        return False
    return sum(p.stat().st_size for p in hub.rglob("*") if p.is_file()) > spec.get("min_gb", 1) * 1e9  # no symlinks on Windows: files sit in snapshots/


def _load(model: str):
    """Load (or reuse) the local Wan text-to-video pipeline for `model`."""
    global _WAN, _WAN_ID
    import torch
    from diffusers import AutoencoderKLWan, WanPipeline

    spec = LOCAL.get(model, LOCAL[WAN21])
    if _WAN is None or _WAN_ID != model:
        release()
        kw = {}
        if spec.get("shared_te") and local_ready(spec["shared_te"]):
            from transformers import UMT5EncoderModel

            kw["text_encoder"] = UMT5EncoderModel.from_pretrained(spec["shared_te"], subfolder="text_encoder", torch_dtype=torch.bfloat16)
        vae = AutoencoderKLWan.from_pretrained(model, subfolder="vae", torch_dtype=torch.float32)
        _WAN = WanPipeline.from_pretrained(model, vae=vae, torch_dtype=torch.bfloat16, **kw)
        if spec["offload"]:
            _WAN.enable_model_cpu_offload()
        else:
            _WAN.to("cuda")
        # Tiled VAE decode: without it the decode can overflow VRAM (the desktop/other apps hold several GB) and spill into
        # system RAM, turning a ~75 s clip into 10+ minutes. Measured: 5B 555 s -> 146 s.
        _WAN.vae.enable_tiling()
        _WAN_ID = model
    return _WAN, spec


def _local_wan(model: str, prompt: str, dst: Path, quality: str = "fast") -> Path:
    import torch

    pipe, spec = _load(model)
    steps = {"fast": 25, "normal": 40, "best": 50}.get(quality, 25)
    t = time.time()
    frames = pipe(prompt=prompt, negative_prompt=NEGATIVE, height=spec["h"], width=spec["w"], num_frames=spec["frames"],
                  guidance_scale=spec["guidance"], num_inference_steps=steps, output_type="np").frames[0]
    _write_mp4(frames, dst, spec["fps"])
    torch.cuda.empty_cache()
    print(f"  wan clip in {time.time() - t:.0f}s")
    return dst


RESTYLE_NEGATIVE = "photorealistic, live action photo, " + NEGATIVE


def restyle(frames: list, prompt: str, strength: float = 0.5, steps: int = 30):
    """Video-to-video with Wan 2.1 1.3B (same weights as text-to-video, so no extra download).
    frames: PIL images (landscape 832x480, count 4k+1). strength 0 = untouched, 1 = ignore the source. Returns (T,H,W,3) floats."""
    import torch
    from diffusers import WanVideoToVideoPipeline

    pipe, _ = _load(WAN21)
    v2v = WanVideoToVideoPipeline.from_pipe(pipe)
    w, h = frames[0].size
    t = time.time()
    out = v2v(video=frames, prompt=prompt, negative_prompt=RESTYLE_NEGATIVE, height=h, width=w, guidance_scale=5.0,
              strength=float(strength), num_inference_steps=steps, output_type="np").frames[0]
    torch.cuda.empty_cache()
    print(f"  restyled {len(frames)} frames in {time.time() - t:.0f}s")
    return out


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
    global _WAN, _WAN_ID
    if _WAN is not None:
        import torch

        _WAN, _WAN_ID = None, None
        torch.cuda.empty_cache()


_DOWN: set[str] = set()  # engines that hit an auth/quota/rate-limit error in this process: don't keep retrying them
_LIMIT_HINTS = ("401", "402", "403", "429", "quota", "credit", "rate limit", "billing", "insufficient", "exhausted", "is not set")


def _run(engine: str, model: str, prompt: str, tmp: Path, quality: str) -> None:
    if engine == "local_wan":
        _local_wan(model, prompt, tmp, quality)
    else:
        globals()[f"_{engine}"](model, prompt, tmp)  # _fal, _replicate, _gemini, _higgsfield


def generate(prompt: str, dst: Path, ref: str = "", c: dict | None = None) -> tuple[Path, str] | None:
    """AI clip for `prompt` -> dst, trying the channel's engine and then its backups. Returns (path, credit label) or
    None. Cached per engine; never raises."""
    c = c or config()
    if not prompt.strip():
        return None
    CACHE.mkdir(parents=True, exist_ok=True)
    engines = chain(c)
    for n, (engine, model) in enumerate(engines):
        if engine in _DOWN or not has_keys(engine):
            continue
        cached = _cache_path(engine, model, prompt)
        try:
            if not cached.exists():
                tmp = cached.with_suffix(".part.mp4")
                _run(engine, model, prompt, tmp, c.get("quality", "fast"))
                tmp.replace(cached)
                _log_cost(engine, model, ref, 0.0 if engine == "local_wan" else float(c.get("cost_per_clip", 0.3)))
            shutil.copy2(cached, dst)
            name = next((m["name"] for m in MODELS.get(engine, []) if m["id"] == model), model)
            return dst, f"AI-generated video ({name})"
        except Exception as e:  # noqa: BLE001
            msg = str(e)
            if any(h in msg.lower() for h in _LIMIT_HINTS):
                _DOWN.add(engine)
            print(f"  video model failed ({engine}:{model}): {msg[:200]}" + ("; trying the next one" if n + 1 < len(engines) else ""))
    return None
