"""설정값·포맷 프리셋·성우 배역 정의."""
from __future__ import annotations

import json
import os
from copy import deepcopy

from .paths import CONFIG_PATH

DEFAULT_GITHUB_REPO = "profusive68-ship-it/sewol-story-studio"

DEFAULT_CONFIG = {
    "gemini_api_key": "",
    "text_model": "gemini-2.5-flash",
    "text_model_fallbacks": ["gemini-2.0-flash", "gemini-2.5-pro"],
    "image_model": "gemini-2.5-flash-image",
    "image_model_fallbacks": ["gemini-2.0-flash-preview-image-generation"],
    "encoder": "auto",          # auto | videotoolbox | libx264
    "force_scale": 0,           # 0 = 원본 해상도, 테스트용으로 0.5 등 지정 가능
    "keep_segments": False,
    "youtube_privacy": "private",
    "youtube_publish_at": "",
    "youtube_title_index": 0,
    "youtube_auto_upload": False,
    # 이미지 요청 이슈를 버튼 한 번에 자동 등록할 때 씁니다 (비워 두면 새 이슈 화면을 엽니다)
    "github_token": "",
    "github_repo": DEFAULT_GITHUB_REPO,
}

# ── 영상 포맷 ────────────────────────────────────────────────────────────────
FORMAT_PRESETS = {
    "shorts50": {
        "label": "50초 쇼츠", "aspect": "9:16",
        "width": 1080, "height": 1920, "target": 50,
        "scene_hint": (7, 10), "chapter_hint": 1, "intro_card": False,
        "note": "첫 3초 훅 · 자막 시원하게 · 세로 화면",
    },
    "pilot5": {
        "label": "5분 파일럿", "aspect": "16:9",
        "width": 1920, "height": 1080, "target": 300,
        "scene_hint": (34, 44), "chapter_hint": 4, "intro_card": True,
        "note": "한 편의 완결된 단편 · 4~5개 장",
    },
    "mid20": {
        "label": "20분 중편", "aspect": "16:9",
        "width": 1920, "height": 1080, "target": 1200,
        "scene_hint": (120, 160), "chapter_hint": 8, "intro_card": True,
        "note": "8개 장 · 감정선 완만하게 · 이미지 5~7분 간격",
    },
    "full40": {
        "label": "40분 본편", "aspect": "16:9",
        "width": 1920, "height": 1080, "target": 2400,
        "scene_hint": (220, 300), "chapter_hint": 12, "intro_card": True,
        "note": "12개 장 · 라디오 드라마형 몰입 · 이미지 5~7분 간격",
    },
    "weekend": {
        "label": "주말 2시간 몰아듣기 합본", "aspect": "16:9",
        "width": 1920, "height": 1080, "target": 7200,
        "scene_hint": (0, 0), "chapter_hint": 0, "intro_card": True,
        "note": "완성된 프로젝트 2~3개를 하나로 자동 합본",
    },
}

GENRES = {
    "tear_family": {
        "label": "① 눈물·가족 감동형",
        "hint": "부모·자식·형제의 오래된 오해와 사랑. 마지막에 가슴이 뭉클해지는 결말.",
        "emotion_arc": ["heal", "conflict", "twist", "heal"],
    },
    "reversal": {
        "label": "② 고구마→사이다 대반전형",
        "hint": "억울하게 몰린 주인공이 마지막에 통쾌하게 뒤집는 사이다 반전.",
        "emotion_arc": ["conflict", "conflict", "twist", "heal"],
    },
    "mystery": {
        "label": "③ 미스터리·휴먼 반전형",
        "hint": "한 가지 단서(편지·사진·물건)를 따라가다 밝혀지는 사람 사연.",
        "emotion_arc": ["conflict", "twist", "heal", "heal"],
    },
    "inlaw": {
        "label": "④ 시댁·부부 갈등형",
        "hint": "며느리·시어머니·부부 사이의 현실적인 갈등과 화해, 혹은 통쾌한 결말.",
        "emotion_arc": ["conflict", "conflict", "twist", "heal"],
    },
    "free": {
        "label": "⑤ 자유 주제 직접 입력",
        "hint": "직접 적어 주신 주제로 만든다.",
        "emotion_arc": ["conflict", "twist", "heal", "heal"],
    },
}

VOICE_MODES = {
    "multi": "다중 성우 라디오 드라마 (InJoon 해설 + BongJin 노인 + SunHi 여성 자동 분리)",
    "male": "단일 남성 낭독",
    "female": "단일 여성 낭독",
}

SUBTITLE_SIZES = {"senior": (92, "시니어 특대"), "basic": (70, "기본")}

AVATAR_KINDS = {"female": "여성 진행자", "male": "남성 진행자", "custom": "내 사진"}

# 성우 배역. 한국어 edge-tts 음성은 현재 InJoon / Hyunsu / SunHi 세 가지가 제공되므로
# BongJin·SoonBok 은 없을 때 대체 음성(피치·속도 보정)으로 자동 폴백한다.
VOICE_MAP = {
    "narrator": {"multi": "ko-KR-InJoonNeural", "male": "ko-KR-InJoonNeural",
                  "female": "ko-KR-SunHiNeural", "pitch": "+0Hz", "rate": 0},
    "female": {"multi": "ko-KR-SunHiNeural", "male": "ko-KR-InJoonNeural",
               "female": "ko-KR-SunHiNeural", "pitch": "+0Hz", "rate": 0},
    "old_female": {"multi": "ko-KR-SoonBokNeural", "male": "ko-KR-SunHiNeural",
                   "female": "ko-KR-SunHiNeural", "pitch": "-12Hz", "rate": -4},
    "young_male": {"multi": "ko-KR-HyunsuMultilingualNeural", "male": "ko-KR-InJoonNeural",
                   "female": "ko-KR-SunHiNeural", "pitch": "+2Hz", "rate": 2},
    "child": {"multi": "ko-KR-SunHiNeural", "male": "ko-KR-HyunsuMultilingualNeural",
              "female": "ko-KR-SunHiNeural", "pitch": "+25Hz", "rate": 4},
}

# BongJin(노인 남성)은 제공 중단된 음성이라 대체 음성으로 노인 톤을 만든다.
VOICE_SUBSTITUTES = {
    "ko-KR-BongJinNeural": ("ko-KR-HyunsuMultilingualNeural", "-20Hz", -6),
    "ko-KR-SoonBokNeural": ("ko-KR-SunHiNeural", "-18Hz", -6),
    "ko-KR-GookMinNeural": ("ko-KR-InJoonNeural", "-2Hz", 0),
    "ko-KR-JiMinNeural": ("ko-KR-SunHiNeural", "+0Hz", 0),
    "ko-KR-SeoHyeonNeural": ("ko-KR-SunHiNeural", "+4Hz", 0),
    "ko-KR-YuJinNeural": ("ko-KR-SunHiNeural", "+2Hz", 0),
}

SPEAKER_LABELS = {
    "narrator": "해설", "old_male": "노인", "old_female": "할머니",
    "female": "여성", "young_male": "청년", "child": "아이",
}


def old_male_voice() -> dict:
    return {"multi": "ko-KR-BongJinNeural", "male": "ko-KR-HyunsuMultilingualNeural",
            "female": "ko-KR-InJoonNeural", "pitch": "-12Hz", "rate": -3}


VOICE_MAP["old_male"] = old_male_voice()


def load_config() -> dict:
    cfg = deepcopy(DEFAULT_CONFIG)
    if CONFIG_PATH.exists():
        try:
            data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                cfg.update({k: v for k, v in data.items() if v is not None})
        except Exception:
            pass
    env_key = os.environ.get("GEMINI_API_KEY")
    if env_key and not cfg.get("gemini_api_key"):
        cfg["gemini_api_key"] = env_key
    return cfg


def save_config(patch: dict) -> dict:
    cfg = load_config()
    allowed = set(DEFAULT_CONFIG.keys())
    for k, v in patch.items():
        if k in allowed:
            cfg[k] = v
    CONFIG_PATH.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        os.chmod(CONFIG_PATH, 0o600)
    except Exception:
        pass
    return cfg


def public_config() -> dict:
    cfg = load_config()
    key = cfg.get("gemini_api_key") or ""
    gh = (cfg.get("github_token") or "").strip()
    return {
        "has_key": bool(key),
        "key_masked": (key[:6] + "••••••••" + key[-4:]) if len(key) > 12 else ("✓ 저장됨" if key else ""),
        "text_model": cfg["text_model"],
        "image_model": cfg["image_model"],
        "encoder": cfg["encoder"],
        "youtube_privacy": cfg.get("youtube_privacy", "private"),
        "youtube_publish_at": cfg.get("youtube_publish_at", ""),
        "youtube_title_index": cfg.get("youtube_title_index", 0),
        "youtube_auto_upload": cfg.get("youtube_auto_upload", False),
        "has_github_token": bool(gh),
        "github_token_masked": (gh[:4] + "••••••••" + gh[-4:]) if len(gh) > 10 else ("✓ 저장됨" if gh else ""),
        "github_repo": cfg.get("github_repo") or DEFAULT_GITHUB_REPO,
    }
