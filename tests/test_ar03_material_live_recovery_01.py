from __future__ import annotations

import hashlib
import importlib.util
import json
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import Field

ROOT = Path(__file__).resolve().parents[1]
RUNNER_PATH = ROOT / "docs/evidence/ar-03/material-live-01/run_live.py"
RUNNER_SPEC = importlib.util.spec_from_file_location("ar03_material_live_runner_recovery", RUNNER_PATH)
RUNNER = importlib.util.module_from_spec(RUNNER_SPEC)
assert RUNNER_SPEC is not None and RUNNER_SPEC.loader is not None
RUNNER_SPEC.loader.exec_module(RUNNER)

EXPERIMENT_ID = "AR-03-MATERIAL-LIVE-01"
ORIGIN = "http://ar03-material-recovery-preview"
PASSWORD = "material-recovery-preview-local"


class RecoveryPreviewModel(BaseChatModel):
    """Deterministic offline adapter; its choices are not real Agent evidence."""

    calls: int = 0
    offered_names: list[str] = Field(default_factory=list)
    proposed_tools: list[str] = Field(default_factory=list)

    @property
    def _llm_type(self) -> str:
        return "AR03_MATERIAL_RECOVERY_PREVIEW_FIXTURE"

    def bind_tools(self, tools, **kwargs):
        self.offered_names = [tool.name for tool in tools]
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        self.calls += 1
        calls = {
            1: ("get_callback_delivery", {"reason": "核实绑定订单当前回调投递和同一 Event 的受理结果。"}),
            2: ("get_receiver_processing", {"reason": "根据投递观察核实同一 Event 的 Receiver 处理状态。"}),
        }
        if self.calls in calls:
            name, args = calls[self.calls]
            self.proposed_tools.append(name)
            message = AIMessage(content="", tool_calls=[{
                "type": "tool_call", "name": name, "args": args,
                "id": f"recovery-preview-tool-{self.calls}",
            }])
        else:
            message = AIMessage(
                content=(
                    "离线预演确认：同一 Event 的 Delivery 为 HTTP 202/ACKNOWLEDGED，"
                    "Receiver 当前为 QUEUED；因此业务处理完成尚未确认。"
                    "此回答来自确定性 FixtureModel，不代表真实模型调用或线上部署判断。"
                )
            )
        message.usage_metadata = {"input_tokens": 48, "output_tokens": 32, "total_tokens": 80}
        return ChatResult(generations=[ChatGeneration(message=message)])


def _file_digest(path: Path) -> str | None:
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _login(client: TestClient) -> dict[str, str]:
    response = client.post(
        "/api/auth/login", headers={"Origin": ORIGIN},
        json={"actor_id": "support-a", "password": PASSWORD},
    )
    assert response.status_code == 200, response.text
    return {"Origin": ORIGIN, "X-CSRF-Token": response.json()["csrf_token"]}


def _wait_run(client: TestClient, run_id: str) -> dict:
    deadline = time.monotonic() + 45
    while time.monotonic() < deadline:
        response = client.get(f"/api/runs/{run_id}")
        assert response.status_code == 200, response.text
        run = response.json()
        if run.get("status") in {"SUCCEEDED", "FAILED", "BLOCKED", "CANCELLED"}:
            return run
        time.sleep(0.05)
    raise AssertionError("recovery preview Worker did not reach a terminal Run state")


@pytest.mark.parametrize("existing_artifact", ["database", "-wal", "-shm"])
def test_bootstrap_refuses_existing_campaign_database_artifacts_without_changing_them(
    tmp_path, existing_artifact,
):
    database = tmp_path / "existing.sqlite3"
    artifact = database if existing_artifact == "database" else Path(f"{database}{existing_artifact}")
    sentinel = b"pre-existing campaign database artifact must never be reset"
    artifact.write_bytes(sentinel)

    with pytest.raises(RuntimeError, match="CAMPAIGN_DATABASE_NOT_FRESH"):
        RUNNER._bootstrap_fresh_campaign_database(database)

    assert artifact.read_bytes() == sentinel
    if existing_artifact != "database":
        assert not database.exists()


def test_fresh_bootstrap_and_formal_worker_read_only_preview(
    tmp_path, monkeypatch,
):
    from opspilot.domain.assistant_experiment import initialize_experiment, read_budget
    from opspilot.domain.database import connect
    from opspilot.domain.d2 import configure_s3_experiment_budget, task_attempt_limits
    from opspilot.domain.execution_budget import execution_budget_snapshot
    from opspilot.domain.s3 import prepare_s3_fixture
    from opspilot.web.app import create_app

    monkeypatch.setenv("OPSPILOT_ASSISTANT_EXPERIMENT_ID", EXPERIMENT_ID)
    monkeypatch.setenv("OPSPILOT_ASSISTANT_PROVIDER_ENABLED", "0")
    monkeypatch.setenv("OPSPILOT_AR03_MATERIAL_SKILL_MODE", "ON")
    from opspilot.assistant import create_assistant_model
    assert create_assistant_model() is None

    # Hash only the immutable historical one-shot evidence; never open its DB.
    historical_paths = [
        RUNNER.EVIDENCE / "EXECUTION_CLAIM.json",
        RUNNER.EVIDENCE / "TRACE.jsonl",
        RUNNER.EVIDENCE / "RESULTS.json",
        RUNNER.EVIDENCE / "BUDGET_LEDGER.json",
        RUNNER.DOMAIN_DB,
        RUNNER.CHECKPOINT_DB,
    ]
    historical_before = {str(path.relative_to(ROOT)): _file_digest(path) for path in historical_paths}

    db_path = tmp_path / "fresh-domain.sqlite3"
    checkpoint_path = tmp_path / "fresh-checkpoint.sqlite3"
    assert not db_path.exists()
    RUNNER._bootstrap_fresh_campaign_database(db_path)

    with connect(db_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM tenants").fetchone()[0] == 2
        assert connection.execute(
            "SELECT COUNT(*) FROM principals WHERE tenant_id='tenant-a' AND principal_id='principal-a' AND status='ENABLED'"
        ).fetchone()[0] == 1

    # The campaign ledger is created only after the trusted demo bootstrap.
    initialize_experiment(db_path, EXPERIMENT_ID)
    campaign_before = read_budget(db_path, EXPERIMENT_ID)
    assert campaign_before["provider_used"] == campaign_before["mcp_used"] == 0
    assert campaign_before["usd_reserved_micro"] == campaign_before["usd_settled_micro"] == 0

    setup = prepare_s3_fixture(
        db_path, "DELIVERED_PENDING", tenant_id="tenant-a", order_id="ar03-order",
        contract_version=2, queue_age_seconds=60,
    )
    with connect(db_path) as connection:
        delivery = dict(connection.execute(
            "SELECT * FROM s3_deliveries WHERE tenant_id='tenant-a' AND order_id='ar03-order'"
        ).fetchone())
        receiver = dict(connection.execute(
            "SELECT * FROM s3_receivers WHERE tenant_id='tenant-a' AND order_id='ar03-order'"
        ).fetchone())
    assert delivery["receiver_http_status"] == 202
    assert delivery["status"] == "ACKNOWLEDGED"
    assert receiver["status"] == "QUEUED"
    assert delivery["event_id"] == receiver["event_id"]

    cases = json.loads(RUNNER.CASES_PATH.read_text(encoding="utf-8"))
    mat04 = next(case for case in cases["cases"] if case["id"] == "MAT-04-BOUND-QUEUED")
    exact_user_input = mat04["input"]
    model = RecoveryPreviewModel()
    app = create_app(
        db_path=db_path, checkpoint_db_path=checkpoint_path, start_worker=False,
        credentials={"support-a": PASSWORD}, expected_origin=ORIGIN,
        assistant_experiment_id=EXPERIMENT_ID,
    )
    with TestClient(app) as client:
        headers = _login(client)
        session_response = client.post("/api/sessions", headers=headers)
        assert session_response.status_code == 201, session_response.text
        session_id = session_response.json()["session_id"]
        accepted_response = client.post(
            f"/api/sessions/{session_id}/assistant/order",
            headers={**headers, "Idempotency-Key": "recovery-preview-mat04"},
            json={"order_id": "ar03-order", "initial_message": exact_user_input},
        )
        assert accepted_response.status_code == 202, accepted_response.text
        accepted = accepted_response.json()
        task_id, run_id, message_id = accepted["task_id"], accepted["run_id"], accepted["message_id"]

    before_time = execution_budget_snapshot(db_path, task_id)
    assert before_time["deadline_ms"] == 300_000
    configured = configure_s3_experiment_budget(db_path, task_id, 16, 10)
    assert configured == {"MODEL": 16, "MCP": 10}
    assert task_attempt_limits(db_path, task_id) == configured
    assert execution_budget_snapshot(db_path, task_id)["deadline_ms"] == before_time["deadline_ms"]

    worker_app = create_app(
        db_path=db_path, checkpoint_db_path=checkpoint_path, start_worker=True,
        credentials={"support-a": PASSWORD}, expected_origin=ORIGIN,
        assistant_model_factory=lambda: model,
        assistant_experiment_id=EXPERIMENT_ID,
    )
    with TestClient(worker_app) as client:
        headers = _login(client)
        run = _wait_run(client, run_id)
        messages_response = client.get(f"/api/sessions/{session_id}/messages", headers=headers)
        assert messages_response.status_code == 200, messages_response.text
        messages = messages_response.json()["items"]
        sources_response = client.get(f"/api/runs/{run_id}/assistant-sources")
        assert sources_response.status_code == 200, sources_response.text
        sources = sources_response.json()

    assert run["status"] == "SUCCEEDED", run
    assert model.calls == 3
    assert model.proposed_tools == ["get_callback_delivery", "get_receiver_processing"]
    assert {"get_callback_delivery", "get_receiver_processing"}.issubset(set(model.offered_names))
    assert set(model.offered_names).issubset(RUNNER.ALLOWED_TOOLS)
    assert sources["current"] is True, sources
    assert {item["tool_name"] for item in sources["items"]} == {
        "get_callback_delivery", "get_receiver_processing",
    }
    assert all(item["status"] == "OK" and item["evidence_id"] and item["observation_id"] for item in sources["items"])
    answers = [item for item in messages if item.get("answer_source_message_id") == message_id]
    assert len(answers) == 1
    answer = answers[0]["body"]
    assert "202/ACKNOWLEDGED" in answer and "QUEUED" in answer
    assert "真实模型调用" in answer

    with connect(db_path) as connection:
        binding = dict(connection.execute(
            "SELECT * FROM s3_task_resources WHERE task_id=?", (task_id,)
        ).fetchone())
        assert binding["order_id"] == "ar03-order"
        observations = [dict(row) for row in connection.execute(
            "SELECT o.*,a.run_id AS attempt_run_id FROM d2_tool_observations o "
            "JOIN d2_attempts a ON a.attempt_id=o.attempt_id AND a.task_id=o.task_id "
            "WHERE o.task_id=? AND a.run_id=? ORDER BY o.created_at,o.observation_id",
            (task_id, run_id),
        ).fetchall()]
        business_write_counts = {
            table: int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
            for table in RUNNER.BUSINESS_WRITE_TABLES
        }
        assistant_core = connection.execute(
            "SELECT core FROM assistant_runs WHERE run_id=?", (run_id,)
        ).fetchone()["core"]
        raw_calls = [dict(row) for row in connection.execute(
            "SELECT kind,request_json,result_json,observation_id,evidence_id,status FROM assistant_calls "
            "WHERE run_id=? ORDER BY rowid", (run_id,),
        ).fetchall()]

    assert assistant_core == "ASSISTANT_V1"
    assert len(observations) == 2
    assert {row["tool_name"] for row in observations} == {"get_callback_delivery", "get_receiver_processing"}
    assert all(row["status"] == "OK" and row["attempt_run_id"] == run_id for row in observations)
    by_tool = {row["tool_name"]: json.loads(row["result_json"]) for row in observations}
    delivery_fact = by_tool["get_callback_delivery"]["facts"]
    receiver_fact = by_tool["get_receiver_processing"]["facts"]
    assert delivery_fact["event_id"] == receiver_fact["event_id"] == delivery["event_id"]
    assert delivery_fact["status"] == "ACKNOWLEDGED" and delivery_fact["receiver_http_status"] == 202
    assert receiver_fact["status"] == "QUEUED"
    assert set(business_write_counts.values()) == {0}

    budget_after = read_budget(db_path, EXPERIMENT_ID)
    assert budget_after["provider_used"] == 3  # Fixture model dispatches, not Provider HTTP.
    assert budget_after["mcp_used"] == 2
    assert budget_after["provider_used"] <= 16 and budget_after["mcp_used"] <= 10
    assert RUNNER.RESERVATION_USD_MICRO == 645_600
    assert os_env_provider_opt_in_disabled()

    historical_after = {str(path.relative_to(ROOT)): _file_digest(path) for path in historical_paths}
    assert historical_after == historical_before

    trace = {
        "record_type": "zero_cost_formal_worker_preview",
        "evidence_level": "DETERMINISTIC_FIXTURE_MODEL_PLUS_FORMAL_API_WORKER_MCP_DOMAIN",
        "experiment_id": EXPERIMENT_ID,
        "provider_http_requests": 0,
        "provider_opt_in": "disabled",
        "fixture_model_calls": model.calls,
        "run_status": run["status"],
        "campaign_model_dispatches_are_not_provider_http": True,
        "session_id": session_id, "task_id": task_id, "run_id": run_id,
        "message_id": message_id, "execution_core": assistant_core,
        "answer_message_id": answers[0]["message_id"],
        "answer_kind": answers[0].get("answer_kind"),
        "exact_frozen_input_sha256": hashlib.sha256(exact_user_input.encode("utf-8")).hexdigest(),
        "fixture_transport": setup["transport_trace"],
        "fixture_event_id": delivery["event_id"],
        "mcp_proposals": model.proposed_tools,
        "offered_read_only_tools": model.offered_names,
        "mcp_observations": observations,
        "assistant_sources": sources,
        "sources_current": sources["current"],
        "answer": answer,
        "campaign_budget": budget_after,
        "task_attempt_limits": configured,
        "task_active_deadline_ms": before_time["deadline_ms"],
        "business_write_counts": business_write_counts,
        "new_paid_execution_claim_created": False,
        "historical_artifact_hashes_unchanged": historical_after,
        "assistant_calls": raw_calls,
    }
    print("RECOVERY_PREVIEW_TRACE=" + json.dumps(trace, ensure_ascii=False, sort_keys=True))
    assert trace["provider_http_requests"] == 0


def os_env_provider_opt_in_disabled() -> bool:
    import os

    return os.environ.get("OPSPILOT_ASSISTANT_PROVIDER_ENABLED") == "0"
