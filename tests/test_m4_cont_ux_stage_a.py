"""CONT-UX A: deterministic reservations, real SQLite/API/MCP; no paid Provider.

Gold is offline and unchanged. A model double demonstrates execution contracts,
not real LLM quality. Trace rows are emitted only after actual test observations.
"""
from __future__ import annotations

import asyncio
import json
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from opspilot.domain.database import connect, initialize, reset_fixture
from opspilot.domain.d2 import BudgetExhausted, ScopeDenied, attempt_counts, finish_attempt, reserve_attempt, task_attempt_limits
from opspilot.domain.investigation_updates import complete_assessment, reserve_assessment
from opspilot.domain.s3 import prepare_s3_fixture
from opspilot.domain.task_control import (
    TaskControlError, admit_task_message, claim_task_run, create_session,
    create_task_with_initial_run, finish_task_run, register_worker_owner, trusted_identity,
)


def emit(case, **fields):
    payload = {"case_id": case, "evidence_level": "deterministic_actual_test_observation", **fields}
    print("CONTUX_TRACE " + json.dumps(payload, ensure_ascii=False, default=str), flush=True)
    destination = os.environ.get("OPSPILOT_CONTUX_TRACE_PATH")
    if destination:
        with open(destination, "a", encoding="utf-8") as stream:
            stream.write(json.dumps(payload, ensure_ascii=False, default=str) + "\n")


def new_task(tmp_path, name="budget", *, claim=True):
    db = tmp_path / f"{name}.sqlite3"
    reset_fixture(db, "S1_POS")
    prepare_s3_fixture(db, "DELIVERED_PENDING", contract_version=2, queue_age_seconds=1)
    identity = trusted_identity(db, "support-a")
    session = create_session(db, identity)
    task = create_task_with_initial_run(
        db, identity, session_id=str(session["session_id"]), service_id="orders-async-demo",
        integration_id="async-integration-a", ticket_id="CONTUX-A", s3_order_id="async-order",
        initial_message="订单 200 但回调尚未完成，请核对。", idempotency_key="initial",
    )
    if claim:
        claim_task_run(db, identity, str(task["run_id"]))
    return db, identity, task


def route(db, identity, task, key, *, action="INVESTIGATE", text="请重新核对当前接收状态。"):
    source = admit_task_message(
        db, identity, session_id=str(task["session_id"]), task_id=str(task["task_id"]),
        input_kind="CHAT_READONLY", body=text, idempotency_key=key,
        defer_task_chat_until_classified=True,
    )
    mid = str(source["message_id"])
    reservation = reserve_assessment(db, identity, task_id=str(task["task_id"]),
                                     source_message_id=mid, idempotency_key=mid, model_id="deterministic-no-provider")
    if reservation.get("should_call_model"):
        prepared = reservation["prepared"]
        result = complete_assessment(
            db, identity=identity, assessment_id=prepared["assessment_id"], attempt_id=prepared["attempt_id"],
            classification={"intent":"FOLLOW_UP", "change_summary":"", "readonly_action":action},
        )
    else:
        result = reservation
    return source, result


def reserve(db, task_id, run_id, kind="MODEL", *, limit=999):
    from uuid import uuid4
    return reserve_attempt(db, task_id, kind, limit, call_id=f"contux-{uuid4()}", run_id=run_id)


def ledger(db, task_id):
    with connect(db) as c:
        return {"budget":dict(c.execute("SELECT * FROM task_execution_budgets WHERE task_id=?",(task_id,)).fetchone()),
                "attempts":[dict(r) for r in c.execute("SELECT * FROM d2_attempts WHERE task_id=? ORDER BY rowid",(task_id,))]}


def test_a01_new_followup_after_initial_limit_and_operation_replay(tmp_path):
    db, identity, task = new_task(tmp_path)
    tid, first = str(task["task_id"]), str(task["run_id"])
    for _ in range(8):
        reserve(db, tid, first, limit=8)
    finish_task_run(db, identity, first, "WAITING_INPUT")
    source, routed = route(db, identity, task, "followup-one")
    run = str(routed["investigation_run_id"])
    duplicate, routed_again = route(db, identity, task, "followup-one")
    assert source["message_id"] == duplicate["message_id"]
    assert routed_again["investigation_run_id"] == run
    claim_task_run(db, identity, run)
    attempt, _ = reserve(db, tid, run, limit=task_attempt_limits(db, tid)["MODEL"])
    emit("A01", source=source, routed=routed, replay=routed_again, new_attempt_id=attempt, ledger=ledger(db, tid))
    assert attempt_counts(db, tid)["MODEL"] == 9
    assert task_attempt_limits(db, tid) == {"MODEL":24, "MCP":18}
    with connect(db) as c:
        assert c.execute("SELECT policy_version FROM task_execution_budgets WHERE task_id=?",(tid,)).fetchone()[0] == "CONTUX_S3_V1"
    finish_task_run(db, identity, run, "WAITING_INPUT")
    second, routed_two = route(db, identity, task, "followup-two")
    assert second["message_id"] != source["message_id"] and routed_two["investigation_run_id"] != run


@pytest.mark.parametrize("followup,kind,cap", [(False,"MODEL",8),(False,"MCP",6),(True,"MODEL",4),(True,"MCP",3)])
def test_a02_run_limit_is_trusted_not_the_caller_limit(tmp_path, followup, kind, cap):
    db, identity, task = new_task(tmp_path)
    tid, run = str(task["task_id"]), str(task["run_id"])
    if followup:
        finish_task_run(db, identity, run, "WAITING_INPUT")
        _, routed = route(db, identity, task, "followup")
        run = str(routed["investigation_run_id"])
        claim_task_run(db, identity, run)
    for _ in range(cap):
        reserve(db, tid, run, kind)
    try:
        reserve(db, tid, run, kind)
    except BudgetExhausted as error:
        emit("A02", run_id=run, kind=kind, cap=cap, reason=str(error), ledger=ledger(db, tid))
        assert getattr(error, "reason_code", "") == f"RUN_{kind}_LIMIT"
    else:
        pytest.fail("Caller limit=999 bypassed the trusted per-Run cap")


def _race(db, tid, run, kind="MODEL"):
    barrier = threading.Barrier(2)
    def contender(_):
        barrier.wait(timeout=5)
        try:
            return {"accepted":True, "attempt_id":reserve(db,tid,run,kind)[0]}
        except BudgetExhausted as error:
            return {"accepted":False,"reason":getattr(error,"reason_code",str(error))}
    with ThreadPoolExecutor(max_workers=2) as pool:
        return list(pool.map(contender, range(2)))


def test_a02_two_connections_cannot_overfill_run(tmp_path):
    db, identity, task = new_task(tmp_path)
    finish_task_run(db, identity, str(task["run_id"]), "WAITING_INPUT")
    _, result = route(db, identity, task, "race")
    tid, run = str(task["task_id"]), str(result["investigation_run_id"])
    claim_task_run(db, identity, run)
    for _ in range(3): reserve(db, tid, run)
    outcomes = _race(db, tid, run)
    emit("A02-RUN-RACE", outcomes=outcomes, ledger=ledger(db,tid))
    assert sum(x["accepted"] for x in outcomes) == 1


def test_a02_task_limit_survives_many_distinct_followups_and_race(tmp_path):
    db, identity, task = new_task(tmp_path)
    tid, run = str(task["task_id"]), str(task["run_id"])
    for _ in range(7): reserve(db,tid,run,limit=8)
    finish_task_run(db,identity,run,"WAITING_INPUT")
    for i in range(4):
        _, routed = route(db,identity,task,f"intent-{i}")
        run=str(routed["investigation_run_id"]); claim_task_run(db,identity,run)
        for _ in range(4): reserve(db,tid,run)
        finish_task_run(db,identity,run,"WAITING_INPUT")
    _, routed = route(db,identity,task,"last-intent")
    run=str(routed["investigation_run_id"]); claim_task_run(db,identity,run)
    outcomes=_race(db,tid,run)
    emit("A02-TASK-RACE",outcomes=outcomes,ledger=ledger(db,tid))
    assert sum(x["accepted"] for x in outcomes)==1 and attempt_counts(db,tid)["MODEL"]==24
    assert next(x for x in outcomes if not x["accepted"])["reason"]=="TASK_MODEL_LIMIT"


def test_a03_migration_does_not_upgrade_existing_task_and_s1_stays_legacy(tmp_path):
    db, identity, task = new_task(tmp_path, claim=False)
    tid=str(task["task_id"])
    # Reconstruct the actual v16 budget schema, not just its version label.
    with connect(db) as c:
        columns={row["name"] for row in c.execute("PRAGMA table_info(task_execution_budgets)")}
        for name in ("policy_version","aux_provider_limit"):
            if name in columns: c.execute(f"ALTER TABLE task_execution_budgets DROP COLUMN {name}")
        c.execute("UPDATE task_execution_budgets SET model_limit=8,mcp_limit=6")
        c.execute("PRAGMA user_version=16")
        before=dict(c.execute("SELECT * FROM task_execution_budgets WHERE task_id=?",(tid,)).fetchone())
    initialize(db)
    with connect(db) as c:
        after=dict(c.execute("SELECT * FROM task_execution_budgets WHERE task_id=?",(tid,)).fetchone())
        assert after["policy_version"]=="LEGACY_V1"
        assert after["aux_provider_limit"] is None
        assert all(after[k]==v for k,v in before.items())
    assert task_attempt_limits(db,tid)=={"MODEL":8,"MCP":6}
    session=create_session(db,identity)
    s1=create_task_with_initial_run(db,identity,session_id=str(session["session_id"]),service_id="orders-demo",
         integration_id="integration-a",ticket_id="LEGACY",initial_message="401",idempotency_key="s1")
    assert task_attempt_limits(db,str(s1["task_id"]))=={"MODEL":8,"MCP":6}
    emit("A03",legacy_before=before,legacy_after=after,new_s1=s1)


def test_a03_cross_task_and_missing_run_cannot_spend_new_policy(tmp_path):
    db, _, task = new_task(tmp_path)
    tid=str(task["task_id"])
    with pytest.raises(ScopeDenied): reserve_attempt(db,tid,"MODEL",999,call_id="no-run")
    with pytest.raises(ScopeDenied): reserve(db,tid,"foreign-run")
    with connect(db) as c:
        c.execute("UPDATE task_execution_budgets SET model_limit=25 WHERE task_id=?",(tid,))
    with pytest.raises(ScopeDenied): reserve(db,tid,str(task["run_id"]))
    assert attempt_counts(db,tid)=={"MODEL":0,"MCP":0}


def test_a04_auxiliary_classifiers_include_reserved_failures_and_stop_durably(tmp_path):
    from opspilot.domain.investigation_updates import fail_assessment
    db, identity, task = new_task(tmp_path)
    finish_task_run(db,identity,str(task["run_id"]),"WAITING_INPUT")
    tid=str(task["task_id"])
    reservations=[]
    for i in range(8):
        source=admit_task_message(db,identity,session_id=str(task["session_id"]),task_id=tid,
           input_kind="CHAT_READONLY",body="这是什么意思？",idempotency_key=f"aux-{i}",defer_task_chat_until_classified=True)
        mid=str(source["message_id"])
        r=reserve_assessment(db,identity,task_id=tid,source_message_id=mid,idempotency_key=mid,model_id="no-provider")
        assert r.get("should_call_model")
        reservations.append(r["prepared"]["attempt_id"])
        if i % 2:
            fail_assessment(db,assessment_id=r["prepared"]["assessment_id"],attempt_id=r["prepared"]["attempt_id"],error_code="NETWORK_OUTCOME_UNKNOWN")
    source=admit_task_message(db,identity,session_id=str(task["session_id"]),task_id=tid,
       input_kind="CHAT_READONLY",body="再次解释",idempotency_key="aux-over",defer_task_chat_until_classified=True)
    mid=str(source["message_id"])
    over=reserve_assessment(db,identity,task_id=tid,source_message_id=mid,idempotency_key=mid,model_id="no-provider")
    emit("A04",attempt_ids=reservations,over=over,source=source)
    assert over.get("should_call_model") is False and over["fallback_reason"]=="TASK_AUX_PROVIDER_LIMIT"
    with connect(db) as c:
        assert c.execute("SELECT COUNT(*) FROM investigation_update_attempts").fetchone()[0]==8
        run=c.execute("SELECT status,blocked_reason FROM task_runs WHERE run_id=?",(source["run_id"],)).fetchone()
        assert tuple(run)==("FAILED","TASK_AUX_PROVIDER_LIMIT")
        notice=c.execute("SELECT body FROM messages WHERE command_id=?",(f"budget-notice:{source['run_id']}",)).fetchone()
        assert notice and notice[0].strip() and "未" in notice[0]
    replay=reserve_assessment(db,identity,task_id=tid,source_message_id=mid,idempotency_key=mid,model_id="no-provider")
    assert not replay.get("should_call_model")


def test_a05_run_exhaustion_has_nonempty_precise_readonly_delivery(tmp_path):
    from opspilot.s3_investigation import S3Nodes
    db, identity, task = new_task(tmp_path)
    finish_task_run(db,identity,str(task["run_id"]),"WAITING_INPUT")
    _, routed=route(db,identity,task,"exhausted")
    tid,run=str(task["task_id"]),str(routed["investigation_run_id"])
    claim_task_run(db,identity,run)
    for _ in range(4): reserve(db,tid,run,limit=24)
    class NoProvider:
        async def ainvoke(self,_): raise AssertionError("Provider called at Run cap")
    node=S3Nodes(db,tid,run,NoProvider(),"no-provider",None,[],readonly_followup=True,memory_enabled=False)
    asyncio.run(node.report({"evidence_ids":[],"tool_observations":[]}))
    with connect(db) as c:
        row=dict(c.execute("SELECT * FROM c1_readonly_followup_runs WHERE run_id=?",(run,)).fetchone())
        assert row["answer_text"].strip() and row["result_state"]=="PARTIAL"
        assert row["reason_code"]=="RUN_MODEL_LIMIT"
        assert c.execute("SELECT COUNT(*) FROM s3_diagnoses").fetchone()[0]==0
    emit("A05",result=row,ledger=ledger(db,tid))
