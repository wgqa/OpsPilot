"""P0 only: deterministic budget + installed SDK against loopback, never paid."""
from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from experiments.ar01_free_agent.provider_budget import ExperimentBudget, BudgetStop
from experiments.ar01_free_agent.real_model import (
    ProviderConfig, ProviderStopped, build_live_model, build_local_model, selected_cases, batch,
)
from experiments.ar01_free_agent.agent import Trace
from experiments.ar01_free_agent.tests.local_provider import provider


@pytest.fixture
def capture(request):
    trace=Trace()
    yield trace
    directory=os.environ.get("AR01_RM01_TRACE_DIR")
    if directory:
        path=Path(directory)
        path.mkdir(parents=True,exist_ok=True)
        (path/f"{request.node.name}.jsonl").write_text("".join(json.dumps(r,ensure_ascii=False)+"\n" for r in trace.rows),encoding="utf-8")


def test_default_preflight_blocks_before_key_or_network(tmp_path, monkeypatch):
    monkeypatch.delenv("OPSPILOT_MODEL_API_KEY", raising=False)
    budget = ExperimentBudget(tmp_path/"budget.sqlite3")
    assert budget.snapshot()["requests"] == 0
    assert budget.preflight()["next_reservation_usd"] == "0.786432"
    assert budget.preflight()["ready"] is False
    with pytest.raises(ProviderStopped, match="PAID_AUTHORIZATION_REQUIRED"):
        build_live_model(budget=budget, specs=[], trace=None)
    with pytest.raises(BudgetStop, match="COST_CAP"):
        budget.reserve("first", {"request":"test"})
    assert budget.snapshot()["requests"] == 0


def test_settled_and_unknown_reservations_survive_reopen(tmp_path):
    path=tmp_path/"budget.sqlite3"
    budget=ExperimentBudget(path, cost_cap_usd=Decimal("2"))
    key=budget.reserve("one", {"messages":[]})
    budget.sent(key)
    budget.settle(key, {"prompt_tokens":100,"completion_tokens":20,"total_tokens":120})
    assert budget.snapshot()["exposure_usd"] == "0.000054"
    with pytest.raises(BudgetStop, match="DUPLICATE_REQUEST"):
        budget.reserve("one", {})
    key=budget.reserve("two", {})
    budget.unknown(key,"TIMEOUT")
    reopened=ExperimentBudget(path, cost_cap_usd=Decimal("2"))
    assert reopened.snapshot()["requests"] == 2
    assert reopened.snapshot()["exposure_usd"] == "0.786486"
    with pytest.raises(BudgetStop, match="HALTED"):
        reopened.reserve("three", {})


def test_independent_connections_and_duplicate_send_are_bounded(tmp_path):
    path=tmp_path/"budget.sqlite3"
    ExperimentBudget(path,cost_cap_usd=Decimal("2"))
    def compete(label):
        try:
            return ExperimentBudget(path,cost_cap_usd=Decimal("2")).reserve(label,{})
        except BudgetStop as error:
            return str(error)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(compete,("A","B")))
    assert sum("IN_FLIGHT" in r for r in results)==1
    key=next(r for r in results if "IN_FLIGHT" not in r)
    budget=ExperimentBudget(path,cost_cap_usd=Decimal("2"))
    budget.sent(key)
    with pytest.raises(BudgetStop,match="REPEAT_SEND"):
        budget.sent(key)
    assert budget.snapshot()["requests"] == 1


@pytest.mark.parametrize("usage", [None,{}, {"prompt_tokens":True,"completion_tokens":1,"total_tokens":2},
    {"prompt_tokens":1.5,"completion_tokens":1,"total_tokens":2},
    {"prompt_tokens":1,"completion_tokens":1,"total_tokens":99},
    {"prompt_tokens":-1,"completion_tokens":1,"total_tokens":0}])
def test_bad_usage_keeps_full_reservation(tmp_path,usage):
    budget=ExperimentBudget(tmp_path/"budget.sqlite3",cost_cap_usd=Decimal("2"))
    key=budget.reserve("one",{})
    budget.sent(key)
    with pytest.raises(BudgetStop,match="USAGE"):
        budget.settle(key,usage)
    assert budget.snapshot()["exposure_usd"] == "0.786432"
    assert budget.snapshot()["halted"]


def test_request_count_and_case_replay_not_reset(tmp_path):
    budget=ExperimentBudget(tmp_path/"budget.sqlite3",cost_cap_usd=Decimal("2"),request_limit=1)
    budget.claim_group("AR01-01/material/A")
    with pytest.raises(BudgetStop,match="GROUP_ALREADY_CLAIMED"):
        budget.claim_group("AR01-01/material/A")
    key=budget.reserve("one",{})
    budget.sent(key)
    budget.settle(key,{"prompt_tokens":1,"completion_tokens":1,"total_tokens":2})
    with pytest.raises(BudgetStop,match="REQUEST_CAP"):
        budget.reserve("two",{})


def test_frozen_case_order_and_configuration():
    assert [(c["id"],c["variant"]) for c in selected_cases()] == [
        ("AR01-01","material"),("AR01-03","acknowledged"),("AR01-03","failed"),
        ("AR01-04","different-event"),("AR01-06","scope")]
    config=ProviderConfig()
    assert config.model=="deepseek-flash" and config.max_retries==0
    with pytest.raises(ValueError):
        ProviderConfig(model="other-model")


def test_actual_wire_usage_ids_and_exact_parameters(tmp_path,capture):
    async def check(server):
        budget=ExperimentBudget(tmp_path/"budget.sqlite3",cost_cap_usd=Decimal("2"))
        specs=[{"type":"function","function":{"name":"example","description":"local schema probe",
            "parameters":{"type":"object","title":"kept","properties":{}}}}]
        model=build_local_model(base_url=server["url"],budget=budget,specs=specs,trace=capture,group_label="probe")
        try:
            ai=await model.bind_tools(specs,tool_choice="auto",parallel_tool_calls=False).ainvoke("已知材料：202为何不同于完成？")
            assert ai.response_metadata["id"]=="local-completion-1"
            assert ai.response_metadata["provider_request_id"]=="local-http-request-1"
            assert ai.usage_metadata["input_tokens"]==100
            wire=server["requests"][0]
            assert wire["tools"]==specs and wire["max_tokens"]==512
            assert "max_completion_tokens" not in wire
            assert wire["thinking"]=={"type":"disabled"} and wire["stream"] is False
            assert budget.snapshot()["rows"][0]["sends"]==1
            assert budget.snapshot()["exposure_usd"]=="0.000054"
            with pytest.raises(ProviderStopped,match="UNFROZEN_PROVIDER_PARAMETER"):
                await model.ainvoke("no",temperature=1)
            assert len(server["requests"])==1
        finally: await model.aclose()
    with provider() as server: asyncio.run(check(server))


@pytest.mark.parametrize("mode",["400","lost","missing-usage","missing-id","extra-output"])
def test_protocol_failure_no_retry_and_no_next_send(tmp_path,capture,mode):
    async def check(server):
        budget=ExperimentBudget(tmp_path/"budget.sqlite3",cost_cap_usd=Decimal("2"))
        model=build_local_model(base_url=server["url"],budget=budget,specs=[],trace=capture,group_label="failure")
        try:
            with pytest.raises(Exception): await model.ainvoke("已知材料解释")
            assert len(server["requests"])==1
            with pytest.raises(BudgetStop,match="HALTED"):
                await model.ainvoke("must not be sent")
            assert len(server["requests"])==1 and budget.snapshot()["requests"]==1
            if mode in {"400","lost","missing-usage"}:
                assert budget.snapshot()["exposure_usd"]=="0.786432"
            capture.emit("observed_final_budget",mode=mode,ledger=budget.snapshot(),actual_http_count=len(server["requests"]))
        finally: await model.aclose()
    with provider(mode) as server: asyncio.run(check(server))


def test_model_version_drift_stops_and_retains_usage(tmp_path,capture):
    async def check(server):
        budget=ExperimentBudget(tmp_path/"budget.sqlite3",cost_cap_usd=Decimal("2"))
        model=build_local_model(base_url=server["url"],budget=budget,specs=[],trace=capture,group_label="drift")
        try:
            await model.ainvoke("已知材料解释")
            with pytest.raises(BudgetStop,match="MODEL_VERSION_DRIFT"): await model.ainvoke("已知材料解释")
            assert len(server["requests"])==2
            assert budget.snapshot()["requests"]==2 and budget.snapshot()["exposure_usd"]=="0.000108"
        finally: await model.aclose()
    with provider("drift") as server: asyncio.run(check(server))


def test_loopback_factory_cannot_reach_external_endpoint(tmp_path,capture):
    budget=ExperimentBudget(tmp_path/"budget.sqlite3")
    for url in ("https://api.deepseek.com","http://localhost:80","http://127.0.0.1.evil.test:80"):
        with pytest.raises(ProviderStopped,match="LOOPBACK"):
            build_local_model(base_url=url,budget=budget,specs=[],trace=capture,group_label="blocked")


def test_fixed_batch_real_sdk_mcp_ab_parity(tmp_path,capture):
    destination=os.environ.get("AR01_RM01_TRACE_DIR")
    output=(Path(destination)/"five-pair-local" if destination else tmp_path/"batch")
    async def check(server):
        budget=ExperimentBudget(tmp_path/"budget.sqlite3",cost_cap_usd=Decimal("2"))
        def factory(group,task,specs,trace):
            label=f"{task['case_id']}/{group}"
            budget.claim_group(label)
            return build_local_model(base_url=server["url"],budget=budget,specs=specs,trace=trace,group_label=label)
        result=await batch(output,budget,factory)
        assert result["status"]=="COMPLETED" and result["groups_completed"]==10
        assert result["budget"]["requests"]==len(server["requests"])<=80
        # These are actual bodies received by the local HTTP server, not merely
        # the wrapper's declared bind_tools arguments.
        expected_tools=server["requests"][0]["tools"]
        assert len(expected_tools)==6 and all(w.get("tools")==expected_tools for w in server["requests"])
        assert sum(g["attempt_counts"]["MCP"] for r in result["results"] for g in r["groups"])<=60
        for pair in result["results"]:
            a,b=pair["groups"]
            assert a["initial_business_digest"]==b["initial_business_digest"]
            assert a["actual_outbound_tool_schema_digest"]==b["actual_outbound_tool_schema_digest"]
            assert all(g["business_state_unchanged"] for g in pair["groups"])
        capture.emit("observed_local_batch",result=result,actual_http_count=len(server["requests"]),paid_calls=0)
    with provider() as server: asyncio.run(check(server))


@pytest.mark.parametrize("sent",[False,True])
def test_os_process_exit_preserves_reserved_or_sent_exposure(tmp_path,capture,sent):
    path=tmp_path/"process-budget.sqlite3"
    code=("import os,sys; from decimal import Decimal; "
        "from experiments.ar01_free_agent.provider_budget import ExperimentBudget; "
        "b=ExperimentBudget(sys.argv[1],cost_cap_usd=Decimal('2')); "
        "k=b.reserve('crash-request',{}); "+("b.sent(k); " if sent else "")+"os._exit(23)")
    child=subprocess.run([sys.executable,"-c",code,str(path)],capture_output=True,timeout=10)
    assert child.returncode==23
    reopened=ExperimentBudget(path,cost_cap_usd=Decimal("2"))
    snapshot=reopened.snapshot()
    assert snapshot["requests"]==1 and snapshot["exposure_usd"]=="0.786432"
    assert snapshot["rows"][0]["sends"]==int(sent)
    with pytest.raises(BudgetStop,match="IN_FLIGHT_OR_UNKNOWN"): reopened.reserve("retry",{})
    capture.emit("os_process_exit_observed",returncode=child.returncode,ledger=snapshot)


@pytest.mark.parametrize("cancel_kind",["cancel","timeout"])
def test_cancelled_or_timed_out_send_keeps_reservation(tmp_path,capture,cancel_kind):
    async def check(server):
        budget=ExperimentBudget(tmp_path/"budget.sqlite3",cost_cap_usd=Decimal("2"))
        model=build_local_model(base_url=server["url"],budget=budget,specs=[],trace=capture,group_label="cancel")
        try:
            pending=asyncio.create_task(model.ainvoke("已知材料解释"))
            for _ in range(200):
                if server["requests"]: break
                await asyncio.sleep(.01)
            assert len(server["requests"])==1
            if cancel_kind=="cancel":
                pending.cancel()
                with pytest.raises(asyncio.CancelledError): await pending
            else:
                with pytest.raises(TimeoutError): await asyncio.wait_for(pending,.02)
            snapshot=budget.snapshot()
            assert snapshot["rows"][0]["status"]=="UNKNOWN" and snapshot["exposure_usd"]=="0.786432"
            assert model.sdk.max_retries==0 and model.sdk.request_timeout==30
            capture.emit("observed_cancelled_request",kind=cancel_kind,actual_http_count=len(server["requests"]),ledger=snapshot)
        finally: await model.aclose()
    with provider("wait") as server: asyncio.run(check(server))


def test_first_pair_protocol_fault_stops_batch_and_retains_incomplete_group(tmp_path,capture):
    async def check(server):
        budget=ExperimentBudget(tmp_path/"budget.sqlite3",cost_cap_usd=Decimal("2"))
        def factory(group,task,specs,trace):
            budget.claim_group(f"{task['case_id']}/{group}")
            return build_local_model(base_url=server["url"],budget=budget,specs=specs,trace=trace,group_label="first-pair")
        result=await batch(tmp_path/"stopped-batch",budget,factory)
        assert result["status"]=="STOPPED" and result["groups_completed"]==0
        assert len(server["requests"])==1 and budget.snapshot()["requests"]==1
        assert (tmp_path/"stopped-batch/AR01-01-material/A.result.json").is_file()
        assert not (tmp_path/"stopped-batch/AR01-01-material/B.result.json").exists()
        capture.emit("observed_batch_protocol_stop",result=result,actual_http_count=len(server["requests"]))
    with provider("400") as server: asyncio.run(check(server))


def test_even_explicit_live_flag_cannot_bypass_monetary_preflight(tmp_path,monkeypatch):
    from dataclasses import asdict
    from opspilot.domain.d2 import digest_json
    from experiments.ar01_free_agent.real_model import ORDER
    # Synthetic fixture only, NOT a human paid authorization.
    auth={"authorized":True,"human_approval_reference":"LOCAL_TEST_ONLY_NOT_AUTHORIZATION",
        "config_digest":digest_json(asdict(ProviderConfig())),"request_limit":80,"cost_cap_usd":"0.50",
        "cases":[list(k) for k in ORDER]}
    monkeypatch.setenv("OPSPILOT_MODEL_API_KEY","must-not-be-used-local-fixture")
    budget=ExperimentBudget(tmp_path/"budget.sqlite3")
    with pytest.raises(ProviderStopped,match="PREFLIGHT_BLOCKED"):
        build_live_model(budget=budget,specs=[],trace=None,live=True,authorization=auth)
    assert budget.snapshot()["requests"]==0


def test_safe_trace_omits_credentials_and_hidden_reasoning():
    from experiments.ar01_free_agent.real_model import safe_response
    text=json.dumps(safe_response({"authorization":"Bearer sk-supersecretdummy12345",
        "choices":[{"message":{"content":"safe","reasoning_content":"do not record"}}]}))
    assert "sk-supersecretdummy12345" not in text and "do not record" not in text


def test_exact_eighty_request_cap_and_next_cost_reservation(tmp_path,capture):
    budget=ExperimentBudget(tmp_path/"eighty.sqlite3",cost_cap_usd=Decimal("2"))
    for i in range(80):
        key=budget.reserve(f"request-{i}",{})
        budget.sent(key)
        budget.settle(key,{"prompt_tokens":1,"completion_tokens":1,"total_tokens":2})
    with pytest.raises(BudgetStop,match="REQUEST_CAP"): budget.reserve("request-81",{})
    assert budget.snapshot()["requests"]==80
    capture.emit("exact_request_cap_observed",ledger=budget.snapshot())
    cost=ExperimentBudget(tmp_path/"exact-cost.sqlite3",cost_cap_usd=Decimal("0.786450"))
    key=cost.reserve("first",{})
    cost.sent(key)
    cost.settle(key,{"prompt_tokens":100,"completion_tokens":20,"total_tokens":120})
    with pytest.raises(BudgetStop,match="COST_CAP"): cost.reserve("next",{})
    capture.emit("next_cost_reservation_rejected",ledger=cost.snapshot(),next_reservation_usd="0.786432")
