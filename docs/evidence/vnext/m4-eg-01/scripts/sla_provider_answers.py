"""Four fresh real CHAT_READONLY answers for the frozen M4-EG-01 SLA cases."""
from __future__ import annotations

import asyncio
import json
import os
import sqlite3
import sys
import time
import traceback
from datetime import datetime, timedelta, timezone
from pathlib import Path

from opspilot.config import ROOT, load_local_environment
from opspilot.domain.database import connect
from opspilot.domain.d2 import canonical_json, digest_json
from opspilot.domain.s3 import get_s3_outcome, persist_s3_diagnosis
from opspilot.domain.task_control import (
    admit_task_message, finish_task_run, get_task_run, register_worker_owner, trusted_identity,
)
from opspilot.smokes.m4_02 import write_json
from opspilot.web.worker import _process_chat_run

sys.path.insert(0, str(ROOT / "tests"))
from test_m4_03_s3 import _evidence, _facts, _prepared_task  # noqa: E402

EVIDENCE = ROOT / "docs/evidence/vnext/m4-eg-01"
CASES = [
    {"case_id": "SLA-PROCESSED-EARLY", "receiver_status": "PROCESSED", "queue_age_seconds": 60,
     "expected_direction": "NO_FURTHER_ACTION", "expected_phrase": "PROCESSED"},
    {"case_id": "SLA-QUEUED-IN-WINDOW", "receiver_status": "QUEUED", "queue_age_seconds": 60,
     "expected_direction": "WAIT_FOR_RECEIVER_PROCESSING", "expected_phrase": "QUEUED"},
    {"case_id": "SLA-QUEUED-OVERDUE", "receiver_status": "QUEUED", "queue_age_seconds": 360,
     "expected_direction": "CONTACT_RECEIVER_OPERATOR", "expected_phrase": "CONTACT_RECEIVER_OPERATOR"},
    {"case_id": "SLA-202-UNKNOWN", "receiver_status": None, "queue_age_seconds": 60,
     "expected_direction": "EVIDENCE_INSUFFICIENT", "expected_phrase": "UNKNOWN"},
]


def _read_result(db: Path, task_id: str, chat_run_id: str, diagnosis_run_id: str) -> dict[str, object]:
    with sqlite3.connect(db) as connection:
        connection.row_factory = sqlite3.Row
        row = connection.execute(
            """SELECT r.status AS run_status,a.model_id,a.provider_response_id,a.input_tokens,
                      a.output_tokens,a.total_tokens,m.body AS answer,cm.evidence_refs_json,
                      cm.excluded_sources_json,cm.trusted_state_digest
               FROM task_runs r JOIN chat_run_answers ca ON ca.run_id=r.run_id
               JOIN chat_attempts a ON a.attempt_id=ca.attempt_id
               JOIN messages m ON m.message_id=ca.message_id
               JOIN chat_context_manifests cm ON cm.manifest_id=ca.manifest_id
               WHERE r.run_id=?""",
            (chat_run_id,),
        ).fetchone()
        diagnosis = connection.execute(
            "SELECT body_json FROM s3_diagnoses WHERE task_id=? AND run_id=?", (task_id, diagnosis_run_id),
        ).fetchone()
    if row is None:
        raise RuntimeError(f"{run_id} has no persisted real Provider answer and ContextManifest.")
    body = json.loads(str(diagnosis["body_json"])) if diagnosis else {}
    return {
        "task_id": task_id, "run_id": chat_run_id, "diagnosis_run_id": diagnosis_run_id,
        "run_status": row["run_status"],
        "model_id": row["model_id"], "provider_response_id": row["provider_response_id"],
        "input_tokens": row["input_tokens"], "output_tokens": row["output_tokens"],
        "total_tokens": row["total_tokens"], "answer": row["answer"],
        "expected_direction": body.get("gate", {}).get("handling_direction"),
        "gate_outcome": body.get("gate", {}).get("outcome"),
        "evidence_refs": json.loads(str(row["evidence_refs_json"])),
        "excluded_sources": json.loads(str(row["excluded_sources_json"])),
        "trusted_state_digest": row["trusted_state_digest"],
    }


async def main_async() -> int:
    load_local_environment()
    if not os.environ.get("OPSPILOT_MODEL_API_KEY", "").strip() or not os.environ.get("OPSPILOT_MODEL_NAME", "").strip():
        raise RuntimeError("M4-EG-01 SLA Provider answers require local credentials; values are never printed.")
    stamp = datetime.now(timezone.utc).strftime("sla-provider-%Y%m%dT%H%M%SZ")
    result_dir = EVIDENCE / "runs" / stamp
    result_dir.mkdir(parents=True, exist_ok=False)
    runtime = ROOT / ".runtime/m4-eg-01" / stamp
    runtime.mkdir(parents=True, exist_ok=False)
    result: dict[str, object] = {
        "release_id": stamp, "git_sha": os.environ.get("OPSPILOT_RELEASE_SHA"),
        "model_id": os.environ.get("OPSPILOT_MODEL_NAME"), "status": "FAIL",
        "provider_request_max_for_run": 4, "case_ids": [case["case_id"] for case in CASES],
        "evidence_setup": "isolated local Domain fixture plus persisted test Observation helper; live DeepSeek CHAT_READONLY Worker call",
        "cases": [],
    }
    request_count = 0
    try:
        for index, case in enumerate(CASES):
            case_dir = runtime / f"case-{index + 1}"
            case_dir.mkdir(parents=True, exist_ok=False)
            order_id = f"eg01-sla-{index + 1}"
            db, identity, task = _prepared_task(
                case_dir, "DELIVERED_PENDING", order_id,
                contract_version=2, queue_age_seconds=int(case["queue_age_seconds"]),
                processing_sla_seconds=300,
            )
            now = datetime.now(timezone.utc)
            accepted_at = (now - timedelta(seconds=int(case["queue_age_seconds"]))).isoformat().replace("+00:00", "Z")
            with connect(db) as connection:
                connection.execute(
                    "UPDATE s3_receivers SET accepted_at=?,status=? WHERE order_id=?",
                    (accepted_at, case["receiver_status"] or "QUEUED", order_id),
                )
                delivery = connection.execute(
                    "SELECT transport_response_json FROM s3_deliveries WHERE order_id=?", (order_id,),
                ).fetchone()
                response = json.loads(str(delivery["transport_response_json"]))
                response["accepted_at"] = accepted_at
                connection.execute(
                    "UPDATE s3_deliveries SET transport_response_json=?,response_digest=? WHERE order_id=?",
                    (canonical_json(response), digest_json(response), order_id),
                )
            order_fact, delivery_fact, receiver_fact = _facts(db, task)
            evidence_ids = [
                _evidence(db, task, "get_order_status", order_fact),
                _evidence(db, task, "get_callback_delivery", delivery_fact),
            ]
            if case["receiver_status"] is not None:
                evidence_ids.append(_evidence(db, task, "get_receiver_processing", receiver_fact))

            import opspilot.domain.s3 as s3_domain
            decision_now = datetime.now(timezone.utc) + timedelta(seconds=5)
            s3_domain._now = lambda: decision_now
            diagnosis = persist_s3_diagnosis(
                db, str(task["task_id"]), str(task["run_id"]), evidence_ids,
                stop_reason="EG01_NO_CURRENT_RECEIVER_STATE" if case["receiver_status"] is None else None,
            )
            finish_task_run(db, identity, str(task["run_id"]), "SUCCEEDED")
            accepted = admit_task_message(
                db, identity, session_id=str(task["session_id"]), task_id=str(task["task_id"]),
                input_kind="CHAT_READONLY",
                body="同一事件现在是否处理完成？请只根据当前 Task 的可信事实和接入协议解释；如状态未知，请明确说明。",
                idempotency_key=f"eg01-sla-provider-{case['case_id']}",
            )
            worker_id = f"eg01-sla-chat-{index + 1}"
            register_worker_owner(db, worker_id, os.getpid())
            run_record = get_task_run(db, identity, str(accepted["run_id"]))
            started = time.perf_counter()
            request_count += 1
            await _process_chat_run(db, worker_id, run_record)
            elapsed = round(time.perf_counter() - started, 3)
            answer = _read_result(db, str(task["task_id"]), str(accepted["run_id"]), str(task["run_id"]))
            answer.update({
                "case_id": case["case_id"], "expected_handling_direction": case["expected_direction"],
                "fixture_preparation": {"order_id": order_id, "receiver_status": case["receiver_status"],
                                         "queue_age_seconds": case["queue_age_seconds"], "sla_seconds": 300,
                                         "contract_version": 2, "source_task_run": diagnosis["run_id"]},
                "elapsed_seconds": elapsed,
                "semantic_review": {
                    "manual_review_required": True,
                    "expected_answer_contract": case["expected_direction"],
                    "automated_semantic_pass_claim": False,
                },
            })
            pre_chat_outcome = get_s3_outcome(db, str(task["task_id"])) or {}
            answer["pre_chat_business_outcome"] = {
                "outcome": pre_chat_outcome.get("outcome"), "handling_direction": pre_chat_outcome.get("handling_direction"),
                "receipt_id": pre_chat_outcome.get("receipt_id"),
                "business_writes": pre_chat_outcome.get("body", {}).get("business_writes"),
            }
            answer["actual_http_reads"] = [
                {"request_id": item.get("request_id"), "route": item.get("route"), "http_status": item.get("http_status")}
                for item in _facts_http_events(db)
            ]
            write_json(result_dir / f"{case['case_id']}.json", answer)
            result["cases"].append(answer)
        result["provider_requests"] = request_count
        result["total_tokens"] = sum(int(item.get("total_tokens") or 0) for item in result["cases"])
        result["status"] = "EXECUTION_COMPLETE" if request_count == len(CASES) and all(
            item["run_status"] == "SUCCEEDED" for item in result["cases"]
        ) else "PARTIAL"
        write_json(result_dir / "RESULTS.json", result)
        return 0 if result["status"] == "EXECUTION_COMPLETE" else 1
    except Exception as error:
        (result_dir / "FAILURE.txt").write_text("".join(traceback.format_exception(error)), encoding="utf-8")
        result.update({"failure": str(error), "provider_requests": request_count})
        write_json(result_dir / "RESULTS.json", result)
        return 1


def _facts_http_events(db: Path) -> list[dict[str, object]]:
    with connect(db) as connection:
        return [dict(row) for row in connection.execute(
            "SELECT request_id,route,http_status,body_digest,created_at FROM s3_http_observations ORDER BY rowid"
        )]


def main() -> int:
    return asyncio.run(main_async())


if __name__ == "__main__":
    raise SystemExit(main())
