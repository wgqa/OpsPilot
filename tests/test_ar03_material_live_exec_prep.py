from __future__ import annotations

import importlib.util
import hashlib
import json
import sys
import types
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[1]
EXPERIMENT_ID = "AR-03-MATERIAL-LIVE-01-RESUME-01"
RUNNER_PATH = ROOT / "docs/evidence/ar-03/material-live-01/resume-01/run_live.py"


def _load_resume_runner():
    spec = importlib.util.spec_from_file_location("ar03_material_resume_runner_test", RUNNER_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_recovery_test():
    path = ROOT / "tests/test_ar03_material_live_recovery_01.py"
    spec = importlib.util.spec_from_file_location("ar03_material_live_recovery_helpers", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _file_digest(path: Path) -> str | None:
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def test_new_execution_identity_has_the_same_frozen_budget_but_no_run_limit_expansion(monkeypatch):
    from opspilot.domain.assistant_experiment import SUPPORTED_EXPERIMENT_IDS, _limits_for_experiment
    from opspilot.domain.assistant import run_limits_for_experiment
    from opspilot.assistant import assistant_tool_hidden_for_experiment

    assert EXPERIMENT_ID in SUPPORTED_EXPERIMENT_IDS
    assert _limits_for_experiment(EXPERIMENT_ID) == (16, 10)
    assert run_limits_for_experiment(EXPERIMENT_ID) == (16, 10)
    assert run_limits_for_experiment(None) == (8, 6)
    monkeypatch.setenv("OPSPILOT_AR03_MATERIAL_SKILL_MODE", "OFF")
    assert assistant_tool_hidden_for_experiment("load_protocol_upgrade_skill", EXPERIMENT_ID) is True
    assert assistant_tool_hidden_for_experiment("get_order_status", EXPERIMENT_ID) is False
    monkeypatch.setenv("OPSPILOT_AR03_MATERIAL_SKILL_MODE", "ON")
    assert assistant_tool_hidden_for_experiment("load_protocol_upgrade_skill", EXPERIMENT_ID) is False


def test_prepared_experiment_cannot_construct_a_paid_provider_even_with_global_opt_in(monkeypatch):
    monkeypatch.setenv("OPSPILOT_ASSISTANT_PROVIDER_ENABLED", "1")
    monkeypatch.setenv("OPSPILOT_ASSISTANT_EXPERIMENT_ID", EXPERIMENT_ID)
    monkeypatch.setenv("OPSPILOT_MODEL_NAME", "deepseek-flash")
    monkeypatch.setenv("OPSPILOT_MODEL_API_KEY", "offline-placeholder-not-a-secret")
    monkeypatch.setenv("OPSPILOT_MODEL_BASE_URL", "https://api.deepseek.com/v1")

    class OfflineClient:
        def close(self):
            pass

        async def aclose(self):
            pass

    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: OfflineClient())
    monkeypatch.setattr(httpx, "Client", lambda **kwargs: OfflineClient())
    fake_sdk = types.ModuleType("langchain_openai")
    fake_sdk.ChatOpenAI = lambda **kwargs: object()
    monkeypatch.setitem(sys.modules, "langchain_openai", fake_sdk)

    from opspilot.assistant import create_assistant_model

    with pytest.raises(RuntimeError, match="AR03_MATERIAL_LIVE_PAID_AUTHORIZATION_REQUIRED"):
        create_assistant_model(
            transport_async=httpx.MockTransport(lambda request: httpx.Response(200, json={})),
            transport_sync=httpx.MockTransport(lambda request: httpx.Response(200, json={})),
        )


def test_resume_runner_has_a_separate_prep_identity_and_never_executes_paid_run():
    runner = _load_resume_runner()
    assert runner.EXPERIMENT_ID == EXPERIMENT_ID
    assert runner.BRANCH == "codex/ar03-material-live-01-exec-prep"
    assert runner.BASE_SHA == "ff956ea71b90448d40229c57b8f8619c997b5cbd"
    assert runner.main(["--execute-once"]) == 2
    assert runner.main(["--execute-once"]) == 2
    assert not (runner.EVIDENCE / "EXECUTION_CLAIM.json").exists()
    assert not runner.RUNTIME.exists()


def test_prepared_claim_cannot_be_promoted_without_a_separate_authorization(tmp_path, monkeypatch):
    runner = _load_resume_runner()
    claim = json.loads(runner.PREPARED_CLAIM.read_text(encoding="utf-8"))
    claim["paid_dispatch_authorized"] = True
    claim_path = tmp_path / "claim.json"
    claim_path.write_text(json.dumps(claim), encoding="utf-8")
    monkeypatch.setattr(runner, "PREPARED_CLAIM", claim_path)
    with pytest.raises(RuntimeError, match="PREPARED_CLAIM_IDENTITY_OR_AUTHORIZATION_MISMATCH"):
        runner._validate_prepared_claim()


def test_resume_runner_preflight_rejects_wrong_branch_and_existing_campaign_state(tmp_path, monkeypatch):
    runner = _load_resume_runner()
    module = runner._bound_base_runner()
    module.ROOT = tmp_path
    module.EVIDENCE = tmp_path / "docs/evidence/ar-03/material-live-01/resume-01"
    module.CASES_PATH = tmp_path / "docs/evidence/ar-03/material-01/CASES.json"
    module.CASES_PATH.parent.mkdir(parents=True)
    module.CASES_PATH.write_bytes((ROOT / "docs/evidence/ar-03/material-01/CASES.json").read_bytes())
    module.RUNTIME = tmp_path / ".runtime" / "ar03-material-live-01-resume-01"
    module.DOMAIN_DB = module.RUNTIME / "domain.sqlite3"
    module.CHECKPOINT_DB = module.RUNTIME / "checkpoints.sqlite3"
    module.BRANCH = runner.BRANCH
    module.BASE_SHA = runner.BASE_SHA
    module.FREEZE_SHA = runner.FREEZE_SHA
    module.EXPERIMENT_ID = runner.EXPERIMENT_ID
    module._load_environment = lambda: tmp_path / ".env"

    env = {
        "OPSPILOT_MODEL_API_KEY": "offline-placeholder-not-a-secret",
        "OPSPILOT_MODEL_NAME": "deepseek-flash",
        "OPSPILOT_MODEL_BASE_URL": "https://api.deepseek.com/v1",
        "OPSPILOT_ASSISTANT_PROVIDER_ENABLED": "0",
        "OPSPILOT_ASSISTANT_EXPERIMENT_ID": "",
    }
    for key, value in env.items():
        monkeypatch.setenv(key, value)

    original_git = module._git

    def wrong_branch_git(*args, **kwargs):
        if args == ("branch", "--show-current"):
            return "codex/unapproved-branch"
        return original_git(*args, **kwargs)

    monkeypatch.setattr(module, "_git", wrong_branch_git)
    with pytest.raises(RuntimeError, match="MATERIAL_LIVE_BRANCH_MISMATCH"):
        module._validate_preflight()

    monkeypatch.setattr(module, "_git", original_git)
    monkeypatch.setattr(module, "_git", lambda *args, **kwargs: {
        ("rev-parse", "HEAD"): "test-head",
        ("branch", "--show-current"): runner.BRANCH,
        ("rev-parse", f"HEAD:docs/evidence/ar-03/material-01/CASES.json"): runner.CASES_BLOB,
        ("diff", "--name-only"): "",
        ("diff", "--cached", "--name-only"): "",
        ("ls-files", "--others", "--exclude-standard"): "",
        ("rev-parse", "main"): "unverified",
    }.get(args, ""))
    monkeypatch.setattr(module.subprocess, "run", lambda *args, **kwargs: types.SimpleNamespace(returncode=0, stdout="", stderr=""))
    module.EVIDENCE.mkdir(parents=True)
    (module.EVIDENCE / "EXECUTION_CLAIM.json").write_text("{}", encoding="utf-8")
    with pytest.raises(RuntimeError, match="EXPERIMENT_ALREADY_CLAIMED_OR_EVIDENCE_EXISTS"):
        module._validate_preflight()

    (module.EVIDENCE / "EXECUTION_CLAIM.json").unlink()
    module.RUNTIME.mkdir(parents=True)
    (module.RUNTIME / "domain.sqlite3").write_bytes(b"existing campaign must not be reused")
    with pytest.raises(RuntimeError, match="ISOLATED_RUNTIME_PATH_ALREADY_EXISTS"):
        module._validate_preflight()


def test_new_identity_zero_cost_formal_worker_preview_uses_independent_ledger(
    tmp_path, monkeypatch,
):
    from opspilot.domain.assistant_experiment import initialize_experiment, read_budget
    from opspilot.domain.d2 import configure_s3_experiment_budget, task_attempt_limits
    from opspilot.domain.database import connect
    from opspilot.domain.execution_budget import execution_budget_snapshot
    from opspilot.domain.s3 import prepare_s3_fixture
    from opspilot.web.app import create_app

    recovery = _load_recovery_test()
    runner = _load_resume_runner()
    base_runner = runner._bound_base_runner()
    historical_evidence = ROOT / "docs/evidence/ar-03/material-live-01"
    historical_runtime = ROOT / ".runtime/ar03-material-live-01"
    historical_paths = [
        historical_evidence / "EXECUTION_CLAIM.json",
        historical_evidence / "TRACE.jsonl",
        historical_evidence / "RESULTS.json",
        historical_evidence / "BUDGET_LEDGER.json",
        historical_runtime / "domain.sqlite3",
        historical_runtime / "checkpoints.sqlite3",
    ]
    historical_before = {str(path): _file_digest(path) for path in historical_paths}
    monkeypatch.setenv("OPSPILOT_ASSISTANT_EXPERIMENT_ID", EXPERIMENT_ID)
    monkeypatch.setenv("OPSPILOT_ASSISTANT_PROVIDER_ENABLED", "0")
    monkeypatch.setenv("OPSPILOT_AR03_MATERIAL_SKILL_MODE", "ON")

    db_path = tmp_path / "independent-domain.sqlite3"
    checkpoint_path = tmp_path / "independent-checkpoints.sqlite3"
    base_runner._bootstrap_fresh_campaign_database(db_path)
    initialize_experiment(db_path, EXPERIMENT_ID)
    empty_budget = read_budget(db_path, EXPERIMENT_ID)
    assert empty_budget["provider_limit"] == 16 and empty_budget["mcp_limit"] == 10
    assert empty_budget["provider_used"] == empty_budget["mcp_used"] == 0
    assert empty_budget["usd_reserved_micro"] == empty_budget["usd_settled_micro"] == 0

    fixture = prepare_s3_fixture(
        db_path, "DELIVERED_PENDING", tenant_id="tenant-a", order_id="ar03-order",
        contract_version=2, queue_age_seconds=60,
    )
    with connect(db_path) as connection:
        delivery = dict(connection.execute(
            "SELECT * FROM s3_deliveries WHERE tenant_id='tenant-a' AND order_id='ar03-order'"
        ).fetchone())
        receiver = dict(connection.execute(
            "SELECT * FROM s3_receivers WHERE tenant_id='tenant-a' AND order_id='ar03-order'"
        ).fetchone())
    assert delivery["status"] == "ACKNOWLEDGED" and delivery["receiver_http_status"] == 202
    assert receiver["status"] == "QUEUED"
    assert delivery["event_id"] == receiver["event_id"]

    cases = json.loads((ROOT / "docs/evidence/ar-03/material-01/CASES.json").read_text(encoding="utf-8"))
    user_input = next(item["input"] for item in cases["cases"] if item["id"] == "MAT-04-BOUND-QUEUED")
    model = recovery.RecoveryPreviewModel()
    from opspilot.assistant import create_assistant_model
    assert create_assistant_model() is None
    credentials = {"support-a": recovery.PASSWORD}
    setup_app = create_app(
        db_path=db_path, checkpoint_db_path=checkpoint_path, start_worker=False,
        credentials=credentials, expected_origin=recovery.ORIGIN,
        assistant_experiment_id=EXPERIMENT_ID,
    )
    with TestClient(setup_app) as client:
        headers = recovery._login(client)
        session_id = client.post("/api/sessions", headers=headers).json()["session_id"]
        accepted = client.post(
            f"/api/sessions/{session_id}/assistant/order",
            headers={**headers, "Idempotency-Key": "resume-01-offline-mat04"},
            json={"order_id": "ar03-order", "initial_message": user_input},
        )
        assert accepted.status_code == 202, accepted.text
        accepted_data = accepted.json()

    task_id = accepted_data["task_id"]
    run_id = accepted_data["run_id"]
    configured = configure_s3_experiment_budget(db_path, task_id, 16, 10)
    assert configured == {"MODEL": 16, "MCP": 10}
    assert task_attempt_limits(db_path, task_id) == configured
    assert execution_budget_snapshot(db_path, task_id)["deadline_ms"] == 300_000

    worker_app = create_app(
        db_path=db_path, checkpoint_db_path=checkpoint_path, start_worker=True,
        credentials=credentials, expected_origin=recovery.ORIGIN,
        assistant_model_factory=lambda: model, assistant_experiment_id=EXPERIMENT_ID,
    )
    with TestClient(worker_app) as client:
        headers = recovery._login(client)
        run = recovery._wait_run(client, run_id)
        messages = client.get(f"/api/sessions/{session_id}/messages", headers=headers).json()["items"]
        sources = client.get(f"/api/runs/{run_id}/assistant-sources").json()

    assert run["status"] == "SUCCEEDED"
    assert model.calls == 3
    assert model.proposed_tools == ["get_callback_delivery", "get_receiver_processing"]
    assert sources["current"] is True
    answer_rows = [row for row in messages if row.get("answer_source_message_id") == accepted_data["message_id"]]
    assert len(answer_rows) == 1
    assert "202/ACKNOWLEDGED" in answer_rows[0]["body"] and "QUEUED" in answer_rows[0]["body"]

    with connect(db_path) as connection:
        business_write_counts = {
            table: int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
            for table in base_runner.BUSINESS_WRITE_TABLES
        }
        observations = [dict(row) for row in connection.execute(
            "SELECT o.*,a.run_id AS attempt_run_id FROM d2_tool_observations o "
            "JOIN d2_attempts a ON a.attempt_id=o.attempt_id AND a.task_id=o.task_id "
            "WHERE o.task_id=? ORDER BY o.created_at,o.observation_id", (task_id,)
        ).fetchall()]
    after_budget = read_budget(db_path, EXPERIMENT_ID)
    assert len(observations) == 2
    assert {row["tool_name"] for row in observations} == {
        "get_callback_delivery", "get_receiver_processing",
    }
    assert all(row["status"] == "OK" and row["attempt_run_id"] == run_id for row in observations)
    assert after_budget["provider_used"] == 3  # Deterministic model dispatches, never HTTP Provider requests.
    assert after_budget["mcp_used"] == 2
    assert set(business_write_counts.values()) == {0}
    assert not runner.DOMAIN_DB.exists() and not runner.CHECKPOINT_DB.exists()
    assert runner._validate_prepared_claim()["paid_dispatch_authorized"] is False
    historical_after = {str(path): _file_digest(path) for path in historical_paths}
    assert historical_after == historical_before
