"""세월의 사연극장 v2.0.0 — 4단계 스튜디오 · 성우 분리/속도 균일 · 무중단 이미지 수신 검증.

네트워크·ffmpeg·실제 API 호출 없음. (OpenAI 응답과 git/API 는 가짜로 흥내낸다)

    python3 tools/selftest_v200.py
"""
from __future__ import annotations

import ast
import asyncio
import io
import json
import shutil
import sys
import tarfile
import threading
import traceback
import urllib.error
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent.parent
WORK = ROOT / ".cache" / "selftest_v200"

PASS: list[str] = []
FAIL: list[str] = []

FAKE_KEY = "FAKE_KEY_FOR_SELFTEST"
FAKE_MP3 = b"\xff\xfb\x90\x00" + b"\x00" * 2600
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


class FakeResp:
    def __init__(self, body: bytes):
        self.body = body

    def read(self) -> bytes:
        return self.body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class FakeRequests:
    """requests.post 대역 — 보낸 payload(voice·speed·instructions)를 모두 기록한다."""

    def __init__(self):
        self.calls: list[dict] = []

    def post(self, url, data=None, headers=None, timeout=None):
        try:
            payload = json.loads((data or b"{}").decode("utf-8"))
        except Exception:
            payload = {}
        self.calls.append({"url": url, "payload": payload, "headers": dict(headers or {})})
        return SimpleNamespace(status_code=200, content=FAKE_MP3)


def main() -> int:
    print("== 1. 버전 · 문서 · Python 3.9 ==")
    disk = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    init_src = (ROOT / "app" / "__init__.py").read_text(encoding="utf-8")
    try:
        ver_tuple = tuple(int(x) for x in disk.split(".")[:3])
    except Exception:
        ver_tuple = (0,)
    check("VERSION 이 2.0.0 이상", ver_tuple >= (2, 0, 0), disk)
    check("app.__version__ 가 VERSION 과 같다", f'"{disk}"' in init_src, init_src.strip().splitlines()[-1])
    readme = (ROOT / "README_맥북설치방법.txt").read_text(encoding="utf-8")
    check("설명서 머리말 버전 일치", f"(v{disk})" in readme.splitlines()[1], readme.splitlines()[1])
    for probe in ("4단계 스튜디오", "시나리오 추천받기", "목소리 분배", "목소리 배정",
                  "호흡", "assets_inbox", "대본 전체", "OpenAI 자동 보조"):
        if probe == "목소리 분배":
            continue
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
    from app import inbox_watch as ib  # noqa: E402
    from app import main as web  # noqa: E402
    from app import tts as T  # noqa: E402
    from app.paths import BASE, project_dir  # noqa: E402
    from app.project import GAPS, create_project, load  # noqa: E402
    from app.settings import load_config, save_config  # noqa: E402

    check("임시 사본 버전 일치", pkg_version == disk, f"{pkg_version}/{disk}")
    client = TestClient(web.app)

    print("== 3. 속도 균일화 · 해설/인물 목소리 분리 ==")
    check("기준 속도 1.00", T.NARRATION_SPEED == 1.00, str(T.NARRATION_SPEED))
    check("화자 사이 허용 편차 ±0.03", T.SPEED_TOLERANCE == 0.03, str(T.SPEED_TOLERANCE))
    check("uniform_speed 경계(±15%)", (T.uniform_speed(0), T.uniform_speed(100), T.uniform_speed(-100))
          == (1.0, 1.15, 0.85), str((T.uniform_speed(0), T.uniform_speed(100), T.uniform_speed(-100))))
    check("uniform_rate ±15%", (T.uniform_rate(0), T.uniform_rate(40), T.uniform_rate(-40)) == (0, 15, -15),
          str((T.uniform_rate(0), T.uniform_rate(40), T.uniform_rate(-40))))
    rule = T.with_speed_rule("연기 지시")
    check("지시문에 극단 속도 금지", "극단적으로 빠르거나 느리" in rule, rule[:80])
    check("지시문에 '해설과 같은 속도'", "해설자와 똑같은" in rule, rule[:120])
    check("속도 규칙 중복 없음", T.with_speed_rule(rule) == rule, "중복됨")

    narr = T.openai_narrator_voice("multi")
    casts = {
        "old_male": T.openai_cast("old_male", "multi", "70대", "male", "노인", "heal")[0],
        "old_female": T.openai_cast("old_female", "multi", "78세", "female", "노모", "heal")[0],
        "daughter_in_law": T.openai_cast("female", "multi", "30대 후반", "female", "며느리", "conflict")[0],
        "son": T.openai_cast("young_male", "multi", "40대 후반", "male", "아들", "conflict")[0],
        "child": T.openai_cast("child", "multi", "8세", "male", "아이", "heal")[0],
    }
    check("해설은 onyx", narr == "onyx", narr)
    check("대화 인물은 해설 목소리를 쓰지 않는다",
          all(v != narr for v in casts.values()), str(casts))
    check("인물끼리도 서로 다른 목소리", len(set(casts.values())) == len(casts), str(casts))
    check("노년 어머니는 낮은 여성음(sage)", casts["old_female"] == "sage", casts["old_female"])
    check("노년 아버지는 ash", casts["old_male"] == "ash", casts["old_male"])
    check("며느리는 젊은 여성음(shimmer)", casts["daughter_in_law"] == "shimmer",
          casts["daughter_in_law"])
    check("아들은 onyx 가 아닌 남성음", casts["son"] not in ("onyx", narr), casts["son"])

    f_narr = T.openai_narrator_voice("female")
    f_dil = T.openai_cast("female", "female", "30대", "female", "며느리", "conflict")[0]
    check("여성 낭독 해설은 coral", f_narr == "coral", f_narr)
    check("여성 해설 + 여성 인물도 다른 목소리", f_dil != f_narr, f"{f_dil} / {f_narr}")

    e_narr = T.edge_narrator_voice("multi")
    e_old = T.edge_cast("old_female", "multi", 0, "70대 후반", "female", "노모")
    e_son = T.edge_cast("young_male", "multi", 0, "40대", "male", "아들")
    check("edge 해설은 InJoon", e_narr == "ko-KR-InJoonNeural", e_narr)
    check("edge 노년 어머니는 SunHi 저음", e_old[0] == "ko-KR-SunHiNeural" and int(e_old[1][:-2]) <= -10,
          str(e_old))
    check("edge 남성 인물은 해설과 다른 음성", e_son[0] != e_narr, str(e_son))
    check("edge 속도 균일(±3%)", all(abs(x[2]) <= 3 for x in (e_old, e_son)), str((e_old, e_son)))

    print("== 4. 화자 사이 호흡 간격 ==")
    check("호흡 간격 0.28~0.35초", 0.28 <= T.breath_gap() <= 0.35, str(T.breath_gap()))
    check("본문 대사 간격이 호흡 간격", abs(GAPS["body"] - T.BREATH_GAP_SECONDS) < 0.0001,
          str(GAPS["body"]))
    check("본문 간격이 허용 범위", 0.28 <= GAPS["body"] <= 0.35, str(GAPS["body"]))
    raw, how = T.join_with_breath([b"a" * 10, b"b" * 10])
    check("ffmpeg 없으면 원본 그대로(무중단)", how == "raw" and raw == b"a" * 10 + b"b" * 10, how)
    one, how1 = T.join_with_breath([b"only"])
    check("한 덩어리는 그대로", one == b"only" and how1 == "raw", str(how1))

    # ffmpeg 대역 — 무음 트림 → 0.32초 무음 삽입 → concat 명령이 실제로 만들어지는지
    real_ffmpeg, real_silence, real_trim, real_run = (T._ffmpeg, T._silence_wav, T._trim_wav,
                                                      T.subprocess.run)
    commands: list[list[str]] = []
    trims: list[str] = []
    sil = WORK / "silence032.wav"
    sil.parent.mkdir(parents=True, exist_ok=True)

    def fake_silence(gap):
        sil.write_bytes(b"\x00" * 400)
        return sil

    def fake_trim(src: Path, dst: Path) -> bool:
        trims.append(src.name)
        dst.write_bytes(b"\x00" * 500)
        return True

    def fake_run(args, **kw):
        commands.append([str(a) for a in args])
        out = Path(str(args[-1]))
        try:
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(b"MP3" * 400 if "concat" in args else b"\x00" * 400)
        except Exception:
            pass
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    T._ffmpeg = lambda: "ffmpeg"
    T._silence_wav = fake_silence
    T._trim_wav = fake_trim
    T.subprocess.run = fake_run
    wd = WORK / "join_work"
    try:
        joined, how2 = T.join_with_breath([b"x" * 900, b"y" * 900, b"z" * 900], 0.32, wd)
        check("ffmpeg 경로로 이어붙임", how2 == "ffmpeg" and joined.startswith(b"MP3"), how2)
        listing = (wd / "list.txt").read_text(encoding="utf-8")
        check("무음이 문장 사이에 2번 들어간다", listing.count("silence") == 2, listing.replace("\n", " | "))
        check("마지막 문장 뒤에는 무음 없음", listing.strip().splitlines()[-1].startswith("file 'c02"),
              listing.strip().splitlines()[-1])
        concat_cmd = next((c for c in commands if "concat" in c), [])
        check("concat 명령 사용", "-f" in concat_cmd and "concat" in concat_cmd, str(concat_cmd)[:160])
        check("문장마다 무음 트림 시도", len(trims) == 3, str(trims))

        # 실제 _trim_wav 가 만드는 필터(앞·뒤 무음 제거)를 확인한다
        commands.clear()
        ok_trim = real_trim(Path(wd / "c00.mp3"), Path(wd / "probe.wav"))
        cmd = commands[-1] if commands else []
        filt = cmd[cmd.index("-af") + 1] if "-af" in cmd else ""
        check("silenceremove 로 앞뒤 무음 제거", ok_trim and filt.count("silenceremove") == 2
              and "areverse" in filt, filt[:120])
    finally:
        T._ffmpeg, T._silence_wav, T._trim_wav, T.subprocess.run = (real_ffmpeg, real_silence,
                                                                    real_trim, real_run)

    print("== 4-1. 전체 톤(따뜻/담담/처절/통쾌) ==")
    from app.gemini_script import _short_design_prompt
    from app.settings import STORY_TONES
    check("톤 4종", set(STORY_TONES) == {"warm", "calm", "tense", "sassy"}, str(STORY_TONES))
    tone_prompt = _short_design_prompt({"genre": "inlaw", "target_seconds": 50,
                                        "preset": "shorts50", "tone": "sassy"})
    check("톤이 대본 지시문에 반영", "통쾌한 사이다" in tone_prompt, tone_prompt[:200])
    check("톤이 없으면 따뜻한 기본", "따뜻하고 정 많은" in _short_design_prompt(
        {"genre": "inlaw", "target_seconds": 50, "preset": "shorts50"}), "")

    print("== 5. 대본에서 목소리 표(project_voice_plan) ==")
    save_config({"gemini_api_key": "", "openai_api_key": "", "tts_engine": "edge",
                 "script_engine": "auto"})
    proj = create_project({"preset": "shorts50", "genre": "inlaw", "topic": "며느리의 반격",
                           "image_mode": "B"})
    pid = proj["id"]
    tone_proj = create_project({"preset": "shorts50", "genre": "reversal", "topic": "톤 테스트",
                                "tone": "sassy", "image_mode": "B"})
    check("프로젝트에 톤 저장", (tone_proj.get("options") or {}).get("tone") == "sassy",
          str((tone_proj.get("options") or {}).get("tone")))
    bad_tone = create_project({"preset": "shorts50", "genre": "reversal", "topic": "톤 기본",
                               "tone": "??", "image_mode": "B"})
    check("잘못된 톤은 따뜻한 기본", (bad_tone.get("options") or {}).get("tone") == "warm",
          str((bad_tone.get("options") or {}).get("tone")))
    plan_edge = T.project_voice_plan(load(pid))
    check("장면마다 화자 배정", len(plan_edge["speakers"]) >= 2, str(list(plan_edge["speakers"])))
    check("해설과 인물 목소리 분리(edge)", not T.separation_violations(plan_edge),
          str(T.separation_violations(plan_edge)))
    check("모든 화자 속도 동일", max(T.speed_values(plan_edge)) - min(T.speed_values(plan_edge)) <= 0.0001,
          str(T.speed_values(plan_edge)))
    check("표에 호흡 간격 기록", 0.28 <= plan_edge["breath_gap"] <= 0.35, str(plan_edge["breath_gap"]))
    plan_ai = T.project_voice_plan(load(pid), engine="openai", mode="multi")
    narr2 = plan_ai["narrator"]["voice"]
    dialog = [s for k, s in plan_ai["speakers"].items() if s["role"] != "narrator"]
    check("해설과 대화 인물 voice 불일치(openai)", all(s["voice"] != narr2 for s in dialog),
          str([(s["label"], s["voice"]) for s in dialog]))
    check("대화 인물끼리도 서로 다른 voice", len({s["voice"] for s in dialog}) == len(dialog),
          str([(s["label"], s["voice"]) for s in dialog]))
    check("openai 표 속도 1.00", all(abs(float(s["speed"]) - 1.0) <= 0.0001 for s in dialog),
          str([s["speed"] for s in dialog]))
    check("연기 지시에 속도 규칙", all("속도는 극단적으로" in s.get("instructions", "")
                                       for s in dialog), "지시문 누락")
    edge_narr = plan_ai["narrator"].get("edge_voice")
    check("OpenAI 실패 시 edge 폴백도 해설과 분리",
          edge_narr == "ko-KR-InJoonNeural" and all(s.get("edge_voice") != edge_narr for s in dialog),
          str([(s["label"], s.get("edge_voice")) for s in dialog]))

    print("== 6. 성우 합성 — 같은 속도 · 분리된 목소리 · 파일 생성 ==")
    save_config({"tts_engine": "openai", "openai_api_key": FAKE_KEY,
                 "openai_tts_model": "gpt-4o-mini-tts", "openai_fallback_edge": True})
    real_requests = T.requests
    fake = FakeRequests()
    T.requests = fake
    try:
        p2 = load(pid)
        durations = asyncio.run(T.synthesize_lines(p2))
        payloads = [c["payload"] for c in fake.calls]
        speeds = {round(float(p["speed"]), 2) for p in payloads}
        check("장면 수만큼 음성 파일", all((project_dir(pid) / "audio_clips" / f"{s['id']}.mp3").exists()
                                    for s in p2["scenes"]), "파일 누락")
        check("모든 호출 speed 동일(1.00)", speeds == {1.0}, str(speeds))
        check("모든 호출에 속도 지시", all("극단적으로" in p.get("instructions", "") for p in payloads),
              "지시 누락")
        voices = {p["voice"] for p in payloads}
        narrs = {p["voice"] for p in payloads if "해설자입니다" in p.get("instructions", "")}
        check("해설 payload 는 onyx", narrs == {"onyx"}, str(narrs))
        check("대화 payload 는 onyx 미사용", "onyx" not in (voices - narrs), str(voices))
        meta = json.loads((project_dir(pid) / "voice_plan.json").read_text(encoding="utf-8"))
        check("voice_plan.json 기록", meta.get("speed") == 1.0 and meta.get("speakers"),
              str(sorted(meta))[:120])
        check("장면 길이 계산", len(durations) == len(p2["scenes"]) and all(v >= 0 for v in durations.values()),
              str(durations)[:120])
        n_calls = len(fake.calls)
        asyncio.run(T.synthesize_lines(load(pid), only_missing=True))
        check("이미 만든 음성은 다시 호출하지 않음", len(fake.calls) == n_calls,
              f"{n_calls} → {len(fake.calls)}")
    finally:
        T.requests = real_requests

    print("== 7. 무중단 이미지 수신 (scoped checkout · GitHub API) ==")
    real_is_git, real_pull, real_run2 = ib.is_git_repo, ib.git_pull, ib.subprocess.run
    real_scoped, real_api = ib.scoped_inbox_sync, ib.api_fetch_inbox
    calls: list[list[str]] = []

    def fake_git(args, **kw):
        calls.append([str(a) for a in args])
        return SimpleNamespace(returncode=0, stdout="ok", stderr="")

    try:
        ib.is_git_repo = lambda: True
        ib.subprocess.run = fake_git
        res = ib.scoped_inbox_sync()
        checkout = next((c for c in calls if "checkout" in c), [])
        check("pull 실패 시 fetch+checkout 으로 받는다", res.get("reason") == "scoped_checkout",
              str(res)[:200])
        check("checkout 은 origin/main -- assets_inbox 만", checkout[-3:] == ["origin/main", "--", "assets_inbox"],
              str(checkout))
        joined = " ".join(" ".join(c) for c in calls)
        check("projects/ · config/ 는 건드리지 않는다",
              " projects" not in joined and " config" not in joined, joined[:200])

        # pull 실패 → scoped 성공 → 새 이미지가 프로젝트로 들어온다
        ib.git_pull = lambda timeout=120: {"ok": False, "reason": "pull_failed",
                                           "message": "error: Your local changes would be overwritten"}
        folder = ib.INBOX / pid
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "s01.png").write_bytes(_png(7))
        r1 = ib.receive_once("selftest")
        check("pull 실패해도 수신 성공(경로 scoped_checkout)", r1.get("ok") and r1.get("route") == "scoped_checkout",
              str(r1)[:240])
        check("이미지가 프로젝트 images 로 복사", (project_dir(pid) / "images" / "s01.png").exists(),
              "복사 안 됨")
        check("수신 기록에 route 남김", any(e.get("route") == "scoped_checkout" for e in r1.get("received", [])),
              str(r1.get("received"))[:160])

        # pull·scoped 실패 → GitHub API 성공
        (project_dir(pid) / "images" / "s01.png").unlink()
        (folder / "s01.png").unlink()
        ib.scoped_inbox_sync = lambda timeout=120: {"ok": False, "reason": "checkout_failed",
                                                    "message": "assets_inbox 충돌"}

        def fake_api(projects=None, timeout=40):
            d = ib.INBOX / pid
            d.mkdir(parents=True, exist_ok=True)
            (d / "s01.png").write_bytes(_png(8))
            return {"ok": True, "reason": "api", "message": "GitHub API 로 이미지 1장을 받았습니다.",
                    "files": [f"{pid}/s01.png"], "errors": []}

        ib.api_fetch_inbox = fake_api
        r2 = ib.receive_once("selftest")
        check("git 도 막혀도 API 로 수신", r2.get("ok") and r2.get("route") == "api", str(r2)[:240])
        check("API 로 받은 이미지도 프로젝트로", (project_dir(pid) / "images" / "s01.png").exists(), "")

        # 모두 실패 → 원인이 상태에 남는다
        (project_dir(pid) / "images" / "s01.png").unlink()
        (folder / "s01.png").unlink()
        ib.api_fetch_inbox = lambda projects=None, timeout=40: {"ok": False, "reason": "api_error",
                                                                "message": "GitHub API 연결 실패"}
        r3 = ib.receive_once("selftest")
        st = ib.status()
        check("모두 실패하면 ok=false·경로 failed", r3.get("ok") is False and r3.get("route") == "failed",
              str(r3)[:240])
        check("last_error 에 원인 기록", bool(st.get("last_error")) and "pull_failed" not in str(st.get("last_error")),
              str(st.get("last_error"))[:200])
        prog = ib.project_progress(pid)
        check("2단계 타임라인용 진행 정보", prog.get("ok") and "remaining" in prog and "total" in prog,
              str(prog)[:200])
        check("진행 정보에 오류도 함께", bool(prog.get("last_error")), str(prog.get("last_error"))[:120])
    finally:
        ib.is_git_repo, ib.git_pull, ib.subprocess.run = real_is_git, real_pull, real_run2
        ib.scoped_inbox_sync, ib.api_fetch_inbox = real_scoped, real_api

    print("== 8. GitHub API 폴더 내려받기 ==")
    real_json, real_dl = ib._api_json, ib._api_download
    try:
        ib._api_json = lambda url, timeout=40: [
            {"name": "s01.png", "type": "file", "download_url": "https://example.invalid/s01.png"},
            {"name": "s02.jpg", "type": "file", "download_url": "https://example.invalid/s02.jpg"},
            {"name": "메모.txt", "type": "file", "download_url": "https://example.invalid/memo.txt"},
        ]
        ib._api_download = lambda url, timeout=60: _png(3)
        api_dir = ib.INBOX / "api-proj"
        shutil.rmtree(api_dir, ignore_errors=True)
        res = ib.api_fetch_inbox(["api-proj"])
        names = sorted(p.name for p in api_dir.glob("*")) if api_dir.exists() else []
        check("API 목록에서 이미지 확장자만 저장", names == ["s01.png", "s02.jpg"], str(names))
        check("API 수신 결과에 파일 목록", res.get("ok") and len(res.get("files") or []) == 2, str(res)[:200])
    finally:
        ib._api_json, ib._api_download = real_json, real_dl

    print("== 9. 4단계 API ==")
    meta = client.get("/api/meta").json()
    steps = meta.get("studio_steps") or []
    check("/api/meta 4단계 정보", [s.get("n") for s in steps] == [1, 2, 3, 4], str(steps)[:160])
    check("/api/meta 음성 기준", meta.get("voice_standard", {}).get("speed") == 1.0,
          str(meta.get("voice_standard")))

    sug = client.post("/api/scenario/suggest", json={"genre": "inlaw", "preset": "shorts50", "count": 5})
    sdata = sug.json()
    check("POST /api/scenario/suggest 200", sug.status_code == 200, sug.text[:200])
    check("주제·훅 3~5개 추천", 3 <= len(sdata.get("ideas") or []) <= 5 and
          all(i.get("topic") and i.get("hook") for i in sdata["ideas"]), str(sdata)[:240])

    stu = client.get(f"/api/projects/{pid}/studio").json()
    check("GET /studio (요약·카피·목소리·수신)", stu.get("ok") and "project" in stu and "voices" in stu
          and "pack" in stu and "receive" in stu, str(sorted(stu))[:200])
    check("studio 에 4단계 업로드 결정 상태", "publish" in stu["project"], str(sorted(stu["project"]))[:160])

    voices = client.get(f"/api/projects/{pid}/voices").json()
    check("GET /voices 분리 검사 통과", voices.get("separated") is True and not voices.get("violations"),
          str(voices.get("violations")))
    check("GET /voices 속도 균일", voices.get("speed_uniform") is True, str(voices.get("speeds")))
    check("GET /voices 호흡 간격", 0.28 <= voices.get("breath_gap", 0) <= 0.35, str(voices.get("breath_gap")))

    # 모드 A 이미지 자동 생성 — 키가 없으면 안내, 있으면 작업
    no_key = client.post(f"/api/projects/{pid}/images/generate")
    check("키 없으면 자동 이미지 생성 400 안내", no_key.status_code == 400 and
          "Gemini" in no_key.text, f"{no_key.status_code} {no_key.text[:160]}")
    real_gen = web.generate_images
    web.generate_images = lambda p, progress=None: (progress(50, "이미지 생성") if progress else None) or \
        {"generated": 1, "failed": 0}
    save_config({"gemini_api_key": "FAKE_GEMINI_FOR_SELFTEST"})
    try:
        if (project_dir(pid) / "images" / "s01.png").exists():
            (project_dir(pid) / "images" / "s01.png").unlink()
        r = client.post(f"/api/projects/{pid}/images/generate")
        job = r.json().get("job") if r.status_code == 200 else None
        jr = {}
        for _ in range(80):
            if not job:
                break
            jr = client.get(f"/api/jobs/{job}").json()
            if jr.get("status") in ("done", "error"):
                break
            threading.Event().wait(0.1)
        check("모드 A 이미지 자동 생성 작업", r.status_code == 200 and jr.get("status") == "done",
              str(jr)[:200])
        check("생성 결과 보고", (jr.get("result") or {}).get("generated") == 1, str(jr.get("result"))[:160])
    finally:
        web.generate_images = real_gen
        save_config({"gemini_api_key": ""})

    # 성우 음성 만들기 (합성은 대역)
    real_synth = web.synthesize_sync
    web.synthesize_sync = lambda p, progress=None, only_missing=False: (
        progress(1, 1) if progress else None) or {s["id"]: 2.5 for s in p["scenes"]}
    try:
        r = client.post(f"/api/projects/{pid}/tts")
        job = r.json().get("job") if r.status_code == 200 else None
        jr = {}
        for _ in range(80):
            if not job:
                break
            jr = client.get(f"/api/jobs/{job}").json()
            if jr.get("status") in ("done", "error"):
                break
            threading.Event().wait(0.1)
        check("POST /tts 작업 완료", r.status_code == 200 and jr.get("status") == "done", str(jr)[:240])
        check("성우 결과에 목소리 표", bool((jr.get("result") or {}).get("plan", {}).get("speakers")),
              str(jr.get("result"))[:160])
    finally:
        web.synthesize_sync = real_synth

    # 대사별 미리듣기·재녹음
    real_prev = web.synthesize_line_preview

    def fake_prev(project, scene, text=None, name=None):
        d = web.preview_dir(project["id"])
        f = d / f"{name or scene.get('id')}.mp3"
        f.write_bytes(FAKE_MP3)
        return {"ok": True, "file": f.name, "seconds": 1.8, "engine": "openai",
                "voice": "onyx", "pitch": "", "speed": 1.0, "rate": 0,
                "speaker": scene.get("speaker"), "label": "해설", "text": text or ""}

    web.synthesize_line_preview = fake_prev
    try:
        target = load(pid)["scenes"][0]
        pr = client.post(f"/api/projects/{pid}/tts/preview",
                         json={"scene_id": target["id"], "text": target["text"], "save": True})
        pdata = pr.json()
        check("POST /tts/preview 200", pr.status_code == 200, pr.text[:200])
        check("미리듣기 주소·길이·목소리 반환", bool(pdata.get("url")) and pdata.get("seconds") and
              pdata.get("voice"), str(pdata)[:220])
        audio = client.get(f"/api/projects/{pid}/tts/{target['id']}")
        check("GET /tts/{장면} audio/mpeg", audio.status_code == 200 and
              audio.headers.get("content-type", "").startswith("audio/mpeg") and len(audio.content) > 500,
              f"{audio.status_code} {audio.headers.get('content-type')}")
        check("없는 음성은 404", client.get(f"/api/projects/{pid}/tts/s99").status_code == 404, "")
        check("잘못된 이름은 400", client.get(f"/api/projects/{pid}/tts/..%2Fproject.json").status_code in (400, 404), "")
    finally:
        web.synthesize_line_preview = real_prev

    # 렌더링 — 단계별 진행률
    p = load(pid)
    for i, img in enumerate(p["image_plan"], start=1):
        (project_dir(pid) / "images" / img["file"]).write_bytes(_png(i))
    real_mix, real_video, real_thumb = web.build_mix, web.render_video, web.render_thumbnails
    real_synth2 = web.synthesize_sync
    stage_seen: list[dict] = []

    def fake_mix(p, items, progress=None):
        if progress:
            progress(100, "믹싱 완료")
        out = project_dir(p["id"]) / "output" / "mix.wav"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(b"RIFF")
        return out

    def fake_video(p, items, mix, progress=None):
        if progress:
            progress(50, "장면 렌더")
            progress(100, "인코딩 완료")
        out = project_dir(p["id"]) / "output" / "final.mp4"
        out.write_bytes(b"\x00" * 64)
        return out

    def fake_thumb(p, progress=None):
        d = project_dir(p["id"]) / "output" / "thumb"
        d.mkdir(parents=True, exist_ok=True)
        a, b = d / "t1.png", d / "t2.png"
        a.write_bytes(_png(1)); b.write_bytes(_png(2))
        return {"style1": str(a), "style2": str(b)}

    web.build_mix, web.render_video, web.render_thumbnails = fake_mix, fake_video, fake_thumb
    web.synthesize_sync = lambda p, progress=None, only_missing=False: (
        progress(1, 1) if progress else None) or {s["id"]: 2.0 for s in p["scenes"]}
    try:
        r = client.post(f"/api/projects/{pid}/render", json={"remix": True})
        job = r.json().get("job") if r.status_code == 200 else None
        jr = {}
        for _ in range(120):
            if not job:
                break
            jr = client.get(f"/api/jobs/{job}").json()
            if jr.get("stages"):
                stage_seen.append(dict(jr["stages"]))
            if jr.get("status") in ("done", "error"):
                break
            threading.Event().wait(0.1)
        check("POST /render 완료", r.status_code == 200 and jr.get("status") == "done", str(jr)[:300])
        check("단계별 진행률(4단계) 노출", bool(stage_seen) and set(stage_seen[-1]) == {"성우", "BGM", "자막", "인코딩"},
              str(stage_seen[-1] if stage_seen else None))
        check("모든 단계 100%", stage_seen and all(v == 100 for v in stage_seen[-1].values()),
              str(stage_seen[-1] if stage_seen else None))
        after = client.get(f"/api/projects/{pid}").json()
        check("final.mp4 산출물 기록", bool((after.get("outputs") or {}).get("video")), str(after.get("outputs")))
        check("자막 파일 생성", (project_dir(pid) / "output" / "subtitles.srt").exists(), "")
        check("썸네일 2종 생성", bool(after["outputs"].get("thumb_style1")) and
              bool(after["outputs"].get("thumb_style2")), str(after["outputs"])[:160])
    finally:
        web.build_mix, web.render_video, web.render_thumbnails = real_mix, real_video, real_thumb
        web.synthesize_sync = real_synth2

    # 업로드 결정
    hold = client.post(f"/api/projects/{pid}/publish", json={"decision": "hold"}).json()
    check("POST /publish 보류는 파일만", hold.get("ok") and hold.get("decision") == "hold" and
          bool(hold.get("files")), str(hold)[:200])
    proj_now = client.get(f"/api/projects/{pid}").json()
    check("보류 결정 기록", (proj_now.get("publish") or {}).get("decision") == "hold",
          str(proj_now.get("publish")))
    now_res = client.post(f"/api/projects/{pid}/publish",
                          json={"decision": "now", "privacy": "public"}).json()
    check("유튜브 미연결이면 업로드하지 않고 안내", now_res.get("ok") is False and
          "유튜브" in str(now_res.get("error")), str(now_res)[:200])
    check("연결 전에는 업로드 job 을 만들지 않는다", not now_res.get("job"), str(now_res)[:160])

    print("== 10. 화면 연결 (4단계 위자드) ==")
    home = client.get("/").text
    for probe in ("class=\"stepbar\"", "data-step=\"1\"", "data-step=\"2\"", "data-step=\"3\"",
                  "data-step=\"4\"", "panel1", "panel2", "panel3", "panel4", "btnNext2", "btnNext3",
                  "btnNext4", "settingsDrawer", "btnSettings", "btnIdeas", "btnTtsRun", "lineList",
                  "btnRender", "stageBars", "publishDecision", "즉시 업로드", "예약 업로드",
                  "보류하고 파일만 저장", "imgReviseNote", "inboxStatus", "runImages", "voicePlanBox",
                  "대본 전체 읽기", "시나리오 추천받기", "성우 음성 만들기", "영상 렌더링 시작",
                  "storyTone", "전체 톤", "btnGenImages", "이미지 자동 생성",
                  "scriptEngine", "Gemini (무료) / OpenAI 자동 보조", "ttsCard", "ttsEngine",
                  "openaiKey", "btnTtsSave", "btnTtsTest", "ttsFallback", "liveBadge", "290px",
                  "LIVE 표시", "platform.openai.com/api-keys", "OpenAI 감성 TTS", "무료 edge-tts"):
        check(f"index.html 에 {probe}", probe in home, "")
    import re as _re
    panels = _re.findall(r'<section class="panel"[^>]*>', home)
    hidden_panels = [x for x in panels if "hidden" in x]
    check("패널 4개", len(panels) == 4, str(panels)[:200])
    check("2~4단계는 처음에 숨김(한 화면에 한 단계)",
          len(hidden_panels) == 3 and 'id="panel1"' not in " ".join(hidden_panels),
          str(hidden_panels)[:200])

    js = client.get("/static/app.js").text
    for probe in ("function setStep", "renderStep2", "renderStep3", "renderStep4", "runTts",
                  "recordLine", "/tts/preview", "/tts/", "/render", "/publish", "/scenario/suggest",
                  "/studio", "updateStageBars", "publishNow", "suggestIdeas", "renderIdeas",
                  "GALLERY_SIG", "loadGallery", "renderGallery", "imgLightbox", "pickCut",
                  "kevin-timeline", "image_revision", "location.reload", "restarting",
                  "loadKevinTimeline", "btnScriptRead", "btnScriptEdit", "btnScriptSave",
                  "btnScriptRebuild", "/script/rebuild", "saveScript", "rebuildScript",
                  "collectScriptScenes", "openScriptRead", "openScriptEditor", "SCRIPT_DIRTY",
                  "AI 대본 (OpenAI)", "AI 대본 (Gemini)", "applyScriptConfig", "saveScriptEngine",
                  "applyTtsConfig", "saveTts", "testTts", "tts_engine", "openai_tts_model",
                  "openai_fallback_edge", "live_badge: $(\"#liveBadge\").checked"):
        check(f"app.js 에 {probe}", probe in js, "")
    check("설정은 드로어로 분리", "settingsDrawer" in js and "openSettings" in js, "")

    css = client.get("/static/style.css").text
    for probe in (".stepbar", ".panel[hidden]", ".timeline", ".stagebars", ".drawer", ".lline",
                  ".vptable", ".idea-list", ".runbar", ".img-grid.gallery", ".lightbox", ".logbox",
                  ".revise-result", ".sedit", ".sedit textarea", ".chapter-head", ".sline", ".scriptbox"):
        check(f"style.css 에 {probe}", probe in css, "")

    print("== 11. 화면 스모크 테스트 (quickjs) ==")
    try:
        import importlib.util
        has_q = importlib.util.find_spec("quickjs") is not None
    except Exception:
        has_q = False
    if has_q:
        import subprocess
        smoke = ROOT / "tools" / "smoke_ui_v200.py"
        r = subprocess.run([sys.executable, str(smoke)], capture_output=True, text=True, timeout=120)
        check("app.js 스모크(bind·4단계 렌더) 통과", r.returncode == 0,
              (r.stdout or "")[-300:] + (r.stderr or "")[-200:])
    else:
        print("  (quickjs 없음 — 화면 스모크는 건너뜁니다. pip install quickjs)")

    print("== 12. 비밀키 없음(푸시 전 점검) ==")
    blob = js + home + (ROOT / "app" / "main.py").read_text(encoding="utf-8") + \
        (ROOT / "app" / "tts.py").read_text(encoding="utf-8")
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
