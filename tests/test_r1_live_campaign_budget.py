from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from threading import Barrier

import httpx
import pytest

from opspilot.domain.assistant_runtime_grant import (
    R1_LIVE_JOURNEY_INPUT_RATE_MICRO_PER_MILLION,
    R1_LIVE_JOURNEY_OUTPUT_RATE_MICRO_PER_MILLION,
    R1_LIVE_JOURNEY_PRICE_VERSION,
    R1_LIVE_JOURNEY_PER_REQUEST_RESERVE_USD_MICRO,
    R1_J2_LIVE_RECHECK_APPLICATION_BUDGET_USD_MICRO,
    R1_J2_LIVE_RECHECK_CAMPAIGN_ID,
    R1_J2_LIVE_RECHECK_PROVIDER_LIMIT,
    R1_J2_LIVE_RECHECK_02_APPLICATION_BUDGET_USD_MICRO,
    R1_J2_LIVE_RECHECK_02_CAMPAIGN_ID,
    R1_J2_LIVE_RECHECK_02_PROVIDER_LIMIT,
    RuntimeGrantError,
    bind_run,
    claim_send,
    close_unfinished_dispatch,
    mark_delivered,
    mark_unknown,
    provision_default_grant,
    r1_live_journey_campaign_policy,
    r1_live_journey_02_campaign_policy,
    r1_j2_live_recheck_campaign_policy,
    r1_j2_live_recheck_02_campaign_policy,
    reserve_dispatch,
    runtime_config_from_env,
    spend_summary,
    store_response,
    validate_http_request,
)
from opspilot.domain.assistant import reserve as reserve_assistant_call
from opspilot.domain.d2 import digest_json
from opspilot.domain.database import connect
from opspilot.web.worker import SingleInstanceWorker
from test_ar02_assistant import ORIGIN, PASSWORDS
from test_ar02_journey_p0 import _wait_run
from test_product_01_runtime_grant_01 import _configure, _run


def _provision_campaign(
    db_path, monkeypatch, *, pool_limit=11_000_000,
    idempotency_key="r1-live-journey-01-campaign-provision-v1",
    campaign_policy=None,
):
    _configure(monkeypatch)
    monkeypatch.setenv("OPSPILOT_MODEL_CONFIG_VERSION", "r1-live-config-v1")
    monkeypatch.setenv("OPSPILOT_MODEL_PRICE_VERSION", R1_LIVE_JOURNEY_PRICE_VERSION)
    now = datetime.now(timezone.utc)
    return provision_default_grant(
        db_path,
        grant_source="R1-LIVE-JOURNEY-01 user authorization",
        operator_id="local-campaign-operator",
        service_identity="offline-test-service",
        model_id="deepseek-flash",
        endpoint="https://api.deepseek.com",
        model_config_version="r1-live-config-v1",
        price_version=R1_LIVE_JOURNEY_PRICE_VERSION,
        input_rate_micro_per_million=R1_LIVE_JOURNEY_INPUT_RATE_MICRO_PER_MILLION,
        output_rate_micro_per_million=R1_LIVE_JOURNEY_OUTPUT_RATE_MICRO_PER_MILLION,
        max_input_tokens=12_000,
        max_output_tokens=2_048,
        total_limit_usd_micro=pool_limit,
        valid_from=(now - timedelta(minutes=1)).isoformat().replace("+00:00", "Z"),
        expires_at=(now + timedelta(hours=2)).isoformat().replace("+00:00", "Z"),
        evidence_ref="docs/evidence/vnext/r1-live-journey-01/CASES.json",
        evidence_digest="a668240be2f816e66b39557daab5e58937f264fb258525d04765baf75974bf63",
        idempotency_key=idempotency_key,
        campaign_policy=campaign_policy or r1_live_journey_campaign_policy(),
    )


def _worker(db_path):
    worker = SingleInstanceWorker(db_path)
    worker.acquire()
    worker.register()
    return worker


def _reserved_call(db_path, worker_id, ordinal):
    run = _run(db_path, f"r1-live-call-{ordinal}", worker_id=worker_id)
    binding = bind_run(db_path, run["run_id"], runtime_config_from_env())
    request = {
        "model_id": "deepseek-flash",
        "messages": [{"role": "user", "content": f"campaign request {ordinal}"}],
    }
    call, fresh = reserve_assistant_call(
        db_path, run["run_id"], "MODEL", f"answer:{ordinal}", request, worker_id,
        runtime_recovery=True,
    )
    assert fresh
    dispatch = reserve_dispatch(
        db_path, binding, call_id=call["call_id"], logical_key=call["logical_key"],
        request_digest=call["request_digest"], worker_id=worker_id,
    )
    body = json.dumps({
        "model": "deepseek-flash",
        "messages": [{"role": "user", "content": f"campaign request {ordinal}"}],
        "max_tokens": 2_048,
        "thinking": {"type": "disabled"},
        "stream": False,
    }, separators=(",", ":")).encode()
    body_digest, output_cap = validate_http_request(
        "https://api.deepseek.com/chat/completions", "POST", body, binding,
    )
    return run, binding, call, dispatch, call["request_digest"], body_digest, output_cap


def _send(db_path, worker_id, worker_epoch, prepared):
    _, binding, call, dispatch, request_digest, body_digest, output_cap = prepared
    return claim_send(
        db_path, binding, call_id=call["call_id"], request_key=dispatch["request_key"],
        request_digest=request_digest, body_digest=body_digest,
        request_url="https://api.deepseek.com/chat/completions", method="POST",
        requested_max_output_tokens=output_cap, worker_id=worker_id,
        worker_epoch=worker_epoch,
    )


def _campaign_row(db_path):
    with connect(db_path) as connection:
        return dict(connection.execute(
            "SELECT * FROM assistant_runtime_campaigns WHERE pool_id='DEFAULT'"
        ).fetchone())


def _complete_known_response(db_path, prepared):
    request_key = prepared[3]["request_key"]
    response_body = json.dumps({"id": "offline-completion", "choices": []}).encode()
    stored = store_response(
        db_path, request_key, status_code=200, headers={}, body=response_body,
        usage={"prompt_tokens": 10, "completion_tokens": 10, "total_tokens": 20},
    )
    assert stored["usage_state"] == "KNOWN"
    mark_delivered(db_path, request_key)


def test_campaign_allows_sixteenth_send_and_persistently_rejects_seventeenth_after_worker_restart(
    demo_db, monkeypatch,
):
    _provision_campaign(demo_db, monkeypatch)
    worker = _worker(demo_db)
    try:
        for ordinal in range(1, 9):
            prepared = _reserved_call(demo_db, worker.owner_id, ordinal)
            assert prepared[3]["reserved_usd_micro"] == R1_LIVE_JOURNEY_PER_REQUEST_RESERVE_USD_MICRO
            assert _send(demo_db, worker.owner_id, worker.epoch, prepared)["action"] == "SEND"
            _complete_known_response(demo_db, prepared)
        worker.release()

        # Reopening the same isolated Domain DB and starting a new Worker cannot reset the cap.
        worker = _worker(demo_db)
        for ordinal in range(9, 17):
            prepared = _reserved_call(demo_db, worker.owner_id, ordinal)
            assert _send(demo_db, worker.owner_id, worker.epoch, prepared)["action"] == "SEND"
            _complete_known_response(demo_db, prepared)

        campaign = _campaign_row(demo_db)
        assert campaign["provider_limit"] == 16
        assert campaign["provider_sends_granted"] == 16
        assert campaign["application_budget_usd_micro"] == 11_000_000
        assert campaign["per_request_reserve_usd_micro"] == 645_600
        assert spend_summary(demo_db)["committed_or_reserved_usd_micro"] == 16 * 15

        with pytest.raises(RuntimeGrantError, match="RUNTIME_DEFAULT_GRANT_ALREADY_PROVISIONED"):
            _provision_campaign(
                demo_db, monkeypatch, idempotency_key="attempt-second-campaign-grant",
            )
        assert _campaign_row(demo_db)["provider_sends_granted"] == 16

        run = _run(demo_db, "r1-live-call-17", worker_id=worker.owner_id)
        binding = bind_run(demo_db, run["run_id"], runtime_config_from_env())
        request = {"model_id": "deepseek-flash", "messages": [{"role": "user", "content": "17th"}]}
        call, fresh = reserve_assistant_call(
            demo_db, run["run_id"], "MODEL", "answer:17", request, worker.owner_id,
            runtime_recovery=True,
        )
        assert fresh
        with pytest.raises(RuntimeGrantError, match="RUNTIME_CAMPAIGN_PROVIDER_LIMIT"):
            reserve_dispatch(
                demo_db, binding, call_id=call["call_id"], logical_key=call["logical_key"],
                request_digest=call["request_digest"], worker_id=worker.owner_id,
            )
        assert _campaign_row(demo_db)["provider_sends_granted"] == 16
    finally:
        worker.release()


def test_r1_live_journey_02_campaign_uses_its_frozen_12_send_and_8_usd_limits(
    demo_db, monkeypatch,
):
    policy = r1_live_journey_02_campaign_policy()
    assert policy["campaign_id"] == "R1-LIVE-JOURNEY-02"
    assert policy["provider_limit"] == 12
    assert policy["application_budget_usd_micro"] == 8_000_000
    assert policy["per_request_reserve_usd_micro"] == R1_LIVE_JOURNEY_PER_REQUEST_RESERVE_USD_MICRO
    for field, value in (
        ("provider_limit", 13),
        ("application_budget_usd_micro", 8_500_000),
        ("per_request_reserve_usd_micro", 600_000),
    ):
        with pytest.raises(RuntimeGrantError, match="RUNTIME_CAMPAIGN_POLICY_INVALID"):
            _provision_campaign(
                demo_db, monkeypatch, campaign_policy={**policy, field: value},
                pool_limit=8_000_000,
            )
    _provision_campaign(
        demo_db, monkeypatch, campaign_policy=policy, pool_limit=8_000_000,
        idempotency_key="r1-live-journey-02-campaign-provision-v1",
    )
    worker = _worker(demo_db)
    try:
        for ordinal in range(1, 13):
            prepared = _reserved_call(demo_db, worker.owner_id, ordinal)
            assert prepared[3]["reserved_usd_micro"] == R1_LIVE_JOURNEY_PER_REQUEST_RESERVE_USD_MICRO
            assert _send(demo_db, worker.owner_id, worker.epoch, prepared)["action"] == "SEND"
            _complete_known_response(demo_db, prepared)
        worker.release()

        worker = _worker(demo_db)
        campaign = _campaign_row(demo_db)
        assert campaign["campaign_id"] == "R1-LIVE-JOURNEY-02"
        assert campaign["provider_sends_granted"] == 12
        assert campaign["application_budget_usd_micro"] == 8_000_000

        run = _run(demo_db, "r1-live-journey-02-call-13", worker_id=worker.owner_id)
        binding = bind_run(demo_db, run["run_id"], runtime_config_from_env())
        request = {"model_id": "deepseek-flash", "messages": [{"role": "user", "content": "13th"}]}
        call, fresh = reserve_assistant_call(
            demo_db, run["run_id"], "MODEL", "answer:13", request, worker.owner_id,
            runtime_recovery=True,
        )
        assert fresh
        with pytest.raises(RuntimeGrantError, match="RUNTIME_CAMPAIGN_PROVIDER_LIMIT"):
            reserve_dispatch(
                demo_db, binding, call_id=call["call_id"], logical_key=call["logical_key"],
                request_digest=call["request_digest"], worker_id=worker.owner_id,
            )
        assert _campaign_row(demo_db)["provider_sends_granted"] == 12
    finally:
        worker.release()


def test_r1_j2_live_recheck_campaign_is_separate_and_enforces_its_own_12_send_cap(
    demo_db, monkeypatch,
):
    policy = r1_j2_live_recheck_campaign_policy()
    assert policy == {
        "campaign_id": R1_J2_LIVE_RECHECK_CAMPAIGN_ID,
        "provider_model_version": "DeepSeek-V4.1-Flash-1017",
        "public_context_tokens": 1_000_000,
        "public_max_output_tokens": 384_000,
        "provider_limit": R1_J2_LIVE_RECHECK_PROVIDER_LIMIT,
        "per_request_reserve_usd_micro": R1_LIVE_JOURNEY_PER_REQUEST_RESERVE_USD_MICRO,
        "application_budget_usd_micro": R1_J2_LIVE_RECHECK_APPLICATION_BUDGET_USD_MICRO,
    }
    assert R1_J2_LIVE_RECHECK_PROVIDER_LIMIT == 12
    assert R1_J2_LIVE_RECHECK_APPLICATION_BUDGET_USD_MICRO == 8_000_000
    # The exact authorized configuration is required. An unapproved campaign
    # identity or inflated limit cannot be substituted for this policy.
    with pytest.raises(RuntimeGrantError, match="RUNTIME_CAMPAIGN_POLICY_INVALID"):
        _provision_campaign(
            demo_db, monkeypatch,
            campaign_policy={**policy, "campaign_id": "R1-J2-LIVE-RECHECK-03"},
            pool_limit=8_000_000,
            idempotency_key="r1-j2-live-recheck-invalid-new-id",
        )
    with pytest.raises(RuntimeGrantError, match="RUNTIME_CAMPAIGN_POLICY_INVALID"):
        _provision_campaign(
            demo_db, monkeypatch,
            campaign_policy={**policy, "provider_limit": 13},
            pool_limit=8_000_000,
            idempotency_key="r1-j2-live-recheck-invalid-limit",
        )

    _provision_campaign(
        demo_db, monkeypatch, campaign_policy=policy, pool_limit=8_000_000,
        idempotency_key="r1-j2-live-recheck-campaign-provision-v1",
    )
    worker = _worker(demo_db)
    try:
        for ordinal in range(1, 13):
            prepared = _reserved_call(demo_db, worker.owner_id, ordinal)
            assert prepared[3]["reserved_usd_micro"] == 645_600
            assert _send(demo_db, worker.owner_id, worker.epoch, prepared)["action"] == "SEND"
            _complete_known_response(demo_db, prepared)
        worker.release()
        worker = _worker(demo_db)
        campaign = _campaign_row(demo_db)
        assert campaign["campaign_id"] == R1_J2_LIVE_RECHECK_CAMPAIGN_ID
        assert campaign["provider_limit"] == 12
        assert campaign["provider_sends_granted"] == 12
        assert campaign["application_budget_usd_micro"] == 8_000_000

        run = _run(demo_db, "r1-j2-live-recheck-call-13", worker_id=worker.owner_id)
        binding = bind_run(demo_db, run["run_id"], runtime_config_from_env())
        request = {"model_id": "deepseek-flash", "messages": [{"role": "user", "content": "13th"}]}
        call, fresh = reserve_assistant_call(
            demo_db, run["run_id"], "MODEL", "answer:13", request, worker.owner_id,
            runtime_recovery=True,
        )
        assert fresh
        with pytest.raises(RuntimeGrantError, match="RUNTIME_CAMPAIGN_PROVIDER_LIMIT"):
            reserve_dispatch(
                demo_db, binding, call_id=call["call_id"], logical_key=call["logical_key"],
                request_digest=call["request_digest"], worker_id=worker.owner_id,
            )
        assert _campaign_row(demo_db)["provider_sends_granted"] == 12
    finally:
        worker.release()


@pytest.mark.parametrize(
    ("policy_factory", "campaign_id", "provider_limit", "application_budget"),
    [
        (r1_j2_live_recheck_campaign_policy, R1_J2_LIVE_RECHECK_CAMPAIGN_ID,
         R1_J2_LIVE_RECHECK_PROVIDER_LIMIT, R1_J2_LIVE_RECHECK_APPLICATION_BUDGET_USD_MICRO),
        (r1_j2_live_recheck_02_campaign_policy, R1_J2_LIVE_RECHECK_02_CAMPAIGN_ID,
         R1_J2_LIVE_RECHECK_02_PROVIDER_LIMIT,
         R1_J2_LIVE_RECHECK_02_APPLICATION_BUDGET_USD_MICRO),
    ],
    ids=["recheck-01", "recheck-02"],
)
def test_r1_j2_live_recheck_campaign_policy_has_an_independent_12_send_cap(
    demo_db, monkeypatch, policy_factory, campaign_id, provider_limit, application_budget,
):
    policy = policy_factory()
    assert policy == {
        "campaign_id": campaign_id,
        "provider_model_version": "DeepSeek-V4.1-Flash-1017",
        "public_context_tokens": 1_000_000,
        "public_max_output_tokens": 384_000,
        "provider_limit": provider_limit,
        "per_request_reserve_usd_micro": 645_600,
        "application_budget_usd_micro": application_budget,
    }
    assert provider_limit == 12
    assert application_budget == 8_000_000
    _provision_campaign(
        demo_db, monkeypatch, campaign_policy=policy, pool_limit=application_budget,
        idempotency_key=f"{campaign_id}-independent-policy-v1",
    )
    worker = _worker(demo_db)
    try:
        for ordinal in range(1, provider_limit + 1):
            prepared = _reserved_call(demo_db, worker.owner_id, ordinal)
            assert prepared[3]["reserved_usd_micro"] == 645_600
            assert _send(demo_db, worker.owner_id, worker.epoch, prepared)["action"] == "SEND"
            _complete_known_response(demo_db, prepared)
        campaign = _campaign_row(demo_db)
        assert campaign["campaign_id"] == campaign_id
        assert campaign["provider_sends_granted"] == provider_limit
        assert campaign["application_budget_usd_micro"] == application_budget
    finally:
        worker.release()


@pytest.mark.parametrize(
    ("campaign_policy", "pool_limit", "provider_limit"),
    [
        (r1_live_journey_campaign_policy(), 11_000_000, 16),
        (r1_live_journey_02_campaign_policy(), 8_000_000, 12),
        (r1_j2_live_recheck_campaign_policy(), 8_000_000, 12),
        (r1_j2_live_recheck_02_campaign_policy(), 8_000_000, 12),
    ],
    ids=["r1-live-01", "r1-live-02", "r1-j2-recheck-01", "r1-j2-recheck-02"],
)
def test_campaign_concurrent_final_slot_is_consumed_atomically(
    demo_db, monkeypatch, campaign_policy, pool_limit, provider_limit,
):
    _provision_campaign(
        demo_db, monkeypatch, campaign_policy=campaign_policy, pool_limit=pool_limit,
        idempotency_key=f"{campaign_policy['campaign_id']}-concurrency-provision",
    )
    worker = _worker(demo_db)
    try:
        for ordinal in range(1, provider_limit):
            prepared = _reserved_call(demo_db, worker.owner_id, ordinal)
            _send(demo_db, worker.owner_id, worker.epoch, prepared)
            _complete_known_response(demo_db, prepared)

        candidate_a = _reserved_call(demo_db, worker.owner_id, provider_limit)
        candidate_b = _reserved_call(demo_db, worker.owner_id, provider_limit + 1)
        barrier = Barrier(2)

        def compete(prepared):
            barrier.wait(timeout=5)
            try:
                return _send(demo_db, worker.owner_id, worker.epoch, prepared)["action"]
            except RuntimeGrantError as error:
                return error.code

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(compete, (candidate_a, candidate_b)))

        assert results.count("SEND") == 1
        assert sum(result != "SEND" for result in results) == 1
        assert _campaign_row(demo_db)["provider_sends_granted"] == provider_limit
        assert _campaign_row(demo_db)["provider_sends_granted"] == provider_limit - 1 + results.count("SEND")
        for prepared in (candidate_a, candidate_b):
            close_unfinished_dispatch(demo_db, prepared[3]["request_key"], "concurrency-loser")
        assert _campaign_row(demo_db)["provider_sends_granted"] == provider_limit
    finally:
        worker.release()


def test_campaign_uses_public_capacity_reserve_and_refuses_when_pool_budget_is_exhausted(
    demo_db, monkeypatch,
):
    _provision_campaign(
        demo_db, monkeypatch, pool_limit=645_600,
        campaign_policy=r1_j2_live_recheck_campaign_policy(),
        idempotency_key="r1-j2-live-recheck-budget-exhaustion",
    )
    worker = _worker(demo_db)
    try:
        prepared = _reserved_call(demo_db, worker.owner_id, 1)
        assert prepared[3]["reserved_usd_micro"] == 645_600

        run = _run(demo_db, "r1-live-budget-exhausted", worker_id=worker.owner_id)
        binding = bind_run(demo_db, run["run_id"], runtime_config_from_env())
        request = {"model_id": "deepseek-flash", "messages": [{"role": "user", "content": "next"}]}
        call, fresh = reserve_assistant_call(
            demo_db, run["run_id"], "MODEL", "answer:next", request, worker.owner_id,
            runtime_recovery=True,
        )
        assert fresh
        with pytest.raises(RuntimeGrantError, match="RUNTIME_BUDGET_EXHAUSTED"):
            reserve_dispatch(
                demo_db, binding, call_id=call["call_id"], logical_key=call["logical_key"],
                request_digest=call["request_digest"], worker_id=worker.owner_id,
            )
        assert _campaign_row(demo_db)["provider_sends_granted"] == 0
        assert spend_summary(demo_db)["committed_or_reserved_usd_micro"] == 645_600
    finally:
        worker.release()


@pytest.mark.parametrize(
    ("campaign_policy", "pool_limit"),
    [
        (r1_live_journey_campaign_policy(), 11_000_000),
        (r1_live_journey_02_campaign_policy(), 8_000_000),
        (r1_j2_live_recheck_campaign_policy(), 8_000_000),
        (r1_j2_live_recheck_02_campaign_policy(), 8_000_000),
    ],
    ids=["r1-live-01", "r1-live-02", "r1-j2-recheck-01", "r1-j2-recheck-02"],
)
@pytest.mark.parametrize("unknown_transition", ["mark", "close", "worker_restart"])
def test_campaign_unknown_stops_future_sessions_and_preserves_reservation(
    demo_db, monkeypatch, campaign_policy, pool_limit, unknown_transition,
):
    _provision_campaign(
        demo_db, monkeypatch, campaign_policy=campaign_policy, pool_limit=pool_limit,
        idempotency_key=f"{campaign_policy['campaign_id']}-unknown-{unknown_transition}",
    )
    worker = _worker(demo_db)
    prepared = _reserved_call(demo_db, worker.owner_id, 1)
    assert _send(demo_db, worker.owner_id, worker.epoch, prepared)["action"] == "SEND"

    if unknown_transition == "mark":
        mark_unknown(demo_db, prepared[3]["request_key"], "SIMULATED_UNKNOWN")
    elif unknown_transition == "close":
        assert close_unfinished_dispatch(
            demo_db, prepared[3]["request_key"], "simulated-close-after-send",
        ) == "UNKNOWN"
    else:
        from opspilot.domain.assistant_runtime_grant import recover_interrupted_sends

        recovered = recover_interrupted_sends(demo_db, "replacement-worker")
        assert recovered == [prepared[3]["request_key"]]

    row = _campaign_row(demo_db)
    assert row["status"] == "STOPPED"
    assert row["provider_sends_granted"] == 1
    assert spend_summary(demo_db)["committed_or_reserved_usd_micro"] == R1_LIVE_JOURNEY_PER_REQUEST_RESERVE_USD_MICRO

    worker.release()
    restarted = _worker(demo_db)
    try:
        run = _run(demo_db, f"r1-live-after-unknown-{unknown_transition}", worker_id=restarted.owner_id)
        with pytest.raises(RuntimeGrantError, match="RUNTIME_CAMPAIGN_STOPPED"):
            bind_run(demo_db, run["run_id"], runtime_config_from_env())
        assert _campaign_row(demo_db)["provider_sends_granted"] == 1
        assert spend_summary(demo_db)["committed_or_reserved_usd_micro"] == R1_LIVE_JOURNEY_PER_REQUEST_RESERVE_USD_MICRO
    finally:
        restarted.release()


@pytest.mark.parametrize(
    ("campaign_policy", "pool_limit"),
    [
        (r1_live_journey_campaign_policy(), 11_000_000),
        (r1_live_journey_02_campaign_policy(), 8_000_000),
        (r1_j2_live_recheck_campaign_policy(), 8_000_000),
        (r1_j2_live_recheck_02_campaign_policy(), 8_000_000),
    ],
    ids=["r1-live-01", "r1-live-02", "r1-j2-recheck-01", "r1-j2-recheck-02"],
)
def test_campaign_missing_usage_response_stops_without_releasing_unknown_reserve(
    demo_db, monkeypatch, campaign_policy, pool_limit,
):
    _provision_campaign(
        demo_db, monkeypatch, campaign_policy=campaign_policy, pool_limit=pool_limit,
        idempotency_key=f"{campaign_policy['campaign_id']}-missing-usage",
    )
    worker = _worker(demo_db)
    try:
        prepared = _reserved_call(demo_db, worker.owner_id, 1)
        assert _send(demo_db, worker.owner_id, worker.epoch, prepared)["action"] == "SEND"
        result = store_response(
            demo_db, prepared[3]["request_key"], status_code=200, headers={},
            body=b'{"id":"offline-no-usage","choices":[]}', usage=None,
        )
        assert result["usage_state"] == "UNKNOWN"
        assert _campaign_row(demo_db)["status"] == "STOPPED"
        assert spend_summary(demo_db)["committed_or_reserved_usd_micro"] == R1_LIVE_JOURNEY_PER_REQUEST_RESERVE_USD_MICRO
        assert _campaign_row(demo_db)["provider_sends_granted"] == 1
    finally:
        worker.release()


@pytest.mark.parametrize(
    "campaign_policy",
    [
        r1_live_journey_campaign_policy(),
        r1_live_journey_02_campaign_policy(),
        r1_j2_live_recheck_campaign_policy(),
        r1_j2_live_recheck_02_campaign_policy(),
    ],
    ids=["r1-live-01", "r1-live-02", "r1-j2-recheck-01", "r1-j2-recheck-02"],
)
def test_campaign_known_provider_http_error_stops_future_sends(demo_db, monkeypatch, campaign_policy):
    _provision_campaign(
        demo_db, monkeypatch, pool_limit=int(campaign_policy["application_budget_usd_micro"]),
        campaign_policy=campaign_policy,
        idempotency_key=f"{campaign_policy['campaign_id']}-known-http-error",
    )
    worker = _worker(demo_db)
    try:
        prepared = _reserved_call(demo_db, worker.owner_id, 1)
        assert _send(demo_db, worker.owner_id, worker.epoch, prepared)["action"] == "SEND"
        result = store_response(
            demo_db, prepared[3]["request_key"], status_code=401, headers={},
            body=b'{"error":{"message":"redacted"}}',
            usage={"prompt_tokens": 1, "completion_tokens": 0, "total_tokens": 1},
        )
        assert result["usage_state"] == "KNOWN"
        assert _campaign_row(demo_db)["status"] == "STOPPED"
        assert _campaign_row(demo_db)["stop_reason"] == "PROVIDER_HTTP_ERROR"
        assert _campaign_row(demo_db)["provider_sends_granted"] == 1
    finally:
        worker.release()


@pytest.mark.parametrize(
    ("campaign_policy", "pool_limit"),
    [
        (r1_live_journey_campaign_policy(), 11_000_000),
        (r1_live_journey_02_campaign_policy(), 8_000_000),
        (r1_j2_live_recheck_campaign_policy(), 8_000_000),
        (r1_j2_live_recheck_02_campaign_policy(), 8_000_000),
    ],
    ids=["r1-live-01", "r1-live-02", "r1-j2-recheck-01", "r1-j2-recheck-02"],
)
@pytest.mark.parametrize("drift", ["price_version", "campaign_capacity"])
def test_campaign_rejects_price_or_capacity_drift_before_send(
    demo_db, monkeypatch, campaign_policy, pool_limit, drift,
):
    from opspilot.domain.database import initialize

    _provision_campaign(
        demo_db, monkeypatch, campaign_policy=campaign_policy, pool_limit=pool_limit,
        idempotency_key=f"{campaign_policy['campaign_id']}-drift-{drift}",
    )
    if drift == "price_version":
        monkeypatch.setenv("OPSPILOT_MODEL_PRICE_VERSION", "unexpected-rates")
    else:
        with connect(demo_db) as connection:
            connection.execute(
                "UPDATE assistant_runtime_campaigns SET public_max_output_tokens=383_999 "
                "WHERE campaign_id=?",
                (campaign_policy["campaign_id"],),
            )
        initialize(demo_db)

    run = _run(demo_db, f"campaign-drift-{drift}")
    if drift == "price_version":
        with pytest.raises(RuntimeGrantError, match="RUNTIME_PROVIDER_CONFIGURATION_STALE"):
            bind_run(demo_db, run["run_id"], runtime_config_from_env())
    else:
        with pytest.raises(RuntimeGrantError, match="RUNTIME_CAMPAIGN_CONFIGURATION_STALE"):
            bind_run(demo_db, run["run_id"], runtime_config_from_env())
    with connect(demo_db) as connection:
        assert connection.execute("SELECT COUNT(*) FROM assistant_runtime_spends").fetchone()[0] == 0
        assert connection.execute(
            "SELECT provider_sends_granted FROM assistant_runtime_campaigns"
        ).fetchone()[0] == 0


@pytest.mark.parametrize(
    ("campaign_policy", "idempotency_key"),
    [
        (r1_live_journey_campaign_policy(), "r1-live-journey-01-formal-worker-provision"),
        (r1_live_journey_02_campaign_policy(), "r1-live-journey-02-formal-worker-provision"),
        (r1_j2_live_recheck_campaign_policy(), "r1-j2-live-recheck-formal-worker-provision"),
        (r1_j2_live_recheck_02_campaign_policy(), "r1-j2-live-recheck-02-formal-worker-provision"),
    ],
    ids=["r1-live-01", "r1-live-02", "r1-j2-recheck-01", "r1-j2-recheck-02"],
)
def test_formal_worker_campaign_request_is_reserved_before_mock_transport_and_settled(
    demo_db, tmp_path, monkeypatch, campaign_policy, idempotency_key,
):
    from fastapi.testclient import TestClient
    from opspilot.assistant import create_assistant_model
    from opspilot.web.app import create_app

    _provision_campaign(
        demo_db, monkeypatch, campaign_policy=campaign_policy,
        pool_limit=int(campaign_policy["application_budget_usd_micro"]),
        idempotency_key=idempotency_key,
    )
    monkeypatch.setenv("OPSPILOT_ASSISTANT_RUNTIME_ENABLED", "1")
    monkeypatch.setenv("OPSPILOT_ASSISTANT_PROVIDER_ENABLED", "1")
    monkeypatch.setenv("OPSPILOT_MODEL_API_KEY", "test-only-not-a-real-key")
    monkeypatch.delenv("OPSPILOT_ASSISTANT_EXPERIMENT_ID", raising=False)
    observed = []

    async def respond(request):
        wire = json.loads((await request.aread()).decode("utf-8"))
        assert str(request.url) == "https://api.deepseek.com/chat/completions"
        assert wire["model"] == "deepseek-flash"
        assert wire["max_tokens"] == 2_048
        assert wire["thinking"] == {"type": "disabled"}
        assert wire["stream"] is False
        assert wire.get("tool_choice") == "auto"
        assert wire.get("parallel_tool_calls") is False
        with connect(demo_db) as connection:
            spend = connection.execute(
                "SELECT status,reserved_usd_micro,campaign_id FROM assistant_runtime_spends"
            ).fetchone()
            campaign = connection.execute(
                "SELECT provider_sends_granted FROM assistant_runtime_campaigns"
            ).fetchone()
        assert spend["status"] == "SEND_GRANTED"
        assert spend["reserved_usd_micro"] == 645_600
        assert spend["campaign_id"] == campaign_policy["campaign_id"]
        assert campaign["provider_sends_granted"] == 1
        observed.append(wire)
        return httpx.Response(200, headers={"x-request-id": "offline-campaign-request"}, json={
            "id": "offline-campaign-completion", "object": "chat.completion", "created": 1,
            "model": "deepseek-flash",
            "choices": [{"index": 0, "message": {"role": "assistant", "content":
                "HTTP 202 只表示已受理；没有当前 Receiver Observation 时，不能确认业务处理完成。"},
                "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 12, "completion_tokens": 24, "total_tokens": 36},
        })

    transports = {
        "transport_async": httpx.MockTransport(respond),
        "transport_sync": httpx.MockTransport(lambda request: httpx.Response(500, request=request)),
    }
    app = create_app(
        db_path=demo_db, checkpoint_db_path=tmp_path / "r1-live-campaign-checkpoint.sqlite3",
        start_worker=True, credentials=PASSWORDS, expected_origin=ORIGIN,
        assistant_model_factory=lambda *, runtime_grant_binding: create_assistant_model(
            runtime_grant_binding=runtime_grant_binding, **transports,
        ),
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
            f"/api/sessions/{session_id}/assistant/messages",
            headers={**headers, "Idempotency-Key": "r1-live-campaign-user-message"},
            json={"body": "HTTP 202 是否意味着回调已经处理完成？"},
        )
        assert accepted.status_code == 202, accepted.text
        run = _wait_run(client, accepted.json()["run_id"])
        assert run["status"] == "SUCCEEDED"
        messages = client.get(f"/api/sessions/{session_id}/messages").json()["items"]
        assert any(
            row["role"] == "ASSISTANT" and "不能确认业务处理完成" in row["body"]
            for row in messages
        )

    assert len(observed) == 1
    assert _campaign_row(demo_db)["provider_sends_granted"] == 1
    with connect(demo_db) as connection:
        spend = connection.execute("SELECT * FROM assistant_runtime_spends").fetchone()
        assert spend["status"] == "DELIVERED"
        assert spend["reserved_usd_micro"] == 645_600
        assert spend["settled_usd_micro"] == 33
        assert spend["completion_id"] == "offline-campaign-completion"
