"""Local test credential resolution; secret values never leave this module/API call."""

from pathlib import Path

from opspilot.domain.database import get_credential_secret


def resolve_integration_credential(
    db_path: str | Path, tenant_id: str, credential_ref: str
) -> str:
    return get_credential_secret(db_path, tenant_id, credential_ref)
