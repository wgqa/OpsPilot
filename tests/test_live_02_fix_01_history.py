"""History visibility through FastAPI and the real local MCP pipeline."""
import json
from datetime import timedelta

import pytest
from starlette.requests import Request

from opspilot.domain import s3, semantic_memory
from opspilot.domain.database import connect
from test_ar02_assistant import client_for
from test_ar02_runtime import FixtureModel, execute, setup_run


class HistoryFixture(FixtureModel):
    marker: str = "captured receiver snapshot"

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        result = super()._generate(messages, stop, run_manager, **kwargs)
        message = result.generations[0].message
        if message.content and not message.tool_calls:
            message.content = f"{self.marker}\n{message.content}"
        return result


def _answered(db, checkpoint, marker="captured receiver snapshot"):
    s3.prepare_s3_fixture(db, "DELIVERED_PENDING", order_id="ar02-order", contract_version=2)
    admitted = setup_run(db, "请查询当前绑定订单的状态", "s3-history", bind=True)
    result, trace = execute(db, admitted, HistoryFixture(mode="business", marker=marker), checkpoint)
    assert result["status"] == "SUCCEEDED", result
    original = next(event["answer"] for event in trace if event["event"] == "answer_committed")
    return admitted, original


def _answer(client, path, cursor="?latest=true&limit=1"):
    response = client.get(path + cursor)
    assert response.status_code == 200, response.status_code
    return next(item for item in response.json()["items"] if item["role"] == "ASSISTANT"), response


def _expire(monkeypatch):
    later = s3._now() + timedelta(seconds=s3.S3_EVIDENCE_TTL_SECONDS + 1)
    monkeypatch.setattr(s3, "_now", lambda: later)


def test_ttl_allows_owner_snapshot_but_never_new_model_input(demo_db, tmp_path, monkeypatch):
    checkpoint = tmp_path / "history-checkpoints.sqlite3"
    admitted, original = _answered(demo_db, checkpoint)
    session_path = f"/api/sessions/{admitted['session_id']}"
    path = session_path + "/messages"
    client, _ = client_for(demo_db)
    fresh, _ = _answer(client, path)
    assert fresh["body"] == original
    _expire(monkeypatch)

    def fail_on_memory_write(*_args):
        pytest.fail("history projection tried to persist semantic memory expiry")

    with monkeypatch.context() as read_only:
        read_only.setattr(semantic_memory, "_expire_scope", fail_on_memory_write)
        stale, response = _answer(client, path)
        assert stale["body"] == original
        assert stale["answer_visibility"] == "HISTORICAL_SNAPSHOT"
        assert stale["source_status"] == "S3_EVIDENCE_EXPIRED"
        assert response.headers.get("cache-control") == "no-store"
        for cursor in (f"?before_seq={fresh['sequence'] + 1}", f"?after_seq={fresh['sequence'] - 1}"):
            assert _answer(client, path, cursor)[0] == stale

    sources = client.get(f"/api/runs/{admitted['run_id']}/assistant-sources").json()
    assert not sources["current"] and all(source["result"] is None for source in sources["items"])
    chunks = client.get(f"/api/runs/{admitted['run_id']}/chunks").json()["items"]
    assert chunks == []
    outsider, _ = client_for(demo_db, "support-b")
    assert outsider.get(path).status_code == 404
    assert outsider.get(session_path + "/events/history").status_code == 404

    events = client.get(session_path + "/events/history").json()["items"]
    committed = next(item for item in events if item["event_kind"] == "CHAT_ANSWER_COMMITTED")
    assert original not in json.dumps(events, ensure_ascii=False)
    polls = 0

    async def disconnect_after_one_poll(_request):
        nonlocal polls
        polls += 1
        return polls > 1

    monkeypatch.setattr(Request, "is_disconnected", disconnect_after_one_poll)
    with client.stream("GET", session_path + "/events?after=0",
                       headers={"Last-Event-ID": str(committed["event_seq"] - 1)}) as stream:
        body = stream.read().decode()
    assert f"id: {committed['event_seq']}\nevent: CHAT_ANSWER_COMMITTED" in body
    assert original not in body and "captured receiver snapshot" not in body
    reopened, _ = client_for(demo_db)
    assert _answer(reopened, path)[0] == stale

    continuation = setup_run(demo_db, "解释接收和处理的区别", "history-follow-up",
                             session=admitted["session_id"], task=admitted["task_id"])
    model = FixtureModel()
    result, _ = execute(demo_db, continuation, model, checkpoint)
    assert result["status"] == "SUCCEEDED", result
    assert "captured receiver snapshot" not in str(model.seen)
    assert "EXCLUDED_HISTORY" in str(model.seen)
    with connect(demo_db) as db:
        assert db.execute("SELECT count(*) FROM s3_diagnoses").fetchone()[0] == 0
        assert db.execute("SELECT count(*) FROM d3_action_intents").fetchone()[0] == 0
        assert db.execute("SELECT count(*) FROM assistant_runtime_spends").fetchone()[0] == 0
    print("TTL owner snapshot retained across cursors and SSE; no stale model input or action")


def test_business_version_change_keeps_snapshot_and_fresh_query(demo_db, tmp_path):
    checkpoint = tmp_path / "version-checkpoints.sqlite3"
    admitted, original = _answered(demo_db, checkpoint)
    path = f"/api/sessions/{admitted['session_id']}/messages"
    client, _ = client_for(demo_db)
    with connect(demo_db) as db:
        db.execute("UPDATE s3_receivers SET status='PROCESSED',version=version+1 WHERE order_id='ar02-order'")
    old, _ = _answer(client, path)
    assert old["body"] == original
    assert old["answer_visibility"] == "HISTORICAL_SNAPSHOT"
    assert old["source_status"] == "S3_BUSINESS_VERSION_CHANGED"

    continuation = setup_run(demo_db, "重新查询同一 Event", "history-new-version",
                             session=admitted["session_id"], task=admitted["task_id"])
    model = HistoryFixture(mode="business", marker="new observation")
    result, _ = execute(demo_db, continuation, model, checkpoint)
    assert result["status"] == "SUCCEEDED", result
    current, _ = _answer(client, path)
    assert '"status": "PROCESSED"' in current["body"]
    assert current["answer_visibility"] == "CURRENT"
    assert "captured receiver snapshot" not in str(model.seen)
    print("Versioned business change preserved the old text and admitted a fresh same-scope observation")


@pytest.mark.parametrize(("change", "expected"), [
    ("revoked", "S3_AUTHORIZATION_UNAVAILABLE"),
    ("grant-version", "S3_AUTHORIZATION_CHANGED"),
    ("corrupt-result", "ASSISTANT_SOURCE_RESULT_INVALID"),
    ("source-message-changed", "S3_HISTORY_SOURCE_UNVERIFIED"),
    ("unversioned-fact", "S3_CURRENT_FACT_MISMATCH"),
    ("sensitive", "S3_HISTORY_SENSITIVE_CONTENT"),
])
def test_stale_snapshot_fails_closed(demo_db, tmp_path, monkeypatch, change, expected):
    marker = "Authorization: Bearer fixture-only-synthetic" if change == "sensitive" else "protected snapshot marker"
    admitted, _ = _answered(demo_db, tmp_path / "denial-checkpoints.sqlite3", marker)
    path = f"/api/sessions/{admitted['session_id']}/messages"
    _expire(monkeypatch)
    with connect(demo_db) as db:
        if change == "revoked":
            db.execute("UPDATE principal_scope_grants SET granted_scopes_json='[]',grant_version=grant_version+1 WHERE principal_id='async-principal-a'")
        elif change == "grant-version":
            db.execute("UPDATE principal_scope_grants SET grant_version=grant_version+1 WHERE principal_id='async-principal-a'")
        elif change == "corrupt-result":
            db.execute("UPDATE assistant_calls SET result_json='{}' WHERE run_id=? AND evidence_id IS NOT NULL", (admitted["run_id"],))
        elif change == "unversioned-fact":
            db.execute("UPDATE s3_receivers SET status='PROCESSED' WHERE order_id='ar02-order'")
        elif change == "source-message-changed":
            db.execute("UPDATE messages SET body='changed' WHERE message_id=?", (admitted["message_id"],))
    client, _ = client_for(demo_db)
    answer, _ = _answer(client, path)
    assert marker not in answer["body"]
    assert answer["answer_visibility"] == "HIDDEN"
    assert answer["source_status"] == expected
    if change == "revoked":
        for endpoint in ("context", "assistant-sources", "chunks", "activity"):
            assert client.get(f"/api/runs/{admitted['run_id']}/{endpoint}").status_code in (403, 404)
    print(f"Stale answer withheld: {expected}")
