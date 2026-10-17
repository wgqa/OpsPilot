from __future__ import annotations

import argparse
import json
import os
import sqlite3
from pathlib import Path
from typing import TypedDict

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt


class SmokeState(TypedDict, total=False):
    task_id: str
    stage: str
    draft_marker: str
    evidence_count: int
    resume_answer: str


def emit(event: str, **fields: object) -> None:
    print(json.dumps({"event": event, **fields}, sort_keys=True, default=str))


def ensure_owner_db(path: str | Path) -> None:
    owner_path = Path(path).resolve()
    owner_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(owner_path) as connection:
        connection.execute(
            "CREATE TABLE IF NOT EXISTS thread_owners "
            "(thread_id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, owner_id TEXT NOT NULL)"
        )


def authorize_thread(path: str | Path, thread_id: str, actor_id: str, *, register: bool) -> bool:
    ensure_owner_db(path)
    with sqlite3.connect(Path(path).resolve()) as connection:
        row = connection.execute(
            "SELECT tenant_id, owner_id FROM thread_owners WHERE thread_id = ?",
            (thread_id,),
        ).fetchone()
        if register and row is None:
            connection.execute(
                "INSERT INTO thread_owners(thread_id, tenant_id, owner_id) VALUES (?, ?, ?)",
                (thread_id, "tenant-a", actor_id),
            )
            return True
    return bool(row and row[0] == "tenant-a" and row[1] == actor_id)


def build_graph(checkpointer: SqliteSaver):
    def wait_for_resume(state: SmokeState) -> dict[str, object]:
        answer = interrupt({"kind": "d1_smoke", "task_id": state["task_id"]})
        return {"resume_answer": str(answer), "stage": "resumed"}

    def finish(state: SmokeState) -> dict[str, object]:
        return {"stage": "complete", "evidence_count": state["evidence_count"]}

    builder = StateGraph(SmokeState)
    builder.add_node("wait_for_resume", wait_for_resume)
    builder.add_node("finish", finish)
    builder.add_edge(START, "wait_for_resume")
    builder.add_edge("wait_for_resume", "finish")
    builder.add_edge("finish", END)
    return builder.compile(checkpointer=checkpointer)


def run(args: argparse.Namespace) -> int:
    os.environ["LANGGRAPH_STRICT_MSGPACK"] = "true"
    thread_id = args.thread_id
    if args.mode == "start":
        if not authorize_thread(args.owner_db, thread_id, args.actor, register=True):
            emit("checkpoint_owner_register_denied", thread_id=thread_id)
            return 3
    elif not authorize_thread(args.owner_db, thread_id, args.actor, register=False):
        emit("checkpoint_resume_denied", thread_id=thread_id, reason="trusted_thread_owner_mismatch")
        return 3

    config = {"configurable": {"thread_id": thread_id}}
    with SqliteSaver.from_conn_string(str(Path(args.checkpoint_db).resolve())) as checkpointer:
        graph = build_graph(checkpointer)
        if args.mode == "start":
            graph.invoke(
                {
                    "task_id": "d1-task",
                    "stage": "waiting_for_resume",
                    "draft_marker": "draft-401",
                    "evidence_count": 2,
                },
                config,
            )
            snapshot = graph.get_state(config)
            values = snapshot.values
            if values.get("stage") != "waiting_for_resume" or not snapshot.tasks:
                emit("checkpoint_interrupt_failed", thread_id=thread_id, stage=values.get("stage"))
                return 1
            emit(
                "checkpoint_interrupt_saved",
                pid=os.getpid(),
                thread_id=thread_id,
                task_id=values["task_id"],
                stage=values["stage"],
                draft_marker=values["draft_marker"],
                evidence_count=values["evidence_count"],
                interrupted=True,
            )
            return 0

        if args.mode != "resume":
            raise ValueError("Unsupported worker mode.")
        snapshot_before = graph.get_state(config)
        before = snapshot_before.values
        if before.get("stage") != "waiting_for_resume" or not snapshot_before.tasks:
            emit("checkpoint_resume_missing_prior_state", thread_id=thread_id)
            return 1
        result = graph.invoke(Command(resume={"decision": "continue"}), config)
        snapshot_after = graph.get_state(config)
        after = snapshot_after.values
        preserved = all(after.get(key) == before.get(key) for key in ("task_id", "draft_marker", "evidence_count"))
        if not preserved or result.get("stage") != "complete" or after.get("stage") != "complete":
            emit("checkpoint_resume_assertion_failed", thread_id=thread_id)
            return 1
        emit(
            "checkpoint_resume_pass",
            pid=os.getpid(),
            thread_id=thread_id,
            state_before={key: before.get(key) for key in ("task_id", "stage", "draft_marker", "evidence_count")},
            state_after={key: after.get(key) for key in ("task_id", "stage", "draft_marker", "evidence_count", "resume_answer")},
            preserved_state=preserved,
            completed=True,
        )
        return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("start", "resume"))
    parser.add_argument("--checkpoint-db", required=True)
    parser.add_argument("--owner-db", required=True)
    parser.add_argument("--thread-id", required=True)
    parser.add_argument("--actor", required=True)
    return run(parser.parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
