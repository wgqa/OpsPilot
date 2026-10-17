from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Literal


Scenario = Literal["S1_POS", "S1_DISABLED"]

SCHEMA = """
CREATE TABLE IF NOT EXISTS tenants (
    tenant_id TEXT PRIMARY KEY
);
CREATE TABLE IF NOT EXISTS credentials (
    tenant_id TEXT NOT NULL REFERENCES tenants(tenant_id),
    credential_ref TEXT NOT NULL,
    secret_value TEXT NOT NULL,
    credential_version INTEGER NOT NULL,
    PRIMARY KEY (tenant_id, credential_ref)
);
CREATE TABLE IF NOT EXISTS principals (
    tenant_id TEXT NOT NULL REFERENCES tenants(tenant_id),
    principal_id TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('ENABLED', 'DISABLED')),
    principal_version INTEGER NOT NULL,
    PRIMARY KEY (tenant_id, principal_id)
);
CREATE TABLE IF NOT EXISTS integrations (
    tenant_id TEXT NOT NULL REFERENCES tenants(tenant_id),
    integration_id TEXT NOT NULL,
    principal_id TEXT NOT NULL,
    credential_ref TEXT NOT NULL,
    config_version INTEGER NOT NULL,
    PRIMARY KEY (tenant_id, integration_id),
    FOREIGN KEY (tenant_id, principal_id)
        REFERENCES principals(tenant_id, principal_id),
    FOREIGN KEY (tenant_id, credential_ref)
        REFERENCES credentials(tenant_id, credential_ref)
);
CREATE TABLE IF NOT EXISTS services (
    tenant_id TEXT NOT NULL REFERENCES tenants(tenant_id),
    service_id TEXT NOT NULL,
    integration_id TEXT NOT NULL,
    route TEXT NOT NULL,
    PRIMARY KEY (tenant_id, service_id),
    FOREIGN KEY (tenant_id, integration_id)
        REFERENCES integrations(tenant_id, integration_id)
);
CREATE TABLE IF NOT EXISTS auth_policies (
    tenant_id TEXT NOT NULL,
    service_id TEXT NOT NULL,
    accepted_credential_ref TEXT NOT NULL,
    policy_version INTEGER NOT NULL,
    PRIMARY KEY (tenant_id, service_id),
    FOREIGN KEY (tenant_id, service_id)
        REFERENCES services(tenant_id, service_id),
    FOREIGN KEY (tenant_id, accepted_credential_ref)
        REFERENCES credentials(tenant_id, credential_ref)
);
CREATE TABLE IF NOT EXISTS orders (
    tenant_id TEXT NOT NULL REFERENCES tenants(tenant_id),
    order_id TEXT NOT NULL,
    status TEXT NOT NULL,
    PRIMARY KEY (tenant_id, order_id)
);
CREATE TABLE IF NOT EXISTS auth_events (
    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id TEXT NOT NULL,
    integration_id TEXT NOT NULL,
    principal_id TEXT NOT NULL,
    service_id TEXT NOT NULL,
    route TEXT NOT NULL,
    result_code TEXT NOT NULL,
    observed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS thread_owners (
    thread_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL REFERENCES tenants(tenant_id),
    owner_id TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS trusted_operators (
    actor_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL REFERENCES tenants(tenant_id),
    role TEXT NOT NULL CHECK (role IN ('SUPPORT', 'APPROVER'))
);
CREATE TABLE IF NOT EXISTS task_bindings (
    task_id TEXT PRIMARY KEY,
    thread_id TEXT NOT NULL UNIQUE,
    tenant_id TEXT NOT NULL REFERENCES tenants(tenant_id),
    actor_id TEXT NOT NULL REFERENCES trusted_operators(actor_id),
    service_id TEXT NOT NULL,
    integration_id TEXT NOT NULL,
    principal_id TEXT NOT NULL,
    ticket_id TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (task_id, tenant_id),
    FOREIGN KEY (tenant_id, service_id) REFERENCES services(tenant_id, service_id),
    FOREIGN KEY (tenant_id, integration_id) REFERENCES integrations(tenant_id, integration_id),
    FOREIGN KEY (tenant_id, principal_id) REFERENCES principals(tenant_id, principal_id)
);
CREATE TABLE IF NOT EXISTS d2_attempts (
    attempt_id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL REFERENCES task_bindings(task_id),
    kind TEXT NOT NULL CHECK (kind IN ('MODEL', 'MCP')),
    call_id TEXT NOT NULL,
    tool_call_id TEXT,
    tool_name TEXT,
    argument_digest TEXT,
    status TEXT NOT NULL DEFAULT 'RESERVED',
    reserved_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at TEXT,
    result_digest TEXT,
    error_class TEXT
);
CREATE INDEX IF NOT EXISTS ix_d2_attempts_task_kind ON d2_attempts(task_id, kind);
CREATE TABLE IF NOT EXISTS d2_model_traces (
    call_id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL REFERENCES task_bindings(task_id),
    attempt_id TEXT NOT NULL REFERENCES d2_attempts(attempt_id),
    model_id TEXT NOT NULL,
    prompt_digest TEXT NOT NULL,
    input_evidence_ids_json TEXT NOT NULL,
    provider_response_id TEXT,
    tool_calls_json TEXT NOT NULL,
    assistant_text TEXT NOT NULL,
    usage_json TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS d2_pending_tool_calls (
    task_id TEXT NOT NULL REFERENCES task_bindings(task_id),
    call_id TEXT NOT NULL REFERENCES d2_model_traces(call_id),
    tool_call_id TEXT NOT NULL,
    tool_name TEXT NOT NULL,
    arguments_json TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'PENDING',
    PRIMARY KEY (task_id, call_id, tool_call_id)
);
CREATE TABLE IF NOT EXISTS d2_tool_observations (
    observation_id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL REFERENCES task_bindings(task_id),
    call_id TEXT NOT NULL,
    attempt_id TEXT,
    tool_call_id TEXT NOT NULL,
    tool_name TEXT NOT NULL,
    argument_digest TEXT NOT NULL,
    status TEXT NOT NULL,
    progress_added INTEGER NOT NULL,
    error_class TEXT,
    result_digest TEXT,
    result_json TEXT,
    evidence_id TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS ix_d2_observations_task ON d2_tool_observations(task_id, created_at);
CREATE TABLE IF NOT EXISTS d2_evidence (
    evidence_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    task_id TEXT NOT NULL REFERENCES task_bindings(task_id),
    call_id TEXT NOT NULL,
    tool_call_id TEXT NOT NULL,
    resource_id TEXT NOT NULL,
    principal_id TEXT,
    data_source TEXT NOT NULL,
    fetched_at TEXT NOT NULL,
    observed_versions_json TEXT NOT NULL,
    fact_type TEXT NOT NULL,
    facts_json TEXT NOT NULL,
    original_result_ref TEXT NOT NULL,
    trust_class TEXT NOT NULL,
    digest TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_d2_evidence_task_fact ON d2_evidence(task_id, fact_type, fetched_at);
CREATE TABLE IF NOT EXISTS d2_reports (
    report_ref TEXT PRIMARY KEY,
    task_id TEXT NOT NULL UNIQUE REFERENCES task_bindings(task_id),
    content_digest TEXT NOT NULL,
    immutable_content_json TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS d2_tool_faults (
    task_id TEXT NOT NULL REFERENCES task_bindings(task_id),
    tool_name TEXT NOT NULL,
    remaining_calls INTEGER NOT NULL,
    error_code TEXT NOT NULL,
    PRIMARY KEY (task_id, tool_name)
);
CREATE TABLE IF NOT EXISTS executor_services (
    executor_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL REFERENCES tenants(tenant_id),
    active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1))
);
CREATE TABLE IF NOT EXISTS tickets (
    tenant_id TEXT NOT NULL REFERENCES tenants(tenant_id),
    ticket_id TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'OPEN',
    PRIMARY KEY (tenant_id, ticket_id)
);
CREATE TABLE IF NOT EXISTS d3_plans (
    plan_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    task_id TEXT NOT NULL REFERENCES task_bindings(task_id),
    plan_version INTEGER NOT NULL,
    plan_hash TEXT NOT NULL,
    plan_signature TEXT NOT NULL,
    canonical_plan_json TEXT NOT NULL,
    created_by TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (tenant_id, task_id, plan_hash),
    UNIQUE (tenant_id, task_id, plan_signature),
    UNIQUE (tenant_id, task_id, plan_version)
);
CREATE TABLE IF NOT EXISTS d3_plan_authorizations (
    plan_hash TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    task_id TEXT NOT NULL,
    eligibility TEXT NOT NULL CHECK (eligibility IN ('ACTIVE', 'SUPERSEDED', 'CANCELLED')),
    generation INTEGER NOT NULL,
    changed_by TEXT,
    change_reason TEXT,
    active_from TEXT NOT NULL,
    changed_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_d3_plan_auth_task ON d3_plan_authorizations(tenant_id, task_id, eligibility);
CREATE TABLE IF NOT EXISTS d3_plan_authorization_history (
    history_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    task_id TEXT NOT NULL,
    plan_hash TEXT NOT NULL,
    eligibility TEXT NOT NULL CHECK (eligibility IN ('ACTIVE', 'SUPERSEDED', 'CANCELLED')),
    generation INTEGER NOT NULL,
    changed_by TEXT,
    change_reason TEXT,
    changed_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS d3_approvals (
    approval_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    task_id TEXT NOT NULL,
    plan_hash TEXT NOT NULL,
    approver_id TEXT NOT NULL,
    approval_scope_json TEXT NOT NULL,
    approved_plan_digest TEXT NOT NULL,
    target_resource_id TEXT NOT NULL,
    environment TEXT NOT NULL,
    action_kinds_json TEXT NOT NULL,
    decision TEXT NOT NULL CHECK (decision IN ('APPROVED', 'REJECTED')),
    decided_at TEXT NOT NULL,
    UNIQUE (tenant_id, task_id, plan_hash)
);
CREATE TABLE IF NOT EXISTS d3_action_permissions (
    tenant_id TEXT NOT NULL,
    task_id TEXT NOT NULL,
    plan_hash TEXT NOT NULL,
    approval_id TEXT NOT NULL REFERENCES d3_approvals(approval_id),
    action_kind TEXT NOT NULL CHECK (action_kind IN ('REPAIR', 'DELIVER')),
    state TEXT NOT NULL CHECK (state IN ('AVAILABLE', 'CONSUMED', 'REVOKED')),
    used_by_action_id TEXT,
    changed_at TEXT NOT NULL,
    PRIMARY KEY (tenant_id, task_id, plan_hash, action_kind)
);
CREATE TABLE IF NOT EXISTS d3_action_intents (
    action_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    task_id TEXT NOT NULL,
    plan_hash TEXT NOT NULL,
    action_kind TEXT NOT NULL CHECK (action_kind IN ('REPAIR', 'DELIVER')),
    idempotency_key TEXT NOT NULL UNIQUE,
    approval_id TEXT NOT NULL,
    canonical_request_json TEXT NOT NULL,
    request_digest TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE (tenant_id, task_id, plan_hash, action_kind)
);
CREATE TABLE IF NOT EXISTS d3_action_ledgers (
    ledger_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    task_id TEXT NOT NULL,
    plan_hash TEXT NOT NULL,
    action_kind TEXT NOT NULL CHECK (action_kind IN ('REPAIR', 'DELIVER')),
    action_id TEXT NOT NULL UNIQUE REFERENCES d3_action_intents(action_id),
    idempotency_key TEXT NOT NULL UNIQUE,
    request_digest TEXT NOT NULL,
    approval_id TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('COMMITTED', 'REJECTED_PRECONDITION', 'REJECTED_AUTH')),
    before_version INTEGER,
    after_version INTEGER,
    result_json TEXT NOT NULL,
    result_digest TEXT NOT NULL,
    committed_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS d3_verification_receipts (
    verification_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    task_id TEXT NOT NULL,
    plan_hash TEXT NOT NULL,
    repair_action_id TEXT NOT NULL,
    service_id TEXT NOT NULL,
    integration_id TEXT NOT NULL,
    principal_id TEXT NOT NULL,
    business_route TEXT NOT NULL,
    probe_observed_versions_json TEXT NOT NULL,
    observed_at TEXT NOT NULL,
    response_status INTEGER NOT NULL,
    business_assertions_json TEXT NOT NULL,
    recovery_verified INTEGER NOT NULL CHECK (recovery_verified IN (0, 1)),
    result_digest TEXT NOT NULL,
    UNIQUE (tenant_id, task_id, plan_hash, repair_action_id)
);
CREATE TABLE IF NOT EXISTS d3_report_artifacts (
    report_ref TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    task_id TEXT NOT NULL,
    plan_hash TEXT NOT NULL,
    repair_action_id TEXT NOT NULL,
    verification_id TEXT NOT NULL,
    report_version INTEGER NOT NULL,
    content_digest TEXT NOT NULL,
    immutable_content_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE (tenant_id, task_id, plan_hash, repair_action_id, report_version)
);
CREATE TABLE IF NOT EXISTS d3_ticket_resolution_entries (
    entry_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    ticket_id TEXT NOT NULL,
    task_id TEXT NOT NULL,
    plan_hash TEXT NOT NULL,
    delivery_action_id TEXT NOT NULL,
    field_name TEXT NOT NULL,
    content_json TEXT NOT NULL,
    content_digest TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE (tenant_id, ticket_id, delivery_action_id)
);
CREATE TABLE IF NOT EXISTS d3_delivery_records (
    delivery_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    task_id TEXT NOT NULL,
    plan_hash TEXT NOT NULL,
    delivery_action_id TEXT NOT NULL UNIQUE,
    ticket_id TEXT NOT NULL,
    report_ref TEXT NOT NULL,
    report_version INTEGER NOT NULL,
    payload_digest TEXT NOT NULL,
    ticket_entry_id TEXT NOT NULL,
    delivery_receipt_json TEXT NOT NULL,
    committed_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS d3_local_reports (
    report_ref TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    task_id TEXT NOT NULL,
    plan_hash TEXT,
    outcome TEXT NOT NULL,
    content_digest TEXT NOT NULL,
    immutable_content_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE (tenant_id, task_id, plan_hash, outcome)
);
CREATE TABLE IF NOT EXISTS d5_memories (
    memory_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL REFERENCES tenants(tenant_id),
    project_id TEXT NOT NULL,
    type TEXT NOT NULL CHECK (type = 'EPISODIC'),
    problem_type TEXT NOT NULL,
    summary TEXT NOT NULL,
    applicability_constraints_json TEXT NOT NULL,
    source_task_id TEXT NOT NULL REFERENCES task_bindings(task_id),
    source_evidence_ids_json TEXT NOT NULL,
    source_report_ref TEXT NOT NULL,
    source_verification_id TEXT NOT NULL,
    state TEXT NOT NULL CHECK (state IN ('CANDIDATE', 'ACTIVE', 'REVOKED')),
    version INTEGER NOT NULL,
    confirmed_by TEXT,
    confirmed_at TEXT,
    revoked_by TEXT,
    revoked_at TEXT,
    expires_at TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE (tenant_id, project_id, problem_type, source_task_id)
);
CREATE INDEX IF NOT EXISTS ix_d5_memories_lookup
    ON d5_memories(tenant_id, project_id, problem_type, state, expires_at);
CREATE TABLE IF NOT EXISTS d5_memory_events (
    event_id TEXT PRIMARY KEY,
    memory_id TEXT NOT NULL REFERENCES d5_memories(memory_id),
    tenant_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    event_type TEXT NOT NULL CHECK (event_type IN ('CANDIDATE_CREATED', 'CONFIRMED', 'REVOKED')),
    actor_id TEXT NOT NULL,
    memory_version INTEGER NOT NULL,
    occurred_at TEXT NOT NULL,
    details_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS d5_context_provenance (
    call_id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL REFERENCES task_bindings(task_id),
    attempt_id TEXT NOT NULL UNIQUE REFERENCES d2_attempts(attempt_id),
    model_id TEXT NOT NULL,
    prompt_version TEXT NOT NULL,
    prompt_digest TEXT NOT NULL,
    tool_schema_version TEXT NOT NULL,
    tool_schema_digest TEXT NOT NULL,
    selected_skill_name TEXT,
    selected_skill_version TEXT,
    selected_skill_digest TEXT,
    selected_memories_json TEXT NOT NULL,
    evidence_ids_json TEXT NOT NULL,
    built_at TEXT NOT NULL,
    model_status TEXT NOT NULL DEFAULT 'PREPARED',
    completed_at TEXT,
    error_class TEXT
);
CREATE INDEX IF NOT EXISTS ix_d5_context_task ON d5_context_provenance(task_id, built_at);
"""


@contextmanager
def connect(path: str | Path) -> Iterator[sqlite3.Connection]:
    db_path = Path(path).resolve()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(db_path, timeout=5.0)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def initialize(path: str | Path) -> None:
    with connect(path) as connection:
        connection.executescript(SCHEMA)


def reset_fixture(path: str | Path, scenario: Scenario) -> None:
    """Reset local demo state. This function is never exposed as an Agent tool."""
    initialize(path)
    status_a = "DISABLED" if scenario == "S1_DISABLED" else "ENABLED"
    with connect(path) as connection:
        for table in (
            "d5_context_provenance",
            "d5_memory_events",
            "d5_memories",
            "d3_local_reports",
            "d3_delivery_records",
            "d3_ticket_resolution_entries",
            "d3_report_artifacts",
            "d3_verification_receipts",
            "d3_action_ledgers",
            "d3_action_intents",
            "d3_action_permissions",
            "d3_approvals",
            "d3_plan_authorization_history",
            "d3_plan_authorizations",
            "d3_plans",
            "tickets",
            "executor_services",
            "d2_tool_faults",
            "d2_reports",
            "d2_evidence",
            "d2_tool_observations",
            "d2_pending_tool_calls",
            "d2_model_traces",
            "d2_attempts",
            "task_bindings",
            "auth_events",
            "auth_policies",
            "services",
            "integrations",
            "principals",
            "credentials",
            "orders",
            "thread_owners",
            "trusted_operators",
            "tenants",
        ):
            connection.execute(f"DELETE FROM {table}")
        connection.executemany(
            "INSERT INTO tenants (tenant_id) VALUES (?)",
            [("tenant-a",), ("tenant-b",)],
        )
        connection.executemany(
            "INSERT INTO trusted_operators (actor_id, tenant_id, role) VALUES (?, ?, ?)",
            [
                ("support-a", "tenant-a", "SUPPORT"),
                ("approver-a", "tenant-a", "APPROVER"),
                ("support-b", "tenant-b", "SUPPORT"),
                ("approver-b", "tenant-b", "APPROVER"),
            ],
        )
        connection.executemany(
            "INSERT INTO executor_services (executor_id, tenant_id, active) VALUES (?, ?, 1)",
            [("executor-a", "tenant-a"), ("executor-b", "tenant-b")],
        )
        connection.executemany(
            "INSERT INTO tickets (tenant_id, ticket_id, status) VALUES (?, ?, 'OPEN')",
            [("tenant-a", "INC-A-001"), ("tenant-b", "INC-B-001")],
        )
        for tenant_id, suffix, principal_status in (
            ("tenant-a", "a", status_a),
            ("tenant-b", "b", "ENABLED"),
        ):
            connection.executemany(
                "INSERT INTO credentials VALUES (?, ?, ?, ?)",
                [
                    (tenant_id, "cred-v1", f"fixture-{suffix}-old-secret", 1),
                    (tenant_id, "cred-v2", f"fixture-{suffix}-current-secret", 2),
                ],
            )
            connection.execute(
                "INSERT INTO principals VALUES (?, ?, ?, ?)",
                (tenant_id, f"principal-{suffix}", principal_status, 2),
            )
            connection.execute(
                "INSERT INTO integrations VALUES (?, ?, ?, ?, ?)",
                (tenant_id, f"integration-{suffix}", f"principal-{suffix}", "cred-v1", 7),
            )
            connection.execute(
                "INSERT INTO services VALUES (?, ?, ?, ?)",
                (tenant_id, "orders-demo", f"integration-{suffix}", "/api/orders/demo-order"),
            )
            connection.execute(
                "INSERT INTO auth_policies VALUES (?, ?, ?, ?)",
                (tenant_id, "orders-demo", "cred-v2", 3),
            )
            connection.execute(
                "INSERT INTO orders VALUES (?, ?, ?)",
                (tenant_id, "demo-order", "CONFIRMED"),
            )


def get_service_info(path: str | Path, tenant_id: str, service_id: str) -> dict[str, object]:
    with connect(path) as connection:
        row = connection.execute(
            """
            SELECT s.service_id, s.route, s.tenant_id, s.integration_id,
                   i.credential_ref, i.config_version, i.principal_id,
                   p.status AS principal_status, p.principal_version,
                   a.accepted_credential_ref, a.policy_version
            FROM services AS s
            JOIN integrations AS i
              ON i.tenant_id = s.tenant_id AND i.integration_id = s.integration_id
            JOIN principals AS p
              ON p.tenant_id = i.tenant_id AND p.principal_id = i.principal_id
            JOIN auth_policies AS a
              ON a.tenant_id = s.tenant_id AND a.service_id = s.service_id
            WHERE s.tenant_id = ? AND s.service_id = ?
            """,
            (tenant_id, service_id),
        ).fetchone()
    if row is None:
        raise LookupError("Service is not available in the trusted tenant scope.")
    return dict(row)


def get_integration_info(
    path: str | Path, tenant_id: str, integration_id: str
) -> dict[str, object]:
    with connect(path) as connection:
        row = connection.execute(
            """
            SELECT i.integration_id, i.principal_id, i.credential_ref,
                   i.config_version, p.status AS principal_status,
                   p.principal_version
            FROM integrations AS i
            JOIN principals AS p
              ON p.tenant_id = i.tenant_id AND p.principal_id = i.principal_id
            WHERE i.tenant_id = ? AND i.integration_id = ?
            """,
            (tenant_id, integration_id),
        ).fetchone()
    if row is None:
        raise LookupError("Integration is not available in the trusted tenant scope.")
    return dict(row)


def get_credential_secret(path: str | Path, tenant_id: str, credential_ref: str) -> str:
    with connect(path) as connection:
        row = connection.execute(
            "SELECT secret_value FROM credentials WHERE tenant_id = ? AND credential_ref = ?",
            (tenant_id, credential_ref),
        ).fetchone()
    if row is None:
        raise LookupError("Credential reference is not available in the trusted tenant scope.")
    return str(row["secret_value"])


def record_auth_event(
    path: str | Path,
    tenant_id: str,
    integration_id: str,
    principal_id: str,
    service_id: str,
    route: str,
    result_code: str,
) -> int:
    with connect(path) as connection:
        cursor = connection.execute(
            """INSERT INTO auth_events
               (tenant_id, integration_id, principal_id, service_id, route, result_code)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (tenant_id, integration_id, principal_id, service_id, route, result_code),
        )
        return int(cursor.lastrowid)


def get_auth_event(path: str | Path, tenant_id: str, event_id: int) -> dict[str, object]:
    with connect(path) as connection:
        row = connection.execute(
            """SELECT event_id, tenant_id, integration_id, principal_id,
                      service_id, route, result_code, observed_at
               FROM auth_events WHERE tenant_id = ? AND event_id = ?""",
            (tenant_id, event_id),
        ).fetchone()
    if row is None:
        raise LookupError("Authentication event is not available within the trusted tenant scope.")
    return dict(row)
