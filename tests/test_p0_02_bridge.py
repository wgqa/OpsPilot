"""Condition review contract through the existing authenticated workbench API."""
from __future__ import annotations

import asyncio
import importlib.util
import json
import os
from pathlib import Path
import time

from fastapi.testclient import TestClient
import pytest

from opspilot.domain.database import connect, initialize
from opspilot.domain.d2 import configure_s3_experiment_budget
from opspilot.domain.s3 import prepare_s3_fixture
from opspilot.domain import task_control as tc
from opspilot.web.app import create_app
from opspilot.web.worker import _dispatch_run


ORIGIN = "http://bridge.test"
PASSWORD = "bridge-fixture"

spec = importlib.util.spec_from_file_location(
    "bridge_offline", Path(__file__).resolve().parents[1] / "docs/reviews/p0-02-bridge-01/offline.py",
)
offline = importlib.util.module_from_spec(spec)
spec.loader.exec_module(offline)
frozen = offline.frozen


def test_bridge_review_requires_provider_authorization_for_bound_task(demo_db, monkeypatch):
    from opspilot.config import LEGACY_PROVIDER_ENABLED, MODEL_API_KEY, MODEL_NAME
    from opspilot.domain import investigation_updates

    monkeypatch.setenv(MODEL_NAME, "deepseek-flash")
    monkeypatch.setenv(MODEL_API_KEY, "offline-fixture-key")
    monkeypatch.setenv("OPSPILOT_ASSISTANT_PROVIDER_ENABLED", "1")
    monkeypatch.setenv(LEGACY_PROVIDER_ENABLED, "0")
    monkeypatch.delenv("OPSPILOT_ASSISTANT_EXPERIMENT_ID", raising=False)
    constructed = []
    monkeypatch.setattr(investigation_updates, "input_classifier_model", lambda *args, **kwargs: constructed.append(args))

    prepare_s3_fixture(demo_db, "DELIVERED_PENDING", order_id="bridge-order", contract_version=2)
    app = create_app(db_path=demo_db, start_worker=False, expected_origin=ORIGIN,
                     credentials={"support-a": PASSWORD})
    with TestClient(app) as client:
        login = client.post("/api/auth/login", headers={"Origin": ORIGIN},
                            json={"actor_id": "support-a", "password": PASSWORD})
        assert login.status_code == 200
        headers = {"Origin": ORIGIN, "X-CSRF-Token": login.json()["csrf_token"]}
        session = client.post("/api/sessions", headers=headers).json()["session_id"]
        binding = client.post(
            f"/api/sessions/{session}/assistant/order",
            headers={**headers, "Idempotency-Key": "bind"},
            json={"order_id": "bridge-order", "initial_message": "Investigate the callback"},
        )
        assert binding.status_code == 202, binding.text
        task = binding.json()["task_id"]
        review_url = f"/api/tasks/{task}/condition-review"
        response = client.get(review_url)
        assert response.status_code == 200, response.text
        assert response.json() == {"active": [], "review": None}

        accepted = client.post(
            f"/api/sessions/{session}/assistant/messages",
            headers={**headers, "Idempotency-Key": "review-source"},
            json={"task_id": task, "body": "整理当前任务条件"},
        )
        assert accepted.status_code == 202, accepted.text
        source_id = accepted.json()["message_id"]
        response = client.post(review_url, headers={**headers, "Idempotency-Key": source_id},
                               json={"source_message_id": source_id})
        assert response.status_code == 200, response.text
        review = response.json()["review"]
        assert review["status"] == "FAILED" and review["reason"] == "MODEL_CONFIGURATION_MISSING"
        assert constructed == []
        with connect(demo_db) as connection:
            assert connection.execute("SELECT COUNT(*) FROM investigation_update_attempts").fetchone()[0] == 0


@pytest.fixture
def bridge(demo_db, tmp_path, monkeypatch):
    for key in ("LANGSMITH_TRACING", "LANGCHAIN_TRACING_V2"):
        monkeypatch.setenv(key, "false")
    for key, value in {
        "OPSPILOT_ASSISTANT_PROVIDER_ENABLED": "1", "OPSPILOT_ASSISTANT_EXPERIMENT_ID": "AR-02-LIVE-01",
        "OPSPILOT_MODEL_NAME": "deepseek-flash", "OPSPILOT_MODEL_API_KEY": "offline-fixture-key",
        "OPSPILOT_MODEL_BASE_URL": "https://api.deepseek.com", "OPSPILOT_CONTEXT_STRATEGY": "HYBRID",
        "OPSPILOT_CONTEXT_INPUT_BUDGET_TOKENS": "12000",
    }.items():
        monkeypatch.setenv(key, value)
    prepare_s3_fixture(demo_db, "DELIVERED_PENDING", order_id="p002-order", contract_version=2)
    output = Path(os.environ.get("OPSPILOT_BRIDGE_EVIDENCE", str(tmp_path))) / tmp_path.name
    output.mkdir(parents=True, exist_ok=False)
    wire = offline.BridgeWire(output)
    app = create_app(db_path=demo_db, start_worker=False, expected_origin=ORIGIN,
                     credentials={"support-a": PASSWORD}, condition_model_factory=wire.review_factory)
    owner = tc.trusted_identity(demo_db, "support-a")
    epoch = tc.register_worker_owner(demo_db, frozen.WORKER, os.getpid())
    with TestClient(app) as client:
        login = client.post("/api/auth/login", headers={"Origin": ORIGIN},
                            json={"actor_id": "support-a", "password": PASSWORD})
        headers = {"Origin": ORIGIN, "X-CSRF-Token": login.json()["csrf_token"]}
        client.headers.update(headers)
        session = client.post("/api/sessions", headers=headers).json()["session_id"]

        def post(path, key, payload, status=202):
            response = client.post(path, headers={**headers, "Idempotency-Key": key}, json=payload)
            assert response.status_code == status, response.text
            return response.json()

        def message(task, key, text):
            return post(f"/api/sessions/{session}/assistant/messages", key, {"body": text, "task_id": task})

        def bind(key, text):
            return post(f"/api/sessions/{session}/assistant/order", key,
                        {"order_id": "p002-order", "initial_message": text})

        def dispatch(label, receipt):
            wire.target = {"case": label, "run_id": receipt["run_id"], "task_id": receipt["task_id"]}
            asyncio.run(_dispatch_run(
                demo_db, tmp_path / "checkpoint.sqlite", frozen.WORKER, "executor-a",
                frozen.persisted_run(demo_db, receipt["run_id"]), epoch, assistant_model_factory=wire.factory,
            ))
            assert frozen.persisted_run(demo_db, receipt["run_id"])["status"] == "SUCCEEDED"
            return wire.calls[-1]

        def discover(task, source):
            wire.target = {"case": "review", "task_id": task, "source_message_id": source}
            previous = len(wire.calls)
            start = time.perf_counter()
            state = post(f"/api/tasks/{task}/condition-review", source, {"source_message_id": source}, 200)
            if len(wire.calls) > previous:
                wire.calls[-1]["elapsed_ms"] = round((time.perf_counter() - start) * 1000, 2)
            return state

        def confirm(task, review, ids, status=200):
            key = review["operation_id"]
            return post(f"/api/tasks/{task}/condition-review/{review['id']}/confirm", key,
                        {"operation_id": key, "selected_ids": ids}, status)

        def apply(receipt):
            tc.claim_task_run(demo_db, owner, receipt["run_id"])
            state = tc.apply_pending_critical_inputs(demo_db, owner, receipt["run_id"])
            tc.finish_task_run(demo_db, owner, receipt["run_id"], "WAITING_INPUT")
            return state

        yield client, message, bind, dispatch, discover, confirm, apply, wire, output


def _active_wire(wire):
    blocks = [item["content"] for item in wire["request"]["messages"] if
              item["role"] == "system" and item["content"].startswith("CURRENT TASK CONDITIONS")]
    return json.loads(blocks[0][blocks[0].index("["):]) if blocks else []


def test_full_recovery_from_frozen_24_turns(demo_db, bridge):
    client, message, bind, dispatch, discover, confirm, apply, wire, output = bridge
    protected = frozen.protected_counts(demo_db)
    message(None, "public", frozen.PUBLIC)
    foreign = bind("foreign", frozen.FOREIGN)
    bound = bind("bound", frozen.GOAL)
    task = bound["task_id"]
    configure_s3_experiment_budget(demo_db, task, 16, 10)
    schedule = [bound]
    sources = {}
    by_turn = dict(zip((2, 4, 6, 8), frozen.CONDITIONS))
    for index in range(2, 25):
        filler = f"Turn {index} compares ordinary support labels. " + (
            "A sample status page labels accepted requests and displays ordinary maintenance notes. " * 49
        )
        text = frozen.FINAL if index == 24 else by_turn.get(index, filler)
        entry = message(task, f"turn-{index}", text)
        schedule.append(entry)
        if index in by_turn:
            sources[text] = entry
    for index, entry in enumerate(schedule, 1):
        before = dispatch(f"turn-{index}", entry)
    assert not _active_wire(before)
    before_coverage = frozen.scan_answer(before, frozen.CONDITIONS)
    # R2 may retain E7 in the historical summary. Only formal confirmation
    # can place a requirement in the active block, checked above and below.
    outgoing = [call for call in wire.calls if call["phase"] == "compression"]
    assert len(outgoing) >= 2
    url = f"/api/tasks/{task}/condition-review"
    assert client.get(url).json() == {"active": [], "review": None}
    assert all(call["phase"] != "discovery" for call in wire.calls)
    review = discover(task, schedule[-1]["message_id"])["review"]
    assert review["status"] == "PENDING_CONFIRMATION"
    assert {row["source_text"] for row in review["candidates"]} == set(sources)
    assert all(row["sequence"] == sources[row["source_text"]]["sequence"] for row in review["candidates"])
    assert review["partial"] and review["coverage"]["excerpted"] > 0
    discovery_wire = wire.calls[-1]
    assert frozen.FOREIGN not in json.dumps(discovery_wire)
    assert discovery_wire["request"]["max_tokens"] == 640
    assert client.get(url).json()["review"] == review
    assert discover(task, schedule[-1]["message_id"])["review"] == review
    assert sum(call["phase"] == "discovery" for call in wire.calls) == 1
    assert client.get(f"/api/tasks/{task}/investigation-updates").json() == {"items": []}

    selected = [row["id"] for row in review["candidates"]]
    legacy = client.post(
        f"/api/tasks/{task}/investigation-updates/{review['id']}/confirm",
        headers={"Idempotency-Key": review["operation_id"]},
        json={"operation_id": review["operation_id"], "expected_control_revision": 0},
    )
    assert legacy.json() == {"code": "UPDATE_PROPOSAL_NOT_FOUND"}
    first = confirm(task, review, selected)
    assert confirm(task, review, selected[::-1]) == first
    confirm(task, review, selected[:1], 409)
    with connect(demo_db) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM commands WHERE target_ref=? AND idempotency_key=?",
            (task, review["operation_id"]),
        ).fetchone()[0] == 1
        assert connection.execute(
            "SELECT COUNT(*) FROM task_runs WHERE command_id=?", (first["command_id"],),
        ).fetchone()[0] == 1
        usage = connection.execute(
            "SELECT input_tokens,output_tokens FROM investigation_update_attempts WHERE assessment_id=?",
            (review["id"],),
        ).fetchone()
        assert tuple(usage) == (discovery_wire["sdk_message_token_estimate"],
                                discovery_wire["returned_content_token_estimate"])
    assert client.get(url).json()["active"] == []
    applied = apply(first)
    assert applied["expected_control_revision"] == 2
    assert client.get(url).json()["review"]["application_state"] == "APPLIED_TO_RUN"
    after = dispatch("after-confirm", message(task, "after-confirm", frozen.FINAL))
    active = _active_wire(after)
    assert {item["text"] for item in active} == set(frozen.CONDITIONS)
    assert all(item["source_message_id"] == sources[item["text"]]["message_id"] for item in active)
    assert frozen.PUBLIC in json.dumps(after) and frozen.FOREIGN not in json.dumps(after)
    assert foreign["task_id"] != task

    for label, text, action in (
        ("hypothesis", frozen.HYPOTHESIS, "HYPOTHESIS"),
        ("replace", frozen.FULL_DAY, "REPLACE"),
        ("withdraw", frozen.WITHDRAW, "REVOKE"),
    ):
        source = message(task, label, text)
        proposed = discover(task, source["message_id"])["review"]
        candidate = next(row for row in proposed["candidates"] if row["source_text"] == text)
        assert candidate["action"] == action
        assert all(row["action"] != "ADD" for row in proposed["candidates"])
        if action == "HYPOTHESIS":
            assert proposed["status"] == "NO_UPDATE"
            assert {row["text"] for row in client.get(url).json()["active"]} == set(frozen.CONDITIONS)
            continue
        applied = apply(confirm(task, proposed, [candidate["id"]]))
        assert applied["inputs"]
        new_answer = dispatch(label, message(task, f"{label}-continue", frozen.FINAL))
        latest = {row["item_id"]: row for row in _active_wire(new_answer)}
        if action == "REPLACE":
            assert latest["time"]["text"] == frozen.FULL_DAY
            assert all(latest[item["item_id"]] == item for item in active if item["item_id"] != "time")
            active = list(latest.values())
        else:
            assert latest == {item["item_id"]: item for item in active if item["item_id"] != "report"}

    for index, text in enumerate(frozen.UNCONFIRMED):
        ambiguous = message(task, f"ambiguous-{index}", text)
    conflict = discover(task, ambiguous["message_id"])["review"]
    conflicts = [item for item in conflict["candidates"] if item["source_text"] in frozen.UNCONFIRMED]
    assert len(conflicts) == 2 and all(item["action"] == "CONFLICT" for item in conflicts)
    confirm(task, conflict, [conflicts[0]["id"]], 409 if conflict["status"] == "NO_UPDATE" else 400)
    cancelled = client.post(
        f"/api/tasks/{task}/condition-review/{conflict['id']}/cancel",
        headers={"Idempotency-Key": conflict["operation_id"]}, json={"operation_id": conflict["operation_id"]},
    )
    assert cancelled.status_code == 200 and cancelled.json()["review"]["status"] == "CANCELLED"
    ordinary = message(task, "plain-202", offline.HTTP_202)
    count = sum(call["phase"] == "discovery" for call in wire.calls)
    answer = dispatch("plain-202", ordinary)
    assert answer["mock_response"] == offline.EXPLANATION
    assert sum(call["phase"] == "discovery" for call in wire.calls) == count
    assert frozen.protected_counts(demo_db) == protected
    frozen.save(output / "results.json", {
        "bound_turns": 24, "compression": len(outgoing), "before": before, "discovery": discovery_wire,
        "before_coverage": before_coverage,
        "after": after, "candidate_review": review, "active": client.get(url).json()["active"], "protected": protected,
    })


def test_partial_and_budget_exhaustion_preserve_ordinary_route(demo_db, bridge):
    client, message, bind, _, discover, _, _, wire, _ = bridge
    task = bind("limited", frozen.GOAL)["task_id"]
    for index in range(50):
        message(task, f"padding-{index}", f"Ordinary investigation reference {index}.")
    invalid = message(task, "invalid-source", frozen.CONDITIONS[0])
    with connect(demo_db) as connection:
        connection.execute("UPDATE messages SET body='invalidated' WHERE message_id=?", (invalid["message_id"],))
    for index in range(8):
        anchor = message(task, f"review-{index}", frozen.FINAL)
        result = discover(task, anchor["message_id"])["review"]
        assert result["partial"] and result["coverage"]["older_history_exists"] and result["coverage"]["invalid"] == 1
    last = message(task, "over-budget", frozen.FINAL)
    result = discover(task, last["message_id"])["review"]
    assert result["status"] == "FAILED" and result["reason"] == "TASK_AUX_PROVIDER_LIMIT"
    assert len(wire.calls) == 8 and all(call["phase"] == "discovery" for call in wire.calls)
    assert frozen.persisted_run(demo_db, last["run_id"])["blocked_reason"] is None
    assert client.get(f"/api/tasks/{task}/condition-review").json()["active"] == []


def test_invalidation_and_revoke_block_confirmation(demo_db, bridge):
    client, message, bind, _, discover, confirm, _, wire, _ = bridge
    task = bind("bound", frozen.GOAL)["task_id"]
    source = message(task, "source", frozen.CONDITIONS[0])
    anchor = message(task, "anchor", frozen.FINAL)
    ready = discover(task, anchor["message_id"])["review"]
    item, = ready["candidates"]
    with connect(demo_db) as connection:
        connection.execute("UPDATE messages SET body='invalidated' WHERE message_id=?", (source["message_id"],))
    displayed = client.get(f"/api/tasks/{task}/condition-review").json()["review"]
    assert displayed["status"] == "STALE" and displayed["candidates"][0]["source_text"] is None
    confirm(task, ready, [item["id"]], 404)
    with connect(demo_db) as connection:
        connection.execute(
            """UPDATE principal_scope_grants SET granted_scopes_json='[]', grant_version=grant_version+1
               WHERE tenant_id='tenant-a' AND principal_id=(SELECT principal_id FROM task_bindings WHERE task_id=?)""",
            (task,),
        )
        control = connection.execute("SELECT control_revision FROM task_controls WHERE task_id=?", (task,)).fetchone()
        assert control[0] == 0
    assert client.get(f"/api/tasks/{task}/condition-review").status_code == 404
    confirm(task, ready, [item["id"]], 404)
    assert len(wire.calls) == 1


def test_migrates_v18_proposal_storage(demo_db):
    with connect(demo_db) as connection:
        connection.execute("ALTER TABLE investigation_update_assessments DROP COLUMN condition_review_json")
        connection.execute("PRAGMA user_version = 18")
    initialize(demo_db)
    initialize(demo_db)
    with connect(demo_db) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 25
        assert [entry["name"] for entry in connection.execute(
            "PRAGMA table_info(investigation_update_assessments)"
        )].count("condition_review_json") == 1
