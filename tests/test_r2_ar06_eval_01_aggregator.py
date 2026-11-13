from __future__ import annotations

import importlib.util
import json
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/evaluation/aggregate_r2_ar06_eval_01.py"
SPEC = importlib.util.spec_from_file_location("aggregate_r2_ar06_eval_01", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
aggregator = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(aggregator)


def _row(record_type: str, case_id: str, status: str, run_status: str) -> dict[str, object]:
    return {
        "record_type": record_type,
        "case_id": case_id,
        "attempt_id": f"attempt-{case_id}",
        "attempt_no": 1,
        "result_status": status,
        "run_status": run_status,
        "task_status": "NOT_APPLICABLE",
        "expected_outcome": "frozen expectation",
        "actual_outcome": "NOT_RUN" if status == "NOT_RUN" else "EXPLANATION_DELIVERED",
        "business_outcome_code": "NOT_RUN" if status == "NOT_RUN" else "ANSWERED_GENERAL",
        "evidence_completeness": "NOT_RUN" if status == "NOT_RUN" else "PARTIAL",
        "evidence_validity": "NOT_RUN" if status == "NOT_RUN" else "UNVERIFIED",
        "decision_quality_rating": "UNVERIFIED",
        "unsupported_certainty_count": 0,
        "safety_red_lines": [],
        "session_ids": [],
        "task_ids": [],
        "run_ids": [],
        "provider_requests": 0,
        "provider_input_tokens": None,
        "provider_output_tokens": None,
        "provider_cost_usd": None,
        "mcp_tools_call_count": 0 if status != "NOT_RUN" else None,
        "fixture_model_dispatches": 0 if status != "NOT_RUN" else None,
        "fixture_token_metadata": [],
        "elapsed_ms": None,
        "trace_refs": [],
        "release_ref": {"git_sha": "fixture"},
    }


def test_aggregator_keeps_not_run_denominator_and_does_not_infer_pass_from_run():
    cases = {
        "experiment_id": "R2-AR06-EVAL-01",
        "baseline_sha": "base",
        "cases": [
            {"case_id": f"E{index:02d}-{'D' if index % 2 else 'H'}",
             "split": "D" if index % 2 else "H", "work_type": "fixture"}
            for index in range(1, 13)
        ],
        "security_negatives": [
            {"case_id": f"N{index:02d}"} for index in range(1, 5)
        ],
    }
    runs = []
    for case in cases["cases"]:
        status = "NOT_RUN" if case["case_id"].startswith("E02") else "PARTIAL"
        # A successful workflow is intentionally still PARTIAL.
        runs.append(_row("CASE_ATTEMPT", str(case["case_id"]), status,
                         "NOT_RUN" if status == "NOT_RUN" else "SUCCEEDED"))
    for case in cases["security_negatives"]:
        runs.append(_row("SECURITY_NEGATIVE", str(case["case_id"]), "PASS", "SUCCEEDED"))

    result = aggregator.aggregate(cases, runs, "cases-hash", "runs-hash")

    assert result["planned_case_count"] == 12
    assert result["first_attempt_status_counts"]["NOT_RUN"] == 1
    assert result["first_attempt_status_counts"]["PASS"] == 0
    assert result["first_attempt_completion_rate"] == 0
    assert result["score_dimensions"]["M1_goal_completion"]["partial_cases"] == 11
    assert result["score_dimensions"]["M4_business_outcomes"]["run_status_is_not_used_as_business_outcome"] is True
    assert result["score_dimensions"]["M3_decision_quality"]["independent_semantic_scoring_performed"] is False
    assert result["security_negative_count"] == 4
    assert result["security_negative_first_attempt_status_counts"]["PASS"] == 4
    assert result["usage"]["provider_requests"] == 0
    assert result["usage"]["provider_input_tokens"] is None


def test_aggregator_rejects_missing_case_attempts():
    cases = {
        "experiment_id": "R2-AR06-EVAL-01",
        "baseline_sha": "base",
        "cases": [{"case_id": f"E{index:02d}-D", "split": "D", "work_type": "fixture"}
                  for index in range(1, 13)],
        "security_negatives": [{"case_id": f"N{index:02d}"} for index in range(1, 5)],
    }
    runs = [
        _row("CASE_ATTEMPT", str(case["case_id"]), "NOT_RUN", "NOT_RUN")
        for case in cases["cases"][:-1]
    ]
    runs.extend(_row("SECURITY_NEGATIVE", str(case["case_id"]), "NOT_RUN", "NOT_RUN")
                for case in cases["security_negatives"])

    try:
        aggregator.aggregate(cases, runs, "cases-hash", "runs-hash")
    except ValueError as exc:
        assert "Missing frozen cases" in str(exc)
    else:
        raise AssertionError("Aggregator accepted an incomplete frozen denominator")
