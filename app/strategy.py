"""채널 전략 분석 — 업로드 시간·장르·합본 조합을 데이터로 제안하고 원클릭 실행."""
from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path

from .paths import BASE, PROJECTS_DIR
from .settings import GENRES, load_config

KST_OFFSET = 9
BENCHMARK = {
    "source": "@ZestyBureau · 시니어 사연 롱폼 벤치마크",
    "best_hours": [20, 21, 22],
    "best_days": ["화", "수", "목", "일"],
    "top_genres": ["tear_family", "reversal", "inlaw"],
    "length": "20~40분 본편, 주말 2시간 합본",
    "title_rule": "[억울함/갈등] + [결정적 단서] + [충격 반전]",
    "note": "시니어 시청자는 저녁 8~10시에 길게 듣고, 주말에 몰아듣기 선호",
}
CACHE = BASE / "config" / "strategy_last.json"


def _kst(dt: datetime) -> datetime:
    return dt.astimezone().replace(tzinfo=None) if dt.tzinfo is None else dt


def _next_slot(hour: int, day_offset: int = 1) -> str:
    now = datetime.now()
    target = (now + timedelta(days=day_offset)).replace(hour=hour, minute=0, second=0, microsecond=0)
    if target <= now + timedelta(minutes=90):
        target += timedelta(days=1)
    return target.strftime("%Y-%m-%dT%H:%M")


# ── 채널 데이터 ───────────────────────────────────────────────────────────
def channel_videos(limit: int = 50) -> list[dict]:
    from .youtube_upload import _service
    svc = _service()
    ch = svc.channels().list(part="contentDetails,snippet,statistics", mine=True).execute()
    items = ch.get("items") or []
    if not items:
        return []
    uploads = items[0]["contentDetails"]["relatedPlaylists"]["uploads"]
    pl = svc.playlistItems().list(part="contentDetails", playlistId=uploads, maxResults=min(50, limit)).execute()
    ids = [x["contentDetails"]["videoId"] for x in (pl.get("items") or [])]
    if not ids:
        return []
    vids = svc.videos().list(part="snippet,statistics,contentDetails", id=",".join(ids)).execute()
    out = []
    for v in vids.get("items", []):
        sn = v.get("snippet", {})
        st = v.get("statistics", {})
        out.append({
            "id": v.get("id"),
            "title": sn.get("title", ""),
            "published_at": sn.get("publishedAt", ""),
            "tags": sn.get("tags", [])[:10],
            "views": int(st.get("viewCount", 0) or 0),
            "likes": int(st.get("likeCount", 0) or 0),
            "comments": int(st.get("commentCount", 0) or 0),
            "duration": v.get("contentDetails", {}).get("duration", ""),
        })
    return out


GENRE_WORDS = {
    "inlaw": ["며느리", "시댁", "시어머니", "시아버지", "유언", "제사", "명절"],
    "reversal": ["반전", "사이다", "통쾌", "등기", "건물주", "이혼", "복수", "뒤집"],
    "mystery": ["사진", "편지", "택배", "비밀", "실종", "미스터리", "단서", "묘비"],
    "tear_family": ["엄마", "어머니", "아버지", "가족", "눈물", "김치", "고향", "할머니"],
}


def _guess_genre(text: str) -> str:
    best, score = "tear_family", 0
    for g, words in GENRE_WORDS.items():
        s = sum(1 for w in words if w in text)
        if s > score:
            best, score = g, s
    return best


def _analyze_videos(videos: list[dict]) -> dict:
    hours = defaultdict(lambda: {"n": 0, "views": 0})
    days = defaultdict(lambda: {"n": 0, "views": 0})
    genres = defaultdict(lambda: {"n": 0, "views": 0, "likes": 0})
    top = []
    for v in videos:
        try:
            dt = datetime.fromisoformat(v["published_at"].replace("Z", "+00:00"))
            dt = dt + timedelta(hours=KST_OFFSET)
        except Exception:
            continue
        hours[dt.hour]["n"] += 1
        hours[dt.hour]["views"] += v["views"]
        days[dt.weekday()]["n"] += 1
        days[dt.weekday()]["views"] += v["views"]
        g = _guess_genre(v["title"] + " " + " ".join(v.get("tags") or []))
        genres[g]["n"] += 1
        genres[g]["views"] += v["views"]
        genres[g]["likes"] += v["likes"]
        top.append(v)
    top.sort(key=lambda v: v["views"], reverse=True)
    best_hour = max(hours.items(), key=lambda kv: (kv[1]["views"] / max(1, kv[1]["n"])))[0] if hours else 21
    best_genre = max(genres.items(), key=lambda kv: (kv[1]["views"] / max(1, kv[1]["n"])))[0] if genres else "tear_family"
    weekday_names = ["월", "화", "수", "목", "금", "토", "일"]
    best_day = weekday_names[max(days.items(), key=lambda kv: kv[1]["views"] / max(1, kv[1]["n"]))[0]] if days else "화"
    return {
        "count": len(videos),
        "total_views": sum(v["views"] for v in videos),
        "avg_views": int(sum(v["views"] for v in videos) / max(1, len(videos))),
        "best_hour": best_hour,
        "best_day": best_day,
        "hourly": {str(k): v for k, v in sorted(hours.items())},
        "genres": {k: v for k, v in genres.items()},
        "best_genre": best_genre,
        "top_videos": [{"title": v["title"], "views": v["views"], "likes": v["likes"]} for v in top[:5]],
        "avg_title_len": int(sum(len(v["title"]) for v in videos) / max(1, len(videos))),
    }


def _local_basis() -> dict:
    projects = []
    for p in PROJECTS_DIR.glob("*/project.json"):
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
            if d.get("kind") == "weekend":
                continue
            projects.append(d)
        except Exception:
            continue
    genres = Counter(d.get("genre", "tear_family") for d in projects)
    done = [d for d in projects if (d.get("status") or {}).get("stage") == "done"]
    return {
        "count": len(projects),
        "done": len(done),
        "genres": dict(genres),
        "titles": [d.get("title", "") for d in projects[:10]],
        "completed": [{"id": d.get("id"), "title": d.get("title"),
                       "genre": d.get("genre"), "duration": d.get("duration")} for d in done],
    }


def snapshot(progress=None) -> dict:
    data = {"channel": None, "analysis": None, "basis": "benchmark", "local": _local_basis()}
    try:
        vids = channel_videos()
        if vids:
            data["channel"] = {"videos": vids[:50]}
            data["analysis"] = _analyze_videos(vids)
            data["basis"] = "youtube"
    except Exception as e:
        data["channel_error"] = str(e)[:200]
    if data["basis"] != "youtube" and data["local"]["count"]:
        data["basis"] = "local"
    return data


# ── 제안 카드 ─────────────────────────────────────────────────────────────
def _genre_label(g: str) -> str:
    return GENRES.get(g, GENRES["tear_family"])["label"]


def heuristic_cards(data: dict) -> list[dict]:
    a = data.get("analysis") or {}
    hour = a.get("best_hour", 21)
    day = a.get("best_day", "화")
    genre = a.get("best_genre", "tear_family")
    if genre not in GENRES:
        genre = "tear_family"
    local = data.get("local") or {}
    completed = local.get("completed") or []
    publish1 = _next_slot(hour, 1)

    cards = [{
        "id": "time_topic",
        "kind": "create",
        "badge": "최적 시간 + 다음 사연",
        "title": f"{day}요일 밤 {hour}시, ‘{_genre_label(genre)}’ 새 사연",
        "reason": [
            f"채널 데이터 기준 가장 반응이 좋은 시간대는 {hour}시 전후입니다."
            if data.get("basis") == "youtube" else "시니어 사연 채널의 공통 황금 시간대는 저녁 8~10시입니다.",
            "첫 15초 반전 훅 + 6개월 뒤 후속편 떡밥을 붙여 다음 편까지 이어지게 합니다.",
        ],
        "action": {
            "type": "create", "preset": "full40", "genre": genre,
            "topic": "가족이 숨긴 생활 물증 하나로 시작하는 사연 (통장·영수증·녹음 등)",
            "teaser_mode": "auto_sequel", "publish_at": publish1,
            "privacy": "private", "auto_upload": True, "auto_assemble": True,
        },
        "summary": f"40분 본편 · {_genre_label(genre)} · {publish1.replace('T', ' ')} 예약",
    }, {
        "id": "genre_focus",
        "kind": "create",
        "badge": "장르 집중 편성",
        "title": f"지금은 ‘{_genre_label(genre)}’에 집중할 때",
        "reason": [
            "최근 반응이 좋은 장르를 3편 연속 편성하면 채널 알고리즘이 시청자를 더 잘 찾습니다."
            if data.get("basis") == "youtube" else "가족·사이다 계열이 시니어 롱폼에서 가장 안정적인 반응을 냅니다.",
            "20분 중편으로 부담을 낮추고, 반응이 좋으면 40분 본편으로 확장합니다.",
        ],
        "action": {
            "type": "create", "preset": "mid20", "genre": genre,
            "topic": "이웃이 알려 준 한 장의 영수증으로 시작되는 가족 이야기",
            "teaser_mode": "next_story", "publish_at": _next_slot(max(19, hour - 1), 2),
            "privacy": "private", "auto_upload": True, "auto_assemble": True,
        },
        "summary": f"20분 중편 · {_genre_label(genre)} · 3편 연속 편성 1편",
    }]

    if len(completed) >= 2:
        pick = completed[:3]
        ids = [c["id"] for c in pick]
        names = ", ".join(c["title"] for c in pick)
        cards.append({
            "id": "weekend_bundle",
            "kind": "weekend",
            "badge": "주말 몰아듣기",
            "title": "이 2~3편을 주말에 묶으면 시너지가 큽니다",
            "reason": [f"완성된 사연: {names}", "같은 장르·비슷한 감정선으로 이어 붙이면 이탈 없이 오래 듣습니다."],
            "action": {"type": "weekend", "project_ids": ids,
                       "title": "주말 몰아듣기 · 세월의 사연극장",
                       "publish_at": _next_slot(20, 3), "privacy": "private",
                       "auto_upload": True},
            "summary": f"{len(ids)}편 합본 · 약 {sum(int(c.get('duration') or 0) for c in pick) // 60}분",
        })
    else:
        cards.append({
            "id": "weekend_plan",
            "kind": "create",
            "badge": "주말 몰아듣기 준비",
            "title": "주말용 3부작 1편을 먼저 만드세요",
            "reason": ["완성된 사연이 2편 이상이면 자동 합본을 만들 수 있습니다.",
                       "같은 인물·집안이 이어지는 3부작으로 만들면 몰아듣기 전환이 높습니다."],
            "action": {"type": "create", "preset": "full40", "genre": "tear_family",
                       "topic": "한 집안의 3부작 1편 — 어머니의 김치통",
                       "teaser_mode": "auto_sequel", "publish_at": _next_slot(20, 3),
                       "privacy": "private", "auto_upload": True, "auto_assemble": True},
            "summary": "3부작 1편 · 40분 · 주말 합본 준비",
        })
    return cards[:3]


def gemini_cards(data: dict, cards_hint: list[dict]) -> list[dict]:
    cfg = load_config()
    if not (cfg.get("gemini_api_key") or "").strip():
        raise RuntimeError("no key")
    from .gemini_script import _extract_json, call_gemini
    brief = {
        "basis": data.get("basis"),
        "channel_analysis": data.get("analysis"),
        "local_projects": data.get("local"),
        "benchmark": BENCHMARK,
    }
    prompt = f"""너는 한국 시니어 유튜브 채널의 전략가다. 아래 데이터를 보고 다음 3가지 제안을 만든다.
1) 최적 업로드 시간대 + 다음에 만들 사연 주제(장르·한 줄 소재·길이)
2) 지금 가장 반응 좋은 장르 집중 편성안(20~40분)
3) 주말 2시간 몰아듣기 합본 조합(완성된 사연이 2편 미만이면 3부작 1편 제작 제안)

데이터: {json.dumps(brief, ensure_ascii=False)[:6000]}

규칙:
- 근거는 데이터에 있는 숫자만. 없는 숫자를 지어내지 않는다.
- 제목은 [억울함/갈등]+[결정적 단서]+[충격 반전] 공식.
- publish_at 은 'YYYY-MM-DDTHH:MM' (한국 시간, 지금보다 미래).
- 카드마다 실행 가능한 action 을 넣는다. type 은 create 또는 weekend.
  create action: preset(shorts50|pilot5|mid20|full40), genre(tear_family|reversal|mystery|inlaw|free), topic, teaser_mode(auto_sequel|next_story), publish_at, privacy, auto_upload, auto_assemble
  weekend action: project_ids(로컬 완성 프로젝트 id 배열), title, publish_at, privacy, auto_upload
JSON 만 출력:
{{"cards":[{{"id":"time_topic|genre_focus|weekend_bundle","kind":"create|weekend","badge":"짧은 분류",
 "title":"제안 제목","reason":["근거 1","근거 2"],"summary":"한 줄 요약","action":{{...}}}}]}}"""
    resp_text = call_gemini(cfg, prompt, temperature=0.7, response_json=True)
    data2 = _extract_json(resp_text)
    out = []
    for c in data2.get("cards", [])[:3]:
        if not isinstance(c, dict) or not c.get("action"):
            continue
        out.append({
            "id": str(c.get("id", len(out))),
            "kind": str(c.get("kind", c["action"].get("type", "create"))),
            "badge": str(c.get("badge", "전략 제안")),
            "title": str(c.get("title", ""))[:80],
            "reason": [str(r)[:160] for r in (c.get("reason") or [])][:3],
            "summary": str(c.get("summary", ""))[:120],
            "action": c["action"],
        })
    if not out:
        raise RuntimeError("no cards")
    return out


def analyze(progress=None) -> dict:
    if progress:
        progress(10, "채널 영상 데이터를 모으는 중…")
    data = snapshot()
    if progress:
        progress(45, "업로드 시간·장르·제목 패턴 분석 중…")
    cards = None
    try:
        cards = gemini_cards(data, [])
    except Exception as e:
        data["gemini_error"] = str(e)[:160]
    if not cards:
        cards = heuristic_cards(data)
    result = {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "basis": data.get("basis"),
        "channel": (data.get("channel") or {}).get("videos", [])[:8],
        "analysis": data.get("analysis"),
        "local": data.get("local"),
        "benchmark": BENCHMARK,
        "cards": cards,
        "note": data.get("channel_error") or data.get("gemini_error") or "",
    }
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    if progress:
        progress(100, "전략 3가지를 만들었습니다.")
    return result


def load_cached() -> dict | None:
    if CACHE.exists():
        try:
            return json.loads(CACHE.read_text(encoding="utf-8"))
        except Exception:
            return None
    return None
