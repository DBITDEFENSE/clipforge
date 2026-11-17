"""clipforge CLI."""
from __future__ import annotations

import json
import shutil
import subprocess
import time
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from . import db, ingest, pipeline
from .config import INBOX, MUSIC, ensure_dirs, secret, settings
from .schemas import Script, Story

app = typer.Typer(add_completion=False, help="ClipForge: long videos in, original shorts out.")
console = Console()


@app.command()
def add(urls: list[str] = typer.Argument(..., help="YouTube / X / any yt-dlp supported links")):
    """Download links into inbox/."""
    ensure_dirs()
    for u in urls:
        console.print(f"[cyan]download[/] {u}")
        p = ingest.download(u)
        console.print(f"  -> {p.name}")


@app.command()
def run(
    voice: Optional[str] = typer.Option(None, help="Override voice provider: elevenlabs | take | say"),
    per_day: Optional[int] = typer.Option(None, help="Shorts per day (default from settings)"),
    days: Optional[int] = typer.Option(None, help="How many days of posts to plan"),
):
    """Process everything new in inbox/ end to end."""
    ensure_dirs()
    if per_day:
        settings()["plan"]["per_day"] = per_day
    if days:
        settings()["plan"]["days"] = days
    secret("ANTHROPIC_API_KEY")
    if (voice or settings()["voice"]["provider"]) == "elevenlabs":
        secret("ELEVENLABS_API_KEY")
        secret("ELEVENLABS_VOICE_ID")
    t = time.time()
    results = pipeline.run(voice)
    _summary(results, time.time() - t)
    if results:
        gallery(True)


@app.command()
def make(
    script_path: Path = typer.Argument(..., help="A Script JSON (schemas.Script)"),
    story_path: Optional[Path] = typer.Option(None, help="Optional Story JSON for sources/kicker"),
    voice: Optional[str] = typer.Option(None, help="elevenlabs | take | say"),
    short_id: Optional[str] = typer.Option(None),
):
    """Produce one short from a script file (skips mining/writing). Useful for re-renders and testing."""
    script = Script.model_validate_json(script_path.read_text(encoding="utf-8"))
    story = Story.model_validate_json(story_path.read_text(encoding="utf-8")) if story_path else Story(
        topic=script.title, cluster="manual", category="cyber", key_facts=[], angle="", who_affected="", how_it_works="",
        sources=[], scores={"hook": 0, "clarity": 0, "curiosity": 0, "niche_fit": 0})
    sid = short_id or f"manual-{time.strftime('%Y%m%d-%H%M%S')}"
    t = time.time()
    _summary([pipeline.produce(sid, "manual", story, script, 0, voice)], time.time() - t)


@app.command()
def setup(port: int = typer.Option(8788)):
    """Open a local page to paste API keys (validated, saved to .env)."""
    from .setup_page import serve

    serve(port)


@app.command()
def status():
    """Show videos and shorts in the database."""
    with db.connect() as con:
        vids = con.execute("SELECT hash,title,status,error FROM videos ORDER BY created DESC LIMIT 20").fetchall()
        shorts = con.execute("SELECT id,status,out_dir,error FROM shorts ORDER BY updated DESC LIMIT 30").fetchall()
    t = Table("video", "status", "title", title="Videos")
    for v in vids:
        t.add_row(v["hash"], v["status"], (v["title"] or "")[:60])
    console.print(t)
    t = Table("short", "status", "output / error", title="Shorts")
    for s in shorts:
        t.add_row(s["id"], s["status"], s["out_dir"] or (s["error"] or "")[:80])
    console.print(t)


@app.command()
def doctor():
    """Check that every dependency and secret is in place."""
    ok = lambda b: "[green]ok[/]" if b else "[red]missing[/]"  # noqa: E731
    import torch

    rows = [
        ("ffmpeg", shutil.which("ffmpeg") is not None, ""),
        ("node / npx", shutil.which("npx") is not None, ""),
        ("remotion deps", (Path(__file__).parent.parent / "render" / "node_modules" / "remotion").exists(), "cd render && npm install"),
        ("CUDA GPU", torch.cuda.is_available(), torch.cuda.get_device_name(0) if torch.cuda.is_available() else "CPU fallback (slow)"),
        ("ANTHROPIC_API_KEY", bool(secret("ANTHROPIC_API_KEY", False)), "add to .env"),
        ("ELEVENLABS_API_KEY", bool(secret("ELEVENLABS_API_KEY", False)), "add to .env"),
        ("ELEVENLABS_VOICE_ID", bool(secret("ELEVENLABS_VOICE_ID", False)), "your voice clone's ID"),
        ("music tracks", any(p.suffix.lower() in {".mp3", ".wav", ".m4a", ".flac", ".ogg"} for p in MUSIC.iterdir()), f"drop royalty-free tracks in {MUSIC} named <mood>__name.mp3"),
    ]
    t = Table("check", "status", "note")
    for name, good, note in rows:
        t.add_row(name, ok(good), note)
    console.print(t)
    console.print(f"inbox: {sum(1 for p in INBOX.iterdir() if p.suffix.lower() in {'.mp4', '.mkv', '.webm', '.mov'})} video(s)")


@app.command()
def gallery(open_it: bool = typer.Option(True, "--open/--no-open")):
    """Build out/gallery.html (every short with player, caption, hooks) and open it."""
    from . import gallery as g

    path = g.build()
    console.print(f"gallery: {path}")
    if open_it:
        import webbrowser

        webbrowser.open(path.as_uri())


@app.command()
def review():
    """(Phase 3: approve/reject/regenerate.) For now, opens the gallery."""
    gallery(True)


def _summary(results: list[dict], secs: float):
    t = Table("short", "status", "title", "output / error", title=f"Done in {secs / 60:.1f} min")
    for r in results:
        color = {"done": "green", "flagged": "yellow", "failed": "red"}.get(r["status"], "white")
        t.add_row(r["id"], f"[{color}]{r['status']}[/]", r.get("title", "")[:40], r.get("out") or r.get("error", "")[:80])
    console.print(t)


if __name__ == "__main__":
    app()
