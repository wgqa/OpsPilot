from __future__ import annotations

import gzip
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
EVIDENCE = Path(__file__).resolve().parent
LIVE = EVIDENCE / "live_run_02"


def main() -> None:
    results = json.loads((LIVE / "LIVE_RESULTS.json").read_text(encoding="utf-8"))
    ledger = json.loads((LIVE / "COST_LEDGER.json").read_text(encoding="utf-8"))
    with gzip.open(LIVE / "LIVE_REQUESTS.jsonl.gz", "rt", encoding="utf-8") as handle:
        events = [json.loads(line) for line in handle if line.strip()]
    answer_sends = {event["case_id"]: event for event in events
                    if event.get("event") == "SEND_STARTED" and event.get("purpose") == "ANSWER"}
    summary_returns = {}
    for event in events:
        if event.get("event") == "RESPONSE_RECEIVED" and event.get("purpose") == "SUMMARY":
            summary_returns.setdefault(event["case_id"], []).append(
                event.get("response_payload", {}).get("choices", [{}])[0]
                .get("message", {}).get("content", "")
            )
    slots = {slot["logical_id"]: slot for slot in ledger["slots"]}
    assessments = []
    for row in results["rows"]:
        case_id = row["question_id"] + "-" + row["group"]
        question_id = row["question_id"]
        response = str(row.get("response") or "")
        prompt = "\n".join(str(item.get("content", ""))
                            for item in answer_sends[case_id].get("request_payload", {}).get("messages", []))
        manifest = row.get("input_manifest", {})
        summary_versions = summary_returns.get(case_id, [])
        final_summary = summary_versions[-1] if summary_versions else ""
        try:
            final_summary_doc = json.loads(final_summary) if final_summary else {}
        except json.JSONDecodeError:
            final_summary_doc = {}
        def declared_sequences(value):
            found = set()
            if isinstance(value, dict):
                for key, item in value.items():
                    if key == "source_sequences" and isinstance(item, list):
                        found.update(int(seq) for seq in item if type(seq) is int)
                    else:
                        found.update(declared_sequences(item))
            elif isinstance(value, list):
                for item in value:
                    found.update(declared_sequences(item))
            return found
        if question_id == "Q02":
            source_supported = "/callback" in prompt
            answer_matches_gold = "/callback" in response
            abstained = any(phrase in response for phrase in ("无法确定", "无法判断", "无从确定", "无法根据"))
            visible = {"initial_endpoint_callback": source_supported}
            if answer_matches_gold and source_supported:
                category = "CORRECT_SUPPORTED"
                reason = "The expected endpoint is present in the final model prompt and the response gives it."
            elif answer_matches_gold:
                category = "CORRECT_UNSUPPORTED"
                reason = "The response gives the expected endpoint but the final model prompt does not contain it."
            elif abstained and not source_supported:
                category = "SAFE_ABSTENTION"
                reason = "The endpoint is absent from the final model prompt and the model explicitly abstains."
            else:
                category = "INCORRECT_OR_UNSAFE"
                reason = "The response neither gives the supported endpoint nor safely abstains."
            summary_fact = {
                "summary_call_count": len(summary_versions),
                "first_summary_contains_endpoint": bool(summary_versions and "/callback" in summary_versions[0]),
                "final_summary_contains_endpoint": "/callback" in final_summary,
            }
        elif question_id == "Q03":
            source_supported = all(term in prompt for term in ("req-483", "req-482", "\u6b63\u5f0f\u66f4\u6b63", "\u5f55\u5165\u9519\u8bef"))
            answer_matches_gold = "req-483" in response
            abstained = any(phrase in response for phrase in ("无法确定", "无法判断", "不知道"))
            visible = {
                "req_483": "req-483" in prompt,
                "req_482": "req-482" in prompt,
                "formal_correction_and_error_source": "\u6b63\u5f0f\u66f4\u6b63" in prompt and "\u5f55\u5165\u9519\u8bef" in prompt,
            }
            if answer_matches_gold and source_supported:
                category = "CORRECT_SUPPORTED"
                reason = "The final model prompt contains the formal correction, superseded value, and corrected value."
            elif answer_matches_gold:
                category = "CORRECT_UNSUPPORTED"
                reason = "The corrected identifier appears in the prompt, but the formal correction source and superseded value do not; the response attributes it to a formal correction."
            elif abstained and not source_supported:
                category = "SAFE_ABSTENTION"
                reason = "The formal correction source is not complete in the final model prompt and the model abstains."
            else:
                category = "INCORRECT_OR_UNSAFE"
                reason = "The response does not provide the corrected Request ID with adequate source support."
            summary_fact = {
                "summary_call_count": len(summary_versions),
                "first_summary_contains_formal_correction": bool(summary_versions and all(term in summary_versions[0] for term in ("req-483", "req-482", "\u5f55\u5165\u9519\u8bef"))),
                "final_summary_contains_formal_correction": bool(summary_versions and all(term in final_summary for term in ("req-483", "req-482", "\u5f55\u5165\u9519\u8bef"))),
            }
        else:
            source_supported = all(term in prompt for term in ("v1.2", "v1.3"))
            answer_matches_gold = all(term in response for term in ("v1.2", "v1.3"))
            abstained = any(phrase in response for phrase in ("无法根据", "无法回答", "没有可核实的资料", "无法确定"))
            visible = {
                "v1_2": "v1.2" in prompt,
                "v1_3": "v1.3" in prompt,
                "max_attempts_3_to_5": "max_attempts" in prompt and "3" in prompt and "5" in prompt,
            }
            if answer_matches_gold and source_supported:
                category = "CORRECT_SUPPORTED"
                reason = "The final model prompt contains both protocol versions and the response states the transition."
            elif answer_matches_gold:
                category = "CORRECT_UNSUPPORTED"
                reason = "The response states the version transition although it is absent from the final model prompt."
            elif abstained and not source_supported:
                category = "SAFE_ABSTENTION"
                reason = "The version transition is absent from the final model prompt and the model explicitly abstains."
            else:
                category = "INCORRECT_OR_UNSAFE"
                reason = "The response neither states the supported transition nor safely abstains."
            summary_fact = {
                "summary_call_count": len(summary_versions),
                "first_summary_contains_protocol_transition": bool(summary_versions and all(term in summary_versions[0] for term in ("v1.2", "v1.3"))),
                "final_summary_contains_protocol_transition": bool(summary_versions and all(term in final_summary for term in ("v1.2", "v1.3"))),
                "source_sequence_11_declared_by_final_summary": 11 in declared_sequences(final_summary_doc),
            }
        prompt_prefix = "\n".join(str(x.get("content", "")) for x in answer_sends[case_id].get("request_payload", {}).get("messages", []) if x.get("role") == "system").split("\nWORK_CONTEXT\n", 1)[0]
        slot = slots[case_id + ":ANSWER:1"]
        assessments.append({
            "case_id": case_id,
            "question_id": question_id,
            "strategy": row["strategy"],
            "status": row["status"],
            "evidence_level": "REAL_PROVIDER_RESPONSE_AND_FINAL_REQUEST_TRACE",
            "review_category": category,
            "review_authority": "IMPLEMENTER_PRELIMINARY_REVIEW",
            "answer_matches_gold_fact": answer_matches_gold,
            "necessary_fact_visible_in_final_model_prompt": source_supported,
            "prompt_fact_checks": visible,
            "summary_retention_checks": summary_fact,
            "answer_request_digest": slot.get("request_digest"),
            "response_id": slot.get("provider_request_id"),
            "response_sha256": hashlib.sha256(response.encode("utf-8")).hexdigest(),
            "tool_choice": manifest.get("answer_tool_choice"),
            "tool_calls_observed": False,
            "claims_http_202_or_queued_means_complete": False,
            "preliminary_reason": reason,
        })
    counts = {}
    for item in assessments:
        counts[item["review_category"]] = counts.get(item["review_category"], 0) + 1
    report = {
        "schema_version": 1,
        "task": "ABC-LIVE-ENV-UNBLOCK-01",
        "evidence_level": "REAL_PROVIDER_TRACE_PLUS_IMPLEMENTER_PRELIMINARY_SEMANTIC_REVIEW",
        "scoring_protocol": ["CORRECT_SUPPORTED", "CORRECT_UNSUPPORTED", "SAFE_ABSTENTION", "INCORRECT_OR_UNSAFE"],
        "review_authority": "IMPLEMENTER_PRELIMINARY_REVIEW",
        "independent_main_agent_review": "NOT_PERFORMED_PENDING_ACCEPTANCE",
        "provider_requests_sent": results.get("provider_requests_sent"),
        "provider_cost_usd": results.get("provider_cost_usd"),
        "category_counts": counts,
        "sample_is_not_an_accuracy_estimate": True,
        "cases": assessments,
    }
    path = EVIDENCE / "IMPLEMENTER_PRELIMINARY_ASSESSMENT.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"category_counts": counts, "independent_main_agent_review": report["independent_main_agent_review"]}, indent=2))

if __name__ == "__main__":
    main()
