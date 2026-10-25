"""Bound-order callback transport observations, not a sender or Agent write API."""
from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import httpx

from opspilot.domain.database import connect
from opspilot.domain.d2 import ScopeDenied, canonical_json, digest_json, utc_now, _fact


SCHEMA = """
CREATE TABLE IF NOT EXISTS s3_transport_attempts (
 attempt_id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, service_id TEXT NOT NULL,
 integration_id TEXT NOT NULL, order_id TEXT NOT NULL, event_id TEXT NOT NULL,
 event_created_at TEXT NOT NULL, attempt_no INTEGER NOT NULL CHECK(attempt_no>0),
 transport_request_id TEXT NOT NULL, order_version INTEGER NOT NULL,
 contract_version INTEGER NOT NULL, target_ref TEXT NOT NULL,
 request_json TEXT NOT NULL, request_digest TEXT NOT NULL,
 started_at TEXT NOT NULL, observed_at TEXT NOT NULL, persisted_at TEXT NOT NULL,
 result_kind TEXT NOT NULL CHECK(result_kind IN ('HTTP_RESPONSE','OUTCOME_UNKNOWN')),
 http_status INTEGER, response_json TEXT, response_digest TEXT,
 source_ref TEXT NOT NULL, content_digest TEXT NOT NULL,
 UNIQUE(tenant_id,service_id,transport_request_id),
 UNIQUE(tenant_id,service_id,order_id,event_id,attempt_no),
 FOREIGN KEY(tenant_id,service_id,order_id) REFERENCES s3_orders(tenant_id,service_id,order_id));
CREATE TRIGGER IF NOT EXISTS s3_transport_immutable_update BEFORE UPDATE ON s3_transport_attempts
 BEGIN SELECT RAISE(ABORT,'Transport observation is immutable'); END;
CREATE TRIGGER IF NOT EXISTS s3_transport_immutable_delete BEFORE DELETE ON s3_transport_attempts
 BEGIN SELECT RAISE(ABORT,'Transport observation is immutable'); END;
"""


def history_snapshot(connection, binding, event_id=None):
    """Current authorized read of immutable known observations; never claim complete audit."""
    from opspilot.domain.s3 import SERVICE

    key = (binding["tenant_id"], SERVICE, binding["order_id"])
    count = int(connection.execute("SELECT COUNT(*) FROM s3_transport_attempts WHERE tenant_id=? AND service_id=? AND order_id=?",key).fetchone()[0])
    current = connection.execute(
        "SELECT event_id FROM s3_deliveries WHERE tenant_id=? AND service_id=? AND order_id=?", key,
    ).fetchone()
    known = connection.execute("SELECT 1 FROM s3_transport_attempts WHERE tenant_id=? AND service_id=? AND order_id=? AND event_id=? LIMIT 1",(*key,event_id)).fetchone() if isinstance(event_id,str) else None
    if event_id is not None and (not isinstance(event_id, str) or len(event_id)>128 or (not known and (not current or str(current[0])!=event_id))):
        raise ScopeDenied("S3_EVENT_NOT_AVAILABLE_WITHIN_BOUND_ORDER")
    query="SELECT * FROM s3_transport_attempts WHERE tenant_id=? AND service_id=? AND order_id=?"
    params=key
    if event_id is not None:
        query += " AND event_id=?"
        params=(*key,event_id)
    selected=[dict(row) for row in connection.execute(query+" ORDER BY rowid DESC LIMIT 13",params)]
    # Both the data query and the prompt are bounded; a caller can refine by Event.
    truncated = len(selected) > 12
    selected = list(reversed(selected[:12]))
    for row in selected:
        if row["integration_id"] != binding["integration_id"]:
            raise ScopeDenied("S3_TRANSPORT_CORRELATION_INVALID")
        payload = {key: value for key, value in row.items() if key != "content_digest"}
        if digest_json(payload) != row["content_digest"]:
            raise ScopeDenied("S3_TRANSPORT_SOURCE_DIGEST_INVALID")
        request = json.loads(row["request_json"])
        response = json.loads(row["response_json"]) if row["response_json"] else None
        if digest_json(request) != row["request_digest"] or (response is not None and digest_json(response) != row["response_digest"]):
            raise ScopeDenied("S3_TRANSPORT_SOURCE_DIGEST_INVALID")
        if (request.get("event_id") != row["event_id"] or request.get("request_id") != row["transport_request_id"]
            or request.get("order_id") != binding["order_id"] or request.get("order_version") != row["order_version"]
            or request.get("contract_version") != row["contract_version"]):
            raise ScopeDenied("S3_TRANSPORT_CORRELATION_INVALID")
        if response is not None and any(response.get(k) != request[k] for k in ("event_id", "request_id", "order_id")):
            raise ScopeDenied("S3_TRANSPORT_CORRELATION_INVALID")
    return {
        "order_id": str(binding["order_id"]), "requested_event_id": event_id,
        "attempts": selected, "coverage": "RECORDED_OBSERVATIONS_ONLY",
        "truncated": truncated,
        "unknowns": ["No record does not prove no send; the send-to-persist crash window is not a complete audit."],
        "processing_authority": "Transport responses describe that attempt, not the target Event current processing state.",
    }, count + 1


def get_transport_history_fact(path, task_id, event_id=None):
    from opspilot.domain.s3 import get_s3_binding, _snapshot, SERVICE

    with connect(path) as connection:
        binding = get_s3_binding(connection, task_id)
        facts, revision = history_snapshot(connection, binding, event_id)
        _, _, _, versions = _snapshot(connection, binding)
    return _fact(
        binding, fact_type="s3_transport_history", resource_id=f"{SERVICE}:{binding['order_id']}",
        data_source="sqlite:s3_transport_attempts", observed_versions={**versions, "transport_history_version": revision},
        facts=facts, original_result_ref=f"s3-history://{binding['order_id']}/{revision}",
    )


def _append(connection, payload):
    """Trusted fixture sender appends the observed HTTP result; not registered in MCP/Web."""
    payload = {**payload, "content_digest": digest_json(payload)}
    columns = list(payload)
    existing = connection.execute(
        "SELECT * FROM s3_transport_attempts WHERE tenant_id=? AND service_id=? AND transport_request_id=?",
        (payload["tenant_id"], payload["service_id"], payload["transport_request_id"]),
    ).fetchone()
    if existing:
        if dict(existing) != payload:
            raise ValueError("TRANSPORT_REQUEST_ID_CONFLICT")
        return dict(existing)
    connection.execute(
        f"INSERT INTO s3_transport_attempts ({','.join(columns)}) VALUES ({','.join('?' for _ in columns)})",
        tuple(payload[key] for key in columns),
    )
    return payload


def prepare_transport_history_fixture(
    path, *, order_id, attempts, receiver_status="QUEUED", tenant_id="tenant-a", contract_version=2,
    history_mode="observed",
):
    """Isolated TEST PREPARATION. Each scripted attempt really POSTs to a local receiver.

    event_created_at is a business timestamp; actual HTTP times are never backdated.
    snapshot_only/missing_first deliberately model absent capture, not a fake complete history.
    """
    from opspilot.domain.s3 import prepare_s3_fixture, SERVICE

    if receiver_status not in {"QUEUED", "PROCESSED", "NOT_RECEIVED"} or history_mode not in {"observed", "snapshot_only", "missing_first"}:
        raise ValueError("Invalid test preparation state")
    if not 1 <= len(attempts) <= 10:
        raise ValueError("Fixture attempts must be bounded")
    prepare_s3_fixture(path, "PROCESSING", tenant_id=tenant_id, order_id=order_id, contract_version=contract_version)
    suffix = "a" if tenant_id == "tenant-a" else "b"
    integration = f"async-integration-{suffix}"
    trace, event_times, ordinals, event_versions = [], {}, {}, {}
    active = {}

    class Receiver(BaseHTTPRequestHandler):
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            code = active.get("http_status")
            if code is None:
                self.close_connection = True  # actual send, no definite response
                self.connection.shutdown(2)
                return
            response = {**body, "receiver_state": "QUEUED" if code == 202 else "UNAVAILABLE",
                        "failure_code": None if code == 202 else "TEMPORARY_UNAVAILABLE",
                        "attempt_count": ordinals[body["event_id"]], "max_attempts": 10,
                        "retry_state": "NOT_APPLICABLE" if code == 202 else "SCHEDULED",
                        "retry_at": None if code == 202 else (datetime.now(timezone.utc) + timedelta(seconds=60)).isoformat()}
            if code == 202:
                response.update(accepted_at=utc_now(),processing_sla_seconds=300)
            raw = canonical_json(response).encode()
            self.send_response(int(code))
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)
        def log_message(self, *_args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Receiver)
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
    thread.start()
    try:
        for index, item in enumerate(attempts):
            event = str(item["event_id"])
            with connect(path) as connection:
                known=connection.execute("SELECT * FROM s3_transport_attempts WHERE tenant_id=? AND service_id=? AND order_id=? AND event_id=? ORDER BY attempt_no DESC LIMIT 1",(tenant_id,SERVICE,order_id,event)).fetchone()
                current_version=int(connection.execute("SELECT version FROM s3_orders WHERE tenant_id=? AND service_id=? AND order_id=?",(tenant_id,SERVICE,order_id)).fetchone()[0])
            ordinals.setdefault(event, int(known["attempt_no"]) if known else 0)
            event_versions.setdefault(event,(int(known["order_version"]),int(known["contract_version"])) if known else (current_version,contract_version))
            ordinals[event] = ordinals.get(event, 0) + 1
            event_times.setdefault(event, str(known["event_created_at"]) if known else (datetime.now(timezone.utc) + timedelta(seconds=int(item.get("offset_seconds", 0)))).isoformat())
            request = {"event_id": event, "order_id": order_id, "request_id": str(item.get("transport_request_id") or f"transport-{uuid.uuid4()}"),
                       "order_version":event_versions[event][0],"contract_version":event_versions[event][1]}
            started = utc_now()
            active.update(item)
            response, code, error, raw_http_status = None, None, None, None
            try:
                received = httpx.post(f"http://127.0.0.1:{server.server_port}/callback", json=request, timeout=2)
                raw_http_status = received.status_code
                code, response = received.status_code, received.json()
            except (httpx.HTTPError, ValueError) as caught:
                error = type(caught).__name__
            observed = utc_now()
            record = {
                "attempt_id": f"transport-observation-{uuid.uuid4()}", "tenant_id": tenant_id,
                "service_id": SERVICE, "integration_id": integration, "order_id": order_id,
                "event_id": event, "event_created_at": event_times[event], "attempt_no": ordinals[event],
                "transport_request_id": request["request_id"], "order_version": request["order_version"],
                "contract_version": request["contract_version"], "target_ref": "registered-local-test-receiver",
                "request_json": canonical_json(request), "request_digest": digest_json(request),
                "started_at": started, "observed_at": observed, "persisted_at": utc_now(),
                "result_kind": "HTTP_RESPONSE" if response is not None else "OUTCOME_UNKNOWN",
                "http_status": code, "response_json": canonical_json(response) if response is not None else None,
                "response_digest": digest_json(response) if response is not None else None,
                "source_ref": f"trusted-test-http://{request['request_id']}",
            }
            captured = history_mode != "snapshot_only" and not (history_mode == "missing_first" and index == 0)
            with connect(path) as connection:
                connection.execute("BEGIN IMMEDIATE")
                if captured:
                    record = _append(connection, record)
                if response is not None:
                    accepted = code in {200, 202}
                    projection_response = {**(response or {}), "failure_code": None if accepted else "TEMPORARY_UNAVAILABLE"}
                    connection.execute("UPDATE s3_orders SET status='COMPLETED' WHERE tenant_id=? AND service_id=? AND order_id=?", (tenant_id, SERVICE, order_id))
                    connection.execute(
                        """UPDATE s3_deliveries SET event_id=?,order_version=?,version=version+1,status=?,receiver_http_status=?,transport_request_id=?,
                           response_digest=?,failure_code=?,attempt_count=?,max_attempts=10,retry_state=?,retry_at=?,transport_response_json=?
                           WHERE tenant_id=? AND service_id=? AND order_id=?""",
                        (event, request["order_version"], "ACKNOWLEDGED" if accepted else "FAILED", code, request["request_id"], digest_json(projection_response),
                         projection_response["failure_code"], ordinals[event], "NOT_APPLICABLE" if accepted else "SCHEDULED",projection_response.get("retry_at"),
                         canonical_json(projection_response), tenant_id, SERVICE, order_id),
                    )
                    delivery_version = connection.execute("SELECT version FROM s3_deliveries WHERE tenant_id=? AND service_id=? AND order_id=?", (tenant_id, SERVICE, order_id)).fetchone()[0]
                    connection.execute(
                        """UPDATE s3_receivers SET event_id=?,delivery_version=?,version=version+1,status=?,accepted_at=?,processing_sla_seconds=300
                           WHERE tenant_id=? AND service_id=? AND order_id=?""",
                        (event, delivery_version, receiver_status if accepted else "NOT_RECEIVED", response.get("accepted_at") if accepted else None, tenant_id, SERVICE, order_id),
                    )
            trace.append({"preparation_only": True, "request": request, "http_status": code, "response": response,
                          "raw_http_status":raw_http_status,"started_at": started, "observed_at": observed, "error": error, "persisted": captured,
                          "prepared_receiver_projection_after_http":receiver_status if code==202 else "NOT_RECEIVED",
                          "record": record if captured else None})
    finally:
        server.shutdown()
        thread.join(timeout=3)
        server.server_close()
    return {"preparation_only": True, "agent_actions": [], "transport_trace": trace,
            "order_id": order_id, "history_mode": history_mode}
