"""`clipforge setup`: a local page to paste API keys. Validates each key with read-only calls and saves .env.

Bound to 127.0.0.1 only. Keys go straight from your browser to this file; nothing else stores them.
Only read-only endpoints are called (list models, list voices, one stock search). No account settings are touched.
"""
from __future__ import annotations

import json
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import httpx

from .config import ROOT

ENV = ROOT / ".env"
FIELDS = ["ANTHROPIC_API_KEY", "ELEVENLABS_API_KEY", "ELEVENLABS_VOICE_ID", "PEXELS_API_KEY"]

PAGE = r"""<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>ClipForge setup</title><style>
:root{--bg:#0A0B0D;--panel:#14161A;--line:#ffffff14;--text:#F2F4F7;--muted:#8A93A0;--accent:#00E0FF;--bad:#FF4D3D;--ok:#3DF2A6}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font:15px/1.5 system-ui,Segoe UI,sans-serif}
.w{max-width:620px;margin:0 auto;padding:48px 20px}h1{font-size:34px;margin:0 0 6px;letter-spacing:-.02em}h1 b{color:var(--accent)}
p{color:var(--muted);margin:0 0 28px}label{display:block;font-weight:600;margin:22px 0 6px}small{color:var(--muted);font-weight:400}
input,select{width:100%;height:46px;border-radius:12px;border:1px solid var(--line);background:var(--panel);color:var(--text);padding:0 14px;font:14px ui-monospace,Consolas,monospace}
input:focus,select:focus{outline:2px solid var(--accent);border-color:transparent}
.row{display:flex;gap:8px}.row input{flex:1}button{height:46px;border:0;border-radius:12px;padding:0 18px;font-weight:700;cursor:pointer}
.ghost{background:var(--panel);color:var(--text);border:1px solid var(--line)}.go{width:100%;margin-top:30px;background:var(--accent);color:#001014;font-size:16px}
.st{font:13px ui-monospace,Consolas,monospace;margin-top:6px;min-height:18px}.ok{color:var(--ok)}.bad{color:var(--bad)}
#done{display:none;margin-top:24px;padding:16px;border-radius:12px;background:#3DF2A614;border:1px solid #3DF2A655}
</style></head><body><div class="w">
<h1>Clip<b>Forge</b> setup</h1><p>Paste your keys. Each one is checked with a read-only call, then saved to <code>.env</code> on this PC.</p>
<label>Anthropic API key <small>console.anthropic.com → API keys</small></label>
<input id="ANTHROPIC_API_KEY" placeholder="sk-ant-..." autocomplete="off"><div class="st" id="s_ANTHROPIC_API_KEY"></div>
<label>ElevenLabs API key <small>elevenlabs.io → profile → API keys</small></label>
<div class="row"><input id="ELEVENLABS_API_KEY" placeholder="sk_..." autocomplete="off"><button class="ghost" id="load">Load my voices</button></div>
<div class="st" id="s_ELEVENLABS_API_KEY"></div>
<label>Your voice <small>pick your clone</small></label>
<select id="ELEVENLABS_VOICE_ID"><option value="">Load your voices first (or paste an ID below)</option></select>
<input id="voice_manual" placeholder="...or paste a voice ID" style="margin-top:8px" autocomplete="off">
<label>Pexels API key <small>optional, for stock B-roll · pexels.com/api (free)</small></label>
<input id="PEXELS_API_KEY" placeholder="optional" autocomplete="off"><div class="st" id="s_PEXELS_API_KEY"></div>
<button class="go" id="save">Check & save</button>
<div id="done">Saved. You can close this tab. Claude will take it from here.</div>
</div><script>
const $=id=>document.getElementById(id);
fetch('/api/current').then(r=>r.json()).then(c=>{for(const k in c){if(c[k]&&$(k)&&$(k).tagName==='INPUT')$(k).placeholder='saved (leave blank to keep)';}
 if(c.ELEVENLABS_VOICE_ID){$('voice_manual').placeholder='saved: '+c.ELEVENLABS_VOICE_ID_hint}});
async function post(u,b){const r=await fetch(u,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(b)});return r.json();}
$('load').onclick=async()=>{const s=$('s_ELEVENLABS_API_KEY');s.textContent='checking...';s.className='st';
 const j=await post('/api/voices',{key:$('ELEVENLABS_API_KEY').value.trim()});
 if(j.error){s.textContent='✗ '+j.error;s.className='st bad';return;}
 s.textContent='✓ key works · '+j.voices.length+' voices';s.className='st ok';
 $('ELEVENLABS_VOICE_ID').innerHTML=j.voices.map(v=>`<option value="${v.id}">${v.name} (${v.category})</option>`).join('');};
$('save').onclick=async()=>{const body={};for(const k of ['ANTHROPIC_API_KEY','ELEVENLABS_API_KEY','PEXELS_API_KEY'])body[k]=$(k).value.trim();
 body.ELEVENLABS_VOICE_ID=$('voice_manual').value.trim()||$('ELEVENLABS_VOICE_ID').value;
 $('save').textContent='Checking...';const j=await post('/api/save',body);$('save').textContent='Check & save';
 for(const k in j.results){const s=$('s_'+k);if(s){s.textContent=(j.results[k].ok?'✓ ':'✗ ')+j.results[k].msg;s.className='st '+(j.results[k].ok?'ok':'bad');}}
 if(j.saved)$('done').style.display='block';};
</script></body></html>"""


def read_env() -> dict:
    out = {}
    if ENV.exists():
        for line in ENV.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1)
                out[k.strip()] = v.strip()
    return out


def write_env(updates: dict) -> None:
    cur = read_env()
    cur.update({k: v for k, v in updates.items() if v})
    lines = [f"{k}={cur.get(k, '')}" for k in FIELDS] + [f"{k}={v}" for k, v in cur.items() if k not in FIELDS]
    ENV.write_text("\n".join(lines) + "\n", encoding="utf-8")


def check_anthropic(key: str) -> tuple[bool, str]:
    r = httpx.get("https://api.anthropic.com/v1/models?limit=1", headers={"x-api-key": key, "anthropic-version": "2023-06-01"}, timeout=20)
    return (True, "key works") if r.status_code == 200 else (False, f"rejected ({r.status_code})")


def el_voices(key: str) -> list[dict]:
    r = httpx.get("https://api.elevenlabs.io/v1/voices", headers={"xi-api-key": key}, timeout=20)
    if r.status_code != 200:
        raise ValueError(f"rejected ({r.status_code})")
    vs = r.json().get("voices", [])
    rank = {"professional": 0, "cloned": 1, "generated": 2}
    vs.sort(key=lambda v: (rank.get(v.get("category"), 3), v.get("name", "")))
    return [{"id": v["voice_id"], "name": v.get("name"), "category": v.get("category")} for v in vs]


def check_pexels(key: str) -> tuple[bool, str]:
    r = httpx.get("https://api.pexels.com/videos/search", params={"query": "server", "per_page": 1}, headers={"Authorization": key}, timeout=20)
    return (True, "key works") if r.status_code == 200 else (False, f"rejected ({r.status_code})")


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
        if self.path == "/api/current":
            env = read_env()
            vid = env.get("ELEVENLABS_VOICE_ID", "")
            return self._json({k: bool(env.get(k)) for k in FIELDS} | {"ELEVENLABS_VOICE_ID_hint": vid[:6] + "…" if vid else ""})
        body = PAGE.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        data = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
        env = read_env()
        if self.path == "/api/voices":
            try:
                return self._json({"voices": el_voices(data.get("key") or env.get("ELEVENLABS_API_KEY", ""))})
            except Exception as e:
                return self._json({"error": str(e)})
        if self.path == "/api/save":
            res, keep = {}, {}
            checks = {"ANTHROPIC_API_KEY": check_anthropic, "PEXELS_API_KEY": check_pexels,
                      "ELEVENLABS_API_KEY": lambda k: (bool(el_voices(k)) or True, "key works")}
            for k, fn in checks.items():
                val = data.get(k) or ""
                if not val:
                    res[k] = {"ok": bool(env.get(k)), "msg": "kept saved value" if env.get(k) else ("skipped" if k == "PEXELS_API_KEY" else "missing")}
                    continue
                try:
                    ok, msg = fn(val)
                except Exception as e:
                    ok, msg = False, str(e)[:120]
                res[k] = {"ok": ok, "msg": msg}
                if ok:
                    keep[k] = val
            if data.get("ELEVENLABS_VOICE_ID"):
                keep["ELEVENLABS_VOICE_ID"] = data["ELEVENLABS_VOICE_ID"]
            write_env(keep)
            required_ok = all(res[k]["ok"] for k in ("ANTHROPIC_API_KEY", "ELEVENLABS_API_KEY")) and bool(read_env().get("ELEVENLABS_VOICE_ID"))
            return self._json({"results": res, "saved": required_ok})
        self._json({"error": "not found"}, 404)


def serve(port: int = 8788, open_browser: bool = True) -> None:
    srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    url = f"http://127.0.0.1:{port}"
    print(f"ClipForge setup: {url}  (Ctrl+C to stop)")
    if open_browser:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    srv.serve_forever()
