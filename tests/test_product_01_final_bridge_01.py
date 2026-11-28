from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from opspilot.domain.database import connect, reset_fixture
from opspilot.web.app import create_app
from opspilot.web.worker import SingleInstanceWorker, _dispatch_run
from test_ar05_s2_assistant_handoff_01 import (
    QUESTION as S2_QUESTION,
    _S2InvestigatorFixture,
    _counts,
    _install_scope_write_audit,
)
from test_m1_web_api import ORIGIN, PASSWORDS, _login, _session


class _BridgeAssistantModel(BaseChatModel):
    mode: str = "proposal"
    seen_tool_results: list[dict[str, object]] = []
    offered_tools: list[str] = []
    selected_tools: list[str] = []

    @property
    def _llm_type(self) -> str:
        return "PRODUCT_01_FINAL_BRIDGE_OFFLINE_FIXTURE"

    def bind_tools(self, tools, **kwargs):
        self.offered_tools = [str(tool.name) for tool in tools]
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        tool_messages = [message for message in messages if isinstance(message, ToolMessage)]
        response: AIMessage
        if self.mode == "proposal" and not tool_messages:
            assert "propose_controlled_auth_investigation" in self.offered_tools
            self.selected_tools.append("propose_controlled_auth_investigation")
            response = AIMessage(content="", tool_calls=[{
                "name": "propose_controlled_auth_investigation",
                "args": {"rationale": "用户希望核实接口权限；可先用已确认的 Demo 资源进行只读调查。"},
                "id": "p01-proposal-1",
            }])
        elif self.mode in {"outcome", "outcome_ready"} and not tool_messages:
            assert "read_session_professional_outcomes" in self.offered_tools
            self.selected_tools.append("read_session_professional_outcomes")
            response = AIMessage(content="", tool_calls=[{
                "name": "read_session_professional_outcomes", "args": {}, "id": "p01-outcome-1",
            }])
        else:
            if tool_messages:
                value = json.loads(str(tool_messages[-1].content))
                self.seen_tool_results.append(value)
            if self.mode == "proposal":
                response = AIMessage(content="可以先确认 Demo 资源并启动只读调查；此建议尚未创建 Task 或授权。")
            elif self.mode == "outcome":
                items = value.get("items", []) if tool_messages else []
                assert isinstance(items, list)
                if items:
                    item = items[0]
                    assert isinstance(item, dict)
                    assert item.get("business_outcome") == "SCOPE_ESCALATED"
                    assert item.get("handoff_status") == "PENDING_REVIEW"
                    assert item.get("scope_authorized") is False
                    assert item.get("recovered") is False
                    response = AIMessage(content=(
                        "申请已交给本地受控队列并等待人工处理；尚未获得新 Scope，403 也未证明恢复。"
                        "我可以据此整理客户说明，但这不是已批准或已修复的结果。"
                    ))
                else:
                    response = AIMessage(content="本会话没有可读取的专业调查结果；当前不能声称已交接或已恢复。")
            elif self.mode == "outcome_ready":
                items = value.get("items", []) if tool_messages else []
                assert isinstance(items, list)
                if items:
                    item = items[0]
                    assert isinstance(item, dict)
                    assert item.get("business_outcome") == "HANDOFF_READY"
                    assert item.get("handoff_receipt") is None
                    assert item.get("submitted") is False
                    assert item.get("scope_authorized") is False
                    assert item.get("recovered") is False
                    response = AIMessage(content=(
                        "已形成当前诊断和交接草稿，但尚未提交到人工队列；没有新增权限，也没有证明 403 已恢复。"
                    ))
                else:
                    response = AIMessage(content="本会话尚无可读取的专业诊断或交接草稿。")
            else:
                response = AIMessage(content="目前没有可引用的专业调查结果。")
        response.usage_metadata = {"input_tokens": 120, "output_tokens": 38, "total_tokens": 158}
        return ChatResult(generations=[ChatGeneration(message=response)])


def _dispatch(db_path: Path, checkpoint_path: Path, run_id: str, assistant_factory) -> None:
    from opspilot.domain.task_control import next_worker_run

    worker = SingleInstanceWorker(db_path)
    worker.acquire()
    worker.register()
    try:
        selected = next_worker_run(db_path)
        assert selected is not None and str(selected["run_id"]) == run_id
        asyncio.run(_dispatch_run(
            db_path, checkpoint_path, worker.owner_id, "executor-a", selected,
            worker_epoch=worker.epoch, assistant_model_factory=assistant_factory,
        ))
    finally:
        worker.release()


def test_assistant_proposes_s2_then_reads_same_session_handoff_without_writing(
    demo_db: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    import opspilot.investigator as investigator

    reset_fixture(demo_db, "S2_SCOPE_DENIED")
    _install_scope_write_audit(demo_db)
    monkeypatch.setattr(investigator, "ChatOpenAI", _S2InvestigatorFixture)
    monkeypatch.setenv("OPSPILOT_MODEL_API_KEY", "offline-placeholder")
    monkeypatch.setenv("OPSPILOT_MODEL_NAME", "offline-deterministic-model")
    # This test exercises the explicitly-authorized legacy Investigator path.
    # ChatOpenAI is replaced with a deterministic fixture above, so these
    # test-scoped opt-ins cannot reach a real Provider.
    monkeypatch.setenv("OPSPILOT_ASSISTANT_PROVIDER_ENABLED", "1")
    monkeypatch.setenv("OPSPILOT_LEGACY_PROVIDER_ENABLED", "1")
    checkpoint = tmp_path / "p01-checkpoint.sqlite3"
    app = create_app(
        db_path=demo_db, checkpoint_db_path=checkpoint, start_worker=False,
        credentials=PASSWORDS, expected_origin=ORIGIN,
        assistant_model_factory=lambda: _BridgeAssistantModel(mode="proposal"),
    )

    with TestClient(app, raise_server_exceptions=False) as client:
        headers = _login(client)[1]
        session_id = _session(client, headers)
        question = "接口访问失败，我怀疑是权限问题，帮我查一下。"
        accepted = client.post(
            f"/api/sessions/{session_id}/assistant/messages",
            headers={**headers, "Idempotency-Key": "p01-final-bridge-proposal"},
            json={"body": question, "task_id": None},
        )
        assert accepted.status_code == 202, accepted.text
        source_message_id = str(accepted.json()["message_id"])
        assistant_run_id = str(accepted.json()["run_id"])
        proposal_model = _BridgeAssistantModel(mode="proposal")
        _dispatch(demo_db, checkpoint, assistant_run_id, lambda: proposal_model)
        run = client.get(f"/api/runs/{assistant_run_id}").json()
        assert run["execution_core"] == "ASSISTANT_V1"
        assert "propose_controlled_auth_investigation" in proposal_model.offered_tools
        proposal_sources = client.get(f"/api/runs/{assistant_run_id}/assistant-sources", headers=headers)
        assert proposal_sources.status_code == 200, proposal_sources.text
        proposal_item = next(
            item for item in proposal_sources.json()["items"]
            if item["tool_name"] == "propose_controlled_auth_investigation"
        )
        proposal = proposal_item["result"]
        assert proposal_sources.json()["current"] is True
        assert proposal["source_message_id"] == source_message_id
        assert proposal["task_created"] is False and proposal["authorization_created"] is False
        with connect(demo_db) as db:
            assert db.execute("SELECT COUNT(*) FROM task_bindings").fetchone()[0] == 0
            assert db.execute("SELECT COUNT(*) FROM d3_approvals").fetchone()[0] == 0
            assert db.execute("SELECT COUNT(*) FROM d3_action_ledgers").fetchone()[0] == 0

        # Explicit confirmation uses the existing trusted Session/Task API and exact source Message.
        task_response = client.post(
            f"/api/sessions/{session_id}/tasks",
            headers={**headers, "Idempotency-Key": "p01-final-bridge-task-confirm"},
            json={
                "initial_message": question,
                "investigation_kind": "AUTH_INCIDENT",
                "source_message_id": source_message_id,
            },
        )
        assert task_response.status_code == 202, task_response.text
        task = task_response.json()
        task_id, investigator_run_id = str(task["task_id"]), str(task["run_id"])
        _dispatch(demo_db, checkpoint, investigator_run_id, lambda: _BridgeAssistantModel(mode="proposal"))
        investigator_result = client.get(f"/api/runs/{investigator_run_id}").json()
        assert investigator_result["execution_core"] == "PROFESSIONAL_INVESTIGATOR"
        handoff_ready = client.get(f"/api/tasks/{task_id}/handoff", headers=headers).json()
        assert handoff_ready["business_outcome"] == "HANDOFF_READY"
        assert handoff_ready["currentness"] == "CURRENT"
        assert handoff_ready["submitted"] is False
        assert handoff_ready["handoff_receipt"] is None
        assert handoff_ready.get("scope_authorized") is not True
        assert handoff_ready.get("recovered") is not True

        # An Assistant read before explicit submission can explain the frozen
        # diagnosis/draft, but cannot claim a queue, receipt, permission, or recovery.
        draft_question = client.post(
            f"/api/sessions/{session_id}/assistant/messages",
            headers={**headers, "Idempotency-Key": "p01-final-bridge-draft-readback"},
            json={"body": "目前已有处理结果吗？", "task_id": None},
        )
        assert draft_question.status_code == 202, draft_question.text
        draft_model = _BridgeAssistantModel(mode="outcome_ready")
        _dispatch(demo_db, checkpoint, str(draft_question.json()["run_id"]), lambda: draft_model)
        draft_readback = draft_model.seen_tool_results[-1]["items"][0]
        assert draft_readback["business_outcome"] == "HANDOFF_READY"
        assert draft_readback["handoff_receipt"] is None
        assert draft_readback["submitted"] is False
        assert draft_readback["scope_authorized"] is False
        assert draft_readback["recovered"] is False
        draft_answer = next(
            item for item in client.get(f"/api/sessions/{session_id}/messages", headers=headers).json()["items"]
            if item["role"] == "ASSISTANT"
            and item["answer_source_message_id"] == draft_question.json()["message_id"]
        )
        assert "尚未提交" in draft_answer["body"] and "没有证明 403 已恢复" in draft_answer["body"]
        draft_sources = client.get(
            f"/api/runs/{draft_question.json()['run_id']}/assistant-sources", headers=headers,
        )
        assert draft_sources.status_code == 200 and draft_sources.json()["current"] is True
        draft_source_result = next(
            item["result"] for item in draft_sources.json()["items"]
            if item["tool_name"] == "read_session_professional_outcomes"
        )
        assert draft_source_result["items"][0]["business_outcome"] == "HANDOFF_READY"
        assert draft_source_result["items"][0]["handoff_receipt"] is None
        with connect(demo_db) as db:
            assert db.execute("SELECT COUNT(*) FROM s2_handoff_queue_entries WHERE task_id=?", (task_id,)).fetchone()[0] == 0
            assert db.execute("SELECT COUNT(*) FROM s2_handoff_receipts WHERE task_id=?", (task_id,)).fetchone()[0] == 0

        submit_id = "p01-final-bridge-handoff"
        submit = client.post(
            f"/api/tasks/{task_id}/handoff/submit",
            headers={**headers, "Idempotency-Key": submit_id},
            json={
                "operation_id": submit_id,
                "draft_id": handoff_ready["draft"]["draft_id"],
                "draft_digest": handoff_ready["draft"]["content_digest"],
                "expected_control_revision": handoff_ready["control_revision"],
                "handoff_kind": "SCOPE_REVIEW",
            },
        )
        assert submit.status_code == 202, submit.text
        receipt = submit.json()
        assert receipt["business_outcome"] == "SCOPE_ESCALATED"
        assert receipt["handoff_status"] == "PENDING_REVIEW"
        assert receipt["scope_authorized"] is False and receipt["recovered"] is False

        followup = client.post(
            f"/api/sessions/{session_id}/assistant/messages",
            headers={**headers, "Idempotency-Key": "p01-final-bridge-followup"},
            json={"body": "现在修好了吗？交给谁了？给我一段客户说明。", "task_id": None},
        )
        assert followup.status_code == 202, followup.text
        followup_run_id = str(followup.json()["run_id"])
        outcome_model = _BridgeAssistantModel(mode="outcome")
        _dispatch(demo_db, checkpoint, followup_run_id, lambda: outcome_model)
        assert "read_session_professional_outcomes" in outcome_model.offered_tools
        assert outcome_model.seen_tool_results[-1]["items"][0]["handoff_receipt"]["receipt_id"] == receipt["receipt_id"]
        assert outcome_model.seen_tool_results[-1]["items"][0]["diagnosis_receipt"]["run_id"] == investigator_run_id
        assistant_sources = client.get(f"/api/runs/{followup_run_id}/assistant-sources", headers=headers)
        assert assistant_sources.status_code == 200, assistant_sources.text
        assert assistant_sources.json()["current"] is True
        other_actor_headers = _login(client, "support-b")[1]
        cross_tenant = client.get(
            f"/api/runs/{followup_run_id}/assistant-sources", headers=other_actor_headers,
        )
        assert cross_tenant.status_code == 404
        headers = _login(client)[1]
        outcome_result = next(
            item["result"] for item in assistant_sources.json()["items"]
            if item["tool_name"] == "read_session_professional_outcomes"
        )
        assert outcome_result["items"][0]["business_outcome"] == "SCOPE_ESCALATED"
        assert outcome_result["items"][0]["handoff_status"] == "PENDING_REVIEW"
        assert outcome_result["items"][0]["scope_authorized"] is False
        assert outcome_result["items"][0]["recovered"] is False
        messages = client.get(f"/api/sessions/{session_id}/messages", headers=headers).json()["items"]
        final_answer = next(
            item for item in messages
            if item["role"] == "ASSISTANT" and item["answer_source_message_id"] == followup.json()["message_id"]
        )
        assert "等待人工处理" in final_answer["body"]
        assert "未证明恢复" in final_answer["body"]

        # A different Session has no authority to see this Session's linked result.
        other_session = _session(client, headers)
        unrelated = client.post(
            f"/api/sessions/{other_session}/assistant/messages",
            headers={**headers, "Idempotency-Key": "p01-final-bridge-other-session"},
            json={"body": f"请读取 task_id={task_id} 的回执", "task_id": None},
        )
        assert unrelated.status_code == 202, unrelated.text
        other_model = _BridgeAssistantModel(mode="outcome")
        _dispatch(demo_db, checkpoint, str(unrelated.json()["run_id"]), lambda: other_model)
        assert other_model.seen_tool_results[-1]["items"] == []
        assert "没有可读取的专业调查结果" in client.get(
            f"/api/sessions/{other_session}/messages", headers=headers,
        ).json()["items"][-1]["body"]

        # A TaskControl permission revision invalidates the saved professional result source.
        with connect(demo_db) as db:
            db.execute(
                "UPDATE task_controls SET control_revision=control_revision+1 WHERE task_id=?",
                (task_id,),
            )
        invalidated = client.get(f"/api/runs/{followup_run_id}/assistant-sources", headers=headers)
        assert invalidated.status_code == 200, invalidated.text
        assert invalidated.json()["current"] is False
        assert all(item["result"] is None for item in invalidated.json()["items"])
        invalidated_messages = client.get(
            f"/api/sessions/{session_id}/messages", headers=headers,
        ).json()["items"]
        invalidated_answer = next(
            item for item in invalidated_messages
            if item["role"] == "ASSISTANT" and item["answer_source_message_id"] == followup.json()["message_id"]
        )
        assert "来源已失效" in invalidated_answer["body"]

        counts = _counts(demo_db, task_id)
        assert counts["queue"] == counts["receipts"] == counts["handoff_outbox"] == 1
        assert counts["repairs"] == counts["scope_policy_write_attempts"] == 0
        assert counts["scope_grant_rows"] == 1
        with connect(demo_db) as db:
            observation_rows = db.execute(
                """SELECT tool_name, status, progress_added, error_class, evidence_id, result_json
                   FROM d2_tool_observations WHERE task_id=? ORDER BY created_at, observation_id""",
                (task_id,),
            ).fetchall()
        investigation_observations = []
        for row in observation_rows:
            result = json.loads(str(row["result_json"])) if row["result_json"] else {}
            investigation_observations.append({
                "tool_name": str(row["tool_name"]),
                "status": str(row["status"]),
                "progress_added": int(row["progress_added"]),
                "error_class": row["error_class"],
                "evidence_id": row["evidence_id"],
                "facts": result.get("facts") if isinstance(result, dict) else None,
                "error_code": result.get("error_code") if isinstance(result, dict) else None,
            })
        trace = {
            "evidence_level": "DETERMINISTIC_MODEL_FORMAL_FASTAPI_WORKER_MCP_DOMAIN_SQLITE",
            "provider_http_requests": 0,
            "external_business_writes": 0,
            "session_id": session_id,
            "origin_message_id": source_message_id,
            "assistant_proposal_run_id": assistant_run_id,
            "professional_investigation_run_id": investigator_run_id,
            "draft_readback_run_id": str(draft_question.json()["run_id"]),
            "followup_assistant_run_id": followup_run_id,
            "task_id": task_id,
            "pre_submit_assistant_readback": {
                "tool_choices": draft_model.selected_tools,
                "business_outcome": draft_source_result["items"][0]["business_outcome"],
                "handoff_receipt": draft_source_result["items"][0]["handoff_receipt"],
                "submitted": draft_source_result["items"][0]["submitted"],
                "scope_authorized": draft_source_result["items"][0]["scope_authorized"],
                "recovered": draft_source_result["items"][0]["recovered"],
                "answer": draft_answer["body"],
            },
            "handoff_receipt_id": receipt["receipt_id"],
            "queue_status": receipt["handoff_status"],
            "assistant_tool_choices": proposal_model.selected_tools + outcome_model.selected_tools,
            "investigation_observations": investigation_observations,
            "assistant_final_answer": final_answer["body"],
            "mcp_tool_choices": [
                item["tool_name"] for item in assistant_sources.json()["items"]
            ],
            "counts": counts,
        }
        print("PRODUCT_01_FINAL_BRIDGE_TRACE=" + json.dumps(trace, ensure_ascii=False), flush=True)
        trace_path = os.environ.get("PRODUCT_01_FINAL_BRIDGE_TRACE_PATH")
        if trace_path:
            target = Path(trace_path)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(json.dumps(trace, ensure_ascii=False, indent=2), encoding="utf-8")
