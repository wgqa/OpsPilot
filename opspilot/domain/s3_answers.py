"""Immutable user delivery for S3 business Runs; never a Diagnosis or permission."""
from __future__ import annotations

import json

from opspilot.domain.database import connect
from opspilot.domain.d2 import ScopeDenied, canonical_json, digest_json, utc_now

SCHEMA = """
CREATE TABLE IF NOT EXISTS s3_run_answers (
 run_id TEXT PRIMARY KEY REFERENCES task_runs(run_id), task_id TEXT NOT NULL REFERENCES task_bindings(task_id),
 tenant_id TEXT NOT NULL, body_json TEXT NOT NULL, digest TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TRIGGER IF NOT EXISTS s3_run_answer_no_update BEFORE UPDATE ON s3_run_answers
 BEGIN SELECT RAISE(ABORT,'S3 user answer is immutable'); END;
CREATE TRIGGER IF NOT EXISTS s3_run_answer_no_delete BEFORE DELETE ON s3_run_answers
 BEGIN SELECT RAISE(ABORT,'S3 user answer is immutable'); END;
"""


def persist_run_answer(path, task_id, run_id, *, context, answer, result_state, source_refs, result, report_ref):
    from opspilot.domain.investigation_context import validate_task_run_context_in_transaction
    from opspilot.domain.s3 import get_s3_binding, current_s3_evidence
    if not isinstance(answer,str) or not answer.strip() or len(answer)>20000 or result_state not in {"ANSWERED","PARTIAL","NOT_COMPLETED"}:
        raise ValueError("S3_USER_ANSWER_INVALID")
    body={"run_id":run_id,"task_id":task_id,"source_message_id":context["source_message_id"],
          "source_digest":next(ref["digest"] for ref in context["input_refs"] if ref["message_id"]==context["source_message_id"]),
          "control_revision":context["expected_control_revision"],"answer_text":answer,"result_state":result_state,
          "source_refs":source_refs,"result":result,"report_ref":report_ref,
          "authority":"USER_DELIVERY_NOT_BUSINESS_RECEIPT","currentness":"HISTORICAL_AT_DELIVERY"}
    digest=digest_json(body)
    with connect(path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        binding=get_s3_binding(connection,task_id)
        validate_task_run_context_in_transaction(connection,task_id,context)
        if not connection.execute("SELECT 1 FROM s3_diagnoses WHERE receipt_id=? AND task_id=? AND run_id=?",(report_ref,task_id,run_id)).fetchone():
            raise ScopeDenied("S3_USER_ANSWER_DIAGNOSIS_REFERENCE_INVALID")
        ids=[ref["evidence_id"] for ref in source_refs if ref.get("kind")=="EVIDENCE"]
        pins={ref["evidence_id"]:ref["observation_id"] for ref in source_refs if ref.get("kind")=="EVIDENCE"}
        evidence,excluded=current_s3_evidence(connection,task_id,ids,run_id=run_id,observation_ids=pins)
        if excluded or set(ids)!={item["evidence_id"] for item in evidence}:
            raise ScopeDenied("S3_USER_ANSWER_SOURCES_INVALIDATED")
        existing=connection.execute("SELECT digest FROM s3_run_answers WHERE run_id=? AND task_id=?",(run_id,task_id)).fetchone()
        if existing:
            if existing[0]!=digest:
                raise ValueError("S3_USER_ANSWER_REPLAY_CONFLICT")
            return body
        connection.execute("INSERT INTO s3_run_answers VALUES(?,?,?,?,?,?)",(run_id,task_id,binding["tenant_id"],canonical_json(body),digest,utc_now()))
    return body


def answers_in_transaction(connection, task_id):
    # The caller has verified tenant/owner; independently recheck current S3 scope.
    from opspilot.domain.s3 import get_s3_binding
    binding=connection.execute("SELECT service_id FROM task_bindings WHERE task_id=?",(task_id,)).fetchone()
    if binding is None or binding[0]!="orders-async-demo":
        return []
    try:
        get_s3_binding(connection,task_id)
    except ScopeDenied:
        return []
    rows=connection.execute("SELECT body_json,digest,created_at FROM s3_run_answers WHERE task_id=? ORDER BY rowid",(task_id,)).fetchall()
    result=[]
    for row in rows:
        body=json.loads(row[0])
        if digest_json(body)!=row[1]:
            raise ScopeDenied("S3_USER_ANSWER_DIGEST_INVALID")
        result.append({**body,"created_at":row[2]})
    return result


def prior_answer_rows(connection, tenant_id, session_id, task_id, before_sequence, limit):
    """Adapt this narrow store to the existing shared historical-source assembler."""
    rows=connection.execute(
        """SELECT a.*,r.kind AS run_kind,r.status AS run_status,r.source_message_id AS run_source_message_id,
                  r.consumed_message_seq AS run_consumed_message_seq,r.session_id,
                  m.body AS source_message_body,m.body_digest AS actual_source_digest,m.sequence AS source_sequence,
                  m.role AS source_role,m.input_kind AS source_input_kind,m.session_id AS source_session_id,
                  m.tenant_id AS source_tenant_id
           FROM s3_run_answers a JOIN task_runs r ON r.run_id=a.run_id AND r.task_id=a.task_id AND r.tenant_id=a.tenant_id
           JOIN messages m ON m.message_id=r.source_message_id AND m.task_id=a.task_id AND m.tenant_id=a.tenant_id
           WHERE a.tenant_id=? AND a.task_id=? AND r.session_id=? AND m.session_id=? AND m.sequence<?
           ORDER BY m.sequence DESC LIMIT ?""",(tenant_id,task_id,session_id,session_id,before_sequence,limit),
    ).fetchall()
    converted,excluded=[],[]
    for raw in rows:
        row=dict(raw)
        body=json.loads(row["body_json"])
        if digest_json(body)!=row["digest"]:
            excluded.append({"source_id":row["run_id"],"reason":"S3_USER_ANSWER_DIGEST_INVALID"})
            continue
        refs=canonical_json(body["source_refs"])
        result=canonical_json(body["result"])
        normalized={"run_id":row["run_id"],"result_state":body["result_state"],"answer_text":body["answer_text"],
                    "source_refs_json":refs,"result_json":result,"reason_code":None}
        converted.append({**row,**normalized,"source_message_id":body["source_message_id"],"source_digest":body["source_digest"],
                          "result_digest":digest_json(normalized),"completed_at":row["created_at"],
                          "result_storage":"S3_RUN_ANSWER","storage_digest":row["digest"]})
    return converted,excluded
