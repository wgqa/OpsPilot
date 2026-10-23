from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
from uuid import uuid4

from test_m4_03_s3 import _facts, _prepared_task
from s3_observation_support import record_s3_observation


def test_ttl_07_unlinked_failed_malformed_and_future_observations_fail_closed(
    tmp_path: Path, monkeypatch,
):
    from opspilot.domain.database import connect
    from opspilot.domain.d2 import (
        digest_json, finish_attempt, record_tool_observation, reserve_attempt,
    )
    from opspilot.domain.investigation_context import load_investigation_context
    from opspilot.domain.s3 import current_s3_evidence, evaluate_s3_gate
    import opspilot.domain.s3 as s3

    db, _, task = _prepared_task(tmp_path, "PROCESSING", "async-order-2")
    order, _, _ = _facts(db, task)
    valid = record_s3_observation(db, task, "get_order_status", order)
    evidence_id = str(valid["evidence_id"])
    run_id = str(task["run_id"])
    assert evaluate_s3_gate(db, str(task["task_id"]), [evidence_id], run_id=run_id)["outcome"] == "ORDER_PROCESSING"

    fake_call = f"fake-no-attempt-{uuid4()}"
    unlinked = record_tool_observation(
        db, task_id=str(task["task_id"]), call_id=fake_call, attempt_id=None,
        tool_call_id=fake_call, tool_name="get_order_status", arguments={},
        status="OK", result=order,
    )
    current, excluded = _current_s3_evidence(
        db, str(task["task_id"]), [evidence_id], run_id=run_id,
        observation_ids={evidence_id: str(unlinked["observation_id"])},
    )
    assert not current
    assert any(item["reason"] == "S3_OBSERVATION_ASSOCIATION_INVALID" for item in excluded)
    unlinked_reasons = excluded

    args: dict[str, object] = {}
    call_id, tool_call_id = f"failed-attempt-{uuid4()}", f"tool-{uuid4()}"
    run_control = load_investigation_context(db, str(task["task_id"]), run_id)["task_run_control"]
    attempt_id, _ = reserve_attempt(
        db, str(task["task_id"]), "MCP", 6, call_id=call_id,
        tool_call_id=tool_call_id, tool_name="get_order_status",
        argument_digest=digest_json(args), run_id=run_id, task_run_control=run_control,
    )
    failed = record_tool_observation(
        db, task_id=str(task["task_id"]), call_id=call_id, attempt_id=attempt_id,
        tool_call_id=tool_call_id, tool_name="get_order_status", arguments=args,
        status="OK", result=order,
    )
    finish_attempt(db, attempt_id, "FAILED", error_class="injected failure after observation persistence")
    current, excluded = _current_s3_evidence(
        db, str(task["task_id"]), [evidence_id], run_id=run_id,
        observation_ids={evidence_id: str(failed["observation_id"])},
    )
    assert not current
    assert any(item["reason"] == "S3_OBSERVATION_ASSOCIATION_INVALID" for item in excluded)
    failed_reasons = excluded

    original_time = str(valid["observation_id"])
    with connect(db) as connection:
        created_at = str(connection.execute(
            "SELECT created_at FROM d2_tool_observations WHERE observation_id=?", (original_time,),
        ).fetchone()[0])
        evidence_before = dict(connection.execute(
            "SELECT evidence_id,fetched_at,digest,original_result_ref FROM d2_evidence WHERE evidence_id=?",
            (evidence_id,),
        ).fetchone())
        connection.execute(
            "UPDATE d2_tool_observations SET created_at='malformed-time' WHERE observation_id=?",
            (original_time,),
        )
    current, excluded = _current_s3_evidence(
        db, str(task["task_id"]), [evidence_id], run_id=run_id,
        observation_ids={evidence_id: original_time},
    )
    assert not current
    assert any(item["reason"] == "S3_OBSERVATION_TIME_INVALID" for item in excluded)
    malformed_reasons = excluded
    with connect(db) as connection:
        connection.execute(
            "UPDATE d2_tool_observations SET created_at=? WHERE observation_id=?",
            (created_at, original_time),
        )

    observed = datetime.fromisoformat(created_at.replace("Z", "+00:00"))

    class FutureObservationClock(datetime):
        @classmethod
        def now(cls, tz=None):
            now = observed - timedelta(seconds=1)
            return now if tz is not None else now.replace(tzinfo=None)

    monkeypatch.setattr(s3, "datetime", FutureObservationClock)
    current, excluded = _current_s3_evidence(
        db, str(task["task_id"]), [evidence_id], run_id=run_id,
        observation_ids={evidence_id: original_time},
    )
    assert not current
    assert any(item["reason"] == "S3_OBSERVATION_TIME_INVALID" for item in excluded)
    future_reasons = excluded
    with connect(db) as connection:
        evidence_after = dict(connection.execute(
            "SELECT evidence_id,fetched_at,digest,original_result_ref FROM d2_evidence WHERE evidence_id=?",
            (evidence_id,),
        ).fetchone())
    assert evidence_after == evidence_before
    trace_path = os.environ.get("OPSPILOT_PREFLIGHT_TRACE_PATH")
    if trace_path:
        trace = {
            "event": "ttl07_observation_integrity",
            "task_id": str(task["task_id"]),
            "run_id": run_id,
            "http_request_id": str(order["facts"]["body"]["request_id"]),
            "evidence_id": evidence_id,
            "evidence_unchanged": evidence_after == evidence_before,
            "valid_observation": {
                "observation_id": str(valid["observation_id"]),
                "attempt_id": str(valid["attempt_id"]),
                "created_at": created_at,
                "gate": "DIAGNOSED",
            },
            "unlinked_observation": {
                "observation_id": str(unlinked["observation_id"]),
                "attempt_id": None,
                "excluded": unlinked_reasons,
            },
            "failed_attempt_observation": {
                "observation_id": str(failed["observation_id"]),
                "attempt_id": attempt_id,
                "attempt_status": "FAILED",
                "excluded": failed_reasons,
            },
            "malformed_time_observation_id": original_time,
            "malformed_time_excluded": malformed_reasons,
            "negative_age_clock": (observed - timedelta(seconds=1)).isoformat(),
            "negative_age_excluded": future_reasons,
        }
        with open(trace_path, "a", encoding="utf-8") as stream:
            stream.write(json.dumps(trace, ensure_ascii=False, sort_keys=True) + "\n")


def test_same_fact_refresh_counts_as_observation_but_duplicate_call_is_suppressed(tmp_path: Path):
    import asyncio
    from opspilot.domain.d2 import attempt_counts, digest_json
    from opspilot.s3_investigation import S3Nodes

    db, _, task = _prepared_task(tmp_path, "PROCESSING", "async-order-2")
    order, _, _ = _facts(db, task)
    first = record_s3_observation(db, task, "get_order_status", order)
    second = record_s3_observation(db, task, "get_order_status", order)
    assert first["evidence_id"] == second["evidence_id"]
    assert first["observation_id"] != second["observation_id"]
    assert first["progress_added"] is True
    assert second["progress_added"] is False

    class NeverCallMCP:
        async def call_tool(self, *_args, **_kwargs):
            raise AssertionError("duplicate current tool call must be suppressed")

    nodes = S3Nodes(
        db, str(task["task_id"]), str(task["run_id"]), None,
        "unit-test-only", NeverCallMCP(), [],
    )
    second_state_observation = {
        **second,
        "status": "OK",
        "tool_name": "get_order_status",
        "argument_digest": digest_json({}),
        "observation_current": nodes._observation_current(second),
    }
    assert nodes._observation_action(second_state_observation) == "MCP_OBSERVATION_REFRESHED"
    before = attempt_counts(db, str(task["task_id"]))["MCP"]
    stopped = asyncio.run(nodes.execute({
        "evidence_ids": [str(second["evidence_id"])],
        "tool_observations": [second_state_observation],
        "diagnosis_draft": {},
        "pending_call_refs": [],
        "policy_tool_call": {
            "call_id": "same-tool-same-arguments",
            "name": "get_order_status",
            "args": {},
        },
    }))
    after = attempt_counts(db, str(task["task_id"]))["MCP"]
    assert stopped["last_investigation_action"] == "MCP_NO_PROGRESS"
    assert after == before


def _current_s3_evidence(db, task_id, evidence_ids, **kwargs):
    from opspilot.domain.database import connect
    from opspilot.domain.s3 import current_s3_evidence as validate
    with connect(db) as connection:
        return validate(connection, task_id, evidence_ids, **kwargs)
