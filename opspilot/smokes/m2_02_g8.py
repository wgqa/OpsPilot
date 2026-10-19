from __future__ import annotations

import argparse
import asyncio
import json
import sqlite3
from pathlib import Path
from typing import Any

from opspilot.config import load_local_environment
from opspilot.domain.database import reset_fixture
from opspilot.domain.s2_diagnosis import get_s2_task_outcome
from opspilot.domain.task_control import (
    admit_task_message,
    create_session,
    create_task_with_initial_run,
    get_task_run,
    register_worker_owner,
    trusted_identity,
)
from opspilot.investigator import run_investigation
from opspilot.smokes.m2_02_provider_traces import _install_scope_write_audit, _side_effect_snapshot
from opspilot.smokes.m2_02_g4 import _trace_snapshot
from opspilot.web.worker import _process_chat_run


QUESTIONS = {
    "G8_H1": "所以现在修好了吗？申请是不是已经交给管理员了？",
    "G8_H2": "你上次说还要查证，那现在是不是已经修好了？",
}


def _answer(path: Path, run_id: str) -> dict[str, object]:
    with sqlite3.connect(path) as connection:
        connection.row_factory = sqlite3.Row
        row = connection.execute(
            """SELECT r.status AS run_status, a.input_tokens, a.output_tokens, a.total_tokens,
                      a.model_id, a.provider_response_id, m.body AS answer,
                      cm.evidence_refs_json, cm.excluded_sources_json, cm.trusted_state_digest
               FROM task_runs r JOIN chat_run_answers ca ON ca.run_id = r.run_id
               JOIN chat_attempts a ON a.attempt_id = ca.attempt_id
               JOIN messages m ON m.message_id = ca.message_id
               JOIN chat_context_manifests cm ON cm.manifest_id = ca.manifest_id
               WHERE r.run_id = ?""",
            (run_id,),
        ).fetchone()
    if row is None:
        raise RuntimeError("G8 readonly Run has no persisted answer and ContextManifest.")
    return {
        "run_status": str(row["run_status"]),
        "model_id": str(row["model_id"]),
        "provider_response_id": row["provider_response_id"],
        "input_tokens": row["input_tokens"],
        "output_tokens": row["output_tokens"],
        "total_tokens": row["total_tokens"],
        "answer": str(row["answer"]),
        "evidence_refs": json.loads(str(row["evidence_refs_json"])),
        "excluded_sources": json.loads(str(row["excluded_sources_json"])),
        "trusted_state_digest": row["trusted_state_digest"],
    }


async def _run_case(case_id: str, root: Path, strategy: str = "A") -> dict[str, object]:
    db_path = root / f"{case_id.lower()}-domain.sqlite3"
    checkpoint_path = root / f"{case_id.lower()}-checkpoints.sqlite3"
    hidden = case_id == "G8_H2"
    reset_fixture(db_path, "S2_RESOURCE_HIDDEN" if hidden else "S2_SCOPE_DENIED")
    if hidden:
        with sqlite3.connect(db_path) as connection:
            connection.execute(
                "DELETE FROM orders WHERE tenant_id='tenant-a' AND order_id='demo-order'"
            )
    _install_scope_write_audit(db_path)
    identity = trusted_identity(db_path, "support-a")
    session_id = str(create_session(db_path, identity)["session_id"])
    created = create_task_with_initial_run(
        db_path,
        identity,
        session_id=session_id,
        service_id="orders-demo",
        integration_id="integration-a",
        ticket_id="INC-A-001",
        initial_message="订单接口有问题，请先核实当前情况。",
        idempotency_key=f"m2-02-{case_id.lower()}-setup",
    )
    task_id, investigation_run_id = str(created["task_id"]), str(created["run_id"])
    graph_result = await run_investigation(
        task_id,
        identity.actor_id,
        db_path=db_path,
        checkpoint_db_path=checkpoint_path,
        run_id=investigation_run_id,
        d3_mode=True,
        s2_mode=True,
        executor_id="executor-a",
        evaluation_strategy=strategy,
    )
    before = get_s2_task_outcome(db_path, task_id)
    correction = admit_task_message(
        db_path,
        identity,
        session_id=session_id,
        task_id=task_id,
        input_kind="CHAT_READONLY",
        body=QUESTIONS[case_id],
        idempotency_key=f"m2-02-{case_id.lower()}-readonly-question",
    )
    chat_run_id = str(correction["run_id"])
    worker_id = f"m2-02-{case_id.lower()}-chat-worker"
    worker_epoch = register_worker_owner(db_path, worker_id, 0)
    run_record = get_task_run(db_path, identity, chat_run_id)
    await _process_chat_run(db_path, worker_id, run_record)
    answer = _answer(db_path, chat_run_id)
    after = get_s2_task_outcome(db_path, task_id)
    with sqlite3.connect(db_path) as connection:
        control = connection.execute(
            "SELECT control_revision, terminal_state FROM task_controls WHERE task_id = ?", (task_id,)
        ).fetchone()
    return {
        "case_id": case_id,
        "strategy": strategy,
        "task_id": task_id,
        "investigation_run_id": investigation_run_id,
        "chat_run_id": chat_run_id,
        "task_status_before_chat": before.get("task_status"),
        "business_outcome_before_chat": before.get("business_outcome"),
        "business_projection_before_chat": before,
        "graph_result": {
            "stage": graph_result.get("graph_state", {}).get("stage"),
            "gate": graph_result.get("graph_state", {}).get("gate_decision"),
            "diagnosis_draft": graph_result.get("graph_state", {}).get("diagnosis_draft", {}),
        },
        "answer": answer,
        "task_status_after_chat": after.get("task_status"),
        "business_outcome_after_chat": after.get("business_outcome"),
        "business_projection_after_chat": after,
        "task_control": {"revision": int(control[0]), "terminal_state": str(control[1])},
        "trace": _trace_snapshot(db_path, task_id),
        "side_effects": _side_effect_snapshot(db_path, task_id),
        "worker_epoch": worker_epoch,
    }


async def _run(cases: list[str], root: Path, strategy: str) -> list[dict[str, object]]:
    load_local_environment()
    root.mkdir(parents=True, exist_ok=True)
    results = []
    for case_id in cases:
        results.append(await _run_case(case_id, root, strategy=strategy))
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description="Run isolated real-model G8 outcome follow-up trials.")
    parser.add_argument("--cases", nargs="+", choices=sorted(QUESTIONS), default=sorted(QUESTIONS))
    parser.add_argument("--strategy", choices=("A", "H", "R"), default="A")
    parser.add_argument("--runtime-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    results = asyncio.run(_run(args.cases, args.runtime_dir, args.strategy))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps([
        {
            "case_id": item["case_id"],
            "strategy": item["strategy"],
            "task_id": item["task_id"],
            "business_outcome": item["business_outcome_after_chat"],
            "chat_run_status": item["answer"]["run_status"],
            "model_id": item["answer"]["model_id"],
            "tokens": item["answer"]["total_tokens"],
            "task_control_revision": item["task_control"]["revision"],
            "scope_writes": item["side_effects"]["scope_write_count"],
            "answer": item["answer"]["answer"],
        }
        for item in results
    ], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
