"""edge-tts 다중 성우 낭독 — 역할 자동 분리·속도·발음 사전·캐시."""
from __future__ import annotations

import asyncio
import hashlib
import json
import re
from pathlib import Path

from .ffmpeg_util import duration
from .paths import CACHE_DIR, project_dir
from .pronunciation import tts_text
from .settings import VOICE_MAP, VOICE_SUBSTITUTES

CACHE_DIR.mkdir(parents=True, exist_ok=True)
(CACHE_DIR / "tts").mkdir(parents=True, exist_ok=True)

_substitute_lock = asyncio.Lock()
_broken_voices: set[str] = set()


def _role_cfg(role: str, mode: str, global_rate: int) -> tuple[str, str, int]:
    cfg = VOICE_MAP.get(role) or VOICE_MAP["narrator"]
    voice = cfg.get(mode) or cfg.get("multi") or "ko-KR-InJoonNeural"
    pitch = cfg.get("pitch", "+0Hz")
    rate = int(global_rate) + int(cfg.get("rate", 0))
    rate = max(-45, min(45, rate))
    return voice, pitch, rate


def _split_long(text: str, limit: int = 180) -> list[str]:
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


def _cache_path(text: str, voice: str, rate: int, pitch: str) -> Path:
    key = hashlib.sha1(f"{voice}|{rate}|{pitch}|{text}".encode("utf-8")).hexdigest()[:20]
    return CACHE_DIR / "tts" / f"{key}.mp3"


async def synthesize_lines(project: dict, progress=None) -> dict[str, float]:
    """모든 장면 음성을 만들고 장면별 길이(초)를 돌려준다."""
    scenes = project["scenes"]
    mode = project["options"].get("voice_mode", "multi")
    gr = int(project["options"].get("rate", 0))
    pdir = project_dir(project["id"])
    lines_dir = pdir / "audio_clips"
    lines_dir.mkdir(parents=True, exist_ok=True)

    jobs = []
    for sc in scenes:
        text = tts_text(sc.get("text", ""))
        if not text:
            text = "…"
        voice, pitch, rate = _role_cfg(sc.get("speaker", "narrator"), mode, gr)
        jobs.append((sc, text, voice, pitch, rate))

    sem = asyncio.Semaphore(4)
    durations: dict[str, float] = {}
    done = {"n": 0}

    async def worker(sc, text, voice, pitch, rate):
        dest = lines_dir / f"{sc['id']}.mp3"
        cache = _cache_path(text, voice, rate, pitch)
        async with sem:
            if not dest.exists() or dest.stat().st_size < 500:
                if cache.exists() and cache.stat().st_size > 500:
                    dest.write_bytes(cache.read_bytes())
                else:
                    parts = _split_long(text)
                    data = b""
                    for part in parts:
                        data += await _synth_with_fallback(part, voice, rate, pitch)
                    cache.write_bytes(data)
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
    mode = project["options"].get("voice_mode", "multi")
    gr = int(project["options"].get("rate", 0))
    rows = []
    for role in ("narrator", "old_male", "female"):
        v, p, r = _role_cfg(role, mode, gr)
        rows.append(f"{role}: {v} ({r:+d}%, {p})")
    return " / ".join(rows)
