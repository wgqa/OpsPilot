from __future__ import annotations

import json
from pathlib import Path

from opspilot.domain.chat import (
    assert_chat_compression_sources_current,
    _compact_summary_document,
    _canonical,
    complete_chat_attempt,
    complete_chat_compression_attempt,
    get_chat_manifest,
    persist_chat_chunk,
    prepare_chat_attempt,
    prepare_chat_compression_attempt,
)
from opspilot.domain.context_engineering import (
    ContextBudgetExceeded,
    allocate_context_blocks,
    context_budget_for_model,
    estimate_messages_tokens,
)
from opspilot.domain.database import connect
from opspilot.investigator import _investigator_context_budget, _prompt_messages
from opspilot.domain.task_control import (
    admit_task_message,
    apply_pending_critical_inputs,
    claim_task_run,
    create_session,
    create_task_with_initial_run,
    recover_running_task_runs,
    register_worker_owner,
    trusted_identity,
)


def _turn(
    db: Path, session_id: str, owner: str, text: str, *, key: str, answer: str,
) -> dict[str, object]:
    identity = trusted_identity(db, "support-a")
    admitted = admit_task_message(
        db, identity, session_id=session_id, task_id=None, input_kind="CHAT_READONLY",
        body=text, idempotency_key=key,
    )
    run_id = str(admitted["run_id"])
    claim_task_run(db, identity, run_id)
    prepared = prepare_chat_attempt(db, run_id, owner, "test-model")
    attempt_id = str(prepared["attempt_id"])
    persist_chat_chunk(db, owner, attempt_id, 1, answer)
    complete_chat_attempt(
        db, owner, attempt_id, answer, provider_response_id=f"provider:{attempt_id}",
        input_tokens=17, output_tokens=9, total_tokens=26,
    )
    return admitted


def _long_history(db: Path, turns: int = 18) -> tuple[str, str]:
    identity = trusted_identity(db, "support-a")
    session_id = str(create_session(db, identity)["session_id"])
    owner = "m302-context-worker"
    register_worker_owner(db, owner, 72001)
    for index in range(turns):
        user_text = (f"Turn {index} states the original incident goal, constraints, negations and correction order. " * 3)
        assistant_text = f"Answer {index} preserves this earlier conversation context and unresolved question."
        _turn(db, session_id, owner, user_text, key=f"m302-history-{index}", answer=assistant_text)
    return session_id, owner


def _new_run(db: Path, session_id: str, owner: str, *, key: str = "m302-current") -> str:
    identity = trusted_identity(db, "support-a")
    accepted = admit_task_message(
        db, identity, session_id=session_id, task_id=None, input_kind="CHAT_READONLY",
        body="Continue from the original goal and preserve the latest correction.", idempotency_key=key,
    )
    run_id = str(accepted["run_id"])
    claim_task_run(db, identity, run_id)
    return run_id


def _summary_json(sequences: list[int]) -> str:
    first = sequences[0]
    return json.dumps({
        "initial_goal": {"text": "Investigate the original incident goal.", "source_sequences": [first]},
        "constraints": [], "user_assertions": [], "corrections": [],
        "rejected_hypotheses": [], "unresolved_items": [], "timeline": [],
    }, ensure_ascii=False)


def test_context_token_estimate_and_required_block_fail_closed(monkeypatch) -> None:
    monkeypatch.setenv("OPSPILOT_CONTEXT_INPUT_BUDGET_TOKENS", "24")
    profile = context_budget_for_model("test-model")
    assert profile["input_budget_tokens"] == 24
    assert profile["estimator"] == "tiktoken:cl100k_base:0.14.0"
    messages = [{"role": "system", "content": "trusted " * 50}]
    assert estimate_messages_tokens(messages) > 24
    try:
        allocate_context_blocks(
            [{"block_id": "current-facts", "required": True, "messages": messages}],
            budget=profile,
        )
    except ContextBudgetExceeded as error:
        assert error.code == "REQUIRED_CONTEXT_EXCEEDS_BUDGET"
    else:
        raise AssertionError("Required trusted context must fail closed when it exceeds the model input budget.")


def test_hybrid_context_compression_commits_versioned_source_linked_summary(demo_db: Path, monkeypatch) -> None:
    session_id, owner = _long_history(demo_db)
    run_id = _new_run(demo_db, session_id, owner)
    monkeypatch.setenv("OPSPILOT_CONTEXT_STRATEGY", "HYBRID")
    monkeypatch.setenv("OPSPILOT_CONTEXT_INPUT_BUDGET_TOKENS", "1400")

    compression = prepare_chat_compression_attempt(demo_db, run_id, owner, "test-model")

    assert compression is not None
    assert compression["estimated_input_tokens"] <= compression["input_budget_tokens"]
    assert assert_chat_compression_sources_current(demo_db, owner, str(compression["attempt_id"]))["current"] is True
    result = complete_chat_compression_attempt(
        demo_db, owner, str(compression["attempt_id"]),
        _summary_json(list(compression["allowed_message_sequences"])),
        provider_response_id="provider-summary-1", input_tokens=800, output_tokens=60, total_tokens=860,
    )
    assert result["status"] == "SUCCEEDED"
    assert result["token_usage"] == {"input_tokens": 800, "output_tokens": 60, "total_tokens": 860}

    answer = prepare_chat_attempt(demo_db, run_id, owner, "test-model")
    assert answer["attempt_no"] == 2
    assert answer["summary_refs"][0]["summary_id"] == result["summary_id"]
    assert int(answer["context_budget"]["estimated_input_tokens"]) <= int(answer["context_budget"]["input_budget_tokens"])
    assert {item["category"] for item in answer["context_blocks"]} >= {
        "TRUSTED_CONTROL", "CURRENT_TASK_STATE", "CURRENT_FACTS", "HISTORICAL_SUMMARY", "RECENT_INTERACTION",
    }
    persist_chat_chunk(demo_db, owner, str(answer["attempt_id"]), 1, "The current question is preserved with the earlier goal summary.")
    complete_chat_attempt(
        demo_db, owner, str(answer["attempt_id"]), "The current question is preserved with the earlier goal summary.",
        provider_response_id="provider-answer-2", input_tokens=500, output_tokens=15, total_tokens=515,
    )
    manifest = get_chat_manifest(demo_db, trusted_identity(demo_db, "support-a"), run_id)
    assert manifest["compression_attempts"][0]["status"] == "SUCCEEDED"
    assert manifest["compression_attempts"][0]["token_usage"]["total_tokens"] == 860
    assert manifest["attempts"][0]["manifest"]["truncation"]["summary_refs"][0]["summary_id"] == result["summary_id"]
    with connect(demo_db) as connection:
        lineage = connection.execute(
            "SELECT summary_id, summary_version, summary_digest FROM chat_message_summary_sources WHERE message_id = (SELECT message_id FROM chat_run_answers WHERE run_id = ?)",
            (run_id,),
        ).fetchone()
        source_ref = connection.execute(
            """SELECT dependency_ref FROM context_summary_dependencies
               WHERE summary_id = ? AND dependency_kind = 'MESSAGE' ORDER BY source_order LIMIT 1""",
            (result["summary_id"],),
        ).fetchone()[0]
        prior_answer_id = connection.execute(
            "SELECT message_id FROM chat_run_answers WHERE run_id = ?", (run_id,),
        ).fetchone()[0]
    assert lineage is not None and lineage["summary_id"] == result["summary_id"]

    with connect(demo_db) as connection:
        connection.execute("UPDATE messages SET body_digest = 'invalidated-source-digest' WHERE message_id = ?", (source_ref,))
    next_run = _new_run(demo_db, session_id, owner, key="m302-after-source-invalidation")
    monkeypatch.setenv("OPSPILOT_CONTEXT_STRATEGY", "RECENT_WINDOW")
    monkeypatch.setenv("OPSPILOT_CONTEXT_INPUT_BUDGET_TOKENS", "12000")
    next_context = prepare_chat_attempt(demo_db, next_run, owner, "test-model")
    assert all(item["summary_id"] != result["summary_id"] for item in next_context["summary_refs"])
    assert str(prior_answer_id) not in next_context["selected_message_ids"]
    summary_exclusions = [
        {"source_id": item.get("source_id"), "reason": item.get("reason")}
        for item in next_context["excluded_sources"] if item.get("source_id")
    ]
    assert any(item.get("source_id") == result["summary_id"] and "SUMMARY_" in str(item["reason"])
               for item in summary_exclusions), {"expected": result["summary_id"], "actual": summary_exclusions}


def test_hybrid_compression_batches_old_history_within_input_budget(demo_db: Path, monkeypatch) -> None:
    identity = trusted_identity(demo_db, "support-a")
    session_id = str(create_session(demo_db, identity)["session_id"])
    owner = "m302-batched-compression-worker"
    register_worker_owner(demo_db, owner, 72011)
    for index in range(18):
        _turn(
            demo_db, session_id, owner,
            f"User turn {index}: preserve the original goal and constraints.",
            key=f"m302-batched-history-{index}",
            answer=(f"Earlier assistant answer {index} preserves context and uncertainty. " * 12),
        )
    run_id = _new_run(demo_db, session_id, owner, key="m302-batched-compression-current")
    monkeypatch.setenv("OPSPILOT_CONTEXT_STRATEGY", "HYBRID")
    monkeypatch.setenv("OPSPILOT_CONTEXT_INPUT_BUDGET_TOKENS", "1400")

    compression = prepare_chat_compression_attempt(demo_db, run_id, owner, "test-model")

    assert compression is not None
    assert compression["estimated_input_tokens"] <= compression["input_budget_tokens"]
    assert 0 < len(compression["allowed_message_sequences"]) < 24
    sequences = compression["allowed_message_sequences"]
    assert sequences == list(range(sequences[0], sequences[-1] + 1))


def test_rolling_compression_bounds_a_single_oversized_assistant_message(demo_db: Path, monkeypatch) -> None:
    identity = trusted_identity(demo_db, "support-a")
    session_id = str(create_session(demo_db, identity)["session_id"])
    owner = "m302-oversized-assistant-worker"
    register_worker_owner(demo_db, owner, 72012)
    for index in range(8):
        answer = (
            "This older assistant response is verbose historical conversation, not current trusted evidence. " * 160
            if index == 0 else f"Short answer {index} preserves uncertainty."
        )
        _turn(
            demo_db, session_id, owner,
            f"User turn {index}: keep the original goal, negations, and unresolved items.",
            key=f"m302-oversized-history-{index}", answer=answer,
        )
    monkeypatch.setenv("OPSPILOT_CONTEXT_STRATEGY", "ROLLING_SUMMARY")
    monkeypatch.setenv("OPSPILOT_CONTEXT_INPUT_BUDGET_TOKENS", "1400")

    first_run = _new_run(demo_db, session_id, owner, key="m302-oversized-first")
    compression = prepare_chat_compression_attempt(demo_db, first_run, owner, "test-model")

    assert compression is not None
    assert compression["estimated_input_tokens"] <= compression["input_budget_tokens"]
    assert {1, 2} <= set(compression["allowed_message_sequences"])
    assert 2 in compression["allowed_message_sequences"]
    with connect(demo_db) as connection:
        row = connection.execute(
            "SELECT source_dependencies_json FROM context_compression_attempts WHERE attempt_id = ?",
            (compression["attempt_id"],),
        ).fetchone()
    source_material = json.loads(str(row["source_dependencies_json"]))["source_material"]
    truncation = source_material["truncated_sources"][0]
    new_messages = source_material["new_messages"]
    assert [item["sequence"] for item in new_messages][:2] == [1, 2]
    assert truncation["sequence"] == 2
    assert truncation["reason"] == "ASSISTANT_HISTORY_EXCERPTED_TO_FIT_COMPRESSION_BUDGET"
    assert truncation["original_estimated_tokens"] > truncation["included_estimated_tokens"]
    assistant_excerpt = next(item["body"] for item in new_messages if item["sequence"] == 2)
    assert "historical assistant text omitted" in assistant_excerpt


def test_summary_projection_and_storage_are_bounded_and_keep_core_categories() -> None:
    source = {"source_message_ids": [f"message-{index}" for index in range(1, 20)]}
    document = {
        "initial_goal": {"text": "Original goal and limitations " * 20, **source},
        "constraints": [{"text": "Keep the caller and route unchanged " * 12, **source}],
        "user_assertions": [{"text": "An unverified user assertion " * 12, **source}],
        "corrections": [{"text": "Latest formal correction remains untrusted " * 12, **source}],
        "rejected_hypotheses": [{"text": "Credential expiry is an unverified hypothesis " * 12, **source}],
        "unresolved_items": [{"text": "Current status and recovery remain unverified " * 12, **source}],
        "timeline": [{"text": "A versioned event occurred at a known sequence " * 12, **source}],
    }

    compact = _compact_summary_document(document)
    estimate = estimate_messages_tokens([{"role": "system", "content": _canonical(compact)}])

    assert estimate <= 512
    assert compact["initial_goal"]["text"]
    for field in ("constraints", "corrections", "rejected_hypotheses", "unresolved_items", "timeline"):
        assert compact[field], field
        assert compact[field][-1]["source_message_ids"]


def test_compression_source_change_is_rejected_before_provider_io(demo_db: Path, monkeypatch) -> None:
    session_id, owner = _long_history(demo_db)
    run_id = _new_run(demo_db, session_id, owner, key="m302-invalidation")
    monkeypatch.setenv("OPSPILOT_CONTEXT_INPUT_BUDGET_TOKENS", "1400")
    compression = prepare_chat_compression_attempt(demo_db, run_id, owner, "test-model")
    assert compression is not None
    with connect(demo_db) as connection:
        dependencies = json.loads(str(connection.execute(
            "SELECT source_dependencies_json FROM context_compression_attempts WHERE attempt_id = ?",
            (compression["attempt_id"],),
        ).fetchone()[0]))["dependencies"]
        source = next(item for item in dependencies if item["kind"] == "MESSAGE")
        connection.execute(
            "UPDATE messages SET body_digest = 'changed-after-reservation' WHERE message_id = ?",
            (source["ref"],),
        )

    result = assert_chat_compression_sources_current(demo_db, owner, str(compression["attempt_id"]))

    assert result["current"] is False
    with connect(demo_db) as connection:
        row = connection.execute(
            "SELECT status, provider_response_id FROM context_compression_attempts WHERE attempt_id = ?",
            (compression["attempt_id"],),
        ).fetchone()
        summary_count = int(connection.execute("SELECT COUNT(*) FROM context_summaries").fetchone()[0])
    assert row["status"] == "INVALIDATED"
    assert row["provider_response_id"] is None
    assert summary_count == 0


def test_worker_recovery_marks_reserved_compression_attempt_interrupted(demo_db: Path, monkeypatch) -> None:
    session_id, owner = _long_history(demo_db)
    run_id = _new_run(demo_db, session_id, owner, key="m302-worker-crash")
    monkeypatch.setenv("OPSPILOT_CONTEXT_INPUT_BUDGET_TOKENS", "1400")
    compression = prepare_chat_compression_attempt(demo_db, run_id, owner, "test-model")
    assert compression is not None

    replacement = "m302-context-worker-restarted"
    epoch = register_worker_owner(demo_db, replacement, 72002)
    assert run_id in recover_running_task_runs(demo_db, replacement, epoch)

    with connect(demo_db) as connection:
        attempt = connection.execute(
            "SELECT status, error_class FROM context_compression_attempts WHERE attempt_id = ?",
            (compression["attempt_id"],),
        ).fetchone()
        run = connection.execute("SELECT status FROM task_runs WHERE run_id = ?", (run_id,)).fetchone()
    assert attempt["status"] == "INTERRUPTED"
    assert attempt["error_class"] == "WorkerRestarted"
    assert run["status"] == "INTERRUPTED_RECOVERABLE"


def test_context_strategies_report_recent_window_and_rolling_summary(demo_db: Path, monkeypatch) -> None:
    from opspilot.domain.chat import _prepare_context

    session_id, _owner_id = _long_history(demo_db, turns=14)
    identity = trusted_identity(demo_db, "support-a")
    accepted = admit_task_message(
        demo_db, identity, session_id=session_id, task_id=None, input_kind="CHAT_READONLY",
        body="Retain the latest correction.", idempotency_key="m302-strategy-current",
    )
    run_id = str(accepted["run_id"])
    claim_task_run(demo_db, identity, run_id)
    with connect(demo_db) as connection:
        run = connection.execute("SELECT * FROM task_runs WHERE run_id = ?", (run_id,)).fetchone()
        monkeypatch.setenv("OPSPILOT_CONTEXT_STRATEGY", "RECENT_WINDOW")
        recent = _prepare_context(connection, run, "test-model", demo_db)
        monkeypatch.setenv("OPSPILOT_CONTEXT_STRATEGY", "ROLLING_SUMMARY")
        rolling = _prepare_context(connection, run, "test-model", demo_db)
        monkeypatch.setenv("OPSPILOT_CONTEXT_STRATEGY", "HYBRID")
        monkeypatch.setenv("OPSPILOT_CONTEXT_INPUT_BUDGET_TOKENS", "12000")
        hybrid = _prepare_context(connection, run, "test-model", demo_db)

    assert recent["context_budget"]["strategy"] == "RECENT_WINDOW"
    assert recent["needs_compression"] is False
    assert len(recent["selected_message_ids"]) <= 12
    assert rolling["context_budget"]["strategy"] == "ROLLING_SUMMARY"
    assert rolling["needs_compression"] is True
    assert hybrid["context_budget"]["strategy"] == "HYBRID"
    assert hybrid["needs_compression"] is False


def test_investigator_manifest_uses_shared_budget_and_layered_context_blocks(demo_db: Path) -> None:
    identity = trusted_identity(demo_db, "support-a")
    session_id = str(create_session(demo_db, identity)["session_id"])
    created = create_task_with_initial_run(
        demo_db, identity, session_id=session_id, service_id="orders-demo",
        integration_id="integration-a", ticket_id="M302-CONTEXT-BLOCKS",
        initial_message="The order endpoint returned an authentication error; do not assume it is fixed.",
        idempotency_key="m302-context-blocks-create",
    )
    task_id, run_id = str(created["task_id"]), str(created["run_id"])
    claim_task_run(demo_db, identity, run_id)
    apply_pending_critical_inputs(demo_db, identity, run_id)
    metadata: dict[str, object] = {}
    messages = _prompt_messages(
        demo_db, task_id, {"evidence_ids": [], "tool_observations": [], "gate_decision": {}},
        context_metadata=metadata, run_id=run_id,
    )

    budget = _investigator_context_budget(messages, "test-model", [], metadata)
    categories = {item["category"] for item in metadata["context_blocks"]}
    actual_prompt_estimate = estimate_messages_tokens([
        {"role": str(message.type), "content": str(message.content)} for message in messages
    ])

    assert categories >= {
        "TRUSTED_CONTROL", "CURRENT_TASK_STATE", "CURRENT_FACTS", "RECENT_INTERACTION",
        "HISTORICAL_SUMMARY", "EXTERNAL_GUIDANCE", "TOOL_SCHEMA",
    }
    assert budget["estimated_input_tokens"] == actual_prompt_estimate + 8
    assert budget["input_budget_tokens"] <= budget["context_window_tokens"]
