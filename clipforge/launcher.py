"""`clipforge launcher`: the front door. One local page (127.0.0.1) to open the studio, see what's new, check that
everything is installed, and update.

Updates and news come from the GitHub repo named in settings.yaml (`launcher.repo` / `launcher.branch`):
  pyproject.toml  -> latest version (compared with the installed one)
  news.json       -> the news feed (falls back to the local copy when offline)

The launcher never replaces files itself. "Update" writes data/update-request.json and exits with code 42;
launcher.ps1 (which ClipForge.bat runs) sees that, updates the files and dependencies while no Python is running,
and starts the launcher again. Stays light on imports (no torch) so it opens fast.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import socket
import subprocess
import sys
import threading
import time
import tomllib
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import httpx

from .config import DATA, RENDER, ROOT, settings
from .setup_page import read_env

UPDATE_EXIT = 42
STUDIO_PORT, SETUP_PORT = 8790, 8788
REQUEST = DATA / "update-request.json"
RESULT = DATA / "update-result.json"
SLUG = re.compile(r"[\w.-]+/[\w.-]+")
BRANCH = re.compile(r"[\w./-]+")


def source() -> tuple[str, str]:
    """(owner/repo, branch) to update from; repo is '' when not configured or malformed."""
    cfg = settings().get("launcher") or {}
    repo, branch = str(cfg.get("repo") or "").strip(), str(cfg.get("branch") or "main").strip()
    return (repo if SLUG.fullmatch(repo) else "", branch if BRANCH.fullmatch(branch) else "main")


def version_tuple(v: str) -> tuple[int, ...]:
    return tuple(int(x) for x in re.findall(r"\d+", v or "")[:4])


def is_newer(latest: str, installed: str) -> bool:
    return bool(version_tuple(latest)) and version_tuple(latest) > version_tuple(installed)


def local_version() -> str:
    try:
        return tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
    except (OSError, KeyError, tomllib.TOMLDecodeError):
        return "0"


def clean_news(raw) -> list[dict]:
    """Keep well-formed items only, as plain strings, newest first. The feed is remote content: text, never markup."""
    items = raw.get("news") if isinstance(raw, dict) else raw
    out = []
    for it in items if isinstance(items, list) else []:
        if isinstance(it, dict) and it.get("title"):
            out.append({"date": str(it.get("date") or "")[:10], "title": str(it["title"])[:140], "body": str(it.get("body") or "")[:1200],
                        "tag": str(it.get("tag") or "")[:20], "version": str(it.get("version") or "")[:20]})
    return sorted(out, key=lambda x: x["date"], reverse=True)[:30]


def local_news() -> list[dict]:
    try:
        return clean_news(json.loads((ROOT / "news.json").read_text(encoding="utf-8")))
    except (OSError, ValueError):
        return []


def fetch_remote(repo: str, branch: str, get=None) -> dict:
    """Latest version + news from the repo. `get(url) -> text` is injectable for tests."""
    if get is None:
        def get(url: str) -> str:
            r = httpx.get(url, timeout=8, follow_redirects=True)
            r.raise_for_status()
            return r.text
    base = f"https://raw.githubusercontent.com/{repo}/{branch}"
    latest = tomllib.loads(get(f"{base}/pyproject.toml"))["project"]["version"]
    try:
        news = clean_news(json.loads(get(f"{base}/news.json")))
    except Exception:  # noqa: BLE001  (news is optional; the version check still counts)
        news = []
    return {"latest": str(latest), "news": news}


class Remote:
    """Background, cached check of the update source so the page never waits on the network."""

    def __init__(self):
        self.lock = threading.Lock()
        self.data: dict | None = None
        self.error = ""
        self.checked = 0.0
        self.busy = False

    def refresh(self, force: bool = False) -> None:
        repo, branch = source()
        with self.lock:
            if self.busy or not repo or (not force and time.time() - self.checked < 600):
                return
            self.busy = True

        def work():
            try:
                data, err = fetch_remote(repo, branch), ""
            except Exception as e:  # noqa: BLE001
                data, err = None, ("update source not found (is the repo public?)" if "404" in str(e) else "couldn't reach the update source")
            with self.lock:
                self.data, self.error, self.checked, self.busy = data or self.data, err, time.time(), False

        threading.Thread(target=work, daemon=True).start()


REMOTE = Remote()
CHILD: dict[str, subprocess.Popen] = {}


def port_open(port: int) -> bool:
    with socket.socket() as s:
        s.settimeout(0.3)
        return s.connect_ex(("127.0.0.1", port)) == 0


def start(name: str, port: int, *args: str) -> None:
    """Run a clipforge command as a child process unless something already listens on its port."""
    if port_open(port):
        return
    CHILD[name] = subprocess.Popen([sys.executable, "-c", "from clipforge.cli import app; app()", *args], cwd=ROOT)
    for _ in range(100):
        if port_open(port) or CHILD[name].poll() is not None:
            return
        time.sleep(0.2)


def stop_children() -> None:
    for p in CHILD.values():
        if p.poll() is None:
            p.terminate()
    for p in CHILD.values():
        try:
            p.wait(timeout=8)
        except subprocess.TimeoutExpired:
            p.kill()


def checks() -> list[dict]:
    env = read_env()
    has = lambda k: bool(env.get(k) or os.environ.get(k))  # noqa: E731
    row = lambda name, ok, fix, need=True: {"name": name, "ok": bool(ok), "fix": "" if ok else fix, "required": need}  # noqa: E731
    return [
        row("ffmpeg", shutil.which("ffmpeg"), "Run install.ps1 again, or: winget install Gyan.FFmpeg"),
        row("Node.js", shutil.which("npx"), "Run install.ps1 again, or: winget install OpenJS.NodeJS.LTS"),
        row("Video renderer", (RENDER / "node_modules" / "remotion").exists(), "Close and reopen ClipForge to finish installing"),
        row("Claude key", has("ANTHROPIC_API_KEY"), "Add it under API keys"),
        row("ElevenLabs key", has("ELEVENLABS_API_KEY"), "Add it under API keys"),
        row("ElevenLabs voice", has("ELEVENLABS_VOICE_ID"), "Pick one under API keys"),
        row("NVIDIA GPU", shutil.which("nvidia-smi"), "Optional: local voice, video and music models need one", need=False),
    ]


def last_update() -> dict | None:
    try:
        return json.loads(RESULT.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return None


def state() -> dict:
    REMOTE.refresh()
    repo, branch = source()
    installed = local_version()
    with REMOTE.lock:
        data, err, busy, checked = REMOTE.data, REMOTE.error, REMOTE.busy, REMOTE.checked
    latest = (data or {}).get("latest", "")
    return {
        "version": installed, "latest": latest, "update_available": is_newer(latest, installed),
        "repo": repo, "branch": branch, "checking": busy and not checked, "source_error": err,
        "news": (data or {}).get("news") or local_news(), "checks": checks(),
        "studio_running": port_open(STUDIO_PORT), "studio_url": f"http://127.0.0.1:{STUDIO_PORT}",
        "supervised": os.environ.get("CLIPFORGE_SUPERVISED") == "1", "dev_checkout": (ROOT / ".git").exists(),
        "last_update": last_update(),
    }


PAGE = r"""<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>ClipForge</title><style>
:root{--bg:#06070B;--panel:#11131A;--line:#ffffff14;--text:#fff;--muted:#8B93A7;--accent:#00E5FF;--lime:#E8FF3A;--bad:#FF3B30;--ok:#3DF2A6;--warn:#FFB020}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font:15px/1.5 system-ui,Segoe UI,sans-serif}
.w{max-width:900px;margin:0 auto;padding:40px 20px 80px}h1{font-size:38px;margin:0;letter-spacing:-.02em}h1 b{color:var(--accent)}
h2{font-size:13px;text-transform:uppercase;letter-spacing:.08em;color:var(--muted);margin:0 0 12px}
.top{display:flex;align-items:center;gap:12px;flex-wrap:wrap}.grow{flex:1}.muted{color:var(--muted)}.small{font-size:13px}
.pill{font-size:12px;font-weight:700;padding:3px 10px;border-radius:99px;background:#ffffff12;white-space:nowrap}
.pill.ok{background:#3DF2A61f;color:var(--ok)}.pill.warn{background:#FFB0201f;color:var(--warn)}.pill.bad{background:#FF3B301f;color:var(--bad)}
.panel{background:var(--panel);border:1px solid var(--line);border-radius:16px;padding:20px;margin-top:16px}
.hero{display:flex;align-items:center;gap:16px;flex-wrap:wrap}
button{height:44px;border:0;border-radius:12px;padding:0 18px;font:700 14px system-ui,Segoe UI,sans-serif;cursor:pointer;background:var(--accent);color:#001014}
button.big{height:58px;font-size:18px;padding:0 30px}button.ghost{background:transparent;color:var(--text);border:1px solid var(--line)}
button.lime{background:var(--lime);color:#111}button:disabled{opacity:.5;cursor:default}
.banner{border-color:#E8FF3A66;background:#E8FF3A0d}.banner.bad{border-color:#FF3B3066;background:#FF3B300d}
.cols{display:grid;grid-template-columns:1fr 1.4fr;gap:16px}@media(max-width:760px){.cols{grid-template-columns:1fr}}
.chk{display:flex;gap:10px;padding:8px 0;border-top:1px solid var(--line)}.chk:first-of-type{border-top:0}
.dot{width:10px;height:10px;border-radius:50%;margin-top:7px;flex:none;background:var(--ok)}.dot.bad{background:var(--bad)}.dot.opt{background:var(--muted)}
.news{padding:14px 0;border-top:1px solid var(--line)}.news:first-of-type{border-top:0;padding-top:0}.news b{font-size:16px}
.news p{margin:6px 0 0;color:#c9cfdb;white-space:pre-line}
#toast{position:fixed;left:50%;bottom:28px;transform:translateX(-50%);background:#1c1f29;border:1px solid var(--line);padding:10px 16px;border-radius:12px;display:none}
</style></head><body><div class="w">
<div class="top"><h1 class="grow">Clip<b>Forge</b></h1><span id="ver" class="pill">…</span><button class="ghost" onclick="act('check')">Check for updates</button><button class="ghost" onclick="quit()">Quit</button></div>
<div id="banner"></div>
<div class="panel hero"><div class="grow"><b style="font-size:20px">Studio</b><div class="muted" id="studio-note">Make, review, schedule and publish shorts.</div></div>
  <button class="ghost" onclick="openTool('setup')">API keys</button><button class="big" id="go" onclick="openTool('launch')">Open Studio</button></div>
<div class="cols"><div class="panel"><h2>This PC</h2><div id="checks" class="muted">Checking…</div></div>
<div class="panel"><h2>Latest news</h2><div id="news" class="muted">Loading…</div></div></div>
<p class="muted small" id="foot" style="margin-top:18px"></p>
</div><div id="toast"></div><script>
const $ = s => document.querySelector(s);
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
let S = null, updating = false, armed = false, gone = false;
function toast(m) { const t = $('#toast'); t.textContent = m; t.style.display = 'block'; clearTimeout(toast.t); toast.t = setTimeout(() => t.style.display = 'none', 4000); }
async function post(p) { const r = await fetch(p, {method: 'POST'}); const j = await r.json().catch(() => ({})); if (!r.ok || j.error) throw new Error(j.error || 'failed'); return j; }
async function load() {
  try { const r = await fetch('/api/state'); S = await r.json(); if (updating && gone) { location.reload(); return; } render(); }
  catch (e) { if (updating) gone = true; else $('#foot').textContent = 'ClipForge is closed. Start it again from the ClipForge shortcut.'; }
}
function render() {
  $('#ver').textContent = 'v' + S.version; $('#ver').className = 'pill ' + (S.update_available ? 'warn' : (S.latest ? 'ok' : ''));
  let b = '';
  if (updating) b = `<div class="panel banner"><b>Updating…</b><div class="muted">Progress is in the ClipForge window. This page comes back by itself when it's done.</div></div>`;
  else if (S.update_available) b = `<div class="panel banner hero"><div class="grow"><b>Version ${esc(S.latest)} is ready</b><div class="muted">You have ${esc(S.version)}. Your shorts, channels and keys stay as they are.${S.studio_running ? ' The studio closes during the update, so let running jobs finish first.' : ''}</div></div>
      <button class="lime" onclick="update()">${armed ? 'Confirm: update now' : 'Update'}</button></div>`;
  else if (S.last_update && !S.last_update.ok) b = `<div class="panel banner bad"><b>The last update didn't finish</b><div class="muted">${esc(S.last_update.message)}</div></div>`;
  $('#banner').innerHTML = b;
  $('#go').textContent = S.studio_running ? 'Open Studio' : 'Start Studio';
  $('#studio-note').textContent = S.studio_running ? 'Running at ' + S.studio_url : 'Make, review, schedule and publish shorts.';
  $('#checks').innerHTML = S.checks.map(c => `<div class="chk"><span class="dot ${c.ok ? '' : (c.required ? 'bad' : 'opt')}"></span><div><b>${esc(c.name)}</b>${c.ok ? '' : `<div class="muted small">${esc(c.fix)}</div>`}</div></div>`).join('');
  $('#news').innerHTML = S.news.length ? S.news.map(n => `<div class="news"><div class="top"><b class="grow">${esc(n.title)}</b>${n.version ? `<span class="pill">v${esc(n.version)}</span>` : ''}${n.tag ? `<span class="pill ok">${esc(n.tag)}</span>` : ''}</div>
      <div class="muted small">${esc(n.date)}</div><p>${esc(n.body)}</p></div>`).join('') : 'No news yet.';
  $('#foot').textContent = !S.repo ? 'Updates are off: no update source is set (launcher.repo in config/settings.yaml).'
    : S.checking ? 'Checking for updates…' : S.source_error ? 'Update check failed: ' + S.source_error + '.'
    : S.update_available ? '' : 'You are up to date. Updates come from github.com/' + S.repo + '.';
}
async function openTool(which) { const b = event.currentTarget, t = b.textContent; b.disabled = true; b.textContent = 'Starting…';
  try { const j = await post('/api/' + which); window.open(j.url, '_blank'); } catch (e) { toast(e.message); }
  b.disabled = false; b.textContent = t; load(); }
async function act(what) { try { await post('/api/' + what); toast('Checking…'); setTimeout(load, 2500); } catch (e) { toast(e.message); } }
async function update() { if (!armed) { armed = true; render(); setTimeout(() => { armed = false; if (!updating) render(); }, 6000); return; }
  try { await post('/api/update'); updating = true; render(); } catch (e) { armed = false; render(); toast(e.message); } }
async function quit() { try { await post('/api/quit'); } catch (e) {} document.body.innerHTML = '<div class="w"><h1>Clip<b>Forge</b></h1><p class="muted">Closed. You can close this tab.</p></div>'; clearInterval(tick); }
load(); const tick = setInterval(load, 3000);
</script></body></html>"""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _json(self, obj, code=200):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/api/state":
            return self._json(state())
        body = PAGE.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        # Local page only: refuse cross-site posts from other pages open in the browser.
        origin = self.headers.get("Origin")
        if origin and origin.split("://")[-1] != self.headers.get("Host"):
            return self._json({"error": "forbidden"}, 403)
        if self.path == "/api/launch":
            start("studio", STUDIO_PORT, "studio", "--no-open")
            if not port_open(STUDIO_PORT):
                return self._json({"error": "The studio didn't start. Look at the ClipForge window for the reason."}, 500)
            return self._json({"url": f"http://127.0.0.1:{STUDIO_PORT}"})
        if self.path == "/api/setup":
            start("setup", SETUP_PORT, "setup", "--no-open")
            return self._json({"url": f"http://127.0.0.1:{SETUP_PORT}"})
        if self.path == "/api/check":
            REMOTE.refresh(force=True)
            return self._json({"ok": True})
        if self.path == "/api/update":
            repo, branch = source()
            if not repo:
                return self._json({"error": "No update source is set (launcher.repo in config/settings.yaml)."}, 400)
            if os.environ.get("CLIPFORGE_SUPERVISED") != "1":
                return self._json({"error": "Start ClipForge from ClipForge.bat (or the desktop shortcut) to update from here."}, 400)
            DATA.mkdir(parents=True, exist_ok=True)
            REQUEST.write_text(json.dumps({"repo": repo, "branch": branch}), encoding="utf-8")
            self._json({"ok": True})
            return _exit_soon(UPDATE_EXIT)
        if self.path == "/api/quit":
            self._json({"ok": True})
            return _exit_soon(0)
        self._json({"error": "not found"}, 404)


def _exit_soon(code: int) -> None:
    def go():
        stop_children()
        os._exit(code)

    threading.Timer(0.4, go).start()


def serve(port: int = 8787, open_browser: bool = True) -> None:
    url = f"http://127.0.0.1:{port}"
    if port_open(port):  # already running: just bring the page up
        print(f"ClipForge is already open: {url}")
        if open_browser:
            webbrowser.open(url)
        return
    srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"ClipForge: {url}  (keep this window open; Ctrl+C or Quit on the page to stop)")
    REMOTE.refresh()
    if open_browser:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        stop_children()
