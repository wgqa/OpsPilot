from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any


_PUBLIC_PAYLOAD_KEYS = {
    "command_id", "message_id", "run_id", "resume_run_id", "source_run_id", "task_id", "plan_hash", "action_id",
    "action_kind", "approval_id", "verification_id", "report_ref", "delivery_id",
    "sequence", "input_kind", "application_state", "control_revision", "error_code",
    "status", "decision", "reason_code", "task_status", "run_status", "attempt_id",
    "recovery_verified", "report_version", "delivery_status", "ledger_id",
    "chunk_id", "chunk_seq", "manifest_id", "answer_message_id", "model_attempt_id",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def _public_payload(raw: str | dict[str, Any]) -> str:
    try:
        value = json.loads(raw) if isinstance(raw, str) else raw
    except (TypeError, ValueError):
        value = {}
    if not isinstance(value, dict):
        value = {}
    # Events are small references to already committed facts. Never carry message
    # bodies, prompts, credentials, authorization material, or arbitrary objects.
    safe = {key: value[key] for key in sorted(_PUBLIC_PAYLOAD_KEYS) if key in value}
    return json.dumps(safe, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _session_for_event(
    connection: sqlite3.Connection, tenant_id: str, session_id: str | None, task_id: str | None
) -> str | None:
    if session_id:
        row = connection.execute(
            "SELECT session_id FROM sessions WHERE session_id = ? AND tenant_id = ?",
            (session_id, tenant_id),
        ).fetchone()
        if row is not None:
            return str(row["session_id"])
    if task_id:
        row = connection.execute(
            "SELECT session_id FROM session_task_links WHERE task_id = ? AND tenant_id = ? ORDER BY is_primary DESC, linked_at LIMIT 1",
            (task_id, tenant_id),
        ).fetchone()
        if row is not None:
            return str(row["session_id"])
    return None


def project_outbox_row(connection: sqlite3.Connection, row: sqlite3.Row | dict[str, Any]) -> bool:
    tenant_id = str(row["tenant_id"])
    task_id = str(row["task_id"]) if row["task_id"] is not None else None
    session_id = _session_for_event(
        connection,
        tenant_id,
        str(row["session_id"]) if row["session_id"] is not None else None,
        task_id,
    )
    if session_id is None:
        return False
    payload = _public_payload(str(row["payload_json"]))
    try:
        decoded = json.loads(payload)
    except ValueError:
        decoded = {}
    run_id = decoded.get("run_id") if isinstance(decoded, dict) else None
    if run_id is None and str(row["source_kind"]) == "RUN":
        run_id = str(row["source_id"])
    connection.execute(
        """INSERT OR IGNORE INTO session_events
           (event_id, source_kind, source_id, event_kind, tenant_id, session_id,
            task_id, run_id, happened_at, payload_json)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            str(row["event_id"]), str(row["source_kind"]), str(row["source_id"]),
            str(row["event_kind"]), tenant_id, session_id, task_id,
            str(run_id) if run_id is not None else None,
            str(row["created_at"]), payload,
        ),
    )
    return True


def write_outbox_event(
    connection: sqlite3.Connection,
    *,
    tenant_id: str,
    source_kind: str,
    source_id: str,
    event_kind: str,
    payload: dict[str, Any],
    task_id: str | None = None,
    session_id: str | None = None,
    created_at: str | None = None,
) -> None:
    """Insert an idempotent outbox fact and project it inside the caller's transaction."""
    happened = created_at or _now()
    event_id = f"event-{uuid.uuid4()}"
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    connection.execute(
        """INSERT OR IGNORE INTO domain_outbox
           (event_id, tenant_id, task_id, session_id, source_kind, source_id,
            event_kind, payload_json, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (event_id, tenant_id, task_id, session_id, source_kind, source_id, event_kind, serialized, happened),
    )
    row = connection.execute(
        """SELECT * FROM domain_outbox
           WHERE source_kind = ? AND source_id = ? AND event_kind = ?""",
        (source_kind, source_id, event_kind),
    ).fetchone()
    if row is not None:
        project_outbox_row(connection, row)


def project_outbox(path: str, *, limit: int = 500) -> dict[str, int]:
    from opspilot.domain.database import connect

    projected = 0
    skipped = 0
    with connect(path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        rows = connection.execute(
            """SELECT o.* FROM domain_outbox AS o
               LEFT JOIN session_events AS e
                 ON e.source_kind = o.source_kind AND e.source_id = o.source_id AND e.event_kind = o.event_kind
               WHERE e.event_id IS NULL ORDER BY o.created_at, o.event_id LIMIT ?""",
            (max(1, min(limit, 5000)),),
        ).fetchall()
        for row in rows:
            if project_outbox_row(connection, row):
                projected += 1
            else:
                skipped += 1
    return {"projected": projected, "skipped_without_session": skipped}


def reconcile_legacy_action_events(path: str) -> dict[str, int]:
    """Backfill event-only projections from committed action ledgers; never re-executes actions."""
    from opspilot.domain.database import connect

    inserted = 0
    with connect(path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        rows = connection.execute(
            """SELECT ledger_id, tenant_id, task_id, action_kind, action_id, committed_at
               FROM d3_action_ledgers WHERE status = 'COMMITTED' ORDER BY committed_at, ledger_id"""
        ).fetchall()
        for row in rows:
            event_kind = "REPAIR_COMMITTED" if str(row["action_kind"]) == "REPAIR" else "DELIVERY_COMMITTED"
            before = connection.total_changes
            write_outbox_event(
                connection,
                tenant_id=str(row["tenant_id"]), task_id=str(row["task_id"]),
                source_kind="ACTION_LEDGER", source_id=str(row["action_id"]),
                event_kind=event_kind,
                payload={"action_id": str(row["action_id"]), "action_kind": str(row["action_kind"]),
                         "status": "COMMITTED"},
                created_at=str(row["committed_at"]),
            )
            if connection.total_changes > before:
                inserted += 1
    projected = project_outbox(path)
    return {"action_events_reconciled": inserted, **projected}


def list_session_events(path: str, session_id: str, identity: Any, *, after_seq: int = 0, limit: int = 100) -> list[dict[str, Any]]:
    from opspilot.domain.database import connect
    from opspilot.domain.task_control import _verify_identity

    with connect(path) as connection:
        _verify_identity(connection, identity)
        session = connection.execute(
            "SELECT 1 FROM sessions WHERE session_id = ? AND tenant_id = ? AND owner_id = ?",
            (session_id, identity.tenant_id, identity.actor_id),
        ).fetchone()
        if session is None:
            from opspilot.domain.task_control import TaskControlError

            raise TaskControlError("SESSION_SCOPE_DENIED")
        rows = connection.execute(
            """SELECT event_seq, event_id, source_kind, source_id, event_kind, tenant_id,
                      session_id, task_id, run_id, happened_at, payload_json
               FROM session_events WHERE session_id = ? AND tenant_id = ? AND event_seq > ?
               ORDER BY event_seq LIMIT ?""",
            (session_id, identity.tenant_id, max(0, after_seq), max(1, min(limit, 500))),
        ).fetchall()
    return [
        {**{key: row[key] for key in row.keys()}, "payload": json.loads(str(row["payload_json"]))}
        for row in rows
    ]
