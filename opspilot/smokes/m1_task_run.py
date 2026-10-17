from __future__ import annotations

import argparse
import asyncio
import json
import os
from importlib.metadata import version
from pathlib import Path

from opspilot.config import MODEL_API_KEY, MODEL_NAME, ROOT, database_path, load_local_environment
from opspilot.domain.d2 import create_task_binding
from opspilot.domain.database import connect, reset_fixture
from opspilot.domain.task_control import admit_task_message, trusted_identity
from opspilot.investigator import run_investigation


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the real-model M1-01 durable TaskRun integration smoke.")
    parser.add_argument("--db", default=".runtime/m1-task-run.sqlite3")
    parser.add_argument("--checkpoint-db", default=".runtime/m1-task-run-checkpoints.sqlite3")
    args = parser.parse_args()
    load_local_environment()
    if not os.environ.get(MODEL_API_KEY) or not os.environ.get(MODEL_NAME):
        print(json.dumps({"status": "NOT_RUN", "reason": "model_configuration_missing", "secret_emitted": False}))
        return 2

    db = database_path(args.db)
    checkpoint = Path(args.checkpoint_db)
    if not checkpoint.is_absolute():
        checkpoint = ROOT / checkpoint
    checkpoint = checkpoint.resolve()
    reset_fixture(db, "S1_POS")
    binding = create_task_binding(db, "support-a", "orders-demo", "integration-a", "INC-A-001")
    identity = trusted_identity(db, "support-a")
    accepted = admit_task_message(
        db,
        identity,
        session_id=str(binding["session_id"]),
        task_id=str(binding["task_id"]),
        input_kind="CORRECT_TASK_INPUT",
        body=(
            "The same orders service returns HTTP 401 after its scheduled service-account credential rotation. "
            "Please verify the current integration credential reference and accepted authentication policy."
        ),
        idempotency_key="m1-real-smoke-correction",
    )
    try:
        result = asyncio.run(
            run_investigation(
                str(binding["task_id"]),
                "support-a",
                db_path=db,
                checkpoint_db_path=checkpoint,
                d3_mode=True,
                executor_id="executor-a",
                run_id=str(accepted["run_id"]),
            )
        )
    except Exception as error:
        error_code = getattr(error, "code", None)
        print(json.dumps({
            "status": "FAIL",
            "case": "M1-01_REAL_TASK_RUN_MODEL_MCP",
            "error_class": type(error).__name__,
            "error_code": error_code,
            "secret_emitted": False,
        }, ensure_ascii=False, sort_keys=True))
        return 1
    with connect(db) as connection:
        run = connection.execute("SELECT status, expected_control_revision, consumed_message_seq FROM task_runs WHERE run_id = ?", (accepted["run_id"],)).fetchone()
        control = connection.execute(
            "SELECT terminal_state, control_revision, pending_critical_message_seq, applied_critical_message_seq FROM task_controls WHERE task_id = ?",
            (binding["task_id"],),
        ).fetchone()
        plan_binding = connection.execute(
            "SELECT bound_control_revision, consumed_message_seq, task_run_id FROM d3_plan_control_bindings WHERE task_id = ?",
            (binding["task_id"],),
        ).fetchone()
        traces = connection.execute(
            "SELECT model_id, status, usage_json, tool_calls_json FROM d2_model_traces WHERE task_id = ? ORDER BY created_at",
            (binding["task_id"],),
        ).fetchall()
        observations = connection.execute(
            "SELECT tool_name, status FROM d2_tool_observations WHERE task_id = ? ORDER BY created_at",
            (binding["task_id"],),
        ).fetchall()
        config_version = connection.execute(
            "SELECT config_version FROM integrations WHERE tenant_id = 'tenant-a' AND integration_id = 'integration-a'"
        ).fetchone()[0]
    action_state = result.get("action_state", {})
    stage = result.get("graph_state", {}).get("stage") if isinstance(result.get("graph_state"), dict) else None
    checks = {
        "run_waiting_for_approval": run["status"] == "WAITING_APPROVAL",
        "control_revision_consumed": (
            control["terminal_state"] == "ACTIVE"
            and control["control_revision"] == 2
            and control["pending_critical_message_seq"] is None
            and control["applied_critical_message_seq"] == accepted["sequence"]
        ),
        "plan_bound_to_run_and_revision": (
            plan_binding is not None
            and plan_binding["bound_control_revision"] == run["expected_control_revision"] == 2
            and plan_binding["consumed_message_seq"] == accepted["sequence"]
            and plan_binding["task_run_id"] == accepted["run_id"]
        ),
        "evidence_gate_ready": stage == "d3_plan_created",
        "approval_interrupt_pending": result.get("next_nodes") == ["d3_human_approval"],
        "no_business_write_before_approval": (
            config_version == 7
            and not action_state.get("action_intents")
            and not action_state.get("action_ledgers")
        ),
        "real_model_and_mcp_trace": bool(traces) and bool(observations),
    }
    output = {
        "status": "PASS" if all(checks.values()) else "FAIL",
        "case": "M1-01_REAL_TASK_RUN_MODEL_MCP",
        "task_id": binding["task_id"],
        "thread_id": binding["thread_id"],
        "session_id": binding["session_id"],
        "message_id": accepted["message_id"],
        "run_id": accepted["run_id"],
        "model_id": traces[-1]["model_id"] if traces else None,
        "model_call_count": len(traces),
        "model_statuses": [row["status"] for row in traces],
        "usage": [json.loads(str(row["usage_json"])) for row in traces],
        "function_calls": [json.loads(str(row["tool_calls_json"])) for row in traces],
        "mcp_observations": [{"tool_name": row["tool_name"], "status": row["status"]} for row in observations],
        "graph_stage": stage,
        "next_nodes": result.get("next_nodes"),
        "run_status": run["status"],
        "control": dict(control),
        "plan_control_binding": dict(plan_binding) if plan_binding is not None else None,
        "config_version": config_version,
        "checks": checks,
        "dependencies": {
            package: version(package)
            for package in ("langchain", "langchain-openai", "langgraph", "langgraph-checkpoint-sqlite", "mcp", "pydantic")
        },
        "secrets_emitted": False,
    }
    print(json.dumps(output, ensure_ascii=False, sort_keys=True, default=str))
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
