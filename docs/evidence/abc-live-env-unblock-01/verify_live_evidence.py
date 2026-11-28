from __future__ import annotations

import gzip
import hashlib
import json
import os
import sys
from pathlib import Path
from urllib.parse import urlparse

_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from opspilot.config import ROOT, load_local_environment
from opspilot.domain.context_engineering import estimate_messages_tokens, estimate_text_tokens

BASE = Path(__file__).resolve().parent
LIVE = BASE / "live_run_02"
PHASE_A = ROOT / "docs/evidence/r2-ar04-long-context-journey-01"
EVIDENCE_DIR = BASE

def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

def ceil_cost(input_tokens: int, output_tokens: int) -> int:
    return (input_tokens * 300_000 + output_tokens * 1_200_000 + 999_999) // 1_000_000

def main():
    results = json.loads((LIVE / "LIVE_RESULTS.json").read_text(encoding="utf-8"))
    ledger = json.loads((LIVE / "COST_LEDGER.json").read_text(encoding="utf-8"))
    preflight = json.loads((LIVE / "PREFLIGHT.json").read_text(encoding="utf-8"))
    questions_doc = json.loads((PHASE_A / "QUESTIONS.json").read_text(encoding="utf-8"))
    questions = {row["id"]: row for row in questions_doc["questions"]}
    events = []
    with gzip.open(LIVE / "LIVE_REQUESTS.jsonl.gz", "rt", encoding="utf-8") as handle:
        events = [json.loads(line) for line in handle if line.strip()]

    checks = {}
    checks["live_run_completed"] = results.get("status") == "COMPLETED"
    checks["exact_nine_frozen_cases"] = len(results.get("rows", [])) == 9 and {
        (row["question_id"], row["group"]) for row in results["rows"]
    } == {(qid, group) for qid in ("Q02", "Q03", "Q06") for group in ("A", "B", "C")}
    checks["all_cases_succeeded"] = all(row.get("status") == "SUCCEEDED" for row in results["rows"])
    checks["shared_persistent_ledger_cap"] = (
        ledger.get("request_limit") == 21
        and ledger.get("hard_cap_usd_micro") == 150_000
        and ledger.get("provider_requests_started") == 21
        and ledger.get("status") == "FINISHED"
        and ledger.get("stop_reason") is None
    )
    checks["actual_cost_matches_ledger_and_is_below_cap"] = (
        sum(int(s.get("settled_usd_micro") or 0) for s in ledger["slots"])
        == int(ledger.get("settled_usd_micro") or 0)
        and int(ledger.get("settled_usd_micro") or 0) < 150_000
        and results.get("provider_cost_usd") == f"{int(ledger.get('settled_usd_micro') or 0) / 1_000_000:.6f}"
    )
    sent_slots = [s for s in ledger["slots"] if s.get("request_digest")]
    checks["all_planned_slots_sent_once_and_completed"] = (
        len(sent_slots) == 21
        and len({s["logical_id"] for s in sent_slots}) == 21
        and all(s.get("status") == "COMPLETED" for s in sent_slots)
        and all(s.get("provider_request_id") for s in sent_slots)
        and len({s.get("provider_request_id") for s in sent_slots}) == 21
    )
    checks["no_unknown_or_reserved_budget"] = (
        results.get("reserved_unknown_usd_micro") == 0
        and ledger.get("currently_reserved_usd_micro") == 0
        and not any(s.get("status") in {"UNKNOWN", "USAGE_UNKNOWN", "STOPPED_UNKNOWN", "SENDING"} for s in ledger["slots"])
    )
    checks["zero_cost_preflight_passed_without_provider_send"] = (
        preflight.get("main_repo_env_found") is True
        and preflight.get("main_repo_env_loaded") is True
        and all(preflight.get("effective_required_presence_after_non_secret_supplement", {}).values())
        and set(preflight.get("supplemented_non_secret_configuration", [])) == {
            "OPSPILOT_MODEL_CONFIG_VERSION", "OPSPILOT_MODEL_PRICE_VERSION",
            "OPSPILOT_ASSISTANT_SERVICE_IDENTITY",
        }
        and preflight.get("runtime_grant_bindable") is True
        and preflight.get("assistant_model_constructed_with_mock_transports") is True
        and preflight.get("provider_transport_invocations") == 0
        and preflight.get("provider_requests_sent") == 0
        and preflight.get("real_provider_send_condition") is True
    )

    started = [e for e in events if e.get("event") == "SEND_STARTED"]
    received = [e for e in events if e.get("event") == "RESPONSE_RECEIVED"]
    unknown = [e for e in events if e.get("event") == "SEND_UNKNOWN"]
    checks["trace_matches_ledger_and_has_no_unknown"] = len(started) == len(received) == 21 and len(unknown) == 0
    checks["authorization_header_never_serialized"] = all(
        e.get("authorization_header_recorded") is False for e in events
    )
    checks["all_responses_are_expected_model_and_complete"] = all(
        e.get("response_model") == "deepseek-flash" and e.get("status") == "COMPLETED"
        and e.get("http_status") == 200 and e.get("finish_reason") == "stop"
        for e in received
    )
    checks["no_provider_tool_calls_or_search_fetch_tools"] = all(
        not e.get("response_payload", {}).get("choices", [{}])[0].get("message", {}).get("tool_calls")
        for e in received
    )
    checks["no_deepseek_search_or_fetch_tools_in_any_request"] = all(
        not any(
            isinstance(t, dict) and t.get("type") in {"deepseek_web_search", "deepseek_read_url"}
            for t in e.get("request_payload", {}).get("tools", [])
        )
        for e in started
    )
    checks["all_answer_requests_are_tool_choice_none"] = all(
        e.get("request_payload", {}).get("tool_choice") == "none"
        for e in started if e.get("purpose") == "ANSWER"
    ) and sum(e.get("purpose") == "ANSWER" for e in started) == 9
    checks["all_requests_match_frozen_model_parameters"] = all(
        e.get("request_payload", {}).get("model") == "deepseek-flash"
        and e.get("request_payload", {}).get("thinking") == {"type": "disabled"}
        and e.get("request_payload", {}).get("temperature") == 0
        and e.get("request_payload", {}).get("stream") is False
        and type(e.get("request_payload", {}).get("max_tokens")) is int
        and 0 < e["request_payload"]["max_tokens"] <= 512
        for e in started
    )
    runner_source = (BASE / "run_abc_eval.py").read_text(encoding="utf-8")
    checks["runner_source_guards_exact_official_endpoint_before_dispatch"] = (
        'url.host != "api.deepseek.com"' in runner_source
        and 'url.path != "/chat/completions"' in runner_source
        and 'url.query or url.fragment' in runner_source
    )

    gold_leaks = []
    scoring_rule_leaks = []
    request_by_case_purpose = {}
    send_event_by_case_purpose = {}
    for event in started:
        case_id = str(event["case_id"])
        qid = case_id.split("-", 1)[0]
        payload = event.get("request_payload", {})
        serialized = canonical(payload)
        gold = questions[qid].get("gold")
        scoring_rule = str(questions[qid].get("scoring_rule") or "")
        if canonical(gold) in serialized:
            gold_leaks.append(event["logical_id"])
        if scoring_rule and scoring_rule in serialized:
            scoring_rule_leaks.append(event["logical_id"])
        request_by_case_purpose[(case_id, event["purpose"])] = payload
        send_event_by_case_purpose[(case_id, event["purpose"])] = event
    checks["gold_and_scoring_rules_absent_from_all_requests"] = not gold_leaks and not scoring_rule_leaks

    cases = []
    parity = set()
    summary_loss = []
    summaries_by_case = {}
    for event in received:
        if event.get("purpose") != "SUMMARY":
            continue
        case_id = str(event.get("case_id"))
        content = str(event.get("response_payload", {}).get("choices", [{}])[0]
                      .get("message", {}).get("content", ""))
        try:
            document = json.loads(content)
        except json.JSONDecodeError:
            document = {}
        def flatten(value):
            if isinstance(value, dict):
                return " ".join(flatten(item) for item in value.values())
            if isinstance(value, list):
                return " ".join(flatten(item) for item in value)
            return str(value) if isinstance(value, (str, int, float)) else ""
        def source_sequences(value):
            found = set()
            if isinstance(value, dict):
                for key, item in value.items():
                    if key == "source_sequences" and isinstance(item, list):
                        found.update(int(seq) for seq in item if type(seq) is int)
                    else:
                        found.update(source_sequences(item))
            elif isinstance(value, list):
                for item in value:
                    found.update(source_sequences(item))
            return found
        text = flatten(document)
        summaries_by_case.setdefault(case_id, []).append({
            "ordinal": len(summaries_by_case.get(case_id, [])) + 1,
            "summary_sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
            "top_level_schema_keys": sorted(document) if isinstance(document, dict) else [],
            "declared_source_sequences": sorted(source_sequences(document)),
            "contains_callback_endpoint": "/callback" in text,
            "contains_formal_request_correction": all(x in text for x in ("req-483", "req-482", "\u5f55\u5165\u9519\u8bef")),
            "contains_protocol_transition": all(x in text for x in ("v1.2", "v1.3")),
        })
    expected_summary_keys = sorted({
        "initial_goal", "constraints", "user_assertions", "corrections",
        "rejected_hypotheses", "unresolved_items", "timeline",
    })
    all_summaries = [item for rows in summaries_by_case.values() for item in rows]
    checks["all_live_summaries_are_structured_json_with_expected_schema"] = (
        len(all_summaries) == 12
        and all(item["top_level_schema_keys"] == expected_summary_keys for item in all_summaries)
    )
    for row in results["rows"]:
        case_id = row["question_id"] + "-" + row["group"]
        manifest = row.get("input_manifest", {})
        parity.add((manifest.get("tool_schema_sha256"), manifest.get("system_prompt_prefix_sha256")))
        answer_payload = request_by_case_purpose[(case_id, "ANSWER")]
        answer_send_event = send_event_by_case_purpose[(case_id, "ANSWER")]
        estimated_answer_input = (
            estimate_messages_tokens(answer_payload.get("messages", []))
            + estimate_text_tokens(canonical(answer_payload.get("tools", []))) + 64
        )
        answer_slot = next(s for s in sent_slots if s["logical_id"] == case_id + ":ANSWER:1")
        summary_slots = [s for s in sent_slots if s.get("case_id") == case_id and s["purpose"] == "SUMMARY"]
        prompt = "\n".join(str(m.get("content", "")) for m in answer_payload.get("messages", []))
        qid = row["question_id"]
        visible = {}
        if qid == "Q02":
            visible["callback_endpoint"] = "/callback" in prompt
        elif qid == "Q03":
            visible["req483"] = "req-483" in prompt
            visible["req482"] = "req-482" in prompt
            visible["formal_correction_source"] = "\u6b63\u5f0f\u66f4\u6b63" in prompt and "\u5f55\u5165\u9519\u8bef" in prompt
        else:
            visible["v1_2"] = "v1.2" in prompt
            visible["v1_3"] = "v1.3" in prompt
            visible["max_attempts_3_to_5"] = "max_attempts" in prompt and "3" in prompt and "5" in prompt
        ref_ids = {str(x.get("summary_id")) for x in manifest.get("summary_refs", [])}
        selected_summary_ids = {
            str(x.get("source_refs", [""])[0]) for x in manifest.get("answer_context_blocks", [])
            if x.get("status") == "SELECTED" and x.get("category") == "HISTORICAL_SUMMARY"
        }
        cases.append({
            "case_id": case_id,
            "evidence_level": "REAL_PROVIDER_TRACE_AND_CURRENT_CONTEXT_MANIFEST",
            "summary_calls": manifest.get("summary_calls"),
            "answer_tool_choice": manifest.get("answer_tool_choice"),
            "estimated_answer_input_tokens": estimated_answer_input,
            "provider_reported_answer_usage": answer_slot.get("usage"),
            "summary_call_usage": [
                {"logical_id": s["logical_id"], "usage": s.get("usage"), "settled_usd_micro": s.get("settled_usd_micro")}
                for s in summary_slots
            ],
            "effective_context_input_budget_tokens": manifest.get("effective_context_input_budget_tokens"),
            "history_digest_sha256": manifest.get("history_digest_sha256"),
            "domain_instance_sha256": manifest.get("domain_instance_sha256"),
            "checkpoint_instance_sha256": manifest.get("checkpoint_instance_sha256"),
            "summary_ref_matches_selected_context_block": bool(ref_ids) and ref_ids == selected_summary_ids if manifest.get("summary_refs") else not selected_summary_ids,
            "required_fact_visibility_in_actual_answer_prompt": visible,
        })
        if qid == "Q02" and row["group"] in {"A", "B"} and not visible["callback_endpoint"]:
            summary_loss.append({"case_id": case_id, "lost_fact": "early endpoint=/callback", "final_summary_and_answer_prompt_omitted_source_sequence": 3})
        if qid == "Q06" and row["group"] == "B" and not visible["v1_2"]:
            summary_loss.append({"case_id": case_id, "lost_fact": "protocol v1.2 to v1.3 / max_attempts 3 to 5", "final_summary_and_answer_prompt_omitted_source_sequence": 11})

    checks["cross_case_prompt_schema_and_trusted_prefix_parity"] = len(parity) == 1 and None not in next(iter(parity))
    checks["domain_and_checkpoint_are_isolated_per_case"] = (
        len({x["domain_instance_sha256"] for x in cases}) == 9
        and len({x["checkpoint_instance_sha256"] for x in cases}) == 9
    )
    checks["each_case_uses_bounded_runtime_grant_and_12k_context"] = all(
        row["input_manifest"].get("configured_input_limit_tokens") == 12_000
        and row["input_manifest"].get("runtime_binding_database_identity_matches") is True
        and row["input_manifest"].get("runtime_grant_status") == "ACTIVE"
        and row["input_manifest"].get("runtime_grant_case_limit_usd_micro") == (
            12_645 if row["group"] in {"A", "B"} else 4_215
        )
        and row["input_manifest"].get("runtime_spend_summary", {}).get("status") == "ACTIVE"
        and row["input_manifest"].get("runtime_spend_summary", {}).get("committed_or_reserved_usd_micro", 10**9)
        <= row["input_manifest"].get("runtime_grant_case_limit_usd_micro", -1)
        for row in results["rows"]
    )
    checks["all_summary_refs_are_in_current_answer_context"] = all(
        x["summary_ref_matches_selected_context_block"] for x in cases
    )
    checks["all_final_answer_estimates_fit_the_12k_input_budget"] = all(
        0 < int(x["estimated_answer_input_tokens"] or 0) <= 12_000
        and int(x["provider_reported_answer_usage"].get("input_tokens", 0)) <= 12_000
        for x in cases
    )
    checks["all_provider_request_usage_is_complete_and_within_caps"] = all(
        isinstance(s.get("usage"), dict)
        and 0 < int(s["usage"].get("input_tokens", 0)) <= 12_000
        and 0 <= int(s["usage"].get("output_tokens", 0)) <= 512
        and int(s.get("settled_usd_micro", 0)) == ceil_cost(
            int(s["usage"]["input_tokens"]), int(s["usage"]["output_tokens"]),
        )
        for s in sent_slots
    )

    # Scan the task's evidence artifacts and decompressed trace for the loaded
    # key without ever printing or serializing the key itself.
    load_local_environment(ROOT.parent.parent / ".env")
    api_key = os.environ.get("OPSPILOT_MODEL_API_KEY", "").strip()
    leaked_paths = []
    if api_key:
        needle = api_key.encode("utf-8")
        for path in EVIDENCE_DIR.rglob("*"):
            if not path.is_file() or path.name == "verify_live_evidence.py":
                continue
            raw = path.read_bytes()
            if needle in raw:
                leaked_paths.append(path.relative_to(EVIDENCE_DIR).as_posix())
            if path.suffix == ".gz":
                try:
                    if needle in gzip.decompress(raw):
                        leaked_paths.append(path.relative_to(EVIDENCE_DIR).as_posix() + " (decompressed)")
                except OSError:
                    pass
    checks["api_key_not_found_in_evidence_files"] = bool(api_key) and not leaked_paths

    report = {
        "schema_version": 1,
        "task": "ABC-LIVE-ENV-UNBLOCK-01",
        "evidence_level": "REAL_PROVIDER_TRACE_PLUS_FIXTURE_MOCK_AND_DETERMINISTIC_OFFLINE_AUDIT",
        "base_sha": results.get("base_sha"),
        "execution_id": results.get("execution_id"),
        "provider_requests_sent": ledger.get("provider_requests_started"),
        "summary_requests_sent": sum(1 for s in sent_slots if s["purpose"] == "SUMMARY"),
        "answer_requests_sent": sum(1 for s in sent_slots if s["purpose"] == "ANSWER"),
        "provider_cost_usd": results.get("provider_cost_usd"),
        "hard_cap_usd": "0.15",
        "unique_response_ids": len({e.get("provider_request_id") for e in received}),
        "unknown_requests": len(unknown),
        "cross_case_schema_prompt_parity_count": len(parity),
        "summary_information_losses": summary_loss,
        "actual_provider_summary_versions": summaries_by_case,
        "cases": cases,
        "gold_leak_logical_ids": gold_leaks,
        "scoring_rule_leak_logical_ids": scoring_rule_leaks,
        "api_key_leaked_paths": leaked_paths,
        "checks": checks,
        "status": "PASS" if all(checks.values()) else "FAIL",
    }
    target = BASE / "VERIFY_RESULTS.json"
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "checks": checks, "provider_requests_sent": report["provider_requests_sent"], "provider_cost_usd": report["provider_cost_usd"], "summary_information_losses": summary_loss}, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
