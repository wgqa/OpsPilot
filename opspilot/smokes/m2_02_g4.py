from __future__ import annotations

import argparse
import asyncio
import json
import sqlite3
import threading
from pathlib import Path
from typing import Any

import httpx

from opspilot.config import load_local_environment
from opspilot.domain.api import make_server
from opspilot.domain.database import get_credential_secret, reset_fixture
from opspilot.domain.s2_diagnosis import get_s2_task_outcome
from opspilot.domain.task_control import (
    admit_task_message,
    create_session,
    create_task_with_initial_run,
    trusted_identity,
)
from opspilot.investigator import run_investigation


def _db_rows(db_path: Path, query: str, params: tuple[object, ...]) -> list[dict[str, Any]]:
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    try:
        return [dict(row) for row in connection.execute(query, params).fetchall()]
    finally:
        connection.close()


def _live_request(db_path: Path) -> dict[str, object]:
    server = make_server(db_path, "tenant-a", "127.0.0.1", 0)
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
    thread.start()
    try:
        host, port = server.server_address
        response = httpx.get(
            f"http://{host}:{port}/api/orders/demo-order",
            headers={
                "X-Integration-ID": "integration-a",
                "Authorization": "Bearer " + get_credential_secret(db_path, "tenant-a", "cred-v2"),
            },
            timeout=5,
        )
        body = response.json()
        return {
            "status": response.status_code,
            "request_id": body.get("request_id"),
            "authn_event_id": body.get("authn_event_id"),
            "authz_event_id": body.get("authz_event_id"),
            "route": "/api/orders/demo-order",
        }
    finally:
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()


def _trace_snapshot(db_path: Path, task_id: str) -> dict[str, object]:
    return {
        "runs": _db_rows(
            db_path,
            "SELECT run_id, kind, status, blocked_reason, expected_control_revision, "
            "applied_critical_message_seq, created_at, started_at, ended_at "
            "FROM task_runs WHERE task_id = ? ORDER BY created_at, run_id",
            (task_id,),
        ),
        "model_calls": _db_rows(
            db_path,
            "SELECT call_id, model_id, prompt_digest, provider_response_id, status, usage_json, "
            "tool_calls_json, assistant_text "
            "FROM d2_model_traces WHERE task_id = ? ORDER BY rowid",
            (task_id,),
        ),
        "mcp_observations": _db_rows(
            db_path,
            "SELECT o.observation_id, o.created_at, o.tool_name, o.status, o.error_class, "
            "o.evidence_id, o.argument_digest, o.result_json, a.run_id "
            "FROM d2_tool_observations o JOIN d2_attempts a ON a.attempt_id = o.attempt_id "
            "WHERE o.task_id = ? ORDER BY o.rowid",
            (task_id,),
        ),
        "gate_traces": _db_rows(
            db_path,
            "SELECT run_id, decision, reason_code, request_id, decision_id, evidence_ids_json, "
            "predicate_json, created_at FROM s2_gate_traces WHERE task_id = ? ORDER BY created_at, rowid",
            (task_id,),
        ),
        "attempt_counts": {
            row["kind"]: row["n"]
            for row in _db_rows(
                db_path,
                "SELECT kind, COUNT(*) n FROM d2_attempts WHERE task_id = ? GROUP BY kind",
                (task_id,),
            )
        },
    }


async def _run(db_path: Path, checkpoint_path: Path, strategy: str = "A") -> dict[str, object]:
    load_local_environment()
    reset_fixture(db_path, "S2_SCOPE_DENIED")
    identity = trusted_identity(db_path, "support-a")
    session_id = str(create_session(db_path, identity)["session_id"])
    initial = create_task_with_initial_run(
        db_path,
        identity,
        session_id=session_id,
        service_id="orders-demo",
        integration_id="integration-a",
        ticket_id="M2-02-G4-REAL-001",
        initial_message="订单接口现在调不通，能帮我看一下吗？",
        idempotency_key="m2-02-g4-initial-real-provider-mcp",
    )
    task_id, first_run_id = str(initial["task_id"]), str(initial["run_id"])
    first_run_result = await run_investigation(
        task_id,
        identity.actor_id,
        db_path=db_path,
        checkpoint_db_path=checkpoint_path,
        run_id=first_run_id,
        d3_mode=True,
        s2_mode=True,
        executor_id="executor-a",
        evaluation_strategy=strategy,
    )

    corrected_request = _live_request(db_path)
    if corrected_request["status"] != 403 or not corrected_request["request_id"]:
        raise RuntimeError("The second bound-route request did not produce a real correlated HTTP 403.")
    correction = admit_task_message(
        db_path,
        identity,
        session_id=session_id,
        task_id=task_id,
        input_kind="CORRECT_TASK_INPUT",
        body=(
            "正式更正：请按这个当前真实请求重新调查 Request ID "
            f"{corrected_request['request_id']}。它只是调查线索；不要改变 Task 的服务、集成、主体或路由绑定。"
        ),
        idempotency_key="m2-02-g4-current-request-correction",
    )
    second_run_id = str(correction["run_id"])
    second_run_result = await run_investigation(
        task_id,
        identity.actor_id,
        db_path=db_path,
        checkpoint_db_path=checkpoint_path,
        run_id=second_run_id,
        d3_mode=True,
        s2_mode=True,
        executor_id="executor-a",
        evaluation_strategy=strategy,
    )
    outcome = get_s2_task_outcome(db_path, task_id)
    return {
        "journey_id": "G4",
        "strategy": strategy,
        "session_id": session_id,
        "task_id": task_id,
        "initial_message_id": initial.get("message_id"),
        "initial_run_id": first_run_id,
        "initial_graph_result": {
            "stage": first_run_result.get("graph_state", {}).get("stage"),
            "gate": first_run_result.get("graph_state", {}).get("gate_decision"),
        },
        "correction_message_id": correction.get("message_id"),
        "correction_control_revision": correction.get("expected_control_revision"),
        "correction_run_id": second_run_id,
        "corrected_real_http_request": corrected_request,
        "corrected_graph_result": {
            "stage": second_run_result.get("graph_state", {}).get("stage"),
            "gate": second_run_result.get("graph_state", {}).get("gate_decision"),
        },
        "business_outcome": outcome,
        "trace": _trace_snapshot(db_path, task_id),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the real Provider/MCP G4 correction journey.")
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--checkpoint-db", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--strategy", choices=("A", "H", "R"), default="A")
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    result = asyncio.run(_run(args.db, args.checkpoint_db, args.strategy))
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "journey_id": result["journey_id"],
        "strategy": result["strategy"],
        "task_id": result["task_id"],
        "initial_run_id": result["initial_run_id"],
        "correction_run_id": result["correction_run_id"],
        "correction_control_revision": result["correction_control_revision"],
        "outcome": result["business_outcome"].get("business_outcome"),
        "output": str(args.output),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
