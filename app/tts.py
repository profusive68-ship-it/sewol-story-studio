"""성우 낭독 — OpenAI 감성 TTS(gpt-4o-mini-tts) · 무료 edge-tts 폴백 · 발음 사전 · 캐시.

엔진 선택(`config.tts_engine`)
  · "edge"   : 무료 edge-tts (기본값, 설치 없이 바로)
  · "openai" : OpenAI Audio Speech API 에 역할별 연기 지시(instructions)를 함께 보내
               사람이 읽는 듯한 감정 연출을 낸다. 키가 없거나 호출이 실패하면
               `config.openai_fallback_edge` 가 켜져 있을 때 edge-tts 로 안전하게 대체한다.

두 엔진 모두 발음 사전(pronunciation.tts_text)을 통과한 문장을 합성하고,
디스크 캐시 키에 engine·model 을 넣어 서로 섞이지 않게 한다.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import re
import time
import urllib.error
import urllib.request
from pathlib import Path

from .ffmpeg_util import duration
from .paths import CACHE_DIR, project_dir
from .pronunciation import tts_text
from .settings import VOICE_MAP, VOICE_SUBSTITUTES, load_config

try:  # requests 가 있으면 그대로 쓰고, 없으면 표준 라이브러리로 호출한다
    import requests  # type: ignore
except Exception:  # pragma: no cover - 설치되지 않은 환경
    requests = None  # type: ignore

CACHE_DIR.mkdir(parents=True, exist_ok=True)
(CACHE_DIR / "tts").mkdir(parents=True, exist_ok=True)

OPENAI_SPEECH_URL = "https://api.openai.com/v1/audio/speech"
OPENAI_DEFAULT_MODEL = "gpt-4o-mini-tts"
OPENAI_TIMEOUT = 90          # 초 (음성 1덩어리 기준)
OPENAI_CHUNK = 900           # 한 번에 보내는 글자 수 (모델 한도 4096자보다 넉넉히 작게)
EDGE_CHUNK = 180

TEST_TEXT = "안녕하세요. 세월의 사연극장입니다. 이 목소리가 잘 들리면 연결이 된 것입니다."
TEST_PREVIEW_NAME = "openai_test.mp3"

_substitute_lock = asyncio.Lock()
_broken_voices: set[str] = set()

# ── OpenAI 보이스 매핑 (역할 → 모드별 보이스) ────────────────────────────────
# onyx: 낮고 차분한 남성 / ash: 거친 질감의 남성 / echo: 또렷한 남성
# coral: 따뜻한 여성 / sage: 부드럽고 낮은 여성 / nova: 밝고 높은 여성
OPENAI_VOICE_MAP = {
    "narrator": {"multi": "onyx", "male": "onyx", "female": "coral"},
    "female": {"multi": "coral", "male": "coral", "female": "coral"},
    "old_female": {"multi": "sage", "male": "sage", "female": "sage"},
    "young_male": {"multi": "echo", "male": "echo", "female": "echo"},
    "old_male": {"multi": "ash", "male": "ash", "female": "ash"},
    "child": {"multi": "nova", "male": "nova", "female": "nova"},
}

# 대본에서 다른 이름으로 적혀도 같은 배역으로 본다
OPENAI_ROLE_ALIASES = {
    "elder": "old_male", "grandpa": "old_male", "oldman": "old_male",
    "grandma": "old_female", "oldwoman": "old_female",
    "man": "young_male", "woman": "female", "boy": "child", "girl": "child",
    "해설": "narrator", "노인": "old_male", "할머니": "old_female",
    "여성": "female", "청년": "young_male", "아이": "child",
}

# 역할별 감정 연기 지시문 (gpt-4o-mini-tts 전용 · tts-1-hd 에는 보내지 않는다)
OPENAI_INSTRUCTIONS = {
    "narrator": (
        "한국 시니어 라디오 드라마의 해설자입니다. 따뜻하고 차분한 심야 라디오 DJ처럼 "
        "낮고 안정된 톤으로, 문장 끝을 부드럽게 눌러 주며 감정을 과장하지 않습니다. "
        "슬픈 대목은 조금 느리고 숨을 고르듯, 따뜻한 대목은 미소가 섞인 듯 읽습니다. "
        "표준 한국어 발음으로 또박또박, 말이 너무 빠르지 않게."
    ),
    "old_male": (
        "70대 노인입니다. 낮고 연륜이 묻어나는 목소리로 천천히, 말끝을 조금 떨며 이야기합니다. "
        "감정이 북받치는 대목에서는 울먹임을 담되 소리치지 않고, 손주에게 이야기하듯 다정하게."
    ),
    "old_female": (
        "70대 할머니입니다. 가늘고 부드러운 목소리로 느리게, 정을 담아 이야기합니다. "
        "서운함과 눈물을 꾹 눌러 담은 듯한 숨결을 넣습니다."
    ),
    "female": (
        "40~50대 여성입니다. 담담하지만 정이 많고 따뜻한 목소리로, 서운함과 눈물을 참듯 "
        "조용히 읽습니다. 흥분한 대목에서도 날카롭지 않게."
    ),
    "young_male": (
        "20~30대 청년입니다. 또렷하고 조금 힘 있는 목소리로, 다급한 대목은 숨가쁘게 빠르게 "
        "말하고 평소에는 자연스러운 대화체로 읽습니다."
    ),
    "child": (
        "7~10세 아이입니다. 밝고 높은 목소리로, 또박또박 조금 느리게 말합니다."
    ),
}


def _norm_role(role: str) -> str:
    r = str(role or "narrator").strip()
    r = OPENAI_ROLE_ALIASES.get(r, OPENAI_ROLE_ALIASES.get(r.lower(), r))
    return r if r in OPENAI_VOICE_MAP else "narrator"


def openai_voice(role: str, mode: str = "multi") -> str:
    cfg = OPENAI_VOICE_MAP.get(_norm_role(role)) or OPENAI_VOICE_MAP["narrator"]
    return cfg.get(mode) or cfg.get("multi") or "onyx"


def openai_instructions(role: str) -> str:
    return OPENAI_INSTRUCTIONS.get(_norm_role(role), OPENAI_INSTRUCTIONS["narrator"])


def openai_speed(rate: int) -> float:
    """낭독 속도(%) → OpenAI speed 배율(0.25~4.0)."""
    try:
        r = int(rate)
    except Exception:
        r = 0
    return round(max(0.25, min(4.0, 1.0 + r / 100.0)), 2)


def clamp_speed(speed) -> float:
    """배율 그대로 받은 값을 0.25~4.0 안으로 다듬는다."""
    try:
        v = float(speed)
    except Exception:
        v = 1.0
    return round(max(0.25, min(4.0, v)), 2)


def _engine_settings() -> dict:
    cfg = load_config()
    engine = str(cfg.get("tts_engine") or "edge").strip().lower()
    if engine not in ("edge", "openai"):
        engine = "edge"
    model = str(cfg.get("openai_tts_model") or OPENAI_DEFAULT_MODEL).strip()
    return {
        "engine": engine,
        "model": model,
        "api_key": (cfg.get("openai_api_key") or "").strip(),
        "fallback": bool(cfg.get("openai_fallback_edge", True)),
    }


def _supports_instructions(model: str) -> bool:
    """감정 연기 지시(instructions)는 gpt-4o 계열 음성 모델만 받는다."""
    return str(model or "").startswith("gpt-4o")


# ── edge-tts ────────────────────────────────────────────────────────────
def _role_cfg(role: str, mode: str, global_rate: int) -> tuple[str, str, int]:
    cfg = VOICE_MAP.get(role) or VOICE_MAP["narrator"]
    voice = cfg.get(mode) or cfg.get("multi") or "ko-KR-InJoonNeural"
    pitch = cfg.get("pitch", "+0Hz")
    rate = int(global_rate) + int(cfg.get("rate", 0))
    rate = max(-45, min(45, rate))
    return voice, pitch, rate


def _split_long(text: str, limit: int = EDGE_CHUNK) -> list[str]:
    if len(text) <= limit:
        return [text]
    parts, buf = [], ""
    for sent in re.split(r"(?<=[.!?])\s+", text):
        if len(buf) + len(sent) + 1 <= limit:
            buf = (buf + " " + sent).strip()
        else:
            if buf:
                parts.append(buf)
            buf = sent
    if buf:
        parts.append(buf)
    return parts or [text[:limit]]


async def _synth_one(text: str, voice: str, rate: int, pitch: str) -> bytes:
    import edge_tts
    last: Exception | None = None
    for attempt in range(3):
        try:
            com = edge_tts.Communicate(text, voice, rate=f"{rate:+d}%", pitch=pitch)
            data = bytearray()
            async for chunk in com.stream():
                if chunk["type"] == "audio":
                    data.extend(chunk["data"])
            if len(data) < 500:
                raise RuntimeError("빈 오디오")
            return bytes(data)
        except Exception as e:
            last = e
            await asyncio.sleep(0.8 * (attempt + 1))
    raise RuntimeError(f"TTS 실패({voice}): {last}")


async def _synth_with_fallback(text: str, voice: str, rate: int, pitch: str) -> bytes:
    global _broken_voices
    if voice in _broken_voices and voice in VOICE_SUBSTITUTES:
        voice, pitch, dr = VOICE_SUBSTITUTES[voice]
        rate = max(-45, min(45, rate + int(dr)))
    try:
        return await _synth_one(text, voice, rate, pitch)
    except Exception:
        if voice in VOICE_SUBSTITUTES:
            async with _substitute_lock:
                _broken_voices.add(voice)
            nv, npitch, dr = VOICE_SUBSTITUTES[voice]
            return await _synth_one(text, nv, max(-45, min(45, rate + int(dr))), npitch)
        raise


# ── OpenAI Audio Speech ─────────────────────────────────────────────────
def _decode(raw: bytes) -> str:
    try:
        return raw.decode("utf-8", "replace")
    except Exception:
        return ""


def _http_post_json(url: str, payload: dict, headers: dict, timeout: int) -> tuple[int, bytes, str]:
    """POST 한 번 — requests 가 없으면 표준 라이브러리로 같은 요청을 보낸다."""
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    if requests is not None:
        try:
            r = requests.post(url, data=body, headers=headers, timeout=(10, timeout))
        except Exception as e:
            raise RuntimeError(f"OpenAI 서버에 연결하지 못했습니다: {str(e)[:160]}")
        return int(r.status_code), r.content or b"", _decode(r.content or b"")
    req = urllib.request.Request(url, data=body, headers=dict(headers), method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = resp.read()
            return int(getattr(resp, "status", 200) or 200), data, ""
    except urllib.error.HTTPError as e:
        raw = e.read() if hasattr(e, "read") else b""
        return int(e.code), raw, _decode(raw)
    except Exception as e:
        raise RuntimeError(f"OpenAI 서버에 연결하지 못했습니다: {str(e)[:160]}")


def openai_error_message(status: int, body: str) -> str:
    """OpenAI 오류 응답을 맥북 화면에서 바로 읽을 수 있는 한국어로 바꾼다."""
    msg = ""
    try:
        payload = json.loads(body or "{}")
        err = payload.get("error") if isinstance(payload, dict) else None
        if isinstance(err, dict):
            msg = str(err.get("message") or "")
        elif isinstance(err, str):
            msg = err
    except Exception:
        msg = (body or "").strip()
    msg = msg[:200]
    if status == 401:
        return ("OpenAI API 키가 올바르지 않습니다(401). "
                "platform.openai.com/api-keys 에서 키를 다시 확인해 주세요.")
    if status == 403:
        return ("이 키로는 음성 합성을 쓸 수 없습니다(403). 결제 정보와 키 권한을 확인해 주세요.")
    if status == 404:
        return "요청한 음성 모델이나 보이스를 찾을 수 없습니다(404). " + (msg or "")
    if status == 429:
        return ("OpenAI 사용 한도를 넘었습니다(429). 결제 정보·월 한도를 확인해 주세요. "
                + (msg or ""))
    if status == 400:
        return "요청이 거부되었습니다(400). " + (msg or "모델·보이스 이름을 확인해 주세요.")
    if status >= 500:
        return f"OpenAI 서버가 잠시 불안정합니다({status}). " + (msg or "")
    return f"OpenAI 음성 호출 실패({status}). " + (msg or "")


RETRY_STATUS = (408, 409, 425, 429, 500, 502, 503, 504)


def synthesize_openai_chunk(text: str, voice: str, speed: float, instructions: str,
                            model: str, api_key: str, retries: int = 2) -> bytes:
    """OpenAI Audio Speech 로 한 덩어리 mp3 바이트를 만든다 (동기)."""
    if not (api_key or "").strip():
        raise RuntimeError("OpenAI API 키가 없습니다.")
    payload = {
        "model": model or OPENAI_DEFAULT_MODEL,
        "input": text,
        "voice": voice or "onyx",
        "response_format": "mp3",
        "speed": clamp_speed(speed),
    }
    if instructions and _supports_instructions(model):
        payload["instructions"] = instructions
    headers = {"Authorization": "Bearer " + api_key.strip(), "Content-Type": "application/json"}

    last = "OpenAI 음성 합성에 실패했습니다."
    for attempt in range(retries + 1):
        status, data, body = _http_post_json(OPENAI_SPEECH_URL, payload, headers, OPENAI_TIMEOUT)
        if status == 200 and len(data) > 500:
            return data
        if status == 200:
            last = "OpenAI가 빈 음성을 돌려주었습니다. 잠시 뒤 다시 시도해 주세요."
        else:
            last = openai_error_message(status, body)
        if status in RETRY_STATUS and attempt < retries:
            time.sleep(1.0 * (attempt + 1))
            continue
        raise RuntimeError(last)
    raise RuntimeError(last)


def openai_payload_preview(text: str, role: str = "narrator", mode: str = "multi",
                           rate: int = 0, model: str = OPENAI_DEFAULT_MODEL) -> dict:
    """실제로 OpenAI 에 보낼 payload 모양 (테스트·화면 설명용)."""
    voice = openai_voice(role, mode)
    instr = openai_instructions(role)
    payload = {
        "model": model or OPENAI_DEFAULT_MODEL,
        "input": text,
        "voice": voice,
        "response_format": "mp3",
        "speed": openai_speed(rate),
    }
    if instr and _supports_instructions(model):
        payload["instructions"] = instr
    return payload


def test_openai_tts(cfg: dict | None = None, save_preview: bool = True) -> dict:
    """설정 화면 [연결 테스트] — 짧은 한국어 한 문장을 실제로 합성해 본다."""
    st = _engine_settings()
    cfg = cfg or {}
    api_key = (cfg.get("openai_api_key") or st["api_key"] or "").strip()
    model = str(cfg.get("openai_tts_model") or st["model"] or OPENAI_DEFAULT_MODEL).strip()
    if not api_key:
        return {"ok": False, "error": "OpenAI API 키가 저장되어 있지 않습니다. 키를 먼저 저장해 주세요."}
    text = tts_text(TEST_TEXT) or TEST_TEXT
    voice = openai_voice("narrator", "multi")
    try:
        data = synthesize_openai_chunk(text, voice, 1.0, openai_instructions("narrator"),
                                       model, api_key, retries=1)
    except RuntimeError as e:
        return {"ok": False, "error": str(e)[:300], "model": model, "voice": voice}
    except Exception as e:  # pragma: no cover - 예상 밖 오류도 화면에 알린다
        return {"ok": False, "error": f"연결 테스트 실패: {str(e)[:250]}",
                "model": model, "voice": voice}

    preview_url = ""
    seconds = 0.0
    if save_preview:
        dest = CACHE_DIR / "tts" / TEST_PREVIEW_NAME
        try:
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(data)
            preview_url = f"/api/tts/preview?ts={int(dest.stat().st_mtime)}"
            try:
                seconds = round(float(duration(dest)), 1)
            except Exception:
                seconds = round(len(TEST_TEXT) / 4.3, 1)
        except Exception:
            preview_url = ""
    if not seconds:
        seconds = round(len(TEST_TEXT) / 4.3, 1)
    return {
        "ok": True,
        "message": (f"연결 성공 — {model} · {voice} · {len(data) // 1024}KB · 약 {seconds}초"),
        "model": model,
        "voice": voice,
        "bytes": len(data),
        "seconds": seconds,
        "preview_url": preview_url,
    }


def preview_path() -> Path:
    return CACHE_DIR / "tts" / TEST_PREVIEW_NAME


# ── 캐시 ────────────────────────────────────────────────────────────────
def _cache_path(text: str, engine: str, model: str, voice: str, rate: int,
                pitch: str, speed: float, instructions: str) -> Path:
    raw = "|".join([
        engine, model, voice, f"{rate:+d}", pitch, f"{float(speed):.2f}",
        hashlib.sha1((instructions or "").encode("utf-8")).hexdigest()[:8], text,
    ])
    key = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:20]
    return CACHE_DIR / "tts" / f"{engine}_{key}.mp3"


# ── 본 합성 ─────────────────────────────────────────────────────────────
async def synthesize_lines(project: dict, progress=None) -> dict[str, float]:
    """모든 장면 음성을 만들고 장면별 길이(초)를 돌려준다."""
    scenes = project["scenes"]
    opts = project.get("options") or {}
    mode = opts.get("voice_mode", "multi")
    gr = int(opts.get("rate", 0))
    pdir = project_dir(project["id"])
    lines_dir = pdir / "audio_clips"
    lines_dir.mkdir(parents=True, exist_ok=True)

    st = _engine_settings()
    state = {"engine": st["engine"]}
    model = st["model"]
    api_key = st["api_key"]
    fallback = st["fallback"]
    warned = {"flag": False}

    def warn(msg: str) -> None:
        if warned["flag"]:
            return
        warned["flag"] = True
        try:
            project.setdefault("warnings", []).append(msg)
        except Exception:
            pass

    if state["engine"] == "openai" and not api_key:
        if not fallback:
            raise RuntimeError(
                "OpenAI API 키가 없습니다. [🎙️ 음성 엔진]에서 키를 저장하거나 "
                "음성 엔진을 '무료 edge-tts'로 바꿔 주세요.")
        warn("OpenAI API 키가 없어 무료 edge-tts로 제작했습니다. [🎙️ 음성 엔진]에서 키를 저장하면 다음 편부터 감성 TTS로 나갑니다.")
        state["engine"] = "edge"

    jobs = []
    for sc in scenes:
        text = tts_text(sc.get("text", ""))
        if not text:
            text = "…"
        jobs.append((sc, text, sc.get("speaker", "narrator")))

    sem = asyncio.Semaphore(4)
    durations: dict[str, float] = {}
    done = {"n": 0}

    def plan_for(text: str, role: str) -> dict:
        if state["engine"] == "openai":
            voice = openai_voice(role, mode)
            speed = openai_speed(gr)
            instr = openai_instructions(role)
            return {"engine": "openai", "voice": voice, "speed": speed, "instr": instr,
                    "rate": 0, "pitch": "", "limit": OPENAI_CHUNK,
                    "cache": _cache_path(text, "openai", model, voice, 0, "", speed, instr)}
        voice, pitch, rate = _role_cfg(role, mode, gr)
        return {"engine": "edge", "voice": voice, "speed": 0.0, "instr": "",
                "rate": rate, "pitch": pitch, "limit": EDGE_CHUNK,
                "cache": _cache_path(text, "edge", "", voice, rate, pitch, 0.0, "")}

    async def synth_part(part: str, role: str) -> bytes:
        if state["engine"] == "openai":
            try:
                return await asyncio.to_thread(
                    synthesize_openai_chunk, part, openai_voice(role, mode), openai_speed(gr),
                    openai_instructions(role), model, api_key)
            except RuntimeError as e:
                if not fallback:
                    raise
                warn(f"OpenAI 음성 호출에 실패해 무료 edge-tts로 대체했습니다 — {str(e)[:140]}")
                state["engine"] = "edge"
        voice, pitch, rate = _role_cfg(role, mode, gr)
        return await _synth_with_fallback(part, voice, rate, pitch)

    async def worker(sc, text, role):
        dest = lines_dir / f"{sc['id']}.mp3"
        async with sem:
            if not dest.exists() or dest.stat().st_size < 500:
                plan = plan_for(text, role)
                cache: Path = plan["cache"]
                if cache.exists() and cache.stat().st_size > 500:
                    dest.write_bytes(cache.read_bytes())
                else:
                    data = b""
                    for part in _split_long(text, int(plan["limit"])):
                        data += await synth_part(part, role)
                    if state["engine"] == plan["engine"]:
                        try:
                            cache.write_bytes(data)
                        except Exception:
                            pass
                    dest.write_bytes(data)
        try:
            durations[sc["id"]] = duration(dest)
        except Exception:
            durations[sc["id"]] = max(1.2, len(text) / 4.3)
        done["n"] += 1
        if progress:
            progress(done["n"], len(jobs))

    await asyncio.gather(*[worker(*j) for j in jobs])
    return durations


def synthesize_sync(project: dict, progress=None) -> dict[str, float]:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(synthesize_lines(project, progress))
    # 이미 이벤트 루프 안이면 별도 스레드에서 실행
    import concurrent.futures
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
        return ex.submit(lambda: asyncio.run(synthesize_lines(project, progress))).result()


def voice_report(project: dict) -> str:
    opts = project.get("options") or {}
    mode = opts.get("voice_mode", "multi")
    gr = int(opts.get("rate", 0))
    st = _engine_settings()
    rows = []
    if st["engine"] == "openai" and st["api_key"]:
        for role in ("narrator", "old_male", "female"):
            rows.append(f"{role}: {openai_voice(role, mode)} (x{openai_speed(gr):.2f})")
        return f"OpenAI {st['model']} · " + " / ".join(rows)
    for role in ("narrator", "old_male", "female"):
        v, p, r = _role_cfg(role, mode, gr)
        rows.append(f"{role}: {v} ({r:+d}%, {p})")
    prefix = "무료 edge-tts"
    if st["engine"] == "openai":
        prefix = "무료 edge-tts (OpenAI 키 없음)"
    return prefix + " · " + " / ".join(rows)
