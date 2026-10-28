from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
import json
import os
from pathlib import Path

import pytest
from mcp import Client
from langchain_core.messages import AIMessage

from experiments.ar01_free_agent.agent import Candidate, Limits, sanitize
from experiments.ar01_free_agent.harness import (
    mcp_params,new_task,prepare_seed,run_pair,snapshot,PROTECTED,
)
from experiments.ar01_free_agent.simulation import LocalModel,call,answer
from opspilot.domain.database import connect
from opspilot.domain.d2 import attempt_counts, list_model_traces, list_observations, canonical_json
from opspilot.s3_investigation import s3_catalog


@pytest.fixture
def setup(tmp_path):
    db=tmp_path/"domain.sqlite3"
    prepare_seed(db,{"state":"PROCESSING","outside_event":"event-outside"})
    return db,new_task(db,"现在绑定订单是什么状态？")


@asynccontextmanager
async def candidate_context(setup, **options):
    db,task=setup
    async with Client(mcp_params(db,task)) as client:
        _,specs=s3_catalog((await client.list_tools()).tools)
        candidate=Candidate(db,task["task_id"],task["run_id"],client,specs,**options)
        try:
            yield candidate,client
        finally:
            destination=os.environ.get("AR01_TEST_TRACE_DIR")
            if destination:
                directory=Path(destination)
                directory.mkdir(parents=True,exist_ok=True)
                candidate.trace.emit("test_ledger",task_id=task["task_id"],run_id=task["run_id"],
                    observations=list_observations(db,task["task_id"]),model_traces=list_model_traces(db,task["task_id"]))
                with (directory/f"{db.parent.name}.jsonl").open("x",encoding="utf-8") as output:
                    for row in candidate.trace.rows: output.write(canonical_json(row)+"\n")


def sequence(*responses):
    items=iter(responses)
    return LocalModel(policy=lambda _messages:next(items))


def test_pair_equivalent_facts_and_exact_actual_model_tools(tmp_path):
    case={"id":"AR01-02","variant":"unit","question":"现在订单是什么状态？","setup":{"state":"PROCESSING"}}
    result=asyncio.run(run_pair(case,tmp_path/"pair"))
    a,b=result["groups"]
    assert a["initial_business_digest"]==b["initial_business_digest"]
    assert a["actual_outbound_tool_schema_digest"]==b["actual_outbound_tool_schema_digest"]
    for group in (a,b):
        assert group["business_state_unchanged"]
        assert "PROCESSING" in group["result"]["answer"]
        assert "get_order_status" in group["tool_names"]


def test_direct_answer_and_clarification_need_no_tools(setup):
    async def check():
        async with candidate_context(setup) as (candidate,_):
            model=sequence(answer("HTTP受理与业务完成不同。"),answer("您指哪个事件？",clarify=True))
            first=await candidate.run(model,"已有资料足够，解释概念。")
            second=await candidate.run(model,"哪个事件？",history=first["messages"])
            assert first["result"]["result_state"]=="ANSWERED"
            assert second["result"]["action"]=="clarify"
            assert attempt_counts(candidate.db,candidate.task)=={"MODEL":2,"MCP":0}
            assert len(model.requests)==2
            with connect(candidate.db) as c:
                statuses=[r[0] for r in c.execute("SELECT model_status FROM d5_context_provenance WHERE task_id=?",(candidate.task,))]
            assert statuses==["OK","OK"]
            assert any("HTTP受理" in str(m.content) for m in model.requests[-1])
    asyncio.run(check())


def test_pronoun_continuation_and_reordered_questions_retain_budget(setup):
    async def check():
        async with candidate_context(setup) as (candidate,_):
            model=LocalModel()
            one=await candidate.run(model,"订单目前处理到哪一步？")
            before=attempt_counts(candidate.db,candidate.task)
            two=await candidate.run(model,"刚才说的处理完成和受理有什么区别？",history=one["messages"])
            assert two["result"]["answer"]
            assert attempt_counts(candidate.db,candidate.task)=={"MODEL":before["MODEL"]+1,"MCP":before["MCP"]}
            assert any(m.type=="tool" for m in model.requests[-1])
    asyncio.run(check())


def test_scope_denial_and_same_scope_positive_through_real_mcp(setup):
    async def check():
        async with candidate_context(setup) as (candidate,client):
            outside=await client.call_tool("get_callback_transport_history",{"reason":"test scope","event_id":"event-outside"})
            forged=await client.call_tool("get_order_status",{"reason":"test scope","tenant_id":"tenant-b","order_id":"ar01-outside-order"})
            good=await client.call_tool("get_order_status",{"reason":"legal bound order"})
            assert outside.is_error and forged.is_error and not good.is_error
            model=sequence(call("get_order_status",tenant_id="tenant-b",order_id="ar01-outside-order"),
                call("get_order_status"),answer("越域请求被拒绝；合法本订单仍在处理中。",partial=True))
            result=await candidate.run(model,"先越域，再查本订单")
            assert "ar01-outside-order" not in result["result"]["answer"]
            assert any(r["event"]=="tool_error" for r in result["trace"])
            assert any(r["event"]=="tool_result" for r in result["trace"])
    asyncio.run(check())


def test_scope_revoked_before_dispatch_no_model_or_fact(setup):
    async def check():
        async with candidate_context(setup) as (candidate,_):
            with connect(candidate.db) as c:
                c.execute("UPDATE principal_scope_grants SET granted_scopes_json='[]',grant_version=grant_version+1 WHERE principal_id='async-principal-a'")
            model=LocalModel()
            result=await candidate.run(model,"当前订单状态？")
            assert not model.requests
            assert result["result"]["result_state"]=="PARTIAL"
            assert result["result"]["answer"]
    asyncio.run(check())


def test_scope_revoke_after_observation_stops_history_then_fresh_reauthorization_works(setup):
    async def check():
        async with candidate_context(setup) as (candidate,client):
            model=LocalModel()
            first=await candidate.run(model,"当前订单状态？")
            used=len(model.requests)
            with connect(candidate.db) as c:
                old=c.execute("SELECT granted_scopes_json FROM principal_scope_grants WHERE principal_id='async-principal-a'").fetchone()[0]
                c.execute("UPDATE principal_scope_grants SET granted_scopes_json='[]',grant_version=grant_version+1 WHERE principal_id='async-principal-a'")
            denied=await candidate.run(model,"现在呢？",history=first["messages"])
            assert len(model.requests)==used and denied["result"]["result_state"]=="PARTIAL"
            assert all(eid not in denied["result"]["answer"] for eid in candidate.evidence_ids)
            with connect(candidate.db) as c:
                c.execute("UPDATE principal_scope_grants SET granted_scopes_json=?,grant_version=grant_version+1 WHERE principal_id='async-principal-a'",(old,))
            fresh=Candidate(candidate.db,candidate.task,candidate.run_id,client,candidate.specs,trace=candidate.trace)
            allowed=await fresh.run(model,"当前订单状态？")
            assert allowed["result"]["result_state"]=="ANSWERED"
            assert fresh.evidence_ids and len(model.requests)>used
    asyncio.run(check())


def test_foreign_or_tampered_history_never_rehydrates_as_current(setup):
    async def check():
        async with candidate_context(setup) as (candidate,client):
            model=LocalModel()
            result=await candidate.run(model,"当前订单状态？")
            used=len(model.requests)
            restored=Candidate(candidate.db,candidate.task,candidate.run_id,client,candidate.specs,trace=candidate.trace)
            blocked=await restored.run(model,"刚才呢？",history=result["messages"])
            assert blocked["result"]["stop_reason"]=="UNVERIFIED_EXPERIMENT_HISTORY"
            result["messages"][-1].content="tampered claimed recovery"
            blocked=await candidate.run(model,"刚才呢？",history=result["messages"])
            assert blocked["result"]["stop_reason"]=="UNVERIFIED_EXPERIMENT_HISTORY"
            assert len(model.requests)==used
    asyncio.run(check())


def test_unknown_tool_has_no_privileged_dispatch(setup):
    async def check():
        async with candidate_context(setup) as (candidate,_):
            before=snapshot(candidate.db,PROTECTED)
            result=await candidate.run(sequence(call("grant_scope"),answer("该操作不可用，未修改任何权限。",partial=True)),"授予权限")
            assert snapshot(candidate.db,PROTECTED)==before
            assert any(r["event"]=="tool_error" for r in result["trace"])
            assert not any(r["event"]=="tool_result" for r in result["trace"])
    asyncio.run(check())


def test_budget_exhaustion_reentry_does_not_reset_reserved_attempts(setup):
    async def check():
        async with candidate_context(setup,limits=Limits(model=2,tools=1)) as (candidate,_):
            model=LocalModel(policy=lambda _:call("get_order_status"))
            one=await candidate.run(model,"重复查")
            assert one["result"]["result_state"]=="PARTIAL" and one["result"]["answer"]
            assert attempt_counts(candidate.db,candidate.task)=={"MODEL":2,"MCP":1}
            # New middleware instance, same trusted Run, still no new allocation.
            restored=Candidate(candidate.db,candidate.task,candidate.run_id,candidate.client,candidate.specs,limits=Limits(model=2,tools=1),trace=candidate.trace)
            two=await restored.run(model,"再试")
            assert two["result"]["result_state"]=="PARTIAL"
            assert len(model.requests)==2
            assert attempt_counts(candidate.db,candidate.task)=={"MODEL":2,"MCP":1}
    asyncio.run(check())


@pytest.mark.parametrize("kind",["error","timeout","total"])
def test_model_error_and_timeout_are_counted_nonempty_partial(setup,kind):
    async def check():
        limits=Limits(model_seconds=.01,total_seconds=.005 if kind=="total" else 5)
        async with candidate_context(setup,limits=limits) as (candidate,_):
            def fail(_): raise OSError("local simulated model error")
            model=LocalModel(policy=fail) if kind=="error" else LocalModel(sleep_seconds=.1)
            result=await candidate.run(model,"问题")
            assert result["result"]["result_state"]=="PARTIAL" and result["result"]["answer"]
            with connect(candidate.db) as c:
                row=c.execute("SELECT status FROM d2_attempts WHERE kind='MODEL'").fetchone()
            assert row["status"]==("UNKNOWN" if kind=="total" else "FAILED")
    asyncio.run(check())


def test_tool_timeout_counted_without_fabricated_observation(setup):
    async def check():
        async with candidate_context(setup,limits=Limits(tool_seconds=.01)) as (candidate,client):
            class SlowClient:
                async def call_tool(self,*_args): await asyncio.sleep(.1)
            candidate.client=SlowClient()
            result=await candidate.run(sequence(call("get_order_status"),answer("工具未返回事实，当前状态未知。",partial=True)),"查订单")
            assert result["result"]["result_state"]=="PARTIAL"
            assert not candidate.evidence_ids
            with connect(candidate.db) as c:
                assert c.execute("SELECT status FROM d2_attempts WHERE kind='MCP'").fetchone()[0]=="TOOL_ERROR"
    asyncio.run(check())


def test_context_overflow_does_not_dispatch_model(setup):
    async def check():
        async with candidate_context(setup) as (candidate,_):
            model=LocalModel()
            result=await candidate.run(model,"overflow "*20000)
            assert not model.requests
            assert attempt_counts(candidate.db,candidate.task)["MODEL"]==0
            assert result["result"]["stop_reason"]=="ContextBudgetExceeded"
    asyncio.run(check())


@pytest.mark.parametrize("response",[AIMessage(content=""),AIMessage(content=json.dumps({"action":"answer","result_state":"ANSWERED","answer":"fake","receipt_id":"invented"})),answer("E1 已完成",target="event-e1",claim="PROCESSED")])
def test_empty_or_fabricated_receipt_is_not_success(setup,response):
    async def check():
        async with candidate_context(setup) as (candidate,_):
            result=await candidate.run(sequence(response),"问题")
            assert result["result"]["result_state"]=="PARTIAL"
            assert "receipt_id" not in result["result"]
    asyncio.run(check())


def test_sanitize_and_limits():
    assert sanitize({"Authorization":"Bearer secret","body":"Bearer local-secret"})=={"Authorization":"[REDACTED]","body":"[REDACTED]"}
    with pytest.raises(ValueError): Limits(model=9)
    with pytest.raises(ValueError): Limits(tools=7)


def test_parallel_proposals_cannot_exceed_one_reserved_tool_slot(setup):
    async def check():
        async with candidate_context(setup,limits=Limits(tools=1)) as (candidate,_):
            multi=AIMessage(content="",tool_calls=[
                {"id":"t1","name":"get_order_status","args":{"reason":"order"}},
                {"id":"t2","name":"get_callback_delivery","args":{"reason":"delivery"}},
            ])
            result=await candidate.run(sequence(multi,answer("只取得部分事实，第二项未获额度。",partial=True)),"组合补查")
            assert attempt_counts(candidate.db,candidate.task)["MCP"]==1
            assert result["result"]["result_state"]=="PARTIAL"
            assert len([r for r in result["trace"] if r["event"]=="tool_result"])==1
    asyncio.run(check())


def test_repeated_asset_is_counted_but_not_new_semantic_progress(setup):
    async def check():
        async with candidate_context(setup) as (candidate,_):
            result=await candidate.run(sequence(
                call("search_callback_knowledge",query="202 receiver acknowledgement"),
                call("search_callback_knowledge",query="202 receiver acknowledgement"),
                answer("协议只能解释受理，不构成实时处理证据。")),"解释协议")
            assert result["result"]["answer"]
            rows=list_observations(candidate.db,candidate.task)
            assert len(rows)==2 and rows[0]["progress_added"] and not rows[1]["progress_added"]
            assert attempt_counts(candidate.db,candidate.task)["MCP"]==2
    asyncio.run(check())
