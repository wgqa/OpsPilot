"""Read-only monitor; terminates only controller-owned API after a real checkpoint."""
import json
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parent
RUNTIME = Path.cwd() / ".runtime/m3-hf-02/journey-01"
task_id = sys.argv[1]
with sqlite3.connect(RUNTIME / "domain.sqlite3") as d:
    if d.execute("SELECT 1 FROM task_bindings WHERE task_id=?", (task_id,)).fetchone() is None:
        raise SystemExit("Monitor target does not exist; no process was terminated.")
    known = {r[0] for r in d.execute("SELECT run_id FROM task_runs WHERE task_id=? AND kind='INVESTIGATE'", (task_id,))}
print("ARMED: same task, only a newly admitted INVESTIGATE Run", flush=True)
deadline = time.monotonic() + 180
while time.monotonic() < deadline:
    with sqlite3.connect(f"file:{(RUNTIME / 'domain.sqlite3').as_posix()}?mode=ro", uri=True) as d:
        d.row_factory = sqlite3.Row
        runs = [dict(r) for r in d.execute("SELECT * FROM task_runs WHERE task_id=? AND kind='INVESTIGATE' AND status='RUNNING'", (task_id,)) if r["run_id"] not in known]
        for run in runs:
            binding = dict(d.execute("SELECT * FROM task_bindings WHERE task_id=?", (task_id,)).fetchone())
            observations = [dict(r) for r in d.execute("SELECT o.observation_id,o.attempt_id,o.evidence_id,o.tool_name,o.status FROM d2_tool_observations o JOIN d2_attempts a ON a.attempt_id=o.attempt_id WHERE a.run_id=?", (run["run_id"],))]
            thread = binding["thread_id"] + "::" + run["run_id"]
            with sqlite3.connect(f"file:{(RUNTIME / 'checkpoints.sqlite3').as_posix()}?mode=ro", uri=True) as cp:
                cp.row_factory = sqlite3.Row
                checkpoints = [dict(r) for r in cp.execute("SELECT thread_id,checkpoint_id,parent_checkpoint_id FROM checkpoints WHERE thread_id=?", (thread,))]
            if not observations or not checkpoints:
                continue
            attempts = [dict(r) for r in d.execute("SELECT * FROM d2_attempts WHERE task_id=?", (task_id,))]
            record = {"at": datetime.now(timezone.utc).isoformat(), "run": run, "binding": binding, "checkpoint_thread": thread, "checkpoints": checkpoints, "observations": observations, "task_attempts": attempts, "business_ledger_count": d.execute("SELECT COUNT(*) FROM d3_action_ledgers").fetchone()[0]}
            (BASE / "runs/journey-01/A-crash-trigger.json").write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
            with (RUNTIME / "commands.jsonl").open("a", encoding="utf-8") as f:
                f.write(json.dumps({"command": "restart", "reason": "A4: same Run crash after current MCP and persisted checkpoint"}) + "\n")
            print(json.dumps({"triggered_run_id": run["run_id"], "thread": thread, "checkpoint_count": len(checkpoints), "current_run_mcp": len(observations)}), flush=True)
            raise SystemExit(0)
    time.sleep(.01)
print("MONITOR_TIMEOUT: no injection happened", flush=True)
raise SystemExit(1)
