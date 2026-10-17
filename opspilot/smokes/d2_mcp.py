from __future__ import annotations

import asyncio
import json
import sys
import tempfile
from pathlib import Path
from typing import Any

from mcp import Client, StdioServerParameters

from opspilot.config import ROOT, database_path
from opspilot.domain.d2 import create_task_binding
from opspilot.domain.database import reset_fixture
from opspilot.investigator import EXPECTED_D2_TOOLS, _mcp_child_environment


def emit(event: str, **fields: object) -> None:
    print(json.dumps({"event": event, **fields}, sort_keys=True, default=str))


def _structured(result: Any) -> dict[str, object] | None:
    value = result.structured_content
    if isinstance(value, dict) and isinstance(value.get("result"), dict):
        value = value["result"]
    return value if isinstance(value, dict) else None


async def run_smoke(db_path: Path) -> int:
    reset_fixture(db_path, "S1_POS")
    binding = create_task_binding(db_path, "support-a", "orders-demo", "integration-a")
    server_params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "opspilot.mcp_server", "--db", str(database_path(str(db_path))), "--binding-id", str(binding["task_id"])],
        env=_mcp_child_environment(database_path(str(db_path))),
        cwd=str(ROOT),
    )
    try:
        async with Client(server_params) as client:
            listed = await client.list_tools()
            names = {item.name for item in listed.tools}
            if names != EXPECTED_D2_TOOLS:
                emit("d2_mcp_tool_list_failed", tools=sorted(names))
                return 1
            schemas = [
                {"name": item.name, "description": item.description, "input_schema": item.input_schema}
                for item in listed.tools
            ]
            forbidden = ("tenant_id", "actor_id", "authorization", "credential", "url", "thread_id")
            if any(any(term in json.dumps(item["input_schema"]).lower() for term in forbidden) for item in schemas):
                emit("d2_mcp_schema_scope_failed", tools=schemas)
                return 1
            emit("d2_mcp_tools_list", tools=schemas, count=len(schemas))

            calls = [
                ("get_integration_config", {"integration_id": "integration-a"}),
                ("get_principal_status", {"principal_id": "principal-a"}),
                ("get_auth_policy", {"service_id": "orders-demo"}),
                ("probe_endpoint", {"service_id": "orders-demo", "integration_id": "integration-a"}),
            ]
            outputs: dict[str, dict[str, object]] = {}
            for name, arguments in calls:
                result = await client.call_tool(name, arguments)
                fact = _structured(result)
                if result.is_error or fact is None:
                    emit("d2_mcp_call_failed", tool_name=name, is_error=result.is_error)
                    return 1
                outputs[name] = fact
                emit("d2_mcp_call", tool_name=name, tool_arguments=arguments, is_error=False, structured_content=fact)

            if outputs["probe_endpoint"].get("facts", {}).get("http_status") != 401:
                emit("d2_mcp_real_probe_failed", result=outputs["probe_endpoint"])
                return 1

            denied = await client.call_tool("get_integration_config", {"integration_id": "integration-b"})
            if not denied.is_error:
                emit("d2_mcp_cross_tenant_negative_failed", is_error=denied.is_error)
                return 1
            error_text = [block.text for block in denied.content if hasattr(block, "text")]
            emit("d2_mcp_cross_tenant_negative", is_error=True, content=error_text)
            emit("d2_mcp_smoke_pass", task_id=binding["task_id"], thread_id=binding["thread_id"])
            return 0
    except (OSError, TimeoutError) as error:
        emit("d2_mcp_transport_error", exception_type=type(error).__name__)
        return 2
    except Exception as error:
        emit("d2_mcp_protocol_error", exception_type=type(error).__name__)
        return 1


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="opspilot-d2-mcp-") as temporary:
        return asyncio.run(run_smoke(Path(temporary) / "domain.sqlite3"))


if __name__ == "__main__":
    raise SystemExit(main())
