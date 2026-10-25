"""Trusted TaskRun input selection for the read-only Investigator prompt."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any

from opspilot.domain.database import connect
from opspilot.domain.task_control import TaskControlError, assert_task_control_in_transaction


class InvestigationContextInvalid(TaskControlError):
    """The persisted Run inputs no longer match the active TaskControl state."""


MAX_PRIOR_READONLY_FOLLOWUPS = 3
MAX_PRIOR_FOLLOWUP_ANSWER_CHARS = 1600
MAX_PRIOR_FOLLOWUP_MESSAGE_CHARS = 600
MAX_PRIOR_FOLLOWUP_SOURCE_REFS = 12


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def load_prior_readonly_followups(
    connection: sqlite3.Connection,
    *,
    tenant_id: str,
    session_id: str,
    task_id: str,
    before_sequence: int,
    limit: int = MAX_PRIOR_READONLY_FOLLOWUPS,
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    """Load bounded, scoped prior C1 answers without inheriting their Evidence as current.

    This shared assembler is used by Chat, the update classifier and Investigator.
    Knowledge is revalidated against the task's current contract version and S3
    authorization; business Evidence is verified only as a source of its original
    Run and is always labeled historical.
    """
    bounded_limit = min(max(int(limit), 0), MAX_PRIOR_READONLY_FOLLOWUPS)
    if bounded_limit == 0 or before_sequence <= 0:
        return [], []
    binding = connection.execute(
        "SELECT service_id FROM task_bindings WHERE tenant_id=? AND task_id=?",
        (tenant_id, task_id),
    ).fetchone()
    if binding is None or str(binding["service_id"]) != "orders-async-demo":
        return [], []
    rows = connection.execute(
        """SELECT f.*,r.kind AS run_kind,r.status AS run_status,
                  r.source_message_id AS run_source_message_id,
                  r.consumed_message_seq AS run_consumed_message_seq,
                  m.body AS source_message_body,m.body_digest AS actual_source_digest,
                  m.sequence AS source_sequence,m.role AS source_role,
                  m.input_kind AS source_input_kind,m.session_id AS source_session_id,
                  m.tenant_id AS source_tenant_id
           FROM c1_readonly_followup_runs f
           JOIN task_runs r ON r.run_id=f.run_id AND r.task_id=f.task_id AND r.tenant_id=f.tenant_id
           JOIN messages m ON m.message_id=f.source_message_id AND m.task_id=f.task_id
             AND m.tenant_id=f.tenant_id AND m.session_id=f.session_id
           WHERE f.tenant_id=? AND f.session_id=? AND f.task_id=? AND m.sequence<?
             AND f.result_state IS NOT NULL AND f.answer_text IS NOT NULL
             AND f.result_digest IS NOT NULL AND f.completed_at IS NOT NULL
           ORDER BY m.sequence DESC,f.run_id DESC LIMIT ?""",
        (tenant_id, session_id, task_id, int(before_sequence), bounded_limit),
    ).fetchall()
    from opspilot.domain.s3_answers import prior_answer_rows
    initial_rows, initial_exclusions = prior_answer_rows(connection,tenant_id,session_id,task_id,int(before_sequence),bounded_limit)
    rows = sorted([dict(row) for row in rows] + initial_rows, key=lambda row:(int(row["source_sequence"]),str(row["run_id"])), reverse=True)[:bounded_limit]
    if not rows:
        return [], initial_exclusions

    from opspilot.domain.s3 import get_s3_binding

    try:
        current_binding = get_s3_binding(connection, task_id)
    except Exception:
        return [], initial_exclusions + [{"source_id": str(row["run_id"]), "reason": "CURRENT_S3_AUTHORIZATION_UNAVAILABLE"}
                    for row in rows]
    from opspilot.domain.s3_assets import refresh_asset_refs

    records: list[dict[str, Any]] = []
    excluded: list[dict[str, str]] = list(initial_exclusions)
    for row in reversed(rows):
        run_id = str(row["run_id"])
        if (
            str(row["run_kind"]) != "INVESTIGATE"
            or str(row["run_status"]) != "SUCCEEDED"
            or str(row["run_source_message_id"]) != str(row["source_message_id"])
            or int(row["run_consumed_message_seq"]) != int(row["source_sequence"])
            or int(row["source_sequence"]) >= int(before_sequence)
            or str(row["source_role"]) != "USER"
            or str(row["source_input_kind"]) not in ({"CHAT_READONLY","CORRECT_TASK_INPUT"} if row.get("result_storage")=="S3_RUN_ANSWER" else {"CHAT_READONLY"})
            or str(row["source_session_id"]) != session_id
            or str(row["source_tenant_id"]) != tenant_id
            or str(row["source_digest"]) != str(row["actual_source_digest"])
        ):
            excluded.append({"source_id": run_id, "reason": "READONLY_FOLLOWUP_SCOPE_OR_RUN_INVALID"})
            continue
        refs_json = str(row["source_refs_json"])
        result_json = str(row["result_json"])
        try:
            source_refs = json.loads(refs_json)
            result_payload = json.loads(result_json)
        except (TypeError, json.JSONDecodeError):
            excluded.append({"source_id": run_id, "reason": "READONLY_FOLLOWUP_RESULT_MALFORMED"})
            continue
        if not isinstance(source_refs, list) or not isinstance(result_payload, dict):
            excluded.append({"source_id": run_id, "reason": "READONLY_FOLLOWUP_RESULT_MALFORMED"})
            continue
        frozen_digest = _sha256(_canonical({
            "run_id": run_id,
            "result_state": str(row["result_state"]),
            "answer_text": str(row["answer_text"]),
            "source_refs_json": refs_json,
            "result_json": result_json,
            "reason_code": row["reason_code"],
        }))
        if frozen_digest != str(row["result_digest"]):
            excluded.append({"source_id": run_id, "reason": "READONLY_FOLLOWUP_DIGEST_INVALID"})
            continue

        knowledge_refs: list[dict[str, Any]] = []
        for ref in source_refs:
            if isinstance(ref, dict) and ref.get("kind") == "KNOWLEDGE":
                knowledge_refs.append({key: ref.get(key) for key in (
                    "document_id", "version", "digest", "source", "valid_from",
                )})
        try:
            current_knowledge, _, knowledge_exclusions = refresh_asset_refs(
                {"s3_knowledge_refs": knowledge_refs},
                contract_version=int(current_binding["contract_version"]),
            )
        except Exception:
            current_knowledge, knowledge_exclusions = [], [
                {"source_type": "KNOWLEDGE", "source_id": str(ref.get("document_id") or "unknown"),
                 "reason": "CURRENT_KNOWLEDGE_UNAVAILABLE"}
                for ref in knowledge_refs
            ]
        current_docs = {str(item["document_id"]): item for item in current_knowledge}
        knowledge_reason = {
            str(item.get("source_id")): str(item.get("reason") or "KNOWLEDGE_REMOVED_EXPIRED_OR_CHANGED")
            for item in knowledge_exclusions if isinstance(item, dict)
        }
        resolved_refs: list[dict[str, Any]] = []
        for ref in source_refs[:MAX_PRIOR_FOLLOWUP_SOURCE_REFS]:
            if not isinstance(ref, dict):
                resolved_refs.append({"kind": "UNKNOWN", "currentness": "INVALID_SOURCE_REFERENCE"})
                continue
            item = {key: value for key, value in ref.items()}
            kind = str(ref.get("kind") or "UNKNOWN")
            if kind == "KNOWLEDGE":
                doc_id = str(ref.get("document_id") or "")
                current_doc = current_docs.get(doc_id)
                if current_doc and all(current_doc.get(key) == ref.get(key) for key in (
                    "version", "digest", "source", "valid_from",
                )):
                    item["currentness"] = "CURRENT_APPLICABLE"
                    item["source_authority"] = "VERSIONED_KNOWLEDGE_NOT_BUSINESS_EVIDENCE"
                else:
                    item["currentness"] = "HISTORICAL_SOURCE_STALE"
                    item["reason"] = knowledge_reason.get(doc_id, "KNOWLEDGE_REMOVED_EXPIRED_OR_CHANGED")
                    item["source_authority"] = "HISTORICAL_REFERENCE_ONLY"
            elif kind == "EVIDENCE":
                evidence_id = str(ref.get("evidence_id") or "")
                observation = connection.execute(
                    """SELECT o.observation_id,o.attempt_id,a.run_id AS origin_run_id
                       FROM d2_tool_observations o
                       JOIN d2_attempts a ON a.attempt_id=o.attempt_id AND a.task_id=o.task_id
                       JOIN d2_evidence e ON e.evidence_id=o.evidence_id AND e.task_id=o.task_id
                       JOIN task_runs r ON r.run_id=a.run_id AND r.task_id=a.task_id
                       WHERE o.task_id=? AND o.evidence_id=? AND o.status='OK'
                         AND a.kind='MCP' AND a.status='OK' AND r.tenant_id=?
                         AND (? IS NULL OR a.run_id=?)
                         AND o.created_at<=? ORDER BY o.created_at DESC LIMIT 1""",
                    (task_id, evidence_id, tenant_id, ref.get("origin_run_id"), ref.get("origin_run_id"), str(row["completed_at"])),
                ).fetchone()
                item["currentness"] = "HISTORICAL_RUN_ONLY" if observation is not None else "INVALID_SOURCE_RUN_ASSOCIATION"
                item["reason"] = None if observation is not None else "EVIDENCE_NOT_OBSERVED_BY_SOURCE_RUN"
                item["source_authority"] = "HISTORICAL_EVIDENCE_NOT_CURRENT"
                if observation is not None:
                    item["observation_id"] = str(observation["observation_id"])
                    item["attempt_id"] = str(observation["attempt_id"])
                    item["origin_run_id"] = str(observation["origin_run_id"])
            elif kind == "USER_MESSAGE":
                if (
                    str(ref.get("message_id") or "") == str(row["source_message_id"])
                    and str(ref.get("digest") or "") == str(row["actual_source_digest"])
                ):
                    item["currentness"] = "SOURCE_MESSAGE_VERIFIED"
                    item["source_authority"] = "USER_INPUT_UNTRUSTED"
                else:
                    item["currentness"] = "INVALID_SOURCE_MESSAGE"
            else:
                item["currentness"] = "HISTORICAL_ONLY"
                item["source_authority"] = "NON_AUTHORITATIVE_HISTORY"
            resolved_refs.append(item)

        gate = result_payload.get("gate") if isinstance(result_payload.get("gate"), dict) else {}
        summary = {
            "gate_decision": gate.get("decision"),
            "gate_reason_code": gate.get("reason_code"),
            "diagnosis_persisted": result_payload.get("diagnosis_persisted") is True,
            "observation_ids": [str(value)[:200] for value in result_payload.get("observation_ids", [])[:12]]
            if isinstance(result_payload.get("observation_ids"), list) else [],
        }
        records.append({
            "run_id": run_id,
            "source_message_id": str(row["source_message_id"]),
            "source_message_digest": str(row["source_digest"]),
            "source_sequence": int(row["source_sequence"]),
            "source_message": str(row["source_message_body"])[:MAX_PRIOR_FOLLOWUP_MESSAGE_CHARS],
            "result_state": str(row["result_state"]),
            "answer_text": str(row["answer_text"])[:MAX_PRIOR_FOLLOWUP_ANSWER_CHARS],
            "answer_truncated": len(str(row["answer_text"])) > MAX_PRIOR_FOLLOWUP_ANSWER_CHARS,
            "result_digest": str(row["result_digest"]),
            "reason_code": str(row["reason_code"]) if row["reason_code"] else None,
            "result_summary": summary,
            "source_refs": resolved_refs,
            "completed_at": str(row["completed_at"]),
            "source_authority": "HISTORICAL_RESULT_ONLY",
            "result_storage": row.get("result_storage", "C1_READONLY_FOLLOWUP"),
            "storage_digest": row.get("storage_digest", row["result_digest"]),
        })
    return records, excluded


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
    readonly_followup = connection.execute(
        """SELECT source_message_id,source_digest,expected_control_revision
           FROM c1_readonly_followup_runs WHERE run_id=? AND task_id=? AND tenant_id=?""",
        (run_id, task_id, str(row["tenant_id"])),
    ).fetchone()
    if readonly_followup is not None:
        if (
            source_id != str(readonly_followup["source_message_id"])
            or int(readonly_followup["expected_control_revision"]) != int(expected_revision)
        ):
            raise InvestigationContextInvalid("READONLY_FOLLOWUP_SOURCE_STALE")
        followup_message = connection.execute(
            """SELECT m.*,r.control_revision_at_start,
                      r.expected_control_revision AS applied_control_revision
               FROM messages m JOIN task_runs r ON r.source_message_id=m.message_id
               WHERE r.run_id=? AND m.message_id=? AND m.task_id=? AND m.tenant_id=?
                 AND m.session_id=? AND m.role='USER' AND m.input_kind='CHAT_READONLY'""",
            (run_id, source_id, task_id, str(row["tenant_id"]), str(row["session_id"])),
        ).fetchone()
        if (
            followup_message is None
            or str(followup_message["body_digest"]) != str(readonly_followup["source_digest"])
        ):
            raise InvestigationContextInvalid("READONLY_FOLLOWUP_SOURCE_INVALID")
        selected.append(input_ref(followup_message, "READONLY_FOLLOWUP"))
    elif source_id and str(row["kind"]) == "INVESTIGATE":
        # Ordinary Investigator Runs must source their initial symptom or the
        # currently applied correction; chat-only messages cannot be borrowed.
        pass
    if source_id and not any(item["message_id"] == source_id for item in selected):
        raise InvestigationContextInvalid("RUN_SOURCE_MESSAGE_NOT_CONSUMED")
    if int(row["consumed_message_seq"]) < max(int(item["sequence"]) for item in selected):
        raise InvestigationContextInvalid("RUN_INPUT_NOT_CONSUMED")

    prior_readonly_followups, prior_followup_exclusions = load_prior_readonly_followups(
        connection,
        tenant_id=str(row["tenant_id"]),
        session_id=str(row["session_id"]),
        task_id=task_id,
        before_sequence=int(row["consumed_message_seq"]),
    )

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
        "prior_readonly_followups": prior_readonly_followups,
        "prior_readonly_followup_exclusions": prior_followup_exclusions,
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
        "SELECT tenant_id, session_id, source_message_id, expected_control_revision, consumed_message_seq, applied_critical_message_seq, status FROM task_runs WHERE run_id = ? AND task_id = ?",
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
    followup_refs = [ref for ref in refs if isinstance(ref, dict) and ref.get("kind") == "READONLY_FOLLOWUP"]
    readonly_followup = connection.execute(
        "SELECT source_message_id,source_digest,expected_control_revision FROM c1_readonly_followup_runs WHERE run_id=? AND task_id=? AND tenant_id=?",
        (run_id, task_id, str(run["tenant_id"])),
    ).fetchone()
    if readonly_followup is None and followup_refs:
        raise InvestigationContextInvalid("READONLY_FOLLOWUP_SOURCE_UNEXPECTED")
    if readonly_followup is not None and (
        len(followup_refs) != 1
        or str(followup_refs[0].get("message_id")) != str(readonly_followup["source_message_id"])
        or int(readonly_followup["expected_control_revision"]) != int(run["expected_control_revision"])
    ):
        raise InvestigationContextInvalid("READONLY_FOLLOWUP_SOURCE_STALE")
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
            "SELECT role,session_id,body,body_digest,sequence,input_kind,application_state,applied_run_id FROM messages WHERE message_id = ? AND task_id = ? AND tenant_id = ?",
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
        elif ref.get("kind") == "READONLY_FOLLOWUP":
            if (
                message is None
                or str(message["role"]) != "USER"
                or str(message["session_id"]) != str(run["session_id"])
                or str(message["input_kind"]) != "CHAT_READONLY"
                or str(message["application_state"]) not in {"NOT_APPLICABLE", "RECEIVED_NOT_APPLIED"}
                or str(ref.get("message_id")) != str(readonly_followup["source_message_id"])
                or str(message["body_digest"]) != str(readonly_followup["source_digest"])
            ):
                raise InvestigationContextInvalid("READONLY_FOLLOWUP_SOURCE_INVALID")
        elif ref.get("kind") != "INITIAL_SYMPTOM":
            raise InvestigationContextInvalid("TASK_INPUT_KIND_INVALID")
