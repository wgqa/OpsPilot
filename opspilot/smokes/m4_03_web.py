"""Real Edge/API/Provider/MCP S3 correction, confirmed handoff and restart journey."""
from __future__ import annotations

import json
import os
import re
import secrets
import shutil
import signal
import socket
import subprocess
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from opspilot.config import ROOT, load_local_environment
from opspilot.domain.database import connect, reset_fixture
from opspilot.domain.s3 import prepare_s3_fixture
from opspilot.smokes.m1_03 import _kill, _server_environment
from opspilot.smokes.m4_01 import _free_port, _start_api, _start_vite
from opspilot.smokes.m4_02 import business_snapshot, trace, write_json

EVIDENCE = ROOT / "docs/evidence/vnext/m4-03"
SCRIPT = ROOT / "frontend/e2e/m4-03-s3-journey.mjs"


def _wait_stage(process: subprocess.Popen, stage_path: Path, expected: str, *, timeout: int = 600) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"Edge journey exited early with status {process.returncode}; inspect browser-run.log")
        try:
            value = json.loads(stage_path.read_text(encoding="utf-8"))
            if value.get("stage") == expected:
                return value
        except (OSError, ValueError):
            pass
        time.sleep(0.25)
    raise TimeoutError(f"Edge journey did not reach {expected}")


def _handoff_records(db: Path, task_id: str) -> dict[str, Any]:
    with connect(db) as connection:
        return {
            "queue_entries": [dict(row) for row in connection.execute(
                "SELECT * FROM s3_handoff_queue_entries WHERE task_id=?", (task_id,))],
            "receipts": [dict(row) for row in connection.execute(
                "SELECT * FROM s3_handoff_receipts WHERE task_id=?", (task_id,))],
            "commands": [dict(row) for row in connection.execute(
                "SELECT command_id,tenant_id,actor_id,command_kind,target_ref,idempotency_key,request_digest,accepted_status,result_json,accepted_at FROM commands WHERE command_kind='S3_HANDOFF_SUBMIT' AND target_ref LIKE ? ORDER BY accepted_at",
                (f"{task_id}:%",))],
            "outbox": [dict(row) for row in connection.execute(
                "SELECT event_id,event_kind,source_kind,source_id,payload_json,created_at FROM domain_outbox WHERE task_id=? AND event_kind='S3_HANDOFF_ACCEPTED'",
                (task_id,))],
            "task_status": connection.execute("SELECT status FROM task_bindings WHERE task_id=?", (task_id,)).fetchone()[0],
            "run_statuses": [dict(row) for row in connection.execute(
                "SELECT run_id,kind,status,source_message_id,control_revision_at_start,expected_control_revision,consumed_message_seq,applied_critical_message_seq FROM task_runs WHERE task_id=? ORDER BY rowid",
                (task_id,))],
        }


def _uvicorn_pid(log_path: Path) -> int:
    matches = re.findall(r"Started server process \[(\d+)\]", log_path.read_text(encoding="utf-8", errors="replace"))
    if not matches:
        raise RuntimeError(f"Uvicorn process id is missing from {log_path}")
    return int(matches[-1])


def _stop_api_process(process: subprocess.Popen, server_pid: int) -> None:
    """Stop the actual Uvicorn listener as well as its Python launcher on Windows."""
    if os.name == "nt":
        for pid in dict.fromkeys((server_pid, process.pid)):
            subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
    else:
        for pid in dict.fromkeys((server_pid, process.pid)):
            try:
                os.kill(pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
    try:
        process.wait(timeout=15)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)
    handle = getattr(process, "_opspilot_log_handle", None)
    if handle is not None and not handle.closed:
        handle.close()


def _wait_port_closed(port: int, timeout: float = 10) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.25):
                time.sleep(0.1)
        except OSError:
            return
    raise RuntimeError(f"API port {port} remained open after stopping its recorded Uvicorn process")


def main() -> int:
    load_local_environment()
    stamp = datetime.now(timezone.utc).strftime("web-%Y%m%dT%H%M%SZ")
    base = EVIDENCE / "runs" / stamp
    base.mkdir(parents=True, exist_ok=False)
    runtime = ROOT / ".runtime/m4-03/web" / stamp
    runtime.mkdir(parents=True, exist_ok=False)
    db, checkpoint = runtime / "domain.sqlite3", runtime / "checkpoints.sqlite3"
    reset_fixture(db, "S1_POS")
    initial_preparation = prepare_s3_fixture(db, "PROCESSING", order_id="async-order-2", contract_version=2)
    write_json(base / "PREPARATION-INITIAL.json", initial_preparation)
    passwords = {name: secrets.token_urlsafe(24) for name in ("support-a", "approver-a", "support-b", "approver-b")}
    api_port, ui_port = _free_port(), _free_port()
    api_origin, ui_origin = f"http://127.0.0.1:{api_port}", f"http://127.0.0.1:{ui_port}"
    env = _server_environment(db, checkpoint, ui_origin, passwords)
    api = vite = browser = None
    stage_path, signal_path, result_path = base / "JOURNEY-STAGE.json", base / "continue.signal", base / "JOURNEY.json"
    browser_env = os.environ.copy()
    browser_env.update({
        "OPSPILOT_M403_UI_URL": ui_origin,
        "OPSPILOT_M403_SUPPORT_PASSWORD": passwords["support-a"],
        "OPSPILOT_M403_SCREENSHOTS": str(base / "screenshots"),
        "OPSPILOT_M403_RESULT_PATH": str(result_path),
        "OPSPILOT_M403_STAGE_PATH": str(stage_path),
        "OPSPILOT_M403_SIGNAL_PATH": str(signal_path),
    })
    summary: dict[str, Any] = {"status": "FAIL"}
    try:
        api = _start_api(api_port, env, base / "api.log")
        vite = _start_vite(ui_port, api_origin, env, base / "vite.log")
        node = shutil.which("node")
        if not node:
            raise RuntimeError("Node.js is required for the real Edge journey")
        browser_log = (base / "browser-run.log").open("w", encoding="utf-8", newline="\n")
        browser = subprocess.Popen([node, str(SCRIPT)], cwd=ROOT / "frontend", env=browser_env,
                                   stdout=browser_log, stderr=subprocess.STDOUT)
        stage1 = _wait_stage(browser, stage_path, "FIRST_DIAGNOSIS_READY")
        write_json(base / "FIRST_DIAGNOSIS.json", stage1)
        external = prepare_s3_fixture(
            db, "DELIVERY_FAILED", order_id="async-order-2", contract_version=2,
            failure_code="TEMPORARY_UNAVAILABLE", attempt_count=3, max_attempts=3,
            retry_state="EXHAUSTED",
        )
        write_json(base / "EXTERNAL_PREPARATION-AFTER-FIRST-RUN.json", {
            "actor": "isolated acceptance harness, not Agent or end user",
            "reason": "change the test receiver/order state before a formal user correction",
            "old_run_result": stage1,
            "preparation_only": external,
        })
        agent_start_snapshot = business_snapshot(db)
        write_json(base / "BUSINESS-SNAPSHOT-AGENT-START.json", agent_start_snapshot)
        signal_path.write_text(json.dumps({"stage": "FACTS_PREPARED", "order_id": "async-order-2"}), encoding="utf-8")

        stage2 = _wait_stage(browser, stage_path, "HANDOFF_COMMITTED_WAIT_FOR_API_RESTART")
        write_json(base / "HANDOFF-BEFORE-RESTART.json", stage2)
        old_launcher_pid = api.pid
        old_server_pid = _uvicorn_pid(base / "api.log")
        _stop_api_process(api, old_server_pid)
        _wait_port_closed(api_port)
        api = _start_api(api_port, env, base / "api-restart.log")
        new_launcher_pid = api.pid
        new_server_pid = _uvicorn_pid(base / "api-restart.log")
        if old_server_pid == new_server_pid:
            raise RuntimeError("API restart reused the recorded Uvicorn process id")
        signal_path.unlink(missing_ok=True)
        signal_path.write_text(json.dumps({"stage": "API_RESTARTED", "old_launcher_pid": old_launcher_pid,
                                           "new_launcher_pid": new_launcher_pid,
                                           "old_server_pid": old_server_pid, "new_server_pid": new_server_pid}), encoding="utf-8")
        browser_return = browser.wait(timeout=600)
        browser_log.close()
        raw_browser_log = (base / "browser-run.log").read_text(encoding="utf-8", errors="replace")
        for password in passwords.values():
            raw_browser_log = raw_browser_log.replace(password, "[REDACTED_TEST_PASSWORD]")
        (base / "browser-run.log").write_text(raw_browser_log, encoding="utf-8")
        if browser_return != 0:
            raise RuntimeError(f"Microsoft Edge journey failed with exit code {browser_return}; inspect browser-run.log")
        journey = json.loads(result_path.read_text(encoding="utf-8"))
        task_id = str(journey["task_id"])
        raw_trace = trace(db, task_id)
        handoff = _handoff_records(db, task_id)
        after = business_snapshot(db)
        write_json(base / "TRACE.json", {"provider_mcp_http": raw_trace, "s3_handoff_transaction": handoff})
        unchanged = agent_start_snapshot == after
        write_json(base / "NO_AGENT_BUSINESS_MUTATION.json", {
            "baseline_after_external_test_preparation": agent_start_snapshot,
            "after_browser_agent_runs_and_handoff": after,
            "unchanged": unchanged,
        })
        if not unchanged:
            raise RuntimeError("S3 Agent run modified order/config/authorization/ticket business state")
        if len(handoff["queue_entries"]) != 1 or len(handoff["receipts"]) != 1 or len(handoff["outbox"]) != 1:
            raise RuntimeError("S3 handoff was not represented by exactly one queue entry/receipt/outbox event")
        if handoff["task_status"] != "COMPLETED":
            raise RuntimeError("Task did not reach its receipt-backed terminal state")
        if any(row.get("business_outcome") == "SCOPE_ESCALATED" for row in handoff["receipts"]):
            raise RuntimeError("S3 receipt improperly used S2 Scope Escalation semantics")
        summary = {
            "status": "PASS", "baseline": "main@f7c739f4e3d02988fc125b377dfa85a902bc2a0d",
            "browser": "Microsoft Edge real browser", "api_origin": api_origin, "ui_origin": ui_origin,
            "domain_db": str(db.relative_to(ROOT)), "checkpoint_db": str(checkpoint.relative_to(ROOT)),
            "task_id": task_id, "session_id": journey["session_id"], "selected_order": "async-order-2",
            "first_run_outcome": journey["first_diagnosis"]["outcome"],
            "correction_run": journey["critical_correction"]["run_id"],
            "corrected_outcome": journey["critical_correction"]["diagnosis"]["outcome"],
            "handoff_business_outcome": journey["handoff"]["business_outcome"],
            "receipt_id": journey["handoff"]["receipt_id"],
            "duplicate_browser_confirmation_replayed": journey["duplicate_confirmation"]["body"]["replayed"],
            "api_process_restart": {"old_launcher_pid": old_launcher_pid, "new_launcher_pid": new_launcher_pid,
                                    "old_server_pid": old_server_pid, "new_server_pid": new_server_pid},
            "followup_run": journey["followup"]["run_id"], "followup_answer": journey["followup"]["answer"],
            "handoff_records": {"queue_entries": len(handoff["queue_entries"]), "receipts": len(handoff["receipts"]),
                                "commands": len(handoff["commands"]), "outbox_events": len(handoff["outbox"]),
                                "task_status": handoff["task_status"]},
            "agent_did_not_write_order_or_security_configuration": unchanged,
            "evidence_dir": str(base.relative_to(ROOT)),
        }
    except Exception as error:
        (base / "FAILURE.txt").write_text("".join(traceback.format_exception(error)), encoding="utf-8")
        if result_path.exists():
            try:
                journey = json.loads(result_path.read_text(encoding="utf-8"))
                task_id = journey.get("task_id")
                if task_id:
                    write_json(base / "TRACE.json", {"provider_mcp_http": trace(db, str(task_id)),
                                                     "s3_handoff_transaction": _handoff_records(db, str(task_id))})
            except Exception:
                pass
        summary = {"status": "FAIL", "failure": str(error), "evidence_dir": str(base.relative_to(ROOT))}
    finally:
        _kill(api)
        _kill(vite)
        if browser is not None and browser.poll() is None:
            browser.kill()
        try:
            if "browser_log" in locals() and not browser_log.closed:
                browser_log.close()
        except Exception:
            pass
        for password in passwords.values():
            for logfile in (base / "api.log", base / "api-restart.log", base / "vite.log", base / "browser-run.log"):
                if logfile.exists():
                    content = logfile.read_text(encoding="utf-8", errors="replace").replace(password, "[REDACTED_TEST_PASSWORD]")
                    logfile.write_text(content, encoding="utf-8")
    write_json(base / "RESULTS.json", summary)
    print(json.dumps(summary, ensure_ascii=False), flush=True)
    return 0 if summary["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
