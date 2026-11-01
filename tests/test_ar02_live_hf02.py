"""Free HF-02 checks: exact SDK wire path, local connection fault, and failure closure."""

from __future__ import annotations

import asyncio
import json
import os

import httpx
import pytest
from langchain_core.messages import HumanMessage


_KNOWLEDGE_TOOL = {
    "type": "function",
    "function": {
        "name": "search_project_knowledge",
        "description": "Search the authorized Session document scope.",
        "parameters": {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
    },
}


def _mock_assistant_model(monkeypatch, handler, base_url="https://api.deepseek.com"):
    from opspilot.assistant import create_assistant_model

    monkeypatch.setenv("OPSPILOT_ASSISTANT_PROVIDER_ENABLED", "1")
    monkeypatch.setenv("OPSPILOT_ASSISTANT_EXPERIMENT_ID", "AR-02-LIVE-01")
    monkeypatch.setenv("OPSPILOT_MODEL_API_KEY", "HF02-LOCAL-MOCK-ONLY")
    monkeypatch.setenv("OPSPILOT_MODEL_NAME", "deepseek-flash")
    monkeypatch.setenv("OPSPILOT_MODEL_BASE_URL", base_url)
    captured = []

    async def capture(request):
        body = json.loads((await request.aread()).decode("utf-8"))
        captured.append({
            "method": request.method,
            "url": str(request.url),
            "path": request.url.path,
            "host": request.url.host,
            "authorization_present": bool(request.headers.get("authorization")),
            "body": body,
        })
        return await handler(request, body)

    async_transport = httpx.MockTransport(capture)
    sync_transport = httpx.MockTransport(
        lambda request: httpx.Response(500, request=request)
    )
    model = create_assistant_model(
        transport_async=async_transport,
        transport_sync=sync_transport,
    )
    return model, model.http_async_client, model.http_client, captured


def _mock_success(response_module=httpx):
    return response_module.Response(
        200,
        json={
            "id": "hf02-mock-completion",
            "object": "chat.completion",
            "created": 1,
            "model": "deepseek-flash",
            "choices": [{
                "index": 0,
                "message": {"role": "assistant", "content": "local mock only"},
                "finish_reason": "stop",
            }],
            "usage": {"prompt_tokens": 4, "completion_tokens": 3, "total_tokens": 7},
        },
    )


@pytest.mark.parametrize(
    ("base_url", "expected_path"),
    [
        ("https://api.deepseek.com", "/chat/completions"),
        ("https://api.deepseek.com/v1", "/v1/chat/completions"),
    ],
)
def test_locked_openai_sdk_posts_to_observed_base_url_path(monkeypatch, base_url, expected_path):
    async def respond(_request, _body):
        return _mock_success()

    model, async_client, sync_client, captured = _mock_assistant_model(monkeypatch, respond, base_url)

    async def invoke():
        try:
            answer = await model.bind_tools([_KNOWLEDGE_TOOL], tool_choice="auto", parallel_tool_calls=False).ainvoke(
                [HumanMessage(content="local request path check")]
            )
            assert answer.content == "local mock only"
        finally:
            await async_client.aclose()
            sync_client.close()

    asyncio.run(invoke())
    assert len(captured) == 1
    wire = captured[0]
    assert wire["method"] == "POST"
    assert wire["host"] == "api.deepseek.com"
    assert wire["path"] == expected_path
    assert wire["authorization_present"] is True
    assert wire["body"]["model"] == "deepseek-flash"
    assert wire["body"]["max_tokens"] == 2048
    assert wire["body"]["thinking"] == {"type": "disabled"}
    assert wire["body"]["tool_choice"] == "auto"
    assert wire["body"]["parallel_tool_calls"] is False
    assert wire["body"]["tools"][0]["function"]["name"] == "search_project_knowledge"
    print("HF02_SDK_WIRE=" + json.dumps(wire, sort_keys=True, separators=(",", ":")))


def test_mock_transport_connection_error_exposes_sdk_to_httpx_cause_chain(monkeypatch):
    async def fail(request, _body):
        raise httpx.ConnectError("HF02_LOCAL_CONNECT_FAILURE", request=request)

    model, async_client, sync_client, captured = _mock_assistant_model(monkeypatch, fail)

    async def invoke():
        try:
            with pytest.raises(Exception) as caught:
                await model.bind_tools([_KNOWLEDGE_TOOL], tool_choice="auto", parallel_tool_calls=False).ainvoke(
                    [HumanMessage(content="local failure injection")]
                )
            chain = []
            current = caught.value
            while current is not None and len(chain) < 8:
                chain.append(type(current).__name__)
                current = current.__cause__ or current.__context__
            assert "ConnectError" in chain
            print("HF02_LOCAL_FAILURE=" + json.dumps({
                "phase": "httpx.MockTransport handler before any response",
                "host": captured[0]["host"],
                "path": captured[0]["path"],
                "method": captured[0]["method"],
                "http_response": "NONE",
                "exception_type_chain": chain,
                "authorization_present": captured[0]["authorization_present"],
            }, sort_keys=True))
        finally:
            await async_client.aclose()
            sync_client.close()

    asyncio.run(invoke())


def test_formal_factory_uses_explicit_offline_httpx_clients(monkeypatch):
    from opspilot.assistant import create_assistant_model

    monkeypatch.setenv("OPSPILOT_ASSISTANT_PROVIDER_ENABLED", "1")
    monkeypatch.setenv("OPSPILOT_ASSISTANT_EXPERIMENT_ID", "AR-02-LIVE-01")
    monkeypatch.setenv("OPSPILOT_MODEL_API_KEY", "HF02-LOCAL-MOCK-ONLY")
    monkeypatch.setenv("OPSPILOT_MODEL_NAME", "deepseek-flash")
    monkeypatch.setenv("OPSPILOT_MODEL_BASE_URL", "https://api.deepseek.com/v1")

    async_transport = httpx.MockTransport(lambda request: httpx.Response(500, request=request))
    sync_transport = httpx.MockTransport(lambda request: httpx.Response(500, request=request))
    model = create_assistant_model(
        transport_async=async_transport,
        transport_sync=sync_transport,
    )
    try:
        assert isinstance(model.http_async_client, httpx.AsyncClient)
        assert isinstance(model.http_client, httpx.Client)
        assert model.http_async_client._transport is async_transport
        assert model.http_client._transport is sync_transport
        assert model.http_async_client.trust_env is False
        assert model.http_async_client.follow_redirects is False
        assert model.http_client.trust_env is False
        assert model.http_client.follow_redirects is False
        print("HF02_DEFAULT_TRANSPORT=" + json.dumps({
            "async_client_type": type(model.http_async_client).__module__ + "." + type(model.http_async_client).__name__,
            "sync_client_type": type(model.http_client).__module__ + "." + type(model.http_client).__name__,
            "explicit_async_transport": True,
            "explicit_sync_transport": True,
            "trust_env": False,
            "follow_redirects": False,
        }, sort_keys=True))
    finally:
        asyncio.run(model.http_async_client.aclose())
        model.http_client.close()

def test_explicit_transport_captures_v1_path(monkeypatch):
    async def respond(_request, _body):
        return _mock_success()

    model, async_client, sync_client, captured = _mock_assistant_model(
        monkeypatch,
        respond,
        base_url="https://api.deepseek.com/v1",
    )

    async def invoke():
        try:
            answer = await model.bind_tools([_KNOWLEDGE_TOOL], tool_choice="auto", parallel_tool_calls=False).ainvoke(
                [HumanMessage(content="locked default transport local request")]
            )
            assert answer.content == "local mock only"
        finally:
            await async_client.aclose()
            sync_client.close()

    asyncio.run(invoke())
    wire = captured[0]
    assert len(captured) == 1
    assert wire["method"] == "POST"
    assert wire["url"] == "https://api.deepseek.com/v1/chat/completions"
    assert wire["path"] == "/v1/chat/completions"
    assert wire["body"]["model"] == "deepseek-flash"
    assert wire["body"]["max_tokens"] == 2048
    assert wire["body"]["thinking"] == {"type": "disabled"}
    assert wire["body"]["tool_choice"] == "auto"
    assert wire["body"]["parallel_tool_calls"] is False
    print("HF02_EXPLICIT_HTTPX_SDK_WIRE=" + json.dumps(wire, sort_keys=True, separators=(",", ":")))


def test_explicit_httpx_connection_error_chain_is_local(monkeypatch):
    async def fail(request, _body):
        raise httpx.ConnectError("HF02_LOCAL_HTTPX_CONNECT_FAILURE", request=request)

    model, async_client, sync_client, captured = _mock_assistant_model(
        monkeypatch,
        fail,
        base_url="https://api.deepseek.com/v1",
    )

    async def invoke():
        try:
            with pytest.raises(Exception) as caught:
                await model.bind_tools([_KNOWLEDGE_TOOL], tool_choice="auto", parallel_tool_calls=False).ainvoke(
                    [HumanMessage(content="local httpx failure injection")]
                )
            chain = []
            current = caught.value
            while current is not None and len(chain) < 8:
                chain.append(type(current).__name__)
                current = current.__cause__ or current.__context__
            assert "ConnectError" in chain
            print("HF02_EXPLICIT_HTTPX_LOCAL_FAILURE=" + json.dumps({
                "phase": "httpx.MockTransport handler before any response",
                "host": captured[0]["host"],
                "path": captured[0]["path"],
                "method": captured[0]["method"],
                "http_response": "NONE",
                "exception_type_chain": chain,
            }, sort_keys=True))
        finally:
            await async_client.aclose()
            sync_client.close()

    asyncio.run(invoke())


def test_assistant_connection_failure_closes_attempt_and_keeps_unknown_reservation(
    demo_db, tmp_path, monkeypatch
):
    from fastapi.testclient import TestClient

    from opspilot.assistant import run_assistant
    from opspilot.domain.assistant_experiment import EXPERIMENT_ID, read_budget
    from opspilot.domain.database import connect
    from opspilot.domain.task_control import (
        admit_task_message,
        claim_task_run,
        create_session,
        register_worker_owner,
        trusted_identity,
    )
    from opspilot.web.app import create_app

    async def fail(request, _body):
        raise httpx.ConnectError("HF02_LOCAL_CONNECT_FAILURE", request=request)

    model, async_client, sync_client, captured = _mock_assistant_model(
        monkeypatch, fail, base_url="https://api.deepseek.com/v1"
    )
    identity = trusted_identity(demo_db, "support-a")
    session_id = create_session(demo_db, identity)["session_id"]
    accepted = admit_task_message(
        demo_db,
        identity,
        session_id=session_id,
        task_id=None,
        input_kind="CHAT_READONLY",
        body="解释 HTTP 202，但不要读取订单事实。",
        idempotency_key="hf02-local-connect-failure",
        assistant_core=True,
    )
    worker_id = "ar02-hf02-worker"
    register_worker_owner(demo_db, worker_id, os.getpid())
    claim_task_run(demo_db, identity, accepted["run_id"])
    events = []

    async def execute():
        try:
            return await run_assistant(
                demo_db,
                tmp_path / "hf02-checkpoint.sqlite3",
                worker_id,
                accepted["run_id"],
                model=model,
                trace=lambda event, **values: events.append({"event": event, **values}),
                experiment_id=EXPERIMENT_ID,
            )
        finally:
            await async_client.aclose()
            sync_client.close()

    result = asyncio.run(execute())
    assert result["status"] == "NOT_COMPLETED"
    assert len(captured) == 1

    with connect(demo_db) as connection:
        run = connection.execute(
            "SELECT status, blocked_reason, ended_at FROM task_runs WHERE run_id=?",
            (accepted["run_id"],),
        ).fetchone()
        attempt = connection.execute(
            "SELECT attempt_id, run_id, status, error_class, completed_at FROM chat_attempts WHERE run_id=?",
            (accepted["run_id"],),
        ).fetchone()
        dispatches = connection.execute(
            "SELECT dispatch_id, status, reserved_usd_micro, settled_usd_micro, error_code FROM ar02_live_dispatches WHERE run_id=?",
            (accepted["run_id"],),
        ).fetchall()
        answer_count = connection.execute(
            "SELECT COUNT(*) FROM chat_run_answers WHERE run_id=?", (accepted["run_id"],)
        ).fetchone()[0]
        notices = connection.execute(
            "SELECT message_id, body, command_id FROM messages WHERE session_id=? AND command_id=?",
            (session_id, "budget-notice:" + accepted["run_id"]),
        ).fetchall()

    # These assertions intentionally fail on the original HF-02 baseline:
    # run_assistant() marks the Run FAILED but leaves its Chat Attempt STREAMING.
    assert run["status"] == "FAILED"
    assert attempt["status"] == "FAILED"
    assert attempt["run_id"] == accepted["run_id"]
    assert attempt["error_class"] in {"OpenAIConnectionError", "APIConnectionError"}
    assert attempt["completed_at"] == run["ended_at"]
    assert run["blocked_reason"].startswith("ASSISTANT_STOP:")
    assert len(dispatches) == 1
    assert dispatches[0]["status"] == "UNKNOWN"
    assert dispatches[0]["reserved_usd_micro"] == 645_600
    assert dispatches[0]["settled_usd_micro"] == 0
    assert dispatches[0]["error_code"] == attempt["error_class"]
    assert answer_count == 0
    assert len(notices) == 1
    assert "模型服务连接失败" in notices[0]["body"]
    assert "未完成" in notices[0]["body"]
    assert "ASSISTANT_STOP" not in notices[0]["body"]
    assert "OpenAIConnectionError" not in notices[0]["body"]

    budget = read_budget(demo_db, EXPERIMENT_ID)
    assert budget["provider_used"] == 1
    assert budget["usd_reserved_micro"] == 645_600
    assert budget["usd_settled_micro"] == 0

    # Read through the existing API contract: the notice is a program result,
    # not a model-generated chat answer.
    from test_ar02_assistant import ORIGIN, PASSWORDS

    app = create_app(db_path=demo_db, start_worker=False, credentials=PASSWORDS, expected_origin=ORIGIN)
    with TestClient(app) as api:
        login = api.post(
            "/api/auth/login",
            headers={"Origin": ORIGIN},
            json={"actor_id": "support-a", "password": PASSWORDS["support-a"]},
        )
        headers = {"Origin": ORIGIN, "X-CSRF-Token": login.json()["csrf_token"]}
        response = api.get(f"/api/sessions/{session_id}/messages", headers=headers)
    assert response.status_code == 200, response.text
    program = next(item for item in response.json()["items"] if item["message_id"] == notices[0]["message_id"])
    assert program["answer_kind"] == "PROGRAM_LIMIT"
    assert program["answer_run_id"] == accepted["run_id"]

    # Replaying failure closure must not make a new dispatch, notice, or answer.
    from opspilot.domain.chat import fail_chat_attempt

    replay = fail_chat_attempt(
        demo_db,
        worker_id,
        attempt["attempt_id"],
        attempt["error_class"],
        terminal_reason=run["blocked_reason"],
    )
    assert replay["status"] == "FAILED"
    duplicate_message = admit_task_message(
        demo_db,
        identity,
        session_id=session_id,
        task_id=None,
        input_kind="CHAT_READONLY",
        body="解释 HTTP 202，但不要读取订单事实。",
        idempotency_key="hf02-local-connect-failure",
        assistant_core=True,
    )
    assert duplicate_message["message_id"] == accepted["message_id"]
    assert duplicate_message["run_id"] == accepted["run_id"]
    assert len(captured) == 1
    with connect(demo_db) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM ar02_live_dispatches WHERE run_id=?", (accepted["run_id"],)
        ).fetchone()[0] == 1
        assert connection.execute(
            "SELECT COUNT(*) FROM messages WHERE session_id=? AND command_id=?",
            (session_id, "budget-notice:" + accepted["run_id"]),
        ).fetchone()[0] == 1
        assert connection.execute(
            "SELECT COUNT(*) FROM chat_run_answers WHERE run_id=?", (accepted["run_id"],)
        ).fetchone()[0] == 0
        outbox_counts = dict(connection.execute(
            "SELECT event_kind,COUNT(*) FROM domain_outbox WHERE source_id IN (?,?) GROUP BY event_kind",
            (accepted["run_id"], attempt["attempt_id"]),
        ).fetchall())
    assert outbox_counts == {
        "CHAT_ATTEMPT_FAILED": 1,
        "CHAT_BUDGET_STOP": 1,
        "RUN_STATUS_FAILED": 1,
    }
    print("HF02_RUNTIME_TRACE=" + json.dumps({
        "run_id": accepted["run_id"],
        "attempt_id": attempt["attempt_id"],
        "dispatch_id": dispatches[0]["dispatch_id"],
        "sdk_wire": {key: captured[0][key] for key in ("method", "url", "path", "authorization_present")},
        "result": {"run": run["status"], "attempt": attempt["status"], "dispatch": dispatches[0]["status"]},
        "reservation_usd_micro": dispatches[0]["reserved_usd_micro"],
        "settled_usd_micro": dispatches[0]["settled_usd_micro"],
        "answer_kind": program["answer_kind"],
        "user_message_id": program["message_id"],
        "program_notice_body": program["body"],
        "answer_run_id": program["answer_run_id"],
        "model_answer_count": answer_count,
    }, sort_keys=True))
