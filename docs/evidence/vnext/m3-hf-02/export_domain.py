"""Read-only whitelist export with no credentials, auth sessions or full Prompts."""
from __future__ import annotations
import hashlib
import json
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path.cwd()
BASE = Path(__file__).resolve().parent
RUNTIME = ROOT / ".runtime/m3-hf-02/journey-01"
label = sys.argv[1]
tables = (
    "d5_memories", "d5_memory_events", "commands", "d3_plans", "d3_plan_authorizations",
    "d3_action_permissions", "d3_plan_control_bindings", "approval_resume_links",
    "integrations", "principals", "auth_policies", "orders", "tickets", "auth_events", "authz_events",
    "task_bindings", "task_controls", "sessions", "messages", "task_runs", "task_run_inputs",
    "task_execution_budgets", "d2_attempts", "d2_model_traces", "d2_tool_observations", "d2_evidence",
    "d5_context_provenance", "semantic_memories", "semantic_memory_events",
    "chat_attempts", "chat_context_manifests", "context_compression_attempts", "context_summaries",
    "context_summary_dependencies", "chat_message_sources", "chat_message_summary_sources", "chat_run_answers",
    "d3_approvals", "d3_action_intents", "d3_action_ledgers", "d3_verification_receipts",
    "d3_report_artifacts", "d3_delivery_records", "s2_handoff_queue_entries", "s2_handoff_receipts",
    "principal_scope_grants", "route_scope_policies", "domain_outbox", "web_worker_state",
)


def sha(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def decoded(row):
    item = dict(row)
    for k, v in list(item.items()):
        if k.endswith("_json") and isinstance(v, str):
            item[k] = json.loads(v)
    return item


result = {"at": datetime.now(timezone.utc).isoformat(), "label": label,
          "checkout_sha": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
          "database_origin": ".runtime/m3-hf-02/journey-01/domain.sqlite3; initialized once, not user DB",
          "raw_prompts_and_auth_values_excluded": True, "tables": {}}
with sqlite3.connect(f"file:{(RUNTIME / 'domain.sqlite3').as_posix()}?mode=ro", uri=True) as d:
    d.row_factory = sqlite3.Row
    existing = {r[0] for r in d.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    for table in tables:
        if table not in existing:
            continue
        rows = [decoded(row) for row in d.execute("SELECT * FROM " + table)]
        for row in rows:
            if table == "messages":
                body = row.pop("body")
                row.update(body_excerpt=body[:180], body_chars=len(body), body_export="BOUNDED_EXCERPT_ONLY")
            if table == "context_compression_attempts":
                sources = row.get("source_dependencies_json", {})
                material = sources.pop("source_material", None)
                if material is not None:
                    sources["source_material_sha256"] = sha(json.dumps(material, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
                    sources["new_message_body_digests"] = [{"sequence": m["sequence"], "role": m["role"], "body_sha256": sha(m["body"])} for m in material.get("new_messages", [])]
                    sources["source_material_omitted"] = True
        result["tables"][table] = rows
with sqlite3.connect(f"file:{(RUNTIME / 'checkpoints.sqlite3').as_posix()}?mode=ro", uri=True) as d:
    d.row_factory = sqlite3.Row
    result["checkpoints"] = [dict(r) for r in d.execute("SELECT thread_id,checkpoint_ns,checkpoint_id,parent_checkpoint_id FROM checkpoints ORDER BY thread_id,checkpoint_id")]
output = BASE / f"runs/journey-01/TRACE-{label}.json"
output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps({"output": str(output), "tables": len(result["tables"])}))
