"""C01-B owner-scoped Personal Memory acceptance using Fixture Model calls."""
from __future__ import annotations

import json
import hashlib
import time

from fastapi.testclient import TestClient
import pytest

from opspilot.domain.database import connect
from opspilot.web.app import create_app

ORIGIN = "http://c01-b-personal-memory-local"
PASSWORDS = {
    "support-a": "c01-b-fixture-a",
    "support-b": "c01-b-fixture-b",
    "support-c": "c01-b-fixture-c",
}


def _login(client: TestClient, actor_id: str) -> dict[str, str]:
    response = client.post(
        "/api/auth/login", headers={"Origin": ORIGIN},
        json={"actor_id": actor_id, "password": PASSWORDS[actor_id]},
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


def _ask(client: TestClient, headers: dict[str, str], session_id: str, body: str, key: str) -> str:
    accepted = client.post(
        f"/api/sessions/{session_id}/assistant/messages",
        headers={**headers, "Idempotency-Key": key}, json={"body": body},
    )
    assert accepted.status_code == 202, accepted.text
    run_id = str(accepted.json()["run_id"])
    assert _wait_run(client, run_id)["status"] == "SUCCEEDED"
    return run_id


def _run_wire(db_path, run_id: str) -> str:
    with connect(db_path) as connection:
        rows = connection.execute(
            "SELECT request_json FROM assistant_calls WHERE run_id=? AND kind='MODEL' AND status='OK'",
            (run_id,),
        ).fetchall()
    assert rows, f"No successful Fixture Model request was persisted for {run_id}"
    return "\n".join(
        json.dumps(json.loads(str(row["request_json"])).get("messages", []), ensure_ascii=False)
        for row in rows
    )


def _messages(client: TestClient, session_id: str) -> list[dict]:
    return client.get(f"/api/sessions/{session_id}/messages?latest=true&limit=500").json()["items"]


def _candidate(
    client, headers, *, source_message_id, key, content, idempotency_key,
    supersedes_memory_id=None, expected_version=None,
):
    payload = {
        "memory_kind": "WORK_HABIT", "memory_key": key, "content": content,
        "source_message_id": source_message_id,
    }
    if supersedes_memory_id is not None:
        payload["supersedes_memory_id"] = supersedes_memory_id
    if expected_version is not None:
        payload["expected_version"] = expected_version
    return client.post(
        "/api/personal-memories/candidates",
        headers={**headers, "Idempotency-Key": idempotency_key},
        json=payload,
    )


def test_personal_memory_cross_session_lifecycle_relevance_and_owner_scope(demo_db, tmp_path):
    from test_ar04a_context_journey_01 import LongSessionFixture

    with connect(demo_db) as connection:
        connection.execute(
            "INSERT INTO trusted_operators(actor_id,tenant_id,role) VALUES ('support-c','tenant-a','SUPPORT')",
        )
    fixture = LongSessionFixture(mode="s01")
    app = create_app(
        db_path=demo_db, checkpoint_db_path=tmp_path / "c01-b-personal-checkpoint.sqlite3",
        start_worker=True, credentials=PASSWORDS, expected_origin=ORIGIN,
        assistant_model_factory=lambda: fixture,
    )

    with TestClient(app) as client:
        owner_headers = _login(client, "support-a")
        session_a = client.post("/api/sessions", headers=owner_headers).json()["session_id"]
        _ask(
            client, owner_headers, session_a,
            "Please remember my callback explanation preference.", "c01-b-source-message",
        )
        source_message = next(item for item in _messages(client, session_a) if item["role"] == "USER")
        source_message_id = source_message["message_id"]
        old_content = (
            "讨论回调时，区分 HTTP 202 的受理与下游业务处理；信息不足时明确说明未知。"
        )
        create = _candidate(
            client, owner_headers, source_message_id=source_message_id,
            key="回调.202含义", content=old_content,
            idempotency_key="c01-b-personal-create-v1",
        )
        assert create.status_code == 201, create.text
        candidate = create.json()
        memory_id = candidate["memory_id"]
        assert candidate["state"] == "CANDIDATE"

        replay = _candidate(
            client, owner_headers, source_message_id=source_message_id,
            key="回调.202含义", content=old_content,
            idempotency_key="c01-b-personal-create-v1",
        )
        assert replay.status_code == 201
        assert replay.json()["memory_id"] == memory_id
        conflict = _candidate(
            client, owner_headers, source_message_id=source_message_id,
            key="回调.202含义", content=old_content + " 更新",
            idempotency_key="c01-b-personal-create-v1",
        )
        assert conflict.status_code == 409
        assert conflict.json()["code"] == "MEMORY_IDEMPOTENCY_CONFLICT"

        owner_injection = client.post(
            "/api/personal-memories/candidates",
            headers={**owner_headers, "Idempotency-Key": "c01-b-owner-injection"},
            json={
                "memory_kind": "WORK_HABIT", "memory_key": "injected.owner",
                "content": "Should be rejected", "source_message_id": source_message_id,
                "owner_actor_id": "support-c",
            },
        )
        assert owner_injection.status_code == 422

        session_b = client.post("/api/sessions", headers=owner_headers).json()["session_id"]
        before_confirmation = _ask(
            client, owner_headers, session_b,
            "HTTP 202 表示回调业务已经处理完成了吗？", "c01-b-before-confirm",
        )
        assert memory_id not in _run_wire(demo_db, before_confirmation)
        before_context = client.get(f"/api/runs/{before_confirmation}/context").json()
        assert before_context["attempts"][-1]["manifest"]["memory_refs"] == []

        confirmed = client.post(
            f"/api/personal-memories/{memory_id}/confirm",
            headers={**owner_headers, "Idempotency-Key": "c01-b-personal-confirm-v1"}, json={},
        )
        assert confirmed.status_code == 200, confirmed.text
        assert confirmed.json()["state"] == "ACTIVE"
        confirmed_replay = client.post(
            f"/api/personal-memories/{memory_id}/confirm",
            headers={**owner_headers, "Idempotency-Key": "c01-b-personal-confirm-v1"}, json={},
        )
        assert confirmed_replay.status_code == 200
        assert confirmed_replay.json()["memory_id"] == memory_id
        assert confirmed_replay.json()["state"] == "ACTIVE"

        # A nearby callback/server-error memory has one generic lexical overlap;
        # it must not pass the conservative relevance threshold.
        distractors = [
            ("回调.超时规则", "回调接口超时后先检查重试日志，不要据此判断接收方当前状态。"),
            ("editor.shortcuts", "Use Vim key chords for local code editing."),
            ("release.naming", "Prefix internal release branches with the team project code."),
            ("meeting.preference", "Keep weekly planning meetings to thirty minutes."),
            ("python.style", "Prefer small typed helpers and explicit return values."),
        ]
        for index, (key, content) in enumerate(distractors):
            proposal = _candidate(
                client, owner_headers, source_message_id=source_message_id,
                key=key, content=content, idempotency_key=f"c01-b-distractor-{index}",
            )
            assert proposal.status_code == 201, proposal.text
            result = client.post(
                f"/api/personal-memories/{proposal.json()['memory_id']}/confirm",
                headers={**owner_headers, "Idempotency-Key": f"c01-b-distractor-confirm-{index}"}, json={},
            )
            assert result.status_code == 200, result.text
            assert result.json()["state"] == "ACTIVE"

        relevant_run = _ask(
            client, owner_headers, session_b,
            "HTTP 202 表示回调业务是否已经处理完成？", "c01-b-relevant-query",
        )
        relevant_wire = _run_wire(demo_db, relevant_run)
        assert "CONFIRMED PERSONAL MEMORY GUIDANCE" in relevant_wire
        assert memory_id in relevant_wire
        assert old_content in relevant_wire
        relevant_context = client.get(f"/api/runs/{relevant_run}/context").json()
        selected_ids = {
            item["memory_id"] for item in relevant_context["attempts"][-1]["manifest"]["memory_refs"]
        }
        assert selected_ids == {memory_id}
        excluded_ids = {
            item.get("source_id") for item in relevant_context["excluded_sources"]
            if item.get("reason") == "NOT_RELEVANT_TO_QUERY"
        }
        assert {key for key, _ in distractors}.issubset(
            {item["memory_key"] for item in client.get("/api/personal-memories").json()["items"]
             if item["memory_id"] in excluded_ids}
        )

        unrelated_run = _ask(
            client, owner_headers, session_b,
            "冰岛首都是哪里？", "c01-b-unrelated-query",
        )
        assert "CONFIRMED PERSONAL MEMORY GUIDANCE" not in _run_wire(demo_db, unrelated_run)
        unrelated_context = client.get(f"/api/runs/{unrelated_run}/context").json()
        assert unrelated_context["attempts"][-1]["manifest"]["memory_refs"] == []

        session_c = client.post("/api/sessions", headers=owner_headers).json()["session_id"]
        revision = _candidate(
            client, owner_headers, source_message_id=source_message_id,
            key="回调.202含义",
            content="说明 HTTP 202 只代表受理；判断回调完成前应查询当前接收方证据。",
            idempotency_key="c01-b-personal-revision-v2",
            supersedes_memory_id=memory_id, expected_version=1,
        )
        assert revision.status_code == 201, revision.text
        assert revision.json()["version"] == 2
        stale_revision = _candidate(
            client, owner_headers, source_message_id=source_message_id,
            key="回调.202含义", content="过期更新不得覆盖当前记忆。",
            idempotency_key="c01-b-personal-stale-revision",
            supersedes_memory_id=revision.json()["memory_id"], expected_version=1,
        )
        assert stale_revision.status_code == 409
        activated_v2 = client.post(
            f"/api/personal-memories/{revision.json()['memory_id']}/confirm",
            headers={**owner_headers, "Idempotency-Key": "c01-b-personal-confirm-v2"}, json={},
        )
        assert activated_v2.status_code == 200, activated_v2.text
        assert activated_v2.json()["state"] == "ACTIVE"
        assert client.get(f"/api/personal-memories/{memory_id}").status_code == 200
        assert client.get(f"/api/personal-memories/{memory_id}").json()["state"] == "REVISED"

        updated_run = _ask(
            client, owner_headers, session_c,
            "HTTP 202 回调业务处理完成前，需要什么当前证据？",
            "c01-b-after-revision",
        )
        updated_wire = _run_wire(demo_db, updated_run)
        assert revision.json()["memory_id"] in updated_wire
        assert revision.json()["content"] in updated_wire
        assert old_content not in updated_wire
        from opspilot.assistant import Loop
        from opspilot.domain.task_control import trusted_identity

        with connect(demo_db) as connection:
            restored_run = dict(connection.execute(
                "SELECT * FROM task_runs WHERE run_id=?", (updated_run,),
            ).fetchone())
        resume_guard = object.__new__(Loop)
        resume_guard.path = str(demo_db)
        resume_guard.run = restored_run
        resume_guard.run_id = updated_run
        resume_guard.actor = trusted_identity(demo_db, "support-a")
        # run_assistant invokes this persisted-manifest guard before reusing any
        # messages loaded from the LangGraph checkpoint.
        resume_guard.assert_manifest_memories_current()

        # Same-Tenant actor and separate-Tenant actor cannot inspect, create from,
        # or recall the owner's Personal Memory.
        for actor_id, denied_code in (("support-c", "MEMORY_SCOPE_DENIED"), ("support-b", "MEMORY_SCOPE_DENIED")):
            other_headers = _login(client, actor_id)
            assert client.get(f"/api/personal-memories/{memory_id}").status_code == 404
            denied_candidate = _candidate(
                client, other_headers, source_message_id=source_message_id,
                key=f"cross-scope.{actor_id}", content="Must not bind another owner's source.",
                idempotency_key=f"c01-b-cross-scope-{actor_id}",
            )
            assert denied_candidate.status_code == 409
            assert denied_candidate.json()["code"] == "PERSONAL_MEMORY_SOURCE_REJECTED"
            other_session = client.post("/api/sessions", headers=other_headers).json()["session_id"]
            other_run = _ask(
                client, other_headers, other_session,
                "HTTP 202 回调业务处理完成前，需要什么当前证据？",
                f"c01-b-other-owner-{actor_id}",
            )
            assert revision.json()["memory_id"] not in _run_wire(demo_db, other_run)

        owner_headers = _login(client, "support-a")
        revoke = client.post(
            f"/api/personal-memories/{revision.json()['memory_id']}/revoke",
            headers={**owner_headers, "Idempotency-Key": "c01-b-personal-revoke-v2"}, json={},
        )
        assert revoke.status_code == 200, revoke.text
        assert revoke.json()["state"] == "REVOKED"
        revoke_replay = client.post(
            f"/api/personal-memories/{revision.json()['memory_id']}/revoke",
            headers={**owner_headers, "Idempotency-Key": "c01-b-personal-revoke-v2"}, json={},
        )
        assert revoke_replay.status_code == 200
        assert revoke_replay.json()["state"] == "REVOKED"
        from opspilot.domain.episodic_memory import MemorySourceRejected

        with pytest.raises(MemorySourceRejected, match="PERSONAL_MEMORY_REVOKED_EXPIRED_OR_CHANGED"):
            resume_guard.assert_manifest_memories_current()
        sanitized = _messages(client, session_c)
        old_answer = next(item for item in sanitized if item.get("answer_run_id") == updated_run)
        assert old_answer["source_status"] == "PERSONAL_MEMORY_REVOKED_EXPIRED_OR_CHANGED"
        assert "个人记忆已撤销或失效" in old_answer["body"]
        after_revoke_run = _ask(
            client, owner_headers, session_c,
            "偏好撤销后，请谨慎解释 HTTP 202 回调业务处理。",
            "c01-b-after-revoke",
        )
        after_revoke_wire = _run_wire(demo_db, after_revoke_run)
        assert revision.json()["memory_id"] not in after_revoke_wire
        assert old_content not in after_revoke_wire
        assert revision.json()["content"] not in after_revoke_wire


def test_personal_memory_source_invalidation_and_expiry_are_excluded(demo_db, tmp_path):
    from opspilot.domain.semantic_memory import (
        confirm_personal_memory, create_personal_candidate, list_personal_memories,
        personal_memory_context,
    )
    from opspilot.domain.episodic_memory import MemorySourceRejected
    from opspilot.domain.task_control import create_session, trusted_identity

    identity = trusted_identity(demo_db, "support-a")
    session = create_session(demo_db, identity)
    session_id = str(session["session_id"])
    body = "Please remember the agreed callback investigation style."
    digest = hashlib.sha256(body.encode("utf-8")).hexdigest()
    source_id = "c01-b-source-invalidation"
    with connect(demo_db) as connection:
        connection.execute(
            """INSERT INTO messages
               (message_id,tenant_id,session_id,task_id,sequence,role,input_kind,body,body_digest,command_id,created_at)
               VALUES (?, 'tenant-a', ?, NULL, 1, 'USER', 'CHAT_READONLY', ?, ?, ?, '2026-11-10T00:00:00Z')""",
            (source_id, session_id, body, digest, "c01-b-source-command"),
        )
    with pytest.raises(MemorySourceRejected, match="Secret-like content"):
        create_personal_candidate(
            demo_db, "tenant-a", "support-a", memory_kind="PREFERENCE",
            memory_key="security.secret", content="api_key=not-a-real-secret",
            source_message_id=source_id, idempotency_key="c01-b-secret-reject",
        )
    candidate = create_personal_candidate(
        demo_db, "tenant-a", "support-a", memory_kind="PREFERENCE",
        memory_key="callback.evidence-style", content="Distinguish acceptance from processing.",
        source_message_id=source_id, idempotency_key="c01-b-source-candidate",
    )
    active = confirm_personal_memory(
        demo_db, "tenant-a", candidate["memory_id"], "support-a",
        idempotency_key="c01-b-source-confirm",
    )
    with connect(demo_db) as connection:
        selected, _, _ = personal_memory_context(
            connection, "tenant-a", "support-a", "callback acceptance processing",
        )
        assert [item["memory_id"] for item in selected] == [active["memory_id"]]
        connection.execute(
            "UPDATE messages SET body_digest=? WHERE message_id=?",
            ("invalidated-source-digest", source_id),
        )
        selected_after_invalidation, excluded, _ = personal_memory_context(
            connection, "tenant-a", "support-a", "callback acceptance processing",
        )
        assert selected_after_invalidation == []
        assert any(item["reason"] == "PERSONAL_MEMORY_SOURCE_INVALID" for item in excluded)
    visible = list_personal_memories(demo_db, "tenant-a", "support-a", memory_id=active["memory_id"])
    assert visible[0]["source_current"] is False

    with connect(demo_db) as connection:
        connection.execute(
            "UPDATE personal_memories SET expires_at='2000-01-01T00:00:00.000+00:00' WHERE memory_id=?",
            (active["memory_id"],),
        )
    expired = list_personal_memories(demo_db, "tenant-a", "support-a", memory_id=active["memory_id"])
    assert expired[0]["state"] == "EXPIRED"
    with connect(demo_db) as connection:
        event = connection.execute(
            "SELECT event_type FROM personal_memory_events WHERE memory_id=? ORDER BY occurred_at DESC LIMIT 1",
            (active["memory_id"],),
        ).fetchone()
    assert event["event_type"] == "EXPIRED"
