"""Offline consistency checks for the bounded live evaluation evidence."""
from __future__ import annotations

import gzip
import hashlib
import json
import pathlib
from decimal import Decimal


ROOT = pathlib.Path(__file__).resolve().parents[3]
EVIDENCE = pathlib.Path(__file__).resolve().parent
PHASE_A = ROOT / "docs/evidence/r2-ar04-long-context-journey-01"
REQUEST_IDS = ["Q02", "Q03", "Q06"]
GROUPS = ["A", "B", "C", "D"]
QUESTION_IDS = ["Q02", "Q03", "Q06", "Q07", "Q08", "Q10", "Q12"]


def read_json(path: pathlib.Path):
    return json.loads(path.read_text(encoding="utf-8"))


def digest(value: str | bytes) -> str:
    raw = value.encode("utf-8") if isinstance(value, str) else value
    return hashlib.sha256(raw).hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(f"VALIDATION_FAILED: {message}")


def main() -> int:
    required_files = ["PLAN.md", "PREFLIGHT.json", "RESULTS.json", "LIVE_REQUESTS.jsonl.gz",
                      "COST_LEDGER.json", "COMPARISON.md", "FAILURE_ANALYSIS.md", "TEST_RUN.txt",
                      "run_direct_reference.py", "score_live_results.py", "validate_live_evidence.py"]
    require(all((EVIDENCE / name).is_file() for name in required_files), "required evidence file missing")
    preflight = read_json(EVIDENCE / "PREFLIGHT.json")
    results = read_json(EVIDENCE / "RESULTS.json")
    ledger = read_json(EVIDENCE / "COST_LEDGER.json")
    require(preflight["provider_requests_at_preflight"] == 0, "preflight was not zero-request")
    require(preflight["direct_d_ready"] and preflight["input_checks"]["errors"] == [], "D preflight did not pass")
    require(preflight["base_sha"] == "fd941299966f6cc54ae35be3102f071d2be29acc", "Base drift")
    require(len(results["rows"]) == 28, "answer slot count drift")
    require(len({(row["group"], row["question_id"]) for row in results["rows"]}) == 28,
            "duplicate or missing answer slot")
    for group in GROUPS:
        for qid in QUESTION_IDS:
            require(sum(row["group"] == group and row["question_id"] == qid for row in results["rows"]) == 1,
                    f"slot missing or duplicated: {group}/{qid}")
    request_events = []
    response_events = []
    with gzip.open(EVIDENCE / "LIVE_REQUESTS.jsonl.gz", "rt", encoding="utf-8") as handle:
        events = [json.loads(line) for line in handle]
    request_events = [event for event in events if event["event"] == "REQUEST_RESERVED_AND_SENT_ONCE"]
    response_events = [event for event in events if event["event"] == "PROVIDER_RESPONSE"]
    require(len(events) == 6 and len(request_events) == 3 and len(response_events) == 3,
            "raw request/response event count mismatch")
    require({event["logical_request_id"] for event in request_events}
            == {f"D-{qid}-answer" for qid in REQUEST_IDS}, "unexpected live request IDs")
    for event in request_events:
        require(event["authorization_header_saved"] is False, "authorization header marked as saved")
        require(event["headers_saved"] == ["Content-Type"], "unexpected saved request headers")
        require(event["provider_url"] == "https://api.deepseek.com/chat/completions", "non-official endpoint")
        require(event["request_digest"] == digest(json.dumps(event["request"], ensure_ascii=False,
                                                               sort_keys=True, separators=(",", ":"))),
                "request digest mismatch")
        require(event["request"]["model"] == "deepseek-flash", "model alias drift")
        require(event["request"]["thinking"] == {"type": "disabled"}, "thinking mode drift")
        require(event["request"]["temperature"] == 0 and event["request"]["max_tokens"] == 512,
                "generation parameter drift")
    response_ids = {event["response"].get("id") for event in response_events}
    require(response_ids == {
        "e2218b38-9c49-4b5a-ac77-6289c459c9fd",
        "8850e205-aef7-48f6-8a90-de8ddb027de7",
        "68aab07c-7a64-4ba9-891d-3baf6018101e",
    }, "Provider response ID mismatch")
    require(ledger["provider_requests_sent"] == 3 and ledger["provider_unknown_count"] == 0,
            "Provider request count or unknown state mismatch")
    require(ledger["summary_requests_sent"] == 0 and ledger["retries"] == 0,
            "summary request or retry was sent")
    require(ledger["direct_d_requests_sent"] == 3 and ledger["active_reserved_usd"] == 0,
            "direct request/reservation state mismatch")
    require(ledger["actual_billed_usd"] is None and not ledger["provider_billing_amount_retrieved"],
            "API usage estimate was mislabeled as billed dollars")
    total_cost = Decimal("0")
    total_input = 0
    total_output = 0
    for event in response_events:
        usage = event["response"]["usage"]
        total_input += usage["prompt_tokens"]
        total_output += usage["completion_tokens"]
        total_cost += (Decimal(usage["prompt_tokens"]) * Decimal("0.30")
                       + Decimal(usage["completion_tokens"]) * Decimal("1.20")) / Decimal(1000000)
    require(total_input == 78766 and total_output == 532, "usage total mismatch")
    require(total_cost == Decimal("0.0242682"), "peak no-cache usage estimate mismatch")
    require(Decimal(str(ledger["actual_usage_cost_upper_bound_usd"])) == total_cost,
            "ledger cost differs from Provider usage")
    require(total_cost < Decimal("0.50"), "hard cost cap exceeded")
    for qid in ["Q02", "Q03", "Q06"]:
        row = next(item for item in results["rows"] if item["group"] == "D" and item["question_id"] == qid)
        require(row["source_sequence_audit"]["history_order_preserved"], f"history mismatch for {qid}")
        require(len(row["source_sequence_audit"]["visible_source_sequences"]) == 29,
                f"history source count mismatch for {qid}")
        require(row["source_sequence_audit"]["summary_messages"] == 0, f"summary appeared for {qid}")
    require(next(row for row in results["rows"] if row["group"] == "D" and row["question_id"] == "Q02")["score_category"]
            == "CORRECT_SUPPORTED", "Q02 review missing")
    q03 = next(row for row in results["rows"] if row["group"] == "D" and row["question_id"] == "Q03")
    require(q03["score_category"] == "INCORRECT_OR_UNSAFE"
            and q03["deterministic_checks"]["claims_correction_was_in_current_question_message"],
            "Q03 provenance issue not recorded")
    q06 = next(row for row in results["rows"] if row["group"] == "D" and row["question_id"] == "Q06")
    require(q06["score_category"] == "INCOMPLETE"
            and q06["deterministic_checks"]["tool_call_executed"] is False,
            "Q06 tool-call stop not recorded")
    for qid in ["Q07", "Q08", "Q10", "Q12"]:
        row = next(item for item in results["rows"] if item["group"] == "D" and item["question_id"] == qid)
        require(row["status"] == "BLOCKED_AFTER_STOP_CONDITION", f"D slot not stopped: {qid}")
    for qid in QUESTION_IDS:
        for group in ["A", "B", "C"]:
            row = next(item for item in results["rows"] if item["group"] == group and item["question_id"] == qid)
            require(row["status"] == "BLOCKED_BEFORE_PROVIDER_SEND", f"ABC slot not blocked: {group}/{qid}")
    expected_phase_hashes = preflight["phase_a_file_sha256"]
    for name, expected in expected_phase_hashes.items():
        require(digest((PHASE_A / name).read_bytes()) == expected, f"Phase A source changed: {name}")
    local_env = ROOT.parent.parent / ".env"
    key = ""
    if local_env.is_file():
        for line in local_env.read_text(encoding="utf-8").splitlines():
            if line.strip().startswith("OPSPILOT_MODEL_API_KEY="):
                key = line.split("=", 1)[1].strip().strip("\"").strip("'")
                break
    if key:
        for path in EVIDENCE.rglob("*"):
            if path.is_file():
                require(key.encode("utf-8") not in path.read_bytes(), "credential value found in evidence")
    print("VALIDATION_OK: 28 slots; 3 Provider calls; 6 raw events; no retry/unknown/secret leak; Phase A unchanged; cost USD 0.0242682 upper estimate")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
