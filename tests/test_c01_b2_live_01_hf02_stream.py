"""Offline stream completion, cancellation and single Session export regressions."""
from __future__ import annotations

import asyncio
import json
import runpy
from contextlib import asynccontextmanager, suppress
from pathlib import Path

import httpx
import pytest

from opspilot.assistant import Loop, create_assistant_model, run_assistant
from opspilot.domain import assistant as assistant_domain
from opspilot.domain import assistant_runtime_grant as runtime
from opspilot.domain.chat import get_chat_chunks
from opspilot.domain.database import connect
from opspilot.domain.task_control import claim_task_run, create_session, next_worker_run, trusted_identity
from test_c01_b2_live_01_hf01 import _SSEProviderStream, _chunk, _configure_runtime, _provision_runtime
from test_c01_b2_live_01_hf02_memory import admit, completed_messages, registered_worker, save_preference, set_learning


USAGE = {"prompt_tokens": 40, "completion_tokens": 9, "total_tokens": 49}
NORMALIZED_USAGE = {"input_tokens": 40, "output_tokens": 9, "total_tokens": 49}
DRAFT = "A visible answer from the mock provider."


def stream_response(*, finish_reason="stop", delta=None, include_done=True):
    delta = delta or {"role": "assistant", "content": DRAFT}
    parts = [
        _chunk(delta=delta), _chunk(delta={}, finish_reason=finish_reason),
        _chunk(delta={}, choices=False, usage=USAGE),
    ]
    if include_done:
        parts.append(b"data: [DONE]\n\n")
    return _SSEProviderStream(parts)


@asynccontextmanager
async def model_for(demo_db, run_id, respond):
    binding = runtime.bind_run(demo_db, run_id, runtime.runtime_config_from_env())
    transport = httpx.MockTransport(respond)
    model = create_assistant_model(
        runtime_grant_binding=binding, transport_async=transport, transport_sync=transport,
    )
    try:
        yield model, binding
    finally:
        await model.http_async_client.aclose()
        model.http_client.close()


async def run_stream(path, checkpoint, worker, run_id, respond):
    actor = trusted_identity(path, "support-a")
    claim_task_run(path, actor, run_id)
    async with model_for(path, run_id, respond) as (model, binding):
        return await run_assistant(
            path, checkpoint, worker.owner_id, run_id, model=model,
            runtime_grant_binding=binding, worker_epoch=worker.epoch, streaming_enabled=True,
        )


def stored_outcome(path, run_id):
    with connect(path) as connection:
        run = connection.execute("SELECT * FROM task_runs WHERE run_id=?", (run_id,)).fetchone()
        spend = connection.execute("SELECT * FROM assistant_runtime_spends WHERE run_id=?", (run_id,)).fetchone()
        call = connection.execute("SELECT * FROM assistant_calls WHERE run_id=? AND kind='MODEL' ORDER BY created_at,rowid", (run_id,)).fetchone()
        answers = connection.execute("SELECT COUNT(*) FROM chat_run_answers WHERE run_id=?", (run_id,)).fetchone()[0]
    return run, spend, call, answers


@pytest.mark.parametrize(("reason", "code"), [
    ("stop", None),
    ("length", "ASSISTANT_PROVIDER_STREAM_OUTPUT_TRUNCATED"),
    ("content_filter", "ASSISTANT_PROVIDER_STREAM_CONTENT_FILTERED"),
    ("insufficient_system_resource", "ASSISTANT_PROVIDER_STREAM_INSUFFICIENT_RESOURCES"),
    ("aborted", "ASSISTANT_PROVIDER_STREAM_ABORTED"),
    ("unexpected", "ASSISTANT_PROVIDER_STREAM_FINISH_REASON_UNSUPPORTED"),
    ("tool_calls", "ASSISTANT_PROVIDER_STREAM_TOOL_CALL_INVALID"),
])
def test_complete_stream_finish_reason_controls_answer_not_settlement(demo_db, tmp_path, monkeypatch, reason, code):
    _configure_runtime(monkeypatch)
    _provision_runtime(demo_db)
    actor = trusted_identity(demo_db, "support-a")
    session = create_session(demo_db, actor)["session_id"]
    run_id = admit(demo_db, session, f"finish-{reason}")["run_id"]
    sent = []

    async def respond(request):
        sent.append(json.loads(request.content))
        return httpx.Response(200, headers={"content-type": "text/event-stream"}, stream=stream_response(finish_reason=reason))

    with registered_worker(demo_db) as worker:
        asyncio.run(run_stream(demo_db, tmp_path / "checkpoints.sqlite3", worker, run_id, respond))
    run, spend, call, answers = stored_outcome(demo_db, run_id)
    assert len(sent) == 1 and sent[0]["stream"] is True
    assert spend["settled_usd_micro"] == 49
    assert json.loads(spend["usage_json"]) == NORMALIZED_USAGE
    assert runtime.spend_summary(demo_db)["committed_or_reserved_usd_micro"] == 49
    assert "".join(chunk["body"] for chunk in get_chat_chunks(demo_db, actor, run_id)) == DRAFT
    if code is None:
        assert (run["status"], call["status"], spend["status"], answers) == ("SUCCEEDED", "OK", "DELIVERED", 1)
    else:
        assert (run["status"], call["status"], spend["status"], answers) == ("FAILED", "FAILED", "RESPONSE_STORED", 0)
        assert code in run["blocked_reason"]
        assert json.loads(call["result_json"])["error"] == code
        assert json.loads(call["usage_json"]) == [NORMALIZED_USAGE]


def test_tool_finish_rejects_json_that_langchain_could_repair(demo_db, tmp_path, monkeypatch):
    _configure_runtime(monkeypatch)
    _provision_runtime(demo_db)
    actor = trusted_identity(demo_db, "support-a")
    session = create_session(demo_db, actor)["session_id"]
    run_id = admit(demo_db, session, "truncated-tool-args")["run_id"]
    sends = []
    delta = {"role": "assistant", "tool_calls": [{
        "index": 0, "id": "fixture-tool", "type": "function",
        "function": {"name": "list_scoped_protocol_documents", "arguments": '{"topic":"callbacks"'},
    }]}

    async def respond(request):
        sends.append(json.loads(request.content))
        if len(sends) == 1:
            stream = stream_response(finish_reason="tool_calls", delta=delta)
        else:
            stream = stream_response()
        return httpx.Response(200, headers={"content-type": "text/event-stream"}, stream=stream)

    with registered_worker(demo_db) as worker:
        asyncio.run(run_stream(demo_db, tmp_path / "checkpoints.sqlite3", worker, run_id, respond))
    run, spend, call, answers = stored_outcome(demo_db, run_id)
    assert len(sends) == 1
    with connect(demo_db) as connection:
        assert connection.execute("SELECT COUNT(*) FROM assistant_calls WHERE kind='MCP'").fetchone()[0] == 0
    assert (run["status"], call["status"], spend["status"], answers) == ("FAILED", "FAILED", "RESPONSE_STORED", 0)
    assert "ASSISTANT_PROVIDER_STREAM_TOOL_CALL_INVALID" in run["blocked_reason"]


def test_usage_without_done_keeps_spend_unknown(demo_db, tmp_path, monkeypatch):
    _configure_runtime(monkeypatch)
    _provision_runtime(demo_db)
    actor = trusted_identity(demo_db, "support-a")
    session = create_session(demo_db, actor)["session_id"]
    run_id = admit(demo_db, session, "missing-done")["run_id"]
    sends = []

    async def respond(request):
        sends.append(request.url)
        return httpx.Response(200, headers={"content-type": "text/event-stream"}, stream=stream_response(include_done=False))

    with registered_worker(demo_db) as worker:
        asyncio.run(run_stream(demo_db, tmp_path / "checkpoints.sqlite3", worker, run_id, respond))
    run, spend, call, answers = stored_outcome(demo_db, run_id)
    assert (run["status"], call["status"], spend["status"], answers, len(sends)) == ("FAILED", "UNKNOWN", "UNKNOWN", 0, 1)
    assert spend["settled_usd_micro"] is None and spend["reserved_usd_micro"] > 0


def test_durable_truncated_response_replay_fails_without_resending(demo_db, tmp_path, monkeypatch):
    _configure_runtime(monkeypatch)
    _provision_runtime(demo_db)
    actor = trusted_identity(demo_db, "support-a")
    session = create_session(demo_db, actor)["session_id"]
    run_id = admit(demo_db, session, "replay-truncation")["run_id"]
    sends = []
    checkpoint = tmp_path / "checkpoints.sqlite3"

    class SimulatedCrash(BaseException):
        pass

    async def respond(request):
        sends.append(request.url)
        return httpx.Response(200, headers={"content-type": "text/event-stream"}, stream=stream_response(finish_reason="length"))

    def interrupt_failure_receipt(self, *args):
        raise SimulatedCrash("after response storage, before Assistant failure receipt")

    with registered_worker(demo_db) as first, monkeypatch.context() as patch:
        patch.setattr(Loop, "_record_runtime_model_failure", interrupt_failure_receipt)
        with pytest.RaisesGroup(SimulatedCrash, flatten_subgroups=True, allow_unwrapped=True):
            asyncio.run(run_stream(demo_db, checkpoint, first, run_id, respond))
    _, spend, call, answers = stored_outcome(demo_db, run_id)
    assert (spend["status"], call["status"], answers) == ("RESPONSE_STORED", "RESERVED", 0)
    assistant_domain.finish(demo_db, call["call_id"], "UNKNOWN")

    with registered_worker(demo_db) as second:
        assert asyncio.run(second.recover_after_exclusive_start()) == [run_id]
        asyncio.run(run_stream(demo_db, checkpoint, second, run_id, respond))
    run, spend, call, answers = stored_outcome(demo_db, run_id)
    assert (run["status"], call["status"], spend["status"], answers, len(sends)) == ("FAILED", "FAILED", "RESPONSE_STORED", 0, 1)
    assert spend["settled_usd_micro"] == 49
    assert "ASSISTANT_PROVIDER_STREAM_OUTPUT_TRUNCATED" in run["blocked_reason"]
    assert "".join(chunk["body"] for chunk in get_chat_chunks(demo_db, actor, run_id)) == DRAFT


def test_recovery_does_not_publish_truncated_answer_from_hf01_checkpoint(demo_db, tmp_path, monkeypatch):
    from opspilot import assistant

    _configure_runtime(monkeypatch)
    _provision_runtime(demo_db)
    actor = trusted_identity(demo_db, "support-a")
    session = create_session(demo_db, actor)["session_id"]
    run_id = admit(demo_db, session, "hf01-checkpoint-length")["run_id"]
    sends = []
    checkpoint = tmp_path / "checkpoints.sqlite3"

    class SimulatedCrash(BaseException):
        pass

    async def respond(request):
        sends.append(request.url)
        return httpx.Response(200, headers={"content-type": "text/event-stream"}, stream=stream_response(finish_reason="length"))

    def crash_before_answer(*args, **kwargs):
        raise SimulatedCrash("after the checkpoint, before the final answer")

    with registered_worker(demo_db) as first, monkeypatch.context() as patch:
        patch.setattr(assistant, "_assert_stream_completion", lambda *args: None, raising=False)
        patch.setattr(assistant, "_stream_finish_reason", lambda *args: "length", raising=False)
        patch.setattr(assistant, "complete_chat_attempt", crash_before_answer)
        with pytest.RaisesGroup(SimulatedCrash, flatten_subgroups=True, allow_unwrapped=True):
            asyncio.run(run_stream(demo_db, checkpoint, first, run_id, respond))
    _, spend, call, answers = stored_outcome(demo_db, run_id)
    assert (spend["status"], call["status"], answers) == ("DELIVERED", "OK", 0)

    with registered_worker(demo_db) as second:
        assert asyncio.run(second.recover_after_exclusive_start()) == [run_id]
        asyncio.run(run_stream(demo_db, checkpoint, second, run_id, respond))
    run, spend, _, answers = stored_outcome(demo_db, run_id)
    assert (run["status"], spend["status"], answers, len(sends)) == ("FAILED", "DELIVERED", 0, 1)
    assert "ASSISTANT_PROVIDER_STREAM_OUTPUT_TRUNCATED" in run["blocked_reason"]
    assert spend["settled_usd_micro"] == 49


def test_cancelling_outer_run_joins_blocked_read_and_keeps_unknown_reserve(demo_db, tmp_path, monkeypatch):
    _configure_runtime(monkeypatch)
    _provision_runtime(demo_db)
    actor = trusted_identity(demo_db, "support-a")
    session = create_session(demo_db, actor)["session_id"]
    run_id = admit(demo_db, session, "cancel-stream")["run_id"]
    sends = []

    async def scenario(worker):
        reading = asyncio.Event()
        finished_reading = asyncio.Event()
        read_task = None
        closed = False

        class BlockingStream(httpx.AsyncByteStream):
            async def __aiter__(self):
                nonlocal read_task
                yield _chunk(delta={"role": "assistant", "content": DRAFT})
                read_task = asyncio.current_task()
                reading.set()
                try:
                    await asyncio.Event().wait()
                finally:
                    finished_reading.set()

            async def aclose(self):
                nonlocal closed
                closed = True

        async def respond(request):
            sends.append(request.url)
            return httpx.Response(200, headers={"content-type": "text/event-stream"}, stream=BlockingStream())

        task = asyncio.create_task(run_stream(demo_db, tmp_path / "checkpoints.sqlite3", worker, run_id, respond))
        try:
            await asyncio.wait_for(reading.wait(), 10)
            async with asyncio.timeout(3):
                while not get_chat_chunks(demo_db, actor, run_id):
                    await asyncio.sleep(0.025)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            assert read_task is not None and read_task.done()
            assert finished_reading.is_set() and closed
        finally:
            if not task.done():
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task
            if read_task is not None and not read_task.done():
                read_task.cancel()
                await asyncio.gather(read_task, return_exceptions=True)

    with registered_worker(demo_db) as worker:
        asyncio.run(scenario(worker))
    run, spend, call, answers = stored_outcome(demo_db, run_id)
    assert (run["status"], call["status"], spend["status"], answers) == ("FAILED", "UNKNOWN", "UNKNOWN", 0)
    assert "ASSISTANT_PROVIDER_RESULT_UNKNOWN" in run["blocked_reason"]
    assert spend["settled_usd_micro"] is None and spend["reserved_usd_micro"] > 0
    with connect(demo_db) as connection:
        assert connection.execute("SELECT status FROM chat_attempts WHERE run_id=?", (run_id,)).fetchone()[0] == "FAILED"
    chunks = get_chat_chunks(demo_db, actor, run_id)
    assert [(item["chunk_seq"], item["body"]) for item in chunks] == [(1, DRAFT)]
    with registered_worker(demo_db) as replacement:
        assert asyncio.run(replacement.recover_after_exclusive_start()) == []
        assert runtime.recover_interrupted_sends(demo_db, replacement.owner_id) == []
        assert next_worker_run(demo_db) is None
    assert len(sends) == 1


@pytest.mark.parametrize("session_kind", ["empty", "selected", "origin"])
def test_single_session_export_includes_only_own_or_actual_chat_memory(demo_db, tmp_path, monkeypatch, session_kind):
    _configure_runtime(monkeypatch)
    _provision_runtime(demo_db)
    actor = trusted_identity(demo_db, "support-a")
    session_a = create_session(demo_db, actor)["session_id"]
    session_b = create_session(demo_db, actor)["session_id"]
    selected = save_preference(demo_db, session_a, "answer.java", "I prefer Java examples.")
    unrelated = save_preference(demo_db, session_a, "topic.music", "I prefer baroque music.", mode="RELEVANT")
    assert selected["memory_id"] != unrelated["memory_id"]

    if session_kind == "selected":
        body = "Explain an API. Authorization: Bearer mock-token-private-123\nCookie: demo=mock-cookie-private-123\nAPI Key: sk-mock-private-api-key12345"
        run_id = admit(demo_db, session_b, "export-recall", body)["run_id"]
        wire = []

        async def respond(request):
            wire.append(json.loads(request.content))
            return httpx.Response(200, headers={"content-type": "text/event-stream"}, stream=stream_response())

        with registered_worker(demo_db) as worker:
            asyncio.run(run_stream(demo_db, tmp_path / "checkpoints.sqlite3", worker, run_id, respond))
        assert stored_outcome(demo_db, run_id)[0]["status"] == "SUCCEEDED"
        assert len(wire) == 1
        assert selected["memory_id"] in json.dumps(wire)
        assert unrelated["memory_id"] in json.dumps(wire)

    exporter = runpy.run_path(str(Path(__file__).resolve().parents[1] / "scripts/user-demo/export_live_evidence.py"))
    export = exporter["export_session"]
    evidence_dir = tmp_path / "evidence"
    monkeypatch.setitem(export.__globals__, "DB_PATH", demo_db)
    monkeypatch.setitem(export.__globals__, "EVIDENCE_DIR", evidence_dir)
    output = evidence_dir / "session.json"
    session_id = session_a if session_kind == "origin" else session_b
    selected_session_memories = {selected["memory_id"], unrelated["memory_id"]}
    expected = {
        "empty": set(), "selected": selected_session_memories,
        "origin": selected_session_memories,
    }[session_kind]
    assert export(session_id, output)["memories"] == len(expected)
    text = output.read_text(encoding="utf-8")
    evidence = json.loads(text)
    assert {row["memory_id"] for row in evidence["personal_memories"]} == expected
    assert {row["memory_id"] for row in evidence["personal_memory_events"]} == expected
    with pytest.raises(RuntimeError, match="EVIDENCE_OUTPUT_MUST_STAY_INSIDE_ISOLATED_RUNTIME"):
        export(session_id, tmp_path / "outside.json")
    if session_kind == "selected":
        assert evidence["personal_memories"][0]["source_session_id"] == session_a
        assert evidence["personal_memories"][0]["source_refs_json"][0]["id"] == selected["source_message_id"]
        assert evidence["personal_memories"][0]["source_refs_json"][0]["digest"]
        assert unrelated["memory_id"] in text and "baroque music" in text
        assert "mock-token-private-123" not in text
        assert "mock-cookie-private-123" not in text
        assert "sk-mock-private-api-key12345" not in text
        assert "[REDACTED]" in text


def test_session_export_does_not_disclose_unrelated_memory_comparison_payload(demo_db, tmp_path, monkeypatch):
    from opspilot.domain import personal_memory_consolidation as consolidation

    _configure_runtime(monkeypatch)
    _provision_runtime(demo_db)
    actor = trusted_identity(demo_db, "support-a")
    session_a = create_session(demo_db, actor)["session_id"]
    other_content = "I prefer baroque music."
    other = save_preference(demo_db, session_a, "outside.preference", other_content)
    set_learning(demo_db, True)
    session_b = create_session(demo_db, actor)["session_id"]
    completed_messages(demo_db, session_b, "compare-for-export", 6)
    sends = []

    async def respond(request):
        source_material = json.loads(json.loads(request.content)["messages"][-1]["content"].split("\n", 1)[1])
        sends.append(source_material)
        return httpx.Response(200, json={
            "id": "fixture-memory-comparison", "object": "chat.completion", "created": 1,
            "model": "deepseek-flash", "choices": [{"index": 0, "finish_reason": "stop", "message": {
                "role": "assistant", "content": json.dumps({"proposals": [{"action": "KEEP", "content": other_content}]}),
            }}], "usage": USAGE,
        })

    async def consolidate(worker, job):
        async with model_for(demo_db, job["source_run_id"], respond) as (model, binding):
            return await consolidation.process_personal_memory_job(
                demo_db, worker.owner_id, job["job_id"], model,
                runtime_binding=binding, worker_epoch=worker.epoch,
            )

    with registered_worker(demo_db) as worker:
        job = consolidation.claim_next_personal_memory_job(demo_db, worker.owner_id)
        asyncio.run(consolidate(worker, job))
    assert [row["memory_id"] for row in sends[0]["existing_personal_memory"]] == [other["memory_id"]]

    exporter = runpy.run_path(str(Path(__file__).resolve().parents[1] / "scripts/user-demo/export_live_evidence.py"))
    export = exporter["export_session"]
    evidence_dir = tmp_path / "evidence"
    monkeypatch.setitem(export.__globals__, "DB_PATH", demo_db)
    monkeypatch.setitem(export.__globals__, "EVIDENCE_DIR", evidence_dir)
    output = evidence_dir / "session-b.json"
    export(session_b, output)
    text = output.read_text(encoding="utf-8")
    evidence = json.loads(text)
    assert other["memory_id"] not in text and other_content not in text
    assert evidence["personal_memories"] == [] and evidence["personal_memory_events"] == []
    call = evidence["assistant_calls_actual_model_input_output"][0]
    exported_context = json.loads(call["request_json"]["messages"][-1]["data"]["content"].split("\n", 1)[1])
    assert len(exported_context["sources"]) == 6 and exported_context["existing_personal_memory"] == []
    assert call["result_json"] == {"omitted": "CROSS_SESSION_MEMORY_COMPARISON"}
    assert len(evidence["runtime_spends"]) == 1
