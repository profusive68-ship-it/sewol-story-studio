"""주말 몰아듣기 합본 — 완성된 프로젝트 2~3개를 하나로 잇는다."""
from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path

import numpy as np
from scipy.io import wavfile

from .ffmpeg_util import ffmpeg_exe, run
from .ffmpeg_util import duration as probe_duration
from .graphics import card_text, thumbnail_style2, save
from .music import SR, get_bgm
from .paths import PROJECTS_DIR, project_dir
from .project import load, now, set_status
from .render import detect_encoder
from .settings import load_config

W, H = 1920, 1080


def _safe(name: str) -> str:
    import re
    return re.sub(r"[\\/:*?\"<>|]", "", name).strip()[:60].replace(" ", "_") or "합본"


def _bgm_wav(seconds: float, path: Path) -> Path:
    loop_path = get_bgm("heal")
    sr, data = wavfile.read(loop_path)
    if data.ndim == 1:
        data = np.stack([data, data], axis=1)
    data = data.astype(np.float32) / 32768.0
    need = int(seconds * SR)
    tiles = int(np.ceil(need / len(data))) + 1
    big = np.tile(data, (tiles, 1))[:need]
    fade = int(1.2 * SR)
    big[:fade] *= np.linspace(0, 1, fade)[:, None]
    big[-fade:] *= np.linspace(1, 0, fade)[:, None]
    big *= 10 ** (-24 / 20)
    wavfile.write(path, SR, (np.clip(big, -1, 1) * 32767).astype(np.int16))
    return path


def _card_video(img: Path, secs: float, out: Path, enc: dict, work: Path) -> Path:
    bgm = _bgm_wav(secs, work / "card_bgm.wav")
    cmd = [ffmpeg_exe(), "-y", "-v", "error", "-loop", "1", "-t", f"{secs}", "-i", str(img),
           "-i", str(bgm), "-filter_complex",
           f"[0:v]scale={W}:{H},fps=25,format=yuv420p,fade=t=in:st=0:d=0.4,fade=t=out:st={secs - 0.6}:d=0.6[v]",
           "-map", "[v]", "-map", "1:a", *enc["args"], "-c:a", "aac", "-b:a", "192k",
           "-ar", "48000", "-ac", "2", "-shortest", str(out)]
    r = run(cmd, timeout=600)
    if not out.exists():
        raise RuntimeError("카드 영상 생성 실패: " + (r.stderr or "")[-300:])
    return out


def _normalize_video(src: Path, out: Path, enc: dict) -> Path:
    cmd = [ffmpeg_exe(), "-y", "-v", "error", "-i", str(src),
           "-vf", (f"scale={W}:{H}:force_original_aspect_ratio=decrease,"
                   f"pad={W}:{H}:(ow-iw)/2:(oh-ih)/2:color=black,fps=25,format=yuv420p"),
           "-af", "loudnorm=I=-15:TP=-1.5:LRA=11",
           *enc["args"], "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2",
           "-movflags", "+faststart", str(out)]
    r = run(cmd, timeout=60 * 60)
    if not out.exists():
        raise RuntimeError("합본 구간 인코딩 실패: " + (r.stderr or "")[-300:])
    return out


def compile_weekend(project_ids: list[str], title: str = "", progress=None,
                    auto_upload: bool = False, privacy: str = "private",
                    publish_at: str = "") -> dict:
    if not (2 <= len(project_ids) <= 4):
        raise ValueError("합본은 완성된 프로젝트 2~3개(최대 4개)를 골라 주세요.")
    projects = []
    for pid in project_ids:
        p = load(pid)
        video = (p.get("outputs") or {}).get("video")
        if not video or not (project_dir(pid) / video).exists():
            raise ValueError(f"'{p['title']}' 은 아직 영상이 완성되지 않았습니다.")
        projects.append(p)

    cid = "weekend-" + datetime.now().strftime("%Y%m%d-%H%M%S")
    cdir = PROJECTS_DIR / cid
    work = cdir / "work"
    out_dir = cdir / "output"
    work.mkdir(parents=True, exist_ok=True)
    out_dir.mkdir(parents=True, exist_ok=True)
    enc = detect_encoder(load_config().get("encoder", "auto"))

    label = title.strip() or "주말 몰아듣기 · 세월의 사연극장"
    cover = card_text("주말 몰아듣기", [label] + [f"· {p['title']}" for p in projects],
                      W, H, note="세월의 사연극장  ·  이어폰을 끼고 천천히 들어보세요")
    cover_path = work / "cover.png"
    save(cover, cover_path)

    segments: list[Path] = []
    if progress:
        progress(2, "표지 카드 만드는 중…")
    segments.append(_card_video(cover_path, 7.0, work / "seg_000.mp4", enc, work))

    total_est = sum(max(30.0, float(p.get("duration") or 300)) for p in projects)
    done = 0.0
    for i, p in enumerate(projects, start=1):
        if progress:
            progress(min(60, int(5 + 55 * done / max(1, total_est))), f"{p['title']} 준비 중…")
        src = project_dir(p["id"]) / p["outputs"]["video"]
        seg = _normalize_video(src, work / f"seg_{i:03d}.mp4", enc)
        segments.append(seg)
        done += float(p.get("duration") or 0)
        if i < len(projects):
            bridge = card_text(f"다음 사연 · {i + 1}", [projects[i]["title"], "잠시 후 이어집니다"],
                               W, H, note=p.get("logline", ""))
            bp = work / f"bridge_{i}.png"
            save(bridge, bp)
            segments.append(_card_video(bp, 3.5, work / f"seg_{i:03d}b.mp4", enc, work))

    if progress:
        progress(65, "하나로 잇는 중…")
    listfile = work / "list.txt"
    listfile.write_text("\n".join(f"file '{s.name}'" for s in segments), encoding="utf-8")
    out = out_dir / f"{_safe(label)}_{datetime.now().strftime('%Y%m%d')}.mp4"
    r = run([ffmpeg_exe(), "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(listfile),
             "-c", "copy", "-movflags", "+faststart", str(out)], timeout=3600)
    if not out.exists():
        raise RuntimeError("합본 연결 실패: " + (r.stderr or "")[-400:])

    total = probe_duration(out)
    # 챕터: 각 사연 시작 시각
    chapters, acc = [], 7.0
    for i, p in enumerate(projects):
        chapters.append({"title": p["title"], "time": round(acc, 2)})
        acc += float(p.get("duration") or 0)
        if i < len(projects) - 1:
            acc += 3.5
    hashtags = ["#주말몰아듣기", "#사연", "#라디오드라마", "#감동사연", "#사이다",
                "#가족사연", "#시니어", "#노인사연", "#세월의사연극장", "#몰아보기"]
    meta = {
        "schema": "sewol-weekend/1", "id": cid, "title": label,
        "created_at": now(), "kind": "weekend", "children": project_ids,
        "duration": total, "format": {"label": "주말 2시간 몰아듣기", "aspect": "16:9",
                                      "width": W, "height": H},
        "titles": [label, f"{len(projects)}편 몰아듣기 — {label}",
                   f"잠들기 전 2시간, 사연 {len(projects)}편"],
        "description": (f"{label}\n\n" + "\n".join(f"· {p['title']}" for p in projects) +
                        f"\n\n총 {int(total // 60)}분. 사연은 창작·각색된 이야기입니다."),
        "hashtags": hashtags,
        "chapters": chapters,
        "chapters_meta": chapters,
        "timeline": [],
        "options": {},
        "outputs": {"video": str(out.relative_to(cdir))},
        "status": {"stage": "done", "percent": 100, "message": "합본 완성", "updated": now()},
    }
    (cdir / "project.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    # 썸네일·안내문
    th = thumbnail_style2([f"“{label}”", f"{len(projects)}편 몰아듣기", "밤에 이어폰 끼고", "천천히 들어보세요"],
                          1280, 720)
    thumb_path = out_dir / "thumb" / "thumbnail_주말합본.jpg"
    save(th, thumb_path)
    meta["outputs"]["thumb_style1"] = str(thumb_path.relative_to(cdir))
    meta["outputs"]["thumb_style2"] = str(thumb_path.relative_to(cdir))
    lines = [f"[제목] {label}", "", "[구성]"]
    for i, p in enumerate(projects, start=1):
        lines.append(f"{i}. {p['title']}  ({p.get('format', {}).get('label', '')})")
    lines += ["", f"[길이] 약 {int(total // 60)}분", "",
              "[고정댓글]", "여러분이라면 어떻게 하셨을까요? 어느 지역에서 듣고 계신지 댓글로 남겨주세요! 🌷"]
    (out_dir / "upload_copy.txt").write_text("\n".join(lines), encoding="utf-8")

    (cdir / "project.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    # 유튜브 자동 업로드
    if auto_upload:
        try:
            from .youtube_upload import has_client, upload_project
            if has_client():
                if progress:
                    progress(85, "합본을 유튜브에 올리는 중…")
                upload_project(cid, 0, privacy, publish_at,
                               progress=lambda q, m: progress(85 + int(q * 0.15), m))
        except Exception as e:
            meta.setdefault("warnings", []).append(f"합본 업로드 실패: {str(e)[:160]}")
            (cdir / "project.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    # 임시 파일 정리
    if not load_config().get("keep_segments"):
        shutil.rmtree(work, ignore_errors=True)
    if progress:
        progress(100, "합본 완성")
    return {"id": cid, "video": str(out), "duration": total, "title": label}
