from __future__ import annotations

import json
import os
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from opspilot.domain.api import make_server
from opspilot.domain.d2 import (
    evaluate_evidence_gate,
    get_auth_policy_fact,
    get_integration_config_fact,
    get_principal_status_fact,
    probe_endpoint_fact,
    record_tool_observation,
)
from opspilot.domain.d3 import (
    execute_repair,
    get_or_create_action_intent,
)
from opspilot.domain.database import connect
from tests.d3_recovery_setup import (
    approve_s1_repair,
    claim_and_revalidate_s1_repair,
    plan_s1_repair,
    recovery_snapshot,
    start_s1_investigation,
)


def main() -> int:
    db_path = Path(sys.argv[1]).resolve()
    server = make_server(db_path, "tenant-a", "127.0.0.1", 0)
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True)
    thread.start()
    host, port = server.server_address
    api_url = f"http://{host}:{port}"
    binding, source_run_id = start_s1_investigation(db_path, "m1-process-recovery")
    task_id = str(binding["task_id"])
    observations = (
        ("get_integration_config", get_integration_config_fact(db_path, task_id, "integration-a")),
        ("get_principal_status", get_principal_status_fact(db_path, task_id, "principal-a")),
        ("get_auth_policy", get_auth_policy_fact(db_path, task_id, "orders-demo")),
        ("probe_endpoint", probe_endpoint_fact(db_path, task_id, "orders-demo", "integration-a", api_url)),
    )
    evidence_ids = []
    for index, (tool_name, result) in enumerate(observations, 1):
        item = record_tool_observation(
            db_path, task_id=task_id, call_id=f"n2-01-call-{index}", attempt_id=None,
            tool_call_id=f"n2-01-tool-{index}", tool_name=tool_name,
            arguments={"case": "N2-01", "index": index}, status="OK", result=result,
        )
        evidence_ids.append(str(item["evidence_id"]))
    gate = evaluate_evidence_gate(db_path, task_id, evidence_ids)
    if gate["decision"] != "READY":
        raise RuntimeError("N2-01 precondition did not produce a READY evidence gate.")
    plan = plan_s1_repair(db_path, task_id, source_run_id, gate)
    approval = approve_s1_repair(db_path, task_id, str(plan["plan_hash"]))
    claim_and_revalidate_s1_repair(db_path, approval, api_url)
    intent = get_or_create_action_intent(db_path, task_id, str(plan["plan_hash"]), "REPAIR", "executor-a")
    before_commit = recovery_snapshot(db_path, task_id)
    ledger = execute_repair(db_path, str(intent["action_id"]), "executor-a", "n2-01-process-commit")
    with connect(db_path) as connection:
        version = connection.execute(
            "SELECT config_version FROM integrations WHERE tenant_id='tenant-a' AND integration_id='integration-a'"
        ).fetchone()[0]
        events = connection.execute(
            "SELECT COUNT(*) FROM session_events WHERE source_kind='ACTION_LEDGER' AND source_id=? AND event_kind='REPAIR_COMMITTED'",
            (intent["action_id"],),
        ).fetchone()[0]
    print(json.dumps({
        "case": "N2-01", "task_id": task_id, "session_id": binding["session_id"],
        "plan_hash": plan["plan_hash"], "action_id": intent["action_id"],
        "ledger_id": ledger["ledger_id"], "status": ledger["status"],
        "before_version": ledger["before_version"], "after_version": ledger["after_version"],
        "config_version": version, "durable_repair_event_count_before_process_exit": events,
        "before_commit": before_commit, "after_commit": recovery_snapshot(db_path, task_id),
        "pid": os.getpid(), "process_exits_without_sse_delivery": True,
    }, sort_keys=True), flush=True)
    # Exit without a normal API/SSE shutdown after the Domain transaction commits.
    os._exit(0)


if __name__ == "__main__":
    raise SystemExit(main())
