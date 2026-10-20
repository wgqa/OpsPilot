"""Offline evidence index for this run only; never alters a Domain or calls a model."""
from __future__ import annotations

import hashlib
import importlib.metadata
import json
import platform
import re
import sqlite3
import subprocess
from collections import Counter
from pathlib import Path

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[3]
JOURNEY = BASE / "runs/journey-01"
REGRESSION = BASE / "runs/regression-01"
BASELINE = "95b235f29af2df40b1608c23e3bf15acbaf25c26"


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


raw = read(JOURNEY / "TRACE-final-domain.json")
t = raw["tables"]
memory = t["d5_memories"][0]
task_a = memory["source_task_id"]
task_b = next(r["task_id"] for r in t["task_bindings"] if r["task_id"] != task_a)
runs = {r["run_id"]: r for r in t["task_runs"]}
attempts = {r["attempt_id"]: r for r in t["d2_attempts"]}
crash = read(JOURNEY / "crash-trigger.json")
resume_run = crash["run"]["run_id"]
initial_b_run = next(r["run_id"] for r in runs.values() if r["task_id"] == task_b and r["kind"] == "INVESTIGATE")
fixture = read(JOURNEY / "fixture-second-incident.json")
initial = read(JOURNEY / "fixture-initial-state.json")["state"]
for rows in initial.values():
    for row in rows:
        for key, value in row.items():
            if key.endswith("_json") and isinstance(value, str):
                row[key] = json.loads(value)
process_events = [json.loads(s) for s in (JOURNEY / "process-events.jsonl").read_text(encoding="utf-8").splitlines()]
observer = [json.loads(s) for s in (JOURNEY / "provider-wire.jsonl").read_text(encoding="utf-8").splitlines()]
wire_requests = [r for r in observer if r["kind"] == "PROVIDER_REQUEST"]

usage = {}
for run in runs.values():
    model_attempts = [r for r in attempts.values() if r["run_id"] == run["run_id"] and r["kind"] == "MODEL"]
    traces = [r for r in t["d2_model_traces"] if attempts[r["attempt_id"]]["run_id"] == run["run_id"]]
    chat = [r for r in t["chat_attempts"] if r["run_id"] == run["run_id"]]
    usages = [r["usage_json"] for r in traces] + chat
    usage[run["run_id"]] = {
        "task_id": run["task_id"], "kind": run["kind"], "status": run["status"],
        "model_reservations": len(model_attempts) + len(chat),
        "provider_responses_with_usage": len(usages),
        "mcp_attempts": sum(r["run_id"] == run["run_id"] and r["kind"] == "MCP" for r in attempts.values()),
        "known_input_tokens": sum(r.get("input_tokens", 0) or 0 for r in usages),
        "known_output_tokens": sum(r.get("output_tokens", 0) or 0 for r in usages),
        "known_total_tokens": sum(r.get("total_tokens", 0) or 0 for r in usages),
        "unknown_usage_attempt_ids": [r["attempt_id"] for r in model_attempts if r["status"] != "OK"],
        "provider_response_ids": [r["provider_response_id"] for r in traces + chat],
        "monetary_cost": "NOT_REPORTED",
    }

selected_b = [r for r in t["d5_context_provenance"] if r["task_id"] == task_b and r["selected_memories_json"]]
resume_contexts = [r for r in t["d5_context_provenance"] if attempts[r["attempt_id"]]["run_id"] == resume_run]
post_chat = next(r for r in t["chat_context_manifests"] if not r["memory_refs_json"])
verification = t["d3_verification_receipts"][0]
intent_by_id = {r["action_id"]: r for r in t["d3_action_intents"]}
scope_unchanged = all(initial[k] == t[k] for k in ("principal_scope_grants", "route_scope_policies"))
checks = {
    "different_source_and_target_tasks": task_a != task_b,
    "same_tenant_project_binding": all(r["tenant_id"] == "tenant-a" and r["service_id"] == "orders-demo" for r in t["task_bindings"]),
    "verification_real_200_and_order_fields": verification["response_status"] == 200 and verification["recovery_verified"] == 1 and all(verification["business_assertions_json"][k] is True for k in ("same_service", "same_integration", "same_principal", "same_business_route", "order_id_matches", "order_status_matches")),
    "single_approved_repair_and_delivery": Counter(r["action_kind"] for r in t["d3_action_ledgers"]) == {"REPAIR": 1, "DELIVER": 1} and len(t["d3_approvals"]) == 1,
    "intents_precede_matching_ledger_commits": all(intent_by_id[r["action_id"]]["created_at"] < r["committed_at"] and intent_by_id[r["action_id"]]["request_digest"] == r["request_digest"] for r in t["d3_action_ledgers"]),
    "all_business_actions_belong_to_task_a": all(r["task_id"] == task_a for r in t["d3_action_ledgers"] + t["d3_action_intents"] + t["d3_approvals"]),
    "no_scope_writes_in_journey": scope_unchanged,
    "separate_fixture_setup_invariants": all(fixture["unchanged"].values()) and fixture["new_config_version"] == 9,
    "episodic_confirmed_then_revoked": memory["type"] == "EPISODIC" and memory["state"] == "REVOKED" and memory["version"] == 3 and [(r["event_type"], r["memory_version"]) for r in t["d5_memory_events"]] == [("CANDIDATE_CREATED", 1), ("CONFIRMED", 2), ("REVOKED", 3)],
    "independent_approver_events": all(r["actor_id"] == "approver-a" for r in t["d5_memory_events"] if r["event_type"] in {"CONFIRMED", "REVOKED"}),
    "task_b_selected_v2_in_provenance": len(selected_b) == 4 and all(r["selected_memories_json"][0]["version"] == 2 and r["selected_memories_json"][0]["digest"] == memory["content_digest"] for r in selected_b),
    "post_revoke_chat_excludes_dependent_assistant": any(r.get("reason") == "MEMORY_REVOKED_EXPIRED_OR_CHANGED" for r in post_chat["excluded_sources_json"]),
    "same_run_resumed_without_memory_in_provenance": runs[resume_run]["status"] == "WAITING_APPROVAL" and all(not r["selected_memories_json"] for r in resume_contexts),
    "resume_records_revocation_reason": any(r.get("reason") == "MEMORY_REVOKED" for c in resume_contexts for r in c["excluded_sources_json"]),
    "task_budget_not_reset": sum(r["kind"] == "MODEL" and r["task_id"] == task_b for r in attempts.values()) == 8 and sum(r["kind"] == "MCP" and r["task_id"] == task_b for r in attempts.values()) == 6,
    "no_semantic_substitution": not t["semantic_memories"],
}
assert all(checks.values()), {k: v for k, v in checks.items() if not v}

tests = {}
for name in ("pytest-full", "pytest-focused", "frontend-typecheck", "frontend-build", "frontend-lint"):
    log = (REGRESSION / f"{name}.log").read_text(encoding="utf-8-sig")
    code = int((REGRESSION / f"{name}.exit-code.txt").read_text(encoding="utf-8-sig").strip())
    match = re.search(r"(\d+) passed in ([\d.]+)s", log)
    tests[name] = {"exit_code": code, "log": f"runs/regression-01/{name}.log", "status": "PASS" if code == 0 else "FAIL"}
    if match:
        tests[name].update(passed=int(match[1]), seconds=float(match[2]))
assert tests["pytest-full"]["passed"] == 225 and tests["pytest-focused"]["passed"] == 24
assert all(r["exit_code"] == 0 for r in tests.values())

criteria = [
    (1, "新鲜真实Task A可信业务结果", "PASS"),
    (2, "Episodic Candidate合法来源", "PASS"),
    (3, "独立Approver真实Web确认", "PASS"),
    (4, "不同Task B真实Provider/MCP使用有效经验", "PARTIAL"),
    (5, "Web撤销与Domain事件", "PASS"),
    (6, "撤销后新Provider请求实际内容排除Memory", "PARTIAL"),
    (7, "同Run跨进程恢复、撤销与预算", "PARTIAL"),
    (8, "安全及新鲜全量回归", "PASS"),
    (9, "如实保留失败、成本缺口与环境限制", "PASS"),
    (10, "范围内未新增业务或架构", "PASS"),
]
result = {
    "release": "M3-CLOSEOUT-01", "status": "PARTIAL", "independent_acceptance": "PENDING_MAIN_AGENT",
    "baseline_sha": BASELINE,
    "scope_commit": "936c2c59f8ca13ea7187e6f25559f600d676405b",
    "fixture_supplement_commit": "6f5249412f0420523c8476e300a523bd8a7e53b3",
    "production_source_changes": 0, "test_case_changes": 0,
    "criteria": [{"id": n, "title": title, "status": status, "evidence": ["REPORT.md", "TRACE.json", "runs/journey-01/TRACE-final-domain.json"]} for n, title, status in criteria],
    "evidence_gap": {"id": "GAP-01", "actual_provider_request_bodies": "NOT_CAPTURED", "captured_request_count": len(wire_requests), "cause": "Observer patched httpx; installed OpenAI SDK uses httpx2", "domain_provenance_and_real_response_usage": "AVAILABLE", "consequence": "Cannot independently inspect actual transmitted memory content or absence from raw Provider request bodies; no PASS_CANDIDATE"},
    "ids": {"task_a": task_a, "task_b": task_b, "task_b_initial_run": initial_b_run, "same_run_recovery": resume_run, "memory_id": memory["memory_id"], "memory_digest": memory["content_digest"], "checkpoint_thread": crash["checkpoint_thread"]},
    "computed_domain_checks": checks, "tests": tests, "usage_by_run": usage,
    "counts": {"known_provider_responses": sum(r["provider_responses_with_usage"] for r in usage.values()), "model_reservations_including_chat": sum(r["model_reservations"] for r in usage.values()), "mcp_tools_call_attempts": sum(r["kind"] == "MCP" for r in attempts.values()), "mcp_tool_observations": len(t["d2_tool_observations"]), "mcp_tools_list_raw_count": "NOT_SEPARATELY_CAPTURED", "business_http_requests": len(t["auth_events"]), "known_total_tokens": sum(r["known_total_tokens"] for r in usage.values())},
    "cost_gaps": {"interrupted_attempt": "attempt-52e3a93b-7e05-421e-a1e5-3f0e759e3ebc", "provider_received_request": "UNKNOWN", "interrupted_usage": "UNKNOWN", "interrupted_cost": "UNKNOWN", "all_monetary_costs": "NOT_REPORTED"},
    "summary_dag_real_journey": {"status": "NOT_COVERED", "summary_count": len(t["context_summaries"]), "reason": "No dependent summary naturally generated; separate fresh test_hybrid_context_compression_commits_versioned_source_linked_summary checks message -> summary -> assistant invalidation, not a real Episodic-revocation summary journey"},
    "fixture_setup_separate_from_agent": "CASE-B-SETUP.md and runs/journey-01/fixture-second-incident.json",
    "runtime_stopped": process_events[-1]["kind"] == "OWNED_SERVICES_STOPPED",
    "next_step": "STOP; main Agent independent review and user project retrospective; no M4",
}
save(BASE / "RESULTS.json", result)

events = []
def add(at, kind, source, **refs):
    events.append({"at_utc": at, "kind": kind, "source": source, **refs})

for e in process_events:
    add(e["at"], e["kind"], "runs/journey-01/process-events.jsonl", details=e)
for e in t["d5_memory_events"]:
    add(e["occurred_at"], e["event_type"], "tables.d5_memory_events", **e)
for e in t["task_runs"]:
    add(e["created_at"], "RUN_ACCEPTED", "tables.task_runs", run_id=e["run_id"], task_id=e["task_id"], run_kind=e["kind"], final_status=e["status"])
for e in t["d5_context_provenance"]:
    add(e["built_at"], "MODEL_CONTEXT_RESERVED", "tables.d5_context_provenance", call_id=e["call_id"], run_id=attempts[e["attempt_id"]]["run_id"], task_id=e["task_id"], attempt_id=e["attempt_id"], prompt_digest=e["prompt_digest"], selected_memories=e["selected_memories_json"], excluded_sources=e["excluded_sources_json"], model_status=e["model_status"], raw_provider_body="NOT_CAPTURED")
for e in t["chat_context_manifests"]:
    add(e["created_at"], "CHAT_CONTEXT_RESERVED", "tables.chat_context_manifests", run_id=e["run_id"], task_id=e["task_id"], attempt_id=e["attempt_id"], prompt_digest=e["prompt_digest"], memory_refs=e["memory_refs_json"], excluded_sources=e["excluded_sources_json"], raw_provider_body="NOT_CAPTURED")
for e in t["d2_tool_observations"]:
    add(e["created_at"], "MCP_TOOL_RESULT", "tables.d2_tool_observations", run_id=attempts[e["attempt_id"]]["run_id"], **e)
for e in t["d3_approvals"]:
    add(e["decided_at"], "APPROVAL", "tables.d3_approvals", **e)
for e in t["d3_action_ledgers"]:
    add(e["committed_at"], "BUSINESS_ACTION_COMMITTED", "tables.d3_action_ledgers", **e)
for e in t["d3_verification_receipts"]:
    add(e["observed_at"], "VERIFICATION", "tables.d3_verification_receipts", **e)
for e in t["d3_delivery_records"]:
    add(e["committed_at"], "DELIVERY", "tables.d3_delivery_records", **e)
add(fixture["at"], "EXPLICIT_TEST_SETUP_NOT_AGENT_ACTION", "runs/journey-01/fixture-second-incident.json", source_function=fixture["source_function"], setup_commit=fixture["setup_commit"], new_config_version=9)
events.sort(key=lambda e: e["at_utc"].replace(" ", "T"))
save(BASE / "TRACE.json", {"source_snapshot": "runs/journey-01/TRACE-final-domain.json", "timestamp_note": "Naive database timestamps are UTC; browser renders Asia/Shanghai", "raw_provider_body_gap": "GAP-01", "events": events, "usage_by_run": usage, "checkpoint_counts": raw["checkpoint_counts"]})

packages = ("fastapi", "langgraph", "mcp", "tiktoken", "langchain-openai", "openai", "httpx", "httpx2", "pytest")
save(BASE / "runs/environment.json", {
    "python": platform.python_version(), "sqlite": sqlite3.sqlite_version,
    "packages": {p: importlib.metadata.version(p) for p in packages},
    "node": subprocess.check_output(["node", "--version"], text=True).strip(),
    "npm": subprocess.check_output(["cmd", "/c", "npm --version"], text=True).strip(),
    "frontend_lock_versions": {p: read(ROOT / "frontend/package-lock.json")["packages"]["node_modules/" + p]["version"] for p in ("vue", "vite", "typescript")},
    "locks_sha256": {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in ("requirements.lock.txt", "frontend/package-lock.json")},
    "model_id": "deepseek-flash", "model_key": "LOCAL_ENV_VALUE_OMITTED", "model_endpoint": "LOCAL_ENV_VALUE_OMITTED",
    "loaded_source_sha256": observer[1]["source_hashes"],
    "boot_pids": [r["pid"] for r in observer],
    "boot_note": "First PID 37468 exited before import succeeded; actual successful API processes 19320 and 38868",
})
print(json.dumps({"status": result["status"], "domain_checks": len(checks), "counts": result["counts"], "usage": usage}, ensure_ascii=False))
