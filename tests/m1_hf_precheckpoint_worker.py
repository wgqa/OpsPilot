from __future__ import annotations

import asyncio
import hashlib
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("LANGGRAPH_STRICT_MSGPACK", "true")


def _event(name: str, **fields: object) -> None:
    print(json.dumps({"event": name, "pid": os.getpid(), **fields}, sort_keys=True, default=str), flush=True)


def _crash(db_path: str, checkpoint_path: str, task_id: str, run_id: str, failpoint: str) -> int:
    from opspilot.domain.database import connect
    # The production Worker owns this same lock while it claims and applies input.
    from opspilot.web.worker import SingleInstanceWorker
    from opspilot.domain.d2 import MAX_MCP_ATTEMPTS, reserve_attempt
    from opspilot.domain.investigation_context import load_investigation_context
    from opspilot.domain.task_control import apply_pending_critical_inputs, claim_task_run, trusted_identity

    worker = SingleInstanceWorker(db_path)
    worker.acquire()
    worker.register()
    identity = trusted_identity(db_path, "support-a")
    claimed = claim_task_run(db_path, identity, run_id)
    _event(
        "hf_precheckpoint_claim_committed", task_id=task_id, run_id=run_id,
        run_status=claimed["status"], worker_id=worker.owner_id, worker_epoch=worker.epoch,
        checkpoint_path=checkpoint_path,
    )

    def reserve_unknown_mcp_outcome() -> None:
        selected = load_investigation_context(db_path, task_id, run_id)
        call_id = f"hf-precheckpoint-unknown-{run_id}"
        attempt_id, count = reserve_attempt(
            db_path, task_id, "MCP", MAX_MCP_ATTEMPTS,
            call_id=call_id, tool_call_id=f"{call_id}-tool", tool_name="get_integration_config",
            argument_digest=hashlib.sha256(call_id.encode("utf-8")).hexdigest(),
            task_run_control=selected["task_run_control"],
        )
        _event(
            "hf_precheckpoint_mcp_attempt_reserved_unknown", task_id=task_id, run_id=run_id,
            attempt_id=attempt_id, attempt_count=count, status="RESERVED",
            outcome="UNKNOWN_AT_PROCESS_EXIT",
        )

    if failpoint == "after_claim":
        reserve_unknown_mcp_outcome()
        os._exit(87)
    applied = apply_pending_critical_inputs(db_path, identity, run_id)
    reserve_unknown_mcp_outcome()
    with connect(db_path) as connection:
        run = connection.execute(
            "SELECT expected_control_revision, consumed_message_seq, applied_critical_message_seq FROM task_runs WHERE run_id = ?",
            (run_id,),
        ).fetchone()
        control = connection.execute(
            "SELECT control_revision, pending_critical_message_seq, applied_critical_message_seq FROM task_controls WHERE task_id = ?",
            (task_id,),
        ).fetchone()
        messages = connection.execute(
            "SELECT message_id, sequence, body_digest, application_state, applied_run_id FROM messages "
            "WHERE task_id = ? AND input_kind = 'CORRECT_TASK_INPUT' ORDER BY sequence",
            (task_id,),
        ).fetchall()
        inputs = connection.execute(
            "SELECT message_id, run_id, input_digest, provenance FROM task_run_inputs WHERE task_id = ? ORDER BY rowid",
            (task_id,),
        ).fetchall()
    _event(
        "hf_precheckpoint_correction_applied", task_id=task_id, run_id=run_id,
        applied_inputs=applied.get("inputs", []), run=dict(run), control=dict(control),
        messages=[dict(row) for row in messages], inputs=[dict(row) for row in inputs],
        worker_id=worker.owner_id, worker_epoch=worker.epoch,
    )
    if failpoint != "after_correction_applied":
        return 2
    os._exit(87)


def _recover(db_path: str, checkpoint_path: str, task_id: str, run_id: str, prompt_capture: str) -> int:
    from langchain_core.messages import AIMessage

    import opspilot.investigator as investigator
    from opspilot.domain.database import connect
    from opspilot.web.worker import SingleInstanceWorker, _dispatch_run
    from opspilot.domain.task_control import next_worker_run

    class DeterministicChat:
        def __init__(self, *args, **kwargs):
            self.model = kwargs.get("model")

        def bind_tools(self, *args, **kwargs):
            return self

        async def ainvoke(self, messages):
            payload = [
                {"type": getattr(message, "type", type(message).__name__), "content": message.content}
                for message in messages
            ]
            with open(prompt_capture, "a", encoding="utf-8") as stream:
                stream.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")
            return AIMessage(content="The deterministic test model requests no tool call.")

    investigator.ChatOpenAI = DeterministicChat
    original_run = investigator.run_investigation

    async def pause_after_first_investigation(*args, **kwargs):
        kwargs["_interrupt_after_for_test"] = ("investigate",)
        return await original_run(*args, **kwargs)

    investigator.run_investigation = pause_after_first_investigation
    worker = SingleInstanceWorker(db_path)
    worker.acquire()
    worker.register()
    try:
        recovered = asyncio.run(worker.recover_after_exclusive_start())
        _event(
            "hf_precheckpoint_new_worker_recovered_run", task_id=task_id, run_id=run_id,
            recovered_run_ids=recovered, worker_id=worker.owner_id, worker_epoch=worker.epoch,
        )
        if run_id not in recovered:
            return 3
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            with connect(db_path) as connection:
                run = connection.execute(
                    "SELECT status FROM task_runs WHERE run_id = ?", (run_id,)
                ).fetchone()
            selected = next_worker_run(db_path)
            if selected is not None and str(selected["run_id"]) == run_id:
                asyncio.run(_dispatch_run(
                    Path(db_path), Path(checkpoint_path), worker.owner_id,
                    "executor-a", selected, worker.epoch,
                ))
                break
            time.sleep(0.1)
        else:
            _event("hf_precheckpoint_worker_selection_timeout", task_id=task_id, run_id=run_id)
            return 4
        with connect(db_path) as connection:
            run = connection.execute(
                "SELECT status, blocked_reason, expected_control_revision, consumed_message_seq, applied_critical_message_seq "
                "FROM task_runs WHERE run_id = ?", (run_id,),
            ).fetchone()
            control = connection.execute(
                "SELECT control_revision, pending_critical_message_seq, applied_critical_message_seq "
                "FROM task_controls WHERE task_id = ?", (task_id,),
            ).fetchone()
            attempts = connection.execute(
                "SELECT kind, COUNT(*) AS count FROM d2_attempts WHERE task_id = ? GROUP BY kind",
                (task_id,),
            ).fetchall()
            provenance = connection.execute(
                "SELECT selected_input_messages_json, task_run_control_json, model_status "
                "FROM d5_context_provenance WHERE task_id = ? ORDER BY built_at DESC LIMIT 1",
                (task_id,),
            ).fetchone()
            binding = connection.execute(
                "SELECT thread_id FROM task_bindings WHERE task_id = ?", (task_id,)
            ).fetchone()
        async def read_checkpoint_identity() -> tuple[str | None, str | None]:
            from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

            config = {"configurable": {"thread_id": f"{binding['thread_id']}::{run_id}"}}
            async with AsyncSqliteSaver.from_conn_string(str(checkpoint_path)) as saver:
                await saver.setup()
                saved = await saver.aget_tuple(config)
                if saved is None:
                    return None, None
                checkpoint_config = saved.config.get("configurable", {})
                return (
                    str(checkpoint_config.get("thread_id", "")),
                    str(checkpoint_config.get("checkpoint_id", "")),
                )

        checkpoint_thread_id, checkpoint_id = asyncio.run(read_checkpoint_identity())
        from opspilot.domain.execution_budget import execution_budget_snapshot

        budget = execution_budget_snapshot(db_path, task_id)
        checkpoint_exists = Path(checkpoint_path).exists() and Path(checkpoint_path).stat().st_size > 0
        _event(
            "hf_precheckpoint_recovery_finished", task_id=task_id, run_id=run_id,
            run=dict(run), control=dict(control), attempts=[dict(row) for row in attempts],
            provenance=dict(provenance) if provenance else None,
            checkpoint_exists=checkpoint_exists, checkpoint_path=checkpoint_path,
            checkpoint_thread_id=checkpoint_thread_id, checkpoint_id=checkpoint_id,
            execution_budget=budget,
            prompt_capture=prompt_capture, worker_id=worker.owner_id, worker_epoch=worker.epoch,
        )
        return 0 if checkpoint_exists and provenance is not None else 5
    finally:
        worker.release()


def main() -> int:
    if len(sys.argv) != 7:
        raise SystemExit("usage: worker crash|recover DB CHECKPOINT TASK_ID RUN_ID FAILPOINT_OR_CAPTURE")
    _, mode, db_path, checkpoint_path, task_id, run_id, final_arg = sys.argv
    if mode == "crash":
        return _crash(db_path, checkpoint_path, task_id, run_id, final_arg)
    if mode == "recover":
        return _recover(db_path, checkpoint_path, task_id, run_id, final_arg)
    raise SystemExit(f"unsupported mode: {mode}")


if __name__ == "__main__":
    raise SystemExit(main())
