"""S3 local asynchronous order model and deterministic read-only evidence contract.

Fixture preparation is deliberately separate from Agent tools. No runtime mutation
of order, delivery or receiver state is exposed to the model or Web caller.
"""
from __future__ import annotations

import json
import re
import secrets
import sqlite3
import threading
import uuid
from datetime import datetime, timedelta, timezone
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
OUTCOMES = {"ORDER_PROCESSING", "CALLBACK_DELIVERY_FAILED", "RECEIVER_PROCESSING_UNCONFIRMED", "RECEIVER_PROCESSED"}


def _strict_positive_version(value: object) -> int:
    """Accept only an actual positive integer authorization version."""
    if type(value) is not int or value < 1:
        raise ValueError("authorization version must be a positive integer")
    return value


def _now() -> datetime:
    return datetime.now(timezone.utc)

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
 failure_code TEXT, attempt_count INTEGER NOT NULL DEFAULT 0, max_attempts INTEGER NOT NULL DEFAULT 3,
 retry_state TEXT, retry_at TEXT, transport_response_json TEXT NOT NULL DEFAULT '{}',
 PRIMARY KEY(tenant_id,service_id,order_id));
CREATE TABLE IF NOT EXISTS s3_receivers (
 tenant_id TEXT NOT NULL, service_id TEXT NOT NULL, order_id TEXT NOT NULL,
 event_id TEXT NOT NULL, delivery_version INTEGER NOT NULL, version INTEGER NOT NULL,
 status TEXT NOT NULL CHECK(status IN ('NOT_RECEIVED','QUEUED','PROCESSED')),
 accepted_at TEXT, processing_sla_seconds INTEGER,
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
CREATE TABLE IF NOT EXISTS s3_task_resources (
 task_id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, service_id TEXT NOT NULL,
 integration_id TEXT NOT NULL, order_id TEXT NOT NULL, confirmed_by TEXT NOT NULL,
 confirmed_at TEXT NOT NULL, selection_digest TEXT NOT NULL,
 FOREIGN KEY(task_id,tenant_id) REFERENCES task_bindings(task_id,tenant_id) ON DELETE CASCADE,
 FOREIGN KEY(tenant_id,service_id,order_id) REFERENCES s3_orders(tenant_id,service_id,order_id),
 FOREIGN KEY(tenant_id,integration_id) REFERENCES integrations(tenant_id,integration_id));
CREATE TRIGGER IF NOT EXISTS s3_task_resources_immutable_update BEFORE UPDATE ON s3_task_resources
 BEGIN SELECT RAISE(ABORT,'S3 task resource binding is immutable'); END;
CREATE TRIGGER IF NOT EXISTS s3_task_resources_immutable_delete BEFORE DELETE ON s3_task_resources
 BEGIN SELECT RAISE(ABORT,'S3 task resource binding is immutable'); END;
CREATE TRIGGER IF NOT EXISTS s3_diagnoses_immutable_update BEFORE UPDATE ON s3_diagnoses
 BEGIN SELECT RAISE(ABORT,'S3 diagnosis is immutable'); END;
CREATE TRIGGER IF NOT EXISTS s3_diagnoses_no_delete BEFORE DELETE ON s3_diagnoses
 BEGIN SELECT RAISE(ABORT,'S3 diagnosis is immutable'); END;
"""


def _authorized_s3_scope(
    connection: sqlite3.Connection, *, tenant_id: str, service_id: str,
    integration_id: str, principal_id: str, route: str, credential_ref: str,
) -> dict[str, object]:
    """Resolve and validate the current authorization contract for the bound route."""
    row = connection.execute(
        """SELECT i.credential_ref, i.config_version, p.status AS principal_status,
                  p.principal_version, a.accepted_credential_ref, a.policy_version,
                  r.required_scopes_json, r.scope_policy_version,
                  g.granted_scopes_json, g.grant_version
           FROM services s
           JOIN integrations i ON i.tenant_id=s.tenant_id AND i.integration_id=s.integration_id
           JOIN principals p ON p.tenant_id=i.tenant_id AND p.principal_id=i.principal_id
           JOIN auth_policies a ON a.tenant_id=s.tenant_id AND a.service_id=s.service_id
           JOIN route_scope_policies r ON r.tenant_id=s.tenant_id AND r.service_id=s.service_id AND r.route=s.route
           JOIN principal_scope_grants g ON g.tenant_id=p.tenant_id AND g.principal_id=p.principal_id
           WHERE s.tenant_id=? AND s.service_id=? AND s.integration_id=? AND s.route=?
             AND i.principal_id=?""",
        (tenant_id, service_id, integration_id, route, principal_id),
    ).fetchone()
    if row is None:
        raise ScopeDenied("S3_SCOPE_AUTHORIZATION_DENIED")
    try:
        required = json.loads(str(row["required_scopes_json"]))
        granted = json.loads(str(row["granted_scopes_json"]))
        versions = {
            key: _strict_positive_version(row[key]) for key in (
                "scope_policy_version", "grant_version", "principal_version", "policy_version", "config_version",
            )
        }
    except (json.JSONDecodeError, TypeError, ValueError) as error:
        raise ScopeDenied("S3_SCOPE_AUTHORIZATION_DENIED") from error
    if (
        not isinstance(required, list) or not isinstance(granted, list)
        or any(not isinstance(scope, str) or not scope for scope in [*required, *granted])
        or any(version < 1 for version in versions.values())
        or str(row["principal_status"]) != "ENABLED"
        or str(row["credential_ref"]) != credential_ref
        or str(row["accepted_credential_ref"]) != credential_ref
        or not set(required) <= set(granted)
    ):
        raise ScopeDenied("S3_SCOPE_AUTHORIZATION_DENIED")
    return {
        "credential_ref": str(row["credential_ref"]),
        "config_version": versions["config_version"],
        "principal_status": str(row["principal_status"]),
        "principal_version": versions["principal_version"],
        "accepted_credential_ref": str(row["accepted_credential_ref"]),
        "policy_version": versions["policy_version"],
        "scope_policy_version": versions["scope_policy_version"],
        "grant_version": versions["grant_version"],
        "required_scopes": sorted(set(required)),
        "granted_scopes": sorted(set(granted)),
    }


def get_s3_binding(connection: sqlite3.Connection, task_id: str) -> dict[str, object]:
    row = connection.execute(
        """SELECT b.*, s.route, i.credential_ref, i.config_version, p.principal_version,
                  p.status AS principal_status, a.policy_version, a.accepted_credential_ref,
                  r.order_id,r.confirmed_by AS resource_confirmed_by,
                  r.confirmed_at AS resource_confirmed_at,r.selection_digest,
                  o.contract_version
           FROM task_bindings b JOIN services s ON s.tenant_id=b.tenant_id AND s.service_id=b.service_id
           AND s.integration_id=b.integration_id JOIN integrations i ON i.tenant_id=b.tenant_id
           AND i.integration_id=b.integration_id AND i.principal_id=b.principal_id
           JOIN principals p ON p.tenant_id=b.tenant_id AND p.principal_id=b.principal_id
           JOIN auth_policies a ON a.tenant_id=b.tenant_id AND a.service_id=b.service_id
           JOIN s3_task_resources r ON r.task_id=b.task_id AND r.tenant_id=b.tenant_id
             AND r.service_id=b.service_id AND r.integration_id=b.integration_id
           JOIN s3_orders o ON o.tenant_id=r.tenant_id AND o.service_id=r.service_id
             AND o.integration_id=r.integration_id AND o.order_id=r.order_id
           WHERE b.task_id=? AND b.service_id=? AND s.route=?""", (task_id, SERVICE, ROUTE),
    ).fetchone()
    if row is None:
        raise ScopeDenied("S3_RESOURCE_OUTSIDE_TASK_BINDING")
    order = connection.execute("SELECT 1 FROM s3_orders WHERE tenant_id=? AND service_id=? AND integration_id=? AND order_id=?",
                               (row["tenant_id"], SERVICE, row["integration_id"], row["order_id"])).fetchone()
    if order is None:
        raise ScopeDenied("S3_RESOURCE_OUTSIDE_TASK_BINDING")
    binding = dict(row)
    authorization = _authorized_s3_scope(
        connection, tenant_id=str(binding["tenant_id"]), service_id=str(binding["service_id"]),
        integration_id=str(binding["integration_id"]), principal_id=str(binding["principal_id"]),
        route=str(binding["route"]), credential_ref=str(binding["credential_ref"]),
    )
    binding.update({key: authorization[key] for key in (
        "scope_policy_version", "grant_version", "required_scopes", "granted_scopes",
    )})
    return binding


def list_s3_order_resources(path: str | Path, identity) -> list[dict[str, object]]:
    """List registered S3 resources currently readable by this trusted SUPPORT actor."""
    if getattr(identity, "role", None) != "SUPPORT":
        raise ScopeDenied("S3_RESOURCE_SELECTION_REQUIRES_SUPPORT_OWNER")
    with connect(path) as connection:
        operator = connection.execute(
            "SELECT 1 FROM trusted_operators WHERE tenant_id=? AND actor_id=? AND role='SUPPORT'",
            (identity.tenant_id, identity.actor_id),
        ).fetchone()
        if operator is None:
            raise ScopeDenied("S3_RESOURCE_SELECTION_REQUIRES_SUPPORT_OWNER")
        service = connection.execute(
            """SELECT s.service_id,s.route,s.integration_id,i.principal_id,i.credential_ref
               FROM services s JOIN integrations i ON i.tenant_id=s.tenant_id AND i.integration_id=s.integration_id
               WHERE s.tenant_id=? AND s.service_id=? AND s.route=?""",
            (identity.tenant_id, SERVICE, ROUTE),
        ).fetchone()
        if service is None:
            raise ScopeDenied("S3_SCOPE_AUTHORIZATION_DENIED")
        _authorized_s3_scope(
            connection, tenant_id=identity.tenant_id, service_id=str(service["service_id"]),
            integration_id=str(service["integration_id"]), principal_id=str(service["principal_id"]),
            route=str(service["route"]), credential_ref=str(service["credential_ref"]),
        )
        rows = connection.execute(
            """SELECT o.order_id,o.status,o.version AS order_version,o.contract_version,
                      i.integration_id,i.principal_id
               FROM s3_orders o JOIN services s ON s.tenant_id=o.tenant_id AND s.service_id=o.service_id
               JOIN integrations i ON i.tenant_id=o.tenant_id AND i.integration_id=o.integration_id
                 AND i.integration_id=s.integration_id
               WHERE o.tenant_id=? AND o.service_id=? AND s.route=? ORDER BY o.order_id""",
            (identity.tenant_id, SERVICE, ROUTE),
        ).fetchall()
        result: list[dict[str, object]] = []
        for row in rows:
            result.append({
                "order_id": str(row["order_id"]), "order_status": str(row["status"]),
                "order_version": int(row["order_version"]),
                "contract_version": int(row["contract_version"]),
                "service_id": SERVICE, "integration_id": str(row["integration_id"]),
                "route": ROUTE, "principal_id": str(row["principal_id"]),
                "selection_status": "REGISTERED_AND_READ_AUTHORIZED",
            })
        return result


def bind_s3_order_in_transaction(
    connection: sqlite3.Connection, *, task_id: str, tenant_id: str, service_id: str,
    integration_id: str, order_id: str, actor_id: str, confirmed_at: str,
) -> dict[str, object]:
    """Persist the owner's confirmed directory selection with the TaskBinding transaction."""
    if service_id != SERVICE or not isinstance(order_id, str) or not re.fullmatch(r"[A-Za-z0-9._-]{1,100}", order_id):
        raise ScopeDenied("S3_ORDER_NOT_REGISTERED")
    row = connection.execute(
        """SELECT b.task_id,b.tenant_id,b.integration_id,b.principal_id,o.contract_version,
                  i.credential_ref,s.route
           FROM task_bindings b JOIN s3_orders o ON o.tenant_id=b.tenant_id AND o.service_id=b.service_id
             AND o.integration_id=b.integration_id AND o.order_id=?
           JOIN integrations i ON i.tenant_id=b.tenant_id AND i.integration_id=b.integration_id
           JOIN services s ON s.tenant_id=b.tenant_id AND s.service_id=b.service_id
             AND s.integration_id=b.integration_id AND s.route=?
           JOIN trusted_operators actor ON actor.tenant_id=b.tenant_id AND actor.actor_id=? AND actor.role='SUPPORT'
           WHERE b.task_id=? AND b.tenant_id=? AND b.service_id=? AND b.integration_id=?""",
        (order_id, ROUTE, actor_id, task_id, tenant_id, service_id, integration_id),
    ).fetchone()
    if row is None:
        raise ScopeDenied("S3_ORDER_NOT_REGISTERED_OR_AUTHORIZED")
    _authorized_s3_scope(
        connection, tenant_id=tenant_id, service_id=service_id, integration_id=integration_id,
        principal_id=str(row["principal_id"]), route=str(row["route"]),
        credential_ref=str(row["credential_ref"]),
    )
    selection = {
        "tenant_id": tenant_id, "task_id": task_id, "service_id": service_id,
        "integration_id": integration_id, "order_id": order_id, "confirmed_by": actor_id,
        "confirmed_at": confirmed_at, "contract_version": int(row["contract_version"]),
    }
    connection.execute(
        """INSERT INTO s3_task_resources
           (task_id,tenant_id,service_id,integration_id,order_id,confirmed_by,confirmed_at,selection_digest)
           VALUES(?,?,?,?,?,?,?,?)""",
        (task_id, tenant_id, service_id, integration_id, order_id, actor_id, confirmed_at, digest_json(selection)),
    )
    return selection


def _snapshot(connection, binding):
    key = (binding["tenant_id"], SERVICE, binding["order_id"])
    order = dict(connection.execute("SELECT * FROM s3_orders WHERE tenant_id=? AND service_id=? AND order_id=?", key).fetchone())
    delivery = dict(connection.execute("SELECT * FROM s3_deliveries WHERE tenant_id=? AND service_id=? AND order_id=?", key).fetchone())
    receiver = dict(connection.execute("SELECT * FROM s3_receivers WHERE tenant_id=? AND service_id=? AND order_id=?", key).fetchone())
    versions = {"order_version": order["version"], "delivery_version": delivery["version"],
                "receiver_version": receiver["version"], "contract_version": order["contract_version"],
                "config_version": binding["config_version"], "principal_version": binding["principal_version"],
                "policy_version": binding["policy_version"],
                "scope_policy_version": binding["scope_policy_version"],
                "grant_version": binding["grant_version"]}
    return order, delivery, receiver, versions


def prepare_s3_fixture(
    path: str | Path, state: str, *, tenant_id: str = "tenant-a", order_id: str = ORDER,
    contract_version: int = 1, failure_code: str = "TEMPORARY_UNAVAILABLE",
    attempt_count: int | None = None, max_attempts: int = 3, retry_state: str | None = None,
    retry_after_seconds: int = 60, queue_age_seconds: int = 60,
    processing_sla_seconds: int = 300,
) -> dict[str, object]:
    """Explicit test setup, NOT a registered tool/API. Performs a real receiver POST."""
    if state not in {"PROCESSING", "DELIVERY_FAILED", "DELIVERED_PENDING"}:
        raise ValueError("Unknown S3 test state")
    if not isinstance(order_id, str) or not re.fullmatch(r"[A-Za-z0-9._-]{1,100}", order_id):
        raise ValueError("S3 fixture order id is invalid")
    if contract_version not in {1, 2} or not 1 <= max_attempts <= 10:
        raise ValueError("S3 fixture contract/retry bounds are invalid")
    actual_attempts = attempt_count if attempt_count is not None else (1 if state == "DELIVERY_FAILED" else 0)
    if isinstance(actual_attempts, bool) or not 0 <= actual_attempts <= max_attempts:
        raise ValueError("S3 fixture attempt count is invalid")
    if not 0 <= retry_after_seconds <= 86_400 or not 0 <= queue_age_seconds <= 86_400:
        raise ValueError("S3 fixture retry/queue bounds are invalid")
    if not 30 <= processing_sla_seconds <= 86_400:
        raise ValueError("S3 processing SLA is outside the fixture range")
    actual_retry_state = retry_state or (
        "SCHEDULED" if state == "DELIVERY_FAILED" and actual_attempts < max_attempts
        else "EXHAUSTED" if state == "DELIVERY_FAILED" else "NOT_APPLICABLE"
    )
    if actual_retry_state not in {"SCHEDULED", "EXHAUSTED", "NOT_APPLICABLE"}:
        raise ValueError("S3 retry state is invalid")
    retry_at = (datetime.now(timezone.utc) + timedelta(seconds=retry_after_seconds)).isoformat().replace("+00:00", "Z") if actual_retry_state == "SCHEDULED" else None
    accepted_at = (datetime.now(timezone.utc) - timedelta(seconds=queue_age_seconds)).isoformat().replace("+00:00", "Z") if state == "DELIVERED_PENDING" else None
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
                result = {
                    "event_id": body["event_id"], "order_id": body["order_id"],
                    "request_id": body["request_id"],
                    "receiver_state": "UNAVAILABLE" if code == 503 else "QUEUED",
                    "failure_code": failure_code if code == 503 else None,
                    "attempt_count": actual_attempts, "max_attempts": max_attempts,
                    "retry_state": actual_retry_state if code == 503 else "NOT_APPLICABLE",
                    "retry_at": retry_at if code == 503 else None,
                    "accepted_at": accepted_at if code == 202 else None,
                    "processing_sla_seconds": processing_sla_seconds if code == 202 else None,
                }
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
                                  json={"event_id": event_id, "order_id": order_id, "request_id": transport_id}, timeout=5)
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
        previous = c.execute("SELECT version FROM s3_orders WHERE tenant_id=? AND service_id=? AND order_id=?", (tenant_id,SERVICE,order_id)).fetchone()
        version = int(previous[0]) + 1 if previous else 1
        c.execute("""INSERT OR REPLACE INTO s3_orders
                     (tenant_id,service_id,integration_id,order_id,status,version,contract_version)
                     VALUES(?,?,?,?,?,?,?)""",
                  (tenant_id,SERVICE,integration,order_id,"PROCESSING" if state == "PROCESSING" else "COMPLETED",version,contract_version))
        body_value = response_body or {}
        c.execute("""INSERT OR REPLACE INTO s3_deliveries
                     (tenant_id,service_id,order_id,event_id,order_version,version,status,receiver_http_status,
                      transport_request_id,response_digest,failure_code,attempt_count,max_attempts,retry_state,retry_at,transport_response_json)
                     VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                  (tenant_id,SERVICE,order_id,event_id,version,version,
                   "NOT_DUE" if status is None else "FAILED" if status == 503 else "ACKNOWLEDGED",status,
                   transport_id if status else None,digest_json(body_value) if status else None,
                   body_value.get("failure_code"),body_value.get("attempt_count",0),body_value.get("max_attempts",max_attempts),
                   body_value.get("retry_state"),body_value.get("retry_at"),canonical_json(body_value)))
        c.execute("""INSERT OR REPLACE INTO s3_receivers
                     (tenant_id,service_id,order_id,event_id,delivery_version,version,status,accepted_at,processing_sla_seconds)
                     VALUES(?,?,?,?,?,?,?,?,?)""",
                  (tenant_id,SERVICE,order_id,event_id,version,version,"QUEUED" if status == 202 else "NOT_RECEIVED",
                   body_value.get("accepted_at"),body_value.get("processing_sla_seconds")))
    return {"preparation_only": True, "agent_actions": [], "state": state, "order_version": version,
            "order_id": order_id, "contract_version": contract_version,
            "receiver_http_status": status, "transport_trace": transport_trace}


def order_http_payload(path, tenant_id, integration_id, request_id, authn_event_id, order_id: str = ORDER):
    with connect(path) as c:
        row = c.execute("SELECT * FROM s3_orders WHERE tenant_id=? AND service_id=? AND integration_id=? AND order_id=?",
                        (tenant_id,SERVICE,integration_id,order_id)).fetchone()
        if row is None:
            return None
        payload = {"order_id": order_id, "status": row["status"], "order_version": row["version"],
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
    from urllib.parse import urlencode
    order_id = str(binding["order_id"])
    response = httpx.get(
        f"{api_url}{ROUTE}?{urlencode({'order_id': order_id})}",
        headers={"X-Integration-ID": str(binding["integration_id"]), "Authorization": f"Bearer {secret}"},
        timeout=5,
    )
    body = response.json()
    with connect(path) as c:
        binding = get_s3_binding(c, task_id)
        _, _, _, after = _snapshot(c, binding)
    return _fact(binding, fact_type="s3_order", resource_id=f"{SERVICE}:{order_id}", data_source=SOURCES["s3_order"],
                 observed_versions=after, facts={"http_status": response.status_code, "body": body,
                 "versions_before": before, "versions_after": after}, original_result_ref=f"s3-http://{body.get('request_id')}")


def _table_fact(path, task_id, fact_type):
    with connect(path) as c:
        binding = get_s3_binding(c, task_id)
        order, delivery, receiver, versions = _snapshot(c, binding)
    record = delivery if fact_type == "s3_delivery" else receiver
    return _fact(binding, fact_type=fact_type, resource_id=f"{SERVICE}:{binding['order_id']}", data_source=SOURCES[fact_type],
                 observed_versions=versions, facts=record, original_result_ref=f"s3://{record['event_id']}/v{record['version']}")


def get_callback_delivery_fact(path, task_id):
    return _table_fact(path, task_id, "s3_delivery")


def get_receiver_processing_fact(path, task_id):
    return _table_fact(path, task_id, "s3_receiver")


def current_s3_evidence(connection, task_id, evidence_ids=None, *, historical=False):
    """Revalidate actual rows/HTTP observations, not just the model's typed envelope."""
    rows = connection.execute("SELECT * FROM d2_evidence WHERE task_id=? ORDER BY fetched_at,rowid", (task_id,)).fetchall()
    try:
        binding = get_s3_binding(connection, task_id)
    except ScopeDenied:
        excluded = [
            {"source_id": str(row["evidence_id"]), "reason": "S3_AUTHORIZATION_UNAVAILABLE"}
            for row in rows if evidence_ids is None or str(row["evidence_id"]) in evidence_ids
        ]
        if not excluded:
            excluded.append({"source_id": str(task_id), "reason": "S3_AUTHORIZATION_UNAVAILABLE"})
        return [], excluded
    order, delivery, receiver, current_versions = _snapshot(connection, binding)
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
            age = (_now() - datetime.fromisoformat(e["fetched_at"].replace("Z","+00:00"))).total_seconds()
            observation = connection.execute("SELECT 1 FROM d2_tool_observations WHERE task_id=? AND evidence_id=? AND tool_name=? AND status='OK'", (task_id,e["evidence_id"],FACT_TO_TOOL[fact_type])).fetchone()
            if (e["tenant_id"] != binding["tenant_id"] or e["principal_id"] != binding["principal_id"]
                or e["resource_id"] != f"{SERVICE}:{binding['order_id']}" or e["data_source"] != SOURCES[fact_type]
                or e["trust_class"] != "untrusted_tool_observation" or e["digest"] != digest_json(payload) or not observation):
                reason = "S3_FACT_ORIGIN_INVALID"
            elif not historical and (age > 300 or age < -30):
                reason = "S3_EVIDENCE_EXPIRED"
            elif (set(versions) != set(current_versions) or any(type(v) is not int or v < 1 for v in versions.values())
                  or (not historical and versions != current_versions)):
                reason = "S3_CURRENT_VERSION_MISMATCH"
            elif fact_type == "s3_order":
                body = facts.get("body", {})
                http = connection.execute(
                    """SELECT h.* FROM s3_http_observations h
                       JOIN auth_events a ON a.event_id=h.authn_event_id
                       JOIN authz_events z ON z.request_id=h.request_id AND z.authn_event_id=h.authn_event_id
                       WHERE h.request_id=? AND h.tenant_id=? AND h.service_id=?
                         AND h.integration_id=? AND h.principal_id=? AND h.route=?
                         AND a.result_code='AUTH_ACCEPTED' AND z.outcome='ALLOW'
                         AND z.reason_code='SCOPE_GRANTED' AND z.resource_binding_valid=1
                         AND z.credential_policy_version=? AND z.scope_policy_version=? AND z.grant_version=?""",
                    (body.get("request_id"),binding["tenant_id"],SERVICE,binding["integration_id"],
                     binding["principal_id"],ROUTE,current_versions["policy_version"],
                     current_versions["scope_policy_version"],current_versions["grant_version"]),
                ).fetchone()
                if (http is None or facts.get("http_status") != 200 or http["body_digest"] != digest_json(body)
                    or facts.get("versions_before") != versions or facts.get("versions_after") != versions
                    or http["route"] != ROUTE or body.get("order_id") != binding["order_id"] or body.get("order_version") != versions.get("order_version")
                    or (not historical and body.get("status") != order["status"])):
                    reason = "S3_HTTP_OBSERVATION_INVALID"
            elif not historical and facts != (delivery if fact_type == "s3_delivery" else receiver):
                reason = "S3_CURRENT_FACT_MISMATCH"
            elif fact_type in {"s3_delivery", "s3_receiver"} and (facts.get("tenant_id") != binding["tenant_id"] or facts.get("service_id") != SERVICE or facts.get("order_id") != binding["order_id"]):
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
    direction = "EVIDENCE_INSUFFICIENT"
    handoff_allowed = False
    needed = ["s3_order"]
    valid_until = None
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
                d = delivery["facts"]
                correlated = False
                try:
                    response = json.loads(str(d.get("transport_response_json", "{}")))
                    correlated = (
                        isinstance(response, dict)
                        and bool(d.get("response_digest"))
                        and digest_json(response) == str(d["response_digest"])
                        and response.get("event_id") == d.get("event_id")
                        and response.get("order_id") == d.get("order_id")
                        and response.get("request_id") == d.get("transport_request_id")
                        and bool(d.get("transport_request_id"))
                    )
                except (KeyError, TypeError, ValueError):
                    response, correlated = {}, False
                if d.get("status") == "FAILED" and d.get("receiver_http_status") == 503:
                    attempts, maximum = d.get("attempt_count"), d.get("max_attempts")
                    reason_valid = (
                        correlated and bool(d.get("failure_code"))
                        and response.get("failure_code") == d.get("failure_code")
                        and type(attempts) is int and type(maximum) is int
                        and 1 <= attempts <= maximum
                        and response.get("attempt_count") == attempts
                        and response.get("max_attempts") == maximum
                        and response.get("receiver_state") == "UNAVAILABLE"
                        and response.get("retry_state") == d.get("retry_state")
                        and response.get("retry_at") == d.get("retry_at")
                    )
                    if reason_valid and attempts < maximum and d.get("retry_state") == "SCHEDULED" and d.get("retry_at"):
                        used.extend([order, delivery])
                        outcome, direction = "CALLBACK_DELIVERY_FAILED", "WAIT_FOR_SCHEDULED_RETRY"
                    elif reason_valid and attempts == maximum and d.get("retry_state") == "EXHAUSTED" and not d.get("retry_at"):
                        used.extend([order, delivery])
                        outcome, direction, handoff_allowed = "CALLBACK_DELIVERY_FAILED", "CONTACT_CALLBACK_OPERATOR", True
                elif d.get("status") == "ACKNOWLEDGED" and d.get("receiver_http_status") == 202:
                    needed = ["s3_receiver"]
                    receiver = by_type.get("s3_receiver")
                    if receiver and receiver["facts"].get("event_id") == d.get("event_id") and receiver["facts"].get("delivery_version") == d.get("version"):
                        try:
                            response = json.loads(str(d.get("transport_response_json", "{}")))
                            accepted_text = str(receiver["facts"].get("accepted_at", ""))
                            accepted = datetime.fromisoformat(accepted_text.replace("Z", "+00:00"))
                            sla = receiver["facts"].get("processing_sla_seconds")
                            deadline = accepted.astimezone(timezone.utc) + timedelta(seconds=sla) if type(sla) is int and sla > 0 else None
                            now = _now()
                            if now.tzinfo is None:
                                now = now.replace(tzinfo=timezone.utc)
                            expired = deadline is not None and now >= deadline
                            age = max(0, int((now - accepted.astimezone(timezone.utc)).total_seconds()))
                            delivery_valid = (
                                correlated and response.get("receiver_state") == "QUEUED"
                                and response.get("accepted_at") == accepted_text
                                and response.get("processing_sla_seconds") == sla
                                and type(sla) is int and sla > 0
                                and type(age) is int and age >= 0
                            )
                        except (TypeError, ValueError, KeyError):
                            response, age, sla, delivery_valid = {}, None, None, False
                        if delivery_valid and receiver["facts"].get("status") == "QUEUED":
                            used.extend([order, delivery, receiver])
                            outcome = "RECEIVER_PROCESSING_UNCONFIRMED"
                            valid_until = deadline.isoformat().replace("+00:00", "Z")
                            if expired:
                                direction, handoff_allowed = "CONTACT_RECEIVER_OPERATOR", True
                            else:
                                direction = "WAIT_FOR_RECEIVER_PROCESSING"
                        elif delivery_valid and receiver["facts"].get("status") == "PROCESSED":
                            used.extend([order, delivery, receiver])
                            outcome, direction = "RECEIVER_PROCESSED", "NO_FURTHER_ACTION"
    if order and order["facts"]["body"].get("status") == "PROCESSING":
        outcome = "ORDER_PROCESSING"
        direction = "WAIT_FOR_ORDER_COMPLETION"
    return {"decision": "DIAGNOSED" if outcome else "NEED_MORE", "outcome": outcome,
            "reason_code": outcome or "S3_CURRENT_FACTS_REQUIRED", "required_facts": [] if outcome else needed,
            "handling_direction": direction, "handoff_allowed": handoff_allowed,
            "checked_fact_ids": [x["evidence_id"] for x in used], "valid_until": valid_until,
            "recovered": False, "side_effects": []}


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
        task_status = "WAITING_HANDOFF" if gate["decision"] == "DIAGNOSED" else "INCONCLUSIVE"
        c.execute("UPDATE task_bindings SET status=? WHERE task_id=? AND status NOT IN ('ABORTED','COMPLETED')", (task_status,task_id))
        session_id = c.execute("SELECT session_id FROM task_runs WHERE run_id=?", (run_id,)).fetchone()[0]
        _insert_outbox(c,str(b["tenant_id"]),task_id,str(session_id),"S3_DIAGNOSIS",ref,"S3_DIAGNOSIS_FROZEN",{"receipt_id":ref,"business_outcome":gate["outcome"],"handling_direction":gate.get("handling_direction"),"handoff_allowed":gate.get("handoff_allowed",False),"run_id":run_id,"recovered":False})
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
        authorization_unavailable = any(item.get("reason") == "S3_AUTHORIZATION_UNAVAILABLE" for item in excluded)
        frozen_gate = body.get("gate", {})
        current_gate = _gate_from_evidence(evidence) if not excluded else {}
        gate_matches = True
        if frozen_gate.get("decision") == "DIAGNOSED":
            gate_matches = current_gate.get("decision") == "DIAGNOSED" and all(
                current_gate.get(key) == frozen_gate.get(key)
                for key in ("outcome", "handling_direction", "handoff_allowed", "checked_fact_ids", "valid_until")
            )
        sla_expired = (
            frozen_gate.get("handling_direction") == "WAIT_FOR_RECEIVER_PROCESSING"
            and current_gate.get("handling_direction") == "CONTACT_RECEIVER_OPERATOR"
            and frozen_gate.get("valid_until") == current_gate.get("valid_until")
        )
        current = (not excluded and gate_matches and rev == row["control_revision"]
                   and digest_json(body) == row["digest"])
        invalidation_reason = (
            "S3_AUTHORIZATION_UNAVAILABLE" if authorization_unavailable
            else "S3_SLA_EXPIRED" if sla_expired
            else "S3_CURRENT_FACTS_INVALIDATED"
        )
        if authorization_unavailable:
            narrative_exclusions = [{"source_id": row["receipt_id"], "reason": invalidation_reason}]
        else:
            narrative_exclusions = _explanation_exclusions(c, task_id, body) if current else [{"source_id":row["receipt_id"],"reason":invalidation_reason}]
        narrative_current = current and not narrative_exclusions
        invalid_sources = excluded or ([{"source_id": row["receipt_id"], "reason": invalidation_reason}] if not current else [])
        result = {"receipt_id":row["receipt_id"],"outcome":row["outcome"] if current else "INCONCLUSIVE",
                "currentness":"CURRENT" if current else "INVALIDATED_BY_CURRENT_FACTS", "recovered":False,
                "handling_direction":body.get("gate",{}).get("handling_direction") if current else "EVIDENCE_INSUFFICIENT",
                "handoff_allowed":bool(body.get("gate",{}).get("handoff_allowed",False)) if current else False,
                "explanation":body.get("model_summary_untrusted","") if narrative_current else "",
                "explanation_currentness":"CURRENT" if narrative_current else "SOURCE_INVALIDATED",
                "explanation_excluded_sources":narrative_exclusions,
                "gate":body["gate"] if current else {"decision":"INCONCLUSIVE","reason_code":invalidation_reason,"excluded_sources":invalid_sources}}
        if not authorization_unavailable:
            result["body"] = body
        return result


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
