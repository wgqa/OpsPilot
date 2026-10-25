from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

from langchain_core.messages import AIMessage

from opspilot.domain.database import connect, reset_fixture
from opspilot.domain.d2 import attempt_counts, reserve_attempt
from opspilot.s3_investigation import S3Nodes
from test_m4_c1_s3_prompt import _start_investigation_run, _business_snapshot
from test_m4_c1_hf_01 import _diagnosed_task


def _followup(tmp_path: Path):
    db = tmp_path / "continuous.sqlite3"
    reset_fixture(db, "S1_POS")
    session, task, _, _ = _diagnosed_task(db)
    _, run = _start_investigation_run(db, session, task, suffix="continuous")
    return db, task, run


class Model:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.messages = []

    def bind_tools(self, *_args, **_kwargs):
        return self

    async def ainvoke(self, messages):
        self.messages.append(messages)
        return next(self.responses)


def _node(db, task, run, model, client=None):
    return S3Nodes(db, task, run, model, "continuous-deterministic", client, [],
                   readonly_followup=True, memory_enabled=False)


def _business_only(db, task):
    value = _business_snapshot(db, task)
    value.pop("outbox_count")  # a read-only result may emit its own user-visible progress event
    return value


def test_vs01_real_transport_history_capability(tmp_path):
    # No fabricated Observation is used to establish a transport send.
    from opspilot.domain import s3_history

    db = tmp_path / "history.sqlite3"
    reset_fixture(db, "S1_POS")
    prepared = s3_history.prepare_transport_history_fixture(
        db, order_id="continuous-order", attempts=[
            {"event_id": "event-one", "http_status": 503},
            {"event_id": "event-one", "http_status": 202},
        ], receiver_status="QUEUED",
    )
    assert len(prepared["transport_trace"]) == 2
    with connect(db) as c:
        rows = [dict(row) for row in c.execute("SELECT * FROM s3_transport_attempts ORDER BY attempt_no")]
    assert [row["http_status"] for row in rows] == [503, 202]
    assert len({row["transport_request_id"] for row in rows}) == 2
    assert {row["event_id"] for row in rows} == {"event-one"}


def test_vs06_remaining_candidates_follow_observation_into_normal_decision(tmp_path):
    db, task, run = _followup(tmp_path)
    model = Model([
        AIMessage(content="two relevant candidates", tool_calls=[
            {"name": "search_callback_knowledge", "id": "first", "args": {"query": "202", "reason": "interpret acknowledgement"}},
            {"name": "get_receiver_processing", "id": "second", "args": {"reason": "check actual processing"}},
        ]),
        AIMessage(content="RESULT: PARTIAL\n当前协议检索没有结果，仍无法确认目标事件的处理状态。"),
    ])
    class Client:
        def __init__(self): self.names = []
        async def call_tool(self, name, args):
            self.names.append(name)
            return SimpleNamespace(is_error=False, structured_content={"documents": []})
    client = Client()
    node = _node(db, task, run, model, client)
    async def journey():
        state = {"evidence_ids": [], "tool_observations": []}
        state.update(await node.investigate(state))
        state.update(await node.execute(state))
        state.update(await node.investigate(state))
        return state
    asyncio.run(journey())
    second_input = json.loads(model.messages[1][-1].content)
    remaining = second_input.get("unexecuted_candidates", [])
    assert any(item["tool_name"] == "get_receiver_processing" and item.get("tool_call_id") == "second" for item in remaining)
    assert client.names == ["search_callback_knowledge"]  # no automatic execution of the second proposal
    assert len(model.messages) == 2  # no per-candidate reviewer request
    assert second_input["previous_actions"]


def test_vs08_reuses_a_current_final_answer_without_report_provider_call(tmp_path):
    db, task, run = _followup(tmp_path)
    # The real prompt/trace/source validation is exercised, not a hand-written final-answer flag.
    model = Model([AIMessage(content="RESULT: PARTIAL\n当前还没有本轮接收状态证据，不能断言已处理完成。")])
    node = _node(db, task, run, model)
    before = _business_only(db, task)
    async def journey():
        state = {"evidence_ids": [], "tool_observations": []}
        state.update(await node.investigate(state))
        state.update(await node.report(state))
        return state
    asyncio.run(journey())
    with connect(db) as c:
        row = c.execute("SELECT answer_text FROM c1_readonly_followup_runs WHERE run_id=?", (run,)).fetchone()
    assert len(model.messages) == 1
    assert row[0] == "当前还没有本轮接收状态证据，不能断言已处理完成。"
    assert _business_only(db, task) == before


def test_vs09_budget_exhaustion_delivers_explicit_nonblank_gap_without_writes(tmp_path):
    db, task, run = _followup(tmp_path)
    for i in range(8):
        reserve_attempt(db, task, "MODEL", 8, call_id=f"spent-{i}", run_id=run)
    model = Model([])
    node = _node(db, task, run, model)
    before = _business_only(db, task)
    asyncio.run(node.report({"evidence_ids": [], "tool_observations": []}))
    with connect(db) as c:
        row = c.execute("SELECT answer_text,result_state FROM c1_readonly_followup_runs WHERE run_id=?", (run,)).fetchone()
    assert row[0].strip(), "An empty PARTIAL does not answer the user or identify a concrete gap"
    assert row[1] in {"PARTIAL", "NOT_COMPLETED"}
    assert attempt_counts(db, task)["MODEL"] == 8
    assert model.messages == []
    assert _business_only(db, task) == before
