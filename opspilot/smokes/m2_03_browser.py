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
from opspilot.domain.database import connect, reset_fixture
from opspilot.smokes import m2_02_hf_01
from opspilot.smokes.m1_03 import _free_port, _kill, _server_environment, _start_api, _start_vite, _write_json


def _rows(db_path: Path, query: str, params: tuple[object, ...]) -> list[dict[str, Any]]:
    with connect(db_path) as connection:
        return [dict(row) for row in connection.execute(query, params).fetchall()]


def _trace_bundle(db_path: Path, task_id: str, session_id: str) -> dict[str, object]:
    model_calls = _rows(db_path, """
        SELECT t.call_id, a.run_id, t.model_id, t.provider_response_id, t.prompt_digest,
               t.status, t.usage_json, t.tool_calls_json
        FROM d2_model_traces t JOIN d2_attempts a ON a.attempt_id = t.attempt_id
        WHERE t.task_id = ? ORDER BY t.rowid
    """, (task_id,))
    observations = _rows(db_path, """
        SELECT o.observation_id, o.call_id, o.tool_name, o.status, o.progress_added,
               o.evidence_id, o.result_digest, o.result_json, o.created_at, a.run_id
        FROM d2_tool_observations o LEFT JOIN d2_attempts a ON a.attempt_id = o.attempt_id
        WHERE o.task_id = ? ORDER BY o.rowid
    """, (task_id,))
    evidence = _rows(db_path, """
        SELECT evidence_id, fact_type, fetched_at, observed_versions_json, facts_json,
               trust_class, digest FROM d2_evidence WHERE task_id = ? ORDER BY rowid
    """, (task_id,))
    gates = _rows(db_path, """
        SELECT trace_id, run_id, decision, reason_code, request_id, decision_id,
               evidence_ids_json, evidence_digests_json, predicate_json, created_at
        FROM s2_gate_traces WHERE task_id = ? ORDER BY rowid
    """, (task_id,))
    receipts = _rows(db_path, """
        SELECT receipt_id, run_id, request_id, decision_id, evidence_ids_json,
               evidence_digests_json, observed_versions_json, created_at
        FROM s2_diagnosis_receipts WHERE task_id = ? ORDER BY rowid
    """, (task_id,))
    drafts = _rows(db_path, """
        SELECT draft_id, receipt_id, version, content_digest, content_json, created_at
        FROM s2_handoff_drafts WHERE task_id = ? ORDER BY version
    """, (task_id,))
    queue = _rows(db_path, """
        SELECT entry_id, handoff_kind, receiver_queue_id, receiver_identity_ref, draft_id,
               draft_version, draft_digest, received_at, review_due_at, queue_status
        FROM s2_handoff_queue_entries WHERE task_id = ? ORDER BY received_at
    """, (task_id,))
    handoff_receipts = _rows(db_path, """
        SELECT receipt_id, entry_id, draft_id, draft_version, draft_digest, operation_id,
               canonical_request_digest, accepted_by_receiver_ref, accepted_by_actor_id,
               accepted_at, receipt_digest, control_revision, request_id, decision_id,
               credential_policy_version, scope_policy_version, grant_version
        FROM s2_handoff_receipts WHERE task_id = ? ORDER BY accepted_at
    """, (task_id,))
    commands = _rows(db_path, """
        SELECT command_id, command_kind, target_ref, idempotency_key, request_digest,
               accepted_at, accepted_status, error_code, result_json
        FROM commands WHERE target_ref LIKE ? ORDER BY accepted_at, command_id
    """, (f"{task_id}:%",))
    outbox = _rows(db_path, """
        SELECT event_id, source_kind, source_id, event_kind, payload_json, created_at
        FROM domain_outbox WHERE task_id = ? AND source_kind = 'S2_HANDOFF_RECEIPT'
        ORDER BY created_at, event_id
    """, (task_id,))
    chat_attempts = _rows(db_path, """
        SELECT attempt_id, run_id, attempt_no, model_id, status, provider_response_id,
               input_tokens, output_tokens, total_tokens, error_class, created_at, completed_at
        FROM chat_attempts WHERE task_id = ? ORDER BY created_at, attempt_id
    """, (task_id,))
    session_events = _rows(db_path, """
        SELECT event_id, event_seq AS sequence, event_kind, source_kind, source_id, happened_at
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
    for row in gates:
        for source, target in (("evidence_ids_json", "evidence_ids"),
                               ("evidence_digests_json", "evidence_digests"),
                               ("predicate_json", "predicate")):
            row[target] = json.loads(str(row.pop(source)))
    for row in receipts:
        for source, target in (("evidence_ids_json", "evidence_ids"),
                               ("evidence_digests_json", "evidence_digests"),
                               ("observed_versions_json", "observed_versions")):
            row[target] = json.loads(str(row.pop(source)))
    for row in drafts:
        row["content"] = json.loads(str(row.pop("content_json")))
    for row in outbox:
        row["payload"] = json.loads(str(row.pop("payload_json")))
    for row in commands:
        row["result"] = json.loads(str(row.pop("result_json")))
    return {
        "model_calls": model_calls, "mcp_observations": observations, "evidence": evidence,
        "gate_traces": gates, "diagnosis_receipts": receipts, "frozen_drafts": drafts,
        "queue_entries": queue, "handoff_receipts": handoff_receipts,
        "submit_commands": commands, "handoff_outbox": outbox,
        "chat_attempts": chat_attempts, "session_events": session_events,
    }


def _redact(text: str, secrets_to_redact: list[str]) -> str:
    for value in secrets_to_redact:
        if value:
            text = text.replace(value, "[REDACTED_LOCAL_TEST_SECRET]")
    return text


def _package_version(name: str) -> str | None:
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

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    runtime = ROOT / ".runtime" / "m2-03-browser" / stamp
    screenshots, logs = evidence_dir / "screenshots", evidence_dir / "logs"
    runtime.mkdir(parents=True, exist_ok=False)
    screenshots.mkdir(parents=True, exist_ok=False)
    logs.mkdir(parents=True, exist_ok=True)
    db_path, checkpoint_path = runtime / "domain.sqlite3", runtime / "checkpoints.sqlite3"
    reset_fixture(db_path, "S2_SCOPE_DENIED")
    scope_counts_before = m2_02_hf_01._fixture_scope_counts(db_path)
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
    server = vite = None
    git_sha = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True,
        text=True, encoding="utf-8", check=True,
    ).stdout.strip()
    result: dict[str, Any] = {
        "status": "RUNNING", "run_stamp": stamp, "implementation_sha": git_sha,
        "model_id": os.environ.get(MODEL_NAME), "provider_configured": True,
        "browser": "Microsoft Edge", "domain_db": str(db_path.relative_to(ROOT)),
        "checkpoint_db": str(checkpoint_path.relative_to(ROOT)),
        "dependencies": {name: _package_version(name) for name in (
            "langgraph", "langchain-openai", "mcp", "fastapi", "pydantic",
        )},
    }
    try:
        server = _start_api(api_port, server_env, logs / "api-server.log")
        vite = _start_vite(ui_port, api_origin, runtime_facts, logs / "vite-server.log")
        browser_env = {
            **runtime_facts, "PYTHONUTF8": "1", "OPSPILOT_UI_BASE_URL": ui_origin,
            "OPSPILOT_EVIDENCE_SCREENSHOTS": str(screenshots),
            "OPSPILOT_E2E_SUPPORT_PASSWORD": passwords["support-a"],
            "OPSPILOT_E2E_PYTHON": sys.executable, "OPSPILOT_E2E_REPO_ROOT": str(ROOT),
            "OPSPILOT_DB_PATH": str(db_path),
        }
        script = ROOT / "frontend" / "e2e" / "m2-03-browser.mjs"
        completed = subprocess.run(
            [node, str(script)], cwd=ROOT / "frontend", env=browser_env,
            capture_output=True, text=True, encoding="utf-8", timeout=1200,
        )
        raw = f"exit_code={completed.returncode}\nstdout:\n{completed.stdout}\nstderr:\n{completed.stderr}"
        (logs / "browser-run.txt").write_text(_redact(raw, list(passwords.values())), encoding="utf-8")
        if completed.returncode != 0:
            raise RuntimeError(f"Real Microsoft Edge M2-03 journey failed; see logs/browser-run.txt.")
        lines = [line for line in completed.stdout.splitlines() if line.strip()]
        if not lines:
            raise RuntimeError("Browser emitted no result record.")
        browser_trace = json.loads(lines[-1])
        task_id, session_id = str(browser_trace["task_id"]), str(browser_trace["session_id"])
        final_snapshot = m2_02_hf_01._snapshot(db_path, task_id)
        scope_counts_after = m2_02_hf_01._fixture_scope_counts(db_path)
        final_counts = {key: scope_counts_after.get(key, 0) for key in scope_counts_before}
        handoff = browser_trace["handoff"]
        counts_ok = (
            final_snapshot["protected_table_counts"].get("s2_handoff_queue_entries") == 1
            and final_snapshot["protected_table_counts"].get("s2_handoff_receipts") == 1
            and len(_rows(db_path, "SELECT event_id FROM domain_outbox WHERE task_id = ? AND source_kind = 'S2_HANDOFF_RECEIPT' AND event_kind = 'S2_HANDOFF_ACCEPTED'", (task_id,))) == 1
            and final_counts == scope_counts_before
            and final_snapshot["s2_projection"]["business_outcome"] == "SCOPE_ESCALATED"
            and final_snapshot["s2_projection"]["submitted"] is True
            and final_snapshot["s2_projection"]["scope_authorized"] is False
            and handoff["business_outcome"] == "SCOPE_ESCALATED"
            and handoff["scope_authorized"] is False
        )
        if not counts_ok:
            raise RuntimeError("Browser completion did not match atomic queue/receipt/outbox and zero Scope-write expectations.")
        result.update({
            "status": "PASS", "fixture_authorization_counts_before": scope_counts_before,
            "fixture_authorization_counts_after": final_counts, "final_domain_snapshot": final_snapshot,
            "browser_trace": browser_trace, "domain_trace": _trace_bundle(db_path, task_id, session_id),
        })
        _write_json(evidence_dir / "RESULTS.json", result)
        return 0
    except Exception as error:
        result.update({"status": "FAIL", "error_class": type(error).__name__, "error": str(error)})
        _write_json(evidence_dir / "RESULTS.json", result)
        (logs / "failure-traceback.txt").write_text(traceback.format_exc(), encoding="utf-8")
        raise
    finally:
        for log_path in (logs / "api-server.log", logs / "vite-server.log"):
            if log_path.is_file():
                log_path.write_text(_redact(log_path.read_text(encoding="utf-8", errors="replace"), list(passwords.values())), encoding="utf-8")
        _kill(vite)
        _kill(server)


def main() -> int:
    parser = argparse.ArgumentParser(description="Real Provider/MCP/Web M2-03 handoff journey with concurrent tabs and lost-response recovery.")
    parser.add_argument("--evidence-dir", type=Path)
    args = parser.parse_args()
    evidence_dir = args.evidence_dir or ROOT / "docs" / "evidence" / "vnext" / "m2-03" / "runs" / "browser"
    if not evidence_dir.is_absolute():
        evidence_dir = ROOT / evidence_dir
    return run_browser(evidence_dir)


if __name__ == "__main__":
    raise SystemExit(main())
