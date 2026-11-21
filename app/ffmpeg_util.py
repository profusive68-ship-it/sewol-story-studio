"""ffmpeg 실행 파일 찾기·실행·길이 재기."""
from __future__ import annotations

import functools
import re
import shutil
import subprocess
from pathlib import Path


class FFmpegMissing(RuntimeError):
    pass


@functools.lru_cache(maxsize=1)
def ffmpeg_exe() -> str:
    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    try:
        import imageio_ffmpeg
        p = imageio_ffmpeg.get_ffmpeg_exe()
        if p and Path(p).exists():
            return p
    except Exception:
        pass
    for cand in ("/opt/homebrew/bin/ffmpeg", "/usr/local/bin/ffmpeg", "/usr/bin/ffmpeg"):
        if Path(cand).exists():
            return cand
    raise FFmpegMissing(
        "ffmpeg 를 찾지 못했습니다. 터미널에서  brew install ffmpeg  를 실행한 뒤 다시 시작해 주세요."
    )


@functools.lru_cache(maxsize=1)
def ffprobe_exe() -> str | None:
    exe = shutil.which("ffprobe")
    if exe:
        return exe
    for cand in ("/opt/homebrew/bin/ffprobe", "/usr/local/bin/ffprobe", "/usr/bin/ffprobe"):
        if Path(cand).exists():
            return cand
    # imageio-ffmpeg 옆에 ffprobe 가 있는 경우
    try:
        import imageio_ffmpeg
        base = Path(imageio_ffmpeg.get_ffmpeg_exe()).with_name("ffprobe")
        if base.exists():
            return str(base)
    except Exception:
        pass
    return None


def run(args: list[str], timeout: int = 600, capture: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(args, stdout=subprocess.PIPE if capture else None,
                          stderr=subprocess.PIPE if capture else None,
                          text=True, timeout=timeout, check=False)


def duration(path: Path) -> float:
    """오디오/영상 길이(초). ffprobe 가 없으면 ffmpeg -i 출력을 읽는다."""
    p = str(path)
    probe = ffprobe_exe()
    if probe:
        r = run([probe, "-v", "error", "-show_entries", "format=duration",
                 "-of", "default=nw=1:nk=1", p], timeout=60)
        try:
            v = float((r.stdout or "").strip())
            if v > 0:
                return v
        except ValueError:
            pass
    r = run([ffmpeg_exe(), "-hide_banner", "-i", p], timeout=60)
    m = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", (r.stderr or ""))
    if m:
        h, mi, s = m.group(1), m.group(2), m.group(3)
        return int(h) * 3600 + int(mi) * 60 + float(s)
    raise RuntimeError(f"길이를 읽지 못했습니다: {path}")


def has_encoder(name: str) -> bool:
    try:
        r = run([ffmpeg_exe(), "-hide_banner", "-encoders"], timeout=60)
        return name in (r.stdout or "")
    except Exception:
        return False


def has_filter(name: str) -> bool:
    try:
        r = run([ffmpeg_exe(), "-hide_banner", "-filters"], timeout=60)
        return bool(re.search(rf"\s{name}\s", r.stdout or ""))
    except Exception:
        return False


def version() -> str:
    try:
        r = run([ffmpeg_exe(), "-version"], timeout=30)
        first = (r.stdout or "").splitlines()[0]
        return first.strip()
    except Exception:
        return "없음"
