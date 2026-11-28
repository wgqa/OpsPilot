"""New one-shot scope and budget checks; all Provider traffic is MockTransport."""
import asyncio
import json
import subprocess
from types import SimpleNamespace

import httpx
import pytest

import opspilot.assistant as assistant
from opspilot.domain import assistant_experiment as ledger


EXP = 'AR04C-F01-RECHECK-01'


def _authorization(tmp_path, monkeypatch):
    monkeypatch.setenv('OPSPILOT_ASSISTANT_PROVIDER_ENABLED', '1')
    monkeypatch.setenv('OPSPILOT_ASSISTANT_EXPERIMENT_ID', EXP)
    monkeypatch.setenv('OPSPILOT_MODEL_API_KEY', 'offline-test-only')
    monkeypatch.setenv('OPSPILOT_MODEL_NAME', 'deepseek-flash')
    monkeypatch.setenv('OPSPILOT_MODEL_BASE_URL', 'https://api.deepseek.com')
    monkeypatch.setenv('OPSPILOT_AR04C_MEMORY_MODE', 'ON')
    monkeypatch.setenv('OPSPILOT_AR04C_F01_RECHECK_ONE_SHOT_TOKEN', 'offline-test-token')
    auth = tmp_path / 'authorization.json'
    claim = tmp_path / 'claim.json'
    monkeypatch.setattr(assistant, 'AR04C_RECHECK_AUTH_RECORD', auth)
    monkeypatch.setattr(assistant, 'AR04C_RECHECK_CLAIM', claim)
    head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=assistant.ROOT, text=True).strip()
    record = {
        'authorization_id': 'AR04C-F01-RECHECK-01-USER-AUTH',
        'experiment_id': EXP, 'status': 'AUTHORIZED_ONE_SHOT',
        'authorization_source': 'Explicit user authorization for AR04C-F01-RECHECK-01',
        'branch': 'codex/ar04c-f01-context-currentness-01',
        'base_sha': '08b007dda384b03a3b7d1ac6351d8c4ee1dcfb45',
        'execution_head_sha': head,
        'frozen_contract_sha256': assistant._ar04c_contract_digest(EXP),
        'provider': 'DeepSeek', 'model': 'deepseek-flash', 'thinking': {'type': 'disabled'},
        'provider_limit': 8, 'providers_per_condition': 8, 'mcp_limit': None,
        'application_budget_usd_micro': 5_250_000, 'condition_budget_usd_micro': 5_250_000,
        'provider_reservation_usd_micro': 668_468, 'price_version': ledger.AR04C_PRICE_VERSION,
        'max_tokens': 2048, 'tool_choice': 'auto when tools are supplied',
        'parallel_tool_calls': False, 'stream': False, 'context_input_limit_tokens': 12000,
        'request_timeout_seconds': 30, 'provider_concurrency': 1,
        'automatic_retries': 0, 'manual_retries': 0, 'business_writes_allowed': False,
        'authorized_on': 'test-only', 'authorization_card_sha256': 'a' * 64,
    }
    auth.write_text(json.dumps(record, sort_keys=True), encoding='utf-8')
    return auth, claim


def test_new_identity_uses_bounded_separate_budget_without_changing_old():
    assert ledger._limits_for_experiment(EXP) == (8, None)
    assert ledger._budget_for_experiment(EXP) == 5_250_000
    assert ledger._reservation_for_experiment(EXP) == 668_468
    assert ledger._reservation_for_experiment(ledger.AR04C_REAL_JOURNEY_01_EXPERIMENT_ID) == 645_600
    legacy = assistant._ar04c_scope(ledger.AR04C_REAL_JOURNEY_01_EXPERIMENT_ID)
    assert legacy['branch'] == 'codex/ar04c-real-journey-01'
    assert legacy['provider_limit'] == 16 and legacy['budget'] == 10_500_000
    assert legacy['claim'] == assistant.AR04C_CLAIM and legacy['reservation'] == 645_600


def test_legacy_authorization_path_remains_compatible(tmp_path, monkeypatch):
    from test_ar04c_prelive_hf01 import _write_authorization

    actual_run = subprocess.run
    def git_in_legacy_branch(args, *positional, **kwargs):
        if args[:3] == ['git', 'branch', '--show-current']:
            return SimpleNamespace(returncode=0, stdout='codex/ar04c-real-journey-01\n')
        return actual_run(args, *positional, **kwargs)

    monkeypatch.setattr(subprocess, 'run', git_in_legacy_branch)
    monkeypatch.setenv('OPSPILOT_ASSISTANT_EXPERIMENT_ID', ledger.AR04C_REAL_JOURNEY_01_EXPERIMENT_ID)
    _write_authorization(tmp_path, monkeypatch)
    assistant._ar04c_create_one_shot_claim()
    assert assistant._ar04c_one_shot_authorized(ledger.AR04C_REAL_JOURNEY_01_EXPERIMENT_ID)


def test_recheck_authorization_claim_and_mock_send_are_scoped(tmp_path, monkeypatch):
    from opspilot.domain.database import connect

    _auth, claim = _authorization(tmp_path, monkeypatch)
    assistant._ar04c_create_one_shot_claim()
    assert assistant._ar04c_one_shot_authorized(EXP)
    with pytest.raises(RuntimeError, match='CLAIM_ALREADY_EXISTS'):
        assistant._ar04c_create_one_shot_claim()
    db = tmp_path / 'domain.sqlite3'
    ledger.initialize_experiment(db, EXP)
    assistant._ar04c_bind_campaign_database(db, 'ON')
    with pytest.raises(RuntimeError, match='MEMORY_MODE'):
        assistant._ar04c_bind_campaign_database(db, 'OFF')
    with connect(db) as connection:
        connection.execute('CREATE TABLE task_runs (run_id TEXT PRIMARY KEY)')
        connection.execute("INSERT INTO task_runs VALUES ('run-offline')")
    reserved = ledger.reserve_dispatch(db, experiment_id=EXP, run_id='run-offline', kind='MODEL',
                                       logical_key='call-offline', request={'offline': True})
    assert reserved['reserved_usd_micro'] == 668_468
    sent = []

    def reply(request):
        state = json.loads(assistant._ar04c_claim_state_path().read_text(encoding='utf-8'))
        assert state['status'] == 'CONSUMED' and state['database_ids'].get('ON')
        with connect(db) as connection:
            row = connection.execute('SELECT status,reserved_usd_micro FROM ar02_live_dispatches').fetchone()
            assert row['status'] == 'RESERVED' and row['reserved_usd_micro'] == 668_468
        body = json.loads(request.content)
        assert str(request.url) == 'https://api.deepseek.com/chat/completions'
        assert body['model'] == 'deepseek-flash' and body['thinking'] == {'type': 'disabled'}
        assert body['max_tokens'] == 2048 and body.get('stream', False) is False
        sent.append(body)
        return httpx.Response(200, json={'id': 'mock', 'object': 'chat.completion', 'created': 1,
            'model': 'deepseek-flash', 'choices': [{'index': 0, 'message': {'role': 'assistant', 'content': 'offline'}, 'finish_reason': 'stop'}],
            'usage': {'prompt_tokens': 4, 'completion_tokens': 2, 'total_tokens': 6}}, request=request)

    model = assistant.create_assistant_model(transport_async=httpx.MockTransport(reply),
                                             transport_sync=httpx.MockTransport(reply))
    token = assistant._AR04C_DISPATCH_CONTEXT.set({'experiment_id': EXP, 'db_path': str(db),
                                                  'memory_mode': 'ON', 'run_id': 'run-offline', 'logical_key': 'call-offline'})
    try:
        result = asyncio.run(model.ainvoke('offline only'))
    finally:
        assistant._AR04C_DISPATCH_CONTEXT.reset(token)
        asyncio.run(model.http_async_client.aclose())
        model.http_client.close()
    assert result.content == 'offline' and len(sent) == 1 and claim.exists()
    settled = ledger.complete_dispatch(db, experiment_id=EXP, run_id='run-offline', kind='MODEL',
                                       logical_key='call-offline', usage={'input_tokens': 4, 'output_tokens': 2, 'total_tokens': 6})
    assert settled['usage_state'] == 'KNOWN'
    assert ledger.read_budget(db, EXP)['provider_used'] == 1
    replacement = tmp_path / 'replacement.sqlite3'
    ledger.initialize_experiment(replacement, EXP)
    with pytest.raises(RuntimeError, match='CAMPAIGN_DATABASE_REPLAY'):
        assistant._ar04c_bind_campaign_database(replacement, 'ON')


def test_recheck_missing_authorization_and_wrong_mode_fail_closed(tmp_path, monkeypatch):
    auth, claim = _authorization(tmp_path, monkeypatch)
    auth.unlink()
    with pytest.raises(RuntimeError, match='AUTHORIZATION_INVALID'):
        assistant._ar04c_create_one_shot_claim()
    assert not claim.exists()
    monkeypatch.setenv('OPSPILOT_AR04C_MEMORY_MODE', 'OFF')
    with pytest.raises(RuntimeError, match='MEMORY_MODE'):
        assistant.assistant_memory_enabled_for_experiment(EXP)


def test_recheck_wrong_reservation_rejects_before_claim(tmp_path, monkeypatch):
    auth, claim = _authorization(tmp_path, monkeypatch)
    record = json.loads(auth.read_text(encoding='utf-8'))
    record['provider_reservation_usd_micro'] = 645_600
    auth.write_text(json.dumps(record), encoding='utf-8')
    with pytest.raises(RuntimeError, match='AUTHORIZATION_INVALID'):
        assistant._ar04c_create_one_shot_claim()
    assert not claim.exists()


def test_eight_settled_requests_exhaust_count_without_reset(tmp_path):
    from opspilot.domain.database import connect

    db = tmp_path / 'count.sqlite3'
    ledger.initialize_experiment(db, EXP)
    with connect(db) as connection:
        connection.execute('CREATE TABLE task_runs (run_id TEXT PRIMARY KEY)')
        connection.executemany('INSERT INTO task_runs VALUES (?)', [(f'run-{i}',) for i in range(9)])
    for i in range(8):
        ledger.reserve_dispatch(db, experiment_id=EXP, run_id=f'run-{i}', kind='MODEL', logical_key='one', request={})
        ledger.complete_dispatch(db, experiment_id=EXP, run_id=f'run-{i}', kind='MODEL', logical_key='one',
                                 usage={'input_tokens': 4, 'output_tokens': 2, 'total_tokens': 6})
    with pytest.raises(ledger.ExperimentBudgetError, match='PROVIDER_LIMIT'):
        ledger.reserve_dispatch(db, experiment_id=EXP, run_id='run-8', kind='MODEL', logical_key='one', request={})


def test_unknown_keeps_reservation_and_blocks_new_run(tmp_path):
    from opspilot.domain.database import connect

    db = tmp_path / 'unknown.sqlite3'
    ledger.initialize_experiment(db, EXP)
    with connect(db) as connection:
        connection.execute('CREATE TABLE task_runs (run_id TEXT PRIMARY KEY)')
        connection.executemany('INSERT INTO task_runs VALUES (?)', [('first',), ('second',)])
    ledger.reserve_dispatch(db, experiment_id=EXP, run_id='first', kind='MODEL', logical_key='one', request={})
    ledger.mark_unknown(db, experiment_id=EXP, run_id='first', kind='MODEL', logical_key='one', error_code='offline-unknown')
    saved = ledger.read_dispatch(db, experiment_id=EXP, run_id='first', kind='MODEL', logical_key='one')
    assert saved['status'] == 'UNKNOWN' and saved['reserved_usd_micro'] == 668_468
    with pytest.raises(ledger.ExperimentBudgetError, match='SPEND_BOUND_BREACHED'):
        ledger.reserve_dispatch(db, experiment_id=EXP, run_id='second', kind='MODEL', logical_key='two', request={})


def test_formal_worker_uses_scoped_mock_transport_and_mcp(tmp_path, monkeypatch):
    from opspilot.domain.database import connect
    import test_ar04c_real_journey_01 as journey

    _authorization(tmp_path, monkeypatch)
    assistant._ar04c_create_one_shot_claim()
    monkeypatch.setattr(journey, 'EXPERIMENT_ID', EXP)
    seed = journey._prepare_memory_seed(tmp_path / 'seed.sqlite3', tmp_path / 'seed-checkpoint.sqlite3',
                                        tmp_path / 'unused.sqlite3', tmp_path / 'on.sqlite3')
    db = tmp_path / 'on.sqlite3'
    ledger.initialize_experiment(db, EXP)
    original = journey._MockProvider

    class ScopedMock(original):
        async def handle(self, request):
            body = json.loads((await request.aread()).decode('utf-8'))
            state = json.loads(assistant._ar04c_claim_state_path().read_text(encoding='utf-8'))
            assert state['status'] == 'CONSUMED' and state['database_ids'].get('ON')
            with connect(self.db_path) as connection:
                rows = connection.execute("SELECT * FROM ar02_live_dispatches WHERE experiment_id=? AND kind='MODEL' AND status='RESERVED'", (EXP,)).fetchall()
                assert len(rows) == 1 and rows[0]['reserved_usd_micro'] == 668_468
                row = connection.execute("SELECT request_json FROM assistant_calls WHERE run_id=? AND kind='MODEL' ORDER BY created_at DESC LIMIT 1", (rows[0]['run_id'],)).fetchone()
            context = json.loads(row['request_json'])['context_budget']
            assert context['estimated_input_tokens'] <= 12000
            response = self._response_body(body)
            self.records.append({'url': str(request.url), 'method': request.method, 'body': body,
                                 'dispatch_id': rows[0]['dispatch_id'], 'reservation_before_transport_usd_micro': 668_468,
                                 'estimated_input_tokens': context.get('estimated_input_tokens'),
                                 'input_budget_tokens': context.get('input_budget_tokens'),
                                 'completion_id': response['id'], 'usage': response['usage']})
            return httpx.Response(200, json=response, request=request)

    monkeypatch.setattr(journey, '_MockProvider', ScopedMock)
    result = journey._run_condition(db, tmp_path / 'checkpoint.sqlite3', 'ON', seed['memory'], monkeypatch)
    assert result['task_budget']['model_limit'] == 8
    assert ledger.read_budget(db, EXP)['provider_used'] == 6
