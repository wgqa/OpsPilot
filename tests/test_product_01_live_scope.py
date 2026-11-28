"""Single transport boundary check for the new live identity. No Provider I/O."""
import asyncio
import json
import subprocess
from types import SimpleNamespace

import httpx
import pytest

import opspilot.assistant as assistant
from opspilot.domain import assistant_experiment as ledger
from opspilot.domain.database import connect


def test_product_01_live_scope_requires_one_claim_and_one_reservation(tmp_path, monkeypatch):
    exp = ledger.PRODUCT_01_LIVE_EXPERIMENT_ID
    monkeypatch.setattr(assistant, "PRODUCT_01_RUNTIME", tmp_path)
    monkeypatch.setenv(ledger.EXPERIMENT_ENV, exp)
    monkeypatch.setenv("OPSPILOT_ASSISTANT_PROVIDER_ENABLED", "1")
    monkeypatch.setenv("OPSPILOT_MODEL_API_KEY", "offline-test-only")
    monkeypatch.setenv("OPSPILOT_MODEL_NAME", "deepseek-flash")
    monkeypatch.setenv("OPSPILOT_MODEL_BASE_URL", "https://api.deepseek.com")
    monkeypatch.setenv(assistant.PRODUCT_01_TOKEN_ENV, "offline-test-token")
    sent = []

    def respond(request):
        body = json.loads(request.content)
        assert str(request.url) == "https://api.deepseek.com/chat/completions"
        assert body["model"] == "deepseek-flash"
        assert body["thinking"] == {"type": "disabled"} and body["max_tokens"] == 2048
        assert body["stream"] is False and "max_completion_tokens" not in body
        state = json.loads(assistant._ar04c_claim_state_path().read_text(encoding="utf-8"))
        assert state["status"] == "CONSUMED" and set(state["database_ids"]) == {"SESSION"}
        assert ledger.read_budget(db, exp)["usd_reserved_micro"] == 668_468
        sent.append(body)
        return httpx.Response(200, json={
            "id": "offline", "object": "chat.completion", "created": 1, "model": "deepseek-flash",
            "choices": [{"index": 0, "message": {"role": "assistant", "content": "offline"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 4, "completion_tokens": 2, "total_tokens": 6},
        })

    transports = dict(transport_async=httpx.MockTransport(respond), transport_sync=httpx.MockTransport(respond))
    with pytest.raises(RuntimeError, match="PRODUCT_01_ONE_SHOT_AUTHORIZATION_REQUIRED"):
        assistant.create_assistant_model(**transports)

    actual_run = subprocess.run

    def git_in_test_branch(args, *positional, **kwargs):
        if args[:3] == ["git", "branch", "--show-current"]:
            return SimpleNamespace(returncode=0, stdout="codex/product-01-slice-02-live\n")
        return actual_run(args, *positional, **kwargs)

    monkeypatch.setattr(subprocess, "run", git_in_test_branch)
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=assistant.ROOT, text=True).strip()
    grant = {
        "authorization_id": "PRODUCT-01-SLICE-02-USER-AUTH", "experiment_id": exp,
        "status": "AUTHORIZED_ONE_SHOT", "authorization_source": "Explicit user authorization for PRODUCT-01-SLICE-02",
        "branch": "codex/product-01-slice-02-live", "base_sha": "3ff5678a2f067ad2bef7945095395d26d59b5328",
        "execution_head_sha": head, "frozen_contract_sha256": assistant._ar04c_contract_digest(exp),
        "provider": "DeepSeek", "model": "deepseek-flash", "thinking": {"type": "disabled"},
        "provider_limit": 24, "providers_per_condition": 24, "mcp_limit": 12,
        "application_budget_usd_micro": 2_000_000, "condition_budget_usd_micro": 2_000_000,
        "provider_reservation_usd_micro": 668_468, "price_version": "DEEPSEEK_FLASH_PEAK_2026-11-07",
        "max_tokens": 2048, "tool_choice": "auto when tools are supplied",
        "parallel_tool_calls": False, "stream": False, "context_input_limit_tokens": 12000,
        "request_timeout_seconds": 30, "provider_concurrency": 1, "automatic_retries": 0, "manual_retries": 0,
        "business_writes_allowed": False, "authorized_on": "offline-test-only", "authorization_card_sha256": "a" * 64,
    }
    (tmp_path / "PAID_AUTHORIZATION.json").write_text(json.dumps(grant), encoding="utf-8")
    assistant._ar04c_create_one_shot_claim()
    with pytest.raises(RuntimeError, match="CLAIM_ALREADY_EXISTS"):
        assistant._ar04c_create_one_shot_claim()

    db = tmp_path / "domain.sqlite3"
    ledger.initialize_experiment(db, exp)
    assistant._ar04c_bind_campaign_database(db, "SESSION")
    with connect(db) as connection:
        connection.execute("CREATE TABLE task_runs (run_id TEXT PRIMARY KEY)")
        connection.execute("INSERT INTO task_runs VALUES ('run-offline')")

    async def invoke_once():
        model = assistant.create_assistant_model(**transports)
        try:
            with assistant._provider_dispatch_context(exp, db, "run-offline", "call-offline"):
                with pytest.raises(RuntimeError, match="PRODUCT_01_DISPATCH_RESERVATION_REQUIRED"):
                    await model.ainvoke("offline")
                ledger.reserve_dispatch(db, experiment_id=exp, run_id="run-offline", kind="MODEL",
                                        logical_key="call-offline", request={"offline": True})
                response = await model.ainvoke("offline")
                with pytest.raises(RuntimeError, match="PRODUCT_01_DISPATCH_ALREADY_SENT"):
                    await model.ainvoke("offline")
            return response
        finally:
            await model.http_async_client.aclose()
            model.http_client.close()

    response = asyncio.run(invoke_once())
    assert response.content == "offline" and len(sent) == 1
    ledger.complete_dispatch(db, experiment_id=exp, run_id="run-offline", kind="MODEL",
                             logical_key="call-offline", usage=response.usage_metadata)
    budget = ledger.read_budget(db, exp)
    assert budget["provider_used"] == 1 and budget["usd_reserved_micro"] == 0
    assert budget["usd_settled_micro"] == 4 and budget["budget_usd_micro"] == 2_000_000
    other_db = tmp_path / "other.sqlite3"
    ledger.initialize_experiment(other_db, exp)
    with pytest.raises(RuntimeError, match="CAMPAIGN_DATABASE_REPLAY"):
        assistant._ar04c_bind_campaign_database(other_db, "SESSION")
