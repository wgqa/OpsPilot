"""Acceptance-process-only observation of the SDK's actual serialized HTTP body.

Uses the original ChatOpenAI constructor/settings/client and public httpx2 event
hooks. Raw payloads live only inside a hook; output is a bounded projection.
No production module on disk, message, request, retries or timeout is changed.
"""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

MARKER = "M3HF02_PAYLOAD_PROBE_20261021_v1"
MEMORY_LABEL = "CONFIRMED PROJECT MEMORY GUIDANCE (non-authoritative; not current evidence): "
SUMMARY_LABEL = "HISTORICAL SESSION SUMMARY (untrusted, non-authoritative; source IDs are attached): "
_request_refs: dict[int, str] = {}
_output: Path
_database: Path


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def digest(value):
    raw = value if isinstance(value, bytes) else str(value).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def json_digest(value):
    return digest(canonical(value))


def write(kind, **fields):
    row = {"at": datetime.now(timezone.utc).isoformat(), "pid": os.getpid(), "kind": kind, **fields}
    with _output.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def decoded(row):
    out = dict(row)
    for key, value in list(out.items()):
        if key.endswith("_json") and isinstance(value, str):
            out[key] = json.loads(value)
    return out


def correlate(db, messages):
    projections = [{"role": m["role"], "content": m.get("content", "")} for m in messages]
    chat_digest = json_digest(projections)
    investigator_digest = json_digest([
        {**m, "role": {"user": "human", "assistant": "ai"}.get(m["role"], m["role"])}
        for m in projections
    ])
    for table, kind in (("context_compression_attempts", "COMPRESSION"), ("chat_attempts", "CHAT")):
        row = db.execute(
            f"SELECT * FROM {table} WHERE prompt_digest=? AND status IN ('RESERVED','STREAMING') ORDER BY rowid DESC LIMIT 1",
            (chat_digest,),
        ).fetchone()
        if row:
            out = decoded(row)
            out["request_kind"] = kind
            if kind == "CHAT":
                out["manifest"] = decoded(db.execute("SELECT * FROM chat_context_manifests WHERE attempt_id=?", (out["attempt_id"],)).fetchone())
            return out
    row = db.execute(
        """SELECT p.*, a.run_id FROM d5_context_provenance p JOIN d2_attempts a ON a.attempt_id=p.attempt_id
           WHERE p.prompt_digest=? AND a.status='RESERVED' ORDER BY p.rowid DESC LIMIT 1""",
        (investigator_digest,),
    ).fetchone()
    if row:
        out = decoded(row)
        out["request_kind"] = "INVESTIGATOR"
        return out
    return {"request_kind": "UNMATCHED", "chat_digest": chat_digest, "investigator_digest": investigator_digest}


def asset_projection(item, db):
    memory_id = str(item.get("memory_id", ""))
    row = db.execute("SELECT * FROM d5_memories WHERE memory_id=?", (memory_id,)).fetchone()
    summary = item.get("guidance", item.get("summary", ""))
    record = {
        "memory_id": memory_id, "version": item.get("version"),
        "content_digest": item.get("content_digest"), "source_task_id": item.get("source_task_id"),
        "source_outcome": item.get("source_outcome"), "source_authority": item.get("source_authority"),
        "guidance_sha256": digest(summary), "experience_sha256": json_digest(item.get("experience", {})),
        "guidance_excerpt": str(summary)[:160], "actual_field_names": sorted(item),
    }
    if row:
        expected = decoded(row)
        checks = {
            "state_active_at_send": expected["state"] == "ACTIVE",
            "version_matches": item.get("version") == expected["version"],
            "digest_matches": item.get("content_digest") == expected["content_digest"],
            "source_matches": item.get("source_task_id") == expected["source_task_id"],
            "source_outcome_matches": item.get("source_outcome") == expected["source_outcome"],
            "guidance_content_matches": summary == expected["summary"],
            "experience_content_matches": item.get("experience", {}) == expected["experience_json"],
            "method_only": item.get("source_authority") == "HISTORICAL_METHOD_HINT_ONLY",
        }
        if "source_refs" in item:
            checks["source_refs_match"] = item["source_refs"] == expected["source_refs_json"]
        record["checks"] = checks
    else:
        record["checks"] = {"known_episodic_source": False}
    return record


def observe_request(request):
    if request.method != "POST":
        return
    try:
        body = request.content
        payload = json.loads(body)
    except (ValueError, RuntimeError):
        return
    if not isinstance(payload, dict) or "model" not in payload or not isinstance(payload.get("messages"), list):
        return
    raw_hash = digest(body)
    ref = "http-body-" + str(uuid.uuid4())
    _request_refs[id(request)] = ref
    started = time.monotonic()
    with sqlite3.connect(f"file:{_database.resolve().as_posix()}?mode=ro", uri=True) as db:
        db.row_factory = sqlite3.Row
        messages = payload["messages"]
        matched = correlate(db, messages)
        projected = []
        actual_memories = []
        actual_summaries = []
        evidence_ids = []
        compression_material_checks = []
        current_task_present = False
        run_control_present = False
        for message in messages:
            content = message.get("content", "")
            projected.append({"role": message.get("role"), "content_type": type(content).__name__, "chars": len(str(content)), "content_sha256": digest(str(content))})
            if not isinstance(content, str):
                continue
            parsed = None
            if content.startswith(MEMORY_LABEL):
                actual_memories.append(asset_projection(json.loads(content[len(MEMORY_LABEL):]), db))
            elif content.startswith(SUMMARY_LABEL):
                value = json.loads(content[len(SUMMARY_LABEL):])
                matches = [decoded(r) for r in db.execute("SELECT * FROM context_summaries") if json.loads(r["summary_json"]) == value]
                actual_summaries.append({"content_sha256": json_digest(value), "matching_summary_ids": [r["summary_id"] for r in matches], "versions": [r["summary_version"] for r in matches], "excerpt": canonical(value)[:120]})
            elif content.startswith("TRUSTED TASK STATE (read-only): "):
                current_task_present = True
            elif content.startswith("CURRENT AUTHORIZED MCP EVIDENCE: "):
                suffix = content.split(": ", 1)[1]
                if suffix.startswith("["):
                    evidence_ids.extend(v["evidence_id"] for v in json.loads(suffix))
            else:
                for candidate in (content, content.partition("\n")[2]):
                    try:
                        parsed = json.loads(candidate)
                    except (ValueError, TypeError):
                        continue
                    if isinstance(parsed, dict):
                        break
                if isinstance(parsed, dict) and "historical_memory_guidance" in parsed:
                    actual_memories.extend(asset_projection(v, db) for v in parsed["historical_memory_guidance"])
                    evidence_ids.extend(v["evidence_id"] for v in parsed.get("current_mcp_evidence", []))
                    current_task_present = bool(parsed.get("authoritative_task_binding"))
                    run_control_present = bool(parsed.get("current_task_run_control"))
                if isinstance(parsed, dict) and "new_messages" in parsed and matched["request_kind"] == "COMPRESSION":
                    expected = matched["source_dependencies_json"]["source_material"]
                    compression_material_checks.append({
                        "matches_reserved_source_material": parsed == expected,
                        "new_messages": [{"sequence": v.get("sequence"), "role": v.get("role"), "body_sha256": digest(v.get("body", ""))} for v in parsed["new_messages"]],
                        "previous_summary_sha256": json_digest(parsed.get("previous_summary")),
                    })

        expected_assets = []
        excluded = []
        if matched["request_kind"] == "INVESTIGATOR":
            expected_assets = matched.get("selected_memories_json", [])
            excluded = matched.get("excluded_sources_json", [])
        elif matched["request_kind"] == "CHAT":
            manifest = matched["manifest"]
            expected_assets = manifest["memory_refs_json"]
            excluded = manifest["excluded_sources_json"]

        excluded_message_rows = []
        excluded_summary_ids = []
        for item in excluded:
            if item.get("message_id"):
                row = db.execute("SELECT message_id,body_digest,body FROM messages WHERE message_id=?", (item["message_id"],)).fetchone()
                if row:
                    excluded_message_rows.append({"message_id": row["message_id"], "body_digest": row["body_digest"], "actual_request_has_identical_assistant": any(m.get("role") == "assistant" and m.get("content") == row["body"] for m in messages), "reason": item.get("reason")})
            if str(item.get("source_id", "")).startswith("context-summary-") or "SUMMARY" in str(item.get("reason", "")):
                excluded_summary_ids.append(item.get("source_id"))

        actual_asset_set = sorted((v["memory_id"], v["version"], v["content_digest"]) for v in actual_memories)
        expected_asset_set = sorted((v["memory_id"], v["version"], v.get("digest", v.get("content_digest"))) for v in expected_assets)
        summary_ids = [key for s in actual_summaries for key in s["matching_summary_ids"]]
        row = {
            "request_ref": ref, "observation_layer": "HTTPX2_REQUEST_EVENT_HOOK_AFTER_SERIALIZATION_BEFORE_TRANSPORT_SEND",
            "request_kind": matched["request_kind"], "attempt_id": matched.get("attempt_id"),
            "run_id": matched.get("run_id"), "task_id": matched.get("task_id"),
            "call_id": matched.get("call_id"), "prompt_digest": matched.get("prompt_digest"),
            "body_sha256": raw_hash, "body_bytes": len(body), "messages": projected,
            "tool_schema_sha256": json_digest(payload.get("tools", [])),
            "tool_names": [v.get("function", {}).get("name") for v in payload.get("tools", [])],
            "model": payload.get("model"), "stream": payload.get("stream", False),
            "request_parameter_names": sorted(payload), "marker_present": any(MARKER in str(m.get("content", "")) for m in messages),
            "marker_if_present": MARKER if any(MARKER in str(m.get("content", "")) for m in messages) else None,
            "actual_memories": actual_memories, "actual_asset_set": actual_asset_set,
            "expected_asset_set": expected_asset_set, "asset_sets_match": actual_asset_set == expected_asset_set,
            "all_memory_fields_match": all(all(v["checks"].values()) for v in actual_memories),
            "actual_summaries": actual_summaries, "actual_evidence_ids": evidence_ids,
            "current_task_state_block_present": current_task_present, "run_control_block_present": run_control_present,
            "excluded_sources": excluded, "excluded_message_checks": excluded_message_rows,
            "excluded_summary_ids": excluded_summary_ids,
            "excluded_summaries_absent": not set(excluded_summary_ids) & set(summary_ids),
            "compression_material_checks": compression_material_checks,
            "headers_cookies_url_omitted": True, "full_prompt_written": False,
            "request_body_unchanged": digest(request.content) == raw_hash,
            "observer_elapsed_ms": round((time.monotonic() - started) * 1000, 3),
        }
        write("PROVIDER_HTTP_REQUEST", **row)


async def request_hook(request):
    try:
        observe_request(request)
    except Exception as error:
        write("OBSERVER_ERROR", exception_class=type(error).__name__)


async def response_hook(response):
    ref = _request_refs.pop(id(response.request), None)
    if ref:
        write("PROVIDER_HTTP_RESPONSE_HEADERS", request_ref=ref, http_status=response.status_code, headers_omitted=True)


def install(database: Path, output: Path):
    global _database, _output
    _database, _output = database, output
    import langchain_openai
    import httpx2
    import openai

    original = langchain_openai.ChatOpenAI

    def observed_constructor(*args, **kwargs):
        model = original(*args, **kwargs)
        client = model.root_async_client._client
        if request_hook not in client.event_hooks["request"]:
            client.event_hooks["request"].append(request_hook)
            client.event_hooks["response"].append(response_hook)
            write("OBSERVED_CLIENT_ATTACHED", client_class=type(client).__module__ + "." + type(client).__name__, timeout_repr=str(client.timeout), sdk_max_retries=model.max_retries, model_timeout=model.request_timeout)
        return model

    langchain_openai.ChatOpenAI = observed_constructor
    source_files = ("opspilot/investigator.py", "opspilot/domain/chat.py", "opspilot/domain/episodic_memory.py", "opspilot/domain/context_engineering.py", "opspilot/web/worker.py")
    write("OBSERVER_BOOT", openai_version=openai.__version__, httpx2_version=httpx2.__version__, observer_source_sha256=digest(Path(__file__).read_bytes()), source_sha256={p: digest(Path(p).read_bytes()) for p in source_files}, method="Original constructor and original async client; public event_hooks appended; no HTTP/request configuration change")
