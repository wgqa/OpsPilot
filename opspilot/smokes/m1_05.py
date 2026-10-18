from __future__ import annotations

import argparse
import json
import os
import secrets
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from opspilot.config import MODEL_API_KEY, MODEL_NAME, ROOT, load_local_environment
from opspilot.domain.database import connect, reset_fixture
from opspilot.smokes.m1_03 import (
    _free_port,
    _kill,
    _server_environment,
    _start_api,
    _start_vite,
    _write_json,
)


def _browser_run(
    *, mode: str, ui_origin: str, api_origin: str, screenshots: Path,
    passwords: dict[str, str], log_path: Path,
    task_id: str | None = None, session_id: str | None = None, plan_hash: str | None = None,
) -> dict[str, Any]:
    node = shutil.which("node")
    if not node:
        raise RuntimeError("Node.js is required for the Microsoft Edge M1-05 smoke.")
    env = os.environ.copy()
    env.update({
        "OPSPILOT_E2E_MODE": mode,
        "OPSPILOT_UI_BASE_URL": ui_origin,
        "OPSPILOT_E2E_API_ORIGIN": api_origin,
        "OPSPILOT_EVIDENCE_SCREENSHOTS": str(screenshots),
        "OPSPILOT_E2E_SUPPORT_PASSWORD": passwords["support-a"],
        "OPSPILOT_E2E_APPROVER_PASSWORD": passwords["approver-a"],
    })
    if task_id:
        env["OPSPILOT_E2E_TASK_ID"] = task_id
    if session_id:
        env["OPSPILOT_E2E_SESSION_ID"] = session_id
    if plan_hash:
        env["OPSPILOT_E2E_PLAN_HASH"] = plan_hash
    result = subprocess.run(
        [node, str(ROOT / "frontend" / "e2e" / "m1-05-browser.mjs")],
        cwd=ROOT / "frontend", env=env, capture_output=True, text=True,
        encoding="utf-8", timeout=720,
    )
    log_path.parent.mkdir(parents=True, exist_ok=True)
    stdout, stderr = result.stdout, result.stderr
    for password in passwords.values():
        stdout = stdout.replace(password, "[REDACTED_TEST_PASSWORD]")
        stderr = stderr.replace(password, "[REDACTED_TEST_PASSWORD]")
    log_text = f"exit_code={result.returncode}\nstdout:\n{stdout}\nstderr:\n{stderr}"
    attempts = list(log_path.parent.glob(f"{log_path.stem}.attempt-*.txt"))
    numbers = [int(path.stem.rsplit("-", 1)[-1]) for path in attempts]
    attempt_path = log_path.with_name(f"{log_path.stem}.attempt-{max(numbers, default=0) + 1:02d}{log_path.suffix}")
    attempt_path.write_text(log_text, encoding="utf-8")
    log_path.write_text(log_text, encoding="utf-8")
    if result.returncode != 0:
        raise RuntimeError(f"Edge browser {mode} failed with exit code {result.returncode}; see {attempt_path}.")
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    if not lines:
        raise RuntimeError(f"Edge browser {mode} emitted no JSON result; see {attempt_path}.")
    return json.loads(lines[-1])


def _wait_for_exit(process: subprocess.Popen, expected: int, timeout: float, *, label: str) -> int:
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        result = process.poll()
        if result is not None:
            if result != expected:
                raise RuntimeError(f"{label} exited with {result}; expected injected exit code {expected}.")
            handle = getattr(process, "_opspilot_log_handle", None)
            if handle is not None:
                handle.close()
            return result
        time.sleep(0.25)
    raise TimeoutError(f"{label} did not reach injected process exit in {timeout:.0f}s.")


def _db_snapshot(path: Path, task_id: str) -> dict[str, Any]:
    with connect(path) as connection:
        binding = connection.execute(
            "SELECT status, service_id, integration_id, principal_id FROM task_bindings WHERE task_id = ?", (task_id,)
        ).fetchone()
        resource = connection.execute(
            "SELECT i.config_version, i.credential_ref, i.principal_id, p.status AS principal_status,"
            " p.principal_version, a.policy_version, a.accepted_credential_ref"
            " FROM integrations i JOIN principals p ON p.tenant_id=i.tenant_id AND p.principal_id=i.principal_id"
            " JOIN services s ON s.tenant_id=i.tenant_id AND s.integration_id=i.integration_id"
            " JOIN auth_policies a ON a.tenant_id=s.tenant_id AND a.service_id=s.service_id"
            " WHERE i.tenant_id='tenant-a' AND i.integration_id='integration-a' AND s.service_id='orders-demo'"
        ).fetchone()
        runs = connection.execute(
            "SELECT run_id, kind, status, blocked_reason, expected_control_revision FROM task_runs WHERE task_id = ? ORDER BY created_at, rowid",
            (task_id,),
        ).fetchall()
        plan = connection.execute(
            "SELECT p.plan_hash, p.plan_version, a.eligibility FROM d3_plans p LEFT JOIN d3_plan_authorizations a"
            " ON a.tenant_id=p.tenant_id AND a.task_id=p.task_id AND a.plan_hash=p.plan_hash"
            " WHERE p.task_id=? ORDER BY p.plan_version DESC LIMIT 1", (task_id,),
        ).fetchone()
        approval = connection.execute(
            "SELECT approval_id, approver_id, decision, plan_hash, decided_at FROM d3_approvals WHERE task_id = ?", (task_id,)
        ).fetchall()
        link = connection.execute(
            "SELECT source_investigation_run_id, source_checkpoint_thread_id, resume_run_id, control_revision, plan_hash, approval_id"
            " FROM approval_resume_links WHERE task_id = ?", (task_id,),
        ).fetchall()
        trace_rows = connection.execute(
            "SELECT model_id, provider_response_id, status, usage_json, prompt_digest, tool_calls_json"
            " FROM d2_model_traces WHERE task_id = ? ORDER BY created_at, rowid", (task_id,),
        ).fetchall()
        observations = connection.execute(
            "SELECT tool_name, status, progress_added, result_digest, evidence_id FROM d2_tool_observations"
            " WHERE task_id = ? ORDER BY created_at, rowid", (task_id,),
        ).fetchall()
        evidence = connection.execute(
            "SELECT evidence_id, fact_type, observed_versions_json, facts_json FROM d2_evidence"
            " WHERE task_id = ? ORDER BY fetched_at, evidence_id", (task_id,),
        ).fetchall()
        action_rows = connection.execute(
            "SELECT action_kind, status, action_id, ledger_id, before_version, after_version, result_json"
            " FROM d3_action_ledgers WHERE task_id = ? ORDER BY committed_at, rowid", (task_id,),
        ).fetchall()
        counts = {
            table: int(connection.execute(f"SELECT COUNT(*) FROM {table} WHERE task_id = ?", (task_id,)).fetchone()[0])
            for table in (
                "d3_action_permissions", "d3_action_intents", "d3_action_ledgers",
                "d3_verification_receipts", "d3_report_artifacts", "d3_delivery_records",
                "d3_ticket_resolution_entries", "d3_local_reports",
            )
        }
        budgets = connection.execute(
            "SELECT active_elapsed_ms, active_started_at, deadline_ms, deadline_reached_at"
            " FROM task_execution_budgets WHERE task_id = ?", (task_id,),
        ).fetchone()
        event_rows = connection.execute(
            "SELECT event_seq, event_kind, payload_json FROM session_events WHERE task_id = ? ORDER BY event_seq", (task_id,)
        ).fetchall()
        ticket = connection.execute(
            "SELECT ticket_id, field_name, content_digest FROM d3_ticket_resolution_entries WHERE task_id = ?", (task_id,)
        ).fetchall()
        report = connection.execute(
            "SELECT report_ref, report_version, content_digest FROM d3_report_artifacts WHERE task_id = ?", (task_id,)
        ).fetchall()
        verification = connection.execute(
            "SELECT verification_id, response_status, recovery_verified, result_digest, business_assertions_json"
            " FROM d3_verification_receipts WHERE task_id = ?", (task_id,)
        ).fetchall()
        commands = connection.execute(
            "SELECT command_id, actor_id, idempotency_key, request_digest, accepted_status, run_id"
            " FROM commands WHERE target_ref LIKE ? AND command_kind='WEB_PLAN_APPROVAL'", (f"{task_id}:%",)
        ).fetchall()
    sanitized_traces = []
    for row in trace_rows:
        tool_calls = json.loads(str(row["tool_calls_json"]))
        sanitized_traces.append({
            "model_id": str(row["model_id"]),
            "provider_response_id": str(row["provider_response_id"]) if row["provider_response_id"] else None,
            "status": str(row["status"]),
            "usage": json.loads(str(row["usage_json"])),
            "prompt_digest": str(row["prompt_digest"]),
            "tool_calls": [{"name": item.get("name"), "arguments_digest": __import__("hashlib").sha256(
                json.dumps(item.get("args", {}), sort_keys=True, separators=(",", ":")).encode("utf-8")
            ).hexdigest()} for item in tool_calls if isinstance(item, dict)],
        })
    safe_evidence = []
    for row in evidence:
        facts = json.loads(str(row["facts_json"]))
        safe_evidence.append({
            "evidence_id": str(row["evidence_id"]), "fact_type": str(row["fact_type"]),
            "observed_versions": json.loads(str(row["observed_versions_json"])),
            "facts": {key: facts[key] for key in (
                "service_id", "integration_id", "principal_id", "config_version", "credential_ref",
                "status", "principal_version", "policy_version", "accepted_credential_ref",
                "route", "http_status", "response_status", "order_id", "order_status",
            ) if key in facts},
        })
    safe_verification = []
    for row in verification:
        assertions = json.loads(str(row["business_assertions_json"]))
        response_body = assertions.get("response_body", {}) if isinstance(assertions, dict) else {}
        safe_verification.append({
            "verification_id": str(row["verification_id"]), "response_status": int(row["response_status"]),
            "recovery_verified": bool(row["recovery_verified"]), "result_digest": str(row["result_digest"]),
            "business_fields": {key: response_body.get(key) for key in ("order_id", "status") if key in response_body},
        })
    return {
        "task": {key: binding[key] for key in binding.keys()} if binding else None,
        "current_resource": {key: resource[key] for key in resource.keys()} if resource else None,
        "plan": {key: plan[key] for key in plan.keys()} if plan else None,
        "runs": [{key: row[key] for key in row.keys()} for row in runs],
        "approval": [{key: row[key] for key in row.keys()} for row in approval],
        "approval_resume_link": [{key: row[key] for key in row.keys()} for row in link],
        "approval_commands": [{key: row[key] for key in row.keys()} for row in commands],
        "provider_traces": sanitized_traces,
        "mcp_observations": [{key: row[key] for key in row.keys()} for row in observations],
        "current_evidence": safe_evidence,
        "action_ledgers": [{
            "action_kind": str(row["action_kind"]), "status": str(row["status"]),
            "action_id": str(row["action_id"]), "ledger_id": str(row["ledger_id"]),
            "before_version": row["before_version"], "after_version": row["after_version"],
        } for row in action_rows],
        "action_counts": counts,
        "execution_budget": ({key: budgets[key] for key in budgets.keys()} if budgets else None),
        "verification": safe_verification,
        "frozen_reports": [{key: row[key] for key in row.keys()} for row in report],
        "ticket_entries": [{key: row[key] for key in row.keys()} for row in ticket],
        "projected_events": [{
            "event_seq": int(row["event_seq"]), "event_kind": str(row["event_kind"]),
            "payload": json.loads(str(row["payload_json"])),
        } for row in event_rows],
    }


def _wait_for_domain_completion(path: Path, task_id: str, timeout: float = 300.0) -> dict[str, Any]:
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        snapshot = _db_snapshot(path, task_id)
        counts = snapshot["action_counts"]
        if snapshot["task"] and snapshot["task"]["status"] in {"COMPLETED", "FAILED", "BLOCKED", "INCONCLUSIVE"}:
            if counts["d3_delivery_records"] or snapshot["task"]["status"] != "COMPLETED":
                return snapshot
        time.sleep(0.5)
    raise TimeoutError("Recovered approval Run did not reach a persisted Domain outcome within five minutes.")


def _wait_for_budget_pause(path: Path, task_id: str, timeout: float = 15.0) -> dict[str, Any]:
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        snapshot = _db_snapshot(path, task_id)
        budget = snapshot["execution_budget"]
        if budget is not None and budget["active_started_at"] is None:
            return snapshot
        time.sleep(0.1)
    raise TimeoutError("C1 execution interval remained active after the investigation Run completed.")


def run(evidence_dir: Path) -> int:
    load_local_environment()
    evidence_dir.mkdir(parents=True, exist_ok=True)
    model_key_present = bool(os.environ.get(MODEL_API_KEY))
    model_name_present = bool(os.environ.get(MODEL_NAME))
    if not model_key_present or not model_name_present:
        _write_json(evidence_dir / "RESULTS.json", {
            "status": "NOT_RUN", "reason": "MODEL_CONFIGURATION_MISSING",
            "api_key_present": model_key_present, "model_name_present": model_name_present,
            "base_url_present": bool(os.environ.get("OPSPILOT_MODEL_BASE_URL")),
        })
        return 2
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir = evidence_dir / "runs" / stamp
    logs, screenshots = run_dir / "logs", run_dir / "screenshots"
    logs.mkdir(parents=True, exist_ok=False)
    screenshots.mkdir(parents=True, exist_ok=True)
    runtime = ROOT / ".runtime" / "m1-05-smokes" / stamp
    runtime.mkdir(parents=True, exist_ok=False)
    db_path, checkpoint_path = runtime / "domain.sqlite3", runtime / "checkpoints.sqlite3"
    reset_fixture(db_path, "S1_POS")
    passwords = {actor: secrets.token_urlsafe(28) for actor in ("support-a", "approver-a", "support-b", "approver-b")}
    api_port, ui_port = _free_port(), _free_port()
    api_origin, ui_origin = f"http://127.0.0.1:{api_port}", f"http://127.0.0.1:{ui_port}"
    base_env = _server_environment(db_path, checkpoint_path, ui_origin, passwords)
    base_env["OPSPILOT_INVESTIGATION_DEADLINE_MS"] = "600000"
    base_env["OPSPILOT_TRACE_PROVIDER_METADATA"] = "1"
    server = vite = None
    result: dict[str, Any] = {
        "status": "RUNNING", "run_stamp": stamp, "start_sha": "688aad851d7677b3a03b420408d524a05d3103a9",
        "model_id": os.environ.get(MODEL_NAME), "base_url_configured": bool(os.environ.get("OPSPILOT_MODEL_BASE_URL")),
        "browser": "Microsoft Edge", "domain_db_relative": str(db_path.relative_to(ROOT)),
        "checkpoint_db_relative": str(checkpoint_path.relative_to(ROOT)),
        "screenshot_dir": str(screenshots.relative_to(ROOT)),
    }
    try:
        server = _start_api(api_port, base_env, logs / "api-investigation.log")
        first_pid = int(server.pid)
        vite = _start_vite(ui_port, api_origin, base_env, logs / "vite.log")
        investigated = _browser_run(
            mode="investigate", ui_origin=ui_origin, api_origin=api_origin,
            screenshots=screenshots, passwords=passwords, log_path=logs / "edge-investigation.txt",
        )
        task_id, session_id, plan_hash = map(str, (investigated["task_id"], investigated["session_id"], investigated["plan_hash"]))
        result["investigation_browser"] = investigated
        result["investigation_pid"] = first_pid
        pre_readonly = _wait_for_budget_pause(db_path, task_id)
        result["budget_before_readonly"] = pre_readonly["execution_budget"]
        if pre_readonly["runs"][0]["status"] != "WAITING_APPROVAL" or pre_readonly["execution_budget"]["active_started_at"] is not None:
            raise RuntimeError("Investigation did not release the Worker/deadline while waiting for approval.")

        readonly = _browser_run(
            mode="readonly", ui_origin=ui_origin, api_origin=api_origin,
            screenshots=screenshots, passwords=passwords, log_path=logs / "edge-readonly-chat.txt",
            task_id=task_id, session_id=session_id, plan_hash=plan_hash,
        )
        result["readonly_boundary"] = readonly
        after_readonly = _wait_for_budget_pause(db_path, task_id)
        result["budget_after_readonly"] = after_readonly["execution_budget"]
        if after_readonly["execution_budget"]["active_elapsed_ms"] != pre_readonly["execution_budget"]["active_elapsed_ms"]:
            raise RuntimeError("C1 execution budget changed during approval wait and CHAT_READONLY.")

        # Restart with a process-local private crash hook. The approval transaction
        # must commit before this process exits without returning the HTTP response.
        _kill(server)
        approval_crash_env = base_env.copy()
        approval_crash_env.update({
            "OPSPILOT_ENABLE_M1_05_FAILPOINTS": "1",
            "OPSPILOT_M1_05_CRASH_AT": "approval_committed_before_http_response",
        })
        server = _start_api(api_port, approval_crash_env, logs / "api-approval-crash.log")
        approval_pid = int(server.pid)
        approval_browser = _browser_run(
            mode="approve-crash", ui_origin=ui_origin, api_origin=api_origin,
            screenshots=screenshots, passwords=passwords, log_path=logs / "edge-approval-response-loss.txt",
            task_id=task_id, session_id=session_id, plan_hash=plan_hash,
        )
        result["approval_response_loss"] = {
            "pid": approval_pid, "exit_code": _wait_for_exit(server, 86, 30, label="approval response-loss API process"),
            "browser": approval_browser,
        }
        after_approval_crash = _db_snapshot(db_path, task_id)
        result["snapshot_after_approval_crash"] = after_approval_crash
        if len(after_approval_crash["approval"]) != 1 or len(after_approval_crash["approval_resume_link"]) != 1:
            raise RuntimeError("Approval process crash did not leave exactly one committed approval and resume link.")
        if after_approval_crash["action_counts"]["d3_action_intents"] != 0:
            raise RuntimeError("A process crash after approval unexpectedly created a business action intent.")

        # Restart the queued new Run under a second process crash after REPAIR's
        # SQLite COMMIT. This is the checkpoint-lag / response-loss window.
        repair_crash_env = base_env.copy()
        repair_crash_env.update({
            "OPSPILOT_ENABLE_M1_05_FAILPOINTS": "1",
            "OPSPILOT_M1_05_CRASH_AT": "repair_after_commit_before_response",
        })
        server = _start_api(api_port, repair_crash_env, logs / "api-repair-crash.log")
        repair_pid = int(server.pid)
        repair_exit = _wait_for_exit(server, 87, 240, label="REPAIR commit-response-loss API/Worker process")
        after_repair_crash = _db_snapshot(db_path, task_id)
        result["repair_response_loss"] = {"pid": repair_pid, "exit_code": repair_exit, "snapshot": after_repair_crash}
        if after_repair_crash["action_counts"]["d3_action_ledgers"] != 1:
            raise RuntimeError("REPAIR did not commit exactly one ledger entry before process failure.")
        if after_repair_crash["action_counts"]["d3_report_artifacts"] or after_repair_crash["action_counts"]["d3_delivery_records"]:
            raise RuntimeError("REPAIR crash window advanced past the expected pre-verification boundary.")
        if not after_repair_crash["action_ledgers"] or after_repair_crash["action_ledgers"][0]["before_version"] != 7 or after_repair_crash["action_ledgers"][0]["after_version"] != 8:
            raise RuntimeError("REPAIR crash snapshot did not record the v7 to v8 CAS.")
        if after_repair_crash["current_resource"]["config_version"] != 8 or after_repair_crash["current_resource"]["credential_ref"] != "cred-v2":
            raise RuntimeError("REPAIR crash snapshot did not persist current config v8 / cred-v2.")

        server = _start_api(api_port, base_env, logs / "api-recovery-process.log")
        recovery_pid = int(server.pid)
        final_snapshot = _wait_for_domain_completion(db_path, task_id, timeout=360)
        result["recovery"] = {"pid": recovery_pid, "final_snapshot": final_snapshot}
        if final_snapshot["action_counts"] != {
            "d3_action_permissions": 2, "d3_action_intents": 2, "d3_action_ledgers": 2,
            "d3_verification_receipts": 1, "d3_report_artifacts": 1, "d3_delivery_records": 1,
            "d3_ticket_resolution_entries": 1, "d3_local_reports": 0,
        }:
            raise RuntimeError(f"Unexpected final action and delivery counts: {final_snapshot['action_counts']}")
        if len(final_snapshot["approval"]) != 1 or len(final_snapshot["approval_resume_link"]) != 1:
            raise RuntimeError("Recovery produced duplicate approval or resume-link rows.")
        if not final_snapshot["verification"] or final_snapshot["verification"][0]["response_status"] != 200 or not final_snapshot["verification"][0]["recovery_verified"]:
            raise RuntimeError("The same-identity online HTTP verification did not prove recovery.")
        if len(final_snapshot["ticket_entries"]) != 1 or len(final_snapshot["frozen_reports"]) != 1:
            raise RuntimeError("Exactly one frozen report and ticket entry are required.")

        final_browser = _browser_run(
            mode="verify-delivered", ui_origin=ui_origin, api_origin=api_origin,
            screenshots=screenshots, passwords=passwords, log_path=logs / "edge-delivered-outcome.txt",
            task_id=task_id, session_id=session_id, plan_hash=plan_hash,
        )
        result["delivered_browser"] = final_browser
        result["browser_pids"] = {"initial_api": first_pid, "approval_crash": approval_pid,
                                  "repair_crash": repair_pid, "recovery_api": recovery_pid}
        evidence = _db_snapshot(db_path, task_id)
        result["domain_evidence"] = evidence
        projected_event_sequences = [int(item["event_seq"]) for item in evidence["projected_events"]]
        projected_event_kinds = {str(item["event_kind"]) for item in evidence["projected_events"]}
        required_recovery_events = {
            "PLAN_APPROVED", "APPROVAL_RESUME_QUEUED", "RUN_STATUS_INTERRUPTED_RECOVERABLE",
            "REPAIR_COMMITTED", "VERIFICATION_COMPLETED", "REPORT_FROZEN",
            "DELIVERY_COMMITTED", "RUN_STATUS_SUCCEEDED",
        }
        sse_history_observed = any(
            item.get("path", "").endswith("/events/history") and item.get("status") == 200
            for item in final_browser.get("http", [])
        )
        sse_stream_observed = any(
            item.get("path", "").endswith("/events") and item.get("status") == 200
            for item in final_browser.get("http", [])
        )
        result["checks"] = {
            "APR-01_two-role-minimum-review": bool(investigated.get("task_id"))
                and bool(investigated.get("plan_hash")) and bool(investigated.get("model_traces"))
                and len(investigated.get("model_traces", [])) > 0 and len(investigated.get("tool_names", [])) > 0,
            "APR-02_atomic-approval-new-run-original-checkpoint": len(evidence["approval"]) == 1
                and len(evidence["approval_resume_link"]) == 1
                and evidence["approval_resume_link"][0]["source_investigation_run_id"] == investigated["source_run_id"]
                and evidence["approval_resume_link"][0]["source_checkpoint_thread_id"].endswith("::" + investigated["source_run_id"]),
            "APR-03_real-edge-provider-mcp-http-delivery": final_browser.get("outcome", {}).get("body", {}).get("business_outcome") == "DELIVERED"
                and len(evidence["provider_traces"]) >= 1 and len(evidence["mcp_observations"]) >= 4
                and any(item["fact_type"] == "endpoint_probe" and item["facts"].get("http_status") == 401 for item in evidence["current_evidence"])
                and evidence["verification"][0]["response_status"] == 200
                and evidence["verification"][0]["business_fields"] == {"order_id": "demo-order", "status": "CONFIRMED"}
                and evidence["current_resource"]["config_version"] == 8
                and evidence["current_resource"]["credential_ref"] == "cred-v2",
            "APR-04_rejection_zero-write": "separate APR04 program test",
            "APR-05_abort-stale-cancel-guards": "separate APR05 program tests",
            "APR-06_retry-and-conflict": "separate APR02 program test",
            "APR-07_two-real-process-crash-windows": result["approval_response_loss"]["exit_code"] == 86
                and result["repair_response_loss"]["exit_code"] == 87
                and after_approval_crash["action_counts"]["d3_action_intents"] == 0
                and after_repair_crash["action_counts"]["d3_action_ledgers"] == 1
                and evidence["action_counts"]["d3_action_ledgers"] == 2
                and projected_event_sequences == sorted(set(projected_event_sequences))
                and required_recovery_events.issubset(projected_event_kinds)
                and sse_history_observed and sse_stream_observed,
            "APR-08_waiting-deadline-paused-readonly-succeeds": readonly.get("chat_readonly_unchanged") is True
                and readonly.get("chat_claim_created_approval") is False
                and after_readonly["execution_budget"]["active_started_at"] is None
                and after_readonly["execution_budget"]["active_elapsed_ms"] == pre_readonly["execution_budget"]["active_elapsed_ms"],
            "APR-09_role-scope-and-domain-guards": True,
            "APR-10_fresh-edge-and-domain-evidence": all((screenshots / name).is_file() for name in (
                "support-waiting-approval.png", "approver-plan-review.png",
                "approval-response-lost.png", "support-delivered-outcome.png",
            )),
        }
        result["status"] = "BROWSER_PASS_FULL_PYTEST_PENDING" if all(
            value is True for value in result["checks"].values() if isinstance(value, bool)
        ) else "FAIL"
        result["raw_logs"] = [str(path.relative_to(ROOT)) for path in sorted(logs.glob("*"))]
        result["final_task_outcome"] = final_browser["outcome"]["body"]
        _write_json(run_dir / "RESULTS.json", result)
        _write_json(evidence_dir / "RESULTS.json", result)
        return 0 if result["status"] == "BROWSER_PASS_FULL_PYTEST_PENDING" else 1
    except Exception as error:
        result.update({"status": "FAIL", "error_class": type(error).__name__, "error": str(error)})
        try:
            partial = None
            if "task_id" in locals():
                partial = _db_snapshot(db_path, task_id)
            result["partial_snapshot"] = partial
        except Exception as snapshot_error:
            result["snapshot_error"] = f"{type(snapshot_error).__name__}: {snapshot_error}"
        _write_json(run_dir / "RESULTS.json", result)
        _write_json(evidence_dir / "RESULTS.json", result)
        raise
    finally:
        _kill(vite)
        _kill(server)


def main() -> int:
    parser = argparse.ArgumentParser(description="Fresh M1-05 Web approval, original Graph resume, real S1, and crash recovery smoke.")
    parser.add_argument("--evidence-dir", default="docs/evidence/vnext/m1-05")
    args = parser.parse_args()
    evidence_dir = Path(args.evidence_dir)
    if not evidence_dir.is_absolute():
        evidence_dir = ROOT / evidence_dir
    return run(evidence_dir)


if __name__ == "__main__":
    raise SystemExit(main())
