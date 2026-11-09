"""Targeted offline regressions for legacy Provider isolation and pool resume."""
from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import httpx
import pytest


def _env(monkeypatch, *, base_url="https://api.deepseek.com", legacy=False, provider=True):
    from opspilot.domain.assistant_experiment import EXPERIMENT_ENV

    monkeypatch.setenv("OPSPILOT_ASSISTANT_RUNTIME_ENABLED", "1")
    monkeypatch.setenv("OPSPILOT_ASSISTANT_PROVIDER_ENABLED", "1" if provider else "0")
    monkeypatch.setenv("OPSPILOT_MODEL_API_KEY", "test-only-not-a-real-key")
    monkeypatch.setenv("OPSPILOT_MODEL_NAME", "deepseek-flash")
    monkeypatch.setenv("OPSPILOT_MODEL_BASE_URL", base_url)
    monkeypatch.setenv("OPSPILOT_MODEL_CONFIG_VERSION", "offline-model-config-v1")
    monkeypatch.setenv("OPSPILOT_MODEL_PRICE_VERSION", "offline-price-v1")
    monkeypatch.setenv("OPSPILOT_ASSISTANT_SERVICE_IDENTITY", "offline-test-service")
    monkeypatch.delenv(EXPERIMENT_ENV, raising=False)
    if legacy:
        monkeypatch.setenv("OPSPILOT_LEGACY_PROVIDER_ENABLED", "1")
    else:
        monkeypatch.delenv("OPSPILOT_LEGACY_PROVIDER_ENABLED", raising=False)


def _mock_legacy_chat(monkeypatch, requests):
    from langchain_core.messages import AIMessage
    import langchain_openai

    class MockLegacyChat:
        def __init__(self, *args, **kwargs):
            self.base_url = str(kwargs.get("base_url") or "https://api.deepseek.com").rstrip("/")

        async def _send(self, messages):
            async def handler(request):
                requests.append({"url": str(request.url), "body": json.loads(await request.aread())})
                return httpx.Response(200, json={"mock": "legacy-provider"}, request=request)

            body = {
                "model": "deepseek-flash",
                "messages": [{"role": "user", "content": "offline fixture"}],
            }
            async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
                response = await client.post(f"{self.base_url}/chat/completions", json=body)
            assert response.status_code == 200
            return SimpleNamespace(
                content="Offline legacy answer.",
                response_metadata={"headers": {"x-request-id": "offline-legacy-request"}},
                usage_metadata={"input_tokens": 3, "output_tokens": 2, "total_tokens": 5},
            )

        async def astream(self, messages):
            result = await self._send(messages)
            yield result

        async def ainvoke(self, messages):
            return await self._send(messages)

    monkeypatch.setattr(langchain_openai, "ChatOpenAI", MockLegacyChat)


def _mock_investigator_provider(monkeypatch, requests):
    import opspilot.investigator as investigator

    async def fake_run(*args, **kwargs):
        async def handler(request):
            requests.append({"url": str(request.url), "body": json.loads(await request.aread())})
            return httpx.Response(200, json={"mock": "legacy-investigator"}, request=request)

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            await client.post("https://api.deepseek.com/chat/completions", json={
                "model": "deepseek-flash", "messages": [{"role": "user", "content": "offline fixture"}],
            })
        return {"status": "OFFLINE_FIXTURE"}

    monkeypatch.setattr(investigator, "run_investigation", fake_run, raising=False)


def _legacy_investigation_run(db_path):
    from opspilot.domain.task_control import create_session, create_task_with_initial_run, trusted_identity

    identity = trusted_identity(db_path, "support-a")
    session = create_session(db_path, identity)["session_id"]
    return create_task_with_initial_run(
        db_path, identity, session_id=session, service_id="orders-demo",
        integration_id="integration-a", ticket_id="INC-A-001",
        initial_message="Investigate why the API returned 401.",
        idempotency_key="runtime-grant-hf01-legacy-investigation",
    )


def test_plain_messages_cannot_bypass_runtime_grant_without_legacy_authorization(
    demo_db, tmp_path, monkeypatch,
):
    from fastapi.testclient import TestClient
    from opspilot.domain.database import connect
    from opspilot.web.app import create_app
    from test_ar02_assistant import ORIGIN, PASSWORDS
    from test_ar02_journey_p0 import _wait_run
    from test_product_01_runtime_grant_01 import _configure, _provision

    _configure(monkeypatch)
    _env(monkeypatch, base_url="https://unsupported.example")
    _provision(demo_db)
    requests = []
    _mock_legacy_chat(monkeypatch, requests)
    app = create_app(
        db_path=demo_db, checkpoint_db_path=tmp_path / "plain-message-checkpoint.sqlite3",
        start_worker=True, credentials=PASSWORDS, expected_origin=ORIGIN,
        assistant_runtime_enabled=True,
    )
    with TestClient(app) as client:
        login = client.post(
            "/api/auth/login", headers={"Origin": ORIGIN},
            json={"actor_id": "support-a", "password": PASSWORDS["support-a"]},
        )
        headers = {"Origin": ORIGIN, "X-CSRF-Token": login.json()["csrf_token"]}
        session_id = client.post("/api/sessions", headers=headers).json()["session_id"]
        accepted = client.post(
            f"/api/sessions/{session_id}/messages",
            headers={**headers, "Idempotency-Key": "hf01-plain-message"},
            json={"input_kind": "CHAT_READONLY", "body": "Explain this API failure."},
        )
        assert accepted.status_code == 202
        run = _wait_run(client, accepted.json()["run_id"])
        assert requests == []
        assert run["status"] == "FAILED"
    with connect(demo_db) as connection:
        assert connection.execute("SELECT COUNT(*) FROM assistant_runtime_spends").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM chat_attempts").fetchone()[0] == 0


@pytest.mark.parametrize("run_kind", ["INVESTIGATE", "APPROVAL_RESUME"])
def test_legacy_investigator_worker_requires_independent_provider_authorization(
    demo_db, monkeypatch, run_kind,
):
    from opspilot.domain.task_control import TaskControlError
    from opspilot.web.worker import _process_run_inner
    from test_product_01_runtime_grant_01 import _configure, _worker

    _configure(monkeypatch)
    _env(monkeypatch)
    run = _legacy_investigation_run(demo_db)
    requests = []
    _mock_investigator_provider(monkeypatch, requests)
    worker = _worker(demo_db)
    try:
        error = None
        try:
            asyncio.run(_process_run_inner(
                demo_db, demo_db.parent / "legacy-checkpoint.sqlite3", worker.owner_id,
                "executor-a", {"run_id": run["run_id"], "task_id": run["task_id"],
                               "kind": run_kind}, worker.epoch,
            ))
        except TaskControlError as caught:
            error = caught
        assert requests == []
        assert error is not None and error.code == "LEGACY_PROVIDER_AUTHORIZATION_REQUIRED"
    finally:
        worker.release()


def test_direct_investigator_entry_requires_legacy_authorization_before_client_creation(
    demo_db, tmp_path, monkeypatch,
):
    from opspilot.domain.task_control import TaskControlError
    import opspilot.investigator as investigator
    from test_product_01_runtime_grant_01 import _configure

    _configure(monkeypatch)
    _env(monkeypatch)
    run = _legacy_investigation_run(demo_db)
    constructed = []

    def forbidden_client(*args, **kwargs):
        constructed.append(True)
        raise AssertionError("Legacy Provider client must not be constructed without authorization.")

    monkeypatch.setattr(investigator, "ChatOpenAI", forbidden_client)
    with pytest.raises(TaskControlError, match="LEGACY_PROVIDER_AUTHORIZATION_REQUIRED"):
        asyncio.run(investigator.run_investigation(
            run["task_id"], "support-a", db_path=demo_db,
            checkpoint_db_path=tmp_path / "direct-investigator-checkpoint.sqlite3",
            run_id=run["run_id"],
        ))
    assert constructed == []


def test_explicit_legacy_provider_authorization_preserves_old_investigator(
    demo_db, monkeypatch,
):
    from opspilot.web.worker import _process_run_inner
    from test_product_01_runtime_grant_01 import _configure, _worker

    _configure(monkeypatch)
    _env(monkeypatch, legacy=True)
    run = _legacy_investigation_run(demo_db)
    requests = []
    _mock_investigator_provider(monkeypatch, requests)
    worker = _worker(demo_db)
    try:
        asyncio.run(_process_run_inner(
            demo_db, demo_db.parent / "authorized-legacy-checkpoint.sqlite3", worker.owner_id,
            "executor-a", {"run_id": run["run_id"], "task_id": run["task_id"],
                           "kind": "INVESTIGATE"}, worker.epoch,
        ))
    finally:
        worker.release()

    assert len(requests) == 1
    assert requests[0]["url"] == "https://api.deepseek.com/chat/completions"


def test_legacy_authorization_does_not_override_global_provider_disable(
    demo_db, tmp_path, monkeypatch,
):
    from fastapi.testclient import TestClient
    from opspilot.web.app import create_app
    from test_ar02_assistant import ORIGIN, PASSWORDS
    from test_ar02_journey_p0 import _wait_run
    from test_product_01_runtime_grant_01 import _configure, _provision

    _configure(monkeypatch)
    _env(monkeypatch, legacy=True, provider=False)
    _provision(demo_db)
    requests = []
    _mock_legacy_chat(monkeypatch, requests)
    app = create_app(
        db_path=demo_db, checkpoint_db_path=tmp_path / "provider-disabled-checkpoint.sqlite3",
        start_worker=True, credentials=PASSWORDS, expected_origin=ORIGIN,
        assistant_runtime_enabled=True,
    )
    with TestClient(app) as client:
        login = client.post(
            "/api/auth/login", headers={"Origin": ORIGIN},
            json={"actor_id": "support-a", "password": PASSWORDS["support-a"]},
        )
        headers = {"Origin": ORIGIN, "X-CSRF-Token": login.json()["csrf_token"]}
        session_id = client.post("/api/sessions", headers=headers).json()["session_id"]
        accepted = client.post(
            f"/api/sessions/{session_id}/messages",
            headers={**headers, "Idempotency-Key": "hf01-provider-disabled"},
            json={"input_kind": "CHAT_READONLY", "body": "Explain this API failure."},
        )
        run = _wait_run(client, accepted.json()["run_id"])
        assert run["status"] == "FAILED"

    assert requests == []


def test_investigation_update_classifier_requires_legacy_authorization_before_provider_send(
    monkeypatch,
):
    from opspilot.config import LEGACY_PROVIDER_ENABLED
    from opspilot.domain.investigation_updates import classify_input
    from opspilot.domain.task_control import TaskControlError
    import langchain_openai

    _env(monkeypatch)
    requests = []
    constructed = []

    class MockClassifier:
        def __init__(self, **kwargs):
            constructed.append(kwargs)

        def invoke(self, _messages):
            def handler(request):
                requests.append({"url": str(request.url), "body": json.loads(request.content)})
                return httpx.Response(200, json={"mock": "classifier"}, request=request)

            with httpx.Client(transport=httpx.MockTransport(handler)) as client:
                response = client.post(
                    "https://api.deepseek.com/chat/completions",
                    json={"model": "deepseek-flash", "messages": [{"role": "user", "content": "offline"}]},
                )
            assert response.status_code == 200
            return SimpleNamespace(
                content='{"intent":"FOLLOW_UP","change_summary":"","readonly_action":"EXPLAIN"}',
                response_metadata={}, usage_metadata={},
            )

    monkeypatch.setattr(langchain_openai, "ChatOpenAI", MockClassifier)
    prepared = {
        "conversation": [], "source_message": "Explain the current result.",
        "prior_input_text": "Investigate the incident.",
        "prior_readonly_followups": [], "prior_readonly_followup_exclusions": [],
    }
    with pytest.raises(TaskControlError, match="LEGACY_PROVIDER_AUTHORIZATION_REQUIRED"):
        classify_input(prepared=prepared, model_id="deepseek-flash", api_key="offline-key")
    assert constructed == []
    assert requests == []

    monkeypatch.setenv(LEGACY_PROVIDER_ENABLED, "1")
    result = classify_input(prepared=prepared, model_id="deepseek-flash", api_key="offline-key")
    assert result["intent"] == "FOLLOW_UP"
    assert len(constructed) == 1
    assert len(requests) == 1
    assert requests[0]["url"] == "https://api.deepseek.com/chat/completions"


def test_runtime_grant_failure_does_not_fallback_to_legacy_provider(
    demo_db, tmp_path, monkeypatch,
):
    from fastapi.testclient import TestClient
    from opspilot.domain.database import connect
    from opspilot.web.app import create_app
    from test_ar02_assistant import ORIGIN, PASSWORDS
    from test_ar02_journey_p0 import _wait_run
    from test_product_01_runtime_grant_01 import _configure

    _configure(monkeypatch)
    _env(monkeypatch, legacy=True)
    requests = []
    _mock_legacy_chat(monkeypatch, requests)
    factory_calls = []

    def forbidden_runtime_factory(**kwargs):
        factory_calls.append(kwargs)
        raise AssertionError("A missing persisted Grant must fail before client construction.")

    app = create_app(
        db_path=demo_db, checkpoint_db_path=tmp_path / "no-fallback-checkpoint.sqlite3",
        start_worker=True, credentials=PASSWORDS, expected_origin=ORIGIN,
        assistant_runtime_enabled=True, assistant_model_factory=forbidden_runtime_factory,
    )
    with TestClient(app) as client:
        login = client.post(
            "/api/auth/login", headers={"Origin": ORIGIN},
            json={"actor_id": "support-a", "password": PASSWORDS["support-a"]},
        )
        headers = {"Origin": ORIGIN, "X-CSRF-Token": login.json()["csrf_token"]}
        session_id = client.post("/api/sessions", headers=headers).json()["session_id"]
        accepted = client.post(
            f"/api/sessions/{session_id}/assistant/messages",
            headers={**headers, "Idempotency-Key": "hf01-runtime-no-fallback"},
            json={"body": "Use the regular Assistant path."},
        )
        assert accepted.status_code == 202
        assert _wait_run(client, accepted.json()["run_id"])["status"] == "FAILED"

    assert factory_calls == []
    assert requests == []
    with connect(demo_db) as connection:
        assert connection.execute("SELECT COUNT(*) FROM assistant_runtime_spends").fetchone()[0] == 0


def test_explicit_legacy_provider_authorization_preserves_old_readonly_chat(
    demo_db, tmp_path, monkeypatch,
):
    from fastapi.testclient import TestClient
    from opspilot.domain.database import connect
    from opspilot.web.app import create_app
    from test_ar02_assistant import ORIGIN, PASSWORDS
    from test_ar02_journey_p0 import _wait_run
    from test_product_01_runtime_grant_01 import _configure, _provision

    _configure(monkeypatch)
    _env(monkeypatch, legacy=True)
    _provision(demo_db)
    requests = []
    _mock_legacy_chat(monkeypatch, requests)
    app = create_app(
        db_path=demo_db, checkpoint_db_path=tmp_path / "authorized-legacy-checkpoint.sqlite3",
        start_worker=True, credentials=PASSWORDS, expected_origin=ORIGIN,
        assistant_runtime_enabled=True,
    )
    with TestClient(app) as client:
        login = client.post(
            "/api/auth/login", headers={"Origin": ORIGIN},
            json={"actor_id": "support-a", "password": PASSWORDS["support-a"]},
        )
        headers = {"Origin": ORIGIN, "X-CSRF-Token": login.json()["csrf_token"]}
        session_id = client.post("/api/sessions", headers=headers).json()["session_id"]
        accepted = client.post(
            f"/api/sessions/{session_id}/messages",
            headers={**headers, "Idempotency-Key": "hf01-authorized-legacy-message"},
            json={"input_kind": "CHAT_READONLY", "body": "Explain this API failure."},
        )
        assert accepted.status_code == 202
        assert _wait_run(client, accepted.json()["run_id"])["status"] == "SUCCEEDED"

    assert len(requests) == 1
    assert requests[0]["url"] == "https://api.deepseek.com/chat/completions"
    with connect(demo_db) as connection:
        assert connection.execute("SELECT COUNT(*) FROM chat_attempts WHERE status='SUCCEEDED'").fetchone()[0] == 1


def _resume_evidence(key):
    return {
        "expected_version": key["version"],
        "operator_id": "offline-recovery-operator",
        "source": "LOCAL_OPERATOR_RECOVERY",
        "evidence_ref": "offline local config and ledger verification",
        "evidence_digest": "b" * 64,
        "idempotency_key": key["idempotency_key"],
    }


def test_pool_resume_requires_fixed_config_and_is_audited_idempotently(
    demo_db, monkeypatch,
):
    from opspilot.domain.assistant_runtime_grant import (
        RuntimeGrantError, bind_run, resume_spend_pool, runtime_config_from_env,
        spend_summary,
    )
    from opspilot.domain.database import connect
    from test_product_01_runtime_grant_01 import _configure, _provision, _run, _worker, _call

    _configure(monkeypatch)
    _env(monkeypatch)
    _provision(demo_db, total=100_000)
    run = _run(demo_db, "resume-after-stale-config")
    monkeypatch.setenv("OPSPILOT_MODEL_PRICE_VERSION", "stale-price-version")
    with pytest.raises(RuntimeGrantError, match="RUNTIME_PROVIDER_CONFIGURATION_STALE"):
        bind_run(demo_db, run["run_id"], runtime_config_from_env())
    paused = spend_summary(demo_db)
    assert paused["status"] == "PAUSED"
    evidence = _resume_evidence({"version": 2, "idempotency_key": "hf01-resume-after-stale"})

    with pytest.raises(RuntimeGrantError, match="RUNTIME_PROVIDER_CONFIGURATION_STALE"):
        resume_spend_pool(demo_db, **evidence)
    assert spend_summary(demo_db)["status"] == "PAUSED"

    monkeypatch.setenv("OPSPILOT_MODEL_PRICE_VERSION", "offline-price-v1")
    resumed = resume_spend_pool(demo_db, **evidence)
    assert resumed["status"] == "ACTIVE"
    assert resumed["version"] == 3
    assert resumed["replay"] is False
    replayed = resume_spend_pool(demo_db, **evidence)
    assert replayed["replay"] is True
    assert replayed["version"] == 3
    with pytest.raises(RuntimeGrantError, match="RUNTIME_AUDIT_IDEMPOTENCY_CONFLICT"):
        resume_spend_pool(demo_db, **{**evidence, "evidence_ref": "different recovery evidence"})

    with connect(demo_db) as connection:
        audit = connection.execute(
            "SELECT action,details_json FROM assistant_runtime_audit WHERE idempotency_key=?",
            (evidence["idempotency_key"],),
        ).fetchone()
        assert audit["action"] == "RESUME_POOL"
        assert connection.execute(
            "SELECT COUNT(*) FROM assistant_runtime_audit WHERE action='RESUME_POOL'"
        ).fetchone()[0] == 1

    worker = _worker(demo_db)
    try:
        next_run = _run(demo_db, "resume-normal-call", worker_id=worker.owner_id)
        binding = bind_run(demo_db, next_run["run_id"], runtime_config_from_env())
        _, dispatch, _ = _call(demo_db, next_run, worker.owner_id, binding)
        assert dispatch["status"] == "RESERVED"
    finally:
        worker.release()


@pytest.mark.parametrize("pool_total,can_resume", [(40_000, True), (14_048, False)])
def test_pool_resume_preserves_unknown_reservation_and_revalidates_balance(
    demo_db, monkeypatch, pool_total, can_resume,
):
    from opspilot.domain.assistant_runtime_grant import (
        RuntimeGrantError, bind_run, claim_send, mark_unknown, resume_spend_pool,
        runtime_config_from_env, spend_summary, validate_http_request,
    )
    from opspilot.domain.database import connect
    from opspilot.domain.d2 import digest_json
    from test_product_01_runtime_grant_01 import (
        _configure, _provision, _run, _worker, _call,
    )

    _configure(monkeypatch)
    _env(monkeypatch)
    _provision(demo_db, total=pool_total)
    worker = _worker(demo_db)
    try:
        run = _run(demo_db, "unknown-before-resume", worker_id=worker.owner_id)
        binding = bind_run(demo_db, run["run_id"], runtime_config_from_env())
        call, dispatch, request = _call(demo_db, run, worker.owner_id, binding)
        wire = json.dumps({
            "model": "deepseek-flash", "messages": [{"role": "user", "content": "hello"}],
            "max_tokens": 2048, "thinking": {"type": "disabled"}, "stream": False,
        }, separators=(",", ":")).encode()
        body_digest, output_cap = validate_http_request(
            "https://api.deepseek.com/chat/completions", "POST", wire, binding,
        )
        claim_send(
            demo_db, binding, call_id=call["call_id"], request_key=dispatch["request_key"],
            request_digest=digest_json(request), body_digest=body_digest,
            request_url="https://api.deepseek.com/chat/completions", method="POST",
            requested_max_output_tokens=output_cap, worker_id=worker.owner_id, worker_epoch=worker.epoch,
        )
        mark_unknown(demo_db, dispatch["request_key"], "offline-unknown-fixture")

        monkeypatch.setenv("OPSPILOT_MODEL_PRICE_VERSION", "stale-price-version")
        failed_run = _run(demo_db, "pause-for-stale-config")
        with pytest.raises(RuntimeGrantError, match="RUNTIME_PROVIDER_CONFIGURATION_STALE"):
            bind_run(demo_db, failed_run["run_id"], runtime_config_from_env())
        paused = spend_summary(demo_db)
        assert paused["committed_or_reserved_usd_micro"] == dispatch["reserved_usd_micro"]
        evidence = _resume_evidence({"version": 2, "idempotency_key": "hf01-resume-unknown"})
        monkeypatch.setenv("OPSPILOT_MODEL_PRICE_VERSION", "offline-price-v1")
        if can_resume:
            resumed = resume_spend_pool(demo_db, **evidence)
            assert resumed["status"] == "ACTIVE"
            assert resumed["unknown_count"] == 1
            assert resumed["unknown_reserved_usd_micro"] == dispatch["reserved_usd_micro"]
        else:
            with pytest.raises(RuntimeGrantError, match="RUNTIME_POOL_REMAINING_BUDGET_UNAVAILABLE"):
                resume_spend_pool(demo_db, **evidence)

        with connect(demo_db) as connection:
            row = connection.execute(
                "SELECT status,reserved_usd_micro FROM assistant_runtime_spends WHERE request_key=?",
                (dispatch["request_key"],),
            ).fetchone()
            assert row["status"] == "UNKNOWN"
            assert row["reserved_usd_micro"] == dispatch["reserved_usd_micro"]
        assert spend_summary(demo_db)["committed_or_reserved_usd_micro"] == dispatch["reserved_usd_micro"]
        if can_resume:
            next_run = _run(demo_db, "after-unknown-resume", worker_id=worker.owner_id)
            next_binding = bind_run(demo_db, next_run["run_id"], runtime_config_from_env())
            _, next_dispatch, _ = _call(demo_db, next_run, worker.owner_id, next_binding)
            assert next_dispatch["status"] == "RESERVED"
            assert spend_summary(demo_db)["committed_or_reserved_usd_micro"] == (
                dispatch["reserved_usd_micro"] + next_dispatch["reserved_usd_micro"]
            )
        else:
            assert spend_summary(demo_db)["status"] == "PAUSED"
    finally:
        worker.release()


def test_pool_resume_refuses_usage_bound_violation(demo_db, monkeypatch):
    from opspilot.domain.assistant_runtime_grant import (
        RuntimeGrantError, bind_run, claim_send, resume_spend_pool, runtime_config_from_env,
        spend_summary, store_response, validate_http_request,
    )
    from opspilot.domain.database import connect
    from opspilot.domain.d2 import digest_json
    from test_product_01_runtime_grant_01 import _configure, _provision, _run, _worker, _call

    _configure(monkeypatch)
    _env(monkeypatch)
    _provision(demo_db, total=50_000)
    worker = _worker(demo_db)
    try:
        run = _run(demo_db, "usage-bound-violation", worker_id=worker.owner_id)
        binding = bind_run(demo_db, run["run_id"], runtime_config_from_env())
        call, dispatch, request = _call(demo_db, run, worker.owner_id, binding)
        wire = b'{"model":"deepseek-flash","messages":[{"role":"user","content":"hello"}],"max_tokens":2048,"thinking":{"type":"disabled"},"stream":false}'
        body_digest, output_cap = validate_http_request(
            "https://api.deepseek.com/chat/completions", "POST", wire, binding,
        )
        claim_send(
            demo_db, binding, call_id=call["call_id"], request_key=dispatch["request_key"],
            request_digest=digest_json(request), body_digest=body_digest,
            request_url="https://api.deepseek.com/chat/completions", method="POST",
            requested_max_output_tokens=output_cap, worker_id=worker.owner_id, worker_epoch=worker.epoch,
        )
        body = json.dumps({
            "id": "offline-bound-violation",
            "usage": {"prompt_tokens": 1, "completion_tokens": output_cap + 1,
                      "total_tokens": output_cap + 2},
            "choices": [{"message": {"role": "assistant", "content": "undeliverable"},
                         "finish_reason": "stop"}],
        }).encode()
        result = store_response(
            demo_db, dispatch["request_key"], status_code=200,
            headers={"content-type": "application/json"}, body=body,
            usage={"prompt_tokens": 1, "completion_tokens": output_cap + 1,
                   "total_tokens": output_cap + 2},
        )
        assert result["usage_state"] == "VIOLATION"
        summary = spend_summary(demo_db)
        with connect(demo_db) as connection:
            pool_version = connection.execute(
                "SELECT version FROM assistant_runtime_pools WHERE pool_id='DEFAULT'"
            ).fetchone()[0]
        evidence = _resume_evidence({"version": pool_version,
                                     "idempotency_key": "hf01-do-not-resume-violation"})
        with pytest.raises(RuntimeGrantError, match="RUNTIME_POOL_PAUSE_NOT_RESUMABLE"):
            resume_spend_pool(demo_db, **evidence)
        assert spend_summary(demo_db)["status"] == "PAUSED"
    finally:
        worker.release()
