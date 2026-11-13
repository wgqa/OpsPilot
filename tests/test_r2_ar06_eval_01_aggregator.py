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
    if record_type == "CASE_ATTEMPT":
        if case_id == "E01-D":
            fidelity = {
                "input_match": "EXACT_FROZEN_INPUT",
                "execution_source": "NEW_INDEPENDENT_TEST",
                "trusted_initial_state": "MATCH",
                "required_evidence": "SATISFIED",
                "holdout_status": "NOT_HOLDOUT",
                "assessment_modes": ["PROGRAM_ASSERTIONS", "FIXTURE_SEMANTICS"],
                "notes": "synthetic exact independent fixture case",
            }
        elif status == "NOT_RUN":
            fidelity = {
                "input_match": "NOT_RUN",
                "execution_source": "NOT_RUN",
                "trusted_initial_state": "NOT_RUN",
                "required_evidence": "NOT_RUN",
                "holdout_status": "HOLDOUT_NOT_INDEPENDENTLY_EXECUTED"
                if case_id.endswith("-H") else "NOT_HOLDOUT",
                "assessment_modes": [],
                "notes": "synthetic not-run case",
            }
        else:
            fidelity = {
                "input_match": "MAPPED_EXISTING_TEST",
                "execution_source": "REUSED_EXISTING_TRACE",
                "trusted_initial_state": "MATCH",
                "required_evidence": "SATISFIED",
                "holdout_status": "HOLDOUT_NOT_INDEPENDENTLY_EXECUTED"
                if case_id.endswith("-H") else "NOT_HOLDOUT",
                "assessment_modes": ["PROGRAM_ASSERTIONS", "FIXTURE_SEMANTICS"],
                "notes": "synthetic mapped case",
            }
    else:
        fidelity = None
    row = {
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
    if fidelity is not None:
        row["execution_fidelity"] = fidelity
    return row


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
    assert result["phase_a_offline_engineering_coverage"]["label"] == "Phase A 离线工程覆盖评定"
    assert result["phase_a_offline_engineering_coverage"]["pass_cases"] == 0
    assert result["phase_a_offline_engineering_coverage"]["planned_cases"] == 12
    assert result["phase_a_offline_engineering_coverage"]["pass_fraction"] == 0
    assert "first_attempt_completion_rate" not in result
    assert result["score_dimensions"]["M1_goal_completion"]["partial_cases"] == 11
    assert result["score_dimensions"]["M4_business_outcomes"]["run_status_is_not_used_as_business_outcome"] is True
    assert result["score_dimensions"]["M3_decision_quality"]["independent_semantic_scoring_performed"] is False
    assert result["execution_fidelity"]["frozen_input_exact_and_independent"]["case_ids"] == ["E01-D"]
    assert result["execution_fidelity"]["holdout"]["independently_executed_count"] == 0
    assert result["security_negative_count"] == 4
    assert result["security_negative_first_attempt_status_counts"]["PASS"] == 4
    assert result["usage"]["provider_requests"] == 0
    assert result["usage"]["provider_input_tokens"] is None


def test_execution_fidelity_is_separate_from_status_and_records_run_reuse():
    cases = {
        "experiment_id": "R2-AR06-EVAL-01",
        "baseline_sha": "base",
        "cases": [
            {"case_id": f"E{index:02d}-{'D' if index % 2 else 'H'}",
             "split": "D" if index % 2 else "H", "work_type": "fixture"}
            for index in range(1, 13)
        ],
        "security_negatives": [{"case_id": f"N{index:02d}"} for index in range(1, 5)],
    }
    runs = []
    for case in cases["cases"]:
        case_id = str(case["case_id"])
        status = "PASS" if case_id == "E01-D" else "NOT_RUN" if case_id == "E02-H" else "PARTIAL"
        runs.append(_row("CASE_ATTEMPT", case_id, status, "SUCCEEDED"))
    runs[2]["run_ids"] = ["fixture-run-shared"]
    for case in cases["security_negatives"]:
        row = _row("SECURITY_NEGATIVE", str(case["case_id"]), "PASS", "SUCCEEDED")
        if case["case_id"] == "N01":
            row["run_ids"] = ["fixture-run-shared"]
        runs.append(row)

    result = aggregator.aggregate(cases, runs, "cases-hash", "runs-hash")

    assert result["first_attempt_status_counts"]["PASS"] == 1
    assert result["execution_fidelity"]["input_match_counts"]["EXACT_FROZEN_INPUT"] == 1
    assert result["execution_fidelity"]["input_match_counts"]["MAPPED_EXISTING_TEST"] == 10
    assert result["execution_fidelity"]["holdout"]["not_independently_executed_case_ids"] == [
        "E02-H", "E04-H", "E06-H", "E08-H", "E10-H", "E12-H",
    ]
    assert result["execution_fidelity"]["run_reference_audit"]["shared_run_ids_between_frozen_cases"] == {}
    assert result["execution_fidelity"]["run_reference_audit"]["security_negative_reuse_of_frozen_case_runs"] == [
        {"security_negative_case_id": "N01", "case_ids": ["E03-D"], "shared_run_id_count": 1},
    ]


def test_holdout_execution_remains_executed_when_required_evidence_is_missing():
    cases = {
        "experiment_id": "R2-AR06-EVAL-01",
        "baseline_sha": "base",
        "cases": [
            {"case_id": f"E{index:02d}-{'D' if index % 2 else 'H'}",
             "split": "D" if index % 2 else "H", "work_type": "fixture"}
            for index in range(1, 13)
        ],
        "security_negatives": [{"case_id": f"N{index:02d}"} for index in range(1, 5)],
    }
    runs = [
        _row("CASE_ATTEMPT", str(case["case_id"]),
             "PASS" if case["case_id"] == "E01-D" else "NOT_RUN" if case["case_id"] == "E02-H" else "PARTIAL",
             "SUCCEEDED")
        for case in cases["cases"]
    ]
    failed_holdout = runs[1]
    failed_holdout["result_status"] = "PARTIAL"
    failed_holdout["run_status"] = "FAILED"
    failed_holdout["execution_fidelity"] = {
        "input_match": "EXACT_FROZEN_INPUT",
        "execution_source": "NEW_INDEPENDENT_TEST",
        "trusted_initial_state": "MATCH",
        "required_evidence": "PARTIAL",
        "holdout_status": "INDEPENDENT_HOLDOUT_EXECUTED",
        "assessment_modes": ["PROGRAM_ASSERTIONS"],
        "notes": "independent exact holdout run did not obtain all required evidence",
    }
    runs.extend(
        _row("SECURITY_NEGATIVE", str(case["case_id"]), "PASS", "SUCCEEDED")
        for case in cases["security_negatives"]
    )

    result = aggregator.aggregate(cases, runs, "cases-hash", "runs-hash")

    assert result["first_attempt_status_counts"]["PARTIAL"] == 11
    assert result["execution_fidelity"]["holdout"]["independently_executed_case_ids"] == ["E02-H"]
    assert result["execution_fidelity"]["frozen_input_exact_and_independent"]["case_ids"] == [
        "E01-D", "E02-H",
    ]
    assert result["execution_fidelity"]["frozen_input_exact_independent_initial_state_and_evidence_complete"]["case_ids"] == [
        "E01-D",
    ]


def test_frozen_phase_a_fidelity_metadata_keeps_original_scores():
    base = Path(__file__).resolve().parents[1] / "docs/evidence/r2-ar06-eval-01"
    cases = json.loads((base / "CASES.json").read_text(encoding="utf-8"))
    runs = aggregator._read_jsonl(base / "runs/RUNS.jsonl")
    result = aggregator.aggregate(cases, runs, "cases-hash", "runs-hash")

    assert result["first_attempt_status_counts"] == {
        "FAIL": 0, "NOT_RUN": 3, "PARTIAL": 3, "PASS": 6, "UNVERIFIED": 0,
    }
    assert result["phase_a_offline_engineering_coverage"]["pass_cases"] == 6
    assert result["phase_a_offline_engineering_coverage"]["planned_cases"] == 12
    fidelity = result["execution_fidelity"]
    assert fidelity["input_match_counts"] == {
        "EXACT_FROZEN_INPUT": 1, "MAPPED_EXISTING_TEST": 8, "NOT_RUN": 3,
    }
    assert fidelity["frozen_input_exact_and_independent"]["case_ids"] == ["E01-D"]
    assert fidelity["frozen_input_exact_independent_initial_state_and_evidence_complete"]["case_ids"] == ["E01-D"]
    assert fidelity["holdout"]["independently_executed_count"] == 0
    assert fidelity["holdout"]["not_independently_executed_case_ids"] == [
        "E02-H", "E04-H", "E06-H", "E08-H", "E10-H", "E12-H",
    ]
    audit = fidelity["run_reference_audit"]
    assert "real Provider requests are 0" in audit["run_id_scope"]
    assert audit["shared_run_ids_between_frozen_cases"] == {}
    assert [item["security_negative_case_id"] for item in audit[
        "security_negative_reuse_of_frozen_case_runs"
    ]] == ["N01-CROSS-TENANT", "N02-REVOKED-SOURCE-RESURRECTION", "N03-UNAPPROVED-CONTROLLED-ACTION"]


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
