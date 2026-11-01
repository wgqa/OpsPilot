from __future__ import annotations

import asyncio
import json
from pathlib import Path
import sqlite3
import inspect

import httpx
import pytest

from experiments.ar02_conn02 import single_request as conn


def authorized_request(body=None, authorization="Bearer offline-dummy"):
    return httpx.Request(
        "POST",
        conn.ENDPOINT,
        headers={"authorization": authorization, "content-type": "application/json"},
        content=json.dumps(body if body is not None else conn.expected_body(), ensure_ascii=False).encode("utf-8"),
    )


def test_offline_preflight_uses_explicit_mock_transport_and_exact_sdk_wire():
    result = asyncio.run(conn.offline_preflight())
    assert result["status"] == "PASS_OFFLINE_PREFLIGHT"
    assert result["evidence_level"] == "EXPLICIT_HTTPX_MOCKTRANSPORT_ONLY"
    assert result["external_requests"] == 0
    assert result["mock_requests"] == result["sdk_http_requests"] == 1
    assert result["endpoint"] == conn.ENDPOINT
    assert result["body"] == conn.expected_body()
    assert result["body"]["messages"] == [{"role": "user", "content": "请只回复：OK"}]
    assert result["body"]["max_tokens"] == 64
    assert result["body"]["thinking"] == {"type": "disabled"}
    assert result["body"]["stream"] is False
    assert "tools" not in result["body"]
    assert "tool_choice" not in result["body"]
    assert "parallel_tool_calls" not in result["body"]


def test_wire_validation_rejects_any_parameter_drift():
    body = conn.expected_body()
    body["max_tokens"] = 65
    with pytest.raises(conn.StopBeforeSend, match="REQUEST_BODY_MISMATCH"):
        conn.validate_wire(authorized_request(body))


def test_wire_validation_requires_exact_endpoint_and_method():
    request = authorized_request()
    request.url = httpx.URL("https://example.invalid/chat/completions")
    with pytest.raises(conn.StopBeforeSend, match="ENDPOINT_MISMATCH"):
        conn.validate_wire(request)


def test_reservation_atomically_persists_unused_identity_attempt_and_cap(tmp_path):
    db = tmp_path / "single-use.sqlite3"
    ledger = conn.OneShotLedger(db)
    digest = conn.sha256_hex(conn.canonical_bytes(conn.expected_body()))
    attempt_id = ledger.reserve_exclusive(digest)
    snapshot = ledger.snapshot()
    assert snapshot["authorization"]["authorization_id"] == conn.AUTHORIZATION_ID
    assert snapshot["authorization"]["scope"] == "AR-02-CONN-02-ONE-COMPLETION"
    assert snapshot["authorization"]["reserved_micro_usd"] == 10_000
    assert snapshot["attempt"]["attempt_id"] == attempt_id
    assert snapshot["attempt"]["status"] == "ATTEMPT_RESERVED"
    assert snapshot["attempt"]["request_count"] == 0
    assert snapshot["attempt"]["request_digest"] == digest
    check = sqlite3.connect(db)
    try:
        assert check.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert check.execute("SELECT COUNT(*) FROM authorizations").fetchone()[0] == 1
        assert check.execute("SELECT COUNT(*) FROM attempts").fetchone()[0] == 1
    finally:
        check.close()


def test_one_shot_ledger_file_cannot_be_reused(tmp_path):
    db = tmp_path / "single-use.sqlite3"
    ledger = conn.OneShotLedger(db)
    digest = conn.sha256_hex(conn.canonical_bytes(conn.expected_body()))
    ledger.reserve_exclusive(digest)
    with pytest.raises(FileExistsError):
        ledger.reserve_exclusive(digest)


def test_transport_send_requires_persisted_attempt():
    capture = conn.WireCapture(live=True)
    with pytest.raises(conn.StopBeforeSend, match="MISSING_PERSISTED_ATTEMPT"):
        asyncio.run(capture.on_request(authorized_request()))
    assert capture.request_count == 1


def test_dispatch_is_exactly_once_and_terminal_state_blocks_a_second_dispatch(tmp_path):
    db = tmp_path / "single-use.sqlite3"
    ledger = conn.OneShotLedger(db)
    digest = conn.sha256_hex(conn.canonical_bytes(conn.expected_body()))
    attempt_id = ledger.reserve_exclusive(digest)
    ledger.mark_outbound_started(attempt_id, digest)
    snapshot = ledger.snapshot()
    assert snapshot["attempt"]["status"] == "OUTBOUND_STARTED"
    assert snapshot["attempt"]["request_count"] == 1
    with pytest.raises(conn.StopBeforeSend, match="PERSISTED_RESERVATION_NOT_AVAILABLE"):
        ledger.mark_outbound_started(attempt_id, digest)
    ledger.finish(attempt_id, "UNKNOWN_STOPPED", error_class="TEST_UNKNOWN")
    assert ledger.snapshot()["attempt"]["status"] == "UNKNOWN_STOPPED"


def test_peak_usage_cost_estimate_uses_peak_prices_without_cache_discount():
    assert conn.peak_cost_micro_usd({
        "prompt_tokens": 9,
        "completion_tokens": 1,
        "total_tokens": 10,
    }) == 4
    with pytest.raises(ValueError, match="USAGE_TOTAL_MISMATCH"):
        conn.peak_cost_micro_usd({
            "prompt_tokens": 9,
            "completion_tokens": 1,
            "total_tokens": 11,
        })


def test_make_clients_requires_explicit_transports():
    signature = inspect.signature(conn.make_clients)
    assert signature.parameters["transport_async"].default is inspect.Parameter.empty
    assert signature.parameters["transport_sync"].default is inspect.Parameter.empty


def test_known_response_validation_distinguishes_output_compliance_from_connectivity():
    capture = conn.WireCapture(live=False)
    capture.responses = [{
        "http_status": 200,
        "request_id": "req-local",
        "body": conn.mock_completion(),
    }]
    capture.raw_response = conn.mock_completion()

    class Message:
        content = "OK"

    summary = conn.completion_summary(capture, Message())
    assert summary["valid"] is True
    assert summary["completion_id"] == "mock-conn02-completion"
    assert summary["usage"]["total_tokens"] == 10
    assert summary["output_matches_requested_ok"] is True


def make_frozen_proof(path: Path):
    proof = {
        "status": "PASS_OFFLINE_PREFLIGHT",
        "evidence_level": "EXPLICIT_HTTPX_MOCKTRANSPORT_ONLY",
        "external_requests": 0,
        "mock_requests": 1,
        "sdk_http_requests": 1,
        "endpoint": conn.ENDPOINT,
        "body": conn.expected_body(),
        "body_sha256": conn.sha256_hex(conn.canonical_bytes(conn.expected_body())),
        "sender_source_sha256": conn.sha256_hex(Path(conn.__file__).read_bytes()),
    }
    path.write_text(json.dumps(proof, ensure_ascii=False), encoding="utf-8")
    return path


def test_reserve_only_persists_attempt_before_any_outbound(tmp_path, monkeypatch):
    db = tmp_path / "authorization.sqlite3"
    trace_path = tmp_path / "TRACE.jsonl"
    monkeypatch.setattr(conn, "ONE_SHOT_DB", db)
    monkeypatch.setattr(conn, "TRACE_PATH", trace_path)
    monkeypatch.setattr(conn, "read_api_key", lambda _: ("offline-dummy-key", "test-only"))
    proof = make_frozen_proof(tmp_path / "PREFLIGHT.json")

    result = asyncio.run(conn.reserve_only(None, proof))

    assert result["status"] == "ATTEMPT_RESERVED"
    assert result["outbound_requests"] == 0
    assert result["reserved_micro_usd"] == 10_000
    assert result["ledger"]["attempt"]["status"] == "ATTEMPT_RESERVED"
    assert result["ledger"]["attempt"]["request_count"] == 0
    rows = [json.loads(line) for line in trace_path.read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 1 and rows[0]["event"] == "authorization_reserved"


def test_replay_after_outbound_started_returns_unknown_without_reading_key(tmp_path, monkeypatch):
    db = tmp_path / "authorization.sqlite3"
    trace_path = tmp_path / "TRACE.jsonl"
    monkeypatch.setattr(conn, "ONE_SHOT_DB", db)
    monkeypatch.setattr(conn, "TRACE_PATH", trace_path)
    proof = make_frozen_proof(tmp_path / "PREFLIGHT.json")
    ledger = conn.OneShotLedger(db)
    proof_digest = json.loads(proof.read_text(encoding="utf-8"))["body_sha256"]
    attempt_id = ledger.reserve_exclusive(proof_digest)
    ledger.mark_outbound_started(attempt_id, proof_digest)
    with trace_path.open("w", encoding="utf-8") as stream:
        stream.write(json.dumps({"event": "authorization_reserved"}) + "\n")
    monkeypatch.setattr(conn, "read_api_key", lambda _: (_ for _ in ()).throw(AssertionError("must not read key")))

    result = asyncio.run(conn.send_once(None, proof))

    assert result["status"] == "UNKNOWN_STOPPED"
    assert result["reason"] == "PRIOR_OUTBOUND_STARTED_DO_NOT_RETRY"
    assert result["ledger"]["attempt"]["request_count"] == 1


def test_concurrent_dispatch_cas_allows_only_one_outbound_owner(tmp_path):
    from concurrent.futures import ThreadPoolExecutor

    db = tmp_path / "authorization.sqlite3"
    ledger = conn.OneShotLedger(db)
    digest = conn.sha256_hex(conn.canonical_bytes(conn.expected_body()))
    attempt_id = ledger.reserve_exclusive(digest)

    def mark():
        try:
            ledger.mark_outbound_started(attempt_id, digest)
            return "OWNED"
        except conn.StopBeforeSend:
            return "DENIED"

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: mark(), range(2)))

    assert sorted(results) == ["DENIED", "OWNED"]
    snapshot = ledger.snapshot()
    assert snapshot["attempt"]["request_count"] == 1
    assert snapshot["attempt"]["status"] == "OUTBOUND_STARTED"


def test_blocked_sender_cannot_overwrite_concurrent_outbound_state(tmp_path):
    db = tmp_path / "authorization.sqlite3"
    ledger = conn.OneShotLedger(db)
    digest = conn.sha256_hex(conn.canonical_bytes(conn.expected_body()))
    attempt_id = ledger.reserve_exclusive(digest)
    ledger.mark_outbound_started(attempt_id, digest)

    with pytest.raises(RuntimeError, match="ATTEMPT_FINALIZATION_CONFLICT"):
        ledger.finish(
            attempt_id,
            "BLOCKED_NOT_SENT",
            expected_prior_status="ATTEMPT_RESERVED",
        )

    assert ledger.snapshot()["attempt"]["status"] == "OUTBOUND_STARTED"
