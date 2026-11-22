"""세월의 사연극장 — 로컬 웹 스튜디오 (FastAPI)."""
from __future__ import annotations

import io
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import traceback
import uuid
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import __version__
from .audio_mix import build_mix
from .compile_parts import compile_weekend
from .ffmpeg_util import FFmpegMissing, ffmpeg_exe, version as ffmpeg_version
from .gemini_images import generate_images
from .gemini_script import SYSTEM_RULES, engine_tag
from .paths import (ASSETS_DIR, BASE, PROJECTS_DIR, STATIC_DIR, ensure_dirs,
                    project_dir)
from .project import (CTA_SHORT, CTA_TEXT, LIKE_VOICE_SHORT, LIKE_VOICE_TEXT, build_timeline,
                      build_upload_pack, create_project, list_projects, load, missing_images, now,
                      read_script_view, save_edited_script, save, set_status,
                      write_image_request, write_upload_copy)
from .pronunciation import ensure_pron_file
from .render import detect_encoder, encoder_info, render_thumbnails, render_video
from .settings import (AVATAR_GENDERS, AVATAR_KINDS, AVATAR_SIZE_PX, DEFAULT_GITHUB_REPO,
                       FORMAT_PRESETS, GENRES, LIVE_BADGE_DEFAULT, LIVE_BADGE_PERIOD,
                       AVATAR_MOTION_CYCLE, AVATAR_MOTION_SECONDS, OPENAI_SCRIPT_MODELS,
                       OPENAI_TTS_MODELS, SCRIPT_ENGINES,
                       SUBTITLE_SIZES, TTS_ENGINES, VOICE_MODES, STORY_TONES, load_config, public_config,
                       save_config,
                       BREATH_GAP_MAX, BREATH_GAP_MIN, BREATH_GAP_SECONDS, NARRATION_SPEED,
                       SPEED_TOLERANCE)
from .tts import (breath_gap, build_voice_plan, clip_path, preview_dir, preview_path,
                  project_voice_plan, separation_violations, speed_values,
                  synthesize_line_preview, synthesize_sync, test_openai_tts, voice_report,
                  write_voice_meta)
from .suggest import suggest_ideas
from . import youtube_upload as yt
from . import strategy as st
from . import comments as cm
from . import netinfo as net
from . import scheduler as sch
from . import github_issue as gh
from . import inbox_watch as ib
from .shorts import extract_shorts

ensure_dirs()
ensure_pron_file()

app = FastAPI(title="세월의 사연극장 스튜디오", version=__version__)


@app.on_event("startup")
def _startup():
    try:
        sch.start_worker()
    except Exception:
        pass
    try:
        ib.start_worker()
    except Exception:
        pass
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
if ASSETS_DIR.exists():
    app.mount("/assets", StaticFiles(directory=str(ASSETS_DIR)), name="assets")


@app.middleware("http")
async def pin_guard(request, call_next):
    try:
        pin = sch.load_settings().get("pin", "")
    except Exception:
        pin = ""
    host = (request.client.host if request.client else "") or ""
    local = host in ("127.0.0.1", "::1", "localhost")
    path = request.url.path
    if pin and not local and not path.startswith("/static") and path not in ("/login", "/api/login"):
        supplied = request.query_params.get("pin") or ""
        cookie = request.cookies.get("sewol_pin", "")
        if supplied == pin or cookie == pin:
            response = await call_next(request)
            if supplied == pin:
                response.set_cookie("sewol_pin", pin, httponly=True, max_age=60 * 60 * 24 * 30)
            return response
        if path.startswith("/api/"):
            return JSONResponse({"error": "접속 비밀번호가 필요합니다.", "need_pin": True}, status_code=401)
        return JSONResponse({"error": "비밀번호가 필요합니다. 주소 뒤에 ?pin=비밀번호를 붙여 주세요."}, status_code=401)
    return await call_next(request)

JOBS: dict[str, dict] = {}
JOBS_LOCK = threading.Lock()
EXEC = ThreadPoolExecutor(max_workers=1, thread_name_prefix="sewol")
PID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9\-_]{2,80}$")
STEP_LABELS = {1: "대본", 2: "이미지", 3: "성우·발음", 4: "배경음·효과음",
               5: "영상 만들기", 6: "썸네일·카피"}


# ── 작업(job) ────────────────────────────────────────────────────────────
def _job_update(jid: str, **kw) -> None:
    with JOBS_LOCK:
        j = JOBS.get(jid)
        if j:
            j.update(kw)
            j["updated"] = now()


def start_job(kind: str, fn, *args, project_id: str | None = None) -> str:
    jid = uuid.uuid4().hex[:12]
    with JOBS_LOCK:
        JOBS[jid] = {"id": jid, "kind": kind, "status": "running", "percent": 0,
                     "message": "시작하는 중…", "project_id": project_id,
                     "started": now(), "log": [], "result": None, "error": None}

    def progress(pct: int, msg: str, step: int | None = None, stages: dict | None = None) -> None:
        with JOBS_LOCK:
            j = JOBS.get(jid)
            if not j:
                return
            j["percent"] = max(j.get("percent", 0), min(100, int(pct)))
            j["message"] = msg
            if step:
                j["step"] = int(step)
                j["step_label"] = STEP_LABELS.get(int(step), "")
            if stages:
                j["stages"] = {str(k): int(v) for k, v in dict(stages).items()}
            log = j.setdefault("log", [])
            if not log or log[-1] != msg:
                log.append(msg)
            del log[:-200]

    def runner():
        try:
            result = fn(*args, progress=progress)
            _job_update(jid, status="done", percent=100, message="완료", result=result)
        except Exception as e:
            tb = traceback.format_exc()
            _job_update(jid, status="error", message=str(e)[:400], error=tb[-4000:])

    EXEC.submit(runner)
    return jid


@app.get("/api/jobs/{jid}")
def job_status(jid: str):
    with JOBS_LOCK:
        j = JOBS.get(jid)
        if not j:
            raise HTTPException(404, "작업을 찾을 수 없습니다.")
        return JSONResponse(j)


@app.get("/api/jobs")
def jobs_list():
    with JOBS_LOCK:
        return list(JOBS.values())[-20:]


# ── 기본 정보 ─────────────────────────────────────────────────────────────
@app.get("/api/health")
def health():
    info = {"ok": True, "version": __version__, "ffmpeg": "없음", "encoder": "확인 중",
            "python": os.sys.version.split()[0]}
    try:
        info["ffmpeg"] = ffmpeg_version()
        info["encoder"] = encoder_info()["label"]
    except FFmpegMissing as e:
        info["ok"] = False
        info["error"] = str(e)
    info["projects"] = len(list_projects())
    return info


@app.get("/api/meta")
def meta():
    return {
        "app": "세월의 사연극장",
        "version": __version__,
        "genres": [{"key": k, **v} for k, v in GENRES.items()],
        "presets": [{"key": k, **v} for k, v in FORMAT_PRESETS.items()],
        "voice_modes": VOICE_MODES,
        "story_tones": STORY_TONES,
        "tts_engines": TTS_ENGINES,
        "openai_tts_models": OPENAI_TTS_MODELS,
        "script_engines": SCRIPT_ENGINES,
        "openai_script_models": OPENAI_SCRIPT_MODELS,
        "subtitle_sizes": {k: {"px": v[0], "label": v[1]} for k, v in SUBTITLE_SIZES.items()},
        "avatar_kinds": AVATAR_KINDS,
        "avatar_genders": AVATAR_GENDERS,
        "avatar_size": AVATAR_SIZE_PX,
        "live_badge_default": LIVE_BADGE_DEFAULT,
        "live_badge_period": LIVE_BADGE_PERIOD,
        "avatar_motion": {"cycle": AVATAR_MOTION_CYCLE, "seconds": AVATAR_MOTION_SECONDS},
        "config": public_config(),
        "encoder": encoder_info(),
        "defaults": {
            "like_voice_text": LIKE_VOICE_TEXT,
            "like_voice_short": LIKE_VOICE_SHORT,
            "cta_text": CTA_TEXT,
            "cta_short": CTA_SHORT,
        },
        "studio_steps": [
            {"n": 1, "key": "script", "label": "대본 설계·검토", "icon": "✍️"},
            {"n": 2, "key": "media", "label": "이미지·음성 검토", "icon": "🎧"},
            {"n": 3, "key": "render", "label": "영상 렌더링", "icon": "🎬"},
            {"n": 4, "key": "final", "label": "최종 확인·업로드", "icon": "🚀"},
        ],
        "voice_standard": {
            "speed": NARRATION_SPEED, "tolerance": SPEED_TOLERANCE,
            "breath_gap": BREATH_GAP_SECONDS, "min": BREATH_GAP_MIN, "max": BREATH_GAP_MAX,
            "openai_voices": list(OPENAI_TTS_MODELS.keys()),
        },
    }


@app.get("/api/config")
def get_config():
    return public_config()


class ConfigIn(BaseModel):
    gemini_api_key: str | None = None
    text_model: str | None = None
    image_model: str | None = None
    encoder: str | None = None
    force_scale: float | None = None
    keep_segments: bool | None = None
    github_token: str | None = None
    github_repo: str | None = None
    tts_engine: str | None = None
    openai_api_key: str | None = None
    openai_tts_model: str | None = None
    openai_fallback_edge: bool | None = None
    script_engine: str | None = None
    openai_script_model: str | None = None


@app.post("/api/config")
def set_config(body: ConfigIn):
    patch = {k: v for k, v in body.model_dump().items() if v is not None}
    for k in ("gemini_api_key", "github_token", "openai_api_key"):
        if k in patch:
            patch[k] = (patch[k] or "").strip()
    if "github_repo" in patch:
        patch["github_repo"] = (patch["github_repo"] or "").strip() or DEFAULT_GITHUB_REPO
    if "tts_engine" in patch:
        engine = str(patch["tts_engine"] or "").strip().lower()
        patch["tts_engine"] = engine if engine in TTS_ENGINES else "edge"
    if "openai_tts_model" in patch:
        model = str(patch["openai_tts_model"] or "").strip()
        patch["openai_tts_model"] = model if model in OPENAI_TTS_MODELS else "gpt-4o-mini-tts"
    if "script_engine" in patch:
        sengine = str(patch["script_engine"] or "").strip().lower()
        patch["script_engine"] = sengine if sengine in SCRIPT_ENGINES else "auto"
    if "openai_script_model" in patch:
        smodel = str(patch["openai_script_model"] or "").strip()
        patch["openai_script_model"] = smodel if smodel in OPENAI_SCRIPT_MODELS else "gpt-4o-mini"
    save_config(patch)
    return public_config()


class ConfigTestIn(BaseModel):
    engine: str | None = None          # gemini(기본) | openai_tts


@app.post("/api/config/test")
def test_config(body: ConfigTestIn | None = None):
    target = str((body.engine if body else "") or "gemini").strip().lower()
    cfg = load_config()
    if target in ("openai_script", "script_openai", "openai_text"):
        from .openai_script import test_connection
        return test_connection(cfg)
    if target in ("openai_tts", "openai", "tts"):
        return test_openai_tts(cfg)
    if not (cfg.get("gemini_api_key") or "").strip():
        return {"ok": False, "error": "API 키가 저장되어 있지 않습니다."}
    try:
        from .gemini_script import call_gemini
        text = call_gemini(cfg, "한국어로 '연결 성공'이라고만 답해 주세요.", temperature=0,
                           response_json=False, max_output_tokens=20)
        return {"ok": True, "message": (text or "").strip()[:40] or "연결 성공"}
    except Exception as e:
        return {"ok": False, "error": str(e)[:300]}


@app.get("/api/tts/preview")
def tts_preview():
    """[연결 테스트]에서 만든 짧은 미리듣기 mp3."""
    path = preview_path()
    if not path.exists() or path.stat().st_size < 500:
        raise HTTPException(404, "미리듣기 음성이 없습니다. [연결 테스트]를 먼저 눌러 주세요.")
    return FileResponse(str(path), media_type="audio/mpeg",
                        headers={"Cache-Control": "no-cache, no-store, must-revalidate"})


# ── 프로젝트 ──────────────────────────────────────────────────────────────
@app.get("/api/projects")
def projects():
    return list_projects()


class CreateIn(BaseModel):
    preset: str = "pilot5"
    genre: str = "tear_family"
    topic: str = ""
    hook15: bool = True
    sequel: bool = True
    teaser_mode: str = "auto_sequel"
    teaser_text: str = ""
    voice_mode: str = "multi"
    tone: str = "warm"
    rate: int = 0
    avatar: bool = True
    avatar_kind: str = "auto"
    live_badge: bool = True
    subtitle_size: str = "senior"
    image_mode: str = "B"
    like_banner: bool = True
    like_voice: bool = True
    like_voice_text: str = ""
    outro_cta: bool = True
    cta_text: str = ""
    bgm: bool = True
    sfx: bool = True
    end_screen: bool = True
    sleep_rain: bool = False
    auto_assemble: bool = False
    youtube_privacy: str = "private"
    youtube_publish_at: str = ""
    youtube_title_index: int = 0
    auto_upload: bool = False


@app.post("/api/projects")
def create(body: CreateIn):
    payload = body.model_dump()

    def work(progress):
        p = create_project(payload, lambda q, m: progress(min(24, int(q * 0.24)), m, 1))
        if payload.get("auto_assemble") and payload.get("image_mode") == "A":
            assemble_project(p["id"], lambda q, m, step=None: progress(24 + int(q * 0.76), m, step))
            return {"project": load(p["id"]), "assembled": True}
        return {"project": p}

    jid = start_job("create", work)
    return {"job": jid}


@app.get("/api/projects/{pid}")
def get_project(pid: str):
    _check_pid(pid)
    try:
        p = load(pid)
    except FileNotFoundError:
        raise HTTPException(404, "프로젝트를 찾을 수 없습니다.")
    p["image_files"] = _image_files(pid)
    p["missing_images"] = missing_images(p)
    p["voice_report"] = voice_report(p)
    p["script_engine"] = p.get("script_engine") or p.get("source") or ""
    p["script_engine_tag"] = engine_tag(p["script_engine"])
    p["script_dirty"] = bool(p.get("script_dirty"))
    return p


@app.patch("/api/projects/{pid}")
def patch_project(pid: str, body: dict):
    _check_pid(pid)
    p = load(pid)
    allowed = {"thumbnail", "upload", "options", "sequel_teaser", "title"}
    for k, v in body.items():
        if k in allowed:
            if k == "options":
                p.setdefault("options", {}).update(v or {})
            else:
                p[k] = v
    save(p)
    write_upload_copy(p)
    return {"ok": True}


# ── 대본 전문 읽기 · 직접 수정 · 재제작 (v1.2.5) ──────────────────────
@app.get("/api/projects/{pid}/script")
def get_project_script(pid: str):
    """[📖 대본 전체 읽기] — 장별 묶음 + 통째로 복사할 평문."""
    _check_pid(pid)
    return read_script_view(_load_or_404(pid))


class ScriptIn(BaseModel):
    scenes: list[dict]
    title: str | None = None


@app.post("/api/projects/{pid}/script")
def save_project_script(pid: str, body: ScriptIn):
    """화면에서 고친 대본을 저장한다 (script.json · project.json · 요청서·카피까지)."""
    _check_pid(pid)
    p = _load_or_404(pid)
    try:
        return save_edited_script(p, body.scenes, body.title)
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.post("/api/projects/{pid}/script/rebuild")
def rebuild_project_script(pid: str):
    """[🎬 수정한 대본으로 성우·영상 다시 만들기] — 성우부터 영상·썸네일까지 재제작."""
    _check_pid(pid)
    p = _load_or_404(pid)
    if not (p.get("scenes") or []):
        raise HTTPException(400, "이 사연에는 대본이 없습니다.")
    missing = missing_images(p)
    if missing:
        raise HTTPException(400, f"이미지 {len(missing)}장이 아직 없습니다: {', '.join(missing[:6])}")

    def work(progress):
        return rebuild_from_script(pid, progress)

    return {"job": start_job("rescript", work, project_id=pid)}


# ── v2.0.0 4단계 스튜디오 API ────────────────────────────────────────────
class SuggestIn(BaseModel):
    genre: str = "tear_family"
    preset: str = "short50"
    count: int = 5


@app.post("/api/scenario/suggest")
def scenario_suggest(body: SuggestIn | None = None):
    """1단계 [✨ 시나리오 추천받기] — AI가 주제·훅 3~5개를 추천한다."""
    body = body or SuggestIn()
    settings_in = {"genre": body.genre or "tear_family", "preset": body.preset or "short50"}
    try:
        return suggest_ideas(settings_in, load_config(), count=body.count)
    except Exception as e:
        return {"ok": False, "ideas": [], "error": str(e)[:300]}


def _project_brief(p: dict) -> dict:
    """스튜디오 화면(4단계)이 쓰는 요약 — 상세 JSON 전체를 보내지 않는다."""
    plan = p.get("image_plan") or []
    have = _image_files(p["id"])
    return {
        "id": p.get("id"), "title": p.get("title"), "status": p.get("status") or {},
        "format": p.get("format") or {}, "options": p.get("options") or {},
        "outputs": p.get("outputs") or {}, "duration": p.get("duration"),
        "script_rev": p.get("script_rev", 0), "script_dirty": bool(p.get("script_dirty")),
        "script_engine": p.get("script_engine") or p.get("source") or "",
        "script_editor": p.get("script_editor") or p.get("script_engine") or p.get("source") or "",
        "script_engine_tag": engine_tag(p.get("script_engine") or p.get("source") or ""),
        "warnings": list(p.get("warnings") or [])[-6:],
        "publish": p.get("publish") or {"decision": "undecided"},
        "youtube": p.get("youtube") or {},
        "images": {"total": len(plan), "found": len([f for f in have if f in {e.get('file') for e in plan}]),
                   "files": have, "missing": missing_images(p)},
        "scenes": len(p.get("scenes") or []),
        "receive_log": (p.get("receive_log") or [])[-1:],
    }


@app.get("/api/projects/{pid}/studio")
def project_studio(pid: str):
    """4단계 위자드가 한 번에 읽는 상태 묶음(대본 · 이미지 · 성우 · 수신 · 업로드 카피)."""
    _check_pid(pid)
    p = _load_or_404(pid)
    plan = project_voice_plan(p)
    before = json.dumps(p.get("upload_pack") or {}, ensure_ascii=False, sort_keys=True)
    pack = build_upload_pack(p)
    after = json.dumps(pack, ensure_ascii=False, sort_keys=True)
    if before != after:          # 화면이 4초마다 부르므로 바뀔 때만 저장(디스크 낭비 방지)
        try:
            save(p)
        except Exception:
            pass
    return {
        "ok": True,
        "project": _project_brief(p),
        "pack": pack,
        "voices": {"plan": plan, "report": voice_report(p),
                   "violations": separation_violations(plan),
                   "speeds": speed_values(plan),
                   "speed_uniform": (max(speed_values(plan)) - min(speed_values(plan))) <= 0.0001,
                   "breath_gap": breath_gap()},
        "receive": ib.project_progress(pid),
    }


@app.get("/api/projects/{pid}/voices")
def project_voices(pid: str):
    """해설/인물 목소리 분리·속도 균일 검사 결과(2단계 화면·테스트용)."""
    _check_pid(pid)
    p = _load_or_404(pid)
    plan = project_voice_plan(p)
    speeds = speed_values(plan)
    return {"ok": True, "report": voice_report(p), "plan": plan,
            "violations": separation_violations(plan),
            "separated": not separation_violations(plan),
            "speeds": speeds,
            "speed_uniform": (max(speeds) - min(speeds)) <= 0.0001,
            "breath_gap": breath_gap()}


@app.post("/api/projects/{pid}/tts")
def project_tts(pid: str):
    """2단계 [성우 음성 만들기] — 대본 전체를 성우(목소리 표)로 녹음한다."""
    _check_pid(pid)
    p = _load_or_404(pid)
    if not (p.get("scenes") or []):
        raise HTTPException(400, "이 사연에는 대본이 없습니다.")

    def work(progress):
        return _tts_stage(pid, progress)

    return {"job": start_job("tts", work, project_id=pid)}


def _tts_stage(pid: str, progress, base_pct: int = 0, span: int = 100) -> dict:
    p = load(pid)
    set_status(p, "tts", 30, "성우 녹음 준비 중…")
    plan = build_voice_plan(p)
    save(p)
    progress(base_pct + int(span * 0.03), f"성우 {len(plan.get('speakers') or {})}명 배정…", 3)

    def on_line(i, n):
        progress(base_pct + int(span * (0.05 + 0.9 * i / max(1, n))), f"성우 녹음 {i}/{n}", 3)

    durations = synthesize_sync(p, progress=on_line)
    items = build_timeline(p, durations)
    save(p)
    write_voice_meta(p)
    set_status(p, "tts", max(30, base_pct + span),
               f"성우 녹음 완료 — 장면 {len(durations)}개 · 약 {round(p.get('duration') or 0)}초")
    progress(base_pct + span, "성우 녹음 완료", 3)
    return {"project_id": pid, "lines": len(durations),
            "seconds": round(sum(v for v in durations.values() if v), 1),
            "duration": p.get("duration"), "plan": plan, "timeline": len(items)}


@app.get("/api/projects/{pid}/tts/{name}")
def project_tts_audio(pid: str, name: str):
    """2단계 미리듣기 — 장면 음성(`s03`)과 재녹음 파일(`preview/s03`)을 내보낸다."""
    _check_pid(pid)
    base = re.sub(r"\.mp3$", "", (name or "").strip())
    if not re.fullmatch(r"[A-Za-z0-9_\-]{1,40}", base):
        raise HTTPException(400, "잘못된 음성 이름입니다.")
    candidates = [preview_dir(pid) / f"{base}.mp3", clip_path(pid, base)]
    for path in candidates:
        if path.exists() and path.stat().st_size > 500:
            return FileResponse(str(path), media_type="audio/mpeg",
                                headers={"Cache-Control": "no-cache, max-age=0, must-revalidate"})
    raise HTTPException(404, "아직 음성이 없습니다. [성우 음성 만들기]를 먼저 눌러 주세요.")


class TtsPreviewIn(BaseModel):
    scene_id: str
    text: str | None = None
    speaker: str | None = None
    emotion: str | None = None
    save: bool = False       # 고친 대사를 대본에 저장할지
    commit: bool = False     # 이 음성을 본 렌더에 쓸 audio_clips 로 고정할지


@app.post("/api/projects/{pid}/tts/preview")
def project_tts_preview(pid: str, body: TtsPreviewIn):
    """2단계 개별 대사 미리듣기·재녹음 (대사·화자를 바꿔 바로 들어볼 수 있다)."""
    _check_pid(pid)
    p = _load_or_404(pid)
    scenes = [dict(s) for s in (p.get("scenes") or [])]
    target = next((s for s in scenes if str(s.get("id")) == str(body.scene_id)), None)
    if not target:
        raise HTTPException(404, "그 장면을 찾을 수 없습니다.")
    changed = False
    if body.text is not None and str(body.text).strip() != str(target.get("text") or "").strip():
        target["text"] = str(body.text).strip()[:600]
        changed = True
    if body.speaker and str(body.speaker) != str(target.get("speaker")):
        target["speaker"] = str(body.speaker)
        changed = True
    if body.emotion and str(body.emotion) != str(target.get("emotion")):
        target["emotion"] = str(body.emotion)
        changed = True
    try:
        info = synthesize_line_preview(p, target, text=target.get("text") or "",
                                       name=f"{target.get('id')}")
    except Exception as e:
        raise HTTPException(400, f"음성을 만들지 못했습니다: {str(e)[:200]}")
    saved = False
    if body.save and changed:
        rows = [{"id": s.get("id"), "text": s.get("text"), "speaker": s.get("speaker"),
                 "emotion": s.get("emotion")} for s in scenes]
        try:
            save_edited_script(p, rows)
            saved = True
        except ValueError as e:
            raise HTTPException(400, str(e))
    if body.commit:
        src = preview_dir(pid) / f"{target.get('id')}.mp3"
        dst = clip_path(pid, str(target.get("id")))
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(src.read_bytes())
        p = _load_or_404(pid)
        try:
            from .ffmpeg_util import duration as _dur
            all_d = {}
            for sc in p.get("scenes") or []:
                f = clip_path(pid, str(sc.get("id")))
                if f.exists():
                    try:
                        all_d[sc["id"]] = _dur(f)
                    except Exception:
                        all_d[sc["id"]] = 0.0
            build_timeline(p, all_d)
        except Exception:
            pass
        save(p)
    return {"ok": True, "scene_id": target.get("id"),
            "url": f"/api/projects/{pid}/tts/{target.get('id')}?v={int(uuid.uuid4().int % 100000)}",
            "seconds": info.get("seconds"), "voice": info.get("voice"),
            "label": info.get("label"), "speed": info.get("speed"),
            "engine": info.get("engine"), "changed": changed, "saved": saved,
            "committed": bool(body.commit), "text": target.get("text")}


class RenderIn(BaseModel):
    remix: bool = True          # BGM·자막을 새로 만들지


@app.post("/api/projects/{pid}/render")
def project_render(pid: str, body: RenderIn | None = None):
    """3단계 [영상 렌더링] — 성우/BGM/자막/인코딩 단계별 진행률과 함께 final.mp4 를 만든다."""
    _check_pid(pid)
    p = _load_or_404(pid)
    missing = missing_images(p)
    if missing:
        raise HTTPException(400, f"이미지 {len(missing)}장이 아직 없습니다: {', '.join(missing[:6])}")
    if not (p.get("scenes") or []):
        raise HTTPException(400, "이 사연에는 대본이 없습니다.")

    def work(progress):
        return render_project(pid, progress)

    return {"job": start_job("render", work, project_id=pid)}


def render_project(pid: str, progress) -> dict:
    """성우 → 타임라인 → BGM·효과음 → 자막 → 인코딩 → 썸네일·카피.

    각 단계 진행률을 `stages` 로 함께 보내 3단계 화면이 네 개 막대로 보여 준다.
    """
    stages = {"성우": 0, "BGM": 0, "자막": 0, "인코딩": 0}

    def report(name: str, pct: int, msg: str, total: int, step: int = 5) -> None:
        stages[name] = max(stages.get(name, 0), max(0, min(100, int(pct))))
        progress(max(0, min(100, int(total))), msg, step, stages=dict(stages))

    p = load(pid)
    # 1) 성우 — 이미 만든 음성은 그대로 쓰고 빠진 것만 녹음한다
    report("성우", 2, "성우 음성 확인 중…", 2)
    clips = [clip_path(pid, str(s.get("id"))) for s in p.get("scenes") or []]
    missing_lines = [c for c in clips if not (c.exists() and c.stat().st_size > 500)]
    if missing_lines:
        report("성우", 10, f"성우 {len(missing_lines)}개 대사 새로 녹음…", 6)
        _tts_stage(pid, lambda pct, msg, step=None, **kw: report(
            "성우", 10 + int(0.85 * (pct if isinstance(pct, int) else 0)), msg, 6 + int(pct * 0.09), 3),
            base_pct=0, span=100)
        p = load(pid)
    report("성우", 100, "성우 음성 준비 완료", 16)

    from .ffmpeg_util import duration as _dur
    from .project import est_seconds
    durations = {}
    for sc in p.get("scenes") or []:
        f = clip_path(pid, str(sc.get("id")))
        sec = 0.0
        try:
            sec = _dur(f) if f.exists() else 0.0
        except Exception:
            sec = 0.0
        durations[sc["id"]] = sec if sec and sec > 0.05 else est_seconds(str(sc.get("text") or ""))
    items = build_timeline(p, durations)
    save(p)

    # 2) BGM · 효과음
    report("BGM", 5, "감정별 BGM·효과음 믹싱…", 20)
    mix = build_mix(p, items, progress=lambda q, m: report("BGM", 5 + int(0.95 * q), m, 20 + int(q * 0.14)))
    p.setdefault("outputs", {})["audio"] = str(mix.relative_to(project_dir(pid)))
    save(p)
    report("BGM", 100, "BGM·효과음 완료", 34)

    # 3) 자막 (SRT 는 화면·업로드용, ASS 는 인코딩 단계에서 다시 만든다)
    report("자막", 20, "자막 파일 만드는 중…", 36)
    try:
        from .project import scale_for
        from .subtitles import write_ass, write_srt
        w, h = scale_for(p)
        write_srt(p, items, project_dir(pid) / "output" / "subtitles.srt")
        (project_dir(pid) / "render").mkdir(parents=True, exist_ok=True)
        write_ass(p, items, project_dir(pid) / "render" / "subs.ass", w, h)
        p["outputs"]["srt"] = "output/subtitles.srt"
        save(p)
    except Exception as e:
        p.setdefault("warnings", []).append(f"자막 파일 생성 경고: {str(e)[:120]}")
        save(p)
    report("자막", 100, "자막 완료", 42)

    # 4) 인코딩
    report("인코딩", 2, "영상 조립 중…", 44)
    video = render_video(p, items, mix, progress=lambda q, m: report(
        "인코딩", 2 + int(0.98 * q), m, 44 + int(q * 0.5)))
    p["outputs"]["video"] = str(video.relative_to(project_dir(pid)))
    save(p)
    report("인코딩", 100, "영상 인코딩 완료", 94)

    # 5) 썸네일·업로드 카피
    progress(95, "썸네일 2종 만드는 중…", 6, stages=dict(stages))
    try:
        th = render_thumbnails(p, progress=lambda q, m: progress(95 + int(3 * q / 100), m, 6,
                                                                 stages=dict(stages)))
        p["outputs"]["thumb_style1"] = str(Path(th["style1"]).relative_to(project_dir(pid)))
        p["outputs"]["thumb_style2"] = str(Path(th["style2"]).relative_to(project_dir(pid)))
    except Exception as e:
        p.setdefault("warnings", []).append(f"썸네일 생성 실패: {str(e)[:140]}")
    save(p)
    write_image_request(p)
    write_upload_copy(p)
    set_status(p, "done", 99, "영상·썸네일·업로드 카피가 준비되었습니다. 4단계에서 감수하세요.")
    progress(100, "완성 — 4단계에서 확인하세요", 6, stages=dict(stages))
    return {"project_id": pid, "video": p["outputs"].get("video"),
            "duration": p.get("duration"), "stages": stages,
            "thumb1": p["outputs"].get("thumb_style1"),
            "thumb2": p["outputs"].get("thumb_style2")}


class PublishIn(BaseModel):
    decision: str = "hold"          # now(지금 공개) | schedule(예약) | hold(보류·파일만)
    privacy: str = ""               # now 일 때 public/unlisted/private
    publish_at: str = ""            # schedule 일 때 YYYY-MM-DDTHH:MM
    title_index: int = 0


@app.post("/api/projects/{pid}/publish")
def project_publish(pid: str, body: PublishIn):
    """4단계 최종 결정 — 지금 업로드 / 예약 업로드 / 보류하고 파일만 저장."""
    _check_pid(pid)
    p = _load_or_404(pid)
    decision = (body.decision or "hold").strip().lower()
    if decision not in ("now", "schedule", "hold"):
        decision = "hold"
    privacy = (body.privacy or ("public" if decision == "now" else "private")).strip()
    if privacy not in ("public", "unlisted", "private"):
        privacy = "private"
    publish_at = (body.publish_at or "").strip() if decision == "schedule" else ""
    p["publish"] = {"decision": decision, "privacy": privacy if decision != "hold" else "",
                    "publish_at": publish_at, "title_index": int(body.title_index or 0),
                    "updated": now()}
    p.setdefault("options", {}).update({"youtube_privacy": privacy,
                                        "youtube_publish_at": publish_at,
                                        "youtube_title_index": int(body.title_index or 0)})
    save(p)
    files = {"video": f"/api/projects/{pid}/file/video",
             "thumb1": f"/api/projects/{pid}/file/thumb1",
             "thumb2": f"/api/projects/{pid}/file/thumb2",
             "copy": f"/api/projects/{pid}/file/copy"}
    if decision == "hold":
        return {"ok": True, "decision": "hold", "files": files,
                "message": "업로드하지 않고 파일만 저장했습니다. 나중에 4단계에서 다시 결정할 수 있습니다."}
    if not yt.has_client():
        return {"ok": False, "decision": decision, "files": files,
                "error": "유튜브 채널이 아직 연결되지 않았습니다. [⚙️ 설정] → 유튜브 연동을 먼저 해 주세요."}

    def work(progress):
        return yt.upload_project(pid, int(body.title_index or 0), privacy, publish_at, progress)

    return {"ok": True, "decision": decision, "privacy": privacy, "publish_at": publish_at,
            "job": start_job("youtube_upload", work, project_id=pid),
            "message": ("예약 업로드를 시작합니다." if decision == "schedule" else "지금 업로드를 시작합니다.")}


@app.post("/api/projects/{pid}/assemble")
def assemble(pid: str):
    _check_pid(pid)
    p = load(pid)
    missing = missing_images(p)
    if missing and p["options"].get("image_mode") == "B":
        raise HTTPException(400, f"이미지 {len(missing)}장이 아직 없습니다: {', '.join(missing[:6])}")

    def work(progress):
        return assemble_project(pid, progress)

    jid = start_job("assemble", work, project_id=pid)
    return {"job": jid}


def assemble_project(pid: str, progress) -> dict:
    p = load(pid)
    set_status(p, "images", 2, "이미지 준비 중…")
    progress(2, "이미지 준비 중…", 2)
    if p["options"].get("image_mode") == "A":
        res = generate_images(p, progress=lambda q, m: progress(2 + int(q * 0.2), m, 2))
        save(p)
        if res.get("placeholder"):
            p.setdefault("warnings", []).append("일부 이미지를 임시 이미지로 대체했습니다.")
    missing = missing_images(p)
    if missing:
        raise RuntimeError("이미지가 부족합니다: " + ", ".join(missing[:8]))

    p = _render_stage(pid, p, progress)

    if p["options"].get("auto_upload") and yt.has_client():
        try:
            set_status(p, "upload", 99, "유튜브 자동 업로드 중…")
            progress(99, "유튜브 자동 업로드 중…", 6)
            res = yt.upload_project(pid,
                                    title_index=p["options"].get("youtube_title_index", 0),
                                    privacy=p["options"].get("youtube_privacy", "private"),
                                    publish_at=p["options"].get("youtube_publish_at"),
                                    progress=lambda q, m: progress(99, m, 6))
            p = load(pid)
            p["warnings"] = list(p.get("warnings", []))
        except Exception as e:
            p = load(pid)
            p.setdefault("warnings", []).append(f"유튜브 자동 업로드 실패: {str(e)[:160]}")
            save(p)

    set_status(p, "done", 100, "완성! 영상·썸네일·업로드 카피가 준비되었습니다.")
    progress(100, "완성", 6)
    return {"project_id": pid, "video": p["outputs"]["video"], "duration": p.get("duration")}


def _render_stage(pid: str, p: dict, progress) -> dict:
    """성우 녹음 → 타임라인 → BGM·효과음 → 영상 → 썸네일·카피.

    대본을 고친 뒤 [🎬 수정한 대본으로 성우·영상 다시 만들기]도 같은 단계를 탄다.
    음성은 대사 글자로 캐시되므로, 고친 장면만 다시 만들고 나머지는 그대로 쓴다.
    """
    set_status(p, "tts", 22, "성우 녹음 중…")
    progress(22, "성우 음성 만드는 중…", 3)
    durations = synthesize_sync(p, progress=lambda i, n: progress(22 + int(26 * i / max(1, n)),
                                                                 f"성우 녹음 {i}/{n}", 3))
    set_status(p, "timeline", 48, "대사 길이에 맞춰 초 단위 타임라인 구성…")
    progress(48, "초 단위 타임라인 구성…", 3)
    items = build_timeline(p, durations)
    save(p)

    set_status(p, "audio", 52, "BGM·효과음 믹싱…")
    progress(52, "감정별 BGM·효과음 믹싱…", 4)
    mix = build_mix(p, items, progress=lambda q, m: progress(52 + int(14 * q / 100), m, 4))
    p.setdefault("outputs", {})["audio"] = str(mix.relative_to(project_dir(pid)))
    save(p)

    set_status(p, "render", 68, "영상 조립 중… (영상 길이에 따라 오래 걸립니다)")
    progress(68, "영상 조립 중…", 5)
    video = render_video(p, items, mix, progress=lambda q, m: progress(68 + int(26 * q / 100), m, 5))
    p["outputs"]["video"] = str(video.relative_to(project_dir(pid)))
    save(p)

    set_status(p, "thumb", 95, "썸네일 2종 만드는 중…")
    th = render_thumbnails(p, progress=lambda q, m: progress(95 + int(3 * q / 100), m, 6))
    p["outputs"]["thumb_style1"] = str(Path(th["style1"]).relative_to(project_dir(pid)))
    p["outputs"]["thumb_style2"] = str(Path(th["style2"]).relative_to(project_dir(pid)))
    p["outputs"]["srt"] = "output/subtitles.srt"
    save(p)
    write_image_request(p)
    write_upload_copy(p)
    return p


def rebuild_from_script(pid: str, progress) -> dict:
    """수정한 대본으로 성우·타임라인·영상·썸네일을 다시 만든다(이미지는 그대로)."""
    p = load(pid)
    missing = missing_images(p)
    if missing:
        raise RuntimeError(f"이미지 {len(missing)}장이 아직 없습니다: " + ", ".join(missing[:6]))
    progress(6, f"수정한 대본({p.get('script_rev', 0)}차)으로 다시 만드는 중…", 1)
    p = _render_stage(pid, p, progress)
    # 영상이 실제로 새로 만들어진 뒤에만 '수정본 반영됨'으로 바꾼다(중간에 실패하면 표시가 남는다)
    p["script_dirty"] = False
    p["script_rebuilt_at"] = now()
    save(p)
    set_status(p, "done", 100, "수정한 대본으로 영상을 다시 만들었습니다.")
    progress(100, "완성", 6)
    return {"project_id": pid, "video": p["outputs"].get("video"),
            "duration": p.get("duration"), "script_rev": p.get("script_rev", 0),
            "rebuilt": True}


@app.post("/api/projects/{pid}/images/generate")
def project_images_generate(pid: str):
    """2단계 — 모드 A(완전자동)의 [이미지 자동 생성]. Gemini 로 빠진 컷을 만든다."""
    _check_pid(pid)
    p = _load_or_404(pid)
    missing = missing_images(p)
    if not missing:
        return {"ok": True, "generated": 0, "message": "이미지가 이미 모두 준비되어 있습니다.", "missing": []}
    cfg = load_config()
    if not (cfg.get("gemini_api_key") or "").strip():
        raise HTTPException(400, "Gemini API 키가 없어 자동 이미지 생성이 안 됩니다. "
                                "[⚙️ 설정]에 키를 넣거나, 케빈에게 이미지를 요청해 주세요.")

    def work(progress):
        progress(3, f"장면 이미지 {len(missing)}장 생성 준비…", 2)
        res = generate_images(p, progress=lambda q, m: progress(3 + int(q * 0.95), m, 2))
        save(p)
        left = missing_images(p)
        progress(100, f"이미지 생성 완료 — 남은 {len(left)}장", 2)
        return {"project_id": pid, "generated": res.get("generated", 0),
                "failed": res.get("failed", 0), "missing": left,
                "message": f"{res.get('generated', 0)}장을 만들었습니다. 남은 {len(left)}장."}

    return {"job": start_job("images", work, project_id=pid)}


@app.post("/api/projects/{pid}/images")
async def upload_images(pid: str, files: list[UploadFile] = File(...)):
    _check_pid(pid)
    p = load(pid)
    pdir = project_dir(pid) / "images"
    pdir.mkdir(parents=True, exist_ok=True)
    saved, skipped = [], []
    plan_files = {e["file"] for e in p.get("image_plan", [])}
    for f in files:
        raw = await f.read()
        name = Path(f.filename or "").name
        if name.lower().endswith(".zip"):
            with zipfile.ZipFile(io.BytesIO(raw)) as z:
                for info in z.infolist():
                    base = Path(info.filename).name
                    if base.lower().endswith((".png", ".jpg", ".jpeg", ".webp")):
                        target = _match_name(base, plan_files)
                        if target:
                            (pdir / target).write_bytes(z.read(info))
                            saved.append(target)
                        else:
                            skipped.append(base)
            continue
        if not name.lower().endswith((".png", ".jpg", ".jpeg", ".webp")):
            skipped.append(name)
            continue
        target = _match_name(name, plan_files)
        if not target:
            skipped.append(name)
            continue
        (pdir / target).write_bytes(raw)
        saved.append(target)
    missing = missing_images(p)
    p["warnings"] = [w for w in p.get("warnings", []) if "이미지" not in w]
    save(p)
    return {"saved": sorted(set(saved)), "skipped": skipped, "missing": missing}


def _match_name(name: str, plan_files: set[str]) -> str | None:
    from .project import match_plan_name
    return match_plan_name(name, plan_files)


@app.delete("/api/projects/{pid}/images/{name}")
def delete_image(pid: str, name: str):
    _check_pid(pid)
    if not re.match(r"^s\d{2}\.(png|jpg|jpeg)$", name):
        raise HTTPException(400, "잘못된 파일 이름입니다.")
    p = project_dir(pid) / "images" / name
    if p.exists():
        p.unlink()
    return {"ok": True}


class ThumbIn(BaseModel):
    style1: list[str] | None = None
    style2: list[str] | None = None


@app.post("/api/projects/{pid}/thumbnail")
def regen_thumbnail(pid: str, body: ThumbIn):
    _check_pid(pid)
    p = load(pid)
    th = p.setdefault("thumbnail", {})
    if body.style1 is not None:
        th["style1"] = [s for s in body.style1 if s.strip()][:2]
    if body.style2 is not None:
        th["style2"] = [s for s in body.style2 if s.strip()][:5]
    save(p)
    try:
        res = render_thumbnails(p)
    except Exception as e:
        raise HTTPException(500, f"썸네일 생성 실패: {e}")
    p["outputs"]["thumb_style1"] = str(Path(res["style1"]).relative_to(project_dir(pid)))
    p["outputs"]["thumb_style2"] = str(Path(res["style2"]).relative_to(project_dir(pid)))
    save(p)
    write_upload_copy(p)
    return {"ok": True, "thumb1": f"/api/projects/{pid}/file/thumb1",
            "thumb2": f"/api/projects/{pid}/file/thumb2"}


@app.post("/api/projects/{pid}/open")
def open_folder(pid: str):
    _check_pid(pid)
    d = project_dir(pid)
    if not d.exists():
        raise HTTPException(404, "폴더가 없습니다.")
    import platform
    import subprocess
    try:
        if platform.system() == "Darwin":
            subprocess.Popen(["open", str(d)])
        elif platform.system() == "Windows":
            subprocess.Popen(["explorer", str(d)])
        else:
            subprocess.Popen(["xdg-open", str(d)])
    except Exception as e:
        return {"ok": False, "error": str(e)}
    return {"ok": True, "path": str(d)}


@app.get("/api/projects/{pid}/file/{kind}")
def project_file(pid: str, kind: str, v: int = 0):
    _check_pid(pid)
    p = load(pid)
    out = p.get("outputs") or {}
    mapping = {
        "video": out.get("video"),
        "thumb1": out.get("thumb_style1"),
        "thumb2": out.get("thumb_style2"),
        "srt": out.get("srt"),
        "audio": out.get("audio"),
        "request": "이미지_요청서.txt",
        "copy": "upload_copy.txt",
        "project": "project.json",
        "shorts": out.get("shorts"),
    }
    if kind == "video_preview":
        mapping[kind] = out.get("video")
    rel = mapping.get(kind)
    if not rel:
        raise HTTPException(404, "아직 만들어지지 않았습니다.")
    path = (project_dir(pid) / rel).resolve()
    if not str(path).startswith(str(project_dir(pid).resolve())) or not path.exists():
        raise HTTPException(404, "파일이 없습니다.")
    fname = path.name if kind != "video" else f"{p.get('title', '사연')}.mp4"
    return FileResponse(str(path), filename=fname)


@app.get("/api/projects/{pid}/images")
def project_images(pid: str):
    """장면 이미지 갤러리 — 컷 번호·파일·mtime·장면 설명·내레이션.

    프론트엔드는 이 signature 가 바뀜 때만 DOM 을 다시 그린다(깜박임 0).
    """
    _check_pid(pid)
    p = _load_or_404(pid)
    rows = _gallery(pid, p)
    return {"project_id": pid, "total": len(rows),
            "found": sum(1 for r in rows if r["found"]),
            "signature": _gallery_signature(rows), "images": rows}


def _load_or_404(pid: str) -> dict:
    try:
        return load(pid)
    except FileNotFoundError:
        raise HTTPException(404, "프로젝트를 찾을 수 없습니다.")


def _gallery(pid: str, p: dict) -> list[dict]:
    """image_plan 순서대로 컷 번호(1부터)를 붙인다. 계획에 없는 이미지는 뒤에 덧붙인다."""
    have = _image_files(pid)
    present = set(have)
    rows: list[dict] = []
    for idx, img in enumerate(p.get("image_plan") or [], start=1):
        file = str(img.get("file") or f"s{idx:02d}.png")
        rows.append(_gallery_row(pid, idx, file, file in present,
                                 img.get("caption") or "", img.get("prompt") or "",
                                 img.get("line") or ""))
    planned = {r["file"] for r in rows}
    for file in have:
        if file in planned:
            continue
        rows.append(_gallery_row(pid, len(rows) + 1, file, True, "", "", ""))
    return rows


def _gallery_row(pid: str, idx: int, file: str, found: bool,
                 caption: str, prompt: str, line: str) -> dict:
    path = project_dir(pid) / "images" / file
    mtime = 0
    if found and path.exists():
        try:
            mtime = int(path.stat().st_mtime_ns // 1_000_000)
        except Exception:
            mtime = 0
    else:
        found = False
    return {"idx": idx, "file": file, "found": found, "mtime": mtime,
            "url": f"/api/projects/{pid}/image/{idx}?v={mtime}",
            "caption": " ".join(str(caption).split())[:120],
            "prompt": " ".join(str(prompt).split())[:400],
            "line": " ".join(str(line).split())[:400]}


def _gallery_signature(rows: list[dict]) -> str:
    return "|".join(f"{r['idx']}:{int(r['found'])}:{r['mtime']}:{r['caption']}" for r in rows)


@app.get("/api/projects/{pid}/image/{name}")
def project_image(pid: str, name: str, request: Request, v: int = 0):
    """이미지 한 장 — `name` 은 컷 번호(1부터, 예: 3) 또는 파일명(s03.png).

    캐시방지 헤더(no-cache) + ETag(mtime) 를 붙여 새 이미지는 바로 보이고,
    바뀌지 않은 이미지는 304 로 다시 그리지 않는다.
    """
    _check_pid(pid)
    file: str | None = None
    if re.fullmatch(r"\d{1,4}", name or ""):
        idx = int(name)
        rows = _gallery(pid, _load_or_404(pid))
        row = next((r for r in rows if r["idx"] == idx), None)
        if not row or not row["found"]:
            raise HTTPException(404, "이미지가 없습니다.")
        file = row["file"]
    else:
        if not re.match(r"^[A-Za-z0-9._\-]+\.(png|jpg|jpeg|webp)$", name or ""):
            raise HTTPException(400, "잘못된 파일 이름입니다.")
        file = name
    path = project_dir(pid) / "images" / file
    if not path.exists():
        raise HTTPException(404, "이미지가 없습니다.")
    st = path.stat()
    etag = f'"{st.st_mtime_ns}-{st.st_size}"'
    headers = {"Cache-Control": "no-cache, max-age=0, must-revalidate",
               "ETag": etag, "Pragma": "no-cache"}
    if (request.headers.get("if-none-match") or "") == etag:
        return Response(status_code=304, headers=headers)
    return FileResponse(str(path), headers=headers)


class CompileIn(BaseModel):
    project_ids: list[str]
    title: str = ""


@app.post("/api/compile")
def compile_route(body: CompileIn):
    def work(progress):
        return compile_weekend(body.project_ids, body.title, progress)

    jid = start_job("weekend", work)
    return {"job": jid}


# ── 유튜브 자동 업로드 ───────────────────────────────────────────────────
@app.get("/api/youtube/status")
def youtube_status():
    return yt.status()


@app.post("/api/youtube/client-secret")
async def youtube_client_secret(file: UploadFile = File(...)):
    raw = await file.read()
    try:
        path = yt.save_client_secret(raw, file.filename or "client_secret.json")
    except Exception as e:
        raise HTTPException(400, str(e))
    return {"ok": True, "path": str(path), "status": yt.status()}


@app.post("/api/youtube/connect")
def youtube_connect():
    def work(progress):
        return yt.connect(progress)

    jid = start_job("youtube_connect", work)
    return {"job": jid}


@app.post("/api/youtube/disconnect")
def youtube_disconnect():
    return yt.disconnect()


class YtSettings(BaseModel):
    privacy: str = "private"
    publish_at: str = ""
    title_index: int = 0
    auto_upload: bool = False


@app.post("/api/youtube/settings")
def youtube_settings(body: YtSettings):
    return yt.save_defaults(body.privacy, body.publish_at, body.title_index, body.auto_upload)


class YtUploadIn(BaseModel):
    title_index: int = 0
    privacy: str = "private"
    publish_at: str = ""


@app.post("/api/projects/{pid}/youtube/upload")
def youtube_upload_project(pid: str, body: YtUploadIn):
    _check_pid(pid)
    def work(progress):
        return yt.upload_project(pid, body.title_index, body.privacy, body.publish_at, progress)

    jid = start_job("youtube_upload", work, project_id=pid)
    return {"job": jid}


# ── 채널 전략 분석 ───────────────────────────────────────────────────────
@app.get("/api/strategy")
def strategy_get():
    data = st.load_cached()
    return data or {"cards": [], "basis": "none", "note": "아직 분석하지 않았습니다."}


@app.post("/api/strategy/analyze")
def strategy_analyze():
    def work(progress):
        return st.analyze(progress)

    return {"job": start_job("strategy", work)}


class StrategyIn(BaseModel):
    action: dict
    image_mode: str = ""


@app.post("/api/strategy/execute")
def strategy_execute(body: StrategyIn):
    import re as _re
    action = dict(body.action or {})
    kind = str(action.get("type") or "create")

    def work(progress):
        if kind == "weekend":
            ids = [str(x) for x in (action.get("project_ids") or []) if _re.match(r"^[A-Za-z0-9\-_]+$", str(x))]
            return compile_weekend(ids, str(action.get("title") or ""),
                                   progress=lambda q, m: progress(q, m),
                                   auto_upload=bool(action.get("auto_upload")),
                                   privacy=str(action.get("privacy") or "private"),
                                   publish_at=str(action.get("publish_at") or ""))
        cfg = load_config()
        mode = body.image_mode or ("A" if (cfg.get("gemini_api_key") or "").strip() else "B")
        payload = {
            "preset": action.get("preset") or "full40",
            "genre": action.get("genre") or "tear_family",
            "topic": action.get("topic") or "",
            "hook15": True,
            "sequel": True,
            "teaser_mode": action.get("teaser_mode") or "auto_sequel",
            "voice_mode": "multi",
            "tone": action.get("tone") or "warm",
            "rate": 0,
            "avatar": True,
            "avatar_kind": "auto",
            "live_badge": True,
            "subtitle_size": "senior",
            "image_mode": mode,
            "like_banner": True,
            "like_voice": True,
            "outro_cta": True,
            "end_screen": True,
            "sleep_rain": False,
            "auto_assemble": bool(action.get("auto_assemble", True)) and mode == "A",
            "auto_upload": bool(action.get("auto_upload")),
            "youtube_privacy": str(action.get("privacy") or "private"),
            "youtube_publish_at": str(action.get("publish_at") or ""),
            "youtube_title_index": int(action.get("title_index") or 0),
        }
        p = create_project(payload, lambda q, m: progress(min(20, int(q * 0.2)), m, 1))
        if payload["auto_assemble"]:
            assemble_project(p["id"], lambda q, m, step=None: progress(20 + int(q * 0.8), m, step))
            p = load(p["id"])
        return {"project": p, "mode": mode}

    return {"job": start_job("strategy_execute", work)}


# ── 폰 접속 ─────────────────────────────────────────────────────────────
@app.get("/api/remote")
def remote_info(request: Request):
    port = request.url.port or 8765
    lan = net.lan_ip()
    ts = net.tailscale_ip()
    s = sch.load_settings()
    pin = s.get("pin", "")
    q = f"?pin={pin}" if pin else ""
    return {
        "lan_ip": lan, "port": port,
        "lan_url": f"http://{lan}:{port}/{q}",
        "tailscale_ip": ts,
        "tailscale_url": f"http://{ts}:{port}/{q}" if ts else "",
        "pin_set": bool(pin),
        "caffeinate": net.caffeinate_on(),
    }


@app.get("/api/remote/qr.png")
def remote_qr(url: str = ""):
    from fastapi.responses import FileResponse as FR
    p = net.qr_png(url or "http://localhost:8765")
    if not p or not p.exists():
        raise HTTPException(500, "QR 을 만들지 못했습니다.")
    return FR(str(p), media_type="image/png")


class PinIn(BaseModel):
    pin: str = ""


@app.post("/api/remote/pin")
def set_pin(body: PinIn):
    pin = "".join(ch for ch in (body.pin or "") if ch.isdigit())[:8]
    sch.save_settings({"pin": pin})
    return {"ok": True, "pin_set": bool(pin)}


class CafeIn(BaseModel):
    on: bool


@app.post("/api/remote/caffeinate")
def set_caffeinate(body: CafeIn):
    return net.caffeinate(body.on)


# ── 50초 쇼츠 추출 ───────────────────────────────────────────────────────
@app.post("/api/projects/{pid}/shorts")
def make_shorts(pid: str):
    _check_pid(pid)

    def work(progress):
        return extract_shorts(pid, progress)

    return {"job": start_job("shorts", work, project_id=pid)}


# ── 댓글 관리 ────────────────────────────────────────────────────────────
@app.get("/api/comments")
def comments_list(limit: int = 20):
    try:
        return {"items": cm.list_comments(limit)}
    except Exception as e:
        return {"items": [], "error": str(e)[:300]}


class DraftIn(BaseModel):
    text: str
    video_title: str = ""


@app.post("/api/comments/draft")
def comments_draft(body: DraftIn):
    return {"draft": cm.draft_reply(body.text, body.video_title)}


class ReplyIn(BaseModel):
    comment_id: str
    text: str


@app.post("/api/comments/reply")
def comments_reply(body: ReplyIn):
    try:
        return cm.post_reply(body.comment_id, body.text)
    except Exception as e:
        raise HTTPException(400, str(e)[:300])


# ── 자동 스케줄 ──────────────────────────────────────────────────────────
class ScheduleIn(BaseModel):
    auto_daily: bool | None = None
    daily_time: str | None = None
    daily_genre: str | None = None
    daily_preset: str | None = None
    daily_publish_time: str | None = None
    daily_image_mode: str | None = None
    daily_auto_upload: bool | None = None


@app.get("/api/schedule")
def schedule_get():
    s = sch.load_settings()
    st_ = sch.load_state()
    return {"settings": s, "state": st_, "worker": sch.worker_alive()}


@app.post("/api/schedule")
def schedule_set(body: ScheduleIn):
    patch = {k: v for k, v in body.model_dump().items() if v is not None}
    return sch.save_settings(patch)


@app.post("/api/schedule/run-now")
def schedule_run_now():
    def work(progress):
        return sch.run_daily_job("manual")

    return {"job": start_job("daily", work)}


# ── 깃허브 업데이트 · 이미지 인박스 ──────────────────────────────────────
INBOX = BASE / "assets_inbox"


@app.get("/api/github/status")
def github_status():
    cfg = load_config()
    tok = gh.token()
    return {"repo": gh.repo_name(), "has_token": bool(tok),
            "token_masked": public_config().get("github_token_masked", ""),
            "label": gh.LABEL, "revision_label": gh.KINDS["image_revision"]["label"],
            "revision_title_prefix": gh.title_prefix("image_revision"),
            "configured_repo": cfg.get("github_repo") or DEFAULT_GITHUB_REPO}


@app.post("/api/github/test")
def github_test():
    try:
        info = gh.check_token()
        return {"ok": True, **info, "message": f"{info.get('login') or ''} 로 연결됐습니다."}
    except Exception as e:
        return {"ok": False, "error": str(e)[:300]}


class GhRequestIn(BaseModel):
    mode: str = "auto"       # auto | url  (url = 토큰을 쓰지 않고 등록 화면을 연다)
    kind: str = "image_request"   # image_request | image_revision
    instruction: str = ""    # 이미지 수정 지시(수정 요청일 때)


@app.post("/api/projects/{pid}/github-request")
def github_request(pid: str, body: GhRequestIn | None = None):
    """이미지 요청/수정 요청을 깃허브 이슈로 보낸다 (토큰이 없으면 1클릭 등록 화면)."""
    _check_pid(pid)
    p = load(pid)
    body = body or GhRequestIn()
    mode = (body.mode or "auto").strip() or "auto"
    kind = gh.kind_of(body.kind)
    instruction = (body.instruction or "").strip()
    if kind == "image_revision" and not instruction:
        raise HTTPException(400, "수정 지시를 입력해 주세요. 예: '3번 컷 표정 더 놀라게'")
    p["image_files"] = _image_files(pid)      # 이슈 본문에 '받은 컷' 장수를 적기 위해

    req_path = project_dir(pid) / "이미지_요청서.txt"
    if not req_path.exists():
        write_image_request(p)
    text = req_path.read_text(encoding="utf-8") if req_path.exists() else ""
    plan = gh.build_request(p, text, kind=kind, instruction=instruction)
    tok = gh.token()

    if tok and mode != "url":
        try:
            issue = gh.create_issue(p, text, tok, kind=kind, instruction=instruction)
            _append_request_log(p, issue, "api", kind=kind, instruction=instruction)
            return {**plan, "mode": "api", "url": issue["url"], "number": issue.get("number"),
                    "message": _request_done_message(kind, issue.get("number"))}
        except Exception as e:
            plan["fallback_error"] = str(e)[:300]
            plan["copy_body"] = True
            _append_request_log(p, {"url": plan["url"]}, "url", error=str(e)[:200],
                                kind=kind, instruction=instruction)
            return {**plan, "mode": "url",
                    "message": "토큰으로 등록하지 못해 1클릭 등록 화면을 여는 방법으로 넘어갑니다."}

    _append_request_log(p, {"url": plan["url"]}, "url", kind=kind, instruction=instruction)
    return {**plan, "mode": "url", "message": _request_url_message(kind)}


def _request_done_message(kind: str, number) -> str:
    if kind == "image_revision":
        return (f"깃허브에 이미지 수정 요청 이슈 #{number} 를 등록했습니다. "
                "케빈이 고친 이미지를 같은 파일명으로 다시 올리면 20초 안에 자동으로 바뀝니다.")
    return f"깃허브에 이미지 요청 이슈 #{number} 를 등록했습니다."


def _request_url_message(kind: str) -> str:
    if kind == "image_revision":
        return "깃허브 이미지 수정 요청 화면을 열었습니다. [Create]만 누르면 케빈에게 전달됩니다."
    return "깃허브 새 이슈 화면을 열었습니다. [Create]만 누르면 케빈에게 전달됩니다."


def _append_request_log(p: dict, issue: dict, mode: str, error: str = "",
                       kind: str = "image_request", instruction: str = "") -> None:
    try:
        rec = {"time": now(), "mode": mode, "kind": kind, "url": issue.get("url", ""),
               "number": issue.get("number")}
        if instruction:
            rec["instruction"] = instruction[:500]
        if error:
            rec["error"] = error
        log = p.setdefault("request_log", [])
        log.append(rec)
        p["request_log"] = log[-20:]
        save(p)
    except Exception:
        pass


@app.get("/api/projects/{pid}/kevin-timeline")
def project_kevin_timeline(pid: str):
    """공개 저장소의 이슈·케빈 진행 댓글을 시간순으로 (토큰 없으면 비인증 조회)."""
    _check_pid(pid)
    try:
        return gh.timeline(pid)
    except Exception as e:
        return {"ok": False, "events": [], "issues": [], "error": str(e)[:300]}


@app.get("/api/inbox/auto")
def inbox_auto_status():
    return ib.status()


class InboxAutoIn(BaseModel):
    enabled: bool | None = None
    auto_assemble: bool | None = None


@app.post("/api/inbox/auto")
def inbox_auto_set(body: InboxAutoIn):
    patch = {}
    if body.enabled is not None:
        patch["auto_receive"] = bool(body.enabled)
    if body.auto_assemble is not None:
        patch["auto_assemble_on_receive"] = bool(body.auto_assemble)
    if patch:
        sch.save_settings(patch)
    ib.start_worker()
    return ib.status()


@app.post("/api/inbox/check")
def inbox_check_now():
    def work(progress):
        progress(25, "깃허브 assets_inbox 확인 중…")
        res = ib.receive_once("manual")
        progress(100, res.get("message") or "확인 완료")
        return res

    return {"job": start_job("inbox", work)}


@app.get("/api/inbox")
def inbox_list():
    out = []
    if INBOX.exists():
        for d in sorted(INBOX.iterdir()):
            if d.is_dir():
                imgs = sorted([p.name for p in d.glob("*") if p.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp")])
                if imgs:
                    out.append({"folder": d.name, "files": imgs[:80], "count": len(imgs)})
            elif d.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp"):
                out.append({"folder": "", "files": [d.name], "count": 1})
    return {"root": str(INBOX), "folders": out}


class InboxIn(BaseModel):
    project_id: str
    folder: str = ""


@app.post("/api/inbox/import")
def inbox_import(body: InboxIn):
    _check_pid(body.project_id)
    src = INBOX / body.folder if body.folder else INBOX
    if not src.exists() or INBOX not in src.parents and src != INBOX:
        raise HTTPException(400, "폴더를 찾을 수 없습니다.")
    p = load(body.project_id)
    plan = {e["file"] for e in p.get("image_plan", [])}
    dest = project_dir(body.project_id) / "images"
    dest.mkdir(parents=True, exist_ok=True)
    saved = []
    for f in src.rglob("*"):
        if f.is_file() and f.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp"):
            name = f.name
            if name in plan:
                dest.joinpath(name).write_bytes(f.read_bytes())
                saved.append(name)
    return {"saved": sorted(set(saved)), "missing": missing_images(p)}


# ── 프로세스 재시작 (새 코드 반영) ───────────────────────────────
def _read_head() -> str:
    """현재 작업 폴더의 git HEAD 커밋. (git 저장소가 아니면 빈 문자열)"""
    try:
        r = subprocess.run(["git", "-C", str(BASE), "rev-parse", "HEAD"],
                           capture_output=True, text=True, timeout=10)
        return (r.stdout or "").strip() if r.returncode == 0 else ""
    except Exception:
        return ""


_START_HEAD = _read_head()


def _disk_version() -> str:
    try:
        return (BASE / "VERSION").read_text(encoding="utf-8").strip()
    except Exception:
        return ""


def _server_port() -> int:
    """지금 서버가 쓰는 포트 — start.command 가 고른 포트를 그대로 재시작에 쓴다.

    순서: 실행 중인 명령줄(--port) → SEWOL_PORT 환경변수 → start.command 의 PORT=.
    """
    argv = [str(a) for a in sys.argv]
    for i, a in enumerate(argv):
        if a == "--port" and i + 1 < len(argv) and argv[i + 1].isdigit():
            return int(argv[i + 1])
        if a.startswith("--port=") and a.split("=", 1)[1].strip().isdigit():
            return int(a.split("=", 1)[1])
    for key in ("SEWOL_PORT", "UVICORN_PORT", "PORT"):
        val = (os.environ.get(key) or "").strip()
        if val.isdigit():
            return int(val)
    try:
        m = re.search(r"PORT=(\d{2,5})", (BASE / "start.command").read_text(encoding="utf-8"))
        if m:
            return int(m.group(1))
    except Exception:
        pass
    return 8765


def _restart_argv(port: int) -> list[str]:
    return [sys.executable, "-m", "uvicorn", "app.main:app",
            "--host", "0.0.0.0", "--port", str(port)]


def _restart_now(port: int) -> None:            # pragma: no cover - 실제 프로세스 교체
    os.execv(sys.executable, _restart_argv(port))


def _schedule_restart(port: int) -> None:
    """응답을 먼저 보내고 0.6초 뒤 같은 포트로 제자리 재시작한다."""
    threading.Timer(0.6, lambda: _restart_now(port)).start()


@app.post("/api/update/pull")
def update_pull():
    def work(progress):
        if not (BASE / ".git").exists():
            return {"ok": False, "restarting": False,
                    "message": "이 폴더는 깃허브 저장소가 아닙니다. README 의 [설치]를 참고해 git clone 으로 다시 받아 주세요."}
        progress(20, "깃허브에서 최신 버전 확인 중…")
        res = ib.git_pull()          # 자동 수신 워커와 같은 잠금을 쓴다 (동시 pull 방지)
        out = res.get("message") or ""
        disk_ver = _disk_version()
        ver_changed = bool(disk_ver) and disk_ver != __version__
        head_now = _read_head()
        head_changed = bool(head_now and _START_HEAD and head_now != _START_HEAD)
        # 워커가 먼저 pull 해서 'Already up to date' 가 나와도 코드가 바뀌었으면 재시작한다
        pulled_code = (bool(res.get("ok")) and res.get("reason") == "updated"
                       and any(k in out for k in ("app/", "VERSION", "requirements.txt",
                                                  "static/", "start.command", "tools/")))
        code_changed = bool(res.get("ok")) and (ver_changed or head_changed or pulled_code)
        port = _server_port()
        if code_changed:
            _schedule_restart(port)
        if code_changed:
            msg = (f"새 코드 반영 중… 서버가 {port} 포트로 제자리 재시작합니다. "
                   "2~3초 뒤 사파리가 자동으로 새로고침됩니다!")
        elif not res.get("ok"):
            msg = "업데이트 실패 — " + (res.get("message") or "알 수 없는 이유")
        else:
            msg = "이미 최신 버전입니다."
        return {"ok": bool(res.get("ok")), "restarting": code_changed, "port": port,
                "running_version": __version__, "disk_version": disk_ver,
                "head_changed": head_changed, "message": msg,
                "git": out[-1200:]}

    return {"job": start_job("update", work)}


@app.post("/api/update")
def update_now():
    """예전 이름(/api/update) — 같은 일을 한다(프론트 호환)."""
    return update_pull()


@app.get("/api/download/package")
def download_package():
    z = Path("/workspace/downloads/세월의사연극장_맥북_자동화패키지.zip")
    if not z.exists():
        raise HTTPException(404, "패키지 파일이 없습니다.")
    return FileResponse(str(z), filename=z.name)


def _check_pid(pid: str) -> None:
    if not PID_RE.match(pid or ""):
        raise HTTPException(400, "잘못된 프로젝트 번호입니다.")


def _image_files(pid: str) -> list[str]:
    d = project_dir(pid) / "images"
    if not d.exists():
        return []
    return sorted(p.name for p in d.glob("*") if p.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp"))


@app.get("/")
def index():
    f = STATIC_DIR / "index.html"
    if not f.exists():
        return JSONResponse({"message": "세월의 사연극장 서버가 실행 중입니다."})
    return FileResponse(str(f))


@app.exception_handler(FFmpegMissing)
def ffmpeg_missing(request, exc):
    return JSONResponse({"error": str(exc)}, status_code=500)
