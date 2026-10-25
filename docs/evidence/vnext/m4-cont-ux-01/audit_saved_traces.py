"""Read-only planning audit of saved artifacts; no OpsPilot/DB/network execution.

Run from any directory with Python. Only TRACE_AUDIT.json next to this file is
written. No sealed holdout, local environment file, or live SQLite is opened.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
from collections import Counter
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
BASE = "b70c02284a3f1f873c4fbf56b1d6768e9a0ec1c8"
SOURCES: dict[str, dict[str, object]] = {}


def read(relative: str):
    raw = (ROOT / relative).read_bytes()
    blob = subprocess.check_output(
        ["git", "rev-parse", f"{BASE}:{relative}"], cwd=ROOT, text=True,
    ).strip()
    SOURCES[relative] = {
        "git_blob_at_base": blob,
        "working_file_sha256": hashlib.sha256(raw).hexdigest(),
        "bytes": len(raw),
        "method": "structured parse of saved artifact; no live replay",
    }
    text = raw.decode("utf-8-sig")
    return [json.loads(line) for line in text.splitlines() if line.strip()] if relative.endswith(".jsonl") else json.loads(text)


def parsed(value):
    return json.loads(value) if isinstance(value, str) else value


def usage_sum(values):
    values = [parsed(value) for value in values]
    known = [value for value in values if isinstance(value, dict) and all(
        type(value.get(key)) is int for key in ("input_tokens", "output_tokens", "total_tokens")
    )]
    return {
        **{key: sum(value[key] for value in known) for key in ("input_tokens", "output_tokens", "total_tokens")},
        "known_records": len(known), "unknown_records": len(values) - len(known),
        "peak_no_cache_estimated_usd": round(sum(
            (value["input_tokens"] * 0.3 + value["output_tokens"] * 1.2) / 1_000_000 for value in known
        ), 8),
        "estimate_basis": "2026-10-26 official Flash peak rates; not account charge",
    }


def elapsed(start, end):
    return round((datetime.fromisoformat(end.replace("Z", "+00:00")) - datetime.fromisoformat(start.replace("Z", "+00:00"))).total_seconds(), 3) if start and end else None


def hf_journey():
    path = "docs/evidence/vnext/m4-c1-hf-01/TRACE.jsonl"
    rows = read(path)
    by_type = lambda kind: [row for row in rows if row.get("record_type") == kind]
    attempts = by_type("investigation_model_or_tool_attempt")
    messages = {row["message_id"]: row for row in by_type("message")}
    results = {row["run_id"]: row for row in by_type("readonly_followup_result")}
    run_stats = []
    for run in by_type("task_run"):
        own = [row for row in attempts if row["run_id"] == run["run_id"]]
        models = [row for row in own if row["attempt_kind"] == "MODEL"]
        result = results.get(run["run_id"], {})
        run_stats.append({
            "run_id": run["run_id"], "kind": run["kind"], "status": run["status"],
            "source_message_id": run["source_message_id"],
            "source_text": messages.get(run["source_message_id"], {}).get("body"),
            "model_attempts": len(models),
            "mcp_attempts": sum(row["attempt_kind"] == "MCP" for row in own),
            "tools": [row["tool_name"] for row in own if row["attempt_kind"] == "MCP"],
            "usage": usage_sum([row["usage"] for row in models]),
            "elapsed_seconds": elapsed(run.get("started_at"), run.get("ended_at")),
            "result_state": result.get("result_state"),
            "answer_chars": len(result.get("answer_text") or "") if result else None,
            "reason_code": result.get("reason_code"),
        })
    classifier = by_type("classifier_provider_attempt")
    chat = by_type("chat_provider_attempt_and_context_manifest")
    models = [row for row in attempts if row["attempt_kind"] == "MODEL"]
    return {
        "source": path, "runs": run_stats,
        "investigator_usage": usage_sum([row["usage"] for row in models]),
        "classifier_usage": usage_sum(classifier), "chat_usage": usage_sum(chat),
        "provider_requests": len(models) + len(classifier) + len(chat),
        "total_usage": usage_sum([row["usage"] for row in models] + classifier + chat),
        "compression_export": "not separately exported; no zero-cost inference",
        "mcp_observations": len(by_type("mcp_observation")),
        "http_observations": len(by_type("http_observation")),
        "evidence_level": "historical real Web/Provider/MCP/HTTP saved records; not rerun in phase 0",
    }


def task_trace(path: str):
    data = read(path)
    attempts = data["d2_attempts"]
    traces = {row["attempt_id"]: row for row in data["d2_model_traces"]}
    outputs = {}
    for row in data.get("s3_run_answers", []):
        body = parsed(row["body_json"])
        outputs[row["run_id"]] = {
            "result_state": body["result_state"], "answer_chars": len(body["answer_text"]),
            "delivery_mode": body.get("result", {}).get("delivery_mode"),
            "source_message_id": body["source_message_id"],
        }
    for row in data.get("c1_readonly_followup_runs", []):
        body = parsed(row.get("result_json") or "{}")
        outputs[row["run_id"]] = {
            "result_state": row["result_state"], "answer_chars": len(row.get("answer_text") or ""),
            "reason_code": row.get("reason_code"), "delivery_mode": body.get("delivery_mode"),
            "source_message_id": row["source_message_id"],
        }
    runs = []
    for row in data["task_runs"]:
        own = [item for item in attempts if item.get("run_id") == row["run_id"]]
        model = [item for item in own if item["kind"] == "MODEL"]
        runs.append({
            "run_id": row["run_id"], "source_message_id": row["source_message_id"],
            "kind": row["kind"], "status": row["status"], "blocked_reason": row.get("blocked_reason"),
            "control_revision": row.get("expected_control_revision"),
            "applied_critical_message_seq": row.get("applied_critical_message_seq"),
            "model_attempts": len(model), "mcp_attempts": sum(item["kind"] == "MCP" for item in own),
            "usage": usage_sum([traces.get(item["attempt_id"], {}).get("usage_json", {}) for item in model]),
            "elapsed_seconds": elapsed(row.get("started_at"), row.get("ended_at")),
            "output": outputs.get(row["run_id"]),
        })
    return {
        "source": path, "runs": runs,
        "total_d2_model_attempts": sum(item["kind"] == "MODEL" for item in attempts),
        "total_mcp_attempts": sum(item["kind"] == "MCP" for item in attempts),
        "investigator_usage": usage_sum([item.get("usage_json", {}) for item in data["d2_model_traces"]]),
        "classifier_usage": usage_sum(data.get("investigation_update_attempts", [])),
        "chat_usage": usage_sum(data.get("chat_attempts", [])),
        "write_counts": data.get("write_counts"),
        "messages": [{key: row.get(key) for key in ("message_id", "sequence", "role", "input_kind", "created_at")} for row in data["messages"]],
        "evidence_level": "historical saved raw Task export, statically joined by attempt/run/message IDs",
    }


def budget_examples():
    rows = []
    for relative in sorted((ROOT / "docs/evidence/vnext/m4-continuous-vs01/runs/budget-02").glob("*/RESULT.json")):
        path = relative.relative_to(ROOT).as_posix()
        result = read(path)
        trace = task_trace(path.replace("RESULT.json", "TRACE.json"))
        answer = result.get("answer") or {}
        rows.append({
            "case_id": result["case_id"], "profile": result["profile"], "task_id": result["task_id"],
            "model_attempts": trace["total_d2_model_attempts"], "mcp_attempts": trace["total_mcp_attempts"],
            "result_state": answer.get("result_state"), "delivery_mode": answer.get("result", {}).get("delivery_mode"),
            "elapsed_seconds": result["elapsed_seconds"], "usage": trace["investigator_usage"],
            "write_counts": trace["write_counts"], "source": path,
            "limitation": "prepared-fact repair version before final bounded-response retention fix; one instance, not a current efficacy trial",
        })
    return rows


def main():
    hf = hf_journey()
    old = read("docs/evidence/vnext/m4-autonomy-c1/runs/rev1/web-e2e-04/TRACE.jsonl")
    sidecar = next(row for row in old if row.get("record_type") == "legacy_chat_sidecar")
    ledger = read("docs/evidence/vnext/m4-continuous-vs01/PROVIDER_LEDGER.jsonl")
    completes = [row for row in ledger if row["event"] == "COMPLETE"]
    requests = [row["request_id"] for row in completes]
    web = [task_trace(path) for path in (
        "docs/evidence/vnext/m4-continuous-vs01/runs/web-02/task-bfbec733-f041-4a68-95e6-60773741f6d6-TRACE.json",
        "docs/evidence/vnext/m4-continuous-vs01/runs/web-03/task-1734be3c-5d50-4462-80c5-d4199b3bbcc8-TRACE.json",
    )]
    eg_calls = read("docs/evidence/vnext/m4-eg-01/runs/memory-paired-20261025T100556Z/TRACE.jsonl")
    eg_memory = [row for row in eg_calls if row.get("kind") == "provider_call"]
    eg_sla = read("docs/evidence/vnext/m4-eg-01/runs/sla-provider-20261025T101512Z/RESULTS.json")
    eg_web = read("docs/evidence/vnext/m4-eg-01/runs/web-memory-green-02/WEB-JOURNEY-RECONCILIATION.json")
    eg_web_contexts = eg_web["target"]["provider_contexts"]
    hf_latest = read("docs/evidence/vnext/m4-eg01-hf-01/TRACE.jsonl")
    output = {
        "schema": "opspilot-m4-cont-ux-01-saved-trace-audit-v1",
        "target_commit": BASE, "review_date_asia_shanghai": "2026-10-26",
        "live_provider_requests": 0, "live_mcp_calls": 0, "live_http_calls": 0,
        "new_business_tests": "NOT_RUN; PLAN/FREEZE ONLY",
        "c1_hf_journey": hf,
        "c1_rev1_hidden_chat": {"run_id": sidecar["run_id"], "attempt": {key: sidecar["attempt"].get(key) for key in ("attempt_id", "status", "input_tokens", "output_tokens", "total_tokens")}},
        "continuous_web_examples": web,
        "continuous_budget_examples": budget_examples(),
        "continuous_provider_ledger": {
            "reserve_rows": sum(row["event"] == "RESERVE" for row in ledger),
            "complete_rows": len(completes), "unique_complete_request_ids": len(set(requests)),
            "duplicate_complete_request_ids": [key for key, count in Counter(requests).items() if count > 1],
            "usage": usage_sum([row.get("usage", {}) for row in completes]),
            "rule": "deduplicated global request IDs; never sum cumulative per-case provider_requests fields",
        },
        "eg01": {
            "memory_provider_requests": len(eg_memory), "memory_usage": usage_sum([row["usage"] for row in eg_memory]),
            "sla_provider_requests": len(eg_sla["cases"]), "sla_usage": usage_sum(eg_sla["cases"]),
            "web_provider_requests": eg_web["target"]["provider_request_count"],
            "web_usage": usage_sum([row["usage"] for row in eg_web_contexts]),
            "total_requests": len(eg_memory) + len(eg_sla["cases"]) + eg_web["target"]["provider_request_count"],
            "total_usage": usage_sum([row["usage"] for row in eg_memory] + eg_sla["cases"] + [row["usage"] for row in eg_web_contexts]),
            "web_provider_context_keys": list(eg_web_contexts[0]) if eg_web_contexts else [],
            "web_business_write_counts": eg_web["target"]["business_write_counts"],
            "known_original_results_total_tokens_bug": "Memory top-level total_tokens=0 is not used; sums derive from real usage rows",
        },
        "eg01_hf_partial_facts": [{
            key: row.get(key) for key in (
                "case_id", "task_id", "investigation_run_id", "chat_run_id", "event_id",
                "http_order_status", "delivery_http_status", "chat_fact_types", "chat_fact_evidence_ids", "excluded_sources", "provider_call",
            )
        } for row in hf_latest],
        "sources": SOURCES,
        "limitations": [
            "Saved artifacts were parsed, not independently rerun; historical release versions differ.",
            "Historical estimates are not current account invoices or new effectiveness results.",
            "No sealed holdout, live DB, password or model API key was read.",
        ],
    }
    destination = Path(__file__).with_name("TRACE_AUDIT.json")
    destination.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": destination.name, "historical_hf_provider_requests": hf["provider_requests"], "vs_unique_provider_requests": len(set(requests)), "sources_read": len(SOURCES), "new_provider_requests": 0}, ensure_ascii=False))


if __name__ == "__main__":
    main()
