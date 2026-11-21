"""assets_inbox 자동 수신 — 깃허브에 케빈이 올린 이미지를 20초마다 받아 프로젝트에 넣는다.

· `.git` 폴더가 있을 때만 `git pull --ff-only` 로 원격 변경을 확인한다.
· pull 이 실패해도 예외로 서버가 죽지 않고 경고 로그만 남긴다.
· assets_inbox/{project_id}/ 의 이미지를 projects/{project_id}/images/ 로 복사한다.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

from . import scheduler as sch
from .paths import BASE, CONFIG_DIR, LOG_DIR, project_dir

INBOX = BASE / "assets_inbox"
STATE_PATH = CONFIG_DIR / "inbox_state.json"
POLL_SECONDS = 20
IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".webp")
RECEIVE_MSG = "🎉 케빈이 올린 이미지 자동 수신 완료!"

_RUN_LOCK = threading.Lock()


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


# ── git ──────────────────────────────────────────────────────────────────
def git_pull(timeout: int = 120) -> dict[str, Any]:
    """`git pull --ff-only` — 실패해도 예외를 올리지 않고 결과만 돌려준다."""
    if not is_git_repo():
        return {"ok": False, "reason": "not_git",
                "message": "이 폴더는 깃허브 저장소가 아닙니다. README 의 [설치]를 참고해 git clone 으로 받아 주세요."}
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
    """깃허브에서 pull → assets_inbox 스캔 → 프로젝트로 복사. 결과 요약을 돌려준다."""
    if not _RUN_LOCK.acquire(blocking=False):
        return {"ok": True, "busy": True, "message": "이미 확인 중입니다.",
                "received": [], "checked_at": _now(), "trigger": trigger}
    try:
        result: dict[str, Any] = {"ok": True, "trigger": trigger, "checked_at": _now(),
                                  "received": [], "pulledat": None}
        if not is_git_repo():
            result.update(ok=False, message="이 폴더는 깃허브 저장소가 아닙니다. (git clone 으로 설치하면 자동 수신이 켜집니다)")
            save_state(last_check=_now(), last_ok=False, last_message=result["message"])
            return result

        pull = git_pull()
        result["git"] = pull
        result["pulledat"] = pull.get("reason")
        prev = load_state()
        if not pull["ok"]:
            result["ok"] = False
            result["message"] = "깃허브 확인 실패 — " + (pull["message"] or "알 수 없는 이유")
            if prev.get("last_message") != result["message"]:
                _log(f"git pull 실패(무시하고 계속): {result['message'][:300]}")
            save_state(last_check=_now(), last_ok=False, last_message=result["message"][:400],
                       last_failed=_now())
            return result

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
                     "missing": len(info.get("missing") or []), "message": RECEIVE_MSG}
            events.append(event)
            result["received"].append(event)
            _log(f"{RECEIVE_MSG} project={pid} folder={folder_name or '(root)'} {len(saved)}장 "
                 f"남은 {event['missing']}장")
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
                   last_pull=pull.get("reason"), last_git=(pull.get("message") or "")[:400],
                   events=old_events[-30:], seq=int(state.get("seq") or 0) + (1 if events else 0))
        return result
    except Exception as e:
        _log(f"자동 수신 중 예외(무시): {str(e)[:200]}")
        save_state(last_check=_now(), last_ok=False, last_message=f"자동 수신 오류: {str(e)[:200]}")
        return {"ok": False, "message": f"자동 수신 오류: {str(e)[:200]}", "received": [],
                "checked_at": _now(), "trigger": trigger}
    finally:
        _RUN_LOCK.release()


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
        "events": list(st.get("events") or [])[-8:],
        "seq": int(st.get("seq") or 0),
        "message": RECEIVE_MSG,
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
