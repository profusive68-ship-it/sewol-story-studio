"""한 편 안에서 호칭·인물명을 하나로 통일한다.

'엄마'와 '어머니', '아빠'와 '아버지'처럼 같은 사람을 가리키는 다른 표현이
제목·썸네일 문구·대본에 섞이면, 청취자는 다른 사람으로 오해한다.
(예: 제목은 「엄마의 김치통」인데 썸네일은 '어머니', 대사는 '엄마' — 같은 사람인지 헷갈린다)

그래서 한 편을 만들 때 표준 표현을 하나 정하고, 나머지 표현을 그 표준으로 바꾼다.
  1) 사용자가 직접 적은 주제(topic)에 쓰인 표현이 있으면 그것이 표준
  2) 없으면 제목에 쓰인 표현이 표준
  3) 둘 다 없으면 손대지 않는다(모델이 처음부터 하나로 쓴 것으로 본다)

v1.2.5 — 예시 대본(폴백)과 AI 대본(정규화) 모두에 같은 규칙을 적용한다.
"""
from __future__ import annotations

from typing import Iterable, List, Optional

# (대표 이름, 같은 사람을 부르는 말들)
HONORIFIC_GROUPS = (
    ("어머니", ("엄마", "어머니", "어머님")),
    ("아버지", ("아빠", "아버지", "아버님")),
    ("할머니", ("할머니", "할머님")),
    ("할아버지", ("할아버지", "할아버님")),
)
VARIANTS = {head: variants for head, variants in HONORIFIC_GROUPS}


def find_variant(text: str) -> Optional[tuple]:
    """이 글에 들어 있는 (대표 이름, 표현) — 가장 긴 표현부터 확인한다."""
    body = str(text or "")
    if not body:
        return None
    for head, variants in HONORIFIC_GROUPS:
        for v in sorted(variants, key=len, reverse=True):
            if v in body:
                return head, v
    return None


def pick_variants(hints: Iterable[str]) -> dict:
    """앞에 오는 힌트(주제 → 제목)에서 먼저 나온 표현을 그 편의 표준으로 정한다."""
    chosen: dict = {}
    for hint in hints:
        text = str(hint or "")
        if not text:
            continue
        for head, variants in HONORIFIC_GROUPS:
            if head in chosen:
                continue
            for v in sorted(variants, key=len, reverse=True):
                if v in text:
                    chosen[head] = v
                    break
    return chosen


def harmonize_text(text: str, chosen: dict) -> str:
    """표준이 아닌 표현을 표준 표현으로 바꾼다. (긴 표현부터 바꿔 '어머님'이 깨지지 않게)"""
    out = str(text or "")
    if not out or not chosen:
        return out
    for head, want in chosen.items():
        for v in sorted(VARIANTS.get(head, (want,)), key=len, reverse=True):
            if v == want or v not in out:
                continue
            out = _replace_honorific(out, v, want)
    return out


# 조사 쌍 (받침 있을 때, 받침 없을 때) — '어머님이'를 '엄마이'로 만들지 않기 위해
JOSA_PAIRS = (("이랑", "랑"), ("으로", "로"), ("이며", "며"),
               ("이", "가"), ("은", "는"), ("을", "를"), ("과", "와"))


def _has_batchim(word: str) -> bool:
    """마지막 글자에 받침이 있는지 — 한글 음절만 판단하고 그 밖은 False."""
    if not word:
        return False
    code = ord(word[-1])
    if 0xAC00 <= code <= 0xD7A3:
        return (code - 0xAC00) % 28 != 0
    return False


def _replace_honorific(text: str, old: str, new: str) -> str:
    """호칭 하나를 바꿀 때 뒤에 붙은 조사도 같이 고친다. ('어머님이' → '엄마가')"""
    if not old or old == new or old not in text:
        return text
    out = text
    for batchim_form, plain_form in sorted(JOSA_PAIRS, key=lambda p: len(p[0]), reverse=True):
        cur = old + (batchim_form if _has_batchim(old) else plain_form)
        if cur in out:
            dst = new + (batchim_form if _has_batchim(new) else plain_form)
            out = out.replace(cur, dst)
    return out.replace(old, new)


def _harmonize_list(items, chosen: dict) -> List[str]:
    return [harmonize_text(x, chosen) for x in (items or [])]


def harmonize_script(script: dict, *hints: str) -> dict:
    """대본 묶음(제목·설명·썸네일 문구·장면 대사·연기 지시)의 호칭을 하나로 맞춘다."""
    if not isinstance(script, dict):
        return script
    ordered = [h for h in hints if h] + [script.get("title", "")]
    chosen = pick_variants(ordered)
    if not chosen:
        return script

    for key in ("title", "logline", "description", "setting", "sequel_teaser"):
        if isinstance(script.get(key), str):
            script[key] = harmonize_text(script[key], chosen)
    if isinstance(script.get("titles"), list):
        script["titles"] = _harmonize_list(script["titles"], chosen)

    thumb = script.get("thumbnail")
    if isinstance(thumb, dict):
        for key in ("style1", "style2"):
            if isinstance(thumb.get(key), list):
                thumb[key] = _harmonize_list(thumb[key], chosen)

    upload = script.get("upload")
    if isinstance(upload, dict):
        for key in ("title", "description"):
            if isinstance(upload.get(key), str):
                upload[key] = harmonize_text(upload[key], chosen)

    for ch in (script.get("chapters") or []):
        if isinstance(ch, dict) and isinstance(ch.get("title"), str):
            ch["title"] = harmonize_text(ch["title"], chosen)

    hook = script.get("hook")
    if isinstance(hook, dict):
        for key in ("caption", "line", "rewind_caption"):
            if isinstance(hook.get(key), str):
                hook[key] = harmonize_text(hook[key], chosen)

    nxt = script.get("next_story")
    if isinstance(nxt, dict):
        for key in ("title", "teaser"):
            if isinstance(nxt.get(key), str):
                nxt[key] = harmonize_text(nxt[key], chosen)

    for sc in (script.get("scenes") or []):
        if not isinstance(sc, dict):
            continue
        for key in ("text", "image_caption", "speaker_tone", "chapter_title"):
            if isinstance(sc.get(key), str):
                sc[key] = harmonize_text(sc[key], chosen)

    for c in (script.get("characters") or []):
        if not isinstance(c, dict):
            continue
        # 인물 이름은 '어머니'처럼 딱 그 표현일 때만 바꾼다('어머니 순자' 같은 이름은 그대로 둔다)
        name = str(c.get("name") or "")
        hit = find_variant(name)
        if hit and name == hit[1]:
            c["name"] = harmonize_text(name, chosen)
        if isinstance(c.get("relation"), str):
            c["relation"] = harmonize_text(c["relation"], chosen)

    script["honorifics"] = chosen
    return script
