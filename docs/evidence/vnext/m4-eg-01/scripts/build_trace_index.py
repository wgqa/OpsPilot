from __future__ import annotations

import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
RUNS = ROOT / "runs"
OUTPUT = ROOT / "TRACE.jsonl"


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def traced(row: dict[str, Any], source: str) -> dict[str, Any]:
    return {**row, "evidence_source": source.replace("\\", "/")}


def main() -> None:
    records: list[dict[str, Any]] = []

    memory_trace = RUNS / "memory-paired-20261025T100556Z/TRACE.jsonl"
    for line in memory_trace.read_text(encoding="utf-8").splitlines():
        if line.strip():
            records.append(traced(json.loads(line), "runs/memory-paired-20261025T100556Z/TRACE.jsonl"))

    sla_path = RUNS / "sla-provider-20261025T101512Z/RESULTS.json"
    sla = read_json(sla_path)
    for case in sla["cases"]:
        records.append(
            {
                "kind": "provider_chat_case",
                "case_id": case["case_id"],
                "task_id": case["task_id"],
                "run_id": case["run_id"],
                "diagnosis_run_id": case["diagnosis_run_id"],
                "model_id": case["model_id"],
                "provider_response_id": case["provider_response_id"],
                "usage": {
                    "input_tokens": case["input_tokens"],
                    "output_tokens": case["output_tokens"],
                    "total_tokens": case["total_tokens"],
                },
                "expected_direction": case["expected_direction"],
                "gate_outcome": case["gate_outcome"],
                "trusted_state_digest": case["trusted_state_digest"],
                "evidence_refs": [
                    {key: evidence.get(key) for key in ("evidence_id", "digest", "fact_type")}
                    for evidence in case["evidence_refs"]
                ],
                "actual_http_reads": case["actual_http_reads"],
                "semantic_review": case["semantic_review"],
                "evidence_source": "runs/sla-provider-20261025T101512Z/RESULTS.json",
            }
        )

    web_path = RUNS / "web-memory-green-02/WEB-JOURNEY-RECONCILIATION.json"
    web = read_json(web_path)
    for observation in web["source"]["http_observations"]:
        records.append(traced({"kind": "http_observation", **observation}, "runs/web-memory-green-02/WEB-JOURNEY-RECONCILIATION.json#/source/http_observations"))
    for observation in web["source"]["mcp_observations"]:
        records.append(traced({"kind": "mcp_observation", **observation}, "runs/web-memory-green-02/WEB-JOURNEY-RECONCILIATION.json#/source/mcp_observations"))
    for call in web["target"]["provider_contexts"]:
        records.append(traced({"kind": "provider_call", "task_id": web["target"]["task"]["task_id"], **call}, "runs/web-memory-green-02/WEB-JOURNEY-RECONCILIATION.json#/target/provider_contexts"))
    for observation in web["target"]["mcp_observations"]:
        records.append(traced({"kind": "mcp_observation", **observation}, "runs/web-memory-green-02/WEB-JOURNEY-RECONCILIATION.json#/target/mcp_observations"))

    records.append(
        traced(
            {
                "kind": "browser_journey",
                "source_task_id": web["source"]["task_id"],
                "target_task_id": web["target"]["task"]["task_id"],
                "candidate_http_status": web["browser_actions"]["candidate_http_status"],
                "approval_http_status": web["browser_actions"]["approval_http_status"],
                "target_task_acceptance_http_status": web["browser_actions"]["target_task_acceptance_http_status"],
                "target_run_id": web["target"]["run"]["run_id"],
                "target_run_status": web["target"]["run"]["status"],
                "selected_memory_call_ids": web["target"]["selected_task_a_memory_calls"],
                "business_write_counts": web["target"]["business_write_counts"],
                "runner_end_state": web["browser_actions"]["runner_end_state"],
                "runner_failure_is_postcondition_only": web["browser_actions"]["runner_failure_is_postcondition_only"],
                "screenshots": [
                    "runs/web-memory-green-02/screenshots/02-task-a-candidate-created.png",
                    "runs/web-memory-green-02/screenshots/04-approver-memory-active.png",
                    "runs/web-memory-green-02/screenshots/06-task-b-persisted-result.png",
                ],
            },
            "runs/web-memory-green-02/WEB-JOURNEY-RECONCILIATION.json#/browser_actions",
        )
    )

    revisit_path = RUNS / "web-memory-green-02/screenshots/WEB-REVISIT.json"
    revisit = read_json(revisit_path)
    records.append(
        traced(
            {
                "kind": "browser_readonly_revisit",
                "target_task_id": revisit["target_task_id"],
                "target_run_id": revisit["target_run_id"],
                "run_status": revisit["run_status"],
                "currentness_at_revisit": revisit["currentness_at_revisit"],
                "visible_diagnosis": revisit["visible_diagnosis"],
                "model_called_during_revisit": revisit["model_called_during_revisit"],
            },
            "runs/web-memory-green-02/screenshots/WEB-REVISIT.json",
        )
    )

    OUTPUT.write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in records),
        encoding="utf-8",
        newline="\n",
    )
    print(f"wrote {len(records)} evidence-index rows to {OUTPUT}")


if __name__ == "__main__":
    main()
