"""Targeted regressions for the offline R1 J2 closeout fixes."""
from __future__ import annotations

import asyncio
import copy
from types import SimpleNamespace

import pytest
from langchain_core.messages import HumanMessage, ToolMessage

from opspilot.assistant import Loop
from opspilot.domain import assistant as domain
from opspilot.domain.assistant import source_context_for_model
from opspilot.domain.context_engineering import ContextBudgetExceeded


def test_model_context_projects_current_observation_metadata_without_duplicate_payload():
    payload = {
        "authority": "EXPLANATION_ONLY_NO_BUSINESS_RECEIPT",
        "current_run": {
            "run_id": "run-current",
            "completed_tools": [
                {"tool": "get_callback_delivery", "call_id": "call-1", "completed_at": "2026-11-08T09:00:00Z"},
                {"tool": "get_receiver_processing", "call_id": "call-2", "completed_at": "2026-11-08T09:01:00Z"},
            ],
            "business_observations": [
                {
                    "tool": "get_callback_delivery", "call_id": "call-1",
                    "tool_call_id": "provider-call-1",
                    "evidence_id": "evidence-1", "observation_id": "observation-1",
                    "observed_at": "2026-11-08T09:00:00Z",
                    "observed_versions": {"order": 3, "delivery": 7, "contract": 2},
                    "result_digest": "a" * 64,
                },
                {
                    "tool": "get_receiver_processing", "call_id": "call-2",
                    "tool_call_id": "provider-call-2",
                    "evidence_id": "evidence-2", "observation_id": "observation-2",
                    "observed_at": "2026-11-08T09:01:00Z",
                    "observed_versions": {"order": 3, "delivery": 7, "receiver": 8},
                    "result_digest": "b" * 64,
                },
            ],
        },
        "history_sources": [
            {
                "run_id": "run-history",
                "current_source_valid": True,
                "exclusion_reason": None,
                "omitted_source_count": 0,
                "sources": [{
                    "call_id": "old-call", "evidence_id": "old-evidence",
                    "observation_id": "old-observation", "result_digest": "c" * 64,
                    "observed_at": "2026-11-07T09:00:00Z", "completed_at": "2026-11-07T09:00:01Z",
                    "summary": "历史快照：Receiver 曾为 QUEUED。",
                }],
            },
        ],
        "prior_answers": [], "task_id": "task-current", "source_message_id": "message-current",
        "summary_refs": [], "trusted_binding": {"service_id": "orders", "order_id": "order-a", "contract_version": 2},
    }
    original = copy.deepcopy(payload)

    projected = source_context_for_model(payload)

    current = projected["current_run"]
    assert current == {
        "run_id": "run-current",
        "description": "以下 2 条业务观察由本轮工具取得，只能对其实际覆盖的状态说本轮已查询。",
        "business_observations": [
            {
                "tool": "get_callback_delivery", "call_id": "call-1",
                "tool_call_id": "provider-call-1",
                "evidence_id": "evidence-1", "observation_id": "observation-1",
                "observed_at": "2026-11-08T09:00:00Z",
            },
            {
                "tool": "get_receiver_processing", "call_id": "call-2",
                "tool_call_id": "provider-call-2",
                "evidence_id": "evidence-2", "observation_id": "observation-2",
                "observed_at": "2026-11-08T09:01:00Z",
            },
        ],
    }
    historical = projected["history_sources"][0]
    assert historical["reference_scope"] == "HISTORICAL_SNAPSHOT_NOT_REQUERIED"
    assert historical["snapshots"][0]["reference"]["evidence_id"] == "old-evidence"
    assert historical["snapshots"][0]["reference"]["result_digest"] == "c" * 64
    assert payload == original


def test_next_oversized_tool_result_stops_before_persisted_model_reservation(monkeypatch):
    observations = [
        {
            "tool": f"read_fact_{index}", "call_id": f"call-{index}",
            "evidence_id": f"evidence-{index}", "observation_id": f"observation-{index}",
            "observed_at": f"2026-11-08T09:0{index}:00Z",
            "observed_versions": {"resource": index + 1}, "result_digest": f"{index}" * 64,
        }
        for index in range(1, 5)
    ]
    payload = {
        "authority": "EXPLANATION_ONLY_NO_BUSINESS_RECEIPT",
        "current_run": {
            "run_id": "run-budget-stop", "completed_tools": [],
            "business_observations": observations,
        },
        "history_sources": [], "prior_answers": [], "task_id": "task-budget-stop",
        "source_message_id": "message-budget-stop", "summary_refs": [],
        "trusted_binding": {"service_id": "orders", "order_id": "order-a", "contract_version": 2},
    }
    prepared = {
        "memory_guidance_messages": [], "summary_refs": [], "memory_refs": [],
        "excluded_sources": [], "selected_message_ids": [], "messages": [],
    }
    messages = [HumanMessage(content="核对同一订单内的当前事实，保留来源。")]
    messages.extend(
        ToolMessage(
            content='{"fixture_only":true,"fact":"bounded prior observation"}',
            tool_call_id=f"call-{index}", name=f"read_fact_{index}",
        )
        for index in range(1, 4)
    )
    messages.append(ToolMessage(
        content='{"fixture_only":true,"padding":"' + ("synthetic-only " * 16_000) + '"}',
        tool_call_id="call-4", name="read_fact_4",
    ))

    loop = object.__new__(Loop)
    loop.context = lambda: (prepared, payload)
    loop.run = {"source_message_id": "message-budget-stop"}
    loop.model_id = "deepseek-flash"
    loop.reserved_tokens = 0
    loop.specs = []
    loop.experiment_id = None
    loop.path = "unused-offline-path"
    loop.run_id = "run-budget-stop"
    loop.worker_id = None
    loop.runtime_grant_binding = None
    loop.trace = lambda *_args, **_kwargs: None
    reservations = []
    provider_handlers = []
    monkeypatch.setattr(domain, "reserve", lambda *args, **kwargs: reservations.append(args))

    async def handler(_request):
        provider_handlers.append(True)

    with pytest.raises(ContextBudgetExceeded):
        asyncio.run(loop.awrap_model_call(SimpleNamespace(messages=messages), handler))

    assert reservations == []
    assert provider_handlers == []
