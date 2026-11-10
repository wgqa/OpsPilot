from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from opspilot.domain.database import connect
from opspilot.domain.episodic_memory import (
    MemoryIdempotencyConflict,
    MemoryScopeDenied,
    MemorySourceRejected,
    _now,
    _now_text,
    _parse_time,
    _require_memory_operator,
    _trusted_binding,
    project_id_for_service,
)


SEMANTIC_MEMORY_KINDS = {"ALIAS", "INTERFACE_CONVENTION", "WORK_CONSTRAINT"}
SEMANTIC_MEMORY_STATES = {"CANDIDATE", "ACTIVE", "REVISED", "REVOKED", "EXPIRED"}
MAX_SEMANTIC_RESULTS = 3
_SENSITIVE_TEXT = re.compile(
    r"(?i)(?:\bbearer\s+\S+|\b(?:api[_ -]?key|password|passwd|secret|credential(?:[_ -]?ref)?|access[_ -]?token)\b\s*[:=])"
)
PERSONAL_MEMORY_KINDS = {"PREFERENCE", "WORK_HABIT", "PROJECT_BACKGROUND"}
PERSONAL_MEMORY_LIMIT = 3
_MEMORY_TOKEN = re.compile(r"[a-z0-9]{2,}|[\u4e00-\u9fff]+", re.IGNORECASE)
_MEMORY_STOPWORDS = {
    "about", "also", "answer", "answers", "can", "could", "for", "from", "have",
    "help", "into", "just", "please", "project", "remember", "save", "should",
    "that", "this", "with", "would", "you", "your", "使用", "保存", "偏好",
    "信息", "内容", "希望", "当前", "可以", "我们", "我的", "记住", "请用",
    "表示", "是否", "已经", "完成", "处理", "这些", "之前", "这里", "说明",
    "问题", "根据", "什么", "需要", "可能", "相关", "资料", "方法", "如何",
    "应该", "一下", "用户", "场景", "情况", "时候", "这个", "那个", "作为",
}


class SemanticMemoryConflict(RuntimeError):
    pass


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _digest(value: Any) -> str:
    payload = value if isinstance(value, str) else _canonical(value)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _row_dict(row: sqlite3.Row | dict[str, Any]) -> dict[str, Any]:
    item = dict(row)
    item["source_refs"] = json.loads(str(item.pop("source_refs_json")))
    item["source_authority"] = "CONFIRMED_PROJECT_CONTEXT_ONLY"
    return item


def _event(
    connection: sqlite3.Connection,
    row: sqlite3.Row | dict[str, Any],
    *,
    event_type: str,
    actor_id: str,
    version: int,
    details: dict[str, Any] | None = None,
) -> None:
    item = dict(row)
    connection.execute(
        """INSERT INTO semantic_memory_events
           (event_id, memory_id, tenant_id, project_id, event_type, actor_id,
            memory_version, occurred_at, details_json)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (f"semantic-event-{uuid.uuid4()}", item["memory_id"], item["tenant_id"],
         item["project_id"], event_type, actor_id, version, _now_text(),
         _canonical(details or {})),
    )


def _find_command(
    connection: sqlite3.Connection,
    *,
    tenant_id: str,
    actor_id: str,
    idempotency_key: str,
    command_kind: str,
    target_ref: str,
    request_digest: str,
) -> dict[str, Any] | None:
    row = connection.execute(
        """SELECT command_kind, target_ref, request_digest, result_json
           FROM semantic_memory_commands
           WHERE tenant_id = ? AND actor_id = ? AND idempotency_key = ?""",
        (tenant_id, actor_id, idempotency_key),
    ).fetchone()
    if row is None:
        return None
    if (
        str(row["command_kind"]) != command_kind
        or str(row["target_ref"]) != target_ref
        or str(row["request_digest"]) != request_digest
    ):
        raise MemoryIdempotencyConflict("IDEMPOTENCY_KEY_REUSED_WITH_DIFFERENT_REQUEST")
    return json.loads(str(row["result_json"]))


def _record_command(
    connection: sqlite3.Connection,
    *,
    tenant_id: str,
    actor_id: str,
    idempotency_key: str,
    command_kind: str,
    target_ref: str,
    request_digest: str,
    result: dict[str, Any],
) -> None:
    connection.execute(
        """INSERT INTO semantic_memory_commands
           (command_id, tenant_id, actor_id, idempotency_key, command_kind,
            target_ref, request_digest, result_json, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (f"semantic-command-{uuid.uuid4()}", tenant_id, actor_id, idempotency_key,
         command_kind, target_ref, request_digest, _canonical(result), _now_text()),
    )


def _scope_for_binding(binding: dict[str, Any]) -> str:
    return project_id_for_service(str(binding["service_id"]))


def _check_source(
    connection: sqlite3.Connection,
    *,
    task_id: str,
    tenant_id: str,
    project_id: str,
    refs: list[dict[str, Any]],
) -> bool:
    binding = connection.execute(
        "SELECT tenant_id, service_id FROM task_bindings WHERE task_id = ?", (task_id,),
    ).fetchone()
    if (
        binding is None
        or str(binding["tenant_id"]) != tenant_id
        or project_id_for_service(str(binding["service_id"])) != project_id
        or len(refs) != 1
    ):
        return False
    ref = refs[0]
    if ref.get("kind") != "MESSAGE":
        return False
    message = connection.execute(
        """SELECT tenant_id, task_id, role, input_kind, body_digest
           FROM messages WHERE message_id = ?""",
        (str(ref.get("id", "")),),
    ).fetchone()
    return bool(
        message is not None
        and str(message["tenant_id"]) == tenant_id
        and str(message["task_id"]) == task_id
        and str(message["role"]) == "USER"
        and str(message["input_kind"]) in {"CHAT_READONLY", "CORRECT_TASK_INPUT"}
        and str(message["body_digest"]) == str(ref.get("digest", ""))
    )


def _source_is_current(connection: sqlite3.Connection, row: sqlite3.Row | dict[str, Any]) -> bool:
    item = dict(row)
    try:
        refs = json.loads(str(item["source_refs_json"]))
    except (KeyError, TypeError, json.JSONDecodeError):
        return False
    if not isinstance(refs, list):
        return False
    content = {
        "memory_kind": str(item["memory_kind"]),
        "memory_key": str(item["memory_key"]),
        "content": str(item["content"]),
        "source_refs": refs,
    }
    return (
        str(item.get("content_digest", "")) == _digest(content)
        and _check_source(
            connection, task_id=str(item["source_task_id"]), tenant_id=str(item["tenant_id"]),
            project_id=str(item["project_id"]), refs=refs,
        )
    )


def _validate_proposal(memory_kind: str, memory_key: str, content: str) -> tuple[str, str, str]:
    kind = memory_kind.strip().upper()
    key = " ".join(memory_key.split())
    value = " ".join(content.split())
    if kind not in SEMANTIC_MEMORY_KINDS:
        raise MemorySourceRejected("Unsupported Semantic Memory kind.")
    if not key or len(key) > 120 or not value or len(value) > 800:
        raise MemorySourceRejected("Semantic Memory key or content is outside the allowed length.")
    if _SENSITIVE_TEXT.search(key + " " + value):
        raise MemorySourceRejected("Secret-like content cannot be stored as Semantic Memory.")
    return kind, key, value


def create_semantic_candidate(
    path: str | Path,
    task_id: str,
    actor_id: str,
    *,
    memory_kind: str,
    memory_key: str,
    content: str,
    source_message_id: str,
    ttl_days: int = 90,
    idempotency_key: str,
    supersedes_memory_id: str | None = None,
    expected_version: int | None = None,
) -> dict[str, Any]:
    if not idempotency_key.strip() or len(idempotency_key) > 200:
        raise MemoryIdempotencyConflict("IDEMPOTENCY_KEY_REQUIRED")
    if not 1 <= ttl_days <= 365:
        raise MemorySourceRejected("Semantic Memory lifetime must be between 1 and 365 days.")
    kind, key, value = _validate_proposal(memory_kind, memory_key, content)
    with connect(path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        binding = _trusted_binding(connection, task_id)
        operator = _require_memory_operator(connection, actor_id, str(binding["tenant_id"]), "SUPPORT")
        if actor_id != str(binding["actor_id"]):
            raise MemoryScopeDenied("Only the trusted Task owner may propose project Semantic Memory.")
        source = connection.execute(
            """SELECT message_id, tenant_id, task_id, role, input_kind, body_digest
               FROM messages WHERE message_id = ?""",
            (source_message_id,),
        ).fetchone()
        project_id = _scope_for_binding(binding)
        if (
            source is None or str(source["tenant_id"]) != str(binding["tenant_id"])
            or str(source["task_id"]) != task_id or str(source["role"]) != "USER"
            or str(source["input_kind"]) not in {"CHAT_READONLY", "CORRECT_TASK_INPUT"}
        ):
            raise MemorySourceRejected("Semantic proposal source must be a persisted user message on this Task.")
        _expire_scope(connection, str(binding["tenant_id"]), project_id)
        refs = [{"kind": "MESSAGE", "id": source_message_id, "digest": str(source["body_digest"])}]
        request_payload = {
            "task_id": task_id, "memory_kind": kind, "memory_key": key, "content": value,
            "source_message_id": source_message_id, "ttl_days": ttl_days,
            "supersedes_memory_id": supersedes_memory_id, "expected_version": expected_version,
        }
        request_digest = _digest(request_payload)
        replay = _find_command(
            connection, tenant_id=str(operator["tenant_id"]), actor_id=actor_id,
            idempotency_key=idempotency_key, command_kind="SEMANTIC_CANDIDATE_CREATE",
            target_ref=task_id, request_digest=request_digest,
        )
        if replay is not None:
            return replay
        active = None
        if supersedes_memory_id is not None:
            active = connection.execute(
                """SELECT * FROM semantic_memories WHERE memory_id = ? AND tenant_id = ?
                   AND project_id = ? AND state = 'ACTIVE'""",
                (supersedes_memory_id, binding["tenant_id"], project_id),
            ).fetchone()
            if (
                active is None or expected_version is None
                or int(active["version"]) != expected_version
                or str(active["memory_kind"]) != kind or str(active["memory_key"]) != key
                or _parse_time(str(active["expires_at"])) <= _now()
                or not _source_is_current(connection, active)
            ):
                raise MemorySourceRejected("Semantic revision target is stale, expired, or outside this project.")
            if str(active["content"]) == value:
                raise MemorySourceRejected("A Semantic revision must change the proposed content.")
            version = int(active["version"]) + 1
        else:
            active = connection.execute(
                """SELECT memory_id FROM semantic_memories WHERE tenant_id = ? AND project_id = ?
                   AND memory_kind = ? AND memory_key = ? AND state = 'ACTIVE'""",
                (binding["tenant_id"], project_id, kind, key),
            ).fetchone()
            if active is not None:
                raise SemanticMemoryConflict("An active Semantic Memory already uses this key; submit an explicit versioned revision.")
            version = 1
        memory_id = f"semantic-{uuid.uuid4()}"
        created_at = _now_text()
        expires_at = (_now() + timedelta(days=ttl_days)).isoformat(timespec="milliseconds")
        content_payload = {"memory_kind": kind, "memory_key": key, "content": value, "source_refs": refs}
        content_digest = _digest(content_payload)
        connection.execute(
            """INSERT INTO semantic_memories
               (memory_id, tenant_id, project_id, memory_kind, memory_key, content,
                content_digest, source_task_id, source_refs_json, state, version,
                supersedes_memory_id, supersedes_version, created_by, expires_at, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'CANDIDATE', ?, ?, ?, ?, ?, ?)""",
            (memory_id, str(binding["tenant_id"]), project_id, kind, key, value,
             content_digest, task_id, _canonical(refs), version,
             supersedes_memory_id, expected_version, actor_id, expires_at, created_at),
        )
        row = connection.execute("SELECT * FROM semantic_memories WHERE memory_id = ?", (memory_id,)).fetchone()
        _event(connection, row, event_type="CANDIDATE_CREATED", actor_id=actor_id, version=version,
               details={"source_message_id": source_message_id, "content_digest": content_digest,
                        "supersedes_memory_id": supersedes_memory_id, "scope": "PROJECT"})
        result = _row_dict(row)
        _record_command(
            connection, tenant_id=str(operator["tenant_id"]), actor_id=actor_id,
            idempotency_key=idempotency_key, command_kind="SEMANTIC_CANDIDATE_CREATE",
            target_ref=task_id, request_digest=request_digest, result=result,
        )
    return result


def _validate_approver_scope(
    connection: sqlite3.Connection, row: sqlite3.Row, actor_id: str,
) -> None:
    operator = _require_memory_operator(connection, actor_id, str(row["tenant_id"]), "APPROVER")
    binding = _trusted_binding(connection, str(row["source_task_id"]))
    if (
        str(operator["tenant_id"]) != str(row["tenant_id"])
        or _scope_for_binding(binding) != str(row["project_id"])
    ):
        raise MemoryScopeDenied("Approver is not authorized for the TaskBinding-derived project scope.")
    grant = connection.execute(
        """SELECT 1 FROM semantic_memory_project_approvers
           WHERE tenant_id = ? AND project_id = ? AND actor_id = ? AND active = 1""",
        (row["tenant_id"], row["project_id"], actor_id),
    ).fetchone()
    if grant is None:
        raise MemoryScopeDenied("Approver does not hold a current project Semantic Memory grant.")


def confirm_semantic_memory(
    path: str | Path, memory_id: str, actor_id: str, *, idempotency_key: str,
) -> dict[str, Any]:
    if not idempotency_key.strip() or len(idempotency_key) > 200:
        raise MemoryIdempotencyConflict("IDEMPOTENCY_KEY_REQUIRED")
    with connect(path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute("SELECT * FROM semantic_memories WHERE memory_id = ?", (memory_id,)).fetchone()
        if row is None:
            raise MemorySourceRejected("Semantic Memory does not exist.")
        _validate_approver_scope(connection, row, actor_id)
        _expire_scope(connection, str(row["tenant_id"]), str(row["project_id"]))
        row = connection.execute("SELECT * FROM semantic_memories WHERE memory_id = ?", (memory_id,)).fetchone()
        request_digest = _digest({"command_kind": "SEMANTIC_CONFIRM", "memory_id": memory_id})
        replay = _find_command(
            connection, tenant_id=str(row["tenant_id"]), actor_id=actor_id,
            idempotency_key=idempotency_key, command_kind="SEMANTIC_CONFIRM",
            target_ref=memory_id, request_digest=request_digest,
        )
        if replay is not None:
            return replay
        if str(row["state"]) == "ACTIVE":
            result = _row_dict(row)
            _record_command(
                connection, tenant_id=str(row["tenant_id"]), actor_id=actor_id,
                idempotency_key=idempotency_key, command_kind="SEMANTIC_CONFIRM",
                target_ref=memory_id, request_digest=request_digest, result=result,
            )
            return result
        if str(row["state"]) != "CANDIDATE":
            raise MemorySourceRejected("Only an unexpired Semantic Candidate can be activated.")
        if _parse_time(str(row["expires_at"])) <= _now() or not _source_is_current(connection, row):
            raise MemorySourceRejected("Semantic Candidate source is expired or no longer valid.")
        supersedes_id = row["supersedes_memory_id"]
        if supersedes_id is not None:
            prior = connection.execute(
                "SELECT * FROM semantic_memories WHERE memory_id = ?", (str(supersedes_id),),
            ).fetchone()
            if (
                prior is None or str(prior["state"]) != "ACTIVE"
                or int(prior["version"]) != int(row["supersedes_version"])
                or str(prior["tenant_id"]) != str(row["tenant_id"])
                or str(prior["project_id"]) != str(row["project_id"])
                or str(prior["memory_key"]) != str(row["memory_key"])
                or str(prior["memory_kind"]) != str(row["memory_kind"])
                or _parse_time(str(prior["expires_at"])) <= _now()
            ):
                raise SemanticMemoryConflict("Semantic revision target changed before approval.")
            connection.execute(
                "UPDATE semantic_memories SET state = 'REVISED' WHERE memory_id = ? AND state = 'ACTIVE'",
                (str(supersedes_id),),
            )
            _event(connection, prior, event_type="REVISED", actor_id=actor_id,
                   version=int(prior["version"]),
                   details={"superseded_by": memory_id, "new_version": int(row["version"]),
                            "previous_content_digest": str(prior["content_digest"]),
                            "new_content_digest": str(row["content_digest"])} )
        else:
            conflict = connection.execute(
                """SELECT 1 FROM semantic_memories WHERE tenant_id = ? AND project_id = ?
                   AND memory_kind = ? AND memory_key = ? AND state = 'ACTIVE' LIMIT 1""",
                (row["tenant_id"], row["project_id"], row["memory_kind"], row["memory_key"]),
            ).fetchone()
            if conflict is not None:
                raise SemanticMemoryConflict("An active Semantic Memory already uses this key.")
        confirmed_at = _now_text()
        connection.execute(
            """UPDATE semantic_memories SET state = 'ACTIVE', confirmed_by = ?, confirmed_at = ?
               WHERE memory_id = ? AND state = 'CANDIDATE'""",
            (actor_id, confirmed_at, memory_id),
        )
        _event(connection, row, event_type="CONFIRMED", actor_id=actor_id,
               version=int(row["version"]), details={"scope": "PROJECT"})
        updated = connection.execute("SELECT * FROM semantic_memories WHERE memory_id = ?", (memory_id,)).fetchone()
        result = _row_dict(updated)
        _record_command(
            connection, tenant_id=str(row["tenant_id"]), actor_id=actor_id,
            idempotency_key=idempotency_key, command_kind="SEMANTIC_CONFIRM",
            target_ref=memory_id, request_digest=request_digest, result=result,
        )
    return result


def revoke_semantic_memory(
    path: str | Path, memory_id: str, actor_id: str, *, idempotency_key: str,
) -> dict[str, Any]:
    if not idempotency_key.strip() or len(idempotency_key) > 200:
        raise MemoryIdempotencyConflict("IDEMPOTENCY_KEY_REQUIRED")
    with connect(path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute("SELECT * FROM semantic_memories WHERE memory_id = ?", (memory_id,)).fetchone()
        if row is None:
            raise MemorySourceRejected("Semantic Memory does not exist.")
        _validate_approver_scope(connection, row, actor_id)
        _expire_scope(connection, str(row["tenant_id"]), str(row["project_id"]))
        row = connection.execute("SELECT * FROM semantic_memories WHERE memory_id = ?", (memory_id,)).fetchone()
        request_digest = _digest({"command_kind": "SEMANTIC_REVOKE", "memory_id": memory_id})
        replay = _find_command(
            connection, tenant_id=str(row["tenant_id"]), actor_id=actor_id,
            idempotency_key=idempotency_key, command_kind="SEMANTIC_REVOKE",
            target_ref=memory_id, request_digest=request_digest,
        )
        if replay is not None:
            return replay
        if str(row["state"]) == "REVOKED":
            result = _row_dict(row)
            _record_command(
                connection, tenant_id=str(row["tenant_id"]), actor_id=actor_id,
                idempotency_key=idempotency_key, command_kind="SEMANTIC_REVOKE",
                target_ref=memory_id, request_digest=request_digest, result=result,
            )
            return result
        if str(row["state"]) != "ACTIVE":
            raise MemorySourceRejected("Only ACTIVE Semantic Memory can be revoked.")
        version = int(row["version"]) + 1
        revoked_at = _now_text()
        connection.execute(
            """UPDATE semantic_memories SET state = 'REVOKED', version = ?, revoked_by = ?, revoked_at = ?
               WHERE memory_id = ? AND state = 'ACTIVE'""",
            (version, actor_id, revoked_at, memory_id),
        )
        _event(connection, row, event_type="REVOKED", actor_id=actor_id, version=version,
               details={"previous_version": int(row["version"]), "content_digest": str(row["content_digest"])})
        updated = connection.execute("SELECT * FROM semantic_memories WHERE memory_id = ?", (memory_id,)).fetchone()
        result = _row_dict(updated)
        _record_command(
            connection, tenant_id=str(row["tenant_id"]), actor_id=actor_id,
            idempotency_key=idempotency_key, command_kind="SEMANTIC_REVOKE",
            target_ref=memory_id, request_digest=request_digest, result=result,
        )
    return result


def _expire_scope(connection: sqlite3.Connection, tenant_id: str, project_id: str) -> None:
    now = _now_text()
    rows = connection.execute(
        """SELECT * FROM semantic_memories WHERE tenant_id = ? AND project_id = ?
           AND state IN ('CANDIDATE', 'ACTIVE') AND expires_at <= ?""",
        (tenant_id, project_id, now),
    ).fetchall()
    for row in rows:
        version = int(row["version"]) + 1
        connection.execute(
            "UPDATE semantic_memories SET state = 'EXPIRED', version = ? WHERE memory_id = ? AND state IN ('CANDIDATE', 'ACTIVE')",
            (version, row["memory_id"]),
        )
        _event(connection, row, event_type="EXPIRED", actor_id="system:expiry", version=version,
               details={"previous_state": str(row["state"]), "expired_at": str(row["expires_at"])})


def list_semantic_memories(
    path: str | Path,
    task_id: str,
    actor_id: str,
    *,
    state: str | None = None,
) -> list[dict[str, Any]]:
    if state is not None and state not in SEMANTIC_MEMORY_STATES:
        raise MemorySourceRejected("Unsupported Semantic Memory lifecycle state.")
    with connect(path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        binding = _trusted_binding(connection, task_id)
        operator = _require_memory_operator(connection, actor_id, str(binding["tenant_id"]))
        if str(operator["role"]) == "SUPPORT" and str(binding["actor_id"]) != actor_id:
            raise MemoryScopeDenied("Only the trusted Task owner can inspect project Semantic Memory.")
        project_id = _scope_for_binding(binding)
        if str(operator["role"]) == "APPROVER":
            grant = connection.execute(
                """SELECT 1 FROM semantic_memory_project_approvers
                   WHERE tenant_id = ? AND project_id = ? AND actor_id = ? AND active = 1""",
                (binding["tenant_id"], project_id, actor_id),
            ).fetchone()
            if grant is None:
                raise MemoryScopeDenied("Approver does not hold this project Semantic Memory grant.")
        _expire_scope(connection, str(binding["tenant_id"]), project_id)
        query = "SELECT * FROM semantic_memories WHERE tenant_id = ? AND project_id = ?"
        params: list[object] = [str(binding["tenant_id"]), project_id]
        if state is not None:
            query += " AND state = ?"
            params.append(state)
        query += " ORDER BY memory_key, version DESC, created_at DESC LIMIT 100"
        rows = connection.execute(query, params).fetchall()
    return [_row_dict(row) for row in rows]


def list_semantic_review_queue(
    path: str | Path, actor_id: str, *, state: str | None = None,
) -> list[dict[str, Any]]:
    if state is not None and state not in SEMANTIC_MEMORY_STATES:
        raise MemorySourceRejected("Unsupported Semantic Memory lifecycle state.")
    with connect(path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        operator = connection.execute(
            "SELECT tenant_id, role FROM trusted_operators WHERE actor_id = ?", (actor_id,),
        ).fetchone()
        if operator is None or str(operator["role"]) != "APPROVER":
            raise MemoryScopeDenied("Semantic review queue requires a trusted APPROVER.")
        grants = connection.execute(
            """SELECT project_id FROM semantic_memory_project_approvers
               WHERE tenant_id = ? AND actor_id = ? AND active = 1 ORDER BY project_id""",
            (operator["tenant_id"], actor_id),
        ).fetchall()
        project_ids = [str(row["project_id"]) for row in grants]
        for project_id in project_ids:
            _expire_scope(connection, str(operator["tenant_id"]), project_id)
        if not project_ids:
            return []
        placeholders = ",".join("?" for _ in project_ids)
        query = f"SELECT * FROM semantic_memories WHERE tenant_id = ? AND project_id IN ({placeholders})"
        params: list[object] = [str(operator["tenant_id"]), *project_ids]
        if state is not None:
            query += " AND state = ?"
            params.append(state)
        query += " ORDER BY created_at DESC, memory_id LIMIT 100"
        rows = connection.execute(query, params).fetchall()
    return [_row_dict(row) for row in rows]


def active_semantic_context(
    connection: sqlite3.Connection, task_id: str,
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    binding = _trusted_binding(connection, task_id)
    tenant_id = str(binding["tenant_id"])
    project_id = _scope_for_binding(binding)
    _expire_scope(connection, tenant_id, project_id)
    rows = connection.execute(
        """SELECT * FROM semantic_memories WHERE tenant_id = ? AND project_id = ?
           AND state IN ('ACTIVE', 'EXPIRED', 'REVOKED', 'REVISED')
           ORDER BY memory_key, version DESC, created_at DESC LIMIT 100""",
        (tenant_id, project_id),
    ).fetchall()
    selected: list[dict[str, Any]] = []
    excluded: list[dict[str, str]] = []
    for row in rows:
        memory_id = str(row["memory_id"])
        lifecycle_state = str(row["state"])
        if lifecycle_state != "ACTIVE":
            excluded.append({
                "source_id": memory_id,
                "reason": {
                    "EXPIRED": "SEMANTIC_MEMORY_EXPIRED",
                    "REVOKED": "SEMANTIC_MEMORY_REVOKED",
                    "REVISED": "SEMANTIC_MEMORY_REVISED",
                }.get(lifecycle_state, "SEMANTIC_MEMORY_INACTIVE"),
            })
            continue
        if str(row["source_task_id"]) == task_id:
            excluded.append({"source_id": memory_id, "reason": "SEMANTIC_MEMORY_SAME_TASK_SOURCE"})
            continue
        if _parse_time(str(row["expires_at"])) <= _now():
            excluded.append({"source_id": memory_id, "reason": "SEMANTIC_MEMORY_EXPIRED"})
            continue
        if not _source_is_current(connection, row):
            excluded.append({"source_id": memory_id, "reason": "SEMANTIC_MEMORY_SOURCE_INVALID"})
            continue
        if len(selected) >= MAX_SEMANTIC_RESULTS:
            excluded.append({"source_id": memory_id, "reason": "SEMANTIC_SELECTION_LIMIT"})
            continue
        item = _row_dict(row)
        item.update({
            "memory_id": memory_id,
            "digest": str(row["content_digest"]),
            "content_digest": str(row["content_digest"]),
            "source_task_id": str(row["source_task_id"]),
            "source_outcome": "PROJECT_CONTEXT",
            "schema_version": "semantic-memory-v1",
            "memory_type": "SEMANTIC",
            "summary": str(row["content"]),
            "experience": {
                "memory_kind": str(row["memory_kind"]),
                "memory_key": str(row["memory_key"]),
                "content": str(row["content"]),
                "limitations": ["Project context only; current Domain facts and formal Knowledge have precedence."],
            },
            "applicability_reason": "TRUSTED_TASK_PROJECT_MATCH",
        })
        selected.append(item)
    return selected, excluded


def semantic_memory_context(
    path: str | Path, task_id: str, actor_id: str,
) -> dict[str, Any]:
    with connect(path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        trusted_binding = _trusted_binding(connection, task_id)
        operator = _require_memory_operator(connection, actor_id, str(trusted_binding["tenant_id"]))
        if str(operator["role"]) == "SUPPORT" and str(trusted_binding["actor_id"]) != actor_id:
            raise MemoryScopeDenied("Only the trusted Task owner can inspect Semantic Memory context.")
        project_id = _scope_for_binding(trusted_binding)
        if str(operator["role"]) == "APPROVER":
            grant = connection.execute(
                """SELECT 1 FROM semantic_memory_project_approvers
                   WHERE tenant_id = ? AND project_id = ? AND actor_id = ? AND active = 1""",
                (trusted_binding["tenant_id"], project_id, actor_id),
            ).fetchone()
            if grant is None:
                raise MemoryScopeDenied("Approver does not hold this project Semantic Memory grant.")
        _expire_scope(connection, str(trusted_binding["tenant_id"]), project_id)
        source_rows = connection.execute(
            "SELECT * FROM semantic_memories WHERE tenant_id = ? AND project_id = ? AND source_task_id = ? ORDER BY created_at",
            (trusted_binding["tenant_id"], project_id, task_id),
        ).fetchall()
        project_rows = connection.execute(
            """SELECT * FROM semantic_memories WHERE tenant_id = ? AND project_id = ?
               AND state IN ('ACTIVE', 'EXPIRED', 'REVOKED', 'REVISED')
               ORDER BY memory_key, version DESC, created_at DESC LIMIT 100""",
            (trusted_binding["tenant_id"], project_id),
        ).fetchall()
        active = [
            _row_dict(row) for row in project_rows
            if str(row["state"]) == "ACTIVE"
            and str(row["source_task_id"]) != task_id
            and _parse_time(str(row["expires_at"])) > _now() and _source_is_current(connection, row)
        ]
        excluded = [
            {"memory_id": str(row["memory_id"]),
             "reason": (
                 "SEMANTIC_MEMORY_SAME_TASK_SOURCE" if str(row["source_task_id"]) == task_id
                 else "SEMANTIC_MEMORY_EXPIRED" if str(row["state"]) == "EXPIRED"
                 else "SEMANTIC_MEMORY_REVOKED" if str(row["state"]) == "REVOKED"
                 else "SEMANTIC_MEMORY_REVISED" if str(row["state"]) == "REVISED"
                 else "SEMANTIC_MEMORY_SOURCE_INVALID_OR_EXPIRED"
             )}
            for row in project_rows
            if str(row["state"]) != "ACTIVE"
            or str(row["source_task_id"]) == task_id
            or _parse_time(str(row["expires_at"])) <= _now() or not _source_is_current(connection, row)
        ]
    return {
        "task_id": task_id,
        "project_id": project_id,
        "source_candidates": [_row_dict(row) for row in source_rows],
        "active_project_memories": active[:MAX_SEMANTIC_RESULTS],
        "excluded": excluded,
    }


def _personal_row_dict(row: sqlite3.Row | dict[str, Any]) -> dict[str, Any]:
    item = dict(row)
    item["source_refs"] = json.loads(str(item.pop("source_refs_json")))
    item["source_authority"] = "CONFIRMED_PERSONAL_CONTEXT_ONLY"
    item["memory_type"] = "PERSONAL"
    item["digest"] = str(item["content_digest"])
    item["summary"] = str(item["content"])
    return item


def _personal_payload(
    memory_kind: str, memory_key: str, content: str, source_refs: list[dict[str, str]],
) -> dict[str, Any]:
    return {
        "memory_kind": memory_kind, "memory_key": memory_key,
        "content": content, "source_refs": source_refs,
    }


def _personal_source_is_current(
    connection: sqlite3.Connection, row: sqlite3.Row | dict[str, Any],
) -> bool:
    item = dict(row)
    try:
        refs = json.loads(str(item["source_refs_json"]))
    except (KeyError, TypeError, json.JSONDecodeError):
        return False
    if (
        not isinstance(refs, list) or len(refs) != 1
        or not isinstance(refs[0], dict)
        or refs[0].get("kind") != "MESSAGE"
        or str(refs[0].get("id", "")) != str(item.get("source_message_id", ""))
    ):
        return False
    source = connection.execute(
        """SELECT m.tenant_id, m.role, m.input_kind, m.body_digest, s.owner_id
           FROM messages m JOIN sessions s ON s.session_id = m.session_id AND s.tenant_id = m.tenant_id
           WHERE m.message_id = ?""",
        (str(item["source_message_id"]),),
    ).fetchone()
    content_payload = _personal_payload(
        str(item["memory_kind"]), str(item["memory_key"]), str(item["content"]), refs,
    )
    return bool(
        source is not None
        and str(source["tenant_id"]) == str(item["tenant_id"])
        and str(source["owner_id"]) == str(item["owner_actor_id"])
        and str(source["role"]) == "USER"
        and str(source["input_kind"]) in {"CHAT_READONLY", "CORRECT_TASK_INPUT"}
        and str(source["body_digest"]) == str(refs[0].get("digest", ""))
        and str(item.get("content_digest", "")) == _digest(content_payload)
    )


def _personal_event(
    connection: sqlite3.Connection,
    row: sqlite3.Row | dict[str, Any],
    *, event_type: str, actor_id: str, version: int,
    details: dict[str, Any] | None = None,
) -> None:
    item = dict(row)
    connection.execute(
        """INSERT INTO personal_memory_events
           (event_id, memory_id, tenant_id, owner_actor_id, event_type, actor_id,
            memory_version, occurred_at, details_json)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (f"personal-memory-event-{uuid.uuid4()}", item["memory_id"], item["tenant_id"],
         item["owner_actor_id"], event_type, actor_id, version, _now_text(),
         _canonical(details or {})),
    )


def _validate_personal_proposal(
    memory_kind: str, memory_key: str, content: str,
) -> tuple[str, str, str]:
    kind = memory_kind.strip().upper()
    key = " ".join(memory_key.split())
    value = " ".join(content.split())
    if kind not in PERSONAL_MEMORY_KINDS:
        raise MemorySourceRejected("Unsupported Personal Memory kind.")
    if not key or len(key) > 120 or not value or len(value) > 800:
        raise MemorySourceRejected("Personal Memory key or content is outside the allowed length.")
    if _SENSITIVE_TEXT.search(key + " " + value):
        raise MemorySourceRejected("Secret-like content cannot be stored as Personal Memory.")
    return kind, key, value


def _expire_personal_scope(
    connection: sqlite3.Connection, tenant_id: str, owner_actor_id: str,
) -> None:
    rows = connection.execute(
        """SELECT * FROM personal_memories WHERE tenant_id = ? AND owner_actor_id = ?
           AND state IN ('CANDIDATE', 'ACTIVE') AND expires_at <= ?""",
        (tenant_id, owner_actor_id, _now_text()),
    ).fetchall()
    for row in rows:
        version = int(row["version"]) + 1
        connection.execute(
            "UPDATE personal_memories SET state = 'EXPIRED', version = ? WHERE memory_id = ? AND state IN ('CANDIDATE', 'ACTIVE')",
            (version, row["memory_id"]),
        )
        _personal_event(
            connection, row, event_type="EXPIRED", actor_id="system:expiry", version=version,
            details={"previous_state": str(row["state"]), "expired_at": str(row["expires_at"])},
        )


def create_personal_candidate(
    path: str | Path,
    tenant_id: str,
    actor_id: str,
    *, memory_kind: str, memory_key: str, content: str,
    source_message_id: str, ttl_days: int = 180,
    idempotency_key: str, supersedes_memory_id: str | None = None,
    expected_version: int | None = None,
) -> dict[str, Any]:
    if not idempotency_key.strip() or len(idempotency_key) > 200:
        raise MemoryIdempotencyConflict("IDEMPOTENCY_KEY_REQUIRED")
    if not 1 <= ttl_days <= 365:
        raise MemorySourceRejected("Personal Memory lifetime must be between 1 and 365 days.")
    kind, key, value = _validate_personal_proposal(memory_kind, memory_key, content)
    with connect(path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        operator = _require_memory_operator(connection, actor_id, tenant_id)
        source = connection.execute(
            """SELECT m.message_id, m.tenant_id, m.role, m.input_kind, m.body_digest,
                      s.owner_id
               FROM messages m JOIN sessions s ON s.session_id = m.session_id AND s.tenant_id = m.tenant_id
               WHERE m.message_id = ?""",
            (source_message_id,),
        ).fetchone()
        if (
            source is None or str(source["tenant_id"]) != tenant_id
            or str(source["owner_id"]) != actor_id or str(source["role"]) != "USER"
            or str(source["input_kind"]) not in {"CHAT_READONLY", "CORRECT_TASK_INPUT"}
        ):
            raise MemorySourceRejected("Personal Memory source must be the owner's persisted user message.")
        _expire_personal_scope(connection, tenant_id, actor_id)
        refs = [{"kind": "MESSAGE", "id": source_message_id, "digest": str(source["body_digest"])}]
        request_payload = {
            "memory_kind": kind, "memory_key": key, "content": value,
            "source_message_id": source_message_id, "source_digest": str(source["body_digest"]),
            "ttl_days": ttl_days, "supersedes_memory_id": supersedes_memory_id,
            "expected_version": expected_version,
        }
        request_digest = _digest(request_payload)
        replay = _find_command(
            connection, tenant_id=str(operator["tenant_id"]), actor_id=actor_id,
            idempotency_key=idempotency_key, command_kind="PERSONAL_CANDIDATE_CREATE",
            target_ref=actor_id, request_digest=request_digest,
        )
        if replay is not None:
            return replay
        prior = None
        if supersedes_memory_id is not None:
            prior = connection.execute(
                """SELECT * FROM personal_memories WHERE memory_id = ? AND tenant_id = ?
                   AND owner_actor_id = ? AND state = 'ACTIVE'""",
                (supersedes_memory_id, tenant_id, actor_id),
            ).fetchone()
            if (
                prior is None or expected_version is None
                or int(prior["version"]) != expected_version
                or str(prior["memory_kind"]) != kind or str(prior["memory_key"]) != key
                or _parse_time(str(prior["expires_at"])) <= _now()
                or not _personal_source_is_current(connection, prior)
            ):
                raise MemorySourceRejected("Personal Memory revision target is stale, expired, or outside this owner scope.")
            if str(prior["content"]) == value:
                raise MemorySourceRejected("A Personal Memory revision must change the proposed content.")
            version = int(prior["version"]) + 1
        else:
            prior = connection.execute(
                """SELECT memory_id FROM personal_memories WHERE tenant_id = ? AND owner_actor_id = ?
                   AND memory_kind = ? AND memory_key = ? AND state = 'ACTIVE'""",
                (tenant_id, actor_id, kind, key),
            ).fetchone()
            if prior is not None:
                raise SemanticMemoryConflict("An active Personal Memory already uses this key; submit an explicit versioned revision.")
            version = 1
        memory_id = f"personal-{uuid.uuid4()}"
        created_at = _now_text()
        expires_at = (_now() + timedelta(days=ttl_days)).isoformat(timespec="milliseconds")
        content_digest = _digest(_personal_payload(kind, key, value, refs))
        connection.execute(
            """INSERT INTO personal_memories
               (memory_id, tenant_id, owner_actor_id, memory_kind, memory_key, content,
                content_digest, source_message_id, source_refs_json, state, version,
                supersedes_memory_id, supersedes_version, created_by, expires_at, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'CANDIDATE', ?, ?, ?, ?, ?, ?)""",
            (memory_id, tenant_id, actor_id, kind, key, value, content_digest,
             source_message_id, _canonical(refs), version, supersedes_memory_id,
             expected_version, actor_id, expires_at, created_at),
        )
        row = connection.execute("SELECT * FROM personal_memories WHERE memory_id = ?", (memory_id,)).fetchone()
        _personal_event(
            connection, row, event_type="CANDIDATE_CREATED", actor_id=actor_id, version=version,
            details={"source_message_id": source_message_id, "content_digest": content_digest,
                     "supersedes_memory_id": supersedes_memory_id, "scope": "PERSONAL"},
        )
        result = _personal_row_dict(row)
        _record_command(
            connection, tenant_id=tenant_id, actor_id=actor_id,
            idempotency_key=idempotency_key, command_kind="PERSONAL_CANDIDATE_CREATE",
            target_ref=actor_id, request_digest=request_digest, result=result,
        )
    return result


def confirm_personal_memory(
    path: str | Path, tenant_id: str, memory_id: str, actor_id: str, *, idempotency_key: str,
) -> dict[str, Any]:
    if not idempotency_key.strip() or len(idempotency_key) > 200:
        raise MemoryIdempotencyConflict("IDEMPOTENCY_KEY_REQUIRED")
    with connect(path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        _require_memory_operator(connection, actor_id, tenant_id)
        row = connection.execute(
            "SELECT * FROM personal_memories WHERE memory_id = ? AND tenant_id = ? AND owner_actor_id = ?",
            (memory_id, tenant_id, actor_id),
        ).fetchone()
        if row is None:
            raise MemoryScopeDenied("Personal Memory is outside the authenticated owner scope.")
        _expire_personal_scope(connection, tenant_id, actor_id)
        row = connection.execute("SELECT * FROM personal_memories WHERE memory_id = ?", (memory_id,)).fetchone()
        request_digest = _digest({"command_kind": "PERSONAL_CONFIRM", "memory_id": memory_id})
        replay = _find_command(
            connection, tenant_id=tenant_id, actor_id=actor_id, idempotency_key=idempotency_key,
            command_kind="PERSONAL_CONFIRM", target_ref=memory_id, request_digest=request_digest,
        )
        if replay is not None:
            return replay
        if str(row["state"]) == "ACTIVE":
            result = _personal_row_dict(row)
            _record_command(
                connection, tenant_id=tenant_id, actor_id=actor_id,
                idempotency_key=idempotency_key, command_kind="PERSONAL_CONFIRM",
                target_ref=memory_id, request_digest=request_digest, result=result,
            )
            return result
        if (
            str(row["state"]) != "CANDIDATE"
            or _parse_time(str(row["expires_at"])) <= _now()
            or not _personal_source_is_current(connection, row)
        ):
            raise MemorySourceRejected("Personal candidate is inactive, expired, or its source is no longer valid.")
        supersedes_id = row["supersedes_memory_id"]
        if supersedes_id is not None:
            prior = connection.execute(
                "SELECT * FROM personal_memories WHERE memory_id = ?", (str(supersedes_id),),
            ).fetchone()
            if (
                prior is None or str(prior["state"]) != "ACTIVE"
                or int(prior["version"]) != int(row["supersedes_version"])
                or str(prior["tenant_id"]) != tenant_id
                or str(prior["owner_actor_id"]) != actor_id
                or str(prior["memory_key"]) != str(row["memory_key"])
                or str(prior["memory_kind"]) != str(row["memory_kind"])
                or _parse_time(str(prior["expires_at"])) <= _now()
                or not _personal_source_is_current(connection, prior)
            ):
                raise SemanticMemoryConflict("Personal revision target changed before confirmation.")
            connection.execute(
                "UPDATE personal_memories SET state = 'REVISED' WHERE memory_id = ? AND state = 'ACTIVE'",
                (str(supersedes_id),),
            )
            _personal_event(
                connection, prior, event_type="REVISED", actor_id=actor_id,
                version=int(prior["version"]),
                details={"superseded_by": memory_id, "new_version": int(row["version"]),
                         "previous_content_digest": str(prior["content_digest"]),
                         "new_content_digest": str(row["content_digest"])},
            )
        else:
            conflict = connection.execute(
                """SELECT 1 FROM personal_memories WHERE tenant_id = ? AND owner_actor_id = ?
                   AND memory_kind = ? AND memory_key = ? AND state = 'ACTIVE' LIMIT 1""",
                (tenant_id, actor_id, row["memory_kind"], row["memory_key"]),
            ).fetchone()
            if conflict is not None:
                raise SemanticMemoryConflict("An active Personal Memory already uses this key.")
        now = _now_text()
        connection.execute(
            """UPDATE personal_memories SET state = 'ACTIVE', confirmed_by = ?, confirmed_at = ?
               WHERE memory_id = ? AND state = 'CANDIDATE'""",
            (actor_id, now, memory_id),
        )
        _personal_event(
            connection, row, event_type="CONFIRMED", actor_id=actor_id,
            version=int(row["version"]), details={"scope": "PERSONAL"},
        )
        updated = connection.execute("SELECT * FROM personal_memories WHERE memory_id = ?", (memory_id,)).fetchone()
        result = _personal_row_dict(updated)
        _record_command(
            connection, tenant_id=tenant_id, actor_id=actor_id,
            idempotency_key=idempotency_key, command_kind="PERSONAL_CONFIRM",
            target_ref=memory_id, request_digest=request_digest, result=result,
        )
    return result


def revoke_personal_memory(
    path: str | Path, tenant_id: str, memory_id: str, actor_id: str, *, idempotency_key: str,
) -> dict[str, Any]:
    if not idempotency_key.strip() or len(idempotency_key) > 200:
        raise MemoryIdempotencyConflict("IDEMPOTENCY_KEY_REQUIRED")
    with connect(path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        _require_memory_operator(connection, actor_id, tenant_id)
        row = connection.execute(
            "SELECT * FROM personal_memories WHERE memory_id = ? AND tenant_id = ? AND owner_actor_id = ?",
            (memory_id, tenant_id, actor_id),
        ).fetchone()
        if row is None:
            raise MemoryScopeDenied("Personal Memory is outside the authenticated owner scope.")
        request_digest = _digest({"command_kind": "PERSONAL_REVOKE", "memory_id": memory_id})
        replay = _find_command(
            connection, tenant_id=tenant_id, actor_id=actor_id, idempotency_key=idempotency_key,
            command_kind="PERSONAL_REVOKE", target_ref=memory_id, request_digest=request_digest,
        )
        if replay is not None:
            return replay
        if str(row["state"]) == "REVOKED":
            result = _personal_row_dict(row)
            _record_command(
                connection, tenant_id=tenant_id, actor_id=actor_id,
                idempotency_key=idempotency_key, command_kind="PERSONAL_REVOKE",
                target_ref=memory_id, request_digest=request_digest, result=result,
            )
            return result
        if str(row["state"]) != "ACTIVE":
            raise MemorySourceRejected("Only ACTIVE Personal Memory can be revoked.")
        version = int(row["version"]) + 1
        revoked_at = _now_text()
        connection.execute(
            """UPDATE personal_memories SET state = 'REVOKED', version = ?, revoked_by = ?, revoked_at = ?
               WHERE memory_id = ? AND state = 'ACTIVE'""",
            (version, actor_id, revoked_at, memory_id),
        )
        _personal_event(
            connection, row, event_type="REVOKED", actor_id=actor_id, version=version,
            details={"previous_version": int(row["version"]), "content_digest": str(row["content_digest"])},
        )
        updated = connection.execute("SELECT * FROM personal_memories WHERE memory_id = ?", (memory_id,)).fetchone()
        result = _personal_row_dict(updated)
        _record_command(
            connection, tenant_id=tenant_id, actor_id=actor_id,
            idempotency_key=idempotency_key, command_kind="PERSONAL_REVOKE",
            target_ref=memory_id, request_digest=request_digest, result=result,
        )
    return result


def list_personal_memories(
    path: str | Path, tenant_id: str, actor_id: str, *,
    state: str | None = None, memory_id: str | None = None,
) -> list[dict[str, Any]]:
    if state is not None and state not in SEMANTIC_MEMORY_STATES:
        raise MemorySourceRejected("Unsupported Personal Memory lifecycle state.")
    with connect(path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        _require_memory_operator(connection, actor_id, tenant_id)
        _expire_personal_scope(connection, tenant_id, actor_id)
        query = "SELECT * FROM personal_memories WHERE tenant_id = ? AND owner_actor_id = ?"
        params: list[object] = [tenant_id, actor_id]
        if memory_id is not None:
            query += " AND memory_id = ?"
            params.append(memory_id)
        if state is not None:
            query += " AND state = ?"
            params.append(state)
        query += " ORDER BY created_at DESC, memory_id LIMIT 100"
        rows = connection.execute(query, params).fetchall()
        results = []
        for row in rows:
            item = _personal_row_dict(row)
            current = _personal_source_is_current(connection, row)
            item["source_current"] = current
            if not current and str(row["state"]) == "ACTIVE":
                item["exclusion_reason"] = "PERSONAL_MEMORY_SOURCE_INVALID"
            results.append(item)
    return results


def _memory_terms(text: str) -> set[str]:
    terms: set[str] = set()
    for match in _MEMORY_TOKEN.findall(text.casefold()):
        token = match.casefold()
        if re.fullmatch(r"[\u4e00-\u9fff]+", token):
            if len(token) == 2:
                terms.add(token)
            else:
                terms.update(token[index:index + 2] for index in range(len(token) - 1))
        elif token not in _MEMORY_STOPWORDS:
            terms.add(token)
    return terms - _MEMORY_STOPWORDS


def personal_memory_context(
    connection: sqlite3.Connection,
    tenant_id: str,
    owner_actor_id: str,
    query: str,
    *, limit: int = PERSONAL_MEMORY_LIMIT,
) -> tuple[list[dict[str, Any]], list[dict[str, str]], list[dict[str, Any]]]:
    """Return relevant active Personal Memory, excluded reasons, and all current records.

    Retrieval is deliberately lexical and conservative. `all_current` is used
    only to validate prior summaries/answers; only `selected` enters the prompt.
    """
    _require_memory_operator(connection, owner_actor_id, tenant_id)
    _expire_personal_scope(connection, tenant_id, owner_actor_id)
    rows = connection.execute(
        """SELECT * FROM personal_memories WHERE tenant_id = ? AND owner_actor_id = ?
           ORDER BY created_at DESC, memory_id LIMIT 100""",
        (tenant_id, owner_actor_id),
    ).fetchall()
    valid_active: list[dict[str, Any]] = []
    excluded: list[dict[str, str]] = []
    for row in rows:
        state = str(row["state"])
        memory_id = str(row["memory_id"])
        if state != "ACTIVE":
            reason = {
                "CANDIDATE": "PERSONAL_MEMORY_PENDING_CONFIRMATION",
                "REVISED": "PERSONAL_MEMORY_REVISED",
                "REVOKED": "PERSONAL_MEMORY_REVOKED",
                "EXPIRED": "PERSONAL_MEMORY_EXPIRED",
            }.get(state, "PERSONAL_MEMORY_INACTIVE")
            excluded.append({"source_id": memory_id, "reason": reason, "category": "PERSONAL_MEMORY"})
            continue
        if _parse_time(str(row["expires_at"])) <= _now():
            excluded.append({"source_id": memory_id, "reason": "PERSONAL_MEMORY_EXPIRED", "category": "PERSONAL_MEMORY"})
            continue
        if not _personal_source_is_current(connection, row):
            excluded.append({"source_id": memory_id, "reason": "PERSONAL_MEMORY_SOURCE_INVALID", "category": "PERSONAL_MEMORY"})
            continue
        item = _personal_row_dict(row)
        item.update({
            "memory_id": memory_id, "digest": str(row["content_digest"]),
            "content_digest": str(row["content_digest"]), "version": int(row["version"]),
            "source_outcome": "PERSONAL_CONTEXT", "source_task_id": None,
            "experience": {"memory_kind": str(row["memory_kind"]),
                           "memory_key": str(row["memory_key"]), "content": str(row["content"]),
                           "limitations": ["Personal background only; it is not current business evidence or authorization."]},
        })
        valid_active.append(item)
    query_terms = _memory_terms(query)
    scored: list[tuple[float, dict[str, Any]]] = []
    for memory in valid_active:
        document_terms = _memory_terms(str(memory["memory_key"]) + " " + str(memory["content"]))
        key_terms = _memory_terms(str(memory["memory_key"]))
        overlap = query_terms & document_terms
        key_overlap = query_terms & key_terms
        covered = len(overlap)
        # A single generic key token (for example "callback" or "HTTP") is
        # not enough to make a nearby but inapplicable memory eligible. Keys
        # still influence ranking, but selection requires multiple matching
        # terms or a one-token query.
        relevant = (
            covered >= 2 and covered / max(1, len(query_terms)) >= 0.2
        ) or (len(query_terms) == 1 and covered == 1)
        if not query_terms or not relevant:
            excluded.append({"source_id": str(memory["memory_id"]), "reason": "NOT_RELEVANT_TO_QUERY", "category": "PERSONAL_MEMORY"})
            continue
        score = float(len(overlap) + 3 * len(key_overlap)) / max(1, len(query_terms))
        memory["relevance_score"] = round(score, 4)
        memory["selection_reason"] = "LEXICAL_RELEVANCE"
        scored.append((score, memory))
    scored.sort(key=lambda pair: (-pair[0], str(pair[1]["memory_id"])))
    selected = [item for _, item in scored[:max(0, min(limit, PERSONAL_MEMORY_LIMIT))]]
    selected_ids = {str(item["memory_id"]) for item in selected}
    for _, item in scored:
        if str(item["memory_id"]) not in selected_ids:
            excluded.append({"source_id": str(item["memory_id"]), "reason": "PERSONAL_MEMORY_SELECTION_LIMIT", "category": "PERSONAL_MEMORY"})
    return selected, excluded, valid_active


def assert_selected_personal_memories_current_in_connection(
    connection: sqlite3.Connection,
    tenant_id: str,
    owner_actor_id: str,
    selected_memories: list[dict[str, Any]],
) -> None:
    if not selected_memories:
        return
    _require_memory_operator(connection, owner_actor_id, tenant_id)
    _expire_personal_scope(connection, tenant_id, owner_actor_id)
    for selected in selected_memories:
        if str(selected.get("memory_type", "")) != "PERSONAL":
            continue
        row = connection.execute(
            """SELECT * FROM personal_memories WHERE memory_id = ? AND tenant_id = ?
               AND owner_actor_id = ?""",
            (str(selected.get("memory_id", "")), tenant_id, owner_actor_id),
        ).fetchone()
        if (
            row is None or str(row["state"]) != "ACTIVE"
            or int(row["version"]) != int(selected.get("version", 0))
            or str(row["content_digest"]) != str(selected.get("content_digest", ""))
            or not _personal_source_is_current(connection, row)
            or _parse_time(str(row["expires_at"])) <= _now()
        ):
            raise MemorySourceRejected("PERSONAL_MEMORY_REVOKED_EXPIRED_OR_CHANGED")
