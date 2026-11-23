# ClipForge

Long-form videos in, original vertical shorts out. The uploads are **research input, not footage**. ClipForge watches them, pulls out the stories, and makes new segments: original scripts, your cloned voice, original animated visuals.

## Install and update: the launcher

On a new Windows 10/11 PC, open PowerShell and run:

```powershell
irm https://raw.githubusercontent.com/DBITDEFENSE/clipforge/master/install.ps1 | iex
```

That installs uv, Node.js and ffmpeg (winget), downloads ClipForge to `%LOCALAPPDATA%\ClipForge` and adds a **ClipForge**
shortcut to the desktop and Start menu. The first start downloads the dependencies (several GB, including PyTorch).

Double-click **ClipForge** (or `ClipForge.bat` in the folder) to open the launcher at http://127.0.0.1:8787:

- **Start Studio** and **API keys** (paste and validate your keys).
- **This PC**: what's installed and what's missing, with the fix.
- **Latest news**: read from `news.json` in the repo.
- **Update**: appears when the repo's `pyproject.toml` version is higher than yours. It replaces the program files and
  syncs dependencies. `.env`, `data/`, `out/`, `work/`, `inbox/`, `takes/` and your music/gameplay files are never touched;
  config files you edited are copied to `config/backup/<time>/` before the new defaults replace them. In a git checkout
  the button runs `git pull --ff-only` instead.

Publishing a release (maintainer): bump `version` in `pyproject.toml`, run `uv lock`, add an item to the top of
`news.json` (`date`, `title`, `body`, optional `version` and `tag`), push. News-only posts need no version bump.
The update source is `launcher.repo` / `launcher.branch` in `config/settings.yaml` and `$Repo` / `$Branch` in
`install.ps1`; the repo has to be public.

## Daily use: the studio

```powershell
uv run clipforge studio
```

One local app (http://127.0.0.1:8790) for the whole flow. You sign in to a **channel account** first; every channel
(e.g. Cyber Cowboy, DBIT Defense) has its own persona, colors, handle, voice, posting times, connected YouTube/TikTok and
optional password. Home shows what to do next.

1. **Create**: paste links or drop video files. Jobs run one at a time with a live log.
2. **Review**: watch each short, then **Approve** (pick a slot, YouTube and/or TikTok), **Regenerate** with notes (visuals only, or script + voice), or **Reject**.
3. **Schedule**: the week's slots (`plan.slots`, Eastern), per-platform status, post now, unschedule. Mirrored to `out/queue.csv`.
4. **Performance**: views/likes per post, refreshed every 6 h, plus **ad candidates** (beat your median views with strong engagement). ClipForge never spends money; you boost in TikTok Ads Manager and mark it here.
5. **Connect**: link YouTube (Google OAuth) and TikTok (Content Posting API). Step-by-step setup is on the page.

How posting works:
- **YouTube** uploads right after you approve, as private with `publishAt`, so YouTube publishes it on time even if the studio is closed.
- **TikTok** has no scheduling API, so the studio posts at the slot time **while it's running** (or run `clipforge publish-due` from Task Scheduler). The approve dialog follows TikTok's required posting UX (account shown, privacy with no default, interaction toggles, commercial disclosure, consent line). Until TikTok audits your app, posts are private-only.

- **Local voice (free)**: Kokoro-82M runs on the GPU. Settings → Voice has presets (Radio cowboy, Trail boss, ...), two-narrator
  blend, pace, pitch, warmth/grit, expressiveness, pauses, and a Southern/country accent (phoneme-level drawl: off / light / full).
- **AI meme**: every short gets a meme written by a dedicated Claude pass (nope/yep, expectation vs reality, galaxy brain,
  starter pack, two buttons, POV, nobody, calm chaos), drawn with emoji + meme type and placed to play inside the first 6 seconds.
- **Video models (Settings > Visuals)**: B-roll from motion graphics only, Pexels stock, **local Wan** (free, on the
  GPU: Wan 2.1 1.3B at 480p, ~75 s/clip, or Wan 2.2 5B at 720p, sharper and slower), or any **fal.ai** / **Replicate** text-to-video model (Kling, Veo, Hailuo, Wan 2.2, LTX,
  Seedance...; your key, capped clips per short, estimated cost logged). The director writes a prompt per clip (no real
  people's likeness, logos or text); failures fall back to motion graphics. `clipforge video-test --prompt "..."` tries a model.
- **Background music (Settings > Visuals, video & music)**: each channel gets its own library of original instrumental
  beds generated locally with ACE-Step 1.5 (MIT license, ~11 GB one-time download, a few seconds per track). Describe the
  channel's sound once; tracks are made per mood and each short picks one matching its mood, ducked under the voice.
  CLI: `clipforge --account <id> music [--per-mood 2] [--replace]`. Your own tracks in `assets/music/<channel>/` work too.
- **Gameplay split-screen**: Settings > Visuals > Layout. Graphics on top, your footage from `assets/gameplay/` looping below.
- **Autopilot (Make tab)**: follow channels (e.g. @Fireship); each day at the set time new uploads become shorts for that
  channel and wait in Review. Off by default (it spends Claude credits). CLI: `clipforge --account <id> autopilot [--follow @x]`.
- **Length**: scripts target ~30 s (65-85 words); QA accepts 20-45 s.
- **Preview voice**: if ElevenLabs is out of credits, shorts render with a robotic placeholder voice and are marked
  "Preview voice". They can't be scheduled until you hit **Re-voice** (after topping up).
- **Originality check**: every short reports how much wording overlaps the source transcripts (7+ word runs). Informational, never blocks.
- **Feedback loop**: once posts have stats, the writer sees which hooks/topics did best and worst on that channel.

## CLI

All commands take `--account <id>` (`clipforge channels` lists them), e.g. `clipforge --account cyber-cowboy add <url> --run`.

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
3. Music: `clipforge music` generates a channel library, or drop licensed tracks in `assets/music/` (shared) or
   `assets/music/<channel>/` named `<mood>__name.mp3`. Moods: `tense`, `dark`, `driving`, `curious`, `upbeat`.
4. `uv run clipforge doctor` should be all green.

## Other commands

- `clipforge revise <id> --notes "..." [--scope visuals|script]`: regenerate one short with your notes.
- `clipforge publish-due`, `clipforge stats`: what the studio does in the background (post what's due, pull stats + ad candidates).
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
- Music and B-roll must be licensed for commercial use. ACE-Step 1.5 weights are MIT and Wan is Apache-2.0, so what
  they generate is yours; check any provider's terms if you use fal.ai/Replicate models. You're running paid ads behind winners.
