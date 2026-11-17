from __future__ import annotations

import gzip
import importlib.util
import json
import subprocess
import tempfile
from pathlib import Path

import pytest

SCRIPT = Path(__file__).with_name("run_versioned_admission.py")
SPEC = importlib.util.spec_from_file_location("ar04_versioned_admission_under_test", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
runner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runner)
gate = runner.load_gate()

# This pytest process is offline. MockTransport is the only permitted HTTP path.
gate.v2.block_external_network()


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_final_source_and_production_pins_match_candidate() -> None:
    frozen = runner.assert_frozen()
    assert frozen["task_base_sha"] == runner.BASE_SHA
    assert frozen["candidate_head_at_check"] == subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=runner.ROOT, text=True,
    ).strip()
    assert frozen["production_blobs"] == {
        "opspilot/domain/chat.py": "6a57360de6f5579fa65dc008de4fcf37148c43f0",
        "opspilot/assistant.py": "288559c6e9b77549939501f4cedb1a8097a79918",
    }
    assert frozen["protected_historical_files_match_base"] is True


def test_mock_bound_to_this_runner_and_reaches_mock_transport() -> None:
    result_path = runner.MOCK_RESULTS_PATH
    ledger_path = result_path.with_name("MOCK_COST_LEDGER.json")
    trace_path = result_path.with_name("MOCK_TRACE.jsonl.gz")
    assert result_path.is_file() and ledger_path.is_file() and trace_path.is_file()
    result = read_json(result_path)
    ledger = read_json(ledger_path)
    with gzip.open(trace_path, "rt", encoding="utf-8") as stream:
        events = [json.loads(line) for line in stream if line.strip()]

    assert result["task"] == runner.TASK
    assert result["base_sha"] == runner.BASE_SHA
    assert result["case_matrix_passed"] is True
    assert result["recorded_requests"] == 6
    assert result["summary_requests"] == 4
    assert result["answer_requests"] == 2
    assert result["provider_requests_sent"] == 0
    assert result["external_mcp_calls"] == 0
    assert result["runner_sha256"] == runner._sha256(SCRIPT)
    assert result["source_manifest_sha256"] == runner._sha256(runner.SOURCE_MANIFEST_PATH)
    assert [case["case_id"] for case in result["cases"]] == ["Q02-B", "Q06-B"]
    assert all(case["status"] == "SUCCEEDED" for case in result["cases"])
    assert all(case["summary_calls"] == 2 and case["answer_calls"] == 1 for case in result["cases"])
    assert all(case["answer_tool_choice"] == "none" and case["mcp_attempts"] == 0
               for case in result["cases"])
    assert all(all(0 <= n <= 512 for n in case["persisted_summary_token_estimates"])
               for case in result["cases"])

    slots = ledger.get("slots", [])
    assert len(slots) == 6
    assert all(slot.get("transport") == "httpx.MockTransport" for slot in slots)
    starts = [event for event in events if event.get("event") == "SEND_STARTED"]
    received = [event for event in events if event.get("event") == "RESPONSE_RECEIVED"]
    assert len(starts) == len(received) == 6
    assert {event.get("mode") for event in starts + received} == {"MOCK"}

    facts = {row["case_id"]: row for row in result["target_fact_visibility"]}
    assert facts["Q02-B"]["present_in_final_prompt_with_source"] is True
    q06 = facts["Q06-B"]
    assert q06["present_in_final_prompt_with_source"] is True
    assert q06["early_seq3_status"] == "PARTIAL"
    sources = read_json(runner.SOURCE_MANIFEST_PATH)["case_reply_sources"]
    assert set(sources) == {"Q02-B", "Q06-B"}
    assert sources["Q02-B"]["logical_id"] == "Q02-B:SUMMARY:1"
    assert sources["Q02-B"]["provider_response_id"] == "d52800ab-6315-4374-ae93-8ff98c5b20a2"
    assert sources["Q06-B"]["logical_id"] == "Q06-B:SUMMARY:1"
    assert sources["Q06-B"]["provider_response_id"] == "2a3e15cc-5127-468b-b892-9ce8d194459f"
    assert all(len(sources[case]["trace_sha256"]) == 64
               and len(sources[case]["request_body_sha256"]) == 64
               and len(sources[case]["response_body_sha256"]) == 64
               for case in sources)
    q06_provenance = [row for row in result["mock_reply_provenance"]
                      if row.get("case_id") == "Q06-B"]
    assert [(row["logical_sequence"], row["origin"]) for row in q06_provenance] == [
        (1, "FROZEN_HISTORICAL_LIVE_SUMMARY"),
        (2, "SYNTHETIC_DETERMINISTIC_PARENT_PROJECTION"),
        (3, "SYNTHETIC_MOCK_ANSWER"),
    ]
    assert all(row.get("origin") != "OLD_Q06B_SECOND_ROUND_LIVE_REPLY"
               for row in q06_provenance)


def test_preflight_binds_same_mock_and_is_zero_cost() -> None:
    preflight = read_json(runner.PREFLIGHT_PATH)
    result = read_json(runner.MOCK_RESULTS_PATH)
    assert preflight["status"] == "READY_FOR_NEW_LIVE_AUTHORIZATION"
    assert preflight["mock_results_sha256"] == runner._sha256(runner.MOCK_RESULTS_PATH)
    assert result["runner_sha256"] == runner._sha256(SCRIPT)
    assert preflight["actual_provider_requests_sent"] == 0
    assert preflight["provider_cost_usd"] == "0.00"
    assert preflight["authenticated_provider_check"] == "NOT_PERFORMED_ZERO_COST_PREFLIGHT"
    assert preflight["api_key_value_recorded"] is False
    assert preflight["live_dispatch_available"] is False
    assert preflight["historical_authorization_reuse_blocked"] is True
    assert preflight["review_task_id_rejected_as_authorization_identity"] is True
    with tempfile.TemporaryDirectory(prefix="ar04-final-preflight-", dir=runner.EVIDENCE_DIR) as temp:
        final_check = runner.run_preflight(
            runner.MOCK_RESULTS_PATH, Path(temp) / "FINAL_HEAD_PREFLIGHT.json",
        )
        assert final_check["status"] == "READY_FOR_NEW_LIVE_AUTHORIZATION"
        assert final_check["actual_provider_requests_sent"] == 0
        assert final_check["mock_results_sha256"] == runner._sha256(runner.MOCK_RESULTS_PATH)


def test_old_authorization_identity_is_rejected_before_dispatch() -> None:
    old_probe = {
        "task": "R2-AR04-REMAINING-LIVE-GATE-01",
        "base_sha": "fa4cd8a7ea6dd36babccbbfc5fcdb7a179729fd3",
    }
    with pytest.raises(gate.GateStop, match="NEW_TASK_SPECIFIC_LIVE_AUTHORIZATION_REQUIRED"):
        gate.validate_authorization_manifest(old_probe, mock_path=runner.MOCK_RESULTS_PATH)

    with tempfile.TemporaryDirectory(prefix="ar04-old-auth-", dir=runner.EVIDENCE_DIR) as temp:
        root = Path(temp)
        old_auth = root / "old-auth.json"
        old_auth.write_text(json.dumps(old_probe), encoding="utf-8")
        output = root / "must-not-exist-live-output"
        with pytest.raises(gate.GateStop, match="NEW_TASK_SPECIFIC_LIVE_AUTHORIZATION_REQUIRED"):
            runner.run_live(old_auth, output_path=output)
        assert not output.exists()


def test_preflight_rejects_interchanged_mock_artifact() -> None:
    with tempfile.TemporaryDirectory(prefix="ar04-mock-swap-", dir=runner.EVIDENCE_DIR) as temp:
        root = Path(temp)
        altered = root / "different-mock-results.json"
        altered.write_bytes(runner.MOCK_RESULTS_PATH.read_bytes())
        output = root / "must-not-be-created.json"
        with pytest.raises(gate.GateStop, match="AUTH_MOCK_RESULTS_PATH_MISMATCH"):
            runner.run_preflight(altered, output)
        assert not output.exists()
