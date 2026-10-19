from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from opspilot.domain.d2 import (
    canonical_json,
    create_task_binding,
    digest_json,
    reserve_attempt,
)
from opspilot.domain.database import connect
from opspilot.domain.episodic_memory import (
    ContextAssetInvalidated,
    MemoryScopeDenied,
    MemorySourceRejected,
    SkillCompatibilityError,
    assert_task_skill_compatible,
    confirm_memory,
    create_memory_candidate,
    finish_context_provenance,
    list_applicable_memories,
    list_context_provenance,
    revoke_memory,
)
from opspilot.investigator import PROMPT_VERSION, _prompt_messages
from opspilot.skill_assets import SkillIntegrityError, load_applicable_skill


def _seed_verified_source(db: Path, task_id: str) -> str:
    binding = create_task_binding(db, "support-a", "orders-demo", "integration-a")
    task_id = str(binding["task_id"])
    action_id = f"repair-{task_id}"
    plan_hash = f"plan-{task_id}"
    verification_id = f"verification-{task_id}"
    report_ref = f"report-{task_id}"
    evidence_id = f"evidence-{task_id}"
    now = datetime.now(timezone.utc).isoformat(timespec="milliseconds")
    assertions = {
        "same_tenant": True,
        "same_service": True,
        "same_integration": True,
        "same_principal": True,
        "same_business_route": True,
        "order_id_matches": True,
        "order_status_matches": True,
        "expected_post_repair_versions": True,
        "response_body": {"order_id": "demo-order", "status": "CONFIRMED"},
    }
    probe_versions = {"before": {"config_version": 7}, "after": {"config_version": 7}}
    probe_facts = {
        "service_id": "orders-demo", "integration_id": "integration-a", "principal_id": "principal-a",
        "route": "/api/orders/demo-order", "http_status": 401, "request_id": "initial-401-request",
        "auth_event_id": 1, "authz_event_id": None, "auth_event_result": "AUTH_REJECTED",
        "auth_event_scope_valid": True, "versions_stable_during_probe": True,
    }
    evidence_digest = digest_json({
        "tenant_id": "tenant-a", "task_id": task_id, "fact_type": "endpoint_probe",
        "resource_id": "orders-demo:integration-a:/api/orders/demo-order", "principal_id": "principal-a",
        "data_source": "http:loopback-demo-business-api", "observed_versions": probe_versions,
        "facts": probe_facts, "trust_class": "untrusted_tool_observation",
    })
    verification_assertions = {**assertions, "request_id": "verify-request", "auth_event_id": 2}
    verification_versions = {"config_version": 8, "principal_version": 1, "auth_policy_version": 1}
    verification_digest = digest_json({
        "tenant_id": "tenant-a", "task_id": task_id, "plan_hash": plan_hash,
        "repair_action_id": action_id, "service_id": "orders-demo", "integration_id": "integration-a",
        "principal_id": "principal-a", "business_route": "/api/orders/demo-order",
        "request_id": "verify-request", "auth_event_id": 2,
        "observed_versions": verification_versions, "response_status": 200,
        "response_body": assertions["response_body"], "business_assertions": {
            key: value for key, value in assertions.items() if key != "response_body"
        }, "recovery_verified": True,
    })
    report_body = {
        "schema_version": "opspilot-d3-report-v1",
        "business_outcome": "RECOVERED",
        "tenant_id": "tenant-a",
        "task_id": task_id,
        "plan_hash": plan_hash,
        "repair_ledger": {"action_id": action_id, "status": "COMMITTED"},
        "verification_receipt": {
            "verification_id": verification_id,
            "response_status": 200,
            "recovery_verified": True,
        },
        "evidence": [{"evidence_id": evidence_id, "fact_type": "endpoint_probe"}],
    }
    report_content = canonical_json(report_body)
    with connect(db) as connection:
        connection.execute(
            """INSERT INTO d3_action_intents
               (action_id, tenant_id, task_id, plan_hash, action_kind, idempotency_key,
                approval_id, canonical_request_json, request_digest, created_at)
               VALUES (?, 'tenant-a', ?, ?, 'REPAIR', ?, ?, '{}', ?, ?)""",
            (action_id, task_id, plan_hash, f"key-{task_id}", f"approval-{task_id}", digest_json({}), now),
        )
        connection.execute(
            """INSERT INTO d3_action_ledgers
               (ledger_id, tenant_id, task_id, plan_hash, action_kind, action_id,
                idempotency_key, request_digest, approval_id, status, before_version,
                after_version, result_json, result_digest, committed_at)
               VALUES (?, 'tenant-a', ?, ?, 'REPAIR', ?, ?, ?, ?, 'COMMITTED', 7, 8, ?, ?, ?)""",
            (f"ledger-{task_id}", task_id, plan_hash, action_id, f"key-{task_id}", digest_json({}), f"approval-{task_id}", canonical_json({"status": "COMMITTED"}), digest_json({"status": "COMMITTED"}), now),
        )
        connection.execute(
            """INSERT INTO d3_verification_receipts
               (verification_id, tenant_id, task_id, plan_hash, repair_action_id,
                service_id, integration_id, principal_id, business_route,
                probe_observed_versions_json, observed_at, response_status,
                business_assertions_json, recovery_verified, result_digest)
               VALUES (?, 'tenant-a', ?, ?, ?, 'orders-demo', 'integration-a', 'principal-a',
                       '/api/orders/demo-order', ?, ?, 200, ?, 1, ?)""",
            (verification_id, task_id, plan_hash, action_id, canonical_json(verification_versions), now,
             canonical_json(verification_assertions), verification_digest),
        )
        connection.execute(
            """INSERT INTO d2_evidence
               (evidence_id, tenant_id, task_id, call_id, tool_call_id, resource_id,
                principal_id, data_source, fetched_at, observed_versions_json, fact_type,
                facts_json, original_result_ref, trust_class, digest)
               VALUES (?, 'tenant-a', ?, ?, ?, 'orders-demo:integration-a:/api/orders/demo-order',
                       'principal-a', 'http:loopback-demo-business-api', ?, ?,
                       'endpoint_probe', ?, 'probe-ref', 'untrusted_tool_observation', ?)""",
            (evidence_id, task_id, f"call-{task_id}", f"tool-{task_id}", now,
             canonical_json(probe_versions), canonical_json(probe_facts), evidence_digest),
        )
        connection.execute(
            """INSERT INTO d3_report_artifacts
               (report_ref, tenant_id, task_id, plan_hash, repair_action_id, verification_id,
                report_version, content_digest, immutable_content_json, created_at)
               VALUES (?, 'tenant-a', ?, ?, ?, ?, 1, ?, ?, ?)""",
            (report_ref, task_id, plan_hash, action_id, verification_id, hashlib.sha256(report_content.encode("utf-8")).hexdigest(), report_content, now),
        )
    return task_id


def test_memory_candidate_requires_real_domain_links_and_manual_lifecycle(demo_db: Path) -> None:
    with pytest.raises(MemorySourceRejected):
        create_memory_candidate(demo_db, str(create_task_binding(demo_db, "support-a", "orders-demo", "integration-a")["task_id"]), "support-a")

    task_id = _seed_verified_source(demo_db, "unused")
    candidate = create_memory_candidate(demo_db, task_id, "support-a")
    repeated = create_memory_candidate(demo_db, task_id, "support-a")
    assert candidate["state"] == "CANDIDATE"
    assert candidate["version"] == 1
    assert candidate["memory_id"] == repeated["memory_id"]

    target = create_task_binding(demo_db, "support-a", "orders-demo", "integration-a")
    assert list_applicable_memories(demo_db, str(target["task_id"]), "auth_401") == []
    with pytest.raises(MemoryScopeDenied):
        confirm_memory(demo_db, str(candidate["memory_id"]), "support-a")

    active = confirm_memory(demo_db, str(candidate["memory_id"]), "approver-a")
    same_active = confirm_memory(demo_db, str(candidate["memory_id"]), "approver-a")
    assert active["state"] == "ACTIVE" and active["version"] == 2
    assert same_active["version"] == active["version"]
    assert [item["memory_id"] for item in list_applicable_memories(demo_db, str(target["task_id"]), "auth_401")] == [candidate["memory_id"]]

    revoked = revoke_memory(demo_db, str(candidate["memory_id"]), "approver-a")
    assert revoked["state"] == "REVOKED" and revoked["version"] == 3
    assert list_applicable_memories(demo_db, str(target["task_id"]), "auth_401") == []
    with pytest.raises(MemorySourceRejected, match="never revive"):
        confirm_memory(demo_db, str(candidate["memory_id"]), "approver-a")
    with connect(demo_db) as connection:
        events = connection.execute(
            "SELECT event_type, memory_version FROM d5_memory_events WHERE memory_id = ? ORDER BY occurred_at, rowid",
            (candidate["memory_id"],),
        ).fetchall()
    assert [(row["event_type"], row["memory_version"]) for row in events] == [
        ("CANDIDATE_CREATED", 1), ("CONFIRMED", 2), ("REVOKED", 3)
    ]


def test_memory_expiry_tenant_and_project_filters(demo_db: Path) -> None:
    task_a = _seed_verified_source(demo_db, "unused")
    memory = create_memory_candidate(demo_db, task_a, "support-a")
    active = confirm_memory(demo_db, str(memory["memory_id"]), "approver-a")
    other_tenant = create_task_binding(demo_db, "support-b", "orders-demo", "integration-b")
    assert list_applicable_memories(demo_db, str(other_tenant["task_id"]), "auth_401") == []
    with pytest.raises(MemoryScopeDenied):
        revoke_memory(demo_db, str(memory["memory_id"]), "approver-b")

    with connect(demo_db) as connection:
        connection.execute(
            "INSERT INTO services (tenant_id, service_id, integration_id, route) VALUES ('tenant-a', 'orders-other', 'integration-a', '/api/orders/demo-order')"
        )
    other_project = create_task_binding(demo_db, "support-a", "orders-other", "integration-a")
    assert list_applicable_memories(demo_db, str(other_project["task_id"]), "auth_401") == []

    with connect(demo_db) as connection:
        expired = (datetime.now(timezone.utc) - timedelta(seconds=2)).isoformat()
        connection.execute("UPDATE d5_memories SET expires_at = ? WHERE memory_id = ?", (expired, active["memory_id"]))
    target = create_task_binding(demo_db, "support-a", "orders-demo", "integration-a")
    assert list_applicable_memories(demo_db, str(target["task_id"]), "auth_401") == []


def test_expired_candidate_and_unverifiable_report_or_evidence_are_rejected(demo_db: Path) -> None:
    expired_source = _seed_verified_source(demo_db, "unused")
    expired_candidate = create_memory_candidate(demo_db, expired_source, "support-a")
    with connect(demo_db) as connection:
        expired = (datetime.now(timezone.utc) - timedelta(seconds=2)).isoformat()
        connection.execute("UPDATE d5_memories SET expires_at = ? WHERE memory_id = ?", (expired, expired_candidate["memory_id"]))
    with pytest.raises(MemorySourceRejected, match="Expired candidates"):
        confirm_memory(demo_db, str(expired_candidate["memory_id"]), "approver-a")

    tampered_source = _seed_verified_source(demo_db, "unused")
    with connect(demo_db) as connection:
        connection.execute(
            "UPDATE d3_report_artifacts SET immutable_content_json = immutable_content_json || ' ' WHERE task_id = ?",
            (tampered_source,),
        )
    with pytest.raises(MemorySourceRejected):
        create_memory_candidate(demo_db, tampered_source, "support-a")

    evidence_source = _seed_verified_source(demo_db, "unused")
    with connect(demo_db) as connection:
        connection.execute("DELETE FROM d2_evidence WHERE task_id = ?", (evidence_source,))
    with pytest.raises(MemorySourceRejected):
        create_memory_candidate(demo_db, evidence_source, "support-a")


def test_context_builder_and_reservation_record_exact_sources(demo_db: Path) -> None:
    task_a = _seed_verified_source(demo_db, "unused")
    memory = create_memory_candidate(demo_db, task_a, "support-a")
    confirm_memory(demo_db, str(memory["memory_id"]), "approver-a")
    target = create_task_binding(demo_db, "support-a", "orders-demo", "integration-a")
    task_id = str(target["task_id"])
    state = {"task_binding_id": task_id, "evidence_ids": []}
    metadata: dict[str, object] = {}
    messages = _prompt_messages(demo_db, task_id, state, context_metadata=metadata)
    prompt = "\n".join(str(item.content) for item in messages)
    assert str(memory["memory_id"]) in prompt
    assert "historical_memory_guidance" in prompt and "skill_methodology" in prompt
    assert metadata["selected_skill"]["name"] == "auth-incident-triage"
    assert metadata["selected_memories"][0]["memory_id"] == memory["memory_id"]

    prompt_digest = digest_json([{"role": item.type, "content": item.content} for item in messages])
    attempt_id, _ = reserve_attempt(
        demo_db, task_id, "MODEL", 8, call_id="d5-context-test-call",
        argument_digest=prompt_digest,
        context_provenance={
            "model_id": "test-model", "prompt_version": PROMPT_VERSION,
            "prompt_digest": prompt_digest, "tool_schema_version": "test-schema-v1",
            "tool_schema_digest": digest_json([]), **metadata,
        },
    )
    finish_context_provenance(demo_db, "d5-context-test-call", "MODEL_REQUEST_FAILED", "TimeoutError")
    row = list_context_provenance(demo_db, task_id, "support-a")[0]
    assert len(row["selected_memories"]) == 1
    selected_memory = row["selected_memories"][0]
    assert selected_memory["memory_id"] == memory["memory_id"]
    assert selected_memory["version"] == 2
    assert selected_memory["source_task_id"] == task_a
    assert selected_memory["source_outcome"] == "REPAIRED_VERIFIED"
    assert selected_memory["digest"] == memory["content_digest"]
    assert row["selected_skill_name"] == "auth-incident-triage"
    assert row["prompt_digest"] == prompt_digest
    assert row["model_status"] == "MODEL_REQUEST_FAILED"
    assert row["error_class"] == "TimeoutError"
    assert row["attempt_id"] == attempt_id
    assert row["model_trace_prompt_digest"] is None


def test_memory_revocation_between_build_and_reserve_blocks_stale_prompt(demo_db: Path) -> None:
    task_a = _seed_verified_source(demo_db, "unused")
    memory = create_memory_candidate(demo_db, task_a, "support-a")
    confirm_memory(demo_db, str(memory["memory_id"]), "approver-a")
    target = create_task_binding(demo_db, "support-a", "orders-demo", "integration-a")
    metadata: dict[str, object] = {}
    messages = _prompt_messages(demo_db, str(target["task_id"]), {"evidence_ids": []}, context_metadata=metadata)
    prompt_digest = digest_json([{"role": item.type, "content": item.content} for item in messages])
    revoke_memory(demo_db, str(memory["memory_id"]), "approver-a")
    with pytest.raises(ContextAssetInvalidated):
        reserve_attempt(
            demo_db, str(target["task_id"]), "MODEL", 8, call_id="stale-memory-call",
            argument_digest=prompt_digest,
            context_provenance={
                "model_id": "test-model", "prompt_version": PROMPT_VERSION,
                "prompt_digest": prompt_digest, "tool_schema_version": "test-schema-v1",
                "tool_schema_digest": digest_json([]), **metadata,
            },
        )
    assert list_context_provenance(demo_db, str(target["task_id"]), "support-a") == []
    with connect(demo_db) as connection:
        assert connection.execute("SELECT COUNT(*) AS n FROM d2_attempts WHERE task_id = ?", (target["task_id"],)).fetchone()["n"] == 0


def test_skill_is_loaded_lazily_and_digest_tampering_fails(monkeypatch, tmp_path: Path) -> None:
    import opspilot.skill_assets as assets

    skill_dir = tmp_path / "auth-incident-triage"
    skill_dir.mkdir()
    (skill_dir / "manifest.json").write_text(json.dumps({
        "name": "auth-incident-triage", "version": "1.0.0", "problem_type": "other",
        "skill_file": "SKILL.md", "digest_algorithm": "sha256", "digest": "0" * 64,
    }), encoding="utf-8")
    monkeypatch.setattr(assets, "SKILL_DIRECTORY", skill_dir)
    assert load_applicable_skill("auth_401") is None
    assert not (skill_dir / "SKILL.md").exists()

    manifest = {
        "name": "auth-incident-triage", "version": "1.0.0", "problem_type": "auth_401",
        "skill_file": "SKILL.md", "digest_algorithm": "sha256", "digest": "0" * 64,
    }
    (skill_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (skill_dir / "SKILL.md").write_text("tampered content", encoding="utf-8")
    with pytest.raises(SkillIntegrityError, match="digest"):
        load_applicable_skill("auth_401")


def test_skill_version_change_blocks_continuing_task(demo_db: Path) -> None:
    target = create_task_binding(demo_db, "support-a", "orders-demo", "integration-a")
    skill = load_applicable_skill("auth_401")
    assert skill is not None
    metadata: dict[str, object] = {}
    _prompt_messages(demo_db, str(target["task_id"]), {"evidence_ids": []}, context_metadata=metadata)
    prompt_digest = digest_json({"prompt": "version binding"})
    reserve_attempt(
        demo_db, str(target["task_id"]), "MODEL", 8, call_id="skill-version-call",
        argument_digest=prompt_digest,
        context_provenance={
            "model_id": "test-model", "prompt_version": PROMPT_VERSION,
            "prompt_digest": prompt_digest, "tool_schema_version": "test-schema-v1",
            "tool_schema_digest": digest_json([]), **metadata,
        },
    )
    assert_task_skill_compatible(demo_db, str(target["task_id"]), skill)
    with pytest.raises(SkillCompatibilityError):
        assert_task_skill_compatible(demo_db, str(target["task_id"]), {**skill, "version": "2.0.0"})
