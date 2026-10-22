from __future__ import annotations

import json
import os
import secrets
import shutil
import socket
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from opspilot.config import MODEL_API_KEY, MODEL_NAME, ROOT, load_local_environment
from opspilot.domain.database import connect, reset_fixture
from opspilot.smokes.m1_03 import _kill, _server_environment


EVIDENCE = ROOT / "docs" / "evidence" / "vnext" / "m4-01"
SCRIPT = ROOT / "frontend" / "e2e" / "m4-01-dialogue-updates.mjs"
SENSITIVE_NAME = ("password", "secret", "api_key", "authorization", "cookie")


def _scrub(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: "[REDACTED]" if any(term in key.lower() for term in SENSITIVE_NAME) else _scrub(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_scrub(item) for item in value]
    return value


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_scrub(value), ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _start(command: list[str], cwd: Path, env: dict[str, str], log_path: Path) -> subprocess.Popen:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    handle = log_path.open("a", encoding="utf-8", newline="\n")
    process = subprocess.Popen(command, cwd=cwd, env=env, stdout=handle, stderr=subprocess.STDOUT)
    setattr(process, "_opspilot_log_handle", handle)
    return process


def _wait_http(process: subprocess.Popen, url: str, log_path: Path, timeout: int = 45) -> None:
    deadline = time.monotonic() + timeout
    last_error = "not attempted"
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"Service exited with {process.returncode}; inspect {log_path}.")
        try:
            response = httpx.get(url, timeout=1.0)
            if response.status_code == 200:
                return
            last_error = f"HTTP {response.status_code}"
        except httpx.HTTPError as error:
            last_error = type(error).__name__
        time.sleep(0.25)
    raise TimeoutError(f"Local service did not become ready: {last_error}; inspect {log_path}.")


def _start_api(port: int, env: dict[str, str], log_path: Path) -> subprocess.Popen:
    process = _start(
        [sys.executable, "-X", "utf8", "-u", "-m", "opspilot.web.server", "--host", "127.0.0.1", "--port", str(port)],
        ROOT, env, log_path,
    )
    _wait_http(process, f"http://127.0.0.1:{port}/api/health", log_path)
    return process


def _start_vite(port: int, api_origin: str, env: dict[str, str], log_path: Path) -> subprocess.Popen:
    node = shutil.which("node")
    if not node:
        raise RuntimeError("Node.js is required for the real Edge browser run.")
    npm_cli = Path(node).resolve().parent / "node_modules" / "npm" / "bin" / "npm-cli.js"
    vite_env = env.copy()
    vite_env["OPSPILOT_API_ORIGIN"] = api_origin
    process = _start(
        [node, str(npm_cli), "run", "dev", "--", "--host", "127.0.0.1", "--port", str(port), "--strictPort"],
        ROOT / "frontend", vite_env, log_path,
    )
    _wait_http(process, f"http://127.0.0.1:{port}/", log_path)
    return process


def _browser_run(env: dict[str, str], log_path: Path, passwords: dict[str, str]) -> dict[str, Any]:
    node = shutil.which("node")
    if not node:
        raise RuntimeError("Node.js is required for the real Edge browser run.")
    completed = subprocess.run(
        [node, str(SCRIPT)], cwd=ROOT / "frontend", env=env,
        capture_output=True, text=True, encoding="utf-8", timeout=900,
    )
    stdout, stderr = completed.stdout, completed.stderr
    for value in passwords.values():
        stdout = stdout.replace(value, "[REDACTED_TEST_PASSWORD]")
        stderr = stderr.replace(value, "[REDACTED_TEST_PASSWORD]")
    attempt_path = log_path.with_name(f"{log_path.stem}.attempt-01{log_path.suffix}")
    attempt_path.write_text(
        f"exit_code={completed.returncode}\nstdout:\n{stdout}\nstderr:\n{stderr}", encoding="utf-8",
    )
    if completed.returncode != 0:
        raise RuntimeError(f"Microsoft Edge journey failed with exit code {completed.returncode}; inspect {attempt_path}.")
    records = [line for line in completed.stdout.splitlines() if line.strip()]
    if not records:
        raise RuntimeError(f"Microsoft Edge journey returned no result record; inspect {attempt_path}.")
    result = json.loads(records[-1])
    _write_json(log_path.with_suffix(".json"), result)
    return result


def _rows(db: Path, query: str, parameters: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    with connect(db) as connection:
        return [dict(row) for row in connection.execute(query, parameters).fetchall()]


def _one(db: Path, query: str, parameters: tuple[Any, ...] = ()) -> dict[str, Any] | None:
    rows = _rows(db, query, parameters)
    return rows[0] if rows else None


def _current_versions(db: Path) -> dict[str, Any]:
    return {
        "integration": _one(db, "SELECT tenant_id, integration_id, principal_id, credential_ref, config_version FROM integrations WHERE tenant_id = 'tenant-a' AND integration_id = 'integration-a'"),
        "principal": _one(db, "SELECT tenant_id, principal_id, status, principal_version FROM principals WHERE tenant_id = 'tenant-a' AND principal_id = 'principal-a'"),
        "auth_policy": _one(db, "SELECT tenant_id, service_id, accepted_credential_ref, policy_version FROM auth_policies WHERE tenant_id = 'tenant-a' AND service_id = 'orders-demo'"),
        "grant": _one(db, "SELECT tenant_id, principal_id, granted_scopes_json, grant_version FROM principal_scope_grants WHERE tenant_id = 'tenant-a' AND principal_id = 'principal-a'"),
        "route_policy": _one(db, "SELECT tenant_id, service_id, route, required_scopes_json, scope_policy_version FROM route_scope_policies WHERE tenant_id = 'tenant-a' AND service_id = 'orders-demo'"),
    }


def _domain_trace(db: Path, task_id: str, session_id: str, before: dict[str, Any]) -> dict[str, Any]:
    binding = _one(
        db,
        "SELECT b.task_id, b.tenant_id, b.actor_id, b.service_id, b.integration_id, b.principal_id, b.ticket_id, s.route FROM task_bindings b JOIN services s ON s.tenant_id = b.tenant_id AND s.service_id = b.service_id WHERE b.task_id = ?",
        (task_id,),
    )
    return {
        "captured_at_utc": datetime.now(timezone.utc).isoformat(),
        "session_id": session_id,
        "task_binding": binding,
        "task_control": _one(db, "SELECT * FROM task_controls WHERE task_id = ?", (task_id,)),
        "messages": _rows(db, "SELECT message_id, sequence, role, input_kind, body, body_digest, application_state, applied_run_id, created_at FROM messages WHERE task_id = ? ORDER BY sequence", (task_id,)),
        "runs": _rows(db, "SELECT run_id, kind, status, blocked_reason, source_message_id, expected_control_revision, control_revision_at_start, created_at, started_at, ended_at FROM task_runs WHERE task_id = ? ORDER BY created_at, rowid", (task_id,)),
        "update_assessments": _rows(db, "SELECT assessment_id, actor_id, source_message_id, source_digest, expected_control_revision, status, intent, change_summary, operation_id, correction_message_id, investigation_run_id, created_at, confirmed_at, cancelled_at FROM investigation_update_assessments WHERE task_id = ? ORDER BY created_at", (task_id,)),
        "classifier_attempts": _rows(db, "SELECT attempt_id, assessment_id, attempt_no, model_id, prompt_digest, input_digest, status, response_digest, provider_response_id, input_tokens, output_tokens, total_tokens, error_code, created_at, completed_at FROM investigation_update_attempts WHERE assessment_id IN (SELECT assessment_id FROM investigation_update_assessments WHERE task_id = ?) ORDER BY created_at", (task_id,)),
        "chat_provider_attempts": _rows(db, "SELECT attempt_id, run_id, model_id, status, provider_response_id, input_tokens, output_tokens, total_tokens, error_class, created_at, completed_at FROM chat_attempts WHERE task_id = ? ORDER BY created_at", (task_id,)),
        "s2_gate_traces": _rows(db, "SELECT trace_id, run_id, decision, reason_code, request_id, decision_id, evidence_ids_json, evidence_digests_json, predicate_json, created_at FROM s2_gate_traces WHERE task_id = ? ORDER BY created_at, rowid", (task_id,)),
        "s2_diagnosis_receipts": _rows(db, "SELECT receipt_id, run_id, request_id, decision_id, gate_policy_version, predicate_json, evidence_ids_json, evidence_digests_json, observed_versions_json, created_at FROM s2_diagnosis_receipts WHERE task_id = ? ORDER BY created_at, rowid", (task_id,)),
        "s2_handoff_drafts": _rows(db, "SELECT draft_id, receipt_id, version, content_json, content_digest, created_at FROM s2_handoff_drafts WHERE task_id = ? ORDER BY version", (task_id,)),
        "provider_traces": _rows(db, "SELECT a.run_id, t.call_id, t.attempt_id, t.model_id, t.provider_response_id, t.status, t.prompt_digest, t.tool_calls_json, t.usage_json, t.created_at FROM d2_model_traces t JOIN d2_attempts a ON a.attempt_id = t.attempt_id WHERE t.task_id = ? ORDER BY t.created_at, t.rowid", (task_id,)),
        "mcp_observations": _rows(db, "SELECT observation_id, attempt_id, tool_name, status, result_digest, result_json, created_at FROM d2_tool_observations WHERE task_id = ? ORDER BY created_at, rowid", (task_id,)),
        "evidence": _rows(db, "SELECT e.evidence_id, a.run_id, e.fact_type, e.resource_id, e.observed_versions_json, e.facts_json, e.digest, e.fetched_at FROM d2_evidence e JOIN d2_model_traces t ON t.call_id = e.call_id JOIN d2_attempts a ON a.attempt_id = t.attempt_id WHERE e.task_id = ? ORDER BY e.fetched_at, e.rowid", (task_id,)),
        "auth_events": _rows(db, "SELECT event_id, tenant_id, integration_id, principal_id, service_id, route, result_code, credential_policy_version, request_id, observed_at FROM auth_events WHERE tenant_id = 'tenant-a' AND service_id = 'orders-demo' ORDER BY event_id"),
        "authz_decisions": _rows(db, "SELECT decision_id, request_id, authn_event_id, tenant_id, principal_id, service_id, integration_id, route, outcome, reason_code, credential_policy_version, scope_policy_version, grant_version, required_scopes_json, granted_scopes_json FROM authz_events WHERE tenant_id = 'tenant-a' AND service_id = 'orders-demo' ORDER BY decision_id"),
        "versions_before_agent": before,
        "versions_after_agent": _current_versions(db),
        "business_write_counts": {
            table: int((_one(db, f"SELECT COUNT(*) AS count FROM {table} WHERE task_id = ?", (task_id,)) or {}).get("count", 0))
            for table in ("d3_approvals", "d3_action_permissions", "d3_action_intents", "d3_action_ledgers", "d3_verification_receipts", "d3_report_artifacts", "d3_delivery_records", "s2_handoff_receipts", "s2_handoff_queue_entries")
        },
    }


def _validate_agent_trace(scenario: str, journey: dict[str, Any], trace: dict[str, Any], before: dict[str, Any]) -> None:
    correction = journey["correction"]
    run_id = correction["investigation_run_id"]
    expected_status = 401 if scenario == "S1_401" else 403
    run_evidence = [item for item in trace["evidence"] if item["run_id"] == run_id]
    probes = [
        item for item in run_evidence
        if item["fact_type"] == "endpoint_probe" and json.loads(item["facts_json"]).get("http_status") == expected_status
    ]
    if not probes:
        raise RuntimeError(f"Confirmed Investigator Run has no real HTTP {expected_status} Probe Evidence.")
    probe_facts = json.loads(probes[-1]["facts_json"])
    if not probe_facts.get("request_id") or probe_facts.get("versions_stable_during_probe") is not True:
        raise RuntimeError("The current Probe is missing its trusted request correlation or stable versions.")
    if scenario == "S1_401":
        if probe_facts.get("auth_event_result") != "AUTH_REJECTED" or probe_facts.get("authz_event_id") is not None:
            raise RuntimeError("The unchanged S1 401 was not backed by an authentication rejection.")
    else:
        request_id = probe_facts["request_id"]
        scope_evidence = [
            item for item in run_evidence if item["fact_type"] == "scope_authz_decision"
            and json.loads(item["facts_json"]).get("request_id") == request_id
        ]
        decisions = [item for item in trace["authz_decisions"] if item["request_id"] == request_id]
        if not scope_evidence or not decisions:
            raise RuntimeError("The current 403 Probe lacks a same-request trusted Authz Decision Evidence.")
        facts = json.loads(scope_evidence[-1]["facts_json"])
        decision = decisions[-1]
        if (
            facts.get("outcome") != "DENY"
            or facts.get("reason_code") != "SCOPE_INSUFFICIENT"
            or facts.get("decision_id") != decision["decision_id"]
            or decision.get("outcome") != "DENY"
            or decision.get("reason_code") != "SCOPE_INSUFFICIENT"
            or decision.get("request_id") != request_id
            or probe_facts.get("authz_event_id") != decision["decision_id"]
        ):
            raise RuntimeError("Probe, Evidence, and persisted Authz Decision do not share the same 403 authorization fact.")
    if before != trace["versions_after_agent"]:
        raise RuntimeError("The Agent changed trusted Config/Principal/Policy/Scope facts during investigation.")
    if any(trace["business_write_counts"].values()):
        raise RuntimeError("Read-only investigation unexpectedly created business authorization or action writes.")
    if trace["task_binding"] is None or trace["task_binding"].get("service_id") != "orders-demo" \
            or trace["task_binding"].get("integration_id") != "integration-a" \
            or trace["task_binding"].get("principal_id") != "principal-a" \
            or trace["task_binding"].get("route") != "/api/orders/demo-order":
        raise RuntimeError("The Agent's investigation escaped its trusted TaskBinding.")


def _case(scenario: str, evidence_run: Path) -> dict[str, Any]:
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]
    work = ROOT / ".runtime" / f"m4-01-{scenario.lower()}-{run_id}"
    work.mkdir(parents=True, exist_ok=False)
    db, checkpoint = work / "domain.sqlite3", work / "checkpoints.sqlite3"
    fixture = "S1_POS" if scenario == "S1_401" else "S2_SCOPE_DENIED"
    reset_fixture(db, fixture)
    before = _current_versions(db)
    prepared_task_count = int((_one(db, "SELECT COUNT(*) AS count FROM task_bindings") or {}).get("count", 0))
    prep = {
        "kind": "PREPARATION_ONLY",
        "scenario": scenario,
        "fixture": f"reset_fixture({fixture})",
        "runtime_directory": str(work.relative_to(ROOT)),
        "performed_before_agent_run": True,
        "task_count_before_agent": prepared_task_count,
        "prepared_versions": before,
        "scope_write_by_agent_expected": 0,
    }
    base = evidence_run / scenario.lower()
    screenshots = base / "screenshots"
    base.mkdir(parents=True, exist_ok=True)
    api_port, ui_port = _free_port(), _free_port()
    api_origin, ui_origin = f"http://127.0.0.1:{api_port}", f"http://127.0.0.1:{ui_port}"
    passwords = {
        "support-a": secrets.token_urlsafe(24),
        "approver-a": secrets.token_urlsafe(24),
        "support-b": secrets.token_urlsafe(24),
        "approver-b": secrets.token_urlsafe(24),
    }
    env = _server_environment(db, checkpoint, ui_origin, passwords)
    env["OPSPILOT_INVESTIGATION_DEADLINE_MS"] = "300000"
    env["OPSPILOT_DEMO_SERVICE_ID"] = "orders-demo"
    env["OPSPILOT_DEMO_INTEGRATION_ID"] = "integration-a"
    env["OPSPILOT_DEMO_TICKET_ID"] = "INC-A-001"
    _write_json(base / "PREPARATION.json", prep)
    api = vite = None
    task_id = session_id = None
    browser_env = os.environ.copy()
    browser_env.update({
        "OPSPILOT_M4_UI_URL": ui_origin,
        "OPSPILOT_M4_SUPPORT_PASSWORD": passwords["support-a"],
        "OPSPILOT_M4_SCREENSHOTS": str(screenshots),
        "OPSPILOT_M4_SCENARIO": scenario,
        "OPSPILOT_M4_MODE": "journey",
        "OPSPILOT_M4_RESULT_PATH": str(base / "JOURNEY.json"),
    })
    try:
        api = _start_api(api_port, env, base / "api-server.log")
        api_pid = api.pid
        vite = _start_vite(ui_port, api_origin, env, base / "vite.log")
        journey = _browser_run(browser_env, base / "journey-browser.log", passwords)
        task_id, session_id = journey["task_id"], journey["session_id"]
        domain_trace = _domain_trace(db, task_id, session_id, before)
        _validate_agent_trace(scenario, journey, domain_trace, before)
        _kill(api)
        api = None
        _write_json(base / "SERVICE_RESTART.json", {
            "old_api_pid": api_pid, "terminated_before_resume": True,
            "same_domain_db": str(db.relative_to(ROOT)), "same_checkpoint_db": str(checkpoint.relative_to(ROOT)),
            "same_task_id": task_id, "same_session_id": session_id,
        })
        api = _start_api(api_port, env, base / "api-server-after-restart.log")
        resume_env = browser_env.copy()
        resume_env.update({
            "OPSPILOT_M4_MODE": "resume",
            "OPSPILOT_M4_TASK_ID": task_id,
            "OPSPILOT_M4_SESSION_ID": session_id,
            "OPSPILOT_M4_RESULT_PATH": str(base / "RESUME.json"),
        })
        resume = _browser_run(resume_env, base / "resume-browser.log", passwords)
        with (base / "SERVICE_RESTART.json").open("r", encoding="utf-8") as handle:
            restart = json.load(handle)
        restart["new_api_pid"] = api.pid
        restart["resume_status"] = resume
        _write_json(base / "SERVICE_RESTART.json", restart)
        _write_json(base / "TRACE.json", {
            "run_id": run_id, "scenario": scenario, "user_journey": journey,
            "after_service_restart": resume, "domain_trace": domain_trace,
            "service_prep": prep,
        })
        summary = {
            "run_id": run_id, "scenario": scenario, "status": "PASS",
            "task_id": task_id, "session_id": session_id,
            "expected_http_status": 401 if scenario == "S1_401" else 403,
            "confirmed_correction": journey["correction"]["correction_message_id"],
            "investigation_run_id": journey["correction"]["investigation_run_id"],
            "current_gate": journey["correction"]["current_gate"],
            "mcp_observations": len(domain_trace["mcp_observations"]),
            "service_restart_recovered": resume["api_status"] == 200,
            "evidence_dir": str(base.relative_to(ROOT)),
        }
        return summary
    except BaseException as error:
        if task_id is None:
            task_row = _one(db, "SELECT task_id FROM task_bindings ORDER BY created_at, task_id LIMIT 1")
            task_id = str(task_row["task_id"]) if task_row else None
        if task_id is not None and session_id is None:
            session_row = _one(db, "SELECT session_id FROM session_task_links WHERE task_id = ? ORDER BY session_id LIMIT 1", (task_id,))
            session_id = str(session_row["session_id"]) if session_row else None
        if task_id is not None and session_id is not None:
            _write_json(base / "TRACE.json", {
                "run_id": run_id, "scenario": scenario, "status": "PARTIAL_FAILED_ATTEMPT",
                "failure_class": type(error).__name__, "failure_message": str(error),
                "domain_trace": _domain_trace(db, task_id, session_id, before),
                "service_prep": prep,
            })
        _write_json(base / "FAILURE.json", {
            "scenario": scenario, "exception_class": type(error).__name__, "message": str(error),
            "api_exit_code": api.poll() if api is not None else None,
            "evidence_dir": str(base.relative_to(ROOT)),
        })
        raise
    finally:
        _kill(api)
        _kill(vite)


def main() -> int:
    load_local_environment()
    if not os.environ.get(MODEL_API_KEY, "").strip() or not os.environ.get(MODEL_NAME, "").strip():
        raise RuntimeError("M4-01 requires a configured model API key and model ID; no values were printed.")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    evidence_run = EVIDENCE / "runs" / f"web-{stamp}"
    evidence_run.mkdir(parents=True, exist_ok=False)
    results: list[dict[str, Any]] = []
    failures: list[dict[str, str]] = []
    for scenario in ("S1_401", "S2_403"):
        try:
            results.append(_case(scenario, evidence_run))
        except BaseException as error:
            failures.append({"scenario": scenario, "exception_class": type(error).__name__, "message": str(error)})
    _write_json(evidence_run / "RESULTS.json", {
        "run_id": stamp, "status": "PASS" if not failures and len(results) == 2 else "FAIL",
        "denominator": 2, "passed": len(results), "failed": len(failures),
        "cases": results, "failures": failures,
    })
    print(json.dumps({"evidence_dir": str(evidence_run.relative_to(ROOT)), "passed": len(results), "failed": len(failures)}, ensure_ascii=False))
    return 0 if not failures and len(results) == 2 else 1


if __name__ == "__main__":
    raise SystemExit(main())
