"""설정값·포맷 프리셋·성우 배역 정의."""
from __future__ import annotations

import json
import os
from copy import deepcopy

from .paths import CONFIG_PATH

DEFAULT_GITHUB_REPO = "profusive68-ship-it/sewol-story-studio"

DEFAULT_CONFIG = {
    "gemini_api_key": "",
    # 음성 엔진: edge(무료·기본) | openai(감성 TTS·유료)
    "tts_engine": "edge",
    "openai_api_key": "",
    "openai_tts_model": "gpt-4o-mini-tts",
    # OpenAI 키가 없거나 호출이 실패해도 제작이 멈추지 않게 edge-tts로 대체
    "openai_fallback_edge": True,
    "text_model": "gemini-3.8-flash",
    "text_model_fallbacks": ["gemini-2.5-flash-lite", "gemini-2.0-flash", "gemini-2.5-flash"],
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

TTS_ENGINES = {
    "openai": "OpenAI 감성 TTS (추천 · 유료)",
    "edge": "무료 edge-tts (기본 · 0원)",
}

OPENAI_TTS_MODELS = {
    "gpt-4o-mini-tts": "gpt-4o-mini-tts (감정 연기 지시 지원 · 추천)",
    "tts-1-hd": "tts-1-hd (가성비 · 연기 지시 없음)",
}

VOICE_MODES = {
    "multi": "다중 성우 라디오 드라마 (InJoon 해설 + BongJin 노인 + SunHi 여성 자동 분리)",
    "male": "단일 남성 낭독",
    "female": "단일 여성 낭독",
}

SUBTITLE_SIZES = {"senior": (92, "시니어 특대"), "basic": (70, "기본")}

# ── 진행자(나레이션 호스트) ──────────────────────────────────────────────────
# 1080p 짧은 변 기준 27% ≈ 290px. 시니어 시청자도 한눈에 얼굴을 알아볼 크기.
AVATAR_SIZE_RATIO = 0.27
AVATAR_SIZE_PX = 290
LIVE_BADGE_DEFAULT = True
LIVE_BADGE_PERIOD = 0.8          # 붉은 점 깜빡임 주기(초)
AVATAR_MOTION_CYCLE = 6.0        # 6초마다
AVATAR_MOTION_SECONDS = 1.6      # 1.6초 동안만 살짝 움직임

AVATAR_KINDS = {
    "auto": "자동 (나레이션 목소리 따라가기)",
    "female": "여성 라디오 진행자",
    "male": "남성 라디오 진행자",
    "custom": "내 사진",
}
AVATAR_GENDERS = {"male": "남성", "female": "여성"}

# 나레이션(해설) 목소리 기준 성별. OpenAI·edge 모두 해설자는 남성(onyx / InJoon)이고,
# 여성 단독 낭독일 때만 여성 진행자가 자연스럽다.
_NARRATOR_VOICE_GENDER = {
    "ko-KR-InJoonNeural": "male", "ko-KR-HyunsuMultilingualNeural": "male",
    "ko-KR-SunHiNeural": "female",
    "onyx": "male", "ash": "male", "echo": "male",
    "coral": "female", "sage": "female", "nova": "female",
}


def narrator_gender(options: dict | None = None, cfg: dict | None = None) -> str:
    """지금 설정으로 낭독(해설)을 맡는 목소리의 성별 → 진행자 성별."""
    opt = options or {}
    mode = str(opt.get("voice_mode") or "multi").lower()
    if mode == "female":
        return "female"
    if mode == "male":
        return "male"
    conf = cfg or {}
    engine = str(conf.get("tts_engine") or "edge").strip().lower()
    voice = ("onyx" if engine == "openai" else VOICE_MAP["narrator"]["multi"])
    return _NARRATOR_VOICE_GENDER.get(voice, "male")

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
    env_openai = os.environ.get("OPENAI_API_KEY")
    if env_openai and not cfg.get("openai_api_key"):
        cfg["openai_api_key"] = env_openai
    engine = str(cfg.get("tts_engine") or "edge").strip().lower()
    cfg["tts_engine"] = engine if engine in TTS_ENGINES else "edge"
    model = str(cfg.get("openai_tts_model") or "gpt-4o-mini-tts").strip()
    cfg["openai_tts_model"] = model if model in OPENAI_TTS_MODELS else "gpt-4o-mini-tts"
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


def mask_secret(value: str) -> str:
    """비밀키는 앞뒤 몇 글자만 보여 주고 가운데를 가린다."""
    v = (value or "").strip()
    if not v:
        return ""
    if len(v) > 12:
        return v[:6] + "••••••••" + v[-4:]
    return "✓ 저장됨"


def public_config() -> dict:
    cfg = load_config()
    key = cfg.get("gemini_api_key") or ""
    gh = (cfg.get("github_token") or "").strip()
    okey = (cfg.get("openai_api_key") or "").strip()
    return {
        "has_key": bool(key),
        "key_masked": mask_secret(key),
        "tts_engine": cfg.get("tts_engine", "edge"),
        "openai_tts_model": cfg.get("openai_tts_model", "gpt-4o-mini-tts"),
        "has_openai_key": bool(okey),
        "openai_key_masked": mask_secret(okey),
        "openai_fallback_edge": bool(cfg.get("openai_fallback_edge", True)),
        "tts_engines": TTS_ENGINES,
        "openai_tts_models": OPENAI_TTS_MODELS,
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
