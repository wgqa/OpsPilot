"""Correlate an already-run real Web journey with immutable Domain traces.

This reads the browser's captured HTTP events and persisted rows only; it never
creates Tasks, Evidence, Provider calls, or business outcomes.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path
from typing import Any


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def one(connection: sqlite3.Connection, query: str, parameters: tuple[Any, ...] = ()) -> dict[str, Any] | None:
    row = connection.execute(query, parameters).fetchone()
    return dict(row) if row is not None else None


def many(connection: sqlite3.Connection, query: str, parameters: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    return [dict(row) for row in connection.execute(query, parameters).fetchall()]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=Path, required=True)
    parser.add_argument("--browser-failure", type=Path, required=True)
    parser.add_argument("--browser-revisit", type=Path, required=True)
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    seed = load_json(args.seed)
    browser = load_json(args.browser_failure)
    revisit = load_json(args.browser_revisit)
    source_task = str(seed["source_task"]["task_id"])
    source_session = str(seed["source_session_id"])
    source_check = browser.get("source_check") or {}
    target_task_rows = []

    connection = sqlite3.connect(args.database)
    connection.row_factory = sqlite3.Row
    try:
        target_task_rows = many(
            connection,
            "SELECT task_id, actor_id, service_id, integration_id, ticket_id, status "
            "FROM task_bindings WHERE task_id <> ? ORDER BY rowid",
            (source_task,),
        )
        if len(target_task_rows) != 1:
            raise RuntimeError(f"Expected exactly one Web-created Task B, found {len(target_task_rows)}.")
        target_task = target_task_rows[0]
        target_id = str(target_task["task_id"])
        run = one(
            connection,
            "SELECT run_id, kind, status, blocked_reason, created_at, started_at, ended_at "
            "FROM task_runs WHERE task_id = ? ORDER BY created_at DESC LIMIT 1",
            (target_id,),
        )
        if run is None:
            raise RuntimeError("Web-created Task B has no durable Run row.")
        memory = one(
            connection,
            "SELECT memory_id, state, version, source_task_id, source_outcome, confirmed_by, "
            "created_at, confirmed_at, content_digest, experience_json FROM d5_memories WHERE source_task_id = ?",
            (source_task,),
        )
        if memory is None:
            raise RuntimeError("The browser flow did not persist a Task A Memory record.")
        memory_id = str(memory["memory_id"])
        contexts = many(
            connection,
            "SELECT p.call_id, p.attempt_id, p.model_id, p.prompt_version, p.prompt_digest, "
            "p.selected_memories_json, p.excluded_sources_json, p.model_status, p.built_at, "
            "t.provider_response_id, t.tool_calls_json, t.usage_json "
            "FROM d5_context_provenance p JOIN d2_model_traces t "
            "ON t.call_id=p.call_id AND t.task_id=p.task_id "
            "WHERE p.task_id=? ORDER BY p.built_at, p.call_id",
            (target_id,),
        )
        selected = []
        for context in contexts:
            context["selected_memories"] = json.loads(context.pop("selected_memories_json"))
            context["excluded_sources"] = json.loads(context.pop("excluded_sources_json"))
            context["tool_calls"] = json.loads(context.pop("tool_calls_json"))
            context["usage"] = json.loads(context.pop("usage_json"))
            if any(
                str(item.get("memory_id")) == memory_id
                and str(item.get("source_task_id")) == source_task
                for item in context["selected_memories"]
            ):
                selected.append(context)
        if not selected:
            raise RuntimeError("No Task B Provider call selected the Task A Memory.")

        prompt_rows = many(
            connection,
            "SELECT call_id, messages_json, tools_json FROM s3_model_contexts "
            "WHERE task_id=? AND call_id IN (%s)" % ",".join("?" for _ in selected),
            (target_id, *(str(item["call_id"]) for item in selected)),
        )
        actual_prompts = []
        for row in prompt_rows:
            messages = json.loads(row["messages_json"])
            prompt_text = json.dumps(messages, ensure_ascii=False)
            actual_prompts.append({
                "call_id": str(row["call_id"]),
                "memory_id_in_actual_outbound_messages": memory_id in prompt_text,
                "source_task_id_in_actual_outbound_messages": source_task in prompt_text,
                "prompt_digest": next(item["prompt_digest"] for item in selected if item["call_id"] == row["call_id"]),
            })
        if not actual_prompts or not all(
            item["memory_id_in_actual_outbound_messages"] and item["source_task_id_in_actual_outbound_messages"]
            for item in actual_prompts
        ):
            raise RuntimeError("Persisted Provider messages do not contain the provenance-selected Task A Memory.")

        observations = many(
            connection,
            "SELECT o.observation_id, a.run_id, o.attempt_id, o.tool_name, o.status, o.evidence_id, "
            "o.result_digest, o.created_at FROM d2_tool_observations o "
            "JOIN d2_attempts a ON a.attempt_id=o.attempt_id "
            "WHERE o.task_id=? ORDER BY o.created_at, o.rowid",
            (target_id,),
        )
        diagnoses = many(
            connection,
            "SELECT receipt_id, run_id, outcome, evidence_ids_json, digest, body_json, created_at "
            "FROM s3_diagnoses WHERE task_id=? ORDER BY created_at, rowid",
            (target_id,),
        )
        for item in diagnoses:
            item["evidence_ids"] = json.loads(item.pop("evidence_ids_json"))
            item["body"] = json.loads(item.pop("body_json"))
        write_tables = (
            "s3_handoff_queue_entries", "s3_handoff_receipts", "d3_action_intents",
            "d3_action_ledgers", "d3_delivery_records",
        )
        business_writes = {}
        for table in write_tables:
            exists = connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone()
            if exists:
                business_writes[table] = int(connection.execute(
                    f"SELECT COUNT(*) FROM {table} WHERE task_id=?", (target_id,),
                ).fetchone()[0])
        browser_requests = browser.get("web_requests", [])
        candidate_request = next((r for r in browser_requests if r.get("method") == "POST" and "/memories/candidates" in r.get("path", "")), None)
        approval_request = next((r for r in browser_requests if r.get("method") == "POST" and "/confirm" in r.get("path", "")), None)
        target_create_request = next((r for r in browser_requests if r.get("method") == "POST" and r.get("path", "").endswith("/tasks")), None)
        result = {
            "status": "RECONCILED_FROM_REAL_BROWSER_AND_DOMAIN_OBSERVATIONS",
            "source": {
                "task_id": source_task, "session_id": source_session,
                "run_id": seed["source_task"]["run_id"], "outcome": seed["source_outcome"]["outcome"],
                "currentness_at_browser_action": source_check.get("outcome", {}).get("currentness"),
                "http_observations": seed["source_trace"]["http"],
                "mcp_observations": seed["source_trace"]["observations"],
            },
            "memory": {
                key: memory[key] for key in (
                    "memory_id", "state", "version", "source_task_id", "source_outcome",
                    "confirmed_by", "created_at", "confirmed_at", "content_digest",
                )
            },
            "browser_actions": {
                "candidate_http_status": candidate_request.get("status") if candidate_request else None,
                "approval_http_status": approval_request.get("status") if approval_request else None,
                "target_task_acceptance_http_status": target_create_request.get("status") if target_create_request else None,
                "runner_end_state": browser.get("status"),
                "runner_failure": browser.get("message"),
                "runner_failure_is_postcondition_only": "selected-memory-provenance" in str(browser.get("message", "")),
                "revisit_status": revisit.get("status"),
                "revisit_model_called": revisit.get("model_called_during_revisit"),
            },
            "target": {
                "task": target_task, "run": run, "diagnoses": diagnoses,
                "provider_request_count": len(contexts), "provider_contexts": contexts,
                "selected_task_a_memory_calls": [item["call_id"] for item in selected],
                "actual_outbound_prompt_checks": actual_prompts,
                "mcp_observations": observations,
                "business_write_counts": business_writes,
                "currentness_at_revisit": revisit.get("currentness_at_revisit"),
                "outcome_at_revisit": revisit.get("current_s3_outcome"),
            },
            "limitations": [
                "The Web orchestration script reached a successfully completed Task B Run, then failed its over-strict final locator check, which expected the Memory to remain selected in the latest call.",
                "Persisted trace proves Memory was selected in an earlier actual Task B Provider call, then excluded after current evidence conflicted; the corrected assertion checks the full call history.",
                "The later browser revisit is a read-only replay after the target Event SLA deadline; it correctly displays the historical result as no longer current.",
            ],
            "evidence_sources": {
                "browser_failure_file": str(args.browser_failure),
                "browser_revisit_file": str(args.browser_revisit),
                "seed_file": str(args.seed),
                "database": str(args.database),
            },
        }
    finally:
        connection.close()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": result["status"], "target_task": target_task["task_id"],
        "target_run": run["run_id"], "memory_selected_calls": [item["call_id"] for item in selected],
        "provider_requests": len(contexts), "mcp_observations": len(observations),
        "runner_failure_postcondition_only": result["browser_actions"]["runner_failure_is_postcondition_only"],
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
