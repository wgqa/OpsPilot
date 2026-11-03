from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
BASE_RUNNER = ROOT / "docs/evidence/ar-03/material-live-01/run_live.py"
RESUME02_RUNNER = ROOT / "docs/evidence/ar-03/material-live-01/resume-02/run_live.py"
EXPERIMENT_ID = "AR-03-MATERIAL-LIVE-01-RESUME-02"
CASE_ID = "MAT-01-PROTOCOL-EXCERPT"


def _load_base_runner():
    spec = importlib.util.spec_from_file_location("ar03_material_base_runner_resume02_tests", BASE_RUNNER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_resume02_runner():
    spec = importlib.util.spec_from_file_location("ar03_material_resume02_runner_tests", RESUME02_RUNNER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _valid_call(call_id: str = "call-1"):
    return {
        "call_id": call_id,
        "kind": "MODEL",
        "logical_key": "0:request",
        "status": "OK",
        "result": [{
            "type": "ai",
            "data": {
                "content": "HTTP 202 is accepted, not proof of processing.",
                "response_metadata": {"id": "chatcmpl-offline"},
            },
        }],
        "usage": [{"input_tokens": 35, "output_tokens": 9, "total_tokens": 44}],
    }


def _valid_dispatch(logical_key: str = "0:request"):
    return {
        "kind": "MODEL", "logical_key": logical_key, "status": "OK",
        "usage_state": "KNOWN",
        "usage": {"input_tokens": 35, "output_tokens": 9, "total_tokens": 44},
    }


def test_program_limit_notice_is_not_a_real_provider_answer():
    runner = _load_base_runner()

    outcome = runner._classify_case_outcome(
        run={"run_id": "run-1", "status": "FAILED"},
        answer={
            "body": "Program notice",
            "answer_kind": "PROGRAM_LIMIT",
            "answer_run_id": "run-1",
            "answer_source_message_id": "message-1",
        },
        calls=[], dispatches=[], expected_run_id="run-1",
        expected_source_message_id="message-1",
    )

    assert outcome["provider_outcome"] == "NOT_SENT"
    assert outcome["user_delivery_kind"] == "PROGRAM_FAILURE_NOTIFICATION"
    assert outcome["outcome_level"] == "PROGRAM_FAILURE_NOTIFICATION"


def test_real_answer_requires_completion_usage_and_exact_persisted_source():
    runner = _load_base_runner()

    outcome = runner._classify_case_outcome(
        run={"run_id": "run-1", "status": "SUCCEEDED"},
        answer={
            "body": "HTTP 202 is accepted, not proof of processing.",
            "answer_kind": "CHAT_MODEL",
            "answer_run_id": "run-1",
            "answer_source_message_id": "message-1",
        },
        calls=[_valid_call()], dispatches=[_valid_dispatch()],
        expected_run_id="run-1", expected_source_message_id="message-1",
    )

    assert outcome == {
        "provider_outcome": "KNOWN_VALID",
        "user_delivery_kind": "MODEL_ANSWER",
        "outcome_level": "REAL_PROVIDER_AND_FORMAL_WORKER",
        "completion_ids": ["chatcmpl-offline"],
        "reason": None,
    }


def test_answer_from_another_source_or_not_present_in_provider_completion_is_unverified():
    runner = _load_base_runner()
    answer = {
        "body": "HTTP 202 is accepted, not proof of processing.",
        "answer_kind": "CHAT_MODEL",
        "answer_run_id": "run-1",
        "answer_source_message_id": "different-message",
    }

    source_mismatch = runner._classify_case_outcome(
        run={"run_id": "run-1", "status": "SUCCEEDED"}, answer=answer,
        calls=[_valid_call()], dispatches=[_valid_dispatch()],
        expected_run_id="run-1", expected_source_message_id="message-1",
    )
    body_mismatch = runner._classify_case_outcome(
        run={"run_id": "run-1", "status": "SUCCEEDED"}, answer={**answer, "answer_source_message_id": "message-1", "body": "Unrelated text."},
        calls=[_valid_call()], dispatches=[_valid_dispatch()],
        expected_run_id="run-1", expected_source_message_id="message-1",
    )

    assert source_mismatch["outcome_level"] == "UNVERIFIED_NONMODEL_ANSWER"
    assert source_mismatch["user_delivery_kind"] == "UNVERIFIED_NONMODEL_ANSWER"
    assert body_mismatch["provider_outcome"] == "KNOWN_VALID"
    assert body_mismatch["user_delivery_kind"] == "UNVERIFIED_NONMODEL_ANSWER"
    assert body_mismatch["outcome_level"] == "UNVERIFIED_NONMODEL_ANSWER"


@pytest.mark.parametrize(
    "run,answer,calls,dispatches,expected_level",
    [
        (
            {"run_id": "run-1", "status": "FAILED"},
                {"body": "Program stopped", "answer_kind": "PROGRAM_LIMIT", "answer_run_id": "run-1", "answer_source_message_id": "message-1"},
            [_valid_call()],
            [{**_valid_dispatch(), "status": "UNKNOWN", "usage_state": "UNKNOWN", "usage": None}],
            "PROVIDER_RESULT_UNKNOWN",
        ),
        (
            {"run_id": "run-1", "status": "SUCCEEDED"},
                {"body": "Text without model provenance", "answer_kind": None, "answer_run_id": "run-1", "answer_source_message_id": "message-1"},
            [], [], "UNVERIFIED_NONMODEL_ANSWER",
        ),
        (
            {"run_id": "run-1", "status": "FAILED"},
            None, [], [], "NO_ANSWER_NO_EXECUTION",
        ),
    ],
)
def test_result_classification_keeps_unknown_and_unverified_delivery_distinct(
    run, answer, calls, dispatches, expected_level,
):
    runner = _load_base_runner()

    outcome = runner._classify_case_outcome(
        run=run, answer=answer, calls=calls, dispatches=dispatches,
        expected_run_id="run-1", expected_source_message_id="message-1",
    )

    assert outcome["outcome_level"] == expected_level


def test_resume02_experiment_has_frozen_campaign_limits_and_schema(tmp_path):
    from opspilot.domain.assistant_experiment import (
        EXPERIMENTS_AWAITING_PAID_AUTHORIZATION,
        SUPPORTED_EXPERIMENT_IDS,
        initialize_experiment,
        read_budget,
    )

    assert EXPERIMENT_ID in SUPPORTED_EXPERIMENT_IDS
    assert EXPERIMENT_ID in EXPERIMENTS_AWAITING_PAID_AUTHORIZATION
    path = tmp_path / "domain.sqlite3"
    initialize_experiment(path, EXPERIMENT_ID)
    budget = read_budget(path, EXPERIMENT_ID)
    assert (budget["provider_limit"], budget["mcp_limit"]) == (16, 10)
    assert budget["budget_usd_micro"] == 10_500_000
    from opspilot.domain.assistant import run_limits_for_experiment
    assert run_limits_for_experiment(EXPERIMENT_ID) == (16, 10)


def test_resume02_provider_requires_matching_one_shot_claim(tmp_path, monkeypatch):
    import opspilot.assistant as assistant

    authorization = assistant._resume02_expected_authorization()
    auth_path = tmp_path / "PAID_AUTHORIZATION.json"
    auth_bytes = (json.dumps(authorization, sort_keys=True) + "\n").encode()
    auth_path.write_bytes(auth_bytes)
    token = "offline-resume-02-token"
    claim = assistant._resume02_expected_claim(hashlib.sha256(auth_bytes).hexdigest())
    claim.update({
        "status": "CLAIMED_ONE_SHOT_NO_RETRY",
        "claimed_at": "2026-11-04T00:00:00+00:00",
        "token_sha256": hashlib.sha256(token.encode()).hexdigest(),
    })
    claim_path = tmp_path / "claim.json"
    claim_path.write_text(json.dumps(claim), encoding="utf-8")

    monkeypatch.setattr(assistant, "MATERIAL_RESUME_02_AUTH_RECORD", auth_path)
    monkeypatch.setattr(assistant, "MATERIAL_RESUME_02_CLAIM", claim_path)
    monkeypatch.setenv(assistant.MATERIAL_RESUME_02_TOKEN_ENV, token)
    assert assistant._material_resume_02_one_shot_authorized(EXPERIMENT_ID) is True
    assert assistant._material_resume_02_one_shot_authorized("AR-03-MATERIAL-LIVE-01-RESUME-01") is False

    monkeypatch.setenv(assistant.MATERIAL_RESUME_02_TOKEN_ENV, token + "-wrong")
    assert assistant._material_resume_02_one_shot_authorized(EXPERIMENT_ID) is False


def test_resume02_allowlist_without_token_or_claim_cannot_construct_provider(monkeypatch, tmp_path):
    import opspilot.assistant as assistant

    monkeypatch.setenv("OPSPILOT_ASSISTANT_PROVIDER_ENABLED", "1")
    monkeypatch.setenv("OPSPILOT_ASSISTANT_EXPERIMENT_ID", EXPERIMENT_ID)
    monkeypatch.setenv("OPSPILOT_MODEL_NAME", "deepseek-flash")
    monkeypatch.setenv("OPSPILOT_MODEL_API_KEY", "offline-placeholder-not-a-secret")
    monkeypatch.setenv("OPSPILOT_MODEL_BASE_URL", "https://api.deepseek.com/v1")
    monkeypatch.delenv(assistant.MATERIAL_RESUME_02_TOKEN_ENV, raising=False)

    with pytest.raises(RuntimeError, match="AR03_MATERIAL_LIVE_PAID_AUTHORIZATION_REQUIRED"):
        assistant.create_assistant_model(
            transport_async=__import__("httpx").MockTransport(lambda request: __import__("httpx").Response(200)),
            transport_sync=__import__("httpx").MockTransport(lambda request: __import__("httpx").Response(200)),
        )


def test_blocked_preflight_never_consumes_resume02_claim(monkeypatch, tmp_path):
    runner = _load_resume02_runner()
    monkeypatch.setattr(runner, "AUTHORIZATION_CLAIM_DIR", tmp_path / "authorization")
    monkeypatch.setattr(runner, "AUTHORIZATION_CLAIM", tmp_path / "authorization" / "claim.json")
    monkeypatch.setattr(runner, "_validate_preflight", lambda: (_ for _ in ()).throw(RuntimeError("CREDENTIAL_MISSING")))

    with pytest.raises(RuntimeError, match="CREDENTIAL_MISSING"):
        runner._execute_once()

    assert not runner.AUTHORIZATION_CLAIM_DIR.exists()
    assert not runner.AUTHORIZATION_CLAIM.exists()


def test_static_resume02_authorization_and_immutable_history_hashes_are_valid():
    runner = _load_resume02_runner()
    authorization, digest = runner._validate_authorization()

    assert authorization["experiment_id"] == EXPERIMENT_ID
    assert len(digest) == 64
    assert runner._validate_prepared_claim()["one_shot_consumed"] is False
    history = runner._validate_historical_claims()
    assert history["historical_claims_reused"] == "false"
    assert history["historical_resume01_claim_sha256"] == runner.RESUME01_CLAIM_SHA256
    assert history["historical_root_claim_sha256"] == runner.HISTORICAL_CLAIM_SHA256


@pytest.mark.parametrize("mode,expected_hidden", [("OFF", True), ("ON", False)])
def test_resume02_skill_visibility_preserves_frozen_off_on_condition(monkeypatch, mode, expected_hidden):
    from opspilot.assistant import assistant_tool_hidden_for_experiment

    monkeypatch.setenv("OPSPILOT_AR03_MATERIAL_SKILL_MODE", mode)
    assert assistant_tool_hidden_for_experiment(
        "load_protocol_upgrade_skill", EXPERIMENT_ID,
    ) is expected_hidden


def test_resume02_formal_worker_persists_reservation_and_classifies_mock_completion(
    monkeypatch, tmp_path,
):
    import httpx
    from fastapi.testclient import TestClient
    import opspilot.assistant as assistant
    from opspilot.domain.assistant_experiment import initialize_experiment, read_budget
    from opspilot.domain.database import connect
    from opspilot.web.app import create_app

    wrapper = _load_resume02_runner()
    runner = wrapper._bound_base_runner()
    runner.DOMAIN_DB = tmp_path / "domain.sqlite3"
    runner.CHECKPOINT_DB = tmp_path / "checkpoints.sqlite3"
    runner.EVIDENCE = tmp_path / "evidence"
    runner.EVIDENCE.mkdir()
    runner._bootstrap_fresh_campaign_database(runner.DOMAIN_DB)
    initialize_experiment(runner.DOMAIN_DB, EXPERIMENT_ID)

    authorization_path = tmp_path / "PAID_AUTHORIZATION.json"
    authorization_bytes = (json.dumps(assistant._resume02_expected_authorization(), sort_keys=True) + "\n").encode()
    authorization_path.write_bytes(authorization_bytes)
    token = "offline-resume02-integration-token"
    claim = assistant._resume02_expected_claim(hashlib.sha256(authorization_bytes).hexdigest())
    claim.update({
        "status": "CLAIMED_ONE_SHOT_NO_RETRY",
        "claimed_at": "2026-11-04T00:00:00+00:00",
        "token_sha256": hashlib.sha256(token.encode()).hexdigest(),
    })
    claim_path = tmp_path / "claim.json"
    claim_path.write_text(json.dumps(claim), encoding="utf-8")
    monkeypatch.setattr(assistant, "MATERIAL_RESUME_02_AUTH_RECORD", authorization_path)
    monkeypatch.setattr(assistant, "MATERIAL_RESUME_02_CLAIM", claim_path)
    monkeypatch.setenv(assistant.MATERIAL_RESUME_02_TOKEN_ENV, token)
    monkeypatch.setenv("OPSPILOT_ASSISTANT_PROVIDER_ENABLED", "1")
    monkeypatch.setenv("OPSPILOT_ASSISTANT_EXPERIMENT_ID", EXPERIMENT_ID)
    monkeypatch.setenv("OPSPILOT_MODEL_NAME", "deepseek-flash")
    monkeypatch.setenv("OPSPILOT_MODEL_API_KEY", "offline-placeholder-not-a-secret")
    monkeypatch.setenv("OPSPILOT_MODEL_BASE_URL", "https://api.deepseek.com/v1")

    request_observations = []
    state = runner._CampaignState(tmp_path / "provider.jsonl", runner.DOMAIN_DB)
    accepted = runner._create_user_run(CASE_ID, runner._case_inputs()[CASE_ID], bound=False)
    state.case_id = CASE_ID
    state.run_id = accepted["run_id"]

    def handler(request):
        body = json.loads(request.content)
        assert request.method == "POST"
        assert str(request.url) == "https://api.deepseek.com/v1/chat/completions"
        assert body["model"] == "deepseek-flash"
        assert body["thinking"] == {"type": "disabled"}
        assert body["max_tokens"] == 2048
        assert body["stream"] is False
        assert body["parallel_tool_calls"] is False
        assert body["tool_choice"] == "auto"
        assert body["tools"]
        budget = read_budget(runner.DOMAIN_DB, EXPERIMENT_ID)
        with connect(runner.DOMAIN_DB) as connection:
            dispatches = connection.execute(
                "SELECT status,logical_key FROM ar02_live_dispatches WHERE experiment_id=? AND kind='MODEL'",
                (EXPERIMENT_ID,),
            ).fetchall()
            calls = connection.execute(
                "SELECT status,logical_key FROM assistant_calls WHERE run_id=? AND kind='MODEL'",
                (accepted["run_id"],),
            ).fetchall()
        request_observations.append((budget, [dict(row) for row in dispatches], [dict(row) for row in calls]))
        assert budget["provider_used"] == 1
        assert len(dispatches) == len(calls) == 1
        assert dispatches[0]["status"] == calls[0]["status"] == "RESERVED"
        return httpx.Response(200, json={
            "id": "chatcmpl-resume02-offline",
            "object": "chat.completion",
            "created": 1793740000,
            "model": "deepseek-flash",
            "choices": [{
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": "HTTP 202 means accepted for processing; it does not prove the Receiver completed the callback.",
                },
                "finish_reason": "stop",
            }],
            "usage": {"prompt_tokens": 73, "completion_tokens": 21, "total_tokens": 94},
        })

    transport = httpx.MockTransport(handler)

    def model_factory():
        return assistant.create_assistant_model(
            transport_async=runner._RecordingAsyncTransport(state, inner=transport),
            transport_sync=runner._NoSyncTransport(),
        )

    app = create_app(
        db_path=runner.DOMAIN_DB,
        checkpoint_db_path=runner.CHECKPOINT_DB,
        start_worker=True,
        credentials={"support-a": runner.SUPPORT_PASSWORD},
        expected_origin=runner.API_ORIGIN,
        assistant_model_factory=model_factory,
        assistant_experiment_id=EXPERIMENT_ID,
    )
    with TestClient(app) as client:
        runner._login(client)
        run = runner._wait_run(client, accepted["run_id"], seconds=20)

    result = runner._audit_case(
        {**accepted, "case_id": CASE_ID, "run_id": accepted["run_id"], "message_id": accepted["message_id"]},
        0, 0,
    )
    assert len(request_observations) == 1
    assert result["run"]["status"] == run["status"] == "SUCCEEDED"
    assert result["provider_outcome"] == "KNOWN_VALID"
    assert result["user_delivery_kind"] == "MODEL_ANSWER"
    assert result["outcome_level"] == "REAL_PROVIDER_AND_FORMAL_WORKER"
    assert result["completion_ids"] == ["chatcmpl-resume02-offline"]
    assert result["model_call_count"] == 1
    assert result["answer"] and "202" in result["answer"]
    assert result["campaign_budget"]["provider_used"] == 1
    assert set(result["business_write_counts"].values()) == {0}
