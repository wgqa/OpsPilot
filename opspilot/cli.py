from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from opspilot.config import DEFAULT_DB_PATH, database_path, load_local_environment
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
