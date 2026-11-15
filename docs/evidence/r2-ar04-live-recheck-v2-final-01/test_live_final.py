from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import run_live_final as live
import run_v2


def _authorization(now: datetime) -> dict:
    return {
        "schema_version": 1,
        "authorization_id": "fixture-only-authorization",
        "task": live.TASK,
        "base_sha": live.TASK_BASE_SHA,
        "actual_live_send_authorized": True,
        "authorized_at_utc": live._iso_utc(now),
        "expires_at_utc": live._iso_utc(now + timedelta(hours=1)),
        "provider": "DeepSeek",
        "model_alias": run_v2.MODEL,
        "published_model_version": live.MODEL_VERSION,
        "case_order": list(live.CASE_MATRIX),
        "summary_request_limit": live.SUMMARY_LIMIT,
        "answer_request_limit": live.ANSWER_LIMIT,
        "provider_request_limit": live.REQUEST_LIMIT,
        "hard_cap_usd_micro": live.HARD_CAP_USD_MICRO,
        "automatic_retries": 0,
        "external_mcp": False,
        "tool_choice": "none",
        "max_input_tokens_per_request": run_v2.MAX_INPUT_TOKENS,
        "max_output_tokens_per_request": run_v2.MAX_OUTPUT_TOKENS,
        "price_snapshot": {
            "pricing_url": live.PRICE_URL,
            "checked_at_utc": live._iso_utc(now),
            "input_cache_miss_usd_per_million": live.INPUT_RATE_USD_PER_MILLION,
            "output_usd_per_million": live.OUTPUT_RATE_USD_PER_MILLION,
            "model_alias": run_v2.MODEL,
            "published_model_version": live.MODEL_VERSION,
        },
    }


def _case(result: dict, case_id: str) -> dict:
    return next(row for row in result["cases"] if row["case_id"] == case_id)


def test_task_base_and_current_production_freeze_are_bound():
    freeze = live.assert_final_frozen()
    assert freeze["task_base_sha"] == live.TASK_BASE_SHA
    assert freeze["production_blobs"] == {
        "opspilot/domain/chat.py": run_v2.CHAT_BLOB,
        "opspilot/assistant.py": run_v2.ASSISTANT_BLOB,
    }
    assert freeze["protected_historical_paths_match"] is True
    assert freeze["merge_after_task_base"] is False


def test_final_runner_mock_uses_final_task_and_shared_budget_identity(tmp_path):
    output = tmp_path / "final-mock"
    result = live.run_mock(output)
    ledger = json.loads((output / "MOCK_COST_LEDGER.json").read_text(encoding="utf-8"))
    assert result["task"] == live.TASK
    assert result["base_sha"] == live.TASK_BASE_SHA
    assert result["case_matrix_passed"] is True
    assert ledger["task"] == live.TASK
    assert ledger["request_limit"] == live.REQUEST_LIMIT
    assert ledger["hard_cap_usd_micro"] == live.HARD_CAP_USD_MICRO
    assert result["provider_requests_sent"] == 0
    assert result["live_dispatch_available"] is True
    assert result["live_dispatch_requires_fresh_task_authorization"] is True
    assert result["live_dispatch_performed"] is False
    q02a = _case(result, "Q02-A")["provider_stage_and_prompt_visibility"]["final_answer_summary"]["checks"]
    q02b = _case(result, "Q02-B")["provider_stage_and_prompt_visibility"]["final_answer_summary"]["checks"]
    q06b = _case(result, "Q06-B")["provider_stage_and_prompt_visibility"]["final_answer_summary"]["checks"]
    assert q02a["endpoint_seq3"] is True and q02b["endpoint_seq3"] is True
    assert q06b["protocol_and_parameter_change_seq11"] is True
    assert q06b["explicit_ordered_transition_with_source"] is True


def test_authorization_requires_new_exact_task_and_recent_price_snapshot():
    now = datetime(2026, 11, 15, 12, 0, tzinfo=timezone.utc)
    valid = _authorization(now)
    accepted = live.validate_authorization_manifest(valid, now=now)
    assert accepted["hard_cap_usd_micro"] == 60_000
    assert accepted["worst_case_reserve_usd_micro"] == 37_935

    stale_task = {**valid, "task": "R2-AR04-LIVE-RETENTION-RECHECK-01"}
    with pytest.raises(live.FinalRunnerStop, match="NEW_TASK_SPECIFIC_LIVE_AUTHORIZATION_REQUIRED"):
        live.validate_authorization_manifest(stale_task, now=now)

    stale_price = json.loads(json.dumps(valid))
    stale_price["price_snapshot"]["checked_at_utc"] = live._iso_utc(now - timedelta(hours=25))
    with pytest.raises(live.FinalRunnerStop, match="OFFICIAL_PRICE_SNAPSHOT_STALE"):
        live.validate_authorization_manifest(stale_price, now=now)

    wider_cap = {**valid, "hard_cap_usd_micro": 60_001}
    with pytest.raises(live.FinalRunnerStop, match="AUTHORIZATION_HARD_CAP_EXCEEDS_TASK_LIMIT"):
        live.validate_authorization_manifest(wider_cap, now=now)

    too_small = {**valid, "hard_cap_usd_micro": live.TOTAL_WORST_CASE_RESERVE_USD_MICRO - 1}
    with pytest.raises(live.FinalRunnerStop, match="AUTHORIZED_BUDGET_BELOW_WORST_CASE_RESERVE"):
        live.validate_authorization_manifest(too_small, now=now)

    class LegacyBudget:
        HARD_CAP_MICRO = live.HARD_CAP_USD_MICRO

    lower_valid_cap = {**valid, "hard_cap_usd_micro": live.TOTAL_WORST_CASE_RESERVE_USD_MICRO}
    assert live.bind_authorized_global_cap(LegacyBudget, lower_valid_cap) == live.TOTAL_WORST_CASE_RESERVE_USD_MICRO
    assert LegacyBudget.HARD_CAP_MICRO == live.TOTAL_WORST_CASE_RESERVE_USD_MICRO


def test_live_without_fresh_authorization_fails_before_creating_output(tmp_path):
    missing = tmp_path / "missing-authorization.json"
    live_output = tmp_path / "live_run_01"
    with pytest.raises((live.FinalRunnerStop, FileNotFoundError)):
        live.run_live(missing, mock_path=tmp_path / "not-read-before-auth.json", live_output=live_output)
    assert not live_output.exists()


def test_domain_persistence_failure_stops_and_does_not_answer(tmp_path, monkeypatch):
    from opspilot.domain import chat
    from opspilot.domain.task_control import TaskControlError

    def fail_persist(*_args, **_kwargs):
        raise TaskControlError("FINAL_INJECTED_DOMAIN_PERSISTENCE_FAILURE")

    monkeypatch.setattr(chat, "complete_chat_compression_attempt", fail_persist)
    result = run_v2.run_mock(tmp_path / "domain-failure", scenario={"Q02-A": "summary_persist_failure"})
    case = _case(result, "Q02-A")
    assert result["status"] == "STOPPED"
    assert result["stop_reason"] == "FINAL_INJECTED_DOMAIN_PERSISTENCE_FAILURE"
    assert case["answer_manifest_present"] is False
    assert case["answer_calls"] == 0
    assert result["recorded_requests"] == 1
    assert [row["status"] for row in result["cases"][1:]] == ["NOT_STARTED", "NOT_STARTED"]


def test_source_invalidation_stops_before_answer_and_later_cases(tmp_path):
    result = run_v2.run_mock(
        tmp_path / "source-invalidated",
        scenario={"Q02-A": "source_invalidated_between_rounds"},
    )
    case = _case(result, "Q02-A")
    assert result["status"] == "STOPPED"
    assert result["stop_reason"] == "RECHECK_SOURCE_INVALIDATED"
    assert case["answer_calls"] == 0
    assert result["recorded_requests"] == 1
    assert [row["status"] for row in result["cases"][1:]] == ["NOT_STARTED", "NOT_STARTED"]


def test_global_budget_rejects_before_dispatch(tmp_path):
    _legacy, abc, *_ = run_v2.build_runner()
    ledger = abc.GlobalBudgetLedger.create(
        tmp_path / "undersized-ledger.json", execution_id="final-budget-boundary",
        mode="MOCK", request_limit=live.REQUEST_LIMIT,
        hard_cap_usd_micro=live.REQUEST_RESERVE_USD_MICRO - 1,
    )
    with pytest.raises(abc.RunnerStop, match="GLOBAL_BUDGET_EXHAUSTED_BEFORE_SEND"):
        ledger.start_send("Q02-A:SUMMARY:1", "fixture-digest", "httpx.MockTransport")
    assert ledger.state["provider_requests_started"] == 0
    assert ledger.state["currently_reserved_usd_micro"] == 0
    assert not (tmp_path / "trace.jsonl.gz").exists()


def test_unknown_send_is_reserved_without_retry_or_next_case(tmp_path):
    result = run_v2.run_mock(tmp_path / "unknown", scenario={"Q02-A": "unknown_first_send"})
    assert result["status"] == "STOPPED"
    assert result["stop_reason"] == "UNKNOWN_SEND_STATE_NO_RETRY"
    assert result["recorded_requests"] == 1
    ledger = json.loads((tmp_path / "unknown" / "MOCK_COST_LEDGER.json").read_text(encoding="utf-8"))
    sent = [slot for slot in ledger["slots"] if slot["request_digest"]]
    assert len(sent) == 1 and sent[0]["status"] == "UNKNOWN"
    assert sent[0]["reserved_usd_micro"] >= live.REQUEST_RESERVE_USD_MICRO
    assert [row["status"] for row in result["cases"][1:]] == ["NOT_STARTED", "NOT_STARTED"]

\n