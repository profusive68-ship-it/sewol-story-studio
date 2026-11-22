"""성우 낭독 — OpenAI 감성 TTS(gpt-4o-mini-tts) · 무료 edge-tts 폴백 · 발음 사전 · 캐시.

v2.0.2 — 속도 조절 폭 확대(모든 화자 동일)
  · 사용자가 전체 템포를 **0.85x ~ 1.15x(±15%)** 로 조절할 수 있다. 해설·인물·노인·아이 모두
    같은 배율을 쓰므로 화자 사이 속도 차이는 없다(`SPEED_TOLERANCE` 0.03 이내 유지).
    노인을 느리게 하는 것은 속도가 아니라 음높이(pitch)와 연기 지시로 만든다.

v2.0.0 — 성우 분리 · 속도 균일화 · 호흡 간격
  · **해설(narrator)과 대화 인물의 목소리를 절대 같은 voice 로 쓰지 않는다.**
    프로젝트의 장면을 한 번 훑어 `project_voice_plan()` 으로 화자별 목소리를 확정하고,
    그 표를 `project.json` 의 `voice_plan` 에 남겨 2단계 미리듣기·재녹음·본 렌더가
    모두 같은 목소리를 쓰게 한다. (해설 onyx ↔ 대화 ash/echo/verse/nova/shimmer/sage …)
  · **모든 화자의 속도를 하나로 고정한다.** `uniform_speed()` 는 언제나
    `1.00 ± SPEED_RANGE`(0.15) 범위(낭독 속도 설정도 ±15%)만 돌려주고, 해설·노인·아이 모두 같은 값을 쓴다.
  · 지시문(instructions)에 "극단적으로 빠르거나 느린 속도 금지, 해설과 같은 안정된
    한국어 낭독 속도 유지"를 항상 덧붙인다(`SPEED_RULE`).
  · 문장이 길어 여러 덩어리로 나뉠 때는 앞뒤 무음을 다듬고(`silenceremove`) **0.32초
    호흡 간격**으로 이어 붙인다(`join_with_breath`). ffmpeg 가 없으면 원본 그대로 잇는다.
  · 화자 표기(어머니·며느리·여성·남성 …)는 `app/speakers.py` 가 배역으로 확정한 값을 받는다.

엔진 선택(`config.tts_engine`)
  · "edge"   : 무료 edge-tts (기본값, 설치 없이 바로)
  · "openai" : OpenAI Audio Speech API 에 역할별 연기 지시(instructions)를 함께 보내
               사람이 읽는 듯한 감정 연출을 낸다. 키가 없거나 호출이 실패하면
               `config.openai_fallback_edge` 가 켜져 있을 때 edge-tts 로 안전하게 대체한다.

두 엔진 모두 발음 사전(pronunciation.tts_text)을 통과한 문장을 합성하고,
디스크 캐시 키에 engine·model 을 넣어 서로 섞이지 않게 한다.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import re
import shutil
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

from .ffmpeg_util import duration, ffmpeg_exe
from .paths import CACHE_DIR, project_dir
from .pronunciation import tts_text
from .settings import (BREATH_GAP_MAX, BREATH_GAP_MIN, BREATH_GAP_SECONDS, NARRATION_SPEED,
                       SPEED_RANGE, SPEED_RATE_MAX, SPEED_RATE_MIN, SPEED_TOLERANCE, VOICE_MAP,
                       VOICE_SUBSTITUTES, load_config)

try:  # requests 가 있으면 그대로 쓰고, 없으면 표준 라이브러리로 호출한다
    import requests  # type: ignore
except Exception:  # pragma: no cover - 설치되지 않은 환경
    requests = None  # type: ignore

CACHE_DIR.mkdir(parents=True, exist_ok=True)
(CACHE_DIR / "tts").mkdir(parents=True, exist_ok=True)

OPENAI_SPEECH_URL = "https://api.openai.com/v1/audio/speech"
OPENAI_DEFAULT_MODEL = "gpt-4o-mini-tts"
OPENAI_TIMEOUT = 90          # 초 (음성 1덩어리 기준)
OPENAI_CHUNK = 900           # 한 번에 보내는 글자 수 (모델 한도 4096자보다 넉넉히 작게)
EDGE_CHUNK = 180

TEST_TEXT = "안녕하세요. 세월의 사연극장입니다. 이 목소리가 잘 들리면 연결이 된 것입니다."
TEST_PREVIEW_NAME = "openai_test.mp3"

# ── v2.0.0 속도·호흡 기준 ────────────────────────────────────────────────
# 모든 화자가 같은 속도를 쓴다. 낭독 속도 설정은 ±15%(SPEED_RANGE) 안에서 함께 움직인다.
SPEED_RULE = ("속도는 극단적으로 빠르거나 느리게 읽지 말고, 해설자와 똑같은 안정된 "
              "한국어 낭독 속도를 유지하세요. 말이 빨라지거나 느려지면 안 됩니다.")

_substitute_lock = asyncio.Lock()
_broken_voices: set[str] = set()

# ── OpenAI 보이스 매핑 (역할 → 모드별 보이스) ────────────────────────────────
# onyx: 낮고 차분한 남성 / ash: 거친 질감의 남성 / echo: 또렷한 남성
# coral: 따뜻한 여성 / sage: 부드럽고 낮은 여성 / nova: 밝고 높은 여성
OPENAI_VOICE_MAP = {
    "narrator": {"multi": "onyx", "male": "onyx", "female": "coral"},
    "female": {"multi": "coral", "male": "coral", "female": "coral"},
    "old_female": {"multi": "sage", "male": "sage", "female": "sage"},
    "young_male": {"multi": "echo", "male": "echo", "female": "echo"},
    "old_male": {"multi": "ash", "male": "ash", "female": "ash"},
    "child": {"multi": "nova", "male": "nova", "female": "nova"},
}

# 해설(내레이션) 목소리 — 모드별로 고정. 대화 인물은 이 목소리를 절대 쓰지 않는다.
OPENAI_NARRATOR_VOICES = {"multi": "onyx", "male": "onyx", "female": "coral"}

# 대본에서 다른 이름으로 적혀도 같은 배역으로 본다
OPENAI_ROLE_ALIASES = {
    "elder": "old_male", "grandpa": "old_male", "oldman": "old_male",
    "grandma": "old_female", "oldwoman": "old_female",
    "man": "young_male", "woman": "female", "boy": "child", "girl": "child",
    "해설": "narrator", "노인": "old_male", "할머니": "old_female",
    "여성": "female", "청년": "young_male", "아이": "child",
    "남성": "young_male", "남자": "young_male", "여자": "female",
    "narr": "narrator", "narration": "narrator", "해설자": "narrator", "나레이션": "narrator",
    "어머니": "old_female", "아버지": "old_male", "며느리": "female", "아들": "young_male",
    "시어머니": "old_female", "딸": "female", "손자": "child", "손녀": "child",
}

# 역할별 감정 연기 지시문 (gpt-4o-mini-tts 전용 · tts-1-hd 에는 보내지 않는다)
OPENAI_INSTRUCTIONS = {
    "narrator": (
        "한국 시니어 라디오 드라마의 해설자입니다. 따뜻하고 차분한 심야 라디오 DJ처럼 "
        "낮고 안정된 톤으로, 문장 끝을 부드럽게 눌러 주며 감정을 과장하지 않습니다. "
        "슬픈 대목은 조금 느리고 숨을 고르듯, 따뜻한 대목은 미소가 섞인 듯 읽습니다. "
        "표준 한국어 발음으로 또박또박, 말이 너무 빠르지 않게."
    ),
    "old_male": (
        "70대 노인입니다. 낮고 연륜이 묻어나는 목소리로 천천히, 말끝을 조금 떨며 이야기합니다. "
        "감정이 북받치는 대목에서는 울먹임을 담되 소리치지 않고, 손주에게 이야기하듯 다정하게."
    ),
    "old_female": (
        "70대 할머니입니다. 가늘고 부드러운 목소리로 느리게, 정을 담아 이야기합니다. "
        "서운함과 눈물을 꾹 눌러 담은 듯한 숨결을 넣습니다."
    ),
    "female": (
        "40~50대 여성입니다. 담담하지만 정이 많고 따뜻한 목소리로, 서운함과 눈물을 참듯 "
        "조용히 읽습니다. 흥분한 대목에서도 날카롭지 않게."
    ),
    "young_male": (
        "20~30대 청년입니다. 또렷하고 조금 힘 있는 목소리로, 다급한 대목은 숨가쁘게 "
        "말하고 평소에는 자연스러운 대화체로 읽습니다."
    ),
    "child": (
        "7~10세 아이입니다. 밝고 높은 목소리로, 또박또박 조금 느리게 말합니다."
    ),
}


# ── 인물 맞춤 캐스팅 (나이·성별·성격·상황) ────────────────────────────────
# gpt-4o-mini-tts 가 공식 지원하는 보이스 범위 안에서만 고른다.
OPENAI_VOICES = ("alloy", "ash", "ballad", "coral", "echo", "fable", "nova", "onyx",
                 "sage", "shimmer", "verse")
OPENAI_MALE_VOICES = ("echo", "ash", "ballad", "verse", "fable", "onyx", "alloy")
OPENAI_FEMALE_VOICES = ("nova", "shimmer", "coral", "sage", "fable", "alloy")

# edge-tts 한국어 음성 — 세 종류뿐이라 '목소리 ID' 와 '음높이' 를 함께 써서 나눈다.
EDGE_MALE_1 = "ko-KR-InJoonNeural"
EDGE_MALE_2 = "ko-KR-HyunsuMultilingualNeural"
EDGE_FEMALE = "ko-KR-SunHiNeural"
EDGE_NARRATOR_VOICES = {"multi": EDGE_MALE_1, "male": EDGE_MALE_1, "female": EDGE_FEMALE}

EMOTION_KO = {"conflict": "갈등·서운함", "twist": "반전·충격", "heal": "치유·따뜻함"}

# 성격·상황 키워드 — 보이스는 나이·성별로 고르고, 결은 지시문과 미세 보정으로 살린다.
COLD_WORDS = ("냉정", "거만", "차갑", "싸늘", "분노", "화가", "악", "협박", "비꼬", "무뚝뚝",
              "권위", "재벌", "팀장", "사장", "형님", "고압")
WARM_WORDS = ("다정", "따뜻", "미소", "부드", "정 많", "온화", "자애", "포근", "웃으")
WEAK_WORDS = ("기력", "병상", "아프", "투병", "쇠약", "지친", "수척", "임종", "요양")
YOUNG_WORDS = ("어린", "아이", "학생", "청소년", "초등")
OLD_WORDS = ("노인", "노모", "노파", "할아버지", "할머니", "백발", "주름", "옹 ")


def _has(text: str, words: tuple[str, ...]) -> bool:
    t = str(text or "")
    return any(w in t for w in words)


# 대사에 나이가 없어도 성격·처지 키워드로 대략의 나이를 짐작한다.
def _infer_years(age, tone: str) -> int | None:
    years = parse_age(age)
    if years is not None:
        return years
    t = str(tone or "")
    if _has(t, OLD_WORDS):
        return 75
    if _has(t, YOUNG_WORDS):
        return 10
    if "청년" in t or "젊은" in t:
        return 28
    return None


# 역할만으로도 성별을 알 수 있는 경우(나이 정보가 없을 때의 기본값)
ROLE_GENDER = {"old_male": "male", "young_male": "male", "old_female": "female",
               "female": "female"}

CHARACTER_BASE = (
    "한국 라디오 드라마의 등장인물입니다. 대본의 대사를 실제 사람이 말하듯 자연스러운 "
    "구어체로 연기합니다. 나이와 성격, 지금 처한 상황이 목소리와 말투에 배어 나오게 하고, "
    "감정을 과장하지 않으면서도 숨소리·말끝·쉼이 살아 있게 읽습니다. 표준 한국어 발음으로 또박또박."
)


def parse_age(age) -> int | None:
    """'70대', '70대 후반', '78세', '8세', 'late 40s' → 대표 나이(정수)."""
    if age is None or isinstance(age, bool):
        return None
    if isinstance(age, (int, float)):
        v = int(age)
        return v if 0 < v <= 110 else None
    t = str(age).strip().lower()
    if not t:
        return None
    m = re.search(r"(\d{1,3})\s*대", t)
    if m:
        base = int(m.group(1))
        if "초" in t:
            return base + 2
        if "중" in t:
            return base + 5
        if "후" in t or "말" in t:
            return base + 8
        return base + 5
    m = re.search(r"(\d{1,3})\s*(?:세|살)", t)
    if m:
        return int(m.group(1))
    m = re.search(r"(?:late\s*)?(\d{1,3})\s*(?:s\b|years?\s*old|yo\b)", t)
    if m:
        v = int(m.group(1))
        return v + 8 if "late" in t else v
    m = re.search(r"(\d{1,3})", t)
    if m:
        v = int(m.group(1))
        if 0 < v <= 110:
            return v
    return None


def normalize_gender(gender) -> str:
    """male/female/남/여/남성/여성/아들/어머니… → 'male' | 'female' | ''."""
    t = str(gender or "").strip().lower()
    if not t:
        return ""
    if t in ("male", "m", "man", "boy", "남", "남자", "남성", "아들", "아버지", "할아버지",
             "청년", "삼촌", "오빠", "형", "손자", "사위"):
        return "male"
    if t in ("female", "f", "woman", "girl", "여", "여자", "여성", "딸", "어머니", "엄마",
             "할머니", "아내", "며느리", "누나", "언니", "아주머니", "시어머니", "손녀"):
        return "female"
    if any(k in t for k in ("female", "woman", "girl", "여성", "여자")):
        return "female"
    if any(k in t for k in ("male", "man", "boy", "남성", "남자")):
        return "male"
    return ""


# ── 속도 균일화 ──────────────────────────────────────────────────────────
def uniform_speed(rate: int = 0) -> float:
    """모든 화자가 함께 쓰는 OpenAI speed 배율 — 1.00 ± SPEED_RANGE(±0.15)."""
    try:
        r = int(rate)
    except Exception:
        r = 0
    pct = max(SPEED_RATE_MIN, min(SPEED_RATE_MAX, r))     # ±15% = ±0.15
    lo = round(NARRATION_SPEED - SPEED_RANGE, 2)
    hi = round(NARRATION_SPEED + SPEED_RANGE, 2)
    return round(max(lo, min(hi, NARRATION_SPEED + pct / 100.0)), 2)


def uniform_rate(rate: int = 0) -> int:
    """edge-tts 낭독 속도(%) — 모든 화자 공통, ±15% 안에서만."""
    try:
        r = int(rate)
    except Exception:
        r = 0
    return max(SPEED_RATE_MIN, min(SPEED_RATE_MAX, r))


def openai_speed(rate: int) -> float:
    """(하위 호환) 낭독 속도(%) → OpenAI speed 배율. v2 부터는 균일값을 돌려준다."""
    return uniform_speed(rate)


def clamp_speed(speed) -> float:
    """배율 그대로 받은 값을 0.25~4.0 안으로 다듬는다."""
    try:
        v = float(speed)
    except Exception:
        v = 1.0
    return round(max(0.25, min(4.0, v)), 2)


def with_speed_rule(instr: str) -> str:
    """연기 지시문 뒤에 '속도는 해설과 같게' 규칙을 붙인다(중복 방지)."""
    text = str(instr or "").strip()
    if not text:
        return SPEED_RULE
    if "속도는 극단적으로" in text:
        return text
    return text + " " + SPEED_RULE


def breath_gap() -> float:
    """문장 사이 호흡 간격(초) — 0.28~0.35 범위로 고정."""
    return round(max(BREATH_GAP_MIN, min(BREATH_GAP_MAX, BREATH_GAP_SECONDS)), 2)


def _voice_for(gender: str, years: int | None, tone: str = "") -> str:
    """나이·성별(+성격 결) → OpenAI 보이스. 정보가 없으면 빈 문자열."""
    g = normalize_gender(gender)
    if not g and years is None:
        return ""
    cold = _has(tone, COLD_WORDS)
    warm = _has(tone, WARM_WORDS)
    if years is not None and years <= 12:
        return "verse" if g == "male" else "nova"
    if years is not None and years < 20:
        return "echo" if g == "male" else "coral"
    if g == "male":
        if cold:
            return "ash"
        if years is not None and years >= 60:
            return "ash"
        if years is not None and years >= 40:
            return "ballad" if warm else "echo"      # 해설(onyx)과 겹치지 않는 남성 목소리
        return "ballad" if warm else "verse"
    if g == "female":
        if cold or (years is not None and years >= 60):
            return "sage"
        if years is not None and years < 40:
            return "nova" if warm else "shimmer"
        return "coral"
    return ""


def _base_instruction(role: str, has_meta: bool) -> str:
    """표준 6배역(old_male·female·narrator…)이 아니면 인물 지시문을 기본으로 쓴다.

    man/woman/elder 같은 별명이나 son·mil 같은 자유 화자 이름은 배역 기본 지시문이
    오히려 어긋나므로(예: '냉정한 팀장'에게 '다급한 청년' 지시), 인물 정보 기반으로 읽는다.
    """
    raw = str(role or "").strip()
    if has_meta and raw and raw not in OPENAI_VOICE_MAP:
        return CHARACTER_BASE
    return openai_instructions(role)


def _with_direction(base: str, age="", gender="", tone="", emotion="") -> str:
    parts = []
    g = normalize_gender(gender)
    if g:
        parts.append("성별: " + ("남성" if g == "male" else "여성"))
    if str(age or "").strip():
        parts.append("나이: " + str(age).strip()[:20])
    if str(tone or "").strip():
        parts.append("성격과 처지: " + str(tone).strip()[:120])
    if emotion in EMOTION_KO:
        parts.append("이 장면의 감정: " + EMOTION_KO[emotion])
    if not parts:
        return base
    return (base + " " + " / ".join(parts) +
            ". 이 인물의 나이와 성격, 지금 상황에 맞춰 말투·호흡·말끝을 살려 연기하세요.")


NARRATOR_ROLES = {"narrator", "해설", "해설자", "narr", "narration", "내레이션", "나레이션"}


def _is_narrator(role) -> bool:
    """해설역인가 — 빈 화자도 해설로 본다. 배역 이름이 아니라고 해설이 되지는 않는다."""
    raw = str(role or "").strip()
    if not raw:
        return True
    return raw in NARRATOR_ROLES or raw.lower() in NARRATOR_ROLES


def role_of(role) -> str:
    """화자 → 표준 배역 키. 모르는 이름(son·며느리 등)은 그대로 둔다(해설로 뭉개지 않음)."""
    raw = str(role or "").strip()
    if _is_narrator(raw):
        return "narrator"
    alias = OPENAI_ROLE_ALIASES.get(raw, OPENAI_ROLE_ALIASES.get(raw.lower(), raw))
    return alias if alias in OPENAI_VOICE_MAP else raw.lower()


def _norm_role(role: str) -> str:
    """(하위 호환) 배역 기본 목소리를 고를 때 쓰는 표준 6배역."""
    r = str(role or "narrator").strip()
    r = OPENAI_ROLE_ALIASES.get(r, OPENAI_ROLE_ALIASES.get(r.lower(), r))
    return r if r in OPENAI_VOICE_MAP else "narrator"


def openai_voice(role: str, mode: str = "multi") -> str:
    cfg = OPENAI_VOICE_MAP.get(_norm_role(role)) or OPENAI_VOICE_MAP["narrator"]
    return cfg.get(mode) or cfg.get("multi") or "onyx"


def openai_instructions(role: str) -> str:
    return OPENAI_INSTRUCTIONS.get(_norm_role(role), OPENAI_INSTRUCTIONS["narrator"])


def openai_narrator_voice(mode: str = "multi") -> str:
    """해설 목소리 — 이 목소리는 대화 인물에게 절대 배정하지 않는다."""
    return OPENAI_NARRATOR_VOICES.get(str(mode or "multi"), "onyx")


def _separate(preferred: str, gender: str, narrator: str, used=None) -> str:
    """해설·이미 쓴 목소리를 피해 대화 인물 목소리를 고른다(가능한 한 서로 다르게)."""
    g = normalize_gender(gender)
    pool = OPENAI_FEMALE_VOICES if g == "female" else OPENAI_MALE_VOICES
    taken = {narrator}
    for v in (used or set()):
        taken.add(v)
    order = [preferred] + [v for v in pool if v != preferred] + [v for v in OPENAI_VOICES if v != preferred]
    for v in order:
        if v and v not in taken:
            return v
    if preferred and preferred != narrator:
        return preferred
    return next((v for v in pool if v != narrator), "echo")


def openai_cast(role: str, mode: str = "multi", age="", gender="", tone="",
                emotion="", used=None) -> tuple[str, str]:
    """장면의 인물 정보로 (보이스, 연기 지시문)을 고른다.

    해설이면 모드별 해설 목소리(onyx/coral)를 그대로 쓰고,
    대화 인물이면 그 목소리를 피해서 고른다 — 해설과 인물이 같은 voice 가 되지 않는다.
    """
    narrator = openai_narrator_voice(mode)
    has_meta = bool(str(age or "").strip() or normalize_gender(gender) or str(tone or "").strip())
    if _is_narrator(role):
        instr = openai_instructions(role)
        if has_meta:
            instr = _with_direction(instr, age, gender, tone, emotion)
        return narrator, instr
    if not has_meta:
        base_voice = openai_voice(role, mode)
        voice = base_voice if base_voice != narrator else _separate("", "", narrator, used)
        return voice, openai_instructions(role)
    role_n = _norm_role(role)
    g = normalize_gender(gender) or ROLE_GENDER.get(role_n, "")
    years = _infer_years(age, tone)
    if role_n == "child":
        preferred = "verse" if g == "male" else "nova"
    else:
        preferred = _voice_for(g, years, tone) or openai_voice(role, mode)
    voice = _separate(preferred, g, narrator, used)
    instr = _with_direction(_base_instruction(role, has_meta), age, gender, tone, emotion)
    return voice, instr


def edge_narrator_voice(mode: str = "multi") -> str:
    return EDGE_NARRATOR_VOICES.get(str(mode or "multi"), EDGE_MALE_1)


def edge_cast(role: str, mode: str, global_rate: int, age="", gender="", tone="") -> tuple[str, str, int]:
    """무료 edge-tts 목소리·피치·속도.

    나이·성별 정보가 없으면 기존 배역 기본값 그대로(하위 호환).
    정보가 있으면 해설 목소리와 다른 음성을 쓰고, 속도는 모든 화자가 같은 값(±15%)이다.
    """
    voice, pitch, rate = _role_cfg(role, mode, global_rate)
    has_meta = bool(str(age or "").strip() or normalize_gender(gender) or str(tone or "").strip())
    if not has_meta:
        # 인물 정보가 없어도 속도는 모든 화자 동일(배역별 기본 속도 차이는 두지 않는다)
        return voice, pitch, uniform_rate(global_rate)
    narrator = edge_narrator_voice(mode)
    role_n = _norm_role(role)
    if _is_narrator(role):
        return narrator, "+0Hz", uniform_rate(global_rate)
    g = normalize_gender(gender) or ROLE_GENDER.get(role_n, "")
    years = _infer_years(age, tone)
    rate = uniform_rate(global_rate)          # 모든 화자 동일 속도
    if g == "male":
        voice = EDGE_MALE_2 if narrator != EDGE_MALE_2 else EDGE_MALE_1
        hz = 0
        if years is not None and years <= 12:
            hz = 14
        elif years is not None and years < 20:
            hz = 6
        elif years is not None and years >= 75:
            hz = -12
        elif years is not None and years >= 60:
            hz = -8
        if _has(tone, COLD_WORDS) and hz < 0:
            hz = max(hz, -6)
        pitch = f"{hz:+d}Hz"
    elif g == "female":
        voice = EDGE_FEMALE
        hz = 0
        if years is not None and years <= 12:
            hz = 24
        elif years is not None and years < 20:
            hz = 8
        elif years is not None and years < 30:
            hz = 4
        elif years is not None and years >= 75:
            hz = -18
        elif years is not None and years >= 60:
            hz = -14
        if voice == narrator:        # 여성 해설(SunHi) + 여성 인물: 음높이로만 구분
            hz = hz - 8 if hz <= 0 else hz
        pitch = f"{hz:+d}Hz"
    elif years is not None and years < 12:
        voice = EDGE_FEMALE
        pitch = "+24Hz"
    else:
        pitch = "+0Hz"
    return voice, pitch, rate


def scene_cast(scene: dict | None) -> dict:
    """장면 dict 에서 인물 정보만 꺼낸다(과거 프로젝트는 모두 빈 값)."""
    sc = scene or {}
    return {"age": str(sc.get("speaker_age") or "").strip()[:20],
            "gender": normalize_gender(sc.get("speaker_gender") or ""),
            "tone": str(sc.get("speaker_tone") or "").strip()[:120],
            "emotion": str(sc.get("emotion") or "").strip()}


def speaker_key(scene: dict | None) -> str:
    """같은 인물을 같은 목소리로 묶는 열쇠 — 배역 + 나이 + 성별 (연기 지시는 제외)."""
    sc = scene or {}
    role = role_of(sc.get("speaker") or "narrator")
    meta = scene_cast(sc)
    if role == "narrator":
        return "narrator"
    return "|".join([role, meta["age"], meta["gender"]])


def speaker_label(key: str, scene: dict | None = None) -> str:
    """화면에 보여 줄 화자 이름 — '어머니 (70대 후반·female)' 처럼."""
    from .settings import SPEAKER_LABELS
    sc = scene or {}
    role = key.split("|")[0]
    label = (str(sc.get("speaker_name") or "").strip()
             or SPEAKER_LABELS.get(role, role))
    parts = [p for p in key.split("|")[1:] if p]
    if parts:
        return f"{label} ({'·'.join(parts)})"
    return label


# ── 프로젝트 목소리 표 (해설 ↔ 인물 분리 확정) ─────────────────────────────
def project_voice_plan(project: dict, engine: str = "", model: str = "",
                       mode: str = "", rate=None) -> dict:
    """장면 전체를 한 번 훑어 화자별 목소리를 확정한다.

    · 해설 목소리는 모드별로 고정하고 대화 인물에게는 절대 주지 않는다.
    · 대화 인물끼리도 가능한 한 다른 목소리를 준다(같은 배역·나이·성별은 같은 목소리).
    · 모든 화자의 speed 는 `uniform_speed()` 하나로 같다.
    """
    st = _engine_settings()
    engine = str(engine or st["engine"] or "edge").lower()
    if engine not in ("openai", "edge"):
        engine = "edge"
    model = str(model or st["model"] or OPENAI_DEFAULT_MODEL)
    opts = project.get("options") or {}
    mode = str(mode or opts.get("voice_mode") or "multi")
    if mode not in ("multi", "male", "female"):
        mode = "multi"
    gr = int(opts.get("rate") or 0) if rate is None else int(rate)
    speed = uniform_speed(gr)
    erate = uniform_rate(gr)

    if engine == "openai":
        narrator_voice, narrator_pitch = openai_narrator_voice(mode), ""
        narrator_rate = 0
    else:
        narrator_voice, narrator_pitch = edge_narrator_voice(mode), "+0Hz"
        narrator_rate = erate

    used: set[str] = {narrator_voice}
    speakers: dict[str, dict] = {}
    notes: list[str] = []
    for sc in project.get("scenes") or []:
        key = speaker_key(sc)
        if key in speakers:
            continue
        role = role_of(sc.get("speaker") or "narrator")
        meta = scene_cast(sc)
        entry = {"role": role, "key": key, "label": speaker_label(key, sc),
                 "age": meta["age"], "gender": meta["gender"], "tone": meta["tone"],
                 "speed": speed, "rate": erate, "pitch": "", "voice": narrator_voice,
                 "edge_voice": edge_narrator_voice(mode), "edge_pitch": "+0Hz",
                 "edge_rate": erate, "fallback_voice": openai_narrator_voice(mode),
                 "instructions": with_speed_rule(openai_instructions("narrator")),
                 "separation": "narrator"}
        if role == "narrator":
            speakers[key] = entry
            continue
        if engine == "openai":
            voice, instr = openai_cast(role, mode, meta["age"], meta["gender"],
                                       meta["tone"], meta["emotion"], used=used)
            ev, ep, er = edge_cast(role, mode, gr, meta["age"], meta["gender"], meta["tone"])
            entry.update(voice=voice, instructions=with_speed_rule(instr),
                         edge_voice=ev, edge_pitch=ep, edge_rate=er,
                         separation="voice" if voice != narrator_voice else "pitch")
            used.add(voice)
        else:
            voice, pitch, er = edge_cast(role, mode, gr, meta["age"], meta["gender"], meta["tone"])
            if voice == narrator_voice and pitch == narrator_pitch:
                # 같은 음성·같은 음높이면 최소한 음높이를 벌린다(여성 해설 + 여성 인물)
                voice, pitch = _edge_pitch_split(voice, pitch)
                notes.append(f"{entry['label']}: edge-tts 한국어 음성이 하나뿐이라 음높이로 구분했습니다.")
            ov, oinstr = openai_cast(role, mode, meta["age"], meta["gender"],
                                     meta["tone"], meta["emotion"], used=used)
            entry.update(voice=voice, pitch=pitch, rate=er, fallback_voice=ov,
                         instructions=with_speed_rule(oinstr),
                         separation="voice" if voice != narrator_voice else "pitch")
        speakers[key] = entry

    collisions = [s["label"] for s in speakers.values()
                  if s["role"] != "narrator" and s["voice"] == narrator_voice and s["separation"] == "voice"]
    return {
        "engine": engine, "model": model if engine == "openai" else "", "mode": mode,
        "speed": speed, "rate": erate, "breath_gap": breath_gap(),
        "narrator": {"voice": narrator_voice, "pitch": narrator_pitch, "rate": narrator_rate,
                     "speed": speed, "label": "해설",
                     "edge_voice": edge_narrator_voice(mode),
                     "openai_voice": openai_narrator_voice(mode)},
        "speakers": speakers,
        "separation_ok": not collisions,
        "collisions": collisions,
        "notes": notes,
    }


def _edge_pitch_split(voice: str, pitch: str) -> tuple[str, str]:
    """같은 음성이면 음높이를 10Hz 이상 벌려 목소리를 구분한다."""
    try:
        hz = int(str(pitch).replace("Hz", ""))
    except Exception:
        hz = 0
    return voice, f"{hz - 10:+d}Hz"


def build_voice_plan(project: dict) -> dict:
    """지금 설정(엔진·모델·모드·속도)으로 목소리 표를 만들어 프로젝트에 저장한다."""
    plan = project_voice_plan(project)
    project["voice_plan"] = plan
    return plan


def plan_entry(plan: dict, scene: dict | None) -> dict:
    """목소리 표에서 이 장면의 화자 항목을 꺼낸다(없으면 해설)."""
    key = speaker_key(scene)
    speakers = (plan or {}).get("speakers") or {}
    if key in speakers:
        return speakers[key]
    narrator = (plan or {}).get("narrator") or {}
    return {"role": "narrator", "key": "narrator", "label": "해설",
            "voice": narrator.get("voice", "onyx"), "pitch": narrator.get("pitch", ""),
            "rate": narrator.get("rate", 0), "speed": (plan or {}).get("speed", NARRATION_SPEED),
            "instructions": with_speed_rule(OPENAI_INSTRUCTIONS["narrator"]),
            "separation": "narrator"}


def _engine_settings() -> dict:
    cfg = load_config()
    engine = str(cfg.get("tts_engine") or "edge").strip().lower()
    if engine not in ("edge", "openai"):
        engine = "edge"
    model = str(cfg.get("openai_tts_model") or OPENAI_DEFAULT_MODEL).strip()
    return {
        "engine": engine,
        "model": model,
        "api_key": (cfg.get("openai_api_key") or "").strip(),
        "fallback": bool(cfg.get("openai_fallback_edge", True)),
    }


def _supports_instructions(model: str) -> bool:
    """감정 연기 지시(instructions)는 gpt-4o 계열 음성 모델만 받는다."""
    return str(model or "").startswith("gpt-4o")


# ── edge-tts ────────────────────────────────────────────────────────────
def _role_cfg(role: str, mode: str, global_rate: int) -> tuple[str, str, int]:
    cfg = VOICE_MAP.get(_norm_role(role)) or VOICE_MAP["narrator"]
    voice = cfg.get(mode) or cfg.get("multi") or EDGE_MALE_1
    pitch = cfg.get("pitch", "+0Hz")
    rate = int(global_rate) + int(cfg.get("rate", 0))
    rate = max(-45, min(45, rate))
    return voice, pitch, rate


def _split_long(text: str, limit: int = EDGE_CHUNK) -> list[str]:
    if len(text) <= limit:
        return [text]
    parts, buf = [], ""
    for sent in re.split(r"(?<=[.!?])\s+", text):
        if len(buf) + len(sent) + 1 <= limit:
            buf = (buf + " " + sent).strip()
        else:
            if buf:
                parts.append(buf)
            buf = sent
    if buf:
        parts.append(buf)
    return parts or [text[:limit]]


async def _synth_one(text: str, voice: str, rate: int, pitch: str) -> bytes:
    import edge_tts
    last: Exception | None = None
    for attempt in range(3):
        try:
            com = edge_tts.Communicate(text, voice, rate=f"{rate:+d}%", pitch=pitch)
            data = bytearray()
            async for chunk in com.stream():
                if chunk["type"] == "audio":
                    data.extend(chunk["data"])
            if len(data) < 500:
                raise RuntimeError("빈 오디오")
            return bytes(data)
        except Exception as e:
            last = e
            await asyncio.sleep(0.8 * (attempt + 1))
    raise RuntimeError(f"TTS 실패({voice}): {last}")


async def _synth_with_fallback(text: str, voice: str, rate: int, pitch: str) -> bytes:
    global _broken_voices
    if voice in _broken_voices and voice in VOICE_SUBSTITUTES:
        voice, pitch, dr = VOICE_SUBSTITUTES[voice]
        rate = max(-45, min(45, rate + int(dr)))
    try:
        return await _synth_one(text, voice, rate, pitch)
    except Exception:
        if voice in VOICE_SUBSTITUTES:
            async with _substitute_lock:
                _broken_voices.add(voice)
            nv, npitch, dr = VOICE_SUBSTITUTES[voice]
            return await _synth_one(text, nv, max(-45, min(45, rate + int(dr))), npitch)
        raise


# ── 문장 이어붙이기: 무음 트림 + 일정한 호흡 간격 ──────────────────────────
def _ffmpeg() -> str | None:
    try:
        return ffmpeg_exe()
    except Exception:
        return None


def _silence_wav(gap: float) -> Path | None:
    """호흡 간격만큼의 무음 wav (한 번 만들어 캐시)."""
    exe = _ffmpeg()
    if not exe:
        return None
    name = f"_breath_{int(round(gap * 100)):03d}.wav"
    path = CACHE_DIR / "tts" / name
    if path.exists() and path.stat().st_size > 100:
        return path
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        r = subprocess.run([exe, "-y", "-hide_banner", "-loglevel", "error",
                            "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono",
                            "-t", f"{gap:.2f}", "-c:a", "pcm_s16le", str(path)],
                           capture_output=True, timeout=60)
        if r.returncode == 0 and path.exists() and path.stat().st_size > 100:
            return path
    except Exception:
        pass
    return None


def _trim_wav(src: Path, dst: Path) -> bool:
    """앞뒤 무음을 다듬어 wav 로 만든다(문장 사이 템포를 고르게)."""
    exe = _ffmpeg()
    if not exe:
        return False
    filt = ("silenceremove=start_periods=1:start_duration=0:start_threshold=-45dB,"
            "areverse,"
            "silenceremove=start_periods=1:start_duration=0:start_threshold=-45dB,"
            "areverse")
    try:
        r = subprocess.run([exe, "-y", "-hide_banner", "-loglevel", "error", "-i", str(src),
                            "-af", filt, "-ar", "44100", "-ac", "1", "-c:a", "pcm_s16le",
                            str(dst)], capture_output=True, timeout=120)
        return r.returncode == 0 and dst.exists() and dst.stat().st_size > 200
    except Exception:
        return False


def join_with_breath(chunks: list[bytes], gap: float | None = None,
                     workdir: Path | None = None) -> tuple[bytes, str]:
    """여러 음성 덩어리를 앞뒤 무음 트림 후 일정한 호흡 간격으로 잇는다.

    반환: (mp3 바이트, 방식) — 방식은 "ffmpeg" 또는 "raw".
    ffmpeg 가 없거나 실패하면 원본을 그대로 이어 붙인다(제작이 멈추지 않게).
    """
    data = [c for c in chunks if c]
    if not data:
        return b"", "raw"
    if len(data) == 1:
        return data[0], "raw"
    gap_sec = breath_gap() if gap is None else round(float(gap), 2)
    exe = _ffmpeg()
    silence = _silence_wav(gap_sec) if exe else None
    if not exe or not silence:
        return b"".join(data), "raw"
    tmp = Path(workdir) if workdir else Path(tempfile.mkdtemp(prefix="sewol_breath_"))
    tmp.mkdir(parents=True, exist_ok=True)
    try:
        parts: list[Path] = []
        for i, blk in enumerate(data):
            src = tmp / f"c{i:02d}.mp3"
            wav = tmp / f"c{i:02d}.wav"
            src.write_bytes(blk)
            parts.append(wav if _trim_wav(src, wav) else src)
        listing = tmp / "list.txt"
        lines: list[str] = []
        for i, part in enumerate(parts):
            if i:
                lines.append(f"file '{silence.name}'")
            lines.append(f"file '{part.name}'")
        listing.write_text("\n".join(lines) + "\n", encoding="utf-8")
        out = tmp / "joined.mp3"
        r = subprocess.run([exe, "-y", "-hide_banner", "-loglevel", "error",
                            "-f", "concat", "-safe", "0", "-i", str(listing),
                            "-c:a", "libmp3lame", "-b:a", "128k", str(out)],
                           capture_output=True, timeout=180)
        if r.returncode == 0 and out.exists() and out.stat().st_size > 500:
            return out.read_bytes(), "ffmpeg"
    except Exception:
        pass
    finally:
        if workdir is None:
            shutil.rmtree(tmp, ignore_errors=True)
    return b"".join(data), "raw"


# ── OpenAI Audio Speech ─────────────────────────────────────────────────
def _decode(raw: bytes) -> str:
    try:
        return raw.decode("utf-8", "replace")
    except Exception:
        return ""


def _http_post_json(url: str, payload: dict, headers: dict, timeout: int) -> tuple[int, bytes, str]:
    """POST 한 번 — requests 가 없으면 표준 라이브러리로 같은 요청을 보낸다."""
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    if requests is not None:
        try:
            r = requests.post(url, data=body, headers=headers, timeout=(10, timeout))
        except Exception as e:
            raise RuntimeError(f"OpenAI 서버에 연결하지 못했습니다: {str(e)[:160]}")
        return int(r.status_code), r.content or b"", _decode(r.content or b"")
    req = urllib.request.Request(url, data=body, headers=dict(headers), method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = resp.read()
            return int(getattr(resp, "status", 200) or 200), data, ""
    except urllib.error.HTTPError as e:
        raw = e.read() if hasattr(e, "read") else b""
        return int(e.code), raw, _decode(raw)
    except Exception as e:
        raise RuntimeError(f"OpenAI 서버에 연결하지 못했습니다: {str(e)[:160]}")


def openai_error_message(status: int, body: str) -> str:
    """OpenAI 오류 응답을 맥북 화면에서 바로 읽을 수 있는 한국어로 바꾼다."""
    msg = ""
    try:
        payload = json.loads(body or "{}")
        err = payload.get("error") if isinstance(payload, dict) else None
        if isinstance(err, dict):
            msg = str(err.get("message") or "")
        elif isinstance(err, str):
            msg = err
    except Exception:
        msg = (body or "").strip()
    msg = msg[:200]
    if status == 401:
        return ("OpenAI API 키가 올바르지 않습니다(401). "
                "platform.openai.com/api-keys 에서 키를 다시 확인해 주세요.")
    if status == 403:
        return ("이 키로는 음성 합성을 쓸 수 없습니다(403). 결제 정보와 키 권한을 확인해 주세요.")
    if status == 404:
        return "요청한 음성 모델이나 보이스를 찾을 수 없습니다(404). " + (msg or "")
    if status == 429:
        return ("OpenAI 사용 한도를 넘었습니다(429). 결제 정보·월 한도를 확인해 주세요. "
                + (msg or ""))
    if status == 400:
        return "요청이 거부되었습니다(400). " + (msg or "모델·보이스 이름을 확인해 주세요.")
    if status >= 500:
        return f"OpenAI 서버가 잠시 불안정합니다({status}). " + (msg or "")
    return f"OpenAI 음성 호출 실패({status}). " + (msg or "")


RETRY_STATUS = (408, 409, 425, 429, 500, 502, 503, 504)


def synthesize_openai_chunk(text: str, voice: str, speed: float, instructions: str,
                            model: str, api_key: str, retries: int = 2) -> bytes:
    """OpenAI Audio Speech 로 한 덩어리 mp3 바이트를 만든다 (동기)."""
    if not (api_key or "").strip():
        raise RuntimeError("OpenAI API 키가 없습니다.")
    payload = {
        "model": model or OPENAI_DEFAULT_MODEL,
        "input": text,
        "voice": voice or "onyx",
        "response_format": "mp3",
        "speed": clamp_speed(speed),
    }
    if instructions and _supports_instructions(model):
        payload["instructions"] = instructions
    headers = {"Authorization": "Bearer " + api_key.strip(), "Content-Type": "application/json"}

    last = "OpenAI 음성 합성에 실패했습니다."
    for attempt in range(retries + 1):
        status, data, body = _http_post_json(OPENAI_SPEECH_URL, payload, headers, OPENAI_TIMEOUT)
        if status == 200 and len(data) > 500:
            return data
        if status == 200:
            last = "OpenAI가 빈 음성을 돌려주었습니다. 잠시 뒤 다시 시도해 주세요."
        else:
            last = openai_error_message(status, body)
        if status in RETRY_STATUS and attempt < retries:
            time.sleep(1.0 * (attempt + 1))
            continue
        raise RuntimeError(last)
    raise RuntimeError(last)


def openai_payload_preview(text: str, role: str = "narrator", mode: str = "multi",
                           rate: int = 0, model: str = OPENAI_DEFAULT_MODEL) -> dict:
    """실제로 OpenAI 에 보낼 payload 모양 (테스트·화면 설명용).

    인물 정보(나이·성별)가 없는 '배역 기본값' 이다. 실제 제작은
    `project_voice_plan()` 이 프로젝트 전체를 보고 해설과 겹치지 않는 목소리를 정한다.
    """
    voice = openai_voice(role, mode)
    instr = with_speed_rule(openai_instructions(role))
    payload = {
        "model": model or OPENAI_DEFAULT_MODEL,
        "input": text,
        "voice": voice,
        "response_format": "mp3",
        "speed": uniform_speed(rate),
    }
    if instr and _supports_instructions(model):
        payload["instructions"] = instr
    return payload


def test_openai_tts(cfg: dict | None = None, save_preview: bool = True) -> dict:
    """설정 화면 [연결 테스트] — 짧은 한국어 한 문장을 실제로 합성해 본다."""
    st = _engine_settings()
    cfg = cfg or {}
    api_key = (cfg.get("openai_api_key") or st["api_key"] or "").strip()
    model = str(cfg.get("openai_tts_model") or st["model"] or OPENAI_DEFAULT_MODEL).strip()
    if not api_key:
        return {"ok": False, "error": "OpenAI API 키가 저장되어 있지 않습니다. 키를 먼저 저장해 주세요."}
    text = tts_text(TEST_TEXT) or TEST_TEXT
    voice = openai_narrator_voice("multi")
    try:
        data = synthesize_openai_chunk(text, voice, uniform_speed(0),
                                       with_speed_rule(openai_instructions("narrator")),
                                       model, api_key, retries=1)
    except RuntimeError as e:
        return {"ok": False, "error": str(e)[:300], "model": model, "voice": voice}
    except Exception as e:  # pragma: no cover - 예상 밖 오류도 화면에 알린다
        return {"ok": False, "error": f"연결 테스트 실패: {str(e)[:250]}",
                "model": model, "voice": voice}

    preview_url = ""
    seconds = 0.0
    if save_preview:
        dest = CACHE_DIR / "tts" / TEST_PREVIEW_NAME
        try:
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(data)
            preview_url = f"/api/tts/preview?ts={int(dest.stat().st_mtime)}"
            try:
                seconds = round(float(duration(dest)), 1)
            except Exception:
                seconds = round(len(TEST_TEXT) / 4.3, 1)
        except Exception:
            preview_url = ""
    if not seconds:
        seconds = round(len(TEST_TEXT) / 4.3, 1)
    return {
        "ok": True,
        "message": (f"연결 성공 — {model} · {voice} · {len(data) // 1024}KB · 약 {seconds}초"),
        "model": model,
        "voice": voice,
        "bytes": len(data),
        "seconds": seconds,
        "preview_url": preview_url,
    }


def preview_path() -> Path:
    return CACHE_DIR / "tts" / TEST_PREVIEW_NAME


# ── 캐시 ────────────────────────────────────────────────────────────────
def _cache_path(text: str, engine: str, model: str, voice: str, rate: int,
                pitch: str, speed: float, instructions: str) -> Path:
    raw = "|".join([
        engine, model, voice, f"{rate:+d}", pitch, f"{float(speed):.2f}",
        hashlib.sha1((instructions or "").encode("utf-8")).hexdigest()[:8], text,
    ])
    key = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:20]
    return CACHE_DIR / "tts" / f"{engine}_{key}.mp3"


# ── 한 장면 합성 (본 제작·미리듣기·재녹음 공용) ─────────────────────────
class _Synth:
    """한 번의 제작에서 공유하는 엔진·목소리 표·경고 창구."""

    def __init__(self, project: dict) -> None:
        self.project = project
        self.opts = project.get("options") or {}
        self.mode = str(self.opts.get("voice_mode") or "multi")
        self.gr = int(self.opts.get("rate") or 0)
        self.st = _engine_settings()
        self.state = {"engine": self.st["engine"]}
        self.model = self.st["model"]
        self.api_key = self.st["api_key"]
        self.fallback = self.st["fallback"]
        self.warned = {"flag": False}
        self.plan = project_voice_plan(project, engine=self.state["engine"],
                                       model=self.model, mode=self.mode, rate=self.gr)
        project["voice_plan"] = self.plan

    def warn(self, msg: str) -> None:
        if self.warned["flag"]:
            return
        self.warned["flag"] = True
        try:
            self.project.setdefault("warnings", []).append(msg)
        except Exception:
            pass

    def prepare(self) -> bool:
        """OpenAI 키가 없을 때 edge 로 내려갈지 정한다(내려가면 False)."""
        if self.state["engine"] == "openai" and not self.api_key:
            if not self.fallback:
                raise RuntimeError(
                    "OpenAI API 키가 없습니다. [🎙️ 음성 엔진]에서 키를 저장하거나 "
                    "음성 엔진을 '무료 edge-tts'로 바꿔 주세요.")
            self.warn("OpenAI API 키가 없어 무료 edge-tts로 제작했습니다. "
                      "[🎙️ 음성 엔진]에서 키를 저장하면 다음 편부터 감성 TTS로 나갑니다.")
            self.state["engine"] = "edge"
            self.plan = project_voice_plan(self.project, engine="edge", mode=self.mode,
                                           rate=self.gr)
            self.project["voice_plan"] = self.plan
            return False
        return self.state["engine"] == "openai"

    def entry(self, scene: dict) -> dict:
        return plan_entry(self.plan, scene)

    def plan_for(self, text: str, scene: dict) -> dict:
        e = self.entry(scene)
        voice = e.get("voice") or "onyx"
        if self.state["engine"] == "openai":
            instr = with_speed_rule(e.get("instructions") or openai_instructions(e.get("role")))
            speed = float(self.plan.get("speed") or uniform_speed(self.gr))
            return {"engine": "openai", "voice": voice, "speed": speed, "instr": instr,
                    "rate": 0, "pitch": "", "limit": OPENAI_CHUNK,
                    "cache": _cache_path(text, "openai", self.model, voice, 0, "", speed, instr)}
        voice = e.get("edge_voice") or voice
        rate = int(e.get("edge_rate", e.get("rate", uniform_rate(self.gr))))
        pitch = e.get("edge_pitch") or e.get("pitch") or "+0Hz"
        return {"engine": "edge", "voice": voice, "speed": 0.0, "instr": "",
                "rate": rate, "pitch": pitch, "limit": EDGE_CHUNK,
                "cache": _cache_path(text, "edge", "", voice, rate, pitch, 0.0, "")}

    async def synth_part(self, part: str, scene: dict) -> bytes:
        e = self.entry(scene)
        if self.state["engine"] == "openai":
            instr = with_speed_rule(e.get("instructions") or openai_instructions(e.get("role")))
            try:
                return await asyncio.to_thread(
                    synthesize_openai_chunk, part, e.get("voice") or "onyx",
                    float(self.plan.get("speed") or uniform_speed(self.gr)), instr,
                    self.model, self.api_key)
            except RuntimeError as ex:
                if not self.fallback:
                    raise
                self.warn(f"OpenAI 음성 호출에 실패해 무료 edge-tts로 대체했습니다 — {str(ex)[:140]}")
                self.state["engine"] = "edge"
        voice = e.get("edge_voice") or e.get("voice") or EDGE_MALE_1
        rate = int(e.get("edge_rate", e.get("rate", uniform_rate(self.gr))))
        pitch = e.get("edge_pitch") or e.get("pitch") or "+0Hz"
        if not str(voice).startswith("ko-KR-"):
            voice = EDGE_MALE_1
        return await _synth_with_fallback(part, voice, rate, pitch)

    async def render_line(self, text: str, scene: dict, workdir: Path | None = None) -> tuple[bytes, str]:
        """한 장면 분량의 음성을 만든다(여러 덩어리면 무음 트림 + 호흡 간격)."""
        plan = self.plan_for(text, scene)
        planned = plan["engine"]
        chunks: list[bytes] = []
        for part in _split_long(text, int(plan["limit"])):
            chunks.append(await self.synth_part(part, scene))
        used = self.state["engine"]        # 도중에 edge 로 내려갔으면 그 엔진으로 기록
        if len(chunks) == 1:
            return chunks[0], planned if used == planned else used
        data, _how = join_with_breath(chunks, breath_gap(), workdir)
        return data, used


# ── 본 합성 ─────────────────────────────────────────────────────────────
async def synthesize_lines(project: dict, progress=None, only_missing: bool = False) -> dict[str, float]:
    """모든 장면 음성을 만들고 장면별 길이(초)를 돌려준다.

    목소리는 `project_voice_plan()` 이 정한 표를 그대로 쓴다(해설 ↔ 인물 분리·속도 균일).
    """
    scenes = project["scenes"]
    pdir = project_dir(project["id"])
    lines_dir = pdir / "audio_clips"
    lines_dir.mkdir(parents=True, exist_ok=True)

    syn = _Synth(project)
    syn.prepare()

    jobs = []
    for sc in scenes:
        text = tts_text(sc.get("text", ""))
        if not text:
            text = "…"
        jobs.append((sc, text))
    if only_missing:
        jobs = [j for j in jobs if not (lines_dir / f"{j[0]['id']}.mp3").exists()
                or (lines_dir / f"{j[0]['id']}.mp3").stat().st_size < 500]

    sem = asyncio.Semaphore(4)
    durations: dict[str, float] = {}
    done = {"n": 0}

    async def worker(sc, text):
        dest = lines_dir / f"{sc['id']}.mp3"
        async with sem:
            if not dest.exists() or dest.stat().st_size < 500:
                plan = syn.plan_for(text, sc)
                cache: Path = plan["cache"]
                if cache.exists() and cache.stat().st_size > 500:
                    dest.write_bytes(cache.read_bytes())
                else:
                    data, engine_used = await syn.render_line(text, sc)
                    if engine_used == plan["engine"]:
                        try:
                            if data and len(data) > 500:
                                cache.write_bytes(data)
                        except Exception:
                            pass
                    dest.write_bytes(data)
        try:
            durations[sc["id"]] = duration(dest)
        except Exception:
            durations[sc["id"]] = max(1.2, len(text) / 4.3)
        done["n"] += 1
        if progress:
            progress(done["n"], len(jobs))

    await asyncio.gather(*[worker(*j) for j in jobs])
    if not only_missing:
        for sc, _text in jobs:
            durations.setdefault(sc["id"], 0.0)
    # 이미 만들어 둔 장면(only_missing)도 길이를 채운다
    for sc in scenes:
        if sc["id"] not in durations:
            clip = lines_dir / f"{sc['id']}.mp3"
            try:
                durations[sc["id"]] = duration(clip) if clip.exists() else 0.0
            except Exception:
                durations[sc["id"]] = 0.0
    write_voice_meta(project)
    return durations


def synthesize_sync(project: dict, progress=None, only_missing: bool = False) -> dict[str, float]:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(synthesize_lines(project, progress, only_missing))
    # 이미 이벤트 루프 안이면 별도 스레드에서 실행
    import concurrent.futures
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
        return ex.submit(lambda: asyncio.run(synthesize_lines(project, progress, only_missing))).result()


def clip_path(pid: str, scene_id: str) -> Path:
    return project_dir(pid) / "audio_clips" / f"{scene_id}.mp3"


def preview_dir(pid: str) -> Path:
    d = project_dir(pid) / "audio_preview"
    d.mkdir(parents=True, exist_ok=True)
    return d


def synthesize_line_preview(project: dict, scene: dict, text: str | None = None,
                            name: str | None = None) -> dict:
    """한 대사만 다시 녹음/미리듣기 한다(2단계 음성 검토).

    · 같은 목소리 표(project_voice_plan)를 쓰므로 본 렌더와 목소리가 같다.
    · 바꾼 대사는 이 미리듣기 파일에만 담고, 대본 저장은 따로 한다.
    """
    text = tts_text(text if text is not None else scene.get("text", "")) or "…"
    syn = _Synth(project)
    syn.prepare()
    data, engine = asyncio.run(_render_preview(syn, text, scene))
    if not data or len(data) < 200:
        raise RuntimeError("음성을 만들지 못했습니다.")
    out = preview_dir(project["id"]) / f"{(name or scene.get('id') or 'line')}.mp3"
    out.write_bytes(data)
    entry = syn.entry(scene)
    try:
        seconds = round(float(duration(out)), 2)
    except Exception:
        seconds = round(max(1.0, len(text) / 4.3), 2)
    return {"ok": True, "file": out.name, "seconds": seconds, "engine": engine,
            "voice": entry.get("voice"), "pitch": entry.get("pitch", ""),
            "speed": float(syn.plan.get("speed") or uniform_speed(syn.gr)),
            "rate": int(entry.get("rate", 0)),
            "speaker": entry.get("role"), "label": entry.get("label"),
            "text": text}


async def _render_preview(syn: "_Synth", text: str, scene: dict):
    return await syn.render_line(text, scene)


def write_voice_meta(project: dict) -> Path:
    """2단계 화면이 읽는 목소리 표·속도·호흡 간격을 프로젝트 폴더에 남긴다."""
    pdir = project_dir(project["id"])
    plan = project.get("voice_plan") or project_voice_plan(project)
    data = {
        "engine": plan.get("engine"), "model": plan.get("model"), "mode": plan.get("mode"),
        "speed": plan.get("speed"), "rate": plan.get("rate"),
        "breath_gap": plan.get("breath_gap"), "separation_ok": plan.get("separation_ok"),
        "notes": plan.get("notes", []),
        "narrator": plan.get("narrator", {}),
        "speakers": {k: {kk: vv for kk, vv in v.items() if kk != "instructions"}
                     for k, v in (plan.get("speakers") or {}).items()},
        "written_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    path = pdir / "voice_plan.json"
    try:
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass
    return path


def voice_report(project: dict) -> str:
    """화면·script.json 에 남기는 성우 요약 — 해설/인물 목소리와 공통 속도.

    저장된 목소리 표가 지금 음성 엔진과 다르면(엔진을 바꿨거나 폴백) 지금 설정으로 다시 계산한다.
    """
    st = _engine_settings()
    plan = project.get("voice_plan") or {}
    if str(plan.get("engine") or "") != str(st["engine"]):
        plan = project_voice_plan(project)
    narrator = plan.get("narrator") or {}
    rows = [f"해설: {narrator.get('voice', '')}"]
    for s in (plan.get("speakers") or {}).values():
        if s.get("role") == "narrator":
            continue
        extra = s.get("pitch") or ""
        rows.append(f"{s.get('label') or s.get('role')}: {s.get('voice')}{(' ' + extra) if extra else ''}")
    speed = plan.get("speed")
    tail = f" (x{float(speed):.2f})" if speed is not None else ""
    if plan.get("engine") == "openai":
        return f"OpenAI {plan.get('model') or OPENAI_DEFAULT_MODEL} · " + " / ".join(rows) + tail
    prefix = "무료 edge-tts"
    if st["engine"] == "openai":
        prefix = "무료 edge-tts (OpenAI 키 없음)"
    return prefix + " · " + " / ".join(rows) + tail


def separation_violations(plan: dict) -> list[str]:
    """해설과 같은 voice 를 쓰는 대화 인물(비어 있어야 정상)."""
    narrator = ((plan or {}).get("narrator") or {}).get("voice")
    out = []
    for s in ((plan or {}).get("speakers") or {}).values():
        if s.get("role") != "narrator" and s.get("voice") == narrator:
            out.append(s.get("label") or s.get("role") or "")
    return out


def speed_values(plan: dict) -> list[float]:
    """목소리 표에 적힌 모든 화자의 속도(값이 하나여야 균일)."""
    vals = [float(((plan or {}).get("narrator") or {}).get("speed", NARRATION_SPEED))]
    for s in ((plan or {}).get("speakers") or {}).values():
        vals.append(float(s.get("speed", NARRATION_SPEED)))
    return vals
