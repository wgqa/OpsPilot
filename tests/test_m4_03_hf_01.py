from __future__ import annotations

import asyncio
import json
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest

from test_m4_03_s3 import _evidence, _facts, _prepared_task


def _diagnose(db: Path, identity, task: dict[str, object], *, state: str = "DELIVERY_FAILED"):
    from opspilot.domain.s3 import persist_s3_diagnosis
    from opspilot.domain.task_control import apply_pending_critical_inputs, claim_task_run, finish_task_run

    run_id = str(task["run_id"])
    claim_task_run(db, identity, run_id)
    apply_pending_critical_inputs(db, identity, run_id)
    order, delivery, receiver = _facts(db, task)
    ids = [_evidence(db, task, "get_order_status", order)]
    if state == "DELIVERED_PENDING":
        ids.extend([
            _evidence(db, task, "get_callback_delivery", delivery),
            _evidence(db, task, "get_receiver_processing", receiver),
        ])
    else:
        ids.append(_evidence(db, task, "get_callback_delivery", delivery))
    diagnosis = persist_s3_diagnosis(db, str(task["task_id"]), run_id, ids)
    finish_task_run(db, identity, run_id, "SUCCEEDED")
    return diagnosis, ids


def _revoke_scope(db: Path, task: dict[str, object]) -> None:
    from opspilot.domain.database import connect

    with connect(db) as connection:
        principal = connection.execute(
            "SELECT principal_id FROM task_bindings WHERE task_id=?", (task["task_id"],)
        ).fetchone()[0]
        connection.execute(
            "UPDATE principal_scope_grants SET granted_scopes_json='[]', grant_version=grant_version+1 "
            "WHERE tenant_id='tenant-a' AND principal_id=?", (principal,),
        )


def _race(left, right):
    gate = threading.Barrier(3)

    def run(call):
        gate.wait(timeout=10)
        try:
            return ("ok", call())
        except Exception as error:  # each side's domain result is asserted below
            return ("error", error)

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(run, left)
        second = pool.submit(run, right)
        gate.wait(timeout=10)
        return first.result(timeout=30), second.result(timeout=30)


def _handoff_request(db: Path, task: dict[str, object], diagnosis: dict[str, object]) -> dict[str, object]:
    from opspilot.domain.database import connect

    with connect(db) as connection:
        revision = int(connection.execute(
            "SELECT control_revision FROM task_controls WHERE task_id=?", (task["task_id"],)
        ).fetchone()[0])
    return {
        "task_id": str(task["task_id"]), "operation_id": f"hf01-race-{uuid4()}",
        "diagnosis_receipt_id": str(diagnosis["receipt_id"]),
        "diagnosis_digest": str(diagnosis["digest"]),
        "expected_control_revision": revision,
    }


def _record_fresh(
    db: Path, task: dict[str, object], tool: str, result: dict[str, object], *, run_id: str,
) -> str:
    from s3_observation_support import record_s3_observation
    return str(record_s3_observation(db, task, tool, result, run_id=run_id)["evidence_id"])


def test_current_s3_binding_uses_same_versioned_authorization_snapshot(tmp_path: Path):
    from opspilot.domain.database import connect
    from opspilot.domain.d2 import ScopeDenied
    from opspilot.domain.s3 import get_s3_binding

    db, _, task = _prepared_task(tmp_path, "DELIVERY_FAILED", "async-order-2")
    with connect(db) as connection:
        binding = get_s3_binding(connection, str(task["task_id"]))
        assert type(binding["scope_policy_version"]) is int
        assert type(binding["grant_version"]) is int
        connection.execute(
            "UPDATE principal_scope_grants SET granted_scopes_json='[]', grant_version=grant_version+1 "
            "WHERE tenant_id='tenant-a' AND principal_id=?", (binding["principal_id"],),
        )
        with pytest.raises(ScopeDenied):
            get_s3_binding(connection, str(task["task_id"]))


def test_scope_revocation_invalidates_diagnosis_and_blocks_new_handoff(tmp_path: Path):
    from opspilot.domain.database import connect
    from opspilot.domain.s3 import get_s3_outcome
    from opspilot.domain.s3_handoff import submit_s3_handoff
    from opspilot.domain.task_control import TaskControlError

    db, identity, task = _prepared_task(
        tmp_path, "DELIVERY_FAILED", "async-order-2", attempt_count=3,
        max_attempts=3, retry_state="EXHAUSTED",
    )
    diagnosis, _ = _diagnose(db, identity, task)
    with connect(db) as connection:
        revision = int(connection.execute(
            "SELECT control_revision FROM task_controls WHERE task_id=?", (task["task_id"],)
        ).fetchone()[0])
    _revoke_scope(db, task)

    outcome = get_s3_outcome(db, str(task["task_id"]))
    assert outcome["currentness"] == "INVALIDATED_BY_CURRENT_FACTS"
    assert outcome["handoff_allowed"] is False
    assert outcome["explanation"] == ""
    assert "body" not in outcome
    from opspilot.domain.chat import _current_task_state
    with connect(db) as connection:
        chat_state = _current_task_state(connection, str(task["task_id"]))
    assert chat_state["s3_outcome"]["currentness"] == "INVALIDATED_BY_CURRENT_FACTS"
    assert chat_state["s3_outcome"]["outcome"] == "INCONCLUSIVE"
    with pytest.raises(TaskControlError):
        submit_s3_handoff(
            db, identity, task_id=str(task["task_id"]), operation_id="hf01-revoked-submit",
            diagnosis_receipt_id=str(diagnosis["receipt_id"]),
            diagnosis_digest=str(diagnosis["digest"]), expected_control_revision=revision,
        )
    with connect(db) as connection:
        for table in ("s3_handoff_queue_entries", "s3_handoff_receipts"):
            assert connection.execute(f"SELECT COUNT(*) FROM {table} WHERE task_id=?", (task["task_id"],)).fetchone()[0] == 0
        assert connection.execute(
            "SELECT COUNT(*) FROM domain_outbox WHERE task_id=? AND event_kind='S3_HANDOFF_ACCEPTED'",
            (task["task_id"],),
        ).fetchone()[0] == 0


@pytest.mark.parametrize("tool_name", ["get_order_status", "get_callback_delivery", "get_receiver_processing"])
def test_scope_revocation_denies_real_mcp_tool_call_and_web_resource_read(tmp_path: Path, tool_name: str):
    from fastapi.testclient import TestClient
    from mcp.server.mcpserver.exceptions import ToolError
    from opspilot.domain.database import reset_fixture
    # The MCP server calls the same Domain binding check as the HTTP/Domain read.
    from opspilot.domain.s3 import get_s3_binding, prepare_s3_fixture
    from opspilot.domain.s3_mcp import build_s3_server
    from opspilot.domain.database import connect
    from opspilot.web.app import create_app
    from test_m4_01_dialogue_updates import PASSWORDS, _login

    db = tmp_path / "hf01-revoked-http-mcp.sqlite3"
    reset_fixture(db, "S1_POS")
    prepare_s3_fixture(db, "DELIVERY_FAILED", order_id="async-order-2")
    from test_m4_03_s3 import _task
    _, task = _task(db, "async-order-2")
    with connect(db) as connection:
        binding = get_s3_binding(connection, str(task["task_id"]))
        connection.execute(
            "UPDATE principal_scope_grants SET granted_scopes_json='[]', grant_version=grant_version+1 "
            "WHERE tenant_id='tenant-a' AND principal_id=?", (binding["principal_id"],),
        )

    server = build_s3_server(db, str(task["task_id"]), "http://127.0.0.1:1")
    with pytest.raises(ToolError):
        asyncio.run(server.call_tool(tool_name, {"reason": "verify current authorization"}))

    app = create_app(db_path=db, start_worker=False, credentials=PASSWORDS, expected_origin="http://testserver")
    with TestClient(app, raise_server_exceptions=False) as client:
        headers = _login(client, "support-a")
        response = client.get("/api/s3/order-resources", headers=headers)
        assert response.status_code == 403
        assert "async-order-2" not in response.text
        task_view = client.get(f"/api/tasks/{task['task_id']}/s3-handoff", headers=headers)
        assert task_view.status_code == 403


@pytest.mark.parametrize("version_source", ["grant", "policy"])
def test_scope_restore_requires_new_evidence_versions(tmp_path: Path, version_source: str):
    from opspilot.domain.database import connect
    from opspilot.domain.s3 import evaluate_s3_gate

    db, identity, task = _prepared_task(tmp_path, "DELIVERY_FAILED", "async-order-2")
    _, evidence_ids = _diagnose(db, identity, task)
    with connect(db) as connection:
        principal = connection.execute("SELECT principal_id FROM task_bindings WHERE task_id=?", (task["task_id"],)).fetchone()[0]
        if version_source == "grant":
            connection.execute(
                "UPDATE principal_scope_grants SET grant_version=grant_version+1 "
                "WHERE tenant_id='tenant-a' AND principal_id=?", (principal,),
            )
        else:
            connection.execute(
                "UPDATE route_scope_policies SET scope_policy_version=scope_policy_version+1 "
                "WHERE tenant_id='tenant-a' AND service_id='orders-async-demo' AND route='/api/async-orders/async-order'"
            )
    stale = evaluate_s3_gate(db, str(task["task_id"]), evidence_ids)
    with connect(db) as connection:
        if version_source == "grant":
            connection.execute(
                "UPDATE principal_scope_grants SET granted_scopes_json='[\"orders.async.read\"]', grant_version=grant_version+1 "
                "WHERE tenant_id='tenant-a' AND principal_id=?", (principal,),
            )
        else:
            connection.execute(
                "UPDATE route_scope_policies SET required_scopes_json='[\"orders.async.read\"]', scope_policy_version=scope_policy_version+1 "
                "WHERE tenant_id='tenant-a' AND service_id='orders-async-demo' AND route='/api/async-orders/async-order'"
            )
    with connect(db) as connection:
        restored = evaluate_s3_gate(db, str(task["task_id"]), evidence_ids)
    assert stale["decision"] != "DIAGNOSED"
    assert restored["decision"] != "DIAGNOSED"


@pytest.mark.parametrize("mutation", ["disabled_principal", "credential_mismatch", "missing_policy", "missing_grant"])
def test_s3_binding_fails_closed_for_all_current_authorization_inputs(tmp_path: Path, mutation: str):
    from opspilot.domain.database import connect
    from opspilot.domain.d2 import ScopeDenied
    from opspilot.domain.s3 import get_s3_binding

    db, _, task = _prepared_task(tmp_path, "DELIVERY_FAILED", f"auth-{mutation}")
    with connect(db) as connection:
        binding = get_s3_binding(connection, str(task["task_id"]))
        if mutation == "disabled_principal":
            connection.execute(
                "UPDATE principals SET status='DISABLED',principal_version=principal_version+1 "
                "WHERE tenant_id='tenant-a' AND principal_id=?", (binding["principal_id"],),
            )
        elif mutation == "credential_mismatch":
            connection.execute(
                "UPDATE auth_policies SET accepted_credential_ref=CASE accepted_credential_ref "
                "WHEN 'cred-v1' THEN 'cred-v2' ELSE 'cred-v1' END,policy_version=policy_version+1 "
                "WHERE tenant_id='tenant-a' AND service_id=?", (binding["service_id"],),
            )
        elif mutation == "missing_policy":
            connection.execute(
                "DELETE FROM route_scope_policies WHERE tenant_id='tenant-a' AND service_id=? AND route=?",
                (binding["service_id"], binding["route"]),
            )
        else:
            connection.execute(
                "DELETE FROM principal_scope_grants WHERE tenant_id='tenant-a' AND principal_id=?",
                (binding["principal_id"],),
            )
        with pytest.raises(ScopeDenied):
            get_s3_binding(connection, str(task["task_id"]))


def test_historical_receipt_is_approver_read_only_after_scope_revocation(tmp_path: Path):
    from opspilot.domain.database import connect
    from opspilot.domain.s3_handoff import get_s3_handoff_outcome, submit_s3_handoff
    from opspilot.domain.task_control import trusted_identity

    db, identity, task = _prepared_task(
        tmp_path, "DELIVERY_FAILED", "async-order-2", attempt_count=3,
        max_attempts=3, retry_state="EXHAUSTED",
    )
    diagnosis, _ = _diagnose(db, identity, task)
    request = _handoff_request(db, task, diagnosis)
    accepted = submit_s3_handoff(db, identity, **request)
    _revoke_scope(db, task)

    approver = trusted_identity(db, "approver-a")
    history = get_s3_handoff_outcome(db, str(task["task_id"]), approver)
    assert history["business_outcome"] == "HANDOFF_ACCEPTED"
    assert history["currentness"] == "HISTORICALLY_ACCEPTED"
    assert history["handoff_receipt"]["receipt_id"] == accepted["receipt_id"]
    assert "diagnosis_receipt" not in history
    from opspilot.domain.d2 import ScopeDenied
    with pytest.raises(ScopeDenied):
        get_s3_handoff_outcome(db, str(task["task_id"]), identity)
    from opspilot.domain.task_control import TaskControlError
    with pytest.raises(TaskControlError):
        submit_s3_handoff(db, identity, **request)
    from fastapi.testclient import TestClient
    from opspilot.web.app import create_app
    from test_m4_01_dialogue_updates import PASSWORDS, _login
    app = create_app(db_path=db, start_worker=False, credentials=PASSWORDS, expected_origin="http://testserver")
    with TestClient(app, raise_server_exceptions=False) as client:
        approver_headers = _login(client, "approver-a")
        response = client.get(f"/api/tasks/{task['task_id']}/s3-handoff", headers=approver_headers)
        assert response.status_code == 200
        assert response.json()["business_outcome"] == "HANDOFF_ACCEPTED"
        assert "diagnosis_receipt" not in response.json()
        support_headers = _login(client, "support-a")
        denied = client.get(f"/api/tasks/{task['task_id']}/s3-handoff", headers=support_headers)
        assert denied.status_code == 403
    with connect(db) as connection:
        assert connection.execute("SELECT COUNT(*) FROM s3_handoff_queue_entries WHERE task_id=?", (task["task_id"],)).fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM s3_handoff_receipts WHERE task_id=?", (task["task_id"],)).fetchone()[0] == 1


def test_receiver_sla_invalidates_wait_diagnosis_before_evidence_ttl(tmp_path: Path, monkeypatch):
    from opspilot.domain.database import connect
    from opspilot.domain.s3 import evaluate_s3_gate, get_s3_outcome
    from opspilot.domain.s3_handoff import submit_s3_handoff
    from opspilot.domain.task_control import TaskControlError
    import opspilot.domain.s3 as s3

    db, identity, task = _prepared_task(
        tmp_path, "DELIVERED_PENDING", "async-order-2", queue_age_seconds=299,
        processing_sla_seconds=300,
    )
    clock = {"now": datetime.now(timezone.utc)}

    class FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            current = clock["now"]
            return current if tz is not None else current.replace(tzinfo=None)

    import opspilot.domain.d2 as d2
    monkeypatch.setattr(s3, "datetime", FrozenDateTime)
    monkeypatch.setattr(d2, "datetime", FrozenDateTime)
    accepted_at = (clock["now"] - timedelta(seconds=299)).isoformat().replace("+00:00", "Z")
    from opspilot.domain.d2 import canonical_json, digest_json
    with connect(db) as connection:
        receiver = connection.execute(
            "SELECT event_id FROM s3_receivers WHERE tenant_id='tenant-a' AND service_id='orders-async-demo' AND order_id='async-order-2'"
        ).fetchone()
        connection.execute(
            "UPDATE s3_receivers SET accepted_at=? WHERE tenant_id='tenant-a' AND service_id='orders-async-demo' AND order_id='async-order-2'",
            (accepted_at,),
        )
        delivery = connection.execute(
            "SELECT transport_response_json FROM s3_deliveries WHERE tenant_id='tenant-a' AND service_id='orders-async-demo' AND order_id='async-order-2'"
        ).fetchone()
        response = json.loads(str(delivery["transport_response_json"]))
        response["accepted_at"] = accepted_at
        response["event_id"] = str(receiver["event_id"])
        connection.execute(
            "UPDATE s3_deliveries SET transport_response_json=?,response_digest=? WHERE tenant_id='tenant-a' AND service_id='orders-async-demo' AND order_id='async-order-2'",
            (canonical_json(response), digest_json(response)),
        )
    diagnosis, evidence_ids = _diagnose(db, identity, task, state="DELIVERED_PENDING")
    assert diagnosis["outcome"] == "RECEIVER_PROCESSING_UNCONFIRMED"
    assert get_s3_outcome(db, str(task["task_id"]))["handling_direction"] == "WAIT_FOR_RECEIVER_PROCESSING"

    with connect(db) as connection:
        revision = int(connection.execute("SELECT control_revision FROM task_controls WHERE task_id=?", (task["task_id"],)).fetchone()[0])
    clock["now"] += timedelta(seconds=2)
    stale = get_s3_outcome(db, str(task["task_id"]))
    assert stale["currentness"] == "INVALIDATED_BY_CURRENT_FACTS"
    assert stale["handoff_allowed"] is False
    assert stale["gate"]["reason_code"] == "S3_SLA_EXPIRED"
    with connect(db) as connection:
        old_row = connection.execute(
            "SELECT body_json,digest FROM s3_diagnoses WHERE receipt_id=?", (diagnosis["receipt_id"],)
        ).fetchone()
        assert old_row["body_json"] == diagnosis["body_json"]
        assert old_row["digest"] == diagnosis["digest"]
        from opspilot.domain.chat import _current_task_state
        chat_state = _current_task_state(connection, str(task["task_id"]))
        assert chat_state["s3_outcome"]["currentness"] == "INVALIDATED_BY_CURRENT_FACTS"
        assert chat_state["s3_outcome"]["outcome"] == "INCONCLUSIVE"
        assert connection.execute(
            "SELECT COUNT(*) FROM s3_handoff_queue_entries WHERE task_id=?", (task["task_id"],)
        ).fetchone()[0] == 0
    from fastapi.testclient import TestClient
    from opspilot.web.app import create_app
    from test_m4_01_dialogue_updates import PASSWORDS, _login
    app = create_app(db_path=db, start_worker=False, credentials=PASSWORDS, expected_origin="http://testserver")
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get(
            f"/api/tasks/{task['task_id']}/s3-handoff", headers=_login(client, "support-a"),
        )
        assert response.status_code == 200
        assert response.json()["business_outcome"] == "INCONCLUSIVE"
        assert response.json()["handoff_allowed"] is False
    assert evaluate_s3_gate(db, str(task["task_id"]), evidence_ids)["handling_direction"] == "CONTACT_RECEIVER_OPERATOR"
    with pytest.raises(TaskControlError):
        submit_s3_handoff(
            db, identity, task_id=str(task["task_id"]), operation_id="hf01-expired-diagnosis",
            diagnosis_receipt_id=str(diagnosis["receipt_id"]),
            diagnosis_digest=str(diagnosis["digest"]), expected_control_revision=revision,
        )

    from opspilot.domain.task_control import admit_task_message, apply_pending_critical_inputs, claim_task_run, finish_task_run
    accepted = admit_task_message(
        db, identity, session_id=str(task["session_id"]), task_id=str(task["task_id"]),
        input_kind="CORRECT_TASK_INPUT", body="请按当前接收方 SLA 重新调查。",
        idempotency_key="hf01-sla-refresh", expected_control_revision=revision,
    )
    run_id = str(accepted["run_id"])
    claim_task_run(db, identity, run_id)
    apply_pending_critical_inputs(db, identity, run_id)
    order, delivery, receiver = _facts(db, task)
    fresh_ids = [
        _record_fresh(db, task, "get_order_status", order, run_id=run_id),
        _record_fresh(db, task, "get_callback_delivery", delivery, run_id=run_id),
        _record_fresh(db, task, "get_receiver_processing", receiver, run_id=run_id),
    ]
    refreshed = s3.persist_s3_diagnosis(db, str(task["task_id"]), run_id, fresh_ids)
    finish_task_run(db, identity, run_id, "SUCCEEDED")
    assert refreshed["outcome"] == "RECEIVER_PROCESSING_UNCONFIRMED"
    current = get_s3_outcome(db, str(task["task_id"]))
    assert current["currentness"] == "CURRENT"
    assert current["handling_direction"] == "CONTACT_RECEIVER_OPERATOR"
    assert current["handoff_allowed"] is True
    new_request = _handoff_request(db, task, refreshed)
    accepted_handoff = submit_s3_handoff(db, identity, **new_request)
    assert accepted_handoff["business_outcome"] == "HANDOFF_ACCEPTED"
    assert accepted_handoff["handling_direction"] == "CONTACT_RECEIVER_OPERATOR"


@pytest.mark.parametrize("mutation", ["correction", "abort", "scope_revoke"])
def test_handoff_and_authority_mutation_are_serialized(tmp_path: Path, mutation: str):
    from opspilot.domain.database import connect
    from opspilot.domain.s3_handoff import submit_s3_handoff
    from opspilot.domain.task_control import admit_task_message, abort_task, trusted_identity

    db, identity, task = _prepared_task(
        tmp_path, "DELIVERY_FAILED", f"race-{mutation}", attempt_count=3,
        max_attempts=3, retry_state="EXHAUSTED",
    )
    diagnosis, _ = _diagnose(db, identity, task)
    request = _handoff_request(db, task, diagnosis)

    def mutate():
        if mutation == "correction":
            return admit_task_message(
                db, identity, session_id=str(task["session_id"]), task_id=str(task["task_id"]),
                input_kind="CORRECT_TASK_INPUT", body="请重新核查当前回调问题。",
                idempotency_key="hf01-race-correction", expected_control_revision=int(request["expected_control_revision"]),
            )
        if mutation == "abort":
            return abort_task(
                db, identity, task_id=str(task["task_id"]), reason="HF-01 abort race",
                idempotency_key="hf01-race-abort",
            )
        with connect(db) as connection:
            connection.execute("BEGIN IMMEDIATE")
            principal = connection.execute("SELECT principal_id FROM task_bindings WHERE task_id=?", (task["task_id"],)).fetchone()[0]
            connection.execute(
                "UPDATE principal_scope_grants SET granted_scopes_json='[]',grant_version=grant_version+1 "
                "WHERE tenant_id='tenant-a' AND principal_id=?", (principal,),
            )
            return {"status": "REVOKED"}

    handoff_result, mutation_result = _race(
        lambda: submit_s3_handoff(db, identity, **request), mutate,
    )
    with connect(db) as connection:
        queues = int(connection.execute("SELECT COUNT(*) FROM s3_handoff_queue_entries WHERE task_id=?", (task["task_id"],)).fetchone()[0])
        receipts = int(connection.execute("SELECT COUNT(*) FROM s3_handoff_receipts WHERE task_id=?", (task["task_id"],)).fetchone()[0])
        accepted_events = int(connection.execute(
            "SELECT COUNT(*) FROM domain_outbox WHERE task_id=? AND event_kind='S3_HANDOFF_ACCEPTED'",
            (task["task_id"],),
        ).fetchone()[0])
    assert queues == receipts == accepted_events
    assert queues in {0, 1}
    if queues:
        assert handoff_result[0] == "ok"
        if mutation in {"correction", "abort"}:
            assert mutation_result[0] == "error" or mutation_result[1].get("status") == "REJECTED"
        else:
            assert mutation_result[0] == "ok"
    else:
        assert handoff_result[0] == "error"
        assert mutation_result[0] == "ok"


def test_s3_handoff_retries_with_distinct_operation_ids_create_one_receipt(tmp_path: Path):
    from opspilot.domain.database import connect
    from opspilot.domain.s3_handoff import submit_s3_handoff

    db, identity, task = _prepared_task(
        tmp_path, "DELIVERY_FAILED", "async-order-2", attempt_count=3,
        max_attempts=3, retry_state="EXHAUSTED",
    )
    diagnosis, _ = _diagnose(db, identity, task)
    request = _handoff_request(db, task, diagnosis)
    left, right = _race(
        lambda: submit_s3_handoff(db, identity, **request),
        lambda: submit_s3_handoff(db, identity, **{**request, "operation_id": request["operation_id"] + "-second"}),
    )
    assert left[0] == right[0] == "ok"
    assert left[1]["receipt_id"] == right[1]["receipt_id"]
    assert {left[1]["replayed"], right[1]["replayed"]} == {False, True}
    with connect(db) as connection:
        assert connection.execute("SELECT COUNT(*) FROM s3_handoff_queue_entries WHERE task_id=?", (task["task_id"],)).fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM s3_handoff_receipts WHERE task_id=?", (task["task_id"],)).fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM domain_outbox WHERE task_id=? AND event_kind='S3_HANDOFF_ACCEPTED'", (task["task_id"],)).fetchone()[0] == 1

