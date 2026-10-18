from __future__ import annotations

import argparse
import json
import os
import secrets
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from opspilot.config import MODEL_API_KEY, MODEL_NAME, ROOT, load_local_environment
from opspilot.domain.database import connect, reset_fixture
from opspilot.smokes.m1_03 import (
    _browser_run,
    _database_evidence,
    _free_port,
    _kill,
    _server_environment,
    _start_api,
    _start_vite,
    _write_json,
)


def _case_id(browser: dict[str, Any], case: str) -> str:
    row = browser.get(case)
    if not isinstance(row, dict) or not row.get("task_id"):
        raise RuntimeError(f"Browser result omitted {case} task identity.")
    return str(row["task_id"])


def run(evidence_dir: Path) -> int:
    load_local_environment()
    evidence_dir.mkdir(parents=True, exist_ok=True)
    if not os.environ.get(MODEL_API_KEY) or not os.environ.get(MODEL_NAME):
        _write_json(evidence_dir / "RESULTS.json", {
            "status": "NOT_RUN", "reason": "MODEL_CONFIGURATION_MISSING",
            "api_key_present": bool(os.environ.get(MODEL_API_KEY)),
            "model_name_present": bool(os.environ.get(MODEL_NAME)),
            "base_url_present": bool(os.environ.get("OPSPILOT_MODEL_BASE_URL")),
        })
        return 2

    run_stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir = evidence_dir / "runs" / run_stamp
    screenshots = run_dir / "screenshots"
    logs = run_dir / "logs"
    screenshots.mkdir(parents=True, exist_ok=False)
    logs.mkdir(parents=True, exist_ok=True)
    runtime = ROOT / ".runtime" / "m1-04-smokes" / run_stamp
    runtime.mkdir(parents=True, exist_ok=False)
    db_path, checkpoint_path = runtime / "domain.sqlite3", runtime / "checkpoints.sqlite3"
    reset_fixture(db_path, "S1_POS")
    passwords = {actor: secrets.token_urlsafe(24) for actor in (
        "support-a", "approver-a", "support-b", "approver-b",
    )}
    api_port, ui_port, attack_port = _free_port(), _free_port(), _free_port()
    api_origin = f"http://127.0.0.1:{api_port}"
    ui_origin = f"http://127.0.0.1:{ui_port}"
    attack_origin = f"http://127.0.0.1:{attack_port}"
    server_env = _server_environment(db_path, checkpoint_path, ui_origin, passwords)
    server = vite = attack_vite = None
    result: dict[str, Any] = {
        "run_stamp": run_stamp, "start_sha": "e73b691ab29dfc46bd79461623ba4e8159257e05",
        "model_id": os.environ.get(MODEL_NAME), "provider_configured": True,
        "browser": "Microsoft Edge", "fresh_domain_db": str(db_path.relative_to(ROOT)),
        "fresh_checkpoint_db": str(checkpoint_path.relative_to(ROOT)),
    }
    try:
        server = _start_api(api_port, server_env, logs / "api-server-first-process.log")
        vite = _start_vite(ui_port, api_origin, server_env, logs / "vite-server.log")
        attack_vite = _start_vite(attack_port, api_origin, server_env, logs / "unlisted-origin-vite.log")
        browser = _browser_run(
            mode="full", ui_origin=ui_origin, api_origin=api_origin, attack_origin=attack_origin,
            screenshots=screenshots, passwords=passwords, log_path=logs / "browser-full.txt",
            script_path=ROOT / "frontend" / "e2e" / "m1-04-browser.mjs",
        )
        result["browser_run"] = browser
        session_id = str(browser["session_id"])
        case_ids = {case: _case_id(browser, case) for case in ("nlD", "nlC", "nlA", "nlB")}

        process_one = int(server.pid)
        _kill(server)
        server = _start_api(api_port, server_env, logs / "api-server-after-restart.log")
        resumed = _browser_run(
            mode="resume", ui_origin=ui_origin, api_origin=api_origin, attack_origin=attack_origin,
            screenshots=screenshots, passwords=passwords, log_path=logs / "browser-after-restart.txt",
            session_id=session_id, task_id=case_ids["nlB"],
            script_path=ROOT / "frontend" / "e2e" / "m1-04-browser.mjs",
        )
        result["service_restart"] = {
            "prior_pid": process_one, "restart_pid": int(server.pid), "browser_resume": resumed,
        }
        result["case_evidence"] = {
            case: _database_evidence(db_path, session_id, task_id)
            for case, task_id in case_ids.items()
        }
        with connect(db_path) as connection:
            config = connection.execute(
                "SELECT credential_ref, config_version FROM integrations WHERE tenant_id = 'tenant-a' AND integration_id = 'integration-a'"
            ).fetchone()
            total_action_counts = {
                table: int(connection.execute(
                    f"SELECT COUNT(*) FROM {table} WHERE task_id IN (?, ?, ?, ?)",
                    tuple(case_ids.values()),
                ).fetchone()[0])
                for table in (
                    "d3_approvals", "d3_action_permissions", "d3_action_intents", "d3_action_ledgers",
                    "d3_verification_receipts", "d3_report_artifacts", "d3_delivery_records",
                )
            }
        cases = result["case_evidence"]
        nl_c = cases["nlC"]
        nl_a = cases["nlA"]
        nl_b = cases["nlB"]
        nl_d = cases["nlD"]
        actual_fact_types = {str(item["fact_type"]) for item in nl_a["evidence"]}
        nl_a_probe = next((item for item in nl_a["evidence"] if item["fact_type"] == "endpoint_probe"), None)
        nl_d_run = next((item for item in nl_d["runs"] if item["run_id"] == browser["nlD"]["run_id"]), None)
        result["business_state_after_browser"] = {
            "integration": {key: config[key] for key in config.keys()} if config else None,
            "action_counts_across_nl_tasks": total_action_counts,
        }
        result["checks"] = {
            "NL-01_initial_message_in_real_investigator_prompt": bool(browser["nlA"].get("message_id"))
                and bool(browser["nlA"].get("run_id"))
                and any(item["kind"] == "INITIAL_SYMPTOM" for item in browser["nlA"].get("context", {}).get("selected_input_messages", [])),
            "NL-02_same_binding_distinct_real_prompt": bool(browser.get("inputContrast", {}).get("distinctPromptDigest"))
                and bool(browser.get("inputContrast", {}).get("sameTrustedBinding"))
                and actual_fact_types == {"integration_config", "principal_status", "auth_policy", "endpoint_probe"}
                and {str(item["fact_type"]) for item in nl_b["evidence"]} == actual_fact_types,
            "NL-03_403_scope_change_fails_closed": browser["nlD"].get("status") == "WAITING_INPUT"
                and browser["nlD"].get("waiting_reason") == "S1_SCOPE_CHANGE_UNSUPPORTED"
                and not nl_d["investigation_model_traces"] and not nl_d["evidence"],
            "NL-04_correction_applied_and_old_plan_invalidated": bool(browser["nlC"].get("correction_message_id"))
                and bool(browser["nlC"].get("correction_run_id"))
                and all(item.get("message_id") in {
                    browser["nlC"].get("initial_message_id"), browser["nlC"].get("correction_message_id"),
                } for item in browser["nlC"].get("selected_input_messages", []))
                and browser["nlC"].get("old_plan_eligibility") != "ACTIVE",
            "NL-05_task_control_and_plan_race_regressions": None,
            "NL-06_CHAT_READONLY_preserved_boundary": bool(browser.get("readOnlyBoundary", {}).get("unchanged")),
            "NL-07_real_provider_mcp_http_and_gate": bool(nl_a["investigation_model_traces"])
                and all(bool(row.get("provider_response_id")) for row in nl_a["investigation_model_traces"])
                and len(nl_a["evidence"]) >= 4 and nl_a_probe is not None
                and nl_a_probe["facts"].get("http_status") == 401
                and browser["nlA"].get("current_gate", {}).get("decision") == "READY",
            "NL-08_browser_reload_sse_and_process_restart": bool(browser.get("streamRecovery", {}).get("finalAnswerRecovered"))
                and bool(resumed.get("persistence", {}).get("labelRecovered"))
                and int(resumed.get("persistence", {}).get("status", 0)) == 200,
            "NL-09_permissions_budgets_and_legacy_regressions": browser.get("crossTenantStatus") == 404
                and browser.get("approverInspectorStatus") == 200
                and all(value == 0 for value in total_action_counts.values())
                and nl_d_run is not None,
        }
        browser_checks = {key: value for key, value in result["checks"].items() if key != "NL-05_task_control_and_plan_race_regressions"}
        result["status"] = "BROWSER_PASS_FULL_PYTEST_PENDING" if all(value is True for value in browser_checks.values()) else "FAIL"
        result["runtime"] = {"worker_first_pid": process_one, "worker_restart_pid": int(server.pid)}
        _write_json(run_dir / "RESULTS.json", result)
        _write_json(evidence_dir / "RESULTS.json", result)
        return 0 if result["status"] == "BROWSER_PASS_FULL_PYTEST_PENDING" else 1
    except Exception as error:
        result.update({"status": "FAIL", "error_class": type(error).__name__, "error": str(error)})
        _write_json(run_dir / "RESULTS.json", result)
        _write_json(evidence_dir / "RESULTS.json", result)
        raise
    finally:
        _kill(attack_vite)
        _kill(vite)
        _kill(server)


def main() -> int:
    parser = argparse.ArgumentParser(description="Fresh M1-04 real Provider, MCP, HTTP, and Microsoft Edge acceptance run.")
    parser.add_argument("--evidence-dir", default="docs/evidence/vnext/m1-04")
    args = parser.parse_args()
    evidence_dir = Path(args.evidence_dir)
    if not evidence_dir.is_absolute():
        evidence_dir = ROOT / evidence_dir
    return run(evidence_dir)


if __name__ == "__main__":
    raise SystemExit(main())
