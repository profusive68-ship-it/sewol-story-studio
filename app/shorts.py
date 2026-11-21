"""롱폼 → 50초 세로 쇼츠 자동 추출 (상단 2줄 제목 + 중앙 크롭 + 하단 자막)."""
from __future__ import annotations

import os
import shutil
from pathlib import Path

from PIL import Image, ImageDraw

from .ffmpeg_util import ffmpeg_exe, run
from .graphics import CREAM, YELLOW, fit_font, font, text_outlined
from .paths import FONT_DIR, project_dir
from .project import build_upload_pack, load, now, save
from .render import FPS, _write_fontconfig, detect_encoder
from .settings import load_config
from .subtitles import write_ass


def _pick_window(items: list[dict], total: float) -> tuple[float, float]:
    twists = [it["start"] for it in items if it.get("emotion") == "twist" and it.get("kind") in ("body", "hook")]
    anchor = twists[-1] if twists else (items[len(items) // 2]["start"] if items else 0)
    length = min(50.0, max(20.0, total))
    start = max(0.0, min(anchor - 8.0, total - length))
    return round(start, 2), round(min(length, total - start), 2)


def _title_png(project: dict, out: Path, width: int, height: int) -> Path:
    pack = build_upload_pack(project)
    title = (pack.get("titles") or [project["title"]])[0]
    # 두 줄로 나누기
    words = title.replace("—", "-").split()
    line1, line2 = "", ""
    for w in words:
        if len(line1) + len(w) + 1 <= 13 and not line2:
            line1 = (line1 + " " + w).strip()
        else:
            line2 = (line2 + " " + w).strip()
    if not line2:
        line2 = ((project.get("thumbnail") or {}).get("style1") or ["", "실화 같은 사연"])[1] or "실화 같은 사연"
    if not line1:
        line1, line2 = title[:13], title[13:26]
    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    y = int(height * 0.085)
    for text, color, size in ((line1, (255, 255, 255), int(height * 0.048)),
                              (line2 or "끝까지 보세요", YELLOW, int(height * 0.045))):
        f = fit_font(d, text, int(width * 0.92), size, min_size=40)
        # 반투명 검은 띠
        tw = int(d.textlength(text, font=f))
        d.rounded_rectangle([(width - tw) // 2 - 24, y - 12, (width + tw) // 2 + 24, y + f.size + 12],
                            radius=18, fill=(0, 0, 0, 140))
        text_outlined(d, (width / 2, y), text, f, fill=color, outline=(0, 0, 0), width=6, anchor="ma")
        y += f.size + int(height * 0.012)
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out)
    return out


def extract_shorts(pid: str, progress=None) -> dict:
    p = load(pid)
    video = (p.get("outputs") or {}).get("video")
    if not video or not (project_dir(pid) / video).exists():
        raise RuntimeError("먼저 롱폼 영상을 완성해 주세요.")
    items = p.get("timeline") or []
    total = float(p.get("duration") or (items[-1]["end"] if items else 0))
    if total < 20:
        raise RuntimeError("쇼츠로 뽑기엔 영상이 너무 짧습니다.")
    start, length = _pick_window(items, total)

    # 자막: 창 안의 대사를 0초 기준으로 옮긴다
    sub_items = []
    for it in items:
        if it.get("card"):
            continue
        a, b = it["start"], it["end"]
        if b <= start + 0.2 or a >= start + length - 0.2:
            continue
        sub_items.append({**it, "start": max(0.0, a - start), "end": min(length, b - start)})
    opts = dict(p.get("options", {}))
    opts["no_brand"] = True
    tmp_project = {"options": opts, "duration": length}
    rdir = project_dir(pid) / "render"
    (rdir / "fonts").mkdir(parents=True, exist_ok=True)
    for f in FONT_DIR.glob("*.*"):
        shutil.copy2(f, rdir / "fonts" / f.name)
    ass = write_ass(tmp_project, sub_items, rdir / "shorts.ass", 1080, 1920)
    title = _title_png(p, rdir / "shorts_title.png", 1080, 1920)

    out = project_dir(pid) / "output" / "shorts_50s.mp4"
    enc = detect_encoder(load_config().get("encoder", "auto"))
    fc = _write_fontconfig(rdir)
    env = os.environ.copy()
    env["FONTCONFIG_FILE"] = str(fc)
    env.setdefault("FONTCONFIG_PATH", str(rdir))

    graph = (
        "[0:v]split=2[bg][fg];"
        "[bg]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,"
        "boxblur=24:2,eq=brightness=-0.22:saturation=0.8[bg2];"
        "[fg]scale=1080:-2[fg2];"
        "[bg2][fg2]overlay=(W-w)/2:560[b];"
        "[b][1:v]overlay=0:0[t];"
        "[t]format=yuv420p,ass=filename=render/shorts.ass:fontsdir=render/fonts[v]"
    )
    cmd = [ffmpeg_exe(), "-y", "-hide_banner", "-v", "warning",
           "-ss", f"{start:.3f}", "-t", f"{length:.3f}", "-i", str(project_dir(pid) / video),
           "-loop", "1", "-i", str(title),
           "-filter_complex", graph, "-map", "[v]", "-map", "0:a?",
           "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2",
           *enc["args"], "-r", str(FPS), "-t", f"{length:.3f}",
           "-movflags", "+faststart", "-threads", "0", str(out)]
    if progress:
        progress(20, "50초 구간을 세로 화면으로 뽑는 중…")
    import subprocess
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                          env=env, timeout=1800, cwd=str(project_dir(pid)))
    if not out.exists() or out.stat().st_size < 20000:
        raise RuntimeError("쇼츠 렌더 실패: " + (proc.stderr or "")[-400:])
    p.setdefault("outputs", {})["shorts"] = str(out.relative_to(project_dir(pid)))
    p["shorts"] = {"start": start, "duration": length, "created_at": now(),
                   "title": build_upload_pack(p)["titles"][0]}
    save(p)
    if progress:
        progress(100, "50초 쇼츠 완성")
    return {"video": str(out), "start": start, "duration": length}
