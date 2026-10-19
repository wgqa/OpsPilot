from __future__ import annotations

import argparse
import json
import os
import secrets
import shutil
import subprocess
import sys
import traceback
from datetime import datetime, timezone
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

from opspilot.config import MODEL_API_KEY, MODEL_NAME, ROOT, load_local_environment
from opspilot.domain.database import connect, get_auth_event, reset_fixture
from opspilot.domain.d2 import get_task_binding
from opspilot.domain.s2_diagnosis import get_s2_task_outcome
from opspilot.smokes import m2_02_g4
from opspilot.smokes.m1_03 import _free_port, _kill, _server_environment, _start_api, _start_vite, _write_json


def _rows(path: Path, query: str, params: tuple[object, ...]) -> list[dict[str, Any]]:
    with connect(path) as connection:
        return [dict(row) for row in connection.execute(query, params).fetchall()]


def _probe_for_task(db_path: Path, task_id: str) -> dict[str, object]:
    binding = get_task_binding(db_path, task_id)
    request = m2_02_g4._live_request(db_path)
    event_id = request.get("authn_event_id")
    event = get_auth_event(db_path, str(binding["tenant_id"]), int(event_id)) if event_id else None
    matches = bool(
        event
        and event.get("service_id") == binding["service_id"]
        and event.get("integration_id") == binding["integration_id"]
        and event.get("principal_id") == binding["principal_id"]
        and event.get("route") == request.get("route")
        and event.get("result_code") == "AUTH_ACCEPTED"
    )
    return {**request, "binding_matches": matches}


def _snapshot(db_path: Path, task_id: str) -> dict[str, object]:
    with connect(db_path) as connection:
        task = connection.execute(
            "SELECT tenant_id, status, service_id, integration_id, principal_id FROM task_bindings WHERE task_id = ?",
            (task_id,),
        ).fetchone()
        control = connection.execute(
            "SELECT control_revision, terminal_state, pending_critical_message_seq, applied_critical_message_seq "
            "FROM task_controls WHERE task_id = ?", (task_id,),
        ).fetchone()
        if task is None or control is None:
            raise ValueError("Task snapshot requires a persisted TaskBinding and TaskControl.")
        tables = {
            str(row["name"]) for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
        counts: dict[str, int] = {}
        for table in (
            "principal_scope_grants", "route_scope_policies", "d3_approvals", "d3_action_permissions",
            "d3_action_intents", "d3_action_ledgers", "d3_verification_receipts", "d3_report_artifacts",
            "d3_delivery_records", "s2_gate_traces", "s2_diagnosis_receipts", "s2_handoff_drafts",
            "s2_handoff_receipts", "s2_handoff_queue",
        ):
            if table in tables:
                columns = {str(row["name"]) for row in connection.execute(f"PRAGMA table_info({table})").fetchall()}
                if "task_id" in columns:
                    row = connection.execute(f"SELECT COUNT(*) FROM {table} WHERE task_id = ?", (task_id,)).fetchone()
                elif "tenant_id" in columns:
                    row = connection.execute(f"SELECT COUNT(*) FROM {table} WHERE tenant_id = ?", (task["tenant_id"],)).fetchone()
                else:
                    row = connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
                counts[table] = int(row[0])
        business_runs = [
            {"run_id": str(row["run_id"]), "kind": str(row["kind"]), "status": str(row["status"])}
            for row in connection.execute(
                "SELECT run_id, kind, status FROM task_runs WHERE task_id = ? AND kind <> 'CHAT_READONLY' "
                "ORDER BY created_at, run_id", (task_id,),
            ).fetchall()
        ]
        d2_attempts = [
            {"run_id": str(row["run_id"]) if row["run_id"] else None,
             "kind": str(row["kind"]), "tool_name": str(row["tool_name"]) if row["tool_name"] else None,
             "status": str(row["status"])}
            for row in connection.execute(
                "SELECT run_id, kind, tool_name, status FROM d2_attempts WHERE task_id = ? ORDER BY rowid",
                (task_id,),
            ).fetchall()
        ]
    outcome = get_s2_task_outcome(db_path, task_id)
    return {
        "task": {key: task[key] for key in task.keys()},
        "task_control": {key: control[key] for key in control.keys()},
        "business_runs": business_runs,
        "d2_attempts": d2_attempts,
        "protected_table_counts": counts,
        "s2_projection": {
            "business_outcome": outcome.get("business_outcome"),
            "currentness": outcome.get("currentness"),
            "receipt_id": (outcome.get("diagnosis_receipt") or {}).get("receipt_id"),
            "draft_id": (outcome.get("draft") or {}).get("draft_id"),
            "submitted": outcome.get("submitted"),
            "scope_authorized": outcome.get("scope_authorized"),
        },
    }


def _fixture_scope_counts(db_path: Path) -> dict[str, int]:
    result: dict[str, int] = {}
    with connect(db_path) as connection:
        tables = {str(row["name"]) for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()}
        for table in (
            "principal_scope_grants", "route_scope_policies", "s2_handoff_receipts", "s2_handoff_queue",
        ):
            if table in tables:
                result[table] = int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
    return result


def _trace_bundle(db_path: Path, task_id: str, corrected_run_id: str, session_id: str) -> dict[str, object]:
    model_calls = _rows(db_path, """
        SELECT t.call_id, a.run_id, t.model_id, t.provider_response_id, t.prompt_digest,
               t.status, t.usage_json, t.tool_calls_json
        FROM d2_model_traces t JOIN d2_attempts a ON a.attempt_id = t.attempt_id
        WHERE t.task_id = ? ORDER BY t.rowid
    """, (task_id,))
    observations = _rows(db_path, """
        SELECT o.observation_id, o.tool_name, o.status, o.progress_added, o.evidence_id,
               o.result_digest, o.created_at, a.run_id, o.result_json
        FROM d2_tool_observations o LEFT JOIN d2_attempts a ON a.attempt_id = o.attempt_id
        WHERE o.task_id = ? ORDER BY o.rowid
    """, (task_id,))
    evidence = _rows(db_path, """
        SELECT e.evidence_id, e.fact_type, e.fetched_at, e.observed_versions_json, e.facts_json,
               e.trust_class, a.run_id, o.created_at AS observation_at, o.tool_name
        FROM d2_evidence e JOIN d2_tool_observations o ON o.evidence_id = e.evidence_id
        JOIN d2_attempts a ON a.attempt_id = o.attempt_id
        WHERE e.task_id = ? AND a.run_id = ? AND o.status = 'OK'
        ORDER BY o.rowid
    """, (task_id, corrected_run_id))
    gate_traces = _rows(db_path, """
        SELECT trace_id, run_id, decision, reason_code, request_id, decision_id,
               evidence_ids_json, evidence_digests_json, predicate_json, created_at
        FROM s2_gate_traces WHERE task_id = ? ORDER BY rowid
    """, (task_id,))
    receipts = _rows(db_path, """
        SELECT receipt_id, run_id, request_id, decision_id, evidence_ids_json, evidence_digests_json, created_at
        FROM s2_diagnosis_receipts WHERE task_id = ? ORDER BY created_at, receipt_id
    """, (task_id,))
    drafts = _rows(db_path, """
        SELECT draft_id, receipt_id, version, content_digest, created_at
        FROM s2_handoff_drafts WHERE task_id = ? ORDER BY version
    """, (task_id,))
    chat_attempts = _rows(db_path, """
        SELECT attempt_id, run_id, attempt_no, model_id, status, provider_response_id,
               input_tokens, output_tokens, total_tokens, error_class, created_at, completed_at
        FROM chat_attempts WHERE task_id = ? ORDER BY created_at, attempt_id
    """, (task_id,))
    outbox = _rows(db_path, """
        SELECT event_id, task_id, session_id, source_kind, source_id, event_kind, created_at
        FROM domain_outbox WHERE task_id = ? OR session_id = ? ORDER BY created_at, event_id
    """, (task_id, session_id))
    session_events = _rows(db_path, """
        SELECT event_id, session_id, event_seq AS sequence, event_kind, source_kind, source_id,
               happened_at AS created_at
        FROM session_events WHERE session_id = ? ORDER BY event_seq
    """, (session_id,))
    for row in model_calls:
        row["usage"] = json.loads(str(row.pop("usage_json")))
        row["tool_calls"] = json.loads(str(row.pop("tool_calls_json")))
    for row in observations:
        row["result"] = json.loads(str(row.pop("result_json"))) if row.get("result_json") else None
    for row in evidence:
        row["observed_versions"] = json.loads(str(row.pop("observed_versions_json")))
        row["facts"] = json.loads(str(row.pop("facts_json")))
    for row in gate_traces:
        row["evidence_ids"] = json.loads(str(row.pop("evidence_ids_json")))
        row["evidence_digests"] = json.loads(str(row.pop("evidence_digests_json")))
        row["predicate"] = json.loads(str(row.pop("predicate_json")))
    for row in receipts:
        row["evidence_ids"] = json.loads(str(row.pop("evidence_ids_json")))
        row["evidence_digests"] = json.loads(str(row.pop("evidence_digests_json")))
    return {
        "model_calls": model_calls,
        "mcp_observations": observations,
        "corrected_run_evidence": evidence,
        "gate_traces": gate_traces,
        "diagnosis_receipts": receipts,
        "handoff_drafts": drafts,
        "chat_attempts": chat_attempts,
        "domain_outbox": outbox,
        "session_events": session_events,
    }


def _version_or_missing(name: str) -> str | None:
    try:
        return version(name)
    except PackageNotFoundError:
        return None


def run_browser(evidence_dir: Path) -> int:
    load_local_environment()
    evidence_dir.mkdir(parents=True, exist_ok=True)
    if not os.environ.get(MODEL_API_KEY) or not os.environ.get(MODEL_NAME):
        _write_json(evidence_dir / "RESULTS.json", {
            "status": "NOT_RUN", "reason": "MODEL_CONFIGURATION_MISSING",
            "api_key_present": bool(os.environ.get(MODEL_API_KEY)),
            "model_name_present": bool(os.environ.get(MODEL_NAME)),
        })
        return 2
    node = shutil.which("node")
    if not node:
        _write_json(evidence_dir / "RESULTS.json", {"status": "NOT_RUN", "reason": "NODEJS_MISSING"})
        return 2

    run_stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    runtime = ROOT / ".runtime" / "m2-02-hf-01-browser" / run_stamp
    screenshots, logs = evidence_dir / "screenshots", evidence_dir / "logs"
    runtime.mkdir(parents=True, exist_ok=False)
    screenshots.mkdir(parents=True, exist_ok=False)
    logs.mkdir(parents=True, exist_ok=True)
    db_path, checkpoint_path = runtime / "domain.sqlite3", runtime / "checkpoints.sqlite3"
    reset_fixture(db_path, "S2_SCOPE_DENIED")
    fixture_scope_counts = _fixture_scope_counts(db_path)
    passwords = {actor: secrets.token_urlsafe(24) for actor in (
        "support-a", "approver-a", "support-b", "approver-b",
    )}
    api_port, ui_port = _free_port(), _free_port()
    api_origin, ui_origin = f"http://127.0.0.1:{api_port}", f"http://127.0.0.1:{ui_port}"
    server_env = _server_environment(db_path, checkpoint_path, ui_origin, passwords)
    runtime_facts = {key: os.environ.get(key) for key in (
        "PATH", "SYSTEMROOT", "WINDIR", "PATHEXT", "COMSPEC", "USERPROFILE", "LOCALAPPDATA",
        "APPDATA", "ProgramFiles", "ProgramFiles(x86)", "PROGRAMFILES", "PROGRAMFILES(X86)", "TEMP", "TMP",
    ) if os.environ.get(key)}
    vite_env = {**runtime_facts, "PYTHONUTF8": "1"}
    server = vite = None
    git_sha = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True,
        text=True, encoding="utf-8", check=True,
    ).stdout.strip()
    result: dict[str, Any] = {
        "status": "RUNNING",
        "run_stamp": run_stamp,
        "model_id": os.environ.get(MODEL_NAME),
        "provider_configured": True,
        "browser": "Microsoft Edge",
        "domain_db": str(db_path.relative_to(ROOT)),
        "checkpoint_db": str(checkpoint_path.relative_to(ROOT)),
        "implementation_sha": git_sha,
        "dependencies": {
            name: _version_or_missing(name)
            for name in ("langgraph", "langchain-openai", "mcp", "fastapi", "pydantic")
        },
    }
    try:
        server = _start_api(api_port, server_env, logs / "api-server.log")
        vite = _start_vite(ui_port, api_origin, vite_env, logs / "vite-server.log")
        browser_env = {
            **runtime_facts,
            "PYTHONUTF8": "1",
            "OPSPILOT_UI_BASE_URL": ui_origin,
            "OPSPILOT_EVIDENCE_SCREENSHOTS": str(screenshots),
            "OPSPILOT_E2E_SUPPORT_PASSWORD": passwords["support-a"],
            "OPSPILOT_E2E_PYTHON": sys.executable,
            "OPSPILOT_E2E_REPO_ROOT": str(ROOT),
            "OPSPILOT_DB_PATH": str(db_path),
        }
        browser_script = ROOT / "frontend" / "e2e" / "m2-02-hf-01-browser.mjs"
        completed = subprocess.run(
            [node, str(browser_script)], cwd=ROOT / "frontend", env=browser_env,
            capture_output=True, text=True, encoding="utf-8", timeout=900,
        )
        stdout, stderr = completed.stdout, completed.stderr
        for password in passwords.values():
            stdout, stderr = stdout.replace(password, "[REDACTED_TEST_PASSWORD]"), stderr.replace(password, "[REDACTED_TEST_PASSWORD]")
        log_text = f"exit_code={completed.returncode}\nstdout:\n{stdout}\nstderr:\n{stderr}"
        (logs / "browser-run.txt").write_text(log_text, encoding="utf-8")
        if completed.returncode != 0:
            raise RuntimeError(f"Real Microsoft Edge smoke failed with exit code {completed.returncode}; see logs/browser-run.txt.")
        lines = [line for line in stdout.splitlines() if line.strip()]
        if not lines:
            raise RuntimeError("Real Microsoft Edge smoke emitted no result record.")
        browser_result = json.loads(lines[-1])
        corrected_run_id = str(browser_result["correction"]["run_id"])
        task_id = str(browser_result["task_id"])
        session_id = str(browser_result["session_id"])
        final_snapshot = _snapshot(db_path, task_id)
        current_scope_counts = _fixture_scope_counts(db_path)
        final_scope_counts = {
            key: current_scope_counts.get(key, 0) for key in fixture_scope_counts
        }
        if final_scope_counts != fixture_scope_counts:
            raise RuntimeError("S2 Web journey wrote a fixture Scope/Grant/Policy or Handoff table.")
        result.update({
            "status": "PASS",
            "fixture_scope_counts_before": fixture_scope_counts,
            "fixture_scope_counts_after": final_scope_counts,
            "final_domain_snapshot": final_snapshot,
            "browser_trace": browser_result,
            "domain_trace": _trace_bundle(db_path, task_id, corrected_run_id, session_id),
        })
        _write_json(evidence_dir / "RESULTS.json", result)
        return 0
    except Exception as error:
        result.update({"status": "FAIL", "error_class": type(error).__name__, "error": str(error)})
        _write_json(evidence_dir / "RESULTS.json", result)
        (logs / "failure-traceback.txt").write_text(traceback.format_exc(), encoding="utf-8")
        raise
    finally:
        _kill(vite)
        _kill(server)


def main() -> int:
    parser = argparse.ArgumentParser(description="Fresh HF-01 Web/MCP/Provider correction and read-only follow-up smoke.")
    parser.add_argument("--evidence-dir", type=Path)
    parser.add_argument("--probe-only", action="store_true")
    parser.add_argument("--snapshot-only", action="store_true")
    parser.add_argument("--db", type=Path)
    parser.add_argument("--task-id")
    args = parser.parse_args()
    if args.probe_only:
        load_local_environment()
        if args.db is None or not args.task_id:
            parser.error("--probe-only requires --db and --task-id")
        print(json.dumps(_probe_for_task(args.db, args.task_id), ensure_ascii=False))
        return 0
    if args.snapshot_only:
        if args.db is None or not args.task_id:
            parser.error("--snapshot-only requires --db and --task-id")
        print(json.dumps(_snapshot(args.db, args.task_id), ensure_ascii=False))
        return 0
    evidence_dir = args.evidence_dir or ROOT / "docs" / "evidence" / "vnext" / "m2-02-hf-01" / "runs" / "browser"
    if not evidence_dir.is_absolute():
        evidence_dir = ROOT / evidence_dir
    return run_browser(evidence_dir)


if __name__ == "__main__":
    raise SystemExit(main())
