from __future__ import annotations

import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "user-demo"))

from initialize_demo import initialize_user_demo  # noqa: E402


def test_user_demo_initialization_seeds_isolated_profiles_once_and_refuses_reset(tmp_path):
    from opspilot.domain.database import connect

    runtime = tmp_path / ".runtime" / "user-demo"
    db_path = initialize_user_demo(runtime)
    assert db_path == runtime / "domain.sqlite3"
    checkpoint_path = runtime / "checkpoint.sqlite3"
    assert db_path.is_file()
    assert checkpoint_path.is_file()
    from sqlite3 import connect as connect_sqlite
    with connect_sqlite(checkpoint_path) as checkpoint_connection:
        checkpoint_tables = {
            row[0] for row in checkpoint_connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
    assert {"checkpoints", "writes"} <= checkpoint_tables

    with connect(db_path) as connection:
        s1 = connection.execute(
            "SELECT i.credential_ref,a.accepted_credential_ref "
            "FROM integrations i JOIN auth_policies a ON a.tenant_id=i.tenant_id "
            "AND a.service_id='orders-demo' WHERE i.tenant_id='tenant-a' AND i.integration_id='integration-a'"
        ).fetchone()
        s2 = connection.execute(
            "SELECT i.credential_ref,a.accepted_credential_ref,g.granted_scopes_json "
            "FROM integrations i JOIN auth_policies a ON a.tenant_id=i.tenant_id "
            "AND a.service_id='orders-demo-s2' JOIN principal_scope_grants g "
            "ON g.tenant_id=i.tenant_id AND g.principal_id=i.principal_id "
            "WHERE i.tenant_id='tenant-a' AND i.integration_id='integration-s2-a'"
        ).fetchone()
        s3 = connection.execute(
            "SELECT d.status AS delivery_status,r.status AS receiver_status,"
            "d.event_id AS delivery_event_id,r.event_id AS receiver_event_id "
            "FROM s3_deliveries d JOIN s3_receivers r ON r.tenant_id=d.tenant_id "
            "AND r.service_id=d.service_id AND r.order_id=d.order_id "
            "WHERE d.tenant_id='tenant-a' AND d.order_id='async-order'"
        ).fetchone()
        assert s1["credential_ref"] == "cred-v1" and s1["accepted_credential_ref"] == "cred-v2"
        assert s2["credential_ref"] == s2["accepted_credential_ref"] == "cred-v2"
        assert s2["granted_scopes_json"] == "[]"
        assert s3["delivery_status"] == "ACKNOWLEDGED"
        assert s3["receiver_status"] == "QUEUED"
        assert s3["delivery_event_id"] == s3["receiver_event_id"]
        for table in (
            "assistant_runtime_authority", "assistant_runtime_pools",
            "assistant_runtime_default_grant", "assistant_runtime_spends",
            "assistant_runtime_campaigns",
        ):
            assert connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0

    with pytest.raises(FileExistsError, match="will not reset"):
        initialize_user_demo(runtime)
    with connect(db_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM sessions").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM tenants").fetchone()[0] == 2
