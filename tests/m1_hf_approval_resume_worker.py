from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("LANGGRAPH_STRICT_MSGPACK", "true")


def _event(name: str, **fields: object) -> None:
    print(json.dumps({"event": name, "pid": os.getpid(), **fields}, sort_keys=True, default=str), flush=True)


def main() -> int:
    if len(sys.argv) != 7:
        raise SystemExit("usage: worker MODE DB CHECKPOINT TASK_ID RUN_ID FAILPOINT")
    _, mode, db_path, checkpoint_path, task_id, run_id, failpoint = sys.argv
    from opspilot.domain import d3
    from opspilot.investigator import run_investigation

    if mode == "recover":
        from opspilot.domain.database import connect
        from opspilot.web.worker import SingleInstanceWorker, _process_run, next_worker_run

        worker = SingleInstanceWorker(db_path)
        worker.acquire()
        worker.register()
        try:
            recovered = asyncio.run(worker.recover_after_exclusive_start())
            _event("hf_approval_resume_recovery_started", recovered_run_ids=recovered,
                   worker_id=worker.owner_id, worker_epoch=worker.epoch)
            deadline = __import__("time").monotonic() + 30
            while __import__("time").monotonic() < deadline:
                with connect(db_path) as conn:
                    row = conn.execute("SELECT status FROM task_runs WHERE run_id = ?", (run_id,)).fetchone()
                if row is not None and str(row["status"]) == "SUCCEEDED":
                    _event("hf_approval_resume_recovered", task_id=task_id, run_id=run_id,
                           status="SUCCEEDED", worker_epoch=worker.epoch)
                    return 0
                selected = next_worker_run(db_path)
                if selected is not None:
                    asyncio.run(_process_run(
                        Path(db_path), Path(checkpoint_path), worker.owner_id, "executor-a",
                        selected, worker.epoch,
                    ))
                else:
                    __import__("time").sleep(0.1)
            _event("hf_approval_resume_recovery_timeout", task_id=task_id, run_id=run_id)
            return 2
        finally:
            worker.release()
    if mode != "crash":
        raise SystemExit(f"unsupported mode: {mode}")

    def crash(name: str, connection=None) -> None:
        if name != failpoint:
            return
        from opspilot.domain.database import connect

        with connect(db_path) as conn:
            repair = conn.execute(
                "SELECT ledger_id, action_id FROM d3_action_ledgers WHERE task_id = ? AND action_kind = 'REPAIR'",
                (task_id,),
            ).fetchone()
            deliver = conn.execute(
                "SELECT ledger_id, action_id FROM d3_action_ledgers WHERE task_id = ? AND action_kind = 'DELIVER'",
                (task_id,),
            ).fetchone()
            delivery = conn.execute(
                "SELECT delivery_id, ticket_entry_id FROM d3_delivery_records WHERE task_id = ?",
                (task_id,),
            ).fetchone()
            counts = {
                "repair_ledgers": int(conn.execute(
                    "SELECT COUNT(*) FROM d3_action_ledgers WHERE task_id = ? AND action_kind = 'REPAIR'",
                    (task_id,),
                ).fetchone()[0]),
                "deliver_ledgers": int(conn.execute(
                    "SELECT COUNT(*) FROM d3_action_ledgers WHERE task_id = ? AND action_kind = 'DELIVER'",
                    (task_id,),
                ).fetchone()[0]),
                "ticket_entries": int(conn.execute(
                    "SELECT COUNT(*) FROM d3_ticket_resolution_entries WHERE task_id = ?", (task_id,)
                ).fetchone()[0]),
                "config_version": int(conn.execute(
                    "SELECT config_version FROM integrations WHERE tenant_id = 'tenant-a' AND integration_id = 'integration-a'"
                ).fetchone()[0]),
            }
        _event(
            "hf_approval_resume_crash_after_commit", failpoint=failpoint,
            in_transaction=bool(connection.in_transaction) if connection is not None else False,
            repair_ledger_id=str(repair["ledger_id"]) if repair else None,
            repair_action_id=str(repair["action_id"]) if repair else None,
            deliver_ledger_id=str(deliver["ledger_id"]) if deliver else None,
            deliver_action_id=str(deliver["action_id"]) if deliver else None,
            delivery_id=str(delivery["delivery_id"]) if delivery else None,
            ticket_entry_id=str(delivery["ticket_entry_id"]) if delivery else None,
            **counts,
        )
        os._exit(87)

    d3._D4_TEST_FAILPOINT = crash
    _event("hf_approval_resume_started", task_id=task_id, run_id=run_id, failpoint=failpoint)
    result = asyncio.run(run_investigation(
        task_id,
        "support-a",
        db_path=Path(db_path),
        checkpoint_db_path=Path(checkpoint_path),
        resume=True,
        d3_mode=True,
        executor_id="executor-a",
        run_id=run_id,
    ))
    _event("hf_approval_resume_returned", task_id=task_id, run_id=run_id,
           stage=result.get("graph_state", {}).get("stage"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
