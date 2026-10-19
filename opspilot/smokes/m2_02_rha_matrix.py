from __future__ import annotations

import argparse
import asyncio
import json
import traceback
from pathlib import Path
from typing import Any

from opspilot.config import load_local_environment
from opspilot.smokes import m2_02_g4, m2_02_g4_401, m2_02_g8, m2_02_provider_traces


PROVIDER_CASES = (
    "G1_H1", "G1_H2", "G2_H1", "G2_H2", "G3_H1", "G3_H2",
    "G5_H1", "G5_H2", "G6_H1", "G6_H2", "G7_H1", "G7_H2",
)


async def _run_trial(strategy: str, case_id: str, runtime_root: Path) -> dict[str, Any]:
    case_root = runtime_root / strategy / case_id
    case_root.mkdir(parents=True, exist_ok=True)
    if case_id in m2_02_provider_traces.CASES:
        return await m2_02_provider_traces._run_case(
            case_id, m2_02_provider_traces.CASES[case_id], case_root, strategy=strategy,
        )
    if case_id == "G4_H1":
        return await m2_02_g4._run(
            case_root / "domain.sqlite3", case_root / "checkpoints.sqlite3", strategy,
        )
    if case_id == "G4_H2":
        return await m2_02_g4_401._run(
            case_root / "domain.sqlite3", case_root / "checkpoints.sqlite3", strategy,
        )
    if case_id in m2_02_g8.QUESTIONS:
        return await m2_02_g8._run_case(case_id, case_root, strategy=strategy)
    raise ValueError(f"Unknown frozen holdout case: {case_id}")


def _status(case_id: str, result: dict[str, Any]) -> tuple[str, str | None]:
    if case_id.startswith("G8_"):
        outcome = result.get("business_outcome_after_chat")
        expected = "HANDOFF_READY" if case_id == "G8_H1" else "INCONCLUSIVE"
        answer = result.get("answer", {})
        text = str(answer.get("answer", "")).casefold() if isinstance(answer, dict) else ""
        if outcome != expected:
            return "FAIL", f"expected {expected}, got {outcome}"
        if any(term in text for term in ("已经修好", "已提交", "已交接")) and expected == "HANDOFF_READY":
            return "FAIL", "readonly answer overclaimed repair or submission"
        return "PASS", None
    outcome = result.get("s2_outcome")
    if isinstance(outcome, dict):
        outcome = outcome.get("business_outcome")
    if outcome is None:
        outcome = result.get("business_outcome")
        if isinstance(outcome, dict):
            outcome = outcome.get("business_outcome")
    if case_id in {"G1_H1", "G2_H1", "G2_H2", "G3_H2", "G4_H1", "G5_H1", "G5_H2"}:
        expected = "HANDOFF_READY"
    elif case_id == "G3_H1" or case_id == "G4_H2":
        expected = None  # S1 remains on its original approval path or safely stops.
    elif case_id in {"G6_H1", "G6_H2"}:
        expected = "NO_ACTION"
    else:
        expected = "INCONCLUSIVE"
    if expected is None:
        if outcome in {"HANDOFF_READY", "DIAGNOSED", "NO_S2_DIAGNOSIS", "INCONCLUSIVE", "NO_ACTION"}:
            return "PASS", None
        return "FAIL", f"expected the existing S1 path or safe stop, got {outcome}"
    if outcome == expected:
        return "PASS", None
    return "FAIL", f"expected {expected}, got {outcome}"


async def _run(strategies: list[str], runtime_root: Path, evidence_root: Path) -> list[dict[str, Any]]:
    load_local_environment()
    rows: list[dict[str, Any]] = []
    for strategy in strategies:
        for case_id in (*PROVIDER_CASES, "G4_H1", "G4_H2", "G8_H1", "G8_H2"):
            raw_path = evidence_root / strategy / f"{case_id}.json"
            error_path = evidence_root / strategy / f"{case_id}.stderr.txt"
            try:
                result = await _run_trial(strategy, case_id, runtime_root)
                raw_path.parent.mkdir(parents=True, exist_ok=True)
                raw_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                status, failure = _status(case_id, result)
                rows.append({
                    "journey_id": case_id.split("_")[0],
                    "instance_id": case_id.rsplit("_", 1)[-1],
                    "case_id": case_id.replace("_", "-"),
                    "strategy": strategy,
                    "trial_status": status,
                    "raw_trace_ref": raw_path.as_posix(),
                    "failure_reason": failure,
                    "task_id": result.get("task_id"),
                    "run_id": result.get("run_id") or result.get("initial_run_id"),
                    "outcome": (
                        result.get("business_outcome_after_chat")
                        or result.get("s2_outcome", {}).get("business_outcome")
                        or (result.get("business_outcome", {}).get("business_outcome")
                            if isinstance(result.get("business_outcome"), dict) else result.get("business_outcome"))
                    ),
                })
            except Exception as error:
                error_path.parent.mkdir(parents=True, exist_ok=True)
                error_path.write_text(traceback.format_exc(), encoding="utf-8")
                rows.append({
                    "journey_id": case_id.split("_")[0],
                    "instance_id": case_id.rsplit("_", 1)[-1],
                    "case_id": case_id.replace("_", "-"),
                    "strategy": strategy,
                    "trial_status": "NOT_RUN",
                    "raw_trace_ref": error_path.as_posix(),
                    "failure_reason": f"{type(error).__name__}: {error}",
                    "task_id": None,
                    "run_id": None,
                    "outcome": None,
                })
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the frozen M2-02 R/H policy comparison on isolated holdouts.")
    parser.add_argument("--strategies", nargs="+", choices=("R", "H"), default=["R", "H"])
    parser.add_argument("--runtime-dir", type=Path, required=True)
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--score-from", type=Path, help="Re-score already saved raw trial traces without rerunning them.")
    args = parser.parse_args()
    if args.score_from is not None:
        rows = json.loads(args.score_from.read_text(encoding="utf-8"))
        for row in rows:
            trace_path = Path(str(row.get("raw_trace_ref", "")))
            if row.get("trial_status") == "NOT_RUN" or not trace_path.is_file() or trace_path.suffix != ".json":
                continue
            result = json.loads(trace_path.read_text(encoding="utf-8"))
            case_id = str(row["case_id"]).replace("-", "_")
            status, failure = _status(case_id, result)
            row["trial_status"] = status
            row["failure_reason"] = failure
            if case_id.startswith("G8_"):
                row["outcome"] = result.get("business_outcome_after_chat")
            elif isinstance(result.get("s2_outcome"), dict):
                row["outcome"] = result["s2_outcome"].get("business_outcome")
            else:
                outcome = result.get("business_outcome")
                row["outcome"] = outcome.get("business_outcome") if isinstance(outcome, dict) else outcome
    else:
        rows = asyncio.run(_run(args.strategies, args.runtime_dir, args.evidence_dir))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    summary_strategies = sorted({str(row.get("strategy")) for row in rows})
    print(json.dumps({
        "trials": len(rows),
        "by_strategy": {
            strategy: {
                status: sum(1 for row in rows if row["strategy"] == strategy and row["trial_status"] == status)
                for status in ("PASS", "FAIL", "PARTIAL", "NOT_RUN")
            }
            for strategy in summary_strategies
        },
        "output": args.output.as_posix(),
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
