from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "user-demo"))

import runtime_admin  # noqa: E402
from initialize_demo import initialize_user_demo  # noqa: E402


def _values(**overrides: str) -> dict[str, str]:
    values = {
        "OPSPILOT_MODEL_API_KEY": "offline-test-key-not-a-provider-credential",
        "OPSPILOT_MODEL_NAME": "deepseek-flash",
        "OPSPILOT_MODEL_BASE_URL": "https://api.deepseek.com",
        "OPSPILOT_MODEL_CONFIG_VERSION": "offline-user-demo-config-v1",
        "OPSPILOT_MODEL_PRICE_VERSION": "offline-user-demo-price-v1",
        "OPSPILOT_ASSISTANT_SERVICE_IDENTITY": "offline-user-demo-service",
        "OPSPILOT_MODEL_INPUT_RATE_MICRO_PER_MILLION": "300000",
        "OPSPILOT_MODEL_OUTPUT_RATE_MICRO_PER_MILLION": "1200000",
        "OPSPILOT_ASSISTANT_EXPERIMENT_ID": "",
    }
    values.update(overrides)
    return values


def _new_demo(tmp_path: Path) -> Path:
    return initialize_user_demo(tmp_path / "isolated" / ".runtime" / "user-demo")


def _create_grant(db_path: Path, monkeypatch, values=None, *, budget="5.00"):
    monkeypatch.setattr(runtime_admin, "_services_are_stopped", lambda: True)
    config = values or _values()
    expiry = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat().replace("+00:00", "Z")
    micro = runtime_admin._money_to_micro(budget)
    return runtime_admin.provision_user_demo_grant(
        db_path, config, budget_usd=budget, expires_at=expiry,
        confirmation=runtime_admin._confirmation_text(micro),
    )


def test_live_grant_requires_explicit_confirmation_and_preflight_uses_persisted_grant(
    tmp_path, monkeypatch,
):
    from opspilot.domain.assistant_runtime_grant import RuntimeGrantError
    from opspilot.domain.database import connect

    db_path = _new_demo(tmp_path)
    values = _values()
    monkeypatch.setattr(runtime_admin, "_services_are_stopped", lambda: True)
    expiry = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat().replace("+00:00", "Z")
    budget = "5.00"
    with pytest.raises(runtime_admin.UserDemoRuntimeError, match="USER_DEMO_GRANT_CONFIRMATION_MISMATCH"):
        runtime_admin.provision_user_demo_grant(
            db_path, values, budget_usd=budget, expires_at=expiry,
            confirmation="AUTHORIZE REAL DEEPSEEK SPENDING UP TO USD 0.000001",
        )
    with connect(db_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM assistant_runtime_authority").fetchone()[0] == 0

    grant = _create_grant(db_path, monkeypatch, values, budget=budget)
    assert grant["status"] == "ACTIVE"
    preflight = runtime_admin.preflight(db_path, values)
    assert preflight["status"] == "ACTIVE"
    assert preflight["model_id"] == "deepseek-flash"
    assert preflight["total_limit_usd_micro"] == 5_000_000
    assert preflight["remaining_usd_micro"] == 5_000_000
    assert preflight["one_max_request_reserve_usd_micro"] > 0
    with pytest.raises(runtime_admin.UserDemoRuntimeError, match="USER_DEMO_RUNTIME_STATE_ALREADY_EXISTS"):
        _create_grant(db_path, monkeypatch, values, budget="6.00")

    with connect(db_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM assistant_runtime_authority").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM assistant_runtime_audit WHERE action='PROVISION'").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM assistant_runtime_campaigns").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM assistant_runtime_spends").fetchone()[0] == 0


def test_live_preflight_fails_closed_for_missing_key_stale_config_revoked_and_expired_grants(
    tmp_path, monkeypatch,
):
    from opspilot.domain.assistant_runtime_grant import RuntimeGrantError
    from opspilot.domain.database import connect

    db_path = _new_demo(tmp_path)
    values = _values()
    with pytest.raises(RuntimeGrantError, match="RUNTIME_GRANT_NOT_PROVISIONED"):
        runtime_admin.preflight(db_path, values)
    with pytest.raises(runtime_admin.UserDemoRuntimeError, match="USER_DEMO_LIVE_CONFIG_MISSING"):
        runtime_admin.preflight(db_path, _values(OPSPILOT_MODEL_API_KEY=""))

    _create_grant(db_path, monkeypatch, values)
    with pytest.raises(RuntimeGrantError, match="RUNTIME_PROVIDER_CONFIGURATION_STALE"):
        runtime_admin.preflight(
            db_path, _values(OPSPILOT_MODEL_PRICE_VERSION="offline-user-demo-price-v2")
        )
    with connect(db_path) as connection:
        assert connection.execute(
            "SELECT status FROM assistant_runtime_pools WHERE pool_id='DEFAULT'"
        ).fetchone()[0] == "PAUSED"

    db_path = _new_demo(tmp_path / "revoked")
    _create_grant(db_path, monkeypatch, values)
    with connect(db_path) as connection:
        connection.execute(
            "UPDATE assistant_runtime_default_grant SET status='REVOKED' WHERE singleton=1"
        )
    with pytest.raises(RuntimeGrantError, match="RUNTIME_GRANT_REVOKED"):
        runtime_admin.preflight(db_path, values)

    db_path = _new_demo(tmp_path / "expired")
    _create_grant(db_path, monkeypatch, values)
    with connect(db_path) as connection:
        connection.execute(
            "UPDATE assistant_runtime_default_grant SET expires_at='2000-01-01T00:00:00Z' WHERE singleton=1"
        )
    with pytest.raises(RuntimeGrantError, match="RUNTIME_GRANT_EXPIRED_OR_NOT_YET_VALID"):
        runtime_admin.preflight(db_path, values)


def test_live_grant_rejects_budget_below_one_max_request_and_summary_handles_unconfigured_pool(
    tmp_path, monkeypatch, capsys,
):
    from opspilot.domain.database import connect

    db_path = _new_demo(tmp_path)
    monkeypatch.setattr(runtime_admin, "_services_are_stopped", lambda: True)
    values = _values()
    expiry = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat().replace("+00:00", "Z")
    budget = "0.000001"
    with pytest.raises(runtime_admin.UserDemoRuntimeError, match="USER_DEMO_BUDGET_BELOW_ONE_MAX_REQUEST_RESERVE"):
        runtime_admin.provision_user_demo_grant(
            db_path, values, budget_usd=budget, expires_at=expiry,
            confirmation=runtime_admin._confirmation_text(runtime_admin._money_to_micro(budget)),
        )
    with connect(db_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM assistant_runtime_authority").fetchone()[0] == 0

    monkeypatch.setattr(runtime_admin, "DB_PATH", db_path)
    runtime_admin._print_summary()
    assert "Runtime Grant not configured" in capsys.readouterr().out


def test_runtime_admin_summary_uses_selected_isolated_database(tmp_path, monkeypatch, capsys):
    selected_root = tmp_path / "repo"
    runtime_dir = selected_root / ".runtime" / "user-demo-r2-e07"
    selected_db = initialize_user_demo(runtime_dir, require_absent_directory=True)
    monkeypatch.setattr(runtime_admin, "ROOT", selected_root)

    assert runtime_admin.main(["summary", "--runtime-name", "user-demo-r2-e07"]) == 0
    output = capsys.readouterr().out
    assert "Selected runtime: user-demo-r2-e07" in output
    assert ".runtime/user-demo-r2-e07/domain.sqlite3" in output
    assert "Runtime Grant not configured" in output
    assert selected_db.is_file()


def test_runtime_admin_refuses_unlisted_or_path_like_runtime_name(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(runtime_admin, "ROOT", tmp_path / "repo")
    assert runtime_admin.main(["summary", "--runtime-name", "../outside"]) == 2
    output = capsys.readouterr()
    assert "RUNTIME_NAME_INVALID" in output.err
    assert "outside" not in output.err


def test_runtime_admin_preflight_uses_selected_database_without_provisioning(tmp_path, monkeypatch, capsys):
    from opspilot.domain.database import connect

    selected_root = tmp_path / "repo"
    runtime_dir = selected_root / ".runtime" / "user-demo-r2-preflight"
    db_path = initialize_user_demo(runtime_dir, require_absent_directory=True)
    monkeypatch.setattr(runtime_admin, "ROOT", selected_root)
    monkeypatch.setattr(runtime_admin, "read_env", lambda: _values())

    assert runtime_admin.main(["preflight", "--runtime-name", "user-demo-r2-preflight"]) == 2
    output = capsys.readouterr().err
    assert "RUNTIME_GRANT_NOT_PROVISIONED" in output
    with connect(db_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM assistant_runtime_authority").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM assistant_runtime_pools").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM assistant_runtime_spends").fetchone()[0] == 0


def test_stopped_check_observes_custom_runtime_manifest(tmp_path, monkeypatch):
    root = tmp_path / "repo"
    manifest = root / ".runtime" / "user-demo-r2-e07" / "processes.json"
    manifest.parent.mkdir(parents=True)
    manifest.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(runtime_admin, "ROOT", root)
    assert runtime_admin._services_are_stopped() is False
