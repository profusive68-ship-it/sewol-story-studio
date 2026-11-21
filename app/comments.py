"""유튜브 댓글 관리 — 최신 댓글 읽기, 시니어 눈높이 답글 초안, 답글 등록."""
from __future__ import annotations

import re

from .settings import load_config
from .youtube_upload import YouTubeError, _service


def _channel_id() -> str | None:
    svc = _service()
    r = svc.channels().list(part="id", mine=True).execute()
    items = r.get("items") or []
    return items[0]["id"] if items else None


def list_comments(limit: int = 20) -> list[dict]:
    svc = _service()
    cid = _channel_id()
    if not cid:
        return []
    resp = svc.commentThreads().list(
        part="snippet", allThreadsRelatedToChannelId=cid,
        maxResults=min(50, limit), order="time", textFormat="plainText").execute()
    out = []
    for it in resp.get("items", []):
        sn = it.get("snippet", {})
        top = (sn.get("topLevelComment") or {}).get("snippet", {})
        out.append({
            "thread_id": it.get("id"),
            "comment_id": (sn.get("topLevelComment") or {}).get("id"),
            "video_id": sn.get("videoId"),
            "author": top.get("authorDisplayName", ""),
            "text": top.get("textDisplay", ""),
            "published_at": top.get("publishedAt", ""),
            "like_count": int(top.get("likeCount", 0) or 0),
            "reply_count": int(sn.get("totalReplyCount", 0) or 0),
            "video_url": f"https://youtu.be/{sn.get('videoId')}" if sn.get("videoId") else "",
        })
    return out


def draft_reply(comment: str, video_title: str = "") -> str:
    """시니어 시청자 눈높이의 따뜻한 답글 초안."""
    cfg = load_config()
    text = (comment or "").strip()[:300]
    if (cfg.get("gemini_api_key") or "").strip():
        try:
            from google import genai
            from google.genai import types
            client = genai.Client(api_key=cfg["gemini_api_key"])
            prompt = f"""한국 시니어 유튜브 채널 '세월의 사연극장'의 답글을 쓴다.
시청자 댓글: {text}
영상 제목: {video_title}

규칙:
- 2~3문장, 존댓말, 따뜻하고 공손하게. 이모지는 1개까지.
- 시청자가 남긴 말을 한 번 받아 주고, 사연에 공감하는 한마디를 더한다.
- 자기 이야기를 하소연하듯 길게 쓰지 말고, 채널 홍보 문구도 넣지 않는다.
- '어느 지역에서 들려주셔서 감사합니다' 같은 자연스러운 인사 허용.
- 의료·법률·금전 조언은 하지 않는다.
답글만 출력."""
            resp = client.models.generate_content(
                model=cfg.get("text_model") or "gemini-2.5-flash", contents=prompt,
                config=types.GenerateContentConfig(temperature=0.6, max_output_tokens=200))
            draft = (getattr(resp, "text", "") or "").strip()
            if draft:
                return draft[:400]
        except Exception:
            pass
    if re.search(r"사연|이야기", text):
        return "따뜻한 말씀 남겨 주셔서 정말 감사합니다. 사연 속 주인공에게도 큰 힘이 될 것 같습니다. 오늘도 편안한 밤 되세요 🌙"
    return "소중한 댓글 남겨 주셔서 감사합니다. 어느 지역에서 들려주셨는지도 궁금하네요. 다음 사연도 정성껏 준비하겠습니다 🌷"


def post_reply(comment_id: str, text: str) -> dict:
    if not (text or "").strip():
        raise YouTubeError("답글 내용이 비어 있습니다.")
    svc = _service()
    resp = svc.comments().insert(
        part="snippet",
        body={"snippet": {"parentId": comment_id, "textOriginal": text.strip()[:9000]}}
    ).execute()
    return {"ok": True, "id": resp.get("id")}
