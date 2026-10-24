from __future__ import annotations

import json
import sqlite3
from collections import Counter
from pathlib import Path
from typing import Any


RUN_ROOT = Path(__file__).resolve().parent / "web-e2e-hf01-03"
DB_PATH = RUN_ROOT / "domain.sqlite3"
JOURNEY_PATH = RUN_ROOT / "journey.json"
TRACE_PATH = RUN_ROOT / "TRACE.jsonl"


def decoded(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return value


def query(connection: sqlite3.Connection, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    return [dict(row) for row in connection.execute(sql, params).fetchall()]


def main() -> None:
    journey = json.loads(JOURNEY_PATH.read_text(encoding="utf-8"))
    task_id, session_id = str(journey["task_id"]), str(journey["session_id"])
    records: list[dict[str, Any]] = []
    connection = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only=ON")

    api_counts = Counter(f"{item['method']} {item['path']} {item['status']}" for item in journey.get("http", []))
    records.append({
        "record_type": "browser_journey",
        "browser": journey.get("browser"),
        "base_url": journey.get("baseURL"),
        "task_id": task_id,
        "session_id": session_id,
        "order_id": journey.get("order_id"),
        "initial_outcome": journey.get("initial_outcome"),
        "steps": [{
            key: step.get(key) for key in (
                "label", "message_id", "source_chat_run_id", "source_chat_run_status",
                "intent", "follow_up_action", "assessment_id", "classifier_attempt_id",
                "investigation_run_id", "screenshot",
            )
        } for step in journey.get("steps", [])],
        "api_response_counts": dict(sorted(api_counts.items())),
        "console_errors": journey.get("console_errors", []),
        "result": journey.get("result"),
    })

    binding = query(connection,
        "SELECT * FROM task_bindings WHERE task_id=? AND tenant_id='tenant-a'", (task_id,))
    resource = query(connection,
        "SELECT * FROM s3_task_resources WHERE task_id=? AND tenant_id='tenant-a'", (task_id,))
    records.append({"record_type": "task_binding", "rows": binding, "task_resources": resource})

    for item in query(connection, """SELECT message_id,tenant_id,session_id,task_id,sequence,role,input_kind,
                                     body,body_digest,command_id,created_at
                              FROM messages WHERE task_id=? ORDER BY sequence""", (task_id,)):
        records.append({"record_type": "message", **item})

    runs = query(connection, "SELECT * FROM task_runs WHERE task_id=? ORDER BY created_at,run_id", (task_id,))
    for item in runs:
        records.append({"record_type": "task_run", **item})

    diagnoses = query(connection, "SELECT * FROM s3_diagnoses WHERE task_id=? ORDER BY created_at", (task_id,))
    for item in diagnoses:
        for key in ("evidence_ids_json", "body_json"):
            item[key.removesuffix("_json")] = decoded(item.pop(key))
        records.append({"record_type": "s3_diagnosis", **item})

    assessments = query(connection,
        "SELECT * FROM investigation_update_assessments WHERE task_id=? ORDER BY created_at,assessment_id", (task_id,))
    for assessment in assessments:
        records.append({"record_type": "investigation_update_assessment", **assessment})
        attempts = query(connection, """SELECT attempt_id,assessment_id,attempt_no,model_id,prompt_digest,input_digest,
                                         status,response_digest,provider_response_id,input_tokens,output_tokens,
                                         total_tokens,error_code,created_at,completed_at
                                  FROM investigation_update_attempts WHERE assessment_id=? ORDER BY attempt_no""",
                         (assessment["assessment_id"],))
        for attempt in attempts:
            records.append({"record_type": "classifier_provider_attempt", **attempt})

    for item in query(connection, "SELECT * FROM c1_readonly_followup_runs WHERE task_id=? ORDER BY created_at,run_id", (task_id,)):
        for key in ("source_refs_json", "result_json"):
            item[key.removesuffix("_json")] = decoded(item.pop(key))
        records.append({"record_type": "readonly_followup_result", **item})

    model_rows = query(connection, """SELECT a.run_id,a.attempt_id,a.kind AS attempt_kind,a.status AS attempt_status,
                                       a.tool_name,a.tool_call_id,a.call_id,
                                       t.model_id,t.prompt_digest,t.input_evidence_ids_json,t.provider_response_id,
                                       t.tool_calls_json,t.assistant_text,t.usage_json,t.status AS model_status,t.created_at
                                FROM d2_attempts a LEFT JOIN d2_model_traces t ON t.attempt_id=a.attempt_id
                                WHERE a.task_id=? ORDER BY a.reserved_at,a.attempt_id""", (task_id,))
    for item in model_rows:
        for key in ("input_evidence_ids_json", "tool_calls_json", "usage_json"):
            if key in item:
                item[key.removesuffix("_json")] = decoded(item.pop(key))
        records.append({"record_type": "investigation_model_or_tool_attempt", **item})

    observation_rows = query(connection, """SELECT o.observation_id,o.task_id,o.call_id,o.attempt_id,o.tool_call_id,
                                              o.tool_name,o.status,o.progress_added,o.error_class,o.result_digest,
                                              o.result_json,o.evidence_id,o.created_at,a.run_id
                                       FROM d2_tool_observations o JOIN d2_attempts a
                                         ON a.attempt_id=o.attempt_id AND a.task_id=o.task_id
                                       WHERE o.task_id=? ORDER BY o.created_at,o.observation_id""", (task_id,))
    evidence_ids: set[str] = set()
    for item in observation_rows:
        item["result"] = decoded(item.pop("result_json"))
        if item.get("evidence_id"):
            evidence_ids.add(str(item["evidence_id"]))
        records.append({"record_type": "mcp_observation", **item})

    if evidence_ids:
        placeholders = ",".join("?" for _ in evidence_ids)
        evidence_rows = query(connection, f"""SELECT * FROM d2_evidence WHERE task_id=?
                                             AND evidence_id IN ({placeholders}) ORDER BY fetched_at,evidence_id""",
                              (task_id, *sorted(evidence_ids)))
    else:
        evidence_rows = []
    for item in evidence_rows:
        for key in ("observed_versions_json", "facts_json"):
            item[key.removesuffix("_json")] = decoded(item.pop(key))
        records.append({"record_type": "evidence", **item})

    task = binding[0] if binding else {}
    for item in query(connection, """SELECT request_id,tenant_id,service_id,integration_id,principal_id,route,
                                       authn_event_id,http_status,body_json,body_digest,created_at
                                FROM s3_http_observations WHERE tenant_id=? AND service_id=? AND integration_id=?
                                ORDER BY created_at,request_id""",
                      (str(task.get("tenant_id", "tenant-a")), str(task.get("service_id", "orders-async-demo")),
                       str(task.get("integration_id", "async-integration-a")))):
        item["body"] = decoded(item.pop("body_json"))
        item["source_role"] = "actual local HTTP read observed by the bound MCP tool"
        records.append({"record_type": "http_observation", **item})

    deliveries = query(connection, """SELECT * FROM s3_deliveries WHERE tenant_id='tenant-a'
                                        AND service_id='orders-async-demo' AND order_id=?""", (str(journey["order_id"]),))
    receivers = query(connection, """SELECT * FROM s3_receivers WHERE tenant_id='tenant-a'
                                       AND service_id='orders-async-demo' AND order_id=?""", (str(journey["order_id"]),))
    for row in deliveries:
        for key in ("transport_response_json",):
            row[key.removesuffix("_json")] = decoded(row.pop(key))
        records.append({"record_type": "fixture_preparation_transport", "agent_action": False,
                        "preparation_only": True, "row": row,
                        "note": "The local receiver HTTP 202 was created by explicit fixture preparation; it is separate from Agent behavior."})
    for row in receivers:
        records.append({"record_type": "receiver_current_domain_row", **row})

    chat_attempts = query(connection, """SELECT a.*,m.manifest_id,m.prompt_digest AS manifest_prompt_digest,
                                           m.selected_message_ids_json,m.evidence_refs_json,m.excluded_sources_json,
                                           m.truncation_json,m.trusted_state_digest,m.created_at AS manifest_created_at
                                    FROM chat_attempts a LEFT JOIN chat_context_manifests m
                                      ON m.attempt_id=a.attempt_id AND m.run_id=a.run_id
                                    WHERE a.task_id=? ORDER BY a.created_at,a.attempt_id""", (task_id,))
    chat_input_total = chat_output_total = 0
    for item in chat_attempts:
        chat_input_total += int(item.get("input_tokens") or 0)
        chat_output_total += int(item.get("output_tokens") or 0)
        for key in ("selected_message_ids_json", "evidence_refs_json", "excluded_sources_json", "truncation_json"):
            if item.get(key) is not None:
                item[key.removesuffix("_json")] = decoded(item.pop(key))
        records.append({"record_type": "chat_provider_attempt_and_context_manifest", **item})
    for item in query(connection, """SELECT a.run_id,a.message_id,a.attempt_id,a.manifest_id,a.body_digest,
                                      a.committed_at,m.body,m.body_digest AS actual_body_digest
                               FROM chat_run_answers a JOIN messages m ON m.message_id=a.message_id
                               WHERE m.task_id=? ORDER BY a.committed_at""", (task_id,)):
        records.append({"record_type": "chat_answer", **item})

    classifier_totals = query(connection, """SELECT COALESCE(SUM(a.input_tokens),0) AS input_tokens,
                                               COALESCE(SUM(a.output_tokens),0) AS output_tokens,
                                               COALESCE(SUM(a.total_tokens),0) AS total_tokens,
                                               COUNT(*) AS requests
                                        FROM investigation_update_attempts a
                                        JOIN investigation_update_assessments x ON x.assessment_id=a.assessment_id
                                        WHERE x.task_id=? AND a.status='SUCCEEDED'""", (task_id,))[0]
    investigator_input = investigator_output = investigator_total = 0
    investigator_requests = 0
    for item in model_rows:
        usage = item.get("usage")
        if item.get("attempt_kind") == "MODEL" and isinstance(usage, dict):
            investigator_requests += 1
            investigator_input += int(usage.get("input_tokens") or 0)
            investigator_output += int(usage.get("output_tokens") or 0)
            investigator_total += int(usage.get("total_tokens") or 0)
    records.append({
        "record_type": "provider_token_summary",
        "model": "deepseek-flash",
        "classifier": classifier_totals,
        "investigator": {"requests": investigator_requests, "input_tokens": investigator_input,
                         "output_tokens": investigator_output, "total_tokens": investigator_total},
        "chat": {"requests": len(chat_attempts), "input_tokens": chat_input_total,
                 "output_tokens": chat_output_total, "total_tokens": chat_input_total + chat_output_total},
        "total": {"requests": int(classifier_totals["requests"]) + investigator_requests + len(chat_attempts),
                  "input_tokens": int(classifier_totals["input_tokens"]) + investigator_input + chat_input_total,
                  "output_tokens": int(classifier_totals["output_tokens"]) + investigator_output + chat_output_total,
                  "total_tokens": int(classifier_totals["total_tokens"]) + investigator_total + chat_input_total + chat_output_total},
        "note": "Token values are the provider/domain persisted usage records; no API credentials are captured.",
    })

    connection.close()
    TRACE_PATH.write_text("".join(json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n" for item in records), encoding="utf-8")
    print(json.dumps({"trace_path": str(TRACE_PATH), "records": len(records), "chat_attempts": len(chat_attempts),
                      "followups": len(journey.get("steps", [])), "result": journey.get("result")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
