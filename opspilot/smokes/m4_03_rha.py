"""Fresh frozen S3 R/H/A evaluation. Gold facts never enter model context."""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

from opspilot.config import ROOT, load_local_environment
from opspilot.domain.database import connect, reset_fixture
from opspilot.domain.s3 import get_s3_outcome, prepare_s3_fixture
from opspilot.domain.task_control import create_session, create_task_with_initial_run, trusted_identity
from opspilot.smokes.m4_02 import business_snapshot, trace, write_json
from opspilot.investigator import run_investigation

EVIDENCE = ROOT / "docs/evidence/vnext/m4-03"


def _case_facts(case: dict[str, object], cases: dict[str, dict[str, object]]) -> dict[str, object]:
    facts = dict(case["facts"])
    same = facts.get("same_business_facts_as")
    if same:
        source = cases[str(same)]
        facts = {**dict(source["facts"]), **{k: v for k, v in facts.items() if k != "same_business_facts_as"}}
    return facts


def _prepare(db: Path, case: dict[str, object], facts: dict[str, object]) -> dict[str, object]:
    if facts.get("order_status") == "PROCESSING":
        return prepare_s3_fixture(db, "PROCESSING", order_id=str(case["order_ref"]),
                                  contract_version=int(facts.get("contract_version", 1)))
    if facts.get("delivery_http_status") == 503:
        attempts, maximum = int(facts.get("attempt_count", 1)), int(facts.get("max_attempts", 3))
        retry_state = str(facts.get("retry_state", "EXHAUSTED" if attempts >= maximum else "SCHEDULED"))
        return prepare_s3_fixture(db, "DELIVERY_FAILED", order_id=str(case["order_ref"]),
                                  contract_version=int(facts.get("contract_version", 1)),
                                  failure_code=str(facts.get("failure_code", "TEMPORARY_UNAVAILABLE")),
                                  attempt_count=attempts, max_attempts=maximum, retry_state=retry_state)
    if facts.get("delivery_http_status") == 202:
        return prepare_s3_fixture(db, "DELIVERED_PENDING", order_id=str(case["order_ref"]),
                                  contract_version=int(facts.get("contract_version", 1)),
                                  queue_age_seconds=int(facts.get("queue_age_seconds", 60)),
                                  processing_sla_seconds=int(facts.get("processing_sla_seconds", 300)))
    raise ValueError(f"Unsupported frozen S3 facts for {case['case_id']}")


def _new_task(db: Path, case: dict[str, object], strategy: str):
    identity = trusted_identity(db, "support-a")
    session = create_session(db, identity)
    return create_task_with_initial_run(
        db, identity, session_id=str(session["session_id"]), service_id="orders-async-demo",
        integration_id="async-integration-a", ticket_id=f"M403-{case['case_id']}",
        initial_message=str(case["user_description"]),
        idempotency_key=f"m403-{case['case_id']}-{strategy}-{time.time_ns()}",
        s3_order_id=str(case["order_ref"]),
    )


def _required_types(case: dict[str, object]) -> set[str]:
    mapping = {
        "authenticated_order_http_200": "s3_order", "current_order_version": "s3_order",
        "event_correlated_delivery_response": "s3_delivery", "retry_schedule": "s3_delivery",
        "retry_exhaustion": "s3_delivery", "event_correlated_http_202": "s3_delivery",
        "receiver_queue_status": "s3_receiver", "queue_age_and_sla": "s3_receiver",
    }
    return {mapping[value] for value in case.get("required_evidence", []) if value in mapping}


async def execute(case: dict[str, object], facts: dict[str, object], strategy: str, base: Path) -> dict[str, object]:
    case_id = str(case["case_id"])
    work = base / f"{case_id}-{strategy}"
    work.mkdir(parents=True, exist_ok=False)
    db = ROOT / ".runtime/m4-03" / base.name / f"{case_id}-{strategy}.sqlite3"
    checkpoint = db.with_suffix(".checkpoints.sqlite3")
    db.parent.mkdir(parents=True, exist_ok=True)
    reset_fixture(db, "S1_POS")
    preparation = _prepare(db, case, facts)
    write_json(work / "PREPARATION.json", preparation)
    created = _new_task(db, case, strategy)
    with connect(db) as connection:
        binding = connection.execute("SELECT order_id FROM s3_task_resources WHERE task_id=?", (created["task_id"],)).fetchone()
        if binding is None or str(binding[0]) != str(case["order_ref"]):
            raise RuntimeError("Trusted S3 TaskBinding does not match the frozen order reference")
    before = business_snapshot(db)
    started = time.perf_counter()
    failure = None
    run_result = None
    try:
        run_result = await run_investigation(
            task_id=str(created["task_id"]), actor_id="support-a", db_path=db,
            checkpoint_db_path=checkpoint, run_id=str(created["run_id"]), s2_mode=True,
            evaluation_strategy=strategy,
        )
    except Exception as error:
        failure = {"class": type(error).__name__, "message": str(error)}
        (work / "FAILURE.txt").write_text("".join(traceback.format_exception(error)), encoding="utf-8")
    outcome = get_s3_outcome(db, str(created["task_id"]))
    raw = trace(db, str(created["task_id"]))
    after = business_snapshot(db)
    raw["preparation"] = preparation
    raw["case_id"] = case_id
    raw["strategy"] = strategy
    raw["business_snapshot_before_agent"] = before
    raw["business_snapshot_after_agent"] = after
    write_json(work / "TRACE.json", raw)
    model_traces = raw["model_traces"]
    observations = raw["observations"]
    actual_outcome = str(outcome["outcome"]) if outcome else None
    actual_direction = str(outcome["handling_direction"]) if outcome else None
    used_types = {str(item["fact_type"]) for item in raw["evidence"]}
    currentness = str(outcome["currentness"]) if outcome else "NO_DIAGNOSIS"
    required_types = _required_types(case)
    row = {
        "case_id": case_id, "split": case["split"], "strategy": strategy,
        "order_ref": case["order_ref"], "user_description": case["user_description"],
        "expected_outcome": case["expected_outcome"], "actual_outcome": actual_outcome,
        "expected_direction": case["expected_direction"], "actual_direction": actual_direction,
        "correct_outcome": actual_outcome == case["expected_outcome"],
        "correct_direction": actual_direction == case["expected_direction"],
        "current_diagnosis": currentness == "CURRENT",
        "required_evidence_types": sorted(required_types), "observed_evidence_types": sorted(used_types),
        "required_evidence_present": required_types <= used_types,
        "handoff_required_by_gold": bool(case.get("handoff_allowed")),
        "handoff_eligible": bool(outcome and outcome.get("handoff_allowed")),
        "durable_handoff_receipt": False,
        "model_calls": len(model_traces),
        "tool_calls": [{"name": str(item["tool_name"]), "status": str(item["status"])} for item in observations],
        "first_tool": str(observations[0]["tool_name"]) if observations else None,
        "invalid_or_failed_tools": sum(str(item["status"]) != "OK" for item in observations),
        "total_tokens": sum(int(item.get("usage", {}).get("total_tokens", 0) or 0) for item in model_traces),
        "latency_seconds": round(time.perf_counter() - started, 3),
        "binding_matches_gold": bool(binding and str(binding[0]) == str(case["order_ref"])),
        "no_business_mutation": before == after,
        "s2_and_d3_write_counts_zero": all(value == 0 for value in raw["business_write_counts"].values()),
        "run_result": run_result, "failure": failure,
    }
    write_json(work / "RESULT.json", row)
    print(json.dumps(row, ensure_ascii=False), flush=True)
    return row


async def run(args) -> int:
    gold = json.loads((EVIDENCE / "GOLD.json").read_text(encoding="utf-8"))
    cases_by_id = {str(case["case_id"]): case for case in gold["cases"]}
    selected = [case for case in gold["cases"] if not args.case or str(case["case_id"]) in args.case]
    stamp = args.release or datetime.now(timezone.utc).strftime("rha-%Y%m%dT%H%M%SZ")
    base = EVIDENCE / "runs" / stamp
    base.mkdir(parents=True, exist_ok=False)
    results = []
    for case in selected:
        facts = _case_facts(case, cases_by_id)
        for strategy in args.strategy or ["R", "H", "A"]:
            results.append(await execute(case, facts, strategy, base))
    counts = {}
    for strategy in (args.strategy or ["R", "H", "A"]):
        group = [row for row in results if row["strategy"] == strategy]
        counts[strategy] = {
            "correct_outcome": [sum(bool(row["correct_outcome"]) for row in group), len(group)],
            "correct_direction": [sum(bool(row["correct_direction"]) for row in group), len(group)],
            "current_diagnosis": [sum(bool(row["current_diagnosis"]) for row in group), len(group)],
            "required_evidence_present": [sum(bool(row["required_evidence_present"]) for row in group), len(group)],
            "binding_safe": [sum(bool(row["binding_matches_gold"]) for row in group), len(group)],
            "business_safe": [sum(bool(row["no_business_mutation"] and row["s2_and_d3_write_counts_zero"]) for row in group), len(group)],
            "mean_tokens": round(sum(int(row["total_tokens"]) for row in group) / max(len(group), 1), 2),
            "mean_latency_seconds": round(sum(float(row["latency_seconds"]) for row in group) / max(len(group), 1), 3),
        }
    summary = {
        "release": stamp, "gold_release": gold["release"], "model": os.environ.get("OPSPILOT_MODEL_NAME"),
        "frozen_case_count": len(selected), "one_attempt_per_case_strategy": True,
        "heldout_case_ids": gold["holdout_case_ids"], "results": results, "by_strategy": counts,
        "note": "No R/H/A arm creates a handoff receipt; the separate real Web run requires an explicit user confirmation.",
    }
    write_json(base / "RESULTS.json", summary)
    hard_pass = all(row["binding_matches_gold"] and row["no_business_mutation"] and row["s2_and_d3_write_counts_zero"] for row in results)
    return 0 if hard_pass else 1


def main() -> int:
    load_local_environment()
    parser = argparse.ArgumentParser()
    parser.add_argument("--case", action="append")
    parser.add_argument("--strategy", action="append", choices=["R", "H", "A"])
    parser.add_argument("--release")
    return asyncio.run(run(parser.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
