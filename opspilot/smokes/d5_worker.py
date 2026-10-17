from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys

from opspilot.config import load_local_environment
from opspilot.domain.d2 import authorize_thread_resume, read_report
from opspilot.investigator import run_investigation


def main() -> int:
    load_local_environment()
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("start", "resume", "run"))
    parser.add_argument("--task-id")
    parser.add_argument("--thread-id")
    parser.add_argument("--actor", required=True)
    parser.add_argument("--db", required=True)
    parser.add_argument("--checkpoint-db", required=True)
    args = parser.parse_args()
    identity = args.thread_id if args.mode == "resume" else args.task_id
    if not identity:
        parser.error("start/run require --task-id; resume requires --thread-id")
    try:
        result = asyncio.run(run_investigation(
            identity,
            args.actor,
            db_path=args.db,
            checkpoint_db_path=args.checkpoint_db,
            resume=args.mode == "resume",
            _interrupt_after_for_test=("investigate",) if args.mode == "start" else (),
        ))
    except Exception as error:
        print(json.dumps({
            "event": "d5_worker_failed",
            "pid": os.getpid(),
            "mode": args.mode,
            "error_class": type(error).__name__,
            "error": str(error)[:500],
        }, ensure_ascii=False, sort_keys=True))
        return 1
    task_id = str(result.get("task_id", args.task_id or ""))
    if not task_id and args.mode == "resume" and args.thread_id:
        task_id = str(authorize_thread_resume(args.db, args.thread_id, args.actor)["task_id"])
    report = read_report(args.db, task_id) if args.mode != "start" else None
    gate = report.get("report", {}).get("gate_decision") if report else None
    graph_state = result.get("graph_state", {})
    print(json.dumps({
        "event": "d5_worker_complete",
        "pid": os.getpid(),
        "mode": args.mode,
        "task_id": task_id,
        "thread_id": result.get("thread_id", args.thread_id),
        "paused_after_model_call": bool(result.get("d5_paused_after_model_call")),
        "next_nodes": result.get("next_nodes", []),
        "gate_decision": gate or (graph_state.get("gate_decision") if isinstance(graph_state, dict) else None),
        "model_calls": int(result.get("budget", {}).get("MODEL", 0)) if isinstance(result.get("budget"), dict) else None,
    }, ensure_ascii=False, sort_keys=True))
    if args.mode == "start" and not result.get("d5_paused_after_model_call"):
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
