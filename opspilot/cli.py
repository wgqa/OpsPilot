from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path

from opspilot.config import DEFAULT_CHECKPOINT_DB_PATH, DEFAULT_DB_PATH, database_path, load_local_environment
from opspilot.domain.api import make_server
from opspilot.domain.client import probe_orders
from opspilot.domain.database import reset_fixture


def emit(event: str, **fields: object) -> None:
    print(json.dumps({"event": event, **fields}, sort_keys=True, default=str))


def d3_public_action_summary(state: dict[str, object]) -> dict[str, object]:
    def rows(name: str) -> list[dict[str, object]]:
        value = state.get(name, [])
        return [dict(item) for item in value if isinstance(item, dict)] if isinstance(value, list) else []

    receipts = []
    for item in rows("verification_receipts"):
        assertions = json.loads(str(item.pop("business_assertions_json", "{}")))
        versions = json.loads(str(item.pop("probe_observed_versions_json", "{}")))
        item["business_assertions"] = assertions
        item["probe_observed_versions"] = versions
        item["recovery_verified"] = bool(item.get("recovery_verified"))
        receipts.append(item)
    ledgers = []
    for item in rows("action_ledgers"):
        item["result"] = json.loads(str(item.pop("result_json", "{}")))
        ledgers.append(item)
    deliveries = []
    for item in rows("delivery_records"):
        item["delivery_receipt"] = json.loads(str(item.pop("delivery_receipt_json", "{}")))
        deliveries.append(item)
    entries = rows("ticket_entries")
    return {
        "task_binding": state.get("task_binding"),
        "plans": [
            {key: item.get(key) for key in ("plan_id", "plan_hash", "plan_version", "created_by")}
            for item in rows("plans")
        ],
        "plan_authorizations": rows("plan_authorizations"),
        "approvals": [
            {key: item.get(key) for key in ("approval_id", "plan_hash", "approver_id", "decision", "approval_scope_json", "decided_at")}
            for item in rows("approvals")
        ],
        "permissions": rows("permissions"),
        "action_intents": [
            {key: item.get(key) for key in ("action_id", "action_kind", "idempotency_key", "request_digest", "approval_id", "plan_hash")}
            for item in rows("action_intents")
        ],
        "action_ledgers": ledgers,
        "verification_receipts": receipts,
        "report_artifacts": [
            {key: item.get(key) for key in ("report_ref", "plan_hash", "repair_action_id", "verification_id", "report_version", "content_digest")}
            for item in rows("report_artifacts")
        ],
        "delivery_records": deliveries,
        "ticket_entries": entries,
        "local_reports": [
            {key: item.get(key) for key in ("report_ref", "outcome", "content_digest", "plan_hash")}
            for item in rows("local_reports")
        ],
    }


def parser_for_cli() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="opspilot")
    subparsers = parser.add_subparsers(dest="command", required=True)

    reset = subparsers.add_parser("reset", help="Reset local S1 demo fixture data.")
    reset.add_argument("--scenario", choices=("S1_POS", "S1_DISABLED"), required=True)
    reset.add_argument("--db", default=str(DEFAULT_DB_PATH))

    serve = subparsers.add_parser("serve", help="Run the loopback business API.")
    serve.add_argument("--db", default=str(DEFAULT_DB_PATH))
    serve.add_argument("--tenant", default="tenant-a")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)

    probe = subparsers.add_parser("probe", help="Call the registered demo order business route.")
    probe.add_argument("--db", default=str(DEFAULT_DB_PATH))
    probe.add_argument("--base-url", default="http://127.0.0.1:8000")
    probe.add_argument("--tenant", default="tenant-a")
    probe.add_argument("--integration", default="integration-a")

    smoke = subparsers.add_parser("smoke", help="Run a D1 technical smoke.")
    smoke.add_argument("kind", choices=("tool-call", "mcp", "checkpoint", "s1"))

    investigate = subparsers.add_parser("investigate", help="Create and run a trusted D2 read-only task.")
    investigate.add_argument("--actor", required=True, help="Trusted local support actor ID.")
    investigate.add_argument("--service", default="orders-demo")
    investigate.add_argument("--integration", default="integration-a")
    investigate.add_argument("--db", default=str(DEFAULT_DB_PATH))
    investigate.add_argument("--checkpoint-db", default=str(DEFAULT_CHECKPOINT_DB_PATH))

    resume = subparsers.add_parser("resume", help="Resume a D2 task after checking trusted thread ownership.")
    resume.add_argument("--actor", required=True, help="Trusted local support actor ID.")
    resume.add_argument("--thread-id", required=True)
    resume.add_argument("--db", default=str(DEFAULT_DB_PATH))
    resume.add_argument("--checkpoint-db", default=str(DEFAULT_CHECKPOINT_DB_PATH))

    d2_smoke = subparsers.add_parser("d2-smoke", help="Run one real-model D2 investigation scenario.")
    d2_smoke.add_argument("--scenario", choices=("POS", "DISABLED", "INSUFFICIENT"), required=True)
    d2_smoke.add_argument("--actor", default="support-a")
    d2_smoke.add_argument("--db", default=str(DEFAULT_DB_PATH))
    d2_smoke.add_argument("--checkpoint-db", default=str(DEFAULT_CHECKPOINT_DB_PATH))

    d3_start = subparsers.add_parser("d3-start", help="Run real D2 investigation and persist a Plan before the HITL interrupt.")
    d3_start.add_argument("--actor", default="support-a", help="Trusted task submitter actor ID.")
    d3_start.add_argument("--executor", default="executor-a", help="Trusted executor service ID.")
    d3_start.add_argument("--db", default=str(DEFAULT_DB_PATH))
    d3_start.add_argument("--checkpoint-db", default=str(DEFAULT_CHECKPOINT_DB_PATH))

    d3_approve = subparsers.add_parser("d3-approve", help="Persist an independent human approval and resume a D3 checkpoint.")
    d3_approve.add_argument("--actor", required=True, help="Trusted approver actor ID.")
    d3_approve.add_argument("--thread-id", required=True)
    d3_approve.add_argument("--plan-hash", required=True)
    d3_approve.add_argument("--decision", choices=("APPROVED", "REJECTED"), required=True)
    d3_approve.add_argument("--executor", default="executor-a", help="Trusted executor service ID.")
    d3_approve.add_argument("--db", default=str(DEFAULT_DB_PATH))
    d3_approve.add_argument("--checkpoint-db", default=str(DEFAULT_CHECKPOINT_DB_PATH))

    d3_resume = subparsers.add_parser("d3-resume", help="Safely resume a D3 checkpoint from its persisted Domain state.")
    d3_resume.add_argument("--actor", required=True, help="Trusted task owner or authorized approver actor ID.")
    d3_resume.add_argument("--thread-id", required=True)
    d3_resume.add_argument("--executor", default="executor-a", help="Trusted executor service ID.")
    d3_resume.add_argument("--db", default=str(DEFAULT_DB_PATH))
    d3_resume.add_argument("--checkpoint-db", default=str(DEFAULT_CHECKPOINT_DB_PATH))

    d3_cancel = subparsers.add_parser("d3-cancel", help="Cancel an active persisted D3 Plan.")
    d3_cancel.add_argument("--actor", required=True, help="Trusted task submitter actor ID.")
    d3_cancel.add_argument("--task-id", required=True)
    d3_cancel.add_argument("--plan-hash", required=True)
    d3_cancel.add_argument("--reason", required=True)
    d3_cancel.add_argument("--db", default=str(DEFAULT_DB_PATH))

    d3_smoke = subparsers.add_parser("d3-smoke", help="Run a real-model, real-MCP D3 workflow with approval in a second OS process.")
    d3_smoke.add_argument("--db", default=str(DEFAULT_DB_PATH))
    d3_smoke.add_argument("--checkpoint-db", default=str(DEFAULT_CHECKPOINT_DB_PATH))
    d3_smoke.add_argument("--evidence-dir", default="docs/evidence/d3")

    memory = subparsers.add_parser("memory", help="Manage a trusted, source-verified episodic memory.")
    memory_commands = memory.add_subparsers(dest="memory_command", required=True)
    memory_candidate = memory_commands.add_parser("candidate", help="Create an unconfirmed memory candidate from a completed D3 recovery.")
    memory_candidate.add_argument("--task-id", required=True)
    memory_candidate.add_argument("--actor", required=True)
    memory_candidate.add_argument("--db", default=str(DEFAULT_DB_PATH))
    memory_confirm = memory_commands.add_parser("confirm", help="Activate a source-verified memory as a trusted approver.")
    memory_confirm.add_argument("--memory-id", required=True)
    memory_confirm.add_argument("--actor", required=True)
    memory_confirm.add_argument("--db", default=str(DEFAULT_DB_PATH))
    memory_revoke = memory_commands.add_parser("revoke", help="Revoke an active memory as a trusted approver.")
    memory_revoke.add_argument("--memory-id", required=True)
    memory_revoke.add_argument("--actor", required=True)
    memory_revoke.add_argument("--db", default=str(DEFAULT_DB_PATH))
    memory_list = memory_commands.add_parser("list", help="List applicable active memories for a trusted task.")
    memory_list.add_argument("--task-id", required=True)
    memory_list.add_argument("--actor", required=True)
    memory_list.add_argument("--db", default=str(DEFAULT_DB_PATH))

    d5_smoke = subparsers.add_parser("d5-smoke", help="Run the D5 real-model, real-MCP cross-task memory smoke.")
    d5_smoke.add_argument("--db", default=".runtime/d5-domain.sqlite3")
    d5_smoke.add_argument("--checkpoint-db", default=".runtime/d5-checkpoints.sqlite3")
    d5_smoke.add_argument("--evidence-dir", default="docs/evidence/d5")
    return parser


def main() -> int:
    load_local_environment()
    args = parser_for_cli().parse_args()
    db_path = database_path(getattr(args, "db", None))
    if args.command == "reset":
        reset_fixture(db_path, args.scenario)
        emit("fixture_reset", scenario=args.scenario, database=str(db_path))
        return 0
    if args.command == "serve":
        server = make_server(db_path, args.tenant, args.host, args.port)
        emit("api_listening", host=args.host, port=args.port, tenant_id=args.tenant)
        try:
            server.serve_forever(poll_interval=0.2)
        except KeyboardInterrupt:
            pass
        finally:
            server.server_close()
        return 0
    if args.command == "probe":
        result = probe_orders(db_path, args.base_url, args.tenant, args.integration)
        emit("business_probe", **result.public_dict())
        return 0
    if args.command == "investigate":
        from opspilot.domain.d2 import create_task_binding
        from opspilot.investigator import run_investigation

        binding = create_task_binding(db_path, args.actor, args.service, args.integration)
        emit("task_binding_created", task_binding={key: binding[key] for key in (
            "task_id", "thread_id", "tenant_id", "actor_id", "service_id", "integration_id", "principal_id", "ticket_id"
        )})
        try:
            saved = asyncio.run(
                run_investigation(
                    str(binding["task_id"]),
                    args.actor,
                    db_path=db_path,
                    checkpoint_db_path=args.checkpoint_db,
                )
            )
        except Exception as error:
            from opspilot.smokes.tool_call import safe_error_details

            emit("d2_investigation_failed", error=safe_error_details(error))
            return 1
        emit("d2_investigation_report", **saved)
        return 0
    if args.command == "resume":
        from opspilot.investigator import run_investigation

        try:
            saved = asyncio.run(
                run_investigation(
                    args.thread_id,
                    args.actor,
                    db_path=db_path,
                    checkpoint_db_path=args.checkpoint_db,
                    resume=True,
                )
            )
        except Exception as error:
            from opspilot.smokes.tool_call import safe_error_details

            emit("d2_resume_failed", error=safe_error_details(error))
            return 1
        emit("d2_investigation_report", **saved)
        return 0
    if args.command == "d2-smoke":
        from opspilot.domain.d2 import (
            create_task_binding,
            inject_read_tool_failure_for_test,
        )
        from opspilot.domain.database import get_integration_info as read_integration, reset_fixture
        from opspilot.investigator import run_investigation

        fixture_scenario = "S1_DISABLED" if args.scenario == "DISABLED" else "S1_POS"
        reset_fixture(db_path, fixture_scenario)
        binding = create_task_binding(db_path, args.actor, "orders-demo", "integration-a")
        if args.scenario == "INSUFFICIENT":
            inject_read_tool_failure_for_test(
                db_path, str(binding["task_id"]), "get_auth_policy", "POLICY_SOURCE_UNAVAILABLE", calls=6
            )
        emit("d2_smoke_task", scenario=args.scenario, task_id=binding["task_id"], thread_id=binding["thread_id"])
        try:
            saved = asyncio.run(
                run_investigation(
                    str(binding["task_id"]),
                    args.actor,
                    db_path=db_path,
                    checkpoint_db_path=args.checkpoint_db,
                )
            )
        except Exception as error:
            from opspilot.smokes.tool_call import safe_error_details

            emit("d2_smoke_failed", scenario=args.scenario, error=safe_error_details(error))
            return 1
        report = saved["report"]
        decision = report["gate_decision"]["decision"]
        current = read_integration(db_path, "tenant-a", "integration-a")
        expected = {"POS": "READY", "DISABLED": "NO_ACTION", "INSUFFICIENT": "INCONCLUSIVE"}[args.scenario]
        passed = decision == expected and int(current["config_version"]) == 7
        emit(
            "d2_smoke_result",
            scenario=args.scenario,
            expected_gate=expected,
            actual_gate=decision,
            config_version_after=current["config_version"],
            configuration_unchanged=int(current["config_version"]) == 7,
            passed=passed,
            report_ref=saved["report_ref"],
            report=report,
        )
        return 0 if passed else 1
    if args.command == "d3-start":
        from opspilot.domain.d2 import create_task_binding
        from opspilot.domain.d3 import get_plan_for_task
        from opspilot.investigator import run_investigation

        binding = create_task_binding(db_path, args.actor, "orders-demo", "integration-a")
        try:
            result = asyncio.run(run_investigation(
                str(binding["task_id"]), args.actor, db_path=db_path,
                checkpoint_db_path=args.checkpoint_db, d3_mode=True, executor_id=args.executor,
            ))
        except Exception as error:
            from opspilot.smokes.tool_call import safe_error_details

            emit("d3_start_failed", process_id=os.getpid(), error=safe_error_details(error))
            return 1
        state = dict(result.get("graph_state", {}))
        action_state = dict(result.get("action_state", {}))
        plan = get_plan_for_task(db_path, str(binding["task_id"]), str(state["plan_hash"]), args.actor) if state.get("plan_hash") else None
        emit(
            "d3_plan_waiting_approval" if action_state.get("task_binding", {}).get("status") == "WAITING_APPROVAL" else "d3_investigation_complete",
            process_id=os.getpid(),
            task_binding=action_state.get("task_binding", {key: binding[key] for key in ("task_id", "thread_id", "tenant_id", "actor_id", "service_id", "integration_id", "principal_id", "ticket_id")}),
            stage=state.get("stage"),
            gate_decision=state.get("gate_decision"),
            plan_hash=state.get("plan_hash"),
            plan=plan,
            graph_only_plan_reference="plan" not in state and "canonical_request_json" not in state,
            next_nodes=result.get("next_nodes", []),
        )
        return 0
    if args.command == "d3-approve":
        from opspilot.domain.d3 import submit_plan_approval
        from opspilot.domain.d2 import get_task_binding
        from opspilot.investigator import run_investigation

        try:
            approval = submit_plan_approval(db_path, args.thread_id, args.actor, args.plan_hash, args.decision)
            binding = get_task_binding(db_path, str(approval["task_id"]))
            result = asyncio.run(run_investigation(
                args.thread_id, args.actor, db_path=db_path,
                checkpoint_db_path=args.checkpoint_db, resume=True, d3_mode=True,
                executor_id=args.executor,
                resume_command={"approval_id": approval["approval_id"], "plan_hash": args.plan_hash},
            ))
        except Exception as error:
            from opspilot.smokes.tool_call import safe_error_details

            emit("d3_approval_resume_failed", process_id=os.getpid(), error=safe_error_details(error))
            return 1
        state = dict(result.get("graph_state", {}))
        action_state = dict(result.get("action_state", {}))
        public_state = d3_public_action_summary(action_state)
        business_outcome = "RECOVERED" if any(
            item.get("action_kind") == "DELIVER" and item.get("status") == "COMMITTED"
            for item in public_state.get("action_ledgers", [])
        ) else (public_state.get("local_reports", [{}])[-1].get("outcome") if public_state.get("local_reports") else "UNRESOLVED")
        emit(
            "d3_approval_process_completed",
            process_id=os.getpid(),
            task_id=binding["task_id"],
            thread_id=args.thread_id,
            plan_hash=args.plan_hash,
            approval_id=approval["approval_id"],
            approval_decision=approval["decision"],
            graph_stage=state.get("stage"),
            graph_signals={key: state.get(key) for key in ("plan_id", "plan_hash", "repair_action_id", "repair_ledger_ref", "verification_id", "frozen_report_ref", "deliver_action_id", "deliver_ledger_ref", "local_report_ref")},
            business_outcome=business_outcome,
            action_state=public_state,
        )
        return 0
    if args.command == "d3-resume":
        from opspilot.investigator import run_investigation

        try:
            result = asyncio.run(run_investigation(
                args.thread_id,
                args.actor,
                db_path=db_path,
                checkpoint_db_path=args.checkpoint_db,
                resume=True,
                d3_mode=True,
                executor_id=args.executor,
            ))
        except Exception as error:
            from opspilot.smokes.tool_call import safe_error_details

            emit("d3_recovery_resume_failed", process_id=os.getpid(), error=safe_error_details(error))
            return 1
        graph_state = dict(result.get("graph_state", {}))
        action_state = d3_public_action_summary(dict(result.get("action_state", {})))
        emit(
            "d3_recovery_resumed",
            process_id=os.getpid(),
            task_id=result.get("task_id"),
            thread_id=result.get("thread_id"),
            graph_stage=graph_state.get("stage"),
            blocked_reason=graph_state.get("blocked_reason"),
            next_nodes=result.get("next_nodes", []),
            graph_signals={key: graph_state.get(key) for key in (
                "plan_id", "plan_hash", "repair_action_id", "repair_ledger_ref", "verification_id",
                "frozen_report_ref", "deliver_action_id", "deliver_ledger_ref", "local_report_ref",
            )},
            action_state=action_state,
        )
        return 2 if graph_state.get("blocked_reason") == "ACTION_OUTCOME_UNKNOWN" else 0
    if args.command == "d3-cancel":
        from opspilot.domain.d3 import cancel_plan

        result = cancel_plan(db_path, args.task_id, args.plan_hash, args.actor, args.reason)
        emit("d3_plan_cancelled", authorization=result)
        return 0
    if args.command == "d3-smoke":
        from opspilot.smokes.d3 import run_smoke

        return run_smoke(db_path, args.checkpoint_db, args.evidence_dir)
    if args.command == "memory":
        from opspilot.domain.episodic_memory import (
            confirm_memory,
            create_memory_candidate,
            list_applicable_memories,
            revoke_memory,
        )

        if args.memory_command == "candidate":
            result = create_memory_candidate(db_path, args.task_id, args.actor)
        elif args.memory_command == "confirm":
            result = confirm_memory(db_path, args.memory_id, args.actor)
        elif args.memory_command == "revoke":
            result = revoke_memory(db_path, args.memory_id, args.actor)
        elif args.memory_command == "list":
            from opspilot.domain.d2 import get_task_binding

            binding = get_task_binding(db_path, args.task_id)
            if binding["actor_id"] != args.actor:
                from opspilot.domain.episodic_memory import MemoryScopeDenied

                raise MemoryScopeDenied("Only the task owner may list memories from the CLI.")
            result = {"memories": list_applicable_memories(db_path, args.task_id, "auth_401")}
        else:
            raise AssertionError("Unknown memory operation.")
        emit(f"memory_{args.memory_command}", result=result)
        return 0
    if args.command == "d5-smoke":
        from opspilot.smokes.d5 import run_smoke

        return run_smoke(db_path, args.checkpoint_db, args.evidence_dir)
    if args.kind == "tool-call":
        from opspilot.smokes.tool_call import run_smoke

        return run_smoke()
    if args.kind == "mcp":
        from opspilot.smokes.mcp import main as run_mcp

        return run_mcp()
    if args.kind == "checkpoint":
        from opspilot.smokes.checkpoint import run_smoke

        return run_smoke()
    if args.kind == "s1":
        from opspilot.smokes.s1 import run_smoke

        return run_smoke()
    raise AssertionError("Unsupported command.")


if __name__ == "__main__":
    raise SystemExit(main())
