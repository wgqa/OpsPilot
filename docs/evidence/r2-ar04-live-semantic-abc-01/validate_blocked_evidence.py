"""Validate the zero-send, preflight-blocked R2-AR04 evidence package."""

from __future__ import annotations

import gzip
import hashlib
import json
from decimal import Decimal
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
EVIDENCE = Path(__file__).resolve().parent


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(f"INVALID: {message}")


preflight = json.loads((EVIDENCE / "PREFLIGHT.json").read_text(encoding="utf-8"))
results = json.loads((EVIDENCE / "LIVE_RESULTS.json").read_text(encoding="utf-8"))
ledger = json.loads((EVIDENCE / "COST_LEDGER.json").read_text(encoding="utf-8"))
setup_results = json.loads(
    (ROOT / "docs/evidence/r2-ar04-live-eval-setup-hf01/TEST_RESULTS.json").read_text(encoding="utf-8")
)

require(preflight["status"] == "BLOCKED_BEFORE_PROVIDER_SEND", "preflight status drift")
require(preflight["provider_requests_before"] == 0, "preflight request counter is nonzero")
require(preflight["provider_requests_sent"] == 0, "preflight reports a sent request")
require(preflight["credential_and_runtime_preflight"]["api_key_present"] is False, "credential result drift")
require(preflight["credential_and_runtime_preflight"]["runtime_grant_created"] is False, "live Grant was recorded as created")

require(results["status"] == "BLOCKED_BEFORE_PROVIDER_SEND", "result status drift")
require(results["provider_requests_sent"] == 0, "result request counter is nonzero")
require(results["summary_requests_sent"] == 0, "result summary counter is nonzero")
require(results["answer_requests_sent"] == 0, "result answer counter is nonzero")
require(results["provider_unknown_count"] == 0 and results["retries"] == 0, "unexpected UNKNOWN or retry count")
require(results["answers"] == [], "blocked result package must not contain answers")
require(results["main_agent_independent_review"] == "NOT_PERFORMED", "main-agent review attribution drift")
require(results["implementer_semantic_review"] == "NOT_RUN_NO_LIVE_ANSWERS", "implementer review attribution drift")

rows = results["rows"]
expected = {(q, g) for q in ("Q02", "Q03", "Q06") for g in ("A", "B", "C")}
actual = {(row["question_id"], row["group"]) for row in rows}
require(len(rows) == 9 and actual == expected, "the nine fixed slots are not represented exactly once")
require(all(row["status"] == "BLOCKED_BEFORE_PROVIDER_SEND" for row in rows), "a slot is not blocked")
require(all(row["l2"] == "BLOCKED" and row["l3"] == "BLOCKED" for row in rows), "blocked L2/L3 status drift")
require(all(row["provider_requests"] == row["summary_requests"] == 0 for row in rows), "slot contains a send")
require(all(row["answer"] is None and row["summary"] is None and row["provider_request_ids"] == [] for row in rows), "slot contains fabricated live output")

require(ledger["provider_requests_sent"] == ledger["summary_requests_sent"] == ledger["answer_requests_sent"] == 0, "cost ledger send counters are nonzero")
require(ledger["unknown_requests"] == ledger["automatic_retries"] == ledger["grants_created"] == 0, "cost ledger has unexpected activity")
require(Decimal(ledger["reserved_usd"]) == 0 and Decimal(ledger["settled_usd_estimate"]) == 0, "cost ledger has a reserve or settlement")
require(Decimal(ledger["hard_usd_cap"]) == Decimal("0.15"), "hard cap drift")
per_request = (Decimal(12000) * Decimal("0.30") + Decimal(512) * Decimal("1.20")) / Decimal(1_000_000)
require(per_request == Decimal(ledger["per_request_worst_case_usd"]), "per-request budget arithmetic drift")
require(per_request * 21 == Decimal(ledger["full_schedule_worst_case_usd"]), "schedule budget arithmetic drift")
require(per_request * 21 < Decimal(ledger["hard_usd_cap"]), "frozen schedule exceeds the hard cap")

with gzip.open(EVIDENCE / "LIVE_REQUESTS.jsonl.gz", "rb") as archive:
    require(archive.read() == b"", "blocked request archive is not empty")

frozen = preflight["frozen_phase_a_inputs"]
phase_a = ROOT / "docs/evidence/r2-ar04-long-context-journey-01"
for key, name in (
    ("questions_sha256", "QUESTIONS.json"),
    ("history_snapshot_sha256", "HISTORY_SNAPSHOT.json"),
    ("phase_a_results_sha256", "RESULTS.json"),
    ("phase_a_model_requests_sha256", "MODEL_REQUESTS.jsonl.gz"),
):
    require(sha256(phase_a / name) == frozen[key], f"frozen Phase A input changed: {name}")

protected_paths = {
    "phase_a_live_eval_proposal": ROOT / "docs/evidence/r2-ar04-long-context-journey-01/LIVE_EVAL_PROPOSAL.md",
    "phase_a_runner": ROOT / "docs/evidence/r2-ar04-long-context-journey-01/run_long_context_eval.py",
    "setup_hf01_test_results": ROOT / "docs/evidence/r2-ar04-live-eval-setup-hf01/TEST_RESULTS.json",
    "setup_hf01_mock_trace": ROOT / "docs/evidence/r2-ar04-live-eval-setup-hf01/MOCK_TRACE.jsonl.gz",
    "setup_hf01_test_run": ROOT / "docs/evidence/r2-ar04-live-eval-setup-hf01/TEST_RUN.txt",
    "setup_hf01_harness": ROOT / "docs/evidence/r2-ar04-live-eval-setup-hf01/test_offline_harness.py",
    "previous_pilot_plan": ROOT / "docs/evidence/r2-ar04-live-semantic-pilot-01/PLAN.md",
    "previous_pilot_preflight": ROOT / "docs/evidence/r2-ar04-live-semantic-pilot-01/PREFLIGHT.json",
    "previous_pilot_results": ROOT / "docs/evidence/r2-ar04-live-semantic-pilot-01/RESULTS.json",
    "previous_pilot_trace": ROOT / "docs/evidence/r2-ar04-live-semantic-pilot-01/LIVE_REQUESTS.jsonl.gz",
    "previous_pilot_cost_ledger": ROOT / "docs/evidence/r2-ar04-live-semantic-pilot-01/COST_LEDGER.json",
    "previous_pilot_score_script": ROOT / "docs/evidence/r2-ar04-live-semantic-pilot-01/score_live_results.py",
    "compaction_results_including_c06_red": ROOT / "docs/evidence/r2-ar04-compaction-audit-01/RESULTS.json",
    "compaction_test_run": ROOT / "docs/evidence/r2-ar04-compaction-audit-01/TEST_RUN.txt",
    "c06_user_oversize_trace": ROOT / "docs/evidence/r2-ar04-compaction-audit-01/case_traces/C06_USER_OVERSIZE.json",
    "c06_assistant_excerpt_trace": ROOT / "docs/evidence/r2-ar04-compaction-audit-01/case_traces/C06_ASSISTANT_EXCERPT.json",
    "wp3_information_retention_trace": ROOT / "docs/evidence/r2-ar04-compaction-audit-01/case_traces/WP3_INFORMATION_RETENTION.json",
}
protected_hashes = preflight["protected_historical_artifact_sha256"]
for key, path in protected_paths.items():
    require(sha256(path) == protected_hashes[key], f"protected historical artifact changed: {key}")

trace_path = ROOT / "docs/evidence/r2-ar04-live-eval-setup-hf01/MOCK_TRACE.jsonl.gz"
with gzip.open(trace_path, "rt", encoding="utf-8") as source:
    trace = [json.loads(line) for line in source if line.strip()]
expected_tools = preflight["strategy_parity_preflight"]["current_runtime_tool_names"]
schema_digest = preflight["strategy_parity_preflight"]["current_runtime_tool_schema_sha256"]
prefix_digest = preflight["strategy_parity_preflight"]["current_trusted_system_prompt_prefix_sha256"]
for question_id in ("Q02", "Q03", "Q06"):
    rows_for_question = [
        item for item in trace
        if item.get("track") == "history_recall"
        and item.get("case_id", "").endswith(f"-{question_id}-recall")
        and item.get("request_payload", {}).get("tools")
    ]
    require({item["group"] for item in rows_for_question} == {"A", "B", "C"}, f"missing Mock groups for {question_id}")
    for item in rows_for_question:
        payload = item["request_payload"]
        digest = hashlib.sha256(canonical(payload["tools"]).encode("utf-8")).hexdigest()
        names = [tool["function"]["name"] for tool in payload["tools"]]
        require(digest == schema_digest, f"Mock schema mismatch for {question_id}/{item['group']}")
        require(names == expected_tools, f"Mock tool-set mismatch for {question_id}/{item['group']}")
        require(item["system_prompt_prefix_sha256"] == prefix_digest, f"trusted prompt mismatch for {question_id}/{item['group']}")
        require(payload.get("tool_choice") == "none", f"tool_choice drift for {question_id}/{item['group']}")
        require(payload.get("model") == "deepseek-flash", f"model alias drift for {question_id}/{item['group']}")

print("slots=9/9 blocked; evidence invariants validated (offline only); live semantic evaluation=NOT_RUN")
