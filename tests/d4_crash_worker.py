from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("LANGGRAPH_STRICT_MSGPACK", "true")


def emit(event: str, **fields: object) -> None:
    print(json.dumps({"event": event, **fields}, sort_keys=True, default=str), flush=True)


def _counts(db_path: str, connection=None) -> dict[str, int | None]:
    from opspilot.domain.database import connect

    def read(conn) -> dict[str, int | None]:
        result: dict[str, int | None] = {}
        for key, sql in (
            ("action_intent_count", "SELECT COUNT(*) FROM d3_action_intents"),
            ("ledger_count", "SELECT COUNT(*) FROM d3_action_ledgers"),
            ("delivery_count", "SELECT COUNT(*) FROM d3_delivery_records"),
            ("ticket_entry_count", "SELECT COUNT(*) FROM d3_ticket_resolution_entries"),
            ("report_count", "SELECT COUNT(*) FROM d3_report_artifacts"),
        ):
            result[key] = int(conn.execute(sql).fetchone()[0])
        try:
            result["config_version"] = int(conn.execute(
                "SELECT config_version FROM integrations WHERE tenant_id = 'tenant-a' AND integration_id = 'integration-a'"
            ).fetchone()[0])
        except (TypeError, IndexError):
            result["config_version"] = None
        latest = conn.execute(
            "SELECT ledger_id, action_id, action_kind FROM d3_action_ledgers ORDER BY rowid DESC LIMIT 1"
        ).fetchone()
        result["ledger_id"] = str(latest["ledger_id"]) if latest else None
        result["ledger_action_id"] = str(latest["action_id"]) if latest else None
        result["ledger_action_kind"] = str(latest["action_kind"]) if latest else None
        latest_intent = conn.execute(
            "SELECT action_id FROM d3_action_intents ORDER BY rowid DESC LIMIT 1"
        ).fetchone()
        result["latest_action_id"] = str(latest_intent["action_id"]) if latest_intent else None
        latest_report = conn.execute(
            "SELECT report_ref, content_digest FROM d3_report_artifacts ORDER BY rowid DESC LIMIT 1"
        ).fetchone()
        result["latest_report_ref"] = str(latest_report["report_ref"]) if latest_report else None
        result["latest_report_digest"] = str(latest_report["content_digest"]) if latest_report else None
        return result

    if connection is not None:
        return read(connection)
    with connect(db_path) as conn:
        return read(conn)


def _install_failpoint(db_path: str, target: str) -> None:
    from opspilot.domain import d3

    def crash(name: str, connection=None) -> None:
        if name != target:
            return
        emit(
            "process_crash_injected",
            pid=os.getpid(),
            failpoint=name,
            in_transaction=bool(connection.in_transaction) if connection is not None else False,
            **_counts(db_path, connection),
        )
        os._exit(75)

    d3._D4_TEST_FAILPOINT = crash


def _install_graph_failpoint(db_path: str, target: str) -> None:
    from opspilot import investigator

    def crash(name: str) -> None:
        if name != target:
            return
        emit("graph_process_crash_injected", pid=os.getpid(), failpoint=name, **_counts(db_path))
        os._exit(77)

    investigator._D4_GRAPH_TEST_FAILPOINT = crash


def run_action(args: list[str]) -> int:
    _, db_path, action_id, executor_id, action_kind, failpoint = args
    _install_failpoint(db_path, failpoint)
    from opspilot.domain.d3 import execute_deliver, execute_repair

    execute_repair(db_path, action_id, executor_id, "d4-process-action") if action_kind == "REPAIR" else execute_deliver(
        db_path, action_id, executor_id, "d4-process-action"
    )
    emit("action_returned_without_crash", pid=os.getpid(), action_id=action_id, action_kind=action_kind)
    return 0


def run_intent(args: list[str]) -> int:
    _, db_path, task_id, plan_hash, action_kind, executor_id = args
    from opspilot.domain.d3 import get_or_create_action_intent

    intent = get_or_create_action_intent(db_path, task_id, plan_hash, action_kind, executor_id)
    emit(
        "action_intent_persisted_before_checkpoint",
        pid=os.getpid(),
        action_id=intent["action_id"],
        idempotency_key=intent["idempotency_key"],
        request_digest=intent["request_digest"],
    )
    os._exit(76)


async def _run_graph(db_path: str, checkpoint_path: str, task_id: str, run_id: str, failpoint: str) -> int:
    from opspilot import investigator
    from opspilot.config import MODEL_API_KEY, MODEL_NAME
    from opspilot.domain.d2 import get_task_binding
    from opspilot.domain.task_control import get_approval_resume_link, trusted_identity
    from opspilot.web.worker import SingleInstanceWorker
    from tests.d3_recovery_setup import NoRecoveryModel, recovery_snapshot

    # Only the test process installs crash hooks or replaces model construction.
    os.environ[MODEL_API_KEY] = "d4-fixture-no-provider"
    os.environ[MODEL_NAME] = "d4-model-not-called"
    investigator.ChatOpenAI = NoRecoveryModel
    if failpoint != "-":
        if failpoint in {
            "repair_before_commit",
            "repair_after_commit_before_response",
            "deliver_before_commit",
            "deliver_after_commit_before_response",
        }:
            _install_failpoint(db_path, failpoint)
        else:
            _install_graph_failpoint(db_path, failpoint)
    worker = SingleInstanceWorker(db_path)
    worker.acquire()
    try:
        worker.register()
        recovered = await worker.recover_after_exclusive_start()
        binding = get_task_binding(db_path, task_id)
        actor = str(binding["actor_id"])
        link = get_approval_resume_link(db_path, trusted_identity(db_path, actor), run_id)
        assert link["task_id"] == task_id
        emit(
            "graph_process_start", pid=os.getpid(), run_id=run_id, worker_epoch=worker.epoch,
            recovered_run_ids=recovered, checkpoint_thread_id=link["source_checkpoint_thread_id"],
            domain=recovery_snapshot(db_path, task_id),
        )
        result = await investigator.run_investigation(
            task_id, actor, db_path=db_path, checkpoint_db_path=checkpoint_path,
            resume=True, d3_mode=True, executor_id="executor-a", run_id=run_id,
        )
        state = result["graph_state"]
        emit(
            "graph_replay_completed", pid=os.getpid(), run_id=run_id,
            stage=state.get("stage"), next_nodes=result.get("next_nodes"),
            repair_action_id=state.get("repair_action_id"),
            repair_ledger_ref=state.get("repair_ledger_ref"),
            verification_id=state.get("verification_id"),
            frozen_report_ref=state.get("frozen_report_ref"),
            deliver_action_id=state.get("deliver_action_id"),
            deliver_ledger_ref=state.get("deliver_ledger_ref"),
            domain=recovery_snapshot(db_path, task_id),
        )
        return 0
    finally:
        worker.release()


def main() -> int:
    mode = sys.argv[1]
    if mode == "action":
        return run_action(sys.argv[1:])
    if mode == "intent":
        return run_intent(sys.argv[1:])
    if mode == "graph":
        return asyncio.run(_run_graph(*sys.argv[2:]))
    raise SystemExit(f"unsupported test worker mode: {mode}")


if __name__ == "__main__":
    raise SystemExit(main())
