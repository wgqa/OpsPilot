"""Professional assistant execution metadata. Session/Run/Task remain authoritative."""
from __future__ import annotations

import hashlib
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


MAX_SESSION_PROFESSIONAL_OUTCOMES = 4


def _assistant_source_message(connection, run):
    message_id = run.get('source_message_id')
    if not message_id:
        raise TaskControlError('ASSISTANT_SOURCE_MESSAGE_REQUIRED')
    row = connection.execute(
        """SELECT message_id, tenant_id, session_id, task_id, sequence, role, input_kind,
                  body, body_digest, created_at
           FROM messages WHERE message_id = ?""",
        (message_id,),
    ).fetchone()
    if (
        row is None or row['tenant_id'] != run['tenant_id']
        or row['session_id'] != run['session_id'] or row['task_id'] is not None
        or row['role'] != 'USER' or row['input_kind'] != 'CHAT_READONLY'
        or int(row['sequence']) != int(run['consumed_message_seq'])
    ):
        raise TaskControlError('ASSISTANT_SOURCE_MESSAGE_SCOPE_INVALID')
    actual_digest = hashlib.sha256(str(row['body']).encode('utf-8')).hexdigest()
    if actual_digest != str(row['body_digest']):
        raise TaskControlError('ASSISTANT_SOURCE_MESSAGE_DIGEST_INVALID')
    return row, actual_digest


def propose_controlled_auth_investigation(path, run_id, rationale):
    """Persist an advisory-only proposal as an ordinary MCP call result.

    The existing Assistant call ledger stores the proposal. It creates no Task,
    permission, approval, or business state; the UI must use the existing
    explicit-confirmation Task API with the trusted source message ID.
    """
    if not isinstance(rationale, str) or not rationale.strip() or len(rationale.strip()) > 240:
        raise TaskControlError('ASSISTANT_INVESTIGATION_PROPOSAL_INVALID')
    with connect(path) as connection:
        run, identity = state(connection, run_id, active=False)
        if run['kind'] != 'CHAT_READONLY' or run['task_id'] is not None:
            raise TaskControlError('ASSISTANT_INVESTIGATION_PROPOSAL_REQUIRES_UNBOUND_CHAT')
        operator = _verify_identity(connection, identity)
        if operator['role'] != 'SUPPORT':
            raise TaskControlError('ASSISTANT_INVESTIGATION_PROPOSAL_SUPPORT_ONLY')
        message, source_digest = _assistant_source_message(connection, run)
        return {
            'success': True,
            'proposal_type': 'CONTROLLED_AUTH_INVESTIGATION',
            'authority': 'MODEL_SUGGESTION_ONLY_UNTRUSTED',
            'rationale': rationale.strip(),
            'source_message_id': str(message['message_id']),
            'source_message_digest': source_digest,
            'source_created_at': str(message['created_at']),
            'task_created': False,
            'authorization_created': False,
            'requires_explicit_user_confirmation': True,
        }


def _session_professional_outcomes(connection, run, identity):
    _verify_identity(connection, identity)
    if run['kind'] != 'CHAT_READONLY' or run['task_id'] is not None or identity.role != 'SUPPORT':
        raise TaskControlError('ASSISTANT_PROFESSIONAL_OUTCOME_READ_SCOPE_DENIED')
    session = connection.execute(
        """SELECT session_id FROM sessions
           WHERE session_id = ? AND tenant_id = ? AND owner_id = ?""",
        (run['session_id'], identity.tenant_id, identity.actor_id),
    ).fetchone()
    if session is None:
        raise TaskControlError('SESSION_SCOPE_DENIED')

    # The window count and bounded page share one authorization predicate and
    # one SQLite statement snapshot, so hidden outcomes cannot leak across scope.
    rows = connection.execute(
        """SELECT b.task_id, b.status AS task_status, b.created_at, c.control_revision,
                  COUNT(*) OVER () AS eligible_count,
                  (SELECT COUNT(*) FROM d3_plans p
                   WHERE p.tenant_id = b.tenant_id AND p.task_id = b.task_id) AS s1_plan_count,
                  (SELECT COUNT(*) FROM s2_diagnosis_receipts d
                   WHERE d.tenant_id = b.tenant_id AND d.task_id = b.task_id) AS s2_receipt_count
           FROM session_task_links l
           JOIN task_bindings b ON b.task_id = l.task_id AND b.tenant_id = l.tenant_id
           JOIN task_controls c ON c.task_id = b.task_id AND c.tenant_id = b.tenant_id
           WHERE l.session_id = ? AND l.tenant_id = ? AND b.actor_id = ?
             AND c.terminal_state = 'ACTIVE'
             AND (EXISTS (SELECT 1 FROM d3_plans p WHERE p.tenant_id = b.tenant_id AND p.task_id = b.task_id)
                  OR EXISTS (SELECT 1 FROM s2_diagnosis_receipts d WHERE d.tenant_id = b.tenant_id AND d.task_id = b.task_id))
           ORDER BY l.linked_at DESC, b.task_id DESC LIMIT ?""",
        (run['session_id'], identity.tenant_id, identity.actor_id, MAX_SESSION_PROFESSIONAL_OUTCOMES),
    ).fetchall()
    eligible_count = int(rows[0]['eligible_count']) if rows else 0
    database_path = str(connection.execute('PRAGMA database_list').fetchone()[2])
    items: list[dict[str, object]] = []
    for row in rows[:MAX_SESSION_PROFESSIONAL_OUTCOMES]:
        task_id = str(row['task_id'])
        latest_runs = connection.execute(
            """SELECT run_id, kind, status, created_at, ended_at
               FROM task_runs WHERE tenant_id = ? AND task_id = ? AND kind != 'CHAT_READONLY'
               ORDER BY created_at DESC, run_id DESC LIMIT 3""",
            (identity.tenant_id, task_id),
        ).fetchall()
        run_refs = [{key: item[key] for key in ('run_id', 'kind', 'status', 'created_at', 'ended_at')}
                    for item in latest_runs]

        if int(row['s2_receipt_count']) > 0:
            from opspilot.domain.s2_handoff import get_s2_handoff

            outcome = get_s2_handoff(database_path, identity, task_id)
            if outcome.get('business_outcome') == 'NO_S2_DIAGNOSIS':
                continue
            diagnosis = outcome.get('diagnosis_receipt')
            receipt = outcome.get('handoff_receipt')
            draft = outcome.get('draft')
            diagnosis_view = None
            if isinstance(diagnosis, dict):
                diagnosis_view = {key: diagnosis.get(key) for key in (
                    'receipt_id', 'task_id', 'outcome', 'run_id', 'request_id', 'decision_id',
                    'gate_policy_version', 'predicate', 'evidence_ids', 'evidence_digests',
                    'observed_versions', 'created_at',
                )}
            draft_view = None
            if isinstance(draft, dict):
                content = draft.get('content') if isinstance(draft.get('content'), dict) else {}
                draft_view = {
                    **{key: draft.get(key) for key in ('draft_id', 'task_id', 'receipt_id', 'version', 'content_digest', 'created_at', 'status')},
                    'content': {key: content.get(key) for key in (
                        'service_id', 'integration_id', 'principal_id', 'route', 'required_scopes',
                        'granted_scopes', 'missing_scopes', 'reason', 'evidence_ids', 'knowledge_refs',
                        'state', 'authorization_changed', 'handoff_receipt_created',
                    ) if key in content},
                    'current': draft.get('current'),
                }
            receipt_view = None
            if isinstance(receipt, dict):
                receipt_view = {key: receipt.get(key) for key in (
                    'receipt_id', 'task_id', 'queue_entry_id', 'handoff_kind', 'draft_id',
                    'draft_digest', 'accepted_by_actor_id', 'accepted_at', 'request_id', 'decision_id',
                    'credential_policy_version', 'scope_policy_version', 'grant_version',
                )}
            queue = outcome.get('queue_entry')
            queue_view = ({key: queue.get(key) for key in (
                'entry_id', 'queue_id', 'receiver_label', 'received_at', 'review_due_at', 'status',
            )} if isinstance(queue, dict) else None)
            source_refs: dict[str, object] = {}
            if isinstance(diagnosis, dict):
                source_refs = {
                    'diagnosis_receipt_id': diagnosis.get('receipt_id'),
                    'run_id': diagnosis.get('run_id'),
                    'evidence_ids': diagnosis.get('evidence_ids', []),
                    'created_at': diagnosis.get('created_at'),
                }
            items.append({
                'task_id': task_id,
                'professional_type': 'S2_SCOPE_HANDOFF',
                'execution_core': 'PROFESSIONAL_INVESTIGATOR',
                'task_status': outcome.get('task_status', str(row['task_status'])),
                'task_control_revision': int(row['control_revision']),
                'latest_runs': run_refs,
                'business_outcome': outcome.get('business_outcome'),
                'currentness': outcome.get('currentness'),
                'reason_code': outcome.get('reason_code'),
                'diagnosis_receipt': diagnosis_view,
                'draft': draft_view,
                'handoff_receipt': receipt_view,
                'queue_entry': queue_view,
                'handoff_status': outcome.get('handoff_status'),
                'submitted': outcome.get('submitted') is True,
                'scope_authorized': outcome.get('scope_authorized') is True,
                'recovered': outcome.get('recovered') is True,
                'source_refs': source_refs,
            })
            continue

        from opspilot.domain.d3 import get_task_outcome

        outcome = get_task_outcome(database_path, task_id, identity.actor_id)
        plan_ref = outcome.get('plan') if isinstance(outcome.get('plan'), dict) else None
        if not plan_ref:
            continue
        plan_row = connection.execute(
            """SELECT p.canonical_plan_json, p.created_at, pcb.task_run_id
               FROM d3_plans p LEFT JOIN d3_plan_control_bindings pcb
                 ON pcb.tenant_id = p.tenant_id AND pcb.task_id = p.task_id AND pcb.plan_hash = p.plan_hash
               WHERE p.tenant_id = ? AND p.task_id = ? AND p.plan_hash = ?""",
            (identity.tenant_id, task_id, plan_ref['plan_hash']),
        ).fetchone()
        canonical_plan = json.loads(str(plan_row['canonical_plan_json'])) if plan_row else {}
        evidence_ids = canonical_plan.get('required_evidence_ids', [])
        evidence_ids = [str(value) for value in evidence_ids if isinstance(value, str)] if isinstance(evidence_ids, list) else []
        verification = outcome.get('verification') if isinstance(outcome.get('verification'), dict) else None
        verification_time = None
        if verification:
            verification_row = connection.execute(
                """SELECT observed_at FROM d3_verification_receipts
                   WHERE tenant_id = ? AND task_id = ? AND verification_id = ?""",
                (identity.tenant_id, task_id, verification.get('verification_id')),
            ).fetchone()
            verification_time = str(verification_row['observed_at']) if verification_row else None
        items.append({
            'task_id': task_id,
            'professional_type': 'S1_CONTROLLED_REPAIR',
            'execution_core': 'PROFESSIONAL_INVESTIGATOR_D3',
            'task_status': outcome.get('task_status', str(row['task_status'])),
            'task_control_revision': int(row['control_revision']),
            'latest_runs': run_refs,
            'business_outcome': outcome.get('business_outcome'),
            'currentness': 'PERSISTED_OUTCOME_NOT_CURRENT_PROBE',
            'outcome_time': verification_time or (str(plan_row['created_at']) if plan_row else str(row['created_at'])),
            'plan': plan_ref,
            'approval': outcome.get('approval'),
            'revalidation': outcome.get('revalidation'),
            'repair': outcome.get('repair'),
            'verification': verification,
            'frozen_report': outcome.get('frozen_report'),
            'delivery': outcome.get('delivery'),
            'local_report': outcome.get('local_report'),
            'source_refs': {
                'plan_hash': plan_ref.get('plan_hash'),
                'plan_task_run_id': str(plan_row['task_run_id']) if plan_row and plan_row['task_run_id'] else None,
                'evidence_ids': evidence_ids,
                'verification_id': verification.get('verification_id') if verification else None,
                'verification_observed_at': verification_time,
            },
        })
    return {
        'success': True,
        'session_id': str(run['session_id']),
        'authority': 'TRUSTED_SAME_SESSION_PROFESSIONAL_OUTCOMES',
        'currentness_semantics': 'REVALIDATED_BEFORE_EACH_MODEL_DISPATCH; S1 persisted verification is historical, S2 diagnosis currentness is Domain-derived',
        'items': items,
        'omitted_count': max(0, eligible_count - len(items)),
        'snapshot_digest': digest_json({
            'session_id': str(run['session_id']), 'tenant_id': identity.tenant_id,
            'actor_id': identity.actor_id, 'items': items,
            'omitted_count': max(0, eligible_count - len(items)),
        }),
    }


def read_session_professional_outcomes(path, run_id):
    """Read only S1/S2 outcomes linked to the current trusted Assistant Session."""
    run, identity = read_run(path, run_id, active=False)
    with connect(path) as connection:
        return _session_professional_outcomes(connection, run, identity)


def _proposal_source_is_current(connection, run, identity, result, request):
    try:
        if (
            run['kind'] != 'CHAT_READONLY' or run['task_id'] is not None
            or identity.role != 'SUPPORT' or result.get('success') is not True
            or result.get('proposal_type') != 'CONTROLLED_AUTH_INVESTIGATION'
            or result.get('authority') != 'MODEL_SUGGESTION_ONLY_UNTRUSTED'
            or result.get('task_created') is not False
            or result.get('authorization_created') is not False
            or result.get('requires_explicit_user_confirmation') is not True
        ):
            return False
        message, source_digest = _assistant_source_message(connection, run)
        args = request.get('args') if isinstance(request, dict) else None
        rationale = args.get('rationale') if isinstance(args, dict) else None
        return bool(
            result.get('source_message_id') == message['message_id']
            and result.get('source_message_digest') == source_digest
            and isinstance(rationale, str)
            and result.get('rationale') == rationale.strip()
        )
    except Exception:
        return False


def _professional_outcome_source_is_current(connection, run_id, result):
    try:
        run, identity = state(connection, run_id, active=False)
        expected = _session_professional_outcomes(connection, run, identity)
        return bool(
            result.get('success') is True
            and result.get('session_id') == expected['session_id']
            and result.get('authority') == expected['authority']
            and result.get('snapshot_digest') == expected['snapshot_digest']
        )
    except Exception:
        return False

def run_limits_for_experiment(experiment_id):
    """Keep ordinary Runs at 8/6; only explicitly scoped experiments vary."""
    from opspilot.domain.assistant_experiment import (
        AR03_MATERIAL_LIVE_01_EXPERIMENT_ID,
        AR03_MATERIAL_LIVE_01_RESUME_01_EXPERIMENT_ID,
        AR03_MATERIAL_LIVE_01_RESUME_02_EXPERIMENT_ID,
        AR03_MATERIAL_REMAINDER_01_EXPERIMENT_ID,
        AR04C_REAL_JOURNEY_01_EXPERIMENT_ID,
    )
    if experiment_id in {
        AR03_MATERIAL_LIVE_01_EXPERIMENT_ID,
        AR03_MATERIAL_LIVE_01_RESUME_01_EXPERIMENT_ID,
        AR03_MATERIAL_LIVE_01_RESUME_02_EXPERIMENT_ID,
    }:
        return 16, 10
    if experiment_id == AR03_MATERIAL_REMAINDER_01_EXPERIMENT_ID:
        return 16, None
    if experiment_id == AR04C_REAL_JOURNEY_01_EXPERIMENT_ID:
        return 8, None
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
            if tool_name == 'propose_controlled_auth_investigation':
                if not _proposal_source_is_current(connection, run, identity, value, request):
                    return False, 'ASSISTANT_INVESTIGATION_PROPOSAL_SOURCE_INVALID'
            elif tool_name == 'read_session_professional_outcomes':
                if not _professional_outcome_source_is_current(connection, run_id, value):
                    return False, 'ASSISTANT_PROFESSIONAL_OUTCOME_SOURCE_INVALID'
            elif row['evidence_id']:
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


def source_context_for_model(payload):
    """Present source time clearly; retain the full source ledger in audit metadata."""
    context = dict(payload)
    current = dict(payload['current_run'])
    count = len(current['business_observations'])
    current['description'] = (
        f'以下 {count} 条业务观察由本轮工具取得，只能对其实际覆盖的状态说本轮已查询。'
        if count else
        '本轮尚未重新查询业务状态。可以解释历史快照，或自主选择合法补查；当前状态仍待核实。'
    )
    context['current_run'] = current
    context['source_time_guide'] = (
        '通过来源检查的历史快照可引用；引用资格有效不表示业务状态刚被查询。'
        '历史快照用于说明过去；current_run.business_observations 才是本轮新取得的业务观察。'
        '没有新观察时，可以解释旧结果或说明当前未知，不能声称本轮已重读。'
    )
    history = []
    for prior in payload.get('history_sources', []):
        valid = prior['current_source_valid']
        snapshots = []
        for source in prior['sources'] if valid else []:
            snapshots.append({
                'summary': source['summary'],
                'reference': {
                    'source_run_id': prior['run_id'],
                    **{key: source.get(key) for key in (
                        'call_id', 'observation_id', 'evidence_id', 'result_digest',
                        'observed_at', 'completed_at',
                    )},
                },
            })
        history.append({
            'source_run_id': prior['run_id'],
            'reference_scope': 'HISTORICAL_SNAPSHOT_NOT_REQUERIED' if valid else 'EXCLUDED_HISTORY',
            'exclusion_reason': prior['exclusion_reason'],
            'snapshots': snapshots,
            'omitted_source_count': prior.get('omitted_source_count', 0),
        })
    context['history_sources'] = history
    return context
