"""Platform publishing (YouTube, TikTok). Tokens live in data/tokens/ (gitignored); client IDs/secrets in .env."""
from __future__ import annotations

import json
import time
from pathlib import Path

from ..config import DATA

TOKENS = DATA / "tokens"


def load_token(name: str) -> dict | None:
    p = TOKENS / f"{name}.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def save_token(name: str, tok: dict) -> None:
    TOKENS.mkdir(parents=True, exist_ok=True)
    if "expires_in" in tok and "expires_at" not in tok:
        tok["expires_at"] = time.time() + int(tok["expires_in"]) - 60
    (TOKENS / f"{name}.json").write_text(json.dumps(tok, indent=2), encoding="utf-8")


def forget(name: str) -> None:
    p: Path = TOKENS / f"{name}.json"
    if p.exists():
        p.unlink()


class NotConnected(RuntimeError):
    pass
