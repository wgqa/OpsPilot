from __future__ import annotations

"""Real Edge/DeepSeek/MCP M3-01 A-to-B approval and revocation journey."""

import argparse
import json
import os
import secrets
import shutil
import subprocess
import sys
import time
import traceback
from datetime import datetime, timezone
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

from opspilot.config import MODEL_NAME, ROOT, load_local_environment
from opspilot.domain.database import connect
from opspilot.smokes.m1_03 import _free_port, _kill, _server_environment, _start_api, _start_vite
from opspilot.smokes.m301_eval import _backup


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")


def _redact(text: str, secrets_to_remove: list[str]) -> str:
    for secret in secrets_to_remove:
        if secret:
            text = text.replace(secret, "[REDACTED_TEST_SECRET]")
    return text


def _package_version(name: str) -> str | None:
    try:
        return version(name)
    except PackageNotFoundError:
        return None


def _scope_snapshot(path: Path) -> list[dict[str, object]]:
    with connect(path) as connection:
        return [dict(row) for row in connection.execute(
            "SELECT tenant_id, principal_id, granted_scopes_json, grant_version FROM principal_scope_grants ORDER BY tenant_id, principal_id"
        ).fetchall()]


def run_web(source_db: str | Path, source_task_id: str, evidence_dir: str | Path) -> int:
    load_local_environment()
    output = Path(evidence_dir)
    if not output.is_absolute():
        output = ROOT / output
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    if not os.environ.get("OPSPILOT_MODEL_API_KEY") or not os.environ.get(MODEL_NAME):
        _write_json(output / "RESULTS.json", {"status": "NOT_RUN", "reason": "MODEL_CONFIGURATION_MISSING"})
        return 2
    node = shutil.which("node")
    if not node:
        _write_json(output / "RESULTS.json", {"status": "NOT_RUN", "reason": "NODEJS_MISSING"})
        return 2

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    runtime = ROOT / ".runtime" / "m301-web-chain" / stamp
    runtime.mkdir(parents=True, exist_ok=False)
    screenshots = output / "screenshots"
    logs = output / "logs"
    screenshots.mkdir(parents=True, exist_ok=True)
    logs.mkdir(parents=True, exist_ok=True)
    database = runtime / "domain.sqlite3"
    checkpoint = runtime / "checkpoints.sqlite3"
    source_path = Path(source_db)
    if not source_path.is_absolute():
        source_path = ROOT / source_path
    _backup(source_path.resolve(), database)
    with connect(database) as connection:
        connection.execute("BEGIN IMMEDIATE")
        connection.execute(
            "UPDATE integrations SET credential_ref = 'cred-v1', config_version = 7 WHERE tenant_id = 'tenant-a' AND integration_id = 'integration-a'"
        )
        connection.commit()
    scope_before = _scope_snapshot(database)
    passwords = {actor: secrets.token_urlsafe(32) for actor in ("support-a", "approver-a", "support-b", "approver-b")}
    api_port, ui_port = _free_port(), _free_port()
    api_origin = f"http://127.0.0.1:{api_port}"
    ui_origin = f"http://127.0.0.1:{ui_port}"
    server_env = _server_environment(database, checkpoint, ui_origin, passwords)
    server = vite = None
    result: dict[str, Any] = {
        "status": "RUNNING", "run_stamp": stamp, "git_head": subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True,
        ).stdout.strip(),
        "browser": "Microsoft Edge via Playwright", "model_id": os.environ.get(MODEL_NAME),
        "source_db": str(source_path.resolve()), "isolated_domain_db": str(database),
        "source_task_id": source_task_id,
        "dependencies": {name: _package_version(name) for name in (
            "langchain", "langchain-openai", "langgraph", "langgraph-checkpoint-sqlite", "mcp", "fastapi", "pydantic",
        )},
        "initial_target_fixture": {"credential_ref": "cred-v1", "config_version": 7},
    }
    try:
        server = _start_api(api_port, server_env, logs / "api-server.log")
        vite = _start_vite(ui_port, api_origin, server_env, logs / "vite-server.log")
        browser_env = os.environ.copy()
        browser_env.update({
            "OPSPILOT_UI_BASE_URL": ui_origin,
            "OPSPILOT_EVIDENCE_SCREENSHOTS": str(screenshots),
            "OPSPILOT_E2E_SUPPORT_PASSWORD": passwords["support-a"],
            "OPSPILOT_E2E_APPROVER_PASSWORD": passwords["approver-a"],
            "OPSPILOT_M301_SOURCE_TASK_ID": source_task_id,
        })
        browser_script = ROOT / "frontend" / "e2e" / "m3-01-browser.mjs"
        completed = subprocess.run(
            [node, str(browser_script)], cwd=ROOT / "frontend", env=browser_env,
            capture_output=True, text=True, encoding="utf-8", timeout=1200,
        )
        raw_log = f"exit_code={completed.returncode}\nstdout:\n{completed.stdout}\nstderr:\n{completed.stderr}"
        (logs / "browser-run.txt").write_text(_redact(raw_log, list(passwords.values())), encoding="utf-8")
        trace_path = screenshots / "BROWSER-TRACE.json"
        if not trace_path.is_file():
            raise RuntimeError("Browser did not produce BROWSER-TRACE.json; see logs/browser-run.txt.")
        browser_trace = json.loads(trace_path.read_text(encoding="utf-8"))
        if completed.returncode != 0 or browser_trace.get("status") != "PASS":
            raise RuntimeError("Real browser A-to-B lifecycle failed; see BROWSER-TRACE.json and logs/browser-run.txt.")

        target_id = str(browser_trace["target"]["task_id"])
        memory_id = str(browser_trace["source"]["memory_id"])
        with connect(database) as connection:
            memory = connection.execute("SELECT * FROM d5_memories WHERE memory_id = ?", (memory_id,)).fetchone()
            target = connection.execute("SELECT tenant_id, integration_id FROM task_bindings WHERE task_id = ?", (target_id,)).fetchone()
            repairs = int(connection.execute(
                "SELECT COUNT(*) FROM d3_action_ledgers WHERE task_id = ? AND action_kind = 'REPAIR'", (target_id,),
            ).fetchone()[0])
            deliveries = int(connection.execute(
                "SELECT COUNT(*) FROM d3_action_ledgers WHERE task_id = ? AND action_kind = 'DELIVER'", (target_id,),
            ).fetchone()[0])
        scope_after = _scope_snapshot(database)
        probe_401 = any(
            item.get("fact_type") == "endpoint_probe" and item.get("facts", {}).get("http_status") == 401
            for item in browser_trace["target"].get("current_evidence", [])
        )
        passed = bool(
            target and memory and str(target["tenant_id"]) == "tenant-a"
            and target_id != source_task_id
            and str(memory["source_task_id"]) == source_task_id
            and str(memory["state"]) == "REVOKED"
            and probe_401
            and repairs == 0 and deliveries == 0
            and scope_before == scope_after
            and browser_trace["approval"]["confirmed_by"] == "approver-a"
            and browser_trace["revocation"]["revoked_by"] == "approver-a"
            and browser_trace["after_revocation"]["memory_refs"] == []
            and len(list(screenshots.glob("0*.png"))) == 8
        )
        result.update({
            "status": "PASS" if passed else "FAIL",
            "browser_trace": browser_trace,
            "domain_checks": {
                "source_task_id": source_task_id, "target_task_id": target_id,
                "cross_task": source_task_id != target_id,
                "memory_final_state": str(memory["state"]) if memory else None,
                "memory_source_task_id": str(memory["source_task_id"]) if memory else None,
                "target_current_http_401_evidence": probe_401,
                "target_repair_ledger_count": repairs,
                "target_delivery_ledger_count": deliveries,
                "scope_grants_unchanged": scope_before == scope_after,
                "scope_grants_before": scope_before, "scope_grants_after": scope_after,
                "post_revocation_model_memory_refs": browser_trace["after_revocation"].get("memory_refs"),
            },
        })
        _write_json(output / "RESULTS.json", result)
        return 0 if passed else 1
    except Exception as error:
        result.update({"status": "FAIL", "error_class": type(error).__name__, "error": str(error)[:500]})
        _write_json(output / "RESULTS.json", result)
        (logs / "failure-traceback.txt").write_text(traceback.format_exc(), encoding="utf-8")
        raise
    finally:
        for path in (logs / "api-server.log", logs / "vite-server.log"):
            if path.is_file():
                path.write_text(_redact(path.read_text(encoding="utf-8", errors="replace"), list(passwords.values())), encoding="utf-8")
        _kill(vite)
        _kill(server)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-db", required=True)
    parser.add_argument("--source-task-id", required=True)
    parser.add_argument("--evidence-dir", required=True)
    args = parser.parse_args()
    return run_web(args.source_db, args.source_task_id, args.evidence_dir)


if __name__ == "__main__":
    raise SystemExit(main())
