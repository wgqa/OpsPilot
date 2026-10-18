from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from opspilot.domain.d2 import (
    create_task_binding,
    evaluate_evidence_gate,
    get_auth_policy_fact,
    get_integration_config_fact,
    get_principal_status_fact,
    probe_endpoint_fact,
    record_tool_observation,
)
from opspilot.domain.d3 import (
    D3PreconditionRejected,
    D3ScopeDenied,
    activate_plan,
    authorize_workflow_resume,
    create_plan_from_gate,
    execute_deliver,
    execute_repair,
    get_or_create_action_intent,
    get_or_create_report,
    get_task_action_state,
    submit_plan_approval,
    verify_repair_online,
)
from opspilot.domain.database import connect, get_integration_info
from opspilot.domain.task_control import (
    IdempotencyConflict,
    TaskControlError,
    TrustedIdentity,
    abort_task,
    admit_task_message,
    apply_pending_critical_inputs,
    claim_task_run,
    finish_task_run,
    get_task_run,
    resume_task_run,
    trusted_identity,
)


def _append_ready_evidence(db: Path, api_url: str, task_id: str, label: str) -> list[str]:
    observations = (
        ("get_integration_config", get_integration_config_fact(db, task_id, "integration-a")),
        ("get_principal_status", get_principal_status_fact(db, task_id, "principal-a")),
        ("get_auth_policy", get_auth_policy_fact(db, task_id, "orders-demo")),
        ("probe_endpoint", probe_endpoint_fact(db, task_id, "orders-demo", "integration-a", api_url)),
    )
    evidence_ids: list[str] = []
    for index, (tool_name, result) in enumerate(observations, start=1):
        stored = record_tool_observation(
            db,
            task_id=task_id,
            call_id=f"m1-{label}-call-{index}",
            attempt_id=None,
            tool_call_id=f"m1-{label}-tool-{index}",
            tool_name=tool_name,
            arguments={"case": label, "index": index},
            status="OK",
            result=result,
        )
        evidence_ids.append(str(stored["evidence_id"]))
    return evidence_ids


def _ready_task(db: Path, api_url: str, label: str = "ready") -> tuple[dict[str, object], dict[str, object], dict[str, object]]:
    binding = create_task_binding(db, "support-a", "orders-demo", "integration-a", "INC-A-001")
    task_id = str(binding["task_id"])
    evidence_ids = _append_ready_evidence(db, api_url, task_id, label)
    gate = evaluate_evidence_gate(db, task_id, evidence_ids)
    assert gate["decision"] == "READY"
    plan = create_plan_from_gate(db, task_id, "support-a", gate)
    return binding, gate, plan


def _seed_checkpoint(
    db: Path, checkpoint_db: Path, binding: dict[str, object], state: dict[str, object], as_node: str
) -> None:
    from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

    from opspilot.investigator import build_investigation_graph

    async def seed() -> None:
        async with AsyncSqliteSaver.from_conn_string(str(checkpoint_db)) as checkpointer:
            await checkpointer.setup()
            graph = build_investigation_graph(
                db, str(binding["task_id"]), "m1-checkpoint-seed", None, [], [], None,
                checkpointer, checkpoint_db, d3_mode=True,
                submitter_id=str(binding["actor_id"]), executor_id="executor-a",
                business_api_url="http://127.0.0.1:1",
            )
            await graph.aupdate_state(
                {"configurable": {"thread_id": str(binding["thread_id"])}}, state, as_node=as_node
            )

    asyncio.run(seed())


def _run_resume_worker(db: Path, checkpoint_db: Path, binding: dict[str, object]) -> tuple[dict[str, object], int, str]:
    worker = Path(__file__).with_name("m1_crash_worker.py")
    completed = subprocess.run(
        [
            sys.executable,
            str(worker),
            str(db),
            str(checkpoint_db),
            str(binding["thread_id"]),
            str(binding["actor_id"]),
        ],
        cwd=Path(__file__).resolve().parents[1],
        text=True,
        capture_output=True,
        timeout=60,
        check=False,
    )
    events = [json.loads(line) for line in completed.stdout.splitlines() if line.startswith("{")]
    assert events, completed.stdout + completed.stderr
    return events[-1], completed.returncode, completed.stdout + completed.stderr


def _count(db: Path, table: str, where: str = "1 = 1", params: tuple[object, ...] = ()) -> int:
    with connect(db) as connection:
        return int(connection.execute(f"SELECT COUNT(*) FROM {table} WHERE {where}", params).fetchone()[0])


def test_n1_01_02_admission_is_atomic_and_idempotent(demo_db: Path) -> None:
    binding = create_task_binding(demo_db, "support-a", "orders-demo", "integration-a", "INC-M1-ADMIT")
    identity = trusted_identity(demo_db, "support-a")
    with connect(demo_db) as connection:
        connection.execute(
            """CREATE TRIGGER fail_m1_run BEFORE INSERT ON task_runs
               BEGIN SELECT RAISE(ABORT, 'injected_n1_01_after_message_before_run'); END"""
        )

    with pytest.raises(Exception, match="injected_n1_01_after_message_before_run"):
        admit_task_message(
            demo_db, identity, session_id=str(binding["session_id"]),
            task_id=str(binding["task_id"]), input_kind="CORRECT_TASK_INPUT",
            body="The service account has been rotated; investigate current configuration.",
            idempotency_key="n1-01-atomic",
        )
    assert _count(demo_db, "messages") == 0
    assert _count(demo_db, "commands") == 0
    assert _count(demo_db, "task_runs") == 0
    assert _count(demo_db, "domain_outbox") == 0
    with connect(demo_db) as connection:
        connection.execute("DROP TRIGGER fail_m1_run")
        control = connection.execute(
            "SELECT control_revision, pending_critical_message_seq FROM task_controls WHERE task_id = ?",
            (binding["task_id"],),
        ).fetchone()
    assert tuple(control) == (0, None)

    request = dict(
        session_id=str(binding["session_id"]), task_id=str(binding["task_id"]),
        input_kind="CORRECT_TASK_INPUT", body="The service account has been rotated; investigate current configuration.",
        idempotency_key="n1-01-atomic",
    )
    first = admit_task_message(demo_db, identity, **request)
    replay = admit_task_message(demo_db, identity, **request)
    assert (first["command_id"], first["message_id"], first["run_id"]) == (
        replay["command_id"], replay["message_id"], replay["run_id"]
    )
    changed = {**request, "body": "Different request under the same idempotency key."}
    with pytest.raises(IdempotencyConflict, match="IDEMPOTENCY_CONFLICT"):
        admit_task_message(demo_db, identity, **changed)
    assert _count(demo_db, "messages") == _count(demo_db, "commands") == 1
    assert _count(demo_db, "task_runs") == _count(demo_db, "domain_outbox") == 1
    with connect(demo_db) as connection:
        control = connection.execute(
            "SELECT control_revision, pending_critical_message_seq FROM task_controls WHERE task_id = ?",
            (binding["task_id"],),
        ).fetchone()
    assert tuple(control) == (1, 1)
    print("M1_EVIDENCE " + json.dumps({
        "case": "N1-01/02",
        "failed_insert_rollback": "PASS",
        "accepted_message_id": first["message_id"],
        "accepted_command_id": first["command_id"],
        "accepted_run_id": first["run_id"],
        "retry_same_ids": True,
        "control_revision": control["control_revision"],
        "conflicting_digest": "IDEMPOTENCY_CONFLICT",
    }, sort_keys=True))


def test_n1_05_one_worker_claims_the_durable_run(demo_db: Path) -> None:
    binding = create_task_binding(demo_db, "support-a", "orders-demo", "integration-a", "INC-M1-CLAIM")
    identity = trusted_identity(demo_db, "support-a")
    accepted = admit_task_message(
        demo_db, identity, session_id=str(binding["session_id"]), task_id=str(binding["task_id"]),
        input_kind="CORRECT_TASK_INPUT", body="Investigate the credential rotation.", idempotency_key="n1-05-run",
    )
    barrier = threading.Barrier(2)

    def claim() -> tuple[str, str]:
        barrier.wait()
        try:
            claimed = claim_task_run(demo_db, identity, str(accepted["run_id"]))
            return "CLAIMED", str(claimed["status"])
        except TaskControlError as error:
            return "REJECTED", error.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: claim(), range(2)))
    assert sum(1 for status, _ in results if status == "CLAIMED") == 1
    assert sorted(code for status, code in results if status == "REJECTED") == ["TASK_RUN_NOT_QUEUED"]
    assert _count(demo_db, "task_runs", "run_id = ? AND status = 'RUNNING'", (accepted["run_id"],)) == 1
    assert get_task_run(demo_db, identity, str(accepted["run_id"]))["status"] == "RUNNING"
    print("M1_EVIDENCE " + json.dumps({"case": "N1-05", "claims": results, "running_count": 1}, sort_keys=True))


def test_revision_zero_run_can_be_claimed_applied_and_resumed(demo_db: Path) -> None:
    binding = create_task_binding(demo_db, "support-a", "orders-demo", "integration-a", "INC-M1-REVISION-ZERO")
    identity = trusted_identity(demo_db, "support-a")
    run_id = "run-m1-revision-zero"
    with connect(demo_db) as connection:
        connection.execute(
            """INSERT INTO task_runs
               (run_id, tenant_id, task_id, session_id, command_id, kind, status,
                control_revision_at_start, expected_control_revision, consumed_message_seq,
                applied_critical_message_seq, created_at)
               VALUES (?, ?, ?, ?, ?, 'INVESTIGATE', 'QUEUED', 0, 0, 0, 0, '2026-10-18T00:00:00+00:00')""",
            (run_id, binding["tenant_id"], binding["task_id"], binding["session_id"], "command-m1-revision-zero"),
        )

    claimed = claim_task_run(demo_db, identity, run_id)
    assert claimed["expected_control_revision"] == 0 and claimed["status"] == "RUNNING"
    authorized = authorize_workflow_resume(
        demo_db, str(binding["thread_id"]), "support-a", run_id=run_id
    )
    assert authorized["task_id"] == binding["task_id"]
    applied = apply_pending_critical_inputs(demo_db, identity, run_id)
    assert applied["expected_control_revision"] == 0 and applied["inputs"] == []
    waiting = finish_task_run(demo_db, identity, run_id, "WAITING_APPROVAL")
    assert waiting["status"] == "WAITING_APPROVAL"

    resumed = resume_task_run(demo_db, identity, run_id)
    assert resumed["expected_control_revision"] == 0 and resumed["status"] == "RUNNING"
    resumed_inputs = apply_pending_critical_inputs(demo_db, identity, run_id)
    assert resumed_inputs["expected_control_revision"] == 0 and resumed_inputs["inputs"] == []
    finish_task_run(demo_db, identity, run_id, "WAITING_APPROVAL")
    with connect(demo_db) as connection:
        control = connection.execute(
            "SELECT control_revision FROM task_controls WHERE task_id = ?", (binding["task_id"],)
        ).fetchone()[0]
        task_status = connection.execute(
            "SELECT status FROM task_bindings WHERE task_id = ?", (binding["task_id"],)
        ).fetchone()[0]
    assert control == 0 and task_status == "WAITING_APPROVAL"


def test_chat_readonly_run_does_not_change_business_task_lifecycle(demo_db: Path, live_api: str) -> None:
    binding, _, plan = _ready_task(demo_db, live_api, "chat-readonly-lifecycle")
    task_id = str(binding["task_id"])
    identity = trusted_identity(demo_db, "support-a")

    chat = admit_task_message(
        demo_db, identity, session_id=str(binding["session_id"]), task_id=task_id,
        input_kind="CHAT_READONLY", body="Explain the current investigation status.",
        idempotency_key="m1-chat-readonly-before-approval",
    )
    chat_run = claim_task_run(demo_db, identity, str(chat["run_id"]))
    assert chat_run["kind"] == "CHAT_READONLY"
    finish_task_run(demo_db, identity, str(chat["run_id"]), "SUCCEEDED")
    with connect(demo_db) as connection:
        status_after_chat = connection.execute(
            "SELECT status FROM task_bindings WHERE task_id = ?", (task_id,)
        ).fetchone()[0]
    assert status_after_chat == "WAITING_APPROVAL"

    approval = submit_plan_approval(
        demo_db, str(binding["thread_id"]), "approver-a", str(plan["plan_hash"]), "APPROVED"
    )
    assert approval["decision"] == "APPROVED"
    repair_intent = get_or_create_action_intent(demo_db, task_id, str(plan["plan_hash"]), "REPAIR", "executor-a")
    repair = execute_repair(demo_db, str(repair_intent["action_id"]), "executor-a", "m1-chat-readonly-repair")
    receipt = verify_repair_online(
        demo_db, task_id, str(plan["plan_hash"]), str(repair_intent["action_id"]), "executor-a", live_api
    )
    assert receipt["recovery_verified"] is True
    get_or_create_report(demo_db, task_id, str(plan["plan_hash"]), str(repair_intent["action_id"]), "executor-a")
    delivery_intent = get_or_create_action_intent(demo_db, task_id, str(plan["plan_hash"]), "DELIVER", "executor-a")
    delivery = execute_deliver(demo_db, str(delivery_intent["action_id"]), "executor-a", "m1-chat-readonly-deliver")
    assert repair["status"] == delivery["status"] == "COMMITTED"

    completed_chat = admit_task_message(
        demo_db, identity, session_id=str(binding["session_id"]), task_id=task_id,
        input_kind="CHAT_READONLY", body="Summarize the completed business task.",
        idempotency_key="m1-chat-readonly-after-completion",
    )
    claim_task_run(demo_db, identity, str(completed_chat["run_id"]))
    finish_task_run(demo_db, identity, str(completed_chat["run_id"]), "SUCCEEDED")
    with connect(demo_db) as connection:
        final_status = connection.execute(
            "SELECT status FROM task_bindings WHERE task_id = ?", (task_id,)
        ).fetchone()[0]
        ledger_counts = connection.execute(
            """SELECT action_kind, COUNT(*) AS count FROM d3_action_ledgers
               WHERE task_id = ? GROUP BY action_kind""",
            (task_id,),
        ).fetchall()
    assert final_status == "COMPLETED"
    assert {row["action_kind"]: row["count"] for row in ledger_counts} == {"DELIVER": 1, "REPAIR": 1}


def test_abort_is_owner_scoped_idempotent_and_does_not_overwrite_completion(demo_db: Path) -> None:
    binding = create_task_binding(demo_db, "support-a", "orders-demo", "integration-a", "INC-M1-ABORT")
    owner = trusted_identity(demo_db, "support-a")
    with pytest.raises(TaskControlError, match="TASK_OWNER_REQUIRED"):
        abort_task(demo_db, trusted_identity(demo_db, "support-b"), task_id=str(binding["task_id"]), reason="cross tenant", idempotency_key="bad")
    with pytest.raises(TaskControlError, match="TASK_OWNER_REQUIRED"):
        abort_task(demo_db, trusted_identity(demo_db, "approver-a"), task_id=str(binding["task_id"]), reason="approver", idempotency_key="bad-2")
    forged = TrustedIdentity("support-a", "tenant-b", "SUPPORT")
    with pytest.raises(TaskControlError, match="TRUSTED_IDENTITY_MISMATCH"):
        abort_task(demo_db, forged, task_id=str(binding["task_id"]), reason="forged", idempotency_key="bad-3")

    first = abort_task(demo_db, owner, task_id=str(binding["task_id"]), reason="operator stopped the task", idempotency_key="abort-once")
    replay = abort_task(demo_db, owner, task_id=str(binding["task_id"]), reason="operator stopped the task", idempotency_key="abort-once")
    assert first == replay
    assert first["status"] == "ACCEPTED" and first["control_revision"] == 1
    rejected = abort_task(demo_db, owner, task_id=str(binding["task_id"]), reason="another abort", idempotency_key="abort-again")
    assert rejected["status"] == "REJECTED" and rejected["error_code"] == "TASK_ALREADY_TERMINAL"
    with connect(demo_db) as connection:
        control = connection.execute("SELECT terminal_state, control_revision FROM task_controls WHERE task_id = ?", (binding["task_id"],)).fetchone()
    assert tuple(control) == ("ABORTED", 1)
    assert _count(demo_db, "d3_plans") == _count(demo_db, "d3_approvals") == 0


def test_n1_09_abort_before_old_checkpoint_resume_is_enforced_in_another_process(
    demo_db: Path, live_api: str, tmp_path: Path
) -> None:
    binding = create_task_binding(demo_db, "support-a", "orders-demo", "integration-a", "INC-M1-N1-09")
    task_id = str(binding["task_id"])
    evidence_ids = _append_ready_evidence(demo_db, live_api, task_id, "n1-09")
    gate = evaluate_evidence_gate(demo_db, task_id, evidence_ids)
    assert gate["decision"] == "READY"
    checkpoint_db = tmp_path / "m1-n1-09.sqlite3"
    _seed_checkpoint(
        demo_db, checkpoint_db, binding,
        {
            "task_binding_id": task_id,
            "stage": "investigating",
            "budget": {"MODEL": 1, "MCP": 1},
            "diagnosis_draft": {},
            "evidence_ids": evidence_ids,
            "tool_observations": [],
            "pending_call_refs": [],
            "gate_decision": {},
        },
        "investigate",
    )
    owner = trusted_identity(demo_db, "support-a")
    aborted = abort_task(
        demo_db, owner, task_id=task_id, reason="cancel while an old investigation response is pending",
        idempotency_key="n1-09-abort",
    )
    child_event, exit_code, raw_output = _run_resume_worker(demo_db, checkpoint_db, binding)
    assert exit_code == 0, raw_output
    assert child_event["pid"] != os.getpid()
    assert child_event["reason"] == "TASK_ABORTED"
    with pytest.raises(D3PreconditionRejected, match="TASK_ABORTED"):
        create_plan_from_gate(demo_db, task_id, "support-a", gate)
    with connect(demo_db) as connection:
        control = connection.execute("SELECT terminal_state, control_revision FROM task_controls WHERE task_id = ?", (task_id,)).fetchone()
    assert tuple(control) == ("ABORTED", 1)
    assert _count(demo_db, "d3_plans", "task_id = ?", (task_id,)) == 0
    assert _count(demo_db, "d3_approvals", "task_id = ?", (task_id,)) == 0
    assert _count(demo_db, "d3_action_intents", "task_id = ?", (task_id,)) == 0
    assert _count(demo_db, "d3_action_ledgers", "task_id = ?", (task_id,)) == 0
    print("M1_EVIDENCE " + json.dumps({
        "case": "N1-09",
        "abort_command_id": aborted["command_id"],
        "abort_control_revision": control["control_revision"],
        "parent_pid": os.getpid(),
        "child_process": child_event,
        "checkpoint_exists_before_resume": checkpoint_db.exists(),
        "plan_count": 0,
        "approval_count": 0,
        "intent_count": 0,
        "ledger_count": 0,
    }, sort_keys=True))


def test_n1_10_correction_invalidates_old_run_and_new_run_binds_fresh_plan(
    demo_db: Path, live_api: str
) -> None:
    binding, old_gate, old_plan = _ready_task(demo_db, live_api, "n1-10")
    task_id = str(binding["task_id"])
    old_approval = submit_plan_approval(demo_db, str(binding["thread_id"]), "approver-a", str(old_plan["plan_hash"]), "APPROVED")
    old_intent = get_or_create_action_intent(demo_db, task_id, str(old_plan["plan_hash"]), "REPAIR", "executor-a")
    identity = trusted_identity(demo_db, "support-a")
    correction = admit_task_message(
        demo_db, identity,
        session_id=str(binding["session_id"]), task_id=task_id,
        input_kind="CORRECT_TASK_INPUT",
        body="The observed 401 began after a service-account credential rotation; check the current accepted credential reference.",
        idempotency_key="n1-10-correction",
    )
    with pytest.raises(D3PreconditionRejected, match="TASK_INPUT_PENDING"):
        execute_repair(demo_db, str(old_intent["action_id"]), "executor-a", "n1-10-old-pending")
    with pytest.raises(D3PreconditionRejected, match="TASK_INPUT_PENDING"):
        create_plan_from_gate(demo_db, task_id, "support-a", old_gate)
    with pytest.raises(D3PreconditionRejected, match="TASK_INPUT_PENDING"):
        activate_plan(demo_db, task_id, str(old_plan["plan_hash"]), "support-a")

    claimed = claim_task_run(demo_db, identity, str(correction["run_id"]))
    assert claimed["status"] == "RUNNING"
    applied = apply_pending_critical_inputs(demo_db, identity, str(correction["run_id"]))
    assert applied["inputs"][0]["body"].startswith("The observed 401")
    assert applied["inputs"][0]["provenance"] == "USER_INPUT_UNTRUSTED"
    from opspilot.investigator import _prompt_messages

    prompt = _prompt_messages(
        demo_db, task_id,
        {"evidence_ids": old_plan["required_evidence_ids"], "critical_input_messages": applied["inputs"]},
    )
    assert "untrusted_user_corrections" in prompt[1].content
    assert applied["inputs"][0]["body"] in prompt[1].content
    assert "USER_INPUT_UNTRUSTED" in prompt[1].content
    with pytest.raises(D3PreconditionRejected, match="TASK_CONTROL_STALE"):
        execute_repair(demo_db, str(old_intent["action_id"]), "executor-a", "n1-10-old-stale")
    with pytest.raises(D3PreconditionRejected, match="TASK_CONTROL_STALE"):
        create_plan_from_gate(demo_db, task_id, "support-a", old_gate)

    fresh_evidence = _append_ready_evidence(demo_db, live_api, task_id, "n1-10-after-correction")
    fresh_gate = evaluate_evidence_gate(demo_db, task_id, fresh_evidence)
    fresh_plan = create_plan_from_gate(
        demo_db, task_id, "support-a", fresh_gate, run_id=str(correction["run_id"])
    )
    with connect(demo_db) as connection:
        plan_binding = connection.execute(
            "SELECT bound_control_revision, consumed_message_seq, task_run_id FROM d3_plan_control_bindings WHERE plan_hash = ?",
            (fresh_plan["plan_hash"],),
        ).fetchone()
        control = connection.execute(
            "SELECT control_revision, pending_critical_message_seq, applied_critical_message_seq FROM task_controls WHERE task_id = ?",
            (task_id,),
        ).fetchone()
        old_permission = connection.execute(
            "SELECT state FROM d3_action_permissions WHERE task_id = ? AND plan_hash = ? AND action_kind = 'REPAIR'",
            (task_id, old_plan["plan_hash"]),
        ).fetchone()
    assert tuple(plan_binding) == (2, int(correction["sequence"]), correction["run_id"])
    assert tuple(control) == (2, None, int(correction["sequence"]))
    assert old_permission["state"] == "REVOKED"
    assert old_approval["approval_id"] is not None
    # Replaying the old persisted approval returns history only; it cannot recreate
    # the revoked permission or authorize its stale ActionIntent.
    assert submit_plan_approval(
        demo_db, str(binding["thread_id"]), "approver-a", str(old_plan["plan_hash"]), "APPROVED"
    )["approval_id"] == old_approval["approval_id"]
    assert _count(demo_db, "d3_action_permissions", "task_id = ? AND plan_hash = ? AND state = 'AVAILABLE'", (task_id, old_plan["plan_hash"])) == 0

    new_approval = submit_plan_approval(demo_db, str(binding["thread_id"]), "approver-a", str(fresh_plan["plan_hash"]), "APPROVED")
    finish_task_run(demo_db, identity, str(correction["run_id"]), "WAITING_APPROVAL")
    resumed_run = resume_task_run(demo_db, identity, str(correction["run_id"]))
    assert resumed_run["status"] == "RUNNING"
    from opspilot.domain.d3 import authorize_workflow_resume

    authorize_workflow_resume(demo_db, str(binding["thread_id"]), "support-a", run_id=str(correction["run_id"]))
    new_intent = get_or_create_action_intent(demo_db, task_id, str(fresh_plan["plan_hash"]), "REPAIR", "executor-a")
    new_ledger = execute_repair(demo_db, str(new_intent["action_id"]), "executor-a", "n1-10-new-run")
    assert new_ledger["status"] == "COMMITTED" and new_ledger["before_version"] == 7 and new_ledger["after_version"] == 8
    assert get_integration_info(demo_db, "tenant-a", "integration-a")["config_version"] == 8
    assert _count(demo_db, "d3_action_ledgers", "task_id = ? AND action_kind = 'REPAIR'", (task_id,)) == 1
    print("M1_EVIDENCE " + json.dumps({
        "case": "N1-10",
        "old_plan_hash": old_plan["plan_hash"],
        "old_approval_id": old_approval["approval_id"],
        "old_repair_intent_id": old_intent["action_id"],
        "pending_error": "TASK_INPUT_PENDING",
        "post_apply_error": "TASK_CONTROL_STALE",
        "correction_message_id": correction["message_id"],
        "correction_run_id": correction["run_id"],
        "consumed_control_revision": control["control_revision"],
        "fresh_plan_hash": fresh_plan["plan_hash"],
        "fresh_approval_id": new_approval["approval_id"],
        "fresh_repair_ledger_id": new_ledger["ledger_id"],
        "config_version_after": 8,
        "repair_ledger_count": 1,
    }, sort_keys=True))


def test_plan_approval_cannot_be_created_after_correction_is_pending(
    demo_db: Path, live_api: str
) -> None:
    binding, _, plan = _ready_task(demo_db, live_api, "approval-pending")
    identity = trusted_identity(demo_db, "support-a")
    accepted = admit_task_message(
        demo_db, identity,
        session_id=str(binding["session_id"]), task_id=str(binding["task_id"]),
        input_kind="CORRECT_TASK_INPUT", body="The credential reference may have rotated; re-check current policy.",
        idempotency_key="m1-approval-pending",
    )
    with pytest.raises(D3PreconditionRejected, match="TASK_INPUT_PENDING"):
        submit_plan_approval(demo_db, str(binding["thread_id"]), "approver-a", str(plan["plan_hash"]), "APPROVED")
    assert accepted["status"] == "ACCEPTED"
    assert _count(demo_db, "d3_approvals", "task_id = ?", (binding["task_id"],)) == 0
    assert _count(demo_db, "d3_action_permissions", "task_id = ?", (binding["task_id"],)) == 0


def test_abort_after_real_delivery_cannot_overwrite_completed_business_task(
    demo_db: Path, live_api: str
) -> None:
    binding, _, plan = _ready_task(demo_db, live_api, "complete")
    task_id = str(binding["task_id"])
    submit_plan_approval(demo_db, str(binding["thread_id"]), "approver-a", str(plan["plan_hash"]), "APPROVED")
    repair_intent = get_or_create_action_intent(demo_db, task_id, str(plan["plan_hash"]), "REPAIR", "executor-a")
    repair = execute_repair(demo_db, str(repair_intent["action_id"]), "executor-a", "m1-complete-repair")
    receipt = verify_repair_online(demo_db, task_id, str(plan["plan_hash"]), str(repair_intent["action_id"]), "executor-a", live_api)
    get_or_create_report(demo_db, task_id, str(plan["plan_hash"]), str(repair_intent["action_id"]), "executor-a")
    delivery_intent = get_or_create_action_intent(demo_db, task_id, str(plan["plan_hash"]), "DELIVER", "executor-a")
    delivery = execute_deliver(demo_db, str(delivery_intent["action_id"]), "executor-a", "m1-complete-deliver")
    result = abort_task(
        demo_db, trusted_identity(demo_db, "support-a"), task_id=task_id,
        reason="too late to abort a delivered business task", idempotency_key="m1-abort-after-complete",
    )
    with connect(demo_db) as connection:
        control = connection.execute("SELECT terminal_state, control_revision FROM task_controls WHERE task_id = ?", (task_id,)).fetchone()
        task_status = connection.execute("SELECT status FROM task_bindings WHERE task_id = ?", (task_id,)).fetchone()[0]
    assert result["status"] == "REJECTED" and result["error_code"] == "TASK_ALREADY_TERMINAL"
    assert tuple(control) == ("ACTIVE", 0) and task_status == "COMPLETED"
    assert receipt["response_status"] == 200 and delivery["status"] == "COMMITTED"
    assert _count(demo_db, "d3_action_ledgers", "task_id = ? AND action_kind = 'REPAIR'", (task_id,)) == 1
    assert _count(demo_db, "d3_action_ledgers", "task_id = ? AND action_kind = 'DELIVER'", (task_id,)) == 1
    assert _count(demo_db, "d3_ticket_resolution_entries", "task_id = ?", (task_id,)) == 1


def test_n1_11_repair_commit_survives_abort_and_old_checkpoint_cannot_deliver(
    demo_db: Path, live_api: str, tmp_path: Path
) -> None:
    binding, _, plan = _ready_task(demo_db, live_api, "n1-11")
    task_id = str(binding["task_id"])
    approval = submit_plan_approval(demo_db, str(binding["thread_id"]), "approver-a", str(plan["plan_hash"]), "APPROVED")
    repair_intent = get_or_create_action_intent(demo_db, task_id, str(plan["plan_hash"]), "REPAIR", "executor-a")
    repair_ledger = execute_repair(demo_db, str(repair_intent["action_id"]), "executor-a", "n1-11-repair")
    verification = verify_repair_online(
        demo_db, task_id, str(plan["plan_hash"]), str(repair_intent["action_id"]), "executor-a", live_api
    )
    report = get_or_create_report(demo_db, task_id, str(plan["plan_hash"]), str(repair_intent["action_id"]), "executor-a")
    deliver_intent = get_or_create_action_intent(demo_db, task_id, str(plan["plan_hash"]), "DELIVER", "executor-a")
    checkpoint_db = tmp_path / "m1-n1-11.sqlite3"
    _seed_checkpoint(
        demo_db, checkpoint_db, binding,
        {
            "task_binding_id": task_id,
            "stage": "d3_deliver_intent_persisted",
            "budget": {"MODEL": 0, "MCP": 0},
            "diagnosis_draft": {},
            "evidence_ids": list(plan["required_evidence_ids"]),
            "tool_observations": [],
            "pending_call_refs": [],
            "gate_decision": {},
            "plan_id": plan["plan_id"],
            "plan_hash": plan["plan_hash"],
            "approval_id": approval["approval_id"],
            "approval_decision": "APPROVED",
            "repair_action_id": repair_intent["action_id"],
            "repair_ledger_ref": repair_ledger["ledger_id"],
            "verification_id": verification["verification_id"],
            "frozen_report_ref": report["report_ref"],
            "deliver_action_id": deliver_intent["action_id"],
        },
        "d3_deliver_intent",
    )
    owner = trusted_identity(demo_db, "support-a")
    aborted = abort_task(
        demo_db, owner, task_id=task_id, reason="stop delivery after committed repair",
        idempotency_key="n1-11-abort",
    )
    child_event, exit_code, raw_output = _run_resume_worker(demo_db, checkpoint_db, binding)
    assert exit_code == 0, raw_output
    assert child_event["pid"] != os.getpid() and child_event["reason"] == "TASK_ABORTED"
    with pytest.raises(D3PreconditionRejected, match="TASK_ABORTED"):
        execute_deliver(demo_db, str(deliver_intent["action_id"]), "executor-a", "n1-11-old-deliver")
    replayed_repair = execute_repair(demo_db, str(repair_intent["action_id"]), "executor-a", "n1-11-repair-history")
    assert replayed_repair["ledger_id"] == repair_ledger["ledger_id"]
    assert replayed_repair["result"]["status"] == "COMMITTED"
    assert get_integration_info(demo_db, "tenant-a", "integration-a")["config_version"] == 8
    action_state = get_task_action_state(demo_db, task_id, "support-a")
    assert len([item for item in action_state["action_ledgers"] if item["action_kind"] == "REPAIR"]) == 1
    assert len([item for item in action_state["action_ledgers"] if item["action_kind"] == "DELIVER"]) == 0
    assert action_state["delivery_records"] == [] and action_state["ticket_entries"] == []
    assert aborted["terminal_state"] == "ABORTED"
    with connect(demo_db) as connection:
        control = connection.execute("SELECT terminal_state, control_revision FROM task_controls WHERE task_id = ?", (task_id,)).fetchone()
        deliver_permission = connection.execute(
            "SELECT state FROM d3_action_permissions WHERE task_id = ? AND plan_hash = ? AND action_kind = 'DELIVER'",
            (task_id, plan["plan_hash"]),
        ).fetchone()
    assert tuple(control) == ("ABORTED", 1)
    assert deliver_permission["state"] == "REVOKED"
    print("M1_EVIDENCE " + json.dumps({
        "case": "N1-11",
        "abort_command_id": aborted["command_id"],
        "control_revision": control["control_revision"],
        "parent_pid": os.getpid(),
        "child_process": child_event,
        "repair_ledger_id": repair_ledger["ledger_id"],
        "repair_history_read_after_abort": "PASS",
        "config_version_after": 8,
        "repair_ledger_count": 1,
        "deliver_ledger_count": 0,
        "delivery_record_count": 0,
        "ticket_entry_count": 0,
    }, sort_keys=True))


def test_schema_migration_is_idempotent_and_preserves_frozen_plan_hash(
    demo_db: Path, live_api: str
) -> None:
    from opspilot.domain.database import initialize

    binding, _, plan = _ready_task(demo_db, live_api, "migration")
    task_id = str(binding["task_id"])
    with connect(demo_db) as connection:
        connection.execute("DELETE FROM d3_plan_control_bindings WHERE task_id = ?", (task_id,))
        connection.execute("DELETE FROM task_controls WHERE task_id = ?", (task_id,))
        connection.execute("DELETE FROM session_task_links WHERE task_id = ?", (task_id,))
        connection.execute("DELETE FROM sessions WHERE session_id = ?", (binding["session_id"],))
        connection.execute("PRAGMA user_version = 0")
    initialize(demo_db)
    initialize(demo_db)
    with connect(demo_db) as connection:
        control = connection.execute("SELECT terminal_state, control_revision FROM task_controls WHERE task_id = ?", (task_id,)).fetchone()
        session_link = connection.execute("SELECT COUNT(*) FROM session_task_links WHERE task_id = ?", (task_id,)).fetchone()[0]
        migrated_plan = connection.execute("SELECT plan_hash FROM d3_plans WHERE task_id = ?", (task_id,)).fetchone()[0]
        plan_bindings = connection.execute("SELECT COUNT(*) FROM d3_plan_control_bindings WHERE task_id = ?", (task_id,)).fetchone()[0]
        version = connection.execute("PRAGMA user_version").fetchone()[0]
    assert tuple(control) == ("ACTIVE", 0)
    assert session_link == 1 and migrated_plan == plan["plan_hash"] and plan_bindings == 1 and version == 3
    print("M1_EVIDENCE " + json.dumps({
        "case": "migration",
        "user_version": version,
        "task_id": task_id,
        "migrated_control": list(control),
        "plan_hash_preserved": migrated_plan,
        "plan_control_binding_count": plan_bindings,
        "idempotent_replays": 2,
    }, sort_keys=True))
