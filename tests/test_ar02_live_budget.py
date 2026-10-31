"""P0 contract tests for the isolated AR-02-LIVE-01 campaign budget."""

from __future__ import annotations

import asyncio
import time
from concurrent.futures import ThreadPoolExecutor

import pytest


EXPERIMENT_ID = "AR-02-LIVE-01"


def _assistant_run(db_path, key: str, *, session_id: str | None = None):
    from opspilot.domain.task_control import (
        admit_task_message,
        create_session,
        trusted_identity,
    )

    actor = trusted_identity(db_path, "support-a")
    current_session = session_id or create_session(db_path, actor)["session_id"]
    return admit_task_message(
        db_path,
        actor,
        session_id=current_session,
        task_id=None,
        input_kind="CHAT_READONLY",
        body=f"AR-02 live budget fixture {key}",
        idempotency_key=key,
        assistant_core=True,
    )


def test_real_provider_requires_explicit_live_experiment_scope(monkeypatch):
    from opspilot.assistant import create_assistant_model

    monkeypatch.setenv("OPSPILOT_ASSISTANT_PROVIDER_ENABLED", "1")
    monkeypatch.setenv("OPSPILOT_MODEL_API_KEY", "test-only-not-a-real-key")
    monkeypatch.setenv("OPSPILOT_MODEL_NAME", "deepseek-flash")
    monkeypatch.setenv("OPSPILOT_MODEL_BASE_URL", "https://api.deepseek.com")
    monkeypatch.delenv("OPSPILOT_ASSISTANT_EXPERIMENT_ID", raising=False)

    with pytest.raises(RuntimeError, match="AR02_LIVE_EXPERIMENT_SCOPE_REQUIRED"):
        create_assistant_model()


def test_real_provider_requires_frozen_model_id(monkeypatch):
    from opspilot.assistant import create_assistant_model

    monkeypatch.setenv("OPSPILOT_ASSISTANT_PROVIDER_ENABLED", "1")
    monkeypatch.setenv("OPSPILOT_ASSISTANT_EXPERIMENT_ID", EXPERIMENT_ID)
    monkeypatch.setenv("OPSPILOT_MODEL_API_KEY", "test-only-not-a-real-key")
    monkeypatch.setenv("OPSPILOT_MODEL_NAME", "some-other-model")
    monkeypatch.setenv("OPSPILOT_MODEL_BASE_URL", "https://example.invalid/v1")

    with pytest.raises(RuntimeError, match="AR02_LIVE_MODEL_CONFIGURATION_MISMATCH"):
        create_assistant_model()


def test_deepseek_factory_pins_nonthinking_max_tokens_and_no_retries(monkeypatch):
    from opspilot.assistant import create_assistant_model

    monkeypatch.setenv("OPSPILOT_ASSISTANT_PROVIDER_ENABLED", "1")
    monkeypatch.setenv("OPSPILOT_ASSISTANT_EXPERIMENT_ID", EXPERIMENT_ID)
    monkeypatch.setenv("OPSPILOT_MODEL_API_KEY", "test-only-not-a-real-key")
    monkeypatch.setenv("OPSPILOT_MODEL_NAME", "deepseek-flash")
    monkeypatch.setenv("OPSPILOT_MODEL_BASE_URL", "https://api.deepseek.com")

    model = create_assistant_model()

    assert model.model_name == "deepseek-flash"
    assert model.extra_body == {
        "max_tokens": 2048,
        "thinking": {"type": "disabled"},
    }
    assert model.request_timeout == 30
    assert model.max_retries == 0


def test_real_provider_endpoint_must_be_official_https(monkeypatch):
    from opspilot.assistant import create_assistant_model

    monkeypatch.setenv("OPSPILOT_ASSISTANT_PROVIDER_ENABLED", "1")
    monkeypatch.setenv("OPSPILOT_ASSISTANT_EXPERIMENT_ID", EXPERIMENT_ID)
    monkeypatch.setenv("OPSPILOT_MODEL_API_KEY", "test-only-not-a-real-key")
    monkeypatch.setenv("OPSPILOT_MODEL_NAME", "deepseek-flash")
    monkeypatch.setenv("OPSPILOT_MODEL_BASE_URL", "https://proxy.example.invalid:9443/v1")

    with pytest.raises(RuntimeError, match="AR02_LIVE_PROVIDER_ENDPOINT_MISMATCH"):
        create_assistant_model()


def test_experiment_budget_uses_one_persistent_scope_and_usage_settlement(demo_db):
    from opspilot.domain.database import connect
    from opspilot.domain.assistant_experiment import (
        complete_dispatch,
        initialize_experiment,
        read_budget,
        reserve_dispatch,
    )

    initialize_experiment(demo_db, EXPERIMENT_ID)
    with connect(demo_db) as connection:
        version_before = connection.execute("PRAGMA user_version").fetchone()[0]
    first = _assistant_run(demo_db, "budget-first")
    second = _assistant_run(demo_db, "budget-second")

    model_reservation = reserve_dispatch(
        demo_db,
        experiment_id=EXPERIMENT_ID,
        run_id=first["run_id"],
        kind="MODEL",
        logical_key="model:0",
        request={"digest_only": "fixture-model-request"},
    )
    complete_dispatch(
        demo_db,
        experiment_id=EXPERIMENT_ID,
        run_id=first["run_id"],
        kind="MODEL",
        logical_key="model:0",
        usage={"input_tokens": 10, "output_tokens": 5, "total_tokens": 15},
    )
    replay = reserve_dispatch(
        demo_db,
        experiment_id=EXPERIMENT_ID,
        run_id=first["run_id"],
        kind="MODEL",
        logical_key="model:0",
        request={"digest_only": "fixture-model-request"},
    )
    assert replay["dispatch"] is False and replay["replay"] is True
    mcp_reservation = reserve_dispatch(
        demo_db,
        experiment_id=EXPERIMENT_ID,
        run_id=second["run_id"],
        kind="MCP",
        logical_key="mcp:0",
        request={"tool": "search_project_knowledge", "args": {"query": "202"}},
    )
    complete_dispatch(
        demo_db,
        experiment_id=EXPERIMENT_ID,
        run_id=second["run_id"],
        kind="MCP",
        logical_key="mcp:0",
    )

    assert model_reservation["dispatch"] is True
    assert mcp_reservation["dispatch"] is True
    snapshot = read_budget(demo_db, EXPERIMENT_ID)
    assert snapshot["provider_used"] == 1
    assert snapshot["mcp_used"] == 1
    assert snapshot["usd_settled_micro"] == 9
    assert snapshot["usd_reserved_micro"] == 0
    with connect(demo_db) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == version_before


def test_unknown_provider_result_keeps_reserve_and_rejects_replay_after_reopen(demo_db):
    from opspilot.domain.assistant_experiment import (
        ExperimentBudgetError,
        initialize_experiment,
        mark_unknown,
        read_budget,
        reserve_dispatch,
    )

    initialize_experiment(demo_db, EXPERIMENT_ID)
    run = _assistant_run(demo_db, "unknown-provider")
    request = {"digest_only": "same-request"}
    reserve_dispatch(
        demo_db,
        experiment_id=EXPERIMENT_ID,
        run_id=run["run_id"],
        kind="MODEL",
        logical_key="model:0",
        request=request,
    )
    mark_unknown(
        demo_db,
        experiment_id=EXPERIMENT_ID,
        run_id=run["run_id"],
        kind="MODEL",
        logical_key="model:0",
        error_code="SimulatedResponseLoss",
    )

    with pytest.raises(ExperimentBudgetError, match="AR02_LIVE_CALL_OUTCOME_UNKNOWN"):
        reserve_dispatch(
            demo_db,
            experiment_id=EXPERIMENT_ID,
            run_id=run["run_id"],
            kind="MODEL",
            logical_key="model:0",
            request=request,
        )
    with pytest.raises(ExperimentBudgetError, match="AR02_LIVE_IDEMPOTENCY_CONFLICT"):
        reserve_dispatch(
            demo_db,
            experiment_id=EXPERIMENT_ID,
            run_id=run["run_id"],
            kind="MODEL",
            logical_key="model:0",
            request={"digest_only": "different-request"},
        )

    snapshot = read_budget(demo_db, EXPERIMENT_ID)
    assert snapshot["provider_used"] == 1
    assert snapshot["usd_reserved_micro"] == 645_600


def test_fixed_budget_covers_all_sixteen_documented_max_reservations(demo_db):
    from opspilot.domain.assistant_experiment import (
        ExperimentBudgetError,
        initialize_experiment,
        read_budget,
        reserve_dispatch,
    )

    initialize_experiment(demo_db, EXPERIMENT_ID)
    runs = [_assistant_run(demo_db, f"unknown-cap-{index}") for index in range(17)]
    for index, run in enumerate(runs[:16]):
        reservation = reserve_dispatch(
            demo_db,
            experiment_id=EXPERIMENT_ID,
            run_id=run["run_id"],
            kind="MODEL",
            logical_key="model:0",
            request={"index": index},
        )
        assert reservation["dispatch"] is True

    with pytest.raises(ExperimentBudgetError, match="AR02_LIVE_PROVIDER_LIMIT"):
        reserve_dispatch(
            demo_db,
            experiment_id=EXPERIMENT_ID,
            run_id=runs[16]["run_id"],
            kind="MODEL",
            logical_key="model:0",
            request={"index": 16},
        )

    snapshot = read_budget(demo_db, EXPERIMENT_ID)
    assert snapshot["provider_used"] == 16
    assert snapshot["usd_reserved_micro"] == 10_329_600
    assert snapshot["usd_remaining_micro"] == 170_400


def test_usd_ceiling_refuses_before_reserving_when_headroom_is_too_small(demo_db, monkeypatch):
    import opspilot.domain.assistant_experiment as experiment

    monkeypatch.setattr(experiment, "BUDGET_USD_MICRO", 5_000_000)
    experiment.initialize_experiment(demo_db, EXPERIMENT_ID)
    runs = [_assistant_run(demo_db, f"usd-limit-{index}") for index in range(8)]
    for index, run in enumerate(runs[:7]):
        reservation = experiment.reserve_dispatch(
            demo_db, experiment_id=EXPERIMENT_ID, run_id=run["run_id"],
            kind="MODEL", logical_key="model:0", request={"index": index},
        )
        assert reservation["dispatch"] is True
    with pytest.raises(experiment.ExperimentBudgetError, match="AR02_LIVE_USD_LIMIT"):
        experiment.reserve_dispatch(
            demo_db, experiment_id=EXPERIMENT_ID, run_id=runs[7]["run_id"],
            kind="MODEL", logical_key="model:0", request={"index": 7},
        )


def test_provider_and_mcp_count_limits_are_experiment_wide(demo_db):
    from opspilot.domain.assistant_experiment import (
        ExperimentBudgetError,
        complete_dispatch,
        initialize_experiment,
        reserve_dispatch,
    )

    initialize_experiment(demo_db, EXPERIMENT_ID)
    runs = [_assistant_run(demo_db, f"count-limit-{index}") for index in range(17)]
    for index, run in enumerate(runs[:16]):
        reserve_dispatch(
            demo_db,
            experiment_id=EXPERIMENT_ID,
            run_id=run["run_id"],
            kind="MODEL",
            logical_key="model:0",
            request={"index": index},
        )
        complete_dispatch(
            demo_db,
            experiment_id=EXPERIMENT_ID,
            run_id=run["run_id"],
            kind="MODEL",
            logical_key="model:0",
            usage={"input_tokens": 1, "output_tokens": 1, "total_tokens": 2},
        )
    with pytest.raises(ExperimentBudgetError, match="AR02_LIVE_PROVIDER_LIMIT"):
        reserve_dispatch(
            demo_db,
            experiment_id=EXPERIMENT_ID,
            run_id=runs[16]["run_id"],
            kind="MODEL",
            logical_key="model:0",
            request={"index": 16},
        )

    # MCP has no token cost, so its independent hard count can reach 12.
    for index, run in enumerate(runs[:12]):
        reserve_dispatch(
            demo_db,
            experiment_id=EXPERIMENT_ID,
            run_id=run["run_id"],
            kind="MCP",
            logical_key="mcp:0",
            request={"index": index},
        )
        complete_dispatch(
            demo_db,
            experiment_id=EXPERIMENT_ID,
            run_id=run["run_id"],
            kind="MCP",
            logical_key="mcp:0",
        )
    with pytest.raises(ExperimentBudgetError, match="AR02_LIVE_MCP_LIMIT"):
        reserve_dispatch(
            demo_db,
            experiment_id=EXPERIMENT_ID,
            run_id=runs[12]["run_id"],
            kind="MCP",
            logical_key="mcp:0",
            request={"index": 12},
        )


def test_missing_usage_keeps_full_provider_reservation(demo_db):
    from opspilot.domain.assistant_experiment import (
        complete_dispatch,
        initialize_experiment,
        read_budget,
        reserve_dispatch,
    )

    initialize_experiment(demo_db, EXPERIMENT_ID)
    run = _assistant_run(demo_db, "missing-provider-usage")
    reserve_dispatch(
        demo_db,
        experiment_id=EXPERIMENT_ID,
        run_id=run["run_id"],
        kind="MODEL",
        logical_key="model:missing-usage",
        request={"request": "local fixture only"},
    )
    completed = complete_dispatch(
        demo_db,
        experiment_id=EXPERIMENT_ID,
        run_id=run["run_id"],
        kind="MODEL",
        logical_key="model:missing-usage",
        usage=None,
    )

    assert completed["usage_state"] == "UNKNOWN"
    snapshot = read_budget(demo_db, EXPERIMENT_ID)
    assert snapshot["provider_used"] == 1
    assert snapshot["usd_reserved_micro"] == 645_600
    assert snapshot["usd_settled_micro"] == 0


def test_provider_usage_over_requested_cap_closes_campaign(demo_db):
    from opspilot.domain.assistant_experiment import (
        ExperimentBudgetError,
        complete_dispatch,
        initialize_experiment,
        read_budget,
        reserve_dispatch,
    )

    initialize_experiment(demo_db, EXPERIMENT_ID)
    first = _assistant_run(demo_db, "provider-over-cap")
    second = _assistant_run(demo_db, "provider-after-over-cap")
    reserve_dispatch(
        demo_db,
        experiment_id=EXPERIMENT_ID,
        run_id=first["run_id"],
        kind="MODEL",
        logical_key="model:over-cap",
        request={"request": "local fixture only"},
    )
    completed = complete_dispatch(
        demo_db,
        experiment_id=EXPERIMENT_ID,
        run_id=first["run_id"],
        kind="MODEL",
        logical_key="model:over-cap",
        usage={"input_tokens": 8, "output_tokens": 2049, "total_tokens": 2057},
    )

    assert completed["usage_state"] == "VIOLATION"
    assert read_budget(demo_db, EXPERIMENT_ID)["status"] == "BUDGET_BREACH"
    with pytest.raises(ExperimentBudgetError, match="AR02_LIVE_SPEND_BOUND_BREACHED"):
        reserve_dispatch(
            demo_db,
            experiment_id=EXPERIMENT_ID,
            run_id=second["run_id"],
            kind="MODEL",
            logical_key="model:after-over-cap",
            request={"request": "must not send"},
        )


def test_standard_app_start_does_not_create_experiment_ledger(demo_db, tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from opspilot.domain.database import connect
    from opspilot.web.app import create_app

    monkeypatch.delenv("OPSPILOT_ASSISTANT_EXPERIMENT_ID", raising=False)
    app = create_app(
        db_path=demo_db,
        checkpoint_db_path=tmp_path / "ordinary-checkpoint.sqlite3",
        start_worker=False,
    )
    with TestClient(app):
        with connect(demo_db) as connection:
            tables = {
                row["name"]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
            assert "ar02_live_experiment_budgets" not in tables
            assert "ar02_live_dispatches" not in tables


def test_app_rejects_non_frozen_experiment_scope(demo_db, tmp_path, monkeypatch):
    from opspilot.web.app import create_app

    monkeypatch.delenv("OPSPILOT_ASSISTANT_EXPERIMENT_ID", raising=False)
    with pytest.raises(ValueError, match="AR02_LIVE_EXPERIMENT_SCOPE_INVALID"):
        create_app(
            db_path=demo_db,
            checkpoint_db_path=tmp_path / "unrecognized-checkpoint.sqlite3",
            start_worker=False,
            assistant_experiment_id="AR-02-UNAPPROVED",
        )


@pytest.mark.parametrize(
    ("limited_kind", "fixture_mode", "expected_status", "expected_model_dispatches"),
    [
        ("PROVIDER_LIMIT", "concept", "FAILED", 0),
        ("MCP_LIMIT", "knowledge", "SUCCEEDED", 2),
    ],
)
def test_formal_worker_quota_refusal_precedes_external_dispatch(
    demo_db, tmp_path, monkeypatch, limited_kind, fixture_mode, expected_status,
    expected_model_dispatches,
):
    from fastapi.testclient import TestClient

    import opspilot.domain.assistant_experiment as experiment
    from opspilot.domain.assistant_experiment import read_budget
    from opspilot.web.app import create_app
    from test_ar02_assistant import ORIGIN, PASSWORDS
    from test_ar02_runtime import FixtureModel

    monkeypatch.setattr(experiment, limited_kind, 0)
    model = FixtureModel(mode=fixture_mode)
    app = create_app(
        db_path=demo_db,
        checkpoint_db_path=tmp_path / "limited-checkpoint.sqlite3",
        start_worker=True,
        credentials=PASSWORDS,
        expected_origin=ORIGIN,
        assistant_experiment_id=EXPERIMENT_ID,
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
            headers={**headers, "Idempotency-Key": f"limited-{limited_kind}"},
            json={"body": "请解释 HTTP 202 与回调处理完成的区别。"},
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
        assert run["status"] == expected_status, run

    assert len(model.seen) == expected_model_dispatches
    snapshot = read_budget(demo_db, EXPERIMENT_ID)
    assert snapshot["provider_used"] == expected_model_dispatches
    assert snapshot["mcp_used"] == 0


def test_separate_sqlite_connections_cannot_exceed_campaign_counts(demo_db):
    from opspilot.domain.assistant_experiment import (
        ExperimentBudgetError,
        complete_dispatch,
        initialize_experiment,
        reserve_dispatch,
    )

    initialize_experiment(demo_db, EXPERIMENT_ID)
    runs = [_assistant_run(demo_db, f"parallel-{index}") for index in range(24)]

    def provider_call(index: int) -> bool:
        run = runs[index]
        try:
            reserve_dispatch(
                demo_db,
                experiment_id=EXPERIMENT_ID,
                run_id=run["run_id"],
                kind="MODEL",
                logical_key="model:0",
                request={"index": index},
            )
            complete_dispatch(
                demo_db,
                experiment_id=EXPERIMENT_ID,
                run_id=run["run_id"],
                kind="MODEL",
                logical_key="model:0",
                usage={"input_tokens": 1, "output_tokens": 1, "total_tokens": 2},
            )
            return True
        except ExperimentBudgetError:
            return False

    with ThreadPoolExecutor(max_workers=8) as pool:
        provider_results = list(pool.map(provider_call, range(24)))
    assert sum(provider_results) == 16

    def mcp_call(index: int) -> bool:
        run = runs[index]
        try:
            reserve_dispatch(
                demo_db,
                experiment_id=EXPERIMENT_ID,
                run_id=run["run_id"],
                kind="MCP",
                logical_key="mcp:0",
                request={"index": index},
            )
            complete_dispatch(
                demo_db,
                experiment_id=EXPERIMENT_ID,
                run_id=run["run_id"],
                kind="MCP",
                logical_key="mcp:0",
            )
            return True
        except ExperimentBudgetError:
            return False

    with ThreadPoolExecutor(max_workers=8) as pool:
        mcp_results = list(pool.map(mcp_call, range(24)))
    assert sum(mcp_results) == 12


def test_live_budget_is_used_by_formal_api_worker_across_sessions(demo_db, tmp_path):
    from fastapi.testclient import TestClient

    from opspilot.domain.assistant_experiment import EXPERIMENT_ID as LIVE_ID, read_budget
    from opspilot.domain.database import connect
    from opspilot.web.app import create_app
    from test_ar02_assistant import ORIGIN, PASSWORDS
    from test_ar02_runtime import FixtureModel

    models = iter((FixtureModel(mode="knowledge"), FixtureModel(mode="concept")))
    app = create_app(
        db_path=demo_db,
        checkpoint_db_path=tmp_path / "worker-checkpoint.sqlite3",
        start_worker=True,
        credentials=PASSWORDS,
        expected_origin=ORIGIN,
        assistant_experiment_id=LIVE_ID,
        assistant_model_factory=lambda: next(models),
    )
    with TestClient(app) as client:
        csrf = client.post(
            "/api/auth/login",
            headers={"Origin": ORIGIN},
            json={"actor_id": "support-a", "password": PASSWORDS["support-a"]},
        ).json()["csrf_token"]
        headers = {"Origin": ORIGIN, "X-CSRF-Token": csrf}
        accepted = []
        for index, prompt in enumerate((
            "HTTP 202 Accepted 是否意味着订单回调已经处理完成？请区分 HTTP/协议语义和当前订单事实。我没有提供订单、Event 或 Receiver 的当前状态。",
            "请查询授权资料并解释回调协议版本与来源。",
        )):
            session_id = client.post("/api/sessions", headers=headers).json()["session_id"]
            response = client.post(
                f"/api/sessions/{session_id}/assistant/messages",
                headers={**headers, "Idempotency-Key": f"live-budget-{index}"},
                json={"body": prompt},
            )
            assert response.status_code == 202, response.text
            value = response.json()
            accepted.append((session_id, value))
            deadline = time.monotonic() + 12
            while True:
                run = client.get(f"/api/runs/{value['run_id']}").json()
                if run["status"] in ("SUCCEEDED", "FAILED", "BLOCKED"):
                    break
                assert time.monotonic() < deadline, run
                time.sleep(0.05)
            assert run["status"] == "SUCCEEDED", run

        snapshot = read_budget(demo_db, LIVE_ID)
        # The first deterministic model asks Knowledge, then answers; the
        # second answers directly. Count the real formal Worker dispatches.
        assert snapshot["provider_used"] == 3
        assert snapshot["mcp_used"] == 1
        for session_id, value in accepted:
            messages = client.get(f"/api/sessions/{session_id}/messages").json()["items"]
            answers = [item for item in messages if item["role"] == "ASSISTANT"]
            assert len(answers) == 1
            assert answers[0]["answer_source_message_id"] == value["message_id"]

        with connect(demo_db) as connection:
            assert connection.execute(
                "SELECT COUNT(*) FROM assistant_calls WHERE kind='MODEL'"
            ).fetchone()[0] == snapshot["provider_used"]
            assert connection.execute(
                "SELECT COUNT(*) FROM assistant_calls WHERE kind='MCP'"
            ).fetchone()[0] == snapshot["mcp_used"]
            assert connection.execute("SELECT COUNT(*) FROM s3_diagnoses").fetchone()[0] == 0
            assert connection.execute("SELECT COUNT(*) FROM s3_handoff_receipts").fetchone()[0] == 0
            assert connection.execute("SELECT COUNT(*) FROM d3_action_intents").fetchone()[0] == 0
