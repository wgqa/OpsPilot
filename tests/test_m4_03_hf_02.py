from __future__ import annotations

import asyncio
import json
import os
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import pytest

from test_m4_03_hf_01 import _diagnose, _handoff_request, _revoke_scope
from test_m4_03_s3 import _facts, _prepared_task


def _trace(record: dict[str, object]) -> None:
    path = os.environ.get("OPSPILOT_HF02_TRACE_PATH")
    if path:
        with open(path, "a", encoding="utf-8") as stream:
            stream.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def _accepted_case(tmp_path: Path):
    from opspilot.domain.s3_handoff import submit_s3_handoff

    db, identity, task = _prepared_task(
        tmp_path, "DELIVERY_FAILED", "async-order-2", attempt_count=3,
        max_attempts=3, retry_state="EXHAUSTED",
    )
    diagnosis, _ = _diagnose(db, identity, task)
    accepted = submit_s3_handoff(db, identity, **_handoff_request(db, task, diagnosis))
    return db, identity, task, accepted


def _add_normal_event(db: Path, task: dict[str, object]) -> str:
    from opspilot.domain.database import connect
    from opspilot.domain.events import write_outbox_event

    source_id = f"hf02-normal-{uuid4()}"
    with connect(db) as connection:
        write_outbox_event(
            connection, tenant_id="tenant-a", task_id=None,
            session_id=str(task["session_id"]), source_kind="HF02_TEST_NOTE",
            source_id=source_id, event_kind="NORMAL_SESSION_NOTE",
            payload={"status": "AVAILABLE"},
        )
        seq = connection.execute(
            "SELECT event_seq FROM session_events WHERE source_kind='HF02_TEST_NOTE' AND source_id=?",
            (source_id,),
        ).fetchone()[0]
    return str(seq)


def _event_app(db: Path):
    from opspilot.web.app import create_app
    from test_m4_01_dialogue_updates import PASSWORDS

    return create_app(db_path=db, start_worker=False, credentials=PASSWORDS,
                      expected_origin="http://testserver")


def _call_s3_tool(server, name: str, args: dict[str, object]):
    from mcp.server.mcpserver.context import Context
    from mcp.types import CallToolRequestParams

    context = Context(
        mcp_server=server,
        input_params=CallToolRequestParams(name=name, arguments=args),
    )
    return asyncio.run(server.call_tool(name, args, context))


def test_revoked_support_event_history_hides_only_s3_diagnosis_and_handoff(tmp_path: Path):
    from fastapi.testclient import TestClient
    from opspilot.domain.database import connect
    from opspilot.domain.events import list_session_events
    from opspilot.domain.task_control import trusted_identity
    from test_m4_01_dialogue_updates import _login

    db, identity, task, accepted = _accepted_case(tmp_path)
    with connect(db) as connection:
        before = list_session_events(db, str(task["session_id"]), identity)
    visible_kinds = {str(item["event_kind"]) for item in before}
    assert "S3_DIAGNOSIS_FROZEN" in visible_kinds
    assert "S3_HANDOFF_ACCEPTED" in visible_kinds
    accepted_seq = max(int(item["event_seq"]) for item in before
                       if item["event_kind"] == "S3_HANDOFF_ACCEPTED")
    note_seq = int(_add_normal_event(db, task))
    _revoke_scope(db, task)

    with TestClient(_event_app(db), raise_server_exceptions=False) as client:
        support_headers = _login(client, "support-a")
        response = client.get(
            f"/api/sessions/{task['session_id']}/events/history", headers=support_headers,
        )
        assert response.status_code == 200
        payload = response.json()
        events = payload["items"]
        kinds = {item["event_kind"] for item in events}
        assert "S3_DIAGNOSIS_FROZEN" not in kinds, f"revoked S3 diagnosis leaked: {events!r}"
        assert "S3_HANDOFF_ACCEPTED" not in kinds, f"revoked S3 receipt leaked: {events!r}"
        serialized = json.dumps(events, ensure_ascii=False)
        assert accepted["receipt_id"] not in serialized
        assert accepted["queue_entry_id"] not in serialized
        assert "async-order-2" not in serialized
        assert "HANDOFF_ACCEPTED" not in serialized
        assert "NORMAL_SESSION_NOTE" in kinds
        assert int(payload["next_after"]) >= note_seq > accepted_seq

        resumed = client.get(
            f"/api/sessions/{task['session_id']}/events/history",
            params={"after": 0}, headers={**support_headers, "Last-Event-ID": str(accepted_seq)},
        )
        assert resumed.status_code == 200
        assert all(item["event_kind"] != "S3_HANDOFF_ACCEPTED" for item in resumed.json()["items"])
        assert "NORMAL_SESSION_NOTE" in {item["event_kind"] for item in resumed.json()["items"]}

        owner_handoff = client.get(f"/api/tasks/{task['task_id']}/s3-handoff", headers=support_headers)
        assert owner_handoff.status_code == 403
        approver_headers = _login(client, "approver-a")
        audit = client.get(f"/api/tasks/{task['task_id']}/s3-handoff", headers=approver_headers)
        assert audit.status_code == 200
        assert audit.json()["handoff_receipt"]["receipt_id"] == accepted["receipt_id"]
        assert "diagnosis_receipt" not in audit.json()
        assert client.get(
            f"/api/sessions/{task['session_id']}/events/history", headers=approver_headers,
        ).status_code in (403, 404)

        support_headers = _login(client, "support-a")
        inspector = client.get(f"/api/tasks/{task['task_id']}/inspector", headers=support_headers)
        assert inspector.status_code == 200
        inspector_json = json.dumps(inspector.json(), ensure_ascii=False)
        assert accepted["receipt_id"] not in inspector_json
        assert accepted["queue_entry_id"] not in inspector_json
        assert "HANDOFF_ACCEPTED" not in inspector_json
        messages = client.get(f"/api/sessions/{task['session_id']}/messages", headers=support_headers)
        assert messages.status_code == 200
        assert any("订单接口返回" in item["body"] for item in messages.json()["items"])
        for suffix in ("context", "chunks"):
            other_surface = client.get(
                f"/api/runs/{task['run_id']}/{suffix}", headers=support_headers,
            )
            assert accepted["receipt_id"] not in other_surface.text

    _trace({
        "case": "HF02-01-history-read-audit", "task_id": str(task["task_id"]),
        "session_id": str(task["session_id"]), "accepted_event_seq": accepted_seq,
        "normal_event_seq": note_seq, "receipt_id": accepted["receipt_id"],
        "support_history_status": response.status_code,
        "visible_event_kinds_after_revocation": sorted(kinds),
        "approver_receipt_audit_status": audit.status_code,
        "inspector_status": inspector.status_code,
        "history_next_after": payload["next_after"],
    })


def test_revoked_support_sse_uses_same_s3_event_filter(tmp_path: Path, monkeypatch):
    from fastapi.testclient import TestClient
    from starlette.requests import Request
    from test_m4_01_dialogue_updates import _login

    db, _, task, accepted = _accepted_case(tmp_path)
    note_seq = int(_add_normal_event(db, task))
    _revoke_scope(db, task)
    calls = {"count": 0}

    async def disconnect_after_one_poll(_request):
        calls["count"] += 1
        return calls["count"] > 1

    monkeypatch.setattr(Request, "is_disconnected", disconnect_after_one_poll)
    with TestClient(_event_app(db), raise_server_exceptions=False) as client:
        with client.stream(
            "GET", f"/api/sessions/{task['session_id']}/events", headers=_login(client, "support-a"),
        ) as response:
            body = response.read().decode("utf-8")
        assert response.status_code == 200
    assert accepted["receipt_id"] not in body
    assert accepted["queue_entry_id"] not in body
    assert "S3_HANDOFF_ACCEPTED" not in body
    assert "S3_DIAGNOSIS_FROZEN" not in body
    assert "NORMAL_SESSION_NOTE" in body
    assert f"id: {note_seq}" in body
    _trace({
        "case": "HF02-01-sse-read-audit", "task_id": str(task["task_id"]),
        "session_id": str(task["session_id"]), "normal_event_seq": note_seq,
        "receipt_id": accepted["receipt_id"], "sse_status": response.status_code,
        "s3_event_names_exposed": False, "normal_event_delivered": True,
    })


def test_scope_revocation_audits_task_run_inspector_context_chunks_and_messages(tmp_path: Path):
    from fastapi.testclient import TestClient
    from test_m4_01_dialogue_updates import _login

    db, _, task, accepted = _accepted_case(tmp_path)
    _revoke_scope(db, task)
    with TestClient(_event_app(db), raise_server_exceptions=False) as client:
        support = _login(client, "support-a")
        task_view = client.get(f"/api/tasks/{task['task_id']}", headers=support)
        run_view = client.get(f"/api/runs/{task['run_id']}", headers=support)
        inspector = client.get(f"/api/tasks/{task['task_id']}/inspector", headers=support)
        messages = client.get(f"/api/sessions/{task['session_id']}/messages", headers=support)
        context = client.get(f"/api/runs/{task['run_id']}/context", headers=support)
        chunks = client.get(f"/api/runs/{task['run_id']}/chunks", headers=support)
    assert task_view.status_code == 200 and run_view.status_code == 200
    assert inspector.status_code == 200 and messages.status_code == 200
    for response in (task_view, run_view, inspector, messages, context, chunks):
        assert accepted["receipt_id"] not in response.text
        assert accepted["queue_entry_id"] not in response.text
        assert "HANDOFF_ACCEPTED" not in response.text
    assert "async-order-2" not in task_view.text
    assert "async-order-2" not in run_view.text
    assert "async-order-2" not in inspector.text
    assert any("订单接口返回" in item["body"] for item in messages.json()["items"])
    # Run Context and chat chunks only accept CHAT_READONLY Runs; this S3
    # investigator Run cannot be used as a second fact-reading route.
    assert context.status_code != 200
    assert chunks.status_code != 200
    _trace({
        "case": "HF02-01-additional-read-surface-audit", "task_id": str(task["task_id"]),
        "support_task_status": task_view.status_code, "run_status": run_view.status_code,
        "inspector_status": inspector.status_code, "messages_status": messages.status_code,
        "run_context_status": context.status_code, "run_chunks_status": chunks.status_code,
        "handoff_receipt_exposed": False, "normal_owner_message_retained": True,
    })


def test_revoked_scope_blocks_s3_chat_context_chunks_and_redacts_bound_answer(tmp_path: Path):
    from fastapi.testclient import TestClient
    from opspilot.domain.chat import (
        complete_chat_attempt, persist_chat_chunk, prepare_chat_attempt,
    )
    from opspilot.domain.task_control import (
        admit_task_message, claim_task_run, register_worker_owner, trusted_identity,
    )
    from test_m4_01_dialogue_updates import _login

    db, identity, task, accepted = _accepted_case(tmp_path)
    worker_id = "hf02-chat-worker"
    register_worker_owner(db, worker_id, 84102)
    message = admit_task_message(
        db, identity, session_id=str(task["session_id"]), task_id=str(task["task_id"]),
        input_kind="CHAT_READONLY", body="请复述当前 S3 交接结果。",
        idempotency_key="hf02-bound-chat-answer",
    )
    run_id = str(message["run_id"])
    claim_task_run(db, identity, run_id)
    prepared = prepare_chat_attempt(db, run_id, worker_id, "hf02-test-model")
    answer = (
        f"HANDOFF_ACCEPTED receipt_id={accepted['receipt_id']} "
        f"queue_entry_id={accepted['queue_entry_id']} order_id=async-order-2"
    )
    persist_chat_chunk(db, worker_id, str(prepared["attempt_id"]), 1, answer)
    complete_chat_attempt(
        db, worker_id, str(prepared["attempt_id"]), answer,
        provider_response_id=f"hf02-test-provider-{prepared['attempt_id']}",
        input_tokens=5, output_tokens=8, total_tokens=13,
    )
    with TestClient(_event_app(db), raise_server_exceptions=False) as client:
        support = _login(client, "support-a")
        current_chunks = client.get(f"/api/runs/{run_id}/chunks", headers=support)
        current_context = client.get(f"/api/runs/{run_id}/context", headers=support)
        current_messages = client.get(f"/api/sessions/{task['session_id']}/messages", headers=support)
        assert current_chunks.status_code == current_context.status_code == 200
        assert accepted["receipt_id"] in current_chunks.text
        assert accepted["receipt_id"] in current_messages.text

    _revoke_scope(db, task)
    with TestClient(_event_app(db), raise_server_exceptions=False) as client:
        support = _login(client, "support-a")
        chunks = client.get(f"/api/runs/{run_id}/chunks", headers=support)
        context = client.get(f"/api/runs/{run_id}/context", headers=support)
        messages = client.get(f"/api/sessions/{task['session_id']}/messages", headers=support)
    exposed = {
        name: [value for value in (
            accepted["receipt_id"], accepted["queue_entry_id"], "HANDOFF_ACCEPTED", "async-order-2",
        ) if value in response.text]
        for name, response in (("chunks", chunks), ("context", context), ("messages", messages))
    }
    assert not any(exposed.values()), f"restricted S3 chat data remained readable: {exposed!r}"
    assert chunks.status_code != 200
    assert context.status_code != 200
    assert messages.status_code == 200
    items = messages.json()["items"]
    assert any(item["role"] == "USER" and item["body"] == "请复述当前 S3 交接结果。" for item in items)
    answer_row = next(item for item in items if item["role"] == "ASSISTANT")
    assert "S3 受限历史回答已隐藏" in answer_row["body"]
    _trace({
        "case": "HF02-01-revoked-s3-chat-read-audit", "task_id": str(task["task_id"]),
        "run_id": run_id, "attempt_id": str(prepared["attempt_id"]),
        "receipt_id": accepted["receipt_id"], "queue_entry_id": accepted["queue_entry_id"],
        "chunks_status_after_revocation": chunks.status_code,
        "context_status_after_revocation": context.status_code,
        "messages_status_after_revocation": messages.status_code,
        "user_message_retained": True, "assistant_body_redacted": True,
    })


@pytest.mark.parametrize(("table", "column", "where", "params"), [
    ("route_scope_policies", "scope_policy_version", "tenant_id=? AND service_id=? AND route=?",
     ("tenant-a", "orders-async-demo", "/api/async-orders/async-order")),
    ("principal_scope_grants", "grant_version", "tenant_id=? AND principal_id=?",
     ("tenant-a", "async-principal-a")),
    ("principals", "principal_version", "tenant_id=? AND principal_id=?",
     ("tenant-a", "async-principal-a")),
    ("auth_policies", "policy_version", "tenant_id=? AND service_id=?",
     ("tenant-a", "orders-async-demo")),
    ("integrations", "config_version", "tenant_id=? AND integration_id=?",
     ("tenant-a", "async-integration-a")),
])
def test_fractional_authorization_versions_fail_closed_in_domain(
    tmp_path: Path, table: str, column: str, where: str, params: tuple[str, ...],
):
    from opspilot.domain.database import connect
    from opspilot.domain.d2 import ScopeDenied
    from opspilot.domain.s3 import get_s3_binding

    db, _, task = _prepared_task(tmp_path, "DELIVERED_PENDING", "async-order-2")
    with connect(db) as connection:
        connection.execute("PRAGMA ignore_check_constraints=ON")
        connection.execute(f"UPDATE {table} SET {column}=1.5 WHERE {where}", params)
        with pytest.raises(ScopeDenied):
            get_s3_binding(connection, str(task["task_id"]))


@pytest.mark.parametrize("invalid", [True, False, 1.0, 1.5, "1", "bad", None, 0, -1])
def test_s3_positive_version_parser_is_strict(invalid):
    from opspilot.domain.s3 import _strict_positive_version

    with pytest.raises(ValueError):
        _strict_positive_version(invalid)


@pytest.mark.parametrize("surface", ["domain", "web", "mcp"])
def test_fractional_scope_policy_version_fails_closed_across_read_surfaces(tmp_path: Path, surface: str):
    from fastapi.testclient import TestClient
    from mcp.server.mcpserver.exceptions import ToolError
    from opspilot.domain.database import connect
    from opspilot.domain.d2 import ScopeDenied
    from opspilot.domain.s3 import get_s3_binding
    from opspilot.domain.s3_mcp import build_s3_server
    from opspilot.web.app import create_app
    from test_m4_01_dialogue_updates import PASSWORDS, _login

    db, _, task = _prepared_task(tmp_path, "DELIVERY_FAILED", "async-order-2")
    with connect(db) as connection:
        connection.execute("PRAGMA ignore_check_constraints=ON")
        connection.execute(
            "UPDATE route_scope_policies SET scope_policy_version=1.5 "
            "WHERE tenant_id='tenant-a' AND service_id='orders-async-demo' "
            "AND route='/api/async-orders/async-order'"
        )
    if surface == "domain":
        with connect(db) as connection, pytest.raises(ScopeDenied):
            get_s3_binding(connection, str(task["task_id"]))
    elif surface == "web":
        app = create_app(db_path=db, start_worker=False, credentials=PASSWORDS,
                         expected_origin="http://testserver")
        with TestClient(app, raise_server_exceptions=False) as client:
            response = client.get("/api/s3/order-resources", headers=_login(client, "support-a"))
            assert response.status_code != 200
            assert "async-order-2" not in response.text
    else:
        from opspilot.domain.api import make_server
        api = make_server(db, "tenant-a", "127.0.0.1", 0)
        thread = threading.Thread(target=api.serve_forever, daemon=True)
        thread.start()
        try:
            server = build_s3_server(db, str(task["task_id"]), f"http://127.0.0.1:{api.server_port}")
            with pytest.raises(ToolError):
                _call_s3_tool(server, "get_order_status", {"reason": "validate strict scope version"})
        finally:
            api.shutdown()
            thread.join(timeout=5)
            api.server_close()


def _set_accepted_at(db: Path, accepted_at: str) -> None:
    from opspilot.domain.database import connect
    from opspilot.domain.d2 import canonical_json, digest_json

    with connect(db) as connection:
        receiver = connection.execute(
            "SELECT event_id FROM s3_receivers WHERE tenant_id='tenant-a' "
            "AND service_id='orders-async-demo' AND order_id='async-order-2'"
        ).fetchone()
        connection.execute(
            "UPDATE s3_receivers SET accepted_at=? WHERE tenant_id='tenant-a' "
            "AND service_id='orders-async-demo' AND order_id='async-order-2'", (accepted_at,),
        )
        delivery = connection.execute(
            "SELECT transport_response_json FROM s3_deliveries WHERE tenant_id='tenant-a' "
            "AND service_id='orders-async-demo' AND order_id='async-order-2'"
        ).fetchone()
        response = json.loads(str(delivery["transport_response_json"]))
        response.update(accepted_at=accepted_at, event_id=str(receiver["event_id"]))
        connection.execute(
            "UPDATE s3_deliveries SET transport_response_json=?,response_digest=? "
            "WHERE tenant_id='tenant-a' AND service_id='orders-async-demo' AND order_id='async-order-2'",
            (canonical_json(response), digest_json(response)),
        )


def test_sla_gate_exact_deadline_is_wait_before_contact_at_and_after(tmp_path: Path, monkeypatch):
    import opspilot.domain.s3 as s3
    from opspilot.domain.database import connect
    from opspilot.domain.s3 import evaluate_s3_gate

    db, identity, task = _prepared_task(
        tmp_path, "DELIVERED_PENDING", "async-order-2", processing_sla_seconds=300,
    )
    now = datetime.now(timezone.utc).replace(microsecond=0)

    class FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            current = clock["now"]
            return current if tz is not None else current.replace(tzinfo=None)

    clock = {"now": now}
    monkeypatch.setattr(s3, "datetime", FrozenDateTime)
    for offset, expected in ((-1, "WAIT_FOR_RECEIVER_PROCESSING"),
                             (0, "CONTACT_RECEIVER_OPERATOR"),
                             (1, "CONTACT_RECEIVER_OPERATOR")):
        accepted_at = (now - timedelta(seconds=300 + offset)).isoformat().replace("+00:00", "Z")
        _set_accepted_at(db, accepted_at)
        order, delivery, receiver = _facts(db, task)
        ids = [
            _record_evidence(db, task, "get_order_status", order),
            _record_evidence(db, task, "get_callback_delivery", delivery),
            _record_evidence(db, task, "get_receiver_processing", receiver),
        ]
        decision = evaluate_s3_gate(db, str(task["task_id"]), ids)
        assert decision["handling_direction"] == expected
        if offset == -1:
            clock["now"] = now + timedelta(seconds=1)
            exact = evaluate_s3_gate(db, str(task["task_id"]), ids)
            assert exact["handling_direction"] == "CONTACT_RECEIVER_OPERATOR"
            clock["now"] = now


def _record_evidence(db: Path, task: dict[str, object], tool: str, result: dict[str, object]) -> str:
    from opspilot.domain.d2 import record_tool_observation

    call_id = f"hf02-boundary-{uuid4()}"
    return str(record_tool_observation(
        db, task_id=str(task["task_id"]), call_id=call_id, attempt_id=None,
        tool_call_id=call_id, tool_name=tool, arguments={}, status="OK", result=result,
    )["evidence_id"])


def test_sla_expiry_at_exact_deadline_keeps_evidence_but_invalidates_immutable_wait(tmp_path: Path, monkeypatch):
    import opspilot.domain.s3 as s3
    from opspilot.domain.database import connect
    from opspilot.domain.s3 import current_s3_evidence, get_s3_outcome

    db, identity, task = _prepared_task(
        tmp_path, "DELIVERED_PENDING", "async-order-2", queue_age_seconds=299,
        processing_sla_seconds=300,
    )
    clock = {"now": datetime.now(timezone.utc).replace(microsecond=0)}

    class FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            current = clock["now"]
            return current if tz is not None else current.replace(tzinfo=None)

    monkeypatch.setattr(s3, "datetime", FrozenDateTime)
    accepted_at = (clock["now"] - timedelta(seconds=299)).isoformat().replace("+00:00", "Z")
    _set_accepted_at(db, accepted_at)
    diagnosis, evidence_ids = _diagnose(db, identity, task, state="DELIVERED_PENDING")
    original_body, original_digest = diagnosis["body_json"], diagnosis["digest"]
    assert get_s3_outcome(db, str(task["task_id"]))["handling_direction"] == "WAIT_FOR_RECEIVER_PROCESSING"
    clock["now"] += timedelta(seconds=1)
    current = get_s3_outcome(db, str(task["task_id"]))
    assert current["currentness"] == "INVALIDATED_BY_CURRENT_FACTS"
    assert current["gate"]["reason_code"] == "S3_SLA_EXPIRED"
    with connect(db) as connection:
        evidence, excluded = current_s3_evidence(connection, str(task["task_id"]), evidence_ids)
        stored = connection.execute(
            "SELECT body_json,digest FROM s3_diagnoses WHERE receipt_id=?", (diagnosis["receipt_id"],),
        ).fetchone()
    assert len(evidence) == 3 and excluded == []
    assert stored["body_json"] == original_body and stored["digest"] == original_digest


def _run_mcp_facts(db: Path, identity, task: dict[str, object], run_id: str, server) -> list[str]:
    from opspilot.domain.d2 import digest_json, finish_attempt, record_tool_observation, reserve_attempt
    from opspilot.domain.investigation_context import load_investigation_context

    evidence_ids: list[str] = []
    for tool in ("get_order_status", "get_callback_delivery", "get_receiver_processing"):
        args = {"reason": "M4-03-HF-02 controlled current-time S3 investigation"}
        call_id, tool_call_id = f"hf02-{uuid4()}", f"tool-{uuid4()}"
        control = load_investigation_context(db, str(task["task_id"]), run_id)["task_run_control"]
        attempt_id, attempt_no = reserve_attempt(
            db, str(task["task_id"]), "MCP", 6, call_id=call_id,
            tool_call_id=tool_call_id, tool_name=tool, argument_digest=digest_json(args),
            run_id=run_id, task_run_control=control,
        )
        # MCPServer.call_tool() is the real in-process server path; provide the
        # same request params that _handle_call_tool() normally attaches so the
        # server can enforce its raw argument allowlist.
        result = _call_s3_tool(server, tool, args)
        assert not result.is_error
        value = result.structured_content
        if value is None:
            value = json.loads("".join(block.text for block in result.content if hasattr(block, "text")))
        if isinstance(value, dict) and isinstance(value.get("result"), dict):
            value = value["result"]
        from opspilot.domain.schemas import D2ToolFact
        normalized = D2ToolFact.model_validate(value).model_dump(mode="json")
        observation = record_tool_observation(
            db, task_id=str(task["task_id"]), call_id=call_id, attempt_id=attempt_id,
            tool_call_id=tool_call_id, tool_name=tool, arguments=args, status="OK", result=normalized,
        )
        finish_attempt(db, attempt_id, "OK", result_digest=digest_json(normalized))
        evidence_id = str(observation["evidence_id"])
        evidence_ids.append(evidence_id)
        _trace({
            "case": "HF02-03-fresh-sla-investigation", "run_id": run_id,
            "attempt_id": attempt_id, "attempt_no": attempt_no,
            "call_id": call_id, "tool_call_id": tool_call_id,
            "tool_name": tool, "evidence_id": evidence_id,
            "task_id": str(task["task_id"]), "status": observation["status"],
            "fact_type": normalized["fact_type"],
            "observed_versions": normalized["observed_versions"],
            "request_id": normalized.get("facts", {}).get("body", {}).get("request_id"),
            "event_id": normalized.get("facts", {}).get("event_id"),
        })
    return evidence_ids


def test_sla_recovery_uses_fresh_real_http_mcp_evidence_before_one_handoff(tmp_path: Path, monkeypatch):
    from fastapi.testclient import TestClient
    from opspilot.domain.api import make_server
    from opspilot.domain.database import connect
    from opspilot.domain.s3 import get_s3_outcome, persist_s3_diagnosis
    from opspilot.domain.s3_handoff import submit_s3_handoff
    from opspilot.domain.s3_mcp import build_s3_server
    from opspilot.domain.task_control import (
        TaskControlError, admit_task_message, apply_pending_critical_inputs,
        claim_task_run, finish_task_run,
    )
    import opspilot.domain.s3 as s3

    db, identity, task = _prepared_task(
        tmp_path, "DELIVERED_PENDING", "async-order-2", queue_age_seconds=299,
        processing_sla_seconds=300,
    )
    clock = {"now": datetime.now(timezone.utc).replace(microsecond=0)}

    class FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            current = clock["now"]
            return current if tz is not None else current.replace(tzinfo=None)

    monkeypatch.setattr(s3, "datetime", FrozenDateTime)
    accepted_at = (clock["now"] - timedelta(seconds=299)).isoformat().replace("+00:00", "Z")
    _set_accepted_at(db, accepted_at)
    api = make_server(db, "tenant-a", "127.0.0.1", 0)
    thread = threading.Thread(target=api.serve_forever, daemon=True)
    thread.start()
    try:
        root = f"http://127.0.0.1:{api.server_port}"
        claim_task_run(db, identity, str(task["run_id"]))
        apply_pending_critical_inputs(db, identity, str(task["run_id"]))
        initial_server = build_s3_server(db, str(task["task_id"]), root)
        initial_ids = _run_mcp_facts(db, identity, task, str(task["run_id"]), initial_server)
        initial = persist_s3_diagnosis(db, str(task["task_id"]), str(task["run_id"]), initial_ids)
        finish_task_run(db, identity, str(task["run_id"]), "SUCCEEDED")
        assert json.loads(initial["body_json"])["gate"]["handling_direction"] == "WAIT_FOR_RECEIVER_PROCESSING"
        initial_request = _handoff_request(db, task, initial)
        clock["now"] += timedelta(seconds=1)
        assert get_s3_outcome(db, str(task["task_id"]))["currentness"] == "INVALIDATED_BY_CURRENT_FACTS"
        with connect(db) as connection:
            before = tuple(connection.execute(
                "SELECT (SELECT COUNT(*) FROM s3_handoff_queue_entries WHERE task_id=?),"
                "(SELECT COUNT(*) FROM s3_handoff_receipts WHERE task_id=?),"
                "(SELECT COUNT(*) FROM domain_outbox WHERE task_id=? AND event_kind='S3_HANDOFF_ACCEPTED')",
                (task["task_id"], task["task_id"], task["task_id"]),
            ).fetchone())
        with pytest.raises(TaskControlError):
            submit_s3_handoff(db, identity, **initial_request)
        with connect(db) as connection:
            after = tuple(connection.execute(
                "SELECT (SELECT COUNT(*) FROM s3_handoff_queue_entries WHERE task_id=?),"
                "(SELECT COUNT(*) FROM s3_handoff_receipts WHERE task_id=?),"
                "(SELECT COUNT(*) FROM domain_outbox WHERE task_id=? AND event_kind='S3_HANDOFF_ACCEPTED')",
                (task["task_id"], task["task_id"], task["task_id"]),
            ).fetchone())
            revision = int(connection.execute(
                "SELECT control_revision FROM task_controls WHERE task_id=?", (task["task_id"],),
            ).fetchone()[0])
        assert before == after == (0, 0, 0)

        accepted = admit_task_message(
            db, identity, session_id=str(task["session_id"]), task_id=str(task["task_id"]),
            input_kind="CORRECT_TASK_INPUT",
            body="请按当前时间重新调查这个订单的接收方处理状态。",
            idempotency_key="hf02-fresh-sla-run", expected_control_revision=revision,
        )
        run_id = str(accepted["run_id"])
        claim_task_run(db, identity, run_id)
        applied = apply_pending_critical_inputs(db, identity, run_id)
        assert applied["inputs"]
        fresh_server = build_s3_server(db, str(task["task_id"]), root)
        fresh_ids = _run_mcp_facts(db, identity, task, run_id, fresh_server)
        fresh_diagnosis = persist_s3_diagnosis(db, str(task["task_id"]), run_id, fresh_ids)
        finish_task_run(db, identity, run_id, "SUCCEEDED")
        body = json.loads(fresh_diagnosis["body_json"])
        assert body["gate"]["handling_direction"] == "CONTACT_RECEIVER_OPERATOR"
        assert body["gate"]["handoff_allowed"] is True
        order_evidence = next(item for item in body["evidence"] if item["fact_type"] == "s3_order")
        order_fact = order_evidence["facts"]["body"]
        request_id = order_fact["request_id"]
        event_id = next(item for item in body["evidence"] if item["fact_type"] == "s3_receiver")["facts"]["event_id"]
        assert order_fact["order_id"] == "async-order-2"
        assert order_fact["status"] == "COMPLETED"
        assert event_id == next(item for item in body["evidence"] if item["fact_type"] == "s3_delivery")["facts"]["event_id"]
        with connect(db) as connection:
            http = connection.execute(
                "SELECT tenant_id,service_id,integration_id,principal_id,route,http_status,body_json "
                "FROM s3_http_observations WHERE request_id=?", (request_id,),
            ).fetchone()
            observations = connection.execute(
                "SELECT DISTINCT tool_name,evidence_id FROM d2_tool_observations "
                "WHERE task_id=? AND evidence_id IN (?,?,?) ORDER BY tool_name",
                (task["task_id"], *fresh_ids),
            ).fetchall()
            revision = int(connection.execute(
                "SELECT control_revision FROM task_controls WHERE task_id=?", (task["task_id"],),
            ).fetchone()[0])
        assert http["http_status"] == 200
        assert http["tenant_id"] == "tenant-a" and http["integration_id"] == "async-integration-a"
        assert http["principal_id"] == "async-principal-a" and http["route"] == "/api/async-orders/async-order"
        assert len(observations) == 3 and {row["evidence_id"] for row in observations} == set(fresh_ids)
        request = {
            "task_id": str(task["task_id"]), "operation_id": "hf02-contact-once",
            "diagnosis_receipt_id": str(fresh_diagnosis["receipt_id"]),
            "diagnosis_digest": str(fresh_diagnosis["digest"]),
            "expected_control_revision": revision,
        }
        receipt = submit_s3_handoff(db, identity, **request)
        replay = submit_s3_handoff(db, identity, **request)
        assert replay["receipt_id"] == receipt["receipt_id"] and replay["replayed"] is True
        with connect(db) as connection:
            counts = tuple(connection.execute(
                "SELECT (SELECT COUNT(*) FROM s3_handoff_queue_entries WHERE task_id=?),"
                "(SELECT COUNT(*) FROM s3_handoff_receipts WHERE task_id=?),"
                "(SELECT COUNT(*) FROM domain_outbox WHERE task_id=? AND event_kind='S3_HANDOFF_ACCEPTED')",
                (task["task_id"], task["task_id"], task["task_id"]),
            ).fetchone())
            receipt_row = connection.execute(
                "SELECT receipt_digest FROM s3_handoff_receipts WHERE receipt_id=?", (receipt["receipt_id"],),
            ).fetchone()
        assert counts == (1, 1, 1)
        assert receipt_row["receipt_digest"]
        _trace({
            "case": "HF02-03-fresh-sla-business-result", "task_id": str(task["task_id"]),
            "initial_run_id": str(task["run_id"]), "initial_diagnosis_receipt_id": str(initial["receipt_id"]),
            "fresh_run_id": run_id, "fresh_diagnosis_receipt_id": str(fresh_diagnosis["receipt_id"]),
            "http_request_id": request_id, "http_status": http["http_status"],
            "http_route": http["route"], "event_id": event_id,
            "fresh_evidence_ids": fresh_ids, "handling_direction": body["gate"]["handling_direction"],
            "handoff_receipt_id": receipt["receipt_id"], "replay_receipt_id": replay["receipt_id"],
            "queue_receipt_outbox_counts": counts,
        })
    finally:
        api.shutdown()
        thread.join(timeout=5)
        api.server_close()
