"""AR-03-03: Protocol version comparison integrated into real Agent investigation.

Formal API -> Worker -> Assistant -> MCP (compare_scoped_protocols) -> Session Answer.
Verifies end-to-end execution, provenance linking, unauthorized document refusal,
cross-session result rejection, and tamper-evident digest checking.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import time
from typing import Any

import pytest
from fastapi.testclient import TestClient
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import Field

from opspilot.domain.database import connect
from opspilot.domain.assistant import state as assistant_state, sources_current
from opspilot.domain.scoped_protocol_comparison import (
    compare_scoped_protocols,
    scoped_comparison_is_current,
)
from opspilot.domain.task_control import TrustedIdentity, create_session
from opspilot.web.app import create_app
from test_ar02_assistant import ORIGIN, PASSWORDS


def _wait_run(client: TestClient, run_id: str, timeout: float = 20.0) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        response = client.get(f"/api/runs/{run_id}")
        assert response.status_code == 200, response.text
        run = response.json()
        if run["status"] in {"SUCCEEDED", "FAILED", "BLOCKED"}:
            return run
        time.sleep(0.05)
    raise TimeoutError(f"Run {run_id} did not finish within {timeout}s")


class ProtocolCompareSurrogateModel(BaseChatModel):
    """Deterministic surrogate model simulating agent autonomy for protocol investigation."""

    mode: str = "compare_journey"
    seen_messages: list = Field(default_factory=list)
    decisions: list = Field(default_factory=list)
    offered_tool_names: list = Field(default_factory=list)

    @property
    def _llm_type(self) -> str:
        return "AR03_03_PROTOCOL_COMPARE_SURROGATE"

    def bind_tools(self, tools, **kwargs):
        self.offered_tool_names = [tool.name for tool in tools]
        return self

    @staticmethod
    def _tool_payload(message: ToolMessage) -> dict[str, Any]:
        payload = json.loads(message.content)
        if isinstance(payload, dict) and set(payload) == {"result"}:
            payload = payload["result"]
        return payload

    def _generate(self, messages, stop=None, run_manager=None, **kwargs) -> ChatResult:
        self.seen_messages.append(messages)
        tool_messages = [m for m in messages if isinstance(m, ToolMessage)]
        tool_payloads = [self._tool_payload(m) for m in tool_messages]

        if self.mode == "compare_journey":
            if not tool_messages:
                # Turn 1: decide to invoke compare_scoped_protocols tool
                self.decisions.append({
                    "action": "CALL_TOOL",
                    "tool": "compare_scoped_protocols",
                    "args": {
                        "base_document_id": "callback-retry-contract",
                        "target_document_id": "callback-retry-contract-v2",
                    },
                })
                message = AIMessage(
                    content="",
                    tool_calls=[{
                        "name": "compare_scoped_protocols",
                        "args": {
                            "base_document_id": "callback-retry-contract",
                            "target_document_id": "callback-retry-contract-v2",
                        },
                        "id": f"call-compare-{len(tool_messages)}",
                    }],
                )
            else:
                # Turn 2: inspect tool observation and produce grounded investigation answer
                self.decisions.append({"action": "ANSWER"})
                obs = tool_payloads[-1]
                diff_count = obs.get("diff_count", 0)
                diffs = obs.get("differences", [])
                unconfirmed = obs.get("unconfirmed_aspects", [])
                verified = obs.get("deployment_version_verified", True)

                # Format grounded answer with difference analysis, impact, and explicit epistemic bounds
                base_doc = obs.get('base_document_id') or obs.get('base_ref', {}).get('document_id')
                target_doc = obs.get('target_document_id') or obs.get('target_ref', {}).get('document_id')
                summary_lines = [
                    f"经比对授权规范 {base_doc} 与 {target_doc}，发现 {diff_count} 项差异：",
                ]
                for d in diffs:
                    summary_lines.append(f"- [{d.get('category')}] {d.get('description')}")
                summary_lines.append(
                    "潜在影响：回调失败重试行为由固定延迟升级为错误分类退避策略，max_attempts 与 attempt_count 参数要求发生变化。"
                )
                summary_lines.append(
                    f"未确定事项：静态协议比对不证明线上集群真实部署状态（deployment_version_verified={verified}）。"
                    "线上环境是否已生效该规范，需结合具体订单和运行环境确认。"
                )
                content = "\n".join(summary_lines)
                message = AIMessage(content=content)

        elif self.mode == "unauthorized_compare":
            if not tool_messages:
                self.decisions.append({
                    "action": "CALL_TOOL",
                    "tool": "compare_scoped_protocols",
                    "args": {
                        "base_document_id": "unauthorized-secret-spec",
                        "target_document_id": "callback-retry-contract-v2",
                    },
                })
                message = AIMessage(
                    content="",
                    tool_calls=[{
                        "name": "compare_scoped_protocols",
                        "args": {
                            "base_document_id": "unauthorized-secret-spec",
                            "target_document_id": "callback-retry-contract-v2",
                        },
                        "id": "call-unauthorized-0",
                    }],
                )
            else:
                self.decisions.append({"action": "ANSWER"})
                obs = tool_payloads[-1]
                error_msg = obs.get("error", "DOCUMENT_NOT_AUTHORIZED")
                content = f"无法对比请求的规范：{error_msg}。该文档未在当前会话授权的项目范围内，系统拒绝越权读取。"
                message = AIMessage(content=content)

        else:
            self.decisions.append({"action": "ANSWER"})
            message = AIMessage(content="简单协议咨询直接解答，零工具调用。")

        message.usage_metadata = {"input_tokens": 12, "output_tokens": 8, "total_tokens": 20}
        return ChatResult(generations=[ChatGeneration(message=message)])


def test_formal_api_worker_mcp_protocol_compare_journey(demo_db, tmp_path):
    """End-to-end journey: Formal API -> Worker -> Assistant -> MCP -> Scoped Protocol Compare -> Session Answer."""
    surrogate = ProtocolCompareSurrogateModel(mode="compare_journey")
    app = create_app(
        db_path=demo_db,
        checkpoint_db_path=tmp_path / "ar03-03-checkpoint.sqlite3",
        start_worker=True,
        credentials=PASSWORDS,
        expected_origin=ORIGIN,
        assistant_model_factory=lambda: surrogate,
    )

    with TestClient(app) as client:
        # 1. Login as authorized support-a
        login = client.post(
            "/api/auth/login",
            headers={"Origin": ORIGIN},
            json={"actor_id": "support-a", "password": PASSWORDS["support-a"]},
        )
        assert login.status_code == 200, login.text
        headers = {"Origin": ORIGIN, "X-CSRF-Token": login.json()["csrf_token"]}

        # 2. Create session (bound to orders-callback by default)
        session_res = client.post("/api/sessions", headers=headers)
        assert session_res.status_code in (200, 201), session_res.text
        session_id = session_res.json()["session_id"]

        # 3. Submit formal user question asking about protocol upgrade differences
        user_prompt = (
            "客户反馈升级回调协议后行为发生了变化。请检查旧版和新版回调重试规范，"
            "告诉我有哪些差异、可能影响什么，以及目前还不能确定什么。"
        )
        post_res = client.post(
            f"/api/sessions/{session_id}/assistant/messages",
            headers={**headers, "Idempotency-Key": "ar03-03-user-journey-turn-1"},
            json={"body": user_prompt},
        )
        assert post_res.status_code == 202, post_res.text
        accepted = post_res.json()
        run_id = accepted["run_id"]

        # 4. Await asynchronous worker completion
        completed_run = _wait_run(client, run_id)
        assert completed_run["status"] == "SUCCEEDED"

        # 5. Verify session message response
        messages_res = client.get(f"/api/sessions/{session_id}/messages", headers=headers)
        assert messages_res.status_code == 200
        messages = messages_res.json()["items"]
        assistant_msg = next((m for m in messages if m["role"] == "ASSISTANT"), None)
        assert assistant_msg is not None, "Assistant response not found in session messages"
        body = assistant_msg["body"]

        # 6. Verify grounded content, impact, and epistemic bounds
        assert "callback-retry-contract" in body
        assert "差异" in body
        assert "潜在影响" in body
        assert "未确定事项" in body or "不能确定" in body
        assert "deployment_version_verified=False" in body or "不证明线上" in body

        # 7. Verify SQLite DB records
        with connect(demo_db) as conn:
            # Check MCP call was recorded in assistant_calls
            calls = conn.execute(
                "SELECT * FROM assistant_calls WHERE run_id=? AND kind='MCP'", (run_id,)
            ).fetchall()
            assert len(calls) == 1, f"Expected 1 MCP call, got {len(calls)}"
            call_row = dict(calls[0])
            assert call_row["status"] == "OK"
            call_result = json.loads(call_row["result_json"])
            assert call_result["success"] is True
            assert call_result["base_document_id"] == "callback-retry-contract"
            assert call_result["target_document_id"] == "callback-retry-contract-v2"
            assert call_result["diff_count"] > 0
            assert call_result["deployment_version_verified"] is False
            assert "comparison_digest" in call_result

            # Check sources_current validates the persisted call
            is_valid, reason = sources_current(conn, run_id)
            assert is_valid is True, f"sources_current failed: {reason}"
            assert reason is None

        # 8. Capture trace for evidence artifact
        trace_path = Path("docs/evidence/ar-03/agent-integration/dialog_trace.json")
        trace_path.parent.mkdir(parents=True, exist_ok=True)
        trace_data = {
            "session_id": session_id,
            "run_id": run_id,
            "user_prompt": user_prompt,
            "assistant_response": body,
            "mcp_call": call_result,
            "surrogate_decisions": surrogate.decisions,
            "sources_current_verified": is_valid,
        }
        trace_path.write_text(json.dumps(trace_data, ensure_ascii=False, indent=2), encoding="utf-8")


def test_unauthorized_document_compare_fails_closed_without_leakage(demo_db, tmp_path):
    """Verify that an unauthorized document comparison attempt is refused cleanly without leaking content."""
    surrogate = ProtocolCompareSurrogateModel(mode="unauthorized_compare")
    app = create_app(
        db_path=demo_db,
        checkpoint_db_path=tmp_path / "ar03-03-unauthorized-cp.sqlite3",
        start_worker=True,
        credentials=PASSWORDS,
        expected_origin=ORIGIN,
        assistant_model_factory=lambda: surrogate,
    )

    with TestClient(app) as client:
        login = client.post(
            "/api/auth/login",
            headers={"Origin": ORIGIN},
            json={"actor_id": "support-a", "password": PASSWORDS["support-a"]},
        )
        headers = {"Origin": ORIGIN, "X-CSRF-Token": login.json()["csrf_token"]}
        session_id = client.post("/api/sessions", headers=headers).json()["session_id"]

        post_res = client.post(
            f"/api/sessions/{session_id}/assistant/messages",
            headers={**headers, "Idempotency-Key": "ar03-03-unauth-turn"},
            json={"body": "请比对未授权保密协议与当前回调规范。"},
        )
        assert post_res.status_code == 202
        run_id = post_res.json()["run_id"]
        completed = _wait_run(client, run_id)
        assert completed["status"] == "SUCCEEDED"

        messages = client.get(f"/api/sessions/{session_id}/messages", headers=headers).json()["items"]
        assistant_msg = next(m for m in messages if m["role"] == "ASSISTANT")
        assert "拒绝越权读取" in assistant_msg["body"] or "DOCUMENT_NOT_AUTHORIZED" in assistant_msg["body"]

        with connect(demo_db) as conn:
            calls = conn.execute(
                "SELECT * FROM assistant_calls WHERE run_id=? AND kind='MCP'", (run_id,)
            ).fetchall()
            assert len(calls) == 1
            call_res = json.loads(calls[0]["result_json"])
            assert call_res["success"] is False
            assert call_res["authority"] == "TOOL_REFUSAL_NOT_FACT"
            assert "DOCUMENT_NOT_AUTHORIZED" in call_res["error"]

            # sources_current remains safe and valid on refusal
            is_valid, reason = sources_current(conn, run_id)
            assert is_valid is True, f"Expected valid sources for refusal, got {reason}"


def test_cross_session_and_cross_tenant_old_result_rejection(demo_db):
    """Revalidation fails closed if a comparison result is presented across sessions, tenants, or actors."""
    identity_a = TrustedIdentity(tenant_id="tenant-a", actor_id="support-a", role="SUPPORT")
    identity_b = TrustedIdentity(tenant_id="tenant-b", actor_id="support-b", role="SUPPORT")
    identity_approver = TrustedIdentity(tenant_id="tenant-a", actor_id="approver-a", role="APPROVER")

    session_01 = create_session(demo_db, identity_a)["session_id"]
    session_02 = create_session(demo_db, identity_a)["session_id"]
    session_03 = create_session(demo_db, identity_b)["session_id"]

    with connect(demo_db) as conn:
        # Execute legitimate comparison in session-01
        res = compare_scoped_protocols(
            conn,
            identity_a,
            session_01,
            "callback-retry-contract",
            "callback-retry-contract-v2",
        )
        assert res.session_id == session_01

        # 1. Revalidating in original session-01 succeeds
        valid, reason = scoped_comparison_is_current(conn, identity_a, session_01, res)
        assert valid is True
        assert reason is None

        # 2. Revalidating in session-02 (cross-session) fails closed
        valid_s2, reason_s2 = scoped_comparison_is_current(conn, identity_a, session_02, res)
        assert valid_s2 is False
        assert reason_s2 == "CROSS_SESSION_COMPARISON_REJECTED"

        # 3. Revalidating in session-03 with tenant-b identity fails closed
        valid_tb, reason_tb = scoped_comparison_is_current(conn, identity_b, session_03, res)
        assert valid_tb is False
        assert reason_tb in {"CROSS_SESSION_COMPARISON_REJECTED", "CROSS_TENANT_COMPARISON_REJECTED"}

        # 4. Revalidating with different actor in same session fails closed
        valid_act, reason_act = scoped_comparison_is_current(conn, identity_approver, session_01, res)
        assert valid_act is False
        assert reason_act == "ACTOR_MISMATCH"


def test_tampered_model_modified_comparison_result_rejection(demo_db):
    """Revalidation detects tampered or forged comparison result dicts via cryptographic digest check."""
    identity = TrustedIdentity(tenant_id="tenant-a", actor_id="support-a", role="SUPPORT")
    session_tamper = create_session(demo_db, identity)["session_id"]
    with connect(demo_db) as conn:
        res = compare_scoped_protocols(
            conn,
            identity,
            session_tamper,
            "callback-retry-contract",
            "callback-retry-contract-v2",
        )
        clean_dict = res.to_dict()

        # Clean dict revalidates
        assert scoped_comparison_is_current(conn, identity, session_tamper, clean_dict) == (True, None)

        # 1. Tamper identical flag from False to True
        tampered_identical = dict(clean_dict)
        tampered_identical["identical"] = True
        is_valid, reason = scoped_comparison_is_current(conn, identity, session_tamper, tampered_identical)
        assert is_valid is False
        assert reason == "COMPARISON_DIGEST_MISMATCH"

        # 2. Tamper differences list (delete items)
        tampered_diffs = dict(clean_dict)
        tampered_diffs["differences"] = []
        is_valid, reason = scoped_comparison_is_current(conn, identity, session_tamper, tampered_diffs)
        assert is_valid is False
        assert reason == "COMPARISON_DIGEST_MISMATCH"

        # 3. Tamper diff_count
        tampered_count = dict(clean_dict)
        tampered_count["diff_count"] = 0
        is_valid, reason = scoped_comparison_is_current(conn, identity, session_tamper, tampered_count)
        assert is_valid is False
        assert reason == "COMPARISON_DIGEST_MISMATCH"


def test_direct_mcp_client_tool_enumeration_and_call(demo_db, tmp_path):
    """Verify that assistant_mcp exposes compare_scoped_protocols via stdio with correct schema and execution."""
    import asyncio
    import sys
    from mcp import Client, StdioServerParameters
    from opspilot.config import ROOT

    identity = TrustedIdentity(tenant_id="tenant-a", actor_id="support-a", role="SUPPORT")
    session_mcp = create_session(demo_db, identity)["session_id"]
    run_id = "test-mcp-direct-run"
    with connect(demo_db) as conn:
        conn.execute(
            "INSERT INTO task_runs (run_id, tenant_id, session_id, command_id, kind, status, created_at) "
            "VALUES (?, 'tenant-a', ?, 'cmd-direct-mcp', 'CHAT_READONLY', 'RUNNING', '2026-11-01T00:00:00Z')",
            (run_id, session_mcp),
        )
        conn.execute(
            "INSERT INTO assistant_runs (run_id, core, delivery_attempt_id, created_at) VALUES (?, 'ASSISTANT_V1', NULL, '2026-11-01T00:00:00Z')",
            (run_id,),
        )
        conn.commit()

    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "opspilot.assistant_mcp", "--db", str(demo_db), "--run-id", run_id],
        cwd=str(ROOT),
        env={k: v for k, v in os.environ.items() if k not in {"OPSPILOT_MODEL_API_KEY", "OPENAI_API_KEY"}},
    )

    async def _invoke():
        async with Client(params) as client:
            listed = await client.list_tools()
            tool_names = [t.name for t in listed.tools]
            assert "compare_scoped_protocols" in tool_names
            assert "search_project_knowledge" in tool_names

            # Verify tool input schema
            compare_tool = next(t for t in listed.tools if t.name == "compare_scoped_protocols")
            props = compare_tool.input_schema.get("properties", {})
            assert "base_document_id" in props
            assert "target_document_id" in props
            assert "base_version" in props
            assert "target_version" in props

            # Call the tool through stdio MCP
            res = await client.call_tool(
                "compare_scoped_protocols",
                {
                    "base_document_id": "callback-retry-contract",
                    "target_document_id": "callback-retry-contract-v2",
                },
            )
            assert res.is_error is False
            content_text = "\n".join(b.text for b in res.content if hasattr(b, "text"))
            data = json.loads(content_text)
            assert data["success"] is True
            assert data["base_document_id"] == "callback-retry-contract"
            assert data["target_document_id"] == "callback-retry-contract-v2"
            assert data["deployment_version_verified"] is False
            assert len(data["differences"]) > 0

    asyncio.run(_invoke())
