from __future__ import annotations

import json

import pytest

from archimate_mcp.llm import call_llm, load_llm_settings


def test_load_llm_settings_defaults_to_lm_studio_when_base_url_is_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ARCHIMATE_MCP_LLM_BASE_URL", "http://host.docker.internal:1234/v1")
    monkeypatch.delenv("ARCHIMATE_MCP_LLM_PROVIDER", raising=False)
    monkeypatch.delenv("ARCHIMATE_MCP_LLM_MODEL", raising=False)

    settings = load_llm_settings()

    assert settings.provider == "openai"
    assert settings.base_url == "http://host.docker.internal:1234/v1"
    assert settings.api_key == "lm-studio"


def test_load_llm_settings_rejects_unknown_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ARCHIMATE_MCP_LLM_PROVIDER", "unknown")

    with pytest.raises(RuntimeError, match="Unsupported ARCHIMATE_MCP_LLM_PROVIDER"):
        load_llm_settings()


def test_call_llm_parses_openai_compatible_response(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ARCHIMATE_MCP_LLM_PROVIDER", "openai")
    monkeypatch.setenv("ARCHIMATE_MCP_LLM_BASE_URL", "http://127.0.0.1:1234/v1")
    monkeypatch.setenv("ARCHIMATE_MCP_LLM_MODEL", "local-model")

    response_payload = {
        "choices": [
            {
                "message": {
                    "content": '{"elements":[],"relationships":[]}'
                }
            }
        ]
    }

    class FakeResponse:
        def __enter__(self) -> "FakeResponse":
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

        def read(self) -> bytes:
            return json.dumps(response_payload).encode("utf-8")

    def fake_urlopen(req, timeout: int):  # type: ignore[no-untyped-def]
        assert req.full_url == "http://127.0.0.1:1234/v1/chat/completions"
        assert timeout == 60
        body = json.loads(req.data.decode("utf-8"))
        assert body["model"] == "local-model"
        return FakeResponse()

    monkeypatch.setattr("archimate_mcp.llm.request.urlopen", fake_urlopen)

    assert call_llm("system", "user") == '{"elements":[],"relationships":[]}'
