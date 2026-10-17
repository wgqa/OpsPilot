from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main(argv: list[str]) -> int:
    if len(argv) != 5:
        raise SystemExit("usage: m1_crash_worker.py <db> <checkpoint_db> <thread_id> <actor_id>")
    _, db_path, checkpoint_path, thread_id, actor_id = argv
    from opspilot.domain.d3 import D3PreconditionRejected
    from opspilot.investigator import run_investigation

    try:
        asyncio.run(
            run_investigation(
                thread_id,
                actor_id,
                db_path=db_path,
                checkpoint_db_path=checkpoint_path,
                resume=True,
                d3_mode=True,
                executor_id="executor-a",
            )
        )
    except D3PreconditionRejected as error:
        print(json.dumps({
            "event": "old_checkpoint_resume_blocked",
            "pid": os.getpid(),
            "reason": str(error),
            "thread_id": thread_id,
        }, sort_keys=True), flush=True)
        return 0
    print(json.dumps({
        "event": "unexpected_resume_success",
        "pid": os.getpid(),
        "thread_id": thread_id,
    }, sort_keys=True), flush=True)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
