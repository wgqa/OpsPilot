from __future__ import annotations

import json
import os
import time
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import Field

from opspilot.domain.database import connect
from opspilot.domain.s3 import prepare_s3_fixture
from opspilot.web.app import create_app
from test_ar02_assistant import ORIGIN, PASSWORDS
from test_ar02_ar03_integration_01 import _login, _wait_run


EVENT_ID = "event-00000000-0000-4000-8000-000000000001"
GOAL = (
    "我们正在把回调 API 从 v1 升级到 v2。这是我们当前的 JSON 配置和最近的回调失败日志。"
    "请分析哪些地方需要修改、会有什么兼容性风险、哪些可以直接从材料判断，以及当前订单的处理情况。"
    "最后帮我整理一份可以发给研发同事的升级检查清单。"
)
MATERIAL = (
    "\n\nJSON 配置（用户提供，未核实）：\n"
    '{\"api_version\":\"v1\",\"callback\":{\"retry\":{\"max_attempts\":5,\"backoff\":\"fixed\"}}}\n\n'
    "最近失败日志（用户提供，未核实）：\n"
    f"event_id={EVENT_ID}\n"
    "request_id=request-r2-sample-01\n"
    "http_status=503\n"
    "error_code=TEMPORARY_UNAVAILABLE\n"
    "attempt_count=1\n"
    "max_attempts=5\n"
    "retry_state=SCHEDULED\n"
    "retry_at=2026-11-12T10:15:00Z"
)
J1_INPUT = GOAL + MATERIAL


class IntegratedJourneyFixtureModel(BaseChatModel):
    """Offline model fixture; decisions are recorded and are not real-model evidence."""

    scenario: str
    use_skill: bool = False
    offered_tool_names: list[str] = Field(default_factory=list)
    seen: list = Field(default_factory=list)
    decisions: list[dict] = Field(default_factory=list)

    @property
    def _llm_type(self) -> str:
        return "R2_AR03_INTEGRATED_JOURNEY_FIXTURE"

    def bind_tools(self, tools, **kwargs):
        self.offered_tool_names = [tool.name for tool in tools]
        return self

    @staticmethod
    def _payload(message):
        value = message.content
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except json.JSONDecodeError:
                return {}
        while isinstance(value, dict) and set(value) == {"result"}:
            value = value["result"]
        return value if isinstance(value, dict) else {}

    @classmethod
    def _tool_results(cls, messages):
        names_by_id = {}
        for message in messages:
            for call in getattr(message, "tool_calls", []) or []:
                names_by_id[str(call.get("id"))] = str(call.get("name"))
        results = {}
        for message in messages:
            if isinstance(message, ToolMessage):
                name = getattr(message, "name", None) or names_by_id.get(str(message.tool_call_id))
                if name:
                    results[str(name)] = cls._payload(message)
        return results

    def _tool(self, name: str, arguments: dict) -> ChatResult:
        tool_call_id = f"r2-{self.scenario}-{len(self.decisions) + 1}"
        self.decisions.append({"action": "CALL", "tool": name, "args": arguments})
        message = AIMessage(content="", tool_calls=[{
            "name": name, "args": arguments, "id": tool_call_id,
        }])
        message.usage_metadata = {"input_tokens": 20, "output_tokens": 10, "total_tokens": 30}
        return ChatResult(generations=[ChatGeneration(message=message)])

    def _answer(self, text: str) -> ChatResult:
        self.decisions.append({"action": "ANSWER"})
        message = AIMessage(content=text)
        message.usage_metadata = {"input_tokens": 20, "output_tokens": 10, "total_tokens": 30}
        return ChatResult(generations=[ChatGeneration(message=message)])

    def _materials_response(self, payloads: dict) -> ChatResult:
        discovery = payloads.get("list_scoped_protocol_documents")
        if discovery is None:
            return self._tool("list_scoped_protocol_documents", {"topic": "callback retry"})

        documents = discovery.get("protocol_documents", [])
        old = next((row for row in documents if str(row.get("version", "")).startswith("1.")), None)
        new = next((row for row in documents if str(row.get("version", "")).startswith("2.")), None)
        if old is None or new is None:
            raise AssertionError(f"Expected scoped v1/v2 references, got: {discovery}")

        comparison = payloads.get("compare_scoped_protocols")
        if comparison is None:
            return self._tool("compare_scoped_protocols", {
                "base_document_id": old["document_id"],
                "target_document_id": new["document_id"],
                "base_version": old["version"],
                "target_version": new["version"],
            })

        excerpt_result = payloads.get("read_scoped_protocol_excerpt")
        if excerpt_result is None:
            return self._tool("read_scoped_protocol_excerpt", {
                "document_id": new["document_id"],
                "version": new["version"],
                "query": "retryable failure",
            })

        skill_result = payloads.get("load_protocol_upgrade_skill")
        if self.use_skill and skill_result is None:
            return self._tool("load_protocol_upgrade_skill", {
                "reason": "用户要求进行协议迁移影响分析并整理检查清单",
            })

        base = comparison.get("base_ref", {})
        target = comparison.get("target_ref", {})
        excerpt = excerpt_result.get("excerpts", [{}])[0]
        source_ref = excerpt_result.get("source_refs", [{}])[0]
        text = excerpt.get("text", "")
        loaded_skill = (
            skill_result.get("skill", {}).get("name")
            if skill_result and skill_result.get("success") is True else None
        )
        answer = (
            "## 协议差异与依据\n"
            f"本次授权目录比较了 {base.get('document_id')} v{base.get('version')} 与 "
            f"{target.get('document_id')} v{target.get('version')}；实际比较结果："
            f"{comparison.get('summary')}。原文摘录（{target.get('document_id')} "
            f"v{target.get('version')}，{source_ref.get('source')}，"
            f"第 {source_ref.get('line_start')}-{source_ref.get('line_end')} 行）：“{text}”\n"
            "该比较说明 v2 将重试判断绑定到可核实的 retryable failure 与当前 retry policy，"
            "并要求核对 attempt_count/max_attempts 及 response digest、event、request 与当前 delivery row；"
            "具体字段映射以授权原文为依据。\n"
            "## 用户材料能说明什么\n"
            "你提供的 JSON 写有 api_version=v1、max_attempts=5、backoff=fixed；这些是材料内容，"
            "不能证明线上服务已采用这些值。日志文本写有 HTTP 503、TEMPORARY_UNAVAILABLE、"
            "attempt_count=1、SCHEDULED 和 retry_at；若日志真实且与目标事件匹配，表示该快照记录了"
            "一个待重试线索，但本次没有从业务系统核验它。\n"
            "v2 原文没有证明 max_attempts=5 或 fixed backoff 一定兼容，也没有足够依据直接改成某个新数值。"
            "应先确认部署配置的字段映射、当前 retry policy、重试边界和旧客户端行为，再做兼容决策。\n"
            "## 当前订单状态\n"
            "当前 Session 没有可信订单绑定；不能从用户贴的日志判断订单现在是 QUEUED 还是 PROCESSED。"
            "项目文档版本也不能证明线上部署版本。\n"
            "## 研发升级检查清单\n"
            "1. 从可信发布配置核对实际 API 版本和 retry policy；风险：文档/配置与线上版本不一致；验证：查目标环境部署清单。\n"
            "2. 将 max_attempts、backoff 和 retryable failure 映射到 v2 原文；风险：字段虽存在但语义不同；验证：契约测试覆盖 503、不可重试错误、边界 attempt_count。\n"
            "3. 对每次重试校验 request、event、response digest 与当前 delivery row 的关联；风险：旧响应或其他 Event 被误配；验证：相关性负例与幂等测试。\n"
            "4. 分别验证 HTTP 202/ACKNOWLEDGED、Receiver QUEUED 与 PROCESSED；风险：把受理当完成；验证：同一 Event 的端到端状态对照。\n"
            "5. 灰度旧客户端/新客户端并记录回滚条件；这是建议的工程验证，不是本次已观测的业务事实。\n"
            "草稿尚未提交、没有创建工单或执行业务写入。"
            + (f"\n已按需加载方法 Skill：{loaded_skill}；它只提供方法提示，不是授权或事实。" if loaded_skill else "")
        )
        return self._answer(answer)

    def _current_response(self, payloads: dict) -> ChatResult:
        receiver = payloads.get("get_receiver_processing")
        if receiver is None:
            return self._tool("get_receiver_processing", {"reason": "核对绑定订单当前 Event 的 Receiver 状态"})
        delivery = payloads.get("get_callback_delivery")
        if delivery is None:
            return self._tool("get_callback_delivery", {"reason": "核对该订单当前 Event 的 Delivery 状态"})

        receiver_facts = receiver.get("facts", {})
        delivery_facts = delivery.get("facts", {})
        same_event = receiver_facts.get("event_id") == delivery_facts.get("event_id")
        state = receiver_facts.get("status") if same_event else "UNKNOWN"
        if state == "QUEUED":
            conclusion = "同一 Event 的 Receiver 当前为 QUEUED，处理尚未确认。"
        elif state == "PROCESSED":
            conclusion = "同一 Event 的 Receiver 当前为 PROCESSED，已处理完成。"
        else:
            conclusion = "缺少匹配同一 Event 的当前观察，处理状态未知。"
        return self._answer(
            f"本 Run 新读取到 Delivery HTTP {delivery_facts.get('receiver_http_status')} / "
            f"{delivery_facts.get('status')}，Event={delivery_facts.get('event_id')}；"
            f"Receiver Event={receiver_facts.get('event_id')}，状态={state}。{conclusion} "
            "HTTP 202/ACKNOWLEDGED 只表示接收方已受理，不单独证明处理完成。"
            "上一轮的协议比较和用户日志只是历史材料，本 Run 没有重新读取协议；"
            "线上部署版本仍未知。结论只适用于这个 Event；未创建工单、回执或业务写入。"
        )

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        self.seen.append(messages)
        payloads = self._tool_results(messages)
        if self.scenario == "materials":
            return self._materials_response(payloads)
        if self.scenario == "current":
            return self._current_response(payloads)
        if self.scenario == "simple":
            return self._answer(
                "HTTP 202 Accepted 通常表示请求已被接受处理；它本身不证明异步工作已经完成。"
            )
        if self.scenario == "history-unknown":
            return self._answer(
                "此前资料和回答是历史线索。本 Run 没有新的业务 Observation，因此当前订单处理状态仍未知。"
            )
        raise AssertionError(f"Unknown Fixture scenario: {self.scenario}")


def _messages(client, headers, session_id):
    return client.get(f"/api/sessions/{session_id}/messages", headers=headers).json()["items"]


def _answer_for(items, message_id):
    answers = [row for row in items if row.get("answer_source_message_id") == message_id]
    assert len(answers) == 1
    return answers[0]["body"]


def _submit(client, headers, session_id, model, key, body):
    started = time.perf_counter()
    response = client.post(
        f"/api/sessions/{session_id}/assistant/messages",
        headers={**headers, "Idempotency-Key": key},
        json={"body": body},
    )
    assert response.status_code == 202, response.text
    accepted = response.json()
    run = _wait_run(client, accepted["run_id"])
    elapsed_ms = round((time.perf_counter() - started) * 1000)
    assert run["status"] == "SUCCEEDED", run
    return accepted, run, elapsed_ms


def _record_trace(db_path, session_id, models, case, elapsed_ms, extras=None):
    run_rows = []
    calls = []
    messages = []
    protected = {}
    execution_budgets = []
    provider_spends = 0
    with connect(db_path) as connection:
        for row in connection.execute(
            "SELECT message_id,tenant_id,session_id,task_id,sequence,role,input_kind,body,body_digest,"
            "application_state,applied_run_id,created_at "
            "FROM messages WHERE session_id=? ORDER BY sequence",
            (session_id,),
        ).fetchall():
            messages.append(dict(row))
        answer_links = [
            dict(row) for row in connection.execute(
                "SELECT a.run_id,a.message_id,a.attempt_id,a.manifest_id,a.body_digest,a.committed_at,"
                "r.source_message_id FROM chat_run_answers a JOIN task_runs r ON r.run_id=a.run_id "
                "WHERE r.session_id=? ORDER BY a.committed_at",
                (session_id,),
            ).fetchall()
        ]
        run_rows = [
            dict(row) for row in connection.execute(
                "SELECT run_id,task_id,kind,status,source_message_id,created_at,started_at,ended_at "
                "FROM task_runs WHERE session_id=? ORDER BY created_at",
                (session_id,),
            ).fetchall()
        ]
        task_ids = sorted({str(row["task_id"]) for row in run_rows if row["task_id"]})
        if task_ids:
            placeholders = ",".join("?" for _ in task_ids)
            execution_budgets = [
                dict(row) for row in connection.execute(
                    f"SELECT task_id,tenant_id,policy_version,model_limit,mcp_limit,"
                    f"aux_provider_limit,deadline_ms FROM task_execution_budgets "
                    f"WHERE task_id IN ({placeholders}) ORDER BY task_id",
                    task_ids,
                ).fetchall()
            ]
        provider_spends = int(connection.execute(
            "SELECT COUNT(*) FROM assistant_runtime_spends",
        ).fetchone()[0])
        run_ids = [row["run_id"] for row in run_rows]
        if run_ids:
            placeholders = ",".join("?" for _ in run_ids)
            calls = [
                dict(row) for row in connection.execute(
                    f"SELECT * FROM assistant_calls WHERE run_id IN ({placeholders}) "
                    "ORDER BY created_at,call_id",
                    run_ids,
                ).fetchall()
            ]
        for table in (
            "s3_diagnoses", "d3_plans", "d3_plan_authorizations", "d3_approvals",
            "d3_action_permissions", "d3_action_intents", "d3_action_ledgers",
            "d3_verification_receipts", "d3_report_artifacts", "d3_delivery_records",
            "s3_handoff_queue_entries", "s3_handoff_receipts",
        ):
            protected[table] = int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])

    normalized_calls = []
    for row in calls:
        item = {key: row[key] for key in (
            "call_id", "run_id", "kind", "status", "created_at", "completed_at",
            "evidence_id", "observation_id", "usage_json", "error_code",
        ) if key in row.keys()}
        for field in ("request_json", "result_json"):
            value = row.get(field)
            if value:
                try:
                    item[field.removesuffix("_json")] = json.loads(value)
                except (TypeError, json.JSONDecodeError):
                    item[field.removesuffix("_json")] = value
        normalized_calls.append(item)

    record = {
        "record_type": "r2_ar03_integrated_journey",
        "evidence_level": "LOCAL_API_WORKER_MCP_WITH_FIXTURE_MODEL",
        "case": case,
        "session_id": session_id,
        "elapsed_ms": elapsed_ms,
        "provider_requests": provider_spends,
        "provider_spend_rows": provider_spends,
        "external_business_writes": 0,
        "task_execution_budgets": execution_budgets,
        "task_runs": run_rows,
        "messages": messages,
        "answer_source_links": answer_links,
        "calls": normalized_calls,
        "context_estimates": [
            call.get("request", {}).get("context_budget")
            for call in normalized_calls
            if call.get("kind") == "MODEL" and isinstance(call.get("request"), dict)
        ],
        "fixture_decisions": [
            {"scenario": model.scenario, "offered_tool_names": model.offered_tool_names,
             "decisions": model.decisions}
            for model in models
        ],
        "protected_write_counts": protected,
        "extras": extras or {},
    }
    line = json.dumps(record, ensure_ascii=False, sort_keys=True, default=str)
    target = os.environ.get("R2_AR03_TRACE_PATH")
    if target:
        trace_path = Path(target)
        trace_path.parent.mkdir(parents=True, exist_ok=True)
        with trace_path.open("a", encoding="utf-8") as stream:
            stream.write(line + "\n")
    print(
        f"R2_AR03_TRACE case={case} session_id={session_id} runs={len(run_rows)} "
        f"calls={len(normalized_calls)} provider_spend_rows={provider_spends}"
    )
    return record


def _mcp_calls(db_path, run_id):
    with connect(db_path) as connection:
        return [
            dict(row) for row in connection.execute(
                "SELECT request_json,result_json,status,evidence_id,observation_id "
                "FROM assistant_calls WHERE run_id=? AND kind='MCP' ORDER BY created_at",
                (run_id,),
            ).fetchall()
        ]


def _tool_names(calls):
    return [json.loads(row["request_json"])["name"] for row in calls]


def _assert_no_protected_writes(db_path):
    with connect(db_path) as connection:
        for table in (
            "s3_diagnoses", "d3_plans", "d3_plan_authorizations", "d3_approvals",
            "d3_action_permissions", "d3_action_intents", "d3_action_ledgers",
            "d3_verification_receipts", "d3_report_artifacts", "d3_delivery_records",
            "s3_handoff_queue_entries", "s3_handoff_receipts",
        ):
            assert connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0


def test_j1_material_protocol_comparison_and_checklist_without_binding(demo_db, tmp_path):
    model = IntegratedJourneyFixtureModel(scenario="materials", use_skill=True)
    app = create_app(
        db_path=demo_db,
        checkpoint_db_path=tmp_path / "r2-j1-checkpoint.sqlite3",
        start_worker=True,
        credentials=PASSWORDS,
        expected_origin=ORIGIN,
        assistant_model_factory=lambda: model,
    )
    with TestClient(app) as client:
        headers = _login(client)
        session_id = client.post("/api/sessions", headers=headers).json()["session_id"]
        accepted, run, elapsed_ms = _submit(
            client, headers, session_id, model, "r2-j1-materials", J1_INPUT,
        )
        answer = _answer_for(_messages(client, headers, session_id), accepted["message_id"])
        trace = _record_trace(
            demo_db, session_id, [model], "J1", elapsed_ms,
            {"answer": answer, "accepted": accepted},
        )

    assert run["status"] == "SUCCEEDED"
    assert accepted.get("task_id") is None
    assert all(marker in answer for marker in (
        "callback-retry-contract v1.0.0",
        "callback-retry-contract-v2 v2.0.0",
        "max_attempts=5",
        "backoff=fixed",
        "当前 Session 没有可信订单绑定",
        "升级检查清单",
        "没有创建工单",
    ))
    calls = _mcp_calls(demo_db, accepted["run_id"])
    names = _tool_names(calls)
    assert set(names) == {
        "list_scoped_protocol_documents", "compare_scoped_protocols",
        "read_scoped_protocol_excerpt", "load_protocol_upgrade_skill",
    }
    assert len(calls) <= 6 and all(row["status"] == "OK" for row in calls)
    comparison = next(json.loads(row["result_json"]) for row in calls
                      if json.loads(row["request_json"])["name"] == "compare_scoped_protocols")
    excerpt = next(json.loads(row["result_json"]) for row in calls
                   if json.loads(row["request_json"])["name"] == "read_scoped_protocol_excerpt")
    assert comparison["diff_evidence"]
    assert excerpt["source_refs"] and excerpt["excerpts"]
    assert "get_order_status" not in model.offered_tool_names
    assert not ({"get_order_status", "get_callback_delivery", "get_receiver_processing"} & set(names))
    with connect(demo_db) as connection:
        assert connection.execute("SELECT COUNT(*) FROM task_bindings").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM d2_evidence").fetchone()[0] == 0
        assert connection.execute(
            "SELECT COUNT(*) FROM messages WHERE session_id=? AND role='USER'", (session_id,),
        ).fetchone()[0] == 1
    assert trace["provider_requests"] == 0
    _assert_no_protected_writes(demo_db)


@pytest.mark.parametrize("receiver_state", ["QUEUED", "PROCESSED"])
def test_j2_same_session_binding_uses_current_same_event_observation(
    demo_db, tmp_path, monkeypatch, receiver_state,
):
    ids = iter((
        uuid.UUID("00000000-0000-4000-8000-000000000001"),
        uuid.UUID("00000000-0000-4000-8000-000000000002"),
    ))
    with monkeypatch.context() as patcher:
        patcher.setattr("opspilot.domain.s3.uuid.uuid4", lambda: next(ids))
        fixture = prepare_s3_fixture(
            demo_db, "DELIVERED_PENDING", order_id="r2-ar03-order", contract_version=2,
        )
    assert fixture["transport_trace"][0]["request"]["event_id"] == EVENT_ID
    if receiver_state == "PROCESSED":
        with connect(demo_db) as connection:
            connection.execute(
                "UPDATE s3_receivers SET status='PROCESSED',version=version+1 "
                "WHERE tenant_id='tenant-a' AND order_id='r2-ar03-order'"
            )

    materials_model = IntegratedJourneyFixtureModel(scenario="materials", use_skill=True)
    current_model = IntegratedJourneyFixtureModel(scenario="current")
    model_queue = [materials_model, current_model]
    app = create_app(
        db_path=demo_db,
        checkpoint_db_path=tmp_path / f"r2-j2-{receiver_state}-checkpoint.sqlite3",
        start_worker=True,
        credentials=PASSWORDS,
        expected_origin=ORIGIN,
        assistant_model_factory=lambda: model_queue.pop(0),
    )
    with TestClient(app) as client:
        headers = _login(client)
        session_id = client.post("/api/sessions", headers=headers).json()["session_id"]
        first, _, first_elapsed = _submit(
            client, headers, session_id, materials_model, "r2-j2-materials", J1_INPUT,
        )
        binding_started = time.perf_counter()
        binding_response = client.post(
            f"/api/sessions/{session_id}/assistant/order",
            headers={**headers, "Idempotency-Key": f"r2-j2-bind-{receiver_state.lower()}"},
            json={
                "order_id": "r2-ar03-order",
                "initial_message": "请结合刚才的材料，核对这个订单当前同一 Event 的处理状态。",
            },
        )
        assert binding_response.status_code == 202, binding_response.text
        binding = binding_response.json()
        bound_run = _wait_run(client, binding["run_id"])
        second_elapsed = round((time.perf_counter() - binding_started) * 1000)
        assert bound_run["status"] == "SUCCEEDED", bound_run
        items = _messages(client, headers, session_id)
        first_answer = _answer_for(items, first["message_id"])
        answer = _answer_for(items, binding["message_id"])
        trace = _record_trace(
            demo_db, session_id, [materials_model, current_model], f"J2-{receiver_state}",
            first_elapsed + second_elapsed,
            {"answer": answer, "first_answer": first_answer, "binding": binding},
        )

    assert "max_attempts=5" in first_answer
    assert "本 Run 新读取到 Delivery HTTP 202 / ACKNOWLEDGED" in answer
    assert "同一 Event" in answer and EVENT_ID in answer
    assert "HTTP 202/ACKNOWLEDGED 只表示" in answer
    assert "上一轮的协议比较和用户日志只是历史材料，本 Run 没有重新读取协议" in answer
    if receiver_state == "QUEUED":
        assert "QUEUED" in answer and "处理尚未确认" in answer
        assert "PROCESSED" not in answer
    else:
        assert "PROCESSED" in answer and "已处理完成" in answer
        assert "处理尚未确认" not in answer

    calls = _mcp_calls(demo_db, binding["run_id"])
    names = _tool_names(calls)
    assert set(names) == {"get_receiver_processing", "get_callback_delivery"}
    assert len(calls) == 2 and all(row["status"] == "OK" for row in calls)
    by_name = {json.loads(row["request_json"])["name"]: row for row in calls}
    receiver = json.loads(by_name["get_receiver_processing"]["result_json"])
    delivery = json.loads(by_name["get_callback_delivery"]["result_json"])
    assert receiver["facts"]["event_id"] == delivery["facts"]["event_id"] == EVENT_ID
    assert all(by_name[name]["evidence_id"] and by_name[name]["observation_id"]
               for name in ("get_receiver_processing", "get_callback_delivery"))
    with connect(demo_db) as connection:
        model_requests = [
            json.loads(row["request_json"])
            for row in connection.execute(
                "SELECT request_json FROM assistant_calls WHERE run_id=? AND kind='MODEL' ORDER BY created_at",
                (binding["run_id"],),
            ).fetchall()
        ]
    assert model_requests
    refs = model_requests[-1]["source_refs"]
    current = refs["current_run"]["business_observations"]
    assert {item["tool"] for item in current} >= {
        "get_receiver_processing", "get_callback_delivery",
    }
    assert first["message_id"] in model_requests[-1]["selected_message_ids"]
    assert binding["message_id"] in model_requests[-1]["selected_message_ids"]
    prompt_text = "\n".join(
        str(message.get("data", {}).get("content", ""))
        for request in model_requests
        for message in request.get("messages", [])
    )
    assert '"max_attempts":5' in prompt_text and '"backoff":"fixed"' in prompt_text
    assert "SCHEDULED" in prompt_text
    with connect(demo_db) as connection:
        assert all(
            json.loads(row["request_json"])["context_budget"]["estimated_input_tokens"] <= 12_000
            for row in connection.execute(
                "SELECT request_json FROM assistant_calls WHERE run_id=? AND kind='MODEL'",
                (binding["run_id"],),
            ).fetchall()
        )
    with connect(demo_db) as connection:
        budget = connection.execute(
            "SELECT model_limit,mcp_limit,aux_provider_limit,policy_version "
            "FROM task_execution_budgets WHERE task_id=?",
            (binding["task_id"],),
        ).fetchone()
        assert budget is not None
        assert (budget["model_limit"], budget["mcp_limit"], budget["aux_provider_limit"],
                budget["policy_version"]) == (24, 18, 8, "CONTUX_S3_V1")
        assistant_model_count = connection.execute(
            "SELECT COUNT(*) FROM assistant_calls WHERE run_id=? AND kind='MODEL'",
            (binding["run_id"],),
        ).fetchone()[0]
        assert assistant_model_count <= budget["aux_provider_limit"]
        assert connection.execute(
            "SELECT COUNT(*) FROM task_runs WHERE session_id=?", (session_id,),
        ).fetchone()[0] == 2
        assert connection.execute(
            "SELECT COUNT(*) FROM task_bindings WHERE task_id=?", (binding["task_id"],),
        ).fetchone()[0] == 1
        assert connection.execute(
            "SELECT COUNT(*) FROM d3_action_ledgers WHERE task_id=?", (binding["task_id"],),
        ).fetchone()[0] == 0
        from opspilot.domain.assistant import sources_current
        assert sources_current(connection, binding["run_id"]) == (True, None)
    assert trace["provider_requests"] == 0
    _assert_no_protected_writes(demo_db)


def test_j3_cross_tenant_binding_is_denied_then_material_analysis_continues(demo_db, tmp_path):
    prepare_s3_fixture(
        demo_db, "DELIVERED_PENDING", tenant_id="tenant-b",
        order_id="tenant-b-secret-order", contract_version=2,
    )
    model = IntegratedJourneyFixtureModel(scenario="materials", use_skill=False)
    app = create_app(
        db_path=demo_db,
        checkpoint_db_path=tmp_path / "r2-j3-checkpoint.sqlite3",
        start_worker=True,
        credentials=PASSWORDS,
        expected_origin=ORIGIN,
        assistant_model_factory=lambda: model,
    )
    with TestClient(app, raise_server_exceptions=False) as client:
        headers = _login(client)
        session_id = client.post("/api/sessions", headers=headers).json()["session_id"]
        denied = client.post(
            f"/api/sessions/{session_id}/assistant/order",
            headers={**headers, "Idempotency-Key": "r2-j3-cross-tenant-bind"},
            json={
                "order_id": "tenant-b-secret-order",
                "initial_message": "读取另一个租户订单的处理状态。",
            },
        )
        assert 400 <= denied.status_code < 500, denied.text
        assert denied.status_code != 202
        assert "tenant-b-secret-order" not in denied.text

        accepted, run, elapsed_ms = _submit(
            client, headers, session_id, model, "r2-j3-legal-materials",
            "虽然当前订单查询不可访问，请继续完成合法协议分析与升级清单。"
            + MATERIAL,
        )
        answer = _answer_for(_messages(client, headers, session_id), accepted["message_id"])
        trace = _record_trace(
            demo_db, session_id, [model], "J3", elapsed_ms,
            {"answer": answer, "denied_status": denied.status_code},
        )

    assert run["status"] == "SUCCEEDED"
    assert accepted.get("task_id") is None
    assert "callback-retry-contract-v2 v2.0.0" in answer
    assert "当前 Session 没有可信订单绑定" in answer
    assert "线上部署版本" in answer
    assert "tenant-b-secret-order" not in str(model.seen)
    assert "get_order_status" not in model.offered_tool_names
    names = _tool_names(_mcp_calls(demo_db, accepted["run_id"]))
    assert not ({"get_order_status", "get_callback_delivery", "get_receiver_processing"} & set(names))
    with connect(demo_db) as connection:
        assert connection.execute("SELECT COUNT(*) FROM task_bindings").fetchone()[0] == 0
        assert connection.execute(
            "SELECT COUNT(*) FROM task_runs WHERE session_id=? AND task_id IS NOT NULL",
            (session_id,),
        ).fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM d2_evidence").fetchone()[0] == 0
    assert trace["provider_requests"] == 0
    _assert_no_protected_writes(demo_db)


def test_heldout_expression_uses_documents_and_simple_question_skips_skill(demo_db, tmp_path):
    heldout = IntegratedJourneyFixtureModel(scenario="materials", use_skill=False)
    simple = IntegratedJourneyFixtureModel(scenario="simple")
    model_queue = [heldout, simple]
    app = create_app(
        db_path=demo_db,
        checkpoint_db_path=tmp_path / "r2-heldout-checkpoint.sqlite3",
        start_worker=True,
        credentials=PASSWORDS,
        expected_origin=ORIGIN,
        assistant_model_factory=lambda: model_queue.pop(0),
    )
    with TestClient(app) as client:
        headers = _login(client)
        session_id = client.post("/api/sessions", headers=headers).json()["session_id"]
        heldout_input = (
            "这份重试配置能否直接用于新回调接口？请把依据、兼容风险和还未确认的地方一起列成上线前检查表。"
            + MATERIAL
        )
        first, _, first_elapsed = _submit(
            client, headers, session_id, heldout, "r2-heldout-materials", heldout_input,
        )
        first_answer = _answer_for(_messages(client, headers, session_id), first["message_id"])
        second, _, second_elapsed = _submit(
            client, headers, session_id, simple, "r2-simple-http-202",
            "HTTP 202 通常代表什么？",
        )
        second_answer = _answer_for(_messages(client, headers, session_id), second["message_id"])
        trace = _record_trace(
            demo_db, session_id, [heldout, simple], "HELDOUT_AND_SIMPLE",
            first_elapsed + second_elapsed,
            {"heldout_answer": first_answer, "simple_answer": second_answer},
        )

    assert "callback-retry-contract-v2 v2.0.0" in first_answer
    assert "升级检查清单" in first_answer
    assert "HTTP 202 Accepted" in second_answer
    assert "load_protocol_upgrade_skill" not in [row["tool"] for row in heldout.decisions if row["action"] == "CALL"]
    assert heldout.offered_tool_names
    assert simple.decisions == [{"action": "ANSWER"}]
    assert _mcp_calls(demo_db, second["run_id"]) == []
    assert trace["provider_requests"] == 0
    _assert_no_protected_writes(demo_db)


def test_historical_material_followup_does_not_claim_a_current_business_read(demo_db, tmp_path):
    prior = IntegratedJourneyFixtureModel(scenario="materials", use_skill=False)
    followup = IntegratedJourneyFixtureModel(scenario="history-unknown")
    model_queue = [prior, followup]
    app = create_app(
        db_path=demo_db,
        checkpoint_db_path=tmp_path / "r2-history-checkpoint.sqlite3",
        start_worker=True,
        credentials=PASSWORDS,
        expected_origin=ORIGIN,
        assistant_model_factory=lambda: model_queue.pop(0),
    )
    with TestClient(app) as client:
        headers = _login(client)
        session_id = client.post("/api/sessions", headers=headers).json()["session_id"]
        first, _, first_elapsed = _submit(
            client, headers, session_id, prior, "r2-history-first", J1_INPUT,
        )
        second, _, second_elapsed = _submit(
            client, headers, session_id, followup, "r2-history-followup",
            "根据前面内容，现在订单处理到哪一步了？",
        )
        answer = _answer_for(_messages(client, headers, session_id), second["message_id"])
        trace = _record_trace(
            demo_db, session_id, [prior, followup], "HISTORY_WITHOUT_NEW_BUSINESS_OBSERVATION",
            first_elapsed + second_elapsed, {"answer": answer},
        )

    assert "当前订单处理状态仍未知" in answer
    assert _mcp_calls(demo_db, second["run_id"]) == []
    with connect(demo_db) as connection:
        model_request = connection.execute(
            "SELECT request_json FROM assistant_calls WHERE run_id=? AND kind='MODEL' ORDER BY created_at DESC LIMIT 1",
            (second["run_id"],),
        ).fetchone()
        request_json = model_request["request_json"]
        refs = json.loads(request_json)["source_refs"]
        assert refs["current_run"]["business_observations"] == []
        assert "不能声称本轮已重读" in request_json
    assert trace["provider_requests"] == 0
    _assert_no_protected_writes(demo_db)
