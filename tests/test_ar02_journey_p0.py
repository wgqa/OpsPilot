"""AR-02-JOURNEY-P0: formal API/Worker/ASSISTANT_V1 offline journey.

No real Provider is contacted. Business facts pass through the actual stdio MCP
client and the local authenticated HTTP route; S3 setup POSTs are test preparation.
"""
from __future__ import annotations

import json
import os
import time
from collections import deque
from pathlib import Path

import httpx
import pytest
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import Field


def _enable_provider_factory(monkeypatch):
    monkeypatch.setenv("OPSPILOT_ASSISTANT_PROVIDER_ENABLED", "1")
    monkeypatch.setenv("OPSPILOT_ASSISTANT_EXPERIMENT_ID", "AR-02-LIVE-01")
    monkeypatch.setenv("OPSPILOT_MODEL_API_KEY", "test-only-not-a-real-key")
    monkeypatch.setenv("OPSPILOT_MODEL_NAME", "deepseek-flash")
    monkeypatch.setenv("OPSPILOT_MODEL_BASE_URL", "https://api.deepseek.com")


def test_formal_provider_factory_serializes_frozen_wire_with_explicit_mock_transport(monkeypatch):
    """Exercise the real ChatOpenAI factory and SDK serializer without network access."""
    from opspilot.assistant import create_assistant_model

    _enable_provider_factory(monkeypatch)
    captured = []

    async def async_response(request):
        captured.append({
            "url": str(request.url), "method": request.method,
            "body": json.loads((await request.aread()).decode("utf-8")),
        })
        return httpx.Response(200, json={
            "id": "journey-p0-mock-completion", "object": "chat.completion", "created": 1,
            "model": "deepseek-flash", "choices": [{"index": 0,
                "message": {"role": "assistant", "content": "Local mock response"},
                "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 7, "completion_tokens": 4, "total_tokens": 11},
        })

    model = create_assistant_model(
        transport_async=httpx.MockTransport(async_response),
        transport_sync=httpx.MockTransport(lambda request: httpx.Response(500)),
    )
    tool = {
        "type": "function",
        "function": {
            "name": "get_order_status",
            "description": "Read the trusted bound order.",
            "parameters": {"type": "object", "properties": {
                "reason": {"type": "string"}}, "required": ["reason"]},
        },
    }

    async def invoke():
        response = await model.bind_tools(
            [tool], tool_choice="auto", parallel_tool_calls=False,
        ).ainvoke([HumanMessage(content="Read the authorized order.")])
        assert response.content == "Local mock response"

    try:
        import asyncio
        asyncio.run(invoke())
    finally:
        import asyncio
        asyncio.run(model.http_async_client.aclose())
        model.http_client.close()

    assert len(captured) == 1
    record = captured[0]
    body = record["body"]
    assert record["method"] == "POST"
    assert record["url"] == "https://api.deepseek.com/chat/completions"
    assert body["model"] == "deepseek-flash"
    assert body["thinking"] == {"type": "disabled"}
    assert body["max_tokens"] == 2048
    assert body["tool_choice"] == "auto"
    assert body["parallel_tool_calls"] is False
    assert body["tools"][0]["function"]["name"] == "get_order_status"
    assert "max_completion_tokens" not in body


def test_formal_worker_closes_factory_owned_httpx_clients_after_run(demo_db, monkeypatch):
    import asyncio
    from opspilot.domain import assistant as assistant_domain
    from opspilot import assistant as assistant_runtime
    from opspilot.web import worker

    class AsyncClient:
        closed = False

        async def aclose(self):
            self.closed = True

    class SyncClient:
        closed = False

        def close(self):
            self.closed = True

    class Model:
        http_async_client = AsyncClient()
        http_client = SyncClient()

    model = Model()
    monkeypatch.setattr(assistant_domain, "selected", lambda *_: True)
    monkeypatch.setattr(worker, "_chat_run_actor", lambda *_: "support-a")
    monkeypatch.setattr(worker, "claim_task_run", lambda *_: None)

    async def completed_run(*_args, **_kwargs):
        return {"status": "SUCCEEDED"}

    monkeypatch.setattr(assistant_runtime, "run_assistant", completed_run)
    asyncio.run(worker._dispatch_run(
        demo_db, demo_db.parent / "unused-checkpoint.sqlite3", "offline-worker", "executor",
        {"run_id": "offline-factory-close-test", "kind": "CHAT_READONLY"},
        assistant_model_factory=lambda: model,
    ))
    assert model.http_async_client.closed is True
    assert model.http_client.closed is True


class JourneyFixtureModel(BaseChatModel):
    """Deterministic policy fixture; never evidence of real model autonomy."""

    mode: str
    seen: list = Field(default_factory=list)
    decisions: list = Field(default_factory=list)
    offered_tool_names: list = Field(default_factory=list)

    @property
    def _llm_type(self):
        return "AR02_JOURNEY_P0_DETERMINISTIC_FIXTURE"

    def bind_tools(self, tools, **kwargs):
        self.offered_tool_names = [tool.name for tool in tools]
        return self

    @staticmethod
    def _tool_payload(message):
        payload = json.loads(message.content)
        if isinstance(payload, dict) and set(payload) == {"result"}:
            payload = payload["result"]
        return payload

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        self.seen.append(messages)
        tool_messages = [m for m in messages if isinstance(m, ToolMessage)]
        tool_payloads = [self._tool_payload(message) for message in tool_messages]
        name = None
        args = {}

        if self.mode == "knowledge" and not tool_messages:
            name = "search_project_knowledge"
            args = {"query": "HTTP 202 acceptance receiver processing"}
        elif self.mode == "knowledge_empty" and not tool_messages:
            name = "search_project_knowledge"
            args = {"query": "zzzz-no-matching-document-zzzz"}
        elif self.mode in {"order", "receiver", "draft", "receiver_not_received"}:
            seen_names = set()
            for message in tool_messages:
                for prior in messages:
                    if isinstance(prior, AIMessage):
                        for call in prior.tool_calls:
                            if call.get("id") == message.tool_call_id:
                                seen_names.add(call.get("name"))
            desired = {
                "order": ["get_order_status"],
                "receiver": ["get_callback_delivery", "get_receiver_processing"],
                "receiver_not_received": ["get_callback_delivery", "get_receiver_processing"],
                "draft": ["get_receiver_processing"],
            }[self.mode]
            name = next((candidate for candidate in desired if candidate not in seen_names), None)
            if name:
                args = {"reason": "verify the current fact through the trusted binding"}

        if name:
            self.decisions.append({"action": "CALL", "tool": name})
            message = AIMessage(content="", tool_calls=[{
                "name": name, "args": args, "id": f"journey-{self.mode}-{len(tool_messages)}",
            }])
        else:
            self.decisions.append({"action": "ANSWER"})
            if self.mode == "s01":
                text = "HTTP 202 表示受理，不证明下游处理完成。没有订单、Event 或 Receiver 的当前观察，因此当前处理状态未知。"
            elif self.mode in {"knowledge", "knowledge_empty"}:
                result = tool_payloads[-1] if tool_payloads else {}
                documents, refs = result.get("documents", []), result.get("source_refs", [])
                if documents and refs:
                    doc, ref = documents[0], refs[0]
                    excerpt = doc.get("summary") or doc.get("content", "")[:240]
                    text = (f"检索到 {doc['document_id']} v{doc['version']}，摘要摘录：{excerpt}；"
                            f"来源：{ref['source']}。HTTP 202 仅表示受理，不证明处理完成。")
                else:
                    text = "本次检索没有找到可引用文档。一般 HTTP 语义上，202 表示受理，不证明处理完成。"
            elif self.mode == "history":
                prior = [m.content for m in messages if isinstance(m, AIMessage) and "历史答复" in m.content]
                text = "根据同一 Session 上一轮实际答复继续说明；协议引用仅按历史来源理解，不是新的业务观察。"
                if prior:
                    text += " 上轮内容：" + prior[-1][:500]
            elif self.mode == "order":
                facts = tool_payloads[-1].get("facts", {})
                body = facts.get("body", {})
                text = f"本次真实查询返回 HTTP {facts.get('http_status')}，绑定订单 {body.get('order_id')} 状态为 {body.get('status')}；这不单独证明 Receiver 已处理。"
            elif self.mode in {"receiver", "receiver_not_received", "draft"}:
                by_call = {}
                ids = {m.tool_call_id for m in tool_messages}
                for prior in messages:
                    if isinstance(prior, AIMessage):
                        for call in prior.tool_calls:
                            if call.get("id") in ids:
                                matched = next(m for m in tool_messages if m.tool_call_id == call.get("id"))
                                by_call[call.get("name")] = self._tool_payload(matched).get("facts", {})
                delivery = by_call.get("get_callback_delivery", {})
                receiver = by_call.get("get_receiver_processing", {})
                event_id = delivery.get("event_id") or receiver.get("event_id")
                receiver_event = receiver.get("event_id")
                state, http_status = receiver.get("status"), delivery.get("receiver_http_status")
                if state == "QUEUED":
                    if http_status is None:
                        outcome = f"同一 Event {event_id} 的 Receiver 本次查询为 QUEUED；Delivery 未在本 Run 重查，不能称为处理完成。"
                    else:
                        outcome = f"同一 Event {event_id} 的 Delivery HTTP {http_status}，Receiver 当前为 QUEUED；尚不能称为处理完成。"
                elif state == "PROCESSED":
                    outcome = f"同一 Event {event_id} 的 Receiver 当前为 PROCESSED。"
                else:
                    outcome = f"同一 Event {event_id} 的 Receiver 状态为 {state or 'UNKNOWN'}，处理完成与否未知。"
                if event_id is not None and receiver_event is not None and event_id != receiver_event:
                    outcome = "Delivery 与 Receiver Event 不匹配，不能得出完成结论。"
                if self.mode == "draft":
                    prior_answers = [
                        item.content for item in messages
                        if isinstance(item, AIMessage) and "历史答复" in item.content
                    ]
                    last_known = "；".join(prior_answers[-3:])
                    text = (f"处理说明草稿：此前调查结果（历史来源，本 Run 未重新核验）：{last_known[:700]}；"
                            f"当前观察：{outcome} 用户示例 event-e1/req-e1-1 是未验证线索。"
                            "未知：Receiver 是否完成业务处理；本草稿未提交、未创建工单。")
                else:
                    text = outcome + " 用户提供的 event-e1/req-e1-1 仍是未验证线索，不能替代本次绑定资源的真实观察。"
            elif self.mode == "negative_no_binding":
                text = "聊天请求不能建立 TaskBinding；未执行任何订单查询。请通过可信订单选择操作确认资源。"
            else:
                text = "未找到可引用协议；一般 HTTP 202 表示受理，不代表下游业务已经完成。"
            message = AIMessage(content=text)
        message.usage_metadata = {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15}
        return ChatResult(generations=[ChatGeneration(message=message)])


def _wait_run(client, run_id):
    deadline = time.monotonic() + 15
    while True:
        response = client.get("/api/runs/" + run_id)
        assert response.status_code == 200, response.text
        run = response.json()
        if run["status"] in {"SUCCEEDED", "FAILED", "BLOCKED"}:
            return run
        assert time.monotonic() < deadline, run
        time.sleep(0.05)


def _write_actual_trace(db_path, sessions, accepted, model_instances):
    target = os.environ.get("OPSPILOT_JOURNEY_TRACE_PATH")
    if not target:
        return
    from opspilot.domain.database import connect

    rows = []
    run_ids = [item["run_id"] for item in accepted]
    with connect(db_path) as connection:
        for item in accepted:
            row = connection.execute(
                "SELECT run_id,task_id,kind,status,source_message_id,created_at,ended_at "
                "FROM task_runs WHERE run_id=?", (item["run_id"],),
            ).fetchone()
            rows.append({"record_type": "persisted_run", **dict(row)})
        for row in connection.execute(
            "SELECT call_id,run_id,kind,logical_key,status,request_json,result_json,usage_json,created_at,completed_at "
            "FROM assistant_calls WHERE run_id IN (" + ",".join("?" for _ in run_ids) + ") ORDER BY created_at",
            run_ids,
        ):
            rows.append({"record_type": "persisted_assistant_call", **dict(row)})
        for row in connection.execute(
            "SELECT o.*,a.run_id FROM d2_tool_observations o JOIN d2_attempts a "
            "ON a.attempt_id=o.attempt_id AND a.task_id=o.task_id "
            "WHERE a.run_id IN (" + ",".join("?" for _ in run_ids) + ") ORDER BY o.created_at",
            run_ids,
        ):
            rows.append({"record_type": "persisted_mcp_observation", **dict(row)})
        for session_id in sessions:
            for row in connection.execute(
                "SELECT message_id,session_id,tenant_id,role,body,task_id,sequence,created_at "
                "FROM messages WHERE session_id=? ORDER BY sequence",
                (session_id,),
            ):
                rows.append({"record_type": "persisted_session_message", **dict(row)})
            for row in connection.execute(
                "SELECT a.run_id,a.message_id,a.attempt_id,a.manifest_id,a.body_digest,a.committed_at,"
                "r.source_message_id,m.body FROM chat_run_answers a JOIN task_runs r ON r.run_id=a.run_id "
                "JOIN messages m ON m.message_id=a.message_id WHERE r.session_id=? ORDER BY a.committed_at",
                (session_id,),
            ):
                rows.append({"record_type": "persisted_answer_source_link", **dict(row)})
    for index, model in enumerate(model_instances):
        rows.append({
            "record_type": "deterministic_fixture_decisions",
            "evidence_level": "DETERMINISTIC_FIXTURE_NOT_REAL_PROVIDER",
            "run_id": accepted[index]["run_id"],
            "mode": model.mode,
            "offered_tool_names": model.offered_tool_names,
            "decisions": model.decisions,
        })
    path = Path(target)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as stream:
        for row in rows:
            stream.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def test_formal_api_worker_s01_and_five_turn_s02_are_persisted_and_source_linked(demo_db, tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from opspilot.domain.database import connect
    from opspilot.domain.s3 import prepare_s3_fixture
    from opspilot.web.app import create_app
    from test_ar02_assistant import ORIGIN, PASSWORDS

    setup = prepare_s3_fixture(demo_db, "DELIVERED_PENDING", order_id="ar02-order", contract_version=2)
    model_instances = [
        JourneyFixtureModel(mode="s01"), JourneyFixtureModel(mode="knowledge"),
        JourneyFixtureModel(mode="history"), JourneyFixtureModel(mode="order"),
        JourneyFixtureModel(mode="receiver"), JourneyFixtureModel(mode="draft"),
    ]
    models = deque(model_instances)
    app = create_app(
        db_path=demo_db, checkpoint_db_path=tmp_path / "journey-worker.sqlite3",
        start_worker=True, credentials=PASSWORDS, expected_origin=ORIGIN,
        assistant_model_factory=lambda: models.popleft(),
    )
    accepted, session_ids = [], []
    with TestClient(app) as client:
        login = client.post("/api/auth/login", headers={"Origin": ORIGIN},
                            json={"actor_id": "support-a", "password": PASSWORDS["support-a"]})
        assert login.status_code == 200
        headers = {"Origin": ORIGIN, "X-CSRF-Token": login.json()["csrf_token"]}

        # S01 is a separate Session, without TaskBinding or current business evidence.
        s01_session = client.post("/api/sessions", headers=headers).json()["session_id"]
        session_ids.append(s01_session)
        s01_text = ("HTTP 202 Accepted 是否意味着订单回调已经处理完成？请区分 HTTP/协议语义和当前订单事实。"
                    "我没有提供订单、Event 或 Receiver 的当前状态。")
        s01 = client.post(
            f"/api/sessions/{s01_session}/assistant/messages",
            headers={**headers, "Idempotency-Key": "journey-p0-s01"},
            json={"body": s01_text},
        )
        assert s01.status_code == 202, s01.text
        s01_item = s01.json()
        accepted.append(s01_item)
        assert _wait_run(client, s01_item["run_id"])["status"] == "SUCCEEDED"
        s01_messages = client.get(f"/api/sessions/{s01_session}/messages").json()["items"]
        s01_answer = next(item for item in s01_messages if item["role"] == "ASSISTANT")
        assert "受理" in s01_answer["body"] and "未知" in s01_answer["body"]
        assert s01_answer["answer_source_message_id"] == s01_item["message_id"]
        with connect(demo_db) as connection:
            assert connection.execute(
                "SELECT COUNT(*) FROM assistant_calls WHERE run_id=? AND kind='MCP'", (s01_item["run_id"],)
            ).fetchone()[0] == 0
            assert connection.execute(
                "SELECT task_id FROM task_runs WHERE run_id=?", (s01_item["run_id"],)
            ).fetchone()[0] is None

        # S02 has five user turns in one Session. Natural-language text does
        # not bind an order; the authenticated endpoint below is the user action.
        s02_session = client.post("/api/sessions", headers=headers).json()["session_id"]
        session_ids.append(s02_session)
        inputs = [
            "请记住下面是待核实的示例线索，不是你已验证的业务事实：`event_id=event-e1, transport_request_id=req-e1-1, delivery_http_status=202, receiver_status=unknown`。请查适用的回调/Receiver 协议，说明 202 能证明和不能证明什么。",
            "我现在确认要查询资料范围中已授权的回调协议；没有特别指定旧版，请按本问题适用范围核对。说明检索到的版本、摘要和来源。",
        ]
        for index, body in enumerate(inputs):
            response = client.post(
                f"/api/sessions/{s02_session}/assistant/messages",
                headers={**headers, "Idempotency-Key": f"journey-p0-s02-{index + 1}"},
                json={"body": body},
            )
            assert response.status_code == 202, response.text
            item = response.json()
            accepted.append(item)
            assert _wait_run(client, item["run_id"])["status"] == "SUCCEEDED"

        resources = client.get("/api/s3/order-resources", headers=headers)
        assert resources.status_code == 200, resources.text
        assert any(row["order_id"] == "ar02-order" for row in resources.json()["items"])
        binding_input = "请绑定我有权访问的订单 `ar02-order` 并核查当前状态。"
        binding = client.post(
            f"/api/sessions/{s02_session}/assistant/order",
            headers={**headers, "Idempotency-Key": "journey-p0-s02-bind"},
            json={"order_id": "ar02-order", "initial_message": binding_input},
        )
        assert binding.status_code == 202, binding.text
        binding_item = binding.json()
        accepted.append(binding_item)
        task_id = binding_item["task_id"]
        assert _wait_run(client, binding_item["run_id"])["status"] == "SUCCEEDED"
        with connect(demo_db) as connection:
            binding_row = connection.execute(
                "SELECT order_id,confirmed_by FROM s3_task_resources WHERE task_id=?", (task_id,)
            ).fetchone()
            assert binding_row and binding_row["order_id"] == "ar02-order"
            assert binding_row["confirmed_by"] == "support-a"

        followups = [
            "对照刚才的 E1 线索和本次真实查询，接收方现在处理完成了吗？",
            "基于目前有来源的事实整理一份处理说明草稿，并明确仍未知的部分。",
        ]
        for index, body in enumerate(followups, start=4):
            response = client.post(
                f"/api/sessions/{s02_session}/assistant/messages",
                headers={**headers, "Idempotency-Key": f"journey-p0-s02-{index}"},
                json={"body": body, "task_id": task_id},
            )
            assert response.status_code == 202, response.text
            item = response.json()
            accepted.append(item)
            assert _wait_run(client, item["run_id"])["status"] == "SUCCEEDED"

        s02_messages = client.get(f"/api/sessions/{s02_session}/messages").json()["items"]
        users = [item for item in s02_messages if item["role"] == "USER"]
        answers = [item for item in s02_messages if item["role"] == "ASSISTANT"]
        assert len(users) == len(answers) == 5
        assert {item["answer_source_message_id"] for item in answers} == {
            item["message_id"] for item in accepted[1:]
        }
        answer_by_source = {item["answer_source_message_id"]: item["body"] for item in answers}
        assert "receiver-ack-contract-v2" in answer_by_source[accepted[1]["message_id"]]
        assert "v2" in answer_by_source[accepted[1]["message_id"]]
        assert "来源" in answer_by_source[accepted[1]["message_id"]]
        assert "receiver-ack-contract-v2" in answer_by_source[accepted[2]["message_id"]]
        assert "HTTP 200" in answer_by_source[accepted[3]["message_id"]]
        assert "QUEUED" in answer_by_source[accepted[4]["message_id"]]
        assert "尚不能称为处理完成" in answer_by_source[accepted[4]["message_id"]]
        draft = answer_by_source[accepted[5]["message_id"]]
        assert "草稿" in draft and "未知" in draft and "未提交" in draft and "未创建工单" in draft
        assert setup["receiver_http_status"] == 202
        assert setup["agent_actions"] == []

        with connect(demo_db) as connection:
            ids = [item["run_id"] for item in accepted]
            calls = connection.execute(
                "SELECT run_id,kind,request_json,result_json,evidence_id,observation_id FROM assistant_calls "
                "WHERE run_id IN (" + ",".join("?" for _ in accepted) + ") ORDER BY created_at",
                ids,
            ).fetchall()
            mcp_calls = [row for row in calls if row["kind"] == "MCP"]
            assert len(mcp_calls) == 5
            results = [json.loads(row["result_json"]) for row in mcp_calls]
            assert any("receiver-ack-contract-v2" in json.dumps(result) for result in results)
            observations = connection.execute(
                "SELECT o.*,a.run_id FROM d2_tool_observations o JOIN d2_attempts a "
                "ON a.attempt_id=o.attempt_id AND a.task_id=o.task_id WHERE a.run_id IN (" +
                ",".join("?" for _ in accepted) + ")",
                ids,
            ).fetchall()
            assert len(observations) == 4
            delivery = next(json.loads(row["result_json"]) for row in mcp_calls
                            if json.loads(row["request_json"])["name"] == "get_callback_delivery")
            receiver = next(json.loads(row["result_json"]) for row in mcp_calls
                            if json.loads(row["request_json"])["name"] == "get_receiver_processing")
            assert delivery["facts"]["event_id"] == setup["transport_trace"][0]["request"]["event_id"]
            assert receiver["facts"]["event_id"] == delivery["facts"]["event_id"]
            assert receiver["facts"]["status"] == "QUEUED"
            assert {tool for model in model_instances for tool in model.offered_tool_names} >= {
                "search_project_knowledge"
            }
            task_tools = set(model_instances[3].offered_tool_names)
            assert {
                "get_order_status", "get_callback_delivery", "get_receiver_processing",
                "get_callback_transport_history", "search_project_knowledge",
            } <= task_tools
            assert connection.execute("SELECT COUNT(*) FROM s3_diagnoses WHERE task_id=?", (task_id,)).fetchone()[0] == 0
            for table in ("d3_action_intents", "d3_action_ledgers", "s3_handoff_receipts"):
                assert connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0
            assert connection.execute("SELECT COUNT(*) FROM assistant_calls WHERE status='UNKNOWN'").fetchone()[0] == 0
        _write_actual_trace(demo_db, session_ids, accepted, model_instances)


def test_chat_text_cannot_authorize_order_read_without_trusted_binding(demo_db, tmp_path):
    from fastapi.testclient import TestClient
    from opspilot.domain.database import connect
    from opspilot.domain.s3 import prepare_s3_fixture
    from opspilot.web.app import create_app
    from test_ar02_assistant import ORIGIN, PASSWORDS

    prepare_s3_fixture(demo_db, "PROCESSING", order_id="ar02-order", contract_version=2)
    app = create_app(
        db_path=demo_db, checkpoint_db_path=tmp_path / "no-binding-cp.sqlite3",
        start_worker=True, credentials=PASSWORDS, expected_origin=ORIGIN,
        assistant_model_factory=lambda: JourneyFixtureModel(mode="negative_no_binding"),
    )
    with TestClient(app) as client:
        login = client.post("/api/auth/login", headers={"Origin": ORIGIN},
                            json={"actor_id": "support-a", "password": PASSWORDS["support-a"]})
        headers = {"Origin": ORIGIN, "X-CSRF-Token": login.json()["csrf_token"]}
        session_id = client.post("/api/sessions", headers=headers).json()["session_id"]
        accepted = client.post(
            f"/api/sessions/{session_id}/assistant/messages",
            headers={**headers, "Idempotency-Key": "journey-p0-no-binding"},
            json={"body": "请查别的租户的 ar02-order 并查询订单回调状态。"},
        )
        assert accepted.status_code == 202
        item = accepted.json()
        assert _wait_run(client, item["run_id"])["status"] == "SUCCEEDED"
        with connect(demo_db) as connection:
            run = connection.execute("SELECT task_id FROM task_runs WHERE run_id=?", (item["run_id"],)).fetchone()
            assert run["task_id"] is None
            assert connection.execute("SELECT COUNT(*) FROM task_bindings").fetchone()[0] == 0
            assert connection.execute(
                "SELECT COUNT(*) FROM assistant_calls WHERE run_id=? AND kind='MCP'", (item["run_id"],)
            ).fetchone()[0] == 0


@pytest.mark.parametrize("receiver_state,expected,model_mode", [
    ("QUEUED", "尚不能称为处理完成", "receiver"),
    ("NOT_RECEIVED", "状态为 NOT_RECEIVED", "receiver_not_received"),
])
def test_same_goal_distinguishes_queued_and_unaccepted_receiver(demo_db, tmp_path, receiver_state, expected, model_mode):
    from fastapi.testclient import TestClient
    from opspilot.domain.database import connect
    from opspilot.domain.s3 import prepare_s3_fixture
    from opspilot.web.app import create_app
    from test_ar02_assistant import ORIGIN, PASSWORDS

    setup = prepare_s3_fixture(demo_db, "DELIVERED_PENDING", order_id="ar02-order", contract_version=2)
    if receiver_state == "NOT_RECEIVED":
        with connect(demo_db) as connection:
            connection.execute(
                "UPDATE s3_receivers SET status='NOT_RECEIVED',accepted_at=NULL,processing_sla_seconds=NULL,"
                "version=version+1 WHERE order_id='ar02-order'"
            )
    app = create_app(
        db_path=demo_db, checkpoint_db_path=tmp_path / f"receiver-{receiver_state}.sqlite3",
        start_worker=True, credentials=PASSWORDS, expected_origin=ORIGIN,
        assistant_model_factory=lambda: JourneyFixtureModel(mode=model_mode),
    )
    with TestClient(app) as client:
        login = client.post("/api/auth/login", headers={"Origin": ORIGIN},
                            json={"actor_id": "support-a", "password": PASSWORDS["support-a"]})
        headers = {"Origin": ORIGIN, "X-CSRF-Token": login.json()["csrf_token"]}
        session_id = client.post("/api/sessions", headers=headers).json()["session_id"]
        resource = client.get("/api/s3/order-resources", headers=headers).json()["items"][0]
        assert resource["order_id"] == "ar02-order"
        bound = client.post(
            f"/api/sessions/{session_id}/assistant/order",
            headers={**headers, "Idempotency-Key": "journey-p0-receiver-bind"},
            json={"order_id": "ar02-order", "initial_message": "绑定授权订单"},
        )
        assert bound.status_code == 202
        assert _wait_run(client, bound.json()["run_id"])["status"] == "SUCCEEDED"
        with connect(demo_db) as connection:
            calls = connection.execute(
                "SELECT request_json,result_json FROM assistant_calls WHERE run_id=? AND kind='MCP' ORDER BY created_at",
                (bound.json()["run_id"],),
            ).fetchall()
            assert any(json.loads(row["request_json"])["name"] == "get_receiver_processing" for row in calls)
            receiver_call = next(row for row in calls if json.loads(row["request_json"])["name"] == "get_receiver_processing")
            receiver = json.loads(receiver_call["result_json"])
            assert receiver["facts"]["status"] == receiver_state
            assert receiver["facts"]["event_id"] == setup["transport_trace"][0]["request"]["event_id"]
        messages = client.get(f"/api/sessions/{session_id}/messages").json()["items"]
        answer = next(item["body"] for item in messages if item["role"] == "ASSISTANT")
        assert expected in answer
        assert "已处理完成" not in answer


def test_empty_knowledge_tool_result_is_not_reported_as_a_document_citation(demo_db, tmp_path):
    from fastapi.testclient import TestClient
    from opspilot.domain.database import connect
    from opspilot.web.app import create_app
    from test_ar02_assistant import ORIGIN, PASSWORDS

    app = create_app(
        db_path=demo_db, checkpoint_db_path=tmp_path / "knowledge-empty-cp.sqlite3",
        start_worker=True, credentials=PASSWORDS, expected_origin=ORIGIN,
        assistant_model_factory=lambda: JourneyFixtureModel(mode="knowledge_empty"),
    )
    with TestClient(app) as client:
        login = client.post("/api/auth/login", headers={"Origin": ORIGIN},
                            json={"actor_id": "support-a", "password": PASSWORDS["support-a"]})
        headers = {"Origin": ORIGIN, "X-CSRF-Token": login.json()["csrf_token"]}
        session_id = client.post("/api/sessions", headers=headers).json()["session_id"]
        accepted = client.post(
            f"/api/sessions/{session_id}/assistant/messages",
            headers={**headers, "Idempotency-Key": "journey-p0-empty-knowledge"},
            json={"body": "解释 202 的一般协议语义。"},
        )
        item = accepted.json()
        assert _wait_run(client, item["run_id"])["status"] == "SUCCEEDED"
        with connect(demo_db) as connection:
            call = connection.execute(
                "SELECT request_json,result_json FROM assistant_calls WHERE run_id=? AND kind='MCP'",
                (item["run_id"],),
            ).fetchone()
            assert call is not None
            tool_result = json.loads(call["result_json"])
            assert tool_result["documents"] == []
            assert tool_result["source_refs"] == []
        messages = client.get(f"/api/sessions/{session_id}/messages").json()["items"]
        answer = next(row["body"] for row in messages if row["role"] == "ASSISTANT")
        assert "没有找到可引用文档" in answer
        assert "callback-ack-contract" not in answer
