"""AR-03-04: Protocol upgrade impact investigation business closed loop.

Validates:
1. Natural language query -> discovers authorized versions -> compares changes -> grounded conclusion.
2. Journey A (unbound order):
   - Discovers authorized protocols without prior internal document IDs.
   - Compares retry protocol v1 vs v2.
   - Explicitly notes customer order/receiver status is unknown without bound order.
   - Recommends binding order via authenticated user action.
3. Journey B (bound order):
   - Under identical user prompt, Receiver QUEUED vs PROCESSED yields distinct factual conclusions.
   - Distinguishes HTTP 202 transport acknowledgement from downstream business processing completion.
   - Technical support hand-off notes formatted (known facts, potential impact, conclusion, verify items, next steps).
   - Zero repair/write actions performed.
4. Security & Epistemic Boundaries:
   - Unauthorized documents cannot be discovered or compared.
   - Continuous revalidation via sources_current for discovery and comparison.
   - Cross-session discovery result revalidation rejection.
"""
from __future__ import annotations

from collections import deque
import json
import os
from pathlib import Path
import sqlite3
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
    list_scoped_protocols,
    scoped_comparison_is_current,
    scoped_discovery_is_current,
)
from opspilot.domain.s3 import prepare_s3_fixture
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


class UpgradeInvestigationSurrogateModel(BaseChatModel):
    """Deterministic surrogate simulating agent autonomy across upgrade investigation journeys."""

    mode: str = "journey_a"
    seen_messages: list = Field(default_factory=list)
    decisions: list = Field(default_factory=list)
    offered_tool_names: list = Field(default_factory=list)

    @property
    def _llm_type(self) -> str:
        return "AR03_04_UPGRADE_INVESTIGATION_SURROGATE"

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

        if self.mode == "journey_a":
            # Journey A: Unbound order.
            # Turn 1: Discover protocol documents matching topic 'retry'
            if len(tool_messages) == 0:
                self.decisions.append({
                    "action": "CALL_TOOL",
                    "tool": "list_scoped_protocol_documents",
                    "args": {"topic": "retry"},
                })
                message = AIMessage(
                    content="",
                    tool_calls=[{
                        "name": "list_scoped_protocol_documents",
                        "args": {"topic": "retry"},
                        "id": "call-disc-0",
                    }],
                )
            # Turn 2: Inspect discovered protocols and compare the two versions
            elif len(tool_messages) == 1:
                discovery_obs = tool_payloads[0]
                protocols = discovery_obs.get("protocols", [])
                retry_family = next((p for p in protocols if "retry" in p.get("family", "")), None)
                if retry_family and len(retry_family.get("document_ids", [])) >= 2:
                    doc_ids = retry_family["document_ids"]
                    base_id = doc_ids[0]
                    target_id = doc_ids[1]
                else:
                    # fallback to protocol_documents
                    doc_ids = [d["document_id"] for d in discovery_obs.get("protocol_documents", [])]
                    base_id = doc_ids[0] if doc_ids else "callback-retry-contract"
                    target_id = doc_ids[1] if len(doc_ids) > 1 else "callback-retry-contract-v2"

                self.decisions.append({
                    "action": "CALL_TOOL",
                    "tool": "compare_scoped_protocols",
                    "args": {
                        "base_document_id": base_id,
                        "target_document_id": target_id,
                    },
                })
                message = AIMessage(
                    content="",
                    tool_calls=[{
                        "name": "compare_scoped_protocols",
                        "args": {
                            "base_document_id": base_id,
                            "target_document_id": target_id,
                        },
                        "id": "call-comp-1",
                    }],
                )
            # Turn 3: Synthesize diff analysis and explicitly address unbound customer order
            else:
                self.decisions.append({"action": "ANSWER"})
                diff_obs = tool_payloads[-1]
                diff_count = diff_obs.get("diff_count", 0)
                diffs = diff_obs.get("differences", [])
                base_id = diff_obs.get("base_document_id") or "callback-retry-contract"
                target_id = diff_obs.get("target_document_id") or "callback-retry-contract-v2"

                lines = [
                    f"通过授权资料发现并比对了规范 {base_id} 与 {target_id}（共发现 {diff_count} 项差异）：",
                ]
                for d in diffs:
                    lines.append(f"- [{d.get('category')}] {d.get('description')}")
                lines.append(
                    "潜在影响：回调失败重试行为从固定间隔重试升级为错误分类退避策略，新增了 attempt_count 和 max_attempts 参数校验要求。"
                )
                lines.append(
                    "客户处理状态核实：当前会话尚未绑定具体订单或资源（未建立 TaskBinding），无法核查该客户订单的当前回调或接收端实际处理状态。"
                )
                lines.append(
                    "建议操作：请在系统中通过可信订单选择操作绑定待核查的订单（如 ar02-order），绑定后再行核查实时处理状态。"
                )
                lines.append(
                    "说明：静态协议比较仅作为规范分析证据，不证明线上集群已生效该部署版本（deployment_version_verified=False）。"
                )
                content = "\n".join(lines)
                message = AIMessage(content=content)

        elif self.mode == "journey_b":
            # Journey B: Bound order investigation.
            # Check last user message to distinguish initial binding from follow-up investigation
            last_human = next((m for m in reversed(messages) if isinstance(m, HumanMessage)), None)
            human_text = last_human.content if last_human else ""

            if "绑定" in human_text and "结合" not in human_text:
                # Initial binding run confirmation
                self.decisions.append({"action": "CONFIRM_BINDING"})
                message = AIMessage(content="已成功关联订单 ar02-order，可结合该订单当前事实与协议开展调查。")
            elif len(tool_messages) == 0:
                # Turn 1 of investigation: Query live delivery and receiver processing state
                self.decisions.append({
                    "action": "CALL_TOOLS",
                    "tools": ["get_callback_delivery", "get_receiver_processing"],
                })
                message = AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "get_callback_delivery",
                            "args": {"reason": "核查绑定订单的回调投递与传输响应事实"},
                            "id": "call-s3-deliv-0",
                        },
                        {
                            "name": "get_receiver_processing",
                            "args": {"reason": "核查绑定订单的接收队列处理事实"},
                            "id": "call-s3-recv-1",
                        },
                    ],
                )
            else:
                # Turn 2 of investigation: Synthesize structured support hand-off notes
                self.decisions.append({"action": "ANSWER"})
                by_tool = {}
                ids = {m.tool_call_id for m in tool_messages}
                for prior in messages:
                    if isinstance(prior, AIMessage) and getattr(prior, "tool_calls", None):
                        for call in prior.tool_calls:
                            if call.get("id") in ids:
                                matched = next((m for m in tool_messages if m.tool_call_id == call.get("id")), None)
                                if matched:
                                    payload = self._tool_payload(matched)
                                    facts = payload.get("facts", {}) if isinstance(payload, dict) else {}
                                    by_tool[call.get("name")] = facts

                deliv = by_tool.get("get_callback_delivery", {})
                recv = by_tool.get("get_receiver_processing", {})

                http_status = deliv.get("receiver_http_status")
                event_id = deliv.get("event_id") or recv.get("event_id", "unknown-event")
                receiver_status = recv.get("status", "UNKNOWN")

                lines = ["【技术支持交接说明草稿】"]
                lines.append(f"1. 真实已知事实：Event {event_id} 投递响应 HTTP {http_status}；接收端状态为 {receiver_status}。")

                if receiver_status == "QUEUED":
                    lines.append(
                        "2. 升级潜在影响：根据升级后的回调规范，HTTP 202 仅代表传输受理并进入接收队列，不代表下游业务处理完成；且退避策略下不应重复触发投递。"
                    )
                    lines.append(
                        "3. 当前业务结论：客户订单【尚未处理完成】（当前在队列排队中，非成功终态）。"
                    )
                    lines.append(
                        "4. 待验证事项：关注接收端在 SLA 内是否能正常出队并流转至 PROCESSED。"
                    )
                    lines.append(
                        "5. 下一步建议：一线支持请耐心等待排队消费，切勿重复重试回调；若超过 SLA 仍为 QUEUED，向下游接收服务团队报障。"
                    )
                elif receiver_status == "PROCESSED":
                    lines.append(
                        "2. 升级潜在影响：升级后的回调规范正常执行，接收端已按预期完成排队与业务消费。"
                    )
                    lines.append(
                        "3. 当前业务结论：客户订单【已处理完成】（接收端状态为 PROCESSED，业务处理完毕）。"
                    )
                    lines.append(
                        "4. 待验证事项：向客户核对本地业务系统展示是否已刷新。"
                    )
                    lines.append(
                        "5. 下一步建议：可向客户反馈回调已顺利完成入账与消费，工单可正常办结归档。"
                    )
                else:
                    lines.append(f"2. 当前状态：接收端处于 {receiver_status}，无法证明处理完成。")
                    lines.append("3. 下一步建议：等待系统状态明确。")

                lines.append("注：本说明为支持交接草稿，无配置修改与业务写入副作用。")
                content = "\n".join(lines)
                message = AIMessage(content=content)

        else:
            self.decisions.append({"action": "ANSWER"})
            message = AIMessage(content="直接回答，零工具调用。")

        message.usage_metadata = {"input_tokens": 15, "output_tokens": 10, "total_tokens": 25}
        return ChatResult(generations=[ChatGeneration(message=message)])


def _append_investigation_trace(db_path: Path, session_id: str, run_id: str, surrogate: Any) -> None:
    """Append end-to-end trace from actual test execution into dialog_trace.json."""
    target = os.environ.get("OPSPILOT_UPGRADE_INVESTIGATION_TRACE_PATH")
    if not target:
        target = "docs/evidence/ar-03/upgrade-investigation/dialog_trace.json"
    target_path = Path(target)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    existing_rows: list[dict[str, Any]] = []
    if target_path.is_file():
        try:
            existing_rows = json.loads(target_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            existing_rows = []

    rows: list[dict[str, Any]] = []
    with connect(db_path) as conn:
        run_row = conn.execute(
            "SELECT run_id,task_id,session_id,tenant_id,kind,status,source_message_id,created_at,ended_at "
            "FROM task_runs WHERE run_id=?", (run_id,),
        ).fetchone()
        if run_row:
            rows.append({"record_type": "task_run", **dict(run_row)})

        for call_row in conn.execute(
            "SELECT call_id,run_id,kind,logical_key,status,request_json,result_json,created_at,completed_at "
            "FROM assistant_calls WHERE run_id=? ORDER BY created_at",
            (run_id,),
        ):
            rows.append({"record_type": "assistant_call", **dict(call_row)})

        for msg_row in conn.execute(
            "SELECT message_id,session_id,tenant_id,role,body,task_id,sequence,created_at "
            "FROM messages WHERE session_id=? ORDER BY sequence",
            (session_id,),
        ):
            rows.append({"record_type": "session_message", **dict(msg_row)})

    rows.append({
        "record_type": "surrogate_model_summary",
        "run_id": run_id,
        "mode": getattr(surrogate, "mode", "unknown"),
        "offered_tools": getattr(surrogate, "offered_tool_names", []),
        "decisions": getattr(surrogate, "decisions", []),
    })

    combined = existing_rows + rows
    target_path.write_text(json.dumps(combined, ensure_ascii=False, indent=2), encoding="utf-8")


def test_journey_a_unbound_order_discovers_and_compares_protocols(demo_db, tmp_path):
    """Journey A: Unbound order inquiry -> discovery -> version compare -> impacts -> refusal to guess order."""
    surrogate = UpgradeInvestigationSurrogateModel(mode="journey_a")
    app = create_app(
        db_path=demo_db,
        checkpoint_db_path=tmp_path / "ar03-04-journey-a.sqlite3",
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

        # 2. Create unbound session
        session_res = client.post("/api/sessions", headers=headers)
        assert session_res.status_code in (200, 201), session_res.text
        session_id = session_res.json()["session_id"]

        # 3. User asks natural-language question without knowing internal doc IDs
        user_prompt = (
            "我们最近升级了回调协议，客户反馈重试行为变了。你帮我找一下旧版、新版规范，"
            "分析有什么变化，再看看客户是不是已经处理完成了。"
        )
        post_res = client.post(
            f"/api/sessions/{session_id}/assistant/messages",
            headers={**headers, "Idempotency-Key": "ar03-04-journey-a-turn-1"},
            json={"body": user_prompt},
        )
        assert post_res.status_code == 202, post_res.text
        run_id = post_res.json()["run_id"]

        # 4. Await asynchronous worker completion
        completed_run = _wait_run(client, run_id)
        assert completed_run["status"] == "SUCCEEDED"

        # 5. Verify assistant answer content
        messages_res = client.get(f"/api/sessions/{session_id}/messages")
        assert messages_res.status_code == 200
        messages = messages_res.json()["items"]
        assistant_msg = next(m for m in messages if m["role"] == "ASSISTANT")
        answer_text = assistant_msg["body"]

        # Check: difference analysis present
        assert "callback-retry-contract" in answer_text
        assert "callback-retry-contract-v2" in answer_text
        assert "重试" in answer_text or "retry" in answer_text.lower()

        # Check: unbound order handled honestly (cannot check customer order / receiver without binding)
        assert "尚未绑定" in answer_text or "未建立" in answer_text
        assert "无法核查" in answer_text or "未提供" in answer_text

        # Check: recommended next action to bind order
        assert "ar02-order" in answer_text or "绑定" in answer_text

        # 6. Verify continuous revalidation on persisted calls
        with connect(demo_db) as conn:
            valid, reason = sources_current(conn, run_id)
            assert valid is True, f"sources_current failed: {reason}"

            # Check that list_scoped_protocol_documents and compare_scoped_protocols were called
            mcp_calls = conn.execute(
                "SELECT request_json, status, result_json FROM assistant_calls WHERE run_id=? AND kind='MCP'",
                (run_id,),
            ).fetchall()
            reqs = [c["request_json"] for c in mcp_calls]
            assert any("list_scoped_protocol_documents" in r for r in reqs)
            assert any("compare_scoped_protocols" in r for r in reqs)

        _append_investigation_trace(demo_db, session_id, run_id, surrogate)


@pytest.mark.parametrize("receiver_target_state", ["QUEUED", "PROCESSED"])
def test_journey_b_bound_order_queued_vs_processed_distinction(demo_db, tmp_path, receiver_target_state):
    """Journey B: Bound order investigation under identical prompt yields distinct factual conclusions for QUEUED vs PROCESSED."""
    # 1. Setup S3 fixture
    fixture = prepare_s3_fixture(demo_db, "DELIVERED_PENDING", order_id="ar02-order", contract_version=2)
    assert fixture["receiver_http_status"] == 202

    if receiver_target_state == "PROCESSED":
        with connect(demo_db) as conn:
            conn.execute(
                "UPDATE s3_receivers SET status='PROCESSED', version=version+1 WHERE order_id='ar02-order'"
            )

    surrogate = UpgradeInvestigationSurrogateModel(mode="journey_b")
    app = create_app(
        db_path=demo_db,
        checkpoint_db_path=tmp_path / f"ar03-04-journey-b-{receiver_target_state}.sqlite3",
        start_worker=True,
        credentials=PASSWORDS,
        expected_origin=ORIGIN,
        assistant_model_factory=lambda: surrogate,
    )

    with TestClient(app) as client:
        # 2. Login as support-a
        login = client.post(
            "/api/auth/login",
            headers={"Origin": ORIGIN},
            json={"actor_id": "support-a", "password": PASSWORDS["support-a"]},
        )
        assert login.status_code == 200
        headers = {"Origin": ORIGIN, "X-CSRF-Token": login.json()["csrf_token"]}

        # 3. Create session and bind ar02-order
        session_res = client.post("/api/sessions", headers=headers)
        session_id = session_res.json()["session_id"]

        bind_res = client.post(
            f"/api/sessions/{session_id}/assistant/order",
            headers={**headers, "Idempotency-Key": f"bind-{receiver_target_state}"},
            json={"order_id": "ar02-order", "initial_message": "绑定 ar02-order"},
        )
        assert bind_res.status_code == 202
        bind_item = bind_res.json()
        bind_run_id = bind_item["run_id"]
        task_id = bind_item["task_id"]
        _wait_run(client, bind_run_id)

        # 4. Identical prompt asking about impact on completion status
        user_prompt = "现在结合这条订单的回调状态，判断升级是否可能影响处理完成，并帮我整理下一步建议。"
        investigate_res = client.post(
            f"/api/sessions/{session_id}/assistant/messages",
            headers={**headers, "Idempotency-Key": f"investigate-{receiver_target_state}"},
            json={"body": user_prompt, "task_id": task_id},
        )
        assert investigate_res.status_code == 202
        run_id = investigate_res.json()["run_id"]

        completed_run = _wait_run(client, run_id)
        assert completed_run["status"] == "SUCCEEDED"

        # 5. Verify assistant answer
        messages = client.get(f"/api/sessions/{session_id}/messages").json()["items"]
        assistant_msgs = [m for m in messages if m["role"] == "ASSISTANT"]
        last_answer = assistant_msgs[-1]["body"]

        # Both answers must recognise transport status 202
        assert "202" in last_answer

        # Verification of distinct conclusions:
        if receiver_target_state == "QUEUED":
            assert "尚未处理完成" in last_answer
            assert "QUEUED" in last_answer
            assert "切勿" in last_answer or "排队" in last_answer
            assert "已处理完成" not in last_answer or "尚未" in last_answer
        else:
            assert "已处理完成" in last_answer
            assert "PROCESSED" in last_answer
            assert "尚未处理完成" not in last_answer

        # Structured support hand-off notes check
        assert "真实已知事实" in last_answer
        assert "升级潜在影响" in last_answer
        assert "当前业务结论" in last_answer
        assert "下一步建议" in last_answer

        # 6. Verify zero business writes or repairs
        with connect(demo_db) as conn:
            valid, reason = sources_current(conn, run_id)
            assert valid is True

            # Ensure deliveries and receivers were not modified during investigation
            curr_rec = conn.execute("SELECT status FROM s3_receivers WHERE order_id='ar02-order'").fetchone()
            assert curr_rec["status"] == receiver_target_state

        _append_investigation_trace(demo_db, session_id, run_id, surrogate)


def test_scoped_protocol_discovery_safety_and_revalidation(demo_db, tmp_path):
    """Safety and revalidation tests for list_scoped_protocols and scoped_discovery_is_current."""
    identity = TrustedIdentity(
        actor_id="support-a",
        tenant_id="tenant-a",
        role="SUPPORT",
    )
    session_id = create_session(demo_db, identity)["session_id"]

    # 1. Normal listing discovers authorized documents under orders-callback
    discovery = list_scoped_protocols(demo_db, identity, session_id)
    assert discovery["session_id"] == session_id
    assert discovery["project_id"] == "orders-callback"
    assert discovery["tenant_id"] == "tenant-a"
    assert discovery["deployment_version_verified"] is False
    assert discovery["authority"] == "SESSION_AUTHORIZED_DISCOVERY_NOT_ACTION_AUTHORIZATION"

    doc_ids = [d["document_id"] for d in discovery["protocol_documents"]]
    assert "callback-retry-contract" in doc_ids
    assert "callback-retry-contract-v2" in doc_ids
    # Unauthorized docs (from other catalogs or projects) MUST NOT be present
    assert "api-scope-current" not in doc_ids

    # 2. Topic filtering
    retry_discovery = list_scoped_protocols(demo_db, identity, session_id, topic="retry")
    retry_doc_ids = [d["document_id"] for d in retry_discovery["protocol_documents"]]
    assert all("retry" in doc_id or "retry" in str(d.get("keywords", [])) for doc_id, d in zip(retry_doc_ids, retry_discovery["protocol_documents"]))
    assert "order-lifecycle-contract" not in retry_doc_ids

    # 3. Validation: legitimate discovery passes scoped_discovery_is_current
    ok, reason = scoped_discovery_is_current(demo_db, identity, session_id, discovery)
    assert ok is True
    assert reason is None

    # 4. Cross-session rejection
    ok, reason = scoped_discovery_is_current(demo_db, identity, "other-session-uuid", discovery)
    assert ok is False
    assert reason == "CROSS_SESSION_DISCOVERY_REJECTED"

    # 5. Cross-tenant rejection
    other_tenant_id = TrustedIdentity(actor_id="support-a", tenant_id="tenant-b", role="SUPPORT")
    ok, reason = scoped_discovery_is_current(demo_db, other_tenant_id, session_id, discovery)
    assert ok is False
    assert reason == "CROSS_TENANT_DISCOVERY_REJECTED"

    # 6. Actor mismatch rejection
    other_actor_id = TrustedIdentity(actor_id="support-b", tenant_id="tenant-a", role="SUPPORT")
    ok, reason = scoped_discovery_is_current(demo_db, other_actor_id, session_id, discovery)
    assert ok is False
    assert reason == "ACTOR_MISMATCH"

    # 7. Tampered document injection (inject unauthorized document)
    tampered_discovery = dict(discovery)
    tampered_docs = list(discovery["protocol_documents"]) + [{
        "document_id": "unauthorized-secret-spec",
        "title": "Secret",
        "version": "1.0.0",
        "source": "local:unknown",
        "digest": "0" * 64,
    }]
    tampered_discovery["protocol_documents"] = tampered_docs
    ok, reason = scoped_discovery_is_current(demo_db, identity, session_id, tampered_discovery)
    assert ok is False
    assert reason == "DOCUMENT_AUTHORIZATION_REVOKED"
