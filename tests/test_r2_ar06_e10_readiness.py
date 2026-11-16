from __future__ import annotations

import hashlib
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

from fastapi.testclient import TestClient


FROZEN_CASE_PATH = Path(__file__).resolve().parents[1] / "docs/evidence/r2-ar06-eval-01/CASES.json"
ORIGIN = "http://127.0.0.1:8000"


def _wait_for_run(client: TestClient, run_id: str) -> dict[str, object]:
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        response = client.get(f"/api/runs/{run_id}")
        assert response.status_code == 200, response.text
        run = response.json()
        if run["status"] in {"SUCCEEDED", "FAILED", "BLOCKED"}:
            return run
        time.sleep(0.05)
    raise AssertionError(f"Run did not finish before test deadline: {run_id}")


def _login(client: TestClient, passwords: dict[str, str], actor_id: str) -> dict[str, str]:
    response = client.post(
        "/api/auth/login", headers={"Origin": ORIGIN},
        json={"actor_id": actor_id, "password": passwords[actor_id]},
    )
    assert response.status_code == 200, response.text
    return {"Origin": ORIGIN, "X-CSRF-Token": response.json()["csrf_token"]}


def _seed_project_approver(db_path: Path) -> None:
    from opspilot.domain.database import connect

    with connect(db_path) as connection:
        connection.execute(
            """INSERT OR IGNORE INTO semantic_memory_project_approvers
               (tenant_id, project_id, actor_id, active, granted_by, granted_at)
               VALUES ('tenant-a', 'service:orders-async-demo', 'approver-a', 1,
                       'fixture:e10-trusted-approver', CURRENT_TIMESTAMP)"""
        )


def _create_confirmed_memory(
    client: TestClient,
    passwords: dict[str, str],
    support_headers: dict[str, str],
    *,
    suffix: str,
    content: str,
    memory_key: str,
    order_id: str,
) -> tuple[dict[str, object], dict[str, str]]:
    """Create source Task/Session, candidate and confirmation through existing API routes."""
    session_response = client.post("/api/sessions", headers=support_headers)
    assert session_response.status_code == 201, session_response.text
    source_session_id = session_response.json()["session_id"]
    accepted = client.post(
        f"/api/sessions/{source_session_id}/assistant/order",
        headers={**support_headers, "Idempotency-Key": f"e10-source-{suffix}"},
        json={"order_id": order_id, "initial_message": content},
    )
    assert accepted.status_code == 202, accepted.text
    source = accepted.json()
    assert _wait_for_run(client, str(source["run_id"]))["status"] == "SUCCEEDED"

    candidate = client.post(
        f"/api/tasks/{source['task_id']}/semantic-memories/candidates",
        headers={**support_headers, "Idempotency-Key": f"e10-candidate-{suffix}"},
        json={
            "memory_kind": "INTERFACE_CONVENTION",
            "memory_key": memory_key,
            "content": content,
            "source_message_id": source["message_id"],
            "ttl_days": 90,
        },
    )
    assert candidate.status_code == 201, candidate.text
    candidate_item = candidate.json()
    approver_headers = _login(client, passwords, "approver-a")
    confirmed = client.post(
        f"/api/semantic-memories/{candidate_item['memory_id']}/confirm",
        headers={**approver_headers, "Idempotency-Key": f"e10-confirm-{suffix}"},
        json={},
    )
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["state"] == "ACTIVE"
    memory = {
        **candidate_item,
        **confirmed.json(),
        "source_session_id": source_session_id,
        "source_task_id": source["task_id"],
        "source_run_id": source["run_id"],
        "source_message_id": source["message_id"],
    }
    return memory, _login(client, passwords, "support-a")


def _submit_target(
    client: TestClient,
    support_headers: dict[str, str],
    *,
    case_input: str,
    idempotency_key: str,
    order_id: str,
) -> tuple[dict[str, object], str, str]:
    session_response = client.post("/api/sessions", headers=support_headers)
    assert session_response.status_code == 201, session_response.text
    session_id = session_response.json()["session_id"]
    accepted = client.post(
        f"/api/sessions/{session_id}/assistant/order",
        headers={**support_headers, "Idempotency-Key": idempotency_key},
        json={"order_id": order_id, "initial_message": case_input},
    )
    assert accepted.status_code == 202, accepted.text
    run_item = accepted.json()
    result = _wait_for_run(client, str(run_item["run_id"]))
    assert result["status"] == "SUCCEEDED", result
    messages = client.get(f"/api/sessions/{session_id}/messages").json()["items"]
    answer = next(item for item in messages if item["role"] == "ASSISTANT")
    return run_item, session_id, str(answer["body"])


def _parse_json(value: object) -> object:
    if value is None:
        return None
    if isinstance(value, bytes):
        value = value.decode("utf-8", errors="replace")
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
    return value


def _message_text(wire: dict[str, object]) -> str:
    messages = wire.get("messages", [])
    return "\n".join(
        str((message.get("data") or {}).get("content", message.get("content", "")))
        for message in messages
        if isinstance(message, dict)
    )


def _collect_run_records(db_path: Path, run_ids: list[str]) -> dict[str, object]:
    from opspilot.domain.database import connect

    placeholders = ",".join("?" for _ in run_ids)
    with connect(db_path) as connection:
        runs = [dict(row) for row in connection.execute(
            f"SELECT run_id,tenant_id,task_id,session_id,kind,status,created_at,started_at,ended_at "
            f"FROM task_runs WHERE run_id IN ({placeholders}) ORDER BY created_at", run_ids,
        ).fetchall()]
        task_ids = sorted({str(item["task_id"]) for item in runs if item["task_id"]})
        task_placeholders = ",".join("?" for _ in task_ids)
        bindings = [dict(row) for row in connection.execute(
            f"SELECT task_id,tenant_id,actor_id,service_id,integration_id,principal_id,ticket_id,status,created_at "
            f"FROM task_bindings WHERE task_id IN ({task_placeholders}) ORDER BY created_at", task_ids,
        ).fetchall()] if task_ids else []
        session_ids = sorted({str(item["session_id"]) for item in runs})
        session_placeholders = ",".join("?" for _ in session_ids)
        sessions = [dict(row) for row in connection.execute(
            f"SELECT session_id,tenant_id,owner_id,created_at,updated_at FROM sessions "
            f"WHERE session_id IN ({session_placeholders}) ORDER BY created_at", session_ids,
        ).fetchall()] if session_ids else []
        calls = [dict(row) for row in connection.execute(
            f"SELECT call_id,run_id,kind,logical_key,request_json,status,result_json,usage_json,"
            f"observation_id,evidence_id,created_at,completed_at FROM assistant_calls "
            f"WHERE run_id IN ({placeholders}) ORDER BY created_at,call_id", run_ids,
        ).fetchall()]
        attempts = [dict(row) for row in connection.execute(
            f"SELECT attempt_id,run_id,attempt_no,model_id,status,"
            f"provider_response_id AS fixture_framework_trace_id,"
            f"input_tokens,output_tokens,total_tokens,error_class,created_at,completed_at "
            f"FROM chat_attempts WHERE run_id IN ({placeholders}) ORDER BY created_at,attempt_no", run_ids,
        ).fetchall()]
        manifests = [dict(row) for row in connection.execute(
            f"SELECT manifest_id,attempt_id,run_id,tenant_id,session_id,task_id,"
            f"selected_message_ids_json,evidence_refs_json,memory_refs_json,model_call_refs_json,"
            f"excluded_sources_json,truncation_json,trusted_state_digest,prompt_digest,created_at "
            f"FROM chat_context_manifests WHERE run_id IN ({placeholders}) ORDER BY created_at", run_ids,
        ).fetchall()]
        messages = [dict(row) for row in connection.execute(
            f"SELECT message_id,tenant_id,session_id,task_id,sequence,role,input_kind,body,body_digest,created_at "
            f"FROM messages WHERE session_id IN (SELECT session_id FROM task_runs WHERE run_id IN ({placeholders})) "
            f"ORDER BY session_id,sequence", run_ids,
        ).fetchall()]
        semantic_rows = [dict(row) for row in connection.execute(
            "SELECT * FROM semantic_memories ORDER BY created_at,memory_id"
        ).fetchall()]
        semantic_events = [dict(row) for row in connection.execute(
            "SELECT * FROM semantic_memory_events ORDER BY occurred_at,event_id"
        ).fetchall()]
        grants = {
            "runtime_default_grant_rows": int(connection.execute(
                "SELECT COUNT(*) FROM assistant_runtime_default_grant"
            ).fetchone()[0]),
            "runtime_spend_rows": int(connection.execute(
                "SELECT COUNT(*) FROM assistant_runtime_spends"
            ).fetchone()[0]),
        }
        protected_writes = {
            table: int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
            for table in ("s3_diagnoses", "d3_action_intents", "d3_action_ledgers", "s3_handoff_receipts")
        }

    for row in calls:
        row["request"] = _parse_json(row.pop("request_json"))
        row["result"] = _parse_json(row.pop("result_json"))
        row["usage"] = _parse_json(row.pop("usage_json"))
    for row in manifests:
        for key in ("selected_message_ids_json", "evidence_refs_json", "memory_refs_json",
                    "model_call_refs_json", "excluded_sources_json", "truncation_json"):
            row[key.removesuffix("_json")] = _parse_json(row.pop(key))
    for row in semantic_rows:
        row["source_refs"] = _parse_json(row.pop("source_refs_json"))
    for row in semantic_events:
        row["details"] = _parse_json(row.pop("details_json"))
    return {
        "runs": runs,
        "task_bindings": bindings,
        "sessions": sessions,
        "assistant_calls": calls,
        "chat_attempts": attempts,
        "context_manifests": manifests,
        "messages": messages,
        "semantic_memories": semantic_rows,
        "semantic_memory_events": semantic_events,
        "grant_and_spend_counts": grants,
        "protected_business_write_counts": protected_writes,
    }


def _write_evidence(directory: Path, files: dict[str, object]) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    for name, payload in files.items():
        (directory / name).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )


def test_e10_two_memory_conflict_formal_assistant_journey_and_offline_evidence(
    demo_db: Path, tmp_path: Path, monkeypatch,
) -> None:
    """Exercise formal candidate/confirm/revoke, target Session, MCP and actual model wires."""
    from opspilot.domain.database import connect
    from opspilot.domain.s3 import prepare_s3_fixture
    from opspilot.web.app import create_app
    import opspilot.domain.chat as chat_domain
    from test_ar02_assistant import PASSWORDS
    from test_ar02_journey_p0 import JourneyFixtureModel
    from test_ar04b_memory_journey_01 import MemoryWireFixtureModel

    case_data = json.loads(FROZEN_CASE_PATH.read_text(encoding="utf-8"))
    case = next(item for item in case_data["cases"] if item["case_id"] == "E10-H")
    case_input = case["user_turns"][0]
    assert case_input == (
        "New Session: use any still-valid cross-session method memory only as guidance, "
        "check it against current evidence, and ignore/reject an older conflicting memory after it is revoked."
    )
    gold_input_sha256 = hashlib.sha256(case_input.encode("utf-8")).hexdigest()

    runtime_name = os.environ.get("OPSPILOT_E10_RUNTIME_NAME", "").strip()
    if runtime_name:
        # Final evidence may target a fresh named User Demo Runtime. Never reuse or reset it.
        import sys

        repository = Path(__file__).resolve().parents[1]
        user_demo_dir = repository / "scripts" / "user-demo"
        if str(user_demo_dir) not in sys.path:
            sys.path.insert(0, str(user_demo_dir))
        from initialize_demo import initialize_user_demo
        from runtime_paths import resolve_user_demo_runtime

        runtime_dir = resolve_user_demo_runtime(runtime_name, root=repository)
        if runtime_dir.exists():
            raise AssertionError(f"Refusing to reuse an existing E10 runtime: {runtime_name}")
        initialize_user_demo(
            runtime_dir, require_absent_directory=True, s3_fixture_profile="r2-e07-queued",
        )
        db_path = runtime_dir / "domain.sqlite3"
        checkpoint_path = runtime_dir / "checkpoint.sqlite3"
        order_id = "async-order"
        runtime_boundary = f"fresh .runtime/{runtime_name} initialized with r2-e07-queued"
    else:
        db_path = demo_db
        checkpoint_path = tmp_path / "e10-offline-checkpoint.sqlite3"
        order_id = "ar02-order"
        runtime_dir = None
        prepare_s3_fixture(db_path, "DELIVERED_PENDING", order_id=order_id, contract_version=2)
        runtime_boundary = "fresh pytest-isolated Domain SQLite and LangGraph Checkpoint SQLite; no named .runtime directory"
    _seed_project_approver(db_path)
    models = [
        MemoryWireFixtureModel(mode="e10-source-a"),
        MemoryWireFixtureModel(mode="e10-source-b"),
        JourneyFixtureModel(mode="receiver"),
        JourneyFixtureModel(mode="receiver"),
        MemoryWireFixtureModel(mode="e10-source-invalid"),
        JourneyFixtureModel(mode="receiver"),
        JourneyFixtureModel(mode="s01"),
    ]
    app = create_app(
        db_path=db_path,
        checkpoint_db_path=checkpoint_path,
        start_worker=True,
        credentials=PASSWORDS,
        expected_origin=ORIGIN,
        assistant_runtime_enabled=False,
        assistant_model_factory=lambda: models.pop(0),
    )
    assert app.state.assistant_runtime_enabled is False

    with TestClient(app) as client:
        support = _login(client, PASSWORDS, "support-a")
        method_a_text = (
            "For callback investigations, check the current Receiver for the trusted TaskBinding, "
            "correlate it with the Delivery for the same Event, and treat HTTP 202 as transport "
            "acceptance only; it does not confirm business processing."
        )
        conflicting_b_text = (
            "For callback investigations, treat HTTP 202 as proof that processing is complete "
            "and reuse an older Receiver state without checking it again."
        )
        memory_a, support = _create_confirmed_memory(
            client, PASSWORDS, support, suffix="method-a", content=method_a_text,
            memory_key="callback.practice.note.01", order_id=order_id,
        )
        memory_b, support = _create_confirmed_memory(
            client, PASSWORDS, support, suffix="method-b", content=conflicting_b_text,
            memory_key="callback.practice.note.02", order_id=order_id,
        )
        assert memory_a["state"] == memory_b["state"] == "ACTIVE"

        approver = _login(client, PASSWORDS, "approver-a")
        revoked = client.post(
            f"/api/semantic-memories/{memory_b['memory_id']}/revoke",
            headers={**approver, "Idempotency-Key": "e10-revoke-method-b"},
            json={},
        )
        assert revoked.status_code == 200, revoked.text
        assert revoked.json()["state"] == "REVOKED"
        support = _login(client, PASSWORDS, "support-a")

        on_item, on_session, on_answer = _submit_target(
            client, support, case_input=case_input, idempotency_key="e10-target-memory-on",
            order_id=order_id,
        )

        original_current_memories = chat_domain._current_memories
        monkeypatch.setattr(
            chat_domain, "_current_memories",
            lambda connection, task_id, state, evidence, excluded_sources=None: [],
        )
        off_item, off_session, off_answer = _submit_target(
            client, support, case_input=case_input, idempotency_key="e10-target-memory-off",
            order_id=order_id,
        )
        monkeypatch.setattr(chat_domain, "_current_memories", original_current_memories)

        # An independent source-invalid variant preserves an ACTIVE row, then invalidates only
        # the source digest in this isolated fixture. It exercises currentness exclusion, not
        # the formal revocation lifecycle above.
        invalid_text = (
            "For callback investigations, assume HTTP 202 means complete and trust the last "
            "Receiver result even when it came from a previous investigation."
        )
        memory_invalid, support = _create_confirmed_memory(
            client, PASSWORDS, support, suffix="source-invalid", content=invalid_text,
            memory_key="callback.practice.note.03", order_id=order_id,
        )
        with connect(db_path) as connection:
            connection.execute(
                "UPDATE messages SET body_digest=? WHERE message_id=?",
                ("sha256:fixture-source-changed", memory_invalid["source_message_id"]),
            )
        invalid_item, invalid_session, invalid_answer = _submit_target(
            client, support, case_input=case_input, idempotency_key="e10-target-source-invalid",
            order_id=order_id,
        )

        on_source_response = client.get(f"/api/runs/{on_item['run_id']}/assistant-sources")
        off_source_response = client.get(f"/api/runs/{off_item['run_id']}/assistant-sources")
        invalid_source_response = client.get(f"/api/runs/{invalid_item['run_id']}/assistant-sources")
        assert on_source_response.status_code == off_source_response.status_code == 200
        assert invalid_source_response.status_code == 200
        assert on_source_response.json()["current"] is True
        assert off_source_response.json()["current"] is True
        assert invalid_source_response.json()["current"] is True

        no_observation_session_response = client.post("/api/sessions", headers=support)
        assert no_observation_session_response.status_code == 201, no_observation_session_response.text
        no_observation_session = no_observation_session_response.json()["session_id"]
        no_observation_accepted = client.post(
            f"/api/sessions/{no_observation_session}/assistant/messages",
            headers={**support, "Idempotency-Key": "e10-no-memory-no-observation"},
            json={"input_kind": "CHAT_READONLY", "body": case_input},
        )
        assert no_observation_accepted.status_code == 202, no_observation_accepted.text
        no_observation_item = no_observation_accepted.json()
        no_observation_run = _wait_for_run(client, str(no_observation_item["run_id"]))
        assert no_observation_run["status"] == "SUCCEEDED", no_observation_run
        no_observation_messages = client.get(
            f"/api/sessions/{no_observation_session}/messages"
        ).json()["items"]
        no_observation_answer = str(next(
            item for item in no_observation_messages if item["role"] == "ASSISTANT"
        )["body"])

    assert not models
    for answer in (on_answer, off_answer, invalid_answer):
        assert "QUEUED" in answer
        assert "尚不能称为处理完成" in answer

    collected = _collect_run_records(
        db_path,
        [
            str(memory_a["source_run_id"]), str(memory_b["source_run_id"]), str(on_item["run_id"]),
            str(off_item["run_id"]), str(memory_invalid["source_run_id"]), str(invalid_item["run_id"]),
        str(no_observation_item["run_id"]),
        ],
    )
    memories_by_id = {str(item["memory_id"]): item for item in collected["semantic_memories"]}
    lifecycle: dict[str, list[dict[str, object]]] = {}
    for event in collected["semantic_memory_events"]:
        lifecycle.setdefault(str(event["memory_id"]), []).append(event)
    manifests_by_run: dict[str, list[dict[str, object]]] = {}
    for manifest in collected["context_manifests"]:
        manifests_by_run.setdefault(str(manifest["run_id"]), []).append(manifest)

    on_manifests = manifests_by_run[str(on_item["run_id"])]
    off_manifests = manifests_by_run[str(off_item["run_id"])]
    invalid_manifests = manifests_by_run[str(invalid_item["run_id"])]
    no_observation_manifests = manifests_by_run[str(no_observation_item["run_id"])]
    assert on_manifests and off_manifests and invalid_manifests
    assert no_observation_manifests
    assert all([item["memory_id"] for item in manifest["memory_refs"]] == [memory_a["memory_id"]]
               for manifest in on_manifests)
    assert all(manifest["memory_refs"] == [] for manifest in off_manifests)
    assert all([item["memory_id"] for item in manifest["memory_refs"]] == [memory_a["memory_id"]]
               for manifest in invalid_manifests)
    assert all(manifest["memory_refs"] == [] for manifest in no_observation_manifests)
    assert all(manifest["task_id"] is None for manifest in no_observation_manifests)
    assert any(
        item.get("source_id") == memory_b["memory_id"] and item.get("reason") == "SEMANTIC_MEMORY_REVOKED"
        for manifest in on_manifests for item in manifest["excluded_sources"]
    )
    assert any(
        item.get("source_id") == memory_invalid["memory_id"]
        and item.get("reason") == "SEMANTIC_MEMORY_SOURCE_INVALID"
        for manifest in invalid_manifests for item in manifest["excluded_sources"]
    )
    assert [event["event_type"] for event in lifecycle[str(memory_b["memory_id"])]] == [
        "CANDIDATE_CREATED", "CONFIRMED", "REVOKED",
    ]
    assert lifecycle[str(memory_b["memory_id"])][-1]["memory_version"] == 2

    def run_calls(run_id: str, kind: str) -> list[dict[str, object]]:
        return [item for item in collected["assistant_calls"]
                if item["run_id"] == run_id and item["kind"] == kind]

    on_model_calls = run_calls(str(on_item["run_id"]), "MODEL")
    off_model_calls = run_calls(str(off_item["run_id"]), "MODEL")
    invalid_model_calls = run_calls(str(invalid_item["run_id"]), "MODEL")
    no_observation_model_calls = run_calls(str(no_observation_item["run_id"]), "MODEL")
    on_mcp_calls = run_calls(str(on_item["run_id"]), "MCP")
    off_mcp_calls = run_calls(str(off_item["run_id"]), "MCP")
    invalid_mcp_calls = run_calls(str(invalid_item["run_id"]), "MCP")
    no_observation_mcp_calls = run_calls(str(no_observation_item["run_id"]), "MCP")
    assert len(no_observation_model_calls) == 1
    assert no_observation_mcp_calls == []
    assert {json.loads(json.dumps(item["request"]))["name"] for item in on_mcp_calls} == {
        "get_callback_delivery", "get_receiver_processing",
    }
    assert {json.loads(json.dumps(item["request"]))["name"] for item in off_mcp_calls} == {
        "get_callback_delivery", "get_receiver_processing",
    }
    assert {json.loads(json.dumps(item["request"]))["name"] for item in invalid_mcp_calls} == {
        "get_callback_delivery", "get_receiver_processing",
    }
    on_tool_schemas = [item["request"].get("tools", []) for item in on_model_calls]
    off_tool_schemas = [item["request"].get("tools", []) for item in off_model_calls]
    assert on_tool_schemas == off_tool_schemas

    on_wire_text = "\n".join(_message_text(item["request"]) for item in on_model_calls)
    off_wire_text = "\n".join(_message_text(item["request"]) for item in off_model_calls)
    invalid_wire_text = "\n".join(_message_text(item["request"]) for item in invalid_model_calls)
    no_observation_wire_text = "\n".join(_message_text(item["request"]) for item in no_observation_model_calls)
    assert str(memory_a["memory_id"]) in on_wire_text
    assert method_a_text in on_wire_text
    assert "CONFIRMED_SEMANTIC_PROJECT_CONTEXT_NOT_FACT" in on_wire_text
    assert str(memory_b["memory_id"]) not in on_wire_text
    assert conflicting_b_text not in on_wire_text
    assert str(memory_a["memory_id"]) not in off_wire_text
    assert method_a_text not in off_wire_text
    assert str(memory_b["memory_id"]) not in off_wire_text
    assert str(memory_a["memory_id"]) in invalid_wire_text
    assert str(memory_invalid["memory_id"]) not in invalid_wire_text
    assert invalid_text not in invalid_wire_text
    assert str(memory_a["memory_id"]) not in no_observation_wire_text
    assert str(memory_b["memory_id"]) not in no_observation_wire_text
    assert str(memory_invalid["memory_id"]) not in no_observation_wire_text
    assert "未知" in no_observation_answer
    for evaluation_label in (
        "METHOD_MEMORY_VALID", "METHOD_MEMORY_REVOKED_CONFLICT", "METHOD_MEMORY_SOURCE_INVALID_CONFLICT",
        "POST_FREEZE_FIXTURE_SPECIFIED", "expected_answer", "gold_status",
    ):
        assert evaluation_label not in on_wire_text + off_wire_text + invalid_wire_text + no_observation_wire_text

    def mcp_projection(calls: list[dict[str, object]]) -> list[dict[str, object]]:
        return [{
            "name": item["request"]["name"],
            "result": item["result"],
            "observation_id": item["observation_id"],
            "evidence_id": item["evidence_id"],
        } for item in calls]

    on_facts = mcp_projection(on_mcp_calls)
    off_facts = mcp_projection(off_mcp_calls)
    invalid_facts = mcp_projection(invalid_mcp_calls)
    for facts in (on_facts, off_facts, invalid_facts):
        assert all(item["observation_id"] and item["evidence_id"] for item in facts)
    on_tool_names = [item["name"] for item in on_facts]
    off_tool_names = [item["name"] for item in off_facts]
    assert on_tool_names == off_tool_names

    def observation_identity(facts: list[dict[str, object]], task_id: str) -> dict[str, object]:
        by_name = {str(item["name"]): item for item in facts}
        delivery = by_name["get_callback_delivery"]["result"]
        receiver = by_name["get_receiver_processing"]["result"]
        assert isinstance(delivery, dict) and isinstance(receiver, dict)
        delivery_facts, receiver_facts = delivery["facts"], receiver["facts"]
        assert delivery_facts["event_id"] == receiver_facts["event_id"]
        assert delivery["task_id"] == receiver["task_id"] == task_id
        assert delivery_facts["service_id"] == receiver_facts["service_id"] == "orders-async-demo"
        assert delivery_facts["order_id"] == receiver_facts["order_id"] == order_id
        assert receiver_facts["status"] == "QUEUED"
        assert delivery_facts["status"] == "ACKNOWLEDGED"
        assert delivery_facts["receiver_http_status"] == 202
        return {
            "event_id": delivery_facts["event_id"],
            "service_id": delivery_facts["service_id"],
            "order_id": delivery_facts["order_id"],
            "delivery_status": delivery_facts["status"],
            "receiver_http_status": delivery_facts["receiver_http_status"],
            "receiver_status": receiver_facts["status"],
            "delivery_task_id": delivery["task_id"],
            "receiver_task_id": receiver["task_id"],
        }

    on_observation = observation_identity(on_facts, str(on_item["task_id"]))
    off_observation = observation_identity(off_facts, str(off_item["task_id"]))
    invalid_observation = observation_identity(invalid_facts, str(invalid_item["task_id"]))
    assert {key: value for key, value in on_observation.items() if key not in {"delivery_task_id", "receiver_task_id"}} == {
        key: value for key, value in off_observation.items() if key not in {"delivery_task_id", "receiver_task_id"}
    }
    assert {key: value for key, value in on_observation.items() if key not in {"delivery_task_id", "receiver_task_id"}} == {
        key: value for key, value in invalid_observation.items() if key not in {"delivery_task_id", "receiver_task_id"}
    }
    # The fixture model emits the same useful current-state response in the ON/OFF arms;
    # this is integration evidence only, not a semantic quality comparison.
    assert on_answer == off_answer

    def guidance_tokens(manifests: list[dict[str, object]]) -> list[int]:
        result: list[int] = []
        for manifest in manifests:
            truncation = manifest["truncation"]
            blocks = truncation.get("context_blocks", []) if isinstance(truncation, dict) else []
            result.append(sum(
                int(item.get("estimated_tokens", 0))
                for item in blocks if item.get("category") == "EXTERNAL_GUIDANCE"
            ))
        return result

    def fixture_usage(calls: list[dict[str, object]]) -> dict[str, int]:
        totals = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
        for call in calls:
            if call["kind"] != "MODEL" or not isinstance(call["usage"], list):
                continue
            for usage in call["usage"]:
                if not isinstance(usage, dict):
                    continue
                for key in totals:
                    totals[key] += int(usage.get(key, 0) or 0)
        return totals

    assert all(run["status"] == "SUCCEEDED" for run in collected["runs"])
    assert collected["grant_and_spend_counts"] == {"runtime_default_grant_rows": 0, "runtime_spend_rows": 0}
    assert collected["protected_business_write_counts"] == {
        "s3_diagnoses": 0, "d3_action_intents": 0, "d3_action_ledgers": 0, "s3_handoff_receipts": 0,
    }

    if evidence_dir := os.environ.get("OPSPILOT_E10_EVIDENCE_DIR"):
        evidence = Path(evidence_dir)
        all_target_wires = {
            "ON": [item["request"] for item in on_model_calls],
            "OFF": [item["request"] for item in off_model_calls],
            "SOURCE_INVALID_VARIANT": [item["request"] for item in invalid_model_calls],
            "NO_MEMORY_NO_OBSERVATION": [item["request"] for item in no_observation_model_calls],
        }
        label_map = {
            str(memory_a["memory_id"]): "METHOD_MEMORY_VALID",
            str(memory_b["memory_id"]): "METHOD_MEMORY_REVOKED_CONFLICT",
            str(memory_invalid["memory_id"]): "METHOD_MEMORY_SOURCE_INVALID_CONFLICT",
        }
        memory_a_row = memories_by_id[str(memory_a["memory_id"])]
        memory_b_row = memories_by_id[str(memory_b["memory_id"])]
        memory_invalid_row = memories_by_id[str(memory_invalid["memory_id"])]
        lifecycle_audit = {
            "evidence_level": "ISOLATED_FORMAL_API_WORKER_FIXTURE_MCP_DOMAIN",
            "memory_types": "SEMANTIC_PROJECT_CONTEXT_NOT_PERSONAL_MEMORY",
            "scope": {"tenant_id": "tenant-a", "project_id": "service:orders-async-demo", "recall_owner": None},
            "evaluation_labels_not_model_visible": label_map,
            "records": [memory_a_row, memory_b_row, memory_invalid_row],
            "effective_currentness": {
                str(memory_a["memory_id"]): {"current": True, "reason": "ACTIVE_SOURCE_AND_SCOPE_VALID"},
                str(memory_b["memory_id"]): {"current": False, "reason": "SEMANTIC_MEMORY_REVOKED"},
                str(memory_invalid["memory_id"]): {"current": False, "reason": "SEMANTIC_MEMORY_SOURCE_INVALID"},
            },
            "events": [item for item in collected["semantic_memory_events"]
                       if item["memory_id"] in label_map],
            "source_message_ids": {
                str(memory_a["memory_id"]): memory_a["source_message_id"],
                str(memory_b["memory_id"]): memory_b["source_message_id"],
                str(memory_invalid["memory_id"]): memory_invalid["source_message_id"],
            },
            "source_invalid_variant": {
                "memory_id": memory_invalid["memory_id"], "database_fixture_mutation": "source message body_digest changed after confirmation",
                "row_state_remains": "ACTIVE", "selection_exclusion": "SEMANTIC_MEMORY_SOURCE_INVALID",
            },
        }
        manifest = {
            "case_id": "E10-H",
            "fixture_specification": "POST_FREEZE_FIXTURE_SPECIFIED",
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "gold_modified": False,
            "gold_rubric_protocol_modified": False,
            "label_names_are_evidence_only": True,
            "input_sha256": gold_input_sha256,
            "fixture_data": "Synthetic callback records in an isolated Domain/Checkpoint runtime; no E09 or user Demo database imported.",
            "runtime_boundary": runtime_boundary,
            "runtime_name": runtime_name or None,
            "checkpoint_exists_after_run": checkpoint_path.is_file(),
            "model_visible_project_scope": "orders-async-demo",
            "target_order_id": order_id,
            "target_profile": "DELIVERED_PENDING / ACKNOWLEDGED HTTP 202 / Receiver QUEUED",
            "source_sessions": [memory_a["source_session_id"], memory_b["source_session_id"], memory_invalid["source_session_id"]],
            "target_sessions": {"ON": on_session, "OFF": off_session, "SOURCE_INVALID_VARIANT": invalid_session,
                                "NO_MEMORY_NO_OBSERVATION": no_observation_session},
            "fixture_memory_labels": label_map,
            "assistant_runtime_enabled": False,
            "runtime_grant_created": False,
            "provider_requests": 0,
            "fixture_model_calls": sum(1 for item in collected["assistant_calls"] if item["kind"] == "MODEL"),
            "fixture_mcp_calls": sum(1 for item in collected["assistant_calls"] if item["kind"] == "MCP"),
            "fixture_usage": fixture_usage(collected["assistant_calls"]),
            "application_spend_usd": 0,
            "database_sha256": hashlib.sha256(db_path.read_bytes()).hexdigest(),
        }
        model_input_audit = {
            "actual_model_wires_by_arm": all_target_wires,
            "selected_memory_refs": {
                str(on_item["run_id"]): on_manifests[0]["memory_refs"],
                str(off_item["run_id"]): off_manifests[0]["memory_refs"],
                str(invalid_item["run_id"]): invalid_manifests[0]["memory_refs"],
                str(no_observation_item["run_id"]): no_observation_manifests[0]["memory_refs"],
            },
            "excluded_sources": {
                "ON": [item for manifest_item in on_manifests for item in manifest_item["excluded_sources"]],
                "OFF": [item for manifest_item in off_manifests for item in manifest_item["excluded_sources"]],
                "SOURCE_INVALID_VARIANT": [item for manifest_item in invalid_manifests for item in manifest_item["excluded_sources"]],
            "NO_MEMORY_NO_OBSERVATION": [item for manifest_item in no_observation_manifests for item in manifest_item["excluded_sources"]],
            },
            "revoked_b_text_or_id_in_target_wires": False,
            "source_invalid_text_or_id_in_target_wires": False,
            "evaluation_labels_in_target_wires": False,
            "no_memory_no_observation_control": {
                "task_binding": None,
                "selected_memory_refs": no_observation_manifests[0]["memory_refs"],
                "mcp_calls": len(no_observation_mcp_calls),
                "answer_explicitly_unknown": "未知" in no_observation_answer,
                "fixture_answer": no_observation_answer,
            },
            "current_observation_is_distinct_from_memory": True,
            "fixture_limitation": "The Fixture Model follows a predetermined receiver investigation policy; this proves data flow and scoped observations, not real-model autonomy or semantic benefit.",
        }
        trace = {
            "evidence_level": "ISOLATED_FORMAL_API_WORKER_FIXTURE_MODEL_LOCAL_MCP_DOMAIN",
            "case_input": case_input,
            "gold_input_sha256": gold_input_sha256,
            "source_and_target_ids": {
                "memory_a": {key: memory_a[key] for key in ("memory_id", "version", "content_digest", "source_session_id", "source_task_id", "source_run_id", "source_message_id")},
                "memory_b": {key: memory_b[key] for key in ("memory_id", "version", "content_digest", "source_session_id", "source_task_id", "source_run_id", "source_message_id")},
                "memory_source_invalid": {key: memory_invalid[key] for key in ("memory_id", "version", "content_digest", "source_session_id", "source_task_id", "source_run_id", "source_message_id")},
                "target_runs": {"ON": on_item, "OFF": off_item, "SOURCE_INVALID_VARIANT": invalid_item},
                "no_memory_no_observation_run": no_observation_item,
            },
            "target_answers": {"ON": on_answer, "OFF": off_answer, "SOURCE_INVALID_VARIANT": invalid_answer,
                               "NO_MEMORY_NO_OBSERVATION": no_observation_answer},
            "run_records": collected["runs"],
            "chat_attempts_with_fixture_usage": collected["chat_attempts"],
            "session_records": collected["sessions"],
            "trusted_task_bindings": collected["task_bindings"],
            "calls_and_observations": collected["assistant_calls"],
            "context_manifests": collected["context_manifests"],
            "source_messages_and_answers": collected["messages"],
            "assistant_sources_api": {
                "ON": on_source_response.json(),
                "OFF": off_source_response.json(),
                "SOURCE_INVALID_VARIANT": invalid_source_response.json(),
            },
            "grant_and_spend_counts": collected["grant_and_spend_counts"],
            "protected_business_write_counts": collected["protected_business_write_counts"],
        }
        on_off = {
            "evidence_level": "FIXTURE_INTEGRATION_COMPARISON_ONLY",
            "memory_selection_only_test_override": "ON uses existing selection; OFF monkeypatches only chat._current_memories for this isolated test.",
            "same_frozen_input": True,
            "same_synthetic_order_profile": True,
            "same_tool_schemas": on_tool_schemas == off_tool_schemas,
            "same_mcp_tool_names": on_tool_names == off_tool_names,
            "same_observation_facts": {
                "ON": on_observation,
                "OFF": off_observation,
                "same_business_fact_projection": {
                    key: value for key, value in on_observation.items()
                    if key not in {"delivery_task_id", "receiver_task_id"}
                } == {
                    key: value for key, value in off_observation.items()
                    if key not in {"delivery_task_id", "receiver_task_id"}
                },
            },
            "ON_selected_memory_ids": [item["memory_id"] for item in on_manifests[0]["memory_refs"]],
            "OFF_selected_memory_ids": [item["memory_id"] for item in off_manifests[0]["memory_refs"]],
            "ON_memory_context_tokens": guidance_tokens(on_manifests),
            "OFF_memory_context_tokens": guidance_tokens(off_manifests),
            "fixture_usage_ON": fixture_usage(on_model_calls),
            "fixture_usage_OFF": fixture_usage(off_model_calls),
            "fixture_answers_equal": on_answer == off_answer,
            "quality_or_autonomy_effect_conclusion": "NOT_MEASURED_FIXTURE_MODEL",
            "causal_comparison_limit": "Runs have distinct Session/Task/Run IDs; this checks wiring under matched fixture profile, not a controlled real-model quality experiment.",
        }
        _write_evidence(evidence, {
            "E10_MEMORY_FIXTURE_MANIFEST.json": manifest,
            "E10_MEMORY_LIFECYCLE_AUDIT.json": lifecycle_audit,
            "E10_OFFLINE_TRACE.json": trace,
            "E10_MODEL_INPUT_AUDIT.json": model_input_audit,
            "E10_ON_OFF_COMPARISON.json": on_off,
        })
