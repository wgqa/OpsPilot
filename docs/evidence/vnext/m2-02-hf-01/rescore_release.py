from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))

from opspilot.smokes.m2_02_hf_01_release import _score_case  # noqa: E402
from opspilot.smokes.m2_02_rha_matrix import PROVIDER_CASES  # noqa: E402


HOLDOUTS = (*PROVIDER_CASES, "G4_H1", "G4_H2", "G8_H1", "G8_H2")
STRATEGIES = ("R", "H", "A")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _git_sha() -> str:
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, encoding="utf-8",
    ).strip()


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    for strategy in STRATEGIES:
        selected = [row for row in rows if row["strategy"] == strategy]
        summary[strategy] = {
            status: sum(1 for row in selected if row["trial_status"] == status)
            for status in ("PASS", "FAIL", "PARTIAL", "NOT_RUN")
        }
        summary[strategy]["by_axis"] = {
            axis: {
                status: sum(1 for row in selected if row["score_axes"].get(axis) == status)
                for status in ("PASS", "FAIL", "PARTIAL", "NOT_RUN")
            }
            for axis in ("correct_handling", "evidence_integrity", "control_safety", "boundedness")
        }
    return summary


def rescore(source_results: Path, output_dir: Path) -> dict[str, Any]:
    source_results = source_results.resolve()
    output_dir = output_dir.resolve()
    if output_dir.exists():
        raise FileExistsError(f"Refusing to overwrite existing rescore output: {output_dir}")
    source = json.loads(source_results.read_text(encoding="utf-8"))
    if source.get("fixed_denominator") != 48 or len(source.get("rows", [])) != 48:
        raise ValueError("The rescore input must contain the frozen 48-row release.")
    actual_keys = {(row["strategy"], row["case_id"].replace("-", "_")) for row in source["rows"]}
    expected_keys = {(strategy, case_id) for strategy in STRATEGIES for case_id in HOLDOUTS}
    if actual_keys != expected_keys:
        raise ValueError("The rescore input does not contain the complete fixed R/H/A holdout matrix.")

    scoring_commit = _git_sha()
    scorer_path = ROOT / "opspilot" / "smokes" / "m2_02_hf_01_release.py"
    rows: list[dict[str, Any]] = []
    for original in source["rows"]:
        row = dict(original)
        trace_ref = row.get("trace_ref")
        if not isinstance(trace_ref, str):
            raise ValueError(f"Trial {row.get('case_id')} has no saved raw Trace.")
        trace_path = ROOT / trace_ref
        if not trace_path.is_file():
            raise FileNotFoundError(trace_path)
        result = json.loads(trace_path.read_text(encoding="utf-8"))
        case_id = str(row["case_id"]).replace("-", "_")
        scored = _score_case(case_id, result)
        row.update({
            "trial_status": scored["trial_status"],
            "outcome": scored["outcome"],
            "run_id": scored["primary_run_id"],
            "score_axes": scored["score_axes"],
            "findings": scored["findings"],
            "evidence_completeness": scored["score_axes"]["evidence_integrity"],
            "safety_red_line": (
                "PASS" if scored["score_axes"]["control_safety"] == "PASS"
                else scored["score_axes"]["control_safety"]
            ),
            "score_revision": scoring_commit,
        })
        rows.append(row)

    output_dir.mkdir(parents=True)
    rescore_manifest = {
        "schema_version": "opspilot-m2-02-hf01-rescore-v1",
        "source_release_id": source.get("release_id"),
        "source_results_ref": source_results.relative_to(ROOT).as_posix(),
        "source_results_sha256": _sha256(source_results),
        "scoring_commit": scoring_commit,
        "scorer_sha256": _sha256(scorer_path),
        "replayed_provider_or_mcp_calls": False,
        "replayed_trial_traces": 48,
        "reason": "The first corrected Release exposed G8 negation false positives in the scorer; the exact 48 saved real traces were re-scored without rerunning the model or MCP.",
    }
    output = {
        "schema_version": "opspilot-m2-02-hf01-results-v2-rescored",
        "release_id": source.get("release_id"),
        "fixed_denominator": 48,
        "historical_results_mutated": False,
        "rescore_revision": rescore_manifest,
        "rows": rows,
    }
    (output_dir / "RESULTS.json").write_text(
        json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
    )
    summary = {
        "fixed_denominator": 48,
        "trial_status_by_strategy": _summary(rows),
        "release_id": source.get("release_id"),
        "scoring_commit": scoring_commit,
        "dynamic_agent_advantage_required": False,
    }
    (output_dir / "SUMMARY.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
    )
    (output_dir / "RESCORE.json").write_text(
        json.dumps(rescore_manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
    )
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Re-score saved HF-01 Release traces without new model or MCP calls.")
    parser.add_argument("--source-results", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    source = args.source_results if args.source_results.is_absolute() else ROOT / args.source_results
    output = args.output_dir if args.output_dir.is_absolute() else ROOT / args.output_dir
    print(json.dumps(rescore(source, output), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
