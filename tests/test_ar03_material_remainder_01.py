from __future__ import annotations

from pathlib import Path
import asyncio
import hashlib
import json
import time

import pytest
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import Field


EXPERIMENT_ID = "AR-03-MATERIAL-REMAINDER-01"
ORIGIN = "http://ar03-material-remainder-offline"
PASSWORDS = {"support-a": "material-remainder-offline"}
CASEBOOK = Path(__file__).resolve().parents[1] / "docs/evidence/ar-03/material-01/CASES.json"


def _case_input(case_id: str) -> str:
    casebook = json.loads(CASEBOOK.read_text(encoding="utf-8"))
    items = {row["id"]: row for row in casebook["cases"]}
    row = items[case_id]
    if "input" not in row and case_id == "MAT-05-BOUND-PROCESSED":
        return str(items["MAT-04-BOUND-QUEUED"]["input"])
    return str(row["input"])


def _prepare_bound_run(db_path, checkpoint_path, case_id, receiver_status="QUEUED"):
    from fastapi.testclient import TestClient
    from opspilot.domain.assistant_experiment import initialize_experiment
    from opspilot.domain.database import connect
    from opspilot.domain.d2 import configure_material_remainder_budget
    from opspilot.domain.s3 import prepare_s3_fixture
    from opspilot.web.app import create_app

    initialize_experiment(db_path, EXPERIMENT_ID)
    prepare_s3_fixture(
        db_path, "DELIVERED_PENDING", tenant_id="tenant-a", order_id="ar03-order",
        contract_version=2, queue_age_seconds=60,
    )
    with connect(db_path) as connection:
        delivery = connection.execute(
            "SELECT event_id,status,receiver_http_status FROM s3_deliveries WHERE tenant_id='tenant-a' AND order_id='ar03-order'"
        ).fetchone()
        receiver = connection.execute(
            "SELECT event_id,status,version FROM s3_receivers WHERE tenant_id='tenant-a' AND order_id='ar03-order'"
        ).fetchone()
        assert delivery and receiver and delivery["event_id"] == receiver["event_id"]
        assert delivery["status"] == "ACKNOWLEDGED" and delivery["receiver_http_status"] == 202
        if receiver_status == "PROCESSED":
            changed = connection.execute(
                "UPDATE s3_receivers SET status='PROCESSED',version=version+1 WHERE tenant_id='tenant-a' AND order_id='ar03-order' AND event_id=? AND status='QUEUED'",
                (receiver["event_id"],),
            )
            assert changed.rowcount == 1
            receiver = connection.execute(
                "SELECT event_id,status,version FROM s3_receivers WHERE tenant_id='tenant-a' AND order_id='ar03-order'"
            ).fetchone()
    assert receiver["status"] == receiver_status

    app = create_app(
        db_path=db_path, checkpoint_db_path=checkpoint_path, start_worker=False,
        credentials=PASSWORDS, expected_origin=ORIGIN,
        assistant_experiment_id=EXPERIMENT_ID,
    )
    with TestClient(app) as client:
        login = client.post(
            "/api/auth/login", headers={"Origin": ORIGIN},
            json={"actor_id": "support-a", "password": PASSWORDS["support-a"]},
        )
        assert login.status_code == 200, login.text
        headers = {"Origin": ORIGIN, "X-CSRF-Token": login.json()["csrf_token"]}
        session_id = client.post("/api/sessions", headers=headers).json()["session_id"]
        response = client.post(
            f"/api/sessions/{session_id}/assistant/order",
            headers={**headers, "Idempotency-Key": f"remainder-{case_id.lower()}"},
            json={"order_id": "ar03-order", "initial_message": _case_input(case_id)},
        )
        assert response.status_code == 202, response.text
        accepted = response.json()
    task_id = str(accepted["task_id"])
    limits = configure_material_remainder_budget(db_path, task_id, EXPERIMENT_ID)
    assert limits == {"MODEL": 16, "MCP": None}
    return {
        "session_id": str(session_id), "task_id": task_id,
        "run_id": str(accepted["run_id"]), "event_id": str(receiver["event_id"]),
        "user_input": _case_input(case_id),
    }


def _prepare_unbound_runs(db_path, checkpoint_path, count=1):
    from fastapi.testclient import TestClient
    from opspilot.domain.assistant_experiment import initialize_experiment
    from opspilot.domain.database import reset_fixture
    from opspilot.web.app import create_app

    # The helper is only used with fresh pytest temporary databases. Reuse the
    # trusted project bootstrap before creating this experiment's ledger.
    reset_fixture(db_path, "S1_POS")
    initialize_experiment(db_path, EXPERIMENT_ID)
    app = create_app(
        db_path=db_path, checkpoint_db_path=checkpoint_path, start_worker=False,
        credentials=PASSWORDS, expected_origin=ORIGIN,
        assistant_experiment_id=EXPERIMENT_ID,
    )
    run_ids = []
    with TestClient(app) as client:
        headers = _login(client)
        for index in range(count):
            session_id = client.post("/api/sessions", headers=headers).json()["session_id"]
            response = client.post(
                f"/api/sessions/{session_id}/assistant/messages",
                headers={**headers, "Idempotency-Key": f"remainder-unbound-{index}"},
                json={"body": "离线验证授权范围内的只读调查入口。"},
            )
            assert response.status_code == 202, response.text
            run_ids.append(str(response.json()["run_id"]))
    return run_ids


def _login(client):
    response = client.post(
        "/api/auth/login", headers={"Origin": ORIGIN},
        json={"actor_id": "support-a", "password": PASSWORDS["support-a"]},
    )
    assert response.status_code == 200, response.text
    return {"Origin": ORIGIN, "X-CSRF-Token": response.json()["csrf_token"]}


def _wait_run(client, run_id):
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        response = client.get(f"/api/runs/{run_id}")
        assert response.status_code == 200, response.text
        result = response.json()
        if result["status"] in {"SUCCEEDED", "FAILED", "BLOCKED", "CANCELLED"}:
            return result
        time.sleep(0.05)
    raise AssertionError(f"offline worker did not finish Run {run_id}")


class _RepeatedReadModel(BaseChatModel):
    """A deterministic capacity probe; not a model-quality or fixed-order Gold."""

    calls: int = 11
    proposed: int = 0
    offered: list[str] = Field(default_factory=list)

    @property
    def _llm_type(self):
        return "AR03_MATERIAL_REMAINDER_OFFLINE_CAPACITY_PROBE"

    def bind_tools(self, tools, **kwargs):
        self.offered = [tool.name for tool in tools]
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        self.proposed += 1
        if self.proposed <= self.calls:
            response = AIMessage(content="", tool_calls=[{
                "type": "tool_call", "name": "get_callback_delivery",
                "args": {"reason": f"离线容量回归的同一授权 Event 再核对 {self.proposed}"},
                "id": f"remainder-read-{self.proposed}",
            }])
        else:
            response = AIMessage(content="离线容量探针完成；这不是真实模型实验结果。")
        response.usage_metadata = {"input_tokens": 32, "output_tokens": 16, "total_tokens": 48}
        return ChatResult(generations=[ChatGeneration(message=response)])


def _wire_model_factory(handler, clients):
    import httpx
    from langchain_openai import ChatOpenAI

    def factory():
        async_transport = httpx.MockTransport(handler)
        sync_transport = httpx.MockTransport(
            lambda request: (_ for _ in ()).throw(AssertionError("sync HTTP path must stay unused"))
        )
        async_client = httpx.AsyncClient(
            timeout=httpx.Timeout(30), trust_env=False, follow_redirects=False,
            transport=async_transport,
        )
        sync_client = httpx.Client(
            timeout=httpx.Timeout(30), trust_env=False, follow_redirects=False,
            transport=sync_transport,
        )
        clients.append((async_client, sync_client))
        return ChatOpenAI(
            model="deepseek-flash", api_key="offline-placeholder", base_url="https://api.deepseek.com/v1",
            temperature=0, timeout=30, max_retries=0, stream_usage=True,
            include_response_headers=True, http_async_client=async_client,
            http_client=sync_client, http_socket_options=(),
            extra_body={"max_tokens": 2048, "thinking": {"type": "disabled"}},
        )
    return factory


def _close_clients(clients):
    for async_client, sync_client in clients:
        asyncio.run(async_client.aclose())
        sync_client.close()


def test_remainder_campaign_counts_mcp_without_a_low_call_ceiling(demo_db):
    from opspilot.domain.assistant_experiment import initialize_experiment, read_budget

    initialize_experiment(demo_db, EXPERIMENT_ID)
    budget = read_budget(demo_db, EXPERIMENT_ID)
    assert budget["provider_limit"] == 16
    assert budget["mcp_limit"] is None
    assert budget["budget_usd_micro"] == 10_500_000
    assert budget["provider_used"] == budget["mcp_used"] == 0


def test_remainder_limits_are_experiment_scoped_and_legacy_defaults_stay():
    from opspilot.domain.assistant import run_limits_for_experiment

    assert run_limits_for_experiment(EXPERIMENT_ID) == (16, None)
    assert run_limits_for_experiment("AR-03-MATERIAL-LIVE-01-RESUME-02") == (16, 10)
    assert run_limits_for_experiment(None) == (8, 6)


def test_remainder_policy_allows_multiple_runs_but_keeps_task_time_budget(demo_db):
    from opspilot.domain.d2 import configure_material_remainder_budget, task_attempt_limits
    from opspilot.domain.execution_budget import execution_budget_snapshot, investigation_budget_snapshot
    from opspilot.domain.s3 import prepare_s3_fixture

    fixture = prepare_s3_fixture(
        demo_db, "DELIVERED_PENDING", tenant_id="tenant-a", order_id="ar03-order",
        contract_version=2, queue_age_seconds=60,
    )
    assert fixture
    from fastapi.testclient import TestClient
    from opspilot.web.app import create_app

    origin = "http://ar03-material-remainder-offline"
    passwords = {"support-a": "material-remainder-offline"}

    app = create_app(
        db_path=demo_db, checkpoint_db_path=Path(str(demo_db) + ".checkpoints.sqlite3"),
        start_worker=False, credentials=passwords, expected_origin=origin,
        assistant_experiment_id=EXPERIMENT_ID,
    )
    with TestClient(app) as client:
        login = client.post(
            "/api/auth/login", headers={"Origin": origin},
            json={"actor_id": "support-a", "password": passwords["support-a"]},
        )
        assert login.status_code == 200, login.text
        headers = {"Origin": origin, "X-CSRF-Token": login.json()["csrf_token"]}
        session_id = client.post("/api/sessions", headers=headers).json()["session_id"]
        accepted = client.post(
            f"/api/sessions/{session_id}/assistant/order",
            headers={**headers, "Idempotency-Key": "remainder-policy-red"},
            json={"order_id": "ar03-order", "initial_message": "MAT-05 offline policy probe"},
        )
        assert accepted.status_code == 202, accepted.text
        task_id = accepted.json()["task_id"]

    limits = configure_material_remainder_budget(demo_db, task_id, EXPERIMENT_ID)
    assert limits == {"MODEL": 16, "MCP": None}
    assert task_attempt_limits(demo_db, task_id) == limits
    snapshot = execution_budget_snapshot(demo_db, task_id)
    assert snapshot["deadline_ms"] == 300_000


def test_remainder_paid_provider_is_still_fail_closed(monkeypatch):
    from opspilot.assistant import create_assistant_model

    monkeypatch.setenv("OPSPILOT_ASSISTANT_PROVIDER_ENABLED", "1")
    monkeypatch.setenv("OPSPILOT_ASSISTANT_EXPERIMENT_ID", EXPERIMENT_ID)
    monkeypatch.setenv("OPSPILOT_MODEL_API_KEY", "offline-test-placeholder")
    monkeypatch.setenv("OPSPILOT_MODEL_NAME", "deepseek-flash")
    monkeypatch.setenv("OPSPILOT_MODEL_BASE_URL", "https://api.deepseek.com")
    with pytest.raises(RuntimeError, match="PAID_AUTHORIZATION_REQUIRED|SCOPE_REQUIRED"):
        create_assistant_model()


def test_remainder_bound_policy_is_idempotent_and_deadline_still_stops_mcp(demo_db, tmp_path):
    from opspilot.domain.database import connect
    from opspilot.domain.d2 import (
        BudgetExhausted, configure_material_remainder_budget, reserve_attempt,
        task_attempt_limits,
    )
    from opspilot.domain.execution_budget import execution_budget_snapshot, investigation_budget_snapshot

    accepted = _prepare_bound_run(
        demo_db, tmp_path / "deadline-checkpoint.sqlite3", "MAT-04-BOUND-QUEUED",
    )
    assert configure_material_remainder_budget(demo_db, accepted["task_id"], EXPERIMENT_ID) == {
        "MODEL": 16, "MCP": None,
    }
    assert task_attempt_limits(demo_db, accepted["task_id"]) == {"MODEL": 16, "MCP": None}
    with connect(demo_db) as connection:
        stored_policy = connection.execute(
            "SELECT model_limit,mcp_limit,policy_version FROM task_execution_budgets WHERE task_id=?",
            (accepted["task_id"],),
        ).fetchone()
    assert tuple(stored_policy) == (16, 0, "AR03_MATERIAL_REMAINDER_01_V1")
    before = execution_budget_snapshot(demo_db, accepted["task_id"])
    assert before["deadline_ms"] == 300_000

    with connect(demo_db) as connection:
        connection.execute(
            "UPDATE task_execution_budgets SET active_elapsed_ms=deadline_ms WHERE task_id=?",
            (accepted["task_id"],),
        )
    expired = investigation_budget_snapshot(demo_db, accepted["task_id"], accepted["run_id"])
    assert expired["remaining_attempts"] == {"MODEL": 0, "MCP": 0}
    assert expired["limit_reasons"] == {
        "MODEL": "ACTIVE_TIME_LIMIT", "MCP": "ACTIVE_TIME_LIMIT",
    }
    with connect(demo_db) as connection:
        connection.execute(
            "UPDATE task_runs SET status='RUNNING' WHERE run_id=? AND status='QUEUED'",
            (accepted["run_id"],),
        )
    with pytest.raises(BudgetExhausted) as stopped:
        reserve_attempt(
            demo_db, accepted["task_id"], "MCP", None,
            call_id="deadline-mcp-not-dispatched", tool_call_id="deadline-mcp-not-dispatched",
            tool_name="get_receiver_processing", argument_digest="offline-deadline-test",
            run_id=accepted["run_id"],
        )
    assert stopped.value.reason_code == "ACTIVE_TIME_LIMIT"
    with connect(demo_db) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM d2_attempts WHERE task_id=?", (accepted["task_id"],),
        ).fetchone()[0] == 0


def test_remainder_task_policy_requires_its_campaign_row(demo_db, tmp_path):
    from opspilot.domain.database import connect
    from opspilot.domain.d2 import ScopeDenied, configure_material_remainder_budget

    accepted = _prepare_bound_run(
        demo_db, tmp_path / "missing-campaign-checkpoint.sqlite3", "MAT-04-BOUND-QUEUED",
    )
    with connect(demo_db) as connection:
        connection.execute(
            "DELETE FROM ar02_live_experiment_budgets WHERE experiment_id=?", (EXPERIMENT_ID,),
        )
    with pytest.raises(ScopeDenied, match="MATERIAL_REMAINDER_CAMPAIGN_SCOPE_INVALID"):
        configure_material_remainder_budget(demo_db, accepted["task_id"], EXPERIMENT_ID)


def test_remainder_repeated_same_tool_can_cross_old_ten_mcp_limit_in_formal_worker(
    demo_db, tmp_path, monkeypatch,
):
    from fastapi.testclient import TestClient
    from opspilot.domain.assistant_experiment import read_budget
    from opspilot.domain.database import connect
    from opspilot.web.app import create_app

    accepted = _prepare_bound_run(
        demo_db, tmp_path / "capacity-checkpoint.sqlite3", "MAT-04-BOUND-QUEUED",
    )
    model = _RepeatedReadModel(calls=11)
    monkeypatch.setenv("OPSPILOT_ASSISTANT_PROVIDER_ENABLED", "0")
    monkeypatch.setenv("OPSPILOT_AR03_MATERIAL_SKILL_MODE", "OFF")
    app = create_app(
        db_path=demo_db, checkpoint_db_path=tmp_path / "capacity-checkpoint.sqlite3",
        start_worker=True, credentials=PASSWORDS, expected_origin=ORIGIN,
        assistant_model_factory=lambda: model,
        assistant_experiment_id=EXPERIMENT_ID,
    )
    with TestClient(app) as client:
        headers = _login(client)
        run = _wait_run(client, accepted["run_id"])
        messages = client.get(
            f"/api/sessions/{accepted['session_id']}/messages", headers=headers,
        )
        assert messages.status_code == 200, messages.text

    assert run["status"] == "SUCCEEDED"
    assert model.proposed == 12
    assert "get_callback_delivery" in model.offered
    budget = read_budget(demo_db, EXPERIMENT_ID)
    assert budget["provider_limit"] == 16 and budget["mcp_limit"] is None
    assert budget["provider_used"] == 12 and budget["mcp_used"] == 11
    with connect(demo_db) as connection:
        calls = connection.execute(
            "SELECT kind,status FROM assistant_calls WHERE run_id=? ORDER BY created_at",
            (accepted["run_id"],),
        ).fetchall()
        attempts = connection.execute(
            "SELECT kind,status,tool_name,run_id FROM d2_attempts WHERE task_id=?",
            (accepted["task_id"],),
        ).fetchall()
        assert len([row for row in calls if row["kind"] == "MCP" and row["status"] == "OK"]) == 11
        assert len([row for row in attempts if row["kind"] == "MCP" and row["status"] == "OK"]) == 11
        assert all(row["run_id"] == accepted["run_id"] for row in attempts)
        assert connection.execute("SELECT COUNT(*) FROM s3_diagnoses").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM s3_handoff_queue_entries").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM s3_handoff_receipts").fetchone()[0] == 0


@pytest.mark.parametrize(
    ("receiver_status", "skill_mode"),
    [("QUEUED", "OFF"), ("QUEUED", "ON"), ("PROCESSED", "OFF"), ("PROCESSED", "ON")],
)
def test_remainder_mocktransport_formal_worker_observes_same_event_and_serializes_live_contract(
    demo_db, tmp_path, monkeypatch, receiver_status, skill_mode,
):
    import httpx
    from fastapi.testclient import TestClient
    from opspilot.domain.assistant_experiment import read_budget
    from opspilot.domain.database import connect
    from opspilot.web.app import create_app

    case_id = "MAT-05-BOUND-PROCESSED" if receiver_status == "PROCESSED" else "MAT-04-BOUND-QUEUED"
    assert _case_input("MAT-04-BOUND-QUEUED") == _case_input("MAT-05-BOUND-PROCESSED")
    accepted = _prepare_bound_run(
        demo_db, tmp_path / f"wire-{receiver_status}-{skill_mode}.sqlite3", case_id,
        receiver_status=receiver_status,
    )
    client_entries = []
    requests = []
    responses = []

    def completion(completion_id, *, text=None, tool_calls=None):
        response = httpx.Response(200, json={
            "id": completion_id,
            "object": "chat.completion",
            "created": 1793740000,
            "model": "deepseek-flash",
            "choices": [{
                "index": 0,
                "message": {"role": "assistant", "content": text, **({"tool_calls": tool_calls} if tool_calls else {})},
                "finish_reason": "tool_calls" if tool_calls else "stop",
            }],
            "usage": {"prompt_tokens": 90, "completion_tokens": 24, "total_tokens": 114},
        }, headers={"x-request-id": completion_id})
        responses.append({
            "request_number": len(requests), "status_code": response.status_code,
            "completion_id": completion_id,
            "input_tokens": 90, "output_tokens": 24, "total_tokens": 114,
        })
        return response

    def handler(request):
        body = json.loads(request.content)
        request_number = len(requests) + 1
        assert request.method == "POST"
        assert str(request.url) == "https://api.deepseek.com/v1/chat/completions"
        assert body["model"] == "deepseek-flash"
        assert body["thinking"] == {"type": "disabled"}
        assert body["max_tokens"] == 2048 and "max_completion_tokens" not in body
        assert body["stream"] is False
        assert body["tool_choice"] == "auto" and body["parallel_tool_calls"] is False
        tools = {item["function"]["name"] for item in body.get("tools", [])}
        assert {"get_callback_delivery", "get_receiver_processing"} <= tools
        assert (("load_protocol_upgrade_skill" in tools) == (skill_mode == "ON"))

        budget = read_budget(demo_db, EXPERIMENT_ID)
        assert budget["provider_used"] == request_number
        with connect(demo_db) as connection:
            reserved_dispatches = connection.execute(
                "SELECT * FROM ar02_live_dispatches WHERE experiment_id=? AND kind='MODEL' AND status='RESERVED'",
                (EXPERIMENT_ID,),
            ).fetchall()
            reserved_calls = connection.execute(
                "SELECT * FROM assistant_calls WHERE run_id=? AND kind='MODEL' AND status='RESERVED'",
                (accepted["run_id"],),
            ).fetchall()
        assert len(reserved_dispatches) == len(reserved_calls) == 1
        assert reserved_dispatches[0]["run_id"] == accepted["run_id"]
        assert reserved_dispatches[0]["logical_key"] == reserved_calls[0]["logical_key"]
        assert reserved_dispatches[0]["reserved_usd_micro"] == 645_600
        stored_request = json.loads(reserved_calls[0]["request_json"])
        assert stored_request["context_budget"]["input_budget_tokens"] == 12_000
        assert stored_request["context_budget"]["estimated_input_tokens"] <= 12_000
        requests.append(body)

        if request_number == 1:
            calls = [
                {"id": "wire-delivery", "type": "function", "function": {
                    "name": "get_callback_delivery",
                    "arguments": json.dumps({"reason": "读取绑定订单中目标 Event 的当前投递"}),
                }},
                {"id": "wire-receiver", "type": "function", "function": {
                    "name": "get_receiver_processing",
                    "arguments": json.dumps({"reason": "读取同一绑定 Event 的当前 Receiver"}),
                }},
            ]
            return completion("mock-remainder-tools", tool_calls=calls)

        messages = body.get("messages", [])
        tool_payload = json.dumps(messages, ensure_ascii=False)
        assert accepted["event_id"] in tool_payload
        assert receiver_status in tool_payload
        if receiver_status == "PROCESSED":
            text = "当前 Run 的同一 Event Observation 显示 Receiver=PROCESSED；只能确认这一事件已处理，不代表其他事件或线上协议部署。"
        else:
            text = "当前 Run 的同一 Event Observation 显示 Receiver=QUEUED；HTTP 202 仅表示投递已受理，处理完成仍未知。"
        return completion("mock-remainder-final", text=text)

    monkeypatch.setenv("OPSPILOT_ASSISTANT_PROVIDER_ENABLED", "0")
    monkeypatch.setenv("OPSPILOT_AR03_MATERIAL_SKILL_MODE", skill_mode)
    monkeypatch.delenv("OPSPILOT_ASSISTANT_EXPERIMENT_ID", raising=False)
    app = create_app(
        db_path=demo_db, checkpoint_db_path=tmp_path / f"worker-{receiver_status}-{skill_mode}.sqlite3",
        start_worker=True, credentials=PASSWORDS, expected_origin=ORIGIN,
        assistant_model_factory=_wire_model_factory(handler, client_entries),
        assistant_experiment_id=EXPERIMENT_ID,
    )
    try:
        with TestClient(app) as client:
            headers = _login(client)
            run = _wait_run(client, accepted["run_id"])
            messages_response = client.get(
                f"/api/sessions/{accepted['session_id']}/messages", headers=headers,
            )
            assert messages_response.status_code == 200, messages_response.text
            messages = messages_response.json()["items"]
    finally:
        _close_clients(client_entries)

    captured_http = tmp_path / f"mock-http-{receiver_status.lower()}-{skill_mode.lower()}.jsonl"
    with captured_http.open("w", encoding="utf-8", newline="\n") as stream:
        for index, body in enumerate(requests, start=1):
            body_bytes = json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
            stream.write(json.dumps({
                "evidence_level": "HTTPX_MOCKTRANSPORT_CAPTURED_FORMAL_ASSISTANT_REQUEST",
                "request_number": index, "method": "POST",
                "url": "https://api.deepseek.com/v1/chat/completions",
                "request_sha256": hashlib.sha256(body_bytes).hexdigest(),
                "model": body.get("model"), "thinking": body.get("thinking"),
                "max_tokens": body.get("max_tokens"),
                "tool_choice": body.get("tool_choice"),
                "parallel_tool_calls": body.get("parallel_tool_calls"),
                "stream": body.get("stream"),
                "message_count": len(body.get("messages", [])),
                "tool_names": [item.get("function", {}).get("name") for item in body.get("tools", [])],
                "mock_response": responses[index - 1],
                "external_provider_request": False,
            }, ensure_ascii=False, sort_keys=True) + "\n")

    assert run["status"] == "SUCCEEDED"
    assert len(requests) == 2
    assert any(receiver_status in str(item) for item in messages)
    budget = read_budget(demo_db, EXPERIMENT_ID)
    assert budget["provider_used"] == 2 and budget["mcp_used"] == 2
    assert budget["mcp_limit"] is None and budget["usd_reserved_micro"] == 0
    with connect(demo_db) as connection:
        observations = connection.execute(
            """SELECT o.tool_name,o.status,e.facts_json,e.resource_id
               FROM d2_tool_observations o JOIN d2_evidence e ON e.evidence_id=o.evidence_id
               WHERE o.task_id=? AND o.status='OK'""",
            (accepted["task_id"],),
        ).fetchall()
        assert len(observations) == 2
        assert all(accepted["event_id"] in row["facts_json"] for row in observations)
        assert all(row["status"] == "OK" for row in observations)
        assert {row["tool_name"] for row in observations} == {
            "get_callback_delivery", "get_receiver_processing",
        }
        assert connection.execute("SELECT COUNT(*) FROM s3_diagnoses").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM s3_handoff_queue_entries").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM s3_handoff_receipts").fetchone()[0] == 0


def test_remainder_provider_unknown_and_duplicate_dispatch_stay_hard_stops(demo_db, tmp_path):
    from fastapi.testclient import TestClient
    from opspilot.domain.assistant_experiment import (
        ExperimentBudgetError, initialize_experiment, mark_unknown, read_budget,
        reserve_dispatch,
    )
    from opspilot.web.app import create_app

    initialize_experiment(demo_db, EXPERIMENT_ID)
    app = create_app(
        db_path=demo_db, checkpoint_db_path=tmp_path / "unknown-checkpoints.sqlite3",
        start_worker=False, credentials=PASSWORDS, expected_origin=ORIGIN,
        assistant_experiment_id=EXPERIMENT_ID,
    )
    with TestClient(app) as client:
        headers = _login(client)
        run_ids = []
        for index in range(2):
            session = client.post("/api/sessions", headers=headers).json()["session_id"]
            response = client.post(
                f"/api/sessions/{session}/assistant/messages",
                headers={**headers, "Idempotency-Key": f"remainder-unknown-{index}"},
                json={"body": "offline dispatch failure boundary"},
            )
            assert response.status_code == 202, response.text
            run_ids.append(response.json()["run_id"])

    reserved = reserve_dispatch(
        demo_db, experiment_id=EXPERIMENT_ID, run_id=run_ids[0], kind="MODEL",
        logical_key="unknown-one-shot", request={"model": "deepseek-flash", "offline": True},
    )
    mark_unknown(
        demo_db, experiment_id=EXPERIMENT_ID, run_id=run_ids[0], kind="MODEL",
        logical_key="unknown-one-shot", error_code="MOCK_UNKNOWN",
    )
    with pytest.raises(ExperimentBudgetError, match="AR02_LIVE_CALL_OUTCOME_UNKNOWN"):
        reserve_dispatch(
            demo_db, experiment_id=EXPERIMENT_ID, run_id=run_ids[0], kind="MODEL",
            logical_key="unknown-one-shot", request={"model": "deepseek-flash", "offline": True},
        )
    with pytest.raises(ExperimentBudgetError, match="AR02_LIVE_SPEND_BOUND_BREACHED"):
        reserve_dispatch(
            demo_db, experiment_id=EXPERIMENT_ID, run_id=run_ids[1], kind="MODEL",
            logical_key="different-run-after-unknown", request={"model": "deepseek-flash"},
        )
    budget = read_budget(demo_db, EXPERIMENT_ID)
    assert budget["provider_used"] == 1
    assert budget["usd_reserved_micro"] == 645_600
    assert budget["status"] == "BUDGET_BREACH"
    assert reserved["dispatch"] is True


def test_remainder_campaign_provider_count_is_shared_and_fee_reserve_is_hard(demo_db, tmp_path):
    from opspilot.domain.assistant_experiment import (
        ExperimentBudgetError, read_budget, reserve_dispatch,
    )
    from opspilot.domain.database import connect

    run_ids = _prepare_unbound_runs(
        demo_db, tmp_path / "shared-campaign-checkpoints.sqlite3", count=2,
    )
    for index in range(16):
        result = reserve_dispatch(
            demo_db, experiment_id=EXPERIMENT_ID, run_id=run_ids[index % 2],
            kind="MODEL", logical_key=f"shared-reserve-{index}",
            request={"offline-reservation-test": index},
        )
        assert result["dispatch"] is True
    budget = read_budget(demo_db, EXPERIMENT_ID)
    assert budget["provider_used"] == 16
    assert budget["mcp_limit"] is None
    assert budget["usd_reserved_micro"] == 16 * 645_600 == 10_329_600
    assert budget["usd_reserved_micro"] < budget["budget_usd_micro"] == 10_500_000
    with pytest.raises(ExperimentBudgetError, match="AR02_LIVE_PROVIDER_LIMIT"):
        reserve_dispatch(
            demo_db, experiment_id=EXPERIMENT_ID, run_id=run_ids[0], kind="MODEL",
            logical_key="seventeenth-shared-reserve", request={"offline": True},
        )

    # A persisted settled balance near the ceiling proves the cost check itself
    # remains before dispatch, independent of the request-count check above.
    budget_db = tmp_path / "fee-ceiling.sqlite3"
    budget_runs = _prepare_unbound_runs(
        budget_db, tmp_path / "fee-checkpoints.sqlite3", count=1,
    )
    from opspilot.domain.assistant import digest_json
    from opspilot.domain.d2 import utc_now
    from opspilot.domain.assistant_experiment import canonical_json
    with connect(budget_db) as connection:
        connection.execute(
            """INSERT INTO ar02_live_dispatches
               (dispatch_id,experiment_id,run_id,kind,logical_key,request_digest,status,
                reserved_usd_micro,settled_usd_micro,usage_state,usage_json,created_at,completed_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                "synthetic-settled-fee-boundary", EXPERIMENT_ID, budget_runs[0], "MODEL",
                "synthetic-settled-fee-boundary", digest_json({"synthetic": True}), "OK",
                0, 10_000_000, "KNOWN", canonical_json({"offline_test_fixture": True}),
                utc_now(), utc_now(),
            ),
        )
    with pytest.raises(ExperimentBudgetError, match="AR02_LIVE_USD_LIMIT"):
        reserve_dispatch(
            budget_db, experiment_id=EXPERIMENT_ID, run_id=budget_runs[0], kind="MODEL",
            logical_key="would-cross-usd-ceiling", request={"offline": True},
        )
    final = read_budget(budget_db, EXPERIMENT_ID)
    assert final["provider_used"] == 1
    assert final["usd_settled_micro"] == 10_000_000
    assert final["usd_reserved_micro"] == 0


def test_remainder_does_not_migrate_an_old_campaign_ledger_schema(demo_db):
    from opspilot.domain.assistant_experiment import ExperimentBudgetError, SCHEMA, initialize_experiment
    from opspilot.domain.database import connect

    old_schema = SCHEMA.replace(
        ", 'AR-03-MATERIAL-REMAINDER-01'", "",
    ).replace("mcp_limit INTEGER,", "mcp_limit INTEGER NOT NULL,")
    with connect(demo_db) as connection:
        connection.executescript(old_schema)
        before = connection.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='ar02_live_experiment_budgets'"
        ).fetchone()["sql"]
    with pytest.raises(ExperimentBudgetError, match="AR02_LIVE_SCHEMA_ID_NOT_SUPPORTED"):
        initialize_experiment(demo_db, EXPERIMENT_ID)
    with connect(demo_db) as connection:
        after = connection.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='ar02_live_experiment_budgets'"
        ).fetchone()["sql"]
    assert after == before


def test_remainder_paid_provider_cannot_be_constructed_from_id_or_api_key_alone(monkeypatch):
    from opspilot.assistant import create_assistant_model

    monkeypatch.setenv("OPSPILOT_ASSISTANT_PROVIDER_ENABLED", "1")
    monkeypatch.setenv("OPSPILOT_ASSISTANT_EXPERIMENT_ID", EXPERIMENT_ID)
    monkeypatch.setenv("OPSPILOT_MODEL_API_KEY", "offline-test-placeholder")
    monkeypatch.setenv("OPSPILOT_MODEL_NAME", "deepseek-flash")
    monkeypatch.setenv("OPSPILOT_MODEL_BASE_URL", "https://api.deepseek.com")
    with pytest.raises(RuntimeError, match="AR03_MATERIAL_LIVE_PAID_AUTHORIZATION_REQUIRED"):
        create_assistant_model()
