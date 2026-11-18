"""Channel accounts. Each account is one channel/brand: name, handle, persona (how scripts sound), colors, voice,
posting slots, connected platforms (tokens under data/tokens/<account>/), and an optional password for the studio.

The active account comes from CLIPFORGE_ACCOUNT (the studio and `--account` set it); default = the first account.
"""
from __future__ import annotations

import contextvars
import hashlib
import hmac
import json
import os
import re
import secrets
import time

from . import db

ACTIVE: contextvars.ContextVar[str | None] = contextvars.ContextVar("clipforge_account", default=None)
DEFAULT_SLOTS = ["09:00", "12:00", "15:00", "18:00", "21:00"]

PERSONAS = {
    "cyber-cowboy": (
        "Channel: CYBER COWBOY. The host is a working SOC analyst who rides herd on the internet's chaos.\n"
        "- Energy: rapid-fire, funny, deadpan tech-news delivery; dense with facts and jokes.\n"
        "- Angle: always lands a practitioner's take: what this means for people who work in cyber or are breaking into it "
        "(what to patch, what to learn, what it says about the job). Relatable, real-talk, never preachy.\n"
        "- Flavor: a light western streak. At most one or two touches per script (\"partner\", \"outlaws\", \"sheriff\", "
        "\"this town\", \"rodeo\", \"saddle up\", \"wanted poster\"). Never corny, never forced, never the whole bit.\n"
        "- Visual flavor: an occasional 🤠 🐎 🌵 🔫 🪢 sticker or reaction fits the brand; use sparingly.\n"
        "- Audience: cyber pros, people breaking into cyber, and tech-curious viewers."
    ),
    "default": (
        "Channel: a cybersecurity-first short-form channel run by a working SOC analyst. Fast, deadpan, confident; "
        "audience is cyber first, then tech/AI, then some gaming."
    ),
}

BRANDS = {
    "cyber-cowboy": {
        "name": "Cyber Cowboy", "handle": "CYBER COWBOY",
        "colors": {"bg": "#0B0806", "surface": "#18120D", "text": "#FFF7EC", "muted": "#A8977F", "accent": "#FFB627",
                   "accent2": "#FF5A1F", "highlight": "#3DFF8F", "warning": "#FF3B30", "fire": "#FF8A00"},
    },
}


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:40] or "channel"


def _hash(pw: str, salt: str | None = None) -> str:
    salt = salt or secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", pw.encode(), bytes.fromhex(salt), 240_000)
    return f"pbkdf2${salt}${dk.hex()}"


def check_password(acc: dict, pw: str) -> bool:
    h = acc.get("password_hash")
    if not h:
        return True
    _, salt, _ = h.split("$")
    return hmac.compare_digest(_hash(pw, salt), h)


def _row(r) -> dict:
    d = dict(r)
    for k in ("brand", "slots", "voice", "visuals", "autopilot"):
        d[k] = json.loads(d.get(k) or ("[]" if k == "slots" else "{}"))
    return d


def ensure() -> None:
    """Bootstrap: DBIT Defense (the original brand) + Cyber Cowboy."""
    with db.connect() as con:
        if con.execute("SELECT COUNT(*) FROM accounts").fetchone()[0]:
            return
    from .config import _load

    base = _load("brand.yaml")
    create("DBIT Defense", handle=base.get("handle", "@dbitdefense"), persona=PERSONAS["default"],
           brand={"colors": base.get("colors", {})}, voice_id=os.environ.get("ELEVENLABS_VOICE_ID", ""), slug="dbit-defense")
    create("Cyber Cowboy", handle=BRANDS["cyber-cowboy"]["handle"], persona=PERSONAS["cyber-cowboy"],
           brand={"colors": BRANDS["cyber-cowboy"]["colors"]}, voice_id=os.environ.get("ELEVENLABS_VOICE_ID", ""), slug="cyber-cowboy")


def create(name: str, handle: str = "", persona: str = "", brand: dict | None = None, voice_id: str = "",
           password: str = "", slug: str | None = None, slots: list[str] | None = None) -> dict:
    sid = slug or _slug(name)
    with db.connect() as con:
        if con.execute("SELECT 1 FROM accounts WHERE id=?", (sid,)).fetchone():
            sid = f"{sid}-{secrets.token_hex(2)}"
        con.execute("INSERT INTO accounts(id,name,handle,persona,brand,voice,slots,password_hash,created) VALUES(?,?,?,?,?,?,?,?,?)",
                    (sid, name, handle, persona or PERSONAS["default"], json.dumps(brand or {}), json.dumps({"voice_id": voice_id}),
                     json.dumps(slots or DEFAULT_SLOTS), _hash(password) if password else None, time.time()))
    return get(sid)


def update(sid: str, **f) -> dict:
    acc = get(sid)
    if "password" in f:
        pw = f.pop("password")
        f["password_hash"] = _hash(pw) if pw else None
    for k in ("brand", "voice", "visuals", "autopilot"):
        if k in f:
            f[k] = json.dumps(acc[k] | f[k])
    if "slots" in f:
        f["slots"] = json.dumps(sorted(f["slots"]))
    with db.connect() as con:
        con.execute(f"UPDATE accounts SET {', '.join(k + '=?' for k in f)} WHERE id=?", (*f.values(), sid))
    return get(sid)


def get(sid: str) -> dict:
    with db.connect() as con:
        r = con.execute("SELECT * FROM accounts WHERE id=?", (sid,)).fetchone()
    if not r:
        raise KeyError(f"no account {sid}")
    return _row(r)


def all_accounts() -> list[dict]:
    ensure()
    with db.connect() as con:
        return [_row(r) for r in con.execute("SELECT * FROM accounts ORDER BY created")]


def current_id() -> str:
    ensure()
    sid = ACTIVE.get() or os.environ.get("CLIPFORGE_ACCOUNT", "").strip()
    if sid:
        return sid
    return all_accounts()[0]["id"]


def current() -> dict:
    return get(current_id())


def public(acc: dict) -> dict:
    return {k: v for k, v in acc.items() if k != "password_hash"} | {"has_password": bool(acc.get("password_hash"))}


def voice_id() -> str:
    try:
        v = current()["voice"].get("voice_id")
    except KeyError:
        v = None
    return v or os.environ.get("ELEVENLABS_VOICE_ID", "")
