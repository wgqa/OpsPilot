"""Professional assistant execution metadata. Session/Run/Task remain authoritative."""
from __future__ import annotations

import json
import uuid
from pathlib import Path
from opspilot.domain.database import connect
from opspilot.domain.d2 import canonical_json, digest_json, utc_now
from opspilot.domain.task_control import TaskControlError, trusted_identity, _verify_identity

SCHEMA = """
CREATE TABLE IF NOT EXISTS assistant_runs (
 run_id TEXT PRIMARY KEY REFERENCES task_runs(run_id) ON DELETE CASCADE,
 core TEXT NOT NULL CHECK(core='ASSISTANT_V1'),
 delivery_attempt_id TEXT,
 created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS assistant_calls (
 call_id TEXT PRIMARY KEY,
 run_id TEXT NOT NULL REFERENCES assistant_runs(run_id) ON DELETE CASCADE,
 kind TEXT NOT NULL CHECK(kind IN ('MODEL','MCP')),
 logical_key TEXT NOT NULL,
 request_json TEXT NOT NULL,
 request_digest TEXT NOT NULL,
 status TEXT NOT NULL CHECK(status IN ('RESERVED','OK','FAILED','UNKNOWN')),
 result_json TEXT,
 usage_json TEXT,
 observation_id TEXT,
 evidence_id TEXT,
 created_at TEXT NOT NULL,
 completed_at TEXT,
 UNIQUE(run_id,kind,logical_key)
);
"""

def register(connection, run_id):
    connection.execute("INSERT INTO assistant_runs(run_id,core,created_at) VALUES (?,'ASSISTANT_V1',?)",(run_id,utc_now()))

def selected(connection, run_id):
    return connection.execute('SELECT 1 FROM assistant_runs WHERE run_id=?',(run_id,)).fetchone() is not None

def state(connection, run_id, *, active=True, worker_id=None):
    from opspilot.domain.chat import _check_worker_fence
    from opspilot.domain.task_control import assert_task_control_in_transaction
    row=connection.execute('SELECT r.*,s.owner_id FROM task_runs r JOIN sessions s ON s.session_id=r.session_id AND s.tenant_id=r.tenant_id JOIN assistant_runs a ON a.run_id=r.run_id WHERE r.run_id=?',(run_id,)).fetchone()
    if row is None: raise TaskControlError('ASSISTANT_RUN_NOT_FOUND')
    if worker_id: _check_worker_fence(connection,worker_id)
    if active and row['status']!='RUNNING': raise TaskControlError('TASK_RUN_NOT_ACTIVE')
    identity=trusted_identity(Path(connection.execute('PRAGMA database_list').fetchone()[2]),row['owner_id'])
    _verify_identity(connection,identity)
    if row['task_id'] and active:
        assert_task_control_in_transaction(connection,row['tenant_id'],row['task_id'],run_id=run_id,allow_completed=True)
    return dict(row),identity

def read_run(path,run_id,*,active=True,worker_id=None):
    with connect(path) as c: return state(c,run_id,active=active,worker_id=worker_id)

def reserve(path,run_id,kind,logical_key,request,worker_id):
    """Count durable dispatches, including unknown results, before external I/O."""
    from opspilot.domain.execution_budget import auxiliary_budget_in_transaction
    with connect(path) as c:
        c.execute('BEGIN IMMEDIATE')
        run,_=state(c,run_id,worker_id=worker_id)
        old=c.execute('SELECT * FROM assistant_calls WHERE run_id=? AND kind=? AND logical_key=?',(run_id,kind,logical_key)).fetchone()
        if old:
            if old['request_digest']!=digest_json(request): raise TaskControlError('ASSISTANT_REPLAY_CONTEXT_CHANGED')
            if old['status']!='OK': raise TaskControlError('ASSISTANT_EXTERNAL_RESULT_UNKNOWN')
            return dict(old),False
        used=c.execute('SELECT COUNT(*) FROM assistant_calls WHERE run_id=? AND kind=?',(run_id,kind)).fetchone()[0]
        if used >= (8 if kind=='MODEL' else 6): raise TaskControlError('ASSISTANT_RUN_'+kind+'_LIMIT')
        if kind=='MODEL' and run['task_id']:
            budget=auxiliary_budget_in_transaction(c,run['task_id'])
            if budget['reason_code']: raise TaskControlError(budget['reason_code'])
        call='assistant-call-'+str(uuid.uuid4())
        c.execute('INSERT INTO assistant_calls(call_id,run_id,kind,logical_key,request_json,request_digest,status,created_at) VALUES (?,?,?,?,?,?,?,?)',(call,run_id,kind,logical_key,canonical_json(request),digest_json(request),'RESERVED',utc_now()))
        return dict(c.execute('SELECT * FROM assistant_calls WHERE call_id=?',(call,)).fetchone()),True

def finish(path,call_id,status,result=None,usage=None,observation=None):
    with connect(path) as c:
        c.execute("UPDATE assistant_calls SET status=?,result_json=?,usage_json=?,observation_id=?,evidence_id=?,completed_at=? WHERE call_id=? AND status='RESERVED'",(status,canonical_json(result),canonical_json(usage), (observation or {}).get('observation_id'),(observation or {}).get('evidence_id'),utc_now(),call_id))

def sources_current(connection, run_id):
    """Revalidate actual persisted sources; never trust a saved Prompt/answer."""
    from opspilot.domain.assistant_knowledge import sources_current as knowledge_current
    from opspilot.domain.s3 import current_s3_evidence, get_s3_binding
    try:
        run,identity=state(connection,run_id,active=False)
        if run['task_id']:
            get_s3_binding(connection,run['task_id'])
            control=connection.execute('SELECT control_revision,terminal_state FROM task_controls WHERE task_id=?',(run['task_id'],)).fetchone()
            if control['terminal_state']!='ACTIVE' or control['control_revision']!=run['expected_control_revision']:
                return False,'TASK_CONTROL_CHANGED'
        calls=connection.execute("SELECT * FROM assistant_calls WHERE run_id=? AND kind='MCP' AND status='OK'",(run_id,)).fetchall()
        for row in calls:
            value=json.loads(row['result_json'])
            if row['evidence_id']:
                facts,excluded=current_s3_evidence(connection,run['task_id'],[row['evidence_id']],run_id=run_id,observation_ids={row['evidence_id']:row['observation_id']})
                if excluded or not facts: return False,'BUSINESS_SOURCE_INVALIDATED'
            elif isinstance(value,dict) and 'documents' in value:
                ok,reason=knowledge_current(connection,identity,run['session_id'],value)
                if not ok:return False,reason
        return True,None
    except Exception:
        return False,'ASSISTANT_SOURCE_SCOPE_INVALID'

def history_sources(connection,run):
    """Bounded prior references are leads, never this Run's current observations."""
    output=[]
    previous=connection.execute('SELECT r.run_id,r.task_id FROM task_runs r JOIN assistant_runs a ON a.run_id=r.run_id JOIN messages m ON m.message_id=r.source_message_id WHERE r.session_id=? AND r.tenant_id=? AND m.sequence < ? AND (r.task_id IS NULL OR r.task_id IS ?) ORDER BY m.sequence DESC LIMIT 6',(run['session_id'],run['tenant_id'],run['consumed_message_seq'],run['task_id'])).fetchall()
    for old in previous:
        valid,reason=sources_current(connection,old['run_id'])
        refs=[]
        if valid:
            refs=[{'call_id':r['call_id'],'observation_id':r['observation_id'],'evidence_id':r['evidence_id'],'result':json.loads(r['result_json'])} for r in connection.execute("SELECT * FROM assistant_calls WHERE run_id=? AND kind='MCP' AND status='OK' ORDER BY created_at LIMIT 6",(old['run_id'],))]
        output.append({'run_id':old['run_id'],'authority':'HISTORICAL_LEAD_NOT_CURRENT_OBSERVATION','current_source_valid':valid,'exclusion_reason':reason,'sources':refs})
    return output
