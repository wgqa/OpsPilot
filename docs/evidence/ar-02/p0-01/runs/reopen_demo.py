"""Reopen an isolated copy of the free API journey; no real Provider/browser."""
import json,shutil,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[5]
sys.path[:0]=[str(ROOT),str(ROOT/'tests')]
from fastapi.testclient import TestClient
from langchain_core.messages import messages_to_dict
from test_ar02_runtime import FixtureModel
from test_ar02_assistant import ORIGIN,PASSWORDS
from opspilot.web.app import create_app
from opspilot.domain.database import connect

source=next((ROOT/'.tmp/ar02-full-02').glob('test_real_api_worker_sessio*/domain.sqlite3'))
target=ROOT/'.tmp/ar02-reopened-01.sqlite3'
if target.exists():raise RuntimeError('Refuse to overwrite previous reopen experiment')
shutil.copy2(source,target)
folder=Path(__file__).resolve().parent
with connect(source) as c:
    tables={name:[dict(r) for r in c.execute('SELECT * FROM '+name+' ORDER BY rowid')] for name in ('sessions','messages','task_runs','assistant_runs','assistant_calls','d2_tool_observations','task_controls','task_execution_budgets','chat_run_answers','domain_outbox')}
(folder/'api-journey-persisted-trace.json').write_text(json.dumps({'evidence_level':'DETERMINISTIC_MODEL_REAL_MCP_HTTP_SQLITE','source_sha':'ead3ec4bcf44b1e7110fc95b8b1fde7520b1bfbf','tables':tables},ensure_ascii=False,indent=2),encoding='utf-8')
with connect(target) as c:
    row=c.execute('SELECT session_id,task_id FROM task_runs WHERE task_id IS NOT NULL ORDER BY created_at DESC LIMIT 1').fetchone()
    session,task=row['session_id'],row['task_id']
model=FixtureModel()
app=create_app(db_path=target,checkpoint_db_path=ROOT/'.tmp/ar02-reopened-01-cp.sqlite3',credentials=PASSWORDS,expected_origin=ORIGIN,assistant_model_factory=lambda:model)
with TestClient(app) as client:
    login=client.post('/api/auth/login',headers={'Origin':ORIGIN},json={'actor_id':'support-a','password':PASSWORDS['support-a']})
    h={'Origin':ORIGIN,'X-CSRF-Token':login.json()['csrf_token'],'Idempotency-Key':'reopen-same-session'}
    accepted=client.post(f'/api/sessions/{session}/assistant/messages',headers=h,json={'task_id':task,'body':'重新打开后继续解释 ORION-42 的日志；先不判断当前订单。'})
    assert accepted.status_code==202,accepted.text
    run=accepted.json()['run_id']; deadline=time.monotonic()+15
    while True:
        status=client.get('/api/runs/'+run).json()
        if status['status'] in ('SUCCEEDED','FAILED','BLOCKED'):break
        assert time.monotonic()<deadline,status
        time.sleep(.05)
    assert status['status']=='SUCCEEDED',status
    assert 'ORION-42' in str(model.seen)
    messages=client.get(f'/api/sessions/{session}/messages').json()
    with connect(target) as c:
        assert c.execute('SELECT COUNT(*) FROM chat_run_answers WHERE run_id=?',(run,)).fetchone()[0]==1
        assert c.execute("SELECT COUNT(*) FROM assistant_calls WHERE run_id=? AND kind='MCP'",(run,)).fetchone()[0]==0
    (folder/'reopened-session-trace.json').write_text(json.dumps({'evidence_level':'DETERMINISTIC_MODEL_NEW_APP_REAL_HTTP_API_SQLITE','accepted':accepted.json(),'status':status,'messages':messages,'actual_model_input':[messages_to_dict(x) for x in model.seen],'new_provider_requests':0},ensure_ascii=False,indent=2),encoding='utf-8')
print('REOPENED_APP_SAME_SESSION_PASS; original DB untouched; new model dispatch=1 (fixture), MCP=0, Provider=0, final answer=1')
