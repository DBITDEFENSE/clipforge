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


@app.callback()
def _global(account: Optional[str] = typer.Option(None, "--account", "-a", help="Channel account id (e.g. cyber-cowboy). Default: first account.")):
    import os

    from . import accounts

    accounts.ensure()
    if account:
        accounts.get(account)  # fail fast on a typo
        os.environ["CLIPFORGE_ACCOUNT"] = account


@app.command()
def channels():
    """List channel accounts."""
    from . import accounts

    t = Table("id", "name", "handle", "voice", "password")
    for a in accounts.all_accounts():
        t.add_row(a["id"], a["name"], a.get("handle") or "", (a["voice"] or {}).get("voice_id", ""), "yes" if a.get("password_hash") else "")
    console.print(t)


@app.command()
def add(
    urls: list[str] = typer.Argument(..., help="YouTube / X / any yt-dlp supported links (as many as you want)"),
    go: bool = typer.Option(False, "--run", help="Process everything right after downloading"),
    open_it: bool = typer.Option(True, "--open/--no-open"),
):
    """Download links into inbox/. With --run, make the shorts too."""
    ensure_dirs()
    for u in urls:
        console.print(f"[cyan]download[/] {u}")
        try:
            p = ingest.download(u)
            console.print(f"  -> {p.name}")
        except Exception as e:  # one bad link shouldn't sink the batch
            console.print(f"  [red]failed[/]: {e}")
    if go:
        run(None, None, None, open_it)


@app.command()
def run(
    voice: Optional[str] = typer.Option(None, help="Override voice provider: elevenlabs | take | say"),
    per_day: Optional[int] = typer.Option(None, help="Shorts per day (default from settings)"),
    days: Optional[int] = typer.Option(None, help="How many days of posts to plan"),
    open_it: bool = typer.Option(True, "--open/--no-open", help="Open the gallery when done"),
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
    t = time.time()
    results = pipeline.run(voice)
    _summary(results, time.time() - t)
    if results and open_it:
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
def redo(
    short_ids: list[str] = typer.Argument(..., help="Short IDs to re-direct and re-render (voice is reused, no TTS cost)"),
    keep_shots: bool = typer.Option(False, "--keep-shots", help="Reuse the existing shot plan too (render-only, no Claude calls)"),
    revoice: bool = typer.Option(False, "--revoice", help="Re-synthesize the voice with the current voice/settings (uses TTS credits)"),
    open_it: bool = typer.Option(True, "--open/--no-open"),
):
    """Re-run shots -> render -> finish -> QA for existing shorts, keeping their script and voice."""
    from .config import WORK

    results, t = [], time.time()
    for sid in short_ids:
        work = WORK / "shorts" / sid
        script = Script.model_validate_json((work / "script.json").read_text(encoding="utf-8"))
        with db.connect() as con:
            row = con.execute("SELECT data, day, batch_id FROM stories WHERE id=?", (sid,)).fetchone()
        story = Story.model_validate_json(row["data"]) if row else Story(
            topic=script.title, cluster="manual", category="cyber", key_facts=[], angle="", who_affected="", how_it_works="",
            sources=[], scores={"hook": 0, "clarity": 0, "curiosity": 0, "niche_fit": 0})
        results.append(pipeline.produce(sid, row["batch_id"] if row else "manual", story, script, (row["day"] or 0) if row else 0,
                                        reuse_voice=not revoice, keep_shots=keep_shots and not revoice))
    _summary(results, time.time() - t)
    if open_it:
        gallery(True)


def _load(sid: str) -> tuple[Script, Story, str, int]:
    from .config import WORK

    script = Script.model_validate_json((WORK / "shorts" / sid / "script.json").read_text(encoding="utf-8"))
    with db.connect() as con:
        row = con.execute("SELECT data, day, batch_id FROM stories WHERE id=?", (sid,)).fetchone()
    story = Story.model_validate_json(row["data"]) if row else Story(
        topic=script.title, cluster="manual", category="cyber", key_facts=[], angle="", who_affected="", how_it_works="",
        sources=[], scores={"hook": 0, "clarity": 0, "curiosity": 0, "niche_fit": 0})
    return script, story, (row["batch_id"] if row else "manual"), ((row["day"] or 0) if row else 0)


@app.command()
def revise(
    short_id: str = typer.Argument(...),
    notes: str = typer.Option(..., "--notes", help="What to change, in your words"),
    scope: str = typer.Option("visuals", help="visuals (re-direct + re-render, no TTS) | script (rewrite + re-voice + re-render)"),
):
    """Regenerate one short with your notes."""
    from . import schedule, write
    from .config import WORK

    script, story, batch, day = _load(short_id)
    t = time.time()
    if scope == "script":
        new, issues = write.review(short_id, story, script, notes)
        (WORK / "shorts" / short_id / "revision_notes.json").write_text(json.dumps({"notes": notes, "issues": issues}, indent=2), encoding="utf-8")
        console.print(f"[cyan]rewrote[/] {short_id}: {len(issues)} change(s)")
        res = pipeline.produce(short_id, batch, story, new, day)
    else:
        res = pipeline.produce(short_id, batch, story, script, day, reuse_voice=True, director_notes=notes)
    schedule.set_review(short_id, "pending", None, notes)
    _summary([res], time.time() - t)


@app.command()
def autopilot(
    follow: Optional[str] = typer.Option(None, help="Follow a channel URL or @handle for this account"),
    backfill: int = typer.Option(0, help="With --follow: also process this many of its latest uploads"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Just show what's new"),
    open_it: bool = typer.Option(False, "--open/--no-open"),
):
    """Check followed channels for new uploads and make shorts from them (they land in Review)."""
    from . import accounts
    from . import autopilot as ap

    acc = accounts.current_id()
    if follow:
        s = ap.add_source(acc, follow, backfill)
        console.print(f"following [cyan]{s['label']}[/] ({s['url']}); latest: {[x['title'][:50] for x in s['latest']]}")
        return
    cfg = ap.config(acc)
    new = ap.new_uploads(acc, int(cfg["max_videos"]), mark=not dry_run)
    if dry_run:
        for s in ap.sources(acc):
            console.print(f"following {s['label']}: {s['url']}")
        for it in new:
            console.print(f"[cyan]would make[/] {it['source']}: {it['title']}")
        if not new:
            console.print("No new uploads.")
        return
    if not new:
        console.print("No new uploads.")
        return
    for it in new:
        console.print(f"[cyan]new[/] {it['source']}: {it['title']}")
    add([it["url"] for it in new], True, open_it)


@app.command("video-test")
def video_test(prompt: str = typer.Option(..., help="What to generate")):
    """Generate one sample clip with this channel's video model -> out/_samples/."""
    from . import videogen
    from .config import OUT

    c = videogen.config()
    console.print(f"[cyan]video model[/] {c['engine']}: {c['model']}")
    (OUT / "_samples").mkdir(parents=True, exist_ok=True)
    t = time.time()
    got = videogen.generate(prompt, OUT / "_samples" / f"sample_{time.strftime('%Y%m%d-%H%M%S')}.mp4", "video-test", c)
    if not got:
        console.print("[red]no clip (engine is not an AI model, missing key, or the model failed; see above)[/]")
        raise typer.Exit(1)
    console.print(f"done in {time.time() - t:.0f}s: {got[0]}")


@app.command("music")
def music_cmd(per_mood: int = typer.Option(2, help="Tracks per mood (tops up; existing tracks are kept)"),
              seconds: float = typer.Option(45.0, help="Track length"),
              mood: list[str] = typer.Option(None, help="Only these moods (tense, dark, driving, curious, upbeat)"),
              replace: bool = typer.Option(False, help="Delete this channel's AI tracks first and regenerate")):
    """Generate this channel's background-music library locally with ACE-Step 1.5 -> assets/music/<channel>/."""
    from . import accounts, music

    acc = accounts.current_id()
    c = music.config(acc)
    console.print(f"[cyan]music[/] {acc}: {c['style_effective']}")
    t = time.time()
    made = music.build_library(acc, per_mood, seconds, mood or None, replace)
    console.print(f"{len(made)} new track(s) in {time.time() - t:.0f}s -> {music.folder(acc)}")


@app.command()
def remix(short_ids: list[str] = typer.Argument(None, help="Short IDs (default: every finished short on this channel)")):
    """Re-mix the audio (current music library + loudness) on existing shorts without re-rendering. Seconds each."""
    from . import accounts, db, pipeline

    if not short_ids:
        with db.connect() as con:
            short_ids = [r[0] for r in con.execute("SELECT id FROM shorts WHERE account=? AND status IN ('done','preview','flagged')"
                                                  " AND (review IS NULL OR review != 'rejected')", (accounts.current_id(),))]
    for sid in short_ids:
        try:
            r = pipeline.remix(sid)
            console.print(f"[green]{r['status']}[/] {sid}: {r['music'] or 'no music'}")
        except Exception as e:  # noqa: BLE001
            console.print(f"[red]skip[/] {sid}: {e}")


@app.command("publish-due")
def publish_due():
    """Publish whatever is due (TikTok slots that arrived, pending YouTube uploads) and update post statuses."""
    from . import publisher

    for line in publisher.tick() or ["nothing due"]:
        console.print(line)


@app.command()
def stats():
    """Pull views/likes/comments/shares for posted shorts, then show ad candidates."""
    from . import ads, publisher

    console.print(f"metrics rows: {publisher.refresh_metrics()}")
    t = Table("short", "platform", "views", "engagement", "why", title="Ad candidates")
    for c in ads.candidates():
        t.add_row(c["short_id"], c["platform"], str(c["views"]), f"{c['engagement']:.1%}", ", ".join(c["why"]))
    console.print(t)


@app.command()
def studio(port: int = typer.Option(8790), open_it: bool = typer.Option(True, "--open/--no-open")):
    """The app: make shorts from links, review, schedule, publish, track."""
    from .studio import serve

    serve(port, open_it)


@app.command()
def setup(port: int = typer.Option(8788)):
    """Open a local page to paste API keys (validated, saved to .env)."""
    from .setup_page import serve

    serve(port)


@app.command()
def voices(port: int = typer.Option(8789)):
    """Audition voices on a real line, pick one, or clone your own."""
    from .voice_lab import serve

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
        ("music tracks", any(p.suffix.lower() in {".mp3", ".wav", ".m4a", ".flac", ".ogg"} for p in MUSIC.rglob("*")), "make a library: clipforge music (or drop tracks in assets/music named <mood>__name.mp3)"),
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
    """Approve / reject / regenerate: opens the studio."""
    studio(8790, True)


def _summary(results: list[dict], secs: float):
    t = Table("short", "status", "title", "output / error", title=f"Done in {secs / 60:.1f} min")
    for r in results:
        color = {"done": "green", "flagged": "yellow", "failed": "red"}.get(r["status"], "white")
        t.add_row(r["id"], f"[{color}]{r['status']}[/]", r.get("title", "")[:40], r.get("out") or r.get("error", "")[:80])
    console.print(t)


if __name__ == "__main__":
    app()
