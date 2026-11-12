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
PERSONAL_MEMORY_PINNED_LIMIT = 3
PERSONAL_MEMORY_PINNED_TOKEN_BUDGET = 250
PERSONAL_MEMORY_MODES = {"PINNED", "RELEVANT"}
_GLOBAL_LEARNING_WORKFLOW_CUE = re.compile(
    r"(?is)(?:学习|学会|learning|studying).{0,45}(?:技术|新技术|新知识|technology|technical|new concepts?)?"
    r".{0,70}(?:先|首先|优先|first|before).{0,35}(?:理解|掌握|分析|梳理|understand|learn)"
    r".{0,35}(?:原理|机制|流程|执行过程|fundamentals?|principles?|mechanisms?|process|flow)"
    r".{0,55}(?:再|然后|之后|before|then|after).{0,30}(?:代码|实现|coding|code|implementation)"
)
_LEARNING_WORKFLOW_QUERY_CUE = re.compile(
    r"(?i)(?:学习|技术|代码|程序|算法|原理|机制|实现|系统|接口|协议|数据库|模型|框架|"
    r"\b(?:api|http|python|java|typescript|javascript|langgraph|checkpoint|mcp|sql|code|software|programming)\b)"
)
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
# ASCII boundaries also match identifiers adjacent to Chinese prose, e.g. Java后端.
_BACKEND_TOPIC = re.compile(r"(?i)后端|服务端|(?<![a-z0-9_])(?:back[ -]?end|server[ -]side|web services?|rest apis?)(?![a-z0-9_])")
_JVM_TOPIC = re.compile(r"(?i)(?<![a-z0-9_])(?:java|jvm|kotlin)(?![a-z0-9_])")
_JAVA_BACKEND_FRAMEWORK = re.compile(r"(?i)(?<![a-z0-9_])(?:spring[ -]*(?:boot|framework|mvc)|jakarta[ -]+ee)(?![a-z0-9_])")
_AGENT_TOPIC = re.compile(
    r"(?i)智能体|大模型应用|(?<![a-z0-9_])(?:(?:ai|llm|python)[ -]+agents?"
    r"|agent(?:ic)?[ -]+(?:engineering|workflows?)|agent\s*(?:工程|开发|应用|工作流))(?![a-z0-9_])"
)
_AGENT_FRAMEWORK = re.compile(r"(?i)(?<![a-z0-9_])(?:langgraph|langchain)(?![a-z0-9_])")


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
    item["source_authority"] = "PERSONAL_BACKGROUND_ONLY"
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
    if not isinstance(refs, list) or not 1 <= len(refs) <= 3:
        return False
    source_ids: list[str] = []
    sources: list[sqlite3.Row] = []
    for ref in refs:
        if not isinstance(ref, dict) or ref.get("kind") != "MESSAGE":
            return False
        source_id = str(ref.get("id", ""))
        if not source_id or source_id in source_ids or not str(ref.get("digest", "")):
            return False
        source_ids.append(source_id)
        source = connection.execute(
            """SELECT m.tenant_id, m.session_id, m.role, m.input_kind, m.body, m.body_digest, s.owner_id
               FROM messages m JOIN sessions s ON s.session_id = m.session_id AND s.tenant_id = m.tenant_id
               WHERE m.message_id = ?""",
            (source_id,),
        ).fetchone()
        if (
            source is None
            or str(source["tenant_id"]) != str(item["tenant_id"])
            or str(source["owner_id"]) != str(item["owner_actor_id"])
            or str(source["role"]) != "USER"
            or str(source["input_kind"]) not in {"CHAT_READONLY", "CORRECT_TASK_INPUT"}
            or str(source["body_digest"]) != str(ref["digest"])
            or _digest(str(source["body"])) != str(ref["digest"])
        ):
            return False
        sources.append(source)
    if source_ids[0] != str(item.get("source_message_id", "")):
        return False
    if len({str(source["session_id"]) for source in sources}) != 1:
        return False
    content_payload = _personal_payload(
        str(item["memory_kind"]), str(item["memory_key"]), str(item["content"]), refs,
    )
    return bool(
        str(item.get("content_digest", "")) == _digest(content_payload)
    )


def _personal_memory_exclusion(connection: sqlite3.Connection, row: sqlite3.Row) -> str | None:
    """Check a Personal Memory fetched inside its trusted tenant/owner scope."""
    state = str(row["state"])
    if state != "ACTIVE":
        return {
            "CANDIDATE": "PERSONAL_MEMORY_PENDING_CONFIRMATION",
            "REVISED": "PERSONAL_MEMORY_REVISED",
            "REVOKED": "PERSONAL_MEMORY_REVOKED",
            "EXPIRED": "PERSONAL_MEMORY_EXPIRED",
        }.get(state, "PERSONAL_MEMORY_INACTIVE")
    if row["revoked_at"] is not None:
        return "PERSONAL_MEMORY_REVOKED"
    try:
        if _parse_time(str(row["expires_at"])) <= _now():
            return "PERSONAL_MEMORY_EXPIRED"
    except ValueError:
        return "PERSONAL_MEMORY_SOURCE_INVALID"
    if not _personal_source_is_current(connection, row):
        return "PERSONAL_MEMORY_SOURCE_INVALID"
    return None


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
    memory_kind: str, memory_key: str, content: str, memory_mode: str = "RELEVANT",
) -> tuple[str, str, str, str]:
    kind = memory_kind.strip().upper()
    mode = memory_mode.strip().upper()
    key = " ".join(memory_key.split())
    value = " ".join(content.split())
    if kind not in PERSONAL_MEMORY_KINDS:
        raise MemorySourceRejected("Unsupported Personal Memory kind.")
    if mode not in PERSONAL_MEMORY_MODES:
        raise MemorySourceRejected("Unsupported Personal Memory use mode.")
    if mode == "PINNED" and kind == "PROJECT_BACKGROUND":
        raise MemorySourceRejected("Project background cannot be marked as a global pinned preference.")
    if not key or len(key) > 120 or not value or len(value) > 800:
        raise MemorySourceRejected("Personal Memory key or content is outside the allowed length.")
    if _SENSITIVE_TEXT.search(key + " " + value):
        raise MemorySourceRejected("Secret-like content cannot be stored as Personal Memory.")
    return kind, key, value, mode


_EXPLICIT_MEMORY_SAVE = re.compile(
    r"(?i)(?:(?:请|麻烦|帮我|请你)\s*(?:记住|记下|记着|记得)|"
    r"记住\s*[:：，,]|记住(?:我的)?(?:偏好|背景)\s*[:：]|我希望你.{0,12}记住)|"
    r"(?:请|麻烦|帮我|请你)\s*(?:把|将)?.{0,40}(?:保存|存储|保留).{0,16}(?:记忆|偏好|背景)|"
    r"please\s+remember\s*[:：,]|remember (?:this|that|my)|keep (?:this|that|my) .{1,80} in mind|"
    r"save .{1,100} (?:as|to) (?:my )?(?:long[- ]term )?memory|store .{1,100} in (?:my )?memory"
)
_DURABLE_PERSONAL_DIRECTIVE = re.compile(
    r"(?i)(?:以后|今后|从现在起|往后|每次|from now on|going forward|in the future)"
    r".{0,80}(?:回答我|回复我|跟我|为我|对我|我希望|我偏好|我喜欢|我习惯|"
    r"请你.{0,20}(?:回答|解释|使用|采用)|(?:回答|解释).{0,40}(?:先|优先|总是|都|用|采用)|"
    r"reply to me|answer me|explain to me|I prefer|I like|my preference)"
)
_DURABLE_PERSONAL_CUE = re.compile(
    r"(?i)(?:以后|今后|从现在起|往后|长期|稳定偏好|个人偏好|我(?:更)?(?:喜欢|偏好|习惯|希望)|"
    r"我的.{0,12}(?:偏好|习惯|背景)|我叫|我的名字|I prefer|I like|my preference|my name is)"
)
_MEMORY_SAVE_NEGATION = re.compile(
    r"(?i)(?:不要|别|不需要|不用).{0,12}(?:记住|记下|记着|保存|存储|保留|记忆)|"
    r"(?:don't|do not|never)\s+(?:remember|save|store|retain)"
)
_MEMORY_QUESTION = re.compile(
    r"(?i)(?:[?？]|(?:吗|么|呢|如何|怎样|怎么|是否|为什么|哪个|哪种|能否|可否|要不要|该不该)\s*[?？]?)"
)
_ONE_SHOT_MEMORY_INTENT = re.compile(
    r"(?i)(?:这次|本次|当前这轮|这一次|临时|只在今天|仅(?:限)?这次|仅(?:限)?本次|"
    r"for this (?:time|answer|turn) only|just this time|temporarily)"
)
_EXPLICIT_MEMORY_REVISION_INTENT = re.compile(
    r"(?i)(?:更新|修改|更正|改成|替换|修订|update|revise|correct|replace|change)"
)


def _personal_memory_intent_prose(text: str) -> str:
    user_prose = re.sub(r"(?s)```.*?```|~~~.*?~~~|`[^`\n]*`|'[^'\n]*'", " ", text)
    user_prose = re.sub(r"(?m)^\s*>.*$", " ", user_prose)
    user_prose = re.sub(r"(?s)[\"“‘][^\"”’]*[\"”’]", " ", user_prose)
    material_marker = re.search(
        r"(?i)(?:日志|文档|材料|工具输出|错误输出|邮件|报告|\blogs?\b|\bdocuments?\b|"
        r"\btool output\b|\berror output\b|\bpasted material\b|\bemail\b|\breports?\b)"
        r"(?:内容|如下|摘录)?\s*[:：]\s*",
        user_prose,
    )
    if material_marker:
        user_prose = user_prose[:material_marker.start()]
    return user_prose


def user_message_has_explicit_memory_intent(text: str) -> bool:
    """Require a save request or a personal durable directive in user prose."""
    user_prose = _personal_memory_intent_prose(text)
    if _MEMORY_SAVE_NEGATION.search(user_prose):
        return False
    save_request = bool(_EXPLICIT_MEMORY_SAVE.search(user_prose))
    durable_directive = bool(_DURABLE_PERSONAL_DIRECTIVE.search(user_prose)) and not bool(_MEMORY_QUESTION.search(user_prose))
    if not save_request and not durable_directive:
        return False
    if _ONE_SHOT_MEMORY_INTENT.search(user_prose) and not _DURABLE_PERSONAL_CUE.search(user_prose):
        return False
    return True


def user_message_supports_personal_memory_content(text: str, content: str) -> bool:
    """Accept literal content only from a durable, unquoted part of this user message."""
    if not user_message_has_explicit_memory_intent(text):
        return False
    candidate = " ".join(content.split())
    if not candidate or _ONE_SHOT_MEMORY_INTENT.search(candidate) or _MEMORY_SAVE_NEGATION.search(candidate):
        return False
    prose = _personal_memory_intent_prose(text)
    clauses = re.split(r"(?<=[。.!?！？;；\n])", prose)
    durable_parts: list[str] = []
    for clause in clauses:
        if _MEMORY_SAVE_NEGATION.search(clause):
            continue
        one_shot = _ONE_SHOT_MEMORY_INTENT.search(clause)
        if one_shot:
            clause = clause[:one_shot.start()]
        if clause and user_message_has_explicit_memory_intent(clause):
            durable_parts.append(" ".join(clause.split()))
    return any(candidate in part for part in durable_parts)


def user_message_has_explicit_memory_revision_intent(text: str) -> bool:
    """Identify an explicit version correction; ordinary saves cannot overwrite an active key."""
    if not user_message_has_explicit_memory_intent(text):
        return False
    return bool(_EXPLICIT_MEMORY_REVISION_INTENT.search(_personal_memory_intent_prose(text)))


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
    *, memory_kind: str, memory_key: str, content: str, memory_mode: str = "RELEVANT",
    source_message_id: str, ttl_days: int = 180,
    idempotency_key: str, supersedes_memory_id: str | None = None,
    expected_version: int | None = None,
) -> dict[str, Any]:
    if not idempotency_key.strip() or len(idempotency_key) > 200:
        raise MemoryIdempotencyConflict("IDEMPOTENCY_KEY_REQUIRED")
    if not 1 <= ttl_days <= 365:
        raise MemorySourceRejected("Personal Memory lifetime must be between 1 and 365 days.")
    kind, key, value, mode = _validate_personal_proposal(memory_kind, memory_key, content, memory_mode)
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
            "memory_kind": kind, "memory_mode": mode, "memory_key": key, "content": value,
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
            if str(prior["content"]) == value and str(prior["memory_mode"]) == mode:
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
               (memory_id, tenant_id, owner_actor_id, memory_kind, memory_mode, memory_key, content,
                content_digest, source_message_id, source_refs_json, state, version,
                supersedes_memory_id, supersedes_version, created_by, expires_at, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'CANDIDATE', ?, ?, ?, ?, ?, ?)""",
            (memory_id, tenant_id, actor_id, kind, mode, key, value, content_digest,
             source_message_id, _canonical(refs), version, supersedes_memory_id,
             expected_version, actor_id, expires_at, created_at),
        )
        row = connection.execute("SELECT * FROM personal_memories WHERE memory_id = ?", (memory_id,)).fetchone()
        _personal_event(
            connection, row, event_type="CANDIDATE_CREATED", actor_id=actor_id, version=version,
            details={"source_message_id": source_message_id, "content_digest": content_digest,
                     "supersedes_memory_id": supersedes_memory_id, "memory_mode": mode,
                     "scope": "PERSONAL", "creation_source": None},
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
            """UPDATE personal_memories SET state = 'ACTIVE', creation_source = 'USER_CONFIRMED',
               confirmed_by = ?, confirmed_at = ?
               WHERE memory_id = ? AND state = 'CANDIDATE'""",
            (actor_id, now, memory_id),
        )
        _personal_event(
            connection, row, event_type="CONFIRMED", actor_id=actor_id,
            version=int(row["version"]), details={"scope": "PERSONAL", "creation_source": "USER_CONFIRMED"},
        )
        updated = connection.execute("SELECT * FROM personal_memories WHERE memory_id = ?", (memory_id,)).fetchone()
        result = _personal_row_dict(updated)
        _record_command(
            connection, tenant_id=tenant_id, actor_id=actor_id,
            idempotency_key=idempotency_key, command_kind="PERSONAL_CONFIRM",
            target_ref=memory_id, request_digest=request_digest, result=result,
        )
    return result


def _explicit_memory_receipt(row: sqlite3.Row | dict[str, Any], *, replayed: bool = False) -> dict[str, Any]:
    item = dict(row)
    return {
        "saved": True,
        "replayed": replayed,
        "memory_id": str(item["memory_id"]),
        "memory_kind": str(item["memory_kind"]),
        "memory_mode": str(item["memory_mode"]),
        "memory_key": str(item["memory_key"]),
        "version": int(item["version"]),
        "creation_source": str(item["creation_source"]),
        "content_digest": str(item["content_digest"]),
        "source_message_id": str(item["source_message_id"]),
        "expires_at": str(item["expires_at"]),
        "authority": "PERSONAL_BACKGROUND_ONLY_NOT_BUSINESS_FACT",
    }


def remember_personal_memory(
    path: str | Path,
    tenant_id: str,
    actor_id: str,
    *, memory_kind: str, memory_mode: str, memory_key: str, content: str,
    source_message_id: str, idempotency_key: str,
    supersedes_memory_id: str | None = None, expected_version: int | None = None,
) -> dict[str, Any]:
    """Immediately save a user-explicit request, with owner, source and version checks."""
    if not idempotency_key.strip() or len(idempotency_key) > 200:
        raise MemoryIdempotencyConflict("IDEMPOTENCY_KEY_REQUIRED")
    if (supersedes_memory_id is None) != (expected_version is None):
        raise MemorySourceRejected("A versioned Personal Memory revision requires both target ID and expected version.")
    kind, key, value, mode = _validate_personal_proposal(memory_kind, memory_key, content, memory_mode)
    with connect(path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        operator = _require_memory_operator(connection, actor_id, tenant_id)
        source = connection.execute(
            """SELECT m.message_id, m.tenant_id, m.role, m.input_kind, m.body, m.body_digest,
                      s.owner_id
               FROM messages m JOIN sessions s ON s.session_id = m.session_id AND s.tenant_id = m.tenant_id
               WHERE m.message_id = ?""",
            (source_message_id,),
        ).fetchone()
        if (
            source is None or str(source["tenant_id"]) != tenant_id
            or str(source["owner_id"]) != actor_id or str(source["role"]) != "USER"
            or str(source["input_kind"]) != "CHAT_READONLY"
        ):
            raise MemorySourceRejected("Explicit Personal Memory requires the owner's persisted ordinary chat message.")
        if not user_message_has_explicit_memory_intent(str(source["body"])):
            raise MemorySourceRejected("The current user message does not explicitly request durable memory.")
        if not user_message_supports_personal_memory_content(str(source["body"]), value):
            raise MemorySourceRejected("PERSONAL_MEMORY_SOURCE_NOT_SUPPORTED")
        explicit_revision = user_message_has_explicit_memory_revision_intent(str(source["body"]))
        _expire_personal_scope(connection, tenant_id, actor_id)
        refs = [{"kind": "MESSAGE", "id": source_message_id, "digest": str(source["body_digest"])}]
        request_payload = {
            "creation_source": "USER_EXPLICIT", "memory_kind": kind, "memory_mode": mode,
            "memory_key": key, "content": value, "source_message_id": source_message_id,
            "source_digest": str(source["body_digest"]), "supersedes_memory_id": supersedes_memory_id,
            "expected_version": expected_version,
        }
        request_digest = _digest(request_payload)
        replay = _find_command(
            connection, tenant_id=str(operator["tenant_id"]), actor_id=actor_id,
            idempotency_key=idempotency_key, command_kind="PERSONAL_EXPLICIT_REMEMBER",
            target_ref=actor_id, request_digest=request_digest,
        )
        if replay is not None:
            replay["replayed"] = True
            return replay

        active = connection.execute(
            """SELECT * FROM personal_memories WHERE tenant_id = ? AND owner_actor_id = ?
               AND memory_kind = ? AND memory_key = ? AND state = 'ACTIVE'""",
            (tenant_id, actor_id, kind, key),
        ).fetchone()
        prior = None
        effective_supersedes_memory_id = supersedes_memory_id
        effective_expected_version = expected_version
        if active is not None:
            same_value = str(active["content"]) == value and str(active["memory_mode"]) == mode
            if same_value and effective_supersedes_memory_id in {None, str(active["memory_id"])} \
                    and (expected_version is None or int(active["version"]) == expected_version) \
                    and _personal_source_is_current(connection, active):
                result = _explicit_memory_receipt(active)
                _record_command(
                    connection, tenant_id=tenant_id, actor_id=actor_id,
                    idempotency_key=idempotency_key, command_kind="PERSONAL_EXPLICIT_REMEMBER",
                    target_ref=actor_id, request_digest=request_digest, result=result,
                )
                return result
            if effective_supersedes_memory_id is None and explicit_revision:
                # Under BEGIN IMMEDIATE the active row/version cannot change
                # between this lookup and the versioned replacement below.
                effective_supersedes_memory_id = str(active["memory_id"])
                effective_expected_version = int(active["version"])
            if (effective_supersedes_memory_id != str(active["memory_id"])
                    or effective_expected_version != int(active["version"])):
                raise SemanticMemoryConflict(
                    "An active Personal Memory differs; an explicit versioned correction is required."
                )
            prior = active
        elif effective_supersedes_memory_id is not None:
            prior = connection.execute(
                """SELECT * FROM personal_memories WHERE memory_id = ? AND tenant_id = ?
                   AND owner_actor_id = ?""",
                (effective_supersedes_memory_id, tenant_id, actor_id),
            ).fetchone()
            if (
                prior is None or int(prior["version"]) != effective_expected_version
                or str(prior["memory_kind"]) != kind or str(prior["memory_key"]) != key
                or str(prior["state"]) not in {"REVOKED", "EXPIRED", "REVISED"}
            ):
                raise MemorySourceRejected("Personal Memory revision target is stale or outside this owner scope.")
        else:
            # An explicit new save after revocation or expiry may establish a
            # fresh source and version for the same owner/key. This does not
            # overwrite an ACTIVE revision and cannot cross owner scope.
            prior = connection.execute(
                """SELECT * FROM personal_memories WHERE tenant_id = ? AND owner_actor_id = ?
                   AND memory_kind = ? AND memory_key = ? AND state IN ('REVOKED', 'EXPIRED', 'REVISED')
                   ORDER BY version DESC, created_at DESC, memory_id DESC LIMIT 1""",
                (tenant_id, actor_id, kind, key),
            ).fetchone()

        version = int(prior["version"]) + 1 if prior is not None else 1
        memory_id = f"personal-{uuid.uuid4()}"
        created_at = _now_text()
        expires_at = (_now() + timedelta(days=180)).isoformat(timespec="milliseconds")
        content_digest = _digest(_personal_payload(kind, key, value, refs))
        if prior is not None and str(prior["state"]) == "ACTIVE":
            connection.execute(
                "UPDATE personal_memories SET state = 'REVISED' WHERE memory_id = ? AND state = 'ACTIVE'",
                (str(prior["memory_id"]),),
            )
            _personal_event(
                connection, prior, event_type="REVISED", actor_id=actor_id,
                version=int(prior["version"]),
                details={"superseded_by": memory_id, "new_version": version,
                         "previous_content_digest": str(prior["content_digest"]),
                         "new_content_digest": content_digest, "creation_source": "USER_EXPLICIT"},
            )
        connection.execute(
            """INSERT INTO personal_memories
               (memory_id, tenant_id, owner_actor_id, memory_kind, memory_mode, memory_key, content,
                content_digest, source_message_id, source_refs_json, state, version,
                supersedes_memory_id, supersedes_version, created_by, creation_source, expires_at, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'ACTIVE', ?, ?, ?, ?, 'USER_EXPLICIT', ?, ?)""",
            (memory_id, tenant_id, actor_id, kind, mode, key, value, content_digest,
             source_message_id, _canonical(refs), version,
             str(prior["memory_id"]) if prior is not None else None,
             int(prior["version"]) if prior is not None else None,
             actor_id, expires_at, created_at),
        )
        row = connection.execute("SELECT * FROM personal_memories WHERE memory_id = ?", (memory_id,)).fetchone()
        _personal_event(
            connection, row, event_type="USER_EXPLICIT_CREATED", actor_id=actor_id, version=version,
            details={"source_message_id": source_message_id, "content_digest": content_digest,
                     "memory_mode": mode, "creation_source": "USER_EXPLICIT", "scope": "PERSONAL",
                     "supersedes_memory_id": str(prior["memory_id"]) if prior is not None else None,
                     "supersedes_version": int(prior["version"]) if prior is not None else None},
        )
        result = _explicit_memory_receipt(row)
        _record_command(
            connection, tenant_id=tenant_id, actor_id=actor_id,
            idempotency_key=idempotency_key, command_kind="PERSONAL_EXPLICIT_REMEMBER",
            target_ref=actor_id, request_digest=request_digest, result=result,
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


def get_personal_memory_settings(
    path: str | Path, tenant_id: str, actor_id: str,
) -> dict[str, Any]:
    with connect(path) as connection:
        setting = personal_memory_recall_setting(connection, tenant_id, actor_id)
    return {
        "tenant_id": tenant_id, "owner_actor_id": actor_id,
        **setting,
    }


def personal_memory_recall_setting(
    connection: sqlite3.Connection, tenant_id: str, actor_id: str,
) -> dict[str, Any]:
    _require_memory_operator(connection, actor_id, tenant_id)
    row = connection.execute(
        """SELECT recall_enabled, auto_learn_enabled, updated_at FROM personal_memory_settings
           WHERE tenant_id = ? AND owner_actor_id = ?""",
        (tenant_id, actor_id),
    ).fetchone()
    return {
        "recall_enabled": bool(row["recall_enabled"]) if row is not None else True,
        "auto_learn_enabled": bool(row["auto_learn_enabled"]) if row is not None else False,
        "is_default": row is None,
        "updated_at": str(row["updated_at"]) if row is not None else None,
    }


def set_personal_memory_recall(
    path: str | Path, tenant_id: str, actor_id: str, *, recall_enabled: bool,
    auto_learn_enabled: bool | None = None,
) -> dict[str, Any]:
    if type(recall_enabled) is not bool:
        raise MemorySourceRejected("Personal Memory recall setting must be a boolean.")
    updated_at = _now_text()
    with connect(path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        _require_memory_operator(connection, actor_id, tenant_id)
        current = personal_memory_recall_setting(connection, tenant_id, actor_id)
        if auto_learn_enabled is not None and type(auto_learn_enabled) is not bool:
            raise MemorySourceRejected("Personal Memory auto-learn setting must be a boolean.")
        next_auto_learn = (
            bool(current["auto_learn_enabled"])
            if auto_learn_enabled is None else auto_learn_enabled
        )
        if not recall_enabled:
            next_auto_learn = False
        connection.execute(
            """INSERT INTO personal_memory_settings
               (tenant_id, owner_actor_id, recall_enabled, auto_learn_enabled, updated_at)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT (tenant_id, owner_actor_id) DO UPDATE SET
                 recall_enabled = excluded.recall_enabled,
                 auto_learn_enabled = excluded.auto_learn_enabled,
                 updated_at = excluded.updated_at""",
            (tenant_id, actor_id, int(recall_enabled), int(next_auto_learn), updated_at),
        )
        from opspilot.domain.personal_memory_consolidation import (
            advance_disabled_personal_memory_watermarks,
            skip_pending_personal_memory_jobs,
        )

        old_enabled = bool(current["recall_enabled"] and current["auto_learn_enabled"])
        new_enabled = bool(recall_enabled and next_auto_learn)
        if old_enabled and not new_enabled:
            skip_pending_personal_memory_jobs(connection, tenant_id, actor_id)
            advance_disabled_personal_memory_watermarks(connection, tenant_id, actor_id)
        elif not old_enabled and new_enabled:
            # Messages created while learning was disabled are never backfilled.
            advance_disabled_personal_memory_watermarks(connection, tenant_id, actor_id)
    return {
        "tenant_id": tenant_id, "owner_actor_id": actor_id,
        "recall_enabled": recall_enabled, "auto_learn_enabled": next_auto_learn,
        "is_default": False, "updated_at": updated_at,
    }


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


def _project_background_topics(text: str) -> set[str]:
    """Match technical phrases with bilingual aliases for the two project areas."""
    topics: set[str] = set()
    backend = _BACKEND_TOPIC.search(text)
    agent = _AGENT_TOPIC.search(text)
    if _JAVA_BACKEND_FRAMEWORK.search(text) or (backend and _JVM_TOPIC.search(text)):
        topics.add("java_backend")
    if agent or _AGENT_FRAMEWORK.search(text):
        topics.add("agent_engineering")
    if backend and agent:
        topics.add("backend_and_agent")
    return topics


def personal_memory_context(
    connection: sqlite3.Connection,
    tenant_id: str,
    owner_actor_id: str,
    query: str,
    *, limit: int = PERSONAL_MEMORY_LIMIT, recall_enabled: bool = True,
    suppress_recall_reason: str | None = None,
    exclude_source_message_id: str | None = None,
    pinned_limit: int = PERSONAL_MEMORY_PINNED_LIMIT,
    pinned_token_budget: int = PERSONAL_MEMORY_PINNED_TOKEN_BUDGET,
) -> tuple[list[dict[str, Any]], list[dict[str, str]], list[dict[str, Any]]]:
    """Return bounded PINNED plus relevant Personal Memory and all current records.

    RELEVANT memories use lexical overlap and bounded project topic aliases.
    PINNED preferences bypass term matching but stay under a small item and
    token cap. `all_current` validates prior summaries/answers; only selected
    records enter the prompt.
    """
    from opspilot.domain.context_engineering import estimate_text_tokens

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
        memory_id = str(row["memory_id"])
        reason = _personal_memory_exclusion(connection, row)
        if reason is not None:
            excluded.append({"source_id": memory_id, "reason": reason, "category": "PERSONAL_MEMORY"})
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
    if not recall_enabled or suppress_recall_reason:
        reason = "PERSONAL_MEMORY_RECALL_DISABLED" if not recall_enabled else suppress_recall_reason
        excluded.extend({
            "source_id": str(memory["memory_id"]), "reason": reason,
            "category": "PERSONAL_MEMORY",
        } for memory in valid_active)
        return [], excluded, valid_active

    selected_pinned: list[dict[str, Any]] = []
    pinned_tokens = 0
    pinned_candidates = sorted(
        (memory for memory in valid_active
         if (str(memory.get("memory_mode", "RELEVANT")) == "PINNED"
             and not _is_global_learning_preference(memory))
         or (_is_global_learning_preference(memory) and _learning_workflow_query_applies(query))),
        key=lambda memory: (
            1 if str(memory.get("creation_source") or "") in {"USER_EXPLICIT", "USER_CONFIRMED"} else 0,
            str(memory.get("created_at", "")), str(memory["memory_id"]),
        ),
        reverse=True,
    )
    for memory in pinned_candidates:
        if exclude_source_message_id and str(memory["source_message_id"]) == exclude_source_message_id:
            excluded.append({"source_id": str(memory["memory_id"]), "reason": "PERSONAL_MEMORY_CREATED_IN_CURRENT_RUN", "category": "PERSONAL_MEMORY"})
            continue
        estimate = estimate_text_tokens(_canonical({
            "memory_id": memory["memory_id"], "version": memory["version"],
            "memory_kind": memory["memory_kind"], "memory_key": memory["memory_key"],
            "content": memory["content"],
        })) + 20
        if len(selected_pinned) >= max(0, min(pinned_limit, PERSONAL_MEMORY_PINNED_LIMIT)):
            excluded.append({"source_id": str(memory["memory_id"]), "reason": "PINNED_MEMORY_ITEM_LIMIT", "category": "PERSONAL_MEMORY"})
            continue
        if pinned_tokens + estimate > max(0, min(pinned_token_budget, PERSONAL_MEMORY_PINNED_TOKEN_BUDGET)):
            excluded.append({"source_id": str(memory["memory_id"]), "reason": "PINNED_MEMORY_TOKEN_BUDGET", "category": "PERSONAL_MEMORY"})
            continue
        memory["selection_reason"] = (
            "GLOBAL_LEARNING_PREFERENCE"
            if str(memory.get("memory_mode", "RELEVANT")) != "PINNED"
            else "PINNED_PERSONAL_PREFERENCE"
        )
        memory["estimated_tokens"] = estimate
        selected_pinned.append(memory)
        pinned_tokens += estimate

    query_terms = _memory_terms(query)
    query_topics = _project_background_topics(query)
    scored: list[tuple[float, dict[str, Any]]] = []
    for memory in valid_active:
        if str(memory.get("memory_mode", "RELEVANT")) == "PINNED" or _is_global_learning_preference(memory):
            if _is_global_learning_preference(memory) and not _learning_workflow_query_applies(query):
                excluded.append({"source_id": str(memory["memory_id"]), "reason": "NOT_RELEVANT_TO_QUERY", "category": "PERSONAL_MEMORY"})
            continue
        if exclude_source_message_id and str(memory["source_message_id"]) == exclude_source_message_id:
            excluded.append({"source_id": str(memory["memory_id"]), "reason": "PERSONAL_MEMORY_CREATED_IN_CURRENT_RUN", "category": "PERSONAL_MEMORY"})
            continue
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
        topic_match = (not relevant and memory["memory_kind"] == "PROJECT_BACKGROUND"
                       and bool(query_topics & _project_background_topics(str(memory["content"]))))
        if not relevant and not topic_match:
            excluded.append({"source_id": str(memory["memory_id"]), "reason": "NOT_RELEVANT_TO_QUERY", "category": "PERSONAL_MEMORY"})
            continue
        score = float(len(overlap) + 3 * len(key_overlap)) / max(1, len(query_terms))
        if topic_match:
            score = max(score, 0.25)
        memory["relevance_score"] = round(score, 4)
        memory["selection_reason"] = "PROJECT_TOPIC_RELEVANCE" if topic_match else "LEXICAL_RELEVANCE"
        scored.append((score, memory))
    scored.sort(key=lambda pair: (-pair[0], str(pair[1]["memory_id"])))
    selected_relevant = [item for _, item in scored[:max(0, min(limit, PERSONAL_MEMORY_LIMIT))]]
    selected = [*selected_pinned, *selected_relevant]
    selected_ids = {str(item["memory_id"]) for item in selected}
    for _, item in scored:
        if str(item["memory_id"]) not in selected_ids:
            excluded.append({"source_id": str(item["memory_id"]), "reason": "PERSONAL_MEMORY_SELECTION_LIMIT", "category": "PERSONAL_MEMORY"})
    return selected, excluded, valid_active


def _is_global_learning_preference(memory: dict[str, Any]) -> bool:
    """Recognize only the tested cross-topic principle/process-before-code preference."""
    if str(memory.get("memory_kind", "")).upper() not in {"PREFERENCE", "WORK_HABIT"}:
        return False
    text = str(memory.get("memory_key", "")) + " " + str(memory.get("content", ""))
    return bool(_GLOBAL_LEARNING_WORKFLOW_CUE.search(text))


def _learning_workflow_query_applies(query: str) -> bool:
    return bool(_LEARNING_WORKFLOW_QUERY_CUE.search(query))


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
            row is None
            or int(row["version"]) != int(selected.get("version", 0))
            or str(row["content_digest"]) != str(selected.get("content_digest", ""))
            or _personal_memory_exclusion(connection, row) is not None
        ):
            raise MemorySourceRejected("PERSONAL_MEMORY_REVOKED_EXPIRED_OR_CHANGED")
