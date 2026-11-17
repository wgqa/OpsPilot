"""Offline Assistant/Domain replay for the accepted compact-summary format.

The Q02-B first response is read from its immutable saved Provider trace. All
other model outputs are explicitly marked deterministic fixtures. No Provider
client or live authorization is constructed in this test.
"""
from __future__ import annotations

import asyncio
import copy
import gzip
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import uuid

import pytest
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import Field


ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from opspilot import assistant as assistant_runtime  # noqa: E402
from opspilot.domain import chat  # noqa: E402
from opspilot.domain.context_engineering import estimate_messages_tokens, estimate_text_tokens  # noqa: E402
from opspilot.domain.database import connect, reset_fixture  # noqa: E402
from opspilot.domain.task_control import (  # noqa: E402
    admit_task_message,
    claim_task_run,
    create_session,
    create_task_with_initial_run,
    register_worker_owner,
    trusted_identity,
)


EVIDENCE = ROOT / "docs/evidence/r2-ar04-summary-persist-integration-01"
DATASET = ROOT / "docs/evidence/r2-ar04-long-context-journey-01"
LIVE = ROOT / "docs/evidence/r2-ar04-remaining-live-gate-01/live_run_02"
MOCK_TRACE_PATH = (
    ROOT / "docs/evidence/r2-ar04-live-retention-recheck-01/mock_run_04/MOCK_TRACE.jsonl.gz"
)
MOCK_TRACE_SHA256 = "6adc0ac322f284bb1df0a628250c2bd0888bc5e07f8e46206f5cdadd1dfc3756"
QUESTIONS_SHA256 = "ea3d6554eafa433d1617dc5a5ba9f140471f3cb95f8ae10bcd25b807a4e7afe2"
HISTORY_SHA256 = "356512f611b046a04e33506a0fb1a88c6a08af93517b2134125dd6771b282c16"
LIVE_TRACE_SHA256 = "6c5d60bce519aad6ce60af1b647845117ca754685320dbc4040c734087672e9a"

REPLAY_SPEC = importlib.util.spec_from_file_location(
    "ar04_persistence_budget_replay_for_integration",
    ROOT / "docs/evidence/r2-ar04-summary-persist-budget-hf01/replay_budget.py",
)
assert REPLAY_SPEC is not None and REPLAY_SPEC.loader is not None
REPLAY = importlib.util.module_from_spec(REPLAY_SPEC)
REPLAY_SPEC.loader.exec_module(REPLAY)


def _sha(value: bytes | str) -> str:
    if isinstance(value, str):
        value = value.encode("utf-8")
    return hashlib.sha256(value).hexdigest()


def _read_prior_mock_replies() -> tuple[dict[str, dict[str, str]], dict[str, object]]:
    raw = MOCK_TRACE_PATH.read_bytes()
    assert _sha(raw) == MOCK_TRACE_SHA256
    rows = [json.loads(line) for line in gzip.decompress(raw).splitlines()]
    selected: dict[str, dict[str, str]] = {}
    for row in rows:
        logical_id = str(row.get("logical_id") or "")
        if row.get("event") != "RESPONSE_RECEIVED" or logical_id not in {
            "Q02-B:SUMMARY:2", "Q06-B:SUMMARY:1", "Q06-B:SUMMARY:2",
        }:
            continue
        assert row.get("http_status") == 200 and row.get("finish_reason") == "stop"
        assert row.get("status") in {"SUCCEEDED", "COMPLETED"}
        body = row["response_payload"]["choices"][0]["message"]["content"]
        json.loads(body)
        selected[logical_id] = {
            "content": body,
            "evidence_level": "PRIOR_MOCK_TRACE_REPLY",
            "original_response_id": str(row["provider_request_id"]),
            "content_sha256": _sha(body),
            "trace_sha256": MOCK_TRACE_SHA256,
        }
    assert set(selected) == {"Q02-B:SUMMARY:2", "Q06-B:SUMMARY:1", "Q06-B:SUMMARY:2"}
    return selected, {
        "path": str(MOCK_TRACE_PATH.relative_to(ROOT)).replace("\\", "/"),
        "sha256": MOCK_TRACE_SHA256,
        "replies": {
            key: {k: v for k, v in value.items() if k != "content"}
            for key, value in selected.items()
        },
    }


def _q06_second_round_fixture() -> dict[str, str]:
    """A context-bound offline reply using only the second-round source map."""
    content = json.dumps({
        "initial_goal": {
            "text": "只调查 callback 协议与处理状态；不要把 HTTP 202 当完成。",
            "source_sequences": [1],
        },
        "constraints": [{
            "text": "禁止改凭据；禁止任何业务写入；只做只读证据调查。",
            "source_sequences": [5],
        }],
        "user_assertions": [{
            "text": "早期 API 配置 endpoint=/callback，max_attempts=…；Request ID=req-482；Event ID=evt-731。",
            "source_sequences": [3],
        }],
        "corrections": [{
            "text": "正式更正：Request ID=req-483；req-482 记录错误；Event ID 仍为 evt-731。",
            "source_sequences": [7],
        }],
        "rejected_hypotheses": [],
        "unresolved_items": [{
            "text": "unresolved_receiver_completion=true；Receiver 尚未确认完成。",
            "source_sequences": [16],
        }],
        "timeline": [{
            "text": "协议 v1.2 → v1.3；max_attempts 3 → 5。部署版本未知。",
            "source_sequences": [11],
        }],
    }, ensure_ascii=False, separators=(",", ":"))
    return {
        "content": content,
        "evidence_level": "SYNTHETIC_CONTEXT_BOUND_FIXTURE_NOT_MODEL_OUTPUT",
        "content_sha256": _sha(content),
        "original_response_id": "synthetic-q06b-second-round-context-bound",
    }


def _read_frozen_case_inputs() -> tuple[list[dict[str, object]], dict[str, str], dict[str, dict[str, object]], dict[str, object]]:
    history_raw = (DATASET / "HISTORY_SNAPSHOT.json").read_bytes()
    questions_raw = (DATASET / "QUESTIONS.json").read_bytes()
    assert _sha(history_raw) == HISTORY_SHA256
    assert _sha(questions_raw) == QUESTIONS_SHA256
    history, source_ids, _original_messages, live_response = REPLAY.load_replay()
    questions = json.loads(questions_raw)["questions"]
    # The model adapter receives only these prompt strings; this function does
    # not load Gold, rubric, required fact groups, or scoring rules.
    prompts: dict[str, dict[str, object]] = {}
    for question_id in ("Q02", "Q06"):
        [row] = [item for item in questions if item.get("id") == question_id]
        prompts[question_id] = {
            "prompt_text": str(row["prompt_text"]),
            "question_file_sha256": QUESTIONS_SHA256,
        }
    q02_reply = live_response["response_payload"]["choices"][0]["message"]["content"]
    prompts["Q02-B-FIRST-SUMMARY"] = {
        "content": q02_reply,
        "evidence_level": "SAVED_PROVIDER_RESPONSE_REPLAYED_OFFLINE",
        "original_response_id": REPLAY.RESPONSE_ID,
        "content_sha256": _sha(q02_reply),
        "trace_sha256": REPLAY.TRACE_SHA256,
    }
    return history, source_ids, prompts, {
        "history_file_sha256": HISTORY_SHA256,
        "question_file_sha256": QUESTIONS_SHA256,
        "live_trace_sha256": LIVE_TRACE_SHA256,
        "saved_q02_response_id": REPLAY.RESPONSE_ID,
        "saved_q02_response_content_sha256": _sha(q02_reply),
    }


def _with_message_id(monkeypatch, message_id: str | None, fn, *args, **kwargs):
    if not message_id:
        return fn(*args, **kwargs)
    forced = iter([uuid.UUID(message_id.removeprefix("message-"))])
    uuid4 = uuid.uuid4
    with monkeypatch.context() as patch:
        patch.setattr(uuid, "uuid4", lambda: next(forced, None) or uuid4())
        return fn(*args, **kwargs)


def _serialize_messages(messages) -> list[dict[str, object]]:
    result = []
    role_map = {"ai": "assistant", "human": "user", "system": "system", "tool": "tool"}
    for item in messages:
        role = role_map.get(str(getattr(item, "type", "")), str(getattr(item, "type", "unknown")))
        row: dict[str, object] = {"role": role, "content": item.content}
        if getattr(item, "tool_calls", None):
            row["tool_calls"] = item.tool_calls
        if getattr(item, "tool_call_id", None):
            row["tool_call_id"] = item.tool_call_id
        result.append(row)
    return result


def _tool_json_schema(tool) -> dict[str, object]:
    schema = getattr(tool, "args_schema", None)
    parameters = schema.model_json_schema() if schema is not None and hasattr(schema, "model_json_schema") else {}
    return {
        "type": "function",
        "function": {
            "name": str(getattr(tool, "name", "")),
            "description": str(getattr(tool, "description", "") or ""),
            "parameters": parameters,
        },
    }


class OfflineAssistantFixture(BaseChatModel):
    """A deterministic response source injected into the real Assistant runtime."""

    case_id: str
    summary_replies: list[dict[str, str]]
    answer_text: str
    calls: list[dict[str, object]] = Field(default_factory=list)
    tool_bindings: list[dict[str, object]] = Field(default_factory=list)

    @property
    def _llm_type(self) -> str:
        return "R2_AR04_OFFLINE_ASSISTANT_DOMAIN_FIXTURE"

    def bind_tools(self, tools, **kwargs):
        schemas = [_tool_json_schema(tool) for tool in tools]
        self.tool_bindings.append({
            "tool_choice": kwargs.get("tool_choice"),
            "parallel_tool_calls": kwargs.get("parallel_tool_calls"),
            "tool_schemas": schemas,
            "tool_schema_sha256": _sha(json.dumps(schemas, ensure_ascii=False, sort_keys=True)),
        })
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        serialized = _serialize_messages(messages)
        compression = any(
            role["role"] == "system"
            and "Compress only the supplied conversation into one compact JSON object" in str(role["content"])
            for role in serialized
        )
        stage = "SUMMARY" if compression else "ANSWER"
        assert stage == "SUMMARY" or not any(
            item.get("tool_calls") for item in serialized if item.get("role") == "assistant"
        ), "fixture does not execute tools"
        if stage == "SUMMARY":
            assert self.summary_replies, f"unexpected extra summary request for {self.case_id}"
            reply = self.summary_replies.pop(0)
            content = reply["content"]
            evidence = reply["evidence_level"]
            reply_digest = reply["content_sha256"]
        else:
            content = self.answer_text
            evidence = "SYNTHETIC_FINAL_ANSWER_FIXTURE_NOT_L3"
            reply_digest = _sha(content)
        # Keep the actual Assistant input and the source level of each response.
        self.calls.append({
            "case_id": self.case_id,
            "stage": stage,
            "messages": serialized,
            "estimated_input_tokens_local": estimate_messages_tokens(serialized),
            "reply_evidence_level": evidence,
            "reply_content_sha256": reply_digest,
            "original_response_id": reply.get("original_response_id") if stage == "SUMMARY" else None,
            "finish_reason": "stop",
        })
        local_input = estimate_messages_tokens(serialized)
        output_tokens = estimate_text_tokens(content)
        message = AIMessage(
            content=content,
            id=f"offline-{self.case_id}-{stage.lower()}-{len(self.calls)}",
            response_metadata={"finish_reason": "stop"},
        )
        message.usage_metadata = {
            "input_tokens": local_input,
            "output_tokens": output_tokens,
            "total_tokens": local_input + output_tokens,
        }
        return ChatResult(generations=[ChatGeneration(message=message)])


def _seed_frozen_history(path: Path, identity, session_id: str, worker_id: str,
                         history: list[dict[str, object]], source_ids: dict[str, str], monkeypatch) -> None:
    assert len(history) == 29
    for index in range(0, 28, 2):
        user, prior_assistant = history[index:index + 2]
        seq = str(user["sequence"])
        accepted = _with_message_id(
            monkeypatch, source_ids.get(seq), admit_task_message,
            path, identity, session_id=session_id, task_id=None,
            input_kind="CHAT_READONLY", body=str(user["body"]),
            idempotency_key=f"ar04-integration-{session_id}-{seq}",
        )
        prior_run = str(accepted["run_id"])
        claim_task_run(path, identity, prior_run)
        attempt = chat.prepare_chat_attempt(path, prior_run, worker_id, "offline-frozen-history")
        assert "attempt_id" in attempt, attempt
        chat.persist_chat_chunk(path, worker_id, attempt["attempt_id"], 1, str(prior_assistant["body"]))
        _with_message_id(
            monkeypatch, source_ids.get(str(prior_assistant["sequence"])),
            chat.complete_chat_attempt, path, worker_id, attempt["attempt_id"],
            str(prior_assistant["body"]),
            provider_response_id=f"frozen-history-fixture-{prior_assistant['sequence']}",
            input_tokens=17, output_tokens=9, total_tokens=26,
        )
    last = history[28]
    _with_message_id(
        monkeypatch, source_ids.get(str(last["sequence"])), admit_task_message,
        path, identity, session_id=session_id, task_id=None,
        input_kind="CHAT_READONLY", body=str(last["body"]),
        idempotency_key=f"ar04-integration-{session_id}-{last['sequence']}",
    )


def _summary_document(connection, run_id: str) -> tuple[list[object], object, dict[str, object], dict[str, object]]:
    rows = connection.execute(
        "SELECT * FROM context_summaries WHERE session_id=(SELECT session_id FROM task_runs WHERE run_id=?) "
        "ORDER BY summary_version", (run_id,),
    ).fetchall()
    assert len(rows) == 2
    assert [str(row["state"]) for row in rows] == ["SUPERSEDED", "CURRENT"]
    current = rows[-1]
    document = json.loads(str(current["summary_json"]))
    attempt = connection.execute(
        "SELECT * FROM context_compression_attempts WHERE attempt_id=? AND status='SUCCEEDED'",
        (str(current["source_attempt_id"]),),
    ).fetchone()
    assert attempt is not None
    snapshot = json.loads(str(attempt["source_dependencies_json"]))
    return rows, current, document, snapshot


def _all_items(document: dict[str, object]):
    for field, values in document.items():
        for index, item in enumerate(values if isinstance(values, list) else [values]):
            yield field, index, item


def _matching_item(document: dict[str, object], required: tuple[str, ...]) -> tuple[str, int, dict[str, object]]:
    found = [
        (field, index, item)
        for field, index, item in _all_items(document)
        if isinstance(item, dict) and all(needle in str(item.get("text", "")) for needle in required)
    ]
    assert found, f"required fact missing from compact summary: {required}"
    return found[0]


def _assert_current_fact_sources(path: Path, summary_row, document: dict[str, object],
                                 snapshot: dict[str, object], required: tuple[str, ...]) -> dict[str, object]:
    field, index, item = _matching_item(document, required)
    source_map = snapshot["source_sequence_map"]
    inverse_map = {str(message_id): int(sequence) for sequence, message_id in source_map.items()}
    refs = item.get("source_sequences")
    if not isinstance(refs, list):
        message_ids = item.get("source_message_ids")
        assert isinstance(message_ids, list) and message_ids
        refs = [inverse_map[str(message_id)] for message_id in message_ids]
    assert refs
    observed = []
    with connect(path) as connection:
        if chat._uses_sequence_sources(document):
            actual_ids = chat._summary_sequence_source_ids(connection, summary_row, document)
            assert actual_ids is not None
        for seq in refs:
            message_id = source_map[str(seq)]
            assert message_id in set(snapshot["allowed_message_ids"])
            source = connection.execute(
                "SELECT message_id, sequence, tenant_id, session_id, task_id, role, body "
                "FROM messages WHERE message_id=?", (message_id,),
            ).fetchone()
            assert source is not None
            assert str(source["tenant_id"]) == str(summary_row["tenant_id"])
            assert str(source["session_id"]) == str(summary_row["session_id"])
            assert (str(source["task_id"]) if source["task_id"] is not None else None) == (
                str(summary_row["task_id"]) if summary_row["task_id"] is not None else None
            )
            assert int(source["sequence"]) == int(seq)
            observed.append({
                "sequence": int(seq),
                "message_id": str(source["message_id"]),
                "message_role": str(source["role"]),
                "message_body_sha256": _sha(str(source["body"])),
            })
    return {"field": field, "index": index, "source_messages": observed}


def _create_unowned_scope_probe_messages(path: Path, identity, session_id: str,
                                         last_sequence: int, marker: str) -> str:
    for sequence in range(1, last_sequence + 1):
        accepted = admit_task_message(
            path, identity, session_id=session_id, task_id=None,
            input_kind="CHAT_READONLY", body=f"synthetic scope probe {marker} sequence {sequence}",
            idempotency_key=f"scope-probe-{marker}-{sequence}",
        )
        assert accepted.get("run_id")
    with connect(path) as connection:
        row = connection.execute(
            "SELECT message_id FROM messages WHERE tenant_id=? AND session_id=? AND sequence=? AND task_id IS NULL",
            (identity.tenant_id, session_id, last_sequence),
        ).fetchone()
    assert row is not None
    return str(row["message_id"])


def _scope_probe(path: Path, identity, session_id: str, summary_row, document: dict[str, object],
                 snapshot: dict[str, object], foreign_sequence: int, foreign_id: str,
                 scope_kind: str) -> dict[str, object]:
    attempt_id = str(summary_row["source_attempt_id"])
    altered = copy.deepcopy(document)
    initial_goal = altered["initial_goal"]
    assert isinstance(initial_goal, dict)
    initial_goal["source_sequences"] = [foreign_sequence]
    with connect(path) as connection:
        row = connection.execute(
            "SELECT source_dependencies_json FROM context_compression_attempts WHERE attempt_id=?",
            (attempt_id,),
        ).fetchone()
        original_json = str(row["source_dependencies_json"])
        forged = json.loads(original_json)
        forged["source_sequence_map"][str(foreign_sequence)] = foreign_id
        if foreign_id not in forged["allowed_message_ids"]:
            forged["allowed_message_ids"].append(foreign_id)
        connection.execute(
            "UPDATE context_compression_attempts SET source_dependencies_json=? WHERE attempt_id=?",
            (json.dumps(forged, ensure_ascii=False, sort_keys=True), attempt_id),
        )
        try:
            result = chat._summary_sequence_source_ids(connection, summary_row, altered)
            assert result is None, f"foreign {scope_kind} source was incorrectly resolved"
        finally:
            connection.execute(
                "UPDATE context_compression_attempts SET source_dependencies_json=? WHERE attempt_id=?",
                (original_json, attempt_id),
            )
    return {
        "scope_kind": scope_kind,
        "foreign_source_id_sha256": _sha(foreign_id),
        "foreign_sequence": foreign_sequence,
        "correctly_rejected": True,
        "evidence_level": "ISOLATED_SQLITE_DOMAIN_ADVERSARIAL_SOURCE_MAP_FIXTURE",
    }


def _check_scope_isolation(path: Path, identity, session_id: str, run_id: str,
                           summary_row, document: dict[str, object], snapshot: dict[str, object]) -> list[dict[str, object]]:
    source_map = snapshot["source_sequence_map"]
    target_seq = max(int(value) for value in source_map) + 1
    tenant_b = trusted_identity(path, "support-b")
    assert tenant_b.tenant_id != identity.tenant_id
    probes = []

    other_tenant_session = str(create_session(path, tenant_b)["session_id"])
    foreign_id = _create_unowned_scope_probe_messages(
        path, tenant_b, other_tenant_session, target_seq, "tenant-b",
    )
    probes.append(_scope_probe(
        path, identity, session_id, summary_row, document, snapshot,
        target_seq, foreign_id, "TENANT",
    ))

    other_session = str(create_session(path, identity)["session_id"])
    foreign_id = _create_unowned_scope_probe_messages(
        path, identity, other_session, target_seq, "same-tenant-other-session",
    )
    probes.append(_scope_probe(
        path, identity, session_id, summary_row, document, snapshot,
        target_seq, foreign_id, "SESSION",
    ))

    other_task = create_task_with_initial_run(
        path, identity, session_id=session_id, service_id="orders-demo",
        integration_id="integration-a", ticket_id=f"AR04-SCOPE-{run_id[-8:]}",
        initial_message="Synthetic Task-scope probe; no execution requested.",
        idempotency_key=f"ar04-scope-task-{run_id}",
    )
    task_id = str(other_task["task_id"])
    with connect(path) as connection:
        row = connection.execute(
            "SELECT message_id, sequence FROM messages WHERE task_id=? AND session_id=? AND role='USER' "
            "ORDER BY sequence LIMIT 1", (task_id, session_id),
        ).fetchone()
    assert row is not None
    probes.append(_scope_probe(
        path, identity, session_id, summary_row, document, snapshot,
        int(row["sequence"]), str(row["message_id"]), "TASK",
    ))
    return probes


def _run_case(case_id: str, question_id: str, db_path: Path, checkpoint_path: Path,
              history, source_ids, prompt_rows, prior_mock_replies, monkeypatch):
    reset_fixture(db_path, "S1_POS")
    monkeypatch.setenv("OPSPILOT_CONTEXT_INPUT_BUDGET_TOKENS", "12000")
    monkeypatch.setenv("OPSPILOT_CONTEXT_STRATEGY", "RECENT_WINDOW")
    identity = trusted_identity(db_path, "support-a")
    session_id = str(create_session(db_path, identity)["session_id"])
    worker_id = f"ar04-integration-{case_id.lower()}"
    register_worker_owner(db_path, worker_id, os.getpid())
    with monkeypatch.context() as history_patch:
        history_patch.setattr(chat, "CHAT_RECENT_WINDOW_MESSAGES", 2)
        _seed_frozen_history(db_path, identity, session_id, worker_id, history, source_ids, history_patch)
    monkeypatch.setenv("OPSPILOT_CONTEXT_STRATEGY", "ROLLING_SUMMARY")
    question = str(prompt_rows[question_id]["prompt_text"])
    accepted = admit_task_message(
        db_path, identity, session_id=session_id, task_id=None, input_kind="CHAT_READONLY",
        body=question, idempotency_key=f"ar04-integrated-{case_id}", assistant_core=True,
    )
    run_id = str(accepted["run_id"])
    claim_task_run(db_path, identity, run_id)

    if case_id == "Q02-B":
        summary_replies = [
            prompt_rows["Q02-B-FIRST-SUMMARY"],
            prior_mock_replies["Q02-B:SUMMARY:2"],
        ]
    else:
        summary_replies = [
            prior_mock_replies["Q06-B:SUMMARY:1"],
                _q06_second_round_fixture(),
        ]
    model = OfflineAssistantFixture(
        case_id=case_id,
        summary_replies=copy.deepcopy(summary_replies),
        answer_text=f"SYNTHETIC_FIXTURE_ONLY::{case_id}; not a semantic answer.",
    )
    trace_events: list[dict[str, object]] = []

    def record_trace(event, **values):
        trace_events.append({
            "event": str(event),
            "status": values.get("status"),
            "reason": values.get("reason"),
            "phase": values.get("phase"),
            "error_class": values.get("error_class"),
        })

    outcome = asyncio.run(assistant_runtime.run_assistant(
        db_path, checkpoint_path, worker_id, run_id,
        model=model, trace=record_trace, tool_choice_override="none",
    ))
    assert outcome.get("status") == "SUCCEEDED", outcome
    assert not model.summary_replies, "not all frozen summary fixture replies were consumed"
    assert [item["stage"] for item in model.calls] == ["SUMMARY", "SUMMARY", "ANSWER"]
    assert model.tool_bindings and model.tool_bindings[-1]["tool_choice"] == "none"

    with connect(db_path) as connection:
        attempts = connection.execute(
            "SELECT attempt_no, status, error_class, prompt_digest, summary_id, estimated_input_tokens, "
            "input_tokens, output_tokens, total_tokens "
            "FROM context_compression_attempts WHERE run_id=? ORDER BY attempt_no", (run_id,),
        ).fetchall()
        assert len(attempts) == 2 and all(row["status"] == "SUCCEEDED" for row in attempts)
        answer_attempts = connection.execute(
            "SELECT attempt_id, status, prompt_digest, provider_response_id FROM chat_attempts WHERE run_id=?",
            (run_id,),
        ).fetchall()
        assert len(answer_attempts) == 1 and answer_attempts[0]["status"] == "SUCCEEDED"
        summary_rows, current_summary, document, snapshot = _summary_document(connection, run_id)
        compact_summary_row = summary_rows[0]
        compact_document = json.loads(str(compact_summary_row["summary_json"]))
        compact_source_format = "SEQUENCE" if chat._uses_sequence_sources(compact_document) else "MESSAGE_ID"
        compact_attempt = connection.execute(
            "SELECT source_dependencies_json FROM context_compression_attempts WHERE attempt_id=?",
            (str(compact_summary_row["source_attempt_id"]),),
        ).fetchone()
        compact_snapshot = json.loads(str(compact_attempt["source_dependencies_json"]))
        if compact_source_format == "SEQUENCE":
            compact_resolved_ids = chat._summary_sequence_source_ids(
                connection, compact_summary_row, compact_document,
            )
            assert compact_resolved_ids is not None
        else:
            compact_resolved_ids = chat._summary_source_message_ids(compact_document)
            assert compact_resolved_ids
            assert set(compact_resolved_ids) <= set(compact_snapshot["allowed_message_ids"])
        final_answer = connection.execute(
            "SELECT m.body, m.body_digest FROM chat_run_answers a JOIN messages m ON m.message_id=a.message_id "
            "WHERE a.run_id=?", (run_id,),
        ).fetchone()
        assert final_answer is not None and str(final_answer["body"]).startswith("SYNTHETIC_FIXTURE_ONLY::")
        tool_observation_count = connection.execute(
            "SELECT COUNT(*) FROM assistant_calls WHERE run_id=? AND kind='MCP'", (run_id,),
        ).fetchone()[0]
        business_rows = {
            table: int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
            for table in ("d3_action_intents", "d3_action_ledgers", "d3_approvals", "d3_delivery_records",
                          "s2_handoff_receipts", "s2_handoff_queue_entries")
        }
        assert tool_observation_count == 0
        assert all(value == 0 for value in business_rows.values())
        current_prompt = copy.deepcopy(model.calls[-1]["messages"])
        summary_blocks = [
            str(item["content"]) for item in current_prompt
            if item["role"] == "system" and str(item["content"]).startswith("HISTORICAL SESSION SUMMARY")
        ]
        assert len(summary_blocks) == 1
        summary_context = json.loads(summary_blocks[0].split(": ", 1)[1])
        assert summary_context == document
        resolved_ids = chat._summary_source_message_ids(document)
        assert resolved_ids and set(resolved_ids) <= set(snapshot["allowed_message_ids"])
        summary_rows = connection.execute(
            "SELECT summary_version,state,summary_digest,source_attempt_id,depends_on_summary_id "
            "FROM context_summaries WHERE session_id=? ORDER BY summary_version", (session_id,),
        ).fetchall()
        run_state = connection.execute("SELECT status FROM task_runs WHERE run_id=?", (run_id,)).fetchone()[0]
        mcp_rows = connection.execute(
            "SELECT call_id FROM assistant_calls WHERE run_id=? AND kind='MCP'", (run_id,),
        ).fetchall()
        assert not mcp_rows

    full_prompt_text = json.dumps(current_prompt, ensure_ascii=False, sort_keys=True)
    assert "required_fact_groups" not in full_prompt_text
    assert "scoring_rule" not in full_prompt_text
    assert '"gold"' not in full_prompt_text
    assert question in full_prompt_text

    if case_id == "Q02-B":
        [fact] = [_matching_item(document, ("endpoint=/callback",))]
        assert fact[0] == "user_assertions"
        fact_source = _assert_current_fact_sources(
            db_path, current_summary, document, snapshot, ("endpoint=/callback",),
        )
        # The first compacted projection uses sequence references; after the
        # second persistence pass the current document expands them to message
        # IDs. Assert provenance against the frozen inverse map rather than
        # requiring the storage representation to stay sequence-based.
        assert 3 in {item["sequence"] for item in fact_source["source_messages"]}
        scope_probes = _check_scope_isolation(
            db_path, identity, session_id, run_id, compact_summary_row, compact_document, compact_snapshot,
        )
        fact_status = "FULL"
    else:
        fact = _matching_item(document, ("v1.2", "v1.3", "max_attempts", "3", "5"))
        assert fact[0] == "timeline"
        fact_source = _assert_current_fact_sources(
            db_path, current_summary, document, snapshot,
            ("v1.2", "v1.3", "max_attempts", "3", "5"),
        )
        assert 11 in {item["sequence"] for item in fact_source["source_messages"]}
        [early] = [
            item for item in document["user_assertions"]
            if "endpoint=/callback" in item["text"] and "max_attempts" in item["text"]
        ]
        assert "max_attempts=…" in early["text"]
        early_source = _assert_current_fact_sources(
            db_path, current_summary, document, snapshot,
            ("endpoint=/callback", "max_attempts=…"),
        )
        assert 3 in {item["sequence"] for item in early_source["source_messages"]}
        scope_probes = []
        fact_status = "FULL_TRANSITION_WITH_EARLY_SEQ3_PARTIAL"

    estimated_prompt_tokens = estimate_messages_tokens(current_prompt)
    return {
        "case_id": case_id,
        "question_id": question_id,
        "strategy": "ROLLING_SUMMARY",
        "run_status": str(run_state),
        "assistant_outcome": outcome,
        "evidence_level": "ASSISTANT_DOMAIN_PATH_WITH_OFFLINE_FIXTURE_AND_SAVED_RESPONSE_REPLAY",
        "provider_requests": 0,
        "external_mcp_calls": 0,
        "assistant_tool_executions": int(tool_observation_count),
        "summary_attempts": [dict(row) for row in attempts],
        "summary_versions": [dict(row) for row in summary_rows],
        "first_persisted_summary_source_format": compact_source_format,
        "answer_attempts": [dict(row) for row in answer_attempts],
        "current_summary": document,
        "current_summary_digest": str(current_summary["summary_digest"]),
        "source_sequence_map": snapshot["source_sequence_map"],
        "resolved_source_message_ids": sorted(set(resolved_ids)),
        "target_fact_status": fact_status,
        "target_fact_source_check": fact_source,
        "scope_isolation_probes": scope_probes,
        "final_answer_fixture": str(final_answer["body"]),
        "final_prompt": current_prompt,
        "final_prompt_estimated_tokens_local": estimated_prompt_tokens,
        "final_prompt_sha256": _sha(json.dumps(current_prompt, ensure_ascii=False, sort_keys=True)),
        "fixture_calls": model.calls,
        "tool_choice": model.tool_bindings[-1]["tool_choice"],
        "tool_schema_sha256": model.tool_bindings[-1]["tool_schema_sha256"],
        "business_write_counts": business_rows,
        "assistant_trace_event_names": [row["event"] for row in trace_events],
        "gold_and_rubric_leakage_markers_absent": True,
    }


def test_q02b_q06b_through_normal_assistant_domain_path_and_scope_checks(
    tmp_path: Path, monkeypatch,
):
    history, source_ids, prompt_rows, input_provenance = _read_frozen_case_inputs()
    prior_mock_replies, prior_mock_provenance = _read_prior_mock_replies()
    output_dir_value = os.environ.get("OPSPILOT_AR04_INTEGRATION_OUTPUT", "").strip()
    output_dir = Path(output_dir_value).resolve() if output_dir_value else None
    if output_dir is not None:
        assert not output_dir.exists(), "refusing to overwrite an existing evidence run directory"

    results = []
    for case_id, question_id in (("Q02-B", "Q02"), ("Q06-B", "Q06")):
        results.append(_run_case(
            case_id, question_id,
            tmp_path / f"{case_id.lower()}-domain.sqlite3",
            tmp_path / f"{case_id.lower()}-checkpoint.sqlite3",
            history, source_ids, prompt_rows, prior_mock_replies, monkeypatch,
        ))

    assert len(results) == 2
    assert all(len(row["summary_attempts"]) == 2 for row in results)
    assert all(row["run_status"] == "SUCCEEDED" for row in results)
    assert all(row["provider_requests"] == 0 for row in results)
    assert results[0]["target_fact_status"] == "FULL"
    assert results[1]["target_fact_status"] == "FULL_TRANSITION_WITH_EARLY_SEQ3_PARTIAL"
    assert len(results[0]["scope_isolation_probes"]) == 3
    assert all(row["correctly_rejected"] for row in results[0]["scope_isolation_probes"])

    calls = [call for case in results for call in case["fixture_calls"]]
    assert len(calls) == 6
    assert sum(call["stage"] == "SUMMARY" for call in calls) == 4
    assert sum(call["stage"] == "ANSWER" for call in calls) == 2
    output = {
        "schema_version": 1,
        "status": "PASS_OFFLINE_INTEGRATION_ONLY",
        "evidence_level": "SAVED_PROVIDER_RESPONSE_REPLAY_PLUS_PRIOR_MOCK_FIXTURES_PLUS_TEMP_SQLITE_DOMAIN",
        "frozen_production_chat_blob": "6a57360de6f5579fa65dc008de4fcf37148c43f0",
        "provider_requests": 0,
        "external_mcp_calls": 0,
        "real_authorization_created": False,
        "production_database_writes": 0,
        "fixture_dispatches": 6,
        "summary_fixture_dispatches": 4,
        "answer_fixture_dispatches": 2,
        "input_provenance": input_provenance,
        "prior_mock_provenance": prior_mock_provenance,
        "cases": results,
        "l3_semantic_evaluation": "NOT_RUN_FIXTURE_OUTPUT_IS_NOT_MODEL_EVIDENCE",
        "old_runner_compatibility": "REQUIRES_NEW_VERSION_BINDING; OLD_RUNNER_PINS_PRE_FIX_CHAT_BLOB",
    }

    if output_dir is not None:
        output_dir.mkdir(parents=True)
        (output_dir / "RESULTS.json").write_text(
            json.dumps(output, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8",
        )
        final_prompts = {
            case["case_id"]: {
                "evidence_level": "CAPTURED_INPUT_TO_INJECTED_ASSISTANT_FIXTURE_NOT_PROVIDER_WIRE",
                "messages": case["final_prompt"],
                "estimated_tokens_local": case["final_prompt_estimated_tokens_local"],
                "sha256": case["final_prompt_sha256"],
                "tool_choice": case["tool_choice"],
                "tool_schema_sha256": case["tool_schema_sha256"],
            }
            for case in results
        }
        (output_dir / "FINAL_PROMPTS.json").write_text(
            json.dumps(final_prompts, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8",
        )
    assert all(call["reply_evidence_level"] in {
        "SAVED_PROVIDER_RESPONSE_REPLAYED_OFFLINE", "PRIOR_MOCK_TRACE_REPLY",
        "SYNTHETIC_CONTEXT_BOUND_FIXTURE_NOT_MODEL_OUTPUT",
        "SYNTHETIC_FINAL_ANSWER_FIXTURE_NOT_L3",
    } for call in calls)
