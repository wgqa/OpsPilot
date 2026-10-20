"""Join immutable, sanitized real-run exports. No model or Domain mutations."""
from __future__ import annotations
import hashlib
import json
import statistics
import subprocess
from collections import Counter
from pathlib import Path

BASE = Path(__file__).resolve().parent
RUN = BASE / "runs/journey-01"
snapshot = json.loads((RUN / "TRACE-P1-finished-after-restart.json").read_text(encoding="utf-8"))
tables = snapshot["tables"]
observations = [json.loads(line) for line in (RUN / "provider-observations.jsonl").read_text(encoding="utf-8").splitlines()]
requests = [o for o in observations if o["kind"] == "PROVIDER_HTTP_REQUEST"]
headers = {o["request_ref"]: o for o in observations if o["kind"] == "PROVIDER_HTTP_RESPONSE_HEADERS"}
chat = {o["attempt_id"]: o for o in tables["chat_attempts"]}
compression = {o["attempt_id"]: o for o in tables["context_compression_attempts"]}
model = {o["attempt_id"]: o for o in tables["d2_model_traces"]}
attempts = {o["attempt_id"]: o for o in tables["d2_attempts"]}
manifests = {o["attempt_id"]: o for o in tables["chat_context_manifests"]}
provenance = {o["attempt_id"]: o for o in tables["d5_context_provenance"]}
usage_rows = []
for request in requests:
    attempt_id = request["attempt_id"]
    db_row = chat.get(attempt_id) or compression.get(attempt_id) or model.get(attempt_id) or attempts.get(attempt_id)
    if db_row is None:
        raise AssertionError("Uncorrelated actual request")
    if request["request_kind"] == "INVESTIGATOR":
        usage = db_row.get("usage_json") or {}
        estimate = provenance.get(attempt_id, {}).get("context_budget_json", {}).get("estimated_input_tokens")
    else:
        usage = {key: db_row.get(key) for key in ("input_tokens", "output_tokens", "total_tokens")}
        estimate = (manifests.get(attempt_id, {}).get("truncation_json", {}).get("context_budget", {}).get("estimated_input_tokens")
                    if request["request_kind"] == "CHAT" else db_row.get("estimated_input_tokens"))
    known = all(isinstance(usage.get(key), int) for key in ("input_tokens", "output_tokens", "total_tokens"))
    usage_rows.append({
        "request_ref": request["request_ref"], "at": request["at"], "pid": request["pid"],
        "kind": request["request_kind"], "task_id": request["task_id"], "run_id": request["run_id"],
        "attempt_id": attempt_id, "call_id": request["call_id"], "prompt_digest": request["prompt_digest"],
        "body_sha256": request["body_sha256"], "actual_tool_names": request["tool_names"],
        "http_status": headers.get(request["request_ref"], {}).get("http_status"),
        "domain_attempt_status": db_row["status"], "provider_response_id": db_row.get("provider_response_id"),
        "usage_status": "KNOWN_PROVIDER_REPORTED" if known else "UNKNOWN_NOT_ZERO",
        "usage": usage if known else None, "local_estimated_input_tokens": estimate,
        "actual_minus_estimated_input": usage["input_tokens"] - estimate if known and isinstance(estimate, int) else None,
        "asset_sets_match": request["asset_sets_match"], "all_memory_fields_match": request["all_memory_fields_match"],
        "request_body_unchanged": request["request_body_unchanged"],
        "actual_asset_set": request["actual_asset_set"], "actual_summaries": request["actual_summaries"],
        "actual_evidence_ids": request["actual_evidence_ids"], "excluded_sources": request["excluded_sources"],
        "excluded_message_checks": request["excluded_message_checks"],
        "excluded_summaries_absent": request["excluded_summaries_absent"],
        "compression_material_checks": request["compression_material_checks"],
    })

known = [r for r in usage_rows if r["usage_status"] == "KNOWN_PROVIDER_REPORTED"]
unknown = [r for r in usage_rows if r["usage_status"] != "KNOWN_PROVIDER_REPORTED"]
token_totals = {key: sum(r["usage"][key] for r in known) for key in ("input_tokens", "output_tokens", "total_tokens")}
deviations = [r["actual_minus_estimated_input"] for r in known if r["actual_minus_estimated_input"] is not None]
ratios = [r["usage"]["input_tokens"] / r["local_estimated_input_tokens"] for r in known if r["local_estimated_input_tokens"]]
by_kind = {}
for kind in ("CHAT", "INVESTIGATOR", "COMPRESSION"):
    group = [r for r in usage_rows if r["kind"] == kind]
    by_kind[kind] = {"actual_requests": len(group), "known_usage": sum(r["usage"] is not None for r in group),
                     "unknown_usage": sum(r["usage"] is None for r in group),
                     **{key: sum((r["usage"] or {}).get(key, 0) for r in group) for key in token_totals}}

a_validation = json.loads((RUN / "A-VALIDATION.json").read_text(encoding="utf-8"))
b_ids = json.loads((RUN / "B-identities.json").read_text(encoding="utf-8"))
p1_ids = json.loads((RUN / "P1-identities.json").read_text(encoding="utf-8"))
assets = {r["memory_id"]: r for r in tables["d5_memories"]}
scope_initial = json.loads((RUN / "fixture-initial.json").read_text(encoding="utf-8"))
def normalize_json_columns(rows):
    return [{k: json.loads(v) if k.endswith("_json") and isinstance(v, str) else v for k, v in row.items()} for row in rows]


scope_unchanged = all(normalize_json_columns(scope_initial[t]) == tables[t] for t in ("principal_scope_grants", "route_scope_policies"))
diff = subprocess.check_output(["git", "diff", "c2f71e9", "--numstat", "--", "opspilot", "tests"], text=True).strip()
commit_rows = [line.split(" ", 1) for line in subprocess.check_output(["git", "log", "--reverse", "--format=%H %s", "c2f71e9..HEAD"], text=True).splitlines()]
checks = {
    "all_actual_requests_correlated": all(r["attempt_id"] for r in usage_rows),
    "asset_set_and_content_match": all(r["asset_sets_match"] and r["all_memory_fields_match"] for r in requests),
    "request_body_unchanged": all(r["request_body_unchanged"] for r in requests),
    "excluded_messages_absent_from_actual_payload": all(not m["actual_request_has_identical_assistant"] for r in requests for m in r["excluded_message_checks"]),
    "excluded_summaries_absent_from_actual_payload": all(r["excluded_summaries_absent"] for r in requests),
    "compression_source_material_matches": all(c["matches_reserved_source_material"] for r in requests for c in r["compression_material_checks"]),
    "no_observer_error": not any(r["kind"] == "OBSERVER_ERROR" for r in observations),
    "scope_runtime_writes_zero": scope_unchanged,
    "all_three_case_memories_finally_revoked": len(assets) == 3 and all(r["state"] == "REVOKED" for r in assets.values()),
    "three_genuine_source_verifications": len(tables["d3_verification_receipts"]) == 3 and all(r["response_status"] == 200 and r["recovery_verified"] == 1 for r in tables["d3_verification_receipts"]),
    "final_target_has_no_business_ledger": not any(r["task_id"] == p1_ids["target_task_id"] for r in tables["d3_action_ledgers"]),
}
trace = {
    "schema_version": "opspilot-m3-hf02-trace-v1", "baseline_sha": "c2f71e9b4e3db9fdc3cd522115f304e6a53dfaae",
    "code_fix_sha": "00d054aeba196b972255dafd0e7faa03fcd0ce41", "commits_before_evidence": commit_rows,
    "observation_file": "runs/journey-01/provider-observations.jsonl", "domain_export": "runs/journey-01/TRACE-P1-finished-after-restart.json",
    "requests": usage_rows, "unknown_requests": unknown, "provider_known_token_lower_bound": token_totals,
    "request_stats_by_kind": by_kind, "observer_boots": [r for r in observations if r["kind"] == "OBSERVER_BOOT"],
    "process_events": [json.loads(l) for l in (RUN / "process-events.jsonl").read_text(encoding="utf-8").splitlines()],
    "memory_records": tables["d5_memories"], "memory_events": tables["d5_memory_events"],
    "summaries": tables["context_summaries"], "summary_dependencies": tables["context_summary_dependencies"],
    "compression_attempts": tables["context_compression_attempts"],
    "business_ledgers": tables["d3_action_ledgers"], "verifications": tables["d3_verification_receipts"],
    "deliveries": tables["d3_delivery_records"], "scope_unchanged": scope_unchanged,
    "currency_cost": "UNKNOWN_PROVIDER_PRICE_OR_BILL_NOT_CAPTURED; unknown requests must not be valued as zero",
    "raw_prompt_exported": False,
}
results = {
    "schema_version": "opspilot-m3-hf02-results-v1", "review_status": "PENDING_INDEPENDENT_MAIN_AGENT",
    "overall": "A_TECHNICAL_PASS_B_PARTIAL_C_COMPLETED_WITH_LIMITS",
    "baseline_sha": trace["baseline_sha"], "freeze_sha": commit_rows[0][0], "red_sha": "ba44a5c36ab37ab000096e042e23c6b7f022b6b0",
    "fix_sha": trace["code_fix_sha"], "evidence_sha_resolution": "git rev-parse HEAD after final evidence commit; no self-referential SHA embedded",
    "stage_A": {"status": "TECHNICAL_PASS", "checks": a_validation["checks"], "direct_payload_gap": "CLOSED",
                "strict_E2E03": "PASS_CANDIDATE_PENDING_MAIN_AGENT", "historical_closeout_partial_unchanged": True,
                "qualification": "A direct lineage and same-Run recovery are fresh baseline-code runs; final fix has 26 targeted/227 full and new actual-payload checks, but transitive post-revoke real isolation remains unproven due TTL confound."},
    "stage_B": {"status": "PARTIAL", "target_memory_summary_dag_proven": False,
                "original_active_turns": 8, "original_revoked_turns": 2, "original_persisted_summaries": 1,
                "persisted_summary_has_target_memory_dependency": False, "original_failed_compressions": 1,
                "postfix_active_turns": 8, "postfix_revoked_turns": 2, "postfix_persisted_summaries": 0,
                "postfix_failed_compressions": 1, "frozen_input_budget": 3600, "increased_budget_or_rounds": False,
                "reason": "Evidence TTL elapsed while actual compression was in flight. Valid-history rebuild made compression no longer required; exact TaskControlError code not persisted. No target Summary was committed; revocation follows expiry, so causality is not isolated."},
    "stage_C": {"status": "COMPLETED_WITH_LIMITS", "worker": "ROOT_CAUSE_NOT_PROVEN", "bounded_fault_probes": {"passed": 2, "total": 2},
                "confirmed_P1": "MODEL_ATTEMPT ancestor source validity", "P1_fix": "35 lines in existing validation, no schema/transaction/runtime changes", "new_lineage_tests": {"red_valid_failures": 2, "green_passed": 2}, "learning_files": 5, "interview_questions": 20},
    "regression": {"full_pytest": {"passed": 227, "total": 227, "seconds": 162.42, "exit_code": 0, "log": "runs/regression-02/pytest-full.log"},
                   "targeted": {"passed": 26, "total": 26, "seconds": 14.38, "exit_code": 0, "log": "runs/lineage-green-01.log"},
                   "frontend": {"typecheck": 0, "build": 0, "lint": 0}, "pre_fix_full": {"passed": 225, "total": 225}},
    "real_calls": {"serialized_provider_http_requests": len(requests), "http_200_response_headers": len(headers),
                   "provider_usage_known": len(known), "provider_usage_unknown": len(unknown), "by_kind": by_kind,
                   "mcp_stdio_tools_call_attempts": len([r for r in tables["d2_attempts"] if r["kind"] == "MCP"]),
                   "mcp_observations": len(tables["d2_tool_observations"]), "tools_list_count": "NOT_SEPARATELY_INSTRUMENTED",
                   "chat_completed_runs": len([r for r in tables["task_runs"] if r["kind"] == "CHAT_READONLY" and r["status"] == "SUCCEEDED"])},
    "tokens_known_lower_bound": token_totals,
    "token_estimate_comparison": {"paired_known_requests": len(deviations), "min_actual_minus_estimate": min(deviations),
                                  "max_actual_minus_estimate": max(deviations), "mean_actual_minus_estimate": round(statistics.mean(deviations), 3),
                                  "mean_provider_input_over_local_estimate": round(statistics.mean(ratios), 4),
                                  "not_a_provider_window_or_billing_guarantee": True},
    "safety_checks": checks, "safety_check_count": {"passed": sum(checks.values()), "total": len(checks)},
    "actions": {"committed_REPAIR": 3, "committed_DELIVER": 3, "explicit_fixture_preparations": 3, "fixture_actions_are_agent_recovery": False,
                "scope_writes": 0, "final_target_actions": 0, "business_contract_changed": False},
    "production_test_diff_numstat": diff, "no_dependency_upgrade": True, "no_next_phase_started": True,
    "limits": ["Target real Summary DAG unproven; B remains PARTIAL", "Postfix revocation causal isolation confounded by earlier Evidence TTL",
               "Historical Worker root cause unproven", "Three real requests have unknown usage/cost", "Demo identities are not production IAM", "No new ON/OFF utility evaluation"],
}
for name, value in (("TRACE.json", trace), ("RESULTS.json", results)):
    (BASE / name).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps({"requests": len(requests), "known_usage": len(known), "unknown_usage": len(unknown), "tokens": token_totals,
                  "by_kind": by_kind, "checks": checks, "estimate_comparison": results["token_estimate_comparison"]}, ensure_ascii=False))
