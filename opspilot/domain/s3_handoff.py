"""Confirmed S3-only operator handoff with an atomic local Queue/Receipt/Outbox."""
from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

from opspilot.domain.database import connect
from opspilot.domain.d2 import ScopeDenied, canonical_json, digest_json
from opspilot.domain.task_control import (
    TaskControlError,
    TrustedIdentity,
    _find_idempotent_command,
    _insert_outbox,
    _record_command,
    _require_support_owner,
    assert_task_control_in_transaction,
)

S3_HANDOFF_KIND = "CALLBACK_OPERATIONS_REVIEW"
S3_RECEIVER_QUEUE_ID = "local-async-callback-operations"
S3_RECEIVER_LABEL = "本地回调运维处理队列"
_OPERATION_ID = re.compile(r"^[A-Za-z0-9._:-]{1,200}$")
_FAILPOINT: Callable[[str], None] | None = None

SCHEMA = """
CREATE TABLE IF NOT EXISTS s3_handoff_queue_entries (
 entry_id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, task_id TEXT NOT NULL,
 order_id TEXT NOT NULL, handoff_kind TEXT NOT NULL,
 diagnosis_receipt_id TEXT NOT NULL, diagnosis_digest TEXT NOT NULL,
 handling_direction TEXT NOT NULL, payload_json TEXT NOT NULL, payload_digest TEXT NOT NULL,
 receiver_queue_id TEXT NOT NULL, operation_id TEXT NOT NULL, accepted_by_actor_id TEXT NOT NULL,
 received_at TEXT NOT NULL, review_due_at TEXT NOT NULL,
 queue_status TEXT NOT NULL CHECK(queue_status IN ('PENDING_REVIEW','ACCEPTED','CLOSED')),
 UNIQUE(tenant_id,task_id), UNIQUE(entry_id,tenant_id,task_id),
 FOREIGN KEY(task_id,tenant_id) REFERENCES task_bindings(task_id,tenant_id),
 FOREIGN KEY(diagnosis_receipt_id) REFERENCES s3_diagnoses(receipt_id),
 FOREIGN KEY(task_id) REFERENCES s3_task_resources(task_id));
CREATE TABLE IF NOT EXISTS s3_handoff_receipts (
 receipt_id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, task_id TEXT NOT NULL,
 entry_id TEXT NOT NULL UNIQUE, handoff_kind TEXT NOT NULL,
 diagnosis_receipt_id TEXT NOT NULL, diagnosis_digest TEXT NOT NULL,
 operation_id TEXT NOT NULL, canonical_request_digest TEXT NOT NULL,
 business_outcome TEXT NOT NULL CHECK(business_outcome='HANDOFF_ACCEPTED'),
 accepted_by_actor_id TEXT NOT NULL, accepted_at TEXT NOT NULL,
 control_revision INTEGER NOT NULL, receipt_digest TEXT NOT NULL,
 UNIQUE(tenant_id,task_id), UNIQUE(receipt_id,tenant_id,task_id),
 FOREIGN KEY(entry_id,tenant_id,task_id)
   REFERENCES s3_handoff_queue_entries(entry_id,tenant_id,task_id),
 FOREIGN KEY(diagnosis_receipt_id) REFERENCES s3_diagnoses(receipt_id));
CREATE INDEX IF NOT EXISTS ix_s3_handoff_status ON s3_handoff_queue_entries(queue_status,received_at);
CREATE TRIGGER IF NOT EXISTS s3_handoff_receipt_immutable_update BEFORE UPDATE ON s3_handoff_receipts
 BEGIN SELECT RAISE(ABORT,'S3 handoff receipt is immutable'); END;
CREATE TRIGGER IF NOT EXISTS s3_handoff_receipt_immutable_delete BEFORE DELETE ON s3_handoff_receipts
 BEGIN SELECT RAISE(ABORT,'S3 handoff receipt is immutable'); END;
"""


def _failpoint(name: str) -> None:
    if _FAILPOINT is not None:
        _FAILPOINT(name)
    elif os.environ.get("OPSPILOT_ENABLE_S3_FAILPOINTS") == "1" and os.environ.get("OPSPILOT_S3_FAIL_AT") == name:
        if os.environ.get("OPSPILOT_S3_CRASH_PROCESS") == "1":
            os._exit(87)
        raise RuntimeError(f"S3 handoff failpoint: {name}")


def _request_digest(
    identity: TrustedIdentity, *, task_id: str, operation_id: str,
    diagnosis_receipt_id: str, diagnosis_digest: str, expected_control_revision: int,
) -> str:
    request = {
        "schema_version": 1, "method": "POST", "route": f"/api/tasks/{task_id}/s3-handoff/submit",
        "tenant_id": identity.tenant_id, "actor_id": identity.actor_id, "task_id": task_id,
        "operation_id": operation_id, "diagnosis_receipt_id": diagnosis_receipt_id,
        "diagnosis_digest": diagnosis_digest, "expected_control_revision": expected_control_revision,
        "handoff_kind": S3_HANDOFF_KIND,
    }
    return hashlib.sha256(canonical_json(request).encode("utf-8")).hexdigest()


def _response(receipt: sqlite3.Row, entry: sqlite3.Row, *, replayed: bool) -> dict[str, object]:
    return {
        "status": "ACCEPTED", "business_outcome": "HANDOFF_ACCEPTED",
        "receipt_id": str(receipt["receipt_id"]), "queue_entry_id": str(entry["entry_id"]),
        "task_id": str(receipt["task_id"]), "order_id": str(entry["order_id"]),
        "operation_id": str(receipt["operation_id"]),
        "handoff_kind": str(receipt["handoff_kind"]),
        "handling_direction": str(entry["handling_direction"]),
        "receiver_queue_id": str(entry["receiver_queue_id"]),
        "queue_status": str(entry["queue_status"]), "accepted_at": str(receipt["accepted_at"]),
        "recovered": False, "replayed": replayed,
        "callback_resent": False, "order_recovered": False,
    }


def _load_receipt(connection: sqlite3.Connection, tenant_id: str, task_id: str):
    return connection.execute(
        """SELECT r.*,q.entry_id,q.order_id,q.handling_direction,q.receiver_queue_id,q.queue_status,
                  q.payload_json,q.payload_digest,q.received_at,q.review_due_at
           FROM s3_handoff_receipts r JOIN s3_handoff_queue_entries q
             ON q.entry_id=r.entry_id AND q.tenant_id=r.tenant_id AND q.task_id=r.task_id
           WHERE r.tenant_id=? AND r.task_id=?""",
        (tenant_id, task_id),
    ).fetchone()


def submit_s3_handoff(
    path: str | Path,
    identity: TrustedIdentity,
    *,
    task_id: str,
    operation_id: str,
    diagnosis_receipt_id: str,
    diagnosis_digest: str,
    expected_control_revision: int,
) -> dict[str, object]:
    """Accept one owner-confirmed, current S3 diagnosis into its local operator queue."""
    if (
        not isinstance(operation_id, str) or not _OPERATION_ID.fullmatch(operation_id)
        or operation_id.strip() != operation_id
        or not isinstance(diagnosis_receipt_id, str) or not diagnosis_receipt_id or len(diagnosis_receipt_id) > 200
        or not re.fullmatch(r"[0-9a-f]{64}", diagnosis_digest)
        or isinstance(expected_control_revision, bool) or not isinstance(expected_control_revision, int)
        or expected_control_revision < 0
    ):
        raise TaskControlError("INVALID_REQUEST")
    request_digest = _request_digest(
        identity, task_id=task_id, operation_id=operation_id,
        diagnosis_receipt_id=diagnosis_receipt_id, diagnosis_digest=diagnosis_digest,
        expected_control_revision=expected_control_revision,
    )
    accepted: dict[str, object] | None = None
    with connect(path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        binding = _require_support_owner(connection, identity, task_id)
        from opspilot.domain.s3 import get_s3_binding, s3_outcome_in_transaction
        try:
            s3_binding = get_s3_binding(connection, task_id)
        except ScopeDenied as error:
            raise TaskControlError("S3_SCOPE_AUTHORIZATION_DENIED") from error
        target_ref = f"{task_id}:{S3_HANDOFF_KIND}"
        prior = _find_idempotent_command(
            connection, identity, operation_id, "S3_HANDOFF_SUBMIT", target_ref, request_digest,
        )
        if prior is not None:
            prior["replayed"] = True
            return prior
        existing = _load_receipt(connection, identity.tenant_id, task_id)
        if existing is not None:
            if (
                str(existing["diagnosis_receipt_id"]) != diagnosis_receipt_id
                or str(existing["diagnosis_digest"]) != diagnosis_digest
            ):
                raise TaskControlError("S3_HANDOFF_ALREADY_ACCEPTED")
            result = _response(existing, existing, replayed=True)
            _record_command(
                connection, command_id=f"s3-handoff-command-{uuid.uuid4()}", identity=identity,
                command_kind="S3_HANDOFF_SUBMIT", target_ref=target_ref,
                idempotency_key=operation_id, request_digest=request_digest,
                accepted_status="ACCEPTED", result=result,
            )
            return result

        control = assert_task_control_in_transaction(
            connection, identity.tenant_id, task_id, expected_control_revision,
        )
        if str(binding["status"]) != "WAITING_HANDOFF":
            raise TaskControlError("S3_DIAGNOSIS_NOT_HANDOFF_READY")
        active = connection.execute(
            """SELECT 1 FROM task_runs WHERE tenant_id=? AND task_id=? AND kind!='CHAT_READONLY'
               AND status IN ('QUEUED','RUNNING','WAITING_INPUT','WAITING_APPROVAL','INTERRUPTED_RECOVERABLE') LIMIT 1""",
            (identity.tenant_id, task_id),
        ).fetchone()
        if active is not None:
            raise TaskControlError("TASK_RUN_BUSY")
        current = s3_outcome_in_transaction(connection, task_id)
        if (
            current is None or current["currentness"] != "CURRENT"
            or current["receipt_id"] != diagnosis_receipt_id
            or not current.get("handoff_allowed")
            or current.get("handling_direction") not in {"CONTACT_CALLBACK_OPERATOR", "CONTACT_RECEIVER_OPERATOR"}
        ):
            raise TaskControlError("S3_DIAGNOSIS_NOT_HANDOFF_READY")
        diagnosis = connection.execute(
            "SELECT * FROM s3_diagnoses WHERE tenant_id=? AND task_id=? AND receipt_id=?",
            (identity.tenant_id, task_id, diagnosis_receipt_id),
        ).fetchone()
        if diagnosis is None or str(diagnosis["digest"]) != diagnosis_digest:
            raise TaskControlError("S3_DIAGNOSIS_STALE")
        if int(control["control_revision"]) != expected_control_revision:
            raise TaskControlError("TASK_CONTROL_STALE")

        now = datetime.now(timezone.utc)
        accepted_at = now.isoformat().replace("+00:00", "Z")
        due_at = (now + timedelta(hours=72)).isoformat().replace("+00:00", "Z")
        entry_id = f"s3-queue-{uuid.uuid4()}"
        receipt_id = f"s3-handoff-{uuid.uuid4()}"
        payload = {
            "schema_version": 1, "task_id": task_id, "tenant_id": identity.tenant_id,
            "order_id": str(s3_binding["order_id"]), "service_id": str(s3_binding["service_id"]),
            "integration_id": str(s3_binding["integration_id"]),
            "diagnosis_receipt_id": diagnosis_receipt_id, "diagnosis_digest": diagnosis_digest,
            "business_outcome": str(diagnosis["outcome"]),
            "handling_direction": str(current["handling_direction"]),
            "evidence_ids": json.loads(str(diagnosis["evidence_ids_json"])),
            "control_revision": expected_control_revision,
            "requested_by_actor_id": identity.actor_id,
        }
        payload_digest = digest_json(payload)
        result = {
            "status": "ACCEPTED", "business_outcome": "HANDOFF_ACCEPTED",
            "receipt_id": receipt_id, "queue_entry_id": entry_id, "task_id": task_id,
            "order_id": str(s3_binding["order_id"]), "handoff_kind": S3_HANDOFF_KIND,
            "handling_direction": str(current["handling_direction"]),
            "receiver_queue_id": S3_RECEIVER_QUEUE_ID, "queue_status": "PENDING_REVIEW",
            "accepted_at": accepted_at, "operation_id": operation_id, "recovered": False,
            "replayed": False, "callback_resent": False, "order_recovered": False,
        }
        _record_command(
            connection, command_id=f"s3-handoff-command-{uuid.uuid4()}", identity=identity,
            command_kind="S3_HANDOFF_SUBMIT", target_ref=target_ref,
            idempotency_key=operation_id, request_digest=request_digest,
            accepted_status="ACCEPTED", result=result,
        )
        _failpoint("after_command_before_queue")
        connection.execute(
            """INSERT INTO s3_handoff_queue_entries
               (entry_id,tenant_id,task_id,order_id,handoff_kind,diagnosis_receipt_id,diagnosis_digest,
                handling_direction,payload_json,payload_digest,receiver_queue_id,operation_id,
                accepted_by_actor_id,received_at,review_due_at,queue_status)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,'PENDING_REVIEW')""",
            (entry_id,identity.tenant_id,task_id,str(s3_binding["order_id"]),S3_HANDOFF_KIND,
             diagnosis_receipt_id,diagnosis_digest,str(current["handling_direction"]),canonical_json(payload),
             payload_digest,S3_RECEIVER_QUEUE_ID,operation_id,identity.actor_id,accepted_at,due_at),
        )
        _failpoint("after_queue_before_receipt")
        receipt_body = {
            "schema_version": 1, "receipt_id": receipt_id, "entry_id": entry_id,
            "tenant_id": identity.tenant_id, "task_id": task_id, "order_id": str(s3_binding["order_id"]),
            "handoff_kind": S3_HANDOFF_KIND, "diagnosis_receipt_id": diagnosis_receipt_id,
            "diagnosis_digest": diagnosis_digest, "operation_id": operation_id,
            "canonical_request_digest": request_digest, "business_outcome": "HANDOFF_ACCEPTED",
            "accepted_by_actor_id": identity.actor_id, "accepted_at": accepted_at,
            "control_revision": expected_control_revision, "payload_digest": payload_digest,
        }
        receipt_digest = digest_json(receipt_body)
        connection.execute(
            """INSERT INTO s3_handoff_receipts
               (receipt_id,tenant_id,task_id,entry_id,handoff_kind,diagnosis_receipt_id,diagnosis_digest,
                operation_id,canonical_request_digest,business_outcome,accepted_by_actor_id,accepted_at,
                control_revision,receipt_digest)
               VALUES(?,?,?,?,?,?,?,?,?,'HANDOFF_ACCEPTED',?,?,?,?)""",
            (receipt_id,identity.tenant_id,task_id,entry_id,S3_HANDOFF_KIND,diagnosis_receipt_id,
             diagnosis_digest,operation_id,request_digest,identity.actor_id,accepted_at,
             expected_control_revision,receipt_digest),
        )
        _failpoint("after_receipt_before_task")
        updated = connection.execute(
            "UPDATE task_bindings SET status='COMPLETED' WHERE tenant_id=? AND task_id=? AND status='WAITING_HANDOFF'",
            (identity.tenant_id, task_id),
        )
        if updated.rowcount != 1:
            raise TaskControlError("S3_DIAGNOSIS_NOT_HANDOFF_READY")
        _insert_outbox(
            connection, identity.tenant_id, task_id, None, "S3_HANDOFF_RECEIPT", receipt_id,
            "S3_HANDOFF_ACCEPTED", {
                **result, "task_status": "COMPLETED", "outcome_means_recovered": False,
                "scope_authorized": False,
            },
        )
        _failpoint("after_outbox_before_commit")
        accepted = result
    _failpoint("after_commit_before_http_response")
    assert accepted is not None
    return accepted


def get_s3_handoff_outcome(
    path: str | Path, task_id: str, identity: TrustedIdentity,
) -> dict[str, object] | None:
    """Read current owner state or a receipt-only same-tenant APPROVER audit view."""
    with connect(path) as connection:
        binding = connection.execute(
            "SELECT tenant_id,actor_id,service_id FROM task_bindings WHERE task_id=? AND tenant_id=?",
            (task_id, identity.tenant_id),
        ).fetchone()
        if binding is None:
            raise ScopeDenied("TASK_SCOPE_DENIED")
        trusted = connection.execute(
            "SELECT 1 FROM trusted_operators WHERE tenant_id=? AND actor_id=? AND role=?",
            (identity.tenant_id, identity.actor_id, identity.role),
        ).fetchone()
        if trusted is None:
            raise ScopeDenied("TASK_SCOPE_DENIED")
        receipt = _load_receipt(connection, str(binding["tenant_id"]), task_id)
        if identity.role == "APPROVER":
            if receipt is None:
                raise ScopeDenied("S3_HISTORICAL_AUDIT_RECEIPT_REQUIRED")
            return {
                "business_outcome": "HANDOFF_ACCEPTED", "currentness": "HISTORICALLY_ACCEPTED",
                "status": "ACCEPTED", "task_id": task_id, "submitted": True,
                "handoff_receipt": {
                    "receipt_id": str(receipt["receipt_id"]), "entry_id": str(receipt["entry_id"]),
                    "receipt_digest": str(receipt["receipt_digest"]),
                    "diagnosis_receipt_id": str(receipt["diagnosis_receipt_id"]),
                    "diagnosis_digest": str(receipt["diagnosis_digest"]),
                    "accepted_by_actor_id": str(receipt["accepted_by_actor_id"]),
                    "accepted_at": str(receipt["accepted_at"]),
                    "control_revision": int(receipt["control_revision"]),
                },
                "queue_entry": {
                    "entry_id": str(receipt["entry_id"]), "queue_status": str(receipt["queue_status"]),
                    "received_at": str(receipt["received_at"]), "review_due_at": str(receipt["review_due_at"]),
                    "payload_digest": str(receipt["payload_digest"]),
                },
                "recovered": False, "callback_resent": False, "order_recovered": False,
            }
        if identity.role != "SUPPORT" or str(binding["actor_id"]) != identity.actor_id:
            raise ScopeDenied("TASK_SCOPE_DENIED")
        from opspilot.domain.s3 import get_s3_binding
        get_s3_binding(connection, task_id)
        if receipt is None:
            from opspilot.domain.s3 import s3_outcome_in_transaction
            current = s3_outcome_in_transaction(connection, task_id)
            if current is not None:
                diagnosis = connection.execute(
                    "SELECT digest,control_revision FROM s3_diagnoses WHERE receipt_id=? AND task_id=?",
                    (current["receipt_id"], task_id),
                ).fetchone()
                binding = get_s3_binding(connection, task_id)
                if diagnosis is not None:
                    current["diagnosis_digest"] = str(diagnosis["digest"])
                    current["control_revision"] = int(diagnosis["control_revision"])
                current["order_id"] = str(binding["order_id"])
            return {"business_outcome": "HANDOFF_READY" if current and current.get("handoff_allowed") else (current["outcome"] if current else "NO_DIAGNOSIS"),
                    "currentness": current["currentness"] if current else "NO_DIAGNOSIS",
                    "handling_direction": current.get("handling_direction") if current else None,
                    "handoff_allowed": bool(current and current.get("handoff_allowed")),
                    "diagnosis_receipt": current,
                    "handoff_receipt": None, "queue_entry": None, "submitted": False,
                    "recovered": False, "callback_resent": False, "order_recovered": False}
        response = _response(receipt, receipt, replayed=True)
        return {
            **response, "business_outcome": "HANDOFF_ACCEPTED", "currentness": "HISTORICALLY_ACCEPTED",
            "handoff_receipt": {
                "receipt_id": str(receipt["receipt_id"]), "entry_id": str(receipt["entry_id"]),
                "receipt_digest": str(receipt["receipt_digest"]), "diagnosis_receipt_id": str(receipt["diagnosis_receipt_id"]),
                "diagnosis_digest": str(receipt["diagnosis_digest"]), "accepted_by_actor_id": str(receipt["accepted_by_actor_id"]),
                "accepted_at": str(receipt["accepted_at"]), "control_revision": int(receipt["control_revision"]),
            },
            "queue_entry": {
                "entry_id": str(receipt["entry_id"]), "queue_id": str(receipt["receiver_queue_id"]),
                "queue_status": str(receipt["queue_status"]), "received_at": str(receipt["received_at"]),
                "review_due_at": str(receipt["review_due_at"]), "payload_digest": str(receipt["payload_digest"]),
            },
            "submitted": True, "recovered": False, "callback_resent": False, "order_recovered": False,
        }
