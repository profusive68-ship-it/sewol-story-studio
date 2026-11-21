"""모드 A — Gemini 이미지 자동 생성 (실패 시 임시 이미지로 파이프라인 유지)."""
from __future__ import annotations

import base64
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from .graphics import CREAM, font, text_outlined
from .paths import project_dir
from .settings import load_config


def _client(cfg: dict):
    from google import genai
    key = (cfg.get("gemini_api_key") or "").strip()
    if not key:
        raise RuntimeError("Gemini API 키가 없습니다.")
    return genai.Client(api_key=key)


def _models(cfg: dict) -> list[str]:
    primary = cfg.get("image_model") or "gemini-2.5-flash-image"
    return [primary] + [m for m in (cfg.get("image_model_fallbacks") or []) if m != primary]


def _style_suffix(project: dict) -> str:
    aspect = project["format"]["aspect"]
    look = ("Vertical 9:16 cinematic film still" if aspect == "9:16"
            else "Widescreen 16:9 cinematic film still")
    return (f"{look}, Korean drama, photorealistic, 35mm, natural window light, shallow depth of field, "
            "subtle film grain, muted warm color grade, no text, no letters, no logo, no watermark, "
            "no borders. Keep the SAME characters' faces, ages, hair and clothing as described.")


def _gen_one(cfg: dict, project: dict, entry: dict, dest: Path) -> bool:
    from google.genai import types
    prompt = (entry.get("prompt") or entry.get("caption") or project["title"]) + ". " + _style_suffix(project)
    aspect = project["format"]["aspect"]
    client = _client(cfg)
    last = None
    for model in _models(cfg):
        for attempt in range(2):
            try:
                kwargs = {"temperature": 0.7, "response_modalities": ["IMAGE"]}
                try:
                    kwargs["image_config"] = types.ImageConfig(aspect_ratio=aspect)
                    conf = types.GenerateContentConfig(**kwargs)
                except Exception:
                    kwargs.pop("image_config", None)
                    conf = types.GenerateContentConfig(**kwargs)
                resp = client.models.generate_content(model=model, contents=prompt, config=conf)
                data = _extract_image(resp)
                if data:
                    tmp = dest.with_suffix(".raw.png")
                    tmp.write_bytes(data)
                    _fit(tmp, dest, project["format"]["width"], project["format"]["height"])
                    tmp.unlink(missing_ok=True)
                    return True
                last = RuntimeError("이미지 데이터 없음")
            except Exception as e:
                last = e
    raise RuntimeError(str(last)[:200])


def _extract_image(resp) -> bytes | None:
    try:
        for cand in (getattr(resp, "candidates", None) or []):
            content = getattr(cand, "content", None)
            for part in (getattr(content, "parts", None) or []):
                inline = getattr(part, "inline_data", None)
                if inline is not None and getattr(inline, "data", None):
                    d = inline.data
                    return base64.b64decode(d) if isinstance(d, str) else bytes(d)
    except Exception:
        pass
    return None


def _fit(src: Path, dest: Path, w: int, h: int) -> None:
    im = Image.open(src).convert("RGB")
    sw, sh = im.size
    s = max(w / sw, h / sh)
    im = im.resize((int(sw * s + 0.5), int(sh * s + 0.5)), Image.LANCZOS)
    x, y = (im.width - w) // 2, (im.height - h) // 2
    im = im.crop((x, y, x + w, y + h))
    im = im.filter(ImageFilter.UnsharpMask(radius=2, percent=60, threshold=3))
    dest.parent.mkdir(parents=True, exist_ok=True)
    im.save(dest, "PNG")


def placeholder(entry: dict, w: int, h: int, title: str, path: Path) -> None:
    """이미지 생성이 실패해도 영상이 멈추지 않도록 만드는 임시 장면 이미지."""
    arr = np.zeros((h, w, 3), dtype=np.float32)
    top = np.array([46, 38, 30], dtype=np.float32)
    bot = np.array([16, 13, 12], dtype=np.float32)
    for y in range(h):
        f = y / max(1, h - 1)
        arr[y, :, :] = top * (1 - f) + bot * f
    im = Image.fromarray(arr.astype(np.uint8))
    # 은은한 빛 번짐
    glow = Image.new("L", (w, h), 0)
    gd = ImageDraw.Draw(glow)
    gd.ellipse([w * 0.15, h * 0.15, w * 0.75, h * 0.6], fill=70)
    glow = glow.filter(ImageFilter.GaussianBlur(w * 0.12))
    im = Image.composite(Image.new("RGB", (w, h), (120, 96, 64)), im, glow)
    d = ImageDraw.Draw(im)
    d.rectangle([w * 0.05, h * 0.06, w * 0.95, h * 0.94], outline=(90, 74, 48), width=max(2, w // 600))
    caption = entry.get("caption") or title
    f = font(int(h * 0.035), True)
    y = h * 0.44
    for line in _wrap(caption, 14):
        d.text((w / 2, y), line, font=f, fill=CREAM, anchor="mm")
        y += f.size * 1.4
    d.text((w / 2, h * 0.90), "이미지 준비 중 — images 폴더에 넣으면 교체됩니다",
           font=font(int(h * 0.018), True), fill=(190, 172, 148), anchor="mm")
    path.parent.mkdir(parents=True, exist_ok=True)
    im.save(path)


def _wrap(text: str, width: int) -> list[str]:
    import textwrap
    return textwrap.wrap(text, width=width)[:4]


def generate_images(project: dict, progress=None) -> dict:
    cfg = load_config()
    pdir = project_dir(project["id"])
    plan = project.get("image_plan", [])
    missing = [e for e in plan if not (pdir / "images" / e["file"]).exists()]
    sources = project.setdefault("image_sources", {})
    if not missing:
        return {"generated": 0, "failed": 0}

    w, h = project["format"]["width"], project["format"]["height"]
    done, failed = 0, 0
    errors: list[str] = []

    if not (cfg.get("gemini_api_key") or "").strip():
        for e in missing:
            placeholder(e, w, h, project["title"], pdir / "images" / e["file"])
            sources[e["file"]] = "placeholder"
        project["warnings"] = list(project.get("warnings", [])) + [
            "이미지 자동 생성에는 Gemini API 키가 필요합니다. 임시 이미지로 조립했습니다."]
        return {"generated": 0, "failed": len(missing), "placeholder": len(missing)}

    def job(e):
        dest = pdir / "images" / e["file"]
        _gen_one(cfg, project, e, dest)
        return e["file"]

    with ThreadPoolExecutor(max_workers=3) as ex:
        futures = {ex.submit(job, e): e for e in missing}
        for i, fut in enumerate(as_completed(futures), start=1):
            e = futures[fut]
            try:
                f = fut.result()
                sources[f] = "gemini"
                done += 1
                if progress:
                    progress(int(95 * i / len(missing)), f"이미지 생성 {i}/{len(missing)}")
            except Exception as ex_:
                failed += 1
                errors.append(f"{e['file']}: {str(ex_)[:120]}")
                placeholder(e, w, h, project["title"], pdir / "images" / e["file"])
                sources[e["file"]] = "placeholder"
    if errors:
        project["warnings"] = list(project.get("warnings", [])) + ["이미지 일부 생성 실패 → 임시 이미지 사용"] + errors[:3]
    return {"generated": done, "failed": failed, "errors": errors[:3]}
