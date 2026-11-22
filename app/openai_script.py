"""OpenAI Chat Completions 대본 보조 엔진 (gpt-4o-mini).

Gemini 가 503·429·한도 초과 등으로 대본을 만들지 못할 때, 같은 JSON 스키마로
이어서 만들기 위한 두 번째 엔진이다. `config.openai_api_key` 하나로 동작하고
(음성 엔진과 같은 키), 키가 없으면 호출하지 않는다.

  · 엔드포인트: https://api.openai.com/v1/chat/completions
  · 모델: gpt-4o-mini (config.openai_script_model 로 바꿀 수 있다)
  · response_format={"type": "json_object"} 로 JSON 만 받는다
  · 429·5xx 는 1.5초 뒤 한 번 더 시도하고, 401·403 은 즉시 한국어 안내로 실패한다

표준 라이브러리(urllib)만 쓴다 — 맥에 requests 가 없어도 대본이 만들어지게.
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from typing import Optional

OPENAI_CHAT_URL = "https://api.openai.com/v1/chat/completions"
OPENAI_SCRIPT_MODEL = "gpt-4o-mini"
OPENAI_SCRIPT_MODELS = {
    "gpt-4o-mini": "gpt-4o-mini (기본 · 빠르고 저렴)",
    "gpt-4o": "gpt-4o (더 좋은 문장 · 비쌈)",
    "gpt-4.1-mini": "gpt-4.1-mini (최신 소형 · 추천)",
}
OPENAI_TIMEOUT = 120          # 초 (설계 단계 한 번 기준)
RETRY_SECONDS = 1.5
BUSY_CODES = (408, 409, 429, 500, 502, 503, 504)
AUTH_CODES = (401, 403)


def api_key(cfg: dict) -> str:
    return str((cfg or {}).get("openai_api_key") or "").strip().lstrip("=").strip()


def has_key(cfg: dict) -> bool:
    return bool(api_key(cfg))


def model_name(cfg: dict) -> str:
    model = str((cfg or {}).get("openai_script_model") or "").strip()
    return model or OPENAI_SCRIPT_MODEL


def build_payload(cfg: dict, prompt: str, *, temperature: float = 0.9,
                  response_json: bool = True,
                  max_output_tokens: Optional[int] = None,
                  system: Optional[str] = None) -> dict:
    """요청 본문 — 테스트에서 네트워크 없이 그대로 확인할 수 있게 분리해 둔다."""
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    payload = {
        "model": model_name(cfg),
        "messages": messages,
        "temperature": max(0.0, min(2.0, float(temperature))),
    }
    if response_json:
        payload["response_format"] = {"type": "json_object"}
    if max_output_tokens:
        payload["max_tokens"] = int(max_output_tokens)
    return payload


def _headers(key: str) -> dict:
    return {"Content-Type": "application/json", "Authorization": "Bearer " + key}


def _content_of(data: dict) -> str:
    try:
        choices = data.get("choices") or []
        msg = (choices[0] or {}).get("message") or {}
        content = msg.get("content")
        if isinstance(content, list):        # 일부 응답은 조각 목록으로 온다
            return "".join(str(p.get("text", "")) for p in content if isinstance(p, dict))
        return str(content or "")
    except Exception:
        return ""


def call_openai(cfg: dict, prompt: str, *, temperature: float = 0.9,
                response_json: bool = True, max_output_tokens: Optional[int] = None,
                system: Optional[str] = None) -> str:
    """OpenAI Chat Completions 호출 — 응답 텍스트를 돌려준다.

    429·5xx 는 1.5초 뒤 1회 재시도, 401·403 은 즉시 RuntimeError.
    """
    key = api_key(cfg)
    if not key:
        raise RuntimeError("OpenAI API 키가 없습니다.")
    payload = build_payload(cfg, prompt, temperature=temperature,
                            response_json=response_json,
                            max_output_tokens=max_output_tokens, system=system)
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    last_err: Optional[Exception] = None
    for attempt in range(2):
        req = urllib.request.Request(OPENAI_CHAT_URL, data=body,
                                     headers=_headers(key), method="POST")
        try:
            with urllib.request.urlopen(req, timeout=OPENAI_TIMEOUT) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            text = _content_of(data).strip()
            if not text:
                raise RuntimeError("OpenAI 응답이 비어 있습니다.")
            return text
        except urllib.error.HTTPError as e:
            detail = ""
            try:
                detail = e.read().decode("utf-8", errors="ignore")[:400]
            except Exception:
                pass
            if e.code in AUTH_CODES:
                raise RuntimeError(f"OpenAI 키가 거부되었습니다(HTTP {e.code}). "
                                   "[🎙️ 음성 엔진]의 OpenAI API 키를 다시 확인해 주세요. " + detail)
            last_err = RuntimeError(f"HTTP {e.code} ({model_name(cfg)}): {detail or e.reason}")
            if e.code in BUSY_CODES and attempt == 0:
                time.sleep(RETRY_SECONDS)
                continue
            raise last_err
        except urllib.error.URLError as e:
            last_err = RuntimeError(f"OpenAI 연결 실패: {getattr(e, 'reason', e)}")
            if attempt == 0:
                time.sleep(RETRY_SECONDS)
                continue
            raise last_err
    raise RuntimeError(f"OpenAI 호출 실패({model_name(cfg)}): {last_err}")


def test_connection(cfg: dict) -> dict:
    """[연결 테스트] — 짧은 한국어 한 줄로 키와 모델을 확인한다."""
    if not has_key(cfg):
        return {"ok": False, "error": "OpenAI API 키가 저장되어 있지 않습니다."}
    try:
        text = call_openai(cfg, "'연결 성공'이라고만 답해 주세요.", temperature=0,
                           response_json=False, max_output_tokens=20)
        return {"ok": True, "message": (text or "").strip()[:40] or "연결 성공",
                "model": model_name(cfg)}
    except Exception as e:
        return {"ok": False, "error": str(e)[:300]}
