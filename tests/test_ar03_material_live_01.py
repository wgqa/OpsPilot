from __future__ import annotations

import time

import pytest
import httpx
from fastapi.testclient import TestClient
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import Field

from opspilot.domain.database import connect

EXPERIMENT_ID = "AR-03-MATERIAL-LIVE-01"
ORIGIN = "http://ar03-material-live-offline"
PASSWORDS = {"support-a": "material-live-offline"}


class RepeatedKnowledgeModel(BaseChatModel):
    """Offline contract probe: nine legal reads, then a final answer."""

    calls: int = 0
    offered_names: list = Field(default_factory=list)

    @property
    def _llm_type(self):
        return "AR03_MATERIAL_BUDGET_FIXTURE"

    def bind_tools(self, tools, **kwargs):
        self.offered_names = [tool.name for tool in tools]
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        self.calls += 1
        if self.calls <= 9:
            message = AIMessage(content="", tool_calls=[{
                "type": "tool_call",
                "name": "search_project_knowledge",
                "args": {"query": f"callback retry {self.calls}"},
                "id": f"material-budget-tool-{self.calls}",
            }])
        else:
            message = AIMessage(content="已完成离线预算边界验证；不代表真实模型结果。")
        message.usage_metadata = {"input_tokens": 24, "output_tokens": 12, "total_tokens": 36}
        return ChatResult(generations=[ChatGeneration(message=message)])


class ImmediateAnswerModel(BaseChatModel):
    offered_names: list = Field(default_factory=list)
    calls: int = 0

    @property
    def _llm_type(self):
        return "AR03_MATERIAL_SKILL_FIXTURE"

    def bind_tools(self, tools, **kwargs):
        self.offered_names = [tool.name for tool in tools]
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        self.calls += 1
        message = AIMessage(content="离线工具暴露检查；不代表真实模型效果。")
        message.usage_metadata = {"input_tokens": 24, "output_tokens": 12, "total_tokens": 36}
        return ChatResult(generations=[ChatGeneration(message=message)])


def _wait_run(client, run_id):
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        response = client.get(f"/api/runs/{run_id}")
        assert response.status_code == 200, response.text
        run = response.json()
        if run["status"] in {"SUCCEEDED", "FAILED", "BLOCKED", "CANCELLED"}:
            return run
        time.sleep(0.05)
    raise AssertionError(f"Run did not finish within offline test bound: {run_id}")


def test_material_live_campaign_uses_frozen_aggregate_limits(demo_db):
    from opspilot.domain.assistant_experiment import (
        initialize_experiment,
        read_budget,
    )

    initialize_experiment(demo_db, EXPERIMENT_ID)
    budget = read_budget(demo_db, EXPERIMENT_ID)

    assert budget["provider_limit"] == 16
    assert budget["mcp_limit"] == 10
    assert budget["budget_usd_micro"] == 10_500_000
    assert budget["provider_used"] == budget["mcp_used"] == 0


def test_material_live_mcp_ceiling_is_shared_across_runs(demo_db, tmp_path):
    from opspilot.domain.assistant_experiment import (
        ExperimentBudgetError,
        initialize_experiment,
        read_budget,
        reserve_dispatch,
    )
    from opspilot.web.app import create_app

    initialize_experiment(demo_db, EXPERIMENT_ID)
    app = create_app(
        db_path=demo_db,
        checkpoint_db_path=tmp_path / "material-live-campaign-cap.sqlite3",
        start_worker=False,
        credentials=PASSWORDS,
        expected_origin=ORIGIN,
        assistant_experiment_id=EXPERIMENT_ID,
    )
    with TestClient(app) as client:
        login = client.post(
            "/api/auth/login", headers={"Origin": ORIGIN},
            json={"actor_id": "support-a", "password": PASSWORDS["support-a"]},
        )
        assert login.status_code == 200, login.text
        headers = {"Origin": ORIGIN, "X-CSRF-Token": login.json()["csrf_token"]}
        run_ids = []
        for index in range(2):
            session_id = client.post("/api/sessions", headers=headers).json()["session_id"]
            accepted = client.post(
                f"/api/sessions/{session_id}/assistant/messages",
                headers={**headers, "Idempotency-Key": f"material-live-cap-run-{index}"},
                json={"body": "离线验证共享 Campaign MCP 额度。"},
            )
            assert accepted.status_code == 202, accepted.text
            run_ids.append(accepted.json()["run_id"])

    for index in range(10):
        reserved = reserve_dispatch(
            demo_db,
            experiment_id=EXPERIMENT_ID,
            run_id=run_ids[index // 5],
            kind="MCP",
            logical_key=f"tool-attempt-{index}",
            request={"tool": "search_project_knowledge", "index": index},
        )
        assert reserved["dispatch"] is True

    with pytest.raises(ExperimentBudgetError, match="AR02_LIVE_MCP_LIMIT"):
        reserve_dispatch(
            demo_db,
            experiment_id=EXPERIMENT_ID,
            run_id="third-isolated-run",
            kind="MCP",
            logical_key="tool-attempt-10",
            request={"tool": "search_project_knowledge", "index": 10},
        )

    budget = read_budget(demo_db, EXPERIMENT_ID)
    assert budget["mcp_used"] == 10


def test_material_live_run_limits_are_scoped_and_legacy_defaults_stay(demo_db):
    from opspilot.domain.assistant import run_limits_for_experiment
    from opspilot.domain.assistant_experiment import (
        AR03_REAL_LLM_02_EXPERIMENT_ID,
    )

    assert run_limits_for_experiment(EXPERIMENT_ID) == (16, 10)
    assert run_limits_for_experiment(AR03_REAL_LLM_02_EXPERIMENT_ID) == (8, 6)
    assert run_limits_for_experiment(None) == (8, 6)


def test_skill_off_hides_only_the_optional_loader_for_this_campaign(monkeypatch):
    from opspilot.assistant import assistant_tool_hidden_for_experiment

    monkeypatch.setenv("OPSPILOT_AR03_MATERIAL_SKILL_MODE", "OFF")

    assert assistant_tool_hidden_for_experiment(
        "load_protocol_upgrade_skill", EXPERIMENT_ID
    ) is True
    assert assistant_tool_hidden_for_experiment("compare_scoped_protocols", EXPERIMENT_ID) is False
    assert assistant_tool_hidden_for_experiment(
        "load_protocol_upgrade_skill", "AR-03-REAL-LLM-02"
    ) is False


def test_skill_on_keeps_optional_loader_available_for_model_choice(monkeypatch):
    from opspilot.assistant import assistant_tool_hidden_for_experiment

    monkeypatch.setenv("OPSPILOT_AR03_MATERIAL_SKILL_MODE", "ON")

    assert assistant_tool_hidden_for_experiment(
        "load_protocol_upgrade_skill", EXPERIMENT_ID
    ) is False


def test_formal_worker_allows_nine_mcp_and_ten_model_calls_under_campaign_caps(
    demo_db, tmp_path, monkeypatch,
):
    from opspilot.assistant import assistant_tool_hidden_for_experiment
    from opspilot.domain.assistant_experiment import read_budget
    from opspilot.web.app import create_app

    monkeypatch.setenv("OPSPILOT_ASSISTANT_EXPERIMENT_ID", EXPERIMENT_ID)
    monkeypatch.delenv("OPSPILOT_ASSISTANT_PROVIDER_ENABLED", raising=False)
    model = RepeatedKnowledgeModel()
    app = create_app(
        db_path=demo_db,
        checkpoint_db_path=tmp_path / "material-live-budget-checkpoint.sqlite3",
        start_worker=True,
        credentials=PASSWORDS,
        expected_origin=ORIGIN,
        assistant_model_factory=lambda: model,
        assistant_experiment_id=EXPERIMENT_ID,
    )
    with TestClient(app) as client:
        login = client.post(
            "/api/auth/login", headers={"Origin": ORIGIN},
            json={"actor_id": "support-a", "password": PASSWORDS["support-a"]},
        )
        assert login.status_code == 200, login.text
        headers = {"Origin": ORIGIN, "X-CSRF-Token": login.json()["csrf_token"]}
        session_id = client.post("/api/sessions", headers=headers).json()["session_id"]
        accepted = client.post(
            f"/api/sessions/{session_id}/assistant/messages",
            headers={**headers, "Idempotency-Key": "material-live-nine-mcp"},
            json={"body": "请查询有权限访问的回调重试协议资料。"},
        )
        assert accepted.status_code == 202, accepted.text
        run = _wait_run(client, accepted.json()["run_id"])
        assert run["status"] == "SUCCEEDED", run
        items = client.get(f"/api/sessions/{session_id}/messages", headers=headers).json()["items"]
        answer = next(
            row["body"] for row in items
            if row.get("answer_source_message_id") == accepted.json()["message_id"]
        )
        assert "离线预算边界验证" in answer

    budget = read_budget(demo_db, EXPERIMENT_ID)
    assert model.calls == 10
    assert budget["provider_used"] == 10
    assert budget["mcp_used"] == 9
    assert budget["provider_limit"] == 16 and budget["mcp_limit"] == 10
    assert "search_project_knowledge" in model.offered_names
    assert not assistant_tool_hidden_for_experiment(
        "load_protocol_upgrade_skill", EXPERIMENT_ID
    )
    with connect(demo_db) as connection:
        call_counts = dict(connection.execute(
            "SELECT kind, COUNT(*) FROM assistant_calls GROUP BY kind"
        ).fetchall())
        assert call_counts == {"MODEL": 10, "MCP": 9}


def test_trusted_s3_setup_can_use_approved_16_10_d2_attempt_pair(demo_db, tmp_path):
    from opspilot.domain.d2 import configure_s3_experiment_budget, task_attempt_limits
    from opspilot.domain.execution_budget import execution_budget_snapshot
    from opspilot.domain.s3 import prepare_s3_fixture
    from opspilot.web.app import create_app

    prepare_s3_fixture(demo_db, "DELIVERED_PENDING", order_id="ar03-order", contract_version=2)
    app = create_app(
        db_path=demo_db,
        checkpoint_db_path=tmp_path / "material-live-d2-checkpoint.sqlite3",
        start_worker=False,
        credentials=PASSWORDS,
        expected_origin=ORIGIN,
        assistant_experiment_id=EXPERIMENT_ID,
    )
    with TestClient(app) as client:
        login = client.post(
            "/api/auth/login", headers={"Origin": ORIGIN},
            json={"actor_id": "support-a", "password": PASSWORDS["support-a"]},
        )
        assert login.status_code == 200, login.text
        headers = {"Origin": ORIGIN, "X-CSRF-Token": login.json()["csrf_token"]}
        session_id = client.post("/api/sessions", headers=headers).json()["session_id"]
        accepted = client.post(
            f"/api/sessions/{session_id}/assistant/order",
            headers={**headers, "Idempotency-Key": "material-live-d2-budget"},
            json={"order_id": "ar03-order", "initial_message": "只读核实当前回调状态。"},
        )
        assert accepted.status_code == 202, accepted.text
        task_id = accepted.json()["task_id"]

    before = execution_budget_snapshot(demo_db, task_id)
    assert before["deadline_ms"] == 300_000
    configured = configure_s3_experiment_budget(demo_db, task_id, 16, 10)
    assert configured == {"MODEL": 16, "MCP": 10}
    assert task_attempt_limits(demo_db, task_id) == {"MODEL": 16, "MCP": 10}
    after = execution_budget_snapshot(demo_db, task_id)
    assert after["deadline_ms"] == before["deadline_ms"]
    with connect(demo_db) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM d2_attempts WHERE task_id=?", (task_id,)
        ).fetchone()[0] == 0


def test_material_live_can_create_distinct_isolated_tasks_for_same_registered_order(demo_db, tmp_path):
    from opspilot.domain.s3 import prepare_s3_fixture
    from opspilot.web.app import create_app

    prepare_s3_fixture(demo_db, "DELIVERED_PENDING", order_id="ar03-order", contract_version=2)
    app = create_app(
        db_path=demo_db,
        checkpoint_db_path=tmp_path / "material-live-two-task-checkpoint.sqlite3",
        start_worker=False,
        credentials=PASSWORDS,
        expected_origin=ORIGIN,
        assistant_experiment_id=EXPERIMENT_ID,
    )
    with TestClient(app) as client:
        login = client.post(
            "/api/auth/login", headers={"Origin": ORIGIN},
            json={"actor_id": "support-a", "password": PASSWORDS["support-a"]},
        )
        assert login.status_code == 200, login.text
        headers = {"Origin": ORIGIN, "X-CSRF-Token": login.json()["csrf_token"]}
        tasks = []
        for index in range(2):
            session_id = client.post("/api/sessions", headers=headers).json()["session_id"]
            accepted = client.post(
                f"/api/sessions/{session_id}/assistant/order",
                headers={**headers, "Idempotency-Key": f"material-live-same-order-{index}"},
                json={"order_id": "ar03-order", "initial_message": "只读核实授权订单。"},
            )
            assert accepted.status_code == 202, accepted.text
            tasks.append(accepted.json()["task_id"])
    assert tasks[0] != tasks[1]
    with connect(demo_db) as connection:
        bindings = connection.execute(
            "SELECT task_id,order_id FROM s3_task_resources WHERE task_id IN (?,?)",
            tuple(tasks),
        ).fetchall()
        assert {str(row["order_id"]) for row in bindings} == {"ar03-order"}
        assert {str(row["task_id"]) for row in bindings} == set(tasks)


@pytest.mark.parametrize("mode,expected", [("OFF", False), ("ON", True)])
def test_formal_worker_skill_mode_changes_only_loader_visibility(
    demo_db, tmp_path, monkeypatch, mode, expected,
):
    from opspilot.domain.assistant_experiment import read_budget
    from opspilot.web.app import create_app

    monkeypatch.setenv("OPSPILOT_ASSISTANT_EXPERIMENT_ID", EXPERIMENT_ID)
    monkeypatch.setenv("OPSPILOT_AR03_MATERIAL_SKILL_MODE", mode)
    monkeypatch.delenv("OPSPILOT_ASSISTANT_PROVIDER_ENABLED", raising=False)
    model = ImmediateAnswerModel()
    app = create_app(
        db_path=demo_db,
        checkpoint_db_path=tmp_path / f"material-live-skill-{mode}.sqlite3",
        start_worker=True,
        credentials=PASSWORDS,
        expected_origin=ORIGIN,
        assistant_model_factory=lambda: model,
        assistant_experiment_id=EXPERIMENT_ID,
    )
    with TestClient(app) as client:
        login = client.post(
            "/api/auth/login", headers={"Origin": ORIGIN},
            json={"actor_id": "support-a", "password": PASSWORDS["support-a"]},
        )
        assert login.status_code == 200, login.text
        headers = {"Origin": ORIGIN, "X-CSRF-Token": login.json()["csrf_token"]}
        session_id = client.post("/api/sessions", headers=headers).json()["session_id"]
        accepted = client.post(
            f"/api/sessions/{session_id}/assistant/messages",
            headers={**headers, "Idempotency-Key": f"material-live-skill-{mode}"},
            json={"body": "同一份回调协议升级问题，在 Skill unavailable/OFF 与 ON 的隔离运行中分别处理。"},
        )
        assert accepted.status_code == 202, accepted.text
        run = _wait_run(client, accepted.json()["run_id"])
        assert run["status"] == "SUCCEEDED", run
    assert model.calls == 1
    assert ("load_protocol_upgrade_skill" in model.offered_names) is expected
    assert "list_scoped_protocol_documents" in model.offered_names
    assert read_budget(demo_db, EXPERIMENT_ID)["provider_used"] == 1


def test_new_campaign_formal_api_wire_is_mocked_and_matches_frozen_provider_contract(
    demo_db, tmp_path, monkeypatch,
):
    import json

    from opspilot.assistant import create_assistant_model
    from opspilot.domain.assistant_experiment import read_budget
    from opspilot.web.app import create_app

    monkeypatch.setenv("OPSPILOT_ASSISTANT_EXPERIMENT_ID", EXPERIMENT_ID)
    monkeypatch.setenv("OPSPILOT_ASSISTANT_PROVIDER_ENABLED", "1")
    monkeypatch.setenv("OPSPILOT_MODEL_API_KEY", "offline-placeholder-not-a-credential")
    monkeypatch.setenv("OPSPILOT_MODEL_NAME", "deepseek-flash")
    monkeypatch.setenv("OPSPILOT_MODEL_BASE_URL", "https://api.deepseek.com/v1")
    captured = []
    urls = []

    async def respond(request):
        urls.append(str(request.url))
        captured.append(json.loads((await request.aread()).decode("utf-8")))
        return httpx.Response(
            200,
            headers={"x-request-id": "offline-material-live-wire"},
            json={
                "id": "offline-material-live-completion",
                "object": "chat.completion",
                "created": 1,
                "model": "deepseek-flash",
                "choices": [{
                    "index": 0,
                    "message": {"role": "assistant", "content": "Mock wire only; no real provider call."},
                    "finish_reason": "stop",
                }],
                "usage": {"prompt_tokens": 80, "completion_tokens": 10, "total_tokens": 90},
            },
        )

    app = create_app(
        db_path=demo_db,
        checkpoint_db_path=tmp_path / "material-live-mock-provider.sqlite3",
        start_worker=True,
        credentials=PASSWORDS,
        expected_origin=ORIGIN,
        assistant_model_factory=lambda: create_assistant_model(
            transport_async=httpx.MockTransport(respond),
            transport_sync=httpx.MockTransport(lambda request: httpx.Response(500)),
        ),
        assistant_experiment_id=EXPERIMENT_ID,
    )
    with TestClient(app) as client:
        login = client.post(
            "/api/auth/login", headers={"Origin": ORIGIN},
            json={"actor_id": "support-a", "password": PASSWORDS["support-a"]},
        )
        assert login.status_code == 200, login.text
        headers = {"Origin": ORIGIN, "X-CSRF-Token": login.json()["csrf_token"]}
        session_id = client.post("/api/sessions", headers=headers).json()["session_id"]
        accepted = client.post(
            f"/api/sessions/{session_id}/assistant/messages",
            headers={**headers, "Idempotency-Key": "material-live-mock-wire"},
            json={"body": "请解释用户提供材料中 HTTP 202 的一般含义，业务状态仍未知。"},
        )
        assert accepted.status_code == 202, accepted.text
        run = _wait_run(client, accepted.json()["run_id"])
        assert run["status"] == "SUCCEEDED", run
        messages = client.get(f"/api/sessions/{session_id}/messages", headers=headers).json()["items"]
        answer = next(
            row["body"] for row in messages
            if row.get("answer_source_message_id") == accepted.json()["message_id"]
        )
        assert "Mock wire only" in answer

    assert urls == ["https://api.deepseek.com/v1/chat/completions"]
    assert len(captured) == 1
    body = captured[0]
    assert body["model"] == "deepseek-flash"
    assert body["thinking"] == {"type": "disabled"}
    assert body["max_tokens"] == 2048
    assert body["tool_choice"] == "auto"
    assert body["parallel_tool_calls"] is False
    assert body["stream"] is False
    assert "max_completion_tokens" not in body
    tools = {tool["function"]["name"] for tool in body["tools"]}
    assert "load_protocol_upgrade_skill" in tools
    assert "list_scoped_protocol_documents" in tools
    assert "compare_scoped_protocols" in tools
    assert not any("repair" in tool.lower() or "deliver" in tool.lower() or "handoff" in tool.lower() for tool in tools)
    budget = read_budget(demo_db, EXPERIMENT_ID)
    assert budget["provider_used"] == 1 and budget["mcp_used"] == 0
    assert budget["usd_reserved_micro"] == 0 and budget["usd_settled_micro"] > 0
