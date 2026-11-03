from __future__ import annotations

import importlib.util
import json
import uuid
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
WRAPPER_PATH = ROOT / "docs/evidence/ar-03/material-live-01/resume-02/run_live.py"
EXPERIMENT_ID = "AR-03-MATERIAL-LIVE-01-RESUME-02"
CASE_ID = "MAT-04-BOUND-QUEUED"


def _runner(tmp_path: Path):
    spec = importlib.util.spec_from_file_location("ar03_material_post_live_closeout_runner", WRAPPER_PATH)
    assert spec is not None and spec.loader is not None
    wrapper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(wrapper)
    runner = wrapper._bound_base_runner()
    runner.DOMAIN_DB = tmp_path / "domain.sqlite3"
    runner.CHECKPOINT_DB = tmp_path / "checkpoints.sqlite3"
    runner.EVIDENCE = tmp_path / "evidence"
    runner.EVIDENCE.mkdir()
    runner._bootstrap_fresh_campaign_database(runner.DOMAIN_DB)

    from opspilot.domain.assistant_experiment import initialize_experiment

    initialize_experiment(runner.DOMAIN_DB, EXPERIMENT_ID)
    runner._prepare_fixture(runner.DOMAIN_DB)
    accepted = runner._create_user_run(
        CASE_ID, runner._case_inputs()[CASE_ID], bound=True,
    )
    task_id = str(accepted["task_id"])
    run_id = str(accepted["run_id"])

    from opspilot.domain.database import connect
    from opspilot.domain.d2 import canonical_json, digest_json, finish_attempt, record_tool_observation, utc_now
    from opspilot.domain.s3 import get_callback_delivery_fact, get_s3_binding

    with connect(runner.DOMAIN_DB) as connection:
        binding = get_s3_binding(connection, task_id)
    fact = get_callback_delivery_fact(runner.DOMAIN_DB, task_id)
    call_id = "assistant-call-closeout-" + uuid.uuid4().hex
    attempt_id = "attempt-closeout-" + uuid.uuid4().hex
    tool_call_id = "tool-closeout-" + uuid.uuid4().hex
    args = {"reason": "audit association fixture"}
    request = {"name": "get_callback_delivery", "args": args}

    def add_observation(attempt_run_id: str) -> dict[str, str]:
        with connect(runner.DOMAIN_DB) as connection:
            connection.execute(
                """INSERT INTO d2_attempts
                   (attempt_id,task_id,run_id,kind,call_id,tool_call_id,tool_name,
                    argument_digest,reserved_at)
                   VALUES (?,?,?,'MCP',?,?,?,?,?)""",
                (
                    attempt_id, task_id, attempt_run_id, call_id, tool_call_id,
                    "get_callback_delivery", digest_json(args), utc_now(),
                ),
            )
        observation = record_tool_observation(
            runner.DOMAIN_DB, task_id=task_id, call_id=call_id,
            attempt_id=attempt_id, tool_call_id=tool_call_id,
            tool_name="get_callback_delivery", arguments=args,
            status="OK", result=fact,
        )
        finish_attempt(
            runner.DOMAIN_DB, attempt_id, "OK", result_digest=observation["result_digest"],
        )
        with connect(runner.DOMAIN_DB) as connection:
            connection.execute(
                """INSERT INTO assistant_calls
                   (call_id,run_id,kind,logical_key,request_json,request_digest,status,
                    result_json,observation_id,evidence_id,created_at,completed_at)
                   VALUES (?,?,'MCP',?,?,?,?,?,?,?,?,?)""",
                (
                    call_id, run_id, "closeout-mcp-observation", canonical_json(request),
                    digest_json(request), "OK", canonical_json(fact),
                    observation["observation_id"], observation["evidence_id"],
                    utc_now(), utc_now(),
                ),
            )
            connection.execute(
                "UPDATE task_runs SET status='SUCCEEDED' WHERE run_id=?",
                (run_id,),
            )
        return observation

    return runner, accepted, binding, add_observation


def test_audit_case_accepts_same_run_observation_from_temp_database(tmp_path):
    runner, accepted, _binding, add_observation = _runner(tmp_path)
    observation = add_observation(str(accepted["run_id"]))

    result = runner._audit_case(
        {
            **accepted,
            "case_id": CASE_ID,
            "run_id": accepted["run_id"],
            "session_id": accepted["session_id"],
            "message_id": accepted["message_id"],
        },
        0,
        0,
    )

    assert result["d2_observations"][0]["observation_id"] == observation["observation_id"]
    assert result["d2_observations"][0]["attempt_run_id"] == accepted["run_id"]
    assert result["d2_observations"][0]["evidence_id"] == observation["evidence_id"]


def test_audit_case_rejects_current_call_linked_to_another_run_observation(tmp_path):
    runner, accepted, _binding, add_observation = _runner(tmp_path)
    add_observation("run-from-another-execution")

    with pytest.raises(RuntimeError, match="CROSS_RUN_OBSERVATION_ASSOCIATION"):
        runner._audit_case(
            {
                **accepted,
                "case_id": CASE_ID,
                "run_id": accepted["run_id"],
                "session_id": accepted["session_id"],
                "message_id": accepted["message_id"],
            },
            0,
            0,
        )


def test_audit_case_rejects_current_run_call_linked_to_another_task_observation(tmp_path):
    runner, accepted, _binding, _add_observation = _runner(tmp_path)
    other = runner._create_user_run(CASE_ID, runner._case_inputs()[CASE_ID], bound=True)
    other_task_id = str(other["task_id"])
    other_run_id = str(other["run_id"])

    from opspilot.domain.database import connect
    from opspilot.domain.d2 import canonical_json, digest_json, finish_attempt, record_tool_observation, utc_now
    from opspilot.domain.s3 import get_callback_delivery_fact

    fact = get_callback_delivery_fact(runner.DOMAIN_DB, other_task_id)
    call_id = "assistant-call-cross-task-" + uuid.uuid4().hex
    attempt_id = "attempt-cross-task-" + uuid.uuid4().hex
    tool_call_id = "tool-cross-task-" + uuid.uuid4().hex
    args = {"reason": "cross-task audit association fixture"}
    request = {"name": "get_callback_delivery", "args": args}
    with connect(runner.DOMAIN_DB) as connection:
        connection.execute(
            """INSERT INTO d2_attempts
               (attempt_id,task_id,run_id,kind,call_id,tool_call_id,tool_name,
                argument_digest,reserved_at)
               VALUES (?,?,?,'MCP',?,?,?,?,?)""",
            (
                attempt_id, other_task_id, other_run_id, call_id, tool_call_id,
                "get_callback_delivery", digest_json(args), utc_now(),
            ),
        )
    observation = record_tool_observation(
        runner.DOMAIN_DB, task_id=other_task_id, call_id=call_id,
        attempt_id=attempt_id, tool_call_id=tool_call_id,
        tool_name="get_callback_delivery", arguments=args,
        status="OK", result=fact,
    )
    finish_attempt(runner.DOMAIN_DB, attempt_id, "OK", result_digest=observation["result_digest"])
    with connect(runner.DOMAIN_DB) as connection:
        connection.execute(
            """INSERT INTO assistant_calls
               (call_id,run_id,kind,logical_key,request_json,request_digest,status,
                result_json,observation_id,evidence_id,created_at,completed_at)
               VALUES (?,?,'MCP',?,?,?,?,?,?,?,?,?)""",
            (
                call_id, str(accepted["run_id"]), "cross-task-observation",
                canonical_json(request), digest_json(request), "OK", canonical_json(fact),
                observation["observation_id"], observation["evidence_id"], utc_now(), utc_now(),
            ),
        )
        connection.execute("UPDATE task_runs SET status='SUCCEEDED' WHERE run_id=?", (accepted["run_id"],))

    with pytest.raises(RuntimeError, match="OBSERVATION_TASK_ASSOCIATION_INVALID"):
        runner._audit_case(
            {
                **accepted,
                "case_id": CASE_ID,
                "run_id": accepted["run_id"],
                "session_id": accepted["session_id"],
                "message_id": accepted["message_id"],
            },
            0,
            0,
        )
