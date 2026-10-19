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
from opspilot.smokes.m2_02_g4 import _trace_snapshot


def _real_401(db_path: Path) -> dict[str, object]:
    server = make_server(db_path, "tenant-a", "127.0.0.1", 0)
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
    thread.start()
    try:
        host, port = server.server_address
        response = httpx.get(
            f"http://{host}:{port}/api/orders/demo-order",
            headers={
                "X-Integration-ID": "integration-a",
                "Authorization": "Bearer " + get_credential_secret(db_path, "tenant-a", "cred-v1"),
            },
            timeout=5,
        )
        body = response.json()
        return {
            "status": response.status_code,
            "request_id": body.get("request_id"),
            "authn_event_id": body.get("authn_event_id"),
            "route": "/api/orders/demo-order",
        }
    finally:
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()


async def _run(db_path: Path, checkpoint_path: Path, strategy: str = "A") -> dict[str, object]:
    load_local_environment()
    reset_fixture(db_path, "S2_INVALID_CREDENTIAL")
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "UPDATE integrations SET credential_ref='cred-v1', config_version=config_version+1 "
            "WHERE tenant_id='tenant-a' AND integration_id='integration-a'"
        )
    old_request = _real_401(db_path)
    identity = trusted_identity(db_path, "support-a")
    session_id = str(create_session(db_path, identity)["session_id"])
    initial = create_task_with_initial_run(
        db_path,
        identity,
        session_id=session_id,
        service_id="orders-demo",
        integration_id="integration-a",
        ticket_id="INC-A-001",
        initial_message=f"先核实这个可能过期的 Request ID：{old_request['request_id']}。",
        idempotency_key="m2-02-g4-401-initial",
    )
    task_id, first_run_id = str(initial["task_id"]), str(initial["run_id"])
    first = await run_investigation(
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
    corrected_request = _real_401(db_path)
    if corrected_request.get("status") != 401 or not corrected_request.get("request_id"):
        raise RuntimeError("G4-H2 correction fixture did not create a real correlated HTTP 401 event.")
    correction = admit_task_message(
        db_path,
        identity,
        session_id=session_id,
        task_id=task_id,
        input_kind="CORRECT_TASK_INPUT",
        body=(
            "更正一下，前一个请求不属于这次故障。请改查这个 Request ID："
            f"{corrected_request['request_id']}。服务、集成、主体和路由保持原绑定。"
        ),
        idempotency_key="m2-02-g4-401-correction",
    )
    second_run_id = str(correction["run_id"])
    second = await run_investigation(
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
    with sqlite3.connect(db_path) as connection:
        control = connection.execute(
            "SELECT control_revision, pending_critical_message_seq, applied_critical_message_seq "
            "FROM task_controls WHERE task_id=?", (task_id,),
        ).fetchone()
        side_effects = {
            table: int(connection.execute(f"SELECT COUNT(*) FROM {table} WHERE task_id=?", (task_id,)).fetchone()[0])
            for table in ("d3_action_intents", "d3_action_ledgers", "s2_diagnosis_receipts", "s2_handoff_drafts")
        }
    return {
        "case_id": "G4-H2",
        "strategy": strategy,
        "task_id": task_id,
        "initial_message_id": initial.get("message_id"),
        "initial_run_id": first_run_id,
        "initial_run_status": _trace_snapshot(db_path, task_id)["runs"][0]["status"],
        "initial_gate": first.get("graph_state", {}).get("gate_decision"),
        "old_real_http_request": old_request,
        "correction_message_id": correction.get("message_id"),
        "correction_control_revision": correction.get("expected_control_revision"),
        "corrected_real_http_request": corrected_request,
        "corrected_run_id": second_run_id,
        "corrected_gate": second.get("graph_state", {}).get("gate_decision"),
        "business_outcome": get_s2_task_outcome(db_path, task_id),
        "control": {
            "revision": int(control[0]),
            "pending_critical_message_seq": control[1],
            "applied_critical_message_seq": int(control[2]),
        },
        "side_effects": side_effects,
        "trace": _trace_snapshot(db_path, task_id),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the real Provider/MCP G4-H2 correction-to-401 journey.")
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--checkpoint-db", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--strategy", choices=("A", "H", "R"), default="A")
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    result = asyncio.run(_run(args.db, args.checkpoint_db, args.strategy))
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "case_id": result["case_id"],
        "strategy": result["strategy"],
        "task_id": result["task_id"],
        "control_revision": result["control"]["revision"],
        "initial_gate": result["initial_gate"],
        "corrected_gate": result["corrected_gate"],
        "business_outcome": result["business_outcome"].get("business_outcome"),
        "side_effects": result["side_effects"],
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
