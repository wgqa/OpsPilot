"""Frozen offline acceptance tests for protocol sources and user-provided material."""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import Field

from fastapi.testclient import TestClient

from opspilot.domain.database import connect
from opspilot.domain.task_control import create_session, trusted_identity


@pytest.fixture
def scoped_material_env(demo_db, monkeypatch, tmp_path):
    import opspilot.domain.assistant_knowledge as knowledge

    registry = tmp_path / "assistant-access.json"
    registry.write_bytes(Path(knowledge.REGISTRY).read_bytes())
    monkeypatch.setattr(knowledge, "REGISTRY", registry)
    with connect(demo_db) as connection:
        connection.executescript(knowledge.SCHEMA)
    identity = trusted_identity(demo_db, "support-a")
    session_id = create_session(demo_db, identity)["session_id"]
    catalog = tmp_path / "callback-catalog"
    import shutil

    shutil.copytree(Path(__file__).resolve().parents[1] / "knowledge" / "async-callback", catalog)
    return demo_db, identity, session_id, registry, catalog


def test_authorized_protocol_excerpt_is_bounded_exact_and_revalidated(scoped_material_env):
    from opspilot.domain.scoped_protocol_comparison import (
        read_scoped_protocol_excerpt,
        scoped_protocol_excerpt_is_current,
        DocumentNotAuthorizedError,
    )

    db, identity, session_id, _, catalog = scoped_material_env
    result = read_scoped_protocol_excerpt(
        db, identity, session_id,
        document_id="callback-retry-contract", version="1.0.0",
        query="EXHAUSTED attempt limit retry state", catalog_dirs=[catalog],
    )
    assert result["authority"] == "SESSION_AUTHORIZED_ORIGINAL_TEXT_NOT_RUNTIME_EVIDENCE"
    assert result["deployment_version_verified"] is False
    ref = result["document_ref"]
    assert ref["document_id"] == "callback-retry-contract"
    assert ref["version"] == "1.0.0" and ref["source"] and ref["digest"]
    assert result["grant_version"] >= 1 and result["scope_digest"]
    assert result["excerpts"]
    assert all(0 < len(row["text"]) <= 1600 for row in result["excerpts"])
    assert sum(len(row["text"]) for row in result["excerpts"]) <= 1600
    assert all(row["line_start"] >= 1 and row["line_end"] >= row["line_start"] for row in result["excerpts"])
    source = (catalog / "callback-retry-contract.md").read_text(encoding="utf-8")
    assert any(row["text"] in source for row in result["excerpts"])
    assert scoped_protocol_excerpt_is_current(
        db, identity, session_id, result, catalog_dirs=[catalog],
    ) == (True, None)

    forged = copy.deepcopy(result)
    forged["excerpts"][0]["text"] += " forged deployment claim"
    assert not scoped_protocol_excerpt_is_current(
        db, identity, session_id, forged, catalog_dirs=[catalog],
    )[0]
    other_session = create_session(db, identity)["session_id"]
    assert not scoped_protocol_excerpt_is_current(
        db, identity, other_session, result, catalog_dirs=[catalog],
    )[0]
    with pytest.raises(DocumentNotAuthorizedError):
        read_scoped_protocol_excerpt(
            db, identity, session_id, document_id="api-scope-current", version="1.0.0",
            query="scope", catalog_dirs=[catalog],
        )


def test_protocol_excerpt_fails_closed_after_grant_or_source_digest_changes(scoped_material_env):
    from opspilot.domain.scoped_protocol_comparison import (
        read_scoped_protocol_excerpt,
        scoped_protocol_excerpt_is_current,
    )

    db, identity, session_id, registry, catalog = scoped_material_env
    result = read_scoped_protocol_excerpt(
        db, identity, session_id,
        document_id="callback-retry-contract", version="1.0.0", query="retry",
        catalog_dirs=[catalog],
    )

    original_grant = json.loads(registry.read_text(encoding="utf-8"))
    grant = copy.deepcopy(original_grant)
    project = next(row for row in grant["projects"] if row["project_id"] == "orders-callback")
    project["grant_version"] += 1
    project["document_ids"].remove("callback-retry-contract")
    registry.write_text(json.dumps(grant), encoding="utf-8")
    assert not scoped_protocol_excerpt_is_current(
        db, identity, session_id, result, catalog_dirs=[catalog],
    )[0]
    with pytest.raises(Exception):
        read_scoped_protocol_excerpt(
            db, identity, session_id,
            document_id="callback-retry-contract", version="1.0.0", query="retry",
            catalog_dirs=[catalog],
        )

    # Restore this isolated registry, then demonstrate that the reference digest
    # cannot survive a content change in the copied, non-authoritative catalog.
    registry.write_text(json.dumps(original_grant), encoding="utf-8")
    restored = read_scoped_protocol_excerpt(
        db, identity, session_id,
        document_id="callback-retry-contract", version="1.0.0", query="retry",
        catalog_dirs=[catalog],
    )
    document_path = catalog / "callback-retry-contract.md"
    document_path.write_text(document_path.read_text(encoding="utf-8") + " changed", encoding="utf-8")
    assert not scoped_protocol_excerpt_is_current(
        db, identity, session_id, restored, catalog_dirs=[catalog],
    )[0]


def test_authorized_protocol_excerpt_continues_from_exact_bounded_cursor(scoped_material_env):
    import hashlib

    from opspilot.domain.scoped_protocol_comparison import (
        read_scoped_protocol_excerpt,
        scoped_protocol_excerpt_is_current,
    )

    db, identity, session_id, _, catalog = scoped_material_env
    content = "retry " + ("x" * 1800) + "\nfollowing callback clause.\n"
    document_path = catalog / "callback-retry-contract.md"
    document_path.write_bytes(content.encode("utf-8"))
    manifest_path = catalog / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    ref = next(row for row in manifest["documents"] if row["document_id"] == "callback-retry-contract")
    ref["digest"] = hashlib.sha256(content.encode("utf-8")).hexdigest()
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    first = read_scoped_protocol_excerpt(
        db, identity, session_id, document_id="callback-retry-contract", version="1.0.0",
        query="retry", catalog_dirs=[catalog],
    )
    first_text = first["excerpts"][0]["text"]
    assert len(first_text) == 1600
    assert first["next_cursor"] == {"line": 1, "column": 1601}
    assert first["source_refs"][0]["column_start"] == 1
    assert scoped_protocol_excerpt_is_current(db, identity, session_id, first, catalog_dirs=[catalog]) == (True, None)

    second = read_scoped_protocol_excerpt(
        db, identity, session_id, document_id="callback-retry-contract", version="1.0.0",
        query="retry", start_line=first["next_cursor"]["line"],
        start_column=first["next_cursor"]["column"], catalog_dirs=[catalog],
    )
    second_text = second["excerpts"][0]["text"]
    assert first_text + second_text == content.splitlines()[0]
    assert second["next_cursor"] == {"line": 2, "column": 1}
    assert scoped_protocol_excerpt_is_current(db, identity, session_id, second, catalog_dirs=[catalog]) == (True, None)

    forged_cursor = copy.deepcopy(second)
    forged_cursor["next_cursor"]["line"] = 1
    assert not scoped_protocol_excerpt_is_current(
        db, identity, session_id, forged_cursor, catalog_dirs=[catalog],
    )[0]


def test_protocol_upgrade_skill_is_integrity_checked_and_only_loaded_on_demand():
    from opspilot.skill_assets import (
        PROTOCOL_UPGRADE_PROBLEM_TYPE,
        load_applicable_skill,
        skill_asset_is_current,
    )

    assert load_applicable_skill(None) is None
    skill = load_applicable_skill(PROTOCOL_UPGRADE_PROBLEM_TYPE)
    assert skill is not None
    assert skill["name"] == "protocol-upgrade-impact-analysis"
    assert skill["version"] and skill["digest"] and "untrusted" in skill["content"].lower()
    assert skill_asset_is_current(PROTOCOL_UPGRADE_PROBLEM_TYPE, skill)
    forged = dict(skill)
    forged["content"] += " forged authority"
    assert not skill_asset_is_current(PROTOCOL_UPGRADE_PROBLEM_TYPE, forged)


def test_protocol_excerpt_history_projection_keeps_source_bounded_and_non_authoritative():
    from opspilot.domain.assistant import _historical_result_summary

    prior = {
        "authority": "SESSION_AUTHORIZED_ORIGINAL_TEXT_NOT_RUNTIME_EVIDENCE",
        "session_id": "session-a", "project_id": "orders-callback",
        "tenant_id": "tenant-a", "actor_id": "support-a",
        "grant_version": 3, "scope_digest": "scope-digest",
        "document_ref": {
            "document_id": "callback-retry-contract", "version": "1.0.0",
            "source": "local:orders-async-demo/contract-v1", "digest": "doc-digest",
        },
        "query": "retry state",
        "excerpts": [{"section": "Root", "line_start": 1, "line_end": 1,
                      "text": "Protocol v1 retry contract. Retry state SCHEDULED means wait.",
                      "excerpt_digest": "excerpt-digest"}],
        "deployment_version_verified": False,
    }
    summary = _historical_result_summary("read_scoped_protocol_excerpt", prior)
    assert summary["authority"] == "HISTORICAL_PROTOCOL_SOURCE_TEXT_ONLY"
    assert summary["document_ref"]["digest"] == "doc-digest"
    assert summary["excerpts"][0]["excerpt_digest"] == "excerpt-digest"
    assert summary["currentness"] == "NOT_CURRENT_BUSINESS_EVIDENCE"
    assert len(str(summary)) <= 1400


class MaterialFixtureModel(BaseChatModel):
    """Deterministic offline decisions; never evidence of real-model autonomy."""

    route: str = "protocol"
    load_skill: bool = False
    seen: list = Field(default_factory=list)
    decisions: list = Field(default_factory=list)
    offered_tool_names: list = Field(default_factory=list)

    @property
    def _llm_type(self):
        return "AR03_MATERIAL_FIXTURE"

    def bind_tools(self, tools, **kwargs):
        self.offered_tool_names = [tool.name for tool in tools]
        return self

    @staticmethod
    def _payload(message):
        try:
            value = json.loads(message.content) if isinstance(message.content, str) else message.content
        except json.JSONDecodeError:
            return {}
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
        answer = ""
        if self.route == "protocol":
            if "list_scoped_protocol_documents" not in payloads:
                selected, args = "list_scoped_protocol_documents", {"topic": "callback retry"}
            elif "read_scoped_protocol_excerpt" not in payloads:
                docs = payloads["list_scoped_protocol_documents"].get("protocol_documents", [])
                document = next(row for row in docs if row.get("document_id") == "callback-retry-contract")
                selected, args = "read_scoped_protocol_excerpt", {
                    "document_id": document["document_id"], "version": document["version"],
                    "query": "EXHAUSTED attempt limit retry state",
                }
            elif self.load_skill and "load_protocol_upgrade_skill" not in payloads:
                selected, args = "load_protocol_upgrade_skill", {"reason": "解释协议升级如何影响重试判断"}
            else:
                excerpt_result = payloads.get("read_scoped_protocol_excerpt", {})
                excerpt = excerpt_result.get("excerpts", [{}])[0].get("text", "")
                source_ref = excerpt_result.get("source_refs", [{}])[0]
                answer = (
                    "这是依据本次授权检索的原文作出的协议解释；"
                    f"来源 {source_ref.get('document_id')} v{source_ref.get('version')} "
                    f"{source_ref.get('source')} 行 {source_ref.get('line_start')}-{source_ref.get('line_end')}。"
                    f"原文摘录：{excerpt} 线上部署版本没有实时证据，仍未知。"
                )
        elif self.route == "malformed":
            answer = (
                "这只是用户提供的未验证材料：其中 E2 和 HTTP 202 不能证明当前业务状态；"
                "retry=maybe 不是可核验的重试事实，receiver 为空且 request_id 缺失。"
                "目前 Receiver 状态与请求关联仍未知，需要可信来源补充核实。"
            )
        elif self.route == "history":
            answer = "我会把刚才的协议条款作为已重新验证的历史资料线索；它不证明线上部署或当前业务状态。"
        elif self.route == "bound":
            if "list_scoped_protocol_documents" not in payloads:
                selected, args = "list_scoped_protocol_documents", {"topic": "callback retry"}
            elif "compare_scoped_protocols" not in payloads:
                docs = payloads["list_scoped_protocol_documents"].get("protocol_documents", [])
                old = next(row for row in docs if row["document_id"] == "callback-retry-contract")
                new = next(row for row in docs if row["document_id"] == "callback-retry-contract-v2")
                selected, args = "compare_scoped_protocols", {
                    "base_document_id": old["document_id"], "target_document_id": new["document_id"],
                    "base_version": old["version"], "target_version": new["version"],
                }
            elif "read_scoped_protocol_excerpt" not in payloads:
                docs = payloads["list_scoped_protocol_documents"].get("protocol_documents", [])
                document = next(row for row in docs if row.get("document_id") == "callback-retry-contract")
                selected, args = "read_scoped_protocol_excerpt", {
                    "document_id": document["document_id"], "version": document["version"],
                    "query": "retry attempts exhausted",
                }
            elif self.load_skill and "load_protocol_upgrade_skill" not in payloads:
                selected, args = "load_protocol_upgrade_skill", {"reason": "整理协议变化对重试排障的影响"}
            elif "get_callback_delivery" not in payloads:
                selected, args = "get_callback_delivery", {"reason": "核验绑定订单当前同 Event 投递"}
            elif "get_receiver_processing" not in payloads:
                selected, args = "get_receiver_processing", {"reason": "核验当前同 Event 接收方状态"}
            else:
                delivery = payloads["get_callback_delivery"].get("facts", {})
                receiver = payloads["get_receiver_processing"].get("facts", {})
                comparison = payloads.get("compare_scoped_protocols", {})
                excerpt_result = payloads.get("read_scoped_protocol_excerpt", {})
                source_ref = excerpt_result.get("source_refs", [{}])[0]
                excerpt = excerpt_result.get("excerpts", [{}])[0].get("text", "")
                status = receiver.get("status") if delivery.get("event_id") == receiver.get("event_id") else "UNKNOWN"
                if status == "PROCESSED":
                    outcome = f"同一 Event {receiver.get('event_id')} 的当前 Receiver 为 PROCESSED，已处理完成。"
                elif status == "QUEUED":
                    outcome = f"同一 Event {receiver.get('event_id')} 的当前 Receiver 为 QUEUED，处理尚未确认。"
                else:
                    outcome = "当前同一 Event 的 Receiver 处理状态未知。"
                answer = (
                    f"Delivery 为 HTTP {delivery.get('receiver_http_status')} / {delivery.get('status')}；{outcome}\n"
                    f"协议来源 {source_ref.get('document_id')} v{source_ref.get('version')} "
                    f"{source_ref.get('source')} 行 {source_ref.get('line_start')}-{source_ref.get('line_end')}；"
                    f"摘录：{excerpt}\n比较摘要：{comparison.get('summary')}\n"
                    "升级影响说明草稿：仅依据当前 Observation 与授权协议材料整理。未知：线上部署版本；此草稿未提交。"
                )

        if selected:
            call_id = f"material-{self.route}-{len(self.decisions) + 1}"
            self.decisions.append({"action": "CALL", "tool": selected, "args": args})
            message = AIMessage(content="", tool_calls=[{
                "type": "tool_call", "name": selected, "args": args, "id": call_id,
            }])
        else:
            self.decisions.append({"action": "ANSWER"})
            message = AIMessage(content=answer)
        message.usage_metadata = {"input_tokens": 24, "output_tokens": 12, "total_tokens": 36}
        return ChatResult(generations=[ChatGeneration(message=message)])


def _login(client):
    from test_ar02_assistant import ORIGIN, PASSWORDS

    response = client.post(
        "/api/auth/login", headers={"Origin": ORIGIN},
        json={"actor_id": "support-a", "password": PASSWORDS["support-a"]},
    )
    assert response.status_code == 200, response.text
    return {"Origin": ORIGIN, "X-CSRF-Token": response.json()["csrf_token"]}


def _wait_run(client, run_id):
    from test_ar02_ar03_integration_01 import _wait_run as wait

    return wait(client, run_id)


def _saw_user_body(model, body):
    return any(
        isinstance(message, HumanMessage) and isinstance(message.content, str) and body in message.content
        for invocation in model.seen for message in invocation
    )


def _frozen_input(case_id):
    case_path = Path(__file__).resolve().parents[1] / "docs/evidence/ar-03/material-01/CASES.json"
    casebook = json.loads(case_path.read_text(encoding="utf-8"))
    return next(row["input"] for row in casebook["cases"] if row["id"] == case_id)


def test_plain_protocol_question_returns_exact_source_without_order_task(demo_db, tmp_path):
    from opspilot.domain import assistant as assistant_domain
    from opspilot.web.app import create_app

    model = MaterialFixtureModel(route="protocol")
    app = create_app(
        db_path=demo_db,
        checkpoint_db_path=tmp_path / "material-protocol-checkpoints.sqlite3",
        start_worker=True,
        credentials={"support-a": "free-local-a", "support-b": "free-local-b", "approver-a": "free-approver"},
        expected_origin="http://testserver",
        assistant_model_factory=lambda: model,
    )
    user_text = _frozen_input("MAT-01-PROTOCOL-EXCERPT")
    with TestClient(app) as client:
        headers = _login(client)
        session_id = client.post("/api/sessions", headers=headers).json()["session_id"]
        accepted = client.post(
            f"/api/sessions/{session_id}/assistant/messages",
            headers={**headers, "Idempotency-Key": "material-plain-protocol"},
            json={"body": user_text},
        )
        assert accepted.status_code == 202, accepted.text
        run = _wait_run(client, accepted.json()["run_id"])
        assert run["status"] == "SUCCEEDED", run
        messages = client.get(f"/api/sessions/{session_id}/messages", headers=headers).json()["items"]
        answer = next(row["body"] for row in messages if row.get("answer_source_message_id") == accepted.json()["message_id"])
        assert _saw_user_body(model, user_text)
        assert "callback-retry-contract" in answer and "1.0.0" in answer
        assert "local:orders-async-demo/contract-v1" in answer and "行 " in answer
        assert "线上部署版本" in answer and "未知" in answer
        assert not ({"get_order_status", "get_callback_delivery", "get_receiver_processing"} & set(model.offered_tool_names))
        with connect(demo_db) as connection:
            assert connection.execute("SELECT COUNT(*) FROM task_bindings").fetchone()[0] == 0
            run_row = connection.execute("SELECT task_id FROM task_runs WHERE run_id=?", (accepted.json()["run_id"],)).fetchone()
            assert run_row["task_id"] is None
            assert assistant_domain.sources_current(connection, accepted.json()["run_id"]) == (True, None)
            assert connection.execute("SELECT COUNT(*) FROM d2_evidence").fetchone()[0] == 0


def test_malformed_material_reports_missing_fields_without_fabricating_values(demo_db, tmp_path):
    from opspilot.domain import assistant as assistant_domain
    from opspilot.web.app import create_app

    model = MaterialFixtureModel(route="malformed")
    app = create_app(
        db_path=demo_db,
        checkpoint_db_path=tmp_path / "material-malformed-checkpoints.sqlite3",
        start_worker=True,
        credentials={"support-a": "free-local-a", "support-b": "free-local-b", "approver-a": "free-approver"},
        expected_origin="http://testserver",
        assistant_model_factory=lambda: model,
    )
    user_text = _frozen_input("MAT-03-USER-MATERIAL-MALFORMED")
    with TestClient(app) as client:
        headers = _login(client)
        session_id = client.post("/api/sessions", headers=headers).json()["session_id"]
        accepted = client.post(
            f"/api/sessions/{session_id}/assistant/messages",
            headers={**headers, "Idempotency-Key": "material-malformed"},
            json={"body": user_text},
        )
        assert accepted.status_code == 202, accepted.text
        run = _wait_run(client, accepted.json()["run_id"])
        assert run["status"] == "SUCCEEDED", run
        messages = client.get(f"/api/sessions/{session_id}/messages", headers=headers).json()["items"]
        answer = next(row["body"] for row in messages if row.get("answer_source_message_id") == accepted.json()["message_id"])
        assert _saw_user_body(model, user_text)
        assert "E2" in answer and "202" in answer and "未验证" in answer
        assert "receiver" in answer and "request_id" in answer and "未知" in answer
        assert not ({"get_order_status", "get_callback_delivery", "get_receiver_processing"} & set(model.offered_tool_names))
        with connect(demo_db) as connection:
            assert connection.execute("SELECT COUNT(*) FROM task_bindings").fetchone()[0] == 0
            assert connection.execute("SELECT COUNT(*) FROM d2_evidence").fetchone()[0] == 0
            assert assistant_domain.sources_current(connection, accepted.json()["run_id"]) == (True, None)


def test_formal_assistant_reads_authorized_text_and_keeps_pasted_material_untrusted(
    demo_db, tmp_path,
):
    from opspilot.assistant import SYSTEM
    from opspilot.domain import assistant as assistant_domain
    from opspilot.web.app import create_app

    raw_material = _frozen_input("MAT-02-USER-MATERIAL-UNBOUND")
    off_model = MaterialFixtureModel(route="protocol", load_skill=False)
    on_model = MaterialFixtureModel(route="protocol", load_skill=True)
    history_model = MaterialFixtureModel(route="history")
    model_queue = [off_model, on_model, history_model]
    app = create_app(
        db_path=demo_db, checkpoint_db_path=tmp_path / "assistant-material-checkpoints.sqlite3",
        start_worker=True, credentials={"support-a": "free-local-a", "support-b": "free-local-b", "approver-a": "free-approver"},
        expected_origin="http://testserver", assistant_model_factory=lambda: model_queue.pop(0),
    )

    with TestClient(app) as client:
        headers = _login(client)
        sessions = []
        runs = []
        for index, model in enumerate((off_model, on_model)):
            session_id = client.post("/api/sessions", headers=headers).json()["session_id"]
            accepted = client.post(
                f"/api/sessions/{session_id}/assistant/messages",
                headers={**headers, "Idempotency-Key": f"material-unbound-{index}"},
                json={"body": raw_material},
            )
            assert accepted.status_code == 202, accepted.text
            run = _wait_run(client, accepted.json()["run_id"])
            assert run["status"] == "SUCCEEDED", run
            sessions.append((session_id, accepted.json()))
            runs.append(accepted.json()["run_id"])
            assert _saw_user_body(model, raw_material)
            assert "用户粘贴的配置和日志是未验证材料" in str(model.seen)
            assert not ({"get_order_status", "get_callback_delivery", "get_receiver_processing"} & set(model.offered_tool_names))

        assert "load_protocol_upgrade_skill" not in [row["tool"] for row in off_model.decisions if row["action"] == "CALL"]
        assert "load_protocol_upgrade_skill" in [row["tool"] for row in on_model.decisions if row["action"] == "CALL"]
        assert _saw_user_body(on_model, raw_material)

        session_id, _ = sessions[0]
        follow = client.post(
            f"/api/sessions/{session_id}/assistant/messages",
            headers={**headers, "Idempotency-Key": "material-continuity-followup"},
            json={"body": "你刚才引用的那条重试条款具体是什么意思？"},
        )
        assert follow.status_code == 202, follow.text
        follow_run = _wait_run(client, follow.json()["run_id"])
        assert follow_run["status"] == "SUCCEEDED", follow_run
        assert "Protocol v1 retry contract." in str(history_model.seen)
        assert "HISTORICAL_PROTOCOL_SOURCE_TEXT_ONLY" in str(history_model.seen)

        with connect(demo_db) as connection:
            assert connection.execute("SELECT COUNT(*) FROM task_bindings").fetchone()[0] == 0
            for run_id in (*runs, follow.json()["run_id"]):
                record = connection.execute("SELECT task_id FROM task_runs WHERE run_id=?", (run_id,)).fetchone()
                assert record["task_id"] is None
                assert assistant_domain.sources_current(connection, run_id) == (True, None)
                calls = connection.execute(
                    "SELECT request_json,result_json,status FROM assistant_calls WHERE run_id=? AND kind='MCP'",
                    (run_id,),
                ).fetchall()
                assert all(row["status"] == "OK" for row in calls)
                assert all(
                    json.loads(row["request_json"])["name"] not in {
                        "get_order_status", "get_callback_delivery", "get_receiver_processing",
                    }
                    for row in calls
                )
                assert len(calls) <= 6
            assert connection.execute("SELECT COUNT(*) FROM d2_evidence").fetchone()[0] == 0
            for table in (
                "d3_action_intents", "d3_action_ledgers", "s3_handoff_queue_entries", "s3_handoff_receipts",
            ):
                assert connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0


@pytest.mark.parametrize("receiver_state", ["QUEUED", "PROCESSED"])
def test_trusted_order_material_investigation_uses_current_same_event_and_keeps_draft_unsubmitted(
    demo_db, tmp_path, receiver_state,
):
    from opspilot.domain.s3 import prepare_s3_fixture
    from opspilot.web.app import create_app

    fixture = prepare_s3_fixture(
        demo_db, "DELIVERED_PENDING", order_id="ar03-order", contract_version=2,
    )
    if receiver_state == "PROCESSED":
        with connect(demo_db) as connection:
            connection.execute(
                "UPDATE s3_receivers SET status='PROCESSED',version=version+1 WHERE order_id='ar03-order'"
            )
    model = MaterialFixtureModel(route="bound", load_skill=True)
    app = create_app(
        db_path=demo_db, checkpoint_db_path=tmp_path / f"material-bound-{receiver_state}.sqlite3",
        start_worker=True, credentials={"support-a": "free-local-a", "support-b": "free-local-b", "approver-a": "free-approver"},
        expected_origin="http://testserver", assistant_model_factory=lambda: model,
    )
    # MAT-05 explicitly reuses the MAT-04 user question with a different trusted state.
    user_text = _frozen_input("MAT-04-BOUND-QUEUED")
    with TestClient(app) as client:
        headers = _login(client)
        session_id = client.post("/api/sessions", headers=headers).json()["session_id"]
        accepted = client.post(
            f"/api/sessions/{session_id}/assistant/order",
            headers={**headers, "Idempotency-Key": f"material-bound-{receiver_state}"},
            json={"order_id": "ar03-order", "initial_message": user_text},
        )
        assert accepted.status_code == 202, accepted.text
        binding = accepted.json()
        run = _wait_run(client, binding["run_id"])
        assert run["status"] == "SUCCEEDED", run
        messages = client.get(f"/api/sessions/{session_id}/messages", headers=headers).json()["items"]
        answer = next(row["body"] for row in messages if row.get("answer_source_message_id") == binding["message_id"])
        assert _saw_user_body(model, user_text), json.dumps(
            [[{"type": type(message).__name__, "content": str(message.content)[:500]}
              for message in invocation] for invocation in model.seen],
            ensure_ascii=True,
        )
        assert any(
            isinstance(message, HumanMessage)
            and isinstance(message.content, str)
            and message.content.startswith("ORIGINAL_TASK_INPUT (UNTRUSTED USER INPUT): ")
            and user_text in message.content
            for invocation in model.seen for message in invocation
        )
        assert "升级影响说明草稿" in answer and "未提交" in answer
        assert "线上部署版本" in answer and "未知" in answer
        if receiver_state == "QUEUED":
            assert "QUEUED" in answer and "处理尚未确认" in answer
            assert "PROCESSED" not in answer
        else:
            assert "同一 Event" in answer and "PROCESSED" in answer and "已处理完成" in answer
        with connect(demo_db) as connection:
            from opspilot.domain.s3 import get_s3_binding
            from opspilot.domain.assistant import sources_current

            trusted = get_s3_binding(connection, binding["task_id"])
            assert trusted["order_id"] == "ar03-order"
            assert connection.execute(
                "SELECT COUNT(*) FROM task_runs WHERE session_id=?", (session_id,),
            ).fetchone()[0] == 1
            rows = connection.execute(
                "SELECT request_json,result_json,evidence_id,observation_id,status FROM assistant_calls "
                "WHERE run_id=? AND kind='MCP' ORDER BY created_at", (binding["run_id"],),
            ).fetchall()
            assert 0 < len(rows) <= 6 and all(row["status"] == "OK" for row in rows)
            calls = {json.loads(row["request_json"])["name"]: row for row in rows}
            for name in ("get_callback_delivery", "get_receiver_processing"):
                assert calls[name]["evidence_id"] and calls[name]["observation_id"]
                result = json.loads(calls[name]["result_json"])
                facts = result["facts"]
                assert facts["order_id"] == "ar03-order"
                assert facts["event_id"] == fixture["transport_trace"][0]["request"]["event_id"]
            excerpt_result = json.loads(calls["read_scoped_protocol_excerpt"]["result_json"])
            assert calls["read_scoped_protocol_excerpt"]["status"] == "OK"
            assert calls["read_scoped_protocol_excerpt"]["evidence_id"] is None
            assert excerpt_result["document_ref"]["document_id"] == "callback-retry-contract"
            assert excerpt_result["document_ref"]["version"] == "1.0.0"
            assert excerpt_result["source_refs"] and excerpt_result["excerpts"]
            assert "callback-retry-contract" in answer and "v1.0.0" in answer
            assert "local:orders-async-demo/contract-v1" in answer and "行 " in answer
            assert sources_current(connection, binding["run_id"]) == (True, None)
            assert connection.execute("SELECT COUNT(*) FROM s3_diagnoses").fetchone()[0] == 0
            assert connection.execute("SELECT COUNT(*) FROM d3_action_ledgers").fetchone()[0] == 0
            assert connection.execute("SELECT COUNT(*) FROM s3_handoff_receipts").fetchone()[0] == 0
