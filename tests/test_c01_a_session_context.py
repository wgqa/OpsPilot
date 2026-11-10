"""C01-A session pagination and bounded-context regressions.

All Assistant calls use deterministic local fixtures and isolated SQLite files.
"""
from __future__ import annotations

import hashlib
import json
import time
import asyncio
from types import SimpleNamespace

from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from opspilot.domain.database import connect
from opspilot.web.app import create_app

ORIGIN = "http://c01-a-session-context-local"
PASSWORDS = {"support-a": "c01-a-fixture"}


def _login(client: TestClient) -> dict[str, str]:
    response = client.post(
        "/api/auth/login", headers={"Origin": ORIGIN},
        json={"actor_id": "support-a", "password": PASSWORDS["support-a"]},
    )
    assert response.status_code == 200, response.text
    return {"Origin": ORIGIN, "X-CSRF-Token": response.json()["csrf_token"]}


def _wait_run(client: TestClient, run_id: str, timeout: float = 30.0) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        response = client.get(f"/api/runs/{run_id}")
        assert response.status_code == 200, response.text
        result = response.json()
        if result["status"] in {"SUCCEEDED", "FAILED", "BLOCKED", "CANCELLED"}:
            return result
        time.sleep(0.025)
    raise AssertionError(f"Run did not finish before timeout: {run_id}")


def _seed_user_messages(db_path, session_id: str, tenant_id: str, count: int, *, first_body: str = "") -> None:
    with connect(db_path) as connection:
        connection.executemany(
            """INSERT INTO messages
               (message_id,tenant_id,session_id,task_id,sequence,role,input_kind,body,body_digest,
                command_id,created_at)
               VALUES (?, ?, ?, NULL, ?, 'USER', 'CHAT_READONLY', ?, ?, ?, '2026-11-10T00:00:00Z')""",
            [
                (
                    f"fixture-message-{session_id}-{sequence}", tenant_id, session_id, sequence,
                    first_body if sequence == 1 and first_body else (
                        f"历史会话第 {sequence} 轮。" + ("这是普通协议讨论和排查上下文。" * 24)
                    ),
                    hashlib.sha256((first_body if sequence == 1 and first_body else (
                        f"历史会话第 {sequence} 轮。" + ("这是普通协议讨论和排查上下文。" * 24)
                    )).encode("utf-8")).hexdigest(),
                    f"fixture-command-{session_id}-{sequence}",
                )
                for sequence in range(1, count + 1)
            ],
        )


def test_message_pages_show_latest_then_load_older_and_survive_app_restart(demo_db, tmp_path):
    checkpoint_path = tmp_path / "c01-a-pages-checkpoint.sqlite3"
    app = create_app(
        db_path=demo_db, checkpoint_db_path=checkpoint_path,
        start_worker=False, credentials=PASSWORDS, expected_origin=ORIGIN,
    )
    with TestClient(app) as client:
        headers = _login(client)
        session_a = client.post("/api/sessions", headers=headers).json()["session_id"]
        session_b = client.post("/api/sessions", headers=headers).json()["session_id"]
        tenant_id = client.get("/api/auth/me").json()["tenant_id"]
        _seed_user_messages(demo_db, session_a, tenant_id, 1200)
        _seed_user_messages(demo_db, session_b, tenant_id, 1, first_body="SESSION_B_ONLY")

        latest = client.get(
            f"/api/sessions/{session_a}/messages?limit=500&latest=true",
        ).json()
        assert [item["sequence"] for item in latest["items"]] == list(range(701, 1201))
        assert latest["has_more_before"] is True
        assert latest["has_more_after"] is False

        older = client.get(
            f"/api/sessions/{session_a}/messages?limit=500&before_seq=701",
        ).json()
        assert [item["sequence"] for item in older["items"]] == list(range(201, 701))
        assert older["has_more_before"] is True
        oldest = client.get(
            f"/api/sessions/{session_a}/messages?limit=500&before_seq=201",
        ).json()
        assert [item["sequence"] for item in oldest["items"]] == list(range(1, 201))
        assert oldest["has_more_before"] is False

        other = client.get(f"/api/sessions/{session_b}/messages?limit=500&latest=true").json()
        assert [item["body"] for item in other["items"]] == ["SESSION_B_ONLY"]

    # A new app/worker process over the same isolated Domain database sees the
    # same Session and latest messages without touching the checkpoint store.
    restarted = create_app(
        db_path=demo_db, checkpoint_db_path=checkpoint_path,
        start_worker=False, credentials=PASSWORDS, expected_origin=ORIGIN,
    )
    with TestClient(restarted) as client:
        _login(client)
        restored = client.get(
            f"/api/sessions/{session_a}/messages?limit=500&latest=true",
        ).json()
        assert restored["items"][-1]["body"].startswith("历史会话第 1200 轮")
        assert restored["items"][0]["sequence"] == 701


def test_unsummarized_history_before_former_500_row_window_reaches_compression(demo_db, tmp_path, monkeypatch):
    from opspilot.domain.chat import _prepare_context

    monkeypatch.delenv("OPSPILOT_CONTEXT_STRATEGY", raising=False)
    monkeypatch.setenv("OPSPILOT_CONTEXT_INPUT_BUDGET_TOKENS", "12000")
    app = create_app(
        db_path=demo_db, checkpoint_db_path=tmp_path / "c01-a-history-checkpoint.sqlite3",
        start_worker=False, credentials=PASSWORDS, expected_origin=ORIGIN,
    )
    with TestClient(app) as client:
        headers = _login(client)
        session_id = client.post("/api/sessions", headers=headers).json()["session_id"]
        tenant_id = client.get("/api/auth/me").json()["tenant_id"]
        goal = "C01A_INITIAL_GOAL_KEEP_UNTIL_SUMMARIZED"
        _seed_user_messages(demo_db, session_id, tenant_id, 501, first_body=goal)
        accepted = client.post(
            f"/api/sessions/{session_id}/assistant/messages",
            headers={**headers, "Idempotency-Key": "c01-a-history-current"},
            json={"body": "当前问题：继续检查最初目标。"},
        )
        assert accepted.status_code == 202, accepted.text
        run_id = accepted.json()["run_id"]

    with connect(demo_db) as connection:
        run = connection.execute("SELECT * FROM task_runs WHERE run_id=?", (run_id,)).fetchone()
        prepared = _prepare_context(connection, run, "deepseek-flash", demo_db)
    assert prepared["needs_compression"] is True
    compression_source = json.dumps(prepared["compression_messages"], ensure_ascii=False)
    assert goal in compression_source
    assert f"fixture-message-{session_id}-1" in prepared["compression_work"]["allowed_message_ids"]


def test_large_mock_mcp_tool_results_are_projected_without_mutating_checkpoint_messages(monkeypatch):
    from opspilot.assistant import _fit_tool_messages_to_budget

    monkeypatch.setenv("OPSPILOT_CONTEXT_INPUT_BUDGET_TOKENS", "900")
    payload_a = {
        "observation_id": "observation-mock-a", "evidence_id": "evidence-mock-a",
        "facts": {"summary": "verified result A", "payload": "A" * 18000},
    }
    payload_b = {
        "observation_id": "observation-mock-b", "evidence_id": "evidence-mock-b",
        "facts": {"summary": "verified result B", "payload": "B" * 18000},
    }
    raw_a, raw_b = json.dumps(payload_a), "B" * 18000
    call_a = AIMessage(content="", tool_calls=[{"name": "mock_read", "args": {}, "id": "mock-call-a"}])
    result_a = ToolMessage(
        name="mock_read", tool_call_id="mock-call-a", content=raw_a, artifact=payload_a,
    )
    call_b = AIMessage(content="", tool_calls=[{"name": "mock_read", "args": {}, "id": "mock-call-b"}])
    result_b = ToolMessage(
        name="mock_read", tool_call_id="mock-call-b", content=raw_b, artifact=payload_b,
    )
    checkpoint_messages = [
        SystemMessage(content="Read-only assistant context."),
        HumanMessage(content="Explain the current verified result."),
        call_a, result_a, call_b, result_b,
    ]

    bounded, projections, budget = _fit_tool_messages_to_budget(
        checkpoint_messages, "deepseek-flash", [], {},
    )

    assert budget["estimated_input_tokens"] <= budget["input_budget_tokens"]
    assert len(bounded) == len(checkpoint_messages)
    assert [item.tool_call_id for item in bounded if isinstance(item, ToolMessage)] == [
        "mock-call-a", "mock-call-b",
    ]
    assert [call["id"] for item in bounded if isinstance(item, AIMessage) for call in item.tool_calls] == [
        "mock-call-a", "mock-call-b",
    ]
    assert len(projections) == 2
    projected_results = [item for item in bounded if isinstance(item, ToolMessage)]
    for item, expected_id in zip(projected_results, ("evidence-mock-a", "evidence-mock-b")):
        envelope = json.loads(item.content)
        assert envelope["context_projection"] == "LOSSY_TOOL_RESULT_EXCERPT"
        assert envelope["tool_call_id"] == item.tool_call_id
        assert expected_id in {source["id"] for source in envelope["source_refs"]}
        assert envelope["original_sha256"]
        assert item.artifact is None
    assert result_a.content == raw_a and result_a.artifact == payload_a
    assert result_b.content == raw_b and result_b.artifact == payload_b


def test_loop_projects_current_run_tool_results_before_provider_and_keeps_pairing(demo_db, tmp_path, monkeypatch):
    import opspilot.assistant as assistant_module
    from opspilot.assistant import Loop

    app = create_app(
        db_path=demo_db, checkpoint_db_path=tmp_path / "c01-a-middleware-checkpoint.sqlite3",
        start_worker=False, credentials=PASSWORDS, expected_origin=ORIGIN,
    )
    with TestClient(app) as client:
        headers = _login(client)
        session_id = client.post("/api/sessions", headers=headers).json()["session_id"]
        body = "Summarize the four current observations and keep their source IDs."
        accepted = client.post(
            f"/api/sessions/{session_id}/assistant/messages",
            headers={**headers, "Idempotency-Key": "c01-a-middleware-projection"},
            json={"body": body},
        )
        assert accepted.status_code == 202, accepted.text
        with connect(demo_db) as connection:
            run = dict(connection.execute(
                "SELECT * FROM task_runs WHERE run_id=?", (accepted.json()["run_id"],),
            ).fetchone())
            source_message_id = run["source_message_id"]

    prepared = {
        "memory_guidance_messages": [], "summary_refs": [], "memory_refs": [],
        "excluded_sources": [], "selected_message_ids": [source_message_id],
        "messages": [{"role": "user", "content": body}],
    }
    observations = []
    tool_calls = []
    tool_messages = []
    for index in range(4):
        call_id = f"c01-a-mock-tool-{index}"
        artifact = {
            "evidence_id": f"c01-a-evidence-{index}",
            "observation_id": f"c01-a-observation-{index}",
            "facts": {"summary": f"Verified fixture result {index}"},
        }
        observations.append({
            "tool": "mock_read", "call_id": call_id,
            "evidence_id": artifact["evidence_id"], "observation_id": artifact["observation_id"],
        })
        tool_calls.append({"name": "mock_read", "args": {}, "id": call_id})
        tool_messages.append(ToolMessage(
            name="mock_read", tool_call_id=call_id,
            content="synthetic-only " * 20_000, artifact=artifact,
        ))
    payload = {
        "authority": "EXPLANATION_ONLY_NO_BUSINESS_RECEIPT",
        "current_run": {"run_id": run["run_id"], "business_observations": observations},
        "history_sources": [], "prior_answers": [], "task_id": None,
        "source_message_id": source_message_id, "summary_refs": [],
    }
    original_contents = [message.content for message in tool_messages]
    original_artifacts = [message.artifact for message in tool_messages]
    request_messages = [
        HumanMessage(content=body), AIMessage(content="", tool_calls=tool_calls), *tool_messages,
    ]
    loop = object.__new__(Loop)
    loop.context = lambda: (prepared, payload)
    loop.run = run
    loop.model_id = "deepseek-flash"
    loop.reserved_tokens = 0
    loop.specs = []
    loop.experiment_id = None
    loop.path = str(demo_db)
    loop.run_id = run["run_id"]
    loop.worker_id = None
    loop.runtime_grant_binding = None
    loop.trace = lambda *_args, **_kwargs: None
    loop._assert_memories_current = lambda _selected: None

    reservations = []
    monkeypatch.setattr(assistant_module, "get_config", lambda: {"metadata": {"langgraph_step": 1}})
    monkeypatch.setattr(
        assistant_module.domain, "reserve",
        lambda *args, **kwargs: (reservations.append(args) or {
            "call_id": "c01-a-mock-model-call", "logical_key": "c01-a-logical-key",
            "request_digest": "c01-a-request-digest", "status": "RESERVED",
        }, True),
    )
    monkeypatch.setattr(assistant_module.domain, "finish", lambda *_args, **_kwargs: None)

    class OfflineRequest:
        messages = request_messages
        tools = []
        tool_choice = None
        model_settings = {}

        def override(self, **kwargs):
            return SimpleNamespace(**kwargs)

    provider_requests = []

    async def handler(provider_request):
        provider_requests.append(provider_request)
        return SimpleNamespace(result=[AIMessage(content="Fixture answer with source lineage.")])

    asyncio.run(loop.awrap_model_call(OfflineRequest(), handler))

    assert len(reservations) == 1 and len(provider_requests) == 1
    wire = reservations[0][4]
    assert wire["context_budget"]["estimated_input_tokens"] <= wire["context_budget"]["input_budget_tokens"]
    sent = provider_requests[0].messages
    sent_calls = [call["id"] for item in sent if isinstance(item, AIMessage) for call in item.tool_calls]
    sent_results = [item for item in sent if isinstance(item, ToolMessage)]
    assert sent_calls == [f"c01-a-mock-tool-{index}" for index in range(4)]
    assert [item.tool_call_id for item in sent_results] == sent_calls
    for index, result in enumerate(sent_results):
        envelope = json.loads(result.content)
        assert envelope["context_projection"] == "LOSSY_TOOL_RESULT_EXCERPT"
        assert result.artifact is None
        assert f"c01-a-evidence-{index}" in {item["id"] for item in envelope["source_refs"]}
        assert f"c01-a-observation-{index}" in {item["id"] for item in envelope["source_refs"]}
    assert [message.content for message in tool_messages] == original_contents
    assert [message.artifact for message in tool_messages] == original_artifacts


def test_40_turn_session_compresses_with_fixture_model_and_isolates_session_history(demo_db, tmp_path, monkeypatch):
    from test_ar04a_context_journey_01 import LongSessionFixture

    monkeypatch.delenv("OPSPILOT_CONTEXT_STRATEGY", raising=False)
    monkeypatch.delenv("OPSPILOT_CONTEXT_INPUT_BUDGET_TOKENS", raising=False)
    model = LongSessionFixture(mode="knowledge", pad_tokens=250)
    checkpoint_path = tmp_path / "c01-a-40-turn-checkpoint.sqlite3"
    app = create_app(
        db_path=demo_db, checkpoint_db_path=checkpoint_path,
        start_worker=True, credentials=PASSWORDS, expected_origin=ORIGIN,
        assistant_model_factory=lambda: model,
    )
    with TestClient(app) as client:
        headers = _login(client)
        session_a = client.post("/api/sessions", headers=headers).json()["session_id"]
        session_b = client.post("/api/sessions", headers=headers).json()["session_id"]
        runs = []
        for turn in range(40):
            body = (
                "C01A_40_TURN_INITIAL_GOAL: explain whether HTTP 202 proves callback processing. "
                if turn == 0 else f"Turn {turn}: continue from the existing goal and explain one detail. "
            )
            accepted = client.post(
                f"/api/sessions/{session_a}/assistant/messages",
                headers={**headers, "Idempotency-Key": f"c01-a-40-turn-{turn}"},
                json={"body": body},
            )
            assert accepted.status_code == 202, accepted.text
            runs.append(accepted.json()["run_id"])
            assert _wait_run(client, runs[-1], timeout=90)["status"] == "SUCCEEDED"

        with connect(demo_db) as connection:
            summaries = connection.execute(
                "SELECT summary_json,state FROM context_summaries WHERE session_id=?",
                (session_a,),
            ).fetchall()
            attempts = connection.execute(
                "SELECT COUNT(*) FROM context_compression_attempts WHERE run_id IN ("
                + ",".join("?" for _ in runs) + ") AND status='SUCCEEDED'",
                runs,
            ).fetchone()[0]
            mcp_calls = connection.execute(
                "SELECT COUNT(*) FROM assistant_calls WHERE run_id IN ("
                + ",".join("?" for _ in runs) + ") AND kind='MCP' AND status='OK'",
                runs,
            ).fetchone()[0]
            business_writes = {
                table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                for table in ("d3_action_intents", "d3_action_ledgers", "d3_approvals", "s3_handoff_receipts")
            }
            summary_refs = connection.execute(
                "SELECT request_json FROM assistant_calls WHERE run_id IN ("
                + ",".join("?" for _ in runs) + ") AND kind='MODEL' ORDER BY created_at",
                runs,
            ).fetchall()

        assert summaries and any(row["state"] == "CURRENT" for row in summaries)
        assert all(row["state"] in {"CURRENT", "SUPERSEDED"} for row in summaries)
        assert attempts > 0
        assert mcp_calls >= 40
        assert business_writes == {
            "d3_action_intents": 0, "d3_action_ledgers": 0,
            "d3_approvals": 0, "s3_handoff_receipts": 0,
        }
        wire_text = "\n".join(str(row["request_json"]) for row in summary_refs)
        assert "C01A_40_TURN_INITIAL_GOAL" in wire_text
        assert client.get(f"/api/sessions/{session_b}/messages?latest=true").json()["items"] == []
        session_a_messages = client.get(
            f"/api/sessions/{session_a}/messages?latest=true&limit=500",
        ).json()["items"]
        assert len(session_a_messages) <= 500
        assert session_a_messages[-2]["body"].startswith("Turn 39")

    # Reopening the API over the same Domain and Checkpoint files preserves the
    # selected Session history and lets a new Run continue from its summary.
    restarted = create_app(
        db_path=demo_db, checkpoint_db_path=checkpoint_path,
        start_worker=True, credentials=PASSWORDS, expected_origin=ORIGIN,
        assistant_model_factory=lambda: model,
    )
    with TestClient(restarted) as client:
        headers = _login(client)
        restored = client.get(f"/api/sessions/{session_a}/messages?latest=true&limit=500").json()
        assert restored["items"][-2]["body"].startswith("Turn 39")
        continued = client.post(
            f"/api/sessions/{session_a}/assistant/messages",
            headers={**headers, "Idempotency-Key": "c01-a-after-restart"},
            json={"body": "After restart, preserve the initial goal and continue."},
        )
        assert continued.status_code == 202, continued.text
        assert _wait_run(client, continued.json()["run_id"], timeout=90)["status"] == "SUCCEEDED"
        after_restart = client.get(f"/api/sessions/{session_a}/messages?latest=true&limit=500").json()
        assert after_restart["items"][-2]["body"].startswith("After restart")
        assert client.get(f"/api/sessions/{session_b}/messages?latest=true").json()["items"] == []
