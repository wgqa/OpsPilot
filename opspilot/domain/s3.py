"""S3 local asynchronous order model and deterministic read-only evidence contract.

Fixture preparation is deliberately separate from Agent tools. No runtime mutation
of order, delivery or receiver state is exposed to the model or Web caller.
"""
from __future__ import annotations

import json
import secrets
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import httpx

from opspilot.domain.database import connect, initialize
from opspilot.domain.d2 import ScopeDenied, _fact, canonical_json, digest_json, utc_now

SERVICE = "orders-async-demo"
INTEGRATION = "async-integration-a"
ROUTE = "/api/async-orders/async-order"
ORDER = "async-order"
PROBLEM = "async_callback"
POLICY = "s3-callback-evidence-v1"
FACT_TO_TOOL = {"s3_order": "get_order_status", "s3_delivery": "get_callback_delivery", "s3_receiver": "get_receiver_processing"}
SOURCES = {"s3_order": "http:loopback-async-orders", "s3_delivery": "sqlite:s3_deliveries", "s3_receiver": "sqlite:s3_receivers"}
OUTCOMES = {"ORDER_PROCESSING", "CALLBACK_DELIVERY_FAILED", "RECEIVER_PROCESSING_UNCONFIRMED"}

SCHEMA = """
CREATE TABLE IF NOT EXISTS s3_orders (
 tenant_id TEXT NOT NULL, service_id TEXT NOT NULL, integration_id TEXT NOT NULL,
 order_id TEXT NOT NULL, status TEXT NOT NULL CHECK(status IN ('PROCESSING','COMPLETED')),
 version INTEGER NOT NULL CHECK(version>0), contract_version INTEGER NOT NULL,
 PRIMARY KEY(tenant_id,service_id,order_id),
 FOREIGN KEY(tenant_id,service_id) REFERENCES services(tenant_id,service_id));
CREATE TABLE IF NOT EXISTS s3_deliveries (
 tenant_id TEXT NOT NULL, service_id TEXT NOT NULL, order_id TEXT NOT NULL,
 event_id TEXT NOT NULL, order_version INTEGER NOT NULL, version INTEGER NOT NULL,
 status TEXT NOT NULL CHECK(status IN ('NOT_DUE','FAILED','ACKNOWLEDGED')),
 receiver_http_status INTEGER, transport_request_id TEXT, response_digest TEXT,
 PRIMARY KEY(tenant_id,service_id,order_id));
CREATE TABLE IF NOT EXISTS s3_receivers (
 tenant_id TEXT NOT NULL, service_id TEXT NOT NULL, order_id TEXT NOT NULL,
 event_id TEXT NOT NULL, delivery_version INTEGER NOT NULL, version INTEGER NOT NULL,
 status TEXT NOT NULL CHECK(status IN ('NOT_RECEIVED','QUEUED','PROCESSED')),
 PRIMARY KEY(tenant_id,service_id,order_id));
CREATE TABLE IF NOT EXISTS s3_http_observations (
 request_id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, service_id TEXT NOT NULL,
 integration_id TEXT NOT NULL, principal_id TEXT NOT NULL, route TEXT NOT NULL,
 authn_event_id INTEGER NOT NULL REFERENCES auth_events(event_id),
 http_status INTEGER NOT NULL, body_json TEXT NOT NULL, body_digest TEXT NOT NULL,
 created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS s3_diagnoses (
 receipt_id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, task_id TEXT NOT NULL REFERENCES task_bindings(task_id),
 run_id TEXT NOT NULL UNIQUE REFERENCES task_runs(run_id), control_revision INTEGER NOT NULL,
 gate_policy TEXT NOT NULL, outcome TEXT NOT NULL, evidence_ids_json TEXT NOT NULL,
 body_json TEXT NOT NULL, digest TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS s3_model_contexts (
 call_id TEXT PRIMARY KEY,
 task_id TEXT NOT NULL, run_id TEXT NOT NULL, messages_json TEXT NOT NULL, tools_json TEXT NOT NULL);
CREATE TRIGGER IF NOT EXISTS s3_diagnoses_immutable_update BEFORE UPDATE ON s3_diagnoses
 BEGIN SELECT RAISE(ABORT,'S3 diagnosis is immutable'); END;
CREATE TRIGGER IF NOT EXISTS s3_diagnoses_no_delete BEFORE DELETE ON s3_diagnoses
 BEGIN SELECT RAISE(ABORT,'S3 diagnosis is immutable'); END;
"""


def get_s3_binding(connection: sqlite3.Connection, task_id: str) -> dict[str, object]:
    row = connection.execute(
        """SELECT b.*, s.route, i.credential_ref, i.config_version, p.principal_version,
                  p.status AS principal_status, a.policy_version, a.accepted_credential_ref
           FROM task_bindings b JOIN services s ON s.tenant_id=b.tenant_id AND s.service_id=b.service_id
           AND s.integration_id=b.integration_id JOIN integrations i ON i.tenant_id=b.tenant_id
           AND i.integration_id=b.integration_id AND i.principal_id=b.principal_id
           JOIN principals p ON p.tenant_id=b.tenant_id AND p.principal_id=b.principal_id
           JOIN auth_policies a ON a.tenant_id=b.tenant_id AND a.service_id=b.service_id
           WHERE b.task_id=? AND b.service_id=? AND s.route=?""", (task_id, SERVICE, ROUTE),
    ).fetchone()
    if row is None:
        raise ScopeDenied("S3_RESOURCE_OUTSIDE_TASK_BINDING")
    order = connection.execute("SELECT 1 FROM s3_orders WHERE tenant_id=? AND service_id=? AND integration_id=? AND order_id=?",
                               (row["tenant_id"], SERVICE, row["integration_id"], ORDER)).fetchone()
    if order is None:
        raise ScopeDenied("S3_RESOURCE_OUTSIDE_TASK_BINDING")
    return dict(row)


def _snapshot(connection, binding):
    key = (binding["tenant_id"], SERVICE, ORDER)
    order = dict(connection.execute("SELECT * FROM s3_orders WHERE tenant_id=? AND service_id=? AND order_id=?", key).fetchone())
    delivery = dict(connection.execute("SELECT * FROM s3_deliveries WHERE tenant_id=? AND service_id=? AND order_id=?", key).fetchone())
    receiver = dict(connection.execute("SELECT * FROM s3_receivers WHERE tenant_id=? AND service_id=? AND order_id=?", key).fetchone())
    versions = {"order_version": order["version"], "delivery_version": delivery["version"],
                "receiver_version": receiver["version"], "contract_version": order["contract_version"],
                "config_version": binding["config_version"], "principal_version": binding["principal_version"],
                "policy_version": binding["policy_version"]}
    return order, delivery, receiver, versions


def prepare_s3_fixture(path: str | Path, state: str, *, tenant_id: str = "tenant-a") -> dict[str, object]:
    """Explicit test setup, NOT a registered tool/API. Performs a real receiver POST."""
    if state not in {"PROCESSING", "DELIVERY_FAILED", "DELIVERED_PENDING"}:
        raise ValueError("Unknown S3 test state")
    initialize(path)
    suffix = "a" if tenant_id == "tenant-a" else "b"
    integration = f"async-integration-{suffix}"
    event_id, transport_id = f"event-{uuid.uuid4()}", f"transport-{uuid.uuid4()}"
    status = None
    response_body: dict[str, object] | None = None
    transport_trace: list[dict[str, object]] = []
    if state != "PROCESSING":
        class Receiver(BaseHTTPRequestHandler):
            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                code = 503 if state == "DELIVERY_FAILED" else 202
                result = {"event_id": body["event_id"], "request_id": body["request_id"],
                          "receiver_state": "UNAVAILABLE" if code == 503 else "QUEUED"}
                raw = canonical_json(result).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)
                transport_trace.append({"request": body, "http_status": code, "response": result})
            def log_message(self, *_):
                pass
        server = ThreadingHTTPServer(("127.0.0.1", 0), Receiver)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            response = httpx.post(f"http://127.0.0.1:{server.server_port}/callback",
                                  json={"event_id": event_id, "order_id": ORDER, "request_id": transport_id}, timeout=5)
            status, response_body = response.status_code, response.json()
        finally:
            server.shutdown()
            thread.join()
            server.server_close()
    with connect(path) as c:
        c.execute("BEGIN IMMEDIATE")
        c.execute("INSERT OR IGNORE INTO principals VALUES(?,?, 'ENABLED',1)", (tenant_id,f"async-principal-{suffix}"))
        c.execute("INSERT OR IGNORE INTO integrations VALUES(?,?,?, ?,1)", (tenant_id, integration, f"async-principal-{suffix}", "cred-v2"))
        c.execute("INSERT OR IGNORE INTO services VALUES(?,?,?,?)", (tenant_id, SERVICE, integration, ROUTE))
        c.execute("INSERT OR IGNORE INTO auth_policies VALUES(?,?,?,1)", (tenant_id, SERVICE, "cred-v2"))
        c.execute("INSERT OR IGNORE INTO principal_scope_grants (tenant_id,principal_id,granted_scopes_json,grant_version) VALUES(?,?,?,1)", (tenant_id,f"async-principal-{suffix}",canonical_json(["orders.async.read"])))
        c.execute("INSERT OR IGNORE INTO route_scope_policies (tenant_id,service_id,route,required_scopes_json,scope_policy_version) VALUES(?,?,?,?,1)", (tenant_id,SERVICE,ROUTE,canonical_json(["orders.async.read"])))
        previous = c.execute("SELECT version FROM s3_orders WHERE tenant_id=? AND service_id=? AND order_id=?", (tenant_id,SERVICE,ORDER)).fetchone()
        version = int(previous[0]) + 1 if previous else 1
        c.execute("INSERT OR REPLACE INTO s3_orders VALUES(?,?,?,?,?,?,1)", (tenant_id,SERVICE,integration,ORDER,"PROCESSING" if state == "PROCESSING" else "COMPLETED",version))
        c.execute("INSERT OR REPLACE INTO s3_deliveries VALUES(?,?,?,?,?,?,?,?,?,?)", (tenant_id,SERVICE,ORDER,event_id,version,version,
                  "NOT_DUE" if status is None else "FAILED" if status == 503 else "ACKNOWLEDGED",status,transport_id if status else None,
                  digest_json(response_body) if response_body else None))
        c.execute("INSERT OR REPLACE INTO s3_receivers VALUES(?,?,?,?,?,?,?)", (tenant_id,SERVICE,ORDER,event_id,version,version,"QUEUED" if status == 202 else "NOT_RECEIVED"))
    return {"preparation_only": True, "agent_actions": [], "state": state, "order_version": version,
            "receiver_http_status": status, "transport_trace": transport_trace}


def order_http_payload(path, tenant_id, integration_id, request_id, authn_event_id):
    with connect(path) as c:
        row = c.execute("SELECT * FROM s3_orders WHERE tenant_id=? AND service_id=? AND integration_id=? AND order_id=?",
                        (tenant_id,SERVICE,integration_id,ORDER)).fetchone()
        if row is None:
            return None
        payload = {"order_id": ORDER, "status": row["status"], "order_version": row["version"],
                   "contract_version": row["contract_version"], "request_id": request_id, "authn_event_id": authn_event_id}
        principal = c.execute("SELECT principal_id FROM integrations WHERE tenant_id=? AND integration_id=?", (tenant_id,integration_id)).fetchone()[0]
        c.execute("INSERT INTO s3_http_observations VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                  (request_id,tenant_id,SERVICE,integration_id,principal,ROUTE,authn_event_id,200,canonical_json(payload),digest_json(payload),utc_now()))
    return payload


def get_order_status_fact(path, task_id, api_url):
    from opspilot.domain.database import get_credential_secret
    with connect(path) as c:
        binding = get_s3_binding(c, task_id)
        _, _, _, before = _snapshot(c, binding)
    secret = get_credential_secret(path, str(binding["tenant_id"]), str(binding["credential_ref"]))
    response = httpx.get(f"{api_url}{ROUTE}", headers={"X-Integration-ID": str(binding["integration_id"]), "Authorization": f"Bearer {secret}"}, timeout=5)
    body = response.json()
    with connect(path) as c:
        binding = get_s3_binding(c, task_id)
        _, _, _, after = _snapshot(c, binding)
    return _fact(binding, fact_type="s3_order", resource_id=f"{SERVICE}:{ORDER}", data_source=SOURCES["s3_order"],
                 observed_versions=after, facts={"http_status": response.status_code, "body": body,
                 "versions_before": before, "versions_after": after}, original_result_ref=f"s3-http://{body.get('request_id')}")


def _table_fact(path, task_id, fact_type):
    with connect(path) as c:
        binding = get_s3_binding(c, task_id)
        order, delivery, receiver, versions = _snapshot(c, binding)
    record = delivery if fact_type == "s3_delivery" else receiver
    return _fact(binding, fact_type=fact_type, resource_id=f"{SERVICE}:{ORDER}", data_source=SOURCES[fact_type],
                 observed_versions=versions, facts=record, original_result_ref=f"s3://{record['event_id']}/v{record['version']}")


def get_callback_delivery_fact(path, task_id):
    return _table_fact(path, task_id, "s3_delivery")


def get_receiver_processing_fact(path, task_id):
    return _table_fact(path, task_id, "s3_receiver")


def current_s3_evidence(connection, task_id, evidence_ids=None, *, historical=False):
    """Revalidate actual rows/HTTP observations, not just the model's typed envelope."""
    binding = get_s3_binding(connection, task_id)
    order, delivery, receiver, current_versions = _snapshot(connection, binding)
    rows = connection.execute("SELECT * FROM d2_evidence WHERE task_id=? ORDER BY fetched_at,rowid", (task_id,)).fetchall()
    current, excluded = [], []
    for row in rows:
        e = dict(row)
        if evidence_ids is not None and e["evidence_id"] not in evidence_ids:
            continue
        reason = None
        try:
            facts, versions = json.loads(e["facts_json"]), json.loads(e["observed_versions_json"])
            fact_type = str(e["fact_type"])
            if fact_type not in FACT_TO_TOOL:
                continue
            payload = {"tenant_id": e["tenant_id"], "task_id": task_id, "fact_type": fact_type,
                       "resource_id": e["resource_id"], "principal_id": e["principal_id"],
                       "data_source": e["data_source"], "observed_versions": versions,
                       "facts": facts, "trust_class": e["trust_class"]}
            age = (datetime.now(timezone.utc) - datetime.fromisoformat(e["fetched_at"].replace("Z","+00:00"))).total_seconds()
            observation = connection.execute("SELECT 1 FROM d2_tool_observations WHERE task_id=? AND evidence_id=? AND tool_name=? AND status='OK'", (task_id,e["evidence_id"],FACT_TO_TOOL[fact_type])).fetchone()
            if (e["tenant_id"] != binding["tenant_id"] or e["principal_id"] != binding["principal_id"]
                or e["resource_id"] != f"{SERVICE}:{ORDER}" or e["data_source"] != SOURCES[fact_type]
                or e["trust_class"] != "untrusted_tool_observation" or e["digest"] != digest_json(payload) or not observation):
                reason = "S3_FACT_ORIGIN_INVALID"
            elif not historical and (age > 300 or age < -30):
                reason = "S3_EVIDENCE_EXPIRED"
            elif (set(versions) != set(current_versions) or any(type(v) is not int or v < 1 for v in versions.values())
                  or (not historical and versions != current_versions)):
                reason = "S3_CURRENT_VERSION_MISMATCH"
            elif fact_type == "s3_order":
                body = facts.get("body", {})
                http = connection.execute("SELECT h.* FROM s3_http_observations h JOIN auth_events a ON a.event_id=h.authn_event_id WHERE h.request_id=? AND h.tenant_id=? AND h.service_id=? AND h.integration_id=? AND h.principal_id=? AND h.route=? AND a.result_code='AUTH_ACCEPTED'", (body.get("request_id"),binding["tenant_id"],SERVICE,binding["integration_id"],binding["principal_id"],ROUTE)).fetchone()
                if (http is None or facts.get("http_status") != 200 or http["body_digest"] != digest_json(body)
                    or facts.get("versions_before") != versions or facts.get("versions_after") != versions
                    or body.get("order_id") != ORDER or body.get("order_version") != versions.get("order_version")
                    or (not historical and body.get("status") != order["status"])):
                    reason = "S3_HTTP_OBSERVATION_INVALID"
            elif not historical and facts != (delivery if fact_type == "s3_delivery" else receiver):
                reason = "S3_CURRENT_FACT_MISMATCH"
            elif fact_type in {"s3_delivery", "s3_receiver"} and (facts.get("tenant_id") != binding["tenant_id"] or facts.get("service_id") != SERVICE or facts.get("order_id") != ORDER):
                reason = "S3_CORRELATION_INVALID"
            if reason is None:
                current.append({**e, "facts": facts, "observed_versions": versions})
        except (ValueError, TypeError, KeyError):
            reason = "S3_MALFORMED_EVIDENCE"
        if reason:
            excluded.append({"source_id": e["evidence_id"], "reason": reason})
    return current, excluded


def _gate_from_evidence(evidence):
    by_type = {e["fact_type"]: e for e in evidence}
    outcome = None
    needed = ["s3_order"]
    order = by_type.get("s3_order")
    used = []
    if order:
        used.append(order)
        if order["facts"]["body"]["status"] == "PROCESSING":
            outcome = "ORDER_PROCESSING"
        else:
            needed = ["s3_delivery"]
            delivery = by_type.get("s3_delivery")
            if delivery and delivery["facts"]["order_version"] == order["facts"]["body"]["order_version"]:
                used.append(delivery)
                d = delivery["facts"]
                if d["status"] == "FAILED" and d["receiver_http_status"] == 503 and d["transport_request_id"] and d["response_digest"]:
                    outcome = "CALLBACK_DELIVERY_FAILED"
                elif d["status"] == "ACKNOWLEDGED" and d["receiver_http_status"] == 202:
                    needed = ["s3_receiver"]
                    receiver = by_type.get("s3_receiver")
                    if receiver and receiver["facts"]["event_id"] == d["event_id"] and receiver["facts"]["delivery_version"] == d["version"]:
                        used.append(receiver)
                        if receiver["facts"]["status"] == "QUEUED":
                            outcome = "RECEIVER_PROCESSING_UNCONFIRMED"
    return {"decision": "DIAGNOSED" if outcome else "NEED_MORE", "outcome": outcome,
            "reason_code": outcome or "S3_CURRENT_FACTS_REQUIRED", "required_facts": [] if outcome else needed,
            "checked_fact_ids": [x["evidence_id"] for x in used], "recovered": False, "side_effects": []}


def evaluate_s3_gate(path, task_id, evidence_ids=None):
    with connect(path) as c:
        evidence, excluded = current_s3_evidence(c, task_id, evidence_ids)
    return {**_gate_from_evidence(evidence), "excluded_sources": excluded, "policy": POLICY}


def persist_s3_diagnosis(path, task_id, run_id, evidence_ids, summary="", *, stop_reason=None, summary_gate_outcome=None, summary_call_id=None):
    from opspilot.domain.task_control import assert_task_control_in_transaction, _insert_outbox
    with connect(path) as c:
        c.execute("BEGIN IMMEDIATE")
        b = get_s3_binding(c, task_id)
        assert_task_control_in_transaction(c, str(b["tenant_id"]), task_id, None, run_id=run_id)
        existing = c.execute("SELECT * FROM s3_diagnoses WHERE run_id=?", (run_id,)).fetchone()
        if existing:
            return dict(existing)
        evidence, excluded = current_s3_evidence(c, task_id, evidence_ids)
        gate = {**_gate_from_evidence(evidence), "excluded_sources": excluded, "policy": POLICY}
        if gate["decision"] != "DIAGNOSED":
            gate.update(decision="INCONCLUSIVE", outcome="INCONCLUSIVE", reason_code=stop_reason or "S3_INSUFFICIENT_CURRENT_FACTS")
        narrative = c.execute("SELECT p.call_id FROM d5_context_provenance p JOIN d2_model_traces t ON t.call_id=p.call_id JOIN d2_attempts a ON a.attempt_id=t.attempt_id WHERE p.call_id=? AND p.task_id=? AND a.run_id=? AND t.status='OK'", (summary_call_id,task_id,run_id)).fetchone() if summary_call_id else None
        if summary_gate_outcome != gate["outcome"] or narrative is None:
            summary = ""
        revision = int(c.execute("SELECT control_revision FROM task_controls WHERE task_id=?", (task_id,)).fetchone()[0])
        body = {"schema": POLICY, "task_id": task_id, "run_id": run_id, "control_revision": revision,
                "gate": gate, "evidence": [{"id": e["evidence_id"], "digest": e["digest"], "fact_type": e["fact_type"], "facts": e["facts"], "versions": e["observed_versions"]} for e in evidence],
                "model_summary_untrusted": summary[:1200], "explanation_call_id":summary_call_id if narrative else None,
                "recovered": False, "business_writes": 0}
        ref = f"s3-diagnosis-{uuid.uuid4()}"
        c.execute("INSERT INTO s3_diagnoses VALUES(?,?,?,?,?,?,?,?,?,?,?)", (ref,b["tenant_id"],task_id,run_id,revision,POLICY,gate["outcome"],canonical_json(gate["checked_fact_ids"]),canonical_json(body),digest_json(body),utc_now()))
        c.execute("UPDATE task_bindings SET status=? WHERE task_id=?", ("NO_ACTION" if gate["decision"] == "DIAGNOSED" else "INCONCLUSIVE",task_id))
        session_id = c.execute("SELECT session_id FROM task_runs WHERE run_id=?", (run_id,)).fetchone()[0]
        _insert_outbox(c,str(b["tenant_id"]),task_id,str(session_id),"S3_DIAGNOSIS",ref,"S3_DIAGNOSIS_FROZEN",{"receipt_id":ref,"business_outcome":gate["outcome"],"run_id":run_id,"recovered":False})
        return dict(c.execute("SELECT * FROM s3_diagnoses WHERE receipt_id=?", (ref,)).fetchone())


def get_s3_outcome(path, task_id):
    with connect(path) as c:
        return s3_outcome_in_transaction(c, task_id)


def s3_outcome_in_transaction(c, task_id):
        row = c.execute("SELECT * FROM s3_diagnoses WHERE task_id=? ORDER BY rowid DESC LIMIT 1", (task_id,)).fetchone()
        if row is None:
            return None
        body = json.loads(row["body_json"])
        evidence, excluded = current_s3_evidence(c, task_id, json.loads(row["evidence_ids_json"]))
        rev = c.execute("SELECT control_revision FROM task_controls WHERE task_id=?", (task_id,)).fetchone()[0]
        current = not excluded and rev == row["control_revision"] and digest_json(body) == row["digest"]
        narrative_exclusions = _explanation_exclusions(c, task_id, body) if current else [{"source_id":row["receipt_id"],"reason":"S3_CURRENT_FACTS_INVALIDATED"}]
        narrative_current = current and not narrative_exclusions
        return {"receipt_id":row["receipt_id"],"outcome":row["outcome"] if current else "INCONCLUSIVE",
                "currentness":"CURRENT" if current else "INVALIDATED_BY_CURRENT_FACTS", "recovered":False,
                "explanation":body.get("model_summary_untrusted","") if narrative_current else "",
                "explanation_currentness":"CURRENT" if narrative_current else "SOURCE_INVALIDATED",
                "explanation_excluded_sources":narrative_exclusions,
                "gate":body["gate"] if current else {"decision":"INCONCLUSIVE","reason_code":"S3_SOURCE_INVALIDATED","excluded_sources":excluded},"body":body}


def _explanation_exclusions(c, task_id, body):
    """A frozen narrative is not current merely because its factual Gate still is."""
    if not body.get("model_summary_untrusted"):
        return []
    provenance = c.execute("SELECT * FROM d5_context_provenance WHERE call_id=? AND task_id=?", (body.get("explanation_call_id"),task_id)).fetchone()
    if provenance is None:
        return [{"source_id":body.get("explanation_call_id"),"reason":"EXPLANATION_PROVENANCE_UNAVAILABLE"}]
    from opspilot.domain.episodic_memory import _memory_exclusion_reason, _now
    from opspilot.domain.s3_assets import load_knowledge, load_s3_skill
    excluded=[]
    binding=get_s3_binding(c,task_id)
    for ref in json.loads(provenance["selected_memories_json"]):
        memory=c.execute("SELECT * FROM d5_memories WHERE memory_id=?", (ref["memory_id"],)).fetchone()
        reason="MEMORY_MISSING" if memory is None else _memory_exclusion_reason(c,memory,task_id=task_id,problem_type=PROBLEM,service_id=SERVICE,now=_now())
        if memory and (memory["tenant_id"] != binding["tenant_id"] or int(memory["version"]) != int(ref["version"]) or memory["content_digest"] != ref["digest"]):
            reason=reason or "MEMORY_VERSION_CHANGED"
        if reason:
            excluded.append({"source_type":"EPISODIC_MEMORY","source_id":ref["memory_id"],"reason":f"EXPLANATION_{reason}"})
    available={d["document_id"]:d for d in load_knowledge()}
    for ref in json.loads(provenance["selected_knowledge_json"]):
        doc=available.get(ref["document_id"])
        if doc is None or any(doc.get(k) != ref.get(k) for k in ("version","digest","source","valid_from")):
            excluded.append({"source_type":"KNOWLEDGE","source_id":ref["document_id"],"reason":"EXPLANATION_KNOWLEDGE_INVALIDATED"})
    name=provenance["selected_skill_name"]
    if name:
        try:
            skill=load_s3_skill(name)
            valid=skill["version"] == provenance["selected_skill_version"] and skill["digest"] == provenance["selected_skill_digest"]
        except (OSError,ValueError,KeyError):
            valid=False
        if not valid:
            excluded.append({"source_type":"SKILL","source_id":name,"reason":"EXPLANATION_SKILL_INVALIDATED"})
    _,fact_excluded=current_s3_evidence(c,task_id,json.loads(provenance["evidence_ids_json"]))
    excluded.extend(fact_excluded)
    return excluded


def s3_memory_source(connection, task_id):
    from opspilot.domain.episodic_memory import MemorySourceRejected, project_id_for_service
    b = get_s3_binding(connection, task_id)
    row = connection.execute("SELECT * FROM s3_diagnoses WHERE task_id=? ORDER BY rowid DESC LIMIT 1", (task_id,)).fetchone()
    if row is None or row["outcome"] not in OUTCOMES:
        raise MemorySourceRejected("S3 requires a trusted read-only diagnosis")
    body = json.loads(row["body_json"])
    ids = json.loads(row["evidence_ids_json"])
    evidence, excluded = current_s3_evidence(connection, task_id, ids, historical=True)
    frozen = {e["id"]: e for e in body["evidence"]}
    gate = _gate_from_evidence(evidence)
    if (digest_json(body) != row["digest"] or excluded or gate["outcome"] != row["outcome"] or not ids
        or any(e["evidence_id"] not in frozen or e["digest"] != frozen[e["evidence_id"]]["digest"] for e in evidence)):
        raise MemorySourceRejected("S3 source facts/receipt cannot be verified")
    return {"tenant_id": b["tenant_id"], "project_id":project_id_for_service(SERVICE),"problem_type":PROBLEM,
            "source_outcome":"DIAGNOSED","source_task_id":task_id,"source_evidence_ids":ids,
            "source_report_ref":None,"source_verification_id":None,
            "source_refs":[{"kind":"S3_DIAGNOSIS","id":row["receipt_id"],"digest_or_version":row["digest"]}]+[{"kind":"EVIDENCE","id":e["evidence_id"],"digest_or_version":e["digest"]} for e in evidence],
            "source_facts":{"outcome":row["outcome"],"route":ROUTE,"observed_facts":[e["facts"] for e in evidence],"required_current_checks":[e["fact_type"] for e in evidence]}}
