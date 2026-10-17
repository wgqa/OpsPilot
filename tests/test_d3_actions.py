from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from opspilot.domain.d2 import (
    create_task_binding,
    evaluate_evidence_gate,
    get_auth_policy_fact,
    get_integration_config_fact,
    get_principal_status_fact,
    list_evidence,
    probe_endpoint_fact,
    record_tool_observation,
)
from opspilot.domain.d3 import (
    D3PreconditionRejected,
    D3ScopeDenied,
    KeyReuseConflict,
    activate_plan,
    authorize_workflow_resume,
    cancel_plan,
    create_plan_from_gate,
    execute_deliver,
    execute_repair,
    get_or_create_action_intent,
    get_or_create_report,
    get_task_action_state,
    get_task_ticket_entries,
    get_verification_receipt,
    save_local_report,
    submit_plan_approval,
    verify_repair_online,
)
from opspilot.domain.database import connect, get_integration_info, reset_fixture


def _store(db: Path, task_id: str, tool: str, fact: dict[str, object], index: int) -> str:
    result = record_tool_observation(
        db,
        task_id=task_id,
        call_id=f"d3-test-call-{index}",
        attempt_id=None,
        tool_call_id=f"d3-test-tool-{index}",
        tool_name=tool,
        arguments={"test_index": index},
        status="OK",
        result=fact,
    )
    return str(result["evidence_id"])


def _ready(db: Path, api_url: str, *, actor: str = "support-a", ticket: str = "INC-A-001"):
    binding = create_task_binding(db, actor, "orders-demo", "integration-a" if actor == "support-a" else "integration-b", ticket)
    task_id = str(binding["task_id"])
    suffix = "a" if actor == "support-a" else "b"
    integration = f"integration-{suffix}"
    principal = f"principal-{suffix}"
    evidence_ids = [
        _store(db, task_id, "get_integration_config", get_integration_config_fact(db, task_id, integration), 1),
        _store(db, task_id, "get_principal_status", get_principal_status_fact(db, task_id, principal), 2),
        _store(db, task_id, "get_auth_policy", get_auth_policy_fact(db, task_id, "orders-demo"), 3),
        _store(db, task_id, "probe_endpoint", probe_endpoint_fact(db, task_id, "orders-demo", integration, api_url), 4),
    ]
    gate = evaluate_evidence_gate(db, task_id, evidence_ids)
    return binding, gate, create_plan_from_gate(db, task_id, actor, gate)


def _approve(db: Path, binding: dict[str, object], plan: dict[str, object], decision: str = "APPROVED"):
    return submit_plan_approval(
        db, str(binding["thread_id"]), "approver-a" if binding["tenant_id"] == "tenant-a" else "approver-b",
        str(plan["plan_hash"]), decision,  # type: ignore[arg-type]
    )


def test_d3_plan_repair_verify_freeze_and_independent_delivery_are_idempotent(demo_db: Path, live_api: str) -> None:
    binding, gate, plan = _ready(demo_db, live_api)
    assert gate["decision"] == "READY"
    assert plan["required_evidence_ids"] == gate["checked_fact_ids"]
    assert plan["ticket_id"] == binding["ticket_id"]
    assert activate_plan(demo_db, str(binding["task_id"]), str(plan["plan_hash"]), "support-a")["plan_hash"] == plan["plan_hash"]

    approval = _approve(demo_db, binding, plan)
    assert approval["decision"] == "APPROVED"
    repair_intent = get_or_create_action_intent(demo_db, str(binding["task_id"]), str(plan["plan_hash"]), "REPAIR", "executor-a")
    assert get_or_create_action_intent(demo_db, str(binding["task_id"]), str(plan["plan_hash"]), "REPAIR", "executor-a")["action_id"] == repair_intent["action_id"]
    assert get_integration_info(demo_db, "tenant-a", "integration-a")["config_version"] == 7

    repair = execute_repair(demo_db, str(repair_intent["action_id"]), "executor-a", "attempt-one")
    assert repair["status"] == "COMMITTED"
    assert repair["before_version"] == 7 and repair["after_version"] == 8
    assert execute_repair(demo_db, str(repair_intent["action_id"]), "executor-a", "attempt-replay")["ledger_id"] == repair["ledger_id"]
    assert get_integration_info(demo_db, "tenant-a", "integration-a")["credential_ref"] == "cred-v2"

    receipt = verify_repair_online(demo_db, str(binding["task_id"]), str(plan["plan_hash"]), str(repair_intent["action_id"]), "executor-a", live_api)
    assert receipt["recovery_verified"] is True
    assert receipt["response_status"] == 200
    assert receipt["business_assertions"]["response_body"]["order_id"] == "demo-order"
    assert receipt["business_assertions"]["response_body"]["status"] == "CONFIRMED"
    assert get_verification_receipt(demo_db, str(binding["task_id"]), str(receipt["verification_id"]), "executor-a")["recovery_verified"] is True
    frozen = get_or_create_report(demo_db, str(binding["task_id"]), str(plan["plan_hash"]), str(repair_intent["action_id"]), "executor-a")
    assert frozen["report"]["business_outcome"] == "RECOVERED"

    deliver_intent = get_or_create_action_intent(demo_db, str(binding["task_id"]), str(plan["plan_hash"]), "DELIVER", "executor-a")
    assert deliver_intent["action_id"] != repair_intent["action_id"]
    delivered = execute_deliver(demo_db, str(deliver_intent["action_id"]), "executor-a", "attempt-deliver")
    assert delivered["status"] == "COMMITTED"
    assert execute_deliver(demo_db, str(deliver_intent["action_id"]), "executor-a", "attempt-deliver-replay")["ledger_id"] == delivered["ledger_id"]
    assert _approve(demo_db, binding, plan)["approval_id"] == approval["approval_id"]
    state = get_task_action_state(demo_db, str(binding["task_id"]), "support-a")
    assert len(state["action_intents"]) == 2
    assert {row["action_kind"] for row in state["action_ledgers"]} == {"REPAIR", "DELIVER"}
    assert {row["state"] for row in state["permissions"]} == {"CONSUMED"}
    assert len(state["report_artifacts"]) == len(state["delivery_records"]) == len(state["ticket_entries"]) == 1
    assert len(get_task_ticket_entries(demo_db, str(binding["task_id"]), "support-a")) == 1


def test_d3_rejection_creates_no_action_intents_or_business_writes(demo_db: Path, live_api: str) -> None:
    binding, gate, plan = _ready(demo_db, live_api)
    approval = _approve(demo_db, binding, plan, "REJECTED")
    assert approval["decision"] == "REJECTED"
    with pytest.raises(D3PreconditionRejected, match="APPROVAL_DOES_NOT_BIND_PLAN"):
        get_or_create_action_intent(demo_db, str(binding["task_id"]), str(plan["plan_hash"]), "REPAIR", "executor-a")
    integration = get_integration_info(demo_db, "tenant-a", "integration-a")
    assert integration["credential_ref"] == "cred-v1" and integration["config_version"] == 7
    state = get_task_action_state(demo_db, str(binding["task_id"]), "support-a")
    assert state["action_intents"] == []
    assert state["action_ledgers"] == []
    assert state["ticket_entries"] == []
    local = save_local_report(demo_db, str(binding["task_id"]), "REJECTED", {"approval_id": approval["approval_id"]}, str(plan["plan_hash"]))
    assert local["report"]["outcome"] == "REJECTED"
    assert get_task_action_state(demo_db, str(binding["task_id"]), "support-a")["local_reports"][0]["outcome"] == "REJECTED"


def test_d3_plan_cancellation_blocks_approval_and_action(demo_db: Path, live_api: str) -> None:
    binding, gate, plan = _ready(demo_db, live_api)
    cancelled = cancel_plan(demo_db, str(binding["task_id"]), str(plan["plan_hash"]), "support-a", "operator cancelled before approval")
    assert cancelled["eligibility"] == "CANCELLED"
    with pytest.raises(D3PreconditionRejected, match="PLAN_NOT_ACTIVE"):
        _approve(demo_db, binding, plan)
    with pytest.raises(D3PreconditionRejected, match="PLAN_ALREADY_INACTIVE"):
        activate_plan(demo_db, str(binding["task_id"]), str(plan["plan_hash"]), "support-a")


def test_d3_approval_requires_task_tenant_approver_and_intact_plan_hash(demo_db: Path, live_api: str) -> None:
    binding, gate, plan = _ready(demo_db, live_api)
    with pytest.raises(D3ScopeDenied, match="approver"):
        submit_plan_approval(demo_db, str(binding["thread_id"]), "approver-b", str(plan["plan_hash"]), "APPROVED")
    with pytest.raises(D3ScopeDenied, match="authorized before checkpoint"):
        authorize_workflow_resume(demo_db, str(binding["thread_id"]), "approver-a")
    with connect(demo_db) as connection:
        stored = json.loads(connection.execute(
            "SELECT canonical_plan_json FROM d3_plans WHERE plan_hash = ?", (plan["plan_hash"],)
        ).fetchone()[0])
        stored["new_credential_ref"] = "cred-attacker"
        connection.execute(
            "UPDATE d3_plans SET canonical_plan_json = ? WHERE plan_hash = ?",
            (json.dumps(stored, sort_keys=True, separators=(",", ":")), plan["plan_hash"]),
        )
    with pytest.raises(D3PreconditionRejected, match="PLAN_HASH_MISMATCH"):
        _approve(demo_db, binding, plan)
    current = get_integration_info(demo_db, "tenant-a", "integration-a")
    assert current["credential_ref"] == "cred-v1" and current["config_version"] == 7


@pytest.mark.parametrize("update_sql", [
    "UPDATE integrations SET config_version = 9 WHERE tenant_id = 'tenant-a' AND integration_id = 'integration-a'",
    "UPDATE principals SET principal_version = 3 WHERE tenant_id = 'tenant-a' AND principal_id = 'principal-a'",
    "UPDATE auth_policies SET policy_version = 4 WHERE tenant_id = 'tenant-a' AND service_id = 'orders-demo'",
])
def test_d3_resource_version_change_blocks_repair_without_changing_its_new_value(demo_db: Path, live_api: str, update_sql: str) -> None:
    binding, gate, plan = _ready(demo_db, live_api)
    _approve(demo_db, binding, plan)
    intent = get_or_create_action_intent(demo_db, str(binding["task_id"]), str(plan["plan_hash"]), "REPAIR", "executor-a")
    with connect(demo_db) as connection:
        connection.execute(update_sql)
    with pytest.raises(D3PreconditionRejected, match="RESOURCE_VERSION_OR_CREDENTIAL_PRECONDITION_FAILED"):
        execute_repair(demo_db, str(intent["action_id"]), "executor-a", "attempt-stale")
    current = get_integration_info(demo_db, "tenant-a", "integration-a")
    expected_config_version = 9 if "integrations SET" in update_sql else 7
    assert current["credential_ref"] == "cred-v1" and current["config_version"] == expected_config_version
    state = get_task_action_state(demo_db, str(binding["task_id"]), "support-a")
    assert state["action_ledgers"] == [] and state["ticket_entries"] == []


def test_d3_failed_online_probe_cannot_freeze_or_deliver_recovered_report(demo_db: Path, live_api: str) -> None:
    binding, gate, plan = _ready(demo_db, live_api)
    _approve(demo_db, binding, plan)
    repair_intent = get_or_create_action_intent(demo_db, str(binding["task_id"]), str(plan["plan_hash"]), "REPAIR", "executor-a")
    execute_repair(demo_db, str(repair_intent["action_id"]), "executor-a", "attempt-repair")
    with connect(demo_db) as connection:
        connection.execute("UPDATE principals SET status = 'DISABLED', principal_version = 3 WHERE tenant_id = 'tenant-a' AND principal_id = 'principal-a'")
    receipt = verify_repair_online(demo_db, str(binding["task_id"]), str(plan["plan_hash"]), str(repair_intent["action_id"]), "executor-a", live_api)
    assert receipt["response_status"] == 401 and receipt["recovery_verified"] is False
    with pytest.raises(D3PreconditionRejected, match="REPORT_REQUIRES_COMMITTED_REPAIR_AND_RECOVERED_VERIFICATION"):
        get_or_create_report(demo_db, str(binding["task_id"]), str(plan["plan_hash"]), str(repair_intent["action_id"]), "executor-a")
    with pytest.raises(D3PreconditionRejected, match="FROZEN_REPORT_NOT_FOUND"):
        get_or_create_action_intent(demo_db, str(binding["task_id"]), str(plan["plan_hash"]), "DELIVER", "executor-a")
    assert get_task_ticket_entries(demo_db, str(binding["task_id"]), "support-a") == []


def test_d3_same_action_key_with_changed_canonical_request_is_rejected(demo_db: Path, live_api: str) -> None:
    binding, gate, plan = _ready(demo_db, live_api)
    _approve(demo_db, binding, plan)
    intent = get_or_create_action_intent(demo_db, str(binding["task_id"]), str(plan["plan_hash"]), "REPAIR", "executor-a")
    request = json.loads(str(intent["canonical_request_json"]))
    request["action_parameters"]["new_credential_ref"] = "cred-other"
    tampered = json.dumps(request, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    tampered_digest = hashlib.sha256(tampered.encode("utf-8")).hexdigest()
    with connect(demo_db) as connection:
        connection.execute(
            "UPDATE d3_action_intents SET canonical_request_json = ?, request_digest = ? WHERE action_id = ?",
            (tampered, tampered_digest, intent["action_id"]),
        )
    with pytest.raises(KeyReuseConflict, match="KEY_REUSE_CONFLICT"):
        execute_repair(demo_db, str(intent["action_id"]), "executor-a", "attempt-tampered")
    current = get_integration_info(demo_db, "tenant-a", "integration-a")
    assert current["credential_ref"] == "cred-v1" and current["config_version"] == 7


def test_d3_delivery_rejects_wrong_ticket_before_ticket_write(demo_db: Path, live_api: str) -> None:
    binding, gate, plan = _ready(demo_db, live_api)
    _approve(demo_db, binding, plan)
    repair_intent = get_or_create_action_intent(demo_db, str(binding["task_id"]), str(plan["plan_hash"]), "REPAIR", "executor-a")
    execute_repair(demo_db, str(repair_intent["action_id"]), "executor-a", "attempt-repair")
    receipt = verify_repair_online(demo_db, str(binding["task_id"]), str(plan["plan_hash"]), str(repair_intent["action_id"]), "executor-a", live_api)
    assert receipt["recovery_verified"]
    get_or_create_report(demo_db, str(binding["task_id"]), str(plan["plan_hash"]), str(repair_intent["action_id"]), "executor-a")
    deliver_intent = get_or_create_action_intent(demo_db, str(binding["task_id"]), str(plan["plan_hash"]), "DELIVER", "executor-a")
    request = json.loads(str(deliver_intent["canonical_request_json"]))
    request["action_parameters"]["ticket_id"] = "INC-B-001"
    tampered = json.dumps(request, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    tampered_digest = hashlib.sha256(tampered.encode("utf-8")).hexdigest()
    with connect(demo_db) as connection:
        connection.execute(
            "UPDATE d3_action_intents SET canonical_request_json = ?, request_digest = ? WHERE action_id = ?",
            (tampered, tampered_digest, deliver_intent["action_id"]),
        )
    with pytest.raises(KeyReuseConflict, match="KEY_REUSE_CONFLICT"):
        execute_deliver(demo_db, str(deliver_intent["action_id"]), "executor-a", "attempt-wrong-ticket")
    state = get_task_action_state(demo_db, str(binding["task_id"]), "support-a")
    assert state["ticket_entries"] == [] and state["delivery_records"] == []
    with pytest.raises(D3ScopeDenied):
        get_task_ticket_entries(demo_db, str(binding["task_id"]), "support-b")


def test_d3_disabled_principal_cannot_create_plan(demo_db: Path, live_api: str) -> None:
    reset_fixture(demo_db, "S1_DISABLED")
    binding = create_task_binding(demo_db, "support-a", "orders-demo", "integration-a")
    task_id = str(binding["task_id"])
    evidence_ids = [
        _store(demo_db, task_id, "get_integration_config", get_integration_config_fact(demo_db, task_id, "integration-a"), 1),
        _store(demo_db, task_id, "get_principal_status", get_principal_status_fact(demo_db, task_id, "principal-a"), 2),
        _store(demo_db, task_id, "get_auth_policy", get_auth_policy_fact(demo_db, task_id, "orders-demo"), 3),
        _store(demo_db, task_id, "probe_endpoint", probe_endpoint_fact(demo_db, task_id, "orders-demo", "integration-a", live_api), 4),
    ]
    gate = evaluate_evidence_gate(demo_db, task_id, evidence_ids)
    assert gate["decision"] == "NO_ACTION"
    with pytest.raises(D3PreconditionRejected, match="NON_READY_CANNOT_CREATE_EXECUTABLE_PLAN"):
        create_plan_from_gate(demo_db, task_id, "support-a", gate)
    assert get_integration_info(demo_db, "tenant-a", "integration-a")["config_version"] == 7
