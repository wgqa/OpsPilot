"""Offline preflight for the separately authorized AR-02 journey 02 identity."""

from __future__ import annotations

import asyncio
import json

import httpx


EXPERIMENT = "AR-02-REAL-JOURNEY-02"


def test_journey_02_initializes_an_independent_budget_identity(tmp_path):
    from opspilot.domain.assistant_experiment import initialize_experiment, read_budget
    from opspilot.domain.database import reset_fixture

    db_path = tmp_path / "ar02-journey-02.sqlite3"
    reset_fixture(db_path, "S1_POS")
    initialize_experiment(db_path, EXPERIMENT)

    snapshot = read_budget(db_path, EXPERIMENT)
    assert snapshot == {
        "experiment_id": EXPERIMENT,
        "initialized": True,
        "status": "OPEN",
        "provider_limit": 16,
        "provider_used": 0,
        "mcp_limit": 12,
        "mcp_used": 0,
        "budget_usd_micro": 10_500_000,
        "usd_reserved_micro": 0,
        "usd_settled_micro": 0,
        "usd_remaining_micro": 10_500_000,
        "price_version": "DEEPSEEK_FLASH_PEAK_2026-11-01",
    }


def test_formal_app_accepts_journey_02_only_with_its_explicit_identity(
    demo_db, tmp_path, monkeypatch,
):
    from fastapi.testclient import TestClient

    from opspilot.domain.assistant_experiment import read_budget
    from opspilot.web.app import create_app

    monkeypatch.delenv("OPSPILOT_ASSISTANT_EXPERIMENT_ID", raising=False)
    monkeypatch.delenv("OPSPILOT_ASSISTANT_PROVIDER_ENABLED", raising=False)
    app = create_app(
        db_path=demo_db,
        checkpoint_db_path=tmp_path / "ar02-journey-02-checkpoint.sqlite3",
        start_worker=False,
        assistant_experiment_id=EXPERIMENT,
        assistant_model_factory=lambda: None,
    )
    with TestClient(app):
        assert app.state.assistant_experiment_id == EXPERIMENT
        snapshot = read_budget(demo_db, EXPERIMENT)
        assert snapshot["initialized"] is True
        assert snapshot["provider_used"] == 0
        assert snapshot["mcp_used"] == 0


def test_journey_02_offline_sdk_wire_is_the_frozen_deepseek_request(monkeypatch):
    from opspilot.assistant import create_assistant_model

    monkeypatch.setenv("OPSPILOT_ASSISTANT_PROVIDER_ENABLED", "1")
    monkeypatch.setenv("OPSPILOT_ASSISTANT_EXPERIMENT_ID", EXPERIMENT)
    monkeypatch.setenv("OPSPILOT_MODEL_API_KEY", "offline-mock-only")
    monkeypatch.setenv("OPSPILOT_MODEL_NAME", "deepseek-flash")
    monkeypatch.setenv("OPSPILOT_MODEL_BASE_URL", "https://api.deepseek.com")
    captured = []

    async def mock_response(request: httpx.Request) -> httpx.Response:
        captured.append({
            "method": request.method,
            "url": str(request.url),
            "body": json.loads((await request.aread()).decode("utf-8")),
        })
        return httpx.Response(200, json={
            "id": "offline-ar02-journey-02",
            "object": "chat.completion",
            "created": 1,
            "model": "deepseek-flash",
            "choices": [{"index": 0, "message": {"role": "assistant", "content": "offline"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        })

    model = create_assistant_model(
        transport_async=httpx.MockTransport(mock_response),
        transport_sync=httpx.MockTransport(lambda request: httpx.Response(500)),
    )
    tool = {
        "type": "function",
        "function": {
            "name": "search_callback_knowledge",
            "description": "Search authorized callback protocol materials.",
            "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]},
        },
    }

    async def invoke() -> None:
        response = await model.bind_tools(
            [tool], tool_choice="auto", parallel_tool_calls=False,
        ).ainvoke("检索适用的回调协议。")
        assert response.content == "offline"

    try:
        asyncio.run(invoke())
    finally:
        asyncio.run(model.http_async_client.aclose())
        model.http_client.close()

    assert len(captured) == 1
    sent = captured[0]
    body = sent["body"]
    assert sent["method"] == "POST"
    assert sent["url"] == "https://api.deepseek.com/chat/completions"
    assert body["model"] == "deepseek-flash"
    assert body["thinking"] == {"type": "disabled"}
    assert body["max_tokens"] == 2048
    assert body["tool_choice"] == "auto"
    assert body["parallel_tool_calls"] is False
    assert body["tools"][0]["function"]["name"] == "search_callback_knowledge"
    assert body["stream"] is False
    assert "max_completion_tokens" not in body
