from __future__ import annotations

import argparse
import asyncio
import os

from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations

from opspilot.config import DEFAULT_DB_PATH, database_path
from opspilot.domain.database import get_integration_info, get_service_info, initialize
from opspilot.domain.schemas import IntegrationInfoResponse, ServiceInfoResponse


def build_server(db_path: str, tenant_id: str) -> MCPServer:
    trusted_db_path = database_path(db_path)
    initialize(trusted_db_path)
    server = MCPServer("OpsPilot read-only demo domain")

    @server.tool(
        title="Read demo service information",
        annotations=ToolAnnotations(read_only_hint=True, open_world_hint=False),
    )
    def get_demo_service_info(service_id: str) -> ServiceInfoResponse:
        """Read public configuration facts for a registered service in the server-bound tenant."""
        try:
            data = get_service_info(trusted_db_path, tenant_id, service_id)
        except LookupError:
            raise ToolError("Service is not available within the server-bound scope.") from None
        return ServiceInfoResponse.model_validate(data)

    @server.tool(
        title="Read integration configuration",
        annotations=ToolAnnotations(read_only_hint=True, open_world_hint=False),
    )
    def get_integration_config(integration_id: str) -> IntegrationInfoResponse:
        """Read a non-secret integration configuration in the server-bound tenant."""
        try:
            data = get_integration_info(trusted_db_path, tenant_id, integration_id)
        except LookupError:
            raise ToolError("Integration is not available within the server-bound scope.") from None
        return IntegrationInfoResponse.model_validate(data)

    return server


async def run(db_path: str, tenant_id: str) -> None:
    server = build_server(db_path, tenant_id)
    await server.run_stdio_async()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the read-only OpsPilot MCP server over stdio.")
    parser.add_argument("--db", default=os.environ.get("OPSPILOT_DB_PATH", str(DEFAULT_DB_PATH)))
    parser.add_argument("--tenant", default=os.environ.get("OPSPILOT_TENANT_ID", "tenant-a"))
    args = parser.parse_args()
    asyncio.run(run(args.db, args.tenant))


if __name__ == "__main__":
    main()
