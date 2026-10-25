"""CONT-UX A: deterministic reservations, real SQLite/API/MCP; no paid Provider.

Gold is offline and unchanged. A model double demonstrates execution contracts,
not real LLM quality. Trace rows are emitted only after actual test observations.
"""
from __future__ import annotations

import asyncio
import json
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from opspilot.domain.database import connect, initialize, reset_fixture
from opspilot.domain.d2 import BudgetExhausted, ScopeDenied, attempt_counts, finish_attempt, reserve_attempt, task_attempt_limits
from opspilot.domain.investigation_updates import complete_assessment, reserve_assessment
from opspilot.domain.s3 import prepare_s3_fixture
from opspilot.domain.task_control import (
    TaskControlError, admit_task_message, claim_task_run, create_session,
    create_task_with_initial_run, finish_task_run, register_worker_owner, trusted_identity,
)


def emit(case, **fields):
    payload = {"case_id": case, "evidence_level": "deterministic_actual_test_observation", **fields}
    print("CONTUX_TRACE " + json.dumps(payload, ensure_ascii=False, default=str), flush=True)
    destination = os.environ.get("OPSPILOT_CONTUX_TRACE_PATH")
    if destination:
        with open(destination, "a", encoding="utf-8") as stream:
            stream.write(json.dumps(payload, ensure_ascii=False, default=str) + "\n")


def new_task(tmp_path, name="budget", *, claim=True):
    db = tmp_path / f"{name}.sqlite3"
    reset_fixture(db, "S1_POS")
    prepare_s3_fixture(db, "DELIVERED_PENDING", contract_version=2, queue_age_seconds=1)
    identity = trusted_identity(db, "support-a")
    session = create_session(db, identity)
    task = create_task_with_initial_run(
        db, identity, session_id=str(session["session_id"]), service_id="orders-async-demo",
        integration_id="async-integration-a", ticket_id="CONTUX-A", s3_order_id="async-order",
        initial_message="订单 200 但回调尚未完成，请核对。", idempotency_key="initial",
    )
    if claim:
        claim_task_run(db, identity, str(task["run_id"]))
    return db, identity, task


def route(db, identity, task, key, *, action="INVESTIGATE", text="请重新核对当前接收状态。"):
    source = admit_task_message(
        db, identity, session_id=str(task["session_id"]), task_id=str(task["task_id"]),
        input_kind="CHAT_READONLY", body=text, idempotency_key=key,
        defer_task_chat_until_classified=True,
    )
    mid = str(source["message_id"])
    reservation = reserve_assessment(db, identity, task_id=str(task["task_id"]),
                                     source_message_id=mid, idempotency_key=mid, model_id="deterministic-no-provider")
    if reservation.get("should_call_model"):
        prepared = reservation["prepared"]
        result = complete_assessment(
            db, identity=identity, assessment_id=prepared["assessment_id"], attempt_id=prepared["attempt_id"],
            classification={"intent":"FOLLOW_UP", "change_summary":"", "readonly_action":action},
        )
    else:
        result = reservation
    return source, result


def reserve(db, task_id, run_id, kind="MODEL", *, limit=999):
    from uuid import uuid4
    return reserve_attempt(db, task_id, kind, limit, call_id=f"contux-{uuid4()}", run_id=run_id)


def ledger(db, task_id):
    with connect(db) as c:
        return {"budget":dict(c.execute("SELECT * FROM task_execution_budgets WHERE task_id=?",(task_id,)).fetchone()),
                "attempts":[dict(r) for r in c.execute("SELECT * FROM d2_attempts WHERE task_id=? ORDER BY rowid",(task_id,))]}


def test_a01_new_followup_after_initial_limit_and_operation_replay(tmp_path):
    db, identity, task = new_task(tmp_path)
    tid, first = str(task["task_id"]), str(task["run_id"])
    for _ in range(8):
        reserve(db, tid, first, limit=8)
    finish_task_run(db, identity, first, "WAITING_INPUT")
    source, routed = route(db, identity, task, "followup-one")
    run = str(routed["investigation_run_id"])
    duplicate, routed_again = route(db, identity, task, "followup-one")
    assert source["message_id"] == duplicate["message_id"]
    assert routed_again["investigation_run_id"] == run
    claim_task_run(db, identity, run)
    attempt, _ = reserve(db, tid, run, limit=task_attempt_limits(db, tid)["MODEL"])
    emit("A01", source=source, routed=routed, replay=routed_again, new_attempt_id=attempt, ledger=ledger(db, tid))
    assert attempt_counts(db, tid)["MODEL"] == 9
    assert task_attempt_limits(db, tid) == {"MODEL":24, "MCP":18}
    with connect(db) as c:
        assert c.execute("SELECT policy_version FROM task_execution_budgets WHERE task_id=?",(tid,)).fetchone()[0] == "CONTUX_S3_V1"
    finish_task_run(db, identity, run, "WAITING_INPUT")
    second, routed_two = route(db, identity, task, "followup-two")
    assert second["message_id"] != source["message_id"] and routed_two["investigation_run_id"] != run


@pytest.mark.parametrize("followup,kind,cap", [(False,"MODEL",8),(False,"MCP",6),(True,"MODEL",4),(True,"MCP",3)])
def test_a02_run_limit_is_trusted_not_the_caller_limit(tmp_path, followup, kind, cap):
    db, identity, task = new_task(tmp_path)
    tid, run = str(task["task_id"]), str(task["run_id"])
    if followup:
        finish_task_run(db, identity, run, "WAITING_INPUT")
        _, routed = route(db, identity, task, "followup")
        run = str(routed["investigation_run_id"])
        claim_task_run(db, identity, run)
    for _ in range(cap):
        reserve(db, tid, run, kind)
    try:
        reserve(db, tid, run, kind)
    except BudgetExhausted as error:
        emit("A02", run_id=run, kind=kind, cap=cap, reason=str(error), ledger=ledger(db, tid))
        assert getattr(error, "reason_code", "") == f"RUN_{kind}_LIMIT"
    else:
        pytest.fail("Caller limit=999 bypassed the trusted per-Run cap")


def _race(db, tid, run, kind="MODEL"):
    barrier = threading.Barrier(2)
    def contender(_):
        barrier.wait(timeout=5)
        try:
            return {"accepted":True, "attempt_id":reserve(db,tid,run,kind)[0]}
        except BudgetExhausted as error:
            return {"accepted":False,"reason":getattr(error,"reason_code",str(error))}
    with ThreadPoolExecutor(max_workers=2) as pool:
        return list(pool.map(contender, range(2)))


def test_a02_two_connections_cannot_overfill_run(tmp_path):
    db, identity, task = new_task(tmp_path)
    finish_task_run(db, identity, str(task["run_id"]), "WAITING_INPUT")
    _, result = route(db, identity, task, "race")
    tid, run = str(task["task_id"]), str(result["investigation_run_id"])
    claim_task_run(db, identity, run)
    for _ in range(3): reserve(db, tid, run)
    outcomes = _race(db, tid, run)
    emit("A02-RUN-RACE", outcomes=outcomes, ledger=ledger(db,tid))
    assert sum(x["accepted"] for x in outcomes) == 1


def test_a02_task_limit_survives_many_distinct_followups_and_race(tmp_path):
    db, identity, task = new_task(tmp_path)
    tid, run = str(task["task_id"]), str(task["run_id"])
    for _ in range(7): reserve(db,tid,run,limit=8)
    finish_task_run(db,identity,run,"WAITING_INPUT")
    for i in range(4):
        _, routed = route(db,identity,task,f"intent-{i}")
        run=str(routed["investigation_run_id"]); claim_task_run(db,identity,run)
        for _ in range(4): reserve(db,tid,run)
        finish_task_run(db,identity,run,"WAITING_INPUT")
    _, routed = route(db,identity,task,"last-intent")
    run=str(routed["investigation_run_id"]); claim_task_run(db,identity,run)
    outcomes=_race(db,tid,run)
    emit("A02-TASK-RACE",outcomes=outcomes,ledger=ledger(db,tid))
    assert sum(x["accepted"] for x in outcomes)==1 and attempt_counts(db,tid)["MODEL"]==24
    assert next(x for x in outcomes if not x["accepted"])["reason"]=="TASK_MODEL_LIMIT"


def test_a03_migration_does_not_upgrade_existing_task_and_s1_stays_legacy(tmp_path):
    db, identity, task = new_task(tmp_path, claim=False)
    tid=str(task["task_id"])
    # Reconstruct the actual v16 budget schema, not just its version label.
    with connect(db) as c:
        columns={row["name"] for row in c.execute("PRAGMA table_info(task_execution_budgets)")}
        for name in ("policy_version","aux_provider_limit"):
            if name in columns: c.execute(f"ALTER TABLE task_execution_budgets DROP COLUMN {name}")
        c.execute("UPDATE task_execution_budgets SET model_limit=8,mcp_limit=6")
        c.execute("PRAGMA user_version=16")
        before=dict(c.execute("SELECT * FROM task_execution_budgets WHERE task_id=?",(tid,)).fetchone())
    initialize(db)
    with connect(db) as c:
        after=dict(c.execute("SELECT * FROM task_execution_budgets WHERE task_id=?",(tid,)).fetchone())
        assert after["policy_version"]=="LEGACY_V1"
        assert after["aux_provider_limit"] is None
        assert all(after[k]==v for k,v in before.items())
    assert task_attempt_limits(db,tid)=={"MODEL":8,"MCP":6}
    session=create_session(db,identity)
    s1=create_task_with_initial_run(db,identity,session_id=str(session["session_id"]),service_id="orders-demo",
         integration_id="integration-a",ticket_id="LEGACY",initial_message="401",idempotency_key="s1")
    assert task_attempt_limits(db,str(s1["task_id"]))=={"MODEL":8,"MCP":6}
    emit("A03",legacy_before=before,legacy_after=after,new_s1=s1)


def test_a03_cross_task_and_missing_run_cannot_spend_new_policy(tmp_path):
    db, _, task = new_task(tmp_path)
    tid=str(task["task_id"])
    with pytest.raises(ScopeDenied): reserve_attempt(db,tid,"MODEL",999,call_id="no-run")
    with pytest.raises(ScopeDenied): reserve(db,tid,"foreign-run")
    with connect(db) as c:
        c.execute("UPDATE task_execution_budgets SET model_limit=25 WHERE task_id=?",(tid,))
    with pytest.raises(ScopeDenied): reserve(db,tid,str(task["run_id"]))
    assert attempt_counts(db,tid)=={"MODEL":0,"MCP":0}


def test_a04_auxiliary_classifiers_include_reserved_failures_and_stop_durably(tmp_path):
    from opspilot.domain.investigation_updates import fail_assessment
    db, identity, task = new_task(tmp_path)
    finish_task_run(db,identity,str(task["run_id"]),"WAITING_INPUT")
    tid=str(task["task_id"])
    reservations=[]
    for i in range(8):
        source=admit_task_message(db,identity,session_id=str(task["session_id"]),task_id=tid,
           input_kind="CHAT_READONLY",body="这是什么意思？",idempotency_key=f"aux-{i}",defer_task_chat_until_classified=True)
        mid=str(source["message_id"])
        r=reserve_assessment(db,identity,task_id=tid,source_message_id=mid,idempotency_key=mid,model_id="no-provider")
        assert r.get("should_call_model")
        reservations.append(r["prepared"]["attempt_id"])
        if i % 2:
            fail_assessment(db,assessment_id=r["prepared"]["assessment_id"],attempt_id=r["prepared"]["attempt_id"],error_code="NETWORK_OUTCOME_UNKNOWN")
    source=admit_task_message(db,identity,session_id=str(task["session_id"]),task_id=tid,
       input_kind="CHAT_READONLY",body="再次解释",idempotency_key="aux-over",defer_task_chat_until_classified=True)
    mid=str(source["message_id"])
    over=reserve_assessment(db,identity,task_id=tid,source_message_id=mid,idempotency_key=mid,model_id="no-provider")
    emit("A04",attempt_ids=reservations,over=over,source=source)
    assert over.get("should_call_model") is False and over["fallback_reason"]=="TASK_AUX_PROVIDER_LIMIT"
    with connect(db) as c:
        assert c.execute("SELECT COUNT(*) FROM investigation_update_attempts").fetchone()[0]==8
        run=c.execute("SELECT status,blocked_reason FROM task_runs WHERE run_id=?",(source["run_id"],)).fetchone()
        assert tuple(run)==("FAILED","TASK_AUX_PROVIDER_LIMIT")
        notice=c.execute("SELECT body FROM messages WHERE command_id=?",(f"budget-notice:{source['run_id']}",)).fetchone()
        assert notice and notice[0].strip() and "未" in notice[0]
    replay=reserve_assessment(db,identity,task_id=tid,source_message_id=mid,idempotency_key=mid,model_id="no-provider")
    assert not replay.get("should_call_model")


def test_a05_run_exhaustion_has_nonempty_precise_readonly_delivery(tmp_path):
    from opspilot.s3_investigation import S3Nodes
    db, identity, task = new_task(tmp_path)
    finish_task_run(db,identity,str(task["run_id"]),"WAITING_INPUT")
    _, routed=route(db,identity,task,"exhausted")
    tid,run=str(task["task_id"]),str(routed["investigation_run_id"])
    claim_task_run(db,identity,run)
    for _ in range(4): reserve(db,tid,run,limit=24)
    class NoProvider:
        async def ainvoke(self,_): raise AssertionError("Provider called at Run cap")
    node=S3Nodes(db,tid,run,NoProvider(),"no-provider",None,[],readonly_followup=True,memory_enabled=False)
    asyncio.run(node.report({"evidence_ids":[],"tool_observations":[]}))
    with connect(db) as c:
        row=dict(c.execute("SELECT * FROM c1_readonly_followup_runs WHERE run_id=?",(run,)).fetchone())
        assert row["answer_text"].strip() and row["result_state"]=="PARTIAL"
        assert row["reason_code"]=="RUN_MODEL_LIMIT"
        assert c.execute("SELECT COUNT(*) FROM s3_diagnoses").fetchone()[0]==0
    emit("A05",result=row,ledger=ledger(db,tid))


def test_a04_all_auxiliary_categories_share_one_atomic_task_cap(tmp_path, monkeypatch):
    import opspilot.domain.chat as chat
    db, identity, task = new_task(tmp_path)
    finish_task_run(db,identity,str(task["run_id"]),"WAITING_INPUT")
    tid=str(task["task_id"]); worker="contux-aux-worker"
    register_worker_owner(db,worker,os.getpid())
    original=chat._prepare_context
    attempt_ids=[]
    # Small compression input double: only reservation accounting is under test,
    # not summary correctness. No business Evidence or model text is fabricated.
    def compression_input(*_args,**_kwargs):
        return {"needs_compression":True,"compression_messages":[{"role":"user","content":"historical message"}],
                "compression_work":{"dependencies":[],"allowed_message_ids":[],"source_sequence_map":{},
                  "source_material":{},"covered_from_seq":1,"covered_to_seq":1,"parent_summary_id":None}}
    for i in range(2):
        source,_=route(db,identity,task,f"mixed-{i}",action="EXPLAIN",text="请解释现有材料。")
        run=str(source["run_id"]); claim_task_run(db,identity,run)
        monkeypatch.setattr(chat,"_prepare_context",compression_input)
        compression=chat.prepare_chat_compression_attempt(db,run,worker,"no-provider")
        attempt_ids.append(compression["attempt_id"])
        monkeypatch.setattr(chat,"_prepare_context",original)
        answer=chat.prepare_chat_attempt(db,run,worker,"no-provider")
        attempt_ids.append(answer["attempt_id"])
        chat.fail_chat_attempt(db,worker,str(answer["attempt_id"]),"NETWORK_OUTCOME_UNKNOWN")
    source,_=route(db,identity,task,"mixed-last",action="EXPLAIN",text="请直接解释。")
    run=str(source["run_id"]); claim_task_run(db,identity,run)
    # 3 classifications + 2 compression + 2 Chat = 7; one place remains.
    barrier=threading.Barrier(2)
    other=admit_task_message(db,identity,session_id=str(task["session_id"]),task_id=tid,
        input_kind="CHAT_READONLY",body="另一次有意操作",idempotency_key="mixed-race-other",defer_task_chat_until_classified=True)
    def contender(which):
        barrier.wait(timeout=5)
        if which==0:
            r=chat.prepare_chat_attempt(db,run,worker,"no-provider")
            return {"kind":"CHAT","accepted":bool(r.get("attempt_id")),"result":r}
        mid=str(other["message_id"])
        r=reserve_assessment(db,identity,task_id=tid,source_message_id=mid,idempotency_key=mid,model_id="no-provider")
        return {"kind":"CLASSIFIER","accepted":bool(r.get("should_call_model")),"result":r}
    with ThreadPoolExecutor(max_workers=2) as pool: outcomes=list(pool.map(contender,range(2)))
    with connect(db) as c:
        counts={name:c.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0] for name in
                ("investigation_update_attempts","chat_attempts","context_compression_attempts")}
        assert sum(counts.values())==8
    emit("A04-MIXED-RACE",outcomes=outcomes,counts=counts,attempt_ids=attempt_ids)
    assert sum(x["accepted"] for x in outcomes)==1


@pytest.mark.parametrize("followup",[False,True])
@pytest.mark.parametrize("window",["before_checkpoint","after_observation"])
def test_a06_real_os_crash_restores_same_run_without_new_allowance(tmp_path, followup, window):
    import subprocess, sys
    db,identity,task=new_task(tmp_path,claim=False)
    tid,run=str(task["task_id"]),str(task["run_id"])
    cap=8
    if followup:
        claim_task_run(db,identity,run); finish_task_run(db,identity,run,"WAITING_INPUT")
        _,result=route(db,identity,task,"os-followup")
        run=str(result["investigation_run_id"]); cap=4
    checkpoint=tmp_path/"checkpoint.sqlite3"
    args=[sys.executable,str(Path(__file__).with_name("cont_ux_stage_a_worker.py")),"crash",str(db),str(checkpoint),tid,run,window,str(cap)]
    env=dict(os.environ,PYTHONUTF8="1",PYTHONIOENCODING="utf-8")
    crash=subprocess.run(args,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,env=env,timeout=50)
    (tmp_path/"crash.log").write_bytes(crash.stdout)
    assert crash.returncode==87,crash.stdout.decode("utf8",errors="replace")
    before=ledger(db,tid)
    with connect(db) as c:
        control_before=dict(c.execute("SELECT * FROM task_controls WHERE task_id=?",(tid,)).fetchone())
    args[2]="recover"
    recovered=subprocess.run(args,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,env=env,timeout=60)
    (tmp_path/"recover.log").write_bytes(recovered.stdout)
    assert recovered.returncode==0,recovered.stdout.decode("utf8",errors="replace")
    events=[json.loads(line.removeprefix("CONTUX_OS ")) for line in recovered.stdout.decode("utf8").splitlines() if line.startswith("CONTUX_OS ")]
    crash_events=[json.loads(line.removeprefix("CONTUX_OS ")) for line in crash.stdout.decode("utf8").splitlines() if line.startswith("CONTUX_OS ")]
    final=next(e for e in events if e["event"]=="recovered_finished")
    assert final["pid"]!=crash_events[-1]["pid"]
    assert final["run"]["run_id"]==run and final["control"]==control_before
    assert sum(r["kind"]=="MODEL" for r in final["attempts"])==cap
    assert {r["attempt_id"] for r in before["attempts"]}<={r["attempt_id"] for r in final["attempts"]}
    assert sum(r["kind"]=="MCP" for r in final["attempts"])==1
    if window=="after_observation":
        assert {r["observation_id"] for r in final["observations"]}=={r["observation_id"] for r in crash_events[-1]["observations"]}
    if followup:
        assert final["answer"]["answer_text"].strip() and final["answer"]["result_state"]=="PARTIAL"
    assert final["budget"]["deadline_ms"]==300000
    assert final["budget"]["active_elapsed_ms"]>=before["budget"]["active_elapsed_ms"]
    emit("A06",window=window,followup=followup,crash=crash_events,recovery=events,ledger_before=before)


@pytest.mark.parametrize("protocol_first",["knowledge","delivery"])
def test_a08_four_api_requests_with_real_mcp_http_and_deterministic_model(tmp_path, monkeypatch, protocol_first):
    from fastapi.testclient import TestClient
    from langchain_core.messages import AIMessage, AIMessageChunk
    from opspilot.web.app import create_app
    from opspilot.web.worker import SingleInstanceWorker, _dispatch_run
    from opspilot.domain.execution_budget import execution_budget_snapshot
    from test_m4_c1_s3_prompt import _business_snapshot
    import opspilot.investigator as investigator
    import langchain_openai
    db=tmp_path/"four-requests.sqlite3"
    reset_fixture(db,"S1_POS"); preparation=prepare_s3_fixture(db,"DELIVERED_PENDING",contract_version=2,queue_age_seconds=1)
    calls=[]; classifications=[]
    class DeterministicModel:
        def __init__(self,**_kwargs): pass
        def bind_tools(self,*_args,**_kwargs): return self
        async def ainvoke(self,messages):
            body=json.loads(messages[-1].content); calls.append({"kind":"INVESTIGATOR","body":body})
            inputs=body["untrusted_user_inputs"]; question=str(inputs[-1]["body"])
            facts=body["current_mcp_evidence"]; kinds={x["type"] for x in facts}
            knowledge=body["retrieved_knowledge_method_only"]
            protocol="绑定协议" in question
            if protocol:
                available={"knowledge":bool(knowledge),"delivery":"s3_delivery" in kinds}
                choice=next((kind for kind in [protocol_first,"delivery" if protocol_first=="knowledge" else "knowledge"] if not available[kind]),None)
                tool={"knowledge":"search_callback_knowledge","delivery":"get_callback_delivery"}.get(choice)
            elif "新一轮" in question:
                tool=None if "s3_receiver" in kinds else "get_receiver_processing"
            else:
                tool=next((name for kind,name in [("s3_order","get_order_status"),("s3_delivery","get_callback_delivery"),("s3_receiver","get_receiver_processing")] if kind not in kinds),None)
            if tool:
                args={"reason":"read an applicable source missing from this Run; deterministic test double"}
                if tool=="search_callback_knowledge": args["query"]="HTTP 202 receiver acknowledgement"
                return AIMessage(content="",tool_calls=[{"id":f"tool-{len(calls)}","name":tool,"args":args}])
            if protocol:
                doc=next(x for x in knowledge if x["document_id"]=="receiver-ack-contract-v2")
                answer=f"根据 {doc['document_id']}@{doc['version']}，HTTP 202 表示受理，不代表处理完成；本轮投递证据仅证明受理。"
                value={"action":"answer","result_state":"ANSWERED","answer":answer,"processing_claim":"NOT_APPLICABLE"}
            else:
                receiver=next(x for x in facts if x["type"]=="s3_receiver")
                answer=f"本轮同一事件 {receiver['facts']['event_id']} 接收状态为 {receiver['facts']['status']}，来源 {receiver['id']}。"
                value={"action":"answer","result_state":"ANSWERED","answer":answer,
                       "processing_claim":receiver["facts"]["status"],"target_event_id":receiver["facts"]["event_id"]}
            return AIMessage(content=json.dumps(value,ensure_ascii=False))
        async def astream(self,messages):
            contents=json.dumps([m.content for m in messages],ensure_ascii=False)
            calls.append({"kind":"CHAT","messages":[{"role":m.type,"content":m.content} for m in messages]})
            assert "receiver-ack-contract-v2" in contents and "prior" in contents.lower()
            yield AIMessageChunk(content="刚才引用的是 receiver-ack-contract-v2@2.0.0。它只约定 202 受理，不能证明接收方处理完成；当前状态须另取本轮事实。")
    monkeypatch.setattr(investigator,"ChatOpenAI",DeterministicModel)
    monkeypatch.setattr(langchain_openai,"ChatOpenAI",DeterministicModel)
    monkeypatch.setenv("OPSPILOT_MODEL_API_KEY","deterministic-no-paid-provider")
    monkeypatch.setenv("OPSPILOT_MODEL_NAME","deterministic-no-paid-provider")
    def classify(*,prepared,**_kwargs):
        classifications.append(prepared)
        return {"intent":"FOLLOW_UP","change_summary":"","readonly_action":"EXPLAIN" if "刚才引用" in prepared["source_message"] else "INVESTIGATE"}
    monkeypatch.setattr("opspilot.domain.investigation_updates.classify_input",classify)
    app=create_app(db_path=db,start_worker=False,credentials={"support-a":"contux-password"},expected_origin="http://testserver")
    rounds=[]; worker=SingleInstanceWorker(db)
    with TestClient(app) as client:
        login=client.post("/api/auth/login",headers={"Origin":"http://testserver"},json={"actor_id":"support-a","password":"contux-password"})
        assert login.status_code==200
        headers={"Origin":"http://testserver","X-CSRF-Token":login.json()["csrf_token"]}
        session=client.post("/api/sessions",headers=headers).json()["session_id"]
        created=client.post(f"/api/sessions/{session}/tasks",headers={**headers,"Idempotency-Key":"initial-api"},
             json={"investigation_kind":"ASYNC_CALLBACK","s3_order_id":"async-order","initial_message":"订单返回 200，但下游回调还未完成，请核实。"})
        assert created.status_code==202,created.text
        task=created.json(); tid=str(task["task_id"])
        worker.acquire(); worker.register()
        try:
            def drive(run):
                with connect(db) as c: selected=dict(c.execute("SELECT * FROM task_runs WHERE run_id=?",(run,)).fetchone())
                asyncio.run(_dispatch_run(db,tmp_path/"checkpoints.sqlite3",worker.owner_id,"executor-a",selected,worker.epoch))
                item=client.get(f"/api/runs/{run}").json()
                assert item["status"]=="SUCCEEDED",item
            drive(str(task["run_id"]))
            inspector=client.get(f"/api/tasks/{tid}/inspector").json()
            initial=inspector["investigation_answers"][0]
            assert initial["answer_text"].strip()
            rounds.append({"source":task,"result":initial,"active_time":execution_budget_snapshot(db,tid)})
            before=_business_snapshot(db,tid); before.pop("outbox_count")
            for i,text in enumerate([
                "请按当前绑定协议核对 HTTP 202 的含义，给出能核对的来源。",
                "你刚才引用的那份，为什么不能证明已经处理完成？",
                "那现在这次回调完成了吗？请按新一轮事实核实。",
            ]):
                prep=None
                if i==2:
                    # Independent trusted test preparation, never an Agent tool.
                    with connect(db) as c:
                        previous=dict(c.execute("SELECT * FROM s3_receivers WHERE tenant_id='tenant-a' AND order_id='async-order'").fetchone())
                        c.execute("UPDATE s3_receivers SET status='PROCESSED',version=version+1 WHERE tenant_id='tenant-a' AND order_id='async-order'")
                        after=dict(c.execute("SELECT * FROM s3_receivers WHERE tenant_id='tenant-a' AND order_id='async-order'").fetchone())
                    prep={"kind":"INDEPENDENT_TEST_PREPARATION","before":previous,"after":after}
                response=client.post(f"/api/sessions/{session}/messages",headers={**headers,"Idempotency-Key":f"round-{i}"},json={"task_id":tid,"input_kind":"CHAT_READONLY","body":text})
                assert response.status_code==202,response.text
                source=response.json(); mid=source["message_id"]
                assessment=client.post(f"/api/tasks/{tid}/investigation-updates/proposals",headers={**headers,"Idempotency-Key":mid},json={"source_message_id":mid})
                assert assessment.status_code==200,assessment.text
                classified=assessment.json()
                run=str(classified.get("investigation_run_id") or source["run_id"])
                drive(run)
                inspector=client.get(f"/api/tasks/{tid}/inspector").json()
                if i==1:
                    messages=client.get(f"/api/sessions/{session}/messages").json()["items"]
                    answer=next(m for m in reversed(messages) if m["role"]=="ASSISTANT")
                    assert "receiver-ack-contract-v2" in answer["body"]
                else:
                    answer=next(x for x in inspector["readonly_followups"] if x["run_id"]==run)
                    assert answer["answer_text"].strip() and answer["result_state"]=="ANSWERED"
                    if i==2: assert "PROCESSED" in answer["answer_text"]
                rounds.append({"operation_id":f"round-{i}","message":source,"classification":classified,"run_id":run,"result":answer,
                               "preparation":prep,"active_time":execution_budget_snapshot(db,tid)})
                replay=client.post(f"/api/sessions/{session}/messages",headers={**headers,"Idempotency-Key":f"round-{i}"},json={"task_id":tid,"input_kind":"CHAT_READONLY","body":text})
                assert replay.json()["message_id"]==mid
            after=_business_snapshot(db,tid); after.pop("outbox_count")
            assert before==after
            assert task_attempt_limits(db,tid)=={"MODEL":24,"MCP":18}
            assert attempt_counts(db,tid)=={"MODEL":9,"MCP":6}
            assert sum(x["kind"]=="CHAT" for x in calls)==1
            assert len(classifications)==3
            with connect(db) as c:
                observations=[dict(r) for r in c.execute("SELECT * FROM d2_tool_observations WHERE task_id=? ORDER BY rowid",(tid,))]
                manifests=[dict(r) for r in c.execute("SELECT * FROM chat_context_manifests WHERE task_id=?",(tid,))]
            emit("A08",protocol_first=protocol_first,rounds=rounds,actual_model_double_inputs=calls,classifier_inputs=classifications,
                 observations=observations,chat_manifests=manifests,ledger=ledger(db,tid),protected_before=before,protected_after=after,
                 paid_provider_calls=0,token_usage="NOT_AVAILABLE_FOR_DETERMINISTIC_DOUBLE",preparation=preparation)
        finally: worker.release()
