"""TikTok Content Posting API (Direct Post) with Login Kit for Desktop (PKCE, localhost redirect).

Setup (once): developers.tiktok.com -> Manage apps -> create an app -> add products "Login Kit" (platform: Desktop) and
"Content Posting API" (enable Direct Post) -> scopes user.info.basic, video.publish, video.list -> add the redirect URI the
studio shows on its Connect tab. Put TIKTOK_CLIENT_KEY / TIKTOK_CLIENT_SECRET in .env (or paste them on the Connect tab).

Until TikTok audits the app, every post is restricted to private (SELF_ONLY) viewing. That's TikTok's rule, not ours.
"""
from __future__ import annotations

import hashlib
import math
import secrets
import time
from pathlib import Path
from urllib.parse import urlencode

import httpx

from ..config import secret
from . import NotConnected, forget, load_token, save_token

AUTH = "https://www.tiktok.com/v2/auth/authorize/"
API = "https://open.tiktokapis.com/v2"
SCOPES = ["user.info.basic", "video.publish", "video.list"]
NAME = "tiktok"
CHUNK = 10 * 1024 * 1024  # TikTok: chunks 5-64 MB, last chunk may be up to 128 MB


def configured() -> bool:
    return bool(secret("TIKTOK_CLIENT_KEY", False) and secret("TIKTOK_CLIENT_SECRET", False))


def connected() -> bool:
    return bool((load_token(NAME) or {}).get("refresh_token"))


def auth_url(redirect_uri: str) -> tuple[str, str, str]:
    """Returns (url, state, code_verifier). TikTok desktop PKCE uses the HEX sha256 of the verifier."""
    verifier = secrets.token_urlsafe(48)[:64]
    challenge = hashlib.sha256(verifier.encode()).hexdigest()
    state = secrets.token_urlsafe(16)
    q = {"client_key": secret("TIKTOK_CLIENT_KEY"), "scope": ",".join(SCOPES), "response_type": "code",
         "redirect_uri": redirect_uri, "state": state, "code_challenge": challenge, "code_challenge_method": "S256"}
    return f"{AUTH}?{urlencode(q)}", state, verifier


def _token_call(data: dict) -> dict:
    r = httpx.post(f"{API}/oauth/token/", data=data, headers={"Content-Type": "application/x-www-form-urlencoded"}, timeout=30)
    j = r.json()
    if r.status_code != 200 or "access_token" not in j:
        raise RuntimeError(f"TikTok token {r.status_code}: {j.get('error')} {j.get('error_description', '')}".strip())
    return j


def exchange(code: str, redirect_uri: str, verifier: str) -> None:
    save_token(NAME, _token_call({"client_key": secret("TIKTOK_CLIENT_KEY"), "client_secret": secret("TIKTOK_CLIENT_SECRET"),
                                  "code": code, "grant_type": "authorization_code", "redirect_uri": redirect_uri,
                                  "code_verifier": verifier}))


def _access() -> str:
    tok = load_token(NAME)
    if not tok or not tok.get("refresh_token"):
        raise NotConnected("TikTok isn't connected")
    if time.time() < tok.get("expires_at", 0):
        return tok["access_token"]
    try:  # refresh tokens rotate: always store the new one
        new = _token_call({"client_key": secret("TIKTOK_CLIENT_KEY"), "client_secret": secret("TIKTOK_CLIENT_SECRET"),
                           "grant_type": "refresh_token", "refresh_token": tok["refresh_token"]})
    except RuntimeError as e:
        forget(NAME)
        raise NotConnected(f"TikTok session expired; reconnect ({e})") from e
    save_token(NAME, new)
    return new["access_token"]


def _post(path: str, body: dict, params: dict | None = None) -> dict:
    r = httpx.post(f"{API}{path}", params=params, json=body, timeout=60,
                   headers={"Authorization": f"Bearer {_access()}", "Content-Type": "application/json; charset=UTF-8"})
    j = r.json()
    err = (j.get("error") or {})
    if r.status_code != 200 or err.get("code") not in (None, "ok"):
        raise RuntimeError(f"TikTok {path} {r.status_code}: {err.get('code')} {err.get('message', '')}".strip())
    return j.get("data") or {}


def creator_info() -> dict:
    """Nickname, privacy options, interaction settings, max duration. Must be fetched fresh for every post page."""
    return _post("/post/publish/creator_info/query/", {})


def post(mp4: Path, caption: str, privacy: str, allow_comment: bool, allow_duet: bool, allow_stitch: bool,
         brand_organic: bool = False, branded_content: bool = False, is_aigc: bool = True) -> str:
    """Direct Post via FILE_UPLOAD. Returns publish_id (poll status())."""
    size = mp4.stat().st_size
    if size <= CHUNK:
        chunk, count = size, 1
    else:
        chunk, count = CHUNK, max(1, math.floor(size / CHUNK))  # remainder rides on the last chunk
    data = _post("/post/publish/video/init/", {
        "post_info": {"title": caption[:2200], "privacy_level": privacy, "disable_comment": not allow_comment,
                      "disable_duet": not allow_duet, "disable_stitch": not allow_stitch,
                      "brand_organic_toggle": brand_organic, "brand_content_toggle": branded_content, "is_aigc": is_aigc},
        "source_info": {"source": "FILE_UPLOAD", "video_size": size, "chunk_size": chunk, "total_chunk_count": count},
    })
    url, pid = data["upload_url"], data["publish_id"]
    with open(mp4, "rb") as f:
        for i in range(count):
            start = i * chunk
            end = size - 1 if i == count - 1 else start + chunk - 1
            f.seek(start)
            body = f.read(end - start + 1)
            r = httpx.put(url, content=body, timeout=600, headers={
                "Content-Type": "video/mp4", "Content-Length": str(len(body)), "Content-Range": f"bytes {start}-{end}/{size}"})
            if r.status_code not in (200, 201, 206):
                raise RuntimeError(f"TikTok chunk {i + 1}/{count} upload {r.status_code}: {r.text[:200]}")
    return pid


def status(publish_id: str) -> dict:
    """{status: PROCESSING_UPLOAD|PROCESSING_DOWNLOAD|SEND_TO_USER_INBOX|PUBLISH_COMPLETE|FAILED, fail_reason, publicaly_available_post_id}"""
    return _post("/post/publish/status/fetch/", {"publish_id": publish_id})


def stats(video_ids: list[str]) -> dict[str, dict]:
    out = {}
    for i in range(0, len(video_ids), 20):
        data = _post("/video/query/", {"filters": {"video_ids": video_ids[i:i + 20]}},
                     params={"fields": "id,view_count,like_count,comment_count,share_count"})
        for v in data.get("videos", []):
            out[str(v["id"])] = {"views": v.get("view_count", 0), "likes": v.get("like_count", 0),
                                 "comments": v.get("comment_count", 0), "shares": v.get("share_count", 0)}
    return out
