"""HF-01 free tests; legacy tests and frozen cases are not modified."""
from __future__ import annotations

import asyncio
from decimal import Decimal
import json
import os
from pathlib import Path
import subprocess
import sys
import time

import pytest

from experiments.ar01_free_agent.provider_budget import (
    ExperimentBudget, BudgetStop, REQUEST_WIRE_V1, request_bound,
)
from experiments.ar01_free_agent.real_model import (
    build_local_model, build_live_model, ProviderStopped, batch,
)
from experiments.ar01_free_agent.agent import Trace
from experiments.ar01_free_agent.tests.local_provider import provider


def wire():
    return {"model":"deepseek-flash","stream":False,"thinking":{"type":"disabled"},
        "max_tokens":512,"parallel_tool_calls":False,
        "messages":[{"role":"user","content":"已知材料：请解释 HTTP 202 与处理完成的区别。"}]}


def budget(path,**kwargs):
    return ExperimentBudget(path,reservation_policy=REQUEST_WIRE_V1,**kwargs)


@pytest.fixture
def capture(request):
    trace=Trace()
    yield trace
    root=os.environ.get("AR01_HF01_TRACE_DIR")
    if root:
        path=Path(root)
        path.mkdir(parents=True,exist_ok=True)
        (path/f"{request.node.name}.jsonl").write_text("".join(json.dumps(r,ensure_ascii=False)+"\n" for r in trace.rows),encoding="utf-8")


def test_hf01_01_request_contract_fits_without_heuristic_input_bound(tmp_path,capture):
    body=wire()
    bound=request_bound(body)
    assert bound["input_upper_tokens"]==1_048_576 and bound["output_upper_tokens"]==512
    assert bound["reserve_micro"]==315188 and not bound["absolute_billing_guarantee"]
    b=budget(tmp_path/"budget.sqlite3")
    assert not b.preflight()["ready"]  # An actual body is mandatory.
    assert b.preflight(body)["ready"]
    key=b.reserve("valid",body)
    b.sent(key,payload=body)
    assert b.snapshot()["exposure_usd"]=="0.315188"
    capture.emit("request_bound_observed",bound=bound,body=body,ledger=b.snapshot())
    old=ExperimentBudget(tmp_path/"legacy.sqlite3")
    with pytest.raises(BudgetStop,match="COST_CAP"): old.reserve("legacy",body)


@pytest.mark.parametrize("change",[
    {"max_tokens":None},{"max_tokens":True},{"max_tokens":512.0},{"max_tokens":393216},
    {"thinking":{"type":"enabled"}},{"max_completion_tokens":512},
    {"model":"unknown"},{"messages":[{"role":"user","content":[{"type":"image_url"}]}]},
])
def test_hf01_02_unbounded_or_unknown_wire_rejected(tmp_path,change):
    b=budget(tmp_path/"budget.sqlite3")
    with pytest.raises(BudgetStop,match="WIRE_"): b.reserve("invalid",{**wire(),**change})
    assert b.snapshot()["requests"]==0


def test_hf01_02_actual_wire_must_match_prepared_reservation(tmp_path,capture):
    async def check(server):
        b=budget(tmp_path/"budget.sqlite3")
        model=build_local_model(base_url=server["url"],budget=b,specs=[],trace=capture,group_label="changed")
        async def tamper(request):
            data=json.loads(request.content)
            data["messages"][0]["content"]+=" changed after reserve"
            request._content=json.dumps(data).encode()
        model.runtime["http_async"].event_hooks["request"].insert(0,tamper)
        try:
            with pytest.raises(BudgetStop,match="WIRE_BODY_CHANGED"):
                await model.ainvoke("已知材料解释")
            assert not server["requests"] and b.snapshot()["requests"]==1
            assert b.snapshot()["exposure_usd"]=="0.315188"
        finally: await model.aclose()
    with provider() as server: asyncio.run(check(server))


def test_hf01_03_settled_plus_next_reserve_and_legacy_policy_isolation(tmp_path,capture):
    path=tmp_path/"budget.sqlite3"
    b=budget(path)
    for i in range(2):
        key=b.reserve(str(i),wire())
        b.sent(key,payload=wire())
        b.settle(key,{"prompt_tokens":600000,"completion_tokens":20,"total_tokens":600020})
    with pytest.raises(BudgetStop,match="COST_CAP"): b.reserve("third",wire())
    assert b.snapshot()["exposure_usd"]=="0.360048"
    with pytest.raises(BudgetStop,match="LEDGER_POLICY_CHANGED"): ExperimentBudget(path)
    assert budget(path).snapshot()["requests"]==2
    capture.emit("accumulation_observed",ledger=b.snapshot())


@pytest.mark.parametrize("mode",["lost","wait"])
def test_hf01_04_unknown_and_timeout_keep_request_reservation(tmp_path,capture,mode):
    async def check(server):
        b=budget(tmp_path/"budget.sqlite3")
        model=build_local_model(base_url=server["url"],budget=b,specs=[],trace=capture,group_label="unknown")
        try:
            with pytest.raises(Exception): await asyncio.wait_for(model.ainvoke("已知材料解释"),.2 if mode=="wait" else 3)
            assert len(server["requests"])==1
            assert b.snapshot()["exposure_usd"]=="0.315188"
            assert not budget(b.path).preflight(wire())["ready"]
            with pytest.raises(BudgetStop,match="HALTED"): b.reserve("retry",wire())
            capture.emit("unknown_keeps_reservation",mode=mode,ledger=b.snapshot())
        finally: await model.aclose()
    with provider(mode) as server: asyncio.run(check(server))


def test_hf01_05_two_os_processes_restart_and_same_logical_key(tmp_path,capture):
    path=tmp_path/"budget.sqlite3"
    budget(path)
    program="""import json,pathlib,sys,time
from experiments.ar01_free_agent.provider_budget import ExperimentBudget,BudgetStop,REQUEST_WIRE_V1
b=ExperimentBudget(sys.argv[1],reservation_policy=REQUEST_WIRE_V1)
pathlib.Path(sys.argv[2]+sys.argv[3]).touch()
while not pathlib.Path(sys.argv[2]).exists(): time.sleep(.01)
body=json.loads(sys.argv[4])
try:
 k=b.reserve(sys.argv[3],body); b.sent(k,payload=body); print(json.dumps({'reserved':k}),flush=True)
except BudgetStop as e: print(json.dumps({'denied':str(e)}),flush=True)
"""
    gate=tmp_path/"go"
    children=[subprocess.Popen([sys.executable,"-c",program,str(path),str(gate),label,json.dumps(wire())],
        stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,encoding="utf-8") for label in ("A","B")]
    try:
        deadline=time.monotonic()+10
        while not all(Path(str(gate)+v).exists() for v in ("A","B")):
            assert time.monotonic()<deadline
            time.sleep(.01)
        gate.touch()
        outputs=[p.communicate(timeout=10) for p in children]
        results=[json.loads(o) for o,e in outputs if not e]
        assert len(results)==2 and sum("reserved" in r for r in results)==1
        assert sum("IN_FLIGHT" in r.get("denied","") for r in results)==1
        reopened=budget(path)
        assert reopened.snapshot()["requests"]==1 and reopened.snapshot()["exposure_usd"]=="0.315188"
        with pytest.raises(BudgetStop): reopened.reserve("A",wire())
        capture.emit("two_process_race_observed",outputs=results,ledger=reopened.snapshot(),exit_codes=[p.returncode for p in children])
    finally:
        for child in children:
            if child.poll() is None:
                child.terminate()
                child.wait(timeout=5)


@pytest.mark.parametrize("mode",["400","missing-usage","extra-output","input-overrun","both-bound-overrun","reasoning","reasoning-text","bad-total","no-completion","no-finish"])
def test_hf01_06_usage_or_response_contract_halts_next_request(tmp_path,capture,mode):
    async def check(server):
        b=budget(tmp_path/"budget.sqlite3")
        model=build_local_model(base_url=server["url"],budget=b,specs=[],trace=capture,group_label="invalid-response")
        try:
            with pytest.raises(Exception): await model.ainvoke("已知材料解释")
            assert b.snapshot()["halted"]
            with pytest.raises(BudgetStop,match="HALTED"): await model.ainvoke("no retry")
            assert len(server["requests"])==1
            assert server["requests"][0]["parallel_tool_calls"] is False
            if mode=="both-bound-overrun":
                # A vendor contract violation can exceed the reservation on the
                # already-sent request. Detect/retain it, never claim prevention.
                assert b.snapshot()["exposure_usd"]=="0.786432"
            capture.emit("response_contract_rejected",mode=mode,ledger=b.snapshot())
        finally: await model.aclose()
    with provider(mode) as server: asyncio.run(check(server))


def test_hf01_07_08_same_five_pairs_fit_with_unchanged_cap_and_tools(tmp_path,capture):
    target=os.environ.get("AR01_HF01_TRACE_DIR")
    output=Path(target)/"paired-request-policy" if target else tmp_path/"pairs"
    async def check(server):
        b=budget(tmp_path/"budget.sqlite3")
        def factory(group,task,specs,trace):
            label=f"{task['case_id']}/{group}"
            b.claim_group(label)
            return build_local_model(base_url=server["url"],budget=b,specs=specs,trace=trace,group_label=label)
        result=await batch(output,b,factory)
        assert result["status"]=="COMPLETED" and result["groups_completed"]==10
        assert result["budget"]["policy"]["cap_micro"]==500000
        assert result["budget"]["requests"]==26
        tools=server["requests"][0]["tools"]
        assert len(tools)==6 and all(r["tools"]==tools and r["max_tokens"]==512 for r in server["requests"])
        for pair in result["results"]:
            a,bgroup=pair["groups"]
            assert a["initial_business_digest"]==bgroup["initial_business_digest"]
            assert a["actual_outbound_tool_schema_digest"]==bgroup["actual_outbound_tool_schema_digest"]
            assert all(g["business_state_unchanged"] for g in pair["groups"])
        capture.emit("observed_five_pairs",result=result,paid_calls=0)
    with provider() as server: asyncio.run(check(server))


def test_hf01_header_optional_but_completion_is_real_correlation(tmp_path,capture):
    async def check(server):
        b=budget(tmp_path/"budget.sqlite3")
        model=build_local_model(base_url=server["url"],budget=b,specs=[],trace=capture,group_label="no-header")
        try:
            ai=await model.ainvoke("已知材料解释")
            assert ai.response_metadata["provider_request_id"] is None
            assert ai.response_metadata["provider_correlation_id"]=="local-completion-1"
            assert ai.response_metadata["provider_correlation_kind"]=="COMPLETION_ID"
            model.assert_healthy()
        finally: await model.aclose()
    with provider("no-request-id") as server: asyncio.run(check(server))


def test_hf01_09_unapproved_or_p1_authorization_cannot_construct_paid_client(tmp_path,monkeypatch):
    import experiments.ar01_free_agent.real_model as adapter
    from dataclasses import asdict
    from opspilot.domain.d2 import digest_json
    constructed=[]
    monkeypatch.setattr(adapter,"_model",lambda **kwargs:constructed.append(kwargs))
    b=budget(tmp_path/"budget.sqlite3",request_limit=1)
    with pytest.raises(ProviderStopped,match="PAID_AUTHORIZATION_REQUIRED"):
        build_live_model(budget=b,specs=[],trace=None,probe_wire=wire())
    p1={"authorized":True,"human_approval_reference":"SYNTHETIC_TEST_NOT_AUTHORIZATION",
        "config_digest":digest_json(asdict(adapter.ProviderConfig())),"request_limit":80,"cost_cap_usd":"0.50",
        "cases":[list(k) for k in adapter.ORDER]}
    with pytest.raises(ProviderStopped,match="PROBE_AUTHORIZATION"):
        build_live_model(budget=b,specs=[],trace=None,probe_wire=wire(),live=True,authorization=p1)
    assert not constructed and b.snapshot()["requests"]==0


def test_hf01_probe_scope_and_wire_digest_checked_before_client_factory(tmp_path,monkeypatch):
    import experiments.ar01_free_agent.real_model as adapter
    from dataclasses import asdict
    from types import SimpleNamespace
    from opspilot.domain.d2 import digest_json
    constructed=[]
    def fake_factory(**kwargs):
        constructed.append(kwargs["base_url"])
        return SimpleNamespace(runtime={})
    monkeypatch.setattr(adapter,"_model",fake_factory)
    monkeypatch.setenv("OPSPILOT_MODEL_API_KEY","local-fixture-never-sent")
    b=budget(tmp_path/"budget.sqlite3",request_limit=1)
    auth={"authorized":True,"human_approval_reference":"SYNTHETIC_GATE_TEST_ONLY_NOT_USER_APPROVAL",
        "scope":"ONE_REQUEST_PROTOCOL_PROBE","reservation_policy":REQUEST_WIRE_V1,
        "config_digest":digest_json(asdict(adapter.ProviderConfig())),"request_limit":1,
        "cost_cap_usd":"0.50","wire_digest":digest_json(wire())}
    with pytest.raises(ProviderStopped,match="WIRE_MISMATCH"):
        build_live_model(budget=b,specs=[],trace=None,live=True,authorization=auth,
            probe_wire={**wire(),"messages":[{"role":"user","content":"different"}]})
    assert not constructed
    # A replaced factory proves gate reachability; no real SDK/client is created.
    model=build_live_model(budget=b,specs=[],trace=None,live=True,authorization=auth,probe_wire=wire())
    assert constructed==["https://api.deepseek.com"]
    assert model.runtime["authorized_wire_digest"]==digest_json(wire())
    assert b.snapshot()["requests"]==0


def test_hf01_exact_one_probe_and_reservation_survive_after_settlement(tmp_path,capture):
    b=budget(tmp_path/"budget.sqlite3",request_limit=1)
    key=b.reserve("probe",wire())
    b.sent(key,payload=wire())
    b.settle(key,{"prompt_tokens":100,"completion_tokens":20,"total_tokens":120})
    with pytest.raises(BudgetStop,match="REQUEST_CAP"): budget(b.path,request_limit=1).reserve("second",wire())
    with pytest.raises(BudgetStop,match="DUPLICATE_REQUEST"): b.reserve("probe",wire())
    capture.emit("single_probe_cap_observed",ledger=b.snapshot())
