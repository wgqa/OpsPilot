"""P0-01 pre-fix probes. Run explicitly with pytest. All content is synthetic."""

import asyncio
import json
import os
from pathlib import Path

import httpx
from fastapi.testclient import TestClient

from opspilot.assistant import create_assistant_model
from opspilot.domain.chat import prepare_chat_attempt
from opspilot.domain.database import connect, reset_fixture
from opspilot.domain.s3 import prepare_s3_fixture
from opspilot.domain.task_control import (
    admit_task_message,
    claim_task_run,
    create_session,
    create_task_with_initial_run,
    register_worker_owner,
    trusted_identity,
)
from opspilot.web.app import create_app
from opspilot.web.worker import _dispatch_run

A_ONLY = "Audit A only: receiver condition ALPHA-ONLY"
B_ONLY = "Audit B only: protocol BETA-ONLY"
SHARED = "Session protocol reference: HTTP 202 acknowledges receipt."
QUESTION = "Continue B"
WORKER = "p0-01-offline-worker"


def save(name, payload):
    output_dir = Path(os.environ["P0_01_OUTPUT"])
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / name).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def protected_counts(db):
    with connect(db) as connection:
        return {
            table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in (
                "d3_approvals", "d3_action_intents", "d3_action_ledgers",
                "s2_handoff_receipts", "s3_handoff_receipts",
            )
        }


def test_builder_excludes_other_task(tmp_path):
    db = tmp_path / "domain.sqlite"
    reset_fixture(db, "S1_POS")
    owner = trusted_identity(db, "support-a")
    session_id = create_session(db, owner)["session_id"]
    register_worker_owner(db, WORKER, os.getpid())

    def create_task(key, body):
        return create_task_with_initial_run(
            db, owner, session_id=session_id, service_id="orders-demo",
            integration_id="integration-a", ticket_id="INC-A-001",
            initial_message=body, idempotency_key=key,
        )["task_id"]

    task_a = create_task("p0-a", A_ONLY)
    task_b = create_task("p0-b", B_ONLY)
    assert task_a != task_b
    accepted = admit_task_message(
        db, owner, session_id=session_id, task_id=task_b, input_kind="CHAT_READONLY",
        body=QUESTION, idempotency_key="p0-b-followup",
    )
    claim_task_run(db, owner, accepted["run_id"])
    prepared = prepare_chat_attempt(db, accepted["run_id"], WORKER, "audit-fixture")
    with connect(db) as connection:
        selected = [
            dict(connection.execute(
                "SELECT message_id, task_id, sequence, body FROM messages WHERE message_id=?",
                (message_id,),
            ).fetchone())
            for message_id in prepared["selected_message_ids"]
        ]
    save("builder-context.json", {
        "session_id": session_id, "task_a": task_a, "task_b": task_b,
        "accepted": accepted, "selected_messages": selected, "messages": prepared["messages"],
    })
    contents = [message["content"] for message in prepared["messages"]]
    assert QUESTION in contents and any(B_ONLY in value for value in contents)
    assert all(A_ONLY not in value for value in contents), "A text was selected for B"


def test_sdk_wire_excludes_other_task_and_keeps_shared_history(tmp_path, monkeypatch):
    db = tmp_path / "domain.sqlite"
    reset_fixture(db, "S1_POS")
    prepare_s3_fixture(db, "DELIVERED_PENDING", order_id="p0-order", contract_version=2)
    epoch = register_worker_owner(db, WORKER, os.getpid())
    counts_before = protected_counts(db)
    monkeypatch.setenv("OPSPILOT_ASSISTANT_PROVIDER_ENABLED", "1")
    monkeypatch.setenv("OPSPILOT_ASSISTANT_EXPERIMENT_ID", "AR-02-LIVE-01")
    monkeypatch.setenv("OPSPILOT_MODEL_NAME", "deepseek-flash")
    monkeypatch.setenv("OPSPILOT_MODEL_API_KEY", "offline-fixture-key")
    monkeypatch.setenv("OPSPILOT_MODEL_BASE_URL", "https://api.deepseek.com")
    requests = []

    async def respond(request):
        requests.append(json.loads(await request.aread()))
        return httpx.Response(200, json={
            "id": "p0-offline-completion", "object": "chat.completion", "created": 1,
            "model": "deepseek-flash",
            "choices": [{
                "index": 0, "finish_reason": "stop",
                "message": {"role": "assistant", "content": "Offline fixture response."},
            }],
            "usage": {"prompt_tokens": 100, "completion_tokens": 5, "total_tokens": 105},
        })

    def reject_sync(_request):
        raise AssertionError("Unexpected sync dispatch in the offline run")

    def model_factory():
        return create_assistant_model(
            transport_async=httpx.MockTransport(respond),
            transport_sync=httpx.MockTransport(reject_sync),
        )

    origin = "http://p0-01.test"
    app = create_app(db_path=db, start_worker=False, expected_origin=origin,
                     credentials={"support-a": "p0-offline-password"})
    with TestClient(app) as client:
        login = client.post("/api/auth/login", headers={"Origin": origin},
                            json={"actor_id": "support-a", "password": "p0-offline-password"})
        assert login.status_code == 200
        headers = {"Origin": origin, "X-CSRF-Token": login.json()["csrf_token"]}
        session = client.post("/api/sessions", headers=headers)
        assert session.status_code == 201
        path = f"/api/sessions/{session.json()['session_id']}/assistant"

        def post(route, key, payload):
            response = client.post(path + route, json=payload,
                                   headers={**headers, "Idempotency-Key": key})
            assert response.status_code == 202, response.text
            return response.json()

        post("/messages", "p0-common", {"body": SHARED})
        task_a = post("/order", "p0-a", {"order_id": "p0-order", "initial_message": A_ONLY})
        task_b = post("/order", "p0-b", {"order_id": "p0-order", "initial_message": B_ONLY})
        assert task_a["task_id"] != task_b["task_id"]
        submitted = {"task_id": task_b["task_id"], "body": QUESTION}
        accepted = post("/messages", "p0-b-followup", submitted)

    with connect(db) as connection:
        run = dict(connection.execute(
            "SELECT * FROM task_runs WHERE run_id=?", (accepted["run_id"],)
        ).fetchone())
        source = dict(connection.execute(
            "SELECT message_id, task_id, sequence, body FROM messages WHERE message_id=?",
            (run["source_message_id"],),
        ).fetchone())
    assert run["task_id"] == source["task_id"] == submitted["task_id"]
    asyncio.run(_dispatch_run(
        db, tmp_path / "checkpoint.sqlite", WORKER, "executor-a", run, epoch,
        assistant_model_factory=model_factory,
    ))
    counts_after = protected_counts(db)
    with connect(db) as connection:
        status = dict(connection.execute(
            "SELECT status, blocked_reason FROM task_runs WHERE run_id=?", (run["run_id"],)
        ).fetchone())
        calls = connection.execute(
            "SELECT kind, status, request_json FROM assistant_calls WHERE run_id=? ORDER BY created_at",
            (run["run_id"],),
        ).fetchall()
    save("mock-sdk-wire.json", {
        "submitted_json": submitted, "accepted": accepted, "run_source_message": source,
        "status": status, "task_a": task_a["task_id"], "task_b": task_b["task_id"],
        "local_mock_requests": requests, "protected_before": counts_before,
        "protected_after": counts_after,
        "ledger": [{"kind": row["kind"], "status": row["status"],
                    "request": json.loads(row["request_json"])} for row in calls],
    })
    assert status == {"status": "SUCCEEDED", "blocked_reason": None}
    assert len(requests) == 1
    assert counts_before == counts_after
    text = [item["content"] for item in requests[0]["messages"]]
    assert all(any(marker in item for item in text) for marker in (SHARED, B_ONLY, QUESTION))
    assert all(A_ONLY not in item for item in text), "A text reached the serialized B request"
