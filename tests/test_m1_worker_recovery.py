from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from opspilot.domain.database import connect
from opspilot.domain.execution_budget import (
    begin_execution_interval,
    end_execution_interval,
    execution_budget_snapshot,
    heartbeat_execution_interval,
    recover_abandoned_execution_intervals,
)
from opspilot.domain.task_control import (
    create_session,
    create_task_with_initial_run,
    next_worker_run,
    trusted_identity,
)
from opspilot.web.worker import SingleInstanceWorker, WorkerAlreadyRunning, _process_run


def _create_queued_run(db: Path, deadline_ms: int = 300_000) -> tuple[str, str, str]:
    identity = trusted_identity(db, "support-a")
    session = create_session(db, identity)
    accepted = create_task_with_initial_run(
        db, identity, session_id=str(session["session_id"]), service_id="orders-demo",
        integration_id="integration-a", ticket_id="INC-A-001",
        initial_message="The authenticated orders route is returning 401.",
        idempotency_key="worker-recovery-run",
        deadline_ms=deadline_ms,
    )
    return str(accepted["task_id"]), str(accepted["run_id"]), str(accepted["thread_id"])


def test_ops_02_active_deadline_persists_across_wait_and_process_recovery(demo_db: Path) -> None:
    task_id, _, _ = _create_queued_run(demo_db, deadline_ms=10_000)
    remaining = begin_execution_interval(demo_db, task_id, now_ms=1_000)
    assert remaining == 10_000
    remaining = heartbeat_execution_interval(demo_db, task_id, now_ms=2_500)
    assert remaining == 8_500
    ended = end_execution_interval(demo_db, task_id, now_ms=4_000)
    assert ended == {"active_elapsed_ms": 3_000, "deadline_ms": 10_000, "expired": False}

    # Approval/input waiting time is outside the active interval and survives a
    # process restart without giving the Task a fresh deadline.
    remaining = begin_execution_interval(demo_db, task_id, now_ms=100_000)
    assert remaining == 7_000
    heartbeat_execution_interval(demo_db, task_id, now_ms=105_000)
    heartbeat_execution_interval(demo_db, task_id, now_ms=107_000)
    snapshot = execution_budget_snapshot(demo_db, task_id)
    assert snapshot["active_elapsed_ms"] == 10_000
    assert snapshot["remaining_ms"] == 0
    expired = end_execution_interval(demo_db, task_id, now_ms=107_000)
    assert expired["expired"] is True


def test_ops_01_process_death_releases_worker_lock_and_recovers_running_run(
    demo_db: Path, tmp_path: Path
) -> None:
    task_id, run_id, thread_id = _create_queued_run(demo_db)
    checkpoint_db = tmp_path / "checkpoint.sqlite3"
    from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
    from opspilot.investigator import build_investigation_graph

    async def seed_checkpoint() -> None:
        async with AsyncSqliteSaver.from_conn_string(str(checkpoint_db)) as checkpointer:
            await checkpointer.setup()
            graph = build_investigation_graph(
                demo_db, task_id, "m1-worker-recovery-test", None, [], [], None,
                checkpointer, checkpoint_db, d3_mode=True,
                submitter_id="support-a", executor_id="executor-a",
                business_api_url="http://127.0.0.1:1", run_id=run_id,
            )
            config = {"configurable": {"thread_id": f"{thread_id}::{run_id}"}}
            await graph.aupdate_state(
                config,
                {"task_binding_id": task_id, "stage": "investigating", "budget": {"MODEL": 0, "MCP": 0},
                 "diagnosis_draft": {}, "evidence_ids": [], "tool_observations": [],
                 "pending_call_refs": [], "gate_decision": {}, "critical_input_messages": []},
                as_node="investigate",
            )
            snapshot = await graph.aget_state(config)
            assert snapshot.values and snapshot.next

    asyncio.run(seed_checkpoint())
    child_script = Path(__file__).with_name("m1_worker_lock_holder.py")
    child_log = tmp_path / "worker-child.jsonl"
    with child_log.open("w", encoding="utf-8") as output:
        child = subprocess.Popen(
            [sys.executable, "-X", "utf8", "-u", str(child_script), str(demo_db), run_id, task_id],
            cwd=Path(__file__).resolve().parents[1], stdout=output, stderr=subprocess.STDOUT,
        )
        try:
            deadline = time.monotonic() + 15
            event = None
            while time.monotonic() < deadline:
                text = child_log.read_text(encoding="utf-8")
                for line in text.splitlines():
                    if line.startswith("{"):
                        event = json.loads(line)
                if event is not None:
                    break
                if child.poll() is not None:
                    break
                time.sleep(0.05)
            assert event is not None, child_log.read_text(encoding="utf-8")
            assert event["event"] == "RUNNING" and event["status"] == "RUNNING"
            contender = SingleInstanceWorker(demo_db)
            with pytest.raises(WorkerAlreadyRunning):
                contender.acquire()
        finally:
            if child.poll() is None:
                child.kill()
            child.wait(timeout=10)

    restarted = SingleInstanceWorker(demo_db)
    restarted.acquire()
    try:
        restarted.register()
        recovered = asyncio.run(restarted.recover_after_exclusive_start())
        assert recovered == [run_id]
        with connect(demo_db) as connection:
            run = connection.execute("SELECT status, blocked_reason FROM task_runs WHERE run_id = ?", (run_id,)).fetchone()
            budget = connection.execute(
                "SELECT active_started_at, heartbeat_at FROM task_execution_budgets WHERE task_id = ?",
                (task_id,),
            ).fetchone()
            owner = connection.execute("SELECT process_id, epoch FROM web_worker_state WHERE singleton_id = 1").fetchone()
        assert run["status"] == "INTERRUPTED_RECOVERABLE"
        assert run["blocked_reason"] == "WORKER_OWNER_RESTARTED"
        assert budget["active_started_at"] is None and budget["heartbeat_at"] is None
        assert int(owner["process_id"]) == os.getpid() and int(owner["epoch"]) == 2
        assert checkpoint_db.is_file() and checkpoint_db.stat().st_size > 0

        async def restore_checkpoint_in_new_saver() -> None:
            async with AsyncSqliteSaver.from_conn_string(str(checkpoint_db)) as checkpointer:
                graph = build_investigation_graph(
                    demo_db, task_id, "m1-worker-recovery-test", None, [], [], None,
                    checkpointer, checkpoint_db, d3_mode=True,
                    submitter_id="support-a", executor_id="executor-a",
                    business_api_url="http://127.0.0.1:1", run_id=run_id,
                )
                snapshot = await graph.aget_state(
                    {"configurable": {"thread_id": f"{thread_id}::{run_id}"}}
                )
                assert snapshot.values["stage"] == "investigating"
                assert snapshot.values["task_binding_id"] == task_id
                assert snapshot.next

        asyncio.run(restore_checkpoint_in_new_saver())
    finally:
        restarted.release()


def test_ops_02_recovered_interval_excludes_unobserved_process_downtime(demo_db: Path) -> None:
    task_id, _, _ = _create_queued_run(demo_db, deadline_ms=20_000)
    begin_execution_interval(demo_db, task_id, now_ms=1_000)
    heartbeat_execution_interval(demo_db, task_id, now_ms=2_000)
    recovered = recover_abandoned_execution_intervals(demo_db, now_ms=100_000, max_gap_ms=2_000)
    assert recovered == [task_id]
    snapshot = execution_budget_snapshot(demo_db, task_id)
    assert snapshot["active_elapsed_ms"] == 3_000
    assert snapshot["active_started_at"] is None
    assert snapshot["remaining_ms"] == 17_000


def test_ops_02_expired_total_deadline_blocks_run_without_model_call(demo_db: Path, tmp_path: Path) -> None:
    task_id, run_id, _ = _create_queued_run(demo_db, deadline_ms=1_000)
    with connect(demo_db) as connection:
        connection.execute(
            "UPDATE task_execution_budgets SET active_elapsed_ms = 1000 WHERE task_id = ?",
            (task_id,),
        )
    run = next_worker_run(demo_db)
    assert run is not None and run["run_id"] == run_id
    worker = SingleInstanceWorker(demo_db)
    worker.acquire()
    worker.register()
    try:
        asyncio.run(_process_run(
            demo_db, tmp_path / "unused-checkpoint.sqlite3", worker.owner_id, "executor-a", run
        ))
    finally:
        worker.release()
    with connect(demo_db) as connection:
        persisted_run = connection.execute(
            "SELECT status, blocked_reason FROM task_runs WHERE run_id = ?", (run_id,)
        ).fetchone()
        task_status = connection.execute(
            "SELECT status FROM task_bindings WHERE task_id = ?", (task_id,)
        ).fetchone()[0]
        model_attempts = connection.execute(
            "SELECT COUNT(*) FROM d2_attempts WHERE task_id = ? AND kind = 'MODEL'", (task_id,)
        ).fetchone()[0]
    assert tuple(persisted_run) == ("BLOCKED", "INVESTIGATION_DEADLINE_EXCEEDED")
    assert task_status == "INCONCLUSIVE"
    assert model_attempts == 0


@pytest.mark.parametrize(
    ("arguments", "expected_fragment"),
    [(("--workers", "2"), "exactly one"), (("--host", "0.0.0.0"), "127.0.0.1")],
)
def test_web_server_rejects_unsupported_multiworker_or_non_loopback_binding(
    arguments: tuple[str, ...], expected_fragment: str
) -> None:
    result = subprocess.run(
        [sys.executable, "-X", "utf8", "-m", "opspilot.web.server", *arguments],
        cwd=Path(__file__).resolve().parents[1], capture_output=True,
        text=True, encoding="utf-8", timeout=10,
    )
    assert result.returncode == 2
    assert expected_fragment in result.stderr
