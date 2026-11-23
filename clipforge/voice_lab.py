"""`clipforge voices`: audition voices on a real line, pick one, or clone your own. Local page on 127.0.0.1.

Samples are cached in data/voice_audition/ so re-opening the page costs nothing. "Use this voice" writes
ELEVENLABS_VOICE_ID (and optional per-voice settings) to .env / settings. Cloning uploads YOUR audio files to
ElevenLabs (POST /v1/voices/add) only when you press the button on the page.
"""
from __future__ import annotations

import base64
import json
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import httpx

from .config import DATA, secret, settings
from .setup_page import read_env, write_env

AUD = DATA / "voice_audition"
SAMPLE = ("Every Linux kernel since 2016 had a 9.8 bug in the TCP handshake. "
          "The fix? Two lines. Nobody blinked. Then it scored a 9.8, and everybody panicked.")

# Curated: American/creator-style male voices that suit fast cyber explainers. Any other voice on the account shows below.
PICKS = [
    ("TX3LPaxmHKxFdv7VOQHJ", "Liam", "energetic social-media creator"),
    ("R9RZPy40Zzy1wNxrgQpj", "Witty McGee", "sarcastic, hyped podcast host"),
    ("7zoixx2reelPHqsL6WsW", "Odom", "upbeat, playful, TV energy"),
    ("D67rM1z9DvsK9KkWi88m", "Mercer", "monotone, casual, deadpan"),
    ("pNInz6obpgDQGcFmaJgB", "Adam", "dominant, firm"),
    ("nPczCjzI2devNBz1zQrb", "Brian", "deep, resonant"),
    ("IKne3meq5aSn9XLyUdCD", "Charlie", "deep, confident, energetic (Aussie)"),
    ("iP95p4xoKVk53GoZ742B", "Chris", "charming, down-to-earth"),
    ("FXtFF6hdEEp8aY3YcMS8", "Damian", "steady baritone, conversational"),
    ("bIHbv24MWmeRgasZH58o", "Will", "relaxed, chill"),
]

# ElevenLabs voice-library voices for western/country channels. Shown only when they're on the account (add them from
# the ElevenLabs Voice Library first) and only for western channels.
COWBOY = [
    ("Bj9UqZbhQsanLzgalpEG", "Austin", "deep, raspy Texas good ol' boy (most used)"),
    ("ruirxsoakN0GWmGNIo04", "John Morgan", "gritty Southern cowboy"),
    ("KTPVrSVAEUSJRClDzBw7", "Bob", "rugged, warm cowboy"),
    ("0hh7H4ZVAtaGpm1VZyEN", "David", "deep, weathered Southern drawl"),
    ("Zg15Et3nnFl0MqqzwK3w", "Hayden", "young Texan, bold and clear"),
    ("nylWpjFYhUvfMc8YQinc", "Rio", "warm young Texan, conversational"),
    ("9T9vSqRrPPxIs5wpyZfK", "Eric", "confident, sassy Southern"),
    ("YXpFCvM1S3JbWEJhoskW", "Wyatt", "wise old rustic cowboy (slower)"),
    ("aOcS60CY8CoaVaZfqqb5", "Arthur", "engaging Southern cowboy narrator (slower)"),
]


def _key() -> str:
    return secret("ELEVENLABS_API_KEY")


def sample_path(voice_id: str, style: dict | None = None) -> Path:
    """Default-style samples are cached per voice; a custom style gets its own cached file."""
    from .voice import el_clean, el_defaults

    style = el_defaults() | el_clean(style or {})
    if style == el_defaults():
        return AUD / f"{voice_id}.mp3"
    import hashlib

    return AUD / f"{voice_id}-{hashlib.md5(json.dumps(style, sort_keys=True).encode()).hexdigest()[:10]}.mp3"


def make_sample(voice_id: str, style: dict | None = None) -> Path:
    from .voice import el_voice_settings

    p = sample_path(voice_id, style)
    if p.exists():
        return p
    cfg = settings()["voice"]
    r = httpx.post(
        f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}",
        params={"output_format": "mp3_44100_128"},
        headers={"xi-api-key": _key()},
        json={"text": SAMPLE, "model_id": cfg["model_id"],
              "voice_settings": el_voice_settings(style or {})},
        timeout=120,
    )
    if r.status_code != 200:
        raise RuntimeError(f"ElevenLabs {r.status_code}: {r.text[:200]}")
    AUD.mkdir(parents=True, exist_ok=True)
    p.write_bytes(r.content)
    return p


def account_voices() -> list[dict]:
    r = httpx.get("https://api.elevenlabs.io/v2/voices", headers={"xi-api-key": _key()}, params={"page_size": 100}, timeout=30)
    r.raise_for_status()
    out = []
    for v in r.json().get("voices", []):
        lab = v.get("labels") or {}
        out.append({"id": v["voice_id"], "name": v["name"], "category": v.get("category", ""),
                    "desc": " · ".join(x for x in [lab.get("accent"), lab.get("gender"), lab.get("descriptive"), lab.get("language")] if x)})
    return out


def clone(name: str, files: list[tuple[str, bytes]]) -> str:
    r = httpx.post("https://api.elevenlabs.io/v1/voices/add", headers={"xi-api-key": _key()},
                   data={"name": name, "remove_background_noise": "true", "description": "ClipForge narrator clone"},
                   files=[("files", (fn, data)) for fn, data in files], timeout=300)
    if r.status_code != 200:
        raise RuntimeError(f"ElevenLabs {r.status_code}: {r.text[:300]}")
    return r.json()["voice_id"]


PAGE = r"""<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>ClipForge voices</title><style>
:root{--bg:#06070B;--panel:#11131A;--line:#ffffff14;--text:#fff;--muted:#8B93A7;--accent:#00E5FF;--pink:#FF2D87;--lime:#E8FF3A;--bad:#FF3B30}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font:15px/1.5 system-ui,Segoe UI,sans-serif}
.w{max-width:760px;margin:0 auto;padding:40px 16px 80px}h1{font-size:34px;margin:0 0 6px;letter-spacing:-.02em}h1 b{color:var(--accent)}
h2{font-size:18px;margin:36px 0 12px}p{color:var(--muted);margin:0 0 18px}
.v{display:grid;grid-template-columns:1fr auto;gap:8px 14px;align-items:center;background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:14px 16px;margin:10px 0}
.v.cur{border-color:var(--lime);box-shadow:0 0 0 1px var(--lime) inset}.n{font-weight:800}.d{color:var(--muted);font-size:13px}
audio{width:100%;grid-column:1/-1;height:36px}button{height:40px;border:0;border-radius:10px;padding:0 16px;font-weight:800;cursor:pointer;background:var(--accent);color:#001014}
button.ghost{background:transparent;color:var(--text);border:1px solid var(--line)}.tag{color:var(--lime);font-size:12px;font-weight:800;margin-left:8px}
.drop{border:2px dashed #ffffff30;border-radius:14px;padding:22px;text-align:center;color:var(--muted)}input[type=text]{height:40px;border-radius:10px;border:1px solid var(--line);background:var(--panel);color:#fff;padding:0 12px;width:100%;margin:10px 0}
#msg{position:fixed;left:50%;bottom:20px;transform:translateX(-50%);background:var(--lime);color:#000;font-weight:800;padding:10px 18px;border-radius:12px;display:none}
details summary{cursor:pointer;color:var(--muted)}
</style></head><body><div class="w">
<h1>Pick the <b>voice</b></h1><p>Same line, every voice. Hit play, then "Use this". New shorts use it right away; <code>clipforge redo &lt;id&gt; --revoice</code> re-voices old ones.</p>
<div id="picks"></div>
<details><summary>Every other voice on your account</summary><div id="rest"></div></details>
<h2>Clone your own voice</h2>
<p>Best option: it sounds like you. Upload 1–3 minutes of clean audio of just you talking (an mp3/wav/m4a, or a few). No music, no other people.</p>
<input type="text" id="cname" value="Devin (ClipForge)"><div class="drop"><input type="file" id="files" multiple accept="audio/*,video/mp4"></div>
<p style="margin-top:12px"><button id="clone">Clone and use it</button></p>
</div><div id="msg"></div><script>
const $=id=>document.getElementById(id);const toast=t=>{$('msg').textContent=t;$('msg').style.display='block';setTimeout(()=>$('msg').style.display='none',3500)};
let cur='';
function card(v,lazy){return `<div class="v ${v.id===cur?'cur':''}" id="v_${v.id}"><div><span class="n">${v.name}</span>${v.id===cur?'<span class="tag">IN USE</span>':''}<div class="d">${v.desc||''}</div></div>
<button onclick="use('${v.id}','${v.name.replace(/'/g,'')}')">Use this</button>${lazy?`<button class="ghost" style="grid-column:1/-1" onclick="gen(this,'${v.id}')">Generate sample</button>`:`<audio controls preload="none" src="/sample/${v.id}.mp3"></audio>`}</div>`}
async function load(){const j=await (await fetch('/api/list')).json();cur=j.current;$('picks').innerHTML=j.picks.map(v=>card(v,false)).join('');$('rest').innerHTML=j.rest.map(v=>card(v,true)).join('');}
async function use(id,name){const j=await (await fetch('/api/use',{method:'POST',body:JSON.stringify({id})})).json();if(j.ok){toast('Using '+name);load();}else toast(j.error)}
async function gen(b,id){b.textContent='generating...';const r=await fetch('/sample/'+id+'.mp3');if(!r.ok){b.textContent='failed';return}b.outerHTML=`<audio controls autoplay src="/sample/${id}.mp3"></audio>`}
$('clone').onclick=async()=>{const fs=$('files').files;if(!fs.length){toast('Pick audio files first');return}$('clone').textContent='Uploading + cloning...';
 const parts=[];for(const f of fs){const b=await f.arrayBuffer();let s='';const u=new Uint8Array(b);for(let i=0;i<u.length;i+=32768)s+=String.fromCharCode.apply(null,u.subarray(i,i+32768));parts.push({name:f.name,b64:btoa(s)})}
 const j=await (await fetch('/api/clone',{method:'POST',body:JSON.stringify({name:$('cname').value,files:parts})})).json();$('clone').textContent='Clone and use it';
 if(j.ok){toast('Cloned and in use');load()}else toast(j.error)};
load();
</script></body></html>"""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, body: bytes, ctype: str, code: int = 200):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, code=200):
        self._send(json.dumps(obj).encode(), "application/json", code)

    def do_GET(self):
        if self.path == "/":
            return self._send(PAGE.encode(), "text/html; charset=utf-8")
        if self.path == "/api/list":
            cur = read_env().get("ELEVENLABS_VOICE_ID", "")
            try:
                acct = account_voices()
            except Exception as e:  # noqa: BLE001
                return self._json({"error": str(e)}, 500)
            by_id = {v["id"]: v for v in acct}
            picks = [{"id": i, "name": n, "desc": d} for i, n, d in PICKS if i in by_id]
            ids = {p["id"] for p in picks}
            rest = sorted([v for v in acct if v["id"] not in ids], key=lambda v: (v["category"] not in {"cloned", "generated"}, v["name"]))
            if cur and cur not in ids:  # show the voice in use at the top
                hit = [v for v in rest if v["id"] == cur]
                rest = [v for v in rest if v["id"] != cur]
                picks = hit + picks
            return self._json({"current": cur, "picks": picks, "rest": rest})
        if self.path.startswith("/sample/") and self.path.endswith(".mp3"):
            vid = self.path[len("/sample/"):-4]
            if not vid.isalnum():
                return self._json({"error": "bad id"}, 400)
            try:
                return self._send(make_sample(vid).read_bytes(), "audio/mpeg")
            except Exception as e:  # noqa: BLE001
                return self._json({"error": str(e)}, 502)
        self._json({"error": "not found"}, 404)

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
        if self.path == "/api/use":
            vid = str(body.get("id", ""))
            if not vid.isalnum():
                return self._json({"ok": False, "error": "bad id"})
            write_env({"ELEVENLABS_VOICE_ID": vid})
            return self._json({"ok": True})
        if self.path == "/api/clone":
            try:
                files = [(f["name"], base64.b64decode(f["b64"])) for f in body.get("files", [])]
                vid = clone(str(body.get("name") or "ClipForge clone")[:60], files)
                write_env({"ELEVENLABS_VOICE_ID": vid})
                return self._json({"ok": True, "id": vid})
            except Exception as e:  # noqa: BLE001
                msg = str(e)
                if "missing the permission" in msg:
                    msg = "Your ElevenLabs key can't create voices. Make a key with Voices: Write, paste it in `clipforge setup`, retry."
                return self._json({"ok": False, "error": msg})
        self._json({"error": "not found"}, 404)


def warm() -> None:
    """Pre-generate the curated samples so the page plays instantly."""
    for vid, _, _ in PICKS:
        try:
            make_sample(vid)
        except Exception:  # noqa: BLE001
            pass


def serve(port: int = 8789, open_browser: bool = True) -> None:
    srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    url = f"http://127.0.0.1:{port}/"
    print(f"Voice lab: {url}  (Ctrl+C to stop)")
    if open_browser:
        threading.Timer(0.5, webbrowser.open, args=(url,)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
