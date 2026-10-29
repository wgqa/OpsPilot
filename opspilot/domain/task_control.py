from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from opspilot.domain.database import connect, initialize
from opspilot.domain.events import write_outbox_event


MessageKind = Literal["CHAT_READONLY", "CORRECT_TASK_INPUT"]
RunStatus = Literal[
    "SUCCEEDED", "FAILED", "BLOCKED", "WAITING_INPUT", "WAITING_APPROVAL", "INTERRUPTED_RECOVERABLE"
]


class TaskControlError(RuntimeError):
    def __init__(self, code: str, message: str | None = None):
        super().__init__(message or code)
        self.code = code


class IdempotencyConflict(TaskControlError):
    def __init__(self):
        super().__init__("IDEMPOTENCY_CONFLICT")


class TaskRunBusy(TaskControlError):
    def __init__(self):
        super().__init__("TASK_RUN_BUSY")


@dataclass(frozen=True)
class TrustedIdentity:
    """Server-resolved identity value passed to internal Domain command APIs."""

    actor_id: str
    tenant_id: str
    role: str


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def _canonical(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def trusted_identity(path: str | Path, actor_id: str) -> TrustedIdentity:
    with connect(path) as connection:
        row = connection.execute(
            "SELECT actor_id, tenant_id, role FROM trusted_operators WHERE actor_id = ?",
            (actor_id,),
        ).fetchone()
    if row is None:
        raise TaskControlError("TRUSTED_IDENTITY_REQUIRED")
    return TrustedIdentity(str(row["actor_id"]), str(row["tenant_id"]), str(row["role"]))


def _verify_identity(connection: sqlite3.Connection, identity: TrustedIdentity) -> sqlite3.Row:
    if not isinstance(identity, TrustedIdentity):
        raise TaskControlError("TRUSTED_IDENTITY_REQUIRED")
    row = connection.execute(
        "SELECT actor_id, tenant_id, role FROM trusted_operators WHERE actor_id = ?",
        (identity.actor_id,),
    ).fetchone()
    if row is None or (str(row["tenant_id"]), str(row["role"])) != (identity.tenant_id, identity.role):
        raise TaskControlError("TRUSTED_IDENTITY_MISMATCH")
    return row


def _require_support_owner(
    connection: sqlite3.Connection, identity: TrustedIdentity, task_id: str
) -> sqlite3.Row:
    operator = _verify_identity(connection, identity)
    binding = connection.execute(
        "SELECT * FROM task_bindings WHERE task_id = ? AND tenant_id = ? AND actor_id = ?",
        (task_id, operator["tenant_id"], operator["actor_id"]),
    ).fetchone()
    if operator["role"] != "SUPPORT" or binding is None:
        raise TaskControlError("TASK_OWNER_REQUIRED")
    return binding


def _control(connection: sqlite3.Connection, tenant_id: str, task_id: str) -> sqlite3.Row:
    row = connection.execute(
        "SELECT * FROM task_controls WHERE tenant_id = ? AND task_id = ?",
        (tenant_id, task_id),
    ).fetchone()
    if row is None:
        raise TaskControlError("TASK_CONTROL_MIGRATION_REQUIRED")
    return row


def _is_readonly_followup(connection: sqlite3.Connection, run_id: str) -> bool:
    return connection.execute(
        "SELECT 1 FROM c1_readonly_followup_runs WHERE run_id=?", (run_id,)
    ).fetchone() is not None


def _record_readonly_followup_failure_in_transaction(
    connection: sqlite3.Connection, run_id: str, reason_code: str,
) -> None:
    row = connection.execute(
        "SELECT result_digest FROM c1_readonly_followup_runs WHERE run_id=?", (run_id,)
    ).fetchone()
    if row is None or row["result_digest"]:
        return
    answer = "本次只读补查未完成；Task 和既有业务诊断保持不变。请检查当前授权与运行状态后再继续。"
    refs_json = "[]"
    result_json = json.dumps(
        {"run_id": run_id, "status": "NOT_COMPLETED"},
        ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    )
    safe_reason = reason_code[:100]
    digest = _digest({
        "run_id": run_id, "result_state": "NOT_COMPLETED", "answer_text": answer,
        "source_refs_json": refs_json, "result_json": result_json, "reason_code": safe_reason,
    })
    now = _utc_now()
    connection.execute(
        """UPDATE c1_readonly_followup_runs SET result_state='NOT_COMPLETED',answer_text=?,
           source_refs_json=?,result_json=?,result_digest=?,reason_code=?,completed_at=?
           WHERE run_id=? AND result_digest IS NULL""",
        (answer, refs_json, result_json, digest, safe_reason, now, run_id),
    )


def _is_business_complete(connection: sqlite3.Connection, tenant_id: str, task_id: str) -> bool:
    binding = connection.execute(
        "SELECT status FROM task_bindings WHERE tenant_id = ? AND task_id = ?",
        (tenant_id, task_id),
    ).fetchone()
    delivered = connection.execute(
        "SELECT 1 FROM d3_delivery_records WHERE tenant_id = ? AND task_id = ? LIMIT 1",
        (tenant_id, task_id),
    ).fetchone()
    return bool(delivered is not None or (binding is not None and str(binding["status"]) == "COMPLETED"))


def assert_task_control_in_transaction(
    connection: sqlite3.Connection,
    tenant_id: str,
    task_id: str,
    expected_control_revision: int | None = None,
    *,
    run_id: str | None = None,
    allow_completed: bool = False,
    allow_pending_for_run: bool = False,
) -> sqlite3.Row:
    """Final control check for callers already holding the Domain write transaction.

    Omitted revision is the deliberately narrow legacy route: it can act only at
    revision zero. New Runs must supply their persisted run_id.
    """
    state = _control(connection, tenant_id, task_id)
    if str(state["terminal_state"]) != "ACTIVE":
        raise TaskControlError("TASK_ABORTED")
    pending = state["pending_critical_message_seq"]
    if pending is not None and not allow_pending_for_run:
        raise TaskControlError("TASK_INPUT_PENDING")
    run: sqlite3.Row | None = None
    if run_id is not None:
        run = connection.execute(
            "SELECT * FROM task_runs WHERE run_id = ? AND tenant_id = ? AND task_id = ?",
            (run_id, tenant_id, task_id),
        ).fetchone()
        if run is None or str(run["status"]) != "RUNNING":
            raise TaskControlError("TASK_RUN_NOT_ACTIVE")
        if expected_control_revision is None:
            expected_control_revision = run["expected_control_revision"]
    if expected_control_revision is None:
        expected_control_revision = 0
    if int(state["control_revision"]) != int(expected_control_revision):
        raise TaskControlError("TASK_CONTROL_STALE")
    if not allow_completed and _is_business_complete(connection, tenant_id, task_id):
        raise TaskControlError("TASK_ALREADY_TERMINAL")
    if run is not None:
        run_revision = run["expected_control_revision"]
        if run_revision is None or int(run_revision) != int(expected_control_revision):
            raise TaskControlError("TASK_CONTROL_STALE")
        if pending is not None and int(run["consumed_message_seq"]) < int(pending):
            raise TaskControlError("TASK_INPUT_PENDING")
    return state


def assert_plan_control_in_transaction(
    connection: sqlite3.Connection,
    tenant_id: str,
    task_id: str,
    plan_hash: str,
    *,
    allow_completed: bool = False,
) -> sqlite3.Row:
    binding = connection.execute(
        """SELECT * FROM d3_plan_control_bindings
           WHERE tenant_id = ? AND task_id = ? AND plan_hash = ?""",
        (tenant_id, task_id, plan_hash),
    ).fetchone()
    if binding is None:
        raise TaskControlError("PLAN_CONTROL_BINDING_MISSING")
    assert_task_control_in_transaction(
        connection,
        tenant_id,
        task_id,
        int(binding["bound_control_revision"]),
        allow_completed=allow_completed,
    )
    state = _control(connection, tenant_id, task_id)
    if int(binding["consumed_message_seq"]) < int(state["applied_critical_message_seq"]):
        raise TaskControlError("TASK_CONTROL_STALE")
    return state


def assert_legacy_task_control(
    path: str | Path, task_id: str, *, allow_completed: bool = False
) -> dict[str, object]:
    with connect(path) as connection:
        binding = connection.execute("SELECT * FROM task_bindings WHERE task_id = ?", (task_id,)).fetchone()
        if binding is None:
            raise TaskControlError("TASK_NOT_FOUND")
        state = assert_task_control_in_transaction(
            connection,
            str(binding["tenant_id"]),
            task_id,
            0,
            allow_completed=allow_completed,
        )
        return {key: state[key] for key in state.keys()}


def _invalidate_plans_in_transaction(
    connection: sqlite3.Connection,
    tenant_id: str,
    task_id: str,
    actor_id: str,
    reason: str,
) -> int:
    now = _utc_now()
    rows = connection.execute(
        """SELECT plan_hash, generation FROM d3_plan_authorizations
           WHERE tenant_id = ? AND task_id = ? AND eligibility = 'ACTIVE'""",
        (tenant_id, task_id),
    ).fetchall()
    for row in rows:
        generation = int(row["generation"]) + 1
        plan_hash = str(row["plan_hash"])
        connection.execute(
            """UPDATE d3_plan_authorizations SET eligibility = 'CANCELLED', generation = ?,
                      changed_by = ?, change_reason = ?, changed_at = ?
               WHERE tenant_id = ? AND task_id = ? AND plan_hash = ? AND eligibility = 'ACTIVE'""",
            (generation, actor_id, reason, now, tenant_id, task_id, plan_hash),
        )
        connection.execute(
            """INSERT INTO d3_plan_authorization_history
               (history_id, tenant_id, task_id, plan_hash, eligibility, generation,
                changed_by, change_reason, changed_at)
               VALUES (?, ?, ?, ?, 'CANCELLED', ?, ?, ?, ?)""",
            (f"plan-history-{uuid.uuid4()}", tenant_id, task_id, plan_hash, generation, actor_id, reason, now),
        )
    connection.execute(
        """UPDATE d3_action_permissions SET state = 'REVOKED', changed_at = ?
           WHERE tenant_id = ? AND task_id = ? AND state = 'AVAILABLE'""",
        (now, tenant_id, task_id),
    )
    return len(rows)


def _insert_outbox(
    connection: sqlite3.Connection,
    tenant_id: str,
    task_id: str | None,
    session_id: str | None,
    source_kind: str,
    source_id: str,
    event_kind: str,
    payload: dict[str, object],
) -> None:
    write_outbox_event(
        connection,
        tenant_id=tenant_id,
        task_id=task_id,
        session_id=session_id,
        source_kind=source_kind,
        source_id=source_id,
        event_kind=event_kind,
        payload=payload,
    )


def _find_idempotent_command(
    connection: sqlite3.Connection,
    identity: TrustedIdentity,
    idempotency_key: str,
    command_kind: str,
    target_ref: str,
    request_digest: str,
) -> dict[str, object] | None:
    rows = connection.execute(
        "SELECT * FROM commands WHERE tenant_id = ? AND actor_id = ? AND idempotency_key = ?",
        (identity.tenant_id, identity.actor_id, idempotency_key),
    ).fetchall()
    if not rows:
        return None
    if len(rows) != 1:
        raise TaskControlError("IDEMPOTENCY_STATE_AMBIGUOUS")
    row = rows[0]
    if (
        str(row["command_kind"]) != command_kind
        or str(row["target_ref"]) != target_ref
        or str(row["request_digest"]) != request_digest
    ):
        raise IdempotencyConflict()
    return json.loads(str(row["result_json"]))


def _record_command(
    connection: sqlite3.Connection,
    *,
    command_id: str,
    identity: TrustedIdentity,
    command_kind: str,
    target_ref: str,
    idempotency_key: str,
    request_digest: str,
    accepted_status: str,
    result: dict[str, object],
    message_id: str | None = None,
    run_id: str | None = None,
    error_code: str | None = None,
) -> None:
    connection.execute(
        """INSERT INTO commands
           (command_id, tenant_id, actor_id, command_kind, target_ref, idempotency_key,
            request_digest, accepted_at, accepted_status, error_code, message_id, run_id, result_json)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (command_id, identity.tenant_id, identity.actor_id, command_kind, target_ref,
         idempotency_key, request_digest, _utc_now(), accepted_status, error_code,
         message_id, run_id, _canonical(result)),
    )


def submit_web_plan_approval(
    path: str | Path,
    identity: TrustedIdentity,
    *,
    task_id: str,
    plan_hash: str,
    decision: Literal["APPROVED", "REJECTED"],
    idempotency_key: str,
) -> dict[str, object]:
    """Atomically persist approval, Web command, resume Run, link and Outbox."""
    if decision not in {"APPROVED", "REJECTED"}:
        raise TaskControlError("INVALID_REQUEST")
    if not idempotency_key.strip() or len(idempotency_key) > 200:
        raise TaskControlError("IDEMPOTENCY_KEY_REQUIRED")
    target_ref = f"{task_id}:{plan_hash}"
    request = {
        "command_kind": "WEB_PLAN_APPROVAL", "target_ref": target_ref,
        "task_id": task_id, "plan_hash": plan_hash, "decision": decision,
    }
    request_digest = _digest(request)
    with connect(path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        _verify_identity(connection, identity)
        if identity.role != "APPROVER":
            raise TaskControlError("TASK_APPROVER_REQUIRED")
        binding = connection.execute(
            "SELECT * FROM task_bindings WHERE task_id = ? AND tenant_id = ?",
            (task_id, identity.tenant_id),
        ).fetchone()
        if binding is None:
            raise TaskControlError("TASK_SCOPE_DENIED")
        duplicate = _find_idempotent_command(
            connection, identity, idempotency_key, "WEB_PLAN_APPROVAL", target_ref, request_digest
        )
        if duplicate is not None:
            return {**duplicate, "replayed": True}

        existing = connection.execute(
            """SELECT * FROM d3_approvals WHERE tenant_id = ? AND task_id = ? AND plan_hash = ?""",
            (identity.tenant_id, task_id, plan_hash),
        ).fetchone()
        if existing is not None:
            if str(existing["approver_id"]) != identity.actor_id or str(existing["decision"]) != decision:
                raise TaskControlError("APPROVAL_ALREADY_RECORDED")
            link = connection.execute(
                "SELECT * FROM approval_resume_links WHERE approval_id = ?",
                (existing["approval_id"],),
            ).fetchone()
            if link is None:
                raise TaskControlError("APPROVAL_RESUME_LINK_MISSING")
            command_id = f"command-{uuid.uuid4()}"
            result = {
                "status": "ACCEPTED", "task_id": task_id, "plan_hash": plan_hash,
                "decision": decision, "approval_id": str(existing["approval_id"]),
                "resume_run_id": str(link["resume_run_id"]),
                "control_revision": int(link["control_revision"]),
                "replayed": True,
            }
            _record_command(
                connection, command_id=command_id, identity=identity,
                command_kind="WEB_PLAN_APPROVAL", target_ref=target_ref,
                idempotency_key=idempotency_key, request_digest=request_digest,
                accepted_status="ACCEPTED", result=result, run_id=str(link["resume_run_id"]),
            )
            return result

        from opspilot.domain.d3 import (
            D3PreconditionRejected,
            D3ScopeDenied,
            _load_plan,
            _submit_plan_approval_in_transaction,
        )

        plan_binding = connection.execute(
            """SELECT * FROM d3_plan_control_bindings
               WHERE tenant_id = ? AND task_id = ? AND plan_hash = ?""",
            (identity.tenant_id, task_id, plan_hash),
        ).fetchone()
        if plan_binding is None or plan_binding["task_run_id"] is None:
            raise TaskControlError("APPROVAL_CHECKPOINT_BINDING_MISSING")
        source_run_id = str(plan_binding["task_run_id"])
        source = connection.execute(
            """SELECT * FROM task_runs WHERE run_id = ? AND tenant_id = ? AND task_id = ?""",
            (source_run_id, identity.tenant_id, task_id),
        ).fetchone()
        if (
            source is None or str(source["kind"]) not in {"INVESTIGATE", "RESUME"}
            or str(source["status"]) != "WAITING_APPROVAL"
            or source["expected_control_revision"] is None
            or int(source["expected_control_revision"]) != int(plan_binding["bound_control_revision"])
            or int(source["consumed_message_seq"]) != int(plan_binding["consumed_message_seq"])
            or str(binding["status"]) != "WAITING_APPROVAL"
        ):
            raise TaskControlError("TASK_NOT_WAITING_FOR_APPROVAL")
        control = _control(connection, identity.tenant_id, task_id)
        if str(control["terminal_state"]) != "ACTIVE":
            raise TaskControlError("TASK_ABORTED")
        if control["pending_critical_message_seq"] is not None:
            raise TaskControlError("TASK_INPUT_PENDING")
        revision = int(control["control_revision"])
        if revision != int(plan_binding["bound_control_revision"]):
            raise TaskControlError("TASK_CONTROL_STALE")
        if int(control["applied_critical_message_seq"]) > int(plan_binding["consumed_message_seq"]):
            raise TaskControlError("TASK_CONTROL_STALE")
        plan = _load_plan(connection, identity.tenant_id, task_id, plan_hash)
        current_resource = connection.execute(
            """SELECT i.credential_ref, i.config_version, i.principal_id,
                      p.status AS principal_status, p.principal_version,
                      a.accepted_credential_ref, a.policy_version
               FROM integrations i JOIN principals p ON p.tenant_id = i.tenant_id
                 AND p.principal_id = i.principal_id
               JOIN services s ON s.tenant_id = i.tenant_id AND s.integration_id = i.integration_id
               JOIN auth_policies a ON a.tenant_id = s.tenant_id AND a.service_id = s.service_id
               WHERE i.tenant_id = ? AND i.integration_id = ? AND s.service_id = ?""",
            (identity.tenant_id, plan["integration_id"], plan["service_id"]),
        ).fetchone()
        if decision == "APPROVED":
            if current_resource is None or str(current_resource["principal_id"]) != str(plan["principal_id"]):
                raise TaskControlError("APPROVAL_TARGET_NOT_FOUND")
            if str(current_resource["principal_status"]) != "ENABLED":
                raise TaskControlError("PRINCIPAL_NOT_ENABLED_OR_MISMATCHED")
            if (
                int(current_resource["config_version"]) != int(plan["expected_config_version"])
                or int(current_resource["principal_version"]) != int(plan["expected_principal_version"])
                or int(current_resource["policy_version"]) != int(plan["expected_auth_policy_version"])
                or str(current_resource["credential_ref"]) != str(plan["old_credential_ref"])
                or str(current_resource["accepted_credential_ref"]) != str(plan["new_credential_ref"])
            ):
                raise TaskControlError("RESOURCE_VERSION_OR_CREDENTIAL_PRECONDITION_FAILED")
        session = connection.execute(
            """SELECT s.session_id FROM session_task_links l JOIN sessions s
                 ON s.session_id = l.session_id AND s.tenant_id = l.tenant_id
               WHERE l.task_id = ? AND l.tenant_id = ? AND s.owner_id = ?
               ORDER BY l.is_primary DESC, l.linked_at LIMIT 1""",
            (task_id, identity.tenant_id, str(binding["actor_id"])),
        ).fetchone()
        if session is None:
            raise TaskControlError("SESSION_TASK_LINK_REQUIRED")

        resume_run_id = f"run-{uuid.uuid4()}"
        command_id = f"command-{uuid.uuid4()}"
        now = _utc_now()
        try:
            approval = _submit_plan_approval_in_transaction(
                connection, str(binding["thread_id"]), identity.actor_id,
                plan_hash, decision, resume_run_id=resume_run_id,
            )
        except D3PreconditionRejected as error:
            raise TaskControlError(str(error)) from error
        except D3ScopeDenied as error:
            # D3 scope errors are deliberately collapsed to the same non-enumerating result.
            raise TaskControlError("APPROVAL_SCOPE_DENIED") from error
        approval_id = str(approval["approval_id"])
        checkpoint_thread_id = f"{binding['thread_id']}::{source_run_id}"
        result = {
            "status": "ACCEPTED", "task_id": task_id, "plan_hash": plan_hash,
            "decision": decision, "approval_id": approval_id,
            "resume_run_id": resume_run_id, "source_run_id": source_run_id,
            "control_revision": revision, "run_status": "QUEUED", "replayed": False,
        }
        _record_command(
            connection, command_id=command_id, identity=identity,
            command_kind="WEB_PLAN_APPROVAL", target_ref=target_ref,
            idempotency_key=idempotency_key, request_digest=request_digest,
            accepted_status="ACCEPTED", result=result, run_id=resume_run_id,
        )
        connection.execute(
            """INSERT INTO task_runs
               (run_id, tenant_id, task_id, session_id, command_id, source_message_id,
                kind, status, control_revision_at_start, expected_control_revision,
                consumed_message_seq, applied_critical_message_seq, created_at)
               VALUES (?, ?, ?, ?, ?, NULL, 'APPROVAL_RESUME', 'QUEUED', ?, ?, ?, ?, ?)""",
            (resume_run_id, identity.tenant_id, task_id, str(session["session_id"]), command_id,
             revision, revision, int(source["consumed_message_seq"]),
             int(source["applied_critical_message_seq"]), now),
        )
        connection.execute(
            """INSERT INTO approval_resume_links
               (approval_id, tenant_id, task_id, plan_hash, source_investigation_run_id,
                source_checkpoint_thread_id, resume_run_id, control_revision, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (approval_id, identity.tenant_id, task_id, plan_hash, source_run_id,
             checkpoint_thread_id, resume_run_id, revision, now),
        )
        connection.execute(
            """INSERT INTO worker_retry_state (run_id, retry_count, max_retries, updated_at)
               VALUES (?, 0, 3, ?)""",
            (resume_run_id, now),
        )
        _insert_outbox(
            connection, identity.tenant_id, task_id, str(session["session_id"]),
            "RUN", resume_run_id, "RUN_STATUS_QUEUED",
            {"run_id": resume_run_id, "run_status": "QUEUED", "approval_id": approval_id,
             "plan_hash": plan_hash},
        )
        _insert_outbox(
            connection, identity.tenant_id, task_id, str(session["session_id"]),
            "APPROVAL_RESUME", approval_id, "APPROVAL_RESUME_QUEUED",
            {"task_id": task_id, "plan_hash": plan_hash, "approval_id": approval_id,
             "decision": decision, "resume_run_id": resume_run_id},
        )
    return result


def get_approval_resume_link(
    path: str | Path, identity: TrustedIdentity, run_id: str
) -> dict[str, object]:
    """Validate the durable approval-to-checkpoint link before any checkpoint read."""
    with connect(path) as connection:
        _verify_identity(connection, identity)
        run = connection.execute(
            """SELECT r.*, s.owner_id FROM task_runs r JOIN sessions s
                 ON s.session_id = r.session_id AND s.tenant_id = r.tenant_id
               WHERE r.run_id = ? AND r.tenant_id = ?""",
            (run_id, identity.tenant_id),
        ).fetchone()
        if run is None or str(run["kind"]) != "APPROVAL_RESUME" or str(run["owner_id"]) != identity.actor_id:
            raise TaskControlError("TASK_RUN_SCOPE_DENIED")
        return _validate_approval_resume_in_transaction(connection, run)


def _validate_approval_resume_in_transaction(
    connection: sqlite3.Connection, run: sqlite3.Row
) -> dict[str, object]:
    link = connection.execute(
        """SELECT l.*, a.decision, a.approver_id, a.approved_plan_digest,
                  r.status AS source_status, r.kind AS source_kind,
                  r.consumed_message_seq AS source_consumed_message_seq,
                  b.thread_id, b.status AS task_status,
                  c.terminal_state, c.control_revision AS current_control_revision,
                  c.pending_critical_message_seq, c.applied_critical_message_seq,
                  pc.bound_control_revision, pc.consumed_message_seq AS plan_consumed_message_seq,
                  auth.eligibility
           FROM approval_resume_links l
           JOIN d3_approvals a ON a.approval_id = l.approval_id
           JOIN task_runs r ON r.run_id = l.source_investigation_run_id
           JOIN task_bindings b ON b.tenant_id = l.tenant_id AND b.task_id = l.task_id
           JOIN task_controls c ON c.tenant_id = l.tenant_id AND c.task_id = l.task_id
           JOIN d3_plan_control_bindings pc ON pc.tenant_id = l.tenant_id
             AND pc.task_id = l.task_id AND pc.plan_hash = l.plan_hash
           JOIN d3_plan_authorizations auth ON auth.tenant_id = l.tenant_id
             AND auth.task_id = l.task_id AND auth.plan_hash = l.plan_hash
           WHERE l.resume_run_id = ? AND l.tenant_id = ? AND l.task_id = ?""",
        (str(run["run_id"]), str(run["tenant_id"]), str(run["task_id"])),
    ).fetchone()
    if link is None:
        raise TaskControlError("APPROVAL_RESUME_LINK_MISSING")
    expected_revision = run["expected_control_revision"]
    if (
        str(link["source_kind"]) not in {"INVESTIGATE", "RESUME"}
        or str(link["source_status"]) != "WAITING_APPROVAL"
        or str(link["thread_id"]) + "::" + str(link["source_investigation_run_id"])
            != str(link["source_checkpoint_thread_id"])
        or str(link["plan_hash"]) != str(link["approved_plan_digest"])
        or int(link["control_revision"]) != int(link["bound_control_revision"])
        or expected_revision is None
        or int(link["control_revision"]) != int(expected_revision)
        or int(link["control_revision"]) != int(link["current_control_revision"])
        or link["terminal_state"] != "ACTIVE"
        or link["pending_critical_message_seq"] is not None
        or int(link["plan_consumed_message_seq"]) < int(link["applied_critical_message_seq"])
        or link["eligibility"] != "ACTIVE"
        or int(link["plan_consumed_message_seq"]) != int(link["source_consumed_message_seq"])
        or str(link["decision"]) not in {"APPROVED", "REJECTED"}
    ):
        raise TaskControlError("TASK_CONTROL_STALE")
    if not _approval_resume_domain_stage_is_consistent(connection, link):
        raise TaskControlError("APPROVAL_RESUME_LINK_INVALID")
    return {key: link[key] for key in link.keys()}


def _approval_resume_domain_stage_is_consistent(
    connection: sqlite3.Connection, link: sqlite3.Row
) -> bool:
    """Require the TaskBinding phase to agree with immutable same-Plan receipts."""
    tenant_id, task_id, plan_hash = (
        str(link["tenant_id"]), str(link["task_id"]), str(link["plan_hash"])
    )
    decision = str(link["decision"])
    task_status = str(link["task_status"])
    approval_id = str(link["approval_id"])
    intents = connection.execute(
        """SELECT * FROM d3_action_intents WHERE tenant_id = ? AND task_id = ? AND plan_hash = ?
           ORDER BY action_kind""",
        (tenant_id, task_id, plan_hash),
    ).fetchall()
    ledgers = connection.execute(
        """SELECT * FROM d3_action_ledgers WHERE tenant_id = ? AND task_id = ? AND plan_hash = ?
           ORDER BY action_kind""",
        (tenant_id, task_id, plan_hash),
    ).fetchall()
    receipts = connection.execute(
        """SELECT * FROM d3_verification_receipts WHERE tenant_id = ? AND task_id = ? AND plan_hash = ?""",
        (tenant_id, task_id, plan_hash),
    ).fetchall()
    reports = connection.execute(
        """SELECT * FROM d3_report_artifacts WHERE tenant_id = ? AND task_id = ? AND plan_hash = ?""",
        (tenant_id, task_id, plan_hash),
    ).fetchall()
    deliveries = connection.execute(
        """SELECT * FROM d3_delivery_records WHERE tenant_id = ? AND task_id = ? AND plan_hash = ?""",
        (tenant_id, task_id, plan_hash),
    ).fetchall()
    entries = connection.execute(
        """SELECT * FROM d3_ticket_resolution_entries WHERE tenant_id = ? AND task_id = ? AND plan_hash = ?""",
        (tenant_id, task_id, plan_hash),
    ).fetchall()
    local_reports = connection.execute(
        """SELECT * FROM d3_local_reports WHERE tenant_id = ? AND task_id = ? AND plan_hash = ?""",
        (tenant_id, task_id, plan_hash),
    ).fetchall()

    if decision == "REJECTED":
        if task_status != "COMPLETED" or any((intents, ledgers, receipts, reports, deliveries, entries)):
            return False
        for report in local_reports:
            serialized = str(report["immutable_content_json"])
            if (
                str(report["outcome"]) != "REJECTED"
                or hashlib.sha256(serialized.encode("utf-8")).hexdigest() != str(report["content_digest"])
            ):
                return False
        return True
    if decision != "APPROVED" or len(intents) > 2 or len(ledgers) > 2 or len(receipts) > 1 or len(reports) > 1 or len(deliveries) > 1 or len(entries) > 1 or local_reports:
        return False

    plan_row = connection.execute(
        "SELECT canonical_plan_json FROM d3_plans WHERE tenant_id = ? AND task_id = ? AND plan_hash = ?",
        (tenant_id, task_id, plan_hash),
    ).fetchone()
    if plan_row is None:
        return False
    try:
        plan = json.loads(str(plan_row["canonical_plan_json"]))
    except (TypeError, ValueError):
        return False
    permissions = connection.execute(
        """SELECT action_kind, state, approval_id, used_by_action_id FROM d3_action_permissions
           WHERE tenant_id = ? AND task_id = ? AND plan_hash = ?""",
        (tenant_id, task_id, plan_hash),
    ).fetchall()
    permission_by_kind = {str(item["action_kind"]): item for item in permissions}
    if set(permission_by_kind) != {"REPAIR", "DELIVER"} or any(
        str(item["approval_id"]) != approval_id for item in permissions
    ):
        return False
    intent_by_kind = {str(item["action_kind"]): item for item in intents}
    ledger_by_kind = {str(item["action_kind"]): item for item in ledgers}
    if len(intent_by_kind) != len(intents) or len(ledger_by_kind) != len(ledgers):
        return False
    if set(ledger_by_kind) - set(intent_by_kind):
        return False

    for kind, intent in intent_by_kind.items():
        serialized = str(intent["canonical_request_json"])
        try:
            request = json.loads(serialized)
        except (TypeError, ValueError):
            return False
        if (
            kind not in {"REPAIR", "DELIVER"}
            or request.get("tenant_id") != tenant_id
            or request.get("task_id") != task_id
            or request.get("plan_hash") != plan_hash
            or request.get("action_kind") != kind
            or request.get("approval_id") != approval_id
            or serialized != _canonical(request)
            or hashlib.sha256(serialized.encode("utf-8")).hexdigest() != str(intent["request_digest"])
            or str(intent["approval_id"]) != approval_id
        ):
            return False

    repair_intent = intent_by_kind.get("REPAIR")
    repair_ledger = ledger_by_kind.get("REPAIR")
    if repair_ledger is not None:
        if repair_intent is None or not _approval_resume_ledger_matches_intent(repair_ledger, repair_intent):
            return False
        if str(repair_ledger["status"]) != "COMMITTED":
            return False
        try:
            repair_result = json.loads(str(repair_ledger["result_json"]))
        except (TypeError, ValueError):
            return False
        expected_before = int(plan["expected_config_version"])
        if (
            int(repair_ledger["before_version"] or -1) != expected_before
            or int(repair_ledger["after_version"] or -1) != expected_before + 1
            or repair_result.get("action_id") != str(repair_intent["action_id"])
            or repair_result.get("plan_hash") != plan_hash
            or repair_result.get("config_version_before") != expected_before
            or repair_result.get("config_version_after") != expected_before + 1
            or repair_result.get("credential_ref_before") != plan.get("old_credential_ref")
            or repair_result.get("credential_ref_after") != plan.get("new_credential_ref")
        ):
            return False
        repair_permission = permission_by_kind["REPAIR"]
        if (
            str(repair_permission["state"]) != "CONSUMED"
            or str(repair_permission["used_by_action_id"]) != str(repair_intent["action_id"])
        ):
            return False
    elif any((receipts, reports, deliveries, entries)) or "DELIVER" in intent_by_kind or "DELIVER" in ledger_by_kind:
        return False
    else:
        repair_permission = permission_by_kind["REPAIR"]
        if str(repair_permission["state"]) != "AVAILABLE" or repair_permission["used_by_action_id"] is not None:
            return False

    receipt = receipts[0] if receipts else None
    if receipt is not None:
        if repair_intent is None or repair_ledger is None:
            return False
        try:
            observed = json.loads(str(receipt["probe_observed_versions_json"]))
            assertions = json.loads(str(receipt["business_assertions_json"]))
        except (TypeError, ValueError):
            return False
        expected_versions = {
            "config_version": int(plan["expected_config_version"]) + 1,
            "principal_version": int(plan["expected_principal_version"]),
            "auth_policy_version": int(plan["expected_auth_policy_version"]),
        }
        if (
            str(receipt["repair_action_id"]) != str(repair_intent["action_id"])
            or str(receipt["service_id"]) != str(plan["service_id"])
            or str(receipt["integration_id"]) != str(plan["integration_id"])
            or str(receipt["principal_id"]) != str(plan["principal_id"])
            or str(receipt["business_route"]) != str(plan["verification_contract"]["route"])
            or int(receipt["response_status"]) != 200
            or int(receipt["recovery_verified"]) != 1
            or observed != expected_versions
            or any(value is not True for key, value in assertions.items() if key not in {"request_id", "auth_event_id", "response_body"})
            or not assertions.get("request_id")
            or not assertions.get("auth_event_id")
        ):
            return False
    elif reports or deliveries or entries or "DELIVER" in intent_by_kind or "DELIVER" in ledger_by_kind:
        return False

    report = reports[0] if reports else None
    if report is not None:
        if receipt is None or repair_intent is None or repair_ledger is None:
            return False
        serialized = str(report["immutable_content_json"])
        if hashlib.sha256(serialized.encode("utf-8")).hexdigest() != str(report["content_digest"]):
            return False
        try:
            body = json.loads(serialized)
            body_receipt = body.get("verification_receipt")
            body_repair = body.get("repair_ledger")
        except (TypeError, ValueError):
            return False
        if (
            str(report["repair_action_id"]) != str(repair_intent["action_id"])
            or str(report["verification_id"]) != str(receipt["verification_id"])
            or body.get("business_outcome") != "RECOVERED"
            or body.get("tenant_id") != tenant_id
            or body.get("task_id") != task_id
            or body.get("plan_hash") != plan_hash
            or not isinstance(body_receipt, dict)
            or body_receipt.get("verification_id") != str(receipt["verification_id"])
            or not isinstance(body_repair, dict)
            or body_repair.get("action_id") != str(repair_intent["action_id"])
        ):
            return False

    deliver_intent = intent_by_kind.get("DELIVER")
    deliver_ledger = ledger_by_kind.get("DELIVER")
    delivery = deliveries[0] if deliveries else None
    entry = entries[0] if entries else None
    if deliver_intent is not None:
        if report is None or receipt is None:
            return False
        request = json.loads(str(deliver_intent["canonical_request_json"]))
        parameters = request.get("action_parameters")
        if (
            not isinstance(parameters, dict)
            or parameters.get("report_ref") != str(report["report_ref"])
            or parameters.get("report_version") != int(report["report_version"])
            or parameters.get("content_digest") != str(report["content_digest"])
            or parameters.get("verification_id") != str(receipt["verification_id"])
        ):
            return False
    deliver_permission = permission_by_kind["DELIVER"]
    if deliver_ledger is not None:
        if (
            str(deliver_permission["state"]) != "CONSUMED"
            or str(deliver_permission["used_by_action_id"]) != str(deliver_intent["action_id"] if deliver_intent else "")
        ):
            return False
    elif str(deliver_permission["state"]) != "AVAILABLE" or deliver_permission["used_by_action_id"] is not None:
        return False
    elif deliver_ledger is not None or delivery is not None or entry is not None:
        return False

    delivered = deliver_ledger is not None or delivery is not None or entry is not None
    if delivered:
        if (
            deliver_intent is None or deliver_ledger is None or delivery is None or entry is None
            or not _approval_resume_ledger_matches_intent(deliver_ledger, deliver_intent)
            or str(deliver_ledger["status"]) != "COMMITTED"
            or str(delivery["delivery_action_id"]) != str(deliver_intent["action_id"])
            or str(delivery["plan_hash"]) != plan_hash
            or str(delivery["ticket_id"]) != str(plan["ticket_id"])
            or str(delivery["report_ref"]) != str(report["report_ref"])
            or str(delivery["report_version"]) != str(report["report_version"])
            or str(delivery["ticket_entry_id"]) != str(entry["entry_id"])
            or str(entry["delivery_action_id"]) != str(deliver_intent["action_id"])
            or str(entry["ticket_id"]) != str(plan["ticket_id"])
        ):
            return False
        try:
            delivery_receipt = json.loads(str(delivery["delivery_receipt_json"]))
            ledger_receipt = json.loads(str(deliver_ledger["result_json"]))
            entry_content = str(entry["content_json"])
        except (TypeError, ValueError):
            return False
        if (
            hashlib.sha256(entry_content.encode("utf-8")).hexdigest() != str(entry["content_digest"])
            or delivery_receipt != ledger_receipt
            or delivery_receipt.get("delivery_action_id") != str(deliver_intent["action_id"])
            or delivery_receipt.get("ticket_entry_id") != str(entry["entry_id"])
            or delivery_receipt.get("report_ref") != str(report["report_ref"])
            or delivery_receipt.get("verification_id") != str(receipt["verification_id"])
            or delivery_receipt.get("status") != "COMMITTED"
        ):
            return False
        return task_status == "COMPLETED"
    # Before REPAIR commits, and after REPAIR but before the first verification,
    # the live resources must still match the exact version expected by that
    # phase. Later delivery replay is tied to the immutable verification receipt.
    if receipt is None:
        current = connection.execute(
            """SELECT i.credential_ref, i.config_version, i.principal_id,
                      p.status AS principal_status, p.principal_version,
                      a.policy_version
               FROM integrations i
               JOIN principals p ON p.tenant_id = i.tenant_id AND p.principal_id = i.principal_id
               JOIN services s ON s.tenant_id = i.tenant_id AND s.integration_id = i.integration_id
               JOIN auth_policies a ON a.tenant_id = s.tenant_id AND a.service_id = s.service_id
               WHERE i.tenant_id = ? AND i.integration_id = ? AND s.service_id = ?""",
            (tenant_id, plan["integration_id"], plan["service_id"]),
        ).fetchone()
        config_version = int(plan["expected_config_version"]) + (1 if repair_ledger is not None else 0)
        credential_ref = plan["new_credential_ref"] if repair_ledger is not None else plan["old_credential_ref"]
        if (
            current is None
            or str(current["principal_id"]) != str(plan["principal_id"])
            or str(current["principal_status"]) != "ENABLED"
            or str(current["credential_ref"]) != str(credential_ref)
            or int(current["config_version"]) != config_version
            or int(current["principal_version"]) != int(plan["expected_principal_version"])
            or int(current["policy_version"]) != int(plan["expected_auth_policy_version"])
        ):
            return False
    if task_status == "COMPLETED":
        return False
    if receipt is not None:
        return task_status in {"DELIVERY_PENDING", "INTERRUPTED_RECOVERABLE"}
    if repair_ledger is not None:
        return task_status in {"VERIFYING", "INTERRUPTED_RECOVERABLE"}
    return task_status in {"APPROVED", "INTERRUPTED_RECOVERABLE"}


def _approval_resume_ledger_matches_intent(ledger: sqlite3.Row, intent: sqlite3.Row) -> bool:
    return all(
        str(ledger[key]) == str(intent[key])
        for key in ("tenant_id", "task_id", "plan_hash", "action_kind", "action_id", "idempotency_key", "request_digest", "approval_id")
    ) and hashlib.sha256(str(ledger["result_json"]).encode("utf-8")).hexdigest() == str(ledger["result_digest"])


def create_session(path: str | Path, identity: TrustedIdentity) -> dict[str, object]:
    initialize(path)
    session_id = f"session-{uuid.uuid4()}"
    now = _utc_now()
    with connect(path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        _verify_identity(connection, identity)
        connection.execute(
            "INSERT INTO sessions (session_id, tenant_id, owner_id, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
            (session_id, identity.tenant_id, identity.actor_id, now, now),
        )
        _insert_outbox(
            connection, identity.tenant_id, None, session_id, "SESSION", session_id,
            "SESSION_CREATED", {"status": "CREATED"},
        )
    return {"session_id": session_id, "tenant_id": identity.tenant_id, "owner_id": identity.actor_id, "created_at": now}


def create_task_with_initial_run(
    path: str | Path,
    identity: TrustedIdentity,
    *,
    session_id: str,
    service_id: str,
    integration_id: str,
    ticket_id: str,
    initial_message: str,
    idempotency_key: str,
    deadline_ms: int = 300_000,
    s3_order_id: str | None = None,
    assistant_core: bool = False,
) -> dict[str, object]:
    """Atomically create a trusted S1 binding and its first Message/Command/Run."""
    if not initial_message.strip():
        raise ValueError("Initial message must be non-empty text.")
    if not idempotency_key.strip() or len(idempotency_key) > 200:
        raise ValueError("A non-empty idempotency key of at most 200 characters is required.")
    if deadline_ms < 1000 or deadline_ms > 86_400_000:
        raise ValueError("Investigation deadline must be between 1 second and 24 hours.")
    initialize(path)
    command_kind = "CREATE_TASK"
    request = {
        "command_kind": command_kind,
        "target_ref": session_id,
        "session_id": session_id,
        "service_id": service_id,
        "integration_id": integration_id,
        "s3_order_id": s3_order_id if service_id == "orders-async-demo" else None,
        "ticket_id": ticket_id,
        "initial_message": initial_message,
    }
    if assistant_core:
        if service_id != "orders-async-demo":
            raise TaskControlError("ASSISTANT_BINDING_KIND_INVALID")
        request["execution_core"] = "ASSISTANT_V1"
    request_digest = _digest(request)
    with connect(path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        _verify_identity(connection, identity)
        if identity.role != "SUPPORT":
            raise TaskControlError("TASK_OWNER_REQUIRED")
        duplicate = _find_idempotent_command(
            connection, identity, idempotency_key, command_kind, session_id, request_digest
        )
        if duplicate is not None:
            return {**duplicate, "replayed": True}
        session = connection.execute(
            "SELECT 1 FROM sessions WHERE session_id = ? AND tenant_id = ? AND owner_id = ?",
            (session_id, identity.tenant_id, identity.actor_id),
        ).fetchone()
        if session is None:
            raise TaskControlError("SESSION_SCOPE_DENIED")
        try:
            from opspilot.domain.d2 import ScopeDenied, _create_task_binding_in_transaction

            binding = _create_task_binding_in_transaction(
                connection, identity.actor_id, service_id, integration_id, ticket_id,
                session_id=session_id,
            )
        except ScopeDenied as error:
            raise TaskControlError("RESOURCE_NOT_FOUND") from error
        task_id = str(binding["task_id"])
        if service_id == "orders-async-demo":
            try:
                from opspilot.domain.s3 import ORDER, bind_s3_order_in_transaction
                bind_s3_order_in_transaction(
                    connection, task_id=task_id, tenant_id=identity.tenant_id,
                    service_id=service_id, integration_id=integration_id,
                    order_id=s3_order_id or ORDER, actor_id=identity.actor_id,
                    confirmed_at=_utc_now(),
                )
            except ScopeDenied as error:
                raise TaskControlError("S3_ORDER_NOT_REGISTERED") from error
        elif s3_order_id is not None:
            raise TaskControlError("S3_ORDER_NOT_REGISTERED")
        sequence = int(connection.execute(
            "SELECT COALESCE(MAX(sequence), 0) + 1 FROM messages WHERE session_id = ?",
            (session_id,),
        ).fetchone()[0])
        message_id = f"message-{uuid.uuid4()}"
        command_id = f"command-{uuid.uuid4()}"
        run_id = f"run-{uuid.uuid4()}"
        now = _utc_now()
        body_digest = hashlib.sha256(initial_message.encode("utf-8")).hexdigest()
        result = {
            "status": "ACCEPTED", "command_id": command_id, "session_id": session_id,
            "task_id": task_id, "thread_id": str(binding["thread_id"]),
            "message_id": message_id, "run_id": run_id, "sequence": sequence,
            "run_status": "QUEUED", "request_digest": request_digest,
            "application_state": "RECEIVED_NOT_APPLIED", "replayed": False,
        }
        _record_command(
            connection, command_id=command_id, identity=identity, command_kind=command_kind,
            target_ref=session_id, idempotency_key=idempotency_key, request_digest=request_digest,
            accepted_status="ACCEPTED", result=result, message_id=message_id, run_id=run_id,
        )
        connection.execute(
            """INSERT INTO messages
               (message_id, tenant_id, session_id, task_id, sequence, role, input_kind,
                body, body_digest, command_id, created_at, application_state)
               VALUES (?, ?, ?, ?, ?, 'USER', 'CHAT_READONLY', ?, ?, ?, ?, 'RECEIVED_NOT_APPLIED')""",
            (message_id, identity.tenant_id, session_id, task_id, sequence,
             initial_message, body_digest, command_id, now),
        )
        connection.execute(
            """INSERT INTO task_runs
               (run_id, tenant_id, task_id, session_id, command_id, source_message_id,
                kind, status, control_revision_at_start, expected_control_revision,
                consumed_message_seq, created_at)
               VALUES (?, ?, ?, ?, ?, ?, 'INVESTIGATE', 'QUEUED', 0, 0, ?, ?)""",
            (run_id, identity.tenant_id, task_id, session_id, command_id, message_id, sequence, now),
        )
        if assistant_core:
            from opspilot.domain.assistant import register
            connection.execute("UPDATE task_runs SET kind='CHAT_READONLY' WHERE run_id=?", (run_id,))
            register(connection, run_id)
        connection.execute(
            """INSERT INTO worker_retry_state (run_id, retry_count, max_retries, updated_at)
               VALUES (?, 0, 3, ?)""",
            (run_id, now),
        )
        connection.execute(
            """INSERT INTO task_execution_budgets
               (task_id, tenant_id, active_elapsed_ms, active_started_at, heartbeat_at,
                deadline_ms, deadline_reached_at, updated_at, policy_version,
                model_limit, mcp_limit, aux_provider_limit)
               VALUES (?, ?, 0, NULL, NULL, ?, NULL, ?, ?, ?, ?, ?)""",
            (task_id, identity.tenant_id, deadline_ms, now,
             "CONTUX_S3_V1" if service_id == "orders-async-demo" else "LEGACY_V1",
             24 if service_id == "orders-async-demo" else 8,
             18 if service_id == "orders-async-demo" else 6,
             8 if service_id == "orders-async-demo" else None),
        )
        _insert_outbox(
            connection, identity.tenant_id, task_id, session_id, "COMMAND", command_id,
            "TASK_CREATED", {"command_id": command_id, "message_id": message_id, "run_id": run_id,
                             "task_id": task_id, "status": "QUEUED"},
        )
        _insert_outbox(
            connection, identity.tenant_id, task_id, session_id, "COMMAND", command_id,
            "MESSAGE_ACCEPTED", {"command_id": command_id, "message_id": message_id, "run_id": run_id,
                                 "sequence": sequence, "input_kind": "CHAT_READONLY",
                                 "application_state": "RECEIVED_NOT_APPLIED"},
        )
        connection.execute("UPDATE sessions SET updated_at = ? WHERE session_id = ?", (now, session_id))
    return result


def admit_task_message(
    path: str | Path,
    identity: TrustedIdentity,
    *,
    session_id: str,
    task_id: str | None,
    input_kind: MessageKind,
    body: str,
    idempotency_key: str,
    expected_control_revision: int | None = None,
    update_proposal_id: str | None = None,
    defer_task_chat_until_classified: bool = False,
    assistant_core: bool = False,
) -> dict[str, object]:
    if input_kind not in {"CHAT_READONLY", "CORRECT_TASK_INPUT"}:
        raise ValueError("Unsupported task message kind.")
    if not idempotency_key.strip() or len(idempotency_key) > 200:
        raise ValueError("A non-empty idempotency key of at most 200 characters is required.")
    if not isinstance(body, str) or not body.strip():
        raise ValueError("Message body must be non-empty text.")
    if task_id is None and input_kind != "CHAT_READONLY":
        raise TaskControlError("CORRECTION_REQUIRES_TASK")
    if expected_control_revision is not None and (
        input_kind != "CORRECT_TASK_INPUT" or expected_control_revision < 0
    ):
        raise TaskControlError("INVALID_UPDATE_PROPOSAL")
    if update_proposal_id is not None and (
        input_kind != "CORRECT_TASK_INPUT" or expected_control_revision is None
    ):
        raise TaskControlError("INVALID_UPDATE_PROPOSAL")
    if defer_task_chat_until_classified and (task_id is None or input_kind != "CHAT_READONLY"):
        raise TaskControlError("INVALID_CHAT_ROUTE_DEFERRAL")
    command_kind = input_kind
    target_ref = task_id or session_id
    request = {
        "command_kind": command_kind,
        "target_ref": target_ref,
        "session_id": session_id,
        "task_id": task_id,
        "body": body,
    }
    if assistant_core:
        if input_kind != "CHAT_READONLY" or defer_task_chat_until_classified:
            raise TaskControlError("ASSISTANT_ADMISSION_INVALID")
        request["execution_core"] = "ASSISTANT_V1"
    if update_proposal_id is not None:
        request["expected_control_revision"] = expected_control_revision
        request["update_proposal_id"] = update_proposal_id
    if defer_task_chat_until_classified:
        request["defer_task_chat_until_classified"] = True
    request_digest = _digest(request)
    with connect(path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        _verify_identity(connection, identity)
        duplicate = _find_idempotent_command(
            connection, identity, idempotency_key, command_kind, target_ref, request_digest
        )
        if duplicate is not None:
            return duplicate
        session = connection.execute(
            "SELECT * FROM sessions WHERE session_id = ? AND tenant_id = ? AND owner_id = ?",
            (session_id, identity.tenant_id, identity.actor_id),
        ).fetchone()
        if session is None:
            raise TaskControlError("SESSION_SCOPE_DENIED")
        control: sqlite3.Row | None = None
        binding: sqlite3.Row | None = None
        if task_id is not None:
            binding = _require_support_owner(connection, identity, task_id)
            linked = connection.execute(
                "SELECT 1 FROM session_task_links WHERE session_id = ? AND task_id = ? AND tenant_id = ?",
                (session_id, task_id, identity.tenant_id),
            ).fetchone()
            if linked is None:
                raise TaskControlError("SESSION_TASK_LINK_REQUIRED")
            control = _control(connection, identity.tenant_id, task_id)
            if input_kind == "CORRECT_TASK_INPUT":
                if str(control["terminal_state"]) != "ACTIVE":
                    raise TaskControlError("TASK_ABORTED")
                if _is_business_complete(connection, identity.tenant_id, task_id):
                    raise TaskControlError("TASK_ALREADY_TERMINAL")
                if update_proposal_id is not None:
                    proposal = connection.execute(
                        """SELECT * FROM investigation_update_assessments
                           WHERE assessment_id = ? AND tenant_id = ? AND actor_id = ? AND task_id = ?""",
                        (update_proposal_id, identity.tenant_id, identity.actor_id, task_id),
                    ).fetchone()
                    if proposal is None or str(proposal["intent"] or "") != "CRITICAL_CORRECTION":
                        raise TaskControlError("UPDATE_PROPOSAL_NOT_FOUND")
                    if str(proposal["operation_id"]) != idempotency_key:
                        raise TaskControlError("IDEMPOTENCY_KEY_MISMATCH")
                    if int(proposal["expected_control_revision"]) != expected_control_revision:
                        raise TaskControlError("TASK_CONTROL_STALE")
                    if str(proposal["status"]) != "PENDING_CONFIRMATION":
                        raise TaskControlError("UPDATE_PROPOSAL_ALREADY_RESOLVED")
                    source = connection.execute(
                        """SELECT body, body_digest FROM messages WHERE message_id = ? AND task_id = ?
                           AND tenant_id = ? AND session_id = ? AND input_kind = 'CHAT_READONLY'
                           AND role = 'USER'""",
                        (proposal["source_message_id"], task_id, identity.tenant_id, session_id),
                    ).fetchone()
                    if source is None or str(source["body"]) != body or str(source["body_digest"]) != str(proposal["source_digest"]):
                        raise TaskControlError("UPDATE_SOURCE_MESSAGE_INVALID")
                    if int(control["control_revision"]) != expected_control_revision:
                        connection.execute(
                            """UPDATE investigation_update_assessments SET status = 'STALE', completed_at = ?
                               WHERE assessment_id = ? AND status = 'PENDING_CONFIRMATION'""",
                            (_utc_now(), update_proposal_id),
                        )
                        return {
                            "status": "REJECTED", "error_code": "TASK_CONTROL_STALE",
                            "proposal_id": update_proposal_id,
                            "control_revision": int(control["control_revision"]),
                        }
                elif expected_control_revision is not None and int(control["control_revision"]) != expected_control_revision:
                    raise TaskControlError("TASK_CONTROL_STALE")
        seq = int(connection.execute(
            "SELECT COALESCE(MAX(sequence), 0) + 1 FROM messages WHERE session_id = ?", (session_id,)
        ).fetchone()[0])
        message_id = f"message-{uuid.uuid4()}"
        command_id = f"command-{uuid.uuid4()}"
        run_id = f"run-{uuid.uuid4()}"
        now = _utc_now()
        body_digest = hashlib.sha256(body.encode("utf-8")).hexdigest()
        if input_kind == "CORRECT_TASK_INPUT":
            assert control is not None and task_id is not None
            new_revision = int(control["control_revision"]) + 1
            connection.execute(
                """UPDATE task_controls SET control_revision = ?, pending_critical_message_seq = ?,
                          changed_at = ?, changed_by = ?, reason = 'critical_input_received'
                   WHERE task_id = ? AND tenant_id = ?""",
                (new_revision, seq, now, identity.actor_id, task_id, identity.tenant_id),
            )
            _invalidate_plans_in_transaction(
                connection, identity.tenant_id, task_id, identity.actor_id, "critical_input_received"
            )
            connection.execute("UPDATE task_bindings SET status = 'WAITING_INPUT' WHERE task_id = ?", (task_id,))
            stale_runs = connection.execute(
                """SELECT run_id, session_id, tenant_id FROM task_runs
                   WHERE task_id = ? AND kind != 'CHAT_READONLY'
                     AND status IN ('QUEUED', 'RUNNING', 'INTERRUPTED_RECOVERABLE')""",
                (task_id,),
            ).fetchall()
            for stale_run in stale_runs:
                connection.execute(
                    """UPDATE task_runs SET status = 'BLOCKED', ended_at = ?, blocked_reason = 'TASK_CONTROL_STALE'
                       WHERE run_id = ? AND status IN ('QUEUED', 'RUNNING', 'INTERRUPTED_RECOVERABLE')""",
                    (now, stale_run["run_id"]),
                )
                _insert_outbox(
                    connection, str(stale_run["tenant_id"]), task_id, str(stale_run["session_id"]),
                    "RUN", str(stale_run["run_id"]), "RUN_STATUS_BLOCKED",
                    {"run_id": str(stale_run["run_id"]), "run_status": "BLOCKED",
                     "reason_code": "TASK_CONTROL_STALE"},
                )
            expected_revision = new_revision
            run_kind = "INVESTIGATE"
        else:
            expected_revision = int(control["control_revision"]) if control is not None else None
            run_kind = "CHAT_READONLY"
        result = {
            "status": "ACCEPTED",
            "command_id": command_id,
            "message_id": message_id,
            "run_id": run_id,
            "session_id": session_id,
            "task_id": task_id,
            "sequence": seq,
            "input_kind": input_kind,
            "request_digest": request_digest,
            "expected_control_revision": expected_revision,
            "application_state": "RECEIVED_NOT_APPLIED" if input_kind == "CORRECT_TASK_INPUT" else "NOT_APPLICABLE",
        }
        _record_command(
            connection, command_id=command_id, identity=identity, command_kind=command_kind,
            target_ref=target_ref, idempotency_key=idempotency_key, request_digest=request_digest,
            accepted_status="ACCEPTED", result=result, message_id=message_id, run_id=run_id,
        )
        connection.execute(
            """INSERT INTO messages
               (message_id, tenant_id, session_id, task_id, sequence, role, input_kind, body,
                body_digest, command_id, created_at)
               VALUES (?, ?, ?, ?, ?, 'USER', ?, ?, ?, ?, ?)""",
            (message_id, identity.tenant_id, session_id, task_id, seq, input_kind,
             body, body_digest, command_id, now),
        )
        connection.execute(
            """INSERT INTO task_runs
               (run_id, tenant_id, task_id, session_id, command_id, source_message_id,
                kind, status, control_revision_at_start, expected_control_revision,
                consumed_message_seq, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, 'QUEUED', ?, ?, ?, ?)""",
            (run_id, identity.tenant_id, task_id, session_id, command_id, message_id,
             run_kind, expected_revision, expected_revision, seq, now),
        )
        if assistant_core:
            from opspilot.domain.assistant import register
            register(connection, run_id)
        if defer_task_chat_until_classified:
            connection.execute(
                "UPDATE task_runs SET blocked_reason='UPDATE_CLASSIFICATION_PENDING' WHERE run_id=? AND status='QUEUED'",
                (run_id,),
            )
        if update_proposal_id is not None:
            proposal_source = connection.execute(
                "SELECT source_message_id FROM investigation_update_assessments WHERE assessment_id=?",
                (update_proposal_id,),
            ).fetchone()
            updated = connection.execute(
                """UPDATE investigation_update_assessments SET status = 'CONFIRMED',
                   correction_message_id = ?, investigation_run_id = ?, confirmed_at = ?, completed_at = ?
                   WHERE assessment_id = ? AND tenant_id = ? AND actor_id = ? AND task_id = ?
                     AND status = 'PENDING_CONFIRMATION'""",
                (message_id, run_id, now, now, update_proposal_id,
                 identity.tenant_id, identity.actor_id, task_id),
            )
            if updated.rowcount != 1:
                raise TaskControlError("UPDATE_PROPOSAL_ALREADY_RESOLVED")
            if proposal_source is not None:
                stale_chat_run = connection.execute(
                    """SELECT run_id FROM task_runs WHERE source_message_id=? AND task_id=?
                       AND tenant_id=? AND kind='CHAT_READONLY' AND status='QUEUED'
                       AND blocked_reason IN ('UPDATE_CLASSIFICATION_PENDING','UPDATE_CONFIRMATION_PENDING')""",
                    (str(proposal_source["source_message_id"]), task_id, identity.tenant_id),
                ).fetchone()
                stale_chat = connection.execute(
                    """UPDATE task_runs SET status='BLOCKED',blocked_reason='CORRECTION_CONFIRMED',ended_at=?
                       WHERE source_message_id=? AND kind='CHAT_READONLY' AND status='QUEUED'
                         AND blocked_reason IN ('UPDATE_CLASSIFICATION_PENDING','UPDATE_CONFIRMATION_PENDING')""",
                    (now, str(proposal_source["source_message_id"])),
                )
                if stale_chat.rowcount and stale_chat_run is not None:
                    stale_chat_id = str(stale_chat_run["run_id"])
                    _insert_outbox(
                        connection, identity.tenant_id, task_id, session_id, "RUN", stale_chat_id,
                        "RUN_STATUS_BLOCKED",
                        {"run_id": stale_chat_id, "run_status": "BLOCKED", "reason_code": "CORRECTION_CONFIRMED"},
                    )
        if input_kind == "CHAT_READONLY":
            connection.execute(
                """INSERT INTO worker_retry_state (run_id, retry_count, max_retries, updated_at)
                   VALUES (?, 0, 3, ?)""",
                (run_id, now),
            )
        _insert_outbox(
            connection, identity.tenant_id, task_id, session_id, "COMMAND", command_id,
            "MESSAGE_ACCEPTED",
            {"command_id": command_id, "message_id": message_id, "run_id": run_id,
             "sequence": seq, "input_kind": input_kind, "application_state": result["application_state"]},
        )
        connection.execute("UPDATE sessions SET updated_at = ? WHERE session_id = ?", (now, session_id))
    return result


def create_readonly_followup_run_in_transaction(
    connection: sqlite3.Connection,
    identity: TrustedIdentity,
    *,
    task_id: str,
    session_id: str,
    source_message_id: str,
    source_digest: str,
    expected_control_revision: int,
) -> dict[str, object]:
    """Persist a same-Task read-only Investigator Run from an accepted chat message.

    The caller owns the surrounding Domain write transaction so the assessment,
    Run, provenance row, retry state, and outbox event commit atomically.
    """
    _verify_identity(connection, identity)
    _require_support_owner(connection, identity, task_id)
    session = connection.execute(
        "SELECT owner_id FROM sessions WHERE session_id=? AND tenant_id=?",
        (session_id, identity.tenant_id),
    ).fetchone()
    if session is None or str(session["owner_id"]) != identity.actor_id:
        raise TaskControlError("SESSION_SCOPE_DENIED")
    source = connection.execute(
        """SELECT sequence,body_digest FROM messages
           WHERE message_id=? AND task_id=? AND tenant_id=? AND session_id=?
             AND role='USER' AND input_kind='CHAT_READONLY'""",
        (source_message_id, task_id, identity.tenant_id, session_id),
    ).fetchone()
    if source is None or str(source["body_digest"]) != source_digest:
        raise TaskControlError("UPDATE_SOURCE_MESSAGE_INVALID")
    control = _control(connection, identity.tenant_id, task_id)
    if str(control["terminal_state"]) != "ACTIVE":
        raise TaskControlError("TASK_ABORTED")
    if control["pending_critical_message_seq"] is not None:
        raise TaskControlError("TASK_INPUT_PENDING")
    if int(control["control_revision"]) != expected_control_revision:
        raise TaskControlError("TASK_CONTROL_STALE")
    existing = connection.execute(
        """SELECT run_id,source_digest,expected_control_revision FROM c1_readonly_followup_runs
           WHERE tenant_id=? AND task_id=? AND source_message_id=?""",
        (identity.tenant_id, task_id, source_message_id),
    ).fetchone()
    if existing is not None:
        if (
            str(existing["source_digest"]) != source_digest
            or int(existing["expected_control_revision"]) != expected_control_revision
        ):
            raise TaskControlError("IDEMPOTENCY_KEY_MISMATCH")
        return {"run_id": str(existing["run_id"]), "replayed": True}

    active = connection.execute(
        """SELECT run_id FROM task_runs WHERE task_id=? AND status='RUNNING'
           AND kind!='CHAT_READONLY' LIMIT 1""",
        (task_id,),
    ).fetchone()
    if active is not None:
        raise TaskRunBusy()
    run_id = f"run-c1-followup-{uuid.uuid4()}"
    command_id = f"command-c1-followup-{uuid.uuid4()}"
    now = _utc_now()
    sequence = int(source["sequence"])
    connection.execute(
        """INSERT INTO task_runs
           (run_id,tenant_id,task_id,session_id,command_id,source_message_id,kind,status,
          control_revision_at_start,expected_control_revision,consumed_message_seq,applied_critical_message_seq,created_at)
         VALUES (?,?,?,?,?,?,'INVESTIGATE','QUEUED',?,?,?,?,?)""",
        (run_id, identity.tenant_id, task_id, session_id, command_id, source_message_id,
         expected_control_revision, expected_control_revision, sequence, int(control["applied_critical_message_seq"]), now),
    )
    connection.execute(
        """INSERT INTO c1_readonly_followup_runs
           (run_id,tenant_id,task_id,session_id,source_message_id,source_digest,
            expected_control_revision,created_at)
           VALUES (?,?,?,?,?,?,?,?)""",
        (run_id, identity.tenant_id, task_id, session_id, source_message_id,
         source_digest, expected_control_revision, now),
    )
    connection.execute(
        """INSERT INTO worker_retry_state (run_id,retry_count,max_retries,updated_at)
           VALUES (?,0,3,?)""",
        (run_id, now),
    )
    _insert_outbox(
        connection, identity.tenant_id, task_id, session_id, "RUN", run_id, "RUN_QUEUED",
        {"run_id": run_id, "run_kind": "INVESTIGATE", "execution_mode": "READONLY_FOLLOWUP",
         "source_message_id": source_message_id, "control_revision": expected_control_revision},
    )
    return {"run_id": run_id, "replayed": False}


def persist_readonly_followup_result(
    path: str | Path,
    identity: TrustedIdentity,
    run_id: str,
    *,
    result_state: str,
    answer_text: str,
    source_refs: list[dict[str, object]],
    result: dict[str, object],
    reason_code: str | None = None,
) -> dict[str, object]:
    """Freeze a readonly run's user-facing answer and its auditable source refs."""
    if result_state not in {"ANSWERED", "PARTIAL", "NOT_COMPLETED"}:
        raise TaskControlError("READONLY_RESULT_STATE_INVALID")
    if not isinstance(answer_text, str) or len(answer_text) > 20000:
        raise TaskControlError("READONLY_RESULT_INVALID")
    if not isinstance(source_refs, list) or any(not isinstance(item, dict) for item in source_refs):
        raise TaskControlError("READONLY_RESULT_SOURCES_INVALID")
    serialized_refs = json.dumps(source_refs, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    serialized_result = json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    result_digest = _digest({
        "run_id": run_id, "result_state": result_state, "answer_text": answer_text,
        "source_refs_json": serialized_refs, "result_json": serialized_result,
        "reason_code": reason_code,
    })
    with connect(path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        _verify_identity(connection, identity)
        row = connection.execute(
            """SELECT f.*,r.status AS run_status,r.kind AS run_kind,
                      r.tenant_id AS run_tenant_id,r.task_id AS run_task_id,
                      r.session_id AS run_session_id,r.source_message_id AS run_source_message_id,
                      r.consumed_message_seq AS run_consumed_message_seq,
                      r.expected_control_revision AS run_expected_control_revision
               FROM c1_readonly_followup_runs f JOIN task_runs r ON r.run_id=f.run_id
               WHERE f.run_id=? AND f.tenant_id=?""",
            (run_id, identity.tenant_id),
        ).fetchone()
        if row is None:
            raise TaskControlError("READONLY_FOLLOWUP_NOT_FOUND")
        _require_support_owner(connection, identity, str(row["task_id"]))
        if (
            str(row["run_kind"]) != "INVESTIGATE"
            or str(row["run_tenant_id"]) != str(row["tenant_id"])
            or str(row["run_task_id"]) != str(row["task_id"])
            or str(row["run_session_id"]) != str(row["session_id"])
            or str(row["run_source_message_id"]) != str(row["source_message_id"])
        ):
            raise TaskControlError("READONLY_FOLLOWUP_RUN_INVALID")
        if int(row["run_expected_control_revision"]) != int(row["expected_control_revision"]):
            raise TaskControlError("TASK_CONTROL_STALE")
        source = connection.execute(
            """SELECT body_digest,sequence FROM messages WHERE message_id=? AND task_id=?
               AND tenant_id=? AND session_id=? AND role='USER' AND input_kind='CHAT_READONLY'""",
            (row["source_message_id"], row["task_id"], identity.tenant_id, row["session_id"]),
        ).fetchone()
        if (
            source is None or str(source["body_digest"]) != str(row["source_digest"])
            or int(source["sequence"]) != int(row["run_consumed_message_seq"])
        ):
            raise TaskControlError("UPDATE_SOURCE_MESSAGE_INVALID")
        existing_digest = row["result_digest"]
        if existing_digest:
            if str(existing_digest) != result_digest:
                raise TaskControlError("READONLY_RESULT_CONFLICT")
            return {"run_id": run_id, "result_state": str(row["result_state"]), "result_digest": result_digest, "replayed": True}
        if str(row["run_status"]) != "RUNNING":
            raise TaskControlError("TASK_RUN_NOT_ACTIVE")
        control = _control(connection, identity.tenant_id, str(row["task_id"]))
        if (
            str(control["terminal_state"]) != "ACTIVE"
            or control["pending_critical_message_seq"] is not None
            or int(control["control_revision"]) != int(row["expected_control_revision"])
        ):
            raise TaskControlError("TASK_CONTROL_STALE")
        now = _utc_now()
        connection.execute(
            """UPDATE c1_readonly_followup_runs SET result_state=?,answer_text=?,source_refs_json=?,
               result_json=?,result_digest=?,reason_code=?,completed_at=? WHERE run_id=? AND result_digest IS NULL""",
            (result_state, answer_text, serialized_refs, serialized_result, result_digest,
             reason_code, now, run_id),
        )
    return {"run_id": run_id, "result_state": result_state, "result_digest": result_digest, "replayed": False}


def abort_task(
    path: str | Path,
    identity: TrustedIdentity,
    *,
    task_id: str,
    reason: str,
    idempotency_key: str,
) -> dict[str, object]:
    if not reason.strip():
        raise ValueError("An abort reason is required.")
    if not idempotency_key.strip() or len(idempotency_key) > 200:
        raise ValueError("A non-empty idempotency key of at most 200 characters is required.")
    request = {"command_kind": "ABORT_TASK", "target_ref": task_id, "reason": reason}
    request_digest = _digest(request)
    with connect(path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        _verify_identity(connection, identity)
        binding = _require_support_owner(connection, identity, task_id)
        duplicate = _find_idempotent_command(
            connection, identity, idempotency_key, "ABORT_TASK", task_id, request_digest
        )
        if duplicate is not None:
            return duplicate
        control = _control(connection, str(binding["tenant_id"]), task_id)
        command_id = f"command-{uuid.uuid4()}"
        now = _utc_now()
        if str(control["terminal_state"]) != "ACTIVE" or _is_business_complete(connection, str(binding["tenant_id"]), task_id):
            result = {
                "status": "REJECTED",
                "error_code": "TASK_ALREADY_TERMINAL",
                "command_id": command_id,
                "task_id": task_id,
                "control_revision": int(control["control_revision"]),
            }
            _record_command(
                connection, command_id=command_id, identity=identity, command_kind="ABORT_TASK",
                target_ref=task_id, idempotency_key=idempotency_key, request_digest=request_digest,
                accepted_status="REJECTED", error_code="TASK_ALREADY_TERMINAL", result=result,
            )
            _insert_outbox(connection, identity.tenant_id, task_id, None, "COMMAND", command_id,
                           "COMMAND_REJECTED", {"error_code": "TASK_ALREADY_TERMINAL"})
            return result
        new_revision = int(control["control_revision"]) + 1
        _invalidate_plans_in_transaction(
            connection, identity.tenant_id, task_id, identity.actor_id, "task_aborted"
        )
        connection.execute(
            """UPDATE task_controls SET terminal_state = 'ABORTED', control_revision = ?,
                      pending_critical_message_seq = NULL, changed_at = ?, changed_by = ?, reason = ?
               WHERE task_id = ? AND tenant_id = ?""",
            (new_revision, now, identity.actor_id, reason.strip()[:500], task_id, identity.tenant_id),
        )
        active_runs = connection.execute(
            """SELECT run_id, session_id, tenant_id FROM task_runs
               WHERE task_id = ? AND kind != 'CHAT_READONLY'
                 AND status IN ('QUEUED', 'RUNNING', 'INTERRUPTED_RECOVERABLE')""",
            (task_id,),
        ).fetchall()
        for active_run in active_runs:
            connection.execute(
                """UPDATE task_runs SET status = 'BLOCKED', ended_at = ?, blocked_reason = 'TASK_ABORTED'
                   WHERE run_id = ? AND status IN ('QUEUED', 'RUNNING', 'INTERRUPTED_RECOVERABLE')""",
                (now, active_run["run_id"]),
            )
            _insert_outbox(
                connection, str(active_run["tenant_id"]), task_id, str(active_run["session_id"]),
                "RUN", str(active_run["run_id"]), "RUN_STATUS_BLOCKED",
                {"run_id": str(active_run["run_id"]), "run_status": "BLOCKED",
                 "reason_code": "TASK_ABORTED"},
            )
        connection.execute("UPDATE task_bindings SET status = 'ABORTED' WHERE task_id = ?", (task_id,))
        result = {
            "status": "ACCEPTED",
            "command_id": command_id,
            "task_id": task_id,
            "terminal_state": "ABORTED",
            "control_revision": new_revision,
            "reason": reason.strip()[:500],
        }
        _record_command(
            connection, command_id=command_id, identity=identity, command_kind="ABORT_TASK",
            target_ref=task_id, idempotency_key=idempotency_key, request_digest=request_digest,
            accepted_status="ACCEPTED", result=result,
        )
        _insert_outbox(connection, identity.tenant_id, task_id, None, "COMMAND", command_id,
                       "TASK_ABORTED", {"command_id": command_id, "control_revision": new_revision})
    return result


CHAT_CLASSIFICATION_ROUTE_TIMEOUT_SECONDS = 90


def _release_stale_classification_routes(connection: sqlite3.Connection) -> None:
    """Resolve abandoned task-chat routing while preserving confirmed user decisions."""
    stale = connection.execute(
        """SELECT r.run_id,r.tenant_id,r.task_id,r.session_id,a.assessment_id,
                  a.status AS assessment_status,a.follow_up_action,a.investigation_run_id
           FROM task_runs r LEFT JOIN investigation_update_assessments a
             ON a.source_message_id=r.source_message_id AND a.task_id=r.task_id AND a.tenant_id=r.tenant_id
           WHERE r.kind='CHAT_READONLY' AND r.task_id IS NOT NULL AND r.status='QUEUED'
             AND r.blocked_reason='UPDATE_CLASSIFICATION_PENDING'
             AND julianday('now') >= julianday(r.created_at, ?)""",
        (f"+{CHAT_CLASSIFICATION_ROUTE_TIMEOUT_SECONDS} seconds",),
    ).fetchall()
    for row in stale:
        run_id = str(row["run_id"])
        assessment_status = str(row["assessment_status"] or "")
        now = _utc_now()
        if assessment_status == "ASSESSING":
            connection.execute(
                """UPDATE investigation_update_assessments SET status='FAILED',
                   failure_code='CLASSIFICATION_ROUTE_TIMEOUT',completed_at=?
                   WHERE assessment_id=? AND status='ASSESSING'""",
                (now, str(row["assessment_id"])),
            )
            assessment_status = "FAILED"
        if assessment_status == "PENDING_CONFIRMATION":
            connection.execute(
                "UPDATE task_runs SET blocked_reason='UPDATE_CONFIRMATION_PENDING' WHERE run_id=? AND status='QUEUED'",
                (run_id,),
            )
            continue
        if assessment_status == "CONFIRMED":
            reason, status = "CORRECTION_CONFIRMED", "BLOCKED"
        elif (
            assessment_status == "NO_UPDATE"
            and str(row["follow_up_action"] or "EXPLAIN") == "INVESTIGATE"
            and row["investigation_run_id"]
        ):
            reason, status = "FOLLOWUP_ROUTED_TO_INVESTIGATOR", "BLOCKED"
        else:
            reason, status = "CLASSIFICATION_ROUTE_TIMEOUT_FALLBACK", "QUEUED"
        if status == "BLOCKED":
            connection.execute(
                """UPDATE task_runs SET status='BLOCKED',blocked_reason=?,ended_at=?
                   WHERE run_id=? AND status='QUEUED'""",
                (reason, now, run_id),
            )
        else:
            connection.execute(
                "UPDATE task_runs SET blocked_reason=NULL WHERE run_id=? AND status='QUEUED'",
                (run_id,),
            )
        _insert_outbox(
            connection, str(row["tenant_id"]), str(row["task_id"]), str(row["session_id"]),
            "RUN", run_id, "CHAT_ROUTE_RESOLVED",
            {"run_id": run_id, "run_status": status, "reason_code": reason},
        )


def claim_task_run(path: str | Path, identity: TrustedIdentity, run_id: str) -> dict[str, object]:
    with connect(path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        _verify_identity(connection, identity)
        _release_stale_classification_routes(connection)
        run = connection.execute(
            "SELECT * FROM task_runs WHERE run_id = ? AND tenant_id = ?",
            (run_id, identity.tenant_id),
        ).fetchone()
        if run is None:
            raise TaskControlError("TASK_RUN_NOT_FOUND")
        session = connection.execute(
            "SELECT owner_id FROM sessions WHERE session_id = ? AND tenant_id = ?",
            (run["session_id"], identity.tenant_id),
        ).fetchone()
        if session is None or str(session["owner_id"]) != identity.actor_id or identity.role != "SUPPORT":
            raise TaskControlError("TASK_RUN_SCOPE_DENIED")
        resumable_chat = str(run["kind"]) == "CHAT_READONLY" and str(run["status"]) == "INTERRUPTED_RECOVERABLE"
        if str(run["status"]) != "QUEUED" and not resumable_chat:
            raise TaskControlError("TASK_RUN_NOT_QUEUED")
        if str(run["kind"]) == "CHAT_READONLY" and str(run["blocked_reason"] or "") in {
            "UPDATE_CLASSIFICATION_PENDING", "UPDATE_CONFIRMATION_PENDING",
        }:
            raise TaskControlError("UPDATE_CLASSIFICATION_PENDING")
        if str(run["kind"]) != "CHAT_READONLY":
            if run["task_id"] is None:
                raise TaskControlError("TASK_REQUIRED_FOR_BUSINESS_RUN")
            control = _control(connection, identity.tenant_id, str(run["task_id"]))
            if str(control["terminal_state"]) != "ACTIVE":
                raise TaskControlError("TASK_ABORTED")
            expected_revision = run["expected_control_revision"]
            if expected_revision is None or int(control["control_revision"]) != int(expected_revision):
                raise TaskControlError("TASK_CONTROL_STALE")
            if (
                control["pending_critical_message_seq"] is not None
                and int(run["consumed_message_seq"]) < int(control["pending_critical_message_seq"])
            ):
                raise TaskControlError("TASK_INPUT_PENDING")
            active = connection.execute(
                """SELECT run_id FROM task_runs WHERE task_id = ? AND status = 'RUNNING'
                   AND kind != 'CHAT_READONLY' LIMIT 1""",
                (run["task_id"],),
            ).fetchone()
            if active is not None:
                raise TaskRunBusy()
            if str(run["kind"]) == "APPROVAL_RESUME":
                _validate_approval_resume_in_transaction(connection, run)
        now = _utc_now()
        if resumable_chat:
            connection.execute(
                """UPDATE task_runs SET status = 'RUNNING', started_at = COALESCE(started_at, ?),
                          ended_at = NULL, blocked_reason = NULL
                   WHERE run_id = ? AND status = 'INTERRUPTED_RECOVERABLE'""",
                (now, run_id),
            )
        else:
            connection.execute(
                "UPDATE task_runs SET status = 'RUNNING', started_at = ? WHERE run_id = ? AND status = 'QUEUED'",
                (now, run_id),
            )
        current = connection.execute("SELECT * FROM task_runs WHERE run_id = ?", (run_id,)).fetchone()
        return {key: current[key] for key in current.keys()}


def resume_task_run(path: str | Path, identity: TrustedIdentity, run_id: str) -> dict[str, object]:
    """Reacquire a persisted waiting/recoverable Run after rechecking Task control."""
    with connect(path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        _verify_identity(connection, identity)
        run = connection.execute(
            "SELECT * FROM task_runs WHERE run_id = ? AND tenant_id = ?",
            (run_id, identity.tenant_id),
        ).fetchone()
        if run is None or run["task_id"] is None:
            raise TaskControlError("TASK_RUN_NOT_FOUND")
        session = connection.execute(
            "SELECT owner_id FROM sessions WHERE session_id = ? AND tenant_id = ?",
            (run["session_id"], identity.tenant_id),
        ).fetchone()
        if session is None or str(session["owner_id"]) != identity.actor_id or identity.role != "SUPPORT":
            raise TaskControlError("TASK_RUN_SCOPE_DENIED")
        if str(run["status"]) not in {"WAITING_APPROVAL", "INTERRUPTED_RECOVERABLE"}:
            raise TaskControlError("TASK_RUN_NOT_RESUMABLE")
        task_id = str(run["task_id"])
        control = _control(connection, identity.tenant_id, task_id)
        if str(control["terminal_state"]) != "ACTIVE":
            raise TaskControlError("TASK_ABORTED")
        if control["pending_critical_message_seq"] is not None:
            raise TaskControlError("TASK_INPUT_PENDING")
        expected_revision = run["expected_control_revision"]
        if expected_revision is None or int(control["control_revision"]) != int(expected_revision):
            raise TaskControlError("TASK_CONTROL_STALE")
        if int(run["consumed_message_seq"]) < int(control["applied_critical_message_seq"]):
            raise TaskControlError("TASK_CONTROL_STALE")
        active = connection.execute(
            "SELECT run_id FROM task_runs WHERE task_id = ? AND status = 'RUNNING' AND kind != 'CHAT_READONLY' LIMIT 1",
            (task_id,),
        ).fetchone()
        if active is not None:
            raise TaskRunBusy()
        if str(run["kind"]) == "APPROVAL_RESUME":
            _validate_approval_resume_in_transaction(connection, run)
        connection.execute(
            "UPDATE task_runs SET status = 'RUNNING', ended_at = NULL, blocked_reason = NULL WHERE run_id = ?",
            (run_id,),
        )
        current = connection.execute("SELECT * FROM task_runs WHERE run_id = ?", (run_id,)).fetchone()
        return {key: current[key] for key in current.keys()}


def apply_pending_critical_inputs(
    path: str | Path, identity: TrustedIdentity, run_id: str
) -> dict[str, object]:
    with connect(path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        _verify_identity(connection, identity)
        run = connection.execute(
            "SELECT * FROM task_runs WHERE run_id = ? AND tenant_id = ?",
            (run_id, identity.tenant_id),
        ).fetchone()
        if run is None or run["task_id"] is None or str(run["status"]) != "RUNNING":
            raise TaskControlError("TASK_RUN_NOT_ACTIVE")
        task_id = str(run["task_id"])
        _require_support_owner(connection, identity, task_id)
        control = _control(connection, identity.tenant_id, task_id)
        if str(control["terminal_state"]) != "ACTIVE":
            raise TaskControlError("TASK_ABORTED")
        expected_revision = run["expected_control_revision"]
        if expected_revision is None or int(control["control_revision"]) != int(expected_revision):
            raise TaskControlError("TASK_CONTROL_STALE")
        pending = control["pending_critical_message_seq"]
        if pending is None:
            return {
                "run_id": run_id,
                "task_id": task_id,
                "expected_control_revision": int(control["control_revision"]),
                "applied_critical_message_seq": int(control["applied_critical_message_seq"]),
                "inputs": [],
            }
        pending_seq = int(pending)
        if int(run["consumed_message_seq"]) < pending_seq:
            raise TaskControlError("TASK_INPUT_PENDING")
        rows = connection.execute(
            """SELECT * FROM messages WHERE task_id = ? AND input_kind = 'CORRECT_TASK_INPUT'
               AND application_state = 'RECEIVED_NOT_APPLIED'
               AND sequence > ? AND sequence <= ? ORDER BY sequence""",
            (task_id, int(control["applied_critical_message_seq"]), pending_seq),
        ).fetchall()
        if not rows or int(rows[-1]["sequence"]) != pending_seq:
            raise TaskControlError("TASK_INPUT_INCOMPLETE")
        # The latest accepted correction's Run must consume the entire pending high-water.
        if str(run["source_message_id"]) != str(rows[-1]["message_id"]):
            raise TaskControlError("TASK_CONTROL_STALE")
        now = _utc_now()
        inputs: list[dict[str, object]] = []
        for row in rows:
            message_id = str(row["message_id"])
            digest = str(row["body_digest"])
            connection.execute(
                """UPDATE messages SET application_state = 'APPLIED_TO_RUN', applied_run_id = ?
                   WHERE message_id = ? AND application_state = 'RECEIVED_NOT_APPLIED'""",
                (run_id, message_id),
            )
            connection.execute(
                """INSERT INTO task_run_inputs
                   (message_id, task_id, run_id, input_digest, provenance, consumed_at)
                   VALUES (?, ?, ?, ?, 'USER_INPUT_UNTRUSTED', ?)""",
                (message_id, task_id, run_id, digest, now),
            )
            inputs.append({
                "message_id": message_id,
                "sequence": int(row["sequence"]),
                "body": str(row["body"]),
                "provenance": "USER_INPUT_UNTRUSTED",
                "body_digest": digest,
            })
        next_revision = int(control["control_revision"]) + 1
        connection.execute(
            """UPDATE task_controls SET control_revision = ?, pending_critical_message_seq = NULL,
                      applied_critical_message_seq = ?, changed_at = ?, changed_by = ?,
                      reason = 'critical_inputs_applied_to_run'
               WHERE task_id = ? AND tenant_id = ?""",
            (next_revision, pending_seq, now, identity.actor_id, task_id, identity.tenant_id),
        )
        connection.execute(
            """UPDATE task_runs SET expected_control_revision = ?, applied_critical_message_seq = ?,
                      consumed_message_seq = MAX(consumed_message_seq, ?)
               WHERE run_id = ? AND status = 'RUNNING'""",
            (next_revision, pending_seq, pending_seq, run_id),
        )
        connection.execute("UPDATE task_bindings SET status = 'RUNNING' WHERE task_id = ?", (task_id,))
        _insert_outbox(
            connection, identity.tenant_id, task_id, str(run["session_id"]), "RUN", run_id,
            "CRITICAL_INPUTS_APPLIED",
            {"run_id": run_id, "message_ids": [item["message_id"] for item in inputs],
             "applied_critical_message_seq": pending_seq, "control_revision": next_revision,
             "provenance": "USER_INPUT_UNTRUSTED"},
        )
        return {
            "run_id": run_id,
            "task_id": task_id,
            "expected_control_revision": next_revision,
            "applied_critical_message_seq": pending_seq,
            "inputs": inputs,
        }


def finish_task_run(
    path: str | Path,
    identity: TrustedIdentity,
    run_id: str,
    status: RunStatus,
    *,
    blocked_reason: str | None = None,
) -> dict[str, object]:
    if status not in {"SUCCEEDED", "FAILED", "BLOCKED", "WAITING_INPUT", "WAITING_APPROVAL", "INTERRUPTED_RECOVERABLE"}:
        raise ValueError("Run outcome is not terminal or waiting.")
    with connect(path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        _verify_identity(connection, identity)
        run = connection.execute(
            "SELECT * FROM task_runs WHERE run_id = ? AND tenant_id = ?",
            (run_id, identity.tenant_id),
        ).fetchone()
        if run is None:
            raise TaskControlError("TASK_RUN_NOT_FOUND")
        session = connection.execute(
            "SELECT owner_id FROM sessions WHERE session_id = ? AND tenant_id = ?",
            (run["session_id"], identity.tenant_id),
        ).fetchone()
        if session is None or str(session["owner_id"]) != identity.actor_id:
            raise TaskControlError("TASK_RUN_SCOPE_DENIED")
        if str(run["status"]) == "BLOCKED" and str(run["blocked_reason"] or "").startswith("TASK_"):
            return {key: run[key] for key in run.keys()}
        if str(run["status"]) != "RUNNING":
            raise TaskControlError("TASK_RUN_NOT_ACTIVE")
        now = _utc_now()
        connection.execute(
            "UPDATE task_runs SET status = ?, blocked_reason = ?, ended_at = ? WHERE run_id = ?",
            (status, blocked_reason, now, run_id),
        )
        if _is_readonly_followup(connection, run_id) and status in {"FAILED", "BLOCKED"}:
            _record_readonly_followup_failure_in_transaction(
                connection, run_id, blocked_reason or f"RUN_{status}",
            )
        _insert_outbox(
            connection, identity.tenant_id, str(run["task_id"]) if run["task_id"] is not None else None,
            str(run["session_id"]), "RUN", run_id, f"RUN_STATUS_{status}",
            {"run_id": run_id, "run_status": status, "reason_code": blocked_reason},
        )
        if (
            run["task_id"] is not None
            and str(run["kind"]) != "CHAT_READONLY"
            and not _is_readonly_followup(connection, run_id)
            and status in {"WAITING_INPUT", "WAITING_APPROVAL", "SUCCEEDED", "FAILED", "BLOCKED"}
        ):
            existing_task = connection.execute(
                "SELECT status FROM task_bindings WHERE task_id = ?",
                (run["task_id"],),
            ).fetchone()
            projected = {
                "WAITING_INPUT": "WAITING_INPUT",
                "WAITING_APPROVAL": "WAITING_APPROVAL",
                "SUCCEEDED": "COMPLETED",
                "FAILED": "FAILED",
                "BLOCKED": "BLOCKED",
            }[status]
            if (
                status == "SUCCEEDED" and existing_task is not None
                and str(existing_task["status"]) in {"WAITING_HANDOFF", "INCONCLUSIVE", "NO_ACTION"}
            ):
                # S2 Run completion is not business completion. Preserve the
                # trusted Domain outcome projected by its Gate/Receipt transaction.
                projected = str(existing_task["status"])
            if blocked_reason == "INVESTIGATION_DEADLINE_EXCEEDED":
                projected = "INCONCLUSIVE"
            connection.execute(
                "UPDATE task_bindings SET status = ? WHERE task_id = ? AND status NOT IN ('ABORTED', 'COMPLETED')",
                (projected, run["task_id"]),
            )
        updated = connection.execute("SELECT * FROM task_runs WHERE run_id = ?", (run_id,)).fetchone()
        return {key: updated[key] for key in updated.keys()}


def get_task_run(path: str | Path, identity: TrustedIdentity, run_id: str) -> dict[str, object]:
    with connect(path) as connection:
        _verify_identity(connection, identity)
        row = connection.execute(
            """SELECT r.* FROM task_runs AS r JOIN sessions AS s
               ON s.session_id = r.session_id AND s.tenant_id = r.tenant_id
               WHERE r.run_id = ? AND r.tenant_id = ? AND s.owner_id = ?""",
            (run_id, identity.tenant_id, identity.actor_id),
        ).fetchone()
    if row is None:
        raise TaskControlError("TASK_RUN_SCOPE_DENIED")
    return {key: row[key] for key in row.keys()}


def register_worker_owner(path: str | Path, owner_id: str, process_id: int) -> int:
    """Persist a monotonically fenced local worker owner after acquiring its OS lock."""
    with connect(path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute(
            "SELECT epoch FROM web_worker_state WHERE singleton_id = 1"
        ).fetchone()
        epoch = int(row["epoch"]) + 1 if row is not None else 1
        connection.execute(
            """INSERT INTO web_worker_state (singleton_id, owner_id, process_id, epoch, acquired_at)
               VALUES (1, ?, ?, ?, ?)
               ON CONFLICT(singleton_id) DO UPDATE SET owner_id = excluded.owner_id,
                 process_id = excluded.process_id, epoch = excluded.epoch, acquired_at = excluded.acquired_at""",
            (owner_id, process_id, epoch, _utc_now()),
        )
    return epoch


def _assert_worker_fence(
    connection: sqlite3.Connection, owner_id: str, worker_epoch: int | None = None
) -> sqlite3.Row:
    owner = connection.execute(
        "SELECT owner_id, epoch FROM web_worker_state WHERE singleton_id = 1"
    ).fetchone()
    if (
        owner is None
        or str(owner["owner_id"]) != owner_id
        or (worker_epoch is not None and int(owner["epoch"]) != int(worker_epoch))
    ):
        raise TaskControlError("WORKER_FENCE_STALE")
    return owner


def worker_owner_matches(path: str | Path, owner_id: str, worker_epoch: int | None = None) -> bool:
    with connect(path) as connection:
        owner = connection.execute(
            "SELECT owner_id, epoch FROM web_worker_state WHERE singleton_id = 1"
        ).fetchone()
    return bool(
        owner is not None
        and str(owner["owner_id"]) == owner_id
        and (worker_epoch is None or int(owner["epoch"]) == int(worker_epoch))
    )


def recover_running_task_runs(
    path: str | Path, owner_id: str, worker_epoch: int | None = None
) -> list[str]:
    """After exclusive OS lock acquisition, mark prior-process RUNNING runs recoverable."""
    recovered: list[str] = []
    with connect(path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        _assert_worker_fence(connection, owner_id, worker_epoch)
        rows = connection.execute(
            "SELECT * FROM task_runs WHERE status = 'RUNNING' ORDER BY created_at"
        ).fetchall()
        for run in rows:
            now = _utc_now()
            connection.execute(
                """INSERT OR IGNORE INTO worker_retry_state
                   (run_id, retry_count, max_retries, next_attempt_at, last_error_code, updated_at)
                   VALUES (?, 0, 3, NULL, NULL, ?)""",
                (run["run_id"], now),
            )
            retry = connection.execute(
                "SELECT retry_count, max_retries FROM worker_retry_state WHERE run_id = ?",
                (run["run_id"],),
            ).fetchone()
            retry_count, max_retries = int(retry["retry_count"]), int(retry["max_retries"])
            if retry_count >= max_retries:
                recovered_status, reason_code = "BLOCKED", "WORKER_RETRY_EXHAUSTED"
                next_attempt_at = None
            else:
                retry_count += 1
                delay = max(2, min(30, 2 ** retry_count))
                recovered_status, reason_code = "INTERRUPTED_RECOVERABLE", "WORKER_OWNER_RESTARTED"
                next_attempt_at = connection.execute(
                    "SELECT datetime('now', ?)", (f"+{delay} seconds",)
                ).fetchone()[0]
            connection.execute(
                """UPDATE worker_retry_state SET retry_count = ?, next_attempt_at = ?,
                          last_error_code = ?, updated_at = ? WHERE run_id = ?""",
                (retry_count, next_attempt_at, reason_code, now, run["run_id"]),
            )
            connection.execute(
                """UPDATE task_runs SET status = ?, ended_at = ?, blocked_reason = ?
                   WHERE run_id = ? AND status = 'RUNNING'""",
                (recovered_status, now, reason_code, run["run_id"]),
            )
            if run["kind"] == "CHAT_READONLY":
                connection.execute(
                    "UPDATE chat_attempts SET status = 'INTERRUPTED', error_class = 'WorkerRestarted', completed_at = ? "
                    "WHERE run_id = ? AND status IN ('RESERVED', 'STREAMING')",
                    (now, run["run_id"]),
                )
                connection.execute(
                    "UPDATE context_compression_attempts SET status = 'INTERRUPTED', error_class = 'WorkerRestarted', completed_at = ? "
                    "WHERE run_id = ? AND status = 'RESERVED'",
                    (now, run["run_id"]),
                )
            elif run["task_id"] is not None and not _is_readonly_followup(connection, str(run["run_id"])):
                connection.execute(
                    """UPDATE task_bindings SET status = ?
                       WHERE task_id = ? AND status NOT IN ('ABORTED', 'COMPLETED')""",
                    ("INCONCLUSIVE" if recovered_status == "BLOCKED" else "INTERRUPTED_RECOVERABLE", run["task_id"]),
                )
            _insert_outbox(
                connection, str(run["tenant_id"]),
                str(run["task_id"]) if run["task_id"] is not None else None,
                str(run["session_id"]), "RUN", str(run["run_id"]),
                f"RUN_STATUS_{recovered_status}",
                {"run_id": str(run["run_id"]), "run_status": recovered_status,
                 "reason_code": reason_code},
            )
            recovered.append(str(run["run_id"]))
    return recovered


def mark_run_interrupted_by_worker(
    path: str | Path, owner_id: str, run_id: str, reason: str,
    worker_epoch: int | None = None,
) -> dict[str, object] | None:
    """Fenced worker shutdown/timeout transition; does not touch TaskControl authority."""
    with connect(path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        _assert_worker_fence(connection, owner_id, worker_epoch)
        run = connection.execute("SELECT * FROM task_runs WHERE run_id = ?", (run_id,)).fetchone()
        if run is None or str(run["status"]) != "RUNNING":
            return {key: run[key] for key in run.keys()} if run is not None else None
        now = _utc_now()
        status = "BLOCKED" if reason == "INVESTIGATION_DEADLINE_EXCEEDED" else "INTERRUPTED_RECOVERABLE"
        connection.execute(
            "UPDATE task_runs SET status = ?, ended_at = ?, blocked_reason = ? WHERE run_id = ? AND status = 'RUNNING'",
            (status, now, reason, run_id),
        )
        if status == "BLOCKED" and _is_readonly_followup(connection, run_id):
            _record_readonly_followup_failure_in_transaction(connection, run_id, reason)
        if run["kind"] == "CHAT_READONLY":
            connection.execute(
                "UPDATE chat_attempts SET status = 'INTERRUPTED', error_class = ?, completed_at = ? "
                "WHERE run_id = ? AND status IN ('RESERVED', 'STREAMING')",
                (reason[:100], now, run_id),
            )
            connection.execute(
                "UPDATE context_compression_attempts SET status = 'INTERRUPTED', error_class = ?, completed_at = ? "
                "WHERE run_id = ? AND status = 'RESERVED'",
                (reason[:100], now, run_id),
            )
        elif run["task_id"] is not None and not _is_readonly_followup(connection, run_id):
            task_status = "INCONCLUSIVE" if status == "BLOCKED" else "INTERRUPTED_RECOVERABLE"
            connection.execute(
                """UPDATE task_bindings SET status = ? WHERE task_id = ?
                   AND status NOT IN ('ABORTED', 'COMPLETED')""",
                (task_status, run["task_id"]),
            )
        _insert_outbox(
            connection, str(run["tenant_id"]),
            str(run["task_id"]) if run["task_id"] is not None else None,
            str(run["session_id"]), "RUN", run_id, f"RUN_STATUS_{status}",
            {"run_id": run_id, "run_status": status, "reason_code": reason},
        )
        updated = connection.execute("SELECT * FROM task_runs WHERE run_id = ?", (run_id,)).fetchone()
        return {key: updated[key] for key in updated.keys()}


def schedule_worker_retry(
    path: str | Path, owner_id: str, run_id: str, *, error_code: str,
    base_delay_seconds: int = 2, worker_epoch: int | None = None,
) -> dict[str, object]:
    """Persist bounded retry/backoff for a recoverable Run under the current worker fence."""
    with connect(path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        _assert_worker_fence(connection, owner_id, worker_epoch)
        run = connection.execute("SELECT * FROM task_runs WHERE run_id = ?", (run_id,)).fetchone()
        if run is None:
            raise TaskControlError("TASK_RUN_NOT_FOUND")
        if str(run["status"]) != "INTERRUPTED_RECOVERABLE":
            return {"run_id": run_id, "status": str(run["status"]), "retry_scheduled": False}
        now = _utc_now()
        connection.execute(
            """INSERT OR IGNORE INTO worker_retry_state
               (run_id, retry_count, max_retries, next_attempt_at, last_error_code, updated_at)
               VALUES (?, 0, 3, NULL, NULL, ?)""",
            (run_id, now),
        )
        state = connection.execute("SELECT * FROM worker_retry_state WHERE run_id = ?", (run_id,)).fetchone()
        retries = int(state["retry_count"])
        maximum = int(state["max_retries"])
        if retries >= maximum:
            reason = "WORKER_RETRY_EXHAUSTED"
            connection.execute(
                "UPDATE task_runs SET status = 'BLOCKED', blocked_reason = ?, ended_at = ? WHERE run_id = ?",
                (reason, now, run_id),
            )
            if _is_readonly_followup(connection, run_id):
                _record_readonly_followup_failure_in_transaction(connection, run_id, reason)
            if (
                run["kind"] != "CHAT_READONLY" and run["task_id"] is not None
                and not _is_readonly_followup(connection, run_id)
            ):
                connection.execute(
                    "UPDATE task_bindings SET status = 'INCONCLUSIVE' WHERE task_id = ? AND status NOT IN ('ABORTED', 'COMPLETED')",
                    (run["task_id"],),
                )
            next_time = None
            status = "BLOCKED"
        else:
            retries += 1
            delay = max(1, min(30, base_delay_seconds * (2 ** (retries - 1))))
            connection.execute(
                """UPDATE worker_retry_state SET retry_count = ?,
                          next_attempt_at = datetime('now', ?), last_error_code = ?, updated_at = ?
                   WHERE run_id = ?""",
                (retries, f"+{delay} seconds", error_code[:100], now, run_id),
            )
            next_time = connection.execute(
                "SELECT next_attempt_at FROM worker_retry_state WHERE run_id = ?", (run_id,)
            ).fetchone()[0]
            status = "INTERRUPTED_RECOVERABLE"
        _insert_outbox(
            connection, str(run["tenant_id"]), str(run["task_id"]) if run["task_id"] else None,
            str(run["session_id"]), "RUN", run_id, f"RUN_RETRY_{status}",
            {"run_id": run_id, "run_status": status,
             "reason_code": "WORKER_RETRY_EXHAUSTED" if status == "BLOCKED" else error_code[:100]},
        )
    return {"run_id": run_id, "status": status, "retry_count": retries,
            "max_retries": maximum, "next_attempt_at": next_time, "retry_scheduled": status != "BLOCKED"}


def record_worker_run_failure(
    path: str | Path,
    owner_id: str,
    run_id: str,
    *,
    error_code: str,
    retryable: bool,
    worker_epoch: int | None = None,
    base_delay_seconds: int = 2,
) -> dict[str, object]:
    """Persist one worker-local failure under the current single-instance fence.

    TaskControl and completed business state are rechecked in this transaction so
    stale work cannot overwrite an abort, correction, or committed delivery.
    """
    safe_code = "".join(char for char in error_code.upper() if char.isalnum() or char == "_")[:100]
    safe_code = safe_code or "WORKER_RUN_FAILED"
    with connect(path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        _assert_worker_fence(connection, owner_id, worker_epoch)
        run = connection.execute("SELECT * FROM task_runs WHERE run_id = ?", (run_id,)).fetchone()
        if run is None:
            raise TaskControlError("TASK_RUN_NOT_FOUND")
        current_status = str(run["status"])
        if current_status not in {"QUEUED", "RUNNING", "INTERRUPTED_RECOVERABLE"}:
            return {"run_id": run_id, "status": current_status, "recorded": False}

        final_code = safe_code
        is_expected_control_stop = False
        task_status: str | None = None
        if run["task_id"] is not None and str(run["kind"]) != "CHAT_READONLY":
            binding = connection.execute(
                "SELECT status FROM task_bindings WHERE task_id = ? AND tenant_id = ?",
                (run["task_id"], run["tenant_id"]),
            ).fetchone()
            control = connection.execute(
                "SELECT * FROM task_controls WHERE task_id = ? AND tenant_id = ?",
                (run["task_id"], run["tenant_id"]),
            ).fetchone()
            if binding is not None and str(binding["status"]) == "ABORTED":
                final_code, is_expected_control_stop = "TASK_ABORTED", True
            elif control is not None and str(control["terminal_state"]) != "ACTIVE":
                final_code, is_expected_control_stop = "TASK_ABORTED", True
            elif control is None:
                final_code, is_expected_control_stop = "TASK_CONTROL_MIGRATION_REQUIRED", True
            elif (
                run["expected_control_revision"] is not None
                and int(run["expected_control_revision"]) != int(control["control_revision"])
            ):
                final_code, is_expected_control_stop = "TASK_CONTROL_STALE", True
            elif (
                control["pending_critical_message_seq"] is not None
                and int(run["consumed_message_seq"]) < int(control["pending_critical_message_seq"])
            ):
                final_code, is_expected_control_stop = "TASK_INPUT_PENDING", True
            if binding is not None:
                task_status = str(binding["status"])

        can_retry = retryable and not is_expected_control_stop
        now = _utc_now()
        connection.execute(
            """INSERT OR IGNORE INTO worker_retry_state
               (run_id, retry_count, max_retries, next_attempt_at, last_error_code, updated_at)
               VALUES (?, 0, 3, NULL, NULL, ?)""",
            (run_id, now),
        )
        retry = connection.execute(
            "SELECT retry_count, max_retries FROM worker_retry_state WHERE run_id = ?", (run_id,)
        ).fetchone()
        retry_count = int(retry["retry_count"])
        max_retries = int(retry["max_retries"])
        if can_retry and retry_count < max_retries:
            retry_count += 1
            delay_seconds = max(1, min(30, base_delay_seconds * (2 ** (retry_count - 1))))
            next_attempt_at = connection.execute(
                "SELECT datetime('now', ?)", (f"+{delay_seconds} seconds",)
            ).fetchone()[0]
            status = "INTERRUPTED_RECOVERABLE"
            reason = final_code
            connection.execute(
                """UPDATE worker_retry_state SET retry_count = ?, next_attempt_at = ?,
                          last_error_code = ?, updated_at = ? WHERE run_id = ?""",
                (retry_count, next_attempt_at, final_code, now, run_id),
            )
        else:
            status = "BLOCKED"
            reason = "WORKER_RETRY_EXHAUSTED" if can_retry else final_code
            next_attempt_at = None
            connection.execute(
                """UPDATE worker_retry_state SET next_attempt_at = NULL,
                          last_error_code = ?, updated_at = ? WHERE run_id = ?""",
                (final_code, now, run_id),
            )
        changed = connection.execute(
            """UPDATE task_runs SET status = ?, ended_at = ?, blocked_reason = ?
               WHERE run_id = ? AND status IN ('QUEUED', 'RUNNING', 'INTERRUPTED_RECOVERABLE')""",
            (status, now, reason, run_id),
        ).rowcount
        if changed == 0:
            current = connection.execute("SELECT status FROM task_runs WHERE run_id = ?", (run_id,)).fetchone()
            return {"run_id": run_id, "status": str(current["status"]), "recorded": False}

        if status == "BLOCKED" and _is_readonly_followup(connection, run_id):
            _record_readonly_followup_failure_in_transaction(connection, run_id, reason)

        if (
            not _is_readonly_followup(connection, run_id)
            and task_status not in {None, "ABORTED", "COMPLETED", "WAITING_INPUT", "WAITING_APPROVAL"}
        ):
            projected = "INTERRUPTED_RECOVERABLE" if status == "INTERRUPTED_RECOVERABLE" else "INCONCLUSIVE"
            connection.execute(
                """UPDATE task_bindings SET status = ? WHERE task_id = ? AND tenant_id = ?
                   AND status NOT IN ('ABORTED', 'COMPLETED', 'WAITING_INPUT', 'WAITING_APPROVAL')""",
                (projected, run["task_id"], run["tenant_id"]),
            )
        event_kind = "RUN_RETRY_INTERRUPTED_RECOVERABLE" if status == "INTERRUPTED_RECOVERABLE" else "RUN_STATUS_BLOCKED"
        _insert_outbox(
            connection, str(run["tenant_id"]), str(run["task_id"]) if run["task_id"] else None,
            str(run["session_id"]), "RUN", run_id, event_kind,
            {"run_id": run_id, "run_status": status, "reason_code": reason,
             "attempt": retry_count if can_retry else None,
             "max_attempts": max_retries if can_retry else None},
        )
        return {
            "run_id": run_id, "status": status, "reason_code": reason,
            "retry_count": retry_count, "max_retries": max_retries,
            "next_attempt_at": next_attempt_at, "recorded": True,
        }


def next_worker_run(path: str | Path, excluded_run_ids: tuple[str, ...] = ()) -> dict[str, object] | None:
    # `excluded_run_ids` remains accepted for M1-02 callers, but retries are now
    # governed by persisted backoff so a transient failure cannot be hidden by
    # a process-local set for the lifetime of the worker.
    with connect(path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        _release_stale_classification_routes(connection)
        row = connection.execute(
            """SELECT r.* FROM task_runs AS r
               LEFT JOIN worker_retry_state AS w ON w.run_id = r.run_id
               WHERE r.kind IN ('CHAT_READONLY', 'INVESTIGATE', 'RESUME', 'APPROVAL_RESUME', 'RECONCILE')
                 AND r.status IN ('QUEUED', 'INTERRUPTED_RECOVERABLE')
                 AND COALESCE(r.blocked_reason,'') NOT IN ('UPDATE_CLASSIFICATION_PENDING','UPDATE_CONFIRMATION_PENDING')
                 AND (w.run_id IS NULL OR (w.retry_count <= w.max_retries
                      AND (w.next_attempt_at IS NULL OR w.next_attempt_at <= CURRENT_TIMESTAMP)))
                 AND r.run_id NOT IN (SELECT value FROM json_each(?))
               ORDER BY r.created_at, r.run_id LIMIT 1""",
            (__import__("json").dumps(list(excluded_run_ids)),),
        ).fetchone()
    return {key: row[key] for key in row.keys()} if row is not None else None
