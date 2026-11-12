"""The Assistant sees an observation-time SLA assessment with its original source."""
import json

import pytest
from langchain_core.messages import SystemMessage

from opspilot.domain import s3
from opspilot.domain.database import connect
from test_ar02_runtime import FixtureModel, execute, setup_run


@pytest.mark.parametrize(("scenario", "status", "expected"), [
    ("queued-before", "QUEUED", "WITHIN_SLA"),
    ("queued-next-day", "QUEUED", "OVERDUE"),
    ("processed", "PROCESSED", "PROCESSED"),
    ("transport-exhausted", "NOT_RECEIVED", "NOT_APPLICABLE"),
])
def test_assistant_receives_sla_from_current_real_mcp_observation(demo_db, tmp_path, scenario, status, expected):
    expired = scenario in {"queued-next-day", "processed"}
    failed = scenario == "transport-exhausted"
    s3.prepare_s3_fixture(
        demo_db, "DELIVERY_FAILED" if failed else "DELIVERED_PENDING", order_id="ar02-order", contract_version=2,
        queue_age_seconds=86_400 if expired else 5, processing_sla_seconds=300,
        **({"attempt_count": 3, "retry_state": "EXHAUSTED"} if failed else {}),
    )
    if status == "PROCESSED":
        with connect(demo_db) as db:
            db.execute("UPDATE s3_receivers SET status='PROCESSED',version=version+1 WHERE order_id='ar02-order'")
    admitted = setup_run(demo_db, "查询本事件的回调和接收进度，是否超过时限？", f"sla-{scenario}", bind=True)
    model = FixtureModel(mode="business")
    result, trace = execute(demo_db, admitted, model, tmp_path / "sla-checkpoints.sqlite3")
    assert result["status"] == "SUCCEEDED", result
    receiver = next(item for item in trace if item["event"] == "tool_observation" and item["name"] == "get_receiver_processing")
    fact = receiver["result"]
    assert fact["facts"]["status"] == status

    system = next(message.content for message in model.seen[-1] if isinstance(message, SystemMessage))
    context = json.loads(system.split("\nWORK_CONTEXT\n", 1)[1].split("\n\n", 1)[0])
    link = next(item for item in context["current_run"]["business_observations"] if item["tool"] == "get_receiver_processing")
    assert link["observation_id"] == receiver["observation"]["observation_id"]
    assert link["evidence_id"] == receiver["observation"]["evidence_id"]
    assert link["observed_at"] == fact["observed_at"]
    sla = link["receiver_sla"]
    assert sla["assessment"] == expected
    assert sla["event_id"] == fact["facts"]["event_id"]
    assert sla["delivery_version"] == fact["facts"]["delivery_version"]
    assert sla["receiver_version"] == fact["observed_versions"]["receiver_version"]
    if status == "QUEUED":
        assert sla["processing_sla_seconds"] == 300
        assert (sla["elapsed_seconds"] >= 300) is expired
        assert sla["deadline"]
    else:
        assert "deadline" not in sla
    assert "receiver_sla" not in fact["facts"]
    assert "OVERDUE" in system and "EXHAUSTED" in system
    print(f"{scenario}: {status}, {sla['assessment']}, source/Observation/Event/versions match")


@pytest.mark.parametrize(("observed_at", "expected"), [
    ("2026-11-11T15:18:25.999Z", "WITHIN_SLA"),
    ("2026-11-11T15:18:26Z", "OVERDUE"),
    ("2026-11-12T15:13:26Z", "OVERDUE"),
    ("2026-11-11T15:13:25Z", "UNKNOWN"),
])
def test_receiver_sla_uses_observation_time_at_the_exact_deadline(observed_at, expected):
    fact = {
        "fact_type": "s3_receiver", "observed_at": observed_at,
        "observed_versions": {"delivery_version": 3, "receiver_version": 4},
        "facts": {"status": "QUEUED", "event_id": "event-one", "delivery_version": 3, "version": 4,
                  "accepted_at": "2026-11-11T15:13:26Z", "processing_sla_seconds": 300},
    }
    assert s3.receiver_sla_at_observation(fact)["assessment"] == expected
