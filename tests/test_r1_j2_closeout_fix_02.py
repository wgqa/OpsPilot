"""Targeted regressions for the offline R1 J2 closeout fixes."""
from __future__ import annotations

import asyncio
import copy
from types import SimpleNamespace

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

import opspilot.assistant as assistant_module
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


def test_exact_historical_summary_reuse_keeps_each_source_and_scope():
    same_summary = {
        "authority": "HISTORICAL_PROTOCOL_METHOD_ONLY_NOT_CURRENT_BUSINESS_EVIDENCE",
        "session_id": "session-a", "project_id": "project-a", "grant_version": 4,
        "scope_digest": "scope-a", "topic": "callback retry",
        "protocol_documents": [{"document_id": "contract-v1", "version": "1.0", "digest": "a" * 64}],
    }
    different_scope_summary = {**same_summary, "scope_digest": "scope-b"}
    different_content_summary = {**same_summary, "topic": "callback delivery"}
    source = lambda call, observation, evidence, digest: {
        "call_id": call, "observation_id": observation, "evidence_id": evidence,
        "result_digest": digest, "observed_at": "2026-11-08T09:00:00Z",
        "completed_at": "2026-11-08T09:00:01Z", "summary": same_summary,
    }
    payload = {
        "current_run": {"run_id": "run-current", "business_observations": []},
        "history_sources": [
            {
                "run_id": "run-newer", "current_source_valid": True,
                "exclusion_reason": None, "omitted_source_count": 0,
                "sources": [source("call-new", "obs-new", "evidence-new", "digest-new")],
            },
            {
                "run_id": "run-older", "current_source_valid": True,
                "exclusion_reason": None, "omitted_source_count": 0,
                "sources": [
                    source("call-old", "obs-old", "evidence-old", "digest-old"),
                    {**source("call-scope", "obs-scope", "evidence-scope", "digest-scope"), "summary": different_scope_summary},
                    {**source("call-content", "obs-content", "evidence-content", "digest-content"), "summary": different_content_summary},
                ],
            },
            {
                "run_id": "run-invalid", "current_source_valid": False,
                "exclusion_reason": "SOURCE_REVOKED", "omitted_source_count": 1,
                "sources": [source("call-revoked", "obs-revoked", "evidence-revoked", "digest-revoked")],
            },
        ],
        "prior_answers": [], "task_id": "task-current", "source_message_id": "message-current",
    }
    original = copy.deepcopy(payload)

    projected = source_context_for_model(payload)
    newer = projected["history_sources"][0]["snapshots"][0]
    older, different_scope, different_content = projected["history_sources"][1]["snapshots"]
    invalid = projected["history_sources"][2]

    assert newer["summary"] == same_summary
    assert "summary" not in older
    assert older["summary_reused_from"] == {"source_run_id": "run-newer", "call_id": "call-new"}
    assert newer["reference"] == {
        "source_run_id": "run-newer", "call_id": "call-new", "observation_id": "obs-new",
        "evidence_id": "evidence-new", "result_digest": "digest-new",
        "observed_at": "2026-11-08T09:00:00Z", "completed_at": "2026-11-08T09:00:01Z",
    }
    assert older["reference"]["source_run_id"] == "run-older"
    assert older["reference"]["call_id"] == "call-old"
    assert older["reference"]["observation_id"] == "obs-old"
    assert older["reference"]["evidence_id"] == "evidence-old"
    assert older["reference"]["result_digest"] == "digest-old"
    assert different_scope["summary"] == different_scope_summary
    assert different_content["summary"] == different_content_summary
    assert invalid["reference_scope"] == "EXCLUDED_HISTORY"
    assert invalid["exclusion_reason"] == "SOURCE_REVOKED"
    assert invalid["snapshots"] == []
    assert "summary_reused_from" in projected["history_summary_reuse_guide"]
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


def test_normal_followup_after_four_tool_results_reaches_offline_provider_handler(monkeypatch):
    observations = [
        {
            "tool": f"read_fact_{index}", "call_id": f"call-{index}",
            "tool_call_id": f"provider-call-{index}", "evidence_id": f"evidence-{index}",
            "observation_id": f"observation-{index}", "observed_at": f"2026-11-08T09:0{index}:00Z",
        }
        for index in range(1, 5)
    ]
    same_summary = {
        "authority": "HISTORICAL_PROTOCOL_METHOD_ONLY_NOT_CURRENT_BUSINESS_EVIDENCE",
        "session_id": "session-a", "project_id": "project-a", "grant_version": 4,
        "scope_digest": "scope-a", "topic": "callback retry",
    }
    payload = {
        "authority": "EXPLANATION_ONLY_NO_BUSINESS_RECEIPT",
        "current_run": {"run_id": "run-normal-followup", "business_observations": observations},
        "history_sources": [
            {
                "run_id": "run-historical-new", "current_source_valid": True,
                "exclusion_reason": None, "omitted_source_count": 0,
                "sources": [{"call_id": "history-call-new", "summary": same_summary}],
            },
            {
                "run_id": "run-historical-old", "current_source_valid": True,
                "exclusion_reason": None, "omitted_source_count": 0,
                "sources": [{"call_id": "history-call-old", "summary": same_summary}],
            },
        ],
        "prior_answers": [], "task_id": "task-normal-followup", "source_message_id": "message-normal-followup",
        "trusted_binding": {"service_id": "orders", "order_id": "order-a", "contract_version": 2},
    }
    prepared = {
        "memory_guidance_messages": [], "summary_refs": [], "memory_refs": [],
        "excluded_sources": [], "selected_message_ids": [], "messages": [],
    }
    tool_calls = [
        {"name": f"read_fact_{i}", "args": {"event_id": "event-current"}, "id": f"provider-call-{i}"}
        for i in range(1, 5)
    ]
    messages = [
        HumanMessage(content="继续核对这个订单内同一 Event 的当前事实，并保留来源。"),
        AIMessage(content="", tool_calls=tool_calls),
        *[
            ToolMessage(
                content='{"fact":"current scoped observation","status":"ACKNOWLEDGED"}',
                tool_call_id=f"provider-call-{i}", name=f"read_fact_{i}",
            )
            for i in range(1, 5)
        ],
    ]

    loop = object.__new__(Loop)
    loop.context = lambda: (prepared, payload)
    loop.run = {"source_message_id": "message-normal-followup"}
    loop.model_id = "deepseek-flash"
    loop.reserved_tokens = 0
    loop.specs = []
    loop.experiment_id = None
    loop.path = "unused-offline-path"
    loop.run_id = "run-normal-followup"
    loop.worker_id = None
    loop.runtime_grant_binding = None
    loop.trace = lambda *_args, **_kwargs: None
    loop._assert_memories_current = lambda _selected: None

    reservations = []
    finishes = []
    provider_requests = []
    monkeypatch.setattr(assistant_module, "get_config", lambda: {"metadata": {"langgraph_step": 2}})
    monkeypatch.setattr(
        domain, "reserve",
        lambda *args, **kwargs: (reservations.append(args) or {
            "call_id": "model-call-normal", "logical_key": "normal-followup-key",
            "request_digest": "request-digest", "status": "RESERVED",
        }, True),
    )
    monkeypatch.setattr(domain, "finish", lambda *args, **kwargs: finishes.append(args))

    class OfflineRequest:
        def __init__(self, messages, tools=None, tool_choice=None, model_settings=None):
            self.messages = messages
            self.tools = tools or []
            self.tool_choice = tool_choice
            self.model_settings = model_settings or {}

        def override(self, **kwargs):
            return SimpleNamespace(messages=self.messages, tools=self.tools, **kwargs)

    request = OfflineRequest(messages)

    async def handler(provider_request):
        provider_requests.append(provider_request)
        return SimpleNamespace(result=[AIMessage(content="已根据四条当前观察继续分析。")])

    result = asyncio.run(loop.awrap_model_call(request, handler))

    assert len(reservations) == 1
    assert len(finishes) == 1
    assert len(provider_requests) == 1
    assert result.result[-1].content == "已根据四条当前观察继续分析。"
    sent = provider_requests[0].messages
    assert sum(isinstance(message, ToolMessage) for message in sent) == 4
    assert [message.tool_call_id for message in sent if isinstance(message, ToolMessage)] == [
        f"provider-call-{i}" for i in range(1, 5)
    ]
    assert "history_summary_reuse_guide" in provider_requests[0].system_message.content
