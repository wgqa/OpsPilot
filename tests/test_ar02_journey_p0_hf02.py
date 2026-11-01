"""AR-02-JOURNEY-P0-HF02 targeted closeout regressions."""
from __future__ import annotations

import json
import os
from collections import deque
from pathlib import Path

import pytest
from langchain_core.messages import AIMessage

from test_ar02_journey_p0 import JourneyFixtureModel, _wait_run
from test_ar02_journey_p0_hf01 import (
    ExplicitOrderProposalFixture,
    ReceiverAvailabilityFixture,
    _login,
)


def _capture_trace(case_id: str, records: list[dict]) -> None:
    target = os.environ.get("OPSPILOT_AR02_JOURNEY_HF02_TRACE")
    if not target:
        return
    path = Path(target)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as stream:
        for record in records:
            stream.write(json.dumps({"case_id": case_id, **record}, ensure_ascii=False, sort_keys=True) + "\n")


def test_unexposed_tool_is_failed_and_legacy_null_cannot_replay_or_enter_history(
    demo_db, tmp_path, monkeypatch
):
    from fastapi.testclient import TestClient
    from opspilot.domain import assistant as assistant_domain
    from opspilot.domain.database import connect
    from opspilot.domain.task_control import TaskControlError
    from opspilot.web.app import create_app
    from test_ar02_assistant import ORIGIN, PASSWORDS

    model = ExplicitOrderProposalFixture(mode="unused")
    app = create_app(
        db_path=demo_db,
        checkpoint_db_path=tmp_path / "hf02-unexposed.sqlite3",
        start_worker=True,
        credentials=PASSWORDS,
        expected_origin=ORIGIN,
        assistant_model_factory=lambda: model,
    )
    question = "请查询当前绑定订单的订单状态。"
    trace: list[dict] = []

    with TestClient(app) as client:
        headers = _login(client, ORIGIN, PASSWORDS)
        session_id = client.post("/api/sessions", headers=headers).json()["session_id"]
        accepted = client.post(
            f"/api/sessions/{session_id}/assistant/messages",
            headers={**headers, "Idempotency-Key": "hf02-unexposed-order-read"},
            json={"body": question},
        )
        assert accepted.status_code == 202, accepted.text
        item = accepted.json()
        run = _wait_run(client, item["run_id"])
        assert run["status"] == "SUCCEEDED"
        assert model.proposals == [{
            "name": "get_order_status",
            "args": {"reason": "按用户请求查询当前绑定订单状态"},
        }]
        assert "get_order_status" not in model.offered_tool_names

        with connect(demo_db) as connection:
            before_http = connection.execute("SELECT COUNT(*) FROM s3_http_observations").fetchone()[0]
            calls = connection.execute(
                "SELECT * FROM assistant_calls WHERE run_id=? AND kind='MCP'", (item["run_id"],)
            ).fetchall()
            assert len(calls) == 1
            call = dict(calls[0])
            request = json.loads(call["request_json"])
            assert request["name"] == "get_order_status"
            # RED against 990d977: this was recorded as OK with a JSON null result.
            assert call["status"] == "FAILED"
            result = json.loads(call["result_json"])
            assert result["error"] == "ASSISTANT_TOOL_NOT_EXPOSED"
            assert call["observation_id"] is None and call["evidence_id"] is None
            assert connection.execute(
                "SELECT COUNT(*) FROM d2_attempts WHERE run_id=?", (item["run_id"],)
            ).fetchone()[0] == 0
            assert connection.execute(
                "SELECT COUNT(*) FROM d2_tool_observations WHERE call_id=?", (call["call_id"],)
            ).fetchone()[0] == 0
            assert connection.execute("SELECT COUNT(*) FROM s3_http_observations").fetchone()[0] == before_http
            answer = connection.execute(
                "SELECT body FROM messages WHERE role='ASSISTANT' AND session_id=? ORDER BY sequence DESC LIMIT 1",
                (session_id,),
            ).fetchone()
            assert answer is not None
            assert "未返回可信业务事实" in answer["body"]

            # Recreate the legacy persisted state in this isolated test DB only.
            # An in-flight resumed Run must reject its cached null result.
            connection.execute(
                "UPDATE assistant_calls SET status='OK',result_json='null' WHERE call_id=?", (call["call_id"],)
            )
            connection.execute(
                "UPDATE task_runs SET status='RUNNING',ended_at=NULL WHERE run_id=?", (item["run_id"],)
            )

        with pytest.raises(TaskControlError) as replay_error:
            assistant_domain.reserve(
                demo_db,
                item["run_id"],
                "MCP",
                call["logical_key"],
                request,
                worker_id="",
            )
        assert replay_error.value.code == "ASSISTANT_CACHED_RESULT_INVALID"

        with connect(demo_db) as connection:
            history = assistant_domain.history_sources(
                connection,
                {
                    "session_id": session_id,
                    "tenant_id": "tenant-a",
                    "task_id": None,
                    "consumed_message_seq": 2,
                },
            )
        prior = next(record for record in history if record["run_id"] == item["run_id"])
        assert prior["current_source_valid"] is False
        assert prior["exclusion_reason"] == "ASSISTANT_SOURCE_RESULT_INVALID"
        assert prior["sources"] == []

    _capture_trace("HF02-01", [{
        "session_id": session_id,
        "message_id": item["message_id"],
        "run_id": item["run_id"],
        "question": question,
        "model_proposal": model.proposals[0],
        "offered_tools": model.offered_tool_names,
        "new_call_status": call["status"],
        "new_call_result": result,
        "no_d2_attempt_or_observation": True,
        "no_order_http_read": True,
        "legacy_null_replay": replay_error.value.code,
        "legacy_history_exclusion": prior,
        "evidence_level": "FORMAL_API_WORKER_FIXTURE_MODEL_AND_DOMAIN_CACHE_HISTORY",
    }])


def test_receiver_tool_failure_after_queued_observation_produces_unknown_not_success(
    demo_db, tmp_path, monkeypatch
):
    from fastapi.testclient import TestClient
    from opspilot.domain.database import connect
    from opspilot.domain.s3 import prepare_s3_fixture
    from opspilot.web.app import create_app
    from test_ar02_assistant import ORIGIN, PASSWORDS

    fixture = prepare_s3_fixture(
        demo_db, "DELIVERED_PENDING", order_id="hf02-receiver-order", contract_version=2,
    )
    event_id = fixture["transport_trace"][0]["request"]["event_id"]
    bind_model = JourneyFixtureModel(mode="s01")
    queued_model = ReceiverAvailabilityFixture(mode="unused", query_receiver=True)
    failed_model = ReceiverAvailabilityFixture(mode="unused", query_receiver=True)
    models = deque([bind_model, queued_model, failed_model])
    app = create_app(
        db_path=demo_db,
        checkpoint_db_path=tmp_path / "hf02-receiver-failure.sqlite3",
        start_worker=True,
        credentials=PASSWORDS,
        expected_origin=ORIGIN,
        assistant_model_factory=lambda: models.popleft(),
    )
    question = "请依据当前 Receiver 查询，说明同一订单回调是否已经处理完成；若查询失败请明确说明无法确认。"
    trace: list[dict] = []

    with TestClient(app) as client:
        headers = _login(client, ORIGIN, PASSWORDS)
        session_id = client.post("/api/sessions", headers=headers).json()["session_id"]
        binding_response = client.post(
            f"/api/sessions/{session_id}/assistant/order",
            headers={**headers, "Idempotency-Key": "hf02-receiver-bind"},
            json={"order_id": "hf02-receiver-order", "initial_message": "请绑定并开始核查该授权订单。"},
        )
        assert binding_response.status_code == 202, binding_response.text
        binding = binding_response.json()
        assert _wait_run(client, binding["run_id"])["status"] == "SUCCEEDED"
        task_id = binding["task_id"]

        first = client.post(
            f"/api/sessions/{session_id}/assistant/messages",
            headers={**headers, "Idempotency-Key": "hf02-receiver-queued"},
            json={"body": question, "task_id": task_id},
        )
        assert first.status_code == 202, first.text
        queued = first.json()
        assert _wait_run(client, queued["run_id"])["status"] == "SUCCEEDED"
        assert any(item.get("tool") == "get_receiver_processing" for item in queued_model.decisions)

        hook_dir = tmp_path / "receiver-failure-hook"
        hook_dir.mkdir()
        marker = tmp_path / "receiver-tool-invoked.marker"
        (hook_dir / "sitecustomize.py").write_text(
            "import os\n"
            "from pathlib import Path\n"
            "if os.environ.get('OPSPILOT_HF02_FAIL_RECEIVER') == '1':\n"
            "    from opspilot.domain import s3_mcp\n"
            "    def _fail_receiver(db_path, task_id):\n"
            "        Path(os.environ['OPSPILOT_HF02_RECEIVER_MARKER']).write_text('called', encoding='utf-8')\n"
            "        raise RuntimeError('HF02_CONTROLLED_RECEIVER_UNAVAILABLE')\n"
            "    s3_mcp.get_receiver_processing_fact = _fail_receiver\n",
            encoding="utf-8",
        )
        prior_pythonpath = os.environ.get("PYTHONPATH", "")
        repo_root = str(Path(__file__).resolve().parents[1])
        pythonpath_parts = [str(hook_dir), repo_root]
        if prior_pythonpath:
            pythonpath_parts.append(prior_pythonpath)
        monkeypatch.setenv(
            "PYTHONPATH",
            os.pathsep.join(pythonpath_parts),
        )
        monkeypatch.setenv("OPSPILOT_HF02_FAIL_RECEIVER", "1")
        monkeypatch.setenv("OPSPILOT_HF02_RECEIVER_MARKER", str(marker))

        with connect(demo_db) as connection:
            receiver_evidence_before = connection.execute(
                "SELECT COUNT(*) FROM d2_evidence WHERE task_id=? AND fact_type='s3_receiver'", (task_id,)
            ).fetchone()[0]

        second = client.post(
            f"/api/sessions/{session_id}/assistant/messages",
            headers={**headers, "Idempotency-Key": "hf02-receiver-query-fails"},
            json={"body": question, "task_id": task_id},
        )
        assert second.status_code == 202, second.text
        failed = second.json()
        assert _wait_run(client, failed["run_id"])["status"] == "SUCCEEDED"
        assert marker.exists() and marker.read_text(encoding="utf-8") == "called"
        assert any(item.get("tool") == "get_receiver_processing" for item in failed_model.decisions)

        messages = client.get(f"/api/sessions/{session_id}/messages").json()["items"]
        answers = {
            item.get("answer_source_message_id"): item
            for item in messages if item["role"] == "ASSISTANT"
        }
        queued_answer = answers[queued["message_id"]]["body"]
        failed_answer = answers[failed["message_id"]]["body"]
        assert "QUEUED" in queued_answer and "尚不能确认处理完成" in queued_answer
        assert "UNKNOWN" in failed_answer and "无法确认" in failed_answer
        assert "PROCESSED" not in failed_answer and "已处理完成" not in failed_answer

        with connect(demo_db) as connection:
            delivery = connection.execute(
                """SELECT * FROM assistant_calls WHERE run_id=? AND kind='MCP'
                   AND json_extract(request_json,'$.name')='get_callback_delivery'""",
                (failed["run_id"],),
            ).fetchone()
            receiver_call = connection.execute(
                """SELECT * FROM assistant_calls WHERE run_id=? AND kind='MCP'
                   AND json_extract(request_json,'$.name')='get_receiver_processing'""",
                (failed["run_id"],),
            ).fetchone()
            assert delivery is not None
            assert receiver_call is not None
            assert receiver_call["status"] == "FAILED"
            assert json.loads(receiver_call["result_json"])["error"]
            assert receiver_call["evidence_id"] is None
            observations = connection.execute(
                """SELECT o.*,a.run_id FROM d2_tool_observations o
                   JOIN d2_attempts a ON a.attempt_id=o.attempt_id AND a.task_id=o.task_id
                   WHERE a.run_id=? AND o.tool_name='get_receiver_processing'""",
                (failed["run_id"],),
            ).fetchall()
            assert len(observations) == 1
            observation = dict(observations[0])
            assert observation["status"] == "ERROR"
            assert observation["evidence_id"] is None
            assert connection.execute(
                "SELECT COUNT(*) FROM d2_evidence WHERE task_id=? AND fact_type='s3_receiver'", (task_id,)
            ).fetchone()[0] == receiver_evidence_before
            receiver_row = connection.execute(
                "SELECT status,event_id FROM s3_receivers WHERE order_id='hf02-receiver-order'"
            ).fetchone()
            assert receiver_row["status"] == "QUEUED"
            assert receiver_row["event_id"] == event_id

            trace.extend([
                {
                    "stage": "queued_current_receiver",
                    "session_id": session_id,
                    "task_id": task_id,
                    "event_id": event_id,
                    "message_id": queued["message_id"],
                    "run_id": queued["run_id"],
                    "answer": queued_answer,
                    "receiver_state": receiver_row["status"],
                    "model_decisions": queued_model.decisions,
                },
                {
                    "stage": "receiver_tool_failure",
                    "session_id": session_id,
                    "task_id": task_id,
                    "event_id": event_id,
                    "message_id": failed["message_id"],
                    "run_id": failed["run_id"],
                    "answer": failed_answer,
                    "model_decisions": failed_model.decisions,
                    "mcp_call_id": receiver_call["call_id"],
                    "mcp_call_status": receiver_call["status"],
                    "d2_attempt_id": observation["attempt_id"],
                    "observation_id": observation["observation_id"],
                    "observation_status": observation["status"],
                    "evidence_id": observation["evidence_id"],
                    "receiver_evidence_count_before_after": [
                        receiver_evidence_before,
                        connection.execute(
                            "SELECT COUNT(*) FROM d2_evidence WHERE task_id=? AND fact_type='s3_receiver'",
                            (task_id,),
                        ).fetchone()[0],
                    ],
                    "controlled_mcp_subprocess_hook_invoked": marker.exists(),
                    "evidence_level": "FORMAL_API_WORKER_MCP_STDIO_FIXTURE_MODEL_CONTROLLED_FAILURE",
                },
            ])

    _capture_trace("HF02-02", trace)
