"""Frozen free checks for the isolated AR-02 real journey identity."""

from __future__ import annotations

import asyncio
import json

import httpx
import pytest


NEW_EXPERIMENT_ID = "AR-02-REAL-JOURNEY-01"
LEGACY_EXPERIMENT_ID = "AR-02-LIVE-01"


def _assistant_run(db_path, key: str):
    from opspilot.domain.task_control import (
        admit_task_message,
        create_session,
        trusted_identity,
    )

    actor = trusted_identity(db_path, "support-a")
    session_id = create_session(db_path, actor)["session_id"]
    return admit_task_message(
        db_path,
        actor,
        session_id=session_id,
        task_id=None,
        input_kind="CHAT_READONLY",
        body=f"AR-02 real journey budget fixture {key}",
        idempotency_key=key,
        assistant_core=True,
    )


def test_real_journey_has_independent_durable_budget_identity(demo_db):
    from opspilot.domain.assistant_experiment import (
        ExperimentBudgetError,
        initialize_experiment,
        mark_unknown,
        read_budget,
        reserve_dispatch,
    )

    initialize_experiment(demo_db, LEGACY_EXPERIMENT_ID)
    initialize_experiment(demo_db, NEW_EXPERIMENT_ID)
    legacy_run = _assistant_run(demo_db, "real-journey-legacy-budget")
    journey_run = _assistant_run(demo_db, "real-journey-new-budget")

    legacy = reserve_dispatch(
        demo_db,
        experiment_id=LEGACY_EXPERIMENT_ID,
        run_id=legacy_run["run_id"],
        kind="MODEL",
        logical_key="legacy-unknown",
        request={"prompt": "historical ledger fixture"},
    )
    mark_unknown(
        demo_db,
        experiment_id=LEGACY_EXPERIMENT_ID,
        run_id=legacy_run["run_id"],
        kind="MODEL",
        logical_key="legacy-unknown",
        error_code="LOCAL_TEST_UNKNOWN",
    )
    journey = reserve_dispatch(
        demo_db,
        experiment_id=NEW_EXPERIMENT_ID,
        run_id=journey_run["run_id"],
        kind="MODEL",
        logical_key="journey-first",
        request={"prompt": "isolated new experiment"},
    )
    journey_mcp = reserve_dispatch(
        demo_db,
        experiment_id=NEW_EXPERIMENT_ID,
        run_id=journey_run["run_id"],
        kind="MCP",
        logical_key="journey-mcp",
        request={"tool": "get_order_status", "arguments": {"reason": "test"}},
    )

    assert legacy["dispatch_id"] != journey["dispatch_id"]
    assert journey_mcp["reserved_usd_micro"] == 0
    assert read_budget(demo_db, LEGACY_EXPERIMENT_ID)["provider_used"] == 1
    assert read_budget(demo_db, LEGACY_EXPERIMENT_ID)["mcp_used"] == 0
    assert read_budget(demo_db, LEGACY_EXPERIMENT_ID)["usd_reserved_micro"] == 645600
    assert read_budget(demo_db, NEW_EXPERIMENT_ID)["provider_used"] == 1
    assert read_budget(demo_db, NEW_EXPERIMENT_ID)["mcp_used"] == 1
    assert read_budget(demo_db, NEW_EXPERIMENT_ID)["usd_reserved_micro"] == 645600
    with pytest.raises(ExperimentBudgetError, match="AR02_LIVE_CALL_OUTCOME_UNKNOWN"):
        reserve_dispatch(
            demo_db,
            experiment_id=LEGACY_EXPERIMENT_ID,
            run_id=legacy_run["run_id"],
            kind="MODEL",
            logical_key="legacy-unknown",
            request={"prompt": "historical ledger fixture"},
        )


def test_new_experiment_provider_factory_remains_opt_in_and_mock_only(monkeypatch):
    from opspilot.assistant import create_assistant_model

    monkeypatch.delenv("OPSPILOT_ASSISTANT_PROVIDER_ENABLED", raising=False)
    monkeypatch.setenv("OPSPILOT_ASSISTANT_EXPERIMENT_ID", NEW_EXPERIMENT_ID)
    monkeypatch.setenv("OPSPILOT_MODEL_API_KEY", "test-only-not-a-real-key")
    monkeypatch.setenv("OPSPILOT_MODEL_NAME", "deepseek-flash")
    monkeypatch.setenv("OPSPILOT_MODEL_BASE_URL", "https://api.deepseek.com")
    assert create_assistant_model() is None

    monkeypatch.setenv("OPSPILOT_ASSISTANT_PROVIDER_ENABLED", "1")
    model = create_assistant_model(
        transport_async=httpx.MockTransport(lambda request: httpx.Response(500)),
        transport_sync=httpx.MockTransport(lambda request: httpx.Response(500)),
    )
    try:
        assert model.model_name == "deepseek-flash"
        assert model.max_retries == 0
        assert model.request_timeout == 30
        assert model.extra_body == {
            "max_tokens": 2048,
            "thinking": {"type": "disabled"},
        }
        assert model.http_async_client.trust_env is False
        assert model.http_client.trust_env is False
    finally:
        asyncio.run(model.http_async_client.aclose())
        model.http_client.close()


def test_formal_app_initializes_new_identity_without_provider_io(
    demo_db, tmp_path, monkeypatch
):
    from fastapi.testclient import TestClient

    from opspilot.domain.assistant_experiment import read_budget
    from opspilot.web.app import create_app

    monkeypatch.delenv("OPSPILOT_ASSISTANT_EXPERIMENT_ID", raising=False)
    monkeypatch.delenv("OPSPILOT_ASSISTANT_PROVIDER_ENABLED", raising=False)
    app = create_app(
        db_path=demo_db,
        checkpoint_db_path=tmp_path / "real-journey-checkpoint.sqlite3",
        start_worker=False,
        assistant_experiment_id=NEW_EXPERIMENT_ID,
        assistant_model_factory=lambda: None,
    )
    with TestClient(app):
        assert app.state.assistant_experiment_id == NEW_EXPERIMENT_ID
        snapshot = read_budget(demo_db, NEW_EXPERIMENT_ID)
        assert snapshot["initialized"] is True
        assert snapshot["provider_limit"] == 16
        assert snapshot["mcp_limit"] == 12
        assert snapshot["budget_usd_micro"] == 10_500_000


def test_formal_worker_uses_new_budget_identity_with_deterministic_model(
    demo_db, tmp_path, monkeypatch
):
    import time

    from fastapi.testclient import TestClient

    from opspilot.domain.assistant_experiment import read_budget
    from opspilot.web.app import create_app
    from test_ar02_assistant import ORIGIN, PASSWORDS
    from test_ar02_runtime import FixtureModel

    monkeypatch.delenv("OPSPILOT_ASSISTANT_PROVIDER_ENABLED", raising=False)
    monkeypatch.delenv("OPSPILOT_ASSISTANT_EXPERIMENT_ID", raising=False)
    model = FixtureModel(mode="concept")
    app = create_app(
        db_path=demo_db,
        checkpoint_db_path=tmp_path / "real-journey-worker-checkpoint.sqlite3",
        start_worker=True,
        credentials=PASSWORDS,
        expected_origin=ORIGIN,
        assistant_experiment_id=NEW_EXPERIMENT_ID,
        assistant_model_factory=lambda: model,
    )
    with TestClient(app) as client:
        csrf = client.post(
            "/api/auth/login",
            headers={"Origin": ORIGIN},
            json={"actor_id": "support-a", "password": PASSWORDS["support-a"]},
        ).json()["csrf_token"]
        headers = {"Origin": ORIGIN, "X-CSRF-Token": csrf}
        session_id = client.post("/api/sessions", headers=headers).json()["session_id"]
        accepted = client.post(
            f"/api/sessions/{session_id}/assistant/messages",
            headers={**headers, "Idempotency-Key": "real-journey-formal-worker"},
            json={"body": "请解释 HTTP 202 不代表接收方已经完成处理。"},
        )
        assert accepted.status_code == 202, accepted.text
        run_id = accepted.json()["run_id"]
        deadline = time.monotonic() + 12
        while True:
            run = client.get(f"/api/runs/{run_id}").json()
            if run["status"] in {"SUCCEEDED", "FAILED", "BLOCKED"}:
                break
            assert time.monotonic() < deadline, run
            time.sleep(0.05)
        assert run["status"] == "SUCCEEDED", run
        messages = client.get(f"/api/sessions/{session_id}/messages").json()["items"]
        answers = [
            row
            for row in messages
            if row["role"] == "ASSISTANT" and "HTTP 202" in row["body"]
        ]
        assert answers

    snapshot = read_budget(demo_db, NEW_EXPERIMENT_ID)
    assert snapshot["provider_used"] == 1
    assert snapshot["mcp_used"] == 0
    print(
        "LOCAL_FORMAL_WORKER_TRACE="
        + json.dumps(
            {
                "model_source": "deterministic_FixtureModel",
                "provider_network_requests": 0,
                "acceptance_http_status": accepted.status_code,
                "session_id": session_id,
                "source_message_id": accepted.json()["message_id"],
                "run_id": run_id,
                "run_status": run["status"],
                "assistant_message_id": answers[0]["message_id"],
                "assistant_answer": answers[0]["body"],
                "assistant_answer_source_message_id": answers[0].get(
                    "answer_source_message_id"
                ),
                "experiment_id": NEW_EXPERIMENT_ID,
                "provider_dispatches": snapshot["provider_used"],
                "mcp_tools_call_attempts": snapshot["mcp_used"],
                "business_writes": 0,
            },
            sort_keys=True,
        )
    )


def test_legacy_database_schema_fails_closed_for_new_experiment_id(demo_db):
    from opspilot.domain.assistant_experiment import (
        ExperimentBudgetError,
        initialize_experiment,
    )
    from opspilot.domain.database import connect

    with connect(demo_db) as connection:
        connection.execute(
            """CREATE TABLE ar02_live_experiment_budgets (
                experiment_id TEXT PRIMARY KEY CHECK (experiment_id = 'AR-02-LIVE-01'),
                provider_limit INTEGER NOT NULL,
                mcp_limit INTEGER NOT NULL,
                budget_usd_micro INTEGER NOT NULL,
                price_version TEXT NOT NULL,
                status TEXT NOT NULL CHECK (status IN ('OPEN', 'BUDGET_BREACH')),
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )"""
        )

    initialize_experiment(demo_db, LEGACY_EXPERIMENT_ID)
    with pytest.raises(ExperimentBudgetError, match="AR02_LIVE_SCHEMA_ID_NOT_SUPPORTED"):
        initialize_experiment(demo_db, NEW_EXPERIMENT_ID)
