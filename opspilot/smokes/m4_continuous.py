"""Bounded, isolated real Provider/MCP/HTTP experiments, never an online Gold reader."""
from __future__ import annotations

import argparse
import asyncio
import contextvars
import hashlib
import json
import os
import threading
import time
import traceback
import uuid
from datetime import datetime, timezone
from pathlib import Path

from opspilot.config import ROOT, load_local_environment
from opspilot.domain.database import connect, reset_fixture
from opspilot.domain.d2 import digest_json, configure_s3_experiment_budget
from opspilot.domain.s3_history import prepare_transport_history_fixture
from opspilot.domain.task_control import create_session, create_task_with_initial_run, trusted_identity

EVIDENCE=ROOT/"docs/evidence/vnext/m4-continuous-vs01"
RUNTIME=ROOT/".runtime/m4-continuous-vs01"
LABEL=contextvars.ContextVar("ci_experiment",default="WEB")
ID_SEED="ci-vs01-opaque-v1-before-provider-20261025"


def write_json(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2,default=str),encoding="utf-8")


def physical(kind,value):
    return kind+"-"+hashlib.sha256((ID_SEED+":"+str(value)).encode()).hexdigest()[:12]


def render_case(case):
    """Fixture preparation sees facts; labels/expected/partition never enter model input."""
    events={item["event_id"]:physical("event",item["event_id"]) for item in case["attempts"]}
    events.setdefault(case["target_event_id"],physical("event",case["target_event_id"]))
    message=case["message"]
    for logical,opaque in events.items():
        message=message.replace(logical,opaque)
    return {"order_id":physical("order",case["order_id"]),"target_event_id":events[case["target_event_id"]],
            "message":message,"attempts":[{**item,"event_id":events[item["event_id"]]} for item in case["attempts"]],
            "receiver":case["current_receiver_status"],"contract_version":case.get("contract_version",2),
            "history_mode":case.get("history_mode","observed"),"mapping":events}


class ProviderMeter:
    """Test-only serial-process cap. Reservations survive restart; no Gateway or runtime policy."""
    def __init__(self,path):
        self.path=path
        path.parent.mkdir(parents=True,exist_ok=True)
        self.lock=threading.Lock()

    def rows(self):
        return [json.loads(line) for line in self.path.read_text(encoding="utf-8").splitlines()] if self.path.exists() else []

    def append(self,row):
        with self.path.open("a",encoding="utf-8") as handle:
            handle.write(json.dumps(row,ensure_ascii=False,default=str)+"\n")
            handle.flush()
            os.fsync(handle.fileno())

    def begin(self,model,messages,kwargs):
        # UTF8 bytes plus schema and framing is a conservative input-token reservation.
        raw=json.dumps([m.model_dump(mode="json") for m in messages],ensure_ascii=False,default=str)
        input_upper=len(raw.encode())+len(json.dumps(kwargs.get("tools",[]),ensure_ascii=False,default=str).encode())+2048
        # The real provider returned more than the SDK's nominal 512 output tokens.
        # Use its documented absolute 384K output maximum for in-flight exposure.
        output_upper=393216
        reserved=(input_upper*.30+output_upper*1.20)/1_000_000
        with self.lock:
            reservations=[row for row in self.rows() if row["event"]=="RESERVE"]
            completions={row["request_id"]:row for row in self.rows() if row["event"]=="COMPLETE"}
            exposure=0.0
            for row in reservations:
                settled=completions.get(row.get("request_id"),{})
                actual=settled.get("estimated_peak_usd")
                exposure += actual if actual is not None else max(row["reserved_usd"],(row.get("input_token_upper",0)*.30+393216*1.20)/1_000_000)
            if len(reservations)>=180 or exposure+reserved>3:
                raise RuntimeError("EXPERIMENT_PROVIDER_CAP_REACHED")
            system=str(messages[0].content)[:250] if messages else ""
            category="CLASSIFIER" if "classif" in system.lower() or "follow_up_action" in raw[:1600] else "H_NORMALIZER" if system.startswith("Interpret the untrusted") else "INVESTIGATOR_OR_CHAT"
            request_id=str(uuid.uuid4())
            self.append({"event":"RESERVE","request_id":request_id,"experiment":LABEL.get(),"category":category,
                         "at":datetime.now(timezone.utc).isoformat(),"model":str(model.model_name),
                         "prompt_digest":hashlib.sha256(raw.encode()).hexdigest(),"input_token_upper":input_upper,
                         "output_token_upper":output_upper,"reserved_usd":reserved,"accounting":"PEAK_ESTIMATE_NOT_INVOICE"})
        return request_id,time.perf_counter()

    def end(self,start,response,error=None):
        request_id,began=start
        usage=getattr(response,"usage_metadata",None) or {}
        metadata=getattr(response,"response_metadata",None) or {}
        tokens=usage or metadata.get("token_usage") or {}
        input_tokens=tokens.get("input_tokens",tokens.get("prompt_tokens"))
        output_tokens=tokens.get("output_tokens",tokens.get("completion_tokens"))
        estimated=None if input_tokens is None or output_tokens is None else (input_tokens*.30+output_tokens*1.20)/1_000_000
        self.append({"event":"COMPLETE","request_id":request_id,"experiment":LABEL.get(),"latency_seconds":time.perf_counter()-began,
                     "usage":tokens or "UNKNOWN","estimated_peak_usd":estimated,"provider_response_id":getattr(response,"id",None),
                     "tool_calls":getattr(response,"tool_calls",None),"assistant_text":getattr(response,"content",None),
                     "status":"ERROR" if error else "OK","error_class":type(error).__name__ if error else None})

    def install(self):
        from langchain_openai import ChatOpenAI
        original,stream=ChatOpenAI.ainvoke,ChatOpenAI.astream
        meter=self
        async def invoke(model,messages,*args,**kwargs):
            start=meter.begin(model,messages,kwargs)
            try:
                value=await original(model,messages,*args,**kwargs)
            except BaseException as error:
                meter.end(start,None,error)
                raise
            meter.end(start,value)
            return value
        async def astream(model,messages,*args,**kwargs):
            start=meter.begin(model,messages,kwargs)
            merged=None
            try:
                async for chunk in stream(model,messages,*args,**kwargs):
                    merged=chunk if merged is None else merged+chunk
                    yield chunk
            except BaseException as error:
                meter.end(start,merged,error)
                raise
            meter.end(start,merged)
        ChatOpenAI.ainvoke=invoke
        ChatOpenAI.astream=astream


def export_trace(db,task_id):
    with connect(db) as c:
        def rows(table):
            return [dict(row) for row in c.execute(f"SELECT * FROM {table} WHERE task_id=? ORDER BY rowid",(task_id,))]
        tables=("task_runs","task_controls","messages","d2_attempts","d2_model_traces","d2_pending_tool_calls",
                "d2_tool_observations","d2_evidence","d5_context_provenance","s3_model_contexts","s3_diagnoses",
                "s3_run_answers","c1_readonly_followup_runs","domain_outbox")
        result={table:rows(table) for table in tables}
        result["commands"]=[dict(row) for row in c.execute("SELECT * FROM commands WHERE run_id IN (SELECT run_id FROM task_runs WHERE task_id=?) OR message_id IN (SELECT message_id FROM messages WHERE task_id=?)",(task_id,task_id))]
        result["http"]=[dict(row) for row in c.execute("SELECT * FROM s3_http_observations")]
        result["transport"]=[dict(row) for row in c.execute("SELECT * FROM s3_transport_attempts")]
        result["write_counts"]={table:c.execute(f"SELECT COUNT(*) FROM {table} WHERE task_id=?",(task_id,)).fetchone()[0]
                                for table in ("d3_plans","d3_approvals","d3_action_intents","d3_action_ledgers","s3_handoff_queue_entries","s3_handoff_receipts")}
    return result


async def execute(case,strategy,profile,release,meter):
    from opspilot.investigator import run_investigation
    from opspilot.smokes.m4_02 import business_snapshot
    label=f"{case['case_id']}-{strategy}-{profile[0]}-{profile[1]}"
    directory=EVIDENCE/"runs"/release/label
    directory.mkdir(parents=True,exist_ok=False)
    runtime=RUNTIME/release/label
    runtime.mkdir(parents=True,exist_ok=False)
    db=runtime/"domain.sqlite3"
    reset_fixture(db,"S1_POS")
    physical_case=render_case(case)
    preparation=prepare_transport_history_fixture(db,order_id=physical_case["order_id"],attempts=physical_case["attempts"],
              receiver_status=physical_case["receiver"],history_mode=physical_case["history_mode"],contract_version=physical_case["contract_version"])
    write_json(directory/"PREPARATION.json",preparation)
    identity=trusted_identity(db,"support-a")
    session=create_session(db,identity)
    created=create_task_with_initial_run(db,identity,session_id=session["session_id"],service_id="orders-async-demo",integration_id="async-integration-a",
                                        ticket_id="CI-VS01-LOCAL",initial_message=physical_case["message"],idempotency_key=label,s3_order_id=physical_case["order_id"])
    if profile!=(8,6):
        configure_s3_experiment_budget(db,created["task_id"],*profile)
    before=business_snapshot(db)
    started=time.perf_counter()
    failure=None
    token=LABEL.set(label)
    try:
        await run_investigation(created["task_id"],"support-a",db_path=db,checkpoint_db_path=runtime/"checkpoints.sqlite3",
                                run_id=created["run_id"],s2_mode=True,evaluation_strategy=strategy)
    except Exception as error:
        failure={"class":type(error).__name__,"message":str(error)}
        (directory/"FAILURE.txt").write_text(traceback.format_exc(),encoding="utf-8")
    finally:
        LABEL.reset(token)
    raw=export_trace(db,created["task_id"])
    raw["business_snapshot_before"]=before
    raw["business_snapshot_after"]=business_snapshot(db)
    write_json(directory/"TRACE.json",raw)
    answer=json.loads(raw["s3_run_answers"][-1]["body_json"]) if raw["s3_run_answers"] else {}
    result={"case_id":case["case_id"],"strategy":strategy,"profile":profile,"default_profile":profile==(8,6),"task_id":created["task_id"],
            "run_id":created["run_id"],"physical_mapping":physical_case["mapping"],"target_event_id":physical_case["target_event_id"],
            "failure":failure,"elapsed_seconds":time.perf_counter()-started,"answer":answer,
            "actual_tools":[row["tool_name"] for row in raw["d2_tool_observations"]],"write_counts":raw["write_counts"],
            "run_statuses":[row["status"] for row in raw["task_runs"]],"provider_requests":[row for row in meter.rows() if row.get("experiment")==label],
            "expected_for_offline_review_only":case.get("expected"),"runtime_db":str(db),
            "criteria":{"nonempty_delivery":bool(answer.get("answer_text"," ").strip()) if answer else False,
                        "zero_business_writes":not any(raw["write_counts"].values()),
                        "business_snapshot_unchanged":before==raw["business_snapshot_after"]}}
    write_json(directory/"RESULT.json",result)
    print(json.dumps({key:result[key] for key in ("case_id","strategy","profile","failure","actual_tools","criteria")},ensure_ascii=False),flush=True)
    return result


def preregister():
    write_json(EVIDENCE/"EXPERIMENT_REGISTRATION.json",{
        "mapping_algorithm":"sha256(seed + ':' + logical_id)[:12], prefix order/event","seed":ID_SEED,
        "registered_before_paid_calls":True,"provider_cap":180,"reserved_usd_cap":3,"input_usd_per_million":.30,"output_usd_per_million":1.20,
        "rule":"logical case labels and expected values never enter prompts or MCP; only opaque business IDs and actual prepared facts",
        "primary_tasks":16,"parallel_paid_processes":1,"holdout_runs":1,"holdout_open_only_after_source_commit":True})


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--phase",choices=("register","budget","controls","holdout","serve-web"),required=True)
    parser.add_argument("--release",required=True)
    parser.add_argument("--port",type=int,default=8013)
    args=parser.parse_args()
    if args.phase=="register":
        preregister()
        return 0
    load_local_environment(Path("D:/学习/agent新项目/.env"))
    meter=ProviderMeter(EVIDENCE/"PROVIDER_LEDGER.jsonl")
    meter.install()
    if args.phase=="serve-web":
        from opspilot.web.app import create_app
        import uvicorn
        runtime=RUNTIME/args.release
        runtime.mkdir(parents=True,exist_ok=True)
        db=runtime/"domain.sqlite3"
        directory=EVIDENCE/"runs"/args.release
        directory.mkdir(parents=True,exist_ok=True)
        if not db.exists():
            reset_fixture(db,"S1_POS")
            cases=json.loads((EVIDENCE/"DEVELOPMENT_CASES.json").read_text(encoding="utf-8"))["cases"][:2]
            prepared=[]
            for case in cases:
                physical_case=render_case(case)
                prep=prepare_transport_history_fixture(db,order_id=physical_case["order_id"],attempts=physical_case["attempts"],receiver_status=physical_case["receiver"])
                prepared.append({"case_id":case["case_id"],"physical":physical_case,"http_preparation":prep})
            write_json(directory/"PREPARATION.json",prepared)
        app=create_app(db_path=db,checkpoint_db_path=runtime/"checkpoints.sqlite3",start_worker=True,
                       credentials={"support-a":"support-test-password","approver-a":"approver-test-password"},expected_origin="http://127.0.0.1:5182")
        uvicorn.run(app,host="127.0.0.1",port=args.port,log_level="info")
        return 0
    if args.phase=="holdout":
        sealed=EVIDENCE/"SEALED_P2_P3.json"
        body=sealed.read_bytes()
        expected=json.loads((EVIDENCE/"GOLD.json").read_text(encoding="utf-8"))["sealed_sha256"]
        if hashlib.sha256(body).hexdigest()!=expected:
            raise ValueError("SEALED_BYTES_CHANGED")
        selected=json.loads(body)["cases"]
        plan=[(case,"A",(8,6)) for case in selected]
    else:
        cases=json.loads((EVIDENCE/"DEVELOPMENT_CASES.json").read_text(encoding="utf-8"))["cases"]
        selected=[case for case in cases if case["pair"]=="P5"]
        plan=[(case,"A",profile) for profile in ((8,6),(12,8),(16,10)) for case in selected] if args.phase=="budget" else [(case,strategy,(8,6)) for strategy in ("R","H") for case in selected]
    async def run():
        results=[]
        for case,strategy,profile in plan:
            results.append(await execute(case,strategy,profile,args.release,meter))
            write_json(EVIDENCE/"runs"/args.release/"RESULTS.json",results)
    asyncio.run(run())
    return 0


if __name__=="__main__":
    raise SystemExit(main())
