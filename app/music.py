"""감정별 3단 BGM 자체 합성 (갈등 / 반전 / 치유). 외부 음원 없이 numpy 로 만든다."""
from __future__ import annotations

import hashlib
import math
from pathlib import Path

import numpy as np
from scipy import signal
from scipy.io import wavfile

from .paths import CACHE_DIR

SR = 48000
LOOP_SECONDS = 32.0

# 감정별 화성 진행 (MIDI 노트)
PROGRESSIONS = {
    "conflict": {
        "tempo": 56,
        "chords": [[45, 48, 52], [41, 45, 48], [38, 41, 45], [40, 44, 47]],  # Am F Dm E
        "roots": [33, 29, 26, 28],
        "scale": [57, 60, 62, 64, 67, 69, 72],
        "mood": "minor",
    },
    "twist": {
        "tempo": 72,
        "chords": [[50, 53, 57], [46, 50, 53], [43, 46, 50], [45, 49, 52]],  # Dm Bb Gm A
        "roots": [38, 34, 31, 33],
        "scale": [62, 65, 67, 69, 72, 74, 77],
        "mood": "rising",
    },
    "heal": {
        "tempo": 60,
        "chords": [[41, 45, 48, 52], [36, 40, 43], [43, 47, 50], [45, 48, 52, 55]],  # Fmaj7 C G Am7
        "roots": [29, 24, 31, 33],
        "scale": [65, 69, 72, 74, 77, 81, 84],
        "mood": "warm",
    },
}

EMOTION_GAIN_DB = {"conflict": -28.0, "twist": -25.0, "heal": -26.0}


def midi(m: int) -> float:
    return 440.0 * (2 ** ((m - 69) / 12))


def _adsr(n: int, attack: float, decay: float, sustain: float, release: float, sr: int = SR) -> np.ndarray:
    a = max(1, int(attack * sr))
    d = max(1, int(decay * sr))
    r = max(1, int(release * sr))
    s = max(1, n - a - d - r)
    env = np.concatenate([
        np.linspace(0, 1, a, endpoint=False),
        np.linspace(1, sustain, d, endpoint=False),
        np.full(s, sustain),
        np.linspace(sustain, 0, r),
    ])
    if len(env) < n:
        env = np.pad(env, (0, n - len(env)))
    return env[:n]


def piano(freq: float, dur: float, amp: float = 0.5, detune: float = 0.0) -> np.ndarray:
    n = int(dur * SR)
    t = np.arange(n) / SR
    out = np.zeros(n)
    partials = [(1, 1.0, 1.0), (2, 0.42, 0.7), (3, 0.2, 0.55), (4, 0.1, 0.42), (5, 0.05, 0.3)]
    for mult, a, dk in partials:
        f = freq * mult * (1 + detune)
        if f > 12000:
            continue
        env = np.exp(-t * (2.2 / max(0.2, dur)) * (1 / dk))
        out += a * env * np.sin(2 * np.pi * f * t + np.random.rand() * 0.1)
    click = np.exp(-t * 60) * 0.06 * np.random.randn(n)
    out = out + click
    env = _adsr(n, 0.004, 0.01, 0.85, min(0.5, dur * 0.3))
    return amp * out * env


def pad(freqs: list[float], dur: float, amp: float = 0.25) -> np.ndarray:
    n = int(dur * SR)
    t = np.arange(n) / SR
    out = np.zeros(n)
    for i, f in enumerate(freqs):
        for det in (-0.15, 0.0, 0.18):
            out += (1 / (i + 1)) * np.sin(2 * np.pi * (f * (1 + det / 100)) * t + i * 0.7)
    env = _adsr(n, 1.6, 1.0, 0.8, 2.0)
    trem = 1 + 0.04 * np.sin(2 * np.pi * 0.13 * t)
    return amp * (out / max(1, len(freqs) * 3)) * env * trem


def bass(root_midi: int, dur: float, amp: float = 0.4) -> np.ndarray:
    n = int(dur * SR)
    t = np.arange(n) / SR
    f = midi(root_midi)
    out = 0.7 * np.sin(2 * np.pi * f * t) + 0.25 * np.sin(2 * np.pi * 2 * f * t)
    out += 0.12 * np.sin(2 * np.pi * 3 * f * t)
    env = _adsr(n, 0.02, 0.4, 0.7, 0.8)
    return amp * out * env


def soft_kick(dur: float = 0.5, amp: float = 0.25) -> np.ndarray:
    n = int(dur * SR)
    t = np.arange(n) / SR
    f = 70 * np.exp(-t * 9) + 42
    out = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 7)
    return amp * out


def reverb(x: np.ndarray, amount: float = 0.28, decay: float = 1.8) -> np.ndarray:
    n = int(decay * SR)
    rng = np.random.default_rng(11)
    ir = rng.standard_normal(n) * np.exp(-np.arange(n) / (SR * decay / 3.2))
    ir[: int(0.012 * SR)] = 0
    ir /= np.max(np.abs(ir)) + 1e-9
    wet = signal.fftconvolve(x, ir, mode="full")[: len(x)]
    return (1 - amount) * x + amount * wet


def _lowpass(x: np.ndarray, cutoff: float = 5200) -> np.ndarray:
    b, a = signal.butter(2, cutoff / (SR / 2), btype="low")
    return signal.lfilter(b, a, x)


def compose(emotion: str, seed: int = 3) -> np.ndarray:
    spec = PROGRESSIONS.get(emotion, PROGRESSIONS["heal"])
    rng = np.random.default_rng(seed + hash(emotion) % 1000)
    n = int(LOOP_SECONDS * SR)
    mix = np.zeros(n)
    tempo = spec["tempo"]
    beat = 60.0 / tempo
    n_ch = len(spec["chords"])
    ch_len = LOOP_SECONDS / n_ch
    mood = spec["mood"]

    for ci, chord in enumerate(spec["chords"]):
        start = int(ci * ch_len * SR)
        length = int(ch_len * SR)
        freqs = [midi(m) for m in chord]
        seg = np.zeros(length)
        # 패드
        seg += pad(freqs, ch_len, 0.34 if emotion != "heal" else 0.30)[:length]
        # 베이스
        seg += bass(spec["roots"][ci], ch_len, 0.33)[:length]
        # 피아노/아르페지오
        if emotion == "conflict":
            for k, note in enumerate([chord[0] + 12, chord[1] + 12, chord[2] + 12]):
                at = beat * (1.5 + k * 1.6) + rng.uniform(-0.02, 0.02)
                if at + 2.2 < ch_len:
                    p = piano(midi(note), 2.6, 0.22, detune=rng.uniform(-0.002, 0.002))
                    s = int(at * SR)
                    seg[s:s + len(p)] += p[: length - s] if s + len(p) > length else p
            if ci % 2 == 0:
                k = soft_kick(0.7, 0.16)
                seg[: len(k)] += k
        elif emotion == "twist":
            # 상승 아르페지오 8분음표
            steps = int(ch_len / (beat / 2))
            for st in range(steps):
                note = chord[st % len(chord)] + 12 * (1 + (st // len(chord)) % 2)
                at = st * beat / 2
                p = piano(midi(note), 0.9, 0.16, detune=rng.uniform(-0.003, 0.003))
                s = int(at * SR)
                if s + len(p) <= length:
                    seg[s:s + len(p)] += p
            # 펄스 베이스
            for st in range(int(ch_len / beat)):
                s = int(st * beat * SR)
                b = bass(spec["roots"][ci], beat * 0.85, 0.22)
                if s + len(b) <= length:
                    seg[s:s + len(b)] += b
        else:  # heal
            notes = [chord[0] + 12, chord[1] + 12, chord[2] + 12, chord[3] + 12 if len(chord) > 3 else chord[0] + 24]
            order = [0, 1, 2, 3, 2, 1, 0, 2]
            for st, idx in enumerate(order):
                at = st * beat * 0.9
                note = notes[idx % len(notes)]
                p = piano(midi(note), 3.0, 0.18, detune=0.0)
                s = int(at * SR)
                if s + len(p) <= length:
                    seg[s:s + len(p)] += p
            # 높은 종소리 한 번
            bell = piano(midi(spec["scale"][-1] + 12), 4.0, 0.06)
            s = int(ch_len * 0.55 * SR)
            if s + len(bell) <= length:
                seg[s:s + len(bell)] += bell

        mix[start:start + length] += seg[:length]

    # 감정별 질감
    t = np.arange(n) / SR
    if emotion == "conflict":
        rumble = _lowpass(np.random.default_rng(5).standard_normal(n), 120) * 0.03
        mix += rumble
    elif emotion == "twist":
        mix += 0.012 * np.sin(2 * np.pi * 0.5 * t) * np.sin(2 * np.pi * midi(45) * t)
    else:
        air = _lowpass(np.random.default_rng(9).standard_normal(n), 900) * 0.012
        mix += air

    mix = _lowpass(mix, 6200)
    mix = reverb(mix, 0.30 if mood != "warm" else 0.34, 2.2)
    # 루프 이음새 완화
    fade = int(0.8 * SR)
    mix[:fade] *= np.linspace(0, 1, fade)
    mix[-fade:] *= np.linspace(1, 0, fade)
    mix = np.tanh(mix * 1.1) * 0.85
    peak = np.max(np.abs(mix)) or 1.0
    mix = mix / peak * 0.55
    return mix.astype(np.float32)


def stereo(x: np.ndarray) -> np.ndarray:
    delay = int(0.011 * SR)  # 11ms
    r = np.concatenate([np.zeros(delay, dtype=x.dtype), x[:-delay]]) * 0.94
    l = x
    out = np.stack([l, r], axis=1)
    return out


def get_bgm(emotion: str) -> Path:
    emotion = emotion if emotion in PROGRESSIONS else "heal"
    out_dir = CACHE_DIR / "music"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"bgm_{emotion}_v1.wav"
    if path.exists() and path.stat().st_size > 1000:
        return path
    mono = compose(emotion)
    wavfile.write(path, SR, (stereo(mono) * 32767).astype(np.int16))
    return path
