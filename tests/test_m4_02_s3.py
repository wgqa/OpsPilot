from __future__ import annotations

import copy
import json
import threading
from pathlib import Path

import pytest


def prepared(tmp_path: Path, state: str = "DELIVERY_FAILED"):
    from opspilot.domain.s3 import prepare_s3_fixture
    from opspilot.domain.database import reset_fixture
    from opspilot.domain.task_control import create_session, create_task_with_initial_run, trusted_identity

    db = tmp_path / "s3.sqlite3"
    reset_fixture(db, "S1_POS")
    setup = prepare_s3_fixture(db, state)
    identity = trusted_identity(db, "support-a")
    session = create_session(db, identity)
    task = create_task_with_initial_run(
        db, identity, session_id=str(session["session_id"]), service_id="orders-async-demo",
        integration_id="async-integration-a", ticket_id="S3-LOCAL",
        initial_message="订单接口返回 200，但下游没有收到异步回调。", idempotency_key="s3-create",
    )
    return db, task, setup


def observe(db, task, tool, result):
    from opspilot.domain.d2 import record_tool_observation
    return record_tool_observation(
        db, task_id=task["task_id"], call_id="test-call", attempt_id=None,
        tool_call_id=tool, tool_name=tool, arguments={}, status="OK", result=result,
    )["evidence_id"]


def facts(db, task):
    from opspilot.domain.api import make_server
    from opspilot.domain.s3 import get_order_status_fact, get_callback_delivery_fact, get_receiver_processing_fact
    server = make_server(db, "tenant-a", "127.0.0.1", 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        order = get_order_status_fact(db, task["task_id"], f"http://127.0.0.1:{server.server_port}")
        delivery = get_callback_delivery_fact(db, task["task_id"])
        receiver = get_receiver_processing_fact(db, task["task_id"])
        return order, delivery, receiver
    finally:
        server.shutdown()
        thread.join()
        server.server_close()


@pytest.mark.parametrize("state,outcome", [
    ("PROCESSING", "ORDER_PROCESSING"),
    ("DELIVERY_FAILED", "CALLBACK_DELIVERY_FAILED"),
    ("DELIVERED_PENDING", "RECEIVER_PROCESSING_UNCONFIRMED"),
])
def test_three_current_factual_outcomes(tmp_path, state, outcome):
    from opspilot.domain.s3 import evaluate_s3_gate
    db, task, setup = prepared(tmp_path, state)
    order, delivery, receiver = facts(db, task)
    ids = [observe(db, task, name, fact) for name, fact in zip(
        ("get_order_status", "get_callback_delivery", "get_receiver_processing"), (order, delivery, receiver),
    )]
    gate = evaluate_s3_gate(db, task["task_id"], ids)
    assert gate["outcome"] == outcome
    assert gate["recovered"] is False
    assert order["facts"]["http_status"] == 200
    assert setup["agent_actions"] == []
    assert setup["receiver_http_status"] == {"PROCESSING": None, "DELIVERY_FAILED":503, "DELIVERED_PENDING":202}[state]


def test_processing_does_not_require_callback_reads(tmp_path):
    from opspilot.domain.s3 import evaluate_s3_gate
    db, task, _ = prepared(tmp_path, "PROCESSING")
    order, _, _ = facts(db, task)
    gate = evaluate_s3_gate(db, task["task_id"], [observe(db, task, "get_order_status", order)])
    assert gate["outcome"] == "ORDER_PROCESSING"


def test_completed_needs_correlated_delivery_and_receiver(tmp_path):
    from opspilot.domain.s3 import evaluate_s3_gate
    db, task, _ = prepared(tmp_path, "DELIVERED_PENDING")
    order, delivery, receiver = facts(db, task)
    ids = [observe(db, task, "get_order_status", order)]
    assert evaluate_s3_gate(db, task["task_id"], ids)["decision"] == "NEED_MORE"
    ids.append(observe(db, task, "get_callback_delivery", delivery))
    assert evaluate_s3_gate(db, task["task_id"], ids)["decision"] == "NEED_MORE"
    receiver["facts"]["event_id"] = "forged-event"
    ids.append(observe(db, task, "get_receiver_processing", receiver))
    assert evaluate_s3_gate(db, task["task_id"], ids)["decision"] != "DIAGNOSED"


def test_version_change_and_forged_evidence_excluded(tmp_path):
    from opspilot.domain.database import connect
    from opspilot.domain.s3 import evaluate_s3_gate, current_s3_evidence
    db, task, _ = prepared(tmp_path)
    order, delivery, _ = facts(db, task)
    ids = [observe(db, task, "get_order_status", order), observe(db, task, "get_callback_delivery", delivery)]
    assert evaluate_s3_gate(db, task["task_id"], ids)["decision"] == "DIAGNOSED"
    with connect(db) as c:
        c.execute("UPDATE s3_orders SET version=version+1 WHERE tenant_id='tenant-a'")
    with connect(db) as c:
        current, excluded = current_s3_evidence(c, task["task_id"])
    assert not current
    assert any(x["reason"] == "S3_CURRENT_VERSION_MISMATCH" for x in excluded)
    assert evaluate_s3_gate(db, task["task_id"], ids)["decision"] != "DIAGNOSED"


def test_task_binding_scope_and_no_write_tools(tmp_path):
    from opspilot.domain.database import connect
    from opspilot.domain.d2 import ScopeDenied
    from opspilot.domain.s3 import get_callback_delivery_fact, get_s3_binding
    db, task, _ = prepared(tmp_path)
    with connect(db) as c:
        c.execute("UPDATE task_bindings SET integration_id='integration-a' WHERE task_id=?", (task["task_id"],))
    with pytest.raises(ScopeDenied):
        get_callback_delivery_fact(db, task["task_id"])


def test_knowledge_is_retrieved_and_expired_filtered(tmp_path):
    from opspilot.domain.s3_assets import search_knowledge, load_s3_skill
    hits = search_knowledge("202 receiver acknowledgement processing")
    assert hits and hits[0]["document_id"] == "callback-ack-contract"
    assert all(x["source"] and x["digest"] and x["version"] for x in hits)
    skill = load_s3_skill("callback-delivery-triage")
    assert "content" in skill
    with pytest.raises(ValueError):
        load_s3_skill("arbitrary-scope-writer")


def completed_readonly_case(tmp_path, state="DELIVERY_FAILED"):
    from opspilot.domain.task_control import claim_task_run, apply_pending_critical_inputs, trusted_identity
    from opspilot.domain.s3 import persist_s3_diagnosis
    db, task, _ = prepared(tmp_path,state)
    identity=trusted_identity(db,"support-a")
    claim_task_run(db,identity,task["run_id"])
    apply_pending_critical_inputs(db,identity,task["run_id"])
    values=facts(db,task)
    ids=[observe(db,task,name,value) for name,value in zip(("get_order_status","get_callback_delivery","get_receiver_processing"),values)]
    receipt=persist_s3_diagnosis(db,task["task_id"],task["run_id"],ids)
    return db,task,ids,receipt


def test_diagnosis_outbox_idempotence_and_no_business_authority(tmp_path):
    from opspilot.domain.database import connect
    from opspilot.domain.s3 import persist_s3_diagnosis
    from opspilot.domain.task_control import finish_task_run,trusted_identity
    db,task,ids,receipt=completed_readonly_case(tmp_path)
    replay=persist_s3_diagnosis(db,task["task_id"],task["run_id"],ids)
    assert receipt["receipt_id"] == replay["receipt_id"]
    finish_task_run(db,trusted_identity(db,"support-a"),task["run_id"],"SUCCEEDED")
    with connect(db) as c:
        assert c.execute("SELECT COUNT(*) FROM s3_diagnoses").fetchone()[0] == 1
        assert c.execute("SELECT COUNT(*) FROM domain_outbox WHERE event_kind='S3_DIAGNOSIS_FROZEN'").fetchone()[0] == 1
        assert c.execute("SELECT status FROM task_bindings WHERE task_id=?",(task["task_id"],)).fetchone()[0] == "WAITING_HANDOFF"
        for table in ("d3_plans","d3_action_intents","d3_action_ledgers","s2_handoff_receipts"):
            assert c.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0
        with pytest.raises(__import__('sqlite3').IntegrityError):
            c.execute("UPDATE s3_diagnoses SET outcome='ORDER_PROCESSING'")


def test_abort_prevents_frozen_diagnosis(tmp_path):
    from opspilot.domain.task_control import abort_task, claim_task_run, trusted_identity, TaskControlError
    from opspilot.domain.s3 import persist_s3_diagnosis
    from opspilot.domain.database import connect
    db,task,_=prepared(tmp_path)
    identity=trusted_identity(db,"support-a")
    claim_task_run(db,identity,task["run_id"])
    abort_task(db,identity,task_id=task["task_id"],reason="stop",idempotency_key="abort-s3")
    with pytest.raises(TaskControlError):
        persist_s3_diagnosis(db,task["task_id"],task["run_id"],[])
    with connect(db) as c:
        assert c.execute("SELECT COUNT(*) FROM s3_diagnoses").fetchone()[0] == 0


def test_receipt_and_outbox_roll_back_together(tmp_path):
    from opspilot.domain.task_control import claim_task_run,trusted_identity
    from opspilot.domain.s3 import persist_s3_diagnosis
    from opspilot.domain.database import connect
    db,task,_=prepared(tmp_path,"PROCESSING")
    claim_task_run(db,trusted_identity(db,"support-a"),task["run_id"])
    order,_,_=facts(db,task)
    ids=[observe(db,task,"get_order_status",order)]
    with connect(db) as c:
        c.execute("CREATE TRIGGER test_s3_outbox_failure BEFORE INSERT ON domain_outbox WHEN NEW.event_kind='S3_DIAGNOSIS_FROZEN' BEGIN SELECT RAISE(ABORT,'injected outbox fault'); END")
    with pytest.raises(__import__('sqlite3').IntegrityError):
        persist_s3_diagnosis(db,task["task_id"],task["run_id"],ids)
    with connect(db) as c:
        assert c.execute("SELECT COUNT(*) FROM s3_diagnoses").fetchone()[0] == 0
        c.execute("DROP TRIGGER test_s3_outbox_failure")
    assert persist_s3_diagnosis(db,task["task_id"],task["run_id"],ids)["outcome"] == "ORDER_PROCESSING"


def test_s3_web_owner_cross_tenant_and_resource_body_permissions(tmp_path):
    from fastapi.testclient import TestClient
    from opspilot.web.app import create_app
    from opspilot.domain.s3 import prepare_s3_fixture
    from test_m4_01_dialogue_updates import PASSWORDS,_login
    db,_,_=prepared(tmp_path)
    prepare_s3_fixture(db,"PROCESSING",tenant_id="tenant-b")
    app=create_app(db_path=db,start_worker=False,credentials=PASSWORDS,expected_origin="http://testserver")
    with TestClient(app,raise_server_exceptions=False) as client:
        headers=_login(client)
        session=client.post("/api/sessions",headers=headers).json()["session_id"]
        body={"initial_message":"订单200没有回调","investigation_kind":"ASYNC_CALLBACK","s3_order_id":"async-order"}
        accepted=client.post(f"/api/sessions/{session}/tasks",headers={**headers,"Idempotency-Key":"s3-web"},json=body)
        assert accepted.status_code == 202
        task_id=accepted.json()["task_id"]
        replay=client.post(f"/api/sessions/{session}/tasks",headers={**headers,"Idempotency-Key":"s3-web"},json=body)
        assert replay.status_code == 200 and replay.json()["task_id"] == task_id
        invalid=client.post(f"/api/sessions/{session}/tasks",headers={**headers,"Idempotency-Key":"forged-resource"},json={**body,"integration_id":"async-integration-b"})
        assert invalid.status_code == 422
        _login(client,"support-b")
        assert client.get(f"/api/tasks/{task_id}/inspector").status_code in {403,404}


def test_forged_http_payload_cannot_pass_even_with_recomputed_digest(tmp_path):
    from opspilot.domain.s3 import evaluate_s3_gate
    db,task,_=prepared(tmp_path,"PROCESSING")
    order,_,_=facts(db,task)
    order["facts"]["body"]["status"]="COMPLETED"
    evidence_id=observe(db,task,"get_order_status",order)
    gate=evaluate_s3_gate(db,task["task_id"],[evidence_id])
    assert gate["decision"] != "DIAGNOSED"
    assert gate["excluded_sources"][0]["reason"] == "S3_HTTP_OBSERVATION_INVALID"


def test_s3_chat_currentness_invalidates_previous_facts(tmp_path):
    from opspilot.domain.chat import _current_evidence, _current_task_state
    from opspilot.domain.database import connect
    from opspilot.domain.s3 import prepare_s3_fixture
    db,task,_,_=completed_readonly_case(tmp_path)
    with connect(db) as c:
        state=_current_task_state(c,task["task_id"])
        assert _current_evidence(c,task["task_id"],state)
    prepare_s3_fixture(db,"DELIVERY_FAILED")
    with connect(db) as c:
        state=_current_task_state(c,task["task_id"])
        excluded=[]
        assert _current_evidence(c,task["task_id"],state,excluded_sources=excluded) == []
        assert state["s3_outcome"]["currentness"] == "INVALIDATED_BY_CURRENT_FACTS"
        assert any(x["reason"] == "S3_CURRENT_VERSION_MISMATCH" for x in excluded)


def test_real_case_memory_is_separate_and_revocation_reloads_current_db(tmp_path):
    from opspilot.domain.episodic_memory import create_memory_candidate,confirm_memory,revoke_memory,select_applicable_memories,get_task_memory_context
    from opspilot.smokes.m4_02 import task as new_task
    from opspilot.domain.s3 import prepare_s3_fixture,PROBLEM
    from opspilot.domain.task_control import claim_task_run,apply_pending_critical_inputs,trusted_identity
    from opspilot.s3_investigation import S3Nodes
    db,source,_,_=completed_readonly_case(tmp_path)
    candidate=create_memory_candidate(db,source["task_id"],"support-a")
    assert candidate["source_outcome"] == "DIAGNOSED"
    assert candidate["source_report_ref"] is None and candidate["source_verification_id"] is None
    confirm_memory(db,candidate["memory_id"],"approver-a")
    prepare_s3_fixture(db,"PROCESSING")
    target=new_task(db,"仍然200没有回调","target-b")
    identity=trusted_identity(db,"support-a")
    claim_task_run(db,identity,target["run_id"])
    apply_pending_critical_inputs(db,identity,target["run_id"])
    nodes=S3Nodes(db,target["task_id"],target["run_id"],None,"test-model",None,[])
    _,metadata=nodes.prompt({"evidence_ids":[],"diagnosis_draft":{}})
    assert metadata["selected_memories"][0]["source_task_id"] == source["task_id"] != target["task_id"]
    assert get_task_memory_context(db,target["task_id"],"support-a")["applicable_memories"][0]["memory_id"] == candidate["memory_id"]
    assert not metadata["evidence_ids"]
    revoke_memory(db,candidate["memory_id"],"approver-a")
    _,after=nodes.prompt({"evidence_ids":[],"diagnosis_draft":{}})
    assert after["selected_memories"] == []
    assert get_task_memory_context(db,target["task_id"],"support-a")["applicable_memories"] == []
    assert any(x["reason"] == "MEMORY_REVOKED" for x in after["excluded_sources"])


def test_knowledge_reference_expiry_does_not_reinject_checkpoint_text(tmp_path,monkeypatch):
    import shutil
    from opspilot.domain import s3_assets
    directory=tmp_path/"knowledge"
    shutil.copytree(s3_assets.DIRECTORY,directory)
    monkeypatch.setattr(s3_assets,"DIRECTORY",directory)
    selected=s3_assets.search_knowledge("202 acknowledgement")[0]
    refs={k:selected[k] for k in ("document_id","version","digest","source","valid_from")}
    draft={"s3_knowledge_refs":[refs]}
    assert s3_assets.refresh_asset_refs(draft)[0]
    path=directory/"manifest.json"
    manifest=json.loads(path.read_text(encoding="utf-8"))
    for item in manifest["documents"]:
        item["expires_at"]="2000-01-01T00:00:00+00:00"
    path.write_text(json.dumps(manifest),encoding="utf-8")
    knowledge,_,excluded=s3_assets.refresh_asset_refs(draft)
    assert not knowledge
    assert excluded[0]["reason"] == "KNOWLEDGE_REMOVED_EXPIRED_OR_CHANGED"


def test_live_mcp_stdio_rejects_extra_resource_and_binding_tenant_mutation(tmp_path):
    import asyncio,sys
    from mcp import Client,StdioServerParameters
    from opspilot.config import ROOT
    from opspilot.investigator import _mcp_child_environment
    from opspilot.domain.database import connect
    from opspilot.domain.s3_mcp import TOOLS
    db,task,_=prepared(tmp_path)
    async def check():
        params=StdioServerParameters(command=sys.executable,args=["-m","opspilot.mcp_server","--db",str(db),"--binding-id",task["task_id"]],cwd=str(ROOT),env=_mcp_child_environment(db))
        async with Client(params) as client:
            catalog=await client.list_tools()
            assert {x.name for x in catalog.tools} == TOOLS
            for name in ("get_order_status","get_callback_delivery"):
                bad=await client.call_tool(name,{"reason":"check","tenant_id":"tenant-b","order_id":"foreign-order"})
                assert bad.is_error
            good=await client.call_tool("search_callback_knowledge",{"reason":"check ACK contract","query":"202 acknowledgement"})
            assert not good.is_error
            with connect(db) as c, pytest.raises(__import__('sqlite3').IntegrityError):
                c.execute("UPDATE task_bindings SET tenant_id='tenant-b' WHERE task_id=?",(task["task_id"],))
            denied=await client.call_tool("get_callback_delivery",{"reason":"read foreign event","task_id":"foreign-task"})
            assert denied.is_error
    asyncio.run(check())


def test_parallel_provider_proposals_are_recorded_but_only_one_is_dispatchable(tmp_path):
    import asyncio
    from langchain_core.messages import AIMessage
    from opspilot.domain.task_control import claim_task_run,trusted_identity
    from opspilot.domain.database import connect
    from opspilot.s3_investigation import S3Nodes
    db,task,_=prepared(tmp_path)
    claim_task_run(db,trusted_identity(db,"support-a"),task["run_id"])
    class DeliberatelyParallelModel:
        def bind_tools(self,*_args,**_kwargs): return self
        async def ainvoke(self,_messages):
            return AIMessage(content="unit test: two proposals",id="unit-test-only",tool_calls=[
                {"id":"unit-order","name":"get_order_status","args":{"reason":"check lifecycle"}},
                {"id":"unit-delivery","name":"get_callback_delivery","args":{"reason":"check event"}},
            ])
    nodes=S3Nodes(db,task["task_id"],task["run_id"],DeliberatelyParallelModel(),"unit-test-model",None,[])
    result=asyncio.run(nodes.investigate({"evidence_ids":[],"diagnosis_draft":{}}))
    assert len(result["pending_call_refs"]) == 1
    with connect(db) as c:
        statuses={row["tool_call_id"]:row["status"] for row in c.execute("SELECT * FROM d2_pending_tool_calls")}
        assert statuses == {"unit-order":"PENDING","unit-delivery":"NOT_SENT_RECONSIDER_AFTER_OBSERVATION"}
        assert c.execute("SELECT status FROM d2_model_traces").fetchone()[0] == "PARALLEL_TOOL_CALLS_REDUCED_TO_ONE"


def test_no_tool_and_budget_exhaustion_stop_without_business_writes(tmp_path):
    import asyncio
    from langchain_core.messages import AIMessage
    from opspilot.domain.task_control import claim_task_run,trusted_identity
    from opspilot.domain.d2 import reserve_attempt
    from opspilot.domain.s3 import get_s3_outcome
    from opspilot.s3_investigation import S3Nodes
    db,task,_=prepared(tmp_path)
    claim_task_run(db,trusted_identity(db,"support-a"),task["run_id"])
    class ClarifyingModel:
        def bind_tools(self,*_args,**_kwargs): return self
        async def ainvoke(self,_messages): return AIMessage(content="unit-test clarification: what did the receiver observe?")
    nodes=S3Nodes(db,task["task_id"],task["run_id"],ClarifyingModel(),"unit-test-model",None,[])
    state=asyncio.run(nodes.investigate({"evidence_ids":[],"diagnosis_draft":{}}))
    assert state["last_investigation_action"] == "MODEL_NO_TOOL"
    for index in range(7):
        reserve_attempt(db,task["task_id"],"MODEL",8,call_id=f"unit-budget-{index}",run_id=task["run_id"])
    assert asyncio.run(nodes.investigate(state))["last_investigation_action"] == "BUDGET_EXHAUSTED"
    asyncio.run(nodes.report(state))
    assert get_s3_outcome(db,task["task_id"])["outcome"] == "INCONCLUSIVE"


def test_revoked_memory_invalidates_frozen_model_explanation_not_current_facts(tmp_path):
    import asyncio
    from langchain_core.messages import AIMessage
    from opspilot.domain.episodic_memory import create_memory_candidate,confirm_memory,revoke_memory
    from opspilot.domain.s3 import prepare_s3_fixture,get_s3_outcome
    from opspilot.domain.task_control import claim_task_run,trusted_identity
    from opspilot.smokes.m4_02 import task as new_task
    from opspilot.s3_investigation import S3Nodes
    db,source,_,_=completed_readonly_case(tmp_path)
    memory=create_memory_candidate(db,source["task_id"],"support-a")
    confirm_memory(db,memory["memory_id"],"approver-a")
    prepare_s3_fixture(db,"DELIVERY_FAILED", attempt_count=3, retry_state="EXHAUSTED")
    target=new_task(db,"订单还没有回调，请核实","explanation-target")
    claim_task_run(db,trusted_identity(db,"support-a"),target["run_id"])
    order,delivery,_=facts(db,target)
    ids=[observe(db,target,"get_order_status",order),observe(db,target,"get_callback_delivery",delivery)]
    class ExplanationModel:
        async def ainvoke(self,_messages):
            return AIMessage(content="unit-test historical-method-dependent explanation",id="unit-explanation")
    nodes=S3Nodes(db,target["task_id"],target["run_id"],ExplanationModel(),"unit-model",None,[])
    asyncio.run(nodes.report({"evidence_ids":ids,"diagnosis_draft":{}}))
    assert get_s3_outcome(db,target["task_id"])["explanation"]
    revoke_memory(db,memory["memory_id"],"approver-a")
    after=get_s3_outcome(db,target["task_id"])
    assert after["outcome"] == "CALLBACK_DELIVERY_FAILED"
    assert after["explanation"] == ""
    assert after["explanation_currentness"] == "SOURCE_INVALIDATED"


def test_expired_knowledge_invalidates_frozen_explanation_not_current_facts(tmp_path,monkeypatch):
    import asyncio,shutil
    from langchain_core.messages import AIMessage
    from opspilot.domain import s3_assets
    from opspilot.domain.s3 import get_s3_outcome
    from opspilot.domain.task_control import claim_task_run,trusted_identity
    from opspilot.s3_investigation import S3Nodes
    from opspilot.domain.database import connect
    directory=tmp_path/"knowledge-copy"
    shutil.copytree(s3_assets.DIRECTORY,directory)
    monkeypatch.setattr(s3_assets,"DIRECTORY",directory)
    doc=s3_assets.search_knowledge("order callback processing lifecycle")[0]
    db,task,_=prepared(tmp_path,"PROCESSING")
    claim_task_run(db,trusted_identity(db,"support-a"),task["run_id"])
    order,_,_=facts(db,task)
    ids=[observe(db,task,"get_order_status",order)]
    class ExplanationModel:
        async def ainvoke(self,_messages): return AIMessage(content="unit-test knowledge-dependent explanation",id="unit-knowledge-explanation")
    nodes=S3Nodes(db,task["task_id"],task["run_id"],ExplanationModel(),"unit-model",None,[])
    state={"evidence_ids":ids,"diagnosis_draft":{"s3_knowledge_refs":[{k:doc[k] for k in ("document_id","version","digest","source","valid_from")}]}}
    asyncio.run(nodes.report(state))
    assert get_s3_outcome(db,task["task_id"])["explanation"]
    manifest_path=directory/"manifest.json"
    manifest=json.loads(manifest_path.read_text(encoding="utf-8"))
    for item in manifest["documents"]: item["expires_at"]="2000-01-01T00:00:00+00:00"
    manifest_path.write_text(json.dumps(manifest),encoding="utf-8")
    outcome=get_s3_outcome(db,task["task_id"])
    assert outcome["outcome"] == "ORDER_PROCESSING" and not outcome["explanation"]
    assert any(x["reason"] == "EXPLANATION_KNOWLEDGE_INVALIDATED" for x in outcome["explanation_excluded_sources"])
