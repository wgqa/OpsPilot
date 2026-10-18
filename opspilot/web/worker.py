from __future__ import annotations

import asyncio
import os
import time
import uuid
from pathlib import Path

from opspilot.domain.database import connect
from opspilot.domain.execution_budget import (
    begin_execution_interval,
    end_execution_interval,
    heartbeat_execution_interval,
    recover_abandoned_execution_intervals,
)
from opspilot.domain.events import project_outbox
from opspilot.domain.task_control import (
    TaskControlError,
    finish_task_run,
    mark_run_interrupted_by_worker,
    next_worker_run,
    recover_running_task_runs,
    register_worker_owner,
    resume_task_run,
    claim_task_run,
    trusted_identity,
)


class WorkerAlreadyRunning(RuntimeError):
    pass


class SingleInstanceWorker:
    """Local process lock. Kernel ownership is released automatically on process exit."""

    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path).resolve()
        self.lock_path = self.db_path.with_suffix(self.db_path.suffix + ".worker.lock")
        self.owner_id = f"worker-{uuid.uuid4()}"
        self._handle = None
        self.epoch: int | None = None

    def acquire(self) -> None:
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        handle = self.lock_path.open("a+b")
        handle.seek(0, os.SEEK_END)
        if handle.tell() == 0:
            handle.write(b"\0")
            handle.flush()
        handle.seek(0)
        try:
            if os.name == "nt":
                import msvcrt

                # Windows may take a short interval after TerminateProcess to
                # release byte-range locks for every handle in the dead process.
                # Retry briefly so a clean crash restart does not look occupied.
                deadline = time.monotonic() + 1.0
                while True:
                    try:
                        handle.seek(0)
                        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                        break
                    except OSError:
                        if time.monotonic() >= deadline:
                            raise
                        time.sleep(0.05)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            handle.close()
            raise WorkerAlreadyRunning("Another OpsPilot worker owns this Domain database.") from error
        self._handle = handle

    def register(self) -> None:
        if self._handle is None:
            raise RuntimeError("Worker process lock must be acquired before registration.")
        self.epoch = register_worker_owner(str(self.db_path), self.owner_id, os.getpid())

    async def recover_after_exclusive_start(self) -> list[str]:
        if self._handle is None or self.epoch is None:
            raise RuntimeError("Worker must be registered before recovery.")
        await asyncio.to_thread(recover_abandoned_execution_intervals, str(self.db_path))
        return await asyncio.to_thread(recover_running_task_runs, str(self.db_path), self.owner_id)

    def release(self) -> None:
        if self._handle is None:
            return
        try:
            if os.name == "nt":
                import msvcrt

                self._handle.seek(0)
                msvcrt.locking(self._handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(self._handle.fileno(), fcntl.LOCK_UN)
        finally:
            self._handle.close()
            self._handle = None


def _run_owner(path: str | Path, run_id: str) -> tuple[str, str]:
    with connect(path) as connection:
        row = connection.execute(
            """SELECT r.task_id, r.status, s.owner_id FROM task_runs AS r JOIN sessions AS s
               ON s.session_id = r.session_id AND s.tenant_id = r.tenant_id WHERE r.run_id = ?""",
            (run_id,),
        ).fetchone()
    if row is None or row["task_id"] is None:
        raise TaskControlError("TASK_REQUIRED_FOR_BUSINESS_RUN")
    return str(row["owner_id"]), str(row["status"])


async def _heartbeat_budget(db_path: str, task_id: str, stopped: asyncio.Event) -> None:
    while not stopped.is_set():
        try:
            await asyncio.wait_for(stopped.wait(), timeout=0.5)
            return
        except asyncio.TimeoutError:
            await asyncio.to_thread(heartbeat_execution_interval, db_path, task_id)


async def _process_run(
    db_path: Path,
    checkpoint_path: Path,
    worker_id: str,
    executor_id: str,
    run: dict[str, object],
) -> None:
    from opspilot.investigator import run_investigation

    run_id = str(run["run_id"])
    task_id = str(run["task_id"])
    actor_id, status = await asyncio.to_thread(_run_owner, db_path, run_id)
    identity = await asyncio.to_thread(trusted_identity, db_path, actor_id)
    if identity.role != "SUPPORT":
        await asyncio.to_thread(
            mark_run_interrupted_by_worker, db_path, worker_id, run_id, "RUN_OWNER_NOT_SUPPORT"
        )
        return
    resume = status == "INTERRUPTED_RECOVERABLE"
    remaining_ms = await asyncio.to_thread(begin_execution_interval, db_path, task_id)
    if remaining_ms <= 0:
        if resume:
            await asyncio.to_thread(resume_task_run, db_path, identity, run_id)
        else:
            await asyncio.to_thread(claim_task_run, db_path, identity, run_id)
        await asyncio.to_thread(
            finish_task_run, db_path, identity, run_id, "BLOCKED",
            blocked_reason="INVESTIGATION_DEADLINE_EXCEEDED",
        )
        await asyncio.to_thread(end_execution_interval, db_path, task_id)
        return

    stop_heartbeat = asyncio.Event()
    heartbeat = asyncio.create_task(_heartbeat_budget(str(db_path), task_id, stop_heartbeat))
    try:
        await asyncio.wait_for(
            run_investigation(
                task_id,
                actor_id,
                db_path=db_path,
                checkpoint_db_path=checkpoint_path,
                resume=resume,
                d3_mode=True,
                executor_id=executor_id,
                run_id=run_id,
            ),
            timeout=max(0.05, remaining_ms / 1000),
        )
    except asyncio.TimeoutError:
        await asyncio.to_thread(
            mark_run_interrupted_by_worker, db_path, worker_id, run_id,
            "INVESTIGATION_DEADLINE_EXCEEDED",
        )
    except asyncio.CancelledError:
        await asyncio.to_thread(
            mark_run_interrupted_by_worker, db_path, worker_id, run_id,
            "WORKER_SHUTDOWN_RECOVERABLE",
        )
        raise
    except Exception:
        # run_investigation persists its own interrupted outcome after it claims a
        # Run. Do not expose provider/MCP exception text in worker logs or API DTOs.
        pass
    finally:
        stop_heartbeat.set()
        heartbeat.cancel()
        try:
            await heartbeat
        except asyncio.CancelledError:
            pass
        await asyncio.to_thread(end_execution_interval, db_path, task_id)
        await asyncio.to_thread(project_outbox, str(db_path))


async def run_worker(
    db_path: str | Path,
    checkpoint_db_path: str | Path,
    *,
    worker_id: str,
    executor_id: str,
    poll_interval: float = 0.2,
) -> None:
    resolved_db = Path(db_path).resolve()
    resolved_checkpoint = Path(checkpoint_db_path).resolve()
    attempted: set[str] = set()
    while True:
        run = await asyncio.to_thread(next_worker_run, str(resolved_db), tuple(sorted(attempted)))
        if run is None:
            await asyncio.sleep(poll_interval)
            continue
        run_id = str(run["run_id"])
        attempted.add(run_id)
        await _process_run(resolved_db, resolved_checkpoint, worker_id, executor_id, run)
