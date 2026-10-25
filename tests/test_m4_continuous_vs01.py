from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
import sqlite3
import subprocess
import sys

import pytest

from langchain_core.messages import AIMessage

from opspilot.domain.database import connect, reset_fixture
from opspilot.domain.d2 import attempt_counts, reserve_attempt
from opspilot.s3_investigation import S3Nodes
from test_m4_c1_s3_prompt import _start_investigation_run, _business_snapshot
from test_m4_c1_hf_01 import _diagnosed_task


def _followup(tmp_path: Path):
    db = tmp_path / "continuous.sqlite3"
    reset_fixture(db, "S1_POS")
    session, task, _, _ = _diagnosed_task(db)
    _, run = _start_investigation_run(db, session, task, suffix="continuous")
    return db, task, run


class Model:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.messages = []

    def bind_tools(self, *_args, **_kwargs):
        return self

    async def ainvoke(self, messages):
        self.messages.append(messages)
        return next(self.responses)


def _node(db, task, run, model, client=None):
    return S3Nodes(db, task, run, model, "continuous-deterministic", client, [],
                   readonly_followup=True, memory_enabled=False)


def _business_only(db, task):
    value = _business_snapshot(db, task)
    value.pop("outbox_count")  # a read-only result may emit its own user-visible progress event
    return value


def test_vs01_real_transport_history_capability(tmp_path):
    # No fabricated Observation is used to establish a transport send.
    from opspilot.domain import s3_history

    db = tmp_path / "history.sqlite3"
    reset_fixture(db, "S1_POS")
    prepared = s3_history.prepare_transport_history_fixture(
        db, order_id="continuous-order", attempts=[
            {"event_id": "event-one", "http_status": 503},
            {"event_id": "event-one", "http_status": 202},
        ], receiver_status="QUEUED",
    )
    assert len(prepared["transport_trace"]) == 2
    with connect(db) as c:
        rows = [dict(row) for row in c.execute("SELECT * FROM s3_transport_attempts ORDER BY attempt_no")]
    assert [row["http_status"] for row in rows] == [503, 202]
    assert len({row["transport_request_id"] for row in rows}) == 2
    assert {row["event_id"] for row in rows} == {"event-one"}


def test_vs06_remaining_candidates_follow_observation_into_normal_decision(tmp_path):
    db, task, run = _followup(tmp_path)
    model = Model([
        AIMessage(content="two relevant candidates", tool_calls=[
            {"name": "search_callback_knowledge", "id": "first", "args": {"query": "202", "reason": "interpret acknowledgement"}},
            {"name": "get_receiver_processing", "id": "second", "args": {"reason": "check actual processing"}},
        ]),
        AIMessage(content="RESULT: PARTIAL\n当前协议检索没有结果，仍无法确认目标事件的处理状态。"),
    ])
    class Client:
        def __init__(self): self.names = []
        async def call_tool(self, name, args):
            self.names.append(name)
            return SimpleNamespace(is_error=False, structured_content={"documents": []})
    client = Client()
    node = _node(db, task, run, model, client)
    async def journey():
        state = {"evidence_ids": [], "tool_observations": []}
        state.update(await node.investigate(state))
        state.update(await node.execute(state))
        state.update(await node.investigate(state))
        return state
    asyncio.run(journey())
    second_input = json.loads(model.messages[1][-1].content)
    remaining = second_input.get("unexecuted_candidates", [])
    assert any(item["tool_name"] == "get_receiver_processing" and item.get("tool_call_id") == "second" for item in remaining)
    assert client.names == ["search_callback_knowledge"]  # no automatic execution of the second proposal
    assert len(model.messages) == 2  # no per-candidate reviewer request
    assert second_input["previous_actions"]


def test_vs08_reuses_a_current_final_answer_without_report_provider_call(tmp_path):
    db, task, run = _followup(tmp_path)
    # The real prompt/trace/source validation is exercised, not a hand-written final-answer flag.
    model = Model([AIMessage(content="RESULT: PARTIAL\n当前还没有本轮接收状态证据，不能断言已处理完成。")])
    node = _node(db, task, run, model)
    before = _business_only(db, task)
    async def journey():
        state = {"evidence_ids": [], "tool_observations": []}
        state.update(await node.investigate(state))
        state.update(await node.report(state))
        return state
    asyncio.run(journey())
    with connect(db) as c:
        row = c.execute("SELECT answer_text FROM c1_readonly_followup_runs WHERE run_id=?", (run,)).fetchone()
    assert len(model.messages) == 1
    assert row[0] == "当前还没有本轮接收状态证据，不能断言已处理完成。"
    assert _business_only(db, task) == before


def _history_task(tmp_path, *, different_event=False, history_mode="observed", receiver="PROCESSED"):
    from opspilot.domain.s3_history import prepare_transport_history_fixture
    from test_m4_03_s3 import _task
    from opspilot.domain.task_control import claim_task_run
    db = tmp_path / "event-history.sqlite3"
    reset_fixture(db, "S1_POS")
    prepare_transport_history_fixture(db, order_id="bound-history", attempts=[
        {"event_id":"event-first", "http_status":503},
        {"event_id":"event-second" if different_event else "event-first", "http_status":202},
    ], receiver_status=receiver, history_mode=history_mode)
    identity, task = _task(db, "bound-history", text="请核对 event-first 的回调历史及现在是否处理完成。")
    claim_task_run(db, identity, str(task["run_id"]))
    return db, identity, task


def test_vs02_event_request_identity_and_vs04_current_authorization(tmp_path):
    from opspilot.domain.s3_history import get_transport_history_fact
    from opspilot.domain.s3 import get_receiver_processing_fact, current_s3_evidence
    from opspilot.domain.d2 import ScopeDenied
    from opspilot.s3_delivery import supported_response
    from s3_observation_support import record_s3_observation
    db, _, task = _history_task(tmp_path, different_event=True)
    history = get_transport_history_fact(db, task["task_id"], "event-first")
    assert {row["event_id"] for row in history["facts"]["attempts"]} == {"event-first"}
    assert history["facts"]["attempts"][0]["http_status"] == 503
    observation = record_s3_observation(db, task, "get_callback_transport_history", history)
    receiver = get_receiver_processing_fact(db, task["task_id"])
    assert receiver["facts"]["event_id"] == "event-second" and receiver["facts"]["status"] == "PROCESSED"
    sources = [{"fact_type":"s3_transport_history", "facts":history["facts"]},
               {"fact_type":"s3_receiver", "facts":receiver["facts"]}]
    response = {"action":"answer","result_state":"ANSWERED","answer":"状态说明", "target_event_id":"event-first", "processing_claim":"PROCESSED"}
    assert not supported_response(response, sources, [{"body":"event-first 完成了吗？"}])
    assert supported_response({**response,"processing_claim":"UNKNOWN"}, sources, [{"body":"event-first 完成了吗？"}])
    assert supported_response({**response,"target_event_id":"event-second"}, sources, [{"body":"event-second 完成了吗？"}])
    with pytest.raises(ScopeDenied):
        get_transport_history_fact(db, task["task_id"], "other-order-event")
    with connect(db) as c:
        with pytest.raises(sqlite3.IntegrityError):
            c.execute("UPDATE s3_transport_attempts SET http_status=200")
    with connect(db) as c:
        current, excluded = current_s3_evidence(c, task["task_id"], [observation["evidence_id"]], run_id=task["run_id"])
    assert len(current) == 1 and not excluded
    with connect(db) as c:
        c.execute("UPDATE principal_scope_grants SET granted_scopes_json='[]',grant_version=grant_version+1 WHERE principal_id='async-principal-a'")
    with pytest.raises(ScopeDenied):
        get_transport_history_fact(db, task["task_id"])
    with connect(db) as c:
        current, excluded = current_s3_evidence(c, task["task_id"], [observation["evidence_id"]], run_id=task["run_id"])
    assert not current and excluded


def test_vs03_snapshot_only_cannot_manufacture_transport_history(tmp_path):
    from opspilot.domain.s3_history import get_transport_history_fact
    db, _, task = _history_task(tmp_path, history_mode="snapshot_only")
    fact = get_transport_history_fact(db, task["task_id"], "event-first")
    assert fact["facts"]["attempts"] == []
    assert fact["facts"]["coverage"] == "RECORDED_OBSERVATIONS_ONLY"
    assert fact["facts"]["unknowns"]


def test_vs09_task_budget_is_persistent_and_not_reset_across_processes(tmp_path):
    from opspilot.domain.d2 import configure_s3_experiment_budget, task_attempt_limits, BudgetExhausted
    db, _, task = _history_task(tmp_path)
    configure_s3_experiment_budget(db, task["task_id"], 12, 8)
    model_limit = task_attempt_limits(db, task["task_id"])["MODEL"]
    for i in range(12):
        reserve_attempt(db, task["task_id"], "MODEL", model_limit, call_id=f"budget-{i}", run_id=task["run_id"])
    with pytest.raises(BudgetExhausted):
        reserve_attempt(db, task["task_id"], "MODEL", model_limit, call_id="over", run_id=task["run_id"])
    with pytest.raises(ValueError):
        configure_s3_experiment_budget(db, task["task_id"], 16, 10)
    child = subprocess.run([sys.executable, "-c",
        "import sys,json; from opspilot.domain.d2 import task_attempt_limits,attempt_counts; print(json.dumps([task_attempt_limits(sys.argv[1],sys.argv[2]),attempt_counts(sys.argv[1],sys.argv[2])]))",
        str(db), str(task["task_id"])], capture_output=True, text=True, check=True)
    limits, counts = json.loads(child.stdout)
    assert limits == {"MODEL":12,"MCP":8} and counts["MODEL"] == 12
    assert task_attempt_limits(db, task["task_id"]) == limits


def test_vs05_real_graph_continues_after_diagnosis_for_the_user_goal(tmp_path, monkeypatch):
    from opspilot.investigator import run_investigation
    from opspilot.domain.s3_history import prepare_transport_history_fixture
    from test_m4_03_s3 import _task
    db = tmp_path / "graph.sqlite3"
    reset_fixture(db, "S1_POS")
    prepare_transport_history_fixture(db, order_id="graph-order", attempts=[
        {"event_id":"graph-event", "http_status":503}, {"event_id":"graph-event", "http_status":202},
    ])
    _, task = _task(db, "graph-order", text="graph-event 上次失败后怎么样？请查实际回调历史。")
    responses = [AIMessage(content="",tool_calls=[{"id":f"tool-{n}","name":name,"args":{"reason":"verify actual facts"}}])
                 for n,name in enumerate(("get_order_status","get_callback_delivery","get_receiver_processing","get_callback_transport_history"))]
    responses.append(AIMessage(content=json.dumps({"action":"answer","result_state":"ANSWERED","answer":"graph-event 两次实际请求依次为 503 和 202，当前接收为 QUEUED，尚不能证明处理完成。",
                                                   "target_event_id":"graph-event","processing_claim":"QUEUED"},ensure_ascii=False)))
    model = Model(responses)
    monkeypatch.setattr("opspilot.investigator.ChatOpenAI", lambda **_kwargs:model)
    monkeypatch.setenv("OPSPILOT_MODEL_API_KEY","deterministic-no-provider")
    monkeypatch.setenv("OPSPILOT_MODEL_NAME","deterministic-no-provider")
    result = asyncio.run(run_investigation(str(task["task_id"]),"support-a",db_path=db,
                         checkpoint_db_path=tmp_path/"checkpoint.sqlite3",run_id=str(task["run_id"])))
    assert len(model.messages) == 5  # Gate is already DIAGNOSED after the third read, but the goal still needs history
    with connect(db) as c:
        tools = [row[0] for row in c.execute("SELECT tool_name FROM d2_tool_observations WHERE task_id=? ORDER BY rowid",(task["task_id"],))]
    assert tools[-1] == "get_callback_transport_history"
    assert result["graph_state"]["stage"] == "complete"


def test_vs06_candidate_modify_drop_and_execution_origin(tmp_path):
    db, task, run = _followup(tmp_path)
    node = _node(db, task, run, Model([]))
    candidates = [
        {"reference":"call-a|tool-a","tool_name":"search_callback_knowledge","arguments":{"query":"old","reason":"original"}},
        {"reference":"call-b|tool-b","tool_name":"get_receiver_processing","arguments":{"reason":"original"}},
        {"reference":"call-c|tool-c","tool_name":"get_order_status","arguments":{"reason":"original"}},
    ]
    draft = {"s3_remaining_candidates":candidates}
    node._last_candidates = []
    node._reconsider_candidates(draft,[{"id":"new-tool","name":"search_callback_knowledge","args":{"query":"new","reason":"refined after observation"}}],
                               json.dumps({"candidate_updates":[{"reference":"call-b|tool-b","decision":"DROP","reason":"not relevant to protocol question"}]}),False,"new-call")
    assert [item["reference"] for item in draft["s3_remaining_candidates"]] == ["call-c|tool-c"]
    assert [item["decision"] for item in draft["s3_candidate_decisions"]] == ["MODIFIED_SELECTION","DROP","KEEP"]
    assert draft["s3_candidate_decisions"][0]["decision_call_id"] == "new-call"
    assert draft["s3_candidate_decisions"][0]["selected_calls"][0]["arguments"]["query"] == "new"


def test_vs08_response_source_change_is_not_reused(tmp_path, monkeypatch):
    import shutil
    from opspilot.domain import s3_assets
    db, task, run = _followup(tmp_path)
    copied = tmp_path / "knowledge"
    shutil.copytree(s3_assets.DIRECTORY,copied)
    monkeypatch.setattr(s3_assets,"DIRECTORY",copied)
    doc = s3_assets.search_knowledge("receiver 202 queue",contract_version=2)[0]
    draft = {"s3_knowledge_refs":[{key:doc[key] for key in ("document_id","version","digest","source","valid_from")}]}
    model = Model([AIMessage(content="RESULT: ANSWERED\n这是旧协议的解释，来源随后将失效。")])
    node = _node(db, task, run, model)
    state = {"evidence_ids":[],"diagnosis_draft":draft}
    state.update(asyncio.run(node.investigate(state)))
    # Modify only the isolated asset copy after the actual model response.
    target = copied / "receiver-ack-contract-v2.md"
    target.write_text(target.read_text(encoding="utf-8")+"\nchanged after answer\n",encoding="utf-8")
    asyncio.run(node.report(state))
    with connect(db) as c:
        row = c.execute("SELECT answer_text,result_json FROM c1_readonly_followup_runs WHERE run_id=?",(run,)).fetchone()
    assert row[0] != "这是旧协议的解释，来源随后将失效。"
    assert json.loads(row[1])["delivery_mode"] == "DETERMINISTIC_FALLBACK"
    assert len(model.messages) == 1


def test_vs07_unproductive_provider_is_bounded_and_nonblank(tmp_path, monkeypatch):
    from opspilot.investigator import run_investigation
    from opspilot.domain.s3_history import prepare_transport_history_fixture
    from test_m4_03_s3 import _task
    db = tmp_path / "bounded.sqlite3"
    reset_fixture(db,"S1_POS")
    prepare_transport_history_fixture(db,order_id="bounded-order",attempts=[{"event_id":"bounded-event","http_status":202}])
    _, task = _task(db,"bounded-order",text="请核对当前回调状态。")
    class RepeatingModel(Model):
        async def ainvoke(self,messages):
            self.messages.append(messages)
            return AIMessage(content="",tool_calls=[{"id":f"repeat-{len(self.messages)}","name":"get_receiver_processing","args":{"reason":"same check"}}])
    model = RepeatingModel([])
    monkeypatch.setattr("opspilot.investigator.ChatOpenAI",lambda **_kwargs:model)
    monkeypatch.setenv("OPSPILOT_MODEL_API_KEY","deterministic-no-provider")
    monkeypatch.setenv("OPSPILOT_MODEL_NAME","deterministic-no-provider")
    result = asyncio.run(run_investigation(str(task["task_id"]),"support-a",db_path=db,
                         checkpoint_db_path=tmp_path/"checkpoint.sqlite3",run_id=str(task["run_id"])))
    counts = attempt_counts(db,task["task_id"])
    assert counts["MODEL"] == 8 and counts["MCP"] <= 6 and len(model.messages) == 8
    assert result["graph_state"]["stage"] == "complete"
    from opspilot.domain.chat import get_task_inspector
    from opspilot.domain.task_control import trusted_identity
    view=get_task_inspector(db,trusted_identity(db,"support-a"),str(task["task_id"]))
    replies=view.get("investigation_answers",[])
    assert replies and replies[-1]["answer_text"].strip(), "A frozen Diagnosis reference alone is not a usable user answer"
    assert replies[-1]["result"]["delivery_mode"] == "DETERMINISTIC_FALLBACK"


def test_vs04_history_refresh_does_not_borrow_another_run(tmp_path, monkeypatch):
    from datetime import datetime,timezone,timedelta
    from opspilot.domain import d2,s3
    from opspilot.domain.s3_history import get_transport_history_fact
    from opspilot.domain.task_control import finish_task_run
    from s3_observation_support import record_s3_observation
    db, identity, task = _history_task(tmp_path,receiver="QUEUED")
    clock=[datetime.now(timezone.utc)]
    monkeypatch.setattr(s3,"_now",lambda:clock[0])
    monkeypatch.setattr(d2,"utc_now",lambda:clock[0].isoformat().replace("+00:00","Z"))
    old = record_s3_observation(db,task,"get_callback_transport_history",get_transport_history_fact(db,task["task_id"]))
    from test_m4_03_s3 import _facts,_evidence
    from opspilot.domain.s3 import persist_s3_diagnosis,get_s3_outcome
    current_facts=_facts(db,task)
    ids=[old["evidence_id"]]+[_evidence(db,task,tool,fact) for tool,fact in zip(("get_order_status","get_callback_delivery","get_receiver_processing"),current_facts)]
    diagnosis=persist_s3_diagnosis(db,task["task_id"],task["run_id"],ids)
    finish_task_run(db,identity,task["run_id"],"SUCCEEDED")
    clock[0] += timedelta(seconds=301)
    _, new_run = _start_investigation_run(db,task["session_id"],task["task_id"],suffix="history-refresh")
    with connect(db) as c:
        accepted, excluded = s3.current_s3_evidence(c,task["task_id"],[old["evidence_id"]],run_id=new_run)
    assert not accepted and excluded
    new = record_s3_observation(db,{**task,"run_id":new_run},"get_callback_transport_history",get_transport_history_fact(db,task["task_id"]))
    assert new["observation_id"] != old["observation_id"] and new["evidence_id"] == old["evidence_id"]
    with connect(db) as c:
        accepted, excluded = s3.current_s3_evidence(c,task["task_id"],[new["evidence_id"]],run_id=new_run)
    assert accepted and not excluded
    assert get_s3_outcome(db,task["task_id"])["currentness"] != "CURRENT"
    with connect(db) as c:
        assert c.execute("SELECT digest FROM s3_diagnoses WHERE receipt_id=?",(diagnosis["receipt_id"],)).fetchone()[0] == diagnosis["digest"]


def test_vs01_transport_unknown_and_request_receipt_immutability(tmp_path):
    from opspilot.domain.s3_history import prepare_transport_history_fixture,_append
    db=tmp_path/"unknown.sqlite3"
    reset_fixture(db,"S1_POS")
    prep=prepare_transport_history_fixture(db,order_id="unknown-order",attempts=[{"event_id":"unknown-event","http_status":None}])
    record=prep["transport_trace"][0]["record"]
    assert record["result_kind"] == "OUTCOME_UNKNOWN" and record["http_status"] is None
    payload={key:value for key,value in record.items() if key!='content_digest'}
    with connect(db) as c:
        assert _append(c,payload)["content_digest"] == record["content_digest"]
        with pytest.raises(ValueError):
            _append(c,{**payload,"http_status":200})
        assert c.execute("SELECT COUNT(*) FROM s3_transport_attempts").fetchone()[0] == 1


def test_vs09_schema_v15_migration_preserves_existing_business(tmp_path):
    from opspilot.domain.database import initialize
    from opspilot.domain.d2 import task_attempt_limits
    db, _, task = _history_task(tmp_path)
    before=_business_only(db,task["task_id"])
    with connect(db) as c:
        c.execute("ALTER TABLE task_execution_budgets DROP COLUMN model_limit")
        c.execute("ALTER TABLE task_execution_budgets DROP COLUMN mcp_limit")
        c.execute("PRAGMA user_version=15")
    initialize(db)
    assert _business_only(db,task["task_id"]) == before
    assert task_attempt_limits(db,task["task_id"]) == {"MODEL":8,"MCP":6}
    with connect(db) as c:
        assert c.execute("PRAGMA user_version").fetchone()[0] == 16


def test_vs09_budget_exhaustion_delivers_explicit_nonblank_gap_without_writes(tmp_path):
    db, task, run = _followup(tmp_path)
    for i in range(8):
        reserve_attempt(db, task, "MODEL", 8, call_id=f"spent-{i}", run_id=run)
    model = Model([])
    node = _node(db, task, run, model)
    before = _business_only(db, task)
    asyncio.run(node.report({"evidence_ids": [], "tool_observations": []}))
    with connect(db) as c:
        row = c.execute("SELECT answer_text,result_state FROM c1_readonly_followup_runs WHERE run_id=?", (run,)).fetchone()
    assert row[0].strip(), "An empty PARTIAL does not answer the user or identify a concrete gap"
    assert row[1] in {"PARTIAL", "NOT_COMPLETED"}
    assert attempt_counts(db, task)["MODEL"] == 8
    assert model.messages == []
    assert _business_only(db, task) == before


def test_vs08_initial_delivery_survives_restart_and_enters_scoped_history(tmp_path):
    from opspilot.domain.investigation_context import load_investigation_context, load_prior_readonly_followups
    from opspilot.domain.s3_answers import persist_run_answer, answers_in_transaction
    from opspilot.domain.s3 import persist_s3_diagnosis
    from opspilot.domain.task_control import finish_task_run
    db, identity, task = _history_task(tmp_path)
    context=load_investigation_context(db,task["task_id"],task["run_id"])["task_run_control"]
    diagnosis=persist_s3_diagnosis(db,task["task_id"],task["run_id"],[])
    kwargs=dict(context=context,answer="尚未取得本轮接收状态，不能断言已经完成。",result_state="PARTIAL",
                source_refs=[],result={"delivery_mode":"DETERMINISTIC_FALLBACK"},report_ref=diagnosis["receipt_id"])
    original=persist_run_answer(db,task["task_id"],task["run_id"],**kwargs)
    assert persist_run_answer(db,task["task_id"],task["run_id"],**kwargs) == original
    with pytest.raises(ValueError,match="REPLAY_CONFLICT"):
        persist_run_answer(db,task["task_id"],task["run_id"],**{**kwargs,"answer":"different"})
    finish_task_run(db,identity,task["run_id"],"SUCCEEDED")
    with connect(db) as c:
        last=c.execute("SELECT MAX(sequence) FROM messages WHERE session_id=?",(task["session_id"],)).fetchone()[0]
        histories,excluded=load_prior_readonly_followups(c,tenant_id="tenant-a",session_id=task["session_id"],task_id=task["task_id"],before_sequence=last+1)
        assert histories and histories[0]["answer_text"] == original["answer_text"] and not excluded
        assert histories[0]["run_id"] == task["run_id"]
        assert not load_prior_readonly_followups(c,tenant_id="tenant-b",session_id=task["session_id"],task_id=task["task_id"],before_sequence=last+1)[0]
        assert not load_prior_readonly_followups(c,tenant_id="tenant-a",session_id="wrong-session",task_id=task["task_id"],before_sequence=last+1)[0]
        with pytest.raises(sqlite3.IntegrityError):
            c.execute("UPDATE s3_run_answers SET digest='changed'")
    child=subprocess.run([sys.executable,"-c","import sys,json; from opspilot.domain.database import connect; from opspilot.domain.s3_answers import answers_in_transaction;\nwith connect(sys.argv[1]) as c: print(json.dumps(answers_in_transaction(c,sys.argv[2])))",str(db),task["task_id"]],capture_output=True,text=True,encoding="utf-8",check=True)
    assert json.loads(child.stdout)[0]["answer_text"] == original["answer_text"]
    with connect(db) as c:
        c.execute("UPDATE principal_scope_grants SET granted_scopes_json='[]',grant_version=grant_version+1 WHERE principal_id='async-principal-a'")
    with connect(db) as c:
        assert not answers_in_transaction(c,task["task_id"])
        histories,excluded=load_prior_readonly_followups(c,tenant_id="tenant-a",session_id=task["session_id"],task_id=task["task_id"],before_sequence=last+1)
        assert not histories and excluded[0]["reason"] == "CURRENT_S3_AUTHORIZATION_UNAVAILABLE"


def test_vs01_history_is_bounded_and_repeat_sends_keep_event_identity(tmp_path):
    from opspilot.domain.s3_history import prepare_transport_history_fixture,get_transport_history_fact
    db=tmp_path/"many.sqlite3"
    reset_fixture(db,"S1_POS")
    prepare_transport_history_fixture(db,order_id="many",attempts=[{"event_id":"stable-event","http_status":503}]*10)
    prepare_transport_history_fixture(db,order_id="many",attempts=[{"event_id":"stable-event","http_status":202}]*4)
    from test_m4_03_s3 import _task
    _,task=_task(db,"many")
    rows=get_transport_history_fact(db,task["task_id"])["facts"]
    assert len(rows["attempts"]) == 12 and rows["truncated"] is True
    assert [item["attempt_no"] for item in rows["attempts"]] == list(range(3,15))
    assert len({item["order_version"] for item in rows["attempts"]}) == 1


def test_vs10_experiment_caps_and_opaque_ids_do_not_leak_gold(tmp_path):
    from opspilot.smokes.m4_continuous import ProviderMeter,render_case,export_trace
    from langchain_core.messages import HumanMessage
    meter=ProviderMeter(tmp_path/"provider.jsonl")
    model=SimpleNamespace(model_name="deterministic-no-provider",max_tokens=512)
    request=meter.begin(model,[HumanMessage(content="ordinary question")],{})
    meter.end(request,AIMessage(content="test",usage_metadata={"input_tokens":10,"output_tokens":2,"total_tokens":12}))
    assert meter.rows()[1]["estimated_peak_usd"] == pytest.approx(5.4e-6)
    meter.append({"event":"RESERVE","reserved_usd":3})
    with pytest.raises(RuntimeError,match="CAP_REACHED"):
        meter.begin(model,[HumanMessage(content="another question")],{})
    logical={"case_id":"DO_NOT_SEND_THIS_GOLD_LABEL","order_id":"label-order","target_event_id":"label-event",
             "attempts":[{"event_id":"label-event","http_status":202}],"message":"查回调经过", "current_receiver_status":"QUEUED","expected":{"secret_label":"ANSWER"}}
    rendered=render_case(logical)
    assert "DO_NOT_SEND" not in json.dumps(rendered) and "secret_label" not in json.dumps(rendered)
    assert rendered["order_id"].startswith("order-") and rendered["order_id"] != logical["order_id"]
    db,_,task=_history_task(tmp_path)
    traced=export_trace(db,task["task_id"])
    assert traced["task_runs"][0]["run_id"] == task["run_id"] and len(traced["transport"]) == 2
