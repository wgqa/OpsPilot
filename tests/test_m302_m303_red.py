from __future__ import annotations

from pathlib import Path

from opspilot.domain.chat import get_chat_manifest, prepare_chat_attempt
from opspilot.domain.database import connect, initialize
from opspilot.domain.task_control import (
    admit_task_message,
    claim_task_run,
    create_session,
    register_worker_owner,
    trusted_identity,
)


def test_ctx08_chat_manifest_has_token_budget_and_strategy(demo_db: Path) -> None:
    identity = trusted_identity(demo_db, "support-a")
    session_id = str(create_session(demo_db, identity)["session_id"])
    admitted = admit_task_message(
        demo_db, identity, session_id=session_id, task_id=None,
        input_kind="CHAT_READONLY", body="Orders are failing; do not assume recovery.",
        idempotency_key="m302-red-context-budget",
    )
    run_id = str(admitted["run_id"])
    register_worker_owner(demo_db, "m302-red-worker", 64001)
    claim_task_run(demo_db, identity, run_id)
    prepare_chat_attempt(demo_db, run_id, "m302-red-worker", "test-model")

    manifest = get_chat_manifest(demo_db, identity, run_id)["attempts"][0]["manifest"]

    assert manifest["context_budget"]["strategy"] == "HYBRID"
    assert manifest["context_budget"]["estimated_input_tokens"] >= 1
    assert "provider_usage" not in manifest["context_budget"]


def test_ctx05_summary_dependency_dag_tables_exist_after_v9_migration(demo_db: Path) -> None:
    initialize(demo_db)
    with connect(demo_db) as connection:
        schema_version = int(connection.execute("PRAGMA user_version").fetchone()[0])
        summary_tables = {
            str(row["name"])
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }

    assert schema_version >= 10
    assert "context_summaries" in summary_tables
    assert "context_summary_dependencies" in summary_tables


def test_mem04_semantic_memory_has_versioned_audit_storage(demo_db: Path) -> None:
    initialize(demo_db)
    with connect(demo_db) as connection:
        tables = {
            str(row["name"])
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
        version_columns = {
            str(row["name"])
            for row in connection.execute("PRAGMA table_info(semantic_memories)").fetchall()
        } if "semantic_memories" in tables else set()

    assert "semantic_memories" in tables
    assert {"memory_id", "version", "state", "tenant_id", "project_id", "source_refs_json"}.issubset(version_columns)
    assert "semantic_memory_events" in tables
