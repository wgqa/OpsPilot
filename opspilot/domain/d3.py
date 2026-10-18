from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Literal

from opspilot.domain.d2 import (
    canonical_json,
    digest_json,
    evaluate_evidence_gate,
    get_task_binding,
    list_evidence,
    utc_now,
)
from opspilot.domain.database import connect, get_service_info
from opspilot.domain.events import write_outbox_event
from opspilot.domain.client import BUSINESS_ROUTE, probe_orders
from opspilot.domain.task_control import (
    TaskControlError,
    assert_plan_control_in_transaction,
    assert_task_control_in_transaction,
)


ActionKind = Literal["REPAIR", "DELIVER"]
_D4_TEST_FAILPOINT: Callable[[str, sqlite3.Connection | None], None] | None = None


def _run_d4_test_failpoint(name: str, connection: sqlite3.Connection | None = None) -> None:
    """Private monkeypatch seam for subprocess tests; never exposed to Agent tools or CLI."""
    if _D4_TEST_FAILPOINT is not None:
        _D4_TEST_FAILPOINT(name, connection)
    elif (
        name == "repair_after_commit_before_response"
        and os.environ.get("OPSPILOT_ENABLE_M1_05_FAILPOINTS") == "1"
        and os.environ.get("OPSPILOT_M1_05_CRASH_AT") == name
    ):
        os._exit(87)


class D3Error(RuntimeError):
    pass


class D3ScopeDenied(D3Error):
    pass


class D3PreconditionRejected(D3Error):
    pass


class KeyReuseConflict(D3Error):
    pass


def _row(row: sqlite3.Row | None) -> dict[str, object] | None:
    return {key: row[key] for key in row.keys()} if row is not None else None


def _binding_for_thread(connection: sqlite3.Connection, thread_id: str) -> dict[str, object]:
    result = _row(connection.execute(
        "SELECT * FROM task_bindings WHERE thread_id = ?", (thread_id,)
    ).fetchone())
    if result is None:
        raise D3ScopeDenied("Task thread is not available.")
    return result


def _require_submitter(connection: sqlite3.Connection, task_id: str, actor_id: str) -> dict[str, object]:
    binding = _row(connection.execute(
        """SELECT b.* FROM task_bindings AS b
           JOIN trusted_operators AS o ON o.actor_id = b.actor_id AND o.tenant_id = b.tenant_id
           WHERE b.task_id = ? AND b.actor_id = ? AND o.role = 'SUPPORT'""",
        (task_id, actor_id),
    ).fetchone())
    if binding is None:
        raise D3ScopeDenied("Trusted submitter scope check failed.")
    return binding


def _require_approver(connection: sqlite3.Connection, actor_id: str, tenant_id: str) -> None:
    row = connection.execute(
        "SELECT 1 FROM trusted_operators WHERE actor_id = ? AND tenant_id = ? AND role = 'APPROVER'",
        (actor_id, tenant_id),
    ).fetchone()
    if row is None:
        raise D3ScopeDenied("Trusted approver scope check failed.")


def _require_executor(connection: sqlite3.Connection, executor_id: str, tenant_id: str) -> None:
    row = connection.execute(
        "SELECT 1 FROM executor_services WHERE executor_id = ? AND tenant_id = ? AND active = 1",
        (executor_id, tenant_id),
    ).fetchone()
    if row is None:
        raise D3ScopeDenied("Trusted executor service scope check failed.")


def _load_plan(connection: sqlite3.Connection, tenant_id: str, task_id: str, plan_hash: str) -> dict[str, object]:
    row = connection.execute(
        "SELECT * FROM d3_plans WHERE tenant_id = ? AND task_id = ? AND plan_hash = ?",
        (tenant_id, task_id, plan_hash),
    ).fetchone()
    if row is None:
        raise D3PreconditionRejected("PLAN_NOT_FOUND")
    canonical = str(row["canonical_plan_json"])
    stored_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    if stored_hash != str(row["plan_hash"]):
        raise D3PreconditionRejected("PLAN_HASH_MISMATCH")
    plan = json.loads(canonical)
    if plan.get("tenant_id") != tenant_id or plan.get("task_id") != task_id:
        raise D3PreconditionRejected("PLAN_BINDING_MISMATCH")
    plan["plan_hash"] = stored_hash
    return plan


def _authorization(connection: sqlite3.Connection, tenant_id: str, task_id: str, plan_hash: str) -> dict[str, object] | None:
    return _row(connection.execute(
        """SELECT * FROM d3_plan_authorizations
           WHERE tenant_id = ? AND task_id = ? AND plan_hash = ?""",
        (tenant_id, task_id, plan_hash),
    ).fetchone())


def _write_plan_history(
    connection: sqlite3.Connection,
    tenant_id: str,
    task_id: str,
    plan_hash: str,
    eligibility: str,
    generation: int,
    actor_id: str | None,
    reason: str,
) -> None:
    connection.execute(
        """INSERT INTO d3_plan_authorization_history
           (history_id, tenant_id, task_id, plan_hash, eligibility, generation,
            changed_by, change_reason, changed_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (f"plan-history-{uuid.uuid4()}", tenant_id, task_id, plan_hash,
         eligibility, generation, actor_id, reason, utc_now()),
    )


def _assert_control(
    connection: sqlite3.Connection,
    tenant_id: str,
    task_id: str,
    expected_revision: int | None = None,
    *,
    run_id: str | None = None,
    allow_completed: bool = False,
) -> sqlite3.Row:
    try:
        return assert_task_control_in_transaction(
            connection, tenant_id, task_id, expected_revision, run_id=run_id,
            allow_completed=allow_completed,
        )
    except TaskControlError as exc:
        raise D3PreconditionRejected(exc.code) from exc


def _assert_plan_control(
    connection: sqlite3.Connection,
    tenant_id: str,
    task_id: str,
    plan_hash: str,
    *,
    allow_completed: bool = False,
) -> sqlite3.Row:
    try:
        return assert_plan_control_in_transaction(
            connection, tenant_id, task_id, plan_hash, allow_completed=allow_completed
        )
    except TaskControlError as exc:
        raise D3PreconditionRejected(exc.code) from exc


def _activate_plan_in_transaction(
    connection: sqlite3.Connection,
    tenant_id: str,
    task_id: str,
    plan_hash: str,
    actor_id: str,
    reason: str,
) -> None:
    _require_submitter(connection, task_id, actor_id)
    plan = _load_plan(connection, tenant_id, task_id, plan_hash)
    _assert_plan_control(connection, tenant_id, task_id, plan_hash)
    ticket = connection.execute(
        "SELECT 1 FROM tickets WHERE tenant_id = ? AND ticket_id = ?",
        (tenant_id, plan["ticket_id"]),
    ).fetchone()
    if ticket is None:
        raise D3PreconditionRejected("TICKET_OUTSIDE_TASK_TENANT")
    active_rows = connection.execute(
        """SELECT plan_hash, generation FROM d3_plan_authorizations
           WHERE tenant_id = ? AND task_id = ? AND eligibility = 'ACTIVE'""",
        (tenant_id, task_id),
    ).fetchall()
    for active in active_rows:
        if str(active["plan_hash"]) == plan_hash:
            return
        generation = int(active["generation"]) + 1
        connection.execute(
            """UPDATE d3_plan_authorizations SET eligibility = 'SUPERSEDED', generation = ?,
                      changed_by = ?, change_reason = ?, changed_at = ?
               WHERE tenant_id = ? AND task_id = ? AND plan_hash = ? AND eligibility = 'ACTIVE'""",
            (generation, actor_id, "superseded_by_new_plan", utc_now(), tenant_id, task_id, active["plan_hash"]),
        )
        _write_plan_history(connection, tenant_id, task_id, str(active["plan_hash"]), "SUPERSEDED", generation, actor_id, "superseded_by_new_plan")
    prior = _authorization(connection, tenant_id, task_id, plan_hash)
    if prior is not None:
        if prior["eligibility"] != "ACTIVE":
            raise D3PreconditionRejected("PLAN_ALREADY_INACTIVE")
        return
    generation = int(connection.execute(
        "SELECT COALESCE(MAX(generation), 0) + 1 FROM d3_plan_authorizations WHERE tenant_id = ? AND task_id = ?",
        (tenant_id, task_id),
    ).fetchone()[0])
    now = utc_now()
    connection.execute(
        """INSERT INTO d3_plan_authorizations
           (plan_hash, tenant_id, task_id, eligibility, generation, changed_by,
            change_reason, active_from, changed_at)
           VALUES (?, ?, ?, 'ACTIVE', ?, ?, ?, ?, ?)""",
        (plan_hash, tenant_id, task_id, generation, actor_id, reason, now, now),
    )
    _write_plan_history(connection, tenant_id, task_id, plan_hash, "ACTIVE", generation, actor_id, reason)
    connection.execute("UPDATE task_bindings SET status = 'WAITING_APPROVAL' WHERE task_id = ?", (task_id,))
    write_outbox_event(
        connection, tenant_id=tenant_id, task_id=task_id, source_kind="PLAN",
        source_id=plan_hash, event_kind="PLAN_ACTIVATED",
        payload={"task_id": task_id, "plan_hash": plan_hash, "status": "WAITING_APPROVAL"},
    )


def create_plan_from_gate(
    path: str | Path,
    task_id: str,
    actor_id: str,
    gate_decision: dict[str, object],
    *,
    run_id: str | None = None,
) -> dict[str, object]:
    """Persist and activate the unique immutable Plan derived from a fresh READY gate."""
    if gate_decision.get("decision") != "READY":
        raise D3PreconditionRejected("NON_READY_CANNOT_CREATE_EXECUTABLE_PLAN")
    evidence_ids = [str(value) for value in gate_decision.get("checked_fact_ids", [])]
    recomputed = evaluate_evidence_gate(path, task_id, evidence_ids)
    if recomputed.get("decision") != "READY" or recomputed.get("plan_candidate") != gate_decision.get("plan_candidate"):
        raise D3PreconditionRejected("GATE_DECISION_STALE_OR_MISMATCHED")
    binding = get_task_binding(path, task_id)
    if binding["actor_id"] != actor_id:
        raise D3ScopeDenied("Only the trusted task submitter can create a Plan.")
    evidence = list_evidence(path, task_id, evidence_ids)
    by_type: dict[str, dict[str, object]] = {}
    for item in evidence:
        fact_type = str(item["fact_type"])
        if fact_type not in by_type or str(item["fetched_at"]) > str(by_type[fact_type]["fetched_at"]):
            by_type[fact_type] = item
    required = {"integration_config", "principal_status", "auth_policy", "endpoint_probe"}
    if not required.issubset(by_type):
        raise D3PreconditionRejected("PLAN_SOURCE_EVIDENCE_INCOMPLETE")
    config = by_type["integration_config"]["facts"]
    principal = by_type["principal_status"]["facts"]
    policy = by_type["auth_policy"]["facts"]
    candidate = gate_decision["plan_candidate"]
    if not isinstance(candidate, dict):
        raise D3PreconditionRejected("PLAN_CANDIDATE_INVALID")
    if (
        candidate.get("action_type") != "SWITCH_CREDENTIAL_REF"
        or candidate.get("integration_id") != binding["integration_id"]
        or config.get("principal_id") != binding["principal_id"]
        or principal.get("status") != "ENABLED"
        or candidate.get("expected_config_version") != config.get("config_version")
        or candidate.get("expected_principal_version") != principal.get("principal_version")
        or candidate.get("expected_auth_policy_version") != policy.get("policy_version")
        or candidate.get("new_credential_ref") != policy.get("accepted_credential_ref")
    ):
        raise D3PreconditionRejected("PLAN_TARGET_OR_ACTION_NOT_ALLOWED")
    base_plan: dict[str, object] = {
        "schema_version": "opspilot-plan-v1",
        "tenant_id": binding["tenant_id"],
        "task_id": task_id,
        "environment": "local-demo",
        "service_id": binding["service_id"],
        "integration_id": binding["integration_id"],
        "principal_id": binding["principal_id"],
        "target_resource_id": binding["integration_id"],
        "repair_action_type": "SWITCH_CREDENTIAL_REF",
        "old_credential_ref": config.get("credential_ref"),
        "new_credential_ref": candidate.get("new_credential_ref"),
        "expected_config_version": candidate.get("expected_config_version"),
        "expected_principal_version": candidate.get("expected_principal_version"),
        "expected_auth_policy_version": candidate.get("expected_auth_policy_version"),
        "required_evidence_ids": evidence_ids,
        "verification_contract": {
            "contract_id": "same-caller-orders-demo-v1",
            "method": "GET",
            "route": BUSINESS_ROUTE,
            "expected_http_status": 200,
            "expected_order_id": "demo-order",
            "expected_order_status": "CONFIRMED",
        },
        "ticket_id": binding["ticket_id"],
        "allowed_delivery_fields": ["resolution_entry"],
        "repair_action_definition": {"kind": "REPAIR", "action": "SWITCH_CREDENTIAL_REF"},
        "delivery_action_definition": {"kind": "DELIVER", "action": "APPEND_RESOLUTION_ENTRY"},
        "report_derivation_contract": "repair_ledger+online_verification+same_task_evidence-v1",
        "gate_reason_code": recomputed["reason_code"],
    }
    with connect(path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        _require_submitter(connection, task_id, actor_id)
        if run_id is None:
            control = _assert_control(connection, str(binding["tenant_id"]), task_id, 0)
            expected_revision = int(control["control_revision"])
            consumed_message_seq = int(control["applied_critical_message_seq"])
        else:
            run = connection.execute(
                """SELECT expected_control_revision, consumed_message_seq FROM task_runs
                   WHERE run_id = ? AND tenant_id = ? AND task_id = ?""",
                (run_id, binding["tenant_id"], task_id),
            ).fetchone()
            if run is None:
                raise D3PreconditionRejected("TASK_RUN_NOT_FOUND")
            expected_revision = int(run["expected_control_revision"])
            consumed_message_seq = int(run["consumed_message_seq"])
            _assert_control(connection, str(binding["tenant_id"]), task_id, expected_revision, run_id=run_id)
        base_signature = digest_json(base_plan)
        # Keep the v1.0 plan body/hash byte-for-byte compatible. New control epochs
        # qualify only the lookup signature in this separate authorization layer.
        signature = base_signature if expected_revision == 0 and consumed_message_seq == 0 else digest_json({
            "canonical_plan_signature": base_signature,
            "bound_control_revision": expected_revision,
            "consumed_message_seq": consumed_message_seq,
        })
        existing = connection.execute(
            """SELECT plan_id, plan_hash, canonical_plan_json FROM d3_plans
               WHERE tenant_id = ? AND task_id = ? AND plan_signature = ?""",
            (binding["tenant_id"], task_id, signature),
        ).fetchone()
        if existing is not None:
            _activate_plan_in_transaction(connection, str(binding["tenant_id"]), task_id, str(existing["plan_hash"]), actor_id, "ready_gate_plan_reuse")
            stored = json.loads(str(existing["canonical_plan_json"]))
            stored["plan_hash"] = str(existing["plan_hash"])
            return stored
        version = int(connection.execute(
            "SELECT COALESCE(MAX(plan_version), 0) + 1 FROM d3_plans WHERE tenant_id = ? AND task_id = ?",
            (binding["tenant_id"], task_id),
        ).fetchone()[0])
        plan_name = f"{task_id}:{version}:{signature}"
        plan_id = f"plan-{uuid.uuid5(uuid.NAMESPACE_URL, plan_name)}"
        plan = {**base_plan, "plan_id": plan_id, "plan_version": version, "created_at": utc_now()}
        canonical = canonical_json(plan)
        plan_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        connection.execute(
            """INSERT INTO d3_plans
               (plan_id, tenant_id, task_id, plan_version, plan_hash, plan_signature,
                canonical_plan_json, created_by)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (plan_id, binding["tenant_id"], task_id, version, plan_hash, signature, canonical, actor_id),
        )
        connection.execute(
            """INSERT INTO d3_plan_control_bindings
               (tenant_id, task_id, plan_hash, bound_control_revision, consumed_message_seq,
                task_run_id, bound_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (binding["tenant_id"], task_id, plan_hash, expected_revision,
             consumed_message_seq, run_id, utc_now()),
        )
        _activate_plan_in_transaction(connection, str(binding["tenant_id"]), task_id, plan_hash, actor_id, "ready_gate_plan")
    plan["plan_hash"] = plan_hash
    return plan


def activate_plan(path: str | Path, task_id: str, plan_hash: str, actor_id: str) -> dict[str, object]:
    binding = get_task_binding(path, task_id)
    with connect(path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        _activate_plan_in_transaction(connection, str(binding["tenant_id"]), task_id, plan_hash, actor_id, "trusted_activation")
        plan = _load_plan(connection, str(binding["tenant_id"]), task_id, plan_hash)
    return plan


def cancel_plan(path: str | Path, task_id: str, plan_hash: str, actor_id: str, reason: str) -> dict[str, object]:
    binding = get_task_binding(path, task_id)
    if not reason.strip():
        raise ValueError("A cancellation reason is required.")
    with connect(path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        _require_submitter(connection, task_id, actor_id)
        current = _authorization(connection, str(binding["tenant_id"]), task_id, plan_hash)
        if current is None:
            raise D3PreconditionRejected("PLAN_NOT_FOUND")
        if current["eligibility"] == "ACTIVE":
            # Plan cancellation is an idempotent authorization-history operation.
            # It remains available after a completed delivery, while an ABORTED or
            # stale Task cannot reactivate anything because the active path below
            # still uses the control guard.
            _assert_plan_control(
                connection, str(binding["tenant_id"]), task_id, plan_hash,
                allow_completed=True,
            )
            generation = int(current["generation"]) + 1
            now = utc_now()
            connection.execute(
                """UPDATE d3_plan_authorizations SET eligibility = 'CANCELLED', generation = ?,
                          changed_by = ?, change_reason = ?, changed_at = ?
                   WHERE tenant_id = ? AND task_id = ? AND plan_hash = ? AND eligibility = 'ACTIVE'""",
                (generation, actor_id, reason.strip()[:500], now, binding["tenant_id"], task_id, plan_hash),
            )
            _write_plan_history(connection, str(binding["tenant_id"]), task_id, plan_hash, "CANCELLED", generation, actor_id, reason.strip()[:500])
            resumable_runs = connection.execute(
                """SELECT r.run_id, r.tenant_id, r.session_id FROM approval_resume_links l
                   JOIN task_runs r ON r.run_id = l.resume_run_id
                   WHERE l.tenant_id = ? AND l.task_id = ? AND l.plan_hash = ?
                     AND r.status IN ('QUEUED', 'RUNNING', 'INTERRUPTED_RECOVERABLE')""",
                (binding["tenant_id"], task_id, plan_hash),
            ).fetchall()
            now_for_runs = utc_now()
            for resume_run in resumable_runs:
                connection.execute(
                    """UPDATE task_runs SET status = 'BLOCKED', ended_at = ?,
                              blocked_reason = 'PLAN_CANCELLED' WHERE run_id = ?
                       AND status IN ('QUEUED', 'RUNNING', 'INTERRUPTED_RECOVERABLE')""",
                    (now_for_runs, resume_run["run_id"]),
                )
                write_outbox_event(
                    connection, tenant_id=str(resume_run["tenant_id"]), task_id=task_id,
                    session_id=str(resume_run["session_id"]), source_kind="RUN",
                    source_id=str(resume_run["run_id"]), event_kind="RUN_STATUS_BLOCKED",
                    payload={"run_id": str(resume_run["run_id"]), "run_status": "BLOCKED",
                             "reason_code": "PLAN_CANCELLED"},
                    created_at=now_for_runs,
                )
            committed = connection.execute(
                "SELECT 1 FROM d3_action_ledgers WHERE tenant_id = ? AND task_id = ? AND plan_hash = ? AND status = 'COMMITTED' LIMIT 1",
                (binding["tenant_id"], task_id, plan_hash),
            ).fetchone()
            if committed is None:
                connection.execute("UPDATE task_bindings SET status = 'CANCELLED' WHERE task_id = ?", (task_id,))
        current = _authorization(connection, str(binding["tenant_id"]), task_id, plan_hash)
    return current or {}


def authorize_workflow_resume(
    path: str | Path, thread_id: str, actor_id: str, *, run_id: str | None = None
) -> dict[str, object]:
    """Authorize submitter or task-tenant approver before checkpoint construction/read."""
    with connect(path) as connection:
        binding = _binding_for_thread(connection, thread_id)
        operator = connection.execute(
            "SELECT tenant_id, role FROM trusted_operators WHERE actor_id = ?", (actor_id,)
        ).fetchone()
        owner = connection.execute(
            "SELECT tenant_id, owner_id FROM thread_owners WHERE thread_id = ?", (thread_id,)
        ).fetchone()
        if operator is None or owner is None or operator["tenant_id"] != binding["tenant_id"]:
            raise D3ScopeDenied("Workflow resume actor is outside the task tenant.")
        if owner["tenant_id"] != binding["tenant_id"] or owner["owner_id"] != binding["actor_id"]:
            raise D3ScopeDenied("Workflow thread owner record is invalid.")
        control = connection.execute(
            "SELECT * FROM task_controls WHERE tenant_id = ? AND task_id = ?",
            (binding["tenant_id"], binding["task_id"]),
        ).fetchone()
        if control is None:
            raise D3PreconditionRejected("TASK_CONTROL_MIGRATION_REQUIRED")
        if str(control["terminal_state"]) != "ACTIVE":
            raise D3PreconditionRejected("TASK_ABORTED")
        if control["pending_critical_message_seq"] is not None:
            raise D3PreconditionRejected("TASK_INPUT_PENDING")
        if run_id is None:
            # This legacy Graph entry carries no durable Run token. It is therefore
            # valid only for the original revision-zero execution.
            if int(control["control_revision"]) != 0:
                raise D3PreconditionRejected("TASK_CONTROL_STALE")
        else:
            run = connection.execute(
                """SELECT r.*, s.owner_id FROM task_runs AS r JOIN sessions AS s
                   ON s.session_id = r.session_id AND s.tenant_id = r.tenant_id
                   WHERE r.run_id = ? AND r.tenant_id = ? AND r.task_id = ?""",
                (run_id, binding["tenant_id"], binding["task_id"]),
            ).fetchone()
            if run is None or str(run["owner_id"]) != str(binding["actor_id"]):
                raise D3ScopeDenied("Persisted Run is outside the trusted task owner scope.")
            if str(run["status"]) != "RUNNING":
                raise D3PreconditionRejected("TASK_RUN_NOT_ACTIVE")
            run_revision = run["expected_control_revision"]
            if run_revision is None or int(control["control_revision"]) != int(run_revision):
                raise D3PreconditionRejected("TASK_CONTROL_STALE")
            if int(run["consumed_message_seq"]) < int(control["applied_critical_message_seq"]):
                raise D3PreconditionRejected("TASK_CONTROL_STALE")
        if operator["role"] == "SUPPORT" and actor_id == binding["actor_id"]:
            return binding
        if operator["role"] == "APPROVER":
            allowed = connection.execute(
                """SELECT 1 FROM d3_plans AS p
                   JOIN d3_plan_authorizations AS a ON a.plan_hash = p.plan_hash
                   JOIN d3_approvals AS approval
                     ON approval.tenant_id = p.tenant_id AND approval.task_id = p.task_id
                    AND approval.plan_hash = p.plan_hash
                   JOIN task_bindings AS b ON b.tenant_id = p.tenant_id AND b.task_id = p.task_id
                   WHERE p.tenant_id = ? AND p.task_id = ? AND a.eligibility = 'ACTIVE'
                     AND approval.approver_id = ?
                     AND b.status IN ('APPROVED', 'COMPLETED')""",
                (binding["tenant_id"], binding["task_id"], actor_id),
            ).fetchone()
            if allowed is not None and binding["actor_id"] != actor_id:
                return binding
    raise D3ScopeDenied("Workflow resume actor is not authorized before checkpoint access.")


def submit_plan_approval(
    path: str | Path,
    thread_id: str,
    approver_id: str,
    plan_hash: str,
    decision: Literal["APPROVED", "REJECTED"],
) -> dict[str, object]:
    if decision not in {"APPROVED", "REJECTED"}:
        raise ValueError("Approval decision must be APPROVED or REJECTED.")
    with connect(path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        return _submit_plan_approval_in_transaction(
            connection, thread_id, approver_id, plan_hash, decision
        )


def _submit_plan_approval_in_transaction(
    connection: sqlite3.Connection,
    thread_id: str,
    approver_id: str,
    plan_hash: str,
    decision: Literal["APPROVED", "REJECTED"],
    *,
    resume_run_id: str | None = None,
) -> dict[str, object]:
    """Persist the original D3 approval contract in a caller-owned transaction."""
    if decision not in {"APPROVED", "REJECTED"}:
        raise ValueError("Approval decision must be APPROVED or REJECTED.")
    binding = _binding_for_thread(connection, thread_id)
    _require_approver(connection, approver_id, str(binding["tenant_id"]))
    if approver_id == binding["actor_id"]:
        raise D3ScopeDenied("The submitter cannot approve their own Plan.")
    plan = _load_plan(connection, str(binding["tenant_id"]), str(binding["task_id"]), plan_hash)
    auth = _authorization(connection, str(binding["tenant_id"]), str(binding["task_id"]), plan_hash)
    actions = ["REPAIR", "DELIVER"]
    approval_scope = {
        "plan_hash": plan_hash,
        "target_resource_id": plan["target_resource_id"],
        "environment": plan["environment"],
        "action_kinds": actions,
        "ticket_id": plan["ticket_id"],
        "plan_summary_digest": digest_json({
            key: plan[key] for key in ("repair_action_type", "old_credential_ref", "new_credential_ref", "expected_config_version", "expected_principal_version", "expected_auth_policy_version", "verification_contract", "ticket_id")
        }),
    }
    scope_json = canonical_json(approval_scope)
    existing = connection.execute(
        "SELECT * FROM d3_approvals WHERE tenant_id = ? AND task_id = ? AND plan_hash = ?",
        (binding["tenant_id"], binding["task_id"], plan_hash),
    ).fetchone()
    if existing is not None:
        if existing["approver_id"] != approver_id or existing["decision"] != decision or existing["approval_scope_json"] != scope_json:
            raise D3PreconditionRejected("APPROVAL_ALREADY_RECORDED_WITH_DIFFERENT_SCOPE")
        # Exact approval replay is a history read, never a new grant.
        return _row(existing) or {}
    _assert_plan_control(connection, str(binding["tenant_id"]), str(binding["task_id"]), plan_hash)
    if auth is None or auth["eligibility"] != "ACTIVE":
        raise D3PreconditionRejected("PLAN_NOT_ACTIVE")
    if binding["status"] != "WAITING_APPROVAL":
        raise D3PreconditionRejected("TASK_NOT_WAITING_FOR_APPROVAL")
    approval_id = f"approval-{uuid.uuid4()}"
    decided_at = utc_now()
    connection.execute(
        """INSERT INTO d3_approvals
           (approval_id, tenant_id, task_id, plan_hash, approver_id, approval_scope_json,
            approved_plan_digest, target_resource_id, environment, action_kinds_json, decision, decided_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (approval_id, binding["tenant_id"], binding["task_id"], plan_hash, approver_id,
         scope_json, plan_hash, plan["target_resource_id"], plan["environment"],
         canonical_json(actions), decision, decided_at),
    )
    if decision == "APPROVED":
        for kind in ("REPAIR", "DELIVER"):
            connection.execute(
                """INSERT INTO d3_action_permissions
                   (tenant_id, task_id, plan_hash, approval_id, action_kind, state, changed_at)
                   VALUES (?, ?, ?, ?, ?, 'AVAILABLE', ?)""",
                (binding["tenant_id"], binding["task_id"], plan_hash, approval_id, kind, decided_at),
            )
        connection.execute("UPDATE task_bindings SET status = 'APPROVED' WHERE task_id = ?", (binding["task_id"],))
    else:
        connection.execute("UPDATE task_bindings SET status = 'COMPLETED' WHERE task_id = ?", (binding["task_id"],))
    result = _row(connection.execute("SELECT * FROM d3_approvals WHERE approval_id = ?", (approval_id,)).fetchone()) or {}
    payload: dict[str, object] = {
        "task_id": str(binding["task_id"]), "plan_hash": plan_hash,
        "approval_id": approval_id, "decision": decision,
    }
    if resume_run_id is not None:
        payload["resume_run_id"] = resume_run_id
    write_outbox_event(
        connection, tenant_id=str(binding["tenant_id"]), task_id=str(binding["task_id"]),
        source_kind="APPROVAL", source_id=approval_id,
        event_kind="PLAN_APPROVED" if decision == "APPROVED" else "PLAN_REJECTED",
        payload=payload,
    )
    return result


def list_pending_plan_reviews(path: str | Path, actor_id: str, tenant_id: str) -> list[dict[str, object]]:
    """Return only active, current approval work for a trusted tenant approver."""
    with connect(path) as connection:
        _require_approver(connection, actor_id, tenant_id)
        rows = connection.execute(
            """SELECT p.task_id, p.plan_hash, p.plan_version, p.created_at,
                      b.service_id, b.integration_id, b.ticket_id,
                      c.control_revision, c.pending_critical_message_seq
               FROM d3_plans p
               JOIN task_bindings b ON b.task_id = p.task_id AND b.tenant_id = p.tenant_id
               JOIN task_controls c ON c.task_id = b.task_id AND c.tenant_id = b.tenant_id
               JOIN d3_plan_authorizations a ON a.tenant_id = p.tenant_id
                 AND a.task_id = p.task_id AND a.plan_hash = p.plan_hash
               JOIN d3_plan_control_bindings pc ON pc.tenant_id = p.tenant_id
                 AND pc.task_id = p.task_id AND pc.plan_hash = p.plan_hash
               JOIN task_runs r ON r.run_id = pc.task_run_id AND r.task_id = p.task_id
                 AND r.tenant_id = p.tenant_id
               WHERE p.tenant_id = ? AND b.status = 'WAITING_APPROVAL'
                 AND c.terminal_state = 'ACTIVE' AND c.pending_critical_message_seq IS NULL
                 AND c.control_revision = pc.bound_control_revision
                 AND c.applied_critical_message_seq <= pc.consumed_message_seq
                 AND a.eligibility = 'ACTIVE' AND r.status = 'WAITING_APPROVAL'
                 AND NOT EXISTS (SELECT 1 FROM d3_approvals ap WHERE ap.tenant_id = p.tenant_id
                   AND ap.task_id = p.task_id AND ap.plan_hash = p.plan_hash)
               ORDER BY p.created_at, p.task_id, p.plan_hash LIMIT 100""",
            (tenant_id,),
        ).fetchall()
    return [{key: row[key] for key in row.keys()} for row in rows]


def get_plan_review_for_approver(
    path: str | Path, actor_id: str, tenant_id: str, task_id: str, plan_hash: str
) -> dict[str, object]:
    """Return the minimum sanitized review snapshot; never expose chat or secrets."""
    with connect(path) as connection:
        _require_approver(connection, actor_id, tenant_id)
        binding = _row(connection.execute(
            "SELECT * FROM task_bindings WHERE tenant_id = ? AND task_id = ?",
            (tenant_id, task_id),
        ).fetchone())
        if binding is None:
            raise D3ScopeDenied("Task is outside the approver tenant.")
        control = _row(connection.execute(
            "SELECT * FROM task_controls WHERE tenant_id = ? AND task_id = ?",
            (tenant_id, task_id),
        ).fetchone())
        auth = _authorization(connection, tenant_id, task_id, plan_hash)
        plan = _load_plan(connection, tenant_id, task_id, plan_hash)
        plan_binding = connection.execute(
            "SELECT * FROM d3_plan_control_bindings WHERE tenant_id = ? AND task_id = ? AND plan_hash = ?",
            (tenant_id, task_id, plan_hash),
        ).fetchone()
        if (
            control is None or plan_binding is None or auth is None
            or auth["eligibility"] != "ACTIVE"
            or binding["status"] != "WAITING_APPROVAL"
            or control["terminal_state"] != "ACTIVE"
            or control["pending_critical_message_seq"] is not None
            or int(control["control_revision"]) != int(plan_binding["bound_control_revision"])
        ):
            raise D3PreconditionRejected("PLAN_NOT_CURRENTLY_REVIEWABLE")
        versions = connection.execute(
            """SELECT i.config_version, i.credential_ref, i.principal_id,
                      p.principal_version, p.status AS principal_status,
                      a.policy_version, a.accepted_credential_ref
               FROM integrations i JOIN principals p ON p.tenant_id = i.tenant_id
                 AND p.principal_id = i.principal_id
               JOIN services s ON s.tenant_id = i.tenant_id AND s.integration_id = i.integration_id
               JOIN auth_policies a ON a.tenant_id = s.tenant_id AND a.service_id = s.service_id
               WHERE i.tenant_id = ? AND i.integration_id = ? AND s.service_id = ?""",
            (tenant_id, plan["integration_id"], plan["service_id"]),
        ).fetchone()
        version_compatible = bool(
            versions is not None
            and str(versions["principal_id"]) == str(plan["principal_id"])
            and str(versions["principal_status"]) == "ENABLED"
            and int(versions["config_version"]) == int(plan["expected_config_version"])
            and int(versions["principal_version"]) == int(plan["expected_principal_version"])
            and int(versions["policy_version"]) == int(plan["expected_auth_policy_version"])
            and str(versions["credential_ref"]) == str(plan["old_credential_ref"])
            and str(versions["accepted_credential_ref"]) == str(plan["new_credential_ref"])
        )
        if versions is None:
            compatibility_reason = "APPROVAL_TARGET_NOT_FOUND"
        elif str(versions["principal_id"]) != str(plan["principal_id"]):
            compatibility_reason = "PRINCIPAL_BINDING_CHANGED"
        elif str(versions["principal_status"]) != "ENABLED":
            compatibility_reason = "PRINCIPAL_NOT_ENABLED_OR_MISMATCHED"
        elif (
            int(versions["config_version"]) != int(plan["expected_config_version"])
            or int(versions["principal_version"]) != int(plan["expected_principal_version"])
            or int(versions["policy_version"]) != int(plan["expected_auth_policy_version"])
            or str(versions["credential_ref"]) != str(plan["old_credential_ref"])
            or str(versions["accepted_credential_ref"]) != str(plan["new_credential_ref"])
        ):
            compatibility_reason = "RESOURCE_VERSION_OR_CREDENTIAL_PRECONDITION_FAILED"
        else:
            compatibility_reason = None
        evidence: list[dict[str, object]] = []
        evidence_ids = [str(value) for value in plan.get("required_evidence_ids", [])]
        if evidence_ids:
            placeholders = ",".join("?" for _ in evidence_ids)
            evidence_rows = connection.execute(
                f"""SELECT evidence_id, fact_type, fetched_at, observed_versions_json, facts_json
                    FROM d2_evidence WHERE tenant_id = ? AND task_id = ?
                    AND evidence_id IN ({placeholders}) ORDER BY fetched_at, evidence_id""",
                (tenant_id, task_id, *evidence_ids),
            ).fetchall()
            safe_fact_keys = {
                "service_id", "integration_id", "principal_id", "config_version",
                "credential_ref", "status", "principal_version", "policy_version",
                "accepted_credential_ref", "route", "response_status", "http_status",
                "order_id", "order_status", "result_code",
            }
            for row in evidence_rows:
                facts = json.loads(str(row["facts_json"]))
                versions_json = json.loads(str(row["observed_versions_json"]))
                evidence.append({
                    "evidence_id": str(row["evidence_id"]),
                    "fact_type": str(row["fact_type"]),
                    "fetched_at": str(row["fetched_at"]),
                    "observed_versions": versions_json,
                    "facts": {key: value for key, value in facts.items() if key in safe_fact_keys},
                })
        plan_fields = (
            "plan_id", "plan_version", "plan_hash", "service_id", "integration_id",
            "principal_id", "target_resource_id", "environment", "repair_action_type",
            "old_credential_ref", "new_credential_ref", "expected_config_version",
            "expected_principal_version", "expected_auth_policy_version", "ticket_id",
            "verification_contract", "required_evidence_ids", "allowed_delivery_fields",
        )
        plan_view = {key: plan[key] for key in plan_fields if key in plan}
        return {
            "task_id": task_id,
            "plan_hash": plan_hash,
            "plan": plan_view,
            "current_state": {
                "task_status": str(binding["status"]),
                "terminal_state": str(control["terminal_state"]),
                "control_revision": int(control["control_revision"]),
                "pending_critical_message_seq": control["pending_critical_message_seq"],
                "plan_eligibility": str(auth["eligibility"]),
                "current_versions": ({
                    "config_version": int(versions["config_version"]),
                    "principal_version": int(versions["principal_version"]),
                    "auth_policy_version": int(versions["policy_version"]),
                    "credential_ref": str(versions["credential_ref"]),
                    "accepted_credential_ref": str(versions["accepted_credential_ref"]),
                    "principal_status": str(versions["principal_status"]),
                } if versions is not None else None),
                "version_compatible": version_compatible,
                "version_block_reason": compatibility_reason,
            },
            "evidence": evidence,
            "scope": {
                "actions": ["REPAIR", "DELIVER"],
                "executor": "trusted service configuration",
                "secrets_exposed": False,
            },
        }


def _approval_for(connection: sqlite3.Connection, tenant_id: str, task_id: str, plan_hash: str) -> dict[str, object]:
    result = _row(connection.execute(
        "SELECT * FROM d3_approvals WHERE tenant_id = ? AND task_id = ? AND plan_hash = ?",
        (tenant_id, task_id, plan_hash),
    ).fetchone())
    if result is None:
        raise D3PreconditionRejected("APPROVAL_NOT_FOUND")
    return result


def _require_plan_reader(
    connection: sqlite3.Connection,
    binding: dict[str, object],
    plan_hash: str,
    actor_id: str,
) -> None:
    operator = connection.execute(
        "SELECT tenant_id, role FROM trusted_operators WHERE actor_id = ?", (actor_id,)
    ).fetchone()
    if operator is not None and operator["tenant_id"] == binding["tenant_id"]:
        if operator["role"] == "SUPPORT" and actor_id == binding["actor_id"]:
            return
        if operator["role"] == "APPROVER":
            approval = connection.execute(
                """SELECT 1 FROM d3_approvals WHERE tenant_id = ? AND task_id = ?
                   AND plan_hash = ? AND approver_id = ?""",
                (binding["tenant_id"], binding["task_id"], plan_hash, actor_id),
            ).fetchone()
            if approval is not None:
                return
    executor = connection.execute(
        "SELECT tenant_id FROM executor_services WHERE executor_id = ? AND active = 1", (actor_id,)
    ).fetchone()
    if executor is not None and executor["tenant_id"] == binding["tenant_id"]:
        return
    raise D3ScopeDenied("Plan read scope check failed.")


def get_plan_for_task(path: str | Path, task_id: str, plan_hash: str, actor_id: str) -> dict[str, object]:
    with connect(path) as connection:
        binding = _row(connection.execute(
            "SELECT * FROM task_bindings WHERE task_id = ?", (task_id,)
        ).fetchone())
        if binding is None:
            raise D3ScopeDenied("Task is not available for this Plan read.")
        _require_plan_reader(connection, binding, plan_hash, actor_id)
        return _load_plan(connection, str(binding["tenant_id"]), task_id, plan_hash)


def get_plan_approval(path: str | Path, thread_id: str, plan_hash: str, actor_id: str) -> dict[str, object] | None:
    """Read the persisted approval bound to this task thread and immutable Plan."""
    with connect(path) as connection:
        binding = _binding_for_thread(connection, thread_id)
        _require_plan_reader(connection, binding, plan_hash, actor_id)
        return _row(connection.execute(
            """SELECT * FROM d3_approvals WHERE tenant_id = ? AND task_id = ? AND plan_hash = ?""",
            (binding["tenant_id"], binding["task_id"], plan_hash),
        ).fetchone())


def _request_for_action(
    connection: sqlite3.Connection,
    binding: dict[str, object],
    plan_hash: str,
    action_kind: ActionKind,
) -> tuple[dict[str, object], dict[str, object], dict[str, object]]:
    tenant_id = str(binding["tenant_id"])
    task_id = str(binding["task_id"])
    plan = _load_plan(connection, tenant_id, task_id, plan_hash)
    approval = _approval_for(connection, tenant_id, task_id, plan_hash)
    if approval["decision"] != "APPROVED" or approval["approved_plan_digest"] != plan_hash:
        raise D3PreconditionRejected("APPROVAL_DOES_NOT_BIND_PLAN")
    scope = json.loads(str(approval["approval_scope_json"]))
    expected_scope = {
        "plan_hash": plan_hash,
        "target_resource_id": plan["target_resource_id"],
        "environment": plan["environment"],
        "action_kinds": ["REPAIR", "DELIVER"],
        "ticket_id": plan["ticket_id"],
        "plan_summary_digest": digest_json({
            key: plan[key] for key in ("repair_action_type", "old_credential_ref", "new_credential_ref", "expected_config_version", "expected_principal_version", "expected_auth_policy_version", "verification_contract", "ticket_id")
        }),
    }
    if scope != expected_scope or approval["target_resource_id"] != plan["target_resource_id"] or approval["environment"] != plan["environment"]:
        raise D3PreconditionRejected("APPROVAL_SCOPE_MISMATCH")
    if action_kind == "REPAIR":
        specific = {
            "operation": "SWITCH_CREDENTIAL_REF",
            "integration_id": plan["integration_id"],
            "old_credential_ref": plan["old_credential_ref"],
            "new_credential_ref": plan["new_credential_ref"],
        }
    else:
        report = connection.execute(
            """SELECT * FROM d3_report_artifacts
               WHERE tenant_id = ? AND task_id = ? AND plan_hash = ?""",
            (tenant_id, task_id, plan_hash),
        ).fetchone()
        if report is None:
            raise D3PreconditionRejected("FROZEN_REPORT_NOT_FOUND")
        receipt = connection.execute(
            """SELECT * FROM d3_verification_receipts
               WHERE tenant_id = ? AND task_id = ? AND plan_hash = ? AND recovery_verified = 1""",
            (tenant_id, task_id, plan_hash),
        ).fetchone()
        if receipt is None:
            raise D3PreconditionRejected("RECOVERED_VERIFICATION_NOT_FOUND")
        specific = {
            "operation": "APPEND_RESOLUTION_ENTRY",
            "ticket_id": plan["ticket_id"],
            "allowed_fields": plan["allowed_delivery_fields"],
            "report_ref": report["report_ref"],
            "report_version": int(report["report_version"]),
            "content_digest": report["content_digest"],
            "verification_id": receipt["verification_id"],
        }
    request = {
        "tenant_id": tenant_id,
        "task_id": task_id,
        "plan_hash": plan_hash,
        "action_kind": action_kind,
        "approval_id": approval["approval_id"],
        "target_resource_id": plan["target_resource_id"],
        "environment": plan["environment"],
        "expected_versions": {
            "config_version": plan["expected_config_version"],
            "principal_version": plan["expected_principal_version"],
            "auth_policy_version": plan["expected_auth_policy_version"],
        },
        "action_parameters": specific,
    }
    return request, plan, approval


def get_or_create_action_intent(
    path: str | Path,
    task_id: str,
    plan_hash: str,
    action_kind: ActionKind,
    executor_id: str,
) -> dict[str, object]:
    if action_kind not in {"REPAIR", "DELIVER"}:
        raise ValueError("Only REPAIR and DELIVER intents are supported.")
    binding = get_task_binding(path, task_id)
    with connect(path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        _require_executor(connection, executor_id, str(binding["tenant_id"]))
        request, _, approval = _request_for_action(connection, binding, plan_hash, action_kind)
        request_json = canonical_json(request)
        request_digest = hashlib.sha256(request_json.encode("utf-8")).hexdigest()
        existing = connection.execute(
            """SELECT * FROM d3_action_intents
               WHERE tenant_id = ? AND task_id = ? AND plan_hash = ? AND action_kind = ?""",
            (binding["tenant_id"], task_id, plan_hash, action_kind),
        ).fetchone()
        if existing is not None:
            if existing["request_digest"] != request_digest or existing["canonical_request_json"] != request_json:
                raise KeyReuseConflict("KEY_REUSE_CONFLICT")
            return _row(existing) or {}
        authorization = _authorization(connection, str(binding["tenant_id"]), task_id, plan_hash)
        if authorization is None or authorization["eligibility"] != "ACTIVE":
            raise D3PreconditionRejected("PLAN_NOT_ACTIVE")
        _assert_plan_control(connection, str(binding["tenant_id"]), task_id, plan_hash)
        permission = connection.execute(
            """SELECT state, approval_id FROM d3_action_permissions
               WHERE tenant_id = ? AND task_id = ? AND plan_hash = ? AND action_kind = ?""",
            (binding["tenant_id"], task_id, plan_hash, action_kind),
        ).fetchone()
        if permission is None or permission["state"] != "AVAILABLE" or permission["approval_id"] != approval["approval_id"]:
            raise D3PreconditionRejected(f"{action_kind}_PERMISSION_NOT_AVAILABLE")
        action_id = f"action-{uuid.uuid4()}"
        idempotency_key = f"idem-{uuid.uuid4()}"
        created_at = utc_now()
        connection.execute(
            """INSERT INTO d3_action_intents
               (action_id, tenant_id, task_id, plan_hash, action_kind, idempotency_key,
                approval_id, canonical_request_json, request_digest, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (action_id, binding["tenant_id"], task_id, plan_hash, action_kind, idempotency_key,
             approval["approval_id"], request_json, request_digest, created_at),
        )
        result = _row(connection.execute("SELECT * FROM d3_action_intents WHERE action_id = ?", (action_id,)).fetchone())
    return result or {}


def get_action_intent(path: str | Path, action_id: str, executor_id: str) -> dict[str, object]:
    with connect(path) as connection:
        row = connection.execute("SELECT * FROM d3_action_intents WHERE action_id = ?", (action_id,)).fetchone()
        if row is None:
            raise D3PreconditionRejected("ACTION_INTENT_NOT_FOUND")
        _require_executor(connection, executor_id, str(row["tenant_id"]))
        return _row(row) or {}


def _insert_ledger(
    connection: sqlite3.Connection,
    intent: dict[str, object],
    status: str,
    result: dict[str, object],
    before_version: int | None,
    after_version: int | None,
) -> dict[str, object]:
    result_json = canonical_json(result)
    ledger_id = f"ledger-{uuid.uuid4()}"
    connection.execute(
        """INSERT INTO d3_action_ledgers
           (ledger_id, tenant_id, task_id, plan_hash, action_kind, action_id,
            idempotency_key, request_digest, approval_id, status, before_version,
            after_version, result_json, result_digest, committed_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (ledger_id, intent["tenant_id"], intent["task_id"], intent["plan_hash"], intent["action_kind"],
         intent["action_id"], intent["idempotency_key"], intent["request_digest"], intent["approval_id"],
         status, before_version, after_version, result_json,
         hashlib.sha256(result_json.encode("utf-8")).hexdigest(), utc_now()),
    )
    row = _row(connection.execute("SELECT * FROM d3_action_ledgers WHERE ledger_id = ?", (ledger_id,)).fetchone()) or {}
    row["result"] = json.loads(str(row.pop("result_json")))
    return row


def _prior_ledger(connection: sqlite3.Connection, intent: dict[str, object]) -> dict[str, object] | None:
    row = connection.execute("SELECT * FROM d3_action_ledgers WHERE action_id = ?", (intent["action_id"],)).fetchone()
    if row is None:
        return None
    if row["request_digest"] != intent["request_digest"] or row["idempotency_key"] != intent["idempotency_key"]:
        raise KeyReuseConflict("KEY_REUSE_CONFLICT")
    serialized = str(row["result_json"])
    if hashlib.sha256(serialized.encode("utf-8")).hexdigest() != str(row["result_digest"]):
        raise D3PreconditionRejected("ACTION_LEDGER_DIGEST_MISMATCH")
    result = _row(row) or {}
    result["result"] = json.loads(str(result.pop("result_json")))
    return result


def _validate_action_context(
    connection: sqlite3.Connection,
    intent: dict[str, object],
    executor_id: str,
) -> tuple[dict[str, object], dict[str, object], dict[str, object]]:
    binding = _row(connection.execute(
        "SELECT * FROM task_bindings WHERE task_id = ? AND tenant_id = ?",
        (intent["task_id"], intent["tenant_id"]),
    ).fetchone())
    if binding is None:
        raise D3ScopeDenied("Action TaskBinding scope is invalid.")
    _require_executor(connection, executor_id, str(intent["tenant_id"]))
    request = json.loads(str(intent["canonical_request_json"]))
    if request.get("tenant_id") != intent["tenant_id"] or request.get("task_id") != intent["task_id"] or request.get("plan_hash") != intent["plan_hash"] or request.get("action_kind") != intent["action_kind"]:
        raise KeyReuseConflict("KEY_REUSE_CONFLICT")
    plan = _load_plan(connection, str(intent["tenant_id"]), str(intent["task_id"]), str(intent["plan_hash"]))
    approval = _approval_for(connection, str(intent["tenant_id"]), str(intent["task_id"]), str(intent["plan_hash"]))
    if approval["approval_id"] != intent["approval_id"] or approval["decision"] != "APPROVED" or approval["approved_plan_digest"] != intent["plan_hash"]:
        raise D3PreconditionRejected("APPROVAL_DOES_NOT_BIND_ACTION")
    scope = json.loads(str(approval["approval_scope_json"]))
    if (
        scope.get("plan_hash") != plan["plan_hash"]
        or scope.get("target_resource_id") != plan["target_resource_id"]
        or scope.get("environment") != plan["environment"]
        or scope.get("action_kinds") != ["REPAIR", "DELIVER"]
        or scope.get("ticket_id") != plan["ticket_id"]
    ):
        raise D3PreconditionRejected("APPROVAL_SCOPE_MISMATCH")
    expected_request, _, _ = _request_for_action(
        connection, binding, str(intent["plan_hash"]), str(intent["action_kind"])
    )
    expected_json = canonical_json(expected_request)
    expected_digest = hashlib.sha256(expected_json.encode("utf-8")).hexdigest()
    if (
        str(intent["canonical_request_json"]) != expected_json
        or str(intent["request_digest"]) != expected_digest
        or digest_json(request) != expected_digest
    ):
        raise KeyReuseConflict("KEY_REUSE_CONFLICT")
    return binding, plan, approval


def execute_repair(path: str | Path, action_intent_id: str, executor_id: str, attempt_id: str) -> dict[str, object]:
    del attempt_id  # Attempt identity is operational and never changes the business digest.
    with connect(path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        intent = _row(connection.execute("SELECT * FROM d3_action_intents WHERE action_id = ?", (action_intent_id,)).fetchone())
        if intent is None or intent["action_kind"] != "REPAIR":
            raise D3PreconditionRejected("REPAIR_INTENT_NOT_FOUND")
        binding, plan, approval = _validate_action_context(connection, intent, executor_id)
        prior = _prior_ledger(connection, intent)
        if prior is not None:
            return prior
        _assert_plan_control(connection, str(intent["tenant_id"]), str(intent["task_id"]), str(intent["plan_hash"]))
        auth = _authorization(connection, str(intent["tenant_id"]), str(intent["task_id"]), str(intent["plan_hash"]))
        if auth is None or auth["eligibility"] != "ACTIVE":
            raise D3PreconditionRejected("PLAN_NOT_ACTIVE")
        permission = connection.execute(
            """SELECT state, approval_id FROM d3_action_permissions
               WHERE tenant_id = ? AND task_id = ? AND plan_hash = ? AND action_kind = 'REPAIR'""",
            (intent["tenant_id"], intent["task_id"], intent["plan_hash"]),
        ).fetchone()
        if permission is None or permission["state"] != "AVAILABLE" or permission["approval_id"] != approval["approval_id"]:
            raise D3PreconditionRejected("REPAIR_PERMISSION_NOT_AVAILABLE")
        rows = connection.execute(
            """SELECT i.credential_ref, i.config_version, i.principal_id,
                      p.status, p.principal_version, a.accepted_credential_ref, a.policy_version
               FROM integrations AS i
               JOIN principals AS p ON p.tenant_id = i.tenant_id AND p.principal_id = i.principal_id
               JOIN services AS s ON s.tenant_id = i.tenant_id AND s.integration_id = i.integration_id
               JOIN auth_policies AS a ON a.tenant_id = s.tenant_id AND a.service_id = s.service_id
               WHERE i.tenant_id = ? AND i.integration_id = ? AND s.service_id = ?""",
            (intent["tenant_id"], plan["integration_id"], plan["service_id"]),
        ).fetchone()
        if rows is None:
            raise D3PreconditionRejected("REPAIR_TARGET_NOT_FOUND")
        current = _row(rows) or {}
        if current["principal_id"] != plan["principal_id"] or current["status"] != "ENABLED":
            raise D3PreconditionRejected("PRINCIPAL_NOT_ENABLED_OR_MISMATCHED")
        expected = {
            "config_version": int(plan["expected_config_version"]),
            "principal_version": int(plan["expected_principal_version"]),
            "auth_policy_version": int(plan["expected_auth_policy_version"]),
        }
        if (
            int(current["config_version"]) != expected["config_version"]
            or int(current["principal_version"]) != expected["principal_version"]
            or int(current["policy_version"]) != expected["auth_policy_version"]
            or current["credential_ref"] != plan["old_credential_ref"]
            or current["accepted_credential_ref"] != plan["new_credential_ref"]
        ):
            raise D3PreconditionRejected("RESOURCE_VERSION_OR_CREDENTIAL_PRECONDITION_FAILED")
        cursor = connection.execute(
            """UPDATE integrations SET credential_ref = ?, config_version = config_version + 1
               WHERE tenant_id = ? AND integration_id = ? AND principal_id = ?
                 AND credential_ref = ? AND config_version = ?""",
            (plan["new_credential_ref"], intent["tenant_id"], plan["integration_id"], plan["principal_id"], plan["old_credential_ref"], expected["config_version"]),
        )
        if cursor.rowcount != 1:
            raise D3PreconditionRejected("REPAIR_CAS_FAILED")
        _run_d4_test_failpoint("repair_before_commit", connection)
        result = {
            "action_id": intent["action_id"],
            "idempotency_key": intent["idempotency_key"],
            "action_kind": "REPAIR",
            "status": "COMMITTED",
            "tenant_id": binding["tenant_id"],
            "task_id": binding["task_id"],
            "plan_hash": plan["plan_hash"],
            "integration_id": plan["integration_id"],
            "credential_ref_before": current["credential_ref"],
            "credential_ref_after": plan["new_credential_ref"],
            "config_version_before": expected["config_version"],
            "config_version_after": expected["config_version"] + 1,
            "approval_id": approval["approval_id"],
        }
        ledger = _insert_ledger(connection, intent, "COMMITTED", result, expected["config_version"], expected["config_version"] + 1)
        connection.execute(
            """UPDATE d3_action_permissions SET state = 'CONSUMED', used_by_action_id = ?, changed_at = ?
               WHERE tenant_id = ? AND task_id = ? AND plan_hash = ? AND action_kind = 'REPAIR' AND state = 'AVAILABLE'""",
            (intent["action_id"], utc_now(), intent["tenant_id"], intent["task_id"], intent["plan_hash"]),
        )
        connection.execute("UPDATE task_bindings SET status = 'VERIFYING' WHERE task_id = ?", (intent["task_id"],))
        write_outbox_event(
            connection, tenant_id=str(intent["tenant_id"]), task_id=str(intent["task_id"]),
            source_kind="ACTION_LEDGER", source_id=str(intent["action_id"]),
            event_kind="REPAIR_COMMITTED",
            payload={"task_id": str(intent["task_id"]), "plan_hash": str(intent["plan_hash"]),
                     "action_id": str(intent["action_id"]), "action_kind": "REPAIR", "status": "COMMITTED"},
        )
    _run_d4_test_failpoint("repair_after_commit_before_response")
    return ledger


def verify_repair_online(
    path: str | Path,
    task_id: str,
    plan_hash: str,
    repair_action_id: str,
    executor_id: str,
    business_api_url: str,
) -> dict[str, object]:
    binding = get_task_binding(path, task_id)
    with connect(path) as connection:
        _require_executor(connection, executor_id, str(binding["tenant_id"]))
        plan = _load_plan(connection, str(binding["tenant_id"]), task_id, plan_hash)
        ledger = connection.execute(
            """SELECT * FROM d3_action_ledgers WHERE tenant_id = ? AND task_id = ?
               AND plan_hash = ? AND action_kind = 'REPAIR' AND action_id = ?""",
            (binding["tenant_id"], task_id, plan_hash, repair_action_id),
        ).fetchone()
        if ledger is None or ledger["status"] != "COMMITTED":
            raise D3PreconditionRejected("REPAIR_NOT_COMMITTED")
        existing = connection.execute(
            """SELECT * FROM d3_verification_receipts WHERE tenant_id = ? AND task_id = ?
               AND plan_hash = ? AND repair_action_id = ?""",
            (binding["tenant_id"], task_id, plan_hash, repair_action_id),
        ).fetchone()
        if existing is not None:
            result = _row(existing) or {}
            result["probe_observed_versions"] = json.loads(str(result.pop("probe_observed_versions_json")))
            result["business_assertions"] = json.loads(str(result.pop("business_assertions_json")))
            result["recovery_verified"] = bool(result["recovery_verified"])
            return result
        try:
            _assert_plan_control(connection, str(binding["tenant_id"]), task_id, plan_hash)
        except D3PreconditionRejected:
            raise
    # The verifier uses the registered integration, principal and fixed route from Domain.
    probe = probe_orders(path, business_api_url, str(binding["tenant_id"]), str(binding["integration_id"]))
    assertions = {
        "same_tenant": probe.tenant_id == str(binding["tenant_id"]),
        "same_service": str(binding["service_id"]) == str(plan["service_id"]),
        "same_integration": probe.integration_id == str(plan["integration_id"]),
        "same_principal": probe.principal_id == str(plan["principal_id"]),
        "same_business_route": probe.route == str(plan["verification_contract"]["route"]),
        "order_id_matches": probe.body.get("order_id") == plan["verification_contract"]["expected_order_id"],
        "order_status_matches": probe.body.get("status") == plan["verification_contract"]["expected_order_status"],
        "request_id_present": probe.request_id is not None,
        "auth_event_id_present": probe.event_id is not None,
    }
    service_info = get_service_info(path, str(binding["tenant_id"]), str(binding["service_id"]))
    observed_versions = {
        "config_version": probe.config_version,
        "principal_version": int(service_info["principal_version"]),
        "auth_policy_version": int(service_info["policy_version"]),
    }
    assertions["expected_post_repair_versions"] = (
        observed_versions["config_version"] == int(plan["expected_config_version"]) + 1
        and observed_versions["principal_version"] == int(plan["expected_principal_version"])
        and observed_versions["auth_policy_version"] == int(plan["expected_auth_policy_version"])
    )
    verified = probe.status_code == 200 and all(assertions.values())
    receipt_content = {
        "tenant_id": binding["tenant_id"],
        "task_id": task_id,
        "plan_hash": plan_hash,
        "repair_action_id": repair_action_id,
        "service_id": plan["service_id"],
        "integration_id": probe.integration_id,
        "principal_id": probe.principal_id,
        "business_route": probe.route,
        "request_id": probe.request_id,
        "auth_event_id": probe.event_id,
        "observed_versions": observed_versions,
        "response_status": probe.status_code,
        "response_body": probe.body,
        "business_assertions": assertions,
        "recovery_verified": verified,
    }
    digest = digest_json(receipt_content)
    verification_id = f"verification-{uuid.uuid4()}"
    observed_at = datetime.now(timezone.utc).isoformat(timespec="milliseconds")
    with connect(path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        _require_executor(connection, executor_id, str(binding["tenant_id"]))
        _assert_plan_control(connection, str(binding["tenant_id"]), task_id, plan_hash)
        connection.execute(
            """INSERT INTO d3_verification_receipts
               (verification_id, tenant_id, task_id, plan_hash, repair_action_id,
                service_id, integration_id, principal_id, business_route,
                probe_observed_versions_json, observed_at, response_status,
                business_assertions_json, recovery_verified, result_digest)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (verification_id, binding["tenant_id"], task_id, plan_hash, repair_action_id,
             plan["service_id"], probe.integration_id, probe.principal_id, probe.route,
             canonical_json(observed_versions), observed_at, probe.status_code,
             canonical_json({**assertions, "request_id": probe.request_id, "auth_event_id": probe.event_id, "response_body": probe.body}),
             1 if verified else 0, digest),
        )
        connection.execute(
            "UPDATE task_bindings SET status = ? WHERE task_id = ?",
            ("DELIVERY_PENDING" if verified else "FAILED", task_id),
        )
        write_outbox_event(
            connection, tenant_id=str(binding["tenant_id"]), task_id=task_id,
            source_kind="VERIFICATION", source_id=verification_id,
            event_kind="VERIFICATION_COMPLETED",
            payload={"task_id": task_id, "plan_hash": plan_hash,
                     "verification_id": verification_id, "recovery_verified": verified,
                     "response_status": probe.status_code},
        )
    return {
        "verification_id": verification_id,
        "tenant_id": binding["tenant_id"],
        "task_id": task_id,
        "plan_hash": plan_hash,
        "repair_action_id": repair_action_id,
        "service_id": plan["service_id"],
        "integration_id": probe.integration_id,
        "principal_id": probe.principal_id,
        "business_route": probe.route,
        "probe_observed_versions": observed_versions,
        "observed_at": observed_at,
        "response_status": probe.status_code,
        "business_assertions": {**assertions, "response_body": probe.body, "request_id": probe.request_id, "auth_event_id": probe.event_id},
        "recovery_verified": verified,
        "result_digest": digest,
    }


def get_verification_receipt(
    path: str | Path,
    task_id: str,
    verification_id: str,
    executor_id: str,
) -> dict[str, object]:
    binding = get_task_binding(path, task_id)
    with connect(path) as connection:
        _require_executor(connection, executor_id, str(binding["tenant_id"]))
        item = _row(connection.execute(
            """SELECT * FROM d3_verification_receipts
               WHERE tenant_id = ? AND task_id = ? AND verification_id = ?""",
            (binding["tenant_id"], task_id, verification_id),
        ).fetchone())
    if item is None:
        raise D3PreconditionRejected("VERIFICATION_RECEIPT_NOT_FOUND")
    item["probe_observed_versions"] = json.loads(str(item.pop("probe_observed_versions_json")))
    item["business_assertions"] = json.loads(str(item.pop("business_assertions_json")))
    item["recovery_verified"] = bool(item["recovery_verified"])
    return item


def get_or_create_report(
    path: str | Path,
    task_id: str,
    plan_hash: str,
    repair_action_id: str,
    executor_id: str,
) -> dict[str, object]:
    binding = get_task_binding(path, task_id)
    with connect(path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        _require_executor(connection, executor_id, str(binding["tenant_id"]))
        plan = _load_plan(connection, str(binding["tenant_id"]), task_id, plan_hash)
        ledger = connection.execute(
            """SELECT * FROM d3_action_ledgers WHERE tenant_id = ? AND task_id = ? AND plan_hash = ?
               AND action_kind = 'REPAIR' AND action_id = ? AND status = 'COMMITTED'""",
            (binding["tenant_id"], task_id, plan_hash, repair_action_id),
        ).fetchone()
        receipt = connection.execute(
            """SELECT * FROM d3_verification_receipts WHERE tenant_id = ? AND task_id = ?
               AND plan_hash = ? AND repair_action_id = ? AND recovery_verified = 1""",
            (binding["tenant_id"], task_id, plan_hash, repair_action_id),
        ).fetchone()
        if ledger is None or receipt is None:
            raise D3PreconditionRejected("REPORT_REQUIRES_COMMITTED_REPAIR_AND_RECOVERED_VERIFICATION")
        existing = connection.execute(
            """SELECT * FROM d3_report_artifacts WHERE tenant_id = ? AND task_id = ? AND plan_hash = ?
               AND repair_action_id = ? AND report_version = 1""",
            (binding["tenant_id"], task_id, plan_hash, repair_action_id),
        ).fetchone()
        if existing is not None:
            immutable_content = str(existing["immutable_content_json"])
            if hashlib.sha256(immutable_content.encode("utf-8")).hexdigest() != str(existing["content_digest"]):
                raise D3PreconditionRejected("FROZEN_REPORT_DIGEST_MISMATCH")
            item = _row(existing) or {}
            item["report"] = json.loads(str(item.pop("immutable_content_json")))
            return item
        _assert_plan_control(connection, str(binding["tenant_id"]), task_id, plan_hash)
        evidence_rows = connection.execute(
            """SELECT * FROM d2_evidence WHERE task_id = ?
               AND evidence_id IN (%s) ORDER BY fetched_at"""
            % ",".join("?" for _ in plan["required_evidence_ids"]),
            (task_id, *plan["required_evidence_ids"]),
        ).fetchall()
        evidence = []
        for row in evidence_rows:
            item = _row(row) or {}
            item["observed_versions"] = json.loads(str(item.pop("observed_versions_json")))
            item["facts"] = json.loads(str(item.pop("facts_json")))
            evidence.append(item)
        ledger_result = json.loads(str(ledger["result_json"]))
        receipt_result = _row(receipt) or {}
        receipt_result["probe_observed_versions"] = json.loads(str(receipt_result.pop("probe_observed_versions_json")))
        receipt_result["business_assertions"] = json.loads(str(receipt_result.pop("business_assertions_json")))
        body = {
            "schema_version": "opspilot-d3-report-v1",
            "business_outcome": "RECOVERED",
            "delivery_status": "PENDING",
            "tenant_id": binding["tenant_id"],
            "task_id": task_id,
            "plan_hash": plan_hash,
            "plan": plan,
            "repair_ledger": ledger_result,
            "verification_receipt": receipt_result,
            "evidence": [
                {"evidence_id": item["evidence_id"], "fact_type": item["fact_type"], "resource_id": item["resource_id"], "facts": item["facts"], "observed_versions": item["observed_versions"]}
                for item in evidence
            ],
            "ticket_id": plan["ticket_id"],
            "allowed_delivery_fields": plan["allowed_delivery_fields"],
            "report_version": 1,
        }
        content = canonical_json(body)
        digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
        report_ref = f"report-{uuid.uuid4()}"
        created_at = utc_now()
        connection.execute(
            """INSERT INTO d3_report_artifacts
               (report_ref, tenant_id, task_id, plan_hash, repair_action_id, verification_id,
                report_version, content_digest, immutable_content_json, created_at)
               VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?, ?)""",
            (report_ref, binding["tenant_id"], task_id, plan_hash, repair_action_id,
             receipt["verification_id"], digest, content, created_at),
        )
        write_outbox_event(
            connection, tenant_id=str(binding["tenant_id"]), task_id=task_id,
            source_kind="REPORT", source_id=report_ref, event_kind="REPORT_FROZEN",
            payload={"task_id": task_id, "plan_hash": plan_hash, "report_ref": report_ref,
                     "report_version": 1, "status": "FROZEN"},
        )
        result = {
            "report_ref": report_ref,
            "tenant_id": binding["tenant_id"],
            "task_id": task_id,
            "plan_hash": plan_hash,
            "repair_action_id": repair_action_id,
            "verification_id": receipt["verification_id"],
            "report_version": 1,
            "content_digest": digest,
            "immutable_content_json": content,
            "created_at": created_at,
            "report": body,
        }
    return result


def execute_deliver(path: str | Path, action_intent_id: str, executor_id: str, attempt_id: str) -> dict[str, object]:
    del attempt_id
    with connect(path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        intent = _row(connection.execute("SELECT * FROM d3_action_intents WHERE action_id = ?", (action_intent_id,)).fetchone())
        if intent is None or intent["action_kind"] != "DELIVER":
            raise D3PreconditionRejected("DELIVER_INTENT_NOT_FOUND")
        binding, plan, approval = _validate_action_context(connection, intent, executor_id)
        prior = _prior_ledger(connection, intent)
        if prior is not None:
            return prior
        _assert_plan_control(connection, str(intent["tenant_id"]), str(intent["task_id"]), str(intent["plan_hash"]))
        auth = _authorization(connection, str(intent["tenant_id"]), str(intent["task_id"]), str(intent["plan_hash"]))
        if auth is None or auth["eligibility"] != "ACTIVE":
            raise D3PreconditionRejected("PLAN_NOT_ACTIVE")
        permission = connection.execute(
            """SELECT state, approval_id FROM d3_action_permissions
               WHERE tenant_id = ? AND task_id = ? AND plan_hash = ? AND action_kind = 'DELIVER'""",
            (intent["tenant_id"], intent["task_id"], intent["plan_hash"]),
        ).fetchone()
        if permission is None or permission["state"] != "AVAILABLE" or permission["approval_id"] != approval["approval_id"]:
            raise D3PreconditionRejected("DELIVER_PERMISSION_NOT_AVAILABLE")
        request = json.loads(str(intent["canonical_request_json"]))
        parameters = request["action_parameters"]
        ticket_id = str(parameters["ticket_id"])
        report = connection.execute(
            """SELECT * FROM d3_report_artifacts WHERE report_ref = ? AND tenant_id = ? AND task_id = ?
               AND plan_hash = ? AND report_version = ? AND content_digest = ?""",
            (parameters["report_ref"], intent["tenant_id"], intent["task_id"], intent["plan_hash"], parameters["report_version"], parameters["content_digest"]),
        ).fetchone()
        receipt = connection.execute(
            """SELECT * FROM d3_verification_receipts WHERE verification_id = ? AND tenant_id = ?
               AND task_id = ? AND plan_hash = ? AND recovery_verified = 1""",
            (parameters["verification_id"], intent["tenant_id"], intent["task_id"], intent["plan_hash"]),
        ).fetchone()
        repair_ledger = connection.execute(
            """SELECT action_id FROM d3_action_ledgers WHERE tenant_id = ? AND task_id = ? AND plan_hash = ?
               AND action_kind = 'REPAIR' AND status = 'COMMITTED'""",
            (intent["tenant_id"], intent["task_id"], intent["plan_hash"]),
        ).fetchone()
        ticket = connection.execute(
            "SELECT tenant_id, ticket_id, status FROM tickets WHERE tenant_id = ? AND ticket_id = ?",
            (intent["tenant_id"], ticket_id),
        ).fetchone()
        if (
            report is None or receipt is None or repair_ledger is None or ticket is None
            or ticket_id != str(binding["ticket_id"]) or ticket_id != str(plan["ticket_id"])
            or parameters["allowed_fields"] != plan["allowed_delivery_fields"]
            or "resolution_entry" not in plan["allowed_delivery_fields"]
            or report["verification_id"] != parameters["verification_id"]
            or report["repair_action_id"] != repair_ledger["action_id"]
            or receipt["verification_id"] != report["verification_id"]
        ):
            raise D3PreconditionRejected("DELIVERY_SCOPE_OR_VERIFICATION_INVALID")
        report_content = str(report["immutable_content_json"])
        if hashlib.sha256(report_content.encode("utf-8")).hexdigest() != str(report["content_digest"]):
            raise D3PreconditionRejected("FROZEN_REPORT_DIGEST_MISMATCH")
        report_body = json.loads(report_content)
        report_verification = report_body.get("verification_receipt")
        report_repair = report_body.get("repair_ledger")
        if (
            report_body.get("business_outcome") != "RECOVERED"
            or report_body.get("tenant_id") != intent["tenant_id"]
            or report_body.get("task_id") != intent["task_id"]
            or report_body.get("plan_hash") != intent["plan_hash"]
            or report_body.get("report_version") != int(report["report_version"])
            or not isinstance(report_verification, dict)
            or report_verification.get("verification_id") != receipt["verification_id"]
            or not isinstance(report_repair, dict)
            or report_repair.get("action_id") != report["repair_action_id"]
        ):
            raise D3PreconditionRejected("FROZEN_REPORT_BINDING_INVALID")
        resolution = {
            "outcome": "RECOVERED",
            "summary": "Credential reference was repaired and verified by the registered business route.",
            "report_ref": report["report_ref"],
            "report_version": int(report["report_version"]),
            "report_digest": report["content_digest"],
            "verification_id": receipt["verification_id"],
            "repair_action_id": report["repair_action_id"],
            "plan_hash": intent["plan_hash"],
        }
        resolution_json = canonical_json(resolution)
        resolution_digest = hashlib.sha256(resolution_json.encode("utf-8")).hexdigest()
        entry_id = f"ticket-entry-{uuid.uuid4()}"
        connection.execute(
            """INSERT INTO d3_ticket_resolution_entries
               (entry_id, tenant_id, ticket_id, task_id, plan_hash, delivery_action_id,
                field_name, content_json, content_digest, created_at)
               VALUES (?, ?, ?, ?, ?, ?, 'resolution_entry', ?, ?, ?)""",
            (entry_id, intent["tenant_id"], ticket_id, intent["task_id"], intent["plan_hash"], intent["action_id"], resolution_json, resolution_digest, utc_now()),
        )
        delivery_receipt = {
            "delivery_action_id": intent["action_id"],
            "ticket_id": ticket_id,
            "ticket_entry_id": entry_id,
            "report_ref": report["report_ref"],
            "report_version": report["report_version"],
            "report_digest": report["content_digest"],
            "verification_id": receipt["verification_id"],
            "resolution_digest": resolution_digest,
            "status": "COMMITTED",
        }
        connection.execute(
            """INSERT INTO d3_delivery_records
               (delivery_id, tenant_id, task_id, plan_hash, delivery_action_id, ticket_id,
                report_ref, report_version, payload_digest, ticket_entry_id,
                delivery_receipt_json, committed_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (f"delivery-{uuid.uuid4()}", intent["tenant_id"], intent["task_id"], intent["plan_hash"], intent["action_id"], ticket_id,
             report["report_ref"], report["report_version"], intent["request_digest"], entry_id,
             canonical_json(delivery_receipt), utc_now()),
        )
        ledger = _insert_ledger(connection, intent, "COMMITTED", delivery_receipt, None, None)
        connection.execute(
            """UPDATE d3_action_permissions SET state = 'CONSUMED', used_by_action_id = ?, changed_at = ?
               WHERE tenant_id = ? AND task_id = ? AND plan_hash = ? AND action_kind = 'DELIVER' AND state = 'AVAILABLE'""",
            (intent["action_id"], utc_now(), intent["tenant_id"], intent["task_id"], intent["plan_hash"]),
        )
        connection.execute("UPDATE task_bindings SET status = 'COMPLETED' WHERE task_id = ?", (intent["task_id"],))
        write_outbox_event(
            connection, tenant_id=str(intent["tenant_id"]), task_id=str(intent["task_id"]),
            source_kind="ACTION_LEDGER", source_id=str(intent["action_id"]),
            event_kind="DELIVERY_COMMITTED",
            payload={"task_id": str(intent["task_id"]), "plan_hash": str(intent["plan_hash"]),
                     "action_id": str(intent["action_id"]), "action_kind": "DELIVER", "status": "COMMITTED"},
        )
        _run_d4_test_failpoint("deliver_before_commit", connection)
    _run_d4_test_failpoint("deliver_after_commit_before_response")
    return ledger


def save_local_report(
    path: str | Path,
    task_id: str,
    outcome: str,
    content: dict[str, object],
    plan_hash: str | None = None,
    *,
    run_id: str | None = None,
) -> dict[str, object]:
    binding = get_task_binding(path, task_id)
    if {"tenant_id", "task_id", "outcome", "schema_version"} & set(content):
        raise D3PreconditionRejected("LOCAL_REPORT_RESERVED_FIELD_OVERRIDE")
    body = {"schema_version": "opspilot-d3-local-report-v1", "outcome": outcome, "tenant_id": binding["tenant_id"], "task_id": task_id, **content}
    serialized = canonical_json(body)
    digest = hashlib.sha256(serialized.encode("utf-8")).hexdigest()
    with connect(path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        if plan_hash is None:
            if run_id is None:
                _assert_control(connection, str(binding["tenant_id"]), task_id, 0, allow_completed=True)
            else:
                run = connection.execute(
                    "SELECT expected_control_revision FROM task_runs WHERE run_id = ? AND tenant_id = ? AND task_id = ?",
                    (run_id, binding["tenant_id"], task_id),
                ).fetchone()
                if run is None:
                    raise D3PreconditionRejected("TASK_RUN_NOT_FOUND")
                _assert_control(
                    connection, str(binding["tenant_id"]), task_id,
                    int(run["expected_control_revision"]), run_id=run_id, allow_completed=True,
                )
        else:
            _assert_plan_control(connection, str(binding["tenant_id"]), task_id, plan_hash, allow_completed=True)
        existing = connection.execute(
            """SELECT * FROM d3_local_reports WHERE tenant_id = ? AND task_id = ?
               AND ((plan_hash IS NULL AND ? IS NULL) OR plan_hash = ?) AND outcome = ?""",
            (binding["tenant_id"], task_id, plan_hash, plan_hash, outcome),
        ).fetchone()
        if existing is not None:
            if existing["content_digest"] != digest:
                raise D3Error("Immutable local report already exists with different content.")
            result = _row(existing) or {}
            result["report"] = json.loads(str(result.pop("immutable_content_json")))
            return result
        report_ref = f"local-report-{uuid.uuid4()}"
        connection.execute(
            """INSERT INTO d3_local_reports
               (report_ref, tenant_id, task_id, plan_hash, outcome, content_digest,
                immutable_content_json, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (report_ref, binding["tenant_id"], task_id, plan_hash, outcome, digest, serialized, utc_now()),
        )
        connection.execute(
            "UPDATE task_bindings SET status = 'COMPLETED' WHERE task_id = ? AND status != 'COMPLETED'",
            (task_id,),
        )
    return {"report_ref": report_ref, "tenant_id": binding["tenant_id"], "task_id": task_id, "plan_hash": plan_hash, "outcome": outcome, "content_digest": digest, "report": body}


def get_task_ticket_entries(path: str | Path, task_id: str, actor_id: str) -> list[dict[str, object]]:
    binding = get_task_binding(path, task_id)
    with connect(path) as connection:
        operator = connection.execute("SELECT tenant_id FROM trusted_operators WHERE actor_id = ?", (actor_id,)).fetchone()
        executor = connection.execute("SELECT tenant_id FROM executor_services WHERE executor_id = ? AND active = 1", (actor_id,)).fetchone()
        if (operator is None or operator["tenant_id"] != binding["tenant_id"]) and (executor is None or executor["tenant_id"] != binding["tenant_id"]):
            raise D3ScopeDenied("Ticket entry read scope check failed.")
        rows = connection.execute(
            """SELECT entry_id, ticket_id, field_name, content_json, content_digest, created_at
               FROM d3_ticket_resolution_entries WHERE tenant_id = ? AND task_id = ? ORDER BY created_at, rowid""",
            (binding["tenant_id"], task_id),
        ).fetchall()
    result = []
    for row in rows:
        item = _row(row) or {}
        item["content"] = json.loads(str(item.pop("content_json")))
        result.append(item)
    return result


def get_task_action_state(path: str | Path, task_id: str, actor_id: str) -> dict[str, object]:
    binding = get_task_binding(path, task_id)
    with connect(path) as connection:
        operator = connection.execute("SELECT tenant_id FROM trusted_operators WHERE actor_id = ?", (actor_id,)).fetchone()
        executor = connection.execute("SELECT tenant_id FROM executor_services WHERE executor_id = ? AND active = 1", (actor_id,)).fetchone()
        if (operator is None or operator["tenant_id"] != binding["tenant_id"]) and (executor is None or executor["tenant_id"] != binding["tenant_id"]):
            raise D3ScopeDenied("Action state read scope check failed.")
        plan_rows = connection.execute("SELECT * FROM d3_plans WHERE tenant_id = ? AND task_id = ? ORDER BY plan_version", (binding["tenant_id"], task_id)).fetchall()
        authorizations = connection.execute("SELECT * FROM d3_plan_authorizations WHERE tenant_id = ? AND task_id = ?", (binding["tenant_id"], task_id)).fetchall()
        approvals = connection.execute("SELECT * FROM d3_approvals WHERE tenant_id = ? AND task_id = ?", (binding["tenant_id"], task_id)).fetchall()
        permissions = connection.execute("SELECT * FROM d3_action_permissions WHERE tenant_id = ? AND task_id = ?", (binding["tenant_id"], task_id)).fetchall()
        intents = connection.execute("SELECT * FROM d3_action_intents WHERE tenant_id = ? AND task_id = ?", (binding["tenant_id"], task_id)).fetchall()
        ledgers = connection.execute("SELECT * FROM d3_action_ledgers WHERE tenant_id = ? AND task_id = ?", (binding["tenant_id"], task_id)).fetchall()
        receipts = connection.execute("SELECT * FROM d3_verification_receipts WHERE tenant_id = ? AND task_id = ?", (binding["tenant_id"], task_id)).fetchall()
        reports = connection.execute("SELECT * FROM d3_report_artifacts WHERE tenant_id = ? AND task_id = ?", (binding["tenant_id"], task_id)).fetchall()
        deliveries = connection.execute("SELECT * FROM d3_delivery_records WHERE tenant_id = ? AND task_id = ?", (binding["tenant_id"], task_id)).fetchall()
        local_reports = connection.execute("SELECT * FROM d3_local_reports WHERE tenant_id = ? AND task_id = ?", (binding["tenant_id"], task_id)).fetchall()
    return {
        "task_binding": {key: binding[key] for key in ("task_id", "thread_id", "tenant_id", "actor_id", "service_id", "integration_id", "principal_id", "ticket_id", "status")},
        "plans": [_row(row) for row in plan_rows],
        "plan_authorizations": [_row(row) for row in authorizations],
        "approvals": [_row(row) for row in approvals],
        "permissions": [_row(row) for row in permissions],
        "action_intents": [_row(row) for row in intents],
        "action_ledgers": [_row(row) for row in ledgers],
        "verification_receipts": [_row(row) for row in receipts],
        "report_artifacts": [_row(row) for row in reports],
        "delivery_records": [_row(row) for row in deliveries],
        "local_reports": [_row(row) for row in local_reports],
        "ticket_entries": get_task_ticket_entries(path, task_id, actor_id),
    }


def get_task_outcome(path: str | Path, task_id: str, actor_id: str) -> dict[str, object]:
    """Return a small read-only projection of persisted approval and S1 receipts."""
    binding = get_task_binding(path, task_id)
    with connect(path) as connection:
        operator = connection.execute(
            "SELECT tenant_id, role FROM trusted_operators WHERE actor_id = ?", (actor_id,)
        ).fetchone()
        if (
            operator is None or str(operator["tenant_id"]) != str(binding["tenant_id"])
            or str(operator["role"]) != "SUPPORT" or actor_id != str(binding["actor_id"])
        ):
            raise D3ScopeDenied("Task outcome read scope check failed.")
        plan = connection.execute(
            """SELECT p.plan_hash, p.plan_version, a.eligibility
               FROM d3_plans p LEFT JOIN d3_plan_authorizations a
                 ON a.tenant_id = p.tenant_id AND a.task_id = p.task_id AND a.plan_hash = p.plan_hash
               WHERE p.tenant_id = ? AND p.task_id = ?
               ORDER BY p.plan_version DESC LIMIT 1""",
            (binding["tenant_id"], task_id),
        ).fetchone()
        if plan is None:
            return {"task_id": task_id, "task_status": str(binding["status"]), "business_outcome": "NO_PLAN"}
        plan_hash = str(plan["plan_hash"])
        approval = connection.execute(
            """SELECT approval_id, approver_id, decision, decided_at FROM d3_approvals
               WHERE tenant_id = ? AND task_id = ? AND plan_hash = ?""",
            (binding["tenant_id"], task_id, plan_hash),
        ).fetchone()
        resume_link = connection.execute(
            """SELECT source_investigation_run_id, source_checkpoint_thread_id, resume_run_id,
                      control_revision FROM approval_resume_links
               WHERE tenant_id = ? AND task_id = ? AND plan_hash = ?""",
            (binding["tenant_id"], task_id, plan_hash),
        ).fetchone()
        resume_run = None
        if resume_link is not None:
            resume_run = connection.execute(
                "SELECT run_id, kind, status, blocked_reason FROM task_runs WHERE run_id = ?",
                (resume_link["resume_run_id"],),
            ).fetchone()
        repair = connection.execute(
            """SELECT ledger_id, action_id, status, before_version, after_version, result_json
               FROM d3_action_ledgers WHERE tenant_id = ? AND task_id = ? AND plan_hash = ?
                 AND action_kind = 'REPAIR' ORDER BY committed_at DESC LIMIT 1""",
            (binding["tenant_id"], task_id, plan_hash),
        ).fetchone()
        deliver = connection.execute(
            """SELECT ledger_id, action_id, status, result_json FROM d3_action_ledgers
               WHERE tenant_id = ? AND task_id = ? AND plan_hash = ? AND action_kind = 'DELIVER'
               ORDER BY committed_at DESC LIMIT 1""",
            (binding["tenant_id"], task_id, plan_hash),
        ).fetchone()
        verification = connection.execute(
            """SELECT verification_id, response_status, recovery_verified, business_assertions_json
               FROM d3_verification_receipts WHERE tenant_id = ? AND task_id = ? AND plan_hash = ?
               ORDER BY observed_at DESC LIMIT 1""",
            (binding["tenant_id"], task_id, plan_hash),
        ).fetchone()
        report = connection.execute(
            """SELECT report_ref, report_version, content_digest FROM d3_report_artifacts
               WHERE tenant_id = ? AND task_id = ? AND plan_hash = ? ORDER BY report_version DESC LIMIT 1""",
            (binding["tenant_id"], task_id, plan_hash),
        ).fetchone()
        delivery = connection.execute(
            """SELECT delivery_id, ticket_id, ticket_entry_id, report_ref, committed_at
               FROM d3_delivery_records WHERE tenant_id = ? AND task_id = ? AND plan_hash = ?
               ORDER BY committed_at DESC LIMIT 1""",
            (binding["tenant_id"], task_id, plan_hash),
        ).fetchone()
        ticket_entry_count = int(connection.execute(
            "SELECT COUNT(*) FROM d3_ticket_resolution_entries WHERE tenant_id = ? AND task_id = ?",
            (binding["tenant_id"], task_id),
        ).fetchone()[0])
        local_report = connection.execute(
            """SELECT report_ref, outcome, content_digest FROM d3_local_reports
               WHERE tenant_id = ? AND task_id = ? AND plan_hash = ? ORDER BY created_at DESC LIMIT 1""",
            (binding["tenant_id"], task_id, plan_hash),
        ).fetchone()

    approval_value = ({key: approval[key] for key in approval.keys()} if approval else None)
    repair_value = None
    if repair is not None:
        result = json.loads(str(repair["result_json"]))
        repair_value = {
            "ledger_id": str(repair["ledger_id"]), "action_id": str(repair["action_id"]),
            "status": str(repair["status"]), "before_version": repair["before_version"],
            "after_version": repair["after_version"],
            "credential_ref_before": result.get("credential_ref_before"),
            "credential_ref_after": result.get("credential_ref_after"),
        }
    deliver_value = None
    if deliver is not None:
        receipt = json.loads(str(deliver["result_json"]))
        deliver_value = {
            "ledger_id": str(deliver["ledger_id"]), "action_id": str(deliver["action_id"]),
            "status": str(deliver["status"]), "ticket_id": receipt.get("ticket_id"),
            "ticket_entry_id": receipt.get("ticket_entry_id"),
        }
    verification_value = None
    if verification is not None:
        verification_value = {
            "verification_id": str(verification["verification_id"]),
            "response_status": int(verification["response_status"]),
            "recovery_verified": bool(verification["recovery_verified"]),
            "business_assertions": json.loads(str(verification["business_assertions_json"])),
        }
    if delivery is not None:
        outcome = "DELIVERED"
    elif repair is not None and verification is not None and bool(verification["recovery_verified"]):
        outcome = "RECOVERED_NOT_DELIVERED"
    elif approval is not None and str(approval["decision"]) == "REJECTED":
        outcome = "REJECTED"
    elif approval is not None and str(approval["decision"]) == "APPROVED":
        outcome = "APPROVAL_ACCEPTED"
    else:
        outcome = "WAITING_APPROVAL" if str(binding["status"]) == "WAITING_APPROVAL" else "IN_PROGRESS"
    return {
        "task_id": task_id,
        "task_status": str(binding["status"]),
        "plan": {"plan_hash": plan_hash, "plan_version": int(plan["plan_version"]),
                 "eligibility": str(plan["eligibility"]) if plan["eligibility"] else None},
        "approval": approval_value,
        "resume_link": ({key: resume_link[key] for key in resume_link.keys()} if resume_link else None),
        "resume_run": ({key: resume_run[key] for key in resume_run.keys()} if resume_run else None),
        "repair": repair_value,
        "verification": verification_value,
        "frozen_report": ({key: report[key] for key in report.keys()} if report else None),
        "delivery": ({key: delivery[key] for key in delivery.keys()} if delivery else None),
        "local_report": ({key: local_report[key] for key in local_report.keys()} if local_report else None),
        "ticket_entry_count": ticket_entry_count,
        "business_outcome": outcome,
    }
