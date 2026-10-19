from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from langchain_core.messages import AIMessage

from opspilot import investigator
from opspilot.config import load_local_environment


class NoToolModel:
    def bind_tools(self, *_args, **_kwargs):
        return self

    async def ainvoke(self, _messages):
        return AIMessage(content="Request ID 尚未由当前证据确认，请先澄清。")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", choices=("pause", "resume"), required=True)
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--checkpoint-db", type=Path, required=True)
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args()

    load_local_environment()
    investigator.ChatOpenAI = lambda **_kwargs: NoToolModel()
    result = asyncio.run(investigator.run_investigation(
        args.task_id, "support-a", db_path=args.db,
        checkpoint_db_path=args.checkpoint_db,
        resume=args.phase == "resume",
        d3_mode=True, s2_mode=True, executor_id="executor-a", run_id=args.run_id,
        _interrupt_after_for_test=("investigate",) if args.phase == "pause" else (),
    ))
    graph_state = result.get("graph_state", {})
    print(json.dumps({
        "phase": args.phase,
        "paused_after_model_call": result.get("d5_paused_after_model_call", False),
        "stage": graph_state.get("stage"),
        "gate": graph_state.get("gate_decision"),
        "model_attempts": graph_state.get("budget", {}).get("MODEL"),
    }, ensure_ascii=False), flush=True)
    if args.phase == "pause":
        # Simulate worker process loss after the graph persisted its checkpoint.
        os._exit(73)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
