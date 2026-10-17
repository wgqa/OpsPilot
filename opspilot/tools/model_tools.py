from __future__ import annotations

import os

from langchain.tools import tool

from opspilot.config import DEFAULT_DB_PATH, database_path
from opspilot.domain.database import get_service_info
from opspilot.domain.schemas import ServiceInfoRequest


@tool("get_demo_service_info", args_schema=ServiceInfoRequest)
def get_demo_service_info(service_id: str) -> dict[str, object]:
    """Read non-secret configuration facts for a registered demo service."""
    tenant_id = os.environ.get("OPSPILOT_TENANT_ID", "tenant-a")
    return get_service_info(database_path(os.environ.get("OPSPILOT_DB_PATH", str(DEFAULT_DB_PATH))), tenant_id, service_id)
