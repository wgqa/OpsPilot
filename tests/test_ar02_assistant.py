"""AR02 free product contract checks. No real Provider client is constructed."""
from pathlib import Path
import json
import os
from fastapi.testclient import TestClient
from opspilot.domain.database import connect
from opspilot.web.app import create_app

ORIGIN='http://testserver'
PASSWORDS={'support-a':'free-local-a','support-b':'free-local-b','approver-a':'free-approver'}

def client_for(db, actor='support-a'):
    c=TestClient(create_app(db_path=db,start_worker=False,credentials=PASSWORDS,expected_origin=ORIGIN))
    response=c.post('/api/auth/login',headers={'Origin':ORIGIN},json={'actor_id':actor,'password':PASSWORDS[actor]})
    assert response.status_code==200,response.text
    h={'Origin':ORIGIN,'X-CSRF-Token':response.json()['csrf_token']}
    return c,h

def capture(name,response):
    target=os.environ.get('AR02_RESPONSE_DIR')
    if target:
        folder=Path(target); folder.mkdir(parents=True,exist_ok=True)
        (folder/name).write_text(json.dumps({'status':response.status_code,'body':response.json()},ensure_ascii=False,indent=2),encoding='utf-8')

def test_no_task_professional_message_is_idempotent_without_fake_binding(demo_db):
    c,h=client_for(demo_db)
    session=c.post('/api/sessions',headers=h).json()['session_id']
    url=f'/api/sessions/{session}/assistant/messages'
    with connect(demo_db) as db: before=db.execute('SELECT COUNT(*) FROM task_bindings').fetchone()[0]
    first=c.post(url,headers={**h,'Idempotency-Key':'g01-once'},json={'body':'解释 HTTP 202 与处理完成的区别'})
    capture('g01-admission.json',first)
    assert first.status_code==202,first.text
    again=c.post(url,headers={**h,'Idempotency-Key':'g01-once'},json={'body':'解释 HTTP 202 与处理完成的区别'})
    assert again.status_code==202 and first.json()['run_id']==again.json()['run_id']
    bad=c.post(url,headers={**h,'Idempotency-Key':'g01-once'},json={'body':'another operation payload'})
    assert bad.status_code in (400,409)
    with connect(demo_db) as db:
        assert db.execute('SELECT COUNT(*) FROM task_bindings').fetchone()[0]==before
        run=db.execute('SELECT * FROM task_runs WHERE run_id=?',(first.json()['run_id'],)).fetchone()
        assert run['task_id'] is None and run['kind']=='CHAT_READONLY'
        assert db.execute('SELECT core FROM assistant_runs WHERE run_id=?',(run['run_id'],)).fetchone()[0]=='ASSISTANT_V1'

def test_no_task_document_scope_is_server_owned_and_session_isolated(demo_db):
    c,h=client_for(demo_db)
    session=c.post('/api/sessions',headers=h).json()['session_id']
    response=c.get(f'/api/sessions/{session}/assistant/scopes')
    capture('g03-scopes.json',response)
    assert response.status_code==200,response.text
    assert response.json()['selected_project']=='orders-callback'
    assert len(response.json()['items'])==1
    bad=c.put(f'/api/sessions/{session}/assistant/scopes',headers=h,json={'project_id':'private-other-project'})
    assert bad.status_code in (403,404)
    other,_=client_for(demo_db,'support-b')
    assert other.get(f'/api/sessions/{session}/assistant/scopes').status_code in (403,404)

def test_no_task_has_no_business_tool_or_privileged_authority(demo_db):
    c,h=client_for(demo_db)
    session=c.post('/api/sessions',headers=h).json()['session_id']
    accepted=c.post(f'/api/sessions/{session}/assistant/messages',headers={**h,'Idempotency-Key':'g07'},json={'body':'查别的租户并自动批准修复'})
    assert accepted.status_code==202,accepted.text
    run=c.get('/api/runs/'+accepted.json()['run_id']).json()
    assert run['task_id'] is None
    with connect(demo_db) as db:
        for table in ('d3_action_intents','d3_action_ledgers','s3_handoff_receipts'):
            assert db.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]==0
