"""Focused free P1 parameter/authorization tests; never constructs a paid client."""
import asyncio
from dataclasses import asdict
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from experiments.ar01_free_agent.agent import Trace
from experiments.ar01_free_agent.provider_budget import ExperimentBudget, BudgetStop, REQUEST_WIRE_V1, REQUEST_WIRE_P1_2048, request_bound
from experiments.ar01_free_agent.real_model import P1ProviderConfig, ProviderConfig, ProviderStopped, build_local_model, build_live_model, selected_cases, batch, ORDER
from experiments.ar01_free_agent.tests.local_provider import provider
from opspilot.config import ROOT
from opspilot.domain.d2 import digest_json


def body():
    b=json.loads((ROOT/'docs/evidence/ar-01/real-model-01/hf-01/research/actual-wire-body.json').read_text(encoding='utf-8'))
    return {**b,'max_tokens':2048}


def budget(path): return ExperimentBudget(path,reservation_policy=REQUEST_WIRE_P1_2048)


def test_p1_versioned_parameters_and_legacy_reservations_unchanged(tmp_path):
    assert P1ProviderConfig().max_tokens==2048 and ProviderConfig().max_tokens==512
    assert request_bound(body(),policy=REQUEST_WIRE_P1_2048)['reserve_micro']==317031
    assert request_bound({**body(),'max_tokens':512})['reserve_micro']==315188
    with pytest.raises(BudgetStop): request_bound(body())
    b=budget(tmp_path/'budget.sqlite3')
    key=b.reserve('one',body()); b.sent(key,payload=body())
    b.settle(key,{'prompt_tokens':100,'completion_tokens':1500,'total_tokens':1600})
    assert b.snapshot()['exposure_usd']=='0.001830'
    assert b.preflight(body())['ready']


def test_only_matching_p1_authorization_reaches_client_factory(tmp_path,monkeypatch):
    import experiments.ar01_free_agent.real_model as adapter
    made=[]
    monkeypatch.setattr(adapter,'_model',lambda **kw:made.append(kw['base_url']) or SimpleNamespace())
    monkeypatch.setenv('OPSPILOT_MODEL_API_KEY','local-authorization-fixture-not-sent')
    b=budget(tmp_path/'budget.sqlite3'); specs=body()['tools']
    with pytest.raises(ProviderStopped,match='PAID_AUTHORIZATION_REQUIRED'):
        build_live_model(budget=b,specs=specs,trace=Trace())
    auth={'authorized':True,'human_approval_reference':'SYNTHETIC_TEST_ONLY',
        'scope':'AR01_RM01_BOUNDED_P1','reservation_policy':REQUEST_WIRE_P1_2048,
        'config_digest':digest_json(asdict(P1ProviderConfig())),'request_limit':80,'cost_cap_usd':'0.50',
        'cases':[list(k) for k in ORDER],'case_manifest_digest':digest_json(selected_cases()),
        'tool_schema_digest':digest_json(sorted(specs,key=lambda s:s['function']['name']))}
    with pytest.raises(ProviderStopped,match='P1_AUTHORIZATION_CONFIGURATION_MISMATCH'):
        build_live_model(budget=b,specs=specs,trace=Trace(),live=True,authorization={**auth,'scope':'ONE_REQUEST_PROTOCOL_PROBE'})
    assert not made
    build_live_model(budget=b,specs=specs,trace=Trace(),live=True,authorization=auth)
    assert made==['https://api.deepseek.com'] and b.snapshot()['requests']==0


@pytest.mark.parametrize('mode',['p1-length','lost'])
def test_p1_truncation_or_unknown_halts_without_retry(tmp_path,mode):
    async def check(server):
        b=budget(tmp_path/'budget.sqlite3'); trace=Trace()
        model=build_local_model(base_url=server['url'],budget=b,specs=[],trace=trace,group_label='p1-negative')
        try:
            assert model.config.max_tokens==2048
            with pytest.raises(Exception): await model.ainvoke('已知材料解释')
            with pytest.raises(BudgetStop): await model.ainvoke('not sent')
            assert len(server['requests'])==1 and server['requests'][0]['max_tokens']==2048
            assert b.snapshot()['requests']==1 and b.snapshot()['halted']
            if mode=='lost': assert b.snapshot()['exposure_usd']=='0.317031'
        finally: await model.aclose()
    with provider(mode) as server: asyncio.run(check(server))


def test_p1_local_full_and_tool_answers_exact_ab_wire(tmp_path):
    destination=os.environ.get('AR01_P1_LOCAL_TRACE_DIR')
    target=Path(destination) if destination else tmp_path/'pairs'
    async def check(server):
        b=budget(tmp_path/'budget.sqlite3')
        def factory(group,task,specs,trace):
            label=f"{task['case_id']}/{group}"; b.claim_group(label)
            return build_local_model(base_url=server['url'],budget=b,specs=specs,trace=trace,group_label=label)
        result=await batch(target,b,factory)
        assert result['status']=='COMPLETED' and result['groups_completed']==10
        assert result['budget']['requests']==26 and result['budget']['policy']['cap_micro']==500000
        assert all(r['max_tokens']==2048 and r['tools']==body()['tools'] for r in server['requests'])
        for pair in result['results']:
            assert all(g['business_state_unchanged'] for g in pair['groups'])
            assert pair['groups'][0]['actual_outbound_tool_schema_digest']==pair['groups'][1]['actual_outbound_tool_schema_digest']
    with provider() as server: asyncio.run(check(server))


def test_p1_semantic_failure_does_not_filter_frozen_sample(tmp_path,monkeypatch):
    import experiments.ar01_free_agent.harness as harness
    seen=[]
    async def fake_pair(case,output,**kwargs):
        seen.append((case['id'],case['variant']))
        return {'id':case['id'],'variant':case['variant'],'groups':[
            {'group':g,'model_dispatches':1,'provider_tokens':[{'local_unit_fixture_only':True}],
             'result':{'delivery_mode':'DETERMINISTIC_FALLBACK','result_state':'PARTIAL'}} for g in ('A','B')]}
    monkeypatch.setattr(harness,'run_pair',fake_pair)
    result=asyncio.run(batch(tmp_path/'unit-batch',budget(tmp_path/'budget.sqlite3'),None))
    assert result['status']=='COMPLETED' and seen==list(ORDER)
