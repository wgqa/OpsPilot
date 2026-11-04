from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
EXPERIMENT_ID = "AR-03-MATERIAL-REMAINDER-01"
RUNNER_PATH = ROOT / "docs/evidence/ar-03/material-remainder-live-01/run_live.py"


def _load_runner():
    spec = importlib.util.spec_from_file_location(
        "ar03_material_remainder_live_01_tests", RUNNER_PATH,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_live_runner_freezes_only_the_three_authorized_conditions():
    runner = _load_runner()

    assert runner.EXPERIMENT_ID == EXPERIMENT_ID
    assert runner.CASE_ORDER == (
        "MAT-05-BOUND-PROCESSED", "MAT-06-SKILL-OFF", "MAT-06-SKILL-ON",
    )
    assert runner.PROVIDER_LIMIT == 16
    assert runner.MCP_LIMIT is None
    assert runner.BUDGET_USD_MICRO == 10_500_000
    assert runner.RESERVATION_USD_MICRO == 645_600
    assert runner.CAMPAIGN_WALL_SECONDS == 3_600


def test_live_authorization_requires_a_new_exact_one_shot_claim(tmp_path, monkeypatch):
    from opspilot import assistant

    guard = getattr(assistant, "_material_remainder_live_one_shot_authorized", None)
    assert callable(guard)

    branch = subprocess.run(
        ["git", "branch", "--show-current"], cwd=ROOT, capture_output=True,
        text=True, check=True,
    ).stdout.strip()
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True,
        text=True, check=True,
    ).stdout.strip()
    auth_path = tmp_path / "PAID_AUTHORIZATION.json"
    claim_path = tmp_path / "claim.json"
    auth = assistant._material_remainder_live_expected_authorization()
    auth_bytes = (json.dumps(auth, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")
    auth_path.write_bytes(auth_bytes)
    token = "offline-only-one-shot-token"
    claim = assistant._material_remainder_live_expected_claim(
        hashlib.sha256(auth_bytes).hexdigest(), branch=branch, head=head,
    )
    claim.update({
        "claimed_at": "2026-11-04T00:00:00+00:00",
        "token_sha256": hashlib.sha256(token.encode("utf-8")).hexdigest(),
    })
    claim_path.write_text(json.dumps(claim, sort_keys=True), encoding="utf-8")

    monkeypatch.setattr(assistant, "MATERIAL_REMAINDER_LIVE_AUTH_RECORD", auth_path)
    monkeypatch.setattr(assistant, "MATERIAL_REMAINDER_LIVE_CLAIM", claim_path)
    monkeypatch.setenv(assistant.MATERIAL_REMAINDER_LIVE_TOKEN_ENV, token)
    monkeypatch.setenv("OPSPILOT_ASSISTANT_EXPERIMENT_ID", EXPERIMENT_ID)
    monkeypatch.setenv("OPSPILOT_ASSISTANT_PROVIDER_ENABLED", "1")
    assert guard(EXPERIMENT_ID) is True
    assert guard("AR-03-MATERIAL-LIVE-01-RESUME-02") is False

    claim["branch"] = "codex/unapproved-branch"
    claim_path.write_text(json.dumps(claim, sort_keys=True), encoding="utf-8")
    assert guard(EXPERIMENT_ID) is False

    claim["branch"] = branch
    claim_path.write_text(json.dumps(claim, sort_keys=True), encoding="utf-8")
    monkeypatch.setenv(assistant.MATERIAL_REMAINDER_LIVE_TOKEN_ENV, "wrong-token")
    assert guard(EXPERIMENT_ID) is False


def test_remainder_live_factory_remains_closed_without_claim(monkeypatch):
    from opspilot.assistant import create_assistant_model

    monkeypatch.setenv("OPSPILOT_ASSISTANT_PROVIDER_ENABLED", "1")
    monkeypatch.setenv("OPSPILOT_ASSISTANT_EXPERIMENT_ID", EXPERIMENT_ID)
    monkeypatch.setenv("OPSPILOT_MODEL_API_KEY", "offline-test-placeholder")
    monkeypatch.setenv("OPSPILOT_MODEL_NAME", "deepseek-flash")
    monkeypatch.setenv("OPSPILOT_MODEL_BASE_URL", "https://api.deepseek.com/v1")
    monkeypatch.delenv("OPSPILOT_AR03_MATERIAL_REMAINDER_LIVE_ONE_SHOT_TOKEN", raising=False)

    with pytest.raises(RuntimeError, match="AR03_MATERIAL_LIVE_PAID_AUTHORIZATION_REQUIRED"):
        create_assistant_model()


def test_one_shot_claim_is_atomic_and_cannot_be_reused(tmp_path, monkeypatch):
    runner = _load_runner()
    from opspilot import assistant

    for name in (
        assistant.MATERIAL_REMAINDER_LIVE_TOKEN_ENV,
        "OPSPILOT_ASSISTANT_PROVIDER_ENABLED",
        "OPSPILOT_ASSISTANT_EXPERIMENT_ID",
    ):
        monkeypatch.setenv(name, "")

    runtime = tmp_path / "runtime"
    claim_path = runtime / "claim.json"
    auth_path = tmp_path / "PAID_AUTHORIZATION.json"
    auth_path.write_text(
        json.dumps(assistant._material_remainder_live_expected_authorization(),
                   ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(runner, "RUNTIME", runtime)
    monkeypatch.setattr(runner, "CLAIM", claim_path)
    monkeypatch.setattr(runner, "AUTH_RECORD", auth_path)
    git = runner._git
    monkeypatch.setattr(
        runner, "_git",
        lambda *args, **kwargs: "" if args == ("status", "--porcelain=v1") else git(*args, **kwargs),
    )
    monkeypatch.setattr(assistant, "MATERIAL_REMAINDER_LIVE_AUTH_RECORD", auth_path)
    monkeypatch.setattr(assistant, "MATERIAL_REMAINDER_LIVE_CLAIM", claim_path)

    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True,
        text=True, check=True,
    ).stdout.strip()
    auth_digest = hashlib.sha256(auth_path.read_bytes()).hexdigest()
    preflight = {
        "status": "PREFLIGHT_READY", "branch": runner.BRANCH, "head": head,
        "base_sha": runner.BASE_SHA, "frozen_cases_blob": runner.CASES_BLOB,
        "remote_main": runner.MAIN_SHA,
        "authorization_record_sha256": auth_digest,
    }
    runner._consume_one_shot_claim(preflight)

    claim = json.loads(claim_path.read_text(encoding="utf-8"))
    assert claim["status"] == "CLAIMED_ONE_SHOT_NO_RETRY"
    assert claim["execution_head_sha"] == head
    assert assistant._material_remainder_live_one_shot_authorized(EXPERIMENT_ID)

    with pytest.raises(RuntimeError, match="ONE_SHOT_ALREADY_CONSUMED_OR_RUNTIME_EXISTS"):
        runner._consume_one_shot_claim(preflight)


def test_offline_preflight_uses_formal_worker_mock_transport_and_real_local_mcp():
    runner = _load_runner()

    result = runner._offline_mock_preflight()

    assert result["status"] == "OFFLINE_PREFLIGHT_PASSED"
    assert result["evidence_level"] == (
        "DETERMINISTIC_FIXTURE_MODEL_WITH_HTTPX_MOCKTRANSPORT_AND_REAL_LOCAL_MCP_DOMAIN"
    )
    assert result["run_status"] == "SUCCEEDED"
    assert result["provider_http_requests"] == 3
    assert result["external_provider_requests"] == 0
    assert result["mcp_dispatches"] == 2
    assert result["mcp_limit"] is None
    assert result["receiver_status"] == "PROCESSED"
    assert result["delivery_status"] == "ACKNOWLEDGED"
    assert result["delivery_http_status"] == 202
    assert result["paid_claim_consumed"] is False
    assert result["final_runtime_created"] is False
