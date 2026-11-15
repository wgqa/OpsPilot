from __future__ import annotations
import hashlib, json, os, sqlite3, subprocess, sys, time, uuid
from datetime import datetime, timezone
from pathlib import Path
import requests

ROOT = Path.cwd()
RUNTIME = 'user-demo-r2-e09-live01'
API = 'http://127.0.0.1:8000'
WEB_ORIGIN = 'http://127.0.0.1:5173'
FIXED_TURN_SHA = '744abd7ae909b4e4bac02b2b9fa389a98a0ba8a1450d75f735199d5856da99cc'
POOL_LIMIT_MICRO = 220_000
MAX_RUNS = 11
MAX_DISPATCHES = 33
OUT = ROOT / '.runtime' / RUNTIME / 'evidence'
PREFLIGHT_PATH = OUT / 'live_preflight.json'
JOURNAL = OUT / 'live_execution_journal.jsonl'
LOCK = OUT / 'first_live_submission.lock'
TRACE_AFTER_10 = OUT / 'E09_LIVE_PREBIND_TRACE.json'
SUMMARY_AUDIT = OUT / 'E09_LIVE_PREBIND_SUMMARY_AUDIT.json'
MODEL_INPUT_AUDIT = OUT / 'E09_LIVE_PREBIND_MODEL_INPUT_AUDIT.json'
TURN_SCRIPT = ROOT / 'docs/evidence/r2-ar06-eval-01/e09-d-readiness-20261115-v3/E09_TURN_SCRIPT.json'

class StopJourney(RuntimeError):
    pass

def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds').replace('+00:00','Z')

def write_json(path: Path, value):
    if path.exists():
        raise StopJourney('OUTPUT_ALREADY_EXISTS:' + path.name)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

def load_turn_script():
    raw = TURN_SCRIPT.read_bytes()
    actual = hashlib.sha256(raw).hexdigest()
    if actual != FIXED_TURN_SHA:
        raise StopJourney('FROZEN_TURN_SCRIPT_SHA_MISMATCH')
    data = json.loads(raw.decode('utf-8'))
    turns = data.get('turns')
    if not isinstance(turns, list) or len(turns) != 10:
        raise StopJourney('FROZEN_TURN_COUNT_MISMATCH')
    for index, turn in enumerate(turns, 1):
        body = turn.get('body')
        if turn.get('turn') != index or not isinstance(body, str):
            raise StopJourney('FROZEN_TURN_SEQUENCE_OR_BODY_INVALID')
        if hashlib.sha256(body.encode('utf-8')).hexdigest() != turn.get('sha256'):
            raise StopJourney('FROZEN_TURN_BODY_SHA_MISMATCH:' + str(index))
    binding = data.get('trusted_task_binding')
    if not isinstance(binding, dict) or binding.get('after_turn') != 10 or binding.get('order_id') != 'async-order':
        raise StopJourney('FROZEN_BINDING_SPEC_INVALID')
    return data

def db_readonly():
    path = ROOT / '.runtime' / RUNTIME / 'domain.sqlite3'
    return sqlite3.connect('file:' + str(path) + '?mode=ro', uri=True)

def db_counts():
    c = db_readonly(); c.row_factory = sqlite3.Row
    names = ['sessions','messages','task_bindings','task_runs','assistant_runtime_authority',
             'assistant_runtime_pools','assistant_runtime_default_grant','assistant_runtime_spends',
             'personal_memories','context_summaries','context_compression_attempts']
    result = {n: int(c.execute('SELECT COUNT(*) FROM ' + n).fetchone()[0]) for n in names}
    c.close(); return result

def source_audit():
    c = db_readonly(); c.row_factory = sqlite3.Row
    summaries = [dict(r) for r in c.execute(
        "SELECT summary_id,tenant_id,session_id,task_id,summary_version,state,strategy,summary_json,summary_digest,covered_from_seq,covered_to_seq,depends_on_summary_id,source_attempt_id,model_id,created_at,invalidation_reason FROM context_summaries WHERE session_id=? ORDER BY summary_version,created_at,summary_id",
        (session_id,))]
    dependencies = []
    checks = []
    for summary in summaries:
        try:
            actual = hashlib.sha256(str(summary['summary_json']).encode('utf-8')).hexdigest()
            checks.append({'kind':'SUMMARY_BODY','ref':summary['summary_id'],'expected':summary['summary_digest'],'actual':actual,'valid':actual==summary['summary_digest']})
        except Exception:
            checks.append({'kind':'SUMMARY_BODY','ref':summary['summary_id'],'valid':False})
        deps = [dict(r) for r in c.execute(
            'SELECT summary_id,dependency_kind,dependency_ref,dependency_version,dependency_digest,source_order FROM context_summary_dependencies WHERE summary_id=? ORDER BY source_order,dependency_kind,dependency_ref',
            (summary['summary_id'],))]
        for dep in deps:
            kind, ref = dep['dependency_kind'], dep['dependency_ref']
            observed = None
            source_status = None
            scope_valid = False
            if kind in ('MESSAGE','ASSISTANT_MESSAGE'):
                row = c.execute('SELECT body_digest,session_id FROM messages WHERE message_id=? AND tenant_id=?',(ref,tenant_id)).fetchone()
                observed = str(row['body_digest']) if row else None
                source_status = 'PRESENT' if row else 'MISSING'
                scope_valid = bool(row and str(row['session_id']) == session_id)
            elif kind == 'SUMMARY':
                row = c.execute('SELECT summary_digest,state,session_id FROM context_summaries WHERE summary_id=? AND tenant_id=?',(ref,tenant_id)).fetchone()
                observed = str(row['summary_digest']) if row else None
                source_status = str(row['state']) if row else 'MISSING'
                scope_valid = bool(row and str(row['session_id']) == session_id and str(row['state']) in ('CURRENT','SUPERSEDED'))
            elif kind == 'MODEL_ATTEMPT':
                row = c.execute('SELECT prompt_digest,status,session_id FROM chat_attempts WHERE attempt_id=? AND tenant_id=?',(ref,tenant_id)).fetchone()
                observed = str(row['prompt_digest']) if row else None
                source_status = str(row['status']) if row else 'MISSING'
                scope_valid = bool(row and str(row['session_id']) == session_id and str(row['status']) == 'SUCCEEDED')
            dep['observed_current_digest'] = observed
            dep['source_status'] = source_status
            dep['scope_valid'] = scope_valid
            dep['digest_valid'] = observed is not None and observed == dep['dependency_digest'] and scope_valid
            checks.append({'kind':kind,'ref':ref,'expected':dep['dependency_digest'],'actual':observed,'source_status':source_status,'scope_valid':scope_valid,'valid':dep['digest_valid']})
            dependencies.append(dep)
    attempts = [dict(r) for r in c.execute(
        'SELECT attempt_id,run_id,attempt_no,status,provider_response_id,input_tokens,output_tokens,total_tokens,summary_id,error_class,created_at,completed_at FROM context_compression_attempts WHERE session_id=? ORDER BY created_at,attempt_no',
        (session_id,))]
    c.close()
    return {'runtime_name':RUNTIME,'session_id':session_id,'tenant_id':tenant_id,'summaries':summaries,
            'dependencies':dependencies,'compression_attempts':attempts,'digest_checks':checks,
            'all_known_dependencies_valid':all(x['valid'] for x in checks),
            'current_summary_ids':[s['summary_id'] for s in summaries if s['state']=='CURRENT']}

def assert_api_response(response, expected_status, label):
    if response.status_code != expected_status:
        try:
            payload = response.json()
            code = payload.get('code') or payload.get('detail') or 'API_ERROR'
        except Exception:
            code = 'NON_JSON_API_ERROR'
        raise StopJourney(f'{label}_HTTP_{response.status_code}:{str(code)[:120]}')
    return response.json()

def wait_for_run(http, run_id, number):
    started = time.monotonic()
    while time.monotonic() - started < 900:
        response = http.get(f'{API}/api/runs/{run_id}', timeout=20)
        if response.status_code != 200:
            raise StopJourney(f'RUN_STATUS_UNREADABLE:{number}:{response.status_code}')
        data = response.json(); status = data.get('status')
        if status not in ('QUEUED','RUNNING'):
            return data
        time.sleep(2)
    raise StopJourney(f'RUN_WAIT_TIMEOUT:{number}')

def capture_context(http, run_id, number):
    response = http.get(f'{API}/api/runs/{run_id}/context', timeout=20)
    if response.status_code != 200:
        raise StopJourney(f'RUN_CONTEXT_UNREADABLE:{number}:{response.status_code}')
    data = response.json()
    bad_compression = [x for x in data.get('compression_attempts',[]) if x.get('status') != 'SUCCEEDED']
    if bad_compression:
        raise StopJourney(f'COMPRESSION_NOT_SUCCEEDED:{number}')
    return data

def load_current_spend(admin, values):
    state = admin.preflight(ROOT / '.runtime' / RUNTIME / 'domain.sqlite3', values)
    if int(state.get('unknown_requests', -1)) != 0:
        raise StopJourney('RUNTIME_UNKNOWN_REQUEST_PRESENT')
    if state.get('status') != 'ACTIVE':
        raise StopJourney('RUNTIME_POOL_NOT_ACTIVE')
    return state

# Preflight without creating or submitting another Run.
if not OUT.is_dir() or not PREFLIGHT_PATH.is_file():
    raise StopJourney('RUNTIME_PREFLIGHT_ARTIFACT_MISSING')
if any(p.exists() for p in (JOURNAL, LOCK, TRACE_AFTER_10, SUMMARY_AUDIT, MODEL_INPUT_AUDIT)):
    raise StopJourney('LIVE_EXECUTION_ALREADY_STARTED_OR_OUTPUT_EXISTS')
pref = json.loads(PREFLIGHT_PATH.read_text(encoding='utf-8'))
session_id = pref.get('session_id'); tenant_id = pref.get('identity',{}).get('tenant_id')
if pref.get('runtime_name') != RUNTIME or pref.get('identity') != {'actor_id':'support-a','tenant_id':'tenant-a','role':'SUPPORT'} or not session_id:
    raise StopJourney('SUPPORT_SESSION_PREFLIGHT_MISMATCH')
data = load_turn_script()
turns = data['turns']; binding = data['trusted_task_binding']
sys.path.insert(0, str(ROOT / 'scripts' / 'user-demo'))
import runtime_admin
values = runtime_admin.read_env(); settings = runtime_admin._runtime_settings(values)
if settings.get('model_id') != 'deepseek-flash' or settings.get('endpoint') != 'https://api.deepseek.com':
    raise StopJourney('PROVIDER_MODEL_OR_ENDPOINT_MISMATCH')
if int(settings['input_rate_micro_per_million']) != 300_000 or int(settings['output_rate_micro_per_million']) != 1_200_000:
    raise StopJourney('PROVIDER_PRICE_DOES_NOT_MATCH_CURRENT_OFFICIAL_PEAK_RATE')
reserve_micro = runtime_admin._max_request_reserve(settings)
if reserve_micro * MAX_DISPATCHES > POOL_LIMIT_MICRO:
    raise StopJourney('AUTHORIZED_POOL_BELOW_FULL_JOURNEY_MAX_RESERVE')
initial_spend = load_current_spend(runtime_admin, values)
if initial_spend.get('provider_sends') != 0 or initial_spend.get('unknown_requests') != 0:
    raise StopJourney('RUNTIME_NOT_EMPTY_BEFORE_FIRST_PROVIDER_REQUEST')
initial_counts = db_counts()
if initial_counts['task_runs'] != 0 or initial_counts['messages'] != 0 or initial_counts['task_bindings'] != 0 or initial_counts['assistant_runtime_spends'] != 0:
    raise StopJourney('RUNTIME_SESSION_OR_SPEND_NOT_EMPTY')

http = requests.Session(); http.trust_env = False
login = http.post(API + '/api/auth/login', json={'actor_id':'support-a','password':values['OPSPILOT_WEB_SUPPORT_PASSWORD']}, headers={'Origin':WEB_ORIGIN}, timeout=20)
identity = assert_api_response(login,200,'SUPPORT_LOGIN')
if identity.get('actor_id') != 'support-a' or identity.get('tenant_id') != 'tenant-a' or identity.get('role') != 'SUPPORT':
    raise StopJourney('SUPPORT_IDENTITY_MISMATCH')
csrf = identity['csrf_token']; write_headers={'Origin':WEB_ORIGIN,'X-CSRF-Token':csrf,'Content-Type':'application/json'}
me=http.get(API+'/api/auth/me',timeout=20); me_data=assert_api_response(me,200,'AUTH_ME')
if me_data.get('actor_id')!='support-a' or me_data.get('tenant_id')!='tenant-a': raise StopJourney('AUTH_ME_IDENTITY_MISMATCH')
resources=http.get(API+'/api/s3/order-resources',timeout=20); resources_data=assert_api_response(resources,200,'S3_RESOURCES')
if not any(x.get('order_id')=='async-order' for x in resources_data.get('items',[])): raise StopJourney('S3_ASYNC_ORDER_NOT_AUTHORIZED')
pre_runs=http.get(f'{API}/api/sessions/{session_id}/runs',timeout=20); pre_runs_data=assert_api_response(pre_runs,200,'SESSION_RUNS')
if pre_runs_data.get('items'): raise StopJourney('SESSION_ALREADY_HAS_RUNS')
preflight_guard={'recorded_at':utc_now(),'runtime_name':RUNTIME,'session_id':session_id,'base_sha':__import__('subprocess').check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
                 'turn_script_sha256':hashlib.sha256(TURN_SCRIPT.read_bytes()).hexdigest(),'turn_count':len(turns),'planned_run_count':MAX_RUNS,
                 'planned_max_dispatches':MAX_DISPATCHES,'per_dispatch_max_reserve_usd':f'{reserve_micro/1_000_000:.6f}',
                 'full_journey_max_reserve_usd':f'{reserve_micro*MAX_DISPATCHES/1_000_000:.6f}','authorized_pool_usd':'0.220000',
                 'model_id':settings['model_id'],'endpoint':settings['endpoint'],'model_config_version':settings['model_config_version'],
                 'price_version':settings['price_version'],'input_rate_micro_per_million':settings['input_rate_micro_per_million'],
                 'output_rate_micro_per_million':settings['output_rate_micro_per_million'],'support_login':'PASS','s3_async_order':'PASS',
                 'session_run_count_before_live':0,'provider_sends_before_live':0,'unknown_before_live':0,'no_secret_values_recorded':True}
write_json(OUT/'live_first_request_guard.json',preflight_guard)
fd=os.open(LOCK,os.O_CREAT|os.O_EXCL|os.O_WRONLY)
os.write(fd,(utc_now()+'\n').encode()); os.fsync(fd); os.close(fd)
with JOURNAL.open('x',encoding='utf-8') as _:
    pass

def journal(event, **fields):
    record={'at':utc_now(),'event':event,**fields}
    with JOURNAL.open('a',encoding='utf-8') as f:
        f.write(json.dumps(record,ensure_ascii=False)+'\n'); f.flush(); os.fsync(f.fileno())
    return record

def submit_one(index, body, route, payload, input_sha):
    spend=load_current_spend(runtime_admin, values)
    if int(spend.get('remaining_usd_micro',0)) < reserve_micro:
        raise StopJourney(f'BUDGET_BELOW_ONE_MAX_REQUEST_RESERVE:{index}')
    op_id=str(uuid.uuid4())
    journal('PREPARED',run_number=index,route=route,idempotency_key=op_id,input_sha256=input_sha,provider_sends_before=spend.get('provider_sends'),remaining_usd_micro=spend.get('remaining_usd_micro'))
    try:
        response=http.post(f'{API}{route}',json=payload,headers={**write_headers,'Idempotency-Key':op_id},timeout=30)
    except requests.RequestException as exc:
        journal('SUBMISSION_RESPONSE_UNCERTAIN',run_number=index,idempotency_key=op_id,error_class=type(exc).__name__)
        raise StopJourney(f'SUBMISSION_RESPONSE_UNCERTAIN:{index}:{type(exc).__name__}') from None
    if response.status_code != 202:
        try:
            detail=response.json().get('code') or response.json().get('detail') or 'API_ERROR'
        except Exception: detail='NON_JSON_API_ERROR'
        journal('HTTP_SUBMISSION_REJECTED',run_number=index,idempotency_key=op_id,http_status=response.status_code,error_code=str(detail)[:120])
        raise StopJourney(f'HTTP_SUBMISSION_REJECTED:{index}:{response.status_code}:{str(detail)[:120]}')
    accepted=response.json(); run_id=accepted.get('run_id'); message_id=accepted.get('message_id')
    if not isinstance(run_id,str) or not run_id:
        journal('ACCEPTED_WITHOUT_RUN_ID',run_number=index,idempotency_key=op_id,response_fields=list(accepted.keys()))
        raise StopJourney(f'ACCEPTED_WITHOUT_RUN_ID:{index}')
    journal('ACCEPTED',run_number=index,route=route,idempotency_key=op_id,message_id=message_id,run_id=run_id,
            task_id=accepted.get('task_id'),accepted_status=accepted.get('status'),answer_status=accepted.get('answer_status'))
    run=wait_for_run(http,run_id,index)
    journal('RUN_TERMINAL',run_number=index,run_id=run_id,status=run.get('status'),task_id=run.get('task_id'),blocked_reason=run.get('blocked_reason'),ended_at=run.get('ended_at'))
    if run.get('status') != 'SUCCEEDED':
        raise StopJourney(f'RUN_NOT_SUCCEEDED:{index}:{run.get("status")}')
    context=capture_context(http,run_id,index)
    context_file=OUT/f'context_run_{index:02d}.json'
    write_json(context_file,context)
    chat_attempts=context.get('attempts',[]); compressions=context.get('compression_attempts',[])
    spend_after=load_current_spend(runtime_admin, values)
    journal('RUN_AUDITED',run_number=index,run_id=run_id,status='SUCCEEDED',chat_attempts=len(chat_attempts),
            compression_attempts=len(compressions),compression_statuses=[x.get('status') for x in compressions],
            summary_refs=context.get('summary_refs',[]),provider_sends_total=spend_after.get('provider_sends'),
            unknown_total=spend_after.get('unknown_requests'),remaining_usd_micro=spend_after.get('remaining_usd_micro'),
            chat_usage=[x.get('token_usage') for x in chat_attempts],
            compression_usage=[x.get('token_usage') for x in compressions],
            provider_response_ids=[x.get('provider_response_id') for x in [*chat_attempts,*compressions] if x.get('provider_response_id')])
    return {'run_id':run_id,'message_id':message_id,'task_id':run.get('task_id'),'context':context,'run':run}

runs=[]
try:
    journal('LIVE_JOURNEY_STARTED',runtime_name=RUNTIME,session_id=session_id,run_count=MAX_RUNS,provider_sends_before=0,
            turn_script_sha256=FIXED_TURN_SHA,price_version=settings['price_version'],rate_input=settings['input_rate_micro_per_million'],rate_output=settings['output_rate_micro_per_million'])
    for turn in turns:
        number=int(turn['turn'])
        result=submit_one(number,turn['body'],f'/api/sessions/{session_id}/assistant/messages',{'body':turn['body'],'task_id':None},turn['sha256'])
        runs.append(result)
        print(json.dumps({'event':'taskless_run_succeeded','run_number':number,'run_id':result['run_id'],'provider_sends':runtime_admin.preflight(ROOT/'.runtime'/RUNTIME/'domain.sqlite3',values).get('provider_sends')},ensure_ascii=False),flush=True)
    if len(runs)!=10: raise StopJourney('TASKLESS_RUN_COUNT_NOT_TEN')
    session_runs=http.get(f'{API}/api/sessions/{session_id}/runs',timeout=20)
    session_runs_data=assert_api_response(session_runs,200,'POST_TURN10_SESSION_RUNS')
    if len(session_runs_data.get('items',[]))!=10 or any(x.get('status')!='SUCCEEDED' for x in session_runs_data.get('items',[])):
        raise StopJourney('TASKLESS_SESSION_RUNS_NOT_TEN_SUCCEEDED')
    audit=source_audit(); write_json(SUMMARY_AUDIT,audit)
    if not audit['all_known_dependencies_valid']:
        journal('STOP_INVALID_SUMMARY_SOURCE',invalid_checks=[x for x in audit['digest_checks'] if not x.get('valid')])
        raise StopJourney('SUMMARY_SOURCE_OR_DIGEST_INVALID')
    if any(x.get('status')!='SUCCEEDED' for x in audit['compression_attempts']):
        journal('STOP_COMPRESSION_FAILURE',attempts=audit['compression_attempts'])
        raise StopJourney('COMPRESSION_ATTEMPT_NOT_SUCCEEDED')
    if TRACE_AFTER_10.exists(): raise StopJourney('PREBIND_TRACE_ALREADY_EXISTS')
    command=[sys.executable,str(ROOT/'scripts/user-demo/export_live_evidence.py'),'--runtime-name',RUNTIME,'--session-id',session_id,'--actor-id','support-a','--output',str(TRACE_AFTER_10)]
    exported=subprocess.run(command,cwd=ROOT,capture_output=True,text=True,timeout=120)
    if exported.returncode!=0:
        journal('STOP_PREBIND_EXPORT_FAILURE',exit_code=exported.returncode,stderr=exported.stderr[-300:])
        raise StopJourney('PREBIND_EVIDENCE_EXPORT_FAILED')
    live_trace=json.loads(TRACE_AFTER_10.read_text(encoding='utf-8'))
    run10_id=runs[-1]['run_id']
    model_calls=[x for x in live_trace.get('assistant_calls_actual_model_input_output',[]) if x.get('kind')=='MODEL' and x.get('run_id')==run10_id]
    req_text='\n'.join(json.dumps(x.get('request_json'),ensure_ascii=False) for x in model_calls)
    marker='HISTORICAL SESSION SUMMARY' in req_text
    current_ids=audit.get('current_summary_ids',[])
    run10ctx=runs[-1]['context']
    manifest_summary_refs=run10ctx.get('summary_refs',[])
    input_audit={'runtime_name':RUNTIME,'session_id':session_id,'turn10_run_id':run10_id,'model_call_count':len(model_calls),
                 'actual_request_contains_historical_summary_marker':marker,'current_summary_ids':current_ids,
                 'context_manifest_summary_refs':manifest_summary_refs,'summary_id_occurs_in_actual_request':{sid:(sid in req_text) for sid in current_ids},
                 'actual_request_sha256':[hashlib.sha256(json.dumps(x.get('request_json'),ensure_ascii=False,sort_keys=True).encode()).hexdigest() for x in model_calls],
                 'taskless_summary_visible_before_binding':marker and bool(current_ids),'provider_dispatches_in_turn10':len(model_calls)}
    write_json(MODEL_INPUT_AUDIT,input_audit)
    journal('TASKLESS_STAGE_COMPLETE',session_run_count=10,current_summary_ids=current_ids,all_summary_dependencies_valid=audit['all_known_dependencies_valid'],
            turn10_model_calls=len(model_calls),summary_marker_in_turn10_actual_input=marker,context_manifest_summary_refs=manifest_summary_refs,
            provider_sends_total=runtime_admin.preflight(ROOT/'.runtime'/RUNTIME/'domain.sqlite3',values).get('provider_sends'))
    print(json.dumps({'event':'taskless_stage_complete','runs':10,'current_summaries':len(current_ids),'turn10_summary_input_marker':marker,'all_summary_dependencies_valid':audit['all_known_dependencies_valid']},ensure_ascii=False),flush=True)
    print('Stage A evidence captured. Stage B binding query must be reviewed and submitted separately; this process will not issue a binding Run.',flush=True)
except StopJourney as exc:
    journal('STOPPED',reason=str(exc))
    print(json.dumps({'event':'stopped','reason':str(exc)},ensure_ascii=False),flush=True)
    raise SystemExit(2)
except Exception as exc:
    journal('STOPPED_UNEXPECTED',error_class=type(exc).__name__,reason=str(exc)[:180])
    print(json.dumps({'event':'stopped_unexpected','error_class':type(exc).__name__,'reason':str(exc)[:180]},ensure_ascii=False),flush=True)
    raise SystemExit(2)
