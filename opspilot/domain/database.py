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
            "auth_events",
            "auth_policies",
            "services",
            "integrations",
            "principals",
            "credentials",
            "orders",
            "thread_owners",
            "tenants",
        ):
            connection.execute(f"DELETE FROM {table}")
        connection.executemany(
            "INSERT INTO tenants (tenant_id) VALUES (?)",
            [("tenant-a",), ("tenant-b",)],
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
) -> None:
    with connect(path) as connection:
        connection.execute(
            """INSERT INTO auth_events
               (tenant_id, integration_id, principal_id, service_id, route, result_code)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (tenant_id, integration_id, principal_id, service_id, route, result_code),
        )
