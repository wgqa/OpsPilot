from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sqlite3
import tempfile
import time
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi.testclient import TestClient

from opspilot.config import load_local_environment
from opspilot.web.app import create_app


STRATEGIES = ("RECENT_WINDOW", "ROLLING_SUMMARY", "HYBRID")
PROMPT = (
    "请基于当前可信 Task 元数据和可用来源，复述最初调查目标、正式关键更正、"
    "安全限制与未完成事项；明确区分用户线索、历史摘要和当前 Domain 事实。"
)


def _backup_sqlite(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    source_db = sqlite3.connect(source)
    target_db = sqlite3.connect(destination)
    try:
        source_db.backup(target_db)
    finally:
        target_db.close()
        source_db.close()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _json(value: str | None) -> Any:
    return json.loads(value) if value else None


def _run_variant(
    *,
    source_db: Path,
    source_checkpoint: Path,
    session_id: str,
    task_id: str,
    strategy: str,
    temp_root: Path,
) -> dict[str, Any]:
    db_path = temp_root / f"{strategy.lower()}.sqlite3"
    checkpoint_path = temp_root / f"{strategy.lower()}-checkpoints.sqlite3"
    _backup_sqlite(source_db, db_path)
    _backup_sqlite(source_checkpoint, checkpoint_path)
    snapshot_digest = _sha256(db_path)
    os.environ["OPSPILOT_CONTEXT_STRATEGY"] = strategy
    os.environ["OPSPILOT_CONTEXT_INPUT_BUDGET_TOKENS"] = "1400"

    password = os.environ.get("OPSPILOT_WEB_SUPPORT_PASSWORD", "")
    if not password:
        raise RuntimeError("OPSPILOT_WEB_SUPPORT_PASSWORD is not configured in the local environment.")
    app = create_app(
        db_path=db_path,
        checkpoint_db_path=checkpoint_path,
        credentials={"support-a": password},
        expected_origin="http://testserver",
    )
    origin = "http://testserver"
    with TestClient(app) as client:
        login = client.post(
            "/api/auth/login",
            headers={"Origin": origin},
            json={"actor_id": "support-a", "password": password},
        )
        login.raise_for_status()
        csrf = str(login.json()["csrf_token"])
        admitted = client.post(
            f"/api/sessions/{session_id}/messages",
            headers={
                "Origin": origin,
                "X-CSRF-Token": csrf,
                "Idempotency-Key": f"m302-strategy-{strategy.lower()}-{uuid4()}",
            },
            json={"body": PROMPT, "task_id": task_id, "input_kind": "CHAT_READONLY"},
        )
        admitted.raise_for_status()
        run_id = str(admitted.json()["run_id"])
        run_started = time.monotonic()
        status: dict[str, Any] = {}
        deadline = time.monotonic() + 240
        while time.monotonic() < deadline:
            response = client.get(f"/api/runs/{run_id}")
            response.raise_for_status()
            status = response.json()
            if status.get("status") in {"SUCCEEDED", "FAILED", "ABORTED", "CANCELLED"}:
                break
            time.sleep(0.25)
        else:
            status = {**status, "status": "TIMED_OUT"}

    with sqlite3.connect(db_path) as connection:
        connection.row_factory = sqlite3.Row
        attempts = [
            dict(row)
            for row in connection.execute(
                """SELECT attempt_id, attempt_no, model_id, status, provider_response_id,
                          input_tokens, output_tokens, total_tokens, error_class
                   FROM chat_attempts WHERE run_id = ? ORDER BY attempt_no""",
                (run_id,),
            )
        ]
        compression = [
            dict(row)
            for row in connection.execute(
                """SELECT attempt_id, attempt_no, model_id, status, provider_response_id,
                          estimated_input_tokens, input_tokens, output_tokens, total_tokens,
                          summary_id, error_class, source_dependencies_json
                   FROM context_compression_attempts WHERE run_id = ? ORDER BY attempt_no""",
                (run_id,),
            )
        ]
        for item in compression:
            dependencies = _json(item.pop("source_dependencies_json", None)) or {}
            dependency_items = dependencies.get("dependencies", [])
            item["dependency_kinds"] = sorted({
                str(dep.get("kind")) for dep in dependency_items if isinstance(dep, dict)
            })
            item["source_message_count"] = len(dependencies.get("allowed_message_ids", []))
            item["covered_sequence_range"] = [
                dependencies.get("covered_from_seq"), dependencies.get("covered_to_seq")
            ]
        manifest_row = connection.execute(
            """SELECT selected_message_ids_json, evidence_refs_json, memory_refs_json,
                      excluded_sources_json, truncation_json, prompt_digest
               FROM chat_context_manifests WHERE run_id = ? ORDER BY created_at DESC LIMIT 1""",
            (run_id,),
        ).fetchone()
        manifest: dict[str, Any] | None = None
        if manifest_row is not None:
            truncation = _json(manifest_row["truncation_json"]) or {}
            manifest = {
                "prompt_digest": manifest_row["prompt_digest"],
                "selected_message_ids": _json(manifest_row["selected_message_ids_json"]),
                "evidence_refs": _json(manifest_row["evidence_refs_json"]),
                "memory_refs": _json(manifest_row["memory_refs_json"]),
                "excluded_sources": _json(manifest_row["excluded_sources_json"]),
                "input_budget": truncation.get("context_budget"),
                "summary_refs": truncation.get("summary_refs"),
                "context_blocks": truncation.get("context_blocks"),
            }
        run_row = connection.execute(
            """SELECT status, blocked_reason, consumed_message_seq, started_at, ended_at
               FROM task_runs WHERE run_id = ?""",
            (run_id,),
        ).fetchone()
        answer = connection.execute(
            """SELECT m.body FROM chat_run_answers a
               JOIN messages m ON m.message_id = a.message_id
               WHERE a.run_id = ?""",
            (run_id,),
        ).fetchone()

    return {
        "strategy": strategy,
        "source_snapshot_sha256": snapshot_digest,
        "session_id": session_id,
        "task_id": task_id,
        "run_id": run_id,
        "input_sha256": hashlib.sha256(PROMPT.encode("utf-8")).hexdigest(),
        "status": str(run_row["status"]) if run_row is not None else status.get("status"),
        "blocked_reason": str(run_row["blocked_reason"]) if run_row is not None and run_row["blocked_reason"] else None,
        "consumed_message_seq": int(run_row["consumed_message_seq"]) if run_row is not None else None,
        "run_latency_ms": round((time.monotonic() - run_started) * 1000),
        "model_attempts": attempts,
        "compression_attempts": compression,
        "manifest": manifest,
        "estimated_input_tokens": (
            manifest.get("input_budget", {}).get("estimated_input_tokens")
            if manifest is not None else sum(int(item.get("estimated_input_tokens") or 0) for item in compression)
        ),
        "provider_input_tokens": sum(int(item.get("input_tokens") or 0) for item in [*attempts, *compression]),
        "provider_output_tokens": sum(int(item.get("output_tokens") or 0) for item in [*attempts, *compression]),
        "provider_total_tokens": sum(int(item.get("total_tokens") or 0) for item in [*attempts, *compression]),
        "answer_sha256": hashlib.sha256(str(answer["body"]).encode("utf-8")).hexdigest() if answer else None,
        "answer_excerpt": str(answer["body"])[:360] if answer else None,
    }


def run(source_db: Path, session_id: str, task_id: str, output: Path) -> int:
    load_local_environment()
    from opspilot.config import MODEL_API_KEY, MODEL_NAME

    if not os.environ.get("OPSPILOT_WEB_SUPPORT_PASSWORD", ""):
        raise RuntimeError("Set OPSPILOT_WEB_SUPPORT_PASSWORD to the local demo support password.")
    if not os.environ.get(MODEL_API_KEY, ""):
        raise RuntimeError("The local model API key is not configured.")
    source_db = source_db.resolve()
    source_checkpoint = Path(
        os.environ.get("OPSPILOT_CHECKPOINT_DB_PATH", ".runtime/checkpoints.sqlite3")
    )
    if not source_checkpoint.is_absolute():
        source_checkpoint = Path.cwd() / source_checkpoint
    source_checkpoint = source_checkpoint.resolve()
    if not source_db.is_file() or not source_checkpoint.is_file():
        raise FileNotFoundError("The source Domain and checkpoint databases must both exist.")
    output.mkdir(parents=True, exist_ok=True)
    report = {
        "schema_version": "m302-strategy-comparison-v1",
        "model_id": os.environ.get(MODEL_NAME),
        "input_budget_tokens": 1400,
        "output_reserved_tokens": 512,
        "safety_margin_tokens": 1024,
        "source_database_sha256": _sha256(source_db),
        "source_checkpoint_sha256": _sha256(source_checkpoint),
        "same_source_material": True,
        "input_sha256": hashlib.sha256(PROMPT.encode("utf-8")).hexdigest(),
        "variants": [],
    }
    trace_path = output / "TRACE.json"
    failures_path = output / "FAILURES.jsonl"
    failures_path.write_text("", encoding="utf-8")
    temp_root = Path(tempfile.mkdtemp(prefix="m302-strategy-", dir=Path.cwd() / ".runtime"))
    report["scratch_databases"] = str(temp_root)
    trace_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        for strategy in STRATEGIES:
            try:
                variant = _run_variant(
                    source_db=source_db,
                    source_checkpoint=source_checkpoint,
                    session_id=session_id,
                    task_id=task_id,
                    strategy=strategy,
                    temp_root=temp_root,
                )
                report["variants"].append(variant)
                trace_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
                if variant["status"] != "SUCCEEDED":
                    with failures_path.open("a", encoding="utf-8") as handle:
                        handle.write(json.dumps(variant, ensure_ascii=False) + "\n")
            except Exception as error:
                failure = {
                    "strategy": strategy,
                    "error_class": type(error).__name__,
                    "error": str(error)[:500],
                }
                report["variants"].append(failure)
                with failures_path.open("a", encoding="utf-8") as handle:
                    handle.write(json.dumps(failure, ensure_ascii=False) + "\n")
                trace_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    except BaseException:
        trace_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        raise
    return 0 if all(item.get("status") == "SUCCEEDED" for item in report["variants"]) else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the frozen M3-02 context strategy comparison with the real Provider.")
    parser.add_argument("--source-db", type=Path, required=True)
    parser.add_argument("--session-id", required=True)
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    return run(args.source_db, args.session_id, args.task_id, args.output)


if __name__ == "__main__":
    raise SystemExit(main())
