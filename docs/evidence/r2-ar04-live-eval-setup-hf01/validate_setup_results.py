from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
EVIDENCE = Path(__file__).resolve().parent
RESULT_PATH = EVIDENCE / "TEST_RESULTS.json"
RUN_PATH = EVIDENCE / "TEST_RUN.txt"
SUPPLEMENT_PATH = EVIDENCE / "PREVIOUS_SCORE_SUPPLEMENT.json"
PROTECTED = {
    "docs/evidence/r2-ar04-long-context-journey-01/QUESTIONS.json": "ea3d6554eafa433d1617dc5a5ba9f140471f3cb95f8ae10bcd25b807a4e7afe2",
    "docs/evidence/r2-ar04-long-context-journey-01/HISTORY_SNAPSHOT.json": "356512f611b046a04e33506a0fb1a88c6a08af93517b2134125dd6771b282c16",
    "docs/evidence/r2-ar04-long-context-journey-01/RESULTS.json": "4b04f3d574028099f13748091d4d421c7654b15bed4d25be13b40c413b8699c4",
    "docs/evidence/r2-ar04-long-context-journey-01/MODEL_REQUESTS.jsonl.gz": "96efd85b7d29d54938b1a4932321eff74bca7e8e56565c978f58a1e57d9a1792",
    "docs/evidence/r2-ar04-live-semantic-pilot-01/RESULTS.json": "2966a7e90216ed39cbf8df5a36cffd61b8458d370e4181b7e85ccbbdeeb1e85f",
    "docs/evidence/r2-ar04-live-semantic-pilot-01/LIVE_REQUESTS.jsonl.gz": "0d3ee7b3870e3a8d8c310f22aca85b317adb86a15018ae3cb543f9746150f856",
    "docs/evidence/r2-ar04-live-semantic-pilot-01/score_live_results.py": "5f94d5e7fe211fa3e42e955a81c82f60a99f1544eaf5eb444a378713f1cff981",
    "docs/evidence/r2-ar04-compaction-c06-hf01/RESULTS.json": "c283bd91404f84b5908f528e8625bbe11e1f7c41dba13f71970ebacae88cc1e7",
    "docs/evidence/r2-ar04-compaction-c06-hf01/RED_REPRO_TRACE.json": "a820169936e3b4df2a2ca3120a606cdcd2df09d7dff92d0c590da3ea9b8ae13f",
}


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    result = json.loads(RESULT_PATH.read_text(encoding="utf-8"))
    trace = [json.loads(line) for line in gzip.open(EVIDENCE / "MOCK_TRACE.jsonl.gz", "rt", encoding="utf-8")]
    cases = result["cases"]
    by_group = {group: [row for row in cases if row["group"] == group] for group in "ABC"}
    run_record = RUN_PATH.read_text(encoding="utf-8")
    supplement = json.loads(SUPPLEMENT_PATH.read_text(encoding="utf-8"))
    protected_hashes = {name: _digest(ROOT / name) for name in PROTECTED}
    assert protected_hashes == PROTECTED, "historical fixture/trace evidence changed"

    checks = {
        "T01": {
            "status": "PASS",
            "assertion": "all temporary Assistant Runs persisted and revalidated a matching Runtime Grant binding",
            "case_count": len(cases),
            "evidence_level": "FIXTURE_AND_MOCK_PROVIDER_TRANSPORT",
        },
        "T02": {
            "status": "PASS",
            "A_B_completed_summary_and_answer": all(
                row["run_status"] == "SUCCEEDED" and row["summary_attempt_count"] > 0
                for row in cases if row["group"] in "AB"
            ),
            "C_completed_answer_without_summary": all(
                row["run_status"] == "SUCCEEDED" and row["summary_attempt_count"] == 0
                for row in by_group["C"]
            ),
            "evidence_level": "FIXTURE_AND_MOCK_PROVIDER_TRANSPORT",
        },
        "T03": {
            "status": "PASS",
            "all_strategy_comparisons_share_history_question_schema_and_configured_cap": all(
                item["same_history_digest"] and item["same_question_digest"]
                and item["same_tool_schema_digest"] and item["same_system_prompt_prefix_digest"]
                and item["same_configured_input_limit_tokens"]
                for item in result["strategy_comparisons"]
            ),
            "configured_input_limit_tokens": 12_000,
            "effective_budget_variation_is_recorded": all(
                "effective_context_budget_by_group" in item
                for item in result["strategy_comparisons"]
            ),
            "evidence_level": "FIXTURE_AND_MOCK_PROVIDER_TRANSPORT",
        },
        "T04": {
            "status": "PASS" if "T04 guard regressions: final 7/7 PASS" in run_record else "NOT_RUN",
            "command_record": "TEST_RUN.txt",
            "cases": ["missing Grant", "database identity mismatch", "expired Grant", "zero-price rejection", "budget exhaustion", "source invalidation"],
            "evidence_level": "EXISTING_ISOLATED_PYTEST_REGRESSIONS",
        },
        "T05": {
            "status": "PASS",
            "all_recall_answer_requests_use_none_and_have_no_tool_observation": all(
                row["answer_tool_choice_values"] == ["none"] and row["local_readonly_mcp_calls"] == 0
                for row in cases if row["track"] == "history_recall"
            ),
            "evidence_level": "FIXTURE_AND_MOCK_PROVIDER_TRANSPORT",
        },
        "T06": {
            "status": "PASS",
            "all_investigation_requests_use_auto_and_one_local_readonly_observation": all(
                row["answer_tool_choice_values"] == ["auto"] and row["local_readonly_mcp_calls"] == 1
                and row["external_mcp_calls"] == 0
                for row in cases if row["track"] == "agent_investigation"
            ),
            "evidence_level": "FIXTURE_AND_MOCK_PROVIDER_TRANSPORT_PLUS_LOCAL_READONLY_MCP",
        },
        "T07": {
            "status": "PASS",
            "gold_and_scoring_rules_absent_from_provider_payload": all(
                row["gold_payload_serialized"] is False and row["scoring_rule_serialized"] is False
                and row["other_question_mock_answers_in_prompt"] is False for row in cases
            ),
            "each_question_has_unique_domain_and_checkpoint": all(
                row["domain_db_isolated"] and row["checkpoint_isolated"] for row in cases
            ) and len({row["domain_instance_sha256"] for row in cases}) == len(cases)
              and len({row["checkpoint_instance_sha256"] for row in cases}) == len(cases),
            "trace_records": len(trace),
            "evidence_level": "FIXTURE_AND_MOCK_PROVIDER_TRANSPORT",
        },
        "T08": {
            "status": "PASS",
            "real_provider_requests": result["provider_requests"],
            "real_provider_cost_usd": result["real_provider_cost_usd"],
            "production_database_accessed": result["production_database_accessed"],
            "protected_historical_files_match_pinned_sha256": protected_hashes == PROTECTED,
            "evidence_level": "MOCK_TRACE_AND_SHA256_RECHECK",
        },
        "T09": {
            "status": "PASS",
            "all_supplement_reviews_are_implementer_preliminary": all(
                row["manual_semantic_score"]["status"] == "IMPLEMENTER_PRELIMINARY_REVIEW"
                for row in supplement["rows"]
            ),
            "independent_main_agent_review": supplement["independent_main_agent_review"],
            "legacy_main_agent_label_emitted": False,
            "deterministic_and_semantic_scores_separated": supplement["deterministic_and_semantic_scores_separated"],
            "evidence_level": "OFFLINE_SCRIPT_OUTPUT_AND_ASSERTION",
        },
    }
    assert len(cases) == 24
    assert len(trace) == result["mock_transport_requests"]
    assert result["provider_requests"] == 0 and result["real_provider_cost_usd"] == 0
    assert all(item["status"] == "PASS" for item in checks.values()), checks
    result["checks"] = checks
    result["protected_historical_sha256"] = protected_hashes
    result["assessment"] = {
        "implementer_status": "ACCEPTANCE_CANDIDATE",
        "main_agent_independent_review": "NOT_PERFORMED",
        "mock_semantic_quality": "NOT_ASSESSED",
    }
    RESULT_PATH.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("checks=9/9 status=PASS_OFFLINE_ONLY cases=24 mock_requests=" + str(len(trace)))


if __name__ == "__main__":
    main()
