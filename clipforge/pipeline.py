"""Orchestration: inbox -> transcripts -> stories -> scripts -> shorts in out/<date>/<short_id>/."""
from __future__ import annotations

import datetime as dt
import json
import shutil
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from rich.console import Console

from . import accounts, db, director, finish, ingest, mine, qa, render, shots, voice, write
from .config import OUT, WORK, settings
from .schemas import Script, Story, Word
from .transcribe import transcribe

console = Console()


def _moments(story: Story | None, work: Path) -> tuple[list[dict], Path | None]:
    """Source-footage candidates for the director (empty when the channel has footage off or nothing is on disk)."""
    from . import footage

    try:
        fc = footage.config()
        if story is None or fc["footage"] == "off" or int(fc["max_source_clips"]) <= 0:
            return [], None
        ms = footage.moments(story)
        (work / "moments.json").write_text(json.dumps(ms, indent=1), encoding="utf-8")
        return ms, footage.contact_sheet(ms, work / "moments.jpg") if ms else None
    except Exception as e:  # noqa: BLE001
        console.print(f"[yellow]source footage skipped ({str(e)[:160]})[/]")
        return [], None


def _direct_or_fallback(script: Script, words: list[Word], short_id: str, work: Path, notes: str = "",
                        story: Story | None = None) -> dict:
    """Claude-directed shots; on any failure, the deterministic planner. Always returns a validated doc."""
    try:
        console.print(f"[cyan]direct[/] {short_id}")
        ms, sheet = _moments(story, work)
        if ms:
            console.print(f"  {len(ms)} source moments offered")
        plan = director.direct(script, words, short_id, notes, ms, sheet)
        (work / "shot_plan.json").write_text(plan.model_dump_json(indent=2), encoding="utf-8")
        try:
            doc, notes = director.to_doc(plan, script, words, short_id, work, ms)
        finally:
            from . import videogen

            videogen.release()  # free the local video model's VRAM before rendering
        if notes:
            console.print(f"  director repairs: {'; '.join(notes[:6])}")
        return doc
    except Exception as e:
        console.print(f"[yellow]director failed ({e}); using the built-in planner[/]")
        doc = shots.build(script, words, short_id)
        doc["planner"] = f"fallback: {str(e)[:200]}"
        shots.validate(doc)
        return doc


def _clean_old_outputs(short_id: str, keep: Path) -> None:
    """A re-render can land under a new post date; drop older copies so the studio shows one card per short."""
    for d in OUT.glob(f"*/{short_id}"):
        if d.resolve() != keep.resolve() and d.is_dir():
            shutil.rmtree(d, ignore_errors=True)


def _add_meme(doc: dict, script: Script, short_id: str, work: Path) -> dict:
    """AI meme in the first 6 seconds. Never blocks the short."""
    from . import meme, sfx

    try:
        spec = meme.write(script, short_id)
        (work / "meme.json").write_text(spec.model_dump_json(indent=2), encoding="utf-8")
        props = meme.props(spec) | {"sfx_src": sfx.file_for("boom"), "sfx_volume": sfx.VOLUME["boom"]}
        new = meme.insert(json.loads(json.dumps(doc)), props, settings()["video"]["fps"])
        shots.validate(new)
        console.print(f"[cyan]meme[/] {short_id}: {spec.format} - {spec.why_funny[:80]}")
        return new
    except Exception as e:  # noqa: BLE001
        console.print(f"[yellow]meme skipped ({str(e)[:160]})[/]")
        return doc


def transcribe_pending() -> list[dict]:
    """Transcribe every new inbox video. Returns the batch: [{hash, title, transcript}]."""
    batch = []
    for h in ingest.scan_inbox():
        row = db.video_known(h)
        try:
            console.print(f"[cyan]transcribe[/] {row['title']}")
            audio = ingest.extract_audio(Path(row["path"]), h)
            tr = transcribe(audio, WORK / h / "transcript.json")
            db.set_video_status(h, "transcribed")
            batch.append({"hash": h, "title": row["title"], "transcript": tr})
        except Exception as e:
            db.set_video_status(h, "failed", str(e))
            console.print(f"[red]transcription failed[/] {row['title']}: {e}")
    return batch


def clip_credit(doc: dict) -> str:
    """'Clips: Mad Hat - <url>' for every source video shown on screen ('' when none). A local file with no URL is
    credited by its uploader and title instead."""
    seen: dict[str, str] = {}
    for s in doc["shots"]:
        pr = s["props"]
        if s["type"] != "broll" or not pr.get("source"):
            continue
        url, label, title = pr.get("credit_url") or "", pr.get("credit") or "source", pr.get("credit_title") or ""
        key = url or title or label
        if key not in seen:
            seen[key] = f"{label} - {url}" if url else (f"{label}: {title}" if title and title[:40] != label else (title or label))
    return ("Clips: " + "; ".join(seen.values())) if seen else ""


def with_clip_credit(caption: str, clip_line: str, sep: str = "\n\n") -> str:
    """The post caption with the clip credit appended (unchanged when there is none)."""
    return f"{caption}{sep}{clip_line}" if clip_line else caption


def _sources_txt(story: Story) -> str:
    lines = [f"Story: {story.topic}", ""]
    for ref in story.sources:
        row = db.video_known(ref.video_id)
        title = row["title"] if row else ref.video_id
        url = (row["source_url"] if row else None) or (row["path"] if row else "")
        lines.append(f"- {title} @ {ref.timestamp}\n  {url}")
    lines += ["", "Key facts used:"] + [f"- {f}" for f in story.key_facts]
    return "\n".join(lines)


def produce(short_id: str, batch_id: str, story: Story, script: Script, day: int, voice_provider: str | None = None,
            reuse_voice: bool = False, keep_shots: bool = False, director_notes: str = "") -> dict:
    """Script -> finished short. Returns a status dict; never raises."""
    work = WORK / "shorts" / short_id
    work.mkdir(parents=True, exist_ok=True)
    (work / "script.json").write_text(script.model_dump_json(indent=2), encoding="utf-8")
    date = (dt.date.today() + dt.timedelta(days=day + 1)).isoformat()
    out = OUT / date / short_id
    try:
        db.upsert_short(short_id, short_id, batch_id, "voicing")
        vmeta = work / "voice.json"
        if reuse_voice and (work / "words.json").exists() and (work / "vo.mp3").exists():
            console.print(f"[cyan]voice[/] {short_id}: reusing existing take")
            words = [Word(**w) for w in json.loads((work / "words.json").read_text(encoding="utf-8"))]
            preview = json.loads(vmeta.read_text(encoding="utf-8")).get("preview", False) if vmeta.exists() else False
        else:
            console.print(f"[cyan]voice[/] {short_id}: {script.title}")
            preview = False
            try:
                words = voice.synthesize(script, short_id, work, voice_provider)
            except RuntimeError as e:
                if "quota" not in str(e).lower() and "ElevenLabs 401" not in str(e) and "ElevenLabs 429" not in str(e):
                    raise
                console.print("[yellow]ElevenLabs is out of credits: rendering with the local voice as a PREVIEW (re-voice before posting)[/]")
                words, preview = voice.synthesize(script, short_id, work, "kokoro"), True
            vmeta.write_text(json.dumps({"provider": "kokoro" if preview else (voice_provider or voice.default_provider()), "preview": preview}), encoding="utf-8")

        if keep_shots and (work / "shots.json").exists():
            console.print(f"[cyan]shots[/] {short_id}: reusing existing shot plan")
            doc = json.loads((work / "shots.json").read_text(encoding="utf-8"))
            shots.validate(doc)
        else:
            doc = _direct_or_fallback(script, words, short_id, work, director_notes, story)
            doc = _add_meme(doc, script, short_id, work)
        shots_path = work / "shots.json"
        shots_path.write_text(json.dumps(doc, indent=1), encoding="utf-8")

        music = finish.pick_music(script.music_mood, short_id, accounts.current_id())
        report, fin = None, {}
        for attempt in (1, 2):
            console.print(f"[cyan]render[/] {short_id} (attempt {attempt})")
            mp4 = render.render_video(shots_path, work)
            fin = finish.finish(mp4, work / "final.mp4", music)
            report = qa.check(work / "final.mp4")
            if report["passed"]:
                break
            console.print(f"[yellow]QA failed[/] {short_id}: {[c for c in report['checks'] if not c['ok']]}")

        kicker = next((b.visual.kicker for b in script.beats if b.visual.kicker), "") or story.category.upper()
        render.render_cover(script.post.cover_title, kicker, work)

        out.mkdir(parents=True, exist_ok=True)
        for f in ("final.mp4", "cover.png", "shots.json", "words.json", "vo.mp3"):
            shutil.copy2(work / f, out / f)
        p = script.post
        clip_line = clip_credit(doc)
        (out / "caption.txt").write_text(
            f"{with_clip_credit(p.caption, clip_line)}\n\n{' '.join(p.hashtags)}\n\n--- pinned comment ---\n{p.pinned_comment}\n\n--- cover ---\n{p.cover_title}\n",
            encoding="utf-8")
        (out / "hooks.json").write_text(json.dumps([h.model_dump() for h in script.hooks], indent=2), encoding="utf-8")
        (out / "script.md").write_text(write.script_markdown(script, story), encoding="utf-8")
        credits = sorted({s["props"]["credit"] for s in doc["shots"]
                          if s["type"] == "broll" and s["props"].get("credit") and not s["props"].get("source")})
        src_txt = _sources_txt(story) + ("\n\nB-roll:\n" + "\n".join(f"- {c}" for c in credits) if credits else "")
        if clip_line:
            src_txt += f"\n\n{clip_line}"
        src_txt += f"\n\nShot planner: {doc.get('planner', 'built-in')}"
        (out / "sources.txt").write_text(src_txt, encoding="utf-8")
        (out / "qa.json").write_text(json.dumps(report | {"finish": fin}, indent=2), encoding="utf-8")

        from . import originality

        report["originality"] = originality.for_story(script.spoken_text(), story)
        report["voice_preview"] = preview
        (out / "qa.json").write_text(json.dumps(report | {"finish": fin}, indent=2), encoding="utf-8")
        status = ("preview" if preview else "done") if report["passed"] else "flagged"
        db.upsert_short(short_id, short_id, batch_id, status, out_dir=str(out), qa=report)
        _clean_old_outputs(short_id, out)
        return {"id": short_id, "status": status, "out": str(out), "title": script.title}
    except Exception as e:
        (work / "error.txt").write_text(traceback.format_exc(), encoding="utf-8")
        db.upsert_short(short_id, short_id, batch_id, "failed", error=str(e))
        console.print(f"[red]failed[/] {short_id}: {e}")
        return {"id": short_id, "status": "failed", "error": str(e), "title": script.title}


def remix(short_id: str) -> dict:
    """Re-run only the audio finish (music pick + loudness) on the existing render, then QA. Seconds, no Claude/TTS."""
    work = WORK / "shorts" / short_id
    with db.connect() as con:
        row = con.execute("SELECT out_dir, qa, story_id, batch_id FROM shorts WHERE id=?", (short_id,)).fetchone()
    if not row or not row["out_dir"] or not (work / "render.mp4").exists():
        raise FileNotFoundError(f"{short_id}: no render to remix")
    script = Script.model_validate_json((work / "script.json").read_text(encoding="utf-8"))
    music = finish.pick_music(script.music_mood, short_id, accounts.current_id())
    fin = finish.finish(work / "render.mp4", work / "final.mp4", music)
    report = qa.check(work / "final.mp4")
    out = Path(row["out_dir"])
    shutil.copy2(work / "final.mp4", out / "final.mp4")
    old = json.loads(row["qa"] or "{}")
    report |= {k: old[k] for k in ("originality", "voice_preview") if k in old}
    (out / "qa.json").write_text(json.dumps(report | {"finish": fin}, indent=2), encoding="utf-8")
    preview = bool(old.get("voice_preview"))
    status = ("preview" if preview else "done") if report["passed"] else "flagged"
    db.upsert_short(short_id, row["story_id"], row["batch_id"], status, out_dir=str(out), qa=report)
    return {"id": short_id, "status": status, "music": fin["music"]}


def run(voice_provider: str | None = None, target: int | None = None) -> list[dict]:
    batch = transcribe_pending()
    if not batch:
        console.print("Nothing new in inbox/. Drop videos there or use `clipforge add <url>`.")
        return []
    batch_id = time.strftime("%Y%m%d-%H%M%S")
    console.print(f"[cyan]mine[/] {len(batch)} transcript(s) -> stories (batch {batch_id})")
    stories = mine.mine(batch_id, batch, target)
    picks = mine.pick(batch_id, stories, len(batch), target)
    for v in batch:
        db.set_video_status(v["hash"], "mined")
    console.print(f"  {len(stories)} stories found, {len(picks)} picked")

    def write_and_review(sid: str, st: Story) -> Script:
        draft = write.write(sid, st)
        final, issues = write.review(sid, st, draft)
        d = WORK / "shorts" / sid
        d.mkdir(parents=True, exist_ok=True)
        (d / "draft.json").write_text(draft.model_dump_json(indent=2), encoding="utf-8")
        (d / "review.json").write_text(json.dumps({"issues": issues}, indent=2), encoding="utf-8")
        return final

    scripts: dict[str, Script] = {}
    with ThreadPoolExecutor(max_workers=settings()["claude"]["max_parallel"]) as pool:
        futs = {pool.submit(write_and_review, sid, st): sid for sid, st, _ in picks}
        for f in as_completed(futs):
            sid = futs[f]
            try:
                scripts[sid] = f.result()
                console.print(f"[cyan]script[/] {sid}: {scripts[sid].title} ({scripts[sid].word_count()} words, reviewed)")
            except Exception as e:
                db.upsert_short(sid, sid, batch_id, "failed", error=f"writing: {e}")
                console.print(f"[red]writing failed[/] {sid}: {e}")

    results = []
    for sid, st, day in picks:
        if sid in scripts:
            results.append(produce(sid, batch_id, st, scripts[sid], day, voice_provider))
    return results
