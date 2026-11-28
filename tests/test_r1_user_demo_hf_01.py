"""Targeted offline regressions for the R1 user-demo trusted entry points."""
from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WEB_ORIGIN = "http://127.0.0.1:5173"
API_ORIGIN = "http://127.0.0.1:8000"
PASSWORDS = {"support-a": "r1-user-demo-offline-test-password"}


def test_user_demo_launcher_separates_browser_origin_from_api_upstream(demo_db):
    """The Vite page origin is trusted while the API remains only the proxy target."""
    from fastapi.testclient import TestClient
    from opspilot.web.app import create_app

    launcher = (ROOT / "scripts" / "user-demo" / "Start-UserDemo.ps1").read_text(encoding="utf-8")
    web_assignment = re.search(r"OPSPILOT_WEB_ORIGIN\s*=\s*'([^']+)'", launcher)
    api_assignment = re.search(r"OPSPILOT_API_ORIGIN\s*=\s*'([^']+)'", launcher)
    assert web_assignment and web_assignment.group(1) == WEB_ORIGIN
    assert api_assignment and api_assignment.group(1) == API_ORIGIN

    vite_config = (ROOT / "frontend" / "vite.config.ts").read_text(encoding="utf-8")
    assert "target: process.env.OPSPILOT_API_ORIGIN" in vite_config
    assert "port: 5173" in vite_config

    app = create_app(
        db_path=demo_db, start_worker=False, credentials=PASSWORDS,
        expected_origin=web_assignment.group(1),
    )
    with TestClient(app) as client:
        rejected_login = client.post(
            "/api/auth/login", headers={"Origin": API_ORIGIN},
            json={"actor_id": "support-a", "password": PASSWORDS["support-a"]},
        )
        assert rejected_login.status_code == 403
        assert rejected_login.json()["code"] == "ORIGIN_REJECTED"

        login = client.post(
            "/api/auth/login", headers={"Origin": WEB_ORIGIN},
            json={"actor_id": "support-a", "password": PASSWORDS["support-a"]},
        )
        assert login.status_code == 200, login.text
        headers = {"Origin": WEB_ORIGIN, "X-CSRF-Token": login.json()["csrf_token"]}

        rejected_session = client.post(
            "/api/sessions", headers={**headers, "Origin": API_ORIGIN},
        )
        assert rejected_session.status_code == 403

        created = client.post("/api/sessions", headers=headers)
        assert created.status_code in {200, 201}, created.text
        session_id = created.json()["session_id"]

        rejected_csrf = client.post(
            f"/api/sessions/{session_id}/assistant/messages",
            headers={**headers, "X-CSRF-Token": "wrong-csrf", "Idempotency-Key": "wrong-csrf"},
            json={"body": "Please explain HTTP 202."},
        )
        assert rejected_csrf.status_code == 403
        assert rejected_csrf.json()["code"] == "CSRF_REJECTED"

        rejected_message = client.post(
            f"/api/sessions/{session_id}/assistant/messages",
            headers={**headers, "Origin": API_ORIGIN, "Idempotency-Key": "wrong-origin"},
            json={"body": "Please explain HTTP 202."},
        )
        assert rejected_message.status_code == 403

        accepted_message = client.post(
            f"/api/sessions/{session_id}/assistant/messages",
            headers={**headers, "Idempotency-Key": "right-origin"},
            json={"body": "Please explain HTTP 202."},
        )
        assert accepted_message.status_code == 202, accepted_message.text


def _prepared_send(demo_db, worker, binding, run):
    from opspilot.domain.assistant import reserve
    from opspilot.domain.assistant_runtime_grant import reserve_dispatch, validate_http_request
    from opspilot.domain.d2 import digest_json

    request = {"model_id": "deepseek-flash", "messages": [{"role": "user", "content": "offline"}]}
    call, fresh = reserve(
        demo_db, run["run_id"], "MODEL", "hf01-send", request, worker.owner_id,
        runtime_recovery=True,
    )
    assert fresh
    dispatch = reserve_dispatch(
        demo_db, binding, call_id=call["call_id"], logical_key="hf01-send",
        request_digest=digest_json(request), worker_id=worker.owner_id,
    )
    body = (
        b'{"model":"deepseek-flash","messages":[{"role":"user","content":"offline"}],'
        b'"max_tokens":2048,"thinking":{"type":"disabled"},"stream":false}'
    )
    body_digest, output_cap = validate_http_request(
        "https://api.deepseek.com/chat/completions", "POST", body, binding,
    )
    return call, dispatch, request, body_digest, output_cap, digest_json(request)


def test_reserved_assistant_run_aborted_before_send_cannot_get_send_permit(demo_db, monkeypatch):
    """A durable reservation is not enough once TaskControl has aborted the Run."""
    import os

    import pytest

    from opspilot.domain.assistant_runtime_grant import (
        RuntimeGrantError, bind_run, claim_send, runtime_config_from_env,
    )
    from opspilot.domain.database import connect
    from opspilot.domain.task_control import (
        abort_task, claim_task_run, create_session, create_task_with_initial_run,
        trusted_identity,
    )

    from test_product_01_runtime_grant_01 import _configure, _provision, _worker
    from opspilot.domain.s3 import prepare_s3_fixture

    _configure(monkeypatch)
    _provision(demo_db, total=30_000)
    prepare_s3_fixture(demo_db, "PROCESSING", order_id="ar02-order", contract_version=2)
    worker = _worker(demo_db)
    try:
        identity = trusted_identity(demo_db, "support-a")
        session_id = create_session(demo_db, identity)["session_id"]
        created = create_task_with_initial_run(
            demo_db, identity, session_id=session_id, service_id="orders-async-demo",
            integration_id="async-integration-a", s3_order_id="ar02-order",
            ticket_id="HF01-ABORT-BEFORE-SEND", initial_message="Read-only callback check.",
            idempotency_key="hf01-abort-before-send", assistant_core=True,
        )
        claim_task_run(demo_db, identity, created["run_id"])
        run = {"run_id": created["run_id"], "session_id": session_id}
        binding = bind_run(demo_db, run["run_id"], runtime_config_from_env())
        call, dispatch, _, body_digest, output_cap, request_digest = _prepared_send(
            demo_db, worker, binding, run,
        )
        aborted = abort_task(
            demo_db, identity, task_id=created["task_id"], reason="user cancelled before send",
            idempotency_key="hf01-abort-before-send-command",
        )
        assert aborted["terminal_state"] == "ABORTED"

        with pytest.raises(RuntimeGrantError, match="TASK_ABORTED"):
            claim_send(
                demo_db, binding, call_id=call["call_id"], request_key=dispatch["request_key"],
                request_digest=request_digest, body_digest=body_digest,
                request_url="https://api.deepseek.com/chat/completions", method="POST",
                requested_max_output_tokens=output_cap, worker_id=worker.owner_id, worker_epoch=worker.epoch,
            )
        with connect(demo_db) as connection:
            status = connection.execute(
                "SELECT status FROM assistant_runtime_spends WHERE request_key=?",
                (dispatch["request_key"],),
            ).fetchone()[0]
        assert status == "RESERVED"
    finally:
        worker.release()


def test_stale_worker_epoch_cannot_get_provider_send_permit(demo_db, monkeypatch):
    """A worker superseded after reservation cannot make a new external send."""
    import os

    import pytest

    from opspilot.domain.assistant_runtime_grant import (
        RuntimeGrantError, bind_run, claim_send, runtime_config_from_env,
    )
    from opspilot.domain.task_control import register_worker_owner

    from test_product_01_runtime_grant_01 import _configure, _provision, _run, _worker

    _configure(monkeypatch)
    _provision(demo_db, total=30_000)
    worker = _worker(demo_db)
    try:
        run = _run(demo_db, "stale-worker-epoch", worker_id=worker.owner_id)
        binding = bind_run(demo_db, run["run_id"], runtime_config_from_env())
        call, dispatch, _, body_digest, output_cap, request_digest = _prepared_send(
            demo_db, worker, binding, run,
        )
        register_worker_owner(demo_db, worker.owner_id, os.getpid())

        with pytest.raises(RuntimeGrantError, match="WORKER_FENCE_STALE"):
            claim_send(
                demo_db, binding, call_id=call["call_id"], request_key=dispatch["request_key"],
                request_digest=request_digest, body_digest=body_digest,
                request_url="https://api.deepseek.com/chat/completions", method="POST",
                requested_max_output_tokens=output_cap, worker_id=worker.owner_id,
                worker_epoch=worker.epoch,
            )
    finally:
        worker.release()


def test_revoked_summary_is_removed_from_restored_graph_messages_but_tools_are_kept(
    demo_db, tmp_path, monkeypatch,
):
    """A checkpoint prefix is rebuilt from fresh Domain context on each dispatch."""
    import json
    import time
    from collections import deque

    from fastapi.testclient import TestClient
    from langchain_core.messages import AIMessage
    from langchain_core.outputs import ChatGeneration, ChatResult
    from pydantic import Field

    from test_ar04a_context_journey_01 import (
        LongSessionFixture, ORIGIN as HISTORY_ORIGIN, PASSWORDS as HISTORY_PASSWORDS,
        _chat_bodies, _login as history_login, _wait_run,
    )
    from opspilot.domain.database import connect
    from opspilot.web.app import create_app

    monkeypatch.setenv("OPSPILOT_CONTEXT_STRATEGY", "HYBRID")

    class RevokeSummaryOnFirstDispatch(LongSessionFixture):
        db_path: str
        source_message_id: str
        dispatch_count: int = 0
        checkpoint_messages: list = Field(default_factory=list)
        invalidated_summary: dict = Field(default_factory=dict)

        @property
        def _llm_type(self):
            return "R1_USER_DEMO_HF01_CHECKPOINT_FIXTURE"

        def _generate(self, messages, stop=None, run_manager=None, **kwargs):
            if self._compression_request(messages):
                return super()._generate(messages, stop=stop, run_manager=run_manager, **kwargs)
            self.dispatch_count += 1
            if self.dispatch_count == 1:
                assert any(
                    "HISTORICAL SESSION SUMMARY" in str(message.content)
                    for message in messages if hasattr(message, "content")
                ), "control: first dispatch should receive the currently valid summary"
                with connect(self.db_path) as connection:
                    summary = connection.execute(
                        "SELECT summary_id, summary_json, summary_digest FROM context_summaries "
                        "WHERE state='CURRENT' ORDER BY created_at DESC LIMIT 1"
                    ).fetchone()
                    assert summary is not None
                    self.invalidated_summary = dict(summary)
                    connection.execute(
                        "UPDATE messages SET body_digest=? WHERE message_id=?",
                        ("f" * 64, self.source_message_id),
                    )
                response = AIMessage(content="", tool_calls=[{
                    "name": "read_session_professional_outcomes", "args": {},
                    "id": "hf01-valid-current-tool-call", "type": "tool_call",
                }])
            else:
                from langchain_core.messages import messages_to_dict

                self.checkpoint_messages = messages_to_dict(messages)
                response = AIMessage(content="本轮只读取了同一会话中的专业结果；无新业务状态观察。")
            response.usage_metadata = {"input_tokens": 30, "output_tokens": 10, "total_tokens": 40}
            return ChatResult(generations=[ChatGeneration(message=response)])

    history_models = [LongSessionFixture(mode="s01", pad_tokens=150) for _ in range(7)]
    queue = deque(history_models)
    app = create_app(
        db_path=demo_db, checkpoint_db_path=tmp_path / "hf01-checkpoint.sqlite3",
        start_worker=True, credentials=HISTORY_PASSWORDS, expected_origin=HISTORY_ORIGIN,
        assistant_model_factory=lambda: queue.popleft(),
    )
    fixture = None
    with TestClient(app) as client:
        headers = history_login(client)
        session_id = client.post("/api/sessions", headers=headers).json()["session_id"]
        for index, body in enumerate(_chat_bodies(), start=1):
            accepted = client.post(
                f"/api/sessions/{session_id}/assistant/messages",
                headers={**headers, "Idempotency-Key": f"hf01-history-{index}"},
                json={"body": body},
            )
            assert accepted.status_code == 202, accepted.text
            assert _wait_run(client, accepted.json()["run_id"])["status"] == "SUCCEEDED"

        with connect(demo_db) as connection:
            summary = connection.execute(
                "SELECT summary_id, summary_json, summary_digest, covered_to_seq "
                "FROM context_summaries WHERE state='CURRENT' ORDER BY created_at DESC LIMIT 1"
            ).fetchone()
            assert summary is not None, "fixture must create a current summary before the new Run"
            source = connection.execute(
                "SELECT message_id FROM messages WHERE session_id=? AND role='USER' AND sequence<=? "
                "ORDER BY sequence LIMIT 1", (session_id, int(summary["covered_to_seq"])),
            ).fetchone()
            assert source is not None

        fixture = RevokeSummaryOnFirstDispatch(
            mode="s01", db_path=str(demo_db), source_message_id=str(source["message_id"]),
        )
        queue.append(fixture)
        accepted = client.post(
            f"/api/sessions/{session_id}/assistant/messages",
            headers={**headers, "Idempotency-Key": "hf01-checkpoint-revoke"},
            json={"body": "继续核对刚才讨论的事项。"},
        )
        assert accepted.status_code == 202, accepted.text
        run = _wait_run(client, accepted.json()["run_id"])
        assert run["status"] == "SUCCEEDED", run
        assert fixture.dispatch_count == 2

    checkpoint_text = json.dumps(fixture.checkpoint_messages, ensure_ascii=False)
    assert "hf01-valid-current-tool-call" in checkpoint_text
    assert "read_session_professional_outcomes" in checkpoint_text
    assert any(
        item.get("type") == "tool" and item.get("data", {}).get("tool_call_id")
        == "hf01-valid-current-tool-call"
        for item in fixture.checkpoint_messages
    ), "current Run ToolMessage must retain its tool_call_id"
    assert fixture.invalidated_summary
    assert str(fixture.invalidated_summary["summary_id"]) not in checkpoint_text
    assert str(fixture.invalidated_summary["summary_digest"]) not in checkpoint_text
    assert "HISTORICAL SESSION SUMMARY" not in checkpoint_text
    assert json.dumps(json.loads(str(fixture.invalidated_summary["summary_json"])), ensure_ascii=False) not in checkpoint_text
