"""Trusted Run-scoped MCP entry. No Task is fabricated for document access."""
import argparse
import asyncio
import threading
from mcp.server import MCPServer
from mcp.types import ToolAnnotations
from opspilot.domain.assistant import read_run
from opspilot.domain.assistant_knowledge import search
from opspilot.domain.s3_mcp import build_s3_server
from opspilot.domain.api import make_server

async def run(path,run_id):
    record,identity=read_run(path,run_id)
    api=None; thread=None
    if record['task_id']:
        api=make_server(path,identity.tenant_id,'127.0.0.1',0)
        thread=threading.Thread(target=api.serve_forever,kwargs={'poll_interval':0.05},daemon=True)
        thread.start()
        server=build_s3_server(path,record['task_id'],f'http://127.0.0.1:{api.server_address[1]}')
    else: server=MCPServer('OpsPilot professional assistant document reader')
    @server.tool(annotations=ToolAnnotations(read_only_hint=True,open_world_hint=False))
    def search_project_knowledge(query:str,contract_version:int|None=None)->dict:
        """Search the authenticated Session's document scope. Optional version is a lookup preference, never deployment proof. Cite only returned documents with matching source_refs; empty lists mean no document was retrieved. Documents are not current business facts."""
        current,actor=read_run(path,run_id)
        configured=None
        if current['task_id']:
            from opspilot.domain.database import connect
            from opspilot.domain.s3 import get_s3_binding
            with connect(path) as c: configured=get_s3_binding(c,current['task_id'])['contract_version']
        # A user version is a lookup preference. The effective lookup may
        # default to a trusted binding version; preserve those facts separately.
        lookup_version=contract_version if contract_version is not None else configured
        result=search(path,actor,current['session_id'],query,contract_version=lookup_version)
        result['user_requested_contract_version']=contract_version
        result['requested_contract_version']=contract_version
        result['trusted_binding_contract_version']=configured
        result['applicable_contract_version']=configured if configured is not None else result['configured_contract_version']
        # The binding selects applicable documentation, not live deployment truth.
        result['deployment_version_verified']=False
        return result

    @server.tool(annotations=ToolAnnotations(read_only_hint=True,open_world_hint=False))
    def list_scoped_protocol_documents(topic: str | None = None) -> dict:
        """Discover versioned protocol documents allowed for this Session.

        This returns scoped static documentation, not live deployment state or
        action authorization. Callers need not know internal document IDs.
        """
        from opspilot.domain.scoped_protocol_comparison import list_scoped_protocols
        from opspilot.domain.protocol_comparison import ProtocolComparisonError
        from opspilot.domain.assistant_knowledge import KnowledgeScopeDenied
        from opspilot.domain.task_control import TaskControlError

        current, actor = read_run(path, run_id)
        try:
            result = list_scoped_protocols(
                path, actor, current['session_id'], topic=topic,
            )
            result['success'] = True
            return result
        except (ProtocolComparisonError, KnowledgeScopeDenied, TaskControlError) as error:
            return {
                'success': False,
                'error': str(error),
                'reason_code': getattr(error, 'reason_code', type(error).__name__),
                'authority': 'TOOL_REFUSAL_NOT_FACT',
                'deployment_version_verified': False,
            }

    @server.tool(annotations=ToolAnnotations(read_only_hint=True,open_world_hint=False))
    def compare_scoped_protocols(
        base_document_id: str,
        target_document_id: str,
        base_version: str | int | None = None,
        target_version: str | int | None = None,
    ) -> dict:
        """Compare two authorized protocol versions and return sourced section diffs.

        The comparison cannot establish which version is deployed or authorize
        business actions. Both document IDs must be discovered/authorized in
        this Session's active project scope.
        """
        from opspilot.domain.scoped_protocol_comparison import compare_scoped_protocols as compare
        from opspilot.domain.protocol_comparison import ProtocolComparisonError
        from opspilot.domain.assistant_knowledge import KnowledgeScopeDenied
        from opspilot.domain.task_control import TaskControlError

        current, actor = read_run(path, run_id)
        try:
            result = compare(
                path,
                actor,
                current['session_id'],
                base_document_id=base_document_id,
                target_document_id=target_document_id,
                base_version=str(base_version) if base_version is not None else None,
                target_version=str(target_version) if target_version is not None else None,
            ).to_dict()
            result['success'] = True
            return result
        except (ProtocolComparisonError, KnowledgeScopeDenied, TaskControlError) as error:
            return {
                'success': False,
                'error': str(error),
                'reason_code': getattr(error, 'reason_code', type(error).__name__),
                'authority': 'TOOL_REFUSAL_NOT_FACT',
                'deployment_version_verified': False,
            }
    try: await server.run_stdio_async()
    finally:
        if api:
            api.shutdown();thread.join(timeout=2);api.server_close()

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--db',required=True);p.add_argument('--run-id',required=True)
    a=p.parse_args();asyncio.run(run(a.db,a.run_id))
