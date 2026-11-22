"""Gemini 2단계 대본 엔진.

1단계(설계): 구체적 생활 물증 + 5막 복선·반전 뼈대 + 첫 15초 훅을 먼저 확정한다.
2단계(집필): 확정된 뼈대를 장(章)별로 나누어, 일본어 번역투를 배제한 한국 생활
              디테일·인물 직접 대화·효과음 태그로만 쓴다.

오프닝은 언제나 콜드 오픈이다. 채널 인사·사연 소개로 시작하지 않고 0초부터
가장 충격적인 대사/사건 한복판에서 시작한다(첫 15초 반전 훅).
채널 구독·지역 댓글 안내는 영상 맨 끝 엔딩에만 둔다(project.py 에서 마지막 장면으로 붙임).
"""
from __future__ import annotations

import json
import re
import time
from typing import Callable

from .settings import GENRES, FORMAT_PRESETS

SFX_VOCAB = ["문 쾅", "문 닫기", "문 삽입", "문 삐걱", "찻잔", "숟가락", "한숨",
             "심장박동", "발자국", "비", "바람", "바람 창", "새소리", "종", "전화벨",
             "핸드폰 진동", "종이 넘김", "종이 바스락", "천 바스락", "가쁜 숨", "헉", "놀람 숨",
             "숨죽임", "병원 룸톤", "냄비 보글", "장판", "상자", "가방", "테이프",
             "침대 시트", "냉장고 웅웅", "뚜껑 열림", "박수", "울음"]
EMOTIONS = ["conflict", "twist", "heal"]
SPEAKERS = ("narrator", "old_male", "old_female", "female", "young_male", "child")

SYSTEM_RULES = """너는 한국 시니어 라디오 드라마 전문 작가다. 아래는 절대 규칙이다.

[대화 비중 — 최우선]
- 해설(narrator)만 길게 이어 쓰지 않는다. 전체 대사 중 **인물 간의 직접 대화(생생한 구어체 대사)를 약 30~40% 비중**으로
  자연스럽게 섞는다. 해설로 상황을 요약하기 전에, 그 자리에서 사람들이 실제로 주고받을 말을 먼저 내놓는다.
- 인물 대사는 그 사람의 나이·성별·성격·지금 처한 상황이 말투에 배어 나오게 쓴다.
- 인물이 말하는 장면마다 그 대사의 화자 정보를 함께 적는다:
    "speaker_age": "70대 후반" 처럼 나이(예: "78세", "30대 초반", "8세"),
    "speaker_gender": "male" 또는 "female",
    "speaker_tone": "다정하지만 기력이 약한 병상의 노모" 처럼 성격·처지·지금 감정을 한 줄로.
  이 정보는 그 장면의 음성 연기(목소리 톤·속도)에 그대로 쓰인다. 해설(narrator) 장면에는 넣지 않는다.

[콜드 오픈 — 최우선]
- '안녕하세요', '세월의 사연극장입니다', '오늘의 사연은', '어서 오세요' 같은 인사·채널 소개·사연 예고로 시작하지 않는다.
- 첫 장면 첫 대사는 가장 충격적인 사건·대사 한복판이어야 한다. 청취자가 "어? 뭐지?" 하고 멈추는 첫 문장.
- 첫 15초 안에 반전의 실마리(물증, 배신, 고백, 발견)가 터진다. 그 뒤에 시간을 되돌려 본론으로 들어간다.
- 채널 구독·지역 댓글 안내는 영상 맨 끝에서만 언급한다(중간·开头 금지).

[문체]
- 한국인이 실제로 말하는 구어체. 일본어 번역투를 절대 쓰지 않는다.
  금지 예: '~에 대하여', '~에 있어서', '~하는 것이 가능하다', '~되어진다', '~라고 하는', '~의 경우',
  '그녀는/그는' 남발, '당신', '~씨' 남발, '~해 주었습니다' 반복, '~한 것으로 보인다', '~라는 사실을 알게 되었다'.
- 인물은 이름·호칭(엄마, 어머니, 형님, 순자 씨가 아니라 '순자야/순자 언니')으로 부른다.
- 문장은 15~45자 중심으로 짧게 끊고, 능동형으로 쓴다. 번역체 긴 문장 금지.
- 대사는 따옴표 없이 text 에 그대로 넣는다. 해설은 담담하게, 인물 대사는 그 사람 말투로.
- 60~80대가 한 번에 알아듣는 쉬운 낱말. 어려운 한자어·전문용어·영어 금지.

[한국 생활 디테일]
- 돈·물건·장소는 실제처럼 구체적으로: 국민은행 통장, 경로당, 아파트 관리비 고지서, 시장 국밥집,
  버스 정류장, 병원 접수증, 카톡 단체방, 김치통, 다이어리, 사진관, 복지관, 제사상, 손주 학원비.
- 사연마다 '생활 물증'을 최소 1개 이상 이야기의 축으로 삼는다(영수증, 통장, 녹음, 편지, 사진, 진단서, 문자).

[제목·설명 — 유튜브 조회수 공식]
- 제목은 시니어 롱폼 고조회수 공식([억울함/갈등 상황] + [결정적 행동/단서] + [충격 반전])을 따른다.
  예: "며느리라 무시했는데, 등기부등본 한 장에 집안이 뒤집혔다".
- 25~40자, 앞부분에 후킹 단어. 숫자·고유명사(김치통·통장·등기부등본)를 넣는다. 낚시성 과장·대문자 남발 금지.
- 제목 3안은 서로 다른 각도(① 사건 중심 ② 인물 감정 중심 ③ 반전 결과 중심)로 쓴다.
- 설명문은 줄거리 3~5줄(결말 스포일러는 최소), 구독·사연 제보 안내 1~2줄, 해시태그 8~10개.
- 해시태그는 실제 검색되는 것: #사연 #라디오드라마 #감동사연 #사이다 #가족사연 #시니어 #노인사연 #실화같은이야기 등.

[형식]
- 화자: narrator, old_male, old_female, female, young_male, child 중 하나.
  인물 대사 장면에는 speaker_age(나이 문자열)·speaker_gender("male"|"female")·speaker_tone(성격·상황 한 줄)을 반드시 함께 넣는다.
- 감정: conflict(갈등), twist(반전), heal(치유) 중 하나.
- 효과음 sfx: 다음 목록에서만 0~2개. 대사에 [문 쾅] 같은 태그를 직접 쓰지 말고 sfx 배열에 넣는다.
  목록: """ + ", ".join(SFX_VOCAB) + """
- image_prompt 는 영어. 인물의 나이·머리·옷을 매 장면 똑같이 반복해 얼굴 일관성을 지킨다.
  영화 스틸 같은 사실적 사진, 조명·장소·표정 구체적으로. 화면 안 글자 금지(no text, no letters, no logo).
- characters 의 각 인물에는 age(예: "78세", "40대 후반")와 gender("male"|"female")도 함께 적는다.
- image_caption 은 한국어 한 줄(25자 내외).
"""


def _client(cfg: dict):
    key = (cfg.get("gemini_api_key") or "").strip()
    if not key:
        raise RuntimeError("Gemini API 키가 없습니다.")
    try:
        from google import genai  # 설치된 경우에만
    except ImportError as e:
        raise RuntimeError("google-genai 가 설치되지 않았습니다. (pip install google-genai)") from e
    return genai.Client(api_key=key)


# ── 모델 재시도·폴백 ───────────────────────────────────────────────────────
# settings.json 에 옛 모델(gemini-2.5-flash)이 저장돼 있어도 최신 모델을 먼저 시도한다.
PREFERRED_MODEL = "gemini-3.8-flash"
LEGACY_MODELS = {"gemini-2.5-flash", "gemini-1.5-flash", "gemini-2.5-flash-preview",
                 "gemini-2.0-flash-lite", "gemini-1.0-pro"}
MODEL_FALLBACKS = ("gemini-2.5-flash-lite", "gemini-2.0-flash", "gemini-2.5-flash")
RETRY_SECONDS = 1.5
BUSY_HINTS = ("503", "429", "UNAVAILABLE", "RESOURCE_EXHAUSTED", "overloaded",
              "high demand", "try again", "service unavailable", "exceeded")
NOT_FOUND_HINTS = ("404", "NOT_FOUND", "not found", "no longer available", "is not supported",
                   "does not exist", "was not found")
AUTH_HINTS = ("API key", "API_KEY", "api_key", "permission", "PERMISSION_DENIED",
              "401", "403", "UNAUTHENTICATED")


def _models(cfg: dict) -> list[str]:
    """시도할 모델 순서. 옛 주 모델이 저장돼 있으면 최신 모델을 맨 앞에 둔다."""
    primary = (cfg.get("text_model") or "").strip() or PREFERRED_MODEL
    cands: list[str] = []
    if primary in LEGACY_MODELS:
        cands.append(PREFERRED_MODEL)
    cands.append(primary)
    cands.extend(MODEL_FALLBACKS)
    cands.extend(m for m in (cfg.get("text_model_fallbacks") or []) if m)
    out: list[str] = []
    for m in cands:
        if m and m not in out:
            out.append(m)
    return out


def _err_text(e: Exception) -> str:
    return f"{type(e).__name__} {e}"


def call_gemini(cfg: dict, prompt: str, *, temperature: float = 0.9,
                response_json: bool = True, max_output_tokens: int | None = None,
                system: str | None = None, client=None) -> str:
    """Gemini 호출 — 503/429 는 1.5초 뒤 1회 재시도, 404 는 다음 모델로 폴백.

    돌려주는 값은 응답 텍스트. JSON 이 필요하면 response_json=True 로 두고
    받은 텍스트를 _extract_json 에 넘긴다.
    """
    try:
        from google.genai import types
    except ImportError:          # google-genai 없이도 테스트할 수 있게
        types = None
    client = client or _client(cfg)
    models = _models(cfg)
    last_err: Exception | None = None
    for model in models:
        for attempt in range(2):
            try:
                kw: dict = {"temperature": temperature}
                if response_json:
                    kw["response_mime_type"] = "application/json"
                if max_output_tokens:
                    kw["max_output_tokens"] = int(max_output_tokens)
                if system:
                    kw["system_instruction"] = system
                cfg_obj = types.GenerateContentConfig(**kw) if types else kw
                resp = client.models.generate_content(
                    model=model, contents=prompt, config=cfg_obj)
                return getattr(resp, "text", "") or ""
            except Exception as e:
                last_err = e
                msg = _err_text(e)
                if any(t in msg for t in AUTH_HINTS):
                    raise
                if any(t in msg for t in BUSY_HINTS) and attempt == 0:
                    time.sleep(RETRY_SECONDS)      # 일시 혼잡 → 1회만 재시도
                    continue
                if any(t in msg for t in NOT_FOUND_HINTS):
                    break                          # 404(모델 없음) → 다음 모델
                # 두 번째 혼잡 · 그 밖의 오류 → 다음 모델로
                break
    raise RuntimeError(f"Gemini 호출 실패(모델 {', '.join(models)}): {last_err}")


def _extract_json(text: str) -> dict:
    t = (text or "").strip()
    t = re.sub(r"^```(?:json)?\s*", "", t)
    t = re.sub(r"\s*```$", "", t)
    start, end = t.find("{"), t.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("JSON 을 찾지 못했습니다.")
    return json.loads(t[start:end + 1])


def _call(cfg: dict, prompt: str, temperature: float = 0.9) -> dict:
    text = call_gemini(cfg, prompt, temperature=temperature, response_json=True,
                       system=SYSTEM_RULES)
    return _extract_json(text)


# ── 1단계: 설계 ────────────────────────────────────────────────────────────
def _design_prompt(settings: dict, n_acts: int, n_chapters: int) -> str:
    target = float(settings["target_seconds"])
    chars = int(target * 4.3)
    fmt = FORMAT_PRESETS.get(settings.get("preset", "pilot5"), FORMAT_PRESETS["pilot5"])
    genre = GENRES.get(settings.get("genre", "tear_family"), GENRES["tear_family"])
    topic = (settings.get("topic") or "").strip() or "(없음 — 장르에 맞게 새로 정할 것)"
    return f"""〈세월의 사연극장〉 새 이야기 **1단계 설계**만 한다. 대사는 아직 쓰지 않는다.

- 사연 종류: {genre['label']} — {genre['hint']}
- 직접 적은 주제: {topic}
- 형식: {fmt['label']} · {fmt['aspect']} · 약 {int(target)}초(약 {chars}자)
- 막 구성: {n_acts}막 / 장 구성: {n_chapters}장
- 첫 15초 반전 훅: 반드시 켠다.
- 무대: 한국의 구체적인 동네(예: 제주 서귀포, 부산 사하구, 전주 완산구). 연도도 정한다.

반드시 아래를 확정한다.
1) **생활 물증 2~3개**: 이야기의 축이 되는 실제 물건. 이름만 쓰지 말고 종이 재질·잉크 색·금액·날짜처럼
   눈으로 보이는 디테일까지. 예: "2003년 3월 14일, 국민은행 통장. 3만 원 입금 옆 연필로 '호야 학원비'".
2) **5막 뼈대**: 발단-전개-위기-절정-결말. 각 막마다 '숨겨 둘 것(plant)'과 '터질 것(payoff)'을 짝지어
   복선이 회수되게 한다. 5막은 반드시 훅 장면(절정의 한복판)에서 시작해 시간을 되돌린다.
3) **훅 대사**: 0초에 나갈 첫 대사 한 줄(25자 내외). 인사·소개 금지. 가장 충격적인 말.
4) **되감기 자막**: 훅 직후 화면에 띄울 한 줄(예: "사흘 전, 아무것도 몰랐던 그날").
5) **장별 줄거리**: 각 장에서 무슨 일이 일어나는지 2문장. 어느 막에 속하는지.
6) **엔딩 떡밥 2종**: (a) sequel_teaser = 이번 사연의 '6개월 뒤'를 암시하는 복선 나레이션 2~3문장
   (새 인물·새 물증이 살짝 등장해 다음 이야기를 궁금하게), (b) next_story = 다음에 올릴 새 사연 제목과 예고 1~2문장.
7) 썸네일 문구와 업로드 카피.

JSON 만 출력:
{{
  "title": "대표 제목 25~35자",
  "titles": ["제목안1 (사건 중심)", "제목안2 (인물 감정 중심)", "제목안3 (반전 결과 중심)"],
  "logline": "한 줄 소개",
  "description": "유튜브 설명문 줄거리 3~5줄 (스포일러 최소)",
  "hashtags": ["#사연","#라디오드라마","#감동사연","#사이다","#가족사연","#시니어","#노인사연","#실화같은이야기"],
  "setting": "연도·지역·집/곳",
  "characters": [{{"id":"mother","name":"어머니 순자","relation":"주인공의 어머니","age":"78세",
                   "habit":"말끝을 흐리는 버릇","desc_en":"Korean grandmother, 78, silver hair in a low bun, faded floral apron, deep wrinkles, gentle tired eyes"}}],
  "evidence": [{{"item":"국민은행 통장","detail":"2003년 3월 14일, 3만 원 입금 옆 연필 메모 '호야 학원비'","meaning":"어머니가 몰래 넣어 준 돈","reveal_act":4}}],
  "acts": [{{"act":1,"name":"발단","summary":"...","plant":"...","payoff":"..."}}],
  "hook": {{"line":"0초에 나갈 충격 대사","situation":"그 장면 상황","rewind_caption":"사흘 전, 아무것도 몰랐던 그날"}},
  "chapters": [{{"index":1,"act":1,"title":"장 제목","beat":"이 장에서 일어날 일 2문장","pov":"중심 인물"}}],
  "sequel_teaser": "이번 사연 6개월 뒤 후속편 복선 2~3문장",
  "next_story": {"title": "다음 사연 제목", "teaser": "다음 사연 예고 1~2문장"},
  "thumbnail": {{"style1":["첫째 줄 8자 내외","둘째 줄 10자 내외"],
                "style2":["대화체 1","대화체 2","반전 한 줄","마지막 유도 한 줄"]}},
  "upload": {{"title":"유튜브 제목","description":"설명 3~5줄","tags":["태그","6개"]}}
}}
acts 는 정확히 {n_acts}개, chapters 는 정확히 {n_chapters}개."""


# ── 2단계: 집필 ────────────────────────────────────────────────────────────
def _write_prompt(settings: dict, design: dict, ch: dict, total_chars: int,
                  prev_tail: list[str], is_first: bool, is_last: bool,
                  scenes_hint: str) -> str:
    fmt = FORMAT_PRESETS.get(settings.get("preset", "pilot5"), FORMAT_PRESETS["pilot5"])
    acts = json.dumps(design.get("acts", []), ensure_ascii=False)
    evidence = json.dumps(design.get("evidence", []), ensure_ascii=False)
    chars = json.dumps(design.get("characters", []), ensure_ascii=False)
    hook = json.dumps(design.get("hook", {}), ensure_ascii=False)
    tail = "\n".join(f"- {t}" for t in prev_tail[-6:]) or "- (없음)"
    first_rule = (f"""이 장은 이야기의 첫 장이다. 첫 장면은 반드시 훅 그 자체다.
hook.line 을 첫 대사로 쓰고, 그 상황 한복판에서 시작한다. 인사·소개·배경 설명으로 시작하면 실패다.
훅 1~2장면 뒤에 시간을 되돌리는 해설 한 줄("{design.get('hook', {}).get('rewind_caption','')}")을 넣고 본론으로 간다."""
                  if is_first else "이 장은 앞 장면에서 자연스럽게 이어진다. 앞 장 마지막 대사를 반복하지 않는다.")
    last_rule = ("마지막 장이다. 절정의 반전을 터뜨리고, 물증의 의미를 회수한 뒤, 담담한 여운으로 끝낸다. "
                 "구독·지역 댓글 안내는 여기서 쓰지 않는다(영상 맨 끝에 따로 붙는다).") if is_last else ""
    return f"""〈{design.get('title','')}〉 2단계 집필. {ch.get('index')}장 「{ch.get('title','')}」.

[확정된 설계 — 바꾸지 말 것]
무대: {design.get('setting','')}
등장인물: {chars}
생활 물증: {evidence}
5막 뼈대: {acts}
훅: {hook}

[앞 장면]
{tail}

[이 장]
{ch.get('beat','')} (중심 인물: {ch.get('pov','')}, 막: {ch.get('act','')})
{first_rule}
{last_rule}

[쓰기 규칙]
- 분량 약 {total_chars}자. {scenes_hint}
- 해설(narrator)과 인물 직접 대화를 번갈아. **인물 대화가 전체의 30~40%가 되게 한다.** 해설만 길게 이어 쓰지 않는다.
  요약할 수 있는 상황도 인물들의 실제 말다툼·다정한 말·머뭇거림으로 보여 준다. 대사는 실제 말투 그대로.
- 인물이 말하는 장면마다 speaker_age(예: "40대 후반", "78세", "8세")·speaker_gender("male"|"female")·
  speaker_tone(성격·처지·지금 감정 한 줄)을 함께 적는다. 이 정보가 목소리 연기에 그대로 쓰인다.
- 일본어 번역투 금지(~에 대해, ~에 있어서, ~되어진다, ~라는 사실을 알게 되었다, 그녀/그는 남발).
- 장면마다 효과음(sfx)을 1~2개 붙인다. 표에 있는 것만. 대사 속에 [대괄호] 태그를 쓰지 않는다.
- 효과음은 대사의 문장 시작·대화 사이·문장 끝에 자연스럽게 깔리도록 고른다(문 여닫기, 발자국,
  종이 넘김, 찻잔, 한숨, 가쁜 숨, 심장박동, 핸드폰 진동, 병원 룸톤, 냄비 보글, 빗소리 등).
- 반전이 터지는 장면 앞에는 (연출 메모를 쓰지 말고) 감정 태그를 twist 로 두어 음악이 스웰되게 한다.
- 물증은 대사와 행동으로만 드러낸다. "그는 슬펐다" 같은 설명 대신 "숟가락을 놓았다" 같은 행동.
- 감정 태그는 conflict/twist/heal 중에서 장면 흐름에 맞게.
- image_prompt 는 영어, 인물 묘사를 설계의 desc_en 그대로 반복, no text.

JSON 만 출력:
{{"scenes":[{{"speaker":"narrator","text":"...","emotion":"conflict","sfx":["한숨"],
  "image_prompt":"English cinematic still, ...","image_caption":"한국어 장면 설명"}},
 {{"speaker":"son","text":"...","emotion":"conflict","sfx":[],
  "speaker_age":"40대 후반","speaker_gender":"male",
  "speaker_tone":"십 년 만에 집을 연 아들, 서운함과 그리움이 뒤섞임",
  "image_prompt":"...","image_caption":"..."}}]}}"""


def _short_design_prompt(settings: dict) -> str:
    target = float(settings.get("target_seconds") or 50)
    genre = GENRES.get(settings.get("genre", "tear_family"), GENRES["tear_family"])
    topic = (settings.get("topic") or "").strip() or "(없음 — 장르에 맞게 새로 정할 것)"
    return f"""〈세월의 사연극장〉 {int(target)}초 세로 쇼츠(9:16). **1단계 설계**만 한다.

- 사연 종류: {genre['label']} — {genre['hint']}
- 주제: {topic}
- 0초 콜드 오픈: 가장 충격적인 대사·사건 한복판에서 시작(인사·소개 금지). 첫 15초 안에 반전의 실마리.

확정할 것: 생활 물증 1개(디테일까지), 압축 5비트(훅→되감기→갈등→반전→여운), 훅 대사, 되감기 자막,
인물 2~3명, 썸네일 문구, 업로드 카피.

JSON 만 출력:
{{"title":"대표 제목","titles":["제목안1","제목안2","제목안3"],"logline":"한 줄 소개",
  "description":"설명문 줄거리 3줄","hashtags":["#사연","#라디오드라마","#감동사연","#반전","#가족사연","#시니어","#노인사연","#이야기"],
  "setting":"연도·지역·장소",
  "characters":[{{"id":"mother","name":"어머니","relation":"...","age":"...","desc_en":"English visual, repeated in every image"}}],
  "evidence":[{{"item":"...","detail":"...","meaning":"..."}}],
  "acts":[{{"act":1,"name":"훅","summary":"...","plant":"...","payoff":"..."}}],
  "hook":{{"line":"0초 충격 대사","situation":"...","rewind_caption":"사흘 전, 그날"}},
  "chapters":[{{"index":1,"act":1,"title":"이야기","beat":"훅→되감기→갈등→반전→여운","pov":"..."}}],
  "sequel_teaser":"이번 사연 6개월 뒤 후속편 복선 한두 문장",
  "next_story":{"title":"다음 사연 제목","teaser":"다음 사연 예고 한 문장"},
  "thumbnail":{{"style1":["8자 내외","10자 내외"],"style2":["대화 1","대화 2","반전 한 줄","유도 한 줄"]}},
  "upload":{{"title":"유튜브 제목","description":"설명","tags":["태그","6개"]}}}}"""


def generate_script(settings: dict, cfg: dict,
                    progress: Callable[[int, str], None] | None = None) -> dict:
    """2단계(설계 → 집필)로 대본 생성. 실패하면 예외를 올린다(호출부에서 템플릿 폴백)."""
    target = float(settings.get("target_seconds") or 300)
    short = target <= 90
    fmt = FORMAT_PRESETS.get(settings.get("preset", "pilot5"), FORMAT_PRESETS["pilot5"])
    n_chapters = 1 if short else max(2, min(int(fmt.get("chapter_hint") or 4), 14))
    if not short and target >= 600:
        n_chapters = min(14, max(2, int(round(target / 180))))
    n_acts = 5 if not short else 2

    if progress:
        progress(3, "1단계 · 생활 물증과 5막 반전 뼈대 설계 중…")
    design = _call(cfg, _short_design_prompt(settings) if short else _design_prompt(settings, n_acts, n_chapters),
                   temperature=0.95)
    chapters = design.get("chapters") or [{"index": 1, "title": "이야기", "beat": "훅부터 여운까지", "act": 1}]
    if len(chapters) > n_chapters:
        chapters = chapters[:n_chapters]

    total_chars = int(target * 4.3)
    scenes: list[dict] = []
    prev_tail: list[str] = []
    for i, ch in enumerate(chapters):
        chars_this = max(180, int(total_chars / len(chapters)))
        scenes_hint = ("8~10장면, 12~22자 짧은 호흡" if short
                       else f"{max(6, round(chars_this / 55))}~{max(8, round(chars_this / 38))}장면")
        prompt = _write_prompt(settings, design, ch, chars_this, prev_tail,
                               is_first=(i == 0), is_last=(i == len(chapters) - 1),
                               scenes_hint=scenes_hint)
        if progress:
            pct = 10 + int(78 * i / max(1, len(chapters)))
            progress(pct, f"2단계 · {i + 1}/{len(chapters)}장 집필 중 — {ch.get('title','')}")
        try:
            part = _call(cfg, prompt, temperature=0.88)
        except Exception:
            time.sleep(2.0)
            part = _call(cfg, prompt, temperature=0.8)
        part_scenes = part.get("scenes") or []
        for s in part_scenes:
            s["chapter"] = ch.get("index", i + 1)
            s["chapter_title"] = ch.get("title", "")
            scenes.append(s)
        prev_tail.extend([s.get("text", "") for s in part_scenes[-3:]])

    if len(scenes) < (6 if short else 8):
        raise RuntimeError("생성된 장면이 너무 적습니다.")

    if progress:
        progress(92, "대본·물증 복선 점검 중…")

    result = {
        "source": "gemini",
        "title": design.get("title") or "세월의 사연",
        "logline": design.get("logline", ""),
        "titles": design.get("titles", []),
        "description": design.get("description", ""),
        "hashtags": design.get("hashtags", []),
        "setting": design.get("setting", ""),
        "characters": design.get("characters", []),
        "evidence": design.get("evidence", []),
        "acts": design.get("acts", []),
        "scenes": scenes,
        "chapters": chapters,
        "hook": design.get("hook", {}),
        "sequel_teaser": design.get("sequel_teaser", ""),
        "next_story": design.get("next_story", {}),
        "thumbnail": design.get("thumbnail", {}),
        "upload": design.get("upload", {}),
    }
    return result


# ── 정규화 ─────────────────────────────────────────────────────────────────
def _clean_titles(titles, fallback: str | None) -> list[str]:
    out = []
    for t in (titles or []):
        t = re.sub(r"\s+", " ", str(t)).strip().strip('"“”')
        if t and t not in out:
            out.append(t[:60])
    if fallback and fallback not in out:
        out.insert(0, str(fallback)[:60])
    return out[:3]


def _clean_tags(tags) -> list[str]:
    out = []
    for t in (tags or []):
        t = str(t).strip()
        if not t:
            continue
        if not t.startswith("#"):
            t = "#" + t.replace(" ", "")
        t = re.sub(r"[^#\w가-힣]", "", t)
        if len(t) > 1 and t not in out:
            out.append(t)
    defaults = ["#사연", "#라디오드라마", "#감동사연", "#사이다", "#가족사연",
                "#시니어", "#노인사연", "#실화같은이야기", "#이야기", "#세월의사연극장"]
    for d in defaults:
        if len(out) >= 8:
            break
        if d not in out:
            out.append(d)
    return out[:10]


def normalize_script(data: dict, settings: dict) -> dict:
    """생성 결과를 프로젝트 규격에 맞게 다듬는다."""
    scenes_in = data.get("scenes") or []
    hook_line = str((data.get("hook") or {}).get("line", "")).strip() if isinstance(data.get("hook"), dict) else ""
    # 설계 단계의 인물 정보(나이·성별)를 화자 이름으로 연결해 두면, 화자 메타가 빠진 장면도 채운다.
    char_meta: dict[str, dict] = {}
    for c in (data.get("characters") or []):
        if isinstance(c, dict) and c.get("id"):
            char_meta[str(c["id"]).strip().lower()] = {
                "age": str(c.get("age") or "").strip(),
                "gender": str(c.get("gender") or "").strip(),
                "desc": str(c.get("relation") or "") + " " + str(c.get("habit") or ""),
            }
    scenes: list[dict] = []

    for s in scenes_in:
        text = re.sub(r"\s+", " ", str(s.get("text", ""))).strip()
        text = re.sub(r"^[\"'“”]", "", text).strip()
        if not text:
            continue
        raw_speaker = str(s.get("speaker") or "").strip()
        speaker = raw_speaker or "narrator"
        if speaker not in SPEAKERS:
            speaker = "narrator"
        emotion = str(s.get("emotion") or "heal").strip()
        if emotion not in EMOTIONS:
            emotion = "heal"
        sfx = [str(x).strip() for x in (s.get("sfx") or []) if str(x).strip() in SFX_VOCAB][:2]
        meta = {
            "age": str(s.get("speaker_age") or "").strip()[:20],
            "gender": str(s.get("speaker_gender") or "").strip().lower()[:10],
            "tone": re.sub(r"\s+", " ", str(s.get("speaker_tone") or "")).strip()[:120],
        }
        if raw_speaker and raw_speaker.lower() != "narrator" and not (meta["age"] or meta["gender"]):
            fill = char_meta.get(raw_speaker.lower())
            if fill:
                meta["age"] = meta["age"] or fill["age"]
                meta["gender"] = meta["gender"] or fill["gender"]
                meta["tone"] = meta["tone"] or fill["desc"][:120]
        prompt = re.sub(r"\s+", " ", str(s.get("image_prompt") or "")).strip()
        caption = re.sub(r"\s+", " ", str(s.get("image_caption") or "")).strip()
        if not caption:
            caption = text[:26]
        if not prompt:
            prompt = _fallback_prompt(caption)
        scenes.append({
            "id": f"s{len(scenes) + 1:02d}",
            "speaker": speaker,
            "text": text,
            "emotion": emotion,
            "sfx": sfx,
            "image_prompt": prompt,
            "image_caption": caption,
            "speaker_age": meta["age"],
            "speaker_gender": meta["gender"],
            "speaker_tone": meta["tone"],
            "chapter": int(s.get("chapter") or 1),
            "chapter_title": str(s.get("chapter_title") or "").strip(),
        })
    if not scenes:
        raise RuntimeError("대본에 쓸 수 있는 장면이 없습니다.")

    # 콜드 오픈 보정: 혹시 인사말로 시작하면 훅 장면을 맨 앞으로 끌어온다.
    scenes = _enforce_cold_open(scenes, hook_line)

    chapters_meta = data.get("chapters") or []
    if chapters_meta and len(chapters_meta) > 1:
        max_ch = len(chapters_meta)
        for sc in scenes:
            sc["chapter"] = max(1, min(max_ch, int(sc.get("chapter") or 1)))
    else:
        for sc in scenes:
            sc["chapter"] = 1

    hook_ids = _pick_hook_ids(scenes, hook_line)
    title = (data.get("title") or "세월의 사연").strip()[:40]
    chars = []
    for c in (data.get("characters") or []):
        if isinstance(c, dict) and c.get("name"):
            chars.append({
                "name": str(c["name"]).strip(),
                "desc_en": str(c.get("desc_en", "")).strip(),
                "age": str(c.get("age") or "").strip()[:20],
                "gender": str(c.get("gender") or "").strip().lower()[:10],
            })

    thumb = data.get("thumbnail") or {}
    style1 = [str(x) for x in (thumb.get("style1") or []) if str(x).strip()]
    style2 = [str(x) for x in (thumb.get("style2") or []) if str(x).strip()]
    if len(style1) < 2:
        style1 = [title[:10], "실화 같은 사연"]
    if len(style2) < 3:
        style2 = _style2_from_scenes(scenes, title)

    chapter_list, seen = [], set()
    for sc in scenes:
        if sc["chapter"] in seen:
            continue
        seen.add(sc["chapter"])
        idx = len(chapter_list) + 1
        meta = next((c for c in chapters_meta if int(c.get("index", -1)) == sc["chapter"]), None)
        chapter_list.append({"index": idx,
                             "title": (meta or {}).get("title") or sc.get("chapter_title") or f"{idx}장",
                             "anchor": sc["id"]})

    hook_meta = data.get("hook") if isinstance(data.get("hook"), dict) else {}
    return {
        "source": data.get("source", "gemini"),
        "title": title,
        "logline": str(data.get("logline", ""))[:200],
        "titles": _clean_titles(data.get("titles"), data.get("title")),
        "description": str(data.get("description", ""))[:1200],
        "hashtags": _clean_tags(data.get("hashtags")),
        "setting": str(data.get("setting", ""))[:120],
        "characters": chars,
        "evidence": data.get("evidence") or [],
        "acts": data.get("acts") or [],
        "scenes": scenes,
        "chapters": chapter_list,
        "hook": {
            "enabled": bool(settings.get("hook15", True)),
            "scene_ids": hook_ids,
            "caption": str(hook_meta.get("caption") or hook_meta.get("line") or "")[:50],
            "line": hook_line[:80],
            "rewind_caption": str(hook_meta.get("rewind_caption") or "그날보다 사흘 전").strip()[:40],
        },
        "sequel_teaser": str(data.get("sequel_teaser", ""))[:300],
        "next_story": data.get("next_story") or {},
        "thumbnail": {"style1": style1[:2], "style2": style2[:5]},
        "upload": data.get("upload") or {},
    }


GREETING_RE = re.compile(r"(안녕하세요|반갑습니다|세월의 사연극장입니다|오늘의 사연은|어서 오세요)")


def _looks_like_greeting(text: str) -> bool:
    return bool(GREETING_RE.search(text[:40]))


def _enforce_cold_open(scenes: list[dict], hook_line: str) -> list[dict]:
    """0초가 인사·소개면 훅 장면을 앞으로 옮기고, 훅 대사가 없으면 첫 장면에 심는다."""
    if _looks_like_greeting(scenes[0]["text"]):
        # 인사 장면은 끝으로 보낸다
        greeting = scenes.pop(0)
        scenes.append(greeting)
    if hook_line and not any(hook_line[:12] in s["text"] for s in scenes[:2]):
        first = scenes[0]
        if not _looks_like_greeting(first["text"]):
            # 첫 장면이 이미 사건이면 그대로 두고, 훅 대사를 새 장면으로 앞에 붙인다
            scenes.insert(0, {
                "id": "s00", "speaker": scenes[0]["speaker"], "text": hook_line,
                "emotion": "twist", "sfx": ["심장박동"],
                "image_prompt": scenes[0]["image_prompt"], "image_caption": scenes[0]["image_caption"],
                "chapter": 1, "chapter_title": scenes[0].get("chapter_title", ""), "hook_line": True,
            })
    for i, sc in enumerate(scenes, start=1):
        sc["id"] = f"s{i:02d}"
    return scenes


def _pick_hook_ids(scenes: list[dict], hook_line: str) -> list[str]:
    if hook_line:
        for s in scenes[:3]:
            if hook_line[:12] in s["text"]:
                ids = [s["id"]]
                total = len(s["text"]) / 4.3
                for nxt in scenes[scenes.index(s) + 1:]:
                    if total >= 12:
                        break
                    ids.append(nxt["id"])
                    total += len(nxt["text"]) / 4.3
                return ids
    twist = [s for s in scenes if s["emotion"] == "twist"] or scenes
    picked, total = [], 0.0
    for s in twist[-3:]:
        picked.append(s["id"])
        total += len(s["text"]) / 4.3
        if total >= 12:
            break
    return picked or [scenes[0]["id"]]


def _style2_from_scenes(scenes: list[dict], title: str) -> list[str]:
    lines = [f"“{title}”"]
    for s in scenes:
        if s["emotion"] in ("twist", "conflict") and 8 <= len(s["text"]) <= 24:
            lines.append("“" + s["text"][:24] + "”")
        if len(lines) >= 4:
            break
    lines.append("마지막까지 보세요")
    return lines[:5]


def _fallback_prompt(caption: str) -> str:
    return ("Cinematic realistic Korean drama still, " + caption +
            ", elderly Korean characters, warm natural light, shallow depth of field, "
            "film grain, no text, no letters, no watermark")
