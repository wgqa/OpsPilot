from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

from opspilot.domain.database import connect
from opspilot.domain.d2 import canonical_json, digest_json, utc_now
from opspilot.domain.task_control import (
    TaskControlError,
    TrustedIdentity,
    _find_idempotent_command,
    _insert_outbox,
    _record_command,
    _require_support_owner,
    assert_task_control_in_transaction,
)


HANDOFF_KIND = "SCOPE_REVIEW"
RECEIVER_QUEUE_ID = "local-scope-review"
RECEIVER_IDENTITY_REF = "local-demo-access-reviewer"
RECEIVER_LABEL = "本地受控审查队列"
REVIEW_SLA_HOURS = 72
_OPERATION_ID = re.compile(r"^[A-Za-z0-9._:-]{1,200}$")
_M2_03_TEST_FAILPOINT: Callable[[str], None] | None = None


def _failpoint(name: str) -> None:
    callback = _M2_03_TEST_FAILPOINT
    if callback is not None:
        callback(name)
    if (
        os.environ.get("OPSPILOT_ENABLE_M2_03_FAILPOINTS") == "1"
        and os.environ.get("OPSPILOT_M2_03_FAIL_AT") == name
    ):
        if os.environ.get("OPSPILOT_M2_03_CRASH_PROCESS") == "1":
            os._exit(86)
        raise RuntimeError(f"M2-03 failure injection: {name}")


def _canonical_request(
    identity: TrustedIdentity,
    task_id: str,
    operation_id: str,
    draft_id: str,
    draft_digest: str,
    expected_control_revision: int,
    handoff_kind: str,
) -> dict[str, object]:
    return {
        "schema_version": 1,
        "method": "POST",
        "route": f"/api/tasks/{task_id}/handoff/submit",
        "tenant_id": identity.tenant_id,
        "actor_id": identity.actor_id,
        "task_id": task_id,
        "operation_id": operation_id,
        "draft_id": draft_id,
        "draft_digest": draft_digest,
        "expected_control_revision": expected_control_revision,
        "handoff_kind": handoff_kind,
    }


def _request_digest(request: dict[str, object]) -> str:
    return hashlib.sha256(canonical_json(request).encode("utf-8")).hexdigest()


def _handoff_status(queue_row: sqlite3.Row, now: datetime) -> str:
    status = str(queue_row["queue_status"])
    if status == "PENDING_REVIEW":
        due = datetime.fromisoformat(str(queue_row["review_due_at"]).replace("Z", "+00:00"))
        if due.tzinfo is None:
            due = due.replace(tzinfo=timezone.utc)
        if now.astimezone(timezone.utc) >= due.astimezone(timezone.utc):
            return "OVERDUE"
    return status


def _response(
    receipt: sqlite3.Row,
    queue: sqlite3.Row,
    *,
    operation_id: str,
    replayed: bool,
    now: datetime | None = None,
) -> dict[str, object]:
    now = now or datetime.now(timezone.utc)
    return {
        "status": "ACCEPTED",
        "business_outcome": "SCOPE_ESCALATED",
        "operation_id": operation_id,
        "receipt_id": str(receipt["receipt_id"]),
        "queue_entry_id": str(queue["entry_id"]),
        "draft_id": str(receipt["draft_id"]),
        "draft_digest": str(receipt["draft_digest"]),
        "receiver_label": RECEIVER_LABEL,
        "received_at": str(receipt["accepted_at"]),
        "handoff_status": _handoff_status(queue, now),
        "submitted": True,
        "scope_authorized": False,
        "recovered": False,
        "replayed": replayed,
    }


def _receipt_and_queue(
    connection: sqlite3.Connection, tenant_id: str, task_id: str, handoff_kind: str,
) -> tuple[sqlite3.Row, sqlite3.Row] | None:
    row = connection.execute(
        """SELECT r.receipt_id, r.tenant_id, r.task_id, r.handoff_kind, r.entry_id,
                  r.draft_id, r.draft_version, r.draft_digest, r.operation_id,
                  r.canonical_request_digest, r.accepted_by_receiver_ref, r.accepted_by_actor_id,
                  r.accepted_at, r.receipt_digest, r.control_revision, r.request_id, r.decision_id,
                  r.credential_policy_version, r.scope_policy_version, r.grant_version,
                  q.receiver_queue_id, q.receiver_identity_ref, q.received_at, q.review_due_at, q.queue_status
           FROM s2_handoff_receipts r JOIN s2_handoff_queue_entries q
             ON q.entry_id = r.entry_id AND q.tenant_id = r.tenant_id AND q.task_id = r.task_id
           WHERE r.tenant_id = ? AND r.task_id = ? AND r.handoff_kind = ?""",
        (tenant_id, task_id, handoff_kind),
    ).fetchone()
    if row is None:
        return None
    # Give the queue projection a row-like mapping while keeping the Receipt immutable.
    return row, row


def _persisted_result(
    connection: sqlite3.Connection,
    *,
    tenant_id: str,
    task_id: str,
    handoff_kind: str,
    operation_id: str,
    replayed: bool,
) -> dict[str, object] | None:
    rows = _receipt_and_queue(connection, tenant_id, task_id, handoff_kind)
    if rows is None:
        return None
    receipt, queue = rows
    return _response(receipt, queue, operation_id=operation_id, replayed=replayed)


def _record_command_result(
    connection: sqlite3.Connection,
    *,
    identity: TrustedIdentity,
    task_id: str,
    operation_id: str,
    request_digest: str,
    result: dict[str, object],
) -> None:
    _record_command(
        connection,
        command_id=f"s2-handoff-command-{uuid.uuid4()}",
        identity=identity,
        command_kind="S2_HANDOFF_SUBMIT",
        target_ref=f"{task_id}:{HANDOFF_KIND}",
        idempotency_key=operation_id,
        request_digest=request_digest,
        accepted_status="ACCEPTED",
        result=result,
    )


def _current_draft_gate(
    connection: sqlite3.Connection,
    db_path: str | Path,
    *,
    tenant_id: str,
    task_id: str,
    draft: sqlite3.Row,
) -> dict[str, object]:
    from opspilot.domain.s2_diagnosis import _receipt_dict, evaluate_s2_evidence_gate

    latest_receipt = connection.execute(
        """SELECT receipt_id FROM s2_diagnosis_receipts
           WHERE tenant_id = ? AND task_id = ? ORDER BY created_at DESC, receipt_id DESC LIMIT 1""",
        (tenant_id, task_id),
    ).fetchone()
    if latest_receipt is None or str(latest_receipt["receipt_id"]) != str(draft["receipt_id"]):
        raise TaskControlError("DRAFT_STALE")
    receipt_row = connection.execute(
        """SELECT * FROM s2_diagnosis_receipts
           WHERE tenant_id = ? AND task_id = ? AND receipt_id = ?""",
        (tenant_id, task_id, draft["receipt_id"]),
    ).fetchone()
    if receipt_row is None:
        raise TaskControlError("DRAFT_STALE")
    receipt = _receipt_dict(receipt_row)
    run = connection.execute(
        """SELECT kind, status, expected_control_revision FROM task_runs
           WHERE tenant_id = ? AND task_id = ? AND run_id = ?""",
        (tenant_id, task_id, receipt["run_id"]),
    ).fetchone()
    control = connection.execute(
        "SELECT control_revision FROM task_controls WHERE tenant_id = ? AND task_id = ?",
        (tenant_id, task_id),
    ).fetchone()
    if (
        run is None or str(run["kind"]) not in {"INVESTIGATE", "RESUME"}
        or str(run["status"]) != "SUCCEEDED" or control is None
        or run["expected_control_revision"] is None
        or int(run["expected_control_revision"]) != int(control["control_revision"])
    ):
        raise TaskControlError("DRAFT_STALE")

    try:
        content = json.loads(str(draft["content_json"]))
    except (TypeError, ValueError):
        raise TaskControlError("DRAFT_STALE") from None
    if (
        not isinstance(content, dict)
        or digest_json(content) != str(draft["content_digest"])
        or content.get("diagnosis_receipt_id") != receipt["receipt_id"]
        or content.get("request_id") != receipt["request_id"]
        or content.get("decision_id") != receipt["decision_id"]
        or content.get("state") != "FROZEN_DRAFT_NOT_SUBMITTED"
    ):
        raise TaskControlError("DRAFT_STALE")
    gate = evaluate_s2_evidence_gate(
        db_path, task_id, list(receipt["evidence_ids"]), run_id=str(receipt["run_id"]),
        connection=connection,
    )
    if (
        gate["decision"] != "DIAGNOSED"
        or gate.get("request_id") != receipt["request_id"]
        or gate.get("decision_id") != receipt["decision_id"]
        or gate.get("evidence_digests") != receipt["evidence_digests"]
        or gate.get("predicate") != receipt["predicate"]
    ):
        raise TaskControlError("DRAFT_STALE")
    return gate


def submit_s2_handoff(
    path: str | Path,
    identity: TrustedIdentity,
    *,
    task_id: str,
    operation_id: str,
    draft_id: str,
    draft_digest: str,
    expected_control_revision: int,
    handoff_kind: str,
) -> dict[str, object]:
    """Atomically accept one S2 draft into the fixed local review queue."""
    if (
        not isinstance(operation_id, str) or not _OPERATION_ID.fullmatch(operation_id)
        or operation_id.strip() != operation_id or not draft_id or len(draft_id) > 200
        or not re.fullmatch(r"[0-9a-f]{64}", draft_digest)
        or isinstance(expected_control_revision, bool) or expected_control_revision < 0
        or handoff_kind != HANDOFF_KIND
    ):
        raise TaskControlError("INVALID_REQUEST")
    request = _canonical_request(
        identity, task_id, operation_id, draft_id, draft_digest,
        expected_control_revision, handoff_kind,
    )
    request_digest = _request_digest(request)
    accepted_response: dict[str, object] | None = None
    with connect(path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        binding = _require_support_owner(connection, identity, task_id)
        target_ref = f"{task_id}:{handoff_kind}"
        prior = _find_idempotent_command(
            connection, identity, operation_id, "S2_HANDOFF_SUBMIT", target_ref, request_digest,
        )
        if prior is not None:
            prior["replayed"] = True
            prior["status"] = "ACCEPTED"
            return prior

        existing = _persisted_result(
            connection, tenant_id=identity.tenant_id, task_id=task_id,
            handoff_kind=handoff_kind, operation_id=operation_id, replayed=True,
        )
        if existing is not None:
            if (
                existing["draft_id"] != draft_id
                or existing["draft_digest"] != draft_digest
            ):
                raise TaskControlError("QUEUE_ALREADY_ACCEPTED")
            _record_command_result(
                connection, identity=identity, task_id=task_id, operation_id=operation_id,
                request_digest=request_digest, result=existing,
            )
            return existing
        partial = connection.execute(
            """SELECT
                 (SELECT COUNT(*) FROM s2_handoff_queue_entries WHERE tenant_id = ? AND task_id = ? AND handoff_kind = ?) AS queue_n,
                 (SELECT COUNT(*) FROM s2_handoff_receipts WHERE tenant_id = ? AND task_id = ? AND handoff_kind = ?) AS receipt_n""",
            (identity.tenant_id, task_id, handoff_kind, identity.tenant_id, task_id, handoff_kind),
        ).fetchone()
        if partial is not None and (int(partial["queue_n"]) or int(partial["receipt_n"])):
            raise TaskControlError("HANDOFF_INTEGRITY_ERROR")

        control = assert_task_control_in_transaction(
            connection, identity.tenant_id, task_id, expected_control_revision,
        )
        if str(binding["status"]) != "WAITING_HANDOFF":
            raise TaskControlError("DRAFT_STALE")
        active = connection.execute(
            """SELECT 1 FROM task_runs WHERE tenant_id = ? AND task_id = ?
               AND kind != 'CHAT_READONLY'
               AND status IN ('QUEUED', 'RUNNING', 'WAITING_INPUT', 'WAITING_APPROVAL', 'INTERRUPTED_RECOVERABLE')
               LIMIT 1""",
            (identity.tenant_id, task_id),
        ).fetchone()
        if active is not None:
            raise TaskControlError("TASK_RUN_BUSY")
        latest = connection.execute(
            """SELECT * FROM s2_handoff_drafts WHERE tenant_id = ? AND task_id = ?
               ORDER BY version DESC, draft_id DESC LIMIT 1""",
            (identity.tenant_id, task_id),
        ).fetchone()
        if (
            latest is None or str(latest["draft_id"]) != draft_id
            or str(latest["content_digest"]) != draft_digest
        ):
            raise TaskControlError("DRAFT_STALE")
        gate = _current_draft_gate(
            connection, path, tenant_id=identity.tenant_id, task_id=task_id, draft=latest,
        )
        predicate = gate["predicate"]
        if not isinstance(predicate, dict):
            raise TaskControlError("DRAFT_STALE")

        accepted_at = utc_now()
        accepted_time = datetime.fromisoformat(accepted_at.replace("Z", "+00:00"))
        due_at = (accepted_time + timedelta(hours=REVIEW_SLA_HOURS)).isoformat(timespec="milliseconds")
        entry_id = f"s2-queue-{uuid.uuid4()}"
        receipt_id = f"s2-handoff-{uuid.uuid4()}"
        receipt_payload = {
            "schema_version": 1,
            "tenant_id": identity.tenant_id,
            "task_id": task_id,
            "handoff_kind": handoff_kind,
            "entry_id": entry_id,
            "draft_id": draft_id,
            "draft_version": int(latest["version"]),
            "draft_digest": draft_digest,
            "operation_id": operation_id,
            "canonical_request_digest": request_digest,
            "accepted_by_receiver_ref": RECEIVER_IDENTITY_REF,
            "accepted_by_actor_id": identity.actor_id,
            "accepted_at": accepted_at,
            "control_revision": int(control["control_revision"]),
            "request_id": str(gate["request_id"]),
            "decision_id": int(gate["decision_id"]),
            "credential_policy_version": int(predicate["credential_policy_version"]),
            "scope_policy_version": int(predicate["scope_policy_version"]),
            "grant_version": int(predicate["grant_version"]),
        }
        receipt_digest = digest_json(receipt_payload)
        new_result = {
            "status": "ACCEPTED",
            "business_outcome": "SCOPE_ESCALATED",
            "operation_id": operation_id,
            "receipt_id": receipt_id,
            "queue_entry_id": entry_id,
            "draft_id": draft_id,
            "draft_digest": draft_digest,
            "receiver_label": RECEIVER_LABEL,
            "received_at": accepted_at,
            "handoff_status": "PENDING_REVIEW",
            "submitted": True,
            "scope_authorized": False,
            "recovered": False,
            "replayed": False,
        }
        _record_command_result(
            connection, identity=identity, task_id=task_id, operation_id=operation_id,
            request_digest=request_digest, result=new_result,
        )
        _failpoint("after_command_before_queue")
        connection.execute(
            """INSERT INTO s2_handoff_queue_entries
               (entry_id, tenant_id, task_id, handoff_kind, receiver_queue_id,
                receiver_identity_ref, draft_id, draft_version, draft_digest, received_at,
                review_due_at, queue_status)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'PENDING_REVIEW')""",
            (entry_id, identity.tenant_id, task_id, handoff_kind, RECEIVER_QUEUE_ID,
             RECEIVER_IDENTITY_REF, draft_id, int(latest["version"]), draft_digest,
             accepted_at, due_at),
        )
        _failpoint("after_queue_before_receipt")
        connection.execute(
            """INSERT INTO s2_handoff_receipts
               (receipt_id, tenant_id, task_id, handoff_kind, entry_id, draft_id,
                draft_version, draft_digest, operation_id, canonical_request_digest,
                accepted_by_receiver_ref, accepted_by_actor_id, accepted_at, receipt_digest,
                control_revision, request_id, decision_id, credential_policy_version,
                scope_policy_version, grant_version)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (receipt_id, identity.tenant_id, task_id, handoff_kind, entry_id, draft_id,
             int(latest["version"]), draft_digest, operation_id, request_digest,
             RECEIVER_IDENTITY_REF, identity.actor_id, accepted_at, receipt_digest,
             int(control["control_revision"]), str(gate["request_id"]), int(gate["decision_id"]),
             int(predicate["credential_policy_version"]), int(predicate["scope_policy_version"]),
             int(predicate["grant_version"])),
        )
        _failpoint("after_receipt_before_outbox")
        updated = connection.execute(
            "UPDATE task_bindings SET status = 'COMPLETED' WHERE tenant_id = ? AND task_id = ? AND status = 'WAITING_HANDOFF'",
            (identity.tenant_id, task_id),
        )
        if updated.rowcount != 1:
            raise TaskControlError("DRAFT_STALE")
        _insert_outbox(
            connection, identity.tenant_id, task_id, None,
            "S2_HANDOFF_RECEIPT", receipt_id, "S2_HANDOFF_ACCEPTED",
            {
                "task_id": task_id,
                "task_status": "COMPLETED",
                "business_outcome": "SCOPE_ESCALATED",
                "operation_id": operation_id,
                "receipt_id": receipt_id,
                "queue_entry_id": entry_id,
                "draft_id": draft_id,
                "draft_digest": draft_digest,
                "handoff_status": "PENDING_REVIEW",
                "scope_authorized": False,
                "recovered": False,
            },
        )
        accepted_response = new_result
    _failpoint("after_commit_before_http_response")
    assert accepted_response is not None
    return accepted_response


def get_s2_handoff_outcome(
    path: str | Path, task_id: str, *, now: datetime | None = None,
) -> dict[str, object] | None:
    """Read the durable receipt projection; it outranks later mutable Task facts."""
    now = now or datetime.now(timezone.utc)
    with connect(path) as connection:
        binding = connection.execute("SELECT * FROM task_bindings WHERE task_id = ?", (task_id,)).fetchone()
        if binding is None:
            return None
        pair = _receipt_and_queue(connection, str(binding["tenant_id"]), task_id, HANDOFF_KIND)
        if pair is None:
            return None
        receipt, queue = pair
        from opspilot.domain.s2_diagnosis import _draft_dict, _receipt_dict

        draft_row = connection.execute(
            "SELECT * FROM s2_handoff_drafts WHERE draft_id = ? AND tenant_id = ? AND task_id = ?",
            (receipt["draft_id"], binding["tenant_id"], task_id),
        ).fetchone()
        diagnosis = None
        if draft_row is not None:
            diagnosis_row = connection.execute(
                "SELECT * FROM s2_diagnosis_receipts WHERE receipt_id = ? AND tenant_id = ? AND task_id = ?",
                (draft_row["receipt_id"], binding["tenant_id"], task_id),
            ).fetchone()
            diagnosis = _receipt_dict(diagnosis_row) if diagnosis_row is not None else None
        draft = _draft_dict(draft_row) if draft_row is not None else None
        receipt_value = {
            "receipt_id": str(receipt["receipt_id"]),
            "task_id": str(receipt["task_id"]),
            "queue_entry_id": str(receipt["entry_id"]),
            "handoff_kind": str(receipt["handoff_kind"]),
            "draft_id": str(receipt["draft_id"]),
            "draft_version": int(receipt["draft_version"]),
            "draft_digest": str(receipt["draft_digest"]),
            "operation_id": str(receipt["operation_id"]),
            "canonical_request_digest": str(receipt["canonical_request_digest"]),
            "accepted_by_receiver_ref": str(receipt["accepted_by_receiver_ref"]),
            "accepted_by_actor_id": str(receipt["accepted_by_actor_id"]),
            "accepted_at": str(receipt["accepted_at"]),
            "receipt_digest": str(receipt["receipt_digest"]),
            "control_revision": int(receipt["control_revision"]),
            "request_id": str(receipt["request_id"]),
            "decision_id": int(receipt["decision_id"]),
            "credential_policy_version": int(receipt["credential_policy_version"]),
            "scope_policy_version": int(receipt["scope_policy_version"]),
            "grant_version": int(receipt["grant_version"]),
        }
        queue_value = {
            "entry_id": str(queue["entry_id"]),
            "queue_id": str(queue["receiver_queue_id"]),
            "receiver_label": RECEIVER_LABEL,
            "received_at": str(queue["received_at"]),
            "review_due_at": str(queue["review_due_at"]),
            "status": _handoff_status(queue, now),
        }
        return {
            "task_id": task_id,
            "task_status": str(binding["status"]),
            "business_outcome": "SCOPE_ESCALATED",
            "currentness": "ACCEPTED_AT_COMMIT",
            "reason_code": "LOCAL_HANDOFF_ACCEPTED_WAITING_REVIEW",
            "diagnosis_receipt": diagnosis,
            "draft": draft,
            "handoff_receipt": receipt_value,
            "queue_entry": queue_value,
            "handoff_status": queue_value["status"],
            "submitted": True,
            "scope_authorized": False,
            "recovered": False,
        }


def get_s2_handoff(
    path: str | Path,
    identity: TrustedIdentity,
    task_id: str,
    *,
    now: datetime | None = None,
) -> dict[str, object]:
    with connect(path) as connection:
        binding = _require_support_owner(connection, identity, task_id)
        control = connection.execute(
            "SELECT control_revision FROM task_controls WHERE tenant_id = ? AND task_id = ?",
            (identity.tenant_id, task_id),
        ).fetchone()
    from opspilot.domain.s2_diagnosis import get_s2_task_outcome

    result = get_s2_task_outcome(path, task_id)
    if now is not None:
        accepted = get_s2_handoff_outcome(path, task_id, now=now)
        if accepted is not None:
            accepted["control_revision"] = int(control["control_revision"]) if control else None
            return accepted
    result["control_revision"] = int(control["control_revision"]) if control else None
    result["task_status"] = str(binding["status"])
    return result
