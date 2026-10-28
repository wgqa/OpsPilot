"""One authorized PROBE-01; fixed approved body, no Agent/tool loop or retries.

The immutable marker, request_limit=1 and approved source SHA prevent accidental
replay. This entry is NOT an authorization for P1 or any future invocation.
"""
from __future__ import annotations

import asyncio
from dataclasses import asdict
import hashlib
from importlib.metadata import version
import json
import os
from pathlib import Path
import subprocess
import time

from langchain_core.messages import SystemMessage, HumanMessage

from experiments.ar01_free_agent.agent import Trace, sanitize
from experiments.ar01_free_agent.provider_budget import (
    ExperimentBudget, REQUEST_WIRE_V1, usage_cost, dollars,
)
from experiments.ar01_free_agent.real_model import ProviderConfig, build_live_model, safe_response
from opspilot.config import ROOT, MODEL_API_KEY, load_local_environment
from opspilot.domain.d2 import digest_json, canonical_json, utc_now

BASE="6c61a5cc5f19800b10d10bb50e23a2dfce49f243"
WIRE_PATH="docs/evidence/ar-01/real-model-01/hf-01/research/actual-wire-body.json"
WIRE_DIGEST="e9f088776d73e414238fc393c9d06659fa029280c064bac4c2d2361955521f8f"
DEST=ROOT/"docs/evidence/ar-01/real-model-01/probe-01"


def write(name,value):
    with (DEST/name).open("x",encoding="utf-8",newline="\n") as handle:
        handle.write(json.dumps(sanitize(value),ensure_ascii=False,indent=2)+"\n")
        handle.flush()
        os.fsync(handle.fileno())


class DurableTrace(Trace):
    def __init__(self):
        super().__init__()
        self.handle=(DEST/"TRACE.jsonl").open("x",encoding="utf-8",newline="\n")

    def emit(self,event,**values):
        super().emit(event,**values)
        self.handle.write(canonical_json(self.rows[-1])+"\n")
        self.handle.flush()
        os.fsync(self.handle.fileno())


async def execute():
    head=subprocess.check_output(["git","rev-parse","HEAD"],cwd=ROOT,text=True).strip()
    if head!=BASE: raise RuntimeError("APPROVED_HEAD_MISMATCH_NO_REQUEST")
    if subprocess.check_output(["git","diff","HEAD","--","experiments/ar01_free_agent/real_model.py",
        "experiments/ar01_free_agent/provider_budget.py"],cwd=ROOT):
        raise RuntimeError("APPROVED_ADAPTER_MODIFIED_NO_REQUEST")
    frozen=subprocess.check_output(["git","show",BASE+":"+WIRE_PATH],cwd=ROOT)
    body=json.loads(frozen)
    if digest_json(body)!=WIRE_DIGEST or json.loads((ROOT/WIRE_PATH).read_text(encoding="utf-8"))!=body:
        raise RuntimeError("FROZEN_REQUEST_DIGEST_MISMATCH_NO_REQUEST")
    assert [m["role"] for m in body["messages"]]==["system","user"]
    assert len(body["tools"])==6
    DEST.mkdir(parents=True,exist_ok=True)
    write("RUN_STARTED.json",{"probe":"AR-01-RM-01-PROBE-01","base":BASE,"started_at":utc_now(),
        "wire_digest":WIRE_DIGEST,"authorization_reference":"CURRENT_USER_MESSAGE_2026-10-28_PROBE-01",
        "one_request_only":True,"automatic_retry":False,"mcp_execution_authorized":False})
    trace=DurableTrace()
    budget=ExperimentBudget(DEST/"request-budget.sqlite3",reservation_policy=REQUEST_WIRE_V1,request_limit=1)
    model=None
    answer=None
    failure=None
    began=time.monotonic()
    key_origin="process_environment" if os.environ.get(MODEL_API_KEY) else None
    try:
        if not key_origin:
            for env_path in (ROOT/".env",Path("D:/学习/agent新项目/.env")):
                load_local_environment(env_path)
                if os.environ.get(MODEL_API_KEY):
                    key_origin="isolated_repo_env" if env_path==ROOT/".env" else "primary_repo_env_readonly"
                    break
        if not os.environ.get(MODEL_API_KEY): raise RuntimeError("LOCAL_API_KEY_MISSING_NO_REQUEST")
        # This probe authorizes only DeepSeek, not any environment-based tracing.
        for name in ("LANGCHAIN_TRACING","LANGCHAIN_TRACING_V2","LANGSMITH_TRACING"):
            os.environ[name]="false"
        config=ProviderConfig()
        authorization={"authorized":True,"human_approval_reference":"CURRENT_USER_MESSAGE_2026-10-28_AUTHORIZED_FOR_ONE_PROBE",
            "scope":"ONE_REQUEST_PROTOCOL_PROBE","reservation_policy":REQUEST_WIRE_V1,
            "config_digest":digest_json(asdict(config)),"request_limit":1,"cost_cap_usd":"0.50","wire_digest":WIRE_DIGEST}
        preflight={"source_sha":head,"wire_digest":WIRE_DIGEST,"wire_blob":subprocess.check_output(
            ["git","rev-parse",BASE+":"+WIRE_PATH],cwd=ROOT,text=True).strip(),
            "key_available":True,"key_origin":key_origin,"config":asdict(config),"budget":budget.preflight(body),
            "packages":{name:version(name) for name in ("langchain","langchain-core","langchain-openai","langgraph","openai","httpx")},
            "price_checked_on":"2026-10-28","peak_input_per_million":"0.30","peak_output_per_million":"1.20",
            "price_source":"https://api-docs.deepseek.com/quick_start/pricing/",
            "absolute_vendor_violation_cost_guarantee":False,"p1_authorized":False}
        write("PREFLIGHT.json",preflight)
        write("REQUEST_BODY.json",body)
        if not preflight["budget"]["ready"]: raise RuntimeError("BUDGET_PREFLIGHT_REJECTED_NO_REQUEST")
        model=build_live_model(budget=budget,specs=body["tools"],trace=trace,group_label="AR-01-RM-01-PROBE-01",
            live=True,authorization=authorization,probe_wire=body)

        async def audit_request(request):
            write("HTTP_REQUEST.json",{"observed_at":utc_now(),"method":request.method,"url":str(request.url),
                "headers":{"content-type":request.headers.get("content-type"),"authorization":"[REDACTED]"},
                "body":json.loads(request.content),"wire_bytes":len(request.content),
                "raw_body_sha256":hashlib.sha256(request.content).hexdigest(),
                "semantic_digest":digest_json(json.loads(request.content)),"stage":"PRE_TRANSPORT_ATTEMPT"})

        async def audit_response(response):
            await response.aread()
            try: raw=response.json()
            except ValueError: raw={"unparseable_response_text":sanitize(response.text)}
            write("HTTP_RESPONSE.json",{"observed_at":utc_now(),"http_status":response.status_code,
                "headers":{k:response.headers[k] for k in ("x-request-id","request-id","content-type","date") if k in response.headers},
                "body":safe_response(raw),"wire_bytes":len(response.content),
                "raw_body_sha256":hashlib.sha256(response.content).hexdigest(),
                "omitted_sensitive_fields":["authorization","cookie","reasoning_content","reasoning"]})

        model.runtime["http_async"].event_hooks["request"].append(audit_request)
        model.runtime["http_async"].event_hooks["response"].append(audit_response)
        messages=[SystemMessage(content=body["messages"][0]["content"]),HumanMessage(content=body["messages"][1]["content"])]
        # Exactly one invocation; no create_agent(), MCP client, retry or fallback.
        answer=await asyncio.wait_for(model.bind_tools(body["tools"],tool_choice="auto",parallel_tool_calls=False).ainvoke(messages),30)
        model.assert_healthy()
    except BaseException as error:
        failure={"class":type(error).__name__,"message":sanitize(str(error))}
        trace.emit("probe_stopped",failure=failure,retry=False)
    finally:
        if model is not None: await model.aclose()
        snap=budget.snapshot()
        raw=model.runtime.get("raw") if model is not None else None
        usage=raw.get("usage") if isinstance(raw,dict) else None
        estimated=None
        try:
            if usage is not None: estimated=dollars(usage_cost(usage))
        except Exception: pass
        result={"probe":"AR-01-RM-01-PROBE-01","base_sha":BASE,
            "status":"PROTOCOL_OBSERVED_OK" if answer is not None and failure is None else "STOPPED_WITH_FAILURE_OR_UNKNOWN",
            "finished_at":utc_now(),"elapsed_seconds":time.monotonic()-began,"failure":failure,
            "request_reservations":snap["requests"],"transport_attempts":sum(r["sends"] for r in snap["rows"]),
            "http_response_observed":(DEST/"HTTP_RESPONSE.json").exists(),"budget":snap,"wire_digest":WIRE_DIGEST,
            "model_returned":raw.get("model") if isinstance(raw,dict) else None,
            "system_fingerprint":raw.get("system_fingerprint") if isinstance(raw,dict) else None,
            "completion_id":raw.get("id") if isinstance(raw,dict) else None,
            "provider_request_id":model.runtime.get("request_id") if model is not None else None,
            "usage":usage,"conservative_peak_no_cache_charge_estimate_usd":estimated,
            "invoice_confirmed":False,"absolute_vendor_violation_cost_guarantee":False,
            "sdk_answer":safe_response({"content":answer.content,"tool_calls":answer.tool_calls,
                "metadata":answer.response_metadata,"usage":answer.usage_metadata}) if answer is not None else None,
            "actual_mcp_tools_executed":0,"business_writes":0,"retry_performed":False,
            "p1":"NOT_AUTHORIZED_NOT_RUN","p2":"NOT_RUN","next_action":"STOP_FOR_MAIN_AGENT_REVIEW"}
        trace.emit("probe_finished",result=result)
        write("RESULTS.json",result)
        trace.handle.close()
        print(json.dumps({k:result[k] for k in ("status","request_reservations","transport_attempts",
            "http_response_observed","model_returned","completion_id","usage","conservative_peak_no_cache_charge_estimate_usd","failure")},ensure_ascii=False))
    return 0 if failure is None else 2


if __name__=="__main__":
    raise SystemExit(asyncio.run(execute()))
