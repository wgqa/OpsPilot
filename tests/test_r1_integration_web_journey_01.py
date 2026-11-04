"""Offline API/Worker continuity probe for the R1 integrated journey.

This is deterministic FixtureModel evidence. It does not exercise a browser
or claim real-model autonomy.
"""
from __future__ import annotations

import json
from collections import deque

from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from opspilot.domain.database import connect
from opspilot.domain.s3 import prepare_s3_fixture
from opspilot.web.app import create_app
from test_ar02_ar03_integration_01 import IntegrationFixtureModel, _login, _wait_run


class MaterialAwareFixtureModel(IntegrationFixtureModel):
    """Respond from the actual outgoing same-Session user-material context."""

    @property
    def _llm_type(self):
        return "R1_OFFLINE_MATERIAL_FIXTURE"

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        self.seen.append(messages)
        outgoing = "\n".join(str(getattr(message, "content", "")) for message in messages)
        if '"max_attempts":5' in outgoing:
            answer = (
                "你提供的示例配置包含 max_attempts=5；这属于用户提供的待核实材料，"
                "不能证明线上部署值。结合上轮协议资料，建议核对部署配置后再确认重试影响。"
            )
        else:
            answer = "当前出站上下文未包含所提供配置，不能据此判断重试影响。"
        self.decisions.append({"action": "ANSWER", "basis": "same-session-user-material"})
        message = AIMessage(content=answer)
        message.usage_metadata = {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15}
        return ChatResult(generations=[ChatGeneration(message=message)])


class R1BoundStateFixtureModel(IntegrationFixtureModel):
    """Use only current Event reads; prior protocol context is already in Session."""

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        self.seen.append(messages)
        names_by_id = {
            call.get("id"): call.get("name")
            for message in messages
            if isinstance(message, AIMessage)
            for call in (getattr(message, "tool_calls", []) or [])
        }
        payloads = {
            names_by_id.get(message.tool_call_id): self._payload(message)
            for message in messages
            if hasattr(message, "tool_call_id")
        }
        selected = next(
            (name for name in ("get_callback_delivery", "get_receiver_processing") if name not in payloads),
            None,
        )
        if selected:
            args = {"reason": "核实当前 TaskBinding 下的同一事件状态"}
            tool_call_id = f"r1-bound-{self.mode}-{len(self.decisions)}"
            self.decisions.append({"action": "CALL", "tool": selected, "tool_call_id": tool_call_id})
            message = AIMessage(content="", tool_calls=[{
                "name": selected, "args": args,
                "id": tool_call_id,
            }])
        else:
            delivery = payloads["get_callback_delivery"].get("facts", {})
            receiver = payloads["get_receiver_processing"].get("facts", {})
            same_event = delivery.get("event_id") == receiver.get("event_id")
            state = receiver.get("status") if same_event else "UNKNOWN"
            if state == "PROCESSED":
                conclusion = "同一 Event 的当前 Receiver Observation 为 PROCESSED；只能确认该事件已处理。"
            elif state == "QUEUED":
                conclusion = "Delivery HTTP 202/ACKNOWLEDGED 只表示受理；同一 Event 的 Receiver 当前为 QUEUED，尚不能称为处理完成。"
            else:
                conclusion = "当前无法从匹配的同一 Event Observation 确认接收方状态。"
            self.decisions.append({"action": "ANSWER"})
            message = AIMessage(content=conclusion + " 线上部署版本仍未知；仅整理说明，不提交业务操作。")
        message.usage_metadata = {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15}
        return ChatResult(generations=[ChatGeneration(message=message)])


def test_r1_offline_api_worker_same_session_protocol_material_binding_and_followup(
    demo_db, tmp_path,
):
    setup = prepare_s3_fixture(
        demo_db, "DELIVERED_PENDING", order_id="ar03-order", contract_version=2,
    )
    material_model = MaterialAwareFixtureModel(mode="material")
    model_instances = [
        IntegrationFixtureModel(mode="unbound"),
        material_model,
        R1BoundStateFixtureModel(mode="bound", receiver_state="QUEUED"),
        R1BoundStateFixtureModel(mode="bound", receiver_state="QUEUED"),
    ]
    models = deque(model_instances)
    from test_ar02_assistant import ORIGIN, PASSWORDS

    app = create_app(
        db_path=demo_db,
        checkpoint_db_path=tmp_path / "r1-offline-worker.sqlite3",
        start_worker=True,
        credentials=PASSWORDS,
        expected_origin=ORIGIN,
        assistant_model_factory=lambda: models.popleft(),
    )
    accepted = []

    with TestClient(app) as client:
        headers = _login(client)
        session_id = client.post("/api/sessions", headers=headers).json()["session_id"]

        # J1: protocol consultation works without a TaskBinding.
        j1 = client.post(
            f"/api/sessions/{session_id}/assistant/messages",
            headers={**headers, "Idempotency-Key": "r1-j1-protocol"},
            json={"body": "我们准备从旧回调协议升级到新版，需要修改哪些内容？"},
        )
        assert j1.status_code == 202, j1.text
        j1_item = j1.json()
        accepted.append(j1_item)
        assert _wait_run(client, j1_item["run_id"])["status"] == "SUCCEEDED"

        # J2: a pasted configuration remains user material in the same Session.
        material = (
            "结合这份配置，哪些地方需要改？之前的结论还成立吗？\n"
            "```json\n{\"retry\":{\"max_attempts\":5}}\n```"
        )
        j2 = client.post(
            f"/api/sessions/{session_id}/assistant/messages",
            headers={**headers, "Idempotency-Key": "r1-j2-material"},
            json={"body": material},
        )
        assert j2.status_code == 202, j2.text
        j2_item = j2.json()
        accepted.append(j2_item)
        assert _wait_run(client, j2_item["run_id"])["status"] == "SUCCEEDED"

        # J3: only the trusted order endpoint establishes TaskBinding and starts
        # the current investigation. Chat text did not grant this access.
        resources = client.get("/api/s3/order-resources", headers=headers)
        assert resources.status_code == 200, resources.text
        assert any(item["order_id"] == "ar03-order" for item in resources.json()["items"])
        bind = client.post(
            f"/api/sessions/{session_id}/assistant/order",
            headers={**headers, "Idempotency-Key": "r1-j3-bind-investigate"},
            json={
                "order_id": "ar03-order",
                "initial_message": "请结合适用协议查询这个订单的回调事件目前是否处理完成，并说明未知事项。",
            },
        )
        assert bind.status_code == 202, bind.text
        bind_item = bind.json()
        accepted.append(bind_item)
        task_id = bind_item["task_id"]
        assert task_id
        assert _wait_run(client, bind_item["run_id"])["status"] == "SUCCEEDED"

        # J4: a same-Task follow-up performs a fresh Run and can be restored by
        # re-reading persistent messages. This does not simulate a browser.
        j4 = client.post(
            f"/api/sessions/{session_id}/assistant/messages",
            headers={**headers, "Idempotency-Key": "r1-j4-followup"},
            json={
                "body": "回到刚才这个事件：接收方现在完成了吗？请基于当前同一事件证据回答。",
                "task_id": task_id,
            },
        )
        assert j4.status_code == 202, j4.text
        j4_item = j4.json()
        accepted.append(j4_item)
        assert _wait_run(client, j4_item["run_id"])["status"] == "SUCCEEDED"

        first_read = client.get(f"/api/sessions/{session_id}/messages?limit=500")
        second_read = client.get(f"/api/sessions/{session_id}/messages?limit=500")
        assert first_read.status_code == second_read.status_code == 200
        messages = first_read.json()["items"]
        restored = second_read.json()["items"]
        assert [(item["message_id"], item["body"]) for item in messages] == [
            (item["message_id"], item["body"]) for item in restored
        ]
        answers = {
            item["answer_source_message_id"]: item
            for item in messages
            if item["role"] == "ASSISTANT"
        }
        assert set(answers) == {item["message_id"] for item in accepted}
        assert "callback-retry-contract" in answers[j1_item["message_id"]]["body"]
        assert "max_attempts=5" in answers[j2_item["message_id"]]["body"]
        assert "用户提供的待核实材料" in answers[j2_item["message_id"]]["body"]
        assert "QUEUED" in answers[bind_item["message_id"]]["body"]
        assert "QUEUED" in answers[j4_item["message_id"]]["body"]

        with connect(demo_db) as connection:
            runs = connection.execute(
                "SELECT run_id,task_id,source_message_id,kind,status FROM task_runs "
                "WHERE session_id=? ORDER BY created_at,run_id", (session_id,),
            ).fetchall()
            assert len(runs) == 4
            assert [row["run_id"] for row in runs] == [item["run_id"] for item in accepted]
            assert runs[0]["task_id"] is None and runs[1]["task_id"] is None
            assert runs[2]["task_id"] == runs[3]["task_id"] == task_id

            j2_wire = connection.execute(
                "SELECT request_json FROM assistant_calls WHERE run_id=? AND kind='MODEL' ORDER BY created_at LIMIT 1",
                (j2_item["run_id"],),
            ).fetchone()
            assert j2_wire is not None
            serialized_messages = json.loads(j2_wire["request_json"])["messages"]
            j2_context = "\n".join(
                str(message.get("data", {}).get("content", ""))
                for message in serialized_messages
            )
            assert any(
                '"max_attempts":5' in message.get("data", {}).get("content", "")
                for message in serialized_messages if message.get("type") == "human"
            )
            assert "callback-retry-contract" in j2_context

            protocol_run_id = j1_item["run_id"]
            investigation_run_ids = (bind_item["run_id"], j4_item["run_id"])
            mcp_run_ids = (protocol_run_id, *investigation_run_ids)
            mcp_rows = connection.execute(
                "SELECT call_id,run_id,logical_key,status,observation_id,evidence_id,result_json "
                "FROM assistant_calls WHERE kind='MCP' AND run_id IN (?,?,?) ORDER BY created_at",
                mcp_run_ids,
            ).fetchall()
            tool_names_by_call_id = {
                decision["tool_call_id"]: decision["tool"]
                for model in model_instances for decision in model.decisions
                if decision.get("tool_call_id") and decision.get("tool")
            }
            persisted_mcp = []
            for row in mcp_rows:
                result = json.loads(row["result_json"])
                facts = result.get("facts", {})
                persisted_mcp.append({
                    "call_id": row["call_id"], "run_id": row["run_id"],
                    "tool_call_id": row["logical_key"],
                    "tool": tool_names_by_call_id.get(row["logical_key"]),
                    "status": row["status"], "observation_id": row["observation_id"],
                    "evidence_id": row["evidence_id"], "fact_type": result.get("fact_type"),
                    "task_id": result.get("task_id"), "observed_at": result.get("observed_at"),
                    "event_id": facts.get("event_id"), "order_id": facts.get("order_id"),
                    "business_status": facts.get("status"),
                    "http_status": facts.get("receiver_http_status"),
                    "observed_versions": result.get("observed_versions"),
                    "protocol_documents": [
                        {key: document.get(key) for key in ("document_id", "version", "digest", "source")}
                        for document in result.get("protocol_documents", [])
                    ],
                    "comparison": {
                        key: result.get(key) for key in (
                            "base_document_id", "target_document_id", "diff_count",
                            "comparison_digest", "deployment_version_verified",
                        ) if key in result
                    } or None,
                })
            assert len(persisted_mcp) == 6
            assert all(row["status"] == "OK" for row in persisted_mcp)
            protocol_discovery = next(
                row for row in persisted_mcp if row["tool"] == "list_scoped_protocol_documents"
            )
            assert {
                document["document_id"] for document in protocol_discovery["protocol_documents"]
            } >= {"callback-retry-contract", "callback-retry-contract-v2"}
            protocol_comparison = next(
                row for row in persisted_mcp if row["tool"] == "compare_scoped_protocols"
            )
            assert protocol_comparison["comparison"]["deployment_version_verified"] is False
            for run_id in investigation_run_ids:
                run_facts = [row for row in persisted_mcp if row["run_id"] == run_id]
                by_fact_type = {row["fact_type"]: row for row in run_facts}
                delivery = by_fact_type["s3_delivery"]
                receiver = by_fact_type["s3_receiver"]
                assert delivery["task_id"] == receiver["task_id"] == task_id
                assert delivery["event_id"] == receiver["event_id"]
                assert delivery["business_status"] == "ACKNOWLEDGED"
                assert delivery["http_status"] == 202
                assert receiver["business_status"] == "QUEUED"
                assert all((row["observation_id"] and row["evidence_id"]) for row in run_facts)

            protected_counts = {
                table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                for table in (
                    "s3_diagnoses", "d3_plans", "d3_approvals", "d3_action_intents",
                    "d3_action_ledgers", "d3_verification_receipts", "d3_delivery_records",
                    "s2_handoff_queue_entries", "s2_handoff_receipts",
                    "s3_handoff_queue_entries", "s3_handoff_receipts",
                )
            }
        assert all(count == 0 for count in protected_counts.values())
        assert setup["agent_actions"] == []

        trace = {
            "evidence_level": "OFFLINE_FIXTURE_MODEL_FORMAL_API_WORKER_MCP_DOMAIN",
            "browser_run": False,
            "provider_http_requests": 0,
            "session_id": session_id,
            "task_id": task_id,
            "turns": [
                {"journey": "J1", "run_id": j1_item["run_id"], "message_id": j1_item["message_id"],
                 "answer": answers[j1_item["message_id"]]["body"]},
                {"journey": "J2", "run_id": j2_item["run_id"], "message_id": j2_item["message_id"],
                 "answer": answers[j2_item["message_id"]]["body"], "user_material_present_in_outbound_context": True},
                {"journey": "J3", "run_id": bind_item["run_id"], "message_id": bind_item["message_id"],
                 "answer": answers[bind_item["message_id"]]["body"]},
                {"journey": "J4", "run_id": j4_item["run_id"], "message_id": j4_item["message_id"],
                 "answer": answers[j4_item["message_id"]]["body"], "refresh_stable_ids": True},
            ],
            "protected_business_writes": protected_counts,
            "fixture_agent_actions": setup["agent_actions"],
            "decisions": [model.decisions for model in model_instances],
            "mcp_calls": persisted_mcp,
        }
        print("R1_OFFLINE_TRACE " + json.dumps(trace, ensure_ascii=True, sort_keys=True))
