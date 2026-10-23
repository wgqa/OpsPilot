"""Bounded real-provider Context Summary source invalidation experiment.

Uses a SQLite backup of the frozen M3 continuation fixture. A trigger in that
isolated copy caps reserved answer/compression attempts at four before any
external Provider request can be made.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import sqlite3
import subprocess
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from opspilot.config import ROOT, load_local_environment
from opspilot.domain.database import connect
from opspilot.domain.task_control import admit_task_message, register_worker_owner, trusted_identity

EVIDENCE = ROOT / "docs/evidence/vnext/m4-03"
SOURCE_DB = ROOT / ".runtime/m302-continuation-01/domain.sqlite3"
SOURCE_CHECKPOINT = ROOT / ".runtime/m302-continuation-01/checkpoints.sqlite3"
PROVIDER_REQUEST_CAP = 4


def _write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


def _backup(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(source) as source_connection, sqlite3.connect(target) as target_connection:
        source_connection.backup(target_connection)


def _install_provider_cap(path: Path) -> None:
    with connect(path) as connection:
        connection.executescript(
            """
            CREATE TABLE m403_summary_budget_runs (run_id TEXT PRIMARY KEY);
            CREATE TRIGGER m403_summary_cap_chat_attempt
            BEFORE INSERT ON chat_attempts
            WHEN EXISTS (SELECT 1 FROM m403_summary_budget_runs WHERE run_id = NEW.run_id)
            BEGIN
              SELECT CASE WHEN
                (SELECT COUNT(*) FROM chat_attempts WHERE run_id IN (SELECT run_id FROM m403_summary_budget_runs)) +
                (SELECT COUNT(*) FROM context_compression_attempts WHERE run_id IN (SELECT run_id FROM m403_summary_budget_runs))
                >= 4
              THEN RAISE(ABORT, 'M403_SUMMARY_PROVIDER_REQUEST_CAP') END;
            END;
            CREATE TRIGGER m403_summary_cap_compression_attempt
            BEFORE INSERT ON context_compression_attempts
            WHEN EXISTS (SELECT 1 FROM m403_summary_budget_runs WHERE run_id = NEW.run_id)
            BEGIN
              SELECT CASE WHEN
                (SELECT COUNT(*) FROM chat_attempts WHERE run_id IN (SELECT run_id FROM m403_summary_budget_runs)) +
                (SELECT COUNT(*) FROM context_compression_attempts WHERE run_id IN (SELECT run_id FROM m403_summary_budget_runs))
                >= 4
              THEN RAISE(ABORT, 'M403_SUMMARY_PROVIDER_REQUEST_CAP') END;
            END;
            """
        )


def _run_worker(db: Path, run_id: str, label: str, output: Path) -> dict[str, Any]:
    completed = subprocess.run(
        [sys.executable, "-X", "utf8", "-m", "opspilot.smokes.m4_03_summary",
         "--worker", str(db), run_id, label],
        cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=600,
    )
    output.write_text(
        "=== STDOUT ===\n" + completed.stdout + "\n=== STDERR ===\n" + completed.stderr,
        encoding="utf-8",
    )
    status: str | None = None
    answer: str | None = None
    with connect(db) as connection:
        row = connection.execute("SELECT status FROM task_runs WHERE run_id = ?", (run_id,)).fetchone()
        status = str(row["status"]) if row else None
        answer_row = connection.execute(
            """SELECT m.message_id,m.body FROM chat_run_answers a
               JOIN messages m ON m.message_id=a.message_id WHERE a.run_id=?""", (run_id,),
        ).fetchone()
        if answer_row is not None:
            answer = str(answer_row["body"])
    return {"run_id": run_id, "worker_return_code": completed.returncode, "run_status": status,
            "answer": answer, "worker_log": str(output.relative_to(ROOT)),
            "worker_pid": _worker_pid(output) if completed.returncode == 0 and '\"worker_pid\"' in completed.stdout else None}


def _worker(db: Path, run_id: str, label: str) -> int:
    load_local_environment()
    worker_id = f"m403-summary-{label}-{os.getpid()}"
    register_worker_owner(db, worker_id, os.getpid())
    with connect(db) as connection:
        row = connection.execute(
            "SELECT run_id,task_id,session_id,kind FROM task_runs WHERE run_id=?", (run_id,),
        ).fetchone()
    if row is None:
        raise RuntimeError("Worker run does not exist in isolated Domain.")
    from opspilot.web.worker import _process_chat_run

    asyncio.run(_process_chat_run(db, worker_id, dict(row)))
    with connect(db) as connection:
        status = connection.execute("SELECT status FROM task_runs WHERE run_id=?", (run_id,)).fetchone()
    print(json.dumps({"run_id": run_id, "worker_pid": os.getpid(),
                      "status": str(status["status"]) if status else None}, ensure_ascii=False))
    return 0


def _provider_attempt_count(db: Path, run_ids: list[str]) -> int:
    if not run_ids:
        return 0
    marks = ",".join("?" for _ in run_ids)
    with connect(db) as connection:
        return int(connection.execute(
            f"SELECT (SELECT COUNT(*) FROM chat_attempts WHERE run_id IN ({marks})) + "
            f"(SELECT COUNT(*) FROM context_compression_attempts WHERE run_id IN ({marks}))",
            (*run_ids, *run_ids),
        ).fetchone()[0])


def _manifest(db: Path, actor_id: str, run_id: str) -> dict[str, Any]:
    from opspilot.domain.chat import get_chat_manifest

    return get_chat_manifest(db, trusted_identity(db, actor_id), run_id)


def _business_snapshot(db: Path) -> dict[str, list[dict[str, Any]]]:
    names = (
        "integrations", "principals", "auth_policies", "route_scope_policies",
        "principal_scope_grants", "orders", "s3_orders", "s3_deliveries",
        "s3_receivers", "tickets", "d3_ticket_resolution_entries",
    )
    with connect(db) as connection:
        existing = {
            str(row[0]) for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        return {
            name: [dict(row) for row in connection.execute(f"SELECT * FROM {name} ORDER BY rowid")]
            for name in names if name in existing
        }


def _worker_pid(path: Path) -> int:
    raw = path.read_text(encoding="utf-8", errors="replace")
    marker = "=== STDOUT ===\n"
    body = raw.split(marker, 1)[1].split("\n=== STDERR ===", 1)[0]
    lines = [line for line in body.splitlines() if line.strip().startswith("{") and '"worker_pid"' in line]
    if not lines:
        raise RuntimeError(f"Worker PID record missing from {path}")
    return int(json.loads(lines[-1])["worker_pid"])


def _budget_runs(db: Path) -> list[str]:
    with connect(db) as connection:
        return [str(row[0]) for row in connection.execute("SELECT run_id FROM m403_summary_budget_runs")]


def _main() -> int:
    load_local_environment()
    if not os.environ.get("OPSPILOT_MODEL_API_KEY", "").strip() or not os.environ.get("OPSPILOT_MODEL_NAME", "").strip():
        raise RuntimeError("M4-03 Summary experiment requires configured Provider credentials; values are never printed.")
    if not SOURCE_DB.exists() or not SOURCE_CHECKPOINT.exists():
        raise RuntimeError("Frozen M3 continuation Domain/Checkpoint source is unavailable.")

    stamp = datetime.now(timezone.utc).strftime("summary-%Y%m%dT%H%M%SZ")
    evidence = EVIDENCE / "runs" / stamp
    runtime = ROOT / ".runtime/m4-03" / stamp
    evidence.mkdir(parents=True, exist_ok=False)
    runtime.mkdir(parents=True, exist_ok=False)
    db, checkpoint = runtime / "domain.sqlite3", runtime / "checkpoints.sqlite3"
    result: dict[str, Any] = {
        "status": "PARTIAL", "release": stamp, "provider": os.environ.get("OPSPILOT_MODEL_NAME"),
        "provider_request_cap": PROVIDER_REQUEST_CAP,
        "scope": "one isolated copied session; two real Provider CHAT_READONLY turns in separate worker processes",
        "evidence_dir": str(evidence.relative_to(ROOT)),
    }
    try:
        _backup(SOURCE_DB, db)
        _backup(SOURCE_CHECKPOINT, checkpoint)
        _install_provider_cap(db)
        with connect(db) as connection:
            current = connection.execute(
                "SELECT * FROM context_summaries WHERE state='CURRENT' ORDER BY summary_version DESC LIMIT 1"
            ).fetchone()
            if current is None:
                raise RuntimeError("Isolated session has no CURRENT persisted Summary.")
            summary = dict(current)
            dependency = connection.execute(
                """SELECT dependency_kind,dependency_ref,dependency_version,dependency_digest
                   FROM context_summary_dependencies WHERE summary_id=? AND dependency_kind='MESSAGE'
                   ORDER BY source_order DESC LIMIT 1""", (summary["summary_id"],),
            ).fetchone()
            if dependency is None:
                raise RuntimeError("CURRENT Summary has no versioned message dependency for the drift experiment.")
            source_message = connection.execute(
                "SELECT message_id,body_digest,sequence FROM messages WHERE message_id=?",
                (dependency["dependency_ref"],),
            ).fetchone()
            if source_message is None or str(source_message["body_digest"]) != str(dependency["dependency_digest"]):
                raise RuntimeError("Baseline Summary message dependency is not current before the experiment.")
            session = connection.execute(
                "SELECT session_id,owner_id,tenant_id FROM sessions WHERE session_id=?", (summary["session_id"],),
            ).fetchone()
            task = connection.execute(
                "SELECT task_id,service_id,status FROM task_bindings WHERE task_id=?", (summary["task_id"],),
            ).fetchone()
        if session is None or task is None:
            raise RuntimeError("Copied Summary does not resolve to its source Session and Task.")
        actor_id, session_id, task_id = str(session["owner_id"]), str(session["session_id"]), str(task["task_id"])
        business_before = _business_snapshot(db)
        _write(evidence / "PREPARATION.json", {
            "source_db": str(SOURCE_DB.relative_to(ROOT)), "isolated_db": str(db.relative_to(ROOT)),
            "sqlite_backup_api_used": True, "source_database_modified": False,
            "summary_id": summary["summary_id"], "summary_version": summary["summary_version"],
            "summary_state_before": summary["state"],
            "summary_covered_sequence": [summary["covered_from_seq"], summary["covered_to_seq"]],
            "summary_dependency": {key: dependency[key] for key in dependency.keys()},
            "source_message_sequence": source_message["sequence"], "session_id": session_id,
            "task_id": task_id, "task_status_before": task["status"], "task_service": task["service_id"],
            "provider_cap_enforced_by_sqlite_before_attempt_insert": PROVIDER_REQUEST_CAP,
            "business_snapshot_digest_before": hashlib.sha256(
                json.dumps(business_before, sort_keys=True, default=str).encode()
            ).hexdigest(),
        })

        first = admit_task_message(
            db, trusted_identity(db, actor_id), session_id=session_id, task_id=task_id,
            input_kind="CHAT_READONLY",
            body="请依据此前对话摘要，说明我们更正后的调查目标和仍然有效的安全边界；区分历史上下文与当前可信业务事实。",
            idempotency_key=f"{stamp}-turn-1",
        )
        first_run = str(first["run_id"])
        with connect(db) as connection:
            connection.execute("INSERT INTO m403_summary_budget_runs(run_id) VALUES (?)", (first_run,))
        first_worker = _run_worker(db, first_run, "turn-1", evidence / "worker-turn-1.log")
        if first_worker["worker_return_code"] != 0 or first_worker["run_status"] != "SUCCEEDED" or first_worker["answer"] is None:
            raise RuntimeError("The first Summary-context answer failed; see worker-turn-1.log.")
        first_manifest = _manifest(db, actor_id, first_run)
        first_summary_refs = first_manifest.get("summary_refs", [])
        if not any(str(ref.get("summary_id")) == str(summary["summary_id"])
                   for ref in first_summary_refs if isinstance(ref, dict)):
            raise RuntimeError("First actual Provider context did not include the current persisted Summary.")
        with connect(db) as connection:
            first_answer = connection.execute(
                "SELECT message_id FROM chat_run_answers WHERE run_id=?", (first_run,),
            ).fetchone()
            answer_summary_source = connection.execute(
                """SELECT summary_id,summary_version,summary_digest FROM chat_message_summary_sources
                   WHERE message_id=? AND summary_id=?""",
                (first_answer["message_id"], summary["summary_id"]),
            ).fetchone() if first_answer else None
            old_digest = str(source_message["body_digest"])
            drift_digest = hashlib.sha256(("m403-summary-source-version-drift:" + old_digest).encode()).hexdigest()
            connection.execute("UPDATE messages SET body_digest=? WHERE message_id=?",
                               (drift_digest, source_message["message_id"]))
        if answer_summary_source is None:
            raise RuntimeError("First answer was not persistently linked to the Summary it received.")
        _write(evidence / "TURN-1-SUMMARY-USED.json", {
            "run_id": first_run, "worker_pid": first_worker["worker_pid"],
            "provider_summary_refs": first_summary_refs, "chat_attempts": first_manifest["attempts"],
            "compression_attempts": first_manifest["compression_attempts"],
            "assistant_answer_summary_source": dict(answer_summary_source),
            "answer_excerpt": first_worker["answer"][:1600],
            "summary_dependency_current_after_first_turn": True,
        })

        second = admit_task_message(
            db, trusted_identity(db, actor_id), session_id=session_id, task_id=task_id,
            input_kind="CHAT_READONLY",
            body="请继续回答上一轮的问题，并核实此前助手回答是否仍有有效来源；若历史依据失效，请只依据当前仍有效的信息说明。",
            idempotency_key=f"{stamp}-turn-2",
        )
        second_run = str(second["run_id"])
        with connect(db) as connection:
            connection.execute("INSERT INTO m403_summary_budget_runs(run_id) VALUES (?)", (second_run,))
        drift = {
            "kind": "ISOLATED_SOURCE_VERSION_DRIFT_FAULT_INJECTION",
            "target_dependency_kind": "MESSAGE", "source_message_id": source_message["message_id"],
            "sequence": int(source_message["sequence"]), "old_digest": old_digest, "new_digest": drift_digest,
            "message_body_changed": False,
            "purpose": "Simulate a source-version change in an isolated backup so dependency revalidation must invalidate the Summary and answers that cite it.",
            "business_database_changed": False,
        }
        _write(evidence / "SOURCE-VERSION-DRIFT.json", drift)
        second_attempts = [_run_worker(db, second_run, "turn-2-attempt-1", evidence / "worker-turn-2-attempt-1.log")]
        if second_attempts[-1]["run_status"] != "SUCCEEDED" and second_attempts[-1]["worker_return_code"] == 0:
            # The frozen budget permits at most one bounded retry after a recorded
            # transport failure; the SQLite trigger prevents a fifth reservation.
            time.sleep(2.2)
            second_attempts.append(_run_worker(
                db, second_run, "turn-2-attempt-2", evidence / "worker-turn-2-attempt-2.log"
            ))
        second_worker = second_attempts[-1]
        if second_worker["run_status"] != "SUCCEEDED" or second_worker["answer"] is None:
            with connect(db) as connection:
                attempt_trace = {
                    "compression": [dict(row) for row in connection.execute(
                        "SELECT attempt_id,attempt_no,status,error_class,estimated_input_tokens,provider_response_id,input_tokens,total_tokens,source_dependencies_json "
                        "FROM context_compression_attempts WHERE run_id=? ORDER BY attempt_no", (second_run,)
                    )],
                    "answer": [dict(row) for row in connection.execute(
                        "SELECT attempt_id,attempt_no,status,error_class,provider_response_id,input_tokens,total_tokens "
                        "FROM chat_attempts WHERE run_id=? ORDER BY attempt_no", (second_run,)
                    )],
                    "retry_state": [dict(row) for row in connection.execute(
                        "SELECT * FROM worker_retry_state WHERE run_id=?", (second_run,)
                    )],
                }
            total_reserved = _provider_attempt_count(db, [first_run, second_run])
            _write(evidence / "TURN-2-FAILURE.json", {
                "worker_attempts": second_attempts, "attempt_trace": attempt_trace,
                "provider_request_count_upper_bound": total_reserved,
                "old_summary_reentered": False,
                "note": "The transport failure and bounded retry outcome are retained; the 4-request SQLite cap was enforced.",
            })
            result.update({
                "status": "PARTIAL", "first_turn": {"run_id": first_run, "answer": first_worker["answer"], "manifest": first_manifest},
                "second_turn_worker_attempts": second_attempts, "second_turn_attempt_trace": attempt_trace,
                "provider_request_count_upper_bound": total_reserved,
                "provider_cap_respected": total_reserved <= PROVIDER_REQUEST_CAP,
                "source_version_drift": drift,
                "summary_used_on_first_turn": True,
                "second_turn_summary_recovery": "NOT_PROVEN_DUE_TO_PROVIDER_TRANSPORT_FAILURE",
            })
            _write(evidence / "RESULTS.json", result)
            return 1
        second_manifest = _manifest(db, actor_id, second_run)
        second_refs = second_manifest.get("summary_refs", [])
        second_excluded = second_manifest.get("excluded_sources", [])
        summary_excluded = [
            item for item in second_excluded
            if isinstance(item, dict) and item.get("source_id") == summary["summary_id"]
        ]
        with connect(db) as connection:
            second_context = connection.execute(
                """SELECT excluded_sources_json FROM chat_context_manifests
                   WHERE run_id=? ORDER BY created_at DESC LIMIT 1""", (second_run,),
            ).fetchone()
            answer_exclusions = []
            if second_context is not None:
                decoded = json.loads(str(second_context["excluded_sources_json"]))
                answer_exclusions = [
                    item for item in decoded if isinstance(item, dict)
                    and item.get("message_id") == first_answer["message_id"]
                ]
            summary_after = connection.execute(
                "SELECT state,invalidation_reason FROM context_summaries WHERE summary_id=?",
                (summary["summary_id"],),
            ).fetchone()
        total_reserved = _provider_attempt_count(db, [first_run, second_run])
        business_after = _business_snapshot(db)
        if total_reserved > PROVIDER_REQUEST_CAP:
            raise RuntimeError(f"SQLite provider cap failed: {total_reserved}>{PROVIDER_REQUEST_CAP}.")
        if any(str(ref.get("summary_id")) == str(summary["summary_id"])
               for ref in second_refs if isinstance(ref, dict)):
            raise RuntimeError("Invalidated original Summary re-entered the second Provider context.")
        if not summary_excluded or not answer_exclusions:
            raise RuntimeError("Second context did not record exclusion of the invalid Summary and its dependent assistant answer.")
        if business_before != business_after:
            raise RuntimeError("CHAT_READONLY Summary experiment changed business/security configuration.")
        result.update({
            "status": "PASS", "source_summary_id": summary["summary_id"],
            "source_summary_version": int(summary["summary_version"]), "source_version_drift": drift,
            "provider_request_count_upper_bound": total_reserved,
            "provider_request_cap_respected": total_reserved <= PROVIDER_REQUEST_CAP,
            "first_turn_summary_used_in_real_provider_context": True,
            "first_answer_persistently_depends_on_summary": True,
            "old_summary_excluded_after_source_drift": True,
            "old_summary_exclusion": summary_excluded,
            "dependent_assistant_answer_excluded": answer_exclusions,
            "summary_state_after_drift": dict(summary_after) if summary_after else None,
            "first_turn": {"run_id": first_run, "answer": first_worker["answer"], "manifest": first_manifest},
            "second_turn": {"run_id": second_run, "answer": second_worker["answer"], "manifest": second_manifest},
            "business_configuration_unchanged": business_before == business_after,
        })
        _write(evidence / "RESULTS.json", result)
        return 0
    except Exception as error:
        result["status"] = "PARTIAL"
        result["failure"] = f"{type(error).__name__}: {error}"
        _write(evidence / "FAILURE.txt", "".join(traceback.format_exception(error)))
        result["provider_request_count_upper_bound"] = (
            _provider_attempt_count(db, _budget_runs(db)) if db.exists() else 0
        )
        _write(evidence / "RESULTS.json", result)
        return 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--worker", nargs=3, metavar=("DB", "RUN_ID", "LABEL"))
    args = parser.parse_args()
    if args.worker:
        try:
            return _worker(Path(args.worker[0]), args.worker[1], args.worker[2])
        except Exception:
            traceback.print_exc()
            return 1
    return _main()


if __name__ == "__main__":
    raise SystemExit(main())
