"""Pre-send per-scenario budget caps for the paired AR-03 live experiment."""

from __future__ import annotations

import pytest

from opspilot.domain.database import reset_fixture


EXPERIMENT_ID = "AR-03-REAL-LLM-01"


def _assistant_run(db_path, key: str):
    from opspilot.domain.task_control import (
        admit_task_message,
        create_session,
        trusted_identity,
    )

    actor = trusted_identity(db_path, "support-a")
    session = create_session(db_path, actor)["session_id"]
    return admit_task_message(
        db_path,
        actor,
        session_id=session,
        task_id=None,
        input_kind="CHAT_READONLY",
        body=f"AR-03 live budget fixture {key}",
        idempotency_key=key,
        assistant_core=True,
    )


def test_two_isolated_scenario_ledgers_enforce_half_caps_before_dispatch(
    demo_db, tmp_path,
):
    from opspilot.domain.assistant_experiment import (
        BUDGET_USD_MICRO,
        MAX_PROVIDER_RESERVATION_USD_MICRO,
        ExperimentBudgetError,
        initialize_experiment,
        read_budget,
        reserve_dispatch,
    )

    second_db = tmp_path / "scenario-b-domain.sqlite3"
    reset_fixture(second_db, "S1_POS")
    scenario_dbs = (demo_db, second_db)

    for db_path in scenario_dbs:
        initialize_experiment(db_path, EXPERIMENT_ID)
        snapshot = read_budget(db_path, EXPERIMENT_ID)
        assert snapshot["provider_limit"] == 8
        assert snapshot["mcp_limit"] == 6
        assert snapshot["budget_usd_micro"] == BUDGET_USD_MICRO == 10_500_000

        runs = [_assistant_run(db_path, f"paired-cap-{index}") for index in range(9)]
        for index, run in enumerate(runs[:8]):
            reserve_dispatch(
                db_path,
                experiment_id=EXPERIMENT_ID,
                run_id=run["run_id"],
                kind="MODEL",
                logical_key="model:0",
                request={"scenario": str(db_path), "index": index},
            )
        with pytest.raises(ExperimentBudgetError, match="AR02_LIVE_PROVIDER_LIMIT"):
            reserve_dispatch(
                db_path,
                experiment_id=EXPERIMENT_ID,
                run_id=runs[8]["run_id"],
                kind="MODEL",
                logical_key="model:0",
                request={"scenario": str(db_path), "index": 8},
            )

        for index, run in enumerate(runs[:6]):
            reserve_dispatch(
                db_path,
                experiment_id=EXPERIMENT_ID,
                run_id=run["run_id"],
                kind="MCP",
                logical_key="mcp:0",
                request={"scenario": str(db_path), "index": index},
            )
        with pytest.raises(ExperimentBudgetError, match="AR02_LIVE_MCP_LIMIT"):
            reserve_dispatch(
                db_path,
                experiment_id=EXPERIMENT_ID,
                run_id=runs[6]["run_id"],
                kind="MCP",
                logical_key="mcp:0",
                request={"scenario": str(db_path), "index": 6},
            )

        snapshot = read_budget(db_path, EXPERIMENT_ID)
        assert snapshot["provider_used"] == 8
        assert snapshot["mcp_used"] == 6
        assert snapshot["usd_reserved_micro"] == 8 * MAX_PROVIDER_RESERVATION_USD_MICRO

    total_provider_reserved = sum(
        read_budget(db_path, EXPERIMENT_ID)["usd_reserved_micro"]
        for db_path in scenario_dbs
    )
    assert total_provider_reserved == 16 * MAX_PROVIDER_RESERVATION_USD_MICRO
    assert total_provider_reserved == 10_329_600
    assert total_provider_reserved <= 10_500_000
