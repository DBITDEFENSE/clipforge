# ClipForge

Long-form videos in, original vertical shorts out. The uploads are **research input, not footage**. ClipForge watches them, pulls out the stories, and makes new segments: original scripts, your cloned voice, original animated visuals.

## Daily use

```powershell
uv run clipforge add https://www.youtube.com/watch?v=...   # or drop files in inbox/
uv run clipforge run                                       # transcribe -> mine -> write -> voice -> render -> QA
uv run clipforge status                                    # what happened
```

Each short lands in `out/<post-date>/<short_id>/`:

| file | what |
|---|---|
| `final.mp4` | 1080x1920 H.264, AAC 48 kHz, -14 LUFS, burned-in captions |
| `cover.png` | cover image with title |
| `caption.txt` | caption, hashtags, pinned comment, cover title (ready to paste) |
| `hooks.json` | 3 hook options (A/B) |
| `script.md`, `shots.json`, `words.json`, `vo.mp3` | the script, shot plan, word timings, voice |
| `sources.txt` | which uploads/timestamps it drew from |
| `qa.json` | automatic QA results |

Shorts that fail QA twice are marked `flagged` (not `done`). The batch never stops for one bad video.

## Setup (once)

1. `copy .env.example .env` and fill in `ANTHROPIC_API_KEY`, `ELEVENLABS_API_KEY`, `ELEVENLABS_VOICE_ID`.
2. `uv sync` (Python 3.12, PyTorch CUDA 12.8 for the RTX 5090) and `cd render && npm install`.
3. Drop royalty-free music in `assets/music/` named `<mood>__name.mp3`. Moods: `tense`, `dark`, `driving`, `curious`, `upbeat`.
4. `uv run clipforge doctor` should be all green.

## Other commands

- `clipforge make <script.json> [--voice say|take|elevenlabs]`: produce one short from a script file. Useful for re-renders after you edit a script.
- Voice `take`: record yourself reading the script, save it as `takes/<short_id>.wav`, then run `make ... --voice take`. WhisperX aligns your take to the script.
- `cd render && npm run studio`: live-preview the Remotion components.

## Tuning

- `config/settings.yaml`: models, posts per day, voice settings, loudness, shot pacing.
- `config/brand.yaml`: colors, fonts, handle.
- `config/pronunciations.yaml`: how the voice says CVE IDs and acronyms. Captions keep the original spelling.
- `clipforge/prompts/*.md`: the editorial voice (mining and writing prompts).

## Licensing notes

- Remotion is free for individuals and companies of up to 3 people. DBIT Defense qualifies today. At 4+ people you need a Company License (from $25/seat/month, or $0.01/render for automation).
- Music and B-roll must be licensed for commercial use. You're running paid ads behind winners.
