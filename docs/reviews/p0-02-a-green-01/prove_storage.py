"""Probe the existing TaskControl/outbox contracts without production edits."""
from __future__ import annotations

import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from unittest.mock import patch

sys.path.insert(0, str(Path.cwd()))

from opspilot.domain import task_control as tc
from opspilot.domain.database import connect, reset_fixture
from opspilot.domain.events import list_session_event_page, project_outbox


READ_CURRENT = """
    SELECT o.payload_json
      FROM messages AS m INDEXED BY ix_messages_task_seq
      JOIN task_run_inputs AS i ON i.message_id = m.message_id AND i.task_id = m.task_id
      JOIN domain_outbox AS o ON o.source_kind = 'RUN' AND o.source_id = i.run_id
                             AND o.event_kind = 'CRITICAL_INPUTS_APPLIED'
                             AND o.task_id = m.task_id AND o.tenant_id = m.tenant_id
     WHERE m.task_id = ? AND m.sequence = ? AND m.tenant_id = ?
"""


def load(db, binding):
    with connect(db) as connection:
        args = (binding["task_id"], "tenant-a")
        control = connection.execute(
            "SELECT * FROM task_controls WHERE task_id = ? AND tenant_id = ?", args,
        ).fetchone()
        query_args = (args[0], control["applied_critical_message_seq"], args[1])
        row = connection.execute(READ_CURRENT, query_args).fetchone()
        plan = [entry["detail"] for entry in connection.execute("EXPLAIN QUERY PLAN " + READ_CURRENT, query_args)]
        return dict(control), json.loads(row[0])["condition_state_v1"] if row else {}, plan


def probe(db):
    reset_fixture(db, "S1_POS")
    owner = tc.trusted_identity(db, "support-a")
    session_id = tc.create_session(db, owner)["session_id"]
    task = tc.create_task_with_initial_run(
        db, owner, session_id=session_id, service_id="orders-demo",
        integration_id="integration-a", ticket_id="INC-A-001", initial_message="Investigate",
        idempotency_key="probe-create",
    )
    initial, items, _ = load(db, task)
    assert not items and initial["applied_critical_message_seq"] == 0
    original_outbox = tc._insert_outbox
    operations = []
    for version, (kind, text) in enumerate(
        [("ADD", "From 10 to 11"), ("REPLACE", "All day"), ("REVOKE", "Withdraw the window")], 1,
    ):
        before, items, _ = load(db, task)
        args = dict(session_id=session_id, task_id=task["task_id"], input_kind="CORRECT_TASK_INPUT",
                    body=text, expected_control_revision=before["control_revision"],
                    idempotency_key=f"probe-op-{version}")
        event = {"item_id": "window", "operation": kind, "expected_version": version - 1,
                 "version": version, "operation_id": args["idempotency_key"],
                 "confirmed_at_revision": before["control_revision"]}

        def extended_outbox(connection, tenant, task_id, session, source_kind, source_id, event_kind, payload):
            if event_kind == "MESSAGE_ACCEPTED":
                row = connection.execute(
                    "SELECT body_digest FROM messages WHERE message_id = ?", (payload["message_id"],),
                ).fetchone()
                payload = {**payload, "condition_change_v1": {
                    **event, "source_message_id": payload["message_id"], "source_digest": row[0],
                }}
            elif event_kind == "CRITICAL_INPUTS_APPLIED":
                row = connection.execute(
                    """SELECT o.payload_json FROM messages m JOIN domain_outbox o
                         ON o.source_kind='COMMAND' AND o.source_id=m.command_id AND o.event_kind='MESSAGE_ACCEPTED'
                       WHERE m.message_id=?""", (payload["message_ids"][-1],),
                ).fetchone()
                change = json.loads(row[0])["condition_change_v1"]
                assert change["expected_version"] == items.get("window", {}).get("version", 0)
                payload = {**payload, "condition_state_v1": {"window": {
                    **change, "state": "REVOKED" if change["operation"] == "REVOKE" else "ACTIVE",
                    "applied_revision": payload["control_revision"],
                }}}
            original_outbox(connection, tenant, task_id, session, source_kind, source_id, event_kind, payload)

        with patch.object(tc, "_insert_outbox", new=extended_outbox):
            accepted = tc.admit_task_message(db, owner, **args)
            assert tc.admit_task_message(db, owner, **args) == accepted
            try:
                tc.admit_task_message(db, owner, **{**args, "body": "different payload"})
            except tc.IdempotencyConflict:
                pass
            else:
                raise AssertionError("same key and different digest must conflict")
            pending, not_applied, _ = load(db, task)
            assert pending["pending_critical_message_seq"] == accepted["sequence"] and not_applied == items
            tc.claim_task_run(db, owner, accepted["run_id"])
            applied = tc.apply_pending_critical_inputs(db, owner, accepted["run_id"])
            assert len(applied["inputs"]) == 1
            assert not tc.apply_pending_critical_inputs(db, owner, accepted["run_id"])["inputs"]
            tc.finish_task_run(db, owner, accepted["run_id"], "WAITING_INPUT")
        control, updated, plan = load(db, task)
        assert control["applied_critical_message_seq"] == accepted["sequence"] and control["pending_critical_message_seq"] is None
        assert updated["window"]["version"] == version
        assert updated["window"]["applied_revision"] == applied["expected_control_revision"]
        with connect(db) as connection:
            original_receipt = connection.execute(
                "SELECT result_json FROM commands WHERE command_id=?", (accepted["command_id"],),
            ).fetchone()[0]
            assert json.loads(original_receipt) == accepted == tc.admit_task_message(db, owner, **args)
        operations.append(updated["window"])
    assert updated["window"]["state"] == "REVOKED"
    assert all("SEARCH" in step for step in plan), plan
    assert project_outbox(str(db))["projected"] == 0
    public = list_session_event_page(str(db), session_id, owner, limit=100)
    assert public["items"] and "condition_state_v1" not in json.dumps(public)
    assert "condition_change_v1" not in json.dumps(public)
    print(json.dumps({"operations": operations, "query_plan": plan, "public_payload_unchanged": True,
                      "command_receipts_unchanged": True, "public_event_count": len(public["items"])}, indent=2))


if __name__ == "__main__":
    with TemporaryDirectory(prefix="opspilot-p002-storage-") as directory:
        probe(Path(directory) / "domain.sqlite3")
