"""Trusted Run-scoped MCP entry. No Task is fabricated for document access."""
import argparse
import asyncio
import threading
from mcp.server import MCPServer
from mcp.types import ToolAnnotations
from opspilot.domain.assistant import read_run
from opspilot.domain import assistant as assistant_domain
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

    if record['task_id'] is None and identity.role == 'SUPPORT':
        @server.tool(annotations=ToolAnnotations(read_only_hint=True,open_world_hint=False))
        def propose_controlled_auth_investigation(rationale: str) -> dict:
            """Suggest the existing controlled S1/S2 investigation for this exact user message.

            This records an advisory result only. It creates no Task, binding,
            permission, approval, repair, or handoff. The user must confirm the
            original question and a trusted resource in the existing UI.
            """
            try:
                return assistant_domain.propose_controlled_auth_investigation(
                    path, run_id, rationale,
                )
            except Exception as error:
                return {
                    'success': False,
                    'error': getattr(error, 'code', type(error).__name__),
                    'authority': 'TOOL_REFUSAL_NOT_FACT',
                    'task_created': False,
                    'authorization_created': False,
                }

        @server.tool(annotations=ToolAnnotations(read_only_hint=True,open_world_hint=False))
        def read_session_professional_outcomes() -> dict:
            """Read persisted S1/S2 results linked to this exact trusted Session.

            Session and caller identity are derived from the active server-side
            Assistant Run; model supplied task, receipt, tenant, or actor IDs
            are neither accepted nor used as authority.
            """
            try:
                return assistant_domain.read_session_professional_outcomes(path, run_id)
            except Exception as error:
                return {
                    'success': False,
                    'error': getattr(error, 'code', type(error).__name__),
                    'authority': 'TOOL_REFUSAL_NOT_FACT',
                    'items': [],
                }
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

    @server.tool(annotations=ToolAnnotations(read_only_hint=True,open_world_hint=False))
    def read_scoped_protocol_excerpt(
        document_id: str, version: str, query: str,
        start_line: int = 1, start_column: int = 1,
    ) -> dict:
        """Read up to three short original-text excerpts from a currently authorized protocol.

        Document identity and version must come from scoped discovery. The
        result cites exact lines/columns, source digest, excerpt digest, and an
        optional bounded continuation cursor. It is static protocol text, never
        live deployment or business-state evidence.
        """
        from opspilot.domain.scoped_protocol_comparison import (
            read_scoped_protocol_excerpt as read_excerpt,
        )
        from opspilot.domain.protocol_comparison import ProtocolComparisonError
        from opspilot.domain.assistant_knowledge import KnowledgeScopeDenied
        from opspilot.domain.task_control import TaskControlError

        current, actor = read_run(path, run_id)
        try:
            result = read_excerpt(
                path, actor, current['session_id'], document_id=document_id,
                version=version, query=query, start_line=start_line,
                start_column=start_column,
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
    def load_protocol_upgrade_skill(reason: str) -> dict:
        """Load optional protocol-upgrade method guidance when useful.

        This bundled Skill is a bounded method hint only. It cannot grant
        permissions, establish current facts, or require a particular workflow.
        """
        from opspilot.skill_assets import (
            PROTOCOL_UPGRADE_PROBLEM_TYPE,
            load_applicable_skill,
        )
        from opspilot.skill_assets import SkillIntegrityError

        read_run(path, run_id)
        if not isinstance(reason, str) or not reason.strip() or len(reason) > 240:
            return {
                'success': False,
                'error': 'INVALID_SKILL_SELECTION_REASON',
                'reason_code': 'INVALID_SKILL_SELECTION_REASON',
                'authority': 'TOOL_REFUSAL_NOT_FACT',
            }
        try:
            skill = load_applicable_skill(PROTOCOL_UPGRADE_PROBLEM_TYPE)
        except SkillIntegrityError as error:
            return {
                'success': False,
                'error': str(error),
                'reason_code': 'SKILL_ASSET_INVALID',
                'authority': 'TOOL_REFUSAL_NOT_FACT',
            }
        if skill is None:
            return {
                'success': False,
                'error': 'PROTOCOL_UPGRADE_SKILL_NOT_APPLICABLE',
                'reason_code': 'PROTOCOL_UPGRADE_SKILL_NOT_APPLICABLE',
                'authority': 'TOOL_REFUSAL_NOT_FACT',
            }
        return {
            'success': True,
            'problem_type': PROTOCOL_UPGRADE_PROBLEM_TYPE,
            'skill': skill,
            'selection_reason': reason.strip(),
            'authority': 'METHOD_HINT_ONLY_NOT_AUTHORIZATION_OR_CURRENT_FACT',
        }
    try: await server.run_stdio_async()
    finally:
        if api:
            api.shutdown();thread.join(timeout=2);api.server_close()

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--db',required=True);p.add_argument('--run-id',required=True)
    a=p.parse_args();asyncio.run(run(a.db,a.run_id))
