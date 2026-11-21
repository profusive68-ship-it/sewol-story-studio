"""음성·BGM·효과음 믹싱 — 촘촘한 실음원 SFX, 감정 스웰, 덕킹 -16dB, -13.0 LUFS."""
from __future__ import annotations

import json
import re
from pathlib import Path

import numpy as np
from scipy.io import wavfile
from scipy.ndimage import uniform_filter1d

from .ffmpeg_util import ffmpeg_exe, run
from .music import EMOTION_GAIN_DB, SR, get_bgm
from .paths import project_dir
from .sfx import get_sfx, is_ambience, library_file

TARGET_LUFS = -13.0
DUCK_DB = -16.0

SFX_GAIN = {
    "문 쾅": -5.0, "문 삽입": -12.0, "문 닫기": -11.0, "문 삐걱": -13.0,
    "발자국": -14.0, "찻잔": -13.0, "숟가락": -14.0, "한숨": -12.0,
    "심장박동": -10.0, "헉": -11.0, "놀람 숨": -11.0, "가쁜 숨": -13.0,
    "숨죽임": -15.0, "전화벨": -12.0, "핸드폰 진동": -13.0,
    "종이 넘김": -15.0, "종이 바스락": -16.0, "천 바스락": -17.0,
    "냄비 보글": -16.0, "장판": -18.0, "상자": -16.0, "가방": -15.0,
    "테이프": -15.0, "침대 시트": -17.0, "종": -10.0, "박수": -10.0,
}
DEFAULT_SFX_GAIN = -13.0

# 장면 문장에서 자동으로 깔리는 생활음 (배경음, 아주 낮게)
BED_RULES = [
    (r"병원|간호사|병실|입원|수술", "병원 룸톤", -30.0),
    (r"비가|빗소리|빗줄기|밤비|장맛비|소나기", "비", -27.0),
    (r"시계|째깍|자정", "시계", -30.0),
    (r"냄비|국이|끓|보글|찌개", "냄비 보글", -29.0),
    (r"바람이|찬 바람|바람 소리", "바람 창", -29.0),
]
BED_LOOP_SECONDS = {"비": 40.0, "병원 룸톤": 30.0, "시계": 30.0, "냄비 보글": 25.0, "바람 창": 20.0}

# 대사 속 단어로 자동 배치하는 생활음
CUE_RULES = [
    (r"문을 열|문이 열|밖으로 나가", "문 삐걱", 0.0),
    (r"문을 닫|문이 닫|방문을", "문 닫기", 0.2),
    (r"걸어|걸음|다가왔|들어왔", "발자국", 0.3),
    (r"한숨", "한숨", 0.0),
    (r"심장|가슴이|숨이 멎", "심장박동", 0.0),
    (r"전화|문자|카톡|진동", "핸드폰 진동", 0.0),
    (r"울먹|눈물|훌쩍", "가쁜 숨", 0.4),
    (r"편지|서류|통장|영수증|사진을", "종이 넘김", 0.5),
    (r"찻잔|차를|커피", "찻잔", 0.4),
    (r"국물|숟가락", "숟가락", 0.2),
    (r"박수|축하", "박수", 0.0),
]


def _decode(src: Path, wav: Path) -> Path | None:
    if wav.exists() and wav.stat().st_size > 1000:
        return wav
    if not src.exists():
        return None
    r = run([ffmpeg_exe(), "-y", "-v", "error", "-i", str(src), "-ar", str(SR), "-ac", "1",
             "-c:a", "pcm_s16le", str(wav)], timeout=120)
    return wav if wav.exists() and wav.stat().st_size > 1000 else None


def _read_mono(path: Path) -> np.ndarray:
    path = Path(path)
    if path.suffix.lower() != ".wav":
        from .paths import CACHE_DIR
        import hashlib
        key = hashlib.sha1(str(path).encode()).hexdigest()[:16]
        cached = CACHE_DIR / "sfx_pcm" / f"{key}.wav"
        if not cached.exists() or cached.stat().st_size < 1000:
            cached.parent.mkdir(parents=True, exist_ok=True)
            run([ffmpeg_exe(), "-y", "-v", "error", "-i", str(path), "-ar", str(SR), "-ac", "1",
                 "-c:a", "pcm_s16le", str(cached)], timeout=180)
        path = cached
    sr, data = wavfile.read(path)
    if data.ndim > 1:
        data = data.mean(axis=1)
    data = data.astype(np.float32)
    if np.max(np.abs(data)) > 1.5:
        data = data / 32768.0
    if sr != SR:
        n = int(len(data) * SR / sr)
        data = np.interp(np.linspace(0, len(data) - 1, n), np.arange(len(data)), data).astype(np.float32)
    return data


def _place(track: np.ndarray, clip: np.ndarray, start: float, gain: float = 1.0) -> None:
    s = int(start * SR)
    if s < 0:
        clip = clip[-s:]
        s = 0
    if s >= len(track):
        return
    m = min(len(clip), len(track) - s)
    if m <= 0:
        return
    seg = clip[:m] * gain
    fade = min(int(0.008 * SR), m)
    if fade > 4:
        seg = seg.copy()
        seg[:fade] *= np.linspace(0, 1, fade)
        seg[-fade:] *= np.linspace(1, 0, fade)
    track[s:s + m] += seg


def _tile_loop(loop: np.ndarray, n: int, fade_sec: float = 1.5) -> np.ndarray:
    if len(loop) == 0:
        return np.zeros(n, dtype=np.float32)
    fade = int(fade_sec * SR)
    out = np.zeros(n + fade, dtype=np.float32)
    pos = 0
    first = True
    while pos < n:
        seg = loop.copy()
        if not first and len(seg) > fade:
            seg[:fade] *= np.linspace(0, 1, fade)
        m = max(0, min(len(seg), n + fade - pos))
        if m:
            out[pos:pos + m] += seg[:m]
        pos += max(1, len(loop) - fade)
        first = False
    return out[:n]


def _emotion_segments(items: list[dict], total: float) -> list[tuple[float, float, str]]:
    segs: list[tuple[float, float, str]] = []
    for it in items:
        emo = it.get("emotion") or "heal"
        if emo not in EMOTION_GAIN_DB:
            emo = "heal"
        if segs and segs[-1][2] == emo and it["start"] - segs[-1][1] < 4.0:
            segs[-1] = (segs[-1][0], it["end"], emo)
        else:
            segs.append((it["start"], it["end"], emo))
    merged: list[tuple[float, float, str]] = []
    for s, e, emo in segs:
        if e - s < 4.0 and merged:
            merged[-1] = (merged[-1][0], e, merged[-1][2])
        else:
            merged.append((s, e, emo))
    return merged


def _sentence_marks(text: str, start: float, end: float) -> list[float]:
    sents = [s for s in re.split(r"(?<=[.!?])\s+", text.strip()) if s]
    if not sents:
        return [start]
    total = sum(len(s) for s in sents) or 1
    marks, t = [], start
    for s in sents:
        marks.append(round(t, 3))
        t += (end - start) * len(s) / total
    return marks


def _make_cues(items: list[dict]) -> tuple[list[tuple[float, str, float]], list[tuple[float, float, str, float]]]:
    """(원샷 큐, 배경음 베드) 목록을 만든다."""
    oneshots: list[tuple[float, str, float]] = []
    beds: list[tuple[float, float, str, float]] = []
    for it in items:
        text = it.get("text", "")
        marks = _sentence_marks(text, it["start"], it["end"])
        used = set()
        # 1) 대본에 적힌 효과음 태그 — 문장마다 나눠 배치
        for j, name in enumerate((it.get("sfx") or [])[:2]):
            t = marks[min(j, len(marks) - 1)] - (0.22 if j == 0 else 0.05)
            oneshots.append((max(0.0, t), name, SFX_GAIN.get(name, DEFAULT_SFX_GAIN)))
            used.add(name)
        # 2) 대사 속 단어로 생활음 자동 배치 (태그와 겹치면 건너뜀)
        for pattern, name, offset in CUE_RULES:
            if name in used:
                continue
            if re.search(pattern, text):
                t = marks[0] + offset
                oneshots.append((max(0.0, t), name, SFX_GAIN.get(name, DEFAULT_SFX_GAIN) - 2))
                used.add(name)
        # 3) 배경음 베드 (장면 하나에 하나만)
        for pattern, name, gain in BED_RULES:
            if re.search(pattern, text) and is_ambience(name):
                beds.append((max(0.0, it["start"] - 0.1), it["end"] + 0.4, name, gain))
                break
        # 4) 긴 해설은 문장 사이에 아주 옅은 종이/천 소리로 숨을 넣는다
        if len(marks) >= 3 and it.get("speaker") == "narrator" and "종이 넘김" not in used:
            oneshots.append((max(0.0, marks[1] - 0.1), "종이 넘김", -24.0))
    return oneshots, beds


def _swell_curve(n: int, items: list[dict], total: float) -> np.ndarray:
    """반전·클라이맥스 직전에 BGM 이 자연스럽게 올라오는 곡선."""
    g = np.ones(n, dtype=np.float32)
    climax = [it["start"] for it in items
              if it["kind"] in ("body", "hook") and it.get("emotion") == "twist"]
    # 마지막 4번의 반전만, 서로 너무 가까우면 하나로
    picked: list[float] = []
    for t in climax[-4:]:
        if not picked or t - picked[-1] > 8:
            picked.append(t)
    for t0 in picked:
        a, b = max(0.0, t0 - 6.0), min(total, t0 + 3.5)
        i0, i1, i2 = int(a * SR), int(t0 * SR), int(b * SR)
        if i1 > i0:
            g[i0:i1] = np.maximum(g[i0:i1], np.linspace(1.0, 1.9, i1 - i0))
        if i2 > i1:
            g[i1:i2] = np.maximum(g[i1:i2], np.linspace(1.9, 1.05, i2 - i1))
    return g


def build_mix(project: dict, items: list[dict], progress=None) -> Path:
    pdir = project_dir(project["id"])
    out_dir = pdir / "audio"
    out_dir.mkdir(parents=True, exist_ok=True)
    total = float(project.get("duration") or (items[-1]["end"] + 2 if items else 10))
    n = int((total + 1.0) * SR)

    # 1) 음성
    speech = np.zeros(n, dtype=np.float32)
    for i, it in enumerate(items):
        mp3 = pdir / it["audio"]
        wav = pdir / "audio_clips" / (it["scene_id"] + ".wav")
        p = _decode(mp3, wav)
        if p:
            _place(speech, _read_mono(p), it["start"], 1.0)
        if progress and i % 10 == 0:
            progress(int(75 * i / max(1, len(items))), f"음성 배치 {i + 1}/{len(items)}")

    cues, beds = _make_cues(items)
    if progress:
        progress(78, f"생활음 {len(cues)}개 · 배경음 {len(beds)}구간 배치")

    # 2) BGM (감정 3단 + 스웰)
    bgm = np.zeros(n, dtype=np.float32)
    if project["options"].get("bgm", True):
        for start, end, emo in _emotion_segments(items, total):
            length = int((min(end, total) - start + 1.0) * SR)
            if length <= 0:
                continue
            loop = _read_mono(get_bgm(emo))
            track = _tile_loop(loop, length, 2.0)
            gain = 10 ** (EMOTION_GAIN_DB.get(emo, -26.0) / 20.0)
            s = int(start * SR)
            bgm[s:s + len(track)] += track * gain
        bgm *= _swell_curve(n, items, total)
        fade_in, fade_out = int(1.5 * SR), int(3.0 * SR)
        bgm[:fade_in] *= np.linspace(0, 1, fade_in)
        bgm[-fade_out:] *= np.linspace(1, 0, fade_out)

    # 3) 효과음 (실음원 라이브러리 우선)
    sfx = np.zeros(n, dtype=np.float32)
    if project["options"].get("sfx", True):
        for t, name, gain_db in cues:
            p = get_sfx(name)
            if not p:
                continue
            _place(sfx, _read_mono(p), t, 10 ** (gain_db / 20.0))

    # 4) 배경 생활음 (병원·빗소리·시계·냄비·바람)
    beds_track = np.zeros(n, dtype=np.float32)
    if project["options"].get("sfx", True):
        for start, end, name, gain_db in beds:
            p = library_file(name)
            if not p:
                continue
            length = max(1, int((min(end, total) - start) * SR))
            loop = _read_mono(p)
            seg = _tile_loop(loop, length, 2.0)
            if len(seg) < length:
                seg = np.pad(seg, (0, length - len(seg)))
            fade = min(int(1.0 * SR), length // 3)
            if fade > 10:
                seg[:fade] *= np.linspace(0, 1, fade)
                seg[-fade:] *= np.linspace(1, 0, fade)
            _place(beds_track, seg, start, 10 ** (gain_db / 20.0))

    # 5) 발화 덕킹 (-16dB)
    env = uniform_filter1d(np.abs(speech), size=max(1, int(0.20 * SR)))
    positive = env[env > 0]
    thr = max(0.0025, float(np.percentile(positive, 40)) if positive.size else 0.003)
    presence = (env > thr).astype(np.float32)
    presence = np.clip(uniform_filter1d(presence, size=max(1, int(0.30 * SR))) * 1.7, 0, 1)
    duck = 1.0 - (1.0 - 10 ** (DUCK_DB / 20.0)) * presence

    mix = speech + bgm * duck + sfx * (0.35 + 0.65 * duck) + beds_track * (0.55 + 0.45 * duck)

    # 6) 취침용 빗소리 엔딩 (마지막 30초, 서서히 사라짐)
    if project["options"].get("sleep_rain", False):
        rain_path = library_file("비")
        if rain_path:
            length = int(min(total, 32.0) * SR)
            loop = _read_mono(rain_path)
            seg = _tile_loop(loop, length, 2.5)
            fade_in, fade_out = int(5.0 * SR), int(12.0 * SR)
            if len(seg) > fade_in:
                seg[:fade_in] *= np.linspace(0, 1, fade_in)
            if len(seg) > fade_out:
                seg[-fade_out:] *= np.linspace(1, 0, fade_out)
            _place(mix, seg, max(0.0, total - length / SR), 10 ** (-26.0 / 20.0))
            # 마지막 15초는 음악도 함께 잦아든다
            tail = min(n, int(15 * SR))
            mix[-tail:] *= np.linspace(1, 0.55, tail)

    # 7) 마무리 페이드
    tail = min(n, int(0.8 * SR))
    mix[-tail:] *= np.linspace(1, 0, tail)
    peak = float(np.max(np.abs(mix)) or 1.0)
    if peak > 0.98:
        mix = mix * (0.98 / peak)
    pre = out_dir / "mix_pre.wav"
    wavfile.write(pre, SR, (np.clip(mix, -1, 1) * 32767).astype(np.int16))

    out = out_dir / "mix.wav"
    loudnorm(pre, out)
    try:
        pre.unlink()
    except Exception:
        pass
    return out


def loudnorm(src: Path, dst: Path) -> float:
    """2패스 loudnorm → -13.0 LUFS. 실패하면 1패스."""
    target = f"I={TARGET_LUFS}:TP=-1.5:LRA=11"
    measured = None
    r = run([ffmpeg_exe(), "-hide_banner", "-i", str(src), "-af", target + ":print_format=json",
             "-f", "null", "-"], timeout=900)
    m = re.search(r"\{[^{}]*\"input_i\"[^{}]*\}", r.stderr or "", re.S)
    if m:
        try:
            measured = json.loads(m.group(0))
        except Exception:
            measured = None
    if measured and float(measured.get("input_i", -99)) > -70:
        af = (f"loudnorm=I={TARGET_LUFS}:TP=-1.5:LRA=11:"
              f"measured_I={measured['input_i']}:measured_TP={measured['input_tp']}:"
              f"measured_LRA={measured['input_lra']}:measured_thresh={measured['input_thresh']}:"
              f"offset={measured.get('target_offset', 0)}:linear=true")
    else:
        af = target
    run([ffmpeg_exe(), "-y", "-v", "error", "-i", str(src), "-af", af,
         "-ar", str(SR), "-ac", "2", "-c:a", "pcm_s16le", str(dst)], timeout=900)
    if not dst.exists() or dst.stat().st_size < 1000:
        run([ffmpeg_exe(), "-y", "-v", "error", "-i", str(src), "-ar", str(SR), "-ac", "2",
             "-c:a", "pcm_s16le", str(dst)], timeout=900)
    try:
        return float((measured or {}).get("input_i", 0))
    except Exception:
        return 0.0
