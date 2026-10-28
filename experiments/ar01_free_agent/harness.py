"""Small comparison runner and isolated fixture preparation; not a product Runtime."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
import shutil
import sys
import time

from mcp import Client, StdioServerParameters
from langchain_core.messages import messages_to_dict

from opspilot.config import ROOT
from opspilot.domain.database import connect, reset_fixture
from opspilot.domain.d2 import canonical_json, digest_json, list_model_traces, list_observations, attempt_counts
from opspilot.domain.s3 import prepare_s3_fixture
from opspilot.domain.s3_history import prepare_transport_history_fixture
from opspilot.domain.task_control import create_session, create_task_with_initial_run, trusted_identity, claim_task_run
from opspilot.investigator import _mcp_child_environment
from opspilot.s3_investigation import S3Nodes, s3_catalog
from opspilot.s3_delivery import parse_response, supported_response, factual_partial
from experiments.ar01_free_agent.agent import Candidate, Trace, Limits, sanitize
from experiments.ar01_free_agent.simulation import LocalModel

FACT_TABLES = ("s3_orders","s3_deliveries","s3_receivers","s3_transport_attempts",
    "principals","integrations","auth_policies","route_scope_policies","principal_scope_grants")
PROTECTED = FACT_TABLES + ("task_controls","task_bindings","d3_plans","d3_approvals",
    "d3_action_intents","d3_action_ledgers","s3_diagnoses","s3_handoff_queue_entries",
    "s3_handoff_receipts","domain_outbox")


def snapshot(db, tables):
    with connect(db) as c:
        return {table:[dict(r) for r in c.execute(f"SELECT * FROM {table} ORDER BY rowid")] for table in tables}


def prepare_seed(db, setup):
    reset_fixture(db,"S1_POS")
    if "history" in setup:
        prepared = prepare_transport_history_fixture(db, order_id="ar01-order", attempts=setup["history"], receiver_status=setup["receiver"])
    else:
        prepared = prepare_s3_fixture(db, setup["state"], order_id="ar01-order", contract_version=2)
    if setup.get("outside_event"):
        prepare_transport_history_fixture(db, tenant_id="tenant-b",order_id="ar01-outside-order",
            attempts=[{"event_id":setup["outside_event"],"http_status":202}], receiver_status="PROCESSED")
    return prepared


def new_task(db, question):
    identity = trusted_identity(db,"support-a")
    session = create_session(db,identity)
    task = create_task_with_initial_run(db,identity,session_id=session["session_id"],
        service_id="orders-async-demo",integration_id="async-integration-a",ticket_id="AR01-LOCAL",
        initial_message=question,idempotency_key="ar01-initial",s3_order_id="ar01-order")
    claim_task_run(db,identity,task["run_id"])
    return task


def mcp_params(db, task):
    return StdioServerParameters(command=sys.executable,
        args=["-m","opspilot.mcp_server","--db",str(db),"--binding-id",str(task["task_id"])],
        env=_mcp_child_environment(Path(db)),cwd=str(ROOT))


class AModelTrace:
    def __init__(self,model,trace,limits):
        self.model,self.trace,self.limits = model,trace,limits
    def bind_tools(self,tools,**kwargs):
        return AModelTrace(self.model.bind_tools(tools,**kwargs),self.trace,self.limits)
    async def ainvoke(self,messages):
        self.trace.emit("model_request", messages=messages_to_dict(messages))
        response = await asyncio.wait_for(self.model.ainvoke(messages),self.limits.model_seconds)
        self.trace.emit("model_response",content=response.content,tool_calls=response.tool_calls,usage=response.usage_metadata)
        return response


class AClientTrace:
    def __init__(self,client,trace): self.client,self.trace=client,trace
    async def call_tool(self,name,args):
        self.trace.emit("tool_request",name=name,arguments=args)
        result=await self.client.call_tool(name,args)
        self.trace.emit("tool_result",name=name,is_error=result.is_error,
            result=result.structured_content,content=[b.text for b in result.content if hasattr(b,"text")])
        return result


async def run_a(db, task, client, specs, model, trace, *, model_id="ar01-deterministic"):
    limits = Limits()
    node=S3Nodes(db,task["task_id"],task["run_id"],AModelTrace(model,trace,limits),
        model_id,AClientTrace(client,trace),specs,strategy="A",memory_enabled=False)
    state={"evidence_ids":[],"tool_observations":[],"diagnosis_draft":{}}
    async def drive():
        # Invoke the existing policy methods without rewriting prompt/route logic.
        while True:
            state.update(await node.investigate(state))
            if state.get("pending_call_refs") or state.get("policy_tool_call"):
                state.update(await node.execute(state))
            state.update(await node.gate(state))
            if node.next_step(state)=="report": break
        return state
    reason="MODEL_DELIVERY"
    try:
        await asyncio.wait_for(drive(),limits.total_seconds)
    except Exception as error:
        reason=type(error).__name__
    response=state.get("diagnosis_draft",{}).get("s3_response",{}).get("response")
    _,meta=node.prompt(state)
    with connect(db) as c:
        from opspilot.domain.s3 import current_s3_evidence
        evidence,_=current_s3_evidence(c,task["task_id"],state["evidence_ids"],run_id=task["run_id"])
    from opspilot.domain.investigation_context import load_investigation_context
    inputs=load_investigation_context(db,task["task_id"],task["run_id"])["inputs"]
    if not supported_response(response,evidence,inputs):
        reason=state.get("diagnosis_draft",{}).get("s3_budget_reason") or state.get("diagnosis_draft",{}).get("s3_error") or reason
        text,_=factual_partial(evidence,meta["selected_knowledge"],inputs,reason)
        response={"result_state":"PARTIAL","answer":text,"delivery_mode":"DETERMINISTIC_FALLBACK","stop_reason":reason}
    response={**response,
        "stop_reason":response.get("stop_reason") or ("MODEL_CLARIFY" if response.get("action")=="clarify" else "MODEL_ANSWER"),
        "delivery_mode":response.get("delivery_mode","MODEL"),
        "authority":"EXPERIMENT_ONLY_NO_BUSINESS_RECEIPT"}
    trace.emit("final",result=response)
    return response


async def run_pair(case, output, *, model_factory=None, model_id="ar01-deterministic",trace_factory=None,group_observer=None):
    output.mkdir(parents=True,exist_ok=False)
    seed=output/"seed.sqlite3"
    prepared=prepare_seed(seed,case["setup"])
    initial=digest_json(snapshot(seed,FACT_TABLES))
    (output/"preparation.json").write_text(canonical_json(sanitize(prepared)),encoding="utf-8")
    results=[]
    for group in ("A","B"):
        db=output/f"{group}.sqlite3"
        shutil.copy2(seed,db)
        assert digest_json(snapshot(db,FACT_TABLES)) == initial
        task=new_task(db,case["question"])
        before=snapshot(db,PROTECTED)
        trace=trace_factory(output,group) if trace_factory else Trace()
        trace.emit("initial_state",group=group,task_id=task["task_id"],run_id=task["run_id"],business_digest=initial)
        model=None
        start=time.monotonic()
        try:
            async with Client(mcp_params(db,task)) as client:
                listed=await client.list_tools()
                catalog,specs=s3_catalog(listed.tools)
                trace.emit("tools_list",group=group,tools=catalog,model_specs=specs)
                model=(model_factory(group,{**task,"case_id":f"{case['id']}/{case['variant']}"},specs,trace)
                       if model_factory else LocalModel())
                if group=="A": result=await run_a(db,task,client,specs,model,trace,model_id=model_id)
                else: result=(await Candidate(db,task["task_id"],task["run_id"],client,specs,
                    model_id=model_id,trace=trace,output_limit=getattr(getattr(model,"config",None),"max_tokens",512)).run(model,case["question"]))["result"]
        except BaseException as error:
            trace.emit("group_failure",error_class=type(error).__name__,reason=str(error))
            with (output/f"{group}.trace.jsonl").open("x",encoding="utf-8") as f:
                for row in trace.rows: f.write(canonical_json(row)+"\n")
            raise
        finally:
            if model is not None and hasattr(model,"aclose"):
                await model.aclose()
        after=snapshot(db,PROTECTED)
        same=before==after
        if not same: raise AssertionError("AR01_PROTECTED_BUSINESS_STATE_CHANGED")
        outbound=digest_json(sorted(model.bound_schemas,key=lambda s:s["function"]["name"]))
        assert outbound==digest_json(sorted(specs,key=lambda s:s["function"]["name"])), "ACTUAL_MODEL_TOOL_SCHEMA_MISMATCH"
        traces=list_model_traces(db,task["task_id"])
        observations=list_observations(db,task["task_id"])
        trace.emit("ledger",task_id=task["task_id"],run_id=task["run_id"],model_traces=traces,observations=observations)
        with (output/f"{group}.trace.jsonl").open("w",encoding="utf-8") as f:
            for row in trace.rows: f.write(canonical_json(row)+"\n")
        provider_rows=[r for r in trace.rows if r["event"]=="provider_http_response"]
        results.append({"group":group,"task_id":task["task_id"],"run_id":task["run_id"],
            "initial_business_digest":initial,"tool_schema_digest":digest_json(sorted(specs,key=lambda s:s["function"]["name"])),
            "actual_outbound_tool_schema_digest":outbound,
            "attempt_counts":attempt_counts(db,task["task_id"]),"model_dispatches":len(model.requests),
            "tool_names":[o["tool_name"] for o in observations],"result":result,
            "business_state_unchanged":same,"elapsed_seconds":time.monotonic()-start,
            "provider_tokens":[r.get("body",{}).get("usage") for r in provider_rows] or None,
            "provider_cost_usd":None if model_factory else 0,
            "evidence_level":getattr(model,"runtime",{}).get("evidence_level","DETERMINISTIC_MODEL_REAL_LOCAL_MCP_HTTP")})
        # Persist before enforcing the batch protocol gate: partial/failed A must
        # not disappear when B or later cases are deliberately not executed.
        (output/f"{group}.result.json").write_text(json.dumps(results[-1],ensure_ascii=False,indent=2),encoding="utf-8")
        if hasattr(model,"assert_healthy"):
            model.assert_healthy()
        if group_observer:
            group_observer(results[-1])
    assert results[0]["tool_schema_digest"]==results[1]["tool_schema_digest"]
    return {"id":case["id"],"variant":case["variant"],"groups":results,"conditions_ready":True}


async def suite(output):
    output.mkdir(parents=True,exist_ok=False)
    cases=json.loads((ROOT/"docs/evidence/ar-01/CASES.json").read_text(encoding="utf-8"))["cases"]
    results=[]
    for case in cases:
        pair=await run_pair(case,output/f"{case['id']}-{case['variant']}")
        pair["local_gold_checks"] = assess(case,pair)
        results.append(pair)
    passed=all(all(r["local_gold_checks"].values()) for r in results)
    value={"status":"LOCAL_DETERMINISTIC_VALIDATED" if passed else "LOCAL_TEST_FAILURE","real_model_effect":"NOT_RUN",
        "paid_provider_calls":0,"results":results}
    (output/"local-results.json").write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding="utf-8")
    return value


def assess(case,pair):
    """Offline local rubric only; none of this is visible to either Agent."""
    checks={"equivalent_conditions":pair["conditions_ready"],"protected_state":all(g["business_state_unchanged"] for g in pair["groups"])}
    for g in pair["groups"]:
        result=g["result"]
        valid=bool(result["answer"]) and result.get("delivery_mode")!="DETERMINISTIC_FALLBACK"
        if case["id"]=="AR01-01": valid &= g["attempt_counts"]["MCP"]==0
        elif case["id"]=="AR01-02": valid &= "PROCESSING" in result["answer"]
        elif case["id"]=="AR01-03":
            valid &= result.get("processing_claim")==("QUEUED" if case["variant"]=="acknowledged" else "UNKNOWN")
            if case["variant"]=="failed": valid &= "503" in result["answer"]
        elif case["id"]=="AR01-04": valid &= result.get("processing_claim")==("PROCESSED" if case["variant"]=="same-event" else "UNKNOWN") and result.get("target_event_id")=="event-e1"
        elif case["id"]=="AR01-05": valid &= result.get("processing_claim")=="QUEUED" and "search_callback_knowledge" in g["tool_names"] and "receiver-ack-contract" in result["answer"]
        elif case["id"]=="AR01-06": valid &= result["result_state"]=="PARTIAL" and "ar01-outside-order" not in result["answer"] and "get_order_status" in g["tool_names"]
        checks[g["group"]+"_deterministic_delivery"] = bool(valid)
    return checks
