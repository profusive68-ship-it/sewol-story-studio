"""세월의 사연극장 — 로컬 웹 스튜디오 (FastAPI)."""
from __future__ import annotations

import io
import json
import os
import re
import shutil
import threading
import traceback
import uuid
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import __version__
from .audio_mix import build_mix
from .compile_parts import compile_weekend
from .ffmpeg_util import FFmpegMissing, ffmpeg_exe, version as ffmpeg_version
from .gemini_images import generate_images
from .gemini_script import SYSTEM_RULES
from .paths import ASSETS_DIR, BASE, PROJECTS_DIR, STATIC_DIR, ensure_dirs, project_dir
from .project import (CTA_SHORT, CTA_TEXT, LIKE_VOICE_SHORT, LIKE_VOICE_TEXT, build_timeline,
                      create_project, list_projects, load, missing_images, now, save, set_status,
                      write_image_request, write_upload_copy)
from .pronunciation import ensure_pron_file
from .render import detect_encoder, encoder_info, render_thumbnails, render_video
from .settings import (AVATAR_KINDS, FORMAT_PRESETS, GENRES, SUBTITLE_SIZES, VOICE_MODES,
                       load_config, public_config, save_config)
from .tts import synthesize_sync, voice_report
from . import youtube_upload as yt
from . import strategy as st
from . import comments as cm
from . import netinfo as net
from . import scheduler as sch
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

    def progress(pct: int, msg: str, step: int | None = None) -> None:
        with JOBS_LOCK:
            j = JOBS.get(jid)
            if not j:
                return
            j["percent"] = max(j.get("percent", 0), min(100, int(pct)))
            j["message"] = msg
            if step:
                j["step"] = int(step)
                j["step_label"] = STEP_LABELS.get(int(step), "")
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
        "subtitle_sizes": {k: {"px": v[0], "label": v[1]} for k, v in SUBTITLE_SIZES.items()},
        "avatar_kinds": AVATAR_KINDS,
        "config": public_config(),
        "encoder": encoder_info(),
        "defaults": {
            "like_voice_text": LIKE_VOICE_TEXT,
            "like_voice_short": LIKE_VOICE_SHORT,
            "cta_text": CTA_TEXT,
            "cta_short": CTA_SHORT,
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


@app.post("/api/config")
def set_config(body: ConfigIn):
    patch = {k: v for k, v in body.model_dump().items() if v is not None}
    if "gemini_api_key" in patch:
        patch["gemini_api_key"] = patch["gemini_api_key"].strip()
    save_config(patch)
    return public_config()


@app.post("/api/config/test")
def test_config():
    cfg = load_config()
    if not (cfg.get("gemini_api_key") or "").strip():
        return {"ok": False, "error": "API 키가 저장되어 있지 않습니다."}
    try:
        from google import genai
        from google.genai import types
        client = genai.Client(api_key=cfg["gemini_api_key"])
        resp = client.models.generate_content(
            model=cfg.get("text_model") or "gemini-2.5-flash",
            contents="한국어로 '연결 성공'이라고만 답해 주세요.",
            config=types.GenerateContentConfig(temperature=0, max_output_tokens=20))
        return {"ok": True, "message": (getattr(resp, "text", "") or "").strip()[:40] or "연결 성공"}
    except Exception as e:
        return {"ok": False, "error": str(e)[:300]}


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
    rate: int = 0
    avatar: bool = True
    avatar_kind: str = "female"
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
    base = Path(name).stem.lower()
    for f in plan_files:
        if f.lower() == name.lower():
            return f
        # s1.png → s01.png 허용
        m = re.match(r"^s(\d+)$", base)
        if m and f.lower() == f"s{int(m.group(1)):02d}.png":
            return f
    return None


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


@app.get("/api/projects/{pid}/image/{name}")
def project_image(pid: str, name: str):
    _check_pid(pid)
    if not re.match(r"^[A-Za-z0-9._\-]+\.(png|jpg|jpeg|webp)$", name):
        raise HTTPException(400, "잘못된 파일 이름입니다.")
    path = project_dir(pid) / "images" / name
    if not path.exists():
        raise HTTPException(404, "이미지가 없습니다.")
    return FileResponse(str(path))


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
            "rate": 0,
            "avatar": True,
            "avatar_kind": "female",
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


@app.post("/api/update/pull")
def update_pull():
    def work(progress):
        import subprocess as _sp
        root = str(BASE)
        if not (Path(root) / ".git").exists():
            return {"ok": False, "message": "이 폴더는 깃허브 저장소가 아닙니다. README 의 [설치]를 참고해 git clone 으로 다시 받아 주세요."}
        progress(20, "깃허브에서 최신 버전 확인 중…")
        r = _sp.run(["git", "-C", root, "pull", "--ff-only"], capture_output=True, text=True, timeout=120)
        msg = (r.stdout or "") + (r.stderr or "")
        return {"ok": r.returncode == 0, "message": msg.strip()[-1200:]}

    return {"job": start_job("update", work)}


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
