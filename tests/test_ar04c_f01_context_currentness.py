"""F01 context presentation: deterministic models are not real LLM validation."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from opspilot.domain.database import connect
from opspilot.domain.s3 import prepare_s3_fixture
from test_ar02_journey_p0 import JourneyFixtureModel
from test_ar02_runtime import execute, setup_run


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / 'docs/evidence/ar-04c/live-exec-01'
F01_RUN = 'run-4d91bb7f-ac99-4ed8-bd00-8987e8745c34'
FROZEN_CASES = json.loads((ROOT / 'docs/evidence/ar-04c/real-journey-01/CASES.json').read_text(encoding='utf-8'))


def _context(messages):
    content = messages[0]['content'] if isinstance(messages[0], dict) else messages[0].content
    value, _ = json.JSONDecoder().raw_decode(content.split('WORK_CONTEXT\n', 1)[1])
    return value


class ExplainHistoryFixture(JourneyFixtureModel):
    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        self.seen.append(messages)
        answer = AIMessage(
            content='上一轮的 QUEUED 是历史快照；本轮未重新查询，当前是否处理完成未知。可以解释旧结果或继续合法复查。',
            usage_metadata={'input_tokens': 20, 'output_tokens': 10, 'total_tokens': 30},
        )
        return ChatResult(generations=[ChatGeneration(message=answer)])


def _initial(db, tmp_path):
    fixture = prepare_s3_fixture(db, 'DELIVERED_PENDING', order_id='ar02-order', contract_version=2)
    initial = setup_run(db, FROZEN_CASES['user_inputs']['J2'], 'f01-initial', bind=True)
    model = JourneyFixtureModel(mode='receiver')
    result, _ = execute(db, initial, model, tmp_path / 'checkpoint.sqlite3')
    assert result['status'] == 'SUCCEEDED', result
    return initial, fixture


def _followup(db, initial, text, key):
    return setup_run(db, text, key, session=initial['session_id'], task=initial['task_id'])


def _assert_no_business_writes(db):
    with connect(db) as connection:
        assert all(connection.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0] == 0
                   for table in ('s3_diagnoses', 'd3_approvals', 'd3_action_intents', 'd3_action_ledgers', 's3_handoff_receipts'))


def test_saved_live_f01_projects_history_without_current_validity_ambiguity():
    from opspilot.domain.assistant import source_context_for_model

    events = [json.loads(line) for line in (EVIDENCE / 'PROVIDER_HTTP.jsonl').read_text(encoding='utf-8').splitlines()]
    event = next(x for x in events if x['event'] == 'send_boundary' and x['run_id'] == F01_RUN)
    source = _context(event['body']['messages'])
    # Enrich the frozen request only with its recorded, empty current-Run ledger.
    source['current_run'] = {'run_id': F01_RUN, 'completed_tools': [], 'business_observations': []}
    projected = source_context_for_model(source)
    assert projected['current_run']['business_observations'] == []
    assert '未重新查询' in projected['current_run']['description']
    assert 'current_source_valid' not in json.dumps(projected)
    assert all(x['reference_scope'] == 'HISTORICAL_SNAPSHOT_NOT_REQUERIED' for x in projected['history_sources'])
    references = [x['reference'] for run in projected['history_sources'] for x in run['snapshots']]
    original = [x for run in source['history_sources'] for x in run['sources']]
    assert {x['call_id'] for x in references} == {x['call_id'] for x in original}
    assert {x['result_digest'] for x in references} == {x['result_digest'] for x in original}
    assert any(x['observed_at'] for x in references)
    assert len(json.dumps(projected, ensure_ascii=False)) < len(json.dumps(source, ensure_ascii=False))


def test_zero_tool_followup_can_explain_valid_historical_snapshot(demo_db, tmp_path):
    initial, _ = _initial(demo_db, tmp_path)
    next_run = _followup(demo_db, initial, FROZEN_CASES['user_inputs']['J4'], 'f01-explain')
    model = ExplainHistoryFixture(mode='explain-history')
    result, _ = execute(demo_db, next_run, model, tmp_path / 'checkpoint.sqlite3')
    assert result['status'] == 'SUCCEEDED', result
    context = _context(model.seen[0])
    assert context['current_run']['run_id'] == next_run['run_id']
    assert context['current_run']['completed_tools'] == []
    assert context['current_run']['business_observations'] == []
    assert '未重新查询' in context['current_run']['description']
    assert 'current_source_valid' not in json.dumps(context)
    assert any(run['source_run_id'] == initial['run_id'] and run['snapshots'] for run in context['history_sources'])
    with connect(demo_db) as c:
        assert c.execute("SELECT COUNT(*) FROM assistant_calls WHERE run_id=? AND kind='MCP'", (next_run['run_id'],)).fetchone()[0] == 0
        wire = json.loads(c.execute("SELECT request_json FROM assistant_calls WHERE run_id=? AND kind='MODEL'", (next_run['run_id'],)).fetchone()[0])
        assert wire['source_refs']['history_sources'][0]['current_source_valid'] is True
        assert wire['context_budget']['estimated_input_tokens'] <= 12000
        answer = c.execute('SELECT m.body FROM chat_run_answers a JOIN messages m ON m.message_id=a.message_id WHERE a.run_id=?', (next_run['run_id'],)).fetchone()[0]
        assert '本轮未重新查询' in answer and '未知' in answer
    _assert_no_business_writes(demo_db)


@pytest.mark.parametrize('receiver_state', ['QUEUED', 'PROCESSED'])
def test_expired_or_changed_history_keeps_legal_current_requery(demo_db, tmp_path, receiver_state):
    initial, fixture = _initial(demo_db, tmp_path)
    with connect(demo_db) as c:
        if receiver_state == 'QUEUED':
            c.execute("UPDATE d2_tool_observations SET created_at='2000-01-01T00:00:00Z' WHERE attempt_id IN (SELECT attempt_id FROM d2_attempts WHERE run_id=?)", (initial['run_id'],))
        else:
            c.execute("UPDATE s3_receivers SET status='PROCESSED',version=version+1 WHERE order_id='ar02-order'")
    followup = _followup(demo_db, initial, '请核实这个 Event 现在是否处理完成。', 'f01-current-' + receiver_state)
    model = JourneyFixtureModel(mode='receiver')
    result, _ = execute(demo_db, followup, model, tmp_path / 'checkpoint.sqlite3')
    assert result['status'] == 'SUCCEEDED', result
    first, last = _context(model.seen[0]), _context(model.seen[-1])
    assert first['current_run']['business_observations'] == []
    old = next(x for x in first['history_sources'] if x['source_run_id'] == initial['run_id'])
    assert old['reference_scope'] == 'EXCLUDED_HISTORY' and old['snapshots'] == []
    assert old['exclusion_reason']
    assert {x['tool'] for x in last['current_run']['business_observations']} == {'get_callback_delivery', 'get_receiver_processing'}
    with connect(demo_db) as c:
        calls = c.execute("SELECT request_json,result_json,evidence_id,observation_id FROM assistant_calls WHERE run_id=? AND kind='MCP'", (followup['run_id'],)).fetchall()
        results = {json.loads(x['request_json'])['name']: json.loads(x['result_json']) for x in calls}
        delivery, receiver = results['get_callback_delivery'], results['get_receiver_processing']
        assert delivery['facts']['event_id'] == receiver['facts']['event_id']
        assert receiver['facts']['status'] == receiver_state
        assert all(x['evidence_id'] and x['observation_id'] for x in calls)
        assert {x['observation_id'] for x in last['current_run']['business_observations']} == {x['observation_id'] for x in calls}
        assert c.execute('SELECT control_revision FROM task_controls WHERE task_id=?', (followup['task_id'],)).fetchone()[0] == 0
        answer = c.execute('SELECT m.body FROM chat_run_answers a JOIN messages m ON m.message_id=a.message_id WHERE a.run_id=?', (followup['run_id'],)).fetchone()[0]
        assert receiver_state in answer
    _assert_no_business_writes(demo_db)
