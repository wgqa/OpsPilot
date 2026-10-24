from __future__ import annotations

import json
import threading
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from opspilot.domain.api import make_server
from opspilot.domain.database import connect, reset_fixture
from opspilot.domain.investigation_updates import complete_assessment, reserve_assessment
from opspilot.domain.s3 import (
    evaluate_s3_gate,
    get_callback_delivery_fact,
    get_order_status_fact,
    get_receiver_processing_fact,
    persist_s3_diagnosis,
    prepare_s3_fixture,
)
from opspilot.domain.task_control import (
    TaskControlError,
    admit_task_message,
    claim_task_run,
    create_readonly_followup_run_in_transaction,
    create_session,
    create_task_with_initial_run,
    finish_task_run,
    persist_readonly_followup_result,
    trusted_identity,
)
from opspilot.domain.chat import _prepare_context
from opspilot.domain.investigation_context import load_investigation_context
from opspilot.web.app import create_app
from tests.s3_observation_support import record_s3_observation


ORIGIN = "http://testserver"
PASSWORD = "support-test-password"


def _diagnosed_task(db: Path) -> tuple[str, str, str, str]:
    prepare_s3_fixture(db, "DELIVERED_PENDING", contract_version=2, queue_age_seconds=60)
    identity = trusted_identity(db, "support-a")
    session = create_session(db, identity)
    created = create_task_with_initial_run(
        db, identity, session_id=str(session["session_id"]),
        service_id="orders-async-demo", integration_id="async-integration-a",
        ticket_id="M4-C1-HF-01", initial_message="订单已完成，HTTP 202 后请核实下游回调状态。",
        idempotency_key=f"m4-c1-hf-01-create-{db.stem}", s3_order_id="async-order",
    )
    task_id, diagnosis_run_id = str(created["task_id"]), str(created["run_id"])
    claim_task_run(db, identity, diagnosis_run_id)
    server = make_server(db, "tenant-a", "127.0.0.1", 0)
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True)
    thread.start()
    try:
        root = f"http://127.0.0.1:{server.server_port}"
        facts = [
            ("get_order_status", get_order_status_fact(db, task_id, root)),
            ("get_callback_delivery", get_callback_delivery_fact(db, task_id)),
            ("get_receiver_processing", get_receiver_processing_fact(db, task_id)),
        ]
    finally:
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()
    evidence_ids = [
        str(record_s3_observation(
            db, {"task_id": task_id, "run_id": diagnosis_run_id}, tool_name, fact, arguments={},
        )["evidence_id"])
        for tool_name, fact in facts
    ]
    gate = evaluate_s3_gate(db, task_id, evidence_ids, run_id=diagnosis_run_id)
    assert gate["decision"] == "DIAGNOSED", gate
    diagnosis = persist_s3_diagnosis(db, task_id, diagnosis_run_id, evidence_ids)
    finish_task_run(db, identity, diagnosis_run_id, "SUCCEEDED")
    return str(session["session_id"]), task_id, diagnosis_run_id, str(diagnosis["receipt_id"])


def _persist_previous_followup(
    db: Path, session_id: str, task_id: str, *, suffix: str = "prior",
) -> dict[str, str]:
    from opspilot.domain.s3_assets import search_knowledge

    identity = trusted_identity(db, "support-a")
    source = admit_task_message(
        db, identity, session_id=session_id, task_id=task_id, input_kind="CHAT_READONLY",
        body="按当前绑定协议核对 HTTP 202，并给出可查证依据。",
        idempotency_key=f"m4-c1-hf-01-{suffix}-message",
    )
    source_message_id = str(source["message_id"])
    with connect(db) as connection:
        source_row = connection.execute(
            "SELECT body_digest,sequence FROM messages WHERE message_id=?", (source_message_id,),
        ).fetchone()
        control = connection.execute(
            "SELECT control_revision FROM task_controls WHERE task_id=?", (task_id,),
        ).fetchone()
        connection.execute("BEGIN IMMEDIATE")
        created = create_readonly_followup_run_in_transaction(
            connection, identity, task_id=task_id, session_id=session_id,
            source_message_id=source_message_id, source_digest=str(source_row["body_digest"]),
            expected_control_revision=int(control["control_revision"]),
        )
    run_id = str(created["run_id"])
    claim_task_run(db, identity, run_id)
    doc = next(item for item in search_knowledge(
        "HTTP 202 receiver acknowledgement processing", limit=3, contract_version=2,
    ) if item["document_id"] == "receiver-ack-contract-v2")
    with connect(db) as connection:
        diagnosis = connection.execute(
            "SELECT evidence_ids_json FROM s3_diagnoses WHERE task_id=? ORDER BY rowid DESC LIMIT 1",
            (task_id,),
        ).fetchone()
    prior_evidence_id = str(json.loads(str(diagnosis["evidence_ids_json"]))[-1])
    result = persist_readonly_followup_result(
        db, identity, run_id, result_state="ANSWERED",
        answer_text=(
            "Earlier I cited receiver-ack-contract-v2: HTTP 202 records acceptance/queueing; "
            "it does not prove the receiver finished processing."
        ),
        source_refs=[
            {"kind": "USER_MESSAGE", "message_id": source_message_id,
             "digest": str(source_row["body_digest"]), "provenance": "USER_INPUT_UNTRUSTED"},
            {"kind": "EVIDENCE", "evidence_id": prior_evidence_id,
             "fact_type": "receiver_processing", "versions": {}},
            {"kind": "KNOWLEDGE", **{
                key: doc.get(key) for key in ("document_id", "version", "digest", "source", "valid_from")
            }},
        ],
        result={"task_id": task_id, "source_message_id": source_message_id,
                "diagnosis_persisted": False, "readonly_followup": True},
    )
    finish_task_run(db, identity, run_id, "SUCCEEDED")
    with connect(db) as connection:
        connection.execute(
            """UPDATE task_runs SET status='BLOCKED',blocked_reason='FOLLOWUP_ROUTED_TO_INVESTIGATOR',ended_at=CURRENT_TIMESTAMP
               WHERE source_message_id=? AND kind='CHAT_READONLY' AND status='QUEUED'""",
            (source_message_id,),
        )
    return {"source_message_id": source_message_id, "run_id": run_id,
            "result_digest": str(result["result_digest"]), "document_id": str(doc["document_id"]),
            "document_version": str(doc["version"]), "document_digest": str(doc["digest"])}


def _new_user_message(db: Path, session_id: str, task_id: str, *, body: str, suffix: str) -> dict[str, object]:
    return admit_task_message(
        db, trusted_identity(db, "support-a"), session_id=session_id, task_id=task_id,
        input_kind="CHAT_READONLY", body=body, idempotency_key=f"m4-c1-hf-01-{suffix}-message",
    )


def test_hf01_completed_answer_and_current_knowledge_reach_classifier_context(tmp_path: Path) -> None:
    db = tmp_path / "hf01-classifier.sqlite3"
    reset_fixture(db, "S1_POS")
    session_id, task_id, _, _ = _diagnosed_task(db)
    prior = _persist_previous_followup(db, session_id, task_id)
    current = _new_user_message(
        db, session_id, task_id, body="你刚才引用的那份协议，为什么不能证明接收方已经处理完成？",
        suffix="hf01-current",
    )
    prepared = reserve_assessment(
        db, trusted_identity(db, "support-a"), task_id=task_id,
        source_message_id=str(current["message_id"]), idempotency_key=str(current["message_id"]),
        model_id="hf01-deterministic",
    )["prepared"]
    histories = prepared["prior_readonly_followups"]
    assert histories[0]["run_id"] == prior["run_id"]
    assert prior["result_digest"] == histories[0]["result_digest"]
    assert "receiver-ack-contract-v2" in histories[0]["answer_text"]
    knowledge = next(ref for ref in histories[0]["source_refs"] if ref["kind"] == "KNOWLEDGE")
    assert knowledge["document_id"] == prior["document_id"]
    assert knowledge["version"] == prior["document_version"]
    assert knowledge["digest"] == prior["document_digest"]
    assert knowledge["currentness"] == "CURRENT_APPLICABLE"


def test_hf01_prior_followup_is_a_bounded_chat_context_block_with_provenance(tmp_path: Path) -> None:
    db = tmp_path / "hf01-chat.sqlite3"
    reset_fixture(db, "S1_POS")
    session_id, task_id, _, _ = _diagnosed_task(db)
    prior = _persist_previous_followup(db, session_id, task_id)
    current = _new_user_message(
        db, session_id, task_id, body="你刚才引用的那份协议，为什么不能证明接收方已经处理完成？",
        suffix="hf01-chat-current",
    )
    with connect(db) as connection:
        run = connection.execute(
            "SELECT * FROM task_runs WHERE run_id=?", (current["run_id"],),
        ).fetchone()
        prepared = _prepare_context(connection, run, "hf01-deterministic", db)
    prompt = json.dumps(prepared["messages"], ensure_ascii=False)
    assert "Earlier I cited receiver-ack-contract-v2" in prompt
    block = next(item for item in prepared["context_blocks"] if item["category"] == "PRIOR_READONLY_FOLLOWUP")
    assert prior["run_id"] in block["source_refs"]
    assert prior["result_digest"] in json.dumps(block, ensure_ascii=False)
    assert prepared["prior_readonly_followup_refs"][0]["run_id"] == prior["run_id"]


def test_hf03_investigator_gets_prior_result_as_history_but_not_as_current_evidence(tmp_path: Path) -> None:
    db = tmp_path / "hf03-investigator.sqlite3"
    reset_fixture(db, "S1_POS")
    session_id, task_id, _, _ = _diagnosed_task(db)
    prior = _persist_previous_followup(db, session_id, task_id)
    current = _new_user_message(
        db, session_id, task_id, body="那现在接收方完成处理了吗？", suffix="hf03-current",
    )
    assessment = reserve_assessment(
        db, trusted_identity(db, "support-a"), task_id=task_id,
        source_message_id=str(current["message_id"]), idempotency_key=str(current["message_id"]),
        model_id="hf03-deterministic",
    )
    routed = complete_assessment(
        db, identity=trusted_identity(db, "support-a"),
        assessment_id=str(assessment["prepared"]["assessment_id"]),
        attempt_id=str(assessment["prepared"]["attempt_id"]),
        classification={"intent": "FOLLOW_UP", "change_summary": "", "readonly_action": "INVESTIGATE"},
    )
    run_id = str(routed["investigation_run_id"])
    claim_task_run(db, trusted_identity(db, "support-a"), run_id)
    context = load_investigation_context(db, task_id, run_id)
    prior_context = context["prior_readonly_followups"]
    assert prior_context[0]["run_id"] == prior["run_id"]
    old_evidence = next(ref for ref in prior_context[0]["source_refs"] if ref["kind"] == "EVIDENCE")
    assert old_evidence["currentness"] == "HISTORICAL_RUN_ONLY"
    assert not any(old_evidence["evidence_id"] == item.get("evidence_id")
                   for item in context.get("current_mcp_evidence", []))


def test_hf05_task_chat_run_is_not_worker_claimable_before_classification(tmp_path: Path, monkeypatch) -> None:
    db = tmp_path / "hf05-routing.sqlite3"
    reset_fixture(db, "S1_POS")
    session_id, task_id, _, _ = _diagnosed_task(db)
    app = create_app(db_path=db, start_worker=False, credentials={"support-a": PASSWORD},
                     expected_origin=ORIGIN, heartbeat_seconds=0.05)
    with TestClient(app, raise_server_exceptions=False) as client:
        login = client.post("/api/auth/login", headers={"Origin": ORIGIN},
                            json={"actor_id": "support-a", "password": PASSWORD})
        assert login.status_code == 200, login.text
        headers = {"Origin": ORIGIN, "X-CSRF-Token": login.json()["csrf_token"]}
        accepted = client.post(
            f"/api/sessions/{session_id}/messages",
            headers={**headers, "Idempotency-Key": "m4-c1-hf-01-hf05-pending"},
            json={"task_id": task_id, "input_kind": "CHAT_READONLY", "body": "核对当前接收状态。"},
        )
        assert accepted.status_code == 202, accepted.text
        run_id = str(accepted.json()["run_id"])
    from opspilot.domain.task_control import next_worker_run

    assert next_worker_run(db) is None
    with pytest.raises(TaskControlError, match="UPDATE_CLASSIFICATION_PENDING"):
        claim_task_run(db, trusted_identity(db, "support-a"), run_id)


def test_hf05_investigate_route_blocks_the_unused_chat_run_atomically(tmp_path: Path, monkeypatch) -> None:
    db = tmp_path / "hf05-single-route.sqlite3"
    reset_fixture(db, "S1_POS")
    session_id, task_id, _, _ = _diagnosed_task(db)
    app = create_app(db_path=db, start_worker=False, credentials={"support-a": PASSWORD},
                     expected_origin=ORIGIN, heartbeat_seconds=0.05)
    monkeypatch.setenv("OPSPILOT_MODEL_NAME", "hf05-deterministic")
    monkeypatch.setattr(
        "opspilot.domain.investigation_updates.classify_input",
        lambda **_kwargs: {"intent": "FOLLOW_UP", "change_summary": "", "readonly_action": "INVESTIGATE"},
    )
    with TestClient(app, raise_server_exceptions=False) as client:
        login = client.post("/api/auth/login", headers={"Origin": ORIGIN},
                            json={"actor_id": "support-a", "password": PASSWORD})
        assert login.status_code == 200, login.text
        headers = {"Origin": ORIGIN, "X-CSRF-Token": login.json()["csrf_token"]}
        accepted = client.post(
            f"/api/sessions/{session_id}/messages",
            headers={**headers, "Idempotency-Key": "m4-c1-hf-01-hf05-investigate"},
            json={"task_id": task_id, "input_kind": "CHAT_READONLY",
                  "body": "请重新查当前绑定订单接收方现在的处理状态。"},
        )
        assert accepted.status_code == 202, accepted.text
        source_id = str(accepted.json()["message_id"])
        result = client.post(
            f"/api/tasks/{task_id}/investigation-updates/proposals",
            headers={**headers, "Idempotency-Key": source_id},
            json={"source_message_id": source_id},
        )
        assert result.status_code == 200, result.text
        assert result.json()["follow_up_action"] == "INVESTIGATE"
        chat_run_id = str(accepted.json()["run_id"])
    with connect(db) as connection:
        chat_run = connection.execute(
            "SELECT status,blocked_reason FROM task_runs WHERE run_id=?", (chat_run_id,),
        ).fetchone()
        chat_calls = int(connection.execute(
            "SELECT COUNT(*) FROM chat_attempts WHERE run_id=?", (chat_run_id,),
        ).fetchone()[0])
    assert str(chat_run["status"]) == "BLOCKED"
    assert str(chat_run["blocked_reason"]) == "FOLLOWUP_ROUTED_TO_INVESTIGATOR"
    assert chat_calls == 0


def test_hf01_classifier_provider_payload_contains_prior_answer_and_currentness(tmp_path: Path, monkeypatch) -> None:
    import sys
    from types import ModuleType
    from types import SimpleNamespace

    from opspilot.domain.investigation_updates import classify_input

    db = tmp_path / "hf01-classifier-payload.sqlite3"
    reset_fixture(db, "S1_POS")
    session_id, task_id, _, _ = _diagnosed_task(db)
    _persist_previous_followup(db, session_id, task_id, suffix="classifier-payload")
    current = _new_user_message(
        db, session_id, task_id, body="刚才那条协议能证明处理完成吗？", suffix="classifier-payload-current",
    )
    prepared = reserve_assessment(
        db, trusted_identity(db, "support-a"), task_id=task_id,
        source_message_id=str(current["message_id"]), idempotency_key=str(current["message_id"]),
        model_id="hf01-deterministic",
    )["prepared"]
    captured: dict[str, str] = {}

    class FakeChatOpenAI:
        def __init__(self, **_kwargs):
            pass

        def invoke(self, messages):
            captured["human"] = str(messages[-1].content)
            return SimpleNamespace(
                content='{"intent":"FOLLOW_UP","change_summary":"","readonly_action":"EXPLAIN"}',
                usage_metadata={}, response_metadata={},
            )

    fake_module = ModuleType("langchain_openai")
    fake_module.ChatOpenAI = FakeChatOpenAI
    monkeypatch.setitem(sys.modules, "langchain_openai", fake_module)
    core_module = ModuleType("langchain_core")
    core_module.__path__ = []
    messages_module = ModuleType("langchain_core.messages")

    class FakeMessage:
        def __init__(self, content):
            self.content = content

    messages_module.HumanMessage = FakeMessage
    messages_module.SystemMessage = FakeMessage
    monkeypatch.setitem(sys.modules, "langchain_core", core_module)
    monkeypatch.setitem(sys.modules, "langchain_core.messages", messages_module)
    classify_input(prepared=prepared, model_id="hf01-deterministic", api_key="local-test-key")
    assert "Earlier I cited receiver-ack-contract-v2" in captured["human"]
    assert "CURRENT_APPLICABLE" in captured["human"]
    assert "HISTORICAL_RUN_ONLY" in captured["human"]
    assert "HISTORICAL_RESULT_ONLY" in captured["human"]


def test_hf02_replaced_knowledge_is_visible_only_as_stale_history(tmp_path: Path, monkeypatch) -> None:
    import opspilot.domain.s3_assets as assets

    db = tmp_path / "hf02-knowledge.sqlite3"
    reset_fixture(db, "S1_POS")
    session_id, task_id, _, _ = _diagnosed_task(db)
    prior = _persist_previous_followup(db, session_id, task_id, suffix="stale-knowledge")
    current = _new_user_message(
        db, session_id, task_id, body="刚才那条协议现在还适用吗？", suffix="stale-knowledge-current",
    )
    existing = assets.load_knowledge(contract_version=2)
    replaced = [dict(item) for item in existing]
    target = next(item for item in replaced if item["document_id"] == prior["document_id"])
    target.update({"version": "test-replacement-v3", "digest": "f" * 64})
    monkeypatch.setattr(assets, "load_knowledge", lambda *, contract_version=None: replaced)
    prepared = reserve_assessment(
        db, trusted_identity(db, "support-a"), task_id=task_id,
        source_message_id=str(current["message_id"]), idempotency_key=str(current["message_id"]),
        model_id="hf02-deterministic",
    )["prepared"]
    assert prepared["prior_readonly_followups"][0]["run_id"] == prior["run_id"]
    ref = next(item for item in prepared["prior_readonly_followups"][0]["source_refs"] if item["kind"] == "KNOWLEDGE")
    assert ref["version"] == prior["document_version"]
    assert ref["digest"] == prior["document_digest"]
    assert ref["currentness"] == "HISTORICAL_SOURCE_STALE"


def test_hf04_followup_history_is_task_session_tenant_and_auth_scoped(tmp_path: Path) -> None:
    from opspilot.domain.investigation_context import load_prior_readonly_followups

    db = tmp_path / "hf04-isolation.sqlite3"
    reset_fixture(db, "S1_POS")
    session_id, task_id, _, _ = _diagnosed_task(db)
    prior = _persist_previous_followup(db, session_id, task_id, suffix="isolation")
    identity = trusted_identity(db, "support-a")
    other_task = create_task_with_initial_run(
        db, identity, session_id=session_id, service_id="orders-demo", integration_id="integration-a",
        ticket_id="M4-C1-HF-01-OTHER-TASK", initial_message="另一个 Task 的独立调查。",
        idempotency_key="m4-c1-hf-01-other-task-create",
    )
    with connect(db) as connection:
        end_sequence = int(connection.execute(
            "SELECT COALESCE(MAX(sequence),0)+1 FROM messages WHERE session_id=?", (session_id,),
        ).fetchone()[0])
        same_task, exclusions = load_prior_readonly_followups(
            connection, tenant_id="tenant-a", session_id=session_id, task_id=task_id,
            before_sequence=end_sequence,
        )
        assert [item["run_id"] for item in same_task] == [prior["run_id"]]
        assert exclusions == []
        assert load_prior_readonly_followups(
            connection, tenant_id="tenant-a", session_id=session_id, task_id="other-task",
            before_sequence=end_sequence,
        ) == ([], [])
        assert load_prior_readonly_followups(
            connection, tenant_id="tenant-a", session_id=session_id,
            task_id=str(other_task["task_id"]), before_sequence=end_sequence,
        ) == ([], [])
        assert load_prior_readonly_followups(
            connection, tenant_id="tenant-b", session_id=session_id, task_id=task_id,
            before_sequence=end_sequence,
        ) == ([], [])
        binding = connection.execute(
            "SELECT principal_id FROM task_bindings WHERE task_id=?", (task_id,),
        ).fetchone()
        connection.execute(
            "UPDATE principal_scope_grants SET granted_scopes_json='[]',grant_version=grant_version+1 "
            "WHERE tenant_id='tenant-a' AND principal_id=?", (str(binding["principal_id"]),),
        )
        revoked, revoked_exclusions = load_prior_readonly_followups(
            connection, tenant_id="tenant-a", session_id=session_id, task_id=task_id,
            before_sequence=end_sequence,
        )
    assert revoked == []
    assert {item["reason"] for item in revoked_exclusions} == {"CURRENT_S3_AUTHORIZATION_UNAVAILABLE"}


def test_hf05_explain_route_releases_one_chat_run_and_persists_provenance(tmp_path: Path, monkeypatch) -> None:
    from opspilot.domain.chat import assert_chat_context_current, get_chat_manifest, prepare_chat_attempt
    from opspilot.domain.task_control import next_worker_run, register_worker_owner

    db = tmp_path / "hf05-explain.sqlite3"
    reset_fixture(db, "S1_POS")
    session_id, task_id, _, _ = _diagnosed_task(db)
    _persist_previous_followup(db, session_id, task_id, suffix="explain-context")
    app = create_app(db_path=db, start_worker=False, credentials={"support-a": PASSWORD},
                     expected_origin=ORIGIN, heartbeat_seconds=0.05)
    calls = {"n": 0}

    def classify(**_kwargs):
        calls["n"] += 1
        return {"intent": "FOLLOW_UP", "change_summary": "", "readonly_action": "EXPLAIN"}

    monkeypatch.setattr("opspilot.domain.investigation_updates.classify_input", classify)
    with TestClient(app, raise_server_exceptions=False) as client:
        login = client.post("/api/auth/login", headers={"Origin": ORIGIN},
                            json={"actor_id": "support-a", "password": PASSWORD})
        headers = {"Origin": ORIGIN, "X-CSRF-Token": login.json()["csrf_token"]}
        accepted = client.post(
            f"/api/sessions/{session_id}/messages",
            headers={**headers, "Idempotency-Key": "m4-c1-hf-01-hf05-explain"},
            json={"task_id": task_id, "input_kind": "CHAT_READONLY", "body": "解释当前协议的含义。"},
        )
        assert accepted.status_code == 202, accepted.text
        run_id, message_id = str(accepted.json()["run_id"]), str(accepted.json()["message_id"])
        with connect(db) as connection:
            pending = connection.execute(
                "SELECT status,blocked_reason FROM task_runs WHERE run_id=?", (run_id,),
            ).fetchone()
            assert str(pending["blocked_reason"]) == "UPDATE_CLASSIFICATION_PENDING"
            assert connection.execute("SELECT COUNT(*) FROM chat_attempts WHERE run_id=?", (run_id,)).fetchone()[0] == 0
        assessment = client.post(
            f"/api/tasks/{task_id}/investigation-updates/proposals",
            headers={**headers, "Idempotency-Key": message_id}, json={"source_message_id": message_id},
        )
        assert assessment.status_code == 200, assessment.text
        assert assessment.json()["follow_up_action"] == "EXPLAIN"
        replay = client.post(
            f"/api/tasks/{task_id}/investigation-updates/proposals",
            headers={**headers, "Idempotency-Key": message_id}, json={"source_message_id": message_id},
        )
        assert replay.status_code == 200, replay.text
        assert calls["n"] == 1
        assert str(replay.json()["assessment_id"]) == str(assessment.json()["assessment_id"])

    assert next_worker_run(db)["run_id"] == run_id
    identity = trusted_identity(db, "support-a")
    claim_task_run(db, identity, run_id)
    register_worker_owner(db, "hf05-worker", 4105)
    prepared = prepare_chat_attempt(db, run_id, "hf05-worker", "hf05-no-provider-test")
    assert prepared["attempt_id"]
    assert_chat_context_current(db, "hf05-worker", str(prepared["attempt_id"]))
    manifest = get_chat_manifest(db, identity, run_id)
    refs = manifest["prior_readonly_followup_refs"]
    assert refs, json.dumps({"blocks": manifest["context_blocks"], "excluded": manifest["excluded_sources"]}, ensure_ascii=False)
    assert refs[0]["source_refs"]
    assert "receiver-ack-contract-v2" in json.dumps(refs, ensure_ascii=False)
    with connect(db) as connection:
        assert connection.execute("SELECT COUNT(*) FROM chat_attempts WHERE run_id=?", (run_id,)).fetchone()[0] == 1
        assert connection.execute("SELECT status FROM task_runs WHERE run_id=?", (run_id,)).fetchone()[0] == "RUNNING"


def test_hf05_failed_classification_releases_same_run_and_timeout_recovers_abandoned_route(tmp_path: Path, monkeypatch) -> None:
    from datetime import datetime, timedelta, timezone

    from opspilot.domain.task_control import next_worker_run

    db = tmp_path / "hf05-failure-timeout.sqlite3"
    reset_fixture(db, "S1_POS")
    session_id, task_id, _, _ = _diagnosed_task(db)
    app = create_app(db_path=db, start_worker=False, credentials={"support-a": PASSWORD},
                     expected_origin=ORIGIN, heartbeat_seconds=0.05)
    monkeypatch.setattr(
        "opspilot.domain.investigation_updates.classify_input",
        lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("test classifier failure")),
    )
    with TestClient(app, raise_server_exceptions=False) as client:
        login = client.post("/api/auth/login", headers={"Origin": ORIGIN},
                            json={"actor_id": "support-a", "password": PASSWORD})
        headers = {"Origin": ORIGIN, "X-CSRF-Token": login.json()["csrf_token"]}
        accepted = client.post(
            f"/api/sessions/{session_id}/messages",
            headers={**headers, "Idempotency-Key": "m4-c1-hf-01-hf05-failure"},
            json={"task_id": task_id, "input_kind": "CHAT_READONLY", "body": "请解释上一轮调查。"},
        )
        run_id, message_id = str(accepted.json()["run_id"]), str(accepted.json()["message_id"])
        failed = client.post(
            f"/api/tasks/{task_id}/investigation-updates/proposals",
            headers={**headers, "Idempotency-Key": message_id}, json={"source_message_id": message_id},
        )
        assert failed.status_code >= 400
    with connect(db) as connection:
        run = connection.execute("SELECT status,blocked_reason FROM task_runs WHERE run_id=?", (run_id,)).fetchone()
        assert str(run["status"]) == "QUEUED"
        assert run["blocked_reason"] is None
        assert connection.execute("SELECT COUNT(*) FROM chat_attempts WHERE run_id=?", (run_id,)).fetchone()[0] == 0
    assert next_worker_run(db)["run_id"] == run_id

    # A route whose API caller disappeared before classification is released after the bounded timeout.
    second = _new_user_message(
        db, session_id, task_id, body="无人再补充分类结果的消息。", suffix="hf05-timeout",
    )
    with connect(db) as connection:
        connection.execute(
            "UPDATE task_runs SET blocked_reason='UPDATE_CLASSIFICATION_PENDING',created_at=? WHERE run_id=?",
            ((datetime.now(timezone.utc) - timedelta(minutes=3)).isoformat(), str(second["run_id"])),
        )
    recovered = next_worker_run(db)
    assert recovered is not None and recovered["run_id"] == second["run_id"]
    assert str(recovered["blocked_reason"] or "") == ""
    claim_task_run(db, trusted_identity(db, "support-a"), str(second["run_id"]))


def test_hf05_critical_correction_confirmation_and_cancellation_keep_existing_flow(tmp_path: Path, monkeypatch) -> None:
    from opspilot.domain.investigation_updates import cancel_assessment, confirm_assessment
    from opspilot.domain.task_control import next_worker_run

    db = tmp_path / "hf05-correction-route.sqlite3"
    reset_fixture(db, "S1_POS")
    session_id, task_id, _, _ = _diagnosed_task(db)
    app = create_app(db_path=db, start_worker=False, credentials={"support-a": PASSWORD},
                     expected_origin=ORIGIN, heartbeat_seconds=0.05)
    monkeypatch.setattr(
        "opspilot.domain.investigation_updates.classify_input",
        lambda **_kwargs: {"intent": "CRITICAL_CORRECTION", "change_summary": "修正真实订单状态", "readonly_action": "EXPLAIN"},
    )
    with TestClient(app, raise_server_exceptions=False) as client:
        login = client.post("/api/auth/login", headers={"Origin": ORIGIN},
                            json={"actor_id": "support-a", "password": PASSWORD})
        identity = trusted_identity(db, "support-a")
        headers = {"Origin": ORIGIN, "X-CSRF-Token": login.json()["csrf_token"]}
        accepted = client.post(
            f"/api/sessions/{session_id}/messages",
            headers={**headers, "Idempotency-Key": "m4-c1-hf-01-hf05-correction"},
            json={"task_id": task_id, "input_kind": "CHAT_READONLY", "body": "之前写错了，订单确实已经完成。"},
        )
        source_id, chat_run_id = str(accepted.json()["message_id"]), str(accepted.json()["run_id"])
        classified = client.post(
            f"/api/tasks/{task_id}/investigation-updates/proposals",
            headers={**headers, "Idempotency-Key": source_id}, json={"source_message_id": source_id},
        )
        assert classified.status_code == 200, classified.text
        assessment = classified.json()
        assert assessment["proposal"]["status"] == "PENDING_CONFIRMATION"
        assert next_worker_run(db) is None
        control_before = int(assessment["expected_control_revision"])
        cancelled = cancel_assessment(
            db, identity, task_id=task_id, proposal_id=str(assessment["assessment_id"]),
            operation_id=str(assessment["operation_id"]), idempotency_key=str(assessment["operation_id"]),
        )
        assert cancelled["status"] == "CANCELLED"
        assert next_worker_run(db)["run_id"] == chat_run_id
        claim_task_run(db, identity, chat_run_id)

        # A second message confirms the same frozen proposal flow and blocks its unused Chat Run.
        confirm_message = client.post(
            f"/api/sessions/{session_id}/messages",
            headers={**headers, "Idempotency-Key": "m4-c1-hf-01-hf05-confirm-correction"},
            json={"task_id": task_id, "input_kind": "CHAT_READONLY", "body": "实际主体仍是 principal-async-a，请重新核验。"},
        )
        source2 = str(confirm_message.json()["message_id"])
        classified2 = client.post(
            f"/api/tasks/{task_id}/investigation-updates/proposals",
            headers={**headers, "Idempotency-Key": source2}, json={"source_message_id": source2},
        )
        proposal2 = classified2.json()["proposal"]
        confirmed = confirm_assessment(
            db, identity, task_id=task_id, proposal_id=str(proposal2["proposal_id"]),
            expected_control_revision=int(proposal2["expected_control_revision"]),
            operation_id=str(proposal2["operation_id"]), idempotency_key=str(proposal2["operation_id"]),
        )
        assert confirmed["status"] == "ACCEPTED"
        with connect(db) as connection:
            blocked_chat = connection.execute(
                "SELECT status,blocked_reason FROM task_runs WHERE run_id=?", (confirm_message.json()["run_id"],),
            ).fetchone()
            control_after = int(connection.execute(
                "SELECT control_revision FROM task_controls WHERE task_id=?", (task_id,),
            ).fetchone()[0])
        assert str(blocked_chat["status"]) == "BLOCKED"
        assert str(blocked_chat["blocked_reason"]) == "CORRECTION_CONFIRMED"
        assert control_after == control_before + 1


def test_hf02_later_chat_turn_excludes_answer_after_its_knowledge_source_becomes_stale(
    tmp_path: Path, monkeypatch,
) -> None:
    from opspilot.domain.chat import complete_chat_attempt, persist_chat_chunk, prepare_chat_attempt
    from opspilot.domain.task_control import register_worker_owner
    import opspilot.domain.s3_assets as assets

    db = tmp_path / "hf02-chat-lineage.sqlite3"
    reset_fixture(db, "S1_POS")
    session_id, task_id, _, _ = _diagnosed_task(db)
    prior = _persist_previous_followup(db, session_id, task_id, suffix="chat-lineage")
    app = create_app(db_path=db, start_worker=False, credentials={"support-a": PASSWORD},
                     expected_origin=ORIGIN, heartbeat_seconds=0.05)
    monkeypatch.setattr(
        "opspilot.domain.investigation_updates.classify_input",
        lambda **_kwargs: {"intent": "FOLLOW_UP", "change_summary": "", "readonly_action": "EXPLAIN"},
    )
    identity = trusted_identity(db, "support-a")
    with TestClient(app, raise_server_exceptions=False) as client:
        login = client.post("/api/auth/login", headers={"Origin": ORIGIN},
                            json={"actor_id": "support-a", "password": PASSWORD})
        assert login.status_code == 200, login.text
        headers = {"Origin": ORIGIN, "X-CSRF-Token": login.json()["csrf_token"]}
        first = client.post(
            f"/api/sessions/{session_id}/messages",
            headers={**headers, "Idempotency-Key": "m4-c1-hf-01-hf02-answer-lineage"},
            json={"task_id": task_id, "input_kind": "CHAT_READONLY", "body": "解释刚才引用的协议。"},
        )
        assert first.status_code == 202, first.text
        first_run_id, first_message_id = str(first.json()["run_id"]), str(first.json()["message_id"])
        routed = client.post(
            f"/api/tasks/{task_id}/investigation-updates/proposals",
            headers={**headers, "Idempotency-Key": first_message_id},
            json={"source_message_id": first_message_id},
        )
        assert routed.status_code == 200, routed.text
        claim_task_run(db, identity, first_run_id)
        register_worker_owner(db, "hf02-lineage-worker", 4202)
        first_context = prepare_chat_attempt(db, first_run_id, "hf02-lineage-worker", "hf02-lineage-test")
        answer_text = "This answer depends on the currently applicable receiver-ack-contract-v2."
        persist_chat_chunk(db, "hf02-lineage-worker", str(first_context["attempt_id"]), 1, answer_text)
        answer = complete_chat_attempt(
            db, "hf02-lineage-worker", str(first_context["attempt_id"]), answer_text,
            provider_response_id="hf02-lineage-provider-response", input_tokens=20, output_tokens=12,
            total_tokens=32,
        )
        answer_message_id = str(answer["message_id"])

        existing = assets.load_knowledge(contract_version=2)
        replaced = [dict(item) for item in existing]
        document = next(item for item in replaced if item["document_id"] == prior["document_id"])
        document.update({"version": "hf02-replacement-v3", "digest": "e" * 64})
        monkeypatch.setattr(assets, "load_knowledge", lambda *, contract_version=None: replaced)

        second = client.post(
            f"/api/sessions/{session_id}/messages",
            headers={**headers, "Idempotency-Key": "m4-c1-hf-01-hf02-after-stale"},
            json={"task_id": task_id, "input_kind": "CHAT_READONLY", "body": "刚才那条协议现在仍适用吗？"},
        )
        assert second.status_code == 202, second.text
        second_run_id, second_message_id = str(second.json()["run_id"]), str(second.json()["message_id"])
        second_route = client.post(
            f"/api/tasks/{task_id}/investigation-updates/proposals",
            headers={**headers, "Idempotency-Key": second_message_id},
            json={"source_message_id": second_message_id},
        )
        assert second_route.status_code == 200, second_route.text
        assert second_route.json()["follow_up_action"] == "EXPLAIN"
        claim_task_run(db, identity, second_run_id)
        with connect(db) as connection:
            run = connection.execute("SELECT * FROM task_runs WHERE run_id=?", (second_run_id,)).fetchone()
            prepared = _prepare_context(connection, run, "hf02-lineage-test", db)

    assert not any(item["role"] == "assistant" and answer_text in item["content"]
                   for item in prepared["messages"])
    assert any(
        item.get("message_id") == answer_message_id
        and item.get("reason") == "PRIOR_READONLY_FOLLOWUP_SOURCE_INVALID"
        for item in prepared["excluded_sources"]
    )
