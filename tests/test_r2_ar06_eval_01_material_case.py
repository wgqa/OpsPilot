"""One independent E05 material-analysis case through the formal API/Worker."""
from __future__ import annotations

from fastapi.testclient import TestClient

from opspilot.web.app import create_app
from test_ar02_assistant import ORIGIN, PASSWORDS
from test_r2_ar03_integrated_journey_01 import (
    IntegratedJourneyFixtureModel,
    _answer_for,
    _login,
    _messages,
    _record_trace,
    _submit,
)


E05_INPUT = """请只按材料区分字面信息、条件性解释和未知线上事实，不要假设这些值已经部署。

JSON 配置（用户提供，未核实）：
{"api_version":"v1","callback":{"retry":{"max_attempts":5,"backoff":"fixed"}}}

回调失败日志（用户提供，未核实）：
event_id=event-00000000-0000-4000-8000-000000000001
request_id=request-r2-e05-01
http_status=503
error_code=TEMPORARY_UNAVAILABLE
attempt_count=1
max_attempts=5
retry_state=SCHEDULED
retry_at=2026-11-12T10:15:00Z

当前没有可信订单绑定。"""


def test_r2_ar06_e05_material_analysis_uses_unbound_user_claims(demo_db, tmp_path):
    model = IntegratedJourneyFixtureModel(scenario="materials", use_skill=False)
    app = create_app(
        db_path=demo_db,
        checkpoint_db_path=tmp_path / "r2-ar06-e05-checkpoint.sqlite3",
        start_worker=True,
        credentials=PASSWORDS,
        expected_origin=ORIGIN,
        assistant_model_factory=lambda: model,
    )
    with TestClient(app) as client:
        headers = _login(client)
        session_id = client.post("/api/sessions", headers=headers).json()["session_id"]
        accepted, run, elapsed_ms = _submit(
            client, headers, session_id, model, "r2-ar06-e05-material", E05_INPUT,
        )
        answer = _answer_for(_messages(client, headers, session_id), accepted["message_id"])
        trace = _record_trace(
            demo_db, session_id, [model], "E05-D", elapsed_ms,
            {"answer": answer, "accepted": accepted},
        )

    assert run["status"] == "SUCCEEDED"
    assert accepted.get("task_id") is None
    for marker in (
        "api_version=v1", "max_attempts=5", "backoff=fixed", "HTTP 503",
        "TEMPORARY_UNAVAILABLE", "attempt_count=1", "SCHEDULED",
        "当前 Session 没有可信订单绑定", "项目文档版本也不能证明线上部署版本",
    ):
        assert marker in answer
    assert "当前没有可信订单绑定" in str(model.seen)
    assert trace["provider_requests"] == 0
    assert trace["provider_spend_rows"] == 0
