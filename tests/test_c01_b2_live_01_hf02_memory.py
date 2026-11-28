"""Offline checks for the Personal Memory acceptance and source boundaries."""
from __future__ import annotations

import asyncio
import json
from contextlib import contextmanager, suppress
from types import SimpleNamespace

import httpx
import pytest
from langchain_core.messages import AIMessage

from opspilot.domain import assistant_runtime_grant as runtime
from opspilot.domain import personal_memory_consolidation as consolidation
from opspilot.domain.database import connect
from opspilot.domain.semantic_memory import (
    personal_memory_context,
    remember_personal_memory,
    revoke_personal_memory,
    set_personal_memory_recall,
)
from opspilot.domain.task_control import (
    admit_task_message, claim_task_run, create_session, finish_task_run, trusted_identity,
)
from test_c01_b2_live_01_hf01 import _configure_runtime, _provision_runtime
from test_product_01_runtime_grant_01 import _worker


PREFERENCE = "I prefer explanations with Java examples."


@contextmanager
def registered_worker(path):
    worker = _worker(path)
    try:
        yield worker
    finally:
        worker.release()


def admit(path, session_id, key, body="Explain this interface.", *, actor_id="support-a"):
    actor = trusted_identity(path, actor_id)
    return admit_task_message(
        path, actor, session_id=session_id, task_id=None, input_kind="CHAT_READONLY",
        body=body, idempotency_key=key, assistant_core=True,
    )


def complete(path, item, *, claim=True):
    actor = trusted_identity(path, "support-a")
    if claim:
        claim_task_run(path, actor, item["run_id"])
    assert finish_task_run(path, actor, item["run_id"], "SUCCEEDED")["status"] == "SUCCEEDED"
    return item["message_id"]


def completed_messages(path, session, prefix, count, body="Explain this interface."):
    return [complete(path, admit(path, session, f"{prefix}-{index}", body)) for index in range(count)]


def set_learning(path, enabled, *, recall=True):
    return set_personal_memory_recall(
        path, "tenant-a", "support-a", recall_enabled=recall, auto_learn_enabled=enabled,
    )


def save_preference(path, session, key, preference, *, mode="PINNED", actor_id="support-a"):
    item = admit(path, session, key, f"Please remember: {preference}", actor_id=actor_id)
    actor = trusted_identity(path, actor_id)
    return remember_personal_memory(
        path, actor.tenant_id, actor_id, memory_kind="PREFERENCE", memory_mode=mode,
        memory_key=key, content=preference, source_message_id=item["message_id"],
        idempotency_key=f"save-{key}",
    )


class CaptureConsolidator:
    def __init__(self, *, propose=False, after_input=None):
        self.inputs = []
        self.propose = propose
        self.after_input = after_input

    async def ainvoke(self, messages):
        payload = json.loads(messages[-1].content.split("\n", 1)[1])
        self.inputs.append(payload)
        if self.after_input is not None:
            self.after_input()
        proposals = []
        if self.propose:
            source = payload["sources"][0]
            proposals.append({
                "action": "ADD", "memory_kind": "PREFERENCE", "memory_mode": "PINNED",
                "memory_key": "example.language", "content": PREFERENCE,
                "source_quotes": [{"message_id": source["message_id"], "quote": PREFERENCE}],
            })
        return AIMessage(content=json.dumps({"proposals": proposals}))


def job_message_ids(job):
    return [ref["id"] for ref in json.loads(job["source_refs_json"])]


def test_learning_boundary_uses_accepted_sequence_before_run_success(demo_db):
    actor = trusted_identity(demo_db, "support-a")
    session_a = create_session(demo_db, actor)["session_id"]
    session_b = create_session(demo_db, actor)["session_id"]
    with registered_worker(demo_db) as worker:
        old_a = admit(demo_db, session_a, "pre-enable-running", PREFERENCE)
        assert claim_task_run(demo_db, actor, old_a["run_id"])["status"] == "RUNNING"
        set_learning(demo_db, True)
        complete(demo_db, old_a, claim=False)
        new_a = completed_messages(demo_db, session_a, "enabled-a", 5)
        assert consolidation.claim_next_personal_memory_job(demo_db, worker.owner_id) is None
        new_a += completed_messages(demo_db, session_a, "enabled-a-sixth", 1)
        job_a = consolidation.claim_next_personal_memory_job(demo_db, worker.owner_id)
        assert job_message_ids(job_a) == new_a
        assert consolidation.claim_next_personal_memory_job(demo_db, worker.owner_id)["job_id"] == job_a["job_id"]
        capture = CaptureConsolidator()
        result = asyncio.run(consolidation.process_personal_memory_job(demo_db, worker.owner_id, job_a["job_id"], capture))
        assert result["status"] == "SUCCEEDED"
        assert [row["message_id"] for row in capture.inputs[0]["sources"]] == new_a

        set_learning(demo_db, False)
        old_b = admit(demo_db, session_b, "disabled-b-running", PREFERENCE)
        assert claim_task_run(demo_db, actor, old_b["run_id"])["status"] == "RUNNING"
        set_learning(demo_db, True)
        complete(demo_db, old_b, claim=False)
        new_b = completed_messages(demo_db, session_b, "enabled-b", 5)
        assert consolidation.claim_next_personal_memory_job(demo_db, worker.owner_id) is None
        new_b += completed_messages(demo_db, session_b, "enabled-b-sixth", 1)
        first_worker_id = worker.owner_id

    with registered_worker(demo_db) as replacement:
        assert replacement.owner_id != first_worker_id
        assert asyncio.run(replacement.recover_after_exclusive_start()) == []
        job_b = consolidation.claim_next_personal_memory_job(demo_db, replacement.owner_id)
        assert job_b["session_id"] == session_b
        assert job_message_ids(job_b) == new_b
        capture = CaptureConsolidator()
        result = asyncio.run(consolidation.process_personal_memory_job(demo_db, replacement.owner_id, job_b["job_id"], capture))
        assert result["status"] == "SUCCEEDED"
        assert [row["message_id"] for row in capture.inputs[0]["sources"]] == new_b
        assert consolidation.claim_next_personal_memory_job(demo_db, replacement.owner_id) is None
        with connect(demo_db) as connection:
            boundaries = dict(connection.execute(
                """SELECT j.session_id, j.source_end_sequence FROM personal_memory_consolidation_jobs j
                   WHERE j.status='SKIPPED_DISABLED' AND j.session_id IN (?,?)
                   AND j.source_end_sequence IN (SELECT sequence FROM messages WHERE message_id IN (?,?))""",
                (session_a, session_b, old_a["message_id"], old_b["message_id"]),
            ).fetchall())
        assert boundaries == {session_a: 1, session_b: 1}


@pytest.mark.parametrize("state", ["active", "expired", "source-changed", "revoked"])
def test_existing_memory_currentness_matches_recall_and_actual_consolidator_input(demo_db, state):
    actor = trusted_identity(demo_db, "support-a")
    source_session = create_session(demo_db, actor)["session_id"]
    memory = save_preference(demo_db, source_session, "example.language", PREFERENCE)
    other_actor = trusted_identity(demo_db, "support-b")
    other_session = create_session(demo_db, other_actor)["session_id"]
    other = save_preference(demo_db, other_session, "example.language", "I prefer Go examples.", actor_id="support-b")
    if state == "expired":
        with connect(demo_db) as connection:
            connection.execute("UPDATE personal_memories SET expires_at='2000-01-01T00:00:00Z' WHERE memory_id=?", (memory["memory_id"],))
    elif state == "source-changed":
        with connect(demo_db) as connection:
            connection.execute("UPDATE messages SET body='Changed source' WHERE message_id=?", (memory["source_message_id"],))
    elif state == "revoked":
        revoke_personal_memory(demo_db, "tenant-a", memory["memory_id"], "support-a",
                               idempotency_key="hf02-revoke")

    set_learning(demo_db, True)
    session = create_session(demo_db, actor)["session_id"]
    with registered_worker(demo_db) as worker:
        completed_messages(demo_db, session, "fresh-batch", 6, PREFERENCE)
        job = consolidation.claim_next_personal_memory_job(demo_db, worker.owner_id)
        capture = CaptureConsolidator(propose=True)
        result = asyncio.run(consolidation.process_personal_memory_job(demo_db, worker.owner_id, job["job_id"], capture))
        assert len(capture.inputs) == 1
        sent = capture.inputs[0]["existing_personal_memory"]
        with connect(demo_db) as connection:
            recalled, _, _ = personal_memory_context(connection, "tenant-a", "support-a", "Explain with Java examples.")
        expected = [memory["memory_id"]] if state == "active" else []
        assert [row["memory_id"] for row in recalled] == expected
        assert [row["memory_id"] for row in sent] == expected
        assert other["memory_id"] not in json.dumps(capture.inputs)
        assert result["duplicate_count"] == int(state == "active")
        assert result["written_count"] == 0


def test_disabling_learning_prevents_claimed_batch_from_reaching_model(demo_db):
    session = create_session(demo_db, trusted_identity(demo_db, "support-a"))["session_id"]
    set_learning(demo_db, True)
    completed_messages(demo_db, session, "claimed-batch", 6)
    with registered_worker(demo_db) as worker:
        job = consolidation.claim_next_personal_memory_job(demo_db, worker.owner_id)
        set_learning(demo_db, True, recall=False)
        capture = CaptureConsolidator()
        with pytest.raises(consolidation.ConsolidationError, match="JOB_NOT_RUNNING"):
            asyncio.run(consolidation.process_personal_memory_job(demo_db, worker.owner_id, job["job_id"], capture))
        assert capture.inputs == []
        assert consolidation.claim_next_personal_memory_job(demo_db, worker.owner_id) is None


def test_consolidation_discards_proposals_if_prompt_memory_is_revoked_during_response(demo_db):
    actor = trusted_identity(demo_db, "support-a")
    source = create_session(demo_db, actor)["session_id"]
    memory = save_preference(demo_db, source, "answer.order", "I prefer short paragraphs.")
    set_learning(demo_db, True)
    session = create_session(demo_db, actor)["session_id"]
    completed_messages(demo_db, session, "concurrent-revocation", 6, PREFERENCE)

    def revoke():
        revoke_personal_memory(demo_db, "tenant-a", memory["memory_id"], "support-a",
                               idempotency_key="hf02-revoke-during-response")

    with registered_worker(demo_db) as worker:
        job = consolidation.claim_next_personal_memory_job(demo_db, worker.owner_id)
        capture = CaptureConsolidator(propose=True, after_input=revoke)
        with pytest.raises(consolidation.ConsolidationError, match="EXISTING_PERSONAL_MEMORY_CHANGED"):
            asyncio.run(consolidation.process_personal_memory_job(demo_db, worker.owner_id, job["job_id"], capture))
        assert [row["memory_id"] for row in capture.inputs[0]["existing_personal_memory"]] == [memory["memory_id"]]
        with connect(demo_db) as connection:
            assert connection.execute("SELECT COUNT(*) FROM personal_memories").fetchone()[0] == 1
            assert connection.execute("SELECT status FROM personal_memory_consolidation_jobs WHERE job_id=?", (job["job_id"],)).fetchone()[0] == "FAILED"


def test_runtime_revalidates_consolidation_memory_at_send_permit(demo_db, monkeypatch):
    from opspilot.assistant import create_assistant_model

    _configure_runtime(monkeypatch)
    _provision_runtime(demo_db)
    actor = trusted_identity(demo_db, "support-a")
    source = create_session(demo_db, actor)["session_id"]
    memory = save_preference(demo_db, source, "answer.order", "I prefer short paragraphs.")
    set_learning(demo_db, True)
    session = create_session(demo_db, actor)["session_id"]
    completed_messages(demo_db, session, "before-permit", 6, PREFERENCE)
    claim_send = runtime.claim_send
    sends = []

    def revoke_before_send(*args, **kwargs):
        revoke_personal_memory(demo_db, "tenant-a", memory["memory_id"], "support-a",
                               idempotency_key="hf02-revoke-before-send")
        return claim_send(*args, **kwargs)

    def unexpected_send(request):
        sends.append(request)
        raise AssertionError("Invalid memory must not reach the mock transport")

    monkeypatch.setattr(runtime, "claim_send", revoke_before_send)
    with registered_worker(demo_db) as worker:
        job = consolidation.claim_next_personal_memory_job(demo_db, worker.owner_id)
        binding = runtime.bind_run(demo_db, job["source_run_id"], runtime.runtime_config_from_env())

        async def execute():
            model = create_assistant_model(
                runtime_grant_binding=binding, transport_async=httpx.MockTransport(unexpected_send),
                transport_sync=httpx.MockTransport(unexpected_send),
            )
            try:
                await consolidation.process_personal_memory_job(
                    demo_db, worker.owner_id, job["job_id"], model,
                    runtime_binding=binding, worker_epoch=worker.epoch,
                )
            finally:
                await model.http_async_client.aclose()
                model.http_client.close()

        with pytest.raises(Exception, match="Connection error|RUNTIME_PERSONAL_MEMORY_CONTEXT_CHANGED"):
            asyncio.run(execute())
        assert sends == []
        with connect(demo_db) as connection:
            spend = connection.execute("SELECT status,reserved_usd_micro,send_granted_at FROM assistant_runtime_spends").fetchone()
            assert tuple(spend) == ("NOT_DISPATCHED", 0, None)


def test_worker_restart_releases_unsent_reserve_when_memory_context_changes(demo_db, monkeypatch):
    from test_c01_b2_b_personal_memory_auto_consolidation import _prepare_runtime_consolidation_call

    _configure_runtime(monkeypatch)
    _provision_runtime(demo_db)
    actor = trusted_identity(demo_db, "support-a")
    source = create_session(demo_db, actor)["session_id"]
    memory = save_preference(demo_db, source, "answer.order", "I prefer short paragraphs.")
    set_learning(demo_db, True)
    session = create_session(demo_db, actor)["session_id"]
    completed_messages(demo_db, session, "restart-before-send", 6, PREFERENCE)
    with registered_worker(demo_db) as worker:
        job = consolidation.claim_next_personal_memory_job(demo_db, worker.owner_id)
        binding = runtime.bind_run(demo_db, job["source_run_id"], runtime.runtime_config_from_env())
        app = SimpleNamespace(state=SimpleNamespace(worker_id=worker.owner_id))
        call, logical_key, _, attach_call = _prepare_runtime_consolidation_call(demo_db, app, job, binding)
        attach_call(demo_db, job["job_id"], call["call_id"])
        dispatch = runtime.reserve_dispatch(
            demo_db, binding, call_id=call["call_id"], logical_key=logical_key,
            request_digest=call["request_digest"], worker_id=worker.owner_id,
        )
        assert dispatch["status"] == "RESERVED"

    revoke_personal_memory(demo_db, "tenant-a", memory["memory_id"], "support-a",
                           idempotency_key="revoke-before-worker-restart")
    with registered_worker(demo_db) as replacement:
        assert consolidation.claim_next_personal_memory_job(demo_db, replacement.owner_id)["job_id"] == job["job_id"]
        capture = CaptureConsolidator()
        with pytest.raises(consolidation.ConsolidationError, match="CONSOLIDATION_REPLAY_CONTEXT_CHANGED"):
            asyncio.run(consolidation.process_personal_memory_job(
                demo_db, replacement.owner_id, job["job_id"], capture,
                runtime_binding=binding, worker_epoch=replacement.epoch,
            ))
        assert capture.inputs == []
        assert consolidation.claim_next_personal_memory_job(demo_db, replacement.owner_id) is None
    with connect(demo_db) as connection:
        spend = connection.execute("SELECT status,reserved_usd_micro,send_granted_at FROM assistant_runtime_spends").fetchone()
        assert tuple(spend) == ("NOT_DISPATCHED", 0, None)
        assert connection.execute("SELECT status FROM assistant_calls WHERE call_id=?", (call["call_id"],)).fetchone()[0] == "FAILED"


def test_stalled_consolidation_times_out_and_worker_serves_next_chat(demo_db, tmp_path, monkeypatch):
    from opspilot.assistant import create_assistant_model
    from opspilot.web.worker import run_worker

    _configure_runtime(monkeypatch)
    _provision_runtime(demo_db)
    monkeypatch.setattr(consolidation, "CONSOLIDATION_PROVIDER_TIMEOUT_SECONDS", 0.25, raising=False)
    actor = trusted_identity(demo_db, "support-a")
    session = create_session(demo_db, actor)["session_id"]
    set_learning(demo_db, True)
    completed_messages(demo_db, session, "stalled-batch", 6, PREFERENCE)

    async def scenario(worker):
        pending = asyncio.Event()
        cancelled = asyncio.Event()
        closed = asyncio.Event()
        sent = []

        class StalledResponse(httpx.AsyncByteStream):
            async def __aiter__(self):
                yield b" "
                pending.set()
                try:
                    await asyncio.Event().wait()
                finally:
                    cancelled.set()

            async def aclose(self):
                closed.set()

        async def respond(request):
            body = json.loads(request.content)
            if "existing_personal_memory" in body["messages"][-1]["content"]:
                sent.append("consolidation")
                return httpx.Response(200, headers={"content-type": "application/json"}, stream=StalledResponse())
            sent.append("chat")
            return httpx.Response(200, json={
                "id": "fixture-after-timeout", "object": "chat.completion", "created": 1,
                "model": "deepseek-flash", "choices": [{"index": 0, "finish_reason": "stop",
                    "message": {"role": "assistant", "content": "The Worker can continue."}}],
                "usage": {"prompt_tokens": 40, "completion_tokens": 9, "total_tokens": 49},
            })

        transport = httpx.MockTransport(respond)
        task = asyncio.create_task(run_worker(
            demo_db, tmp_path / "worker-timeout-checkpoints.sqlite3",
            worker_id=worker.owner_id, worker_epoch=worker.epoch, executor_id="executor-a",
            poll_interval=0.025, assistant_runtime_enabled=True,
            assistant_model_factory=lambda *, runtime_grant_binding: create_assistant_model(
                runtime_grant_binding=runtime_grant_binding, transport_async=transport, transport_sync=transport,
            ),
        ))
        try:
            await asyncio.wait_for(pending.wait(), 5)
            before = consolidation.personal_memory_consolidation_status(demo_db, "tenant-a", "support-a")
            assert before["latest_job"]["status"] == "RUNNING"
            accepted = admit(demo_db, session, "chat-queued-during-consolidation")
            async with asyncio.timeout(8):
                while True:
                    with connect(demo_db) as connection:
                        run = connection.execute("SELECT status FROM task_runs WHERE run_id=?", (accepted["run_id"],)).fetchone()
                    if run["status"] == "SUCCEEDED":
                        break
                    await asyncio.sleep(0.025)
            assert cancelled.is_set() and closed.is_set()
            after = consolidation.personal_memory_consolidation_status(demo_db, "tenant-a", "support-a")
            assert after["latest_job"]["status"] == "UNKNOWN"
            assert after["latest_job"]["failure_code"] == "PROVIDER_TIMEOUT_RESULT_UNKNOWN"
            with connect(demo_db) as connection:
                spends = connection.execute("""SELECT status,error_code,settled_usd_micro,reserved_usd_micro
                    FROM assistant_runtime_spends ORDER BY created_at,rowid""").fetchall()
            assert [row["status"] for row in spends] == ["UNKNOWN", "DELIVERED"]
            # The transport sees cancellation first. The enclosing deadline
            # records the more specific timeout on the Job and Assistant Call.
            assert spends[0]["error_code"] == "CancelledError"
            assert spends[0]["settled_usd_micro"] is None and spends[0]["reserved_usd_micro"] > 0
            assert sent == ["consolidation", "chat"]
        finally:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task

    with registered_worker(demo_db) as worker:
        asyncio.run(scenario(worker))
