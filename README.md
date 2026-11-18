# ClipForge

Long-form videos in, original vertical shorts out. The uploads are **research input, not footage**. ClipForge watches them, pulls out the stories, and makes new segments: original scripts, your cloned voice, original animated visuals.

## Daily use

```powershell
uv run clipforge add URL1 URL2 URL3 --run   # download a batch and make the shorts (or drop files in inbox/ and `clipforge run`)
uv run clipforge gallery                    # watch everything, copy captions
uv run clipforge status                     # what happened
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

A batch makes `max(per_day * days, per_video * videos)` shorts (settings.yaml `plan`): every video contributes its best `per_video` stories, the same event covered by two videos is merged into one short, and post dates are spread at `per_day` per day.

Shorts that fail QA twice are marked `flagged` (not `done`). The batch never stops for one bad video.

## Setup (once)

1. `copy .env.example .env` and fill in `ANTHROPIC_API_KEY`, `ELEVENLABS_API_KEY`, `ELEVENLABS_VOICE_ID`.
2. `uv sync` (Python 3.12, PyTorch CUDA 12.8 for the RTX 5090) and `cd render && npm install`.
3. Drop royalty-free music in `assets/music/` named `<mood>__name.mp3`. Moods: `tense`, `dark`, `driving`, `curious`, `upbeat`.
4. `uv run clipforge doctor` should be all green.

## Other commands

- `clipforge voices`: audition voices on the same line, click "Use this", or upload 1-3 minutes of yourself to clone your voice.
- `clipforge redo <ids...> [--keep-shots | --revoice]`: re-direct and re-render existing shorts (voice reused); `--keep-shots` is render-only, `--revoice` re-synthesizes with the current voice.

- `clipforge make <script.json> [--voice say|take|elevenlabs]`: produce one short from a script file. Useful for re-renders after you edit a script.
- Voice `take`: record yourself reading the script, save it as `takes/<short_id>.wav`, then run `make ... --voice take`. WhisperX aligns your take to the script.
- `cd render && npm run studio`: live-preview the Remotion components.

## Tuning

- `config/settings.yaml`: models, posts per day, voice settings, loudness, shot pacing.
- `config/brand.yaml`: colors (cyan accent, pink accent2, lime highlight, warning, fire), fonts, handle.
- `assets/sfx/`: cut and reaction sound effects (synthesized originals). Drop your own `whoosh.wav`, `boom.mp3`, ... to replace any of them.
- Shot types the director can use: kinetic, headline, stat, code, terminal, diagram, cve, broll, **reaction** (meme beat: giant emoji + punchline), **popups** (cascading alert windows). Any shot can add an `fx` (fire, alarm, glitch, shake, emoji_rain), a corner emoji sticker, and a sound effect.
- `config/pronunciations.yaml`: how the voice says CVE IDs and acronyms. Captions keep the original spelling.
- `clipforge/prompts/*.md`: the editorial voice (mining and writing prompts).

## Licensing notes

- Remotion is free for individuals and companies of up to 3 people. DBIT Defense qualifies today. At 4+ people you need a Company License (from $25/seat/month, or $0.01/render for automation).
- Music and B-roll must be licensed for commercial use. You're running paid ads behind winners.
