from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from opspilot.domain.execution_budget import begin_execution_interval
from opspilot.domain.task_control import claim_task_run, register_worker_owner, trusted_identity
from opspilot.web.worker import SingleInstanceWorker


def main() -> int:
    db_path, run_id, task_id = sys.argv[1:]
    worker = SingleInstanceWorker(db_path)
    worker.acquire()
    worker.epoch = register_worker_owner(db_path, worker.owner_id, os.getpid())
    identity = trusted_identity(db_path, "support-a")
    claimed = claim_task_run(db_path, identity, run_id)
    remaining = begin_execution_interval(db_path, task_id, default_deadline_ms=60_000)
    print(json.dumps({"event": "RUNNING", "pid": os.getpid(), "run_id": run_id,
                      "status": claimed["status"], "remaining_ms": remaining,
                      "worker_id": worker.owner_id}, sort_keys=True), flush=True)
    time.sleep(120)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
