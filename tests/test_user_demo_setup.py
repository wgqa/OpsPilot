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


@pytest.mark.parametrize(
    ("profile", "target_event", "target_status", "decoy_event"),
    [
        ("r2-e07-queued", "event-00000000-0000-4000-8000-000000000001", "QUEUED", None),
        ("r2-e08-processed-decoy", "event-00000000-0000-4000-8000-000000000101", "PROCESSED",
         "event-00000000-0000-4000-8000-000000000102"),
    ],
)
def test_r2_s3_profiles_have_isolated_expected_same_event_facts(
    tmp_path, profile, target_event, target_status, decoy_event,
):
    from opspilot.domain.database import connect

    runtime = tmp_path / ".runtime" / f"user-demo-{profile}"
    db_path = initialize_user_demo(runtime, require_absent_directory=True, s3_fixture_profile=profile)
    checkpoint_path = runtime / "checkpoint.sqlite3"
    assert db_path.is_file() and checkpoint_path.is_file()
    with connect(db_path) as connection:
        target = connection.execute(
            "SELECT d.event_id AS delivery_event_id,r.event_id AS receiver_event_id,"
            "d.status AS delivery_status,r.status AS receiver_status "
            "FROM s3_deliveries d JOIN s3_receivers r ON r.tenant_id=d.tenant_id "
            "AND r.service_id=d.service_id AND r.order_id=d.order_id "
            "WHERE d.tenant_id='tenant-a' AND d.order_id='async-order'"
        ).fetchone()
        assert target["delivery_event_id"] == target["receiver_event_id"] == target_event
        assert target["delivery_status"] == "ACKNOWLEDGED"
        assert target["receiver_status"] == target_status
        assert connection.execute("SELECT COUNT(*) FROM sessions").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM messages").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM task_bindings").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM task_runs").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM personal_memories").fetchone()[0] == 0
        for table in (
            "assistant_runtime_authority", "assistant_runtime_pools",
            "assistant_runtime_default_grant", "assistant_runtime_spends",
            "assistant_runtime_campaigns",
        ):
            assert connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0
        if decoy_event:
            decoy = connection.execute(
                "SELECT d.event_id AS delivery_event_id,r.event_id AS receiver_event_id,"
                "d.status AS delivery_status,r.status AS receiver_status "
                "FROM s3_deliveries d JOIN s3_receivers r ON r.tenant_id=d.tenant_id "
                "AND r.service_id=d.service_id AND r.order_id=d.order_id "
                "WHERE d.tenant_id='tenant-a' AND d.order_id='async-order-decoy'"
            ).fetchone()
            assert decoy["delivery_event_id"] == decoy["receiver_event_id"] == decoy_event
            assert decoy["delivery_status"] == "ACKNOWLEDGED"
            assert decoy["receiver_status"] == "QUEUED"

    before = db_path.read_bytes()
    with pytest.raises(FileExistsError, match="directory already exists"):
        initialize_user_demo(runtime, require_absent_directory=True, s3_fixture_profile=profile)
    assert db_path.read_bytes() == before


@pytest.mark.parametrize("profile", ["r2-e07-queued", "r2-e08-processed-decoy"])
def test_r2_s3_profiles_allow_support_to_bind_target_through_assistant_api(tmp_path, profile):
    from fastapi.testclient import TestClient

    from opspilot.domain.database import connect
    from opspilot.domain.s3 import get_s3_binding, list_s3_order_resources
    from opspilot.domain.task_control import trusted_identity
    from opspilot.web.app import create_app

    runtime = tmp_path / ".runtime" / f"user-demo-{profile}-api"
    db_path = initialize_user_demo(runtime, require_absent_directory=True, s3_fixture_profile=profile)
    checkpoint = runtime / "checkpoint.sqlite3"
    origin = "http://127.0.0.1:5173"
    app = create_app(
        db_path=db_path, checkpoint_db_path=checkpoint, start_worker=False,
        credentials={"support-a": "offline-user-demo-test-password"}, expected_origin=origin,
    )
    with TestClient(app) as client:
        login = client.post(
            "/api/auth/login", headers={"Origin": origin},
            json={"actor_id": "support-a", "password": "offline-user-demo-test-password"},
        )
        assert login.status_code == 200
        headers = {"Origin": origin, "X-CSRF-Token": login.json()["csrf_token"]}
        session = client.post("/api/sessions", headers=headers)
        assert session.status_code == 201
        session_id = session.json()["session_id"]
        catalog = client.get("/api/s3/order-resources", headers={"Origin": origin})
        assert catalog.status_code == 200
        expected_orders = {"async-order"}
        if profile == "r2-e08-processed-decoy":
            expected_orders.add("async-order-decoy")
        assert {item["order_id"] for item in catalog.json()["items"]} == expected_orders

        binding_response = client.post(
            f"/api/sessions/{session_id}/assistant/order",
            headers={**headers, "Idempotency-Key": f"offline-{profile}-binding"},
            json={"order_id": "async-order", "initial_message": "Offline TaskBinding setup only."},
        )
        assert binding_response.status_code == 202, binding_response.text
        task_id = binding_response.json()["task_id"]

    identity = trusted_identity(db_path, "support-a")
    assert identity.role == "SUPPORT"
    with connect(db_path) as connection:
        binding = get_s3_binding(connection, task_id)
        assert binding["order_id"] == "async-order"
        assert binding["tenant_id"] == "tenant-a"
        assert connection.execute("SELECT COUNT(*) FROM assistant_runtime_spends").fetchone()[0] == 0
