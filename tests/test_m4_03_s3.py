from __future__ import annotations

import threading
from pathlib import Path

import pytest


def _task(db: Path, order_id: str, *, text: str = "订单接口返回 200，但下游没有收到异步回调。"):
    from opspilot.domain.task_control import (
        create_session, create_task_with_initial_run, trusted_identity,
    )

    identity = trusted_identity(db, "support-a")
    session = create_session(db, identity)
    task = create_task_with_initial_run(
        db, identity, session_id=str(session["session_id"]),
        service_id="orders-async-demo", integration_id="async-integration-a",
        ticket_id="S3-M403", initial_message=text, idempotency_key=f"create-{order_id}-{text[:12]}",
        s3_order_id=order_id,
    )
    return identity, task


def _evidence(db: Path, task: dict[str, object], tool: str, result: dict[str, object]) -> str:
    from s3_observation_support import record_s3_observation
    return str(record_s3_observation(db, task, tool, result)["evidence_id"])


def _facts(db: Path, task: dict[str, object]):
    from opspilot.domain.api import make_server
    from opspilot.domain.s3 import (
        get_callback_delivery_fact, get_order_status_fact, get_receiver_processing_fact,
    )

    server = make_server(db, "tenant-a", "127.0.0.1", 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        root = f"http://127.0.0.1:{server.server_port}"
        return (
            get_order_status_fact(db, str(task["task_id"]), root),
            get_callback_delivery_fact(db, str(task["task_id"])),
            get_receiver_processing_fact(db, str(task["task_id"])),
        )
    finally:
        server.shutdown()
        thread.join()
        server.server_close()


def _prepared_task(tmp_path: Path, state: str, order_id: str, **options):
    from opspilot.domain.database import reset_fixture
    from opspilot.domain.s3 import prepare_s3_fixture

    db = tmp_path / "m403.sqlite3"
    reset_fixture(db, "S1_POS")
    prepare_s3_fixture(db, state, order_id=order_id, **options)
    identity, task = _task(db, order_id)
    return db, identity, task


def test_owner_selects_only_registered_orders_and_task_binding_pins_one(tmp_path: Path):
    from opspilot.domain.s3 import list_s3_order_resources, prepare_s3_fixture
    from opspilot.domain.database import connect, reset_fixture
    from opspilot.domain.task_control import TaskControlError, trusted_identity

    db = tmp_path / "orders.sqlite3"
    reset_fixture(db, "S1_POS")
    prepare_s3_fixture(db, "PROCESSING", order_id="async-order")
    prepare_s3_fixture(db, "DELIVERY_FAILED", order_id="async-order-2")
    identity = trusted_identity(db, "support-a")
    listed = list_s3_order_resources(db, identity)
    assert {item["order_id"] for item in listed} == {"async-order", "async-order-2"}
    _, first = _task(db, "async-order")
    _, second = _task(db, "async-order-2")
    from opspilot.domain.s3 import get_s3_binding
    with connect(db) as connection:
        assert get_s3_binding(connection, str(first["task_id"]))["order_id"] == "async-order"
        assert get_s3_binding(connection, str(second["task_id"]))["order_id"] == "async-order-2"
    with pytest.raises(TaskControlError):
        _task(db, "arbitrary-order-from-user-text")


def test_knowledge_retrieval_is_version_scoped_and_rejects_out_of_domain_hits():
    from opspilot.domain.s3_assets import search_knowledge

    unrelated = "API authentication credential rotation and scope policy version"
    for method in ("lexical-v1", "bm25-lite-v1"):
        assert search_knowledge(unrelated, contract_version=1, method=method) == []
        assert search_knowledge(unrelated, contract_version=2, method=method) == []
    for version in (1, 2):
        ranked = search_knowledge("callback receiver 202 accepted queue", limit=8,
                                  contract_version=version, method="bm25-lite-v1")
        assert ranked
        assert all(version in item["contract_versions"] for item in ranked)
    with pytest.raises(ValueError):
        search_knowledge("callback", limit=9)


def test_specific_receiver_ack_query_ranks_the_v2_202_contract_first():
    from opspilot.domain.s3_assets import search_knowledge

    ranked = search_knowledge(
        "HTTP 202 receiver acknowledgement", limit=1, contract_version=2,
        method="bm25-lite-v1",
    )
    assert ranked[0]["document_id"] == "receiver-ack-contract-v2"


@pytest.mark.parametrize(("state", "options", "expected_outcome", "expected_direction", "handoff"), [
    ("DELIVERY_FAILED", {"attempt_count": 1, "max_attempts": 3, "retry_state": "SCHEDULED"},
     "CALLBACK_DELIVERY_FAILED", "WAIT_FOR_SCHEDULED_RETRY", False),
    ("DELIVERY_FAILED", {"attempt_count": 3, "max_attempts": 3, "retry_state": "EXHAUSTED"},
     "CALLBACK_DELIVERY_FAILED", "CONTACT_CALLBACK_OPERATOR", True),
    ("DELIVERED_PENDING", {"queue_age_seconds": 60, "processing_sla_seconds": 300},
     "RECEIVER_PROCESSING_UNCONFIRMED", "WAIT_FOR_RECEIVER_PROCESSING", False),
    ("DELIVERED_PENDING", {"queue_age_seconds": 1800, "processing_sla_seconds": 300},
     "RECEIVER_PROCESSING_UNCONFIRMED", "CONTACT_RECEIVER_OPERATOR", True),
])
def test_current_event_reason_and_retry_or_receiver_sla_choose_direction(
    tmp_path: Path, state: str, options: dict[str, object], expected_outcome: str,
    expected_direction: str, handoff: bool,
):
    from opspilot.domain.s3 import evaluate_s3_gate

    db, _, task = _prepared_task(tmp_path, state, "async-order-2", **options)
    order, delivery, receiver = _facts(db, task)
    ids = [_evidence(db, task, "get_order_status", order)]
    if state == "DELIVERY_FAILED":
        ids.append(_evidence(db, task, "get_callback_delivery", delivery))
    else:
        ids.extend([
            _evidence(db, task, "get_callback_delivery", delivery),
            _evidence(db, task, "get_receiver_processing", receiver),
        ])
    gate = evaluate_s3_gate(db, str(task["task_id"]), ids)
    assert gate["outcome"] == expected_outcome
    assert gate["handling_direction"] == expected_direction
    assert gate["handoff_allowed"] is handoff
    assert gate["recovered"] is False


def test_missing_server_reason_fields_cannot_produce_contact_direction(tmp_path: Path):
    from opspilot.domain.database import connect
    from opspilot.domain.s3 import evaluate_s3_gate

    db, _, task = _prepared_task(
        tmp_path, "DELIVERY_FAILED", "async-order-2", attempt_count=3,
        max_attempts=3, retry_state="EXHAUSTED",
    )
    # A transport status without a persisted failure reason is not enough to
    # tell an operator what to do, even when the response body says 503.
    with connect(db) as connection:
        connection.execute("UPDATE s3_deliveries SET failure_code=NULL WHERE order_id='async-order-2'")
    order, delivery, _ = _facts(db, task)
    ids = [_evidence(db, task, "get_order_status", order), _evidence(db, task, "get_callback_delivery", delivery)]
    gate = evaluate_s3_gate(db, str(task["task_id"]), ids)
    assert gate["decision"] == "NEED_MORE"
    assert gate["outcome"] is None
    assert gate["handoff_allowed"] is False
    assert gate["handling_direction"] == "EVIDENCE_INSUFFICIENT"


def test_s3_diagnosis_keeps_task_correctable_and_new_run_reprobes_same_resource(tmp_path: Path):
    from opspilot.domain.database import connect, reset_fixture
    from opspilot.domain.s3 import prepare_s3_fixture, persist_s3_diagnosis, get_s3_binding
    from opspilot.domain.task_control import (
        admit_task_message, apply_pending_critical_inputs, claim_task_run,
        finish_task_run, trusted_identity,
    )

    db = tmp_path / "correction.sqlite3"
    reset_fixture(db, "S1_POS")
    prepare_s3_fixture(db, "PROCESSING", order_id="async-order-2")
    identity, task = _task(db, "async-order-2")
    claim_task_run(db, identity, str(task["run_id"]))
    apply_pending_critical_inputs(db, identity, str(task["run_id"]))
    order, _, _ = _facts(db, task)
    evidence_id = _evidence(db, task, "get_order_status", order)
    persist_s3_diagnosis(db, str(task["task_id"]), str(task["run_id"]), [evidence_id])
    finish_task_run(db, identity, str(task["run_id"]), "SUCCEEDED")
    with connect(db) as connection:
        status = connection.execute("SELECT status FROM task_bindings WHERE task_id=?", (task["task_id"],)).fetchone()[0]
        revision = connection.execute("SELECT control_revision FROM task_controls WHERE task_id=?", (task["task_id"],)).fetchone()[0]
    assert status == "WAITING_HANDOFF"
    accepted = admit_task_message(
        db, identity, session_id=str(task["session_id"]), task_id=str(task["task_id"]),
        input_kind="CORRECT_TASK_INPUT", body="我把之前的故障描述补充为：订单还在处理中。",
        idempotency_key="m403-correction", expected_control_revision=int(revision),
    )
    assert accepted["run_id"] != task["run_id"]
    claim_task_run(db, identity, str(accepted["run_id"]))
    applied = apply_pending_critical_inputs(db, identity, str(accepted["run_id"]))
    assert applied["inputs"]
    with connect(db) as connection:
        assert get_s3_binding(connection, str(task["task_id"]))["order_id"] == "async-order-2"


def test_confirmed_s3_handoff_is_atomic_idempotent_and_separate_from_s2_scope(tmp_path: Path):
    from opspilot.domain.database import connect, reset_fixture
    from opspilot.domain.s3 import prepare_s3_fixture, persist_s3_diagnosis
    from opspilot.domain.s3_handoff import get_s3_handoff_outcome, submit_s3_handoff
    from opspilot.domain.task_control import claim_task_run, apply_pending_critical_inputs, finish_task_run

    db, identity, task = _prepared_task(
        tmp_path, "DELIVERY_FAILED", "async-order-2", attempt_count=3,
        max_attempts=3, retry_state="EXHAUSTED",
    )
    claim_task_run(db, identity, str(task["run_id"]))
    apply_pending_critical_inputs(db, identity, str(task["run_id"]))
    order, delivery, _ = _facts(db, task)
    ids = [_evidence(db, task, "get_order_status", order), _evidence(db, task, "get_callback_delivery", delivery)]
    diagnosis = persist_s3_diagnosis(db, str(task["task_id"]), str(task["run_id"]), ids)
    finish_task_run(db, identity, str(task["run_id"]), "SUCCEEDED")
    before = get_s3_handoff_outcome(db, str(task["task_id"]), identity)
    assert before["business_outcome"] == "HANDOFF_READY"
    assert before["handoff_allowed"] is True
    assert before["diagnosis_receipt"]["handoff_allowed"] is True
    with connect(db) as connection:
        revision = int(connection.execute("SELECT control_revision FROM task_controls WHERE task_id=?", (task["task_id"],)).fetchone()[0])
    request = {
        "task_id": str(task["task_id"]), "operation_id": "s3-handoff-once",
        "diagnosis_receipt_id": str(diagnosis["receipt_id"]),
        "diagnosis_digest": str(diagnosis["digest"]), "expected_control_revision": revision,
    }
    first = submit_s3_handoff(db, identity, **request)
    replay = submit_s3_handoff(db, identity, **request)
    assert first["business_outcome"] == "HANDOFF_ACCEPTED"
    assert replay["receipt_id"] == first["receipt_id"] and replay["replayed"] is True
    persisted = get_s3_handoff_outcome(db, str(task["task_id"]), identity)
    assert persisted["handoff_receipt"]["receipt_id"] == first["receipt_id"]
    from opspilot.domain.chat import _current_task_state
    with connect(db) as connection:
        chat_state = _current_task_state(connection, str(task["task_id"]))
    assert chat_state["s3_handoff"]["business_outcome"] == "HANDOFF_ACCEPTED"
    assert chat_state["s3_handoff"]["receipt_id"] == first["receipt_id"]
    assert chat_state["s3_handoff"]["order_recovered"] is False
    with connect(db) as connection:
        assert connection.execute("SELECT COUNT(*) FROM s3_handoff_queue_entries WHERE task_id=?", (task["task_id"],)).fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM s3_handoff_receipts WHERE task_id=?", (task["task_id"],)).fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM s2_handoff_receipts WHERE task_id=?", (task["task_id"],)).fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM d3_action_ledgers WHERE task_id=?", (task["task_id"],)).fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM domain_outbox WHERE task_id=? AND event_kind='S3_HANDOFF_ACCEPTED'", (task["task_id"],)).fetchone()[0] == 1


def test_s3_handoff_rollback_and_response_loss_reconcile_once(tmp_path: Path, monkeypatch):
    import opspilot.domain.s3_handoff as handoff
    from opspilot.domain.database import connect
    from opspilot.domain.s3 import persist_s3_diagnosis
    from opspilot.domain.s3_handoff import get_s3_handoff_outcome, submit_s3_handoff
    from opspilot.domain.task_control import claim_task_run, apply_pending_critical_inputs, finish_task_run

    db, identity, task = _prepared_task(
        tmp_path, "DELIVERY_FAILED", "async-order-2", attempt_count=3,
        max_attempts=3, retry_state="EXHAUSTED",
    )
    claim_task_run(db, identity, str(task["run_id"]))
    apply_pending_critical_inputs(db, identity, str(task["run_id"]))
    order, delivery, _ = _facts(db, task)
    ids = [_evidence(db, task, "get_order_status", order), _evidence(db, task, "get_callback_delivery", delivery)]
    diagnosis = persist_s3_diagnosis(db, str(task["task_id"]), str(task["run_id"]), ids)
    finish_task_run(db, identity, str(task["run_id"]), "SUCCEEDED")
    with connect(db) as connection:
        revision = int(connection.execute("SELECT control_revision FROM task_controls WHERE task_id=?", (task["task_id"],)).fetchone()[0])
    request = {
        "task_id": str(task["task_id"]), "operation_id": "s3-handoff-response-loss",
        "diagnosis_receipt_id": str(diagnosis["receipt_id"]),
        "diagnosis_digest": str(diagnosis["digest"]), "expected_control_revision": revision,
    }

    def fail(name):
        if name == "after_queue_before_receipt":
            raise RuntimeError("injected pre-commit queue failure")

    monkeypatch.setattr(handoff, "_FAILPOINT", fail)
    with pytest.raises(RuntimeError, match="injected pre-commit"):
        submit_s3_handoff(db, identity, **request)
    with connect(db) as connection:
        assert connection.execute("SELECT COUNT(*) FROM s3_handoff_queue_entries WHERE task_id=?", (task["task_id"],)).fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM s3_handoff_receipts WHERE task_id=?", (task["task_id"],)).fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM commands WHERE command_kind='S3_HANDOFF_SUBMIT' AND target_ref LIKE ?", (f"{task['task_id']}:%",)).fetchone()[0] == 0
        assert connection.execute("SELECT status FROM task_bindings WHERE task_id=?", (task["task_id"],)).fetchone()[0] == "WAITING_HANDOFF"

    def lose_response(name):
        if name == "after_commit_before_http_response":
            raise TimeoutError("injected lost HTTP response after commit")

    monkeypatch.setattr(handoff, "_FAILPOINT", lose_response)
    with pytest.raises(TimeoutError, match="lost HTTP response"):
        submit_s3_handoff(db, identity, **request)
    persisted = get_s3_handoff_outcome(db, str(task["task_id"]), identity)
    assert persisted["business_outcome"] == "HANDOFF_ACCEPTED"
    receipt_id = persisted["handoff_receipt"]["receipt_id"]

    monkeypatch.setattr(handoff, "_FAILPOINT", None)
    same_operation = submit_s3_handoff(db, identity, **request)
    different_operation = submit_s3_handoff(db, identity, **{**request, "operation_id": "s3-handoff-second-tab"})
    assert same_operation["receipt_id"] == receipt_id and same_operation["replayed"] is True
    assert different_operation["receipt_id"] == receipt_id and different_operation["replayed"] is True
    with connect(db) as connection:
        assert connection.execute("SELECT COUNT(*) FROM s3_handoff_queue_entries WHERE task_id=?", (task["task_id"],)).fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM s3_handoff_receipts WHERE task_id=?", (task["task_id"],)).fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM domain_outbox WHERE task_id=? AND event_kind='S3_HANDOFF_ACCEPTED'", (task["task_id"],)).fetchone()[0] == 1


def test_order_resource_api_lists_only_authorized_support_resources(tmp_path: Path):
    from fastapi.testclient import TestClient
    from opspilot.domain.database import reset_fixture
    from opspilot.domain.s3 import prepare_s3_fixture
    from opspilot.web.app import create_app
    from test_m4_01_dialogue_updates import PASSWORDS, _login

    db, _, _ = _prepared_task(tmp_path, "PROCESSING", "async-order")
    prepare_s3_fixture(db, "DELIVERED_PENDING", order_id="async-order-2", tenant_id="tenant-a", contract_version=2)
    # Seed a second tenant with an identically named private order. It must not
    # appear in tenant-a's server-side selection catalog.
    prepare_s3_fixture(db, "PROCESSING", order_id="tenant-b-only", tenant_id="tenant-b")
    app = create_app(db_path=db, start_worker=False, credentials=PASSWORDS, expected_origin="http://testserver")
    with TestClient(app, raise_server_exceptions=False) as client:
        support = _login(client, "support-a")
        response = client.get("/api/s3/order-resources", headers=support)
        assert response.status_code == 200
        items = response.json()["items"]
        assert {item["order_id"] for item in items} == {"async-order", "async-order-2"}
        assert all(item["selection_status"] == "REGISTERED_AND_READ_AUTHORIZED" for item in items)
        approver = _login(client, "approver-a")
        denied = client.get("/api/s3/order-resources", headers=approver)
        assert denied.status_code == 403
        assert "tenant-b-only" not in response.text


def test_episodic_memory_relevance_is_method_only_and_revocation_removes_it(tmp_path: Path):
    from opspilot.domain.database import connect, reset_fixture
    from opspilot.domain.episodic_memory import (
        confirm_memory, create_memory_candidate, revoke_memory, select_applicable_memories,
    )
    from opspilot.domain.s3 import persist_s3_diagnosis, prepare_s3_fixture
    from opspilot.domain.task_control import apply_pending_critical_inputs, claim_task_run, finish_task_run

    db = tmp_path / "memory-relevance.sqlite3"
    reset_fixture(db, "S1_POS")
    prepare_s3_fixture(db, "PROCESSING", order_id="async-order")
    source_identity, source = _task(db, "async-order")
    claim_task_run(db, source_identity, str(source["run_id"]))
    apply_pending_critical_inputs(db, source_identity, str(source["run_id"]))
    order, _, _ = _facts(db, source)
    source_evidence = _evidence(db, source, "get_order_status", order)
    source_diagnosis = persist_s3_diagnosis(db, str(source["task_id"]), str(source["run_id"]), [source_evidence])
    assert source_diagnosis["outcome"] == "ORDER_PROCESSING"
    finish_task_run(db, source_identity, str(source["run_id"]), "SUCCEEDED")
    candidate = create_memory_candidate(
        db, str(source["task_id"]), "support-a", idempotency_key="m403-memory-candidate",
    )
    active = confirm_memory(
        db, str(candidate["memory_id"]), "approver-a", idempotency_key="m403-memory-confirm",
    )
    assert active["state"] == "ACTIVE"

    prepare_s3_fixture(db, "PROCESSING", order_id="async-order-2")
    _, target = _task(db, "async-order-2")
    assert source["task_id"] != target["task_id"]
    selected, excluded = select_applicable_memories(
        db, str(target["task_id"]), "async_callback",
        relevance_text="订单接口返回200，下游回调处理中。",
        current_s3_facts={"gate_outcome": "ORDER_PROCESSING", "order_status": "PROCESSING"},
    )
    assert [item["memory_id"] for item in selected] == [candidate["memory_id"]]
    assert selected[0]["relevance"]["reason"] == "S3_CURRENT_OUTCOME_MATCH"
    assert excluded == []
    irrelevant, rejected = select_applicable_memories(
        db, str(target["task_id"]), "async_callback", relevance_text="invoice billing reconciliation",
    )
    assert irrelevant == []
    assert any(item["reason"] == "MEMORY_IRRELEVANT_TO_CURRENT_CASE" for item in rejected)
    unrelated_chinese, rejected = select_applicable_memories(
        db, str(target["task_id"]), "async_callback",
        relevance_text="请核对本月供应商发票的开票抬头、税号和价税合计差异；这是财务账单问题。",
    )
    assert unrelated_chinese == []
    assert any(item["reason"] == "MEMORY_IRRELEVANT_TO_CURRENT_CASE" for item in rejected)
    conflict, rejected = select_applicable_memories(
        db, str(target["task_id"]), "async_callback", relevance_text="订单回调故障",
        current_s3_facts={"gate_outcome": "CALLBACK_DELIVERY_FAILED", "order_status": "COMPLETED"},
    )
    assert conflict == []
    assert any(item["reason"] == "CURRENT_EVIDENCE_CONFLICTS_WITH_MEMORY" for item in rejected)
    revoke_memory(db, str(candidate["memory_id"]), "approver-a", idempotency_key="m403-memory-revoke")
    revoked, rejected = select_applicable_memories(
        db, str(target["task_id"]), "async_callback",
        relevance_text="订单接口返回200，下游回调处理中。",
        current_s3_facts={"gate_outcome": "ORDER_PROCESSING", "order_status": "PROCESSING"},
    )
    assert revoked == []
    assert any(item["reason"] == "MEMORY_REVOKED" for item in rejected)
    with connect(db) as connection:
        assert connection.execute("SELECT COUNT(*) FROM s3_diagnoses WHERE task_id=?", (target["task_id"],)).fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM s2_handoff_receipts WHERE task_id=?", (target["task_id"],)).fetchone()[0] == 0
