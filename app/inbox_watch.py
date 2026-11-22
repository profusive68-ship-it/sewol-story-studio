"""assets_inbox 자동 수신 — 깃허브에 케빈이 올린 이미지를 20초마다 받아 프로젝트에 넣는다.

v2.0.0 무중단 수신
  · 1순위 `git pull --ff-only` (정상일 때 가장 빠름)
  · pull 이 로컬 파일 충돌로 실패하면 → `git fetch origin main` 뒤
    **`git checkout origin/main -- assets_inbox`** 로 이미지 폴더만 새로 받는다.
    `projects/`·`config/` 는 절대 건드리지 않는다(작업 중인 사연·키 보존).
  · 그것도 실패하면 → GitHub Contents API 로 `assets_inbox/{pid}` 의 파일을 직접 내려받는다.
    (git 이 아예 망가졌거나 네트워크가 git 만 막는 경우의 마지막 길)
  · 어느 길로 받았는지(`route`)와 마지막 오류(`last_error`)를 상태에 남겨 2단계 타임라인에 보여 준다.

`assets_inbox/{project_id}/` 의 이미지를 `projects/{project_id}/images/` 로 복사한다.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import threading
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any

from . import scheduler as sch
from .paths import BASE, CONFIG_DIR, LOG_DIR, project_dir
from .settings import DEFAULT_GITHUB_REPO, load_config

INBOX = BASE / "assets_inbox"
INBOX_NAME = "assets_inbox"
STATE_PATH = CONFIG_DIR / "inbox_state.json"
POLL_SECONDS = 20
IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".webp")
RECEIVE_MSG = "🎉 케빈이 올린 이미지 자동 수신 완료!"
API_BASE = "https://api.github.com"
USER_AGENT = "sewol-story-studio"
MAX_API_FILES = 200          # 한 번에 내려받는 최대 파일 수(폭주 방지)

_RUN_LOCK = threading.Lock()
_GIT_LOCK = threading.Lock()


# ── 로그·상태 ─────────────────────────────────────────────────────────────
def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _log(msg: str) -> None:
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        with open(LOG_DIR / "inbox.log", "a", encoding="utf-8") as f:
            f.write(f"[{_now()}] {msg}\n")
    except Exception:
        pass


def load_state() -> dict:
    if STATE_PATH.exists():
        try:
            data = json.loads(STATE_PATH.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
        except Exception:
            pass
    return {}


def save_state(**kw) -> dict:
    data = load_state()
    data.update(kw)
    data["updated"] = _now()
    try:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        STATE_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass
    return data


def settings() -> dict:
    try:
        return sch.load_settings()
    except Exception:
        return {}


def is_enabled() -> bool:
    return bool(settings().get("auto_receive", True))


def is_git_repo() -> bool:
    return (BASE / ".git").exists()


def repo_name() -> str:
    try:
        repo = (load_config().get("github_repo") or "").strip()
    except Exception:
        repo = ""
    return repo or DEFAULT_GITHUB_REPO


def token() -> str:
    try:
        return (load_config().get("github_token") or "").strip()
    except Exception:
        return ""


# ── git ──────────────────────────────────────────────────────────────────
def _git(args: list[str], timeout: int = 120) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(BASE)] + args, capture_output=True,
                          text=True, timeout=timeout)


def git_pull(timeout: int = 120) -> dict[str, Any]:
    """`git pull --ff-only` — 실패해도 예외를 올리지 않고 결과만 돌려준다."""
    if not is_git_repo():
        return {"ok": False, "reason": "not_git",
                "message": "이 폴더는 깃허브 저장소가 아닙니다. README 의 [설치]를 참고해 git clone 으로 받아 주세요."}
    with _GIT_LOCK:              # 20초 워커·[최신 버전 받기] 버튼이 동시에 pull 하지 않게
        try:
            r = subprocess.run(["git", "-C", str(BASE), "pull", "--ff-only"],
                               capture_output=True, text=True, timeout=timeout)
        except Exception as e:
            return {"ok": False, "reason": "error", "message": f"git pull 실행 실패: {str(e)[:200]}"}
    out = ((r.stdout or "") + (r.stderr or "")).strip()
    if r.returncode != 0:
        return {"ok": False, "reason": "pull_failed", "message": out[-600:] or f"git pull 종료 코드 {r.returncode}"}
    changed = "Already up to date" not in out and "최신 상태" not in out
    return {"ok": True, "reason": "up_to_date" if not changed else "updated", "message": out[-600:]}


def scoped_inbox_sync(timeout: int = 120) -> dict[str, Any]:
    """pull 이 실패했을 때 — `assets_inbox/` 만 원격에서 새로 가져온다.

    `git fetch origin main` → `git checkout origin/main -- assets_inbox`
    · projects/ · config/ · assets/ 는 pathspec 에 넣지 않으므로 절대 바뀌지 않는다.
    """
    if not is_git_repo():
        return {"ok": False, "reason": "not_git", "message": "이 폴더는 깃허브 저장소가 아닙니다."}
    out: list[str] = []
    with _GIT_LOCK:
        try:
            f = _git(["fetch", "origin", "main", "--prune"], timeout)
            out.append(((f.stdout or "") + (f.stderr or "")).strip()[-300:])
            if f.returncode != 0:
                return {"ok": False, "reason": "fetch_failed",
                        "message": "git fetch 실패 — " + (out[-1] or f"종료 코드 {f.returncode}")}
            # 이미지 폴더만 원격 기준으로 맞춘다(추적 파일 충돌을 덮어써 해소).
            c = _git(["checkout", "origin/main", "--", INBOX_NAME], timeout)
            out.append(((c.stdout or "") + (c.stderr or "")).strip()[-300:])
            if c.returncode != 0:
                return {"ok": False, "reason": "checkout_failed",
                        "message": "assets_inbox 만 받아오기 실패 — " + (out[-1] or f"종료 코드 {c.returncode}"),
                        "detail": "\n".join(x for x in out if x)[-600:]}
        except Exception as e:
            return {"ok": False, "reason": "error", "message": f"이미지 폴더만 받기 실패: {str(e)[:200]}"}
    return {"ok": True, "reason": "scoped_checkout",
            "message": "git pull 충돌 → assets_inbox 폴더만 새로 받았습니다. (projects·config 는 그대로)",
            "detail": "\n".join(x for x in out if x)[-600:]}


# ── GitHub Contents API 폴백 ─────────────────────────────────────────────
def _api_headers() -> dict:
    h = {"Accept": "application/vnd.github+json", "User-Agent": USER_AGENT}
    tok = token()
    if tok:
        h["Authorization"] = "Bearer " + tok
    return h


def _api_json(url: str, timeout: int = 40) -> Any:
    req = urllib.request.Request(url, headers=_api_headers(), method="GET")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read()
    return json.loads(raw.decode("utf-8", "replace") or "null")


def _api_download(url: str, timeout: int = 60) -> bytes:
    """raw.githubusercontent / download_url 에서 파일 바이트를 받는다(토큰은 붙이지 않는다)."""
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT}, method="GET")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def api_list_folder(folder: str = "", timeout: int = 40) -> list[dict]:
    """`assets_inbox/{folder}` 의 파일 목록(디렉터리면 재귀)."""
    repo = repo_name()
    path = INBOX_NAME + (("/" + folder.strip("/")) if folder else "")
    url = f"{API_BASE}/repos/{repo}/contents/{urllib.parse.quote(path)}?ref=main"
    data = _api_json(url, timeout)
    items = data if isinstance(data, list) else [data]
    out: list[dict] = []
    for it in items:
        if not isinstance(it, dict):
            continue
        if it.get("type") == "file" and str(it.get("name", "")).lower().endswith(IMAGE_EXTS):
            out.append(it)
        elif it.get("type") == "dir":
            out.extend(api_list_folder(f"{folder.strip('/')}/{it.get('name')}".strip("/"), timeout))
    return out


def api_fetch_inbox(projects: list[str] | None = None, timeout: int = 40) -> dict[str, Any]:
    """GitHub Contents API 로 assets_inbox 의 이미지 파일을 직접 내려받는다.

    · 토큰이 있으면 비공개 저장소도 받는다. 없으면 공개 저장소만.
    · 받은 파일은 로컬 `assets_inbox/{폴더}/` 에 저장한다(이후 복사 단계는 동일).
    """
    folders = [p for p in (projects or []) if p]
    if not folders:
        try:
            top = _api_json(f"{API_BASE}/repos/{repo_name()}/contents/{INBOX_NAME}?ref=main", timeout)
        except urllib.error.HTTPError as e:
            return {"ok": False, "reason": "api_http", "status": int(e.code),
                    "message": _api_error(e, "assets_inbox 목록")}
        except Exception as e:
            return {"ok": False, "reason": "api_error",
                    "message": f"GitHub API 연결 실패 — {str(e)[:200]}"}
        items = top if isinstance(top, list) else []
        folders = [str(i.get("name")) for i in items if isinstance(i, dict) and i.get("type") == "dir"]

    saved: list[str] = []
    errors: list[str] = []
    for folder in folders:
        try:
            files = api_list_folder(folder, timeout)
        except urllib.error.HTTPError as e:
            if int(e.code) != 404:
                errors.append(f"{folder}: {_api_error(e, '파일 목록')}")
            continue
        except Exception as e:
            errors.append(f"{folder}: {str(e)[:120]}")
            continue
        dest_dir = INBOX / folder
        dest_dir.mkdir(parents=True, exist_ok=True)
        for it in files[:MAX_API_FILES]:
            name = str(it.get("name") or "")
            url = it.get("download_url") or ""
            if not name or not url:
                continue
            dest = dest_dir / name
            try:
                data = _api_download(str(url), timeout)
                if len(data) < 50:
                    continue
                if dest.exists() and dest.read_bytes() == data:
                    continue
                dest.write_bytes(data)
                saved.append(f"{folder}/{name}")
            except Exception as e:
                errors.append(f"{folder}/{name}: {str(e)[:100]}")
    return {"ok": not errors or bool(saved), "reason": "api",
            "message": (f"GitHub API 로 이미지 {len(saved)}장을 받았습니다." if saved
                        else ("GitHub API 로 받을 새 이미지가 없습니다." if not errors
                              else "GitHub API 수신 실패 — " + "; ".join(errors[:2]))),
            "files": saved[:200], "errors": errors[:5]}


def _api_error(e: urllib.error.HTTPError, what: str) -> str:
    if int(getattr(e, "code", 0)) == 404:
        return f"{what} 없음(404) — 저장소 이름·폴더·토큰 권한을 확인해 주세요."
    if int(getattr(e, "code", 0)) in (401, 403):
        return f"{what} 권한 없음({e.code}) — 깃허브 토큰을 저장하면 비공개 저장소도 받을 수 있습니다."
    return f"{what} 실패(HTTP {getattr(e, 'code', '?')})"


# ── 매칭 ─────────────────────────────────────────────────────────────────
def _images_in(folder: Path) -> list[Path]:
    if not folder.exists():
        return []
    try:
        return sorted(p for p in folder.rglob("*") if p.is_file() and p.suffix.lower() in IMAGE_EXTS)
    except Exception:
        return []


def waiting_projects() -> list[dict]:
    """이미지가 덜 모인 프로젝트 (수신 대기 후보)."""
    from .project import list_projects, load, missing_images
    out = []
    for item in list_projects():
        pid = item.get("id")
        if not pid:
            continue
        try:
            p = load(pid)
        except Exception:
            continue
        plan = p.get("image_plan") or []
        if not plan:
            continue
        if p.get("status", {}).get("stage") == "done":
            continue
        if missing_images(p):
            out.append(p)
    return out


def known_project_ids() -> set[str]:
    """지우지 않은 모든 프로젝트 id (완성된 사연의 이미지를 다시 받을 때도 쓴다)."""
    from .project import list_projects
    try:
        return {str(i.get("id")) for i in list_projects() if i.get("id")}
    except Exception:
        return set()


def match_folder(name: str, files: list[Path], projects: list[dict],
                 known_ids: set[str] | None = None) -> str | None:
    """폴더 이름 → 프로젝트 id. 폴더명이 애매하면 안에 든 파일 이름으로 맞춘다."""
    from .project import match_plan_name
    name = " ".join((name or "").split())
    ids = known_ids or {str(p.get("id")) for p in projects}
    if name in ids:
        return name
    if name:
        hit = [pid for pid in ids if pid.lower() in name.lower()]
        if len(hit) == 1:
            return hit[0]
    scored: dict[str, int] = {}
    for p in projects:
        plan = {str(e.get("file")) for e in (p.get("image_plan") or [])}
        n = 0
        for f in files:
            if match_plan_name(f.name, plan):
                n += 1
        if n:
            scored[str(p["id"])] = n
    if not scored:
        return None
    best = max(scored.values())
    winners = [pid for pid, n in scored.items() if n == best]
    return winners[0] if len(winners) == 1 else None


def _digest(path: Path) -> str:
    h = hashlib.sha1()
    h.update(path.read_bytes())
    return h.hexdigest()


def copy_images(pid: str, files: list[Path]) -> list[str]:
    """요청서 파일명에 맞는 이미지만 프로젝트 images/ 로 복사한다. 새로/바뀐 것만 돌려준다."""
    from .project import load, match_plan_name
    try:
        p = load(pid)
    except Exception:
        return []
    plan = {str(e.get("file")) for e in (p.get("image_plan") or [])}
    if not plan:
        return []
    dest = project_dir(pid) / "images"
    dest.mkdir(parents=True, exist_ok=True)
    saved: list[str] = []
    for f in files:
        target = match_plan_name(f.name, plan)
        if not target:
            continue
        out = dest / target
        try:
            if out.exists() and _digest(out) == _digest(f):
                continue
            out.write_bytes(f.read_bytes())
            saved.append(target)
        except Exception as e:
            _log(f"이미지 복사 실패 {pid}/{target}: {str(e)[:120]}")
    return saved


def _mark_received(pid: str, folder: str, files: list[str]) -> dict:
    """프로젝트 진행 상태를 갱신하고 수신 기록을 남긴다."""
    from .project import load, save, set_status, missing_images
    try:
        p = load(pid)
    except Exception:
        return {}
    missing = missing_images(p)
    msg = f"{RECEIVE_MSG} ({len(files)}장 도착 · 남은 {len(missing)}장)"
    if (p.get("status") or {}).get("stage") != "done":
        pct = int((p.get("status") or {}).get("percent") or 0)
        set_status(p, "images", max(pct, 2), msg)
    log = p.setdefault("receive_log", [])
    log.append({"time": _now(), "folder": folder, "files": files[:80],
                "received": len(files), "missing": len(missing), "message": RECEIVE_MSG})
    p["receive_log"] = log[-20:]
    save(p)
    return {"missing": missing, "percent": (p.get("status") or {}).get("percent", 0)}


def _maybe_assemble(pid: str) -> bool:
    """설정이 켜져 있고 이미지가 다 모였으면 자동 조립을 시작한다."""
    if not settings().get("auto_assemble_on_receive"):
        return False
    from .project import load, missing_images
    try:
        if missing_images(load(pid)):
            return False
        from .main import assemble_project, start_job
        start_job("assemble", lambda progress: assemble_project(pid, progress), project_id=pid)
        _log(f"이미지가 모두 모여 자동 조립을 시작합니다: {pid}")
        return True
    except Exception as e:
        _log(f"자동 조립 시작 실패 {pid}: {str(e)[:150]}")
        return False


# ── 한 번 확인 ────────────────────────────────────────────────────────────
def receive_once(trigger: str = "auto") -> dict:
    """이미지 받기 → assets_inbox 스캔 → 프로젝트로 복사. 결과 요약을 돌려준다."""
    if not _RUN_LOCK.acquire(blocking=False):
        return {"ok": True, "busy": True, "message": "이미 확인 중입니다.",
                "received": [], "checked_at": _now(), "trigger": trigger}
    try:
        result: dict[str, Any] = {"ok": True, "trigger": trigger, "checked_at": _now(),
                                  "received": [], "route": "", "last_error": "",
                                  "pulledat": None}
        if not is_git_repo():
            result.update(ok=False, route="none",
                          message="이 폴더는 깃허브 저장소가 아닙니다. (git clone 으로 설치하면 자동 수신이 켜집니다)")
            save_state(last_check=_now(), last_ok=False, last_route="none",
                       last_message=result["message"], last_error=result["message"])
            return result

        pull = git_pull()
        result["git"] = pull
        result["pulledat"] = pull.get("reason")
        route = "pull"
        if not pull["ok"]:
            # 자동 수신은 이미지 폴더만 받아오면 되므로 한 번 더 시도한다.
            scoped = scoped_inbox_sync()
            result["scoped"] = scoped
            if scoped.get("ok"):
                route = "scoped_checkout"
                _log("git pull 실패 → assets_inbox 만 새로 받았습니다: "
                     + str(pull.get("message") or "")[:160])
            else:
                projects = [str(p.get("id")) for p in waiting_projects()]
                api = api_fetch_inbox(projects)
                result["api"] = api
                if api.get("ok"):
                    route = "api"
                    _log("git 실패 → GitHub API 로 이미지를 받았습니다: " + str(api.get("message"))[:160])
                else:
                    route = "failed"
                    result["route"] = "failed"
                    result["ok"] = False
                    result["last_error"] = " / ".join(
                        x for x in (pull.get("message"), scoped.get("message"), api.get("message")) if x)[:600]
                    result["message"] = "이미지 수신 실패 — " + result["last_error"]
                    if load_state().get("last_message") != result["message"]:
                        _log(f"자동 수신 실패: {result['last_error'][:300]}")
                    save_state(last_check=_now(), last_ok=False, last_route="failed",
                               last_message=result["message"][:400],
                               last_error=result["last_error"],
                               last_failed=_now())
                    return result
        result["route"] = route

        projects = waiting_projects()
        known = known_project_ids()
        cands: list[tuple[str, str, list[Path]]] = []
        if INBOX.exists():
            for d in sorted(INBOX.iterdir()):
                if d.is_dir() and not d.name.startswith("."):
                    files = _images_in(d)
                    if files:
                        cands.append((d.name, str(d), files))
            loose = [p for p in INBOX.iterdir() if p.is_file() and p.suffix.lower() in IMAGE_EXTS]
            if loose:
                cands.append(("", str(INBOX), sorted(loose)))

        events: list[dict] = []
        for folder_name, folder_path, files in cands:
            pid = match_folder(folder_name, files, projects, known)
            if not pid:
                result.setdefault("unmatched", []).append(folder_name or "(기본 폴더)")
                continue
            saved = copy_images(pid, files)
            if not saved:
                continue
            info = _mark_received(pid, folder_name or "(기본 폴더)", saved)
            event = {"time": _now(), "project_id": pid, "folder": folder_name,
                     "files": saved[:80], "count": len(saved),
                     "missing": len(info.get("missing") or []), "message": RECEIVE_MSG,
                     "route": route}
            events.append(event)
            result["received"].append(event)
            _log(f"{RECEIVE_MSG} project={pid} folder={folder_name or '(root)'} {len(saved)}장 "
                 f"남은 {event['missing']}장 (경로 {route})")
            if not info.get("missing"):
                result.setdefault("auto_assemble", []).append({"project_id": pid,
                                                               "started": _maybe_assemble(pid)})

        if events:
            msg = f"{RECEIVE_MSG} ({sum(e['count'] for e in events)}장)"
            result["message"] = msg
        elif result.get("unmatched"):
            msg = ("이미지는 왔지만 넣을 사연을 찾지 못했습니다: "
                   + ", ".join(result["unmatched"][:3])
                   + " — 폴더 이름을 사연 번호로 맞춰 주세요.")
            result["message"] = msg
        elif route == "scoped_checkout":
            msg = "assets_inbox만 새로 받았습니다. (넣을 새 이미지는 없음)"
            result["message"] = msg
        elif route == "api":
            msg = str((result.get("api") or {}).get("message") or "GitHub API 확인 완료")
            result["message"] = msg
        elif pull.get("reason") == "updated":
            msg = "깃허브에서 새 파일을 받았습니다. (넣을 이미지는 없음)"
            result["message"] = msg
        else:
            msg = "새 이미지 없음 · 최신 상태"
            result["message"] = msg
        result["ok"] = True

        state = load_state()
        old_events = list(state.get("events") or [])
        if events:
            old_events.extend(events)
        save_state(last_check=_now(), last_ok=True, last_message=result["message"][:400],
                   last_route=route, last_error="", last_pull=pull.get("reason"),
                   last_git=(pull.get("message") or "")[:400],
                   received_files=_received_map(),
                   events=old_events[-30:], seq=int(state.get("seq") or 0) + (1 if events else 0))
        return result
    except Exception as e:
        _log(f"자동 수신 중 예외(무시): {str(e)[:200]}")
        save_state(last_check=_now(), last_ok=False, last_route="error",
                   last_message=f"자동 수신 오류: {str(e)[:200]}",
                   last_error=f"{type(e).__name__}: {str(e)[:200]}")
        return {"ok": False, "message": f"자동 수신 오류: {str(e)[:200]}", "received": [],
                "route": "error", "last_error": str(e)[:200],
                "checked_at": _now(), "trigger": trigger}
    finally:
        _RUN_LOCK.release()


def _received_map() -> dict[str, list[str]]:
    """폴더(사연 번호)별로 로컬 assets_inbox 에 있는 이미지 파일 이름."""
    out: dict[str, list[str]] = {}
    if not INBOX.exists():
        return out
    try:
        for d in sorted(INBOX.iterdir()):
            if d.is_dir() and not d.name.startswith("."):
                files = [p.name for p in _images_in(d)]
                if files:
                    out[d.name] = files[:200]
    except Exception:
        pass
    return out


def status() -> dict:
    s = settings()
    st = load_state()
    return {
        "enabled": bool(s.get("auto_receive", True)),
        "auto_assemble": bool(s.get("auto_assemble_on_receive", False)),
        "is_git": is_git_repo(),
        "worker": worker_alive(),
        "poll_seconds": POLL_SECONDS,
        "inbox": str(INBOX),
        "last_check": st.get("last_check", ""),
        "last_ok": st.get("last_ok"),
        "last_message": st.get("last_message", ""),
        "last_error": st.get("last_error", ""),
        "last_route": st.get("last_route", ""),
        "received_files": st.get("received_files") or {},
        "events": list(st.get("events") or [])[-8:],
        "seq": int(st.get("seq") or 0),
        "message": RECEIVE_MSG,
    }


def project_progress(pid: str) -> dict:
    """2단계 타임라인이 읽는 '이 사연'의 이미지 수신 현황."""
    from .project import load, missing_images
    try:
        p = load(pid)
    except Exception:
        return {"ok": False, "error": "사연을 찾을 수 없습니다."}
    plan = [str(e.get("file")) for e in (p.get("image_plan") or [])]
    missing = missing_images(p)
    st = load_state()
    files = _images_in(INBOX / pid)
    events = [e for e in (st.get("events") or []) if str(e.get("project_id")) == pid]
    last = events[-1] if events else {}
    return {
        "ok": True, "project_id": pid,
        "total": len(plan), "received": len(plan) - len(missing),
        "missing": missing,
        "remaining": len(missing),
        "inbox_files": [f.name for f in files][:80],
        "last_check": st.get("last_check", ""),
        "route": st.get("last_route", ""),
        "last_message": st.get("last_message", ""),
        "last_error": st.get("last_error", ""),
        "last_event": last,
        "events": events[-6:],
    }


# ── 백그라운드 워커 ────────────────────────────────────────────────────────
class Worker(threading.Thread):
    daemon = True

    def __init__(self) -> None:
        super().__init__(name="sewol-inbox")
        self._stop = threading.Event()

    def run(self) -> None:
        self._stop.wait(6)          # 서버가 뜨자마자 몰리지 않게 잠깐 대기
        while not self._stop.is_set():
            try:
                if is_enabled():
                    receive_once("auto")
            except Exception as e:      # 어떤 경우에도 워커는 죽지 않는다
                _log(f"자동 수신 워커 오류(무시): {str(e)[:200]}")
            self._stop.wait(POLL_SECONDS)

    def stop(self) -> None:
        self._stop.set()


_worker: Worker | None = None


def start_worker() -> None:
    global _worker
    if _worker is None or not _worker.is_alive():
        _worker = Worker()
        _worker.start()


def worker_alive() -> bool:
    return bool(_worker and _worker.is_alive())


def stop_worker() -> None:
    global _worker
    if _worker:
        _worker.stop()
        _worker = None
