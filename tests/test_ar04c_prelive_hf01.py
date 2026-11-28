from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import httpx
import pytest


EXPERIMENT_ID = "AR-04C-REAL-JOURNEY-01"


def _write_authorization(tmp_path: Path, monkeypatch, *, include_execution_head: bool = True) -> tuple[Path, Path]:
    import opspilot.assistant as assistant
    from opspilot.domain.assistant_experiment import (
        AR04C_CONDITION_BUDGET_USD_MICRO,
        AR04C_CONDITION_PROVIDER_LIMIT,
        AR04C_MAX_PROVIDER_RESERVATION_USD_MICRO,
        AR04C_PRICE_VERSION,
        BUDGET_USD_MICRO,
    )

    branch = subprocess.run(
        ["git", "branch", "--show-current"], cwd=assistant.ROOT,
        text=True, capture_output=True, check=True,
    ).stdout.strip()
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=assistant.ROOT,
        text=True, capture_output=True, check=True,
    ).stdout.strip()
    contract_digest = assistant._ar04c_contract_digest()
    assert contract_digest
    auth = {
        "authorization_id": assistant.AR04C_AUTHORIZATION_ID,
        "experiment_id": assistant.AR04C_EXPERIMENT_ID,
        "status": "AUTHORIZED_ONE_SHOT",
        "authorization_source": "Explicit user authorization for AR-04C-REAL-JOURNEY-01",
        "branch": branch,
        "base_sha": "60eee87bfe3cca522011316cb4cd2c0064ad291b",
        "frozen_contract_sha256": contract_digest,
        "provider": "DeepSeek",
        "model": "deepseek-flash",
        "thinking": {"type": "disabled"},
        "provider_limit": 16,
        "providers_per_condition": AR04C_CONDITION_PROVIDER_LIMIT,
        "mcp_limit": None,
        "application_budget_usd_micro": BUDGET_USD_MICRO,
        "condition_budget_usd_micro": AR04C_CONDITION_BUDGET_USD_MICRO,
        "provider_reservation_usd_micro": AR04C_MAX_PROVIDER_RESERVATION_USD_MICRO,
        "price_version": AR04C_PRICE_VERSION,
        "max_tokens": 2048,
        "tool_choice": "auto when tools are supplied",
        "parallel_tool_calls": False,
        "stream": False,
        "context_input_limit_tokens": 12000,
        "request_timeout_seconds": 30,
        "provider_concurrency": 1,
        "automatic_retries": 0,
        "manual_retries": 0,
        "business_writes_allowed": False,
        "authorized_on": "2026-11-05T00:00:00Z",
        "authorization_card_sha256": "a" * 64,
    }
    if include_execution_head:
        auth["execution_head_sha"] = head
    auth_path = tmp_path / "PAID_AUTHORIZATION.json"
    claim_path = tmp_path / ".runtime" / "ar04c-test" / "claim.json"
    auth_path.parent.mkdir(parents=True, exist_ok=True)
    auth_path.write_text(json.dumps(auth, sort_keys=True), encoding="utf-8")
    monkeypatch.setattr(assistant, "AR04C_AUTH_RECORD", auth_path)
    monkeypatch.setattr(assistant, "AR04C_CLAIM", claim_path)
    monkeypatch.setenv("OPSPILOT_ASSISTANT_PROVIDER_ENABLED", "1")
    monkeypatch.setenv("OPSPILOT_ASSISTANT_EXPERIMENT_ID", EXPERIMENT_ID)
    monkeypatch.setenv("OPSPILOT_MODEL_API_KEY", "test-only-not-a-real-key")
    monkeypatch.setenv("OPSPILOT_MODEL_NAME", "deepseek-flash")
    monkeypatch.setenv("OPSPILOT_MODEL_BASE_URL", "https://api.deepseek.com")
    monkeypatch.setenv("OPSPILOT_AR04C_MEMORY_MODE", "OFF")
    monkeypatch.setenv("OPSPILOT_AR04C_REAL_JOURNEY_01_ONE_SHOT_TOKEN", "temp-test-token-never-sent")
    return auth_path, claim_path


def test_ar04c_authorization_positive_claim_is_atomic_and_head_bound(tmp_path, monkeypatch):
    import opspilot.assistant as assistant

    _auth_path, claim_path = _write_authorization(tmp_path, monkeypatch)
    script = r'''
import sys
from pathlib import Path
import opspilot.assistant as a
a.AR04C_AUTH_RECORD = Path(sys.argv[1])
a.AR04C_CLAIM = Path(sys.argv[2])
try:
    a._ar04c_create_one_shot_claim()
except RuntimeError:
    print("LOST")
else:
    print("WON" if a._ar04c_one_shot_authorized(a.AR04C_EXPERIMENT_ID) else "WINNER_NOT_AUTHORIZED")
'''
    processes = [
        subprocess.Popen(
            [sys.executable, "-c", script, str(_auth_path), str(claim_path)],
            cwd=assistant.ROOT, env=dict(os.environ), text=True,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        for _ in range(2)
    ]
    results = [process.communicate(timeout=30) for process in processes]
    assert all(process.returncode == 0 for process in processes), results
    outcomes = [stdout.strip() for stdout, _stderr in results]
    assert sorted(outcomes) == ["LOST", "WON"]
    assert claim_path.exists()
    claim = json.loads(claim_path.read_text(encoding="utf-8"))
    assert claim["execution_head_sha"] == subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=assistant.ROOT,
        text=True, capture_output=True, check=True,
    ).stdout.strip()
    # The parent process did not win the O_EXCL claim race and cannot reuse it.
    assert assistant._ar04c_one_shot_authorized(EXPERIMENT_ID) is False


def test_ar04c_execution_head_missing_from_authorization_fails_closed(tmp_path, monkeypatch):
    import opspilot.assistant as assistant

    _write_authorization(tmp_path, monkeypatch, include_execution_head=False)
    with pytest.raises(RuntimeError, match="AR04C_ONE_SHOT_AUTHORIZATION_INVALID"):
        assistant._ar04c_create_one_shot_claim()


@pytest.mark.parametrize(
    ("field", "value"),
    [("max_tokens", 64), ("provider_reservation_usd_micro", 1)],
)
def test_ar04c_authorization_parameter_mismatch_cannot_create_claim(tmp_path, monkeypatch, field, value):
    import opspilot.assistant as assistant

    auth_path, _claim_path = _write_authorization(tmp_path, monkeypatch)
    authorization = json.loads(auth_path.read_text(encoding="utf-8"))
    authorization[field] = value
    auth_path.write_text(json.dumps(authorization, sort_keys=True), encoding="utf-8")
    with pytest.raises(RuntimeError, match="AR04C_ONE_SHOT_AUTHORIZATION_INVALID"):
        assistant._ar04c_create_one_shot_claim()


def test_ar04c_claim_tamper_is_rejected_before_model_construction(tmp_path, monkeypatch):
    import opspilot.assistant as assistant

    _write_authorization(tmp_path, monkeypatch)
    assistant._ar04c_create_one_shot_claim()
    claim = json.loads(assistant.AR04C_CLAIM.read_text(encoding="utf-8"))
    claim["frozen_contract_sha256"] = "0" * 64
    assistant.AR04C_CLAIM.write_text(json.dumps(claim, sort_keys=True), encoding="utf-8")
    assert assistant._ar04c_one_shot_authorized(EXPERIMENT_ID) is False
    with pytest.raises(RuntimeError, match="AR04C_ONE_SHOT_AUTHORIZATION_REQUIRED"):
        assistant.create_assistant_model(
            transport_async=httpx.MockTransport(lambda request: (_ for _ in ()).throw(AssertionError("transport called"))),
            transport_sync=httpx.MockTransport(lambda request: (_ for _ in ()).throw(AssertionError("transport called"))),
        )


def test_ar04c_authorization_change_after_claim_is_rejected(tmp_path, monkeypatch):
    import opspilot.assistant as assistant

    auth_path, _claim_path = _write_authorization(tmp_path, monkeypatch)
    assistant._ar04c_create_one_shot_claim()
    authorization = json.loads(auth_path.read_text(encoding="utf-8"))
    authorization["execution_head_sha"] = "0" * 40
    auth_path.write_text(json.dumps(authorization, sort_keys=True), encoding="utf-8")
    assert assistant._ar04c_one_shot_authorized(EXPERIMENT_ID) is False
    with pytest.raises(RuntimeError, match="AR04C_ONE_SHOT_AUTHORIZATION_REQUIRED"):
        assistant.create_assistant_model(
            transport_async=httpx.MockTransport(lambda request: (_ for _ in ()).throw(AssertionError("transport called"))),
            transport_sync=httpx.MockTransport(lambda request: (_ for _ in ()).throw(AssertionError("transport called"))),
        )


def test_ar04c_unknown_stop_is_persisted_and_cannot_be_reclaimed(tmp_path, monkeypatch):
    import opspilot.assistant as assistant
    from opspilot.domain.assistant_experiment import initialize_experiment

    _write_authorization(tmp_path, monkeypatch)
    assistant._ar04c_create_one_shot_claim()
    db_path = tmp_path / "condition-off.sqlite3"
    initialize_experiment(db_path, EXPERIMENT_ID)
    assistant._ar04c_bind_campaign_database(db_path, "OFF")
    dispatch_token = assistant._AR04C_DISPATCH_CONTEXT.set({
        "experiment_id": EXPERIMENT_ID,
        "db_path": str(db_path.resolve()),
        "memory_mode": "OFF",
        "run_id": "offline-test-run",
        "logical_key": "offline-test-call",
    })
    try:
        assistant._ar04c_consume_claim_before_provider_send()
    finally:
        assistant._AR04C_DISPATCH_CONTEXT.reset(dispatch_token)
    assistant._ar04c_stop_claim("PROVIDER_RESULT_UNKNOWN")
    state = json.loads(assistant._ar04c_claim_state_path().read_text(encoding="utf-8"))
    assert state["status"] == "STOPPED"
    assert state["stop_reason"] == "PROVIDER_RESULT_UNKNOWN"
    assert assistant._ar04c_one_shot_authorized(EXPERIMENT_ID) is False
    with pytest.raises(RuntimeError, match="AR04C_ONE_SHOT_CLAIM_ALREADY_EXISTS"):
        assistant._ar04c_create_one_shot_claim()


def test_ar04c_consumed_claim_cannot_be_replayed_by_new_worker_process(tmp_path, monkeypatch):
    import opspilot.assistant as assistant
    from opspilot.domain.assistant_experiment import initialize_experiment

    auth_path, claim_path = _write_authorization(tmp_path, monkeypatch)
    assistant._ar04c_create_one_shot_claim()

    script = r'''
import httpx, sys
from pathlib import Path
import opspilot.assistant as a
a.AR04C_AUTH_RECORD = Path(sys.argv[1])
a.AR04C_CLAIM = Path(sys.argv[2])
try:
    a.create_assistant_model(
        transport_async=httpx.MockTransport(lambda request: (_ for _ in ()).throw(AssertionError("transport called"))),
        transport_sync=httpx.MockTransport(lambda request: (_ for _ in ()).throw(AssertionError("transport called"))),
    )
except RuntimeError as error:
    print(str(error))
    raise SystemExit(0)
raise SystemExit(9)
'''
    env = dict(os.environ)
    env.update({
        "OPSPILOT_ASSISTANT_PROVIDER_ENABLED": "1",
        "OPSPILOT_ASSISTANT_EXPERIMENT_ID": EXPERIMENT_ID,
        "OPSPILOT_MODEL_API_KEY": "test-only-not-a-real-key",
        "OPSPILOT_MODEL_NAME": "deepseek-flash",
        "OPSPILOT_MODEL_BASE_URL": "https://api.deepseek.com",
        "OPSPILOT_AR04C_MEMORY_MODE": "OFF",
        "OPSPILOT_AR04C_REAL_JOURNEY_01_ONE_SHOT_TOKEN": "temp-test-token-never-sent",
    })

    def fresh_process_must_refuse():
        replay = subprocess.run(
            [sys.executable, "-c", script, str(auth_path), str(claim_path)],
            cwd=assistant.ROOT, env=env, text=True, capture_output=True, check=False,
        )
        assert replay.returncode == 0, replay.stdout + replay.stderr
        assert "AR04C_ONE_SHOT_AUTHORIZATION_REQUIRED" in replay.stdout

    fresh_process_must_refuse()
    db_path = tmp_path / "condition-off.sqlite3"
    initialize_experiment(db_path, EXPERIMENT_ID)
    assistant._ar04c_bind_campaign_database(db_path, "OFF")
    dispatch_token = assistant._AR04C_DISPATCH_CONTEXT.set({
        "experiment_id": EXPERIMENT_ID,
        "db_path": str(db_path.resolve()),
        "memory_mode": "OFF",
        "run_id": "offline-test-run",
        "logical_key": "offline-test-call",
    })
    try:
        assistant._ar04c_consume_claim_before_provider_send()
    finally:
        assistant._AR04C_DISPATCH_CONTEXT.reset(dispatch_token)
    state = json.loads(assistant._ar04c_claim_state_path().read_text(encoding="utf-8"))
    assert state["status"] == "CONSUMED"
    assert "OFF" in state["database_ids"]
    fresh_process_must_refuse()


def test_ar04c_mock_provider_transport_requires_formal_dispatch_context(tmp_path, monkeypatch):
    import asyncio
    import opspilot.assistant as assistant

    _write_authorization(tmp_path, monkeypatch)
    assistant._ar04c_create_one_shot_claim()
    sent = []

    def respond(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        return httpx.Response(200, json={
            "id": "chatcmpl-ar04c-prelive-mock",
            "object": "chat.completion",
            "created": 1,
            "model": "deepseek-flash",
            "choices": [{"index": 0, "message": {"role": "assistant", "content": "mock reply"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 4, "completion_tokens": 2, "total_tokens": 6},
        }, request=request)

    model = assistant.create_assistant_model(
        transport_async=httpx.MockTransport(respond),
        transport_sync=httpx.MockTransport(respond),
    )
    with pytest.raises(RuntimeError, match="AR04C_ONE_SHOT_DISPATCH_CONTEXT_REQUIRED"):
        asyncio.run(model.ainvoke("offline-only"))
    assert sent == []


def test_ar04c_mock_provider_success_consumes_claim_before_http_and_pins_database(tmp_path, monkeypatch):
    import asyncio
    import opspilot.assistant as assistant
    from opspilot.domain.assistant_experiment import initialize_experiment

    _write_authorization(tmp_path, monkeypatch)
    assistant._ar04c_create_one_shot_claim()
    db_path = tmp_path / "condition-off.sqlite3"
    initialize_experiment(db_path, EXPERIMENT_ID)
    sent = []

    def respond(request: httpx.Request) -> httpx.Response:
        state = json.loads(assistant._ar04c_claim_state_path().read_text(encoding="utf-8"))
        assert state["status"] == "CONSUMED"
        assert state["database_ids"].get("OFF")
        assert request.url == "https://api.deepseek.com/chat/completions"
        sent.append(request)
        return httpx.Response(200, json={
            "id": "chatcmpl-ar04c-prelive-success",
            "object": "chat.completion",
            "created": 1,
            "model": "deepseek-flash",
            "choices": [{"index": 0, "message": {"role": "assistant", "content": "offline mock reply"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 4, "completion_tokens": 3, "total_tokens": 7},
        }, request=request)

    model = assistant.create_assistant_model(
        transport_async=httpx.MockTransport(respond),
        transport_sync=httpx.MockTransport(respond),
    )
    assistant._ar04c_bind_campaign_database(db_path, "OFF")
    dispatch_token = assistant._AR04C_DISPATCH_CONTEXT.set({
        "experiment_id": EXPERIMENT_ID,
        "db_path": str(db_path.resolve()),
        "memory_mode": "OFF",
        "run_id": "offline-test-run",
        "logical_key": "offline-test-call",
    })
    try:
        result = asyncio.run(model.ainvoke("offline-only"))
    finally:
        assistant._AR04C_DISPATCH_CONTEXT.reset(dispatch_token)
    assert result.content == "offline mock reply"
    assert len(sent) == 1
    state = json.loads(assistant._ar04c_claim_state_path().read_text(encoding="utf-8"))
    assert state["status"] == "CONSUMED"
    replacement_db = tmp_path / "replacement.sqlite3"
    initialize_experiment(replacement_db, EXPERIMENT_ID)
    with pytest.raises(RuntimeError, match="AR04C_CAMPAIGN_DATABASE_REPLAY"):
        assistant._ar04c_bind_campaign_database(replacement_db, "OFF")




def test_ar04c_mock_provider_unknown_persists_stop_and_blocks_followup(tmp_path, monkeypatch):
    import asyncio
    import opspilot.assistant as assistant
    from langchain_openai.chat_models.base import OpenAIConnectionError
    from opspilot.domain.assistant_experiment import initialize_experiment

    _write_authorization(tmp_path, monkeypatch)
    assistant._ar04c_create_one_shot_claim()
    db_path = tmp_path / "condition-off.sqlite3"
    initialize_experiment(db_path, EXPERIMENT_ID)
    attempts = []

    def fail(request: httpx.Request) -> httpx.Response:
        attempts.append(request)
        raise httpx.ConnectError("offline injected transport failure", request=request)

    model = assistant.create_assistant_model(
        transport_async=httpx.MockTransport(fail),
        transport_sync=httpx.MockTransport(fail),
    )
    assistant._ar04c_bind_campaign_database(db_path, "OFF")
    dispatch_token = assistant._AR04C_DISPATCH_CONTEXT.set({
        "experiment_id": EXPERIMENT_ID,
        "db_path": str(db_path.resolve()),
        "memory_mode": "OFF",
        "run_id": "offline-test-run",
        "logical_key": "offline-test-call",
    })
    try:
        with pytest.raises(OpenAIConnectionError, match="Connection error"):
            asyncio.run(model.ainvoke("offline-only"))
    finally:
        assistant._AR04C_DISPATCH_CONTEXT.reset(dispatch_token)
    assert len(attempts) == 1
    state = json.loads(assistant._ar04c_claim_state_path().read_text(encoding="utf-8"))
    assert state["status"] == "STOPPED"
    assert state["stop_reason"] == "PROVIDER_TRANSPORT_UNKNOWN"
    with pytest.raises(RuntimeError, match="AR04C_ONE_SHOT_DISPATCH_CONTEXT_REQUIRED"):
        asyncio.run(model.ainvoke("must-not-retry"))
    assert len(attempts) == 1
