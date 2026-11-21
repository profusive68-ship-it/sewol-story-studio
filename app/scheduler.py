"""매일 자동 제작·예약 업로드 스케줄러 + 예약 댓글 워커 (대시보드가 켜져 있는 동안 동작)."""
from __future__ import annotations

import json
import threading
import time
from datetime import datetime, timedelta

from .paths import BASE, LOG_DIR
from .settings import GENRES, load_config

CONFIG_DIR = BASE / "config"
SETTINGS_PATH = CONFIG_DIR / "settings.json"
STATE_PATH = CONFIG_DIR / "scheduler_state.json"

DEFAULTS = {
    "auto_daily": False,
    "daily_time": "04:00",
    "daily_genre": "tear_family",
    "daily_preset": "full40",
    "daily_publish_time": "21:00",
    "daily_image_mode": "B",
    "daily_auto_upload": True,
    "pin": "",
    "allow_remote": True,
}


def _ensure() -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)


def load_settings() -> dict:
    _ensure()
    data = dict(DEFAULTS)
    if SETTINGS_PATH.exists():
        try:
            data.update(json.loads(SETTINGS_PATH.read_text(encoding="utf-8")))
        except Exception:
            pass
    return data


def save_settings(patch: dict) -> dict:
    data = load_settings()
    for k, v in (patch or {}).items():
        if k in DEFAULTS:
            data[k] = v
    _ensure()
    SETTINGS_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return data


def load_state() -> dict:
    if STATE_PATH.exists():
        try:
            return json.loads(STATE_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def save_state(**kw) -> None:
    data = load_state()
    data.update(kw)
    data["updated"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    _ensure()
    STATE_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _log(msg: str) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    with open(LOG_DIR / "scheduler.log", "a", encoding="utf-8") as f:
        f.write(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {msg}\n")


def _publish_at_today(hhmm: str) -> str:
    now = datetime.now()
    h, m = (int(x) for x in (hhmm or "21:00").split(":"))
    target = now.replace(hour=h, minute=m, second=0, microsecond=0)
    if target <= now + timedelta(minutes=5):
        target += timedelta(days=1)
    return target.strftime("%Y-%m-%dT%H:%M")


def run_daily_job(trigger: str = "schedule") -> dict:
    """사연 1편 생성 → (모드 A면) 조립 → 예약 업로드."""
    from .project import create_project, load
    from .settings import load_config
    s = load_settings()
    cfg = load_config()
    mode = s.get("daily_image_mode", "B")
    if mode == "A" and not (cfg.get("gemini_api_key") or "").strip():
        mode = "B"
    genre = s.get("daily_genre", "tear_family")
    payload = {
        "preset": s.get("daily_preset", "full40"), "genre": genre if genre in GENRES else "tear_family",
        "topic": "", "hook15": True, "sequel": True, "teaser_mode": "auto_sequel",
        "voice_mode": "multi", "rate": 0, "avatar": True, "avatar_kind": "female",
        "subtitle_size": "senior", "image_mode": mode, "like_banner": True, "like_voice": True,
        "outro_cta": True, "end_screen": True, "sleep_rain": False, "bgm": True, "sfx": True,
        "auto_assemble": (mode == "A"), "auto_upload": bool(s.get("daily_auto_upload")),
        "youtube_privacy": "private", "youtube_publish_at": _publish_at_today(s.get("daily_publish_time", "21:00")),
        "youtube_title_index": 0,
    }
    _log(f"자동 제작 시작 ({trigger}) preset={payload['preset']} genre={payload['genre']} mode={mode}")
    p = create_project(payload)
    result = {"project_id": p["id"], "mode": mode, "status": "created"}
    if mode == "A":
        from .main import assemble_project
        assemble_project(p["id"], lambda q, m, step=None: None)
        result["status"] = "assembled"
        try:
            from .youtube_upload import has_client, upload_project
            if payload["auto_upload"] and has_client():
                r = upload_project(p["id"], 0, "private", payload["youtube_publish_at"])
                result.update({"uploaded": True, "url": r.get("url")})
        except Exception as e:
            result["upload_error"] = str(e)[:200]
    else:
        result["note"] = "모드 B — images 폴더에 이미지를 넣고 [조립]을 눌러 주세요. 이미지 요청서가 생성되었습니다."
    save_state(last_run=datetime.now().strftime("%Y-%m-%d"), last_result=result)
    _log(f"자동 제작 완료: {result}")
    return result


class Worker(threading.Thread):
    daemon = True

    def __init__(self):
        super().__init__(name="sewol-scheduler")
        self._stop = threading.Event()
        self._last_minute = ""

    def run(self):
        while not self._stop.is_set():
            try:
                from .youtube_upload import has_client, process_pending_comments
                if has_client():
                    done = process_pending_comments()
                    for d in done:
                        _log(f"예약 댓글 게시 완료: {d.get('video_id')}")
            except Exception as e:
                _log(f"예약 댓글 확인 실패: {str(e)[:150]}")
            try:
                s = load_settings()
                if s.get("auto_daily"):
                    now = datetime.now()
                    hhmm = now.strftime("%H:%M")
                    state = load_state()
                    if hhmm == s.get("daily_time", "04:00") and state.get("last_run") != now.strftime("%Y-%m-%d") \
                            and self._last_minute != hhmm:
                        self._last_minute = hhmm
                        threading.Thread(target=run_daily_job, args=("schedule",), daemon=True).start()
            except Exception as e:
                _log(f"스케줄 확인 실패: {str(e)[:150]}")
            self._stop.wait(20)

    def stop(self):
        self._stop.set()


_worker: Worker | None = None


def start_worker() -> None:
    global _worker
    if _worker is None or not _worker.is_alive():
        _worker = Worker()
        _worker.start()


def worker_alive() -> bool:
    return bool(_worker and _worker.is_alive())
