"""Prepare Task A's trusted S3 source in an isolated database for the Web E2E."""
from __future__ import annotations

import asyncio
import json
import time
from datetime import datetime, timezone
from pathlib import Path

from opspilot.config import ROOT
from opspilot.domain.database import reset_fixture
from opspilot.domain.s3 import get_s3_outcome, prepare_s3_fixture
from opspilot.domain.task_control import create_session, create_task_with_initial_run, trusted_identity
from opspilot.investigator import run_investigation
from opspilot.smokes.m4_02 import trace, write_json

EVIDENCE = ROOT / "docs/evidence/vnext/m4-eg-01"


async def main_async() -> int:
    stamp = datetime.now(timezone.utc).strftime("web-memory-%Y%m%dT%H%M%SZ")
    result_dir = EVIDENCE / "runs" / stamp
    result_dir.mkdir(parents=True, exist_ok=False)
    runtime = ROOT / ".runtime/m4-eg-01" / stamp
    runtime.mkdir(parents=True, exist_ok=False)
    db, checkpoint = runtime / "domain.sqlite3", runtime / "checkpoints.sqlite3"
    reset_fixture(db, "S1_POS")
    source_fixture = prepare_s3_fixture(
        db, "DELIVERY_FAILED", order_id="eg01-web-source",
        contract_version=1, failure_code="TEMPORARY_UNAVAILABLE",
        attempt_count=3, max_attempts=3, retry_state="EXHAUSTED",
    )
    target_fixture = prepare_s3_fixture(
        db, "DELIVERED_PENDING", order_id="eg01-web-target",
        contract_version=2, queue_age_seconds=60, processing_sla_seconds=300,
    )
    identity = trusted_identity(db, "support-a")
    session = create_session(db, identity)
    task = create_task_with_initial_run(
        db, identity, session_id=str(session["session_id"]),
        service_id="orders-async-demo", integration_id="async-integration-a",
        ticket_id="M4-EG-01-WEB-SOURCE",
        initial_message="订单接口返回 HTTP 200，但下游没有收到异步回调。请核对这个订单的当前事件和投递情况，不要重发。",
        idempotency_key=f"{stamp}-source-task", s3_order_id="eg01-web-source",
    )
    graph_result = await run_investigation(
        task_id=str(task["task_id"]), actor_id="support-a", db_path=db,
        checkpoint_db_path=checkpoint, run_id=str(task["run_id"]),
        s2_mode=True, evaluation_strategy="R",
    )
    outcome = get_s3_outcome(db, str(task["task_id"]))
    if not outcome or outcome.get("outcome") != "CALLBACK_DELIVERY_FAILED" or outcome.get("currentness") != "CURRENT":
        write_json(result_dir / "FAILURE.json", {"reason": "Task A did not reach current CALLBACK_DELIVERY_FAILED", "outcome": outcome})
        return 1
    seed = {
        "release_id": stamp, "database_path": str(db), "checkpoint_path": str(checkpoint),
        "source_task": task, "source_session_id": session["session_id"],
        "source_outcome": outcome, "source_graph_summary": {
            "stage": graph_result.get("graph_state", {}).get("stage"),
            "gate": graph_result.get("graph_state", {}).get("gate_decision"),
        },
        "fixture_preparation_only": {
            "source_order": source_fixture, "target_order": target_fixture,
            "target_task_not_created_until_web": True,
        },
        "source_policy": "R; no model calls; actual MCP/loopback HTTP evidence; not counted as agent-selected action",
        "source_trace": trace(db, str(task["task_id"])),
    }
    write_json(result_dir / "WEB-SEED.json", seed)
    print(json.dumps({"release_id": stamp, "database_path": str(db), "seed_path": str(result_dir / "WEB-SEED.json"),
                      "source_task_id": task["task_id"], "source_session_id": session["session_id"],
                      "outcome": outcome["outcome"], "mcp_observations": len(seed["source_trace"]["observations"]),
                      "http_observations": len(seed["source_trace"]["http"])}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main_async()))
