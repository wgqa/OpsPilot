from __future__ import annotations

import asyncio
import json
import os
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import pytest


def _trace(event: dict[str, object]) -> None:
    trace_path = os.environ.get("OPSPILOT_PREFLIGHT_TRACE_PATH")
    if trace_path:
        with open(trace_path, "a", encoding="utf-8") as stream:
            stream.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")


def _call_s3_tool(server, name: str, args: dict[str, object]):
    from mcp.server.mcpserver.context import Context
    from mcp.types import CallToolRequestParams

    context = Context(
        mcp_server=server,
        input_params=CallToolRequestParams(name=name, arguments=args),
    )
    return asyncio.run(server.call_tool(name, args, context))


def _run_real_mcp_facts(db: Path, task_id: str, run_id: str, server) -> list[dict[str, object]]:
    from opspilot.domain.d2 import digest_json, finish_attempt, record_tool_observation, reserve_attempt
    from opspilot.domain.investigation_context import load_investigation_context
    from opspilot.domain.schemas import D2ToolFact

    records: list[dict[str, object]] = []
    for tool in ("get_order_status", "get_callback_delivery", "get_receiver_processing"):
        args = {"reason": "M4-PREFLIGHT-01 repeated-fetch TTL investigation"}
        call_id, tool_call_id = f"preflight-{uuid4()}", f"tool-{uuid4()}"
        control = load_investigation_context(db, task_id, run_id)["task_run_control"]
        attempt_id, attempt_no = reserve_attempt(
            db,
            task_id,
            "MCP",
            6,
            call_id=call_id,
            tool_call_id=tool_call_id,
            tool_name=tool,
            argument_digest=digest_json(args),
            run_id=run_id,
            task_run_control=control,
        )
        response = _call_s3_tool(server, tool, args)
        assert not response.is_error, f"real MCP tool {tool} failed: {response!r}"
        value = response.structured_content
        if value is None:
            value = json.loads("".join(block.text for block in response.content if hasattr(block, "text")))
        if isinstance(value, dict) and isinstance(value.get("result"), dict):
            value = value["result"]
        normalized = D2ToolFact.model_validate(value).model_dump(mode="json")
        observation = record_tool_observation(
            db,
            task_id=task_id,
            call_id=call_id,
            attempt_id=attempt_id,
            tool_call_id=tool_call_id,
            tool_name=tool,
            arguments=args,
            status="OK",
            result=normalized,
        )
        finish_attempt(db, attempt_id, "OK", result_digest=digest_json(normalized))
        record = {
            "task_id": task_id,
            "run_id": run_id,
            "attempt_id": attempt_id,
            "attempt_no": attempt_no,
            "call_id": call_id,
            "tool_call_id": tool_call_id,
            "tool_name": tool,
            "mcp_is_error": bool(response.is_error),
            "observation_id": observation["observation_id"],
            "observation_status": observation["status"],
            "progress_added": observation["progress_added"],
            "evidence_id": observation["evidence_id"],
            "observed_at": normalized["observed_at"],
            "observed_versions": normalized["observed_versions"],
            "fact_type": normalized["fact_type"],
            "facts": normalized["facts"],
        }
        records.append(record)
        _trace({"event": "mcp_observation", **record})
    return records


def _business_snapshot(db: Path, order_id: str) -> dict[str, object]:
    from opspilot.domain.database import connect

    with connect(db) as connection:
        order = connection.execute(
            "SELECT status,version,contract_version FROM s3_orders "
            "WHERE tenant_id='tenant-a' AND service_id='orders-async-demo' AND order_id=?",
            (order_id,),
        ).fetchone()
        delivery = connection.execute(
            "SELECT event_id,order_version,version,status,attempt_count,retry_state "
            "FROM s3_deliveries WHERE tenant_id='tenant-a' AND service_id='orders-async-demo' AND order_id=?",
            (order_id,),
        ).fetchone()
        receiver = connection.execute(
            "SELECT event_id,delivery_version,version,status,accepted_at,processing_sla_seconds "
            "FROM s3_receivers WHERE tenant_id='tenant-a' AND service_id='orders-async-demo' AND order_id=?",
            (order_id,),
        ).fetchone()
    return {"order": dict(order), "delivery": dict(delivery), "receiver": dict(receiver)}


def _evidence_rows(db: Path, task_id: str, evidence_ids: list[str]) -> list[dict[str, object]]:
    from opspilot.domain.database import connect

    if not evidence_ids:
        return []
    placeholders = ",".join("?" for _ in evidence_ids)
    with connect(db) as connection:
        rows = connection.execute(
            f"SELECT evidence_id,call_id,tool_call_id,fetched_at,observed_versions_json,fact_type,digest "
            f"FROM d2_evidence WHERE task_id=? AND evidence_id IN ({placeholders}) ORDER BY fact_type",
            (task_id, *evidence_ids),
        ).fetchall()
    return [
        {
            **dict(row),
            "observed_versions": json.loads(row["observed_versions_json"]),
        }
        for row in rows
    ]


def test_ttl_01_04_real_mcp_refresh_is_run_scoped_and_old_diagnosis_stays_frozen(tmp_path: Path, monkeypatch):
    """A new successful MCP/HTTP observation of unchanged facts must satisfy currentness."""
    from opspilot.domain.api import make_server
    from opspilot.domain.database import connect, reset_fixture
    from opspilot.domain.s3 import (
        current_s3_evidence, evaluate_s3_gate, get_s3_outcome,
        persist_s3_diagnosis, prepare_s3_fixture,
    )
    from opspilot.domain.s3_mcp import build_s3_server
    from opspilot.domain.task_control import (
        admit_task_message,
        apply_pending_critical_inputs,
        claim_task_run,
        create_session,
        create_task_with_initial_run,
        finish_task_run,
        trusted_identity,
    )
    import opspilot.domain.d2 as d2
    import opspilot.domain.s3 as s3

    db = tmp_path / "m4-preflight-01.sqlite3"
    order_id = "async-order-2"
    reset_fixture(db, "S1_POS")
    prepare_s3_fixture(
        db,
        "DELIVERED_PENDING",
        order_id=order_id,
        queue_age_seconds=60,
        processing_sla_seconds=3600,
    )
    identity = trusted_identity(db, "support-a")
    session = create_session(db, identity)
    task = create_task_with_initial_run(
        db,
        identity,
        session_id=str(session["session_id"]),
        service_id="orders-async-demo",
        integration_id="async-integration-a",
        ticket_id="M4-PREFLIGHT-01",
        initial_message="订单接口返回 200，但下游没有收到异步回调。",
        idempotency_key="m4-preflight-create-s3-task",
        s3_order_id=order_id,
    )
    task_id, first_run_id = str(task["task_id"]), str(task["run_id"])

    clock = {"now": datetime.now(timezone.utc).replace(microsecond=0)}

    class ControlledDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            current = clock["now"]
            return current if tz is not None else current.replace(tzinfo=None)

    # D2 stamps/validates Evidence through d2.datetime; S3 Gate TTL uses s3.datetime.
    # Both must share the exact same controlled source to avoid a false skew failure.
    monkeypatch.setattr(d2, "datetime", ControlledDateTime)
    monkeypatch.setattr(s3, "datetime", ControlledDateTime)

    api = make_server(db, "tenant-a", "127.0.0.1", 0)
    thread = threading.Thread(target=api.serve_forever, daemon=True)
    thread.start()
    try:
        root = f"http://127.0.0.1:{api.server_port}"
        mcp_server = build_s3_server(db, task_id, root)
        before_business = _business_snapshot(db, order_id)

        claim_task_run(db, identity, first_run_id)
        apply_pending_critical_inputs(db, identity, first_run_id)
        first_records = _run_real_mcp_facts(db, task_id, first_run_id, mcp_server)
        first_ids = [str(item["evidence_id"]) for item in first_records]
        first_gate = evaluate_s3_gate(db, task_id, first_ids, run_id=first_run_id)
        first_diagnosis = persist_s3_diagnosis(db, task_id, first_run_id, first_ids)
        finish_task_run(db, identity, first_run_id, "SUCCEEDED")
        assert first_gate["decision"] == "DIAGNOSED"
        assert first_gate["handling_direction"] == "WAIT_FOR_RECEIVER_PROCESSING"

        first_evidence = _evidence_rows(db, task_id, first_ids)
        first_observation_ids = [str(item["observation_id"]) for item in first_records]
        first_snapshot = _business_snapshot(db, order_id)
        original_fetched_at = {str(item["evidence_id"]): str(item["fetched_at"]) for item in first_evidence}
        with connect(db) as connection:
            original_evidence_rows = [
                dict(connection.execute("SELECT * FROM d2_evidence WHERE evidence_id=?", (item,)).fetchone())
                for item in first_ids
            ]
            first_observation_at = str(connection.execute(
                "SELECT created_at FROM d2_tool_observations WHERE observation_id=?",
                (first_observation_ids[0],),
            ).fetchone()[0])
        observation_time = datetime.fromisoformat(first_observation_at.replace("Z", "+00:00"))
        boundary_results = []
        for age, expected in ((299, "DIAGNOSED"), (300, "DIAGNOSED"), (301, "NEED_MORE")):
            clock["now"] = observation_time + timedelta(seconds=age)
            boundary = evaluate_s3_gate(db, task_id, first_ids, run_id=first_run_id)
            assert boundary["decision"] == expected, json.dumps(boundary, ensure_ascii=False)
            boundary_results.append({
                "age_seconds": age,
                "decision": boundary["decision"],
                "excluded_sources": boundary["excluded_sources"],
            })
        clock["now"] = observation_time + timedelta(seconds=301)
        assert _business_snapshot(db, order_id) == before_business == first_snapshot
        assert _business_snapshot(db, order_id) == before_business == first_snapshot

        with connect(db) as connection:
            revision = int(
                connection.execute(
                    "SELECT control_revision FROM task_controls WHERE task_id=?", (task_id,)
                ).fetchone()[0]
            )
        accepted = admit_task_message(
            db,
            identity,
            session_id=str(task["session_id"]),
            task_id=task_id,
            input_kind="CORRECT_TASK_INPUT",
            body="请基于当前订单、投递和接收状态重新调查。",
            idempotency_key="m4-preflight-second-real-investigation",
            expected_control_revision=revision,
        )
        second_run_id = str(accepted["run_id"])
        assert second_run_id != first_run_id
        claim_task_run(db, identity, second_run_id)
        apply_pending_critical_inputs(db, identity, second_run_id)
        second_records = _run_real_mcp_facts(db, task_id, second_run_id, mcp_server)
        second_ids = [str(item["evidence_id"]) for item in second_records]
        second_gate = evaluate_s3_gate(db, task_id, second_ids, run_id=second_run_id)
        second_diagnosis = persist_s3_diagnosis(db, task_id, second_run_id, second_ids)
        finish_task_run(db, identity, second_run_id, "SUCCEEDED")
        second_evidence = _evidence_rows(db, task_id, second_ids)
        after_business = _business_snapshot(db, order_id)
        second_observation_ids = [str(item["observation_id"]) for item in second_records]

        # The exact Run A observations remain expired after Run B refreshes the same facts.
        # The immutable Diagnosis A row and its body/digest must stay byte-for-byte stable.
        with connect(db) as connection:
            old_current, old_excluded = current_s3_evidence(
                connection, task_id, first_ids, run_id=first_run_id,
                observation_ids=first_observation_ids,
            )
            wrong_run_current, wrong_run_excluded = current_s3_evidence(
                connection, task_id, first_ids, run_id=second_run_id,
                observation_ids=first_observation_ids,
            )
            after_evidence_rows = [
                dict(connection.execute("SELECT * FROM d2_evidence WHERE evidence_id=?", (item,)).fetchone())
                for item in first_ids
            ]
            stored_first_diagnosis = connection.execute(
                "SELECT run_id,body_json,digest FROM s3_diagnoses WHERE receipt_id=?",
                (first_diagnosis["receipt_id"],),
            ).fetchone()
        assert not old_current
        assert any(item["reason"] == "S3_EVIDENCE_EXPIRED" for item in old_excluded)
        assert not wrong_run_current
        assert wrong_run_excluded
        assert after_evidence_rows == original_evidence_rows
        assert stored_first_diagnosis["run_id"] == first_run_id
        assert stored_first_diagnosis["body_json"] == first_diagnosis["body_json"]
        assert stored_first_diagnosis["digest"] == first_diagnosis["digest"]
        assert get_s3_outcome(db, task_id)["currentness"] == "CURRENT"
        assert second_observation_ids != first_observation_ids

        # `d2_tool_observations` links to the Run through its MCP attempt.
        with connect(db) as connection:
            observation_rows = connection.execute(
                "SELECT o.observation_id,o.call_id,o.status,o.progress_added,o.evidence_id,o.created_at,"
                "a.run_id FROM d2_tool_observations o LEFT JOIN d2_attempts a ON a.attempt_id=o.attempt_id "
                "WHERE o.task_id=? ORDER BY o.rowid",
                (task_id,),
            ).fetchall()
            http_rows = connection.execute(
                "SELECT request_id,tenant_id,service_id,integration_id,principal_id,route,http_status,created_at "
                "FROM s3_http_observations WHERE tenant_id='tenant-a' ORDER BY rowid"
            ).fetchall()
        call_observations = [dict(row) for row in observation_rows]
        trace = {
            "case": "M4-PREFLIGHT-01-EVIDENCE-TTL-REPEATED-REAL-FETCH",
            "task_id": task_id,
            "first_run_id": first_run_id,
            "second_run_id": second_run_id,
            "clock_first_observation": first_records[0]["observed_at"],
            "clock_second_observation": second_records[0]["observed_at"],
            "clock_advanced_seconds": 301,
            "ttl_seconds": 300,
            "business_facts_unchanged": before_business == first_snapshot == after_business,
            "business_before": before_business,
            "business_after": after_business,
            "first_records": first_records,
            "first_observation_ids": first_observation_ids,
            "first_evidence_rows": first_evidence,
            "first_evidence_fetched_at": original_fetched_at,
            "first_gate": first_gate,
            "first_diagnosis_id": first_diagnosis["receipt_id"],
            "first_diagnosis_digest": first_diagnosis["digest"],
            "ttl_boundary_results": boundary_results,
            "second_records": second_records,
            "second_observation_ids": second_observation_ids,
            "second_evidence_rows": second_evidence,
            "second_gate": second_gate,
            "second_diagnosis_id": second_diagnosis["receipt_id"],
            "run_a_recheck_after_run_b": {
                "current_evidence_ids": [item["evidence_id"] for item in old_current],
                "excluded_sources": old_excluded,
                "wrong_run_pins_excluded_sources": wrong_run_excluded,
                "evidence_rows_unchanged": after_evidence_rows == original_evidence_rows,
                "diagnosis_body_unchanged": stored_first_diagnosis["body_json"] == first_diagnosis["body_json"],
                "diagnosis_digest_unchanged": stored_first_diagnosis["digest"] == first_diagnosis["digest"],
            },
            "evidence_ids_reused_by_fact_type": {
                str(item["fact_type"]): {
                    "first": first_records[index]["evidence_id"],
                    "second": second_records[index]["evidence_id"],
                    "reused": first_records[index]["evidence_id"] == second_records[index]["evidence_id"],
                    "first_fetched_at": next(
                        str(row["fetched_at"]) for row in first_evidence
                        if row["evidence_id"] == first_records[index]["evidence_id"]
                    ),
                }
                for index, item in enumerate(first_records)
            },
            "all_mcp_observations": call_observations,
            "http_observations": [dict(row) for row in http_rows],
        }
        _trace({"event": "run_scoped_refresh_summary", **trace})
        print("M4_TTL_FIX_TRACE=" + json.dumps(trace, ensure_ascii=False, sort_keys=True), flush=True)

        # Successful fresh Run B reads of unchanged facts must be current, while the
        # exact expired observations frozen by Diagnosis A remain expired.
        assert second_gate["decision"] == "DIAGNOSED", json.dumps(second_gate, ensure_ascii=False)
        assert second_gate["handling_direction"] == "WAIT_FOR_RECEIVER_PROCESSING"
        assert not second_gate["excluded_sources"]
    finally:
        api.shutdown()
        thread.join(timeout=5)
        api.server_close()
