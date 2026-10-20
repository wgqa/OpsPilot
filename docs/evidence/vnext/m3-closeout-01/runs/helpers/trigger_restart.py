import json,sqlite3,time
from pathlib import Path
from datetime import datetime,timezone
r=Path(__file__).resolve().parent
out=Path.cwd()/'docs/evidence/vnext/m3-closeout-01/runs/journey-01'
task='task-c84ae518-8a09-436c-a058-a059951c1d91'
with sqlite3.connect(r/'domain.sqlite3') as d:
 known={x[0] for x in d.execute("SELECT run_id FROM task_runs WHERE task_id=? AND kind='INVESTIGATE'",(task,))}
print('ARMED_FOR_NEW_INVESTIGATE_ON_EXISTING_TASK_B',flush=True)
end=time.monotonic()+240
while time.monotonic()<end:
 with sqlite3.connect(r/'domain.sqlite3') as d:
  d.row_factory=sqlite3.Row
  runs=[dict(x) for x in d.execute("SELECT * FROM task_runs WHERE task_id=? AND kind='INVESTIGATE' AND status='RUNNING'",(task,)) if x['run_id'] not in known]
  for run in runs:
   attempts=[dict(x) for x in d.execute('SELECT * FROM d2_attempts WHERE task_id=?',(task,))]
   observations=[dict(x) for x in d.execute('SELECT o.* FROM d2_tool_observations o JOIN d2_attempts a ON a.attempt_id=o.attempt_id WHERE a.run_id=?',(run['run_id'],))]
   binding=dict(d.execute('SELECT * FROM task_bindings WHERE task_id=?',(task,)).fetchone())
   thread=binding['thread_id']+'::'+run['run_id']
   with sqlite3.connect(r/'checkpoints.sqlite3') as cp:
    cp.row_factory=sqlite3.Row
    checkpoints=[dict(x) for x in cp.execute('SELECT thread_id,checkpoint_ns,checkpoint_id,parent_checkpoint_id FROM checkpoints WHERE thread_id=?',(thread,))]
   if observations and checkpoints:
    snap={'at':datetime.now(timezone.utc).isoformat(),'run':run,'binding':binding,'checkpoint_thread':thread,'checkpoints':checkpoints,'attempts_all_task_b_before_crash':attempts,'observations_this_run_before_crash':observations,'action_ledger_count':d.execute('SELECT COUNT(*) FROM d3_action_ledgers').fetchone()[0],'scope_grants':[dict(x) for x in d.execute('SELECT * FROM principal_scope_grants')]}
    (out/'crash-trigger.json').write_text(json.dumps(snap,ensure_ascii=False,indent=2),encoding='utf-8')
    with (r/'commands.jsonl').open('a',encoding='utf-8') as f:f.write(json.dumps({'command':'restart','reason':'controlled same-Run crash after current Run MCP observation and checkpoint'})+'\n')
    print(json.dumps({'crash_run':run['run_id'],'thread':thread,'checkpoint_count':len(checkpoints),'this_run_observations':len(observations),'task_model_reservations':sum(a['kind']=='MODEL' for a in attempts),'task_mcp_reservations':sum(a['kind']=='MCP' for a in attempts)}),flush=True)
    raise SystemExit(0)
 time.sleep(.01)
print('MONITOR_TIMEOUT_NO_CRASH',flush=True)
raise SystemExit(1)
