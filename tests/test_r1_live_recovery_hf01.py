from __future__ import annotations

import json

from fastapi.testclient import TestClient

from opspilot.domain.database import connect
from opspilot.domain.s3 import prepare_s3_fixture
from opspilot.domain.task_control import TaskControlError, assert_task_control_in_transaction
from opspilot.web.app import create_app
from test_ar02_assistant import ORIGIN, PASSWORDS
from test_ar02_ar03_integration_01 import IntegrationFixtureModel, _login, _wait_run


def _login_as(client, actor_id):
    response = client.post(
        "/api/auth/login", headers={"Origin": ORIGIN},
        json={"actor_id": actor_id, "password": PASSWORDS[actor_id]},
    )
    assert response.status_code == 200, response.text
    return {"Origin": ORIGIN, "X-CSRF-Token": response.json()["csrf_token"]}


def _run_rows(db_path, task_id):
    with connect(db_path) as connection:
        return [dict(row) for row in connection.execute(
            "SELECT run_id,kind,status,blocked_reason,source_message_id,consumed_message_seq,expected_control_revision "
            "FROM task_runs WHERE task_id=? ORDER BY created_at,run_id", (task_id,),
        )]


def test_c02_blocked_correction_does_not_block_same_task_assistant_readonly_red(
    demo_db, tmp_path, monkeypatch,
):
    """Baseline reproduction of the reported C02 -> C03 collateral block."""
    monkeypatch.setenv("OPSPILOT_LEGACY_PROVIDER_ENABLED", "0")
    monkeypatch.setenv("OPSPILOT_ASSISTANT_RUNTIME_ENABLED", "0")
    monkeypatch.setenv("OPSPILOT_ASSISTANT_PROVIDER_ENABLED", "0")
    monkeypatch.delenv("OPSPILOT_ASSISTANT_EXPERIMENT_ID", raising=False)
    monkeypatch.delenv("OPSPILOT_ASSISTANT_EXPERIMENT", raising=False)

    prepare_s3_fixture(demo_db, "DELIVERY_FAILED", order_id="async-order-2")
    model = IntegrationFixtureModel(mode="current-event-only")
    app = create_app(
        db_path=demo_db,
        checkpoint_db_path=tmp_path / "recovery-checkpoint.sqlite3",
        start_worker=True,
        credentials=PASSWORDS,
        expected_origin=ORIGIN,
        assistant_model_factory=lambda: model,
        assistant_runtime_enabled=False,
    )

    with TestClient(app) as client:
        headers = _login(client)
        session_id = client.post("/api/sessions", headers=headers).json()["session_id"]
        created_response = client.post(
            f"/api/sessions/{session_id}/tasks",
            headers={**headers, "Idempotency-Key": "r1-recovery-create-task"},
            json={
                "investigation_kind": "ASYNC_CALLBACK",
                "s3_order_id": "async-order-2",
                "initial_message": "请调查绑定订单的回调处理失败。",
            },
        )
        assert created_response.status_code == 202, created_response.text
        created = created_response.json()
        task_id = created["task_id"]
        first_run = _wait_run(client, created["run_id"])
        assert first_run["status"] in {"FAILED", "BLOCKED"}
        assert first_run["waiting_reason"] == "LEGACY_PROVIDER_AUTHORIZATION_REQUIRED"

        # A Task from another Session must not become readable merely because
        # the same SUPPORT actor owns both Sessions.
        other_order = "async-order-recovery-other"
        prepare_s3_fixture(demo_db, "DELIVERY_FAILED", order_id=other_order)
        other_session = client.post("/api/sessions", headers=headers)
        assert other_session.status_code == 201, other_session.text
        other_session_id = other_session.json()["session_id"]
        other_task_response = client.post(
            f"/api/sessions/{other_session_id}/tasks",
            headers={**headers, "Idempotency-Key": "r1-recovery-other-task"},
            json={
                "investigation_kind": "ASYNC_CALLBACK",
                "s3_order_id": other_order,
                "initial_message": "请调查另一隔离订单。",
            },
        )
        assert other_task_response.status_code == 202, other_task_response.text
        other_task = other_task_response.json()
        _wait_run(client, other_task["run_id"])
        with connect(demo_db) as connection:
            before_wrong_scope = {
                "messages": connection.execute(
                    "SELECT COUNT(*) FROM messages WHERE session_id=?", (session_id,),
                ).fetchone()[0],
                "runs": connection.execute(
                    "SELECT COUNT(*) FROM task_runs WHERE session_id=?", (session_id,),
                ).fetchone()[0],
            }
        wrong_task_scope = client.post(
            f"/api/sessions/{session_id}/assistant/messages",
            headers={**headers, "Idempotency-Key": "r1-recovery-cross-session-task"},
            json={
                "task_id": other_task["task_id"],
                "input_kind": "CHAT_READONLY",
                "body": "请查询这个 Task 的订单状态。",
            },
        )
        assert wrong_task_scope.status_code == 404, wrong_task_scope.text
        assert wrong_task_scope.json()["code"] == "SESSION_TASK_LINK_REQUIRED"
        with connect(demo_db) as connection:
            assert connection.execute(
                "SELECT COUNT(*) FROM messages WHERE session_id=?", (session_id,),
            ).fetchone()[0] == before_wrong_scope["messages"]
            assert connection.execute(
                "SELECT COUNT(*) FROM task_runs WHERE session_id=?", (session_id,),
            ).fetchone()[0] == before_wrong_scope["runs"]

        correction_response = client.post(
            f"/api/sessions/{session_id}/messages",
            headers={**headers, "Idempotency-Key": "r1-recovery-c02-correction"},
            json={
                "task_id": task_id,
                "input_kind": "CORRECT_TASK_INPUT",
                "body": "正式更正：请重新调查 async-order-2 当前回调失败情况。",
            },
        )
        assert correction_response.status_code == 202, correction_response.text
        correction = correction_response.json()
        correction_replay = client.post(
            f"/api/sessions/{session_id}/messages",
            headers={**headers, "Idempotency-Key": "r1-recovery-c02-correction"},
            json={
                "task_id": task_id,
                "input_kind": "CORRECT_TASK_INPUT",
                "body": "正式更正：请重新调查 async-order-2 当前回调失败情况。",
            },
        )
        assert correction_replay.status_code == 202, correction_replay.text
        assert correction_replay.json()["message_id"] == correction["message_id"]
        assert correction_replay.json()["run_id"] == correction["run_id"]
        correction_run = _wait_run(client, correction["run_id"])
        assert correction_run["status"] in {"FAILED", "BLOCKED"}
        assert correction_run["waiting_reason"] == "LEGACY_PROVIDER_AUTHORIZATION_REQUIRED"

        readonly_response = client.post(
            f"/api/sessions/{session_id}/assistant/messages",
            headers={**headers, "Idempotency-Key": "r1-recovery-c03-readonly"},
            json={
                "task_id": task_id,
                "input_kind": "CHAT_READONLY",
                "body": "不要重跑正式调查；请用当前授权的只读工具重新查询绑定订单的回调状态。",
            },
        )
        assert readonly_response.status_code == 202, readonly_response.text
        readonly = readonly_response.json()
        run = _wait_run(client, readonly["run_id"])

        # This assertion is intentionally GREEN-targeted: on the frozen base,
        # the Run is FAILED with TASK_INPUT_PENDING before the FixtureModel runs.
        assert run["status"] == "SUCCEEDED", run
        assert model.seen, "the deterministic model must be reached"
        assert {decision.get("tool") for decision in model.decisions} >= {
            "get_callback_delivery", "get_receiver_processing",
        }

        messages = client.get(f"/api/sessions/{session_id}/messages").json()["items"]
        answer = next(
            item["body"] for item in messages
            if item.get("answer_source_message_id") == readonly["message_id"]
        )
        assert "event-" in answer
        assert "Delivery HTTP 503" in answer
        assert "Receiver 为 NOT_RECEIVED" in answer
        sent_text = "\n".join(
            str(getattr(message, "content", ""))
            for turn in model.seen for message in turn
        )
        assert "不要重跑正式调查" in sent_text

        source_response = client.get(f"/api/runs/{readonly['run_id']}/assistant-sources")
        assert source_response.status_code == 200, source_response.text
        assert source_response.json()["current"] is True, source_response.json()

        with connect(demo_db) as connection:
            control = connection.execute(
                "SELECT control_revision,pending_critical_message_seq,applied_critical_message_seq "
                "FROM task_controls WHERE task_id=?", (task_id,),
            ).fetchone()
            correction_state = connection.execute(
                "SELECT sequence,application_state,applied_run_id FROM messages WHERE message_id=?",
                (correction["message_id"],),
            ).fetchone()
            correction_run_row = connection.execute(
                "SELECT kind,status,blocked_reason,expected_control_revision,source_message_id "
                "FROM task_runs WHERE run_id=?", (correction["run_id"],),
            ).fetchone()
            calls = connection.execute(
                "SELECT call_id,kind,status,request_json,result_json,evidence_id,observation_id "
                "FROM assistant_calls WHERE run_id=? ORDER BY created_at",
                (readonly["run_id"],),
            ).fetchall()
            binding_status = connection.execute(
                "SELECT status FROM task_bindings WHERE task_id=?", (task_id,),
            ).fetchone()[0]
            assert control["pending_critical_message_seq"] == correction["sequence"]
            assert control["applied_critical_message_seq"] < correction["sequence"]
            assert correction_state["application_state"] == "RECEIVED_NOT_APPLIED"
            assert correction_state["applied_run_id"] is None
            assert correction_run_row["kind"] == "INVESTIGATE"
            assert correction_run_row["expected_control_revision"] == 1
            assert correction_run_row["source_message_id"] == correction["message_id"]
            assert correction_run_row["status"] in {"FAILED", "BLOCKED"}
            assert correction_run_row["blocked_reason"] == "LEGACY_PROVIDER_AUTHORIZATION_REQUIRED"
            assert binding_status == "WAITING_INPUT"
            assert connection.execute(
                "SELECT COUNT(*) FROM messages WHERE task_id=? AND input_kind='CORRECT_TASK_INPUT'",
                (task_id,),
            ).fetchone()[0] == 1
            mcp_calls = [row for row in calls if row["kind"] == "MCP" and row["status"] == "OK"]
            assert {json.loads(row["request_json"])["name"] for row in mcp_calls} == {
                "get_callback_delivery", "get_receiver_processing",
            }
            assert len(mcp_calls) == 2
            assert all(row["evidence_id"] and row["observation_id"] for row in mcp_calls)
            results_by_tool = {
                json.loads(row["request_json"])["name"]: json.loads(row["result_json"])
                for row in mcp_calls
            }
            delivery_facts = results_by_tool["get_callback_delivery"]["facts"]
            receiver_facts = results_by_tool["get_receiver_processing"]["facts"]
            assert delivery_facts["order_id"] == receiver_facts["order_id"] == "async-order-2"
            assert delivery_facts["event_id"] == receiver_facts["event_id"]
            assert delivery_facts["status"] == "FAILED"
            assert delivery_facts["receiver_http_status"] == 503
            assert receiver_facts["status"] == "NOT_RECEIVED"
            from opspilot.domain.s3 import get_s3_binding
            binding = get_s3_binding(connection, task_id)
            assert binding["order_id"] == "async-order-2"
            attempts = connection.execute(
                "SELECT attempt_id,call_id,status FROM d2_attempts WHERE run_id=? AND kind='MCP'",
                (readonly["run_id"],),
            ).fetchall()
            assert len(attempts) == 2 and all(row["status"] == "OK" for row in attempts)
            for call in mcp_calls:
                observation = connection.execute(
                    "SELECT o.call_id,o.attempt_id,a.run_id FROM d2_tool_observations o "
                    "JOIN d2_attempts a ON a.attempt_id=o.attempt_id "
                    "WHERE o.task_id=? AND o.observation_id=?",
                    (task_id, call["observation_id"]),
                ).fetchone()
                assert observation is not None and observation["run_id"] == readonly["run_id"]
                assert observation["call_id"] == call["call_id"]
                assert observation["attempt_id"] in {row["attempt_id"] for row in attempts}

            for table in (
                "s3_diagnoses", "d3_plans", "d3_approvals", "d3_action_intents", "d3_action_ledgers",
                "d3_delivery_records",
                "s3_handoff_queue_entries", "s3_handoff_receipts",
            ):
                assert connection.execute(f"SELECT COUNT(*) FROM {table} WHERE task_id=?", (task_id,)).fetchone()[0] == 0

        # The Task owner is also the only actor who can use this bound scope.
        other_owner_headers = _login_as(client, "support-b")
        wrong_owner = client.post(
            f"/api/sessions/{session_id}/assistant/messages",
            headers={**other_owner_headers, "Idempotency-Key": "r1-recovery-other-owner"},
            json={
                "task_id": task_id,
                "input_kind": "CHAT_READONLY",
                "body": "请读取这个 Task 的回调状态。",
            },
        )
        assert wrong_owner.status_code == 404, wrong_owner.text
        assert wrong_owner.json()["code"] == "TASK_SCOPE_DENIED"
        with connect(demo_db) as connection:
            assert connection.execute(
                "SELECT COUNT(*) FROM assistant_calls WHERE run_id=? AND kind='MCP'",
                (readonly["run_id"],),
            ).fetchone()[0] == 2

    runs = _run_rows(demo_db, task_id)
    assert runs[-1]["kind"] == "CHAT_READONLY"
    assert runs[-1]["status"] == "SUCCEEDED"


def test_readonly_run_admitted_before_pending_correction_stays_blocked(
    demo_db, tmp_path, monkeypatch,
):
    """A chat from before the pending correction cannot use the new allowance."""
    monkeypatch.setenv("OPSPILOT_LEGACY_PROVIDER_ENABLED", "0")
    monkeypatch.setenv("OPSPILOT_ASSISTANT_RUNTIME_ENABLED", "0")
    monkeypatch.setenv("OPSPILOT_ASSISTANT_PROVIDER_ENABLED", "0")
    monkeypatch.delenv("OPSPILOT_ASSISTANT_EXPERIMENT_ID", raising=False)
    monkeypatch.delenv("OPSPILOT_ASSISTANT_EXPERIMENT", raising=False)

    prepare_s3_fixture(demo_db, "DELIVERY_FAILED", order_id="async-order-stale-chat")
    checkpoint = tmp_path / "stale-chat-checkpoint.sqlite3"
    model = IntegrationFixtureModel(mode="current-event-only")
    app_without_worker = create_app(
        db_path=demo_db,
        checkpoint_db_path=checkpoint,
        start_worker=False,
        credentials=PASSWORDS,
        expected_origin=ORIGIN,
        assistant_model_factory=lambda: model,
        assistant_runtime_enabled=False,
    )

    with TestClient(app_without_worker) as client:
        headers = _login(client)
        session_id = client.post("/api/sessions", headers=headers).json()["session_id"]
        task_response = client.post(
            f"/api/sessions/{session_id}/tasks",
            headers={**headers, "Idempotency-Key": "r1-stale-chat-create-task"},
            json={
                "investigation_kind": "ASYNC_CALLBACK",
                "s3_order_id": "async-order-stale-chat",
                "initial_message": "请调查订单回调状态。",
            },
        )
        assert task_response.status_code == 202, task_response.text
        task = task_response.json()
        readonly_response = client.post(
            f"/api/sessions/{session_id}/assistant/messages",
            headers={**headers, "Idempotency-Key": "r1-stale-chat-before-correction"},
            json={
                "task_id": task["task_id"],
                "input_kind": "CHAT_READONLY",
                "body": "请只读查询订单回调状态。",
            },
        )
        assert readonly_response.status_code == 202, readonly_response.text
        stale_chat = readonly_response.json()
        correction_response = client.post(
            f"/api/sessions/{session_id}/messages",
            headers={**headers, "Idempotency-Key": "r1-stale-chat-critical-correction"},
            json={
                "task_id": task["task_id"],
                "input_kind": "CORRECT_TASK_INPUT",
                "body": "正式更正：请重新调查该订单的回调状态。",
            },
        )
        assert correction_response.status_code == 202, correction_response.text
        correction = correction_response.json()

    app_with_worker = create_app(
        db_path=demo_db,
        checkpoint_db_path=checkpoint,
        start_worker=True,
        credentials=PASSWORDS,
        expected_origin=ORIGIN,
        assistant_model_factory=lambda: model,
        assistant_runtime_enabled=False,
    )
    with TestClient(app_with_worker) as client:
        _login(client)
        stale_run = _wait_run(client, stale_chat["run_id"])
        correction_run = _wait_run(client, correction["run_id"])
        assert stale_run["status"] in {"FAILED", "BLOCKED"}, stale_run
        assert stale_run["waiting_reason"] == "TASK_INPUT_PENDING", stale_run
        assert correction_run["status"] in {"FAILED", "BLOCKED"}, correction_run
        assert correction_run["waiting_reason"] == "LEGACY_PROVIDER_AUTHORIZATION_REQUIRED"
        assert model.seen == [], "stale readonly and unauthorized Investigator must stop before Provider"

    with connect(demo_db) as connection:
        control = connection.execute(
            "SELECT control_revision,pending_critical_message_seq,applied_critical_message_seq "
            "FROM task_controls WHERE task_id=?", (task["task_id"],),
        ).fetchone()
        correction_message = connection.execute(
            "SELECT sequence,application_state,applied_run_id FROM messages WHERE message_id=?",
            (correction["message_id"],),
        ).fetchone()
        stale_run_row = connection.execute(
            "SELECT consumed_message_seq,expected_control_revision FROM task_runs WHERE run_id=?",
            (stale_chat["run_id"],),
        ).fetchone()
        assert control["pending_critical_message_seq"] == correction_message["sequence"]
        assert control["applied_critical_message_seq"] < correction_message["sequence"]
        assert correction_message["application_state"] == "RECEIVED_NOT_APPLIED"
        assert correction_message["applied_run_id"] is None
        assert stale_run_row["consumed_message_seq"] < correction_message["sequence"]
        assert stale_run_row["expected_control_revision"] == 0
        assert connection.execute(
            "SELECT COUNT(*) FROM assistant_calls WHERE run_id IN (?,?)",
            (stale_chat["run_id"], correction["run_id"]),
        ).fetchone()[0] == 0


def test_pending_correction_allowance_never_applies_to_investigator_run(demo_db):
    """The readonly exception cannot authorize a business Investigator Run."""
    from opspilot.domain.task_control import admit_task_message, create_session, create_task_with_initial_run, trusted_identity

    identity = trusted_identity(demo_db, "support-a")
    session = create_session(demo_db, identity)
    task = create_task_with_initial_run(
        demo_db,
        identity,
        session_id=str(session["session_id"]),
        service_id="orders-demo",
        integration_id="integration-a",
        ticket_id="INC-R1-RECOVERY-GUARD",
        initial_message="请调查接口当前故障。",
        idempotency_key="r1-recovery-investigator-guard-create",
    )
    correction = admit_task_message(
        demo_db,
        identity,
        session_id=str(session["session_id"]),
        task_id=str(task["task_id"]),
        input_kind="CORRECT_TASK_INPUT",
        body="正式更正：请重新调查故障。",
        idempotency_key="r1-recovery-investigator-guard-correction",
    )
    with connect(demo_db) as connection:
        connection.execute(
            "UPDATE task_runs SET status='RUNNING' WHERE run_id=?",
            (correction["run_id"],),
        )
        try:
            assert_task_control_in_transaction(
                connection,
                identity.tenant_id,
                str(task["task_id"]),
                run_id=str(correction["run_id"]),
                allow_pending_for_readonly_chat=True,
            )
        except TaskControlError as error:
            assert error.code == "TASK_INPUT_PENDING"
        else:
            raise AssertionError("CHAT_READONLY allowance must never authorize an INVESTIGATE Run")
