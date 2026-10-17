"""Test-only fixture mutations. Do not expose this module through MCP or the API."""

from pathlib import Path

from opspilot.domain.database import connect


def fixture_only_switch_ref(
    db_path: str | Path,
    tenant_id: str,
    integration_id: str,
    new_credential_ref: str,
) -> int:
    if new_credential_ref != "cred-v2":
        raise ValueError("The D1 fixture only allows the server-accepted credential reference.")
    with connect(db_path) as connection:
        cursor = connection.execute(
            """UPDATE integrations
               SET credential_ref = ?, config_version = config_version + 1
               WHERE tenant_id = ? AND integration_id = ?
                 AND credential_ref != ?""",
            (new_credential_ref, tenant_id, integration_id, new_credential_ref),
        )
        if cursor.rowcount != 1:
            raise ValueError("Fixture integration is missing or already uses that reference.")
        row = connection.execute(
            "SELECT config_version FROM integrations WHERE tenant_id = ? AND integration_id = ?",
            (tenant_id, integration_id),
        ).fetchone()
    return int(row["config_version"])


def prepare_d5_auth_401_for_test(
    db_path: str | Path,
    tenant_id: str,
    integration_id: str,
) -> int:
    """Prepare a second test incident without resetting D3 history or rewinding versions."""
    with connect(db_path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute(
            "SELECT credential_ref, config_version FROM integrations WHERE tenant_id = ? AND integration_id = ?",
            (tenant_id, integration_id),
        ).fetchone()
        if row is None or row["credential_ref"] != "cred-v2":
            raise ValueError("D5 test incident requires the recovered cred-v2 state.")
        connection.execute(
            """UPDATE integrations SET credential_ref = 'cred-v1', config_version = config_version + 1
               WHERE tenant_id = ? AND integration_id = ?""",
            (tenant_id, integration_id),
        )
        updated = connection.execute(
            "SELECT config_version FROM integrations WHERE tenant_id = ? AND integration_id = ?",
            (tenant_id, integration_id),
        ).fetchone()
    return int(updated["config_version"])


def set_d5_principal_status_for_test(
    db_path: str | Path,
    tenant_id: str,
    principal_id: str,
    status: str,
) -> int:
    """Create a new explicit test condition with a monotonic principal version."""
    if status not in {"ENABLED", "DISABLED"}:
        raise ValueError("Invalid principal status for D5 test fixture.")
    with connect(db_path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute(
            "SELECT status, principal_version FROM principals WHERE tenant_id = ? AND principal_id = ?",
            (tenant_id, principal_id),
        ).fetchone()
        if row is None:
            raise ValueError("D5 test principal is missing.")
        version = int(row["principal_version"])
        if row["status"] != status:
            version += 1
            connection.execute(
                "UPDATE principals SET status = ?, principal_version = ? WHERE tenant_id = ? AND principal_id = ?",
                (status, version, tenant_id, principal_id),
            )
    return version
