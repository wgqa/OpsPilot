"""Offline AR-02/AR-03 integration checks; never evidence of real model autonomy."""
from __future__ import annotations

import copy
import json
import os
import time
import uuid
from collections import deque
from pathlib import Path

from pydantic import Field
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult

import pytest

from opspilot.domain import assistant as assistant_domain
from opspilot.domain.assistant_knowledge import KnowledgeScopeDenied
from opspilot.domain.task_control import create_session, trusted_identity


def _discovery(db, identity, session_id):
    from opspilot.domain.scoped_protocol_comparison import list_scoped_protocols

    return list_scoped_protocols(db, identity, session_id, topic="retry")


def _retry_pair(discovery):
    docs = discovery["protocol_documents"]
    old = next(doc for doc in docs if str(doc["version"]).startswith("1."))
    new = next(doc for doc in docs if str(doc["version"]).startswith("2."))
    return old, new


def test_scoped_protocol_discovery_is_current_and_fails_closed(demo_db):
    from opspilot.domain.scoped_protocol_comparison import scoped_discovery_is_current

    identity = trusted_identity(demo_db, "support-a")
    session_id = create_session(demo_db, identity)["session_id"]
    discovery = _discovery(demo_db, identity, session_id)
    assert discovery["protocol_documents"]
    assert all(doc["document_id"] and doc["version"] and doc["digest"] and doc["source"]
               for doc in discovery["protocol_documents"])
    assert discovery["deployment_version_verified"] is False
    assert scoped_discovery_is_current(demo_db, identity, session_id, discovery) == (True, None)

    other_session = create_session(demo_db, identity)["session_id"]
    assert not scoped_discovery_is_current(demo_db, identity, other_session, discovery)[0]

    other_actor = trusted_identity(demo_db, "support-b")
    assert not scoped_discovery_is_current(demo_db, other_actor, session_id, discovery)[0]

    from opspilot.domain.task_control import TrustedIdentity
    other_tenant = TrustedIdentity(actor_id="support-a", tenant_id="tenant-b", role="SUPPORT")
    assert not scoped_discovery_is_current(demo_db, other_tenant, session_id, discovery)[0]

    forged = copy.deepcopy(discovery)
    forged["protocol_documents"][0]["document_id"] = "api-scope-current"
    assert not scoped_discovery_is_current(demo_db, identity, session_id, forged)[0]

    digest_forgery = copy.deepcopy(discovery)
    digest_forgery["protocol_documents"][0]["digest"] = "0" * 64
    assert not scoped_discovery_is_current(demo_db, identity, session_id, digest_forgery)[0]


@pytest.mark.parametrize(
    "topic",
    [
        "retry", "callback", "callback retry", "callback retry protocol",
        "callback retry behavior", "回调", "重试", "回调重试", "回调 重试",
        "回调重试协议",
    ],
)
def test_scoped_protocol_discovery_matches_callback_retry_topics(demo_db, topic):
    from opspilot.domain.scoped_protocol_comparison import list_scoped_protocols

    identity = trusted_identity(demo_db, "support-a")
    session_id = create_session(demo_db, identity)["session_id"]
    result = list_scoped_protocols(demo_db, identity, session_id, topic=topic)
    document_ids = {document["document_id"] for document in result["protocol_documents"]}

    assert {"callback-retry-contract", "callback-retry-contract-v2"} <= document_ids
    assert result["tenant_id"] == identity.tenant_id
    assert result["actor_id"] == identity.actor_id
    assert result["scope_digest"]


def test_callback_retry_topic_rank_prefers_retry_family_and_empty_query_stays_empty(demo_db):
    from opspilot.domain.scoped_protocol_comparison import list_scoped_protocols

    identity = trusted_identity(demo_db, "support-a")
    session_id = create_session(demo_db, identity)["session_id"]
    ranked = list_scoped_protocols(demo_db, identity, session_id, topic="callback retry")
    ids = [document["document_id"] for document in ranked["protocol_documents"]]
    assert ids[:2] == ["callback-retry-contract", "callback-retry-contract-v2"]

    unrelated = list_scoped_protocols(demo_db, identity, session_id, topic="invoice color")
    assert unrelated["protocol_documents"] == []


def test_callback_retry_topic_match_does_not_expand_session_document_scope(demo_db):
    from opspilot.domain.scoped_protocol_comparison import list_scoped_protocols

    identity = trusted_identity(demo_db, "support-a")
    session_id = create_session(demo_db, identity)["session_id"]
    legal = list_scoped_protocols(demo_db, identity, session_id, topic="retry")
    legal_ids = {document["document_id"] for document in legal["protocol_documents"]}
    assert {"callback-retry-contract", "callback-retry-contract-v2"} <= legal_ids

    # The catalog contains API-scope documents, but this Session's selected
    # project does not authorize them. A broad/forged topic cannot widen it.
    outside = list_scoped_protocols(demo_db, identity, session_id, topic="api scope")
    outside_ids = {document["document_id"] for document in outside["protocol_documents"]}
    assert "api-scope-current" not in outside_ids

    other_actor = trusted_identity(demo_db, "support-b")
    with pytest.raises(KnowledgeScopeDenied):
        list_scoped_protocols(demo_db, other_actor, session_id, topic="retry")


def test_scoped_protocol_comparison_revalidates_all_visible_diff_fields(demo_db):
    from opspilot.domain.scoped_protocol_comparison import (
        compare_scoped_protocols,
        scoped_comparison_is_current,
    )

    identity = trusted_identity(demo_db, "support-a")
    session_id = create_session(demo_db, identity)["session_id"]
    discovered = _discovery(demo_db, identity, session_id)
    old, new = _retry_pair(discovered)
    comparison = compare_scoped_protocols(
        demo_db, identity, session_id,
        old["document_id"], new["document_id"],
        base_version=old["version"], target_version=new["version"],
    ).to_dict()
    assert comparison["diff_count"] > 0
    assert comparison["differences"]
    assert comparison["diff_evidence"]
    assert all(item.get("base_location") or item.get("target_location")
               for item in comparison["diff_evidence"])
    assert scoped_comparison_is_current(demo_db, identity, session_id, comparison) == (True, None)

    forged_summary = copy.deepcopy(comparison)
    forged_summary["summary"] = "The provider currently deploys v2."
    assert not scoped_comparison_is_current(demo_db, identity, session_id, forged_summary)[0]

    forged_excerpt = copy.deepcopy(comparison)
    forged_excerpt["diff_evidence"][0]["new_excerpt"] = "forged runtime fact"
    assert not scoped_comparison_is_current(demo_db, identity, session_id, forged_excerpt)[0]

    forged_diff = copy.deepcopy(comparison)
    forged_diff["differences"][0]["title"] = "forged"
    assert not scoped_comparison_is_current(demo_db, identity, session_id, forged_diff)[0]

    other_session = create_session(demo_db, identity)["session_id"]
    assert not scoped_comparison_is_current(demo_db, identity, other_session, comparison)[0]


def test_protocol_history_summary_is_bounded_and_never_current_evidence(demo_db):
    from opspilot.domain.scoped_protocol_comparison import compare_scoped_protocols

    identity = trusted_identity(demo_db, "support-a")
    session_id = create_session(demo_db, identity)["session_id"]
    discovered = _discovery(demo_db, identity, session_id)
    old, new = _retry_pair(discovered)
    comparison = compare_scoped_protocols(
        demo_db, identity, session_id,
        old["document_id"], new["document_id"],
        base_version=old["version"], target_version=new["version"],
    ).to_dict()

    summary = assistant_domain._historical_result_summary("compare_scoped_protocols", comparison)
    assert summary["authority"] == "HISTORICAL_PROTOCOL_METHOD_ONLY_NOT_CURRENT_BUSINESS_EVIDENCE"
    assert summary["comparison_digest"] == comparison["comparison_digest"]
    assert summary["base_ref"]["digest"] == comparison["base_ref"]["digest"]
    assert summary["target_ref"]["digest"] == comparison["target_ref"]["digest"]
    assert len(summary["differences"]) <= 3
    assert all(len(str(item)) < 900 for item in summary["differences"])
    assert "diff_evidence" not in summary
    assert "facts" not in summary
    from opspilot.domain.context_engineering import estimate_text_tokens
    assert estimate_text_tokens(json.dumps(summary, ensure_ascii=False)) < estimate_text_tokens(
        json.dumps(comparison, ensure_ascii=False)
    )


class IntegrationFixtureModel(BaseChatModel):
    """Deterministic choices through formal Assistant; not real model evidence."""

    mode: str
    receiver_state: str = "QUEUED"
    seen: list = Field(default_factory=list)
    decisions: list = Field(default_factory=list)
    offered_tool_names: list = Field(default_factory=list)

    @property
    def _llm_type(self):
        return "AR02_AR03_INTEGRATION_DETERMINISTIC_FIXTURE"

    def bind_tools(self, tools, **kwargs):
        self.offered_tool_names = [tool.name for tool in tools]
        return self

    @staticmethod
    def _payload(message):
        value = json.loads(message.content) if isinstance(message.content, str) else message.content
        while isinstance(value, dict) and set(value) == {"result"}:
            value = value["result"]
        return value if isinstance(value, dict) else {}

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        self.seen.append(messages)
        names_by_id = {}
        for message in messages:
            for call in getattr(message, "tool_calls", []) or []:
                names_by_id[call.get("id")] = call.get("name")
        payloads = {
            names_by_id.get(message.tool_call_id): self._payload(message)
            for message in messages if isinstance(message, ToolMessage)
        }
        selected = None
        args = {}
        if self.mode == "cap-resume":
            denial = payloads.get("search_project_knowledge")
            if denial is not None:
                assert denial.get("executed") is False
                assert denial.get("authority") == "TOOL_REFUSAL_NOT_FACT"
                delivery = payloads.get("get_callback_delivery", {}).get("facts", {})
                receiver = payloads.get("get_receiver_processing", {}).get("facts", {})
                status = receiver.get("status") if delivery.get("event_id") == receiver.get("event_id") else "UNKNOWN"
                answer = (
                    f"当前 Event {delivery.get('event_id')} 的投递为 HTTP {delivery.get('receiver_http_status')} / "
                    f"{delivery.get('status')}；同一 Event Receiver 为 {status}。"
                    "未执行的 Knowledge 提议没有返回资料，因此不作为依据；回答仅基于当前已取得的观察。"
                )
            else:
                plan = [
                    "list_scoped_protocol_documents", "compare_scoped_protocols",
                    "get_order_status", "get_callback_delivery", "get_receiver_processing",
                    "get_callback_transport_history",
                ]
                selected = next((name for name in plan if name not in payloads), None)
                if selected == "list_scoped_protocol_documents":
                    args = {"topic": "callback retry"}
                elif selected == "compare_scoped_protocols":
                    docs = payloads["list_scoped_protocol_documents"].get("protocol_documents", [])
                    old = next(row for row in docs if str(row.get("version", "")).startswith("1."))
                    new = next(row for row in docs if str(row.get("version", "")).startswith("2."))
                    args = {
                        "base_document_id": old["document_id"],
                        "target_document_id": new["document_id"],
                        "base_version": old["version"],
                        "target_version": new["version"],
                    }
                elif selected:
                    args = {"reason": "核验受信订单的当前回调状态"}
                else:
                    selected = "search_project_knowledge"
                    args = {"query": "回调重试协议"}
        elif self.mode == "history-answer":
            answer = "我依据上一轮仍有效但仅属历史线索的协议版本比较回答；它不是线上部署证明或新的业务观察。"
        elif self.mode == "binding":
            answer = "可信订单选择操作已确认资源绑定；聊天文本本身不授予查询权限。"
        elif self.mode == "unauthorized":
            if "compare_scoped_protocols" not in payloads:
                selected = "compare_scoped_protocols"
                args = {
                    "base_document_id": "callback-retry-contract",
                    "target_document_id": "api-scope-current",
                }
            else:
                refusal = payloads["compare_scoped_protocols"]
                answer = (
                    "未授权文档比较被拒绝；返回的是工具拒绝而不是协议差异或客户事实。"
                    f"原因：{refusal.get('reason_code')}。"
                )
        else:
            if "list_scoped_protocol_documents" not in payloads:
                selected = "list_scoped_protocol_documents"
                args = {"topic": "callback retry"}
            elif "compare_scoped_protocols" not in payloads:
                discovered = payloads["list_scoped_protocol_documents"]
                docs = discovered.get("protocol_documents", [])
                old = next((row for row in docs if str(row.get("version", "")).startswith("1.")), None)
                new = next((row for row in docs if str(row.get("version", "")).startswith("2.")), None)
                assert old and new, discovered
                selected = "compare_scoped_protocols"
                args = {
                    "base_document_id": old["document_id"],
                    "target_document_id": new["document_id"],
                    "base_version": old["version"],
                    "target_version": new["version"],
                }
            elif self.mode == "bound":
                choices = (
                    "get_receiver_processing", "get_callback_delivery", "get_order_status",
                )
                selected = next((name for name in choices if name not in payloads), None)
                if selected:
                    args = {"reason": "将协议变化与当前 TaskBinding 下的同一订单事实关联"}
            if selected is None:
                comparison = payloads.get("compare_scoped_protocols", {})
                base = comparison.get("base_ref", {})
                target = comparison.get("target_ref", {})
                diff = comparison.get("summary", "")
                if self.mode == "unbound":
                    answer = (
                        f"发现并比较授权协议 {base.get('document_id')} v{base.get('version')} 与 "
                        f"{target.get('document_id')} v{target.get('version')}。{diff} "
                        "当前 Session 没有可信订单绑定，不能核查客户当前状态；线上部署版本也未验证。"
                    )
                else:
                    delivery = payloads.get("get_callback_delivery", {}).get("facts", {})
                    receiver = payloads.get("get_receiver_processing", {}).get("facts", {})
                    order = payloads.get("get_order_status", {}).get("facts", {}).get("body", {})
                    same_event = delivery.get("event_id") == receiver.get("event_id")
                    status = receiver.get("status") if same_event else "UNKNOWN"
                    if status == "PROCESSED":
                        conclusion = f"同一 Event {receiver.get('event_id')} 的 Receiver 当前为 PROCESSED，已处理完成。"
                    elif status == "QUEUED":
                        conclusion = f"同一 Event {receiver.get('event_id')} 的 Receiver 当前为 QUEUED，尚未证明处理完成。"
                    else:
                        conclusion = "Receiver 当前状态无法由匹配的同 Event Observation 确认。"
                    answer = (
                        f"协议比较：{diff}\n订单 {order.get('order_id')} / {order.get('status')}；"
                        f"Delivery HTTP {delivery.get('receiver_http_status')} / Event {delivery.get('event_id')}；"
                        f"{conclusion}\n升级影响说明草稿：协议差异可能影响重试判断。"
                        "未知：线上部署版本及接收方后续状态；本文是未提交草稿，没有创建工单或回执。"
                    )

        if selected:
            self.decisions.append({"action": "CALL", "tool": selected, "args": args, "tool_call_id": f"integration-{self.mode}-{len(self.decisions) + 1}"})
            message = AIMessage(content="", tool_calls=[{
                "name": selected, "args": args, "id": f"integration-{self.mode}-{len(self.decisions)}",
            }])
        else:
            self.decisions.append({"action": "ANSWER"})
            message = AIMessage(content=answer)
        message.usage_metadata = {"input_tokens": 20, "output_tokens": 10, "total_tokens": 30}
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


def _login(client):
    from test_ar02_assistant import ORIGIN, PASSWORDS

    login = client.post(
        "/api/auth/login", headers={"Origin": ORIGIN},
        json={"actor_id": "support-a", "password": PASSWORDS["support-a"]},
    )
    assert login.status_code == 200, login.text
    return {"Origin": ORIGIN, "X-CSRF-Token": login.json()["csrf_token"]}


def _append_formal_trace(db_path, session_id, run_ids, models):
    target = os.environ.get("AR02_AR03_TRACE_PATH")
    if not target:
        return
    from opspilot.domain.database import connect

    rows = []
    with connect(db_path) as connection:
        for run_id in run_ids:
            run = connection.execute(
                "SELECT run_id,task_id,session_id,tenant_id,kind,status,source_message_id,created_at,ended_at "
                "FROM task_runs WHERE run_id=?", (run_id,),
            ).fetchone()
            rows.append({"record_type": "persisted_run", **dict(run)})
            for call in connection.execute(
                "SELECT call_id,run_id,kind,logical_key,status,request_json,result_json,evidence_id,observation_id,"
                "usage_json,created_at,completed_at FROM assistant_calls WHERE run_id=? ORDER BY created_at",
                (run_id,),
            ):
                rows.append({"record_type": "persisted_assistant_call", **dict(call)})
            for observation in connection.execute(
                "SELECT o.*,a.run_id FROM d2_tool_observations o JOIN d2_attempts a "
                "ON a.attempt_id=o.attempt_id AND a.task_id=o.task_id WHERE a.run_id=? ORDER BY o.created_at",
                (run_id,),
            ):
                rows.append({"record_type": "persisted_mcp_observation", **dict(observation)})
        for message in connection.execute(
            "SELECT message_id,session_id,tenant_id,role,body,task_id,sequence,created_at "
            "FROM messages WHERE session_id=? ORDER BY sequence", (session_id,),
        ):
            rows.append({"record_type": "persisted_session_message", **dict(message)})
        for answer in connection.execute(
            "SELECT a.run_id,a.message_id,a.attempt_id,a.manifest_id,a.body_digest,a.committed_at,"
            "r.source_message_id,m.body FROM chat_run_answers a JOIN task_runs r ON r.run_id=a.run_id "
            "JOIN messages m ON m.message_id=a.message_id WHERE r.session_id=? ORDER BY a.committed_at",
            (session_id,),
        ):
            rows.append({"record_type": "persisted_answer_source_link", **dict(answer)})
    for run_id, model in zip(run_ids, models):
        rows.append({
            "record_type": "deterministic_fixture_decisions",
            "evidence_level": "DETERMINISTIC_FIXTURE_NOT_REAL_PROVIDER",
            "run_id": run_id,
            "mode": model.mode,
            "offered_tool_names": model.offered_tool_names,
            "decisions": model.decisions,
        })
    trace_path = Path(target)
    trace_path.parent.mkdir(parents=True, exist_ok=True)
    with trace_path.open("a", encoding="utf-8", newline="\n") as stream:
        for row in rows:
            stream.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def test_formal_worker_discovers_compares_without_binding_and_keeps_history_bounded(
    demo_db, tmp_path,
):
    from fastapi.testclient import TestClient
    from opspilot.domain.database import connect
    from opspilot.web.app import create_app
    from test_ar02_assistant import ORIGIN, PASSWORDS

    model = IntegrationFixtureModel(mode="unbound")
    history_model = IntegrationFixtureModel(mode="history-answer")
    models = deque([model, history_model])
    app = create_app(
        db_path=demo_db, checkpoint_db_path=tmp_path / "integration-unbound-cp.sqlite3",
        start_worker=True, credentials=PASSWORDS, expected_origin=ORIGIN,
        assistant_model_factory=lambda: models.popleft(),
    )
    with TestClient(app) as client:
        headers = _login(client)
        session_id = client.post("/api/sessions", headers=headers).json()["session_id"]
        question = "找出授权范围中的旧版和新版回调重试规范，比较变化，并说明是否能确认客户已经处理完成。"
        accepted = client.post(
            f"/api/sessions/{session_id}/assistant/messages",
            headers={**headers, "Idempotency-Key": "ar02-ar03-unbound-1"},
            json={"body": question},
        )
        assert accepted.status_code == 202, accepted.text
        first = accepted.json()
        assert _wait_run(client, first["run_id"])["status"] == "SUCCEEDED"
        assert client.get(f"/api/runs/{first['run_id']}/assistant-sources").json()["current"] is True
        messages = client.get(f"/api/sessions/{session_id}/messages").json()["items"]
        answer = next(row["body"] for row in messages if row["role"] == "ASSISTANT")
        assert "callback-retry-contract" in answer and "v2" in answer
        assert "不能核查客户当前状态" in answer
        assert "线上部署版本也未验证" in answer
        assert "list_scoped_protocol_documents" in model.offered_tool_names
        assert "compare_scoped_protocols" in model.offered_tool_names
        assert not {"get_order_status", "get_callback_delivery", "get_receiver_processing"} & set(model.offered_tool_names)

        followup = client.post(
            f"/api/sessions/{session_id}/assistant/messages",
            headers={**headers, "Idempotency-Key": "ar02-ar03-unbound-2"},
            json={"body": "你刚才比较的协议变化是什么？"},
        )
        assert followup.status_code == 202, followup.text
        second = followup.json()
        assert _wait_run(client, second["run_id"])["status"] == "SUCCEEDED"
        assert client.get(f"/api/runs/{second['run_id']}/assistant-sources").json()["current"] is True
        sent = str(history_model.seen)
        assert "HISTORICAL_PROTOCOL_METHOD_ONLY_NOT_CURRENT_BUSINESS_EVIDENCE" in sent
        assert "comparison_digest" in sent and "base_ref" in sent and "target_ref" in sent
        assert "diff_evidence" not in sent

        with connect(demo_db) as connection:
            assert connection.execute("SELECT COUNT(*) FROM task_bindings").fetchone()[0] == 0
            calls = connection.execute(
                "SELECT request_json,result_json FROM assistant_calls WHERE run_id=? AND kind='MCP' ORDER BY created_at",
                (first["run_id"],),
            ).fetchall()
            names = [json.loads(row["request_json"])["name"] for row in calls]
            assert names == ["list_scoped_protocol_documents", "compare_scoped_protocols"]
            assert all(json.loads(row["result_json"]).get("success") is True for row in calls)
            model_calls = connection.execute(
                "SELECT request_json FROM assistant_calls WHERE run_id IN (?,?) AND kind='MODEL'",
                (first["run_id"], second["run_id"]),
            ).fetchall()
            for call in model_calls:
                request = json.loads(call["request_json"])
                assert request["context_budget"]["estimated_input_tokens"] <= 12_000
            for table in ("s3_diagnoses", "d3_action_intents", "d3_action_ledgers", "s3_handoff_receipts"):
                assert connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0
        _append_formal_trace(
            demo_db, session_id, [first["run_id"], second["run_id"]], [model, history_model],
        )


def test_formal_mcp_refuses_unauthorized_protocol_comparison(demo_db, tmp_path):
    from fastapi.testclient import TestClient
    from opspilot.domain.database import connect
    from opspilot.web.app import create_app
    from test_ar02_assistant import ORIGIN, PASSWORDS

    model = IntegrationFixtureModel(mode="unauthorized")
    app = create_app(
        db_path=demo_db, checkpoint_db_path=tmp_path / "integration-unauthorized-cp.sqlite3",
        start_worker=True, credentials=PASSWORDS, expected_origin=ORIGIN,
        assistant_model_factory=lambda: model,
    )
    with TestClient(app) as client:
        headers = _login(client)
        session_id = client.post("/api/sessions", headers=headers).json()["session_id"]
        accepted = client.post(
            f"/api/sessions/{session_id}/assistant/messages",
            headers={**headers, "Idempotency-Key": "ar02-ar03-unauthorized-doc"},
            json={"body": "比较 callback-retry-contract 和用户猜测的 api-scope-current。"},
        )
        assert accepted.status_code == 202, accepted.text
        item = accepted.json()
        assert _wait_run(client, item["run_id"])["status"] == "SUCCEEDED"
        assert "未授权文档比较被拒绝" in client.get(
            f"/api/sessions/{session_id}/messages"
        ).json()["items"][-1]["body"]
        with connect(demo_db) as connection:
            call = connection.execute(
                "SELECT request_json,result_json FROM assistant_calls "
                "WHERE run_id=? AND kind='MCP'", (item["run_id"],),
            ).fetchone()
            request, result = json.loads(call["request_json"]), json.loads(call["result_json"])
            assert request["name"] == "compare_scoped_protocols"
            assert result["success"] is False
            assert result["reason_code"] == "DOCUMENT_NOT_AUTHORIZED"
            assert result["authority"] == "TOOL_REFUSAL_NOT_FACT"
            assert "diff_evidence" not in result
        _append_formal_trace(demo_db, session_id, [item["run_id"]], [model])


@pytest.mark.parametrize("receiver_state", ["QUEUED", "PROCESSED"])
def test_formal_worker_protocol_impact_draft_tracks_current_receiver_observation(
    demo_db, tmp_path, receiver_state, monkeypatch,
):
    from fastapi.testclient import TestClient
    from opspilot.domain.database import connect
    from opspilot.domain.s3 import prepare_s3_fixture
    from opspilot.web.app import create_app
    from test_ar02_assistant import ORIGIN, PASSWORDS

    paired_ids = iter((
        uuid.UUID("00000000-0000-4000-8000-000000000001"),
        uuid.UUID("00000000-0000-4000-8000-000000000002"),
    ))
    with monkeypatch.context() as patcher:
        patcher.setattr("opspilot.domain.s3.uuid.uuid4", lambda: next(paired_ids))
        fixture = prepare_s3_fixture(
            demo_db, "DELIVERED_PENDING", order_id="ar03-order", contract_version=2,
        )
    assert fixture["transport_trace"][0]["request"]["event_id"] == (
        "event-00000000-0000-4000-8000-000000000001"
    )
    if receiver_state == "PROCESSED":
        with connect(demo_db) as connection:
            connection.execute(
                "UPDATE s3_receivers SET status='PROCESSED',version=version+1 WHERE order_id='ar03-order'"
            )

    bind_model = IntegrationFixtureModel(mode="binding")
    journey_model = IntegrationFixtureModel(mode="bound", receiver_state=receiver_state)
    models = deque([bind_model, journey_model])
    app = create_app(
        db_path=demo_db, checkpoint_db_path=tmp_path / f"integration-bound-{receiver_state}.sqlite3",
        start_worker=True, credentials=PASSWORDS, expected_origin=ORIGIN,
        assistant_model_factory=lambda: models.popleft(),
    )
    with TestClient(app) as client:
        headers = _login(client)
        session_id = client.post("/api/sessions", headers=headers).json()["session_id"]
        binding = client.post(
            f"/api/sessions/{session_id}/assistant/order",
            headers={**headers, "Idempotency-Key": f"ar03-prep-bind-{receiver_state}"},
            json={"order_id": "ar03-order", "initial_message": "通过可信资源选择确认订单绑定。"},
        )
        assert binding.status_code == 202, binding.text
        bound = binding.json()
        assert _wait_run(client, bound["run_id"])["status"] == "SUCCEEDED"

        accepted = client.post(
            f"/api/sessions/{session_id}/assistant/messages",
            headers={**headers, "Idempotency-Key": f"ar03-prep-investigate-{receiver_state}"},
            json={
                "body": "比较授权回调协议版本，并结合本订单当前 Event 分析升级影响，整理未提交的支持说明。",
                "task_id": bound["task_id"],
            },
        )
        assert accepted.status_code == 202, accepted.text
        item = accepted.json()
        assert _wait_run(client, item["run_id"])["status"] == "SUCCEEDED"
        assert client.get(f"/api/runs/{item['run_id']}/assistant-sources").json()["current"] is True
        messages = client.get(f"/api/sessions/{session_id}/messages").json()["items"]
        answer = next(row["body"] for row in messages if row.get("answer_source_message_id") == item["message_id"])
        assert "HTTP 202" in answer and "升级影响说明草稿" in answer and "未提交" in answer
        assert "线上部署版本" in answer and "未知" in answer
        if receiver_state == "QUEUED":
            assert "尚未证明处理完成" in answer and "PROCESSED" not in answer
        else:
            assert "已处理完成" in answer and "PROCESSED" in answer
            assert "尚未证明处理完成" not in answer

        with connect(demo_db) as connection:
            from opspilot.domain.s3 import get_s3_binding

            trusted_binding = get_s3_binding(connection, bound["task_id"])
            assert trusted_binding["order_id"] == "ar03-order"
            assert trusted_binding["tenant_id"] == "tenant-a"
            assert trusted_binding["actor_id"] == "support-a"
            assert trusted_binding["resource_confirmed_by"] == "support-a"
            assert trusted_binding["principal_status"] == "ENABLED"
            assert trusted_binding["scope_policy_version"] > 0
            assert trusted_binding["grant_version"] > 0

            calls = connection.execute(
                "SELECT request_json,result_json,evidence_id,observation_id FROM assistant_calls "
                "WHERE run_id=? AND kind='MCP' ORDER BY created_at", (item["run_id"],),
            ).fetchall()
            results_by_name = {
                json.loads(row["request_json"])["name"]: (json.loads(row["result_json"]), row)
                for row in calls
            }
            assert {"list_scoped_protocol_documents", "compare_scoped_protocols",
                    "get_receiver_processing", "get_callback_delivery", "get_order_status"} <= set(results_by_name)
            receiver, receiver_row = results_by_name["get_receiver_processing"]
            delivery, delivery_row = results_by_name["get_callback_delivery"]
            order, _ = results_by_name["get_order_status"]
            assert order["facts"]["body"]["order_id"] == "ar03-order"
            assert delivery["facts"]["order_id"] == "ar03-order"
            assert receiver["facts"]["order_id"] == "ar03-order"
            assert delivery["facts"]["status"] == "ACKNOWLEDGED"
            assert delivery["facts"]["receiver_http_status"] == 202
            assert receiver["facts"]["status"] == receiver_state
            assert receiver["facts"]["event_id"] == delivery["facts"]["event_id"] == fixture["transport_trace"][0]["request"]["event_id"]
            assert receiver_row["evidence_id"] and receiver_row["observation_id"]
            assert delivery_row["evidence_id"] and delivery_row["observation_id"]
            model_calls = connection.execute(
                "SELECT request_json FROM assistant_calls WHERE run_id=? AND kind='MODEL'",
                (item["run_id"],),
            ).fetchall()
            assert all(
                json.loads(row["request_json"])["context_budget"]["estimated_input_tokens"] <= 12_000
                for row in model_calls
            )
            zero_business_write_counts = {}
            for table in (
                "s3_diagnoses", "d3_plans", "d3_plan_authorizations", "d3_approvals",
                "d3_action_permissions", "d3_action_intents", "d3_action_ledgers",
                "d3_verification_receipts", "d3_report_artifacts", "d3_delivery_records",
                "s3_handoff_queue_entries", "s3_handoff_receipts",
            ):
                zero_business_write_counts[table] = connection.execute(
                    f"SELECT COUNT(*) FROM {table}"
                ).fetchone()[0]
                assert zero_business_write_counts[table] == 0
        _append_formal_trace(
            demo_db, session_id, [bound["run_id"], item["run_id"]], [bind_model, journey_model],
        )
        alignment_trace_path = os.environ.get("AR03_ORDER_ALIGNMENT_TRACE_PATH")
        if alignment_trace_path:
            trace_row = {
                "record_type": "persisted_domain_alignment_check",
                "evidence_level": "DETERMINISTIC_FORMAL_WORKER_AND_SQLITE_TEST",
                "case_id": f"AR03-LLM-01-{receiver_state}",
                "session_id": session_id,
                "task_id": bound["task_id"],
                "run_id": item["run_id"],
                "order_id": trusted_binding["order_id"],
                "tenant_id": trusted_binding["tenant_id"],
                "actor_id": trusted_binding["actor_id"],
                "resource_confirmed_by": trusted_binding["resource_confirmed_by"],
                "authorization_source": "authenticated trusted Assistant order API; verified from current get_s3_binding row",
                "principal_status": trusted_binding["principal_status"],
                "scope_policy_version": trusted_binding["scope_policy_version"],
                "grant_version": trusted_binding["grant_version"],
                "required_scopes": trusted_binding["required_scopes"],
                "granted_scopes": trusted_binding["granted_scopes"],
                "event_id": receiver["facts"]["event_id"],
                "delivery_event_id": delivery["facts"]["event_id"],
                "receiver_status": receiver["facts"]["status"],
                "delivery_status": delivery["facts"]["status"],
                "delivery_http_status": delivery["facts"]["receiver_http_status"],
                "delivery_observation_id": delivery_row["observation_id"],
                "delivery_evidence_id": delivery_row["evidence_id"],
                "receiver_observation_id": receiver_row["observation_id"],
                "receiver_evidence_id": receiver_row["evidence_id"],
                "zero_business_write_counts": zero_business_write_counts,
                "real_provider_requests": 0,
            }
            path = Path(alignment_trace_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8", newline="\n") as stream:
                stream.write(json.dumps(trace_row, ensure_ascii=False, sort_keys=True) + "\n")


@pytest.mark.parametrize("receiver_state", ["QUEUED", "PROCESSED"])
def test_formal_worker_can_deliver_from_current_observations_after_mcp_cap_refusal(
    demo_db, tmp_path, receiver_state, monkeypatch,
):
    """A denied seventh tool is not executed, and the Agent may still answer from six current calls."""
    from fastapi.testclient import TestClient
    from opspilot.domain.database import connect
    from opspilot.domain.s3 import prepare_s3_fixture
    from opspilot.web.app import create_app
    from test_ar02_assistant import ORIGIN, PASSWORDS

    paired_ids = iter((
        uuid.UUID("00000000-0000-4000-8000-000000000001"),
        uuid.UUID("00000000-0000-4000-8000-000000000002"),
    ))
    with monkeypatch.context() as patcher:
        patcher.setattr("opspilot.domain.s3.uuid.uuid4", lambda: next(paired_ids))
        fixture = prepare_s3_fixture(
            demo_db, "DELIVERED_PENDING", order_id="ar03-order", contract_version=2,
        )
    if receiver_state == "PROCESSED":
        with connect(demo_db) as connection:
            connection.execute(
                "UPDATE s3_receivers SET status='PROCESSED',version=version+1 WHERE order_id='ar03-order'"
            )

    frozen_cases_path = (
        Path(__file__).resolve().parents[1]
        / "docs/evidence/ar-03-real-llm-01-prep/CASES.json"
    )
    initial_message = json.loads(frozen_cases_path.read_text(encoding="utf-8"))["prompt"]
    model = IntegrationFixtureModel(mode="cap-resume", receiver_state=receiver_state)
    app = create_app(
        db_path=demo_db,
        checkpoint_db_path=tmp_path / f"cap-resume-{receiver_state}.sqlite3",
        start_worker=True,
        credentials=PASSWORDS,
        expected_origin=ORIGIN,
        assistant_model_factory=lambda: model,
    )
    with TestClient(app) as client:
        headers = _login(client)
        session_id = client.post("/api/sessions", headers=headers).json()["session_id"]
        accepted = client.post(
            f"/api/sessions/{session_id}/assistant/order",
            headers={**headers, "Idempotency-Key": f"ar03-cap-resume-{receiver_state}"},
            json={"order_id": "ar03-order", "initial_message": initial_message},
        )
        assert accepted.status_code == 202, accepted.text
        binding = accepted.json()
        run = _wait_run(client, binding["run_id"])
        assert run["status"] == "SUCCEEDED", run

        messages = client.get(f"/api/sessions/{session_id}/messages").json()["items"]
        answer = next(row["body"] for row in messages if row.get("answer_source_message_id") == binding["message_id"])
        assert "未执行的 Knowledge 提议" in answer
        assert fixture["transport_trace"][0]["request"]["event_id"] in answer
        if receiver_state == "QUEUED":
            assert "Receiver 为 QUEUED" in answer
            assert "已处理完成" not in answer
        else:
            assert "Receiver 为 PROCESSED" in answer

        with connect(demo_db) as connection:
            calls = connection.execute(
                "SELECT request_json,result_json,status FROM assistant_calls WHERE run_id=? AND kind='MCP' ORDER BY created_at",
                (binding["run_id"],),
            ).fetchall()
            assert len(calls) == 6
            assert all(row["status"] == "OK" for row in calls)
            names = [json.loads(row["request_json"])["name"] for row in calls]
            assert names == [
                "list_scoped_protocol_documents", "compare_scoped_protocols",
                "get_order_status", "get_callback_delivery", "get_receiver_processing",
                "get_callback_transport_history",
            ]
            attempts = connection.execute(
                "SELECT status FROM d2_attempts WHERE run_id=? AND kind='MCP'",
                (binding["run_id"],),
            ).fetchall()
            assert len(attempts) == 6 and all(row["status"] == "OK" for row in attempts)
            current, reason = assistant_domain.sources_current(connection, binding["run_id"])
            assert current, reason
            for table in (
                "s3_diagnoses", "d3_approvals", "d3_action_intents", "d3_action_ledgers",
                "s3_handoff_queue_entries", "s3_handoff_receipts",
            ):
                assert connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0

        attempted = [decision for decision in model.decisions if decision.get("tool") == "search_project_knowledge"]
        assert len(attempted) == 1
        denied = [
            message for turn in model.seen for message in turn
            if isinstance(message, ToolMessage) and message.tool_call_id == attempted[0]["tool_call_id"]
        ]
        assert len(denied) == 1
        refusal = json.loads(denied[0].content)
        assert refusal["executed"] is False
        assert refusal["authority"] == "TOOL_REFUSAL_NOT_FACT"


@pytest.mark.parametrize("receiver_state", ["QUEUED", "PROCESSED"])
def test_full_frozen_goal_in_trusted_order_initial_message_uses_one_assistant_run(
    demo_db, tmp_path, receiver_state, monkeypatch,
):
    """The trusted binding request itself can be the user's full investigation request."""
    from fastapi.testclient import TestClient
    from opspilot.domain.database import connect
    from opspilot.domain.s3 import prepare_s3_fixture
    from opspilot.web.app import create_app
    from test_ar02_assistant import ORIGIN, PASSWORDS

    paired_ids = iter((
        uuid.UUID("00000000-0000-4000-8000-000000000001"),
        uuid.UUID("00000000-0000-4000-8000-000000000002"),
    ))
    with monkeypatch.context() as patcher:
        patcher.setattr("opspilot.domain.s3.uuid.uuid4", lambda: next(paired_ids))
        fixture = prepare_s3_fixture(
            demo_db, "DELIVERED_PENDING", order_id="ar03-order", contract_version=2,
        )
    assert fixture["transport_trace"][0]["request"]["event_id"] == (
        "event-00000000-0000-4000-8000-000000000001"
    )
    if receiver_state == "PROCESSED":
        with connect(demo_db) as connection:
            connection.execute(
                "UPDATE s3_receivers SET status='PROCESSED',version=version+1 WHERE order_id='ar03-order'"
            )

    frozen_cases_path = (
        Path(__file__).resolve().parents[1]
        / "docs/evidence/ar-03-real-llm-01-prep/CASES.json"
    )
    initial_message = json.loads(frozen_cases_path.read_text(encoding="utf-8"))["prompt"]
    model = IntegrationFixtureModel(mode="bound", receiver_state=receiver_state)
    app = create_app(
        db_path=demo_db,
        checkpoint_db_path=tmp_path / f"hf01-full-initial-{receiver_state}.sqlite3",
        start_worker=True,
        credentials=PASSWORDS,
        expected_origin=ORIGIN,
        assistant_model_factory=lambda: model,
    )
    with TestClient(app) as client:
        headers = _login(client)
        session_id = client.post("/api/sessions", headers=headers).json()["session_id"]
        accepted = client.post(
            f"/api/sessions/{session_id}/assistant/order",
            headers={**headers, "Idempotency-Key": f"ar03-hf01-full-goal-{receiver_state}"},
            json={"order_id": "ar03-order", "initial_message": initial_message},
        )
        assert accepted.status_code == 202, accepted.text
        binding = accepted.json()
        run = _wait_run(client, binding["run_id"])
        assert run["status"] == "SUCCEEDED", run

        messages = client.get(f"/api/sessions/{session_id}/messages").json()["items"]
        user_messages = [row for row in messages if row["role"] == "USER"]
        answers = [row for row in messages if row.get("answer_source_message_id") == binding["message_id"]]
        assert len(user_messages) == 1
        assert user_messages[0]["message_id"] == binding["message_id"]
        assert user_messages[0]["body"] == initial_message
        assert len(answers) == 1
        answer = answers[0]["body"]
        assert "callback-retry-contract" in answer
        assert "升级影响说明草稿" in answer and "未提交" in answer
        assert "线上部署版本" in answer and "未知" in answer
        if receiver_state == "QUEUED":
            assert "尚未证明处理完成" in answer and "PROCESSED" not in answer
        else:
            assert "同一 Event" in answer and "已处理完成" in answer
            assert "尚未证明处理完成" not in answer
        assert initial_message in str(model.seen)

        with connect(demo_db) as connection:
            from opspilot.domain.s3 import get_s3_binding

            trusted_binding = get_s3_binding(connection, binding["task_id"])
            assert trusted_binding["order_id"] == "ar03-order"
            assert trusted_binding["tenant_id"] == "tenant-a"
            assert trusted_binding["actor_id"] == "support-a"
            task_runs = connection.execute(
                "SELECT run_id,kind,status,source_message_id FROM task_runs WHERE session_id=?",
                (session_id,),
            ).fetchall()
            assert len(task_runs) == 1
            assert task_runs[0]["run_id"] == binding["run_id"]
            assert task_runs[0]["kind"] == "CHAT_READONLY"
            assert task_runs[0]["status"] == "SUCCEEDED"
            assert task_runs[0]["source_message_id"] == binding["message_id"]
            assert connection.execute(
                "SELECT COUNT(*) FROM assistant_runs WHERE run_id=? AND core='ASSISTANT_V1'",
                (binding["run_id"],),
            ).fetchone()[0] == 1
            mcp_calls = connection.execute(
                "SELECT request_json,result_json,evidence_id,observation_id,status "
                "FROM assistant_calls WHERE run_id=? AND kind='MCP' ORDER BY created_at",
                (binding["run_id"],),
            ).fetchall()
            assert len(mcp_calls) <= 6
            by_name = {
                json.loads(row["request_json"])["name"]: row for row in mcp_calls
            }
            assert {
                "list_scoped_protocol_documents", "compare_scoped_protocols",
                "get_order_status", "get_callback_delivery", "get_receiver_processing",
            } <= set(by_name)
            discovery_request = json.loads(by_name["list_scoped_protocol_documents"]["request_json"])
            assert discovery_request["args"]["topic"] == "callback retry"
            assert all(row["status"] == "OK" for row in by_name.values())
            attempts = connection.execute(
                "SELECT kind,status FROM d2_attempts WHERE run_id=? ORDER BY reserved_at,attempt_id",
                (binding["run_id"],),
            ).fetchall()
            mcp_attempts = [row for row in attempts if row["kind"] == "MCP"]
            assert len(mcp_attempts) == len(mcp_calls) <= 6
            assert all(row["status"] == "OK" for row in mcp_attempts)
            model_requests = connection.execute(
                "SELECT request_json FROM assistant_calls WHERE run_id=? AND kind='MODEL'",
                (binding["run_id"],),
            ).fetchall()
            assert model_requests
            assert all(
                json.loads(row["request_json"])["context_budget"]["estimated_input_tokens"] <= 12_000
                for row in model_requests
            )
            for tool_name in ("get_callback_delivery", "get_receiver_processing"):
                assert by_name[tool_name]["evidence_id"] and by_name[tool_name]["observation_id"]
                tool_result = json.loads(by_name[tool_name]["result_json"])
                assert tool_result["facts"]["event_id"] == fixture["transport_trace"][0]["request"]["event_id"]
                assert tool_result["facts"]["order_id"] == "ar03-order"
            assert connection.execute(
                "SELECT COUNT(*) FROM messages WHERE session_id=? AND role='USER'", (session_id,)
            ).fetchone()[0] == 1
            for table in (
                "s3_diagnoses", "d3_plans", "d3_plan_authorizations", "d3_approvals",
                "d3_action_permissions", "d3_action_intents", "d3_action_ledgers",
                "d3_verification_receipts", "d3_report_artifacts", "d3_delivery_records",
                "s3_handoff_queue_entries", "s3_handoff_receipts",
            ):
                assert connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0

        trace_target = os.environ.get("AR03_LIVE_HF01_TRACE_PATH")
        if trace_target:
            monkeypatch.setenv("AR02_AR03_TRACE_PATH", trace_target)
            _append_formal_trace(demo_db, session_id, [binding["run_id"]], [model])
