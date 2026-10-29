"""Formal Event correction on a copy of the free Session journey.
The retained Investigator uses a local model substitute; SDK construction is patched.
"""
import asyncio,json,os,shutil,sys
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[5];sys.path[:0]=[str(ROOT),str(ROOT/'tests')]
from langchain_core.messages import AIMessage,messages_to_dict
from opspilot.domain.database import connect
from opspilot.domain.s3_history import prepare_transport_history_fixture
from opspilot.domain.task_control import trusted_identity,admit_task_message,register_worker_owner
from opspilot.web.worker import _dispatch_run
from opspilot.config import MODEL_API_KEY,MODEL_NAME

class Model:
    def __init__(self):self.inputs=[]
    def bind_tools(self,*args,**kwargs):return self
    async def ainvoke(self,messages):
        index=len(self.inputs);self.inputs.append(messages_to_dict(messages))
        tools=[('get_callback_transport_history',{'event_id':'event-e1','reason':'核查正式更正后的目标事件历史'}),('get_receiver_processing',{'reason':'对照当前接收方事件，不能借用其他事件的成功'})]
        if index<2:
            name,args=tools[index]
            return AIMessage(content='',tool_calls=[{'name':name,'args':args,'id':f'free-correction-{index}'}])
        return AIMessage(content=json.dumps({'action':'answer','result_state':'PARTIAL','target_event_id':'event-e1','processing_claim':'UNKNOWN','answer':'event-e1 有503历史；当前Receiver是另一事件，不能证明E1已处理。E1当前处理未知。'},ensure_ascii=False))

source=next((ROOT/'.tmp/ar02-full-02').glob('test_real_api_worker_sessio*/domain.sqlite3'))
db=ROOT/'.tmp/ar02-correction-04.sqlite3'
if db.exists():raise RuntimeError('Refuse to overwrite an existing experiment')
shutil.copy2(source,db)
with connect(db) as c:
    row=c.execute('SELECT session_id,task_id FROM task_runs WHERE task_id IS NOT NULL ORDER BY created_at DESC LIMIT 1').fetchone()
    session,task=row['session_id'],row['task_id']
    original_revision=c.execute('SELECT control_revision FROM task_controls WHERE task_id=?',(task,)).fetchone()[0]
# Independent fixture preparation, not an Agent repair/retry action.
prepare_transport_history_fixture(db,order_id='ar02-order',attempts=[{'event_id':'event-e1','http_status':503},{'event_id':'event-e2','http_status':202}],receiver_status='PROCESSED')
accepted=admit_task_message(db,trusted_identity(db,'support-a'),session_id=session,task_id=task,input_kind='CORRECT_TASK_INPUT',body='正式确认更正：调查目标是 event-e1，不是 event-e2。请重新核查。',idempotency_key='formal-correction-once')
worker='ar02-free-correction';register_worker_owner(db,worker,os.getpid())
with connect(db) as c:run=dict(c.execute('SELECT * FROM task_runs WHERE run_id=?',(accepted['run_id'],)).fetchone())
model=Model()
with patch.dict(os.environ,{MODEL_API_KEY:'FREE_FIXTURE_NEVER_SENT',MODEL_NAME:'ar02-free-legacy-model'}),patch('opspilot.investigator.ChatOpenAI',lambda **kwargs:model):
    asyncio.run(_dispatch_run(db,ROOT/'.tmp/ar02-correction-04-cp.sqlite3',worker,'executor-a',run))
with connect(db) as c:
    final=dict(c.execute('SELECT * FROM task_runs WHERE run_id=?',(accepted['run_id'],)).fetchone())
    control=dict(c.execute('SELECT * FROM task_controls WHERE task_id=?',(task,)).fetchone())
    observations=[dict(r) for r in c.execute('SELECT o.*,a.run_id FROM d2_tool_observations o JOIN d2_attempts a ON a.attempt_id=o.attempt_id WHERE a.run_id=?',(accepted['run_id'],))]
    answers=[dict(r) for r in c.execute('SELECT * FROM s3_run_answers WHERE run_id=?',(accepted['run_id'],))]
    counts={t:c.execute('SELECT COUNT(*) FROM '+t).fetchone()[0] for t in ('d3_action_intents','d3_action_ledgers','s3_handoff_receipts')}
payload={'evidence_level':'DETERMINISTIC_LEGACY_MODEL_REAL_MCP_DOMAIN','preparation':'Trusted fixture changed E1/E2 before Agent execution; no Agent repair or handoff','accepted':accepted,'run':final,'control':control,'observations':observations,'answers':answers,'actual_model_inputs':model.inputs,'protected_business_counts':counts,'real_provider_requests':0}
out=Path(__file__).with_name('correction-04-trace.json');out.write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8')
assert accepted['expected_control_revision']==original_revision+1
assert control['control_revision']==accepted['expected_control_revision']+1
assert final['expected_control_revision']==control['control_revision']
assert control['pending_critical_message_seq'] is None and final['applied_critical_message_seq']==accepted['sequence']
assert final['status']=='SUCCEEDED',final
assert observations and all(o['run_id']==accepted['run_id'] for o in observations)
assert 'event-e1' in str(model.inputs)
assert answers
delivery=json.loads(answers[0]['body_json'])
assert delivery['source_message_id']==accepted['message_id'] and delivery['control_revision']==control['control_revision']
assert delivery['result_state']=='PARTIAL' and 'E1当前处理未知' in delivery['answer_text']
assert all(ref['origin_run_id']==accepted['run_id'] for ref in delivery['source_refs'])
assert all(v==0 for v in counts.values())
print('FORMAL_CORRECTION_PASS',accepted['run_id'],'revision',control['control_revision'],'observations',len(observations),'answers',len(answers),'Provider=0')
