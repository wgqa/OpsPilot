"""Offline test of the one-shot live runner's HTTPX trace boundary."""

from __future__ import annotations

import asyncio
import importlib.util
import json
from pathlib import Path

import httpx


def _runner_module():
    path = (
        Path(__file__).resolve().parents[1]
        / "docs" / "evidence" / "ar-03" / "real-llm-01" / "run_live.py"
    )
    spec = importlib.util.spec_from_file_location("ar03_live_runner_for_test", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_live_trace_transport_records_mocked_wire_and_redacts_auth(tmp_path, monkeypatch):
    monkeypatch.setenv("OPSPILOT_MODEL_API_KEY", "test-secret-not-for-trace")
    module = _runner_module()
    trace_path = tmp_path / "provider-http.jsonl"
    state = module._LiveRequestState(trace_path)
    delegated: list[str] = []
    body = {
        "model": "deepseek-flash",
        "max_tokens": 2048,
        "thinking": {"type": "disabled"},
        "tool_choice": "auto",
        "parallel_tool_calls": False,
        "stream": False,
        "messages": [{"role": "user", "content": "仅作离线协议检查"}],
        "tools": [{"type": "function", "function": {"name": "get_order_status"}}],
    }

    async def response(request: httpx.Request) -> httpx.Response:
        delegated.append(str(request.url))
        return httpx.Response(
            200,
            request=request,
            headers={"x-request-id": "offline-trace-request"},
            json={"id": "offline-trace-completion", "model": "deepseek-flash", "usage": {"prompt_tokens": 1}},
        )

    async def execute():
        transport = module._RecordingAsyncTransport(
            state, "A", inner=httpx.MockTransport(response),
        )
        async with httpx.AsyncClient(
            transport=transport,
            headers={"Authorization": "Bearer test-secret-not-for-trace"},
        ) as client:
            result = await client.post(
                "https://api.deepseek.com/v1/chat/completions", json=body,
            )
            assert result.status_code == 200
            assert result.json()["id"] == "offline-trace-completion"

    asyncio.run(execute())

    records = [json.loads(line) for line in trace_path.read_text(encoding="utf-8").splitlines()]
    assert delegated == ["https://api.deepseek.com/v1/chat/completions"]
    assert [row["record_type"] for row in records] == [
        "provider_http_request", "provider_http_response",
    ]
    assert records[0]["body"] == body
    assert records[1]["status_code"] == 200
    assert records[1]["headers"]["x-request-id"] == "offline-trace-request"
    trace_text = trace_path.read_text(encoding="utf-8")
    assert "test-secret-not-for-trace" not in trace_text
    assert "authorization" not in trace_text.lower()
    assert state.count == 1 and state.inflight == 0


def test_live_trace_transport_refuses_wrong_wire_before_mock_dispatch(tmp_path):
    module = _runner_module()
    trace_path = tmp_path / "provider-http.jsonl"
    state = module._LiveRequestState(trace_path)
    delegated: list[str] = []

    async def response(request: httpx.Request) -> httpx.Response:
        delegated.append(str(request.url))
        return httpx.Response(200, request=request, json={"id": "should-not-send"})

    invalid_body = {
        "model": "deepseek-flash",
        "max_tokens": 512,
        "thinking": {"type": "disabled"},
        "stream": False,
    }

    async def execute():
        transport = module._RecordingAsyncTransport(
            state, "A", inner=httpx.MockTransport(response),
        )
        async with httpx.AsyncClient(transport=transport) as client:
            try:
                await client.post("https://api.deepseek.com/v1/chat/completions", json=invalid_body)
            except RuntimeError as error:
                assert str(error) == "LIVE_WIRE_OUTPUT_CONFIGURATION_MISMATCH"
            else:
                raise AssertionError("wire mismatch was not blocked")

    asyncio.run(execute())
    assert delegated == []
    assert not trace_path.exists()
    assert state.count == 0 and state.inflight == 0
