"""Invoke Remotion: shots.json -> render.mp4, and the cover still."""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

from .config import RENDER, brand, settings

NPX = shutil.which("npx") or shutil.which("npx.cmd") or "npx"


def _remotion(args: list[str], public_dir: Path) -> None:
    cmd = [NPX, "remotion", *args, f"--public-dir={public_dir}", "--log=error"]
    r = subprocess.run(cmd, cwd=RENDER, capture_output=True, text=True, encoding="utf-8", errors="replace", shell=False)
    if r.returncode != 0:
        raise RuntimeError(f"remotion failed ({r.returncode}):\n{(r.stderr or r.stdout)[-2000:]}")


def render_video(shots_path: Path, workdir: Path) -> Path:
    from . import sfx

    doc = json.loads(shots_path.read_text(encoding="utf-8"))
    sfx.stage({Path(s["props"]["sfx_src"]).stem for s in doc["shots"] if s["props"].get("sfx_src")}, workdir)
    gp = doc.get("gameplay")
    if gp and Path(gp["file"]).exists() and not (workdir / gp["src"]).exists():
        shutil.copy2(gp["file"], workdir / gp["src"])
    out = workdir / "render.mp4"
    crf = settings()["finish"]["crf"]
    _remotion(["render", "src/index.ts", "Short", str(out), f"--props={shots_path}", "--codec=h264",
               f"--crf={crf}", "--pixel-format=yuv420p", "--audio-codec=aac"], workdir)
    return out


def render_cover(title: str, kicker: str, workdir: Path) -> Path:
    props = workdir / "cover_props.json"
    props.write_text(json.dumps({"title": title, "kicker": kicker, "brand": brand()}), encoding="utf-8")
    out = workdir / "cover.png"
    _remotion(["still", "src/index.ts", "Cover", str(out), f"--props={props}"], workdir)
    return out
