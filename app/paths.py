"""패키지 안에서 쓰는 모든 경로를 한 곳에서 관리한다."""
from __future__ import annotations

from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
APP_DIR = BASE / "app"
STATIC_DIR = BASE / "static"
ASSETS_DIR = BASE / "assets"
FONT_DIR = ASSETS_DIR / "fonts"
PROJECTS_DIR = BASE / "projects"
CACHE_DIR = BASE / ".cache"
LOG_DIR = BASE / "logs"
CONFIG_DIR = BASE / "config"
CONFIG_PATH = CONFIG_DIR / "config.json"
PRON_PATH = CONFIG_DIR / "발음사전.txt"
VOICES_PATH = BASE / "config_voices.json"


def ensure_dirs() -> None:
    for p in (PROJECTS_DIR, CACHE_DIR, LOG_DIR, CONFIG_DIR, CACHE_DIR / "tts", CACHE_DIR / "sfx",
              CACHE_DIR / "music", CACHE_DIR / "particles", ASSETS_DIR, FONT_DIR):
        p.mkdir(parents=True, exist_ok=True)
    # 예전 버전(root config.json / 발음사전.txt) 자동 이전
    old_cfg = BASE / "config.json"
    if old_cfg.exists() and not CONFIG_PATH.exists():
        try:
            old_cfg.replace(CONFIG_PATH)
        except Exception:
            pass
    old_pron = BASE / "발음사전.txt"
    if old_pron.exists() and not PRON_PATH.exists():
        try:
            PRON_PATH.write_bytes(old_pron.read_bytes())
        except Exception:
            pass


def project_dir(pid: str) -> Path:
    return PROJECTS_DIR / pid
