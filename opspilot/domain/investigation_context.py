"""Trusted TaskRun input selection for the read-only Investigator prompt."""

from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path
from typing import Any

from opspilot.domain.database import connect
from opspilot.domain.task_control import TaskControlError, assert_task_control_in_transaction


class InvestigationContextInvalid(TaskControlError):
    """The persisted Run inputs no longer match the active TaskControl state."""


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _read_context(connection: sqlite3.Connection, task_id: str, run_id: str) -> dict[str, Any]:
    row = connection.execute(
        """SELECT r.*, b.actor_id AS binding_actor_id, b.service_id, b.integration_id,
                  b.principal_id, b.tenant_id AS binding_tenant_id,
                  s.owner_id, c.terminal_state, c.control_revision,
                  c.pending_critical_message_seq,
                  c.applied_critical_message_seq AS control_applied_critical_message_seq
           FROM task_runs r
           JOIN task_bindings b ON b.task_id = r.task_id AND b.tenant_id = r.tenant_id
           JOIN sessions s ON s.session_id = r.session_id AND s.tenant_id = r.tenant_id
           JOIN task_controls c ON c.task_id = r.task_id AND c.tenant_id = r.tenant_id
           WHERE r.run_id = ? AND r.task_id = ?""",
        (run_id, task_id),
    ).fetchone()
    if row is None:
        raise InvestigationContextInvalid("INVESTIGATION_RUN_CONTEXT_NOT_FOUND")
    if str(row["kind"]) not in {"INVESTIGATE", "RESUME", "APPROVAL_RESUME", "RECONCILE"}:
        raise InvestigationContextInvalid("INVESTIGATION_RUN_KIND_INVALID")
    if str(row["status"]) != "RUNNING":
        raise InvestigationContextInvalid("TASK_RUN_NOT_ACTIVE")
    if str(row["binding_tenant_id"]) != str(row["tenant_id"]) or str(row["owner_id"]) != str(row["binding_actor_id"]):
        raise InvestigationContextInvalid("INVESTIGATION_RUN_OWNER_MISMATCH")
    if str(row["terminal_state"]) != "ACTIVE":
        raise InvestigationContextInvalid("TASK_ABORTED")
    if row["pending_critical_message_seq"] is not None:
        raise InvestigationContextInvalid("TASK_INPUT_PENDING")
    expected_revision = row["expected_control_revision"]
    if expected_revision is None or int(expected_revision) != int(row["control_revision"]):
        raise InvestigationContextInvalid("TASK_CONTROL_STALE")
    applied_highwater = int(row["applied_critical_message_seq"])
    consumed_highwater = int(row["consumed_message_seq"])
    if applied_highwater != int(row["control_applied_critical_message_seq"]):
        raise InvestigationContextInvalid("TASK_INPUT_HIGHWATER_STALE")
    if consumed_highwater < applied_highwater:
        raise InvestigationContextInvalid("TASK_INPUT_HIGHWATER_INVALID")

    initial = connection.execute(
        """SELECT m.*, c.accepted_at AS accepted_at, r.control_revision_at_start,
                  r.expected_control_revision AS applied_control_revision
           FROM commands c
           JOIN messages m ON m.message_id = c.message_id
           JOIN task_runs r ON r.run_id = c.run_id
           WHERE c.command_kind = 'CREATE_TASK' AND m.task_id = ? AND m.tenant_id = ?
             AND r.task_id = ? AND r.source_message_id = m.message_id
           ORDER BY c.accepted_at, c.command_id LIMIT 1""",
        (task_id, str(row["tenant_id"]), task_id),
    ).fetchone()
    def input_ref(message: sqlite3.Row, semantic_kind: str) -> dict[str, Any]:
        body = str(message["body"])
        actual_digest = _sha256(body)
        if actual_digest != str(message["body_digest"]):
            raise InvestigationContextInvalid("USER_INPUT_DIGEST_MISMATCH")
        return {
            "message_id": str(message["message_id"]),
            "sequence": int(message["sequence"]),
            "digest": actual_digest,
            "kind": semantic_kind,
            "input_kind": str(message["input_kind"]),
            "body": body,
            "provenance": "USER_INPUT_UNTRUSTED",
            "accepted_control_revision": int(message["control_revision_at_start"] or 0),
            "applied_control_revision": (
                int(message["applied_control_revision"])
                if message["applied_control_revision"] is not None else None
            ),
        }

    if initial is None:
        fallback = "legacy demo symptom"
        selected = [{
            "message_id": None, "sequence": 0, "digest": _sha256(fallback),
            "kind": "LEGACY_DEMO_FALLBACK", "input_kind": "LEGACY_FALLBACK",
            "body": fallback, "provenance": "LEGACY_FALLBACK",
            "accepted_control_revision": 0, "applied_control_revision": None,
        }]
    else:
        if (
            str(initial["role"]) != "USER"
            or str(initial["input_kind"]) != "CHAT_READONLY"
            or str(initial["application_state"]) != "RECEIVED_NOT_APPLIED"
            or str(initial["session_id"]) != str(row["session_id"])
        ):
            raise InvestigationContextInvalid("INITIAL_SYMPTOM_SOURCE_INVALID")
        selected = [input_ref(initial, "INITIAL_SYMPTOM")]

    corrections = connection.execute(
        """SELECT m.*, i.input_digest, i.provenance AS input_provenance,
                  r.run_id AS input_run_id, r.control_revision_at_start,
                  r.expected_control_revision AS applied_control_revision
           FROM task_run_inputs i
           JOIN messages m ON m.message_id = i.message_id
           JOIN task_runs r ON r.run_id = i.run_id
           WHERE i.task_id = ? AND m.tenant_id = ? AND m.sequence <= ?
           ORDER BY m.sequence""",
        (task_id, str(row["tenant_id"]), applied_highwater),
    ).fetchall()
    for correction in corrections:
        if (
            str(correction["role"]) != "USER"
            or str(correction["input_kind"]) != "CORRECT_TASK_INPUT"
            or str(correction["application_state"]) != "APPLIED_TO_RUN"
            or str(correction["input_provenance"]) != "USER_INPUT_UNTRUSTED"
            or str(correction["input_digest"]) != str(correction["body_digest"])
            or str(correction["applied_run_id"]) != str(correction["input_run_id"])
        ):
            raise InvestigationContextInvalid("CRITICAL_INPUT_PROVENANCE_INVALID")
        selected.append(input_ref(correction, "CRITICAL_CORRECTION"))
    if applied_highwater and (not corrections or int(corrections[-1]["sequence"]) != applied_highwater):
        raise InvestigationContextInvalid("CRITICAL_INPUT_HIGHWATER_GAP")

    source_id = str(row["source_message_id"] or "")
    if source_id and not any(item["message_id"] == source_id for item in selected):
        raise InvestigationContextInvalid("RUN_SOURCE_MESSAGE_NOT_CONSUMED")
    if int(row["consumed_message_seq"]) < max(int(item["sequence"]) for item in selected):
        raise InvestigationContextInvalid("RUN_INPUT_NOT_CONSUMED")

    refs = [
        {key: value for key, value in item.items() if key != "body"}
        for item in selected
    ]
    control = {
        "run_id": str(row["run_id"]),
        "source_message_id": source_id,
        "expected_control_revision": int(expected_revision),
        "current_control_revision": int(row["control_revision"]),
        "consumed_message_seq": consumed_highwater,
        "applied_critical_message_seq": applied_highwater,
        "pending_critical_message_seq": None,
        "input_refs": refs,
    }
    return {
        "inputs": selected,
        "task_run_control": control,
        "trusted_binding": {
            "service_id": str(row["service_id"]),
            "integration_id": str(row["integration_id"]),
            "principal_id": str(row["principal_id"]),
            "route": "GET /api/async-orders/async-order" if str(row["service_id"]) == "orders-async-demo" else "GET /api/orders/demo-order",
        },
    }


def load_investigation_context(path: str | Path, task_id: str, run_id: str) -> dict[str, Any]:
    """Read only current Run's source Message and cumulatively applied corrections."""
    with connect(path) as connection:
        return _read_context(connection, task_id, run_id)


def load_initial_checkpoint_recovery_context(
    path: str | Path, task_id: str, run_id: str
) -> dict[str, Any]:
    """Validate the only Domain state that may cold-initialize a missing Graph checkpoint.

    Recovery is limited to an active INVESTIGATE Run whose original accepted inputs
    remain complete and current. Any D3 plan or action phase means a missing graph
    checkpoint could hide work that must be reconciled instead of replayed.
    """
    plan_tables = (
        "d3_plans",
        "d3_plan_control_bindings",
        "d3_plan_authorizations",
        "d3_plan_authorization_history",
        "d3_approvals",
        "approval_resume_links",
        "d3_action_permissions",
    )
    action_tables = (
        "d3_action_intents",
        "d3_action_ledgers",
        "d3_verification_receipts",
        "d3_report_artifacts",
        "d3_delivery_records",
        "d3_ticket_resolution_entries",
    )
    with connect(path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        selected = _read_context(connection, task_id, run_id)
        run = connection.execute(
            "SELECT kind, status, tenant_id FROM task_runs WHERE run_id = ? AND task_id = ?",
            (run_id, task_id),
        ).fetchone()
        if run is None or str(run["kind"]) != "INVESTIGATE":
            raise InvestigationContextInvalid("INITIAL_CHECKPOINT_RECOVERY_RUN_KIND_INVALID")
        if str(run["status"]) != "RUNNING":
            raise InvestigationContextInvalid("TASK_RUN_NOT_ACTIVE")
        inputs = list(selected.get("inputs", []))
        if (
            not inputs
            or inputs[0].get("kind") != "INITIAL_SYMPTOM"
            or not inputs[0].get("message_id")
            or str(inputs[0].get("provenance")) != "USER_INPUT_UNTRUSTED"
        ):
            raise InvestigationContextInvalid("INITIAL_CHECKPOINT_RECOVERY_SOURCE_REQUIRED")
        binding = connection.execute(
            "SELECT status FROM task_bindings WHERE task_id = ? AND tenant_id = ?",
            (task_id, str(run["tenant_id"])),
        ).fetchone()
        if binding is None or str(binding["status"]) in {
            "ABORTED", "COMPLETED", "WAITING_APPROVAL", "VERIFYING", "DELIVERY_PENDING",
        }:
            raise InvestigationContextInvalid("INITIAL_CHECKPOINT_RECOVERY_TASK_PHASE_INVALID")

        for table in action_tables:
            existing = connection.execute(
                f"SELECT 1 FROM {table} WHERE tenant_id = ? AND task_id = ? LIMIT 1",
                (str(run["tenant_id"]), task_id),
            ).fetchone()
            if existing is not None:
                raise InvestigationContextInvalid("ACTION_OUTCOME_UNKNOWN")
        for table in plan_tables:
            existing = connection.execute(
                f"SELECT 1 FROM {table} WHERE tenant_id = ? AND task_id = ? LIMIT 1",
                (str(run["tenant_id"]), task_id),
            ).fetchone()
            if existing is not None:
                raise InvestigationContextInvalid("INITIAL_CHECKPOINT_RECOVERY_DOMAIN_ACTIVITY")
    return selected


def validate_task_run_context_in_transaction(
    connection: sqlite3.Connection,
    task_id: str,
    context: dict[str, Any],
) -> None:
    """Revalidate the selected source refs atomically before a provider/tool attempt."""
    run_id = str(context.get("run_id", ""))
    expected_revision = context.get("expected_control_revision")
    if not run_id or type(expected_revision) is not int:
        raise InvestigationContextInvalid("TASK_RUN_CONTEXT_REQUIRED")
    run = connection.execute(
        "SELECT tenant_id, source_message_id, expected_control_revision, consumed_message_seq, applied_critical_message_seq, status FROM task_runs WHERE run_id = ? AND task_id = ?",
        (run_id, task_id),
    ).fetchone()
    if run is None:
        raise InvestigationContextInvalid("INVESTIGATION_RUN_CONTEXT_NOT_FOUND")
    assert_task_control_in_transaction(
        connection,
        str(run["tenant_id"]),
        task_id,
        expected_revision,
        run_id=run_id,
    )
    for key in ("consumed_message_seq", "applied_critical_message_seq"):
        if int(run[key]) != int(context.get(key, -1)):
            raise InvestigationContextInvalid("TASK_INPUT_HIGHWATER_STALE")
    if str(run["source_message_id"] or "") != str(context.get("source_message_id", "")):
        raise InvestigationContextInvalid("RUN_SOURCE_MESSAGE_STALE")
    refs = context.get("input_refs")
    if not isinstance(refs, list) or not refs:
        raise InvestigationContextInvalid("TASK_INPUT_PROVENANCE_REQUIRED")
    initial_refs = [ref for ref in refs if isinstance(ref, dict) and ref.get("kind") == "INITIAL_SYMPTOM"]
    correction_refs = [ref for ref in refs if isinstance(ref, dict) and ref.get("kind") == "CRITICAL_CORRECTION"]
    if len(initial_refs) != 1:
        raise InvestigationContextInvalid("INITIAL_SYMPTOM_PROVENANCE_REQUIRED")
    if initial_refs[0].get("kind") == "INITIAL_SYMPTOM":
        initial_id = str(initial_refs[0].get("message_id", ""))
        initial_row = connection.execute(
            """SELECT m.role, m.input_kind, m.application_state, c.command_kind, c.run_id
               FROM messages m JOIN commands c ON c.message_id = m.message_id
               WHERE m.message_id = ? AND m.task_id = ? AND m.tenant_id = ?""",
            (initial_id, task_id, str(run["tenant_id"])),
        ).fetchone()
        if (
            initial_row is None or str(initial_row["role"]) != "USER"
            or str(initial_row["input_kind"]) != "CHAT_READONLY"
            or str(initial_row["application_state"]) != "RECEIVED_NOT_APPLIED"
            or str(initial_row["command_kind"]) != "CREATE_TASK"
            or not initial_row["run_id"]
        ):
            raise InvestigationContextInvalid("INITIAL_SYMPTOM_PROVENANCE_INVALID")
        expected_initial = connection.execute(
            "SELECT source_message_id FROM task_runs WHERE run_id = ? AND task_id = ?",
            (str(initial_row["run_id"]), task_id),
        ).fetchone()
        if expected_initial is None or str(expected_initial["source_message_id"]) != initial_id:
            raise InvestigationContextInvalid("INITIAL_SYMPTOM_SOURCE_INVALID")
    elif initial_refs[0].get("kind") != "LEGACY_DEMO_FALLBACK":
        raise InvestigationContextInvalid("INITIAL_SYMPTOM_KIND_INVALID")
    expected_corrections = [
        str(item["message_id"])
        for item in connection.execute(
            """SELECT m.message_id FROM task_run_inputs i JOIN messages m ON m.message_id = i.message_id
               WHERE i.task_id = ? AND m.sequence <= ? ORDER BY m.sequence""",
            (task_id, int(context["applied_critical_message_seq"])),
        ).fetchall()
    ]
    if [str(ref.get("message_id", "")) for ref in correction_refs] != expected_corrections:
        raise InvestigationContextInvalid("CRITICAL_INPUT_SELECTION_STALE")
    for ref in refs:
        if not isinstance(ref, dict):
            raise InvestigationContextInvalid("TASK_INPUT_PROVENANCE_INVALID")
        message = connection.execute(
            "SELECT body, body_digest, sequence, input_kind, application_state, applied_run_id FROM messages WHERE message_id = ? AND task_id = ? AND tenant_id = ?",
            (str(ref.get("message_id", "")), task_id, str(run["tenant_id"])),
        ).fetchone()
        if ref.get("kind") == "LEGACY_DEMO_FALLBACK":
            if ref.get("message_id") is not None or ref.get("digest") != _sha256("legacy demo symptom"):
                raise InvestigationContextInvalid("LEGACY_FALLBACK_INVALID")
            continue
        if (
            message is None
            or int(message["sequence"]) != int(ref.get("sequence", -1))
            or str(message["body_digest"]) != str(ref.get("digest", ""))
            or _sha256(str(message["body"])) != str(ref.get("digest", ""))
        ):
            raise InvestigationContextInvalid("USER_INPUT_PROVENANCE_STALE")
        if ref.get("kind") == "CRITICAL_CORRECTION":
            source = connection.execute(
                "SELECT input_digest, provenance FROM task_run_inputs WHERE message_id = ? AND task_id = ?",
                (str(ref["message_id"]), task_id),
            ).fetchone()
            if (
                str(message["input_kind"]) != "CORRECT_TASK_INPUT"
                or str(message["application_state"]) != "APPLIED_TO_RUN"
                or source is None
                or str(source["input_digest"]) != str(ref["digest"])
                or str(source["provenance"]) != "USER_INPUT_UNTRUSTED"
            ):
                raise InvestigationContextInvalid("CRITICAL_INPUT_PROVENANCE_STALE")
        elif ref.get("kind") != "INITIAL_SYMPTOM":
            raise InvestigationContextInvalid("TASK_INPUT_KIND_INVALID")
