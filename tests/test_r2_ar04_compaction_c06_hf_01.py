"""Offline regression for C06's first context preflight budget failure.

Uses the exact AuditFixtureModel and seed generator from the frozen AR-04
compaction audit. It never constructs a real Provider.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


def _audit_harness():
    name = "r2_ar04_compaction_audit_harness"
    if name in sys.modules:
        return sys.modules[name]
    path = (
        Path(__file__).resolve().parents[1]
        / "docs/evidence/r2-ar04-compaction-audit-01/run_audit.py"
    )
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _exercise_case(
    *, monkeypatch, tmp_path, case_id: str, strategy: str, turns: int,
    seed_size: int, first_body: str | None, final_body: str,
    final_budget: int = 12000, pad_answer_tokens: int = 0,
    preflight_error: str | None = None,
):
    from fastapi.testclient import TestClient

    import opspilot.assistant as assistant
    from opspilot.domain.database import connect, reset_fixture
    from opspilot.web.app import create_app

    audit = _audit_harness()
    for key, value in {
        "OPSPILOT_CONTEXT_WINDOW_TOKENS": "16384",
        "OPSPILOT_CONTEXT_INPUT_BUDGET_TOKENS": "12000",
        "OPSPILOT_CONTEXT_OUTPUT_RESERVE_TOKENS": "512",
        "OPSPILOT_CONTEXT_SAFETY_MARGIN_TOKENS": "1024",
        "OPSPILOT_CONTEXT_STRATEGY": "HYBRID",
        "OPSPILOT_ASSISTANT_PROVIDER_ENABLED": "0",
    }.items():
        monkeypatch.setenv(key, value)

    db_path = tmp_path / f"{case_id}-domain.sqlite3"
    checkpoint_path = tmp_path / f"{case_id}-checkpoint.sqlite3"
    reset_fixture(db_path, "S1_POS")
    audit.ACTIVE_AUDIT = {"tmp_root": str(tmp_path / f"{case_id}-runs"), "target_run_id": None}
    audit._env_budget(context_window=50000, input_limit=45000)
    app = create_app(
        db_path=db_path,
        checkpoint_db_path=checkpoint_path,
        start_worker=True,
        credentials=audit.PASSWORDS,
        expected_origin=audit.ORIGIN,
        assistant_model_factory=lambda: audit.AuditFixtureModel(
            mode="s01", pad_tokens=pad_answer_tokens,
        ),
    )

    with TestClient(app) as client:
        headers = audit._login(client)
        session_id = client.post("/api/sessions", headers=headers).json()["session_id"]
        seeded = audit._seed_turns(
            client, headers, session_id, count=turns, size_tokens=seed_size,
            first_body=first_body,
        )
        monkeypatch.setenv("OPSPILOT_CONTEXT_STRATEGY", strategy)
        audit._env_budget(input_limit=final_budget)
        (instrumentation, chat, patched_assistant, worker, real_prepare,
         patched_client, real_estimate, real_worker_error) = audit._patch_case_instrumentation(case_id)
        audit.ACTIVE_AUDIT["target_run_id"] = None
        if preflight_error:
            def raise_programming_error(self):
                raise RuntimeError(preflight_error)
            monkeypatch.setattr(assistant.Loop, "context", raise_programming_error)
        try:
            accepted, waited = audit._create_run(
                client, headers, session_id, f"{case_id}-final", final_body,
            )
            run_id = str(accepted["run_id"])
            run_view = client.get(f"/api/runs/{run_id}", headers=headers).json()
            messages_view = client.get(
                f"/api/sessions/{session_id}/messages?limit=500", headers=headers,
            ).json()["items"]
        finally:
            audit._restore_instrumentation(
                chat, patched_assistant, worker, real_prepare, patched_client,
                real_estimate, real_worker_error,
            )

    run_id = str(accepted["run_id"])
    with connect(db_path) as connection:
        task_run = dict(connection.execute(
            "SELECT status,blocked_reason,source_message_id FROM task_runs WHERE run_id=?",
            (run_id,),
        ).fetchone())
        first_user = dict(connection.execute(
            "SELECT message_id,body,body_digest FROM messages WHERE session_id=? AND sequence=1",
            (session_id,),
        ).fetchone())
        model_rows = connection.execute(
            "SELECT request_json FROM assistant_calls WHERE run_id=? AND kind='MODEL' ORDER BY created_at,rowid",
            (run_id,),
        ).fetchall()
        all_assistant_calls = int(connection.execute(
            "SELECT COUNT(*) FROM assistant_calls WHERE run_id=?", (run_id,),
        ).fetchone()[0])
        compression_rows = [dict(row) for row in connection.execute(
            "SELECT attempt_no,status,error_class FROM context_compression_attempts WHERE run_id=? ORDER BY attempt_no",
            (run_id,),
        )]
        answer_count = int(connection.execute(
            "SELECT COUNT(*) FROM chat_run_answers WHERE run_id=?", (run_id,),
        ).fetchone()[0])
        delivery = connection.execute(
            "SELECT delivery_attempt_id FROM assistant_runs WHERE run_id=?", (run_id,),
        ).fetchone()
        notice_count = int(connection.execute(
            "SELECT COUNT(*) FROM messages WHERE command_id=?", (f"budget-notice:{run_id}",),
        ).fetchone()[0])
        notice_event_count = int(connection.execute(
            "SELECT COUNT(*) FROM domain_outbox WHERE source_id=? AND event_kind='CHAT_BUDGET_STOP'",
            (run_id,),
        ).fetchone()[0])
        failed_event_count = int(connection.execute(
            "SELECT COUNT(*) FROM domain_outbox WHERE source_id=? AND event_kind='RUN_STATUS_FAILED'",
            (run_id,),
        ).fetchone()[0])

    return {
        "db_path": db_path,
        "session_id": session_id,
        "run_id": run_id,
        "accepted": accepted,
        "waited": waited,
        "run_view": run_view,
        "messages_view": messages_view,
        "seeded": seeded,
        "first_user": first_user,
        "task_run": task_run,
        "model_wires": [json.loads(row["request_json"]) for row in model_rows],
        "assistant_call_count": all_assistant_calls,
        "compression_attempts": compression_rows,
        "answer_count": answer_count,
        "delivery_attempt_id": delivery["delivery_attempt_id"] if delivery else None,
        "notice_count": notice_count,
        "notice_event_count": notice_event_count,
        "failed_event_count": failed_event_count,
        "instrumentation": instrumentation,
    }


def test_t01_t02_t03_c06_user_oversize_is_classified_visible_and_idempotent(
    monkeypatch, tmp_path,
):
    from opspilot.domain.context_engineering import estimate_text_tokens

    audit = _audit_harness()
    original = json.loads((Path(audit.RESULT_DIR) / "case_traces/C06_USER_OVERSIZE.json").read_text(encoding="utf-8"))
    original_user = next(
        message for message in original["persisted_messages"]
        if message["sequence"] == 1 and message["role"] == "USER"
    )
    same_first_body = audit.padded("[GT:GOAL] oversized untrusted user source ", 5900)
    assert estimate_text_tokens(same_first_body) >= 5900

    case = _exercise_case(
        monkeypatch=monkeypatch, tmp_path=tmp_path, case_id="C06_USER_OVERSIZE",
        strategy="ROLLING_SUMMARY", turns=14, seed_size=40,
        first_body=same_first_body, final_body="触发用户超长材料边界。",
        final_budget=12000,
    )
    run_id = case["run_id"]
    assert case["run_view"]["status"] == "FAILED"
    assert case["run_view"]["waiting_reason"] == "SUMMARY_SOURCE_EXCEEDS_COMPRESSION_BUDGET"
    assert case["task_run"]["blocked_reason"] == "SUMMARY_SOURCE_EXCEEDS_COMPRESSION_BUDGET"
    assert not case["instrumentation"].get("worker_errors")
    assert case["first_user"]["body"] == original_user["body"]
    assert case["first_user"]["body_digest"] == original_user["body_digest"]
    assert case["model_wires"] == []
    assert case["assistant_call_count"] == 0
    assert case["compression_attempts"] == []
    assert case["answer_count"] == 0
    assert case["delivery_attempt_id"] is None
    assert case["notice_count"] == case["notice_event_count"] == 1
    assert case["failed_event_count"] == 1

    program_notices = [
        message for message in case["messages_view"]
        if message.get("answer_run_id") == run_id
        and message.get("answer_kind") == "PROGRAM_LIMIT"
    ]
    assert len(program_notices) == 1
    notice = program_notices[0]["body"]
    assert "程序生成" in notice
    assert "安全摘要输入预算" in notice
    assert "本轮未生成模型答复" in notice
    assert "原始消息" in notice and "静默删减" in notice
    assert "不代表模型已完成调查或任何业务处理" in notice
    from opspilot.assistant import _close_terminal_assistant_failure
    from opspilot.domain.context_engineering import ContextBudgetExceeded
    repeated_error = ContextBudgetExceeded(
        "SUMMARY_SOURCE_EXCEEDS_COMPRESSION_BUDGET", required_tokens=6176,
        input_budget_tokens=6000,
    )
    _close_terminal_assistant_failure(
        case["db_path"], "c06-hf01-repeat-closeout", run_id,
        repeated_error, repeated_error.code,
    )
    from opspilot.domain.database import connect
    with connect(case["db_path"]) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM messages WHERE command_id=?", (f"budget-notice:{run_id}",),
        ).fetchone()[0] == 1
        assert connection.execute(
            "SELECT COUNT(*) FROM domain_outbox WHERE source_id=? AND event_kind='CHAT_BUDGET_STOP'",
            (run_id,),
        ).fetchone()[0] == 1
        assert connection.execute(
            "SELECT COUNT(*) FROM domain_outbox WHERE source_id=? AND event_kind='RUN_STATUS_FAILED'",
            (run_id,),
        ).fetchone()[0] == 1


def test_t04_c06_assistant_excerpt_still_compresses_twice_and_answers(monkeypatch, tmp_path):
    audit = _audit_harness()
    original = json.loads((Path(audit.RESULT_DIR) / "case_traces/C06_ASSISTANT_EXCERPT.json").read_text(encoding="utf-8"))
    original_long_answer = next(
        message for message in original["persisted_messages"]
        if message["sequence"] == 2 and message["role"] == "ASSISTANT"
    )
    case = _exercise_case(
        monkeypatch=monkeypatch, tmp_path=tmp_path, case_id="C06_ASSISTANT_EXCERPT",
        strategy="ROLLING_SUMMARY", turns=14, seed_size=40,
        first_body="PAD_FIXTURE_ASSISTANT_RESULT first answer will be an oversized fixture answer.",
        final_body="触发助手历史摘要预算边界。", final_budget=12000,
        pad_answer_tokens=6400,
    )
    from opspilot.domain.database import connect
    with connect(case["db_path"]) as connection:
        actual_long_answer = connection.execute(
            "SELECT body_digest,body FROM messages WHERE session_id=? AND sequence=2",
            (case["session_id"],),
        ).fetchone()
    assert actual_long_answer["body_digest"] == original_long_answer["body_digest"]
    assert case["run_view"]["status"] == "SUCCEEDED"
    assert [item["status"] for item in case["compression_attempts"]] == ["SUCCEEDED", "SUCCEEDED"]
    assert case["answer_count"] == 1
    assert len(case["model_wires"]) == 3
    assert case["messages_view"][-1]["answer_kind"] == "CHAT_MODEL"


def test_t05_short_conversation_still_answers(monkeypatch, tmp_path):
    case = _exercise_case(
        monkeypatch=monkeypatch, tmp_path=tmp_path, case_id="T05_SHORT_CHAT",
        strategy="HYBRID", turns=0, seed_size=0, first_body=None,
        final_body="HTTP 202 的含义是什么？", final_budget=7000,
    )
    assert case["run_view"]["status"] == "SUCCEEDED"
    assert case["answer_count"] == 1
    assert case["compression_attempts"] == []


def test_t06_recent_window_remains_selection_without_summary(monkeypatch, tmp_path):
    case = _exercise_case(
        monkeypatch=monkeypatch, tmp_path=tmp_path, case_id="T06_RECENT_WINDOW",
        strategy="RECENT_WINDOW", turns=14, seed_size=40, first_body=None,
        final_body="只保留近期窗口。", final_budget=12000,
    )
    assert case["run_view"]["status"] == "SUCCEEDED"
    assert case["compression_attempts"] == []
    assert case["instrumentation"]["prep_calls"][0]["context_budget"]["strategy"] == "RECENT_WINDOW"
    answer_wire = case["model_wires"][-1]
    by_id = {
        item["message_id"]: item["sequence"]
        for item in _audit_harness()._messages(case["db_path"], case["session_id"])
    }
    selected_sequences = sorted(by_id[source_id] for source_id in answer_wire["selected_message_ids"])
    assert selected_sequences == list(range(18, 30))


def test_t08_ordinary_preflight_programming_error_is_not_budget_misclassified(
    monkeypatch, tmp_path,
):
    case = _exercise_case(
        monkeypatch=monkeypatch, tmp_path=tmp_path, case_id="T08_PROGRAMMING_ERROR",
        strategy="ROLLING_SUMMARY", turns=0, seed_size=0, first_body=None,
        final_body="普通短消息。", final_budget=12000,
        preflight_error="ordinary fixture programming error",
    )
    assert case["run_view"]["status"] == "FAILED"
    assert case["run_view"]["waiting_reason"] != "SUMMARY_SOURCE_EXCEEDS_COMPRESSION_BUDGET"
    assert case["run_view"]["waiting_reason"] == "WORKER_RUN_FAILED"
    assert case["instrumentation"]["prep_calls"] == []
    assert case["model_wires"] == []
    assert not any(
        "安全摘要输入预算" in message["body"]
        for message in case["messages_view"] if message["role"] == "ASSISTANT"
    )
