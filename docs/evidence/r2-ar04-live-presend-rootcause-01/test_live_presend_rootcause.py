from __future__ import annotations

import gzip
import json
import sys
from pathlib import Path

import httpx

EVIDENCE_DIR = Path(__file__).resolve().parents[1] / "r2-ar04-remaining-live-gate-01"
ROOT = EVIDENCE_DIR.parents[2]
if str(EVIDENCE_DIR) not in sys.path:
    sys.path.insert(0, str(EVIDENCE_DIR))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import run_remaining_live_gate as gate


def _task_runtime_config(abc) -> dict[str, str]:
    return {
        "model_id": gate.v2.MODEL,
        "endpoint": abc.ENDPOINT,
        "model_config_version": abc.NON_SECRET_DEFAULTS["OPSPILOT_MODEL_CONFIG_VERSION"],
        "price_version": abc.NON_SECRET_DEFAULTS["OPSPILOT_MODEL_PRICE_VERSION"],
        "service_identity": abc.NON_SECRET_DEFAULTS["OPSPILOT_ASSISTANT_SERVICE_IDENTITY"],
    }


def _frozen_mock_responses() -> list[dict]:
    trace_path = gate.MOCK_DIR / "MOCK_TRACE.jsonl.gz"
    with gzip.open(trace_path, "rt", encoding="utf-8") as stream:
        rows = [json.loads(line) for line in stream if line.strip()]
    return [row["response_payload"] for row in rows if row.get("event") == "RESPONSE_RECEIVED"]


def test_live_task_freeze_can_reenter_the_already_installed_task_contract():
    adapter_scope = "docs/evidence/abc-live-env-unblock-01"
    with gate._task_contract():
        assert gate._TASK_CONTRACT_DEPTH == 1
        assert gate.v2.PROTECTED_DIFF_PATHS.count(adapter_scope) == 0
        freeze = gate._task_assert_frozen()
        assert freeze["candidate_head_at_check"] == gate._git("rev-parse", "HEAD")
        assert gate._TASK_CONTRACT_DEPTH == 1
    assert gate._TASK_CONTRACT_DEPTH == 0
    assert gate.v2.PROTECTED_DIFF_PATHS.count(adapter_scope) == 1


def test_gate_stop_exposes_only_safe_bounded_error_codes():
    assert gate.GateStop("V2_PROTECTED_PATH_LAYOUT_DRIFT").code == "V2_PROTECTED_PATH_LAYOUT_DRIFT"
    assert not hasattr(gate.GateStop("TASK_DIFF_OUTSIDE_NEW_EVIDENCE:secret/path"), "code")
    assert not hasattr(gate.GateStop("X" * 101), "code")


def test_old_mock_runs_are_rejected_after_the_runner_digest_changes():
    current_runner_sha = gate._sha256(Path(gate.__file__).read_bytes())
    for old_run in ("mock_run_07", "mock_run_08"):
        old_path = gate.EVIDENCE_DIR / old_run / "MOCK_RESULTS.json"
        result, passed = gate._mock_passed(old_path)
        assert result["runner_sha256"] != current_runner_sha
        assert passed is False


def test_live_shaped_assistant_path_is_fully_intercepted_by_mock_transport(tmp_path, monkeypatch):
    responses = _frozen_mock_responses()
    assert len(responses) == gate.REQUEST_LIMIT

    observed_requests: list[dict] = []
    transport_instances: list[str] = []
    auth_checks: list[str] = []
    response_index = 0

    def mock_handler(request: httpx.Request) -> httpx.Response:
        nonlocal response_index
        payload = json.loads(request.content.decode("utf-8"))
        observed_requests.append({
            "host": request.url.host,
            "path": request.url.path,
            "method": request.method,
            "max_tokens": payload.get("max_tokens"),
            "tool_choice": payload.get("tool_choice"),
        })
        response_payload = responses[response_index]
        response_index += 1
        return httpx.Response(200, json=response_payload)

    def forced_mock_transport(*, retries: int = 0) -> httpx.MockTransport:
        assert retries == 0
        transport_instances.append("httpx.MockTransport")
        return httpx.MockTransport(mock_handler)

    sentinel_authorization = tmp_path / "no-authorization-file.json"

    def test_only_authorization_check(path: Path, *, mock_path: Path | None = None):
        assert path == sentinel_authorization
        assert not sentinel_authorization.exists()
        auth_checks.append("TEST_ONLY_VALIDATOR_STUB")
        return ({"test_only": True}, {"validation": "TEST_ONLY_VALIDATOR_STUB"})

    monkeypatch.setenv("OPSPILOT_MODEL_API_KEY", "offline-only-not-a-real-key")
    monkeypatch.setattr(httpx, "AsyncHTTPTransport", forced_mock_transport)
    monkeypatch.setattr(gate, "load_authorization", test_only_authorization_check)
    monkeypatch.setattr(gate, "_ACTIVE_AUTHORIZATION_PATH", sentinel_authorization)
    monkeypatch.setattr(gate, "_ACTIVE_METRICS", {"request_caps": [], "grants": []})

    output = tmp_path / "live-shaped-mock-only"
    with gate._task_contract():
        legacy, abc, *_ = gate.v2.build_runner()
        result = legacy.run_cases(
            abc,
            output,
            mode="LIVE",
            config=_task_runtime_config(abc),
            api_key="offline-only-not-a-real-key",
            authorized_task=gate.TASK,
            live_preflight={"technical_preflight_passed": True, "evidence_level": "TEST_ONLY"},
        )

    assert result["status"] == "COMPLETED"
    assert [row["status"] for row in result["cases"]] == ["SUCCEEDED", "SUCCEEDED"]
    assert len(observed_requests) == gate.REQUEST_LIMIT
    assert len(transport_instances) == 2
    assert len(auth_checks) == gate.REQUEST_LIMIT
    assert all(request["host"] == "api.deepseek.com" for request in observed_requests)
    assert all(request["method"] == "POST" for request in observed_requests)
    assert sorted(request["max_tokens"] for request in observed_requests) == sorted(
        [gate.SUMMARY_OUTPUT_TOKENS] * gate.SUMMARY_REQUEST_LIMIT
        + [gate.ANSWER_OUTPUT_TOKENS] * gate.ANSWER_REQUEST_LIMIT
    )
    assert [request["tool_choice"] for request in observed_requests if request["max_tokens"] == gate.ANSWER_OUTPUT_TOKENS] == [
        "none", "none",
    ]
    assert all(row["local_tool_observations"] == 0 for row in result["cases"])
    assert result["cases"][0]["summary_calls"] == 2
    assert result["cases"][0]["answer_calls"] == 1
    assert result["cases"][1]["summary_calls"] == 2
    assert result["cases"][1]["answer_calls"] == 1
    assert response_index == gate.REQUEST_LIMIT
    assert not sentinel_authorization.exists()
    q02_final = result["cases"][0]["provider_stage_and_prompt_visibility"]["final_answer_summary"]
    q02_items = q02_final["items"]
    assert q02_final["checks"]["endpoint_seq3"] is True
    assert any(3 in item.get("source_sequences", []) and "/callback" in str(item.get("text", ""))
               for item in q02_items)
    q06_final = result["cases"][1]["provider_stage_and_prompt_visibility"]["final_answer_summary"]
    q06_items = q06_final["items"]
    assert q06_final["checks"]["explicit_ordered_transition_with_source"] is True
    assert any(11 in item.get("source_sequences", [])
               and all(marker in str(item.get("text", ""))
                       for marker in ("v1.2", "v1.3", "max_attempts", "3", "5"))
               for item in q06_items)
    pinned_mock = json.loads(gate.MOCK_RESULTS_PATH.read_text(encoding="utf-8"))
    q06_mock = next(row for row in pinned_mock["cases"] if row["case_id"] == "Q06-B")
    assert q06_mock["fact_scope_diagnostics"]["max_attempts_early_value_seq3"]["status"] == "PARTIAL"
    ledger = json.loads((output / "COST_LEDGER.json").read_text(encoding="utf-8"))
    assert ledger["provider_requests_started"] == gate.REQUEST_LIMIT
    assert ledger["currently_reserved_usd_micro"] == 0
    assert all(slot["status"] == "COMPLETED" for slot in ledger["slots"])
    # run_cases marks the mode as LIVE for accounting, but every constructed
    # transport above is an in-process MockTransport and no Provider transport
    # implementation is ever instantiated by this test.


def test_frozen_check_failure_keeps_safe_error_code_and_stops_before_mock_send(tmp_path, monkeypatch):
    transport_handler_calls: list[None] = []
    auth_checks: list[str] = []

    def forbidden_if_reached(_request: httpx.Request) -> httpx.Response:
        transport_handler_calls.append(None)
        return httpx.Response(200, json={})

    def forced_mock_transport(*, retries: int = 0) -> httpx.MockTransport:
        assert retries == 0
        return httpx.MockTransport(forbidden_if_reached)

    sentinel_authorization = tmp_path / "no-authorization-file.json"

    def test_only_authorization_check(path: Path, *, mock_path: Path | None = None):
        assert path == sentinel_authorization
        auth_checks.append("TEST_ONLY_VALIDATOR_STUB")
        return ({"test_only": True}, {"validation": "TEST_ONLY_VALIDATOR_STUB"})

    real_git = gate._git
    adapter_path = "docs/evidence/abc-live-env-unblock-01/run_abc_eval.py"

    def force_adapter_blob_drift(*args: str) -> str:
        if (len(args) >= 3 and args[0] == "hash-object"
                and args[1] == f"--path={adapter_path}"):
            return "0" * 40
        return real_git(*args)

    monkeypatch.setenv("OPSPILOT_MODEL_API_KEY", "offline-only-not-a-real-key")
    monkeypatch.setattr(httpx, "AsyncHTTPTransport", forced_mock_transport)
    monkeypatch.setattr(gate, "load_authorization", test_only_authorization_check)
    monkeypatch.setattr(gate, "_git", force_adapter_blob_drift)
    monkeypatch.setattr(gate, "_ACTIVE_AUTHORIZATION_PATH", sentinel_authorization)
    monkeypatch.setattr(gate, "_ACTIVE_METRICS", {"request_caps": [], "grants": []})

    output = tmp_path / "frozen-drift-live-shaped-mock-only"
    with gate._task_contract():
        legacy, abc, *_ = gate.v2.build_runner()
        result = legacy.run_cases(
            abc,
            output,
            mode="LIVE",
            config=_task_runtime_config(abc),
            api_key="offline-only-not-a-real-key",
            authorized_task=gate.TASK,
            live_preflight={"technical_preflight_passed": True, "evidence_level": "TEST_ONLY"},
        )

    first_case = result["cases"][0]
    assert first_case["status"] == "STOPPED"
    assert first_case["compression_attempts"][0]["error_class"] == "PROVIDER_ADAPTER_BLOB_DRIFT"
    assert auth_checks == ["TEST_ONLY_VALIDATOR_STUB"]
    assert gate._ACTIVE_METRICS["request_caps"] == [
        {"case_id": "Q02-B", "purpose": "SUMMARY", "max_tokens": gate.SUMMARY_OUTPUT_TOKENS},
    ]
    assert transport_handler_calls == []
    assert result["recorded_requests"] == 0
    ledger = json.loads((output / "COST_LEDGER.json").read_text(encoding="utf-8"))
    assert all(slot["request_digest"] is None for slot in ledger["slots"])
