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
