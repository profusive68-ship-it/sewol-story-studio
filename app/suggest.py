"""시나리오 추천 — 1단계 [✨ 시나리오 추천받기] 버튼이 쓰는 주제·훅 3~5개.

AI(Gemini → OpenAI 자동 보조)에게 시니어 라디오 드라마에 맞는 주제·첫 훅·한 줄 이유를
JSON 으로 받는다. 키가 없거나 호출이 실패하면 미리 쌓아 둔 아이디어 은행에서 골라
화면이 비지 않게 한다(대본 생성과 같은 '키 없으면 예시' 원칙).
"""
from __future__ import annotations

import json
import random

from .gemini_script import candidate_engines, _call
from .settings import GENRES, FORMAT_PRESETS

IDEA_BANK = {
    "tear_family": [
        {"topic": "어머니의 마지막 김치통", "hook": "장례식 다음 날, 냉장고 맨 아래 김치통에서 낡은 통장이 나왔다.",
         "why": "물증(통장) 하나로 가족의 오해가 풀리는 눈물형"},
        {"topic": "아버지의 낡은 손목시계", "hook": "시계 뒤 뚜껑을 열자 사진 한 장이 접혀 있었다.",
         "why": "한 사물에 숨은 비밀로 시작하는 가족 감동"},
        {"topic": "형의 등기부등본", "hook": "형이 죽은 뒤, 집 주인이 동생이 되어 있었다.",
         "why": "재산 문제로 갈라진 형제의 오래된 진심"},
        {"topic": "딸이 보낸 마지막 문자", "hook": "삭제하지 못한 문자 한 줄이 7년을 뒤집었다.",
         "why": "휴대폰 하나로 이어지는 부모와 자식의 그리움"},
        {"topic": "경로당 국밥집 사장님", "hook": "값을 안 받던 국밥집 아저씨가 사실은 아버지의 옛 은인이었다.",
         "why": "지역 생활 공간에서 시작하는 따뜻한 인연"},
    ],
    "reversal": [
        {"topic": "며느리의 반격", "hook": "10년을 무시한 시어머니가 며느리 명의 집에서 쫓겨났다.",
         "why": "고구마 → 사이다 구조가 가장 선명한 시댁 소재"},
        {"topic": "하청업체 사장의 승부수", "hook": "갑질하던 대기업이 하청업체 기술에 목을 매게 됐다.",
         "why": "직장 갑질을 통쾌하게 뒤집는 사이다"},
        {"topic": "전 남편의 재산 명세서", "hook": "이혼 서류에 빠뜨린 빚 3억이 이혼한 남편 몫으로 돌아갔다.",
         "why": "숨긴 재산이 드러나는 통쾌한 반전"},
        {"topic": "학부모회장의 장부", "hook": "불우이웃 돕기라던 통장에 회장의 명품 영수증이 들어 있었다.",
         "why": "고발형 사이다 — 시니어가 좋아하는 현실 통쾌"},
        {"topic": "세입자의 마지막 통화", "hook": "집주인이 해지 통보를 마친 뒤, 그 집 주인이 세입자였다.",
         "why": "권력이 뒤집히는 반전 구조"},
    ],
    "mystery": [
        {"topic": "택배 상자 안 감사 편지", "hook": "20년 전 사과와 감사가 담긴 편지가 택배로 도착했다.",
         "why": "한 장의 편지로 시작하는 휴먼 반전"},
        {"topic": "경매 나온 낡은 사진관", "hook": "집을 넘겨받은 사진관 액자 속 주인장이 나를 보고 있었다.",
         "why": "사진 한 장이 푸는 미지의 사람 사연"},
        {"topic": "정류장 시계 수리공", "hook": "버스 정류장 시계를 30년 만에 고쳤더니 막내가 돌아왔다.",
         "why": "동네 공간과 사물이 이어 주는 기적"},
        {"topic": "장례식장 손님 명부", "hook": "치른 적 없는 장례식 명부에 내 이름이 적혀 있었다.",
         "why": "시작부터 강한 후킹 — 미스터리 몰입"},
        {"topic": "당첨된 쓰레기 투표권", "hook": "폐지 더미에서 나온 20년 전 투표권 한 장이 이사 결정을 바꿨다.",
         "why": "작은 물건에서 시작해 사람의 결말을 바꾸는 사연"},
    ],
    "inlaw": [
        {"topic": "시어머니의 미역국", "hook": "30년 만에 처음 끓인 미역국에 소금 대신 눈물이 들어갔다.",
         "why": "갈등 뒤 화해로 가는 시니어 정서"},
        {"topic": "명절 상차림 예고", "hook": "출가한 며느리가 없던 이유를 시어머니가 혼자 고백했다.",
         "why": "명절 갈등을 다른 각도로 비트는 반전"},
        {"topic": "남편의 카톡 단체방", "hook": "가족 단체방에서 나만 빠져 있었다.",
         "why": "부부·시댁 갈등의 현실 디테일"},
        {"topic": "사위의 손편지", "hook": "재산 하나 없는 사위가 20년 묵은 빚을 갚아 왔다.",
         "why": "무시받던 사람이 뒤집는 사이다"},
        {"topic": "장모님과 마지막 식사", "hook": "장모가 남긴 메모 한 줄로 두 집안이 다시 모였다.",
         "why": "갈등 끝의 화해 — 썸네일 밥그릇 그림이 잘 먹힘"},
    ],
    "free": [
        {"topic": "70세 첫 자전거 여행", "hook": "61년 만에 자전거를 샀더니 아내의 편지가 따라왔다.",
         "why": "나이를 뛰어넘는 산뜻한 사연"},
        {"topic": "폐업 앞둔 목욕탕", "hook": "마지막 손님이 50년 전 단골과 같은 장갑을 냈다.",
         "why": "문 닫는 공간에서 피는 사람 이야기"},
        {"topic": "씨름 선수의 오래된 수건", "hook": "수건 가슴에 박힌 장백이 40년 만에 밝혀졌다.",
         "why": "지역 인물·봉사 정서"},
        {"topic": "우편함의 엉뚱한 주소", "hook": "티핑 주소로 온 봉투 하나가 30년 잠든 말을 깨웠다.",
         "why": "비현실적 우연도 잘 삼켜지는 사연"},
        {"topic": "논두렁의 은행나무", "hook": "나무를 베겠다는 날, 70년 전 이름표가 나왔다.",
         "why": "자연·고향 정서"},
    ],
}


def _fallback(genre: str, count: int, seed: int = 0) -> list[dict]:
    bank = IDEA_BANK.get(genre) or IDEA_BANK["tear_family"]
    pool = list(bank)
    rng = random.Random(seed or 0)
    rng.shuffle(pool)
    out = []
    for idea in pool[:max(1, min(5, count))]:
        out.append({"topic": idea["topic"], "hook": idea["hook"], "why": idea["why"],
                    "genre": genre, "source": "template"})
    return out


def _prompt(settings: dict, count: int) -> str:
    genre = settings.get("genre") or "tear_family"
    preset = settings.get("preset") or "short50"
    fmt = FORMAT_PRESETS.get(preset, {})
    return (
        "세월의 사연극장(한국 시니어 시청자용 라디오 드라마)에 올릴 다음 사연 아이디어를 "
        f"{count}개 추천해 주세요.\n"
        f"· 사연 종류: {GENRES.get(genre, {}).get('label', genre)}\n"
        f"· 영상 길이: {fmt.get('label', preset)} ({fmt.get('target', 50)}초)\n"
        "· 시청자는 60~80대입니다. 어려운 한자어·영어·통계는 쓰지 않습니다.\n"
        "· 각 아이디어는 첫 3초에 멈추게 하는 '훅'이 있어야 합니다(인사·소개 금지).\n"
        "· 한 편의 사연으로 완결되어야 하고, 제목만 봐도 어떤 사건인지 보여야 합니다.\n\n"
        "아래 JSON 형식으로만 답하세요. (다른 말 금지)\n"
        '{"ideas": [{"topic": "제목처럼 짧은 주제", "hook": "첫 문장 훅 한 줄", '
        '"why": "왜 시니어가 좋아할지 한 줄"}]}'
    )


def suggest_ideas(settings: dict | None = None, cfg: dict | None = None,
                  count: int = 5, seed: int | None = None) -> dict:
    """주제·훅 3~5개. 반환: {ok, ideas, engine, message}"""
    settings = dict(settings or {})
    cfg = cfg or {}
    count = max(3, min(5, int(count or 5)))
    genre = str(settings.get("genre") or "tear_family")
    if genre not in GENRES:
        genre = "free"
        settings["genre"] = genre
    engines = candidate_engines(cfg)
    if engines:
        try:
            data = _call(cfg, _prompt(settings, count), temperature=0.95)
            raw = data.get("ideas") if isinstance(data, dict) else None
            ideas = []
            for item in raw or []:
                if not isinstance(item, dict):
                    continue
                topic = " ".join(str(item.get("topic") or "").split())[:60]
                hook = " ".join(str(item.get("hook") or "").split())[:160]
                why = " ".join(str(item.get("why") or "").split())[:120]
                if len(topic) < 2 or len(hook) < 6:
                    continue
                ideas.append({"topic": topic, "hook": hook, "why": why,
                              "genre": genre, "source": "ai"})
            if ideas:
                return {"ok": True, "ideas": ideas[:count], "genre": genre,
                        "engine": "ai",
                        "message": f"AI가 사연 {len(ideas[:count])}개를 추천했습니다. 눌러서 주제에 넣으세요."}
        except Exception as e:
            fallback = _fallback(genre, count, seed or 0)
            return {"ok": True, "ideas": fallback, "genre": genre, "engine": "template",
                    "message": f"AI 추천이 막혀 예시 아이디어로 채웠습니다. ({str(e)[:120]})"}
    return {"ok": True, "ideas": _fallback(genre, count, seed or 0), "genre": genre,
            "engine": "template",
            "message": "API 키가 없어 예시 아이디어로 채웠습니다. 키를 저장하면 AI 추천으로 바뀝니다."}
