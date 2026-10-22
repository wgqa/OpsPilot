"""Fresh S3 real Provider/MCP/HTTP paired evaluation. Never reads Gold at runtime."""
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
from opspilot.domain.d2 import list_model_traces, list_observations, list_evidence
from opspilot.domain.s3 import prepare_s3_fixture, get_s3_outcome
from opspilot.domain.task_control import create_session, create_task_with_initial_run, trusted_identity
from opspilot.investigator import run_investigation

EVIDENCE = ROOT / "docs/evidence/vnext/m4-02"


def write_json(path, value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2,default=str),encoding="utf-8")


def task(db, message, key):
    identity = trusted_identity(db,"support-a")
    session = create_session(db,identity)
    return create_task_with_initial_run(db,identity,session_id=session["session_id"],service_id="orders-async-demo",
                                       integration_id="async-integration-a",ticket_id="S3-LOCAL",initial_message=message,idempotency_key=key)


def business_snapshot(db):
    # Exclude credentials/secrets, audit reads, task progress and approved asset lifecycle writes.
    with connect(db) as c:
        return {name:[dict(row) for row in c.execute(f"SELECT * FROM {name} ORDER BY rowid")]
                for name in ("integrations","principals","auth_policies","route_scope_policies","principal_scope_grants",
                             "orders","s3_orders","s3_deliveries","s3_receivers","tickets","d3_ticket_resolution_entries")}


def trace(db, task_id):
    def rows(table):
        with connect(db) as c:
            return [dict(x) for x in c.execute(f"SELECT * FROM {table} WHERE task_id=? ORDER BY rowid",(task_id,))]
    with connect(db) as c:
        http = [dict(x) for x in c.execute("SELECT * FROM s3_http_observations")]
    return {"task_id":task_id,"evidence":list_evidence(db,task_id),"observations":list_observations(db,task_id),
            "model_traces":list_model_traces(db,task_id),"attempts":rows("d2_attempts"),"contexts":rows("d5_context_provenance"),
            "provider_request_contexts":rows("s3_model_contexts"),"diagnoses":rows("s3_diagnoses"),"runs":rows("task_runs"),
            "controls":rows("task_controls"),"outbox":rows("domain_outbox"),"http":http,
            "business_write_counts":{name:len(rows(name)) for name in ("d3_plans","d3_action_intents","d3_action_ledgers","s2_handoff_receipts")}}


async def execute_case(case, strategy, base):
    directory = base / f"{case['id']}-{strategy}"
    directory.mkdir(parents=True,exist_ok=False)
    db = ROOT / ".runtime/m4-02" / base.name / f"{case['id']}-{strategy}.sqlite3"
    db.parent.mkdir(parents=True,exist_ok=True)
    reset_fixture(db,"S1_POS")
    prep = prepare_s3_fixture(db,case["state"])
    write_json(directory/"PREPARATION.json",prep)
    created = task(db,case["input"],f"{case['id']}-{strategy}")
    before = business_snapshot(db)
    started = time.perf_counter()
    failure = None
    try:
        await run_investigation(task_id=created["task_id"],actor_id="support-a",db_path=db,
                               checkpoint_db_path=db.with_suffix(".checkpoints.sqlite3"),run_id=created["run_id"],
                               s2_mode=True,evaluation_strategy=strategy)
    except Exception as error:
        failure = {"class":type(error).__name__,"message":str(error)}
        (directory / "FAILURE.txt").write_text("".join(traceback.format_exception(error)),encoding="utf-8")
    outcome = get_s3_outcome(db,created["task_id"])
    raw = trace(db,created["task_id"])
    after = business_snapshot(db)
    raw["business_snapshot_before"] = before
    raw["business_snapshot_after"] = after
    write_json(directory/"TRACE.json",raw)
    traces = raw["model_traces"]
    result = {"case_id":case["id"],"state":case["state"],"strategy":strategy,"input":case["input"],
              "task_id":created["task_id"],"run_id":created["run_id"],"expected":case["outcome"],
              "actual":outcome["outcome"] if outcome else None,"correct":bool(outcome and outcome["outcome"] == case["outcome"]),
              "actual_recovery":"NOT_APPLICABLE","control_safe":before == after and all(n == 0 for n in raw["business_write_counts"].values()),
              "model_calls":len(traces),"tools":[o["tool_name"] for o in raw["observations"]],
              "mcp_calls":sum(a["kind"] == "MCP" for a in raw["attempts"]),
              "invalid_calls":sum(o["status"] != "OK" for o in raw["observations"]),
              "total_tokens":sum(int(t["usage"].get("total_tokens",0)) for t in traces),
              "latency_seconds":round(time.perf_counter()-started,3),"failure":failure}
    write_json(directory/"RESULT.json",result)
    print(json.dumps(result,ensure_ascii=False),flush=True)
    return result


async def main_async(args):
    gold = json.loads((EVIDENCE/"GOLD.json").read_text(encoding="utf-8"))
    stamp = args.release or datetime.now(timezone.utc).strftime("eval-%Y%m%dT%H%M%SZ")
    base = EVIDENCE / "runs" / stamp
    base.mkdir(parents=True,exist_ok=False)
    cases = [c for c in gold["cases"] if not args.case or c["id"] in args.case]
    results = []
    for case in cases:
        for strategy in (args.strategy or gold["arms"]):
            results.append(await execute_case(case,strategy,base))
    write_json(base/"RESULTS.json",{"release":stamp,"gold_release":gold["release"],"model":os.environ.get("OPSPILOT_MODEL_NAME"),
                                  "cases":results,"correct":sum(r["correct"] for r in results),"denominator":len(results),
                                  "safe":sum(r["control_safe"] for r in results)})
    return 0 if all(r["correct"] and r["control_safe"] for r in results) else 1


def main():
    load_local_environment()
    parser = argparse.ArgumentParser()
    parser.add_argument("--case",action="append")
    parser.add_argument("--strategy",action="append",choices=["R","H","A"])
    parser.add_argument("--release")
    return asyncio.run(main_async(parser.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
