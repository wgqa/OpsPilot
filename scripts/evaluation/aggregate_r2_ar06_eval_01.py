"""Aggregate the frozen OpsPilot R2 AR06 case-attempt JSONL file.

This is deliberately specific to R2-AR06-EVAL-01. It does not execute an
Assistant, score model text, or infer a case result from a Run status.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


RESULT_STATUSES = {"PASS", "PARTIAL", "FAIL", "NOT_RUN", "UNVERIFIED"}
FIDELITY_INPUTS = {"EXACT_FROZEN_INPUT", "MAPPED_EXISTING_TEST", "NOT_RUN"}
FIDELITY_SOURCES = {"NEW_INDEPENDENT_TEST", "REUSED_EXISTING_TRACE", "NOT_RUN"}
FIDELITY_STATES = {"MATCH", "PARTIAL", "NOT_RUN"}
FIDELITY_EVIDENCE = {"SATISFIED", "PARTIAL", "NOT_RUN"}
HOLDOUT_STATUSES = {"NOT_HOLDOUT", "HOLDOUT_NOT_INDEPENDENTLY_EXECUTED", "INDEPENDENT_HOLDOUT_EXECUTED"}
RUN_FIELDS = {
    "record_type", "case_id", "attempt_id", "attempt_no", "result_status",
    "run_status", "task_status", "expected_outcome", "actual_outcome",
    "business_outcome_code",
    "evidence_completeness", "evidence_validity", "decision_quality_rating",
    "unsupported_certainty_count", "safety_red_lines", "session_ids", "task_ids",
    "run_ids", "provider_requests", "provider_input_tokens", "provider_output_tokens",
    "provider_cost_usd", "mcp_tools_call_count", "fixture_model_dispatches",
    "fixture_token_metadata", "elapsed_ms", "trace_refs", "release_ref",
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return value


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        value = json.loads(line)
        if not isinstance(value, dict):
            raise ValueError(f"JSONL row {line_no} must be an object")
        missing = sorted(RUN_FIELDS - value.keys())
        if missing:
            raise ValueError(f"JSONL row {line_no} missing fields: {', '.join(missing)}")
        if value["result_status"] not in RESULT_STATUSES:
            raise ValueError(f"JSONL row {line_no} has invalid result_status")
        if not isinstance(value["attempt_no"], int) or value["attempt_no"] < 1:
            raise ValueError(f"JSONL row {line_no} has invalid attempt_no")
        if not isinstance(value["safety_red_lines"], list):
            raise ValueError(f"JSONL row {line_no} safety_red_lines must be a list")
        rows.append(value)
    return rows


def _sum_known(rows: list[dict[str, Any]], field: str) -> int | float | None:
    values = [row.get(field) for row in rows]
    if not values or any(value is None for value in values):
        return None
    return sum(values)


def _validate_execution_fidelity(row: dict[str, Any], split: str) -> dict[str, Any]:
    fidelity = row.get("execution_fidelity")
    if not isinstance(fidelity, dict):
        raise ValueError(f"CASE_ATTEMPT {row.get('case_id')} missing execution_fidelity")
    required = {
        "input_match", "execution_source", "trusted_initial_state", "required_evidence",
        "holdout_status", "assessment_modes", "notes",
    }
    missing = sorted(required - fidelity.keys())
    if missing:
        raise ValueError(
            f"CASE_ATTEMPT {row.get('case_id')} execution_fidelity missing fields: "
            f"{', '.join(missing)}"
        )
    if fidelity["input_match"] not in FIDELITY_INPUTS:
        raise ValueError(f"CASE_ATTEMPT {row.get('case_id')} has invalid input_match")
    if fidelity["execution_source"] not in FIDELITY_SOURCES:
        raise ValueError(f"CASE_ATTEMPT {row.get('case_id')} has invalid execution_source")
    if fidelity["trusted_initial_state"] not in FIDELITY_STATES:
        raise ValueError(f"CASE_ATTEMPT {row.get('case_id')} has invalid trusted_initial_state")
    if fidelity["required_evidence"] not in FIDELITY_EVIDENCE:
        raise ValueError(f"CASE_ATTEMPT {row.get('case_id')} has invalid required_evidence")
    if fidelity["holdout_status"] not in HOLDOUT_STATUSES:
        raise ValueError(f"CASE_ATTEMPT {row.get('case_id')} has invalid holdout_status")
    if not isinstance(fidelity["assessment_modes"], list) or not all(
        isinstance(item, str) for item in fidelity["assessment_modes"]
    ):
        raise ValueError(f"CASE_ATTEMPT {row.get('case_id')} assessment_modes must be a string list")
    if not isinstance(fidelity["notes"], str):
        raise ValueError(f"CASE_ATTEMPT {row.get('case_id')} fidelity notes must be a string")

    independent_execution = (
        fidelity["input_match"] == "EXACT_FROZEN_INPUT"
        and fidelity["execution_source"] == "NEW_INDEPENDENT_TEST"
        and fidelity["trusted_initial_state"] == "MATCH"
    )
    expected_holdout = (
        "INDEPENDENT_HOLDOUT_EXECUTED" if independent_execution
        else "HOLDOUT_NOT_INDEPENDENTLY_EXECUTED"
    )
    expected_status = expected_holdout if split == "H" else "NOT_HOLDOUT"
    if fidelity["holdout_status"] != expected_status:
        raise ValueError(
            f"CASE_ATTEMPT {row.get('case_id')} holdout_status conflicts with fidelity fields"
        )
    return fidelity


def aggregate(cases: dict[str, Any], runs: list[dict[str, Any]], cases_sha256: str, runs_sha256: str) -> dict[str, Any]:
    case_rows = cases.get("cases")
    negative_rows = cases.get("security_negatives")
    if not isinstance(case_rows, list) or not isinstance(negative_rows, list):
        raise ValueError("CASES.json must contain cases and security_negatives arrays")

    cases_by_id = {str(row["case_id"]): row for row in case_rows}
    negatives_by_id = {str(row["case_id"]): row for row in negative_rows}
    if len(cases_by_id) != len(case_rows) or len(cases_by_id) != 12:
        raise ValueError("Expected exactly 12 unique frozen case IDs")
    if len(negatives_by_id) != len(negative_rows) or len(negatives_by_id) != 4:
        raise ValueError("Expected exactly four unique security-negative IDs")

    attempts: dict[str, list[dict[str, Any]]] = defaultdict(list)
    security_attempts: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in runs:
        record_type = row["record_type"]
        case_id = str(row["case_id"])
        if record_type == "CASE_ATTEMPT":
            if case_id not in cases_by_id:
                raise ValueError(f"Unknown case_id: {case_id}")
            _validate_execution_fidelity(row, str(cases_by_id[case_id]["split"]))
            attempts[case_id].append(row)
        elif record_type == "SECURITY_NEGATIVE":
            if case_id not in negatives_by_id:
                raise ValueError(f"Unknown security-negative case_id: {case_id}")
            security_attempts[case_id].append(row)
        else:
            raise ValueError(f"Unsupported record_type: {record_type}")

    missing = sorted(set(cases_by_id) - set(attempts))
    if missing:
        raise ValueError(f"Missing frozen cases from RUNS.jsonl: {', '.join(missing)}")
    missing_negatives = sorted(set(negatives_by_id) - set(security_attempts))
    if missing_negatives:
        raise ValueError(f"Missing security negatives from RUNS.jsonl: {', '.join(missing_negatives)}")

    first_attempts: list[dict[str, Any]] = []
    case_results: list[dict[str, Any]] = []
    first_fidelity_by_case: dict[str, dict[str, Any]] = {}
    by_split: dict[str, Counter[str]] = defaultdict(Counter)
    by_work_type: dict[str, Counter[str]] = defaultdict(Counter)
    for case_id, case in cases_by_id.items():
        rows = sorted(attempts[case_id], key=lambda item: item["attempt_no"])
        if len({row["attempt_no"] for row in rows}) != len(rows):
            raise ValueError(f"Duplicate attempt_no for {case_id}")
        first = rows[0]
        first_attempts.append(first)
        fidelity = _validate_execution_fidelity(first, str(case["split"]))
        first_fidelity_by_case[case_id] = fidelity
        status = first["result_status"]
        by_split[str(case["split"])][status] += 1
        by_work_type[str(case["work_type"])][status] += 1
        case_results.append({
            "case_id": case_id,
            "work_type": case["work_type"],
            "split": case["split"],
            "first_attempt_id": first["attempt_id"],
            "first_attempt_status": status,
            "attempt_count": len(rows),
            "first_attempt_run_status": first["run_status"],
            "business_outcome": first["actual_outcome"],
            "business_outcome_code": first["business_outcome_code"],
            "evidence_completeness": first["evidence_completeness"],
            "evidence_validity": first["evidence_validity"],
            "execution_fidelity": fidelity,
            "trace_refs": first["trace_refs"],
        })

    status_counts = Counter(row["result_status"] for row in first_attempts)
    evidence_validity_counts = Counter(row["evidence_validity"] for row in first_attempts)
    decision_quality_counts = Counter(row["decision_quality_rating"] for row in first_attempts)
    business_outcome_counts = Counter(row["business_outcome_code"] for row in first_attempts)
    certainty_values = [
        row["unsupported_certainty_count"] for row in first_attempts
        if isinstance(row["unsupported_certainty_count"], int)
    ]
    security_results: list[dict[str, Any]] = []
    security_counts: Counter[str] = Counter()
    for case_id, case in negatives_by_id.items():
        rows = sorted(security_attempts[case_id], key=lambda item: item["attempt_no"])
        first = rows[0]
        security_counts[first["result_status"]] += 1
        security_results.append({
            "case_id": case_id,
            "first_attempt_status": first["result_status"],
            "attempt_count": len(rows),
            "safety_red_lines": first["safety_red_lines"],
            "trace_refs": first["trace_refs"],
        })

    all_first = first_attempts + [
        sorted(security_attempts[case_id], key=lambda item: item["attempt_no"])[0]
        for case_id in negatives_by_id
    ]
    red_lines = [
        {"case_id": row["case_id"], "finding": value}
        for row in all_first
        for value in row["safety_red_lines"]
    ]
    fidelity_input_counts = Counter(value["input_match"] for value in first_fidelity_by_case.values())
    fidelity_source_counts = Counter(value["execution_source"] for value in first_fidelity_by_case.values())
    exact_independent_ids = sorted(
        case_id for case_id, value in first_fidelity_by_case.items()
        if value["input_match"] == "EXACT_FROZEN_INPUT"
        and value["execution_source"] == "NEW_INDEPENDENT_TEST"
    )
    fully_supported_exact_ids = sorted(
        case_id for case_id, value in first_fidelity_by_case.items()
        if value["input_match"] == "EXACT_FROZEN_INPUT"
        and value["execution_source"] == "NEW_INDEPENDENT_TEST"
        and value["trusted_initial_state"] == "MATCH"
        and value["required_evidence"] == "SATISFIED"
    )
    holdout_ids = sorted(case_id for case_id, case in cases_by_id.items() if str(case["split"]) == "H")
    independently_executed_holdouts = sorted(
        case_id for case_id in holdout_ids
        if first_fidelity_by_case[case_id]["holdout_status"] == "INDEPENDENT_HOLDOUT_EXECUTED"
    )

    case_run_owners: dict[str, set[str]] = defaultdict(set)
    case_run_reference_count = 0
    for case_id, rows in attempts.items():
        for row in rows:
            for run_id in row.get("run_ids") or []:
                case_run_reference_count += 1
                case_run_owners[str(run_id)].add(case_id)
    shared_case_run_ids = {
        run_id: sorted(owners) for run_id, owners in case_run_owners.items() if len(owners) > 1
    }
    security_reuse: list[dict[str, Any]] = []
    for negative_id, rows in security_attempts.items():
        overlapping_ids = {
            str(run_id) for row in rows for run_id in (row.get("run_ids") or [])
            if str(run_id) in case_run_owners
        }
        if overlapping_ids:
            case_ids = sorted({
                case_id for run_id in overlapping_ids for case_id in case_run_owners[run_id]
            })
            security_reuse.append({
                "security_negative_case_id": negative_id,
                "case_ids": case_ids,
                "shared_run_id_count": len(overlapping_ids),
            })

    exact_independent_ratio = len(exact_independent_ids) / len(cases_by_id)
    fully_supported_ratio = len(fully_supported_exact_ids) / len(cases_by_id)
    return {
        "schema_version": 1,
        "experiment_id": cases.get("experiment_id"),
        "baseline_sha": cases.get("baseline_sha"),
        "source_hashes": {"cases_sha256": cases_sha256, "runs_jsonl_sha256": runs_sha256},
        "planned_case_count": len(cases_by_id),
        "attempt_record_count": len(runs),
        "first_attempt_status_counts": {key: status_counts.get(key, 0) for key in sorted(RESULT_STATUSES)},
        "phase_a_offline_engineering_coverage": {
            "label": "Phase A 离线工程覆盖评定",
            "pass_cases": status_counts.get("PASS", 0),
            "planned_cases": len(cases_by_id),
            "pass_fraction": status_counts.get("PASS", 0) / len(cases_by_id),
            "interpretation": "Fixture/offline engineering coverage only; not current real-model task success rate.",
        },
        "execution_fidelity": {
            "input_match_counts": {key: fidelity_input_counts.get(key, 0) for key in sorted(FIDELITY_INPUTS)},
            "execution_source_counts": {key: fidelity_source_counts.get(key, 0) for key in sorted(FIDELITY_SOURCES)},
            "frozen_input_exact_and_independent": {
                "case_ids": exact_independent_ids,
                "case_count": len(exact_independent_ids),
                "planned_cases": len(cases_by_id),
                "fraction": exact_independent_ratio,
            },
            "frozen_input_exact_independent_initial_state_and_evidence_complete": {
                "case_ids": fully_supported_exact_ids,
                "case_count": len(fully_supported_exact_ids),
                "planned_cases": len(cases_by_id),
                "fraction": fully_supported_ratio,
            },
            "holdout": {
                "case_count": len(holdout_ids),
                "independently_executed_case_ids": independently_executed_holdouts,
                "independently_executed_count": len(independently_executed_holdouts),
                "not_independently_executed_case_ids": sorted(set(holdout_ids) - set(independently_executed_holdouts)),
            },
            "run_reference_audit": {
                "run_id_scope": "Fixture/Mock or isolated local test Run IDs only; Phase A real Provider requests are 0.",
                "case_attempt_records": sum(len(rows) for rows in attempts.values()),
                "case_run_reference_count": case_run_reference_count,
                "unique_case_run_id_count": len(case_run_owners),
                "shared_run_ids_between_frozen_cases": shared_case_run_ids,
                "security_negative_reuse_of_frozen_case_runs": sorted(
                    security_reuse, key=lambda item: item["security_negative_case_id"],
                ),
            },
        },
        "score_dimensions": {
            "M1_goal_completion": {
                "complete_cases": status_counts.get("PASS", 0),
                "planned_cases": len(cases_by_id),
                "partial_cases": status_counts.get("PARTIAL", 0),
                "failed_cases": status_counts.get("FAIL", 0),
                "not_run_cases": status_counts.get("NOT_RUN", 0),
                "unverified_cases": status_counts.get("UNVERIFIED", 0),
            },
            "M2_evidence_and_calibration": {
                "evidence_validity_counts": dict(sorted(evidence_validity_counts.items())),
                "unsupported_certainty_count": sum(certainty_values) if certainty_values else None,
                "certainty_count_known_cases": len(certainty_values),
            },
            "M3_decision_quality": {
                "rating_counts": dict(sorted(decision_quality_counts.items())),
                "independent_semantic_scoring_performed": False,
            },
            "M4_business_outcomes": {
                "outcome_counts": dict(sorted(business_outcome_counts.items())),
                "run_status_is_not_used_as_business_outcome": True,
            },
            "M6_safety": {
                "red_line_finding_count": len(red_lines),
                "security_negative_counts": {
                    key: security_counts.get(key, 0) for key in sorted(RESULT_STATUSES)
                },
            },
        },
        "by_split": {
            split: {key: counts.get(key, 0) for key in sorted(RESULT_STATUSES)}
            for split, counts in sorted(by_split.items())
        },
        "by_work_type": {
            work_type: {key: counts.get(key, 0) for key in sorted(RESULT_STATUSES)}
            for work_type, counts in sorted(by_work_type.items())
        },
        "case_results": sorted(case_results, key=lambda item: item["case_id"]),
        "security_negative_count": len(negatives_by_id),
        "security_negative_first_attempt_status_counts": {
            key: security_counts.get(key, 0) for key in sorted(RESULT_STATUSES)
        },
        "security_negative_results": sorted(security_results, key=lambda item: item["case_id"]),
        "safety_red_lines": red_lines,
        "usage": {
            "provider_requests": _sum_known(first_attempts, "provider_requests"),
            "provider_input_tokens": _sum_known(first_attempts, "provider_input_tokens"),
            "provider_output_tokens": _sum_known(first_attempts, "provider_output_tokens"),
            "provider_cost_usd": _sum_known(first_attempts, "provider_cost_usd"),
            "mcp_tools_call_count": _sum_known(first_attempts, "mcp_tools_call_count"),
            "fixture_model_dispatches": _sum_known(first_attempts, "fixture_model_dispatches"),
            "fixture_token_metadata": "Per-attempt fixture metadata stays in RUNS.jsonl and is not added to provider token totals.",
            "latency_policy": "Per-attempt elapsed_ms is in RUNS.jsonl; no p50/p95 is calculated from this small mixed fixture set."
        },
        "aggregation_policy": "First attempts only for case outcome; all attempts remain recorded. Explicit result_status is consumed as written and never derived from run_status. Execution fidelity is a separate evidence dimension and never changes status. Security negatives are separate from the 12-case denominator."
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", required=True, type=Path)
    parser.add_argument("--runs", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    cases = _read_json(args.cases)
    runs = _read_jsonl(args.runs)
    result = aggregate(cases, runs, _sha256(args.cases), _sha256(args.runs))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    coverage = result["phase_a_offline_engineering_coverage"]
    exact = result["execution_fidelity"]["frozen_input_exact_and_independent"]
    print(f"Wrote {args.output}: Phase A offline engineering coverage "
          f"{coverage['pass_cases']}/{coverage['planned_cases']} PASS; "
          f"exact independent {exact['case_count']}/{exact['planned_cases']}; "
          f"{result['usage']['provider_requests']} Provider requests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
