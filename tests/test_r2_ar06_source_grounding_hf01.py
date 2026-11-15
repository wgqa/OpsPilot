from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import Field

from opspilot.assistant import SYSTEM
from opspilot.domain.database import connect
from opspilot.domain.s3 import prepare_s3_fixture
from opspilot.web.app import create_app
from test_ar02_assistant import ORIGIN, PASSWORDS
from test_ar02_ar03_integration_01 import _login, _wait_run


class SourceGroundingFixtureModel(BaseChatModel):
    seen: list[list[object]] = Field(default_factory=list)
    offered_tool_descriptions: dict[str, str] = Field(default_factory=dict)

    @property
    def _llm_type(self) -> str:
        return "R2_AR06_SOURCE_GROUNDING_FIXTURE"

    def bind_tools(self, tools, **_kwargs):
        self.offered_tool_descriptions = {
            tool.name: str(getattr(tool, "description", "")) for tool in tools
        }
        return self

    def _generate(self, messages, stop=None, run_manager=None, **_kwargs):
        self.seen.append(list(messages))
        if not any(isinstance(message, ToolMessage) for message in messages):
            calls = [
                {"name": name, "args": {"reason": "读取当前绑定订单的来源字段"}, "id": f"ground-{name}"}
                for name in (
                    "get_order_status", "get_callback_delivery", "get_receiver_processing",
                )
            ]
            answer = AIMessage(content="", tool_calls=calls)
        else:
            # This is only a routing fixture. Semantic answer quality is not scored here.
            answer = AIMessage(content="Fixture completed after receiving the tool observations.")
        return ChatResult(generations=[ChatGeneration(message=answer)])


class NoObservationFixtureModel(BaseChatModel):
    seen: list[list[object]] = Field(default_factory=list)

    @property
    def _llm_type(self) -> str:
        return "R2_AR06_NO_OBSERVATION_FIXTURE"

    def bind_tools(self, _tools, **_kwargs):
        return self

    def _generate(self, messages, stop=None, run_manager=None, **_kwargs):
        self.seen.append(list(messages))
        return ChatResult(generations=[ChatGeneration(message=AIMessage(
            content="Fixture answer; no current business state was observed."
        ))])


def _tool_payloads(messages: list[object]) -> dict[str, dict]:
    payloads = {}
    for message in messages:
        if not isinstance(message, ToolMessage):
            continue
        value = message.content
        if isinstance(value, str):
            value = json.loads(value)
        while isinstance(value, dict) and set(value) == {"result"}:
            value = value["result"]
        assert isinstance(value, dict), (message.name, value)
        payloads[str(message.name)] = value
    return payloads


def _run_bound_order(demo_db, tmp_path, model, *, order_id: str):
    app = create_app(
        db_path=demo_db,
        checkpoint_db_path=tmp_path / f"{order_id}-checkpoint.sqlite3",
        start_worker=True,
        credentials=PASSWORDS,
        expected_origin=ORIGIN,
        heartbeat_seconds=0.05,
        assistant_model_factory=lambda: model,
        assistant_runtime_enabled=False,
    )
    with TestClient(app) as client:
        headers = _login(client)
        session_id = client.post("/api/sessions", headers=headers).json()["session_id"]
        response = client.post(
            f"/api/sessions/{session_id}/assistant/order",
            headers={**headers, "Idempotency-Key": f"source-ground-{order_id}"},
            json={"order_id": order_id, "initial_message": "请检查这个授权订单当前回调处理情况。"},
        )
        assert response.status_code == 202, response.text
        accepted = response.json()
        run = _wait_run(client, accepted["run_id"])
    assert run["status"] == "SUCCEEDED", run
    return accepted, model


@pytest.mark.parametrize("receiver_status", ["QUEUED", "PROCESSED"])
def test_order_delivery_receiver_fields_remain_source_scoped(
    demo_db, tmp_path, receiver_status,
):
    order_id = f"source-ground-{receiver_status.lower()}"
    prepare_s3_fixture(demo_db, "DELIVERED_PENDING", order_id=order_id, contract_version=2)
    if receiver_status == "PROCESSED":
        with connect(demo_db) as connection:
            connection.execute(
                "UPDATE s3_receivers SET status='PROCESSED',version=version+1 "
                "WHERE tenant_id='tenant-a' AND order_id=?", (order_id,),
            )

    model = SourceGroundingFixtureModel()
    accepted, _ = _run_bound_order(demo_db, tmp_path, model, order_id=order_id)
    assert accepted["task_id"]
    assert model.seen
    payloads = _tool_payloads(model.seen[-1])
    assert set(payloads) == {
        "get_order_status", "get_callback_delivery", "get_receiver_processing",
    }

    order_body = payloads["get_order_status"]["facts"]["body"]
    order_facts = payloads["get_order_status"]["facts"]
    delivery = payloads["get_callback_delivery"]["facts"]
    receiver = payloads["get_receiver_processing"]["facts"]
    assert "event_id" not in order_facts
    assert "event_id" not in order_body
    assert order_body["order_id"] == order_id
    assert order_body["status"] == "COMPLETED"
    assert isinstance(order_body["authn_event_id"], int)
    assert delivery["event_id"] == receiver["event_id"]
    assert receiver["status"] == receiver_status
    assert accepted["run_id"]

    assert "does not provide the callback business event_id" in model.offered_tool_descriptions[
        "get_order_status"
    ]
    assert "does not establish an event_id for the order Observation" in model.offered_tool_descriptions[
        "get_callback_delivery"
    ]
    assert "does not establish an event_id for the order Observation" in model.offered_tool_descriptions[
        "get_receiver_processing"
    ]

    all_text = "\n".join(
        str(getattr(message, "content", "")) for message in model.seen[-1]
    )
    assert "s3_order" in all_text and "authn_event_id" in all_text
    assert "Delivery" in all_text and "Receiver" in all_text


def test_mismatched_delivery_and_receiver_event_ids_are_not_collapsed(demo_db, tmp_path):
    order_id = "source-ground-different-events"
    prepare_s3_fixture(demo_db, "DELIVERED_PENDING", order_id=order_id, contract_version=2)
    with connect(demo_db) as connection:
        connection.execute(
            "UPDATE s3_receivers SET event_id=?,version=version+1 "
            "WHERE tenant_id='tenant-a' AND order_id=?",
            ("event-source-ground-decoy", order_id),
        )

    model = SourceGroundingFixtureModel()
    _run_bound_order(demo_db, tmp_path, model, order_id=order_id)
    payloads = _tool_payloads(model.seen[-1])
    delivery = payloads["get_callback_delivery"]["facts"]
    receiver = payloads["get_receiver_processing"]["facts"]
    assert delivery["event_id"] != receiver["event_id"]
    assert receiver["status"] == "QUEUED"


def test_no_current_business_observation_is_visible_without_a_binding(demo_db, tmp_path):
    model = NoObservationFixtureModel()
    app = create_app(
        db_path=demo_db,
        checkpoint_db_path=tmp_path / "no-observation-checkpoint.sqlite3",
        start_worker=True,
        credentials=PASSWORDS,
        expected_origin=ORIGIN,
        heartbeat_seconds=0.05,
        assistant_model_factory=lambda: model,
        assistant_runtime_enabled=False,
    )
    with TestClient(app) as client:
        headers = _login(client)
        session_id = client.post("/api/sessions", headers=headers).json()["session_id"]
        response = client.post(
            f"/api/sessions/{session_id}/assistant/messages",
            headers={**headers, "Idempotency-Key": "source-ground-no-observation"},
            json={"body": "请核查这个订单目前是否已处理。"},
        )
        assert response.status_code == 202, response.text
        run = _wait_run(client, response.json()["run_id"])
    assert run["status"] == "SUCCEEDED", run
    assert model.seen
    assert not any(isinstance(message, ToolMessage) for message in model.seen[-1])
    sent_system = str(model.seen[-1][0].content)
    assert "没有本 Run 有效的订单 Observation，就不能声称当前订单状态" in sent_system


def test_source_grounding_guidance_is_present_without_fixed_tool_order():
    assert "每项业务事实只能归因于实际返回该字段的 Observation" in SYSTEM
    assert "s3_order 的订单 Observation" in SYSTEM
    assert "不提供业务 event_id" in SYSTEM
    assert "authn_event_id 是认证事件标识" in SYSTEM
    assert "Delivery 与 Receiver Observation 各自明确返回相同 event_id" in SYSTEM
    assert "任一 ID 缺失、不同或无法核实时，应说明关联未知" in SYSTEM
    assert "没有本 Run 有效的订单 Observation，就不能声称当前订单状态" in SYSTEM
    assert "不规定工具顺序" in SYSTEM
