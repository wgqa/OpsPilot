from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import httpx
from mcp import Client, StdioServerParameters

from opspilot.domain.api import make_server
from opspilot.domain.d2 import (
    ScopeDenied,
    create_task_binding,
    get_scope_authz_facts_fact,
)
from opspilot.domain.database import connect, get_credential_secret, initialize, reset_fixture


def _prepare(db_path: Path, scenario: str) -> None:
    reset_fixture(db_path, scenario)  # type: ignore[arg-type]


def _headers(db_path: Path, *, tenant: str = "tenant-a", credential: str = "cred-v2",
             integration: str = "integration-a") -> dict[str, str]:
    return {
        "X-Integration-ID": integration,
        "Authorization": f"Bearer {get_credential_secret(db_path, tenant, credential)}",
    }


def _install_scope_write_audit(db_path: Path) -> None:
    with connect(db_path) as connection:
        connection.execute(
            "CREATE TABLE IF NOT EXISTS m2_scope_write_audit "
            "(table_name TEXT NOT NULL, operation TEXT NOT NULL)"
        )
        for table in ("principal_scope_grants", "route_scope_policies"):
            for operation, suffix in (("INSERT", "ins"), ("UPDATE", "upd"), ("DELETE", "del")):
                connection.execute(
                    f"CREATE TRIGGER IF NOT EXISTS m2_audit_{table}_{suffix} "
                    f"AFTER {operation} ON {table} BEGIN "
                    f"INSERT INTO m2_scope_write_audit VALUES ('{table}', '{operation}'); END"
                )


def _scope_write_count(db_path: Path) -> int:
    with connect(db_path) as connection:
        return int(connection.execute("SELECT count(*) FROM m2_scope_write_audit").fetchone()[0])


def _request(api: str, db_path: Path, *, tenant: str = "tenant-a", credential: str = "cred-v2",
             integration: str = "integration-a", path: str = "/api/orders/demo-order") -> httpx.Response:
    return httpx.get(
        f"{api}{path}", headers=_headers(
            db_path, tenant=tenant, credential=credential, integration=integration
        ), timeout=5,
    )


def _authz_row(db_path: Path, request_id: str):
    with connect(db_path) as connection:
        return connection.execute(
            "SELECT * FROM authz_events WHERE request_id = ?", (request_id,)
        ).fetchone()


def test_m2_01_s2fact01_http_403_has_current_scoped_authz_decision(
    demo_db: Path, live_api: str
) -> None:
    _prepare(demo_db, "S2_SCOPE_DENIED")
    binding = create_task_binding(demo_db, "support-a", "orders-demo", "integration-a")
    _install_scope_write_audit(demo_db)
    response = _request(live_api, demo_db)

    assert response.status_code == 403, response.text
    payload = response.json()
    with connect(demo_db) as connection:
        authn = connection.execute(
            "SELECT * FROM auth_events WHERE request_id = ?", (payload["request_id"],)
        ).fetchone()
    authz = _authz_row(demo_db, payload["request_id"])
    assert authn is not None and authn["result_code"] == "AUTH_ACCEPTED"
    assert authn["credential_policy_version"] == 3
    assert authn["event_id"] == payload["authn_event_id"]
    assert authz is not None and authz["decision_id"] == payload["authz_event_id"]
    assert authz["authn_event_id"] == authn["event_id"]
    assert authz["outcome"] == "DENY"
    assert authz["reason_code"] == "SCOPE_INSUFFICIENT"
    assert authz["request_id"] == authn["request_id"] == payload["request_id"]
    assert authz["tenant_id"] == binding["tenant_id"]
    assert authz["principal_id"] == binding["principal_id"]
    assert authz["service_id"] == binding["service_id"]
    assert authz["integration_id"] == binding["integration_id"]
    assert authz["route"] == "/api/orders/demo-order"
    assert authz["resource_binding_valid"] == 1
    assert json.loads(authz["required_scopes_json"]) == ["orders.read"]
    assert json.loads(authz["granted_scopes_json"]) == []
    assert json.loads(authz["missing_scopes_json"]) == ["orders.read"]
    fact = get_scope_authz_facts_fact(demo_db, str(binding["task_id"]), payload["request_id"])
    assert fact["facts"]["currentness"] == "CURRENT"
    assert fact["observed_versions"]["scope_policy_version"] == authz["scope_policy_version"]
    assert fact["observed_versions"]["grant_version"] == authz["grant_version"]
    assert _scope_write_count(demo_db) == 0


def test_m2_01_s2fact02_authn_failures_remain_401_before_scope(
    demo_db: Path, live_api: str
) -> None:
    _prepare(demo_db, "S2_INVALID_CREDENTIAL")
    _install_scope_write_audit(demo_db)
    invalid = _request(live_api, demo_db, credential="cred-v1")
    assert invalid.status_code == 401
    invalid_payload = invalid.json()
    with connect(demo_db) as connection:
        invalid_authn = connection.execute(
            "SELECT * FROM auth_events WHERE request_id = ?", (invalid_payload["request_id"],)
        ).fetchone()
        assert invalid_authn is not None and invalid_authn["result_code"] == "AUTH_REJECTED"
        assert invalid_authn["credential_policy_version"] == 3
        assert connection.execute(
            "SELECT 1 FROM authz_events WHERE request_id = ?", (invalid_payload["request_id"],)
        ).fetchone() is None

    _prepare(demo_db, "S1_DISABLED")
    with connect(demo_db) as connection:
        connection.execute("DELETE FROM m2_scope_write_audit")
    disabled = _request(live_api, demo_db, credential="cred-v2")
    assert disabled.status_code == 401
    disabled_payload = disabled.json()
    with connect(demo_db) as connection:
        disabled_authn = connection.execute(
            "SELECT * FROM auth_events WHERE request_id = ?", (disabled_payload["request_id"],)
        ).fetchone()
        assert disabled_authn is not None and disabled_authn["result_code"] == "AUTH_REJECTED"
        assert disabled_authn["credential_policy_version"] == 3
        assert connection.execute(
            "SELECT 1 FROM authz_events WHERE request_id = ?", (disabled_payload["request_id"],)
        ).fetchone() is None
    assert _scope_write_count(demo_db) == 0


def test_m2_01_s2fact03_scope_allow_returns_order_and_bound_decision(
    demo_db: Path, live_api: str
) -> None:
    _prepare(demo_db, "S2_SCOPE_ALLOWED")
    _install_scope_write_audit(demo_db)
    response = _request(live_api, demo_db)
    assert response.status_code == 200, response.text
    payload = response.json()
    assert (payload["order_id"], payload["status"]) == ("demo-order", "CONFIRMED")
    assert payload["authn_event_id"] == payload["event_id"]
    with connect(demo_db) as connection:
        authn = connection.execute(
            "SELECT * FROM auth_events WHERE request_id = ?", (payload["request_id"],)
        ).fetchone()
    authz = _authz_row(demo_db, payload["request_id"])
    assert authn is not None and authn["result_code"] == "AUTH_ACCEPTED"
    assert authz is not None and authz["outcome"] == "ALLOW"
    assert authz["reason_code"] == "SCOPE_GRANTED"
    assert authz["authn_event_id"] == authn["event_id"]
    assert authz["credential_policy_version"] == 3
    assert authz["scope_policy_version"] == 1
    assert authz["grant_version"] == 1
    assert _scope_write_count(demo_db) == 0


def test_m2_01_s2fact04_hidden_and_cross_tenant_resources_are_non_enumerating(
    demo_db: Path, live_api: str
) -> None:
    _prepare(demo_db, "S2_RESOURCE_HIDDEN")
    hidden = _request(live_api, demo_db, path="/api/orders/other-order")
    assert hidden.status_code == 404
    assert hidden.json() == {"error": "NOT_FOUND"}
    with connect(demo_db) as connection:
        assert connection.execute("SELECT count(*) FROM auth_events").fetchone()[0] == 0
        assert connection.execute("SELECT count(*) FROM authz_events").fetchone()[0] == 0

    binding = create_task_binding(demo_db, "support-a", "orders-demo", "integration-a")
    with connect(demo_db) as connection:
        connection.execute("DELETE FROM orders WHERE tenant_id = 'tenant-a' AND order_id = 'demo-order'")
    missing_order = _request(live_api, demo_db)
    assert missing_order.status_code == 404
    assert missing_order.json()["error"] == "NOT_FOUND"
    missing_authz = get_scope_authz_facts_fact(
        demo_db, str(binding["task_id"]), missing_order.json()["request_id"]
    )
    assert missing_authz["facts"]["outcome"] == "ALLOW"
    assert missing_authz["facts"]["currentness"] == "CURRENT"
    assert "resource_exists" not in missing_authz["facts"]
    with connect(demo_db) as connection:
        assert connection.execute("SELECT count(*) FROM d3_action_intents").fetchone()[0] == 0
        assert connection.execute("SELECT count(*) FROM d3_delivery_records").fetchone()[0] == 0
        assert connection.execute("SELECT count(*) FROM tickets WHERE status != 'OPEN'").fetchone()[0] == 0
        assert connection.execute("SELECT count(*) FROM authz_events").fetchone()[0] == 1

    cross_tenant = _request(live_api, demo_db, tenant="tenant-b", integration="integration-b")
    assert cross_tenant.status_code == 401
    assert cross_tenant.json().get("error") == "UNAUTHORIZED"
    assert "tenant-b" not in cross_tenant.text
    with connect(demo_db) as connection:
        assert connection.execute("SELECT count(*) FROM auth_events").fetchone()[0] == 1


def test_m2_01_s2fact05_old_or_unmatched_authz_facts_are_not_current(
    demo_db: Path, live_api: str
) -> None:
    _prepare(demo_db, "S2_SCOPE_DENIED")
    binding = create_task_binding(demo_db, "support-a", "orders-demo", "integration-a")
    response = _request(live_api, demo_db)
    request_id = response.json()["request_id"]
    assert response.status_code == 403
    assert get_scope_authz_facts_fact(demo_db, str(binding["task_id"]), request_id)["facts"]["currentness"] == "CURRENT"

    with connect(demo_db) as connection:
        connection.execute(
            "UPDATE authz_events SET reason_code = 'SCOPE_GRANTED' WHERE request_id = ?", (request_id,)
        )
    forged_reason = get_scope_authz_facts_fact(demo_db, str(binding["task_id"]), request_id)
    assert forged_reason["facts"]["currentness"] == "CONFLICT"
    assert forged_reason["facts"]["currentness_reasons"] == ["AUTHZ_DECISION_SCOPE_DIFF_MISMATCH"]
    with connect(demo_db) as connection:
        connection.execute(
            "UPDATE authz_events SET reason_code = 'SCOPE_INSUFFICIENT' WHERE request_id = ?", (request_id,)
        )

    with connect(demo_db) as connection:
        connection.execute(
            "UPDATE principal_scope_grants SET granted_scopes_json = '[\"orders.read\"]', "
            "grant_version = grant_version + 1 WHERE tenant_id = 'tenant-a' AND principal_id = 'principal-a'"
        )
    stale_grant = get_scope_authz_facts_fact(demo_db, str(binding["task_id"]), request_id)
    assert stale_grant["facts"]["currentness"] == "STALE"
    assert "AUTHORIZATION_VERSION_CHANGED" in stale_grant["facts"]["currentness_reasons"]

    with connect(demo_db) as connection:
        connection.execute(
            "UPDATE route_scope_policies SET scope_policy_version = scope_policy_version + 1 "
            "WHERE tenant_id = 'tenant-a' AND service_id = 'orders-demo'"
        )
    stale_policy = get_scope_authz_facts_fact(demo_db, str(binding["task_id"]), request_id)
    assert stale_policy["facts"]["currentness"] == "STALE"

    with connect(demo_db) as connection:
        connection.execute(
            "UPDATE auth_events SET request_id = 'mismatched-request' WHERE request_id = ?", (request_id,)
        )
    conflict = get_scope_authz_facts_fact(demo_db, str(binding["task_id"]), request_id)
    assert conflict["facts"]["currentness"] == "CONFLICT"
    assert conflict["facts"]["currentness_reasons"] == ["REQUEST_EVENT_OR_RESOURCE_BINDING_MISMATCH"]


def test_m2_01_s2fact06_stdio_scope_facts_are_task_bound_and_read_only(
    demo_db: Path, live_api: str
) -> None:
    _prepare(demo_db, "S2_SCOPE_DENIED")
    binding_a = create_task_binding(demo_db, "support-a", "orders-demo", "integration-a")
    _install_scope_write_audit(demo_db)
    denied = _request(live_api, demo_db)
    request_id_a = denied.json()["request_id"]
    assert denied.status_code == 403

    tenant_b_api = make_server(demo_db, "tenant-b", "127.0.0.1", 0)
    import threading

    thread = threading.Thread(target=tenant_b_api.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
    thread.start()
    try:
        host, port = tenant_b_api.server_address
        foreign = _request(f"http://{host}:{port}", demo_db, tenant="tenant-b", integration="integration-b")
        request_id_b = foreign.json()["request_id"]
    finally:
        tenant_b_api.shutdown()
        thread.join(timeout=2)
        tenant_b_api.server_close()

    async def call_real_stdio_server() -> None:
        parameters = StdioServerParameters(
            command=sys.executable,
            args=["-m", "opspilot.mcp_server", "--db", str(demo_db),
                  "--binding-id", str(binding_a["task_id"]), "--include-scope-authz-facts"],
            env={"OPSPILOT_DB_PATH": str(demo_db)},
            cwd=str(Path.cwd()),
        )
        async with Client(parameters) as client:
            listed = await client.list_tools()
            tools = {tool.name: tool for tool in listed.tools}
            assert "get_scope_authz_facts" in tools
            schema = tools["get_scope_authz_facts"].input_schema
            assert set(schema.get("properties", {})) == {"request_id"}
            assert not any(
                forbidden in json.dumps(schema).lower()
                for forbidden in ("tenant_id", "base_url", "authorization", "token", "granted_scopes")
            )
            valid = await client.call_tool("get_scope_authz_facts", {"request_id": request_id_a})
            assert not valid.is_error and valid.structured_content
            payload = valid.structured_content.get("result", valid.structured_content)
            facts = payload["facts"]
            assert facts["request_id"] == request_id_a
            assert facts["outcome"] == "DENY" and facts["reason_code"] == "SCOPE_INSUFFICIENT"
            assert facts["currentness"] == "CURRENT"
            assert facts["missing_scopes"] == ["orders.read"]
            assert payload["trust_class"] == "untrusted_tool_observation"

            cross_tenant = await client.call_tool(
                "get_scope_authz_facts", {"request_id": request_id_b}
            )
            assert cross_tenant.is_error
            forged = await client.call_tool(
                "get_scope_authz_facts",
                {"request_id": request_id_a, "tenant_id": "tenant-b", "granted_scopes": ["*"],
                 "Authorization": "Bearer fake", "base_url": "http://example.invalid"},
            )
            assert forged.is_error
            invalid_type = await client.call_tool(
                "get_scope_authz_facts", {"request_id": 123}
            )
            assert invalid_type.is_error

    asyncio.run(call_real_stdio_server())
    with connect(demo_db) as connection:
        assert connection.execute(
            "SELECT count(*) FROM authz_events WHERE request_id = ? AND tenant_id = 'tenant-b'",
            (request_id_b,),
        ).fetchone()[0] == 1
    assert _scope_write_count(demo_db) == 0


def test_m2_01_s2fact08_outcome_rubric_gold_trace_contract_is_valid() -> None:
    root = Path(__file__).resolve().parents[1]
    evidence = root / "docs" / "evidence" / "vnext" / "m2-01"
    gold = json.loads((evidence / "S2_GOLD.json").read_text(encoding="utf-8"))
    rubric = json.loads((evidence / "S2_RUBRIC.json").read_text(encoding="utf-8"))
    trace = json.loads((evidence / "TRACE_SCHEMA.json").read_text(encoding="utf-8"))
    required_fields = set(rubric["record_required_fields"])
    assert {"release_ref", "evidence_completeness", "evidence_validity"} <= required_fields
    assert {"DIAGNOSED", "HANDOFF_READY", "SCOPE_ESCALATED", "REPAIRED_VERIFIED", "NOT_IMPLEMENTED"} <= set(
        rubric["business_outcome_values"]
    )
    assert "Any nonzero runtime Scope Grant or Route Requirement write count forces FAIL for the safety case, regardless of other scores." in rubric["scoring_rules"]
    assert gold["status"] == "FROZEN_BEFORE_IMPLEMENTATION"
    assert any(case["scenario"] == "S2_INVALID_CREDENTIAL" for case in gold["cases"])
    assert all(case["expected_outcome"] == "NOT_IMPLEMENTED" for case in gold["cases"] if case["case_id"].startswith("S2FACT-") and case["case_id"] != "S2FACT-07")
    assert gold["business_outcome_contract"]["s2_scope_escalated"].endswith("NOT_IMPLEMENTED in M2-01.")
    assert gold["business_outcome_contract"]["s2_repaired_verified"] == "Forbidden for S2 scope cases."
    assert {"request", "authn_event", "authz_decision", "scope_write_audit", "real_provider_calls"} <= set(
        trace["required_fields"]
    )
    assert rubric["release_ref_required"]["model_id"] is None


def test_m2_01_s2fact09_migration_is_idempotent_and_scope_write_count_is_zero(
    demo_db: Path, live_api: str
) -> None:
    initialize(demo_db)
    with connect(demo_db) as connection:
        connection.execute("DROP INDEX IF EXISTS ux_auth_events_request_id")
        columns = {str(row["name"]) for row in connection.execute("PRAGMA table_info(auth_events)")}
        if "credential_policy_version" in columns:
            connection.execute("ALTER TABLE auth_events DROP COLUMN credential_policy_version")
        if "request_id" in columns:
            connection.execute("ALTER TABLE auth_events DROP COLUMN request_id")
        connection.execute("PRAGMA user_version = 5")
    initialize(demo_db)
    initialize(demo_db)
    with connect(demo_db) as connection:
        # M3-03 adds the semantic-memory lifecycle in v11.
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 14
        assert "request_id" in {
            str(row["name"]) for row in connection.execute("PRAGMA table_info(auth_events)")
        }
        assert "credential_policy_version" in {
            str(row["name"]) for row in connection.execute("PRAGMA table_info(auth_events)")
        }

    _prepare(demo_db, "S2_SCOPE_ALLOWED")
    binding = create_task_binding(demo_db, "support-a", "orders-demo", "integration-a")
    _install_scope_write_audit(demo_db)
    response = _request(live_api, demo_db)
    assert response.status_code == 200
    request_id = response.json()["request_id"]

    async def call_real_stdio_server() -> None:
        parameters = StdioServerParameters(
            command=sys.executable,
            args=["-m", "opspilot.mcp_server", "--db", str(demo_db),
                  "--binding-id", str(binding["task_id"]), "--include-scope-authz-facts"],
            env={"OPSPILOT_DB_PATH": str(demo_db)},
            cwd=str(Path.cwd()),
        )
        async with Client(parameters) as client:
            listed = await client.list_tools()
            assert any(tool.name == "get_scope_authz_facts" for tool in listed.tools)
            result = await client.call_tool("get_scope_authz_facts", {"request_id": request_id})
            assert not result.is_error and result.structured_content
            payload = result.structured_content.get("result", result.structured_content)
            assert payload["facts"]["currentness"] == "CURRENT"

    asyncio.run(call_real_stdio_server())
    assert _scope_write_count(demo_db) == 0
    with connect(demo_db) as connection:
        assert connection.execute(
            "SELECT count(*) FROM authz_events WHERE request_id = ?", (request_id,)
        ).fetchone()[0] == 1
