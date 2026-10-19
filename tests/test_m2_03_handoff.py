from __future__ import annotations

import importlib
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from opspilot.domain.d2 import (
    finish_attempt,
    get_scope_authz_facts_fact,
    probe_endpoint_fact,
    record_tool_observation,
    reserve_attempt,
)
from opspilot.domain.database import connect, reset_fixture
from opspilot.domain.s2_diagnosis import create_diagnosis_receipt, freeze_handoff_draft
from opspilot.domain.task_control import (
    apply_pending_critical_inputs,
    claim_task_run,
    create_session,
    create_task_with_initial_run,
    finish_task_run,
    trusted_identity,
)


PASSWORDS = {
    "support-a": "support-test-password",
    "approver-a": "approver-test-password",
    "support-b": "support-b-test-password",
    "approver-b": "approver-b-test-password",
}
ORIGIN = "http://testserver"


def _install_scope_write_audit(db: Path) -> None:
    with connect(db) as connection:
        connection.execute("CREATE TABLE m203_scope_write_audit (table_name TEXT, operation TEXT)")
        for table in ("principal_scope_grants", "route_scope_policies"):
            for operation, suffix in (("INSERT", "ins"), ("UPDATE", "upd"), ("DELETE", "del")):
                connection.execute(
                    f"CREATE TRIGGER m203_audit_{table}_{suffix} AFTER {operation} ON {table} "
                    f"BEGIN INSERT INTO m203_scope_write_audit VALUES ('{table}', '{operation}'); END"
                )


def _make_ready_draft(db: Path, live_api: str, prefix: str) -> dict[str, object]:
    """Prepare a real same-Run 403 + authz diagnosis and frozen current draft."""
    reset_fixture(db, "S2_SCOPE_DENIED")
    identity = trusted_identity(db, "support-a")
    session_id = str(create_session(db, identity)["session_id"])
    created = create_task_with_initial_run(
        db,
        identity,
        session_id=session_id,
        service_id="orders-demo",
        integration_id="integration-a",
        ticket_id=f"{prefix}-001",
        initial_message="订单查询 API 返回 403，请核实当前授权事实。",
        idempotency_key=f"{prefix}-task",
    )
    task_id, run_id = str(created["task_id"]), str(created["run_id"])
    claim_task_run(db, identity, run_id)
    apply_pending_critical_inputs(db, identity, run_id)

    probe = probe_endpoint_fact(db, task_id, "orders-demo", "integration-a", live_api)
    assert probe["facts"]["http_status"] == 403
    probe_call = f"{prefix}-probe"
    probe_attempt, _ = reserve_attempt(
        db, task_id, "MCP", 6, call_id=probe_call, tool_call_id=f"{prefix}-probe-tool",
        tool_name="probe_endpoint", argument_digest=f"{prefix}-probe-args", run_id=run_id,
    )
    finish_attempt(db, probe_attempt, "OK")
    probe_observation = record_tool_observation(
        db, task_id=task_id, call_id=probe_call, attempt_id=probe_attempt,
        tool_call_id=f"{prefix}-probe-tool", tool_name="probe_endpoint",
        arguments={"service_id": "orders-demo", "integration_id": "integration-a"},
        status="OK", result=probe,
    )

    request_id = str(probe["facts"]["request_id"])
    authz = get_scope_authz_facts_fact(db, task_id, request_id)
    authz_call = f"{prefix}-authz"
    authz_attempt, _ = reserve_attempt(
        db, task_id, "MCP", 6, call_id=authz_call, tool_call_id=f"{prefix}-authz-tool",
        tool_name="get_scope_authz_facts", argument_digest=f"{prefix}-authz-args", run_id=run_id,
    )
    finish_attempt(db, authz_attempt, "OK")
    authz_observation = record_tool_observation(
        db, task_id=task_id, call_id=authz_call, attempt_id=authz_attempt,
        tool_call_id=f"{prefix}-authz-tool", tool_name="get_scope_authz_facts",
        arguments={"request_id": request_id}, status="OK", result=authz,
    )

    receipt = create_diagnosis_receipt(
        db,
        task_id=task_id,
        run_id=run_id,
        evidence_ids=[str(probe_observation["evidence_id"]), str(authz_observation["evidence_id"])],
    )
    draft = freeze_handoff_draft(db, task_id=task_id, receipt_id=str(receipt["receipt_id"]))
    finish_task_run(db, identity, run_id, "SUCCEEDED")
    _install_scope_write_audit(db)
    with connect(db) as connection:
        control_revision = int(connection.execute(
            "SELECT control_revision FROM task_controls WHERE task_id = ?", (task_id,),
        ).fetchone()[0])
    return {
        "identity": identity,
        "session_id": session_id,
        "task_id": task_id,
        "run_id": run_id,
        "receipt": receipt,
        "draft": draft,
        "control_revision": control_revision,
    }


def _domain_module():
    return importlib.import_module("opspilot.domain.s2_handoff")


def _submit(db: Path, ready: dict[str, object], operation_id: str, **overrides: object) -> dict[str, object]:
    module = _domain_module()
    draft = ready["draft"]
    assert isinstance(draft, dict)
    request = {
        "operation_id": operation_id,
        "draft_id": draft["draft_id"],
        "draft_digest": draft["content_digest"],
        "expected_control_revision": ready["control_revision"],
        "handoff_kind": "SCOPE_REVIEW",
    }
    request.update(overrides)
    return module.submit_s2_handoff(
        db,
        ready["identity"],
        task_id=str(ready["task_id"]),
        **request,
    )


def _counts(db: Path, task_id: str) -> dict[str, int]:
    with connect(db) as connection:
        tables = {str(row["name"]) for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'",
        ).fetchall()}
        result = {"queue": 0, "receipts": 0, "submit_outbox": 0, "scope_writes": 0}
        if "s2_handoff_queue_entries" in tables:
            result["queue"] = int(connection.execute(
                "SELECT COUNT(*) FROM s2_handoff_queue_entries WHERE task_id = ?", (task_id,),
            ).fetchone()[0])
        if "s2_handoff_receipts" in tables:
            result["receipts"] = int(connection.execute(
                "SELECT COUNT(*) FROM s2_handoff_receipts WHERE task_id = ?", (task_id,),
            ).fetchone()[0])
        result["submit_outbox"] = int(connection.execute(
            "SELECT COUNT(*) FROM domain_outbox WHERE task_id = ? AND event_kind = 'S2_HANDOFF_ACCEPTED'",
            (task_id,),
        ).fetchone()[0])
        # These test-only triggers count attempted writes, not just final values.
        if "m203_scope_write_audit" in tables:
            result["scope_writes"] = int(connection.execute(
                "SELECT COUNT(*) FROM m203_scope_write_audit",
            ).fetchone()[0])
        return result


def test_m203_03_explicit_domain_submit_commits_one_queue_receipt_outbox_and_never_grants_scope(
    demo_db: Path, live_api: str,
) -> None:
    ready = _make_ready_draft(demo_db, live_api, "m203-03")
    result = _submit(demo_db, ready, "m203-operation-03")

    assert result["status"] == "ACCEPTED"
    assert result["business_outcome"] == "SCOPE_ESCALATED"
    assert result["scope_authorized"] is False and result["recovered"] is False
    assert result["handoff_status"] == "PENDING_REVIEW"
    assert _counts(demo_db, str(ready["task_id"])) == {
        "queue": 1, "receipts": 1, "submit_outbox": 1, "scope_writes": 1,
    }


def test_m203_04_lost_response_replay_returns_same_immutable_receipt(
    demo_db: Path, live_api: str,
) -> None:
    ready = _make_ready_draft(demo_db, live_api, "m203-04")
    first = _submit(demo_db, ready, "m203-operation-04")
    replay = _submit(demo_db, ready, "m203-operation-04")

    assert first["receipt_id"] == replay["receipt_id"]
    assert replay["replayed"] is True
    assert _counts(demo_db, str(ready["task_id"]))["queue"] == 1
    assert _counts(demo_db, str(ready["task_id"]))["receipts"] == 1
    assert _counts(demo_db, str(ready["task_id"]))["submit_outbox"] == 1


def test_m203_05_same_operation_with_changed_payload_is_rejected_without_side_effects(
    demo_db: Path, live_api: str,
) -> None:
    ready = _make_ready_draft(demo_db, live_api, "m203-05")
    _submit(demo_db, ready, "m203-operation-05")
    module = _domain_module()
    draft = ready["draft"]
    assert isinstance(draft, dict)
    with pytest.raises(Exception) as error:
        module.submit_s2_handoff(
            demo_db,
            ready["identity"],
            task_id=str(ready["task_id"]),
            operation_id="m203-operation-05",
            draft_id=str(draft["draft_id"]),
            draft_digest="0" * 64,
            expected_control_revision=int(ready["control_revision"]),
            handoff_kind="SCOPE_REVIEW",
        )
    assert getattr(error.value, "code", None) == "IDEMPOTENCY_CONFLICT"
    assert _counts(demo_db, str(ready["task_id"]))["queue"] == 1
    assert _counts(demo_db, str(ready["task_id"]))["receipts"] == 1
    assert _counts(demo_db, str(ready["task_id"]))["submit_outbox"] == 1


def test_m203_07_current_policy_change_invalidates_frozen_draft_before_handoff(
    demo_db: Path, live_api: str,
) -> None:
    ready = _make_ready_draft(demo_db, live_api, "m203-07")
    with connect(demo_db) as connection:
        connection.execute(
            "UPDATE route_scope_policies SET scope_policy_version = scope_policy_version + 1 "
            "WHERE tenant_id = 'tenant-a' AND service_id = 'orders-demo' AND route = '/api/orders/demo-order'",
        )

    with pytest.raises(Exception) as error:
        _submit(demo_db, ready, "m203-operation-07")
    assert getattr(error.value, "code", None) == "DRAFT_STALE"
    counts = _counts(demo_db, str(ready["task_id"]))
    assert counts["queue"] == counts["receipts"] == counts["submit_outbox"] == 0


def test_m203_09_real_web_route_requires_owner_and_exposes_submit_operation(
    demo_db: Path, live_api: str,
) -> None:
    ready = _make_ready_draft(demo_db, live_api, "m203-09")
    module = importlib.import_module("opspilot.web.app")
    app = module.create_app(
        db_path=demo_db,
        start_worker=False,
        credentials=PASSWORDS,
        expected_origin=ORIGIN,
    )
    with TestClient(app, raise_server_exceptions=False) as client:
        login = client.post(
            "/api/auth/login",
            headers={"Origin": ORIGIN},
            json={"actor_id": "support-a", "password": PASSWORDS["support-a"]},
        )
        assert login.status_code == 200
        headers = {
            "Origin": ORIGIN,
            "X-CSRF-Token": login.json()["csrf_token"],
            "Idempotency-Key": "m203-operation-web-09",
        }
        task_id = str(ready["task_id"])
        handoff = client.get(f"/api/tasks/{task_id}/handoff")
        assert handoff.status_code == 200, handoff.text
        draft = ready["draft"]
        assert isinstance(draft, dict)
        response = client.post(
            f"/api/tasks/{task_id}/handoff/submit",
            headers=headers,
            json={
                "operation_id": "m203-operation-web-09",
                "draft_id": draft["draft_id"],
                "draft_digest": draft["content_digest"],
                "expected_control_revision": ready["control_revision"],
                "handoff_kind": "SCOPE_REVIEW",
            },
        )
        assert response.status_code == 202, response.text
        assert response.json()["business_outcome"] == "SCOPE_ESCALATED"
