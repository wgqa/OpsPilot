"""Run-linked D2 observation setup for deterministic S3 domain tests."""

from __future__ import annotations

from uuid import uuid4


def record_s3_observation(db, task, tool_name, result, *, run_id=None, arguments=None):
    """Persist a test fact with the same Task/Run/Attempt chain as production.

    S3 Gate tests use deterministic Domain fact providers in place of MCP transport,
    while the TTL integration test exercises the actual HTTP and MCP path.
    This helper only builds valid run-scoped persistence for those Domain tests.
    """
    from opspilot.domain.database import connect
    from opspilot.domain.d2 import (
        attempt_counts, digest_json, finish_attempt, record_tool_observation, reserve_attempt,
    )
    from opspilot.domain.investigation_context import load_investigation_context
    from opspilot.domain.task_control import (
        apply_pending_critical_inputs, claim_task_run, trusted_identity,
    )

    task_id = str(task["task_id"])
    selected_run = str(run_id or task["run_id"])
    with connect(db) as connection:
        run = connection.execute(
            "SELECT status FROM task_runs WHERE run_id=? AND task_id=?", (selected_run, task_id),
        ).fetchone()
        binding = connection.execute(
            "SELECT actor_id FROM task_bindings WHERE task_id=?", (task_id,),
        ).fetchone()
        control = connection.execute(
            "SELECT pending_critical_message_seq FROM task_controls WHERE task_id=?", (task_id,),
        ).fetchone()
    if run is None or binding is None:
        raise AssertionError("S3 test observation requires a persisted Task and Run.")
    identity = trusted_identity(db, str(binding["actor_id"]))
    if str(run["status"]) in {"PENDING", "QUEUED"}:
        claim_task_run(db, identity, selected_run)
        apply_pending_critical_inputs(db, identity, selected_run)
    elif str(run["status"]) == "RUNNING" and control and control["pending_critical_message_seq"] is not None:
        apply_pending_critical_inputs(db, identity, selected_run)
    elif str(run["status"]) != "RUNNING":
        raise AssertionError(f"Cannot add an observation to Run in {run['status']} state.")

    args = arguments or {}
    call_id, tool_call_id = f"test-s3-{uuid4()}", f"tool-{uuid4()}"
    run_context = load_investigation_context(db, task_id, selected_run)["task_run_control"]
    # These direct Domain tests do not exercise the runtime MCP budget. Keep
    # each persisted test Attempt valid without changing the production limit.
    next_limit = max(6, attempt_counts(db, task_id)["MCP"] + 1)
    attempt_id, _ = reserve_attempt(
        db, task_id, "MCP", next_limit, call_id=call_id, tool_call_id=tool_call_id,
        tool_name=tool_name, argument_digest=digest_json(args), run_id=selected_run,
        task_run_control=run_context,
    )
    observation = record_tool_observation(
        db, task_id=task_id, call_id=call_id, attempt_id=attempt_id,
        tool_call_id=tool_call_id, tool_name=tool_name, arguments=args, status="OK", result=result,
    )
    attempt_status = "OK" if observation["status"] == "OK" else "FAILED"
    finish_attempt(
        db, attempt_id, attempt_status,
        result_digest=str(observation["result_digest"]) if attempt_status == "OK" else None,
        error_class=str(observation["error_class"]) if attempt_status != "OK" else None,
    )
    return observation
