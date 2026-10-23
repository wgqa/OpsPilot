"""Bounded real-provider S3 Episodic Memory ON/revoked comparison."""
from __future__ import annotations

import asyncio
import json
import os
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

from opspilot.config import ROOT, load_local_environment
from opspilot.domain.database import connect, reset_fixture
from opspilot.domain.episodic_memory import confirm_memory, create_memory_candidate, revoke_memory
from opspilot.domain.s3 import get_s3_outcome, prepare_s3_fixture
from opspilot.domain.task_control import create_session, create_task_with_initial_run, trusted_identity
from opspilot.investigator import run_investigation
from opspilot.smokes.m4_02 import business_snapshot, trace, write_json

EVIDENCE = ROOT / "docs/evidence/vnext/m4-03"
SYMPTOM = "订单接口返回 HTTP 200，但下游没有收到异步回调。请核实当前订单和回调事件，不要重发。"


def _task(db: Path, *, order_id: str, suffix: str, message: str = SYMPTOM) -> dict[str, object]:
    identity = trusted_identity(db, "support-a")
    session = create_session(db, identity)
    return create_task_with_initial_run(
        db, identity, session_id=str(session["session_id"]),
        service_id="orders-async-demo", integration_id="async-integration-a",
        ticket_id=f"M403-MEM-{suffix}", initial_message=message,
        idempotency_key=f"m403-memory-{suffix}-{time.time_ns()}", s3_order_id=order_id,
    )


def _memory_context(db: Path, task_id: str, memory_id: str) -> dict[str, object]:
    with connect(db) as connection:
        rows = [dict(row) for row in connection.execute(
            "SELECT selected_memories_json,excluded_sources_json,context_blocks_json,model_status,built_at FROM d5_context_provenance WHERE task_id=? ORDER BY rowid",
            (task_id,),
        )]
    selected, excluded = [], []
    for row in rows:
        selected.extend(json.loads(str(row["selected_memories_json"])))
        excluded.extend(json.loads(str(row["excluded_sources_json"])))
    return {
        "provenance_rows": rows,
        "selected_memory_ids": sorted({str(item["memory_id"]) for item in selected if item.get("memory_id")}),
        "target_memory_refs": [item for item in selected if item.get("memory_id") == memory_id],
        "target_exclusions": [item for item in excluded if item.get("source_id") == memory_id],
    }


async def _run(db: Path, checkpoint: Path, task: dict[str, object], *, memory_enabled: bool) -> dict[str, object]:
    started = time.perf_counter()
    failure = None
    run_result = None
    try:
        run_result = await run_investigation(
            task_id=str(task["task_id"]), actor_id="support-a", db_path=db,
            checkpoint_db_path=checkpoint, run_id=str(task["run_id"]),
            s2_mode=True, evaluation_strategy="A", _memory_enabled_for_test=memory_enabled,
        )
    except Exception as error:
        failure = {"class": type(error).__name__, "message": str(error)}
    raw = trace(db, str(task["task_id"]))
    outcome = get_s3_outcome(db, str(task["task_id"]))
    return {
        "task_id": task["task_id"], "session_id": task["session_id"], "run_id": task["run_id"],
        "outcome": outcome, "model_traces": raw["model_traces"], "mcp_observations": raw["observations"],
        "attempts": raw["attempts"], "contexts": raw["contexts"], "provider_request_contexts": raw["provider_request_contexts"],
        "evidence": raw["evidence"], "http": raw["http"], "run_result": run_result,
        "failure": failure, "elapsed_seconds": round(time.perf_counter() - started, 3),
        "total_tokens": sum(int(item.get("usage", {}).get("total_tokens", 0) or 0) for item in raw["model_traces"]),
    }


async def main_async() -> int:
    load_local_environment()
    if not os.environ.get("OPSPILOT_MODEL_API_KEY", "").strip() or not os.environ.get("OPSPILOT_MODEL_NAME", "").strip():
        raise RuntimeError("M4-03 Memory smoke requires configured Provider credentials; values are never printed.")
    stamp = datetime.now(timezone.utc).strftime("memory-%Y%m%dT%H%M%SZ")
    base = EVIDENCE / "runs" / stamp
    base.mkdir(parents=True, exist_ok=False)
    runtime = ROOT / ".runtime/m4-03" / stamp
    runtime.mkdir(parents=True, exist_ok=False)
    db, checkpoint = runtime / "domain.sqlite3", runtime / "checkpoints.sqlite3"
    result = {"status": "FAIL", "release": stamp, "provider_requests_max": 30}
    try:
        reset_fixture(db, "S1_POS")
        prepare_s3_fixture(db, "DELIVERY_FAILED", order_id="async-order", contract_version=1,
                           failure_code="TEMPORARY_UNAVAILABLE", attempt_count=3, max_attempts=3, retry_state="EXHAUSTED")
        prepare_s3_fixture(db, "DELIVERY_FAILED", order_id="async-order-2", contract_version=1,
                           failure_code="TEMPORARY_UNAVAILABLE", attempt_count=3, max_attempts=3, retry_state="EXHAUSTED")
        write_json(base / "PREPARATION.json", {
            "fact_state": "both bound orders completed with event-correlated HTTP 503, three exhausted retries",
            "orders": ["async-order", "async-order-2"], "agent_writes_expected": 0,
            "memory_source": "Task A; real R policy, MCP stdio and loopback HTTP; deterministic model-free diagnosis",
            "memory_review_actor": "approver-a",
        })
        source = _task(db, order_id="async-order", suffix="A")
        await run_investigation(task_id=str(source["task_id"]), actor_id="support-a", db_path=db,
                                checkpoint_db_path=checkpoint, run_id=str(source["run_id"]),
                                s2_mode=True, evaluation_strategy="R")
        source_outcome = get_s3_outcome(db, str(source["task_id"]))
        if not source_outcome or source_outcome["outcome"] != "CALLBACK_DELIVERY_FAILED":
            raise RuntimeError("Task A did not yield the frozen current diagnosis needed for a Memory source.")
        candidate = create_memory_candidate(db, str(source["task_id"]), "support-a",
                                            idempotency_key=f"{stamp}-candidate")
        active = confirm_memory(db, str(candidate["memory_id"]), "approver-a",
                                idempotency_key=f"{stamp}-confirm")
        memory_id = str(candidate["memory_id"])
        write_json(base / "TASK-A-SOURCE-AND-APPROVAL.json", {
            "source_task_id": source["task_id"], "source_run_id": source["run_id"],
            "source_diagnosis": source_outcome, "candidate": candidate, "approval": active,
            "source_trace": trace(db, str(source["task_id"])),
        })

        before = business_snapshot(db)
        target_on = _task(db, order_id="async-order-2", suffix="B-MEMORY-ON")
        on = await _run(db, checkpoint, target_on, memory_enabled=True)
        on["memory_context"] = _memory_context(db, str(target_on["task_id"]), memory_id)
        write_json(base / "TASK-B-MEMORY-ON.json", on)
        if not on["memory_context"]["target_memory_refs"]:
            raise RuntimeError("Real Provider attempt did not select the approved Task A Memory in its current context.")
        after_on = business_snapshot(db)
        if before != after_on:
            raise RuntimeError("Memory ON investigation changed the bound order/security business state.")

        # Change only the harness-owned test fixture after Task B. A similar
        # historical 503 case must be removed from later Provider contexts once
        # current 202/receiver facts contradict it.
        conflict_preparation = prepare_s3_fixture(
            db, "DELIVERED_PENDING", order_id="async-order-2", contract_version=1,
            queue_age_seconds=900, processing_sla_seconds=300,
        )
        write_json(base / "PREPARATION-CONFLICTING-CURRENT-FACTS.json", {
            "harness_action": "replace only the test fixture for the next isolated Task",
            "preparation": conflict_preparation,
            "agent_actions": [],
            "expected_current_direction": "WAIT_FOR_RECEIVER_PROCESSING",
        })
        before_conflict = business_snapshot(db)
        target_conflict = _task(db, order_id="async-order-2", suffix="C-CURRENT-CONFLICT")
        conflicting = await _run(db, checkpoint, target_conflict, memory_enabled=True)
        conflicting["memory_context"] = _memory_context(db, str(target_conflict["task_id"]), memory_id)
        write_json(base / "TASK-C-CONFLICTING-CURRENT-FACTS.json", conflicting)
        if not conflicting["memory_context"]["target_memory_refs"]:
            raise RuntimeError("The similar approved historical case was not present in the initial real Provider context.")
        if not any(item.get("reason") == "CURRENT_EVIDENCE_CONFLICTS_WITH_MEMORY"
                   for item in conflicting["memory_context"]["target_exclusions"]):
            raise RuntimeError("Current delivery evidence did not remove the conflicting Memory from later Provider context.")
        if not conflicting["outcome"] or conflicting["outcome"].get("outcome") != "RECEIVER_PROCESSING_UNCONFIRMED":
            raise RuntimeError("Current receiver-pending case did not retain its independently determined Gate outcome.")
        if "get_receiver_processing" not in [item["tool_name"] for item in conflicting["mcp_observations"]]:
            raise RuntimeError("Current 202 facts did not lead the live investigation to the receiver-processing query.")
        after_conflict = business_snapshot(db)
        if before_conflict != after_conflict:
            raise RuntimeError("Conflicting-memory investigation changed the bound order/security business state.")

        before_unrelated = business_snapshot(db)
        target_unrelated = _task(
            db, order_id="async-order-2", suffix="D-UNRELATED",
            message="请核对本月供应商发票的开票抬头、税号和价税合计差异；这是财务账单问题。",
        )
        unrelated = await _run(db, checkpoint, target_unrelated, memory_enabled=True)
        unrelated["memory_context"] = _memory_context(db, str(target_unrelated["task_id"]), memory_id)
        write_json(base / "TASK-D-UNRELATED-CASE.json", unrelated)
        if unrelated["memory_context"]["target_memory_refs"] or not any(
            item.get("reason") == "MEMORY_IRRELEVANT_TO_CURRENT_CASE"
            for item in unrelated["memory_context"]["target_exclusions"]
        ):
            raise RuntimeError("The approved S3 case Memory was not excluded from a real unrelated Provider context.")
        after_unrelated = business_snapshot(db)
        if before_unrelated != after_unrelated:
            raise RuntimeError("Unrelated-memory investigation changed the bound order/security business state.")

        revoked = revoke_memory(db, memory_id, "approver-a", idempotency_key=f"{stamp}-revoke")
        write_json(base / "MEMORY-REVOCATION.json", revoked)
        before_off = business_snapshot(db)
        target_off = _task(db, order_id="async-order-2", suffix="E-AFTER-REVOKE")
        off = await _run(db, checkpoint, target_off, memory_enabled=True)
        off["memory_context"] = _memory_context(db, str(target_off["task_id"]), memory_id)
        write_json(base / "TASK-E-AFTER-REVOKE.json", off)
        if off["memory_context"]["target_memory_refs"] or not off["memory_context"]["target_exclusions"]:
            raise RuntimeError("A post-revocation Provider context did not exclude the invalidated Memory with provenance.")
        after_off = business_snapshot(db)
        if before_off != after_off:
            raise RuntimeError("Post-revocation investigation changed the bound order/security business state.")
        provider_calls = (
            len(on["model_traces"]) + len(conflicting["model_traces"])
            + len(unrelated["model_traces"]) + len(off["model_traces"])
        )
        if provider_calls > 30:
            raise RuntimeError(f"Memory comparison exceeded the isolated 30-request safety cap: {provider_calls}.")
        result = {
            "status": "PASS" if all(item["failure"] is None for item in (on, conflicting, unrelated, off)) else "PARTIAL",
            "release": stamp, "provider": os.environ.get("OPSPILOT_MODEL_NAME"),
            "source_task_id": source["task_id"], "source_outcome": source_outcome["outcome"],
            "target_task_on": on["task_id"], "target_task_after_revoke": off["task_id"],
            "target_task_current_conflict": conflicting["task_id"],
            "target_task_unrelated_case": unrelated["task_id"],
            "memory_id": memory_id, "memory_state_after_revoke": revoked["state"],
            "different_source_and_target_tasks": str(source["task_id"]) != str(target_on["task_id"]),
            "memory_selected_in_real_provider_context": bool(on["memory_context"]["target_memory_refs"]),
            "revoked_memory_excluded_from_later_provider_context": not bool(off["memory_context"]["target_memory_refs"]),
            "conflicting_memory_removed_after_current_evidence": any(
                item.get("reason") == "CURRENT_EVIDENCE_CONFLICTS_WITH_MEMORY"
                for item in conflicting["memory_context"]["target_exclusions"]
            ),
            "unrelated_memory_excluded_in_real_provider_context": (
                not bool(unrelated["memory_context"]["target_memory_refs"])
                and any(item.get("reason") == "MEMORY_IRRELEVANT_TO_CURRENT_CASE"
                        for item in unrelated["memory_context"]["target_exclusions"])
            ),
            "revoke_exclusion_reasons": sorted({str(item.get("reason")) for item in off["memory_context"]["target_exclusions"]}),
            "memory_on": {"outcome": on["outcome"], "tools": [item["tool_name"] for item in on["mcp_observations"]],
                          "tokens": on["total_tokens"], "elapsed_seconds": on["elapsed_seconds"], "failure": on["failure"]},
            "current_fact_conflict": {"outcome": conflicting["outcome"],
                                      "tools": [item["tool_name"] for item in conflicting["mcp_observations"]],
                                      "selected_memory_contexts": len(conflicting["memory_context"]["target_memory_refs"]),
                                      "conflict_exclusions": conflicting["memory_context"]["target_exclusions"],
                                      "tokens": conflicting["total_tokens"], "elapsed_seconds": conflicting["elapsed_seconds"],
                                      "failure": conflicting["failure"]},
            "unrelated_case": {"outcome": unrelated["outcome"],
                               "tools": [item["tool_name"] for item in unrelated["mcp_observations"]],
                               "memory_exclusions": unrelated["memory_context"]["target_exclusions"],
                               "tokens": unrelated["total_tokens"], "elapsed_seconds": unrelated["elapsed_seconds"],
                               "failure": unrelated["failure"]},
            "after_revoke": {"outcome": off["outcome"], "tools": [item["tool_name"] for item in off["mcp_observations"]],
                             "tokens": off["total_tokens"], "elapsed_seconds": off["elapsed_seconds"], "failure": off["failure"]},
            "provider_requests": provider_calls, "provider_requests_max": 30,
            "no_agent_business_write": (
                before == after_on and before_conflict == after_conflict
                and before_unrelated == after_unrelated and before_off == after_off
            ),
            "evidence_dir": str(base.relative_to(ROOT)),
        }
        write_json(base / "RESULTS.json", result)
        return 0 if result["status"] == "PASS" else 1
    except Exception as error:
        (base / "FAILURE.txt").write_text("".join(traceback.format_exception(error)), encoding="utf-8")
        result.update({"failure": str(error), "evidence_dir": str(base.relative_to(ROOT))})
        write_json(base / "RESULTS.json", result)
        return 1


def main() -> int:
    return asyncio.run(main_async())


if __name__ == "__main__":
    raise SystemExit(main())
