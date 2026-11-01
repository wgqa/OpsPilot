"""Offline-only AR-03 real-LLM preparation checks.

All Provider-shaped traffic in this module is captured by HTTPX MockTransport.
It is not evidence of a real DeepSeek call or model autonomy.
"""
from __future__ import annotations

import json
import hashlib
import os
import time
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from opspilot.domain.database import connect
from opspilot.web.app import create_app


EXPERIMENT_ID = "AR-03-REAL-LLM-01"
LEGACY_EXPERIMENT_ID = "AR-02-REAL-JOURNEY-03"
ORIGIN = "http://testserver"
PASSWORDS = {
    "support-a": "free-local-a",
    "support-b": "free-local-b",
    "approver-a": "free-approver",
}


def _login(client):
    response = client.post(
        "/api/auth/login",
        headers={"Origin": ORIGIN},
        json={"actor_id": "support-a", "password": PASSWORDS["support-a"]},
    )
    assert response.status_code == 200, response.text
    return {"Origin": ORIGIN, "X-CSRF-Token": response.json()["csrf_token"]}


def _wait_run(client, run_id):
    deadline = time.monotonic() + 15
    while True:
        response = client.get("/api/runs/" + run_id)
        assert response.status_code == 200, response.text
        run = response.json()
        if run["status"] in {"SUCCEEDED", "FAILED", "BLOCKED"}:
            return run
        assert time.monotonic() < deadline, run
        time.sleep(0.05)


def _append_trace(row):
    target = os.environ.get("AR03_PREP_TRACE_PATH")
    if not target:
        return
    path = Path(target)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def test_new_experiment_id_initializes_an_independent_fixed_budget(demo_db):
    from opspilot.domain.assistant_experiment import (
        BUDGET_USD_MICRO,
        read_budget,
        initialize_experiment,
    )

    initialize_experiment(demo_db, EXPERIMENT_ID)

    new_budget = read_budget(demo_db, EXPERIMENT_ID)
    old_budget = read_budget(demo_db, LEGACY_EXPERIMENT_ID)
    assert new_budget["initialized"] is True
    assert new_budget["status"] == "OPEN"
    # The live A/B run uses two separate databases, so each database receives
    # half of the approved experiment-wide count ceiling.
    assert new_budget["provider_limit"] == 8
    assert new_budget["mcp_limit"] == 6
    assert new_budget["budget_usd_micro"] == BUDGET_USD_MICRO == 10_500_000
    assert new_budget["provider_used"] == new_budget["mcp_used"] == 0
    assert old_budget["initialized"] is False


def test_new_experiment_id_fails_closed_against_a_legacy_schema(tmp_path):
    from opspilot.domain.assistant_experiment import (
        ExperimentBudgetError,
        initialize_experiment,
    )

    stale_db = tmp_path / "legacy-experiment-schema.sqlite3"
    with connect(stale_db) as connection:
        connection.execute(
            """CREATE TABLE ar02_live_experiment_budgets (
                experiment_id TEXT PRIMARY KEY CHECK (experiment_id IN (
                    'AR-02-LIVE-01', 'AR-02-REAL-JOURNEY-01',
                    'AR-02-REAL-JOURNEY-02', 'AR-02-REAL-JOURNEY-03'
                )),
                provider_limit INTEGER NOT NULL,
                mcp_limit INTEGER NOT NULL,
                budget_usd_micro INTEGER NOT NULL,
                price_version TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )"""
        )

    with pytest.raises(ExperimentBudgetError, match="AR02_LIVE_SCHEMA_ID_NOT_SUPPORTED"):
        initialize_experiment(stale_db, EXPERIMENT_ID)


def test_api_key_alone_does_not_enable_the_new_experiment(monkeypatch):
    from opspilot.assistant import create_assistant_model
    from opspilot.domain.assistant_experiment import EXPERIMENT_ENV

    monkeypatch.setenv(EXPERIMENT_ENV, EXPERIMENT_ID)
    monkeypatch.setenv("OPSPILOT_MODEL_API_KEY", "offline-placeholder-not-a-credential")
    monkeypatch.setenv("OPSPILOT_MODEL_NAME", "deepseek-flash")
    monkeypatch.setenv("OPSPILOT_MODEL_BASE_URL", "https://api.deepseek.com/v1")
    monkeypatch.delenv("OPSPILOT_ASSISTANT_PROVIDER_ENABLED", raising=False)

    assert create_assistant_model() is None


def test_formal_api_worker_mocktransport_uses_new_isolated_experiment(
    demo_db, tmp_path, monkeypatch,
):
    from opspilot.assistant import create_assistant_model
    from opspilot.domain.assistant_experiment import (
        EXPERIMENT_ENV,
        read_budget,
    )

    monkeypatch.setenv(EXPERIMENT_ENV, EXPERIMENT_ID)
    monkeypatch.setenv("OPSPILOT_ASSISTANT_PROVIDER_ENABLED", "1")
    monkeypatch.setenv("OPSPILOT_MODEL_API_KEY", "offline-placeholder-not-a-credential")
    monkeypatch.setenv("OPSPILOT_MODEL_NAME", "deepseek-flash")
    monkeypatch.setenv("OPSPILOT_MODEL_BASE_URL", "https://api.deepseek.com/v1")

    captured: list[dict] = []
    captured_urls: list[str] = []

    async def respond(request: httpx.Request) -> httpx.Response:
        captured_urls.append(str(request.url))
        captured.append(json.loads((await request.aread()).decode("utf-8")))
        return httpx.Response(
            200,
            headers={"x-request-id": "offline-ar03-mock-request"},
            json={
                "id": "offline-ar03-mock-completion",
                "object": "chat.completion",
                "created": 1,
                "model": "deepseek-flash",
                "choices": [{
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": (
                            "HTTP 202 表示传输层已受理，不证明 Receiver 已处理完成；"
                            "本轮没有订单绑定或当前 Receiver Observation，因此业务状态未知。"
                        ),
                    },
                    "finish_reason": "stop",
                }],
                "usage": {
                    "prompt_tokens": 71,
                    "completion_tokens": 28,
                    "total_tokens": 99,
                },
            },
        )

    def model_factory():
        return create_assistant_model(
            transport_async=httpx.MockTransport(respond),
            transport_sync=httpx.MockTransport(lambda request: httpx.Response(500)),
        )

    app = create_app(
        db_path=demo_db,
        checkpoint_db_path=tmp_path / "ar03-prep-checkpoint.sqlite3",
        start_worker=True,
        credentials=PASSWORDS,
        expected_origin=ORIGIN,
        assistant_model_factory=model_factory,
        assistant_experiment_id=EXPERIMENT_ID,
    )

    with TestClient(app) as client:
        headers = _login(client)
        session_id = client.post("/api/sessions", headers=headers).json()["session_id"]
        message_body = (
            "我在排查回调协议升级对重试行为的影响；请按需要查询授权资料或业务状态，"
            "不能确认的地方请说明。"
        )
        accepted = client.post(
            f"/api/sessions/{session_id}/assistant/messages",
            headers={**headers, "Idempotency-Key": "ar03-prep-formal-worker"},
            json={"body": message_body},
        )
        assert accepted.status_code == 202, accepted.text
        run = _wait_run(client, accepted.json()["run_id"])
        assert run["status"] == "SUCCEEDED", run
        messages = client.get(f"/api/sessions/{session_id}/messages").json()["items"]
        answer = next(
            item["body"] for item in messages
            if item.get("answer_source_message_id") == accepted.json()["message_id"]
        )
        assert "HTTP 202" in answer and "未知" in answer

    assert len(captured) == len(captured_urls) == 1
    assert captured_urls[0] == "https://api.deepseek.com/v1/chat/completions"
    body = captured[0]
    assert body["model"] == "deepseek-flash"
    assert body["max_tokens"] == 2048
    assert body["thinking"] == {"type": "disabled"}
    assert body["tool_choice"] == "auto"
    assert body["parallel_tool_calls"] is False
    assert body["stream"] is False
    assert "max_completion_tokens" not in body
    tool_names = {tool["function"]["name"] for tool in body["tools"]}
    assert {"list_scoped_protocol_documents", "compare_scoped_protocols"} <= tool_names
    assert not {
        "get_order_status", "get_callback_delivery", "get_receiver_processing",
    } & tool_names

    with connect(demo_db) as connection:
        persisted_run = connection.execute(
            "SELECT task_id,status FROM task_runs WHERE run_id=?",
            (accepted.json()["run_id"],),
        ).fetchone()
        assert persisted_run["task_id"] is None
        assert persisted_run["status"] == "SUCCEEDED"
        assert connection.execute(
            "SELECT COUNT(*) FROM task_bindings"
        ).fetchone()[0] == 0
        assert connection.execute(
            "SELECT COUNT(*) FROM assistant_calls WHERE run_id=? AND kind='MCP'",
            (accepted.json()["run_id"],),
        ).fetchone()[0] == 0
        for table in (
            "s3_diagnoses", "d3_plans", "d3_approvals", "d3_action_permissions",
            "d3_action_intents", "d3_action_ledgers", "s2_handoff_queue_entries",
            "s2_handoff_receipts", "s3_handoff_queue_entries", "s3_handoff_receipts",
        ):
            assert connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0
        model_call = connection.execute(
            "SELECT request_json FROM assistant_calls WHERE run_id=? AND kind='MODEL'",
            (accepted.json()["run_id"],),
        ).fetchone()
        assert model_call is not None
        model_request = json.loads(model_call["request_json"])
        assert model_request["context_budget"]["estimated_input_tokens"] <= 12_000

    budget = read_budget(demo_db, EXPERIMENT_ID)
    assert budget["provider_used"] == 1
    assert budget["mcp_used"] == 0
    assert budget["usd_reserved_micro"] == 0
    assert budget["usd_settled_micro"] > 0
    assert budget["status"] == "OPEN"
    assert read_budget(demo_db, LEGACY_EXPERIMENT_ID)["initialized"] is False
    body_digest = hashlib.sha256(
        json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    _append_trace({
        "record_type": "formal_api_worker_provider_mock",
        "evidence_level": "LOCAL_HTTPX_MOCKTRANSPORT_NOT_REAL_PROVIDER",
        "experiment_id": EXPERIMENT_ID,
        "session_id": session_id,
        "source_message_id": accepted.json()["message_id"],
        "run_id": accepted.json()["run_id"],
        "run_status": run["status"],
        "provider_http_request_count": len(captured),
        "url": captured_urls[0],
        "request_body_sha256": body_digest,
        "request_body": body,
        "model": body["model"],
        "wire_parameters": {
            "max_tokens": body["max_tokens"],
            "thinking": body["thinking"],
            "tool_choice": body["tool_choice"],
            "parallel_tool_calls": body["parallel_tool_calls"],
            "stream": body["stream"],
            "has_max_completion_tokens": "max_completion_tokens" in body,
        },
        "offered_tools": sorted(tool_names),
        "mock_request_id": "offline-ar03-mock-request",
        "mock_completion_id": "offline-ar03-mock-completion",
        "mock_usage": {"input_tokens": 71, "output_tokens": 28, "total_tokens": 99},
        "user_input": message_body,
        "persisted_answer": answer,
        "mcp_calls": 0,
        "business_task_binding_created": False,
        "experiment_budget": budget,
    })
