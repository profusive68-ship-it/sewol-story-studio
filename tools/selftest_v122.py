"""세월의 사연극장 v1.2.2 — 진행자 확대·LIVE 표시·모션·인물 맞춤 음성 검증.

네트워크·실제 API 호출 없음. PNG 는 실제로 만들어 확인한다.

    python3 tools/selftest_v122.py
"""
from __future__ import annotations

import ast
import shutil
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORK = ROOT / ".cache" / "selftest_v122"

PASS: list[str] = []
FAIL: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    if cond:
        PASS.append(name)
        print(f"  ✅ {name}")
    else:
        FAIL.append(f"{name} — {detail}")
        print(f"  ❌ {name} {detail}")


def main() -> int:
    sys.path.insert(0, str(ROOT))
    shutil.rmtree(WORK, ignore_errors=True)
    WORK.mkdir(parents=True)

    print("== 1. 버전 ==")
    from app import __version__ as pkg_version
    disk = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    check("VERSION == app.__version__", disk == pkg_version, f"{disk} / {pkg_version}")
    check("버전이 1.2.2 이상", tuple(int(x) for x in disk.split(".")) >= (1, 2, 2), disk)

    print("== 2. Python 3.9 문법 호환 ==")
    bad = []
    for folder in ("app", "tools"):
        for f in sorted((ROOT / folder).glob("*.py")):
            try:
                ast.parse(f.read_text(encoding="utf-8"), filename=str(f), feature_version=(3, 9))
            except SyntaxError as e:
                bad.append(f"{f.name}: {e}")
    check("app+tools 전체 ast.parse(3,9)", not bad, "; ".join(bad[:5]))

    print("== 3. 진행자 그래픽 (실제 PNG) ==")
    from PIL import Image
    from app.graphics import (avatar_from_photo, avatar_motion_frames, live_badge,
                              live_badge_frames, make_avatar)
    from app.paths import ASSETS_DIR
    from app.render import avatar_margin, avatar_px, host_portrait

    check("라디오 진행자 초상 2종 준비됨",
          (ASSETS_DIR / "hosts" / "host_male.jpg").exists()
          and (ASSETS_DIR / "hosts" / "host_female.jpg").exists(),
          str(sorted(p.name for p in (ASSETS_DIR / "hosts").glob("*"))))
    check("1080p 아바타 290px", avatar_px(1920, 1080) == 290, str(avatar_px(1920, 1080)))
    check("9:16 아바타 290px", avatar_px(1080, 1920) == 290, str(avatar_px(1080, 1920)))
    check("여백이 자막(92px)과 모서리에 맞게", 16 <= avatar_margin(1920, 1080) <= 60,
          str(avatar_margin(1920, 1080)))

    host = avatar_from_photo(ASSETS_DIR / "hosts" / "host_male.jpg", 580)
    check("사진 아바타 580px(2배) 원형", host.size == (580, 580), str(host.size))
    px = host.load()
    corner = px[2, 2]
    check("원형 크롭(모서리 투명)", corner[3] == 0, str(corner))
    builtin = make_avatar("female", 420)
    check("기본 내장 아바타 유지(폴백)", builtin.size == (420, 420), str(builtin.size))

    b1 = live_badge(1920, 1.0)
    b0 = live_badge(1920, 0.0)
    check("LIVE 배지 알약 크기 합리적", 120 <= b1.width <= 320 and 40 <= b1.height <= 90,
          f"{b1.size}")
    check("LIVE 배지 펄스 프레임이 서로 다름", list(b1.getdata()) != list(b0.getdata()))
    bdir, bn = live_badge_frames(1920, 25, 0.8)
    check("LIVE 점멸 0.8초 = 20프레임", bn == 20, str(bn))
    check("LIVE 프레임 시퀀스 실제 생성", len(list(bdir.glob("l*.png"))) == 20,
          str(len(list(bdir.glob("l*.png")))))
    b1.save(WORK / "live_badge.png")
    host.resize((290, 290), Image.LANCZOS).save(WORK / "avatar_290.png")

    print("== 4. 진행자 모션 ==")
    d, n = avatar_motion_frames(host, 290, key="host_male", fps=25, cycle=6.0, move=1.6)
    files = sorted(d.glob("a*.png"))
    check("6초 주기 = 150프레임", n == 150 and len(files) == 150, f"{n}/{len(files)}")
    import numpy as np
    a0 = np.asarray(Image.open(files[0]).convert("RGBA"), dtype=np.float32)
    a30 = np.asarray(Image.open(files[30]).convert("RGBA"), dtype=np.float32)
    a100 = np.asarray(Image.open(files[100]).convert("RGBA"), dtype=np.float32)
    diff_move = float(np.abs(a0 - a30).mean())
    diff_still = float(np.abs(a0 - a100).mean())
    check("움직임 구간(1.2초)에서 실제 변화", diff_move > 1.5, f"{diff_move:.3f}")
    check("정지 구간에서도 아주 잔잔한 호흡", 0.05 < diff_still < diff_move * 0.6,
          f"{diff_still:.3f} vs move {diff_move:.3f}")

    print("== 5. 진행자 자동 매칭 ==")
    from app.settings import load_config, narrator_gender
    check("multi 해설(edge) → 남성 진행자",
          narrator_gender({"voice_mode": "multi"}, {"tts_engine": "edge"}) == "male")
    check("여성 단독 낭독 → 여성 진행자",
          narrator_gender({"voice_mode": "female"}, {"tts_engine": "edge"}) == "female")
    check("OpenAI onyx 해설 → 남성 진행자",
          narrator_gender({"voice_mode": "multi"}, {"tts_engine": "openai"}) == "male")
    proj = {"id": "selftest", "options": {"avatar_kind": "auto", "voice_mode": "multi"}}
    gender, portrait, key = host_portrait(proj, load_config(), 290)
    check("auto → 남성 초상 선택", gender == "male" and portrait.size == (580, 580),
          f"{gender} {portrait.size} {key}")
    proj_f = {"id": "selftest", "options": {"avatar_kind": "auto", "voice_mode": "female"}}
    gender_f, _, _ = host_portrait(proj_f, load_config(), 290)
    check("auto(여성 낭독) → 여성 초상", gender_f == "female", gender_f)
    proj_m = {"id": "selftest", "options": {"avatar_kind": "male", "voice_mode": "female"}}
    gender_m, _, _ = host_portrait(proj_m, load_config(), 290)
    check("직접 지정 male 우선", gender_m == "male", gender_m)

    print("== 6. 인물 맞춤 음성 캐스팅 ==")
    from app import tts
    from app.settings import AVATAR_KINDS
    check("avatar_kind 기본 'auto'", AVATAR_KINDS.get("auto") is not None, str(AVATAR_KINDS))
    v, i = tts.openai_cast("son", "multi", "40대 후반", "male", "서운한 아들", "conflict")
    check("40대 남성 → onyx", v == "onyx", v)
    check("인물 지시문에 나이 반영", "40대 후반" in i and "성별" in i, i[:80])
    v2, i2 = tts.openai_cast("mother", "multi", "70대 후반", "female",
                             "다정하지만 기력이 약한 병상의 노모", "heal")
    check("70대 여성 → sage", v2 == "sage", v2)
    check("지시문에 성격·상황 반영", "병상" in i2 and "감정" in i2, i2[:80])
    v3, i3 = tts.openai_cast("man", "multi", "30대", "male", "냉정하고 거만한 재벌 2세 팀장", "conflict")
    check("냉정한 인물 → ash", v3 == "ash", v3)
    check("별명 화자는 인물 지시문(청년 지시문 아님)", "라디오 드라마의 등장인물" in i3, i3[:60])
    v4, _ = tts.openai_cast("daughter", "multi", "20대", "여성", "울먹이며 참는 딸", "conflict")
    check("20대 여성 → coral", v4 == "coral", v4)
    v5, i5 = tts.openai_cast("child", "multi", "8세", "male", "밝은 초등학생", "heal")
    check("8세 → verse", v5 == "verse", v5)
    check("공식 보이스 범위 안", all(x in tts.OPENAI_VOICES for x in
          (v, v2, v3, v4, v5)), f"{v},{v2},{v3},{v4},{v5}")
    v6, i6 = tts.openai_cast("narrator", "multi", "", "", "")
    check("메타 없음 → 기존 기본값(하위 호환)", v6 == "onyx" and i6 == tts.OPENAI_INSTRUCTIONS["narrator"])
    v7, i7 = tts.openai_cast("old_male", "multi", "", "", "", "heal")
    check("표준 배역+메타 없음 → 기존 지시문 유지", i7 == tts.OPENAI_INSTRUCTIONS["old_male"])
    v8, i8 = tts.openai_cast("narrator", "multi", "", "", "", "twist")
    check("나이 파싱", (tts.parse_age("70대 후반"), tts.parse_age("78세"), tts.parse_age("8세"),
          tts.parse_age("late 40s")) == (78, 78, 8, 48),
          str((tts.parse_age("70대 후반"), tts.parse_age("78세"), tts.parse_age("8세"), tts.parse_age("late 40s"))))
    ev, ep, er = tts.edge_cast("mil", "multi", 0, "70대 후반", "female", "냉정하고 거만한 시어머니")
    check("edge 70대 여성 → SunHi + 낮은 피치", ev == "ko-KR-SunHiNeural" and int(ep[:-2]) <= -10,
          f"{ev} {ep}")
    ev2, ep2, er2 = tts.edge_cast("son", "multi", 0, "40대", "male", "")
    check("edge 40대 남성 → InJoon", ev2 == "ko-KR-InJoonNeural", f"{ev2} {ep2}")
    ev3, ep3, er3 = tts.edge_cast("narrator", "multi", 0)
    check("edge 메타 없음 → 기존 배역값", (ev3, ep3, er3) ==
          tts._role_cfg("narrator", "multi", 0), f"{ev3} {ep3} {er3}")
    check("tts-1-hd 는 instructions 미전송 유지",
          not tts._supports_instructions("tts-1-hd") and tts._supports_instructions("gpt-4o-mini-tts"))
    payload = tts.openai_payload_preview("테스트", "mother", "multi", 0)
    check("미리보기 payload 도 인물 캐스팅", payload.get("voice") == "onyx"
          and "등장인물" not in payload.get("instructions", "")[:6], str(payload)[:120])

    print("== 7. 캐시 키 분리 ==")
    c_same = tts._cache_path("같은 대사", "openai", "gpt-4o-mini-tts", "onyx", 0, "", 1.0, "지시A")
    c_diff = tts._cache_path("같은 대사", "openai", "gpt-4o-mini-tts", "onyx", 0, "", 1.0, "지시B")
    c_nv = tts._cache_path("같은 대사", "openai", "gpt-4o-mini-tts", "ash", 0, "", 1.0, "지시A")
    check("지시문이 다르면 캐시가 다름", c_same.name != c_diff.name, f"{c_same.name}/{c_diff.name}")
    check("보이스가 다르면 캐시가 다름", c_same.name != c_nv.name)
    c_no = tts._cache_path("같은 대사", "openai", "gpt-4o-mini-tts", "onyx", 0, "", 1.0, "")
    check("메타 없는 과거 대사 캐시 재사용(하위 호환)",
          c_no == tts._cache_path("같은 대사", "openai", "gpt-4o-mini-tts", "onyx", 0, "", 1.0, ""))

    print("== 8. 대본(연기 메타·대화 비중) ==")
    from app.gemini_script import normalize_script
    from app.script_templates import build_template_script
    data = {
        "title": "테스트", "hook": {"line": "아버지가 문을 열었습니다", "scene_ids": ["s01"]},
        "characters": [{"id": "son", "name": "정호", "age": "40대 후반", "gender": "male"}],
        "scenes": [
            {"speaker": "narrator", "text": "아버지가 문을 열었습니다.", "emotion": "heal"},
            {"speaker": "son", "text": "아버지, 이건 왜 아직도 두셨어요.", "emotion": "conflict"},
        ],
        "thumbnail": {"style1": ["엄마의", "마지막"], "style2": ["a", "b", "c"]},
    }
    out = normalize_script(data, {"hook15": True})
    sc2 = next(s for s in out["scenes"] if s["text"].startswith("아버지,"))
    check("설계 인물 정보로 화자 메타 자동 채움",
          sc2.get("speaker_age") == "40대 후반" and sc2.get("speaker_gender") == "male",
          str(sc2.get("speaker_age")))
    old_scenes = {"title": "옛", "hook": {"line": "아버지가 문을 열었습니다", "scene_ids": ["s01"]},
                  "scenes": [{"speaker": "narrator", "text": "아버지가 문을 열었습니다 열었다 떠올랐다 그날",
                              "emotion": "heal", "image_prompt": "x", "image_caption": "y"}]}
    o2 = normalize_script(old_scenes, {"hook15": True})
    check("과거 포맷(메타 없음) 100% 호환",
          all(not s.get("speaker_age") and not s.get("speaker_gender")
              for s in o2["scenes"]),
          str([(s.get("speaker_age"), s.get("speaker_gender")) for s in o2["scenes"]]))
    tpl = build_template_script({"genre": "tear_family", "target_seconds": 300,
                                 "hook15": True, "sequel": True, "preset": "pilot5"})
    tot = sum(len(s["text"]) for s in tpl["scenes"])
    dlg = sum(len(s["text"]) for s in tpl["scenes"] if s["speaker"] != "narrator")
    check("예시 대본 인물 대화 비중 25% 이상", dlg / tot >= 0.25, f"{dlg / tot * 100:.1f}%")
    meta_scenes = [s for s in tpl["scenes"] if s["speaker"] != "narrator"]
    check("예시 대본 대사에 화자 메타 붙음",
          all(s.get("speaker_age") and s.get("speaker_gender") and s.get("speaker_tone")
              for s in meta_scenes),
          str(meta_scenes[0].get("speaker_tone", "")) if meta_scenes else "none")
    sys_rules = __import__("app.gemini_script", fromlist=["SYSTEM_RULES"]).SYSTEM_RULES
    check("AI 프롬프트에 30~40% 대화 지침", "30~40%" in sys_rules and "speaker_age" in sys_rules)
    check("AI 프롬프트에 speaker_tone 지침", "speaker_tone" in sys_rules)

    print("== 9. 자막과 진행자 겹침 방지 ==")
    from app.subtitles import write_ass
    proj = {"id": "selftest_sub", "duration": 10.0, "format": {"aspect": "9:16"},
            "options": {"avatar": True, "subtitle_size": "senior", "no_brand": False},
            "scenes": [{"id": "s01", "speaker": "narrator", "text": "테스트 대사"}]}
    items = [{"scene_id": "s01", "speaker": "narrator", "text": "테스트 대사", "start": 0.2, "end": 2.0}]
    p = write_ass(proj, items, WORK / "subs.ass", 1080, 1920)
    style = next(l for l in p.read_text(encoding="utf-8").splitlines() if l.startswith("Style: narrator"))
    margin_v = int(style.split(",")[-2])
    check("세로 화면 자막이 진행자 위로", margin_v >= 320, f"marginV={margin_v}")
    proj_h = dict(proj, format={"aspect": "16:9"})
    p2 = write_ass(proj_h, items, WORK / "subs169.ass", 1920, 1080)
    style2 = next(l for l in p2.read_text(encoding="utf-8").splitlines() if l.startswith("Style: narrator"))
    margin_v2 = int(style2.split(",")[-2])
    check("가로 화면 자막 위치 유지", margin_v2 == int(1080 * 0.135), f"marginV={margin_v2}")

    print("== 10. 화면·옵션 반영 ==")
    idx = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
    for probe in ("liveBadge", 'value="auto"', "290px", "LIVE 표시"):
        check(f"index.html 에 {probe}", probe in idx)
    js = (ROOT / "static" / "app.js").read_text(encoding="utf-8")
    for probe in ("live_badge: $(\"#liveBadge\").checked", 'avatarKind: "auto"'):
        check(f"app.js 에 {probe}", probe in js)
    main_src = (ROOT / "app" / "main.py").read_text(encoding="utf-8")
    check("CreateIn live_badge 기본 ON", "live_badge: bool = True" in main_src)
    check("자동 생성 payload 에 live_badge", '"live_badge": True' in main_src)
    proj_src = (ROOT / "app" / "project.py").read_text(encoding="utf-8")
    check("프로젝트 옵션 저장(live_badge)", '"live_badge": bool(payload.get("live_badge", True))' in proj_src)
    check("비밀키 없음(푸시 전 점검)",
          not any(k in (main_src + proj_src + js) for k in ("sk-", "AIza", "Bearer " + "x")))

    print()
    print(f"통과 {len(PASS)} · 실패 {len(FAIL)}")
    for f in FAIL:
        print("  ❌", f)
    check_png = WORK / "live_badge.png"
    print(f"  (확인용 PNG: {check_png} · {WORK / 'avatar_290.png'})")
    return 0 if not FAIL else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        traceback.print_exc()
        sys.exit(2)
