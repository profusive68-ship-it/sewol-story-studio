"""깃허브 이미지 요청 — 토큰이 있으면 이슈를 바로 등록하고, 없으면 1클릭 등록 화면을 연다.

두 가지 종류
- image_request  : 장면 이미지 처음 요청        (라벨 image-request,  target_inbox assets_inbox/{pid})
- image_revision : 이미 받은 컷의 이미지 수정   (라벨 image-revision, target_inbox assets_inbox/{pid})

토큰은 config/config.json(또는 settings.json) 안에만 있고 화면·응답에는 가려서 나간다.
이슈 본문에는 항상 `target_inbox: …` 를 넣어 케빈이 정확한 폴더명으로 올릴 수 있게 한다.
"""
from __future__ import annotations

import json
import re
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime

from .settings import DEFAULT_GITHUB_REPO, load_config

API_BASE = "https://api.github.com"
USER_AGENT = "sewol-story-studio"

# 종류별 라벨·제목 접두어
KINDS = {
    "image_request": {
        "label": "image-request", "prefix": "[이미지요청]",
        "color": "c9a227", "desc": "케빈 이미지 요청 (대시보드 자동 등록)",
        "heading": "🖼 세월의 사연극장 이미지 요청",
    },
    "image_revision": {
        "label": "image-revision", "prefix": "[이미지수정]",
        "color": "e0679b", "desc": "케빈 이미지 수정 요청 (같은 파일명으로 다시)",
        "heading": "✏️ 세월의 사연극장 이미지 수정 요청",
    },
}
DEFAULT_KIND = "image_request"
LABEL = KINDS[DEFAULT_KIND]["label"]
LABEL_COLOR = KINDS[DEFAULT_KIND]["color"]
LABEL_DESC = KINDS[DEFAULT_KIND]["desc"]

MAX_BODY_CHARS = 60000      # GitHub 이슈 본문 한도(65,536자)보다 조금 아래
MAX_URL_CHARS = 5600        # github.com 이 약 6,000자를 넘기면 414/500 으로 막는다
MAX_INSTRUCTION_CHARS = 2000


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


def kind_of(kind: str | None) -> str:
    k = (kind or DEFAULT_KIND).strip()
    aliases = {"revision": "image_revision", "image": "image_request",
               "fix": "image_revision", "edit": "image_revision"}
    k = aliases.get(k, k)
    return k if k in KINDS else DEFAULT_KIND


def label(kind: str | None = None) -> str:
    return KINDS[kind_of(kind)]["label"]


def title_prefix(kind: str | None = None) -> str:
    return KINDS[kind_of(kind)]["prefix"]


def target_inbox(pid: str, kind: str | None = None) -> str:
    return f"assets_inbox/{pid}"


# ── 이슈 제목·본문 ────────────────────────────────────────────────────────
def _topic(project: dict) -> str:
    topic = ((project.get("options") or {}).get("topic") or "").strip()
    if not topic:
        topic = (project.get("title") or "").strip()
    return " ".join(topic.split())


def issue_title(project: dict, kind: str | None = None) -> str:
    pid = str(project.get("id") or "")
    topic = _topic(project)[:70]
    prefix = title_prefix(kind)
    return f"{prefix} {pid} - {topic}" if topic else f"{prefix} {pid}"


def _fmt_line(project: dict) -> str:
    fmt = project.get("format") or {}
    bits = [str(fmt.get("label") or "").strip()]
    if fmt.get("aspect"):
        bits.append(str(fmt["aspect"]))
    if fmt.get("width") and fmt.get("height"):
        bits.append(f"{fmt['width']}×{fmt['height']}")
    return " · ".join(b for b in bits if b)


def _instruction(instruction: str) -> str:
    text = (instruction or "").strip()
    if len(text) > MAX_INSTRUCTION_CHARS:
        text = text[:MAX_INSTRUCTION_CHARS].rstrip() + "…"
    return text


def _cut_line(img: dict, prompt_chars: int = 200, caption_chars: int = 40) -> str:
    caption = " ".join(str(img.get("caption") or "").split())[:caption_chars]
    prompt = " ".join(str(img.get("prompt") or "").split())[:prompt_chars]
    return f"{img.get('file')} | {caption} | {prompt}"


def issue_body(project: dict, request_text: str = "", kind: str | None = None,
               instruction: str = "") -> str:
    k = kind_of(kind)
    if k == "image_revision":
        return _body_revision(project, instruction)
    return _body_image_request(project, request_text)


def _body_image_request(project: dict, request_text: str = "") -> str:
    pid = str(project.get("id") or "")
    inbox = target_inbox(pid)
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


def _body_revision(project: dict, instruction: str = "") -> str:
    """이미 받은 컷 중 일부를 고쳐 달라는 요청 — 컷 번호·장면·지시를 함께 보낸다."""
    pid = str(project.get("id") or "")
    inbox = target_inbox(pid, "image_revision")
    plan = project.get("image_plan") or []
    have = set(project.get("image_files") or [])
    lines = [
        "## ✏️ 세월의 사연극장 이미지 수정 요청",
        "",
        f"target_inbox: {inbox}",
        "",
        "이 이슈는 맥북 대시보드의 **[✏️ 케빈에게 이미지 수정 요청]** 버튼이 등록했습니다.",
        "",
        "| 항목 | 값 |",
        "| --- | --- |",
        f"| project_id | `{pid}` |",
        f"| target_inbox | `{inbox}` |",
        f"| label | `{label('image_revision')}` |",
        f"| 형식 | {_fmt_line(project) or '-'} |",
        f"| 전체 장수 | {len(plan)}장" + (f" (받음 {len(have)}장)" if have else ""),
        "| 파일명 규칙 | **같은 폴더에 같은 파일명**으로 다시 (s03.png 는 s03.png) |",
        f"| 등록 시각 | {datetime.now():%Y-%m-%d %H:%M} |",
        "",
        "### 수정 지시",
        "",
        _instruction(instruction) or "(수정 지시가 비어 있습니다 — 컷 번호와 원하는 변경을 적어 주세요)",
        "",
        "### 지금 이미지 목록 (참고)",
        "",
        "파일명 | 장면 설명 | 영문 프롬프트",
        "--- | --- | ---",
    ]
    lines += [_cut_line(img, 160, 40) for img in plan]
    lines += [
        "",
        f"> 케빈: 고친 이미지를 `{inbox}/` 에 **원래 파일명 그대로** 올려 주세요.",
        "> 맥북 대시보드가 20초마다 `git pull` 로 확인해 바뀐 파일만 자동으로 교체하고,",
        "> 영상을 다시 조립하면 새 이미지로 덮어씁니다.",
        "",
    ]
    return "\n".join(lines)


def compact_body(project: dict, prompt_chars: int = 200, caption_chars: int = 30,
                 kind: str | None = None, instruction: str = "") -> str:
    """URL 로 넘길 수 있는 짧은 본문 — 파일명·장면·프롬프트만 남긴다."""
    k = kind_of(kind)
    pid = str(project.get("id") or "")
    plan = project.get("image_plan") or []
    lines = [
        f"project_id: {pid}",
        f"target_inbox: {target_inbox(pid, k)}",
        f"label: {label(k)}",
        f"format: {_fmt_line(project)} · {len(plan)}장",
    ]
    topic = _topic(project)
    if topic:
        lines.append(f"topic: {topic[:120]}")
    if k == "image_revision":
        lines.append("")
        lines.append("[수정 지시]")
        lines.append(_instruction(instruction)[:400] or "(지시 없음)")
        lines.append("※ 고친 이미지는 같은 폴더에 같은 파일명으로 다시 올려 주세요.")
        lines.append("")
    lines.append("[이미지 목록] 파일명 | 장면 | 영문 프롬프트")
    for img in plan:
        lines.append(_cut_line(img, prompt_chars, caption_chars))
    if k != "image_revision":
        lines.append("")
        lines.append(f"※ 케빈: 위 이미지를 만들어 assets_inbox/{pid}/ 폴더에 파일명 그대로 올려 주세요.")
    lines.append("※ 맥북 대시보드가 20초마다 자동으로 받아 images/ 로 복사합니다.")
    return "\n".join(lines)


# ── URL ──────────────────────────────────────────────────────────────────
def new_issue_url(title: str, body: str = "", label_name: str = "") -> str:
    params = {"title": title}
    if body:
        params["body"] = body
    if label_name:
        params["labels"] = label_name
    query = urllib.parse.urlencode(params, quote_via=urllib.parse.quote)
    return f"https://github.com/{repo_name()}/issues/new?{query}"


def build_request(project: dict, request_text: str = "", kind: str | None = None,
                  instruction: str = "") -> dict:
    """이슈로 보낼 제목·본문과, 토큰 없이 열 '1클릭 등록' 주소를 만든다."""
    k = kind_of(kind)
    pid = str(project.get("id") or "")
    title = issue_title(project, k)
    body = issue_body(project, request_text, k, instruction)
    out = {
        "project_id": pid,
        "kind": k,
        "target_inbox": target_inbox(pid, k),
        "title": title,
        "body": body,
        "instruction": _instruction(instruction),
        "body_chars": len(body),
        "url": "",
        "prefill": "none",       # full | compact | none
        "copy_body": True,       # 토큰 없는 경로에서는 전체 본문을 클립보드에 함께 복사
        "label": label(k),
        "labels": [label(k)],
        "repo": repo_name(),
    }
    url = new_issue_url(title, body, label(k))
    if len(url) <= MAX_URL_CHARS:
        out.update(url=url, prefill="full", copy_body=False)
        return out
    for prompt_chars, caption_chars in ((200, 30), (140, 24), (90, 18)):
        cand = compact_body(project, prompt_chars, caption_chars, k, instruction)
        url = new_issue_url(title, cand, label(k))
        if len(url) <= MAX_URL_CHARS:
            out.update(url=url, prefill="compact")
            return out
    # 본문이 아무리 길어도 지시와 target_inbox 는 남긴다
    minimal = "\n".join([
        f"project_id: {pid}",
        f"target_inbox: {target_inbox(pid, k)}",
        f"label: {label(k)}",
        "### 수정 지시" if k == "image_revision" else "### 메모",
        _instruction(instruction)[:400] or "(없음)",
        "※ 전체 목록은 앱의 [요청서 보기]를 참고해 주세요.",
    ])
    out.update(url=new_issue_url(title, minimal, label(k)), prefill="compact")
    return out


# ── 깃허브 API ────────────────────────────────────────────────────────────
def _api(method: str, path: str, tok: str, payload: dict | None = None,
         timeout: int = 25) -> tuple[int, object]:
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


def ensure_label(repo: str, tok: str, kind: str | None = None) -> None:
    """라벨이 없으면 만든다 (이미 있으면 422 — 무시)."""
    k = kind_of(kind)
    info = KINDS[k]
    try:
        _api("POST", f"/repos/{repo}/labels", tok,
             {"name": info["label"], "color": info["color"], "description": info["desc"]})
    except GitHubError:
        pass


def create_issue(project: dict, request_text: str = "", tok: str | None = None,
                 kind: str | None = None, instruction: str = "") -> dict:
    token_value = (tok or "").strip() or token()
    if not token_value:
        raise GitHubError("깃허브 토큰이 없습니다.")
    k = kind_of(kind)
    repo = repo_name()
    body = build_request(project, request_text, k, instruction)
    ensure_label(repo, token_value, k)
    payload = {"title": body["title"], "body": body["body"], "labels": [label(k)]}
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
            "title": body["title"], "labels": label_applied, "label": label(k), "kind": k}


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


# ── 케빈 진행 타임라인 ────────────────────────────────────────────────────
PID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9\-_]{2,80}$")


def _short(text: str, limit: int = 600) -> str:
    text = (text or "").strip()
    return text if len(text) <= limit else text[:limit].rstrip() + "…"


def timeline(pid: str, per_page: int = 20) -> dict:
    """이 프로젝트와 연결된 깃허브 이슈·댓글을 시간순 타임라인으로 돌려준다.

    공개 저장소라 토큰 없이도 읽는다(토큰이 있으면 인증해서 조회).
    """
    pid = (pid or "").strip()
    if not PID_RE.match(pid):
        return {"ok": False, "events": [], "issues": [], "error": "잘못된 프로젝트 번호입니다."}
    repo = repo_name()
    tok = token()
    events: list[dict] = []
    issues: list[dict] = []
    path = (f"/repos/{repo}/issues?state=all&per_page={max(1, min(int(per_page or 20), 50))}"
            "&sort=updated&direction=desc")
    try:
        _, data = _api("GET", path, tok, timeout=12)
    except GitHubError as e:
        return {"ok": False, "events": [], "issues": [],
                "error": str(e)[:300], "repo": repo, "has_token": bool(tok)}
    rows = data if isinstance(data, list) else []
    matched = [it for it in rows
               if isinstance(it, dict) and not it.get("pull_request")
               and (pid in str(it.get("title") or "") or pid in str(it.get("body") or ""))]
    for it in matched[:5]:
        num = it.get("number")
        state = it.get("state")
        issues.append({"number": num, "title": it.get("title"), "state": state,
                       "url": it.get("html_url"), "created_at": it.get("created_at")})
        events.append({
            "at": it.get("created_at") or "",
            "issue": num, "kind": "open", "state": state,
            "url": it.get("html_url"),
            "text": f"📤 요청 등록 (#{num}): {it.get('title')}",
        })
        if int(it.get("comments") or 0) > 0 and num is not None:
            try:
                _, cdata = _api("GET", f"/repos/{repo}/issues/{num}/comments?per_page=30", tok, timeout=10)
            except GitHubError:
                cdata = []
            for c in (cdata if isinstance(cdata, list) else []):
                if not isinstance(c, dict):
                    continue
                events.append({
                    "at": c.get("created_at") or "",
                    "issue": num, "kind": "comment", "state": state,
                    "url": c.get("html_url") or it.get("html_url"),
                    "text": _short(c.get("body") or "", 600),
                })
        if state == "closed" and it.get("closed_at"):
            events.append({
                "at": it.get("closed_at") or "",
                "issue": num, "kind": "close", "state": "closed",
                "url": it.get("html_url"),
                "text": f"🏁 이슈 #{num} 처리 완료 (종료)",
            })
    events.sort(key=lambda e: e.get("at") or "")
    return {"ok": True, "project_id": pid, "repo": repo, "has_token": bool(tok),
            "issues": issues, "events": events,
            "checked_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
