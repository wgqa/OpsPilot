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
