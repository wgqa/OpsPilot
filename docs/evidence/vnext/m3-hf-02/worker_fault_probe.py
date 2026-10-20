"""Two bounded synthetic failure probes; not historical-cause or real LLM evidence."""
import asyncio
import hashlib
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

ROOT = Path.cwd()
sys.path.insert(0, str(ROOT))
from opspilot.domain.database import reset_fixture
from opspilot.domain.task_control import TaskControlError, create_session, create_task_with_initial_run, trusted_identity
from opspilot.web.worker import SingleInstanceWorker, _process_run

BASE = Path(__file__).resolve().parent
OUT = BASE / "runs/worker-audit-01"
OUT.mkdir(parents=True, exist_ok=True)
RUNTIME = ROOT / ".runtime/m3-hf-02/worker-audit-01"
RUNTIME.mkdir(parents=True, exist_ok=True)
results = []


def snapshot(path, run_id):
    with sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True) as db:
        db.row_factory = sqlite3.Row
        return {
            "run": dict(db.execute("SELECT * FROM task_runs WHERE run_id=?", (run_id,)).fetchone()),
            "retry": dict(db.execute("SELECT * FROM worker_retry_state WHERE run_id=?", (run_id,)).fetchone()),
            "owner": dict(db.execute("SELECT * FROM web_worker_state").fetchone()),
            "outbox": [dict(r) for r in db.execute("SELECT * FROM domain_outbox")],
            "attempt_count": db.execute("SELECT COUNT(*) FROM d2_attempts").fetchone()[0],
            "business_ledger_count": db.execute("SELECT COUNT(*) FROM d3_action_ledgers").fetchone()[0],
        }


for label, error, limit in (("generic-runtime", RuntimeError("SYNTHETIC_PRE_PROVIDER_FAILURE"), 4), ("control-stale", TaskControlError("TASK_CONTROL_STALE"), 1)):
    db = RUNTIME / (label + ".sqlite3")
    if db.exists():
        raise SystemExit("Existing audit fixture protected; do not overwrite or reset prior attempt.")
    reset_fixture(db, "S1_POS")
    actor = trusted_identity(db, "support-a")
    session = create_session(db, actor)
    accepted = create_task_with_initial_run(db, actor, session_id=str(session["session_id"]), service_id="orders-demo", integration_id="integration-a", ticket_id="INC-A-001", initial_message="Bounded worker failure classification probe.", idempotency_key="hf02-" + label)
    worker = SingleInstanceWorker(db)
    worker.acquire()
    worker.register()
    steps = []
    try:
        for step in range(limit):
            with sqlite3.connect(db) as connection:
                connection.row_factory = sqlite3.Row
                run = dict(connection.execute("SELECT * FROM task_runs WHERE run_id=?", (accepted["run_id"],)).fetchone())
            with patch("opspilot.web.worker._process_run_inner", side_effect=error):
                asyncio.run(_process_run(db, RUNTIME / (label + "-checkpoints.sqlite3"), worker.owner_id, "executor-a", run, worker.epoch))
            state = snapshot(db, accepted["run_id"])
            steps.append({"step": step + 1, "at": datetime.now(timezone.utc).isoformat(), **state})
            with (OUT / (label + ".jsonl")).open("a", encoding="utf-8") as f:
                f.write(json.dumps(steps[-1], ensure_ascii=False) + "\n")
        final = steps[-1]
        expected_reason = "WORKER_RETRY_EXHAUSTED" if label == "generic-runtime" else "TASK_CONTROL_STALE"
        assert final["run"]["status"] == "BLOCKED" and final["run"]["blocked_reason"] == expected_reason
        assert final["attempt_count"] == 0 and final["business_ledger_count"] == 0
        results.append({"label": label, "injected_exception_class": type(error).__name__, "steps": len(steps), "status": "PASS", "final": final, "actual_provider_calls": 0, "actual_mcp_calls": 0, "historical_root_cause_proven": False})
    finally:
        worker.release()

historical = ROOT / "docs/evidence/vnext/m3-02-03/runs/m303-final/FAILURE-original-web-task-b.json"
result = {"status": "ROOT_CAUSE_NOT_PROVEN", "synthetic_probes": results,
          "historical_source": str(historical.relative_to(ROOT)), "historical_source_sha256": hashlib.sha256(historical.read_bytes()).hexdigest(),
          "historical_records": json.loads(historical.read_text(encoding="utf-8")),
          "limitation": "Matching generic terminal state and zero attempts proves only that the failure can precede Provider reservation. Old exception class, stack and exact failing boundary are absent. No production code changed."}
(OUT / "RESULTS.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps({"historical_root_cause": "ROOT_CAUSE_NOT_PROVEN", "synthetic_probes_passed": len(results), "real_provider_calls": 0, "real_mcp_calls": 0}))
