"""아바타·카드·썸네일·입자·배지 등 이미지 그래픽."""
from __future__ import annotations

import math
import random
import re
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from .paths import CACHE_DIR, FONT_DIR

GOLD = (232, 190, 92)
CREAM = (247, 240, 226)
RED = (196, 42, 38)
ONAIR = (232, 64, 52)
GREEN = (124, 255, 107)
YELLOW = (255, 225, 77)

_FONT_CANDIDATES = [
    FONT_DIR / "GmarketSansBold.ttf",
    FONT_DIR / "NanumSquareRoundEB.ttf",
    Path("/System/Library/Fonts/AppleSDGothicNeo.ttc"),
    Path("/System/Library/Fonts/Supplemental/AppleGothic.ttf"),
]
_ROUND_CANDIDATES = [
    FONT_DIR / "NanumSquareRoundEB.ttf",
    FONT_DIR / "NanumSquareRoundB.ttf",
    FONT_DIR / "GmarketSansBold.ttf",
    Path("/System/Library/Fonts/AppleSDGothicNeo.ttc"),
]


def font_path(round_style: bool = False) -> Path:
    for p in (_ROUND_CANDIDATES if round_style else _FONT_CANDIDATES):
        if p.exists():
            return p
    raise FileNotFoundError("한글 폰트를 찾지 못했습니다. assets/fonts 폴더를 확인하세요.")


def font(size: int, round_style: bool = False) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(font_path(round_style)), max(8, int(size)))


def fit_font(draw: ImageDraw.ImageDraw, text: str, max_width: int, start: int,
             min_size: int = 24, round_style: bool = True) -> ImageFont.FreeTypeFont:
    size = start
    while size > min_size:
        f = font(size, round_style)
        if draw.textlength(text, font=f) <= max_width:
            return f
        size -= 2
    return font(min_size, round_style)


def text_outlined(draw: ImageDraw.ImageDraw, xy, text: str, f: ImageFont.FreeTypeFont,
                  fill=(255, 255, 255), outline=(0, 0, 0), width: int = 4,
                  anchor: str = "la", shadow: bool = True) -> None:
    x, y = xy
    if shadow:
        draw.text((x + width * 0.6, y + width * 0.8), text, font=f, fill=(0, 0, 0, 150), anchor=anchor)
    for dx in range(-width, width + 1, max(1, width // 2)):
        for dy in range(-width, width + 1, max(1, width // 2)):
            if dx or dy:
                draw.text((x + dx, y + dy), text, font=f, fill=outline, anchor=anchor)
    draw.text((x, y), text, font=f, fill=fill, anchor=anchor)


# ── 아바타 ────────────────────────────────────────────────────────────────
def _on_air_glow(S: int, alpha: int = 54, width_ratio: float = 0.036) -> Image.Image:
    """원형 테두리 바깥으로 번지는 은은한 붉은 ON-AIR 빛."""
    glow = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    gd.ellipse([S * 0.018, S * 0.018, S * 0.982, S * 0.982],
               outline=ONAIR + (max(0, min(255, alpha)),), width=max(2, int(S * width_ratio)))
    return glow.filter(ImageFilter.GaussianBlur(max(1.0, S * 0.016)))


def make_avatar(kind: str = "female", size: int = 420) -> Image.Image:
    """우측 하단 원형 진행자 아바타(기본 내장)."""
    ss = 2
    S = size * ss
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    # 배경 원 + 금테
    for i in range(6, 0, -1):
        r = S // 2 - i * (S // 90)
        d.ellipse([S / 2 - r, S / 2 - r, S / 2 + r, S / 2 + r], fill=(28, 24, 20, 255))
    d.ellipse([S * 0.035, S * 0.035, S * 0.965, S * 0.965], outline=GOLD + (235,), width=int(S * 0.018))
    d.ellipse([S * 0.075, S * 0.075, S * 0.925, S * 0.925], fill=(44, 34, 28, 255))

    # 어깨
    shoulder = (74, 58, 46, 255) if kind == "male" else (86, 52, 58, 255)
    d.ellipse([S * 0.16, S * 0.70, S * 0.84, S * 1.12], fill=shoulder)
    # 목
    d.rounded_rectangle([S * 0.42, S * 0.60, S * 0.58, S * 0.76], radius=S * 0.06, fill=(233, 197, 170, 255))
    # 얼굴
    face = (242, 208, 180, 255)
    d.ellipse([S * 0.30, S * 0.24, S * 0.70, S * 0.70], fill=face)
    # 귀
    d.ellipse([S * 0.275, S * 0.42, S * 0.325, S * 0.52], fill=face)
    d.ellipse([S * 0.675, S * 0.42, S * 0.725, S * 0.52], fill=face)

    # 머리
    if kind == "male":
        d.ellipse([S * 0.285, S * 0.185, S * 0.715, S * 0.48], fill=(52, 44, 40, 255))
        d.rectangle([S * 0.285, S * 0.33, S * 0.36, S * 0.45], fill=(52, 44, 40, 255))
        d.rectangle([S * 0.64, S * 0.33, S * 0.715, S * 0.45], fill=(52, 44, 40, 255))
        # 안경
        d.ellipse([S * 0.35, S * 0.42, S * 0.455, S * 0.50], outline=(60, 48, 40, 255), width=int(S * 0.009))
        d.ellipse([S * 0.545, S * 0.42, S * 0.65, S * 0.50], outline=(60, 48, 40, 255), width=int(S * 0.009))
        d.line([S * 0.455, S * 0.455, S * 0.545, S * 0.455], fill=(60, 48, 40, 255), width=int(S * 0.008))
    else:
        d.ellipse([S * 0.265, S * 0.175, S * 0.735, S * 0.52], fill=(58, 42, 36, 255))
        d.ellipse([S * 0.255, S * 0.30, S * 0.355, S * 0.62], fill=(58, 42, 36, 255))
        d.ellipse([S * 0.645, S * 0.30, S * 0.745, S * 0.62], fill=(58, 42, 36, 255))
        d.ellipse([S * 0.30, S * 0.24, S * 0.70, S * 0.34], fill=(58, 42, 36, 255))
        # 귀걸이
        d.ellipse([S * 0.292, S * 0.535, S * 0.315, S * 0.565], fill=GOLD + (255,))

    # 눈썹·눈·코·입
    d.line([S * 0.375, S * 0.435, S * 0.445, S * 0.428], fill=(70, 52, 42, 255), width=int(S * 0.012))
    d.line([S * 0.555, S * 0.428, S * 0.625, S * 0.435], fill=(70, 52, 42, 255), width=int(S * 0.012))
    for cx in (0.408, 0.592):
        d.ellipse([S * (cx - 0.026), S * 0.462, S * (cx + 0.026), S * 0.498], fill=(250, 250, 248, 255))
        d.ellipse([S * (cx - 0.012), S * 0.472, S * (cx + 0.012), S * 0.492], fill=(52, 40, 34, 255))
    d.line([S * 0.50, S * 0.50, S * 0.487, S * 0.555], fill=(210, 168, 142, 255), width=int(S * 0.008))
    d.arc([S * 0.44, S * 0.555, S * 0.56, S * 0.615], start=10, end=170, fill=(150, 78, 70, 255), width=int(S * 0.012))
    # 볼
    blush = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    bd = ImageDraw.Draw(blush)
    bd.ellipse([S * 0.345, S * 0.545, S * 0.415, S * 0.585], fill=(226, 130, 120, 60))
    bd.ellipse([S * 0.585, S * 0.545, S * 0.655, S * 0.585], fill=(226, 130, 120, 60))
    img = Image.alpha_composite(img, blush.filter(ImageFilter.GaussianBlur(S * 0.006)))

    # 원형으로 잘라내 테두리 밖 어깨가 삐져나오지 않게
    mask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(mask).ellipse([2, 2, S - 3, S - 3], fill=255)
    out = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    out.paste(img, (0, 0), mask)
    # ON-AIR 글로우 → 금테를 다시 선명하게
    out = Image.alpha_composite(out, _on_air_glow(S))
    d2 = ImageDraw.Draw(out)
    d2.ellipse([S * 0.035, S * 0.035, S * 0.965, S * 0.965], outline=GOLD + (235,), width=int(S * 0.018))
    return out.resize((size, size), Image.LANCZOS)


def avatar_from_photo(path: Path, size: int = 420, on_air: bool = True) -> Image.Image:
    """사진을 원형으로 잘라 금테(+ON-AIR 글로우)를 두른 진행자 아바타로."""
    ss = 2
    S = size * ss
    im = Image.open(path).convert("RGB")
    w, h = im.size
    s = min(w, h)
    # 얼굴이 위쪽에 오도록 25% 지점 기준으로 크롭
    top = max(0, min(h - s, int((h - s) * 0.25)))
    im = im.crop(((w - s) // 2, top, (w + s) // 2, top + s)).resize((S, S), Image.LANCZOS)
    mask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(mask).ellipse([0, 0, S, S], fill=255)
    out = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    out.paste(im, (0, 0), mask)
    if on_air:
        out = Image.alpha_composite(out, _on_air_glow(S))
    d = ImageDraw.Draw(out)
    d.ellipse([S * 0.018, S * 0.018, S * 0.982, S * 0.982], outline=GOLD + (240,),
              width=max(3, int(S * 0.011)))
    return out.resize((size, size), Image.LANCZOS)


# ── LIVE 배지 ─────────────────────────────────────────────────────────────
def live_badge(w: int, pulse: float = 1.0, label: str = "LIVE") -> Image.Image:
    """라디오 스튜디오 느낌의 `● LIVE` 알약 배지.

    진한 반투명 어두운 배경 + 붉은 원형 점(은은한 글로우) + 선명한 흰색 글씨.
    `pulse` 0~1 로 붉은 점의 숨쉬는 세기를 조절한다(0.8초 주기 프레임용).
    """
    ss = 2
    fs = max(16, int(round(w * 0.0215))) * ss
    pad = int(fs * 0.62)
    dot_r = int(fs * 0.34)
    gap = int(fs * 0.28)
    f = font(fs, round_style=True)
    tw = int(f.getlength(label))
    bw = pad * 2 + dot_r * 2 + gap + tw
    bh = int(fs * 1.62)
    img = Image.new("RGBA", (bw, bh), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([0, 0, bw - 1, bh - 1], radius=bh // 2, fill=(15, 13, 13, 216),
                        outline=(255, 255, 255, 58), width=max(2, fs // 13))
    cx, cy = pad + dot_r, bh / 2
    pulse = max(0.0, min(1.0, float(pulse)))
    # 붉은 점 글로우 — pulse 가 클수록 번진다
    glow = Image.new("RGBA", (bw, bh), (0, 0, 0, 0))
    gr = dot_r * (1.55 + 0.35 * pulse)
    ImageDraw.Draw(glow).ellipse([cx - gr, cy - gr, cx + gr, cy + gr],
                                 fill=ONAIR + (int(60 + 90 * pulse),))
    img = Image.alpha_composite(img, glow.filter(ImageFilter.GaussianBlur(max(1.0, dot_r * 0.5))))
    d = ImageDraw.Draw(img)
    rr = dot_r * (0.92 + 0.08 * pulse)
    d.ellipse([cx - rr, cy - rr, cx + rr, cy + rr], fill=ONAIR + (255,))
    # 점 하이라이트
    d.ellipse([cx - rr * 0.45, cy - rr * 0.62, cx - rr * 0.02, cy - rr * 0.18],
              fill=(255, 205, 198, 140))
    d.text((pad + dot_r * 2 + gap, bh / 2 + fs * 0.02), label, font=f, fill=(255, 255, 255, 255),
           anchor="lm")
    return img.resize((max(1, bw // ss), max(1, bh // ss)), Image.LANCZOS)


def live_badge_frames(w: int, fps: int = 25, period: float = 0.8) -> tuple[Path, int]:
    """0.8초 주기로 붉은 점이 은은하게 깜빡이는 `● LIVE` 배지 PNG 시퀀스."""
    n = max(6, int(round(period * fps)))
    out = CACHE_DIR / "live_badge" / f"lb_{int(w)}_{int(fps)}_{n}"
    if (out / "done").exists():
        return out, n
    out.mkdir(parents=True, exist_ok=True)
    for i in range(n):
        pulse = 0.5 - 0.5 * math.cos(math.tau * i / n)
        live_badge(w, pulse).save(out / f"l{i:03d}.png")
    (out / "done").write_text("ok", encoding="utf-8")
    return out, n


# ── 진행자 모션(정지 사진처럼 보이지 않게) ────────────────────────────────
def _hash01(i: int, salt: int = 0) -> float:
    """0~1 고정 난수 — 같은 프레임은 언제나 같은 리듬이 되도록(캐시 재사용)."""
    x = (i * 1103515245 + 12345 + salt * 7919) & 0x7FFFFFFF
    return x / 0x7FFFFFFF


def _smooth(x: float) -> float:
    x = max(0.0, min(1.0, x))
    return x * x * (3.0 - 2.0 * x)


# 6초 한 주기 안에서 실제로 말하는 구간(초) — 대사 · 숨 고르기 · 대사 · 쉼 · 마무리
SPEECH_SPANS = ((0.18, 2.10), (2.86, 4.02), (4.62, 5.46))
SPEECH_SYLLABLES_PER_SEC = 4.4      # 한국어 낭독 속도에 맞춘 음절 리듬
NOD_BEATS = ((2.26, 0.58), (4.20, 0.50), (5.44, 0.46))   # 대본 보며 끄덕이는 순간(시작, 길이)
NOD_EDGE = 0.16                     # 끄덕임은 짧게 — 프레임이 겹쳐 보이지 않게


def _speech_openness(t: float) -> float:
    """입 벌림 0~1 — 말하는 구간에서만 음절 리듬으로 벌렸다 다문다."""
    val = 0.0
    for si, (a, b) in enumerate(SPEECH_SPANS):
        if a <= t < b:
            u = (t - a) * SPEECH_SYLLABLES_PER_SEC
            k = int(u)
            ph = u - k
            amp = 0.6 + 0.4 * _hash01(k + si * 97, 5)
            if _hash01(k + si * 131, 9) < 0.18:      # 짧게 다물었다 떼는 음절
                amp *= 0.3
            env = min(1.0, (t - a) / 0.14, (b - t) / 0.16)   # 구간 양끝은 다문 입
            val = max(val, amp * (math.sin(math.pi * ph) ** 0.8) * max(0.0, env))
    return min(1.0, max(0.0, val))


def _nod_weight(t: float) -> float:
    """끄덕임 0~1 — 대본/마이크 쪽으로 고개를 살짝 숙였다 드는 순간.

    프레임을 섞지 않고 화면 전체를 아주 작게 기울·내려앉히는 데 쓰므로,
    다른 사진이 겹쳐 보이는 잔상이 생기지 않는다.
    """
    w = 0.0
    for start, dur in NOD_BEATS:
        if start <= t < start + dur:
            u = (t - start) / dur
            edge = min(0.5, NOD_EDGE / dur)
            if u < edge:
                w = max(w, _smooth(u / edge))
            elif u > 1.0 - edge:
                w = max(w, _smooth((1.0 - u) / edge))
            else:
                w = 1.0
    return w


def _avatar_weights(t: float, n: int) -> list[float]:
    """프레임별 블렌드 가중치(합 1.0).

    프레임 순서: [기본(입 벌림), 입 다물, 크게 벌림]. 세 장의 차이는 입 주변뿐이라
    가중치를 섞어도 사진이 겹쳐 보이지 않고, 입 모양이 자연스럽게 이어진다.
    """
    if n <= 1:
        return [1.0]
    mouth = _speech_openness(t)
    if n == 2:
        return [1.0 - mouth, mouth]
    # 입 벌림 0 → 입 다물, 0.5 → 기본, 1 → 크게 벌림
    closed = max(0.0, 1.0 - 2.0 * mouth)
    wide = max(0.0, 2.0 * mouth - 1.0)
    base = max(0.0, 1.0 - closed - wide)
    return [base, closed, wide]


def _avatar_pose(frame: Image.Image, S: int, t: float, move: float,
                 talking: bool, nod: float = 0.0) -> Image.Image:
    """호흡 줌 + 아주 작은 상하/좌우 + 고개 기울기 + 끄덕임 때의 살짝 내려앉는 무게."""
    if talking:
        # 말하는 동안: 프레임 변화가 주인공, 흔들림은 1% 안쪽의 잔잔한 호흡만
        breath = math.sin(math.tau * t / 5.2)
        zoom = 1.006 + 0.005 * breath
        dx = S * 0.0035 * math.sin(math.tau * t / 7.1)
        dy = -S * 0.0025 * (0.5 - 0.5 * math.cos(math.tau * t / 6.3))
        ang = 0.22 * math.sin(math.tau * t / 8.4)
        # 끄덕일 때는 아바타 전체가 살짝 내려앉고 고개를 끄덕인다(사진 두 장을 포개지 않아 잔상 없음)
        dy += S * 0.008 * nod
        ang += 0.6 * nod
        zoom += 0.006 * nod
    else:
        # 사진 1장: 6초 중 move 초만 살짝 — 숨쉬기 줌(≈1.035) + 미세 상하/좌우 + 기울기
        e = math.sin(math.pi * (t / move)) ** 2 if t < move else 0.0
        breath = math.sin(math.tau * t / 4.2)
        zoom = 1.008 + 0.004 * breath + 0.028 * e
        dx = S * 0.008 * math.sin(math.tau * t / move) * e
        dy = -S * 0.011 * e
        ang = 0.9 * math.sin(math.tau * t / move) * e
    w2 = max(2, int(round(S * zoom)) // 2 * 2)
    z = frame.resize((w2, w2), Image.LANCZOS)
    canvas = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    canvas.paste(z, (int((S - w2) / 2 + dx), int((S - w2) / 2 + dy)))
    if abs(ang) > 0.02:
        canvas = canvas.rotate(ang, resample=Image.BICUBIC, center=(S / 2, S / 2))
    return canvas


def avatar_motion_frames(img, size: int, key: str = "host", fps: int = 25,
                         cycle: float = 6.0, move: float = 1.6) -> tuple[Path, int]:
    """6초 주기 진행자 모션 — 로컬 PIL 계산(0원) + 프레임 캐시.

    · 사진 1장(내 사진·직접 지정): 기존과 같은 숨쉬기 모션.
      — 6초 중 1.6초만 숨쉬기 줌 + 미세 상하/좌우 + 고개 기울기, 나머지는 잔잔한 호흡.
    · 사진 2~3장(기본·입 다물·크게 벌림): 실제 대사 리듬으로 프레임을 크로스페이드해
      성우가 마이크 앞에서 말하는 것처럼 입이 움직이고, 끄덕임은 화면 전체를 아주 작게
      기울·내려앉혀 사진이 겹쳐 보이는 잔상 없이 고개 움직임을 만든다.
    """
    imgs = list(img) if isinstance(img, (list, tuple)) else [img]
    imgs = [im for im in imgs if im is not None][:3]
    if not imgs:
        raise ValueError("진행자 이미지가 없습니다")
    n = max(8, int(round(cycle * fps)))
    safe = re.sub(r"[^0-9A-Za-z_.-]", "_", str(key))[:56] or "host"
    tag = "" if len(imgs) == 1 else f"_f{len(imgs)}"
    out = CACHE_DIR / "avatar_motion" / f"am_{safe}{tag}_{int(size)}_{int(fps)}_{int(cycle * 100)}"
    if (out / "done").exists():
        return out, n
    out.mkdir(parents=True, exist_ok=True)
    S = size * 2
    pool = [np.asarray(im.convert("RGBA").resize((S, S), Image.LANCZOS), dtype=np.float32)
            for im in imgs]
    talking = len(pool) > 1
    for i in range(n):
        t = i / fps
        w = _avatar_weights(t % cycle, len(pool))
        frame = pool[0] * w[0]
        for k in range(1, len(pool)):
            frame = frame + pool[k] * w[k]
        img_i = Image.fromarray(np.clip(frame + 0.5, 0, 255).astype(np.uint8), "RGBA")
        nod = _nod_weight(t % cycle) if talking else 0.0
        canvas = _avatar_pose(img_i, S, t, move, talking, nod)
        # ON-AIR 링이 천천히 숨쉬는 펄스(2.4초)
        ring_pulse = 0.5 - 0.5 * math.cos(math.tau * t / 2.4)
        ring = Image.new("RGBA", (S, S), (0, 0, 0, 0))
        ImageDraw.Draw(ring).ellipse([S * 0.026, S * 0.026, S * 0.974, S * 0.974],
                                     outline=ONAIR + (int(34 + 40 * ring_pulse),),
                                     width=max(2, int(S * 0.012)))
        canvas = Image.alpha_composite(canvas, ring.filter(ImageFilter.GaussianBlur(S * 0.006)))
        canvas.resize((size, size), Image.LANCZOS).save(out / f"a{i:04d}.png")
    (out / "done").write_text("ok", encoding="utf-8")
    return out, n


# ── 빛 입자 오버레이 ──────────────────────────────────────────────────────
def particle_frames(width: int = 540, height: int = 960, frames: int = 96, seed: int = 7) -> Path:
    """먼지·빛 입자가 천천히 떠오르는 8초 루프(그레이스케일 PNG 시퀀스)."""
    w = max(240, width // 2 // 2 * 2)
    h = max(320, height // 2 // 2 * 2)
    key = f"p3_{w}x{h}_{frames}"
    out = CACHE_DIR / "particles" / key
    if (out / "done").exists():
        return out
    out.mkdir(parents=True, exist_ok=True)
    rng = random.Random(seed)
    motes = []
    for _ in range(48):
        motes.append({
            "x": rng.uniform(0, w), "y": rng.uniform(0, h),
            "r": rng.uniform(0.6, 2.2) * (w / 540), "a": rng.uniform(12, 58),
            "vy": rng.uniform(2, 8) * (h / 960), "vx": rng.uniform(-1.5, 1.5),
            "ph": rng.uniform(0, math.tau),
        })
    sprite_cache = {}
    for i in range(frames):
        img = Image.new("RGBA", (w, h), (255, 255, 255, 0))
        d = ImageDraw.Draw(img)
        for m in motes:
            y = (m["y"] - m["vy"] * i) % (h + 40) - 20
            x = (m["x"] + m["vx"] * i * 0.4 + math.sin(i * 0.08 + m["ph"]) * 6) % w
            alpha = int(max(0, min(255, m["a"] * (0.55 + 0.45 * math.sin(i * 0.11 + m["ph"])))))
            r = m["r"]
            key_r = int(r * 4)
            if key_r not in sprite_cache:
                sp = Image.new("L", (key_r * 2 + 1, key_r * 2 + 1), 0)
                sd = ImageDraw.Draw(sp)
                for k in range(4, 0, -1):
                    rr = key_r * k / 4
                    sd.ellipse([key_r - rr, key_r - rr, key_r + rr, key_r + rr], fill=int(255 * (1 / k)))
                sprite_cache[key_r] = sp.filter(ImageFilter.GaussianBlur(max(0.6, key_r * 0.18)))
            sp = sprite_cache[key_r]
            layer = Image.new("RGBA", (w, h), (255, 255, 255, 0))
            layer.paste((255, 255, 255, alpha), (int(x - key_r), int(y - key_r)), sp)
            img = Image.alpha_composite(img, layer)
        img.save(out / f"f{i:04d}.png")
    (out / "done").write_text("ok")
    return out


# ── 카드(되감기·예고·엔딩) ────────────────────────────────────────────────
def _card_base(w: int, h: int, warm: bool = True) -> Image.Image:
    base = Image.new("RGB", (w, h), (18, 15, 13) if warm else (8, 8, 10))
    arr = np.zeros((h, w, 3), dtype=np.float32)
    top = np.array([30, 24, 20] if warm else [18, 18, 22], dtype=np.float32)
    bot = np.array([10, 8, 7] if warm else [4, 4, 6], dtype=np.float32)
    for y in range(h):
        f = y / max(1, h - 1)
        arr[y, :, :] = top * (1 - f) + bot * f
    base = Image.fromarray(arr.astype(np.uint8))
    d = ImageDraw.Draw(base)
    # 은은한 금색 선
    d.rectangle([int(w * 0.05), int(h * 0.06), int(w * 0.95), int(h * 0.94)],
                outline=(120, 96, 52), width=max(2, w // 540))
    d.rectangle([int(w * 0.058), int(h * 0.068), int(w * 0.942), int(h * 0.932)],
                outline=(70, 56, 34), width=max(1, w // 1080))
    return base


def card_rewind(text: str, w: int, h: int, title: str = "") -> Image.Image:
    img = _card_base(w, h)
    d = ImageDraw.Draw(img)
    lines = _wrap(text, 16)
    f1 = font(int(h * 0.036), True)
    if title:
        d.text((w / 2, h * 0.38), title, font=f1, fill=GOLD, anchor="mm")
    y = h * 0.46
    f = fit_font(d, max(lines, key=len) if lines else text, int(w * 0.86), int(h * 0.062))
    for line in lines:
        d.text((w / 2, y), line, font=f, fill=CREAM, anchor="mm")
        y += f.size * 1.35
    d.line([w * 0.38, h * 0.64, w * 0.62, h * 0.64], fill=GOLD, width=max(2, w // 540))
    return img


def card_text(title: str, lines: list[str], w: int, h: int, note: str = "",
              cta: bool = False) -> Image.Image:
    img = _card_base(w, h, warm=True)
    d = ImageDraw.Draw(img)
    y = h * 0.24
    ft = font(int(h * 0.030), True)
    if title:
        d.text((w / 2, y), title, font=ft, fill=GOLD, anchor="mm")
        y += h * 0.075
    body = [ln for ln in lines if ln.strip()]
    size = int(h * (0.058 if not cta else 0.052))
    f = fit_font(d, max(body, key=len) if body else "", int(w * 0.84), size)
    for line in body:
        d.text((w / 2, y), line, font=f, fill=CREAM, anchor="mm")
        y += f.size * 1.45
    if note:
        d.text((w / 2, h * 0.855), note, font=font(int(h * 0.022), True), fill=(196, 176, 146), anchor="mm")
    return img


def like_badge(w: int) -> Image.Image:
    text = "이야기가 몰입되신다면 '좋아요' 눌러주세요!"
    f = font(int(w * 0.026), True)
    pad = int(w * 0.022)
    tw = int(f.getlength(text))
    bw, bh = tw + pad * 3 + int(w * 0.036), int(f.size * 2.1)
    img = Image.new("RGBA", (bw, bh), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([0, 0, bw - 1, bh - 1], radius=bh // 2, fill=(18, 14, 12, 224),
                        outline=GOLD + (210,), width=max(2, w // 600))
    # 하트
    cx, cy, r = pad + f.size * 0.42, bh / 2, f.size * 0.40
    d.ellipse([cx - r, cy - r * 1.15, cx, cy - r * 0.15], fill=(240, 90, 98, 255))
    d.ellipse([cx, cy - r * 1.15, cx + r, cy - r * 0.15], fill=(240, 90, 98, 255))
    d.polygon([(cx - r * 1.0, cy - r * 0.35), (cx + r * 1.0, cy - r * 0.35), (cx, cy + r * 1.1)],
              fill=(240, 90, 98, 255))
    d.text((pad + int(w * 0.042), bh / 2), text, font=f, fill=(255, 248, 232), anchor="lm")
    return img


def end_screen_overlay(w: int, h: int) -> Image.Image:
    """마지막 10초: 아래쪽에 어두운 그라데이션 + 구독/다음 영상 자리 표시(아주 옅게)."""
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    grad = np.zeros((h, w, 4), dtype=np.uint8)
    for y in range(h):
        f = max(0.0, (y - h * 0.35) / (h * 0.65))
        grad[y, :, :3] = 0
        grad[y, :, 3] = int(120 * (f ** 1.5))
    img = Image.fromarray(grad, "RGBA")
    d = ImageDraw.Draw(img)
    # 구독 원형 자리(좌하) / 다음 영상 카드 자리(우하) — 아주 옅은 안내선
    ring_r = int(min(w, h) * 0.085)
    cx, cy = int(w * 0.16), int(h * 0.80)
    d.ellipse([cx - ring_r, cy - ring_r, cx + ring_r, cy + ring_r], outline=(255, 255, 255, 46),
              width=max(2, w // 500))
    d.text((cx, cy + ring_r + int(h * 0.012)), "구독", font=font(int(h * 0.020), True),
           fill=(255, 255, 255, 90), anchor="ma")
    cw, ch = int(w * 0.34), int(w * 0.34 * 9 / 16)
    d.rounded_rectangle([int(w * 0.62), int(h * 0.72), int(w * 0.62) + cw, int(h * 0.72) + ch],
                        radius=int(h * 0.008), outline=(255, 255, 255, 42), width=max(2, w // 600))
    d.text((int(w * 0.62) + cw // 2, int(h * 0.72) + ch + int(h * 0.010)), "다음 영상",
           font=font(int(h * 0.018), True), fill=(255, 255, 255, 78), anchor="ma")
    return img


def title_overlay_small(text: str, w: int) -> Image.Image:
    f = font(int(w * 0.024), True)
    tw = int(f.getlength(text))
    img = Image.new("RGBA", (tw + w // 40, int(f.size * 1.7)), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.text((0, 0), text, font=f, fill=(255, 255, 255, 150))
    return img


# ── 썸네일 ────────────────────────────────────────────────────────────────
def _cover(im: Image.Image, w: int, h: int) -> Image.Image:
    im = im.convert("RGB")
    sw, sh = im.size
    s = max(w / sw, h / sh)
    im = im.resize((int(sw * s + 0.5), int(sh * s + 0.5)), Image.LANCZOS)
    x = (im.width - w) // 2
    y = (im.height - h) // 2
    return im.crop((x, y, x + w, y + h))


def thumbnail_style1(image_path: Path | None, lines: list[str], w: int, h: int,
                     badge: str = "실화 사연", channel: str = "세월의 사연극장") -> Image.Image:
    if image_path and Path(image_path).exists():
        img = _cover(Image.open(image_path), w, h)
        img = img.filter(ImageFilter.GaussianBlur(0.4))
    else:
        img = _card_base(w, h).resize((w, h))
    # 아래쪽 어둡게
    ov = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    od = ImageDraw.Draw(ov)
    for y in range(h):
        f = max(0.0, (y - h * 0.30) / (h * 0.70))
        od.line([(0, y), (w, y)], fill=(0, 0, 0, int(215 * (f ** 1.1))))
    img = Image.alpha_composite(img.convert("RGBA"), ov)
    d = ImageDraw.Draw(img)

    # 붉은 배지
    bf = font(int(h * 0.052), True)
    bw = int(bf.getlength(badge) + w * 0.045)
    bh = int(bf.size * 1.75)
    bx, by = int(w * 0.055), int(h * 0.055)
    d.rounded_rectangle([bx, by, bx + bw, by + bh], radius=int(bh * 0.22), fill=RED + (235,),
                        outline=(255, 235, 220, 200), width=max(2, w // 500))
    d.text((bx + bw / 2, by + bh / 2), badge, font=bf, fill=(255, 255, 255), anchor="mm")

    # 두 줄 문구 — 줄 높이를 각 글자 크기에 맞춰 겹치지 않게
    colors = [(255, 214, 64), (255, 255, 255)]
    raw = [(line, int(h * (0.135 if i == 0 else 0.118)), colors[i % 2])
           for i, line in enumerate(lines[:2])]
    fitted = [(line, fit_font(d, line, int(w * 0.82), size, min_size=48, round_style=True), color)
              for line, size, color in raw]
    uni = min([f.size for _, f, _ in fitted] or [int(h * 0.10)])
    fitted = [(line, font(uni, True), color) for line, _, color in fitted]
    gap = int(uni * 0.30)
    total_h = sum(f.size for _, f, _ in fitted) + gap * (len(fitted) - 1)
    y = h * 0.88 - total_h + (fitted[0][1].size / 2 if fitted else 0)
    for i, (line, f, color) in enumerate(fitted):
        text_outlined(d, (w / 2, y), line, f, fill=color, outline=(0, 0, 0),
                      width=max(5, int(f.size * 0.09)), anchor="mm")
        y += f.size / 2 + gap + (fitted[i + 1][1].size / 2 if i + 1 < len(fitted) else 0)
    # 채널 표시는 상단 배지 쪽에만(하단 문구와 겹치지 않게)
    d.text((w - int(w * 0.05), int(h * 0.075)), channel, font=font(int(h * 0.026), True),
           fill=(255, 255, 255, 190), anchor="rs")
    return img.convert("RGB")


def thumbnail_style2(lines: list[str], w: int, h: int, label: str = "오늘의 사연",
                     channel: str = "세월의 사연극장") -> Image.Image:
    img = Image.new("RGB", (w, h), (0, 0, 0))
    d = ImageDraw.Draw(img)
    # 아주 옅은 금색 테두리
    d.rectangle([int(w * 0.03), int(h * 0.03), int(w * 0.97), int(h * 0.97)],
                outline=(54, 46, 32), width=max(2, w // 500))
    d.text((w / 2, h * 0.105), label, font=font(int(h * 0.040), True), fill=(150, 132, 102), anchor="mm")

    colors = [YELLOW, (255, 255, 255), GREEN, (255, 255, 255), YELLOW, GREEN, (255, 255, 255)]
    raw = [ln.strip() for ln in lines if ln.strip()]
    body: list[str] = []
    for ln in raw:
        body += _wrap(ln, 11)[:2]
    body = body[:6]
    avail_h = h * 0.66
    line_h = avail_h / max(1, len(body))
    y = h * 0.20
    fits = []
    for line in body:
        size = int(min(line_h * 0.80, h * 0.145))
        fits.append(fit_font(d, line, int(w * 0.90), size, min_size=40))
    uni = min([f.size for f in fits] or [int(h * 0.08)])
    for i, line in enumerate(body):
        d.text((w / 2, y + line_h / 2), line, font=font(uni, True),
               fill=colors[i % len(colors)], anchor="mm")
        y += line_h
    d.text((w / 2, h * 0.925), channel, font=font(int(h * 0.034), True), fill=(170, 160, 140), anchor="mm")
    return img


def _wrap(text: str, width: int) -> list[str]:
    import textwrap
    return textwrap.wrap(text, width=width)[:6] or [text]


def save(img: Image.Image, path: Path, quality: int = 92) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.suffix.lower() in (".jpg", ".jpeg"):
        img.convert("RGB").save(path, quality=quality, subsampling=1)
    else:
        img.save(path)
    return path
