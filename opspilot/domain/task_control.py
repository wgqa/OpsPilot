from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from opspilot.domain.database import connect


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
    connection.execute(
        """INSERT INTO domain_outbox
           (event_id, tenant_id, task_id, session_id, source_kind, source_id,
            event_kind, payload_json, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (f"event-{uuid.uuid4()}", tenant_id, task_id, session_id, source_kind, source_id,
         event_kind, _canonical(payload), _utc_now()),
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


def create_session(path: str | Path, identity: TrustedIdentity) -> dict[str, object]:
    session_id = f"session-{uuid.uuid4()}"
    now = _utc_now()
    with connect(path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        _verify_identity(connection, identity)
        connection.execute(
            "INSERT INTO sessions (session_id, tenant_id, owner_id, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
            (session_id, identity.tenant_id, identity.actor_id, now, now),
        )
    return {"session_id": session_id, "tenant_id": identity.tenant_id, "owner_id": identity.actor_id, "created_at": now}


def admit_task_message(
    path: str | Path,
    identity: TrustedIdentity,
    *,
    session_id: str,
    task_id: str | None,
    input_kind: MessageKind,
    body: str,
    idempotency_key: str,
) -> dict[str, object]:
    if input_kind not in {"CHAT_READONLY", "CORRECT_TASK_INPUT"}:
        raise ValueError("Unsupported task message kind.")
    if not idempotency_key.strip() or len(idempotency_key) > 200:
        raise ValueError("A non-empty idempotency key of at most 200 characters is required.")
    if not isinstance(body, str) or not body.strip():
        raise ValueError("Message body must be non-empty text.")
    if task_id is None and input_kind != "CHAT_READONLY":
        raise TaskControlError("CORRECTION_REQUIRES_TASK")
    command_kind = input_kind
    target_ref = task_id or session_id
    request = {
        "command_kind": command_kind,
        "target_ref": target_ref,
        "session_id": session_id,
        "task_id": task_id,
        "body": body,
    }
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
            connection.execute(
                """UPDATE task_runs SET status = 'BLOCKED', ended_at = ?, blocked_reason = 'TASK_CONTROL_STALE'
                   WHERE task_id = ? AND kind != 'CHAT_READONLY' AND status IN ('QUEUED', 'RUNNING')""",
                (now, task_id),
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
        _insert_outbox(
            connection, identity.tenant_id, task_id, session_id, "COMMAND", command_id,
            "MESSAGE_ACCEPTED",
            {"command_id": command_id, "message_id": message_id, "run_id": run_id,
             "sequence": seq, "input_kind": input_kind, "application_state": result["application_state"]},
        )
        connection.execute("UPDATE sessions SET updated_at = ? WHERE session_id = ?", (now, session_id))
    return result


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
        connection.execute(
            """UPDATE task_runs SET status = 'BLOCKED', ended_at = ?, blocked_reason = 'TASK_ABORTED'
               WHERE task_id = ? AND kind != 'CHAT_READONLY' AND status IN ('QUEUED', 'RUNNING')""",
            (now, task_id),
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


def claim_task_run(path: str | Path, identity: TrustedIdentity, run_id: str) -> dict[str, object]:
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
        if session is None or str(session["owner_id"]) != identity.actor_id or identity.role != "SUPPORT":
            raise TaskControlError("TASK_RUN_SCOPE_DENIED")
        if str(run["status"]) != "QUEUED":
            raise TaskControlError("TASK_RUN_NOT_QUEUED")
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
        now = _utc_now()
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
        if (
            run["task_id"] is not None
            and str(run["kind"]) != "CHAT_READONLY"
            and status in {"WAITING_INPUT", "WAITING_APPROVAL", "SUCCEEDED", "FAILED", "BLOCKED"}
        ):
            projected = {
                "WAITING_INPUT": "WAITING_INPUT",
                "WAITING_APPROVAL": "WAITING_APPROVAL",
                "SUCCEEDED": "COMPLETED",
                "FAILED": "FAILED",
                "BLOCKED": "BLOCKED",
            }[status]
            connection.execute(
                "UPDATE task_bindings SET status = ? WHERE task_id = ? AND status != 'ABORTED'",
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
