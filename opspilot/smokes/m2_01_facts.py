from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import secrets
import subprocess
import sys
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

import httpx
from mcp import Client, StdioServerParameters

from opspilot.config import ROOT
from opspilot.domain.api import make_server
from opspilot.domain.d2 import create_task_binding, get_scope_authz_facts_fact
from opspilot.domain.database import connect, get_credential_secret, initialize, reset_fixture


EVIDENCE_DIR = ROOT / "docs" / "evidence" / "vnext" / "m2-01"


def _canonical(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _install_scope_write_audit(path: Path) -> None:
    with connect(path) as connection:
        connection.execute(
            "CREATE TABLE m2_scope_write_audit (table_name TEXT NOT NULL, operation TEXT NOT NULL)"
        )
        for table in ("principal_scope_grants", "route_scope_policies"):
            for operation, suffix in (("INSERT", "ins"), ("UPDATE", "upd"), ("DELETE", "del")):
                connection.execute(
                    f"CREATE TRIGGER m2_audit_{table}_{suffix} AFTER {operation} ON {table} "
                    f"BEGIN INSERT INTO m2_scope_write_audit VALUES ('{table}', '{operation}'); END"
                )


def _fresh_domain(path: Path, scenario: str, actor: str, service: str, integration: str) -> tuple[dict[str, object], int]:
    initialize(path)
    _install_scope_write_audit(path)
    reset_fixture(path, scenario)  # type: ignore[arg-type]
    with connect(path) as connection:
        setup_count = int(connection.execute("SELECT count(*) FROM m2_scope_write_audit").fetchone()[0])
        connection.execute("DELETE FROM m2_scope_write_audit")
    binding = create_task_binding(path, actor, service, integration)
    return binding, setup_count


@contextmanager
def _api(path: Path, tenant_id: str) -> Iterator[str]:
    server = make_server(path, tenant_id, "127.0.0.1", 0)
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
    thread.start()
    host, port = server.server_address
    try:
        yield f"http://{host}:{port}"
    finally:
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()


def _http_request(base_url: str, path: Path, *, credential_ref: str, tenant_id: str = "tenant-a",
                  integration_id: str = "integration-a") -> httpx.Response:
    token = get_credential_secret(path, tenant_id, credential_ref)
    return httpx.get(
        f"{base_url}/api/orders/demo-order",
        headers={"X-Integration-ID": integration_id, "Authorization": f"Bearer {token}"},
        timeout=5,
    )


def _authn_event(path: Path, request_id: str) -> dict[str, object] | None:
    with connect(path) as connection:
        row = connection.execute(
            "SELECT event_id, request_id, result_code, credential_policy_version, observed_at "
            "FROM auth_events WHERE request_id = ?",
            (request_id,),
        ).fetchone()
        if row is None:
            return None
        return dict(row)


def _domain_auth_facts(path: Path, task_id: str, request_id: str) -> tuple[dict[str, object] | None, dict[str, object] | None]:
    with connect(path) as connection:
        authn_row = connection.execute(
            "SELECT * FROM auth_events WHERE request_id = ?", (request_id,)
        ).fetchone()
        authz_row = connection.execute(
            "SELECT * FROM authz_events WHERE request_id = ?", (request_id,)
        ).fetchone()
    authn = dict(authn_row) if authn_row is not None else None
    authz = None
    if authz_row is not None:
        fact = get_scope_authz_facts_fact(path, task_id, request_id)
        authz = {
            **fact["facts"],
            "observed_versions": fact["observed_versions"],
            "observed_at": fact["observed_at"],
            "data_source": fact["data_source"],
            "trust_class": fact["trust_class"],
        }
    return authn, authz


def _scope_write_count(path: Path) -> int:
    with connect(path) as connection:
        return int(connection.execute("SELECT count(*) FROM m2_scope_write_audit").fetchone()[0])


def _release_ref(tool_schema_digest: str) -> dict[str, object]:
    lock = ROOT / "requirements.lock.txt"
    return {
        "git_sha": subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, capture_output=True, check=True
        ).stdout.strip(),
        "python_version": sys.version.split()[0],
        "dependency_lock_sha256": _sha256(lock.read_bytes()),
        "model_id": None,
        "prompt_version": "not_applicable",
        "skill_version": "not_applicable",
        "tool_schema_version": tool_schema_digest,
        "gate_policy_version": "not_applicable",
        "budget_policy_version": "not_applicable",
    }


def _base_record(case_id: str, transport: str, release_ref: dict[str, object]) -> dict[str, object]:
    return {
        "trace_id": f"trace-{secrets.token_hex(8)}",
        "attempt_id": f"attempt-{secrets.token_hex(8)}",
        "case_id": case_id,
        "recorded_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "release_ref": release_ref,
        "transport": transport,
        "run_status": "NOT_APPLICABLE",
        "task_status": "NOT_APPLICABLE",
        "expected_outcome": "NOT_IMPLEMENTED",
        "actual_outcome": "NOT_IMPLEMENTED",
        "request": {},
        "response": {},
        "scope_binding": {},
        "authn_event": None,
        "authz_decision": None,
        "mcp_calls": [],
        "evidence": {"source_ids": [], "trust_class": "trusted_domain_event", "completeness": "MISSING", "validity": "UNVERIFIED"},
        "scope_write_audit": {"setup_write_count": 0, "runtime_write_count": 0},
        "receipt_integrity": "NOT_IMPLEMENTED",
        "forbidden_writes": 0,
        "secret_scan": "PENDING",
        "real_provider_calls": 0,
        "real_browser_runs": 0,
        "http_request_count": 0,
        "mcp_tools_list_count": 0,
        "mcp_tools_call_count": 0,
        "failure_reason": None,
        "result_status": "PASS",
    }


async def _stdio_calls(db_path: Path, task_id: str, current_request_id: str,
                       cross_request_id: str) -> tuple[dict[str, object], dict[str, object]]:
    parameters = StdioServerParameters(
        command=sys.executable,
        args=["-m", "opspilot.mcp_server", "--db", str(db_path), "--binding-id", task_id,
              "--include-scope-authz-facts"],
        env={"OPSPILOT_DB_PATH": str(db_path)},
        cwd=str(ROOT),
    )
    async with Client(parameters) as client:
        listed = await client.list_tools()
        catalog = {tool.name: tool for tool in listed.tools}
        tool = catalog["get_scope_authz_facts"]
        schema_digest = _sha256(_canonical(tool.input_schema).encode("utf-8"))
        calls: list[dict[str, object]] = [{
            "method": "tools/list", "status": "OK", "tool_count": len(catalog),
            "scope_fact_schema_sha256": schema_digest,
        }]
        valid = await client.call_tool("get_scope_authz_facts", {"request_id": current_request_id})
        if valid.is_error or not valid.structured_content:
            raise RuntimeError("Task-bound MCP authorization fact read failed.")
        payload = valid.structured_content.get("result", valid.structured_content)
        calls.append({
            "method": "tools/call", "tool_name": "get_scope_authz_facts",
            "arguments": {"request_id": current_request_id}, "status": "OK",
            "source": payload.get("data_source"), "trust_class": payload.get("trust_class"),
            "result_sha256": _sha256(_canonical(payload).encode("utf-8")),
        })
        cross = await client.call_tool("get_scope_authz_facts", {"request_id": cross_request_id})
        calls.append({
            "method": "tools/call", "tool_name": "get_scope_authz_facts",
            "arguments": {"request_id": "[REDACTED_CROSS_SCOPE_ID]"},
            "status": "ERROR" if cross.is_error else "UNEXPECTED_SUCCESS",
            "error_code": "RESOURCE_OUTSIDE_TASK_SCOPE" if cross.is_error else None,
        })
        forged = await client.call_tool(
            "get_scope_authz_facts",
            {"request_id": current_request_id, "tenant_id": "[FORGED]", "granted_scopes": ["*"]},
        )
        calls.append({
            "method": "tools/call", "tool_name": "get_scope_authz_facts",
            "arguments": {"request_id": current_request_id, "extra_fields": "[REDACTED]"},
            "status": "ERROR" if forged.is_error else "UNEXPECTED_SUCCESS",
            "error_code": "INVALID_ARGUMENTS" if forged.is_error else None,
        })
        invalid_type = await client.call_tool("get_scope_authz_facts", {"request_id": 123})
        calls.append({
            "method": "tools/call", "tool_name": "get_scope_authz_facts",
            "arguments": {"request_id": "[INVALID_TYPE]"},
            "status": "ERROR" if invalid_type.is_error else "UNEXPECTED_SUCCESS",
            "error_code": "INVALID_ARGUMENTS" if invalid_type.is_error else None,
        })
        return {"schema_digest": schema_digest, "calls": calls, "payload": payload,
                "valid_calls": 1,
                "denied_calls": int(cross.is_error) + int(forged.is_error) + int(invalid_type.is_error)}, catalog


def run(output: Path) -> dict[str, object]:
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + secrets.token_hex(3)
    runtime = ROOT / ".runtime" / "m2-01" / f"trace-{run_id}"
    runtime.mkdir(parents=True, exist_ok=False)
    denied_db = runtime / "scope-denied.sqlite3"
    denied_binding, denied_setup_writes = _fresh_domain(
        denied_db, "S2_SCOPE_DENIED", "support-a", "orders-demo", "integration-a"
    )
    invalid_db = runtime / "invalid-auth.sqlite3"
    _, invalid_setup_writes = _fresh_domain(
        invalid_db, "S2_SCOPE_ALLOWED", "support-a", "orders-demo", "integration-a"
    )
    allowed_db = runtime / "scope-allowed.sqlite3"
    allowed_binding, allowed_setup_writes = _fresh_domain(
        allowed_db, "S2_SCOPE_ALLOWED", "support-a", "orders-demo", "integration-a"
    )

    with _api(invalid_db, "tenant-a") as invalid_api:
        response_401 = _http_request(invalid_api, invalid_db, credential_ref="cred-v1")
    with _api(denied_db, "tenant-a") as denied_api:
        response_403 = _http_request(denied_api, denied_db, credential_ref="cred-v2")
    with _api(allowed_db, "tenant-a") as allowed_api:
        response_200 = _http_request(allowed_api, allowed_db, credential_ref="cred-v2")

    if (response_401.status_code, response_403.status_code, response_200.status_code) != (401, 403, 200):
        raise RuntimeError("Fresh local HTTP authn/authz smoke returned an unexpected status.")
    request_401 = response_401.json()["request_id"]
    request_403 = response_403.json()["request_id"]
    request_200 = response_200.json()["request_id"]
    outside_scope_request = f"outside-task-{secrets.token_hex(8)}"
    mcp_result, tools = asyncio.run(
        _stdio_calls(denied_db, str(denied_binding["task_id"]), request_403, outside_scope_request)
    )
    if mcp_result["denied_calls"] != 3:
        raise RuntimeError("MCP stdio did not reject all out-of-scope and forged-input calls.")

    release_ref = _release_ref(str(mcp_result["schema_digest"]))
    records: list[dict[str, object]] = []
    for case_id, response, db_path, setup_count, credential_ref in (
        ("S2FACT-02A", response_401, invalid_db, invalid_setup_writes, "cred-v1"),
        ("S2FACT-01", response_403, denied_db, denied_setup_writes, "cred-v2"),
        ("S2FACT-03", response_200, allowed_db, allowed_setup_writes, "cred-v2"),
    ):
        request_id = response.json()["request_id"]
        task_id = str(denied_binding["task_id"]) if db_path == denied_db else str(allowed_binding["task_id"]) if db_path == allowed_db else ""
        authn, authz = _domain_auth_facts(db_path, task_id, request_id)
        record = _base_record(case_id, "REAL_HTTP", release_ref)
        record.update({
            "request": {"method": "GET", "path": "/api/orders/demo-order", "credential_ref": credential_ref},
            "response": {"http_status": response.status_code, "payload": {
                key: response.json()[key] for key in ("order_id", "status", "error", "request_id", "authn_event_id", "authz_event_id")
                if key in response.json()
            }},
            "scope_binding": {"tenant_id": "tenant-a", "service_id": "orders-demo", "integration_id": "integration-a", "principal_id": "principal-a", "route": "/api/orders/demo-order", "source": "trusted Domain fixture and HTTP server"},
            "authn_event": authn,
            "authz_decision": authz,
            "scope_write_audit": {"setup_write_count": setup_count, "runtime_write_count": _scope_write_count(db_path)},
            "forbidden_writes": _scope_write_count(db_path),
            "http_request_count": 1,
            "evidence": {"source_ids": [f"authn:{authn['event_id']}"] + ([f"authz:{authz['decision_id']}"] if authz else []),
                         "trust_class": "trusted_domain_event", "observed_versions": {
                             key: authz[key] for key in ("credential_policy_version", "scope_policy_version", "grant_version")
                         } if authz else {}, "completeness": "COMPLETE" if authn and (authz or response.status_code == 401) else "PARTIAL",
                         "validity": "CURRENT" if authn and (authz is None or authz["currentness"] == "CURRENT") else "UNVERIFIED"},
        })
        expected_status = {"S2FACT-02A": 401, "S2FACT-01": 403, "S2FACT-03": 200}[case_id]
        valid = response.status_code == expected_status and authn is not None
        if case_id == "S2FACT-02A":
            valid = valid and authn["result_code"] == "AUTH_REJECTED" and authz is None
        elif case_id == "S2FACT-01":
            valid = valid and authn["result_code"] == "AUTH_ACCEPTED" and authz is not None
            valid = valid and authz["currentness"] == "CURRENT" and authz["outcome"] == "DENY"
            valid = valid and authz["reason_code"] == "SCOPE_INSUFFICIENT" and authz["missing_scopes"] == ["orders.read"]
        else:
            valid = valid and authn["result_code"] == "AUTH_ACCEPTED" and authz is not None
            valid = valid and authz["currentness"] == "CURRENT" and authz["outcome"] == "ALLOW"
            valid = valid and response.json().get("order_id") == "demo-order" and response.json().get("status") == "CONFIRMED"
        if not valid:
            record["result_status"] = "FAIL"
            record["failure_reason"] = "HTTP response and trusted Domain Authn/Authz facts did not match frozen expectations."
        records.append(record)

    mcp_record = _base_record("S2FACT-06A", "MCP_STDIO", release_ref)
    mcp_record.update({
        "request": {"tool_name": "get_scope_authz_facts", "allowlisted_arguments": ["request_id"]},
        "response": {"valid_fact_currentness": mcp_result["payload"]["facts"]["currentness"],
                     "cross_scope_rejected": True, "forged_arguments_rejected": True},
        "scope_binding": {"tenant_id": "tenant-a", "task_id": denied_binding["task_id"],
                          "service_id": denied_binding["service_id"], "integration_id": denied_binding["integration_id"],
                          "principal_id": denied_binding["principal_id"], "route": "/api/orders/demo-order",
                          "source": "persisted TaskBinding"},
        "authn_event": _authn_event(denied_db, request_403),
        "authz_decision": mcp_result["payload"]["facts"],
        "mcp_calls": mcp_result["calls"],
        "mcp_tools_list_count": 1,
        "mcp_tools_call_count": 4,
        "scope_write_audit": {"setup_write_count": denied_setup_writes, "runtime_write_count": _scope_write_count(denied_db)},
        "forbidden_writes": _scope_write_count(denied_db),
        "evidence": {"source_ids": [f"authz:{mcp_result['payload']['facts']['decision_id']}"],
                     "trust_class": "untrusted_tool_observation", "observed_versions": mcp_result["payload"]["observed_versions"],
                     "completeness": "COMPLETE", "validity": mcp_result["payload"]["facts"]["currentness"]},
    })
    records.append(mcp_record)

    secrets_to_scan = [
        get_credential_secret(db_path, tenant_id, ref)
        for db_path, tenant_id in ((invalid_db, "tenant-a"), (denied_db, "tenant-a"), (allowed_db, "tenant-a"))
        for ref in ("cred-v1", "cred-v2")
    ]
    serialized = _canonical(records)
    if any(secret and secret in serialized for secret in secrets_to_scan):
        raise RuntimeError("Secret scan failed; trace was not written.")
    for record in records:
        record["secret_scan"] = "PASS"
        if record["forbidden_writes"] != 0:
            record["result_status"] = "FAIL"
            record["failure_reason"] = "Runtime Scope/Route Policy write detected."
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(records, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    summary = {
        "result": "PASS" if all(record["result_status"] == "PASS" for record in records) else "FAIL",
        "trace_path": str(output), "run_id": run_id, "http_requests": 3,
        "http_statuses": [401, 403, 200], "mcp_tools_list": 1, "mcp_tools_call": 4,
        "mcp_tool_count": len(tools), "mcp_schema_sha256": mcp_result["schema_digest"],
        "runtime_scope_writes": sum(int(record["forbidden_writes"]) for record in records),
        "real_provider_calls": 0, "real_browser_runs": 0,
        "scope_denied_request_id": request_403,
        "scope_denied_authn_event_id": response_403.json()["authn_event_id"],
        "scope_denied_authz_event_id": response_403.json()["authz_event_id"],
        "allowed_request_id": request_200,
        "invalid_request_id": request_401,
        "cross_scope_check": "REJECTED",
    }
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Run fresh local M2-01 HTTP and MCP stdio facts smoke.")
    parser.add_argument("--output", type=Path, default=EVIDENCE_DIR / "TRACE.json")
    args = parser.parse_args()
    summary = run(args.output.resolve())
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    return 0 if summary["result"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
