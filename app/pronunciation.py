"""한국어 연음·발음 교정 사전.

대본에 쓴 글자는 자막에 그대로 나가고, TTS 로 읽을 때만 사전을 적용한다.
`발음사전.txt` 를 고치면 다음 줄부터 바로 반영된다.
"""
from __future__ import annotations

import re
from functools import lru_cache

from .paths import PRON_PATH

DEFAULT_DICT = """# 세월의 사연극장 발음 사전
# 형식:  원문  →  읽을 소리      (화살표 앞뒤 공백은 있어도 없어도 됨)
# 자막에는 원문이 그대로 나가고, 성우 음성만 이 사전대로 읽습니다.
앞에서 → 아페서
뒤에서 → 뒤에서
옷이 → 오시
옷을 → 오슬
꽃이 → 꼬치
꽃을 → 꼬츨
꽃잎 → 꼬칩
밭에 → 바테
낮에 → 나제
값이 → 갑씨
값어치 → 갑써치
없어서 → 업써서
없었다 → 업썯따
있었다 → 이썯따
같이 → 가치
굳이 → 구지
삶이 → 살미
젊어서 → 절머서
읽었다 → 일걷따
몇이 → 며치
힘없이 → 히멉씨
밥을 → 바블
집에 → 지베
꺼내 → 꺼내
덮었다 → 더펃따
벗었다 → 버섣따
쌓였다 → 싸였다
놓았다 → 노아따
많이 → 마니
앉아 → 안자
닭 → 닥
흙 → 흑
"""


def ensure_pron_file() -> None:
    if not PRON_PATH.exists():
        PRON_PATH.write_text(DEFAULT_DICT, encoding="utf-8")


@lru_cache(maxsize=1)
def _dict_mtime() -> float:
    try:
        return PRON_PATH.stat().st_mtime
    except OSError:
        return 0.0


@lru_cache(maxsize=8)
def load_pron_dict(_mtime: float = 0.0) -> tuple[tuple[str, str], ...]:
    ensure_pron_file()
    entries: list[tuple[str, str]] = []
    try:
        for raw in PRON_PATH.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            for sep in ("→", "->", "=", "\t"):
                if sep in line:
                    src, dst = line.split(sep, 1)
                    src, dst = src.strip(), dst.strip()
                    if src and dst:
                        entries.append((src, dst))
                    break
    except Exception:
        pass
    entries.sort(key=lambda x: len(x[0]), reverse=True)
    return tuple(entries)


def current_dict() -> tuple[tuple[str, str], ...]:
    return load_pron_dict(_dict_mtime())


TAG_RE = re.compile(r"\[[^\]]{1,20}\]")
EMOJI_RE = re.compile(
    "[\U0001F300-\U0001FAFF\U00002600-\U000027BF\U0001F1E6-\U0001F1FF\uFE0F]"
)


def strip_tags(text: str) -> str:
    """대본의 [문 쾅] 같은 효과음 태그를 걷어낸다."""
    return TAG_RE.sub(" ", text or "")


def apply_pron(text: str) -> str:
    out = text
    for src, dst in current_dict():
        if src in out:
            out = out.replace(src, dst)
    return out


def tts_text(text: str) -> str:
    """TTS 로 보낼 최종 문자열."""
    t = strip_tags(text)
    t = EMOJI_RE.sub(" ", t)
    t = t.replace("…", ", ").replace("···", ", ").replace("·", " ")
    t = re.sub(r"[~〜]+", " ", t)
    t = re.sub(r"[“”\"']", "", t)
    t = re.sub(r"\s+", " ", t).strip()
    t = apply_pron(t)
    return t


def _wrap_words(text: str, max_chars: int) -> list[str]:
    words = text.split()
    lines: list[str] = []
    cur = ""
    for w in words:
        while len(w) > max_chars:
            if cur:
                lines.append(cur)
                cur = ""
            lines.append(w[:max_chars])
            w = w[max_chars:]
        if not w:
            continue
        if not cur:
            cur = w
        elif len(cur) + 1 + len(w) <= max_chars:
            cur = cur + " " + w
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines or [""]


def subtitle_text(text: str, max_chars: int = 12) -> list[str]:
    """자막용 줄바꿈. 띄어쓰기 기준으로 10~14자 안에서 끊고 최대 3줄."""
    t = strip_tags(text).strip()
    t = re.sub(r"\s+", " ", t)
    if not t:
        return [""]
    lines = _wrap_words(t, max_chars)
    if len(lines) <= 3:
        return lines
    # 3줄을 넘으면 뒤를 앞 줄에 억지로 붙이지 않고, 호출부가 시간을 나눠 여러 자막으로 보낸다.
    return lines[:3]
