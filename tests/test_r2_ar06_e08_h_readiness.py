from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "user-demo"))

from run_r2_ar06_case import (  # noqa: E402
    E08_H_CASE_ID,
    E08_LOG_EVENT_ID,
    E08_TARGET_EVENT_ID,
    E08_DECOY_EVENT_ID,
    EvaluationPreflightError,
    _case_preflight_cli,
    initialize_case_runtime,
    load_frozen_case,
    inspect_e08_history_ready,
    prime_e08_history_fixture,
    run_e08_fixture,
    _e08_history_audit,
)

from opspilot.domain.database import connect  # noqa: E402
from opspilot.domain.s3_history import get_transport_history_fact  # noqa: E402
from opspilot.domain.d2 import ScopeDenied  # noqa: E402
from opspilot.domain.s3 import current_s3_evidence  # noqa: E402


ORIGIN = "http://127.0.0.1"
PASSWORD = "support-test-password"


def _runtime(tmp_path: Path):
    root = tmp_path / "repo"
    (root / ".runtime").mkdir(parents=True)
    name = "user-demo-e08h-readiness-fixture"
    runtime = initialize_case_runtime(E08_H_CASE_ID, name, root=root)
    return root, name, runtime


def test_e08_loader_returns_only_exact_frozen_question_and_keeps_gold_private():
    case = load_frozen_case(E08_H_CASE_ID)
    assert case["case_id"] == E08_H_CASE_ID
    assert case["split"] == "H"
    assert len(case["user_turns"]) == 1
    assert "target_event_state" not in case
    assert "expected_user_outcome" not in case
    assert "forbidden" not in case


def test_e08_offline_formal_api_history_current_observation_and_blinding(tmp_path):
    root, runtime_name, runtime = _runtime(tmp_path)
    result = run_e08_fixture(
        runtime_name,
        root=root,
        support_password=PASSWORD,
        api_origin=ORIGIN,
        web_origin=ORIGIN,
        timeout_seconds=30,
    )

    run_result = result["result"]
    trace = json.loads(Path(run_result["trace_path"]).read_text(encoding="utf-8"))
    audit = _e08_history_audit(trace, final_run_id=run_result["run_id"], task_id=run_result["task_id"])
    assert run_result["run_status"] == "SUCCEEDED"
    assert run_result["assessment_status"] == "UNVERIFIED"
    assert run_result["provider_send_grants"] == 0
    assert run_result["provider_input_tokens"] is None
    assert run_result["task_id"]
    assert audit["history_event_id"] == E08_TARGET_EVENT_ID
    assert audit["history_receiver_status"] == "QUEUED"
    assert audit["current_event_id"] == E08_TARGET_EVENT_ID
    assert audit["current_receiver_status"] == "PROCESSED"
    assert audit["history_run_id"] != audit["current_run_id"]
    assert audit["history_answer_message_id"]
    assert audit["final_answer_message_id"]
    assert audit["history_observation_id"] != audit["current_observation_id"]
    assert audit["target_event_changed"] is False
    assert audit["current_is_later_version"] is True
    assert audit["decoy_event_id"] == E08_DECOY_EVENT_ID
    assert audit["decoy_event_id"] != audit["current_event_id"]
    assert audit["log_event_id"] == E08_LOG_EVENT_ID
    assert audit["log_event_id"] == E08_DECOY_EVENT_ID
    assert audit["log_authority"] == "USER_PROVIDED_UNVERIFIED"
    assert audit["log_observed_at"] < audit["current_observed_at"]
    assert audit["gold_leak_matches"] == []
    assert audit["model_calls_used_gold_labels"] is False
    assert audit["model_input_contains_history_user_turn"] is True
    assert audit["model_input_contains_historical_assistant_answer"] is False
    assert audit["model_input_contains_target_event_id"] is True
    assert audit["model_input_contains_decoy_event_id"] is True
    assert audit["model_call_count"] >= 2
    assert "tool" in audit["final_model_message_types"]
    assert "get_receiver_processing" in audit["final_model_visible_tool_names"]
    assert audit["current_run_target_observation_count"] >= 1
    assert audit["current_run_other_event_observation_count"] == 0
    assert result["preflight"]["target_receiver_status_before_history"] == "QUEUED"
    assert result["preflight"]["decoy_receiver_status"] == "QUEUED"
    final_answer = next(
        row for row in trace["messages"]
        if row.get("message_id") == audit["final_answer_message_id"]
    )
    assert E08_TARGET_EVENT_ID in final_answer["body"]
    assert "PROCESSED" in final_answer["body"]

    final_user = next(row for row in reversed(trace["messages"]) if row["role"] == "USER")
    assert final_user["body"] == load_frozen_case(E08_H_CASE_ID)["user_turns"][0]
    assert run_result["trace_path"].endswith("E08-H.json")
    assert result["history_setup"]["history_source_current_after_fixture_advance"] is False
    assert result["prepared_state"]["history_source_current"] is False

    # A different order/Event cannot be queried under the target TaskBinding.
    with connect(runtime / "domain.sqlite3") as connection:
        with pytest.raises(ScopeDenied):
            get_transport_history_fact(
                runtime / "domain.sqlite3", run_result["task_id"], E08_DECOY_EVENT_ID,
            )


def test_e08_live_readiness_rejects_missing_or_corrupted_prehistory(tmp_path):
    root, runtime_name, runtime = _runtime(tmp_path)
    with pytest.raises(EvaluationPreflightError, match="E08_HISTORY_NOT_PRIMED"):
        inspect_e08_history_ready(runtime_name, root=root)

    # No Runner state sidecar can make an uncorrelated history answer qualify.
    evidence_dir = runtime / "evidence"
    evidence_dir.mkdir(exist_ok=True)
    (evidence_dir / "E08-H.history.json").write_text(
        json.dumps({"history_receiver_status": "QUEUED", "event_id": E08_DECOY_EVENT_ID}),
        encoding="utf-8",
    )
    with pytest.raises(EvaluationPreflightError, match="E08_HISTORY_NOT_PRIMED"):
        inspect_e08_history_ready(runtime_name, root=root)


def test_e08_history_prime_is_live_preflightable_without_submitting_frozen_question(tmp_path):
    root, runtime_name, _runtime_path = _runtime(tmp_path)
    result = prime_e08_history_fixture(
        runtime_name,
        root=root,
        support_password=PASSWORD,
        api_origin=ORIGIN,
        web_origin=ORIGIN,
        timeout_seconds=30,
    )
    assert result["history"]["provider_requests"] == 0
    assert result["history"]["unknown_requests"] == 0
    assert result["prepared"]["history_source_current"] is False
    assert _case_preflight_cli(
        type("Args", (), {"case_id": E08_H_CASE_ID, "runtime_name": runtime_name})(), root=root,
    )["status"] == "OFFLINE_HISTORY_PRIMED"
    with pytest.raises(EvaluationPreflightError, match="E08_HISTORY_ALREADY_PRIMED"):
        prime_e08_history_fixture(
            runtime_name,
            root=root,
            support_password=PASSWORD,
            api_origin=ORIGIN,
            web_origin=ORIGIN,
            timeout_seconds=30,
        )
    assert len(result["history"]["history_answer_sha256"]) == 64
    assert not any(
        row.get("body") == load_frozen_case(E08_H_CASE_ID)["user_turns"][0]
        for row in json.loads(Path(result["history"]["trace_path"]).read_text(encoding="utf-8"))["messages"]
        if row.get("role") == "USER"
    )


def test_e08_stale_and_digest_tampered_observation_sources_fail_currentness(tmp_path):
    root, runtime_name, runtime = _runtime(tmp_path)
    primed = prime_e08_history_fixture(
        runtime_name,
        root=root,
        support_password=PASSWORD,
        api_origin=ORIGIN,
        web_origin=ORIGIN,
        timeout_seconds=30,
    )
    prepared = primed["prepared"]
    with connect(runtime / "domain.sqlite3") as connection:
        facts, excluded = current_s3_evidence(
            connection,
            prepared["task_id"],
            [prepared["history_evidence_id"]],
            run_id=prepared["history_run_id"],
            observation_ids={prepared["history_evidence_id"]: prepared["history_observation_id"]},
        )
    assert not facts
    assert excluded and excluded[0]["reason"] == "S3_CURRENT_VERSION_MISMATCH"

    with connect(runtime / "domain.sqlite3") as connection:
        connection.execute(
            "UPDATE d2_evidence SET digest=? WHERE evidence_id=?",
            ("0" * 64, prepared["history_evidence_id"]),
        )
    with connect(runtime / "domain.sqlite3") as connection:
        facts, excluded = current_s3_evidence(
            connection,
            prepared["task_id"],
            [prepared["history_evidence_id"]],
            run_id=prepared["history_run_id"],
            observation_ids={prepared["history_evidence_id"]: prepared["history_observation_id"]},
        )
    assert not facts
    assert excluded and excluded[0]["reason"] == "S3_FACT_ORIGIN_INVALID"
