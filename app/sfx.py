"""생활 효과음 자체 합성 (외부 음원 없이)."""
from __future__ import annotations

from pathlib import Path

import numpy as np
from scipy import signal
from scipy.io import wavfile

from .paths import CACHE_DIR

SR = 48000

# ── 내장 고음질 실음원 라이브러리 (sfx_library/) ─────────────────────────
LIBRARY = {
    "문 쾅": "door_slam.mp3",
    "문 닫기": "door_close.mp3",
    "문 삽입": "door_close.mp3",
    "문 삐걱": "door_creak.mp3",
    "발자국": "footsteps.mp3",
    "비": "rain_night.mp3",
    "시계": "clock_tick.mp3",
    "찻잔": "cup_clink.mp3",
    "숟가락": "spoon_clink.mp3",
    "종이 넘김": "page_flip.mp3",
    "종이 바스락": "paper_pages.mp3",
    "천 바스락": "cloth_rustle.mp3",
    "가쁜 숨": "breath_pant.mp3",
    "헉": "breath_gasp.mp3",
    "놀람 숨": "breath_gasp.mp3",
    "숨죽임": "breath_huff.mp3",
    "한숨": "sigh.mp3",
    "심장박동": "heartbeat.mp3",
    "병원 룸톤": "hospital_room.mp3",
    "냄비 보글": "pot_simmer.mp3",
    "핸드폰 진동": "phone_vibrate.mp3",
    "바람": "wind_howl.mp3",
    "바람 창": "wind_window.mp3",
    "침대 시트": "bed_rustle.mp3",
    "장판": "floor_squeak.mp3",
    "테이프": "tape_peel.mp3",
    "가방": "bag_rustle.mp3",
    "상자": "cardboard.mp3",
}

AMBIENCE = {
    "비": "rain_night.mp3",
    "병원 룸톤": "hospital_room.mp3",
    "시계": "clock_tick.mp3",
    "냄비 보글": "pot_simmer.mp3",
    "바람": "wind_howl.mp3",
    "바람 창": "wind_window.mp3",
}

LIB_DIR = Path(__file__).resolve().parent.parent / "sfx_library"


def library_file(name: str) -> Path | None:
    fn = LIBRARY.get(name)
    if not fn:
        return None
    p = LIB_DIR / fn
    return p if p.exists() else None


def is_ambience(name: str) -> bool:
    return name in AMBIENCE and (LIB_DIR / AMBIENCE[name]).exists()


def all_tags() -> list[str]:
    tags = set(EFFECTS.keys()) | set(LIBRARY.keys())
    return sorted(tags)




def _noise(n: int, seed: int = 0) -> np.ndarray:
    return np.random.default_rng(seed).standard_normal(n)


def _bp(x: np.ndarray, lo: float, hi: float, order: int = 2) -> np.ndarray:
    b, a = signal.butter(order, [max(20, lo) / (SR / 2), min(SR / 2 - 100, hi) / (SR / 2)], btype="band")
    return signal.lfilter(b, a, x)


def _lp(x: np.ndarray, f: float) -> np.ndarray:
    b, a = signal.butter(2, f / (SR / 2), btype="low")
    return signal.lfilter(b, a, x)


def _hp(x: np.ndarray, f: float) -> np.ndarray:
    b, a = signal.butter(2, f / (SR / 2), btype="high")
    return signal.lfilter(b, a, x)


def _env(n: int, a: float, d: float) -> np.ndarray:
    na, nd = max(1, int(a * SR)), max(1, int(d * SR))
    e = np.concatenate([np.linspace(0, 1, na), np.exp(-np.linspace(0, 5, nd))])
    if len(e) < n:
        e = np.pad(e, (0, n - len(e)))
    return e[:n]


def _norm(x: np.ndarray, peak: float = 0.8) -> np.ndarray:
    m = np.max(np.abs(x)) or 1.0
    return x / m * peak


# ── 개별 효과음 ───────────────────────────────────────────────────────────
def door_slam() -> np.ndarray:
    dur = 1.4
    n = int(dur * SR)
    t = np.arange(n) / SR
    thump = np.sin(2 * np.pi * np.cumsum(60 * np.exp(-t * 8) + 38) / SR) * np.exp(-t * 5)
    burst = _lp(_noise(n, 3) * np.exp(-t * 18), 1800) * 0.7
    rattle = _bp(_noise(n, 5) * np.exp(-t * 3), 180, 900) * 0.25
    return _norm(thump * 0.9 + burst + rattle)


def door_close() -> np.ndarray:
    dur = 0.9
    n = int(dur * SR)
    t = np.arange(n) / SR
    thump = np.sin(2 * np.pi * np.cumsum(75 * np.exp(-t * 10) + 45) / SR) * np.exp(-t * 8)
    click = _hp(_noise(n, 7) * np.exp(-t * 60), 2200) * 0.25
    return _norm(thump + click)


def door_creak() -> np.ndarray:
    dur = 1.8
    n = int(dur * SR)
    t = np.arange(n) / SR
    base = 240 + 120 * np.sin(2 * np.pi * 0.7 * t) + 40 * np.sin(2 * np.pi * 5.3 * t)
    tone = np.sin(2 * np.pi * np.cumsum(base) / SR)
    noise = _bp(_noise(n, 11), 500, 2500)
    env = _env(n, 0.25, 1.2)
    return _norm((tone * 0.35 + noise * 0.25) * env)


def teacup() -> np.ndarray:
    dur = 1.6
    n = int(dur * SR)
    t = np.arange(n) / SR
    out = np.zeros(n)
    for f, a, dk in ((1850, 0.5, 5), (2780, 0.35, 7), (4100, 0.2, 9), (6300, 0.1, 12)):
        out += a * np.sin(2 * np.pi * f * t) * np.exp(-t * dk)
    out += _hp(_noise(n, 13) * np.exp(-t * 80), 3000) * 0.15
    return _norm(out, 0.6)


def spoon() -> np.ndarray:
    dur = 0.7
    n = int(dur * SR)
    t = np.arange(n) / SR
    out = sum(a * np.sin(2 * np.pi * f * t) * np.exp(-t * dk)
              for f, a, dk in ((2400, 0.4, 9), (3600, 0.25, 12), (5100, 0.12, 16)))
    return _norm(out, 0.55)


def sigh() -> np.ndarray:
    dur = 2.2
    n = int(dur * SR)
    t = np.arange(n) / SR
    breath = _bp(_noise(n, 17), 250, 1400)
    env = _env(n, 0.35, 1.6)
    vib = 1 + 0.15 * np.sin(2 * np.pi * 3.2 * t)
    return _norm(breath * env * vib, 0.35)


def heartbeat() -> np.ndarray:
    dur = 2.4
    n = int(dur * SR)
    out = np.zeros(n)
    for start, amp in ((0.0, 1.0), (0.32, 0.7), (1.15, 0.9), (1.47, 0.6)):
        dur2 = 0.55
        m = int(dur2 * SR)
        tt = np.arange(m) / SR
        f = 62 * np.exp(-tt * 6) + 34
        b = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-tt * 9) * amp
        s = int(start * SR)
        if s + m <= n:
            out[s:s + m] += b
    return _norm(out, 0.85)


def footsteps() -> np.ndarray:
    dur = 3.0
    n = int(dur * SR)
    out = np.zeros(n)
    for i, start in enumerate((0.0, 0.62, 1.24, 1.86, 2.48)):
        m = int(0.35 * SR)
        tt = np.arange(m) / SR
        heel = np.sin(2 * np.pi * np.cumsum(90 * np.exp(-tt * 14) + 45) / SR) * np.exp(-tt * 16)
        scuff = _bp(_noise(m, 19 + i) * np.exp(-tt * 20), 400, 2200) * 0.35
        s = int(start * SR)
        out[s:s + m] += _norm(heel + scuff, 0.5)
    return _norm(out, 0.7)


def rain() -> np.ndarray:
    dur = 4.0
    n = int(dur * SR)
    t = np.arange(n) / SR
    body = _bp(_noise(n, 23), 400, 8000) * 0.5
    drops = np.zeros(n)
    rng = np.random.default_rng(29)
    for _ in range(90):
        s = rng.integers(0, n - 2400)
        m = 2400
        tt = np.arange(m) / SR
        f = rng.uniform(1200, 4200)
        drops[s:s + m] += np.sin(2 * np.pi * f * tt) * np.exp(-tt * 60) * rng.uniform(0.05, 0.18)
    env = np.minimum(1, np.minimum(t / 0.4, (dur - t) / 0.4))
    return _norm((body + drops) * env, 0.5)


def wind() -> np.ndarray:
    dur = 5.0
    n = int(dur * SR)
    t = np.arange(n) / SR
    x = _lp(_noise(n, 31), 800) * (0.6 + 0.4 * np.sin(2 * np.pi * 0.18 * t + 1.2))
    x += _bp(_noise(n, 37), 300, 1200) * 0.3 * (0.5 + 0.5 * np.sin(2 * np.pi * 0.09 * t))
    env = np.minimum(1, np.minimum(t / 1.2, (dur - t) / 1.5))
    return _norm(x * env, 0.45)


def birds() -> np.ndarray:
    dur = 3.5
    n = int(dur * SR)
    out = np.zeros(n)
    rng = np.random.default_rng(41)
    for _ in range(7):
        s = rng.integers(0, n - int(0.4 * SR))
        m = int(0.25 * SR)
        tt = np.arange(m) / SR
        f0 = rng.uniform(2300, 3600)
        f = f0 + 600 * np.sin(2 * np.pi * rng.uniform(8, 14) * tt)
        out[s:s + m] += np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-tt * 20) * 0.25
    return _norm(out, 0.4)


def bell() -> np.ndarray:
    dur = 3.0
    n = int(dur * SR)
    t = np.arange(n) / SR
    out = np.zeros(n)
    for f, a, dk in ((523, 0.5, 1.6), (1046, 0.3, 2.2), (1568, 0.2, 2.8), (2093, 0.1, 3.4)):
        out += a * np.sin(2 * np.pi * f * t) * np.exp(-t * dk)
    return _norm(out, 0.5)


def phone_ring() -> np.ndarray:
    dur = 4.0
    n = int(dur * SR)
    t = np.arange(n) / SR
    sig = (np.sin(2 * np.pi * 440 * t) + np.sin(2 * np.pi * 480 * t)) * 0.5
    gate = ((t % 2.0) < 1.0).astype(float)
    return _norm(sig * gate * 0.5, 0.5)


def paper() -> np.ndarray:
    dur = 1.6
    n = int(dur * SR)
    t = np.arange(n) / SR
    x = _hp(_noise(n, 43), 2500) * (0.5 + 0.5 * np.sin(2 * np.pi * 7 * t) ** 2)
    x *= _env(n, 0.1, 1.2)
    return _norm(x, 0.38)


def fridge_hum() -> np.ndarray:
    dur = 4.0
    n = int(dur * SR)
    t = np.arange(n) / SR
    x = 0.35 * np.sin(2 * np.pi * 60 * t) + 0.18 * np.sin(2 * np.pi * 120 * t)
    x += _lp(_noise(n, 47), 300) * 0.15
    env = np.minimum(1, np.minimum(t / 0.8, (dur - t) / 0.8))
    return _norm(x * env, 0.25)


def lid_open() -> np.ndarray:
    dur = 1.0
    n = int(dur * SR)
    t = np.arange(n) / SR
    pop = np.sin(2 * np.pi * 180 * t) * np.exp(-t * 30) * 0.6
    suck = _bp(_noise(n, 53) * np.exp(-t * 6), 300, 2000) * 0.3
    return _norm(pop + suck, 0.6)


def clap() -> np.ndarray:
    dur = 1.6
    n = int(dur * SR)
    out = np.zeros(n)
    rng = np.random.default_rng(59)
    for _ in range(14):
        s = rng.integers(0, n - 4800)
        m = 4800
        tt = np.arange(m) / SR
        out[s:s + m] += _bp(_noise(m, int(rng.integers(0, 999))), 700, 5000) * np.exp(-tt * 45)
    return _norm(out, 0.5)


def crying() -> np.ndarray:
    dur = 4.0
    n = int(dur * SR)
    t = np.arange(n) / SR
    f = 320 + 40 * np.sin(2 * np.pi * 0.7 * t) - 30 * np.sin(2 * np.pi * 2.1 * t)
    voice = np.sin(2 * np.pi * np.cumsum(f) / SR)
    voice += 0.4 * np.sin(2 * np.pi * np.cumsum(f * 2) / SR)
    formant = _bp(_noise(n, 61), 400, 1800) * 0.5
    amp = (0.5 + 0.5 * np.sin(2 * np.pi * 0.45 * t)) ** 2
    env = np.minimum(1, np.minimum(t / 0.5, (dur - t) / 0.8))
    return _norm((voice * 0.5 + formant) * amp * env, 0.4)


EFFECTS = {
    "문 쾅": door_slam,
    "문 삽입": door_close,
    "문 삐걱": door_creak,
    "찻잔": teacup,
    "숟가락": spoon,
    "한숨": sigh,
    "심장박동": heartbeat,
    "발자국": footsteps,
    "비": rain,
    "바람": wind,
    "새소리": birds,
    "종": bell,
    "전화벨": phone_ring,
    "종이 바스락": paper,
    "냉장고 웅웅": fridge_hum,
    "뚜껑 열림": lid_open,
    "박수": clap,
    "울음": crying,
}


def get_sfx(name: str) -> Path | None:
    name = (name or "").strip()
    lib = library_file(name)
    if lib:
        return lib
    if name not in EFFECTS:
        return None
    out_dir = CACHE_DIR / "sfx"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"sfx_{abs(hash(name)) % 99999}_{name.replace(' ', '')}.wav"
    if path.exists() and path.stat().st_size > 1000:
        return path
    data = EFFECTS[name]()
    wavfile.write(path, SR, (np.clip(data, -1, 1) * 32767).astype(np.int16))
    return path


def all_names() -> list[str]:
    return all_tags()
