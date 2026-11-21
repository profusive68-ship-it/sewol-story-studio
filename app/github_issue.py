"""깃허브 이미지 요청 — 토큰이 있으면 이슈를 바로 등록하고, 없으면 1클릭 등록 화면을 연다."""
from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime

from .settings import DEFAULT_GITHUB_REPO, load_config

API_BASE = "https://api.github.com"
LABEL = "image-request"
LABEL_COLOR = "c9a227"
LABEL_DESC = "케빈 이미지 요청 (대시보드 자동 등록)"
USER_AGENT = "sewol-story-studio"

MAX_BODY_CHARS = 60000      # GitHub 이슈 본문 한도(65,536자)보다 조금 아래
MAX_URL_CHARS = 5600        # github.com 이 약 6,000자를 넘기면 414/500 으로 막는다


class GitHubError(RuntimeError):
    """깃허브 API 호출 실패."""


# ── 설정 ──────────────────────────────────────────────────────────────────
def repo_name() -> str:
    try:
        repo = (load_config().get("github_repo") or "").strip()
    except Exception:
        repo = ""
    return repo or DEFAULT_GITHUB_REPO


def token() -> str:
    """config/config.json 우선, 없으면 config/settings.json 의 github_token."""
    try:
        tok = (load_config().get("github_token") or "").strip()
    except Exception:
        tok = ""
    if tok:
        return tok
    try:
        from . import scheduler as sch
        return (sch.load_settings().get("github_token") or "").strip()
    except Exception:
        return ""


# ── 이슈 제목·본문 ────────────────────────────────────────────────────────
def _topic(project: dict) -> str:
    topic = ((project.get("options") or {}).get("topic") or "").strip()
    if not topic:
        topic = (project.get("title") or "").strip()
    return " ".join(topic.split())


def issue_title(project: dict) -> str:
    pid = str(project.get("id") or "")
    topic = _topic(project)[:70]
    return f"[이미지요청] {pid} - {topic}" if topic else f"[이미지요청] {pid}"


def _fmt_line(project: dict) -> str:
    fmt = project.get("format") or {}
    bits = [str(fmt.get("label") or "").strip()]
    if fmt.get("aspect"):
        bits.append(str(fmt["aspect"]))
    if fmt.get("width") and fmt.get("height"):
        bits.append(f"{fmt['width']}×{fmt['height']}")
    return " · ".join(b for b in bits if b)


def issue_body(project: dict, request_text: str = "") -> str:
    pid = str(project.get("id") or "")
    inbox = f"assets_inbox/{pid}"
    n = len(project.get("image_plan") or [])
    head = [
        "## 🖼 세월의 사연극장 이미지 요청",
        "",
        "이 이슈는 맥북 대시보드의 **[📤 케빈에게 이미지 요청하기]** 버튼이 등록했습니다.",
        "",
        "| 항목 | 값 |",
        "| --- | --- |",
        f"| project_id | `{pid}` |",
        f"| target_inbox | `{inbox}` |",
        f"| label | `{LABEL}` |",
        f"| 형식 | {_fmt_line(project) or '-'} |",
        f"| 요청 장수 | {n}장 |",
        "| 파일명 규칙 | s01.png, s02.png … (요청서 파일명 그대로) |",
        f"| 등록 시각 | {datetime.now():%Y-%m-%d %H:%M} |",
        "",
        f"> 케빈: 이미지를 만들어 위 `target_inbox` 폴더에 **파일명 그대로** 올리고 이 이슈를 닫아 주세요.",
        f"> 맥북 대시보드가 20초마다 `git pull` 로 확인해 `projects/{pid}/images/` 로 자동 복사합니다.",
        "> 파일 이름이 다르면 인식되지 않습니다.",
        "",
        "---",
        "",
    ]
    text = (request_text or "").strip()
    if len(text) > MAX_BODY_CHARS:
        text = text[:MAX_BODY_CHARS] + "\n… (본문 한도로 줄였습니다. 전체 요청서는 맥북 프로젝트 폴더에 있습니다)"
    return "\n".join(head) + "```text\n" + text + "\n```\n"


def compact_body(project: dict, prompt_chars: int = 200, caption_chars: int = 30) -> str:
    """URL 로 넘길 수 있는 짧은 본문 — 파일명·장면·프롬프트만 남긴다."""
    pid = str(project.get("id") or "")
    plan = project.get("image_plan") or []
    lines = [
        f"project_id: {pid}",
        f"target_inbox: assets_inbox/{pid}",
        f"label: {LABEL}",
        f"format: {_fmt_line(project)} · {len(plan)}장",
    ]
    topic = _topic(project)
    if topic:
        lines.append(f"topic: {topic[:120]}")
    chars = (project.get("characters") or [])
    if chars:
        lines.append("")
        lines.append("[인물 — 모든 이미지에 같은 얼굴]")
        for c in chars[:6]:
            lines.append(f"· {str(c.get('name') or '')[:20]}: {str(c.get('desc_en') or '')[:160]}")
    lines.append("")
    lines.append("[이미지 목록] 파일명 | 장면 | 영문 프롬프트")
    for img in plan:
        caption = " ".join(str(img.get("caption") or "").split())[:caption_chars]
        prompt = " ".join(str(img.get("prompt") or "").split())[:prompt_chars]
        lines.append(f"{img.get('file')} | {caption} | {prompt}")
    lines.append("")
    lines.append(f"※ 케빈: 위 이미지를 만들어 assets_inbox/{pid}/ 폴더에 파일명 그대로 올려 주세요.")
    lines.append("※ 맥북 대시보드가 20초마다 자동으로 받아 images/ 로 복사합니다.")
    return "\n".join(lines)


# ── URL ──────────────────────────────────────────────────────────────────
def new_issue_url(title: str, body: str = "") -> str:
    params = {"title": title}
    if body:
        params["body"] = body
    query = urllib.parse.urlencode(params, quote_via=urllib.parse.quote)
    return f"https://github.com/{repo_name()}/issues/new?{query}"


def build_request(project: dict, request_text: str = "") -> dict:
    """이슈로 보낼 제목·본문과, 토큰 없이 열 '1클릭 등록' 주소를 만든다."""
    pid = str(project.get("id") or "")
    title = issue_title(project)
    body = issue_body(project, request_text)
    out = {
        "project_id": pid,
        "target_inbox": f"assets_inbox/{pid}",
        "title": title,
        "body": body,
        "body_chars": len(body),
        "url": "",
        "prefill": "none",       # full | compact | none
        "copy_body": True,       # 토큰 없는 경로에서는 전체 본문을 클립보드에 함께 복사
        "label": LABEL,
        "repo": repo_name(),
    }
    if len(new_issue_url(title, body)) <= MAX_URL_CHARS:
        out.update(url=new_issue_url(title, body), prefill="full", copy_body=False)
        return out
    for prompt_chars, caption_chars in ((200, 30), (140, 24), (90, 18)):
        cand = compact_body(project, prompt_chars, caption_chars)
        if len(new_issue_url(title, cand)) <= MAX_URL_CHARS:
            out.update(url=new_issue_url(title, cand), prefill="compact")
            return out
    out.update(url=new_issue_url(title), prefill="none")
    return out


# ── 깃허브 API ────────────────────────────────────────────────────────────
def _api(method: str, path: str, tok: str, payload: dict | None = None,
         timeout: int = 25) -> tuple[int, dict]:
    url = path if path.startswith("http") else API_BASE + path
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("X-GitHub-Api-Version", "2022-11-28")
    req.add_header("User-Agent", USER_AGENT)
    if data is not None:
        req.add_header("Content-Type", "application/json")
    if tok:
        req.add_header("Authorization", f"Bearer {tok}")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read().decode("utf-8", "replace")
            try:
                return r.status, json.loads(raw) if raw.strip() else {}
            except json.JSONDecodeError:
                return r.status, {"raw": raw[:400]}
    except urllib.error.HTTPError as e:
        detail = ""
        try:
            detail = e.read().decode("utf-8", "replace")[:400]
        except Exception:
            pass
        raise GitHubError(f"깃허브 API {e.code}: {detail or e.reason}") from e
    except Exception as e:
        raise GitHubError(f"깃허브에 연결하지 못했습니다: {str(e)[:200]}") from e


def ensure_label(repo: str, tok: str) -> None:
    """image-request 라벨이 없으면 만든다 (이미 있으면 422 — 무시)."""
    try:
        _api("POST", f"/repos/{repo}/labels", tok,
             {"name": LABEL, "color": LABEL_COLOR, "description": LABEL_DESC})
    except GitHubError:
        pass


def create_issue(project: dict, request_text: str = "", tok: str | None = None) -> dict:
    token_value = (tok or "").strip() or token()
    if not token_value:
        raise GitHubError("깃허브 토큰이 없습니다.")
    repo = repo_name()
    body = build_request(project, request_text)
    ensure_label(repo, token_value)
    payload = {"title": body["title"], "body": body["body"], "labels": [LABEL]}
    label_applied = True
    try:
        status, data = _api("POST", f"/repos/{repo}/issues", token_value, payload)
    except GitHubError as e:
        # 라벨이 없거나 권한이 모자라는 경우(422)에는 라벨 없이 한 번 더 시도해 등록은 되게 한다
        if "422" not in str(e):
            raise
        label_applied = False
        status, data = _api("POST", f"/repos/{repo}/issues", token_value,
                            {"title": body["title"], "body": body["body"]})
    if status not in (200, 201) or not isinstance(data, dict) or not data.get("html_url"):
        raise GitHubError(f"이슈를 만들지 못했습니다 (HTTP {status})")
    return {"number": data.get("number"), "url": data.get("html_url"),
            "title": body["title"], "labels": label_applied}


def check_token(tok: str | None = None) -> dict:
    token_value = (tok or "").strip() or token()
    if not token_value:
        raise GitHubError("저장된 토큰이 없습니다.")
    repo = repo_name()
    _, user = _api("GET", "/user", token_value)
    _, info = _api("GET", f"/repos/{repo}", token_value)
    perms = info.get("permissions") or {}
    return {"login": user.get("login"), "repo": repo, "private": bool(info.get("private")),
            "can_push": bool(perms.get("push") or perms.get("admin")),
            "issues": bool(info.get("has_issues", True))}
