"""Regression: budget-pruned direct assets cannot launder ancestor Memory.

Model completions and the reused D5 source-receipt fixture are deterministic
test doubles, not Provider/business-outcome evidence. The S1 target Probe is real.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from opspilot.domain.chat import complete_chat_attempt
from opspilot.domain.episodic_memory import revoke_memory
from opspilot.domain.semantic_memory import confirm_semantic_memory, revoke_semantic_memory
from test_d5_context import _seed_hf01_chat_target
from test_m303_semantic_memory import _candidate, _create_task, _prepare_task_chat, _session_and_task


@pytest.mark.parametrize("asset_type", ["EPISODIC", "SEMANTIC"])
def test_revocation_excludes_derived_answer_when_direct_memory_block_was_pruned(
    demo_db: Path, live_api: str, monkeypatch: pytest.MonkeyPatch, asset_type: str,
) -> None:
    monkeypatch.setenv("OPSPILOT_CONTEXT_STRATEGY", "HYBRID")
    monkeypatch.setenv("OPSPILOT_CONTEXT_INPUT_BUDGET_TOKENS", "12000")
    if asset_type == "EPISODIC":
        target = _seed_hf01_chat_target(demo_db, live_api, "hf02-episodic")
        active = target["memory"]
        session_id = str(target["session_id"])
        task_id = str(target["task_id"])
        revoke = revoke_memory
    else:
        session_id, source_task, source_message = _session_and_task(demo_db, "hf02-semantic-source")
        task_id, _ = _create_task(demo_db, session_id, "hf02-semantic-target")
        candidate = _candidate(demo_db, source_task, source_message, "hf02-semantic")
        active = confirm_semantic_memory(
            demo_db, str(candidate["memory_id"]), "approver-a", idempotency_key="hf02-semantic-confirm",
        )
        revoke = revoke_semantic_memory

    _, first = _prepare_task_chat(demo_db, session_id, task_id, "hf02-first")
    assert any(r["memory_id"] == active["memory_id"] for r in first["memory_refs"])
    first_answer = "Historical method from the approved case: correlate current facts before drawing a conclusion."
    first_result = complete_chat_attempt(
        demo_db, str(first["worker_id"]), str(first["attempt_id"]), first_answer,
        provider_response_id="TEST_DOUBLE_HF02_FIRST", input_tokens=200, output_tokens=20, total_tokens=220,
    )
    memory_cost = sum(
        int(block["estimated_tokens"]) for block in first["context_blocks"]
        if block["category"] == "EXTERNAL_GUIDANCE" and block["status"] == "SELECTED"
    )
    # Enough for the required state and short prior answer; insufficient for the
    # lower-priority direct Memory block. This uses the normal allocator.
    second_budget = int(first["context_budget"]["estimated_input_tokens"]) - memory_cost + 120
    monkeypatch.setenv("OPSPILOT_CONTEXT_INPUT_BUDGET_TOKENS", str(second_budget))
    _, second = _prepare_task_chat(demo_db, session_id, task_id, "hf02-second")
    assert second["memory_refs"] == []
    assert first_result["message_id"] in second["selected_message_ids"]
    assert first_answer in [m["content"] for m in second["messages"]]
    assert first["attempt_id"] in second["model_call_refs"]
    derived_answer = "The prior case method still suggests correlating current facts; this is no authorization."
    second_result = complete_chat_attempt(
        demo_db, str(second["worker_id"]), str(second["attempt_id"]), derived_answer,
        provider_response_id="TEST_DOUBLE_HF02_DERIVED", input_tokens=200, output_tokens=20, total_tokens=220,
    )

    revoke(demo_db, str(active["memory_id"]), "approver-a", idempotency_key="hf02-revoke-" + asset_type)
    monkeypatch.setenv("OPSPILOT_CONTEXT_INPUT_BUDGET_TOKENS", "12000")
    _, after = _prepare_task_chat(demo_db, session_id, task_id, "hf02-after-revocation")
    assert first_result["message_id"] not in after["selected_message_ids"]
    assert second_result["message_id"] not in after["selected_message_ids"]
    assert derived_answer not in [m["content"] for m in after["messages"]]
    assert any(
        e.get("message_id") == second_result["message_id"]
        and "MEMORY" in str(e.get("reason"))
        for e in after["excluded_sources"]
    )
