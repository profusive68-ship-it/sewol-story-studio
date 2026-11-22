"""세월의 사연극장 v1.2.0 — 새 기능 검증 (네트워크·실제 렌더 없음).

확인 항목
1. VERSION / app.__version__ 일치
2. Gemini 모델 재시도·폴백 (503 → 1.5초 뒤 1회, 404 → 다음 모델, 옛 설정 모델보다 최신 모델 우선)
3. `GET /api/projects/{pid}/images` 갤러리 (mtime·url·장면·지문)
4. `GET /api/projects/{pid}/image/{idx}` (캐시방지 헤더·ETag·304) + 파일명 경로 호환
5. `[✏️ 케빈에게 이미지 수정 요청]` — [이미지수정] 제목·image-revision 라벨·target_inbox·지시 본문
6. `GET /api/projects/{pid}/kevin-timeline` — 공개 저장소 이슈·댓글 타임라인
7. `/api/update/pull` — VERSION 불일치(백그라운드 pull 이후 포함) 시 `restarting: true` + 같은 포트 재시작

    python3 tools/selftest_v120.py
"""
from __future__ import annotations

import json
import shutil
import sys
import threading
import traceback
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORK = ROOT / ".cache" / "selftest_v120"

PASS: list[str] = []
FAIL: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    if cond:
        PASS.append(name)
        print(f"  ✅ {name}")
    else:
        FAIL.append(f"{name} — {detail}")
        print(f"  ❌ {name} {detail}")


# ── PNG 한 장 (실제 이미지처럼 보이는 작은 파일) ─────────────────────────
PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000a49444154789c6300010000050001")


def _png(variant: int = 0) -> bytes:
    return PNG + bytes([variant % 256]) * (24 + variant)


class FakeGitHub(BaseHTTPRequestHandler):
    calls: list[dict] = []
    issues: list[dict] = []
    comments: dict[int, list[dict]] = {}
    fail_issues = False

    def log_message(self, *args):
        pass

    def _send(self, code: int, data) -> None:
        body = json.dumps(data).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        FakeGitHub.calls.append({"method": "GET", "path": self.path,
                                 "auth": self.headers.get("Authorization", "")})
        path = urllib.parse.urlparse(self.path).path
        if path.endswith("/issues"):
            if FakeGitHub.fail_issues:
                self._send(500, {"message": "boom"})
                return
            self._send(200, FakeGitHub.issues)
            return
        if path.endswith("/comments") and "/issues/" in path:
            num = int(path.split("/issues/")[1].split("/")[0])
            self._send(200, FakeGitHub.comments.get(num, []))
            return
        if path.endswith("/user"):
            self._send(200, {"login": "tester"})
            return
        if "/repos/" in path:
            self._send(200, {"permissions": {"push": True, "admin": True},
                             "has_issues": True, "private": False})
            return
        self._send(404, {"message": "not found"})

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(n) if n else b"{}"
        try:
            payload = json.loads(raw or b"{}")
        except Exception:
            payload = {}
        FakeGitHub.calls.append({"method": "POST", "path": self.path, "payload": payload,
                                 "auth": self.headers.get("Authorization", "")})
        path = urllib.parse.urlparse(self.path).path
        if path.endswith("/labels"):
            self._send(201, {"name": payload.get("name")})
            return
        if path.endswith("/issues"):
            self._send(201, {"number": 42, "html_url": "https://github.com/x/y/issues/42"})
            return
        self._send(404, {"message": "not found"})


def main() -> int:
    global WORK
    print("== 임시 폴더 준비 ==")
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
    (app_root / ".git").mkdir(parents=True, exist_ok=True)      # 재시작 판정용(실제 repo 아님)
    sys.path.insert(0, str(app_root))

    from fastapi.testclient import TestClient  # noqa: E402

    from app import __version__ as pkg_version  # noqa: E402
    from app import gemini_script as gs  # noqa: E402
    from app import github_issue as gh  # noqa: E402
    from app import inbox_watch as ib  # noqa: E402
    from app import main as web  # noqa: E402
    from app.paths import BASE, project_dir  # noqa: E402
    from app.project import create_project, load  # noqa: E402

    print("== 1. 버전 ==")
    disk = (BASE / "VERSION").read_text(encoding="utf-8").strip()
    check("VERSION == app.__version__", disk == pkg_version, f"{disk} / {pkg_version}")
    check("버전이 1.2.0 이상", tuple(int(x) for x in disk.split(".") if x.isdigit()) >= (1, 2, 0), disk)

    print("== 2. Gemini 재시도·폴백 ==")

    class FakeResp:
        def __init__(self, text):
            self.text = text

    class FakeModels:
        def __init__(self, script):
            self.script = script          # {model: [예외 또는 텍스트, ...]}
            self.calls: list[str] = []

        def generate_content(self, model, contents, config=None):
            self.calls.append(model)
            seq = list(self.script.get(model) or [RuntimeError("no script")])
            item = seq.pop(0) if len(seq) > 1 else seq[0]
            self.script[model] = seq
            if isinstance(item, Exception):
                raise item
            return FakeResp(item)

    class FakeClient:
        def __init__(self, script):
            self.models = FakeModels(script)

    sleeps: list[float] = []
    real_sleep = gs.time.sleep
    gs.time.sleep = lambda s: sleeps.append(s)
    try:
        # 옛 설정(gemini-2.5-flash)이 저장돼 있어도 최신 모델을 먼저 시도
        cfg_legacy = {"gemini_api_key": "k", "text_model": "gemini-2.5-flash"}
        models = gs._models(cfg_legacy)
        check("옛 설정 모델보다 최신 모델 우선", models[0] == "gemini-3.8-flash", str(models[:3]))
        check("폴백 순서 2.5-flash-lite → 2.0-flash → 2.5-flash",
              models[1:4] == ["gemini-2.5-flash", "gemini-2.5-flash-lite", "gemini-2.0-flash"], str(models))
        nested = [m for i, m in enumerate(models) if m in models[:i]]
        check("모델 목록에 중복 없음", not nested, str(nested))

        # 404 → 다음 모델로 폴백
        client = FakeClient({"gemini-3.8-flash": [RuntimeError("404 NOT_FOUND: model not found")],
                             "gemini-2.5-flash": ["ok"]})
        out = gs.call_gemini({"gemini_api_key": "k", "text_model": "gemini-2.5-flash"},
                             "hi", response_json=False, client=client)
        check("404 → 다음 모델로 폴백", out == "ok" and client.models.calls ==
              ["gemini-3.8-flash", "gemini-2.5-flash"], str(client.models.calls))

        # 503 → 1.5초 뒤 1회 재시도
        sleeps.clear()
        client = FakeClient({"gemini-3.8-flash": [RuntimeError("503 UNAVAILABLE: overloaded"), "good"]})
        out = gs.call_gemini({"gemini_api_key": "k", "text_model": "gemini-3.8-flash"},
                             "hi", response_json=False, client=client)
        check("503 → 1회 재시도 후 성공", out == "good" and len(client.models.calls) == 2,
              str(client.models.calls))
        check("503 재시도 전 1.5초 대기", sleeps == [gs.RETRY_SECONDS], str(sleeps))

        # 429 두 번 → 다른 모델로
        sleeps.clear()
        client = FakeClient({"gemini-3.8-flash": [RuntimeError("429 RESOURCE_EXHAUSTED"),
                                                 RuntimeError("429 RESOURCE_EXHAUSTED")],
                             "gemini-2.5-flash": ["next"]})
        out = gs.call_gemini({"gemini_api_key": "k", "text_model": "gemini-2.5-flash"},
                             "hi", response_json=False, client=client)
        check("429 두 번이면 다음 모델", out == "next" and len(sleeps) == 1, str(client.models.calls))

        # 인증 오류는 재시도하지 않고 즉시 실패
        sleeps.clear()
        client = FakeClient({"gemini-3.8-flash": [RuntimeError("API key not valid")],
                             "gemini-2.5-flash": ["should not"]})
        try:
            gs.call_gemini({"gemini_api_key": "k", "text_model": "gemini-3.8-flash"},
                           "hi", response_json=False, client=client)
            raised = False
        except Exception:
            raised = True
        check("인증 오류는 즉시 실패", raised and client.models.calls == ["gemini-3.8-flash"],
              str(client.models.calls))

        # 전부 404 → 마지막 오류를 알려 준다
        client = FakeClient({m: [RuntimeError("404 NOT_FOUND")] for m in gs._models(
            {"gemini_api_key": "k", "text_model": "gemini-3.8-flash"})})
        try:
            gs.call_gemini({"gemini_api_key": "k", "text_model": "gemini-3.8-flash"},
                           "hi", response_json=False, client=client)
            all_failed = False
        except RuntimeError:
            all_failed = True
        check("모든 모델 실패 시 RuntimeError", all_failed, str(client.models.calls))
    finally:
        gs.time.sleep = real_sleep

    print("== 3. 프로젝트 + 갤러리 ==")
    p = create_project({"preset": "shorts50", "genre": "tear_family",
                        "topic": "갤러리 테스트", "image_mode": "B"})
    pid = p["id"]
    plan = p.get("image_plan") or []
    check("이미지 계획이 있다", len(plan) > 0, str(len(plan)))
    imgs = project_dir(pid) / "images"
    imgs.mkdir(parents=True, exist_ok=True)
    (imgs / plan[0]["file"]).write_bytes(_png(1))
    client = TestClient(web.app)

    g = client.get(f"/api/projects/{pid}/images")
    check("GET /images 200", g.status_code == 200, g.text[:200])
    data = g.json()
    row = data["images"][0]
    check("갤러리 첫 컷 found", row["found"] and row["idx"] == 1, str(row))
    check("갤러리 mtime·url", row["mtime"] > 0 and row["url"] ==
          f"/api/projects/{pid}/image/1?v={row['mtime']}", row.get("url"))
    check("갤러리 장면 설명 포함", "caption" in row and "prompt" in row and "line" in row, str(row.keys()))
    check("갤러리 지문(signature)", bool(data.get("signature")), data.get("signature"))
    check("갤러리 전체 장수", data["total"] == len(plan) and data["found"] == 1,
          f"{data['total']}/{data['found']}")
    check("없는 사연 갤러리 → 404",
          client.get("/api/projects/nope-000/images").status_code == 404)
    check("없는 사연 이미지 → 404",
          client.get("/api/projects/nope-000/image/1").status_code == 404)

    print("== 4. 이미지 엔드포인트 (컷 번호) ==")
    r = client.get(f"/api/projects/{pid}/image/1")
    check("GET /image/1 200 PNG", r.status_code == 200 and r.content.startswith(b"\x89PNG"),
          f"{r.status_code}")
    cc = r.headers.get("cache-control", "")
    check("캐시방지 헤더", "no-cache" in cc, cc)
    etag = r.headers.get("etag", "")
    check("ETag 있음", bool(etag), etag)
    r304 = client.get(f"/api/projects/{pid}/image/1", headers={"If-None-Match": etag})
    check("같은 ETag → 304", r304.status_code == 304, str(r304.status_code))
    check("없는 컷 → 404", client.get(f"/api/projects/{pid}/image/{len(plan) + 5}").status_code == 404)
    r_file = client.get(f"/api/projects/{pid}/image/{plan[0]['file']}")
    check("파일명 경로도 그대로 동작", r_file.status_code == 200 and r_file.content == r.content)

    sig1 = client.get(f"/api/projects/{pid}/images").json()["signature"]
    (imgs / plan[1]["file"]).write_bytes(_png(2))
    sig2 = client.get(f"/api/projects/{pid}/images").json()["signature"]
    check("이미지가 늘면 지문이 바뀐다", sig1 != sig2 and sig2, sig2[:60])
    check("같은 상태면 지문 동일",
          client.get(f"/api/projects/{pid}/images").json()["signature"] == sig2)

    print("== 5. 이미지 수정 요청 (URL 방식) ==")
    off = client.post(f"/api/projects/{pid}/github-request",
                      json={"mode": "auto", "kind": "image_revision", "instruction": "  "})
    check("지시 없으면 400", off.status_code == 400, off.text[:160])
    inst = "3번 컷 표정 더 놀랍게, 5번 더 밝게"
    r = client.post(f"/api/projects/{pid}/github-request",
                    json={"mode": "auto", "kind": "image_revision", "instruction": inst})
    check("수정 요청 200", r.status_code == 200, r.text[:300])
    d = r.json()
    check("토큰 없으면 url 방식", d.get("mode") == "url", d.get("mode"))
    check("target_inbox", d.get("target_inbox") == f"assets_inbox/{pid}", d.get("target_inbox"))
    check("라벨 image-revision", d.get("labels") == ["image-revision"], str(d.get("labels")))
    check("제목 [이미지수정] pid - 주제", d.get("title", "").startswith(f"[이미지수정] {pid} - "), d.get("title"))
    q = urllib.parse.parse_qs(urllib.parse.urlparse(d["url"]).query)
    body = (q.get("body") or [""])[0]
    check("URL 본문에 target_inbox", f"target_inbox: assets_inbox/{pid}" in body, body[:160])
    check("URL 본문에 수정 지시", inst in body, body[:300])
    check("URL 본문에 받은 컷 장수", "받음 2장" in body, body[:400])
    check("URL 에 labels=image-revision", q.get("labels", [""])[0] == "image-revision", str(q.get("labels")))
    check("URL 길이 한도 이내", len(d["url"]) <= gh.MAX_URL_CHARS, str(len(d["url"])))
    log = (load(pid).get("request_log") or [])[-1]
    check("요청 기록에 kind·지시", log.get("kind") == "image_revision" and inst in log.get("instruction", ""),
          str(log))

    print("== 6. 이미지 수정 요청 (이슈 API 방식, 가짜 깃허브) ==")
    srv = ThreadingHTTPServer(("127.0.0.1", 0), FakeGitHub)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    real_base = gh.API_BASE
    real_tok = gh.token
    gh.API_BASE = f"http://127.0.0.1:{srv.server_address[1]}"
    gh.token = lambda: "ghs_dummy"
    try:
        FakeGitHub.calls.clear()
        r = client.post(f"/api/projects/{pid}/github-request",
                        json={"mode": "auto", "kind": "image_revision", "instruction": "2번 컷 더 어둡게"})
        d = r.json()
        check("토큰 있으면 api 방식", d.get("mode") == "api" and d.get("number") == 42, str(d)[:300])
        posts = [c for c in FakeGitHub.calls if c["method"] == "POST"]
        labels_call = [c for c in posts if c["path"].endswith("/labels")]
        issue_call = [c for c in posts if c["path"].endswith("/issues")]
        check("image-revision 라벨 확보", bool(labels_call) and
              labels_call[0]["payload"].get("name") == "image-revision", str(labels_call))
        sent = issue_call[0]["payload"] if issue_call else {}
        check("이슈 라벨 image-revision", sent.get("labels") == ["image-revision"], str(sent.get("labels")))
        check("이슈 제목 [이미지수정]", sent.get("title", "").startswith(f"[이미지수정] {pid} - "), sent.get("title"))
        check("이슈 본문에 지시·target_inbox",
              "2번 컷 더 어둡게" in sent.get("body", "") and f"assets_inbox/{pid}" in sent.get("body", ""),
              str(sent.get("body"))[:200])
        check("토큰은 Authorization 헤더로만", issue_call and issue_call[0]["auth"] == "Bearer ghs_dummy",
              str(issue_call[0]["auth"] if issue_call else ""))

        print("== 7. 케빈 실시간 진행 타임라인 ==")
        FakeGitHub.issues = [
            {"number": 7, "title": f"[이미지요청] {pid} - 갤러리", "state": "open",
             "body": f"target_inbox: assets_inbox/{pid}", "html_url": "https://github.com/x/y/issues/7",
             "created_at": "2026-11-22T01:00:00Z", "comments": 2},
            {"number": 8, "title": "[이미지수정] 다른사연 - x", "state": "closed",
             "body": "target_inbox: assets_inbox/other", "html_url": "https://github.com/x/y/issues/8",
             "created_at": "2026-11-22T02:00:00Z", "closed_at": "2026-11-22T03:00:00Z", "comments": 0},
        ]
        FakeGitHub.comments = {7: [
            {"body": "이미지 3장 만들었습니다", "created_at": "2026-11-22T01:30:00Z",
             "html_url": "https://github.com/x/y/issues/7#c1"},
            {"body": "s01.png 올렸습니다", "created_at": "2026-11-22T01:20:00Z",
             "html_url": "https://github.com/x/y/issues/7#c2"},
        ]}
        t = client.get(f"/api/projects/{pid}/kevin-timeline")
        check("timeline 200", t.status_code == 200, t.text[:200])
        td = t.json()
        check("timeline ok", td.get("ok") is True, str(td)[:200])
        texts = [e["text"] for e in td["events"]]
        checks_join = " | ".join(texts)
        check("요청 등록 이벤트", any("요청 등록 (#7)" in x for x in texts), checks_join[:200])
        check("댓글 2개 표시", sum(1 for e in td["events"] if e["kind"] == "comment") == 2, checks_join[:300])
        check("다른 사연 이슈 제외", all(e["issue"] == 7 for e in td["events"]), checks_join[:200])
        ats = [e["at"] for e in td["events"]]
        check("시간순 정렬", ats == sorted(ats), str(ats))
        check("토큰이 있으면 인증 조회", any(c["method"] == "GET" and "issues" in c["path"]
                                              and c["auth"] for c in FakeGitHub.calls), "")

        gh.token = lambda: ""
        FakeGitHub.calls.clear()
        anon = client.get(f"/api/projects/{pid}/kevin-timeline").json()
        get_calls = [c for c in FakeGitHub.calls if c["method"] == "GET" and "/issues" in c["path"]]
        check("토큰 없으면 비인증 조회", anon.get("ok") is True and
              bool(get_calls) and all(not c["auth"] for c in get_calls), str(get_calls[:1]))

        FakeGitHub.fail_issues = True
        bad = client.get(f"/api/projects/{pid}/kevin-timeline").json()
        check("깃허브 오류는 ok False + error", bad.get("ok") is False and bad.get("error"), str(bad)[:200])
        FakeGitHub.fail_issues = False
    finally:
        gh.API_BASE = real_base
        gh.token = real_tok
        srv.shutdown()

    print("== 8. 업데이트 후 제자리 재시작 ==")
    check("재시작 명령이 uvicorn 같은 포트",
          web._restart_argv(9123) == [sys.executable, "-m", "uvicorn", "app.main:app",
                                      "--host", "0.0.0.0", "--port", "9123"],
          str(web._restart_argv(9123)))

    real_port = web._server_port()
    check("_server_port 기본값(8765~)", 8765 <= real_port <= 8770, str(real_port))
    real_argv = list(sys.argv)
    try:
        sys.argv = ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8767"]
        check("--port 인자에서 포트를 읽는다", web._server_port() == 8767, str(web._server_port()))
        sys.argv = ["python", "-m", "uvicorn", "app.main:app", "--port=8768"]
        check("--port= 형태도 읽는다", web._server_port() == 8768, str(web._server_port()))
    finally:
        sys.argv = real_argv

    restarts: list[int] = []
    real_schedule = web._schedule_restart
    real_pull = ib.git_pull
    web._schedule_restart = lambda port: restarts.append(port)
    ib.git_pull = lambda timeout=120: {"ok": True, "reason": "up_to_date",
                                       "message": "Already up to date."}
    real_version = web.__version__
    try:
        # 백그라운드 워커가 먼저 pull 했어도 VERSION 파일이 다르면 재시작
        (BASE / "VERSION").write_text("9.9.9\n", encoding="utf-8")
        job = client.post("/api/update/pull").json()["job"]
        for _ in range(60):
            jr = client.get(f"/api/jobs/{job}").json()
            if jr["status"] in ("done", "error"):
                break
            threading.Event().wait(0.1)
        res = jr.get("result") or {}
        check("VERSION 불일치 → restarting true", jr["status"] == "done" and res.get("restarting") is True,
              str(res)[:300])
        check("디스크/실행 버전을 함께 돌려준다",
              res.get("disk_version") == "9.9.9" and res.get("running_version") == real_version,
              str(res)[:200])
        check("같은 포트로 재시작 예약", restarts == [real_port], str(restarts))
        check("재시작 안내 문구", "새로고침" in str(res.get("message", "")), str(res.get("message"))[:120])

        # 같은 버전이면 재시작하지 않는다
        restarts.clear()
        (BASE / "VERSION").write_text(real_version + "\n", encoding="utf-8")
        job = client.post("/api/update/pull").json()["job"]
        for _ in range(60):
            jr = client.get(f"/api/jobs/{job}").json()
            if jr["status"] in ("done", "error"):
                break
            threading.Event().wait(0.1)
        res = jr.get("result") or {}
        check("변경 없으면 restarting false", res.get("restarting") is False, str(res)[:200])
        check("변경 없으면 재시작 예약 없음", restarts == [], str(restarts))
    finally:
        web._schedule_restart = real_schedule
        ib.git_pull = real_pull
        web.__version__ = real_version
        (BASE / "VERSION").write_text(real_version + "\n", encoding="utf-8")

    print("== 9. 화면 연결 (app.js · style.css) ==")
    js = client.get("/static/app.js").text
    for probe in ("loadGallery", "renderGallery", "imgGallery", "imgLightbox", "pickCut",
                  "kevin-timeline", "loadKevinTimeline", "image_revision", "location.reload",
                  "restarting", "GALLERY_SIG"):
        check(f"app.js 에 {probe}", probe in js)
    css = client.get("/static/style.css").text
    for probe in (".img-grid.gallery", ".lightbox", ".logbox", ".revise-result"):
        check(f"style.css 에 {probe}", probe in css)
    home = client.get("/").text
    check("index.html 로드", "세월의 사연극장" in home)

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
