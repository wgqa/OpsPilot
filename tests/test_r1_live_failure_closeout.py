"""Offline replay of captured R1 provider tool calls and known-response failure handling."""
from __future__ import annotations

import gzip
import json
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from opspilot.assistant import Loop, _assistant_failure_notice, create_assistant_model
from opspilot.domain.database import connect
from opspilot.domain.s3_history import prepare_transport_history_fixture
from opspilot.web.app import create_app
from test_ar02_assistant import ORIGIN, PASSWORDS
from test_ar02_journey_p0 import _wait_run
from test_product_01_runtime_grant_01 import _configure, _provision


TRACE_PATH = (
    Path(__file__).resolve().parents[1]
    / "docs/evidence/vnext/r1-live-journey-01/continue-01/TRACE.jsonl"
)


def _captured_completion(step: str) -> tuple[dict[str, object], dict[str, object]]:
    records = [
        json.loads(line)
        for line in TRACE_PATH.read_text(encoding="utf-8-sig").splitlines()
        if line.strip()
    ]
    record = next(
        row for row in records
        if row.get("event") == "real_model_decision_and_product_result"
        and row.get("step") == step
    )
    assert record["provider_http_status"] == 200
    assert record["runtime_dispatch_status"] == "RESPONSE_STORED"
    assert record["finish_reason"] == "tool_calls"
    calls = record["tool_calls_proposed_by_model"]
    assert isinstance(calls, list) and calls
    message = {
        "role": "assistant",
        "content": record["model_preface"],
        "tool_calls": [
            {
                "id": item["tool_call_id"],
                "type": "function",
                "function": {
                    "name": item["name"],
                    "arguments": json.dumps(item["arguments"], ensure_ascii=False),
                },
            }
            for item in calls
        ],
    }
    response = {
        "id": record["provider_completion_id"],
        "object": "chat.completion",
        "created": 1,
        "model": record["returned_model"],
        "system_fingerprint": record["system_fingerprint"],
        "choices": [{"index": 0, "message": message, "finish_reason": "tool_calls"}],
        "usage": record["usage"],
    }
    return record, response


def _configure_runtime(monkeypatch) -> None:
    _configure(monkeypatch)
    monkeypatch.setenv("OPSPILOT_ASSISTANT_RUNTIME_ENABLED", "1")
    monkeypatch.setenv("OPSPILOT_ASSISTANT_PROVIDER_ENABLED", "1")
    monkeypatch.setenv("OPSPILOT_MODEL_API_KEY", "offline-only-placeholder")
    monkeypatch.setenv("OPSPILOT_LEGACY_PROVIDER_ENABLED", "0")
    monkeypatch.delenv("OPSPILOT_ASSISTANT_EXPERIMENT_ID", raising=False)


def _login_and_session(client: TestClient) -> tuple[dict[str, str], str]:
    login = client.post(
        "/api/auth/login",
        headers={"Origin": ORIGIN},
        json={"actor_id": "support-a", "password": PASSWORDS["support-a"]},
    )
    assert login.status_code == 200, login.text
    headers = {"Origin": ORIGIN, "X-CSRF-Token": login.json()["csrf_token"]}
    session = client.post("/api/sessions", headers=headers)
    assert session.status_code == 201, session.text
    return headers, session.json()["session_id"]


@pytest.mark.parametrize(
    ("step", "gzip_response", "bind_order", "expected_mcp_count"),
    [
        ("J1-01", True, False, 1),
        ("J2-01", False, True, 3),
    ],
    ids=["captured-single-tool-gzip", "captured-multi-tool-json"],
)
def test_captured_real_tool_calls_replay_through_formal_assistant_mcp_path(
    demo_db, tmp_path, monkeypatch, step, gzip_response, bind_order, expected_mcp_count,
):
    record, captured_response = _captured_completion(step)
    captured_calls = record["tool_calls_proposed_by_model"]
    expected_call_ids = {item["tool_call_id"] for item in captured_calls}
    expected_names = {item["name"] for item in captured_calls}

    if bind_order:
        prepare_transport_history_fixture(
            demo_db,
            order_id="r1-readiness-order",
            receiver_status="PROCESSED",
            contract_version=2,
            attempts=[
                {"event_id": "event-previous", "http_status": 202},
                {"event_id": "event-current", "http_status": 202},
            ],
        )
    _configure_runtime(monkeypatch)
    _provision(demo_db, total=100_000)
    sent_payloads: list[dict[str, object]] = []

    async def respond(request: httpx.Request) -> httpx.Response:
        payload = json.loads((await request.aread()).decode("utf-8"))
        sent_payloads.append(payload)
        assert str(request.url) == "https://api.deepseek.com/chat/completions"
        assert request.method == "POST"
        assert payload["model"] == "deepseek-flash"
        assert payload["max_tokens"] == 2_048
        assert payload["thinking"] == {"type": "disabled"}
        assert payload["stream"] is False
        assert payload["parallel_tool_calls"] is False
        assert payload["tool_choice"] == "auto"
        with connect(demo_db) as connection:
            granted = connection.execute(
                "SELECT status,reserved_usd_micro FROM assistant_runtime_spends "
                "WHERE status='SEND_GRANTED'"
            ).fetchall()
        assert len(granted) == 1
        assert int(granted[0]["reserved_usd_micro"]) > 0

        if len(sent_payloads) == 1:
            tool_schemas = {
                item["function"]["name"]: item["function"]["parameters"]
                for item in payload.get("tools", [])
            }
            for call in captured_calls:
                assert call["name"] in tool_schemas
                schema = tool_schemas[call["name"]]
                assert set(call["arguments"]).issubset(set(schema.get("properties", {})))
                assert set(schema.get("required", [])).issubset(set(call["arguments"]))
            body = json.dumps(
                captured_response, ensure_ascii=False, separators=(",", ":")
            ).encode("utf-8")
            headers = {"content-type": "application/json"}
            if gzip_response:
                body = gzip.compress(body)
                headers["content-encoding"] = "gzip"
                headers["content-length"] = str(len(body))
            return httpx.Response(
                200, headers=headers, content=body, request=request,
            )

        assert len(sent_payloads) == 2
        assistant_messages = [
            item for item in payload["messages"] if item.get("role") == "assistant"
        ]
        assert any(
            {call.get("id") for call in item.get("tool_calls", [])} == expected_call_ids
            for item in assistant_messages
        )
        tool_messages = [
            item for item in payload["messages"] if item.get("role") == "tool"
        ]
        assert {item.get("tool_call_id") for item in tool_messages} == expected_call_ids
        assert len(tool_messages) == expected_mcp_count
        tool_text = "\n".join(str(item.get("content", "")) for item in tool_messages)
        if bind_order:
            assert "ACKNOWLEDGED" in tool_text
            assert "PROCESSED" in tool_text
        else:
            assert "callback-retry-contract" in tool_text
        return httpx.Response(
            200,
            headers={"content-type": "application/json"},
            json={
                "id": f"offline-final-{step}",
                "object": "chat.completion",
                "created": 1,
                "model": "deepseek-flash",
                "choices": [{
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": "OFFLINE_FIXTURE_FINAL: captured tool proposal executed and observation returned.",
                    },
                    "finish_reason": "stop",
                }],
                "usage": {"prompt_tokens": 2_500, "completion_tokens": 30, "total_tokens": 2_530},
            },
            request=request,
        )

    def reject_sync(request: httpx.Request) -> httpx.Response:
        raise AssertionError("Formal async Worker must not use its sync Provider transport")

    app = create_app(
        db_path=demo_db,
        checkpoint_db_path=tmp_path / f"captured-replay-{step}.sqlite3",
        start_worker=True,
        credentials=PASSWORDS,
        expected_origin=ORIGIN,
        assistant_model_factory=lambda *, runtime_grant_binding: create_assistant_model(
            runtime_grant_binding=runtime_grant_binding,
            transport_async=httpx.MockTransport(respond),
            transport_sync=httpx.MockTransport(reject_sync),
        ),
        assistant_runtime_enabled=True,
    )
    with TestClient(app) as client:
        headers, session_id = _login_and_session(client)
        if bind_order:
            accepted = client.post(
                f"/api/sessions/{session_id}/assistant/order",
                headers={**headers, "Idempotency-Key": f"captured-replay-{step}"},
                json={
                    "order_id": "r1-readiness-order",
                    "initial_message": record["user_input"],
                },
            )
        else:
            accepted = client.post(
                f"/api/sessions/{session_id}/assistant/messages",
                headers={**headers, "Idempotency-Key": f"captured-replay-{step}"},
                json={"body": record["user_input"]},
            )
        assert accepted.status_code == 202, accepted.text
        item = accepted.json()
        assert _wait_run(client, item["run_id"])["status"] == "SUCCEEDED"
        messages = client.get(
            f"/api/sessions/{session_id}/messages?limit=200", headers=headers,
        ).json()["items"]
        answer = next(
            row for row in messages
            if row["role"] == "ASSISTANT"
            and row.get("answer_source_message_id") == item["message_id"]
        )
        assert "OFFLINE_FIXTURE_FINAL" in answer["body"]

    assert len(sent_payloads) == 2
    with connect(demo_db) as connection:
        mcp_rows = [
            dict(row) for row in connection.execute(
                "SELECT call_id,logical_key,status,request_json,result_json,evidence_id,observation_id "
                "FROM assistant_calls WHERE run_id=? AND kind='MCP' ORDER BY created_at,rowid",
                (item["run_id"],),
            ).fetchall()
        ]
        provider_rows = [
            dict(row) for row in connection.execute(
                "SELECT status,reserved_usd_micro,settled_usd_micro,completion_id,usage_json "
                "FROM assistant_runtime_spends ORDER BY created_at,rowid"
            ).fetchall()
        ]
        run = dict(connection.execute(
            "SELECT status,task_id FROM task_runs WHERE run_id=?", (item["run_id"],)
        ).fetchone())
        business_side_effects = sum(
            int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
            for table in (
                "d3_approvals", "d3_action_intents", "d3_action_ledgers",
                "d3_delivery_records", "s2_handoff_receipts",
            )
        )
    assert run["status"] == "SUCCEEDED"
    assert len(mcp_rows) == expected_mcp_count
    assert all(row["status"] == "OK" for row in mcp_rows)
    assert {row["logical_key"] for row in mcp_rows} == expected_call_ids
    assert {json.loads(row["request_json"])["name"] for row in mcp_rows} == expected_names
    assert len(provider_rows) == 2
    assert all(row["status"] == "DELIVERED" for row in provider_rows)
    assert all(row["completion_id"] and row["usage_json"] for row in provider_rows)
    assert sum(int(row["settled_usd_micro"]) for row in provider_rows) <= sum(
        int(row["reserved_usd_micro"]) for row in provider_rows
    )
    if bind_order:
        business_rows = [
            row for row in mcp_rows
            if json.loads(row["request_json"])["name"] in {
                "get_callback_delivery", "get_receiver_processing",
            }
        ]
        assert len(business_rows) == 2
        assert all(row["evidence_id"] and row["observation_id"] for row in business_rows)
        assert all(json.loads(row["result_json"])["facts"]["event_id"] == "event-current"
                   for row in business_rows)
        assert run["task_id"]
    else:
        assert all(row["evidence_id"] is None for row in mcp_rows)
        assert run["task_id"] is None
    assert business_side_effects == 0
    print("R1_CAPTURED_RESPONSE_REPLAY " + json.dumps({
        "source_step": step,
        "captured_completion_id": record["provider_completion_id"],
        "captured_tool_calls": captured_calls,
        "gzip_wire": gzip_response,
        "offline_mock_http_requests": len(sent_payloads),
        "mcp_rows": [
            {
                "tool_call_id": row["logical_key"],
                "tool": json.loads(row["request_json"])["name"],
                "status": row["status"],
                "evidence_id": row["evidence_id"],
                "observation_id": row["observation_id"],
            }
            for row in mcp_rows
        ],
        "observation_refed_in_next_model_context": True,
        "provider_spend_statuses": [row["status"] for row in provider_rows],
        "external_provider_http_requests": 0,
        "business_side_effects": business_side_effects,
        "final_source": "DETERMINISTIC_FIXTURE_AFTER_CAPTURED_REAL_TOOL_CALLS",
    }, ensure_ascii=False))


def test_known_stored_usage_parse_failure_is_not_reported_as_unknown(
    demo_db, tmp_path, monkeypatch,
):
    _configure_runtime(monkeypatch)
    _provision(demo_db, total=100_000)
    sends: list[str] = []

    async def malformed_response(request: httpx.Request) -> httpx.Response:
        sends.append(str(request.url))
        with connect(demo_db) as connection:
            granted = connection.execute(
                "SELECT status,reserved_usd_micro FROM assistant_runtime_spends "
                "WHERE status='SEND_GRANTED'"
            ).fetchone()
        assert granted is not None and int(granted["reserved_usd_micro"]) > 0
        return httpx.Response(
            200,
            headers={"content-type": "application/json"},
            json={
                "id": "offline-known-usage-invalid-sdk-shape",
                "object": "chat.completion",
                "created": 1,
                "model": "deepseek-flash",
                "choices": "invalid-shape",
                "usage": {"prompt_tokens": 7, "completion_tokens": 3, "total_tokens": 10},
            },
            request=request,
        )

    app = create_app(
        db_path=demo_db,
        checkpoint_db_path=tmp_path / "known-response-failure-checkpoint.sqlite3",
        start_worker=True,
        credentials=PASSWORDS,
        expected_origin=ORIGIN,
        assistant_model_factory=lambda *, runtime_grant_binding: create_assistant_model(
            runtime_grant_binding=runtime_grant_binding,
            transport_async=httpx.MockTransport(malformed_response),
            transport_sync=httpx.MockTransport(
                lambda request: (_ for _ in ()).throw(
                    AssertionError("Sync Provider transport must not be used")
                )
            ),
        ),
        assistant_runtime_enabled=True,
    )
    with TestClient(app) as client:
        headers, session_id = _login_and_session(client)
        accepted = client.post(
            f"/api/sessions/{session_id}/assistant/messages",
            headers={**headers, "Idempotency-Key": "known-response-parse-failure"},
            json={"body": "HTTP 202 是否意味着回调已经处理完成？"},
        )
        assert accepted.status_code == 202, accepted.text
        item = accepted.json()
        assert _wait_run(client, item["run_id"])["status"] == "FAILED"
        messages = client.get(
            f"/api/sessions/{session_id}/messages?limit=100", headers=headers,
        ).json()["items"]
        notice = next(
            row["body"] for row in messages
            if row["role"] == "ASSISTANT"
            and row.get("answer_source_message_id") == item["message_id"]
        )
    assert len(sends) == 1
    assert "Usage 已记账" in notice
    assert "计费状态未能确认" not in notice
    assert "不会自动重试" in notice
    with connect(demo_db) as connection:
        model_call = dict(connection.execute(
            "SELECT status,result_json FROM assistant_calls "
            "WHERE run_id=? AND kind='MODEL' ORDER BY created_at,rowid LIMIT 1",
            (item["run_id"],),
        ).fetchone())
        spend = dict(connection.execute(
            "SELECT status,completion_id,usage_json,settled_usd_micro,reserved_usd_micro "
            "FROM assistant_runtime_spends ORDER BY created_at,rowid LIMIT 1"
        ).fetchone())
        run_status = connection.execute(
            "SELECT status FROM task_runs WHERE run_id=?", (item["run_id"],)
        ).fetchone()["status"]
    assert run_status == "FAILED"
    assert model_call["status"] == "FAILED"
    failure = json.loads(model_call["result_json"])
    assert failure["error"] == "ASSISTANT_PROVIDER_RESPONSE_PROCESSING_FAILED"
    assert failure["provider_response_known"] is True
    assert failure["runtime_dispatch_state"] == "RESPONSE_STORED"
    assert failure["provider_error_type"]
    assert failure["cause_types"]
    assert spend["status"] == "RESPONSE_STORED"
    assert spend["completion_id"] == "offline-known-usage-invalid-sdk-shape"
    assert json.loads(spend["usage_json"])["total_tokens"] == 10
    assert 0 < int(spend["settled_usd_micro"]) <= int(spend["reserved_usd_micro"])
    print("R1_KNOWN_RESPONSE_FAILURE " + json.dumps({
        "assistant_call_status": model_call["status"],
        "runtime_dispatch_status": spend["status"],
        "usage_known": True,
        "provider_mock_http_requests": len(sends),
        "automatic_retry": False,
        "user_notice_class": "KNOWN_RESPONSE_AND_CHARGE_PROCESSING_FAILED",
        "external_provider_http_requests": 0,
    }, ensure_ascii=False))


@pytest.mark.parametrize(
    ("code", "expected_phrase"),
    [
        ("ASSISTANT_PROVIDER_NOT_SENT", "没有发送 Provider 请求"),
        ("ASSISTANT_PROVIDER_RESPONSE_PROCESSING_FAILED", "Usage 已记账"),
        ("ASSISTANT_PROVIDER_USAGE_VIOLATION", "超出已批准费用边界"),
        ("ASSISTANT_PROVIDER_RESULT_UNKNOWN", "未决预留保持保留"),
    ],
)
def test_program_notice_distinguishes_provider_dispatch_states(code, expected_phrase):
    error = RuntimeError("private underlying exception")
    error._opspilot_failure_code = code

    notice = _assistant_failure_notice(error)

    assert expected_phrase in notice
    assert "不会自动重试" in notice
    assert "private underlying exception" not in notice


def test_unknown_provider_result_keeps_reservation_and_reports_unknown(
    demo_db, tmp_path, monkeypatch,
):
    _configure_runtime(monkeypatch)
    _provision(demo_db, total=100_000)
    sends: list[str] = []

    async def unknown_response(request: httpx.Request) -> httpx.Response:
        sends.append(str(request.url))
        with connect(demo_db) as connection:
            granted = connection.execute(
                "SELECT status,reserved_usd_micro FROM assistant_runtime_spends "
                "WHERE status='SEND_GRANTED'"
            ).fetchone()
        assert granted is not None and int(granted["reserved_usd_micro"]) > 0
        raise httpx.ConnectError("offline injected transport failure", request=request)

    app = create_app(
        db_path=demo_db,
        checkpoint_db_path=tmp_path / "unknown-provider-checkpoint.sqlite3",
        start_worker=True,
        credentials=PASSWORDS,
        expected_origin=ORIGIN,
        assistant_model_factory=lambda *, runtime_grant_binding: create_assistant_model(
            runtime_grant_binding=runtime_grant_binding,
            transport_async=httpx.MockTransport(unknown_response),
            transport_sync=httpx.MockTransport(
                lambda request: (_ for _ in ()).throw(
                    AssertionError("Sync Provider transport must not be used")
                )
            ),
        ),
        assistant_runtime_enabled=True,
    )
    with TestClient(app) as client:
        headers, session_id = _login_and_session(client)
        accepted = client.post(
            f"/api/sessions/{session_id}/assistant/messages",
            headers={**headers, "Idempotency-Key": "unknown-provider-stays-unknown"},
            json={"body": "HTTP 202 是否意味着回调已经处理完成？"},
        )
        assert accepted.status_code == 202, accepted.text
        item = accepted.json()
        assert _wait_run(client, item["run_id"])["status"] == "FAILED"
        messages = client.get(
            f"/api/sessions/{session_id}/messages?limit=100", headers=headers,
        ).json()["items"]
        notice = next(
            row["body"] for row in messages
            if row["role"] == "ASSISTANT"
            and row.get("answer_source_message_id") == item["message_id"]
        )

    assert len(sends) == 1
    assert "结果或 Usage 尚无法确认" in notice
    assert "未决预留保持保留" in notice
    assert "系统不会自动重试" in notice
    with connect(demo_db) as connection:
        model_call = dict(connection.execute(
            "SELECT status,result_json FROM assistant_calls "
            "WHERE run_id=? AND kind='MODEL' ORDER BY created_at,rowid LIMIT 1",
            (item["run_id"],),
        ).fetchone())
        spend = dict(connection.execute(
            "SELECT status,reserved_usd_micro,settled_usd_micro,error_code "
            "FROM assistant_runtime_spends ORDER BY created_at,rowid LIMIT 1"
        ).fetchone())
    assert model_call["status"] == "UNKNOWN"
    failure = json.loads(model_call["result_json"])
    assert failure["error"] == "ASSISTANT_PROVIDER_RESULT_UNKNOWN"
    assert spend["status"] == "UNKNOWN"
    assert int(spend["reserved_usd_micro"]) > 0
    assert spend["settled_usd_micro"] is None
    assert spend["error_code"]
    print("R1_UNKNOWN_RESPONSE_FAILURE " + json.dumps({
        "assistant_call_status": model_call["status"],
        "runtime_dispatch_status": spend["status"],
        "reserved_usd_micro_retained": spend["reserved_usd_micro"],
        "mock_transport_attempts": len(sends),
        "automatic_retry": False,
        "external_provider_http_requests": 0,
    }, ensure_ascii=False))


def test_pre_send_failure_is_not_sent_and_releases_only_unsent_reserve(
    demo_db, tmp_path, monkeypatch,
):
    _configure_runtime(monkeypatch)
    _provision(demo_db, total=100_000)
    sends: list[str] = []

    async def unexpected_response(request: httpx.Request) -> httpx.Response:
        sends.append(str(request.url))
        raise AssertionError("A pre-send failure must not enter HTTPX transport")

    def fail_before_send(self, selected_memories):
        raise RuntimeError("offline pre-send validation failure")

    monkeypatch.setattr(Loop, "_assert_memories_current", fail_before_send)
    app = create_app(
        db_path=demo_db,
        checkpoint_db_path=tmp_path / "pre-send-failure-checkpoint.sqlite3",
        start_worker=True,
        credentials=PASSWORDS,
        expected_origin=ORIGIN,
        assistant_model_factory=lambda *, runtime_grant_binding: create_assistant_model(
            runtime_grant_binding=runtime_grant_binding,
            transport_async=httpx.MockTransport(unexpected_response),
            transport_sync=httpx.MockTransport(
                lambda request: (_ for _ in ()).throw(
                    AssertionError("Sync Provider transport must not be used")
                )
            ),
        ),
        assistant_runtime_enabled=True,
    )
    with TestClient(app) as client:
        headers, session_id = _login_and_session(client)
        accepted = client.post(
            f"/api/sessions/{session_id}/assistant/messages",
            headers={**headers, "Idempotency-Key": "pre-send-is-not-sent"},
            json={"body": "HTTP 202 是否意味着回调已经处理完成？"},
        )
        assert accepted.status_code == 202, accepted.text
        item = accepted.json()
        assert _wait_run(client, item["run_id"])["status"] == "FAILED"
        messages = client.get(
            f"/api/sessions/{session_id}/messages?limit=100", headers=headers,
        ).json()["items"]
        notice = next(
            row["body"] for row in messages
            if row["role"] == "ASSISTANT"
            and row.get("answer_source_message_id") == item["message_id"]
        )

    assert sends == []
    assert "没有发送 Provider 请求" in notice
    assert "系统不会自动重试" in notice
    with connect(demo_db) as connection:
        model_call = dict(connection.execute(
            "SELECT status,result_json FROM assistant_calls "
            "WHERE run_id=? AND kind='MODEL' ORDER BY created_at,rowid LIMIT 1",
            (item["run_id"],),
        ).fetchone())
        spend = dict(connection.execute(
            "SELECT status,reserved_usd_micro,settled_usd_micro,error_code "
            "FROM assistant_runtime_spends ORDER BY created_at,rowid LIMIT 1"
        ).fetchone())
    assert model_call["status"] == "FAILED"
    assert json.loads(model_call["result_json"])["error"] == "ASSISTANT_PROVIDER_NOT_SENT"
    assert spend["status"] == "NOT_DISPATCHED"
    assert int(spend["reserved_usd_micro"]) == 0
    assert spend["settled_usd_micro"] is None
    print("R1_PRE_SEND_FAILURE " + json.dumps({
        "assistant_call_status": model_call["status"],
        "runtime_dispatch_status": spend["status"],
        "reservation_released": True,
        "mock_transport_attempts": len(sends),
        "external_provider_http_requests": 0,
    }, ensure_ascii=False))
