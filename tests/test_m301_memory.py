from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from opspilot.domain.d2 import (
    create_task_binding,
    finish_attempt,
    get_scope_authz_facts_fact,
    probe_endpoint_fact,
    record_tool_observation,
    reserve_attempt,
)
from opspilot.domain.database import connect, initialize, reset_fixture
from opspilot.domain.d2 import canonical_json, digest_json
from opspilot.domain.episodic_memory import (
    MemoryIdempotencyConflict,
    MemoryScopeDenied,
    MemorySourceRejected,
    _memory_content_digest,
    confirm_memory,
    create_memory_candidate,
    list_applicable_memories,
    revoke_memory,
    select_applicable_memories,
)
from opspilot.domain.s2_diagnosis import create_diagnosis_receipt, freeze_handoff_draft
from opspilot.domain.s2_handoff import submit_s2_handoff
from opspilot.domain.task_control import (
    apply_pending_critical_inputs,
    claim_task_run,
    create_task_with_initial_run,
    create_session,
    finish_task_run,
    trusted_identity,
)
from opspilot.web.app import create_app


PASSWORDS = {
    "support-a": "support-test-password",
    "approver-a": "approver-test-password",
    "support-b": "support-b-test-password",
    "approver-b": "approver-b-test-password",
}
ORIGIN = "http://testserver"


def _s2_case(
    db: Path, live_api: str, prefix: str, *, handoff: bool = False, reset: bool = True,
) -> dict[str, object]:
    if reset:
        reset_fixture(db, "S2_SCOPE_DENIED")
    identity = trusted_identity(db, "support-a")
    from opspilot.domain.task_control import create_session

    session_id = str(create_session(db, identity)["session_id"])
    created = create_task_with_initial_run(
        db, identity, session_id=session_id, service_id="orders-demo",
        integration_id="integration-a", ticket_id=f"{prefix}-ticket",
        initial_message="订单接口似乎无法访问，请核实绑定任务的真实授权事实。",
        idempotency_key=f"{prefix}-task",
    )
    task_id, run_id = str(created["task_id"]), str(created["run_id"])
    claim_task_run(db, identity, run_id)
    apply_pending_critical_inputs(db, identity, run_id)

    probe = probe_endpoint_fact(db, task_id, "orders-demo", "integration-a", live_api)
    assert probe["facts"]["http_status"] == 403
    probe_call = f"{prefix}-probe-call"
    probe_attempt, _ = reserve_attempt(
        db, task_id, "MCP", 6, call_id=probe_call, tool_call_id=f"{prefix}-probe-tool",
        tool_name="probe_endpoint", argument_digest=f"{prefix}-probe-args", run_id=run_id,
    )
    finish_attempt(db, probe_attempt, "OK")
    probe_observation = record_tool_observation(
        db, task_id=task_id, call_id=probe_call, attempt_id=probe_attempt,
        tool_call_id=f"{prefix}-probe-tool", tool_name="probe_endpoint",
        arguments={"service_id": "orders-demo", "integration_id": "integration-a"},
        status="OK", result=probe,
    )

    request_id = str(probe["facts"]["request_id"])
    authz = get_scope_authz_facts_fact(db, task_id, request_id)
    authz_call = f"{prefix}-authz-call"
    authz_attempt, _ = reserve_attempt(
        db, task_id, "MCP", 6, call_id=authz_call, tool_call_id=f"{prefix}-authz-tool",
        tool_name="get_scope_authz_facts", argument_digest=f"{prefix}-authz-args", run_id=run_id,
    )
    finish_attempt(db, authz_attempt, "OK")
    authz_observation = record_tool_observation(
        db, task_id=task_id, call_id=authz_call, attempt_id=authz_attempt,
        tool_call_id=f"{prefix}-authz-tool", tool_name="get_scope_authz_facts",
        arguments={"request_id": request_id}, status="OK", result=authz,
    )
    receipt = create_diagnosis_receipt(
        db, task_id=task_id, run_id=run_id,
        evidence_ids=[str(probe_observation["evidence_id"]), str(authz_observation["evidence_id"])],
    )
    result: dict[str, object] = {"task_id": task_id, "run_id": run_id, "receipt": receipt}
    if handoff:
        draft = freeze_handoff_draft(db, task_id=task_id, receipt_id=str(receipt["receipt_id"]))
        finish_task_run(db, identity, run_id, "SUCCEEDED")
        with connect(db) as connection:
            revision = int(connection.execute(
                "SELECT control_revision FROM task_controls WHERE task_id = ?", (task_id,),
            ).fetchone()[0])
        result["draft"] = draft
        result["handoff"] = submit_s2_handoff(
            db, identity, task_id=task_id, operation_id=f"{prefix}-handoff-operation",
            draft_id=str(draft["draft_id"]), draft_digest=str(draft["content_digest"]),
            expected_control_revision=revision, handoff_kind="SCOPE_REVIEW",
        )
    return result


def _s1_401_case(db: Path, live_api: str, prefix: str) -> dict[str, object]:
    """Create one real same-Run 401 Probe without clearing existing source Memories."""
    with connect(db) as connection:
        connection.execute(
            "UPDATE integrations SET credential_ref = 'cred-v1', config_version = config_version + 1 "
            "WHERE tenant_id = 'tenant-a' AND integration_id = 'integration-a'"
        )
    identity = trusted_identity(db, "support-a")
    session_id = str(create_session(db, identity)["session_id"])
    created = create_task_with_initial_run(
        db, identity, session_id=session_id, service_id="orders-demo",
        integration_id="integration-a", ticket_id=f"{prefix}-ticket",
        initial_message="订单接口未认证，请用实际响应核实当前状态。",
        idempotency_key=f"{prefix}-task",
    )
    task_id, run_id = str(created["task_id"]), str(created["run_id"])
    claim_task_run(db, identity, run_id)
    apply_pending_critical_inputs(db, identity, run_id)
    probe = probe_endpoint_fact(db, task_id, "orders-demo", "integration-a", live_api)
    assert probe["facts"]["http_status"] == 401
    call_id = f"{prefix}-probe-call"
    attempt, _ = reserve_attempt(
        db, task_id, "MCP", 6, call_id=call_id, tool_call_id=f"{prefix}-probe-tool",
        tool_name="probe_endpoint", argument_digest=f"{prefix}-probe-args", run_id=run_id,
    )
    finish_attempt(db, attempt, "OK")
    record_tool_observation(
        db, task_id=task_id, call_id=call_id, attempt_id=attempt,
        tool_call_id=f"{prefix}-probe-tool", tool_name="probe_endpoint",
        arguments={"service_id": "orders-demo", "integration_id": "integration-a"},
        status="OK", result=probe,
    )
    return {"task_id": task_id, "run_id": run_id}


def test_s2_diagnosed_and_scope_escalated_cases_have_distinct_real_sources(
    demo_db: Path, live_api: str,
) -> None:
    diagnosed = _s2_case(demo_db, live_api, "m301-diagnosed")
    task_a = str(diagnosed["task_id"])
    candidate = create_memory_candidate(demo_db, task_a, "support-a", idempotency_key="m301-candidate-s2")
    assert candidate["problem_type"] == "auth_403_scope"
    assert candidate["source_outcome"] == "DIAGNOSED"
    assert candidate["source_report_ref"] is None and candidate["source_verification_id"] is None
    assert candidate["schema_version"] == "opspilot-case-memory-v1"
    assert candidate["experience"]["source_authority"] == "HISTORICAL_METHOD_HINT_ONLY"
    assert candidate["experience"]["case_specific_facts"]["http_status"] == 403
    assert candidate["experience"]["case_specific_facts"]["missing_scopes"]
    assert {ref["kind"] for ref in candidate["source_refs"]} == {"DIAGNOSIS_RECEIPT", "EVIDENCE"}
    assert candidate["content_digest"] == _memory_content_digest(candidate)

    active = confirm_memory(
        demo_db, str(candidate["memory_id"]), "approver-a", idempotency_key="m301-confirm-s2",
    )
    target = create_task_binding(demo_db, "support-a", "orders-demo", "integration-a")
    assert target["task_id"] != task_a
    assert list_applicable_memories(demo_db, str(target["task_id"]), "auth_403_scope")[0]["memory_id"] == candidate["memory_id"]
    assert list_applicable_memories(demo_db, task_a, "auth_403_scope") == []

    escalated = _s2_case(demo_db, live_api, "m301-escalated", handoff=True)
    handoff_candidate = create_memory_candidate(
        demo_db, str(escalated["task_id"]), "support-a", idempotency_key="m301-candidate-escalated",
    )
    assert handoff_candidate["source_outcome"] == "SCOPE_ESCALATED"
    assert handoff_candidate["source_report_ref"] is None and handoff_candidate["source_verification_id"] is None
    assert {ref["kind"] for ref in handoff_candidate["source_refs"]} == {
        "DIAGNOSIS_RECEIPT", "EVIDENCE", "HANDOFF_RECEIPT", "HANDOFF_QUEUE_ENTRY",
    }
    assert handoff_candidate["experience"]["case_specific_facts"]["http_status"] == 403
    assert "not a permission grant" in " ".join(handoff_candidate["experience"]["limitations"])


def test_memory_commands_are_idempotent_owner_scoped_and_revocation_is_final(
    demo_db: Path, live_api: str,
) -> None:
    case = _s2_case(demo_db, live_api, "m301-command")
    task_id = str(case["task_id"])
    first = create_memory_candidate(demo_db, task_id, "support-a", idempotency_key="m301-key-candidate")
    replay = create_memory_candidate(demo_db, task_id, "support-a", idempotency_key="m301-key-candidate")
    assert replay["memory_id"] == first["memory_id"]
    other_task = create_task_binding(demo_db, "support-a", "orders-demo", "integration-a")
    with pytest.raises(MemoryIdempotencyConflict):
        create_memory_candidate(demo_db, str(other_task["task_id"]), "support-a", idempotency_key="m301-key-candidate")
    with pytest.raises(MemoryScopeDenied):
        create_memory_candidate(demo_db, task_id, "support-b", idempotency_key="m301-wrong-owner")

    active = confirm_memory(demo_db, str(first["memory_id"]), "approver-a", idempotency_key="m301-key-confirm")
    assert confirm_memory(demo_db, str(first["memory_id"]), "approver-a", idempotency_key="m301-key-confirm")["state"] == "ACTIVE"
    revoked = revoke_memory(demo_db, str(first["memory_id"]), "approver-a", idempotency_key="m301-key-revoke")
    assert revoked["state"] == "REVOKED" and revoked["version"] == active["version"] + 1
    assert revoke_memory(demo_db, str(first["memory_id"]), "approver-a", idempotency_key="m301-key-revoke")["state"] == "REVOKED"
    with pytest.raises(MemorySourceRejected, match="never revive"):
        confirm_memory(demo_db, str(first["memory_id"]), "approver-a", idempotency_key="m301-confirm-after-revoke")
    with connect(demo_db) as connection:
        events = connection.execute(
            "SELECT event_type FROM d5_memory_events WHERE memory_id = ? ORDER BY rowid",
            (first["memory_id"],),
        ).fetchall()
        commands = connection.execute(
            "SELECT command_kind FROM commands WHERE target_ref = ? AND command_kind LIKE 'MEMORY_%'",
            (task_id,),
        ).fetchall()
    assert [row["event_type"] for row in events] == ["CANDIDATE_CREATED", "CONFIRMED", "REVOKED"]
    assert [row["command_kind"] for row in commands] == ["MEMORY_CANDIDATE_CREATE"]


def test_s2_case_memory_is_in_real_investigator_prompt_for_different_task_only(
    demo_db: Path, live_api: str,
) -> None:
    from opspilot.investigator import _prompt_messages

    source = _s2_case(demo_db, live_api, "m301-prompt-source")
    task_a = str(source["task_id"])
    candidate = create_memory_candidate(
        demo_db, task_a, "support-a", idempotency_key="m301-prompt-candidate",
    )
    confirm_memory(
        demo_db, str(candidate["memory_id"]), "approver-a",
        idempotency_key="m301-prompt-confirm",
    )
    target = _s2_case(demo_db, live_api, "m301-prompt-target", reset=False)
    task_b, run_b = str(target["task_id"]), str(target["run_id"])
    assert task_b != task_a

    enabled_metadata: dict[str, object] = {}
    enabled_messages = _prompt_messages(
        demo_db, task_b, {"task_binding_id": task_b, "evidence_ids": []},
        context_metadata=enabled_metadata, run_id=run_b, s2_mode=True,
    )
    enabled_prompt = "\n".join(str(item.content) for item in enabled_messages)
    assert str(candidate["memory_id"]) in enabled_prompt
    selected = enabled_metadata["selected_memories"]
    assert isinstance(selected, list) and selected[0]["source_task_id"] == task_a
    assert selected[0]["source_outcome"] == "DIAGNOSED"
    assert selected[0]["content_digest"] == candidate["content_digest"]
    assert selected[0]["applicability_reason"] == (
        "EXACT_PROBLEM_TYPE_AND_SERVICE; ACTIVE; NOT_EXPIRED; SOURCE_CURRENT"
    )
    assert selected[0]["memory_type"] == "EPISODIC"

    disabled_metadata: dict[str, object] = {}
    disabled_messages = _prompt_messages(
        demo_db, task_b, {"task_binding_id": task_b, "evidence_ids": []},
        context_metadata=disabled_metadata, run_id=run_b, s2_mode=True, memory_enabled=False,
    )
    disabled_prompt = "\n".join(str(item.content) for item in disabled_messages)
    assert str(candidate["memory_id"]) not in disabled_prompt
    assert disabled_metadata["selected_memories"] == []


def test_s2_case_memory_does_not_cross_into_a_current_401_task(
    demo_db: Path, live_api: str,
) -> None:
    from opspilot.investigator import _prompt_messages

    source = _s2_case(demo_db, live_api, "m301-cross-type-source")
    candidate = create_memory_candidate(
        demo_db, str(source["task_id"]), "support-a", idempotency_key="m301-cross-type-candidate",
    )
    confirm_memory(
        demo_db, str(candidate["memory_id"]), "approver-a",
        idempotency_key="m301-cross-type-confirm",
    )
    target = _s1_401_case(demo_db, live_api, "m301-cross-type-target")
    task_b, run_b = str(target["task_id"]), str(target["run_id"])
    metadata: dict[str, object] = {}
    prompt = "\n".join(str(item.content) for item in _prompt_messages(
        demo_db, task_b, {"task_binding_id": task_b, "evidence_ids": []},
        context_metadata=metadata, run_id=run_b, s2_mode=True,
    ))
    assert candidate["memory_id"] not in prompt
    assert metadata["selected_memories"] == []
    assert any(
        item["source_id"] == candidate["memory_id"] and item["reason"] == "PROBLEM_TYPE_MISMATCH"
        for item in metadata["excluded_sources"]
    )


def test_m301_memory_retrieval_records_applicability_and_selection_limits(
    demo_db: Path, live_api: str,
) -> None:
    first_source = _s2_case(demo_db, live_api, "m301-retrieval-first")
    first = create_memory_candidate(
        demo_db, str(first_source["task_id"]), "support-a", idempotency_key="m301-retrieval-candidate-1",
    )
    confirm_memory(demo_db, str(first["memory_id"]), "approver-a", idempotency_key="m301-retrieval-confirm-1")

    second_source = _s2_case(demo_db, live_api, "m301-retrieval-second", reset=False)
    second = create_memory_candidate(
        demo_db, str(second_source["task_id"]), "support-a", idempotency_key="m301-retrieval-candidate-2",
    )
    confirm_memory(demo_db, str(second["memory_id"]), "approver-a", idempotency_key="m301-retrieval-confirm-2")

    target = _s2_case(demo_db, live_api, "m301-retrieval-target", reset=False)
    task_b = str(target["task_id"])
    selected, excluded = select_applicable_memories(demo_db, task_b, "auth_403_scope", limit=2)
    assert {item["memory_id"] for item in selected} == {first["memory_id"], second["memory_id"]}
    assert all(item["applicability_reason"].startswith("EXACT_PROBLEM_TYPE_AND_SERVICE") for item in selected)
    assert excluded == []

    one_selected, one_excluded = select_applicable_memories(demo_db, task_b, "auth_403_scope", limit=1)
    assert len(one_selected) == 1
    assert any(item["reason"] == "MAX_SELECTION_LIMIT" for item in one_excluded)
    _, wrong_condition = select_applicable_memories(demo_db, task_b, "auth_401", limit=2)
    assert {item["reason"] for item in wrong_condition} == {"PROBLEM_TYPE_MISMATCH"}


def test_m301_web_memory_lifecycle_uses_session_roles_and_idempotency(
    demo_db: Path, live_api: str, tmp_path: Path,
) -> None:
    case = _s2_case(demo_db, live_api, "m301-web")
    task_id = str(case["task_id"])
    app = create_app(
        db_path=demo_db, checkpoint_db_path=tmp_path / "checkpoints.sqlite3",
        start_worker=False, credentials=PASSWORDS, expected_origin=ORIGIN,
    )
    with TestClient(app, raise_server_exceptions=False) as client:
        support_login = client.post(
            "/api/auth/login", headers={"Origin": ORIGIN},
            json={"actor_id": "support-a", "password": PASSWORDS["support-a"]},
        )
        support = {"Origin": ORIGIN, "X-CSRF-Token": support_login.json()["csrf_token"]}
        task_page = client.get(f"/api/tasks/{task_id}/memories", headers=support)
        assert task_page.status_code == 200, task_page.text
        candidate_response = client.post(
            f"/api/tasks/{task_id}/memories/candidates",
            headers={**support, "Idempotency-Key": "m301-web-create"}, json={},
        )
        assert candidate_response.status_code == 201, candidate_response.text
        memory_id = candidate_response.json()["memory_id"]
        replay_response = client.post(
            f"/api/tasks/{task_id}/memories/candidates",
            headers={**support, "Idempotency-Key": "m301-web-create"}, json={},
        )
        assert replay_response.status_code == 201 and replay_response.json()["memory_id"] == memory_id
        forged_source = client.post(
            f"/api/tasks/{task_id}/memories/candidates",
            headers={**support, "Idempotency-Key": "m301-web-forged-source"},
            json={"source_outcome": "SCOPE_ESCALATED", "experience": {"scope_authorized": True}},
        )
        assert forged_source.status_code == 422
        missing_key = client.post(
            f"/api/tasks/{task_id}/memories/candidates", headers=support, json={},
        )
        assert missing_key.status_code == 400

        wrong_approver_login = client.post(
            "/api/auth/login", headers={"Origin": ORIGIN},
            json={"actor_id": "approver-b", "password": PASSWORDS["approver-b"]},
        )
        wrong_approver = {"Origin": ORIGIN, "X-CSRF-Token": wrong_approver_login.json()["csrf_token"]}
        assert client.get(f"/api/memories/{memory_id}", headers=wrong_approver).status_code == 404
        assert client.post(
            f"/api/memories/{memory_id}/confirm",
            headers={**wrong_approver, "Idempotency-Key": "m301-web-wrong-confirm"}, json={},
        ).status_code == 403

        approver_login = client.post(
            "/api/auth/login", headers={"Origin": ORIGIN},
            json={"actor_id": "approver-a", "password": PASSWORDS["approver-a"]},
        )
        approver = {"Origin": ORIGIN, "X-CSRF-Token": approver_login.json()["csrf_token"]}
        inventory = client.get("/api/memories?state=CANDIDATE", headers=approver)
        assert inventory.status_code == 200 and inventory.json()["items"][0]["memory_id"] == memory_id
        confirmed = client.post(
            f"/api/memories/{memory_id}/confirm",
            headers={**approver, "Idempotency-Key": "m301-web-confirm"}, json={},
        )
        assert confirmed.status_code == 200 and confirmed.json()["state"] == "ACTIVE"
        active_inventory = client.get("/api/memories?state=ACTIVE", headers=approver)
        assert active_inventory.status_code == 200
        assert any(item["memory_id"] == memory_id for item in active_inventory.json()["items"])
        revoked = client.post(
            f"/api/memories/{memory_id}/revoke",
            headers={**approver, "Idempotency-Key": "m301-web-revoke"}, json={},
        )
        assert revoked.status_code == 200 and revoked.json()["state"] == "REVOKED"


def test_v8_schema_migration_preserves_rows_events_refs_and_can_rerun(demo_db: Path) -> None:
    binding = create_task_binding(demo_db, "support-a", "orders-demo", "integration-a")
    task_id = str(binding["task_id"])
    now = datetime.now(timezone.utc).isoformat(timespec="milliseconds")
    with connect(demo_db) as connection:
        connection.execute("DROP INDEX IF EXISTS ix_d5_memories_lookup")
        connection.execute("DROP TABLE d5_memory_events")
        connection.execute("DROP TABLE d5_memories")
        connection.execute(
            """CREATE TABLE d5_memories (
                 memory_id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL REFERENCES tenants(tenant_id),
                 project_id TEXT NOT NULL, type TEXT NOT NULL CHECK(type='EPISODIC'), problem_type TEXT NOT NULL,
                 summary TEXT NOT NULL, applicability_constraints_json TEXT NOT NULL,
                 source_task_id TEXT NOT NULL REFERENCES task_bindings(task_id), source_evidence_ids_json TEXT NOT NULL,
                 source_report_ref TEXT NOT NULL, source_verification_id TEXT NOT NULL,
                 state TEXT NOT NULL CHECK(state IN ('CANDIDATE','ACTIVE','REVOKED')), version INTEGER NOT NULL,
                 confirmed_by TEXT, confirmed_at TEXT, revoked_by TEXT, revoked_at TEXT,
                 expires_at TEXT NOT NULL, created_at TEXT NOT NULL,
                 UNIQUE(tenant_id, project_id, problem_type, source_task_id))"""
        )
        connection.execute(
            """CREATE TABLE d5_memory_events (
                 event_id TEXT PRIMARY KEY, memory_id TEXT NOT NULL REFERENCES d5_memories(memory_id),
                 tenant_id TEXT NOT NULL, project_id TEXT NOT NULL,
                 event_type TEXT NOT NULL CHECK(event_type IN ('CANDIDATE_CREATED','CONFIRMED','REVOKED')),
                 actor_id TEXT NOT NULL, memory_version INTEGER NOT NULL, occurred_at TEXT NOT NULL,
                 details_json TEXT NOT NULL)"""
        )
        connection.execute(
            """INSERT INTO d3_verification_receipts
               (verification_id, tenant_id, task_id, plan_hash, repair_action_id, service_id, integration_id,
                principal_id, business_route, probe_observed_versions_json, observed_at, response_status,
                business_assertions_json, recovery_verified, result_digest)
               VALUES ('migration-verification', 'tenant-a', ?, 'migration-plan', 'migration-action',
                       'orders-demo', 'integration-a', 'principal-a', '/api/orders/demo-order', '{}', ?, 200,
                       '{}', 1, 'verification-digest')""",
            (task_id, now),
        )
        connection.execute(
            """INSERT INTO d3_report_artifacts
               (report_ref, tenant_id, task_id, plan_hash, repair_action_id, verification_id, report_version,
                content_digest, immutable_content_json, created_at)
               VALUES ('migration-report', 'tenant-a', ?, 'migration-plan', 'migration-action',
                       'migration-verification', 1, 'report-digest', '{}', ?)""",
            (task_id, now),
        )
        connection.execute(
            """INSERT INTO d2_evidence
               (evidence_id, tenant_id, task_id, call_id, tool_call_id, resource_id, principal_id,
                data_source, fetched_at, observed_versions_json, fact_type, facts_json,
                original_result_ref, trust_class, digest)
               VALUES ('migration-evidence', 'tenant-a', ?, 'c', 't', 'r', 'principal-a', 'MCP', ?, '{}',
                       'endpoint_probe', '{}', 'ref', 'untrusted_tool_observation', 'evidence-digest')""",
            (task_id, now),
        )
        connection.execute(
            """INSERT INTO d5_memories
               (memory_id, tenant_id, project_id, type, problem_type, summary, applicability_constraints_json,
                source_task_id, source_evidence_ids_json, source_report_ref, source_verification_id,
                state, version, expires_at, created_at)
               VALUES ('legacy-memory', 'tenant-a', 'service:orders-demo', 'EPISODIC', 'auth_401',
                       'preserved fixed D5 guidance', '{}', ?, '[\"migration-evidence\"]',
                       'migration-report', 'migration-verification', 'ACTIVE', 4, '2999-01-01T00:00:00+00:00', ?)""",
            (task_id, now),
        )
        connection.execute(
            """INSERT INTO d5_memory_events
               VALUES ('legacy-event', 'legacy-memory', 'tenant-a', 'service:orders-demo',
                       'CANDIDATE_CREATED', 'support-a', 1, ?, '{}')""",
            (now,),
        )
        connection.execute("PRAGMA user_version = 8")

    initialize(demo_db)
    initialize(demo_db)
    with connect(demo_db) as connection:
        assert int(connection.execute("PRAGMA user_version").fetchone()[0]) == 13
        context_columns = {
            str(row["name"])
            for row in connection.execute("PRAGMA table_info(d5_context_provenance)").fetchall()
        }
        assert {"context_budget_json", "context_blocks_json", "summary_refs_json", "excluded_sources_json"}.issubset(context_columns)
        context_tables = {
            str(row["name"])
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
        }
        assert {
            "context_compression_attempts", "context_summaries", "context_summary_dependencies",
            "semantic_memories", "semantic_memory_events", "semantic_memory_project_approvers",
        }.issubset(context_tables)
        rows = connection.execute("SELECT * FROM d5_memories WHERE memory_id='legacy-memory'").fetchall()
        events = connection.execute("SELECT * FROM d5_memory_events WHERE memory_id='legacy-memory'").fetchall()
        foreign_keys = connection.execute("PRAGMA foreign_key_list(d5_memory_events)").fetchall()
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
    assert len(rows) == 1 and len(events) == 1
    migrated = dict(rows[0])
    assert migrated["summary"] == "preserved fixed D5 guidance"
    assert migrated["state"] == "ACTIVE" and migrated["version"] == 4
    assert migrated["schema_version"] == "d5-legacy-v1"
    assert migrated["source_outcome"] == "REPAIRED_VERIFIED"
    refs = json.loads(migrated["source_refs_json"])
    assert {(ref["kind"], ref["id"]) for ref in refs} == {
        ("EVIDENCE", "migration-evidence"),
        ("FROZEN_REPORT", "migration-report"),
        ("VERIFICATION_RECEIPT", "migration-verification"),
    }
    assert migrated["content_digest"] == _memory_content_digest(migrated)
    assert any(str(item["table"]) == "d5_memories" for item in foreign_keys)

