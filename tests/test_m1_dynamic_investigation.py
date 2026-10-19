from __future__ import annotations

from pathlib import Path

import pytest

from opspilot.domain.database import connect
from opspilot.domain.d2 import (
    create_task_binding,
    digest_json,
    get_auth_policy_fact,
    get_integration_config_fact,
    get_principal_status_fact,
    probe_endpoint_fact,
    record_tool_observation,
    reserve_attempt,
)
from opspilot.domain.d3 import save_local_report
from opspilot.domain.investigation_context import InvestigationContextInvalid, load_investigation_context
from opspilot.domain.episodic_memory import list_context_provenance
from opspilot.domain.chat import get_task_inspector
from opspilot.domain.task_control import (
    TaskControlError,
    admit_task_message,
    apply_pending_critical_inputs,
    claim_task_run,
    create_session,
    create_task_with_initial_run,
    finish_task_run,
    trusted_identity,
)
from opspilot.investigator import (
    InvestigatorState,
    PROMPT_VERSION,
    _current_task_evidence_ids,
    _prompt_messages,
    _requires_scope_clarification,
)


def _create_task(db: Path, initial_message: str, key: str) -> tuple[object, dict[str, object]]:
    identity = trusted_identity(db, "support-a")
    session_id = str(create_session(db, identity)["session_id"])
    created = create_task_with_initial_run(
        db, identity, session_id=session_id, service_id="orders-demo",
        integration_id="integration-a", ticket_id="INC-A-001",
        initial_message=initial_message, idempotency_key=key,
    )
    return identity, created


def test_initial_symptom_is_selected_from_run_source_and_has_no_synthetic_status(demo_db: Path) -> None:
    identity, created = _create_task(
        demo_db, "昨晚凭证轮换后订单 API 一直提示未认证，请核实当前情况。", "nl-initial",
    )
    run_id, task_id = str(created["run_id"]), str(created["task_id"])
    claim_task_run(demo_db, identity, run_id)
    applied = apply_pending_critical_inputs(demo_db, identity, run_id)
    assert applied["inputs"] == []

    metadata: dict[str, object] = {}
    messages = _prompt_messages(
        demo_db, task_id, {"evidence_ids": [], "tool_observations": []},
        context_metadata=metadata, run_id=run_id,
    )
    prompt = "\n".join(str(message.content) for message in messages)
    control = metadata["task_run_control"]
    refs = metadata["selected_input_messages"]

    assert "昨晚凭证轮换后订单 API 一直提示未认证" in prompt
    assert "reported_http_status" not in prompt
    assert "current_facts_source" in prompt and "MCP Evidence" in prompt
    assert control["run_id"] == run_id
    assert control["source_message_id"] == created["message_id"]
    assert control["expected_control_revision"] == 0
    assert control["consumed_message_seq"] == created["sequence"]
    assert refs[0]["message_id"] == created["message_id"]
    assert refs[0]["kind"] == "INITIAL_SYMPTOM"
    assert refs[0]["provenance"] == "USER_INPUT_UNTRUSTED"

    prompt_digest = digest_json([{"role": message.type, "content": message.content} for message in messages])
    attempt_id, _ = reserve_attempt(
        demo_db, task_id, "MODEL", 8, call_id="nl-initial-provenance-call",
        argument_digest=prompt_digest,
        context_provenance={
            "model_id": "test-model", "prompt_version": PROMPT_VERSION,
            "prompt_digest": prompt_digest, "tool_schema_version": "test-schema-v1",
            "tool_schema_digest": digest_json([]), **metadata,
        },
    )
    persisted = list_context_provenance(demo_db, task_id, "support-a")[0]
    inspector = get_task_inspector(demo_db, identity, task_id)
    assert persisted["attempt_id"] == attempt_id
    assert persisted["selected_input_messages"] == refs
    assert persisted["task_run_control"]["source_message_id"] == created["message_id"]
    assert "昨晚凭证轮换" not in str(persisted["selected_input_messages"])
    assert inspector["task_input_messages"][0]["message_id"] == created["message_id"]
    assert "body" not in inspector["task_input_messages"][0]
    assert inspector["investigator_context_provenance"][0]["selected_input_messages"] == refs


def test_new_run_prompt_includes_initial_and_cumulative_applied_corrections(demo_db: Path) -> None:
    identity, created = _create_task(demo_db, "订单接口最近无法访问。", "nl-cumulative")
    task_id = str(created["task_id"])
    first_run = str(created["run_id"])
    claim_task_run(demo_db, identity, first_run)
    apply_pending_critical_inputs(demo_db, identity, first_run)

    first = admit_task_message(
        demo_db, identity, session_id=str(created["session_id"]), task_id=task_id,
        input_kind="CORRECT_TASK_INPUT", body="先核实实际错误，不要假定状态码。",
        idempotency_key="nl-correction-1",
    )
    claim_task_run(demo_db, identity, str(first["run_id"]))
    apply_pending_critical_inputs(demo_db, identity, str(first["run_id"]))
    second = admit_task_message(
        demo_db, identity, session_id=str(created["session_id"]), task_id=task_id,
        input_kind="CORRECT_TASK_INPUT", body="更正：主体正常，问题发生在凭证轮换之后。",
        idempotency_key="nl-correction-2",
    )
    claim_task_run(demo_db, identity, str(second["run_id"]))
    applied = apply_pending_critical_inputs(demo_db, identity, str(second["run_id"]))

    selected = load_investigation_context(demo_db, task_id, str(second["run_id"]))
    metadata: dict[str, object] = {}
    messages = _prompt_messages(
        demo_db, task_id, {"evidence_ids": [], "tool_observations": []},
        context_metadata=metadata, run_id=str(second["run_id"]),
    )
    prompt = "\n".join(str(message.content) for message in messages)
    refs = metadata["selected_input_messages"]

    assert len(applied["inputs"]) == 1
    assert [item["body"] for item in selected["inputs"]] == [
        "订单接口最近无法访问。",
        "先核实实际错误，不要假定状态码。",
        "更正：主体正常，问题发生在凭证轮换之后。",
    ]
    assert all(body in prompt for body in [item["body"] for item in selected["inputs"]])
    assert [item["message_id"] for item in refs] == [
        created["message_id"], first["message_id"], second["message_id"],
    ]
    assert [item["kind"] for item in refs] == ["INITIAL_SYMPTOM", "CRITICAL_CORRECTION", "CRITICAL_CORRECTION"]
    assert all(item["provenance"] == "USER_INPUT_UNTRUSTED" for item in refs)
    assert metadata["task_run_control"]["expected_control_revision"] == second["expected_control_revision"] + 1
    assert metadata["task_run_control"]["applied_critical_message_seq"] == second["sequence"]
    assert "service_id\":\"orders-demo" in prompt

    prompt_digest = digest_json([{"role": message.type, "content": message.content} for message in messages])
    reserve_attempt(
        demo_db, task_id, "MODEL", 8, call_id="nl-cumulative-provenance-call",
        argument_digest=prompt_digest,
        context_provenance={
            "model_id": "test-model", "prompt_version": PROMPT_VERSION,
            "prompt_digest": prompt_digest, "tool_schema_version": "test-schema-v1",
            "tool_schema_digest": digest_json([]), **metadata,
        },
    )
    persisted = list_context_provenance(demo_db, task_id, "support-a")[0]
    assert persisted["selected_input_messages"] == refs
    assert len(persisted["selected_input_messages"]) == 3


def test_stale_control_cannot_reserve_model_context_built_before_correction(demo_db: Path) -> None:
    identity, created = _create_task(demo_db, "API 无法访问，请检查。", "nl-stale-context")
    task_id, run_id = str(created["task_id"]), str(created["run_id"])
    claim_task_run(demo_db, identity, run_id)
    apply_pending_critical_inputs(demo_db, identity, run_id)
    metadata: dict[str, object] = {}
    messages = _prompt_messages(
        demo_db, task_id, {"evidence_ids": [], "tool_observations": []},
        context_metadata=metadata, run_id=run_id,
    )
    prompt_digest = digest_json([{"role": message.type, "content": message.content} for message in messages])

    admit_task_message(
        demo_db, identity, session_id=str(created["session_id"]), task_id=task_id,
        input_kind="CORRECT_TASK_INPUT", body="更正：请只核实当前绑定的订单路由。",
        idempotency_key="nl-stale-context-correction",
    )
    with pytest.raises(TaskControlError):
        reserve_attempt(
            demo_db, task_id, "MODEL", 8, call_id="nl-stale-model-call",
            argument_digest=prompt_digest,
            context_provenance={
                "model_id": "test-model", "prompt_version": PROMPT_VERSION,
                "prompt_digest": prompt_digest, "tool_schema_version": "test-schema-v1",
                "tool_schema_digest": digest_json([]), **metadata,
            },
        )
    with connect(demo_db) as connection:
        attempts = int(connection.execute(
            "SELECT COUNT(*) FROM d2_attempts WHERE task_id = ?", (task_id,),
        ).fetchone()[0])
        provenance = int(connection.execute(
            "SELECT COUNT(*) FROM d5_context_provenance WHERE task_id = ?", (task_id,),
        ).fetchone()[0])
    assert attempts == provenance == 0


def test_explicit_scope_broadening_requests_take_clarification_branch() -> None:
    assert _requires_scope_clarification([{
        "body": "我看到的响应可能是 403，请立刻自动给这个主体增加Scope并修好订单 API。",
    }])
    assert not _requires_scope_clarification([{
        "body": "请只调查当前订单路由，不要增加 Scope。",
    }])
    assert "scope_clarification_required" in InvestigatorState.__annotations__


def test_followup_run_reuses_only_live_version_compatible_task_evidence(demo_db: Path, live_api: str) -> None:
    binding = create_task_binding(demo_db, "support-a", "orders-demo", "integration-a", "INC-A-001")
    task_id = str(binding["task_id"])
    facts = (
        ("get_integration_config", get_integration_config_fact(demo_db, task_id, "integration-a")),
        ("get_principal_status", get_principal_status_fact(demo_db, task_id, "principal-a")),
        ("get_auth_policy", get_auth_policy_fact(demo_db, task_id, "orders-demo")),
        ("probe_endpoint", probe_endpoint_fact(demo_db, task_id, "orders-demo", "integration-a", live_api)),
    )
    recorded: list[str] = []
    for index, (tool_name, fact) in enumerate(facts, start=1):
        result = record_tool_observation(
            demo_db, task_id=task_id, call_id=f"m1-04-current-evidence-{index}", attempt_id=None,
            tool_call_id=f"m1-04-current-tool-{index}", tool_name=tool_name,
            arguments={"sequence": index}, status="OK", result=fact,
        )
        recorded.append(str(result["evidence_id"]))
    assert set(_current_task_evidence_ids(demo_db, task_id)) == set(recorded)

    with connect(demo_db) as connection:
        connection.execute(
            "UPDATE integrations SET credential_ref = 'cred-v2', config_version = config_version + 1 "
            "WHERE tenant_id = 'tenant-a' AND integration_id = 'integration-a'"
        )
    still_current = _current_task_evidence_ids(demo_db, task_id)
    with connect(demo_db) as connection:
        stale_ids = {
            str(row["evidence_id"])
            for row in connection.execute(
                "SELECT evidence_id FROM d2_evidence WHERE task_id = ? AND fact_type IN ('integration_config', 'endpoint_probe')",
                (task_id,),
            )
        }
    assert not (set(still_current) & stale_ids)


def test_nonready_run_report_uses_current_correction_control_revision(demo_db: Path) -> None:
    identity, created = _create_task(demo_db, "订单接口无法访问。", "nl-nonready-report")
    task_id = str(created["task_id"])
    initial_run = str(created["run_id"])
    claim_task_run(demo_db, identity, initial_run)
    apply_pending_critical_inputs(demo_db, identity, initial_run)
    corrected = admit_task_message(
        demo_db, identity, session_id=str(created["session_id"]), task_id=task_id,
        input_kind="CORRECT_TASK_INPUT", body="更正：请只核实当前绑定的订单路由。",
        idempotency_key="nl-nonready-report-correction",
    )
    correction_run = str(corrected["run_id"])
    claim_task_run(demo_db, identity, correction_run)
    apply_pending_critical_inputs(demo_db, identity, correction_run)

    report = save_local_report(
        demo_db, task_id, "INCONCLUSIVE", {"reason": "bounded evidence incomplete"},
        run_id=correction_run,
    )
    finish_task_run(demo_db, identity, correction_run, "SUCCEEDED")
    assert report["outcome"] == "INCONCLUSIVE"
    assert report["report"]["reason"] == "bounded evidence incomplete"
    with connect(demo_db) as connection:
        run = connection.execute("SELECT status, expected_control_revision FROM task_runs WHERE run_id = ?", (correction_run,)).fetchone()
        writes = sum(int(connection.execute(f"SELECT COUNT(*) FROM {table} WHERE task_id = ?", (task_id,)).fetchone()[0])
                     for table in ("d3_action_intents", "d3_action_ledgers", "d3_approvals", "d3_action_permissions"))
    assert tuple(run) == ("SUCCEEDED", 2)
    assert writes == 0


def test_schema_v3_database_adds_context_input_provenance_columns(demo_db: Path) -> None:
    from opspilot.domain.database import initialize

    with connect(demo_db) as connection:
        connection.execute("ALTER TABLE d5_context_provenance DROP COLUMN selected_input_messages_json")
        connection.execute("ALTER TABLE d5_context_provenance DROP COLUMN task_run_control_json")
        connection.execute("PRAGMA user_version = 3")
    initialize(demo_db)
    with connect(demo_db) as connection:
        version = int(connection.execute("PRAGMA user_version").fetchone()[0])
        columns = {str(row["name"]) for row in connection.execute("PRAGMA table_info(d5_context_provenance)")}
    assert version == 7
    assert "selected_knowledge_json" in columns
    assert {"selected_input_messages_json", "task_run_control_json"}.issubset(columns)
