from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from opspilot.domain.database import connect
from opspilot.domain.d2 import create_task_binding
from opspilot.domain.task_control import admit_task_message
from opspilot.web.app import create_app


PASSWORDS = {
    "support-a": "support-test-password",
    "approver-a": "approver-test-password",
    "support-b": "support-b-test-password",
    "approver-b": "approver-b-test-password",
}
ORIGIN = "http://testserver"


@pytest.fixture
def web_client(demo_db: Path):
    app = create_app(
        db_path=demo_db, start_worker=False, credentials=PASSWORDS,
        expected_origin=ORIGIN, heartbeat_seconds=0.05,
    )
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client


def _login(client: TestClient, actor_id: str = "support-a") -> tuple[str, dict[str, str]]:
    response = client.post(
        "/api/auth/login", headers={"Origin": ORIGIN},
        json={"actor_id": actor_id, "password": PASSWORDS[actor_id]},
    )
    assert response.status_code == 200, response.text
    return response.json()["csrf_token"], {"Origin": ORIGIN, "X-CSRF-Token": response.json()["csrf_token"]}


def _session(client: TestClient, headers: dict[str, str]) -> str:
    response = client.post("/api/sessions", headers=headers)
    assert response.status_code == 201, response.text
    return str(response.json()["session_id"])


def _create_task(client: TestClient, headers: dict[str, str], session_id: str, *, key: str, body: str) -> dict[str, object]:
    response = client.post(
        f"/api/sessions/{session_id}/tasks",
        headers={**headers, "Idempotency-Key": key},
        json={"initial_message": body},
    )
    assert response.status_code in {200, 202}, response.text
    return response.json()


def _count(db: Path, table: str, where: str = "1=1", params: tuple[object, ...] = ()) -> int:
    with connect(db) as connection:
        return int(connection.execute(f"SELECT COUNT(*) FROM {table} WHERE {where}", params).fetchone()[0])


def test_web_01_login_identity_header_and_body_spoofing_fail_closed(web_client: TestClient) -> None:
    unauthenticated = web_client.get("/api/sessions")
    assert unauthenticated.status_code == 401 and unauthenticated.json() == {"code": "AUTHENTICATION_REQUIRED"}
    wrong_password = web_client.post(
        "/api/auth/login", headers={"Origin": ORIGIN},
        json={"actor_id": "support-a", "password": "wrong"},
    )
    assert wrong_password.status_code == 401 and wrong_password.json() == {"code": "INVALID_CREDENTIALS"}
    missing_origin = web_client.post("/api/auth/login", json={"actor_id": "support-a", "password": PASSWORDS["support-a"]})
    assert missing_origin.status_code == 403 and missing_origin.json() == {"code": "ORIGIN_REJECTED"}

    support_headers = _login(web_client, "support-a")[1]
    session_id = _session(web_client, support_headers)
    task = _create_task(web_client, support_headers, session_id, key="web-01-task", body="401 on orders route")
    approver = TestClient(web_client.app, raise_server_exceptions=False)
    try:
        approver_headers = _login(approver, "approver-a")[1]
        denied = approver.post(
            f"/api/tasks/{task['task_id']}/abort",
            headers={**approver_headers, "X-Actor-ID": "support-a", "X-Tenant-ID": "tenant-a",
                     "X-Executor-ID": "executor-a", "Idempotency-Key": "forged-abort"},
            json={"reason": "forged identity must not own this task"},
        )
        assert denied.status_code == 403 and denied.json() == {"code": "TASK_OWNER_REQUIRED"}
        spoofed = web_client.post(
            f"/api/sessions/{session_id}/tasks",
            headers={**support_headers, "Idempotency-Key": "spoofed-body"},
            json={"initial_message": "attempt", "tenant_id": "tenant-b", "actor_id": "support-b", "role": "APPROVER"},
        )
        assert spoofed.status_code == 422 and spoofed.json() == {"code": "INVALID_REQUEST"}
        assert "wrong" not in denied.text and "Authorization" not in denied.text
    finally:
        approver.close()


def test_web_02_owner_tenant_enumeration_and_approver_abort_are_denied(
    web_client: TestClient, demo_db: Path
) -> None:
    support_headers = _login(web_client, "support-a")[1]
    session_id = _session(web_client, support_headers)
    task = _create_task(web_client, support_headers, session_id, key="web-02-task", body="401")
    other_binding = create_task_binding(demo_db, "support-b", "orders-demo", "integration-b", "INC-B-001")

    other_tenant = TestClient(web_client.app, raise_server_exceptions=False)
    approver = TestClient(web_client.app, raise_server_exceptions=False)
    try:
        other_headers = _login(other_tenant, "support-b")[1]
        approver_headers = _login(approver, "approver-a")[1]
        checks = [
            other_tenant.get(f"/api/sessions/{session_id}"),
            other_tenant.get(f"/api/sessions/{session_id}/messages"),
            other_tenant.get(f"/api/sessions/{session_id}/events/history"),
            other_tenant.get(f"/api/tasks/{task['task_id']}"),
            other_tenant.get(f"/api/tasks/{task['task_id']}/runs"),
            other_tenant.get(f"/api/runs/{task['run_id']}"),
            web_client.get(f"/api/tasks/{other_binding['task_id']}"),
        ]
        assert all(response.status_code == 404 for response in checks)
        denied_abort = approver.post(
            f"/api/tasks/{task['task_id']}/abort",
            headers={**approver_headers, "Idempotency-Key": "approver-cannot-abort"},
            json={"reason": "approver is read-only in M1-02"},
        )
        assert denied_abort.status_code == 403
        assert denied_abort.json() == {"code": "TASK_OWNER_REQUIRED"}
        assert other_headers["X-CSRF-Token"] != support_headers["X-CSRF-Token"]
    finally:
        other_tenant.close()
        approver.close()


def test_web_03_task_message_command_run_and_outbox_are_atomic_and_idempotent(
    web_client: TestClient, demo_db: Path
) -> None:
    headers = _login(web_client)[1]
    session_id = _session(web_client, headers)
    first = _create_task(web_client, headers, session_id, key="web-03-task", body="Orders returns 401 after rotation.")
    replay_response = web_client.post(
        f"/api/sessions/{session_id}/tasks",
        headers={**headers, "Idempotency-Key": "web-03-task"},
        json={"initial_message": "Orders returns 401 after rotation."},
    )
    replay = replay_response.json()
    assert replay_response.status_code == 200 and replay["replayed"] is True
    for key in ("task_id", "session_id", "command_id", "message_id", "run_id"):
        assert replay[key] == first[key]
    conflict = web_client.post(
        f"/api/sessions/{session_id}/tasks",
        headers={**headers, "Idempotency-Key": "web-03-task"},
        json={"initial_message": "different canonical request"},
    )
    assert conflict.status_code == 409 and conflict.json() == {"code": "IDEMPOTENCY_CONFLICT"}
    with connect(demo_db) as connection:
        counts = {
            "task": connection.execute("SELECT COUNT(*) FROM task_bindings WHERE task_id = ?", (first["task_id"],)).fetchone()[0],
            "message": connection.execute("SELECT COUNT(*) FROM messages WHERE message_id = ?", (first["message_id"],)).fetchone()[0],
            "command": connection.execute("SELECT COUNT(*) FROM commands WHERE command_id = ?", (first["command_id"],)).fetchone()[0],
            "run": connection.execute("SELECT COUNT(*) FROM task_runs WHERE run_id = ?", (first["run_id"],)).fetchone()[0],
            "events": connection.execute("SELECT COUNT(*) FROM session_events WHERE source_id = ?", (first["command_id"],)).fetchone()[0],
        }
    assert counts == {"task": 1, "message": 1, "command": 1, "run": 1, "events": 2}
    assert first["run_status"] == "QUEUED" and first["application_state"] == "RECEIVED_NOT_APPLIED"
    run = web_client.get(f"/api/runs/{first['run_id']}")
    assert run.status_code == 200 and run.json()["status"] == "QUEUED"


def test_web_04_task_and_correction_insert_failures_roll_back_and_retry_cleanly(
    web_client: TestClient, demo_db: Path
) -> None:
    headers = _login(web_client)[1]
    session_id = _session(web_client, headers)
    with connect(demo_db) as connection:
        connection.execute(
            """CREATE TRIGGER fail_first_investigation BEFORE INSERT ON task_runs
               WHEN NEW.kind = 'INVESTIGATE' BEGIN SELECT RAISE(ABORT, 'injected task run insert'); END"""
        )
    failed = web_client.post(
        f"/api/sessions/{session_id}/tasks",
        headers={**headers, "Idempotency-Key": "web-04-create-failed"},
        json={"initial_message": "new task"},
    )
    assert failed.status_code == 500 and failed.json() == {"code": "INTERNAL_ERROR"}
    with connect(demo_db) as connection:
        for table in ("task_bindings", "messages", "commands", "task_runs", "domain_outbox", "session_events"):
            expected = 1 if table in {"domain_outbox", "session_events"} else 0
            assert connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == expected
        connection.execute("DROP TRIGGER fail_first_investigation")
    created = _create_task(web_client, headers, session_id, key="web-04-create-failed", body="new task")

    with connect(demo_db) as connection:
        connection.execute(
            """CREATE TRIGGER fail_correction_run BEFORE INSERT ON task_runs
               WHEN NEW.kind = 'INVESTIGATE'
               BEGIN SELECT RAISE(ABORT, 'injected correction run insert'); END""",
        )
    correction_headers = {**headers, "Idempotency-Key": "web-04-correction"}
    failed_correction = web_client.post(
        f"/api/sessions/{session_id}/messages", headers=correction_headers,
        json={"task_id": created["task_id"], "input_kind": "CORRECT_TASK_INPUT", "body": "use the rotated credential clue"},
    )
    assert failed_correction.status_code == 500
    with connect(demo_db) as connection:
        control = connection.execute("SELECT control_revision, pending_critical_message_seq FROM task_controls WHERE task_id = ?", (created["task_id"],)).fetchone()
        assert tuple(control) == (0, None)
        connection.execute("DROP TRIGGER fail_correction_run")
    accepted = web_client.post(
        f"/api/sessions/{session_id}/messages", headers=correction_headers,
        json={"task_id": created["task_id"], "input_kind": "CORRECT_TASK_INPUT", "body": "use the rotated credential clue"},
    )
    replay = web_client.post(
        f"/api/sessions/{session_id}/messages", headers=correction_headers,
        json={"task_id": created["task_id"], "input_kind": "CORRECT_TASK_INPUT", "body": "use the rotated credential clue"},
    )
    assert accepted.status_code == replay.status_code == 202
    assert accepted.json()["message_id"] == replay.json()["message_id"]
    with connect(demo_db) as connection:
        control = connection.execute("SELECT control_revision, pending_critical_message_seq FROM task_controls WHERE task_id = ?", (created["task_id"],)).fetchone()
        assert int(control["control_revision"]) == 1 and int(control["pending_critical_message_seq"]) == accepted.json()["sequence"]


def test_web_05_origin_csrf_logout_and_expiry_fail_closed(web_client: TestClient, demo_db: Path) -> None:
    response = web_client.post(
        "/api/auth/login", headers={"Origin": ORIGIN},
        json={"actor_id": "support-a", "password": PASSWORDS["support-a"]},
    )
    assert "httponly" in response.headers["set-cookie"].lower()
    assert "samesite=strict" in response.headers["set-cookie"].lower()
    csrf = response.json()["csrf_token"]
    missing = web_client.post("/api/sessions", headers={"Origin": ORIGIN})
    assert missing.status_code == 403 and missing.json() == {"code": "CSRF_REJECTED"}
    wrong_origin = web_client.post(
        "/api/sessions", headers={"Origin": "https://attacker.invalid", "X-CSRF-Token": csrf}
    )
    assert wrong_origin.status_code == 403 and wrong_origin.json() == {"code": "ORIGIN_REJECTED"}
    assert web_client.get("/api/auth/me").status_code == 200
    token = web_client.cookies.get("opspilot_session")
    token_digest = hashlib.sha256(token.encode()).hexdigest()
    with connect(demo_db) as connection:
        connection.execute(
            "UPDATE web_auth_sessions SET expires_at = '2000-01-01T00:00:00+00:00' WHERE token_digest = ?",
            (token_digest,),
        )
    expired = web_client.get("/api/auth/me")
    assert expired.status_code == 401 and expired.json() == {"code": "AUTHENTICATION_REQUIRED"}

    fresh = TestClient(web_client.app, raise_server_exceptions=False)
    try:
        csrf = _login(fresh)[1]["X-CSRF-Token"]
        logged_out = fresh.post(
            "/api/auth/logout", headers={"Origin": ORIGIN, "X-CSRF-Token": csrf}
        )
        assert logged_out.status_code == 200
        assert fresh.get("/api/auth/me").status_code == 401
    finally:
        fresh.close()


def test_web_06_readonly_chat_remains_queued_and_does_not_change_task_state(
    web_client: TestClient, demo_db: Path
) -> None:
    headers = _login(web_client)[1]
    session_id = _session(web_client, headers)
    task = _create_task(web_client, headers, session_id, key="web-06-task", body="401")
    with connect(demo_db) as connection:
        connection.execute("UPDATE task_bindings SET status = 'WAITING_APPROVAL' WHERE task_id = ?", (task["task_id"],))
    chat = web_client.post(
        f"/api/sessions/{session_id}/messages",
        headers={**headers, "Idempotency-Key": "web-06-chat"},
        json={"task_id": task["task_id"], "input_kind": "CHAT_READONLY", "body": "What is the status?"},
    )
    assert chat.status_code == 202 and chat.json()["answer_status"] == "NOT_IMPLEMENTED"
    run = web_client.get(f"/api/runs/{chat.json()['run_id']}")
    task_view = web_client.get(f"/api/tasks/{task['task_id']}")
    assert run.status_code == 200 and run.json()["status"] == "QUEUED"
    assert task_view.json()["status"] == "WAITING_APPROVAL"
    assert _count(demo_db, "task_runs", "task_id = ? AND status = 'RUNNING'", (task["task_id"],)) == 0
