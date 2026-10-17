from __future__ import annotations

import argparse
import json
import os
import uuid

from opspilot.domain.d2 import BudgetExhausted, attempt_counts, reserve_attempt


def emit(event: str, **fields: object) -> None:
    print(json.dumps({"event": event, **fields}, sort_keys=True))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("reserve", "read-and-reject"))
    parser.add_argument("--db", required=True)
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--limit", type=int, default=1)
    args = parser.parse_args()
    if args.mode == "reserve":
        attempt_id, used = reserve_attempt(
            args.db,
            args.task_id,
            "MCP",
            args.limit,
            call_id=f"restart-test-{uuid.uuid4()}",
            tool_call_id="cross-process-budget-test",
            tool_name="get_integration_config",
            argument_digest="restart-test",
        )
        emit("d2_budget_attempt_reserved", pid=os.getpid(), attempt_id=attempt_id, mcp_used=used)
        return 0

    counts = attempt_counts(args.db, args.task_id)
    try:
        reserve_attempt(
            args.db,
            args.task_id,
            "MCP",
            args.limit,
            call_id=f"restart-test-{uuid.uuid4()}",
            tool_call_id="cross-process-budget-test",
            tool_name="get_integration_config",
            argument_digest="restart-test",
        )
    except BudgetExhausted as error:
        emit("d2_budget_persisted_after_restart", pid=os.getpid(), model_used=counts["MODEL"], mcp_used=counts["MCP"], limit=error.limit, next_attempt_denied=True)
        return 0
    emit("d2_budget_restart_failure", model_used=counts["MODEL"], mcp_used=counts["MCP"], limit=args.limit)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
