"""Offline proof for the ordinary Assistant Runtime Grant and shared spend pool."""
from __future__ import annotations

import json
import shutil
from datetime import datetime, timedelta, timezone

import pytest


MODEL_CONFIG = {
    "OPSPILOT_MODEL_NAME": "deepseek-flash",
    "OPSPILOT_MODEL_BASE_URL": "https://api.deepseek.com",
    "OPSPILOT_MODEL_CONFIG_VERSION": "offline-model-config-v1",
    "OPSPILOT_MODEL_PRICE_VERSION": "offline-price-v1",
    "OPSPILOT_ASSISTANT_SERVICE_IDENTITY": "offline-test-service",
}


def _configure(monkeypatch):
    for key, value in MODEL_CONFIG.items():
        monkeypatch.setenv(key, value)


def _run(db_path, key, *, session_id=None, worker_id=None):
    from opspilot.domain.task_control import (
        admit_task_message, claim_task_run, create_session, trusted_identity,
    )

    actor = trusted_identity(db_path, "support-a")
    session = session_id or create_session(db_path, actor)["session_id"]
    admitted = admit_task_message(
        db_path, actor, session_id=session, task_id=None, input_kind="CHAT_READONLY",
        body="Offline Runtime Grant fixture " + key, idempotency_key="runtime-grant-" + key,
        assistant_core=True,
    )
    if worker_id:
        claim_task_run(db_path, actor, admitted["run_id"])
    return {**admitted, "session_id": session, "actor": actor}


def _provision(
    db_path, *, total=100_000, expires_delta=timedelta(days=1),
    input_rate=1_000_000, output_rate=1_000_000,
):
    from opspilot.domain.assistant_runtime_grant import provision_default_grant

    now = datetime.now(timezone.utc)
    return provision_default_grant(
        db_path, grant_source="offline isolated fixture", operator_id="test-local-operator",
        service_identity=MODEL_CONFIG["OPSPILOT_ASSISTANT_SERVICE_IDENTITY"],
        model_id=MODEL_CONFIG["OPSPILOT_MODEL_NAME"], endpoint=MODEL_CONFIG["OPSPILOT_MODEL_BASE_URL"],
        model_config_version=MODEL_CONFIG["OPSPILOT_MODEL_CONFIG_VERSION"],
        price_version=MODEL_CONFIG["OPSPILOT_MODEL_PRICE_VERSION"],
        input_rate_micro_per_million=input_rate, output_rate_micro_per_million=output_rate,
        max_input_tokens=12_000, max_output_tokens=2_048, total_limit_usd_micro=total,
        valid_from=(now - timedelta(days=2)).isoformat().replace("+00:00", "Z"),
        expires_at=(now + expires_delta).isoformat().replace("+00:00", "Z"),
        evidence_ref="offline task-card fixture", evidence_digest="a" * 64,
        idempotency_key="runtime-grant-provision-v1",
    )


def _worker(db_path):
    from opspilot.web.worker import SingleInstanceWorker

    worker = SingleInstanceWorker(db_path)
    worker.acquire()
    worker.register()
    return worker


def _call(db_path, run, worker_id, binding, logical_key="answer:one", payload=None):
    from opspilot.domain import assistant as assistant_domain
    from opspilot.domain.assistant_runtime_grant import reserve_dispatch
    from opspilot.domain.d2 import digest_json

    request = payload or {"model_id": "deepseek-flash", "messages": [{"role": "user", "content": "hello"}]}
    call, fresh = assistant_domain.reserve(
        db_path, run["run_id"], "MODEL", logical_key, request, worker_id,
        runtime_recovery=True,
    )
    assert fresh
    dispatch = reserve_dispatch(
        db_path, binding, call_id=call["call_id"], logical_key=logical_key,
        request_digest=digest_json(request), worker_id=worker_id,
    )
    return call, dispatch, request


def test_database_initialization_does_not_provision_or_enable_runtime_grant(demo_db, monkeypatch):
    from opspilot.domain.database import connect, initialize
    from opspilot.domain.assistant_runtime_grant import RuntimeGrantError, bind_run, runtime_config_from_env

    _configure(monkeypatch)
    run = _run(demo_db, "no-grant")
    initialize(demo_db)
    with connect(demo_db) as connection:
        assert connection.execute("SELECT COUNT(*) FROM assistant_runtime_authority").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM assistant_runtime_pools").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM assistant_runtime_default_grant").fetchone()[0] == 0
    with pytest.raises(RuntimeGrantError, match="RUNTIME_GRANT_NOT_PROVISIONED"):
        bind_run(demo_db, run["run_id"], runtime_config_from_env())


def test_grant_reservation_send_authority_usage_and_replay_are_persistent(demo_db, monkeypatch):
    from opspilot.domain.assistant_runtime_grant import (
        bind_run, claim_send, mark_delivered, provision_default_grant,
        reserve_dispatch, runtime_config_from_env, spend_summary, store_response,
        validate_http_request,
    )
    from opspilot.domain.database import connect
    from opspilot.domain.d2 import digest_json

    _configure(monkeypatch)
    _provision(demo_db, total=20_000)
    worker = _worker(demo_db)
    try:
        run = _run(demo_db, "settle", worker_id=worker.owner_id)
        binding = bind_run(demo_db, run["run_id"], runtime_config_from_env())
        call, dispatch, request = _call(demo_db, run, worker.owner_id, binding)
        assert dispatch["reserved_usd_micro"] == 14_048
        assert spend_summary(demo_db)["committed_or_reserved_usd_micro"] == 14_048
        assert spend_summary(demo_db)["status"] == "ACTIVE"

        wire = json.dumps({
            "model": "deepseek-flash", "messages": [{"role": "user", "content": "hello"}],
            "max_tokens": 2048, "thinking": {"type": "disabled"}, "stream": False,
        }, separators=(",", ":")).encode()
        body_digest, max_tokens = validate_http_request(
            "https://api.deepseek.com/chat/completions", "POST", wire, binding,
        )
        permit = claim_send(
            demo_db, binding, call_id=call["call_id"], request_key=dispatch["request_key"],
            request_digest=digest_json(request), body_digest=body_digest,
            request_url="https://api.deepseek.com/chat/completions", method="POST",
            requested_max_output_tokens=max_tokens, worker_id=worker.owner_id, worker_epoch=worker.epoch,
        )
        assert permit["action"] == "SEND"
        response_body = json.dumps({
            "id": "offline-completion-1", "model": "deepseek-flash",
            "usage": {"prompt_tokens": 3, "completion_tokens": 1, "total_tokens": 4},
            "choices": [{"message": {"role": "assistant", "content": "OK"}, "finish_reason": "stop"}],
        }).encode()
        stored = store_response(
            demo_db, dispatch["request_key"], status_code=200,
            headers={"content-type": "application/json", "x-request-id": "offline-req-1"},
            body=response_body,
            usage={"prompt_tokens": 3, "completion_tokens": 1, "total_tokens": 4},
        )
        assert stored["replayable"] is True
        assert spend_summary(demo_db)["committed_or_reserved_usd_micro"] == 4
        from opspilot.domain.assistant import finish, finish_runtime_replay, reserve
        from opspilot.domain.assistant_runtime_grant import RuntimeGrantError, mark_delivered
        finish(demo_db, call["call_id"], "UNKNOWN", {"error": "simulated crash after durable response"})
        recovered_call, fresh = reserve(
            demo_db, run["run_id"], "MODEL", "answer:one", request, worker.owner_id,
            runtime_recovery=True,
        )
        assert fresh is False and recovered_call["status"] == "UNKNOWN"
        recovered_dispatch = reserve_dispatch(
            demo_db, binding, call_id=call["call_id"], logical_key="answer:one",
            request_digest=digest_json(request), worker_id=worker.owner_id,
        )
        assert recovered_dispatch["replay"] is True
        with pytest.raises(RuntimeGrantError, match="RUNTIME_CALL_ID_MISMATCH"):
            claim_send(
                demo_db, binding, call_id="wrong-call-id", request_key=dispatch["request_key"],
                request_digest=digest_json(request), body_digest=body_digest,
                request_url="https://api.deepseek.com/chat/completions", method="POST",
                requested_max_output_tokens=max_tokens, worker_id=worker.owner_id, worker_epoch=worker.epoch,
            )
        unrelated_run = _run(demo_db, "unrelated-replay-run", worker_id=worker.owner_id)
        unrelated_binding = bind_run(demo_db, unrelated_run["run_id"], runtime_config_from_env())
        with pytest.raises(RuntimeGrantError, match="RUNTIME_CALL_BINDING_MISMATCH"):
            claim_send(
                demo_db, unrelated_binding, call_id=call["call_id"], request_key=dispatch["request_key"],
                request_digest=digest_json(request), body_digest=body_digest,
                request_url="https://api.deepseek.com/chat/completions", method="POST",
                requested_max_output_tokens=max_tokens, worker_id=worker.owner_id, worker_epoch=worker.epoch,
            )
        # The same logical request returns the saved wire response, never another send.
        replay = claim_send(
            demo_db, binding, call_id=call["call_id"], request_key=dispatch["request_key"],
            request_digest=digest_json(request), body_digest=body_digest,
            request_url="https://api.deepseek.com/chat/completions", method="POST",
            requested_max_output_tokens=max_tokens, worker_id=worker.owner_id, worker_epoch=worker.epoch,
        )
        assert replay == {
            "action": "REPLAY", "response_status": 200,
            "headers": {"content-type": "application/json", "x-request-id": "offline-req-1"},
            "body": response_body, "completion_id": "offline-completion-1",
        }
        finish_runtime_replay(
            demo_db, call["call_id"], {"content": "OK", "provider_response_id": "offline-completion-1"},
            [{"input_tokens": 3, "output_tokens": 1, "total_tokens": 4}],
        )
        mark_delivered(demo_db, recovered_dispatch["request_key"])
        with connect(demo_db) as connection:
            assert connection.execute("SELECT status FROM assistant_calls WHERE call_id=?", (call["call_id"],)).fetchone()[0] == "OK"
            assert connection.execute("SELECT status FROM assistant_runtime_spends WHERE request_key=?", (dispatch["request_key"],)).fetchone()[0] == "DELIVERED"
        assert spend_summary(demo_db)["committed_or_reserved_usd_micro"] == 4
    finally:
        worker.release()


def test_unknown_holds_one_reservation_but_other_sessions_can_use_remaining_pool(demo_db, monkeypatch):
    from opspilot.domain.assistant_runtime_grant import (
        bind_run, claim_send, runtime_config_from_env, spend_summary, store_response,
        validate_http_request,
    )

    _configure(monkeypatch)
    _provision(demo_db, total=30_000)
    worker = _worker(demo_db)
    try:
        run1 = _run(demo_db, "unknown-1", worker_id=worker.owner_id)
        binding1 = bind_run(demo_db, run1["run_id"], runtime_config_from_env())
        call1, dispatch1, request1 = _call(demo_db, run1, worker.owner_id, binding1)
        body = b'{"model":"deepseek-flash","messages":[{"role":"user","content":"hello"}],"max_tokens":2048,"thinking":{"type":"disabled"},"stream":false}'
        digest, max_tokens = validate_http_request("https://api.deepseek.com/chat/completions", "POST", body, binding1)
        claim_send(
            demo_db, binding1, call_id=call1["call_id"], request_key=dispatch1["request_key"],
            request_digest=call1["request_digest"], body_digest=digest,
            request_url="https://api.deepseek.com/chat/completions", method="POST",
            requested_max_output_tokens=max_tokens, worker_id=worker.owner_id, worker_epoch=worker.epoch,
        )
        unknown = store_response(
            demo_db, dispatch1["request_key"], status_code=200,
            headers={"content-type": "application/json"},
            body=b'{"id":"missing-usage","choices":[]}', usage=None,
        )
        assert unknown == {"replayable": False, "usage_state": "UNKNOWN"}
        assert spend_summary(demo_db)["committed_or_reserved_usd_micro"] == 14_048
        with pytest.raises(Exception, match="RUNTIME_EXTERNAL_RESULT_UNKNOWN"):
            claim_send(
                demo_db, binding1, call_id=call1["call_id"], request_key=dispatch1["request_key"],
                request_digest=call1["request_digest"], body_digest=digest,
                request_url="https://api.deepseek.com/chat/completions", method="POST",
                requested_max_output_tokens=max_tokens, worker_id=worker.owner_id, worker_epoch=worker.epoch,
            )
        # A separate authorized Session can spend the remaining pool; UNKNOWN is not a global stop.
        run2 = _run(demo_db, "unknown-2", worker_id=worker.owner_id)
        binding2 = bind_run(demo_db, run2["run_id"], runtime_config_from_env())
        _, dispatch2, _ = _call(demo_db, run2, worker.owner_id, binding2, "answer:two")
        assert dispatch2["reserved_usd_micro"] == 14_048
        assert spend_summary(demo_db)["remaining_usd_micro"] == 1_904
    finally:
        worker.release()


def test_unknown_reconciliation_requires_audited_evidence_and_never_resends(demo_db, monkeypatch):
    from opspilot.domain.assistant_runtime_grant import (
        RuntimeGrantError, bind_run, claim_send, reconcile_unknown,
        reserve_dispatch, runtime_config_from_env, spend_summary, store_response,
        validate_http_request,
    )
    from opspilot.domain.database import connect
    from opspilot.domain.d2 import digest_json

    _configure(monkeypatch)
    _provision(demo_db, total=30_000)
    worker = _worker(demo_db)
    try:
        run = _run(demo_db, "unknown-reconcile", worker_id=worker.owner_id)
        binding = bind_run(demo_db, run["run_id"], runtime_config_from_env())
        call, dispatch, request = _call(demo_db, run, worker.owner_id, binding)
        body = b'{"model":"deepseek-flash","messages":[{"role":"user","content":"hello"}],"max_tokens":2048,"thinking":{"type":"disabled"},"stream":false}'
        digest, cap = validate_http_request("https://api.deepseek.com/chat/completions", "POST", body, binding)
        claim_send(
            demo_db, binding, call_id=call["call_id"], request_key=dispatch["request_key"],
            request_digest=digest_json(request), body_digest=digest,
            request_url="https://api.deepseek.com/chat/completions", method="POST",
            requested_max_output_tokens=cap, worker_id=worker.owner_id, worker_epoch=worker.epoch,
        )
        store_response(
            demo_db, dispatch["request_key"], status_code=200,
            headers={"content-type": "application/json"}, body=b'{"id":"unknown-usage"}', usage=None,
        )
        before = spend_summary(demo_db)
        assert before["committed_or_reserved_usd_micro"] == 14_048
        with pytest.raises(RuntimeGrantError, match="RUNTIME_GRANT_AUDIT_EVIDENCE_REQUIRED"):
            reconcile_unknown(
                demo_db, dispatch["request_key"], outcome="NOT_CHARGED", operator_id="",
                evidence_ref="", evidence_digest="", idempotency_key="unknown-reconcile-invalid",
            )
        assert spend_summary(demo_db)["committed_or_reserved_usd_micro"] == 14_048
        reconciled = reconcile_unknown(
            demo_db, dispatch["request_key"], outcome="NOT_CHARGED", operator_id="test-local-operator",
            evidence_ref="local:verified-provider-ledger-entry", evidence_digest="e" * 64,
            idempotency_key="runtime-grant-reconcile-unknown-v1",
        )
        assert reconciled["status"] == "RECONCILED"
        replay = reconcile_unknown(
            demo_db, dispatch["request_key"], outcome="NOT_CHARGED", operator_id="test-local-operator",
            evidence_ref="local:verified-provider-ledger-entry", evidence_digest="e" * 64,
            idempotency_key="runtime-grant-reconcile-unknown-v1",
        )
        assert replay["status"] == "RECONCILED"
        assert spend_summary(demo_db)["committed_or_reserved_usd_micro"] == 0
        with pytest.raises(RuntimeGrantError, match="RUNTIME_EXTERNAL_RESULT_UNKNOWN"):
            reserve_dispatch(
                demo_db, binding, call_id=call["call_id"], logical_key="answer:one",
                request_digest=digest_json(request), worker_id=worker.owner_id,
            )
        with connect(demo_db) as connection:
            audit_count = connection.execute(
                "SELECT COUNT(*) FROM assistant_runtime_audit WHERE action='RECONCILE_UNKNOWN'"
            ).fetchone()[0]
            spend = connection.execute(
                "SELECT status,settled_usd_micro FROM assistant_runtime_spends WHERE request_key=?",
                (dispatch["request_key"],),
            ).fetchone()
        assert audit_count == 1
        assert spend["status"] == "RECONCILED" and spend["settled_usd_micro"] == 0
    finally:
        worker.release()


def test_spend_pool_refuses_second_reservation_when_only_one_fits(demo_db, monkeypatch):
    from opspilot.domain.assistant_runtime_grant import (
        RuntimeGrantError, bind_run, runtime_config_from_env,
    )

    _configure(monkeypatch)
    _provision(demo_db, total=14_047)
    worker = _worker(demo_db)
    try:
        run = _run(demo_db, "too-small", worker_id=worker.owner_id)
        binding = bind_run(demo_db, run["run_id"], runtime_config_from_env())
        with pytest.raises(RuntimeGrantError, match="RUNTIME_BUDGET_EXHAUSTED"):
            _call(demo_db, run, worker.owner_id, binding)
    finally:
        worker.release()


def test_restarted_worker_marks_unresolved_send_unknown_without_releasing_reserve(demo_db, monkeypatch):
    from opspilot.domain.assistant_runtime_grant import (
        bind_run, claim_send, recover_interrupted_sends, runtime_config_from_env,
        spend_summary, validate_http_request,
    )

    _configure(monkeypatch)
    _provision(demo_db, total=30_000)
    worker = _worker(demo_db)
    try:
        run = _run(demo_db, "crash-after-send-grant", worker_id=worker.owner_id)
        binding = bind_run(demo_db, run["run_id"], runtime_config_from_env())
        call, dispatch, request = _call(demo_db, run, worker.owner_id, binding)
        body = b'{"model":"deepseek-flash","messages":[{"role":"user","content":"hello"}],"max_tokens":2048,"thinking":{"type":"disabled"},"stream":false}'
        digest, cap = validate_http_request("https://api.deepseek.com/chat/completions", "POST", body, binding)
        claim_send(
            demo_db, binding, call_id=call["call_id"], request_key=dispatch["request_key"],
            request_digest=call["request_digest"], body_digest=digest,
            request_url="https://api.deepseek.com/chat/completions", method="POST",
            requested_max_output_tokens=cap, worker_id=worker.owner_id, worker_epoch=worker.epoch,
        )
        assert recover_interrupted_sends(demo_db, "new-worker-epoch") == [dispatch["request_key"]]
        assert spend_summary(demo_db)["committed_or_reserved_usd_micro"] == 14_048
    finally:
        worker.release()


def test_database_copy_cannot_reuse_runtime_grant_or_pool(demo_db, tmp_path, monkeypatch):
    from opspilot.domain.assistant_runtime_grant import RuntimeGrantError, spend_summary

    _configure(monkeypatch)
    _provision(demo_db)
    copied = tmp_path / "copied.sqlite3"
    shutil.copy2(demo_db, copied)
    with pytest.raises(RuntimeGrantError, match="RUNTIME_DB_IDENTITY_MISMATCH"):
        spend_summary(copied)


def test_expired_grant_is_not_bound_and_zero_price_cannot_authorize_paid_calls(demo_db, monkeypatch):
    from opspilot.domain.assistant_runtime_grant import RuntimeGrantError, bind_run, runtime_config_from_env

    _configure(monkeypatch)
    expired = _provision(demo_db, expires_delta=-timedelta(hours=1))
    run = _run(demo_db, "expired-grant")
    assert expired["status"] == "ACTIVE"
    with pytest.raises(RuntimeGrantError, match="RUNTIME_GRANT_EXPIRED_OR_NOT_YET_VALID"):
        bind_run(demo_db, run["run_id"], runtime_config_from_env())

    other = demo_db.parent / "zero-price.sqlite3"
    from opspilot.domain.database import initialize
    initialize(other)
    with pytest.raises(RuntimeGrantError, match="RUNTIME_PRICE_INVALID"):
        _provision(other, input_rate=0)


def test_revoke_between_reservation_and_send_denies_wire_and_releases_only_unsent_reserve(
    demo_db, monkeypatch,
):
    from opspilot.domain.assistant_runtime_grant import (
        RuntimeGrantError, bind_run, claim_send, close_unfinished_dispatch,
        revise_default_grant, runtime_config_from_env, spend_summary, validate_http_request,
    )

    _configure(monkeypatch)
    _provision(demo_db, total=30_000)
    worker = _worker(demo_db)
    try:
        run = _run(demo_db, "revoke-before-send", worker_id=worker.owner_id)
        binding = bind_run(demo_db, run["run_id"], runtime_config_from_env())
        call, dispatch, request = _call(demo_db, run, worker.owner_id, binding)
        revised = revise_default_grant(
            demo_db, expected_version=1, changes={"status": "REVOKED"},
            operator_id="test-local-operator", source="isolated revocation test",
            evidence_ref="test:revoke-before-send", evidence_digest="c" * 64,
            idempotency_key="runtime-grant-revoke-before-send-v1",
        )
        assert revised["status"] == "REVOKED"
        replayed_revision = revise_default_grant(
            demo_db, expected_version=1, changes={"status": "REVOKED"},
            operator_id="test-local-operator", source="isolated revocation test",
            evidence_ref="test:revoke-before-send", evidence_digest="c" * 64,
            idempotency_key="runtime-grant-revoke-before-send-v1",
        )
        assert replayed_revision["grant_id"] == revised["grant_id"]
        assert replayed_revision["version"] == revised["version"]
        with pytest.raises(RuntimeGrantError, match="RUNTIME_AUDIT_IDEMPOTENCY_CONFLICT"):
            revise_default_grant(
                demo_db, expected_version=1, changes={"status": "REVOKED"},
                operator_id="different-operator", source="isolated revocation test",
                evidence_ref="test:revoke-before-send", evidence_digest="c" * 64,
                idempotency_key="runtime-grant-revoke-before-send-v1",
            )
        body = json.dumps({
            "model": "deepseek-flash", "messages": [{"role": "user", "content": "hello"}],
            "max_tokens": 2048, "thinking": {"type": "disabled"}, "stream": False,
        }, separators=(",", ":")).encode()
        digest, max_tokens = validate_http_request(
            "https://api.deepseek.com/chat/completions", "POST", body, binding,
        )
        with pytest.raises(RuntimeGrantError, match="RUNTIME_GRANT_REVOKED"):
            claim_send(
                demo_db, binding, call_id=call["call_id"], request_key=dispatch["request_key"],
                request_digest=call["request_digest"], body_digest=digest,
                request_url="https://api.deepseek.com/chat/completions", method="POST",
                requested_max_output_tokens=max_tokens, worker_id=worker.owner_id, worker_epoch=worker.epoch,
            )
        assert close_unfinished_dispatch(demo_db, dispatch["request_key"], "revoked-before-send") == "NOT_DISPATCHED"
        summary = spend_summary(demo_db)
        assert summary["status"] == "ACTIVE"
        assert summary["committed_or_reserved_usd_micro"] == 0
    finally:
        worker.release()


def test_current_readonly_followup_can_get_send_permit_while_correction_is_pending(
    demo_db, monkeypatch,
):
    from test_ar02_runtime import setup_run
    from opspilot.domain.s3 import prepare_s3_fixture
    from opspilot.domain.assistant_runtime_grant import (
        bind_run, claim_send, mark_unknown, runtime_config_from_env, validate_http_request,
    )
    from opspilot.domain.task_control import admit_task_message, claim_task_run, trusted_identity

    _configure(monkeypatch)
    _provision(demo_db, total=30_000)
    prepare_s3_fixture(demo_db, "PROCESSING", order_id="ar02-order", contract_version=2)
    worker = _worker(demo_db)
    try:
        initial = setup_run(demo_db, "核查当前订单", "pending-send", bind=True)
        identity = trusted_identity(demo_db, "support-a")
        correction = admit_task_message(
            demo_db, identity, session_id=initial["session_id"], task_id=initial["task_id"],
            input_kind="CORRECT_TASK_INPUT", body="请按新时间重新核对当前事实。",
            idempotency_key="runtime-pending-correction",
        )
        followup = admit_task_message(
            demo_db, identity, session_id=initial["session_id"], task_id=initial["task_id"],
            input_kind="CHAT_READONLY", body="在更正处理前说明当前进度。",
            idempotency_key="runtime-pending-readonly", assistant_core=True,
        )
        assert followup["sequence"] > correction["sequence"]
        claim_task_run(demo_db, identity, followup["run_id"])
        binding = bind_run(demo_db, followup["run_id"], runtime_config_from_env())
        call, dispatch, _ = _call(demo_db, followup, worker.owner_id, binding)
        body = json.dumps({
            "model": "deepseek-flash", "messages": [{"role": "user", "content": "hello"}],
            "max_tokens": 2048, "thinking": {"type": "disabled"}, "stream": False,
        }, separators=(",", ":")).encode()
        body_digest, max_tokens = validate_http_request(
            "https://api.deepseek.com/chat/completions", "POST", body, binding,
        )

        permit = claim_send(
            demo_db, binding, call_id=call["call_id"], request_key=dispatch["request_key"],
            request_digest=call["request_digest"], body_digest=body_digest,
            request_url="https://api.deepseek.com/chat/completions", method="POST",
            requested_max_output_tokens=max_tokens, worker_id=worker.owner_id,
            worker_epoch=worker.epoch,
        )
        assert permit == {"action": "SEND"}
        # No HTTP request is made by this offline test. Keep the durable send state
        # conservative, as a process loss after the grant would be UNKNOWN.
        mark_unknown(demo_db, dispatch["request_key"], "OFFLINE_TEST_STOPPED_AT_SEND_GRANT")
    finally:
        worker.release()


def test_aborted_task_cannot_get_new_provider_send_permit(demo_db, monkeypatch):
    from test_ar02_runtime import setup_run
    from opspilot.domain.s3 import prepare_s3_fixture
    from opspilot.domain.assistant_runtime_grant import (
        RuntimeGrantError, bind_run, claim_send, close_unfinished_dispatch,
        runtime_config_from_env, validate_http_request,
    )
    from opspilot.domain.task_control import abort_task, claim_task_run, trusted_identity

    _configure(monkeypatch)
    _provision(demo_db, total=30_000)
    prepare_s3_fixture(demo_db, "PROCESSING", order_id="ar02-order", contract_version=2)
    worker = _worker(demo_db)
    try:
        run = setup_run(demo_db, "核查当前订单", "abort-send", bind=True)
        identity = trusted_identity(demo_db, "support-a")
        claim_task_run(demo_db, identity, run["run_id"])
        binding = bind_run(demo_db, run["run_id"], runtime_config_from_env())
        call, dispatch, _ = _call(demo_db, run, worker.owner_id, binding)
        abort_task(
            demo_db, identity, task_id=run["task_id"], reason="offline send-boundary test",
            idempotency_key="runtime-abort-before-send",
        )
        body = json.dumps({
            "model": "deepseek-flash", "messages": [{"role": "user", "content": "hello"}],
            "max_tokens": 2048, "thinking": {"type": "disabled"}, "stream": False,
        }, separators=(",", ":")).encode()
        body_digest, max_tokens = validate_http_request(
            "https://api.deepseek.com/chat/completions", "POST", body, binding,
        )

        with pytest.raises(RuntimeGrantError, match="TASK_ABORTED"):
            claim_send(
                demo_db, binding, call_id=call["call_id"], request_key=dispatch["request_key"],
                request_digest=call["request_digest"], body_digest=body_digest,
                request_url="https://api.deepseek.com/chat/completions", method="POST",
                requested_max_output_tokens=max_tokens, worker_id=worker.owner_id,
                worker_epoch=worker.epoch,
            )
        assert close_unfinished_dispatch(
            demo_db, dispatch["request_key"], "aborted-before-send",
        ) == "NOT_DISPATCHED"
    finally:
        worker.release()


def test_stale_price_version_pauses_pool_without_resetting_any_spend(demo_db, monkeypatch):
    from opspilot.domain.assistant_runtime_grant import (
        RuntimeGrantError, bind_run, runtime_config_from_env, spend_summary,
    )

    _configure(monkeypatch)
    _provision(demo_db)
    run = _run(demo_db, "price-version-stale")
    monkeypatch.setenv("OPSPILOT_MODEL_PRICE_VERSION", "unexpected-price-version")
    with pytest.raises(RuntimeGrantError, match="RUNTIME_PROVIDER_CONFIGURATION_STALE"):
        bind_run(demo_db, run["run_id"], runtime_config_from_env())
    summary = spend_summary(demo_db)
    assert summary["status"] == "PAUSED"
    assert summary["pause_reason"] == "PROVIDER_CONFIGURATION_OR_PRICE_VERSION_STALE"
    assert summary["committed_or_reserved_usd_micro"] == 0


def test_usage_above_authorized_bound_pauses_shared_pool_and_is_not_delivered(demo_db, monkeypatch):
    from opspilot.domain.assistant_runtime_grant import (
        bind_run, claim_send, runtime_config_from_env, spend_summary, store_response,
        validate_http_request,
    )
    from opspilot.domain.d2 import digest_json
    from opspilot.domain.database import connect
    from opspilot.domain.assistant_runtime_grant import RuntimeGrantError

    _configure(monkeypatch)
    _provision(demo_db, total=30_000)
    worker = _worker(demo_db)
    try:
        run = _run(demo_db, "over-bound-usage", worker_id=worker.owner_id)
        binding = bind_run(demo_db, run["run_id"], runtime_config_from_env())
        call, dispatch, request = _call(demo_db, run, worker.owner_id, binding)
        body = json.dumps({
            "model": "deepseek-flash", "messages": [{"role": "user", "content": "hello"}],
            "max_tokens": 2048, "thinking": {"type": "disabled"}, "stream": False,
        }, separators=(",", ":")).encode()
        body_digest, cap = validate_http_request(
            "https://api.deepseek.com/chat/completions", "POST", body, binding,
        )
        claim_send(
            demo_db, binding, call_id=call["call_id"], request_key=dispatch["request_key"],
            request_digest=digest_json(request), body_digest=body_digest,
            request_url="https://api.deepseek.com/chat/completions", method="POST",
            requested_max_output_tokens=cap, worker_id=worker.owner_id, worker_epoch=worker.epoch,
        )
        response = json.dumps({
            "id": "offline-over-bound", "usage": {"prompt_tokens": 1, "completion_tokens": 2049, "total_tokens": 2050},
            "choices": [{"message": {"role": "assistant", "content": "must not be delivered"}, "finish_reason": "stop"}],
        }).encode()
        result = store_response(
            demo_db, dispatch["request_key"], status_code=200,
            headers={"content-type": "application/json"}, body=response,
            usage={"prompt_tokens": 1, "completion_tokens": 2049, "total_tokens": 2050},
        )
        assert result["usage_state"] == "VIOLATION"
        summary = spend_summary(demo_db)
        assert summary["status"] == "PAUSED"
        assert summary["committed_or_reserved_usd_micro"] == 2_050
        with connect(demo_db) as connection:
            row = connection.execute("SELECT status FROM assistant_runtime_spends WHERE request_key=?", (dispatch["request_key"],)).fetchone()
        assert row["status"] == "VIOLATION"
        with pytest.raises(RuntimeGrantError, match="RUNTIME_SPEND_POOL_PAUSED"):
            paused_run = _run(demo_db, "pool-paused-binding")
            bind_run(demo_db, paused_run["run_id"], runtime_config_from_env())
    finally:
        worker.release()


def test_ledger_total_over_authorized_pool_pauses_instead_of_reporting_remaining_zero(demo_db, monkeypatch):
    from opspilot.domain.assistant_runtime_grant import (
        RuntimeGrantError, bind_run, claim_send, runtime_config_from_env,
        spend_summary, store_response, validate_http_request,
    )
    from opspilot.domain.database import connect
    from opspilot.domain.d2 import digest_json

    _configure(monkeypatch)
    _provision(demo_db, total=20_000)
    worker = _worker(demo_db)
    try:
        run = _run(demo_db, "ledger-over-limit", worker_id=worker.owner_id)
        binding = bind_run(demo_db, run["run_id"], runtime_config_from_env())
        call, dispatch, request = _call(demo_db, run, worker.owner_id, binding)
        body = b'{"model":"deepseek-flash","messages":[{"role":"user","content":"hello"}],"max_tokens":2048,"thinking":{"type":"disabled"},"stream":false}'
        body_digest, cap = validate_http_request("https://api.deepseek.com/chat/completions", "POST", body, binding)
        claim_send(
            demo_db, binding, call_id=call["call_id"], request_key=dispatch["request_key"],
            request_digest=digest_json(request), body_digest=body_digest,
            request_url="https://api.deepseek.com/chat/completions", method="POST",
            requested_max_output_tokens=cap, worker_id=worker.owner_id, worker_epoch=worker.epoch,
        )
        response = b'{"id":"offline-ledger","usage":{"prompt_tokens":1,"completion_tokens":1,"total_tokens":2},"choices":[]}'
        store_response(
            demo_db, dispatch["request_key"], status_code=200,
            headers={"content-type": "application/json"}, body=response,
            usage={"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        )
        with connect(demo_db) as connection:
            connection.execute("UPDATE assistant_runtime_pools SET total_limit_usd_micro=1 WHERE pool_id='DEFAULT'")
        with pytest.raises(RuntimeGrantError, match="RUNTIME_LEDGER_INTEGRITY_ERROR"):
            spend_summary(demo_db)
        with connect(demo_db) as connection:
            pool = connection.execute("SELECT status,pause_reason FROM assistant_runtime_pools WHERE pool_id='DEFAULT'").fetchone()
        assert pool["status"] == "PAUSED"
        assert pool["pause_reason"] == "SPEND_LEDGER_EXCEEDS_AUTHORIZED_LIMIT"
    finally:
        worker.release()


@pytest.mark.parametrize(
    "pool_total,expect_complete",
    [(100_000, True), (14_048, False)],
    ids=["pool-covers-compression-and-answer", "compression-consumes-next-answer-allowance"],
)
def test_runtime_context_compression_and_answer_share_the_persistent_pool(
    demo_db, tmp_path, monkeypatch, pool_total, expect_complete,
):
    import asyncio
    import os
    from test_m302_context import _turn
    from opspilot.assistant import create_assistant_model, run_assistant
    from opspilot.domain.assistant_runtime_grant import bind_run, runtime_config_from_env, spend_summary
    from opspilot.domain.database import connect
    from opspilot.domain.context_engineering import estimate_messages_tokens, estimate_text_tokens
    from opspilot.domain.d2 import canonical_json
    from opspilot.domain.task_control import create_session, register_worker_owner, trusted_identity

    _configure(monkeypatch)
    monkeypatch.setenv("OPSPILOT_ASSISTANT_RUNTIME_ENABLED", "1")
    monkeypatch.setenv("OPSPILOT_ASSISTANT_PROVIDER_ENABLED", "1")
    monkeypatch.setenv("OPSPILOT_MODEL_API_KEY", "test-only-not-a-real-key")
    monkeypatch.delenv("OPSPILOT_ASSISTANT_EXPERIMENT_ID", raising=False)
    monkeypatch.setenv("OPSPILOT_CONTEXT_STRATEGY", "ROLLING_SUMMARY")
    monkeypatch.setenv("OPSPILOT_CONTEXT_INPUT_BUDGET_TOKENS", "12000")
    _provision(demo_db, total=pool_total)
    identity = trusted_identity(demo_db, "support-a")
    session_id = str(create_session(demo_db, identity)["session_id"])
    owner = "runtime-compression-history-worker"
    worker_epoch = register_worker_owner(demo_db, owner, os.getpid())
    for index in range(6):
        _turn(
            demo_db, session_id, owner,
            (f"Turn {index} preserves the original support goal, constraints, and user corrections. " * 180),
            key=f"runtime-compression-history-{index}",
            answer=(f"Historical response {index} is only an earlier explanation, not current evidence. " * 90),
        )
    run = _run(demo_db, "compression-shared-pool", session_id=session_id, worker_id=owner)
    binding = bind_run(demo_db, run["run_id"], runtime_config_from_env())
    import httpx

    sent = []

    async def respond(request):
        payload = json.loads((await request.aread()).decode("utf-8"))
        sent.append(payload)
        if int(payload.get("max_tokens", 2048)) < 2048:
            with connect(demo_db) as connection:
                attempt = connection.execute(
                    "SELECT source_dependencies_json FROM context_compression_attempts WHERE run_id=? AND status='RESERVED' ORDER BY created_at DESC LIMIT 1",
                    (run["run_id"],),
                ).fetchone()
            assert attempt is not None
            source_map = json.loads(attempt["source_dependencies_json"])["source_sequence_map"]
            first_sequence = int(next(iter(source_map)))
            content = json.dumps({
                "initial_goal": {"text": "Investigate the original user objective.", "source_sequences": [first_sequence]},
                "constraints": [], "user_assertions": [], "corrections": [],
                "rejected_hypotheses": [], "unresolved_items": [], "timeline": [],
            })
        else:
            assert payload["max_tokens"] == 2048
            content = "The context was compressed under the same authorized spend pool; no business facts were queried."
        input_usage = (
            estimate_messages_tokens(payload["messages"])
            + estimate_text_tokens(canonical_json(payload.get("tools", [])))
            + 64
        )
        assert 0 < input_usage <= 12_000
        return httpx.Response(200, json={
            "id": f"offline-runtime-{len(sent)}", "object": "chat.completion", "created": 1,
            "model": "deepseek-flash",
            "choices": [{"index": 0, "message": {"role": "assistant", "content": content}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": input_usage, "completion_tokens": 40, "total_tokens": input_usage + 40},
        })

    model = create_assistant_model(
        runtime_grant_binding=binding,
        transport_async=httpx.MockTransport(respond),
        transport_sync=httpx.MockTransport(lambda request: httpx.Response(500, request=request)),
    )
    try:
        result = asyncio.run(run_assistant(
            demo_db, tmp_path / "runtime-compression-checkpoint.sqlite3", owner,
            run["run_id"], model=model, runtime_grant_binding=binding,
            worker_epoch=worker_epoch,
        ))
    finally:
        asyncio.run(model.http_async_client.aclose())
        model.http_client.close()
    if expect_complete:
        assert result["status"] == "SUCCEEDED", result
        assert len(sent) >= 2
    else:
        # The summary call is a real charged model call. When its settlement
        # leaves less than the answer's worst-case reserve, the answer is denied.
        assert result["status"] != "SUCCEEDED", result
        assert len(sent) == 1
    assert any(int(item.get("max_tokens", 2048)) < 2048 for item in sent)
    if expect_complete:
        assert sent[-1]["max_tokens"] == 2048
    expected_settled = sum(
        estimate_messages_tokens(item["messages"])
        + estimate_text_tokens(canonical_json(item.get("tools", []))) + 104
        for item in sent
    )
    assert spend_summary(demo_db)["committed_or_reserved_usd_micro"] == expected_settled
    with connect(demo_db) as connection:
        rows = connection.execute(
            "SELECT status,pool_id,settled_usd_micro FROM assistant_runtime_spends ORDER BY created_at"
        ).fetchall()
        assert len(rows) == len(sent)
        assert all(row["status"] == "DELIVERED" and row["pool_id"] == "DEFAULT" for row in rows)
        assert sum(int(row["settled_usd_micro"]) for row in rows) == expected_settled


def test_concurrent_sessions_cannot_reserve_more_than_shared_pool(demo_db, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from opspilot.domain.assistant_runtime_grant import RuntimeGrantError, bind_run, runtime_config_from_env

    _configure(monkeypatch)
    _provision(demo_db, total=14_048)
    worker = _worker(demo_db)
    try:
        runs = [_run(demo_db, f"concurrent-{index}", worker_id=worker.owner_id) for index in range(2)]
        bindings = [bind_run(demo_db, row["run_id"], runtime_config_from_env()) for row in runs]

        def reserve_one(index):
            try:
                _, dispatch, _ = _call(
                    demo_db, runs[index], worker.owner_id, bindings[index],
                    logical_key=f"concurrent-call-{index}",
                )
                return dispatch["status"]
            except RuntimeGrantError as error:
                return error.code

        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(reserve_one, range(2)))
        assert outcomes.count("RESERVED") == 1
        assert outcomes.count("RUNTIME_BUDGET_EXHAUSTED") == 1
    finally:
        worker.release()


@pytest.mark.parametrize(
    "provision,provider_enabled",
    [(False, "1"), (True, "0")],
    ids=["missing-grant", "provider-disabled"],
)
def test_formal_worker_fails_closed_before_factory_without_runtime_authority(
    demo_db, tmp_path, monkeypatch, provision, provider_enabled,
):
    from fastapi.testclient import TestClient
    from opspilot.domain.database import connect
    from opspilot.web.app import create_app
    from test_ar02_assistant import ORIGIN, PASSWORDS
    from test_ar02_journey_p0 import _wait_run

    _configure(monkeypatch)
    monkeypatch.setenv("OPSPILOT_ASSISTANT_RUNTIME_ENABLED", "1")
    monkeypatch.setenv("OPSPILOT_ASSISTANT_PROVIDER_ENABLED", provider_enabled)
    monkeypatch.setenv("OPSPILOT_MODEL_API_KEY", "test-only-not-a-real-key")
    monkeypatch.delenv("OPSPILOT_ASSISTANT_EXPERIMENT_ID", raising=False)
    if provision:
        _provision(demo_db)
    factory_calls = []

    def forbidden_factory(**kwargs):
        factory_calls.append(kwargs)
        raise AssertionError("Factory must not run before the explicit runtime prerequisites.")

    app = create_app(
        db_path=demo_db, checkpoint_db_path=tmp_path / "runtime-denied-checkpoint.sqlite3",
        start_worker=True, credentials=PASSWORDS, expected_origin=ORIGIN,
        assistant_model_factory=forbidden_factory, assistant_runtime_enabled=True,
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
            headers={**headers, "Idempotency-Key": "runtime-denied-message"},
            json={"body": "Please explain HTTP 202."},
        )
        assert accepted.status_code == 202
        run = _wait_run(client, accepted.json()["run_id"])
        assert run["status"] == "FAILED"

    assert factory_calls == []
    with connect(demo_db) as connection:
        assert connection.execute("SELECT COUNT(*) FROM assistant_runtime_spends").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM assistant_calls WHERE kind='MODEL'").fetchone()[0] == 0


def test_formal_api_worker_chatopenai_uses_persistent_runtime_grant_and_mock_transport(
    demo_db, tmp_path, monkeypatch,
):
    import httpx
    from fastapi.testclient import TestClient
    from opspilot.assistant import create_assistant_model
    from opspilot.domain.database import connect
    from opspilot.web.app import create_app
    from test_ar02_assistant import ORIGIN, PASSWORDS
    from test_ar02_journey_p0 import _wait_run

    _configure(monkeypatch)
    _provision(demo_db, total=100_000)
    monkeypatch.setenv("OPSPILOT_ASSISTANT_RUNTIME_ENABLED", "1")
    monkeypatch.setenv("OPSPILOT_ASSISTANT_PROVIDER_ENABLED", "1")
    monkeypatch.setenv("OPSPILOT_MODEL_API_KEY", "test-only-not-a-real-key")
    monkeypatch.delenv("OPSPILOT_ASSISTANT_EXPERIMENT_ID", raising=False)
    sent = []

    async def respond(request):
        body = json.loads((await request.aread()).decode("utf-8"))
        assert str(request.url) == "https://api.deepseek.com/chat/completions"
        assert body["model"] == "deepseek-flash"
        assert body["max_tokens"] == 2_048 and body["thinking"] == {"type": "disabled"}
        assert body["parallel_tool_calls"] is False
        with connect(demo_db) as connection:
            row = connection.execute(
                "SELECT status,reserved_usd_micro FROM assistant_runtime_spends WHERE status='SEND_GRANTED'"
            ).fetchone()
            assert row is not None and row["reserved_usd_micro"] == 14_048
        sent.append(body)
        return httpx.Response(200, headers={"x-request-id": "runtime-offline-request"}, json={
            "id": "runtime-offline-completion", "object": "chat.completion", "created": 1,
            "model": "deepseek-flash",
            "choices": [{"index": 0, "message": {"role": "assistant", "content":
                "HTTP 202 表示请求已受理；没有当前同 Event 的 Receiver 观察时，不能确认业务处理完成。"},
                "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 12, "completion_tokens": 24, "total_tokens": 36},
        })

    transports = {
        "transport_async": httpx.MockTransport(respond),
        "transport_sync": httpx.MockTransport(lambda request: httpx.Response(500, request=request)),
    }
    app = create_app(
        db_path=demo_db, checkpoint_db_path=tmp_path / "runtime-formal-checkpoint.sqlite3",
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
            headers={**headers, "Idempotency-Key": "runtime-formal-message"},
            json={"body": "HTTP 202 是否意味着回调已经处理完成？"},
        )
        assert accepted.status_code == 202, accepted.text
        item = accepted.json()
        assert _wait_run(client, item["run_id"])["status"] == "SUCCEEDED"
        messages = client.get(f"/api/sessions/{session_id}/messages").json()["items"]
        answer = next(row for row in messages if row["role"] == "ASSISTANT")
        assert "不能确认业务处理完成" in answer["body"]

    assert len(sent) == 1
    with connect(demo_db) as connection:
        spend = connection.execute("SELECT * FROM assistant_runtime_spends").fetchone()
        assert spend["status"] == "DELIVERED"
        assert spend["completion_id"] == "runtime-offline-completion"
        assert json.loads(spend["usage_json"]) == {
            "input_tokens": 12, "output_tokens": 24, "total_tokens": 36,
        }
        call = connection.execute(
            "SELECT status,usage_json FROM assistant_calls WHERE run_id=? AND kind='MODEL'",
            (item["run_id"],),
        ).fetchone()
        assert call["status"] == "OK"
        call_id = connection.execute(
            "SELECT call_id FROM assistant_calls WHERE run_id=? AND kind='MODEL'", (item["run_id"],)
        ).fetchone()[0]
        assert connection.execute(
            "SELECT task_id FROM task_runs WHERE run_id=?", (item["run_id"],)
        ).fetchone()[0] is None
        experiment_tables = connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name IN "
            "('ar02_live_dispatches','ar02_live_experiment_budgets')"
        ).fetchall()
        assert experiment_tables == []
        for table in (
            "d3_approvals", "d3_action_permissions", "d3_action_intents",
            "d3_action_ledgers", "d3_delivery_records", "s3_diagnoses",
            "s3_handoff_receipts",
        ):
            assert connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0
        # Spend survives removal of its operational call row; it has no cascading FK.
        connection.execute("DELETE FROM assistant_calls WHERE call_id=?", (call_id,))
        assert connection.execute(
            "SELECT COUNT(*) FROM assistant_runtime_spends WHERE assistant_call_id=?", (call_id,)
        ).fetchone()[0] == 1


def test_runtime_transport_replays_decoded_gzip_response_with_valid_http_headers(monkeypatch):
    """A response body read by the ledger wrapper must not retain wire encoding headers."""
    import asyncio
    import gzip

    import httpx
    from opspilot import runtime_provider

    payload = json.dumps({
        "id": "offline-gzip-completion",
        "model": "deepseek-flash",
        "choices": [{
            "index": 0,
            "message": {
                "role": "assistant",
                "content": "Offline decoded response.",
            },
            "finish_reason": "stop",
        }],
        "usage": {"prompt_tokens": 3, "completion_tokens": 4, "total_tokens": 7},
    }, separators=(",", ":")).encode("utf-8")
    compressed = gzip.compress(payload)

    class GzipReplyTransport(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request):
            return httpx.Response(
                200,
                headers={
                    "content-type": "application/json",
                    "content-encoding": "gzip",
                    "content-length": str(len(compressed)),
                },
                content=compressed,
                request=request,
            )

        async def aclose(self):
            return None

    monkeypatch.setattr(
        runtime_provider.runtime_grant,
        "validate_http_request",
        lambda *_args: ("body-digest", 2048),
    )
    monkeypatch.setattr(
        runtime_provider.runtime_grant,
        "claim_send",
        lambda *_args, **_kwargs: {"action": "SEND"},
    )
    monkeypatch.setattr(
        runtime_provider.runtime_grant,
        "store_response",
        lambda *_args, **_kwargs: {"replayable": True, "usage_state": "KNOWN"},
    )
    binding = {
        "run_id": "offline-run-gzip",
        "db_path": "unused-offline-db",
        "endpoint": "https://api.deepseek.com/v1",
    }
    dispatch = {"request_key": "offline-request-gzip"}

    async def request_through_wrapped_transport():
        inner = GzipReplyTransport()
        wrapped_async, wrapped_sync = runtime_provider.wrap_transports(
            binding, inner, httpx.HTTPTransport(),
        )
        try:
            async with httpx.AsyncClient(
                transport=wrapped_async, trust_env=False,
            ) as client:
                response = await client.post(
                    "https://api.deepseek.com/v1/chat/completions",
                    content=b"{}",
                )
                return response.json()
        finally:
            wrapped_sync.close()

    with runtime_provider.dispatch_context(
        binding, dispatch, call_id="offline-call-gzip",
        request_digest="offline-digest", worker_id="offline-worker", worker_epoch=1,
    ):
        parsed = asyncio.run(request_through_wrapped_transport())

    assert parsed["id"] == "offline-gzip-completion"
    assert parsed["usage"]["total_tokens"] == 7
