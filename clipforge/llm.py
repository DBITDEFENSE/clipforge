"""Claude calls: structured output, refusal fallback, cost logging."""
from __future__ import annotations

import csv
import time
from typing import TypeVar

import anthropic
from pydantic import BaseModel

from .config import COSTS, secret, settings

T = TypeVar("T", bound=BaseModel)
_client: anthropic.Anthropic | None = None


class ClaudeRefused(RuntimeError):
    pass


def client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        secret("ANTHROPIC_API_KEY")
        _client = anthropic.Anthropic(max_retries=4, timeout=600)
    return _client


def log_cost(stage: str, ref: str, model: str, usage) -> float:
    cfg = settings()["claude"]
    tin = (usage.input_tokens or 0) + (getattr(usage, "cache_creation_input_tokens", 0) or 0)
    tcache = getattr(usage, "cache_read_input_tokens", 0) or 0
    tout = usage.output_tokens or 0
    usd = (tin * cfg["price_in"] + tcache * cfg["price_in"] * 0.1 + tout * cfg["price_out"]) / 1_000_000
    new = not COSTS.exists()
    COSTS.parent.mkdir(parents=True, exist_ok=True)
    with open(COSTS, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["ts", "stage", "ref", "model", "input_tokens", "cache_read", "output_tokens", "usd"])
        w.writerow([time.strftime("%Y-%m-%d %H:%M:%S"), stage, ref, model, tin, tcache, tout, f"{usd:.4f}"])
    return usd


def structured(system: str, user: str, schema: type[T], *, stage: str, ref: str, effort: str = "high",
               max_tokens: int = 16000, images: list | None = None) -> T:
    """One Claude call that must return `schema`. Raises ClaudeRefused if the whole fallback chain declines."""
    cfg = settings()["claude"]
    content = user
    if images:  # local image files (jpg/png) shown before the text
        import base64

        content = [{"type": "image", "source": {"type": "base64", "media_type": "image/png" if str(p).endswith(".png") else "image/jpeg",
                                                "data": base64.b64encode(open(p, "rb").read()).decode()}} for p in images]
        content.append({"type": "text", "text": user})
    kwargs = {}
    if cfg.get("fallbacks"):
        kwargs = {"betas": ["server-side-fallback-2026-07-01"], "fallbacks": cfg["fallbacks"]}
    resp = client().beta.messages.parse(
        model=cfg["model"],
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": content}],
        output_config={"effort": effort},
        output_format=schema,
        **kwargs,
    )
    log_cost(stage, ref, resp.model, resp.usage)
    if resp.stop_reason == "refusal":
        cat = getattr(resp.stop_details, "category", None) if resp.stop_details else None
        raise ClaudeRefused(f"{stage}: declined (category={cat}, request_id={resp._request_id})")
    if resp.stop_reason == "max_tokens":
        raise RuntimeError(f"{stage}: hit max_tokens={max_tokens}; output truncated")
    if resp.parsed_output is None:
        raise RuntimeError(f"{stage}: no parsed output (stop_reason={resp.stop_reason})")
    return resp.parsed_output
