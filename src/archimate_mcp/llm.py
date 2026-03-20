from __future__ import annotations

import json
import os
from dataclasses import dataclass
from urllib import error, request


DEFAULT_ANTHROPIC_MODEL = "claude-opus-4-5"
DEFAULT_OPENAI_MODEL = "gpt-4o-mini"


@dataclass(frozen=True)
class LLMSettings:
    provider: str
    model: str
    api_key: str | None = None
    base_url: str | None = None
    temperature: float = 0.0
    max_tokens: int = 2048
    timeout_seconds: int = 60


def load_llm_settings() -> LLMSettings:
    provider = os.getenv("ARCHIMATE_MCP_LLM_PROVIDER", "").strip().lower()
    base_url = os.getenv("ARCHIMATE_MCP_LLM_BASE_URL", "").strip() or None

    if not provider:
        provider = "openai" if base_url else "anthropic"

    if provider not in {"anthropic", "openai"}:
        raise RuntimeError(
            "Unsupported ARCHIMATE_MCP_LLM_PROVIDER. Use 'anthropic' or 'openai'."
        )

    default_model = DEFAULT_ANTHROPIC_MODEL if provider == "anthropic" else DEFAULT_OPENAI_MODEL
    model = os.getenv("ARCHIMATE_MCP_LLM_MODEL", default_model).strip() or default_model
    api_key = os.getenv("ARCHIMATE_MCP_LLM_API_KEY", "").strip() or None
    temperature = float(os.getenv("ARCHIMATE_MCP_LLM_TEMPERATURE", "0"))
    max_tokens = int(os.getenv("ARCHIMATE_MCP_LLM_MAX_TOKENS", "2048"))
    timeout_seconds = int(os.getenv("ARCHIMATE_MCP_LLM_TIMEOUT_SECONDS", "60"))

    if provider == "openai":
        base_url = base_url or "http://127.0.0.1:1234/v1"
        api_key = api_key or "lm-studio"

    return LLMSettings(
        provider=provider,
        model=model,
        api_key=api_key,
        base_url=base_url,
        temperature=temperature,
        max_tokens=max_tokens,
        timeout_seconds=timeout_seconds,
    )


def call_llm(system: str, user: str) -> str:
    settings = load_llm_settings()

    if settings.provider == "anthropic":
        return _call_anthropic(system, user, settings)
    return _call_openai_compatible(system, user, settings)


def _call_anthropic(system: str, user: str, settings: LLMSettings) -> str:
    try:
        import anthropic
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            "Anthropic provider selected but the 'anthropic' package is not installed."
        ) from exc

    client_kwargs: dict[str, str] = {}
    if settings.api_key:
        client_kwargs["api_key"] = settings.api_key

    client = anthropic.Anthropic(**client_kwargs)
    message = client.messages.create(
        model=settings.model,
        max_tokens=settings.max_tokens,
        temperature=settings.temperature,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    return message.content[0].text


def _call_openai_compatible(system: str, user: str, settings: LLMSettings) -> str:
    assert settings.base_url is not None

    payload = {
        "model": settings.model,
        "temperature": settings.temperature,
        "max_tokens": settings.max_tokens,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    }
    body = json.dumps(payload).encode("utf-8")
    url = settings.base_url.rstrip("/") + "/chat/completions"

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {settings.api_key or 'lm-studio'}",
    }
    req = request.Request(url, data=body, headers=headers, method="POST")

    try:
        with request.urlopen(req, timeout=settings.timeout_seconds) as response:
            raw = response.read().decode("utf-8")
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"OpenAI-compatible provider request failed: {exc.code} {detail}") from exc
    except error.URLError as exc:
        raise RuntimeError(
            f"Could not reach OpenAI-compatible provider at {url}: {exc.reason}"
        ) from exc

    data = json.loads(raw)
    choices = data.get("choices") or []
    if not choices:
        raise RuntimeError("OpenAI-compatible provider returned no choices.")

    message = choices[0].get("message") or {}
    content = message.get("content")

    if isinstance(content, str):
        return content

    if isinstance(content, list):
        text_parts = [
            part.get("text", "")
            for part in content
            if isinstance(part, dict) and part.get("type") == "text"
        ]
        merged = "".join(text_parts).strip()
        if merged:
            return merged

    raise RuntimeError("OpenAI-compatible provider returned an unsupported response format.")
