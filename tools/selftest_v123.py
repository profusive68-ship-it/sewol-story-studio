"""세월의 사연극장 v1.2.3 — 진행자 반측면 성우 사진·멀티프레임 발화 모션 검증.

네트워크·ffmpeg·실제 API 호출 없음. PNG 는 실제로 만들어 확인한다.

    python3 tools/selftest_v123.py
"""
from __future__ import annotations

import ast
import shutil
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORK = ROOT / ".cache" / "selftest_v123"

PASS: list[str] = []
FAIL: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    if cond:
        PASS.append(name)
        print(f"  ✅ {name}")
    else:
        FAIL.append(f"{name} — {detail}")
        print(f"  ❌ {name} {detail}")


def _gray(path: Path, s: int = 256):
    import numpy as np
    from PIL import Image
    return np.asarray(Image.open(path).convert("L").resize((s, s), Image.LANCZOS), dtype=np.float32)


def _diff_stats(a, b, thr: float = 28.0):
    """(임계값 넘는 픽셀 수, 전체 평균 차이, 그 픽셀들의 경계 상자) — 256x256 기준."""
    import numpy as np
    d = np.abs(a - b)
    ys, xs = np.where(d > thr)
    if len(xs) == 0:
        return 0, float(d.mean()), None
    return len(xs), float(d.mean()), (xs.min(), xs.max(), ys.min(), ys.max())


def main() -> int:
    sys.path.insert(0, str(ROOT))
    shutil.rmtree(WORK, ignore_errors=True)
    WORK.mkdir(parents=True)

    print("== 1. 버전 ==")
    from app import __version__ as pkg_version
    disk = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    check("VERSION == app.__version__", disk == pkg_version, f"{disk} / {pkg_version}")
    check("버전이 1.2.3 이상", tuple(int(x) for x in disk.split(".") if x.isdigit()) >= (1, 2, 3), disk)
    readme = (ROOT / "README_맥북설치방법.txt").read_text(encoding="utf-8")
    check("설명서 머리말 버전 일치", f"(v{disk})" in readme, readme.splitlines()[1])

    print("== 2. Python 3.9 문법 호환 ==")
    bad = []
    for folder in ("app", "tools"):
        for f in sorted((ROOT / folder).glob("*.py")):
            try:
                ast.parse(f.read_text(encoding="utf-8"), filename=str(f), feature_version=(3, 9))
            except SyntaxError as e:
                bad.append(f"{f.name}: {e}")
    check("app+tools 전체 ast.parse(3,9)", not bad, "; ".join(bad[:5]))

    print("== 3. 진행자 사진(반측면·마이크) 3장씩 ==")
    from app.paths import ASSETS_DIR
    hosts = ASSETS_DIR / "hosts"
    names = {g: [hosts / f"host_{g}{s}.jpg" for s in ("", "_2", "_3")] for g in ("male", "female")}
    for g, paths in names.items():
        check(f"{g} 프레임 3장 준비", all(p.exists() for p in paths),
              str(sorted(p.name for p in hosts.glob("*.jpg"))))
    from PIL import Image
    sizes = {p.name: Image.open(p).size for g in names for p in names[g] if p.exists()}
    check("사진이 모두 정사각(원형 크롭 대응)", len(set(sizes.values())) == 1 and
          list(sizes.values())[0][0] == list(sizes.values())[0][1], str(sizes))

    worst_local = 0.0
    worst_mean = 0.0
    for g in ("male", "female"):
        base = _gray(names[g][0])
        for p in names[g][1:]:
            if not p.exists():
                continue
            n, mean, box = _diff_stats(base, _gray(p))
            worst_local = max(worst_local, n / (256 * 256))
            worst_mean = max(worst_mean, mean)
            check(f"{g} {p.stem}: 같은 인물·같은 배경(차이가 입 주변에만)",
                  n / (256 * 256) < 0.08 and mean < 6.0,
                  f"다른 픽셀 {n / (256 * 256) * 100:.1f}% · 평균차 {mean:.2f} · box {box}")
    print(f"  (최대 국소차 {worst_local * 100:.1f}% · 최대 평균차 {worst_mean:.2f})")

    print("== 4. 진행자 선택(성별·내 사진) ==")
    from app.render import avatar_px, host_portrait, host_portraits
    from app.settings import load_config
    check("1080p 아바타 290px", avatar_px(1920, 1080) == 290, str(avatar_px(1920, 1080)))
    check("9:16 아바타 290px", avatar_px(1080, 1920) == 290, str(avatar_px(1080, 1920)))
    gender, portraits, key = host_portraits(
        {"id": "selftest", "options": {"avatar_kind": "auto", "voice_mode": "multi"}}, load_config(), 290)
    check("multi 해설 → 남성 3프레임", gender == "male" and len(portraits) == 3,
          f"{gender} {len(portraits)}")
    check("초상 580px(2배)", all(p.size == (580, 580) for p in portraits),
          str([p.size for p in portraits]))
    g_f, p_f, _ = host_portraits(
        {"id": "selftest", "options": {"avatar_kind": "auto", "voice_mode": "female"}}, load_config(), 290)
    check("여성 낭독 → 여성 3프레임", g_f == "female" and len(p_f) == 3, f"{g_f} {len(p_f)}")
    g_m, _, _ = host_portraits(
        {"id": "selftest", "options": {"avatar_kind": "male", "voice_mode": "female"}}, load_config(), 290)
    check("직접 지정 male 우선", g_m == "male", g_m)
    check("캐시 키에 사진 지문(mtime) 포함", key.startswith("host_male_") and key != "host_male", key)
    _, one, key_one = host_portrait(
        {"id": "selftest", "options": {"avatar_kind": "female"}}, load_config(), 290)
    check("(하위 호환) host_portrait 대표 1장", one.size == (580, 580), str(one.size))
    corner = one.load()[2, 2]
    check("원형 크롭(모서리 투명)", corner[3] == 0, str(corner))

    print("== 5. 발화 모션(멀티프레임) ==")
    import numpy as np
    from app.graphics import (avatar_motion_frames, _avatar_pose, _avatar_weights,
                              _nod_weight, _speech_openness)
    d, n = avatar_motion_frames(portraits, 290, key=key, fps=25, cycle=6.0, move=1.6)
    files = sorted(d.glob("a*.png"))
    check("6초 주기 = 150프레임", n == 150 and len(files) == 150, f"{n}/{len(files)}")
    frames = [np.asarray(Image.open(f).convert("RGB"), dtype=np.float32) for f in files]
    bone = [f for f in files if f.stem == "a0000"]
    check("프레임 PNG 실제 생성", len(bone) == 1, str(len(bone)))

    # 말하는 구간에서 입 주변이 실제로 바뀌는지 — 눈·마이크는 그대로
    mouth_box = None
    b0, b2 = names["male"][0], names["male"][1]
    _, _, box = _diff_stats(_gray(b0), _gray(b2))
    if box:
        mouth_box = (int(box[0] * 290 / 256), int(box[2] * 290 / 256),
                     max(1, int((box[1] - box[0]) * 290 / 256)), max(1, int((box[3] - box[2]) * 290 / 256)))
    f_open = frames[0]
    f_closed = frames[int(2.15 * 25)]          # 말이 끝나고 입을 다문 순간
    diff = np.abs(f_open - f_closed).mean(axis=2)
    if mouth_box:
        x, y, w, h = mouth_box
        inside = float(diff[y:y + h, x:x + w].mean())
        outside = float((diff.sum() - diff[y:y + h, x:x + w].sum()) /
                        max(1, diff.size - w * h))
    else:
        inside = outside = 0.0
    check("말하는 동안 입 주변이 실제로 변함", inside > 2.0, f"입주변 평균차 {inside:.2f}")
    check("입 주변이 다른 곳보다 훨씬 많이 변함(눈·마이크·배경은 잔잔)", inside > outside * 1.35,
          f"바깥 평균차 {outside:.2f} vs 안 {inside:.2f}")

    # 대사 리듬: 구간 안에서는 입이 벌어지고, 쉬는 구간에서는 다물어 있다
    check("말하는 구간엔 입 벌림", max(_speech_openness(t / 100) for t in range(30, 200)) > 0.7)
    check("쉬는 구간(2.2~2.8초)엔 입 다묾",
          max(_speech_openness(2.2 + i / 50) for i in range(30)) < 0.05)
    check("6초 주기 이음매가 매끄러움", _speech_openness(5.999) < 0.02 and _nod_weight(5.999) < 0.02,
          f"{_speech_openness(5.999):.3f}/{_nod_weight(5.999):.3f}")

    # 끄덕임은 사진을 겹치지 않고 화면을 내려앉혀 만든다
    still = _avatar_pose(portraits[0], 580, 0.0, 1.6, True, 0.0)
    nodded = _avatar_pose(portraits[0], 580, 0.0, 1.6, True, 1.0)
    a = np.asarray(still, dtype=np.float32)
    b = np.asarray(nodded, dtype=np.float32)
    check("끄덕임 프레임이 실제로 달라짐", float(np.abs(a - b).mean()) > 1.0,
          f"{float(np.abs(a - b).mean()):.2f}")
    ys = np.asarray(still.split()[-1], dtype=np.float32)
    ys2 = np.asarray(nodded.split()[-1], dtype=np.float32)
    check("끄덕임 = 고개가 아래로(불투명 영역 무게중심 하강)",
          float(ys2.mean()) > float(ys.mean()), f"{float(ys.mean()):.2f} → {float(ys2.mean()):.2f}")

    # 프레임 사이 급격한 튐(깜빡임) 없음
    steps = [float(np.abs(frames[i + 1] - frames[i]).mean()) for i in range(len(frames) - 1)]
    steps.append(float(np.abs(frames[0] - frames[-1]).mean()))
    check("이웃 프레임 차이 최대 12 이하(깜빡임 없음)", max(steps) <= 12.0, f"{max(steps):.2f}")
    run = longest = 0
    for st in steps:
        run = run + 1 if st < 1e-6 else 0
        longest = max(longest, run)
    check("3프레임 넘게 완전히 멈춰 있는 구간 없음", longest <= 2, f"{longest}프레임")

    print("== 6. 단일 사진(내 사진) 하위 호환 ==")
    d1, n1 = avatar_motion_frames(portraits[0], 290, key="custom_probe", fps=25, cycle=6.0, move=1.6)
    f1 = sorted(d1.glob("a*.png"))
    check("사진 1장도 150프레임 모션", n1 == 150 and len(f1) == 150, f"{n1}/{len(f1)}")
    a0 = np.asarray(Image.open(f1[0]).convert("RGBA"), dtype=np.float32)
    a30 = np.asarray(Image.open(f1[30]).convert("RGBA"), dtype=np.float32)
    a100 = np.asarray(Image.open(f1[100]).convert("RGBA"), dtype=np.float32)
    dm = float(np.abs(a0 - a30).mean())
    ds = float(np.abs(a0 - a100).mean())
    check("기존 숨쉬기 모션 유지(움직임 구간)", dm > 1.5, f"{dm:.3f}")
    check("기존 숨쉬기 모션 유지(정지 구간 호흡)", 0.05 < ds < dm * 0.6, f"{ds:.3f}/{dm:.3f}")
    w2 = _avatar_weights(1.0, 2)
    check("사진 2장이면 입 다물↔벌림 2단", len(w2) == 2 and abs(sum(w2) - 1.0) < 1e-6, str(w2))
    w3 = _avatar_weights(1.0, 3)
    check("사진 3장이면 가중치 합 1", len(w3) == 3 and abs(sum(w3) - 1.0) < 1e-6, str(w3))

    print("== 7. 렌더 배선·화면 ==")
    render_src = (ROOT / "app" / "render.py").read_text(encoding="utf-8")
    for probe in ("host_portraits", "avatar_motion_frames(portraits", "발화 모션"):
        check(f"render.py 에 {probe}", probe in render_src)
    check("모션 실패 시 정지 아바타 폴백 유지", "· 정지" in render_src)
    graphics_src = (ROOT / "app" / "graphics.py").read_text(encoding="utf-8")
    check("LIVE 배지·링 펄스 유지", "ring_pulse" in graphics_src and "live_badge_frames" in graphics_src)
    idx = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
    check("화면 옵션 유지(진행자·LIVE)", "liveBadge" in idx and "avatarKind" in idx)
    secrets = ("sk-", "AIza", "Bearer " + "x")
    check("비밀키 없음(푸시 전 점검)",
          not any(k in (render_src + graphics_src) for k in secrets))

    print("== 8. 실제 화면 미리보기 PNG ==")
    from app.graphics import card_text, live_badge, save
    prev = card_text("세월의 사연극장", ["그날 밤, 아버지는", "아무 말도 하지 않았다"],
                     1280, 720, note="v1.2.3 진행자 미리보기").convert("RGBA")
    av = portraits[0].resize((290, 290), Image.LANCZOS)
    prev.alpha_composite(av, (1280 - 290 - 35, 720 - 290 - 35))
    badge = live_badge(1280, 0.8)
    prev.alpha_composite(badge, (1280 - 35 - 290 + (290 - badge.width) // 2,
                                 720 - 35 - 290 - int(badge.height * 0.55)))
    save(prev, WORK / "preview_169.png")
    frames[12].astype("uint8")
    Image.open(files[12]).save(WORK / "avatar_290.png")
    sheet = Image.new("RGB", (290 * 4, 290), (14, 12, 11))
    for i, fi in enumerate((0, 18, 33, 56)):
        sheet.paste(Image.open(files[fi]).convert("RGB"), (i * 290, 0))
    sheet.save(WORK / "motion_sheet.png")
    check("미리보기 PNG 저장", (WORK / "preview_169.png").exists())
    check("모션 시트 PNG 저장", (WORK / "motion_sheet.png").exists())

    print()
    print(f"통과 {len(PASS)} · 실패 {len(FAIL)}")
    for f in FAIL:
        print("  ❌", f)
    print(f"  (확인용 PNG: {WORK / 'preview_169.png'} · {WORK / 'motion_sheet.png'})")
    return 0 if not FAIL else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        traceback.print_exc()
        sys.exit(2)
