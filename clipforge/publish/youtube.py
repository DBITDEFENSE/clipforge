"""YouTube Data API v3: OAuth (installed-app loopback), resumable upload with scheduled publish, stats.

Setup (once): Google Cloud console -> new project -> enable "YouTube Data API v3" -> OAuth consent screen (External,
add yourself as a test user) -> Credentials -> OAuth client ID -> "Desktop app". Put GOOGLE_CLIENT_ID/GOOGLE_CLIENT_SECRET
in .env (or paste them on the studio's Connect tab).
"""
from __future__ import annotations

import datetime as dt
import secrets
import time
from pathlib import Path
from urllib.parse import urlencode

import httpx

from ..config import secret
from . import NotConnected, forget, load_token, save_token

SCOPES = ["https://www.googleapis.com/auth/youtube.upload", "https://www.googleapis.com/auth/youtube.readonly"]
AUTH = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN = "https://oauth2.googleapis.com/token"
API = "https://www.googleapis.com/youtube/v3"
NAME = "youtube"


def configured() -> bool:
    return bool(secret("GOOGLE_CLIENT_ID", False) and secret("GOOGLE_CLIENT_SECRET", False))


def connected() -> bool:
    return bool((load_token(NAME) or {}).get("refresh_token"))


def auth_url(redirect_uri: str) -> tuple[str, str]:
    state = secrets.token_urlsafe(16)
    q = {"client_id": secret("GOOGLE_CLIENT_ID"), "redirect_uri": redirect_uri, "response_type": "code",
         "scope": " ".join(SCOPES), "access_type": "offline", "prompt": "consent", "state": state}
    return f"{AUTH}?{urlencode(q)}", state


def exchange(code: str, redirect_uri: str) -> None:
    r = httpx.post(TOKEN, data={"code": code, "client_id": secret("GOOGLE_CLIENT_ID"), "client_secret": secret("GOOGLE_CLIENT_SECRET"),
                                "redirect_uri": redirect_uri, "grant_type": "authorization_code"}, timeout=30)
    r.raise_for_status()
    save_token(NAME, r.json())


def _access() -> str:
    tok = load_token(NAME)
    if not tok or not tok.get("refresh_token"):
        raise NotConnected("YouTube isn't connected")
    if time.time() < tok.get("expires_at", 0):
        return tok["access_token"]
    r = httpx.post(TOKEN, data={"client_id": secret("GOOGLE_CLIENT_ID"), "client_secret": secret("GOOGLE_CLIENT_SECRET"),
                                "refresh_token": tok["refresh_token"], "grant_type": "refresh_token"}, timeout=30)
    if r.status_code in (400, 401):
        forget(NAME)
        raise NotConnected(f"YouTube token was revoked or expired; reconnect ({r.text[:120]})")
    r.raise_for_status()
    new = r.json()
    new.setdefault("refresh_token", tok["refresh_token"])
    new.pop("expires_at", None)
    save_token(NAME, new)
    return new["access_token"]


def _h() -> dict:
    return {"Authorization": f"Bearer {_access()}"}


def channel() -> dict:
    r = httpx.get(f"{API}/channels", params={"part": "snippet", "mine": "true"}, headers=_h(), timeout=30)
    r.raise_for_status()
    items = r.json().get("items") or []
    return {"title": items[0]["snippet"]["title"], "id": items[0]["id"]} if items else {"title": "(no channel)", "id": ""}


def upload(mp4: Path, title: str, description: str, tags: list[str], publish_at: dt.datetime | None,
           synthetic_media: bool = True) -> dict:
    """Upload; if publish_at is in the future the video stays private and YouTube publishes it at that time."""
    future = publish_at is not None and publish_at > dt.datetime.now(dt.timezone.utc)
    status = {"privacyStatus": "private" if future else "public", "selfDeclaredMadeForKids": False,
              "containsSyntheticMedia": synthetic_media}
    if future:
        status["publishAt"] = publish_at.astimezone(dt.timezone.utc).isoformat().replace("+00:00", "Z")
    meta = {"snippet": {"title": title[:100], "description": description[:5000], "tags": [t.lstrip("#") for t in tags][:15],
                        "categoryId": "28"},  # Science & Technology
            "status": status}
    size = mp4.stat().st_size
    init = httpx.post("https://www.googleapis.com/upload/youtube/v3/videos", params={"uploadType": "resumable", "part": "snippet,status"},
                      headers=_h() | {"X-Upload-Content-Type": "video/mp4", "X-Upload-Content-Length": str(size)}, json=meta, timeout=60)
    if init.status_code != 200:
        raise RuntimeError(f"YouTube upload init {init.status_code}: {init.text[:300]}")
    with open(mp4, "rb") as f:
        put = httpx.put(init.headers["Location"], content=f.read(), headers={"Content-Type": "video/mp4"}, timeout=900)
    if put.status_code not in (200, 201):
        raise RuntimeError(f"YouTube upload {put.status_code}: {put.text[:300]}")
    vid = put.json()["id"]
    return {"id": vid, "url": f"https://youtube.com/shorts/{vid}", "scheduled": future}


def stats(video_ids: list[str]) -> dict[str, dict]:
    out = {}
    for i in range(0, len(video_ids), 50):
        r = httpx.get(f"{API}/videos", params={"part": "statistics", "id": ",".join(video_ids[i:i + 50])}, headers=_h(), timeout=30)
        r.raise_for_status()
        for it in r.json().get("items", []):
            s = it.get("statistics", {})
            out[it["id"]] = {"views": int(s.get("viewCount", 0)), "likes": int(s.get("likeCount", 0)),
                             "comments": int(s.get("commentCount", 0)), "shares": None}
    return out
