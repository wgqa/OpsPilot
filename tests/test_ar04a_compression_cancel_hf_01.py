"""AR-04A-COMPRESSION-CANCEL-HF-01: cancellation must close the spend ledger.

Mock Provider only. No real network, no paid request, no business write.
"""
from __future__ import annotations

import asyncio
import json
import threading
import time

import httpx
from langchain_openai import ChatOpenAI

from test_ar04a_compression_budget_hf_01 import (
    EXPERIMENT_ID, MockProvider, _completion, _prepare_six_turn_history, _send,
    _summary_document,
)
from test_ar04a_context_journey_01 import (
    ORIGIN, PASSWORDS, _chat_bodies, _login, _padded,
)

def _compression_in(body: dict) -> bool:
    return any(
        "Compress only the supplied conversation" in str(item.get("content", ""))
        for item in body.get("messages", [])
    )


class BlockingProvider(MockProvider):
    """Responds normally except for the compression call, which stays in flight."""

    def __init__(self):
        super().__init__()
        self.compression_started = threading.Event()
        self.block = False

    def factory(self):
        clients = []

        def build():
            async_client = httpx.AsyncClient(
                timeout=httpx.Timeout(60), trust_env=False, follow_redirects=False,
                transport=httpx.MockTransport(self.handler()),
            )
            sync_client = httpx.Client(
                timeout=httpx.Timeout(60), trust_env=False, follow_redirects=False,
                transport=httpx.MockTransport(lambda _: httpx.Response(500)),
            )
            clients.append((async_client, sync_client))
            return ChatOpenAI(
                model="deepseek-flash", api_key="offline-placeholder",
                base_url="https://api.deepseek.com/v1", temperature=0, timeout=60,
                max_retries=0, stream_usage=True, include_response_headers=True,
                http_async_client=async_client, http_client=sync_client,
                http_socket_options=(),
                extra_body={"max_tokens": 2048, "thinking": {"type": "disabled"}},
            )
        build.clients = clients
        return build

    def handler(self):
        async def handle(request: httpx.Request) -> httpx.Response:
            body = json.loads((await request.aread()).decode("utf-8"))
            index = len(self.requests)
            self.requests.append(body)
            if _compression_in(body) and self.block:
                self.compression_requests.append(body)
                self.compression_started.set()
                while True:  # hold the Provider request open until cancelled
                    await asyncio.sleep(0.05)
            return httpx.Response(
                200, json=_completion("HTTP 202 只表示受理，不证明下游处理完成。", index),
            )
        return handle


class TwoBatchProvider(BlockingProvider):
    """First compression is answered; the second stays in flight until cancelled."""

    def __init__(self):
        super().__init__()
        self.second_started = threading.Event()
        self.compression_seen = 0

    def handler(self):
        async def handle(request: httpx.Request) -> httpx.Response:
            body = json.loads((await request.aread()).decode("utf-8"))
            index = len(self.requests)
            self.requests.append(body)
            if _compression_in(body):
                self.compression_seen += 1
                self.compression_requests.append(body)
                if self.compression_seen == 1:
                    return httpx.Response(
                        200, json=_completion(_summary_document(body), index),
                    )
                self.second_started.set()
                while True:
                    await asyncio.sleep(0.05)
            return httpx.Response(
                200, json=_completion("HTTP 202 只表示受理，不证明下游处理完成。", index),
            )
        return handle


def _make_app(demo_db, tmp_path, provider, *, experiment_id=None):
    from opspilot.web.app import create_app

    return create_app(
        db_path=demo_db,
        checkpoint_db_path=tmp_path / f"cancel-checkpoint-{time.time_ns()}.sqlite3",
        start_worker=True,
        credentials=PASSWORDS,
        expected_origin=ORIGIN,
        assistant_model_factory=provider.factory(),
        assistant_experiment_id=experiment_id,
    )


def _rows(db_path):
    from opspilot.domain.database import connect

    with connect(db_path) as connection:
        call = connection.execute(
            "SELECT * FROM assistant_calls WHERE kind='MODEL' AND logical_key LIKE 'context-compression:%'"
        ).fetchone()
        dispatch = connection.execute(
            "SELECT * FROM ar02_live_dispatches WHERE logical_key LIKE 'context-compression:%'"
        ).fetchone()
        attempt = connection.execute(
            "SELECT * FROM context_compression_attempts ORDER BY created_at DESC LIMIT 1"
        ).fetchone()
        budget = connection.execute(
            "SELECT status FROM ar02_live_experiment_budgets WHERE experiment_id=?",
            (EXPERIMENT_ID,),
        ).fetchone()
        summary_count = connection.execute(
            "SELECT COUNT(*) FROM context_summaries"
        ).fetchone()[0]
    return call, dispatch, attempt, (budget["status"] if budget else None), summary_count


def _cancel_during_compression(demo_db, tmp_path, provider):
    """Drive one long-session turn until the compression request is in flight, then cancel."""
    from fastapi.testclient import TestClient

    app = _make_app(demo_db, tmp_path, provider, experiment_id=EXPERIMENT_ID)
    manager = TestClient(app)
    client = manager.__enter__()
    try:
        headers = _login(client)
        session_id = client.post("/api/sessions", headers=headers).json()["session_id"]
        _prepare_six_turn_history(client, headers, session_id)
        provider.block = True
        response = client.post(
            f"/api/sessions/{session_id}/assistant/messages",
            headers={**headers, "Idempotency-Key": "hf-cancel-trigger"},
            json={"body": _chat_bodies()[6]},
        )
        assert response.status_code == 202, response.text
        run_id = response.json()["run_id"]
        assert provider.compression_started.wait(timeout=30), "compression request never started"
    finally:
        manager.__exit__(None, None, None)
    return run_id


def test_cancelled_in_flight_compression_is_recorded_unknown(demo_db, tmp_path):
    from opspilot.domain.assistant_experiment import initialize_experiment

    initialize_experiment(demo_db, EXPERIMENT_ID)
    provider = BlockingProvider()
    run_id = _cancel_during_compression(demo_db, tmp_path, provider)

    call, dispatch, attempt, budget_status, summaries = _rows(demo_db)
    assert call is not None, "compression Model Call row must exist"
    assert str(call["status"]) == "UNKNOWN", (
        str(call["status"]),
        None if dispatch is None else str(dispatch["status"]),
        None if attempt is None else str(attempt["status"]),
        budget_status,
    )
    assert dispatch is not None
    assert str(dispatch["status"]) == "UNKNOWN"
    assert int(dispatch["reserved_usd_micro"]) > 0, "UNKNOWN must keep the reservation"
    assert str(attempt["status"]) == "FAILED"
    assert budget_status == "BUDGET_BREACH"
    assert summaries == 0
    assert len(provider.compression_requests) == 1
    assert str(call["run_id"]) == run_id


def test_cancelled_compression_is_not_resent_on_recovery(demo_db, tmp_path):
    from fastapi.testclient import TestClient
    from opspilot.domain.assistant_experiment import initialize_experiment
    from opspilot.domain.database import connect

    initialize_experiment(demo_db, EXPERIMENT_ID)
    provider = BlockingProvider()
    run_id = _cancel_during_compression(demo_db, tmp_path, provider)
    sent_before = len(provider.compression_requests)

    with connect(demo_db) as connection:
        connection.execute(
            "UPDATE task_runs SET status='INTERRUPTED_RECOVERABLE', ended_at=NULL WHERE run_id=?",
            (run_id,),
        )

    replay_provider = MockProvider()
    app = _make_app(demo_db, tmp_path, replay_provider, experiment_id=EXPERIMENT_ID)
    deadline = time.monotonic() + 30
    blocked_reason = None
    status = None
    with TestClient(app) as client:
        while time.monotonic() < deadline:
            with connect(demo_db) as connection:
                row = connection.execute(
                    "SELECT status, blocked_reason FROM task_runs WHERE run_id=?", (run_id,)
                ).fetchone()
            status, blocked_reason = str(row["status"]), row["blocked_reason"]
            if status in {"SUCCEEDED", "FAILED", "BLOCKED", "CANCELLED"}:
                break
            time.sleep(0.1)

    assert status == "FAILED", (status, blocked_reason)
    assert "ASSISTANT_EXTERNAL_RESULT_UNKNOWN" in str(blocked_reason), blocked_reason
    assert replay_provider.compression_requests == []
    assert len(provider.compression_requests) == sent_before
    _, dispatch, _, budget_status, _ = _rows(demo_db)
    assert str(dispatch["status"]) == "UNKNOWN"
    assert budget_status == "BUDGET_BREACH"


def test_second_compression_cancel_keeps_first_settled(demo_db, tmp_path, monkeypatch):
    """Two compression batches in one Run: the first stays settled, the second is UNKNOWN."""
    import hashlib

    from fastapi.testclient import TestClient
    from opspilot.domain import chat as chat_domain
    from opspilot.domain.assistant_experiment import initialize_experiment
    from opspilot.domain.database import connect

    initialize_experiment(demo_db, EXPERIMENT_ID)
    provider = TwoBatchProvider()
    app = _make_app(demo_db, tmp_path, provider, experiment_id=EXPERIMENT_ID)

    real_assert = chat_domain.assert_chat_compression_sources_current
    mutated = {"done": False}

    def assert_then_mutate(*args, **kwargs):
        result = real_assert(*args, **kwargs)
        if result.get("current") and not mutated["done"]:
            # Simulate a source change between compression reservation and commit:
            # the first summary is invalidated, so a second batch is needed.
            mutated["done"] = True
            with connect(demo_db) as connection:
                row = connection.execute(
                    "SELECT message_id, body FROM messages WHERE role='ASSISTANT' "
                    "ORDER BY sequence LIMIT 1"
                ).fetchone()
                body = str(row["body"]) + " [source updated]"
                connection.execute(
                    "UPDATE messages SET body=?, body_digest=? WHERE message_id=?",
                    (body, hashlib.sha256(body.encode("utf-8")).hexdigest(), str(row["message_id"])),
                )
        return result

    monkeypatch.setattr(
        chat_domain, "assert_chat_compression_sources_current", assert_then_mutate,
    )
    manager = TestClient(app)
    client = manager.__enter__()
    try:
        headers = _login(client)
        session_id = client.post("/api/sessions", headers=headers).json()["session_id"]
        # Seven moderate turns stay below the budget; the eighth (pasted material)
        # triggers compression once the first user/assistant pair is old history.
        for index in range(1, 8):
            item, run = _send(
                client, headers, session_id, f"hf-two-batch-history-{index}",
                _padded(f"第 {index} 轮追问：协议里的重试与 ACK 语义是什么？", 600),
            )
            assert run["status"] == "SUCCEEDED", run
        response = client.post(
            f"/api/sessions/{session_id}/assistant/messages",
            headers={**headers, "Idempotency-Key": "hf-two-batch-cancel"},
            json={"body": _padded("最后一批排查材料：回调配置如下。", 5000)},
        )
        assert response.status_code == 202, response.text
        if not provider.second_started.wait(timeout=30):
            with connect(demo_db) as connection:
                attempts = connection.execute(
                    "SELECT status, error_class FROM context_compression_attempts ORDER BY created_at"
                ).fetchall()
                calls = connection.execute(
                    "SELECT status, logical_key FROM assistant_calls WHERE kind='MODEL' ORDER BY created_at"
                ).fetchall()
                run_row = connection.execute(
                    "SELECT blocked_reason FROM task_runs WHERE run_id=?",
                    (response.json()["run_id"],),
                ).fetchone()
            items = client.get(f"/api/sessions/{session_id}/messages").json()["items"]
            raise AssertionError({
                "attempts": [dict(row) for row in attempts],
                "calls": [dict(row) for row in calls],
                "compression_seen": provider.compression_seen,
                "mutated": mutated["done"],
                "blocked_reason": run_row[0] if run_row else None,
                "last_notice": items[-1]["body"][:300] if items else None,
            })
    finally:
        manager.__exit__(None, None, None)

    with connect(demo_db) as connection:
        calls = connection.execute(
            "SELECT * FROM assistant_calls WHERE kind='MODEL' "
            "AND logical_key LIKE 'context-compression:%' ORDER BY created_at"
        ).fetchall()
        dispatches = connection.execute(
            "SELECT * FROM ar02_live_dispatches WHERE logical_key LIKE 'context-compression:%' "
            "ORDER BY created_at"
        ).fetchall()
        attempts = connection.execute(
            "SELECT * FROM context_compression_attempts ORDER BY created_at"
        ).fetchall()
        budget = connection.execute(
            "SELECT status FROM ar02_live_experiment_budgets WHERE experiment_id=?",
            (EXPERIMENT_ID,),
        ).fetchone()
        summary_count = connection.execute("SELECT COUNT(*) FROM context_summaries").fetchone()[0]

    assert len(calls) == 2, [str(row["status"]) for row in calls]
    assert str(calls[0]["status"]) == "OK"
    assert str(calls[1]["status"]) == "UNKNOWN"
    assert len(dispatches) == 2
    assert str(dispatches[0]["status"]) == "OK"
    assert str(dispatches[0]["usage_state"]) == "KNOWN"
    assert int(dispatches[0]["settled_usd_micro"]) > 0
    assert str(dispatches[1]["status"]) == "UNKNOWN"
    assert int(dispatches[1]["reserved_usd_micro"]) > 0
    assert str(budget["status"]) == "BUDGET_BREACH"
    assert summary_count == 0
    assert not any(str(row["status"]) == "RESERVED" for row in calls)
    assert not any(str(row["status"]) == "RESERVED" for row in dispatches)
    assert not any(str(row["status"]) == "RESERVED" for row in attempts)
    assert provider.compression_seen == 2


def test_cancel_during_reservation_leaves_no_dangling_dispatch(demo_db, tmp_path, monkeypatch):
    """Cancellation after the Model Call reserve but before any send releases the dispatch."""
    from fastapi.testclient import TestClient
    from opspilot.domain import assistant as assistant_domain
    from opspilot.domain.assistant_experiment import initialize_experiment
    from opspilot.domain.database import connect

    initialize_experiment(demo_db, EXPERIMENT_ID)
    provider = MockProvider()
    app = _make_app(demo_db, tmp_path, provider, experiment_id=EXPERIMENT_ID)

    real_reserve = assistant_domain.reserve

    def reserve_then_cancel(*args, **kwargs):
        result = real_reserve(*args, **kwargs)
        if str(args[3]).startswith("context-compression:"):
            raise asyncio.CancelledError()
        return result

    monkeypatch.setattr(assistant_domain, "reserve", reserve_then_cancel)
    with TestClient(app) as client:
        headers = _login(client)
        session_id = client.post("/api/sessions", headers=headers).json()["session_id"]
        _prepare_six_turn_history(client, headers, session_id)
        response = client.post(
            f"/api/sessions/{session_id}/assistant/messages",
            headers={**headers, "Idempotency-Key": "hf-cancel-reserve"},
            json={"body": _chat_bodies()[6]},
        )
        assert response.status_code == 202, response.text
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            with connect(demo_db) as connection:
                row = connection.execute(
                    "SELECT status FROM assistant_calls WHERE kind='MODEL' AND logical_key LIKE 'context-compression:%'"
                ).fetchone()
            if row is not None and str(row["status"]) != "RESERVED":
                break
            time.sleep(0.05)

    with connect(demo_db) as connection:
        call = connection.execute(
            "SELECT * FROM assistant_calls WHERE kind='MODEL' AND logical_key LIKE 'context-compression:%'"
        ).fetchone()
        dispatch = connection.execute(
            "SELECT * FROM ar02_live_dispatches WHERE logical_key LIKE 'context-compression:%'"
        ).fetchone()
        attempt = connection.execute(
            "SELECT * FROM context_compression_attempts ORDER BY created_at DESC LIMIT 1"
        ).fetchone()
        budget = connection.execute(
            "SELECT status FROM ar02_live_experiment_budgets WHERE experiment_id=?",
            (EXPERIMENT_ID,),
        ).fetchone()
    assert call is not None and str(call["status"]) == "FAILED"
    assert dispatch is None, "no external dispatch may exist for a pre-send cancellation"
    assert attempt is not None and str(attempt["status"]) == "FAILED"
    assert str(budget["status"]) == "OPEN"
    assert provider.compression_requests == []
