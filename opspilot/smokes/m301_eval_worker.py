from __future__ import annotations

import argparse
import asyncio
import json
import os

from opspilot.config import load_local_environment
from opspilot.investigator import run_investigation


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", required=True)
    parser.add_argument("--checkpoint-db", required=True)
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--actor-id", required=True)
    parser.add_argument("--s2", action="store_true")
    parser.add_argument("--memory-off", action="store_true")
    args = parser.parse_args()
    load_local_environment()
    try:
        result = asyncio.run(run_investigation(
            args.task_id, args.actor_id, db_path=args.db, checkpoint_db_path=args.checkpoint_db,
            run_id=args.run_id, s2_mode=args.s2, _memory_enabled_for_test=not args.memory_off,
        ))
        state = result.get("graph_state", {})
        print(json.dumps({
            "event": "m301_worker_complete", "pid": os.getpid(),
            "task_id": args.task_id, "run_id": args.run_id,
            "next_nodes": result.get("next_nodes", []),
            "gate_decision": state.get("gate_decision") if isinstance(state, dict) else None,
        }, ensure_ascii=False, sort_keys=True))
        return 0
    except Exception as error:
        safe_message = str(error)[:300]
        print(json.dumps({
            "event": "m301_worker_failed", "pid": os.getpid(),
            "task_id": args.task_id, "run_id": args.run_id,
            "error_class": type(error).__name__, "error": safe_message,
        }, ensure_ascii=False, sort_keys=True))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
