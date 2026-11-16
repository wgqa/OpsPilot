"""Offline replay of the real Q02-B reply and its exact first-attempt sources."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import uuid

import pytest

from opspilot.domain import chat
from opspilot.domain.database import connect
from opspilot.domain.task_control import (
    TaskControlError,
    admit_task_message,
    claim_task_run,
    create_session,
    register_worker_owner,
    trusted_identity,
)


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "docs/evidence/r2-ar04-summary-persist-budget-hf01"
SPEC = importlib.util.spec_from_file_location("ar04_persistence_budget_replay", EVIDENCE / "replay_budget.py")
assert SPEC is not None and SPEC.loader is not None
REPLAY = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(REPLAY)
ERROR = "CONTEXT_SUMMARY_FACT_RETENTION_BUDGET_EXCEEDED"


@pytest.fixture(scope="module")
def live_reply():
    history, source_map, messages, response = REPLAY.load_replay()
    text = response["response_payload"]["choices"][0]["message"]["content"]
    return history, source_map, messages, text


def test_saved_response_preserves_every_text_and_source_under_512(live_reply):
    _, source_map, _, text = live_reply
    validated = chat._validate_summary_document(text, source_map)
    with pytest.raises(TaskControlError) as base:
        chat._compact_summary_document(validated)
    assert base.value.code == ERROR and str(base.value) == f"{ERROR}:unresolved_items:2"
    candidate = chat._compact_summary_for_persistence(validated, source_map)
    assert candidate == json.loads(text)
    assert REPLAY.tokens(candidate) == 494 <= chat.MAX_PERSISTED_SUMMARY_TOKENS == 512
    assert sum(len(row["source_sequences"]) for _, _, row in REPLAY.entries(candidate)) == 25
    assert len(candidate["constraints"][1]["source_sequences"]) == 6
    assert candidate["user_assertions"][0]["source_sequences"] == [3]
    assert "endpoint=/callback" in candidate["user_assertions"][0]["text"]
    assert "max_attempts=3" in candidate["user_assertions"][0]["text"]
    correction = candidate["corrections"][0]
    assert correction["source_sequences"] == [7] and "req-482" in correction["text"] and "req-483" in correction["text"]


def test_partial_early_value_stays_partial_even_with_complete_later_transition(live_reply):
    _, source_map, _, text = live_reply
    variant = json.loads(text)
    early = variant["user_assertions"][0]
    early["text"] = early["text"].split("max_attempts=", 1)[0] + "max_attempts=…"
    output = chat._compact_summary_for_persistence(
        chat._validate_summary_document(json.dumps(variant, ensure_ascii=False), source_map),
        source_map,
    )
    assert output == variant
    assert output["user_assertions"][0]["source_sequences"] == [3]
    assert output["user_assertions"][0]["text"].endswith("max_attempts=…")
    transition = output["timeline"][0]
    assert transition["source_sequences"] == [11]
    assert all(token in transition["text"] for token in ("v1.2", "v1.3", "max_attempts", "3", "5", "部署版本未知"))


def _with_message_id(monkeypatch, message_id, fn, *args, **kwargs):
    if message_id is None:
        return fn(*args, **kwargs)
    forced = iter([uuid.UUID(message_id.removeprefix("message-"))])
    uuid4 = uuid.uuid4
    with monkeypatch.context() as patch:
        patch.setattr(uuid, "uuid4", lambda: next(forced, None) or uuid4())
        return fn(*args, **kwargs)


@pytest.fixture
def reserved_replay(demo_db, monkeypatch, live_reply):
    history, source_map, original_messages, text = live_reply
    identity = trusted_identity(demo_db, "support-a")
    session_id = str(create_session(demo_db, identity)["session_id"])
    worker = "ar04-exact-replay-worker"
    register_worker_owner(demo_db, worker, 84120)
    monkeypatch.setenv("OPSPILOT_CONTEXT_INPUT_BUDGET_TOKENS", "12000")
    monkeypatch.setenv("OPSPILOT_CONTEXT_STRATEGY", "RECENT_WINDOW")
    with monkeypatch.context() as patch:
        patch.setattr(chat, "CHAT_RECENT_WINDOW_MESSAGES", 2)
        for index in range(0, 28, 2):
            user, assistant = history[index:index + 2]
            accepted = _with_message_id(
                patch, source_map.get(str(user["sequence"])), admit_task_message,
                demo_db, identity, session_id=session_id, task_id=None, input_kind="CHAT_READONLY",
                body=user["body"], idempotency_key=f"exact-replay-seq-{user['sequence']}",
            )
            run_id = str(accepted["run_id"])
            claim_task_run(demo_db, identity, run_id)
            attempt = chat.prepare_chat_attempt(demo_db, run_id, worker, "fixture-model")
            chat.persist_chat_chunk(demo_db, worker, attempt["attempt_id"], 1, assistant["body"])
            _with_message_id(
                patch, source_map.get(str(assistant["sequence"])), chat.complete_chat_attempt,
                demo_db, worker, attempt["attempt_id"], assistant["body"],
                provider_response_id=f"offline-history-{assistant['sequence']}",
                input_tokens=17, output_tokens=9, total_tokens=26,
            )
        admit_task_message(
            demo_db, identity, session_id=session_id, task_id=None, input_kind="CHAT_READONLY",
            body=history[28]["body"], idempotency_key="exact-replay-seq-29",
        )
    questions = json.loads((REPLAY.DATASET / "QUESTIONS.json").read_bytes())["questions"]
    [question] = [row["prompt_text"] for row in questions if row["id"] == "Q02"]
    run = admit_task_message(
        demo_db, identity, session_id=session_id, task_id=None, input_kind="CHAT_READONLY",
        body=question, idempotency_key="exact-replay-question", assistant_core=True,
    )
    run_id = str(run["run_id"])
    claim_task_run(demo_db, identity, run_id)
    monkeypatch.setenv("OPSPILOT_CONTEXT_STRATEGY", "ROLLING_SUMMARY")
    first = chat.prepare_chat_compression_attempt(demo_db, run_id, worker, "deepseek-flash")
    assert first is not None and first["messages"] == original_messages
    with connect(demo_db) as db:
        snapshot = json.loads(db.execute(
            "SELECT source_dependencies_json FROM context_compression_attempts WHERE attempt_id=?",
            (first["attempt_id"],),
        ).fetchone()[0])
    assert snapshot["source_sequence_map"] == source_map
    return demo_db, worker, run_id, first, text


def _complete(path, worker, attempt, text, response_id):
    assert chat.assert_chat_compression_sources_current(path, worker, attempt["attempt_id"])["current"]
    return chat.complete_chat_compression_attempt(
        path, worker, attempt["attempt_id"], text, provider_response_id=response_id,
        input_tokens=4119, output_tokens=458, total_tokens=4577,
    )


def test_real_reply_commits_and_keeps_all_citations_in_second_and_answer_prompts(reserved_replay, live_reply):
    path, worker, run_id, first, text = reserved_replay
    committed = _complete(path, worker, first, text, REPLAY.RESPONSE_ID)
    assert committed["status"] == "SUCCEEDED"
    second = chat.prepare_chat_compression_attempt(path, run_id, worker, "deepseek-flash")
    assert second is not None
    previous = json.loads(second["messages"][1]["content"].split("\n", 1)[1])["previous_summary"]
    assert previous == json.loads(text)
    with connect(path) as db:
        snapshot = json.loads(db.execute(
            "SELECT source_dependencies_json FROM context_compression_attempts WHERE attempt_id=?",
            (second["attempt_id"],),
        ).fetchone()[0])
        assert all(snapshot["source_sequence_map"][seq] == ref for seq, ref in live_reply[1].items())
        assert any(dep["kind"] == "SUMMARY" and dep["ref"] == committed["summary_id"]
                   for dep in snapshot["dependencies"])
    # Same text as a deterministic second reply, with no claim about live L3.
    next_commit = _complete(path, worker, second, text, "offline-second-summary-fixture")
    assert next_commit["status"] == "SUCCEEDED"
    answer = chat.prepare_chat_attempt(path, run_id, worker, "deepseek-flash")
    assert answer.get("error") is None
    assert answer["summary_refs"][0]["summary_id"] == next_commit["summary_id"]
    [block] = [msg["content"] for msg in answer["messages"]
               if msg.get("role") == "system" and msg["content"].startswith("HISTORICAL SESSION SUMMARY")]
    assert "source message sequences are attached" in block
    assert json.loads(block.split(": ", 1)[1]) == previous
    with connect(path) as db:
        records = db.execute("SELECT state,summary_json FROM context_summaries ORDER BY summary_version").fetchall()
    assert [row["state"] for row in records] == ["SUPERSEDED", "CURRENT"]
    assert all(json.loads(row["summary_json"]) == previous for row in records)


@pytest.mark.parametrize("change", ["source_revoked", "sequence_rebound"])
def test_compact_summary_is_excluded_after_source_or_binding_changes(
    reserved_replay, live_reply, monkeypatch, change,
):
    path, worker, run_id, first, text = reserved_replay
    committed = _complete(path, worker, first, text, REPLAY.RESPONSE_ID)
    with connect(path) as db:
        if change == "source_revoked":
            db.execute("UPDATE messages SET body_digest=? WHERE message_id=?",
                       ("revoked-by-test", live_reply[1]["3"]))
        else:
            snapshot = json.loads(db.execute(
                "SELECT source_dependencies_json FROM context_compression_attempts WHERE attempt_id=?",
                (first["attempt_id"],),
            ).fetchone()[0])
            snapshot["source_sequence_map"]["3"] = snapshot["source_sequence_map"]["5"]
            db.execute("UPDATE context_compression_attempts SET source_dependencies_json=? WHERE attempt_id=?",
                       (json.dumps(snapshot), first["attempt_id"]))
    monkeypatch.setenv("OPSPILOT_CONTEXT_STRATEGY", "RECENT_WINDOW")
    context = chat.prepare_chat_attempt(path, run_id, worker, "deepseek-flash")
    assert not context["summary_refs"]
    assert not any("HISTORICAL SESSION SUMMARY" in msg["content"] for msg in context["messages"])
    [reason] = [row["reason"] for row in context["excluded_sources"]
                if row.get("source_id") == committed["summary_id"]]
    assert reason == {
        "source_revoked": "SUMMARY_DEPENDENCY_INVALID:USER_MESSAGE_SOURCE_CHANGED",
        "sequence_rebound": "SUMMARY_SEQUENCE_SOURCE_INVALID",
    }[change]
    with connect(path) as db:
        summary = db.execute("SELECT state FROM context_summaries WHERE summary_id=?",
                             (committed["summary_id"],)).fetchone()
    assert summary["state"] == "INVALID"


def test_lossless_fallback_rejects_a_full_document_over_512(reserved_replay):
    path, worker, _, first, text = reserved_replay
    longer = json.loads(text)
    longer["rejected_hypotheses"].append({
        "text": "Additional fixture detail preserves each original observation and cites its permitted source.",
        "source_sequences": [9],
    })
    assert REPLAY.tokens(longer) > chat.MAX_PERSISTED_SUMMARY_TOKENS == 512
    with pytest.raises(TaskControlError) as stopped:
        _complete(path, worker, first, json.dumps(longer, ensure_ascii=False), "offline-too-large")
    assert stopped.value.code == ERROR
    with connect(path) as db:
        assert db.execute("SELECT COUNT(*) FROM context_summaries").fetchone()[0] == 0
