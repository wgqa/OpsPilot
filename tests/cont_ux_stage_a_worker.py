"""OS crash/recovery harness; only deterministic model calls and real local MCP."""
from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ["OPSPILOT_MODEL_API_KEY"] = "deterministic-no-paid-provider"
os.environ["OPSPILOT_MODEL_NAME"] = "deterministic-no-paid-provider"
os.environ["OPSPILOT_MODEL_BASE_URL"] = "http://127.0.0.1:9/v1"


def event(name, **fields):
    print("CONTUX_OS " + json.dumps({"event":name,"pid":os.getpid(),**fields},ensure_ascii=False,default=str),flush=True)


def main():
    mode, db, checkpoint, tid, run, window, cap = sys.argv[1:]
    cap = int(cap)
    from langchain_core.messages import AIMessage
    from opspilot.domain.database import connect
    from opspilot.domain.d2 import reserve_attempt, attempt_counts
    from opspilot.domain.execution_budget import begin_execution_interval, execution_budget_snapshot
    from opspilot.domain.task_control import claim_task_run, next_worker_run, trusted_identity
    from opspilot.web.worker import SingleInstanceWorker, _dispatch_run
    import opspilot.investigator as investigator
    from opspilot.s3_investigation import S3Nodes

    class Model:
        def __init__(self, **_): pass
        def bind_tools(self,*_,**__): return self
        async def ainvoke(self,messages):
            body=json.loads(messages[-1].content)
            facts=body.get("current_mcp_evidence",[])
            if not facts:
                return AIMessage(content="",tool_calls=[{"id":"current-receiver","name":"get_receiver_processing","args":{"reason":"verify current bound receiver"}}])
            receiver=next((e for e in facts if e["type"]=="s3_receiver"),None)
            return AIMessage(content=json.dumps({"action":"answer","result_state":"ANSWERED" if receiver else "PARTIAL",
                "answer":"本轮接收状态已核对。" if receiver else "当前处理状态缺少本轮事实。",
                "target_event_id":receiver["facts"]["event_id"] if receiver else None,
                "processing_claim":receiver["facts"]["status"] if receiver else "UNKNOWN"},ensure_ascii=False))
    investigator.ChatOpenAI=Model
    worker=SingleInstanceWorker(db); worker.acquire(); worker.register()
    try:
        if mode=="crash":
            claim_task_run(db,trusted_identity(db,"support-a"),run)
            for i in range(cap-1):
                reserve_attempt(db,tid,"MODEL",24,call_id=f"unknown-before-exit-{i}",run_id=run)
            if window=="before_checkpoint":
                begin_execution_interval(db,tid)
                event("before_first_checkpoint_exit",task_id=tid,run_id=run,counts=attempt_counts(db,tid),budget=execution_budget_snapshot(db,tid))
                os._exit(87)
            # Leave the claim recoverable so the normal Worker owns all I/O/time.
            with connect(db) as c:
                c.execute("UPDATE task_runs SET status='INTERRUPTED_RECOVERABLE' WHERE run_id=?",(run,))
            original=S3Nodes.execute
            async def crash_after_observation(self,state):
                result=await original(self,state)
                if result.get("tool_observations"):
                    event("observation_committed_before_checkpoint_exit",task_id=tid,run_id=run,
                          observations=result["tool_observations"],counts=attempt_counts(db,tid),budget=execution_budget_snapshot(db,tid))
                    os._exit(87)
                return result
            S3Nodes.execute=crash_after_observation
        else:
            recovered=asyncio.run(worker.recover_after_exclusive_start())
            event("exclusive_recovery",run_id=run,recovered=recovered,counts=attempt_counts(db,tid),budget=execution_budget_snapshot(db,tid))
        with connect(db) as c:
            selected=dict(c.execute("SELECT * FROM task_runs WHERE run_id=?",(run,)).fetchone())
        asyncio.run(_dispatch_run(Path(db),Path(checkpoint),worker.owner_id,"executor-a",selected,worker.epoch))
        with connect(db) as c:
            result=dict(c.execute("SELECT * FROM task_runs WHERE run_id=?",(run,)).fetchone())
            attempts=[dict(r) for r in c.execute("SELECT * FROM d2_attempts WHERE task_id=? ORDER BY rowid",(tid,))]
            observations=[dict(r) for r in c.execute("SELECT observation_id,attempt_id,status,evidence_id FROM d2_tool_observations WHERE task_id=?",(tid,))]
            control=dict(c.execute("SELECT * FROM task_controls WHERE task_id=?",(tid,)).fetchone())
            answer=c.execute("SELECT answer_text,result_state,reason_code FROM c1_readonly_followup_runs WHERE run_id=?",(run,)).fetchone()
        event("recovered_finished",run=result,attempts=attempts,observations=observations,control=control,
              answer=dict(answer) if answer else None,budget=execution_budget_snapshot(db,tid))
        return 0 if mode=="recover" and result["status"]=="SUCCEEDED" else 5
    finally:
        worker.release()


if __name__=="__main__": raise SystemExit(main())
