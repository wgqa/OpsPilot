from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path

from opspilot.config import DEFAULT_CHECKPOINT_DB_PATH, DEFAULT_DB_PATH, database_path, load_local_environment
from opspilot.domain.api import make_server
from opspilot.domain.client import probe_orders
from opspilot.domain.database import reset_fixture


def emit(event: str, **fields: object) -> None:
    print(json.dumps({"event": event, **fields}, sort_keys=True, default=str))


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
