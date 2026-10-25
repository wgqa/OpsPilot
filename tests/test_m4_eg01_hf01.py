from __future__ import annotations

import asyncio
import hashlib
import json
import os
import threading
from pathlib import Path
from uuid import uuid4

import pytest

from opspilot.domain.database import connect
from test_m4_03_s3 import _prepared_task


def _trace(record: dict[str, object]) -> None:
    trace_path = os.environ.get("OPSPILOT_HF01_TRACE_PATH")
    if trace_path:
        with open(trace_path, "a", encoding="utf-8") as stream:
            stream.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def _call_s3_tool(server, name: str, args: dict[str, object]):
    from mcp.server.mcpserver.context import Context
    from mcp.types import CallToolRequestParams

    context = Context(
        mcp_server=server,
        input_params=CallToolRequestParams(name=name, arguments=args),
    )
    return asyncio.run(server.call_tool(name, args, context))


def _observe_s3_tool(db: Path, task: dict[str, object], run_id: str, server, tool_name: str):
    from opspilot.domain.d2 import digest_json, finish_attempt, record_tool_observation, reserve_attempt
    from opspilot.domain.investigation_context import load_investigation_context
    from opspilot.domain.schemas import D2ToolFact

    task_id = str(task["task_id"])
    args = {"reason": "M4-EG01-HF01 current partial S3 fact validation"}
    call_id, tool_call_id = f"hf01-{uuid4()}", f"tool-{uuid4()}"
    control = load_investigation_context(db, task_id, run_id)["task_run_control"]
    attempt_id, attempt_no = reserve_attempt(
        db, task_id, "MCP", 6, call_id=call_id, tool_call_id=tool_call_id,
        tool_name=tool_name, argument_digest=digest_json(args), run_id=run_id,
        task_run_control=control,
    )
    response = _call_s3_tool(server, tool_name, args)
    assert not response.is_error, f"MCP {tool_name} failed: {response!r}"
    value = response.structured_content
    if value is None:
        value = json.loads("".join(block.text for block in response.content if hasattr(block, "text")))
    if isinstance(value, dict) and isinstance(value.get("result"), dict):
        value = value["result"]
    normalized = D2ToolFact.model_validate(value).model_dump(mode="json")
    observation = record_tool_observation(
        db, task_id=task_id, call_id=call_id, attempt_id=attempt_id,
        tool_call_id=tool_call_id, tool_name=tool_name, arguments=args,
        status="OK", result=normalized,
    )
    finish_attempt(db, attempt_id, "OK", result_digest=digest_json(normalized))
    return {
        "task_id": task_id, "run_id": run_id, "attempt_id": attempt_id,
        "attempt_no": attempt_no, "call_id": call_id, "tool_call_id": tool_call_id,
        "tool_name": tool_name, "observation_id": observation["observation_id"],
        "evidence_id": observation["evidence_id"], "status": observation["status"],
        "progress_added": observation["progress_added"], "fact_type": normalized["fact_type"],
        "observed_at": normalized["observed_at"],
        "observed_versions": normalized["observed_versions"], "facts": normalized["facts"],
    }


def _business_snapshot(db: Path, task_id: str) -> dict[str, object]:
    with connect(db) as connection:
        binding = connection.execute(
            "SELECT status FROM task_bindings WHERE task_id=?", (task_id,),
        ).fetchone()
        control = connection.execute(
            "SELECT control_revision FROM task_controls WHERE task_id=?", (task_id,),
        ).fetchone()
        diagnosis = connection.execute(
            "SELECT receipt_id,body_json,digest,outcome FROM s3_diagnoses WHERE task_id=? ORDER BY rowid DESC LIMIT 1",
            (task_id,),
        ).fetchone()
        protected = {}
        tables = {str(row["name"]) for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'",
        ).fetchall()}
        for table in (
            "d3_approvals", "d3_action_permissions", "d3_action_intents", "d3_action_ledgers",
            "s3_handoff_queue_entries", "s3_handoff_receipts",
        ):
            if table in tables:
                protected[table] = int(connection.execute(
                    f"SELECT COUNT(*) FROM {table} WHERE task_id=?", (task_id,),
                ).fetchone()[0])
        business_events = int(connection.execute(
            """SELECT COUNT(*) FROM domain_outbox WHERE task_id=?
               AND (event_kind LIKE '%APPROVAL%' OR event_kind LIKE '%ACTION%' OR event_kind LIKE '%HANDOFF%')""",
            (task_id,),
        ).fetchone()[0])
    diagnosis_snapshot = None
    if diagnosis:
        diagnosis_snapshot = {
            "receipt_id": str(diagnosis["receipt_id"]), "digest": str(diagnosis["digest"]),
            "body_digest": hashlib.sha256(str(diagnosis["body_json"]).encode("utf-8")).hexdigest(),
            "outcome": str(diagnosis["outcome"]),
        }
    return {
        "task_binding_status": str(binding["status"]),
        "control_revision": int(control["control_revision"]),
        "diagnosis": diagnosis_snapshot,
        "protected_task_rows": protected,
        "approval_action_handoff_outbox_events": business_events,
    }


def _current_facts_from_messages(messages: list[dict[str, object]]) -> list[dict[str, object]]:
    prefix = "CURRENT AUTHORIZED MCP EVIDENCE: "
    message = next(str(item["content"]) for item in messages if str(item["content"]).startswith(prefix))
    payload = message.removeprefix(prefix)
    return [] if payload == "No current authorized MCP Evidence." else json.loads(payload)


def _record_other_event_delivery_observation(
    db: Path, task: dict[str, object], run_id: str, source_observation: dict[str, object],
) -> dict[str, object]:
    """Create a test-only forged Event claim to verify same-Run scope checks."""
    from opspilot.domain.d2 import digest_json, finish_attempt, record_tool_observation, reserve_attempt
    from opspilot.domain.investigation_context import load_investigation_context

    with connect(db) as connection:
        source = connection.execute(
            "SELECT result_json FROM d2_tool_observations WHERE observation_id=?",
            (source_observation["observation_id"],),
        ).fetchone()
    forged = json.loads(str(source["result_json"]))
    forged["facts"]["event_id"] = "event-from-another-bound-order"
    task_id = str(task["task_id"])
    args = {"reason": "M4-EG01-HF01 negative cross-event observation"}
    call_id, tool_call_id = f"hf01-forged-{uuid4()}", f"tool-{uuid4()}"
    control = load_investigation_context(db, task_id, run_id)["task_run_control"]
    attempt_id, attempt_no = reserve_attempt(
        db, task_id, "MCP", 6, call_id=call_id, tool_call_id=tool_call_id,
        tool_name="get_callback_delivery", argument_digest=digest_json(args), run_id=run_id,
        task_run_control=control,
    )
    observation = record_tool_observation(
        db, task_id=task_id, call_id=call_id, attempt_id=attempt_id,
        tool_call_id=tool_call_id, tool_name="get_callback_delivery", arguments=args,
        status="OK", result=forged,
    )
    finish_attempt(db, attempt_id, "OK", result_digest=digest_json(forged))
    return {
        "task_id": task_id, "run_id": run_id, "attempt_id": attempt_id,
        "attempt_no": attempt_no, "call_id": call_id, "tool_call_id": tool_call_id,
        "tool_name": "get_callback_delivery", "observation_id": observation["observation_id"],
        "evidence_id": observation["evidence_id"], "status": observation["status"],
        "forged_event_id": forged["facts"]["event_id"],
        "evidence_level": "test-only forged claim; not a real MCP response",
    }


@pytest.mark.parametrize(
    ("receiver_status", "expected_gate_outcome", "expected_direction"),
    [
        (None, "INCONCLUSIVE", "EVIDENCE_INSUFFICIENT"),
        ("PROCESSED", "RECEIVER_PROCESSED", "NO_FURTHER_ACTION"),
        ("QUEUED", "RECEIVER_PROCESSING_UNCONFIRMED", "WAIT_FOR_RECEIVER_PROCESSING"),
    ],
)
def test_chat_context_preserves_only_current_run_s3_observations(
    tmp_path: Path,
    receiver_status: str | None,
    expected_gate_outcome: str,
    expected_direction: str,
) -> None:
    """Exercise real local HTTP + in-process MCP facts through the Chat provider input boundary."""
    from opspilot.domain.api import make_server
    from opspilot.domain.s3 import evaluate_s3_gate, persist_s3_diagnosis
    from opspilot.domain.s3_mcp import build_s3_server
    from opspilot.domain.task_control import (
        admit_task_message, apply_pending_critical_inputs, claim_task_run,
        finish_task_run, register_worker_owner, trusted_identity,
    )

    order_id = f"hf01-{receiver_status or 'unknown'}-{uuid4().hex[:8]}"
    db, identity, task = _prepared_task(
        tmp_path, "DELIVERED_PENDING", order_id, queue_age_seconds=60,
        processing_sla_seconds=300,
    )
    if receiver_status is not None:
        with connect(db) as connection:
            connection.execute("UPDATE s3_receivers SET status=? WHERE order_id=?", (receiver_status, order_id))

    api = make_server(db, "tenant-a", "127.0.0.1", 0)
    thread = threading.Thread(target=api.serve_forever, daemon=True)
    thread.start()
    try:
        task_id, run_id = str(task["task_id"]), str(task["run_id"])
        claim_task_run(db, identity, run_id)
        apply_pending_critical_inputs(db, identity, run_id)
        mcp = build_s3_server(db, task_id, f"http://127.0.0.1:{api.server_port}")
        observations = [
            _observe_s3_tool(db, task, run_id, mcp, "get_order_status"),
            _observe_s3_tool(db, task, run_id, mcp, "get_callback_delivery"),
        ]
        forged_event_observation = _record_other_event_delivery_observation(
            db, task, run_id, next(item for item in observations if item["fact_type"] == "s3_delivery"),
        )
        if receiver_status is not None:
            observations.append(_observe_s3_tool(db, task, run_id, mcp, "get_receiver_processing"))
        evidence_ids = [str(item["evidence_id"]) for item in observations]
        gate = evaluate_s3_gate(db, task_id, evidence_ids, run_id=run_id)
        diagnosis = persist_s3_diagnosis(
            db, task_id, run_id, evidence_ids,
            stop_reason="HF01_CURRENT_RECEIVER_NOT_OBSERVED" if receiver_status is None else None,
        )
        finish_task_run(db, identity, run_id, "SUCCEEDED")

        register_worker_owner(db, "hf01-chat-worker", os.getpid())
        accepted = admit_task_message(
            db, identity, session_id=str(task["session_id"]), task_id=task_id,
            input_kind="CHAT_READONLY", body="同一事件现在是否处理完成？",
            idempotency_key=f"hf01-chat-{order_id}",
        )
        chat_run = str(accepted["run_id"])
        claim_task_run(db, identity, chat_run)
        from opspilot.domain.chat import prepare_chat_attempt

        business_before_chat = _business_snapshot(db, task_id)
        prepared = prepare_chat_attempt(db, chat_run, "hf01-chat-worker", "hf01-context-capture")
        facts = _current_facts_from_messages(prepared["messages"])
        diagnosis_body = json.loads(str(diagnosis["body_json"]))
        record = {
            "case_id": f"HF01-{receiver_status or '202-UNKNOWN'}",
            "task_id": task_id, "investigation_run_id": run_id, "chat_run_id": chat_run,
            "evidence_observations": observations,
            "forged_event_observation": forged_event_observation,
            "http_order_status": next(item["facts"]["http_status"] for item in observations if item["fact_type"] == "s3_order"),
            "delivery_http_status": next(item["facts"]["receiver_http_status"] for item in observations if item["fact_type"] == "s3_delivery"),
            "event_id": next(item["facts"]["event_id"] for item in observations if item["fact_type"] == "s3_delivery"),
            "transport_request_id": next(item["facts"]["transport_request_id"] for item in observations if item["fact_type"] == "s3_delivery"),
            "gate": gate, "frozen_diagnosis_gate": diagnosis_body["gate"],
            "chat_evidence_refs": prepared["evidence_refs"],
            "provider_input_messages": prepared["messages"],
            "chat_fact_types": [item["fact_type"] for item in facts],
            "chat_fact_evidence_ids": [item["evidence_id"] for item in facts],
            "excluded_sources": prepared["excluded_sources"],
            "business_snapshot_before_chat": business_before_chat,
            "business_snapshot_after_chat": _business_snapshot(db, task_id),
            "provider_call": "NOT_RUN; prepare_chat_attempt output is the exact provider-input payload, no Provider was invoked by this test",
        }
        _trace(record)

        assert next(item["facts"]["http_status"] for item in observations if item["fact_type"] == "s3_order") == 200
        delivery = next(item for item in observations if item["fact_type"] == "s3_delivery")
        assert delivery["facts"]["receiver_http_status"] == 202
        assert gate["decision"] == ("NEED_MORE" if receiver_status is None else "DIAGNOSED")
        assert diagnosis_body["gate"]["outcome"] == expected_gate_outcome
        assert diagnosis_body["gate"]["handling_direction"] == expected_direction
        assert {item["fact_type"] for item in facts} == {item["fact_type"] for item in observations}, (
            "Chat must preserve every current same-Run observation, including valid partial facts not used by Gate"
        )
        assert set(prepared["evidence_refs"][i]["evidence_id"] for i in range(len(prepared["evidence_refs"]))) == set(evidence_ids)
        assert business_before_chat == record["business_snapshot_after_chat"], "CHAT_READONLY must not change S3 business state or write records"
        assert forged_event_observation["evidence_id"] not in {item["evidence_id"] for item in facts}
        assert any(
            item.get("source_id") == forged_event_observation["evidence_id"]
            and item.get("reason") == "S3_CURRENT_FACT_MISMATCH"
            for item in prepared["excluded_sources"]
        ), "The rejected wrong-Event Observation must retain its exclusion reason"
        assert any(
            item["fact_type"] == "s3_delivery"
            and item["facts"]["event_id"] == delivery["facts"]["event_id"]
            and item["facts"]["transport_request_id"] == delivery["facts"]["transport_request_id"]
            and item["observed_versions"] == delivery["observed_versions"]
            for item in facts
        )
        delivery_context = next(item for item in facts if item["fact_type"] == "s3_delivery")
        assert "transport_response_json" not in delivery_context["facts"], (
            "the immutable HTTP 202 payload may describe acceptance-time QUEUED, not current Receiver state"
        )
        with connect(db) as connection:
            manifest = connection.execute(
                "SELECT evidence_refs_json FROM chat_context_manifests WHERE attempt_id=?",
                (prepared["attempt_id"],),
            ).fetchone()
        assert json.loads(str(manifest["evidence_refs_json"])) == prepared["evidence_refs"]
        if receiver_status is None:
            assert "s3_receiver" not in {item["fact_type"] for item in facts}
            assert "HTTP 202 alone proves acceptance only; without current same-event receiver evidence, state is UNKNOWN" in "\n".join(
                str(item["content"]) for item in prepared["messages"]
            )
    finally:
        api.shutdown()
        thread.join()
        api.server_close()


def test_chat_context_does_not_mix_another_tasks_s3_observations(tmp_path: Path) -> None:
    """A valid, current observation from another bound Task is never Chat evidence."""
    import os

    from opspilot.domain.s3 import persist_s3_diagnosis, prepare_s3_fixture
    from opspilot.domain.task_control import (
        admit_task_message, finish_task_run, register_worker_owner,
    )
    from test_m4_03_s3 import _evidence, _facts, _task

    order_a, order_b = "hf01-cross-task-a", "hf01-cross-task-b"
    db, identity_a, task_a = _prepared_task(tmp_path, "DELIVERED_PENDING", order_a)
    facts_a = _facts(db, task_a)
    evidence_a = _evidence(db, task_a, "get_order_status", facts_a[0])
    diagnosis_a = persist_s3_diagnosis(db, str(task_a["task_id"]), str(task_a["run_id"]), [evidence_a], stop_reason="INCONCLUSIVE_PARTIAL")
    finish_task_run(db, identity_a, str(task_a["run_id"]), "SUCCEEDED")

    prepare_s3_fixture(db, "DELIVERED_PENDING", order_id=order_b)
    identity_b, task_b = _task(db, order_b, text="确认第二个订单的回调状态")
    facts_b = _facts(db, task_b)
    evidence_b = _evidence(db, task_b, "get_order_status", facts_b[0])
    diagnosis_b = persist_s3_diagnosis(db, str(task_b["task_id"]), str(task_b["run_id"]), [evidence_b], stop_reason="INCONCLUSIVE_PARTIAL")
    finish_task_run(db, identity_b, str(task_b["run_id"]), "SUCCEEDED")

    worker_id = "hf01-cross-task-chat-worker"
    register_worker_owner(db, worker_id, os.getpid())
    accepted = admit_task_message(
        db, identity_b, session_id=str(task_b["session_id"]), task_id=str(task_b["task_id"]),
        input_kind="CHAT_READONLY", body="只解释第二个订单当前能确认的事实。",
        idempotency_key="hf01-cross-task-chat-b",
    )
    from opspilot.domain.task_control import claim_task_run
    claim_task_run(db, identity_b, str(accepted["run_id"]))
    from opspilot.domain.chat import prepare_chat_attempt

    prepared = prepare_chat_attempt(db, str(accepted["run_id"]), worker_id, "hf01-cross-task-context")
    facts = _current_facts_from_messages(prepared["messages"])
    _trace({
        "case_id": "HF01-CROSS-TASK",
        "source_task_id": str(task_a["task_id"]), "target_task_id": str(task_b["task_id"]),
        "source_evidence_id": evidence_a, "source_run_id": str(task_a["run_id"]),
        "source_diagnosis": {"receipt_id": diagnosis_a["receipt_id"], "digest": diagnosis_a["digest"]},
        "target_evidence_id": evidence_b, "target_run_id": str(task_b["run_id"]),
        "target_diagnosis": {"receipt_id": diagnosis_b["receipt_id"], "digest": diagnosis_b["digest"]},
        "chat_run_id": str(accepted["run_id"]), "chat_fact_evidence_ids": [item["evidence_id"] for item in facts],
        "chat_fact_order_ids": [item["facts"]["body"]["order_id"] for item in facts if item["fact_type"] == "s3_order"],
        "result": "PASS: only Task B's current Run observation entered Chat Context",
    })
    assert evidence_b in {item["evidence_id"] for item in facts}
    assert evidence_a not in {item["evidence_id"] for item in facts}
    assert {item["facts"]["body"]["order_id"] for item in facts if item["fact_type"] == "s3_order"} == {order_b}
