"""Mock-only probe for the no-tool-call boundary in the accepted live runner."""
from __future__ import annotations

import asyncio
import json
import sys
import tempfile
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[4]
RUNNER_DIR = ROOT / "docs/evidence/abc-live-env-unblock-01"
sys.path.insert(0, str(RUNNER_DIR))

import run_abc_eval as abc_runner


async def main() -> int:
    inner_calls = 0

    async def respond(_request: httpx.Request) -> httpx.Response:
        nonlocal inner_calls
        inner_calls += 1
        return httpx.Response(200, json={
            "id": "mock-unexpected-tool-call", "object": "chat.completion", "created": 1,
            "model": "deepseek-flash",
            "choices": [{
                "index": 0,
                "message": {
                    "role": "assistant", "content": None,
                    "tool_calls": [{
                        "id": "call-mock-only", "type": "function",
                        "function": {"name": "list_scoped_protocol_documents", "arguments": "{}"},
                    }],
                },
                "finish_reason": "tool_calls",
            }],
            "usage": {"prompt_tokens": 12, "completion_tokens": 1, "total_tokens": 13},
        })

    with tempfile.TemporaryDirectory(prefix="ar04-unexpected-toolcall-mock-") as temp:
        root = Path(temp)
        ledger = abc_runner.GlobalBudgetLedger.create(
            root / "ledger.json", execution_id="mock-only", mode="MOCK",
        )
        transport = abc_runner.BudgetedAsyncTransport(
            inner=httpx.MockTransport(respond), ledger=ledger, case_id="Q02-B", mode="MOCK",
            trace_path=root / "trace.jsonl.gz",
        )
        payload = {
            "model": "deepseek-flash", "thinking": {"type": "disabled"},
            "temperature": 0, "stream": False, "tool_choice": "none", "max_tokens": 512,
            "tools": [{
                "type": "function", "function": {
                    "name": "list_scoped_protocol_documents", "description": "mock only",
                    "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
                },
            }],
            "messages": [{"role": "user", "content": "MOCK_ONLY"}],
        }
        client = httpx.AsyncClient(transport=transport, trust_env=False)
        try:
            response = await client.post(
                "https://api.deepseek.com/chat/completions",
                content=json.dumps(payload, separators=(",", ":")).encode("utf-8"),
                headers={"content-type": "application/json"},
            )
        finally:
            await client.aclose()

        returned = response.json()["choices"][0]
        tool_calls_reached_assistant_response = bool(returned["message"].get("tool_calls"))
        stop_reason = ledger.state.get("stop_reason")
        assert inner_calls == 1
        assert tool_calls_reached_assistant_response
        assert stop_reason == "PROVIDER_OUTPUT_NOT_COMPLETE"
        assert transport.calls[0]["stop_reason"] == "PROVIDER_OUTPUT_NOT_COMPLETE"
        print({
            "evidence_level": "MOCKTRANSPORT_ONLY",
            "request_tool_choice": payload["tool_choice"],
            "provider_mock_response_finish_reason": "tool_calls",
            "transport_stop_reason": stop_reason,
            "tool_calls_reached_assistant_response": tool_calls_reached_assistant_response,
            "mock_transport_invocations": inner_calls,
            "external_mcp_invocations": 0,
            "provider_requests_sent": 0,
        })
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
