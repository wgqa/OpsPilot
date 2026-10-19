from __future__ import annotations

"""Preserve a paired evaluation and isolate only its failed S2 ON provider arms."""

import argparse
import json
from pathlib import Path
from typing import Any

from opspilot.config import MODEL_NAME, ROOT, load_local_environment
from opspilot.smokes import m301_eval as evaluation


S2_PAIRS = {"P03", "P04", "P05", "P06", "P08"}


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")


def _persisted_trial_paths(pair_id: str, arm: str) -> tuple[Path, Path, Path]:
    runtime = ROOT / ".runtime" / "m301-paired-eval"
    return (
        runtime / f"{pair_id}-template.sqlite3",
        runtime / f"{pair_id}-{arm.lower()}.sqlite3",
        runtime / f"{pair_id}-{arm.lower()}-checkpoints.sqlite3",
    )


def _evaluation_fields(item: dict[str, Any], case: dict[str, Any]) -> None:
    result = item
    pair_id = str(item["pair"]["pair_id"])
    arm = str(item["evaluation"]["arm"])
    outcome = result.get("s2_business_outcome") if pair_id in S2_PAIRS else result.get("s1_gate_decision")
    normalized = "NO_ACTION" if outcome in {"NO_S2_DIAGNOSIS", "NO_ACTION"} else outcome
    allowed = list(case["allowed_outcomes"])
    result["evaluation"].update({
        "allowed_outcomes": allowed,
        "observed_outcome": normalized,
        "outcome_allowed": normalized in allowed,
        "selected_memory_count": len(result.get("selected_memories", [])),
        "selected_different_task_memory": any(
            memory.get("source_task_id") != result.get("task_id")
            for memory in result.get("selected_memories", [])
        ),
        "no_repair_or_deliver": (
            result.get("business_writes", {}).get("repair_ledgers", 0) == 0
            and result.get("business_writes", {}).get("deliver_ledgers", 0) == 0
        ),
        "no_scope_grant_write": bool(result.get("no_scope_grant_write")),
        "execution_ok": result.get("execution_error") is None,
        "recovered_persisted_trial": False,
        "isolated_retry_after_preserved_failure": bool(result.get("isolated_retry_after_preserved_failure")),
    })


def recover(prior_dir: str | Path, evidence_dir: str | Path) -> int:
    load_local_environment()
    prior_root = evaluation._absolute(prior_dir)
    output = evaluation._absolute(evidence_dir)
    output.mkdir(parents=True, exist_ok=True)
    gold = json.loads((ROOT / "docs/evidence/vnext/m3-01/GOLD.json").read_text(encoding="utf-8"))
    if evaluation.os.environ.get(MODEL_NAME) != str(gold["provider"]["model_id"]):
        raise RuntimeError("Loaded model ID differs from frozen Gold; no recovery trial was run.")
    original = json.loads((prior_root / "RESULTS.json").read_text(encoding="utf-8"))
    if original.get("gold_id") != gold["gold_id"] or original.get("actual_trials") != 16:
        raise RuntimeError("Recovery requires the complete frozen 16-arm original evaluation.")
    by_arm = {
        (str(item["pair"]["pair_id"]), str(item["evaluation"]["arm"])): item
        for item in original["trials"]
    }
    if len(by_arm) != 16:
        raise RuntimeError("Original results do not contain exactly 16 unique ON/OFF arms.")

    failures: list[dict[str, Any]] = []
    rerun_logs: list[dict[str, str]] = []
    case_by_id = {str(case["pair_id"]): case for case in gold["cases"]}
    for pair_id in sorted(S2_PAIRS):
        item = by_arm[(pair_id, "ON")]
        bad_traces = [trace for trace in item.get("model_traces", []) if trace.get("status") != "OK"]
        if not bad_traces:
            continue
        task_id = str(item["task_id"])
        template, trial_db, checkpoint_db = _persisted_trial_paths(pair_id, "ON")
        if not template.is_file() or not trial_db.is_file():
            raise RuntimeError(f"Missing frozen snapshot for {pair_id}/ON; refusing to synthesize a retry case.")
        failures.append(evaluation._failed_attempt_snapshot(trial_db, task_id, pair_id, "ON"))

        pair = item["pair"]
        run_id = str(item["run_id"])
        actor_id = "support-b" if pair.get("target_tenant") == "tenant-b" else "support-a"
        if trial_db.exists():
            trial_db.unlink()
        if checkpoint_db.exists():
            checkpoint_db.unlink()
        evaluation._backup(template, trial_db)
        log_path = output / "trials" / f"{pair_id}-on-isolated.worker.log"
        retried = evaluation._run_trial(
            db_path=trial_db, checkpoint_path=checkpoint_db, task_id=task_id, run_id=run_id,
            actor_id=actor_id, s2_mode=True, memory_enabled=True, log_path=log_path,
        )
        retried["evaluation"] = dict(item["evaluation"])
        retried["pair"] = dict(pair)
        retried["isolated_retry_after_preserved_failure"] = True
        retried["original_failed_attempt"] = {
            "source_directory": str(prior_root),
            "failed_model_trace_count": len(bad_traces),
        }
        _evaluation_fields(retried, case_by_id[pair_id])
        by_arm[(pair_id, "ON")] = retried
        rerun_logs.append({"pair_id": pair_id, "arm": "ON", "log": str(log_path.relative_to(output))})
        print(json.dumps({
            "event": "m301_isolated_retry", "pair_id": pair_id,
            "outcome": retried["evaluation"]["observed_outcome"],
            "outcome_allowed": retried["evaluation"]["outcome_allowed"],
            "model_calls": len(retried["model_traces"]), "mcp_attempts": retried["attempt_counts"].get("MCP", 0),
            "execution_error": retried["execution_error"],
        }, ensure_ascii=False), flush=True)

    _write_json(output / "FAILED_ATTEMPTS.json", {
        "schema_version": "m301-failed-attempts-v1",
        "source_evaluation": str(prior_root),
        "preserved_attempts": failures,
        "rerun_logs": rerun_logs,
    })

    trials = [by_arm[(str(case["pair_id"]), arm)] for case in gold["cases"] for arm in ("ON", "OFF")]
    pairs: list[dict[str, Any]] = []
    for case in gold["cases"]:
        pair_id = str(case["pair_id"])
        on, off = by_arm[(pair_id, "ON")], by_arm[(pair_id, "OFF")]
        for item in (on, off):
            _evaluation_fields(item, case)
        pairs.append({
            "pair_id": pair_id, "category": case["category"],
            "ON": on["evaluation"], "OFF": off["evaluation"],
            "token_totals": {
                "ON": evaluation._token_total(on.get("model_traces", [])),
                "OFF": evaluation._token_total(off.get("model_traces", [])),
            },
            "mcp_tool_calls": {
                "ON": on.get("attempt_counts", {}).get("MCP", 0),
                "OFF": off.get("attempt_counts", {}).get("MCP", 0),
            },
            "investigation_tools": {
                "ON": [tool for trace in on.get("model_traces", []) for tool in trace.get("tool_names", [])],
                "OFF": [tool for trace in off.get("model_traces", []) for tool in trace.get("tool_names", [])],
            },
        })
    final_results = {
        **original,
        "schema_version": "m301-results-v1-recovered",
        "executed_at": evaluation.datetime.now(evaluation.timezone.utc).isoformat(),
        "evaluation_code_git_head": evaluation._git_head(),
        "model_id": evaluation.os.environ.get(MODEL_NAME),
        "planned_pairs": 8, "planned_trials": 16, "actual_trials": len(trials),
        "recovery_source": str(prior_root), "isolated_retry_count": len(rerun_logs),
        "pairs": pairs, "trials": trials,
        "utility_assessment": "UTILITY_NOT_PROVEN",
        "limitations": [
            "Exploratory paired sample only; no statistical or generalization claim.",
            "Successful arms are reused from the immutable first attempt; only failed S2 ON Provider arms are rerun in separate Python processes.",
        ],
    }
    _write_json(output / "RESULTS.json", final_results)
    _write_json(output / "TRACE.json", {
        "schema_version": "m301-trace-v1-recovered", "executed_at": final_results["executed_at"],
        "recovery_source": str(prior_root),
        "pair_results": [{
            "pair_id": item["pair"]["pair_id"], "arm": item["evaluation"]["arm"],
            "run_id": item["run_id"], "task_id": item["task_id"],
            "selected_memories": item.get("selected_memories", []),
            "model_traces": item.get("model_traces", []),
            "mcp_observations": item.get("mcp_observations", []),
            "attempt_counts": item.get("attempt_counts", {}),
            "outcome": item["evaluation"]["observed_outcome"],
            "outcome_allowed": item["evaluation"]["outcome_allowed"],
            "execution_error": item.get("execution_error"),
        } for item in trials],
    })
    final_failures = [
        {"pair_id": item["pair"]["pair_id"], "arm": item["evaluation"]["arm"],
         "observed_outcome": item["evaluation"]["observed_outcome"],
         "allowed_outcomes": item["evaluation"]["allowed_outcomes"],
         "execution_error": item.get("execution_error")}
        for item in trials
        if not item["evaluation"]["execution_ok"] or not item["evaluation"]["outcome_allowed"]
    ]
    _write_json(output / "FAILURES.json", {
        "schema_version": "m301-failures-v1", "first_attempt_failures": failures,
        "final_trial_failures": final_failures,
        "source_evaluation_failures": str(prior_root / "FAILURES.json"),
    })
    versions = {name: evaluation.version(name) for name in (
        "langchain", "langchain-openai", "langgraph", "langgraph-checkpoint-sqlite", "mcp", "pydantic",
    )}
    report = [
        "# M3-01 Memory ON/OFF paired evaluation recovery", "",
        f"- Frozen Gold: `{gold['gold_id']}`; 8 pairs / 16 planned and `{len(trials)}` included arms.",
        f"- Model: DeepSeek `{evaluation.os.environ.get(MODEL_NAME)}`; MCP stdio and loopback HTTP; isolated retry arms: `{len(rerun_logs)}`.",
        f"- Source of preserved original arms: `{prior_root}`. First failures remain unchanged there and are summarized in `FAILED_ATTEMPTS.json`.",
        f"- Runtime dependencies: `{json.dumps(versions, sort_keys=True)}`.",
        "- Every retry used a separate Worker process to create a fresh event loop. Other arms reused successful persisted real traces without repeating external calls.",
        "- Per-case tokens, model/MCP calls, tool order, outcomes and safety counters are in `RESULTS.json` and `TRACE.json`.",
        "- Utility remains `UTILITY_NOT_PROVEN`; this report does not claim statistical or causal generalization.",
        "- No REPAIR, DELIVER, Scope grant, or handoff submission is allowed or performed by these trials.",
        "",
    ]
    (output / "REPORT.md").write_text("\n".join(report), encoding="utf-8")
    return 1 if len(trials) != 16 else 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prior-dir", required=True)
    parser.add_argument("--evidence-dir", required=True)
    args = parser.parse_args()
    return recover(args.prior_dir, args.evidence_dir)


if __name__ == "__main__":
    raise SystemExit(main())
