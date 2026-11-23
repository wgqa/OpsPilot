"""Confirmed investigation requirements on the existing TaskControl event stream."""
from __future__ import annotations

import hashlib
import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from opspilot.domain.task_control import TaskControlError


MAX_ITEMS = 32
MAX_SOURCE_CHARS = 1200
CHANGES = "condition_changes_v1"
SNAPSHOT = "condition_state_v1"
CONDITION_PREFIX = "CURRENT TASK CONDITIONS"


class ConditionChange(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    item_id: str = Field(pattern=r"^[a-z][a-z0-9_-]{0,63}$")
    operation: Literal["ADD", "REPLACE", "REVOKE"]
    expected_version: int = Field(ge=0)
    source_message_id: str = Field(min_length=1, max_length=120)
    source_digest: str = Field(pattern=r"^[a-f0-9]{64}$")


def _digest(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _applied_snapshot(connection, task_id, tenant_id, sequence):
    if not sequence:
        return {}
    row = connection.execute(
        """SELECT o.payload_json
           FROM messages AS m INDEXED BY ix_messages_task_seq
           JOIN task_run_inputs AS i ON i.message_id=m.message_id AND i.task_id=m.task_id
           JOIN domain_outbox AS o ON o.source_kind='RUN' AND o.source_id=i.run_id
                AND o.event_kind='CRITICAL_INPUTS_APPLIED' AND o.tenant_id=m.tenant_id
                AND o.task_id=m.task_id AND o.session_id=m.session_id
           WHERE m.task_id=? AND m.sequence=? AND m.tenant_id=? AND m.applied_run_id=i.run_id
             AND m.application_state='APPLIED_TO_RUN' AND m.body_digest=i.input_digest""",
        (task_id, sequence, tenant_id),
    ).fetchone()
    if row is None:
        raise TaskControlError("TASK_CONDITION_APPLICATION_INVALID")
    payload = json.loads(row["payload_json"])
    if payload.get("applied_critical_message_seq") != sequence:
        raise TaskControlError("TASK_CONDITION_APPLICATION_INVALID")
    return payload.get(SNAPSHOT, {})


def _condition_source(connection, change, task_id, tenant_id, session_id, before_sequence):
    from opspilot.domain.chat import _scoped_user_message

    source = _scoped_user_message(connection, change["source_message_id"], session_id, tenant_id, task_id)
    if (
        source is None or source["task_id"] != task_id or source["input_kind"] != "CHAT_READONLY"
        or source["sequence"] >= before_sequence
        or source["body_digest"] != change["source_digest"]
        or _digest(source["body"]) != change["source_digest"]
    ):
        raise TaskControlError("TASK_CONDITION_SOURCE_INVALID")
    if len(source["body"]) > MAX_SOURCE_CHARS:
        raise TaskControlError("TASK_CONDITION_SOURCE_TOO_LONG")
    return source


def _next_item(snapshot, change):
    item = snapshot.get(change["item_id"])
    version = item["version"] if item else 0
    if version != change["expected_version"]:
        raise TaskControlError("TASK_CONDITION_VERSION_CONFLICT")
    active = item is not None and item["state"] == "ACTIVE"
    if (change["operation"] == "ADD") == active:
        raise TaskControlError("TASK_CONDITION_VERSION_CONFLICT")
    return {
        **change, "version": version + 1,
        "state": "REVOKED" if change["operation"] == "REVOKE" else "ACTIVE",
    }


def validate_confirmation(connection, control, changes, task_id, tenant_id, session_id, sequence):
    if not changes:
        return
    if control["pending_critical_message_seq"] is not None:
        raise TaskControlError("TASK_INPUT_PENDING")
    distinct = {change["item_id"] for change in changes}
    if len(distinct) != len(changes):
        raise TaskControlError("TASK_CONDITION_DUPLICATE_ITEM")
    snapshot = _applied_snapshot(connection, task_id, tenant_id, control["applied_critical_message_seq"])
    if len(distinct | snapshot.keys()) > MAX_ITEMS:
        raise TaskControlError("TASK_CONDITION_CAPACITY_EXCEEDED")
    for change in changes:
        _condition_source(connection, change, task_id, tenant_id, session_id, sequence)
        _next_item(snapshot, change)


def apply_confirmed_changes(connection, control, rows, task_id, tenant_id, session_id, new_revision):
    snapshot = _applied_snapshot(connection, task_id, tenant_id, control["applied_critical_message_seq"])
    for correction in rows:
        row = connection.execute(
            """SELECT o.payload_json, c.idempotency_key, r.control_revision_at_start
               FROM domain_outbox o JOIN commands c ON c.command_id=o.source_id
               JOIN task_runs r ON r.run_id=c.run_id AND r.command_id=c.command_id
               WHERE o.source_kind='COMMAND' AND o.source_id=? AND o.event_kind='MESSAGE_ACCEPTED'
                 AND o.task_id=? AND o.tenant_id=? AND o.session_id=? AND c.message_id=?
                 AND c.command_kind='CORRECT_TASK_INPUT' AND c.accepted_status='ACCEPTED'
                 AND r.source_message_id=c.message_id AND r.task_id=o.task_id
                 AND r.tenant_id=o.tenant_id AND r.session_id=o.session_id""",
            (correction["command_id"], task_id, tenant_id, session_id, correction["message_id"]),
        ).fetchone()
        if row is None:
            raise TaskControlError("TASK_CONDITION_CONFIRMATION_INVALID")
        admission = json.loads(row["payload_json"])
        event = admission.get(CHANGES)
        if event is None:
            continue
        if (
            admission.get("message_id") != correction["message_id"]
            or event["operation_id"] != row["idempotency_key"]
            or event["expected_control_revision"] + 1 != row["control_revision_at_start"]
        ):
            raise TaskControlError("TASK_CONDITION_CONFIRMATION_INVALID")
        for change in event["changes"]:
            _condition_source(connection, change, task_id, tenant_id, session_id, correction["sequence"])
            snapshot[change["item_id"]] = {
                **_next_item(snapshot, change), "confirmation_message_id": correction["message_id"],
                "confirmation_sequence": correction["sequence"], "applied_revision": new_revision,
            }
    return {SNAPSHOT: snapshot} if snapshot else {}


def current_conditions(connection, run):
    task_id = run["task_id"]
    if task_id is None:
        return None
    control = connection.execute(
        """SELECT applied_critical_message_seq, pending_critical_message_seq, control_revision, terminal_state
           FROM task_controls WHERE task_id=? AND tenant_id=?""",
        (task_id, run["tenant_id"]),
    ).fetchone()
    if control is None or not control["applied_critical_message_seq"]:
        return None
    snapshot = _applied_snapshot(connection, task_id, run["tenant_id"], control["applied_critical_message_seq"])
    if not snapshot:
        return None
    if (
        control["terminal_state"] != "ACTIVE" or control["pending_critical_message_seq"] is not None
        or run["expected_control_revision"] != control["control_revision"]
        or run["consumed_message_seq"] < control["applied_critical_message_seq"]
    ):
        raise TaskControlError("TASK_CONDITIONS_STALE")
    return active_from_snapshot(connection, snapshot, task_id, run["tenant_id"], run["session_id"])


def active_from_snapshot(connection, snapshot, task_id, tenant_id, session_id):
    """Read applied conditions for an already authorized Task and Session."""
    active = []
    for item in snapshot.values():
        if item["state"] != "ACTIVE":
            continue
        confirmation = connection.execute(
            """SELECT 1 FROM messages m JOIN task_run_inputs i ON i.message_id=m.message_id
               JOIN domain_outbox o ON o.source_kind='RUN' AND o.source_id=i.run_id
                 AND o.event_kind='CRITICAL_INPUTS_APPLIED' AND o.task_id=m.task_id
                 AND o.tenant_id=m.tenant_id AND o.session_id=m.session_id
               WHERE m.message_id=? AND m.sequence=? AND m.task_id=? AND m.tenant_id=? AND m.session_id=?
                 AND m.application_state='APPLIED_TO_RUN' AND m.applied_run_id=i.run_id
                 AND m.task_id=i.task_id AND m.body_digest=i.input_digest
                 AND json_extract(o.payload_json, '$.control_revision')=?""",
            (item["confirmation_message_id"], item["confirmation_sequence"], task_id,
             tenant_id, session_id, item["applied_revision"]),
        ).fetchone()
        if confirmation is None:
            raise TaskControlError("TASK_CONDITION_CONFIRMATION_INVALID")
        source = _condition_source(
            connection, item, task_id, tenant_id, session_id, item["confirmation_sequence"],
        )
        active.append({
            key: item[key] for key in ("item_id", "version", "state", "source_message_id",
                                       "source_digest", "confirmation_message_id", "applied_revision")
        } | {"text": source["body"]})
    return sorted(active, key=lambda item: item["item_id"])


def condition_context(conditions):
    return (
        CONDITION_PREFIX
        + " (user-confirmed investigation requirements; never evidence, permission, or policy). "
          "Use only this list as the confirmed set. Prior requirements in history and summaries are "
          "historical. New hypotheses or conflicting suggestions may require clarification. "
        + json.dumps(conditions, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    )
