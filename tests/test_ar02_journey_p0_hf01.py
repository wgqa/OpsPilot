"""AR-02-JOURNEY-P0-HF01 targeted offline evidence supplements."""
from __future__ import annotations

import json
import os
from collections import deque
from pathlib import Path

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import Field

from test_ar02_journey_p0 import JourneyFixtureModel, _wait_run


class ReceiverAvailabilityFixture(JourneyFixtureModel):
    """Select delivery and optionally the current Receiver read, then answer from this Run."""

    query_receiver: bool

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        self.seen.append(messages)
        tool_messages = [message for message in messages if isinstance(message, ToolMessage)]
        prior_names = {}
        for prior in messages:
            if isinstance(prior, AIMessage):
                for call in prior.tool_calls:
                    prior_names[call.get("id")] = call.get("name")
        observed_names = {prior_names.get(message.tool_call_id) for message in tool_messages}

        name = None
        if "get_callback_delivery" not in observed_names:
            name = "get_callback_delivery"
        elif self.query_receiver and "get_receiver_processing" not in observed_names:
            name = "get_receiver_processing"

        if name:
            self.decisions.append({"action": "CALL", "tool": name})
            message = AIMessage(content="", tool_calls=[{
                "name": name,
                "args": {"reason": "核实同一 Event 的当前接收与处理状态"},
                "id": f"hf01-receiver-{len(tool_messages)}",
            }])
        else:
            facts_by_tool = {}
            for tool_message in tool_messages:
                name_for_message = prior_names.get(tool_message.tool_call_id)
                try:
                    result = json.loads(tool_message.content)
                except (TypeError, json.JSONDecodeError):
                    result = {}
                if isinstance(result, dict) and set(result) == {"result"}:
                    result = result["result"]
                facts_by_tool[name_for_message] = result.get("facts", {}) if isinstance(result, dict) else {}

            delivery = facts_by_tool.get("get_callback_delivery", {})
            receiver = facts_by_tool.get("get_receiver_processing", {})
            event_id = delivery.get("event_id")
            state = receiver.get("status")
            if state == "QUEUED":
                text = f"同一 Event {event_id} 的 Receiver 当前观察为 QUEUED；尚不能确认处理完成。"
            elif state == "PROCESSED":
                text = f"同一 Event {event_id} 的 Receiver 当前观察为 PROCESSED。"
            else:
                text = f"同一 Event {event_id} 没有可用的当前 Receiver Observation，处理完成与否为 UNKNOWN，无法确认已处理。"
            self.decisions.append({"action": "ANSWER", "answer": text})
            message = AIMessage(content=text)

        message.usage_metadata = {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15}
        return ChatResult(generations=[ChatGeneration(message=message)])


class ExplicitOrderProposalFixture(JourneyFixtureModel):
    """Always proposes the same order read, even if it was not exposed by MCP discovery."""

    proposals: list = Field(default_factory=list)

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        self.seen.append(messages)
        tool_messages = [message for message in messages if isinstance(message, ToolMessage)]
        if not tool_messages:
            proposal = {
                "name": "get_order_status",
                "args": {"reason": "按用户请求查询当前绑定订单状态"},
            }
            self.proposals.append(proposal)
            self.decisions.append({"action": "CALL", **proposal})
            message = AIMessage(content="", tool_calls=[{
                **proposal,
                "id": "hf01-explicit-order-proposal",
            }])
        else:
            result = self._tool_payload(tool_messages[-1])
            facts = result.get("facts", {}) if isinstance(result, dict) else {}
            body = facts.get("body", {})
            text = (
                f"订单读取返回 HTTP {facts.get('http_status')}，订单 {body.get('order_id')} "
                f"状态为 {body.get('status')}。"
            ) if facts else "该订单读取请求未返回可信业务事实。"
            self.decisions.append({"action": "ANSWER", "answer": text})
            message = AIMessage(content=text)

        message.usage_metadata = {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15}
        return ChatResult(generations=[ChatGeneration(message=message)])


def _capture_trace(case_id: str, records: list[dict]) -> None:
    target = os.environ.get("OPSPILOT_AR02_JOURNEY_HF01_TRACE")
    if not target:
        return
    path = Path(target)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as stream:
        for record in records:
            stream.write(json.dumps({"case_id": case_id, **record}, ensure_ascii=False, sort_keys=True) + "\n")


def _call_records(connection, run_id: str) -> list[dict]:
    rows = connection.execute(
        "SELECT * FROM assistant_calls WHERE run_id=? ORDER BY created_at", (run_id,)
    ).fetchall()
    result = []
    for row in rows:
        item = dict(row)
        for key in ("request_json", "result_json"):
            value = item.get(key)
            if value:
                try:
                    item[key.removesuffix("_json")] = json.loads(value)
                except (TypeError, json.JSONDecodeError):
                    pass
        result.append(item)
    return result


def _login(client, origin: str, passwords: dict[str, str]) -> dict[str, str]:
    login = client.post(
        "/api/auth/login",
        headers={"Origin": origin},
        json={"actor_id": "support-a", "password": passwords["support-a"]},
    )
    assert login.status_code == 200, login.text
    return {"Origin": origin, "X-CSRF-Token": login.json()["csrf_token"]}


def test_same_task_event_and_question_turn_missing_receiver_observation_into_unknown(
    demo_db, tmp_path, monkeypatch
):
    from fastapi.testclient import TestClient
    from opspilot.domain.database import connect
    from opspilot.domain.s3 import prepare_s3_fixture
    from opspilot.web.app import create_app
    from test_ar02_assistant import ORIGIN, PASSWORDS

    setup = prepare_s3_fixture(demo_db, "DELIVERED_PENDING", order_id="hf01-receiver-order", contract_version=2)
    event_id = setup["transport_trace"][0]["request"]["event_id"]
    models = [
        JourneyFixtureModel(mode="s01"),
        ReceiverAvailabilityFixture(mode="unused", query_receiver=True),
        ReceiverAvailabilityFixture(mode="unused", query_receiver=False),
    ]
    model_queue = deque(models)
    app = create_app(
        db_path=demo_db,
        checkpoint_db_path=tmp_path / "hf01-receiver.sqlite3",
        start_worker=True,
        credentials=PASSWORDS,
        expected_origin=ORIGIN,
        assistant_model_factory=lambda: model_queue.popleft(),
    )
    trace_records = []
    same_question = "请依据当前 Receiver 查询，说明同一订单回调是否已经处理完成；若没有当前状态请明确说明无法确认。"

    with TestClient(app) as client:
        headers = _login(client, ORIGIN, PASSWORDS)
        session_id = client.post("/api/sessions", headers=headers).json()["session_id"]
        binding_response = client.post(
            f"/api/sessions/{session_id}/assistant/order",
            headers={**headers, "Idempotency-Key": "hf01-receiver-bind"},
            json={"order_id": "hf01-receiver-order", "initial_message": "请绑定并开始核查该授权订单。"},
        )
        assert binding_response.status_code == 202, binding_response.text
        binding = binding_response.json()
        assert _wait_run(client, binding["run_id"])["status"] == "SUCCEEDED"
        task_id = binding["task_id"]

        accepted = []
        for index in range(2):
            response = client.post(
                f"/api/sessions/{session_id}/assistant/messages",
                headers={**headers, "Idempotency-Key": f"hf01-receiver-question-{index}"},
                json={"body": same_question, "task_id": task_id},
            )
            assert response.status_code == 202, response.text
            item = response.json()
            accepted.append(item)
            assert _wait_run(client, item["run_id"])["status"] == "SUCCEEDED"

        messages = client.get(f"/api/sessions/{session_id}/messages").json()["items"]
        answers = {item.get("answer_source_message_id"): item for item in messages if item["role"] == "ASSISTANT"}
        queued_answer = answers[accepted[0]["message_id"]]["body"]
        unknown_answer = answers[accepted[1]["message_id"]]["body"]
        assert queued_answer.count("QUEUED") == 1
        assert "尚不能确认处理完成" in queued_answer
        assert "UNKNOWN" in unknown_answer and "无法确认" in unknown_answer
        assert "已处理完成" not in unknown_answer

        from opspilot.domain.database import connect
        with connect(demo_db) as connection:
            calls_by_run = {item["run_id"]: _call_records(connection, item["run_id"]) for item in accepted}
            delivery_by_run = {}
            delivery_calls_by_run = {}
            receiver_calls_by_run = {}
            for item in accepted:
                calls = [call for call in calls_by_run[item["run_id"]] if call["kind"] == "MCP"]
                delivery_call = next(call for call in calls if call.get("request", {}).get("name") == "get_callback_delivery")
                delivery_calls_by_run[item["run_id"]] = delivery_call
                delivery_by_run[item["run_id"]] = delivery_call["result"]["facts"]
                receiver_calls_by_run[item["run_id"]] = [
                    call for call in calls if call.get("request", {}).get("name") == "get_receiver_processing"
                ]
            assert delivery_by_run[accepted[0]["run_id"]]["event_id"] == event_id
            assert delivery_by_run[accepted[1]["run_id"]]["event_id"] == event_id
            queued_receiver = receiver_calls_by_run[accepted[0]["run_id"]]
            assert len(queued_receiver) == 1
            assert queued_receiver[0]["result"]["facts"]["status"] == "QUEUED"
            receiver_observations_first = connection.execute(
                """SELECT o.observation_id,o.status,o.evidence_id,o.attempt_id,o.tool_name,a.run_id
                   FROM d2_tool_observations o JOIN d2_attempts a
                     ON a.attempt_id=o.attempt_id AND a.task_id=o.task_id
                   WHERE a.run_id=? AND o.tool_name='get_receiver_processing'""",
                (accepted[0]["run_id"],),
            ).fetchall()
            assert len(receiver_observations_first) == 1
            assert receiver_observations_first[0]["status"] == "OK"
            assert receiver_observations_first[0]["evidence_id"]
            assert receiver_observations_first[0]["observation_id"] == queued_receiver[0]["observation_id"]
            assert receiver_calls_by_run[accepted[1]["run_id"]] == []
            receiver_observations_second = connection.execute(
                """SELECT o.observation_id,o.status,o.evidence_id,o.attempt_id,o.tool_name,a.run_id
                   FROM d2_tool_observations o JOIN d2_attempts a
                     ON a.attempt_id=o.attempt_id AND a.task_id=o.task_id
                   WHERE a.run_id=? AND o.tool_name='get_receiver_processing'""",
                (accepted[1]["run_id"],),
            ).fetchall()
            assert receiver_observations_second == []

        trace_records.extend([
            {
                "stage": "queued_current_receiver",
                "session_id": session_id,
                "task_id": task_id,
                "user_message_id": accepted[0]["message_id"],
                "run_id": accepted[0]["run_id"],
                "question": same_question,
                "tools_offered": models[1].offered_tool_names,
                "model_decisions": models[1].decisions,
                "order_id": "hf01-receiver-order",
                "delivery_event_id": event_id,
                "delivery_evidence_id": delivery_calls_by_run[accepted[0]["run_id"]]["evidence_id"],
                "delivery_observation_id": delivery_calls_by_run[accepted[0]["run_id"]]["observation_id"],
                "receiver_fact": "QUEUED",
                "receiver_evidence_id": receiver_observations_first[0]["evidence_id"],
                "receiver_observation_id": receiver_observations_first[0]["observation_id"],
                "receiver_attempt_id": receiver_observations_first[0]["attempt_id"],
                "answer": queued_answer,
            },
            {
                "stage": "missing_current_receiver_observation",
                "session_id": session_id,
                "task_id": task_id,
                "user_message_id": accepted[1]["message_id"],
                "run_id": accepted[1]["run_id"],
                "question": same_question,
                "tools_offered": models[2].offered_tool_names,
                "model_decisions": models[2].decisions,
                "order_id": "hf01-receiver-order",
                "delivery_event_id": event_id,
                "delivery_evidence_id": delivery_calls_by_run[accepted[1]["run_id"]]["evidence_id"],
                "delivery_observation_id": delivery_calls_by_run[accepted[1]["run_id"]]["observation_id"],
                "receiver_observation": None,
                "receiver_observation_rows_for_run": 0,
                "answer": unknown_answer,
            },
        ])

    _capture_trace("HF01-01", trace_records)


def test_unbound_explicit_order_tool_proposal_is_not_executed_and_binding_allows_same_request(
    demo_db, tmp_path, monkeypatch
):
    from fastapi.testclient import TestClient
    from opspilot.domain.database import connect
    from opspilot.domain.s3 import prepare_s3_fixture
    from opspilot.web.app import create_app
    from test_ar02_assistant import ORIGIN, PASSWORDS

    prepare_s3_fixture(demo_db, "PROCESSING", order_id="hf01-bound-order", contract_version=2)
    unbound_model = ExplicitOrderProposalFixture(mode="unused")
    bound_model = ExplicitOrderProposalFixture(mode="unused")
    models = deque([unbound_model, bound_model])
    app = create_app(
        db_path=demo_db,
        checkpoint_db_path=tmp_path / "hf01-binding.sqlite3",
        start_worker=True,
        credentials=PASSWORDS,
        expected_origin=ORIGIN,
        assistant_model_factory=lambda: models.popleft(),
    )
    question = "请查询订单 hf01-bound-order 的当前订单状态。"
    trace_records = []

    with TestClient(app) as client:
        headers = _login(client, ORIGIN, PASSWORDS)
        session_id = client.post("/api/sessions", headers=headers).json()["session_id"]

        with connect(demo_db) as connection:
            http_before = connection.execute("SELECT COUNT(*) FROM s3_http_observations").fetchone()[0]
        unbound_response = client.post(
            f"/api/sessions/{session_id}/assistant/messages",
            headers={**headers, "Idempotency-Key": "hf01-order-unbound"},
            json={"body": question},
        )
        assert unbound_response.status_code == 202, unbound_response.text
        unbound = unbound_response.json()
        unbound_run = _wait_run(client, unbound["run_id"])
        assert unbound_run["status"] in {"SUCCEEDED", "FAILED", "BLOCKED"}
        assert unbound_model.proposals == [{
            "name": "get_order_status",
            "args": {"reason": "按用户请求查询当前绑定订单状态"},
        }]
        assert "get_order_status" not in unbound_model.offered_tool_names

        from opspilot.domain.database import connect
        with connect(demo_db) as connection:
            run_row = connection.execute("SELECT task_id FROM task_runs WHERE run_id=?", (unbound["run_id"],)).fetchone()
            assert run_row["task_id"] is None
            assert connection.execute("SELECT COUNT(*) FROM task_bindings").fetchone()[0] == 0
            unbound_mcp_rows = connection.execute(
                "SELECT * FROM assistant_calls WHERE run_id=? AND kind='MCP'", (unbound["run_id"],)
            ).fetchall()
            # The middleware records the model's attempted name before the
            # ToolNode rejects it. This is not an MCP server result or read.
            # The durable refusal is FAILED/NOT_STARTED, never an OK/null fact.
            assert len(unbound_mcp_rows) == 1
            unbound_mcp = unbound_mcp_rows[0]
            assert json.loads(unbound_mcp["request_json"])["name"] == "get_order_status"
            assert unbound_mcp["status"] == "FAILED"
            refusal = json.loads(unbound_mcp["result_json"])
            assert refusal == {
                "dispatch": "NOT_STARTED",
                "error": "ASSISTANT_TOOL_NOT_EXPOSED",
            }
            assert unbound_mcp["observation_id"] is None
            assert unbound_mcp["evidence_id"] is None
            assert connection.execute(
                """SELECT COUNT(*) FROM d2_tool_observations o JOIN d2_attempts a
                   ON a.attempt_id=o.attempt_id AND a.task_id=o.task_id WHERE a.run_id=?""",
                (unbound["run_id"],),
            ).fetchone()[0] == 0
            assert connection.execute("SELECT COUNT(*) FROM s3_http_observations").fetchone()[0] == http_before

        resources = client.get("/api/s3/order-resources", headers=headers)
        assert resources.status_code == 200, resources.text
        assert any(item["order_id"] == "hf01-bound-order" for item in resources.json()["items"])
        bound_response = client.post(
            f"/api/sessions/{session_id}/assistant/order",
            headers={**headers, "Idempotency-Key": "hf01-order-bound"},
            json={"order_id": "hf01-bound-order", "initial_message": question},
        )
        assert bound_response.status_code == 202, bound_response.text
        bound = bound_response.json()
        assert _wait_run(client, bound["run_id"])["status"] == "SUCCEEDED"
        assert "get_order_status" in bound_model.offered_tool_names

        with connect(demo_db) as connection:
            bound_call = connection.execute(
                """SELECT * FROM assistant_calls WHERE run_id=? AND kind='MCP'
                   ORDER BY created_at""",
                (bound["run_id"],),
            ).fetchone()
            assert bound_call is not None
            assert json.loads(bound_call["request_json"])["name"] == "get_order_status"
            tool_result = json.loads(bound_call["result_json"])
            assert tool_result["facts"]["http_status"] == 200
            assert tool_result["facts"]["body"]["order_id"] == "hf01-bound-order"
            assert bound_call["evidence_id"] and bound_call["observation_id"]
            order_http_request_id = tool_result["facts"]["body"]["request_id"]
            business_observation = connection.execute(
                """SELECT o.observation_id,o.status,o.evidence_id,o.attempt_id,o.tool_name,a.run_id
                   FROM d2_tool_observations o JOIN d2_attempts a
                     ON a.attempt_id=o.attempt_id AND a.task_id=o.task_id
                   WHERE o.observation_id=? AND o.evidence_id=?""",
                (bound_call["observation_id"], bound_call["evidence_id"]),
            ).fetchone()
            assert business_observation is not None
            assert business_observation["status"] == "OK"
            assert business_observation["tool_name"] == "get_order_status"
            assert business_observation["run_id"] == bound["run_id"]
            order_http_observation = connection.execute(
                "SELECT * FROM s3_http_observations WHERE request_id=?", (order_http_request_id,)
            ).fetchone()
            assert order_http_observation is not None
            assert order_http_observation["http_status"] == 200
            assert connection.execute("SELECT COUNT(*) FROM s3_http_observations").fetchone()[0] == http_before + 1

        trace_records.extend([
            {
                "stage": "unbound_model_proposal",
                "session_id": session_id,
                "user_message_id": unbound["message_id"],
                "run_id": unbound["run_id"],
                "question": question,
                "model_proposals": unbound_model.proposals,
                "tools_exposed": unbound_model.offered_tool_names,
                "run_status": unbound_run["status"],
                "mcp_tool_attempt_record": {
                    "assistant_call_id": unbound_mcp["call_id"],
                    "name": "get_order_status",
                    "audit_status": unbound_mcp["status"],
                    "server_result": None,
                    "evidence_id": None,
                    "observation_id": None,
                },
                "d2_observations": 0,
                "s3_http_observations_before_after": [http_before, http_before],
            },
            {
                "stage": "same_question_after_trusted_binding",
                "session_id": session_id,
                "task_id": bound["task_id"],
                "user_message_id": bound["message_id"],
                "run_id": bound["run_id"],
                "question": question,
                "model_proposals": bound_model.proposals,
                "tools_exposed": bound_model.offered_tool_names,
                "order_http_status": 200,
                "order_http_request_id": order_http_request_id,
                "order_http_route": order_http_observation["route"],
                "integration_id": order_http_observation["integration_id"],
                "principal_id": order_http_observation["principal_id"],
                "order_id": "hf01-bound-order",
                "assistant_call_id": bound_call["call_id"],
                "evidence_id": bound_call["evidence_id"],
                "observation_id": bound_call["observation_id"],
                "attempt_id": business_observation["attempt_id"],
                "s3_http_observation_count": http_before + 1,
            },
        ])

    _capture_trace("HF01-02", trace_records)
