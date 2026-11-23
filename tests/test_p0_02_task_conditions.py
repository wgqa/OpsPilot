from __future__ import annotations

import hashlib
import json

import pytest

from opspilot.domain import task_control as tc
from opspilot.domain.chat import _prepare_context
from opspilot.domain.context_engineering import ContextBudgetExceeded
from opspilot.domain.database import connect
from opspilot.domain.investigation_context import load_investigation_context, validate_task_run_context_in_transaction
from opspilot.domain.task_conditions import CHANGES, SNAPSHOT, ConditionChange, current_conditions


@pytest.fixture
def task(demo_db):
    owner = tc.trusted_identity(demo_db, "support-a")
    session = tc.create_session(demo_db, owner)["session_id"]
    created = tc.create_task_with_initial_run(
        demo_db, owner, session_id=session, service_id="orders-demo", integration_id="integration-a",
        ticket_id="INC-A-001", initial_message="Investigate the 401.", idempotency_key="condition-task",
    )
    return owner, created["task_id"], session


def admit(db, task, body, key, *, correction=False, **kwargs):
    owner, task_id, session_id = task
    return tc.admit_task_message(
        db, owner, session_id=session_id, task_id=task_id, body=body, idempotency_key=key,
        input_kind="CORRECT_TASK_INPUT" if correction else "CHAT_READONLY", **kwargs,
    )


def apply(db, task, receipt):
    owner, _, _ = task
    tc.claim_task_run(db, owner, receipt["run_id"])
    return tc.apply_pending_critical_inputs(db, owner, receipt["run_id"])


def change(item_id, message_id, body, operation="ADD", version=0):
    return ConditionChange(
        item_id=item_id, operation=operation, source_message_id=message_id, expected_version=version,
        source_digest=hashlib.sha256(body.encode()).hexdigest(),
    )


def test_conditions_become_current_only_on_application_and_keep_original_receipt(demo_db, task):
    source = admit(demo_db, task, "Only E7", "input")
    edit = change("event", source["message_id"], "Only E7")
    options = dict(correction=True, expected_control_revision=0, condition_changes=[edit])
    confirmed = admit(demo_db, task, "Confirm the selected condition", "confirm", **options)
    with connect(demo_db) as connection:
        run = connection.execute("SELECT * FROM task_runs WHERE run_id=?", (confirmed["run_id"],)).fetchone()
        assert current_conditions(connection, run) is None
    applied = apply(demo_db, task, confirmed)
    assert applied["expected_control_revision"] == 2 and applied["applied_critical_message_seq"] == confirmed["sequence"]
    assert admit(demo_db, task, "Confirm the selected condition", "confirm", **options) == confirmed
    with pytest.raises(tc.IdempotencyConflict):
        admit(demo_db, task, "Confirm the selected condition", "confirm",
              **{**options, "condition_changes": [edit.model_copy(update={"item_id": "other"})]})
    with connect(demo_db) as connection:
        stored = connection.execute(
            "SELECT result_json FROM commands WHERE command_id=?", (confirmed["command_id"],),
        ).fetchone()[0]
        assert json.loads(stored) == confirmed
        public = connection.execute(
            "SELECT payload_json FROM session_events WHERE source_id IN (?, ?)", (confirmed["run_id"], confirmed["command_id"]),
        ).fetchall()
        assert public and all(CHANGES not in row[0] and SNAPSHOT not in row[0] for row in public)
    active = load_investigation_context(demo_db, task[1], confirmed["run_id"])["task_run_control"]
    assert active["conditions"][0]["text"] == "Only E7"
    assert active["conditions"][0]["source_message_id"] == source["message_id"]
    with connect(demo_db) as connection:
        validate_task_run_context_in_transaction(connection, task[1], active)
        connection.execute("UPDATE messages SET body='Invalidated' WHERE message_id=?", (source["message_id"],))
        with pytest.raises(tc.TaskControlError, match="TASK_CONDITION_SOURCE_INVALID"):
            validate_task_run_context_in_transaction(connection, task[1], active)


def test_legacy_correction_preserves_projection_and_rejects_stale_item_version(demo_db, task):
    source = admit(demo_db, task, "Only E7", "input")
    receipt = admit(demo_db, task, "Confirm", "confirm", correction=True, expected_control_revision=0,
                    condition_changes=[change("event", source["message_id"], "Only E7")])
    apply(demo_db, task, receipt)
    owner, task_id, _ = task
    tc.finish_task_run(demo_db, owner, receipt["run_id"], "WAITING_INPUT")
    legacy = admit(demo_db, task, "Legacy correction on protocol interpretation.", "legacy", correction=True)
    apply(demo_db, task, legacy)
    control = load_investigation_context(demo_db, task_id, legacy["run_id"])["task_run_control"]
    assert len(control["input_refs"]) == 3
    assert control["conditions"][0]["applied_revision"] == 2
    assert control["current_control_revision"] == 4
    with pytest.raises(tc.TaskControlError, match="TASK_CONDITION_VERSION_CONFLICT"):
        admit(
            demo_db, task, "Try a stale item version", "stale-item", correction=True,
            expected_control_revision=4, condition_changes=[change("event", source["message_id"], "Only E7", "REVOKE")],
        )


def test_confirmed_conditions_share_budget_and_cannot_be_truncated(demo_db, task, monkeypatch):
    monkeypatch.setenv("OPSPILOT_CONTEXT_INPUT_BUDGET_TOKENS", "12000")
    changes = []
    for index in range(4):
        body = f"Condition {index}: " + "alpha beta gamma delta " * 48
        message = admit(demo_db, task, body, f"source-{index}")
        changes.append(change(f"condition-{index}", message["message_id"], body))
    receipt = admit(demo_db, task, "Confirm", "confirm", correction=True,
                    expected_control_revision=0, condition_changes=changes)
    apply(demo_db, task, receipt)
    continued = admit(demo_db, task, "Continue", "next")
    with connect(demo_db) as connection:
        run = connection.execute("SELECT * FROM task_runs WHERE run_id=?", (continued["run_id"],)).fetchone()
        context = _prepare_context(connection, run, "fixture", demo_db, reserved_tokens=500)
        assert len(context["task_conditions"]) == 4
        selected = context["context_blocks"]
        size = sum(block["estimated_tokens"] for block in selected if block["category"] in {
            "TRUSTED_CONTROL", "CURRENT_TASK_STATE", "CURRENT_FACTS", "TASK_INPUT_ANCHOR", "CURRENT_USER_INPUT",
        })
        condition_size = next(
            block["estimated_tokens"] for block in selected if block["category"] == "CURRENT_TASK_CONDITIONS"
        )
        monkeypatch.setenv("OPSPILOT_CONTEXT_INPUT_BUDGET_TOKENS", str(500 + size + condition_size // 2))
        with pytest.raises(ContextBudgetExceeded, match="TASK_CONDITIONS_EXCEED_CONTEXT_BUDGET"):
            _prepare_context(connection, run, "fixture", demo_db, reserved_tokens=500)
