from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
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


@pytest.mark.parametrize(
    ("window", "expected_task_status"),
    [
        ("repair", "VERIFYING"),
        ("verification", "DELIVERY_PENDING"),
        ("report", "DELIVERY_PENDING"),
        ("deliver", "COMPLETED"),
    ],
)
def test_hf04_hf05_hf06_approval_resume_recovers_after_domain_commit(
    approval_client: TestClient,
    demo_db: Path,
    live_api: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    window: str,
    expected_task_status: str,
) -> None:
    import opspilot.domain.d3 as d3
    from opspilot.investigator import run_investigation

    monkeypatch.setenv(MODEL_API_KEY, "m1-hf-test-placeholder")
    monkeypatch.setenv(MODEL_NAME, "m1-hf-no-model-call-on-resume")
    task = _prepare_waiting_task(
        approval_client, demo_db, live_api, tmp_path, key=f"hf-resume-{window}",
    )
    accepted = _approve(approval_client, task, key=f"hf-resume-approve-{window}")
    assert accepted.status_code == 202
    resume_run_id = str(accepted.json()["resume_run_id"])
    names = {
        "repair": "execute_repair",
        "verification": "verify_repair_online",
        "deliver": "execute_deliver",
    }
    function_name = names.get(window)
    if window == "report":
        original = d3.get_or_create_report

        def interrupted(*args, **kwargs):
            original(*args, **kwargs)
            raise RuntimeError("HF injected after frozen report commit")

        function_name = "get_or_create_report"
    else:
        assert function_name is not None
        original = getattr(d3, function_name)

        def interrupted(*args, **kwargs):
            original(*args, **kwargs)
            raise RuntimeError(f"HF injected after {window} commit")

    with monkeypatch.context() as injected:
        injected.setattr(d3, str(function_name), interrupted)
        with pytest.raises(ExceptionGroup) as failure:
            asyncio.run(run_investigation(
                str(task["task_id"]), "support-a", db_path=demo_db,
                checkpoint_db_path=task["checkpoint_path"], resume=True, d3_mode=True,
                executor_id="executor-a", run_id=resume_run_id,
            ))
        assert "HF injected after" in repr(failure.value)

    identity = trusted_identity(demo_db, "support-a")
    link = get_approval_resume_link(demo_db, identity, resume_run_id)
    assert link["source_checkpoint_thread_id"] == f"{task['binding']['thread_id']}::{task['source_run_id']}"
    assert link["plan_hash"] == task["plan"]["plan_hash"]
    with connect(demo_db) as connection:
        task_status = connection.execute(
            "SELECT status FROM task_bindings WHERE task_id = ?", (task["task_id"],)
        ).fetchone()[0]
        run_status = connection.execute(
            "SELECT status FROM task_runs WHERE run_id = ?", (resume_run_id,)
        ).fetchone()[0]
    with connect(task["checkpoint_path"]) as connection:
        checkpoint = connection.execute(
            "SELECT COUNT(*) FROM checkpoints WHERE thread_id = ?",
            (link["source_checkpoint_thread_id"],),
        ).fetchone()[0]
    assert task_status == expected_task_status
    assert run_status == "INTERRUPTED_RECOVERABLE"
    assert int(checkpoint) > 0

    resumed = asyncio.run(run_investigation(
        str(task["task_id"]), "support-a", db_path=demo_db,
        checkpoint_db_path=task["checkpoint_path"], resume=True, d3_mode=True,
        executor_id="executor-a", run_id=resume_run_id,
    ))
    assert resumed["graph_state"]["stage"] == "complete"
    action_state = get_task_action_state(demo_db, str(task["task_id"]), "support-a")
    assert sum(row["action_kind"] == "REPAIR" and row["status"] == "COMMITTED" for row in action_state["action_ledgers"]) == 1
    assert sum(row["action_kind"] == "DELIVER" and row["status"] == "COMMITTED" for row in action_state["action_ledgers"]) == 1
    assert len(action_state["verification_receipts"]) == 1
    assert len(action_state["report_artifacts"]) == 1
    assert len(action_state["delivery_records"]) == len(action_state["ticket_entries"]) == 1
    assert get_integration_info(demo_db, "tenant-a", "integration-a")["config_version"] == 8
    with connect(demo_db) as connection:
        final_run = connection.execute(
            "SELECT status, kind FROM task_runs WHERE run_id = ?", (resume_run_id,)
        ).fetchone()
    assert tuple(final_run) == ("SUCCEEDED", "APPROVAL_RESUME")


@pytest.mark.parametrize(
    ("window", "failpoint"),
    [
        ("repair", "repair_after_commit_before_response"),
        ("deliver", "deliver_after_commit_before_response"),
    ],
)
def test_hf04_hf06_approval_resume_recovers_after_real_process_exit(
    approval_client: TestClient,
    demo_db: Path,
    live_api: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    window: str,
    failpoint: str,
) -> None:
    monkeypatch.setenv(MODEL_API_KEY, "m1-hf-child-test-placeholder")
    monkeypatch.setenv(MODEL_NAME, "m1-hf-child-no-model-call")
    task = _prepare_waiting_task(
        approval_client, demo_db, live_api, tmp_path, key=f"hf-process-{window}",
    )
    accepted = _approve(approval_client, task, key=f"hf-process-approve-{window}")
    assert accepted.status_code == 202
    resume_run_id = str(accepted.json()["resume_run_id"])
    worker_script = Path(__file__).with_name("m1_hf_approval_resume_worker.py")
    child_env = os.environ.copy()
    child_env[MODEL_API_KEY] = "m1-hf-child-test-placeholder"
    child_env[MODEL_NAME] = "m1-hf-child-no-model-call"
    crash = subprocess.run(
        [
            sys.executable, str(worker_script), "crash", str(demo_db), str(task["checkpoint_path"]),
            str(task["task_id"]), resume_run_id, failpoint,
        ],
        cwd=Path(__file__).resolve().parents[1], env=child_env, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=90,
    )
    print(f"HF_CHILD_CRASH_STDOUT[{window}]\n{crash.stdout}", flush=True)
    print(f"HF_CHILD_CRASH_STDERR[{window}]\n{crash.stderr}", flush=True)
    assert crash.returncode == 87
    assert '"event": "hf_approval_resume_crash_after_commit"' in crash.stdout
    assert f'"failpoint": "{failpoint}"' in crash.stdout
    link = get_approval_resume_link(demo_db, trusted_identity(demo_db, "support-a"), resume_run_id)
    assert link["source_checkpoint_thread_id"] == f"{task['binding']['thread_id']}::{task['source_run_id']}"
    with connect(demo_db) as connection:
        crashed_run = connection.execute(
            "SELECT status, kind FROM task_runs WHERE run_id = ?", (resume_run_id,)
        ).fetchone()
    assert tuple(crashed_run) == ("RUNNING", "APPROVAL_RESUME")
    after_crash = get_task_action_state(demo_db, str(task["task_id"]), "support-a")
    assert sum(row["action_kind"] == "REPAIR" for row in after_crash["action_ledgers"]) == 1
    assert get_integration_info(demo_db, "tenant-a", "integration-a")["config_version"] == 8
    if window == "repair":
        assert after_crash["action_ledgers"][-1]["action_kind"] == "REPAIR"
        assert after_crash["ticket_entries"] == []
    else:
        assert sum(row["action_kind"] == "DELIVER" for row in after_crash["action_ledgers"]) == 1
        assert len(after_crash["ticket_entries"]) == len(after_crash["delivery_records"]) == 1

    recovery = subprocess.run(
        [
            sys.executable, str(worker_script), "recover", str(demo_db), str(task["checkpoint_path"]),
            str(task["task_id"]), resume_run_id, "-",
        ],
        cwd=Path(__file__).resolve().parents[1], env=child_env, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=90,
    )
    print(f"HF_CHILD_RECOVERY_STDOUT[{window}]\n{recovery.stdout}", flush=True)
    print(f"HF_CHILD_RECOVERY_STDERR[{window}]\n{recovery.stderr}", flush=True)
    assert recovery.returncode == 0
    assert '"event": "hf_approval_resume_recovered"' in recovery.stdout
    final_state = get_task_action_state(demo_db, str(task["task_id"]), "support-a")
    assert sum(row["action_kind"] == "REPAIR" and row["status"] == "COMMITTED" for row in final_state["action_ledgers"]) == 1
    assert sum(row["action_kind"] == "DELIVER" and row["status"] == "COMMITTED" for row in final_state["action_ledgers"]) == 1
    assert len(final_state["verification_receipts"]) == len(final_state["report_artifacts"]) == 1
    assert len(final_state["delivery_records"]) == len(final_state["ticket_entries"]) == 1
    with connect(demo_db) as connection:
        final_run = connection.execute(
            "SELECT status, kind FROM task_runs WHERE run_id = ?", (resume_run_id,)
        ).fetchone()
    assert tuple(final_run) == ("SUCCEEDED", "APPROVAL_RESUME")


@pytest.mark.parametrize(
    ("change", "expected_error"),
    [
        ("abort", "TASK_CONTROL_STALE"),
        ("correction", "TASK_CONTROL_STALE"),
        ("cancel", "TASK_CONTROL_STALE"),
        ("cross_tenant", "TASK_RUN_SCOPE_DENIED"),
    ],
)
def test_hf09_approval_resume_authority_changes_fail_closed(
    approval_client: TestClient,
    demo_db: Path,
    live_api: str,
    tmp_path: Path,
    change: str,
    expected_error: str,
) -> None:
    task = _prepare_waiting_task(
        approval_client, demo_db, live_api, tmp_path, key=f"hf-negative-{change}",
    )
    accepted = _approve(approval_client, task, key=f"hf-negative-approve-{change}")
    assert accepted.status_code == 202
    run_id = str(accepted.json()["resume_run_id"])
    if change == "abort":
        support_headers = _login(approval_client, "support-a")
        response = approval_client.post(
            f"/api/tasks/{task['task_id']}/abort",
            headers={**support_headers, "Idempotency-Key": "hf-negative-abort-command"},
            json={"reason": "abort before resume"},
        )
        assert response.status_code == 202, response.text
    elif change == "correction":
        support_headers = _login(approval_client, "support-a")
        response = approval_client.post(
            f"/api/sessions/{task['session_id']}/messages",
            headers={**support_headers, "Idempotency-Key": "hf-negative-correction-command"},
            json={"task_id": task["task_id"], "input_kind": "CORRECT_TASK_INPUT",
                  "body": "Correction after approval: recheck current facts."},
        )
        assert response.status_code == 202, response.text
    elif change == "cancel":
        cancelled = cancel_plan(
            demo_db, str(task["task_id"]), str(task["plan"]["plan_hash"]),
            "support-a", "cancel before approval resume",
        )
        assert cancelled["eligibility"] == "CANCELLED"
    else:
        with pytest.raises(TaskControlError, match=expected_error):
            get_approval_resume_link(demo_db, trusted_identity(demo_db, "support-b"), run_id)
        assert _count(demo_db, "d3_action_intents", "task_id = ?", (str(task["task_id"]),)) == 0
        assert get_integration_info(demo_db, "tenant-a", "integration-a")["config_version"] == 7
        return

    with pytest.raises(TaskControlError, match=expected_error):
        get_approval_resume_link(demo_db, trusted_identity(demo_db, "support-a"), run_id)
    assert _count(demo_db, "d3_action_intents", "task_id = ?", (str(task["task_id"]),)) == 0
    assert _count(demo_db, "d3_action_ledgers", "task_id = ?", (str(task["task_id"]),)) == 0
    assert get_integration_info(demo_db, "tenant-a", "integration-a")["config_version"] == 7


@pytest.mark.parametrize("missing_receipt", ["repair_ledger", "delivery_record"])
def test_hf09_missing_action_receipt_fails_closed(
    approval_client: TestClient,
    demo_db: Path,
    live_api: str,
    tmp_path: Path,
    missing_receipt: str,
) -> None:
    from opspilot.domain.d3 import (
        execute_deliver,
        execute_repair,
        get_or_create_action_intent,
        get_or_create_report,
        verify_repair_online,
    )

    task = _prepare_waiting_task(
        approval_client, demo_db, live_api, tmp_path, key=f"hf-missing-{missing_receipt}",
    )
    accepted = _approve(approval_client, task, key=f"hf-missing-approve-{missing_receipt}")
    assert accepted.status_code == 202
    plan_hash = str(task["plan"]["plan_hash"])
    task_id = str(task["task_id"])
    repair = get_or_create_action_intent(demo_db, task_id, plan_hash, "REPAIR", "executor-a")
    execute_repair(demo_db, str(repair["action_id"]), "executor-a", "hf-missing-repair")
    if missing_receipt == "repair_ledger":
        with connect(demo_db) as connection:
            connection.execute("DELETE FROM d3_action_ledgers WHERE action_id = ?", (repair["action_id"],))
    else:
        verified = verify_repair_online(
            demo_db, task_id, plan_hash, str(repair["action_id"]), "executor-a", live_api,
        )
        assert verified["recovery_verified"] is True
        get_or_create_report(
            demo_db, task_id, plan_hash, str(repair["action_id"]), "executor-a",
        )
        deliver = get_or_create_action_intent(demo_db, task_id, plan_hash, "DELIVER", "executor-a")
        execute_deliver(demo_db, str(deliver["action_id"]), "executor-a", "hf-missing-deliver")
        with connect(demo_db) as connection:
            connection.execute(
                "DELETE FROM d3_delivery_records WHERE task_id = ? AND plan_hash = ?",
                (task_id, plan_hash),
            )

    with pytest.raises(TaskControlError, match="APPROVAL_RESUME_LINK_INVALID"):
        get_approval_resume_link(
            demo_db, trusted_identity(demo_db, "support-a"), str(accepted.json()["resume_run_id"]),
        )
    if missing_receipt == "repair_ledger":
        assert _count(demo_db, "d3_action_ledgers", "task_id = ?", (task_id,)) == 0
        assert _count(demo_db, "d3_ticket_resolution_entries", "task_id = ?", (task_id,)) == 0
    else:
        assert _count(demo_db, "d3_action_ledgers", "task_id = ?", (task_id,)) == 2
        assert _count(demo_db, "d3_delivery_records", "task_id = ?", (task_id,)) == 0
        assert _count(demo_db, "d3_ticket_resolution_entries", "task_id = ?", (task_id,)) == 1


def test_hf09_approval_resume_without_checkpoint_does_not_cold_start(
    approval_client: TestClient,
    demo_db: Path,
    live_api: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from opspilot.investigator import run_investigation

    monkeypatch.setenv(MODEL_API_KEY, "m1-hf-no-checkpoint-placeholder")
    monkeypatch.setenv(MODEL_NAME, "m1-hf-no-checkpoint-no-model-call")
    task = _prepare_waiting_task(
        approval_client, demo_db, live_api, tmp_path, key="hf-no-checkpoint",
    )
    accepted = _approve(approval_client, task, key="hf-no-checkpoint-approve")
    assert accepted.status_code == 202
    empty_checkpoint = tmp_path / "approval-resume-empty.sqlite3"
    with pytest.raises(ExceptionGroup) as failure:
        asyncio.run(run_investigation(
            str(task["task_id"]), "support-a", db_path=demo_db,
            checkpoint_db_path=empty_checkpoint, resume=True, d3_mode=True,
            executor_id="executor-a", run_id=str(accepted.json()["resume_run_id"]),
        ))
    assert "No persisted graph state exists" in repr(failure.value)
    assert get_integration_info(demo_db, "tenant-a", "integration-a")["config_version"] == 7
    assert _count(demo_db, "d3_action_intents", "task_id = ?", (str(task["task_id"]),)) == 0
    assert _count(demo_db, "d3_action_ledgers", "task_id = ?", (str(task["task_id"]),)) == 0
    with connect(demo_db) as connection:
        run = connection.execute(
            "SELECT status, blocked_reason FROM task_runs WHERE run_id = ?",
            (str(accepted.json()["resume_run_id"]),),
        ).fetchone()
    assert tuple(run) == ("INTERRUPTED_RECOVERABLE", "RUN_INTERRUPTED_BEFORE_RESULT")


@pytest.mark.parametrize(
    ("case", "failpoint"),
    [("hf07_claim", "after_claim"), ("hf08_correction", "after_correction_applied")],
)
def test_hf07_hf08_initial_investigation_recovers_before_first_checkpoint_in_new_process(
    approval_client: TestClient,
    demo_db: Path,
    tmp_path: Path,
    case: str,
    failpoint: str,
) -> None:
    support_headers = _login(approval_client, "support-a")
    session_response = approval_client.post("/api/sessions", headers=support_headers)
    assert session_response.status_code == 201, session_response.text
    session_id = str(session_response.json()["session_id"])
    created_response = approval_client.post(
        f"/api/sessions/{session_id}/tasks",
        headers={**support_headers, "Idempotency-Key": f"{case}-create"},
        json={"initial_message": "订单 API 当前返回 401，请调查绑定路由的真实原因。"},
    )
    assert created_response.status_code == 202, created_response.text
    created = created_response.json()
    task_id = str(created["task_id"])
    initial_run_id = str(created["run_id"])
    run_id = initial_run_id
    correction_body = "关键纠错：最近一次请求使用的 credential_ref 是 cred-v1，请核对但不要把此陈述视为证据。"
    if case == "hf08_correction":
        correction_response = approval_client.post(
            f"/api/sessions/{session_id}/messages",
            headers={**support_headers, "Idempotency-Key": f"{case}-correction"},
            json={"task_id": task_id, "input_kind": "CORRECT_TASK_INPUT", "body": correction_body},
        )
        assert correction_response.status_code == 202, correction_response.text
        run_id = str(correction_response.json()["run_id"])

    checkpoint_path = tmp_path / f"{case}-checkpoint.sqlite3"
    assert not checkpoint_path.exists()
    worker_script = Path(__file__).with_name("m1_hf_precheckpoint_worker.py")
    child_env = os.environ.copy()
    child_env[MODEL_API_KEY] = "m1-hf-deterministic-placeholder"
    child_env[MODEL_NAME] = "m1-hf-deterministic-no-provider-call"
    crash = subprocess.run(
        [
            sys.executable, str(worker_script), "crash", str(demo_db), str(checkpoint_path),
            task_id, run_id, failpoint,
        ],
        cwd=Path(__file__).resolve().parents[1], env=child_env, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30,
    )
    print(f"HF_PRECHECKPOINT_CRASH_STDOUT[{case}]\n{crash.stdout}", flush=True)
    print(f"HF_PRECHECKPOINT_CRASH_STDERR[{case}]\n{crash.stderr}", flush=True)
    assert crash.returncode == 87
    assert '"event": "hf_precheckpoint_claim_committed"' in crash.stdout
    if case == "hf08_correction":
        assert '"event": "hf_precheckpoint_correction_applied"' in crash.stdout
        with connect(demo_db) as connection:
            applied = connection.execute(
                "SELECT application_state, applied_run_id, body_digest, sequence FROM messages WHERE task_id = ? AND input_kind = 'CORRECT_TASK_INPUT'",
                (task_id,),
            ).fetchone()
            run_after_crash = connection.execute(
                "SELECT expected_control_revision, consumed_message_seq, applied_critical_message_seq FROM task_runs WHERE run_id = ?",
                (run_id,),
            ).fetchone()
            control_after_crash = connection.execute(
                "SELECT control_revision, pending_critical_message_seq, applied_critical_message_seq FROM task_controls WHERE task_id = ?",
                (task_id,),
            ).fetchone()
            input_row = connection.execute(
                "SELECT message_id, run_id, input_digest, provenance FROM task_run_inputs WHERE task_id = ?",
                (task_id,),
            ).fetchone()
        assert applied["application_state"] == "APPLIED_TO_RUN"
        assert applied["applied_run_id"] == run_id
        assert run_after_crash["expected_control_revision"] == control_after_crash["control_revision"]
        assert run_after_crash["applied_critical_message_seq"] == control_after_crash["applied_critical_message_seq"] == applied["sequence"]
        assert control_after_crash["pending_critical_message_seq"] is None
        assert input_row["message_id"] and input_row["run_id"] == run_id
        assert input_row["input_digest"] == applied["body_digest"]
        assert input_row["provenance"] == "USER_INPUT_UNTRUSTED"
    else:
        with connect(demo_db) as connection:
            run_after_crash = connection.execute(
                "SELECT status, expected_control_revision FROM task_runs WHERE run_id = ?", (run_id,)
            ).fetchone()
        assert tuple(run_after_crash) == ("RUNNING", 0)
    with connect(demo_db) as connection:
        attempts_before = connection.execute(
            "SELECT attempt_id, kind, status FROM d2_attempts WHERE task_id = ? ORDER BY reserved_at, attempt_id",
            (task_id,),
        ).fetchall()
        budget_before = connection.execute(
            "SELECT active_elapsed_ms, deadline_ms FROM task_execution_budgets WHERE task_id = ?",
            (task_id,),
        ).fetchone()
    assert len(attempts_before) == 1
    assert (attempts_before[0]["kind"], attempts_before[0]["status"]) == ("MCP", "RESERVED")
    assert not checkpoint_path.exists()

    prompt_capture = tmp_path / f"{case}-prompt.jsonl"
    recovery = subprocess.run(
        [
            sys.executable, str(worker_script), "recover", str(demo_db), str(checkpoint_path),
            task_id, run_id, str(prompt_capture),
        ],
        cwd=Path(__file__).resolve().parents[1], env=child_env, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60,
    )
    print(f"HF_PRECHECKPOINT_RECOVERY_STDOUT[{case}]\n{recovery.stdout}", flush=True)
    print(f"HF_PRECHECKPOINT_RECOVERY_STDERR[{case}]\n{recovery.stderr}", flush=True)
    if prompt_capture.exists():
        print(f"HF_PRECHECKPOINT_PROMPT_CAPTURE[{case}]\n{prompt_capture.read_text(encoding='utf-8')}", flush=True)
    assert recovery.returncode == 0
    assert '"event": "hf_precheckpoint_new_worker_recovered_run"' in recovery.stdout
    assert '"event": "hf_precheckpoint_recovery_finished"' in recovery.stdout
    assert f'"checkpoint_thread_id": "{created["thread_id"]}::{run_id}"' in recovery.stdout
    assert '"checkpoint_id": "' in recovery.stdout
    assert prompt_capture.exists()
    prompt_payload = json.loads(prompt_capture.read_text(encoding="utf-8").splitlines()[0])
    human_prompt = "\n".join(str(item["content"]) for item in prompt_payload if item["type"] == "human")
    assert "订单 API 当前返回 401" in human_prompt
    assert "USER_INPUT_UNTRUSTED" in human_prompt
    if case == "hf08_correction":
        assert correction_body in human_prompt
        assert "关键纠错" in human_prompt

    with connect(demo_db) as connection:
        recovered_run = connection.execute(
            "SELECT status, expected_control_revision, consumed_message_seq, applied_critical_message_seq FROM task_runs WHERE run_id = ?",
            (run_id,),
        ).fetchone()
        control = connection.execute(
            "SELECT control_revision, pending_critical_message_seq, applied_critical_message_seq FROM task_controls WHERE task_id = ?",
            (task_id,),
        ).fetchone()
        retry = connection.execute(
            "SELECT retry_count, max_retries, last_error_code FROM worker_retry_state WHERE run_id = ?",
            (run_id,),
        ).fetchone()
        attempts_after = connection.execute(
            "SELECT kind, status, COUNT(*) AS count FROM d2_attempts WHERE task_id = ? GROUP BY kind, status",
            (task_id,),
        ).fetchall()
        budget_after = connection.execute(
            "SELECT active_elapsed_ms, deadline_ms FROM task_execution_budgets WHERE task_id = ?",
            (task_id,),
        ).fetchone()
        provenance = connection.execute(
            "SELECT selected_input_messages_json, task_run_control_json, model_status FROM d5_context_provenance WHERE task_id = ? ORDER BY built_at DESC LIMIT 1",
            (task_id,),
        ).fetchone()
        plans = int(connection.execute("SELECT COUNT(*) FROM d3_plans WHERE task_id = ?", (task_id,)).fetchone()[0])
        intents = int(connection.execute("SELECT COUNT(*) FROM d3_action_intents WHERE task_id = ?", (task_id,)).fetchone()[0])
        ledgers = int(connection.execute("SELECT COUNT(*) FROM d3_action_ledgers WHERE task_id = ?", (task_id,)).fetchone()[0])
    assert recovered_run["status"] == "INTERRUPTED_RECOVERABLE"
    assert recovered_run["expected_control_revision"] == control["control_revision"]
    assert recovered_run["applied_critical_message_seq"] == control["applied_critical_message_seq"]
    assert control["pending_critical_message_seq"] is None
    assert retry is not None and int(retry["retry_count"]) >= 1 and int(retry["retry_count"]) <= int(retry["max_retries"])
    attempt_summary = {(str(row["kind"]), str(row["status"])): int(row["count"]) for row in attempts_after}
    assert attempt_summary == {("MCP", "RESERVED"): 1, ("MODEL", "OK"): 1}
    assert int(budget_after["deadline_ms"]) == int(budget_before["deadline_ms"])
    assert int(budget_after["active_elapsed_ms"]) >= int(budget_before["active_elapsed_ms"])
    assert provenance is not None and provenance["model_status"] == "OK"
    input_refs = json.loads(provenance["selected_input_messages_json"])
    run_control = json.loads(provenance["task_run_control_json"])
    if case == "hf08_correction":
        assert any(
            item["kind"] == "CRITICAL_CORRECTION"
            and item["message_id"] == correction_response.json()["message_id"]
            and item["provenance"] == "USER_INPUT_UNTRUSTED"
            and item["digest"] == applied["body_digest"]
            for item in input_refs
        )
        assert run_control["applied_critical_message_seq"] == applied["sequence"]
        assert run_control["current_control_revision"] == control["control_revision"]
        assert run_control["expected_control_revision"] == control["control_revision"]
        assert _count(demo_db, "task_run_inputs", "task_id = ?", (task_id,)) == 1
        assert _count(demo_db, "messages", "task_id = ? AND input_kind = 'CORRECT_TASK_INPUT' AND application_state = 'APPLIED_TO_RUN'", (task_id,)) == 1
    else:
        assert any(item["kind"] == "INITIAL_SYMPTOM" for item in input_refs)
        assert run_control["current_control_revision"] == 0
    assert (plans, intents, ledgers) == (0, 0, 0)


@pytest.mark.parametrize(
    ("activity", "expected_error"),
    [
        ("plan", "INITIAL_CHECKPOINT_RECOVERY_DOMAIN_ACTIVITY"),
        ("action_intent", "ACTION_OUTCOME_UNKNOWN"),
    ],
)
def test_hf09_missing_checkpoint_with_existing_plan_or_action_fails_closed(
    approval_client: TestClient,
    demo_db: Path,
    live_api: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    activity: str,
    expected_error: str,
) -> None:
    from opspilot.domain.d2 import (
        get_auth_policy_fact,
        get_integration_config_fact,
        get_principal_status_fact,
        probe_endpoint_fact,
        record_tool_observation,
    )
    from opspilot.domain.d3 import create_plan_from_gate
    from opspilot.domain.task_control import claim_task_run
    from opspilot.investigator import run_investigation

    monkeypatch.setenv(MODEL_API_KEY, "m1-hf-no-provider-placeholder")
    monkeypatch.setenv(MODEL_NAME, "m1-hf-existing-plan-cold-start-rejected")
    support_headers = _login(approval_client, "support-a")
    session_response = approval_client.post("/api/sessions", headers=support_headers)
    assert session_response.status_code == 201, session_response.text
    session_id = str(session_response.json()["session_id"])
    created_response = approval_client.post(
        f"/api/sessions/{session_id}/tasks",
        headers={**support_headers, "Idempotency-Key": "hf09-plan-create"},
        json={"initial_message": "订单 API 返回 401，请核对当前授权事实。"},
    )
    assert created_response.status_code == 202, created_response.text
    created = created_response.json()
    task_id, run_id = str(created["task_id"]), str(created["run_id"])
    identity = trusted_identity(demo_db, "support-a")
    claim_task_run(demo_db, identity, run_id)
    from opspilot.domain.d2 import get_task_binding

    binding = get_task_binding(demo_db, task_id)
    facts = [
        ("get_integration_config", get_integration_config_fact(demo_db, task_id, "integration-a")),
        ("get_principal_status", get_principal_status_fact(demo_db, task_id, "principal-a")),
        ("get_auth_policy", get_auth_policy_fact(demo_db, task_id, "orders-demo")),
        ("probe_endpoint", probe_endpoint_fact(demo_db, task_id, "orders-demo", "integration-a", live_api)),
    ]
    evidence_ids = []
    for index, (tool_name, fact) in enumerate(facts, start=1):
        observation = record_tool_observation(
            demo_db, task_id=task_id, call_id=f"hf09-plan-call-{index}", attempt_id=None,
            tool_call_id=f"hf09-plan-tool-{index}", tool_name=tool_name,
            arguments={"case": "missing_checkpoint_with_plan"}, status="OK", result=fact,
        )
        evidence_ids.append(str(observation["evidence_id"]))
    gate = evaluate_evidence_gate(demo_db, task_id, evidence_ids)
    assert gate["decision"] == "READY"
    plan = create_plan_from_gate(demo_db, task_id, "support-a", gate, run_id=run_id)
    if activity == "action_intent":
        with connect(demo_db) as connection:
            connection.execute(
                """INSERT INTO d3_action_intents
                   (action_id, tenant_id, task_id, plan_hash, action_kind, idempotency_key,
                    approval_id, canonical_request_json, request_digest, created_at)
                   VALUES ('hf09-orphan-repair-intent', 'tenant-a', ?, ?, 'REPAIR',
                           'hf09-orphan-repair-key', 'approval-missing', '{}',
                           'hf09-orphan-repair-digest', '2026-10-18T00:00:00Z')""",
                (task_id, str(plan["plan_hash"])),
            )
    finish_task_run(
        demo_db, identity, run_id, "INTERRUPTED_RECOVERABLE",
        blocked_reason="TEST_MISSING_GRAPH_CHECKPOINT",
    )
    # A new Worker restart projects its recovered Run state to the TaskBinding.
    with connect(demo_db) as connection:
        connection.execute(
            "UPDATE task_bindings SET status = 'INTERRUPTED_RECOVERABLE' WHERE task_id = ?",
            (task_id,),
        )

    checkpoint_path = tmp_path / "hf09-plan-without-checkpoint.sqlite3"
    with pytest.raises(ExceptionGroup) as failure:
        asyncio.run(run_investigation(
            task_id, "support-a", db_path=demo_db, checkpoint_db_path=checkpoint_path,
            resume=True, d3_mode=True, executor_id="executor-a", run_id=run_id,
        ))
    assert expected_error in repr(failure.value)
    assert _count(demo_db, "d3_plans", "task_id = ?", (task_id,)) == 1
    assert _count(demo_db, "d3_action_intents", "task_id = ?", (task_id,)) == (1 if activity == "action_intent" else 0)
    assert _count(demo_db, "d3_action_ledgers", "task_id = ?", (task_id,)) == 0
    assert get_integration_info(demo_db, "tenant-a", "integration-a")["config_version"] == 7
    with connect(demo_db) as connection:
        run = connection.execute(
            "SELECT status, blocked_reason FROM task_runs WHERE run_id = ?", (run_id,)
        ).fetchone()
    assert tuple(run) == ("INTERRUPTED_RECOVERABLE", "RUN_INTERRUPTED_BEFORE_RESULT")


@pytest.mark.parametrize("change", ["abort", "correction"])
def test_hf09_precheckpoint_task_control_change_rejects_resume_before_checkpoint_access(
    approval_client: TestClient,
    demo_db: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    change: str,
) -> None:
    from opspilot.investigator import run_investigation

    monkeypatch.setenv(MODEL_API_KEY, "m1-hf-control-change-placeholder")
    monkeypatch.setenv(MODEL_NAME, "m1-hf-control-change-no-provider-call")
    support_headers = _login(approval_client, "support-a")
    session_response = approval_client.post("/api/sessions", headers=support_headers)
    assert session_response.status_code == 201, session_response.text
    session_id = str(session_response.json()["session_id"])
    created_response = approval_client.post(
        f"/api/sessions/{session_id}/tasks",
        headers={**support_headers, "Idempotency-Key": f"hf09-control-{change}-create"},
        json={"initial_message": "订单 API 返回 401，请调查当前绑定路由。"},
    )
    assert created_response.status_code == 202, created_response.text
    created = created_response.json()
    task_id, run_id = str(created["task_id"]), str(created["run_id"])
    with connect(demo_db) as connection:
        connection.execute(
            "UPDATE task_runs SET status = 'INTERRUPTED_RECOVERABLE' WHERE run_id = ?",
            (run_id,),
        )
        connection.execute(
            "UPDATE task_bindings SET status = 'INTERRUPTED_RECOVERABLE' WHERE task_id = ?",
            (task_id,),
        )

    if change == "abort":
        changed = approval_client.post(
            f"/api/tasks/{task_id}/abort",
            headers={**support_headers, "Idempotency-Key": "hf09-precheckpoint-abort"},
            json={"reason": "abort before cold recovery"},
        )
    else:
        changed = approval_client.post(
            f"/api/sessions/{session_id}/messages",
            headers={**support_headers, "Idempotency-Key": "hf09-precheckpoint-correction"},
            json={"task_id": task_id, "input_kind": "CORRECT_TASK_INPUT",
                  "body": "New critical correction invalidates this old Run."},
        )
    assert changed.status_code == 202, changed.text

    checkpoint_path = tmp_path / f"hf09-control-{change}-empty.sqlite3"
    with pytest.raises(TaskControlError, match="TASK_RUN_NOT_RESUMABLE"):
        asyncio.run(run_investigation(
            task_id, "support-a", db_path=demo_db, checkpoint_db_path=checkpoint_path,
            resume=True, d3_mode=True, executor_id="executor-a", run_id=run_id,
        ))
    assert not checkpoint_path.exists()
    assert _count(demo_db, "d3_plans", "task_id = ?", (task_id,)) == 0
    assert _count(demo_db, "d3_action_intents", "task_id = ?", (task_id,)) == 0
    assert _count(demo_db, "d3_action_ledgers", "task_id = ?", (task_id,)) == 0
    with connect(demo_db) as connection:
        run = connection.execute(
            "SELECT status, blocked_reason FROM task_runs WHERE run_id = ?", (run_id,)
        ).fetchone()
        control = connection.execute(
            "SELECT terminal_state, pending_critical_message_seq, control_revision FROM task_controls WHERE task_id = ?",
            (task_id,),
        ).fetchone()
    assert run["status"] == "BLOCKED"
    if change == "abort":
        assert control["terminal_state"] == "ABORTED"
    else:
        assert control["terminal_state"] == "ACTIVE"
        assert control["pending_critical_message_seq"] is not None
        assert int(control["control_revision"]) == 1
