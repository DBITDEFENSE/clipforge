"""`clipforge studio`: the whole flow in one local app (127.0.0.1 only).

Create (paste links / drop videos) -> Review (approve / reject / regenerate with notes) -> Schedule (slots, YouTube +
TikTok) -> Performance (stats, ad candidates) -> Connect (accounts + keys).
Heavy work (download, transcribe, render) runs as one-at-a-time subprocess jobs with live logs.
A background thread publishes whatever is due every minute and refreshes stats every few hours.
"""
from __future__ import annotations

import json
import mimetypes
import os
import re
import subprocess
import sys
import threading
import time
import traceback
import uuid
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from . import ads, db, publisher, schedule
from .config import DATA, INBOX, OUT, ROOT, WORK, secret, settings
from .publish import NotConnected, forget, tiktok, youtube
from .setup_page import write_env

PAGE = Path(__file__).parent / "studio.html"
JOBS_DIR = DATA / "jobs"
VIDEO_EXT = {".mp4", ".mkv", ".webm", ".mov", ".m4v"}


# ---------------------------------------------------------------- jobs
class Jobs:
    """Subprocess jobs, strictly one at a time (they share the GPU)."""

    def __init__(self):
        self.items: list[dict] = []
        self.lock = threading.Lock()
        self.wake = threading.Event()
        JOBS_DIR.mkdir(parents=True, exist_ok=True)
        threading.Thread(target=self._worker, daemon=True).start()

    def add(self, label: str, args: list[str]) -> dict:
        job = {"id": uuid.uuid4().hex[:8], "label": label, "args": args, "status": "queued", "created": time.time(),
               "started": None, "ended": None}
        with self.lock:
            self.items.append(job)
        self.wake.set()
        return job

    def log(self, jid: str, tail: int = 12000) -> str:
        p = JOBS_DIR / f"{jid}.log"
        if not p.exists():
            return ""
        txt = p.read_text(encoding="utf-8", errors="replace")
        return re.sub(r"\x1b\[[0-9;]*m", "", txt)[-tail:]

    def public(self) -> list[dict]:
        with self.lock:
            return [{k: v for k, v in j.items() if k != "args"} for j in self.items[-15:]][::-1]

    def busy(self) -> bool:
        with self.lock:
            return any(j["status"] in ("queued", "running") for j in self.items)

    def _worker(self):
        while True:
            self.wake.wait(5)
            self.wake.clear()
            while True:
                with self.lock:
                    job = next((j for j in self.items if j["status"] == "queued"), None)
                    if not job:
                        break
                    job["status"], job["started"] = "running", time.time()
                env = os.environ | {"PYTHONIOENCODING": "utf-8", "COLUMNS": "110", "NO_COLOR": "1", "TERM": "dumb"}
                with open(JOBS_DIR / f"{job['id']}.log", "w", encoding="utf-8") as logf:
                    rc = subprocess.run([sys.executable, "-m", "clipforge.cli", *job["args"]], cwd=ROOT, stdout=logf,
                                        stderr=subprocess.STDOUT, env=env).returncode
                with self.lock:
                    job["status"], job["ended"] = ("done" if rc == 0 else "failed"), time.time()


JOBS: Jobs | None = None
OAUTH: dict[str, dict] = {}  # state -> {platform, verifier}
TICK_LOG: list[str] = []


def _scheduler():
    last_stats = 0.0
    while True:
        try:
            for line in publisher.tick():
                TICK_LOG.append(f"{time.strftime('%H:%M')} {line}")
            if time.time() - last_stats > 6 * 3600:
                publisher.refresh_metrics()
                last_stats = time.time()
        except Exception:  # noqa: BLE001
            TICK_LOG.append(f"{time.strftime('%H:%M')} scheduler error: {traceback.format_exc(limit=1)[-300:]}")
        del TICK_LOG[:-50]
        time.sleep(60)


# ---------------------------------------------------------------- state
def _read(d: Path, name: str) -> str:
    p = d / name
    return p.read_text(encoding="utf-8") if p.exists() else ""


def _media(p: Path) -> str:
    return "/media/" + p.relative_to(OUT).as_posix()


def shorts_state() -> list[dict]:
    with db.connect() as con:
        rows = [dict(r) for r in con.execute("SELECT * FROM shorts ORDER BY created DESC")]
        posts = {}
        for r in con.execute("SELECT * FROM posts"):
            posts.setdefault(r["short_id"], {})[r["platform"]] = {k: r[k] for k in ("status", "scheduled_at", "url", "error", "remote_id")}
        mets = {}
        for r in con.execute("SELECT m.* FROM metrics m JOIN (SELECT short_id, platform, MAX(ts) ts FROM metrics GROUP BY short_id, platform) l "
                             "ON l.short_id=m.short_id AND l.platform=m.platform AND l.ts=m.ts"):
            mets.setdefault(r["short_id"], {})[r["platform"]] = {k: r[k] for k in ("views", "likes", "comments", "shares")}
    out = []
    for r in rows:
        d = Path(r["out_dir"]) if r["out_dir"] else None
        has = d is not None and (d / "final.mp4").exists()
        if not has and r["status"] in ("done", "flagged"):
            continue  # stale row whose files were deleted
        script = {}
        sp = WORK / "shorts" / r["id"] / "script.json"
        if sp.exists():
            script = json.loads(sp.read_text(encoding="utf-8"))
        qa = json.loads(r["qa"]) if r["qa"] else {}
        out.append({
            "id": r["id"], "status": r["status"], "review": r["review"], "slot": r["slot"], "notes": r["notes"], "error": r["error"],
            "title": script.get("title", r["id"]), "video": _media(d / "final.mp4") + f"?v={int(r['updated'])}" if has else None,
            "cover": _media(d / "cover.png") + f"?v={int(r['updated'])}" if has and (d / "cover.png").exists() else None,
            "qa_pass": qa.get("passed"), "qa_fail": [c["name"] for c in qa.get("checks", []) if not c["ok"]],
            "duration": next((c["detail"] for c in qa.get("checks", []) if c["name"] == "duration"), ""),
            "post": script.get("post", {}), "hooks": script.get("hooks", []),
            "beats": [{"kind": b["kind"], "text": b["text"]} for b in script.get("beats", [])],
            "posts": posts.get(r["id"], {}), "metrics": mets.get(r["id"], {}), "updated": r["updated"],
        })
    return out


def _new_inbox() -> list[str]:
    with db.connect() as con:
        done = {Path(r["path"]).name for r in con.execute("SELECT path FROM videos WHERE status IN ('transcribed','mined')")}
    return sorted(p.name for p in INBOX.iterdir() if p.suffix.lower() in VIDEO_EXT and p.name not in done)


def connections() -> dict:
    def safe(fn, default=None):
        try:
            return fn()
        except Exception as e:  # noqa: BLE001
            return {"error": str(e)[:200]} if default is None else default

    port = settings().get("_studio_port", 8790)
    return {
        "youtube": {"configured": youtube.configured(), "connected": youtube.connected(),
                    "redirect": f"http://127.0.0.1:{port}/oauth/youtube/callback"},
        "tiktok": {"configured": tiktok.configured(), "connected": tiktok.connected(),
                   "redirect": f"http://localhost:{port}/oauth/tiktok/callback/"},
        "anthropic": bool(secret("ANTHROPIC_API_KEY", False)),
        "elevenlabs": bool(secret("ELEVENLABS_API_KEY", False)), "voice_id": secret("ELEVENLABS_VOICE_ID", False) or "",
        "pexels": bool(secret("PEXELS_API_KEY", False)),
        "channel": safe(youtube.channel) if youtube.connected() else None,
    }


# ---------------------------------------------------------------- http
class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, body: bytes, ctype: str, code: int = 200, extra: dict | None = None):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _json(self, obj, code: int = 200):
        self._send(json.dumps(obj, default=str).encode(), "application/json", code)

    def _redirect(self, to: str):
        self.send_response(302)
        self.send_header("Location", to)
        self.end_headers()

    def _body(self) -> dict:
        n = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(n) or b"{}") if n else {}

    def _file(self, p: Path):
        """Static file with HTTP Range support (video seeking)."""
        size = p.stat().st_size
        ctype = mimetypes.guess_type(p.name)[0] or "application/octet-stream"
        rng = self.headers.get("Range")
        if rng and (m := re.match(r"bytes=(\d*)-(\d*)", rng)):
            start = int(m.group(1)) if m.group(1) else max(0, size - int(m.group(2)))
            end = min(int(m.group(2)) if m.group(1) and m.group(2) else size - 1, size - 1)
            with open(p, "rb") as f:
                f.seek(start)
                data = f.read(end - start + 1)
            return self._send(data, ctype, 206, {"Content-Range": f"bytes {start}-{end}/{size}", "Accept-Ranges": "bytes"})
        self._send(p.read_bytes(), ctype, 200, {"Accept-Ranges": "bytes"})

    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):  # noqa: C901
        u = urlparse(self.path)
        q = {k: v[0] for k, v in parse_qs(u.query).items()}
        path = u.path
        try:
            if path in ("/", "/index.html"):
                return self._send(PAGE.read_bytes(), "text/html; charset=utf-8")
            if path.startswith("/media/"):
                p = (OUT / unquote(path[len("/media/"):])).resolve()
                if OUT.resolve() not in p.parents or not p.is_file():
                    return self._json({"error": "not found"}, 404)
                return self._file(p)
            if path == "/api/state":
                return self._json({"shorts": shorts_state(), "jobs": JOBS.public(), "busy": JOBS.busy(), "log": TICK_LOG[-10:],
                                   "next_slot": schedule.next_free().isoformat(), "slots": schedule.upcoming(7),
                                   "inbox": _new_inbox(),
                                   "tz": settings()["plan"]["timezone"], "ai_disclosure": settings().get("publish", {}).get("ai_disclosure", True),
                                   "platforms": settings().get("publish", {}).get("platforms", ["youtube", "tiktok"])})
            if path == "/api/connections":
                return self._json(connections())
            if path.startswith("/api/job/"):
                return self._json({"log": JOBS.log(path.split("/")[3])})
            if path == "/api/defaults":
                return self._json(publisher.defaults(q["id"]))
            if path == "/api/tiktok/creator":
                return self._json(tiktok.creator_info())
            if path == "/api/ads":
                return self._json(ads.candidates())
            if path == "/oauth/youtube/start":
                url, state = youtube.auth_url(connections()["youtube"]["redirect"])
                OAUTH[state] = {"platform": "youtube"}
                return self._redirect(url)
            if path == "/oauth/tiktok/start":
                url, state, verifier = tiktok.auth_url(connections()["tiktok"]["redirect"])
                OAUTH[state] = {"platform": "tiktok", "verifier": verifier}
                return self._redirect(url)
            if path.startswith("/oauth/") and path.rstrip("/").endswith("/callback"):
                plat = path.split("/")[2]
                st = OAUTH.pop(q.get("state", ""), None)
                if q.get("error") or not st or st["platform"] != plat:
                    return self._redirect(f"/#connect?err={q.get('error_description') or q.get('error') or 'state mismatch, try again'}")
                if plat == "youtube":
                    youtube.exchange(q["code"], connections()["youtube"]["redirect"])
                else:
                    tiktok.exchange(q["code"], connections()["tiktok"]["redirect"], st["verifier"])
                # the TikTok redirect lands on localhost; send the browser back to the studio origin
                return self._redirect(f"http://127.0.0.1:{settings().get('_studio_port', 8790)}/#connect?ok={plat}")
            return self._json({"error": "not found"}, 404)
        except NotConnected as e:
            return self._json({"error": str(e), "not_connected": True}, 409)
        except Exception as e:  # noqa: BLE001
            return self._json({"error": str(e)}, 500)

    def do_POST(self):  # noqa: C901
        path = urlparse(self.path).path
        try:
            if path == "/api/upload":  # drop a source video into inbox/
                name = re.sub(r"[^\w.\- ()\[\]]", "_", unquote(self.headers.get("X-Filename", "upload.mp4")))[:150]
                if Path(name).suffix.lower() not in VIDEO_EXT:
                    return self._json({"error": "only video files"}, 400)
                n, dst = int(self.headers["Content-Length"]), INBOX / name
                with open(dst, "wb") as f:
                    while n > 0:
                        chunk = self.rfile.read(min(n, 1 << 20))
                        if not chunk:
                            break
                        f.write(chunk)
                        n -= len(chunk)
                return self._json({"ok": True, "name": name})
            b = self._body()
            if path == "/api/make":
                urls = [u.strip() for u in re.split(r"[\s,]+", b.get("urls", "")) if u.strip().startswith("http")]
                if urls:
                    job = JOBS.add(f"Make shorts from {len(urls)} link(s)", ["add", *urls, "--run", "--no-open"])
                else:
                    job = JOBS.add("Make shorts from inbox", ["run", "--no-open"])
                return self._json(job)
            if path == "/api/revise":
                scope = "script" if b.get("scope") == "script" else "visuals"
                job = JOBS.add(f"Regenerate {b['id']} ({scope})", ["revise", b["id"], "--notes", b.get("notes") or "Make it better.", "--scope", scope])
                return self._json(job)
            if path == "/api/approve":
                publisher.approve(b["id"], b["slot"], b.get("targets") or {})
                threading.Thread(target=publisher.tick, daemon=True).start()  # YouTube uploads start right away
                return self._json({"ok": True})
            if path == "/api/unapprove":
                return self._json({"ok": True, "notes": publisher.unapprove(b["id"])})
            if path == "/api/reject":
                publisher.reject(b["id"], b.get("notes", ""))
                return self._json({"ok": True})
            if path == "/api/post-now":
                publisher.post_now(b["id"], b["platform"])
                return self._json({"ok": True})
            if path == "/api/keys":
                keys = {k: (b.get(k) or "").strip() for k in ("GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET", "TIKTOK_CLIENT_KEY", "TIKTOK_CLIENT_SECRET")}
                keys = {k: v for k, v in keys.items() if v}
                write_env(keys)
                os.environ.update(keys)
                return self._json({"ok": True, "saved": list(keys)})
            if path == "/api/disconnect":
                forget(b["platform"])
                return self._json({"ok": True})
            if path == "/api/stats":
                return self._json({"rows": publisher.refresh_metrics()})
            if path == "/api/ads/mark":
                ads.mark(b["id"], b["status"], b.get("spend"), b.get("note"))
                return self._json({"ok": True})
            return self._json({"error": "not found"}, 404)
        except (ValueError, KeyError) as e:
            return self._json({"error": str(e)}, 400)
        except NotConnected as e:
            return self._json({"error": str(e), "not_connected": True}, 409)
        except Exception as e:  # noqa: BLE001
            return self._json({"error": str(e)}, 500)


def serve(port: int = 8790, open_browser: bool = True) -> None:
    global JOBS
    settings()["_studio_port"] = port
    JOBS = Jobs()
    threading.Thread(target=_scheduler, daemon=True).start()
    srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    # TikTok's desktop redirect must use "localhost"; on some machines that resolves to ::1 first, so listen there too.
    try:
        import socket

        class V6(ThreadingHTTPServer):
            address_family = socket.AF_INET6

        srv6 = V6(("::1", port), Handler)
        threading.Thread(target=srv6.serve_forever, daemon=True).start()
    except OSError:
        pass
    url = f"http://127.0.0.1:{port}/"
    print(f"ClipForge studio: {url}  (Ctrl+C to stop; scheduled posts only go out while this is running)")
    if open_browser:
        threading.Timer(0.6, webbrowser.open, args=(url,)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
