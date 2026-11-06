from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from opspilot.domain.database import connect, reset_fixture
from opspilot.domain.task_control import next_worker_run
from opspilot.web.app import create_app
from opspilot.web.worker import SingleInstanceWorker, _dispatch_run
from test_m1_web_api import ORIGIN, PASSWORDS, _login, _session


QUESTION = "我们的 API 返回 403，感觉是调用权限不够。帮我查一下，如果需要人工开通权限，帮我准备交接。"


class _AssistantAnswerModel(BaseChatModel):
    @property
    def _llm_type(self) -> str:
        return "AR05_S2_OFFLINE_ASSISTANT_FIXTURE"

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        response = AIMessage(content=(
            "HTTP 403 表示本次请求未获准，但单凭用户描述无法确认具体授权原因。"
            "可以先在可信绑定资源范围内调查；是否提交申请由你明确确认。"
        ))
        response.usage_metadata = {"input_tokens": 12, "output_tokens": 25, "total_tokens": 37}
        return ChatResult(generations=[ChatGeneration(message=response)])


class _S2InvestigatorFixture:
    """Deterministic model for the formal Investigator path; MCP remains real/local."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        self.available_tools: list[dict[str, Any]] = []
        self.seen_tools: list[str] = []
        self.turn = 0

    def bind_tools(self, tools, **kwargs):
        self.available_tools = list(tools)
        return self

    async def ainvoke(self, messages):
        names = [str(item.get("function", {}).get("name")) for item in self.available_tools]
        if "probe_endpoint" in names:
            name = "probe_endpoint"
            args: dict[str, object] = {"service_id": "orders-demo", "integration_id": "integration-a"}
        elif "get_scope_authz_facts" in names:
            human = str(messages[-1].content)
            marker = human.find("\n{")
            assert marker >= 0, "S2 model context must expose the persisted current observation"
            context = json.loads(human[marker + 1:])
            probes = [
                item for item in context["current_mcp_evidence"]
                if item.get("fact_type") == "endpoint_probe"
            ]
            request_id = probes[-1]["facts"]["request_id"]
            name = "get_scope_authz_facts"
            args = {"request_id": request_id}
        else:
            response = AIMessage(content=(
                "本地确定性模型已按当前 Run 的可信 MCP 事实完成诊断；申请内容仍需你确认后才能提交。"
            ))
            response.usage_metadata = {"input_tokens": 80, "output_tokens": 20, "total_tokens": 100}
            return response
        self.turn += 1
        self.seen_tools.append(name)
        response = AIMessage(
            content="",
            tool_calls=[{"name": name, "args": args, "id": f"ar05-s2-fixture-{self.turn}"}],
        )
        response.usage_metadata = {"input_tokens": 100, "output_tokens": 10, "total_tokens": 110}
        return response


def _counts(db_path: Path, task_id: str) -> dict[str, int]:
    with connect(db_path) as db:
        return {
            "queue": int(db.execute(
                "SELECT COUNT(*) FROM s2_handoff_queue_entries WHERE task_id=?", (task_id,),
            ).fetchone()[0]),
            "receipts": int(db.execute(
                "SELECT COUNT(*) FROM s2_handoff_receipts WHERE task_id=?", (task_id,),
            ).fetchone()[0]),
            "handoff_outbox": int(db.execute(
                "SELECT COUNT(*) FROM domain_outbox WHERE task_id=? AND event_kind='S2_HANDOFF_ACCEPTED'",
                (task_id,),
            ).fetchone()[0]),
            "scope_grant_rows": int(db.execute(
                "SELECT COUNT(*) FROM principal_scope_grants WHERE tenant_id='tenant-a' AND principal_id='principal-a'",
            ).fetchone()[0]),
            "scope_policy_write_attempts": int(db.execute(
                "SELECT COUNT(*) FROM ar05_scope_write_audit",
            ).fetchone()[0]),
            "repairs": int(db.execute(
                "SELECT COUNT(*) FROM d3_action_ledgers WHERE task_id=?", (task_id,),
            ).fetchone()[0]),
        }


def _install_scope_write_audit(db_path: Path) -> None:
    with connect(db_path) as db:
        db.execute("CREATE TABLE ar05_scope_write_audit (table_name TEXT, operation TEXT)")
        for table in ("principal_scope_grants", "route_scope_policies"):
            for operation, suffix in (("INSERT", "ins"), ("UPDATE", "upd"), ("DELETE", "del")):
                db.execute(
                    f"CREATE TRIGGER ar05_audit_{table}_{suffix} AFTER {operation} ON {table} "
                    f"BEGIN INSERT INTO ar05_scope_write_audit VALUES ('{table}', '{operation}'); END"
                )


def test_ar05_same_session_assistant_to_s2_handoff_receipt(
    demo_db: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Formal API -> Assistant -> Task Worker -> task-bound MCP -> trusted S2 Queue."""
    import opspilot.investigator as investigator

    reset_fixture(demo_db, "S2_SCOPE_DENIED")
    _install_scope_write_audit(demo_db)
    monkeypatch.setattr(investigator, "ChatOpenAI", _S2InvestigatorFixture)
    monkeypatch.setenv("OPSPILOT_MODEL_API_KEY", "offline-placeholder")
    monkeypatch.setenv("OPSPILOT_MODEL_NAME", "offline-deterministic-model")
    checkpoint_db = tmp_path / "ar05-s2-checkpoint.sqlite3"
    app = create_app(
        db_path=demo_db,
        checkpoint_db_path=checkpoint_db,
        start_worker=False,
        credentials=PASSWORDS,
        expected_origin=ORIGIN,
        assistant_model_factory=_AssistantAnswerModel,
    )

    def dispatch(run_id: str) -> None:
        worker = SingleInstanceWorker(demo_db)
        worker.acquire()
        worker.register()
        try:
            selected = next_worker_run(demo_db)
            assert selected is not None and str(selected["run_id"]) == run_id
            asyncio.run(_dispatch_run(
                demo_db, checkpoint_db, worker.owner_id, "executor-a", selected,
                worker_epoch=worker.epoch, assistant_model_factory=_AssistantAnswerModel,
            ))
        finally:
            worker.release()

    with TestClient(app, raise_server_exceptions=False) as client:
        headers = _login(client)[1]
        session_id = _session(client, headers)

        chat = client.post(
            f"/api/sessions/{session_id}/assistant/messages",
            headers={**headers, "Idempotency-Key": "ar05-s2-original-question"},
            json={"body": QUESTION, "task_id": None},
        )
        assert chat.status_code == 202, chat.text
        origin_message_id = str(chat.json()["message_id"])
        dispatch(str(chat.json()["run_id"]))
        chat_run = client.get(f"/api/runs/{chat.json()['run_id']}").json()
        assert chat_run["execution_core"] == "ASSISTANT_V1"
        chat_only_session = client.get(f"/api/sessions/{session_id}").json()
        assert chat_only_session["tasks"] == []
        with connect(demo_db) as db:
            assert db.execute("SELECT COUNT(*) FROM s2_handoff_queue_entries").fetchone()[0] == 0
            assert db.execute("SELECT COUNT(*) FROM s2_handoff_receipts").fetchone()[0] == 0
            assert db.execute(
                "SELECT COUNT(*) FROM domain_outbox WHERE event_kind='S2_HANDOFF_ACCEPTED'",
            ).fetchone()[0] == 0

        # This POST models the user's explicit "enter controlled investigation" confirmation.
        task_response = client.post(
            f"/api/sessions/{session_id}/tasks",
            headers={**headers, "Idempotency-Key": "ar05-s2-task-confirm"},
            json={
                "initial_message": QUESTION,
                "investigation_kind": "AUTH_INCIDENT",
                "source_message_id": origin_message_id,
            },
        )
        assert task_response.status_code == 202, task_response.text
        created = task_response.json()
        task_id, task_run_id = str(created["task_id"]), str(created["run_id"])
        replay = client.post(
            f"/api/sessions/{session_id}/tasks",
            headers={**headers, "Idempotency-Key": "ar05-s2-task-confirm"},
            json={
                "initial_message": QUESTION,
                "investigation_kind": "AUTH_INCIDENT",
                "source_message_id": origin_message_id,
            },
        )
        assert replay.status_code == 200 and replay.json()["task_id"] == task_id
        dispatch(task_run_id)

        run = client.get(f"/api/runs/{task_run_id}").json()
        assert run["status"] == "SUCCEEDED", run
        assert run["execution_core"] == "PROFESSIONAL_INVESTIGATOR"
        handoff_response = client.get(f"/api/tasks/{task_id}/handoff")
        assert handoff_response.status_code == 200, handoff_response.text
        ready = handoff_response.json()
        assert ready["business_outcome"] == "HANDOFF_READY", ready
        assert ready["currentness"] == "CURRENT"
        assert ready["submitted"] is False
        assert ready.get("scope_authorized") is not True and ready.get("recovered") is not True
        assert ready["diagnosis_receipt"]["run_id"] == task_run_id
        assert ready["draft"]["draft_id"]
        assert _counts(demo_db, task_id) == {
            "queue": 0, "receipts": 0, "handoff_outbox": 0, "scope_grant_rows": 1,
            "scope_policy_write_attempts": 0, "repairs": 0,
        }

        # The caller has inspected the current frozen Draft above; this explicit command
        # is the only action that can submit it to the local review queue.
        draft = ready["draft"]
        operation_id = "ar05-s2-handoff-submit-01"
        submit_body = {
            "operation_id": operation_id,
            "draft_id": draft["draft_id"],
            "draft_digest": draft["content_digest"],
            "expected_control_revision": ready["control_revision"],
            "handoff_kind": "SCOPE_REVIEW",
        }
        submitted = client.post(
            f"/api/tasks/{task_id}/handoff/submit",
            headers={**headers, "Idempotency-Key": operation_id},
            json=submit_body,
        )
        assert submitted.status_code == 202, submitted.text
        accepted = submitted.json()
        assert accepted["business_outcome"] == "SCOPE_ESCALATED"
        assert accepted["handoff_status"] == "PENDING_REVIEW"
        assert accepted["scope_authorized"] is False and accepted["recovered"] is False

        replayed_submit = client.post(
            f"/api/tasks/{task_id}/handoff/submit",
            headers={**headers, "Idempotency-Key": operation_id},
            json=submit_body,
        )
        assert replayed_submit.status_code == 200 and replayed_submit.json()["replayed"] is True
        assert replayed_submit.json()["receipt_id"] == accepted["receipt_id"]
        persisted = client.get(f"/api/tasks/{task_id}/handoff").json()
        assert persisted["business_outcome"] == "SCOPE_ESCALATED"
        assert persisted["handoff_status"] == "PENDING_REVIEW"
        assert persisted["scope_authorized"] is False and persisted["recovered"] is False
        assert persisted["handoff_receipt"]["receipt_id"] == accepted["receipt_id"]

        reentered_session = client.get(f"/api/sessions/{session_id}").json()
        assert any(item["task_id"] == task_id for item in reentered_session["tasks"])
        event_history = client.get(f"/api/sessions/{session_id}/events/history").json()["items"]
        handoff_events = [item for item in event_history if item["event_kind"] == "S2_HANDOFF_ACCEPTED"]
        assert len(handoff_events) == 1
        assert handoff_events[0]["task_id"] == task_id
        assert handoff_events[0]["payload"]["receipt_id"] == accepted["receipt_id"]

        messages = client.get(f"/api/sessions/{session_id}/messages").json()["items"]
        task_message = next(item for item in messages if item["message_id"] == created["message_id"])
        assert task_message["investigation_origin_message_id"] == origin_message_id
        assert task_message["body"] == QUESTION
        assert client.get(f"/api/sessions/{session_id}/messages").json()["items"] == messages

        with connect(demo_db) as db:
            observations = [dict(row) for row in db.execute(
                """SELECT o.tool_name,o.status,o.evidence_id,a.run_id AS attempt_run_id
                   ,e.fact_type,e.facts_json
                   FROM d2_tool_observations o JOIN d2_attempts a ON a.attempt_id=o.attempt_id
                   JOIN d2_evidence e ON e.evidence_id=o.evidence_id AND e.task_id=o.task_id
                   WHERE o.task_id=? ORDER BY o.rowid""",
                (task_id,),
            ).fetchall()]
            grant = db.execute(
                "SELECT granted_scopes_json FROM principal_scope_grants WHERE tenant_id='tenant-a' AND principal_id='principal-a'",
            ).fetchone()[0]
            commands = int(db.execute(
                "SELECT COUNT(*) FROM commands WHERE tenant_id='tenant-a' AND target_ref=? AND command_kind='S2_HANDOFF_SUBMIT'",
                (f"{task_id}:SCOPE_REVIEW",),
            ).fetchone()[0])
        assert [item["tool_name"] for item in observations] == ["probe_endpoint", "get_scope_authz_facts"]
        assert all(item["status"] == "OK" and item["attempt_run_id"] == task_run_id for item in observations)
        facts_by_tool = {item["tool_name"]: json.loads(str(item["facts_json"])) for item in observations}
        assert facts_by_tool["probe_endpoint"]["http_status"] == 403
        assert facts_by_tool["get_scope_authz_facts"]["outcome"] == "DENY"
        assert json.loads(str(grant)) == []
        assert commands == 1

        trace = {
            "evidence_level": "DETERMINISTIC_MODEL_FORMAL_FASTAPI_WORKER_REAL_LOCAL_MCP_HTTP_SQLITE",
            "original_user_question": QUESTION,
            "provider_http_requests": 0,
            "external_business_writes": 0,
            "local_controlled_queue_writes": 1,
            "session_id": session_id,
            "source_message_id": origin_message_id,
            "task_id": task_id,
            "task_initial_message_id": created["message_id"],
            "assistant_run_id": chat_run["run_id"],
            "assistant_execution_core": chat_run["execution_core"],
            "investigation_run_id": task_run_id,
            "investigation_execution_core": run["execution_core"],
            "mcp_observations": observations,
            "same_session_handoff_event": handoff_events[0],
            "handoff_ready": ready,
            "handoff_accepted": accepted,
            "handoff_readback": persisted,
            "counts": _counts(demo_db, task_id),
        }
        print("AR05_S2_HANDOFF_TRACE=" + json.dumps(trace, ensure_ascii=False, default=str), flush=True)
        trace_path = os.environ.get("AR05_S2_HANDOFF_TRACE_PATH")
        if trace_path:
            Path(trace_path).parent.mkdir(parents=True, exist_ok=True)
            Path(trace_path).write_text(json.dumps(trace, ensure_ascii=False, indent=2), encoding="utf-8")
