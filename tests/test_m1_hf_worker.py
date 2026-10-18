from __future__ import annotations

import asyncio
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from opspilot.domain.database import connect
from opspilot.domain.task_control import (
    abort_task,
    admit_task_message,
    apply_pending_critical_inputs,
    claim_task_run,
    create_session,
    create_task_with_initial_run,
    finish_task_run,
    trusted_identity,
)
from opspilot.web.app import create_app
from opspilot.web.worker import SingleInstanceWorker, _process_run, run_worker


PASSWORDS = {"support-a": "support-test-password", "approver-a": "approver-test-password"}
ORIGIN = "http://testserver"


def _new_task(db: Path, session_id: str, key: str, *, deadline_ms: int = 300_000) -> dict[str, str]:
    identity = trusted_identity(db, "support-a")
    accepted = create_task_with_initial_run(
        db, identity, session_id=session_id, service_id="orders-demo", integration_id="integration-a",
        ticket_id=f"INC-{key}", initial_message=f"The orders route is returning 401 ({key}).",
        idempotency_key=key, deadline_ms=deadline_ms,
    )
    return {key: str(accepted[key]) for key in ("task_id", "run_id", "thread_id", "session_id")}


def _set_recoverable(db: Path, task_id: str, run_id: str, *, expire_budget: bool = False) -> None:
    with connect(db) as connection:
        connection.execute(
            "UPDATE task_runs SET status = 'INTERRUPTED_RECOVERABLE', blocked_reason = 'TEST_PREEXISTING' WHERE run_id = ?",
            (run_id,),
        )
        if expire_budget:
            connection.execute(
                "UPDATE task_execution_budgets SET active_elapsed_ms = deadline_ms WHERE task_id = ?",
                (task_id,),
            )


def _query_run(db: Path, run_id: str) -> str:
    with connect(db) as connection:
        return str(connection.execute("SELECT status FROM task_runs WHERE run_id = ?", (run_id,)).fetchone()[0])


def _run_record(db: Path, run_id: str) -> dict[str, object]:
    with connect(db) as connection:
        row = connection.execute("SELECT * FROM task_runs WHERE run_id = ?", (run_id,)).fetchone()
    assert row is not None
    return {key: row[key] for key in row.keys()}


def _test_executor(db: Path, *, correction_run_id: str | None = None):
    async def fake_investigation(task_ref: str, actor_id: str, **kwargs: object) -> dict[str, object]:
        run_id = str(kwargs["run_id"])
        identity = trusted_identity(db, actor_id)
        claim_task_run(db, identity, run_id)
        if run_id == correction_run_id:
            apply_pending_critical_inputs(db, identity, run_id)
            return finish_task_run(db, identity, run_id, "WAITING_INPUT")
        return finish_task_run(db, identity, run_id, "SUCCEEDED")

    return fake_investigation


async def _drive_worker_until(
    db: Path, checkpoint: Path, worker_id: str, worker_epoch: int | None, predicate,
    timeout: float = 3.0,
) -> tuple[bool, str | None]:
    task = asyncio.create_task(
        run_worker(
            db, checkpoint, worker_id=worker_id, executor_id="executor-a",
            poll_interval=0.01, worker_epoch=worker_epoch,
        )
    )
    deadline = time.monotonic() + timeout
    try:
        while time.monotonic() < deadline:
            done = predicate()
            if done:
                # The test executor writes the terminal Run state immediately
                # before returning; let Worker finish its cleanup first.
                await asyncio.sleep(0.05)
                break
            if task.done():
                break
            await asyncio.sleep(0.01)
        worker_was_alive = not task.done()
        worker_error = None
        if task.done() and not task.cancelled():
            error = task.exception()
            worker_error = type(error).__name__ if error is not None else None
        return worker_was_alive, worker_error
    finally:
        if not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass


def test_hf01_aborted_expired_recoverable_run_does_not_starve_next_task(
    demo_db: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import opspilot.investigator

    identity = trusted_identity(demo_db, "support-a")
    session = create_session(demo_db, identity)
    first = _new_task(demo_db, str(session["session_id"]), "hf01-first", deadline_ms=1_000)
    second = _new_task(demo_db, str(session["session_id"]), "hf01-second")
    _set_recoverable(demo_db, first["task_id"], first["run_id"], expire_budget=True)
    abort_task(
        demo_db, identity, task_id=first["task_id"], reason="stop stale work", idempotency_key="hf01-abort",
    )
    monkeypatch.setattr(opspilot.investigator, "run_investigation", _test_executor(demo_db))
    worker = SingleInstanceWorker(demo_db)
    worker.acquire()
    worker.register()
    try:
        worker_alive, worker_error = asyncio.run(_drive_worker_until(
            demo_db, tmp_path / "hf01-checkpoint.sqlite3", worker.owner_id, worker.epoch,
            lambda: _query_run(demo_db, second["run_id"]) == "SUCCEEDED",
        ))
        with connect(demo_db) as connection:
            first_run = connection.execute(
                "SELECT status, blocked_reason FROM task_runs WHERE run_id = ?", (first["run_id"],)
            ).fetchone()
            first_control = connection.execute(
                "SELECT terminal_state FROM task_controls WHERE task_id = ?", (first["task_id"],)
            ).fetchone()[0]
        assert first_control == "ABORTED"
        assert tuple(first_run) == ("BLOCKED", "TASK_ABORTED")
        assert _query_run(demo_db, second["run_id"]) == "SUCCEEDED"
        assert worker_alive, f"worker exited while processing a stale Run: {worker_error}"
    finally:
        worker.release()


def test_hf02_stale_run_after_correction_is_blocked_and_new_run_progresses(
    demo_db: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import opspilot.investigator
    from opspilot.web.worker import next_worker_run

    identity = trusted_identity(demo_db, "support-a")
    session = create_session(demo_db, identity)
    stale = _new_task(demo_db, str(session["session_id"]), "hf02-old")
    _set_recoverable(demo_db, stale["task_id"], stale["run_id"])
    correction = admit_task_message(
        demo_db, identity, session_id=str(session["session_id"]), task_id=stale["task_id"],
        input_kind="CORRECT_TASK_INPUT", body="Correction: the principal is enabled; recheck current credential facts.",
        idempotency_key="hf02-correction",
    )
    healthy = _new_task(demo_db, str(session["session_id"]), "hf02-other")
    monkeypatch.setattr(
        opspilot.investigator, "run_investigation",
        _test_executor(demo_db, correction_run_id=str(correction["run_id"])),
    )
    worker = SingleInstanceWorker(demo_db)
    worker.acquire()
    worker.register()
    try:
        asyncio.run(_process_run(
            demo_db, tmp_path / "hf02-checkpoint.sqlite3", worker.owner_id, "executor-a",
            _run_record(demo_db, stale["run_id"]), worker.epoch,
        ))
        with connect(demo_db) as connection:
            old = connection.execute(
                "SELECT status, blocked_reason FROM task_runs WHERE run_id = ?", (stale["run_id"],)
            ).fetchone()
            control = connection.execute(
                "SELECT control_revision, pending_critical_message_seq, applied_critical_message_seq "
                "FROM task_controls WHERE task_id = ?", (stale["task_id"],)
            ).fetchone()
            plans = connection.execute(
                "SELECT COUNT(*) FROM d3_plans WHERE task_id = ?", (stale["task_id"],)
            ).fetchone()[0]
            ledgers = connection.execute(
                "SELECT COUNT(*) FROM d3_action_ledgers WHERE task_id = ?", (stale["task_id"],)
            ).fetchone()[0]
        assert tuple(old) == ("BLOCKED", "TASK_CONTROL_STALE")
        assert tuple(control) == (1, 2, 0)
        assert int(plans) == 0 and int(ledgers) == 0
        selected = next_worker_run(demo_db)
        assert selected is not None and str(selected["run_id"]) == str(correction["run_id"])
        asyncio.run(_process_run(
            demo_db, tmp_path / "hf02-checkpoint.sqlite3", worker.owner_id, "executor-a", selected,
            worker.epoch,
        ))
        selected = next_worker_run(demo_db)
        assert selected is not None and str(selected["run_id"]) == healthy["run_id"]
        asyncio.run(_process_run(
            demo_db, tmp_path / "hf02-checkpoint.sqlite3", worker.owner_id, "executor-a", selected,
            worker.epoch,
        ))
        assert _query_run(demo_db, str(correction["run_id"])) == "WAITING_INPUT"
        assert _query_run(demo_db, healthy["run_id"]) == "SUCCEEDED"
        with connect(demo_db) as connection:
            applied_control = connection.execute(
                "SELECT control_revision, pending_critical_message_seq, applied_critical_message_seq "
                "FROM task_controls WHERE task_id = ?", (stale["task_id"],)
            ).fetchone()
        assert tuple(applied_control) == (2, None, 2)
    finally:
        worker.release()


def test_hf03_preclaim_failure_is_bounded_and_worker_continues(
    demo_db: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import opspilot.investigator
    from opspilot.config import MODEL_API_KEY, MODEL_NAME

    identity = trusted_identity(demo_db, "support-a")
    session = create_session(demo_db, identity)
    misconfigured = _new_task(demo_db, str(session["session_id"]), "hf03-bad")
    healthy = _new_task(demo_db, str(session["session_id"]), "hf03-good")
    monkeypatch.setenv(MODEL_API_KEY, "")
    monkeypatch.setenv(MODEL_NAME, "")
    original = opspilot.investigator.run_investigation
    good = _test_executor(demo_db)

    async def run_one(task_ref: str, actor_id: str, **kwargs: object) -> dict[str, object]:
        if str(kwargs["run_id"]) == healthy["run_id"]:
            return await good(task_ref, actor_id, **kwargs)
        return await original(task_ref, actor_id, **kwargs)

    monkeypatch.setattr(opspilot.investigator, "run_investigation", run_one)
    from opspilot.web.worker import next_worker_run

    worker = SingleInstanceWorker(demo_db)
    worker.acquire()
    worker.register()
    try:
        selected = next_worker_run(demo_db)
        assert selected is not None and str(selected["run_id"]) == misconfigured["run_id"]
        asyncio.run(_process_run(
            demo_db, tmp_path / "hf03-checkpoint.sqlite3", worker.owner_id, "executor-a", selected,
            worker.epoch,
        ))
        with connect(demo_db) as connection:
            bad = connection.execute(
                "SELECT status, blocked_reason FROM task_runs WHERE run_id = ?", (misconfigured["run_id"],)
            ).fetchone()
            retry = connection.execute(
                "SELECT retry_count, max_retries, last_error_code FROM worker_retry_state WHERE run_id = ?",
                (misconfigured["run_id"],),
            ).fetchone()
        assert tuple(bad) == ("BLOCKED", "MODEL_CONFIGURATION_MISSING")
        assert tuple(retry) == (0, 3, "MODEL_CONFIGURATION_MISSING")
        selected = next_worker_run(demo_db)
        assert selected is not None and str(selected["run_id"]) == healthy["run_id"]
        asyncio.run(_process_run(
            demo_db, tmp_path / "hf03-checkpoint.sqlite3", worker.owner_id, "executor-a", selected,
            worker.epoch,
        ))
        assert _query_run(demo_db, healthy["run_id"]) == "SUCCEEDED"
    finally:
        worker.release()


def test_hf10_health_reports_api_and_worker_liveness_separately(demo_db: Path, tmp_path: Path) -> None:
    app = create_app(
        db_path=demo_db, checkpoint_db_path=tmp_path / "hf10-checkpoint.sqlite3", start_worker=True,
        credentials=PASSWORDS, expected_origin=ORIGIN,
    )
    with TestClient(app) as client:
        healthy = client.get("/api/health").json()
        assert healthy["api"] == "alive"
        assert healthy["worker"]["status"] == "running"
        assert healthy["worker"]["ready"] is True
        worker_task = app.state.worker_task
        app.state.worker_loop.call_soon_threadsafe(worker_task.cancel)
        time.sleep(0.05)
        failed = client.get("/api/health").json()
        assert failed["api"] == "alive"
        assert failed["worker"]["status"] == "stopped"
        assert failed["worker"]["ready"] is False

    disabled_app = create_app(
        db_path=demo_db, checkpoint_db_path=tmp_path / "hf10-disabled-checkpoint.sqlite3", start_worker=False,
        credentials=PASSWORDS, expected_origin=ORIGIN,
    )
    with TestClient(disabled_app) as client:
        disabled = client.get("/api/health").json()
        assert disabled["api"] == "alive"
        assert disabled["worker"]["status"] == "disabled"
        assert disabled["worker"]["ready"] is False


def test_hf09_worker_keeps_action_outcome_unknown_fail_closed_through_async_group() -> None:
    from opspilot.domain.task_control import TaskControlError
    from opspilot.web.worker import _worker_error_class

    wrapped = ExceptionGroup(
        "async client task group",
        [ExceptionGroup("graph task group", [TaskControlError("ACTION_OUTCOME_UNKNOWN")])],
    )
    assert _worker_error_class(wrapped) == ("ACTION_OUTCOME_UNKNOWN", False)
