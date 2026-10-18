from __future__ import annotations

import argparse
import json
import os
import secrets
import shutil
import socket
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from opspilot.config import MODEL_API_KEY, MODEL_NAME, ROOT, load_local_environment
from opspilot.domain.database import connect, reset_fixture


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _start(command: list[str], cwd: Path, env: dict[str, str], output_path: Path) -> subprocess.Popen:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output = output_path.open("a", encoding="utf-8", newline="\n")
    process = subprocess.Popen(command, cwd=cwd, env=env, stdout=output, stderr=subprocess.STDOUT)
    setattr(process, "_opspilot_log_handle", output)
    return process


def _wait_http(process: subprocess.Popen, url: str, output_path: Path, timeout: int = 30) -> None:
    deadline = time.monotonic() + timeout
    last_error = "not attempted"
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"Process exited with {process.returncode}; see {output_path}.")
        try:
            response = httpx.get(url, timeout=1.0)
            if response.status_code == 200:
                return
            last_error = f"HTTP {response.status_code}"
        except httpx.HTTPError as error:
            last_error = type(error).__name__
        time.sleep(0.2)
    raise TimeoutError(f"Local service did not become ready: {last_error}; see {output_path}.")


def _kill(process: subprocess.Popen | None) -> None:
    if process is None or process.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
    else:
        process.kill()
    try:
        process.wait(timeout=15)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)
    handle = getattr(process, "_opspilot_log_handle", None)
    if handle is not None:
        handle.close()


def _server_environment(db_path: Path, checkpoint_path: Path, web_origin: str, passwords: dict[str, str]) -> dict[str, str]:
    env = os.environ.copy()
    env.update({
        "OPSPILOT_DB_PATH": str(db_path),
        "OPSPILOT_CHECKPOINT_DB_PATH": str(checkpoint_path),
        "OPSPILOT_WEB_ORIGIN": web_origin,
        "OPSPILOT_TRACE_PROVIDER_METADATA": "1",
        "OPSPILOT_WEB_SUPPORT_PASSWORD": passwords["support-a"],
        "OPSPILOT_WEB_APPROVER_PASSWORD": passwords["approver-a"],
        "OPSPILOT_WEB_SUPPORT_B_PASSWORD": passwords["support-b"],
        "OPSPILOT_WEB_APPROVER_B_PASSWORD": passwords["approver-b"],
        "OPSPILOT_INVESTIGATION_DEADLINE_MS": "240000",
        "PYTHONUTF8": "1",
    })
    return env


def _start_api(port: int, env: dict[str, str], log_path: Path) -> subprocess.Popen:
    process = _start(
        [sys.executable, "-X", "utf8", "-u", "-m", "opspilot.web.server",
         "--host", "127.0.0.1", "--port", str(port)], ROOT, env, log_path,
    )
    _wait_http(process, f"http://127.0.0.1:{port}/api/health", log_path)
    return process


def _start_vite(port: int, api_origin: str, env: dict[str, str], log_path: Path) -> subprocess.Popen:
    node = shutil.which("node")
    if not node:
        raise RuntimeError("Node.js is required for the Vue browser smoke.")
    npm_cli = Path(node).resolve().parent / "node_modules" / "npm" / "bin" / "npm-cli.js"
    vite_env = env.copy()
    vite_env["OPSPILOT_API_ORIGIN"] = api_origin
    command = [node, str(npm_cli), "run", "dev", "--", "--host", "127.0.0.1", "--port", str(port), "--strictPort"]
    process = _start(command, ROOT / "frontend", vite_env, log_path)
    _wait_http(process, f"http://127.0.0.1:{port}/", log_path)
    return process


def _browser_run(
    *, mode: str, ui_origin: str, api_origin: str, attack_origin: str,
    screenshots: Path, passwords: dict[str, str], log_path: Path,
    session_id: str | None = None, task_id: str | None = None,
    script_path: Path | None = None,
) -> dict[str, Any]:
    node = shutil.which("node")
    if not node:
        raise RuntimeError("Node.js is required for the Vue browser smoke.")
    env = os.environ.copy()
    env.update({
        "OPSPILOT_E2E_MODE": mode,
        "OPSPILOT_UI_BASE_URL": ui_origin,
        "OPSPILOT_E2E_API_ORIGIN": api_origin,
        "OPSPILOT_E2E_ATTACK_ORIGIN": attack_origin,
        "OPSPILOT_EVIDENCE_SCREENSHOTS": str(screenshots),
        "OPSPILOT_E2E_SUPPORT_PASSWORD": passwords["support-a"],
        "OPSPILOT_E2E_APPROVER_PASSWORD": passwords["approver-a"],
        "OPSPILOT_E2E_SUPPORT_B_PASSWORD": passwords["support-b"],
    })
    if session_id:
        env["OPSPILOT_E2E_SESSION_ID"] = session_id
    if task_id:
        env["OPSPILOT_E2E_TASK_ID"] = task_id
    script = script_path or ROOT / "frontend" / "e2e" / "m1-03-browser.mjs"
    result = subprocess.run([node, str(script)], cwd=ROOT / "frontend", env=env,
                            capture_output=True, text=True, encoding="utf-8", timeout=720)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    stdout = result.stdout
    stderr = result.stderr
    for password in passwords.values():
        stdout = stdout.replace(password, "[REDACTED_TEST_PASSWORD]")
        stderr = stderr.replace(password, "[REDACTED_TEST_PASSWORD]")
    log_text = f"exit_code={result.returncode}\nstdout:\n{stdout}\nstderr:\n{stderr}"
    existing_attempts = list(log_path.parent.glob(f"{log_path.stem}.attempt-*.txt"))
    attempt_numbers = [int(path.stem.rsplit("-", 1)[-1]) for path in existing_attempts]
    attempt_path = log_path.with_name(f"{log_path.stem}.attempt-{max(attempt_numbers, default=0) + 1:02d}{log_path.suffix}")
    attempt_path.write_text(log_text, encoding="utf-8")
    log_path.write_text(log_text, encoding="utf-8")
    if result.returncode != 0:
        raise RuntimeError(f"Real Edge browser smoke failed with exit code {result.returncode}; see {attempt_path}.")
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    if not lines:
        raise RuntimeError(f"Real Edge browser smoke produced no result record; see {attempt_path}.")
    return json.loads(lines[-1])


def _database_evidence(db_path: Path, session_id: str, task_id: str) -> dict[str, Any]:
    with connect(db_path) as connection:
        version = int(connection.execute("PRAGMA user_version").fetchone()[0])
        task = connection.execute(
            "SELECT status, service_id, integration_id, principal_id FROM task_bindings WHERE task_id = ?",
            (task_id,),
        ).fetchone()
        chat_runs = connection.execute(
            """SELECT r.run_id, r.status, r.blocked_reason, a.message_id
               FROM task_runs r LEFT JOIN chat_run_answers a ON a.run_id = r.run_id
               WHERE r.session_id = ? AND r.kind = 'CHAT_READONLY' ORDER BY r.created_at, r.run_id""",
            (session_id,),
        ).fetchall()
        attempts = connection.execute(
            """SELECT a.run_id, a.attempt_no, a.model_id, a.prompt_digest, a.status,
                      a.provider_response_id, a.input_tokens, a.output_tokens, a.total_tokens,
                      a.error_class, a.created_at, m.manifest_id,
                      m.selected_message_ids_json, m.evidence_refs_json, m.memory_refs_json,
                      m.model_call_refs_json, m.excluded_sources_json, m.truncation_json
               FROM chat_attempts a JOIN chat_context_manifests m ON m.attempt_id = a.attempt_id
               WHERE a.session_id = ? ORDER BY a.created_at, a.attempt_no""",
            (session_id,),
        ).fetchall()
        evidence_rows = connection.execute(
            """SELECT fact_type, resource_id, fetched_at, observed_versions_json, facts_json, digest
               FROM d2_evidence WHERE task_id = ? ORDER BY fetched_at, evidence_id""",
            (task_id,),
        ).fetchall()
        observation_counts = connection.execute(
            "SELECT tool_name, status, COUNT(*) AS count FROM d2_tool_observations WHERE task_id = ? GROUP BY tool_name, status ORDER BY tool_name, status",
            (task_id,),
        ).fetchall()
        model_rows = connection.execute(
            """SELECT model_id, provider_response_id, status, usage_json, prompt_digest, tool_calls_json
               FROM d2_model_traces WHERE task_id = ? ORDER BY created_at, rowid""",
            (task_id,),
        ).fetchall()
        context_rows = connection.execute(
            """SELECT call_id, attempt_id, model_id, prompt_digest, model_status,
                      selected_input_messages_json, task_run_control_json, evidence_ids_json,
                      error_class, built_at
               FROM d5_context_provenance WHERE task_id = ? ORDER BY built_at, call_id""",
            (task_id,),
        ).fetchall()
        task_inputs = connection.execute(
            """SELECT m.message_id, m.sequence, m.input_kind, m.body_digest,
                      m.application_state, m.applied_run_id, c.command_kind,
                      r.control_revision_at_start, r.expected_control_revision AS applied_control_revision
               FROM messages m JOIN commands c ON c.command_id = m.command_id
               LEFT JOIN task_runs r ON r.run_id = c.run_id
               WHERE m.task_id = ? AND (c.command_kind = 'CREATE_TASK' OR m.input_kind = 'CORRECT_TASK_INPUT')
               ORDER BY m.sequence""",
            (task_id,),
        ).fetchall()
        run_rows = connection.execute(
            """SELECT run_id, source_message_id, kind, status, blocked_reason,
                      expected_control_revision, consumed_message_seq, applied_critical_message_seq
               FROM task_runs WHERE task_id = ? ORDER BY created_at, run_id""",
            (task_id,),
        ).fetchall()
        attempt_counts = connection.execute(
            """SELECT kind, status, COUNT(*) AS count FROM d2_attempts
               WHERE task_id = ? GROUP BY kind, status ORDER BY kind, status""",
            (task_id,),
        ).fetchall()
        plan_rows = connection.execute(
            """SELECT p.plan_hash, p.plan_version, a.eligibility
               FROM d3_plans p LEFT JOIN d3_plan_authorizations a ON a.plan_hash = p.plan_hash
               WHERE p.task_id = ? ORDER BY p.plan_version""",
            (task_id,),
        ).fetchall()
        action_counts = {
            table: int(connection.execute(f"SELECT COUNT(*) FROM {table} WHERE task_id = ?", (task_id,)).fetchone()[0])
            for table in (
                "d3_approvals", "d3_action_permissions", "d3_action_intents", "d3_action_ledgers",
                "d3_verification_receipts", "d3_report_artifacts", "d3_delivery_records",
            )
        }
        config = connection.execute(
            """SELECT i.credential_ref, i.config_version, p.status AS principal_status,
                      a.accepted_credential_ref, a.policy_version
               FROM integrations i JOIN principals p ON p.tenant_id = i.tenant_id AND p.principal_id = i.principal_id
               JOIN services s ON s.tenant_id = i.tenant_id AND s.integration_id = i.integration_id
               JOIN auth_policies a ON a.tenant_id = s.tenant_id AND a.service_id = s.service_id
               WHERE i.tenant_id = 'tenant-a' AND i.integration_id = ?""",
            (str(task["integration_id"]),),
        ).fetchone()
        event_bounds = connection.execute(
            "SELECT MIN(event_seq), MAX(event_seq), COUNT(*) FROM session_events WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        chunk_count = int(connection.execute(
            """SELECT COUNT(*) FROM chat_answer_chunks c JOIN chat_attempts a ON a.attempt_id = c.attempt_id
               WHERE a.session_id = ?""",
            (session_id,),
        ).fetchone()[0])
    safe_facts = []
    allowed_fact_keys = {
        "integration_id", "principal_id", "credential_ref", "config_version", "status", "principal_version",
        "service_id", "accepted_credential_ref", "policy_version", "route", "http_status", "auth_event_result",
        "auth_event_scope_valid", "business_order_id", "business_order_status", "versions_stable_during_probe",
    }
    for row in evidence_rows:
        facts = json.loads(str(row["facts_json"]))
        safe_facts.append({
            "fact_type": str(row["fact_type"]), "resource_id": str(row["resource_id"]),
            "fetched_at": str(row["fetched_at"]),
            "observed_versions": json.loads(str(row["observed_versions_json"])),
            "facts": {key: facts[key] for key in sorted(allowed_fact_keys) if key in facts},
            "digest": str(row["digest"]),
        })
    return {
        "schema_version": version,
        "task": {key: task[key] for key in task.keys()} if task else None,
        "current_config_policy": {key: config[key] for key in config.keys()} if config else None,
        "chat_runs": [{key: row[key] for key in row.keys()} for row in chat_runs],
        "chat_attempts": [{
            "run_id": str(row["run_id"]), "attempt_no": int(row["attempt_no"]),
            "model_id": str(row["model_id"]), "status": str(row["status"]),
            "provider_response_id": str(row["provider_response_id"]) if row["provider_response_id"] else None,
            "token_usage": {key: row[key] for key in ("input_tokens", "output_tokens", "total_tokens")},
            "error_class": str(row["error_class"]) if row["error_class"] else None,
            "manifest_id": str(row["manifest_id"]), "prompt_digest": str(row["prompt_digest"]),
            "selected_message_ids": json.loads(str(row["selected_message_ids_json"])),
            "evidence_refs": json.loads(str(row["evidence_refs_json"])),
            "memory_refs": json.loads(str(row["memory_refs_json"])),
            "model_call_refs": json.loads(str(row["model_call_refs_json"])),
            "excluded_sources": json.loads(str(row["excluded_sources_json"])),
            "truncation": json.loads(str(row["truncation_json"])),
        } for row in attempts],
        "mcp_observation_counts": [{key: row[key] for key in row.keys()} for row in observation_counts],
        "investigation_model_traces": [{
            "model_id": str(row["model_id"]), "provider_response_id": str(row["provider_response_id"]) if row["provider_response_id"] else None,
            "status": str(row["status"]), "usage": json.loads(str(row["usage_json"])),
            "prompt_digest": str(row["prompt_digest"]),
            "tool_names": [str(call["name"]) for call in json.loads(str(row["tool_calls_json"]))
                           if isinstance(call, dict) and isinstance(call.get("name"), str)],
        } for row in model_rows],
        "investigator_context_provenance": [{
            "call_id": str(row["call_id"]), "attempt_id": str(row["attempt_id"]),
            "model_id": str(row["model_id"]), "prompt_digest": str(row["prompt_digest"]),
            "model_status": str(row["model_status"]), "error_class": row["error_class"],
            "selected_input_messages": json.loads(str(row["selected_input_messages_json"])),
            "task_run_control": json.loads(str(row["task_run_control_json"])),
            "evidence_ids": json.loads(str(row["evidence_ids_json"])), "built_at": str(row["built_at"]),
        } for row in context_rows],
        "task_input_messages": [{
            "message_id": str(row["message_id"]), "sequence": int(row["sequence"]),
            "kind": "INITIAL_SYMPTOM" if row["command_kind"] == "CREATE_TASK" else "CRITICAL_CORRECTION",
            "input_kind": str(row["input_kind"]), "digest": str(row["body_digest"]),
            "application_state": str(row["application_state"]),
            "applied_run_id": str(row["applied_run_id"]) if row["applied_run_id"] else None,
            "accepted_control_revision": int(row["control_revision_at_start"] or 0),
            "applied_control_revision": int(row["applied_control_revision"]) if row["applied_control_revision"] is not None else None,
        } for row in task_inputs],
        "runs": [{key: row[key] for key in row.keys()} for row in run_rows],
        "attempt_counts": [{key: row[key] for key in row.keys()} for row in attempt_counts],
        "plan_history": [{key: row[key] for key in row.keys()} for row in plan_rows],
        "evidence": safe_facts,
        "business_action_counts": action_counts,
        "sse_event_range": {"first": event_bounds[0], "last": event_bounds[1], "count": int(event_bounds[2])},
        "persisted_chunk_count": chunk_count,
    }


def run(evidence_dir: Path) -> int:
    load_local_environment()
    if not os.environ.get(MODEL_API_KEY) or not os.environ.get(MODEL_NAME):
        _write_json(evidence_dir / "RESULTS.json", {
            "status": "NOT_RUN", "reason": "MODEL_CONFIGURATION_MISSING",
            "api_key_present": bool(os.environ.get(MODEL_API_KEY)),
            "model_name_present": bool(os.environ.get(MODEL_NAME)),
            "base_url_present": bool(os.environ.get("OPSPILOT_MODEL_BASE_URL")),
        })
        return 2
    evidence_dir.mkdir(parents=True, exist_ok=True)
    screenshots = evidence_dir / "screenshots"
    logs = evidence_dir / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    run_stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    runtime = ROOT / ".runtime" / "m1-03-smokes" / run_stamp
    runtime.mkdir(parents=True, exist_ok=False)
    db_path, checkpoint_path = runtime / "domain.sqlite3", runtime / "checkpoints.sqlite3"
    reset_fixture(db_path, "S1_POS")
    passwords = {actor: secrets.token_urlsafe(24) for actor in ("support-a", "approver-a", "support-b", "approver-b")}
    api_port, ui_port, attack_port = _free_port(), _free_port(), _free_port()
    api_origin = f"http://127.0.0.1:{api_port}"
    ui_origin = f"http://127.0.0.1:{ui_port}"
    attack_origin = f"http://127.0.0.1:{attack_port}"
    server_env = _server_environment(db_path, checkpoint_path, ui_origin, passwords)
    server: subprocess.Popen | None = None
    vite: subprocess.Popen | None = None
    attack_vite: subprocess.Popen | None = None
    results: dict[str, Any] = {"run_stamp": run_stamp, "model_id": os.environ.get(MODEL_NAME), "provider_configured": True}
    try:
        server = _start_api(api_port, server_env, logs / "api-server.log")
        vite = _start_vite(ui_port, api_origin, server_env, logs / "vite-server.log")
        attack_vite = _start_vite(attack_port, api_origin, server_env, logs / "unlisted-origin-vite.log")
        browser = _browser_run(
            mode="full", ui_origin=ui_origin, api_origin=api_origin, attack_origin=attack_origin,
            screenshots=screenshots, passwords=passwords, log_path=logs / "browser-full.txt",
        )
        results["browser"] = browser
        session_id = str(browser["session_id"])
        task_id = str(browser["task_id"])

        # Restart the API process on the same Domain DB and checkpoint path, then
        # reopen the real browser session to verify durable messages and Task state.
        first_pid = int(server.pid)
        _kill(server)
        server = _start_api(api_port, server_env, logs / "api-server-after-restart.log")
        resumed = _browser_run(
            mode="resume", ui_origin=ui_origin, api_origin=api_origin, attack_origin=attack_origin,
            screenshots=screenshots, passwords=passwords, log_path=logs / "browser-after-restart.txt",
            session_id=session_id, task_id=task_id,
        )
        results["service_restart"] = {"prior_pid": first_pid, "restart_pid": int(server.pid), "browser_resume": resumed}
        results["domain_evidence"] = _database_evidence(db_path, session_id, task_id)
        results["checks"] = {
            "CHAT_01_three_real_provider_turns": bool(browser.get("thirdAnswerContainsLabel")),
            "CHAT_02_task_evidence_followup": all(
                row["fact_type"] in {"integration_config", "principal_status", "auth_policy", "endpoint_probe"}
                for row in results["domain_evidence"]["evidence"]
            ) and {row["fact_type"] for row in results["domain_evidence"]["evidence"]} == {
                "integration_config", "principal_status", "auth_policy", "endpoint_probe"
            },
            "CHAT_03_readonly_instruction_did_not_write": bool(browser.get("readOnlyBoundary", {}).get("unchanged"))
                and all(value == 0 for value in results["domain_evidence"]["business_action_counts"].values()),
            "CHAT_05_single_answer_per_run": all(
                row["status"] == "SUCCEEDED" and bool(row["message_id"])
                for row in results["domain_evidence"]["chat_runs"]
            ),
            "REAL_PROVIDER_CORRELATION_IDS": bool(results["domain_evidence"]["chat_attempts"])
                and all(bool(row["provider_response_id"]) for row in results["domain_evidence"]["chat_attempts"]),
            "CHAT_06_sse_chunks_and_restart": int(results["domain_evidence"]["persisted_chunk_count"]) > 0 and bool(resumed.get("persistence", {}).get("labelRecovered")),
            "CHAT_07_browser_roles_and_origin": browser.get("crossTenantStatus") == 404 and browser.get("approverInspectorStatus") == 200 and browser.get("unlistedOriginStatus") == 403,
            "UI_01_real_edge_workbench": browser.get("status") == "PASS" and (screenshots / "chat-three-turns.png").is_file(),
            "UI_02_errors_and_role_controls": browser.get("crossTenantStatus") == 404
                and browser.get("unlistedOriginStatus") == 403
                and len(browser.get("uiErrorMappings", [])) == 4
                and all(item.get("messageMapped") for item in browser.get("uiErrorMappings", [])),
        }
        required = [key for key in results["checks"] if key != "CHAT_04_revoked_source_filter"]
        results["status"] = "PASS" if all(results["checks"][key] for key in required) else "FAIL"
        results["checks"]["CHAT_04_revoked_source_filter"] = "See fresh pytest test_chat_04_revoked_memory_source_excludes_historical_assistant_message."
        results["runtime_paths"] = {"domain_db": str(db_path.relative_to(ROOT)), "checkpoint_db": str(checkpoint_path.relative_to(ROOT))}
        _write_json(evidence_dir / "RESULTS.json", results)
        return 0 if results["status"] == "PASS" else 1
    except Exception as error:
        results["status"] = "FAIL"
        results["error_class"] = type(error).__name__
        results["error"] = str(error)
        _write_json(evidence_dir / "RESULTS.json", results)
        raise
    finally:
        _kill(attack_vite)
        _kill(vite)
        _kill(server)


def main() -> int:
    parser = argparse.ArgumentParser(description="Fresh M1-03 real Provider and Microsoft Edge smoke.")
    parser.add_argument("--evidence-dir", default="docs/evidence/vnext/m1-03")
    args = parser.parse_args()
    evidence_dir = Path(args.evidence_dir)
    if not evidence_dir.is_absolute():
        evidence_dir = ROOT / evidence_dir
    return run(evidence_dir)


if __name__ == "__main__":
    raise SystemExit(main())
