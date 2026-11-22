"""화자(speaker) 자동 배정 — AI 대본이 '해설'로 뭉갠 인물 대사를 되돌린다 (v2.0.2).

AI(Gemini·OpenAI)가 대본을 쓰면 두 가지 일이 자주 생긴다.
  1) 인물이 직접 말하는 대사(`"어머니, 이게 대체 무슨 말이야?"`)까지 `speaker: "narrator"`
     로 적어, 그 대사가 해설자 목소리로 읽힌다.
  2) 반대로 `speaker: "어머니"` / `"며느리"` / `"son"` 처럼 인물 이름을 적어, 배역 목록에
     없는 이름이라 해설(narrator)로 뭉개진다.

이 모듈은 그 둘을 한 곳에서 해결한다.
  · `resolve_speaker()`  — 인물 이름·호칭·나이·성별을 표준 배역 6종
    (narrator · old_male · old_female · female · young_male · child)으로 확정한다.
  · `looks_like_dialogue()` — 대사인지 아닌지 판별한다(따옴표·직접 호칭·말투 어미).
  · `assign_dialogue_speakers()` — 해설로 적힌 대사 장면을 문맥상 말한 인물로 돌린다
    (훅·되감기·예고·엔딩 같은 고정 장면은 건드리지 않는다).

배역 이름은 app/tts.py 의 목소리 표(project_voice_plan)가 그대로 쓰는 값이라,
여기서 확정해 두면 해설과 인물이 같은 목소리로 읽히는 일이 없어진다.
"""
from __future__ import annotations

import re
from typing import Iterable, Optional

from .honorifics import HONORIFIC_GROUPS

# 같은 사람을 부르는 다른 말 — '엄마'로 불러도 인물 이름 '어머니 순자'를 찾는다
_HONORIFIC_SAME: dict[str, set[str]] = {}
for _head, _variants in HONORIFIC_GROUPS:
    _group = set(_variants)
    for _v in _group:
        _HONORIFIC_SAME[_v] = _group

# 표준 배역 6종 — tts.py 의 OPENAI_VOICE_MAP 과 같은 키
SPEAKER_ROLES = ("narrator", "old_male", "old_female", "female", "young_male", "child")

# 해설로 보는 이름
NARRATOR_WORDS = frozenset({
    "narrator", "narr", "narration", "내레이션", "나레이션", "해설", "해설자", "해설역", "서술",
})

# 인물 호칭 → 배역 (이름·나이 정보가 없을 때의 기본값)
ROLE_WORDS = {
    "어머니": "old_female", "어머님": "old_female", "엄마": "old_female", "엄니": "old_female",
    "모친": "old_female", "할머니": "old_female", "할머님": "old_female", "할매": "old_female",
    "시어머니": "old_female", "시모": "old_female", "장모": "old_female", "외할머니": "old_female",
    "이모": "old_female", "고모": "old_female", "아주머니": "old_female", "아줌마": "old_female",
    "아버지": "old_male", "아버님": "old_male", "아빠": "old_male", "부친": "old_male",
    "할아버지": "old_male", "할아버님": "old_male", "할배": "old_male",
    "시아버지": "old_male", "시부": "old_male", "장인": "old_male", "외할아버지": "old_male",
    "삼촌": "old_male", "작은아버지": "old_male", "큰아버지": "old_male",
    "아들": "young_male", "아드님": "young_male", "아들내미": "young_male",
    "남편": "young_male", "신랑": "young_male", "사위": "young_male", "오빠": "young_male",
    "형": "young_male", "형님": "young_male", "청년": "young_male", "남자": "young_male",
    "남성": "young_male", "남": "young_male", "아저씨": "young_male",
    "며느리": "female", "며느님": "female", "며느리년": "female", "딸": "female",
    "따님": "female", "아내": "female", "부인": "female", "와이프": "female",
    "누나": "female", "언니": "female", "올케": "female", "시누이": "female",
    "여자": "female", "여성": "female", "여": "female", "아가씨": "female",
    "아이": "child", "아이들": "child", "어린이": "child", "손자": "child", "손녀": "child",
    "아기": "child", "학생": "child", "꼬마": "child",
}
# 긴 낱말부터 맞춰야 '며느님'이 '며느리'로 깨지지 않는다
_ROLE_WORDS_LONG_FIRST = sorted(ROLE_WORDS.items(), key=lambda kv: len(kv[0]), reverse=True)

FEMALE_WORDS = ("어머니", "어머님", "엄마", "모친", "할머니", "시어머니", "장모", "이모", "고모",
                "며느리", "딸", "아내", "부인", "누나", "언니", "올케", "시누이", "여성", "여자",
                "아가씨", "손녀", "여")
MALE_WORDS = ("아버지", "아버님", "아빠", "부친", "할아버지", "시아버지", "장인", "삼촌",
              "아들", "남편", "신랑", "사위", "오빠", "형", "청년", "남성", "남자", "아저씨",
              "손자", "남")


# ── 나이·성별 ─────────────────────────────────────────────────────────────
def parse_years(age) -> Optional[int]:
    """'70대 후반', '78세', '8세', '40대 초반' → 대표 나이(정수)."""
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
    m = re.search(r"(\d{1,3})", t)
    if m:
        v = int(m.group(1))
        if 0 < v <= 110:
            return v
    return None


def norm_gender(gender) -> str:
    """male/female/남/여/남성/여성/아들/어머니… → 'male' | 'female' | ''."""
    t = str(gender or "").strip().lower()
    if not t:
        return ""
    if t in ("male", "m", "man", "boy", "남", "남자", "남성"):
        return "male"
    if t in ("female", "f", "woman", "girl", "여", "여자", "여성"):
        return "female"
    if any(k in t for k in ("female", "woman", "girl", "여성", "여자", "아가씨")):
        return "female"
    if any(k in t for k in ("male", "man", "boy", "남성", "남자")):
        return "male"
    if any(w in t for w in MALE_WORDS):
        return "male"
    if any(w in t for w in FEMALE_WORDS):
        return "female"
    return ""


def role_for(gender: str = "", years: Optional[int] = None) -> str:
    """나이·성별 → 배역. 60대 이상은 노인/할머니, 12세 이하는 아이."""
    g = norm_gender(gender)
    if years is not None and years <= 12:
        return "child"
    if g == "male":
        return "old_male" if (years is not None and years >= 60) else "young_male"
    if g == "female":
        return "old_female" if (years is not None and years >= 60) else "female"
    return ""


def _role_from_words(text: str) -> str:
    """호칭 낱말이 들어 있으면 그 배역(긴 낱말 우선)."""
    body = str(text or "")
    if not body:
        return ""
    for word, role in _ROLE_WORDS_LONG_FIRST:
        if word in body:
            return role
    return ""


# ── 인물 목록 ─────────────────────────────────────────────────────────────
def character_list(characters: Optional[Iterable]) -> list[dict]:
    """대본의 characters 항목을 id·name·relation·age·gender 로 정리한다."""
    out: list[dict] = []
    for c in (characters or []):
        if not isinstance(c, dict):
            continue
        cid = str(c.get("id") or "").strip()
        name = str(c.get("name") or "").strip()
        if not (cid or name):
            continue
        out.append({
            "id": cid, "name": name,
            "relation": str(c.get("relation") or "").strip(),
            "age": str(c.get("age") or "").strip(),
            "gender": norm_gender(c.get("gender")),
            "tone": str(c.get("tone") or c.get("desc") or "").strip(),
            "words": " ".join(x for x in (cid, name, str(c.get("relation") or "")) if x),
        })
    return out


def match_character(raw: str, characters: Optional[Iterable]) -> Optional[dict]:
    """화자 이름이 인물 목록의 누구인지 찾는다(id·이름 정확히 → 이름 안의 호칭)."""
    key = str(raw or "").strip()
    if not key:
        return None
    low = key.lower()
    chars = character_list(characters)
    for c in chars:                       # id·이름이 그대로
        if low and low in (c["id"].lower(), c["name"].lower()):
            return c
    for c in chars:                       # '며느리 미경' 처럼 이름에 호칭이 들어 있는 경우
        # relation 은 보지 않는다 — '아들의 어머니' 같은 설명에 다른 인물이 걸린다
        if key and key in c["name"]:
            return c
    for c in chars:                       # 반대 방향: '어머니 김순자' → 인물 '어머니'
        if c["name"] and any(tok == c["name"] for tok in key.split()):
            return c
    return None


def _role_of_character(c: dict) -> str:
    return (role_for(c.get("gender") or "", parse_years(c.get("age")))
            or _role_from_words(c.get("words") or ""))


# ── 화자 확정 ─────────────────────────────────────────────────────────────
def is_narrator(raw) -> bool:
    t = str(raw or "").strip()
    return (not t) or t.lower() in NARRATOR_WORDS


def resolve_speaker(raw, characters: Optional[Iterable] = None, age="", gender=""
                    ) -> tuple[str, str]:
    """화자 표기 → (표준 배역, 화면에 보여 줄 이름).

    `"어머니"`/`"며느리"`/`"son"` 처럼 인물 이름으로 적혀 있어도 배역으로 바꾸고,
    모르는 이름이면 narrator 로 되돌린다(이때는 호출부가 대사 판별로 다시 본다).
    """
    text = str(raw or "").strip()
    if is_narrator(text):
        return "narrator", ""
    low = text.lower()
    if low in SPEAKER_ROLES:
        return low, ""
    c = match_character(text, characters)
    if c:
        role = _role_of_character(c) or role_for(gender, parse_years(age))
        if role:
            return role, c["name"] or text
    role = _role_from_words(text)
    if role:
        return role, text
    role = role_for(gender, parse_years(age))
    if role:
        return role, text
    return "narrator", ""


# ── 대사 판별 ─────────────────────────────────────────────────────────────
QUOTE_PAIRS = (('"', '"'), ("“", "”"), ("‘", "’"), ("'", "'"), ("「", "」"), ("『", "』"))

# 직접 호칭으로 시작하는 대사 — 뒤에 쉼표/느낌표가 있어야 대사로 본다
VOCATIVES = ("어머니", "어머님", "엄마", "엄니", "아버지", "아버님", "아빠",
             "할머니", "할머님", "할아버지", "할아버님", "시어머니", "시아버지",
             "아들아", "아들", "딸아", "딸", "며느리야", "며느리", "여보", "자기야",
             "오빠", "언니", "누나", "형", "형님", "삼촌", "이모", "고모", "아가", "얘")
VOCATIVE_RE = re.compile(r"^(?:" + "|".join(sorted(VOCATIVES, key=len, reverse=True)) + r")\s*[,!]\s*")
# 이름을 부르는 말 — '정호야,', '수진아,' (2~5글자 이름 + 야/아 + 쉼표)
NAME_VOCATIVE_RE = re.compile(r"^([가-힣]{2,5})(?:야|아)\s*[,!]\s*")

# 대답·감탄으로 시작하면 대사
RESPONSE_RE = re.compile(
    r"^(?:네|예|아니|아니요|아뇨|그래|그래요|그럼|아이고|아이고나|어머|어머나|세상에|아무리|"
    r"잠깐|저기|실례|미안|미안해|고맙|고마워|괜찮|됐어|싫어|좋아|맞아|글쎄|원래|참|제가|내가|"
    r"당신|너|넌|난|나는|나도|우리)\s*[,.]?"
)

# 해설 문장의 끝 (이 어미로 끝나면 서술로 본다)
NARRATION_ENDINGS = ("습니다", "ㅂ니다", "ㅁ니다", "입니다", "였다", "했다", "었다", "았다",
                     "보였다", "들렸다", "났다", "같았다", "싶었다", "몰랐다", "알았다",
                     "있었다", "없었다", "되었다", "졌다", "렸다")

# 말투로 끝나는 어미 — 대사
SPOKEN_ENDINGS = ("요", "죠", "세요", "해줘", "줘", "봐", "냐", "니", "잖아", "거든", "라니까",
                  "거야", "거지", "이야", "래", "래요", "마", "자", "군", "구나", "는데",
                  "다면서", "더라", "냐고", "단다", "란다", "으라고", "지 마", "줄래", "을래",
                  "실래", "어때", "괜찮아", "미안해", "고마워", "싫어", "좋아", "몰라", "알아",
                  "없어", "있어", "겠어", "올까", "될까", "하네", "네", "어")

# 문장 끝 장식 — 어미를 볼 때는 떼고 본다
_TAIL_CHARS = " .…‥·,!?~\"'”“’」』"


def _strip_quotes(text: str) -> str:
    t = str(text or "").strip()
    for a, b in QUOTE_PAIRS:
        if len(t) >= 2 and t.startswith(a) and t.endswith(b):
            return t[len(a):len(t) - len(b)].strip()
    return t


def _is_quoted(text: str) -> bool:
    t = str(text or "").strip()
    for a, b in QUOTE_PAIRS:
        if len(t) >= 4 and t.startswith(a) and t.endswith(b):
            return True
    return False


def address_word(text: str) -> str:
    """대사를 시작하는 직접 호칭('어머니,', '정호야,') — 듣는 사람을 가리킨다(말하는 사람이 아니다)."""
    body = _strip_quotes(text)
    m = VOCATIVE_RE.search(body)
    if m:
        return m.group(0).strip(" ,!")
    m = NAME_VOCATIVE_RE.search(body)
    return m.group(0).strip(" ,!") if m else ""


def looks_like_dialogue(text) -> tuple[bool, str]:
    """(대사인가, 들리는 사람 호칭). 해설 문장은 절대 대사로 보지 않는다."""
    raw = str(text or "").strip()
    if not raw:
        return False, ""
    if _is_quoted(raw):
        return True, address_word(raw)
    body = _strip_quotes(raw)
    if not body:
        return False, ""
    addr = address_word(body)
    if addr:
        return True, addr
    if "?" in body or "!" in body:
        return True, ""
    core = body.strip(_TAIL_CHARS).strip()
    if not core:
        return False, ""
    if RESPONSE_RE.match(body) and ("," in body[:12] or len(body) <= 40):
        return True, ""
    if core.endswith(NARRATION_ENDINGS):
        return False, ""
    if core.endswith(SPOKEN_ENDINGS):
        return True, ""
    return False, ""


# ── 문맥으로 말한 사람 고르기 ────────────────────────────────────────────
def _is_addressee(c: dict, addr: str) -> bool:
    """호칭이 가리키는 사람인가 — 이 사람은 '듣는 사람'이라 말한 사람이 아니다."""
    if not addr:
        return False
    # relation 은 보지 않는다 — '아들의 어머니'처럼 다른 사람이 걸린다
    words = [w for w in (c["id"], c["name"]) if w]
    forms = {addr} | _HONORIFIC_SAME.get(addr, set())
    if any(form in w for form in forms for w in words):
        return True
    # '정호야' → '정호' (이름을 부르는 말은 야/아를 떼고 본다)
    if len(addr) >= 3 and addr[-1] in "야아":
        stem = addr[:-1]
        if any(stem in w for w in words):
            return True
    return bool(c["name"] and c["name"].startswith(addr))


def speaker_for_line(text: str, characters: Optional[Iterable] = None, addr: str = "",
                     prev_role: str = "", scene: Optional[dict] = None
                     ) -> tuple[str, Optional[dict]]:
    """대사 한 줄을 말한 인물 — (배역, 인물 정보). 알 수 없으면 ('', None)."""
    sc = scene or {}
    chars = character_list(characters)
    mine_g = norm_gender(sc.get("speaker_gender") or "")
    mine_y = parse_years(sc.get("speaker_age"))

    # 장면에 적힌 나이·성별이 있으면 그것부터 (대본이 스스로 밝힌 정보)
    if mine_g:
        role = role_for(mine_g, mine_y)
        if role:
            cand = next((c for c in chars
                         if c["gender"] == mine_g and not _is_addressee(c, addr)), None)
            return role, cand

    cands = [c for c in chars if not _is_addressee(c, addr)]
    roles = {_role_of_character(c) for c in cands}
    roles.discard("")
    if len(cands) == 1 or len(roles) == 1:
        role = next(iter(roles), "") or (_role_of_character(cands[0]) if cands else "")
        if role:
            return role, (cands[0] if len(cands) == 1 else None)
    # 같은 사람이 계속 말하는 경우(문맥) — 그 사람이 이 대사의 듣는 사람이면 쓰지 않는다
    if prev_role:
        prev_char = next((c for c in chars if _role_of_character(c) == prev_role), None)
        if prev_char is None or not _is_addressee(prev_char, addr):
            same = next((c for c in cands if _role_of_character(c) == prev_role), None)
            return prev_role, same
    # 누구인지 분명하지 않으면 해설로 둔다(엉뚱한 목소리보다 낫다)
    return "", None


def assign_dialogue_speakers(scenes: list[dict], characters: Optional[Iterable] = None,
                             exclude_ids: Iterable[str] = ()) -> list[dict]:
    """장면 목록의 화자를 확정한다.

    · 인물 이름으로 적힌 화자(`어머니`·`며느리`·`son`)를 표준 배역으로 바꾼다.
    · 해설로 적혔지만 내용이 대사인 장면은 문맥상 말한 인물로 돌린다.
    · 고정 장면(되감기·예고·엔딩·디자인이 직접 넣은 훅 카드)은 건드리지 않는다 —
      `exclude_ids`, `placement`, `card` 가 붙은 장면.
      다만 이야기 앞부분(훅 구간)이라도 모델이 쓴 장면의 호칭·대사가 분명하면 살린다.
    """
    exclude = {str(x) for x in (exclude_ids or ())}
    prev_role = ""
    for sc in (scenes or []):
        if not isinstance(sc, dict):
            continue
        fixed = (str(sc.get("id") or "") in exclude or bool(sc.get("placement"))
                 or bool(sc.get("card")) or bool(sc.get("hook_line")))
        text = str(sc.get("text") or "")
        role, name = resolve_speaker(sc.get("speaker"), characters,
                                     age=sc.get("speaker_age"), gender=sc.get("speaker_gender"))
        if fixed:
            if role != "narrator":
                sc["speaker"] = role
                if name:
                    sc["speaker_name"] = name
                prev_role = role
            continue
        if role == "narrator":
            is_line, addr = looks_like_dialogue(text)
            if is_line:
                guess, char = speaker_for_line(text, characters, addr, prev_role, sc)
                if guess:
                    role, name = guess, (char or {}).get("name", "") or ""
                    sc["speaker_auto"] = True
                    if char:
                        if not str(sc.get("speaker_age") or "").strip() and char.get("age"):
                            sc["speaker_age"] = char["age"]
                        if not str(sc.get("speaker_gender") or "").strip() and char.get("gender"):
                            sc["speaker_gender"] = char["gender"]
        sc["speaker"] = role
        if name:
            sc["speaker_name"] = name
        if role != "narrator":
            prev_role = role
    return scenes
