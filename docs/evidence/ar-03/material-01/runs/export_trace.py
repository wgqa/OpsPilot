"""Export bounded, observed SQLite traces from the frozen deterministic runs."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
RUNS = ROOT / "runs"
INPUT = RUNS / "green-12-tmp"
OUTPUT = ROOT / "TRACE.jsonl"


def _load(value: str | None):
    if not value:
        return None
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return None


def _tool_result(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        return {"shape": type(value).__name__}
    if isinstance(value.get("protocol_documents"), list):
        return {
            "success": value.get("success"), "project_id": value.get("project_id"),
            "grant_version": value.get("grant_version"), "scope_digest": value.get("scope_digest"),
            "documents": [{key: row.get(key) for key in ("document_id", "version", "digest", "source")}
                          for row in value["protocol_documents"] if isinstance(row, dict)],
        }
    if isinstance(value.get("comparison_digest"), str):
        return {
            "success": value.get("success"), "comparison_digest": value.get("comparison_digest"),
            "base_ref": value.get("base_ref"), "target_ref": value.get("target_ref"),
            "difference_count": value.get("diff_count"), "summary": value.get("summary"),
            "unconfirmed_aspects": value.get("unconfirmed_aspects"),
            "deployment_version_verified": value.get("deployment_version_verified"),
        }
    if isinstance(value.get("document_ref"), dict):
        return {
            "success": value.get("success"), "document_ref": value.get("document_ref"),
            "query": value.get("query"), "excerpts": value.get("excerpts"),
            "source_refs": value.get("source_refs"), "authority": value.get("authority"),
            "deployment_version_verified": value.get("deployment_version_verified"),
        }
    if isinstance(value.get("skill"), dict):
        skill = value["skill"]
        return {
            "success": value.get("success"), "problem_type": value.get("problem_type"),
            "skill": {key: skill.get(key) for key in ("name", "version", "digest", "description")},
            "selection_reason": value.get("selection_reason"), "authority": value.get("authority"),
        }
    facts = value.get("facts")
    if isinstance(facts, dict):
        return {
            "fact_type": value.get("fact_type"), "resource_id": value.get("resource_id"),
            "observed_at": value.get("observed_at"), "observed_versions": value.get("observed_versions"),
            "facts": {key: facts.get(key) for key in (
                "order_id", "event_id", "transport_request_id", "receiver_http_status",
                "status", "retry_state", "processed_at",
            ) if key in facts},
        }
    return {key: value.get(key) for key in (
        "success", "reason_code", "authority", "deployment_version_verified",
    ) if key in value}


def _model_actions(value: object) -> list[dict[str, object]]:
    result = value if isinstance(value, list) else [value]
    actions = []
    for item in result:
        if not isinstance(item, dict):
            continue
        data = item.get("data", item.get("kwargs", {}))
        if not isinstance(data, dict):
            continue
        calls = data.get("tool_calls")
        if not isinstance(calls, list):
            calls = data.get("additional_kwargs", {}).get("tool_calls", []) \
                if isinstance(data.get("additional_kwargs"), dict) else []
        for call in calls:
            if isinstance(call, dict):
                function = call.get("function") if isinstance(call.get("function"), dict) else call
                actions.append({
                    "name": function.get("name"),
                    "arguments": function.get("args", function.get("arguments")),
                })
    return actions


def main() -> None:
    records: list[dict[str, object]] = []
    for db_path in sorted(INPUT.glob("*/domain.sqlite3")):
        connection = sqlite3.connect(db_path)
        connection.row_factory = sqlite3.Row
        runs = connection.execute(
            """SELECT r.run_id,r.task_id,r.session_id,r.status,r.source_message_id,m.body AS user_input
               FROM task_runs r JOIN assistant_runs a ON a.run_id=r.run_id
               JOIN messages m ON m.message_id=r.source_message_id ORDER BY r.created_at"""
        ).fetchall()
        for run in runs:
            binding = None
            if run["task_id"]:
                tables = {row["name"] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                if "s3_task_resources" in tables:
                    binding_row = connection.execute(
                        "SELECT order_id,confirmed_by,confirmed_at,selection_digest "
                        "FROM s3_task_resources WHERE task_id=?", (run["task_id"],)
                    ).fetchone()
                    binding = dict(binding_row) if binding_row else None
            records.append({
                "kind": "assistant_run",
                "source_test": db_path.parent.name,
                "model": "MaterialFixtureModel",
                "provider_requests": 0,
                "run_id": run["run_id"], "session_id": run["session_id"],
                "task_id": run["task_id"], "binding": binding,
                "source_message_id": run["source_message_id"],
                "user_input": run["user_input"], "run_status": run["status"],
            })
            calls = connection.execute(
                "SELECT * FROM assistant_calls WHERE run_id=? ORDER BY created_at,call_id", (run["run_id"],)
            ).fetchall()
            for call in calls:
                request = _load(call["request_json"])
                result = _load(call["result_json"])
                record = {
                    "kind": "assistant_call", "source_test": db_path.parent.name,
                    "model": "MaterialFixtureModel", "provider_requests": 0,
                    "run_id": run["run_id"], "call_id": call["call_id"],
                    "call_kind": call["kind"], "status": call["status"],
                    "created_at": call["created_at"], "completed_at": call["completed_at"],
                }
                if call["kind"] == "MCP" and isinstance(request, dict):
                    record.update({
                        "executed_tool": request.get("name"), "arguments": request.get("args"),
                        "observation_id": call["observation_id"], "evidence_id": call["evidence_id"],
                        "result": _tool_result(result),
                    })
                elif call["kind"] == "MODEL":
                    record["model_tool_proposals"] = _model_actions(result)
                    record["usage"] = _load(call["usage_json"])
                records.append(record)
            answer = connection.execute(
                """SELECT a.message_id,m.body,a.body_digest,a.committed_at
                   FROM chat_run_answers a JOIN messages m ON m.message_id=a.message_id
                   WHERE a.run_id=?""", (run["run_id"],)
            ).fetchone()
            if answer:
                records.append({
                    "kind": "persisted_answer", "source_test": db_path.parent.name,
                    "model": "MaterialFixtureModel", "provider_requests": 0,
                    "run_id": run["run_id"], "answer_message_id": answer["message_id"],
                    "body_digest": answer["body_digest"], "committed_at": answer["committed_at"],
                    "answer": answer["body"],
                })
        connection.close()
    OUTPUT.write_text("".join(json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n" for item in records), encoding="utf-8")
    print(f"records={len(records)} path={OUTPUT}")


if __name__ == "__main__":
    main()
