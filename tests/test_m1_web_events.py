from __future__ import annotations

import hashlib
import json
from pathlib import Path

from fastapi.testclient import TestClient

from opspilot.domain.database import connect
from opspilot.domain.events import project_outbox, reconcile_legacy_action_events
from opspilot.web.app import create_app


PASSWORD = "support-test-password"
ORIGIN = "http://testserver"


def _app_client(db: Path) -> TestClient:
    app = create_app(
        db_path=db, start_worker=False,
        credentials={"support-a": PASSWORD, "approver-a": "approver-test-password",
                     "support-b": "support-b-test-password"},
        expected_origin=ORIGIN, heartbeat_seconds=0.05,
    )
    return TestClient(app, raise_server_exceptions=False)


def _logged_in(client: TestClient) -> dict[str, str]:
    response = client.post(
        "/api/auth/login", headers={"Origin": ORIGIN},
        json={"actor_id": "support-a", "password": PASSWORD},
    )
    assert response.status_code == 200
    return {"Origin": ORIGIN, "X-CSRF-Token": response.json()["csrf_token"]}


def test_n2_02_n2_04_sse_reconnect_cursor_precedence_and_no_fake_chat(demo_db: Path) -> None:
    with _app_client(demo_db) as client:
        headers = _logged_in(client)
        created = client.post("/api/sessions", headers=headers)
        session_id = created.json()["session_id"]
        accepted = client.post(
            f"/api/sessions/{session_id}/messages",
            headers={**headers, "Idempotency-Key": "n2-04-readonly"},
            json={"body": "private user statement 401 marker", "input_kind": "CHAT_READONLY"},
        )
        assert accepted.status_code == 202 and accepted.json()["answer_status"] == "NOT_IMPLEMENTED"
        run = client.get(f"/api/runs/{accepted.json()['run_id']}")
        assert run.status_code == 200 and run.json()["status"] == "QUEUED"

        replay = client.get(
            f"/api/sessions/{session_id}/events/history?after=999",
            headers={"Last-Event-ID": "0"},
        )
        assert replay.status_code == 200
        assert replay.json()["cursor_source"] == "Last-Event-ID"
        events = replay.json()["items"]
        assert [item["event_kind"] for item in events] == ["SESSION_CREATED", "MESSAGE_ACCEPTED"]
        assert all("private user statement" not in json.dumps(item["payload"]) for item in events)
        assert int(events[0]["event_seq"]) < int(events[1]["event_seq"])

        # The response stream deliberately repeats the same durable IDs after a
        # client reconnects from an old cursor; clients dedupe by the sequence.
        replay_again = client.get(
            f"/api/sessions/{session_id}/events/history?after=0",
            headers={"Last-Event-ID": "0"},
        ).json()["items"]
        assert [item["event_seq"] for item in replay_again] == [item["event_seq"] for item in events]
        invalid_cursor = client.get(f"/api/sessions/{session_id}/events/history?after=0", headers={"Last-Event-ID": "abc"})
        assert invalid_cursor.status_code == 400 and invalid_cursor.json() == {"code": "INVALID_EVENT_CURSOR"}


def test_n2_03_reconcile_committed_ledger_only_adds_missing_event(demo_db: Path) -> None:
    with _app_client(demo_db) as client:
        headers = _logged_in(client)
        session_id = client.post("/api/sessions", headers=headers).json()["session_id"]
        task_response = client.post(
            f"/api/sessions/{session_id}/tasks",
            headers={**headers, "Idempotency-Key": "n2-03-task"},
            json={"initial_message": "401 historical event reconciliation fixture"},
        )
        task_id = task_response.json()["task_id"]
        action_id = "action-n2-03-historical-repair"
        result = {"action_id": action_id, "action_kind": "REPAIR", "status": "COMMITTED"}
        serialized = json.dumps(result, sort_keys=True, separators=(",", ":"))
        digest = hashlib.sha256(serialized.encode()).hexdigest()
        with connect(demo_db) as connection:
            connection.execute(
                """INSERT INTO d3_action_intents
                   (action_id, tenant_id, task_id, plan_hash, action_kind, idempotency_key,
                    approval_id, canonical_request_json, request_digest, created_at)
                   VALUES (?, 'tenant-a', ?, 'plan-historical', 'REPAIR', ?, 'approval-historical', '{}', ?, '2026-10-18T00:00:00+00:00')""",
                (action_id, task_id, f"key-{action_id}", digest),
            )
            connection.execute(
                """INSERT INTO d3_action_ledgers
                   (ledger_id, tenant_id, task_id, plan_hash, action_kind, action_id, idempotency_key,
                    request_digest, approval_id, status, before_version, after_version,
                    result_json, result_digest, committed_at)
                   VALUES (?, 'tenant-a', ?, 'plan-historical', 'REPAIR', ?, ?, ?, 'approval-historical',
                           'COMMITTED', 7, 8, ?, ?, '2026-10-18T00:00:01+00:00')""",
                (f"ledger-{action_id}", task_id, action_id, f"key-{action_id}", digest, serialized, digest),
            )
            before = {
                "intents": connection.execute("SELECT COUNT(*) FROM d3_action_intents WHERE task_id = ?", (task_id,)).fetchone()[0],
                "ledgers": connection.execute("SELECT COUNT(*) FROM d3_action_ledgers WHERE task_id = ?", (task_id,)).fetchone()[0],
                "config_version": connection.execute("SELECT config_version FROM integrations WHERE tenant_id = 'tenant-a' AND integration_id = 'integration-a'").fetchone()[0],
            }
        first = reconcile_legacy_action_events(str(demo_db))
        second = reconcile_legacy_action_events(str(demo_db))
        project_outbox(str(demo_db))
        with connect(demo_db) as connection:
            after = {
                "intents": connection.execute("SELECT COUNT(*) FROM d3_action_intents WHERE task_id = ?", (task_id,)).fetchone()[0],
                "ledgers": connection.execute("SELECT COUNT(*) FROM d3_action_ledgers WHERE task_id = ?", (task_id,)).fetchone()[0],
                "config_version": connection.execute("SELECT config_version FROM integrations WHERE tenant_id = 'tenant-a' AND integration_id = 'integration-a'").fetchone()[0],
                "outbox_events": connection.execute("SELECT COUNT(*) FROM domain_outbox WHERE source_kind = 'ACTION_LEDGER' AND source_id = ?", (action_id,)).fetchone()[0],
                "session_events": connection.execute("SELECT COUNT(*) FROM session_events WHERE source_kind = 'ACTION_LEDGER' AND source_id = ?", (action_id,)).fetchone()[0],
            }
        assert before == {"intents": 1, "ledgers": 1, "config_version": 7}
        assert after == {**before, "outbox_events": 1, "session_events": 1}
        assert first["action_events_reconciled"] == 1
        assert second["action_events_reconciled"] == 0


def test_n2_05_unknown_session_events_require_authenticated_owner(demo_db: Path) -> None:
    with _app_client(demo_db) as client:
        support_headers = _logged_in(client)
        session_id = client.post("/api/sessions", headers=support_headers).json()["session_id"]
        other = TestClient(client.app, raise_server_exceptions=False)
        try:
            other.post(
                "/api/auth/login", headers={"Origin": ORIGIN},
                json={"actor_id": "support-b", "password": "support-b-test-password"},
            )
            history = other.get(f"/api/sessions/{session_id}/events/history")
            stream = other.get(f"/api/sessions/{session_id}/events")
            guessed = other.get(f"/api/sessions/guess-event-000/events/history")
            assert history.status_code == stream.status_code == guessed.status_code == 404
            assert "SESSION_CREATED" not in history.text
        finally:
            other.close()
