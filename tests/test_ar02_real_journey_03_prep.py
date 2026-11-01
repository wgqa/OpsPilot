from __future__ import annotations

import asyncio
import json

import httpx
import pytest


EXPERIMENT_ID = "AR-02-REAL-JOURNEY-03"


def test_real_journey_03_has_fresh_isolated_budget_identity(demo_db):
    from opspilot.domain.assistant_experiment import initialize_experiment, read_budget

    initialize_experiment(demo_db, EXPERIMENT_ID)
    budget = read_budget(demo_db, EXPERIMENT_ID)
    assert budget == {
        "experiment_id": EXPERIMENT_ID,
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


def test_pre_real_journey_database_still_fails_closed_for_new_identity(demo_db):
    from opspilot.domain.assistant_experiment import (
        ExperimentBudgetError,
        initialize_experiment,
    )
    from opspilot.domain.database import connect

    with connect(demo_db) as connection:
        connection.execute(
            """CREATE TABLE ar02_live_experiment_budgets (
                experiment_id TEXT PRIMARY KEY CHECK (experiment_id = 'AR-02-LIVE-01'),
                provider_limit INTEGER NOT NULL,
                mcp_limit INTEGER NOT NULL,
                budget_usd_micro INTEGER NOT NULL,
                price_version TEXT NOT NULL,
                status TEXT NOT NULL CHECK (status IN ('OPEN', 'BUDGET_BREACH')),
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )"""
        )

    initialize_experiment(demo_db, "AR-02-LIVE-01")
    with pytest.raises(ExperimentBudgetError, match="AR02_LIVE_SCHEMA_ID_NOT_SUPPORTED"):
        initialize_experiment(demo_db, EXPERIMENT_ID)


def test_formal_assistant_sdk_wire_contract_uses_mock_transport_only(monkeypatch):
    from langchain_core.messages import HumanMessage, SystemMessage
    from langchain_core.tools import tool
    from opspilot.assistant import create_assistant_model

    monkeypatch.delenv("OPSPILOT_ASSISTANT_PROVIDER_ENABLED", raising=False)
    monkeypatch.setenv("OPSPILOT_ASSISTANT_EXPERIMENT_ID", EXPERIMENT_ID)
    monkeypatch.setenv("OPSPILOT_MODEL_API_KEY", "offline-test-key")
    monkeypatch.setenv("OPSPILOT_MODEL_NAME", "deepseek-flash")
    monkeypatch.setenv("OPSPILOT_MODEL_BASE_URL", "https://api.deepseek.com")

    assert create_assistant_model() is None
    monkeypatch.setenv("OPSPILOT_ASSISTANT_PROVIDER_ENABLED", "1")
    captured: list[httpx.Request] = []

    def response_for(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(
            200,
            headers={"x-request-id": "mock-request-rj03"},
            json={
                "id": "chatcmpl-mock-rj03",
                "object": "chat.completion",
                "created": 1793520000,
                "model": "deepseek-flash",
                "choices": [{
                    "index": 0,
                    "message": {"role": "assistant", "content": "离线报文校验"},
                    "finish_reason": "stop",
                }],
                "usage": {"prompt_tokens": 15, "completion_tokens": 5, "total_tokens": 20},
            },
            request=request,
        )

    async def async_handler(request: httpx.Request) -> httpx.Response:
        return response_for(request)

    @tool
    def search_project_knowledge(query: str) -> str:
        """Read authorized callback protocol documents."""
        return "fixture only"

    model = create_assistant_model(
        transport_async=httpx.MockTransport(async_handler),
        transport_sync=httpx.MockTransport(response_for),
    )
    assert model is not None
    assert model.max_retries == 0
    assert model.request_timeout == 30
    assert model.http_async_client.trust_env is False
    assert model.http_client.trust_env is False
    bound = model.bind_tools(
        [search_project_knowledge],
        tool_choice="auto",
        parallel_tool_calls=False,
    )

    try:
        result = asyncio.run(bound.ainvoke([
            SystemMessage(content="offline wire test"),
            HumanMessage(content="请说明 HTTP 202 的含义。"),
        ]))
        assert result.content == "离线报文校验"
    finally:
        asyncio.run(model.http_async_client.aclose())
        model.http_client.close()

    assert len(captured) == 1
    request = captured[0]
    assert str(request.url) == "https://api.deepseek.com/chat/completions"
    body = json.loads(request.content)
    assert body["model"] == "deepseek-flash"
    assert body["thinking"] == {"type": "disabled"}
    assert body["max_tokens"] == 2048
    assert body["tool_choice"] == "auto"
    assert body["parallel_tool_calls"] is False
    assert body.get("stream", False) is False
    assert "max_completion_tokens" not in body
    assert [tool_spec["function"]["name"] for tool_spec in body["tools"]] == [
        "search_project_knowledge"
    ]
