from __future__ import annotations

import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from opspilot.domain.chat import complete_chat_attempt, prepare_chat_attempt, record_chat_limit_in_transaction
from opspilot.domain.database import connect
from opspilot.domain.task_control import claim_task_run, register_worker_owner, trusted_identity
from opspilot.web.app import create_app


PASSWORDS = {"support-a": "support-test-password"}
ORIGIN = "http://testserver"


@pytest.fixture
def web_client(demo_db: Path):
    app = create_app(db_path=demo_db, start_worker=False, credentials=PASSWORDS, expected_origin=ORIGIN)
    with TestClient(app, raise_server_exceptions=True) as client:
        yield client


def _login(client: TestClient) -> tuple[dict[str, str], str]:
    response = client.post("/api/auth/login", headers={"Origin": ORIGIN},
                           json={"actor_id": "support-a", "password": PASSWORDS["support-a"]})
    assert response.status_code == 200, response.text
    token = response.json()["csrf_token"]
    return {"Origin": ORIGIN, "X-CSRF-Token": token}, token


def _new_session(client: TestClient, headers: dict[str, str]) -> str:
    response = client.post("/api/sessions", headers=headers)
    assert response.status_code == 201, response.text
    return str(response.json()["session_id"])


def _complete_chat(db: Path, run_id: str) -> dict[str, object]:
    identity = trusted_identity(db, "support-a")
    worker_id = "stage-b-chat-worker"
    register_worker_owner(db, worker_id, os.getpid())
    claim_task_run(db, identity, run_id)
    attempt = prepare_chat_attempt(db, run_id, worker_id, "deterministic-stage-b")
    return complete_chat_attempt(db, worker_id, str(attempt["attempt_id"]), "persisted answer",
                                 provider_response_id="deterministic-answer", input_tokens=2, output_tokens=3,
                                 total_tokens=5)


def test_stage_b_api_exposes_only_exact_chat_and_durable_limit_source_relations(
    web_client: TestClient, demo_db: Path
) -> None:
    headers, _ = _login(web_client)
    session_id = _new_session(web_client, headers)
    first = web_client.post(f"/api/sessions/{session_id}/messages", headers={**headers, "Idempotency-Key": "stage-b-chat"},
                            json={"input_kind": "CHAT_READONLY", "body": "first"})
    assert first.status_code == 202, first.text
    answer_result = _complete_chat(demo_db, str(first.json()["run_id"]))

    second = web_client.post(f"/api/sessions/{session_id}/messages", headers={**headers, "Idempotency-Key": "stage-b-limit"},
                             json={"input_kind": "CHAT_READONLY", "body": "second"})
    assert second.status_code == 202, second.text
    limit_run = str(second.json()["run_id"])
    with connect(demo_db) as connection:
        record_chat_limit_in_transaction(connection, limit_run, "CHAT_ATTEMPTS_EXHAUSTED")
        notice_id = str(connection.execute("SELECT message_id FROM messages WHERE command_id=?",
                                           (f"budget-notice:{limit_run}",)).fetchone()[0])

    messages = web_client.get(f"/api/sessions/{session_id}/messages", headers=headers)
    assert messages.status_code == 200, messages.text
    by_id = {item["message_id"]: item for item in messages.json()["items"]}
    answer = by_id[str(answer_result["message_id"])]
    notice = by_id[notice_id]

    assert "command_id" not in answer and "command_id" not in notice
    assert (answer["answer_run_id"], answer["answer_source_message_id"], answer["answer_kind"]) == (
        first.json()["run_id"], first.json()["message_id"], "CHAT_MODEL",
    )
    assert (notice["answer_run_id"], notice["answer_source_message_id"], notice["answer_kind"]) == (
        limit_run, second.json()["message_id"], "PROGRAM_LIMIT",
    )
    assert "模型最终答复" in notice["body"]

    with connect(demo_db) as connection:
        source = connection.execute("SELECT body_digest FROM messages WHERE message_id=?",
                                    (second.json()["message_id"],)).fetchone()
        connection.execute(
            "UPDATE chat_message_sources SET source_ref=?, source_digest=? WHERE message_id=? AND source_kind='MESSAGE' AND source_ref=?",
            (second.json()["message_id"], source["body_digest"], answer_result["message_id"], first.json()["message_id"]),
        )
    mismatched = web_client.get(f"/api/sessions/{session_id}/messages", headers=headers)
    assert mismatched.status_code == 200, mismatched.text
    mismatched_answer = next(item for item in mismatched.json()["items"] if item["message_id"] == answer_result["message_id"])
    assert mismatched_answer["answer_run_id"] is None
    assert mismatched_answer["answer_source_message_id"] is None
    assert mismatched_answer["answer_kind"] is None


def test_stage_b_api_redacts_s3_answer_and_its_association_after_scope_revocation(
    web_client: TestClient, demo_db: Path
) -> None:
    headers, _ = _login(web_client)
    session_id = _new_session(web_client, headers)
    task = web_client.post(f"/api/sessions/{session_id}/tasks", headers={**headers, "Idempotency-Key": "stage-b-s3-task"},
                           json={"initial_message": "Order callback investigation", "investigation_kind": "ASYNC_CALLBACK",
                                 "s3_order_id": "async-order"})
    assert task.status_code == 202, task.text
    accepted = task.json()
    from opspilot.domain.task_control import admit_task_message

    identity = trusted_identity(demo_db, "support-a")
    chat = admit_task_message(demo_db, identity, session_id=session_id, task_id=str(accepted["task_id"]),
                              input_kind="CHAT_READONLY", body="what is current?", idempotency_key="stage-b-s3-chat")
    answer_result = _complete_chat(demo_db, str(chat["run_id"]))
    visible = web_client.get(f"/api/sessions/{session_id}/messages", headers=headers)
    assert visible.status_code == 200, visible.text
    answer_before = next(item for item in visible.json()["items"] if item["message_id"] == answer_result["message_id"])
    assert answer_before["answer_kind"] == "CHAT_MODEL"
    assert answer_before["answer_source_message_id"] == chat["message_id"]

    with connect(demo_db) as connection:
        connection.execute("UPDATE route_scope_policies SET required_scopes_json='[\"revoked-scope\"]', scope_policy_version=scope_policy_version+1 WHERE tenant_id='tenant-a' AND service_id='orders-async-demo'")
    redacted = web_client.get(f"/api/sessions/{session_id}/messages", headers=headers)
    assert redacted.status_code == 200, redacted.text
    answer_after = next(item for item in redacted.json()["items"] if item["message_id"] == answer_result["message_id"])
    assert answer_after["body"] == "[S3 受限历史回答已隐藏：当前授权不可用]"
    assert answer_after["answer_run_id"] is None
    assert answer_after["answer_source_message_id"] is None
    assert answer_after["answer_kind"] is None
