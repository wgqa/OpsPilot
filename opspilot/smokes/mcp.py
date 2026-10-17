from __future__ import annotations

import asyncio
import json
import sys
import tempfile
from pathlib import Path

from mcp import Client, StdioServerParameters

from opspilot.domain.database import reset_fixture


def emit(event: str, **fields: object) -> None:
    print(json.dumps({"event": event, **fields}, sort_keys=True, default=str))


async def run_smoke(db_path: Path) -> int:
    reset_fixture(db_path, "S1_POS")
    server_params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "opspilot.mcp_server", "--db", str(db_path), "--tenant", "tenant-a"],
        env={"OPSPILOT_DB_PATH": str(db_path)},
        cwd=str(Path.cwd()),
    )
    try:
        async with Client(server_params) as client:
            tools_result = await client.list_tools()
            tools = [
                {
                    "name": item.name,
                    "input_schema": item.input_schema,
                    "annotations": item.annotations.model_dump(exclude_none=True)
                    if item.annotations
                    else None,
                }
                for item in tools_result.tools
            ]
            tool_names = {item["name"] for item in tools}
            if tool_names != {"get_demo_service_info", "get_integration_config"}:
                emit("mcp_tools_list_failed", tools=tools)
                return 1
            if any(
                "tenant_id" in json.dumps(item["input_schema"])
                or "authorization" in json.dumps(item["input_schema"]).lower()
                for item in tools
            ):
                emit("mcp_scope_schema_failed", tools=tools)
                return 1
            emit("mcp_tools_list", tools=tools)

            result = await client.call_tool("get_demo_service_info", {"service_id": "orders-demo"})
            structured = result.structured_content
            if result.is_error or not structured:
                emit("mcp_domain_call_failed", is_error=result.is_error)
                return 1
            payload = structured.get("result", structured)
            if not isinstance(payload, dict) or payload.get("tenant_id") != "tenant-a":
                emit("mcp_domain_call_failed", structured_content=structured)
                return 1
            emit(
                "mcp_domain_call",
                tool_name="get_demo_service_info",
                structured_content=structured,
                is_error=result.is_error,
            )

            negative = await client.call_tool(
                "get_integration_config", {"integration_id": "integration-b"}
            )
            if not negative.is_error:
                emit("mcp_scope_negative_failed", is_error=negative.is_error)
                return 1
            error_content = [
                block.text for block in negative.content if hasattr(block, "text")
            ]
            emit("mcp_scope_negative", is_error=negative.is_error, content=error_content)
            return 0
    except (OSError, TimeoutError) as error:
        emit("mcp_transport_error", exception_type=type(error).__name__)
        return 2
    except Exception as error:
        emit("mcp_protocol_or_tool_error", exception_type=type(error).__name__)
        return 1


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="opspilot-mcp-") as temporary:
        return asyncio.run(run_smoke(Path(temporary) / "domain.sqlite3"))


if __name__ == "__main__":
    raise SystemExit(main())
