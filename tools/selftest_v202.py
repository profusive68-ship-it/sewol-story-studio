"""세월의 사연극장 v2.0.2 — 인물 화자 자동 배정 · 균일 속도 조절 폭 확대(±15%) 검증.

네트워크·ffmpeg·실제 API 호출 없음. (AI 대본 응답은 가짜로 흉내낸다)

    python3 tools/selftest_v202.py
"""
from __future__ import annotations

import ast
import json
import shutil
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORK = ROOT / ".cache" / "selftest_v202"

PASS: list[str] = []
FAIL: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    if cond:
        PASS.append(name)
        print(f"  ✅ {name}")
    else:
        FAIL.append(f"{name} — {detail}")
        print(f"  ❌ {name} {detail}")


# ── 가짜 AI 응답 (2단계: 설계 → 집필) ─────────────────────────────────────
DESIGN = {
    "title": "김치통에 숨은 이십 년",
    "titles": ["김치통에 숨은 이십 년", "어머니의 마지막 김치통", "이십 년 동안 넣어 둔 돈"],
    "logline": "세상을 떠난 어머니의 김치통에서 이십 년 치 적금 기록이 나왔다.",
    "description": "줄거리 1\n줄거리 2\n줄거리 3",
    "hashtags": ["#사연", "#감동사연", "#가족사연"],
    "setting": "2026년 제주 서귀포, 낡은 기와집",
    "characters": [
        {"id": "mother", "name": "어머니", "relation": "아들의 어머니", "age": "70대 후반",
         "gender": "female", "habit": "말끝을 흐린다",
         "desc_en": "Korean grandmother, late 70s, silver hair, floral apron"},
        {"id": "son", "name": "아들 정호", "relation": "아들", "age": "40대 후반",
         "gender": "male", "habit": "한숨을 자주 쉰다",
         "desc_en": "Korean man, late 40s, short graying hair, navy jacket"},
    ],
    "evidence": [{"item": "국민은행 통장", "detail": "2003년 3월 14일 3만 원", "meaning": "몰래 넣은 돈"}],
    "acts": [{"act": 1, "name": "발단", "summary": "김치통을 연다", "plant": "통", "payoff": "통장"}],
    "hook": {"line": "그 돈, 대체 어디서 난 거야?", "situation": "부엌", "rewind_caption": "사흘 전, 그날"},
    "chapters": [{"index": 1, "act": 1, "title": "김치통", "beat": "훅→되감기→갈등→반전→여운",
                  "pov": "아들 정호"}],
    "sequel_teaser": "육 개월 뒤, 그 김치통이 다시 놓였다.",
    "next_story": {"title": "아버지의 손목시계", "teaser": "다음 사연 예고."},
    "thumbnail": {"style1": ["김치통", "이십 년의 비밀"],
                  "style2": ["어머니, 이게 뭐야?", "몰래 넣어 둔 돈", "이십 년", "끝까지 보세요"]},
    "upload": {"title": "김치통에 숨은 이십 년", "description": "설명", "tags": ["사연"]},
}

# 첫 두 장면 = 훅 구간(hook.line 포함). 훅 구간 밖의 해설-대사가 자동 배정 대상이다.
PART = {
    "scenes": [
        {"speaker": "narrator", "text": "그 돈, 대체 어디서 난 거야?",
         "emotion": "twist", "sfx": ["심장박동"],
         "image_prompt": "Cinematic still, a man at a kimchi pot", "image_caption": "김치통 앞의 아들"},
        {"speaker": "narrator", "text": "사흘 전, 아무것도 몰랐던 그날.",
         "emotion": "twist", "sfx": [],
         "image_prompt": "Cinematic still, old Korean house", "image_caption": "사흘 전 그날"},
        {"speaker": "narrator", "text": "집 안은 그대로였습니다. 다만 모든 물건 위에 하얀 먼지가 앉아 있었습니다.",
         "emotion": "conflict", "sfx": ["문 삐걱"],
         "image_prompt": "Cinematic still, dusty Korean home", "image_caption": "먼지 앉은 집"},
        {"speaker": "narrator", "text": "어머니, 이게 대체 무슨 말이야?",
         "emotion": "conflict", "sfx": ["한숨"],
         "image_prompt": "Cinematic still, man holding an envelope", "image_caption": "봉투를 든 아들"},
        {"speaker": "어머니", "text": "정호야, 엄마가 밥을 못 챙겨 줄 때는 이 김치통을 열어라.",
         "emotion": "heal", "sfx": ["종이 바스락"],
         "image_prompt": "Cinematic still, handwritten note", "image_caption": "어머니의 쪽지"},
        {"speaker": "narrator", "text": "봉투마다 날짜가 적혀 있었습니다. 이십 년 전부터 시작된 날짜였습니다.",
         "emotion": "twist", "sfx": [],
         "image_prompt": "Cinematic still, stacked envelopes", "image_caption": "봉투의 날짜"},
        {"speaker": "narrator", "text": "그때 왜 아무 말도 안 했어요.",
         "emotion": "conflict", "sfx": [],
         "image_prompt": "Cinematic still, man looking down", "image_caption": "묻는 아들"},
        {"speaker": "narrator", "text": "정호는 처음으로 혼자 김치를 담갔습니다. 어머니처럼 소매를 걷고.",
         "emotion": "heal", "sfx": ["찻잔"],
         "image_prompt": "Cinematic still, man salting cabbage", "image_caption": "혼자 담근 김치"},
    ]
}


def main() -> int:
    print("== 1. 버전 · 문서 · Python 3.9 ==")
    disk = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    init_src = (ROOT / "app" / "__init__.py").read_text(encoding="utf-8")
    check("VERSION == 2.0.2", disk == "2.0.2", disk)
    check("app.__version__ == 2.0.2", f'"{disk}"' in init_src, init_src.strip().splitlines()[-1])
    index_src = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
    appjs_src = (ROOT / "static" / "app.js").read_text(encoding="utf-8")
    check("index.html 캐시버스터 ?v=2.0.2 (css·js)", index_src.count("?v=2.0.2") == 2,
          str(index_src.count("?v=2.0.2")))
    check("index.html verTag 2.0.2", "id=\"verTag\">v2.0.2<" in index_src, "")
    readme = (ROOT / "README_맥북설치방법.txt").read_text(encoding="utf-8")
    check("설명서 머리말 버전 일치", f"(v{disk})" in readme.splitlines()[1], readme.splitlines()[1])
    for probe in ("4단계 스튜디오", "시나리오 추천받기", "호흡", "assets_inbox", "대본 전체",
                  "OpenAI 자동 보조", "인물 화자 자동 배정", "x0.85 ~ x1.15"):
        check(f"설명서에 '{probe}'", probe in readme, "")

    bad: list[str] = []
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

    print("== 2. 임시 폴더 준비 ==")
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
    from app import speakers as SP  # noqa: E402
    from app import tts as T  # noqa: E402
    from app.paths import project_dir  # noqa: E402
    from app.project import create_project, load  # noqa: E402
    from app.settings import save_config  # noqa: E402
    from app.speakers import (assign_dialogue_speakers, looks_like_dialogue,  # noqa: E402
                              resolve_speaker)

    check("임시 사본 버전 일치", pkg_version == disk, f"{pkg_version}/{disk}")
    client = TestClient(web.app)

    print("== 3. AI 프롬프트에 화자 배정 규칙 ==")
    rules = gs.SYSTEM_RULES
    for probe in ("화자 배정 — 최우선", "narrator` 는 **해설(3인칭 서술)에만**",
                  "인물이 직접 말하는 대사는 절대 `narrator` 로 적지 않는다",
                  "대사 판별 기준", "speaker_age", "speaker_gender"):
        check(f"SYSTEM_RULES 에 '{probe[:28]}'", probe in rules, "")
    settings50 = {"genre": "tear_family", "target_seconds": 50, "preset": "shorts50", "tone": "warm"}
    design_prompt = gs._short_design_prompt(dict(settings50, topic="어머니와 아들"))
    check("설계 프롬프트가 인물 성별을 함께 받는다", '"gender":"female"' in design_prompt,
          design_prompt[-400:])
    # 본편(90초 초과) 설계 프롬프트 — 예전엔 중괄호 오류로 예외가 나 예시 대본으로 대체됐다
    long_prompt = gs._design_prompt({"genre": "tear_family", "target_seconds": 600,
                                     "preset": "pilot5", "topic": "어머니와 아들", "tone": "warm"}, 5, 3)
    check("본편 설계 프롬프트가 정상 생성", "acts 는 정확히 5개" in long_prompt
          and "chapters 는 정확히 3개" in long_prompt, long_prompt[-160:])
    check("본편 설계 프롬프트 JSON 예시 유지", '"next_story": {"title"' in long_prompt, "")
    write_prompt = gs._write_prompt(settings50, DESIGN, DESIGN["chapters"][0], 220, [], True, True,
                                    "8~10장면, 12~22자 짧은 호흡")
    check("집필 프롬프트에 화자 배정 규칙", "화자 배정(speaker)" in write_prompt, "")
    check("집필 프롬프트 JSON 예시가 인물 이름", '"speaker":"아들"' in write_prompt, "")
    check("집필 프롬프트에 narrator 오용 예시 없음", '"speaker":"son"' not in write_prompt, "")
    check("집필 프롬프트가 해설 예시를 함께 보여 준다", '"speaker":"narrator"' in write_prompt, "")

    print("== 4. 화자 표기 → 배역 확정 (resolve_speaker) ==")
    chars = DESIGN["characters"]
    cases = {"어머니": "old_female", "엄마": "old_female", "시어머니": "old_female",
             "아들": "young_male", "아들 정호": "young_male", "son": "young_male",
             "며느리": "female", "딸": "female", "여성": "female", "남성": "young_male",
             "아이": "child", "손자": "child", "해설": "narrator", "narrator": "narrator",
             "나레이션": "narrator", "": "narrator", "김밥": "narrator"}
    for raw, want in cases.items():
        got, name = resolve_speaker(raw, chars)
        check(f"'{raw}' → {want}", got == want, f"{got} ({name})")
    check("배역 표기는 그대로", [resolve_speaker(r, chars)[0] for r in SP.SPEAKER_ROLES]
          == list(SP.SPEAKER_ROLES), "")
    check("이름 표시는 대본의 인물 이름", resolve_speaker("son", chars)[1] == "아들 정호",
          resolve_speaker("son", chars)[1])
    check("나이·성별만 있어도 배역", resolve_speaker("누군가", [], age="70대 후반", gender="female")[0]
          == "old_female", "")
    check("60대 이상 남성은 노인", SP.role_for("male", 68) == "old_male", "")
    check("10대 여성은 여성역", SP.role_for("female", 17) == "female", "")
    check("12세 이하는 아이", SP.role_for("male", 9) == "child", "")

    print("== 5. 대사 판별 (해설을 대사로 오인하지 않는다) ==")
    lines = [("어머니, 이게 대체 무슨 말이야?", True),
             ("\"그 돈은 대체 어디서 난 거야?\"", True),
             ("정호야, 밥은 먹었니?", True),
             ("여보, 이게 무슨 일이야.", True),
             ("며느리야, 들어와라.", True),
             ("내가 그때 왜 그랬을까.", True),
             ("이제 그만하세요.", True),
             ("네, 알겠습니다.", True),
             ("그래, 알았다.", True)]
    for text, want in lines:
        got, _ = looks_like_dialogue(text)
        check(f"대사로 판별: {text[:20]}", got is want, str(got))
    narr = ["집 안은 그대로였습니다. 다만 모든 물건 위에 하얀 먼지가 앉아 있었습니다.",
            "그는 김치통 뚜껑을 열었습니다.",
            "봉투마다 날짜가 적혀 있었습니다.",
            "사흘 전, 아무것도 몰랐던 그날.",
            "그해 겨울, 어머니가 쓰러졌다.",
            "유언장에는 이렇게 적혀 있었습니다. 이십 년 동안 내 밥을 챙긴 사람에게."]
    for text in narr:
        got, _ = looks_like_dialogue(text)
        check(f"해설은 그대로: {text[:18]}", got is False, str(got))

    print("== 6. 해설로 적힌 대사 → 문맥상 화자 ==")
    scenes = [
        {"id": "s01", "speaker": "narrator", "text": "어머니, 이게 대체 무슨 말이야?"},
        {"id": "s02", "speaker": "narrator", "text": "집 안은 그대로였습니다. 먼지만 앉아 있었습니다."},
        {"id": "s03", "speaker": "어머니", "text": "정호야, 밥은 먹었니?"},
        {"id": "s04", "speaker": "narrator", "text": "사흘 전, 아무것도 몰랐던 그날.",
         "placement": "after_hook"},
        {"id": "s05", "speaker": "narrator", "text": "그 돈, 어디서 났어?"},
    ]
    assign_dialogue_speakers(scenes, chars, exclude_ids=["s05"])
    check("호칭 대사는 듣는 사람이 아닌 화자로", scenes[0]["speaker"] == "young_male",
          scenes[0]["speaker"])
    check("자동 배정 장면에 표시(speaker_auto)", scenes[0].get("speaker_auto") is True, "")
    check("자동 배정 때 인물 나이·성별도 채운다",
          scenes[0].get("speaker_age") == "40대 후반" and scenes[0].get("speaker_gender") == "male",
          str((scenes[0].get("speaker_age"), scenes[0].get("speaker_gender"))))
    check("해설 문장은 narrator 유지", scenes[1]["speaker"] == "narrator", scenes[1]["speaker"])
    check("이름으로 적힌 화자도 배역으로", scenes[2]["speaker"] == "old_female",
          scenes[2]["speaker"])
    check("이름은 speaker_name 에 남긴다", scenes[2].get("speaker_name") == "어머니",
          str(scenes[2].get("speaker_name")))
    check("되감기 카드(placement)는 narrator 유지", scenes[3]["speaker"] == "narrator",
          scenes[3]["speaker"])
    check("고정 장면(exclude_ids)은 건드리지 않는다", scenes[4]["speaker"] == "narrator",
          scenes[4]["speaker"])
    check("디자인이 넣은 훅 카드는 건드리지 않는다",
          assign_dialogue_speakers([{"id": "s01", "speaker": "narrator", "hook_line": True,
                                     "text": "어머니, 이게 무슨 말이야?"}], chars)[0]["speaker"]
          == "narrator", "")
    # 듣는 사람이 직전 화자면 그 목소리를 이어 쓰지 않는다
    turn = [{"id": "s01", "speaker": "narrator", "text": "정호야, 밥은 먹었니?"},
            {"id": "s02", "speaker": "narrator", "text": "어머니, 이게 무슨 말이야?"}]
    assign_dialogue_speakers(turn, chars)
    check("대화가 오갈 때 듣는 사람 목소리를 이어 쓰지 않는다",
          turn[0]["speaker"] == "old_female" and turn[1]["speaker"] == "young_male",
          str([t["speaker"] for t in turn]))
    # '엄마'와 인물 이름 '어머니 순자'는 같은 사람 — 듣는 사람으로 본다
    hon = [{"id": "mother", "name": "어머니 순자", "age": "70대 후반", "gender": "female"},
           {"id": "son", "name": "아들 정호", "age": "40대 후반", "gender": "male"}]
    h1 = [{"id": "s01", "speaker": "narrator", "text": "엄마, 이게 뭔데요?"}]
    assign_dialogue_speakers(h1, hon)
    check("호칭 변형(엄마↔어머니)도 듣는 사람으로 본다", h1[0]["speaker"] == "young_male",
          h1[0]["speaker"])
    amb = [{"id": "s01", "speaker": "narrator", "text": "이혼해. 우리 집에 너 같은 사람 필요 없어."}]
    assign_dialogue_speakers(amb, chars)
    check("누구인지 애매하면 해설로 둔다(엉뚱한 목소리 방지)", amb[0]["speaker"] == "narrator",
          amb[0]["speaker"])
    all_roles = set(SP.SPEAKER_ROLES)
    check("모든 speaker 가 배역 6종 안", all(s["speaker"] in all_roles for s in scenes),
          str([s["speaker"] for s in scenes]))

    print("== 7. AI 대본 생성 → 정규화 (가짜 응답) ==")
    real_call = gs._call
    seen_prompts: list[str] = []

    def fake_call(cfg, prompt, temperature=0.9, on_engine=None):
        seen_prompts.append(prompt)
        if on_engine:
            on_engine("gemini")
        return DESIGN if "1단계 설계" in prompt else PART

    gs._call = fake_call
    try:
        raw = gs.generate_script(settings50, {"gemini_api_key": "FAKE_FOR_SELFTEST",
                                              "script_engine": "gemini"})
        check("집필 프롬프트가 실제로 나갔다", any("2단계 집필" in p for p in seen_prompts),
              str(len(seen_prompts)))
        write_prompts = [p for p in seen_prompts if "2단계 집필" in p]
        check("집필 프롬프트 모두에 화자 배정 규칙", bool(write_prompts)
              and all("화자 배정" in p for p in write_prompts), str(len(write_prompts)))
        script = gs.normalize_script(raw, settings50)
        scenes = script["scenes"]
        check("정규화 후 모든 speaker 가 배역", all(s["speaker"] in all_roles for s in scenes),
              str([(s["id"], s["speaker"]) for s in scenes]))
        by_text = {s["text"]: s for s in scenes}
        hook = by_text.get("그 돈, 대체 어디서 난 거야?")
        check("호칭 없는 훅 대사는 해설 유지(애매하면 그대로)", hook is not None
              and hook["speaker"] == "narrator", str(hook and hook["speaker"]))
        dlg = by_text.get("어머니, 이게 대체 무슨 말이야?")
        check("훅 밖의 해설-대사는 인물로 자동 배정",
              dlg is not None and dlg["speaker"] != "narrator", str(dlg and dlg["speaker"]))
        check("자동 배정이 아들 목소리(young_male)", dlg is not None and dlg["speaker"] == "young_male",
              str(dlg and dlg["speaker"]))
        mom = by_text.get("정호야, 엄마가 밥을 못 챙겨 줄 때는 이 김치통을 열어라.")
        check("'어머니'로 적힌 화자가 old_female 로", mom is not None and mom["speaker"] == "old_female",
              str(mom and mom["speaker"]))
        narr_sc = by_text.get("집 안은 그대로였습니다. 다만 모든 물건 위에 하얀 먼지가 앉아 있었습니다.")
        check("해설 문장은 narrator 유지(정규화)", narr_sc is not None and narr_sc["speaker"] == "narrator",
              str(narr_sc and narr_sc["speaker"]))
        dlg_count = sum(1 for s in scenes if s["speaker"] != "narrator")
        check("대화 인물 장면 2개 이상", dlg_count >= 2, str(dlg_count))
    finally:
        gs._call = real_call

    print("== 8. 속도 조절 폭 ±15% (모든 화자 동일) ==")
    check("기준 속도 1.00", T.NARRATION_SPEED == 1.00, str(T.NARRATION_SPEED))
    check("조절 폭 0.15", T.SPEED_RANGE == 0.15, str(T.SPEED_RANGE))
    check("uniform_speed 경계", (T.uniform_speed(0), T.uniform_speed(15), T.uniform_speed(-15))
          == (1.0, 1.15, 0.85), str((T.uniform_speed(0), T.uniform_speed(15), T.uniform_speed(-15))))
    check("uniform_speed 는 범위를 넘지 않는다",
          (T.uniform_speed(99), T.uniform_speed(-99)) == (1.15, 0.85),
          str((T.uniform_speed(99), T.uniform_speed(-99))))
    check("uniform_rate ±15%", (T.uniform_rate(0), T.uniform_rate(15), T.uniform_rate(-15),
                                T.uniform_rate(99)) == (0, 15, -15, 15),
          str((T.uniform_rate(0), T.uniform_rate(15), T.uniform_rate(-15), T.uniform_rate(99))))
    check("화자 사이 허용 편차 상수는 0.03 그대로", T.SPEED_TOLERANCE == 0.03, str(T.SPEED_TOLERANCE))
    check("속도 규칙 문구 유지", "해설자와 똑같은" in T.with_speed_rule("연기 지시"), "")
    e_old = T.edge_cast("old_male", "multi", 12, "", "", "")
    e_narr = T.edge_cast("narrator", "multi", 12, "", "", "")
    check("인물 정보 없는 배역도 같은 속도(edge)", e_old[2] == 12 and e_narr[2] == 12,
          str((e_old[2], e_narr[2])))

    print("== 9. 목소리 표 — '여성'/'남성' 화자도 해설과 다른 목소리 ==")
    proj = {
        "id": "speed-probe", "options": {"voice_mode": "multi", "rate": 12},
        "scenes": [
            {"id": "s01", "speaker": "narrator", "text": "집 안은 그대로였습니다.", "emotion": "heal"},
            {"id": "s02", "speaker": "여성", "text": "어머니, 이게 무슨 말이야?", "emotion": "conflict"},
            {"id": "s03", "speaker": "남성", "text": "그 돈, 어디서 났어?", "emotion": "conflict"},
        ],
        "characters": [],
    }
    plan = T.project_voice_plan(proj, engine="openai", mode="multi")
    narr_voice = plan["narrator"]["voice"]
    voices = {k: v["voice"] for k, v in plan["speakers"].items() if v["role"] != "narrator"}
    check("'여성' 화자는 해설과 다른 목소리", all(v != narr_voice for v in voices.values()),
          str(voices))
    check("'여성'/'남성' 화자끼리도 다른 목소리", len(set(voices.values())) == len(voices), str(voices))
    check("목소리 표 속도는 모두 x1.12",
          all(abs(float(s["speed"]) - 1.12) <= 0.0001 for s in plan["speakers"].values()),
          str([s["speed"] for s in plan["speakers"].values()]))
    check("narrator 표 속도도 x1.12", abs(float(plan["narrator"]["speed"]) - 1.12) <= 0.0001,
          str(plan["narrator"]["speed"]))
    check("속도 균일 검사 통과", max(T.speed_values(plan)) - min(T.speed_values(plan)) <= 0.0001,
          str(T.speed_values(plan)))
    eplan = T.project_voice_plan(proj, engine="edge", mode="multi")
    erates = {s.get("edge_rate") for s in eplan["speakers"].values()}
    check("edge 폴백도 같은 속도", erates == {12}, str(erates))
    label = T.speaker_label("old_female||", {"speaker_name": "어머니"})
    check("목소리 표 이름에 인물 이름 사용", label.startswith("어머니"), label)

    print("== 10. 프로젝트 생성 — 화자 확정 · 속도 저장 ==")
    save_config({"gemini_api_key": "", "openai_api_key": "", "tts_engine": "edge",
                 "script_engine": "auto"})
    p_fast = create_project({"preset": "shorts50", "genre": "inlaw", "topic": "며느리의 반격",
                             "rate": 99, "image_mode": "B"})
    check("속도 상한 15% 로 저장", (p_fast.get("options") or {}).get("rate") == 15,
          str((p_fast.get("options") or {}).get("rate")))
    p_slow = create_project({"preset": "shorts50", "genre": "free", "topic": "느린 목소리",
                             "rate": -99, "image_mode": "B"})
    check("속도 하한 -15% 로 저장", (p_slow.get("options") or {}).get("rate") == -15,
          str((p_slow.get("options") or {}).get("rate")))
    p = load(p_fast["id"])
    spk = [s.get("speaker") for s in p["scenes"]]
    check("예시 대본 화자도 배역 6종", all(x in all_roles for x in spk),
          str(sorted({x for x in spk if x not in all_roles})))
    check("예시 대본에도 인물 이름 남김",
          any(s.get("speaker_name") for s in p["scenes"]), "")
    plan2 = T.project_voice_plan(p)
    check("목소리 표 속도 균일(x1.15)", max(T.speed_values(plan2)) - min(T.speed_values(plan2)) <= 0.0001
          and abs(plan2["speed"] - 1.15) <= 0.0001, str(T.speed_values(plan2)))

    # 1단계에서 화자를 이름으로 고쳐 저장
    target = p["scenes"][0]
    r = client.post(f"/api/projects/{p['id']}/tts/preview",
                    json={"scene_id": target["id"], "speaker": "어머니", "save": True})
    if r.status_code == 200:
        after = client.get(f"/api/projects/{p['id']}").json()
        edited = next((s for s in after["scenes"] if s["id"] == target["id"]), None)
        check("이름으로 저장한 화자가 배역으로", edited is not None
              and edited["speaker"] in all_roles and edited["speaker"] != "narrator",
              str(edited and edited.get("speaker")))
    else:
        print(f"  (음성 엔진 없음 — 저장 검사는 직접 호출로 대체: {r.status_code})")
        from app.project import save_edited_script
        rows = [{"id": s["id"], "text": s["text"], "speaker": s["speaker"]} for s in load(p["id"])["scenes"]]
        rows[0]["speaker"] = "어머니"
        proj_now = load(p["id"])
        save_edited_script(proj_now, rows)
        check("이름으로 저장한 화자가 배역으로", proj_now["scenes"][0]["speaker"] in all_roles
              and proj_now["scenes"][0]["speaker"] != "narrator",
              str(proj_now["scenes"][0]["speaker"]))

    print("== 11. API · 화면 연결 ==")
    meta = client.get("/api/meta").json()
    std = meta.get("voice_standard") or {}
    check("/api/meta 속도 범위 ±0.15", std.get("range") == 0.15, str(std))
    check("/api/meta 슬라이더 범위 -15~15", (std.get("rate_min"), std.get("rate_max")) == (-15, 15), str(std))
    check("/api/meta 균일 속도 안내", "같은 속도" in str(std.get("uniform")), str(std.get("uniform")))
    sv = client.get(f"/api/projects/{p['id']}/script").json()
    labels = [s.get("speaker_label") for g in sv.get("chapters") or [] for s in g.get("scenes") or []]
    check("대본 전문에 인물 이름으로 화자 표시", any(l and l not in
          ("해설", "노인", "할머니", "여성", "청년", "아이") for l in labels), str(labels[:6]))

    voices = client.get(f"/api/projects/{p['id']}/voices").json()
    check("GET /voices 속도 균일", voices.get("speed_uniform") is True, str(voices.get("speeds")))
    check("GET /voices 해설·인물 분리", voices.get("separated") is True,
          str(voices.get("violations")))

    home = client.get("/").text
    check("index.html 슬라이더 -15~15", 'id="rate" min="-15" max="15"' in home, "")
    check("index.html 균일 속도 안내 문구",
          "모든 화자에게 같은 속도가 적용됩니다 (균일 속도 유지)" in home, "")
    check("index.html 0.85~1.15배 안내", "0.85배 ~ 1.15배" in home, "")
    js = client.get("/static/app.js").text
    check("app.js 에 rateText", "function rateText" in js, "")
    check("대사 목록에 인물 이름 태그", 's.speaker_name && s.speaker_name !== SPEAKER_LABEL[s.speaker]' in js, "")
    check("app.js 속도 표시에 배율", "x${x}" in js, "")
    check("index.html 이 v2.0.2 자산을 부른다", "/static/app.js?v=2.0.2" in home, "")

    print("== 12. 비밀키 없음(푸시 전 점검) ==")
    blob = js + home + (ROOT / "app" / "main.py").read_text(encoding="utf-8") + \
        (ROOT / "app" / "tts.py").read_text(encoding="utf-8") + \
        (ROOT / "app" / "speakers.py").read_text(encoding="utf-8")
    check("비밀키 흔적 없음",
          not any(k in blob for k in ("AIzaSy", "sk-proj-", "Bearer " + "x")), "")

    print()
    print(f"통과 {len(PASS)} · 실패 {len(FAIL)}")
    for f in FAIL:
        print("  ❌", f)
    return 0 if not FAIL else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        traceback.print_exc()
        sys.exit(2)
