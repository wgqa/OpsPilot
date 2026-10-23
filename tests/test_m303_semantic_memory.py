from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from opspilot.domain.chat import complete_chat_attempt, get_chat_manifest, prepare_chat_attempt
from opspilot.domain.database import connect, initialize
from opspilot.domain.episodic_memory import ContextAssetInvalidated, assert_selected_memories_current
from opspilot.domain.semantic_memory import (
    MemoryIdempotencyConflict,
    MemoryScopeDenied,
    MemorySourceRejected,
    SemanticMemoryConflict,
    active_semantic_context,
    confirm_semantic_memory,
    create_semantic_candidate,
    list_semantic_review_queue,
    revoke_semantic_memory,
    semantic_memory_context,
)
from opspilot.domain.task_control import (
    admit_task_message,
    claim_task_run,
    create_session,
    create_task_with_initial_run,
    register_worker_owner,
    trusted_identity,
)


def _create_task(
    db: Path, session_id: str, suffix: str, *, actor_id: str = "support-a", integration_id: str = "integration-a",
) -> tuple[str, str]:
    identity = trusted_identity(db, actor_id)
    created = create_task_with_initial_run(
        db, identity, session_id=session_id, service_id="orders-demo",
        integration_id=integration_id, ticket_id=f"semantic-{suffix}",
        initial_message=f"Task {suffix}: orders use the agreed service route.",
        idempotency_key=f"semantic-create-task-{suffix}",
    )
    return str(created["task_id"]), str(created["message_id"])


def _candidate(
    db: Path, task_id: str, source_message_id: str, suffix: str, *,
    memory_key: str = "orders.route-alias", content: str = "Orders API means the fixed demo orders route.",
    supersedes_memory_id: str | None = None, expected_version: int | None = None,
) -> dict[str, object]:
    return create_semantic_candidate(
        db, task_id, "support-a", memory_kind="ALIAS", memory_key=memory_key,
        content=content, source_message_id=source_message_id, ttl_days=90,
        idempotency_key=f"semantic-candidate-{suffix}",
        supersedes_memory_id=supersedes_memory_id, expected_version=expected_version,
    )


def _session_and_task(db: Path, suffix: str) -> tuple[str, str, str]:
    identity = trusted_identity(db, "support-a")
    session_id = str(create_session(db, identity)["session_id"])
    task_id, message_id = _create_task(db, session_id, suffix)
    return session_id, task_id, message_id


def _prepare_task_chat(db: Path, session_id: str, task_id: str, suffix: str) -> tuple[object, dict[str, object]]:
    identity = trusted_identity(db, "support-a")
    admitted = admit_task_message(
        db, identity, session_id=session_id, task_id=task_id,
        input_kind="CHAT_READONLY", body=f"Please explain the current task context ({suffix}).",
        idempotency_key=f"semantic-chat-{suffix}",
    )
    run_id = str(admitted["run_id"])
    worker_id = f"semantic-worker-{suffix}"
    register_worker_owner(db, worker_id, os.getpid())
    claim_task_run(db, identity, run_id)
    prepared = prepare_chat_attempt(db, run_id, worker_id, "test-model")
    return identity, {**prepared, "run_id": run_id, "worker_id": worker_id}


def test_m303_candidate_is_source_scoped_idempotent_and_not_active(demo_db: Path) -> None:
    session_id, task_a, message_a = _session_and_task(demo_db, "a")
    _, task_b, message_b = _session_and_task(demo_db, "b")

    candidate = _candidate(demo_db, task_a, message_a, "candidate-idempotent")
    replay = _candidate(demo_db, task_a, message_a, "candidate-idempotent")
    assert candidate["memory_id"] == replay["memory_id"]
    assert candidate["state"] == "CANDIDATE"
    with pytest.raises(MemoryIdempotencyConflict):
        _candidate(
            demo_db, task_a, message_a, "candidate-idempotent",
            content="Changed payload under the same idempotency key.",
        )
    with pytest.raises(MemorySourceRejected):
        create_semantic_candidate(
            demo_db, task_a, "support-a", memory_kind="ALIAS", memory_key="other",
            content="A source from another Task must not be accepted.", source_message_id=message_b,
            idempotency_key="semantic-cross-task-source",
        )
    with pytest.raises(MemoryScopeDenied):
        create_semantic_candidate(
            demo_db, task_a, "support-b", memory_kind="ALIAS", memory_key="foreign",
            content="Foreign tenant proposal.", source_message_id=message_a,
            idempotency_key="semantic-cross-tenant-proposal",
        )
    with pytest.raises(MemoryScopeDenied):
        create_semantic_candidate(
            demo_db, task_a, "approver-a", memory_kind="ALIAS", memory_key="wrong-role",
            content="Approvers cannot originate support proposals.", source_message_id=message_a,
            idempotency_key="semantic-wrong-role-proposal",
        )
    with pytest.raises(MemorySourceRejected):
        _candidate(
            demo_db, task_a, message_a, "secret-rejected", memory_key="safe-key",
            content="credential_ref: cred-v2",
        )

    source_context = semantic_memory_context(demo_db, task_a, "support-a")
    assert source_context["source_candidates"][0]["memory_id"] == candidate["memory_id"]
    assert source_context["active_project_memories"] == []
    assert all(item["source_task_id"] != task_b for item in source_context["active_project_memories"])
    assert list_semantic_review_queue(demo_db, "approver-a", state="CANDIDATE")[0]["memory_id"] == candidate["memory_id"]


def test_m303_only_explicitly_granted_same_tenant_approver_can_activate(demo_db: Path) -> None:
    _, task_a, message_a = _session_and_task(demo_db, "grant")
    candidate = _candidate(demo_db, task_a, message_a, "grant-candidate")
    with connect(demo_db) as connection:
        connection.execute(
            "UPDATE semantic_memory_project_approvers SET active = 0 WHERE tenant_id = 'tenant-a' AND actor_id = 'approver-a'"
        )
    with pytest.raises(MemoryScopeDenied):
        confirm_semantic_memory(demo_db, str(candidate["memory_id"]), "approver-a", idempotency_key="grant-rejected")
    with pytest.raises(MemoryScopeDenied):
        confirm_semantic_memory(demo_db, str(candidate["memory_id"]), "approver-b", idempotency_key="tenant-rejected")


def test_m303_cross_task_provider_context_and_revocation_invalidate_answer_source(demo_db: Path) -> None:
    session_id, task_a, message_a = _session_and_task(demo_db, "source")
    task_b, _ = _create_task(demo_db, session_id, "target")
    candidate = _candidate(demo_db, task_a, message_a, "cross-task")
    activated = confirm_semantic_memory(
        demo_db, str(candidate["memory_id"]), "approver-a", idempotency_key="semantic-confirm-cross-task",
    )
    assert activated["state"] == "ACTIVE"
    assert activated["source_task_id"] == task_a != task_b

    with connect(demo_db) as connection:
        source_task_memories, source_excluded = active_semantic_context(connection, task_a)
        target_task_memories, target_excluded = active_semantic_context(connection, task_b)
    assert source_task_memories == []
    assert any(item["source_id"] == candidate["memory_id"] and item["reason"] == "SEMANTIC_MEMORY_SAME_TASK_SOURCE" for item in source_excluded)
    assert [item["memory_id"] for item in target_task_memories] == [candidate["memory_id"]]
    assert target_excluded == []

    from opspilot.investigator import _prompt_messages

    investigator_metadata: dict[str, object] = {}
    investigator_messages = _prompt_messages(
        demo_db, task_b,
        {"evidence_ids": [], "tool_observations": [], "gate_decision": {}, "diagnosis_draft": {}},
        context_metadata=investigator_metadata,
    )
    investigator_payload = "\n".join(str(message.content) for message in investigator_messages)
    assert "confirmed_project_semantic_context" in investigator_payload
    assert "Orders API means the fixed demo orders route." in investigator_payload
    selected_investigator_memories = investigator_metadata["selected_memories"]
    assert any(
        item["memory_id"] == candidate["memory_id"] and item["memory_type"] == "SEMANTIC"
        for item in selected_investigator_memories
    )
    assert_selected_memories_current(demo_db, task_b, selected_investigator_memories)

    identity, first = _prepare_task_chat(demo_db, session_id, task_b, "before-revoke")
    first_manifest = get_chat_manifest(demo_db, identity, str(first["run_id"]))["attempts"][0]["manifest"]
    assert any(item["memory_id"] == candidate["memory_id"] for item in first_manifest["memory_refs"])
    assert any("Orders API means the fixed demo orders route." in str(message["content"]) for message in first["messages"])
    answer = complete_chat_attempt(
        demo_db, str(first["worker_id"]), str(first["attempt_id"]), "Use the project route convention, then verify live facts.",
        provider_response_id="test-response-semantic-on", input_tokens=120, output_tokens=20, total_tokens=140,
    )
    assert answer["status"] == "SUCCEEDED"
    assistant_message_id = str(answer["message_id"])

    revoked = revoke_semantic_memory(
        demo_db, str(candidate["memory_id"]), "approver-a", idempotency_key="semantic-revoke-cross-task",
    )
    assert revoked["state"] == "REVOKED" and revoked["version"] == 2
    with pytest.raises(ContextAssetInvalidated):
        assert_selected_memories_current(demo_db, task_b, selected_investigator_memories)
    refreshed_metadata: dict[str, object] = {}
    refreshed_investigator_messages = _prompt_messages(
        demo_db, task_b,
        {"evidence_ids": [], "tool_observations": [], "gate_decision": {}, "diagnosis_draft": {}},
        context_metadata=refreshed_metadata,
    )
    assert all("Orders API means the fixed demo orders route." not in str(message.content) for message in refreshed_investigator_messages)
    assert all(item["memory_id"] != candidate["memory_id"] for item in refreshed_metadata["selected_memories"])
    assert any(item["reason"] == "SEMANTIC_MEMORY_REVOKED" for item in refreshed_metadata["excluded_sources"])
    identity, second = _prepare_task_chat(demo_db, session_id, task_b, "after-revoke")
    second_manifest = get_chat_manifest(demo_db, identity, str(second["run_id"]))["attempts"][0]["manifest"]
    assert all(item["memory_id"] != candidate["memory_id"] for item in second_manifest["memory_refs"])
    assert all("Orders API means the fixed demo orders route." not in str(message["content"]) for message in second["messages"])
    assert any(
        item.get("message_id") == assistant_message_id
        and item.get("reason") == "MEMORY_REVOKED_EXPIRED_OR_CHANGED"
        for item in second_manifest["excluded_sources"]
    )


def test_m303_revision_requires_current_version_and_preserves_audit_history(demo_db: Path) -> None:
    session_id, task_a, message_a = _session_and_task(demo_db, "revision-source")
    _, task_b, message_b = _session_and_task(demo_db, "revision-proposer")
    original = _candidate(demo_db, task_a, message_a, "revision-original")
    confirm_semantic_memory(demo_db, str(original["memory_id"]), "approver-a", idempotency_key="revision-confirm-original")

    revision = _candidate(
        demo_db, task_b, message_b, "revision-v2", content="Use the fixed demo route only after checking current Domain facts.",
        supersedes_memory_id=str(original["memory_id"]), expected_version=1,
    )
    stale_revision = _candidate(
        demo_db, task_b, message_b, "revision-stale", content="Use a stale route description.",
        supersedes_memory_id=str(original["memory_id"]), expected_version=1,
    )
    confirm_semantic_memory(demo_db, str(revision["memory_id"]), "approver-a", idempotency_key="revision-confirm-v2")
    with pytest.raises(SemanticMemoryConflict):
        confirm_semantic_memory(demo_db, str(stale_revision["memory_id"]), "approver-a", idempotency_key="revision-confirm-stale")
    with connect(demo_db) as connection:
        old = connection.execute("SELECT state, version FROM semantic_memories WHERE memory_id = ?", (original["memory_id"],)).fetchone()
        new = connection.execute("SELECT state, version, supersedes_version FROM semantic_memories WHERE memory_id = ?", (revision["memory_id"],)).fetchone()
        events = [str(row["event_type"]) for row in connection.execute(
            "SELECT event_type FROM semantic_memory_events WHERE memory_id IN (?, ?) ORDER BY occurred_at, event_id",
            (original["memory_id"], revision["memory_id"]),
        )]
    assert tuple(old) == ("REVISED", 1)
    assert tuple(new) == ("ACTIVE", 2, 1)
    assert "REVISED" in events
    assert events.count("CONFIRMED") == 2

    with pytest.raises(SemanticMemoryConflict):
        _candidate(demo_db, task_b, message_b, "unversioned-conflict", content="Conflicting active meaning.")


def test_m303_expiry_is_audited_and_excluded_from_future_context(demo_db: Path) -> None:
    _, task_a, message_a = _session_and_task(demo_db, "expiry-source")
    _, task_b, _ = _session_and_task(demo_db, "expiry-target")
    candidate = _candidate(demo_db, task_a, message_a, "expiry-candidate")
    confirm_semantic_memory(demo_db, str(candidate["memory_id"]), "approver-a", idempotency_key="expiry-confirm")
    with connect(demo_db) as connection:
        past = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat(timespec="milliseconds")
        connection.execute("UPDATE semantic_memories SET expires_at = ? WHERE memory_id = ?", (past, candidate["memory_id"]))
        memories, excluded = active_semantic_context(connection, task_b)
        row = connection.execute("SELECT state, version FROM semantic_memories WHERE memory_id = ?", (candidate["memory_id"],)).fetchone()
        event = connection.execute(
            "SELECT event_type, memory_version FROM semantic_memory_events WHERE memory_id = ? ORDER BY occurred_at DESC, event_id DESC LIMIT 1",
            (candidate["memory_id"],),
        ).fetchone()
    assert memories == []
    assert any(item["source_id"] == candidate["memory_id"] and item["reason"] == "SEMANTIC_MEMORY_EXPIRED" for item in excluded)
    assert tuple(row) == ("EXPIRED", 2)
    assert tuple(event) == ("EXPIRED", 2)


def test_m303_schema_v11_migration_is_repeatable_and_scoped(demo_db: Path) -> None:
    initialize(demo_db)
    _session_and_task(demo_db, "migration-a")
    other_identity = trusted_identity(demo_db, "support-b")
    other_session = str(create_session(demo_db, other_identity)["session_id"])
    _create_task(demo_db, other_session, "migration-b", actor_id="support-b", integration_id="integration-b")
    with connect(demo_db) as connection:
        connection.execute("DELETE FROM semantic_memory_project_approvers")
        connection.execute("PRAGMA user_version = 10")
    initialize(demo_db)
    initialize(demo_db)
    with connect(demo_db) as connection:
        version = int(connection.execute("PRAGMA user_version").fetchone()[0])
        grants = [tuple(row) for row in connection.execute(
            "SELECT tenant_id, project_id, actor_id, active FROM semantic_memory_project_approvers ORDER BY tenant_id, actor_id"
        )]
        foreign_key_errors = connection.execute("PRAGMA foreign_key_check").fetchall()
    assert version == 14
    assert grants == [
        ("tenant-a", "service:orders-demo", "approver-a", 1),
        ("tenant-b", "service:orders-demo", "approver-b", 1),
    ]
    assert foreign_key_errors == []
