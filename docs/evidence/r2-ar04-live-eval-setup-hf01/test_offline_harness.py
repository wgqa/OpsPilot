from __future__ import annotations

import asyncio
import gzip
import hashlib
import json
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import pytest


ROOT = Path(__file__).resolve().parents[3]
EVIDENCE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(EVIDENCE_DIR))

from test_m302_context import _turn  # noqa: E402

from opspilot.domain import chat as chat_domain  # noqa: E402
from opspilot.domain.assistant_runtime_grant import (  # noqa: E402
    bind_run,
    provision_default_grant,
    runtime_config_from_env,
    spend_summary,
    validate_run_binding,
)
from opspilot.domain.chat import get_chat_manifest  # noqa: E402
from opspilot.domain.database import connect, reset_fixture  # noqa: E402
from opspilot.domain.d2 import canonical_json  # noqa: E402
from opspilot.domain.task_control import (  # noqa: E402
    admit_task_message,
    claim_task_run,
    create_session,
    register_worker_owner,
    trusted_identity,
)


MODEL_CONFIG = {
    "OPSPILOT_MODEL_NAME": "deepseek-flash",
    "OPSPILOT_MODEL_BASE_URL": "https://api.deepseek.com",
    "OPSPILOT_MODEL_CONFIG_VERSION": "offline-eval-setup-v1",
    "OPSPILOT_MODEL_PRICE_VERSION": "offline-fixture-price-v1",
    "OPSPILOT_ASSISTANT_SERVICE_IDENTITY": "offline-eval-setup-service",
}
RECALL_QUESTION_IDS = ("Q02", "Q03", "Q06", "Q07", "Q08", "Q10", "Q12")
STRATEGIES = {"A": "HYBRID", "B": "ROLLING_SUMMARY", "C": "RECENT_WINDOW"}
RESULT_FILE = EVIDENCE_DIR / "TEST_RESULTS.json"
TRACE_FILE = EVIDENCE_DIR / "MOCK_TRACE.jsonl.gz"


def _sha(value: bytes | str) -> str:
    data = value if isinstance(value, bytes) else value.encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def _load_frozen_inputs() -> tuple[list[dict], dict[str, dict], str, str]:
    history_path = ROOT / "docs/evidence/r2-ar04-long-context-journey-01/HISTORY_SNAPSHOT.json"
    questions_path = ROOT / "docs/evidence/r2-ar04-long-context-journey-01/QUESTIONS.json"
    history_doc = json.loads(history_path.read_text(encoding="utf-8"))
    questions_doc = json.loads(questions_path.read_text(encoding="utf-8"))
    history = history_doc["recreated_shared_history_rows"]
    questions = {item["id"]: item for item in questions_doc["questions"]}
    assert len(history) == 29
    assert all(_sha(row["body"]) == row["recreated_body_digest"] for row in history)
    assert questions_doc["prompt_leakage_rule"].startswith("Only question.prompt_text")
    history_digest = _sha("\n".join(row["body"] for row in history))
    return history, questions, history_digest, _sha(questions_path.read_bytes())


def _provision_isolated_grant(db_path: Path) -> dict:
    now = datetime.now(timezone.utc)
    return provision_default_grant(
        db_path,
        grant_source="offline-only Runtime Grant fixture",
        operator_id="test-local-operator",
        service_identity=MODEL_CONFIG["OPSPILOT_ASSISTANT_SERVICE_IDENTITY"],
        model_id=MODEL_CONFIG["OPSPILOT_MODEL_NAME"],
        endpoint=MODEL_CONFIG["OPSPILOT_MODEL_BASE_URL"],
        model_config_version=MODEL_CONFIG["OPSPILOT_MODEL_CONFIG_VERSION"],
        price_version=MODEL_CONFIG["OPSPILOT_MODEL_PRICE_VERSION"],
        input_rate_micro_per_million=1_000_000,
        output_rate_micro_per_million=1_000_000,
        max_input_tokens=12_000,
        max_output_tokens=512,
        total_limit_usd_micro=1_000_000,
        valid_from=(now - timedelta(days=1)).isoformat().replace("+00:00", "Z"),
        expires_at=(now + timedelta(days=1)).isoformat().replace("+00:00", "Z"),
        evidence_ref="offline-only test fixture",
        evidence_digest="a" * 64,
        idempotency_key="offline-eval-setup-grant-v1",
    )


def _seed_domain(db_path: Path, owner: str, history: list[dict], question: str) -> tuple[str, str, int, dict]:
    reset_fixture(db_path, "S1_POS")
    identity = trusted_identity(db_path, "support-a")
    session_id = str(create_session(db_path, identity)["session_id"])
    worker_epoch = register_worker_owner(db_path, owner, os.getpid())

    # Use the normal Domain chat APIs to persist the frozen source rows. The
    # smaller temporary preparation window only prevents those fixture writes
    # from recursively summarizing; it is restored before the actual run.
    original_window = chat_domain.CHAT_RECENT_WINDOW_MESSAGES
    chat_domain.CHAT_RECENT_WINDOW_MESSAGES = 2
    os.environ["OPSPILOT_CONTEXT_STRATEGY"] = "RECENT_WINDOW"
    try:
        for index in range(0, 28, 2):
            _turn(
                db_path,
                session_id,
                owner,
                history[index]["body"],
                key=f"offline-history-{index + 1}",
                answer=history[index + 1]["body"],
            )
        # The frozen 29th row is the latest user observation without an
        # assistant answer; keep that exact shape before adding the question.
        admit_task_message(
            db_path,
            identity,
            session_id=session_id,
            task_id=None,
            input_kind="CHAT_READONLY",
            body=history[28]["body"],
            idempotency_key="offline-history-29",
        )
        accepted = admit_task_message(
            db_path,
            identity,
            session_id=session_id,
            task_id=None,
            input_kind="CHAT_READONLY",
            body=question,
            idempotency_key="offline-current-question",
            assistant_core=True,
        )
    finally:
        chat_domain.CHAT_RECENT_WINDOW_MESSAGES = original_window

    run_id = str(accepted["run_id"])
    claim_task_run(db_path, identity, run_id)
    with connect(db_path) as connection:
        rows = connection.execute(
            "SELECT sequence, role, body FROM messages WHERE session_id=? ORDER BY sequence",
            (session_id,),
        ).fetchall()
        actual = [{"sequence": int(row["sequence"]), "role": str(row["role"]), "body": str(row["body"])}
                  for row in rows[:29]]
        assert [row["body"] for row in actual] == [row["body"] for row in history]
        assert len(rows) == 30 and rows[-1]["body"] == question
    return session_id, run_id, worker_epoch, identity


def _summary_response(db_path: Path, run_id: str) -> str:
    with connect(db_path) as connection:
        row = connection.execute(
            """SELECT source_dependencies_json FROM context_compression_attempts
               WHERE run_id=? AND status='RESERVED' ORDER BY created_at DESC LIMIT 1""",
            (run_id,),
        ).fetchone()
    assert row is not None, "summary request must have a persisted compression attempt"
    dependencies = json.loads(str(row["source_dependencies_json"]))
    sequences = sorted(int(item) for item in dependencies["source_sequence_map"])
    assert sequences
    first_sequence = sequences[0]
    summary = {
        "initial_goal": {
            "text": "Offline fixture summary; source-linked Domain compression path only.",
            "source_sequences": [first_sequence],
        },
        "constraints": [],
        "user_assertions": [],
        "corrections": [],
        "rejected_hypotheses": [],
        "unresolved_items": [],
        "timeline": [],
    }
    return json.dumps(summary, ensure_ascii=False)


async def _run_case(
    *, case_root: Path, case_id: str, group: str, strategy: str,
    track: str, question_id: str, question_row: dict, history: list[dict],
    history_digest: str, monkeypatch,
) -> tuple[dict, list[dict]]:
    from opspilot.assistant import create_assistant_model, run_assistant

    db_path = case_root / "domain.sqlite3"
    checkpoint_path = case_root / "checkpoint.sqlite3"
    case_root.mkdir(parents=True, exist_ok=True)
    owner = f"offline-eval-{case_id}"
    for key, value in MODEL_CONFIG.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("OPSPILOT_CONTEXT_INPUT_BUDGET_TOKENS", "12000")
    monkeypatch.setenv("OPSPILOT_ASSISTANT_RUNTIME_ENABLED", "1")
    monkeypatch.setenv("OPSPILOT_ASSISTANT_PROVIDER_ENABLED", "1")
    monkeypatch.setenv("OPSPILOT_MODEL_API_KEY", "offline-only-not-a-real-key")
    monkeypatch.delenv("OPSPILOT_ASSISTANT_EXPERIMENT_ID", raising=False)
    monkeypatch.setenv("OPSPILOT_CONTEXT_STRATEGY", strategy)

    session_id, run_id, worker_epoch, identity = _seed_domain(
        db_path, owner, history, str(question_row["prompt_text"]),
    )
    # Restore the selected strategy after fixture seeding used RECENT_WINDOW.
    monkeypatch.setenv("OPSPILOT_CONTEXT_STRATEGY", strategy)
    grant = _provision_isolated_grant(db_path)
    binding = bind_run(db_path, run_id, runtime_config_from_env())
    validated_binding = validate_run_binding(db_path, run_id, binding, runtime_config_from_env())
    assert validated_binding["database_file_identity"] == binding["database_file_identity"]

    mock_calls: list[dict] = []
    trace_events: list[dict] = []
    tool_call_sent = False

    async def respond(request: httpx.Request) -> httpx.Response:
        nonlocal tool_call_sent
        payload = json.loads((await request.aread()).decode("utf-8"))
        assert request.url.host == "api.deepseek.com"
        assert payload.get("model") == "deepseek-flash"
        assert int(payload.get("max_tokens", 0)) == 512
        serialized = canonical_json(payload)
        assert str(question_row["scoring_rule"]) not in serialized
        assert canonical_json(question_row["gold"]) not in serialized
        assert "offline-only-not-a-real-key" not in serialized

        input_tokens = (
            __import__("opspilot.domain.context_engineering", fromlist=["estimate_messages_tokens"])
            .estimate_messages_tokens(payload["messages"])
            + __import__("opspilot.domain.context_engineering", fromlist=["estimate_text_tokens"])
            .estimate_text_tokens(canonical_json(payload.get("tools", [])))
            + 64
        )
        assert 0 < input_tokens <= 12_000
        system_text = "\n".join(
            str(message.get("content", "")) for message in payload.get("messages", [])
            if message.get("role") == "system"
        )
        system_prefix = system_text.split("\nWORK_CONTEXT\n", 1)[0] if not system_text.startswith("Compress only") else None
        is_summary = system_text.startswith("Compress only the supplied conversation")
        if is_summary:
            content = _summary_response(db_path, run_id)
            message = {"role": "assistant", "content": content}
            finish_reason = "stop"
        elif track == "agent_investigation" and not tool_call_sent:
            assert payload.get("tool_choice") == "auto"
            assert any(
                item.get("function", {}).get("name") == "list_scoped_protocol_documents"
                for item in payload.get("tools", [])
            )
            tool_call_sent = True
            message = {
                "role": "assistant",
                "content": None,
                "tool_calls": [{
                    "id": "offline-tool-call-1",
                    "type": "function",
                    "function": {
                        "name": "list_scoped_protocol_documents",
                        "arguments": json.dumps({"topic": "callback"}),
                    },
                }],
            }
            finish_reason = "tool_calls"
        else:
            if track == "history_recall":
                assert payload.get("tool_choice") == "none"
            content = f"MOCK_ONLY::{group}::{question_id}::{track}"
            message = {"role": "assistant", "content": content}
            finish_reason = "stop"

        response_payload = {
            "id": f"offline-mock-{case_id}-{len(mock_calls) + 1}",
            "object": "chat.completion",
            "created": 1,
            "model": "deepseek-flash",
            "choices": [{"index": 0, "message": message, "finish_reason": finish_reason}],
            "usage": {"prompt_tokens": input_tokens, "completion_tokens": 24, "total_tokens": input_tokens + 24},
        }
        mock_calls.append({
            "case_id": case_id,
            "group": group,
            "strategy": strategy,
            "track": track,
            "request_payload": payload,
            "response_payload": response_payload,
            "request_body_sha256": _sha(serialized),
            "model_id": payload.get("model"),
            "system_prompt_prefix_sha256": _sha(system_prefix) if system_prefix else None,
            "input_tokens": input_tokens,
            "output_tokens": 24,
            "request_transport": "httpx.MockTransport",
            "authorization_header_recorded": False,
        })
        return httpx.Response(200, json=response_payload)

    def forbidden_sync_request(_request: httpx.Request) -> httpx.Response:
        raise AssertionError("The offline harness must never use the non-mocked synchronous transport.")

    async_transport = httpx.MockTransport(respond)
    sync_transport = httpx.MockTransport(forbidden_sync_request)
    model = create_assistant_model(
        runtime_grant_binding=binding,
        transport_async=async_transport,
        transport_sync=sync_transport,
    )
    assert model is not None
    try:
        result = await run_assistant(
            db_path,
            checkpoint_path,
            owner,
            run_id,
            model=model,
            runtime_grant_binding=binding,
            worker_epoch=worker_epoch,
            tool_choice_override="none" if track == "history_recall" else None,
            trace=lambda event, **fields: trace_events.append({"event": event, **fields}),
        )
    finally:
        await model.http_async_client.aclose()
        model.http_client.close()

    assert result["status"] == "SUCCEEDED", result
    manifest = get_chat_manifest(db_path, identity, run_id)
    strategy_calls = [item for item in mock_calls if item["case_id"] == case_id]
    summary_calls = [item for item in strategy_calls if item["request_payload"].get("messages", [{}])[0].get("content", "").startswith("Compress only the supplied conversation")]
    summary_rows = manifest["compression_attempts"]
    if strategy == "RECENT_WINDOW":
        assert not summary_calls and not summary_rows
    else:
        assert summary_calls and summary_rows
        assert all(item["status"] == "SUCCEEDED" and item["summary_id"] for item in summary_rows)
    answer_calls = [item for item in strategy_calls if item not in summary_calls]
    assert answer_calls
    tool_observations = [item for item in trace_events if item["event"] == "tool_observation"]
    if track == "history_recall":
        assert not any("tool_calls" in call["response_payload"]["choices"][0]["message"] for call in answer_calls)
        assert not tool_observations
        choices = {call["request_payload"].get("tool_choice") for call in answer_calls}
        assert choices == {"none"}
    else:
        assert tool_call_sent
        assert any(item.get("name") == "list_scoped_protocol_documents" for item in tool_observations)
        assert all(call["request_payload"].get("tool_choice") == "auto" for call in answer_calls)

    latest = manifest["attempts"][-1]["manifest"]
    assert int(manifest["context_budget"]["configured_input_limit_tokens"]) == 12_000
    selected_message_ids = latest["selected_message_ids"]
    assert selected_message_ids
    full_request_text = canonical_json([call["request_payload"] for call in answer_calls])
    assert str(question_row["prompt_text"]) in full_request_text
    assert "MOCK_ONLY::" not in full_request_text
    case_record = {
        "case_id": case_id,
        "domain_instance_sha256": _sha(str(db_path.resolve())),
        "checkpoint_instance_sha256": _sha(str(checkpoint_path.resolve())),
        "group": group,
        "strategy": strategy,
        "track": track,
        "question_id": question_id,
        "question_prompt_sha256": _sha(str(question_row["prompt_text"])),
        "history_digest_sha256": history_digest,
        "history_rows": 29,
        "history_row_digests_match_frozen_recreation": True,
        "domain_db_isolated": True,
        "checkpoint_isolated": True,
        "grant_status": grant["status"],
        "grant_max_input_tokens": int(grant["max_input_tokens"]),
        "grant_max_output_tokens": int(grant["max_output_tokens"]),
        "runtime_binding_db_identity_matches": validated_binding["database_file_identity"] == binding["database_file_identity"],
        "run_binding_persisted": True,
        "run_status": result["status"],
        "configured_input_limit_tokens": int(manifest["context_budget"]["configured_input_limit_tokens"]),
        "effective_context_input_budget_tokens": int(manifest["context_budget"]["input_budget_tokens"]),
        "selected_message_ids": selected_message_ids,
        "summary_attempt_count": len(summary_rows),
        "summary_attempts": summary_rows,
        "summary_refs": manifest["summary_refs"],
        "answer_manifest_context_blocks": latest["context_blocks"],
        "answer_estimated_input_tokens": latest["context_budget"].get("estimated_input_tokens"),
        "answer_wire_request_count": len(answer_calls),
        "answer_tool_choice_values": sorted({str(call["request_payload"].get("tool_choice")) for call in answer_calls}),
        "tool_schema_sha256": _sha(canonical_json(answer_calls[0]["request_payload"].get("tools", []))),
        "system_prompt_prefix_sha256": answer_calls[0]["system_prompt_prefix_sha256"],
        "model_id": MODEL_CONFIG["OPSPILOT_MODEL_NAME"],
        "tool_schema_name_count": len(answer_calls[0]["request_payload"].get("tools", [])),
        "local_readonly_mcp_calls": len(tool_observations),
        "external_mcp_calls": 0,
        "gold_payload_serialized": False,
        "scoring_rule_serialized": False,
        "other_question_mock_answers_in_prompt": False,
        "spend_ledger_simulated_usd_micro": spend_summary(db_path)["committed_or_reserved_usd_micro"],
        "semantic_assessment": "NOT_SCORED_MOCK_OUTPUT",
        "evidence_level": "FIXTURE_AND_MOCK_PROVIDER_TRANSPORT",
    }
    return case_record, mock_calls


def _run_isolated_grant_backed_cases(case_tmp: Path, monkeypatch) -> None:
    history, questions, history_digest, questions_file_sha = _load_frozen_inputs()
    case_records: list[dict] = []
    raw_calls: list[dict] = []
    calls_by_group_track_question: dict[tuple[str, str, str], dict] = {}
    comparison_records: list[dict] = []

    # Track 1: all fixed recall questions, with the real Assistant tool schema
    # present and tool_choice=none on every outbound answer request.
    for group, strategy in STRATEGIES.items():
        for question_id in RECALL_QUESTION_IDS:
            case_id = f"{group}-{question_id}-recall"
            record, calls = asyncio.run(_run_case(
                case_root=case_tmp / case_id,
                case_id=case_id,
                group=group,
                strategy=strategy,
                track="history_recall",
                question_id=question_id,
                question_row=questions[question_id],
                history=history,
                history_digest=history_digest,
                monkeypatch=monkeypatch,
            ))
            case_records.append(record)
            raw_calls.extend(calls)
            calls_by_group_track_question[(group, "history_recall", question_id)] = record

    # Track 2: one shared question per strategy proves that auto selection is
    # retained and that only the app's local read-only MCP fixture runs.
    for group, strategy in STRATEGIES.items():
        question_id = "Q06"
        case_id = f"{group}-{question_id}-agent"
        record, calls = asyncio.run(_run_case(
            case_root=case_tmp / case_id,
            case_id=case_id,
            group=group,
            strategy=strategy,
            track="agent_investigation",
            question_id=question_id,
            question_row=questions[question_id],
            history=history,
            history_digest=history_digest,
            monkeypatch=monkeypatch,
        ))
        case_records.append(record)
        raw_calls.extend(calls)
        calls_by_group_track_question[(group, "agent_investigation", question_id)] = record

    # Strategy comparisons share exact frozen material and model/tool contract.
    for track, question_id in [("history_recall", qid) for qid in RECALL_QUESTION_IDS] + [("agent_investigation", "Q06")]:
        rows = [calls_by_group_track_question[(group, track, question_id)] for group in STRATEGIES]
        assert len({row["history_digest_sha256"] for row in rows}) == 1
        assert len({row["question_prompt_sha256"] for row in rows}) == 1
        assert len({row["tool_schema_sha256"] for row in rows}) == 1
        assert len({row["system_prompt_prefix_sha256"] for row in rows}) == 1
        assert {row["model_id"] for row in rows} == {"deepseek-flash"}
        assert {row["configured_input_limit_tokens"] for row in rows} == {12_000}
        effective = {row["group"]: row["effective_context_input_budget_tokens"] for row in rows}
        comparison_records.append({
            "track": track,
            "question_id": question_id,
            "same_history_digest": True,
            "same_question_digest": True,
            "same_tool_schema_digest": True,
            "same_system_prompt_prefix_digest": True,
            "same_configured_input_limit_tokens": True,
            "configured_input_limit_tokens": 12_000,
            "effective_context_budget_by_group": effective,
            "effective_context_budget_range_tokens": max(effective.values()) - min(effective.values()),
            "evidence_level": "FIXTURE_AND_MOCK_PROVIDER_TRANSPORT",
        })

    assert len({row["case_id"] for row in case_records}) == len(case_records)
    assert len({row["domain_instance_sha256"] for row in case_records}) == len(case_records)
    assert len({row["checkpoint_instance_sha256"] for row in case_records}) == len(case_records)
    assert all(row["domain_db_isolated"] and row["checkpoint_isolated"] for row in case_records)
    assert all(row["run_status"] == "SUCCEEDED" for row in case_records)
    assert all(call["request_transport"] == "httpx.MockTransport" for call in raw_calls)
    assert all(call["authorization_header_recorded"] is False for call in raw_calls)

    summary = {
        "schema_version": 1,
        "task": "R2-AR04-LIVE-EVAL-SETUP-HF-01",
        "status": "OFFLINE_MOCK_FULL_PATHS_READY",
        "evidence_level": "FIXTURE_AND_MOCK_PROVIDER_TRANSPORT",
        "base_inputs": {
            "history_snapshot_sha256": _sha((ROOT / "docs/evidence/r2-ar04-long-context-journey-01/HISTORY_SNAPSHOT.json").read_bytes()),
            "questions_sha256": questions_file_sha,
            "pre_question_rows": 29,
            "history_digest_sha256": history_digest,
            "recall_question_ids": list(RECALL_QUESTION_IDS),
            "agent_investigation_question_ids": ["Q06"],
        },
        "provider_requests": 0,
        "mock_transport_requests": len(raw_calls),
        "real_provider_cost_usd": 0,
        "persistent_or_production_grants_created": 0,
        "production_database_accessed": False,
        "external_mcp_calls": 0,
        "strategy_comparisons": comparison_records,
        "cases": case_records,
    }
    RESULT_FILE.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    with gzip.open(TRACE_FILE, "wt", encoding="utf-8", newline="\n") as stream:
        for call in raw_calls:
            stream.write(json.dumps(call, ensure_ascii=False, separators=(",", ":")) + "\n")

    assert _sha((ROOT / "docs/evidence/r2-ar04-long-context-journey-01/HISTORY_SNAPSHOT.json").read_bytes()) == summary["base_inputs"]["history_snapshot_sha256"]


def test_isolated_grant_backed_abc_and_two_tracks(monkeypatch) -> None:
    # The runner uses a unique temp root beneath this new evidence directory,
    # avoiding dependence on a machine-wide pytest temp directory ACL.
    with tempfile.TemporaryDirectory(prefix="isolated-mock-", dir=EVIDENCE_DIR) as temp:
        _run_isolated_grant_backed_cases(Path(temp), monkeypatch)


def test_new_scorer_separates_rules_and_preliminary_semantics() -> None:
    from score_preliminary import build_supplement

    source_path = ROOT / "docs/evidence/r2-ar04-live-semantic-pilot-01/RESULTS.json"
    source = json.loads(source_path.read_text(encoding="utf-8"))
    result = build_supplement(source)
    encoded = json.dumps(result, ensure_ascii=False)
    assert result["status"] == "IMPLEMENTER_PRELIMINARY_REVIEW"
    assert result["independent_main_agent_review"] == "NOT_PERFORMED"
    assert len(result["rows"]) == 2
    assert "REVIEWED_BY_MAIN_AGENT" not in encoded
    assert all(row["manual_semantic_score"]["status"] == "IMPLEMENTER_PRELIMINARY_REVIEW" for row in result["rows"])
    assert all("deterministic_rule_score" in row and "manual_semantic_score" in row for row in result["rows"])
