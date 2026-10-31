"""Free checks for the formal AR-02 provider wiring; no Provider I/O."""

from __future__ import annotations

import sys
import asyncio
import json

import httpx
import pytest
from langchain_core.messages import HumanMessage


def test_server_passes_fail_closed_provider_factory_to_formal_app(monkeypatch):
    from opspilot.web import server

    monkeypatch.delenv("OPSPILOT_ASSISTANT_PROVIDER_ENABLED", raising=False)
    monkeypatch.delenv("OPSPILOT_MODEL_API_KEY", raising=False)
    monkeypatch.delenv("OPSPILOT_MODEL_NAME", raising=False)
    captured = {}
    monkeypatch.setattr(
        server,
        "create_app",
        lambda **kwargs: captured.update(kwargs) or object(),
    )
    monkeypatch.setattr(server.uvicorn, "run", lambda *args, **kwargs: None)
    monkeypatch.setattr(sys, "argv", ["opspilot-web"])

    assert server.main() == 0
    factory = captured.get("assistant_model_factory")
    assert callable(factory)
    assert factory() is None


def test_provider_factory_stays_disabled_even_if_credentials_exist(monkeypatch):
    from opspilot.assistant import create_assistant_model

    monkeypatch.delenv("OPSPILOT_ASSISTANT_PROVIDER_ENABLED", raising=False)
    monkeypatch.setenv("OPSPILOT_MODEL_API_KEY", "test-only-not-a-real-key")
    monkeypatch.setenv("OPSPILOT_MODEL_NAME", "deepseek-flash")

    assert create_assistant_model() is None


def test_provider_factory_requires_existing_model_configuration_after_explicit_enable(monkeypatch):
    from opspilot.assistant import create_assistant_model

    monkeypatch.setenv("OPSPILOT_ASSISTANT_PROVIDER_ENABLED", "1")
    monkeypatch.delenv("OPSPILOT_MODEL_API_KEY", raising=False)
    monkeypatch.delenv("OPSPILOT_MODEL_NAME", raising=False)

    with pytest.raises(RuntimeError, match="Missing required model configuration"):
        create_assistant_model()


def test_provider_factory_does_not_default_deepseek_to_openai_endpoint(monkeypatch):
    from opspilot.assistant import create_assistant_model

    monkeypatch.setenv("OPSPILOT_ASSISTANT_PROVIDER_ENABLED", "1")
    monkeypatch.setenv("OPSPILOT_MODEL_API_KEY", "test-only-not-a-real-key")
    monkeypatch.setenv("OPSPILOT_MODEL_NAME", "deepseek-flash")
    monkeypatch.delenv("OPSPILOT_MODEL_BASE_URL", raising=False)

    with pytest.raises(RuntimeError, match="OPSPILOT_MODEL_BASE_URL"):
        create_assistant_model()


def test_provider_factory_builds_bounded_no_retry_chatopenai_without_network(monkeypatch):
    from opspilot.assistant import create_assistant_model

    monkeypatch.setenv("OPSPILOT_ASSISTANT_PROVIDER_ENABLED", "1")
    monkeypatch.setenv("OPSPILOT_MODEL_API_KEY", "test-only-not-a-real-key")
    monkeypatch.setenv("OPSPILOT_MODEL_NAME", "deepseek-flash")
    monkeypatch.setenv("OPSPILOT_MODEL_BASE_URL", "https://api.deepseek.com")

    model = create_assistant_model()

    assert model.model_name == "deepseek-flash"
    assert model.max_tokens is None
    assert model.extra_body == {"max_tokens": 2048}
    assert model.request_timeout == 30
    assert model.max_retries == 0
    assert model.temperature == 0
    assert model.stream_usage is True
    assert model.openai_api_base == "https://api.deepseek.com"


def test_provider_factory_keeps_standard_limit_for_non_deepseek_chatopenai(monkeypatch):
    from opspilot.assistant import create_assistant_model

    monkeypatch.setenv("OPSPILOT_ASSISTANT_PROVIDER_ENABLED", "1")
    monkeypatch.setenv("OPSPILOT_MODEL_API_KEY", "test-only-not-a-real-key")
    monkeypatch.setenv("OPSPILOT_MODEL_NAME", "fixture-compatible-model")
    monkeypatch.setenv("OPSPILOT_MODEL_BASE_URL", "https://example.invalid/v1")

    model = create_assistant_model()

    assert model.max_tokens == 2048
    assert model.extra_body is None
    assert model.max_retries == 0


def test_assistant_factory_emits_deepseek_max_tokens_on_local_mock_wire(monkeypatch):
    from opspilot.assistant import create_assistant_model
    import langchain_openai

    monkeypatch.setenv("OPSPILOT_ASSISTANT_PROVIDER_ENABLED", "1")
    monkeypatch.setenv("OPSPILOT_MODEL_API_KEY", "test-only-not-a-real-key")
    monkeypatch.setenv("OPSPILOT_MODEL_NAME", "deepseek-flash")
    monkeypatch.setenv("OPSPILOT_MODEL_BASE_URL", "https://api.deepseek.com")
    captured = []
    tool = {
        "type": "function",
        "function": {
            "name": "get_order_status",
            "description": "Read the bound order.",
            "parameters": {
                "type": "object",
                "properties": {"reason": {"type": "string"}},
                "required": ["reason"],
            },
        },
    }

    async def run():
        async def respond(request):
            captured.append(json.loads((await request.aread()).decode("utf-8")))
            return httpx.Response(
                200,
                json={
                    "id": "local-mock-completion",
                    "object": "chat.completion",
                    "created": 1,
                    "model": "deepseek-flash",
                    "choices": [{
                        "index": 0,
                        "message": {"role": "assistant", "content": "The local mock answered."},
                        "finish_reason": "stop",
                    }],
                    "usage": {"prompt_tokens": 5, "completion_tokens": 4, "total_tokens": 9},
                },
            )

        client = httpx.AsyncClient(transport=httpx.MockTransport(respond))
        original_chat_openai = langchain_openai.ChatOpenAI

        def local_chat_openai(**kwargs):
            return original_chat_openai(**kwargs, http_async_client=client)

        monkeypatch.setattr(langchain_openai, "ChatOpenAI", local_chat_openai)
        model = create_assistant_model()
        try:
            response = await model.bind_tools(
                [tool], tool_choice="auto", parallel_tool_calls=False,
            ).ainvoke([HumanMessage(content="Read the authorized order.")])
            assert response.content == "The local mock answered."
        finally:
            await client.aclose()

    asyncio.run(run())
    assert len(captured) == 1
    body = captured[0]
    print("LOCAL_MOCK_WIRE_BODY=" + json.dumps(body, sort_keys=True, separators=(",", ":")))
    assert body["model"] == "deepseek-flash"
    assert body["max_tokens"] == 2048
    assert "max_completion_tokens" not in body
    assert body["tool_choice"] == "auto"
    assert body["parallel_tool_calls"] is False
    assert body["tools"][0]["function"]["name"] == "get_order_status"
