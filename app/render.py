"""영상 조립 — 장면별 Ken Burns 렌더 → 합치기 → 입자·아바타·자막·배지 오버레이."""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

from .ffmpeg_util import ffmpeg_exe, has_encoder, run
from .graphics import (avatar_from_photo, avatar_motion_frames, card_rewind, card_text,
                       end_screen_overlay, like_badge, live_badge, live_badge_frames,
                       make_avatar, particle_frames, save)
from .paths import ASSETS_DIR, CACHE_DIR, FONT_DIR, project_dir
from .settings import (AVATAR_MOTION_CYCLE, AVATAR_MOTION_SECONDS, AVATAR_SIZE_RATIO,
                       LIVE_BADGE_PERIOD, load_config, narrator_gender)
from .subtitles import write_ass, write_srt

FPS = 25
LIKE_TOP = 0.045
DIRECTIONS = [(-0.6, -0.4), (0.6, -0.4), (-0.5, 0.5), (0.5, 0.4), (0.0, -0.7), (0.0, 0.7)]


# ── 인코더 감지 ──────────────────────────────────────────────────────────
def detect_encoder(pref: str = "auto") -> dict:
    x264 = {"codec": "libx264", "label": "libx264 (CPU)",
            "args": ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p"]}
    if pref == "libx264" or not has_encoder("h264_videotoolbox"):
        return x264
    test = CACHE_DIR / "enc_test.mp4"
    try:
        r = run([ffmpeg_exe(), "-y", "-v", "error", "-f", "lavfi", "-i",
                 "color=c=black:s=320x240:r=25:d=0.4", "-c:v", "h264_videotoolbox",
                 "-b:v", "800k", str(test)], timeout=90)
        ok = r.returncode == 0 and test.exists() and test.stat().st_size > 1000
    except Exception:
        ok = False
    if ok:
        return {"codec": "h264_videotoolbox", "label": "h264_videotoolbox (맥 하드웨어 가속)",
                "args": ["-c:v", "h264_videotoolbox", "-b:v", "8000k", "-maxrate", "10000k",
                         "-bufsize", "16000k", "-allow_sw", "1", "-pix_fmt", "yuv420p"]}
    return x264


def encoder_info() -> dict:
    cfg = load_config()
    enc = detect_encoder(cfg.get("encoder", "auto"))
    return {"codec": enc["codec"], "label": enc["label"], "force_scale": cfg.get("force_scale", 0)}


# ── 보조 영상(입자) ──────────────────────────────────────────────────────
def particles_video(width: int, height: int) -> Path:
    key = f"pv_{width}x{height}_{FPS}"
    out = CACHE_DIR / "particles" / f"{key}.mp4"
    if out.exists() and out.stat().st_size > 2000:
        return out
    frames = particle_frames(width, height)
    r = run([ffmpeg_exe(), "-y", "-v", "error", "-framerate", "12", "-i", str(frames / "f%04d.png"),
             "-vf", f"fps={FPS},scale={width}:{height}:flags=bicubic,format=yuv420p",
             "-c:v", "libx264", "-preset", "ultrafast", "-crf", "20", "-an", str(out)], timeout=300)
    if not out.exists() or out.stat().st_size < 1000:
        raise RuntimeError("입자 오버레이 생성 실패: " + (r.stderr or "")[-400:])
    return out


# ── fontconfig (번들 폰트만 사용) ────────────────────────────────────────
def _write_fontconfig(rdir: Path) -> Path:
    rdir.mkdir(parents=True, exist_ok=True)
    fonts = (rdir / "fonts").resolve()
    cache = (rdir / "fontcache")
    cache.mkdir(exist_ok=True)
    xml = f"""<?xml version="1.0"?>
<!DOCTYPE fontconfig SYSTEM "urn:fontconfig:fonts.dtd">
<fontconfig>
  <dir>{fonts}</dir>
  <dir>/System/Library/Fonts</dir>
  <dir>/Library/Fonts</dir>
  <cachedir>{cache.resolve()}</cachedir>
  <config></config>
</fontconfig>
"""
    path = rdir / "fonts.conf"
    path.write_text(xml, encoding="utf-8")
    return path


def _popen(cmd: list[str], cwd: Path, total: float, progress=None, stage_msg="영상 인코딩",
           env: dict | None = None) -> None:
    log = cwd / "render" / "ffmpeg.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    with open(log, "w", encoding="utf-8") as lf:
        proc = subprocess.Popen(cmd, cwd=str(cwd), stdout=subprocess.DEVNULL,
                                stderr=subprocess.PIPE, text=True, bufsize=1, env=env)
        assert proc.stderr is not None
        for line in proc.stderr:
            lf.write(line)
            m = re.search(r"time=(\d+):(\d+):(\d+(?:\.\d+)?)", line)
            if m and progress and total > 0:
                t = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))
                progress(min(99, int(100 * t / total)), stage_msg)
        code = proc.wait()
    if code != 0:
        tail = "\n".join(log.read_text(encoding="utf-8", errors="ignore").splitlines()[-24:])
        raise RuntimeError("ffmpeg 렌더 실패:\n" + tail)


def _grade(emotion: str) -> str:
    if emotion == "conflict":
        return "eq=saturation=0.86:contrast=1.07:brightness=-0.012,colorbalance=bs=0.05:bm=0.02:rh=-0.02"
    if emotion == "twist":
        return "eq=saturation=1.05:contrast=1.11:brightness=0.004"
    return "eq=saturation=1.02:contrast=1.02:brightness=0.015,colorbalance=rs=0.03:gs=0.01:bs=-0.02"


def _scene_emotion(project: dict, anchor: str) -> str:
    for s in project["scenes"]:
        if s["id"] == anchor:
            return s.get("emotion", "heal")
    return "heal"


# ── 카드(되감기·예고·엔딩)와 화면 계획 ──────────────────────────────────
# ── 진행자(나레이션 호스트) ──────────────────────────────────────────────────
HOST_DIR = ASSETS_DIR / "hosts"


def avatar_px(width: int, height: int) -> int:
    """1080p 짧은 변 기준 약 290px(27%) — 짝수로 맞춘다."""
    px = max(160, int(min(width, height) * AVATAR_SIZE_RATIO))
    return max(2, px // 2 * 2)


def avatar_margin(width: int, height: int) -> int:
    return max(16, int(min(width, height) * 0.032))


def host_portrait(project: dict, cfg: dict, px: int) -> tuple[str, "object", str]:
    """나레이션 성별에 맞는 라디오 진행자 초상을 2배 크기로 만든다.

    returns (gender, PIL.Image, cache_key)
    """
    opt = project.get("options") or {}
    pdir = project_dir(project["id"])
    kind = str(opt.get("avatar_kind") or "auto").strip().lower()
    custom = str(opt.get("avatar_image") or "").strip()
    if custom and (pdir / custom).exists():
        path = pdir / custom
        return "custom", avatar_from_photo(path, px * 2), f"custom_{int(path.stat().st_mtime)}"
    if kind == "custom":
        kind = "auto"
    gender = kind if kind in ("male", "female") else narrator_gender(opt, cfg)
    asset = HOST_DIR / f"host_{gender}.jpg"
    if asset.exists():
        return gender, avatar_from_photo(asset, px * 2), f"host_{gender}"
    return gender, make_avatar(gender, px * 2), f"builtin_{gender}"


def build_card_images(project: dict, items: list[dict], width: int, height: int) -> dict[str, Path]:
    pdir = project_dir(project["id"])
    cdir = pdir / "render" / "cards"
    cdir.mkdir(parents=True, exist_ok=True)
    out: dict[str, Path] = {}
    for it in items:
        card = it.get("card")
        if not card:
            continue
        style = card.get("style")
        if style == "rewind":
            img = card_rewind(it["text"], width, height, title=str(project.get("title", ""))[:22])
        else:
            lines = [str(x) for x in (card.get("lines") or []) if str(x).strip()] or [it["text"]]
            img = card_text(card.get("title", ""), lines, width, height,
                            note="세월의 사연극장", cta=bool(card.get("cta")))
        path = cdir / f"{it['scene_id']}_{style or 'card'}.png"
        save(img, path)
        out[it["scene_id"]] = path
    return out


def build_visual_plan(project: dict, items: list[dict], cards: dict[str, Path],
                      width: int, height: int) -> list[dict]:
    pdir = project_dir(project["id"])
    imgs = [dict(x) for x in project.get("image_plan", []) if (pdir / "images" / x["file"]).exists()]
    if not imgs:
        return []
    imgs[0]["start"] = 0.0
    total = float(project.get("duration") or (items[-1]["end"] if items else 10))
    card_iv = [(it["start"], it["end"], cards[it["scene_id"]], it["scene_id"])
               for it in items if it.get("card") and it["scene_id"] in cards]
    bounds = {0.0, total}
    for e in imgs:
        bounds.add(max(0.0, min(total, float(e["start"]))))
        bounds.add(max(0.0, min(total, float(e["end"]))))
    for a, b, *_ in card_iv:
        bounds.add(max(0.0, min(total, a)))
        bounds.add(max(0.0, min(total, b)))
    pts = sorted(bounds)
    visual: list[dict] = []
    for a, b in zip(pts, pts[1:]):
        if b - a < 0.06:
            continue
        mid = (a + b) / 2
        chosen = None
        for cs, ce, path, sid in card_iv:
            if cs - 0.02 <= mid <= ce + 0.02:
                chosen = {"path": path, "card": True, "anchor": sid}
                break
        if chosen is None:
            entry = None
            for e in imgs:
                if e["start"] <= mid < e["end"]:
                    entry = e
                    break
            if entry is None:
                entry = imgs[-1] if mid >= imgs[-1]["end"] else imgs[0]
            chosen = {"path": pdir / "images" / entry["file"], "card": False,
                      "anchor": entry.get("anchor", "")}
        chosen.update({"start": round(a, 3), "end": round(b, 3)})
        if visual and visual[-1]["path"] == chosen["path"] and visual[-1]["card"] == chosen["card"] \
                and abs(visual[-1]["end"] - chosen["start"]) < 0.02:
            visual[-1]["end"] = chosen["end"]
        else:
            visual.append(chosen)
    return visual


# ── 1단계: 장면 세그먼트 ─────────────────────────────────────────────────
def render_segments(project: dict, visual: list[dict], width: int, height: int,
                    enc: dict, progress=None) -> Path:
    pdir = project_dir(project["id"])
    rdir = pdir / "render"
    sdir = rdir / "segments"
    sdir.mkdir(parents=True, exist_ok=True)
    marker = sdir / ".res"
    tag = f"{width}x{height}"
    if marker.exists() and marker.read_text(encoding="utf-8").strip() != tag:
        for old in sdir.glob("*.mp4"):
            old.unlink()
    marker.write_text(tag, encoding="utf-8")
    W2, H2 = int(width * 1.08) // 2 * 2, int(height * 1.08) // 2 * 2
    total = sum(max(0.4, v["end"] - v["start"]) for v in visual)
    done = 0.0
    files = []
    for i, item in enumerate(visual):
        span = max(0.4, float(item["end"]) - float(item["start"]))
        fi = 0.7 if i == 0 else 0.30
        fo = 1.0 if i == len(visual) - 1 else 0.30
        out = sdir / f"seg_{i:03d}.mp4"
        if out.exists() and out.stat().st_size > 2000:
            try:
                from .ffmpeg_util import duration as _dur
                if abs(_dur(out) - span) < 0.8:
                    files.append(out)
                    done += span
                    if progress:
                        progress(int(100 * done / max(1, total)), f"장면 {i + 1}/{len(visual)} (이미 완료)")
                    continue
            except Exception:
                pass
        if item.get("card"):
            vf = (f"scale={width}:{height}:force_original_aspect_ratio=increase,"
                  f"crop={width}:{height},fade=t=in:st=0:d={fi},"
                  f"fade=t=out:st={max(0.0, span - fo):.3f}:d={fo},"
                  f"setsar=1,format=yuv420p")
        else:
            frames = max(2, int(round(span * FPS)))
            zr = 0.10 / frames
            dx, dy = DIRECTIONS[i % len(DIRECTIONS)]
            x = f"(iw-iw/zoom)/2+(iw-iw/zoom)/2*({dx})*on/{frames}"
            y = f"(ih-ih/zoom)/2+(ih-ih/zoom)/2*({dy})*on/{frames}"
            emo = _scene_emotion(project, item.get("anchor", ""))
            vf = (f"scale={W2}:{H2}:force_original_aspect_ratio=increase,crop={W2}:{H2},"
                  f"zoompan=z='min(1.0+{zr:.8f}*on,1.12)':x='{x}':y='{y}':d=1:"
                  f"s={width}x{height}:fps={FPS},{_grade(emo)},vignette=angle=PI/5.5,"
                  f"fade=t=in:st=0:d={fi},fade=t=out:st={max(0.0, span - fo):.3f}:d={fo},"
                  f"setsar=1,format=yuv420p")
        seg_args = ["-c:v", "libx264", "-preset", "ultrafast", "-crf", "18", "-pix_fmt", "yuv420p"] \
            if enc["codec"] == "libx264" else enc["args"]
        cmd = [ffmpeg_exe(), "-y", "-v", "error", "-loop", "1", "-framerate", str(FPS),
               "-t", f"{span:.3f}", "-i", str(item["path"]), "-vf", vf, "-an",
               *seg_args, "-r", str(FPS), str(out)]
        r = run(cmd, timeout=1800)
        if not out.exists() or out.stat().st_size < 2000:
            raise RuntimeError(f"장면 렌더 실패({item['path'].name}): " + (r.stderr or "")[-300:])
        files.append(out)
        done += span
        if progress:
            progress(int(100 * done / max(1, total)), f"장면 {i + 1}/{len(visual)} 렌더")

    listfile = sdir / "list.txt"
    listfile.write_text("\n".join(f"file '{f.name}'" for f in files), encoding="utf-8")
    base = rdir / "base.mp4"
    r = run([ffmpeg_exe(), "-y", "-v", "error", "-f", "concat", "-safe", "0",
             "-i", str(listfile), "-c", "copy", str(base)], timeout=600)
    if not base.exists() or base.stat().st_size < 5000:
        raise RuntimeError("장면 연결 실패: " + (r.stderr or "")[-300:])
    return base


# ── 2단계: 오버레이+음성 ─────────────────────────────────────────────────
def render_overlay(project: dict, items: list[dict], base: Path, mix_path: Path,
                   width: int, height: int, enc: dict, progress=None) -> Path:
    pdir = project_dir(project["id"])
    rdir = pdir / "render"
    (rdir / "fonts").mkdir(parents=True, exist_ok=True)
    for f in FONT_DIR.glob("*.*"):
        shutil.copy2(f, rdir / "fonts" / f.name)
    write_ass(project, items, rdir / "subs.ass", width, height)
    write_srt(project, items, pdir / "output" / "subtitles.srt")

    opt = project["options"]
    total = float(project.get("duration") or items[-1]["end"])
    overlays = project.get("overlays") or {}
    like = overlays.get("like_banner")
    end = overlays.get("end_screen")

    cmd = [ffmpeg_exe(), "-y", "-hide_banner", "-v", "warning", "-i", str(base)]
    idx = 1
    pframes = particle_frames(width, height)
    cmd += ["-stream_loop", "-1", "-framerate", "12", "-i", str(pframes / "f%04d.png")]
    p_idx = idx
    idx += 1

    avatar_idx = badge_idx = end_idx = live_idx = None
    av = avatar_px(width, height)
    m = avatar_margin(width, height)
    host_note = ""
    if opt.get("avatar", True):
        # 실제 초상은 이번 렌더의 첫 프레임(미리보기)에도 쓰이므로 render/avatar.png 로 남긴다
        av_path = rdir / "avatar.png"
        gender, portrait, cache_key = host_portrait(project, load_config(), av)
        host_note = f"{gender} 진행자"
        portrait.save(av_path)
        try:
            frames_dir, frame_n = avatar_motion_frames(portrait, av, key=cache_key, fps=FPS,
                                                       cycle=AVATAR_MOTION_CYCLE,
                                                       move=AVATAR_MOTION_SECONDS)
            cmd += ["-stream_loop", "-1", "-framerate", str(FPS), "-i", str(frames_dir / "a%04d.png")]
            host_note += f" · 모션 {frame_n}프레임"
        except Exception:
            # 모션 생성이 실패해도 정지 아바타로 제작은 계속된다
            cmd += ["-loop", "1", "-i", str(av_path)]
            host_note += " · 정지"
        avatar_idx = idx
        idx += 1
    badge_img = None
    if avatar_idx is not None and opt.get("live_badge", True):
        try:
            bdir, bn = live_badge_frames(width, FPS, LIVE_BADGE_PERIOD)
            cmd += ["-stream_loop", "-1", "-framerate", str(FPS), "-i", str(bdir / "l%03d.png")]
            badge_img = live_badge(width, 1.0)
        except Exception:
            # 시퀀스를 못 만들면 정적 배지 한 장으로
            badge_img = live_badge(width, 1.0)
            bp = rdir / "live_badge.png"
            badge_img.save(bp)
            cmd += ["-loop", "1", "-i", str(bp)]
        live_idx = idx
        idx += 1
    if like and opt.get("like_banner", True):
        b_path = rdir / "badge.png"
        like_badge(width).save(b_path)
        cmd += ["-loop", "1", "-i", str(b_path)]
        badge_idx = idx
        idx += 1
    if end and opt.get("end_screen", True):
        e_path = rdir / "endscreen.png"
        end_screen_overlay(width, height).save(e_path)
        cmd += ["-loop", "1", "-i", str(e_path)]
        end_idx = idx
        idx += 1

    cmd += ["-i", str(mix_path)]
    audio_idx = idx

    # 화면 합성은 RGB 에서 해야 색이 틀어지지 않는다(YUV blend 는 보라색으로 변함)
    # 입자는 알파가 있는 PNG 시퀀스로 얹는다(색 변형 없음)
    parts = [f"[0:v]fps={FPS},format=yuv420p[b0]",
             f"[{p_idx}:v]fps={FPS},scale={width}:{height},format=rgba,"
             f"colorchannelmixer=aa=0.55,setpts=PTS-STARTPTS[pt]",
             "[b0][pt]overlay=0:0:format=auto[p0]"]
    cur = "p0"
    if avatar_idx is not None:
        enable = f":enable='lt(t,{end['start']:.2f})'" if end else ""
        parts.append(f"[{avatar_idx}:v]format=rgba,setsar=1,setpts=PTS-STARTPTS[avs]")
        parts.append(f"[{cur}][avs]overlay=W-w-{m}:H-h-{m}{enable}[p1]")
        cur = "p1"
    if live_idx is not None and badge_img is not None:
        bw, bh = badge_img.size
        # 아바타 위쪽 테두리에 걸치게 — 스튜디오 ON-AIR 태그처럼
        bx = max(0, width - m - av + (av - bw) // 2)
        by = max(0, height - m - av - int(bh * 0.55))
        enable = f":enable='lt(t,{end['start']:.2f})'" if end else ""
        parts.append(f"[{live_idx}:v]format=rgba,setsar=1,setpts=PTS-STARTPTS[lvs]")
        parts.append(f"[{cur}][lvs]overlay={bx}:{by}{enable}[pl]")
        cur = "pl"
    if badge_idx is not None:
        bm = int(width * 0.035)
        bt = int(height * LIKE_TOP)
        parts.append(f"[{badge_idx}:v]format=rgba[bd]")
        parts.append(f"[{cur}][bd]overlay=W-w-{bm}:{bt}:"
                     f"enable='between(t,{like['start']:.2f},{like['end']:.2f})'[p2]")
        cur = "p2"
    if end_idx is not None:
        parts.append(f"[{end_idx}:v]format=rgba[es]")
        parts.append(f"[{cur}][es]overlay=0:0:enable='gte(t,{end['start']:.2f})'[p3]")
        cur = "p3"
    parts.append(f"[{cur}]format=yuv420p,ass=filename=render/subs.ass:fontsdir=render/fonts[vout]")

    out = pdir / "output" / "final.mp4"
    out.parent.mkdir(parents=True, exist_ok=True)
    cmd += ["-filter_complex", ";".join(parts), "-map", "[vout]", "-map", f"{audio_idx}:a",
            "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2",
            *enc["args"], "-r", str(FPS), "-t", f"{total:.3f}",
            "-movflags", "+faststart", "-threads", "0", str(out)]
    (rdir / "cmd.json").write_text(json.dumps(cmd, ensure_ascii=False, indent=1), encoding="utf-8")
    fc = _write_fontconfig(rdir)
    env = os.environ.copy()
    env["FONTCONFIG_FILE"] = str(fc)
    env.setdefault("FONTCONFIG_PATH", str(rdir))
    if progress:
        progress(2, f"자막·입자·진행자 합성 중… {host_note}".strip())
    _popen(cmd, pdir, total, progress, "영상 인코딩", env=env)
    if not out.exists() or out.stat().st_size < 10000:
        raise RuntimeError("영상 파일이 만들어지지 않았습니다. render/ffmpeg.log 를 확인하세요.")
    return out


# ── 전체 ─────────────────────────────────────────────────────────────────
def render_video(project: dict, items: list[dict], mix_path: Path, progress=None) -> Path:
    pdir = project_dir(project["id"])
    from .project import scale_for
    width, height = scale_for(project)
    width, height = width // 2 * 2, height // 2 * 2
    plan = [p for p in project.get("image_plan", []) if (pdir / "images" / p["file"]).exists()]
    if not plan:
        raise RuntimeError("이미지가 없습니다. images 폴더에 s01.png … 를 넣어 주세요.")
    if plan[0]["start"] > 0.05:
        plan[0]["start"] = 0.0
    enc = detect_encoder(load_config().get("encoder", "auto"))
    cards = build_card_images(project, items, width, height)
    visual = build_visual_plan(project, items, cards, width, height)
    if progress:
        progress(1, f"{enc['label']} · 장면 렌더 시작")

    def seg_progress(q, m):
        if progress:
            progress(2 + int(q * 0.48), m)

    base = render_segments(project, visual, width, height, enc, seg_progress)
    if progress:
        progress(52, "장면 연결 완료 · 오버레이 합성")

    def ov_progress(q, m):
        if progress:
            progress(52 + int(q * 0.46), m)

    out = render_overlay(project, items, base, mix_path, width, height, enc, ov_progress)
    # 중간 파일 정리(원본 이미지·대본은 그대로 보관)
    if not load_config().get("keep_segments"):
        for f in (pdir / "render" / "segments").glob("*.mp4"):
            try:
                f.unlink()
            except Exception:
                pass
        try:
            base.unlink()
        except Exception:
            pass
    return out


def _safe_name(name: str) -> str:
    name = re.sub(r"[\\/:*?\"<>|]", "", name).strip()
    return (name or "사연")[:60].replace(" ", "_")


# ── 썸네일 2종 ───────────────────────────────────────────────────────────
def render_thumbnails(project: dict, progress=None) -> dict:
    from .graphics import thumbnail_style1, thumbnail_style2
    pdir = project_dir(project["id"])
    out_dir = pdir / "output" / "thumb"
    out_dir.mkdir(parents=True, exist_ok=True)
    aspect = project["format"]["aspect"]
    if aspect == "9:16":
        w, h = 1080, 1920
    else:
        w, h = 1280, 720
    th = project.get("thumbnail") or {}
    lines1 = (th.get("style1") or [project["title"], "실화 같은 사연"])[:2]
    lines2 = (th.get("style2") or [project["title"], "마지막까지 보세요"])[:5]

    hook_ids = project.get("hook", {}).get("scene_ids") or []
    img = None
    from .project import image_for_scene
    if hook_ids:
        entry = image_for_scene(project, hook_ids[0])
        if entry:
            img = pdir / "images" / entry["file"]
    if not img or not img.exists():
        plan = project.get("image_plan") or []
        if plan:
            img = pdir / "images" / plan[0]["file"]

    badge = "실화 사연"
    if project.get("genre") == "reversal":
        badge = "사이다 반전"
    elif project.get("genre") == "mystery":
        badge = "미스터리"
    p1 = out_dir / "thumbnail_1_인물드라마형.jpg"
    p2 = out_dir / "thumbnail_2_대문짝텍스트형.jpg"
    save(thumbnail_style1(img if img and img.exists() else None, lines1, w, h, badge=badge), p1)
    if progress:
        progress(50, "썸네일 1/2 완성")
    save(thumbnail_style2(lines2, w, h), p2)
    if progress:
        progress(100, "썸네일 2/2 완성")
    return {"style1": str(p1), "style2": str(p2), "width": w, "height": h}


def grab_frames(video: Path, times: list[float], out_dir: Path) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    outs = []
    for i, t in enumerate(times):
        p = out_dir / f"frame_{i:02d}_{t:.1f}.jpg"
        run([ffmpeg_exe(), "-y", "-v", "error", "-ss", f"{t:.2f}", "-i", str(video),
             "-frames:v", "1", "-q:v", "3", str(p)], timeout=120)
        if p.exists():
            outs.append(p)
    return outs
