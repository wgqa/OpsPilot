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
    schedule_worker_retry,
    trusted_identity,
    record_worker_run_failure,
    worker_owner_matches,
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
        return await asyncio.to_thread(
            recover_running_task_runs, str(self.db_path), self.owner_id, self.epoch
        )

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


async def _process_run_inner(
    db_path: Path,
    checkpoint_path: Path,
    worker_id: str,
    executor_id: str,
    run: dict[str, object],
    worker_epoch: int | None,
) -> None:
    from opspilot.investigator import run_investigation

    run_id = str(run["run_id"])
    task_id = str(run["task_id"])
    actor_id, status = await asyncio.to_thread(_run_owner, db_path, run_id)
    identity = await asyncio.to_thread(trusted_identity, db_path, actor_id)
    if identity.role != "SUPPORT":
        await asyncio.to_thread(
            mark_run_interrupted_by_worker, db_path, worker_id, run_id,
            "RUN_OWNER_NOT_SUPPORT", worker_epoch,
        )
        return
    resume = status == "INTERRUPTED_RECOVERABLE" or str(run.get("kind")) == "APPROVAL_RESUME"
    remaining_ms = await asyncio.to_thread(begin_execution_interval, db_path, task_id)
    if remaining_ms <= 0:
        await asyncio.to_thread(
            record_worker_run_failure, db_path, worker_id, run_id,
            error_code="INVESTIGATION_DEADLINE_EXCEEDED", retryable=False,
            worker_epoch=worker_epoch,
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
                s2_mode=True,
                executor_id=executor_id,
                run_id=run_id,
            ),
            timeout=max(0.05, remaining_ms / 1000),
        )
    except asyncio.TimeoutError:
        await asyncio.to_thread(
            mark_run_interrupted_by_worker, db_path, worker_id, run_id,
            "INVESTIGATION_DEADLINE_EXCEEDED", worker_epoch,
        )
    except asyncio.CancelledError:
        await asyncio.to_thread(
            mark_run_interrupted_by_worker, db_path, worker_id, run_id,
            "WORKER_SHUTDOWN_RECOVERABLE", worker_epoch,
        )
        raise
    except Exception:
        # The fenced wrapper classifies and persists the failure after cleanup.
        # Keep exception text and stack out of browser DTOs and worker logs.
        raise
    finally:
        stop_heartbeat.set()
        heartbeat.cancel()
        try:
            await heartbeat
        except asyncio.CancelledError:
            pass
        await asyncio.to_thread(end_execution_interval, db_path, task_id)
        await asyncio.to_thread(project_outbox, str(db_path))
    latest = await asyncio.to_thread(_run_status, db_path, run_id)
    if latest == "INTERRUPTED_RECOVERABLE":
        await asyncio.to_thread(
            schedule_worker_retry, db_path, worker_id, run_id,
            error_code="INVESTIGATION_RECOVERABLE_FAILURE",
            worker_epoch=worker_epoch,
        )


def _worker_error_class(error: BaseException) -> tuple[str, bool]:
    if isinstance(error, BaseExceptionGroup):
        for nested in error.exceptions:
            code, retryable = _worker_error_class(nested)
            if code != "WORKER_RUN_FAILED":
                return code, retryable
    if isinstance(error, TaskControlError):
        return error.code, error.code == "TASK_RUN_BUSY"
    if "Missing required model configuration:" in str(error):
        return "MODEL_CONFIGURATION_MISSING", False
    if isinstance(error, ValueError):
        return "WORKER_INPUT_INVALID", False
    return "WORKER_RUN_FAILED", True


async def _process_run(
    db_path: Path,
    checkpoint_path: Path,
    worker_id: str,
    executor_id: str,
    run: dict[str, object],
    worker_epoch: int | None = None,
) -> None:
    try:
        await _process_run_inner(
            db_path, checkpoint_path, worker_id, executor_id, run, worker_epoch
        )
    except asyncio.CancelledError:
        raise
    except Exception as error:
        error_code, retryable = _worker_error_class(error)
        await asyncio.to_thread(
            record_worker_run_failure, db_path, worker_id, str(run["run_id"]),
            error_code=error_code, retryable=retryable, worker_epoch=worker_epoch,
        )


def _run_status(path: str | Path, run_id: str) -> str | None:
    with connect(path) as connection:
        row = connection.execute("SELECT status FROM task_runs WHERE run_id = ?", (run_id,)).fetchone()
    return str(row["status"]) if row is not None else None


def _chat_run_actor(path: str | Path, run_id: str) -> str:
    with connect(path) as connection:
        row = connection.execute(
            """SELECT s.owner_id FROM task_runs r JOIN sessions s
               ON s.session_id = r.session_id AND s.tenant_id = r.tenant_id
               WHERE r.run_id = ? AND r.kind = 'CHAT_READONLY'""",
            (run_id,),
        ).fetchone()
    if row is None:
        raise TaskControlError("TASK_RUN_NOT_FOUND")
    return str(row["owner_id"])


def _stream_text(content: object) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        pieces: list[str] = []
        for item in content:
            if isinstance(item, str):
                pieces.append(item)
            elif isinstance(item, dict) and isinstance(item.get("text"), str):
                pieces.append(str(item["text"]))
        return "".join(pieces)
    return ""


def _provider_response_identifier(metadata: object) -> str | None:
    if not isinstance(metadata, dict):
        return None
    response_id = metadata.get("id")
    if isinstance(response_id, str) and response_id.strip():
        return response_id.strip()[:200]
    headers = metadata.get("headers")
    if not isinstance(headers, dict):
        return None
    normalized = {str(key).lower(): value for key, value in headers.items()}
    for key in ("x-request-id", "request-id", "x-provider-request-id", "x-deepseek-request-id",
                "x-dashscope-request-id", "x-ds-trace-id"):
        value = normalized.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()[:200]
    return None


async def _process_chat_run(db_path: Path, worker_id: str, run: dict[str, object]) -> None:
    from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
    from langchain_openai import ChatOpenAI

    from opspilot.config import MODEL_API_KEY, MODEL_NAME
    from opspilot.domain.chat import (
        assert_chat_compression_sources_current,
        assert_chat_context_current,
        complete_chat_attempt,
        complete_chat_compression_attempt,
        fail_chat_attempt,
        fail_chat_compression_attempt,
        fail_chat_run_without_attempt,
        persist_chat_chunk,
        prepare_chat_attempt,
        prepare_chat_compression_attempt,
        _record_provider_metadata,
    )
    from opspilot.domain.context_engineering import ContextBudgetExceeded

    run_id = str(run["run_id"])
    actor_id = await asyncio.to_thread(_chat_run_actor, db_path, run_id)
    identity = await asyncio.to_thread(trusted_identity, db_path, actor_id)
    try:
        await asyncio.to_thread(claim_task_run, db_path, identity, run_id)
    except TaskControlError:
        return
    model_id = os.environ.get(MODEL_NAME, "").strip()
    api_key = os.environ.get(MODEL_API_KEY, "").strip()
    if not model_id or not api_key:
        await asyncio.to_thread(
            fail_chat_run_without_attempt, db_path, worker_id, run_id, "MODEL_CONFIGURATION_MISSING"
        )
        return
    attempt_id: str | None = None
    compression_attempt_id: str | None = None
    model = ChatOpenAI(
        model=model_id, api_key=api_key,
        base_url=os.environ.get("OPSPILOT_MODEL_BASE_URL") or None,
        temperature=0, max_tokens=512, timeout=30, max_retries=0, stream_usage=True,
        include_response_headers=True,
    )
    try:
        while True:
            try:
                compression = await asyncio.to_thread(
                    prepare_chat_compression_attempt, db_path, run_id, worker_id, model_id
                )
            except ContextBudgetExceeded as error:
                await asyncio.to_thread(
                    fail_chat_run_without_attempt, db_path, worker_id, run_id, error.code
                )
                return
            if compression is None:
                break
            if compression.get("error"):
                return
            compression_attempt_id = str(compression["attempt_id"])
            try:
                current = await asyncio.to_thread(
                    assert_chat_compression_sources_current, db_path, worker_id, compression_attempt_id
                )
                if not current.get("current"):
                    compression_attempt_id = None
                    continue
                compression_messages = []
                for message in compression["messages"]:
                    compression_messages.append(
                        SystemMessage(content=str(message["content"]))
                        if str(message["role"]) == "system"
                        else HumanMessage(content=str(message["content"]))
                    )
                response = await model.ainvoke(compression_messages)
                response_metadata = getattr(response, "response_metadata", {}) or {}
                response_id = _provider_response_identifier(response_metadata) or getattr(response, "id", None)
                usage = getattr(response, "usage_metadata", None)
                if not isinstance(usage, dict):
                    usage = response_metadata.get("token_usage", {}) if isinstance(response_metadata, dict) else {}
                if not isinstance(usage, dict):
                    usage = {}
                result = await asyncio.to_thread(
                    complete_chat_compression_attempt, db_path, worker_id, compression_attempt_id,
                    _stream_text(getattr(response, "content", "")),
                    provider_response_id=str(response_id) if response_id else None,
                    input_tokens=usage.get("input_tokens", usage.get("prompt_tokens")),
                    output_tokens=usage.get("output_tokens", usage.get("completion_tokens")),
                    total_tokens=usage.get("total_tokens"),
                )
                compression_attempt_id = None
                if result.get("status") == "INVALIDATED":
                    continue
                if result.get("status") != "SUCCEEDED":
                    raise RuntimeError("ContextCompressionNotCommitted")
            except asyncio.CancelledError:
                raise
            except Exception as error:
                if compression_attempt_id is not None:
                    failure = await asyncio.to_thread(
                        fail_chat_compression_attempt, db_path, worker_id,
                        compression_attempt_id, type(error).__name__,
                    )
                    if failure.get("status") == "INTERRUPTED_RECOVERABLE":
                        await asyncio.to_thread(
                            schedule_worker_retry, db_path, worker_id, run_id,
                            error_code=str(failure.get("error_class") or "CHAT_COMPRESSION_FAILED"),
                        )
                    return
                raise
        prepared = await asyncio.to_thread(prepare_chat_attempt, db_path, run_id, worker_id, model_id)
        if prepared.get("error"):
            if prepared.get("error") == "CHAT_CONTEXT_COMPRESSION_REQUIRED":
                await asyncio.to_thread(
                    fail_chat_run_without_attempt, db_path, worker_id, run_id,
                    "CHAT_CONTEXT_COMPRESSION_REQUIRED",
                )
            return
        attempt_id = str(prepared["attempt_id"])
        messages = []
        for message in prepared["messages"]:
            role, content = str(message["role"]), str(message["content"])
            if role == "system":
                messages.append(SystemMessage(content=content))
            elif role == "assistant":
                messages.append(AIMessage(content=content))
            else:
                messages.append(HumanMessage(content=content))
        output: list[str] = []
        response_id: str | None = None
        input_tokens: int | None = None
        output_tokens: int | None = None
        total_tokens: int | None = None
        persisted_metadata: tuple[str | None, int | None, int | None, int | None] = (None, None, None, None)
        chunk_seq = 0
        metadata_shape_logged = False
        if run.get("task_id") is not None:
            from opspilot.domain.episodic_memory import assert_selected_memories_current

            assert_selected_memories_current(
                db_path,
                str(run["task_id"]),
                [item for item in prepared.get("memory_refs", []) if isinstance(item, dict)],
            )
        await asyncio.to_thread(assert_chat_context_current, db_path, worker_id, attempt_id)
        async for part in model.astream(messages):
            metadata = getattr(part, "response_metadata", {}) or {}
            if not metadata_shape_logged and os.environ.get("OPSPILOT_TRACE_PROVIDER_METADATA") == "1":
                headers = metadata.get("headers", {}) if isinstance(metadata, dict) else {}
                header_names = sorted(str(key).lower() for key in headers) if isinstance(headers, dict) else []
                fields = sorted(str(key) for key in metadata) if isinstance(metadata, dict) else []
                print(f"CHAT_PROVIDER_METADATA_SHAPE run_id={run_id} fields={fields} header_names={header_names}", flush=True)
                metadata_shape_logged = True
            observed_response_id = _provider_response_identifier(metadata)
            if observed_response_id:
                response_id = observed_response_id
            usage = getattr(part, "usage_metadata", None)
            if isinstance(usage, dict):
                input_tokens = usage.get("input_tokens", input_tokens)
                output_tokens = usage.get("output_tokens", output_tokens)
                total_tokens = usage.get("total_tokens", total_tokens)
            current_metadata = (response_id, input_tokens, output_tokens, total_tokens)
            if current_metadata != persisted_metadata:
                await asyncio.to_thread(
                    _record_provider_metadata, db_path, worker_id, attempt_id,
                    provider_response_id=response_id, input_tokens=input_tokens,
                    output_tokens=output_tokens, total_tokens=total_tokens,
                )
                persisted_metadata = current_metadata
            text = _stream_text(getattr(part, "content", ""))
            if not text:
                continue
            output.append(text)
            chunk_seq += 1
            await asyncio.to_thread(
                persist_chat_chunk, db_path, worker_id, attempt_id, chunk_seq, text
            )
        answer = "".join(output)
        if not answer.strip():
            raise RuntimeError("EmptyProviderResponse")
        await asyncio.to_thread(
            complete_chat_attempt, db_path, worker_id, attempt_id, answer,
            provider_response_id=response_id, input_tokens=input_tokens,
            output_tokens=output_tokens, total_tokens=total_tokens,
        )
    except asyncio.CancelledError:
        # Abrupt process termination is also reconciled by recover_running_task_runs.
        raise
    except Exception as error:
        if attempt_id is None:
            await asyncio.to_thread(
                fail_chat_run_without_attempt, db_path, worker_id, run_id,
                error.code if isinstance(error, ContextBudgetExceeded) else type(error).__name__,
            )
        else:
            result = await asyncio.to_thread(
                fail_chat_attempt, db_path, worker_id, attempt_id, type(error).__name__
            )
            if result.get("status") == "INTERRUPTED_RECOVERABLE":
                await asyncio.to_thread(
                    schedule_worker_retry, db_path, worker_id, run_id,
                    error_code=str(result.get("error_class") or "CHAT_PROVIDER_CALL_FAILED"),
                )
    finally:
        await asyncio.to_thread(project_outbox, str(db_path))


async def _dispatch_run(
    db_path: Path, checkpoint_path: Path, worker_id: str, executor_id: str,
    run: dict[str, object], worker_epoch: int | None = None,
) -> None:
    if str(run["kind"]) == "CHAT_READONLY":
        await _process_chat_run(db_path, worker_id, run)
    else:
        await _process_run(db_path, checkpoint_path, worker_id, executor_id, run, worker_epoch)


async def run_worker(
    db_path: str | Path,
    checkpoint_db_path: str | Path,
    *,
    worker_id: str,
    executor_id: str,
    poll_interval: float = 0.2,
    worker_epoch: int | None = None,
) -> None:
    resolved_db = Path(db_path).resolve()
    resolved_checkpoint = Path(checkpoint_db_path).resolve()
    while True:
        if not await asyncio.to_thread(
            worker_owner_matches, str(resolved_db), worker_id, worker_epoch
        ):
            raise TaskControlError("WORKER_FENCE_STALE")
        run = await asyncio.to_thread(next_worker_run, str(resolved_db))
        if run is None:
            await asyncio.sleep(poll_interval)
            continue
        try:
            await _dispatch_run(
                resolved_db, resolved_checkpoint, worker_id, executor_id, run, worker_epoch
            )
        except asyncio.CancelledError:
            raise
        except Exception as error:
            if isinstance(error, TaskControlError) and error.code == "WORKER_FENCE_STALE":
                raise
            error_code, retryable = _worker_error_class(error)
            if str(run["kind"]) == "CHAT_READONLY":
                from opspilot.domain.chat import fail_chat_run_without_attempt

                await asyncio.to_thread(
                    fail_chat_run_without_attempt, resolved_db, worker_id,
                    str(run["run_id"]), error_code,
                )
            else:
                await asyncio.to_thread(
                    record_worker_run_failure, resolved_db, worker_id,
                    str(run["run_id"]), error_code=error_code, retryable=retryable,
                    worker_epoch=worker_epoch,
                )
