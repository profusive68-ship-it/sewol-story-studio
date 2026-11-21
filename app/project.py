"""project.json 설계도 — 대본·이미지 계획·타임라인·업로드 카피."""
from __future__ import annotations

import json
import math
import re
from datetime import datetime
from pathlib import Path

from .gemini_script import generate_script, normalize_script
from .paths import project_dir
from .script_templates import build_template_script
from .settings import (FORMAT_PRESETS, GENRES, SUBTITLE_SIZES, load_config)

SCHEMA = "sewol-project/1"
CHARS_PER_SEC = 4.3

CTA_TEXT = ("오늘 이야기가 마음에 남으셨다면, 내일 밤에도 또 찾아뵐 수 있게 "
            "'구독' 버튼 한 번만 눌러주세요. 지금 어느 지역에서 듣고 계신지도 "
            "댓글로 남겨주시면 꼭 읽어보겠습니다. 여러분의 사연도 들려주세요. "
            "댓글로 '사연 제보'라고 남겨주시면 다음 이야기로 찾아뵙겠습니다.")
CTA_SHORT = ("오늘 이야기가 마음에 남으셨다면 구독과 좋아요, 어느 지역에서 듣고 계신지 "
             "댓글로 남겨 주세요. 여러분의 사연도 '사연 제보'로 보내주세요.")
LIKE_VOICE_TEXT = ("잠시만요. 지금 이 상황이 너무 답답하고 화가 나신다면, "
                   "우리 주인공이 끝까지 힘낼 수 있게 아래 '좋아요' 한 번만 꾹 눌러주실래요?")
LIKE_VOICE_SHORT = "지금 이 상황이 답답하시다면, 좋아요 한 번만 꾹 눌러주세요."
LIKE_BANNER_TEXT = "👍 이야기가 몰입되신다면 '좋아요' 눌러주세요!"


def now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def make_id(genre: str) -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + re.sub(r"[^a-z]", "", genre)[:8]


def est_seconds(text: str) -> float:
    return max(1.2, len(text) / CHARS_PER_SEC)


# ── 이미지 계획 (배치 황금 비율) ───────────────────────────────────────────
def build_image_plan(scenes: list[dict], preset: str, target: float) -> list[dict]:
    """초반 3분 4~5장 집중 → 본론 5~7분마다 1장. 쇼츠는 장면마다 1장."""
    seq = [s for s in scenes if not s.get("placement")]
    if not seq:
        seq = scenes[:1]
    if preset == "shorts50":
        chosen = seq[:12]
    else:
        # 장면별 예상 시작 시각
        t = 0.0
        starts: list[tuple[dict, float]] = []
        for s in seq:
            starts.append((s, t))
            t += est_seconds(s["text"]) + 0.28
        total = max(target, t)
        anchors: list[dict] = []
        # 1) 초반 3분: 4~5장 (최소 4장, 영상이 3분보다 짧으면 전체의 앞 60%에 4장)
        intro_end = min(180.0, total * 0.62)
        intro_n = 5 if total >= 240 else 4
        for k in range(intro_n):
            want = intro_end * (k / max(1, intro_n - 1)) if intro_n > 1 else 0
            anchors.append(_scene_at(starts, want))
        # 2) 이후 6분 간격
        pos = intro_end
        while pos < total - 30:
            pos += 360.0
            anchors.append(_scene_at(starts, min(pos, max(0.0, total - 12))))
        chosen, seen = [], set()
        for s in anchors:
            if s["id"] in seen:
                continue
            seen.add(s["id"])
            chosen.append(s)
        if not chosen:
            chosen = seq[:1]

    plan = []
    for i, s in enumerate(chosen, start=1):
        plan.append({
            "file": f"s{i:02d}.png",
            "anchor": s["id"],
            "prompt": s.get("image_prompt", ""),
            "caption": s.get("image_caption", ""),
            "line": s.get("text", ""),
        })
    return plan


def _scene_at(starts: list[tuple[dict, float]], t: float) -> dict:
    pick = starts[0][0]
    for s, st in starts:
        if st <= t + 0.5:
            pick = s
        else:
            break
    return pick


# ── 프로젝트 생성 ─────────────────────────────────────────────────────────
def create_project(payload: dict, progress=None) -> dict:
    cfg = load_config()
    preset = payload.get("preset") or "pilot5"
    if preset not in FORMAT_PRESETS:
        raise ValueError("알 수 없는 영상 형식입니다.")
    if preset == "weekend":
        raise ValueError("주말 몰아듣기는 완성된 프로젝트를 골라 [합본 만들기]로 만듭니다.")
    fmt = FORMAT_PRESETS[preset]
    genre = payload.get("genre") or "tear_family"
    if genre not in GENRES:
        genre = "free"

    settings = {
        "genre": genre,
        "genre_label": GENRES[genre]["label"],
        "topic": (payload.get("topic") or "").strip()[:300],
        "preset": preset,
        "target_seconds": float(fmt["target"]),
        "aspect": fmt["aspect"],
        "hook15": bool(payload.get("hook15", True)),
        "sequel": bool(payload.get("sequel", True)),
        "voice_mode": payload.get("voice_mode") or "multi",
        "rate": max(-5, min(10, int(payload.get("rate") or 0))),
        "subtitle_size": payload.get("subtitle_size") or "senior",
        "avatar": bool(payload.get("avatar", True)),
        "avatar_kind": payload.get("avatar_kind") or "female",
        "image_mode": payload.get("image_mode") or "B",
        "outro_cta": bool(payload.get("outro_cta", True)),
        "teaser_mode": payload.get("teaser_mode") or "auto_sequel",
        "teaser_text": (payload.get("teaser_text") or "").strip()[:300],
        "like_banner": bool(payload.get("like_banner", True)),
        "like_voice": bool(payload.get("like_voice", True)),
        "like_voice_text": (payload.get("like_voice_text") or "").strip()[:200],
        "cta_text": (payload.get("cta_text") or "").strip()[:300],
        "end_screen": bool(payload.get("end_screen", True)),
        "sleep_rain": bool(payload.get("sleep_rain", False)),
        "youtube_privacy": payload.get("youtube_privacy") or "private",
        "youtube_publish_at": (payload.get("youtube_publish_at") or "").strip(),
        "youtube_title_index": int(payload.get("youtube_title_index") or 0),
        "auto_upload": bool(payload.get("auto_upload", False)),
        "bgm": bool(payload.get("bgm", True)),
        "sfx": bool(payload.get("sfx", True)),
    }
    if settings["voice_mode"] not in ("multi", "male", "female"):
        settings["voice_mode"] = "multi"
    if settings["teaser_mode"] not in ("auto_sequel", "next_story", "manual"):
        settings["teaser_mode"] = "auto_sequel"

    warnings: list[str] = []
    script = None
    if progress:
        progress(2, "대본 준비 중…")
    if (cfg.get("gemini_api_key") or "").strip():
        try:
            script = normalize_script(generate_script(settings, cfg, progress), settings)
        except Exception as e:
            warnings.append(f"Gemini 대본 생성 실패 → 예시 대본으로 대체했습니다. ({str(e)[:120]})")
    else:
        warnings.append("Gemini API 키가 없어 예시 대본으로 만들었습니다. API 키를 저장하면 완전자동 대본이 나옵니다.")

    if script is None:
        script = build_template_script(settings)

    # 엔딩 떡밥 확정 (6개월 뒤 복선 / 다음 사연 예고 / 직접 입력)
    script["resolved_teaser"] = resolve_teaser(script, settings)

    # 장면 id·되감기 카드·엔딩(예고 → 구독/지역 인사) 정리
    script = _prepare_scenes(script, settings)

    pid = make_id(genre)
    pdir = project_dir(pid)
    for sub in ("images", "audio", "audio_clips", "output", "output/thumb"):
        (pdir / sub).mkdir(parents=True, exist_ok=True)

    project = {
        "schema": SCHEMA,
        "id": pid,
        "title": script["title"],
        "genre": genre,
        "genre_label": GENRES[genre]["label"],
        "created_at": now(),
        "updated_at": now(),
        "format": {
            "preset": preset, "label": fmt["label"], "aspect": fmt["aspect"],
            "width": int(fmt["width"]), "height": int(fmt["height"]),
            "target_seconds": int(fmt["target"]),
        },
        "options": settings,
        "source": script.get("source", "template"),
        "logline": script.get("logline", ""),
        "setting": script.get("setting", ""),
        "characters": script.get("characters", []),
        "evidence": script.get("evidence", []),
        "acts": script.get("acts", []),
        "hook": {
            "enabled": settings["hook15"],
            "scene_ids": script["hook"].get("scene_ids", []),
            "caption": script["hook"].get("caption", ""),
            "rewind_caption": script["hook"].get("rewind_caption") or "그날보다 사흘 전.",
        },
        "scenes": script["scenes"],
        "chapters": script.get("chapters", []),
        "image_plan": build_image_plan(script["scenes"], preset, float(fmt["target"])),
        "thumbnail": script.get("thumbnail", {}),
        "upload": script.get("upload", {}),
        "titles": script.get("titles") or [],
        "hashtags": script.get("hashtags") or [],
        "description": script.get("description") or "",
        "sequel_teaser": script.get("resolved_teaser", ""),
        "next_story": script.get("next_story", {}),
        "teaser_mode": settings["teaser_mode"],
        "warnings": warnings,
        "status": {"stage": "created", "percent": 0, "message": "대본과 이미지 요청서가 준비되었습니다.", "updated": now()},
        "outputs": {},
        "timeline": [],
    }
    if project.get("source") == "template" and float(fmt["target"]) >= 600:
        warnings.append("예시 대본은 실제 목표 길이보다 짧습니다. Gemini API 키를 저장하면 목표 길이에 맞춰 생성됩니다.")
        project["warnings"] = warnings
    _write(project)
    write_script_json(project, script)
    write_license_cc0(pid)
    write_image_request(project)
    write_upload_copy(project)
    return project


def resolve_teaser(script: dict, settings: dict) -> str:
    """엔딩에 붙일 떡밥 문장을 고른다."""
    if not settings.get("sequel"):
        return ""
    mode = settings.get("teaser_mode", "auto_sequel")
    if mode == "manual":
        text = (settings.get("teaser_text") or "").strip()
        if text:
            return text
        mode = "auto_sequel"
    if mode == "next_story":
        ns = script.get("next_story") or {}
        teaser = (ns.get("teaser") or "").strip()
        title = (ns.get("title") or "").strip()
        if teaser:
            return (f"다음 사연은 「{title}」입니다. " if title else "") + teaser
    return (script.get("sequel_teaser") or "").strip()


def _prepare_scenes(script: dict, settings: dict) -> dict:
    scenes = script["scenes"]
    hook_objs = [s for s in scenes if s.get("id") in set(script.get("hook", {}).get("scene_ids", []))]
    for i, sc in enumerate(scenes, start=1):
        sc["id"] = f"s{i:02d}"
        sc.setdefault("chapter", 1)
        sc.setdefault("emotion", "heal")
        sc.setdefault("sfx", [])
        sc.setdefault("speaker", "narrator")

    # 되감기 카드: 훅 바로 뒤
    if settings.get("hook15") and not any(s.get("placement") == "after_hook" for s in scenes):
        caption = script["hook"].get("rewind_caption") or "그날보다 사흘 전."
        scenes.insert(min(2, len(scenes)), {
            "id": "", "speaker": "narrator", "text": caption, "emotion": "heal", "sfx": [],
            "image_prompt": scenes[0].get("image_prompt", ""), "image_caption": caption,
            "placement": "after_hook", "chapter": scenes[0].get("chapter", 1),
            "chapter_title": "되감기",
        })

    # 후속편 예고
    teaser = (script.get("resolved_teaser") or script.get("sequel_teaser") or "").strip()
    if settings.get("sequel") and teaser:
        scenes.append({
            "id": "", "speaker": "narrator", "text": teaser, "emotion": "heal", "sfx": [],
            "image_prompt": "", "image_caption": "후속편 예고", "placement": "teaser",
            "card": {"style": "teaser", "title": "다음 이야기", "lines": _split_card(teaser)},
            "chapter": 99, "chapter_title": "예고",
        })

    # 중반부(약 55%) 좋아요 음성 멘트 — 화면 배너가 아니라 해설자가 직접 말한다
    if settings.get("like_voice") and settings["preset"] != "weekend":
        mid_text = (settings.get("like_voice_text") or "").strip()
        if not mid_text:
            mid_text = LIKE_VOICE_SHORT if settings["preset"] == "shorts50" else LIKE_VOICE_TEXT
        scenes.append({
            "id": "", "speaker": "narrator", "text": mid_text, "emotion": "twist", "sfx": [],
            "image_prompt": "", "image_caption": "좋아요 멘트", "placement": "mid",
            "card": None, "chapter": 0, "chapter_title": "좋아요",
        })

    # 채널 구독·지역 댓글 안내: 영상 맨 끝에만 (해설자가 직접 낭독)
    if settings.get("outro_cta"):
        text = (settings.get("cta_text") or "").strip()
        if not text:
            text = CTA_SHORT if settings["preset"] == "shorts50" else CTA_TEXT
        scenes.append({
            "id": "", "speaker": "narrator", "text": text, "emotion": "heal", "sfx": [],
            "image_prompt": "", "image_caption": "구독·지역 인사",
            "placement": "end", "card": {"style": "cta", "title": "세월의 사연극장",
                                          "lines": _split_card(text, 16), "cta": True},
            "chapter": 99, "chapter_title": "엔딩",
        })

    for sc in scenes:
        if sc.get("placement") == "after_hook" and not sc.get("card"):
            sc["card"] = {"style": "rewind"}
    for i, sc in enumerate(scenes, start=1):
        sc["id"] = f"s{i:02d}"
    if hook_objs:
        script["hook"]["scene_ids"] = [s["id"] for s in hook_objs]
    return script


def _split_card(text: str, width: int = 18) -> list[str]:
    import textwrap
    return textwrap.wrap(text, width=width)[:5]


# ── 저장/불러오기 ─────────────────────────────────────────────────────────
def _write(project: dict) -> None:
    project["updated_at"] = now()
    pdir = project_dir(project["id"])
    pdir.mkdir(parents=True, exist_ok=True)
    (pdir / "project.json").write_text(json.dumps(project, ensure_ascii=False, indent=2), encoding="utf-8")


def save(project: dict) -> None:
    _write(project)


def load(pid: str) -> dict:
    p = project_dir(pid) / "project.json"
    if not p.exists():
        raise FileNotFoundError("프로젝트를 찾을 수 없습니다.")
    d = json.loads(p.read_text(encoding="utf-8"))
    # 예전에 만든 프로젝트도 카드가 빠지지 않게 보정
    for sc in d.get("scenes", []):
        if sc.get("placement") == "after_hook" and not sc.get("card"):
            sc["card"] = {"style": "rewind"}
    return d


def list_projects() -> list[dict]:
    from .paths import PROJECTS_DIR
    out = []
    for p in sorted(PROJECTS_DIR.glob("*/project.json"), key=lambda x: x.stat().st_mtime, reverse=True):
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
            out.append({
                "id": d.get("id"), "title": d.get("title"), "genre_label": d.get("genre_label"),
                "format": (d.get("format") or {}).get("label"),
                "aspect": (d.get("format") or {}).get("aspect"),
                "created_at": d.get("created_at"), "status": d.get("status", {}),
                "image_count": len(d.get("image_plan", [])),
                "outputs": d.get("outputs", {}),
                "source": d.get("source"),
            })
        except Exception:
            continue
    return out


def set_status(project: dict, stage: str, percent: int, message: str) -> None:
    project["status"] = {"stage": stage, "percent": max(0, min(100, percent)),
                         "message": message, "updated": now()}
    _write(project)


# ── 타임라인 ──────────────────────────────────────────────────────────────
def play_order(project: dict) -> list[tuple[dict, str]]:
    """(장면, 재생 종류) 목록. 종류: hook | rewind | body | teaser | end"""
    scenes = project["scenes"]
    by_id = {s["id"]: s for s in scenes}
    ordered: list[tuple[dict, str]] = []
    if project["options"].get("hook15") and project.get("hook", {}).get("enabled", True):
        for sid in project["hook"].get("scene_ids", []):
            if sid in by_id:
                ordered.append((by_id[sid], "hook"))
        ordered.extend([(s, "rewind") for s in scenes if s.get("placement") == "after_hook"])
    body = [s for s in scenes if s.get("placement") not in ("after_hook", "mid", "teaser", "end")]
    if project.get("format", {}).get("aspect") == "9:16":
        hook_ids = set(project.get("hook", {}).get("scene_ids", []))
        trimmed = [s for s in body if s["id"] not in hook_ids]
        if len(trimmed) >= 3:
            body = trimmed
    ordered.extend([(s, "body") for s in body])
    ordered.extend([(s, "teaser") for s in scenes if s.get("placement") == "teaser"])
    ordered.extend([(s, "end") for s in scenes if s.get("placement") == "end"])
    return ordered


GAPS = {"hook": 0.10, "rewind": 0.30, "body": 0.22, "mid": 1.35, "teaser": 1.4, "end": 1.0}


def _layout(order: list[tuple[dict, str]], durations: dict[str, float]) -> tuple[list[dict], float]:
    items: list[dict] = []
    t = 0.35
    prev = None
    for scene, kind in order:
        dur = float(durations.get(scene["id"], est_seconds(scene["text"])))
        if kind == "body" and prev in ("rewind", "hook"):
            gap = 0.55
        else:
            gap = GAPS.get(kind, 0.25)
        t += gap
        items.append({
            "kind": kind,
            "scene_id": scene["id"],
            "speaker": scene.get("speaker", "narrator"),
            "text": scene["text"],
            "emotion": scene.get("emotion", "heal"),
            "sfx": scene.get("sfx", []),
            "card": scene.get("card"),
            "audio": f"audio_clips/{scene['id']}.mp3",
            "start": round(t, 3),
            "end": round(t + dur, 3),
            "duration": round(dur, 3),
        })
        t += dur
        prev = kind
    return items, t + 1.2


def build_timeline(project: dict, durations: dict[str, float]) -> list[dict]:
    """TTS 실측 길이로 초 단위 타임라인을 만든다. (중반 좋아요 음성·배너, 10초 최종화면 포함)"""
    order = play_order(project)
    items, total = _layout(order, durations)

    # 좋아요 음성 멘트를 전체의 약 55% 지점, 마지막 본문 장면 뒤에 끼워 넣는다
    mid_scenes = [s for s in project["scenes"] if s.get("placement") == "mid"]
    if mid_scenes and project["options"].get("like_voice", True):
        mid_scene = mid_scenes[0]
        target = total * 0.55
        body_idx = [i for i, it in enumerate(items) if it["kind"] == "body" and it["start"] <= target]
        idx = body_idx[-1] if body_idx else max(0, len(order) - 1)
        order = order[:idx + 1] + [(mid_scene, "mid")] + order[idx + 1:]
        items, total = _layout(order, durations)

    # 엔딩 10초 최종화면
    end_items = [it for it in items if it["kind"] == "end"]
    if project["options"].get("end_screen", True) and end_items:
        total = max(total, end_items[-1]["start"] + 10.2)
    total = round(total, 3)

    timing: dict[str, dict] = {}
    for it in items:
        timing.setdefault(it["scene_id"], {"start": it["start"], "end": it["end"]})
    for sc in project["scenes"]:
        if sc["id"] in timing:
            sc["start"], sc["end"] = timing[sc["id"]]["start"], timing[sc["id"]]["end"]
        else:
            sc["start"], sc["end"] = None, None

    plan = project.get("image_plan", [])
    starts = []
    for img in plan:
        st = timing.get(img["anchor"], {}).get("start")
        if st is None:
            st = _nearest_start(timing, img["anchor"], project["scenes"])
        starts.append(st if st is not None else 0.0)
    for i, img in enumerate(plan):
        img["start"] = round(starts[i], 3)
        img["end"] = round(starts[i + 1] if i + 1 < len(starts) else total, 3)
    if plan:
        plan[-1]["end"] = total

    if items:
        first = items[0]
        img = image_for_scene(project, first["scene_id"])
        if img:
            first["image"] = img["file"]
            first["image_start"] = 0.0
            first["image_end"] = first["end"]
        if plan and plan[0]["start"] > 0.1:
            plan[0]["start"] = 0.0

    for ch in project.get("chapters", []):
        ch["time"] = timing.get(ch.get("anchor"), {}).get("start")

    overlays = {}
    mid_item = next((it for it in items if it["kind"] == "mid"), None)
    if project["options"].get("like_banner", True) and total > 40:
        like_start = mid_item["start"] if mid_item else round(total * 0.55, 2)
        overlays["like_banner"] = {"start": round(like_start, 2), "end": round(like_start + 5.0, 2),
                                   "text": LIKE_BANNER_TEXT}
    if project["options"].get("end_screen", True):
        overlays["end_screen"] = {"start": round(max(0.0, total - 10.0), 2), "end": total}
    project["overlays"] = overlays

    project["timeline"] = items
    project["duration"] = total
    return items


def _nearest_start(timing: dict, anchor: str, scenes: list[dict]) -> float | None:
    ids = [s["id"] for s in scenes]
    try:
        idx = ids.index(anchor)
    except ValueError:
        return None
    for s in reversed(scenes[:idx + 1]):
        if s["id"] in timing:
            return timing[s["id"]]["start"]
    for s in scenes[idx:]:
        if s["id"] in timing:
            return timing[s["id"]]["start"]
    return None


def image_for_scene(project: dict, scene_id: str) -> dict | None:
    plan = project.get("image_plan", [])
    if not plan:
        return None
    ids = [s["id"] for s in project["scenes"]]
    try:
        idx = ids.index(scene_id)
    except ValueError:
        return plan[0]
    best = plan[0]
    for img in plan:
        try:
            if ids.index(img["anchor"]) <= idx:
                best = img
        except ValueError:
            continue
    return best


# ── 이미지 요청서 ─────────────────────────────────────────────────────────
def write_image_request(project: dict) -> Path:
    pdir = project_dir(project["id"])
    fmt = project["format"]
    lines = []
    lines.append("=" * 64)
    lines.append(f"『세월의 사연극장』 이미지 요청서 — {project['title']}")
    lines.append(f"프로젝트: {project['id']}   형식: {fmt['label']} ({fmt['aspect']}, {fmt['width']}×{fmt['height']})")
    lines.append("=" * 64)
    lines.append("")
    lines.append("[사용 방법]")
    lines.append("1) 아래 파일 이름 그대로 이미지를 받아 이 폴더의 images/ 안에 넣습니다.")
    lines.append("2) 웹 화면에서 [영상 조립 시작]을 누르면 대사 길이에 맞춰 초 단위로 자동 조립됩니다.")
    lines.append("3) 파일 이름이 다르면 인식되지 않습니다. (예: s01.png, s02.png …)")
    lines.append("4) 케빈에게 요청할 때는 이 파일 내용을 그대로 보내면 됩니다.")
    lines.append("")
    lines.append("[배치 원칙] 초반 3분에 4~5장을 집중 배치하고, 본론은 5~7분마다 1장씩 천천히 흐릅니다.")
    lines.append("            모든 이미지에 느린 줌(Ken Burns)과 먼지·빛 입자가 자동으로 들어갑니다.")
    lines.append("")
    lines.append(f"총 {len(project.get('image_plan', []))}장")
    lines.append("")
    if project.get("characters"):
        lines.append("[인물 일관성 — 모든 이미지에 같은 얼굴로]")
        for c in project["characters"]:
            lines.append(f"· {c.get('name','')}: {c.get('desc_en','')}")
        lines.append("")
    for i, img in enumerate(project.get("image_plan", []), start=1):
        lines.append("-" * 64)
        lines.append(f"[{i}] 파일명: {img['file']}")
        if img.get("start") is not None and img.get("end") is not None:
            lines.append(f"    구간: {_mmss(img['start'])} ~ {_mmss(img['end'])} "
                         f"({max(1, round(img['end'] - img['start']))}초)")
        else:
            lines.append("    구간: 영상 조립 시 대사 길이에 맞춰 자동 계산")
        lines.append(f"    장면: {img.get('caption','')}")
        lines.append(f"    대사: “{img.get('line','')}”")
        lines.append(f"    영문 프롬프트: {img.get('prompt','')}")
    lines.append("-" * 64)
    lines.append("")
    lines.append("※ 화면 안에 글자·자막·로고가 들어간 이미지는 피해 주세요. 자막은 영상에서 따로 얹습니다.")
    path = pdir / "이미지_요청서.txt"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def _mmss(sec: float) -> str:
    sec = max(0, int(round(sec)))
    return f"{sec // 60:02d}:{sec % 60:02d}"


# ── 업로드 카피 ───────────────────────────────────────────────────────────
FIXED_COMMENT = ("여러분이라면 어떻게 하셨을까요? 어느 지역에서 듣고 계신지 댓글로 남겨주세요! 🌷\n"
                 "사연 속 주인공을 응원하는 한마디도 함께 남겨주시면 큰 힘이 됩니다.\n"
                 "여러분의 사연도 들려주세요. 댓글로 '사연 제보'라고 남겨주시면 다음 이야기로 찾아뵙겠습니다.")


def _chapter_lines(project: dict) -> list[str]:
    chapter_lines = ["00:00 훅 — 가장 충격적인 장면"]
    used = {0}
    for ch in project.get("chapters", []):
        t = ch.get("time")
        if t is None or t < 8:
            continue
        sec = int(t)
        if any(abs(sec - u) < 5 for u in used):
            continue
        used.add(sec)
        chapter_lines.append(f"{_mmss(sec)} {ch.get('title') or '이야기'}")
    for it in project.get("timeline", []):
        t = int(it.get("start") or 0)
        if it.get("kind") == "teaser" and not any(abs(t - u) < 5 for u in used):
            used.add(t)
            chapter_lines.append(f"{_mmss(t)} 다음 이야기 예고")
        if it.get("kind") == "end" and not any(abs(t - u) < 5 for u in used):
            used.add(t)
            chapter_lines.append(f"{_mmss(t)} 구독·지역 인사")
    return chapter_lines


def build_upload_pack(project: dict) -> dict:
    """제목 3안 · 설명문(챕터+구독/제보+해시태그) · 고정댓글을 한 묶음으로 만든다."""
    up = project.get("upload") or {}
    title = (up.get("title") or project.get("title") or "세월의 사연").strip()
    titles: list[str] = []
    for t in (project.get("titles") or up.get("titles") or []):
        t = str(t).strip()
        if t and t not in titles:
            titles.append(t)
    if project.get("title") and project["title"] not in titles:
        titles.insert(0, project["title"])
    while len(titles) < 3:
        titles.append(title if len(titles) == 0 else f"{title} — {['감동 실화', '반전 결말', '마지막 한마디'][len(titles) % 3]}")

    body = (project.get("description") or up.get("description") or project.get("logline") or "").strip()
    if not body:
        body = f"{title}\n\n사연은 창작·각색된 이야기입니다."
    chapter_lines = _chapter_lines(project)
    hashtags = [str(h).strip() for h in (project.get("hashtags") or up.get("hashtags") or []) if str(h).strip()]
    if len(hashtags) < 8:
        for d in ["#사연", "#라디오드라마", "#감동사연", "#사이다", "#가족사연",
                  "#시니어", "#노인사연", "#실화같은이야기", "#세월의사연극장", "#사연제보"]:
            if d not in hashtags:
                hashtags.append(d)
    hashtags = hashtags[:10]

    cta = ("구독과 좋아요 부탁드립니다. 여러분의 사연도 댓글로 '사연 제보'라고 남겨주세요. "
           "어느 지역에서 듣고 계신지 인사도 남겨주시면 꼭 읽어보겠습니다.")
    parts = [body]
    if len(chapter_lines) >= 3:
        parts.append("\n".join(chapter_lines))
    parts.append(cta)
    parts.append(" ".join(hashtags))
    description = "\n\n".join(p for p in parts if p)

    pack = {
        "titles": titles[:3],
        "description": description,
        "hashtags": hashtags,
        "chapters": chapter_lines,
        "pinned_comment": FIXED_COMMENT,
    }
    project["upload_pack"] = pack
    return pack


def write_upload_copy(project: dict) -> Path:
    pdir = project_dir(project["id"])
    up = project.get("upload") or {}
    tags = up.get("tags") or [h.lstrip("#") for h in (project.get("hashtags") or ["사연", "라디오드라마"])]
    pack = build_upload_pack(project)

    lines = ["[제목 3안 — 조회수 공식: 억울함/갈등 + 결정적 행동/단서 + 충격 반전]", ""]
    for i, t in enumerate(pack["titles"], start=1):
        lines.append(f"{i}. {t}")
    lines += ["", "[설명문 — 그대로 복사해서 붙여넣으세요]", pack["description"], ""]
    lines += ["[챕터 타임라인 — 유튜브 챕터용]", "\n".join(pack["chapters"]), ""]
    lines += ["[해시태그]", " ".join(pack["hashtags"]), ""]
    lines.append("[태그 — 콤마 구분]")
    lines.append(", ".join("#" + str(t).lstrip("#") for t in tags))
    lines.append("")
    lines.append("[고정댓글 — 영상 올린 뒤 이 댓글을 고정하세요]")
    lines.append(pack["pinned_comment"])
    lines.append("")
    if project.get("sequel_teaser"):
        lines.append("[후속편 안내]")
        lines.append(project["sequel_teaser"])
        lines.append("")
    lines.append("[유튜브 업로드 체크 — 수익창출 안전장치]")
    lines.append("· YouTube Studio 업로드 → 세부정보 → '변형 또는 합성된 콘텐츠'에서")
    lines.append("  '예, AI 생성 콘텐츠가 포함되어 있습니다'를 체크하세요. (AI 대본·이미지·음성 사용)")
    lines.append("· 설명란에는 사연이 창작/각색되었음을 한 줄로 밝혀 두면 심사에 안전합니다.")
    lines.append("· 이 폴더의 script.json · project.json · images/ · audio_clips/ · final.mp4 · upload_copy.txt 는")
    lines.append("  수익창출 심사용 작업 원본입니다. 지우지 말고 그대로 보관하세요.")
    lines.append("· 효과음 출처는 LICENSE_CC0.txt 에 정리되어 있습니다.")
    lines.append("")
    lines.append("[썸네일 문구]")
    th = project.get("thumbnail", {})
    lines.append("· 인물 드라마형: " + " / ".join(th.get("style1", [])))
    lines.append("· 대문짝 텍스트형: " + " / ".join(th.get("style2", [])))
    path = pdir / "upload_copy.txt"
    path.write_text("\n".join(lines), encoding="utf-8")
    save(project)
    return path


# ── 수익창출(YPP) 심사용 원본 보관 ────────────────────────────────────────
def write_script_json(project: dict, script: dict) -> Path:
    """대본 원본(설계·장면·인물·물증)을 지우지 않고 보관한다."""
    pdir = project_dir(project["id"])
    data = {
        "schema": "sewol-script/1",
        "project_id": project["id"],
        "title": script.get("title"),
        "source": script.get("source"),
        "created_at": project.get("created_at"),
        "setting": script.get("setting", ""),
        "logline": script.get("logline", ""),
        "characters": script.get("characters", []),
        "evidence": script.get("evidence", []),
        "acts": script.get("acts", []),
        "hook": script.get("hook", {}),
        "chapters": script.get("chapters", []),
        "scenes": script.get("scenes", []),
        "sequel_teaser": script.get("resolved_teaser") or script.get("sequel_teaser", ""),
        "next_story": script.get("next_story", {}),
        "thumbnail": script.get("thumbnail", {}),
        "upload": script.get("upload", {}),
        "voice": __import__("app.tts", fromlist=["voice_report"]).voice_report(project),
    }
    path = pdir / "script.json"
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def write_license_cc0(pid: str) -> Path:
    """프로젝트 폴더에 내장 SFX 라이선스(CC0) 안내를 자동 생성."""
    from .paths import BASE
    pdir = project_dir(pid)
    src = BASE / "sfx_library" / "credits.json"
    lines = ["세월의 사연극장 — 효과음 라이선스 안내 (수익창출 심사 제출용)", "=" * 60, ""]
    lines.append("이 프로젝트에 사용된 모든 효과음은 Freesound 에서 Creative Commons 0 (CC0, 퍼블릭 도메인)로")
    lines.append("배포된 실음원입니다. CC0 는 출처 표기 없이도 상업적 사용·수정·재배포가 가능합니다.")
    lines.append("아래 목록은 패키지 sfx_library/ 에 함께 들어 있는 원본과 출처입니다.")
    lines.append("")
    try:
        data = json.loads(src.read_text(encoding="utf-8"))
        for c in data:
            sid = c.get("freesound_id", "-")
            url = f"https://freesound.org/s/{sid}/" if sid and sid != "-" else "(세션 확보분)"
            lines.append(f"- {c.get('tag','')}: {c.get('title','')} | {c.get('license','CC0')} | {url}")
    except Exception:
        lines.append("- sfx_library/credits.json 를 참고하세요.")
    lines.append("")
    lines.append("배경음악(BGM)과 일부 생활음은 이 패키지에서 직접 합성했으며, 외부 음원을 사용하지 않았습니다.")
    lines.append("생성 이미지·대본은 이 프로젝트에서 AI(Gemini)로 만들었거나 사용자가 제공한 것입니다.")
    lines.append("")
    lines.append("※ 유튜브 업로드 시 '변형 또는 합성된 콘텐츠(AI 생성)' 항목을 체크하세요.")
    path = pdir / "LICENSE_CC0.txt"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


# ── 모드 B: 사용자 이미지 확인 ───────────────────────────────────────────
def missing_images(project: dict) -> list[str]:
    pdir = project_dir(project["id"]) / "images"
    missing = []
    for img in project.get("image_plan", []):
        if not (pdir / img["file"]).exists():
            missing.append(img["file"])
    return missing


def scale_for(project: dict) -> tuple[int, int]:
    cfg = load_config()
    f = float(cfg.get("force_scale") or 0)
    w, h = project["format"]["width"], project["format"]["height"]
    if f and 0 < f < 1:
        # 짝수 해상도 유지
        w = int(w * f) // 2 * 2
        h = int(h * f) // 2 * 2
    return w, h
