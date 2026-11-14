from __future__ import annotations

import asyncio
import importlib.util
import json
from pathlib import Path

import httpx
import pytest

SCRIPT = Path(__file__).with_name("run_abc_eval.py")
spec = importlib.util.spec_from_file_location("abc_live_runner", SCRIPT)
assert spec is not None and spec.loader is not None
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


def _config_values():
    return {
        "OPSPILOT_MODEL_API_KEY": "unit-test-secret-sentinel",
        "OPSPILOT_MODEL_NAME": runner.MODEL,
        "OPSPILOT_MODEL_BASE_URL": runner.ENDPOINT + "/v1",
        "OPSPILOT_MODEL_CONFIG_VERSION": "unit-model-v1",
        "OPSPILOT_MODEL_PRICE_VERSION": "unit-price-v1",
        "OPSPILOT_ASSISTANT_SERVICE_IDENTITY": "unit-service-identity",
    }


def test_explicit_main_repo_env_path_and_presence_only_output(tmp_path, monkeypatch, capsys):
    worktree_root = tmp_path / "repo" / ".worktrees" / "candidate"
    main_env = tmp_path / "repo" / ".env"
    main_env.parent.mkdir(parents=True)
    main_env.write_text("synthetic test fixture only\n", encoding="utf-8")
    values = _config_values()
    loaded_paths = []

    def loader(path):
        loaded_paths.append(Path(path))
        for key, value in values.items():
            monkeypatch.setenv(key, value)

    report = runner.load_main_environment(root=worktree_root, loader=loader, emit_presence=True)
    printed = capsys.readouterr().out

    assert loaded_paths == [main_env]
    assert report["main_repo_env_found"] is True
    assert report["environment_loaded_from_main_repo_env"] is True
    assert report["api_key_present"] is True
    assert report["runtime_config_valid"] is True
    assert report["endpoint_canonicalized_from_official_root_or_v1"] is True
    assert all(report["required_presence_after_load"].values())
    assert all(report["effective_required_presence"].values())
    assert "unit-test-secret-sentinel" not in printed
    assert all(f"'{key}': True" in printed or f'"{key}": true' in printed for key in runner.REQUIRED_ENV)


def test_nonsecret_supplement_never_invents_api_key(tmp_path, monkeypatch):
    worktree_root = tmp_path / "repo" / ".worktrees" / "candidate"
    main_env = tmp_path / "repo" / ".env"
    main_env.parent.mkdir(parents=True)
    main_env.write_text("synthetic test fixture only\n", encoding="utf-8")
    monkeypatch.delenv("OPSPILOT_MODEL_API_KEY", raising=False)
    for key in runner.REQUIRED_ENV:
        if key != "OPSPILOT_MODEL_API_KEY":
            monkeypatch.delenv(key, raising=False)

    report = runner.load_main_environment(root=worktree_root, loader=lambda _path: None)

    assert report["environment_loaded_from_main_repo_env"] is True
    assert report["api_key_present"] is False
    assert report["runtime_config_valid"] is False
    assert report["error"] == "MODEL_API_KEY_NOT_PRESENT_AFTER_MAIN_ENV_LOAD"
    assert set(report["supplemented_non_secret_configuration"]) == set(runner.NON_SECRET_DEFAULTS)
    assert not report["effective_required_presence"]["OPSPILOT_MODEL_API_KEY"]


def test_endpoint_canonicalization_does_not_rewrite_other_hosts(tmp_path, monkeypatch):
    worktree_root = tmp_path / "repo" / ".worktrees" / "candidate"
    main_env = tmp_path / "repo" / ".env"
    main_env.parent.mkdir(parents=True)
    main_env.write_text("synthetic test fixture only\n", encoding="utf-8")
    values = _config_values()
    values["OPSPILOT_MODEL_BASE_URL"] = "https://not-deepseek.example/v1"

    def loader(_path):
        for key, value in values.items():
            monkeypatch.setenv(key, value)

    report = runner.load_main_environment(root=worktree_root, loader=loader)

    assert report["endpoint_canonicalized_from_official_root_or_v1"] is False
    assert report["runtime_config_valid"] is False
    assert report["error"] == "RUNTIME_PROVIDER_ENDPOINT_INVALID"


def test_global_budget_rejects_before_first_dispatch_and_persists(tmp_path):
    path = tmp_path / "global-ledger.json"
    ledger = runner.GlobalBudgetLedger.create(
        path, execution_id="test-budget", mode="MOCK",
        hard_cap_usd_micro=runner.REQUEST_RESERVE_USD_MICRO - 1,
    )
    logical_id = "Q02-A:SUMMARY:1"

    with pytest.raises(runner.RunnerStop, match="GLOBAL_BUDGET_EXHAUSTED_BEFORE_SEND"):
        ledger.start_send(logical_id, "a" * 64, "unit-test")

    persisted = json.loads(path.read_text(encoding="utf-8"))
    slot = next(item for item in persisted["slots"] if item["logical_id"] == logical_id)
    assert persisted["provider_requests_started"] == 0
    assert persisted["stop_reason"] == "GLOBAL_BUDGET_EXHAUSTED_BEFORE_SEND"
    assert slot["status"] == "NOT_SENT"
    assert slot["request_digest"] is None


def test_unknown_inflight_slot_is_persisted_and_cannot_be_retried(tmp_path):
    path = tmp_path / "global-ledger.json"
    ledger = runner.GlobalBudgetLedger.create(path, execution_id="test-unknown", mode="LIVE")
    logical_id = "Q02-A:SUMMARY:1"
    ledger.start_send(logical_id, "b" * 64, "unit-test")

    reopened = runner.GlobalBudgetLedger.open_for_inspection(path)
    slot = next(item for item in reopened.state["slots"] if item["logical_id"] == logical_id)
    assert reopened.state["status"] == "STOPPED"
    assert reopened.state["stop_reason"] == "UNKNOWN_SEND_STATE_REFUSE_RETRY"
    assert slot["status"] == "UNKNOWN"
    assert reopened.state["currently_reserved_usd_micro"] == runner.REQUEST_RESERVE_USD_MICRO
    with pytest.raises(runner.RunnerStop, match="UNKNOWN_SEND_STATE_REFUSE_RETRY"):
        reopened.start_send(logical_id, "b" * 64, "unit-test")
    assert reopened.state["provider_requests_started"] == 1


def test_global_ledger_rejects_duplicate_logical_request(tmp_path):
    path = tmp_path / "global-ledger.json"
    ledger = runner.GlobalBudgetLedger.create(path, execution_id="test-once", mode="MOCK")
    logical_id = "Q02-A:SUMMARY:1"
    ledger.start_send(logical_id, "c" * 64, "unit-test")
    ledger.finish(
        logical_id, status="COMPLETED", http_status=200,
        provider_request_id="fixture-id", response_model=runner.MODEL,
        usage={"input_tokens": 2, "output_tokens": 1, "total_tokens": 3},
        settled_usd_micro=1, finish_reason="stop",
    )

    with pytest.raises(runner.RunnerStop, match="LOGICAL_REQUEST_ALREADY_SENT_REFUSE_RETRY"):
        ledger.start_send(logical_id, "c" * 64, "unit-test")
    assert ledger.state["provider_requests_started"] == 1


def test_history_recall_transport_rejects_tool_choice_auto_before_dispatch(tmp_path):
    path = tmp_path / "global-ledger.json"
    ledger = runner.GlobalBudgetLedger.create(path, execution_id="test-tool-choice", mode="MOCK")
    calls = []
    inner = httpx.MockTransport(lambda request: (calls.append(request) or httpx.Response(200, json={})))
    transport = runner.BudgetedAsyncTransport(
        inner=inner, ledger=ledger, case_id="Q02-A", mode="MOCK",
        trace_path=tmp_path / "trace.jsonl.gz",
    )
    request = httpx.Request(
        "POST", runner.ENDPOINT + "/chat/completions",
        json={
            "model": runner.MODEL,
            "thinking": {"type": "disabled"},
            "temperature": 0,
            "stream": False,
            "max_tokens": runner.MAX_OUTPUT_TOKENS,
            "messages": [{"role": "user", "content": "synthetic question"}],
            "tools": [],
            "tool_choice": "auto",
        },
    )

    async def dispatch():
        try:
            await transport.handle_async_request(request)
        finally:
            await transport.aclose()

    with pytest.raises(runner.RunnerStop, match="HISTORY_RECALL_REQUIRES_TOOL_CHOICE_NONE"):
        asyncio.run(dispatch())
    assert calls == []
    assert ledger.state["provider_requests_started"] == 0
    assert ledger.state["stop_reason"] == "HISTORY_RECALL_REQUIRES_TOOL_CHOICE_NONE"


def test_unknown_transport_failure_stops_and_refuses_a_second_send(tmp_path):
    path = tmp_path / "global-ledger.json"
    ledger = runner.GlobalBudgetLedger.create(path, execution_id="test-send-unknown", mode="MOCK")
    calls = []

    def fail_once(_request):
        calls.append(1)
        raise httpx.ConnectError("synthetic unknown send state")

    inner = httpx.MockTransport(fail_once)
    transport = runner.BudgetedAsyncTransport(
        inner=inner, ledger=ledger, case_id="Q02-A", mode="MOCK",
        trace_path=tmp_path / "trace.jsonl.gz",
    )
    request = httpx.Request(
        "POST", runner.ENDPOINT + "/chat/completions",
        json={
            "model": runner.MODEL,
            "thinking": {"type": "disabled"},
            "temperature": 0,
            "stream": False,
            "max_tokens": runner.MAX_OUTPUT_TOKENS,
            "messages": [{"role": "user", "content": "synthetic question"}],
            "tools": [],
            "tool_choice": "none",
        },
    )

    async def dispatch():
        try:
            await transport.handle_async_request(request)
        finally:
            await transport.aclose()

    with pytest.raises(httpx.ConnectError):
        asyncio.run(dispatch())
    assert len(calls) == 1
    assert ledger.state["stop_reason"] == "UNKNOWN_SEND_STATE_NO_RETRY"
    assert next(s for s in ledger.state["slots"] if s["logical_id"] == "Q02-A:ANSWER:1")["status"] == "UNKNOWN"
    with pytest.raises(runner.RunnerStop, match="UNKNOWN_SEND_STATE_NO_RETRY"):
        ledger.start_send("Q02-A:ANSWER:1", "d" * 64, "unit-test")
    assert len(calls) == 1
    assert ledger.state["provider_requests_started"] == 1
