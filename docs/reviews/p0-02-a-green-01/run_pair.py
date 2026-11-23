"""Run the frozen turn text plus an explicit-confirmation arm through the real SDK."""
from __future__ import annotations

import argparse
import asyncio
from contextlib import closing
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import time
from unittest.mock import patch

FROZEN = Path(__file__).resolve().parent.parent / "p0-02-red-design-01/repro.py"
spec = importlib.util.spec_from_file_location("frozen_p002", FROZEN)
frozen = importlib.util.module_from_spec(spec)
spec.loader.exec_module(frozen)

from fastapi.testclient import TestClient
from langchain_core.messages import SystemMessage

from opspilot import assistant

from opspilot.domain.database import connect, reset_fixture
from opspilot.domain.d2 import configure_s3_experiment_budget
from opspilot.domain.s3 import prepare_s3_fixture
from opspilot.domain import task_control as tc
from opspilot.web.app import create_app
from opspilot.web.worker import _dispatch_run


ITEM_IDS = ("event", "protocol", "time", "report")
BLOCK_PREFIX = "CURRENT TASK CONDITIONS"


def items(answer):
    blocks = [
        message["content"] for message in answer["request"]["messages"]
        if message["role"] == "system" and message["content"].startswith(BLOCK_PREFIX)
    ]
    assert len(blocks) == 1, f"Expected one current conditions block, got {len(blocks)}"
    return {item["item_id"]: item for item in json.loads(blocks[0][blocks[0].index("["):])}


def change(item_id, message_id, body, *, operation="ADD", expected_version=0):
    return {
        "item_id": item_id, "operation": operation, "expected_version": expected_version,
        "source_message_id": message_id, "source_digest": hashlib.sha256(body.encode()).hexdigest(),
    }


async def run(root, output, baseline):
    db = root / "domain.sqlite"
    reset_fixture(db, "S1_POS")
    prepare_s3_fixture(db, "DELIVERED_PENDING", order_id="p002-order", contract_version=2)
    owner = tc.trusted_identity(db, "support-a")
    wire = frozen.Wire(output)
    checkpoint = root / "checkpoint.sqlite"
    epoch = tc.register_worker_owner(db, frozen.WORKER, os.getpid())
    protected = frozen.protected_counts(db)
    origin = "http://p002.test"
    password = "p002-offline"
    app = create_app(db_path=db, start_worker=False, expected_origin=origin, credentials={"support-a": password})
    turns = []

    async def dispatch(case, receipt, *, path=db, worker_epoch=epoch, cp=checkpoint):
        start = time.monotonic()
        run_id = receipt["run_id"]
        wire.target = {"case": case, "run_id": run_id, "task_id": receipt["task_id"]}
        previous = len(wire.calls)
        error = None
        try:
            await _dispatch_run(path, cp, frozen.WORKER, "executor-a", frozen.persisted_run(path, run_id),
                                worker_epoch, assistant_model_factory=wire.factory)
        except tc.TaskControlError as failure:
            error = failure.code
        calls = wire.calls[previous:]
        answer = next((entry for entry in reversed(calls) if entry["phase"] == "answer"), None)
        turns.append({
            **wire.target, "status": frozen.persisted_run(path, run_id)["status"], "error": error,
            "calls": len(calls), "duration_ms": round(1000 * (time.monotonic() - start), 2),
        })
        frozen.save(output / "turns.json", turns)
        return answer

    def read_control(path):
        with connect(path) as connection:
            return dict(connection.execute("SELECT * FROM task_controls WHERE task_id=?", (task_id,)).fetchone())

    def apply_receipt(path, receipt):
        tc.claim_task_run(path, owner, receipt["run_id"])
        applied = tc.apply_pending_critical_inputs(path, owner, receipt["run_id"])
        tc.finish_task_run(path, owner, receipt["run_id"], "WAITING_INPUT")
        return applied

    with TestClient(app) as client:
        login = client.post("/api/auth/login", headers={"Origin": origin},
                            json={"actor_id": "support-a", "password": password})
        assert login.status_code == 200
        headers = {"Origin": origin, "X-CSRF-Token": login.json()["csrf_token"]}
        created = client.post("/api/sessions", headers=headers)
        assert created.status_code == 201
        session_id = created.json()["session_id"]
        base = f"/api/sessions/{session_id}"

        def post(route, key, payload, *, assert_accepted=True):
            result = client.post(base + route, json=payload, headers={**headers, "Idempotency-Key": key})
            if assert_accepted:
                assert result.status_code == 202, result.text
                return result.json()
            return result

        post("/assistant/messages", "public", {"body": frozen.PUBLIC})
        foreign = post("/assistant/order", "foreign", {"order_id": "p002-order", "initial_message": frozen.FOREIGN})
        target = post("/assistant/order", "bound", {"order_id": "p002-order", "initial_message": frozen.GOAL})
        task_id = target["task_id"]
        configure_s3_experiment_budget(db, task_id, 16, 10)
        schedule = [target]
        sources = {}
        by_turn = dict(zip((2, 4, 6, 8), zip(ITEM_IDS, frozen.CONDITIONS)))
        for index in range(2, 24):
            filler = f"Turn {index} compares ordinary support labels. " + (
                "A sample status page labels accepted requests and displays ordinary maintenance notes. " * 49
            )
            item_id, text = by_turn.get(index, (None, filler))
            turn = post("/assistant/messages", f"turn-{index}", {"task_id": task_id, "body": text})
            schedule.append(turn)
            if item_id is not None:
                sources[item_id] = change(item_id, turn["message_id"], text)
        for index, turn in enumerate(schedule, 1):
            assert await dispatch(f"turn-{index}", turn)

        revision = read_control(db)["control_revision"]
        edits = {
            "task_id": task_id, "input_kind": "CORRECT_TASK_INPUT",
            "body": "Confirm the four listed investigation requirements.",
            "expected_control_revision": revision, "condition_changes": list(sources.values()),
        }
        rejected = post("/assistant/messages", "no-chat-promotion", edits, assert_accepted=False)
        assert rejected.status_code == 422
        if baseline:
            # Compare the same read-side assertions against the frozen checkout.
            # Save the API rejection and still collect the unmodified answer wire.
            attempt = post("/messages", "confirm", edits, assert_accepted=False)
            frozen.save(output / "confirmation.json", {"status": attempt.status_code, "response": attempt.json()})
            assert attempt.status_code == 422
        else:
            bad_edit = change("foreign", foreign["message_id"], frozen.FOREIGN)
            denied = post("/messages", "foreign-source", {**edits, "condition_changes": [bad_edit]}, assert_accepted=False)
            assert denied.status_code == 404, denied.text
            confirmed = post("/messages", "confirm", edits)
            assert confirmed == post("/messages", "confirm", edits)
            conflict = post("/messages", "confirm", {**edits, "body": "Different confirmed operation."}, assert_accepted=False)
            assert conflict.status_code == 409, conflict.text
            assert read_control(db)["applied_critical_message_seq"] == 0
            applied = apply_receipt(db, confirmed)
            frozen.save(output / "confirmation.json", {"receipt": confirmed, "application": applied})
        final = post("/assistant/messages", "turn-24", {"task_id": task_id, "body": frozen.FINAL})

    answer = await dispatch("turn-24", final)
    assert answer
    frozen.save(output / "final-sdk.json", answer)
    data = frozen.snapshot(db, session_id, task_id, final["run_id"])
    frozen.save(output / "summary-state.json", {
        "summaries": data["summaries"], "dependencies": data["dependencies"], "control": data["control"],
    })
    expected = dict(zip(ITEM_IDS, frozen.CONDITIONS))
    coverage = frozen.scan_answer(answer, (*frozen.CONDITIONS, frozen.PUBLIC, frozen.FOREIGN))
    frozen.save(output / "coverage.json", coverage)
    assert len(data["summaries"]) >= 2, "Expected multiple real compaction generations"
    assert coverage[frozen.PUBLIC] and not coverage[frozen.FOREIGN]
    active = items(answer)
    assert {key: item["text"] for key, item in active.items()} == expected
    assert all(item["state"] == "ACTIVE" and item["version"] == 1 for item in active.values())
    assert all(
        active[key]["source_message_id"] == ref["source_message_id"]
        and active[key]["source_digest"] == ref["source_digest"] for key, ref in sources.items()
    )
    assert protected == frozen.protected_counts(db)
    from opspilot.domain.context_engineering import estimate_messages_tokens

    condition_messages = [
        message for message in answer["request"]["messages"] if message["content"].startswith(BLOCK_PREFIX)
    ]

    records = {}
    for label, texts, key, operation in (
        ("replace", (frozen.FULL_DAY,), "time", "REPLACE"),
        ("withdraw", (frozen.WITHDRAW,), "report", "REVOKE"),
        ("hypothesis", (frozen.HYPOTHESIS,), None, None),
        ("conflict", frozen.UNCONFIRMED, None, None),
        ("invalid-source", (), None, None),
        ("scope-revoked", (), None, None),
        ("aborted", (), None, None),
        ("budget", (), None, None),
        ("checkpoint-stale", (), None, None),
        ("checkpoint-clean", (), None, None),
    ):
        branch = root / f"{label}.sqlite"
        with closing(sqlite3.connect(db)) as source, closing(sqlite3.connect(branch)) as copy:
            source.backup(copy)
        branch_epoch = tc.register_worker_owner(branch, frozen.WORKER, os.getpid())

        def admit(body, key, **kwargs):
            return tc.admit_task_message(
                branch, owner, session_id=session_id, task_id=task_id, body=body, idempotency_key=key,
                **({"input_kind": "CHAT_READONLY", "assistant_core": True} if not kwargs else kwargs),
            )

        for index, text in enumerate(texts):
            query = admit(text, f"input-{index}")
        if operation:
            from opspilot.domain.task_conditions import ConditionChange

            edit = change(key, query["message_id"], texts[0], operation=operation, expected_version=1)
            receipt = admit(
                "Confirm the selected investigation requirement change.", "change",
                input_kind="CORRECT_TASK_INPUT", expected_control_revision=read_control(branch)["control_revision"],
                condition_changes=[ConditionChange.model_validate(edit)],
            )
            apply_receipt(branch, receipt)
        if label == "invalid-source":
            with connect(branch) as connection:
                connection.execute("UPDATE messages SET body=? WHERE message_id=?", ("changed source", sources["event"]["source_message_id"]))
        if label == "scope-revoked":
            with connect(branch) as connection:
                connection.execute(
                    """UPDATE principal_scope_grants SET granted_scopes_json='[]', grant_version=grant_version+1
                       WHERE tenant_id='tenant-a' AND principal_id=(SELECT principal_id FROM task_bindings WHERE task_id=?)""",
                    (task_id,),
                )
        next_query = admit(frozen.FINAL if label != "budget" else frozen.FINAL + (" large request material" * 4000), "continue")
        if label == "aborted":
            tc.abort_task(branch, owner, task_id=task_id, reason="Offline abort", idempotency_key="abort")
        cp = root / f"{label}-checkpoint.sqlite"
        if label.startswith("checkpoint"):
            reached = asyncio.Event()
            base_seed = assistant._assistant_chat_seed

            async def stop_before_provider(self, request, handler):
                reached.set()
                await asyncio.Event().wait()

            def stale_seed(prepared):
                return [
                    SystemMessage(content=message.content.replace(frozen.CONDITIONS[0], "Only event OLD"))
                    if isinstance(message, SystemMessage) and message.content.startswith(BLOCK_PREFIX) else message
                    for message in base_seed(prepared)
                ]

            with patch.object(assistant.Loop, "awrap_model_call", stop_before_provider), patch.object(
                assistant, "_assistant_chat_seed", stale_seed if label == "checkpoint-stale" else base_seed,
            ):
                stopped = asyncio.create_task(dispatch(label, next_query, path=branch, worker_epoch=branch_epoch, cp=cp))
                try:
                    await asyncio.wait_for(reached.wait(), 20)
                finally:
                    stopped.cancel()
                    try:
                        await stopped
                    except asyncio.CancelledError:
                        pass
            assert tc.recover_running_task_runs(branch, frozen.WORKER, branch_epoch) == [next_query["run_id"]]
        control_answer = await dispatch(label, next_query, path=branch, worker_epoch=branch_epoch, cp=cp)
        assert protected == frozen.protected_counts(branch)
        if label in {"invalid-source", "scope-revoked", "aborted", "budget", "checkpoint-stale"}:
            assert turns[-1]["calls"] == 0 and control_answer is None, turns[-1]
            if label in {"budget", "checkpoint-stale", "invalid-source"}:
                assert turns[-1]["status"] == "FAILED", turns[-1]
                with connect(branch) as connection:
                    reason = connection.execute("SELECT blocked_reason FROM task_runs WHERE run_id=?", (next_query["run_id"],)).fetchone()[0]
                    expected_reason = {
                        "budget": "TASK_CONDITIONS_EXCEED_CONTEXT_BUDGET",
                        "checkpoint-stale": "ASSISTANT_CHAT_HISTORY_CHANGED",
                        "invalid-source": "TASK_CONDITION_SOURCE_INVALID",
                    }[label]
                    assert expected_reason in reason, reason
                    if label == "budget":
                        notice = connection.execute(
                            "SELECT body FROM messages WHERE command_id=?", (f"budget-notice:{next_query['run_id']}",),
                        ).fetchone()[0]
                        assert "请选择较小的调查范围" in notice, notice
            records[label] = turns[-1]
            continue
        assert control_answer, turns[-1]
        frozen.save(output / f"{label}-sdk.json", control_answer)
        observed = items(control_answer)
        historical = [
            message["content"] for message in control_answer["request"]["messages"]
            if message["content"].startswith(frozen.SUMMARY_PREFIX)
        ]
        assert historical and '"historical_constraints"' in historical[0]
        wanted = dict(active)
        if label == "replace":
            wanted["time"] = observed["time"]
            assert observed["time"]["text"] == frozen.FULL_DAY and observed["time"]["version"] == 2
        if label == "withdraw":
            wanted.pop("report")
        assert observed == wanted
        records[label] = observed
    with connect(db) as connection:
        overhead = connection.execute(
            """SELECT SUM(COALESCE(length(CAST(json_extract(payload_json,'$.condition_changes_v1') AS BLOB)),0)
                      + COALESCE(length(CAST(json_extract(payload_json,'$.condition_state_v1') AS BLOB)),0))
               FROM domain_outbox WHERE task_id=?""", (task_id,),
        ).fetchone()[0]
    results = {
        "git_sha": frozen.revision(),
        "summary_generations": len(data["summaries"]), "bound_turns": 24, "coverage": coverage,
        "confirmed": active, "controls": records, "sdk_messages_tokens": answer["sdk_message_token_estimate"],
        "condition_block_tokens": estimate_messages_tokens(condition_messages),
        "storage_payload_bytes": overhead, "long_dispatch_ms": sum(row["duration_ms"] for row in turns[:24]),
    }
    frozen.save(output / "results.json", results)
    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--baseline", action="store_true")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    frozen.configure("HYBRID")
    with TemporaryDirectory(prefix="p002-confirmed-") as temp:
        asyncio.run(run(Path(temp), args.output, args.baseline))
