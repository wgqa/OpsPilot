"""Offline regression for bounded historical context in formal ASSISTANT_V1."""
from __future__ import annotations

from collections import deque
import json
import os
import shutil
from pathlib import Path

from test_ar02_journey_p0 import JourneyFixtureModel, _wait_run


class InflatedHistoryFixture(JourneyFixtureModel):
    """Deterministic fixture that makes prior answers large without network use."""

    padding_chars: int = 1400

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        result = super()._generate(messages, stop=stop, run_manager=run_manager, **kwargs)
        message = result.generations[0].message
        if not message.tool_calls and self.mode in {"knowledge", "order"}:
            padding = ("历史线索必须保留来源并且不能冒充当前事实；" * (self.padding_chars // 20 + 1))[:self.padding_chars]
            message.content = str(message.content) + padding
        return result


def _record_trace(record: dict) -> None:
    target = os.environ.get("OPSPILOT_CONTEXT_CONTINUITY_TRACE")
    if not target:
        return
    path = Path(target)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def test_formal_s02_context_stays_bounded_through_s02_4_and_s02_5(
    demo_db, tmp_path, monkeypatch
):
    from fastapi.testclient import TestClient
    from opspilot.domain.database import connect
    from opspilot.domain.s3 import prepare_s3_fixture
    from opspilot.web.app import create_app
    from test_ar02_assistant import ORIGIN, PASSWORDS

    setup = prepare_s3_fixture(demo_db, "DELIVERED_PENDING", order_id="ar02-continuity-order", contract_version=2)
    models = [
        InflatedHistoryFixture(mode="knowledge", padding_chars=1600),
        InflatedHistoryFixture(mode="knowledge", padding_chars=1600),
        InflatedHistoryFixture(mode="order", padding_chars=1760),
        JourneyFixtureModel(mode="receiver"),
        JourneyFixtureModel(mode="draft"),
    ]
    queue = deque(models)
    app = create_app(
        db_path=demo_db,
        checkpoint_db_path=tmp_path / "context-continuity-checkpoint.sqlite3",
        start_worker=True,
        credentials=PASSWORDS,
        expected_origin=ORIGIN,
        assistant_model_factory=lambda: queue.popleft(),
    )

    with TestClient(app) as client:
        login = client.post(
            "/api/auth/login", headers={"Origin": ORIGIN},
            json={"actor_id": "support-a", "password": PASSWORDS["support-a"]},
        )
        assert login.status_code == 200, login.text
        headers = {"Origin": ORIGIN, "X-CSRF-Token": login.json()["csrf_token"]}
        session_id = client.post("/api/sessions", headers=headers).json()["session_id"]

        first_inputs = [
            "请记住下面是待核实的示例线索，不是你已验证的业务事实：`event_id=event-e1, transport_request_id=req-e1-1, delivery_http_status=202, receiver_status=unknown`。请查适用的回调/Receiver 协议，说明 202 能证明和不能证明什么。",
            "我现在确认要查询资料范围中已授权的回调协议；没有特别指定旧版，请按本问题适用范围核对。说明检索到的版本、摘要和来源。",
        ]
        prior = []
        for index, body in enumerate(first_inputs, start=1):
            response = client.post(
                f"/api/sessions/{session_id}/assistant/messages",
                headers={**headers, "Idempotency-Key": f"ctx-cont-s02-{index}"},
                json={"body": body},
            )
            assert response.status_code == 202, response.text
            item = response.json()
            prior.append(item)
            run = _wait_run(client, item["run_id"])
            assert run["status"] == "SUCCEEDED", run

        resources = client.get("/api/s3/order-resources", headers=headers)
        assert resources.status_code == 200, resources.text
        assert any(row["order_id"] == "ar02-continuity-order" for row in resources.json()["items"])
        binding = client.post(
            f"/api/sessions/{session_id}/assistant/order",
            headers={**headers, "Idempotency-Key": "ctx-cont-s02-bind"},
            json={
                "order_id": "ar02-continuity-order",
                "initial_message": "请绑定我有权访问的订单 `ar02-continuity-order` 并核查当前状态。",
            },
        )
        assert binding.status_code == 202, binding.text
        binding_item = binding.json()
        task_id = binding_item["task_id"]
        assert _wait_run(client, binding_item["run_id"])["status"] == "SUCCEEDED"

        questions = [
            "对照刚才的 E1 线索和本次真实查询，接收方现在处理完成了吗？",
            "基于刚才本 Run 的同 Event 观察整理一份处理说明草稿，并明确仍未知的部分。",
        ]
        final_items = []
        for index, body in enumerate(questions, start=4):
            response = client.post(
                f"/api/sessions/{session_id}/assistant/messages",
                headers={**headers, "Idempotency-Key": f"ctx-cont-s02-{index}"},
                json={"body": body, "task_id": task_id},
            )
            assert response.status_code == 202, response.text
            item = response.json()
            final_items.append(item)
            run = _wait_run(client, item["run_id"])
            if run["status"] != "SUCCEEDED":
                answers = [
                    row for row in client.get(f"/api/sessions/{session_id}/messages").json()["items"]
                    if row["role"] == "ASSISTANT" and row.get("answer_source_message_id") == item["message_id"]
                ]
                failure_body = answers[-1]["body"][:240] if answers else "NO_PERSISTED_NOTICE"
                raise AssertionError({
                    "turn": f"S02-{index}", "status": run["status"],
                    "blocked_reason": run.get("blocked_reason"), "notice": failure_body,
                })

        s02_4, s02_5 = final_items
        with connect(demo_db) as connection:
            model_rows = connection.execute(
                "SELECT request_json FROM assistant_calls WHERE run_id=? AND kind='MODEL' ORDER BY created_at",
                (s02_4["run_id"],),
            ).fetchall()
            assert model_rows, "S02-4 must reach the offline model through the formal worker"
            first_wire = json.loads(model_rows[0]["request_json"])
            budget = first_wire["context_budget"]
            assert budget["input_budget_tokens"] == 12000
            assert budget["estimated_input_tokens"] <= 12000
            refs = first_wire["source_refs"]
            assert refs["authority"] == "EXPLANATION_ONLY_NO_BUSINESS_RECEIPT"
            assert refs["trusted_binding"]["order_id"] == "ar02-continuity-order"
            assert all(
                record["authority"] == "HISTORICAL_LEAD_NOT_CURRENT_OBSERVATION"
                for record in refs["history_sources"]
            )
            sources = [source for record in refs["history_sources"] for source in record["sources"]]
            assert sources
            assert all(source.get("result_digest") for source in sources)
            assert all(source.get("completed_at") for source in sources)
            assert all(source["source_authority"] == "HISTORICAL_RUN_ONLY" for source in sources)
            assert all("result" not in source for source in sources), "historical payloads must be bounded projections"
            answer_refs = refs["prior_answers"]
            assert answer_refs and all(item.get("answer_digest") and item.get("created_at") for item in answer_refs)
            assert all("answer" not in item for item in answer_refs)
            pre_binding_refs = [
                item for item in answer_refs
                if item["content_location"] == "BOUNDED_PRE_BINDING_HISTORY_EXCERPT"
            ]
            assert len(pre_binding_refs) == 2
            assert all(item.get("answer_excerpt") and len(item["answer_excerpt"]) <= 270 for item in pre_binding_refs)
            assert any(
                source.get("summary", {}).get("documents")
                for source in sources
            ), "a still-valid Knowledge result should retain bounded versioned references"
            assert all(
                not ("event_id" in source.get("summary", {}).get("facts", {})
                     and source["summary"].get("authority") != "HISTORICAL_RUN_ONLY")
                for source in sources
            )

            current_calls = connection.execute(
                "SELECT request_json,result_json,status,observation_id,evidence_id FROM assistant_calls "
                "WHERE run_id=? AND kind='MCP' ORDER BY created_at", (s02_4["run_id"],)
            ).fetchall()
            requests_by_name = {json.loads(row["request_json"])["name"]: row for row in current_calls}
            assert set(requests_by_name) >= {
                "get_callback_delivery", "get_receiver_processing"
            }
            delivery = json.loads(requests_by_name["get_callback_delivery"]["result_json"])
            receiver = json.loads(requests_by_name["get_receiver_processing"]["result_json"])
            assert delivery["facts"]["event_id"] == receiver["facts"]["event_id"]
            assert receiver["facts"]["status"] == "QUEUED"
            assert all(row["status"] == "OK" and row["observation_id"] for row in current_calls)

            counts = connection.execute(
                "SELECT COUNT(*) FROM assistant_calls WHERE run_id=? AND kind='MODEL'", (s02_5["run_id"],)
            ).fetchone()[0]
            assert counts > 0
            wires = [json.loads(row["request_json"]) for row in model_rows]
            assert questions[0] in json.dumps(wires[0]["messages"], ensure_ascii=False)
            current_message_payloads = [json.dumps(wire["messages"], ensure_ascii=False) for wire in wires]
            assert any("QUEUED" in payload and "event_id" in payload for payload in current_message_payloads[1:])
            assert all(wire["context_budget"]["estimated_input_tokens"] <= 12_000 for wire in wires)

        messages = client.get(f"/api/sessions/{session_id}/messages").json()["items"]
        answer_by_source = {item.get("answer_source_message_id"): item for item in messages if item["role"] == "ASSISTANT"}
        answer_4 = answer_by_source[s02_4["message_id"]]
        answer_5 = answer_by_source[s02_5["message_id"]]
        assert "QUEUED" in answer_4["body"] and "处理完成" in answer_4["body"]
        assert "草稿" in answer_5["body"] and "未知" in answer_5["body"]
        assert setup["agent_actions"] == []
        _record_trace({
            "case_id": "CC01-S02-4",
            "evidence_level": "OFFLINE_DETERMINISTIC_FORMAL_API_WORKER_MCP_DOMAIN",
            "session_id": session_id,
            "task_id": task_id,
            "run_id": s02_4["run_id"],
            "source_message_id": s02_4["message_id"],
            "provider_calls": 0,
            "provider_model": "DETERMINISTIC_FIXTURE_ONLY",
            "actual_mcp_tools": sorted(requests_by_name),
            "same_event": delivery["facts"]["event_id"] == receiver["facts"]["event_id"],
            "receiver_status": receiver["facts"]["status"],
            "first_actual_outbound_estimated_tokens": budget["estimated_input_tokens"],
            "max_actual_outbound_estimated_tokens": max(
                wire["context_budget"]["estimated_input_tokens"] for wire in wires
            ),
            "actual_model_dispatches": len(wires),
            "input_budget_tokens": budget["input_budget_tokens"],
            "prior_source_count": len(sources),
            "pre_binding_answer_excerpt_count": len(pre_binding_refs),
            "s02_5_run_id": s02_5["run_id"],
            "s02_5_answer_source_message_id": answer_5.get("answer_source_message_id"),
        })

        # A later source revocation removes old Knowledge from the history
        # projection; it cannot survive through a saved summary/reference.
        from opspilot.domain import assistant as assistant_domain
        from opspilot.domain import assistant_knowledge

        registry_path = tmp_path / "revoked-assistant-access.json"
        shutil.copyfile(assistant_knowledge.REGISTRY, registry_path)
        monkeypatch.setattr(assistant_knowledge, "REGISTRY", registry_path)
        policy = json.loads(registry_path.read_text(encoding="utf-8"))
        policy["projects"][0]["grant_version"] += 1
        policy["projects"][0]["active"] = False
        registry_path.write_text(json.dumps(policy), encoding="utf-8")
        with connect(demo_db) as connection:
            current_run = dict(connection.execute(
                "SELECT * FROM task_runs WHERE run_id=?", (s02_5["run_id"],)
            ).fetchone())
            revoked_history = assistant_domain.history_sources(connection, current_run)
        old_knowledge = [
            record for record in revoked_history
            if any(source["summary"].get("documents") for source in record["sources"])
        ]
        assert not old_knowledge
        assert any(
            record["current_source_valid"] is False and record["sources"] == []
            for record in revoked_history
        )
        _record_trace({
            "case_id": "CC05-KNOWLEDGE-REVOCATION",
            "evidence_level": "OFFLINE_DETERMINISTIC_DOMAIN_REVALIDATION",
            "session_id": session_id,
            "task_id": task_id,
            "invalidated_run_ids": [record["run_id"] for record in revoked_history if not record["current_source_valid"]],
            "invalidated_sources_reintroduced": False,
        })


def test_current_run_over_budget_is_still_rejected_before_dispatch():
    from langchain_core.messages import HumanMessage
    import pytest
    from opspilot.domain.context_engineering import ContextBudgetExceeded, investigator_context_budget

    oversized = [HumanMessage(content="x " * 12_100)]
    with pytest.raises(ContextBudgetExceeded) as error:
        investigator_context_budget(oversized, "deepseek-flash", [], {})
    assert error.value.code == "INVESTIGATOR_CONTEXT_EXCEEDS_BUDGET"
    assert error.value.input_budget_tokens == 12_000
