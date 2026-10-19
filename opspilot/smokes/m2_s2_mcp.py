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
from opspilot.investigator import EXPECTED_D2_TOOLS, EXPECTED_S2_TOOLS, _mcp_child_environment


def emit(event: str, **fields: object) -> None:
    print(json.dumps({"event": event, **fields}, sort_keys=True, default=str))


def _structured(result: Any) -> dict[str, object] | None:
    value = result.structured_content
    if isinstance(value, dict) and isinstance(value.get("result"), dict):
        value = value["result"]
    return value if isinstance(value, dict) else None


def _parameters(db_path: Path, task_id: str, *, s2: bool) -> StdioServerParameters:
    args = ["-m", "opspilot.mcp_server", "--db", str(database_path(str(db_path))), "--binding-id", task_id]
    if s2:
        args.append("--include-scope-authz-facts")
    return StdioServerParameters(
        command=sys.executable,
        args=args,
        env=_mcp_child_environment(database_path(str(db_path))),
        cwd=str(ROOT),
    )


async def run_smoke(db_path: Path) -> int:
    reset_fixture(db_path, "S2_SCOPE_DENIED")
    binding = create_task_binding(db_path, "support-a", "orders-demo", "integration-a")
    task_id = str(binding["task_id"])
    try:
        async with Client(_parameters(db_path, task_id, s2=False)) as default_client:
            default_names = {item.name for item in (await default_client.list_tools()).tools}
            if default_names != EXPECTED_D2_TOOLS:
                emit("m2_s2_default_tool_list_failed", names=sorted(default_names))
                return 1
            emit("m2_s2_default_tool_list", names=sorted(default_names), count=len(default_names))

        async with Client(_parameters(db_path, task_id, s2=True)) as client:
            listed = await client.list_tools()
            names = {item.name for item in listed.tools}
            if names != EXPECTED_S2_TOOLS:
                emit("m2_s2_opt_in_tool_list_failed", names=sorted(names))
                return 1
            scope_schema = next(item.input_schema for item in listed.tools if item.name == "get_scope_authz_facts")
            properties = scope_schema.get("properties", {}) if isinstance(scope_schema, dict) else {}
            schema_text = json.dumps(properties).lower()
            forbidden = ("tenant_id", "actor_id", "authorization", "credential", "url", "scope")
            if set(properties) != {"request_id"} or any(value in schema_text for value in forbidden):
                emit("m2_s2_scope_tool_schema_failed", schema=scope_schema)
                return 1
            emit("m2_s2_opt_in_tool_list", names=sorted(names), scope_schema=scope_schema)

            probe_result = await client.call_tool(
                "probe_endpoint", {"service_id": "orders-demo", "integration_id": "integration-a"},
            )
            probe = _structured(probe_result)
            if probe_result.is_error or probe is None or probe.get("facts", {}).get("http_status") != 403:
                emit("m2_s2_probe_failed", is_error=probe_result.is_error, fact=probe)
                return 1
            request_id = str(probe["facts"]["request_id"])
            authz_result = await client.call_tool("get_scope_authz_facts", {"request_id": request_id})
            authz = _structured(authz_result)
            if (
                authz_result.is_error or authz is None
                or authz.get("facts", {}).get("currentness") != "CURRENT"
                or authz.get("facts", {}).get("reason_code") != "SCOPE_INSUFFICIENT"
                or authz.get("facts", {}).get("request_id") != request_id
            ):
                emit("m2_s2_authz_call_failed", is_error=authz_result.is_error, fact=authz)
                return 1
            emit("m2_s2_real_probe", request_id=request_id, fact=probe)
            emit("m2_s2_real_authz_fact", request_id=request_id, fact=authz)

            denied = await client.call_tool("get_scope_authz_facts", {"request_id": "foreign-request-id"})
            if not denied.is_error:
                emit("m2_s2_scope_negative_failed", is_error=False)
                return 1
            emit("m2_s2_scope_negative", is_error=True)
            emit("m2_s2_mcp_smoke_pass", task_id=task_id)
            return 0
    except (OSError, TimeoutError) as error:
        emit("m2_s2_mcp_transport_error", exception_type=type(error).__name__)
        return 2
    except Exception as error:
        emit("m2_s2_mcp_protocol_error", exception_type=type(error).__name__)
        return 1


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="opspilot-m2-s2-mcp-") as temporary:
        return asyncio.run(run_smoke(Path(temporary) / "domain.sqlite3"))


if __name__ == "__main__":
    raise SystemExit(main())
