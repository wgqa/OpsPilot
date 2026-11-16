from __future__ import annotations

import gzip
import json
import sys
from pathlib import Path

import pytest

EVIDENCE_DIR = Path(__file__).resolve().parent
ROOT = EVIDENCE_DIR.parents[2]
if str(EVIDENCE_DIR) not in sys.path:
    sys.path.insert(0, str(EVIDENCE_DIR))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import run_remaining_live_gate as gate


def test_two_case_full_assistant_domain_mock_uses_split_output_caps(tmp_path):
    output = tmp_path / "mock_run"
    result = gate.run_mock(output)

    assert result["case_matrix_passed"] is True
    assert result["status"] == "COMPLETED"
    assert [row["case_id"] for row in result["cases"]] == ["Q02-B", "Q06-B"]
    assert result["recorded_requests"] == 6
    assert result["summary_requests"] == 4
    assert result["answer_requests"] == 2
    assert result["provider_requests_sent"] == 0
    assert result["provider_cost_usd"] == "0.00"
    assert result["external_mcp_calls"] == 0
    assert all(row["history_rows"] == 29 for row in result["cases"])
    for field in ("domain_instance_sha256", "checkpoint_instance_sha256", "session_id_sha256",
                  "run_id_sha256", "runtime_grant_id_sha256"):
        assert len({row[field] for row in result["cases"]}) == 2

    assert sorted((row["case_id"], row["purpose"], row["max_tokens"])
                  for row in result["request_caps"]) == sorted(
        [(case, "SUMMARY", 1024) for case in ("Q02-B", "Q06-B") for _ in range(2)]
        + [(case, "ANSWER", 512) for case in ("Q02-B", "Q06-B")]
    )
    assert len(result["runtime_grant_caps"]) == 2
    assert all(row["max_output_tokens"] == 1024 for row in result["runtime_grant_caps"])
    assert all(row["total_limit_usd_micro"] == gate.GRANT_PER_CASE_RESERVE_USD_MICRO
               for row in result["runtime_grant_caps"])
    assert all(row["status"] == "SUCCEEDED" and row["summary_calls"] == 2 and row["answer_calls"] == 1
               for row in result["cases"])
    assert all(len(row["persisted_summary_token_estimates"]) == 2
               and all(tokens <= 512 for tokens in row["persisted_summary_token_estimates"])
               for row in result["cases"])
    assert all(row["answer_tool_choice"] == "none" for row in result["cases"])
    assert result["target_fact_visibility"] == [
        {"case_id": "Q02-B", "fact": "endpoint=/callback", "source_sequence": 3,
         "present_in_final_prompt_with_source": True},
        {"case_id": "Q06-B", "facts": ["v1.2 -> v1.3", "max_attempts 3 -> 5"],
         "source_sequence": 11, "present_in_final_prompt_with_source": True,
         "early_seq3_status": "PARTIAL"},
    ]

    with gzip.open(output / "MOCK_TRACE.jsonl.gz", "rt", encoding="utf-8") as stream:
        events = [json.loads(line) for line in stream if line.strip()]
    sent = [event for event in events if event.get("event") == "SEND_STARTED"]
    assert len(sent) == 6
    assert all(event["request_payload"]["max_tokens"] == row["max_tokens"]
               for event, row in zip(sent, result["request_caps"]))
    with gzip.open(output / "MOCK_REPLY_PROVENANCE.jsonl.gz", "rt", encoding="utf-8") as stream:
        provenance = [json.loads(line) for line in stream if line.strip()]
    historical = [row for row in provenance if row["origin"] == "FROZEN_HISTORICAL_LIVE_SUMMARY"]
    assert {(row["case_id"], row["historical_response_id"]) for row in historical} == {
        ("Q02-B", "d52800ab-6315-4374-ae93-8ff98c5b20a2"),
        ("Q06-B", "2a3e15cc-5127-468b-b892-9ce8d194459f"),
    }
    assert all(row["historical_response_body_sha256"] and row["historical_content_sha256"]
               for row in historical)


def test_preflight_is_zero_cost_and_rejects_prior_task_authorization(tmp_path, monkeypatch):
    mock_dir = tmp_path / "mock_run"
    mock = gate.run_mock(mock_dir)
    mock_path = mock_dir / "MOCK_RESULTS.json"
    monkeypatch.setattr(gate, "MOCK_RESULTS_PATH", mock_path)
    report = gate.run_preflight(output_path=tmp_path / "PREFLIGHT.json")
    assert mock["case_matrix_passed"] is True
    assert report["status"] == "READY_FOR_NEW_LIVE_AUTHORIZATION"
    assert report["mock_case_matrix_passed"] is True
    assert report["mock_results_path"] == mock_path.resolve().as_posix()
    assert report["mock_results_sha256"] == gate._sha256(mock_path.read_bytes())
    assert report["historical_authorization_reuse_blocked"] is True
    assert report["new_authorization_created"] is False
    assert report["provider_requests_sent"] == 0
    assert report["provider_cost_usd"] == "0.00"
    assert report["budget"]["purpose_specific_total_usd_micro"] == 27_746
    assert report["budget"]["shared_grant_reserve_usd_micro"] == 28_974
    assert report["budget"]["hard_cap_usd_micro"] == 60_000
    assert report["token_limits"] == {
        "input": 12_000, "summary_generation": 1_024, "answer": 512,
        "persisted_summary": 512, "runtime_grant_output": 1_024,
    }
    assert not list(tmp_path.glob("*AUTHORIZATION*.json"))


@pytest.mark.parametrize("legacy_task", [
    "R2-AR04-LIVE-RECHECK-V2-FINAL-01",
    "R2-AR04-LIVE-RETENTION-RECHECK-01",
    "ABC-LIVE-ENV-UNBLOCK-01",
])
def test_historical_authorization_task_is_rejected(legacy_task):
    with pytest.raises(gate.GateStop, match="NEW_TASK_SPECIFIC_LIVE_AUTHORIZATION_REQUIRED"):
        gate.validate_authorization_manifest({"task": legacy_task, "base_sha": "historical"})


def test_missing_authorization_blocks_live_before_output_or_send(tmp_path, monkeypatch):
    missing = tmp_path / "missing.json"
    output = tmp_path / "live_run"
    mock_path = tmp_path / "pinned-mock" / "MOCK_RESULTS.json"
    mock_path.parent.mkdir()
    mock_path.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(gate, "MOCK_RESULTS_PATH", mock_path)
    with pytest.raises(gate.GateStop, match="NEW_TASK_SPECIFIC_LIVE_AUTHORIZATION_REQUIRED"):
        gate.run_live(missing, output_path=output)
    assert not output.exists()


def test_cap_validation_distinguishes_summary_answer_and_rejects_mismatch():
    gate._assert_request_cap({"max_tokens": 1024}, 1024)
    gate._assert_request_cap({"max_tokens": 512}, 512)
    with pytest.raises(gate.GateStop, match="PURPOSE_OUTPUT_TOKEN_CAP_MISMATCH"):
        gate._assert_request_cap({"max_tokens": 1024}, 512)


def test_shared_authorization_budget_enforces_reserve_floor_and_hard_ceiling():
    assert gate._validate_auth_hard_cap(gate.SHARED_GRANT_RESERVE_USD_MICRO) == 28_974
    assert gate._validate_auth_hard_cap(gate.HARD_CAP_USD_MICRO) == 60_000
    with pytest.raises(gate.GateStop, match="AUTH_BUDGET_OUTSIDE_FROZEN_ENVELOPE"):
        gate._validate_auth_hard_cap(gate.SHARED_GRANT_RESERVE_USD_MICRO - 1)
    with pytest.raises(gate.GateStop, match="AUTH_BUDGET_OUTSIDE_FROZEN_ENVELOPE"):
        gate._validate_auth_hard_cap(gate.HARD_CAP_USD_MICRO + 1)


def test_task_freeze_allows_approved_execution_evidence_and_rejects_other_evidence(monkeypatch):
    assert gate.MOCK_DIR.name == "mock_run_09"
    freeze = gate._task_assert_frozen()
    assert freeze["candidate_head_at_check"] == gate._git("rev-parse", "HEAD")

    original_git = gate._git

    def with_unapproved_evidence(*args):
        if args[:2] == ("diff", "--name-only"):
            return "docs/evidence/unapproved-audit/INJECTED.json"
        return original_git(*args)

    monkeypatch.setattr(gate, "_git", with_unapproved_evidence)
    with pytest.raises(gate.GateStop, match="TASK_DIFF_OUTSIDE_NEW_EVIDENCE:docs/evidence/unapproved-audit/INJECTED.json"):
        gate._task_assert_frozen()


def test_task_freeze_allows_only_this_root_cause_evidence_prefix(monkeypatch):
    original_git = gate._git

    def with_root_cause_evidence(*args):
        if args and args[0] == "diff" and "--name-only" in args:
            return "docs/evidence/r2-ar04-live-presend-rootcause-01/FAILURE_REPRO.json"
        return original_git(*args)

    monkeypatch.setattr(gate, "_git", with_root_cause_evidence)
    freeze = gate._task_assert_frozen()
    assert freeze["candidate_head_at_check"] == gate._git("rev-parse", "HEAD")


def test_simulated_historical_frozen_file_drift_remains_blocked(monkeypatch):
    original_git = gate.v2._git
    protected = gate.v2.PROTECTED_HISTORICAL_FILES[0]

    def with_changed_protected_hash(*args):
        if (len(args) >= 3 and args[0] == "hash-object"
                and args[1] == f"--path={protected}" and args[2] == protected):
            return "0" * 40
        return original_git(*args)

    monkeypatch.setattr(gate.v2, "_git", with_changed_protected_hash)
    with pytest.raises(gate.v2.V2Stop, match="FROZEN_DIGEST_DRIFT:protected:"):
        gate._task_assert_frozen()


def test_production_blob_drift_is_not_accepted(monkeypatch):
    monkeypatch.setattr(gate, "CHAT_BLOB", "0" * 40)
    with pytest.raises(Exception, match="PRODUCTION_CHAT_BLOB_DRIFT|CHAT_BLOB|SOURCE_BLOB|FROZEN_DIGEST_DRIFT"):
        gate._task_assert_frozen()


def test_source_invalidation_stops_before_answer_and_later_case(tmp_path):
    result = gate.run_mock(tmp_path / "invalidated", scenario={
        "Q02-B": "source_invalidated_between_rounds",
    })
    assert result["status"] == "STOPPED"
    assert result["stop_reason"]
    assert result["cases"][0]["case_id"] == "Q02-B"
    assert result["cases"][0]["status"] != "SUCCEEDED"
    assert result["cases"][0].get("answer_calls", 0) == 0
    assert result["cases"][1]["status"] == "NOT_STARTED"
    assert result["provider_requests_sent"] == 0


def test_unknown_send_stops_without_retry_or_following_case(tmp_path):
    result = gate.run_mock(tmp_path / "unknown", scenario={"Q02-B": "unknown_first_send"})
    assert result["status"] == "STOPPED"
    assert result["stop_reason"] == "UNKNOWN_SEND_STATE_NO_RETRY"
    assert result["recorded_requests"] == 1
    assert result["cases"][0]["case_id"] == "Q02-B"
    assert result["cases"][1]["status"] == "NOT_STARTED"
    assert result["provider_requests_sent"] == 0
