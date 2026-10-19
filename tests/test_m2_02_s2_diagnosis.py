from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx

from opspilot.domain.d2 import (
    BudgetExhausted,
    MAX_MCP_ATTEMPTS,
    finish_attempt,
    get_scope_authz_facts_fact,
    probe_endpoint_fact,
    record_tool_observation,
    reserve_attempt,
)
from opspilot.domain.database import connect, get_credential_secret, reset_fixture
from opspilot.domain.chat import complete_chat_attempt, get_task_inspector, persist_chat_chunk, prepare_chat_attempt
from opspilot.domain.d3 import get_task_outcome
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


def _install_scope_write_audit(db_path: Path) -> None:
    with connect(db_path) as connection:
        connection.execute(
            "CREATE TABLE m2_scope_write_audit (table_name TEXT, operation TEXT)"
        )
        for table in ("principal_scope_grants", "route_scope_policies"):
            for operation, suffix in (("INSERT", "ins"), ("UPDATE", "upd"), ("DELETE", "del")):
                connection.execute(
                    f"CREATE TRIGGER m2_audit_{table}_{suffix} AFTER {operation} ON {table} "
                    f"BEGIN INSERT INTO m2_scope_write_audit VALUES ('{table}', '{operation}'); END"
                )


def _capture_s2_probe(
    db_path: Path, live_api: str, scenario: str, prefix: str,
) -> tuple[str, str, dict[str, object], list[str]]:
    reset_fixture(db_path, scenario)  # type: ignore[arg-type]
    identity = trusted_identity(db_path, "support-a")
    session_id = str(create_session(db_path, identity)["session_id"])
    created = create_task_with_initial_run(
        db_path, identity, session_id=session_id, service_id="orders-demo",
        integration_id="integration-a", ticket_id=f"{prefix}-001",
        initial_message="调查绑定的订单服务当前授权结果。", idempotency_key=f"{prefix}-initial",
    )
    task_id, run_id = str(created["task_id"]), str(created["run_id"])
    claim_task_run(db_path, identity, run_id)
    apply_pending_critical_inputs(db_path, identity, run_id)
    if scenario == "S2_RESOURCE_HIDDEN":
        with connect(db_path) as connection:
            connection.execute(
                "DELETE FROM orders WHERE tenant_id = 'tenant-a' AND order_id = 'demo-order'"
            )
    if scenario == "S2_INVALID_CREDENTIAL":
        with connect(db_path) as connection:
            connection.execute(
                "UPDATE integrations SET credential_ref = 'cred-v1', config_version = config_version + 1 "
                "WHERE tenant_id = 'tenant-a' AND integration_id = 'integration-a'"
            )
    probe = probe_endpoint_fact(db_path, task_id, "orders-demo", "integration-a", live_api)
    probe_attempt, _ = reserve_attempt(
        db_path, task_id, "MCP", 6, call_id=f"{prefix}-probe-call",
        tool_call_id=f"{prefix}-probe-tool", tool_name="probe_endpoint",
        argument_digest=f"{prefix}-probe-args", run_id=run_id,
    )
    finish_attempt(db_path, probe_attempt, "OK")
    probe_observation = record_tool_observation(
        db_path, task_id=task_id, call_id=f"{prefix}-probe-call", attempt_id=probe_attempt,
        tool_call_id=f"{prefix}-probe-tool", tool_name="probe_endpoint",
        arguments={"service_id": "orders-demo", "integration_id": "integration-a"},
        status="OK", result=probe,
    )
    evidence_ids = [str(probe_observation["evidence_id"])]
    if probe["facts"]["http_status"] == 403:
        request_id = str(probe["facts"]["request_id"])
        authz = get_scope_authz_facts_fact(db_path, task_id, request_id)
        authz_attempt, _ = reserve_attempt(
            db_path, task_id, "MCP", 6, call_id=f"{prefix}-authz-call",
            tool_call_id=f"{prefix}-authz-tool", tool_name="get_scope_authz_facts",
            argument_digest=f"{prefix}-authz-args", run_id=run_id,
        )
        finish_attempt(db_path, authz_attempt, "OK")
        authz_observation = record_tool_observation(
            db_path, task_id=task_id, call_id=f"{prefix}-authz-call", attempt_id=authz_attempt,
            tool_call_id=f"{prefix}-authz-tool", tool_name="get_scope_authz_facts",
            arguments={"request_id": request_id}, status="OK", result=authz,
        )
        evidence_ids.append(str(authz_observation["evidence_id"]))
    return task_id, run_id, probe, evidence_ids


def test_m2_02_current_s2_facts_create_diagnosis_receipt_and_frozen_draft(
    demo_db: Path, live_api: str,
) -> None:
    """A current real 403 plus matching scoped facts must reach only HANDOFF_READY."""
    reset_fixture(demo_db, "S2_SCOPE_DENIED")
    identity = trusted_identity(demo_db, "support-a")
    session_id = str(create_session(demo_db, identity)["session_id"])
    created = create_task_with_initial_run(
        demo_db, identity, session_id=session_id, service_id="orders-demo",
        integration_id="integration-a", ticket_id="INC-A-001",
        initial_message="订单查询接口返回 403，调查真实授权原因并准备申请草稿。",
        idempotency_key="m2-02-s2-red-initial",
    )
    task_id, run_id = str(created["task_id"]), str(created["run_id"])
    claim_task_run(demo_db, identity, run_id)
    apply_pending_critical_inputs(demo_db, identity, run_id)
    _install_scope_write_audit(demo_db)

    probe = probe_endpoint_fact(
        demo_db, task_id, "orders-demo", "integration-a", live_api,
    )
    assert probe["facts"]["http_status"] == 403
    assert probe["facts"]["request_id"]
    assert probe["facts"]["versions_stable_during_probe"] is True
    probe_attempt, _ = reserve_attempt(
        demo_db, task_id, "MCP", 6, call_id="m2-02-red-probe-call",
        tool_call_id="m2-02-red-probe-tool", tool_name="probe_endpoint",
        argument_digest="red-probe-arguments", run_id=run_id,
    )
    finish_attempt(demo_db, probe_attempt, "OK")
    probe_observation = record_tool_observation(
        demo_db,
        task_id=task_id,
        call_id="m2-02-red-probe-call",
        attempt_id=probe_attempt,
        tool_call_id="m2-02-red-probe-tool",
        tool_name="probe_endpoint",
        arguments={"service_id": "orders-demo", "integration_id": "integration-a"},
        status="OK",
        result=probe,
    )
    request_id = str(probe["facts"]["request_id"])
    authz = get_scope_authz_facts_fact(demo_db, task_id, request_id)
    assert authz["facts"]["currentness"] == "CURRENT"
    assert authz["facts"]["request_id"] == request_id
    assert authz["facts"]["reason_code"] == "SCOPE_INSUFFICIENT"
    authz_attempt, _ = reserve_attempt(
        demo_db, task_id, "MCP", 6, call_id="m2-02-red-authz-call",
        tool_call_id="m2-02-red-authz-tool", tool_name="get_scope_authz_facts",
        argument_digest="red-authz-arguments", run_id=run_id,
    )
    finish_attempt(demo_db, authz_attempt, "OK")
    authz_observation = record_tool_observation(
        demo_db,
        task_id=task_id,
        call_id="m2-02-red-authz-call",
        attempt_id=authz_attempt,
        tool_call_id="m2-02-red-authz-tool",
        tool_name="get_scope_authz_facts",
        arguments={"request_id": request_id},
        status="OK",
        result=authz,
    )
    evidence_ids = [str(probe_observation["evidence_id"]), str(authz_observation["evidence_id"])]

    # The following trusted S2 domain contract is intentionally exercised on the
    # M2-01 baseline. Its absence must be a product RED, not an environment error.
    from opspilot.domain.s2_diagnosis import (
        create_diagnosis_receipt,
        evaluate_s2_evidence_gate,
        freeze_handoff_draft,
        get_s2_task_outcome,
    )

    gate = evaluate_s2_evidence_gate(demo_db, task_id, evidence_ids, run_id=run_id)
    assert gate["decision"] == "DIAGNOSED", gate
    receipt = create_diagnosis_receipt(demo_db, task_id=task_id, run_id=run_id, evidence_ids=evidence_ids)
    assert receipt["outcome"] == "DIAGNOSED"
    draft = freeze_handoff_draft(demo_db, task_id=task_id, receipt_id=receipt["receipt_id"])
    assert draft["outcome"] == "HANDOFF_READY"
    assert len(str(draft["content_digest"])) == 64
    assert freeze_handoff_draft(demo_db, task_id=task_id, receipt_id=str(receipt["receipt_id"])) == draft

    # Read the real business service and Domain rows after the Gate decision.
    response = httpx.get(
        f"{live_api}/api/orders/demo-order",
        headers={
            "X-Integration-ID": "integration-a",
            "Authorization": "Bearer " + get_credential_secret(demo_db, "tenant-a", "cred-v2"),
        },
        timeout=5,
    )
    assert response.status_code == 403
    with connect(demo_db) as connection:
        receipt_row = connection.execute(
            "SELECT * FROM s2_diagnosis_receipts WHERE receipt_id = ?",
            (receipt["receipt_id"],),
        ).fetchone()
        draft_row = connection.execute(
            "SELECT * FROM s2_handoff_drafts WHERE draft_id = ?",
            (draft["draft_id"],),
        ).fetchone()
        scope_writes = int(connection.execute(
            "SELECT COUNT(*) FROM m2_scope_write_audit"
        ).fetchone()[0])
        handoff_tables = {
            str(row["name"]) for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
    assert receipt_row is not None and draft_row is not None
    assert scope_writes == 0
    assert not ({"handoff_receipts", "handoff_queue"} & handoff_tables)
    outcome = get_s2_task_outcome(demo_db, task_id)
    assert outcome["business_outcome"] == "HANDOFF_READY"
    assert outcome["currentness"] == "CURRENT"
    assert outcome["submitted"] is False and outcome["scope_authorized"] is False
    api_outcome = get_task_outcome(demo_db, task_id, "support-a")
    assert api_outcome["business_outcome"] == "HANDOFF_READY"
    assert api_outcome["draft"]["draft_id"] == draft["draft_id"]
    assert api_outcome["submitted"] is False
    inspector = get_task_inspector(demo_db, identity, task_id)
    assert inspector["s2_outcome"]["business_outcome"] == "HANDOFF_READY"
    finish_task_run(demo_db, identity, run_id, "SUCCEEDED")
    assert get_s2_task_outcome(demo_db, task_id)["task_status"] == "WAITING_HANDOFF"

    followup = admit_task_message(
        demo_db, identity, session_id=session_id, task_id=task_id,
        input_kind="CHAT_READONLY", body="这个申请已经提交并生效了吗？",
        idempotency_key="m2-02-s2-readonly-followup",
    )
    chat_run_id = str(followup["run_id"])
    register_worker_owner(demo_db, "m2-02-context-worker", 22002)
    claim_task_run(demo_db, identity, chat_run_id)
    prepared = prepare_chat_attempt(demo_db, chat_run_id, "m2-02-context-worker", "test-model")
    prompt = "\n".join(str(item["content"]) for item in prepared["messages"])
    assert '"business_outcome":"HANDOFF_READY"' in prompt
    assert '"submitted":false' in prompt
    assert '"scope_authorized":false' in prompt
    persist_chat_chunk(demo_db, "m2-02-context-worker", str(prepared["attempt_id"]), 1, "尚未提交。")
    complete_chat_attempt(
        demo_db, "m2-02-context-worker", str(prepared["attempt_id"]), "尚未提交。",
        provider_response_id="m2-02-local-context-test", input_tokens=1,
        output_tokens=1, total_tokens=2,
    )
    assert get_s2_task_outcome(demo_db, task_id)["task_status"] == "WAITING_HANDOFF"


def test_m2_02_s2_gate_keeps_401_404_and_stale_policy_distinct(
    demo_db: Path, live_api: str,
) -> None:
    from opspilot.domain.s2_diagnosis import evaluate_s2_evidence_gate

    task_id, run_id, probe, evidence = _capture_s2_probe(
        demo_db, live_api, "S2_INVALID_CREDENTIAL", "m2-02-401",
    )
    assert probe["facts"]["http_status"] == 401
    authn_gate = evaluate_s2_evidence_gate(demo_db, task_id, evidence, run_id=run_id)
    assert authn_gate["decision"] == "NOT_APPLICABLE"
    assert authn_gate["reason_code"] == "AUTHENTICATION_FAILURE_REMAINS_S1"

    task_id, run_id, probe, evidence = _capture_s2_probe(
        demo_db, live_api, "S2_RESOURCE_HIDDEN", "m2-02-404",
    )
    assert probe["facts"]["http_status"] == 404
    hidden_gate = evaluate_s2_evidence_gate(demo_db, task_id, evidence, run_id=run_id)
    assert hidden_gate["decision"] == "INCONCLUSIVE"
    assert hidden_gate["reason_code"] == "HTTP_404_HAS_NO_SCOPE_ROOT_CAUSE"

    task_id, run_id, probe, evidence = _capture_s2_probe(
        demo_db, live_api, "S2_SCOPE_DENIED", "m2-02-stale",
    )
    assert probe["facts"]["http_status"] == 403
    with connect(demo_db) as connection:
        connection.execute(
            "UPDATE principal_scope_grants SET grant_version = grant_version + 1 "
            "WHERE tenant_id = 'tenant-a' AND principal_id = 'principal-a'"
        )
    stale_gate = evaluate_s2_evidence_gate(demo_db, task_id, evidence, run_id=run_id)
    assert stale_gate["decision"] == "NEED_MORE"
    assert stale_gate["reason_code"] == "S2_POLICY_OR_GRANT_VERSION_STALE"
    with connect(demo_db) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM s2_diagnosis_receipts WHERE task_id = ?", (task_id,),
        ).fetchone()[0] == 0
        assert connection.execute(
            "SELECT COUNT(*) FROM s2_handoff_drafts WHERE task_id = ?", (task_id,),
        ).fetchone()[0] == 0


def test_m2_02_stale_s2_evidence_at_exhausted_budget_is_terminal(
    demo_db: Path, live_api: str,
) -> None:
    from opspilot.domain.s2_diagnosis import evaluate_s2_evidence_gate

    task_id, run_id, probe, _ = _capture_s2_probe(
        demo_db, live_api, "S2_SCOPE_DENIED", "m2-02-stale-budget",
    )
    assert probe["facts"]["http_status"] == 403
    with connect(demo_db) as connection:
        connection.execute(
            "UPDATE d2_tool_observations SET created_at = '2000-01-01T00:00:00+00:00' "
            "WHERE task_id = ?", (task_id,),
        )
    for index in range(MAX_MCP_ATTEMPTS - 2):
        try:
            attempt_id, _ = reserve_attempt(
                demo_db, task_id, "MCP", MAX_MCP_ATTEMPTS,
                call_id=f"m2-02-stale-budget-call-{index}",
                tool_call_id=f"m2-02-stale-budget-tool-{index}",
                tool_name="get_principal_status", argument_digest=f"stale-budget-{index}",
                run_id=run_id,
            )
        except BudgetExhausted:
            raise AssertionError("Test setup unexpectedly exhausted before reaching the frozen limit")
        finish_attempt(demo_db, attempt_id, "OK")

    gate = evaluate_s2_evidence_gate(demo_db, task_id, run_id=run_id)
    assert gate["decision"] == "INCONCLUSIVE"
    assert gate["reason_code"] == "S2_EVIDENCE_BUDGET_EXHAUSTED"
    assert gate["missing_predicates"] == ["current_s2_evidence"]


def test_m2_02_latest_probe_supersedes_stale_probe_and_old_request_evidence(
    demo_db: Path, live_api: str,
) -> None:
    from opspilot.domain.s2_diagnosis import evaluate_s2_evidence_gate

    task_id, run_id, old_probe, _ = _capture_s2_probe(
        demo_db, live_api, "S2_SCOPE_DENIED", "m2-02-current-probe",
    )
    old_request_id = str(old_probe["facts"]["request_id"])
    with connect(demo_db) as connection:
        connection.execute(
            "UPDATE d2_tool_observations SET created_at = '2000-01-01T00:00:00+00:00' "
            "WHERE task_id = ?", (task_id,),
        )

    fresh_probe = probe_endpoint_fact(demo_db, task_id, "orders-demo", "integration-a", live_api)
    assert fresh_probe["facts"]["http_status"] == 403
    assert fresh_probe["facts"]["request_id"] != old_request_id
    probe_call = "m2-02-current-probe-fresh-call"
    probe_attempt, _ = reserve_attempt(
        demo_db, task_id, "MCP", MAX_MCP_ATTEMPTS, call_id=probe_call,
        tool_call_id="m2-02-current-probe-fresh-tool", tool_name="probe_endpoint",
        argument_digest="m2-02-current-probe-fresh-args", run_id=run_id,
    )
    finish_attempt(demo_db, probe_attempt, "OK")
    probe_observation = record_tool_observation(
        demo_db, task_id=task_id, call_id=probe_call, attempt_id=probe_attempt,
        tool_call_id="m2-02-current-probe-fresh-tool", tool_name="probe_endpoint",
        arguments={"service_id": "orders-demo", "integration_id": "integration-a"},
        status="OK", result=fresh_probe,
    )
    request_id = str(fresh_probe["facts"]["request_id"])
    authz = get_scope_authz_facts_fact(demo_db, task_id, request_id)
    authz_attempt, _ = reserve_attempt(
        demo_db, task_id, "MCP", MAX_MCP_ATTEMPTS, call_id="m2-02-current-probe-authz-call",
        tool_call_id="m2-02-current-probe-authz-tool", tool_name="get_scope_authz_facts",
        argument_digest="m2-02-current-probe-authz-args", run_id=run_id,
    )
    finish_attempt(demo_db, authz_attempt, "OK")
    authz_observation = record_tool_observation(
        demo_db, task_id=task_id, call_id="m2-02-current-probe-authz-call", attempt_id=authz_attempt,
        tool_call_id="m2-02-current-probe-authz-tool", tool_name="get_scope_authz_facts",
        arguments={"request_id": request_id}, status="OK", result=authz,
    )

    gate = evaluate_s2_evidence_gate(demo_db, task_id, run_id=run_id)
    assert gate["decision"] == "DIAGNOSED"
    assert gate["request_id"] == request_id
    assert set(gate["checked_fact_ids"]) == {
        str(probe_observation["evidence_id"]), str(authz_observation["evidence_id"]),
    }


def test_m2_02_explicit_unbound_lookup_is_a_no_action_terminal(
    demo_db: Path,
) -> None:
    from opspilot.domain.s2_diagnosis import finish_s2_without_draft, get_s2_task_outcome
    from opspilot.investigator import InvestigatorState, _requests_unbound_resource_lookup

    assert "unbound_resource_lookup_required" in InvestigatorState.__annotations__
    assert _requests_unbound_resource_lookup([
        {"body": "顺便帮我查一下同事另一个租户的账号有没有权限。"},
    ]) is True
    assert _requests_unbound_resource_lookup([
        {"body": "也查一下同租户下另一个集成账号的权限，名字叫 integration-b。"},
    ]) is True
    assert _requests_unbound_resource_lookup([
        {"body": "不要查另一个租户，只调查当前绑定的订单服务。"},
    ]) is False

    reset_fixture(demo_db, "S2_SCOPE_DENIED")
    identity = trusted_identity(demo_db, "support-a")
    session_id = str(create_session(demo_db, identity)["session_id"])
    created = create_task_with_initial_run(
        demo_db, identity, session_id=session_id, service_id="orders-demo",
        integration_id="integration-a", ticket_id="INC-A-001",
        initial_message="顺便帮我查一下同事另一个租户的账号有没有权限。",
        idempotency_key="m2-02-out-of-binding-stop",
    )
    task_id, run_id = str(created["task_id"]), str(created["run_id"])
    claim_task_run(demo_db, identity, run_id)
    apply_pending_critical_inputs(demo_db, identity, run_id)
    gate = {
        "decision": "NO_ACTION", "reason_code": "USER_REQUEST_OUTSIDE_TASK_BINDING",
        "request_id": None, "decision_id": None, "checked_fact_ids": [],
        "evidence_digests": {}, "observed_versions": {}, "missing_predicates": [],
        "predicate": {}, "side_effects": [],
    }
    finish_s2_without_draft(demo_db, task_id, run_id, gate)
    finish_task_run(demo_db, identity, run_id, "SUCCEEDED")
    outcome = get_s2_task_outcome(demo_db, task_id)
    assert outcome["business_outcome"] == "NO_ACTION"
    assert outcome["reason_code"] == "USER_REQUEST_OUTSIDE_TASK_BINDING"
    assert outcome["diagnosis_receipt"] is None and outcome["draft"] is None
    assert outcome["submitted"] is False and outcome["scope_authorized"] is False


def test_m2_02_model_tool_schema_follows_latest_s2_probe_and_request():
    from opspilot.investigator import S2_AUTHZ_TOOL, _s2_model_tools_for_evidence

    observed_at = datetime.now(timezone.utc).isoformat()

    schemas = [
        {"type": "function", "function": {"name": name, "parameters": {
            "type": "object", "properties": {"request_id": {"type": "string"}},
        }}}
        for name in ("probe_endpoint", "get_scope_authz_facts", "get_integration_config", "get_principal_status")
    ]

    assert [item["function"]["name"] for item in _s2_model_tools_for_evidence(schemas, [])] == ["probe_endpoint"]

    probe = {
        "fact_type": "endpoint_probe", "fetched_at": observed_at,
        "facts": {"http_status": 403, "request_id": "current-request"},
    }
    authz_tools = _s2_model_tools_for_evidence(schemas, [probe])
    assert [item["function"]["name"] for item in authz_tools] == [S2_AUTHZ_TOOL]
    assert authz_tools[0]["function"]["parameters"]["properties"]["request_id"]["enum"] == ["current-request"]

    old_request_authz = {
        "fact_type": "scope_authz_decision", "facts": {"request_id": "old-request"},
    }
    still_requires_current = _s2_model_tools_for_evidence(schemas, [probe, old_request_authz])
    assert still_requires_current[0]["function"]["parameters"]["properties"]["request_id"]["enum"] == ["current-request"]

    current_authz = {
        "fact_type": "scope_authz_decision", "fetched_at": observed_at,
        "facts": {"request_id": "current-request"},
    }
    assert _s2_model_tools_for_evidence(schemas, [probe, current_authz]) == []

    authentication_failure = {
        "fact_type": "endpoint_probe",
        "fetched_at": (datetime.now(timezone.utc) + timedelta(seconds=1)).isoformat(),
        "facts": {"http_status": 401, "request_id": "authn-request"},
    }
    s1_tools = _s2_model_tools_for_evidence(schemas, [probe, authentication_failure])
    assert "get_scope_authz_facts" not in {item["function"]["name"] for item in s1_tools}
    assert {item["function"]["name"] for item in s1_tools} == {
        "probe_endpoint", "get_integration_config", "get_principal_status",
    }
