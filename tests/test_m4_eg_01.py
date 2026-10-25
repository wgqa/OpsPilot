from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from opspilot.domain.database import connect
from opspilot.domain.task_control import (
    admit_task_message,
    finish_task_run,
    register_worker_owner,
    trusted_identity,
)
from test_m4_03_s3 import _evidence, _facts, _prepared_task


_CHAT_OWNER = "eg01-chat-worker"


def _make_sla_chat_context(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    receiver_status: str | None,
    queue_age_seconds: int = 60,
    order_id: str,
) -> tuple[Path, dict[str, object], dict[str, object]]:
    import opspilot.domain.s3 as s3
    from opspilot.domain.s3 import persist_s3_diagnosis
    from test_m4_03_s3 import _task

    db, identity, task = _prepared_task(
        tmp_path, "DELIVERED_PENDING", order_id,
        queue_age_seconds=queue_age_seconds, processing_sla_seconds=300,
    )
    setup_now = datetime.now(timezone.utc)
    accepted_at = (setup_now - timedelta(seconds=queue_age_seconds)).isoformat().replace("+00:00", "Z")
    with connect(db) as connection:
        connection.execute(
            "UPDATE s3_receivers SET accepted_at=?, status=? WHERE order_id=?",
            (accepted_at, receiver_status or "QUEUED", order_id),
        )
        # The fixture's real HTTP 202 and durable queue record stay correlated.
        row = connection.execute(
            "SELECT transport_response_json FROM s3_deliveries WHERE order_id=?", (order_id,),
        ).fetchone()
        response = json.loads(str(row["transport_response_json"]))
        response["accepted_at"] = accepted_at
        from opspilot.domain.d2 import canonical_json, digest_json
        connection.execute(
            "UPDATE s3_deliveries SET transport_response_json=?, response_digest=? WHERE order_id=?",
            (canonical_json(response), digest_json(response), order_id),
        )

    order, delivery, receiver = _facts(db, task)
    evidence_ids = [
        _evidence(db, task, "get_order_status", order),
        _evidence(db, task, "get_callback_delivery", delivery),
    ]
    if receiver_status is not None:
        evidence_ids.append(_evidence(db, task, "get_receiver_processing", receiver))
    # Keep all persisted observations in the past while applying one consistent
    # deterministic clock to both TTL validation and the SLA decision.
    decision_now = datetime.now(timezone.utc) + timedelta(seconds=5)
    monkeypatch.setattr(s3, "_now", lambda: decision_now)
    diagnosis = persist_s3_diagnosis(
        db, str(task["task_id"]), str(task["run_id"]), evidence_ids,
        stop_reason="EG01_NO_CURRENT_RECEIVER_STATE" if receiver_status is None else None,
    )
    finish_task_run(db, identity, str(task["run_id"]), "SUCCEEDED")
    register_worker_owner(db, _CHAT_OWNER, 6201)
    accepted = admit_task_message(
        db, identity, session_id=str(task["session_id"]), task_id=str(task["task_id"]),
        input_kind="CHAT_READONLY", body="同一事件现在是否处理完成？",
        idempotency_key=f"eg01-chat-{order_id}",
    )
    from opspilot.domain.task_control import claim_task_run
    claim_task_run(db, identity, str(accepted["run_id"]))
    from opspilot.domain.chat import prepare_chat_attempt
    prepared = prepare_chat_attempt(db, str(accepted["run_id"]), _CHAT_OWNER, "eg01-deterministic")
    assert diagnosis["run_id"] == task["run_id"]
    return db, task, prepared


def _prompt_text(prepared: dict[str, object]) -> str:
    return "\n".join(str(item["content"]) for item in prepared["messages"])


@pytest.mark.parametrize(
    ("case_id", "receiver_status", "queue_age", "expected_current_state", "expected_direction"),
    [
        ("SLA-PROCESSED-EARLY", "PROCESSED", 60, "PROCESSED", "NO_FURTHER_ACTION"),
        ("SLA-QUEUED-IN-WINDOW", "QUEUED", 60, "QUEUED", "WAIT_FOR_RECEIVER_PROCESSING"),
        ("SLA-QUEUED-OVERDUE", "QUEUED", 360, "QUEUED", "CONTACT_RECEIVER_OPERATOR"),
        ("SLA-202-UNKNOWN", None, 60, None, "EVIDENCE_INSUFFICIENT"),
    ],
)
def test_sla_chat_outbound_context_carries_correct_same_event_rule(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    case_id: str,
    receiver_status: str | None,
    queue_age: int,
    expected_current_state: str | None,
    expected_direction: str,
) -> None:
    db, task, prepared = _make_sla_chat_context(
        tmp_path, monkeypatch, receiver_status=receiver_status,
        queue_age_seconds=queue_age, order_id=case_id.lower(),
    )
    prompt = _prompt_text(prepared)
    with connect(db) as connection:
        diagnosis = connection.execute(
            "SELECT body_json FROM s3_diagnoses WHERE task_id=?", (task["task_id"],),
        ).fetchone()
    gate = json.loads(str(diagnosis["body_json"]))["gate"]
    assert gate["handling_direction"] == expected_direction
    assert expected_current_state is None or expected_current_state in prompt
    assert "SLA applies only to a same-event receiver that is still QUEUED" in prompt
    assert "same-event current PROCESSED proves completion even before the SLA deadline" in prompt
    assert "HTTP 202 alone proves acceptance only; without current same-event receiver evidence, state is UNKNOWN" in prompt
    assert "do not borrow another event's state" in prompt.casefold()


def test_receiver_ack_knowledge_has_unambiguous_processed_before_sla_rule() -> None:
    from opspilot.domain.s3_assets import load_knowledge

    document = next(
        item for item in load_knowledge(contract_version=2)
        if item["document_id"] == "receiver-ack-contract-v2"
    )
    assert document["version"] == "2.1.0"
    content = str(document["content"])
    assert "`PROCESSED` is sufficient to prove completion even before the SLA deadline" in content
    assert "SLA only sets the handling direction for a same-event receiver that remains `QUEUED`" in content
    assert "HTTP 202 alone" in content and "UNKNOWN" in content


def test_s3_memory_is_in_actual_investigator_provider_message_and_off_is_absent(tmp_path: Path) -> None:
    from langchain_core.messages import AIMessage
    from opspilot.domain.episodic_memory import confirm_memory, create_memory_candidate
    from opspilot.domain.s3 import persist_s3_diagnosis
    from opspilot.s3_investigation import S3Nodes
    from test_m4_03_s3 import _task

    class CapturingModel:
        def __init__(self) -> None:
            self.messages: list[object] = []

        def bind_tools(self, *_args, **_kwargs):
            return self

        async def ainvoke(self, messages):
            self.messages.append(messages)
            return AIMessage(content="I will verify the target Task's own current event before concluding.")

    db, identity, source = _prepared_task(
        tmp_path, "DELIVERY_FAILED", "eg01-memory-source", attempt_count=3,
        max_attempts=3, retry_state="EXHAUSTED",
    )
    order, delivery, _receiver = _facts(db, source)
    source_evidence = [
        _evidence(db, source, "get_order_status", order),
        _evidence(db, source, "get_callback_delivery", delivery),
    ]
    source_diagnosis = persist_s3_diagnosis(
        db, str(source["task_id"]), str(source["run_id"]), source_evidence,
    )
    finish_task_run(db, identity, str(source["run_id"]), "SUCCEEDED")
    candidate = create_memory_candidate(
        db, str(source["task_id"]), "support-a", idempotency_key="eg01-memory-candidate",
    )
    active = confirm_memory(
        db, str(candidate["memory_id"]), "approver-a", idempotency_key="eg01-memory-confirm",
    )

    from opspilot.domain.s3 import prepare_s3_fixture
    prepare_s3_fixture(
        db, "DELIVERED_PENDING", order_id="eg01-memory-target", queue_age_seconds=60,
    )
    _, target = _task(
        db, "eg01-memory-target",
        text="A similar callback delivery failure happened before. Please investigate this retry and delivery problem.",
    )
    assert target["task_id"] != source["task_id"]
    from opspilot.domain.task_control import apply_pending_critical_inputs, claim_task_run
    claim_task_run(db, identity, str(target["run_id"]))
    apply_pending_critical_inputs(db, identity, str(target["run_id"]))
    model_on = CapturingModel()
    node_on = S3Nodes(
        db, str(target["task_id"]), str(target["run_id"]), model_on,
        "eg01-deterministic", None, [], memory_enabled=True,
    )
    call_id, _calls, _text = asyncio.run(node_on.model_call({"evidence_ids": [], "diagnosis_draft": {}}))
    sent = "\n".join(str(item.content) for item in model_on.messages[0])
    assert str(active["memory_id"]) in sent
    assert str(source["task_id"]) in sent
    assert "historical_episodic_method_only" in sent
    assert "historical_episodic_method_only" in sent and "current_mcp_evidence" in sent

    model_off = CapturingModel()
    node_off = S3Nodes(
        db, str(target["task_id"]), str(target["run_id"]), model_off,
        "eg01-deterministic", None, [], memory_enabled=False,
    )
    asyncio.run(node_off.model_call({"evidence_ids": [], "diagnosis_draft": {}}))
    off_sent = "\n".join(str(item.content) for item in model_off.messages[0])
    assert str(active["memory_id"]) not in off_sent
    assert "EVALUATION_MEMORY_OFF" in off_sent
    assert source_diagnosis["outcome"] == "CALLBACK_DELIVERY_FAILED"
    with connect(db) as connection:
        provenance = connection.execute(
            "SELECT selected_memories_json FROM d5_context_provenance WHERE call_id=?", (call_id,),
        ).fetchone()
    assert str(active["memory_id"]) in str(provenance["selected_memories_json"])
