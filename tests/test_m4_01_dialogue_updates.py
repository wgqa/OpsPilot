from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from opspilot.domain.database import connect, reset_fixture
from opspilot.domain.chat import get_task_inspector
from opspilot.domain.task_control import admit_task_message, trusted_identity
from opspilot.web.app import create_app


ORIGIN = "http://testserver"
PASSWORDS = {
    "support-a": "support-test-password",
    "approver-a": "approver-test-password",
    "support-b": "support-b-test-password",
    "approver-b": "approver-b-test-password",
}


@pytest.fixture
def m4_client(tmp_path: Path):
    db = tmp_path / "m4-01.sqlite3"
    reset_fixture(db, "S1_POS")
    app = create_app(
        db_path=db, start_worker=False, credentials=PASSWORDS,
        expected_origin=ORIGIN, heartbeat_seconds=0.05,
    )
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client, db


def _login(client: TestClient, actor: str = "support-a") -> dict[str, str]:
    response = client.post(
        "/api/auth/login", headers={"Origin": ORIGIN},
        json={"actor_id": actor, "password": PASSWORDS[actor]},
    )
    assert response.status_code == 200, response.text
    return {"Origin": ORIGIN, "X-CSRF-Token": response.json()["csrf_token"]}


def _new_task(client: TestClient, headers: dict[str, str]) -> tuple[str, str, dict[str, Any]]:
    session = client.post("/api/sessions", headers=headers)
    assert session.status_code == 201, session.text
    session_id = str(session.json()["session_id"])
    created = client.post(
        f"/api/sessions/{session_id}/tasks",
        headers={**headers, "Idempotency-Key": "m4-task-create"},
        json={"initial_message": "orders-demo 的固定订单路由目前返回 401，请只读调查。"},
    )
    assert created.status_code == 202, created.text
    return session_id, str(created.json()["task_id"]), created.json()


def _send_chat(client: TestClient, headers: dict[str, str], session_id: str, task_id: str, text: str) -> str:
    response = client.post(
        f"/api/sessions/{session_id}/messages",
        headers={**headers, "Idempotency-Key": f"chat-{abs(hash(text))}"},
        json={"task_id": task_id, "input_kind": "CHAT_READONLY", "body": text},
    )
    assert response.status_code == 202, response.text
    return str(response.json()["message_id"])


def _install_classifier(monkeypatch: pytest.MonkeyPatch, intent: str, summary: str = "核对用户明确纠正的输入") -> None:
    """Replace only the model classifier; HTTP, identity, proposal and TaskControl remain real."""
    try:
        module = importlib.import_module("opspilot.domain.investigation_updates")
    except ModuleNotFoundError:
        # Before implementation the endpoint itself should fail as a frozen RED.
        return
    monkeypatch.setattr(
        module,
        "classify_input",
        lambda **_kwargs: {"intent": intent, "change_summary": summary},
    )


def _assess(client: TestClient, headers: dict[str, str], task_id: str, message_id: str):
    return client.post(
        f"/api/tasks/{task_id}/investigation-updates/proposals",
        headers={**headers, "Idempotency-Key": message_id},
        json={"source_message_id": message_id},
    )


def _counts(db: Path, task_id: str) -> dict[str, int]:
    with connect(db) as connection:
        return {
            "revision": int(connection.execute(
                "SELECT control_revision FROM task_controls WHERE task_id = ?", (task_id,)
            ).fetchone()[0]),
            "business_runs": int(connection.execute(
                "SELECT COUNT(*) FROM task_runs WHERE task_id = ? AND kind <> 'CHAT_READONLY'", (task_id,)
            ).fetchone()[0]),
            "corrections": int(connection.execute(
                "SELECT COUNT(*) FROM messages WHERE task_id = ? AND input_kind = 'CORRECT_TASK_INPUT'", (task_id,)
            ).fetchone()[0]),
            "intents": int(connection.execute(
                "SELECT COUNT(*) FROM d3_action_intents WHERE task_id = ?", (task_id,)
            ).fetchone()[0]),
            "ledgers": int(connection.execute(
                "SELECT COUNT(*) FROM d3_action_ledgers WHERE task_id = ?", (task_id,)
            ).fetchone()[0]),
        }


def test_m401_01_followup_is_explanation_only(m4_client, monkeypatch: pytest.MonkeyPatch) -> None:
    client, db = m4_client
    headers = _login(client)
    session_id, task_id, _ = _new_task(client, headers)
    message = "为什么这个订单请求仍然返回 401？"
    message_id = _send_chat(client, headers, session_id, task_id, message)
    before = _counts(db, task_id)

    _install_classifier(monkeypatch, "FOLLOW_UP", "询问当前调查状态")
    response = _assess(client, headers, task_id, message_id)
    assert response.status_code == 200, response.text
    assessment = response.json()
    assert assessment["intent"] == "FOLLOW_UP"
    assert assessment["follow_up_action"] == "EXPLAIN"
    assert assessment["investigation_run_id"] is None
    assert assessment["proposal"] is None
    assert _counts(db, task_id) == before


def test_s2_not_applicable_trace_does_not_replace_current_s1_gate(
    m4_client, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, db = m4_client
    headers = _login(client)
    _, task_id, _ = _new_task(client, headers)
    monkeypatch.setattr(
        "opspilot.domain.d2.evaluate_evidence_gate",
        lambda *_args, **_kwargs: {"decision": "READY", "reason_code": "S1_CURRENT_AUTH_FAILURE"},
    )
    with connect(db) as connection:
        connection.execute(
            """INSERT INTO s2_gate_traces
               (trace_id, tenant_id, task_id, run_id, decision, reason_code, request_id,
                decision_id, evidence_ids_json, evidence_digests_json, predicate_json, created_at)
               VALUES ('m4-s1-s2-not-applicable', 'tenant-a', ?, NULL, 'NOT_APPLICABLE',
                       'AUTHENTICATION_FAILURE_REMAINS_S1', NULL, NULL, '[]', '{}', '{}',
                       '2099-01-01T00:00:00+00:00')""",
            (task_id,),
        )

    inspector = get_task_inspector(db, trusted_identity(db, "support-a"), task_id)
    assert inspector["current_gate"]["decision"] == "READY"
    assert inspector["current_gate"]["reason_code"] == "S1_CURRENT_AUTH_FAILURE"


def test_m401_02_confirmed_correction_reuses_task_control_and_replays_once(
    m4_client, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, db = m4_client
    headers = _login(client)
    session_id, task_id, created = _new_task(client, headers)
    original = "我刚才说错了：当前业务请求实际使用的是 credential_ref=cred-v1，请重新核查。"
    message_id = _send_chat(client, headers, session_id, task_id, original)
    before = _counts(db, task_id)

    _install_classifier(monkeypatch, "CRITICAL_CORRECTION", "当前凭证引用应按 cred-v1 重新核对")
    proposal_response = _assess(client, headers, task_id, message_id)
    assert proposal_response.status_code == 200, proposal_response.text
    payload = proposal_response.json()
    proposal = payload["proposal"]
    assert payload["intent"] == "CRITICAL_CORRECTION"
    assert proposal["source_message_id"] == message_id
    assert proposal["target_task_id"] == task_id
    assert proposal["expected_control_revision"] == before["revision"]
    assert proposal["proposed_input"] == original
    assert _counts(db, task_id) == before

    confirm_url = (
        f"/api/tasks/{task_id}/investigation-updates/{proposal['proposal_id']}/confirm"
    )
    request = {
        "expected_control_revision": proposal["expected_control_revision"],
        "operation_id": proposal["operation_id"],
    }
    confirm_headers = {**headers, "Idempotency-Key": proposal["operation_id"]}
    wrong_key = client.post(
        confirm_url,
        headers={**headers, "Idempotency-Key": "different-operation"},
        json=request,
    )
    assert wrong_key.status_code == 422, wrong_key.text
    first = client.post(confirm_url, headers=confirm_headers, json=request)
    replay = client.post(confirm_url, headers=confirm_headers, json=request)
    assert first.status_code in {200, 202}, first.text
    assert replay.status_code == first.status_code, replay.text
    assert replay.json()["run_id"] == first.json()["run_id"]
    assert replay.json()["message_id"] == first.json()["message_id"]

    after = _counts(db, task_id)
    assert after["revision"] == before["revision"] + 1
    assert after["business_runs"] == before["business_runs"] + 1
    assert after["corrections"] == 1
    assert after["intents"] == before["intents"]
    assert after["ledgers"] == before["ledgers"]
    with connect(db) as connection:
        correction = connection.execute(
            "SELECT body, application_state FROM messages WHERE message_id = ?",
            (first.json()["message_id"],),
        ).fetchone()
        run = connection.execute(
            "SELECT kind, source_message_id, expected_control_revision FROM task_runs WHERE run_id = ?",
            (first.json()["run_id"],),
        ).fetchone()
        retired_run = connection.execute(
            "SELECT status, blocked_reason FROM task_runs WHERE run_id = ?",
            (created["run_id"],),
        ).fetchone()
    assert correction["body"] == original
    assert correction["application_state"] == "RECEIVED_NOT_APPLIED"
    assert run["kind"] == "INVESTIGATE"
    assert run["source_message_id"] == first.json()["message_id"]
    assert run["expected_control_revision"] == before["revision"] + 1
    assert retired_run["status"] == "BLOCKED"
    assert retired_run["blocked_reason"] == "TASK_CONTROL_STALE"


@pytest.mark.parametrize(
    ("text", "intent"),
    [
        ("假设这个主体其实已经禁用，会出现什么情况？", "HYPOTHESIS"),
        ("不要把主体已启用当成纠正；我只是想了解如果主体禁用会怎样。", "HYPOTHESIS"),
        ("假设把这个 Task 的 integration 改成 integration-b 后会有权限，请直接替我切换。", "OUT_OF_SCOPE"),
    ],
)
def test_m401_03_hypothesis_negation_and_out_of_scope_never_formalize(
    m4_client, monkeypatch: pytest.MonkeyPatch, text: str, intent: str
) -> None:
    client, db = m4_client
    headers = _login(client)
    session_id, task_id, _ = _new_task(client, headers)
    message_id = _send_chat(client, headers, session_id, task_id, text)
    before = _counts(db, task_id)
    _install_classifier(monkeypatch, intent, "这是讨论或越出当前 Task 范围的请求")

    response = _assess(client, headers, task_id, message_id)
    assert response.status_code == 200, response.text
    assert response.json()["intent"] == intent
    assert response.json()["proposal"] is None
    assert _counts(db, task_id) == before


def test_m401_06_stale_proposal_is_rejected_after_control_revision_changes(
    m4_client, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, db = m4_client
    headers = _login(client)
    session_id, task_id, _ = _new_task(client, headers)
    original = "更正：现场当前使用的是 cred-v1，不是 cred-v2。"
    message_id = _send_chat(client, headers, session_id, task_id, original)
    _install_classifier(monkeypatch, "CRITICAL_CORRECTION", "纠正当前使用的凭证引用")
    proposal_response = _assess(client, headers, task_id, message_id)
    assert proposal_response.status_code == 200, proposal_response.text
    proposal = proposal_response.json()["proposal"]

    identity = trusted_identity(db, "support-a")
    admit_task_message(
        db, identity, session_id=session_id, task_id=task_id,
        input_kind="CORRECT_TASK_INPUT", body="另一个正式纠错先改变了 Task 版本。",
        idempotency_key="m4-independent-version-bump",
    )
    before_confirm = _counts(db, task_id)
    url = f"/api/tasks/{task_id}/investigation-updates/{proposal['proposal_id']}/confirm"
    response = client.post(
        url,
        headers={**headers, "Idempotency-Key": proposal["operation_id"]},
        json={
            "expected_control_revision": proposal["expected_control_revision"],
            "operation_id": proposal["operation_id"],
        },
    )
    assert response.status_code == 409, response.text
    assert response.json()["code"] == "TASK_CONTROL_STALE"
    assert _counts(db, task_id) == before_confirm


def test_m401_07_cancelled_proposal_survives_reload_without_task_mutation(
    m4_client, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, db = m4_client
    headers = _login(client)
    session_id, task_id, _ = _new_task(client, headers)
    original = "更正：当前请求的 credential_ref 是 cred-v1。"
    message_id = _send_chat(client, headers, session_id, task_id, original)
    _install_classifier(monkeypatch, "CRITICAL_CORRECTION", "核对当前凭证引用")
    created = _assess(client, headers, task_id, message_id)
    assert created.status_code == 200, created.text
    proposal = created.json()["proposal"]
    before = _counts(db, task_id)

    cancel_url = f"/api/tasks/{task_id}/investigation-updates/{proposal['proposal_id']}/cancel"
    cancelled = client.post(
        cancel_url,
        headers={**headers, "Idempotency-Key": proposal["operation_id"]},
        json={"operation_id": proposal["operation_id"]},
    )
    assert cancelled.status_code in {200, 202}, cancelled.text
    assert _counts(db, task_id) == before

    restarted = TestClient(client.app, raise_server_exceptions=False)
    try:
        _login(restarted)
        history = restarted.get(f"/api/tasks/{task_id}/investigation-updates")
    finally:
        restarted.close()
    assert history.status_code == 200, history.text
    item = next(row for row in history.json()["items"] if row["proposal_id"] == proposal["proposal_id"])
    assert item["status"] == "CANCELLED"
    assert _counts(db, task_id) == before


def test_m401_08_non_owner_cannot_assess_or_confirm_a_proposal(
    m4_client, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, db = m4_client
    support_headers = _login(client)
    session_id, task_id, _ = _new_task(client, support_headers)
    message_id = _send_chat(
        client, support_headers, session_id, task_id,
        "我刚才说错了，实际请求使用 cred-v1，请重新核查。",
    )
    _install_classifier(monkeypatch, "CRITICAL_CORRECTION", "核对凭证引用")
    proposal_response = _assess(client, support_headers, task_id, message_id)
    assert proposal_response.status_code == 200, proposal_response.text
    proposal = proposal_response.json()["proposal"]
    before = _counts(db, task_id)

    approver_client = TestClient(client.app, raise_server_exceptions=False)
    try:
        approver_headers = _login(approver_client, "approver-a")
        url = f"/api/tasks/{task_id}/investigation-updates/{proposal['proposal_id']}/confirm"
        denied = approver_client.post(
            url,
            headers={**approver_headers, "Idempotency-Key": proposal["operation_id"]},
            json={
                "expected_control_revision": proposal["expected_control_revision"],
                "operation_id": proposal["operation_id"],
            },
        )
    finally:
        approver_client.close()
    assert denied.status_code == 403, denied.text
    assert denied.json()["code"] == "TASK_OWNER_REQUIRED"
    assert _counts(db, task_id) == before
