from __future__ import annotations

import argparse
import json
import os
import secrets
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


def _write(path: Path, event: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as output:
        output.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _server_env(db_path: Path, checkpoint_path: Path, origin: str) -> tuple[dict[str, str], dict[str, str]]:
    environment = os.environ.copy()
    passwords = {
        "support-a": secrets.token_urlsafe(32),
        "approver-a": secrets.token_urlsafe(32),
        "support-b": secrets.token_urlsafe(32),
        "approver-b": secrets.token_urlsafe(32),
    }
    environment.update({
        "OPSPILOT_DB_PATH": str(db_path),
        "OPSPILOT_CHECKPOINT_DB_PATH": str(checkpoint_path),
        "OPSPILOT_WEB_ORIGIN": origin,
        "OPSPILOT_WEB_SUPPORT_PASSWORD": passwords["support-a"],
        "OPSPILOT_WEB_APPROVER_PASSWORD": passwords["approver-a"],
        "OPSPILOT_WEB_SUPPORT_B_PASSWORD": passwords["support-b"],
        "OPSPILOT_WEB_APPROVER_B_PASSWORD": passwords["approver-b"],
        "OPSPILOT_INVESTIGATION_DEADLINE_MS": "180000",
        "PYTHONUTF8": "1",
    })
    return environment, passwords


def _start_server(port: int, environment: dict[str, str], output, timeout: float = 20.0) -> subprocess.Popen:
    process = subprocess.Popen(
        [sys.executable, "-X", "utf8", "-u", "-m", "opspilot.web.server",
         "--host", "127.0.0.1", "--port", str(port)],
        cwd=ROOT, env=environment, stdout=output, stderr=subprocess.STDOUT,
    )
    base_url = f"http://127.0.0.1:{port}"
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if process.poll() is not None:
            raise RuntimeError(f"Web server exited before readiness with code {process.returncode}.")
        try:
            response = httpx.get(f"{base_url}/api/health", timeout=0.5)
            if response.status_code == 200:
                return process
        except httpx.HTTPError:
            pass
        time.sleep(0.05)
    raise TimeoutError("Web server did not become ready within the configured timeout.")


def _kill_process_tree(process: subprocess.Popen) -> None:
    if process.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False,
        )
    else:
        process.kill()
    process.wait(timeout=15)


def _read_one_sse_event(client: httpx.Client, url: str, headers: dict[str, str]) -> dict[str, Any]:
    with client.stream("GET", url, headers=headers, timeout=httpx.Timeout(5.0, read=5.0)) as response:
        if response.status_code != 200:
            raise RuntimeError(f"SSE returned HTTP {response.status_code}.")
        fields: dict[str, str] = {}
        for line in response.iter_lines():
            if line.startswith(":"):
                continue
            if not line:
                if fields:
                    return {
                        "event_seq": int(fields["id"]),
                        "event_kind": fields.get("event", "message"),
                        "payload": json.loads(fields.get("data", "{}")),
                    }
                continue
            key, _, value = line.partition(":")
            fields[key] = value.lstrip()
    raise RuntimeError("SSE stream ended before returning one durable event.")


def _attempt_snapshot(db_path: Path, task_id: str) -> dict[str, Any]:
    with connect(db_path) as connection:
        attempts = connection.execute(
            "SELECT kind, status, COUNT(*) AS n FROM d2_attempts WHERE task_id = ? GROUP BY kind, status ORDER BY kind, status",
            (task_id,),
        ).fetchall()
        traces = connection.execute(
            "SELECT model_id, provider_response_id, tool_calls_json, usage_json, status, prompt_digest FROM d2_model_traces WHERE task_id = ? ORDER BY created_at, rowid",
            (task_id,),
        ).fetchall()
        observations = connection.execute(
            "SELECT tool_name, status, progress_added, result_digest, evidence_id FROM d2_tool_observations WHERE task_id = ? ORDER BY created_at, rowid",
            (task_id,),
        ).fetchall()
        evidence = connection.execute(
            "SELECT fact_type, facts_json FROM d2_evidence WHERE task_id = ? ORDER BY fetched_at, evidence_id",
            (task_id,),
        ).fetchall()
        counts = {
            table: int(connection.execute(f"SELECT COUNT(*) FROM {table} WHERE task_id = ?", (task_id,)).fetchone()[0])
            for table in (
                "d3_approvals", "d3_action_intents", "d3_action_ledgers",
                "d3_verification_receipts", "d3_report_artifacts", "d3_delivery_records",
            )
        }
    sanitized_traces = []
    for row in traces:
        calls = json.loads(str(row["tool_calls_json"]))
        sanitized_traces.append({
            "model_id": str(row["model_id"]),
            "provider_response_id": str(row["provider_response_id"]) if row["provider_response_id"] else None,
            "status": str(row["status"]),
            "prompt_digest": str(row["prompt_digest"]),
            "tool_calls": [
                {"name": str(call.get("name", "")),
                 "arguments_digest": __import__("hashlib").sha256(
                     json.dumps(call.get("args", {}), sort_keys=True, separators=(",", ":")).encode()
                 ).hexdigest()}
                for call in calls if isinstance(call, dict)
            ],
            "usage": json.loads(str(row["usage_json"])),
        })
    allowed_fact_keys = {
        "credential_ref", "accepted_credential_ref", "principal_status", "http_status",
        "auth_event_result", "business_order_id", "business_order_status", "status",
        "principal_version", "config_version", "policy_version", "service_id",
        "integration_id", "principal_id", "route",
    }
    sanitized_evidence = []
    for row in evidence:
        facts = json.loads(str(row["facts_json"]))
        sanitized_evidence.append({
            "fact_type": str(row["fact_type"]),
            "facts": {key: facts[key] for key in sorted(allowed_fact_keys) if key in facts},
        })
    return {
        "attempts": [{key: row[key] for key in row.keys()} for row in attempts],
        "model_traces": sanitized_traces,
        "mcp_observations": [{key: row[key] for key in row.keys()} for row in observations],
        "evidence": sanitized_evidence,
        "business_write_counts": counts,
    }


def _run(args: argparse.Namespace) -> int:
    load_local_environment()
    evidence_dir = Path(args.evidence_dir)
    if not evidence_dir.is_absolute():
        evidence_dir = ROOT / evidence_dir
    evidence_dir.mkdir(parents=True, exist_ok=True)
    log_paths = {
        "http": evidence_dir / "logs" / "http-two-roles.jsonl",
        "sse": evidence_dir / "logs" / "sse-reconnect.jsonl",
        "restart": evidence_dir / "logs" / "worker-restart.jsonl",
        "model": evidence_dir / "logs" / "real-model-taskrun.jsonl",
        "server": evidence_dir / "logs" / "web-server.log",
    }
    for path in log_paths.values():
        path.parent.mkdir(parents=True, exist_ok=True)
    if not os.environ.get(MODEL_API_KEY) or not os.environ.get(MODEL_NAME):
        _write(log_paths["model"], {
            "status": "NOT_RUN", "reason": "MODEL_CONFIGURATION_MISSING",
            "api_key_present": bool(os.environ.get(MODEL_API_KEY)),
            "model_name_present": bool(os.environ.get(MODEL_NAME)),
            "base_url_present": bool(os.environ.get("OPSPILOT_MODEL_BASE_URL")),
        })
        return 2

    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    runtime = ROOT / ".runtime" / "m1-02-smokes" / run_id
    runtime.mkdir(parents=True, exist_ok=False)
    db_path, checkpoint_path = runtime / "domain.sqlite3", runtime / "checkpoints.sqlite3"
    reset_fixture(db_path, "S1_POS")
    port = _free_port()
    origin = f"http://127.0.0.1:{port}"
    environment, passwords = _server_env(db_path, checkpoint_path, origin)
    server_output = log_paths["server"].open("a", encoding="utf-8", newline="\n")
    server: subprocess.Popen | None = None
    support_cookie: str | None = None
    csrf: str | None = None
    session_id: str | None = None
    task_id: str | None = None
    run_id_value: str | None = None
    process_restart_observed = False
    try:
        server = _start_server(port, environment, server_output)
        base = origin
        support = httpx.Client(base_url=base, timeout=httpx.Timeout(5.0, read=10.0))
        approver = httpx.Client(base_url=base, timeout=5.0)
        other = httpx.Client(base_url=base, timeout=5.0)
        try:
            health = support.get("/api/health")
            unauthenticated = support.get("/api/sessions")
            login = support.post(
                "/api/auth/login", headers={"Origin": origin},
                json={"actor_id": "support-a", "password": passwords["support-a"]},
            )
            if login.status_code != 200:
                raise RuntimeError(f"support-a login failed with HTTP {login.status_code}.")
            csrf = str(login.json()["csrf_token"])
            support_cookie = support.cookies.get("opspilot_session")
            support_headers = {"Origin": origin, "X-CSRF-Token": csrf}
            missing_csrf = support.post("/api/sessions", headers={"Origin": origin})
            wrong_origin = support.post(
                "/api/sessions",
                headers={"Origin": "http://attacker.invalid", "X-CSRF-Token": csrf},
            )
            approver_login = approver.post(
                "/api/auth/login", headers={"Origin": origin},
                json={"actor_id": "approver-a", "password": passwords["approver-a"]},
            )
            other_login = other.post(
                "/api/auth/login", headers={"Origin": origin},
                json={"actor_id": "support-b", "password": passwords["support-b"]},
            )
            approver_headers = {"Origin": origin, "X-CSRF-Token": approver_login.json()["csrf_token"]}
            other_headers = {"Origin": origin, "X-CSRF-Token": other_login.json()["csrf_token"]}
            session_response = support.post("/api/sessions", headers=support_headers)
            session_id = str(session_response.json()["session_id"])
            _write(log_paths["http"], {
                "case": "WEB-01/02", "server_pid": server.pid, "origin": origin,
                "health_status": health.status_code,
                "unauthenticated_sessions_status": unauthenticated.status_code,
                "support_login_status": login.status_code,
                "support_identity": support.get("/api/auth/me").json(),
                "approver_login_status": approver_login.status_code,
                "approver_identity": approver.get("/api/auth/me").json(),
                "other_tenant_login_status": other_login.status_code,
                "session_create_status": session_response.status_code,
                "missing_csrf_status": missing_csrf.status_code,
                "wrong_origin_status": wrong_origin.status_code,
            })

            first_sse = _read_one_sse_event(
                support, f"/api/sessions/{session_id}/events?after=0", {},
            )
            # End the stream after one durable frame; worker progress must not
            # depend on this client's socket staying open.
            chat = support.post(
                f"/api/sessions/{session_id}/messages",
                headers={**support_headers, "Idempotency-Key": "m102-live-chat-readonly"},
                json={"input_kind": "CHAT_READONLY", "body": "Show the current status without starting another investigation."},
            )
            chat_run = support.get(f"/api/runs/{chat.json()['run_id']}")
            resumed_sse = _read_one_sse_event(
                support,
                f"/api/sessions/{session_id}/events?after=999",
                {"Last-Event-ID": str(first_sse["event_seq"])},
            )
            history_replay = support.get(
                f"/api/sessions/{session_id}/events/history?after=999",
                headers={"Last-Event-ID": "0"},
            ).json()["items"]
            _write(log_paths["sse"], {
                "case": "N2-02/N2-04", "first_stream_frame": first_sse,
                "disconnect_after_first_frame": True, "readonly_message_status": chat.status_code,
                "readonly_run_status": chat_run.json()["status"],
                "readonly_answer_status": chat_run.json()["answer_status"],
                "reconnect_last_event_id": first_sse["event_seq"],
                "reconnected_frame": resumed_sse,
                "history_last_event_id_zero_sequences": [item["event_seq"] for item in history_replay],
                "cursor_precedence": "Last-Event-ID overrides after",
            })

            task_response = support.post(
                f"/api/sessions/{session_id}/tasks",
                headers={**support_headers, "Idempotency-Key": "m102-live-s1-task"},
                json={"initial_message": "The authenticated orders route started returning 401 after credential rotation."},
            )
            if task_response.status_code != 202:
                raise RuntimeError(f"Task admission returned HTTP {task_response.status_code}.")
            accepted = task_response.json()
            task_id, run_id_value = str(accepted["task_id"]), str(accepted["run_id"])
            replay_response = support.post(
                f"/api/sessions/{session_id}/tasks",
                headers={**support_headers, "Idempotency-Key": "m102-live-s1-task"},
                json={"initial_message": "The authenticated orders route started returning 401 after credential rotation."},
            )
            conflict_response = support.post(
                f"/api/sessions/{session_id}/tasks",
                headers={**support_headers, "Idempotency-Key": "m102-live-s1-task"},
                json={"initial_message": "different canonical request"},
            )
            task_created_event = _read_one_sse_event(
                support,
                f"/api/sessions/{session_id}/events?after=0",
                {"Last-Event-ID": str(resumed_sse["event_seq"])},
            )
            cross_session = other.get(f"/api/sessions/{session_id}")
            cross_task = other.get(f"/api/tasks/{task_id}")
            forged_actor = other.get(
                f"/api/sessions/{session_id}",
                headers={"X-Actor-ID": "support-a", "X-Tenant-ID": "tenant-a", "X-Executor-ID": "executor-a"},
            )
            approver_abort = approver.post(
                f"/api/tasks/{task_id}/abort", headers={**approver_headers, "Idempotency-Key": "m102-approver-abort"},
                json={"reason": "read-only approver cannot abort"},
            )
            _write(log_paths["http"], {
                "case": "WEB-02/03/05", "task_admission_status": task_response.status_code,
                "replay_status": replay_response.status_code, "same_ids": all(
                    replay_response.json()[key] == accepted[key]
                    for key in ("task_id", "message_id", "command_id", "run_id")
                ),
                "conflicting_digest_status": conflict_response.status_code,
                "conflicting_digest_code": conflict_response.json().get("code"),
                "cross_tenant_session_status": cross_session.status_code,
                "cross_tenant_task_status": cross_task.status_code,
                "cross_tenant_with_forged_identity_headers_status": forged_actor.status_code,
                "approver_abort_status": approver_abort.status_code,
                "approver_abort_code": approver_abort.json().get("code"),
                "idempotency_key": "m102-live-s1-task",
                "task_created_event": task_created_event,
                "accepted_ids": {key: accepted[key] for key in ("task_id", "message_id", "command_id", "run_id")},
            })

            # Kill only after an actual MODEL attempt is durably reserved and a
            # LangGraph checkpoint exists. The restarted service must recover and
            # finish the same Run, not create a new Task/Run.
            restart_deadline = time.monotonic() + args.restart_window_seconds
            while time.monotonic() < restart_deadline:
                with connect(db_path) as connection:
                    run = connection.execute(
                        "SELECT status, blocked_reason FROM task_runs WHERE run_id = ?", (run_id_value,)
                    ).fetchone()
                    model_attempts = int(connection.execute(
                        "SELECT COUNT(*) FROM d2_attempts WHERE task_id = ? AND kind = 'MODEL'", (task_id,)
                    ).fetchone()[0])
                checkpoint_ready = checkpoint_path.is_file() and checkpoint_path.stat().st_size > 0
                if run and run["status"] == "RUNNING" and model_attempts >= 1 and checkpoint_ready:
                    _write(log_paths["restart"], {
                        "case": "OPS-01", "phase": "before_kill", "pid": server.pid,
                        "task_id": task_id, "run_id": run_id_value, "run_status": run["status"],
                        "model_attempts_reserved": model_attempts,
                        "checkpoint_bytes": checkpoint_path.stat().st_size,
                    })
                    _kill_process_tree(server)
                    process_restart_observed = True
                    break
                if run and run["status"] in {"WAITING_APPROVAL", "WAITING_INPUT", "BLOCKED", "FAILED"}:
                    break
                time.sleep(0.02)
            if process_restart_observed:
                server_output.flush()
                server = _start_server(port, environment, server_output)
                recovery_deadline = time.monotonic() + args.completion_timeout_seconds
                recovery_started = time.monotonic()
                interrupted_event_seen = False
                final_status = None
                while time.monotonic() < recovery_deadline:
                    with connect(db_path) as connection:
                        run = connection.execute(
                            "SELECT status, blocked_reason FROM task_runs WHERE run_id = ?", (run_id_value,)
                        ).fetchone()
                        interrupted_event_seen = connection.execute(
                            "SELECT 1 FROM domain_outbox WHERE source_kind = 'RUN' AND source_id = ? AND event_kind = 'RUN_STATUS_INTERRUPTED_RECOVERABLE' LIMIT 1",
                            (run_id_value,),
                        ).fetchone() is not None
                    final_status = str(run["status"]) if run else None
                    if final_status in {"WAITING_APPROVAL", "WAITING_INPUT", "BLOCKED", "FAILED", "SUCCEEDED"}:
                        break
                    if final_status == "INTERRUPTED_RECOVERABLE" and time.monotonic() - recovery_started > 8:
                        break
                    time.sleep(0.1)
                _write(log_paths["restart"], {
                    "case": "OPS-01", "phase": "after_restart", "pid": server.pid,
                    "task_id": task_id, "run_id": run_id_value,
                    "interrupted_recoverable_event_seen": interrupted_event_seen,
                    "final_run_status": final_status,
                    "same_run_id_reused": True,
                    "checkpoint_bytes": checkpoint_path.stat().st_size if checkpoint_path.exists() else 0,
                })

            support.close()
            # Browser reconnection uses a fresh HTTP client with the same saved
            # cookie and CSRF token; no credential value is written to evidence.
            rejoined = httpx.Client(base_url=base, timeout=httpx.Timeout(5.0, read=10.0))
            if support_cookie:
                rejoined.cookies.set("opspilot_session", support_cookie, path="/api")
            rejoined_headers = {"Origin": origin, "X-CSRF-Token": csrf or ""}
            run_status = None
            task_view = None
            rejoin_started = time.monotonic()
            end = rejoin_started + args.completion_timeout_seconds
            while time.monotonic() < end:
                response = rejoined.get(f"/api/runs/{run_id_value}")
                if response.status_code == 200:
                    run_status = response.json()["status"]
                    if run_status in {"WAITING_APPROVAL", "WAITING_INPUT", "BLOCKED", "FAILED", "SUCCEEDED"}:
                        task_view = rejoined.get(f"/api/tasks/{task_id}").json()
                        break
                    if run_status == "INTERRUPTED_RECOVERABLE" and time.monotonic() - rejoin_started > 8:
                        task_view = rejoined.get(f"/api/tasks/{task_id}").json()
                        break
                time.sleep(0.1)
            if task_view is None:
                task_response_view = rejoined.get(f"/api/tasks/{task_id}")
                task_view = task_response_view.json() if task_response_view.status_code == 200 else {}
            final_events = rejoined.get(
                f"/api/sessions/{session_id}/events/history?after=0",
                headers={"Last-Event-ID": "0"},
            ).json().get("items", [])
            approver_task_view = approver.get(f"/api/tasks/{task_id}")
            _write(log_paths["sse"], {
                "case": "WEB-07", "client_reconnected_after_worker_run": True,
                "task_stream_disconnected_before_worker_completion": True,
                "run_id": run_id_value, "run_status": run_status,
                "task_status": task_view.get("status"),
                "approver_pending_task_read_status": approver_task_view.status_code,
                "replayed_event_count": len(final_events),
                "replayed_event_kinds": [item["event_kind"] for item in final_events],
            })

            snapshot = _attempt_snapshot(db_path, task_id)
            with connect(db_path) as connection:
                run_events = [str(row[0]) for row in connection.execute(
                    "SELECT event_kind FROM domain_outbox WHERE source_kind='RUN' AND source_id=? ORDER BY created_at, event_id",
                    (run_id_value,),
                ).fetchall()]
                tool_calls = connection.execute(
                    "SELECT COUNT(*) FROM d2_tool_observations WHERE task_id = ?", (task_id,)
                ).fetchone()[0]
                plan_count = int(connection.execute(
                    "SELECT COUNT(*) FROM d3_plans WHERE task_id = ?", (task_id,)
                ).fetchone()[0])
            required_tool_names = {item["tool_name"] for item in snapshot["mcp_observations"]}
            all_write_counts_zero = all(value == 0 for value in snapshot["business_write_counts"].values())
            _write(log_paths["model"], {
                "case": "WEB-07/REAL-MODEL-MCP-S1", "status": "PASS" if (
                    run_status == "WAITING_APPROVAL" and plan_count == 1 and tool_calls > 0
                    and bool(snapshot["model_traces"]) and all_write_counts_zero
                ) else "FAIL",
                "task_id": task_id, "run_id": run_id_value,
                "run_status": run_status, "task_status": task_view.get("status"),
                "pending_plan": task_view.get("pending_plan"),
                "plan_count": plan_count,
                "model_attempts_and_traces": snapshot["attempts"],
                "model_traces": snapshot["model_traces"],
                "mcp_tool_names_seen": sorted(required_tool_names),
                "mcp_observations": snapshot["mcp_observations"],
                "mcp_tool_observation_count": int(tool_calls),
                "evidence_summaries": snapshot["evidence"],
                "run_event_kinds": run_events,
                "business_write_counts": snapshot["business_write_counts"],
                "worker_process_restart_observed": process_restart_observed,
                "initial_user_message_is_not_claimed_as_model_context": True,
            })
            if not process_restart_observed or run_status != "WAITING_APPROVAL" or not all_write_counts_zero:
                return 1
            return 0
        finally:
            support.close()
            approver.close()
            other.close()
    finally:
        if server is not None and server.poll() is None:
            _kill_process_tree(server)
        server_output.flush()
        server_output.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Run fresh real-port M1-02 Web, SSE, worker and model smoke.")
    parser.add_argument("--evidence-dir", default="docs/evidence/vnext/m1-02")
    parser.add_argument("--restart-window-seconds", type=float, default=45.0)
    parser.add_argument("--completion-timeout-seconds", type=float, default=180.0)
    return _run(parser.parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
