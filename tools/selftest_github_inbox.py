"""세월의 사연극장 — 깃허브 이미지 요청 · assets_inbox 자동 수신 셀프테스트.

깃허브·인터넷에 아무것도 쓰지 않는다. 임시 폴더에 앱 사본과 가짜 원격 저장소를 만들어
엔드포인트·매칭·git pull·실패 처리까지 확인한다.

    python3 tools/selftest_github_inbox.py
"""
from __future__ import annotations

import json
import shutil
import socket
import subprocess
import sys
import threading
import time
import traceback
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORK = ROOT / ".cache" / "selftest_github_inbox"

PASS: list[str] = []
FAIL: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    if cond:
        PASS.append(name)
        print(f"  ✅ {name}")
    else:
        FAIL.append(f"{name} — {detail}")
        print(f"  ❌ {name} {detail}")


def run(cmd: list[str], cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True)


# ── 가짜 깃허브 API ────────────────────────────────────────────────────────
class MockGitHub(BaseHTTPRequestHandler):
    calls: list[dict] = []
    reject_labels = False      # 라벨이 거부되는 상황(422)을 흉내낼 때

    def log_message(self, *args):  # 조용히
        pass

    def _read(self) -> dict:
        n = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(n) if n else b"{}"
        try:
            return json.loads(raw or b"{}")
        except Exception:
            return {}

    def _send(self, code: int, data: dict) -> None:
        body = json.dumps(data).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path.endswith("/user"):
            self._send(200, {"login": "tester"})
            return
        if "/repos/" in self.path:
            self._send(200, {"permissions": {"push": True, "admin": True},
                             "has_issues": True, "private": False})
            return
        self._send(404, {"message": "not found"})

    def do_POST(self):
        payload = self._read()
        MockGitHub.calls.append({"path": self.path, "payload": payload,
                                 "auth": self.headers.get("Authorization", "")})
        if self.path.endswith("/labels"):
            self._send(201, {"name": payload.get("name")})
            return
        if self.path.endswith("/issues"):
            if MockGitHub.reject_labels and payload.get("labels"):
                self._send(422, {"message": "Validation Failed"})
                return
            self._send(201, {"number": 7, "html_url": "https://github.com/example/issues/7"})
            return
        self._send(404, {"message": "not found"})


def free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def main() -> int:
    global WORK
    print("== 임시 폴더 준비 (인터넷·깃허브에 쓰지 않음) ==")
    if WORK.exists():
        shutil.rmtree(WORK, ignore_errors=True)
    if WORK.exists():        # git 이 잠금을 물고 있으면 다른 이름으로 새로 시작한다
        WORK = WORK.parent / f"selftest_github_inbox_{time.strftime('%H%M%S')}"
    app_root = WORK / "app_root"
    app_root.mkdir(parents=True)
    for name in ("app", "static", "assets_inbox", "config", "sfx_library"):
        src = ROOT / name
        if not src.exists():
            continue
        dst = app_root / name
        if src.is_dir():
            shutil.copytree(src, dst, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        else:
            shutil.copy2(src, dst)
    (app_root / "projects").mkdir(parents=True, exist_ok=True)
    (app_root / "assets_inbox").mkdir(parents=True, exist_ok=True)
    (app_root / "config").mkdir(parents=True, exist_ok=True)
    print(f"  {app_root}")

    sys.path.insert(0, str(app_root))
    from fastapi.testclient import TestClient  # noqa: E402

    from app import github_issue as gh  # noqa: E402
    from app import inbox_watch as ib  # noqa: E402
    from app import main as web  # noqa: E402
    from app import scheduler as sch  # noqa: E402
    from app.paths import project_dir  # noqa: E402
    from app.project import create_project, load  # noqa: E402
    from app.settings import save_config  # noqa: E402

    print("== 1. 요청서에 target_inbox 명시 ==")
    p = create_project({"preset": "full40", "genre": "tear_family",
                        "topic": "제주 서귀포 김치통", "image_mode": "B"})
    pid = p["id"]
    req_path = project_dir(pid) / "이미지_요청서.txt"
    text = req_path.read_text(encoding="utf-8")
    check("요청서에 target_inbox 줄이 있다", f"target_inbox: assets_inbox/{pid}" in text,
          text[:200])
    check("요청서에 project_id 줄이 있다", f"project_id: {pid}" in text)
    check("이슈 제목 형식이 [이미지요청] pid - 주제", gh.issue_title(p).startswith(f"[이미지요청] {pid} - "),
          gh.issue_title(p))
    plan = gh.build_request(p, text)
    check("이슈 본문에 target_inbox", f"target_inbox: assets_inbox/{pid}" in plan["body"])
    check("URL 이 github issues/new", plan["url"].startswith("https://github.com/profusive68-ship-it/sewol-story-studio/issues/new?"))
    check("URL 길이가 5,600자 이하", len(plan["url"]) <= gh.MAX_URL_CHARS, str(len(plan["url"])))
    q = urllib.parse.parse_qs(urllib.parse.urlparse(plan["url"]).query)
    check("URL 에 제목이 실려 있다", q.get("title", [""])[0] == plan["title"], str(q.get("title")))
    if q.get("body"):
        check("URL 본문에 target_inbox", f"assets_inbox/{pid}" in q["body"][0])
    print(f"     prefill={plan['prefill']} copy_body={plan['copy_body']} url_len={len(plan['url'])}")

    print("== 2. FastAPI 엔드포인트 ==")
    client = TestClient(web.app)
    r = client.get("/api/github/status")
    check("GET /api/github/status", r.status_code == 200 and r.json()["repo"].endswith("sewol-story-studio"), r.text[:200])
    check("토큰 없음 상태", r.json()["has_token"] is False)

    r = client.post(f"/api/projects/{pid}/github-request", json={"mode": "auto"})
    data = r.json()
    check("토큰 없이 요청 → url 모드", r.status_code == 200 and data.get("mode") == "url", r.text[:300])
    check("토큰 없이 요청 → 주소 반환", data.get("url", "").startswith("https://github.com/"), data.get("url", ""))
    check("토큰 없이 요청 → 전체 본문 동봉", bool(data.get("body")) and "target_inbox" in data.get("body", ""))
    check("project.json 에 요청 기록", bool(load(pid).get("request_log")))

    r = client.get("/api/inbox/auto")
    st = r.json()
    check("GET /api/inbox/auto", r.status_code == 200 and st["enabled"] is True and st["poll_seconds"] == 20, r.text[:200])
    r = client.post("/api/inbox/auto", json={"enabled": False})
    check("자동 수신 끄기", r.json()["enabled"] is False)
    check("설정 파일에 저장", sch.load_settings().get("auto_receive") is False)
    r = client.post("/api/inbox/auto", json={"enabled": True, "auto_assemble": True})
    check("자동 수신 켜기 + 자동 조립 옵션", r.json()["enabled"] is True and r.json()["auto_assemble"] is True)
    client.post("/api/inbox/auto", json={"auto_assemble": False})

    print("== 3. 가짜 깃허브 API 로 이슈 등록 (실제 깃허브에 쓰지 않음) ==")
    port = free_port()
    srv = ThreadingHTTPServer(("127.0.0.1", port), MockGitHub)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    gh.API_BASE = f"http://127.0.0.1:{port}"
    save_config({"github_token": "ghs_test_token_value"})
    try:
        r = client.post("/api/github/test")
        check("토큰 연결 테스트", r.json().get("ok") is True and r.json().get("can_push") is True, r.text[:300])
        r = client.post(f"/api/projects/{pid}/github-request", json={"mode": "auto"})
        data = r.json()
        check("토큰 있으면 api 모드", data.get("mode") == "api", r.text[:300])
        check("이슈 번호·주소 반환", data.get("number") == 7 and data.get("url", "").endswith("/issues/7"), str(data)[:300])
        label_call = [c for c in MockGitHub.calls if c["path"].endswith("/labels")]
        issue_call = [c for c in MockGitHub.calls if c["path"].endswith("/issues")]
        check("image-request 라벨 확보", bool(label_call) and label_call[0]["payload"]["name"] == "image-request")
        check("이슈 POST 1회", len(issue_call) == 1, str(len(issue_call)))
        sent = issue_call[0]["payload"] if issue_call else {}
        check("이슈 제목 형식", str(sent.get("title", "")).startswith(f"[이미지요청] {pid} - "))
        check("이슈 라벨 image-request", sent.get("labels") == ["image-request"], str(sent.get("labels")))
        check("이슈 본문에 target_inbox", f"assets_inbox/{pid}" in str(sent.get("body", "")))
        check("토큰은 Authorization 헤더로만", issue_call[0]["auth"] == "Bearer ghs_test_token_value")

        # 라벨이 거부되는 경우(422)에도 이슈는 등록되어야 한다
        MockGitHub.reject_labels = True
        r = client.post(f"/api/projects/{pid}/github-request", json={"mode": "auto"})
        data = r.json()
        issues = [c for c in MockGitHub.calls if c["path"].endswith("/issues")]
        check("라벨 거부 시 라벨 없이 재시도", data.get("mode") == "api" and len(issues) == 3
              and "labels" not in issues[-1]["payload"], str(len(issues)))
        MockGitHub.reject_labels = False
    finally:
        save_config({"github_token": ""})
        srv.shutdown()

    print("== 4. 자동 수신 매칭 · 복사 ==")
    ib.ggit = None  # noqa  (실수 방지용 표시)
    ib.is_git_repo = lambda: True                     # .git 없이 매칭 로직만 확인
    ib.git_pull = lambda timeout=120: {"ok": True, "reason": "up_to_date", "message": "Already up to date."}
    inbox_dir = app_root / "assets_inbox" / pid
    inbox_dir.mkdir(parents=True, exist_ok=True)
    png = bytes.fromhex("89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
                        "0000000a49444154789c6300010000050001")
    (inbox_dir / "s1.png").write_bytes(png)            # s01.png 로 맞춰져야 한다
    (inbox_dir / "s02.PNG").write_bytes(png + b"2")     # 대소문자 무시
    (inbox_dir / "memo.txt").write_text("not an image", encoding="utf-8")

    res = ib.receive_once("test")
    images = sorted(x.name for x in (project_dir(pid) / "images").glob("*"))
    check("s1.png → s01.png 로 복사", "s01.png" in images, str(images))
    check("s02.PNG → s02.png 로 복사", "s02.png" in images, str(images))
    check("이미지 아닌 파일은 무시", "memo.txt" not in images)
    check("결과 요약에 수신 2장", sum(e["count"] for e in res.get("received", [])) == 2, str(res)[:300])
    p2 = load(pid)
    check("진행 상태에 수신 문구", ib.RECEIVE_MSG in str(p2.get("status", {}).get("message", "")),
          str(p2.get("status")))
    check("project.json 수신 기록", bool(p2.get("receive_log")))
    check("상태 파일에 이벤트 기록", ib.load_state().get("seq", 0) == 1, str(ib.load_state().get("seq")))
    check("수신 로그 파일", (app_root / "logs" / "inbox.log").exists())

    # 두 번째 실행: 같은 파일이면 새로 복사하지 않는다
    res2 = ib.receive_once("test")
    check("같은 이미지는 다시 복사하지 않음", res2.get("received") == [], str(res2)[:300])

    # 폴더 이름이 프로젝트 id 가 아니어도 파일 이름으로 매칭
    odd = app_root / "assets_inbox" / "케빈이보낸폴더"
    odd.mkdir(exist_ok=True)
    (odd / "s03.png").write_bytes(png + b"3")
    res3 = ib.receive_once("test")
    check("애매한 폴더도 파일 이름으로 매칭", any(e["project_id"] == pid for e in res3.get("received", [])),
          str(res3)[:300])
    check("s03.png 복사", (project_dir(pid) / "images" / "s03.png").exists())

    # 완성된 사연도 폴더 이름이 정확하면 새 이미지를 다시 받는다
    from app.project import set_status  # noqa: E402
    p3 = load(pid)
    set_status(p3, "done", 100, "완성")
    (inbox_dir / "s05.png").write_bytes(png + b"5")
    res_done = ib.receive_once("test")
    check("완성된 사연도 폴더명으로 재수신", any(e["project_id"] == pid for e in res_done.get("received", [])),
          str(res_done)[:200])
    check("완성 상태는 덮어쓰지 않음", load(pid).get("status", {}).get("stage") == "done")
    check("재수신도 기록은 남김", bool(load(pid).get("receive_log")))

    orphan = app_root / "assets_inbox" / "unknown-folder"
    orphan.mkdir(parents=True, exist_ok=True)
    (orphan / "s99.png").write_bytes(png + b"9")
    res_orphan = ib.receive_once("test")
    check("매칭 안 되는 폴더는 안내 문구", "찾지 못했습니다" in res_orphan.get("message", ""),
          res_orphan.get("message", ""))

    print("== 5. git pull 실패는 경고만 남기고 서버를 죽이지 않는다 ==")
    ib.git_pull = lambda timeout=120: {"ok": False, "reason": "pull_failed",
                                       "message": "fatal: Not possible to fast-forward, aborting."}
    res4 = ib.receive_once("test")
    check("pull 실패 → 예외 없이 ok False", res4.get("ok") is False, str(res4)[:200])
    check("pull 실패 → 경고 메시지", "실패" in res4.get("message", ""), res4.get("message", ""))
    check("pull 실패 → 상태에 기록", ib.load_state().get("last_ok") is False)

    print("== 6. 진짜 git 원격에서 pull → 자동 복사 ==")
    remote = WORK / "remote.git"
    pusher = WORK / "pusher"
    run(["git", "init", "--bare", "-b", "main", str(remote)], WORK)
    run(["git", "init", "-b", "main"], app_root)
    run(["git", "config", "user.email", "t@example.com"], app_root)
    run(["git", "config", "user.name", "tester"], app_root)
    (app_root / ".gitignore").write_text("config/\nprojects/\nlogs/\n.cache/\n__pycache__/\n",
                                         encoding="utf-8")
    run(["git", "add", "-A"], app_root)
    run(["git", "commit", "-m", "init"], app_root)
    run(["git", "remote", "add", "origin", str(remote)], app_root)
    run(["git", "push", "-u", "origin", "main"], app_root)
    run(["git", "clone", str(remote), str(pusher)], WORK)
    run(["git", "config", "user.email", "k@example.com"], pusher)
    run(["git", "config", "user.name", "kevin"], pusher)
    (pusher / "assets_inbox" / pid).mkdir(parents=True, exist_ok=True)
    (pusher / "assets_inbox" / pid / "s04.png").write_bytes(png + b"4")
    run(["git", "add", "-A"], pusher)
    run(["git", "commit", "-m", "images"], pusher)
    run(["git", "push", "origin", "main"], pusher)

    import importlib
    importlib.reload(ib)          # 위에서 monkeypatch 한 is_git_repo/git_pull 되돌리기
    importlib.reload(ib)          # (settings/github 모듈 상태도 함께 새로 읽는다)
    res5 = ib.receive_once("test")
    check("실제 git pull 성공", res5.get("ok") is True and res5.get("git", {}).get("reason") == "updated",
          str(res5.get("git"))[:300])
    check("실제 pull 로 받은 s04.png 복사", (project_dir(pid) / "images" / "s04.png").exists(),
          str(sorted(x.name for x in (project_dir(pid) / "images").glob('*'))))
    check("받은 이미지 문구", ib.RECEIVE_MSG in res5.get("message", ""), res5.get("message", ""))

    print("== 7. 워커 시작/정지 ==")
    sch.save_settings({"auto_receive": True})
    ib.start_worker()
    time.sleep(0.4)
    check("워커 살아 있음", ib.worker_alive() is True)
    ib.stop_worker()
    time.sleep(0.3)
    check("워커 정지", ib.worker_alive() is False)

    print("== 8. 업로드 매칭 함수 (기존 기능 회귀) ==")
    from app.project import match_plan_name
    check("s1.png → s01.png", match_plan_name("s1.png", {"s01.png"}) == "s01.png")
    check("알 수 없는 이름은 None", match_plan_name("zzz.png", {"s01.png"}) is None)

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
