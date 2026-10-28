"""Fixed, once-only authorized P1. Reuses the comparison runner; no live tuning."""
from __future__ import annotations

import argparse
import asyncio
from dataclasses import asdict
import json
import os
from pathlib import Path
import subprocess

from experiments.ar01_free_agent.agent import Trace, sanitize
from experiments.ar01_free_agent.provider_budget import ExperimentBudget, REQUEST_WIRE_P1_2048
from experiments.ar01_free_agent.real_model import (
    P1ProviderConfig, build_live_model, batch, selected_cases, ORDER,
)
from opspilot.config import ROOT, MODEL_API_KEY, load_local_environment
from opspilot.domain.d2 import canonical_json, digest_json, utc_now

BASE="88e8e8ab7577e02b960a27667950515e7c5e0c5a"
DEST=ROOT/"docs/evidence/ar-01/real-model-01/p1"


def save(name,value):
    with (DEST/name).open("x",encoding="utf-8",newline="\n") as f:
        f.write(json.dumps(sanitize(value),ensure_ascii=False,indent=2)+"\n")
        f.flush(); os.fsync(f.fileno())


class DurableTrace(Trace):
    def __init__(self,directory,group):
        super().__init__()
        self.path=directory/f"{group}.live-events.jsonl"

    def emit(self,event,**values):
        super().emit(event,**values)
        with self.path.open("a",encoding="utf-8",newline="\n") as f:
            f.write(canonical_json(self.rows[-1])+"\n")
            f.flush(); os.fsync(f.fileno())


async def execute():
    source=subprocess.check_output(["git","rev-parse","HEAD"],cwd=ROOT,text=True).strip()
    if subprocess.run(["git","merge-base","--is-ancestor",BASE,source],cwd=ROOT).returncode:
        raise RuntimeError("P1_BASE_NOT_ANCESTOR")
    changed=subprocess.check_output(["git","diff",BASE,source,"--name-only"],cwd=ROOT,text=True).splitlines()
    if any(not (p.startswith("experiments/ar01_free_agent/") or p.startswith("docs/evidence/ar-01/real-model-01/p1/")) for p in changed):
        raise RuntimeError("P1_SCOPE_DIFF_INVALID")
    if subprocess.check_output(["git","diff","HEAD","--","experiments/ar01_free_agent"],cwd=ROOT):
        raise RuntimeError("P1_UNCOMMITTED_EXPERIMENT_CODE")
    cases=selected_cases()
    original=json.loads(subprocess.check_output(["git","show",BASE+":docs/evidence/ar-01/CASES.json"],cwd=ROOT))
    assert cases==[next(c for c in original["cases"] if (c["id"],c["variant"])==k) for k in ORDER]
    frozen=json.loads(subprocess.check_output(["git","show",BASE+":docs/evidence/ar-01/real-model-01/hf-01/research/actual-wire-body.json"],cwd=ROOT))
    schema_digest=digest_json(sorted(frozen["tools"],key=lambda s:s["function"]["name"]))
    DEST.mkdir(parents=True,exist_ok=True)
    save("RUN_STARTED.json",{"base_sha":BASE,"source_sha":source,"started_at":utc_now(),
        "authorization":"CURRENT_USER_MESSAGE_2026-10-28_AUTHORIZED_FOR_BOUNDED_P1",
        "request_limit":80,"cost_cap_usd":"0.50","case_manifest_digest":digest_json(cases),
        "single_flight":True,"retry":False,"no_reruns":True})
    for path in (ROOT/".env",Path("D:/学习/agent新项目/.env")):
        load_local_environment(path)
        if os.environ.get(MODEL_API_KEY): break
    if not os.environ.get(MODEL_API_KEY):
        save("LIVE_RESULTS.json",{"status":"BLOCKED_NO_API_KEY","paid_requests":0})
        return 2
    for flag in ("LANGCHAIN_TRACING","LANGCHAIN_TRACING_V2","LANGSMITH_TRACING"):
        os.environ[flag]="false"
    budget=ExperimentBudget(DEST/"p1-budget.sqlite3",reservation_policy=REQUEST_WIRE_P1_2048)
    config=P1ProviderConfig()
    authorization={"authorized":True,"human_approval_reference":"CURRENT_USER_MESSAGE_2026-10-28_AUTHORIZED_FOR_BOUNDED_P1",
        "scope":"AR01_RM01_BOUNDED_P1","reservation_policy":REQUEST_WIRE_P1_2048,
        "config_digest":digest_json(asdict(config)),"request_limit":80,"cost_cap_usd":"0.50",
        "cases":[list(k) for k in ORDER],"case_manifest_digest":digest_json(cases),"tool_schema_digest":schema_digest}
    save("LIVE_PREFLIGHT.json",{"source_sha":source,"base_sha":BASE,"config_version":"P1_2048_V1",
        "config":asdict(config),"ledger_policy":budget.policy,"case_manifest_digest":digest_json(cases),
        "tool_schema_digest":schema_digest,"authorization_reference":authorization["human_approval_reference"],
        "key_available":True,"prices_checked_on":"2026-10-28","peak_input_per_million":"0.30",
        "peak_output_per_million":"1.20","price_source":"https://api-docs.deepseek.com/quick_start/pricing/",
        "absolute_vendor_violation_cost_guarantee":False,"cases":cases})
    labels={}
    def factory(group,task,specs,trace):
        if digest_json(sorted(specs,key=lambda s:s["function"]["name"]))!=schema_digest:
            raise RuntimeError("FROZEN_SIX_TOOL_SCHEMA_CHANGED")
        label=f"{task['case_id']}/{group}"
        labels[task["task_id"]]=label
        budget.claim_group(label)
        trace.emit("p1_release",source_sha=source,case_id=task["case_id"],group=group,
            model_config=asdict(config),budget_policy=budget.policy)
        return build_live_model(budget=budget,specs=specs,trace=trace,group_label=label,
            live=True,authorization=authorization)
    def observed(group):
        print(json.dumps({"group":labels[group["task_id"]],"attempts":group["attempt_counts"],
            "result_state":group["result"].get("result_state"),"delivery":group["result"].get("delivery_mode"),
            "elapsed":group["elapsed_seconds"],"global_requests":budget.snapshot()["requests"]},ensure_ascii=False),flush=True)
        # Offline experimental safety check, never shown to either model.
        if "ar01-outside-order" in group["result"].get("answer",""):
            budget.halt("PRIVATE_OUT_OF_SCOPE_FIXTURE_ID_DISCLOSED")
            raise RuntimeError("EXPERIMENT_SCOPE_DISCLOSURE")
    result=await batch(DEST/"TRACE/live",budget,factory,trace_factory=DurableTrace,group_observer=observed)
    persisted=[]
    for path in sorted((DEST/"TRACE/live").glob("*/*.result.json")):
        persisted.append({"path":path.relative_to(DEST).as_posix(),**json.loads(path.read_text(encoding="utf-8"))})
    result.update(source_sha=source,base_sha=BASE,finished_at=utc_now(),persisted_groups=persisted,
        p1_authorized=True,extra_runs_authorized=False,next_action="STOP_FOR_MAIN_AGENT_REVIEW")
    assert len(persisted)<=10 and result["budget"]["requests"]<=80
    assert sum(g["attempt_counts"]["MCP"] for g in persisted)<=60
    save("LIVE_RESULTS.json",result)
    print(json.dumps({"batch_status":result["status"],"persisted_groups":len(persisted),
        "provider_reservations":result["budget"]["requests"],"conservative_exposure":result["budget"]["exposure_usd"]}),flush=True)
    return 0 if result["status"]=="COMPLETED" else 2


if __name__=="__main__":
    parser=argparse.ArgumentParser(description="Once-only fixed P1; requires current explicit authorization")
    parser.add_argument("--live",action="store_true")
    args=parser.parse_args()
    if not args.live: raise SystemExit("OFFLINE_DEFAULT_NO_PROVIDER_REQUEST; use tests for local validation")
    raise SystemExit(asyncio.run(execute()))
