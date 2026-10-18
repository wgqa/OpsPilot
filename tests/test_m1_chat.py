from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from fastapi.testclient import TestClient

from opspilot.domain.chat import (
    complete_chat_attempt,
    get_chat_chunks,
    get_chat_manifest,
    get_task_inspector,
    persist_chat_chunk,
    prepare_chat_attempt,
)
from opspilot.domain.database import connect
from opspilot.domain.d2 import (
    create_task_binding,
    evaluate_evidence_gate,
    get_auth_policy_fact,
    get_integration_config_fact,
    get_principal_status_fact,
    probe_endpoint_fact,
    record_tool_observation,
)
from opspilot.domain.d3 import (
    activate_plan,
    create_plan_from_gate,
    execute_repair,
    get_or_create_action_intent,
    submit_plan_approval,
)
from opspilot.domain.task_control import (
    admit_task_message,
    claim_task_run,
    create_session,
    create_task_with_initial_run,
    recover_running_task_runs,
    register_worker_owner,
    trusted_identity,
)
from opspilot.web.app import create_app
from opspilot.web.worker import _provider_response_identifier


ORIGIN = "http://127.0.0.1:5173"


def _new_message(db: Path, session_id: str, body: str, *, key: str, task_id: str | None = None) -> dict[str, object]:
    identity = trusted_identity(db, "support-a")
    return admit_task_message(
        db, identity, session_id=session_id, task_id=task_id,
        input_kind="CHAT_READONLY", body=body, idempotency_key=key,
    )


def _owner(db: Path, *, owner_id: str = "chat-worker-a") -> str:
    register_worker_owner(db, owner_id, 4101)
    return owner_id


def _claim_and_prepare(db: Path, run_id: str, owner_id: str, model: str = "test-model") -> dict[str, object]:
    claim_task_run(db, trusted_identity(db, "support-a"), run_id)
    return prepare_chat_attempt(db, run_id, owner_id, model)


def _complete(db: Path, owner_id: str, prepared: dict[str, object], answer: str) -> dict[str, object]:
    attempt_id = str(prepared["attempt_id"])
    persist_chat_chunk(db, owner_id, attempt_id, 1, answer)
    return complete_chat_attempt(
        db, owner_id, attempt_id, answer,
        provider_response_id=f"provider-test-{attempt_id}",
        input_tokens=11, output_tokens=7, total_tokens=18,
    )


def test_chat_01_three_turn_context_uses_persisted_user_and_valid_assistant_messages(demo_db: Path) -> None:
    identity = trusted_identity(demo_db, "support-a")
    session_id = str(create_session(demo_db, identity)["session_id"])
    owner = _owner(demo_db)
    first = _new_message(demo_db, session_id, "Call my project Orion for this conversation.", key="chat-01-1")
    first_context = _claim_and_prepare(demo_db, str(first["run_id"]), owner)
    _complete(demo_db, owner, first_context, "I will refer to the project as Orion.")
    second = _new_message(demo_db, session_id, "What name should you use?", key="chat-01-2")
    second_context = _claim_and_prepare(demo_db, str(second["run_id"]), owner)
    transcript = "\n".join(str(item["content"]) for item in second_context["messages"])
    assert "Call my project Orion" in transcript
    assert "I will refer to the project as Orion" in transcript
    _complete(demo_db, owner, second_context, "You asked me to call it Orion.")
    third = _new_message(demo_db, session_id, "Repeat the agreed project name.", key="chat-01-3")
    third_context = _claim_and_prepare(demo_db, str(third["run_id"]), owner)
    assert "Orion" in "\n".join(str(item["content"]) for item in third_context["messages"])
    _complete(demo_db, owner, third_context, "The project name is Orion.")
    with connect(demo_db) as connection:
        counts = connection.execute(
            "SELECT role, COUNT(*) AS count FROM messages WHERE session_id = ? GROUP BY role ORDER BY role",
            (session_id,),
        ).fetchall()
        answers = connection.execute(
            "SELECT COUNT(*) FROM chat_run_answers a JOIN task_runs r ON r.run_id = a.run_id WHERE r.session_id = ?",
            (session_id,),
        ).fetchone()[0]
        run_count = connection.execute(
            "SELECT COUNT(*) FROM task_runs WHERE session_id = ? AND kind = 'CHAT_READONLY' AND status = 'SUCCEEDED'",
            (session_id,),
        ).fetchone()[0]
    assert {str(row["role"]): int(row["count"]) for row in counts} == {"ASSISTANT": 3, "USER": 3}
    assert answers == run_count == 3


def test_chat_readonly_waiting_approval_does_not_touch_business_or_graph_state(demo_db: Path, tmp_path: Path) -> None:
    identity = trusted_identity(demo_db, "support-a")
    session_id = str(create_session(demo_db, identity)["session_id"])
    task = create_task_with_initial_run(
        demo_db, identity, session_id=session_id, service_id="orders-demo",
        integration_id="integration-a", ticket_id="INC-A-001", initial_message="Investigate 401",
        idempotency_key="chat-task-create",
    )
    task_id, original_run = str(task["task_id"]), str(task["run_id"])
    with connect(demo_db) as connection:
        connection.execute("UPDATE task_bindings SET status = 'WAITING_APPROVAL' WHERE task_id = ?", (task_id,))
        connection.execute("UPDATE task_runs SET status = 'WAITING_APPROVAL' WHERE run_id = ?", (original_run,))
    tracked_tables = (
        "task_controls", "d3_plans", "d3_plan_authorizations", "d3_approvals", "d3_action_permissions",
        "d3_action_intents", "d3_action_ledgers", "d3_verification_receipts", "d3_report_artifacts",
        "d3_delivery_records", "integrations", "task_bindings",
    )
    with connect(demo_db) as connection:
        before = {table: [tuple(row) for row in connection.execute(f"SELECT * FROM {table} ORDER BY 1").fetchall()]
                  for table in tracked_tables}
    owner = _owner(demo_db)
    accepted = _new_message(demo_db, session_id, "Please explain the current investigation.", key="chat-task-follow-up", task_id=task_id)
    prepared = _claim_and_prepare(demo_db, str(accepted["run_id"]), owner)
    assert "WAITING_APPROVAL" in "\n".join(str(item["content"]) for item in prepared["messages"])
    _complete(demo_db, owner, prepared, "The Task is waiting for approval; this reply does not approve it.")
    with connect(demo_db) as connection:
        after = {table: [tuple(row) for row in connection.execute(f"SELECT * FROM {table} ORDER BY 1").fetchall()]
                 for table in tracked_tables}
        chat_status = connection.execute("SELECT status FROM task_runs WHERE run_id = ?", (accepted["run_id"],)).fetchone()[0]
    assert before == after
    assert chat_status == "SUCCEEDED"
    assert not (tmp_path / "checkpoint.sqlite3").exists()


def test_task_inspector_includes_successful_domain_observation_status(demo_db: Path) -> None:
    identity = trusted_identity(demo_db, "support-a")
    session_id = str(create_session(demo_db, identity)["session_id"])
    task = create_task_with_initial_run(
        demo_db, identity, session_id=session_id, service_id="orders-demo",
        integration_id="integration-a", ticket_id="INC-A-OBS", initial_message="Investigate 401",
        idempotency_key="inspector-domain-status-task",
    )
    task_id = str(task["task_id"])
    with connect(demo_db) as connection:
        binding = connection.execute("SELECT tenant_id, principal_id FROM task_bindings WHERE task_id = ?", (task_id,)).fetchone()
        current_config = connection.execute(
            "SELECT credential_ref, config_version FROM integrations WHERE tenant_id = ? AND integration_id = 'integration-a'",
            (str(binding["tenant_id"]),),
        ).fetchone()
        now = datetime.now(timezone.utc).isoformat()
        connection.execute(
            """INSERT INTO d2_evidence
               (evidence_id, tenant_id, task_id, call_id, tool_call_id, resource_id, principal_id,
                data_source, fetched_at, observed_versions_json, fact_type, facts_json,
                original_result_ref, trust_class, digest)
               VALUES ('evidence-inspector-config', ?, ?, 'call-inspector', 'tool-inspector',
                           'integration-a', ?, 'sqlite:integrations', ?, ?, 'integration_config',
                       ?, 'observation://observation-inspector', 'untrusted_tool_observation', 'digest-inspector')""",
            (str(binding["tenant_id"]), task_id, str(binding["principal_id"]), now,
             json.dumps({"config_version": int(current_config["config_version"])}),
             json.dumps({"integration_id": "integration-a", "principal_id": str(binding["principal_id"]),
                         "credential_ref": str(current_config["credential_ref"]),
                         "config_version": int(current_config["config_version"])})),
        )
        connection.execute(
            """INSERT INTO d2_tool_observations
               (observation_id, task_id, call_id, tool_call_id, tool_name, argument_digest,
                status, progress_added, result_digest, evidence_id)
               VALUES ('observation-inspector', ?, 'call-inspector', 'tool-inspector',
                       'get_integration_config', 'args-digest', 'OK', 1, 'result-digest',
                       'evidence-inspector-config')""",
            (task_id,),
        )

    inspector = get_task_inspector(demo_db, identity, task_id)

    assert [item["fact_type"] for item in inspector["evidence"]] == ["integration_config"]
    assert inspector["evidence"][0]["facts"]["credential_ref"] == str(current_config["credential_ref"])


def test_streaming_provider_identifier_uses_response_id_or_request_id_header() -> None:
    assert _provider_response_identifier({"id": "chatcmpl-response-1"}) == "chatcmpl-response-1"
    assert _provider_response_identifier({"headers": {"X-Request-ID": "provider-request-2"}}) == "provider-request-2"
    assert _provider_response_identifier({"headers": {"X-DS-Trace-ID": "provider-trace-3"}}) == "provider-trace-3"
    assert _provider_response_identifier({"headers": {"content-type": "text/event-stream"}}) is None


def test_chat_04_revoked_memory_source_excludes_historical_assistant_message(demo_db: Path) -> None:
    identity = trusted_identity(demo_db, "support-a")
    session_id = str(create_session(demo_db, identity)["session_id"])
    task = create_task_with_initial_run(
        demo_db, identity, session_id=session_id, service_id="orders-demo",
        integration_id="integration-a", ticket_id="INC-A-001", initial_message="Investigate 401",
        idempotency_key="memory-source-task",
    )
    owner = _owner(demo_db)
    first = _new_message(demo_db, session_id, "Explain current facts.", key="memory-source-1")
    first_context = _claim_and_prepare(demo_db, str(first["run_id"]), owner)
    first_answer = _complete(demo_db, owner, first_context, "A historical memory suggested checking policy first.")
    with connect(demo_db) as connection:
        connection.execute(
            """INSERT INTO chat_message_sources (message_id, source_kind, source_ref, source_version, source_digest)
               VALUES (?, 'MEMORY', 'episodic-revoked-1', '4', 'old-memory-digest')""",
            (first_answer["message_id"],),
        )
        connection.execute(
            """INSERT INTO d5_memories
               (memory_id, tenant_id, project_id, type, problem_type, summary, applicability_constraints_json,
                source_task_id, source_evidence_ids_json, source_report_ref, source_verification_id,
                state, version, revoked_by, revoked_at, expires_at, created_at)
               VALUES ('episodic-revoked-1', 'tenant-a', 'service:orders-demo', 'EPISODIC', 'auth_401',
                'stale memory text', '{}', ?, '[]', 'report-x', 'verification-x',
                'REVOKED', 5, 'approver-a', CURRENT_TIMESTAMP, '2999-01-01T00:00:00+00:00', CURRENT_TIMESTAMP)"""
            , (task["task_id"],)
        )
    second = _new_message(demo_db, session_id, "Now answer with current context only.", key="memory-source-2")
    second_context = _claim_and_prepare(demo_db, str(second["run_id"]), owner)
    transcript = "\n".join(str(item["content"]) for item in second_context["messages"])
    assert "A historical memory suggested checking policy first" not in transcript
    manifest = get_chat_manifest(demo_db, identity, str(second["run_id"]))
    exclusions = manifest["attempts"][0]["manifest"]["excluded_sources"]
    assert any(item.get("message_id") == first_answer["message_id"] and item["reason"] == "MEMORY_REVOKED_EXPIRED_OR_CHANGED"
               for item in exclusions)


def test_chat_evidence_versions_exclude_pre_repair_probe_and_dependent_answer(
    demo_db: Path, live_api: str,
) -> None:
    identity = trusted_identity(demo_db, "support-a")
    binding = create_task_binding(
        demo_db, "support-a", "orders-demo", "integration-a",
    )
    task_id, session_id = str(binding["task_id"]), str(binding["session_id"])
    facts = [
        ("get_integration_config", get_integration_config_fact(demo_db, task_id, "integration-a")),
        ("get_principal_status", get_principal_status_fact(demo_db, task_id, "principal-a")),
        ("get_auth_policy", get_auth_policy_fact(demo_db, task_id, "orders-demo")),
        ("probe_endpoint", probe_endpoint_fact(demo_db, task_id, "orders-demo", "integration-a", live_api)),
    ]
    evidence_ids: list[str] = []
    for index, (tool_name, fact) in enumerate(facts, 1):
        observation = record_tool_observation(
            demo_db, task_id=task_id, call_id=f"chat-version-call-{index}", attempt_id=None,
            tool_call_id=f"chat-version-tool-{index}", tool_name=tool_name,
            arguments={"index": index}, status="OK", result=fact,
        )
        evidence_ids.append(str(observation["evidence_id"]))
    old_probe = facts[-1][1]
    assert old_probe["facts"]["http_status"] == 401
    assert old_probe["observed_versions"]["before"]["config_version"] == 7
    assert old_probe["observed_versions"]["after"]["config_version"] == 7

    first = _new_message(
        demo_db, session_id, "Explain the current authentication result.",
        key="chat-version-before-repair", task_id=task_id,
    )
    first_context = _claim_and_prepare(demo_db, str(first["run_id"]), _owner(demo_db))
    first_prompt = "\n".join(str(item["content"]) for item in first_context["messages"])
    assert "cred-v1" in first_prompt and '"http_status":401' in first_prompt
    old_answer = _complete(
        demo_db, _owner(demo_db), first_context,
        "The current configuration uses cred-v1 at v7 and the endpoint returned HTTP 401.",
    )

    gate = evaluate_evidence_gate(demo_db, task_id, evidence_ids)
    assert gate["decision"] == "READY"
    plan = create_plan_from_gate(demo_db, task_id, "support-a", gate)
    activate_plan(demo_db, task_id, str(plan["plan_hash"]), "support-a")
    submit_plan_approval(
        demo_db, str(binding["thread_id"]), "approver-a", str(plan["plan_hash"]), "APPROVED",
    )
    intent = get_or_create_action_intent(
        demo_db, task_id, str(plan["plan_hash"]), "REPAIR", "executor-a",
    )
    repair = execute_repair(demo_db, str(intent["action_id"]), "executor-a", "chat-version-repair")
    assert repair["status"] == "COMMITTED"
    assert repair["before_version"] == 7 and repair["after_version"] == 8

    second = _new_message(
        demo_db, session_id, "What does the current evidence establish now?",
        key="chat-version-after-repair", task_id=task_id,
    )
    second_owner = _owner(demo_db, owner_id="chat-version-worker-after-repair")
    second_context = _claim_and_prepare(demo_db, str(second["run_id"]), second_owner)
    second_prompt = "\n".join(str(item["content"]) for item in second_context["messages"])
    assert "cred-v1" not in second_prompt
    assert '"http_status":401' not in second_prompt
    assert "The current configuration uses cred-v1 at v7" not in second_prompt

    manifest = get_chat_manifest(demo_db, identity, str(second["run_id"]))["attempts"][0]["manifest"]
    exclusions = manifest["excluded_sources"]
    stale_evidence = set(evidence_ids[0:1] + evidence_ids[3:4])
    excluded_evidence = {
        str(item.get("source_id")): str(item["reason"])
        for item in exclusions if item.get("source_id") is not None
    }
    assert stale_evidence <= set(excluded_evidence)
    assert all(excluded_evidence[item] == "EVIDENCE_RESOURCE_VERSION_MISMATCH" for item in stale_evidence)
    assert any(
        item.get("message_id") == old_answer["message_id"]
        and item["reason"] == "EVIDENCE_RESOURCE_VERSION_MISMATCH"
        for item in exclusions
    )
    assert not (set(manifest["evidence_refs"][i]["evidence_id"] for i in range(len(manifest["evidence_refs"]))) & stale_evidence)
    with connect(demo_db) as connection:
        assert int(connection.execute(
            "SELECT config_version FROM integrations WHERE tenant_id = 'tenant-a' AND integration_id = 'integration-a'"
        ).fetchone()[0]) == 8
        assert connection.execute(
            "SELECT COUNT(*) FROM d2_evidence WHERE task_id = ? AND evidence_id IN (?, ?)",
            (task_id, evidence_ids[0], evidence_ids[3]),
        ).fetchone()[0] == 2


def test_chat_05_restart_and_retry_persist_partial_chunks_and_commit_one_answer(demo_db: Path) -> None:
    identity = trusted_identity(demo_db, "support-a")
    session_id = str(create_session(demo_db, identity)["session_id"])
    accepted = _new_message(demo_db, session_id, "Answer after a restart.", key="restart-chat")
    owner_a = _owner(demo_db, owner_id="chat-worker-first")
    claim_task_run(demo_db, identity, str(accepted["run_id"]))
    first = prepare_chat_attempt(demo_db, str(accepted["run_id"]), owner_a, "test-model")
    persist_chat_chunk(demo_db, owner_a, str(first["attempt_id"]), 1, "partial before crash")
    owner_b = _owner(demo_db, owner_id="chat-worker-restarted")
    assert recover_running_task_runs(demo_db, owner_b) == [str(accepted["run_id"])]
    with connect(demo_db) as connection:
        recovered = connection.execute("SELECT status, blocked_reason FROM task_runs WHERE run_id = ?", (accepted["run_id"],)).fetchone()
        attempt = connection.execute("SELECT status, error_class FROM chat_attempts WHERE attempt_id = ?", (first["attempt_id"],)).fetchone()
        connection.execute("UPDATE worker_retry_state SET next_attempt_at = '2000-01-01 00:00:00' WHERE run_id = ?", (accepted["run_id"],))
    assert tuple(recovered) == ("INTERRUPTED_RECOVERABLE", "WORKER_OWNER_RESTARTED")
    assert tuple(attempt) == ("INTERRUPTED", "WorkerRestarted")
    queued = __import__("opspilot.domain.task_control", fromlist=["next_worker_run"]).next_worker_run(demo_db)
    assert queued is not None and queued["run_id"] == accepted["run_id"]
    claim_task_run(demo_db, identity, str(accepted["run_id"]))
    second = prepare_chat_attempt(demo_db, str(accepted["run_id"]), owner_b, "test-model")
    _complete(demo_db, owner_b, second, "The recovered run committed one final answer.")
    chunks = get_chat_chunks(demo_db, identity, str(accepted["run_id"]))
    assert len(chunks) == 2 and [item["chunk_seq"] for item in chunks] == [1, 2]
    with connect(demo_db) as connection:
        answer_count = connection.execute("SELECT COUNT(*) FROM chat_run_answers WHERE run_id = ?", (accepted["run_id"],)).fetchone()[0]
        assistant_count = connection.execute(
            "SELECT COUNT(*) FROM messages WHERE session_id = ? AND role = 'ASSISTANT'", (session_id,)
        ).fetchone()[0]
        attempt_statuses = [row[0] for row in connection.execute("SELECT status FROM chat_attempts WHERE run_id = ? ORDER BY attempt_no", (accepted["run_id"],))]
    assert answer_count == assistant_count == 1
    assert attempt_statuses == ["INTERRUPTED", "SUCCEEDED"]


def test_chat_07_http_idempotency_sse_payload_and_cross_tenant_context_denied(demo_db: Path) -> None:
    credentials = {"support-a": "support-password", "approver-a": "approver-password",
                   "support-b": "support-b-password", "approver-b": "approver-b-password"}
    with TestClient(create_app(db_path=demo_db, start_worker=False, credentials=credentials,
                               expected_origin=ORIGIN), raise_server_exceptions=False) as client:
        login = client.post("/api/auth/login", headers={"Origin": ORIGIN},
                            json={"actor_id": "support-a", "password": credentials["support-a"]})
        assert login.status_code == 200
        headers = {"Origin": ORIGIN, "X-CSRF-Token": login.json()["csrf_token"]}
        session_id = client.post("/api/sessions", headers=headers).json()["session_id"]
        message_headers = {**headers, "Idempotency-Key": "chat-http-idempotent"}
        payload = {"input_kind": "CHAT_READONLY", "body": "Inspect the persisted stream."}
        first = client.post(f"/api/sessions/{session_id}/messages", headers=message_headers, json=payload)
        replay = client.post(f"/api/sessions/{session_id}/messages", headers=message_headers, json=payload)
        assert first.status_code == replay.status_code == 202
        assert first.json()["run_id"] == replay.json()["run_id"]
        identity = trusted_identity(demo_db, "support-a")
        worker = _owner(demo_db)
        prepared = _claim_and_prepare(demo_db, first.json()["run_id"], worker)
        _complete(demo_db, worker, prepared, "This text was delivered through a persisted chunk.")
        chunks = client.get(f"/api/runs/{first.json()['run_id']}/chunks")
        context = client.get(f"/api/runs/{first.json()['run_id']}/context")
        events = client.get(f"/api/sessions/{session_id}/events/history")
        assert chunks.status_code == context.status_code == events.status_code == 200
        assert chunks.json()["items"][0]["body"].startswith("This text")
        assert "Inspect the persisted stream." not in json.dumps(context.json())
        assert "messages" not in context.json()["attempts"][0]["manifest"]
        assert all("body" not in item["payload"] and "content" not in item["payload"] for item in events.json()["items"])
        assert any(item["event_kind"] == "CHAT_CHUNK_AVAILABLE" for item in events.json()["items"])
        assert identity.role == "SUPPORT"
        client.post("/api/auth/logout", headers=headers)
        other_login = client.post("/api/auth/login", headers={"Origin": ORIGIN},
                                  json={"actor_id": "support-b", "password": credentials["support-b"]})
        assert other_login.status_code == 200
        denied = client.get(f"/api/runs/{first.json()['run_id']}/context")
        assert denied.status_code == 404


def test_chat_origin_rejects_unlisted_dev_port(demo_db: Path) -> None:
    credentials = {"support-a": "support-password"}
    with TestClient(create_app(db_path=demo_db, start_worker=False, credentials=credentials,
                               expected_origin=ORIGIN), raise_server_exceptions=False) as client:
        response = client.post("/api/auth/login", headers={"Origin": "http://127.0.0.1:5174"},
                               json={"actor_id": "support-a", "password": credentials["support-a"]})
    assert response.status_code == 403 and response.json() == {"code": "ORIGIN_REJECTED"}
