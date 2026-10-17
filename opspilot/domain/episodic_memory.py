from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sqlite3
from typing import Any

from opspilot.domain.database import connect
from opspilot.domain.d2 import canonical_json


PROBLEM_TYPE = "auth_401"
MEMORY_SUMMARY = (
    "历史案例提示：先核对主体状态、认证策略、集成配置和真实业务 Probe。"
    "只用当前任务的 MCP Evidence 交给确定性门禁判断；历史经验不代表当前事实、根因或授权。"
)
MAX_MEMORY_RESULTS = 1


class MemoryError(RuntimeError):
    pass


class MemoryScopeDenied(MemoryError):
    pass


class MemorySourceRejected(MemoryError):
    pass


class ContextAssetInvalidated(MemoryError):
    pass


class SkillCompatibilityError(MemoryError):
    pass


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _now_text() -> str:
    return _now().isoformat(timespec="milliseconds")


def _parse_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)


def project_id_for_service(service_id: str) -> str:
    """D5 demo project scope; derived from trusted TaskBinding, never model input."""
    if not service_id or len(service_id) > 64:
        raise ValueError("Invalid trusted service ID.")
    return f"service:{service_id}"


def _row_dict(row: sqlite3.Row) -> dict[str, object]:
    result = dict(row)
    result["source_evidence_ids"] = json.loads(str(result.pop("source_evidence_ids_json")))
    result["applicability_constraints"] = json.loads(str(result.pop("applicability_constraints_json")))
    return result


def _trusted_binding(connection: sqlite3.Connection, task_id: str) -> dict[str, object]:
    row = connection.execute(
        """SELECT b.* FROM task_bindings AS b
           JOIN trusted_operators AS owner ON owner.actor_id = b.actor_id
             AND owner.tenant_id = b.tenant_id AND owner.role = 'SUPPORT'
           WHERE b.task_id = ?""",
        (task_id,),
    ).fetchone()
    if row is None:
        raise MemoryScopeDenied("Trusted TaskBinding is unavailable.")
    return dict(row)


def _require_memory_operator(
    connection: sqlite3.Connection, actor_id: str, tenant_id: str, role: str | None = None
) -> dict[str, object]:
    row = connection.execute(
        "SELECT actor_id, tenant_id, role FROM trusted_operators WHERE actor_id = ?",
        (actor_id,),
    ).fetchone()
    if row is None or str(row["tenant_id"]) != tenant_id:
        raise MemoryScopeDenied("Memory actor is outside the trusted tenant scope.")
    if role is not None and str(row["role"]) != role:
        raise MemoryScopeDenied(f"Memory actor must have {role} role.")
    return dict(row)


def _source_for_task(connection: sqlite3.Connection, task_id: str) -> dict[str, object]:
    binding = _trusted_binding(connection, task_id)
    rows = connection.execute(
        """SELECT l.action_id, l.plan_hash, i.tenant_id, v.verification_id,
                  v.service_id, v.integration_id, v.principal_id, v.business_route,
                  v.response_status, v.business_assertions_json, v.recovery_verified,
                  r.report_ref, r.verification_id AS report_verification_id,
                  r.repair_action_id AS report_repair_action_id, r.report_version,
                  r.content_digest, r.immutable_content_json
           FROM d3_action_ledgers AS l
           JOIN d3_action_intents AS i ON i.action_id = l.action_id
           JOIN d3_verification_receipts AS v ON v.tenant_id = l.tenant_id
             AND v.task_id = l.task_id AND v.plan_hash = l.plan_hash
             AND v.repair_action_id = l.action_id
           JOIN d3_report_artifacts AS r ON r.tenant_id = v.tenant_id
             AND r.task_id = v.task_id AND r.plan_hash = v.plan_hash
             AND r.repair_action_id = v.repair_action_id
             AND r.verification_id = v.verification_id
           WHERE l.tenant_id = ? AND l.task_id = ? AND l.action_kind = 'REPAIR'
             AND l.status = 'COMMITTED' AND v.recovery_verified = 1
             AND v.response_status = 200
           ORDER BY r.created_at DESC, l.committed_at DESC""",
        (binding["tenant_id"], task_id),
    ).fetchall()
    accepted: list[dict[str, object]] = []
    for raw in rows:
        row = dict(raw)
        if row["tenant_id"] != binding["tenant_id"]:
            continue
        if (row["service_id"], row["integration_id"], row["principal_id"]) != (
            binding["service_id"], binding["integration_id"], binding["principal_id"]
        ):
            continue
        route = connection.execute(
            "SELECT route FROM services WHERE tenant_id = ? AND service_id = ?",
            (binding["tenant_id"], binding["service_id"]),
        ).fetchone()
        if route is None or row["business_route"] != route["route"]:
            continue
        try:
            assertions = json.loads(str(row["business_assertions_json"]))
            report = json.loads(str(row["immutable_content_json"]))
        except (json.JSONDecodeError, TypeError):
            continue
        digest = hashlib.sha256(str(row["immutable_content_json"]).encode("utf-8")).hexdigest()
        if digest != row["content_digest"] or row["report_verification_id"] != row["verification_id"]:
            continue
        if row["report_repair_action_id"] != row["action_id"] or int(row["report_version"]) != 1:
            continue
        if report.get("schema_version") != "opspilot-d3-report-v1" or report.get("business_outcome") != "RECOVERED":
            continue
        if report.get("task_id") != task_id or report.get("tenant_id") != binding["tenant_id"]:
            continue
        report_ledger = report.get("repair_ledger")
        report_receipt = report.get("verification_receipt")
        if not isinstance(report_ledger, dict) or report_ledger.get("status") != "COMMITTED" or report_ledger.get("action_id") != row["action_id"]:
            continue
        if not isinstance(report_receipt, dict) or (
            report_receipt.get("verification_id") != row["verification_id"]
            or report_receipt.get("recovery_verified") not in (True, 1)
            or report_receipt.get("response_status") != 200
        ):
            continue
        if report.get("plan_hash") != row["plan_hash"]:
            continue
        if not all(assertions.get(key) is True for key in (
            "same_tenant", "same_service", "same_integration", "same_principal",
            "same_business_route", "order_id_matches", "order_status_matches",
            "expected_post_repair_versions",
        )):
            continue
        response_body = assertions.get("response_body")
        if not isinstance(response_body, dict) or response_body.get("order_id") != "demo-order" or response_body.get("status") != "CONFIRMED":
            continue
        if int(report.get("verification_receipt", {}).get("response_status", 0)) != 200:
            continue
        evidence = report.get("evidence")
        if not isinstance(evidence, list):
            continue
        evidence_ids = list(dict.fromkeys(
            str(item.get("evidence_id")) for item in evidence
            if isinstance(item, dict) and isinstance(item.get("evidence_id"), str)
        ))
        if not evidence_ids:
            continue
        evidence_rows = connection.execute(
            """SELECT evidence_id, tenant_id, task_id FROM d2_evidence
               WHERE tenant_id = ? AND task_id = ? AND evidence_id IN (%s)"""
            % ",".join("?" for _ in evidence_ids),
            (binding["tenant_id"], task_id, *evidence_ids),
        ).fetchall()
        if len(evidence_rows) != len(evidence_ids):
            continue
        accepted.append({
            "tenant_id": str(binding["tenant_id"]),
            "project_id": project_id_for_service(str(binding["service_id"])),
            "problem_type": PROBLEM_TYPE,
            "source_task_id": task_id,
            "source_evidence_ids": evidence_ids,
            "source_report_ref": str(row["report_ref"]),
            "source_verification_id": str(row["verification_id"]),
            "source_repair_action_id": str(row["action_id"]),
        })
    if not accepted:
        raise MemorySourceRejected(
            "Memory requires a committed same-task REPAIR, verified online 200, frozen report, and checkable Evidence."
        )
    return accepted[0]


def _memory_source_still_valid(connection: sqlite3.Connection, row: sqlite3.Row | dict[str, object]) -> bool:
    memory = dict(row)
    try:
        source = _source_for_task(connection, str(memory["source_task_id"]))
        ids = json.loads(str(memory["source_evidence_ids_json"]))
    except (MemoryError, json.JSONDecodeError, KeyError, TypeError):
        return False
    return bool(
        source["tenant_id"] == memory["tenant_id"]
        and source["project_id"] == memory["project_id"]
        and source["source_report_ref"] == memory["source_report_ref"]
        and source["source_verification_id"] == memory["source_verification_id"]
        and ids == source["source_evidence_ids"]
    )


def _record_memory_event(
    connection: sqlite3.Connection,
    *,
    memory_id: str,
    tenant_id: str,
    project_id: str,
    event_type: str,
    actor_id: str,
    version: int,
    details: dict[str, object] | None = None,
) -> None:
    connection.execute(
        """INSERT INTO d5_memory_events
           (event_id, memory_id, tenant_id, project_id, event_type, actor_id,
            memory_version, occurred_at, details_json)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (f"memory-event-{uuid.uuid4()}", memory_id, tenant_id, project_id,
         event_type, actor_id, version, _now_text(), canonical_json(details or {})),
    )


def create_memory_candidate(
    path: str | Path,
    source_task_id: str,
    trusted_actor: str,
    *,
    ttl_days: int = 30,
) -> dict[str, object]:
    if not 1 <= ttl_days <= 30:
        raise ValueError("D5 memory lifetime must be between 1 and 30 days.")
    with connect(path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        binding = _trusted_binding(connection, source_task_id)
        _require_memory_operator(connection, trusted_actor, str(binding["tenant_id"]))
        project_id = project_id_for_service(str(binding["service_id"]))
        existing = connection.execute(
            """SELECT * FROM d5_memories WHERE tenant_id = ? AND project_id = ?
               AND problem_type = ? AND source_task_id = ?""",
            (binding["tenant_id"], project_id, PROBLEM_TYPE, source_task_id),
        ).fetchone()
        if existing is not None:
            return _row_dict(existing)
        source = _source_for_task(connection, source_task_id)
        memory_id = f"episodic-{uuid.uuid4()}"
        created_at = _now_text()
        expires_at = (_now() + timedelta(days=ttl_days)).isoformat(timespec="milliseconds")
        constraints = {
            "problem_type": PROBLEM_TYPE,
            "service_id": str(binding["service_id"]),
            "required_current_mcp_facts": [
                "endpoint_probe", "principal_status", "auth_policy", "integration_config"
            ],
        }
        connection.execute(
            """INSERT INTO d5_memories
               (memory_id, tenant_id, project_id, type, problem_type, summary,
                applicability_constraints_json, source_task_id, source_evidence_ids_json,
                source_report_ref, source_verification_id, state, version,
                expires_at, created_at)
               VALUES (?, ?, ?, 'EPISODIC', ?, ?, ?, ?, ?, ?, ?, 'CANDIDATE', 1, ?, ?)""",
            (memory_id, source["tenant_id"], source["project_id"], PROBLEM_TYPE,
             MEMORY_SUMMARY, canonical_json(constraints), source_task_id,
             canonical_json(source["source_evidence_ids"]), source["source_report_ref"],
             source["source_verification_id"], expires_at, created_at),
        )
        _record_memory_event(
            connection, memory_id=memory_id, tenant_id=str(source["tenant_id"]),
            project_id=str(source["project_id"]), event_type="CANDIDATE_CREATED",
            actor_id=trusted_actor, version=1,
            details={"source_task_id": source_task_id, "problem_type": PROBLEM_TYPE},
        )
        row = connection.execute("SELECT * FROM d5_memories WHERE memory_id = ?", (memory_id,)).fetchone()
    return _row_dict(row)


def confirm_memory(path: str | Path, memory_id: str, actor_id: str) -> dict[str, object]:
    with connect(path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute("SELECT * FROM d5_memories WHERE memory_id = ?", (memory_id,)).fetchone()
        if row is None:
            raise MemorySourceRejected("Memory record does not exist.")
        _require_memory_operator(connection, actor_id, str(row["tenant_id"]), "APPROVER")
        if row["state"] == "ACTIVE":
            return _row_dict(row)
        if row["state"] != "CANDIDATE":
            raise MemorySourceRejected("Only a CANDIDATE memory can be activated; revoked versions never revive.")
        if _parse_time(str(row["expires_at"])) <= _now():
            raise MemorySourceRejected("Expired candidates cannot be activated.")
        if not _memory_source_still_valid(connection, row):
            raise MemorySourceRejected("Memory source is no longer checkable.")
        version = int(row["version"]) + 1
        confirmed_at = _now_text()
        connection.execute(
            """UPDATE d5_memories SET state = 'ACTIVE', version = ?, confirmed_by = ?,
               confirmed_at = ? WHERE memory_id = ? AND state = 'CANDIDATE'""",
            (version, actor_id, confirmed_at, memory_id),
        )
        _record_memory_event(
            connection, memory_id=memory_id, tenant_id=str(row["tenant_id"]),
            project_id=str(row["project_id"]), event_type="CONFIRMED",
            actor_id=actor_id, version=version,
        )
        updated = connection.execute("SELECT * FROM d5_memories WHERE memory_id = ?", (memory_id,)).fetchone()
    return _row_dict(updated)


def revoke_memory(path: str | Path, memory_id: str, actor_id: str) -> dict[str, object]:
    with connect(path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute("SELECT * FROM d5_memories WHERE memory_id = ?", (memory_id,)).fetchone()
        if row is None:
            raise MemorySourceRejected("Memory record does not exist.")
        _require_memory_operator(connection, actor_id, str(row["tenant_id"]), "APPROVER")
        if row["state"] == "REVOKED":
            return _row_dict(row)
        if row["state"] != "ACTIVE":
            raise MemorySourceRejected("Only ACTIVE memory can be revoked.")
        version = int(row["version"]) + 1
        revoked_at = _now_text()
        connection.execute(
            """UPDATE d5_memories SET state = 'REVOKED', version = ?, revoked_by = ?,
               revoked_at = ? WHERE memory_id = ? AND state = 'ACTIVE'""",
            (version, actor_id, revoked_at, memory_id),
        )
        _record_memory_event(
            connection, memory_id=memory_id, tenant_id=str(row["tenant_id"]),
            project_id=str(row["project_id"]), event_type="REVOKED",
            actor_id=actor_id, version=version,
        )
        updated = connection.execute("SELECT * FROM d5_memories WHERE memory_id = ?", (memory_id,)).fetchone()
    return _row_dict(updated)


def _memory_is_applicable(row: sqlite3.Row, *, problem_type: str, now: datetime) -> bool:
    if row["state"] != "ACTIVE" or row["problem_type"] != problem_type:
        return False
    if _parse_time(str(row["expires_at"])) <= now:
        return False
    try:
        constraints = json.loads(str(row["applicability_constraints_json"]))
    except json.JSONDecodeError:
        return False
    return constraints.get("problem_type") == problem_type and len(str(row["summary"])) <= 480


def list_applicable_memories(
    path: str | Path,
    task_id: str,
    problem_type: str,
    *,
    limit: int = MAX_MEMORY_RESULTS,
) -> list[dict[str, object]]:
    if not 1 <= limit <= 3:
        raise ValueError("D5 memory retrieval is limited to at most three records.")
    with connect(path) as connection:
        binding = _trusted_binding(connection, task_id)
        project_id = project_id_for_service(str(binding["service_id"]))
        rows = connection.execute(
            """SELECT * FROM d5_memories WHERE tenant_id = ? AND project_id = ?
               AND problem_type = ? AND state = 'ACTIVE' ORDER BY confirmed_at, memory_id""",
            (binding["tenant_id"], project_id, problem_type),
        ).fetchall()
        now = _now()
        results = []
        for row in rows:
            if not _memory_is_applicable(row, problem_type=problem_type, now=now):
                continue
            if not _memory_source_still_valid(connection, row):
                continue
            item = _row_dict(row)
            item["summary"] = str(item["summary"])[:480]
            results.append(item)
            if len(results) >= limit:
                break
    return results


def insert_context_provenance_in_transaction(
    connection: sqlite3.Connection,
    *,
    task_id: str,
    attempt_id: str,
    model_id: str,
    prompt_version: str,
    prompt_digest: str,
    tool_schema_version: str,
    tool_schema_digest: str,
    selected_skill: dict[str, str] | None,
    selected_memories: list[dict[str, object]],
    evidence_ids: list[str],
) -> str:
    """Validate current memory rows and register provenance in reserve_attempt's transaction."""
    binding = _trusted_binding(connection, task_id)
    project_id = project_id_for_service(str(binding["service_id"]))
    memory_refs: list[dict[str, object]] = []
    for selected in selected_memories:
        memory_id = str(selected.get("memory_id", ""))
        try:
            version = int(selected.get("version", 0))
        except (TypeError, ValueError):
            raise ContextAssetInvalidated("Selected memory version is invalid.")
        row = connection.execute("SELECT * FROM d5_memories WHERE memory_id = ?", (memory_id,)).fetchone()
        if (
            row is None
            or row["state"] != "ACTIVE"
            or int(row["version"]) != version
            or row["tenant_id"] != binding["tenant_id"]
            or row["project_id"] != project_id
            or _parse_time(str(row["expires_at"])) <= _now()
            or not _memory_source_still_valid(connection, row)
        ):
            raise ContextAssetInvalidated("Selected memory is no longer active in this TaskBinding scope.")
        if str(selected.get("summary", "")) != str(row["summary"]):
            raise ContextAssetInvalidated("Selected memory content changed after prompt construction.")
        memory_refs.append({"memory_id": memory_id, "version": version})
    if selected_skill is not None and not all(selected_skill.get(key) for key in ("name", "version", "digest")):
        raise ContextAssetInvalidated("Selected Skill provenance is incomplete.")
    call_id = str(connection.execute(
        "SELECT call_id FROM d2_attempts WHERE attempt_id = ? AND task_id = ? AND kind = 'MODEL'",
        (attempt_id, task_id),
    ).fetchone()["call_id"])
    connection.execute(
        """INSERT INTO d5_context_provenance
           (call_id, task_id, attempt_id, model_id, prompt_version, prompt_digest,
            tool_schema_version, tool_schema_digest, selected_skill_name,
            selected_skill_version, selected_skill_digest, selected_memories_json,
            evidence_ids_json, built_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (call_id, task_id, attempt_id, model_id, prompt_version, prompt_digest,
         tool_schema_version, tool_schema_digest,
         selected_skill.get("name") if selected_skill else None,
         selected_skill.get("version") if selected_skill else None,
         selected_skill.get("digest") if selected_skill else None,
         canonical_json(memory_refs), canonical_json(evidence_ids), _now_text()),
    )
    return call_id


def finish_context_provenance(
    path: str | Path, call_id: str, status: str, error_class: str | None = None
) -> None:
    with connect(path) as connection:
        connection.execute(
            """UPDATE d5_context_provenance SET model_status = ?, completed_at = ?,
               error_class = ? WHERE call_id = ?""",
            (status[:64], _now_text(), error_class[:128] if error_class else None, call_id),
        )


def assert_task_skill_compatible(
    path: str | Path, task_id: str, selected_skill: dict[str, str] | None
) -> None:
    current = (
        (selected_skill.get("name"), selected_skill.get("version"), selected_skill.get("digest"))
        if selected_skill else (None, None, None)
    )
    with connect(path) as connection:
        _trusted_binding(connection, task_id)
        rows = connection.execute(
            """SELECT DISTINCT selected_skill_name, selected_skill_version, selected_skill_digest
               FROM d5_context_provenance WHERE task_id = ? AND selected_skill_name IS NOT NULL""",
            (task_id,),
        ).fetchall()
    if any((row["selected_skill_name"], row["selected_skill_version"], row["selected_skill_digest"]) != current for row in rows):
        raise SkillCompatibilityError("The Skill version or digest changed during this task; stop and review before continuing.")


def list_context_provenance(
    path: str | Path, task_id: str, actor_id: str
) -> list[dict[str, object]]:
    with connect(path) as connection:
        binding = _trusted_binding(connection, task_id)
        operator = _require_memory_operator(connection, actor_id, str(binding["tenant_id"]))
        if operator["role"] == "SUPPORT" and binding["actor_id"] != actor_id:
            raise MemoryScopeDenied("Only the task owner or a same-tenant approver can read Context Provenance.")
        rows = connection.execute(
            """SELECT p.*, t.prompt_digest AS model_trace_prompt_digest,
                      t.status AS trace_status, t.provider_response_id
               FROM d5_context_provenance AS p
               LEFT JOIN d2_model_traces AS t ON t.call_id = p.call_id AND t.task_id = p.task_id
               WHERE p.task_id = ? ORDER BY p.built_at, p.call_id""",
            (task_id,),
        ).fetchall()
    results = []
    for raw in rows:
        item = dict(raw)
        item["selected_memories"] = json.loads(str(item.pop("selected_memories_json")))
        item["evidence_ids"] = json.loads(str(item.pop("evidence_ids_json")))
        item["prompt_digest_matches_trace"] = item.get("model_trace_prompt_digest") in (None, item["prompt_digest"])
        results.append(item)
    return results
