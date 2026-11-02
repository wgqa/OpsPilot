"""Offline preflight for the separately authorized AR-03-REAL-LLM-02 run."""
from __future__ import annotations

import json
import importlib.util
import time
from pathlib import Path

import httpx
from fastapi.testclient import TestClient

from opspilot.assistant import create_assistant_model
from opspilot.domain.database import connect
from opspilot.domain.s3 import prepare_s3_fixture
from opspilot.web.app import create_app


EXPERIMENT_ID = "AR-03-REAL-LLM-02"
LEGACY_EXPERIMENT_ID = "AR-03-REAL-LLM-01"
ORIGIN = "http://ar03-live-02-offline"
PASSWORDS = {"support-a": "offline-support-02", "approver-a": "offline-approver-02"}
FROZEN_CASES = Path(__file__).resolve().parents[1] / "docs/evidence/ar-03-real-llm-01-prep/CASES.json"
RUNNER_PATH = Path(__file__).resolve().parents[1] / "docs/evidence/ar-03/real-llm-02/run_live.py"


def _load_live_runner():
    spec = importlib.util.spec_from_file_location("ar03_real_llm_02_runner", RUNNER_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_live_pair_stops_on_unknown_usage_or_closed_budget():
    stop_reason = _load_live_runner()._provider_stop_reason

    assert stop_reason([{"status": "OK", "usage_state": "KNOWN"}], "OPEN") is None
    assert stop_reason([{"status": "RESERVED", "usage_state": "UNKNOWN"}], "BUDGET_BREACH") == (
        "UNKNOWN_PROVIDER_RESULT_OR_USAGE_STOP_ALL"
    )
    assert stop_reason([{"status": "OK", "usage_state": "UNKNOWN"}], "OPEN") == (
        "UNKNOWN_PROVIDER_RESULT_OR_USAGE_STOP_ALL"
    )
    assert stop_reason([{"status": "OK", "usage_state": "VIOLATION"}], "BUDGET_BREACH") == (
        "PROVIDER_USAGE_VIOLATION_STOP_ALL"
    )
    assert stop_reason([], "BUDGET_BREACH") == "EXPERIMENT_BUDGET_CLOSED_STOP_ALL"


def test_live_wire_refuses_context_over_approved_limit_before_http_dispatch(tmp_path):
    import httpx
    import pytest

    runner = _load_live_runner()
    state = runner._LiveRequestState(tmp_path / "provider-http.jsonl")
    body = {
        "model": "deepseek-flash",
        "max_tokens": 2048,
        "thinking": {"type": "disabled"},
        "stream": False,
        "tools": [],
        "messages": [{"role": "user", "content": "x " * 13_000}],
    }
    raw = json.dumps(body).encode("utf-8")
    request = httpx.Request(
        "POST",
        "https://api.deepseek.com/v1/chat/completions",
        content=raw,
    )

    with pytest.raises(RuntimeError, match="LIVE_CONTEXT_INPUT_LIMIT_EXCEEDED"):
        state.begin("A", request, raw)
    assert state.count == 0
    assert state.inflight == 0
    assert not state.provider_path.exists()


def _wait_run(client, run_id: str) -> dict:
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        response = client.get(f"/api/runs/{run_id}")
        assert response.status_code == 200, response.text
        run = response.json()
        if run["status"] in {"SUCCEEDED", "FAILED", "BLOCKED", "CANCELLED"}:
            return run
        time.sleep(0.05)
    raise AssertionError(f"Run did not finish within preflight timeout: {run_id}")


def test_real_llm_02_has_fresh_per_scenario_budget_and_does_not_open_01(demo_db):
    from opspilot.domain.assistant_experiment import initialize_experiment, read_budget

    initialize_experiment(demo_db, EXPERIMENT_ID)

    new = read_budget(demo_db, EXPERIMENT_ID)
    old = read_budget(demo_db, LEGACY_EXPERIMENT_ID)
    assert new["initialized"] is True
    assert new["status"] == "OPEN"
    assert new["provider_limit"] == 8
    assert new["mcp_limit"] == 6
    assert new["budget_usd_micro"] == 10_500_000
    assert new["provider_used"] == new["mcp_used"] == 0
    assert old["initialized"] is False

    with connect(demo_db) as connection:
        rows = connection.execute(
            "SELECT experiment_id FROM ar02_live_experiment_budgets"
        ).fetchall()
        assert [str(row["experiment_id"]) for row in rows] == [EXPERIMENT_ID]
        schema = connection.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='ar02_live_experiment_budgets'"
        ).fetchone()["sql"]
        assert "'AR-03-REAL-LLM-02'" in schema


def test_frozen_goal_uses_one_trusted_api_run_and_mocked_wire(demo_db, tmp_path, monkeypatch):
    from opspilot.domain.assistant_experiment import EXPERIMENT_ENV, read_budget

    monkeypatch.setenv(EXPERIMENT_ENV, EXPERIMENT_ID)
    monkeypatch.setenv("OPSPILOT_ASSISTANT_PROVIDER_ENABLED", "1")
    monkeypatch.setenv("OPSPILOT_MODEL_API_KEY", "offline-placeholder-not-a-credential")
    monkeypatch.setenv("OPSPILOT_MODEL_NAME", "deepseek-flash")
    monkeypatch.setenv("OPSPILOT_MODEL_BASE_URL", "https://api.deepseek.com/v1")
    prepare_s3_fixture(demo_db, "DELIVERED_PENDING", order_id="ar03-order", contract_version=2)
    prompt = json.loads(FROZEN_CASES.read_text(encoding="utf-8"))["prompt"]

    captured: list[dict] = []
    captured_urls: list[str] = []

    async def respond(request: httpx.Request) -> httpx.Response:
        captured_urls.append(str(request.url))
        captured.append(json.loads((await request.aread()).decode("utf-8")))
        return httpx.Response(
            200,
            headers={"x-request-id": "offline-ar03-live-02-wire"},
            json={
                "id": "offline-ar03-live-02-completion",
                "object": "chat.completion",
                "created": 1,
                "model": "deepseek-flash",
                "choices": [{
                    "index": 0,
                    "message": {"role": "assistant", "content": "MockTransport 预检回答，不代表真实模型效果。"},
                    "finish_reason": "stop",
                }],
                "usage": {"prompt_tokens": 60, "completion_tokens": 9, "total_tokens": 69},
            },
        )

    def factory():
        return create_assistant_model(
            transport_async=httpx.MockTransport(respond),
            transport_sync=httpx.MockTransport(lambda _request: httpx.Response(500)),
        )

    app = create_app(
        db_path=demo_db,
        checkpoint_db_path=tmp_path / "ar03-live-02-mock-checkpoint.sqlite3",
        start_worker=True,
        credentials=PASSWORDS,
        expected_origin=ORIGIN,
        assistant_model_factory=factory,
        assistant_experiment_id=EXPERIMENT_ID,
    )
    with TestClient(app) as client:
        login = client.post(
            "/api/auth/login",
            headers={"Origin": ORIGIN},
            json={"actor_id": "support-a", "password": PASSWORDS["support-a"]},
        )
        assert login.status_code == 200, login.text
        headers = {"Origin": ORIGIN, "X-CSRF-Token": login.json()["csrf_token"]}
        session_id = client.post("/api/sessions", headers=headers).json()["session_id"]
        accepted = client.post(
            f"/api/sessions/{session_id}/assistant/order",
            headers={**headers, "Idempotency-Key": "ar03-real-llm-02-one-frozen-goal"},
            json={"order_id": "ar03-order", "initial_message": prompt},
        )
        assert accepted.status_code == 202, accepted.text
        run = _wait_run(client, accepted.json()["run_id"])
        assert run["status"] == "SUCCEEDED", run

        items = client.get(f"/api/sessions/{session_id}/messages").json()["items"]
        user_messages = [item for item in items if item["role"] == "USER"]
        answers = [item for item in items if item.get("answer_source_message_id") == accepted.json()["message_id"]]
        assert len(user_messages) == 1
        assert user_messages[0]["message_id"] == accepted.json()["message_id"]
        assert user_messages[0]["body"] == prompt
        assert len(answers) == 1

        with connect(demo_db) as connection:
            runs = connection.execute(
                "SELECT run_id FROM task_runs WHERE session_id=?", (session_id,)
            ).fetchall()
            assert [str(row["run_id"]) for row in runs] == [accepted.json()["run_id"]]
            assistant_core = connection.execute(
                "SELECT core FROM assistant_runs WHERE run_id=?", (accepted.json()["run_id"],)
            ).fetchone()
            assert assistant_core["core"] == "ASSISTANT_V1"

    assert len(captured) == len(captured_urls) == 1
    assert captured_urls == ["https://api.deepseek.com/v1/chat/completions"]
    body = captured[0]
    assert body["model"] == "deepseek-flash"
    assert body["max_tokens"] == 2048
    assert body["thinking"] == {"type": "disabled"}
    assert body["tool_choice"] == "auto"
    assert body["parallel_tool_calls"] is False
    assert body["stream"] is False
    assert "max_completion_tokens" not in body
    assert {tool["function"]["name"] for tool in body["tools"]} >= {
        "list_scoped_protocol_documents",
        "compare_scoped_protocols",
        "get_order_status",
        "get_callback_delivery",
        "get_receiver_processing",
    }

    budget = read_budget(demo_db, EXPERIMENT_ID)
    assert budget["status"] == "OPEN"
    assert budget["provider_used"] == 1
    assert budget["mcp_used"] == 0
    assert budget["usd_reserved_micro"] == 0
    assert budget["usd_settled_micro"] > 0
