"""One bounded real-provider check that an explicit protocol question uses Knowledge."""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import time
import traceback
from pathlib import Path

from opspilot.config import ROOT, load_local_environment
from opspilot.domain.database import reset_fixture
from opspilot.domain.s3 import get_s3_outcome, prepare_s3_fixture
from opspilot.domain.task_control import (
    create_session,
    create_task_with_initial_run,
    trusted_identity,
)
from opspilot.investigator import run_investigation
from opspilot.smokes.m4_02 import trace, write_json


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release", required=True, help="Unique evidence run identifier")
    return parser.parse_args()


async def _run(release: str) -> int:
    load_local_environment()
    model = os.environ.get("OPSPILOT_MODEL_NAME", "").strip()
    if not os.environ.get("OPSPILOT_MODEL_API_KEY", "").strip() or not model:
        raise RuntimeError("Provider credentials are required; values are never printed.")

    evidence_root = ROOT / "docs/evidence/vnext/m4-03/runs" / release
    evidence_root.mkdir(parents=True, exist_ok=False)
    work_root = ROOT / ".runtime/m4-03/knowledge-live" / release
    work_root.mkdir(parents=True, exist_ok=True)
    db = work_root / "domain.sqlite3"
    checkpoint = work_root / "checkpoints.sqlite3"

    reset_fixture(db, "S1_POS")
    preparation = prepare_s3_fixture(
        db,
        "DELIVERED_PENDING",
        order_id="async-order-2",
        contract_version=2,
        queue_age_seconds=1800,
        processing_sla_seconds=300,
    )
    identity = trusted_identity(db, "support-a")
    session = create_session(db, identity)
    task = create_task_with_initial_run(
        db,
        identity,
        session_id=str(session["session_id"]),
        service_id="orders-async-demo",
        integration_id="async-integration-a",
        ticket_id=f"M403-KNOWLEDGE-{release[-24:]}",
        initial_message=(
            "订单 async-order-2 接口返回 200，回调接收方返回 202。"
            "请按当前绑定的协议版本查明：202 是否表示接收方已处理？"
            "请核对当前订单、关联投递事件与接收队列，再给出当前处理方向。"
            "不要重发回调。"
        ),
        idempotency_key=f"{release}-{time.time_ns()}",
        s3_order_id="async-order-2",
    )

    started = time.perf_counter()
    failure = None
    run_result = None
    try:
        run_result = await run_investigation(
            task_id=str(task["task_id"]),
            actor_id="support-a",
            db_path=db,
            checkpoint_db_path=checkpoint,
            run_id=str(task["run_id"]),
            s2_mode=True,
            evaluation_strategy="A",
        )
    except Exception as error:  # keep real Provider/MCP failures as a result
        failure = {
            "class": type(error).__name__,
            "message": str(error),
            "traceback": traceback.format_exc(),
        }

    captured = trace(db, str(task["task_id"]))
    outcome = get_s3_outcome(db, str(task["task_id"]))
    observations = captured.get("observations", [])
    knowledge_calls = [
        row for row in observations if row.get("tool_name") == "search_callback_knowledge"
    ]
    total_tokens = sum(
        int((row.get("usage") or {}).get("total_tokens", 0) or 0)
        for row in captured.get("model_traces", [])
    )
    no_business_writes = not outcome or int(outcome.get("body", {}).get("business_writes", 0)) == 0
    passed = (
        failure is None
        and bool(knowledge_calls)
        and outcome is not None
        and outcome.get("outcome") == "RECEIVER_PROCESSING_UNCONFIRMED"
        and outcome.get("recovered") is False
        and no_business_writes
    )
    result = {
        "release": release,
        "status": "PASS" if passed else "FAIL",
        "model": model,
        "task_id": task["task_id"],
        "run_id": task["run_id"],
        "order_id": "async-order-2",
        "contract_version": 2,
        "fixture_preparation": preparation,
        "outcome": outcome,
        "tools": [row.get("tool_name") for row in observations],
        "knowledge_calls": knowledge_calls,
        "model_traces": captured.get("model_traces", []),
        "provider_request_contexts": captured.get("provider_request_contexts", []),
        "mcp_observations": observations,
        "http": captured.get("http", []),
        "evidence": captured.get("evidence", []),
        "contexts": captured.get("contexts", []),
        "run_result": run_result,
        "provider_calls": len(captured.get("model_traces", [])),
        "tokens": total_tokens,
        "elapsed_seconds": round(time.perf_counter() - started, 3),
        "agent_business_writes": 0 if no_business_writes else None,
        "failure": failure,
        "evidence_dir": str(evidence_root.relative_to(ROOT)),
    }
    write_json(evidence_root / "RESULTS.json", result)
    write_json(evidence_root / "TRACE.json", captured)
    print(
        json.dumps(
            {
                "release": release,
                "status": result["status"],
                "task_id": task["task_id"],
                "outcome": outcome.get("outcome") if outcome else None,
                "tools": result["tools"],
                "knowledge_calls": len(knowledge_calls),
                "provider_calls": result["provider_calls"],
                "tokens": total_tokens,
                "elapsed_seconds": result["elapsed_seconds"],
                "evidence_dir": result["evidence_dir"],
            },
            ensure_ascii=False,
        ),
        flush=True,
    )
    return 0 if passed else 1


def main() -> int:
    args = _arguments()
    return asyncio.run(_run(args.release))


if __name__ == "__main__":
    raise SystemExit(main())
