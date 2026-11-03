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

MAX_HISTORY_RUNS = 6
MAX_HISTORY_SOURCE_RESULTS = 12
MAX_HISTORY_KNOWLEDGE_DOCS = 2
MAX_HISTORY_EXCERPT_CHARS = 320

_HISTORICAL_FACT_FIELDS = (
    "order_id", "order_version", "event_id", "transport_request_id", "request_id",
    "delivery_id", "delivery_version", "receiver_id", "http_status",
    "receiver_http_status", "status", "retry_state", "attempt_count",
    "max_attempts", "failure_code", "accepted_at", "processed_at",
    "processing_sla_seconds", "sla_deadline", "observed_at",
)


def history_excerpt(value: object, limit: int = MAX_HISTORY_EXCERPT_CHARS) -> str | None:
    if not isinstance(value, str) or not value:
        return None
    if len(value) <= limit:
        return value
    marker = "…[historical excerpt truncated]"
    if limit <= len(marker):
        return value[:limit]
    return value[:limit - len(marker)] + marker


def _historical_result_summary(tool_name: str, result: dict[str, object]) -> dict[str, object]:
    """Keep small, typed historical leads after their persisted sources were revalidated."""
    if tool_name == "read_scoped_protocol_excerpt" and isinstance(result.get("document_ref"), dict):
        document = result["document_ref"]
        excerpts = result.get("excerpts")
        excerpts = excerpts if isinstance(excerpts, list) else []
        source_refs = result.get("source_refs")
        source_refs = source_refs if isinstance(source_refs, list) else []
        return {
            "authority": "HISTORICAL_PROTOCOL_SOURCE_TEXT_ONLY",
            "currentness": "NOT_CURRENT_BUSINESS_EVIDENCE",
            "session_id": result.get("session_id"),
            "project_id": result.get("project_id"),
            "grant_version": result.get("grant_version"),
            "scope_digest": result.get("scope_digest"),
            "document_ref": {
                key: document.get(key) for key in (
                    "document_id", "version", "source", "digest", "valid_from", "expires_at",
                )
            },
            "query": history_excerpt(result.get("query"), 100),
            "start_line": result.get("start_line"),
            "start_column": result.get("start_column"),
            "next_cursor": result.get("next_cursor"),
            "excerpts": [{
                "section": history_excerpt(row.get("section"), 80),
                "line_start": row.get("line_start"),
                "line_end": row.get("line_end"),
                "column_start": row.get("column_start"),
                "column_end": row.get("column_end"),
                "text": history_excerpt(row.get("text"), 300),
                "excerpt_digest": row.get("excerpt_digest"),
                "truncated": bool(row.get("truncated")),
            } for row in excerpts[:2] if isinstance(row, dict)],
            "source_refs": [{
                key: ref.get(key) for key in (
                    "document_id", "version", "source", "digest", "line_start", "line_end",
                    "column_start", "column_end", "excerpt_digest",
                )
            } for ref in source_refs[:2] if isinstance(ref, dict)],
            "deployment_version_verified": False,
        }

    if isinstance(result.get("protocol_documents"), list):
        documents = result.get("protocol_documents")
        protocols = result.get("protocols")
        documents = documents if isinstance(documents, list) else []
        protocols = protocols if isinstance(protocols, list) else []
        projected = []
        for document in documents[:3]:
            if not isinstance(document, dict):
                continue
            projected.append({
                key: document.get(key) for key in (
                    "document_id", "title", "version", "contract_versions", "digest",
                    "source", "valid_from", "expires_at",
                )
            })
        families = []
        for protocol in protocols[:3]:
            if isinstance(protocol, dict):
                families.append({
                    "family": history_excerpt(protocol.get("family"), 120),
                    "document_ids": [str(value) for value in protocol.get("document_ids", [])[:4]],
                    "versions": [str(value) for value in protocol.get("versions", [])[:4]],
                })
        return {
            "authority": "HISTORICAL_PROTOCOL_METHOD_ONLY_NOT_CURRENT_BUSINESS_EVIDENCE",
            "session_id": result.get("session_id"),
            "project_id": result.get("project_id"),
            "grant_version": result.get("grant_version"),
            "scope_digest": result.get("scope_digest"),
            "topic": history_excerpt(result.get("topic"), 100),
            "document_count": result.get("document_count"),
            "protocol_documents": projected,
            "protocols": families,
            "source_refs": projected,
        }

    if isinstance(result.get("comparison_digest"), str):
        def _protocol_ref(value):
            if not isinstance(value, dict):
                return None
            return {key: value.get(key) for key in (
                "document_id", "version", "digest", "source", "valid_from", "expires_at",
            )}

        differences = result.get("differences")
        differences = differences if isinstance(differences, list) else []
        projected_differences = []
        for item in differences[:3]:
            if not isinstance(item, dict):
                continue
            projected_differences.append({
                "difference_id": item.get("difference_id"),
                "category": item.get("category"),
                "title": history_excerpt(item.get("title"), 120),
                "description": history_excerpt(item.get("description"), 220),
                "base_location": history_excerpt(item.get("base_location"), 100),
                "target_location": history_excerpt(item.get("target_location"), 100),
                "evidence_id": item.get("evidence_id"),
            })
        unconfirmed = result.get("unconfirmed_aspects")
        unconfirmed = unconfirmed if isinstance(unconfirmed, list) else []
        return {
            "authority": "HISTORICAL_PROTOCOL_METHOD_ONLY_NOT_CURRENT_BUSINESS_EVIDENCE",
            "session_id": result.get("session_id"),
            "project_id": result.get("project_id"),
            "grant_version": result.get("grant_version"),
            "scope_digest": result.get("scope_digest"),
            "base_ref": _protocol_ref(result.get("base_ref")),
            "target_ref": _protocol_ref(result.get("target_ref")),
            "summary": history_excerpt(result.get("summary")),
            "diff_count": result.get("diff_count"),
            "differences": projected_differences,
            "unconfirmed_aspects": [history_excerpt(item, 180) for item in unconfirmed[:3]],
            "comparison_digest": result.get("comparison_digest"),
            "deployment_version_verified": False,
        }

    if isinstance(result.get("documents"), list):
        documents = result.get("documents")
        refs = result.get("source_refs")
        documents = documents if isinstance(documents, list) else []
        refs = refs if isinstance(refs, list) else []
        projected = []
        for document, source_ref in zip(documents, refs):
            if not isinstance(document, dict) or not isinstance(source_ref, dict):
                continue
            projected.append({
                "document_id": document.get("document_id"),
                "version": document.get("version"),
                "digest": document.get("digest"),
                "source": document.get("source"),
                "valid_from": document.get("valid_from"),
                "expires_at": document.get("expires_at"),
                "excerpt": history_excerpt(document.get("summary") or document.get("content")),
            })
            if len(projected) >= MAX_HISTORY_KNOWLEDGE_DOCS:
                break
        refs_out = [{
            key: ref.get(key) for key in (
                "document_id", "version", "digest", "source", "valid_from", "expires_at",
            )
        } for ref in refs[:MAX_HISTORY_KNOWLEDGE_DOCS] if isinstance(ref, dict)]
        return {
            "authority": "HISTORICAL_METHOD_ONLY_NOT_CURRENT_BUSINESS_EVIDENCE",
            "documents": projected,
            "source_refs": refs_out,
            "configured_contract_version": result.get("configured_contract_version"),
            "retrieved_contract_version": result.get("retrieved_contract_version"),
            "trusted_binding_contract_version": result.get("trusted_binding_contract_version"),
            "latest_available_contract_version": result.get("latest_available_contract_version"),
        }

    facts = result.get("facts")
    if isinstance(facts, dict):
        projected_facts = {
            key: facts.get(key) for key in _HISTORICAL_FACT_FIELDS if key in facts
        }
        # Transport history may contain multiple related attempts. Keep a few
        # identity/status fields while making the historical scope explicit.
        for list_key in ("attempts", "transport_attempts", "events"):
            records = facts.get(list_key)
            if isinstance(records, list):
                projected_facts[list_key] = [
                    {key: row.get(key) for key in _HISTORICAL_FACT_FIELDS if key in row}
                    for row in records[:3] if isinstance(row, dict)
                ]
        return {
            "authority": "HISTORICAL_RUN_ONLY",
            "fact_type": result.get("fact_type"),
            "resource_id": result.get("resource_id"),
            "data_source": result.get("data_source"),
            "trust_class": result.get("trust_class"),
            "observed_at": result.get("observed_at"),
            "observed_versions": result.get("observed_versions"),
            "original_result_ref": result.get("original_result_ref"),
            "facts": projected_facts,
        }

    skill = result.get("skill")
    if isinstance(skill, dict):
        return {
            "authority": "HISTORICAL_METHOD_HINT_ONLY",
            "skill": {
                "name": skill.get("name"), "version": skill.get("version"),
                "digest": skill.get("digest"), "contract_versions": skill.get("contract_versions"),
                "description": history_excerpt(skill.get("description"), 240),
            },
            "selection_reason": history_excerpt(result.get("selection_reason"), 160),
        }

    # Unknown historical tool formats get a source reference, not arbitrary
    # JSON copied into a future model prompt.
    return {"authority": "HISTORICAL_TOOL_RESULT_REFERENCE_ONLY", "tool_name": tool_name}

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

def run_limits_for_experiment(experiment_id):
    """Keep ordinary Runs at 8/6; only explicitly scoped experiments vary."""
    from opspilot.domain.assistant_experiment import (
        AR03_MATERIAL_LIVE_01_EXPERIMENT_ID,
        AR03_MATERIAL_LIVE_01_RESUME_01_EXPERIMENT_ID,
        AR03_MATERIAL_LIVE_01_RESUME_02_EXPERIMENT_ID,
        AR03_MATERIAL_REMAINDER_01_EXPERIMENT_ID,
    )
    if experiment_id in {
        AR03_MATERIAL_LIVE_01_EXPERIMENT_ID,
        AR03_MATERIAL_LIVE_01_RESUME_01_EXPERIMENT_ID,
        AR03_MATERIAL_LIVE_01_RESUME_02_EXPERIMENT_ID,
    }:
        return 16, 10
    if experiment_id == AR03_MATERIAL_REMAINDER_01_EXPERIMENT_ID:
        return 16, None
    return 8, 6


def reserve(path,run_id,kind,logical_key,request,worker_id,*,experiment_id=None):
    """Count durable dispatches, including unknown results, before external I/O."""
    from opspilot.domain.execution_budget import auxiliary_budget_in_transaction
    with connect(path) as c:
        c.execute('BEGIN IMMEDIATE')
        run,_=state(c,run_id,worker_id=worker_id)
        old=c.execute('SELECT * FROM assistant_calls WHERE run_id=? AND kind=? AND logical_key=?',(run_id,kind,logical_key)).fetchone()
        if old:
            if old['request_digest']!=digest_json(request): raise TaskControlError('ASSISTANT_REPLAY_CONTEXT_CHANGED')
            if old['status']!='OK': raise TaskControlError('ASSISTANT_EXTERNAL_RESULT_UNKNOWN')
            if kind == 'MCP':
                try:
                    cached_result = json.loads(old['result_json']) if old['result_json'] is not None else None
                except (TypeError, json.JSONDecodeError):
                    cached_result = None
                if not isinstance(cached_result, dict):
                    raise TaskControlError('ASSISTANT_CACHED_RESULT_INVALID')
            return dict(old),False
        used=c.execute('SELECT COUNT(*) FROM assistant_calls WHERE run_id=? AND kind=?',(run_id,kind)).fetchone()[0]
        model_limit,mcp_limit=run_limits_for_experiment(experiment_id)
        limit = model_limit if kind=='MODEL' else mcp_limit
        if limit is not None and used >= limit: raise TaskControlError('ASSISTANT_RUN_'+kind+'_LIMIT')
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
    from opspilot.domain.scoped_protocol_comparison import (
        scoped_comparison_is_current,
        scoped_discovery_is_current,
        scoped_protocol_excerpt_is_current,
    )
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
            try:
                value = json.loads(row['result_json']) if row['result_json'] is not None else None
            except (TypeError, json.JSONDecodeError):
                return False,'ASSISTANT_SOURCE_RESULT_INVALID'
            if not isinstance(value, dict):
                return False,'ASSISTANT_SOURCE_RESULT_INVALID'
            try:
                request = json.loads(row['request_json']) if row['request_json'] is not None else None
            except (TypeError, json.JSONDecodeError):
                return False, 'ASSISTANT_SOURCE_REQUEST_INVALID'
            tool_name = request.get('name') if isinstance(request, dict) else None
            if row['evidence_id']:
                facts,excluded=current_s3_evidence(connection,run['task_id'],[row['evidence_id']],run_id=run_id,observation_ids={row['evidence_id']:row['observation_id']})
                if excluded or not facts: return False,'BUSINESS_SOURCE_INVALIDATED'
            elif 'protocol_documents' in value:
                if value.get('success') is not True:
                    return False, 'PROTOCOL_DISCOVERY_RESULT_INVALID'
                ok, reason = scoped_discovery_is_current(
                    connection, identity, run['session_id'], value,
                )
                if not ok:
                    return False, reason or 'PROTOCOL_DISCOVERY_SOURCE_INVALID'
            elif 'comparison_digest' in value:
                if value.get('success') is not True:
                    return False, 'PROTOCOL_COMPARISON_RESULT_INVALID'
                ok, reason = scoped_comparison_is_current(
                    connection, identity, run['session_id'], value,
                )
                if not ok:
                    return False, reason or 'PROTOCOL_COMPARISON_SOURCE_INVALID'
            elif tool_name == 'read_scoped_protocol_excerpt':
                if value.get('success') is not True:
                    return False, 'PROTOCOL_EXCERPT_RESULT_INVALID'
                ok, reason = scoped_protocol_excerpt_is_current(
                    connection, identity, run['session_id'], value,
                )
                if not ok:
                    return False, reason or 'PROTOCOL_EXCERPT_SOURCE_INVALID'
            elif tool_name == 'load_protocol_upgrade_skill':
                from opspilot.skill_assets import (
                    PROTOCOL_UPGRADE_PROBLEM_TYPE, skill_asset_is_current,
                )
                skill = value.get('skill')
                if (
                    value.get('success') is not True
                    or value.get('problem_type') != PROTOCOL_UPGRADE_PROBLEM_TYPE
                    or not isinstance(skill, dict)
                    or not skill_asset_is_current(PROTOCOL_UPGRADE_PROBLEM_TYPE, skill)
                ):
                    return False, 'PROTOCOL_UPGRADE_SKILL_SOURCE_INVALID'
            elif isinstance(value,dict) and 'documents' in value:
                ok,reason=knowledge_current(connection,identity,run['session_id'],value)
                if not ok:return False,reason
        return True,None
    except Exception:
        return False,'ASSISTANT_SOURCE_SCOPE_INVALID'

def history_sources(connection,run):
    """Return bounded prior source projections; never current observations for this Run."""
    output=[]
    remaining=MAX_HISTORY_SOURCE_RESULTS
    previous=connection.execute('SELECT r.run_id,r.task_id FROM task_runs r JOIN assistant_runs a ON a.run_id=r.run_id JOIN messages m ON m.message_id=r.source_message_id WHERE r.session_id=? AND r.tenant_id=? AND m.sequence < ? AND (r.task_id IS NULL OR r.task_id IS ?) ORDER BY m.sequence DESC LIMIT ?',(run['session_id'],run['tenant_id'],run['consumed_message_seq'],run['task_id'],MAX_HISTORY_RUNS)).fetchall()
    for old in previous:
        valid,reason=sources_current(connection,old['run_id'])
        refs=[]
        omitted=0
        if valid:
            rows=connection.execute("SELECT * FROM assistant_calls WHERE run_id=? AND kind='MCP' AND status='OK' ORDER BY created_at DESC",(old['run_id'],)).fetchall()
            selected=rows[:remaining]
            omitted=max(0,len(rows)-len(selected))
            for row in reversed(selected):
                try:
                    result=json.loads(row['result_json']) if row['result_json'] is not None else None
                    request=json.loads(row['request_json']) if row['request_json'] is not None else None
                except (TypeError, json.JSONDecodeError):
                    continue
                if not isinstance(result,dict):
                    continue
                tool_name=str(request.get('name','')) if isinstance(request,dict) else ''
                refs.append({
                    'call_id':row['call_id'],'request_digest':row['request_digest'],
                    'observation_id':row['observation_id'],'evidence_id':row['evidence_id'],
                    'created_at':row['created_at'],'completed_at':row['completed_at'],
                    'observed_at':result.get('observed_at'),
                    'result_digest':digest_json(result),
                    'source_authority':'HISTORICAL_RUN_ONLY',
                    'summary':_historical_result_summary(tool_name,result),
                })
            remaining=max(0,remaining-len(refs))
        output.append({'run_id':old['run_id'],'task_id':old['task_id'],'authority':'HISTORICAL_LEAD_NOT_CURRENT_OBSERVATION','current_source_valid':valid,'exclusion_reason':reason,'sources':refs,'omitted_source_count':omitted})
    return output
