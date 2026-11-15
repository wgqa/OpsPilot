from __future__ import annotations

import copy
import gzip
import json
import sys
from pathlib import Path

import httpx
import pytest

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import run_v2


def _json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _events(path: Path):
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def _case(result, case_id):
    return next(row for row in result["cases"] if row["case_id"] == case_id)


def test_full_mock_matrix_runs_current_assistant_and_persists_two_summaries(tmp_path):
    output = tmp_path / "success"
    result = run_v2.run_mock(output)
    assert result["case_matrix_passed"] is True
    assert result["base_sha"] == run_v2.BASE_SHA
    assert result["production_blob_pins"] == {
        "opspilot/domain/chat.py": run_v2.CHAT_BLOB,
        "opspilot/assistant.py": run_v2.ASSISTANT_BLOB,
    }
    assert result["frozen_history_rows_per_case"] == 29
    assert result["recorded_requests"] == 9
    assert result["summary_requests"] == 6
    assert result["answer_requests"] == 3
    assert result["provider_requests_sent"] == 0
    assert result["provider_cost_usd"] == "0.00"
    assert result["external_mcp_calls"] == 0
    assert result["live_dispatch_available"] is False
    assert len(_events(output / "MOCK_TRACE.jsonl.gz")) == 18

    cases = result["cases"]
    for case in cases:
        assert case["status"] == "SUCCEEDED"
        assert case["summary_calls"] == 2 and case["answer_calls"] == 1
        assert case["answer_tool_choice"] == "none"
        assert case["mcp_attempts"] == 0
        assert len(case["persisted_summaries"]) == 2
        assert case["persisted_summaries"][-1]["state"] == "CURRENT"
        assert all(item["status"] == "SUCCEEDED" for item in case["recorded_compression_attempt_states"])
        assert all(
            case["provider_stage_and_prompt_visibility"][phase]["visibility"] == "COMPLETE_TEXT_WITH_SOURCE"
            for phase in ("first_persisted_summary", "second_summary_input", "second_model_summary", "final_answer_summary")
        )
    for identity in ("domain_instance_sha256", "checkpoint_instance_sha256", "session_id_sha256",
                     "run_id_sha256", "runtime_grant_id_sha256"):
        assert len({case[identity] for case in cases}) == 3

    q02a_first = next(
        item for item in result["mock_reply_provenance"]
        if item["case_id"] == "Q02-A" and item["logical_sequence"] == 1
    )
    assert q02a_first["origin"] == "FROZEN_HISTORICAL_LIVE_SUMMARY"
    assert q02a_first["historical_response_id"] == "c3435ff4-fc27-4ffb-b053-bbfcabc600e0"
    assert q02a_first["historical_content_sha256"] == run_v2.FROZEN_FIRST_SUMMARY_SHA256["Q02-A"]
    assert q02a_first["historical_reply_source"] == run_v2.FROZEN_REPLY_SOURCES["Q02-A"]
    assert q02a_first["historical_reply_source"]["trace_path"].endswith(
        "r2-ar04-live-retention-recheck-01/live_run_01/LIVE_REQUESTS.jsonl.gz"
    )
    assert q02a_first["historical_response_body_sha256"] == run_v2.FROZEN_REPLY_SOURCES["Q02-A"]["response_body_sha256"]
    assert q02a_first["historical_summary_text_sha256"] == run_v2.FROZEN_FIRST_SUMMARY_SHA256["Q02-A"]
    q02a_first_send = next(
        event for event in _events(output / "MOCK_TRACE.jsonl.gz")
        if event.get("event") == "RESPONSE_RECEIVED" and event.get("logical_id") == "Q02-A:SUMMARY:1"
    )
    q02a_first_body = q02a_first_send["response_payload"]["choices"][0]["message"]["content"]
    assert run_v2.sha256(q02a_first_body) == run_v2.FROZEN_REPLY_SOURCES["Q02-A"]["summary_text_sha256"]
    first_document = _case(result, "Q02-A")["persisted_summaries"][0]["document_by_sequence"]
    assert any("endpoint=/callback" in item["text"] and item["source_sequences"] == [3]
               for item in first_document["user_assertions"])
    assert any("req-483" in item["text"] and item["source_sequences"] == [7]
               for item in first_document["corrections"])
    assert any("v1.2" in item["text"] and "v1.3" in item["text"] and item["source_sequences"] == [11]
               for item in first_document["timeline"])
    assert all(item["origin"] != "REAL_PROVIDER_CALL_IN_THIS_RUN" for item in result["mock_reply_provenance"])

    q06 = _case(result, "Q06-B")
    diagnostics = q06["fact_scope_diagnostics"]
    assert diagnostics["max_attempts_early_value_seq3"]["status"] == "PARTIAL"
    assert diagnostics["protocol_and_max_attempts_transition_seq11"]["status"] == "COMPLETE_TEXT_WITH_SOURCE"
    protected = run_v2.assert_frozen()["protected_historical_sha256"]
    assert all(item["matches_base"] for item in protected.values())
    assert "docs/evidence/r2-ar04-compaction-c06-hf01/RED_REPRO_TRACE.json" in protected
    assert "docs/evidence/r2-ar04-base-diff-edge-gate-hf02/F01_RUN.txt" in protected


def test_c01_domain_task_control_error_stops_without_manifest_or_followup(tmp_path, monkeypatch):
    from opspilot.domain import chat
    from opspilot.domain.task_control import TaskControlError

    def fail_persist(*_args, **_kwargs):
        raise TaskControlError("V2_INJECTED_DOMAIN_PERSISTENCE_FAILURE")

    monkeypatch.setattr(chat, "complete_chat_compression_attempt", fail_persist)
    result = run_v2.run_mock(tmp_path / "c01", scenario={"Q02-A": "summary_persist_failure"})
    case = _case(result, "Q02-A")
    assert result["status"] == "STOPPED"
    assert result["stop_reason"] == "V2_INJECTED_DOMAIN_PERSISTENCE_FAILURE"
    assert case["status"] == "STOPPED"
    assert case["error"] == "V2_INJECTED_DOMAIN_PERSISTENCE_FAILURE"
    assert case["answer_manifest_present"] is False
    assert case["answer_calls"] == 0
    assert result["recorded_requests"] == 1
    assert [row["status"] for row in result["cases"][1:]] == ["NOT_STARTED", "NOT_STARTED"]


def test_c02_source_invalidation_between_summary_rounds_blocks_final_prompt(tmp_path):
    result = run_v2.run_mock(
        tmp_path / "c02", scenario={"Q02-A": "source_invalidated_between_rounds"},
    )
    case = _case(result, "Q02-A")
    assert result["status"] == "STOPPED"
    assert result["stop_reason"] == "RECHECK_SOURCE_INVALIDATED"
    assert case["answer_calls"] == 0
    assert result["recorded_requests"] == 1
    assert [row["status"] for row in result["cases"][1:]] == ["NOT_STARTED", "NOT_STARTED"]


def test_c03_512_output_cap_violation_stops_before_second_summary(tmp_path):
    result = run_v2.run_mock(
        tmp_path / "c03", scenario={"Q02-A": "oversized_first_summary"},
    )
    case = _case(result, "Q02-A")
    assert result["status"] == "STOPPED"
    assert result["stop_reason"] == "PROVIDER_USAGE_OVER_TOKEN_CAP"
    assert result["recorded_requests"] == 1
    assert result["summary_requests"] == 1 and result["answer_requests"] == 0
    ledger = _json(tmp_path / "c03" / "MOCK_COST_LEDGER.json")
    sent = [slot for slot in ledger["slots"] if slot["request_digest"]]
    assert sent[0]["usage"]["output_tokens"] == 513
    event = next(event for event in _events(tmp_path / "c03" / "MOCK_TRACE.jsonl.gz")
                 if event["event"] == "SEND_STARTED")
    assert event["request_payload"]["max_tokens"] == 512
    assert case["answer_calls"] == 0


def test_c03_shared_budget_rejects_reservation_before_dispatch(tmp_path):
    legacy, abc, *_ = run_v2.build_runner()
    cap = abc.REQUEST_RESERVE_USD_MICRO - 1
    ledger = abc.GlobalBudgetLedger.create(
        tmp_path / "budget.json", execution_id="v2-budget-boundary", mode="MOCK",
        request_limit=run_v2.REQUEST_CAP, hard_cap_usd_micro=cap,
    )
    with pytest.raises(abc.RunnerStop, match="GLOBAL_BUDGET_EXHAUSTED_BEFORE_SEND"):
        ledger.start_send("Q02-A:SUMMARY:1", "fixture-digest", "httpx.MockTransport")
    assert ledger.state["provider_requests_started"] == 0
    assert ledger.state["currently_reserved_usd_micro"] == 0
    assert not (tmp_path / "trace.jsonl.gz").exists()


def test_c04_unknown_send_is_reserved_and_never_retried_or_followed(tmp_path):
    result = run_v2.run_mock(tmp_path / "c04", scenario={"Q02-A": "unknown_first_send"})
    assert result["status"] == "STOPPED"
    assert result["stop_reason"] == "UNKNOWN_SEND_STATE_NO_RETRY"
    assert result["recorded_requests"] == 1
    ledger = _json(tmp_path / "c04" / "MOCK_COST_LEDGER.json")
    sent = [slot for slot in ledger["slots"] if slot["request_digest"]]
    assert len(sent) == 1 and sent[0]["status"] == "UNKNOWN"
    assert sent[0]["reserved_usd_micro"] > 0
    assert [row["status"] for row in result["cases"][1:]] == ["NOT_STARTED", "NOT_STARTED"]
    events = _events(tmp_path / "c04" / "MOCK_TRACE.jsonl.gz")
    assert sum(event["event"] == "SEND_STARTED" for event in events) == 1
    assert sum(event["event"] == "SEND_UNKNOWN" for event in events) == 1


def test_c05_legacy_authorization_cannot_enable_v2_live_dispatch():
    with pytest.raises(run_v2.V2Stop, match="LIVE_DISPATCH_NOT_IMPLEMENTED"):
        run_v2.reject_live_dispatch("R2-AR04-LIVE-RETENTION-RECHECK-01")
    with pytest.raises(SystemExit) as error:
        run_v2.main(["live", "--output", "unused"])
    assert error.value.code == 2


def test_c06_input_model_tool_and_source_drift_are_rejected_before_send(tmp_path, monkeypatch):
    import subprocess
    from retention_evidence import request_payload, trace_index

    pin_file = tmp_path / "QUESTIONS.json"
    pin_file.write_bytes(b"frozen question, Gold and rubric")
    expected = {"QUESTIONS.json": run_v2.sha256(pin_file.read_bytes())}
    assert run_v2.assert_file_pins(tmp_path, expected)["QUESTIONS.json"] == expected["QUESTIONS.json"]
    pin_file.write_bytes(b"changed Gold or question")
    with pytest.raises(run_v2.V2Stop, match="FROZEN_DIGEST_DRIFT:QUESTIONS.json"):
        run_v2.assert_file_pins(tmp_path, expected)

    with pytest.raises(run_v2.V2Stop, match="FROZEN_DIGEST_DRIFT:opspilot/domain/chat.py"):
        run_v2.assert_source_blob_pins({
            "opspilot/domain/chat.py": "0" * 40,
            "opspilot/assistant.py": run_v2.ASSISTANT_BLOB,
        })
    with pytest.raises(run_v2.V2Stop, match="FROZEN_DIGEST_DRIFT:opspilot/assistant.py"):
        run_v2.assert_source_blob_pins({
            "opspilot/domain/chat.py": run_v2.CHAT_BLOB,
            "opspilot/assistant.py": "0" * 40,
        })

    valid_payload = request_payload(
        trace_index(run_v2.ROOT / "docs/evidence/abc-live-env-unblock-01/live_run_02/LIVE_REQUESTS.jsonl.gz"),
        "Q02-A:ANSWER:1",
    )
    assert valid_payload is not None
    run_v2.assert_model_parameters(valid_payload)
    run_v2.assert_answer_contract(valid_payload)
    with pytest.raises(run_v2.V2Stop, match="MODEL_ID_DRIFT"):
        run_v2.assert_model_parameters({**valid_payload, "model": "other-model"})
    with pytest.raises(run_v2.V2Stop, match="MODEL_OUTPUT_BUDGET_DRIFT"):
        run_v2.assert_model_parameters({**valid_payload, "max_tokens": 513})
    changed_tools = dict(valid_payload)
    changed_tools["tools"] = list(valid_payload.get("tools", [])) + [{"type": "function", "function": {"name": "drift"}}]
    with pytest.raises(run_v2.V2Stop, match="TOOL_SCHEMA_DRIFT"):
        run_v2.assert_answer_contract(changed_tools)
    changed_prefix = dict(valid_payload)
    changed_prefix["messages"] = [dict(item) for item in valid_payload["messages"]]
    first_system = next(item for item in changed_prefix["messages"] if item.get("role") == "system")
    first_system["content"] = "DRIFTED " + str(first_system["content"])
    with pytest.raises(run_v2.V2Stop, match="TRUSTED_PROMPT_PREFIX_DRIFT"):
        run_v2.assert_answer_contract(changed_prefix)

    original = run_v2.assert_frozen
    calls = 0
    def drift_at_send_boundary():
        nonlocal calls
        calls += 1
        if calls == 3:
            raise run_v2.V2Stop("FROZEN_DIGEST_DRIFT:questions_gold_or_chat_blob")
        return original()
    monkeypatch.setattr(run_v2, "assert_frozen", drift_at_send_boundary)
    result = run_v2.run_mock(tmp_path / "c06")
    assert result["status"] == "STOPPED"
    assert result["recorded_requests"] == 0
    assert result["provider_requests_sent"] == 0
    assert calls >= 3


def test_c07_partial_early_value_never_upgrades_from_later_source(tmp_path):
    result = run_v2.run_mock(tmp_path / "c07")
    fact = _case(result, "Q06-B")["fact_scope_diagnostics"]
    assert fact["max_attempts_early_value_seq3"]["status"] == "PARTIAL"
    assert fact["protocol_and_max_attempts_transition_seq11"]["status"] == "COMPLETE_TEXT_WITH_SOURCE"


def test_c08_frozen_c06_red_and_f01_legacy_record_match_base():
    snapshot = run_v2.assert_frozen()["protected_historical_sha256"]
    assert len(snapshot) == len(run_v2.PROTECTED_HISTORICAL_FILES)
    assert all(item["matches_base"] for item in snapshot.values())
    assert snapshot["docs/evidence/r2-ar04-compaction-c06-hf01/RESULTS.json"]["matches_base"]
    assert snapshot["docs/evidence/r2-ar04-base-diff-edge-gate-hf02/F01_RUN.txt"]["matches_base"]


def _no_mock_dispatch(output: Path):
    assert not (output / "MOCK_TRACE.jsonl.gz").exists()
    assert not (output / "MOCK_COST_LEDGER.json").exists()
    assert not (output / "MOCK_RESULTS.json").exists()


def test_provenance_rejects_q02a_misattributed_abc_response_id_before_mock_send(tmp_path):
    manifest = copy.deepcopy(run_v2.FROZEN_REPLY_SOURCES)
    # This is the Q02-A summary response from the separate ABC live_run_02.
    manifest["Q02-A"]["provider_response_id"] = "fa6d38a4-d50e-4735-9732-2c48bfc54746"
    output = tmp_path / "wrong_response_id"
    with pytest.raises(run_v2.V2Stop, match="FROZEN_REPLY_PROVIDER_RESPONSE_ID_DRIFT:Q02-A"):
        run_v2.run_mock(output, reply_manifest=manifest)
    _no_mock_dispatch(output)


def test_provenance_rejects_changed_summary_body_with_original_digest_before_mock_send(tmp_path):
    target = run_v2.ROOT / run_v2.FROZEN_REPLY_SOURCES["Q02-A"]["trace_path"]

    def tampered_loader(path: Path):
        events = copy.deepcopy(run_v2._read_trace_events(path))
        if path.resolve() == target.resolve():
            response = next(event for event in events if event.get("event") == "RESPONSE_RECEIVED")
            response["response_payload"]["choices"][0]["message"]["content"] = '{"tampered":true}'
            # Keep response_body_sha256 unchanged to model a body/metadata mismatch.
        return events

    output = tmp_path / "changed_body"
    with pytest.raises(run_v2.V2Stop, match="FROZEN_REPLY_SUMMARY_DIGEST_DRIFT:Q02-A"):
        run_v2.run_mock(output, trace_event_loader=tampered_loader)
    _no_mock_dispatch(output)


def test_provenance_rejects_swapped_q02a_q02b_sources_before_mock_send(tmp_path):
    manifest = copy.deepcopy(run_v2.FROZEN_REPLY_SOURCES)
    manifest["Q02-A"], manifest["Q02-B"] = manifest["Q02-B"], manifest["Q02-A"]
    output = tmp_path / "swapped_case_sources"
    with pytest.raises(run_v2.V2Stop, match="FROZEN_REPLY_CASE_MISMATCH:Q02-A"):
        run_v2.run_mock(output, reply_manifest=manifest)
    _no_mock_dispatch(output)
