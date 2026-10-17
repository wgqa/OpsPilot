from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from opspilot.domain.client import probe_orders
from opspilot.domain.database import get_integration_info, reset_fixture
from opspilot.domain.test_fixtures import fixture_only_switch_ref


def test_s1_pos_real_business_api_401_then_200(demo_db: Path, live_api: str) -> None:
    before = probe_orders(demo_db, live_api)
    assert before.status_code == 401
    assert before.credential_ref == "cred-v1"
    assert before.config_version == 7

    updated_version = fixture_only_switch_ref(demo_db, "tenant-a", "integration-a", "cred-v2")
    after = probe_orders(demo_db, live_api)
    assert after.status_code == 200
    assert after.body["order_id"] == "demo-order"
    assert after.body["status"] == "CONFIRMED"
    assert after.integration_id == before.integration_id == "integration-a"
    assert after.principal_id == before.principal_id == "principal-a"
    assert after.route == before.route == "/api/orders/demo-order"
    assert after.credential_ref == "cred-v2"
    assert after.config_version == updated_version == 8

    current = get_integration_info(demo_db, "tenant-a", "integration-a")
    assert current["principal_status"] == "ENABLED"
    with sqlite3.connect(demo_db) as connection:
        events = connection.execute("SELECT result_code FROM auth_events ORDER BY event_id").fetchall()
    assert events == [("AUTH_REJECTED",), ("AUTH_ACCEPTED",)]
    evidence_text = json.dumps([before.public_dict(), after.public_dict(), events])
    assert "fixture-a-old-secret" not in evidence_text
    assert "fixture-a-current-secret" not in evidence_text


def test_s1_disabled_stays_401_after_fixture_credential_switch(
    demo_db: Path, live_api: str
) -> None:
    reset_fixture(demo_db, "S1_DISABLED")
    before = probe_orders(demo_db, live_api)
    assert before.status_code == 401
    assert before.config_version == 7

    fixture_only_switch_ref(demo_db, "tenant-a", "integration-a", "cred-v2")
    after = probe_orders(demo_db, live_api)
    assert after.status_code == 401
    assert after.body["error"] == "UNAUTHORIZED"
    assert after.integration_id == before.integration_id
    assert after.principal_id == before.principal_id == "principal-a"
    assert after.route == before.route == "/api/orders/demo-order"
    assert after.config_version == 8
    assert get_integration_info(demo_db, "tenant-a", "integration-a")["principal_status"] == "DISABLED"
    with sqlite3.connect(demo_db) as connection:
        events = connection.execute("SELECT result_code FROM auth_events ORDER BY event_id").fetchall()
    assert events == [("AUTH_REJECTED",), ("AUTH_REJECTED",)]


def test_fixture_switch_is_not_an_agent_side_effect_and_rejects_other_refs(
    demo_db: Path,
) -> None:
    with pytest.raises(ValueError, match="only allows"):
        fixture_only_switch_ref(demo_db, "tenant-a", "integration-a", "cred-v1")
    assert get_integration_info(demo_db, "tenant-a", "integration-a")["config_version"] == 7


def test_business_api_and_probe_reject_non_loopback_targets(demo_db: Path) -> None:
    with pytest.raises(ValueError, match="loopback"):
        probe_orders(demo_db, "http://example.com")
