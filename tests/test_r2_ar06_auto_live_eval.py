from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from fastapi.testclient import TestClient
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "user-demo"))
sys.path.insert(0, str(ROOT / "tests"))

from opspilot.web.app import create_app  # noqa: E402
from run_r2_ar06_case import (  # noqa: E402
    E07_EVENT_ID,
    EvaluationPreflightError,
    initialize_case_runtime,
    execute_case,
    inspect_case_runtime,
    live_preflight,
    load_frozen_case,
    main,
    _manifest_matches,
)
from test_r2_ar03_integrated_journey_01 import IntegratedJourneyFixtureModel  # noqa: E402


ORIGIN = "http://127.0.0.1"
PASSWORDS = {"support-a": "support-test-password"}


class E05FixtureModel(BaseChatModel):
    dispatch_count: int = 0

    @property
    def _llm_type(self) -> str:
        return "R2_AR06_AUTO_LIVE_FIXTURE"

    def bind_tools(self, _tools, **_kwargs):
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        self.dispatch_count += 1
        answer = AIMessage(content=(
            "材料明示：JSON 写 api_version=v1、max_attempts=5、backoff=fixed；"
            "日志写 HTTP 503、TEMPORARY_UNAVAILABLE、attempt_count=1、retry_state=SCHEDULED。"
            "若日志真实且相关，可推断重试已计划；不能证明重试成功或当前线上状态。"
        ), usage_metadata={"input_tokens": 31, "output_tokens": 17, "total_tokens": 48})
        return ChatResult(generations=[ChatGeneration(message=answer)])


def _runtime(tmp_path: Path, case_id: str):
    root = tmp_path / "repo"
    (root / ".runtime").mkdir(parents=True)
    name = f"user-demo-{case_id.lower().replace('-', '')}-fixture"
    runtime = initialize_case_runtime(case_id, name, root=root)
    return root, name, runtime


def _run_fixture_case(root: Path, runtime_name: str, runtime: Path, case_id: str):
    model = (E05FixtureModel() if case_id == "E05-D"
             else IntegratedJourneyFixtureModel(scenario="current"))
    app = create_app(
        db_path=runtime / "domain.sqlite3",
        checkpoint_db_path=runtime / "checkpoint.sqlite3",
        start_worker=True,
        credentials=PASSWORDS,
        expected_origin=ORIGIN,
        heartbeat_seconds=0.05,
        assistant_model_factory=lambda: model,
        assistant_runtime_enabled=False,
    )
    with TestClient(app, base_url=ORIGIN, raise_server_exceptions=False) as client:
        result = execute_case(
            client,
            case_id=case_id,
            runtime_name=runtime_name,
            root=root,
            support_password=PASSWORDS["support-a"],
            api_origin=ORIGIN,
            web_origin=ORIGIN,
            execution_mode="FIXTURE",
            timeout_seconds=30,
        )
    return result, model


def test_frozen_case_loader_requires_the_frozen_input_and_supported_scope():
    assert load_frozen_case("E05-D")["user_turns"] == [
        "請只按以下材料分析已知、推断和未知：JSON 写 api_version=v1、max_attempts=5、backoff=fixed；日志写 HTTP 503、TEMPORARY_UNAVAILABLE、attempt_count=1、retry_state=SCHEDULED。不要假设它们来自线上当前配置。"
    ]
    assert load_frozen_case("E07-D")["user_turns"] == [
        "请核查这个授权订单当前回调处理到了哪一步。HTTP 202 是否表示已经处理完成？"
    ]
    try:
        load_frozen_case("E09-D")
    except ValueError as error:
        assert "LIVE_CASE_NOT_PREPARED" in str(error)
    else:
        raise AssertionError("E09 must stay blocked until its missing frozen inputs are resolved.")


def test_prepare_and_inspect_create_a_fresh_e05_runtime_without_grant_or_history(tmp_path):
    root, name, runtime = _runtime(tmp_path, "E05-D")
    state = inspect_case_runtime("E05-D", name, root=root)
    assert runtime == root / ".runtime" / name
    assert state["sessions"] == state["messages"] == state["task_bindings"] == 0
    assert state["provider_spends"] == state["provider_send_grants"] == 0
    assert state["runtime_grant_present"] is False
    assert state["fresh"] is True


def test_prepare_e07_runtime_keeps_the_frozen_same_event_queued_fixture(tmp_path):
    root, name, _runtime_dir = _runtime(tmp_path, "E07-D")
    state = inspect_case_runtime("E07-D", name, root=root)
    assert state["s3_order_id"] == "async-order"
    assert state["delivery_status"] == "ACKNOWLEDGED"
    assert state["receiver_status"] == "QUEUED"
    assert state["delivery_event_id"] == state["receiver_event_id"] == E07_EVENT_ID
    assert state["sessions"] == state["messages"] == state["task_bindings"] == 0
    assert state["provider_send_grants"] == state["unknown_requests"] == 0


def test_live_manifest_must_prove_selected_runtime_and_live_mode(tmp_path):
    root = tmp_path / "repo"
    runtime = root / ".runtime" / "user-demo-e05-live"
    runtime.mkdir(parents=True)
    manifest = {
        "root": str(root),
        "runtimeName": "user-demo-e05-live",
        "domainDb": str(runtime / "domain.sqlite3"),
        "checkpointDb": str(runtime / "checkpoint.sqlite3"),
        "mode": "Offline",
    }
    (runtime / "processes.json").write_text(json.dumps(manifest), encoding="utf-8")
    try:
        _manifest_matches("user-demo-e05-live", runtime, root)
    except EvaluationPreflightError as error:
        assert "NOT_STARTED_IN_LIVE_MODE" in str(error)
    else:
        raise AssertionError("An Offline worker must not pass the Live automation preflight.")
    manifest["mode"] = "Live"
    (runtime / "processes.json").write_text(json.dumps(manifest), encoding="utf-8")
    assert _manifest_matches("user-demo-e05-live", runtime, root)["mode"] == "Live"


def test_live_preflight_checks_eight_request_reserve_without_creating_grant(tmp_path, monkeypatch):
    import runtime_admin

    root, name, runtime = _runtime(tmp_path, "E05-D")
    manifest = {
        "root": str(root),
        "runtimeName": name,
        "domainDb": str(runtime / "domain.sqlite3"),
        "checkpointDb": str(runtime / "checkpoint.sqlite3"),
        "mode": "Live",
    }
    (runtime / "processes.json").write_text(json.dumps(manifest), encoding="utf-8")
    monkeypatch.setattr(runtime_admin, "read_env", lambda: {})
    monkeypatch.setattr(runtime_admin, "preflight", lambda *_args: {
        "provider_sends": 0,
        "unknown_requests": 0,
        "total_limit_usd_micro": 50_000,
        "remaining_usd_micro": 50_000,
        "one_max_request_reserve_usd_micro": 6_058,
    })

    class HealthResponse:
        status_code = 200

        @staticmethod
        def json():
            return {"status": "ok", "worker": {"ready": True}}

    class HealthClient:
        called = False

        def get(self, url):
            self.called = True
            assert url == "http://127.0.0.1:8000/api/health"
            return HealthResponse()

    client = HealthClient()
    result = live_preflight(
        "E05-D", name, authorized_max_cost_usd="0.05",
        root=root, client=client,
    )
    assert result["maximum_provider_dispatches_per_run"] == 8
    assert result["worst_case_run_reserve_usd_micro"] == 48_464
    assert result["provider_requests_so_far"] == 0
    assert client.called is True
    state = inspect_case_runtime("E05-D", name, root=root)
    assert state["runtime_grant_present"] is False
    assert state["provider_send_grants"] == 0


def test_live_preflight_rejects_over_authorized_pool_before_health_or_chat(tmp_path, monkeypatch):
    import runtime_admin

    root, name, runtime = _runtime(tmp_path, "E05-D")
    (runtime / "processes.json").write_text(json.dumps({
        "root": str(root),
        "runtimeName": name,
        "domainDb": str(runtime / "domain.sqlite3"),
        "checkpointDb": str(runtime / "checkpoint.sqlite3"),
        "mode": "Live",
    }), encoding="utf-8")
    monkeypatch.setattr(runtime_admin, "read_env", lambda: {})
    monkeypatch.setattr(runtime_admin, "preflight", lambda *_args: {
        "provider_sends": 0,
        "unknown_requests": 0,
        "total_limit_usd_micro": 50_001,
        "remaining_usd_micro": 50_001,
        "one_max_request_reserve_usd_micro": 6_058,
    })

    class NoHealthClient:
        called = False

        def get(self, _url):
            self.called = True
            raise AssertionError("Budget refusal must precede HTTP access.")

    client = NoHealthClient()
    try:
        live_preflight("E05-D", name, authorized_max_cost_usd="0.05", root=root, client=client)
    except EvaluationPreflightError as error:
        assert "EXCEEDS_CASE_AUTHORIZED_CAP" in str(error)
    else:
        raise AssertionError("A Grant pool above the case authorization must be refused.")
    assert client.called is False


def test_live_cli_rejects_authorization_for_a_different_case_before_network(capsys):
    status = main([
        "run-live",
        "--case-id", "E05-D",
        "--runtime-name", "user-demo-r2-e05-live",
        "--authorized-case-id", "E07-D",
        "--authorized-max-cost-usd", "0.05",
    ])
    assert status == 2
    assert "LIVE_AUTHORIZATION_CASE_MISMATCH" in capsys.readouterr().err


def test_second_runner_for_the_same_runtime_stops_before_api_submission(tmp_path):
    root, name, runtime = _runtime(tmp_path, "E05-D")
    (runtime / ".r2-ar06-case-run.lock").write_text("active", encoding="utf-8")

    class NoRequestClient:
        called = False

        def post(self, *_args, **_kwargs):
            self.called = True
            raise AssertionError("A concurrent case runner must stop before network access.")

        def get(self, *_args, **_kwargs):
            self.called = True
            raise AssertionError("A concurrent case runner must stop before network access.")

    client = NoRequestClient()
    try:
        execute_case(
            client,
            case_id="E05-D",
            runtime_name=name,
            root=root,
            support_password=PASSWORDS["support-a"],
            api_origin=ORIGIN,
            web_origin=ORIGIN,
            execution_mode="FIXTURE",
        )
    except EvaluationPreflightError as error:
        assert "CASE_RUN_ALREADY_ACTIVE" in str(error)
    else:
        raise AssertionError("Concurrent execution must be rejected.")
    assert client.called is False


def test_e05_uses_formal_session_api_exact_gold_input_and_exports_fixture_trace(tmp_path):
    root, name, runtime = _runtime(tmp_path, "E05-D")
    result, model = _run_fixture_case(root, name, runtime, "E05-D")
    trace = json.loads(Path(result["trace_path"]).read_text(encoding="utf-8"))
    gold = load_frozen_case("E05-D")
    user_messages = [row for row in trace["messages"] if row["role"] == "USER"]
    assert [row["body"] for row in user_messages] == gold["user_turns"]
    assert result["run_status"] == "SUCCEEDED"
    assert result["assessment_status"] == "UNVERIFIED"
    assert result["fixture_model_dispatches"] == model.dispatch_count == 1
    assert result["provider_send_grants"] == 0
    assert result["provider_input_tokens"] is None
    assert result["fixture_token_metadata"]["input_tokens"] == 31
    assert result["mcp_tools_call_count"] == 0
    assert len([row for row in trace["messages"] if row["role"] == "ASSISTANT"]) == 1


def test_e07_uses_trusted_order_api_and_exports_same_event_current_mcp_trace(tmp_path):
    root, name, runtime = _runtime(tmp_path, "E07-D")
    result, model = _run_fixture_case(root, name, runtime, "E07-D")
    trace = json.loads(Path(result["trace_path"]).read_text(encoding="utf-8"))
    gold = load_frozen_case("E07-D")
    user_messages = [row for row in trace["messages"] if row["role"] == "USER"]
    assert [row["body"] for row in user_messages] == gold["user_turns"]
    assert result["run_status"] == "SUCCEEDED"
    assert result["task_id"]
    assert result["provider_send_grants"] == 0
    assert result["fixture_model_dispatches"] == len(model.seen) == 3
    assert result["mcp_tools_call_count"] == 2
    assert result["observation_count"] == 2
    assert set(result["mcp_tool_names"]) == {"get_receiver_processing", "get_callback_delivery"}
    observations = trace["observations"]
    assert len(observations) == 2
    facts = [row["result_json"] for row in observations]
    assert {item["facts"]["event_id"] for item in facts} == {E07_EVENT_ID}
    assert {item["facts"]["status"] for item in facts} == {"QUEUED", "ACKNOWLEDGED"}


def test_ambiguous_message_post_is_never_submitted_twice(tmp_path):
    import httpx

    root, name, runtime = _runtime(tmp_path, "E05-D")
    model = E05FixtureModel()
    app = create_app(
        db_path=runtime / "domain.sqlite3",
        checkpoint_db_path=runtime / "checkpoint.sqlite3",
        start_worker=True,
        credentials=PASSWORDS,
        expected_origin=ORIGIN,
        heartbeat_seconds=0.05,
        assistant_model_factory=lambda: model,
        assistant_runtime_enabled=False,
    )
    with TestClient(app, base_url=ORIGIN, raise_server_exceptions=False) as client:
        class AmbiguousResponseClient:
            def __init__(self):
                self.message_posts = 0

            def post(self, url, **kwargs):
                response = client.post(url, **kwargs)
                if url.endswith("/assistant/messages"):
                    self.message_posts += 1
                    raise httpx.ReadTimeout("simulated lost acknowledgement")
                return response

            def get(self, url, **kwargs):
                return client.get(url, **kwargs)

        ambiguous = AmbiguousResponseClient()
        try:
            execute_case(
                ambiguous,
                case_id="E05-D",
                runtime_name=name,
                root=root,
                support_password=PASSWORDS["support-a"],
                api_origin=ORIGIN,
                web_origin=ORIGIN,
                execution_mode="FIXTURE",
                timeout_seconds=3,
            )
        except httpx.ReadTimeout:
            pass
        else:
            raise AssertionError("The simulated ambiguous POST should stop execution.")
        assert ambiguous.message_posts == 1
