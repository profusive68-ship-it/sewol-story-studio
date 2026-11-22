"""세월의 사연극장 v1.2.5 — OpenAI 대본 자동 보조 · 대본 읽기/수정·재제작 검증.

네트워크·ffmpeg·실제 API 호출 없음. (OpenAI 응답은 가짜 urlopen 으로 흉내낸다)

    python3 tools/selftest_v125.py
"""
from __future__ import annotations

import ast
import io
import json
import shutil
import sys
import threading
import traceback
import urllib.error
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORK = ROOT / ".cache" / "selftest_v125"

PASS: list[str] = []
FAIL: list[str] = []

FAKE = "FAKE_KEY_FOR_SELFTEST"

PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000a49444154789c6300010000050001")


def check(name: str, cond: bool, detail: str = "") -> None:
    if cond:
        PASS.append(name)
        print(f"  ✅ {name}")
    else:
        FAIL.append(f"{name} — {detail}")
        print(f"  ❌ {name} {detail}")


def _png(variant: int = 0) -> bytes:
    return PNG + bytes([variant % 256]) * (24 + variant)


# ── 가짜 OpenAI 응답 ─────────────────────────────────────────────────────
class FakeResp:
    def __init__(self, body: bytes):
        self.body = body

    def read(self) -> bytes:
        return self.body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _chat_body(text: str) -> bytes:
    return json.dumps({"choices": [{"message": {"role": "assistant", "content": text}}]},
                      ensure_ascii=False).encode("utf-8")


DESIGN = {
    "title": "엄마의 마지막 김치통",
    "titles": ["김치통 하나에 집안이 뒤집혔다", "엄마가 남긴 마지막 김치통",
               "등기부등본보다 무서운 김치통"],
    "logline": "김치통 속 통장 한 장이 가족의 거짓말을 드러낸다.",
    "description": "제주 서귀포, 어머니가 남긴 김치통 하나로 시작된 이야기.",
    "hashtags": ["#사연", "#라디오드라마", "#감동사연", "#가족사연"],
    "setting": "제주 서귀포, 2003년 겨울",
    "characters": [{"id": "mother", "name": "어머니 순자", "relation": "주인공의 어머니",
                    "age": "78세", "gender": "female", "habit": "말끝을 흐린다",
                    "desc_en": "Korean grandmother, 78, silver hair in a low bun"}],
    "evidence": [{"item": "김치통", "detail": "바닥에 붙은 국민은행 통장",
                  "meaning": "어머니가 몰래 모은 돈", "reveal_act": 4}],
    "acts": [{"act": 1, "name": "훅", "summary": "김치통을 연다", "plant": "통장", "payoff": "어머니의 마음"}],
    "hook": {"line": "엄마, 이게 뭐야?", "situation": "김치통 바닥에서 통장이 나온다",
             "rewind_caption": "사흘 전, 아무것도 몰랐던 그날"},
    "chapters": [{"index": 1, "act": 1, "title": "이야기", "beat": "훅→되감기→갈등→반전→여운", "pov": "아들"}],
    "sequel_teaser": "6개월 뒤, 어머니의 통장에서 또 다른 이름이 나온다.",
    "next_story": {"title": "아버지의 낡은 손목시계", "teaser": "시계 속에 숨은 사진 한 장."},
    "thumbnail": {"style1": ["김치통 하나에", "집안이 뒤집혔다"],
                  "style2": ["엄마, 이게 뭐야?", "통장이 나왔다", "충격 반전", "끝까지 보세요"]},
    "upload": {"title": "엄마의 마지막 김치통", "description": "설명", "tags": ["사연", "라디오드라마"]},
}

SCENES = {"scenes": [
    {"speaker": "narrator", "text": "엄마, 이게 뭐야?", "emotion": "twist", "sfx": ["숨죽임"],
     "image_prompt": "Korean kitchen, old woman, winter", "image_caption": "김치통을 여는 순간"},
    {"speaker": "old_female", "text": "그건 그냥 오래된 통장이야.", "emotion": "conflict", "sfx": ["한숨"],
     "speaker_age": "78세", "speaker_gender": "female", "speaker_tone": "숨기고 싶은 마음",
     "image_prompt": "Korean grandmother closeup", "image_caption": "말끝을 흐리는 어머니"},
    {"speaker": "narrator", "text": "사흘 전, 아무것도 몰랐던 그날로 돌아간다.", "emotion": "heal", "sfx": [],
     "image_prompt": "Korean house winter morning", "image_caption": "사흘 전 아침"},
    {"speaker": "young_male", "text": "엄마, 나 왔어요.", "emotion": "heal", "sfx": ["문 삽입"],
     "speaker_age": "40대 후반", "speaker_gender": "male", "speaker_tone": "십 년 만에 온 아들",
     "image_prompt": "Korean son entering house", "image_caption": "아들이 집에 들어선다"},
    {"speaker": "narrator", "text": "어머니는 아무 말 없이 냉장고를 열었다.", "emotion": "conflict", "sfx": ["냉장고 웅웅"],
     "image_prompt": "Korean fridge open", "image_caption": "냉장고를 여는 어머니"},
    {"speaker": "old_female", "text": "너 학원비는 내가 냈어. 매달 조금씩.", "emotion": "twist", "sfx": ["종이 넘김"],
     "speaker_age": "78세", "speaker_gender": "female", "speaker_tone": "털어놓는 안도",
     "image_prompt": "Korean grandmother with bankbook", "image_caption": "통장을 내미는 어머니"},
    {"speaker": "narrator", "text": "통장에는 연필로 적힌 메모가 가득했다.", "emotion": "twist", "sfx": ["종이 바스락"],
     "image_prompt": "Korean bankbook closeup pencil notes", "image_caption": "연필 메모가 가득한 통장"},
    {"speaker": "narrator", "text": "그날 밤, 아들은 처음으로 어머니의 손을 잡았다.", "emotion": "heal", "sfx": ["한숨"],
     "image_prompt": "Korean mother and son holding hands", "image_caption": "손을 잡은 모자"},
]}


def _fake_oai_call(rec: list):
    """prompt 내용으로 설계/집필 응답을 갈라 주는 가짜 OpenAI 호출."""
    def call(cfg, prompt, *, temperature=0.9, response_json=True, max_output_tokens=None, system=None):
        rec.append({"prompt": prompt, "temperature": temperature, "model": cfg.get("openai_script_model")})
        if "1단계 설계" in prompt:
            return json.dumps(DESIGN, ensure_ascii=False)
        return json.dumps(SCENES, ensure_ascii=False)
    return call


def main() -> int:
    print("== 1. 버전 · 문서 ==")
    disk = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    init_src = (ROOT / "app" / "__init__.py").read_text(encoding="utf-8")
    ver_tuple = tuple(int(x) for x in disk.split(".") if x.isdigit())
    check("VERSION 이 1.2.5 이상", ver_tuple >= (1, 2, 5), disk)
    check("app.__version__ 가 VERSION 과 같다", f'"{disk}"' in init_src, init_src.strip().splitlines()[-1])
    readme = (ROOT / "README_맥북설치방법.txt").read_text(encoding="utf-8")
    check("설명서 머리말 버전 일치", f"(v{disk})" in readme.splitlines()[1], readme.splitlines()[1])
    check("설명서에 신규 기능 안내", "OpenAI 자동 보조" in readme and "대본 전체" in readme)

    print("== 2. Python 3.9 문법 호환 ==")
    bad = []
    for folder in ("app", "tools"):
        for f in sorted((ROOT / folder).glob("*.py")):
            try:
                ast.parse(f.read_text(encoding="utf-8"), filename=str(f), feature_version=(3, 9))
            except SyntaxError as e:
                bad.append(f"{f.name}: {e}")
    check("app+tools 전체 ast.parse(3,9)", not bad, "; ".join(bad[:5]))
    missing_future = []
    for f in sorted((ROOT / "app").glob("*.py")):
        src = f.read_text(encoding="utf-8")
        if (" | None" in src or "None |" in src) and "from __future__ import annotations" not in src:
            missing_future.append(f.name)
    check("X|Y 표기를 쓰는 파일은 from __future__ import annotations", not missing_future,
          str(missing_future))

    print("== 3. 임시 폴더 준비 ==")
    shutil.rmtree(WORK, ignore_errors=True)
    app_root = WORK / "app_root"
    app_root.mkdir(parents=True)
    for name in ("app", "static", "assets_inbox", "config", "sfx_library", "assets"):
        src = ROOT / name
        if not src.exists():
            continue
        shutil.copytree(src, app_root / name,
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    for name in ("VERSION", "requirements.txt", "start.command"):
        src = ROOT / name
        if src.exists():
            shutil.copy2(src, app_root / name)
    (app_root / "projects").mkdir(parents=True, exist_ok=True)
    (app_root / ".git").mkdir(parents=True, exist_ok=True)
    sys.path.insert(0, str(app_root))

    from fastapi.testclient import TestClient  # noqa: E402

    from app import __version__ as pkg_version  # noqa: E402
    from app import gemini_script as gs  # noqa: E402
    from app import main as web  # noqa: E402
    from app import openai_script as oai  # noqa: E402
    from app.paths import project_dir  # noqa: E402
    from app.project import create_project, load, read_script_view, save_edited_script  # noqa: E402
    from app.settings import load_config, public_config, save_config  # noqa: E402

    check("임시 사본 버전 일치", pkg_version == disk, f"{pkg_version} / {disk}")

    print("== 4. OpenAI 호출(가짜 HTTP) ==")
    payload = oai.build_payload({"openai_script_model": "gpt-4o-mini"}, "프롬프트", temperature=0.7,
                                response_json=True, max_output_tokens=120, system="규칙")
    check("엔드포인트", oai.OPENAI_CHAT_URL == "https://api.openai.com/v1/chat/completions",
          oai.OPENAI_CHAT_URL)
    check("기본 모델 gpt-4o-mini", payload["model"] == "gpt-4o-mini", str(payload.get("model")))
    check("JSON 모드(response_format)", payload.get("response_format") == {"type": "json_object"},
          str(payload.get("response_format")))
    check("system + user 메시지", [m["role"] for m in payload["messages"]] == ["system", "user"],
          str([m["role"] for m in payload["messages"]]))
    check("온도·최대 토큰", payload["temperature"] == 0.7 and payload["max_tokens"] == 120, str(payload)[:160])
    check("키가 없으면 호출 전에 안내", "OpenAI API 키가 없습니다" in
          _err(lambda: oai.call_openai({"openai_api_key": ""}, "hi")), "")

    calls: list[dict] = []
    real_urlopen = oai.urllib.request.urlopen
    real_sleep = oai.time.sleep
    slept: list[float] = []
    oai.time.sleep = lambda s: slept.append(s)
    queue: list = []

    def fake_urlopen(req, timeout=None):
        calls.append({"url": req.full_url, "auth": req.headers.get("Authorization"),
                      "body": json.loads(req.data.decode("utf-8"))})
        item = queue.pop(0) if len(queue) > 1 else queue[0]
        if isinstance(item, Exception):
            raise item
        return FakeResp(item)

    oai.urllib.request.urlopen = fake_urlopen
    try:
        queue[:] = [_chat_body('{"ok": 1}')]
        text = oai.call_openai({"openai_api_key": "FAKE_KEY_FOR_SELFTEST"}, "안녕", response_json=True, system="S")
        check("응답 텍스트 파싱", text == '{"ok": 1}', text)
        check("Authorization 헤더 Bearer", calls[0]["auth"] == "Bearer " + FAKE, str(calls[0]["auth"]))
        check("본문 모델 gpt-4o-mini", calls[0]["body"]["model"] == "gpt-4o-mini",
              str(calls[0]["body"].get("model")))
        check("본문에 response_format", calls[0]["body"].get("response_format", {}).get("type") == "json_object",
              str(calls[0]["body"].get("response_format")))

        # 503 → 1.5초 뒤 1회 재시도
        calls.clear(); slept.clear()
        queue[:] = [urllib.error.HTTPError(oai.OPENAI_CHAT_URL, 503, "overloaded", {}, io.BytesIO(b'{"e":"busy"}')),
                    _chat_body('{"ok": 2}')]
        text = oai.call_openai({"openai_api_key": "FAKE_KEY_FOR_SELFTEST"}, "안녕")
        check("503 → 재시도 후 성공", text == '{"ok": 2}' and len(calls) == 2, str(len(calls)))
        check("재시도 전 1.5초 대기", slept == [oai.RETRY_SECONDS], str(slept))

        # 401 → 재시도 없이 한국어 안내
        calls.clear(); slept.clear()
        queue[:] = [urllib.error.HTTPError(oai.OPENAI_CHAT_URL, 401, "unauthorized", {}, io.BytesIO(b"")),
                    _chat_body('{"ok": 3}')]
        msg = _err(lambda: oai.call_openai({"openai_api_key": "FAKE_KEY_BAD"}, "안녕"))
        check("401 은 즉시 실패 + 키 안내", "키가 거부" in msg and len(calls) == 1, f"{msg} / {len(calls)}")
    finally:
        oai.urllib.request.urlopen = real_urlopen
        oai.time.sleep = real_sleep

    print("== 5. 엔진 선택(auto · gemini · openai) ==")
    both = {"gemini_api_key": "g", "openai_api_key": "o"}
    only_o = {"gemini_api_key": "", "openai_api_key": "o"}
    only_g = {"gemini_api_key": "g", "openai_api_key": ""}
    none = {"gemini_api_key": "", "openai_api_key": ""}
    check("auto · 키 2개 → Gemini 먼저", gs.candidate_engines(both) == ["gemini", "openai"],
          str(gs.candidate_engines(both)))
    check("auto · OpenAI 키만 → OpenAI", gs.candidate_engines(only_o) == ["openai"],
          str(gs.candidate_engines(only_o)))
    check("auto · Gemini 키만 → Gemini", gs.candidate_engines(only_g) == ["gemini"],
          str(gs.candidate_engines(only_g)))
    check("auto · 키 없음 → 빈 목록", gs.candidate_engines(none) == [], str(gs.candidate_engines(none)))
    check("gemini 단독 · OpenAI 키만 → 못 씀",
          gs.candidate_engines({"script_engine": "gemini", **only_o}) == [],
          str(gs.candidate_engines({"script_engine": "gemini", **only_o})))
    check("openai 단독 · Gemini 키만 → 못 씀",
          gs.candidate_engines({"script_engine": "openai", **only_g}) == [],
          str(gs.candidate_engines({"script_engine": "openai", **only_g})))
    check("잘못된 값은 auto 로", gs.script_engine_mode({"script_engine": "gpt"}) == "auto", "")
    check("태그 문구", gs.engine_tag("openai") == "AI 대본 (OpenAI)"
          and gs.engine_tag("gemini") == "AI 대본 (Gemini)"
          and gs.engine_tag("template") == "예시 대본", "")
    check("키 없음 안내에 두 엔진 표기", "Gemini·OpenAI" in gs.no_engine_message({}), gs.no_engine_message({}))

    print("== 6. Gemini 실패 → OpenAI 자동 폴백 ==")
    gem_calls: list[str] = []
    oai_calls: list[dict] = []
    real_gemini = gs.call_gemini
    real_oai = oai.call_openai
    state = {"gemini": "raise", "openai": "ok"}

    def fake_gemini(cfg, prompt, **kw):
        gem_calls.append(prompt)
        if state["gemini"] == "raise":
            raise RuntimeError("Gemini 호출 실패(모델 gemini-3.8-flash): HTTP 503 (busy)")
        return json.dumps(DESIGN, ensure_ascii=False)

    gs.call_gemini = fake_gemini
    oai.call_openai = _fake_oai_call(oai_calls)
    try:
        used: list[str] = []
        data = gs._call({"gemini_api_key": "g", "openai_api_key": "o"}, "1단계 설계 테스트",
                        on_engine=used.append)
        check("Gemini 503 → OpenAI 결과 사용", data.get("title") == DESIGN["title"], str(data)[:120])
        check("사용 엔진 기록 openai", used == ["openai"], str(used))
        check("Gemini 먼저 시도했다", len(gem_calls) == 1, str(len(gem_calls)))
        check("OpenAI 에 같은 프롬프트 전달", oai_calls and oai_calls[0]["prompt"] == "1단계 설계 테스트",
              str(oai_calls[:1])[:160])

        gem_calls.clear(); oai_calls.clear(); used.clear()
        state["gemini"] = "ok"
        data = gs._call({"gemini_api_key": "g", "openai_api_key": "o"}, "1단계 설계 테스트",
                        on_engine=used.append)
        check("Gemini 성공하면 OpenAI 는 부르지 않는다", used == ["gemini"] and not oai_calls,
              f"{used} / {len(oai_calls)}")

        state["gemini"] = "raise"
        oai.call_openai = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("OpenAI HTTP 429"))
        msg = _err(lambda: gs._call({"gemini_api_key": "g", "openai_api_key": "o"}, "테스트"))
        check("둘 다 실패하면 두 원인을 함께 알린다", "Gemini:" in msg and "OpenAI:" in msg, msg[:200])

        oai.call_openai = _fake_oai_call(oai_calls)
        sink: dict = {}
        result = gs.generate_script({"preset": "shorts50", "genre": "tear_family",
                                     "target_seconds": 50, "hook15": True},
                                    {"gemini_api_key": "g", "openai_api_key": "o"}, engine_sink=sink)
        check("generate_script source=openai", result["source"] == "openai", str(result["source"]))
        check("engine_sink 에 엔진 기록", sink.get("engine") == "openai", str(sink))
        check("집필 장면 8개", len(result.get("scenes") or []) == 8, str(len(result.get("scenes") or [])))
    finally:
        gs.call_gemini = real_gemini
        oai.call_openai = real_oai

    print("== 7. 정규화 · 프로젝트 태그 ==")
    from app.gemini_script import normalize_script  # noqa: E402
    norm = normalize_script({**DESIGN, **SCENES, "source": "openai"}, {"hook15": True})
    s0 = norm["scenes"][0]
    check("장면 스키마(화자·감정·대사·챕터)", all(k in s0 for k in
          ("id", "speaker", "text", "emotion", "sfx", "image_prompt", "chapter")), str(sorted(s0)))
    check("인물 연기 메타 유지", any(s.get("speaker_tone") for s in norm["scenes"]), "")

    save_config({"gemini_api_key": "", "openai_api_key": "FAKE_KEY_FOR_SELFTEST",
                 "script_engine": "auto", "openai_script_model": "gpt-4o-mini"})
    gs.call_gemini = fake_gemini
    oai.call_openai = _fake_oai_call(oai_calls)
    try:
        proj = create_project({"preset": "shorts50", "genre": "tear_family",
                               "topic": "김치통 사연", "image_mode": "B"})
    finally:
        gs.call_gemini = real_gemini
        oai.call_openai = real_oai
    check("프로젝트에 script_engine=openai", proj.get("script_engine") == "openai", str(proj.get("script_engine")))
    check("프로젝트 태그 'AI 대본 (OpenAI)'", proj.get("script_engine_tag") == "AI 대본 (OpenAI)",
          str(proj.get("script_engine_tag")))
    check("프로젝트에 호칭 기록", isinstance(proj.get("honorifics"), dict)
          and proj["honorifics"].get("어머니") == "엄마", str(proj.get("honorifics")))
    check("대본 수정 전 script_dirty=false", proj.get("script_dirty") is False, str(proj.get("script_dirty")))
    check("장면·이미지 계획 생성", len(proj["scenes"]) >= 8 and len(proj["image_plan"]) > 0,
          f"{len(proj['scenes'])}/{len(proj['image_plan'])}")

    print("== 8. 키가 하나도 없을 때(예시 대본) ==")
    threading.Event().wait(1.1)      # 사연 번호(초 단위 id)가 겹치지 않게
    save_config({"gemini_api_key": "", "openai_api_key": "", "script_engine": "auto"})
    tpl = create_project({"preset": "shorts50", "genre": "tear_family", "image_mode": "B"})
    check("source=template", tpl.get("source") == "template", str(tpl.get("source")))
    check("태그 '예시 대본'", tpl.get("script_engine_tag") == "예시 대본", str(tpl.get("script_engine_tag")))
    check("안내에 Gemini·OpenAI 표기",
          any("Gemini·OpenAI" in w for w in (tpl.get("warnings") or [])), str(tpl.get("warnings"))[:200])

    print("== 8-1. 호칭 통일 (엄마/어머니 섞임 방지) ==")
    from app.honorifics import (find_variant, harmonize_script, harmonize_text,  # noqa: E402
                               pick_variants)
    from app.script_templates import build_template_script  # noqa: E402
    sys_rules = gs.SYSTEM_RULES
    check("시스템 규칙에 호칭 통일 항목", "호칭·인물명 통일" in sys_rules, "")
    check("시스템 규칙이 제목·썸네일·대본을 함께 지정",
          "제목·제목 3안·썸네일 문구" in sys_rules and "인물 대사" in sys_rules, "")
    check("시스템 규칙에 엄마/어머니 예시", "'엄마'와 '어머니'" in sys_rules, "")
    check("주제의 표현이 표준", pick_variants(["어머니와 아들의 김치통"]) == {"어머니": "어머니"},
          str(pick_variants(["어머니와 아들의 김치통"])))
    check("주제의 표현이 표준(엄마)", pick_variants(["엄마와 아들"]) == {"어머니": "엄마"},
          str(pick_variants(["엄마와 아들"])))
    check("주제가 없으면 제목이 표준",
          pick_variants(["", "엄마의 마지막 김치통"]) == {"어머니": "엄마"}, "")
    check("호칭이 없으면 손대지 않음", pick_variants(["그냥 사연"]) == {}, "")
    check("어머님 → 엄마(조사까지)",
          harmonize_text("어머님이 문을 열었다", {"어머니": "엄마"}) == "엄마가 문을 열었다",
          harmonize_text("어머님이 문을 열었다", {"어머니": "엄마"}))
    check("어머님은 → 엄마는",
          harmonize_text("어머님은 앉아 계셨다", {"어머니": "엄마"}) == "엄마는 앉아 계셨다",
          harmonize_text("어머님은 앉아 계셨다", {"어머니": "엄마"}))
    check("엄마가 → 어머님이(반대 방향도 조사 맞춤)",
          harmonize_text("엄마가 웃었다", {"어머니": "어머님"}) == "어머님이 웃었다",
          harmonize_text("엄마가 웃었다", {"어머니": "어머님"}))
    check("아버님 → 아빠", harmonize_text("아버님이 오셨다", {"아버지": "아빠"}) == "아빠가 오셨다",
          harmonize_text("아버님이 오셨다", {"아버지": "아빠"}))

    tpl_m = build_template_script({"genre": "tear_family", "topic": "어머니와 아들의 김치통",
                                  "target_seconds": 50, "sequel": True})
    tpl_text = json.dumps({k: tpl_m.get(k) for k in ("title", "titles", "thumbnail", "description")},
                          ensure_ascii=False) + "".join(s["text"] for s in tpl_m["scenes"])
    check("예시 대본: 주제가 '어머니'면 '엄마'가 남지 않는다", "엄마" not in tpl_text,
          [l for l in tpl_text.split("\n") if "엄마" in l][:2])
    check("예시 대본: 제목도 '어머니'로 통일", "어머니" in tpl_m["title"], tpl_m["title"])
    check("예시 대본: 썸네일 문구도 통일",
          all("엄마" not in x for x in tpl_m["thumbnail"]["style1"] + tpl_m["thumbnail"]["style2"]),
          str(tpl_m["thumbnail"])[:160])

    tpl_e = build_template_script({"genre": "tear_family", "topic": "엄마와 아들의 김치통",
                                  "target_seconds": 50, "sequel": True})
    tpl_e_text = json.dumps({k: tpl_e.get(k) for k in ("title", "titles", "thumbnail", "description")},
                            ensure_ascii=False) + "".join(s["text"] for s in tpl_e["scenes"])
    check("예시 대본: 주제가 '엄마'면 '어머니'가 남지 않는다", "어머니" not in tpl_e_text.replace("어머님", ""),
          [l for l in tpl_e_text.split("\n") if "어머니" in l][:2])
    check("예시 대본: 제목도 '엄마'로", "엄마" in tpl_e["title"], tpl_e["title"])
    check("호칭 기록 남김", tpl_e.get("honorifics", {}).get("어머니") == "엄마", str(tpl_e.get("honorifics")))

    mixed = {"title": "엄마의 김치통",
             "scenes": [{"text": "어머니가 웃으셨다."}, {"text": "엄마, 나 왔어요."}],
             "thumbnail": {"style1": ["어머니의 김치통", "집안이 뒤집혔다"],
                           "style2": ["어머니, 이게 뭐야?"]},
             "characters": [{"name": "어머니", "relation": "주인공의 어머니"},
                            {"name": "어머니 순자", "relation": ""}],
             "next_story": {"title": "어머니의 손편지", "teaser": "어머니가 남긴 한 장"}}
    hm = harmonize_script(mixed, "")
    check("AI 대본 호칭 통일(대사)", hm["scenes"][0]["text"] == "엄마가 웃으셨다.", hm["scenes"][0]["text"])
    check("AI 대본 호칭 통일(썸네일)", hm["thumbnail"]["style1"][0] == "엄마의 김치통",
          str(hm["thumbnail"]))
    check("AI 대본 호칭 통일(인물·다음 사연)",
          hm["characters"][0]["name"] == "엄마" and hm["characters"][1]["name"] == "어머니 순자"
          and hm["characters"][0]["relation"] == "주인공의 엄마"
          and hm["next_story"]["title"] == "엄마의 손편지",
          str(hm["characters"]) + str(hm["next_story"]))
    check("find_variant 가장 긴 표현", find_variant("어머님 생신") == ("어머니", "어머님"),
          str(find_variant("어머님 생신")))

    print("== 9. 대본 저장 API ==")
    client = TestClient(web.app)
    pid = proj["id"]
    detail = client.get(f"/api/projects/{pid}").json()
    check("상세에 script_engine_tag", detail.get("script_engine_tag") == "AI 대본 (OpenAI)",
          str(detail.get("script_engine_tag")))
    scenes = [{"id": s["id"], "speaker": s.get("speaker", "narrator"),
               "emotion": s.get("emotion", "heal"), "text": s.get("text", "")} for s in detail["scenes"]]
    target_row = None
    for row, sc in zip(scenes, detail["scenes"]):
        if not sc.get("placement") and row["speaker"] != "narrator":
            target_row = row
            break
    check("수정 대상 장면 찾음", target_row is not None, "")
    old_text = target_row["text"] if target_row else ""
    target_row["text"] = "수정된 대사입니다. 여기서 반전이 터진다."
    target_row["speaker"] = "old_male"
    r = client.post(f"/api/projects/{pid}/script", json={"scenes": scenes})
    saved = r.json() if r.status_code == 200 else {}
    check("POST /script 200", r.status_code == 200, r.text[:200])
    check("응답에 저장 요약", saved.get("ok") is True and saved.get("changed", 0) >= 1, str(saved)[:200])
    after = client.get(f"/api/projects/{pid}").json()
    hit = [s for s in after["scenes"] if s["text"] == "수정된 대사입니다. 여기서 반전이 터진다."]
    check("project.json 에 새 대사 저장", len(hit) == 1, str(len(hit)))
    check("화자 변경 반영", hit and hit[0]["speaker"] == "old_male", str(hit[:1])[:160])
    check("script_dirty=true", after.get("script_dirty") is True, str(after.get("script_dirty")))
    check("script_rev 증가", int(after.get("script_rev") or 0) == 1, str(after.get("script_rev")))
    script_json = json.loads((project_dir(pid) / "script.json").read_text(encoding="utf-8"))
    check("script.json 도 새 대사로 갱신",
          any(s["text"] == "수정된 대사입니다. 여기서 반전이 터진다." for s in script_json["scenes"]), "")
    check("script.json 에 호칭·성우 정보 보관",
          "honorifics" in script_json and bool(script_json.get("voice")), str(sorted(script_json))[:200])
    req_txt = (project_dir(pid) / "이미지_요청서.txt").read_text(encoding="utf-8")
    check("이미지 요청서도 새 대사로 갱신", "수정된 대사입니다" in req_txt, "")
    check("상세 상태 문구 안내", "다시 만들기" in (after.get("status") or {}).get("message", ""),
          str((after.get("status") or {}).get("message"))[:120])

    ids = {s["id"] for s in after["scenes"]}
    check("이미지 계획 anchor 모두 유효",
          all(img.get("anchor") in ids for img in after["image_plan"]),
          str([i.get("anchor") for i in after["image_plan"] if i.get("anchor") not in ids]))
    check("장 anchor 모두 유효",
          all(ch.get("anchor") in ids for ch in after.get("chapters", [])),
          str([c.get("anchor") for c in after.get("chapters", []) if c.get("anchor") not in ids]))
    check("훅 장면 id 유효",
          all(h in ids for h in (after.get("hook") or {}).get("scene_ids", [])),
          str((after.get("hook") or {}).get("scene_ids")))

    print("== 10. 대본 전체 읽기 ==")
    sv = client.get(f"/api/projects/{pid}/script").json()
    check("GET /script 200 · 장 묶음", bool(sv.get("chapters")), str(sv)[:160])
    check("전체 읽기 평문에 수정 대사", "수정된 대사입니다" in (sv.get("text") or ""), "")
    check("장면 수 일치", sv.get("total_scenes") == len(after["scenes"]),
          f"{sv.get('total_scenes')}/{len(after['scenes'])}")
    check("화자 라벨 포함", any(s.get("speaker_label") for g in sv["chapters"] for s in g["scenes"]), "")
    check("빈 장면 목록 → 400", client.post(f"/api/projects/{pid}/script", json={"scenes": []}).status_code == 400,
          "")
    too_long = [dict(scenes[0], text="가" * 700)]
    check("너무 긴 대사 → 400", client.post(f"/api/projects/{pid}/script", json={"scenes": too_long}).status_code == 400,
          "")
    check("없는 사연 → 404", client.get("/api/projects/nope-000/script").status_code == 404, "")

    print("== 11. 장면 삭제(빈 대사) · 번호 정리 ==")
    cur = client.get(f"/api/projects/{pid}").json()
    rows = [{"id": s["id"], "speaker": s.get("speaker", "narrator"), "emotion": s.get("emotion", "heal"),
             "text": s.get("text", "")} for s in cur["scenes"]]
    victim = next((r for r, s in zip(rows, cur["scenes"]) if not s.get("placement")), None)
    check("삭제할 본문 장면 찾음", victim is not None, "")
    victim["text"] = ""
    before_n = len(rows)
    r = client.post(f"/api/projects/{pid}/script", json={"scenes": rows})
    res = r.json() if r.status_code == 200 else {}
    check("빈 대사 → 삭제 처리", r.status_code == 200 and res.get("removed") == 1 and res.get("scenes") == before_n - 1,
          str(res)[:200])
    cur2 = client.get(f"/api/projects/{pid}").json()
    check("id 재번호 연속", [s["id"] for s in cur2["scenes"]] == [f"s{i:02d}" for i in range(1, len(cur2["scenes"]) + 1)],
          str([s["id"] for s in cur2["scenes"]])[:120])
    fixed_before = {s["id"]: s["text"] for s in cur2["scenes"] if s.get("placement")}
    rows_fixed = [{"id": s["id"], "speaker": s.get("speaker"), "emotion": s.get("emotion"),
                   "text": "" if s.get("placement") else s.get("text", "")}
                  for s in cur2["scenes"]]
    r3 = client.post(f"/api/projects/{pid}/script", json={"scenes": rows_fixed})
    res3 = r3.json() if r3.status_code == 200 else {}
    cur3 = client.get(f"/api/projects/{pid}").json()
    fixed_after = {s["id"]: s["text"] for s in cur3["scenes"] if s.get("placement")}
    check("고정 장면은 빈 대사 저장에도 원문 유지", bool(fixed_before) and fixed_before == fixed_after
          and res3.get("removed") == 0,
          f"before={fixed_before} after={fixed_after} removed={res3.get('removed')}")

    print("== 12. 수정한 대본으로 재제작(파이프라인 스텁) ==")
    check("이미지 없으면 재제작 400",
          client.post(f"/api/projects/{pid}/script/rebuild").status_code == 400, "")
    for i, img in enumerate(cur2["image_plan"], start=1):
        (project_dir(pid) / "images" / img["file"]).write_bytes(_png(i))
    seen: dict = {}
    real_tts, real_mix, real_video, real_thumb = (web.synthesize_sync, web.build_mix,
                                                 web.render_video, web.render_thumbnails)

    def fake_tts(p, progress=None):
        seen["texts"] = [s["text"] for s in p["scenes"]]
        if progress:
            progress(1, 1)
        return {s["id"]: 2.0 for s in p["scenes"]}

    def fake_mix(p, items, progress=None):
        out = project_dir(p["id"]) / "output" / "mix.wav"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(b"RIFF")
        return out

    def fake_video(p, items, mix, progress=None):
        out = project_dir(p["id"]) / "output" / "final.mp4"
        out.write_bytes(b"\x00" * 64)
        return out

    def fake_thumb(p, progress=None):
        d = project_dir(p["id"]) / "output" / "thumb"
        d.mkdir(parents=True, exist_ok=True)
        a, b = d / "t1.png", d / "t2.png"
        a.write_bytes(_png(1)); b.write_bytes(_png(2))
        return {"style1": str(a), "style2": str(b)}

    web.synthesize_sync, web.build_mix = fake_tts, fake_mix
    web.render_video, web.render_thumbnails = fake_video, fake_thumb
    try:
        r = client.post(f"/api/projects/{pid}/script/rebuild")
        job_id = r.json().get("job") if r.status_code == 200 else None
        check("재제작 작업 시작(200)", r.status_code == 200 and bool(job_id), r.text[:200])
        jr = {}
        if job_id:
            for _ in range(80):
                jr = client.get(f"/api/jobs/{job_id}").json()
                if jr.get("status") in ("done", "error"):
                    break
                threading.Event().wait(0.1)
        check("재제작 완료", jr.get("status") == "done", str(jr)[:300])
        check("성우가 수정된 대본으로", "수정된 대사입니다. 여기서 반전이 터진다." in (seen.get("texts") or []),
              str(seen.get("texts"))[:200])
        final = client.get(f"/api/projects/{pid}").json()
        check("영상 산출물 기록", bool((final.get("outputs") or {}).get("video")), str(final.get("outputs"))[:200])
        check("script_dirty 해제", final.get("script_dirty") is False, str(final.get("script_dirty")))
        check("완료 상태 문구", "다시 만들었습니다" in (final.get("status") or {}).get("message", ""),
              str((final.get("status") or {}).get("message"))[:120])
        check("타임라인·길이 계산", bool(final.get("timeline")) and (final.get("duration") or 0) > 0,
              str(final.get("duration")))
    finally:
        web.synthesize_sync, web.build_mix = real_tts, real_mix
        web.render_video, web.render_thumbnails = real_video, real_thumb

    print("== 13. 설정 API · /api/meta ==")
    meta = client.get("/api/meta").json()
    check("meta 에 script_engines", set((meta.get("script_engines") or {}).keys()) == {"auto", "gemini", "openai"},
          str(meta.get("script_engines")))
    check("meta config 에 script_engine", meta["config"].get("script_engine") in ("auto", "gemini", "openai"),
          str(meta["config"].get("script_engine")))
    conf = client.post("/api/config", json={"script_engine": "openai"}).json()
    check("POST /api/config script_engine 저장", conf.get("script_engine") == "openai", str(conf.get("script_engine")))
    conf = client.post("/api/config", json={"script_engine": "이상한값"}).json()
    check("잘못된 값은 auto 로", conf.get("script_engine") == "auto", str(conf.get("script_engine")))
    check("public_config 에 엔진 목록", isinstance(conf.get("script_engines"), dict), str(conf.get("script_engines")))
    check("비밀키 노출 없음", "FAKE_KEY_FOR_SELFTEST" not in json.dumps(conf, ensure_ascii=False), "")

    print("== 14. 화면 연결 (app.js · index.html · style.css) ==")
    js = client.get("/static/app.js").text
    for probe in ("btnScriptRead", "btnScriptEdit", "btnScriptSave", "btnScriptRebuild",
                  "/script/rebuild", "saveScript", "rebuildScript", "collectScriptScenes",
                  "openScriptRead", "openScriptEditor", "SCRIPT_DIRTY",
                  "AI 대본 (OpenAI)", "AI 대본 (Gemini)", "applyScriptConfig", "saveScriptEngine"):
        check(f"app.js 에 {probe}", probe in js, "")
    home = client.get("/").text
    for probe in ("scriptEngine", "Gemini (무료) / OpenAI 자동 보조", "scriptEngineBadge",
                  "대본 전체 읽기"):
        check(f"index.html 에 {probe}", probe in home, "")
    css = client.get("/static/style.css").text
    for probe in (".sedit", ".sedit textarea", ".chapter-head", ".sline", ".scriptbox"):
        check(f"style.css 에 {probe}", probe in css, "")
    check("대본 미리보기 옛 읽기전용 블록 제거", "대본 미리보기</label>" not in js, "")
    secrets = ("AIzaSy", "sk-proj-", "Bearer " + "x")
    check("비밀키 없음(푸시 전 점검)",
          not any(k in (js + home + (ROOT / "app" / "openai_script.py").read_text(encoding="utf-8"))
                  for k in secrets), "")

    print()
    print(f"통과 {len(PASS)} · 실패 {len(FAIL)}")
    for f in FAIL:
        print("  ❌", f)
    return 0 if not FAIL else 1


def _err(fn) -> str:
    try:
        fn()
    except Exception as e:
        return f"{type(e).__name__}: {e}"
    return ""


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        traceback.print_exc()
        sys.exit(2)
