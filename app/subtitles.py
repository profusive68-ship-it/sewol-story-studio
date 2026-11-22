"""자막(ASS) 생성 — 시니어 특대 92px / 기본 70px, 10~14자 자동 줄바꿈."""
from __future__ import annotations

from pathlib import Path

from .graphics import font_path
from .pronunciation import subtitle_text
from .settings import AVATAR_SIZE_RATIO, SUBTITLE_SIZES
from PIL import ImageFont


def _family() -> str:
    try:
        return ImageFont.truetype(str(font_path()), 40).getname()[0]
    except Exception:
        return "Gmarket Sans TTF"

SPEAKER_COLORS = {
    "narrator": "&H00FFFFFF",
    "old_male": "&H00C8F2FF",
    "old_female": "&H00D8D8FF",
    "female": "&H00E6D5FF",
    "young_male": "&H00FFE8CC",
    "child": "&H0090F0FF",
}


def _ts(sec: float) -> str:
    sec = max(0.0, sec)
    h = int(sec // 3600)
    m = int((sec % 3600) // 60)
    s = sec % 60
    return f"{h}:{m:02d}:{s:05.2f}"


def _ass_text(lines: list[str]) -> str:
    out = []
    for ln in lines:
        ln = ln.replace("\\", "＼").replace("{", "｛").replace("}", "｝")
        out.append(ln)
    return "\\N".join(out)


def _chunks(text: str, start: float, end: float, max_chars: int) -> list[tuple[float, float, list[str]]]:
    """긴 대사를 자막 3줄 이내 단위로 쪼개고, 글자 수에 비례해 시간을 나눈다."""
    import re
    from .pronunciation import _wrap_words
    t = re.sub(r"\s+", " ", (text or "").strip())
    if not t:
        return []
    dur = max(0.6, end - start)
    max_block = max_chars * 3
    words = t.split()
    blocks: list[str] = []
    cur = ""
    for w in words:
        if not cur:
            cur = w
        elif len(cur) + 1 + len(w) <= max_block:
            cur += " " + w
        else:
            blocks.append(cur)
            cur = w
    if cur:
        blocks.append(cur)
    # 너무 잘게 나뉘지 않게 인접 블록 합치기 (2줄 정도)
    merged: list[str] = []
    for b in blocks:
        if merged and len(merged[-1]) + 1 + len(b) <= max_chars * 2.4:
            merged[-1] += " " + b
        else:
            merged.append(b)
    total = sum(len(b) for b in merged) or 1
    out, tcur = [], start
    for b in merged:
        d = dur * len(b) / total
        st = tcur
        en = min(end, tcur + d - 0.03)
        if en - st < 0.35:
            en = min(end, st + 0.35)
        out.append((st, en, _wrap_words(b, max_chars)[:3]))
        tcur += d
    return out


def write_ass(project: dict, items: list[dict], path: Path, width: int, height: int) -> Path:
    opt = project.get("options", {})
    key = opt.get("subtitle_size", "senior")
    base_px = SUBTITLE_SIZES.get(key, SUBTITLE_SIZES["senior"])[0]
    scale = min(width, height) / 1080.0
    size = max(28, int(round(base_px * scale)))
    margin_lr = int(width * 0.055)
    margin_v = int(height * 0.135)
    # 세로 화면에서는 큰 진행자(하단 우측)와 자막이 겹치지 않게 자막 블록을 그 위로 올린다.
    # 가로 화면(16:9)은 자막이 화면 가운데 좁게 놓여 모서리 진행자와 거의 겹치지 않는다.
    if opt.get("avatar", True) and height > width:
        av = max(160, int(min(width, height) * AVATAR_SIZE_RATIO) // 2 * 2)
        am = max(16, int(min(width, height) * 0.032))
        badge_h = int(width * 0.0215 * 1.62)
        margin_v = max(margin_v, am + av + int(badge_h * 0.55) + int(height * 0.012))
    max_chars = max(10, min(14, int((width - margin_lr * 2) / (size * 1.02))))

    family = _family()
    styles = []
    for speaker, color in SPEAKER_COLORS.items():
        styles.append(
            f"Style: {speaker},{family},{size},{color},{color},&H00101010,&H90000000,"
            f"-1,0,0,0,100,100,-0.5,0,1,{max(3, int(size * 0.045))},{max(2, int(size * 0.03))},"
            f"2,{margin_lr},{margin_lr},{margin_v},1"
        )
    brand_size = max(20, int(size * 0.36))
    styles.append(
        f"Style: Brand,{family},{brand_size},&H64FFFFFF,&H64FFFFFF,&H64000000,&H00000000,"
        f"-1,0,0,0,100,100,0,0,1,1,0,7,{int(width * 0.045)},0,{int(height * 0.035)},1"
    )

    header = f"""[Script Info]
; 세월의 사연극장 자동 자막
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
WrapStyle: 2
ScaledBorderAndShadow: yes
YCbCr Matrix: TV.709

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
{chr(10).join(styles)}

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    events = []
    total = float(project.get("duration") or (items[-1]["end"] if items else 0))
    if not project.get("options", {}).get("no_brand"):
        events.append(f"Dialogue: 0,{_ts(0)},{_ts(total)},Brand,,0,0,0,,세월의 사연극장")
    for it in items:
        if it.get("card"):
            continue
        speaker = it.get("speaker", "narrator")
        style = speaker if speaker in SPEAKER_COLORS else "narrator"
        for st, en, lines in _chunks(it["text"], it["start"], it["end"], max_chars):
            if not lines or not lines[0]:
                continue
            text = _ass_text(lines)
            events.append(f"Dialogue: 1,{_ts(st)},{_ts(en)},{style},,0,0,0,,{text}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(header + "\n".join(events) + "\n", encoding="utf-8")
    return path


def write_srt(project: dict, items: list[dict], path: Path, max_chars: int = 14) -> Path:
    def srt_ts(sec: float) -> str:
        h = int(sec // 3600)
        m = int((sec % 3600) // 60)
        s = int(sec % 60)
        ms = int(round((sec - int(sec)) * 1000))
        if ms >= 1000:
            ms = 999
        return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

    rows = []
    idx = 1
    for it in items:
        for st, en, lines in _chunks(it["text"], it["start"], it["end"], max_chars):
            rows.append(f"{idx}\n{srt_ts(st)} --> {srt_ts(en)}\n" + "\n".join(lines) + "\n")
            idx += 1
    path.write_text("\n".join(rows), encoding="utf-8")
    return path
