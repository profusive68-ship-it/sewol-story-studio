"""유튜브 자동/예약 업로드 — OAuth 연동, 제목·설명·썸네일·예약 공개까지."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .paths import BASE, project_dir
from .settings import load_config, save_config

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube",
    "https://www.googleapis.com/auth/youtube.readonly",
    "https://www.googleapis.com/auth/youtube.force-ssl",
]
CONFIG_DIR = BASE / "config"
CLIENT_PATH = CONFIG_DIR / "client_secret.json"
TOKEN_PATH = CONFIG_DIR / "youtube_token.json"
PENDING_PATH = CONFIG_DIR / "pending_comments.json"
KST = timezone(timedelta(hours=9))


class YouTubeError(RuntimeError):
    pass


def _ensure() -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)


def save_client_secret(data: bytes, filename: str = "client_secret.json") -> Path:
    _ensure()
    if len(data) < 40:
        raise YouTubeError("client_secret.json 파일이 비어 있습니다.")
    try:
        obj = json.loads(data.decode("utf-8"))
    except Exception:
        raise YouTubeError("JSON 파일이 아닙니다. Google Cloud 에서 받은 client_secret.json 을 올려 주세요.")
    if "installed" not in obj and "web" not in obj:
        raise YouTubeError("OAuth 클라이언트 JSON 형식이 아닙니다. (installed 또는 web 키가 없습니다)")
    CLIENT_PATH.write_bytes(data)
    try:
        CLIENT_PATH.chmod(0o600)
    except Exception:
        pass
    return CLIENT_PATH


def has_client() -> bool:
    return CLIENT_PATH.exists() and CLIENT_PATH.stat().st_size > 40


def _load_creds():
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    if not TOKEN_PATH.exists():
        return None
    try:
        creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)
    except Exception:
        return None
    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            TOKEN_PATH.write_text(creds.to_json(), encoding="utf-8")
        except Exception:
            return None
    return creds if creds and creds.valid else None


def _service():
    from googleapiclient.discovery import build
    creds = _load_creds()
    if not creds:
        raise YouTubeError("유튜브 채널이 연동되어 있지 않습니다. [유튜브 채널 연동]을 먼저 눌러 주세요.")
    return build("youtube", "v3", credentials=creds, cache_discovery=False)


def channel_info() -> dict | None:
    try:
        svc = _service()
        resp = svc.channels().list(part="snippet,statistics", mine=True).execute()
        items = resp.get("items") or []
        if not items:
            return None
        it = items[0]
        return {
            "id": it.get("id"),
            "title": it.get("snippet", {}).get("title"),
            "handle": it.get("snippet", {}).get("customUrl"),
            "subscribers": it.get("statistics", {}).get("subscriberCount"),
            "videos": it.get("statistics", {}).get("videoCount"),
        }
    except Exception:
        return None


def status() -> dict:
    info = channel_info()
    return {
        "has_client": has_client(),
        "client_path": str(CLIENT_PATH) if has_client() else "",
        "connected": bool(info),
        "channel": info,
        "error": None if info or not has_client() else "연동되지 않았습니다.",
    }


def connect(progress=None) -> dict:
    """브라우저를 열어 구글 로그인 → 토큰 저장."""
    if not has_client():
        raise YouTubeError("먼저 client_secret.json 을 올려 주세요.")
    from google_auth_oauthlib.flow import InstalledAppFlow
    _ensure()
    if TOKEN_PATH.exists():
        try:
            TOKEN_PATH.unlink()
        except Exception:
            pass
    if progress:
        progress(10, "브라우저에서 구글 로그인을 기다리는 중…")
    flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT_PATH), SCOPES)
    creds = flow.run_local_server(port=0, open_browser=True, prompt="consent",
                                  authorization_prompt_message="브라우저에서 세월의 사연극장 채널로 로그인해 주세요.")
    TOKEN_PATH.write_text(creds.to_json(), encoding="utf-8")
    try:
        TOKEN_PATH.chmod(0o600)
    except Exception:
        pass
    if progress:
        progress(80, "채널 정보 확인 중…")
    info = channel_info()
    return {"ok": True, "channel": info}


def disconnect() -> dict:
    if TOKEN_PATH.exists():
        TOKEN_PATH.unlink()
    return {"ok": True}


def _iso_kst(value: str | None) -> str | None:
    if not value:
        return None
    v = value.strip()
    try:
        if v.endswith("Z"):
            dt = datetime.fromisoformat(v.replace("Z", "+00:00"))
        else:
            dt = datetime.fromisoformat(v)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=KST)
        return dt.astimezone(KST).isoformat(timespec="seconds")
    except Exception:
        raise YouTubeError("예약 시간 형식이 올바르지 않습니다. (예: 2026-11-23T21:00)")


def upload_project(pid: str, title_index: int = 0, privacy: str = "private",
                   publish_at: str | None = None, progress=None) -> dict:
    from googleapiclient.http import MediaFileUpload
    from .project import build_upload_pack, load, now, save

    p = load(pid)
    video_rel = (p.get("outputs") or {}).get("video")
    if not video_rel:
        raise YouTubeError("먼저 영상을 조립해 주세요. (final.mp4 없음)")
    video = project_dir(pid) / video_rel
    if not video.exists():
        raise YouTubeError("final.mp4 파일이 없습니다. 다시 조립해 주세요.")

    pack = build_upload_pack(p)
    titles = pack["titles"]
    idx = max(0, min(len(titles) - 1, int(title_index or 0)))
    title = titles[idx][:100]
    desc = pack["description"]
    disclosure = "※ 이 영상은 AI 음성·이미지로 제작한 창작 사연입니다."
    if disclosure not in desc:
        desc = desc + "\n\n" + disclosure
    desc = desc[:4900]
    tags = [h.lstrip("#") for h in pack["hashtags"]][:15]

    if privacy not in ("public", "private", "unlisted"):
        privacy = "private"
    publish_at_iso = _iso_kst(publish_at) if privacy == "private" else None
    if publish_at_iso:
        try:
            dt = datetime.fromisoformat(publish_at_iso)
            if dt <= datetime.now(KST) + timedelta(minutes=2):
                raise YouTubeError("예약 시간은 지금부터 2분 이후로 정해 주세요.")
        except YouTubeError:
            raise
        except Exception:
            publish_at_iso = None

    svc = _service()
    body = {
        "snippet": {
            "title": title,
            "description": desc,
            "tags": tags,
            "categoryId": "24",  # Entertainment
            "defaultLanguage": "ko",
            "defaultAudioLanguage": "ko",
        },
        "status": {
            "privacyStatus": privacy,
            "selfDeclaredMadeForKids": False,
            "embeddable": True,
        },
    }
    if publish_at_iso:
        body["status"]["publishAt"] = publish_at_iso

    if progress:
        progress(5, f"업로드 준비 — {title[:40]}")
    media = MediaFileUpload(str(video), chunksize=8 * 1024 * 1024, resumable=True, mimetype="video/mp4")
    req = svc.videos().insert(part="snippet,status", body=body, media_body=media)
    response = None
    while response is None:
        chunk = req.next_chunk()
        if chunk and chunk[0] and progress:
            progress(max(8, int(chunk[0].progress() * 90)), f"유튜브 업로드 {int(chunk[0].progress() * 100)}%")
        if chunk:
            response = chunk[1]
    vid = (response or {}).get("id")
    if not vid:
        raise YouTubeError("업로드 응답에 영상 ID 가 없습니다.")

    # 썸네일
    thumb_rel = (p.get("outputs") or {}).get("thumb_style1")
    thumb_ok = False
    if thumb_rel and (project_dir(pid) / thumb_rel).exists():
        try:
            svc.thumbnails().set(videoId=vid,
                                 media_body=MediaFileUpload(str(project_dir(pid) / thumb_rel),
                                                            mimetype="image/jpeg")).execute()
            thumb_ok = True
        except Exception:
            pass

    # 첫 댓글 자동 게시 / 예약 대기 등록
    comment_text = pack.get("pinned_comment") or ""
    comment_state = "none"
    try:
        if privacy == "public":
            post_comment(vid, comment_text)
            comment_state = "첫 댓글 자동 게시 완료 (상단 고정 핀만 유튜브 앱/웹에서 1클릭)"
        elif publish_at_iso and comment_text:
            queue_comment(pid, vid, publish_at_iso, comment_text)
            comment_state = "공개 시각에 자동으로 첫 댓글을 답니다 (공개 10초 전부터 확인)"
    except Exception as e:
        comment_state = f"댓글 예약 실패: {str(e)[:120]}"

    result = {
        "video_id": vid,
        "url": f"https://youtu.be/{vid}",
        "studio_url": f"https://studio.youtube.com/video/{vid}/edit",
        "title": title,
        "privacy": privacy,
        "publish_at": publish_at_iso,
        "thumbnail": thumb_ok,
        "comment_status": comment_state,
        "uploaded_at": now(),
    }
    p["youtube"] = result
    p["upload_pack"] = pack
    save(p)
    if progress:
        progress(100, "업로드 완료")
    return result


def post_comment(video_id: str, text: str) -> dict:
    """첫 댓글 자동 게시. (YouTube API 에는 '고정' 기능이 없어 앱에서 1클릭 필요)"""
    if not (text or "").strip():
        raise YouTubeError("댓글 문구가 비어 있습니다.")
    svc = _service()
    resp = svc.commentThreads().insert(
        part="snippet",
        body={"snippet": {"videoId": video_id,
                          "topLevelComment": {"snippet": {"textOriginal": text[:9000]}}}},
    ).execute()
    cid = (resp.get("snippet", {}).get("topLevelComment", {}) or {}).get("id") or resp.get("id")
    return {"comment_id": cid, "video_id": video_id}


def _load_pending() -> list[dict]:
    if PENDING_PATH.exists():
        try:
            return json.loads(PENDING_PATH.read_text(encoding="utf-8"))
        except Exception:
            return []
    return []


def _save_pending(items: list[dict]) -> None:
    _ensure()
    PENDING_PATH.write_text(json.dumps(items, ensure_ascii=False, indent=1), encoding="utf-8")
    try:
        PENDING_PATH.chmod(0o600)
    except Exception:
        pass


def queue_comment(pid: str, video_id: str, publish_at: str | None, text: str) -> dict:
    items = _load_pending()
    entry = {
        "project_id": pid, "video_id": video_id, "publish_at": publish_at or "",
        "text": text, "status": "pending",
        "created_at": datetime.now(KST).isoformat(timespec="seconds"),
        "comment_id": None, "checked": 0, "error": None,
    }
    items = [x for x in items if x.get("video_id") != video_id] + [entry]
    _save_pending(items)
    return entry


def _video_status(video_id: str) -> str | None:
    svc = _service()
    resp = svc.videos().list(part="status", id=video_id).execute()
    items = resp.get("items") or []
    return items[0].get("status", {}).get("privacyStatus") if items else None


def process_pending_comments(progress=None) -> list[dict]:
    """예약 공개 직전부터 10~15초 간격으로 상태를 확인해 공개되는 즉시 1등 댓글을 단다."""
    items = _load_pending()
    done = []
    changed = False
    for it in items:
        if it.get("status") != "pending":
            continue
        vid = it.get("video_id")
        text = it.get("text") or ""
        if not vid:
            continue
        now = datetime.now(KST)
        pub = None
        if it.get("publish_at"):
            try:
                pub = datetime.fromisoformat(it["publish_at"])
            except Exception:
                pub = None
        if pub and now < pub - timedelta(seconds=15):
            continue
        try:
            st = _video_status(vid)
            it["checked"] = int(it.get("checked", 0)) + 1
            changed = True
            if st == "public":
                r = post_comment(vid, text)
                it["status"] = "posted"
                it["comment_id"] = r.get("comment_id")
                it["posted_at"] = now.isoformat(timespec="seconds")
                done.append(it)
                # 프로젝트 상태 갱신
                try:
                    from .project import load as _load, save as _save
                    if it.get("project_id"):
                        p = _load(it["project_id"])
                        y = p.setdefault("youtube", {})
                        y["comment_id"] = r.get("comment_id")
                        y["comment_status"] = "첫 댓글 자동 게시 완료 (상단 고정 핀만 유튜브 앱/웹에서 1클릭)"
                        _save(p)
                except Exception:
                    pass
            elif it["checked"] > 2000:
                it["status"] = "expired"
                it["error"] = f"공개 상태가 되지 않았습니다 (현재 {st})"
        except Exception as e:
            it["error"] = str(e)[:200]
            changed = True
    if changed:
        _save_pending(items)
    return done


def apply_defaults(payload: dict) -> dict:
    cfg = load_config()
    payload.setdefault("youtube_privacy", cfg.get("youtube_privacy", "private"))
    payload.setdefault("youtube_publish_at", cfg.get("youtube_publish_at", ""))
    payload.setdefault("youtube_title_index", cfg.get("youtube_title_index", 0))
    payload.setdefault("auto_upload", cfg.get("youtube_auto_upload", False))
    return payload


def save_defaults(privacy: str, publish_at: str, title_index: int, auto: bool) -> dict:
    cfg = save_config({
        "youtube_privacy": privacy,
        "youtube_publish_at": publish_at,
        "youtube_title_index": int(title_index),
        "youtube_auto_upload": bool(auto),
    })
    return {
        "youtube_privacy": cfg.get("youtube_privacy"),
        "youtube_publish_at": cfg.get("youtube_publish_at"),
        "youtube_title_index": cfg.get("youtube_title_index"),
        "youtube_auto_upload": cfg.get("youtube_auto_upload"),
    }
