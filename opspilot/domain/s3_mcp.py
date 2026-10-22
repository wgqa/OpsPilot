from __future__ import annotations

from mcp.server import MCPServer
from mcp.server.mcpserver.context import Context
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations
from typing import Annotated, Literal
from pydantic import StrictStr, Field

from opspilot.domain.database import connect
from opspilot.domain.d2 import ScopeDenied
from opspilot.domain.s3 import (
    get_s3_binding, get_order_status_fact, get_callback_delivery_fact, get_receiver_processing_fact,
)
from opspilot.domain.s3_assets import search_knowledge, load_s3_skill
from opspilot.domain.schemas import D2ToolFact

TOOLS = {"get_order_status", "get_callback_delivery", "get_receiver_processing", "search_callback_knowledge", "load_callback_skill"}
Reason = Annotated[StrictStr, Field(min_length=1,max_length=400,description="A brief reason for this next query, at most 160 characters recommended.")]
Query = Annotated[StrictStr, Field(min_length=1,max_length=300)]


def build_s3_server(db_path, task_id, api_url):
    server = MCPServer("opspilot-s3-task-readonly")

    def validate(reason, ctx, allowed):
        raw = ctx._input_params.arguments if ctx._input_params else None
        if not isinstance(raw,dict) or set(raw) != allowed:
            raise ToolError("S3_INVALID_ARGUMENTS")
        if not reason.strip() or len(reason) > 400:
            raise ValueError("A bounded investigation reason is required")
        try:
            with connect(db_path) as c:
                get_s3_binding(c, task_id)
        except ScopeDenied:
            raise ToolError("S3_RESOURCE_OUTSIDE_TASK_BINDING") from None

    @server.tool(annotations=ToolAnnotations(read_only_hint=True,open_world_hint=False))
    def get_order_status(reason: Reason, ctx: Context) -> D2ToolFact:
        """Read the bound order through real authenticated HTTP; 200 alone does not prove completion."""
        validate(reason,ctx,{"reason"})
        return D2ToolFact.model_validate(get_order_status_fact(db_path, task_id, api_url))

    @server.tool(annotations=ToolAnnotations(read_only_hint=True,open_world_hint=False))
    def get_callback_delivery(reason: Reason, ctx: Context) -> D2ToolFact:
        """Read current bound callback event, order version and actual transport acknowledgement/failure."""
        validate(reason,ctx,{"reason"})
        return D2ToolFact.model_validate(get_callback_delivery_fact(db_path, task_id))

    @server.tool(annotations=ToolAnnotations(read_only_hint=True,open_world_hint=False))
    def get_receiver_processing(reason: Reason, ctx: Context) -> D2ToolFact:
        """Read current processing state for the bound callback event. ACK is not completed processing."""
        validate(reason,ctx,{"reason"})
        return D2ToolFact.model_validate(get_receiver_processing_fact(db_path, task_id))

    @server.tool(annotations=ToolAnnotations(read_only_hint=True,open_world_hint=False))
    def search_callback_knowledge(query: Query, reason: Reason, ctx: Context) -> dict[str, object]:
        """Retrieve one relevant active versioned integration contract by a short query; method only, not live facts."""
        validate(reason,ctx,{"query","reason"})
        return {"documents":search_knowledge(query), "reason":reason}

    @server.tool(annotations=ToolAnnotations(read_only_hint=True,open_world_hint=False))
    def load_callback_skill(name: Literal["order-lifecycle-triage", "callback-delivery-triage"], reason: Reason, ctx: Context) -> dict[str, object]:
        """Load one method when useful: order-lifecycle-triage or callback-delivery-triage. Does not change authority."""
        validate(reason,ctx,{"name","reason"})
        return {"skill":load_s3_skill(name), "reason":reason}

    return server
