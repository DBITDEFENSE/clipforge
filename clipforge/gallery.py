"""out/gallery.html: every short with a player, caption, hooks and QA, newest first. Static, opens from disk."""
from __future__ import annotations

import html
import json
from pathlib import Path

from .config import OUT

CSS = """
:root{--bg:#0A0B0D;--panel:#14161A;--line:#ffffff12;--text:#F2F4F7;--muted:#8A93A0;--accent:#00E0FF;--warn:#FF4D3D;--ok:#3DF2A6}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font:14px/1.5 system-ui,Segoe UI,sans-serif}
header{padding:28px 24px 8px}h1{margin:0;font-size:28px;letter-spacing:-.02em}h1 b{color:var(--accent)}header p{color:var(--muted);margin:4px 0 0}
h2{font-size:13px;letter-spacing:.12em;text-transform:uppercase;color:var(--muted);margin:28px 24px 12px}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:18px;padding:0 24px 40px}
.card{background:var(--panel);border:1px solid var(--line);border-radius:18px;overflow:hidden;display:flex;flex-direction:column}
video{width:100%;aspect-ratio:9/16;background:#000;display:block}
.b{padding:14px 16px 16px;display:flex;flex-direction:column;gap:8px}.t{font-weight:700;font-size:16px}
.pill{display:inline-block;font:600 11px ui-monospace,Consolas,monospace;padding:3px 8px;border-radius:6px;margin-right:6px}
.ok{background:#3DF2A622;color:var(--ok)}.bad{background:#FF4D3D22;color:var(--warn)}
.cap{background:#0005;border:1px solid var(--line);border-radius:10px;padding:10px;white-space:pre-wrap;font-size:13px}
details summary{cursor:pointer;color:var(--accent);font-size:13px}ol{margin:6px 0 0;padding-left:18px;color:var(--muted)}
button{align-self:flex-start;background:none;border:1px solid var(--line);color:var(--text);border-radius:8px;padding:6px 10px;cursor:pointer}
"""


def build() -> Path:
    shorts = sorted(OUT.glob("*/*/final.mp4"), key=lambda p: (p.parent.parent.name, p.stat().st_mtime), reverse=True)
    by_date: dict[str, list[str]] = {}
    for mp4 in shorts:
        d = mp4.parent
        read = lambda n: (d / n).read_text(encoding="utf-8") if (d / n).exists() else ""  # noqa: E731
        qa = json.loads(read("qa.json") or "{}")
        hooks = json.loads(read("hooks.json") or "[]")
        title = (read("script.md").splitlines() or ["# " + d.name])[0].lstrip("# ")
        caption = read("caption.txt").split("--- pinned")[0].strip()
        fails = [c["name"] for c in qa.get("checks", []) if not c["ok"]]
        pill = '<span class="pill ok">QA PASS</span>' if qa.get("passed") else f'<span class="pill bad">FLAGGED: {", ".join(fails)}</span>'
        rel = lambda p: p.relative_to(OUT).as_posix()  # noqa: E731
        hooks_html = "".join(f"<li><b>{html.escape(h['spoken'])}</b><br>on screen: {html.escape(h['on_screen'])}</li>" for h in hooks)
        by_date.setdefault(d.parent.name, []).append(f"""
<div class="card"><video controls preload="metadata" poster="{rel(d / 'cover.png')}" src="{rel(mp4)}"></video>
<div class="b"><div class="t">{html.escape(title)}</div><div>{pill}<span class="pill" style="background:#ffffff0d">{d.name}</span></div>
<div class="cap">{html.escape(caption)}</div><button onclick="navigator.clipboard.writeText(this.previousElementSibling.innerText);this.textContent='Copied'">Copy caption</button>
<details><summary>Hook options</summary><ol>{hooks_html}</ol></details>
<details><summary>Script</summary><div class="cap">{html.escape(read('script.md'))}</div></details></div></div>""")
    body = "".join(f"<h2>Post date {date}</h2><div class='grid'>{''.join(cards)}</div>" for date, cards in sorted(by_date.items(), reverse=True))
    page = (f"<!doctype html><html><head><meta charset='utf-8'><title>ClipForge shorts</title><style>{CSS}</style></head><body>"
            f"<header><h1>Clip<b>Forge</b> shorts</h1><p>{len(shorts)} short(s). Files live in out/&lt;date&gt;/&lt;id&gt;/.</p></header>"
            f"{body or '<h2>No shorts yet</h2>'}</body></html>")
    path = OUT / "gallery.html"
    OUT.mkdir(parents=True, exist_ok=True)
    path.write_text(page, encoding="utf-8")
    return path
