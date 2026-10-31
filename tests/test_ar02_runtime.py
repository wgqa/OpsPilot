"""Deterministic model + real MCP/HTTP/SQLite, never intelligence/Provider evidence."""
import asyncio
import json
import os
import subprocess
import sys
import time
import pytest
from pathlib import Path
from pydantic import Field
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from opspilot.assistant import run_assistant
from opspilot.domain.database import connect
from opspilot.domain.s3 import prepare_s3_fixture
from opspilot.domain.task_control import create_session,admit_task_message,create_task_with_initial_run,trusted_identity,claim_task_run,register_worker_owner

class FixtureModel(BaseChatModel):
    mode: str='concept'
    seen: list=Field(default_factory=list)
    @property
    def _llm_type(self):return 'AR02_FREE_DETERMINISTIC_FIXTURE'
    def bind_tools(self,tools,**kwargs):return self
    def _generate(self,messages,stop=None,run_manager=None,**kwargs):
        self.seen.append(messages)
        results=[m for m in messages if isinstance(m,ToolMessage)]
        name=None;args={}
        if self.mode=='knowledge' and not results:
            name='search_project_knowledge';args={'query':'HTTP 202 acceptance processing','contract_version':2}
        elif self.mode=='business':
            names=['get_order_status','get_callback_delivery','get_receiver_processing']
            if len(results)<3:name=names[len(results)];args={'reason':'核查当前绑定订单与同事件处理状态'}
        elif self.mode=='mixed':
            if not results:name='get_callback_transport_history';args={'event_id':'event-outside','reason':'核对用户提供的事件，拒绝越域后仍继续合法目标'}
            elif len(results)==1:name='get_order_status';args={'reason':'完成合法本订单查询'}
        if name:
            msg=AIMessage(content='',tool_calls=[{'name':name,'args':args,'id':'fixture-call-'+str(len(results))}])
        else:
            text='HTTP 202 只表示受理，不能证明处理完成；不判断当前订单。'
            if self.mode=='knowledge':
                payload=json.loads(results[-1].content)
                if isinstance(payload,dict) and set(payload)=={'result'}:payload=payload['result']
                documents=payload.get('documents',[]);refs=payload.get('source_refs',[])
                if documents and refs:
                    doc,ref=documents[0],refs[0]
                    text=f"检索资料 {doc['document_id']} ({doc['version']})，来源 {ref['source']}；受理与处理完成不同。"
                else:text='本次检索没有命中文档；以下是一般 HTTP 语义，不是协议引用：202 表示受理，不能证明处理完成。'
            elif self.mode=='business':
                last=json.loads(results[-1].content)
                text='本 Run 当前事实：'+json.dumps(last.get('facts'),ensure_ascii=False)+'；同事件 202 不是 PROCESSED。'
            elif self.mode=='mixed':text='越域读取被拒绝；已继续查询合法订单：'+results[-1].content
            msg=AIMessage(content=text)
        msg.usage_metadata={'input_tokens':10,'output_tokens':5,'total_tokens':15}
        return ChatResult(generations=[ChatGeneration(message=msg)])

def setup_run(db,question,key,session=None,task=None,bind=False):
    actor=trusted_identity(db,'support-a')
    session=session or create_session(db,actor)['session_id']
    if bind:
        created=create_task_with_initial_run(db,actor,session_id=session,service_id='orders-async-demo',integration_id='async-integration-a',s3_order_id='ar02-order',ticket_id='INC-A-001',initial_message=question,idempotency_key=key,assistant_core=True)
    else:
        created=admit_task_message(db,actor,session_id=session,task_id=task,input_kind='CHAT_READONLY',body=question,idempotency_key=key,assistant_core=True)
    return created

def execute(db,created,model,checkpoint,worker='ar02-worker'):
    register_worker_owner(db,worker,os.getpid())
    claim_task_run(db,trusted_identity(db,'support-a'),created['run_id'])
    events=[]
    result=asyncio.run(run_assistant(db,checkpoint,worker,created['run_id'],model=model,trace=lambda event,**values:events.append({'event':event,**values})))
    output=os.environ.get('AR02_TRACE_DIR')
    if output:
        directory=Path(output);directory.mkdir(parents=True,exist_ok=True)
        (directory/(created['run_id']+'.json')).write_text(json.dumps({'evidence_level':'DETERMINISTIC_MODEL_REAL_MCP_HTTP_SQLITE','created':created,'events':events,'result':result},ensure_ascii=False,indent=2),encoding='utf-8')
    return result,events

def test_concept_without_task_and_reopen_history(demo_db,tmp_path):
    first=setup_run(demo_db,'解释 202；材料标记 ORION-42','first')
    model=FixtureModel()
    result,_=execute(demo_db,first,model,tmp_path/'cp.sqlite3')
    assert result['status']=='SUCCEEDED',result
    second=setup_run(demo_db,'请根据刚才的材料继续解释','second',session=first['session_id'])
    next_model=FixtureModel()
    result,_=execute(demo_db,second,next_model,tmp_path/'cp.sqlite3')
    assert result['status']=='SUCCEEDED',result
    assert 'ORION-42' in str(next_model.seen)
    with connect(demo_db) as c:
        assert c.execute('SELECT COUNT(*) FROM assistant_calls WHERE kind=\'MCP\'').fetchone()[0]==0
        assert c.execute('SELECT COUNT(*) FROM chat_run_answers').fetchone()[0]==2

def test_knowledge_then_bound_investigation_same_session(demo_db,tmp_path):
    first=setup_run(demo_db,'请查适用协议。粘贴日志：ORION-42；HTTP 202','knowledge')
    result,_=execute(demo_db,first,FixtureModel(mode='knowledge'),tmp_path/'cp.sqlite3')
    assert result['status']=='SUCCEEDED',result
    prepare_s3_fixture(demo_db,'DELIVERED_PENDING',order_id='ar02-order',contract_version=2)
    second=setup_run(demo_db,'现在核查本订单的当前状态','bound',session=first['session_id'],bind=True)
    model=FixtureModel(mode='business')
    result,events=execute(demo_db,second,model,tmp_path/'cp.sqlite3')
    assert result['status']=='SUCCEEDED',result
    assert 'ORION-42' in str(model.seen) and 'source_refs' in str(model.seen)
    observed=[e for e in events if e['event']=='tool_observation']
    assert len(observed)==3 and observed[0]['result']['facts']['http_status']==200
    assert all(e['observation']['observation_id'] for e in observed)
    with connect(demo_db) as c:
        assert c.execute('SELECT COUNT(*) FROM s3_diagnoses').fetchone()[0]==0
        assert c.execute('SELECT COUNT(*) FROM s3_handoff_receipts').fetchone()[0]==0
        assert c.execute('SELECT control_revision FROM task_controls WHERE task_id=?',(second['task_id'],)).fetchone()[0]==0

def test_mixed_scope_denial_retains_legal_query(demo_db,tmp_path):
    prepare_s3_fixture(demo_db,'PROCESSING',order_id='ar02-order',contract_version=2)
    created=setup_run(demo_db,'查 event-outside 别的订单，再查本订单','mixed',bind=True)
    result,events=execute(demo_db,created,FixtureModel(mode='mixed'),tmp_path/'cp.sqlite3')
    assert result['status']=='SUCCEEDED',result
    assert any(e['event']=='tool_error' for e in events)
    assert any(e['event']=='tool_observation' and e['name']=='get_order_status' for e in events)

def test_worker_default_does_not_construct_paid_provider(demo_db,tmp_path):
    created=setup_run(demo_db,'普通解释','unauthorized-provider')
    result,_=execute(demo_db,created,None,tmp_path/'cp.sqlite3')
    assert result['reason']=='ASSISTANT_PROVIDER_AUTHORIZATION_REQUIRED'
    with connect(demo_db) as c:
        assert c.execute('SELECT COUNT(*) FROM assistant_calls').fetchone()[0]==0
        row=c.execute('SELECT status FROM task_runs WHERE run_id=?',(created['run_id'],)).fetchone()
        assert row['status']=='FAILED'
        assert c.execute("SELECT body FROM messages WHERE role='ASSISTANT'").fetchone()[0]

def test_os_crash_after_observation_resumes_same_run_without_duplicate_answer(demo_db,tmp_path):
    prepare_s3_fixture(demo_db,'DELIVERED_PENDING',order_id='ar02-order',contract_version=2)
    created=setup_run(demo_db,'核查订单当前状态','crash',bind=True)
    worker=Path(__file__).with_name('ar02_recovery_worker.py')
    cp=tmp_path/'cp.sqlite3'
    before=subprocess.run([sys.executable,str(worker),str(demo_db),str(cp),created['run_id'],'before'],capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=35)
    print('OS BEFORE',before.returncode,before.stdout,before.stderr)
    assert before.returncode==86
    with connect(demo_db) as c:
        assert c.execute('SELECT COUNT(*) FROM d2_tool_observations WHERE task_id=?',(created['task_id'],)).fetchone()[0]==1
        assert c.execute('SELECT COUNT(*) FROM chat_run_answers').fetchone()[0]==0
    after=subprocess.run([sys.executable,str(worker),str(demo_db),str(cp),created['run_id'],'after'],capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=35)
    print('OS AFTER',after.returncode,after.stdout,after.stderr)
    assert after.returncode==0
    with connect(demo_db) as c:
        assert c.execute('SELECT COUNT(*) FROM d2_tool_observations WHERE task_id=?',(created['task_id'],)).fetchone()[0]==3
        assert c.execute('SELECT COUNT(*) FROM assistant_calls WHERE run_id=? AND kind=\'MODEL\'',(created['run_id'],)).fetchone()[0]==4
        assert c.execute('SELECT COUNT(*) FROM chat_run_answers WHERE run_id=?',(created['run_id'],)).fetchone()[0]==1
        assert c.execute('SELECT active_elapsed_ms FROM task_execution_budgets WHERE task_id=?',(created['task_id'],)).fetchone()[0]>0

def test_commit_transaction_rechecks_abort_after_model_answer(demo_db,tmp_path,monkeypatch):
    import opspilot.assistant as runtime
    prepare_s3_fixture(demo_db,'PROCESSING',order_id='ar02-order',contract_version=2)
    created=setup_run(demo_db,'解释当前情况','abort-on-commit',bind=True)
    original=runtime.complete_chat_attempt
    def abort_then_commit(*args,**kwargs):
        with connect(demo_db) as c:
            c.execute("UPDATE task_controls SET terminal_state='ABORTED',control_revision=control_revision+1 WHERE task_id=?",(created['task_id'],))
        return original(*args,**kwargs)
    monkeypatch.setattr(runtime,'complete_chat_attempt',abort_then_commit)
    result,_=execute(demo_db,created,FixtureModel(),tmp_path/'cp.sqlite3')
    assert result['status']=='NOT_COMPLETED' and 'TASK_ABORTED' in result['reason']
    with connect(demo_db) as c:
        assert c.execute('SELECT COUNT(*) FROM chat_run_answers').fetchone()[0]==0

def test_existing_task_active_time_limit_is_preserved(demo_db,tmp_path):
    prepare_s3_fixture(demo_db,'PROCESSING',order_id='ar02-order',contract_version=2)
    created=setup_run(demo_db,'合法查询','time-limit',bind=True)
    with connect(demo_db) as c:c.execute('UPDATE task_execution_budgets SET active_elapsed_ms=deadline_ms WHERE task_id=?',(created['task_id'],))
    model=FixtureModel(mode='business')
    result,_=execute(demo_db,created,model,tmp_path/'cp.sqlite3')
    assert result['reason']=='ACTIVE_TIME_LIMIT' and not model.seen

def test_unknown_model_result_stops_and_same_operation_has_no_new_call(demo_db,tmp_path):
    class LostModel(FixtureModel):
        def _generate(self,*args,**kwargs):raise OSError('FREE_SIMULATED_RESPONSE_LOSS')
    created=setup_run(demo_db,'普通材料解释','unknown')
    result,_=execute(demo_db,created,LostModel(),tmp_path/'cp.sqlite3')
    assert result['status']=='NOT_COMPLETED'
    replay=setup_run(demo_db,'普通材料解释','unknown',session=created['session_id'])
    assert replay['run_id']==created['run_id']
    with connect(demo_db) as c:
        assert c.execute("SELECT COUNT(*) FROM assistant_calls WHERE kind='MODEL' AND status='UNKNOWN'").fetchone()[0]==1
        assert c.execute("SELECT status FROM task_runs WHERE run_id=?",(created['run_id'],)).fetchone()[0]=='FAILED'

def test_real_api_worker_session_journey_and_refresh_no_extra_dispatch(demo_db,tmp_path):
    from fastapi.testclient import TestClient
    from opspilot.web.app import create_app
    from test_ar02_assistant import ORIGIN,PASSWORDS,capture
    prepare_s3_fixture(demo_db,'DELIVERED_PENDING',order_id='ar02-order',contract_version=2)
    modes=iter(('knowledge','business','concept'))
    app=create_app(db_path=demo_db,checkpoint_db_path=tmp_path/'worker-cp.sqlite3',start_worker=True,
                   credentials=PASSWORDS,expected_origin=ORIGIN,assistant_model_factory=lambda:FixtureModel(mode=next(modes)))
    with TestClient(app) as client:
        token=client.post('/api/auth/login',headers={'Origin':ORIGIN},json={'actor_id':'support-a','password':PASSWORDS['support-a']}).json()['csrf_token']
        headers={'Origin':ORIGIN,'X-CSRF-Token':token}
        session=client.post('/api/sessions',headers=headers).json()['session_id']
        questions=[('assistant/messages',{'body':'请查协议。粘贴材料 ORION-42；202 是否代表完成？'}),
                   ('assistant/order',{'order_id':'ar02-order','initial_message':'现在核查本订单当前状态'}),
                   ('assistant/messages',{'body':'根据刚才的结果整理一份说明草稿'})]
        task=None;accepted=[]
        for index,(route,body) in enumerate(questions):
            if task and route.endswith('messages'):body['task_id']=task
            response=client.post(f'/api/sessions/{session}/{route}',headers={**headers,'Idempotency-Key':f'journey-{index}'},json=body)
            assert response.status_code==202,response.text
            value=response.json();accepted.append(value);task=value.get('task_id') or task
            deadline=time.monotonic()+12
            while True:
                run=client.get('/api/runs/'+value['run_id']).json()
                if run['status'] in ('SUCCEEDED','FAILED','BLOCKED'):break
                assert time.monotonic()<deadline,run
                time.sleep(.05)
            assert run['status']=='SUCCEEDED',run
            capture(f'journey-{index}-run.json',client.get('/api/runs/'+value['run_id']))
        messages=client.get(f'/api/sessions/{session}/messages').json()['items']
        assert len([m for m in messages if m['role']=='USER'])==3
        answers=[m for m in messages if m['role']=='ASSISTANT']
        assert len(answers)==3 and all(m['answer_source_message_id'] for m in answers)
        assert {m['answer_source_message_id'] for m in answers}=={x['message_id'] for x in accepted}
        capture('journey-messages.json',client.get(f'/api/sessions/{session}/messages'))
        with connect(demo_db) as c:before=c.execute("SELECT COUNT(*) FROM assistant_calls WHERE kind='MODEL'").fetchone()[0]
        for _ in range(2):
            assert client.get(f'/api/sessions/{session}/messages').json()['items']==messages
            assert client.get('/api/runs/'+accepted[1]['run_id']+'/assistant-sources').json()['current']
            client.get(f'/api/sessions/{session}/events/history?after=0')
        with connect(demo_db) as c:assert c.execute("SELECT COUNT(*) FROM assistant_calls WHERE kind='MODEL'").fetchone()[0]==before

def test_old_core_sources_revoke_and_ordinary_chat_cannot_borrow_observation(demo_db,tmp_path):
    from opspilot.domain.assistant import sources_current
    from opspilot.domain.s3 import current_s3_evidence
    prepare_s3_fixture(demo_db,'PROCESSING',order_id='ar02-order',contract_version=2)
    created=setup_run(demo_db,'查询本订单','normal',bind=True)
    result,_=execute(demo_db,created,FixtureModel(mode='business'),tmp_path/'cp.sqlite3')
    assert result['status']=='SUCCEEDED'
    with connect(demo_db) as c:
        call=c.execute('SELECT * FROM assistant_calls WHERE evidence_id IS NOT NULL LIMIT 1').fetchone()
        assert sources_current(c,created['run_id'])[0]
        # Removing the trusted core marker produces an ordinary Chat Run. Such
        # a Run still cannot claim business observations even with copied IDs.
        c.execute('DELETE FROM assistant_calls WHERE run_id=?',(created['run_id'],))
        c.execute('DELETE FROM assistant_runs WHERE run_id=?',(created['run_id'],))
        facts,excluded=current_s3_evidence(c,created['task_id'],[call['evidence_id']],run_id=created['run_id'],observation_ids={call['evidence_id']:call['observation_id']})
        assert not facts and excluded

def test_revocation_between_tool_and_model_stops_and_source_api_denies(demo_db,tmp_path):
    from test_ar02_assistant import client_for
    prepare_s3_fixture(demo_db,'PROCESSING',order_id='ar02-order',contract_version=2)
    created=setup_run(demo_db,'查询本订单','revoke',bind=True)
    owner='revoke-worker';register_worker_owner(demo_db,owner,os.getpid())
    claim_task_run(demo_db,trusted_identity(demo_db,'support-a'),created['run_id'])
    model=FixtureModel(mode='business')
    def revoke(event,**values):
        if event=='tool_observation':
            with connect(demo_db) as c:
                changed=c.execute("UPDATE principals SET status='DISABLED',principal_version=principal_version+1 WHERE principal_id=(SELECT principal_id FROM task_bindings WHERE task_id=?)",(created['task_id'],))
                assert changed.rowcount==1
    result=asyncio.run(run_assistant(demo_db,tmp_path/'cp.sqlite3',owner,created['run_id'],model=model,trace=revoke))
    assert result['status']=='NOT_COMPLETED' and len(model.seen)==1
    client,_=client_for(demo_db)
    assert client.get('/api/runs/'+created['run_id']+'/assistant-sources').status_code==403
    with connect(demo_db) as c:assert c.execute('SELECT COUNT(*) FROM chat_run_answers').fetchone()[0]==0

def test_two_connections_preserve_run_reservation_limit(demo_db):
    from concurrent.futures import ThreadPoolExecutor
    from opspilot.domain.assistant import reserve
    from opspilot.domain.task_control import TaskControlError
    created=setup_run(demo_db,'普通问题','concurrency')
    owner='concurrency-worker';register_worker_owner(demo_db,owner,os.getpid())
    claim_task_run(demo_db,trusted_identity(demo_db,'support-a'),created['run_id'])
    def reservation(index):
        try:
            reserve(demo_db,created['run_id'],'MODEL',str(index),{'free_reservation_fixture':index},owner)
            return True
        except TaskControlError:return False
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(reservation,range(12)))
    assert sum(results)==8
    with connect(demo_db) as c:assert c.execute("SELECT COUNT(*) FROM assistant_calls WHERE status='RESERVED'").fetchone()[0]==8

@pytest.mark.parametrize('state,expected',[('DELIVERED_PENDING','QUEUED'),('DELIVERY_FAILED','NOT_RECEIVED')])
def test_same_wording_different_real_observation_is_delivered(demo_db,tmp_path,state,expected):
    prepare_s3_fixture(demo_db,state,order_id='ar02-order',contract_version=2)
    created=setup_run(demo_db,'请核查接收方是否完成','paired',bind=True)
    result,events=execute(demo_db,created,FixtureModel(mode='business'),tmp_path/'cp.sqlite3')
    assert result['status']=='SUCCEEDED'
    receiver=next(e for e in events if e['event']=='tool_observation' and e['name']=='get_receiver_processing')
    assert receiver['result']['facts']['status']==expected
    answer=next(e for e in events if e['event']=='answer_committed')['answer']
    assert expected in answer
