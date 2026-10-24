from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path
from typing import Any


def parse(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return value


def main() -> None:
    root = Path(sys.argv[1]).resolve()
    db = root / "domain.sqlite3"
    out = root / "TRACE-review.jsonl"
    connection = sqlite3.connect(db)
    connection.row_factory = sqlite3.Row
    followup = connection.execute(
        "SELECT * FROM c1_readonly_followup_runs ORDER BY created_at DESC LIMIT 1",
    ).fetchone()
    if followup is None:
        raise SystemExit("no C1 follow-up row found")
    task_id, run_id = str(followup["task_id"]), str(followup["run_id"])
    records: list[dict[str, Any]] = []

    binding = connection.execute("SELECT * FROM task_bindings WHERE task_id=?", (task_id,)).fetchone()
    resource = connection.execute("SELECT * FROM s3_task_resources WHERE task_id=?", (task_id,)).fetchone()
    records.append({
        "record_type": "failed_web_case",
        "database": "isolated SQLite created for the actual browser run",
        "task_binding": {key: binding[key] for key in ("task_id", "tenant_id", "actor_id", "service_id", "integration_id", "principal_id", "status")},
        "resource": {key: resource[key] for key in ("service_id", "integration_id", "order_id", "confirmed_by", "selection_digest")},
        "run_id": run_id,
        "source_message_id": str(followup["source_message_id"]),
        "result_state": str(followup["result_state"]),
        "result_digest": str(followup["result_digest"]),
    })

    assessment = connection.execute(
        "SELECT * FROM investigation_update_assessments WHERE source_message_id=? AND task_id=?",
        (followup["source_message_id"], task_id),
    ).fetchone()
    if assessment:
        records.append({"record_type": "investigation_update_assessment", **dict(assessment)})
        for item in connection.execute(
            "SELECT * FROM investigation_update_attempts WHERE assessment_id=? ORDER BY attempt_no",
            (assessment["assessment_id"],),
        ):
            records.append({"record_type": "classifier_provider_attempt", **dict(item)})

    for item in connection.execute(
        "SELECT * FROM task_runs WHERE task_id=? ORDER BY created_at,run_id", (task_id,),
    ):
        records.append({"record_type": "task_run", **dict(item)})

    for item in connection.execute(
        """SELECT t.*,a.run_id,a.kind AS attempt_kind,a.status AS attempt_status,
                  a.reserved_at,a.completed_at
           FROM d2_model_traces t JOIN d2_attempts a ON a.attempt_id=t.attempt_id
           WHERE a.run_id=? ORDER BY a.reserved_at,t.call_id""",
        (run_id,),
    ):
        record = dict(item)
        for key in ("input_evidence_ids_json", "tool_calls_json", "usage_json"):
            record[key.removesuffix("_json")] = parse(record.pop(key))
        records.append({"record_type": "provider_call", **record})

    for item in connection.execute(
        """SELECT o.*,a.run_id,a.call_id AS attempt_call_id,a.tool_call_id AS attempt_tool_call_id,
                  a.reserved_at,a.completed_at
           FROM d2_tool_observations o JOIN d2_attempts a ON a.attempt_id=o.attempt_id
           WHERE a.run_id=? AND a.kind='MCP' ORDER BY a.reserved_at,o.observation_id""",
        (run_id,),
    ):
        record = dict(item)
        record["result"] = parse(record.pop("result_json"))
        records.append({"record_type": "mcp_observation", **record})

    result = dict(followup)
    for key in ("source_refs_json", "result_json"):
        result[key.removesuffix("_json")] = parse(result.pop(key))
    records.append({"record_type": "readonly_followup_result", **result})

    counts = {}
    for table in ("d3_plans", "d3_approvals", "d3_action_intents", "d3_action_ledgers", "s3_handoff_queue_entries", "s3_handoff_receipts"):
        counts[table] = int(connection.execute(f"SELECT COUNT(*) FROM {table} WHERE task_id=?", (task_id,)).fetchone()[0])
    records.append({"record_type": "final_safety_counts", "task_id": task_id, "business_side_effect_counts": counts})
    connection.close()

    with out.open("w", encoding="utf-8", newline="\n") as stream:
        for item in records:
            stream.write(json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n")
    print(f"wrote {len(records)} records to {out}")


if __name__ == "__main__":
    main()
