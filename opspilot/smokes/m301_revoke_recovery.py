from __future__ import annotations

"""Cross-process Worker recovery after an approved case Memory is revoked."""

import argparse
import asyncio
import json
import os
import shutil
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from opspilot.config import ROOT, load_local_environment


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )


def _child(phase: str, db_path: Path, checkpoint_path: Path, run_id: str) -> int:
    from langchain_core.messages import AIMessage

    import opspilot.investigator as investigator
    from opspilot.domain.database import connect
    from opspilot.domain.task_control import next_worker_run
    from opspilot.web.worker import SingleInstanceWorker, _dispatch_run

    load_local_environment()
    os.environ.setdefault("OPSPILOT_MODEL_API_KEY", "m301-deterministic-worker-test")
    os.environ.setdefault("OPSPILOT_MODEL_NAME", "m301-deterministic-worker-test")
    captured: list[dict[str, object]] = []

    class DeterministicChat:
        def __init__(self, *args: object, **kwargs: object):
            pass

        def bind_tools(self, *args: object, **kwargs: object) -> "DeterministicChat":
            return self

        async def ainvoke(self, messages: list[object]) -> AIMessage:
            payload = str(getattr(messages[-1], "content", "")) if messages else ""
            _, separator, body = payload.partition("\n")
            context = json.loads(body) if separator else {}
            selected = context.get("historical_memory_guidance", [])
            memory_ids = [
                str(item["memory_id"])
                for item in selected if isinstance(item, dict) and item.get("memory_id")
            ]
            captured.append({"selected_memory_ids": memory_ids})
            if phase == "pause" and len(captured) == 1:
                return AIMessage(
                    content="",
                    tool_calls=[{
                        "name": "get_principal_status",
                        "args": {"principal_id": "principal-a"},
                        "id": "m301-recovery-principal-read",
                        "type": "tool_call",
                    }],
                )
            return AIMessage(content="The current Task evidence is sufficient for a safe stop.")

    investigator.ChatOpenAI = DeterministicChat
    original_run = investigator.run_investigation

    async def run_for_worker(*args: object, **kwargs: object) -> dict[str, object]:
        if phase == "pause":
            kwargs["_interrupt_after_for_test"] = ("investigate",)
        return await original_run(*args, **kwargs)

    investigator.run_investigation = run_for_worker
    worker = SingleInstanceWorker(db_path)
    worker.acquire()
    worker.register()
    try:
        recovered = asyncio.run(worker.recover_after_exclusive_start())
        deadline = time.monotonic() + 45
        selected_run: dict[str, object] | None = None
        while time.monotonic() < deadline:
            item = next_worker_run(db_path)
            if item is not None and str(item["run_id"]) == run_id:
                selected_run = item
                break
            time.sleep(0.2)
        if selected_run is None:
            raise RuntimeError("Restarted Worker did not select the persisted recoverable Run.")
        asyncio.run(_dispatch_run(
            db_path, checkpoint_path, worker.owner_id, "executor-a", selected_run, worker.epoch,
        ))
        with connect(db_path) as connection:
            run = connection.execute(
                "SELECT status, blocked_reason FROM task_runs WHERE run_id = ?", (run_id,),
            ).fetchone()
        print(json.dumps({
            "phase": phase,
            "pid": os.getpid(),
            "worker_id": worker.owner_id,
            "worker_epoch": worker.epoch,
            "recovered_run_ids": recovered,
            "run": dict(run) if run is not None else None,
            "model_contexts": captured,
        }, ensure_ascii=False, sort_keys=True), flush=True)
        return 0
    finally:
        worker.release()


def run_recovery(
    source_db: str | Path, source_task_id: str, evidence_dir: str | Path,
) -> int:
    load_local_environment()
    output = Path(evidence_dir)
    output = (output if output.is_absolute() else ROOT / output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    runtime = ROOT / ".runtime" / "m301-revoke-recovery" / stamp
    runtime.mkdir(parents=True, exist_ok=False)
    source = Path(source_db)
    source = (source if source.is_absolute() else ROOT / source).resolve()
    db_path = runtime / "domain.sqlite3"
    checkpoint_path = runtime / "checkpoints.sqlite3"
    shutil.copy2(source, db_path)

    from opspilot.domain.d2 import finish_attempt, probe_endpoint_fact, record_tool_observation, reserve_attempt
    from opspilot.domain.database import connect
    from opspilot.domain.episodic_memory import confirm_memory, create_memory_candidate, list_context_provenance, revoke_memory
    from opspilot.domain.task_control import (
        apply_pending_critical_inputs, claim_task_run, create_session,
        create_task_with_initial_run, finish_task_run, trusted_identity,
    )

    candidate = create_memory_candidate(
        db_path, source_task_id, "support-a", idempotency_key=f"m301-recovery-{stamp}-candidate",
    )
    active = confirm_memory(
        db_path, str(candidate["memory_id"]), "approver-a",
        idempotency_key=f"m301-recovery-{stamp}-confirm",
    )
    with connect(db_path) as connection:
        connection.execute(
            "UPDATE integrations SET credential_ref = 'cred-v1', config_version = 7 "
            "WHERE tenant_id = 'tenant-a' AND integration_id = 'integration-a'"
        )
    identity = trusted_identity(db_path, "support-a")
    session = create_session(db_path, identity)
    created = create_task_with_initial_run(
        db_path, identity, session_id=str(session["session_id"]),
        service_id="orders-demo", integration_id="integration-a",
        ticket_id=f"M301-RECOVERY-{stamp}",
        initial_message="订单接口当前 401，请基于真实绑定证据核实。",
        idempotency_key=f"m301-recovery-{stamp}-task",
    )
    task_id, run_id = str(created["task_id"]), str(created["run_id"])
    claim_task_run(db_path, identity, run_id)
    apply_pending_critical_inputs(db_path, identity, run_id)

    from opspilot.domain.api import make_server

    server = make_server(db_path, "tenant-a", "127.0.0.1", 0)
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
    thread.start()
    try:
        host, port = server.server_address
        probe = probe_endpoint_fact(
            db_path, task_id, "orders-demo", "integration-a", f"http://{host}:{port}",
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
    if probe.get("facts", {}).get("http_status") != 401:
        raise RuntimeError("Recovery fixture did not produce a real HTTP 401.")
    call_id = f"m301-recovery-{stamp}-probe"
    attempt_id, _ = reserve_attempt(
        db_path, task_id, "MCP", 6, call_id=call_id,
        tool_call_id=f"{call_id}-tool", tool_name="probe_endpoint",
        argument_digest=f"{call_id}-arguments", run_id=run_id,
    )
    finish_attempt(db_path, attempt_id, "OK")
    observation = record_tool_observation(
        db_path, task_id=task_id, call_id=call_id, attempt_id=attempt_id,
        tool_call_id=f"{call_id}-tool", tool_name="probe_endpoint",
        arguments={"service_id": "orders-demo", "integration_id": "integration-a"},
        status="OK", result=probe,
    )
    finish_task_run(
        db_path, identity, run_id, "INTERRUPTED_RECOVERABLE",
        blocked_reason="M301_PROBE_COMMITTED_BEFORE_GRAPH_CHECKPOINT",
    )

    common = [
        sys.executable, "-m", "opspilot.smokes.m301_revoke_recovery",
        "--child", "pause", "--db", str(db_path), "--checkpoint", str(checkpoint_path),
        "--run-id", run_id,
    ]
    first = subprocess.run(common, cwd=ROOT, text=True, capture_output=True, check=False, timeout=120)
    (output / "worker-before-revoke.log").write_text(
        f"COMMAND: {json.dumps(common)}\nEXIT_CODE: {first.returncode}\nSTDOUT:\n{first.stdout}\nSTDERR:\n{first.stderr}",
        encoding="utf-8",
    )
    if first.returncode != 0:
        raise RuntimeError("Initial Worker could not persist the pre-revoke checkpoint.")
    before = list_context_provenance(db_path, task_id, "support-a")
    before_selected = [
        item for row in before for item in row.get("selected_memories", [])
        if item.get("memory_id") == candidate["memory_id"]
    ]
    if not before_selected:
        raise RuntimeError("The initial real-401 context did not select its active S1 Memory.")
    before_call_ids = {str(row["call_id"]) for row in before}

    revoked = revoke_memory(
        db_path, str(candidate["memory_id"]), "approver-a",
        idempotency_key=f"m301-recovery-{stamp}-revoke",
    )
    time.sleep(1.2)
    recover_command = [*common]
    recover_command[recover_command.index("pause")] = "recover"
    second = subprocess.run(
        recover_command, cwd=ROOT, text=True, capture_output=True, check=False, timeout=120,
    )
    (output / "worker-after-revoke.log").write_text(
        f"COMMAND: {json.dumps(recover_command)}\nEXIT_CODE: {second.returncode}\nSTDOUT:\n{second.stdout}\nSTDERR:\n{second.stderr}",
        encoding="utf-8",
    )
    if second.returncode != 0:
        raise RuntimeError("Restarted Worker could not resume the persisted Graph checkpoint.")
    worker_before = json.loads(first.stdout.strip().splitlines()[-1])
    worker_after = json.loads(second.stdout.strip().splitlines()[-1])
    after = list_context_provenance(db_path, task_id, "support-a")
    after_revoke = [row for row in after if str(row["call_id"]) not in before_call_ids]
    after_selected = [
        item for row in after_revoke for item in row.get("selected_memories", [])
        if item.get("memory_id") == candidate["memory_id"]
    ]
    with connect(db_path) as connection:
        run = connection.execute(
            "SELECT status, blocked_reason FROM task_runs WHERE run_id = ?", (run_id,),
        ).fetchone()
        observations = connection.execute(
            "SELECT tool_name, status, evidence_id FROM d2_tool_observations WHERE task_id = ? ORDER BY rowid",
            (task_id,),
        ).fetchall()
    checks = {
        "source_task_differs_from_target": str(candidate["source_task_id"]) != task_id,
        "source_memory_was_active_before_revoke": active["state"] == "ACTIVE",
        "real_http_401_persisted_before_worker_checkpoint": int(probe["facts"]["http_status"]) == 401,
        "memory_selected_before_revoke_checkpoint": bool(before_selected),
        "memory_revoked_by_approver": revoked["state"] == "REVOKED",
        "new_worker_process_id": worker_before.get("pid") != worker_after.get("pid"),
        "same_run_resumed_by_new_worker": run is not None and str(run["status"]) in {"SUCCEEDED", "WAITING_INPUT", "INTERRUPTED_RECOVERABLE"},
        "mcp_read_observation_after_resume": any(str(row["status"]) == "OK" for row in observations),
        "pre_revoke_provenance_retained_as_audit": any(
            any(item.get("memory_id") == candidate["memory_id"] for item in row.get("selected_memories", []))
            for row in after if str(row["call_id"]) in before_call_ids
        ),
        "revoked_memory_absent_from_all_post_resume_contexts": not after_selected,
    }
    result = {
        "schema_version": "m301-revoke-worker-recovery-v1",
        "status": "PASS" if all(checks.values()) else "FAIL",
        "model": "deterministic test provider; no external Provider request",
        "mcp": "real MCP stdio worker/client/server and real local HTTP Probe",
        "source_task_id": str(candidate["source_task_id"]),
        "target_task_id": task_id,
        "run_id": run_id,
        "memory_id": str(candidate["memory_id"]),
        "memory_digest": str(candidate["content_digest"]),
        "http_status": int(probe["facts"]["http_status"]),
        "checkpoint_path": str(checkpoint_path),
        "worker_before": worker_before,
        "worker_after": worker_after,
        "run": dict(run) if run is not None else None,
        "mcp_observations": [dict(row) for row in observations],
        "provenance_before": before,
        "provenance_after": after,
        "provenance_after_revoke": after_revoke,
        "checks": checks,
        "runtime_db": str(db_path),
    }
    _write_json(output / "RESULTS.json", result)
    print(json.dumps({
        "event": "m301_revoke_worker_recovery",
        "status": result["status"],
        "checks": checks,
        "source_task_id": result["source_task_id"],
        "target_task_id": task_id,
        "run_id": run_id,
    }, ensure_ascii=False, sort_keys=True), flush=True)
    return 0 if result["status"] == "PASS" else 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-db")
    parser.add_argument("--source-task-id")
    parser.add_argument("--evidence-dir")
    parser.add_argument("--child", choices=("pause", "recover"))
    parser.add_argument("--db")
    parser.add_argument("--checkpoint")
    parser.add_argument("--run-id")
    args = parser.parse_args()
    if args.child:
        if not all((args.db, args.checkpoint, args.run_id)):
            parser.error("--child requires --db, --checkpoint, and --run-id")
        return _child(args.child, Path(args.db), Path(args.checkpoint), str(args.run_id))
    if not all((args.source_db, args.source_task_id, args.evidence_dir)):
        parser.error("orchestrator mode requires --source-db, --source-task-id, and --evidence-dir")
    return run_recovery(args.source_db, args.source_task_id, args.evidence_dir)


if __name__ == "__main__":
    raise SystemExit(main())
