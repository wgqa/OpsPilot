from __future__ import annotations

import asyncio
import hashlib
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


FROZEN_E11_QUESTION_SHA256 = "721177e0c907421ab13927c9ac10bb23ba5b568c365d4ff58ef33ad2887a39be"
ASSISTANT_ANSWER = (
    "HTTP 403 表示本次请求未获准，但单凭用户描述无法确认具体授权原因。"
    "可以先在可信绑定资源范围内调查；是否提交申请由你明确确认。"
)
_ASSISTANT_MODEL_REQUESTS: list[dict[str, object]] = []


def _frozen_e11_question() -> str:
    cases_path = Path(__file__).resolve().parents[1] / "docs/evidence/r2-ar06-eval-01/CASES.json"
    cases = json.loads(cases_path.read_text(encoding="utf-8"))
    case = next(item for item in cases["cases"] if item["case_id"] == "E11-D")
    turns = case["user_turns"]
    assert len(turns) == 1
    question = str(turns[0])
    assert hashlib.sha256(question.encode("utf-8")).hexdigest() == FROZEN_E11_QUESTION_SHA256
    return question


def _digest_messages(messages: list[object]) -> str:
    material = [
        {
            "type": type(message).__name__,
            "content": getattr(message, "content", None),
            "tool_calls": getattr(message, "tool_calls", None),
        }
        for message in messages
    ]
    raw = json.dumps(material, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _digest_tool_schemas(tools: list[dict[str, Any]]) -> str:
    raw = json.dumps(tools, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


class _AssistantAnswerModel(BaseChatModel):
    @property
    def _llm_type(self) -> str:
        return "AR05_S2_OFFLINE_ASSISTANT_FIXTURE"

    def bind_tools(self, tools, **kwargs):
        # The fixture returns a normal answer, but supports the Assistant's
        # standard tool-binding interface so CHAT_READONLY can complete.
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        visible_messages = [
            {
                "type": type(message).__name__,
                "content": getattr(message, "content", None),
                "tool_calls": getattr(message, "tool_calls", None),
            }
            for message in messages
        ]
        _ASSISTANT_MODEL_REQUESTS.append({
            "model_id": "AR05_S2_OFFLINE_ASSISTANT_FIXTURE",
            "prompt_digest": _digest_messages(messages),
            "message_count": len(messages),
            "visible_messages": visible_messages,
        })
        response = AIMessage(content=ASSISTANT_ANSWER)
        response.usage_metadata = {"input_tokens": 12, "output_tokens": 25, "total_tokens": 37}
        return ChatResult(generations=[ChatGeneration(message=response)])


class _S2InvestigatorFixture:
    """Deterministic model for the formal Investigator path; MCP remains real/local."""

    instances: list["_S2InvestigatorFixture"] = []

    def __init__(self, *args: object, **kwargs: object) -> None:
        self.available_tools: list[dict[str, Any]] = []
        self.seen_tools: list[str] = []
        self.request_digests: list[dict[str, Any]] = []
        self.final_answers: list[str] = []
        self.__class__.instances.append(self)
        self.turn = 0

    def bind_tools(self, tools, **kwargs):
        self.available_tools = list(tools)
        return self

    async def ainvoke(self, messages):
        names = [str(item.get("function", {}).get("name")) for item in self.available_tools]
        human = str(messages[-1].content)
        marker = human.find("\n{")
        context = json.loads(human[marker + 1:]) if marker >= 0 else {}
        current_evidence = context.get("current_mcp_evidence", [])
        probes = [item for item in current_evidence if item.get("fact_type") == "endpoint_probe"]
        authz = [item for item in current_evidence if item.get("fact_type") == "scope_authz_decision"]
        probe_facts = probes[-1].get("facts", {}) if probes else {}
        matching_authz = [
            item for item in authz
            if item.get("facts", {}).get("request_id") == probe_facts.get("request_id")
            and item.get("facts", {}).get("currentness") == "CURRENT"
        ]
        self.request_digests.append({
            "model_id": "AR05_S2_OFFLINE_ASSISTANT_FIXTURE",
            "prompt_digest": _digest_messages(messages),
            "tool_schema_digest": _digest_tool_schemas(self.available_tools),
            "message_count": len(messages),
            "tool_schema_count": len(self.available_tools),
            "tool_schema_names": names,
            "visible_messages": [
                {
                    "type": type(message).__name__,
                    "content": getattr(message, "content", None),
                    "tool_calls": getattr(message, "tool_calls", None),
                }
                for message in messages
            ],
        })
        if matching_authz:
            self.request_digests[-1]["fixture_decision"] = "ANSWER_AFTER_MATCHED_CURRENT_AUTHZ"
            response = AIMessage(content=(
                "同一请求的当前 Authz Observation 显示 DENY / SCOPE_INSUFFICIENT；"
                "可以说明权限不足并准备人工复核草稿，但仍须等待用户明确提交。"
            ))
            self.final_answers.append(str(response.content))
            fixture_usage = {"input_tokens": 80, "output_tokens": 25, "total_tokens": 105}
            self.request_digests[-1]["fixture_usage"] = fixture_usage
            response.usage_metadata = fixture_usage
            return response
        if "probe_endpoint" in names and not probes:
            self.request_digests[-1]["fixture_decision"] = "CALL_PROBE_WITHOUT_CURRENT_OBSERVATION"
            name = "probe_endpoint"
            args: dict[str, object] = {"service_id": "orders-demo", "integration_id": "integration-a"}
        elif "get_scope_authz_facts" in names and probe_facts.get("http_status") == 403:
            self.request_digests[-1]["fixture_decision"] = "CALL_AUTHZ_FOR_CURRENT_403_REQUEST"
            request_id = probe_facts["request_id"]
            name = "get_scope_authz_facts"
            args = {"request_id": request_id}
        else:
            self.request_digests[-1]["fixture_decision"] = "ANSWER_WITHOUT_MORE_TOOL_CALLS"
            response = AIMessage(content=(
                "当前材料不足以确认权限原因；需要在授权绑定范围内取得新的当前证据。"
            ))
            fixture_usage = {"input_tokens": 80, "output_tokens": 20, "total_tokens": 100}
            self.request_digests[-1]["fixture_usage"] = fixture_usage
            response.usage_metadata = fixture_usage
            return response
        self.turn += 1
        self.seen_tools.append(name)
        response = AIMessage(
            content="",
            tool_calls=[{"name": name, "args": args, "id": f"ar05-s2-fixture-{self.turn}"}],
        )
        fixture_usage = {"input_tokens": 100, "output_tokens": 10, "total_tokens": 110}
        self.request_digests[-1]["fixture_usage"] = fixture_usage
        response.usage_metadata = fixture_usage
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


def _scope_policy_snapshot(db_path: Path) -> dict[str, list[dict[str, object]]]:
    with connect(db_path) as db:
        grants = [dict(row) for row in db.execute(
            """SELECT tenant_id,principal_id,granted_scopes_json,grant_version
               FROM principal_scope_grants ORDER BY tenant_id,principal_id""",
        ).fetchall()]
        policies = [dict(row) for row in db.execute(
            """SELECT tenant_id,service_id,route,required_scopes_json,scope_policy_version
               FROM route_scope_policies ORDER BY tenant_id,service_id,route""",
        ).fetchall()]
    return {"grants": grants, "policies": policies}


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

    question = _frozen_e11_question()
    reset_fixture(demo_db, "S2_SCOPE_DENIED")
    _ASSISTANT_MODEL_REQUESTS.clear()
    _S2InvestigatorFixture.instances.clear()
    _install_scope_write_audit(demo_db)
    scope_before = _scope_policy_snapshot(demo_db)
    monkeypatch.setattr(investigator, "ChatOpenAI", _S2InvestigatorFixture)
    monkeypatch.setenv("OPSPILOT_MODEL_API_KEY", "offline-placeholder")
    monkeypatch.setenv("OPSPILOT_MODEL_NAME", "offline-deterministic-model")
    monkeypatch.setenv("OPSPILOT_ASSISTANT_PROVIDER_ENABLED", "1")
    monkeypatch.setenv("OPSPILOT_LEGACY_PROVIDER_ENABLED", "1")
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
            json={"body": question, "task_id": None},
        )
        assert chat.status_code == 202, chat.text
        origin_message_id = str(chat.json()["message_id"])
        dispatch(str(chat.json()["run_id"]))
        chat_run = client.get(f"/api/runs/{chat.json()['run_id']}").json()
        assert chat_run["execution_core"] == "ASSISTANT_V1"
        assert chat_run["status"] == "SUCCEEDED", {
            **chat_run, "blocked_reason": chat_run.get("blocked_reason"),
        }
        assistant_messages = client.get(f"/api/sessions/{session_id}/messages").json()["items"]
        assistant_answers = [
            item for item in assistant_messages
            if item["role"] == "ASSISTANT" and item.get("answer_run_id") == chat_run["run_id"]
        ]
        assert len(assistant_answers) == 1, assistant_messages
        assistant_answer = assistant_answers[0]
        assert assistant_answer["body"] == ASSISTANT_ANSWER
        assert assistant_answer["answer_source_message_id"] == origin_message_id
        assert assistant_answer["answer_kind"] == "CHAT_MODEL"
        with connect(demo_db) as db:
            assistant_answer_row = db.execute(
                """SELECT a.run_id,a.message_id,a.body_digest,r.source_message_id,ca.status,ca.error_class,
                          ca.input_tokens,ca.output_tokens,ca.total_tokens
                   FROM chat_run_answers a JOIN task_runs r ON r.run_id=a.run_id
                   JOIN chat_attempts ca ON ca.attempt_id=a.attempt_id
                   WHERE a.run_id=?""",
                (chat_run["run_id"],),
            ).fetchone()
        assert assistant_answer_row is not None
        assert str(assistant_answer_row["source_message_id"]) == origin_message_id
        assert str(assistant_answer_row["message_id"]) == assistant_answer["message_id"]
        assert str(assistant_answer_row["status"]) == "SUCCEEDED"
        assert assistant_answer_row["error_class"] is None
        assert str(assistant_answer_row["body_digest"]) == hashlib.sha256(
            ASSISTANT_ANSWER.encode("utf-8"),
        ).hexdigest()
        assert len(_ASSISTANT_MODEL_REQUESTS) == 1
        assert any(
            question in str(message.get("content"))
            for request in _ASSISTANT_MODEL_REQUESTS
            for message in request["visible_messages"]
        )
        chat_only_session = client.get(f"/api/sessions/{session_id}").json()
        assert chat_only_session["tasks"] == []
        with connect(demo_db) as db:
            assert db.execute("SELECT COUNT(*) FROM s2_handoff_queue_entries").fetchone()[0] == 0
            assert db.execute("SELECT COUNT(*) FROM s2_handoff_receipts").fetchone()[0] == 0
            assert db.execute(
                "SELECT COUNT(*) FROM domain_outbox WHERE event_kind='S2_HANDOFF_ACCEPTED'",
            ).fetchone()[0] == 0
            assert db.execute("SELECT COUNT(*) FROM ar05_scope_write_audit").fetchone()[0] == 0
        assert _scope_policy_snapshot(demo_db) == scope_before

        # This POST models the user's explicit "enter controlled investigation" confirmation.
        task_response = client.post(
            f"/api/sessions/{session_id}/tasks",
            headers={**headers, "Idempotency-Key": "ar05-s2-task-confirm"},
            json={
                "initial_message": question,
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
                "initial_message": question,
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
        before_submit_counts = _counts(demo_db, task_id)
        assert before_submit_counts == {
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
        assert persisted["handoff_receipt"]["draft_id"] == draft["draft_id"]
        assert persisted["handoff_receipt"]["draft_digest"] == draft["content_digest"]
        assert persisted["handoff_receipt"]["operation_id"] == operation_id
        assert _counts(demo_db, task_id) == {
            "queue": 1, "receipts": 1, "handoff_outbox": 1, "scope_grant_rows": 1,
            "scope_policy_write_attempts": 0, "repairs": 0,
        }
        assert _scope_policy_snapshot(demo_db) == scope_before

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
        assert task_message["body"] == question
        assert client.get(f"/api/sessions/{session_id}/messages").json()["items"] == messages

        with connect(demo_db) as db:
            observations = [dict(row) for row in db.execute(
                """SELECT o.tool_name,o.status,o.evidence_id,a.run_id AS attempt_run_id
                   ,e.fact_type,e.facts_json,e.digest AS evidence_digest
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
            task_binding = dict(db.execute(
                """SELECT tenant_id,actor_id,service_id,integration_id,principal_id,status
                   FROM task_bindings WHERE task_id=?""",
                (task_id,),
            ).fetchone())
            outbox_rows = [dict(row) for row in db.execute(
                """SELECT event_id,tenant_id,task_id,session_id,source_kind,source_id,event_kind,payload_json
                   FROM domain_outbox WHERE task_id=? AND event_kind='S2_HANDOFF_ACCEPTED'""",
                (task_id,),
            ).fetchall()]
        assert [item["tool_name"] for item in observations] == ["probe_endpoint", "get_scope_authz_facts"]
        assert all(item["status"] == "OK" and item["attempt_run_id"] == task_run_id for item in observations)
        facts_by_tool = {item["tool_name"]: json.loads(str(item["facts_json"])) for item in observations}
        assert facts_by_tool["probe_endpoint"]["http_status"] == 403
        assert facts_by_tool["get_scope_authz_facts"]["outcome"] == "DENY"
        assert facts_by_tool["probe_endpoint"]["request_id"] == facts_by_tool["get_scope_authz_facts"]["request_id"]
        assert facts_by_tool["get_scope_authz_facts"]["reason_code"] == "SCOPE_INSUFFICIENT"
        assert facts_by_tool["get_scope_authz_facts"]["currentness"] == "CURRENT"
        assert task_binding == {
            "tenant_id": "tenant-a", "actor_id": "support-a", "service_id": "orders-demo",
            "integration_id": "integration-a", "principal_id": "principal-a", "status": "COMPLETED",
        }
        receipt = ready["diagnosis_receipt"]
        assert receipt["request_id"] == facts_by_tool["probe_endpoint"]["request_id"]
        assert receipt["run_id"] == task_run_id
        assert receipt["decision_id"] == facts_by_tool["get_scope_authz_facts"]["decision_id"]
        assert receipt["outcome"] == "DIAGNOSED"
        assert set(receipt["evidence_ids"]) == {str(item["evidence_id"]) for item in observations}
        assert receipt["evidence_digests"] == {
            str(item["evidence_id"]): str(item["evidence_digest"]) for item in observations
        }
        assert ready["draft"]["version"] == 1
        assert len(str(ready["draft"]["content_digest"])) == 64
        assert ready["draft"]["content"]["authorization_changed"] is False
        assert json.loads(str(grant)) == []
        assert commands == 1
        assert len(outbox_rows) == 1
        assert outbox_rows[0]["tenant_id"] == "tenant-a"
        assert outbox_rows[0]["task_id"] == task_id
        assert outbox_rows[0]["event_kind"] == "S2_HANDOFF_ACCEPTED"
        assert json.loads(str(outbox_rows[0]["payload_json"]))["receipt_id"] == accepted["receipt_id"]
        assert _scope_policy_snapshot(demo_db) == scope_before

        investigator_call_digests = [
            item for model in _S2InvestigatorFixture.instances for item in model.request_digests
        ]
        fixture_usage_records = [
            {
                "input_tokens": int(assistant_answer_row["input_tokens"]),
                "output_tokens": int(assistant_answer_row["output_tokens"]),
                "total_tokens": int(assistant_answer_row["total_tokens"]),
            },
            *[dict(item["fixture_usage"]) for item in investigator_call_digests],
        ]
        fixture_usage_summary = {
            key: sum(int(item[key]) for item in fixture_usage_records)
            for key in ("input_tokens", "output_tokens", "total_tokens")
        }
        trace = {
            "evidence_level": "DETERMINISTIC_MODEL_FORMAL_FASTAPI_WORKER_REAL_LOCAL_MCP_HTTP_SQLITE",
            "case_id": "E11-D",
            "original_user_question": question,
            "original_user_question_sha256": hashlib.sha256(question.encode("utf-8")).hexdigest(),
            "provider_http_requests": 0,
            "fixture_model_invocations": len(_ASSISTANT_MODEL_REQUESTS) + sum(
                len(model.request_digests) for model in _S2InvestigatorFixture.instances
            ),
            "external_business_writes": 0,
            "local_controlled_queue_writes": 1,
            "session_id": session_id,
            "source_message_id": origin_message_id,
            "task_id": task_id,
            "task_binding": task_binding,
            "task_initial_message_id": created["message_id"],
            "assistant_run_id": chat_run["run_id"],
            "assistant_run_status": chat_run["status"],
            "assistant_execution_core": chat_run["execution_core"],
            "assistant_answer": {
                "message_id": assistant_answer["message_id"],
                "body": assistant_answer["body"],
                "answer_kind": assistant_answer["answer_kind"],
                "source_message_id": assistant_answer["answer_source_message_id"],
                "run_id": assistant_answer["answer_run_id"],
                "persisted_body_digest": str(assistant_answer_row["body_digest"]),
                "fixture_usage": {
                    "input_tokens": assistant_answer_row["input_tokens"],
                    "output_tokens": assistant_answer_row["output_tokens"],
                    "total_tokens": assistant_answer_row["total_tokens"],
                },
            },
            "fixture_usage_records": fixture_usage_records,
            "fixture_usage_summary": fixture_usage_summary,
            "assistant_model_requests": _ASSISTANT_MODEL_REQUESTS,
            "ordinary_chat_created_no_task_or_handoff": True,
            "investigation_run_id": task_run_id,
            "investigation_run_status": run["status"],
            "investigation_execution_core": run["execution_core"],
            "mcp_observations": observations,
            "diagnosis_receipt": receipt,
            "pre_submit_counts": before_submit_counts,
            "final_counts": _counts(demo_db, task_id),
            "scope_policy_snapshot_before": scope_before,
            "scope_policy_snapshot_after": _scope_policy_snapshot(demo_db),
            "investigator_call_digests": investigator_call_digests,
            "investigator_tool_choices": [
                tool for model in _S2InvestigatorFixture.instances for tool in model.seen_tools
            ],
            "investigator_final_answers": [
                answer for model in _S2InvestigatorFixture.instances for answer in model.final_answers
            ],
            "same_session_handoff_event": handoff_events[0],
            "handoff_ready": ready,
            "handoff_accepted": accepted,
            "handoff_readback": persisted,
            "handoff_outbox_rows": outbox_rows,
            "explicit_submit_operation_id": operation_id,
        }
        print("AR05_S2_HANDOFF_TRACE=" + json.dumps(trace, ensure_ascii=False, default=str), flush=True)
        trace_path = os.environ.get("AR05_S2_HANDOFF_TRACE_PATH")
        if trace_path:
            Path(trace_path).parent.mkdir(parents=True, exist_ok=True)
            Path(trace_path).write_text(json.dumps(trace, ensure_ascii=False, indent=2), encoding="utf-8")
