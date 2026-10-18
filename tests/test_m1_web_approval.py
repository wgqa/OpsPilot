from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from opspilot.config import MODEL_API_KEY, MODEL_NAME
from opspilot.domain.d2 import (
    evaluate_evidence_gate,
    get_auth_policy_fact,
    get_integration_config_fact,
    get_principal_status_fact,
    probe_endpoint_fact,
    record_tool_observation,
)
from opspilot.domain.database import connect, get_integration_info
from opspilot.domain.d3 import cancel_plan, get_task_action_state
from opspilot.domain.task_control import (
    TaskControlError,
    claim_task_run,
    finish_task_run,
    get_approval_resume_link,
    trusted_identity,
)
from opspilot.domain.d3 import create_plan_from_gate
from opspilot.web.app import create_app


PASSWORDS = {
    "support-a": "support-test-password",
    "approver-a": "approver-test-password",
    "support-b": "support-b-test-password",
    "approver-b": "approver-b-test-password",
}
ORIGIN = "http://testserver"


@pytest.fixture
def approval_client(demo_db: Path, tmp_path: Path):
    app = create_app(
        db_path=demo_db,
        checkpoint_db_path=tmp_path / "checkpoints.sqlite3",
        start_worker=False,
        credentials=PASSWORDS,
        expected_origin=ORIGIN,
    )
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client


def _login(client: TestClient, actor_id: str) -> dict[str, str]:
    response = client.post(
        "/api/auth/login", headers={"Origin": ORIGIN},
        json={"actor_id": actor_id, "password": PASSWORDS[actor_id]},
    )
    assert response.status_code == 200, response.text
    return {"Origin": ORIGIN, "X-CSRF-Token": response.json()["csrf_token"]}


def _count(db: Path, table: str, where: str, params: tuple[object, ...]) -> int:
    with connect(db) as connection:
        return int(connection.execute(f"SELECT COUNT(*) FROM {table} WHERE {where}", params).fetchone()[0])


def _prepare_waiting_task(
    client: TestClient, db: Path, live_api: str, tmp_path: Path, *, key: str = "approval-task"
) -> dict[str, object]:
    support_headers = _login(client, "support-a")
    session_response = client.post("/api/sessions", headers=support_headers)
    assert session_response.status_code == 201, session_response.text
    session_id = str(session_response.json()["session_id"])
    created_response = client.post(
        f"/api/sessions/{session_id}/tasks",
        headers={**support_headers, "Idempotency-Key": key},
        json={"initial_message": "订单 API 在凭证轮换后返回 401，请调查当前事实。"},
    )
    assert created_response.status_code == 202, created_response.text
    created = created_response.json()
    task_id, source_run_id = str(created["task_id"]), str(created["run_id"])
    identity = trusted_identity(db, "support-a")
    claim_task_run(db, identity, source_run_id)

    from opspilot.domain.d2 import get_task_binding

    binding = get_task_binding(db, task_id)
    facts = [
        ("get_integration_config", get_integration_config_fact(db, task_id, "integration-a")),
        ("get_principal_status", get_principal_status_fact(db, task_id, "principal-a")),
        ("get_auth_policy", get_auth_policy_fact(db, task_id, "orders-demo")),
        ("probe_endpoint", probe_endpoint_fact(db, task_id, "orders-demo", "integration-a", live_api)),
    ]
    evidence_ids: list[str] = []
    for index, (tool_name, fact) in enumerate(facts, start=1):
        evidence = record_tool_observation(
            db,
            task_id=task_id,
            call_id=f"m1-05-approval-call-{index}",
            attempt_id=None,
            tool_call_id=f"m1-05-approval-tool-{index}",
            tool_name=tool_name,
            arguments={"probe": index},
            status="OK",
            result=fact,
        )
        evidence_ids.append(str(evidence["evidence_id"]))
    gate = evaluate_evidence_gate(db, task_id, evidence_ids)
    assert gate["decision"] == "READY"
    plan = create_plan_from_gate(db, task_id, "support-a", gate, run_id=source_run_id)
    finish_task_run(db, identity, source_run_id, "WAITING_APPROVAL")

    checkpoint_path = tmp_path / f"checkpoint-{task_id}.sqlite3"
    _seed_approval_interrupt(db, checkpoint_path, binding, plan, source_run_id, live_api)
    return {
        "task_id": task_id, "session_id": session_id, "support_headers": support_headers,
        "source_run_id": source_run_id, "binding": binding, "plan": plan,
        "checkpoint_path": checkpoint_path, "gate": gate,
    }


def _seed_approval_interrupt(
    db: Path, checkpoint_path: Path, binding: dict[str, object], plan: dict[str, object],
    source_run_id: str, live_api: str,
) -> None:
    from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
    from opspilot.investigator import build_investigation_graph

    async def seed() -> None:
        async with AsyncSqliteSaver.from_conn_string(str(checkpoint_path)) as checkpointer:
            await checkpointer.setup()
            graph = build_investigation_graph(
                db, str(binding["task_id"]), "m1-05-test-no-provider-call", None, [], [], None,
                checkpointer, checkpoint_path, d3_mode=True,
                submitter_id=str(binding["actor_id"]), executor_id="executor-a",
                business_api_url=live_api, run_id=source_run_id,
            )
            config = {"configurable": {"thread_id": f"{binding['thread_id']}::{source_run_id}"}}
            await graph.aupdate_state(config, {
                "task_binding_id": str(binding["task_id"]),
                "stage": "d3_plan_created",
                "plan_id": str(plan["plan_id"]),
                "plan_hash": str(plan["plan_hash"]),
                "budget": {"MODEL": 0, "MCP": 0},
                "diagnosis_draft": {},
                "evidence_ids": list(plan["required_evidence_ids"]),
                "tool_observations": [],
                "pending_call_refs": [],
                "gate_decision": {"decision": "READY"},
            }, as_node="d3_create_plan")
            await graph.ainvoke(None, config)
            snapshot = await graph.aget_state(config)
            assert snapshot.values.get("stage") == "d3_plan_created"
            assert snapshot.next == ("d3_human_approval",)
            assert snapshot.tasks and snapshot.tasks[0].interrupts

    asyncio.run(seed())


def _approve(
    client: TestClient, task: dict[str, object], *, decision: str = "APPROVED", key: str = "approval-submit"
):
    headers = _login(client, "approver-a")
    return client.post(
        f"/api/tasks/{task['task_id']}/plans/{task['plan']['plan_hash']}/approval",
        headers={**headers, "Idempotency-Key": key}, json={"decision": decision},
    )


def test_apr01_web_roles_review_scope_and_minimum_snapshot(
    approval_client: TestClient, demo_db: Path, live_api: str, tmp_path: Path
) -> None:
    task = _prepare_waiting_task(approval_client, demo_db, live_api, tmp_path)
    plan = task["plan"]
    support = task["support_headers"]
    approver_headers = _login(approval_client, "approver-a")
    pending = approval_client.get("/api/approvals/pending", headers=approver_headers)
    review = approval_client.get(
        f"/api/tasks/{task['task_id']}/plans/{plan['plan_hash']}/review", headers=approver_headers,
    )
    assert pending.status_code == review.status_code == 200
    assert any(item["task_id"] == task["task_id"] and item["plan_hash"] == plan["plan_hash"] for item in pending.json()["items"])
    body = review.json()
    assert body["plan_hash"] == plan["plan_hash"]
    assert body["current_state"]["version_compatible"] is True
    assert {item["fact_type"] for item in body["evidence"]} == {
        "integration_config", "principal_status", "auth_policy", "endpoint_probe",
    }
    assert body["scope"] == {
        "actions": ["REPAIR", "DELIVER"],
        "executor": "trusted service configuration",
        "secrets_exposed": False,
    }
    assert "messages" not in body and "prompt" not in json.dumps(body).lower()
    support_client = TestClient(approval_client.app, raise_server_exceptions=False)
    try:
        support_session_headers = _login(support_client, "support-a")
        support_approval = support_client.post(
            f"/api/tasks/{task['task_id']}/plans/{plan['plan_hash']}/approval",
            headers={**support_session_headers, "Idempotency-Key": "support-must-not-approve"},
            json={"decision": "APPROVED"},
        )
        assert support_approval.status_code == 403 and support_approval.json()["code"] == "TASK_APPROVER_REQUIRED"
        assert support_client.get(
            f"/api/tasks/{task['task_id']}/plans/{plan['plan_hash']}/review", headers=support_session_headers,
        ).status_code == 403
    finally:
        support_client.close()
    assert approval_client.get(f"/api/sessions/{task['session_id']}/messages").status_code == 404
    missing_csrf = approval_client.post(
        f"/api/tasks/{task['task_id']}/plans/{plan['plan_hash']}/approval",
        headers={"Origin": ORIGIN, "Idempotency-Key": "missing-csrf"},
        json={"decision": "APPROVED"},
    )
    assert missing_csrf.status_code == 403 and missing_csrf.json()["code"] == "CSRF_REJECTED"

    approver_b = TestClient(approval_client.app, raise_server_exceptions=False)
    try:
        foreign_headers = _login(approver_b, "approver-b")
        assert approver_b.get(
            f"/api/tasks/{task['task_id']}/plans/{plan['plan_hash']}/review", headers=foreign_headers,
        ).status_code == 404
    finally:
        approver_b.close()
    anonymous = TestClient(approval_client.app, raise_server_exceptions=False)
    try:
        assert anonymous.get("/api/approvals/pending").status_code == 401
    finally:
        anonymous.close()


def test_apr02_approval_resume_run_outbox_and_command_commit_atomically(
    approval_client: TestClient, demo_db: Path, live_api: str, tmp_path: Path
) -> None:
    task = _prepare_waiting_task(approval_client, demo_db, live_api, tmp_path)
    plan_hash, task_id = str(task["plan"]["plan_hash"]), str(task["task_id"])
    approval_headers = _login(approval_client, "approver-a")
    before_outbox = _count(demo_db, "domain_outbox", "task_id = ?", (task_id,))
    with connect(demo_db) as connection:
        connection.execute(
            """CREATE TRIGGER m1_05_fail_resume_link BEFORE INSERT ON approval_resume_links
               BEGIN SELECT RAISE(ABORT, 'injected approval link failure'); END"""
        )
    failed = approval_client.post(
        f"/api/tasks/{task_id}/plans/{plan_hash}/approval",
        headers={**approval_headers, "Idempotency-Key": "atomic-approval"},
        json={"decision": "APPROVED"},
    )
    assert failed.status_code == 500
    assert _count(demo_db, "d3_approvals", "task_id = ?", (task_id,)) == 0
    assert _count(demo_db, "commands", "target_ref = ? AND command_kind = 'WEB_PLAN_APPROVAL'", (f"{task_id}:{plan_hash}",)) == 0
    assert _count(demo_db, "task_runs", "task_id = ? AND kind = 'APPROVAL_RESUME'", (task_id,)) == 0
    assert _count(demo_db, "approval_resume_links", "task_id = ?", (task_id,)) == 0
    assert _count(demo_db, "domain_outbox", "task_id = ?", (task_id,)) == before_outbox
    with connect(demo_db) as connection:
        connection.execute("DROP TRIGGER m1_05_fail_resume_link")

    accepted = approval_client.post(
        f"/api/tasks/{task_id}/plans/{plan_hash}/approval",
        headers={**approval_headers, "Idempotency-Key": "atomic-approval"},
        json={"decision": "APPROVED"},
    )
    replay = approval_client.post(
        f"/api/tasks/{task_id}/plans/{plan_hash}/approval",
        headers={**approval_headers, "Idempotency-Key": "atomic-approval"},
        json={"decision": "APPROVED"},
    )
    new_key_replay = approval_client.post(
        f"/api/tasks/{task_id}/plans/{plan_hash}/approval",
        headers={**approval_headers, "Idempotency-Key": "atomic-approval-same-decision-new-key"},
        json={"decision": "APPROVED"},
    )
    conflict = approval_client.post(
        f"/api/tasks/{task_id}/plans/{plan_hash}/approval",
        headers={**approval_headers, "Idempotency-Key": "atomic-approval"},
        json={"decision": "REJECTED"},
    )
    assert accepted.status_code == 202 and replay.status_code == 200 and new_key_replay.status_code == 200
    assert accepted.json()["approval_id"] == replay.json()["approval_id"]
    assert accepted.json()["resume_run_id"] == replay.json()["resume_run_id"]
    assert new_key_replay.json()["approval_id"] == accepted.json()["approval_id"]
    assert new_key_replay.json()["resume_run_id"] == accepted.json()["resume_run_id"]
    assert conflict.status_code == 409

    second_approver_password = "approver-a2-test-password"
    with connect(demo_db) as connection:
        connection.execute(
            "INSERT INTO trusted_operators (actor_id, tenant_id, role) VALUES ('approver-a2', 'tenant-a', 'APPROVER')"
        )
    second_approver_app = create_app(
        db_path=demo_db, checkpoint_db_path=task["checkpoint_path"], start_worker=False,
        credentials={**PASSWORDS, "approver-a2": second_approver_password}, expected_origin=ORIGIN,
    )
    second_approver_client = TestClient(second_approver_app, raise_server_exceptions=False)
    try:
        second_login = second_approver_client.post(
            "/api/auth/login", headers={"Origin": ORIGIN},
            json={"actor_id": "approver-a2", "password": second_approver_password},
        )
        assert second_login.status_code == 200
        second_headers = {"Origin": ORIGIN, "X-CSRF-Token": second_login.json()["csrf_token"],
                          "Idempotency-Key": "second-approver-key"}
        second_decision = second_approver_client.post(
            f"/api/tasks/{task_id}/plans/{plan_hash}/approval", headers=second_headers,
            json={"decision": "APPROVED"},
        )
        assert second_decision.status_code == 409
    finally:
        second_approver_client.close()
    resume_run_id = str(accepted.json()["resume_run_id"])
    identity = trusted_identity(demo_db, "support-a")
    link = get_approval_resume_link(demo_db, identity, resume_run_id)
    assert link["source_investigation_run_id"] == task["source_run_id"]
    assert link["source_checkpoint_thread_id"] == f"{task['binding']['thread_id']}::{task['source_run_id']}"
    assert link["resume_run_id"] == resume_run_id and link["plan_hash"] == plan_hash
    assert _count(demo_db, "approval_resume_links", "task_id = ?", (task_id,)) == 1
    assert _count(demo_db, "task_runs", "task_id = ? AND kind = 'APPROVAL_RESUME'", (task_id,)) == 1
    assert _count(demo_db, "d3_approvals", "task_id = ?", (task_id,)) == 1
    with connect(demo_db) as connection:
        source = connection.execute("SELECT status FROM task_runs WHERE run_id = ?", (task["source_run_id"],)).fetchone()
        events = connection.execute(
            "SELECT event_kind FROM domain_outbox WHERE task_id = ? ORDER BY rowid", (task_id,)
        ).fetchall()
    assert source["status"] == "WAITING_APPROVAL"
    assert "PLAN_APPROVED" in {str(row["event_kind"]) for row in events}


def test_apr05_stale_resource_plan_and_abort_before_approval_fail_closed(
    approval_client: TestClient, demo_db: Path, live_api: str, tmp_path: Path
) -> None:
    stale = _prepare_waiting_task(approval_client, demo_db, live_api, tmp_path, key="stale-resource-task")
    task_id, plan_hash = str(stale["task_id"]), str(stale["plan"]["plan_hash"])
    with connect(demo_db) as connection:
        connection.execute(
            "UPDATE integrations SET config_version = 8 WHERE tenant_id = 'tenant-a' AND integration_id = 'integration-a'"
        )
    approver_headers = _login(approval_client, "approver-a")
    review = approval_client.get(
        f"/api/tasks/{task_id}/plans/{plan_hash}/review", headers=approver_headers,
    )
    assert review.status_code == 200
    assert review.json()["current_state"]["version_compatible"] is False
    assert review.json()["current_state"]["version_block_reason"] == "RESOURCE_VERSION_OR_CREDENTIAL_PRECONDITION_FAILED"
    rejected = approval_client.post(
        f"/api/tasks/{task_id}/plans/{plan_hash}/approval",
        headers={**approver_headers, "Idempotency-Key": "stale-plan-approve"},
        json={"decision": "APPROVED"},
    )
    assert rejected.status_code == 409
    assert _count(demo_db, "d3_approvals", "task_id = ?", (task_id,)) == 0
    assert _count(demo_db, "task_runs", "task_id = ? AND kind = 'APPROVAL_RESUME'", (task_id,)) == 0

    aborted = _prepare_waiting_task(approval_client, demo_db, live_api, tmp_path, key="abort-before-approval-task")
    support_headers = aborted["support_headers"]
    abort_result = approval_client.post(
        f"/api/tasks/{aborted['task_id']}/abort",
        headers={**support_headers, "Idempotency-Key": "abort-before-approval"},
        json={"reason": "stop before business changes"},
    )
    assert abort_result.status_code == 202
    after_abort = _approve(approval_client, aborted, key="approval-after-abort")
    assert after_abort.status_code == 409
    assert _count(demo_db, "d3_approvals", "task_id = ?", (str(aborted["task_id"]),)) == 0
    assert _count(demo_db, "d3_action_intents", "task_id = ?", (str(aborted["task_id"]),)) == 0

    corrected = _prepare_waiting_task(
        approval_client, demo_db, live_api, tmp_path, key="critical-correction-before-approval-task",
    )
    correction = approval_client.post(
        f"/api/sessions/{corrected['session_id']}/messages",
        headers={**corrected["support_headers"], "Idempotency-Key": "critical-correction-before-approval"},
        json={"task_id": corrected["task_id"], "input_kind": "CORRECT_TASK_INPUT", "body": "更正：请重新核实同一主体当前配置。"},
    )
    assert correction.status_code == 202
    after_correction = _approve(approval_client, corrected, key="approval-after-critical-correction")
    assert after_correction.status_code == 409
    assert _count(demo_db, "d3_approvals", "task_id = ?", (str(corrected["task_id"]),)) == 0
    assert _count(demo_db, "task_runs", "task_id = ? AND kind = 'APPROVAL_RESUME'", (str(corrected["task_id"]),)) == 0


def test_apr05_plan_cancel_blocks_queued_resume_before_checkpoint_access(
    approval_client: TestClient, demo_db: Path, live_api: str, tmp_path: Path
) -> None:
    task = _prepare_waiting_task(approval_client, demo_db, live_api, tmp_path, key="cancel-after-approval-task")
    accepted = _approve(approval_client, task, key="cancel-after-approval")
    assert accepted.status_code == 202
    canceled = cancel_plan(
        demo_db, str(task["task_id"]), str(task["plan"]["plan_hash"]), "support-a", "superseded before execution",
    )
    assert canceled["eligibility"] == "CANCELLED"
    identity = trusted_identity(demo_db, "support-a")
    with pytest.raises(TaskControlError, match="TASK_RUN_NOT_QUEUED"):
        claim_task_run(demo_db, identity, str(accepted.json()["resume_run_id"]))
    assert _count(demo_db, "d3_action_intents", "task_id = ?", (str(task["task_id"]),)) == 0


def test_apr05_abort_after_approval_blocks_resume_before_checkpoint_access(
    approval_client: TestClient, demo_db: Path, live_api: str, tmp_path: Path
) -> None:
    task = _prepare_waiting_task(
        approval_client, demo_db, live_api, tmp_path, key="abort-after-approval-task",
    )
    accepted = _approve(approval_client, task, key="approve-before-abort")
    assert accepted.status_code == 202
    resume_run_id = str(accepted.json()["resume_run_id"])
    support_headers = _login(approval_client, "support-a")
    aborted = approval_client.post(
        f"/api/tasks/{task['task_id']}/abort",
        headers={**support_headers, "Idempotency-Key": "abort-approved-before-claim"},
        json={"reason": "stop after approval and before repair"},
    )
    assert aborted.status_code == 202
    with connect(demo_db) as connection:
        resume = connection.execute(
            "SELECT status, blocked_reason FROM task_runs WHERE run_id = ?", (resume_run_id,)
        ).fetchone()
    assert tuple(resume) == ("BLOCKED", "TASK_ABORTED")
    identity = trusted_identity(demo_db, "support-a")
    with pytest.raises(TaskControlError, match="TASK_RUN_NOT_QUEUED"):
        claim_task_run(demo_db, identity, resume_run_id)
    assert _count(demo_db, "d3_action_intents", "task_id = ?", (str(task["task_id"]),)) == 0
    assert _count(demo_db, "d3_action_ledgers", "task_id = ?", (str(task["task_id"]),)) == 0


def test_apr04_rejection_resumes_original_graph_without_action_intents(
    approval_client: TestClient, demo_db: Path, live_api: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(MODEL_API_KEY, "m1-05-test-placeholder")
    monkeypatch.setenv(MODEL_NAME, "m1-05-provider-not-called-on-resume")
    task = _prepare_waiting_task(approval_client, demo_db, live_api, tmp_path, key="rejected-task")
    accepted = _approve(approval_client, task, decision="REJECTED", key="reject-plan")
    assert accepted.status_code == 202
    from opspilot.investigator import run_investigation

    resumed = asyncio.run(run_investigation(
        str(task["task_id"]), "support-a", db_path=demo_db,
        checkpoint_db_path=task["checkpoint_path"], resume=True, d3_mode=True,
        executor_id="executor-a", run_id=str(accepted.json()["resume_run_id"]),
    ))
    assert resumed["graph_state"]["stage"] == "complete"
    assert resumed["graph_state"]["approval_decision"] == "REJECTED"
    action_state = get_task_action_state(demo_db, str(task["task_id"]), "support-a")
    assert action_state["action_intents"] == []
    assert action_state["action_ledgers"] == []
    assert action_state["delivery_records"] == []
    assert action_state["ticket_entries"] == []
    assert _count(demo_db, "d3_local_reports", "task_id = ? AND outcome = 'REJECTED'", (str(task["task_id"]),)) == 1
    assert get_integration_info(demo_db, "tenant-a", "integration-a")["config_version"] == 7


def test_apr03_new_run_resumes_original_graph_and_completes_domain_closed_loop(
    approval_client: TestClient, demo_db: Path, live_api: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(MODEL_API_KEY, "m1-05-test-placeholder")
    monkeypatch.setenv(MODEL_NAME, "m1-05-provider-not-called-on-resume")
    task = _prepare_waiting_task(approval_client, demo_db, live_api, tmp_path, key="approved-task")
    accepted = _approve(approval_client, task, decision="APPROVED", key="approve-plan")
    assert accepted.status_code == 202
    resume_run_id = str(accepted.json()["resume_run_id"])
    from opspilot.investigator import run_investigation

    completed = asyncio.run(run_investigation(
        str(task["task_id"]), "support-a", db_path=demo_db,
        checkpoint_db_path=task["checkpoint_path"], resume=True, d3_mode=True,
        executor_id="executor-a", run_id=resume_run_id,
    ))
    assert completed["graph_state"]["stage"] == "complete"
    assert completed["action_state"]["task_binding"]["status"] == "COMPLETED"
    assert _count(demo_db, "d3_action_ledgers", "task_id = ? AND action_kind = 'REPAIR' AND status = 'COMMITTED'", (str(task["task_id"]),)) == 1
    assert _count(demo_db, "d3_action_ledgers", "task_id = ? AND action_kind = 'DELIVER' AND status = 'COMMITTED'", (str(task["task_id"]),)) == 1
    assert _count(demo_db, "d3_report_artifacts", "task_id = ?", (str(task["task_id"]),)) == 1
    assert _count(demo_db, "d3_delivery_records", "task_id = ?", (str(task["task_id"]),)) == 1
    assert _count(demo_db, "d3_ticket_resolution_entries", "task_id = ?", (str(task["task_id"]),)) == 1
    assert get_integration_info(demo_db, "tenant-a", "integration-a")["config_version"] == 8
    assert get_integration_info(demo_db, "tenant-a", "integration-a")["credential_ref"] == "cred-v2"
    with connect(demo_db) as connection:
        source = connection.execute("SELECT status FROM task_runs WHERE run_id = ?", (task["source_run_id"],)).fetchone()
        resume = connection.execute("SELECT status, kind FROM task_runs WHERE run_id = ?", (resume_run_id,)).fetchone()
    assert source["status"] == "WAITING_APPROVAL"
    assert tuple(resume) == ("SUCCEEDED", "APPROVAL_RESUME")
