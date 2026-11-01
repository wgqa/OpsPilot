"""Prepaid HF01 regressions: durable stop after unaccounted Provider outcomes."""

from __future__ import annotations

import asyncio
import hashlib

import pytest
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult


EXPERIMENT_ID = "AR-02-REAL-JOURNEY-01"


def _new_run(db_path, key: str, *, task_binding: bool = False):
    from opspilot.domain.s3 import prepare_s3_fixture
    from opspilot.domain.task_control import (
        create_session,
        create_task_with_initial_run,
        trusted_identity,
        admit_task_message,
    )

    identity = trusted_identity(db_path, "support-a")
    session_id = create_session(db_path, identity)["session_id"]
    if task_binding:
        fixture_suffix = hashlib.sha256(key.encode("utf-8")).hexdigest()[:12]
        order_id = f"hf01-{fixture_suffix}"
        prepare_s3_fixture(db_path, "PROCESSING", order_id=order_id, contract_version=2)
        return create_task_with_initial_run(
            db_path,
            identity,
            session_id=session_id,
            service_id="orders-async-demo",
            integration_id="async-integration-a",
            ticket_id=f"INC-{fixture_suffix}",
            s3_order_id=order_id,
            initial_message="核查当前绑定订单。",
            idempotency_key=f"hf01-{key}",
            assistant_core=True,
        )
    return admit_task_message(
        db_path,
        identity,
        session_id=session_id,
        task_id=None,
        input_kind="CHAT_READONLY",
        body=f"HF01 isolated campaign run {key}",
        idempotency_key=key,
        assistant_core=True,
    )


def _claim(db_path, run_id: str, worker_id: str):
    import os

    from opspilot.domain.task_control import claim_task_run, register_worker_owner, trusted_identity

    register_worker_owner(db_path, worker_id, os.getpid())
    claim_task_run(db_path, trusted_identity(db_path, "support-a"), run_id)


class ToolCallModel(BaseChatModel):
    usage: dict | None = None
    calls: int = 0

    @property
    def _llm_type(self) -> str:
        return "PREPAID_HF01_DETERMINISTIC_TOOL_CALL"

    def bind_tools(self, tools, **kwargs):
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        self.calls += 1
        message = AIMessage(
            content="",
            tool_calls=[{
                "name": "get_order_status",
                "args": {"reason": "check the trusted order binding"},
                "id": f"hf01-tool-{self.calls}",
            }],
            usage_metadata=self.usage,
        )
        return ChatResult(generations=[ChatGeneration(message=message)])


def test_valid_usage_keeps_campaign_open_for_next_legal_dispatch(demo_db):
    from opspilot.domain.assistant_experiment import (
        complete_dispatch,
        initialize_experiment,
        read_budget,
        reserve_dispatch,
    )

    initialize_experiment(demo_db, EXPERIMENT_ID)
    first = _new_run(demo_db, "valid-first")
    second = _new_run(demo_db, "valid-second")
    reserve_dispatch(
        demo_db, experiment_id=EXPERIMENT_ID, run_id=first["run_id"], kind="MODEL",
        logical_key="model:0", request={"prompt": "first"},
    )
    settled = complete_dispatch(
        demo_db, experiment_id=EXPERIMENT_ID, run_id=first["run_id"], kind="MODEL",
        logical_key="model:0", usage={"input_tokens": 10, "output_tokens": 5, "total_tokens": 15},
    )

    assert settled["usage_state"] == "KNOWN"
    next_call = reserve_dispatch(
        demo_db, experiment_id=EXPERIMENT_ID, run_id=second["run_id"], kind="MODEL",
        logical_key="model:0", request={"prompt": "next legal step"},
    )
    assert next_call["dispatch"] is True
    assert read_budget(demo_db, EXPERIMENT_ID)["status"] == "OPEN"


@pytest.mark.parametrize(
    "usage",
    [
        None,
        {"input_tokens": 2, "output_tokens": "bad", "total_tokens": 2},
        {"input_tokens": True, "output_tokens": 2, "total_tokens": 3},
    ],
    ids=["missing", "malformed-output", "boolean-input"],
)
def test_unknown_usage_closes_campaign_and_preserves_reservation(demo_db, usage):
    from opspilot.domain.assistant_experiment import (
        ExperimentBudgetError,
        complete_dispatch,
        initialize_experiment,
        read_budget,
        reserve_dispatch,
    )

    initialize_experiment(demo_db, EXPERIMENT_ID)
    first = _new_run(demo_db, f"unknown-usage-{str(usage)}")
    other_run = _new_run(demo_db, f"after-unknown-usage-{str(usage)}")
    reserve_dispatch(
        demo_db, experiment_id=EXPERIMENT_ID, run_id=first["run_id"], kind="MODEL",
        logical_key="model:0", request={"prompt": "usage will be invalid"},
    )
    result = complete_dispatch(
        demo_db, experiment_id=EXPERIMENT_ID, run_id=first["run_id"], kind="MODEL",
        logical_key="model:0", usage=usage,
    )

    assert result["usage_state"] == "UNKNOWN"
    snapshot = read_budget(demo_db, EXPERIMENT_ID)
    assert snapshot["status"] == "BUDGET_BREACH"
    assert snapshot["usd_reserved_micro"] == 645_600
    assert snapshot["usd_settled_micro"] == 0
    with pytest.raises(ExperimentBudgetError, match="AR02_LIVE_SPEND_BOUND_BREACHED"):
        reserve_dispatch(
            demo_db, experiment_id=EXPERIMENT_ID, run_id=other_run["run_id"], kind="MODEL",
            logical_key="new:model:key", request={"prompt": "must not send"},
        )
    with pytest.raises(ExperimentBudgetError, match="AR02_LIVE_SPEND_BOUND_BREACHED"):
        reserve_dispatch(
            demo_db, experiment_id=EXPERIMENT_ID, run_id=other_run["run_id"], kind="MCP",
            logical_key="new:mcp:key", request={"tool": "get_order_status"},
        )


def test_provider_unknown_is_a_durable_campaign_stop_after_reopen(demo_db):
    from opspilot.domain.assistant_experiment import (
        ExperimentBudgetError,
        initialize_experiment,
        mark_unknown,
        read_budget,
        reserve_dispatch,
    )

    initialize_experiment(demo_db, EXPERIMENT_ID)
    first = _new_run(demo_db, "response-lost")
    other_run = _new_run(demo_db, "response-lost-new-run")
    reserve_dispatch(
        demo_db, experiment_id=EXPERIMENT_ID, run_id=first["run_id"], kind="MODEL",
        logical_key="model:0", request={"prompt": "single authorized request"},
    )
    mark_unknown(
        demo_db, experiment_id=EXPERIMENT_ID, run_id=first["run_id"], kind="MODEL",
        logical_key="model:0", error_code="SimulatedTimeout",
    )

    # Each domain call opens a fresh SQLite connection, modeling worker restart.
    with pytest.raises(ExperimentBudgetError, match="AR02_LIVE_CALL_OUTCOME_UNKNOWN"):
        reserve_dispatch(
            demo_db, experiment_id=EXPERIMENT_ID, run_id=first["run_id"], kind="MODEL",
            logical_key="model:0", request={"prompt": "single authorized request"},
        )
    with pytest.raises(ExperimentBudgetError, match="AR02_LIVE_SPEND_BOUND_BREACHED"):
        reserve_dispatch(
            demo_db, experiment_id=EXPERIMENT_ID, run_id=other_run["run_id"], kind="MODEL",
            logical_key="new:logical:key", request={"prompt": "must not bypass unknown"},
        )
    snapshot = read_budget(demo_db, EXPERIMENT_ID)
    assert snapshot["status"] == "BUDGET_BREACH"
    assert snapshot["provider_used"] == 1
    assert snapshot["usd_reserved_micro"] == 645_600
    assert snapshot["usd_settled_micro"] == 0


@pytest.mark.parametrize(
    "usage",
    [None, {"input_tokens": 1, "output_tokens": 2049, "total_tokens": 2050}],
    ids=["unknown-usage", "usage-violation"],
)
def test_assistant_stops_before_tool_or_normal_answer_when_usage_not_known(
    demo_db, tmp_path, usage
):
    from opspilot.assistant import run_assistant
    from opspilot.domain.assistant_experiment import read_budget
    from opspilot.domain.database import connect
    from opspilot.domain.task_control import claim_task_run, register_worker_owner, trusted_identity

    created = _new_run(demo_db, f"assistant-abnormal-{usage}", task_binding=True)
    worker_id = f"hf01-worker-{created['run_id']}"
    register_worker_owner(demo_db, worker_id, __import__("os").getpid())
    claim_task_run(demo_db, trusted_identity(demo_db, "support-a"), created["run_id"])
    model = ToolCallModel(usage=usage)
    events = []
    result = asyncio.run(
        run_assistant(
            demo_db,
            tmp_path / f"{created['run_id']}-checkpoint.sqlite3",
            worker_id,
            created["run_id"],
            model=model,
            trace=lambda event, **values: events.append({"event": event, **values}),
            experiment_id=EXPERIMENT_ID,
        )
    )

    assert model.calls == 1
    assert result["status"] == "NOT_COMPLETED"
    assert not any(event["event"] == "tool_observation" for event in events)
    with connect(demo_db) as connection:
        calls = connection.execute(
            "SELECT kind, status FROM assistant_calls WHERE run_id=? ORDER BY kind",
            (created["run_id"],),
        ).fetchall()
        dispatch = connection.execute(
            "SELECT status, usage_state, reserved_usd_micro, settled_usd_micro "
            "FROM ar02_live_dispatches WHERE experiment_id=? AND run_id=?",
            (EXPERIMENT_ID, created["run_id"]),
        ).fetchall()
        answers = connection.execute(
            "SELECT COUNT(*) FROM chat_run_answers WHERE run_id=?", (created["run_id"],)
        ).fetchone()[0]
        observations = connection.execute(
            "SELECT COUNT(*) FROM d2_tool_observations WHERE task_id=?", (created["task_id"],)
        ).fetchone()[0]
        run_status = connection.execute(
            "SELECT status FROM task_runs WHERE run_id=?", (created["run_id"],)
        ).fetchone()[0]

    assert [(row["kind"], row["status"]) for row in calls] == [("MODEL", "FAILED")]
    assert len(dispatch) == 1
    assert dispatch[0]["status"] == "OK"
    assert dispatch[0]["usage_state"] == ("UNKNOWN" if usage is None else "VIOLATION")
    assert dispatch[0]["reserved_usd_micro"] == (645_600 if usage is None else 0)
    assert dispatch[0]["settled_usd_micro"] == (0 if usage is None else 20)
    assert answers == 0
    assert observations == 0
    assert run_status == "FAILED"
    assert read_budget(demo_db, EXPERIMENT_ID)["status"] == "BUDGET_BREACH"

    # A fresh Run must not reach the model handler after the campaign has stopped.
    later = _new_run(demo_db, f"after-assistant-abnormal-{usage}")
    later_worker = f"hf01-worker-{later['run_id']}"
    _claim(demo_db, later["run_id"], later_worker)
    blocked_model = ToolCallModel(usage={"input_tokens": 1, "output_tokens": 1, "total_tokens": 2})
    blocked = asyncio.run(
        run_assistant(
            demo_db,
            tmp_path / f"{later['run_id']}-checkpoint.sqlite3",
            later_worker,
            later["run_id"],
            model=blocked_model,
            trace=lambda *_args, **_kwargs: None,
            experiment_id=EXPERIMENT_ID,
        )
    )
    assert blocked["status"] == "NOT_COMPLETED"
    assert blocked_model.calls == 0
