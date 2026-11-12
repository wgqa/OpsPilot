"""Offline regressions for live memory recall and Assistant streaming UX."""
from __future__ import annotations

import asyncio
import json
import threading
import time

import httpx
import pytest
from fastapi.testclient import TestClient

from opspilot.domain.database import connect


ORIGIN = "http://c01-b2-live-hf01-local"
PASSWORDS = {"support-a": "hf01-fixture-a", "support-b": "hf01-fixture-b", "approver-a": "hf01-fixture-approver"}


def _configure_runtime(monkeypatch):
    from test_product_01_runtime_grant_01 import MODEL_CONFIG, _configure

    _configure(monkeypatch)
    monkeypatch.setenv("OPSPILOT_ASSISTANT_RUNTIME_ENABLED", "1")
    monkeypatch.setenv("OPSPILOT_ASSISTANT_PROVIDER_ENABLED", "1")
    monkeypatch.setenv("OPSPILOT_MODEL_API_KEY", "fixture-only-not-a-real-key")
    monkeypatch.delenv("OPSPILOT_ASSISTANT_EXPERIMENT_ID", raising=False)
    return MODEL_CONFIG


def _login(client: TestClient, actor_id="support-a"):
    response = client.post(
        "/api/auth/login", headers={"Origin": ORIGIN},
        json={"actor_id": actor_id, "password": PASSWORDS[actor_id]},
    )
    assert response.status_code == 200, response.text
    return {"Origin": ORIGIN, "X-CSRF-Token": response.json()["csrf_token"]}


def _wait_run(client: TestClient, run_id: str, timeout=25):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = client.get(f"/api/runs/{run_id}")
        assert result.status_code == 200, result.text
        run = result.json()
        if run["status"] in {"SUCCEEDED", "FAILED", "BLOCKED", "CANCELLED", "INTERRUPTED_RECOVERABLE"}:
            return run
        time.sleep(0.025)
    raise AssertionError(f"Run did not finish: {run_id}")


def _sse(payload: dict) -> bytes:
    return b"data: " + json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode() + b"\n\n"


def _chunk(*, delta: dict, finish_reason=None, choices=True, usage=None, identity="hf01-stream") -> bytes:
    return _sse({
        "id": identity, "object": "chat.completion.chunk", "created": 1,
        "model": "deepseek-flash",
        "choices": ([{"index": 0, "delta": delta, "finish_reason": finish_reason}] if choices else []),
        **({"usage": usage} if usage is not None else {}),
    })


class _GatedProviderStream(httpx.AsyncByteStream):
    def __init__(self, second: threading.Event, first_sent: threading.Event, third_sent: threading.Event):
        self.second = second
        self.first_sent = first_sent
        self.third_sent = third_sent

    async def __aiter__(self):
        yield _chunk(delta={"role": "assistant", "content": "第一段 "})
        self.first_sent.set()
        if not await asyncio.to_thread(self.second.wait, 10):
            raise RuntimeError("FIXTURE_STREAM_GATE_TIMEOUT")
        yield _chunk(delta={"content": "第二段 "})
        self.third_sent.set()
        yield _chunk(delta={"content": "第三段。"})
        yield _chunk(delta={}, finish_reason="stop")
        yield _chunk(delta={}, choices=False, usage={"prompt_tokens": 40, "completion_tokens": 9, "total_tokens": 49})
        yield b"data: [DONE]\n\n"

    async def aclose(self):
        return None


class _SSEProviderStream(httpx.AsyncByteStream):
    def __init__(self, parts: list[bytes]):
        self.parts = parts

    async def __aiter__(self):
        for part in self.parts:
            yield part

    async def aclose(self):
        return None


class _IncompleteProviderStream(httpx.AsyncByteStream):
    def __init__(self, *, missing_usage: bool):
        self.missing_usage = missing_usage

    async def __aiter__(self):
        yield _chunk(delta={"role": "assistant", "content": "这是未完成的草稿"}, identity="hf01-incomplete")
        if self.missing_usage:
            yield _chunk(delta={}, finish_reason="stop", identity="hf01-incomplete")
            yield b"data: [DONE]\n\n"
            return
        raise httpx.ReadError("fixture provider stream ended before [DONE]")

    async def aclose(self):
        return None


def _provision_runtime(db_path):
    from test_product_01_runtime_grant_01 import _provision

    return _provision(db_path, total=200_000)


def test_bounded_profile_is_available_for_model_judgment_and_still_excludes_invalid_memory(demo_db):
    from opspilot.domain.semantic_memory import (
        get_personal_memory_settings, list_personal_memories, personal_memory_context,
        personal_memory_recall_setting, remember_personal_memory, revoke_personal_memory,
        set_personal_memory_recall,
    )
    from opspilot.domain.personal_memory_consolidation import _validated_proposal
    from opspilot.domain.task_control import admit_task_message, create_session, trusted_identity

    actor = trusted_identity(demo_db, "support-a")
    session_id = create_session(demo_db, actor)["session_id"]
    source_ids = []
    messages = [
        "请记住我的个人学习习惯：学习技术时先理解原理与执行流程，再看代码。",
        "请记住我的系统设计偏好：学习系统设计时先分析技术选型和取舍。",
    ]
    for index, text in enumerate(messages):
        saved = admit_task_message(
            demo_db, actor, session_id=session_id, task_id=None, input_kind="CHAT_READONLY",
            body=text, idempotency_key=f"hf01-memory-source-{index}", assistant_core=True,
        )
        source_ids.append(saved["message_id"])

    global_memory = remember_personal_memory(
        demo_db, actor.tenant_id, actor.actor_id, memory_kind="WORK_HABIT", memory_mode="RELEVANT",
        memory_key="learning.workflow", content="学习技术时先理解原理与执行流程，再看代码。",
        source_message_id=source_ids[0], idempotency_key="hf01-global-learning-memory",
    )
    topic_memory = remember_personal_memory(
        demo_db, actor.tenant_id, actor.actor_id, memory_kind="PREFERENCE", memory_mode="RELEVANT",
        memory_key="learning.system-design", content="学习系统设计时先分析技术选型和取舍。",
        source_message_id=source_ids[1], idempotency_key="hf01-topic-memory",
    )
    assert global_memory["saved"] is True and topic_memory["saved"] is True
    current_records = {item["memory_id"]: item for item in list_personal_memories(
        demo_db, actor.tenant_id, actor.actor_id, state="ACTIVE",
    )}
    assert current_records[global_memory["memory_id"]]["state"] == "ACTIVE"
    assert current_records[topic_memory["memory_id"]]["state"] == "ACTIVE"

    sources = {"global": {"message_id": "global", "text": messages[0]}}
    proposal = {
        "action": "ADD", "memory_kind": "WORK_HABIT", "memory_mode": "RELEVANT",
        "memory_key": "learning.workflow", "content": "学习技术时先理解原理与执行流程，再看代码。",
        "source_quotes": [{"message_id": "global", "quote": "学习技术时先理解原理与执行流程，再看代码"}],
    }
    assert _validated_proposal(proposal, sources)["memory_mode"] == "PINNED"
    one_time = {**proposal, "source_quotes": [{"message_id": "global", "quote": "这次学习技术时先理解原理与执行流程，再看代码"}]}
    assert _validated_proposal(one_time, sources) is None

    def selected(query):
        with connect(demo_db) as connection:
            setting = personal_memory_recall_setting(connection, actor.tenant_id, actor.actor_id)
            return personal_memory_context(
                connection, actor.tenant_id, actor.actor_id, query,
                recall_enabled=setting["recall_enabled"],
            )[0]

    for query in (
        "详细解释一下 LangGraph Checkpoint 的底层工作机制。",
        "我在学习新技术 LangGraph，能介绍一下 Checkpoint 吗？",
        "今天北京天气怎么样？",
    ):
        chosen = selected(query)
        assert {item["memory_id"] for item in chosen} == {
            global_memory["memory_id"], topic_memory["memory_id"],
        }
        assert all(item["selection_reason"] == "USER_CONFIRMED_STABLE_PREFERENCE" for item in chosen)

    # The same existing owner, expiry, revocation and toggle guards still apply.
    set_personal_memory_recall(demo_db, actor.tenant_id, actor.actor_id, recall_enabled=False)
    assert selected("我在学习新技术 LangGraph，能介绍一下 Checkpoint 吗？") == []
    set_personal_memory_recall(demo_db, actor.tenant_id, actor.actor_id, recall_enabled=True)
    assert get_personal_memory_settings(demo_db, actor.tenant_id, actor.actor_id)["recall_enabled"] is True
    revoke_personal_memory(
        demo_db, actor.tenant_id, global_memory["memory_id"], actor.actor_id,
        idempotency_key="hf01-revoke-global",
    )
    assert all(item["memory_id"] != global_memory["memory_id"] for item in selected("学习新技术 LangGraph Checkpoint"))
    with connect(demo_db) as connection:
        connection.execute(
            "UPDATE personal_memories SET expires_at='2000-01-01T00:00:00+00:00' WHERE memory_id=?",
            (topic_memory["memory_id"],),
        )
    assert all(item["memory_id"] != topic_memory["memory_id"] for item in selected("学习系统设计时先分析技术选型和取舍"))

    other = trusted_identity(demo_db, "support-b")
    with connect(demo_db) as connection:
        assert personal_memory_context(connection, other.tenant_id, other.actor_id, "学习新技术 LangGraph Checkpoint")[0] == []


def test_assistant_v1_streams_real_provider_deltas_before_stream_completion(demo_db, tmp_path, monkeypatch):
    from opspilot.assistant import create_assistant_model
    from opspilot.domain.assistant_runtime_grant import spend_summary
    from opspilot.web.app import create_app

    _configure_runtime(monkeypatch)
    _provision_runtime(demo_db)
    first_sent, third_sent, release = threading.Event(), threading.Event(), threading.Event()
    sent = []

    async def respond(request):
        body = json.loads((await request.aread()).decode())
        sent.append(body)
        assert body["stream"] is True
        assert body["stream_options"]["include_usage"] is True
        return httpx.Response(
            200, headers={"content-type": "text/event-stream", "x-request-id": "hf01-stream-request"},
            stream=_GatedProviderStream(release, first_sent, third_sent), request=request,
        )

    app = create_app(
        db_path=demo_db, checkpoint_db_path=tmp_path / "stream-checkpoint.sqlite3",
        start_worker=True, credentials=PASSWORDS, expected_origin=ORIGIN,
        assistant_runtime_enabled=True, assistant_streaming_enabled=True,
        assistant_model_factory=lambda *, runtime_grant_binding: create_assistant_model(
            runtime_grant_binding=runtime_grant_binding,
            transport_async=httpx.MockTransport(respond),
            transport_sync=httpx.MockTransport(lambda request: httpx.Response(500, request=request)),
        ),
    )
    try:
        with TestClient(app) as client:
            headers = _login(client)
            session_id = client.post("/api/sessions", headers=headers).json()["session_id"]
            accepted = client.post(
                f"/api/sessions/{session_id}/assistant/messages",
                headers={**headers, "Idempotency-Key": "hf01-stream-question"},
                json={"body": "逐步说明这个本地流式测试。"},
            )
            assert accepted.status_code == 202, accepted.text
            run_id = accepted.json()["run_id"]
            assert first_sent.wait(8), "Provider did not yield its first real delta"
            deadline = time.monotonic() + 8
            visible = []
            history = []
            chunk_event = None
            while time.monotonic() < deadline:
                history = client.get(f"/api/sessions/{session_id}/events/history?after=0").json()["items"]
                chunk_event = next((item for item in history if item["event_kind"] == "CHAT_CHUNK_AVAILABLE"), None)
                response = client.get(f"/api/runs/{run_id}/chunks?after_seq=0")
                assert response.status_code == 200, response.text
                visible = response.json()["items"]
                if visible and chunk_event:
                    break
                time.sleep(0.025)
            assert visible and chunk_event and "第一段 " in "".join(item["body"] for item in visible)
            assert not third_sent.is_set(), "All Provider deltas arrived before the first chunk was observable"
            reconnected = client.get(
                f"/api/sessions/{session_id}/events/history?after={chunk_event['event_seq']}",
            ).json()["items"]
            assert all(item["event_seq"] > chunk_event["event_seq"] for item in reconnected)
            assert client.get(f"/api/runs/{run_id}/activity").status_code == 200
            release.set()
            run = _wait_run(client, run_id)
            assert run["status"] == "SUCCEEDED", run
            chunks = client.get(f"/api/runs/{run_id}/chunks?after_seq=0").json()["items"]
            messages = client.get(f"/api/sessions/{session_id}/messages").json()["items"]
            final_answers = [item for item in messages if item["role"] == "ASSISTANT"]
            assert len(final_answers) == 1
            assert "".join(item["body"] for item in chunks) == final_answers[0]["body"] == "第一段 第二段 第三段。"
            activity = client.get(f"/api/runs/{run_id}/activity").json()["items"]
            stages = [item["payload"]["stage"] for item in activity]
            assert "PREPARING_CONTEXT" in stages and "MODEL_REQUESTING" in stages
            assert "MODEL_STREAMING" in stages and "SAVING_ANSWER" in stages
    finally:
        release.set()

    assert len(sent) == 1
    spend = spend_summary(demo_db)
    assert spend["status"] == "ACTIVE"
    assert spend["committed_or_reserved_usd_micro"] == 49
    with connect(demo_db) as connection:
        ledger = connection.execute("SELECT status,usage_json FROM assistant_runtime_spends").fetchone()
        assert ledger["status"] == "DELIVERED"
        assert json.loads(ledger["usage_json"]) == {"input_tokens": 40, "output_tokens": 9, "total_tokens": 49}


def test_assistant_v1_streaming_preserves_mcp_call_and_records_tool_activity(demo_db, tmp_path, monkeypatch):
    from opspilot.assistant import create_assistant_model
    from opspilot.domain.assistant_runtime_grant import spend_summary
    from opspilot.web.app import create_app

    _configure_runtime(monkeypatch)
    _provision_runtime(demo_db)
    bodies = []

    def tool_call_parts():
        return [
            _chunk(delta={"role": "assistant", "tool_calls": [{"index": 0, "id": "hf01-mcp-call", "type": "function", "function": {"name": "list_scoped_protocol_documents", "arguments": ""}}]}, identity="hf01-tool"),
            _chunk(delta={"tool_calls": [{"index": 0, "function": {"arguments": '{"topic":"callbacks"}'}}]}, identity="hf01-tool"),
            _chunk(delta={}, finish_reason="tool_calls", identity="hf01-tool"),
            _chunk(delta={}, choices=False, usage={"prompt_tokens": 35, "completion_tokens": 7, "total_tokens": 42}, identity="hf01-tool"),
            b"data: [DONE]\n\n",
        ]

    def final_parts():
        return [
            _chunk(delta={"role": "assistant", "content": "已查询授权的协议目录；没有业务状态或操作被改变。"}, identity="hf01-final"),
            _chunk(delta={}, finish_reason="stop", identity="hf01-final"),
            _chunk(delta={}, choices=False, usage={"prompt_tokens": 55, "completion_tokens": 14, "total_tokens": 69}, identity="hf01-final"),
            b"data: [DONE]\n\n",
        ]

    async def respond(request):
        body = json.loads((await request.aread()).decode())
        bodies.append(body)
        stream = tool_call_parts() if len(bodies) == 1 else final_parts()
        return httpx.Response(200, headers={"content-type": "text/event-stream"}, stream=_SSEProviderStream(stream), request=request)

    app = create_app(
        db_path=demo_db, checkpoint_db_path=tmp_path / "stream-tool-checkpoint.sqlite3",
        start_worker=True, credentials=PASSWORDS, expected_origin=ORIGIN,
        assistant_runtime_enabled=True, assistant_streaming_enabled=True,
        assistant_model_factory=lambda *, runtime_grant_binding: create_assistant_model(
            runtime_grant_binding=runtime_grant_binding,
            transport_async=httpx.MockTransport(respond),
            transport_sync=httpx.MockTransport(lambda request: httpx.Response(500, request=request)),
        ),
    )
    with TestClient(app) as client:
        headers = _login(client)
        session_id = client.post("/api/sessions", headers=headers).json()["session_id"]
        accepted = client.post(
            f"/api/sessions/{session_id}/assistant/messages",
            headers={**headers, "Idempotency-Key": "hf01-stream-tool-question"},
            json={"body": "查询允许访问的协议目录，并说明业务状态是否改变。"},
        )
        assert accepted.status_code == 202, accepted.text
        run_id = accepted.json()["run_id"]
        run = _wait_run(client, run_id)
        assert run["status"] == "SUCCEEDED", run
        activity = client.get(f"/api/runs/{run_id}/activity").json()["items"]
        tool_events = [item["payload"] for item in activity if item["payload"]["stage"] in {"TOOL_RUNNING", "TOOL_COMPLETED"}]
        assert any(item["stage"] == "TOOL_RUNNING" and item["tool_name"] == "list_scoped_protocol_documents" for item in tool_events)
        assert any(item["stage"] == "TOOL_COMPLETED" and item["activity_status"] == "SUCCEEDED" for item in tool_events)
        assert [item["stream"] for item in bodies] == [True, True]
        messages = client.get(f"/api/sessions/{session_id}/messages").json()["items"]
        final_answers = [item for item in messages if item["role"] == "ASSISTANT"]
        assert len(final_answers) == 1 and "业务状态或操作被改变" in final_answers[0]["body"]

    assert len(bodies) == 2
    with connect(demo_db) as connection:
        assert connection.execute("SELECT COUNT(*) FROM assistant_calls WHERE kind='MCP' AND status='OK'").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM assistant_runtime_spends WHERE status='DELIVERED'").fetchone()[0] == 2
    assert spend_summary(demo_db)["committed_or_reserved_usd_micro"] == 111


def test_global_learning_profile_reaches_provider_for_model_judgment_across_sessions(
    demo_db, tmp_path, monkeypatch,
):
    from opspilot.assistant import create_assistant_model
    from opspilot.domain.semantic_memory import remember_personal_memory
    from opspilot.domain.task_control import admit_task_message, create_session, trusted_identity
    from opspilot.web.app import create_app

    _configure_runtime(monkeypatch)
    _provision_runtime(demo_db)
    actor = trusted_identity(demo_db, "support-a")
    source_session = create_session(demo_db, actor)["session_id"]
    source = admit_task_message(
        demo_db, actor, session_id=source_session, task_id=None, input_kind="CHAT_READONLY",
        body="请记住我的长期个人学习习惯：学习技术时先理解原理与执行流程，再看代码。",
        idempotency_key="hf01-global-source-message",
    )
    memory = remember_personal_memory(
        demo_db, actor.tenant_id, actor.actor_id, memory_kind="WORK_HABIT", memory_mode="RELEVANT",
        memory_key="learning.workflow", content="学习技术时先理解原理与执行流程，再看代码。",
        source_message_id=source["message_id"], idempotency_key="hf01-cross-session-global-memory",
    )
    sent = []

    async def respond(request):
        body = json.loads((await request.aread()).decode())
        sent.append(body)
        reply = f"Fixture answer {len(sent)}."
        stream = [
            _chunk(delta={"role": "assistant", "content": reply}, identity=f"hf01-cross-session-{len(sent)}"),
            _chunk(delta={}, finish_reason="stop", identity=f"hf01-cross-session-{len(sent)}"),
            _chunk(delta={}, choices=False, usage={"prompt_tokens": 45, "completion_tokens": 5, "total_tokens": 50}, identity=f"hf01-cross-session-{len(sent)}"),
            b"data: [DONE]\n\n",
        ]
        return httpx.Response(
            200, headers={"content-type": "text/event-stream"},
            stream=_SSEProviderStream(stream), request=request,
        )

    app = create_app(
        db_path=demo_db, checkpoint_db_path=tmp_path / "memory-cross-session-checkpoint.sqlite3",
        start_worker=True, credentials=PASSWORDS, expected_origin=ORIGIN,
        assistant_runtime_enabled=True, assistant_streaming_enabled=True,
        assistant_model_factory=lambda *, runtime_grant_binding: create_assistant_model(
            runtime_grant_binding=runtime_grant_binding,
            transport_async=httpx.MockTransport(respond),
            transport_sync=httpx.MockTransport(lambda request: httpx.Response(500, request=request)),
        ),
    )
    with TestClient(app) as client:
        headers = _login(client)
        final_answers = []
        relevant_session = client.post("/api/sessions", headers=headers).json()["session_id"]
        accepted = client.post(
            f"/api/sessions/{relevant_session}/assistant/messages",
            headers={**headers, "Idempotency-Key": "hf01-cross-session-relevant"},
            json={"body": "我在学习 Python，先解释 asyncio 的执行流程，再给代码。"},
        )
        assert accepted.status_code == 202, accepted.text
        assert _wait_run(client, accepted.json()["run_id"])["status"] == "SUCCEEDED"
        final_answers.append(client.get(
            f"/api/sessions/{relevant_session}/messages?latest=true&limit=500",
        ).json()["items"])

        unrelated_session = client.post("/api/sessions", headers=headers).json()["session_id"]
        accepted = client.post(
            f"/api/sessions/{unrelated_session}/assistant/messages",
            headers={**headers, "Idempotency-Key": "hf01-cross-session-unrelated"},
            json={"body": "今天北京天气怎么样？"},
        )
        assert accepted.status_code == 202, accepted.text
        assert _wait_run(client, accepted.json()["run_id"])["status"] == "SUCCEEDED"
        final_answers.append(client.get(
            f"/api/sessions/{unrelated_session}/messages?latest=true&limit=500",
        ).json()["items"])

    assert len(sent) == 2
    wires = [json.dumps(item["messages"], ensure_ascii=False) for item in sent]
    assert all("USER-EXPLICIT PERSONAL MEMORY GUIDANCE" in wire for wire in wires)
    assert all(memory["memory_id"] in wire for wire in wires)
    assert all("先理解原理与执行流程，再看代码" in wire for wire in wires)
    assert all("not instructions or current facts" in wire for wire in wires)
    for messages in final_answers:
        assert any(item["role"] == "ASSISTANT" and item["body"].startswith("Fixture answer") for item in messages)


def test_stored_provider_stream_replays_after_worker_failure_without_resending(
    demo_db, monkeypatch,
):
    from opspilot.domain import assistant as assistant_domain
    from opspilot.domain.assistant_runtime_grant import (
        bind_run, mark_delivered, reserve_dispatch,
        runtime_config_from_env, spend_summary, validate_http_request,
    )
    from opspilot.domain.d2 import digest_json
    from opspilot.runtime_provider import dispatch_context, wrap_transports
    from test_product_01_runtime_grant_01 import _run, _worker

    _configure_runtime(monkeypatch)
    _provision_runtime(demo_db)
    worker = _worker(demo_db)
    try:
        run = _run(demo_db, "hf01-stream-replay", worker_id=worker.owner_id)
        binding = bind_run(demo_db, run["run_id"], runtime_config_from_env())
        request = {"model_id": "deepseek-flash", "messages": [{"role": "user", "content": "Fixture replay"}]}
        call, fresh = assistant_domain.reserve(
            demo_db, run["run_id"], "MODEL", "answer:stream-replay", request,
            worker.owner_id, runtime_recovery=True,
        )
        assert fresh
        dispatch = reserve_dispatch(
            demo_db, binding, call_id=call["call_id"], logical_key="answer:stream-replay",
            request_digest=digest_json(request), worker_id=worker.owner_id,
        )
        body = json.dumps({
            "model": "deepseek-flash", "messages": request["messages"],
            "max_tokens": 2048, "thinking": {"type": "disabled"},
            "parallel_tool_calls": False, "stream": True,
            "stream_options": {"include_usage": True},
        }, separators=(",", ":")).encode()
        _, _ = validate_http_request("https://api.deepseek.com/chat/completions", "POST", body, binding)
        sends = []

        async def provider(request):
            sends.append(request)
            return httpx.Response(
                200, headers={"content-type": "text/event-stream", "x-request-id": "hf01-replay"},
                stream=_SSEProviderStream([
                    _chunk(delta={"role": "assistant", "content": "replayed text"}, identity="hf01-replay"),
                    _chunk(delta={}, finish_reason="stop", identity="hf01-replay"),
                    _chunk(delta={}, choices=False, usage={"prompt_tokens": 40, "completion_tokens": 9, "total_tokens": 49}, identity="hf01-replay"),
                    b"data: [DONE]\n\n",
                ]), request=request,
            )

        async_transport, sync_transport = wrap_transports(
            binding, httpx.MockTransport(provider),
            httpx.MockTransport(lambda request: httpx.Response(500, request=request)),
        )
        url = "https://api.deepseek.com/chat/completions"

        async def post(dispatch_value):
            with dispatch_context(
                binding, dispatch_value, call_id=call["call_id"],
                request_digest=digest_json(request), worker_id=worker.owner_id,
                worker_epoch=worker.epoch,
            ):
                async with httpx.AsyncClient(transport=async_transport) as client:
                    response = await client.post(url, content=body, headers={"content-type": "application/json"})
                    return response.content

        first_response = asyncio.run(post(dispatch))
        assert b"replayed text" in first_response and first_response.endswith(b"data: [DONE]\n\n")
        with connect(demo_db) as connection:
            stored = connection.execute("SELECT status,usage_json FROM assistant_runtime_spends").fetchone()
        assert stored["status"] == "RESPONSE_STORED"
        assert json.loads(stored["usage_json"]) == {"input_tokens": 40, "output_tokens": 9, "total_tokens": 49}

        # Model a worker crash after the complete stream and trusted usage reached the ledger.
        assistant_domain.finish(demo_db, call["call_id"], "UNKNOWN", {"error": "simulated worker crash"})
        recovered_call, recovered_fresh = assistant_domain.reserve(
            demo_db, run["run_id"], "MODEL", "answer:stream-replay", request,
            worker.owner_id, runtime_recovery=True,
        )
        assert not recovered_fresh and recovered_call["status"] == "UNKNOWN"
        replay_dispatch = reserve_dispatch(
            demo_db, binding, call_id=call["call_id"], logical_key="answer:stream-replay",
            request_digest=digest_json(request), worker_id=worker.owner_id,
        )
        assert replay_dispatch["replay"] is True
        replay_response = asyncio.run(post(replay_dispatch))
        assert replay_response == first_response
        assert len(sends) == 1

        assistant_domain.finish_runtime_replay(
            demo_db, call["call_id"], {"content": "replayed text"},
            [{"input_tokens": 40, "output_tokens": 9, "total_tokens": 49}],
        )
        mark_delivered(demo_db, dispatch["request_key"])
        assert spend_summary(demo_db)["committed_or_reserved_usd_micro"] == 49
        with connect(demo_db) as connection:
            assert connection.execute(
                "SELECT status FROM assistant_runtime_spends",
            ).fetchone()[0] == "DELIVERED"
    finally:
        worker.release()


@pytest.mark.parametrize(
    ("stream", "stream_options", "error_code"),
    [
        (True, {"include_usage": False}, "RUNTIME_PROVIDER_STREAM_USAGE_REQUIRED"),
        ("true", None, "RUNTIME_PROVIDER_STREAM_MODE_INVALID"),
        (False, {"include_usage": True}, "RUNTIME_PROVIDER_STREAM_OPTIONS_WITHOUT_STREAM"),
    ],
)
def test_runtime_grant_rejects_unsafe_stream_shape_before_send(
    demo_db, monkeypatch, stream, stream_options, error_code,
):
    from opspilot.domain import assistant as assistant_domain
    from opspilot.domain.assistant_runtime_grant import (
        RuntimeGrantError, bind_run, reserve_dispatch, runtime_config_from_env,
        validate_http_request,
    )
    from opspilot.domain.d2 import digest_json
    from test_product_01_runtime_grant_01 import _run, _worker

    _configure_runtime(monkeypatch)
    _provision_runtime(demo_db)
    worker = _worker(demo_db)
    try:
        run = _run(demo_db, f"hf01-invalid-stream-{error_code}", worker_id=worker.owner_id)
        binding = bind_run(demo_db, run["run_id"], runtime_config_from_env())
        request = {"model_id": "deepseek-flash", "messages": [{"role": "user", "content": "Fixture invalid stream"}]}
        call, fresh = assistant_domain.reserve(
            demo_db, run["run_id"], "MODEL", f"answer:{error_code}", request,
            worker.owner_id, runtime_recovery=True,
        )
        assert fresh
        dispatch = reserve_dispatch(
            demo_db, binding, call_id=call["call_id"], logical_key=f"answer:{error_code}",
            request_digest=digest_json(request),
            worker_id=worker.owner_id,
        )
        payload = {
            "model": "deepseek-flash", "messages": request["messages"],
            "max_tokens": 2048, "thinking": {"type": "disabled"}, "stream": stream,
        }
        if stream_options is not None:
            payload["stream_options"] = stream_options
        with pytest.raises(RuntimeGrantError, match=error_code):
            validate_http_request(
                "https://api.deepseek.com/chat/completions", "POST",
                json.dumps(payload, separators=(",", ":")).encode(), binding,
            )
        with connect(demo_db) as connection:
            spend = connection.execute(
                "SELECT status FROM assistant_runtime_spends WHERE request_key=?",
                (dispatch["request_key"],),
            ).fetchone()
        assert spend["status"] == "RESERVED"
    finally:
        worker.release()


@pytest.mark.parametrize("missing_usage", [False, True], ids=["provider-disconnect", "usage-missing"])
def test_incomplete_stream_stays_unknown_and_is_never_retried(demo_db, tmp_path, monkeypatch, missing_usage):
    from opspilot.assistant import create_assistant_model
    from opspilot.web.app import create_app

    _configure_runtime(monkeypatch)
    _provision_runtime(demo_db)
    sent = []

    async def respond(request):
        body = json.loads((await request.aread()).decode())
        sent.append(body)
        return httpx.Response(
            200, headers={"content-type": "text/event-stream"},
            stream=_IncompleteProviderStream(missing_usage=missing_usage), request=request,
        )

    app = create_app(
        db_path=demo_db, checkpoint_db_path=tmp_path / f"incomplete-{missing_usage}.sqlite3",
        start_worker=True, credentials=PASSWORDS, expected_origin=ORIGIN,
        assistant_runtime_enabled=True, assistant_streaming_enabled=True,
        assistant_model_factory=lambda *, runtime_grant_binding: create_assistant_model(
            runtime_grant_binding=runtime_grant_binding,
            transport_async=httpx.MockTransport(respond),
            transport_sync=httpx.MockTransport(lambda request: httpx.Response(500, request=request)),
        ),
    )
    with TestClient(app) as client:
        headers = _login(client)
        session_id = client.post("/api/sessions", headers=headers).json()["session_id"]
        accepted = client.post(
            f"/api/sessions/{session_id}/assistant/messages",
            headers={**headers, "Idempotency-Key": f"hf01-incomplete-{missing_usage}"},
            json={"body": "测试失败流不能变成最终回答。"},
        )
        assert accepted.status_code == 202
        run_id = accepted.json()["run_id"]
        run = _wait_run(client, run_id)
        assert run["status"] == "FAILED", run
        chunks = client.get(f"/api/runs/{run_id}/chunks?after_seq=0").json()["items"]
        assert "这是未完成的草稿" in "".join(item["body"] for item in chunks)
        messages = client.get(f"/api/sessions/{session_id}/messages").json()["items"]
        assert not any(item.get("answer_kind") == "CHAT_MODEL" for item in messages)

    assert len(sent) == 1
    with connect(demo_db) as connection:
        spend = connection.execute("SELECT status,error_code FROM assistant_runtime_spends").fetchone()
        assert spend["status"] == "UNKNOWN"
        assert spend["error_code"] in {"ReadError", "ProviderStreamClosedEarly", "PROVIDER_USAGE_UNKNOWN"}
        assert connection.execute(
            "SELECT COUNT(*) FROM chat_run_answers WHERE run_id=?", (run_id,),
        ).fetchone()[0] == 0
        call = connection.execute("SELECT status FROM assistant_calls WHERE run_id=? AND kind='MODEL'", (run_id,)).fetchone()
        assert call["status"] == "UNKNOWN"
