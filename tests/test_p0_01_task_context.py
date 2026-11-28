"""Task history stays in scope through chat, compression, and recovery."""

import asyncio
import hashlib
import json
import os
from pathlib import Path

import httpx
import pytest
from langchain_core.messages import HumanMessage
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from opspilot import assistant
from opspilot.domain import chat
from opspilot.domain.assistant import sources_current
from opspilot.domain.database import connect
from opspilot.domain.s3 import prepare_s3_fixture
from opspilot.domain.task_control import (
    TaskControlError,
    admit_task_message,
    apply_pending_critical_inputs,
    claim_task_run,
    create_session,
    create_task_with_initial_run,
    recover_running_task_runs,
    register_worker_owner,
    trusted_identity,
)
from opspilot.web.worker import _dispatch_run
from test_ar02_journey_p0 import _enable_provider_factory

WORKER = "p001-worker"
FOREIGN = "ALPHA only: use the A receiver window."
SHARED = "PUBLIC session protocol note: HTTP 202 acknowledges receipt."
UNKNOWN = "UNKNOWN_ORIGIN: should never become shared."
ORIGINAL = "BETA original task objective."
CORRECTION = "BETA latest correction, keep the current receiver scope."


class Session:
    def __init__(self, path):
        self.path = path
        self.identity = trusted_identity(path, "support-a")
        self.session_id = create_session(path, self.identity)["session_id"]
        self.worker_epoch = register_worker_owner(path, WORKER, os.getpid())

    def task(self, text, *, professional=False):
        return create_task_with_initial_run(
            self.path, self.identity, session_id=self.session_id,
            service_id="orders-async-demo" if professional else "orders-demo",
            integration_id="async-integration-a" if professional else "integration-a",
            ticket_id="INC-A-001", initial_message=text, idempotency_key=text,
            s3_order_id="p001-order" if professional else None, assistant_core=professional,
        )

    def send(self, task_id, text, *, kind="CHAT_READONLY", professional=False):
        return admit_task_message(
            self.path, self.identity, session_id=self.session_id, task_id=task_id,
            input_kind=kind, body=text, idempotency_key=text, assistant_core=professional,
        )

    def run(self, message):
        with connect(self.path) as db:
            return dict(db.execute(
                "SELECT * FROM task_runs WHERE run_id=?", (message["run_id"],),
            ).fetchone())

    def claim(self, message):
        claim_task_run(self.path, self.identity, message["run_id"])

    def answer(self, message, content):
        self.claim(message)
        prepared = chat.prepare_chat_attempt(self.path, message["run_id"], WORKER, "fixture")
        return chat.complete_chat_attempt(
            self.path, WORKER, prepared["attempt_id"], content, provider_response_id="fixture-answer",
            input_tokens=10, output_tokens=5, total_tokens=15,
        )["message_id"]


def sdk_capture(monkeypatch):
    _enable_provider_factory(monkeypatch)
    requests = []

    async def respond(request):
        requests.append(json.loads(await request.aread()))
        return httpx.Response(200, json={
            "id": "fixture-p001", "object": "chat.completion", "created": 1,
            "model": "deepseek-flash",
            "choices": [{"index": 0, "finish_reason": "stop",
                         "message": {"role": "assistant", "content": "Offline explanation."}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        })

    def reject_sync(_request):
        raise AssertionError("Offline chat must use the injected asynchronous transport")

    def factory():
        return assistant.create_assistant_model(
            transport_async=httpx.MockTransport(respond),
            transport_sync=httpx.MockTransport(reject_sync),
        )

    return requests, factory


def text_of(messages):
    return "\n".join(message["content"] for message in messages)


def save_trace(name, payload):
    if output := os.environ.get("P0_01_OUTPUT"):
        (Path(output) / name).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def test_history_filters_unproven_and_foreign_rows_before_budgeting(demo_db, monkeypatch):
    session = Session(demo_db)
    task_a = session.task(FOREIGN)["task_id"]
    task_b = session.task(ORIGINAL)["task_id"]
    session.send(None, SHARED)
    session.send(task_b, "BETA earlier legitimate detail.")
    for index in range(5):
        session.send(task_a, f"ALPHA newer detail {index}")
    unproven = session.send(None, UNKNOWN)
    target = session.send(task_b, "Continue B after irrelevant activity")
    with connect(demo_db) as db:
        # A NULL-labelled row without an accepting Run cannot count as public.
        db.execute("DELETE FROM task_runs WHERE run_id=?", (unproven["run_id"],))
    monkeypatch.setenv("OPSPILOT_CONTEXT_STRATEGY", "RECENT_WINDOW")
    session.claim(target)
    messages = chat.prepare_chat_attempt(demo_db, target["run_id"], WORKER, "fixture")["messages"]
    assert "ALPHA" not in text_of(messages)
    assert UNKNOWN not in text_of(messages)
    assert all(text in text_of(messages) for text in (SHARED, ORIGINAL, "BETA earlier legitimate detail."))

    # An unbound Run must stay unbound, even if its source pointer was changed.
    unbound = session.send(None, "Continue general protocol discussion")
    session.claim(unbound)
    clean = chat.prepare_chat_attempt(demo_db, unbound["run_id"], WORKER, "fixture")
    assert SHARED in text_of(clean["messages"])
    assert "ALPHA" not in text_of(clean["messages"]) and "BETA" not in text_of(clean["messages"])
    with connect(demo_db) as db:
        db.execute("UPDATE task_runs SET source_message_id=? WHERE run_id=?",
                   (target["message_id"], unbound["run_id"]))
    with pytest.raises(TaskControlError, match="CHAT_SOURCE_MESSAGE_INVALID"):
        chat.prepare_chat_attempt(demo_db, unbound["run_id"], WORKER, "fixture")


def test_sdk_keeps_b_correction_and_clean_answers_excludes_legacy_pollution(demo_db, tmp_path, monkeypatch):
    prepare_s3_fixture(demo_db, "DELIVERED_PENDING", order_id="p001-order", contract_version=2)
    session = Session(demo_db)
    public = session.answer(session.send(None, SHARED, professional=True), "Legitimate public answer excerpt.")
    task_a = session.task(FOREIGN, professional=True)
    task_b = session.task(ORIGINAL, professional=True)["task_id"]
    correction = session.send(task_b, CORRECTION, kind="CORRECT_TASK_INPUT")
    session.claim(correction)
    apply_pending_critical_inputs(demo_db, session.identity, correction["run_id"])
    session.answer(session.send(task_b, "BETA valid prior request", professional=True),
                   "Legitimate BETA historical answer.")
    dirty_b = session.answer(session.send(task_b, "BETA legacy contaminated turn", professional=True),
                             "OLD_B_CONTAMINATION " + FOREIGN)
    dirty_public = session.answer(session.send(None, "Legacy general turn", professional=True),
                                  "OLD_PUBLIC_CONTAMINATION " + FOREIGN)
    with connect(demo_db) as db:
        for message_id in (dirty_b, dirty_public):
            db.execute(
                """INSERT INTO chat_message_sources (message_id, source_kind, source_ref, source_digest)
                   SELECT ?, 'MESSAGE', message_id, body_digest FROM messages WHERE message_id=?""",
                (message_id, task_a["message_id"]),
            )

    target = session.send(task_b, "Continue the corrected BETA investigation", professional=True)
    requests, factory = sdk_capture(monkeypatch)
    asyncio.run(_dispatch_run(demo_db, tmp_path / "graph.sqlite", WORKER, "executor-a",
                              session.run(target), session.worker_epoch, assistant_model_factory=factory))
    assert session.run(target)["status"] == "SUCCEEDED"
    assert len(requests) == 1
    prompt = text_of(requests[0]["messages"])
    assert all(marker not in prompt for marker in ("ALPHA", "OLD_B_CONTAMINATION", "OLD_PUBLIC_CONTAMINATION"))
    assert all(marker in prompt for marker in (
        ORIGINAL, CORRECTION, SHARED, "BETA valid prior request",
        "Legitimate BETA historical answer.", "Legitimate public answer excerpt.",
    ))
    # The original user note is still shared, but an invalidated derived
    # excerpt must also invalidate any older B answer that depended on it.
    with connect(demo_db) as db:
        db.execute(
            """INSERT INTO chat_message_sources (message_id, source_kind, source_ref, source_digest)
               SELECT ?, 'MESSAGE', message_id, body_digest FROM messages WHERE message_id=?""",
            (public, task_a["message_id"]),
        )
        assert sources_current(db, target["run_id"]) == (False, "ASSISTANT_SESSION_ANSWER_SOURCE_INVALID")
    later = session.send(task_b, "Continue BETA after the older answer becomes invalid", professional=True)
    asyncio.run(_dispatch_run(demo_db, tmp_path / "graph.sqlite", WORKER, "executor-a",
                              session.run(later), session.worker_epoch, assistant_model_factory=factory))
    assert session.run(later)["status"] == "SUCCEEDED"
    assert len(requests) == 2
    later_prompt = text_of(requests[1]["messages"])
    assert "Legitimate public answer excerpt." not in later_prompt
    assert "Offline explanation." not in later_prompt
    assert SHARED in later_prompt and CORRECTION in later_prompt
    save_trace("sdk-correction-and-lineage.json", requests)


def test_compression_reuses_scoped_summary_and_excludes_foreign_dependencies(demo_db, monkeypatch):
    session = Session(demo_db)
    task_a = session.task(FOREIGN)
    task_b = session.task(ORIGINAL)["task_id"]
    shared = session.send(None, SHARED)
    for index in range(15):
        session.send(task_a["task_id"], f"ALPHA filler {index}")
        session.send(task_b, f"BETA filler {index}")
    monkeypatch.setenv("OPSPILOT_CONTEXT_STRATEGY", "ROLLING_SUMMARY")
    target = session.send(task_b, "Build a BETA summary")
    session.claim(target)
    prepared = chat.prepare_chat_compression_attempt(demo_db, target["run_id"], WORKER, "fixture")
    assert SHARED in text_of(prepared["messages"])
    assert "ALPHA" not in text_of(prepared["messages"])
    with connect(demo_db) as db:
        row = db.execute("SELECT sequence FROM messages WHERE message_id=?", (shared["message_id"],)).fetchone()
    result = chat.complete_chat_compression_attempt(
        demo_db, WORKER, prepared["attempt_id"], json.dumps({
            "initial_goal": {"text": SHARED, "source_sequences": [row["sequence"]]},
            "constraints": [], "user_assertions": [], "corrections": [],
            "rejected_hypotheses": [], "unresolved_items": [], "timeline": [],
        }),
        provider_response_id="fixture-summary", input_tokens=30, output_tokens=10, total_tokens=40,
    )
    summary_id = result["summary_id"]
    monkeypatch.setenv("OPSPILOT_CONTEXT_STRATEGY", "HYBRID")
    built = chat.prepare_chat_attempt(demo_db, target["run_id"], WORKER, "fixture")
    assert built["summary_refs"][0]["summary_id"] == summary_id
    assert SHARED in text_of(built["messages"])
    with connect(demo_db) as db:
        # An older B summary can have the wrong dependency even with its own
        # correct task_id and a valid summary digest.
        document = json.loads(db.execute(
            "SELECT summary_json FROM context_summaries WHERE summary_id=?", (summary_id,),
        ).fetchone()["summary_json"])
        document["initial_goal"]["text"] = FOREIGN
        legacy = json.dumps(document)
        db.execute("UPDATE context_summaries SET summary_json=?, summary_digest=? WHERE summary_id=?",
                   (legacy, hashlib.sha256(legacy.encode()).hexdigest(), summary_id))
        db.execute(
            """INSERT INTO context_summary_dependencies
               (summary_id, dependency_kind, dependency_ref, dependency_digest)
               SELECT ?, 'MESSAGE', message_id, body_digest FROM messages WHERE message_id=?""",
            (summary_id, task_a["message_id"]),
        )
    followup = session.send(task_b, "Recover without the old summary")
    session.claim(followup)
    clean = chat.prepare_chat_attempt(demo_db, followup["run_id"], WORKER, "fixture")
    assert not clean["summary_refs"]
    assert {"source_id": summary_id, "reason": "SUMMARY_MESSAGE_SOURCE_INVALID"} in clean["excluded_sources"]
    assert SHARED in text_of(clean["messages"])
    assert "ALPHA" not in text_of(clean["messages"])


@pytest.mark.parametrize("polluted", [False, True])
def test_recovery_checks_saved_chat_messages_before_sdk_dispatch(demo_db, tmp_path, monkeypatch, polluted):
    prepare_s3_fixture(demo_db, "DELIVERED_PENDING", order_id="p001-order", contract_version=2)
    session = Session(demo_db)
    session.task(FOREIGN, professional=True)
    task_b = session.task(ORIGINAL, professional=True)["task_id"]
    session.send(None, SHARED)
    target = session.send(task_b, "Resume BETA", professional=True)
    checkpoint = tmp_path / "saved.sqlite"
    config = {"configurable": {"thread_id": "assistant-v1:" + target["run_id"]}}
    requests, factory = sdk_capture(monkeypatch)

    async def dispatch():
        await _dispatch_run(demo_db, checkpoint, WORKER, "executor-a",
                            session.run(target), session.worker_epoch, assistant_model_factory=factory)

    base_seed = assistant.Loop._fresh_context_prefix

    def polluted_seed(loop, prepared):
        prefix, marker, body = base_seed(loop, prepared)
        return [HumanMessage(content=FOREIGN), *prefix], marker, body

    async def interrupt_worker():
        reached_model = asyncio.Event()

        async def stop_before_provider(self, request, handler):
            reached_model.set()
            await asyncio.Event().wait()

        with monkeypatch.context() as interrupted:
            interrupted.setattr(assistant.Loop, "awrap_model_call", stop_before_provider)
            if polluted:
                interrupted.setattr(assistant.Loop, "_fresh_context_prefix", polluted_seed)
            worker = asyncio.create_task(dispatch())
            try:
                await asyncio.wait_for(reached_model.wait(), 20)
            finally:
                worker.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await worker

    asyncio.run(interrupt_worker())
    assert not requests

    async def read_saved():
        async with AsyncSqliteSaver.from_conn_string(str(checkpoint)) as saver:
            return (await saver.aget_tuple(config)).checkpoint["channel_values"]["messages"]

    saved = asyncio.run(read_saved())
    assert any(message.content == FOREIGN for message in saved) is polluted
    assert recover_running_task_runs(demo_db, WORKER, session.worker_epoch) == [target["run_id"]]
    asyncio.run(dispatch())
    if polluted:
        assert not requests
        run = session.run(target)
        assert run["status"] == "FAILED"
        assert "ASSISTANT_CHAT_HISTORY_CHANGED" in run["blocked_reason"]
    else:
        assert session.run(target)["status"] == "SUCCEEDED"
        assert len(requests) == 1
        assert SHARED in text_of(requests[0]["messages"])
        assert "ALPHA" not in text_of(requests[0]["messages"])
    save_trace(f"checkpoint-{'polluted' if polluted else 'clean'}.json", {
        "run_id": target["run_id"], "task_id": task_b,
        "stored_history": [message.content for message in saved],
        "terminal_status": session.run(target)["status"],
        "terminal_reason": session.run(target)["blocked_reason"],
        "transport_dispatches": len(requests),
    })
