"""Offline wire preflight for a bound AR-03 Assistant Worker run."""

from __future__ import annotations

import json
import time

import httpx
from fastapi.testclient import TestClient

from opspilot.assistant import create_assistant_model
from opspilot.domain.s3 import prepare_s3_fixture
from opspilot.web.app import create_app


EXPERIMENT_ID = "AR-03-REAL-LLM-01"
ORIGIN = "http://ar03-offline-preflight"
PASSWORDS = {"support-a": "offline-support", "approver-a": "offline-approver"}


def _wait_run(client, run_id: str) -> dict:
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        response = client.get(f"/api/runs/{run_id}")
        assert response.status_code == 200, response.text
        run = response.json()
        if run["status"] in {"SUCCEEDED", "FAILED", "BLOCKED"}:
            return run
        time.sleep(0.05)
    raise AssertionError(f"run did not finish: {run_id}")


def test_bound_formal_worker_wire_is_frozen_and_tools_are_task_scoped(
    demo_db, tmp_path, monkeypatch,
):
    from opspilot.domain.assistant_experiment import EXPERIMENT_ENV, read_budget

    monkeypatch.setenv(EXPERIMENT_ENV, EXPERIMENT_ID)
    monkeypatch.setenv("OPSPILOT_ASSISTANT_PROVIDER_ENABLED", "1")
    monkeypatch.setenv("OPSPILOT_MODEL_API_KEY", "offline-placeholder-not-a-credential")
    monkeypatch.setenv("OPSPILOT_MODEL_NAME", "deepseek-flash")
    monkeypatch.setenv("OPSPILOT_MODEL_BASE_URL", "https://api.deepseek.com/v1")
    prepare_s3_fixture(
        demo_db, "DELIVERED_PENDING", order_id="ar03-order", contract_version=2,
    )

    captured: list[dict] = []
    captured_urls: list[str] = []

    async def respond(request: httpx.Request) -> httpx.Response:
        captured_urls.append(str(request.url))
        captured.append(json.loads((await request.aread()).decode("utf-8")))
        index = len(captured)
        return httpx.Response(
            200,
            headers={"x-request-id": f"offline-ar03-wire-{index}"},
            json={
                "id": f"offline-ar03-wire-completion-{index}",
                "object": "chat.completion",
                "created": index,
                "model": "deepseek-flash",
                "choices": [{
                    "index": 0,
                    "message": {"role": "assistant", "content": "已收到。"},
                    "finish_reason": "stop",
                }],
                "usage": {
                    "prompt_tokens": 60,
                    "completion_tokens": 3,
                    "total_tokens": 63,
                },
            },
        )

    def factory():
        return create_assistant_model(
            transport_async=httpx.MockTransport(respond),
            transport_sync=httpx.MockTransport(lambda request: httpx.Response(500)),
        )

    app = create_app(
        db_path=demo_db,
        checkpoint_db_path=tmp_path / "ar03-offline-wire-checkpoint.sqlite3",
        start_worker=True,
        credentials=PASSWORDS,
        expected_origin=ORIGIN,
        assistant_model_factory=factory,
        assistant_experiment_id=EXPERIMENT_ID,
    )
    with TestClient(app) as client:
        login = client.post(
            "/api/auth/login",
            headers={"Origin": ORIGIN},
            json={"actor_id": "support-a", "password": PASSWORDS["support-a"]},
        )
        assert login.status_code == 200, login.text
        headers = {"Origin": ORIGIN, "X-CSRF-Token": login.json()["csrf_token"]}
        session_id = client.post("/api/sessions", headers=headers).json()["session_id"]
        bind = client.post(
            f"/api/sessions/{session_id}/assistant/order",
            headers={**headers, "Idempotency-Key": "ar03-offline-wire-bind"},
            json={"order_id": "ar03-order", "initial_message": "开始核对授权订单。"},
        )
        assert bind.status_code == 202, bind.text
        assert _wait_run(client, bind.json()["run_id"])["status"] == "SUCCEEDED"

        accepted = client.post(
            f"/api/sessions/{session_id}/assistant/messages",
            headers={**headers, "Idempotency-Key": "ar03-offline-wire-investigate"},
            json={
                "body": "我们最近升级了回调协议，客户反馈重试行为和以前不一样。请查一下有权限访问的旧版、新版协议，分析具体变化，再结合这个订单的回调情况判断影响，最后整理一份处理说明草稿。不能确认的地方请明确告诉我。",
                "task_id": bind.json()["task_id"],
            },
        )
        assert accepted.status_code == 202, accepted.text
        assert _wait_run(client, accepted.json()["run_id"])["status"] == "SUCCEEDED"

    assert len(captured) == len(captured_urls) == 2
    assert all(url == "https://api.deepseek.com/v1/chat/completions" for url in captured_urls)
    bound_request = captured[-1]
    assert bound_request["model"] == "deepseek-flash"
    assert bound_request["max_tokens"] == 2048
    assert bound_request["thinking"] == {"type": "disabled"}
    assert bound_request["tool_choice"] == "auto"
    assert bound_request["parallel_tool_calls"] is False
    assert bound_request["stream"] is False
    assert "max_completion_tokens" not in bound_request
    names = {row["function"]["name"] for row in bound_request["tools"]}
    assert {
        "list_scoped_protocol_documents",
        "compare_scoped_protocols",
        "get_order_status",
        "get_callback_delivery",
        "get_receiver_processing",
    } <= names
    assert read_budget(demo_db, EXPERIMENT_ID)["provider_used"] == 2
