from __future__ import annotations
import json,os,sqlite3,sys,time,subprocess,secrets,hashlib
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path.cwd();sys.path.insert(0,str(ROOT))
from opspilot.config import load_local_environment
from opspilot.domain.database import reset_fixture
from opspilot.smokes.m1_03 import _kill,_server_environment,_start_vite,_start,_wait_http
load_local_environment()
runtime=Path(__file__).resolve().parent
out=ROOT/'docs/evidence/vnext/m3-closeout-01/runs/journey-01'
db=runtime/'domain.sqlite3';cp=runtime/'checkpoints.sqlite3'
def record(kind,**kwargs):
 row={'at':datetime.now(timezone.utc).isoformat(),'kind':kind,**kwargs}
 with (out/'process-events.jsonl').open('a',encoding='utf-8') as f:f.write(json.dumps(row,ensure_ascii=False)+'\n')
 print(json.dumps(row,ensure_ascii=False),flush=True)
if not db.exists():
 reset_fixture(db,'S1_POS')
 with sqlite3.connect(db) as d:
  d.row_factory=sqlite3.Row
  snapshot={t:[dict(r) for r in d.execute('SELECT * FROM '+t)] for t in ('integrations','principals','auth_policies','principal_scope_grants','route_scope_policies','orders','trusted_operators')}
 (out/'fixture-initial-state.json').write_text(json.dumps({'fixture':'reset_fixture(S1_POS)','fresh_database':True,'source':'opspilot/domain/database.py at checkout','state':snapshot},ensure_ascii=False,indent=2),encoding='utf-8')
 record('FIXTURE_INITIALIZED_ONCE',database=str(db.relative_to(ROOT)),scenario='S1_POS',task_count=0)
passwords={a:secrets.token_urlsafe(22) for a in ('support-a','approver-a','support-b','approver-b')}
(runtime/'test-passwords.json').write_text(json.dumps(passwords),encoding='utf-8')
env=_server_environment(db,cp,'http://127.0.0.1:5174',passwords)
api=None;vite=None
commands=runtime/'commands.jsonl';commands.write_text('',encoding='utf-8')
def start_api():
 global api
 command=[sys.executable,'-X','utf8','-u',str(runtime/'observed_server.py'),'--host','127.0.0.1','--port','8001']
 api=_start(command,ROOT,env,out/'api.log')
 _wait_http(api,'http://127.0.0.1:8001/api/health',out/'api.log')
 record('API_STARTED',launcher_pid=api.pid,git_sha=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),database=str(db.relative_to(ROOT)),checkpoint=str(cp.relative_to(ROOT)))
try:
 start_api();vite=_start_vite(5174,'http://127.0.0.1:8001',env,out/'vite.log')
 record('VITE_STARTED',launcher_pid=vite.pid,url='http://127.0.0.1:5174/')
 offset=0
 while True:
  with commands.open('r',encoding='utf-8') as f:
   f.seek(offset);line=f.readline()
   if line and line.endswith('\n'):offset=f.tell()
   else:line=''
  if not line:time.sleep(.05);continue
  cmd=json.loads(line)
  if cmd['command']=='restart':
   record('TERMINATING_OWNED_API',launcher_pid=api.pid,reason=cmd.get('reason'))
   _kill(api);record('API_PROCESS_TREE_TERMINATED',launcher_pid=api.pid,returncode=api.returncode)
   start_api()
  elif cmd['command']=='exit':break
finally:
 _kill(api);_kill(vite);record('OWNED_SERVICES_STOPPED')
