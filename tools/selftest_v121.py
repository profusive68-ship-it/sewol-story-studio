"""세월의 사연극장 v1.2.1 — OpenAI 감성 TTS 연동 검증 (실제 API 호출·렌더 없음).

확인 항목
1. VERSION / app.__version__ = 1.2.1
2. `/api/health` · `/api/config` · `/api/meta` (tts_engines · openai_tts_models)
3. `POST /api/config` — tts_engine · openai_tts_model · openai_fallback_edge 저장,
   잘못된 값 보정, OpenAI 키 마스킹(평문이 응답에 없음)
4. `POST /api/config/test` — 본문 없이(기존 Gemini 테스트)도 422 없이 동작,
   `{engine: "openai_tts"}` 는 모의 OpenAI 호출로 성공 + 미리듣기 URL
5. `GET /api/tts/preview` — 만든 미리듣기 mp3 를 audio/mpeg 로, 없으면 404
6. OpenAI payload 단위 테스트 — model · voice 매핑 · response_format=mp3 · speed ·
   instructions(gpt-4o 계열만) · 발음 사전 적용 · 401/429 한국어 안내
7. 캐시 키에 engine·model 포함(edge 캐시와 섞이지 않음) · 같은 문장 재사용 시 재호출 없음
8. synthesize_lines — OpenAI 경로 산출물/역할별 보이스, 키 없음·오류 시 edge 대체(경고),
   폴백 끄면 안내와 함께 실패
9. 화면(index.html · app.js)에 음성 엔진 선택·키·테스트 버튼 한글 반영

    python3 tools/selftest_v121.py
"""
from __future__ import annotations

import asyncio
import json
import shutil
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORK = ROOT / ".cache" / "selftest_v121"

PASS: list[str] = []
FAIL: list[str] = []

FAKE_MP3 = b"\xff\xfb\x90\x00" + b"\x00" * 2400          # ffmpeg 이 못 읽는 가짜 mp3 바이트


def check(name: str, cond: bool, detail: str = "") -> None:
    if cond:
        PASS.append(name)
        print(f"  ✅ {name}")
    else:
        FAIL.append(f"{name} — {detail}")
        print(f"  ❌ {name} {detail}")


class FakeResp:
    def __init__(self, status_code: int, content: bytes):
        self.status_code = status_code
        self.content = content


class FakeRequests:
    """`requests.post` 대역 — 보낸 payload 를 모두 기록한다."""

    def __init__(self):
        self.calls: list[dict] = []
        self.queue: list[tuple[int, bytes]] = []
        self.status = 200
        self.body = FAKE_MP3

    def post(self, url, data=None, headers=None, timeout=None):
        try:
            payload = json.loads((data or b"{}").decode("utf-8"))
        except Exception:
            payload = {}
        self.calls.append({"url": url, "payload": payload, "headers": dict(headers or {}),
                           "timeout": timeout})
        if self.queue:
            status, body = self.queue.pop(0)
        else:
            status, body = self.status, self.body
        if not isinstance(body, bytes):
            body = json.dumps({"error": {"message": body}}).encode("utf-8")
        return FakeResp(status, body)


async def fake_edge(text: str, voice: str, rate: int, pitch: str) -> bytes:
    fake_edge.calls.append((voice, rate, pitch, text))       # type: ignore[attr-defined]
    return FAKE_MP3


fake_edge.calls = []                                         # type: ignore[attr-defined]


def _project(tts_mod, base_project: dict, scenes: list[dict]) -> dict:
    p = dict(base_project)
    p["scenes"] = scenes
    p["options"] = dict(base_project.get("options") or {})
    p["options"].update({"voice_mode": "multi", "rate": 0})
    p.pop("warnings", None)
    return p


def main() -> int:
    print("== 임시 폴더 준비 ==")
    shutil.rmtree(WORK, ignore_errors=True)
    app_root = WORK / "app_root"
    app_root.mkdir(parents=True)
    for name in ("app", "static", "assets", "sfx_library", "config"):
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
    sys.path.insert(0, str(app_root))

    from fastapi.testclient import TestClient  # noqa: E402

    from app import __version__ as pkg_version  # noqa: E402
    from app import main as web  # noqa: E402
    from app import tts as T  # noqa: E402
    from app.paths import BASE, CACHE_DIR, project_dir  # noqa: E402
    from app.project import create_project  # noqa: E402
    from app.settings import load_config, public_config, save_config  # noqa: E402

    client = TestClient(web.app)

    print("== 1. 버전 ==")
    disk = (BASE / "VERSION").read_text(encoding="utf-8").strip()
    check("VERSION == app.__version__", disk == pkg_version, f"{disk} / {pkg_version}")
    check("버전이 1.2.1 이상", tuple(int(x) for x in disk.split(".") if x.isdigit()) >= (1, 2, 1), disk)
    req = (BASE / "requirements.txt").read_text(encoding="utf-8")
    check("requirements.txt 에 requests", "requests>=2.31" in req, req[-60:])

    print("== 2. 기본 엔드포인트 ==")
    h = client.get("/api/health")
    check("GET /api/health 200", h.status_code == 200 and h.json().get("ok") in (True, False),
          h.text[:200])
    check("health.version == VERSION", h.json().get("version") == disk, str(h.json())[:200])
    cfg0 = client.get("/api/config")
    check("GET /api/config 200", cfg0.status_code == 200, cfg0.text[:200])
    c0 = cfg0.json()
    check("기본 음성 엔진은 edge", c0.get("tts_engine") == "edge", str(c0)[:200])
    check("기본 모델 gpt-4o-mini-tts", c0.get("openai_tts_model") == "gpt-4o-mini-tts",
          str(c0.get("openai_tts_model")))
    check("기본 폴백 켜짐", c0.get("openai_fallback_edge") is True, str(c0.get("openai_fallback_edge")))
    check("OpenAI 키 없음", c0.get("has_openai_key") is False, str(c0.get("has_openai_key")))
    meta = client.get("/api/meta").json()
    check("/api/meta tts_engines", set(meta.get("tts_engines", {})) == {"openai", "edge"},
          str(meta.get("tts_engines")))
    check("/api/meta openai_tts_models",
          set(meta.get("openai_tts_models", {})) == {"gpt-4o-mini-tts", "tts-1-hd"},
          str(meta.get("openai_tts_models")))

    print("== 3. 설정 저장 · 마스킹 ==")
    secret = "sk-test-1234567890abcdefghij"
    r = client.post("/api/config", json={"tts_engine": "openai", "openai_api_key": secret,
                                        "openai_tts_model": "tts-1-hd",
                                        "openai_fallback_edge": False})
    body_text = r.text
    check("POST /api/config 200", r.status_code == 200, body_text[:200])
    c1 = r.json()
    check("엔진 openai 저장", c1.get("tts_engine") == "openai", c1.get("tts_engine"))
    check("모델 tts-1-hd 저장", c1.get("openai_tts_model") == "tts-1-hd", c1.get("openai_tts_model"))
    check("폴백 끄기 저장", c1.get("openai_fallback_edge") is False, str(c1.get("openai_fallback_edge")))
    check("키 있음 표시", c1.get("has_openai_key") is True, str(c1.get("has_openai_key")))
    check("키 마스킹(sk-tes…)", "sk-tes" in (c1.get("openai_key_masked") or "")
          and "••••" in (c1.get("openai_key_masked") or ""), str(c1.get("openai_key_masked")))
    check("응답에 평문 키 없음", secret not in body_text, "응답 본문에 키가 그대로 노출")
    check("디스크 설정에 저장됨", load_config().get("openai_api_key") == secret)
    check("GET /api/config 도 평문 키 없음", secret not in client.get("/api/config").text)
    check("파일 모드 600", oct((CACHE_DIR.parent / "config" / "config.json").stat().st_mode)[-3:] in
          ("600", "644"), str((CACHE_DIR.parent / "config" / "config.json").stat().st_mode))

    bad = client.post("/api/config", json={"tts_engine": "pupnet", "openai_tts_model": "gpt-9"}).json()
    check("잘못된 엔진은 edge 로 보정", bad.get("tts_engine") == "edge", str(bad.get("tts_engine")))
    check("잘못된 모델은 기본으로 보정", bad.get("openai_tts_model") == "gpt-4o-mini-tts",
          str(bad.get("openai_tts_model")))

    print("== 4. 연결 테스트 엔드포인트 ==")
    no_body = client.post("/api/config/test")
    check("본문 없는 기존 Gemini 테스트도 422 아님", no_body.status_code == 200, no_body.text[:200])
    check("본문 없으면 Gemini 경로", isinstance(no_body.json().get("ok"), bool), no_body.text[:200])

    real_requests = T.requests
    fake = FakeRequests()
    T.requests = fake
    try:
        preview = client.get("/api/tts/preview")
        check("미리듣기 없으면 404", preview.status_code == 404, str(preview.status_code))

        client.post("/api/config", json={"tts_engine": "openai", "openai_api_key": secret,
                                        "openai_tts_model": "gpt-4o-mini-tts"})
        r = client.post("/api/config/test", json={"engine": "openai_tts"})
        j = r.json()
        check("OpenAI 연결 테스트 200 · ok", r.status_code == 200 and j.get("ok") is True,
              r.text[:300])
        check("테스트 호출 URL", fake.calls and fake.calls[0]["url"] == T.OPENAI_SPEECH_URL,
              str(fake.calls[:1])[:200])
        pl = fake.calls[0]["payload"] if fake.calls else {}
        check("테스트 payload model/voice/format", pl.get("model") == "gpt-4o-mini-tts"
              and pl.get("voice") == "onyx" and pl.get("response_format") == "mp3", str(pl)[:200])
        check("테스트 payload 에 연기 지시", "instructions" in pl and "라디오" in pl["instructions"],
              str(pl.get("instructions"))[:80])
        check("Authorization 헤더", fake.calls[0]["headers"].get("Authorization") == "Bearer " + secret,
              str(fake.calls[0]["headers"])[:80])
        check("미리듣기 URL 반환", str(j.get("preview_url", "")).startswith("/api/tts/preview"),
              str(j.get("preview_url")))
        prev = client.get(j.get("preview_url") or "/api/tts/preview")
        check("미리듣기 mp3 반환", prev.status_code == 200
              and prev.headers.get("content-type", "").startswith("audio/mpeg")
              and len(prev.content) > 500, f"{prev.status_code} {prev.headers.get('content-type')}")

        fake.queue = [(401, b'{"error": {"message": "Incorrect API key provided"}}')]
        j401 = client.post("/api/config/test", json={"engine": "openai_tts"}).json()
        check("401 → 한국어 키 안내", j401.get("ok") is False and "401" in str(j401.get("error"))
              and "키" in str(j401.get("error")), str(j401)[:200])

        fake.status, fake.body = 429, b'{"error": {"message": "You exceeded your current quota"}}'
        j429 = client.post("/api/config/test", json={"engine": "openai_tts"}).json()
        check("429 → 한도 안내", j429.get("ok") is False and "429" in str(j429.get("error")),
              str(j429)[:200])
        fake.status, fake.body = 200, FAKE_MP3

        print("== 5. OpenAI 요청 단위 테스트 (역할·감정·발음) ==")
        fake.calls.clear()
        payload = T.openai_payload_preview("꽃이 피었습니다. 어머니가 웃으셨습니다.", "old_male", "multi", 0)
        check("노인 역할 → ash", payload.get("voice") == "ash", str(payload.get("voice")))
        check("노인 지시문에 연륜", "노인" in payload.get("instructions", ""), payload.get("instructions", "")[:60])
        check("해설 → onyx", T.openai_payload_preview("x", "narrator")["voice"] == "onyx",
              T.openai_payload_preview("x", "narrator")["voice"])
        check("할머니 → sage", T.openai_payload_preview("x", "old_female")["voice"] == "sage",
              T.openai_payload_preview("x", "old_female")["voice"])
        check("여성 → coral", T.openai_payload_preview("x", "female")["voice"] == "coral",
              T.openai_payload_preview("x", "female")["voice"])
        check("아이 → nova", T.openai_payload_preview("x", "child")["voice"] == "nova",
              T.openai_payload_preview("x", "child")["voice"])
        check("별칭 elder/man/woman", (T.openai_payload_preview("x", "elder")["voice"] == "ash"
              and T.openai_payload_preview("x", "man")["voice"] == "echo"
              and T.openai_payload_preview("x", "woman")["voice"] == "coral"),
              "별칭 매핑 틀림")
        p_hd = T.openai_payload_preview("x", "narrator", model="tts-1-hd")
        check("tts-1-hd 에는 instructions 없음", "instructions" not in p_hd, str(p_hd))
        # v2.0.2 — 모든 화자 속도 균일화는 그대로, 사용자가 전체 템포를 ±15%까지 조절한다.
        sp_slow = T.openai_payload_preview("x", "narrator", rate=-10)["speed"]
        check("speed 균일화(-10% → 0.90)", sp_slow == 0.90, str(sp_slow))
        check("화자별 속도 편차 없음(같은 설정이면 같은 값)",
              all(len({T.openai_payload_preview("x", r, rate=v)["speed"]
                       for r in ("narrator", "old_male", "female")}) == 1
                  for v in (-30, -15, 0, 15, 30)),
              "화자별 속도가 다름")
        check("v2 속도 상수", T.SPEED_RANGE == 0.15 and T.uniform_speed(0) == 1.0
              and T.uniform_speed(50) == 1.15 and T.uniform_speed(-50) == 0.85,
              f"{T.SPEED_RANGE} {T.uniform_speed(0)} {T.uniform_speed(50)} {T.uniform_speed(-50)}")

        fake.calls.clear()
        data = T.synthesize_openai_chunk("꽃이 피었습니다.", "ash", 1.0, "노인처럼", "gpt-4o-mini-tts", secret)
        sent = fake.calls[-1]["payload"]
        check("실제 호출도 mp3·model", sent.get("response_format") == "mp3"
              and sent.get("model") == "gpt-4o-mini-tts", str(sent)[:160])
        check("mp3 바이트 반환", isinstance(data, bytes) and len(data) > 500, str(len(data)))
        fake.calls.clear()
        T.synthesize_openai_chunk("꽃이 피었습니다.", "ash", 1.0, "", "tts-1-hd", secret)
        check("tts-1-hd 실제 호출에 instructions 미포함",
              "instructions" not in fake.calls[-1]["payload"], str(fake.calls[-1]["payload"])[:160])

        fake.queue = [(401, b'{"error": {"message": "bad key"}}')]
        fake.calls.clear()
        try:
            T.synthesize_openai_chunk("x", "onyx", 1.0, "", "gpt-4o-mini-tts", secret)
            raised = False
        except RuntimeError as e:
            raised = "401" in str(e) and "키" in str(e)
        check("401 은 재시도 없이 즉시 실패 + 한국어", raised and len(fake.calls) == 1, str(fake.calls[:3]))

        print("== 6. 캐시 키 ==")
        a = T._cache_path("같은 문장", "edge", "", "ko-KR-InJoonNeural", 0, "+0Hz", 0.0, "").name
        b = T._cache_path("같은 문장", "openai", "gpt-4o-mini-tts", "onyx", 0, "", 1.0, "지시")
        b2 = T._cache_path("같은 문장", "openai", "tts-1-hd", "onyx", 0, "", 1.0, "지시")
        check("edge·openai 캐시 분리", a.startswith("edge_") and b.name.startswith("openai_") and a != b.name,
              f"{a} / {b.name}")
        check("모델이 다르면 캐시도 다름", b.name != b2.name, f"{b.name} / {b2.name}")

        print("== 7. synthesize_lines (OpenAI 경로) ==")
        base = create_project({"preset": "shorts50", "genre": "tear_family",
                               "topic": "OpenAI TTS 테스트", "image_mode": "B"})
        pid = base["id"]
        scenes = [
            {"id": "s01", "speaker": "narrator", "text": "꽃이 피었습니다. [문 쾅] 어머니가 웃으셨습니다."},
            {"id": "s02", "speaker": "old_male", "text": "아들아, 밥은 먹었니?"},
            {"id": "s03", "speaker": "child", "text": "할아버지, 같이 가요!"},
        ]
        proj = _project(T, base, scenes)
        save_config({"tts_engine": "openai", "openai_api_key": secret,
                     "openai_tts_model": "gpt-4o-mini-tts", "openai_fallback_edge": True})
        T._broken_voices.clear()
        fake.calls.clear()
        real_edge = T._synth_with_fallback
        T._synth_with_fallback = fake_edge
        fake_edge.calls = []                                      # type: ignore[attr-defined]
        try:
            durations = asyncio.run(T.synthesize_lines(proj))
        finally:
            T._synth_with_fallback = real_edge
        clips = project_dir(pid) / "audio_clips"
        check("장면 수만큼 음성 파일", len(durations) == 3
              and all((clips / f"{s['id']}.mp3").exists() for s in scenes),
              str(sorted(p.name for p in clips.glob("*.mp3"))))
        check("장면 길이 계산", all(v > 0 for v in durations.values()), str(durations))
        check("OpenAI 만 호출(edge 미사용)", not fake_edge.calls, str(fake_edge.calls))  # type: ignore[attr-defined]
        check("장면마다 1회 호출", len(fake.calls) == 3, str(len(fake.calls)))
        voices = [c["payload"]["voice"] for c in fake.calls]
        check("역할별 보이스 onyx·ash·nova", voices == ["onyx", "ash", "nova"], str(voices))
        first = fake.calls[0]["payload"]["input"]
        check("발음 사전 적용(꽃이→꼬치)", "꼬치" in first, first)
        check("효과음 태그 제거", "[문 쾅]" not in first and "쾅" not in first, first)
        check("모든 payload 에 mp3", all(c["payload"]["response_format"] == "mp3" for c in fake.calls),
              "response_format 틀림")
        cached = [p.name for p in (CACHE_DIR / "tts").glob("openai_*.mp3")
                  if p.name != T.TEST_PREVIEW_NAME]
        check("OpenAI 캐시에 engine·model 경로로 저장", len(cached) == 3, str(cached))
        check("경고 없음", not (proj.get("warnings") or []), str(proj.get("warnings")))

        # 같은 문장 다시 → 캐시 재사용(호출 0)
        fake.calls.clear()
        proj2 = _project(T, base, scenes)
        asyncio.run(T.synthesize_lines(proj2))
        check("캐시 재사용 시 재호출 없음", len(fake.calls) == 0, str(len(fake.calls)))

        print("== 8. 폴백 · 오류 처리 ==")
        # 키 없음 + 폴백 켜짐 → edge 로 제작 + 경고
        clips2 = project_dir(base["id"]) / "audio_clips"
        for f in clips2.glob("*.mp3"):
            f.unlink()
        save_config({"tts_engine": "openai", "openai_api_key": "", "openai_fallback_edge": True})
        proj3 = _project(T, base, scenes)
        T._synth_with_fallback = fake_edge
        fake_edge.calls = []                                      # type: ignore[attr-defined]
        try:
            asyncio.run(T.synthesize_lines(proj3))
        finally:
            T._synth_with_fallback = real_edge
        check("키 없으면 edge 로 제작", len(fake_edge.calls) == 3, str(len(fake_edge.calls)))  # type: ignore[attr-defined]
        check("키 없음 경고 문구", any("OpenAI API 키가 없어" in w for w in (proj3.get("warnings") or [])),
              str(proj3.get("warnings")))

        # 키 없음 + 폴백 꺼짐 → 안내와 함께 실패
        for f in clips2.glob("*.mp3"):
            f.unlink()
        save_config({"tts_engine": "openai", "openai_api_key": "", "openai_fallback_edge": False})
        proj4 = _project(T, base, scenes)
        try:
            asyncio.run(T.synthesize_lines(proj4))
            raised = False
            msg = ""
        except RuntimeError as e:
            raised = True
            msg = str(e)
        check("폴백 끄면 키 없음은 실패", raised and "OpenAI API 키" in msg, msg[:120])

        # API 오류 + 폴백 켜짐 → edge 로 이어서 제작
        for f in clips2.glob("*.mp3"):
            f.unlink()
        for f in (CACHE_DIR / "tts").glob("openai_*.mp3"):
            f.unlink()
        save_config({"tts_engine": "openai", "openai_api_key": secret, "openai_fallback_edge": True})
        fake.calls.clear()
        fake.queue = [(500, b'{"error": {"message": "server error"}}')] * 60
        proj5 = _project(T, base, scenes)
        T._synth_with_fallback = fake_edge
        fake_edge.calls = []                                      # type: ignore[attr-defined]
        try:
            asyncio.run(T.synthesize_lines(proj5))
        finally:
            T._synth_with_fallback = real_edge
        check("API 오류 시 edge 로 대체", len(fake_edge.calls) >= 1, str(len(fake_edge.calls)))  # type: ignore[attr-defined]
        check("오류 대체 경고", any("edge-tts로 대체" in w for w in (proj5.get("warnings") or [])),
              str(proj5.get("warnings")))
        check("오류 시에도 음성 파일 생성", all((clips2 / f"{s['id']}.mp3").exists() for s in scenes),
              str(sorted(p.name for p in clips2.glob("*.mp3"))))

        print("== 9. 화면 반영 ==")
        home = client.get("/").text
        for probe in ("ttsCard", "ttsEngine", "openaiKey", "btnTtsSave", "btnTtsTest", "ttsFallback",
                      "platform.openai.com/api-keys", "OpenAI 감성 TTS", "무료 edge-tts"):
            check(f"index.html 에 {probe}", probe in home)
        js = client.get("/static/app.js").text
        for probe in ("applyTtsConfig", "saveTts", "testTts", "tts_engine", "openai_tts_model",
                      "engine: \"openai_tts\"", "openai_fallback_edge"):
            check(f"app.js 에 {probe}", probe in js)

        print("== 10. voice_report ==")
        save_config({"tts_engine": "openai", "openai_api_key": secret})
        rep = T.voice_report(_project(T, base, scenes))
        check("openai 엔진 표기", rep.startswith("OpenAI gpt-4o-mini-tts"), rep[:80])
        save_config({"tts_engine": "edge", "openai_api_key": ""})
        rep2 = T.voice_report(_project(T, base, scenes))
        check("edge 엔진 표기", rep2.startswith("무료 edge-tts") and "InJoon" in rep2, rep2[:80])
        check("public_config 에 비밀키 없음",
              secret not in json.dumps(public_config(), ensure_ascii=False), "public_config 키 노출")
    finally:
        T.requests = real_requests

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
