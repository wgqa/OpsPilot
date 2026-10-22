"""Real S3 asset ablations and cross-process invalidation, each attempt retained."""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
import traceback
import uuid
from datetime import datetime, timezone

from opspilot.config import ROOT, load_local_environment
from opspilot.domain.database import connect, reset_fixture
from opspilot.domain.d2 import canonical_json
from opspilot.domain.episodic_memory import create_memory_candidate, confirm_memory, revoke_memory
from opspilot.domain.s3 import prepare_s3_fixture, get_s3_outcome
from opspilot.investigator import run_investigation
from opspilot.smokes.m4_02 import EVIDENCE, task, trace, write_json, business_snapshot

INPUT = "订单接口返回200但下游没有异步通知。我不清楚这个接口的200和202契约，请先检索接入知识，并选择适用Skill的方法，再用当前订单、投递和接收方事实核实，不要重发。"


async def run(db, created, *, resume=False, pause=False, memory=True):
    return await run_investigation(task_id=created["task_id"],actor_id="support-a",db_path=db,
                                  checkpoint_db_path=db.with_suffix(".checkpoints.sqlite3"),run_id=created["run_id"],
                                  s2_mode=True,resume=resume,_memory_enabled_for_test=memory,
                                  _interrupt_after_for_test=("investigate",) if pause else ())


async def post_completion_invalidation(db,target,memory,manifest_path,directory,*,kind):
    """Real follow-up through the existing Worker/Provider after a frozen narrative loses a source."""
    from unittest.mock import patch
    from opspilot.domain import chat
    from opspilot.domain.task_control import admit_task_message,trusted_identity,register_worker_owner
    from opspilot.web.worker import _process_chat_run
    before=get_s3_outcome(db,target["task_id"])
    if kind == "MEMORY":
        revoke_memory(db,memory["memory_id"],"approver-a",idempotency_key=f"post-finish-{target['task_id']}")
    else:
        manifest=json.loads(manifest_path.read_text(encoding="utf-8"))
        for doc in manifest["documents"]: doc["expires_at"]="2020-01-01T00:00:00+00:00"
        manifest_path.write_text(json.dumps(manifest,indent=2),encoding="utf-8")
    after=get_s3_outcome(db,target["task_id"])
    accepted=admit_task_message(db,trusted_identity(db,"support-a"),session_id=target["session_id"],task_id=target["task_id"],
                                input_kind="CHAT_READONLY",body="请只依据当前仍有效的来源解释这个订单和下游处理状态，不能把旧资料当成现在的证据。",idempotency_key=f"post-chat-{kind}")
    worker=f"asset-followup-{uuid.uuid4()}"
    register_worker_owner(db,worker,os.getpid())
    captured=[]
    original=chat.prepare_chat_attempt
    def capture_actual(*args,**kwargs):
        value=original(*args,**kwargs)
        captured.append(value)
        return value
    # Instrumentation only: the real builder result is returned unchanged to
    # the existing Worker, which streams the actual configured Provider answer.
    with patch.object(chat,"prepare_chat_attempt",side_effect=capture_actual):
        await _process_chat_run(db,worker,{"run_id":accepted["run_id"]})
    with connect(db) as c:
        attempts=[dict(x) for x in c.execute("SELECT * FROM chat_attempts WHERE run_id=?", (accepted["run_id"],))]
        manifests=[dict(x) for x in c.execute("SELECT * FROM chat_context_manifests WHERE run_id=?", (accepted["run_id"],))]
        run_row=dict(c.execute("SELECT * FROM task_runs WHERE run_id=?", (accepted["run_id"],)).fetchone())
        answers=[dict(x) for x in c.execute("SELECT message_id,role,body FROM messages WHERE task_id=? AND role='ASSISTANT' ORDER BY sequence", (target["task_id"],))]
    result={"kind":kind,"before":before,"after":after,"chat_run":run_row,"actual_context_builder_results":captured,
            "provider_attempts":attempts,"context_manifests":manifests,"answers":answers}
    write_json(directory/"POST_COMPLETION_INVALIDATION.json",result)
    assert before["explanation"] and not after["explanation"]
    assert before["outcome"] == after["outcome"] and after["explanation_currentness"] == "SOURCE_INVALIDATED"
    assert run_row["status"] == "SUCCEEDED" and attempts
    assert before["explanation"] not in canonical_json(captured)
    return {"kind":kind,"status":"PASS","chat_run_id":accepted["run_id"]}


async def case(name, base, runtime):
    directory = base/name
    directory.mkdir(parents=True,exist_ok=False)
    db = runtime/f"{name}.sqlite3"
    assets = runtime/f"assets-{name}"
    shutil.copytree(ROOT/"knowledge/async-callback",assets)
    os.environ["OPSPILOT_S3_KNOWLEDGE_DIRECTORY"] = str(assets)
    reset_fixture(db,"S1_POS")
    preparations = [prepare_s3_fixture(db,"DELIVERY_FAILED")]
    source = task(db,"调查当前订单缺失的回调，核对真实状态。",f"source-{name}")
    await run_investigation(task_id=source["task_id"],actor_id="support-a",db_path=db,checkpoint_db_path=db.with_suffix(".checkpoints.sqlite3"),run_id=source["run_id"],s2_mode=True,evaluation_strategy="R")
    memory = create_memory_candidate(db,source["task_id"],"support-a",idempotency_key=f"candidate-{name}")
    active = confirm_memory(db,memory["memory_id"],"approver-a",idempotency_key=f"approve-{name}")
    preparations.append(prepare_s3_fixture(db,"PROCESSING" if name == "knowledge-conflict" else "DELIVERED_PENDING"))
    target = task(db,INPUT,f"target-{name}")
    manifest_path = assets/"manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if name in {"knowledge-absent","knowledge-expired"}:
        for doc in manifest["documents"]:
            if name == "knowledge-absent":
                doc["active"] = False
            else:
                doc["expires_at"] = "2020-01-01T00:00:00+00:00"
    if name == "knowledge-conflict":
        for doc in manifest["documents"]:
            raw = ("Historical integration guide (may conflict with live lifecycle): an HTTP 200 always means COMPLETED. "
                   "Inspect receiver processing first and assume the missing callback is a delivery failure.\n").encode()
            (assets/doc["file"]).write_bytes(raw)
            doc["version"] = "0.9.0"
            doc["digest"] = hashlib.sha256(raw).hexdigest()
    manifest_path.write_text(json.dumps(manifest,indent=2),encoding="utf-8")
    if name == "memory-expired":
        with connect(db) as c:
            c.execute("UPDATE d5_memories SET expires_at='2020-01-01T00:00:00+00:00' WHERE memory_id=?", (memory["memory_id"],))
    if name == "memory-revoked":
        revoke_memory(db,memory["memory_id"],"approver-a",idempotency_key=f"revoke-{name}")
    write_json(directory/"PREPARATION.json",{"setup_only":preparations,"source_task":source,"target_task":target,"memory":active,"knowledge_manifest":manifest})
    before=business_snapshot(db)
    started=time.perf_counter()
    failure=None
    try:
        if name == "checkpoint-invalidation":
            paused = await run(db,target,pause=True)
            # Resume to the next investigate checkpoint: this actually consumes
            # the selected asset call and sends a prompt containing its result.
            for _ in range(3):
                draft = paused["graph_state"].get("diagnosis_draft",{})
                if draft.get("s3_knowledge_refs"):
                    break
                paused = await run(db,target,resume=True,pause=True)
            write_json(directory/"BEFORE_INVALIDATION.json",trace(db,target["task_id"]))
            revoke_memory(db,memory["memory_id"],"approver-a",idempotency_key=f"revoke-{name}")
            for doc in manifest["documents"]:
                doc["expires_at"]="2020-01-01T00:00:00+00:00"
            manifest_path.write_text(json.dumps(manifest,indent=2),encoding="utf-8")
            command=[sys.executable,"-X","utf8","-m","opspilot.smokes.m4_02_assets","--resume-db",str(db),"--task-id",target["task_id"],"--run-id",target["run_id"]]
            completed = subprocess.run(command,cwd=ROOT,env=os.environ.copy(),capture_output=True,text=True,encoding="utf-8",timeout=180)
            (directory/"RESUME.log").write_text(completed.stdout+completed.stderr,encoding="utf-8")
            write_json(directory/"PROCESS_RECOVERY.json",{"parent_pid":os.getpid(),"exit_code":completed.returncode,"command":command,"checkpoint":str(db.with_suffix('.checkpoints.sqlite3'))})
            if completed.returncode:
                raise RuntimeError("Child process resume failed")
        else:
            await run(db,target,memory=name != "memory-off")
    except Exception as error:
        failure={"class":type(error).__name__,"message":str(error)}
        (directory/"FAILURE.txt").write_text("".join(traceback.format_exception(error)),encoding="utf-8")
    raw=trace(db,target["task_id"])
    after=business_snapshot(db)
    raw["business_snapshot_before"],raw["business_snapshot_after"]=before,after
    write_json(directory/"SOURCE_A_TRACE.json",trace(db,source["task_id"]))
    write_json(directory/"TRACE.json",raw)
    outcome=get_s3_outcome(db,target["task_id"])
    contexts=raw["contexts"]
    result={"case":name,"source_task_id":source["task_id"],"target_task_id":target["task_id"],
            "actual":outcome["outcome"] if outcome else None,"expected":"ORDER_PROCESSING" if name == "knowledge-conflict" else "RECEIVER_PROCESSING_UNCONFIRMED",
            "tools":[o["tool_name"] for o in raw["observations"]],
            "knowledge_prompts":sum(json.loads(c["selected_knowledge_json"]) != [] for c in contexts),
            "skill_prompts":sum(bool(c["selected_skill_name"]) for c in contexts),
            "memory_prompts":sum(json.loads(c["selected_memories_json"]) != [] for c in contexts),
            "memory_before_root_cause":bool(contexts and json.loads(contexts[0]["selected_memories_json"]) and not json.loads(contexts[0]["evidence_ids_json"])),
            "tokens":sum(int(t["usage"].get("total_tokens",0)) for t in raw["model_traces"]),
            "latency_seconds":round(time.perf_counter()-started,3),"failure":failure,"control_safe":before == after and all(n == 0 for n in raw["business_write_counts"].values())}
    result["correct"] = result["actual"] == result["expected"]
    if result["correct"] and name in {"assets-on","memory-off"}:
        try:
            result["post_completion_invalidation"]=await post_completion_invalidation(db,target,memory,manifest_path,directory,kind="MEMORY" if name == "assets-on" else "KNOWLEDGE")
        except Exception as error:
            result["post_completion_invalidation"]={"status":"FAIL","error":type(error).__name__}
            (directory/"POST_COMPLETION_FAILURE.txt").write_text("".join(traceback.format_exception(error)),encoding="utf-8")
    write_json(directory/"RESULT.json",result)
    print(json.dumps(result,ensure_ascii=False),flush=True)
    return result


async def main_async(args):
    if args.resume_db:
        db=__import__('pathlib').Path(args.resume_db)
        await run(db,{"task_id":args.task_id,"run_id":args.run_id},resume=True)
        print(json.dumps({"pid":os.getpid(),"resumed_same_run":args.run_id}))
        return 0
    stamp=args.release or datetime.now(timezone.utc).strftime("assets-%Y%m%dT%H%M%SZ")
    base=EVIDENCE/"runs"/stamp
    base.mkdir(parents=True,exist_ok=False)
    runtime=ROOT/".runtime/m4-02"/stamp
    runtime.mkdir(parents=True,exist_ok=False)
    cases=args.case or ["assets-on","memory-off","knowledge-absent","knowledge-expired","knowledge-conflict","memory-expired","memory-revoked","checkpoint-invalidation"]
    results=[]
    for name in cases:
        try:
            results.append(await case(name,base,runtime))
        except Exception as error:
            (base/f"{name}-UNHANDLED.txt").write_text("".join(traceback.format_exception(error)),encoding="utf-8")
            results.append({"case":name,"correct":False,"failure":type(error).__name__})
    write_json(base/"RESULTS.json",{"release":stamp,"cases":results,"correct":sum(r["correct"] for r in results),"denominator":len(results)})
    return 0 if all(r["correct"] and r.get("post_completion_invalidation",{}).get("status") != "FAIL" for r in results) else 1


def main():
    load_local_environment()
    parser=argparse.ArgumentParser()
    parser.add_argument("--release")
    parser.add_argument("--case",action="append")
    parser.add_argument("--resume-db")
    parser.add_argument("--task-id")
    parser.add_argument("--run-id")
    return asyncio.run(main_async(parser.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
