"""Bounded, real Provider/MCP cross-Task Memory comparison for M4-EG-01.

This evidence harness reuses the accepted M4-03 Domain preparation helpers.
It creates one trusted Task A source, approves its method-only Memory, clones
the same pre-Task-B SQLite state, then runs paired Memory ON/OFF Tasks and
current-fact conflict, unrelated-input, and post-revocation cases.
"""
from __future__ import annotations

import asyncio
import json
import os
import shutil
import sqlite3
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

from opspilot.config import ROOT, load_local_environment
from opspilot.domain.database import connect, reset_fixture
from opspilot.domain.episodic_memory import confirm_memory, create_memory_candidate, revoke_memory
from opspilot.domain.s3 import get_s3_outcome, prepare_s3_fixture
from opspilot.investigator import run_investigation
from opspilot.smokes.m4_02 import business_snapshot, trace, write_json
from opspilot.smokes.m4_03_memory import _memory_context, _run, _task

EVIDENCE = ROOT / "docs/evidence/vnext/m4-eg-01"
TARGET_INPUT = (
    "订单接口返回 HTTP 200，但下游没有收到异步回调。"
    "上次遇到过类似问题，请参考之前确认的调查方法，再核实这个 Task 自己的当前事件，不要重发。"
)


def _clone_database(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(source) as source_connection, sqlite3.connect(target) as target_connection:
        source_connection.backup(target_connection)


async def _source_task(db: Path, checkpoint: Path, order_id: str, stamp: str) -> tuple[dict[str, object], dict[str, object]]:
    task = _task(db, order_id=order_id, suffix=f"{stamp}-A")
    result = await run_investigation(
        task_id=str(task["task_id"]), actor_id="support-a", db_path=db,
        checkpoint_db_path=checkpoint, run_id=str(task["run_id"]),
        s2_mode=True, evaluation_strategy="R",
    )
    outcome = get_s3_outcome(db, str(task["task_id"]))
    if not outcome or outcome.get("outcome") != "CALLBACK_DELIVERY_FAILED":
        raise RuntimeError("Trusted Task A preparation did not produce the required current failed-delivery outcome.")
    return task, {"graph_result": result, "outcome": outcome, "trace": trace(db, str(task["task_id"]))}


async def main_async() -> int:
    load_local_environment()
    if not os.environ.get("OPSPILOT_MODEL_API_KEY", "").strip() or not os.environ.get("OPSPILOT_MODEL_NAME", "").strip():
        raise RuntimeError("M4-EG-01 real Provider comparison needs local credentials; values are never printed.")
    stamp = datetime.now(timezone.utc).strftime("memory-paired-%Y%m%dT%H%M%SZ")
    result_dir = EVIDENCE / "runs" / stamp
    result_dir.mkdir(parents=True, exist_ok=False)
    runtime = ROOT / ".runtime/m4-eg-01" / stamp
    runtime.mkdir(parents=True, exist_ok=False)
    base_db = runtime / "source-domain.sqlite3"
    base_checkpoint = runtime / "source-checkpoints.sqlite3"
    on_db, off_db = runtime / "memory-on.sqlite3", runtime / "memory-off.sqlite3"
    on_checkpoint, off_checkpoint = runtime / "memory-on-checkpoints.sqlite3", runtime / "memory-off-checkpoints.sqlite3"
    release = {
        "release_id": stamp,
        "git_sha": os.environ.get("OPSPILOT_RELEASE_SHA"),
        "provider_model": os.environ.get("OPSPILOT_MODEL_NAME"),
        "knowledge_manifest_sha256": None,
        "memory_enabled_flag": "existing _memory_enabled_for_test switch; no runtime policy change",
        "default_budget": {"model_requests": 8, "mcp_calls": 6},
        "provider_request_max": 40,
        "case_plan": ["E1_ON", "E1_OFF", "E2_CONFLICT", "E3_IRRELEVANT", "E4_REVOKED"],
        "target_input_identical_for_e1": True,
    }
    result: dict[str, object] = {
        **release,
        "status": "FAIL",
        "evidence_dir": str(result_dir.relative_to(ROOT)),
    }
    try:
        reset_fixture(base_db, "S1_POS")
        prepare_s3_fixture(
            base_db, "DELIVERY_FAILED", order_id="eg01-memory-source",
            contract_version=1, failure_code="TEMPORARY_UNAVAILABLE",
            attempt_count=3, max_attempts=3, retry_state="EXHAUSTED",
        )
        prepare_s3_fixture(
            base_db, "DELIVERED_PENDING", order_id="eg01-memory-target",
            contract_version=1, queue_age_seconds=60, processing_sla_seconds=300,
        )
        source, source_preparation = await _source_task(
            base_db, base_checkpoint, "eg01-memory-source", stamp,
        )
        candidate = create_memory_candidate(
            base_db, str(source["task_id"]), "support-a", idempotency_key=f"{stamp}-candidate",
        )
        active = confirm_memory(
            base_db, str(candidate["memory_id"]), "approver-a", idempotency_key=f"{stamp}-confirm",
        )
        memory_id = str(active["memory_id"])
        with connect(base_db) as connection:
            row = connection.execute(
                "SELECT version, state, experience_json, content_digest, source_task_id FROM d5_memories WHERE memory_id=?",
                (memory_id,),
            ).fetchone()
            content_sha = str(row["content_digest"])
        preparation = {
            "test_setup_only": True,
            "source_task_id": source["task_id"], "source_run_id": source["run_id"],
            "source_outcome": source_preparation["outcome"],
            "source_trace": source_preparation["trace"],
            "candidate": candidate, "trusted_approver_action": active,
            "memory_id": memory_id, "memory_version": int(row["version"]),
            "memory_digest": content_sha, "source_task_is_not_target_task": True,
            "agent_business_writes_expected": 0,
        }
        write_json(result_dir / "PREPARATION.json", preparation)

        # Both E1 arms start from the same point-in-time Domain snapshot.
        _clone_database(base_db, on_db)
        _clone_database(base_db, off_db)
        on_before, off_before = business_snapshot(on_db), business_snapshot(off_db)
        target_on = _task(on_db, order_id="eg01-memory-target", suffix=f"{stamp}-E1-ON", message=TARGET_INPUT)
        target_off = _task(off_db, order_id="eg01-memory-target", suffix=f"{stamp}-E1-OFF", message=TARGET_INPUT)
        on = await _run(on_db, on_checkpoint, target_on, memory_enabled=True)
        off = await _run(off_db, off_checkpoint, target_off, memory_enabled=False)
        on["memory_context"] = _memory_context(on_db, str(target_on["task_id"]), memory_id)
        off["memory_context"] = _memory_context(off_db, str(target_off["task_id"]), memory_id)
        write_json(result_dir / "E1-MEMORY-ON.json", on)
        write_json(result_dir / "E1-MEMORY-OFF.json", off)
        if not on["memory_context"]["target_memory_refs"]:
            raise RuntimeError("E1 ON did not place the approved Task A Memory in the actual Provider context.")
        if off["memory_context"]["target_memory_refs"]:
            raise RuntimeError("E1 OFF unexpectedly selected the approved Task A Memory.")
        if on_before != business_snapshot(on_db) or off_before != business_snapshot(off_db):
            raise RuntimeError("E1 investigation changed current business/security facts.")
        e1_business_snapshot_unchanged = True

        # E2: the historical delivery-failure method is present initially, but
        # an independent current receiver observation must govern the outcome.
        conflict_setup = prepare_s3_fixture(
            on_db, "DELIVERED_PENDING", order_id="eg01-memory-target",
            contract_version=1, queue_age_seconds=900, processing_sla_seconds=300,
        )
        conflict = _task(on_db, order_id="eg01-memory-target", suffix=f"{stamp}-E2-CONFLICT", message=TARGET_INPUT)
        conflict_result = await _run(on_db, on_checkpoint, conflict, memory_enabled=True)
        conflict_result["memory_context"] = _memory_context(on_db, str(conflict["task_id"]), memory_id)
        write_json(result_dir / "E2-CURRENT-FACT-CONFLICT.json", {"fixture_preparation": conflict_setup, **conflict_result})
        if not conflict_result["memory_context"]["target_memory_refs"]:
            raise RuntimeError("E2 did not expose the historical method before new current evidence was observed.")
        if not any(item.get("reason") == "CURRENT_EVIDENCE_CONFLICTS_WITH_MEMORY" for item in conflict_result["memory_context"]["target_exclusions"]):
            raise RuntimeError("E2 current evidence did not invalidate the conflicting historical method in later context.")
        if not conflict_result.get("outcome") or conflict_result["outcome"].get("outcome") != "RECEIVER_PROCESSING_UNCONFIRMED":
            raise RuntimeError("E2 outcome did not follow Task B's current receiver facts.")

        # E3: a finance question does not consume callback failure Memory.
        unrelated = _task(
            on_db, order_id="eg01-memory-target", suffix=f"{stamp}-E3-IRRELEVANT",
            message="请核对本月供应商发票的开票抬头、税号和价税合计差异；这是财务账单问题。",
        )
        unrelated_result = await _run(on_db, on_checkpoint, unrelated, memory_enabled=True)
        unrelated_result["memory_context"] = _memory_context(on_db, str(unrelated["task_id"]), memory_id)
        write_json(result_dir / "E3-IRRELEVANT.json", unrelated_result)
        if unrelated_result["memory_context"]["target_memory_refs"] or not any(
            item.get("reason") == "MEMORY_IRRELEVANT_TO_CURRENT_CASE"
            for item in unrelated_result["memory_context"]["target_exclusions"]
        ):
            raise RuntimeError("E3 did not exclude irrelevant callback Memory from actual Provider context.")

        revoked = revoke_memory(on_db, memory_id, "approver-a", idempotency_key=f"{stamp}-revoke")
        write_json(result_dir / "E4-REVOCATION.json", revoked)
        after_revoke = _task(on_db, order_id="eg01-memory-target", suffix=f"{stamp}-E4-REVOKED", message=TARGET_INPUT)
        after_revoke_result = await _run(on_db, on_checkpoint, after_revoke, memory_enabled=True)
        after_revoke_result["memory_context"] = _memory_context(on_db, str(after_revoke["task_id"]), memory_id)
        write_json(result_dir / "E4-AFTER-REVOCATION.json", after_revoke_result)
        if after_revoke_result["memory_context"]["target_memory_refs"] or not after_revoke_result["memory_context"]["target_exclusions"]:
            raise RuntimeError("E4 revoked Memory was reloaded or lacked exclusion provenance.")

        cases = [on, off, conflict_result, unrelated_result, after_revoke_result]
        provider_requests = sum(len(item.get("model_traces", [])) for item in cases)
        if provider_requests > int(release["provider_request_max"]):
            raise RuntimeError(f"Memory E1-E4 exceeded its frozen 40-request allocation: {provider_requests}.")
        trace_path = result_dir / "TRACE.jsonl"
        with trace_path.open("w", encoding="utf-8", newline="\n") as stream:
            for case in cases:
                for call in case.get("model_traces", []):
                    stream.write(json.dumps({"kind": "provider_call", "task_id": case["task_id"], **call}, ensure_ascii=False) + "\n")
                for observation in case.get("mcp_observations", []):
                    stream.write(json.dumps({"kind": "mcp_observation", "task_id": case["task_id"], **observation}, ensure_ascii=False) + "\n")
        total_tokens = sum(
            int(trace_item.get("usage", {}).get("total_tokens", 0) or 0)
            for case_result in cases for trace_item in case_result.get("model_traces", [])
        )
        result = {
            **release, "status": "PASS" if all(item.get("failure") is None for item in cases) else "PARTIAL",
            "source_task_id": source["task_id"], "memory_id": memory_id,
            "memory_state_after_revoke": revoked.get("state"), "memory_digest": content_sha,
            "task_b_on_id": on["task_id"], "task_b_off_id": off["task_id"],
            "on_and_off_use_distinct_tasks": on["task_id"] != off["task_id"] and source["task_id"] not in {on["task_id"], off["task_id"]},
            "on_selected_memory": bool(on["memory_context"]["target_memory_refs"]),
            "off_excluded_memory": not bool(off["memory_context"]["target_memory_refs"]),
            "e2_current_evidence_overrode_memory": any(item.get("reason") == "CURRENT_EVIDENCE_CONFLICTS_WITH_MEMORY" for item in conflict_result["memory_context"]["target_exclusions"]),
            "e3_irrelevant_memory_excluded": not bool(unrelated_result["memory_context"]["target_memory_refs"]),
            "e4_revoked_memory_excluded": not bool(after_revoke_result["memory_context"]["target_memory_refs"]),
            "provider_requests": provider_requests, "provider_requests_max": release["provider_request_max"],
            "total_tokens": total_tokens,
            "case_summary": {
                "E1_ON": {"outcome": on.get("outcome"), "tools": [item.get("tool_name") for item in on.get("mcp_observations", [])], "tokens": on.get("total_tokens"), "latency_seconds": on.get("elapsed_seconds"), "failure": on.get("failure")},
                "E1_OFF": {"outcome": off.get("outcome"), "tools": [item.get("tool_name") for item in off.get("mcp_observations", [])], "tokens": off.get("total_tokens"), "latency_seconds": off.get("elapsed_seconds"), "failure": off.get("failure")},
                "E2": {"outcome": conflict_result.get("outcome"), "tools": [item.get("tool_name") for item in conflict_result.get("mcp_observations", [])], "tokens": conflict_result.get("total_tokens"), "latency_seconds": conflict_result.get("elapsed_seconds"), "failure": conflict_result.get("failure")},
                "E3": {"outcome": unrelated_result.get("outcome"), "tools": [item.get("tool_name") for item in unrelated_result.get("mcp_observations", [])], "tokens": unrelated_result.get("total_tokens"), "latency_seconds": unrelated_result.get("elapsed_seconds"), "failure": unrelated_result.get("failure")},
                "E4": {"outcome": after_revoke_result.get("outcome"), "tools": [item.get("tool_name") for item in after_revoke_result.get("mcp_observations", [])], "tokens": after_revoke_result.get("total_tokens"), "latency_seconds": after_revoke_result.get("elapsed_seconds"), "failure": after_revoke_result.get("failure")},
            },
            "e1_business_snapshot_unchanged_before_harness_fixture_mutation": e1_business_snapshot_unchanged,
            "harness_changes_target_fixture_after_e1_for_e2": True,
            "evidence_dir": str(result_dir.relative_to(ROOT)),
        }
        write_json(result_dir / "RESULTS.json", result)
        return 0 if result["status"] == "PASS" else 1
    except Exception as error:
        (result_dir / "FAILURE.txt").write_text("".join(traceback.format_exception(error)), encoding="utf-8")
        result.update({"status": "FAIL", "failure": str(error), "evidence_dir": str(result_dir.relative_to(ROOT))})
        write_json(result_dir / "RESULTS.json", result)
        return 1


def main() -> int:
    return asyncio.run(main_async())


if __name__ == "__main__":
    raise SystemExit(main())
