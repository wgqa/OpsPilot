from __future__ import annotations

import json
import time
from pathlib import Path

from fastapi.testclient import TestClient
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import Field


class MemoryWireFixtureModel(BaseChatModel):
    """Offline model double that records the actual messages passed by ASSISTANT_V1."""

    mode: str
    seen: list = Field(default_factory=list)

    @property
    def _llm_type(self) -> str:
        return "AR04B_MEMORY_WIRE_FIXTURE"

    def bind_tools(self, tools, **kwargs):
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        self.seen.append(messages)
        response = AIMessage(
            content=f"Fixture answer for {self.mode}.",
            usage_metadata={"input_tokens": 20, "output_tokens": 6, "total_tokens": 26},
        )
        return ChatResult(generations=[ChatGeneration(message=response)])


class MemoryRevokedAfterSendFixtureModel(MemoryWireFixtureModel):
    db_path: str
    memory_id: str

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        from opspilot.domain.semantic_memory import revoke_semantic_memory

        self.seen.append(messages)
        revoke_semantic_memory(
            self.db_path, self.memory_id, "approver-a",
            idempotency_key=f"ar04b-after-send-revoke-{self.memory_id}",
        )
        response = AIMessage(
            content="Fixture answer generated after Memory was sent.",
            usage_metadata={"input_tokens": 20, "output_tokens": 8, "total_tokens": 28},
        )
        return ChatResult(generations=[ChatGeneration(message=response)])


class MemoryGuidanceTamperedAfterSendFixtureModel(MemoryWireFixtureModel):
    """Corrupt only the persisted wire guidance after dispatch, before answer commit."""

    db_path: str
    memory_id: str

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        from opspilot.domain.database import connect

        self.seen.append(messages)
        with connect(self.db_path) as connection:
            rows = connection.execute(
                """SELECT call_id,request_json FROM assistant_calls
                   WHERE kind='MODEL' AND status='RESERVED' ORDER BY created_at DESC"""
            ).fetchall()
            for row in rows:
                request = json.loads(str(row["request_json"]))
                source_refs = request.get("source_refs", {})
                selected = source_refs.get("selected_memory_refs", [])
                item = next((value for value in selected if value.get("memory_id") == self.memory_id), None)
                if item is None:
                    continue
                summary = str(item["summary"])
                for message in request.get("messages", []):
                    data = message.get("data") if isinstance(message.get("data"), dict) else message
                    content = str(data.get("content", ""))
                    if summary in content:
                        data["content"] = content.replace(summary, "[tampered guidance]")
                connection.execute(
                    "UPDATE assistant_calls SET request_json=? WHERE call_id=?",
                    (json.dumps(request, ensure_ascii=False, sort_keys=True, separators=(",", ":")), row["call_id"]),
                )
                break
            else:
                raise AssertionError("No reserved MODEL request contained the selected Memory")
        response = AIMessage(
            content="Fixture answer after wire guidance was tampered.",
            usage_metadata={"input_tokens": 20, "output_tokens": 8, "total_tokens": 28},
        )
        return ChatResult(generations=[ChatGeneration(message=response)])


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


def _login(client: TestClient, origin: str, passwords: dict[str, str], actor_id: str) -> dict[str, str]:
    response = client.post(
        "/api/auth/login", headers={"Origin": origin},
        json={"actor_id": actor_id, "password": passwords[actor_id]},
    )
    assert response.status_code == 200, response.text
    return {"Origin": origin, "X-CSRF-Token": response.json()["csrf_token"]}


def _seed_async_project_approver(db_path: Path) -> None:
    """The stock demo fixture grants approvers for orders-demo, not S3's project."""
    from opspilot.domain.database import connect

    with connect(db_path) as connection:
        connection.execute(
            """INSERT OR IGNORE INTO semantic_memory_project_approvers
               (tenant_id, project_id, actor_id, active, granted_by, granted_at)
               VALUES ('tenant-a', 'service:orders-async-demo', 'approver-a', 1,
                       'fixture:ar04b-trusted-approver', CURRENT_TIMESTAMP)"""
        )


def _create_approved_semantic_memory(
    client: TestClient, origin: str, passwords: dict[str, str], support_headers: dict[str, str],
    *, suffix: str, content: str | None = None,
) -> tuple[dict[str, object], dict[str, object], dict[str, str]]:
    source_session = client.post("/api/sessions", headers=support_headers).json()["session_id"]
    source = client.post(
        f"/api/sessions/{source_session}/assistant/order",
        headers={**support_headers, "Idempotency-Key": f"ar04b-source-{suffix}"},
        json={
            "order_id": "ar02-order",
            "initial_message": "For callback support, inspect current same-Event Receiver evidence; HTTP 202 only proves transport acceptance.",
        },
    )
    assert source.status_code == 202, source.text
    source_item = source.json()
    assert _wait_for_run(client, str(source_item["run_id"]))["status"] == "SUCCEEDED"
    candidate = client.post(
        f"/api/tasks/{source_item['task_id']}/semantic-memories/candidates",
        headers={**support_headers, "Idempotency-Key": f"ar04b-semantic-candidate-{suffix}"},
        json={
            "memory_kind": "INTERFACE_CONVENTION",
            "memory_key": f"callback.current-receiver-check.{suffix}",
            "content": content or "For callback support, inspect a current same-Event Receiver observation. HTTP 202 proves transport acceptance only; it does not prove business processing completed.",
            "source_message_id": source_item["message_id"],
            "ttl_days": 90,
        },
    )
    assert candidate.status_code == 201, candidate.text
    candidate_item = candidate.json()
    approver_headers = _login(client, origin, passwords, "approver-a")
    confirmed = client.post(
        f"/api/semantic-memories/{candidate_item['memory_id']}/confirm",
        headers={**approver_headers, "Idempotency-Key": f"ar04b-semantic-confirm-{suffix}"},
        json={},
    )
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["state"] == "ACTIVE"
    return source_item, {**candidate_item, **confirmed.json()}, _login(client, origin, passwords, "support-a")


def test_ar04b_confirmed_cross_task_memory_is_present_on_formal_assistant_wire(
    demo_db: Path, tmp_path: Path, monkeypatch,
) -> None:
    """Pair Memory ON/OFF on the formal API/Worker wire and preserve current MCP facts."""
    from opspilot.domain.database import connect
    from opspilot.domain.s3 import prepare_s3_fixture
    from opspilot.web.app import create_app
    from test_ar02_journey_p0 import JourneyFixtureModel
    from test_ar02_assistant import ORIGIN, PASSWORDS

    prepare_s3_fixture(demo_db, "DELIVERED_PENDING", order_id="ar02-order", contract_version=2)
    _seed_async_project_approver(demo_db)
    models = [
        MemoryWireFixtureModel(mode="source-task"),
        JourneyFixtureModel(mode="receiver"),
        JourneyFixtureModel(mode="receiver"),
    ]
    app = create_app(
        db_path=demo_db, checkpoint_db_path=tmp_path / "ar04b-worker.sqlite3",
        start_worker=True, credentials=PASSWORDS, expected_origin=ORIGIN,
        assistant_model_factory=lambda: models.pop(0),
    )

    with TestClient(app) as client:
        source_item, candidate_item, support_headers = _create_approved_semantic_memory(
            client, ORIGIN, PASSWORDS, _login(client, ORIGIN, PASSWORDS, "support-a"),
            suffix="e1-related-semantic",
        )
        assert candidate_item["state"] == "ACTIVE"

        def start_target(idempotency_key: str) -> tuple[dict[str, object], str, str]:
            session_id = client.post("/api/sessions", headers=support_headers).json()["session_id"]
            response = client.post(
                f"/api/sessions/{session_id}/assistant/order",
                headers={**support_headers, "Idempotency-Key": idempotency_key},
                json={
                    "order_id": "ar02-order",
                    "initial_message": "The new callback for this order is not confirmed yet. What should I check first?",
                },
            )
            assert response.status_code == 202, response.text
            item = response.json()
            assert item["task_id"] != source_item["task_id"]
            assert _wait_for_run(client, str(item["run_id"]))["status"] == "SUCCEEDED"
            answers = client.get(f"/api/sessions/{session_id}/messages").json()["items"]
            answer = next(message for message in answers if message["role"] == "ASSISTANT")
            assert "QUEUED" in answer["body"]
            assert "尚不能称为处理完成" in answer["body"]
            return item, session_id, answer["body"]

        on_item, on_session, on_answer = start_target("ar04b-target-on")
        # Test-only OFF arm: disable only Memory selection. The same assistant,
        # tool schemas, trusted binding and Domain observations remain active.
        import opspilot.domain.chat as chat_domain
        original_current_memories = chat_domain._current_memories
        monkeypatch.setattr(
            chat_domain, "_current_memories",
            lambda connection, task_id, state, evidence, excluded_sources=None: [],
        )
        off_item, off_session, off_answer = start_target("ar04b-target-off")
        monkeypatch.setattr(chat_domain, "_current_memories", original_current_memories)

    with connect(demo_db) as connection:
        calls = connection.execute(
            """SELECT run_id,call_id,kind,status,request_json,result_json,evidence_id,observation_id
               FROM assistant_calls WHERE run_id IN (?, ?) ORDER BY created_at""",
            (on_item["run_id"], off_item["run_id"]),
        ).fetchall()
        protected_writes = {
            table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in ("s3_diagnoses", "d3_action_intents", "d3_action_ledgers", "s3_handoff_receipts")
        }
    manifests_by_run = {}
    for run_id in (on_item["run_id"], off_item["run_id"]):
        with connect(demo_db) as connection:
            row = connection.execute(
                "SELECT memory_refs_json FROM chat_context_manifests WHERE run_id=? ORDER BY created_at DESC LIMIT 1",
                (run_id,),
            ).fetchone()
        manifests_by_run[run_id] = json.loads(str(row["memory_refs_json"]))
    manifest_memories = manifests_by_run[str(on_item["run_id"])]
    assert [item["memory_id"] for item in manifest_memories] == [candidate_item["memory_id"]]
    assert manifests_by_run[str(off_item["run_id"])] == []
    on_calls = [row for row in calls if row["kind"] == "MODEL" and row["run_id"] == on_item["run_id"]]
    off_calls = [row for row in calls if row["kind"] == "MODEL" and row["run_id"] == off_item["run_id"]]
    mcp_calls = [row for row in calls if row["kind"] == "MCP"]
    assert len(on_calls) >= 2 and len(off_calls) >= 2
    assert {json.loads(str(row["request_json"]))["name"] for row in mcp_calls} >= {
        "get_callback_delivery", "get_receiver_processing",
    }
    actual_wires = [json.loads(str(row["request_json"])) for row in on_calls]
    actual_model_messages = [
        "\n".join(
            str(message.get("data", {}).get("content", message.get("content", "")))
            for message in wire["messages"]
        )
        for wire in actual_wires
    ]
    for wire in actual_wires:
        wire_refs = wire["source_refs"]["selected_memory_refs"]
        assert [item["memory_id"] for item in wire_refs] == [candidate_item["memory_id"]]
        assert wire_refs[0]["version"] == candidate_item["version"]
        assert wire_refs[0]["digest"] == candidate_item["content_digest"]
        assert wire["context_blocks"]
        external = next(
            item for item in wire["context_blocks"]
            if item["block_id"] == "investigator-external-guidance"
        )
        assert external["status"] == "SELECTED"
        assert candidate_item["memory_id"] in external["source_refs"]
    assert manifest_memories[0]["version"] == candidate_item["version"]
    assert manifest_memories[0]["digest"] == candidate_item["content_digest"]
    assert protected_writes == {key: 0 for key in protected_writes}
    for wire_text in actual_model_messages:
        assert candidate_item["memory_id"] in wire_text
        assert '"version":1' in wire_text
        assert candidate_item["content_digest"] in wire_text
        assert "For callback support, inspect a current same-Event Receiver observation." in wire_text
    for wire in actual_wires:
        assert wire["context_budget"]["estimated_input_tokens"] <= wire["context_budget"]["input_budget_tokens"]
        external = next(
            item for item in wire["context_blocks"]
            if item["block_id"] == "investigator-external-guidance"
        )
        assert external["estimated_tokens"] > 0
    off_wires = [json.loads(str(row["request_json"])) for row in off_calls]
    assert all(wire["source_refs"]["selected_memory_refs"] == [] for wire in off_wires)
    assert all(candidate_item["memory_id"] not in json.dumps(wire["messages"]) for wire in off_wires)
    assert all(
        next(item for item in wire["context_blocks"]
             if item["block_id"] == "investigator-external-guidance")["estimated_tokens"] == 0
        for wire in off_wires
    )
    assert all(
        wire["tools"] == off_wires[index]["tools"]
        for index, wire in enumerate(actual_wires[: len(off_wires)])
    )
    assert {json.loads(str(row["request_json"]))["name"] for row in mcp_calls if row["run_id"] == on_item["run_id"]} == {
        json.loads(str(row["request_json"]))["name"] for row in mcp_calls if row["run_id"] == off_item["run_id"]
    }
    assert on_answer == off_answer

    trace_path = tmp_path / "ar04b-memory-wire-on-off.json"
    trace_path.write_text(json.dumps({
        "evidence_level": "FORMAL_API_WORKER_MOCK_MODEL_MCP_DOMAIN",
        "pair": "E1_RELATED_SEMANTIC_MEMORY_ON_OFF",
        "source_task_id": source_item["task_id"],
        "source_message_id": source_item["message_id"],
        "candidate_id": candidate_item["memory_id"],
        "candidate_version": candidate_item["version"],
        "candidate_digest": candidate_item["content_digest"],
        "on_task_id": on_item["task_id"],
        "on_run_id": on_item["run_id"],
        "on_session_id": on_session,
        "off_task_id": off_item["task_id"],
        "off_run_id": off_item["run_id"],
        "off_session_id": off_session,
        "manifest_memory_refs": manifest_memories,
        "actual_model_wires": actual_wires,
        "off_model_wires": off_wires,
        "actual_mcp_calls": [
            {"tool_request": json.loads(str(row["request_json"])),
             "result": json.loads(str(row["result_json"])) if row["result_json"] else None,
             "evidence_id": row["evidence_id"], "observation_id": row["observation_id"]}
            for row in mcp_calls
        ],
        "on_answer": on_answer,
        "off_answer": off_answer,
        "protected_business_writes": protected_writes,
    }, ensure_ascii=False, indent=2), encoding="utf-8")


def test_ar04b_answer_commit_rejects_memory_manifest_when_wire_guidance_was_tampered(
    demo_db: Path, tmp_path: Path,
) -> None:
    """A source ref and digest alone cannot claim guidance that the Provider did not receive."""
    from opspilot.domain.database import connect
    from opspilot.domain.s3 import prepare_s3_fixture
    from opspilot.web.app import create_app
    from test_ar02_assistant import ORIGIN, PASSWORDS

    prepare_s3_fixture(demo_db, "DELIVERED_PENDING", order_id="ar02-order", contract_version=2)
    _seed_async_project_approver(demo_db)
    tamper_model = MemoryGuidanceTamperedAfterSendFixtureModel(
        mode="tampered-wire", db_path=str(demo_db), memory_id="pending",
    )
    models = [MemoryWireFixtureModel(mode="source-task"), tamper_model]
    app = create_app(
        db_path=demo_db, checkpoint_db_path=tmp_path / "ar04b-wire-tamper.sqlite3",
        start_worker=True, credentials=PASSWORDS, expected_origin=ORIGIN,
        assistant_model_factory=lambda: models.pop(0),
    )
    with TestClient(app) as client:
        _, memory, support = _create_approved_semantic_memory(
            client, ORIGIN, PASSWORDS, _login(client, ORIGIN, PASSWORDS, "support-a"),
            suffix="wire-tamper",
        )
        tamper_model.memory_id = str(memory["memory_id"])
        session_id = client.post("/api/sessions", headers=support).json()["session_id"]
        response = client.post(
            f"/api/sessions/{session_id}/assistant/order",
            headers={**support, "Idempotency-Key": "ar04b-wire-tamper-target"},
            json={"order_id": "ar02-order", "initial_message": "Check the current callback receiver."},
        )
        assert response.status_code == 202, response.text
        target = response.json()
        run = _wait_for_run(client, str(target["run_id"]))

    assert tamper_model.seen
    assert run["status"] != "SUCCEEDED"
    with connect(demo_db) as connection:
        answers = connection.execute(
            "SELECT COUNT(*) FROM chat_run_answers WHERE run_id=?", (target["run_id"],),
        ).fetchone()[0]
        request = connection.execute(
            "SELECT request_json FROM assistant_calls WHERE run_id=? AND kind='MODEL' ORDER BY created_at DESC LIMIT 1",
            (target["run_id"],),
        ).fetchone()
        manifest = connection.execute(
            "SELECT memory_refs_json FROM chat_context_manifests WHERE run_id=? ORDER BY created_at DESC LIMIT 1",
            (target["run_id"],),
        ).fetchone()
    assert answers == 0
    assert request is not None and manifest is not None
    assert run["status"] == "FAILED"
    assert run.get("waiting_reason") == "ASSISTANT_STOP:TaskControlError:CHAT_MEMORY_WIRE_SOURCE_MISMATCH"
    request_data = json.loads(str(request["request_json"]))
    wire_text = "\n".join(
        str(message.get("data", {}).get("content", message.get("content", "")))
        for message in request_data["messages"]
    )
    assert memory["memory_id"] in wire_text
    assert memory["content_digest"] in wire_text
    assert "[tampered guidance]" in wire_text
    assert "For callback support, inspect a current same-Event Receiver observation." not in wire_text
    assert json.loads(str(manifest["memory_refs_json"]))[0]["memory_id"] == memory["memory_id"]
    (tmp_path / "ar04b-wire-tamper-rejected.json").write_text(json.dumps({
        "evidence_level": "FORMAL_API_WORKER_FIXTURE_MODEL_COMMIT_VALIDATION",
        "case": "MANIFEST_REFERENCE_WITH_TAMPERED_GUIDANCE_REJECTED",
        "memory_id": memory["memory_id"], "memory_version": memory["version"],
        "memory_digest": memory["content_digest"], "task_id": target["task_id"],
        "run_id": target["run_id"], "run_status": run["status"],
        "stop_reason": run.get("waiting_reason"), "committed_answers": answers,
        "manifest_memory_refs": json.loads(str(manifest["memory_refs_json"])),
        "tampered_persisted_model_request": request_data,
    }, ensure_ascii=False, indent=2), encoding="utf-8")


def test_ar04b_unrelated_valid_semantic_memory_does_not_block_current_investigation(
    demo_db: Path, tmp_path: Path, monkeypatch,
) -> None:
    """A valid but unrelated project hint is non-authoritative; current MCP still completes the task."""
    from opspilot.domain.database import connect
    from opspilot.domain.s3 import prepare_s3_fixture
    from opspilot.web.app import create_app
    from test_ar02_assistant import ORIGIN, PASSWORDS
    from test_ar02_journey_p0 import JourneyFixtureModel

    unrelated_hint = (
        "For billing disputes, reconcile monthly invoice totals to the finance ledger; "
        "this is not a callback procedure."
    )
    prepare_s3_fixture(demo_db, "DELIVERED_PENDING", order_id="ar02-order", contract_version=2)
    _seed_async_project_approver(demo_db)
    models = [
        MemoryWireFixtureModel(mode="source-task"),
        JourneyFixtureModel(mode="receiver"),
        JourneyFixtureModel(mode="receiver"),
    ]
    app = create_app(
        db_path=demo_db, checkpoint_db_path=tmp_path / "ar04b-unrelated-memory.sqlite3",
        start_worker=True, credentials=PASSWORDS, expected_origin=ORIGIN,
        assistant_model_factory=lambda: models.pop(0),
    )
    with TestClient(app) as client:
        _, memory, support = _create_approved_semantic_memory(
            client, ORIGIN, PASSWORDS, _login(client, ORIGIN, PASSWORDS, "support-a"),
            suffix="unrelated-valid", content=unrelated_hint,
        )

        def run_target(key: str) -> tuple[dict[str, object], str, str]:
            session_id = client.post("/api/sessions", headers=support).json()["session_id"]
            response = client.post(
                f"/api/sessions/{session_id}/assistant/order",
                headers={**support, "Idempotency-Key": key},
                json={
                    "order_id": "ar02-order",
                    "initial_message": "What is the current callback state for the bound order?",
                },
            )
            assert response.status_code == 202, response.text
            item = response.json()
            assert _wait_for_run(client, str(item["run_id"]))["status"] == "SUCCEEDED"
            answer = next(
                message for message in client.get(f"/api/sessions/{session_id}/messages").json()["items"]
                if message["role"] == "ASSISTANT"
            )["body"]
            return item, session_id, answer

        on_item, on_session, on_answer = run_target("ar04b-unrelated-memory-on")
        import opspilot.domain.chat as chat_domain
        original_current_memories = chat_domain._current_memories
        monkeypatch.setattr(
            chat_domain, "_current_memories",
            lambda connection, task_id, state, evidence, excluded_sources=None: [],
        )
        off_item, off_session, off_answer = run_target("ar04b-unrelated-memory-off")
        monkeypatch.setattr(chat_domain, "_current_memories", original_current_memories)

    with connect(demo_db) as connection:
        run_ids = (on_item["run_id"], off_item["run_id"])
        manifests = {
            run_id: json.loads(str(connection.execute(
                "SELECT memory_refs_json FROM chat_context_manifests WHERE run_id=? ORDER BY created_at DESC LIMIT 1",
                (run_id,),
            ).fetchone()["memory_refs_json"]))
            for run_id in run_ids
        }
        calls = [dict(row) for row in connection.execute(
            "SELECT run_id,kind,request_json,result_json,evidence_id,observation_id FROM assistant_calls "
            "WHERE run_id IN (?,?) ORDER BY created_at", run_ids,
        )]
        protected_writes = {
            table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in ("s3_diagnoses", "d3_action_intents", "d3_action_ledgers", "s3_handoff_receipts")
        }

    assert [item["memory_id"] for item in manifests[on_item["run_id"]]] == [memory["memory_id"]]
    assert manifests[off_item["run_id"]] == []
    on_model_calls = [item for item in calls if item["run_id"] == on_item["run_id"] and item["kind"] == "MODEL"]
    off_model_calls = [item for item in calls if item["run_id"] == off_item["run_id"] and item["kind"] == "MODEL"]
    on_wire_text = "\n".join(
        str(message.get("data", {}).get("content", message.get("content", "")))
        for call in on_model_calls
        for message in json.loads(call["request_json"])["messages"]
    )
    off_wire_text = "\n".join(
        str(message.get("data", {}).get("content", message.get("content", "")))
        for call in off_model_calls
        for message in json.loads(call["request_json"])["messages"]
    )
    assert memory["memory_id"] in on_wire_text and unrelated_hint in on_wire_text
    assert memory["memory_id"] not in off_wire_text and unrelated_hint not in off_wire_text
    on_mcp = [item for item in calls if item["run_id"] == on_item["run_id"] and item["kind"] == "MCP"]
    off_mcp = [item for item in calls if item["run_id"] == off_item["run_id"] and item["kind"] == "MCP"]
    assert {json.loads(item["request_json"])["name"] for item in on_mcp} == {
        json.loads(item["request_json"])["name"] for item in off_mcp
    } == {"get_callback_delivery", "get_receiver_processing"}
    for calls_for_run in (on_mcp, off_mcp):
        results = {json.loads(item["request_json"])["name"]: json.loads(item["result_json"]) for item in calls_for_run}
        assert results["get_callback_delivery"]["facts"]["status"] == "ACKNOWLEDGED"
        assert results["get_callback_delivery"]["facts"]["receiver_http_status"] == 202
        assert results["get_receiver_processing"]["facts"]["status"] == "QUEUED"
        assert results["get_callback_delivery"]["facts"]["event_id"] == results["get_receiver_processing"]["facts"]["event_id"]
    assert on_answer == off_answer and "QUEUED" in on_answer
    assert protected_writes == {key: 0 for key in protected_writes}
    trace_path = tmp_path / "ar04b-unrelated-memory-on-off.json"
    trace_path.write_text(json.dumps({
        "evidence_level": "FORMAL_API_WORKER_MOCK_MODEL_MCP_DOMAIN",
        "pair": "E6_UNRELATED_VALID_SEMANTIC_MEMORY_ON_OFF",
        "memory_id": memory["memory_id"], "memory_version": memory["version"],
        "memory_digest": memory["content_digest"], "source_task_id": memory["source_task_id"],
        "on_task_id": on_item["task_id"], "on_run_id": on_item["run_id"], "on_session_id": on_session,
        "off_task_id": off_item["task_id"], "off_run_id": off_item["run_id"], "off_session_id": off_session,
        "model_call_counts": {"on": len(on_model_calls), "off": len(off_model_calls)},
        "on_answer": on_answer, "off_answer": off_answer,
        "on_mcp_calls": [
            {"request": json.loads(item["request_json"]), "result": json.loads(item["result_json"]),
             "evidence_id": item["evidence_id"], "observation_id": item["observation_id"]}
            for item in on_mcp
        ],
        "off_mcp_calls": [
            {"request": json.loads(item["request_json"]), "result": json.loads(item["result_json"]),
             "evidence_id": item["evidence_id"], "observation_id": item["observation_id"]}
            for item in off_mcp
        ],
        "protected_business_writes": protected_writes,
    }, ensure_ascii=False, indent=2), encoding="utf-8")


def test_ar04b_confirmed_episodic_memory_is_method_only_against_current_queued_fact(
    demo_db: Path, tmp_path: Path, monkeypatch,
) -> None:
    """Pair an approved S3 Episodic Memory ON/OFF; current same-Event MCP wins."""
    from opspilot.domain.database import connect, reset_fixture
    from opspilot.domain.s3 import persist_s3_diagnosis, prepare_s3_fixture
    from opspilot.domain.task_control import apply_pending_critical_inputs, claim_task_run, finish_task_run
    from opspilot.web.app import create_app
    from test_ar02_assistant import ORIGIN, PASSWORDS
    from test_ar02_journey_p0 import JourneyFixtureModel
    from test_m4_03_s3 import _evidence, _facts, _task

    reset_fixture(demo_db, "S1_POS")
    prepare_s3_fixture(
        demo_db, "DELIVERY_FAILED", order_id="ar04b-episodic-source",
        attempt_count=3, retry_state="EXHAUSTED",
    )
    prepare_s3_fixture(demo_db, "DELIVERED_PENDING", order_id="ar02-order")
    prepare_s3_fixture(demo_db, "DELIVERED_PENDING", order_id="ar02-processed-order")
    # This is a deterministic fixture update to a schema-valid receiver state.
    # It creates the current fact variant; no application business action runs.
    with connect(demo_db) as connection:
        connection.execute(
            "UPDATE s3_receivers SET status='PROCESSED', version=version+1 "
            "WHERE tenant_id='tenant-a' AND service_id='orders-async-demo' AND order_id='ar02-processed-order'"
        )
    _seed_async_project_approver(demo_db)
    source_identity, source = _task(
        demo_db, "ar04b-episodic-source",
        text="A prior callback delivery failed. Record only the verified method, not a current customer state.",
    )
    claim_task_run(demo_db, source_identity, str(source["run_id"]))
    apply_pending_critical_inputs(demo_db, source_identity, str(source["run_id"]))
    order, delivery, receiver = _facts(demo_db, source)
    source_evidence = [
        _evidence(demo_db, source, "get_order_status", order),
        _evidence(demo_db, source, "get_callback_delivery", delivery),
        _evidence(demo_db, source, "get_receiver_processing", receiver),
    ]
    diagnosis = persist_s3_diagnosis(
        demo_db, str(source["task_id"]), str(source["run_id"]), source_evidence,
    )
    assert diagnosis["outcome"] == "CALLBACK_DELIVERY_FAILED"
    finish_task_run(demo_db, source_identity, str(source["run_id"]), "SUCCEEDED")
    with connect(demo_db) as connection:
        source_diagnosis_count = connection.execute("SELECT COUNT(*) FROM s3_diagnoses").fetchone()[0]

    on_model = JourneyFixtureModel(mode="receiver")
    off_model = JourneyFixtureModel(mode="receiver")
    processed_on_model = JourneyFixtureModel(mode="receiver")
    processed_off_model = JourneyFixtureModel(mode="receiver")
    models = [on_model, off_model, processed_on_model, processed_off_model]
    app = create_app(
        db_path=demo_db, checkpoint_db_path=tmp_path / "ar04b-episodic.sqlite3",
        start_worker=True, credentials=PASSWORDS, expected_origin=ORIGIN,
        assistant_model_factory=lambda: models.pop(0),
    )
    with TestClient(app) as client:
        support = _login(client, ORIGIN, PASSWORDS, "support-a")
        candidate = client.post(
            f"/api/tasks/{source['task_id']}/memories/candidates",
            headers={**support, "Idempotency-Key": "ar04b-episodic-candidate"}, json={},
        )
        assert candidate.status_code == 201, candidate.text
        candidate_item = candidate.json()
        approver = _login(client, ORIGIN, PASSWORDS, "approver-a")
        confirmed = client.post(
            f"/api/memories/{candidate_item['memory_id']}/confirm",
            headers={**approver, "Idempotency-Key": "ar04b-episodic-confirm"}, json={},
        )
        assert confirmed.status_code == 200, confirmed.text
        assert confirmed.json()["state"] == "ACTIVE"
        support = _login(client, ORIGIN, PASSWORDS, "support-a")

        def run_target(key: str, order_id: str = "ar02-order") -> tuple[dict[str, object], str]:
            session_response = client.post("/api/sessions", headers=support)
            assert session_response.status_code == 201, session_response.text
            session_id = session_response.json()["session_id"]
            accepted = client.post(
                f"/api/sessions/{session_id}/assistant/order",
                headers={**support, "Idempotency-Key": key},
                json={
                    "order_id": order_id,
                    "initial_message": "This callback resembles an earlier failure. What is its current state?",
                },
            )
            assert accepted.status_code == 202, accepted.text
            item = accepted.json()
            assert _wait_for_run(client, str(item["run_id"]))["status"] == "SUCCEEDED"
            answer = next(
                message for message in client.get(f"/api/sessions/{session_id}/messages").json()["items"]
                if message["role"] == "ASSISTANT"
            )["body"]
            if order_id == "ar02-order":
                assert "QUEUED" in answer and "尚不能称为处理完成" in answer
            else:
                assert "PROCESSED" in answer
            return item, answer

        on_item, on_answer = run_target("ar04b-episodic-on")
        import opspilot.domain.chat as chat_domain
        original_current_memories = chat_domain._current_memories
        monkeypatch.setattr(
            chat_domain, "_current_memories",
            lambda connection, task_id, state, evidence, excluded_sources=None: [],
        )
        off_item, off_answer = run_target("ar04b-episodic-off")
        monkeypatch.setattr(chat_domain, "_current_memories", original_current_memories)
        processed_on_item, processed_on_answer = run_target(
            "ar04b-episodic-processed-on", "ar02-processed-order",
        )
        monkeypatch.setattr(
            chat_domain, "_current_memories",
            lambda connection, task_id, state, evidence, excluded_sources=None: [],
        )
        processed_off_item, processed_off_answer = run_target(
            "ar04b-episodic-processed-off", "ar02-processed-order",
        )
        monkeypatch.setattr(chat_domain, "_current_memories", original_current_memories)

    with connect(demo_db) as connection:
        on_manifest = connection.execute(
            "SELECT memory_refs_json FROM chat_context_manifests WHERE run_id=? ORDER BY created_at DESC LIMIT 1",
            (on_item["run_id"],),
        ).fetchone()
        off_manifest = connection.execute(
            "SELECT memory_refs_json FROM chat_context_manifests WHERE run_id=? ORDER BY created_at DESC LIMIT 1",
            (off_item["run_id"],),
        ).fetchone()
        processed_on_manifest = connection.execute(
            "SELECT memory_refs_json FROM chat_context_manifests WHERE run_id=? ORDER BY created_at DESC LIMIT 1",
            (processed_on_item["run_id"],),
        ).fetchone()
        processed_off_manifest = connection.execute(
            "SELECT memory_refs_json FROM chat_context_manifests WHERE run_id=? ORDER BY created_at DESC LIMIT 1",
            (processed_off_item["run_id"],),
        ).fetchone()
        calls = [dict(row) for row in connection.execute(
            "SELECT run_id,kind,request_json,result_json,evidence_id,observation_id FROM assistant_calls WHERE run_id IN (?,?,?,?)",
            (on_item["run_id"], off_item["run_id"], processed_on_item["run_id"], processed_off_item["run_id"]),
        )]
        protected_writes = {
            table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in ("s3_diagnoses", "d3_action_intents", "d3_action_ledgers", "s3_handoff_receipts")
        }
    on_refs = json.loads(str(on_manifest["memory_refs_json"]))
    assert [item["memory_id"] for item in on_refs] == [candidate_item["memory_id"]]
    assert on_refs[0]["memory_type"] == "EPISODIC"
    assert on_refs[0]["source_task_id"] == source["task_id"]
    assert json.loads(str(off_manifest["memory_refs_json"])) == []
    assert [item["memory_id"] for item in json.loads(str(processed_on_manifest["memory_refs_json"]))] == [candidate_item["memory_id"]]
    assert json.loads(str(processed_off_manifest["memory_refs_json"])) == []
    on_model_calls = [item for item in calls if item["run_id"] == on_item["run_id"] and item["kind"] == "MODEL"]
    off_model_calls = [item for item in calls if item["run_id"] == off_item["run_id"] and item["kind"] == "MODEL"]
    processed_on_calls = [item for item in calls if item["run_id"] == processed_on_item["run_id"]]
    processed_off_calls = [item for item in calls if item["run_id"] == processed_off_item["run_id"]]
    on_mcp_calls = [item for item in calls if item["run_id"] == on_item["run_id"] and item["kind"] == "MCP"]
    off_mcp_calls = [item for item in calls if item["run_id"] == off_item["run_id"] and item["kind"] == "MCP"]
    assert on_answer == off_answer
    assert processed_on_answer == processed_off_answer
    assert "PROCESSED" in processed_on_answer
    assert {json.loads(item["request_json"])["name"] for item in on_mcp_calls} == {
        json.loads(item["request_json"])["name"] for item in off_mcp_calls
    }
    on_wire_texts = [json.dumps(json.loads(item["request_json"])["messages"], ensure_ascii=False) for item in on_model_calls]
    assert all(candidate_item["memory_id"] in text for text in on_wire_texts)
    assert all("HISTORICAL_METHOD_HINT_ONLY" in text for text in on_wire_texts)
    assert all(candidate_item["memory_id"] not in json.dumps(json.loads(item["request_json"])["messages"])
               for item in off_model_calls)
    processed_on_mcp = [item for item in processed_on_calls if item["kind"] == "MCP"]
    processed_off_mcp = [item for item in processed_off_calls if item["kind"] == "MCP"]
    processed_results = {
        json.loads(item["request_json"])["name"]: json.loads(item["result_json"])["facts"]
        for item in processed_on_mcp
    }
    assert processed_results["get_callback_delivery"]["status"] == "ACKNOWLEDGED"
    assert processed_results["get_callback_delivery"]["receiver_http_status"] == 202
    assert processed_results["get_receiver_processing"]["status"] == "PROCESSED"
    assert processed_results["get_callback_delivery"]["event_id"] == processed_results["get_receiver_processing"]["event_id"]
    assert {json.loads(item["request_json"])["name"] for item in processed_on_mcp} == {
        json.loads(item["request_json"])["name"] for item in processed_off_mcp
    }
    assert all(candidate_item["memory_id"] in json.dumps(json.loads(item["request_json"])["messages"], ensure_ascii=False)
               for item in processed_on_calls if item["kind"] == "MODEL")
    current_wire = " ".join(on_wire_texts)
    assert "QUEUED" in current_wire
    assert "202" in current_wire
    on_result_by_tool = {
        json.loads(item["request_json"])["name"]: json.loads(item["result_json"])
        for item in on_mcp_calls
    }
    delivery_facts = on_result_by_tool["get_callback_delivery"]["facts"]
    receiver_facts = on_result_by_tool["get_receiver_processing"]["facts"]
    assert delivery_facts["status"] == "ACKNOWLEDGED"
    assert delivery_facts["receiver_http_status"] == 202
    assert receiver_facts["status"] == "QUEUED"
    assert delivery_facts["event_id"] == receiver_facts["event_id"]
    assert protected_writes["s3_diagnoses"] == source_diagnosis_count == 1
    assert protected_writes["d3_action_intents"] == 0
    assert protected_writes["d3_action_ledgers"] == 0
    assert protected_writes["s3_handoff_receipts"] == 0
    trace_path = tmp_path / "ar04b-episodic-queued-processed-on-off.json"
    trace_path.write_text(json.dumps({
        "evidence_level": "FORMAL_API_WORKER_FIXTURE_MODEL_MCP_DOMAIN",
        "pair": "E2_E3_EPISODIC_METHOD_ON_OFF_WITH_QUEUED_AND_PROCESSED_CURRENT_FACTS",
        "memory_id": candidate_item["memory_id"], "memory_version": on_refs[0]["version"],
        "memory_digest": on_refs[0]["content_digest"], "source_task_id": source["task_id"],
        "queued": {
            "on": {"task_id": on_item["task_id"], "run_id": on_item["run_id"], "answer": on_answer},
            "off": {"task_id": off_item["task_id"], "run_id": off_item["run_id"], "answer": off_answer},
        },
        "processed": {
            "on": {"task_id": processed_on_item["task_id"], "run_id": processed_on_item["run_id"],
                   "answer": processed_on_answer},
            "off": {"task_id": processed_off_item["task_id"], "run_id": processed_off_item["run_id"],
                    "answer": processed_off_answer},
        },
        "mcp_calls": [
            {"run_id": item["run_id"], "request": json.loads(item["request_json"]),
             "result": json.loads(item["result_json"]) if item["result_json"] else None,
             "evidence_id": item["evidence_id"], "observation_id": item["observation_id"]}
            for item in calls if item["kind"] == "MCP"
        ],
        "protected_business_writes": protected_writes,
    }, ensure_ascii=False, indent=2), encoding="utf-8")


def test_ar04b_cross_tenant_memory_is_not_visible_and_legal_tenant_b_query_still_works(
    demo_db: Path, tmp_path: Path, monkeypatch,
) -> None:
    from opspilot.domain.database import connect
    from opspilot.domain.s3 import prepare_s3_fixture
    from opspilot.web.app import create_app
    from test_ar02_assistant import ORIGIN, PASSWORDS
    from test_ar02_journey_p0 import JourneyFixtureModel

    prepare_s3_fixture(demo_db, "DELIVERED_PENDING", order_id="ar02-order")
    prepare_s3_fixture(
        demo_db, "DELIVERED_PENDING", tenant_id="tenant-b", order_id="ar04b-tenant-b-order",
    )
    _seed_async_project_approver(demo_db)
    models = [
        MemoryWireFixtureModel(mode="source-task"),
        JourneyFixtureModel(mode="receiver"),
        JourneyFixtureModel(mode="receiver"),
    ]
    app = create_app(
        db_path=demo_db, checkpoint_db_path=tmp_path / "ar04b-cross-tenant.sqlite3",
        start_worker=True, credentials=PASSWORDS, expected_origin=ORIGIN,
        assistant_model_factory=lambda: models.pop(0),
    )
    with TestClient(app) as client:
        _, memory, support_a = _create_approved_semantic_memory(
            client, ORIGIN, PASSWORDS, _login(client, ORIGIN, PASSWORDS, "support-a"),
            suffix="cross-tenant-a",
        )
        support_b = _login(client, ORIGIN, PASSWORDS, "support-b")

        def run_target(key: str) -> tuple[dict[str, object], str, str]:
            session_id = client.post("/api/sessions", headers=support_b).json()["session_id"]
            accepted = client.post(
                f"/api/sessions/{session_id}/assistant/order",
                headers={**support_b, "Idempotency-Key": key},
                json={
                    "order_id": "ar04b-tenant-b-order",
                    "initial_message": "What is the current callback state for the bound order?",
                },
            )
            assert accepted.status_code == 202, accepted.text
            item = accepted.json()
            assert _wait_for_run(client, str(item["run_id"]))["status"] == "SUCCEEDED"
            answer = next(
                message for message in client.get(f"/api/sessions/{session_id}/messages").json()["items"]
                if message["role"] == "ASSISTANT"
            )["body"]
            assert "QUEUED" in answer
            return item, session_id, answer

        on_item, on_session, on_answer = run_target("ar04b-cross-tenant-on")
        import opspilot.domain.chat as chat_domain
        original_current_memories = chat_domain._current_memories
        monkeypatch.setattr(
            chat_domain, "_current_memories",
            lambda connection, task_id, state, evidence, excluded_sources=None: [],
        )
        off_item, off_session, off_answer = run_target("ar04b-cross-tenant-off")
        monkeypatch.setattr(chat_domain, "_current_memories", original_current_memories)

    with connect(demo_db) as connection:
        on_manifest = connection.execute(
            "SELECT memory_refs_json FROM chat_context_manifests WHERE run_id=? ORDER BY created_at DESC LIMIT 1",
            (on_item["run_id"],),
        ).fetchone()
        off_manifest = connection.execute(
            "SELECT memory_refs_json FROM chat_context_manifests WHERE run_id=? ORDER BY created_at DESC LIMIT 1",
            (off_item["run_id"],),
        ).fetchone()
        calls = [dict(row) for row in connection.execute(
            "SELECT run_id,kind,request_json,result_json FROM assistant_calls WHERE run_id IN (?,?)",
            (on_item["run_id"], off_item["run_id"]),
        )]
        tenant_a_task = connection.execute(
            "SELECT tenant_id FROM task_bindings WHERE task_id=?", (memory["source_task_id"],),
        ).fetchone()
        tenant_b_task = connection.execute(
            "SELECT tenant_id FROM task_bindings WHERE task_id=?", (on_item["task_id"],),
        ).fetchone()
    assert tenant_a_task["tenant_id"] == "tenant-a"
    assert tenant_b_task["tenant_id"] == "tenant-b"
    assert json.loads(str(on_manifest["memory_refs_json"])) == []
    assert json.loads(str(off_manifest["memory_refs_json"])) == []
    assert support_a["Origin"] == support_b["Origin"] == ORIGIN
    on_model_wires = [json.loads(item["request_json"]) for item in calls if item["run_id"] == on_item["run_id"] and item["kind"] == "MODEL"]
    off_model_wires = [json.loads(item["request_json"]) for item in calls if item["run_id"] == off_item["run_id"] and item["kind"] == "MODEL"]
    assert on_model_wires and off_model_wires
    assert all(memory["memory_id"] not in json.dumps(wire["messages"]) for wire in on_model_wires + off_model_wires)
    on_tools = {json.loads(item["request_json"])["name"] for item in calls if item["run_id"] == on_item["run_id"] and item["kind"] == "MCP"}
    off_tools = {json.loads(item["request_json"])["name"] for item in calls if item["run_id"] == off_item["run_id"] and item["kind"] == "MCP"}
    assert on_tools == off_tools == {"get_callback_delivery", "get_receiver_processing"}
    assert on_answer == off_answer
    trace_path = tmp_path / "ar04b-cross-tenant-on-off.json"
    trace_path.write_text(json.dumps({
        "evidence_level": "FORMAL_API_WORKER_FIXTURE_MODEL_MCP_DOMAIN",
        "pair": "E4_CROSS_TENANT_MEMORY_EXCLUSION_WITH_LEGAL_TENANT_QUERY",
        "foreign_memory_id": memory["memory_id"], "foreign_source_task_id": memory["source_task_id"],
        "foreign_tenant_id": tenant_a_task["tenant_id"], "target_tenant_id": tenant_b_task["tenant_id"],
        "on": {"task_id": on_item["task_id"], "run_id": on_item["run_id"],
               "session_id": on_session, "answer": on_answer,
               "manifest_memory_refs": json.loads(str(on_manifest["memory_refs_json"]))},
        "off": {"task_id": off_item["task_id"], "run_id": off_item["run_id"],
                "session_id": off_session, "answer": off_answer,
                "manifest_memory_refs": json.loads(str(off_manifest["memory_refs_json"]))},
        "calls": [
            {"run_id": item["run_id"], "kind": item["kind"],
             "request": json.loads(item["request_json"]),
             "result": json.loads(item["result_json"]) if item["result_json"] else None,
             "evidence_id": item.get("evidence_id"), "observation_id": item.get("observation_id")}
            for item in calls
        ],
    }, ensure_ascii=False, indent=2), encoding="utf-8")


def test_ar04b_revocation_before_provider_boundary_blocks_stale_memory_and_keeps_valid_path(
    demo_db: Path, tmp_path: Path, monkeypatch,
) -> None:
    from opspilot.domain.database import connect
    from opspilot.domain.s3 import prepare_s3_fixture
    from opspilot.domain.semantic_memory import revoke_semantic_memory
    from opspilot.web.app import create_app
    from opspilot.domain import episodic_memory
    from test_ar02_assistant import ORIGIN, PASSWORDS

    prepare_s3_fixture(demo_db, "DELIVERED_PENDING", order_id="ar02-order", contract_version=2)
    _seed_async_project_approver(demo_db)
    target_model = MemoryWireFixtureModel(mode="target-not-sent")
    models = [MemoryWireFixtureModel(mode="source-task"), target_model]
    app = create_app(
        db_path=demo_db, checkpoint_db_path=tmp_path / "ar04b-before-send.sqlite3",
        start_worker=True, credentials=PASSWORDS, expected_origin=ORIGIN,
        assistant_model_factory=lambda: models.pop(0),
    )
    with TestClient(app) as client:
        source, memory, support = _create_approved_semantic_memory(
            client, ORIGIN, PASSWORDS, _login(client, ORIGIN, PASSWORDS, "support-a"),
            suffix="before-send-revoke",
        )
        check_count = 0
        original_check = episodic_memory.assert_selected_memories_current
        revoke_events: list[dict[str, object]] = []

        def revoke_on_pre_send(path, task_id, selected_memories):
            nonlocal check_count
            if any(item.get("memory_id") == memory["memory_id"] for item in selected_memories):
                check_count += 1
                if check_count == 2:
                    revoke_events.append(revoke_semantic_memory(
                        path, str(memory["memory_id"]), "approver-a",
                        idempotency_key="ar04b-before-send-revoke",
                    ))
            return original_check(path, task_id, selected_memories)

        monkeypatch.setattr(episodic_memory, "assert_selected_memories_current", revoke_on_pre_send)
        session_id = client.post("/api/sessions", headers=support).json()["session_id"]
        response = client.post(
            f"/api/sessions/{session_id}/assistant/order",
            headers={**support, "Idempotency-Key": "ar04b-before-send-target"},
            json={"order_id": "ar02-order", "initial_message": "Check the current callback receiver."},
        )
        assert response.status_code == 202, response.text
        target = response.json()
        run = _wait_for_run(client, str(target["run_id"]))

    assert revoke_events and revoke_events[0]["state"] == "REVOKED"
    assert check_count >= 2
    assert target_model.seen == [], "stale Memory must be rejected before the model handler is entered"
    with connect(demo_db) as connection:
        call = connection.execute(
            "SELECT status,result_json FROM assistant_calls WHERE run_id=? AND kind='MODEL'",
            (target["run_id"],),
        ).fetchone()
        answer_count = connection.execute(
            "SELECT COUNT(*) FROM chat_run_answers WHERE run_id=?", (target["run_id"],),
        ).fetchone()[0]
    assert run["status"] != "SUCCEEDED"
    assert call is not None and call["status"] == "FAILED"
    assert "ASSISTANT_MEMORY_INVALIDATED_BEFORE_SEND" in str(call["result_json"])
    assert answer_count == 0
    # The preceding E1 positive path proves the same trusted source remains usable before revocation.
    assert source["task_id"] != target["task_id"]
    (tmp_path / "ar04b-revocation-before-send.json").write_text(json.dumps({
        "evidence_level": "FORMAL_API_WORKER_FIXTURE_MODEL_PRE_SEND_REVOCATION",
        "case": "G8_REVOKED_AFTER_RESERVATION_BEFORE_PROVIDER_HANDLER",
        "memory_id": memory["memory_id"], "memory_version": memory["version"],
        "memory_digest": memory["content_digest"], "source_task_id": source["task_id"],
        "target_task_id": target["task_id"], "run_id": target["run_id"],
        "run_status": run["status"], "model_call_status": call["status"],
        "model_call_result": call["result_json"], "model_handler_inputs": target_model.seen,
        "committed_answers": answer_count, "revocations": revoke_events,
    }, ensure_ascii=False, indent=2), encoding="utf-8")


def test_ar04b_revocation_after_checkpoint_load_blocks_stale_continuation(
    demo_db: Path, tmp_path: Path, monkeypatch,
) -> None:
    """Recheck the saved manifest after checkpoint read and before graph continuation."""
    from opspilot.domain.database import connect
    from opspilot.domain.semantic_memory import revoke_semantic_memory
    from opspilot.domain.s3 import prepare_s3_fixture
    from opspilot.web.app import create_app
    import opspilot.assistant as assistant
    from test_ar02_assistant import ORIGIN, PASSWORDS

    prepare_s3_fixture(demo_db, "DELIVERED_PENDING", order_id="ar02-order", contract_version=2)
    _seed_async_project_approver(demo_db)
    target_model = MemoryWireFixtureModel(mode="checkpoint-stale-memory")
    models = [MemoryWireFixtureModel(mode="source-task"), target_model]
    app = create_app(
        db_path=demo_db, checkpoint_db_path=tmp_path / "ar04b-checkpoint-revoke.sqlite3",
        start_worker=True, credentials=PASSWORDS, expected_origin=ORIGIN,
        assistant_model_factory=lambda: models.pop(0),
    )
    with TestClient(app) as client:
        _, memory, support = _create_approved_semantic_memory(
            client, ORIGIN, PASSWORDS, _login(client, ORIGIN, PASSWORDS, "support-a"),
            suffix="checkpoint-revoke",
        )
        original_check = assistant.Loop.assert_manifest_memories_current
        revocations: list[dict[str, object]] = []

        def revoke_after_checkpoint_load(loop) -> None:
            if not revocations:
                with connect(demo_db) as connection:
                    row = connection.execute(
                        "SELECT memory_refs_json FROM chat_context_manifests WHERE run_id=? "
                        "ORDER BY created_at DESC LIMIT 1", (loop.run_id,),
                    ).fetchone()
                if row is not None and any(
                    item.get("memory_id") == memory["memory_id"]
                    for item in json.loads(str(row["memory_refs_json"]))
                ):
                    revocations.append(revoke_semantic_memory(
                        demo_db, str(memory["memory_id"]), "approver-a",
                        idempotency_key="ar04b-checkpoint-revoke",
                    ))
            original_check(loop)

        monkeypatch.setattr(assistant.Loop, "assert_manifest_memories_current", revoke_after_checkpoint_load)
        session_id = client.post("/api/sessions", headers=support).json()["session_id"]
        response = client.post(
            f"/api/sessions/{session_id}/assistant/order",
            headers={**support, "Idempotency-Key": "ar04b-checkpoint-stale-target"},
            json={"order_id": "ar02-order", "initial_message": "Check the current callback receiver."},
        )
        assert response.status_code == 202, response.text
        target = response.json()
        run = _wait_for_run(client, str(target["run_id"]))

    assert revocations and revocations[0]["state"] == "REVOKED"
    assert target_model.seen == []
    assert run["status"] == "FAILED"
    assert "ContextAssetInvalidated" in str(run.get("waiting_reason", ""))
    with connect(demo_db) as connection:
        model_calls = connection.execute(
            "SELECT COUNT(*) FROM assistant_calls WHERE run_id=? AND kind='MODEL'",
            (target["run_id"],),
        ).fetchone()[0]
        answers = connection.execute(
            "SELECT COUNT(*) FROM chat_run_answers WHERE run_id=?", (target["run_id"],),
        ).fetchone()[0]
    assert model_calls == 0
    assert answers == 0
    (tmp_path / "ar04b-checkpoint-revoke.json").write_text(json.dumps({
        "evidence_level": "FORMAL_API_WORKER_FIXTURE_MODEL_CHECKPOINT_PRECONTINUATION",
        "case": "G8_REVOKED_AFTER_CHECKPOINT_READ_BEFORE_GRAPH_CONTINUATION",
        "memory_id": memory["memory_id"], "memory_version": memory["version"],
        "memory_digest": memory["content_digest"], "task_id": target["task_id"],
        "run_id": target["run_id"], "run_status": run["status"],
        "stop_reason": run.get("waiting_reason"), "revocation": revocations[0],
        "provider_model_calls": model_calls, "committed_answers": answers,
    }, ensure_ascii=False, indent=2), encoding="utf-8")


def test_ar04b_revocation_after_send_prevents_answer_commit(
    demo_db: Path, tmp_path: Path, monkeypatch,
) -> None:
    from opspilot.domain.database import connect
    from opspilot.domain.s3 import prepare_s3_fixture
    from opspilot.domain import semantic_memory
    from opspilot.web.app import create_app
    from test_ar02_assistant import ORIGIN, PASSWORDS

    prepare_s3_fixture(demo_db, "DELIVERED_PENDING", order_id="ar02-order", contract_version=2)
    _seed_async_project_approver(demo_db)
    models = [MemoryWireFixtureModel(mode="source-task")]
    app = create_app(
        db_path=demo_db, checkpoint_db_path=tmp_path / "ar04b-after-send.sqlite3",
        start_worker=True, credentials=PASSWORDS, expected_origin=ORIGIN,
        assistant_model_factory=lambda: models.pop(0),
    )
    with TestClient(app) as client:
        _, memory, support = _create_approved_semantic_memory(
            client, ORIGIN, PASSWORDS, _login(client, ORIGIN, PASSWORDS, "support-a"),
            suffix="after-send-revoke",
        )
        target_model = MemoryRevokedAfterSendFixtureModel(
            mode="target-after-send", db_path=str(demo_db), memory_id=str(memory["memory_id"]),
        )
        models.append(target_model)
        session_id = client.post("/api/sessions", headers=support).json()["session_id"]
        response = client.post(
            f"/api/sessions/{session_id}/assistant/order",
            headers={**support, "Idempotency-Key": "ar04b-after-send-target"},
            json={"order_id": "ar02-order", "initial_message": "Check the current callback receiver."},
        )
        assert response.status_code == 202, response.text
        target = response.json()
        run = _wait_for_run(client, str(target["run_id"]))

        post_revoke_model = MemoryWireFixtureModel(mode="post-revoke-normal")
        models.append(post_revoke_model)
        next_session = client.post("/api/sessions", headers=support).json()["session_id"]
        next_response = client.post(
            f"/api/sessions/{next_session}/assistant/order",
            headers={**support, "Idempotency-Key": "ar04b-after-revoke-normal-target"},
            json={"order_id": "ar02-order", "initial_message": "Explain what remains known."},
        )
        assert next_response.status_code == 202, next_response.text
        next_target = next_response.json()
        next_run = _wait_for_run(client, str(next_target["run_id"]))
        next_answer = next(
            message for message in client.get(f"/api/sessions/{next_session}/messages").json()["items"]
            if message["role"] == "ASSISTANT"
        )["body"]

        post_revoke_off_model = MemoryWireFixtureModel(mode="post-revoke-normal")
        models.append(post_revoke_off_model)
        import opspilot.domain.chat as chat_domain
        original_current_memories = chat_domain._current_memories
        monkeypatch.setattr(
            chat_domain, "_current_memories",
            lambda connection, task_id, state, evidence, excluded_sources=None: [],
        )
        off_session = client.post("/api/sessions", headers=support).json()["session_id"]
        off_response = client.post(
            f"/api/sessions/{off_session}/assistant/order",
            headers={**support, "Idempotency-Key": "ar04b-after-revoke-off-target"},
            json={"order_id": "ar02-order", "initial_message": "Explain what remains known."},
        )
        assert off_response.status_code == 202, off_response.text
        off_target = off_response.json()
        off_run = _wait_for_run(client, str(off_target["run_id"]))
        off_answer = next(
            message for message in client.get(f"/api/sessions/{off_session}/messages").json()["items"]
            if message["role"] == "ASSISTANT"
        )["body"]
        monkeypatch.setattr(chat_domain, "_current_memories", original_current_memories)

    assert target_model.seen, "the memory was valid at dispatch and crossed the model boundary"
    sent_text = json.dumps(target_model.seen[0], ensure_ascii=False, default=str)
    assert str(memory["memory_id"]) in sent_text
    assert run["status"] != "SUCCEEDED"
    with connect(demo_db) as connection:
        model_call = connection.execute(
            "SELECT status,result_json FROM assistant_calls WHERE run_id=? AND kind='MODEL'",
            (target["run_id"],),
        ).fetchone()
        answer_count = connection.execute(
            "SELECT COUNT(*) FROM chat_run_answers WHERE run_id=?", (target["run_id"],),
        ).fetchone()[0]
        receipt_count = connection.execute("SELECT COUNT(*) FROM s3_handoff_receipts").fetchone()[0]
    assert model_call is not None and model_call["status"] == "OK"
    assert answer_count == 0
    assert receipt_count == 0
    with connect(demo_db) as connection:
        current = connection.execute(
            "SELECT state,version FROM semantic_memories WHERE memory_id=?", (memory["memory_id"],),
        ).fetchone()
    assert tuple(current) == ("REVOKED", 2)
    assert next_run["status"] == "SUCCEEDED"
    assert post_revoke_model.seen
    assert str(memory["memory_id"]) not in json.dumps(post_revoke_model.seen[0], ensure_ascii=False, default=str)
    assert off_run["status"] == "SUCCEEDED"
    assert next_answer == off_answer
    assert post_revoke_off_model.seen
    assert str(memory["memory_id"]) not in json.dumps(post_revoke_off_model.seen[0], ensure_ascii=False, default=str)
    with connect(demo_db) as connection:
        next_manifest = connection.execute(
            "SELECT memory_refs_json FROM chat_context_manifests WHERE run_id=? ORDER BY created_at DESC LIMIT 1",
            (next_target["run_id"],),
        ).fetchone()
    assert json.loads(str(next_manifest["memory_refs_json"])) == []
    with connect(demo_db) as connection:
        off_manifest = connection.execute(
            "SELECT memory_refs_json FROM chat_context_manifests WHERE run_id=? ORDER BY created_at DESC LIMIT 1",
            (off_target["run_id"],),
        ).fetchone()
    assert json.loads(str(off_manifest["memory_refs_json"])) == []
    (tmp_path / "ar04b-revocation-after-send.json").write_text(json.dumps({
        "evidence_level": "FORMAL_API_WORKER_FIXTURE_MODEL_MEMORY_REVOCATION_RACE",
        "case": "G8_REVOKED_DURING_MODEL_CALL_BLOCKS_ANSWER_COMMIT",
        "memory_id": memory["memory_id"], "memory_version": memory["version"],
        "memory_digest": memory["content_digest"], "state_after_revocation": tuple(current),
        "stale_target": {
            "task_id": target["task_id"], "run_id": target["run_id"], "run_status": run["status"],
            "model_call_status": model_call["status"], "committed_answers": answer_count,
            "receipt_count": receipt_count,
            "actual_model_input": json.dumps(target_model.seen[0], ensure_ascii=False, default=str),
        },
        "after_revoke_on": {
            "task_id": next_target["task_id"], "run_id": next_target["run_id"],
            "run_status": next_run["status"], "answer": next_answer,
            "manifest_memory_refs": json.loads(str(next_manifest["memory_refs_json"])),
            "model_seen": json.dumps(post_revoke_model.seen[0], ensure_ascii=False, default=str),
        },
        "after_revoke_off": {
            "task_id": off_target["task_id"], "run_id": off_target["run_id"],
            "run_status": off_run["status"], "answer": off_answer,
            "manifest_memory_refs": json.loads(str(off_manifest["memory_refs_json"])),
            "model_seen": json.dumps(post_revoke_off_model.seen[0], ensure_ascii=False, default=str),
        },
    }, ensure_ascii=False, indent=2), encoding="utf-8")


def test_ar04b_same_task_followup_keeps_memory_non_authoritative_and_rechecks_current_fact(
    demo_db: Path, tmp_path: Path,
) -> None:
    """J6: continue the same bound task while rechecking facts in the new Run."""
    from opspilot.domain.database import connect
    from opspilot.domain.s3 import prepare_s3_fixture
    from opspilot.web.app import create_app
    from test_ar02_journey_p0 import JourneyFixtureModel
    from test_ar02_assistant import ORIGIN, PASSWORDS

    prepare_s3_fixture(demo_db, "DELIVERED_PENDING", order_id="ar02-order", contract_version=2)
    _seed_async_project_approver(demo_db)
    models = [
        MemoryWireFixtureModel(mode="source-task"),
        JourneyFixtureModel(mode="receiver"),
        JourneyFixtureModel(mode="draft"),
    ]
    app = create_app(
        db_path=demo_db, checkpoint_db_path=tmp_path / "ar04b-same-task-followup.sqlite3",
        start_worker=True, credentials=PASSWORDS, expected_origin=ORIGIN,
        assistant_model_factory=lambda: models.pop(0),
    )
    with TestClient(app) as client:
        _, memory, support = _create_approved_semantic_memory(
            client, ORIGIN, PASSWORDS, _login(client, ORIGIN, PASSWORDS, "support-a"),
            suffix="same-task-followup",
        )
        session_id = client.post("/api/sessions", headers=support).json()["session_id"]
        accepted = client.post(
            f"/api/sessions/{session_id}/assistant/order",
            headers={**support, "Idempotency-Key": "ar04b-same-task-initial"},
            json={
                "order_id": "ar02-order",
                "initial_message": "What is the current callback state for the bound order?",
            },
        )
        assert accepted.status_code == 202, accepted.text
        initial = accepted.json()
        initial_run = _wait_for_run(client, str(initial["run_id"]))
        assert initial_run["status"] == "SUCCEEDED"
        initial_answer = next(
            message["body"] for message in client.get(
                f"/api/sessions/{session_id}/messages"
            ).json()["items"] if message["role"] == "ASSISTANT"
        )
        assert "QUEUED" in initial_answer

        accepted_followup = client.post(
            f"/api/sessions/{session_id}/assistant/messages",
            headers={**support, "Idempotency-Key": "ar04b-same-task-followup"},
            json={
                "task_id": initial["task_id"],
                "body": "Now what should I do? Has it already been fixed?",
            },
        )
        assert accepted_followup.status_code == 202, accepted_followup.text
        followup = accepted_followup.json()
        followup_run = _wait_for_run(client, str(followup["run_id"]))
        assert followup_run["status"] == "SUCCEEDED"
        with connect(demo_db) as connection:
            followup_answer_row = connection.execute(
                "SELECT m.body FROM chat_run_answers a JOIN messages m ON m.message_id=a.message_id "
                "WHERE a.run_id=?", (followup["run_id"],),
            ).fetchone()
        assert followup_answer_row is not None
        final_answer = str(followup_answer_row["body"])

    with connect(demo_db) as connection:
        manifest = connection.execute(
            "SELECT memory_refs_json FROM chat_context_manifests WHERE run_id=? "
            "ORDER BY created_at DESC LIMIT 1", (followup["run_id"],),
        ).fetchone()
        calls = [dict(row) for row in connection.execute(
            "SELECT kind,request_json,result_json,evidence_id,observation_id "
            "FROM assistant_calls WHERE run_id=? ORDER BY created_at",
            (followup["run_id"],),
        )]
        writes = {
            table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in ("s3_diagnoses", "d3_action_intents", "d3_action_ledgers", "s3_handoff_receipts")
        }

    manifest_refs = json.loads(str(manifest["memory_refs_json"]))
    assert [item["memory_id"] for item in manifest_refs] == [memory["memory_id"]]
    model_calls = [item for item in calls if item["kind"] == "MODEL"]
    mcp_calls = [item for item in calls if item["kind"] == "MCP"]
    assert model_calls and mcp_calls
    model_requests = [json.loads(item["request_json"]) for item in model_calls]
    wire_text = "\\n".join(json.dumps(item["messages"], ensure_ascii=False) for item in model_requests)
    assert memory["memory_id"] in wire_text
    assert "CONFIRMED PROJECT MEMORY GUIDANCE (non-authoritative; not current evidence)" in wire_text
    assert initial_answer in wire_text
    assert all(request["context_budget"]["estimated_input_tokens"] <= 12_000 for request in model_requests)
    assert {json.loads(item["request_json"])["name"] for item in mcp_calls} == {
        "get_receiver_processing",
    }
    receiver_results = [json.loads(item["result_json"]) for item in mcp_calls]
    assert all(result["facts"]["status"] == "QUEUED" for result in receiver_results)
    assert all(
        result["facts"]["event_id"] == receiver_results[0]["facts"]["event_id"]
        for result in receiver_results
    )
    assert "QUEUED" in final_answer
    assert "未提交、未创建工单" in final_answer
    assert writes == {
        "s3_diagnoses": 0, "d3_action_intents": 0,
        "d3_action_ledgers": 0, "s3_handoff_receipts": 0,
    }
    (tmp_path / "ar04b-same-task-followup.json").write_text(json.dumps({
        "evidence_level": "FORMAL_API_WORKER_FIXTURE_MODEL_MCP_DOMAIN",
        "case": "J6_SAME_TASK_FOLLOWUP_CURRENT_FACT_RECHECK",
        "task_id": initial["task_id"], "session_id": session_id,
        "initial_run_id": initial["run_id"], "followup_run_id": followup["run_id"],
        "initial_message_id": initial["message_id"], "followup_message_id": followup["message_id"],
        "memory_id": memory["memory_id"], "memory_version": memory["version"],
        "memory_digest": memory["content_digest"], "manifest_memory_refs": manifest_refs,
        "initial_answer": initial_answer, "followup_answer": final_answer,
        "model_requests": model_requests,
        "mcp_calls": [
            {"request": json.loads(item["request_json"]),
             "result": json.loads(item["result_json"]) if item["result_json"] else None,
             "evidence_id": item["evidence_id"], "observation_id": item["observation_id"]}
            for item in mcp_calls
        ],
        "protected_business_writes": writes,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
