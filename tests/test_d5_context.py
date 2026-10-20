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
    finish_attempt,
    probe_endpoint_fact,
    record_tool_observation,
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
from opspilot.domain.task_control import (
    admit_task_message,
    apply_pending_critical_inputs,
    claim_task_run,
    create_session,
    create_task_with_initial_run,
    finish_task_run,
    register_worker_owner,
    trusted_identity,
)


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


def _seed_hf01_chat_target(db: Path, live_api: str, prefix: str) -> dict[str, object]:
    source_task = _seed_verified_source(db, f"{prefix}-source")
    candidate = create_memory_candidate(db, source_task, "support-a")
    active = confirm_memory(db, str(candidate["memory_id"]), "approver-a")
    identity = trusted_identity(db, "support-a")
    session = create_session(db, identity)
    created = create_task_with_initial_run(
        db, identity, session_id=str(session["session_id"]),
        service_id="orders-demo", integration_id="integration-a",
        ticket_id=f"{prefix}-target", initial_message="Verify the current orders API result.",
        idempotency_key=f"{prefix}-create-task",
    )
    task_id, business_run_id = str(created["task_id"]), str(created["run_id"])
    with connect(db) as connection:
        connection.execute(
            "UPDATE integrations SET credential_ref = 'cred-v1', config_version = 7 "
            "WHERE tenant_id = 'tenant-a' AND integration_id = 'integration-a'"
        )
    claim_task_run(db, identity, business_run_id)
    apply_pending_critical_inputs(db, identity, business_run_id)
    probe = probe_endpoint_fact(db, task_id, "orders-demo", "integration-a", live_api)
    assert probe["facts"]["http_status"] == 401
    call_id = f"{prefix}-current-401"
    tool_call_id = f"{prefix}-current-401-tool"
    probe_attempt, _ = reserve_attempt(
        db, task_id, "MCP", 6, call_id=call_id,
        tool_call_id=tool_call_id, tool_name="probe_endpoint",
        argument_digest=f"{prefix}-current-401-args", run_id=business_run_id,
    )
    finish_attempt(db, probe_attempt, "OK")
    record_tool_observation(
        db, task_id=task_id, call_id=call_id, attempt_id=probe_attempt,
        tool_call_id=tool_call_id, tool_name="probe_endpoint",
        arguments={"service_id": "orders-demo", "integration_id": "integration-a"},
        status="OK", result=probe,
    )
    worker_id = f"{prefix}-chat-worker"
    register_worker_owner(db, worker_id, 5101)
    return {
        "task_id": task_id, "business_run_id": business_run_id,
        "session_id": str(session["session_id"]), "identity": identity,
        "memory": active, "memory_id": str(active["memory_id"]), "worker_id": worker_id,
    }


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


def test_s1_memory_waits_for_a_current_same_run_401_before_entering_prompt(
    demo_db: Path, live_api: str,
) -> None:
    source_task = _seed_verified_source(demo_db, "unused")
    memory = create_memory_candidate(demo_db, source_task, "support-a")
    confirm_memory(demo_db, str(memory["memory_id"]), "approver-a")

    # The untrusted initial message is not sufficient to select the 401 case.
    with connect(demo_db) as connection:
        connection.execute(
            "UPDATE integrations SET credential_ref = 'cred-v1', config_version = config_version + 1 "
            "WHERE tenant_id = 'tenant-a' AND integration_id = 'integration-a'"
        )
    identity = trusted_identity(demo_db, "support-a")
    session_id = str(create_session(demo_db, identity)["session_id"])
    created = create_task_with_initial_run(
        demo_db, identity, session_id=session_id, service_id="orders-demo",
        integration_id="integration-a", ticket_id="m301-s1-target",
        initial_message="订单接口 401，请核实当前认证状态。", idempotency_key="m301-s1-target",
    )
    task_b, run_b = str(created["task_id"]), str(created["run_id"])
    claim_task_run(demo_db, identity, run_b)
    apply_pending_critical_inputs(demo_db, identity, run_b)
    state = {"task_binding_id": task_b, "evidence_ids": []}
    before_metadata: dict[str, object] = {}
    before_prompt = "\n".join(str(item.content) for item in _prompt_messages(
        demo_db, task_b, state, context_metadata=before_metadata, run_id=run_b, s2_mode=True,
    ))
    assert before_metadata["selected_memories"] == []
    assert memory["memory_id"] not in before_prompt

    probe = probe_endpoint_fact(demo_db, task_b, "orders-demo", "integration-a", live_api)
    assert probe["facts"]["http_status"] == 401
    call_id = "m301-s1-current-probe"
    attempt, _ = reserve_attempt(
        demo_db, task_b, "MCP", 6, call_id=call_id, tool_call_id="m301-s1-current-tool",
        tool_name="probe_endpoint", argument_digest="m301-s1-current-args", run_id=run_b,
    )
    finish_attempt(demo_db, attempt, "OK")
    observation = record_tool_observation(
        demo_db, task_id=task_b, call_id=call_id, attempt_id=attempt,
        tool_call_id="m301-s1-current-tool", tool_name="probe_endpoint",
        arguments={"service_id": "orders-demo", "integration_id": "integration-a"},
        status="OK", result=probe,
    )
    after_metadata: dict[str, object] = {}
    after_prompt = "\n".join(str(item.content) for item in _prompt_messages(
        demo_db, task_b, {**state, "evidence_ids": [str(observation["evidence_id"])]},
        context_metadata=after_metadata, run_id=run_b, s2_mode=True,
    ))
    selected = after_metadata["selected_memories"]
    assert memory["memory_id"] in after_prompt
    assert isinstance(selected, list) and selected[0]["memory_id"] == memory["memory_id"]
    assert selected[0]["source_task_id"] == source_task != task_b


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


def test_hf01_c02_revocation_after_attempt_reservation_blocks_provider_outbound(
    demo_db: Path, live_api: str, monkeypatch, tmp_path: Path,
) -> None:
    """A revoked Memory must not cross the provider boundary after reservation."""
    import asyncio

    from langchain_core.messages import AIMessage

    import opspilot.investigator as investigator

    source_task = _seed_verified_source(demo_db, "unused")
    memory = create_memory_candidate(demo_db, source_task, "support-a")
    active = confirm_memory(demo_db, str(memory["memory_id"]), "approver-a")
    assert active["state"] == "ACTIVE"

    identity = trusted_identity(demo_db, "support-a")
    session = create_session(demo_db, identity)
    initial = create_task_with_initial_run(
        demo_db, identity, session_id=str(session["session_id"]),
        service_id="orders-demo", integration_id="integration-a",
        ticket_id="HF01-C02-TARGET", initial_message="Orders API is failing; investigate the bound request.",
        idempotency_key="hf01-c02-create-task",
    )
    task_id = str(initial["task_id"])
    with connect(demo_db) as connection:
        connection.execute(
            "UPDATE integrations SET credential_ref = 'cred-v1', config_version = 7 "
            "WHERE tenant_id = 'tenant-a' AND integration_id = 'integration-a'"
        )
    accepted = admit_task_message(
        demo_db, identity, session_id=str(session["session_id"]), task_id=task_id,
        input_kind="CORRECT_TASK_INPUT", body="Use the current request for the bound orders route.",
        idempotency_key="hf01-c02-correction",
    )
    run_id = str(accepted["run_id"])
    claim_task_run(demo_db, identity, run_id)
    apply_pending_critical_inputs(demo_db, identity, run_id)

    probe = probe_endpoint_fact(demo_db, task_id, "orders-demo", "integration-a", live_api)
    assert probe["facts"]["http_status"] == 401
    probe_call = "hf01-c02-live-probe"
    probe_attempt, _ = reserve_attempt(
        demo_db, task_id, "MCP", 6, call_id=probe_call,
        tool_call_id="hf01-c02-live-probe-tool", tool_name="probe_endpoint",
        argument_digest="hf01-c02-live-probe-args", run_id=run_id,
    )
    finish_attempt(demo_db, probe_attempt, "OK")
    record_tool_observation(
        demo_db, task_id=task_id, call_id=probe_call, attempt_id=probe_attempt,
        tool_call_id="hf01-c02-live-probe-tool", tool_name="probe_endpoint",
        arguments={"service_id": "orders-demo", "integration_id": "integration-a"},
        status="OK", result=probe,
    )
    finish_task_run(
        demo_db, identity, run_id, "INTERRUPTED_RECOVERABLE",
        blocked_reason="HF01_C02_PRE_PROVIDER_BARRIER",
    )

    original_reserve = investigator.reserve_attempt
    revocation = {"value": None}
    captured: list[str] = []

    def reserve_then_revoke(*args, **kwargs):
        result = original_reserve(*args, **kwargs)
        provenance = kwargs.get("context_provenance")
        selected = provenance.get("selected_memories", []) if isinstance(provenance, dict) else []
        if selected and revocation["value"] is None:
            revocation["value"] = revoke_memory(
                demo_db, str(memory["memory_id"]), "approver-a",
                idempotency_key="hf01-c02-revoke-after-reserve",
            )
        return result

    class CapturingChat:
        def __init__(self, *args, **kwargs):
            pass

        def bind_tools(self, *args, **kwargs):
            return self

        async def ainvoke(self, messages):
            captured.append("\n".join(str(item.content) for item in messages))
            return AIMessage(content="No additional read is needed.")

    monkeypatch.setattr(investigator, "reserve_attempt", reserve_then_revoke)
    monkeypatch.setattr(investigator, "ChatOpenAI", CapturingChat)
    monkeypatch.setenv("OPSPILOT_MODEL_API_KEY", "deterministic-hf01-test-key")
    monkeypatch.setenv("OPSPILOT_MODEL_NAME", "deterministic-hf01-test-model")

    asyncio.run(investigator.run_investigation(
        task_id, "support-a", db_path=demo_db,
        checkpoint_db_path=tmp_path / "hf01-c02-checkpoint.sqlite3",
        resume=True, run_id=run_id,
    ))

    assert revocation["value"] is not None and revocation["value"]["state"] == "REVOKED"
    assert captured, "the investigation should rebuild a safe context and reach the Provider"
    assert all(str(memory["memory_id"]) not in prompt for prompt in captured)
    provenance = list_context_provenance(demo_db, task_id, "support-a")
    memory_attempts = [
        row for row in provenance
        if any(item.get("memory_id") == memory["memory_id"] for item in row["selected_memories"])
    ]
    assert len(memory_attempts) == 1
    invalidated_call_id = str(memory_attempts[0]["call_id"])
    assert memory_attempts[0]["model_status"] == "CONTEXT_ASSET_INVALIDATED"
    with connect(demo_db) as connection:
        attempts = [dict(row) for row in connection.execute(
            "SELECT attempt_id, call_id, status FROM d2_attempts WHERE task_id = ? AND kind = 'MODEL'",
            (task_id,),
        ).fetchall()]
        model_calls = [str(row[0]) for row in connection.execute(
            "SELECT call_id FROM d2_model_traces WHERE task_id = ?", (task_id,),
        ).fetchall()]
    assert len(attempts) >= 2
    assert len({str(item["call_id"]) for item in attempts}) == len(attempts)
    assert next(item for item in attempts if item["call_id"] == invalidated_call_id)["status"] == "CONTEXT_ASSET_INVALIDATED"
    assert invalidated_call_id not in model_calls
    assert len(model_calls) == len(captured)
    assert all(call_id in {str(item["call_id"]) for item in attempts} for call_id in model_calls)


def test_hf01_c02_chat_revocation_after_attempt_reservation_blocks_provider_outbound(
    demo_db: Path, live_api: str, monkeypatch,
) -> None:
    import asyncio

    import langchain_openai

    import opspilot.domain.chat as chat_domain
    from opspilot.domain.chat import get_chat_manifest
    from opspilot.web.worker import _process_chat_run
    target = _seed_hf01_chat_target(demo_db, live_api, "hf01-c02-chat")
    identity = target["identity"]
    task_id, worker_id = str(target["task_id"]), str(target["worker_id"])
    accepted = admit_task_message(
        demo_db, identity, session_id=str(target["session_id"]), task_id=task_id,
        input_kind="CHAT_READONLY", body="Explain the current bound investigation.",
        idempotency_key="hf01-c02-chat-message",
    )
    original_prepare = chat_domain.prepare_chat_attempt
    revoked_ids: list[str] = []

    def prepare_then_revoke(*args, **kwargs):
        prepared = original_prepare(*args, **kwargs)
        assert any(item.get("memory_id") == target["memory_id"] for item in prepared["memory_refs"])
        revoked = revoke_memory(
            demo_db, str(target["memory_id"]), "approver-a",
            idempotency_key="hf01-c02-chat-revoke-after-reserve",
        )
        assert revoked["state"] == "REVOKED"
        revoked_ids.append(str(revoked["memory_id"]))
        return prepared

    provider_calls: list[str] = []

    class CapturingChat:
        def __init__(self, *args, **kwargs):
            pass

        async def astream(self, messages):
            provider_calls.append("\n".join(str(item.content) for item in messages))
            raise AssertionError("Provider I/O must not start with a revoked Memory in context.")
            yield  # pragma: no cover - keeps this an async generator

    monkeypatch.setattr(chat_domain, "prepare_chat_attempt", prepare_then_revoke)
    monkeypatch.setattr(langchain_openai, "ChatOpenAI", CapturingChat)
    monkeypatch.setenv("OPSPILOT_MODEL_API_KEY", "deterministic-hf01-chat-race-key")
    monkeypatch.setenv("OPSPILOT_MODEL_NAME", "deterministic-hf01-chat-race-model")
    with connect(demo_db) as connection:
        run = dict(connection.execute("SELECT * FROM task_runs WHERE run_id = ?", (accepted["run_id"],)).fetchone())
    asyncio.run(_process_chat_run(demo_db, worker_id, run))

    assert revoked_ids == [str(target["memory_id"])]
    assert provider_calls == []
    manifest = get_chat_manifest(demo_db, identity, str(accepted["run_id"]))
    assert manifest["attempts"][0]["error_class"] == "ContextAssetInvalidated"
    assert manifest["attempts"][0]["status"] == "FAILED"
    assert manifest["attempts"][0]["token_usage"] == {
        "input_tokens": None, "output_tokens": None, "total_tokens": None,
    }


def test_hf01_c03_provider_started_before_revocation_is_recorded_in_order(
    demo_db: Path, live_api: str, monkeypatch, tmp_path: Path,
) -> None:
    import asyncio

    from langchain_core.messages import AIMessage

    import opspilot.investigator as investigator
    from opspilot.domain.episodic_memory import list_context_provenance

    target = _seed_hf01_chat_target(demo_db, live_api, "hf01-c03")
    task_id = str(target["task_id"])
    run_id = str(target["business_run_id"])
    memory_id = str(target["memory_id"])
    finish_task_run(
        demo_db, target["identity"], run_id, "INTERRUPTED_RECOVERABLE",
        blocked_reason="HF01_C03_PROVIDER_START_BARRIER",
    )
    events: list[str] = []
    provider_payloads: list[str] = []

    class CapturingProvider:
        def __init__(self, *args, **kwargs):
            pass

        def bind_tools(self, *args, **kwargs):
            return self

        async def ainvoke(self, provider_messages):
            provider_payloads.append("\n".join(str(item.content) for item in provider_messages))
            if len(provider_payloads) == 1:
                events.append("provider_request_started_with_active_memory")
                assert memory_id in provider_payloads[0]
                revoked = revoke_memory(
                    demo_db, memory_id, "approver-a",
                    idempotency_key="hf01-c03-revoke-after-provider-start",
                )
                assert revoked["state"] == "REVOKED"
                events.append("memory_revocation_committed")
            else:
                events.append("provider_request_started_after_revocation_without_memory")
                assert memory_id not in provider_payloads[-1]
            return AIMessage(
                content="The observed 401 is current; no repair has been performed.",
                response_metadata={"id": f"hf01-c03-provider-{len(provider_payloads)}"},
                usage_metadata={"input_tokens": 10, "output_tokens": 8, "total_tokens": 18},
            )

    monkeypatch.setattr(investigator, "ChatOpenAI", CapturingProvider)
    monkeypatch.setenv("OPSPILOT_MODEL_API_KEY", "deterministic-hf01-c03-key")
    monkeypatch.setenv("OPSPILOT_MODEL_NAME", "deterministic-hf01-c03-model")
    asyncio.run(investigator.run_investigation(
        task_id, "support-a", db_path=demo_db,
        checkpoint_db_path=tmp_path / "hf01-c03-checkpoint.sqlite3",
        resume=True, run_id=run_id,
    ))

    assert events[:2] == ["provider_request_started_with_active_memory", "memory_revocation_committed"]
    assert memory_id in provider_payloads[0]
    assert all(memory_id not in payload for payload in provider_payloads[1:])
    assert events[2:] and all(
        event == "provider_request_started_after_revocation_without_memory" for event in events[2:]
    )
    provenance = list_context_provenance(demo_db, task_id, "support-a")
    selected = [
        item for row in provenance for item in row["selected_memories"]
        if item["memory_id"] == memory_id
    ]
    assert len(selected) == 1 and selected[0]["version"] == target["memory"]["version"]
    with connect(demo_db) as connection:
        model_calls = {
            str(row[0]) for row in connection.execute(
                "SELECT call_id FROM d2_model_traces WHERE task_id = ?", (task_id,),
            ).fetchall()
        }
    assert model_calls == {str(row["call_id"]) for row in provenance if row["model_status"] == "OK"}
    print(json.dumps({
        "event": "hf01_c03_provider_revocation_order",
        "task_id": task_id,
        "run_id": run_id,
        "memory_id": memory_id,
        "events": events,
        "provider_calls": len(provider_payloads),
        "memory_present_by_provider_call": [memory_id in payload for payload in provider_payloads],
        "provider_payload_digests": [digest_json(payload) for payload in provider_payloads],
        "selected_memory_provenance_call_ids": [str(row["call_id"]) for row in provenance
                                                    if any(item["memory_id"] == memory_id for item in row["selected_memories"])],
        "model_trace_call_ids": sorted(model_calls),
    }, sort_keys=True))


@pytest.mark.parametrize("invalidation", ["expired", "version_changed", "source_invalid"])
def test_hf01_c05_stale_memory_context_is_rejected_and_fresh_prompt_excludes_it(
    demo_db: Path, invalidation: str,
) -> None:
    from opspilot.domain.episodic_memory import assert_selected_memories_current

    source_task = _seed_verified_source(demo_db, f"hf01-c05-{invalidation}")
    candidate = create_memory_candidate(demo_db, source_task, "support-a")
    confirm_memory(demo_db, str(candidate["memory_id"]), "approver-a")
    target = create_task_binding(demo_db, "support-a", "orders-demo", "integration-a")
    task_id = str(target["task_id"])
    metadata: dict[str, object] = {}
    messages = _prompt_messages(
        demo_db, task_id, {"task_binding_id": task_id, "evidence_ids": []},
        context_metadata=metadata,
    )
    memory_id = str(candidate["memory_id"])
    assert memory_id in "\n".join(str(item.content) for item in messages)
    prompt_digest = digest_json([{"role": item.type, "content": item.content} for item in messages])
    attempt_id, _ = reserve_attempt(
        demo_db, task_id, "MODEL", 8, call_id=f"hf01-c05-{invalidation}",
        argument_digest=prompt_digest,
        context_provenance={
            "model_id": "test-model", "prompt_version": PROMPT_VERSION,
            "prompt_digest": prompt_digest, "tool_schema_version": "test-schema-v1",
            "tool_schema_digest": digest_json([]), **metadata,
        },
    )
    with connect(demo_db) as connection:
        if invalidation == "expired":
            expired = (datetime.now(timezone.utc) - timedelta(seconds=2)).isoformat()
            connection.execute("UPDATE d5_memories SET expires_at = ? WHERE memory_id = ?", (expired, memory_id))
        elif invalidation == "version_changed":
            connection.execute(
                "UPDATE d5_memories SET state = 'REVOKED', version = version + 1 WHERE memory_id = ?",
                (memory_id,),
            )
        else:
            connection.execute(
                "UPDATE d3_report_artifacts SET immutable_content_json = immutable_content_json || ' ' WHERE task_id = ?",
                (source_task,),
            )

    with pytest.raises(ContextAssetInvalidated):
        assert_selected_memories_current(
            demo_db, task_id,
            [item for item in metadata.get("selected_memories", []) if isinstance(item, dict)],
        )
    finish_attempt(demo_db, attempt_id, "CONTEXT_ASSET_INVALIDATED", error_class="ContextAssetInvalidated")
    finish_context_provenance(demo_db, f"hf01-c05-{invalidation}", "CONTEXT_ASSET_INVALIDATED")

    fresh_metadata: dict[str, object] = {}
    fresh_messages = _prompt_messages(
        demo_db, task_id, {"task_binding_id": task_id, "evidence_ids": []},
        context_metadata=fresh_metadata,
    )
    assert memory_id not in "\n".join(str(item.content) for item in fresh_messages)
    assert fresh_metadata["selected_memories"] == []


def test_hf01_c06_active_memory_chat_answer_is_excluded_from_actual_followup_provider_context(
    demo_db: Path, live_api: str, monkeypatch,
) -> None:
    import asyncio

    import langchain_openai
    from langchain_core.messages import AIMessageChunk

    from opspilot.domain.chat import get_chat_manifest
    from opspilot.web.worker import _process_chat_run

    source_task = _seed_verified_source(demo_db, "hf01-c06-source")
    candidate = create_memory_candidate(demo_db, source_task, "support-a")
    active = confirm_memory(demo_db, str(candidate["memory_id"]), "approver-a")
    memory_id = str(active["memory_id"])

    identity = trusted_identity(demo_db, "support-a")
    session = create_session(demo_db, identity)
    created = create_task_with_initial_run(
        demo_db, identity, session_id=str(session["session_id"]),
        service_id="orders-demo", integration_id="integration-a",
        ticket_id="HF01-C06-TARGET", initial_message="Verify the current orders API result.",
        idempotency_key="hf01-c06-create-task",
    )
    task_id, business_run_id = str(created["task_id"]), str(created["run_id"])
    with connect(demo_db) as connection:
        connection.execute(
            "UPDATE integrations SET credential_ref = 'cred-v1', config_version = 7 "
            "WHERE tenant_id = 'tenant-a' AND integration_id = 'integration-a'"
        )
    claim_task_run(demo_db, identity, business_run_id)
    apply_pending_critical_inputs(demo_db, identity, business_run_id)
    probe = probe_endpoint_fact(demo_db, task_id, "orders-demo", "integration-a", live_api)
    assert probe["facts"]["http_status"] == 401
    probe_attempt, _ = reserve_attempt(
        demo_db, task_id, "MCP", 6, call_id="hf01-c06-current-401",
        tool_call_id="hf01-c06-current-401-tool", tool_name="probe_endpoint",
        argument_digest="hf01-c06-current-401-args", run_id=business_run_id,
    )
    finish_attempt(demo_db, probe_attempt, "OK")
    record_tool_observation(
        demo_db, task_id=task_id, call_id="hf01-c06-current-401", attempt_id=probe_attempt,
        tool_call_id="hf01-c06-current-401-tool", tool_name="probe_endpoint",
        arguments={"service_id": "orders-demo", "integration_id": "integration-a"},
        status="OK", result=probe,
    )

    owner = "hf01-c06-chat-worker"
    register_worker_owner(demo_db, owner, 5101)
    first_user = admit_task_message(
        demo_db, identity, session_id=str(session["session_id"]), task_id=task_id,
        input_kind="CHAT_READONLY", body="Explain what the current investigation can use.",
        idempotency_key="hf01-c06-chat-1",
    )
    memory_derived_answer = f"A prior case method from memory {memory_id} suggested checking policy first."
    provider_contexts: list[str] = []

    class CapturingChat:
        def __init__(self, *args, **kwargs):
            pass

        async def astream(self, messages):
            provider_contexts.append("\n".join(f"{item.type}:{item.content}" for item in messages))
            yield AIMessageChunk(
                content=memory_derived_answer,
                response_metadata={"id": "hf01-c06-provider-1"},
                usage_metadata={"input_tokens": 10, "output_tokens": 9, "total_tokens": 19},
            )

    monkeypatch.setattr(langchain_openai, "ChatOpenAI", CapturingChat)
    monkeypatch.setenv("OPSPILOT_MODEL_API_KEY", "deterministic-hf01-chat-key")
    monkeypatch.setenv("OPSPILOT_MODEL_NAME", "deterministic-hf01-chat-model")
    with connect(demo_db) as connection:
        first_run = dict(connection.execute("SELECT * FROM task_runs WHERE run_id = ?", (first_user["run_id"],)).fetchone())
    asyncio.run(_process_chat_run(demo_db, owner, first_run))
    assert memory_id in provider_contexts[0]

    with connect(demo_db) as connection:
        answer = connection.execute(
            "SELECT a.message_id FROM chat_run_answers a WHERE a.run_id = ?", (first_user["run_id"],),
        ).fetchone()
        assert answer is not None
        answer_id = str(answer["message_id"])
        sources = [dict(row) for row in connection.execute(
            "SELECT * FROM chat_message_sources WHERE message_id = ? AND source_kind = 'MEMORY'",
            (answer_id,),
        ).fetchall()]
    assert len(sources) == 1
    assert sources[0]["source_ref"] == memory_id
    assert sources[0]["source_version"] == str(active["version"])
    assert sources[0]["source_digest"] == active["content_digest"]

    revoked = revoke_memory(demo_db, memory_id, "approver-a", idempotency_key="hf01-c06-revoke")
    assert revoked["state"] == "REVOKED" and revoked["version"] == int(active["version"]) + 1
    second_user = admit_task_message(
        demo_db, identity, session_id=str(session["session_id"]), task_id=task_id,
        input_kind="CHAT_READONLY", body="Explain the currently available evidence only.",
        idempotency_key="hf01-c06-chat-2",
    )
    with connect(demo_db) as connection:
        second_run = dict(connection.execute("SELECT * FROM task_runs WHERE run_id = ?", (second_user["run_id"],)).fetchone())
    asyncio.run(_process_chat_run(demo_db, owner, second_run))

    assert len(provider_contexts) == 2
    assert memory_derived_answer not in provider_contexts[1]
    assert memory_id not in provider_contexts[1]
    manifest = get_chat_manifest(demo_db, identity, str(second_user["run_id"]))
    assert any(
        item.get("message_id") == answer_id
        and item.get("reason") == "MEMORY_REVOKED_EXPIRED_OR_CHANGED"
        for item in manifest["attempts"][0]["manifest"]["excluded_sources"]
    )
    with connect(demo_db) as connection:
        assert connection.execute("SELECT 1 FROM messages WHERE message_id = ?", (answer_id,)).fetchone() is not None


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
