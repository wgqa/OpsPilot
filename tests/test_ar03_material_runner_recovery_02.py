from __future__ import annotations

import asyncio
import importlib.util
import json
import uuid
from pathlib import Path

import httpx
import pytest


ROOT = Path(__file__).resolve().parents[1]
RESUME_RUNNER_PATH = ROOT / "docs/evidence/ar-03/material-live-01/resume-01/run_live.py"
EXPERIMENT_ID = "AR-03-MATERIAL-LIVE-01-RESUME-01"
CASE_ID = "MAT-01-PROTOCOL-EXCERPT"


def _load_runner():
    spec = importlib.util.spec_from_file_location("ar03_material_resume_runner_recovery_02", RESUME_RUNNER_PATH)
    assert spec is not None and spec.loader is not None
    resume = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(resume)
    return resume._bound_base_runner()


def _prepare_campaign(runner, tmp_path: Path, monkeypatch):
    from opspilot.domain.assistant_experiment import initialize_experiment

    runner.DOMAIN_DB = tmp_path / "domain.sqlite3"
    runner.CHECKPOINT_DB = tmp_path / "checkpoints.sqlite3"
    runner.EVIDENCE = tmp_path / "evidence"
    runner.EVIDENCE.mkdir()
    runner._bootstrap_fresh_campaign_database(runner.DOMAIN_DB)
    initialize_experiment(runner.DOMAIN_DB, EXPERIMENT_ID)

    monkeypatch.setenv("OPSPILOT_ASSISTANT_PROVIDER_ENABLED", "0")
    monkeypatch.setenv("OPSPILOT_ASSISTANT_EXPERIMENT_ID", EXPERIMENT_ID)
    return runner


def _accepted_mat01(runner):
    return runner._create_user_run(CASE_ID, runner._case_inputs()[CASE_ID], bound=False)


def _authorized_request_body(*, max_tokens=2048):
    return {
        "model": "deepseek-flash",
        "thinking": {"type": "disabled"},
        "max_tokens": max_tokens,
        "stream": False,
        "tool_choice": "auto",
        "parallel_tool_calls": False,
        "messages": [{"role": "user", "content": "Offline transport guard check."}],
        "tools": [{
            "type": "function",
            "function": {
                "name": "list_scoped_protocol_documents",
                "description": "List documents in the trusted session scope.",
                "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
            },
        }],
    }


def test_campaign_begin_accepts_valid_durable_reservation_and_authoritative_price_version(tmp_path, monkeypatch):
    runner = _prepare_campaign(_load_runner(), tmp_path, monkeypatch)
    accepted = _accepted_mat01(runner)

    from opspilot.domain.assistant_experiment import PRICE_VERSION, reserve_dispatch
    from opspilot.domain.d2 import canonical_json, digest_json, utc_now
    from opspilot.domain.database import connect

    logical_key = "offline-valid-provider-call"
    request_body = _authorized_request_body()
    request_digest = digest_json(request_body)
    with connect(runner.DOMAIN_DB) as connection:
        connection.execute(
            "INSERT INTO assistant_calls(call_id,run_id,kind,logical_key,request_json,request_digest,status,created_at) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (
                "assistant-call-" + uuid.uuid4().hex, accepted["run_id"], "MODEL", logical_key,
                canonical_json(request_body), request_digest, "RESERVED", utc_now(),
            ),
        )
    reserve_dispatch(
        runner.DOMAIN_DB, experiment_id=EXPERIMENT_ID, run_id=accepted["run_id"],
        kind="MODEL", logical_key=logical_key, request=request_body,
    )
    state = runner._CampaignState(tmp_path / "provider.jsonl", runner.DOMAIN_DB)
    state.case_id = CASE_ID
    state.run_id = accepted["run_id"]
    body = request_body
    request = httpx.Request(
        "POST", "https://api.deepseek.com/v1/chat/completions",
        content=json.dumps(body).encode("utf-8"), headers={"content-type": "application/json"},
    )

    assert PRICE_VERSION
    assert state.begin(request, request.content) == 1
    assert state.request_count == 1
    assert state.inflight == 1


def _run_formal_mock_mat01(tmp_path, monkeypatch, *, fail_transport: bool):
    runner = _prepare_campaign(_load_runner(), tmp_path, monkeypatch)
    from opspilot.assistant import create_assistant_model
    from opspilot.domain.assistant_experiment import read_budget
    from opspilot.domain.database import connect
    from opspilot.web.app import create_app

    monkeypatch.setenv("OPSPILOT_ASSISTANT_PROVIDER_ENABLED", "1")
    monkeypatch.setenv("OPSPILOT_ASSISTANT_EXPERIMENT_ID", EXPERIMENT_ID)
    monkeypatch.setenv("OPSPILOT_MODEL_NAME", "deepseek-flash")
    monkeypatch.setenv("OPSPILOT_MODEL_API_KEY", "offline-placeholder-not-a-secret")
    monkeypatch.setenv("OPSPILOT_MODEL_BASE_URL", "https://api.deepseek.com/v1")
    monkeypatch.setattr("opspilot.assistant._material_resume_one_shot_authorized", lambda _experiment_id: True)

    state = runner._CampaignState(tmp_path / "provider.jsonl", runner.DOMAIN_DB)
    wire_requests = []
    pending_before_send = []

    def handler(request):
        wire_requests.append(request)
        body = json.loads(request.content)
        assert request.method == "POST"
        assert str(request.url) == "https://api.deepseek.com/v1/chat/completions"
        assert body["model"] == "deepseek-flash"
        assert body["thinking"] == {"type": "disabled"}
        assert body["max_tokens"] == 2048
        assert "max_completion_tokens" not in body
        assert body["stream"] is False
        assert body["tool_choice"] == "auto"
        assert body["parallel_tool_calls"] is False
        assert body["tools"]
        tool_names = {item["function"]["name"] for item in body["tools"]}
        assert tool_names <= runner.ALLOWED_TOOLS
        assert not tool_names & {
            "get_order_status", "get_callback_delivery", "get_receiver_processing",
            "get_callback_transport_history",
        }
        budget = read_budget(runner.DOMAIN_DB, EXPERIMENT_ID)
        with connect(runner.DOMAIN_DB) as connection:
            dispatches = connection.execute(
                "SELECT status,run_id,kind FROM ar02_live_dispatches WHERE experiment_id=? AND kind='MODEL'",
                (EXPERIMENT_ID,),
            ).fetchall()
            calls = connection.execute(
                "SELECT status,run_id,kind FROM assistant_calls WHERE kind='MODEL'",
            ).fetchall()
        pending_before_send.append((budget, [dict(row) for row in dispatches], [dict(row) for row in calls]))
        assert budget["provider_used"] == 1
        assert len(dispatches) == len(calls) == 1
        assert dispatches[0]["status"] == calls[0]["status"] == "RESERVED"
        if fail_transport:
            raise httpx.ConnectError("synthetic offline transport failure", request=request)
        return httpx.Response(200, json={
            "id": "chatcmpl-offline-ar03-recovery-02",
            "object": "chat.completion",
            "created": 1793740000,
            "model": "deepseek-flash",
            "choices": [{
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": "HTTP 202 表示回调请求已被接收，不足以证明 Receiver 已完成业务处理。",
                },
                "finish_reason": "stop",
            }],
            "usage": {"prompt_tokens": 92, "completion_tokens": 25, "total_tokens": 117},
        })

    mock_transport = httpx.MockTransport(handler)

    def model_factory():
        return create_assistant_model(
            transport_async=runner._RecordingAsyncTransport(state, inner=mock_transport),
            transport_sync=runner._NoSyncTransport(),
        )

    from opspilot.domain.assistant_experiment import read_budget as read_campaign_budget
    provider_before = read_campaign_budget(runner.DOMAIN_DB, EXPERIMENT_ID)["provider_used"]
    accepted = runner._create_user_run(CASE_ID, runner._case_inputs()[CASE_ID], bound=False)
    state.case_id = CASE_ID
    state.run_id = accepted["run_id"]
    app = create_app(
        db_path=runner.DOMAIN_DB, checkpoint_db_path=runner.CHECKPOINT_DB, start_worker=True,
        credentials={"support-a": runner.SUPPORT_PASSWORD}, expected_origin=runner.API_ORIGIN,
        assistant_model_factory=model_factory, assistant_experiment_id=EXPERIMENT_ID,
    )
    with __import__("fastapi.testclient", fromlist=["TestClient"]).TestClient(app) as client:
        runner._login(client)
        run = runner._wait_run(client, accepted["run_id"], seconds=20)
    result = runner._audit_case(
        {
            **accepted, "case_id": CASE_ID, "run_id": accepted["run_id"],
            "session_id": accepted["session_id"], "message_id": accepted["message_id"],
        },
        int(provider_before), 0,
    )
    result["run_status_observed_before_audit"] = run["status"]
    return runner, result, state, wire_requests, pending_before_send


def test_formal_worker_mocktransport_accepts_reserved_request_and_persists_mat01_answer(tmp_path, monkeypatch):
    runner, result, state, requests, reservations = _run_formal_mock_mat01(
        tmp_path, monkeypatch, fail_transport=False,
    )

    assert len(requests) == 1
    assert len(reservations) == 1
    assert state.request_count == 1 and state.unknown is False
    assert result["run_status_observed_before_audit"] == "SUCCEEDED"
    assert result["answer"] and "202" in result["answer"]
    assert result["model_call_count"] == 1
    assert result["provider_outcome"] == "KNOWN_VALID"
    assert result["user_delivery_kind"] == "MODEL_ANSWER"
    assert result["outcome_level"] == "REAL_PROVIDER_AND_FORMAL_WORKER"
    assert result["completion_ids"] == ["chatcmpl-offline-ar03-recovery-02"]
    assert result["model_calls"][0]["error_code_state"] == "UNKNOWN_NOT_IN_ASSISTANT_CALLS_SCHEMA"
    assert result["model_calls"][0]["error_code"] is None
    assert set(result["business_write_counts"].values()) == {0}
    budget = result["campaign_budget"]
    assert budget["provider_used"] == 1 and budget["mcp_used"] == 0
    assert budget["status"] == "OPEN"


def test_formal_worker_failed_mock_request_is_auditable_without_overwriting_run_reason(tmp_path, monkeypatch):
    runner, result, state, requests, reservations = _run_formal_mock_mat01(
        tmp_path, monkeypatch, fail_transport=True,
    )

    assert len(requests) == 1
    assert len(reservations) == 1
    assert state.request_count == 1 and state.unknown is True
    assert result["run_status_observed_before_audit"] == "FAILED"
    assert "模型服务连接失败，本次解释未完成" in result["answer"]
    assert result["model_call_count"] == 1
    assert result["provider_outcome"] == "UNKNOWN"
    assert result["user_delivery_kind"] == "PROGRAM_FAILURE_NOTIFICATION"
    assert result["outcome_level"] == "PROVIDER_RESULT_UNKNOWN"
    assert result["model_calls"][0]["status"] == "UNKNOWN"
    assert result["model_calls"][0]["error_code"] is None
    assert result["model_calls"][0]["error_code_state"] == "UNKNOWN_NOT_IN_ASSISTANT_CALLS_SCHEMA"
    assert "OpenAIConnectionError" in result["run_failure_reason"]
    assert result["campaign_budget"]["status"] == "BUDGET_BREACH"
    assert result["campaign_budget"]["usd_reserved_micro"] == 645_600
    assert set(result["business_write_counts"].values()) == {0}


def test_invalid_wire_is_rejected_before_mocktransport_handler(tmp_path):
    runner = _load_runner()
    state = runner._CampaignState(tmp_path / "provider.jsonl", tmp_path / "unused.sqlite3")
    state.case_id = CASE_ID
    handler_calls = []

    def handler(request):
        handler_calls.append(request)
        return httpx.Response(200, json={})

    request_body = _authorized_request_body(max_tokens=512)
    request = httpx.Request(
        "POST", "https://api.deepseek.com/v1/chat/completions",
        content=json.dumps(request_body).encode("utf-8"), headers={"content-type": "application/json"},
    )
    transport = runner._RecordingAsyncTransport(state, inner=httpx.MockTransport(handler))

    with pytest.raises(RuntimeError, match="LIVE_WIRE_MODEL_OR_OUTPUT_CONFIGURATION_MISMATCH"):
        asyncio.run(transport.handle_async_request(request))

    assert handler_calls == []
    assert state.request_count == 0
    assert state.inflight == 0
