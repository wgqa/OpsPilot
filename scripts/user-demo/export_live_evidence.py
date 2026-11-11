"""Export one SUPPORT owner's local C01-B2 test session with secret redaction."""
from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
DB_PATH = ROOT / ".runtime" / "user-demo" / "domain.sqlite3"
EVIDENCE_DIR = ROOT / ".runtime" / "user-demo" / "evidence"
SENSITIVE_KEYS = {
    "api_key", "authorization", "cookie", "set-cookie", "x-csrf-token",
    "access_token", "refresh_token", "password", "secret",
}


def _private_values() -> list[str]:
    from opspilot.config import load_local_environment

    load_local_environment(ROOT / ".env")
    return [
        value for name, value in os.environ.items()
        if name in {"OPSPILOT_MODEL_API_KEY", "OPSPILOT_WEB_SUPPORT_PASSWORD",
                    "OPSPILOT_WEB_APPROVER_PASSWORD"}
        and value
    ]


def _redact(value: Any, secrets: list[str], key: str = "") -> Any:
    if key.lower() in SENSITIVE_KEYS or key.lower().endswith("_token"):
        return "[REDACTED]"
    if isinstance(value, dict):
        return {name: _redact(item, secrets, str(name)) for name, item in value.items()}
    if isinstance(value, list):
        return [_redact(item, secrets) for item in value]
    if not isinstance(value, str):
        return value
    cleaned = value
    for secret in secrets:
        cleaned = cleaned.replace(secret, "[REDACTED]")
    cleaned = re.sub(r"(?i)(Bearer\s+)[A-Za-z0-9._~+/=-]+", r"\1[REDACTED]", cleaned)
    cleaned = re.sub(r"(?i)(sk-[A-Za-z0-9_-]{12,})", "[REDACTED]", cleaned)
    return cleaned


def _json_field(value: Any, secrets: list[str]) -> Any:
    if value is None:
        return None
    if isinstance(value, bytes):
        value = value.decode("utf-8", errors="replace")
    try:
        parsed = json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return _redact(str(value), secrets)
    return _redact(parsed, secrets)


def _rows(connection: sqlite3.Connection, sql: str, params: tuple[Any, ...]) -> list[dict[str, Any]]:
    return [dict(row) for row in connection.execute(sql, params).fetchall()]


def export_session(session_id: str, output: Path) -> dict[str, Any]:
    if not DB_PATH.is_file():
        raise RuntimeError("USER_DEMO_DATABASE_MISSING")
    output = output.resolve()
    root = EVIDENCE_DIR.resolve()
    if output != root and root not in output.parents:
        raise RuntimeError("EVIDENCE_OUTPUT_MUST_STAY_INSIDE_ISOLATED_RUNTIME")
    secrets = _private_values()
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    try:
        session = connection.execute(
            "SELECT session_id,tenant_id,owner_id,created_at,updated_at FROM sessions WHERE session_id=?",
            (session_id,),
        ).fetchone()
        if session is None or (session["tenant_id"], session["owner_id"]) != ("tenant-a", "support-a"):
            raise RuntimeError("SESSION_SCOPE_DENIED")
        run_ids = [str(row[0]) for row in connection.execute(
            "SELECT run_id FROM task_runs WHERE session_id=? ORDER BY created_at,run_id", (session_id,),
        ).fetchall()]
        messages = _rows(connection,
            """SELECT message_id,sequence,role,input_kind,body,body_digest,application_state,
                      applied_run_id,created_at FROM messages WHERE session_id=? ORDER BY sequence""",
            (session_id,),
        )
        jobs = _rows(connection,
            """SELECT job_id,source_start_sequence,source_end_sequence,source_digest,source_refs_json,
                      status,assistant_call_id,attempt_count,replay_attempt_count,proposal_count,
                      written_count,duplicate_count,skipped_count,rejected_count,result_digest,
                      failure_code,created_at,updated_at,completed_at
               FROM personal_memory_consolidation_jobs
               WHERE tenant_id='tenant-a' AND owner_actor_id='support-a' AND session_id=? ORDER BY created_at""",
            (session_id,),
        )
        memories = _rows(connection,
            """SELECT memory_id,memory_kind,memory_mode,memory_key,content,state,version,
                      source_message_id,source_refs_json,creation_source,expires_at,created_at,
                      revoked_at,supersedes_memory_id,supersedes_version
               FROM personal_memories WHERE tenant_id='tenant-a' AND owner_actor_id='support-a'
               ORDER BY created_at,memory_id""", (),
        )
        memory_ids = [str(row["memory_id"]) for row in memories]
        memory_events: list[dict[str, Any]] = []
        if memory_ids:
            marks = ",".join("?" for _ in memory_ids)
            memory_events = _rows(connection,
                f"""SELECT event_id,memory_id,event_type,actor_id,memory_version,occurred_at,details_json
                    FROM personal_memory_events WHERE memory_id IN ({marks}) ORDER BY occurred_at,event_id""",
                tuple(memory_ids),
            )
        placeholders = ",".join("?" for _ in run_ids)
        if run_ids:
            calls = _rows(connection,
                f"""SELECT c.call_id,c.run_id,c.kind,c.logical_key,c.request_json,c.request_digest,
                           c.status,c.result_json,c.usage_json,c.observation_id,c.evidence_id,
                           c.created_at,c.completed_at
                    FROM assistant_calls c WHERE c.run_id IN ({placeholders}) ORDER BY c.created_at,c.call_id""",
                tuple(run_ids),
            )
            chat_attempts = _rows(connection,
                f"""SELECT attempt_id,run_id,attempt_no,model_id,status,provider_response_id,
                           input_tokens,output_tokens,total_tokens,error_class,created_at,completed_at
                    FROM chat_attempts WHERE run_id IN ({placeholders}) ORDER BY created_at,attempt_id""",
                tuple(run_ids),
            )
            manifests = _rows(connection,
                f"""SELECT manifest_id,attempt_id,run_id,selected_message_ids_json,evidence_refs_json,
                           memory_refs_json,model_call_refs_json,excluded_sources_json,truncation_json,
                           trusted_state_digest,prompt_digest,created_at
                    FROM chat_context_manifests WHERE run_id IN ({placeholders}) ORDER BY created_at,manifest_id""",
                tuple(run_ids),
            )
            compressions = _rows(connection,
                f"""SELECT attempt_id,run_id,attempt_no,model_id,prompt_digest,status,
                           source_dependencies_json,estimated_input_tokens,provider_response_id,
                           input_tokens,output_tokens,total_tokens,summary_id,error_class,created_at,completed_at
                    FROM context_compression_attempts WHERE run_id IN ({placeholders}) ORDER BY created_at,attempt_id""",
                tuple(run_ids),
            )
            runs = _rows(connection,
                f"""SELECT run_id,kind,status,source_message_id,created_at,started_at,ended_at,blocked_reason
                    FROM task_runs WHERE run_id IN ({placeholders}) ORDER BY created_at,run_id""",
                tuple(run_ids),
            )
        else:
            calls, chat_attempts, manifests, compressions, runs = [], [], [], [], []
        spends = _rows(connection,
            """SELECT assistant_call_id,run_id,source_message_id,logical_key,price_version,
                      requested_max_output_tokens,reserved_usd_micro,settled_usd_micro,status,
                      response_status,usage_json,completion_id,error_code,created_at,send_granted_at,completed_at
               FROM assistant_runtime_spends WHERE session_id=? ORDER BY created_at,request_key""",
            (session_id,),
        )
    finally:
        connection.close()

    for item in calls:
        for field in ("request_json", "result_json", "usage_json"):
            item[field] = _json_field(item[field], secrets)
    for item in messages:
        item["body"] = _redact(item["body"], secrets)
    for item in jobs:
        item["source_refs_json"] = _json_field(item["source_refs_json"], secrets)
    for item in memories:
        item["source_refs_json"] = _json_field(item["source_refs_json"], secrets)
        item["content"] = _redact(item["content"], secrets)
    for item in memory_events:
        item["details_json"] = _json_field(item["details_json"], secrets)
    for item in manifests:
        for field in ("selected_message_ids_json", "evidence_refs_json", "memory_refs_json",
                      "model_call_refs_json", "excluded_sources_json", "truncation_json"):
            item[field] = _json_field(item[field], secrets)
    for item in compressions:
        item["source_dependencies_json"] = _json_field(item["source_dependencies_json"], secrets)
    for item in spends:
        item["usage_json"] = _json_field(item["usage_json"], secrets)

    from opspilot.domain.assistant_runtime_grant import spend_summary

    payload = {
        "schema": "opspilot-c01-b2-live-redacted-evidence-v1",
        "session": dict(session),
        "runs": runs,
        "messages": messages,
        "chat_attempts": chat_attempts,
        "context_manifests": manifests,
        "compression_attempts": compressions,
        "consolidation_jobs": jobs,
        "personal_memories": memories,
        "personal_memory_events": memory_events,
        "assistant_calls_actual_model_input_output": calls,
        "runtime_spends": spends,
        "runtime_spend_summary": spend_summary(DB_PATH),
        "redaction": {
            "api_key_cookie_authorization_and_configured_passwords_removed": True,
            "generic_bearer_and_sk_token_patterns_removed": True,
            "secret_values_included_in_export": False,
        },
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"output": str(output), "messages": len(messages), "runs": len(runs),
            "jobs": len(jobs), "calls": len(calls), "memories": len(memories)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--session-id", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        result = export_session(args.session_id, args.output)
    except Exception as error:
        print(f"Evidence export failed: {getattr(error, 'code', None) or type(error).__name__}", file=sys.stderr)
        return 2
    print("Redacted evidence export created inside the isolated runtime.")
    print(f"Messages: {result['messages']}; runs: {result['runs']}; consolidation jobs: {result['jobs']}; model calls: {result['calls']}; owner memories: {result['memories']}.")
    print("Secret values and authorization material are not included in this status output.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
