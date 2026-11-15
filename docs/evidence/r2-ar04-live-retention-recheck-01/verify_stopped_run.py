"""Verify the one live dispatch and replay its recorded summary offline."""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import sys
import uuid
from pathlib import Path

from run_recheck import HERE, MATRIX, block_outbound_model_io
from retention_evidence import OLD_TRACE, read_json, stage_facts, summary_source, trace_index
from opspilot.domain import chat
from opspilot.domain.context_engineering import estimate_messages_tokens


def tokens(document):
    return estimate_messages_tokens([{"role": "system", "content": chat._canonical(document)}])


def replay(text, message_ids):
    validated = chat._validate_summary_document(text, message_ids)
    result = {"summary_schema_and_source_sequences_valid": True, "validated_tokens": tokens(validated)}
    anchor = {}

    def observe(frame, event, arg):
        if (event == "exception" and frame.f_code is chat._compact_summary_document.__code__
                and getattr(arg[1], "code", None) == "CONTEXT_SUMMARY_FACT_RETENTION_BUDGET_EXCEEDED"):
            state = frame.f_locals
            field, index = state["field"], state["index"]
            short = state["normalized"](state["candidates_by_field"][field][index], 24)
            trial_items = {**state["selected_by_index"][field], index: short}
            trial = {**state["result"], field: [trial_items[i] for i in sorted(trial_items)]}
            anchor.update(field=field, index=index, selected_tokens=tokens(state["result"]),
                          shortest_trial_tokens=tokens(trial))
        return observe

    try:
        sys.settrace(observe)
        stored = chat._compact_summary_document(validated)
    except chat.TaskControlError as error:
        result.update(status="PERSISTENCE_REJECTED", error_code=error.code, error_detail=str(error), anchor=anchor)
    else:
        result.update(status="PERSISTENCE_PROJECTION_FITS", compacted_tokens=tokens(stored))
    finally:
        sys.settrace(None)
    return result


def audit():
    root = HERE / "live_run_01"
    trace_path = root / "LIVE_REQUESTS.jsonl.gz"
    with gzip.open(trace_path, "rt", encoding="utf-8") as stream:
        send, response = map(json.loads, stream)
    ledger, result = (read_json(root / name) for name in ("COST_LEDGER.json", "LIVE_RESULTS.json"))
    authority, preflight = read_json(HERE / "EXECUTION_AUTHORIZATION.json"), read_json(root / "PREFLIGHT.json")
    assert authority["case_order"] == list(MATRIX) and authority["total_request_cap"] == ledger["request_limit"] == 9
    assert authority["hard_cap_usd_micro"] == ledger["hard_cap_usd_micro"] == 60_000
    assert preflight["technical_preflight_passed"] and preflight["actual_live_send_authorized"]
    assert [send["event"], response["event"]] == ["SEND_STARTED", "RESPONSE_RECEIVED"]
    logical_id = send["logical_id"]
    assert logical_id == response["logical_id"] == "Q02-A:SUMMARY:1"
    assert not send["authorization_header_recorded"] and not response["authorization_header_recorded"]
    assert response["http_status"] == 200 and response["finish_reason"] == "stop"
    assert response["status"] == "COMPLETED" and response["response_model"] == "deepseek-flash"
    assert response["request_body_sha256"] == send["request_body_sha256"]
    assert ledger["slots"][0]["request_digest"] == send["request_body_sha256"]
    assert ledger["slots"][0]["provider_request_id"] == response["provider_request_id"]
    assert all(slot["status"] == "NOT_SENT_FINAL" and not slot["request_digest"] for slot in ledger["slots"][1:])
    assert ledger["status"] == result["status"] == "STOPPED"
    assert ledger["provider_requests_started"] == result["recorded_requests"] == result["summary_requests"] == 1
    assert result["answer_requests"] == ledger["currently_reserved_usd_micro"] == 0
    assert [case["status"] for case in result["cases"]] == ["FAILED_OR_UNKNOWN", "NOT_STARTED", "NOT_STARTED"]
    first = result["cases"][0]
    assert not first["persisted_summaries"] and first["mcp_attempts"] == 0
    assert first["recorded_compression_attempt_states"][0]["error_class"] == "TaskControlError"
    usage = response["usage"]
    assert usage["input_tokens"] + usage["output_tokens"] == usage["total_tokens"]
    amount = (usage["input_tokens"] * 300_000 + usage["output_tokens"] * 1_200_000 + 999_999) // 1_000_000
    assert amount == ledger["settled_usd_micro"] == result["provider_conservative_cost_estimate_usd_micro"]

    old = trace_index(OLD_TRACE)[logical_id]
    old_send = old["SEND_STARTED"]
    current_source, old_source = map(summary_source, (send["request_payload"], old_send["request_payload"]))
    sequences = [row["sequence"] for row in current_source["new_messages"]]
    assert sequences == [row["sequence"] for row in old_source["new_messages"]] == list(range(1, 17))
    body_differences = [i for i, (new, before) in enumerate(zip(current_source["new_messages"], old_source["new_messages"]))
                        if new != before]
    assert body_differences == [15]
    current_excerpt, old_excerpt = current_source["truncated_sources"][0], old_source["truncated_sources"][0]
    excerpt_differences = sorted(k for k in current_excerpt.keys() | old_excerpt.keys()
                                 if current_excerpt.get(k) != old_excerpt.get(k))
    assert excerpt_differences == ["included_estimated_tokens", "message_id"]
    current_settings = {k: v for k, v in send["request_payload"].items() if k != "messages"}
    old_settings = {k: v for k, v in old_send["request_payload"].items() if k != "messages"}
    assert current_settings == old_settings
    assert send["request_payload"]["messages"][0] == old_send["request_payload"]["messages"][0]
    old_shas = {k: old_send[k] for k in ("request_body_sha256",)}
    new_text = response["response_payload"]["choices"][0]["message"]["content"]
    old_text = old["RESPONSE_RECEIVED"]["response_payload"]["choices"][0]["message"]["content"]
    fact = stage_facts("Q02-A", json.loads(new_text))
    assert fact["visibility"] == "COMPLETE_TEXT_WITH_SOURCE"
    replays = {}
    for salt in ("replay-a", "replay-b", "replay-c"):
        ids = {str(seq): f"message-{uuid.uuid5(uuid.NAMESPACE_URL, f'opspilot/{salt}/{seq}')}"
               for seq in sequences}
        replays[salt] = {"live_recheck_response": replay(new_text, ids), "historical_abc_response": replay(old_text, ids)}
    assert replays["replay-b"]["live_recheck_response"]["anchor"]["shortest_trial_tokens"] > 512
    assert replays["replay-b"]["historical_abc_response"]["status"] == "PERSISTENCE_PROJECTION_FITS"
    assert any(row["live_recheck_response"]["status"] == "PERSISTENCE_PROJECTION_FITS" for row in replays.values())

    return {
        "evidence": "FIRST_HAND_LIVE_TRACE_AND_OFFLINE_PRODUCTION_FUNCTION_REPLAY",
        "provider_requests": 1,
        "provider_responses_received": 1,
        "provider_response_id": response["provider_request_id"],
        "provider_usage": usage,
        "peak_uncached_conservative_cost_usd_micro": amount,
        "provider_account_charge": "UNVERIFIED",
        "remaining_unsent_slots": len(ledger["slots"]) - 1,
        "trace_sha256": hashlib.sha256(trace_path.read_bytes()).hexdigest(),
        "observed_live": {
            "first_model_summary": fact, "compression_attempts": first["recorded_compression_attempt_states"],
            "persisted_summaries": 0, "runner_stop_reason": ledger["stop_reason"],
            "precise_task_control_code": "UNVERIFIED_NOT_CAPTURED",
            "answer_requests": 0, "l3": "NOT_RUN",
        },
        "old_vs_new_first_request": {
            "historical_request_sha256": old_shas["request_body_sha256"],
            "recheck_request_sha256": send["request_body_sha256"],
            "model_settings_and_system_prompt_match": True,
            "sequences_match": sequences,
            "body_difference_only_in_excerpt_seq": 16,
            "historical_excerpt_estimated_tokens": old_excerpt["included_estimated_tokens"],
            "recheck_excerpt_estimated_tokens": current_excerpt["included_estimated_tokens"],
            "varying_truncation_fields": excerpt_differences,
        },
        "offline_replay": {
            "additional_real_requests": 0,
            "live_source_id_map_captured": False,
            "message_id_policy": "deterministic UUID5 fixtures; not original live IDs",
            "cap": chat.MAX_COMPRESSION_OUTPUT_TOKENS,
            "first_raw_summary_estimated_tokens": tokens(json.loads(new_text)),
            "samples": replays,
        },
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    block_outbound_model_io()
    report = audit()
    with args.output.open("x", encoding="utf-8", newline="\n") as dest:
        json.dump(report, dest, ensure_ascii=False, indent=2)
        dest.write("\n")
    print(json.dumps({"live_dispatches_verified": 1, "answer_requests": 0, "offline_uuid_replays": 3}))
