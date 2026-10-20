"""Read-only export of the synthetic local Web acceptance databases; no auth/credential tables."""
from __future__ import annotations

import hashlib
import json
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

root = Path(__file__).resolve().parents[4]
database, checkpoints, output = map(Path, sys.argv[1:4])
tables = (
    "task_bindings", "task_controls", "sessions", "messages", "task_runs", "task_run_inputs",
    "task_execution_budgets", "d2_attempts", "d2_model_traces", "d2_tool_observations", "d2_evidence",
    "d5_context_provenance", "semantic_memories", "semantic_memory_events",
    "chat_attempts", "chat_context_manifests", "context_compression_attempts", "context_summaries",
    "context_summary_dependencies", "chat_message_sources", "chat_message_summary_sources", "chat_run_answers",
    "d3_approvals", "d3_action_intents", "d3_action_ledgers", "d3_verification_receipts",
    "d3_report_artifacts", "d3_delivery_records", "s2_handoff_queue_entries", "s2_handoff_receipts",
    "principal_scope_grants", "route_scope_policies",
)


def decode_row(row: sqlite3.Row) -> dict:
    item = dict(row)
    for key, value in item.items():
        if key.endswith("_json") and isinstance(value, str):
            item[key] = json.loads(value)
    return item


result = {
    "exported_at": datetime.now(timezone.utc).isoformat(),
    "database": str(database), "checkpoint_database": str(checkpoints),
    "git_head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip(),
    "source_sha256": {
        name: hashlib.sha256((root / name).read_bytes()).hexdigest()
        for name in ("opspilot/domain/chat.py", "opspilot/web/worker.py", "frontend/src/api.ts")
    },
    "authentication_and_credential_tables_excluded": True,
    "tables": {},
}
with sqlite3.connect(f"file:{database.resolve().as_posix()}?mode=ro", uri=True) as db:
    db.row_factory = sqlite3.Row
    for table in tables:
        result["tables"][table] = [decode_row(row) for row in db.execute(f"SELECT * FROM {table}")]
    result["lifecycle_outbox"] = [decode_row(row) for row in db.execute(
        """SELECT * FROM domain_outbox WHERE event_kind IN
           ('RUN_STATUS_INTERRUPTED_RECOVERABLE','RUN_STATUS_FAILED','RUN_STATUS_SUCCEEDED',
            'CONTEXT_SUMMARY_COMMITTED','CHAT_ANSWER_COMMITTED') ORDER BY created_at, event_id"""
    )]
with sqlite3.connect(f"file:{checkpoints.resolve().as_posix()}?mode=ro", uri=True) as db:
    db.row_factory = sqlite3.Row
    result["checkpoint_counts"] = [dict(row) for row in db.execute(
        "SELECT thread_id,COUNT(*) AS persisted_checkpoints FROM checkpoints GROUP BY thread_id"
    )]
output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps({"output": str(output), "table_count": len(tables)}, ensure_ascii=False))
