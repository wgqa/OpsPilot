from __future__ import annotations

from pathlib import Path
import json
import os
import time

from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult
import pytest

from opspilot.domain.database import connect
from test_m1_web_api import _login, _session, web_client  # noqa: F401
from test_ar02_runtime import FixtureModel


QUESTION = '我们轮换了 API 凭据以后订单接口一直返回 401。你帮我调查一下，如果需要修复，告诉我后续怎么操作。'


def _ask(client: TestClient, session_id: str, headers: dict[str, str], key: str) -> str:
    response = client.post(f'/api/sessions/{session_id}/assistant/messages',
        headers={**headers, 'Idempotency-Key': key}, json={'body': QUESTION, 'task_id': None})
    assert response.status_code == 202, response.text
    return str(response.json()['message_id'])


def test_bridge_confirmed_task_links_original_message_and_is_idempotent(web_client: TestClient, demo_db: Path) -> None:
    headers = _login(web_client)[1]
    session = _session(web_client, headers)
    original = _ask(web_client, session, headers, 'bridge-question')
    with connect(demo_db) as db:
        assert db.execute('SELECT COUNT(*) FROM task_bindings').fetchone()[0] == 0
    body = {'initial_message': QUESTION, 'investigation_kind': 'AUTH_INCIDENT', 'source_message_id': original}
    url = f'/api/sessions/{session}/tasks'
    req = {**headers, 'Idempotency-Key': 'bridge-confirm-1'}
    first = web_client.post(url, headers=req, json=body)
    assert first.status_code == 202, first.text
    accepted = first.json()
    again = web_client.post(url, headers=req, json=body)
    assert again.status_code == 200 and again.json()['task_id'] == accepted['task_id']
    assert again.json()['message_id'] == accepted['message_id'] and again.json()['run_id'] == accepted['run_id']
    mismatch = web_client.post(url, headers=req, json={**body, 'initial_message': 'another operation'})
    assert mismatch.status_code == 409
    other = web_client.post(url, headers={**headers, 'Idempotency-Key': 'bridge-confirm-2'}, json=body)
    assert other.status_code == 202 and other.json()['task_id'] != accepted['task_id']
    messages = web_client.get(f'/api/sessions/{session}/messages').json()['items']
    initial = next(item for item in messages if item['message_id'] == accepted['message_id'])
    assert initial['investigation_origin_message_id'] == original
    assert initial['body'] == QUESTION
    assert web_client.get(f'/api/sessions/{session}/messages').json()['items'] == messages
    run = web_client.get(f"/api/runs/{accepted['run_id']}").json()
    assert run['source_message_id'] == accepted['message_id'] and run['task_id'] == accepted['task_id']
    assert run['execution_core'] == 'PROFESSIONAL_INVESTIGATOR'
    with connect(demo_db) as db:
        assert db.execute('SELECT COUNT(*) FROM task_bindings').fetchone()[0] == 2
        assert db.execute('SELECT COUNT(*) FROM d3_approvals').fetchone()[0] == 0
        assert db.execute('SELECT COUNT(*) FROM d3_action_ledgers').fetchone()[0] == 0


def test_formal_worker_investigates_same_session_through_real_mcp_and_http(
    demo_db: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    import opspilot.investigator as investigator
    from opspilot.domain.task_control import next_worker_run
    from opspilot.web.app import create_app
    from opspilot.web.worker import SingleInstanceWorker, _dispatch_run
    from test_m1_web_api import ORIGIN, PASSWORDS

    model_tool_choices: list[dict[str, object]] = []

    class OfflineS1Model:
        def __init__(self, *args, **kwargs):
            self.bound = False
            self.index = 0

        def bind_tools(self, *args, **kwargs):
            self.bound = True
            return self

        async def ainvoke(self, messages):
            if not self.bound:
                return AIMessage(content='{}')
            calls = [
                ('probe_endpoint', {'service_id': 'orders-demo', 'integration_id': 'integration-a'}),
                ('get_integration_config', {'integration_id': 'integration-a'}),
                ('get_principal_status', {'principal_id': 'principal-a'}),
                ('get_auth_policy', {'service_id': 'orders-demo'}),
            ]
            if self.index >= len(calls):
                return AIMessage(content='依据本次只读取证，凭据引用需要人工审阅。')
            name, arguments = calls[self.index]
            self.index += 1
            model_tool_choices.append({'name': name, 'arguments': arguments})
            return AIMessage(content='', tool_calls=[{'name': name, 'args': arguments, 'id': f'offline-{self.index}'}])

    class OfflineConversationModel(FixtureModel):
        def _generate(self, messages, stop=None, run_manager=None, **kwargs):
            answer = AIMessage(content='401 表示认证未通过。凭据轮换可能是线索，但当前还没有查询订单接口或确认原因；可以确认资源后进入受控调查。')
            answer.usage_metadata = {'input_tokens': 10, 'output_tokens': 5, 'total_tokens': 15}
            return ChatResult(generations=[ChatGeneration(message=answer)])

    monkeypatch.setattr(investigator, 'ChatOpenAI', OfflineS1Model)
    monkeypatch.setenv('OPSPILOT_MODEL_API_KEY', 'offline-placeholder')
    monkeypatch.setenv('OPSPILOT_MODEL_NAME', 'offline-deterministic-model')
    with connect(demo_db) as db:
        before = tuple(db.execute("SELECT credential_ref, config_version FROM integrations WHERE tenant_id='tenant-a' AND integration_id='integration-a'").fetchone())
    app = create_app(db_path=demo_db, checkpoint_db_path=tmp_path / 'bridge-cp.sqlite3',
        start_worker=False, credentials=PASSWORDS, expected_origin=ORIGIN, heartbeat_seconds=0.05,
        assistant_model_factory=lambda: OfflineConversationModel())

    def process_queued_run(expected_run_id: str) -> None:
        worker = SingleInstanceWorker(demo_db)
        worker.acquire()
        worker.register()
        try:
            selected = next_worker_run(demo_db)
            assert selected is not None and str(selected['run_id']) == expected_run_id
            import asyncio
            asyncio.run(_dispatch_run(
                demo_db, tmp_path / 'bridge-cp.sqlite3', worker.owner_id, 'executor-a', selected,
                worker_epoch=worker.epoch, assistant_model_factory=lambda: OfflineConversationModel(),
            ))
        finally:
            worker.release()

    with TestClient(app, raise_server_exceptions=False) as client:
        headers = _login(client)[1]
        session = _session(client, headers)
        assert client.get(f'/api/sessions/{session}').json()['s1_demo_resource'] == {
            'service_id': 'orders-demo', 'integration_id': 'integration-a', 'principal_id': 'principal-a'}
        question = client.post(f'/api/sessions/{session}/assistant/messages',
            headers={**headers, 'Idempotency-Key': 'journey-chat'}, json={'body': QUESTION, 'task_id': None})
        assert question.status_code == 202, question.text
        origin = question.json()['message_id']
        process_queued_run(str(question.json()['run_id']))
        created_response = client.post(f'/api/sessions/{session}/tasks',
            headers={**headers, 'Idempotency-Key': 'journey-confirm'},
            json={'initial_message': QUESTION, 'source_message_id': origin})
        assert created_response.status_code == 202, created_response.text
        created = created_response.json()
        run_id, task_id = created['run_id'], created['task_id']
        process_queued_run(str(run_id))
        run = client.get(f'/api/runs/{run_id}').json()
        inspector_response = client.get(f'/api/tasks/{task_id}/inspector')
        assert inspector_response.status_code == 200, inspector_response.text
        inspector = inspector_response.json()
        outcome = client.get(f'/api/tasks/{task_id}/outcome').json()
        messages = client.get(f'/api/sessions/{session}/messages').json()['items']
        initial = next(m for m in messages if m['message_id'] == created['message_id'])
        assert any(m['role'] == 'ASSISTANT' and m['answer_source_message_id'] == origin
            and '401' in m['body'] for m in messages)
        trace = {'evidence_level': 'DETERMINISTIC_MODEL_FORMAL_WORKER_REAL_LOCAL_MCP_HTTP_SQLITE',
            'session_id': session, 'origin_message_id': origin, 'task_id': task_id,
            'initial_message_id': created['message_id'], 'run_id': run_id,
            'run': run, 'trusted_state': inspector['trusted_state'],
            'evidence': inspector['evidence'], 'observations': inspector['observations'],
            'gate': inspector['current_gate'], 'outcome': outcome, 'messages': messages,
            'inspector_runs': inspector['runs'],
            'origin_readback': initial['investigation_origin_message_id']}
        print('AR05_JOURNEY_TRACE=' + json.dumps(trace, ensure_ascii=False, default=str), flush=True)
        if os.environ.get('AR05_TRACE_PATH'):
            Path(os.environ['AR05_TRACE_PATH']).write_text(json.dumps(trace, ensure_ascii=False, indent=2), encoding='utf-8')
        assert initial['investigation_origin_message_id'] == origin
        assert run['status'] == 'WAITING_APPROVAL', run
        assert inspector['trusted_state']['plan'] and len(inspector['evidence']) >= 4
        assert outcome['business_outcome'] == 'WAITING_APPROVAL' and outcome['plan']
        assert outcome['plan']['repair_action_type'] == 'SWITCH_CREDENTIAL_REF'
        assert outcome['plan']['verification_preview']['expected_http_status'] == 200
        assert outcome['repair'] is None and outcome['verification'] is None and outcome['delivery'] is None
        rejected_binding = client.post(f'/api/sessions/{session}/assistant/messages',
            headers={**headers, 'Idempotency-Key': 'invalid-s1-assistant-binding'},
            json={'body': '继续解释', 'task_id': task_id})
        assert rejected_binding.status_code >= 400
        ordinary = client.post(f'/api/sessions/{session}/assistant/messages',
            headers={**headers, 'Idempotency-Key': 'same-session-unbound-followup'},
            json={'body': '请继续解释调查结果的含义', 'task_id': None})
        assert ordinary.status_code == 202 and ordinary.json()['execution_core'] == 'ASSISTANT_V1'
        process_queued_run(str(ordinary.json()['run_id']))
        assert client.get(f"/api/runs/{ordinary.json()['run_id']}").json()['execution_core'] == 'ASSISTANT_V1'
        from opspilot.domain.assistant import read_session_professional_outcomes
        bridged_outcomes = read_session_professional_outcomes(demo_db, str(ordinary.json()['run_id']))
        s1_result = next(item for item in bridged_outcomes['items'] if item['task_id'] == task_id)
        assert s1_result['professional_type'] == 'S1_CONTROLLED_REPAIR'
        assert s1_result['business_outcome'] == 'WAITING_APPROVAL'
        assert s1_result['currentness'] == 'PERSISTED_OUTCOME_NOT_CURRENT_PROBE'
        assert s1_result['plan']['plan_hash'] == outcome['plan']['plan_hash']
        assert s1_result['source_refs']['plan_task_run_id'] == run_id
        assert len(s1_result['source_refs']['evidence_ids']) >= 4
        result_trace = {
            'evidence_level': 'DETERMINISTIC_MODEL_FORMAL_S1_WORKER_DOMAIN_PROJECTION',
            'provider_http_requests': 0,
            'task_id': task_id,
            'assistant_read_run_id': str(ordinary.json()['run_id']),
            'investigation_run_id': run_id,
            'business_outcome': s1_result['business_outcome'],
            'currentness': s1_result['currentness'],
            'plan': s1_result['plan'],
            'source_refs': s1_result['source_refs'],
        }
        result_trace_path = os.environ.get('PRODUCT_01_FINAL_BRIDGE_S1_TRACE_PATH')
        if result_trace_path:
            Path(result_trace_path).parent.mkdir(parents=True, exist_ok=True)
            Path(result_trace_path).write_text(json.dumps(result_trace, ensure_ascii=False, indent=2), encoding='utf-8')
        with connect(demo_db) as db:
            assert db.execute('SELECT COUNT(*) FROM d3_approvals').fetchone()[0] == 0
            assert db.execute('SELECT COUNT(*) FROM d3_action_ledgers').fetchone()[0] == 0
            assert db.execute('SELECT COUNT(*) FROM d3_action_intents').fetchone()[0] == 0
            assert db.execute('SELECT COUNT(*) FROM d3_ticket_resolution_entries').fetchone()[0] == 0
            assert tuple(db.execute("SELECT credential_ref, config_version FROM integrations WHERE tenant_id='tenant-a' AND integration_id='integration-a'").fetchone()) == before
            assert db.execute('SELECT COUNT(*) FROM assistant_runs WHERE run_id=?', (run_id,)).fetchone()[0] == 0
            assert db.execute('SELECT COUNT(*) FROM assistant_runs WHERE run_id=?', (ordinary.json()['run_id'],)).fetchone()[0] == 1

        first_approval = client.post(
            f"/api/tasks/{task_id}/plans/{outcome['plan']['plan_hash']}/approval",
            headers={**_login(client, 'approver-a')[1], 'Idempotency-Key': 'ar05-close-approval-1'},
            json={'decision': 'APPROVED'},
        )
        assert first_approval.status_code == 202, first_approval.text
        first_resume_id = str(first_approval.json()['resume_run_id'])
        with connect(demo_db) as db:
            db.execute(
                "UPDATE integrations SET config_version = config_version + 1 "
                "WHERE tenant_id='tenant-a' AND integration_id='integration-a'"
            )
        process_queued_run(first_resume_id)
        first_resume = client.get(f'/api/runs/{first_resume_id}').json()
        assert first_resume['status'] == 'WAITING_APPROVAL', first_resume
        headers = _login(client, 'support-a')[1]
        refreshed = client.get(f'/api/tasks/{task_id}/outcome', headers=headers).json()
        assert refreshed.get('business_outcome') == 'REAPPROVAL_REQUIRED', refreshed
        assert refreshed['repair'] is None and refreshed['delivery'] is None
        with connect(demo_db) as db:
            assert db.execute('SELECT COUNT(*) FROM d3_action_intents WHERE task_id=?', (task_id,)).fetchone()[0] == 0
            assert db.execute('SELECT COUNT(*) FROM d3_action_ledgers WHERE task_id=?', (task_id,)).fetchone()[0] == 0

        second_approval = client.post(
            f"/api/tasks/{task_id}/plans/{refreshed['plan']['plan_hash']}/approval",
            headers={**_login(client, 'approver-a')[1], 'Idempotency-Key': 'ar05-close-approval-2'},
            json={'decision': 'APPROVED'},
        )
        assert second_approval.status_code == 202, second_approval.text
        second_resume_id = str(second_approval.json()['resume_run_id'])
        process_queued_run(second_resume_id)
        headers = _login(client, 'support-a')[1]
        second_resume = client.get(f'/api/runs/{second_resume_id}', headers=headers).json()
        assert second_resume['status'] == 'SUCCEEDED', second_resume
        final_outcome = client.get(f'/api/tasks/{task_id}/outcome', headers=headers).json()
        assert final_outcome['business_outcome'] == 'DELIVERED'
        assert final_outcome['verification']['response_status'] == 200
        assert final_outcome['verification']['recovery_verified'] is True
        with connect(demo_db) as db:
            final_configuration = dict(db.execute(
                "SELECT credential_ref, config_version FROM integrations "
                "WHERE tenant_id='tenant-a' AND integration_id='integration-a'"
            ).fetchone())
            runs = [dict(row) for row in db.execute(
                "SELECT run_id, kind, status, source_message_id FROM task_runs "
                "WHERE task_id=? ORDER BY created_at, rowid", (task_id,),
            ).fetchall()]
            observations = [dict(row) for row in db.execute(
                "SELECT observation_id, tool_name, status, evidence_id, result_digest "
                "FROM d2_tool_observations WHERE task_id=? ORDER BY created_at, rowid", (task_id,),
            ).fetchall()]
            revalidations = [dict(row) for row in db.execute(
                "SELECT receipt_id, plan_hash, approval_id, run_id, status, reason_code, "
                "evidence_ids_json, content_digest FROM d3_revalidation_receipts "
                "WHERE task_id=? ORDER BY observed_at, rowid", (task_id,),
            ).fetchall()]
            ledgers = [dict(row) for row in db.execute(
                "SELECT ledger_id, action_id, action_kind, status, before_version, after_version "
                "FROM d3_action_ledgers WHERE task_id=? ORDER BY committed_at, rowid", (task_id,),
            ).fetchall()]
            verification = dict(db.execute(
                "SELECT verification_id, response_status, recovery_verified, result_digest "
                "FROM d3_verification_receipts WHERE task_id=?", (task_id,),
            ).fetchone())
            delivery = dict(db.execute(
                "SELECT delivery_id, report_ref, ticket_entry_id, payload_digest "
                "FROM d3_delivery_records WHERE task_id=?", (task_id,),
            ).fetchone())
            report = dict(db.execute(
                "SELECT report_ref, content_digest, created_at FROM d3_report_artifacts WHERE task_id=?",
                (task_id,),
            ).fetchone())
            assert final_configuration == {'credential_ref': 'cred-v2', 'config_version': 9}
            assert len([item for item in ledgers if item['action_kind'] == 'REPAIR']) == 1
            assert len([item for item in ledgers if item['action_kind'] == 'DELIVER']) == 1
            assert sum(item['status'] == 'REAPPROVAL_REQUIRED' for item in revalidations) == 1
            assert sum(item['status'] == 'VALID' for item in revalidations) == 1
        final_messages = client.get(f'/api/sessions/{session}/messages', headers=headers).json()['items']
        final_origin = next(item for item in final_messages if item['message_id'] == origin)
        task_message = next(item for item in final_messages if item['message_id'] == created['message_id'])
        assert final_origin['role'] == 'USER' and final_origin['body'] == QUESTION
        assert task_message['investigation_origin_message_id'] == origin
        final_answer = next(
            item for item in final_messages
            if item['role'] == 'ASSISTANT' and item['answer_source_message_id'] == origin
        )
        close_trace = {
            'evidence_level': 'DETERMINISTIC_FORMAL_API_WORKER_REAL_LOCAL_MCP_HTTP_SQLITE',
            'user_goal': QUESTION,
            'session_id': session,
            'origin_message_id': origin,
            'task_initial_message_id': created['message_id'],
            'task_id': task_id,
            'investigation_run_id': run_id,
            'approval_resume_runs': [first_resume_id, second_resume_id],
            'model_tool_choices': model_tool_choices,
            'trusted_observations': observations,
            'approval_revalidation_receipts': revalidations,
            'runs': runs,
            'plan_hashes': [outcome['plan']['plan_hash'], refreshed['plan']['plan_hash']],
            'repair_and_delivery_ledgers': ledgers,
            'verification_receipt': verification,
            'frozen_report': report,
            'delivery_receipt': delivery,
            'assistant_answer': {
                'message_id': final_answer['message_id'],
                'source_message_id': final_answer['answer_source_message_id'],
                'body': final_answer['body'],
                'kind': final_answer['answer_kind'],
            },
            'session_message_readback': {
                'origin_message_id': final_origin['message_id'],
                'task_message_id': task_message['message_id'],
                'investigation_origin_message_id': task_message['investigation_origin_message_id'],
                'task_message_body': task_message['body'],
            },
            'final_outcome': final_outcome['business_outcome'],
            'final_configuration': final_configuration,
            'provider_http_requests': 0,
            'provider_note': 'Both model interfaces were deterministic local substitutes; no Provider client was used.',
            'external_business_writes': 0,
            'isolated_demo_writes': {'repair_commits': 1, 'ticket_entries': 1},
            'browser': 'NOT_RUN_HISTORICAL_STOP',
        }
        if os.environ.get('AR05_D3_CLOSE_TRACE_PATH'):
            Path(os.environ['AR05_D3_CLOSE_TRACE_PATH']).write_text(
                json.dumps(close_trace, ensure_ascii=False, indent=2, default=str), encoding='utf-8',
            )
        print('AR05_D3_CLOSE_TRACE=' + json.dumps(close_trace, ensure_ascii=False, default=str), flush=True)
        with connect(demo_db) as db:
            db.execute("UPDATE d3_plans SET canonical_plan_json=canonical_plan_json || ' ' WHERE task_id=?", (task_id,))
        assert client.get(f'/api/tasks/{task_id}/outcome').status_code >= 400
def test_bridge_refuses_foreign_session_origin_and_approver(web_client: TestClient, demo_db: Path) -> None:
    headers = _login(web_client)[1]
    session = _session(web_client, headers)
    other_session = _session(web_client, headers)
    original = _ask(web_client, other_session, headers, 'other-session-question')
    denied = web_client.post(f'/api/sessions/{session}/tasks',
        headers={**headers, 'Idempotency-Key': 'foreign-origin'},
        json={'initial_message': QUESTION, 'source_message_id': original})
    assert denied.status_code in (403, 404), denied.text
    approver = TestClient(web_client.app, raise_server_exceptions=False)
    try:
        approver_headers = _login(approver, 'approver-a')[1]
        response = approver.post(f'/api/sessions/{session}/tasks',
            headers={**approver_headers, 'Idempotency-Key': 'not-support'},
            json={'initial_message': QUESTION, 'source_message_id': original})
        assert response.status_code == 403
    finally:
        approver.close()
    with connect(demo_db) as db:
        assert db.execute('SELECT COUNT(*) FROM task_bindings').fetchone()[0] == 0


def test_bridge_denies_cross_tenant_and_refuses_tampered_origin(web_client: TestClient, demo_db: Path) -> None:
    headers_a = _login(web_client)[1]
    session_a = _session(web_client, headers_a)
    original = _ask(web_client, session_a, headers_a, 'tenant-a-original')
    other = TestClient(web_client.app, raise_server_exceptions=False)
    try:
        headers_b = _login(other, 'support-b')[1]
        session_b = _session(other, headers_b)
        denied = other.post(f'/api/sessions/{session_b}/tasks',
            headers={**headers_b, 'Idempotency-Key': 'cross-tenant-origin'},
            json={'initial_message': QUESTION, 'source_message_id': original})
        assert denied.status_code in (403, 404)
        assert other.get(f'/api/sessions/{session_a}/messages').status_code == 404
    finally:
        other.close()
    accepted = web_client.post(f'/api/sessions/{session_a}/tasks',
        headers={**headers_a, 'Idempotency-Key': 'correct-origin'},
        json={'initial_message': QUESTION, 'source_message_id': original})
    assert accepted.status_code == 202, accepted.text
    with connect(demo_db) as db:
        db.execute("UPDATE chat_message_sources SET source_digest='tampered' WHERE message_id=?", (accepted.json()['message_id'],))
    items = web_client.get(f'/api/sessions/{session_a}/messages').json()['items']
    linked = next(item for item in items if item['message_id'] == accepted.json()['message_id'])
    assert linked['investigation_origin_message_id'] is None
