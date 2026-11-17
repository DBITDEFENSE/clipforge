"""Paths, settings, brand, and secrets. One place to read config from."""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "config"
INBOX = ROOT / "inbox"
TAKES = ROOT / "takes"
ASSETS = ROOT / "assets"
MUSIC = ASSETS / "music"
DATA = ROOT / "data"
WORK = ROOT / "work"
OUT = ROOT / "out"
RENDER = ROOT / "render"
DB_PATH = DATA / "clipforge.db"
COSTS = DATA / "costs.csv"

VIDEO_EXTS = {".mp4", ".mkv", ".webm", ".mov"}

load_dotenv(ROOT / ".env")


def _load(name: str) -> dict:
    with open(CONFIG / name, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


@lru_cache
def settings() -> dict:
    return _load("settings.yaml")


@lru_cache
def brand() -> dict:
    return _load("brand.yaml")


@lru_cache
def pronunciations() -> dict:
    return _load("pronunciations.yaml")


def secret(name: str, required: bool = True) -> str | None:
    val = os.environ.get(name, "").strip() or None
    if required and not val:
        raise RuntimeError(f"{name} is not set. Add it to {ROOT / '.env'} (see .env.example).")
    return val


def ensure_dirs() -> None:
    for d in (INBOX, TAKES, MUSIC, ASSETS / "gameplay", DATA, WORK, OUT):
        d.mkdir(parents=True, exist_ok=True)
