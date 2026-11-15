import asyncio

import httpx
import pytest

from retention_evidence import stage_facts
import run_recheck
from run_recheck import HARD_CAP_MICRO, MATRIX, REQUEST_CAP, TASK, abc_runner, run_cases


def test_three_case_shared_ledger_reserves_nine_slots(tmp_path):
    abc = abc_runner()
    ledger = abc.GlobalBudgetLedger.create(
        tmp_path / "ledger.json", execution_id="fixture", mode="MOCK",
        request_limit=REQUEST_CAP, hard_cap_usd_micro=HARD_CAP_MICRO,
    )
    assert tuple(dict.fromkeys(slot["case_id"] for slot in ledger.state["slots"])) == MATRIX
    assert sum(slot["purpose"] == "SUMMARY" for slot in ledger.state["slots"]) == 6
    assert sum(slot["purpose"] == "ANSWER" for slot in ledger.state["slots"]) == 3
    assert ledger.state["request_limit"] == 9
    assert ledger.state["hard_cap_usd_micro"] == 60_000
    assert REQUEST_CAP * abc.REQUEST_RESERVE_USD_MICRO == 37_935
    with pytest.raises(abc.RunnerStop, match="NOT_IN_FROZEN_MATRIX"):
        ledger.start_send("Q06-A:ANSWER:1", "unplanned", "fixture")
    assert ledger.state["provider_requests_started"] == 0


def test_shared_budget_refuses_reservation_before_send(tmp_path):
    abc = abc_runner()
    ledger = abc.GlobalBudgetLedger.create(
        tmp_path / "ledger.json", execution_id="fixture", mode="MOCK",
        request_limit=REQUEST_CAP, hard_cap_usd_micro=2 * abc.REQUEST_RESERVE_USD_MICRO - 1,
    )
    ledger.start_send("Q02-A:SUMMARY:1", "first", "fixture")
    # Leave the prior reservation unresolved so another Case cannot take it.
    with pytest.raises(abc.RunnerStop, match="GLOBAL_BUDGET_EXHAUSTED_BEFORE_SEND"):
        ledger.start_send("Q02-B:SUMMARY:1", "next", "fixture")
    assert ledger.state["provider_requests_started"] == 1
    assert ledger.state["currently_reserved_usd_micro"] == abc.REQUEST_RESERVE_USD_MICRO


def test_unknown_stops_the_later_cases_on_the_same_ledger(tmp_path):
    abc = abc_runner()
    ledger = abc.GlobalBudgetLedger.create(
        tmp_path / "ledger.json", execution_id="fixture", mode="MOCK",
        request_limit=REQUEST_CAP, hard_cap_usd_micro=HARD_CAP_MICRO,
    )
    attempts = []

    def fail(request):
        attempts.append(request.url.host)
        raise httpx.ReadTimeout("simulated unknown result")

    transport = abc.BudgetedAsyncTransport(
        inner=httpx.MockTransport(fail), ledger=ledger, case_id=MATRIX[0], mode="MOCK",
        trace_path=tmp_path / "trace.jsonl.gz",
    )

    async def attempt():
        request = httpx.Request("POST", "https://api.deepseek.com/chat/completions", json={
            "model": abc.MODEL, "thinking": {"type": "disabled"}, "temperature": 0,
            "max_tokens": 512, "messages": [
                {"role": "system", "content": "Compress only the supplied conversation."},
                {"role": "user", "content": "isolated recheck fixture"},
            ],
        })
        await transport.handle_async_request(request)

    with pytest.raises(httpx.ReadTimeout):
        asyncio.run(attempt())
    assert attempts == ["api.deepseek.com"]
    assert ledger.state["slots"][0]["status"] == "UNKNOWN"
    assert ledger.state["provider_requests_started"] == 1
    assert ledger.state["currently_reserved_usd_micro"] == abc.REQUEST_RESERVE_USD_MICRO
    with pytest.raises(abc.RunnerStop, match="UNKNOWN_SEND_STATE_NO_RETRY"):
        ledger.next_slot(MATRIX[1], "SUMMARY")


@pytest.mark.parametrize("approved_task", [None, "ABC-LIVE-ENV-UNBLOCK-01"])
def test_live_entry_rejects_missing_or_historical_authority(tmp_path, approved_task):
    abc = abc_runner()
    output = tmp_path / "live"
    with pytest.raises(RuntimeError, match="NEW_LIVE_PROVIDER_AUTHORIZATION_REQUIRED"):
        run_cases(abc, output, mode="LIVE", config={}, api_key="", authorized_task=approved_task)
    assert not output.exists()


def test_live_entry_rejects_a_failed_preflight_even_with_task_name(tmp_path):
    abc = abc_runner()
    output = tmp_path / "live"
    with pytest.raises(abc.RunnerStop, match="RECHECK_TECHNICAL_PREFLIGHT_REQUIRED"):
        run_cases(abc, output, mode="LIVE", config={}, api_key="", authorized_task=TASK)
    assert not output.exists()


def test_source_invalidated_while_first_summary_returns_stops_remaining_sends(tmp_path, monkeypatch):
    from opspilot.domain.database import connect

    real_mock = run_recheck.mock_transport
    dispatches = []

    def with_source_change(abc, case_id, first_summary):
        fixture = real_mock(abc, case_id, first_summary)

        def respond(request):
            dispatches.append(case_id)
            response = fixture.handle_request(request)
            with connect(abc.recheck_case_databases[case_id]) as db:
                changed = db.execute("UPDATE messages SET body_digest=? WHERE sequence=3", ("0" * 64,))
                assert changed.rowcount == 1
            return response

        return httpx.MockTransport(respond)

    monkeypatch.setattr(run_recheck, "mock_transport", with_source_change)
    abc = abc_runner()
    result = run_cases(
        abc, tmp_path / "source-failure", mode="MOCK", config=abc._mock_config(), api_key=run_recheck.MOCK_KEY,
    )
    assert result["status"] == "STOPPED"
    assert result["stop_reason"] == "RECHECK_SOURCE_INVALIDATED"
    assert dispatches == [MATRIX[0]]
    assert result["summary_requests"] == 1 and result["answer_requests"] == 0
    assert [row["status"] for row in result["cases"][1:]] == ["NOT_STARTED", "NOT_STARTED"]


@pytest.mark.parametrize(
    ("text", "seq", "visibility"),
    [
        ("部署版本未知。", 11, "MISSING"),
        ("协议从 v1.2 更新到 v1.3；max_attempts 改为 5。", 11, "PARTIAL_OR_UNSOURCED"),
        ("协议从 v1.2 更新到 v1.3；max_attempts 从 5 改为 3。", 11, "PARTIAL_OR_UNSOURCED"),
        ("协议从 v1.2 更新到 v1.3；max_attempts 从 3 改为 5。", 12, "PARTIAL_OR_UNSOURCED"),
        ("协议从 v1.2 更新到 v1.3；max_attempts 从 3 改为 5。", 11, "COMPLETE_TEXT_WITH_SOURCE"),
    ],
)
def test_l2_requires_text_relation_and_expected_source(text, seq, visibility):
    assert stage_facts("Q06-B", {"timeline": [{"text": text, "source_sequences": [seq]}]})["visibility"] == visibility
