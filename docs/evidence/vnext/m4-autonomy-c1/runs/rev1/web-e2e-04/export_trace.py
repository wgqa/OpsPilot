from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any


ROOT = Path(__file__).parent
DB = ROOT / "domain.sqlite3"
OUT = ROOT / "TRACE.jsonl"
TASK_ID = "task-c1dc432b-8311-4766-a407-77efeaa76749"
INITIAL_RUN = "run-01cb289a-ffa5-4e17-a9ee-4bd98bd48377"
CHAT_RUN = "run-cbc2b22e-a546-49eb-80c8-dd7161a4f287"
FOLLOWUP_RUN = "run-c1-followup-d2086ae7-a00e-4614-a441-8a94e972777c"


def parse_json(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return value


def row(connection: sqlite3.Connection, query: str, params: tuple[Any, ...]) -> dict[str, Any] | None:
    item = connection.execute(query, params).fetchone()
    return dict(item) if item is not None else None


def write(records: list[dict[str, Any]]) -> None:
    with OUT.open("w", encoding="utf-8", newline="\n") as stream:
        for item in records:
            stream.write(json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n")


def main() -> None:
    connection = sqlite3.connect(DB)
    connection.row_factory = sqlite3.Row
    records: list[dict[str, Any]] = []

    binding = row(connection, "SELECT * FROM task_bindings WHERE task_id=?", (TASK_ID,))
    control = row(connection, "SELECT * FROM task_controls WHERE task_id=?", (TASK_ID,))
    resource = row(connection, "SELECT * FROM s3_task_resources WHERE task_id=?", (TASK_ID,))
    session = row(connection, "SELECT * FROM sessions WHERE session_id=?", ("session-83d92f78-9dc6-4069-9de8-d607812eab97",))
    if not all((binding, control, resource, session)):
        raise SystemExit("expected web-e2e-04 task/session rows are missing")

    records.append({
        "record_type": "web_e2e_setup",
        "environment": {"web_origin": "http://127.0.0.1:5175", "backend_origin": "http://127.0.0.1:8001", "database": "isolated SQLite in this evidence directory"},
        "session": {key: session[key] for key in ("session_id", "tenant_id", "owner_id", "created_at")},
        "task_binding": {key: binding[key] for key in ("task_id", "tenant_id", "actor_id", "service_id", "integration_id", "principal_id", "status", "created_at")},
        "confirmed_resource": {key: resource[key] for key in ("service_id", "integration_id", "order_id", "confirmed_by", "confirmed_at", "selection_digest")},
        "task_control": {key: control[key] for key in ("terminal_state", "control_revision", "pending_critical_message_seq", "applied_critical_message_seq")},
        "browser_path": "support-a created the bound async-order task in the actual browser; follow-up submitted in the same session and task.",
    })

    messages = connection.execute(
        "SELECT message_id,sequence,role,input_kind,body,body_digest,command_id,created_at FROM messages WHERE task_id=? ORDER BY sequence",
        (TASK_ID,),
    ).fetchall()
    for item in messages:
        records.append({"record_type": "message", **dict(item)})

    assessment = row(
        connection,
        "SELECT * FROM investigation_update_assessments WHERE source_message_id=? AND task_id=?",
        ("message-e9d75701-6bc1-471a-94a6-e7ece5a7032f", TASK_ID),
    )
    if assessment:
        records.append({"record_type": "investigation_update_assessment", **assessment})
        classifier_attempts = connection.execute(
            "SELECT * FROM investigation_update_attempts WHERE assessment_id=? ORDER BY attempt_no",
            (assessment["assessment_id"],),
        ).fetchall()
        for item in classifier_attempts:
            records.append({"record_type": "classifier_provider_attempt", **dict(item)})

    runs = connection.execute(
        "SELECT * FROM task_runs WHERE task_id=? ORDER BY created_at,run_id", (TASK_ID,),
    ).fetchall()
    for item in runs:
        records.append({"record_type": "task_run", **dict(item)})

    diagnosis = row(connection, "SELECT * FROM s3_diagnoses WHERE task_id=? ORDER BY created_at LIMIT 1", (TASK_ID,))
    if diagnosis:
        diagnosis["evidence_ids_json"] = parse_json(diagnosis["evidence_ids_json"])
        diagnosis["body_json"] = parse_json(diagnosis["body_json"])
        records.append({"record_type": "initial_s3_diagnosis", **diagnosis})

    for run_id in (INITIAL_RUN, FOLLOWUP_RUN):
        model_traces = connection.execute(
            """SELECT t.*,a.run_id,a.kind AS attempt_kind,a.status AS attempt_status,
                      a.reserved_at,a.completed_at
               FROM d2_model_traces t JOIN d2_attempts a ON a.attempt_id=t.attempt_id
               WHERE a.run_id=? ORDER BY a.reserved_at,t.call_id""",
            (run_id,),
        ).fetchall()
        for item in model_traces:
            record = dict(item)
            for key in ("input_evidence_ids_json", "tool_calls_json", "usage_json"):
                record[key.removesuffix("_json")] = parse_json(record.pop(key))
            records.append({"record_type": "provider_call", **record})

        observations = connection.execute(
            """SELECT o.*,a.run_id,a.call_id AS attempt_call_id,a.tool_call_id AS attempt_tool_call_id,
                      a.reserved_at,a.completed_at
               FROM d2_tool_observations o JOIN d2_attempts a ON a.attempt_id=o.attempt_id
               WHERE a.run_id=? AND a.kind='MCP' ORDER BY a.reserved_at,o.observation_id""",
            (run_id,),
        ).fetchall()
        for item in observations:
            record = dict(item)
            record["result"] = parse_json(record.pop("result_json"))
            records.append({"record_type": "mcp_observation", **record})

    chat_attempt = row(connection, "SELECT * FROM chat_attempts WHERE run_id=?", (CHAT_RUN,))
    chat_answer = row(connection, "SELECT message_id,body_digest,created_at FROM messages WHERE command_id=?", (f"chat-answer:{CHAT_RUN}",))
    records.append({
        "record_type": "legacy_chat_sidecar",
        "run_id": CHAT_RUN,
        "attempt": chat_attempt,
        "persisted_answer_ref": chat_answer,
        "ui_policy": "suppressed after task follow-up classification; task answer is rendered from the durable readonly follow-up result",
    })

    followup = row(connection, "SELECT * FROM c1_readonly_followup_runs WHERE run_id=?", (FOLLOWUP_RUN,))
    if followup:
        for key in ("source_refs_json", "result_json"):
            followup[key.removesuffix("_json")] = parse_json(followup.pop(key))
        records.append({"record_type": "readonly_followup_result", **followup})

    model_contexts = connection.execute(
        "SELECT call_id,messages_json,tools_json FROM s3_model_contexts WHERE task_id=? AND run_id=? ORDER BY rowid",
        (TASK_ID, FOLLOWUP_RUN),
    ).fetchall()
    for item in model_contexts:
        records.append({
            "record_type": "actual_provider_context",
            "call_id": item["call_id"],
            "messages": parse_json(item["messages_json"]),
            "tools": parse_json(item["tools_json"]),
        })

    side_effect_counts = {}
    for table in (
        "d3_plans", "d3_approvals", "d3_action_intents", "d3_action_ledgers",
        "s3_handoff_queue_entries", "s3_handoff_receipts",
    ):
        side_effect_counts[table] = int(connection.execute(
            f"SELECT COUNT(*) FROM {table} WHERE task_id=?", (TASK_ID,),
        ).fetchone()[0])
    final_binding = row(connection, "SELECT status FROM task_bindings WHERE task_id=?", (TASK_ID,))
    final_control = row(connection, "SELECT terminal_state,control_revision,pending_critical_message_seq FROM task_controls WHERE task_id=?", (TASK_ID,))
    records.append({
        "record_type": "final_domain_check",
        "task_status": final_binding["status"] if final_binding else None,
        "task_control": final_control,
        "business_side_effect_counts": side_effect_counts,
        "business_diagnosis_count": int(connection.execute("SELECT COUNT(*) FROM s3_diagnoses WHERE task_id=?", (TASK_ID,)).fetchone()[0]),
        "followup_run_count": int(connection.execute("SELECT COUNT(*) FROM c1_readonly_followup_runs WHERE task_id=?", (TASK_ID,)).fetchone()[0]),
    })

    connection.close()
    browser_observation = ROOT / "BROWSER-REFRESH.json"
    if browser_observation.exists():
        records.append(json.loads(browser_observation.read_text(encoding="utf-8")))
    write(records)
    print(f"wrote {len(records)} trace records to {OUT}")


if __name__ == "__main__":
    main()
