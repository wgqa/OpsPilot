from __future__ import annotations

import argparse
import asyncio
import os
import threading

from pydantic import StrictStr
from mcp.server import MCPServer
from mcp.server.mcpserver.context import Context
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations

from opspilot.config import DEFAULT_DB_PATH, database_path
from opspilot.domain.database import get_integration_info, get_service_info, initialize
from opspilot.domain.schemas import D2ToolFact, IntegrationInfoResponse, ScopeAuthzFactRequest, ServiceInfoResponse


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


def build_task_server(
    db_path: str, task_id: str, business_api_url: str, *, include_scope_authz_facts: bool = False
) -> MCPServer:
    """Build the D2 server; every call is scoped through a persisted TaskBinding."""
    from opspilot.domain.d2 import (
        ScopeDenied,
        ToolUnavailable,
        get_auth_policy_fact,
        get_integration_config_fact,
        get_principal_status_fact,
        get_scope_authz_facts_fact,
        get_task_binding,
        probe_endpoint_fact,
    )

    trusted_db_path = database_path(db_path)
    initialize(trusted_db_path)
    binding = get_task_binding(trusted_db_path, task_id)
    server = MCPServer("OpsPilot D2 task-bound read-only investigator")

    @server.tool(
        title="Read integration configuration",
        annotations=ToolAnnotations(read_only_hint=True, open_world_hint=False),
    )
    def get_integration_config(integration_id: str) -> D2ToolFact:
        """Read credential reference and configuration version for the bound integration."""
        try:
            return D2ToolFact.model_validate(
                get_integration_config_fact(trusted_db_path, task_id, integration_id)
            )
        except ScopeDenied:
            raise ToolError("RESOURCE_OUTSIDE_TASK_SCOPE") from None

    @server.tool(
        title="Read principal status",
        annotations=ToolAnnotations(read_only_hint=True, open_world_hint=False),
    )
    def get_principal_status(principal_id: str) -> D2ToolFact:
        """Read status and version of the principal bound to this task."""
        try:
            return D2ToolFact.model_validate(
                get_principal_status_fact(trusted_db_path, task_id, principal_id)
            )
        except ScopeDenied:
            raise ToolError("RESOURCE_OUTSIDE_TASK_SCOPE") from None

    @server.tool(
        title="Read authentication policy",
        annotations=ToolAnnotations(read_only_hint=True, open_world_hint=False),
    )
    def get_auth_policy(service_id: str) -> D2ToolFact:
        """Read the accepted credential reference and policy version for the bound service."""
        try:
            return D2ToolFact.model_validate(
                get_auth_policy_fact(trusted_db_path, task_id, service_id)
            )
        except ScopeDenied:
            raise ToolError("RESOURCE_OUTSIDE_TASK_SCOPE") from None
        except ToolUnavailable as error:
            raise ToolError(error.error_code) from None

    @server.tool(
        title="Read task-bound authorization decision facts",
        annotations=ToolAnnotations(read_only_hint=True, open_world_hint=False),
    )
    def get_scope_authz_facts(request_id: StrictStr, ctx: Context) -> D2ToolFact:
        """Read the currentness of one HTTP decision bound to this task's fixed resources."""
        raw_arguments = ctx._input_params.arguments if ctx._input_params is not None else None
        if not isinstance(raw_arguments, dict) or set(raw_arguments) != {"request_id"}:
            raise ToolError("INVALID_ARGUMENTS")
        try:
            request = ScopeAuthzFactRequest.model_validate({"request_id": request_id})
            return D2ToolFact.model_validate(
                get_scope_authz_facts_fact(trusted_db_path, task_id, request.request_id)
            )
        except ScopeDenied:
            raise ToolError("RESOURCE_OUTSIDE_TASK_SCOPE") from None

    @server.tool(
        title="Probe registered business endpoint",
        annotations=ToolAnnotations(read_only_hint=True, open_world_hint=False),
    )
    def probe_endpoint(service_id: str, integration_id: str) -> D2ToolFact:
        """Call the registered loopback business route using the bound integration."""
        try:
            return D2ToolFact.model_validate(
                probe_endpoint_fact(
                    trusted_db_path,
                    task_id,
                    service_id,
                    integration_id,
                    business_api_url,
                )
            )
        except ScopeDenied:
            raise ToolError("RESOURCE_OUTSIDE_TASK_SCOPE") from None

    if not include_scope_authz_facts:
        server.remove_tool("get_scope_authz_facts")
    return server


async def run(db_path: str, tenant_id: str) -> None:
    server = build_server(db_path, tenant_id)
    await server.run_stdio_async()


async def run_task(db_path: str, task_id: str, *, include_scope_authz_facts: bool = False) -> None:
    from opspilot.domain.d2 import get_task_binding
    from opspilot.domain.api import make_server

    trusted_db_path = database_path(db_path)
    binding = get_task_binding(trusted_db_path, task_id)
    business_api = make_server(trusted_db_path, str(binding["tenant_id"]), "127.0.0.1", 0)
    api_thread = threading.Thread(
        target=business_api.serve_forever,
        kwargs={"poll_interval": 0.05},
        daemon=True,
    )
    api_thread.start()
    try:
        host, port = business_api.server_address
        server = build_task_server(
            trusted_db_path, task_id, f"http://{host}:{port}",
            include_scope_authz_facts=include_scope_authz_facts,
        )
        await server.run_stdio_async()
    finally:
        business_api.shutdown()
        api_thread.join(timeout=2)
        business_api.server_close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the read-only OpsPilot MCP server over stdio.")
    parser.add_argument("--db", default=os.environ.get("OPSPILOT_DB_PATH", str(DEFAULT_DB_PATH)))
    parser.add_argument("--tenant", default=os.environ.get("OPSPILOT_TENANT_ID", "tenant-a"))
    parser.add_argument("--binding-id", help="Run the D2 task-bound server using this trusted TaskBinding.")
    parser.add_argument(
        "--include-scope-authz-facts", action="store_true",
        help="Expose the M2-01 read-only authorization fact tool for a deliberate S2 facts session.",
    )
    args = parser.parse_args()
    if args.binding_id:
        asyncio.run(run_task(args.db, args.binding_id, include_scope_authz_facts=args.include_scope_authz_facts))
    else:
        asyncio.run(run(args.db, args.tenant))


if __name__ == "__main__":
    main()
