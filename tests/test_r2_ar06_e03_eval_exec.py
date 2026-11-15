from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "user-demo"))
sys.path.insert(0, str(ROOT / "tests"))

from opspilot.domain import assistant_knowledge
from opspilot.domain.database import connect
from opspilot.domain.scoped_protocol_comparison import (
    DocumentNotAuthorizedError,
    compare_scoped_protocols,
    list_scoped_protocols,
)
from opspilot.domain.task_control import create_session, trusted_identity
from opspilot.web.app import create_app
from run_r2_ar06_case import (  # noqa: E402
    execute_case,
    initialize_case_runtime,
    load_frozen_case,
    make_e03_fixture_model,
)
from initialize_demo import initialize_user_demo  # noqa: E402


ORIGIN = "http://127.0.0.1"
PASSWORDS = {"support-a": "isolated-fixture-password", "support-b": "isolated-fixture-password-b"}


def _runtime(tmp_path: Path, suffix: str):
    root = tmp_path / "repo"
    (root / ".runtime").mkdir(parents=True)
    name = f"user-demo-r2-e03-{suffix.replace('_', '-')}"
    runtime = initialize_case_runtime("E03-D", name, root=root)
    return root, name, runtime


def _app(runtime: Path, model):
    return create_app(
        db_path=runtime / "domain.sqlite3",
        checkpoint_db_path=runtime / "checkpoint.sqlite3",
        start_worker=True,
        credentials=PASSWORDS,
        expected_origin=ORIGIN,
        heartbeat_seconds=0.05,
        assistant_model_factory=lambda: model,
        assistant_runtime_enabled=False,
        assistant_knowledge_registry_path=runtime / "assistant-access.json",
    )


def _execute(root: Path, name: str, runtime: Path, *, tool_order="compare_then_excerpt"):
    model = make_e03_fixture_model(tool_order=tool_order)
    app = _app(runtime, model)
    with TestClient(app, base_url=ORIGIN, raise_server_exceptions=False) as client:
        result = execute_case(
            client,
            case_id="E03-D",
            runtime_name=name,
            root=root,
            support_password=PASSWORDS["support-a"],
            api_origin=ORIGIN,
            web_origin=ORIGIN,
            execution_mode="FIXTURE",
            timeout_seconds=30,
        )
        current = client.get(f"/api/runs/{result['run_id']}/assistant-sources")
        assert current.status_code == 200, current.text
        return result, model, json.loads(Path(result["trace_path"]).read_text(encoding="utf-8")), current.json()


@pytest.mark.parametrize(
    ("tool_order", "expected_order"),
    [
        ("compare_then_excerpt", [
            "list_scoped_protocol_documents", "compare_scoped_protocols", "read_scoped_protocol_excerpt",
        ]),
        ("excerpt_then_compare", [
            "list_scoped_protocol_documents", "read_scoped_protocol_excerpt", "compare_scoped_protocols",
        ]),
    ],
)
def test_e03_formal_assistant_fixture_runs_frozen_input_without_task_binding(
    tmp_path: Path, tool_order: str, expected_order: list[str],
):
    root, name, runtime = _runtime(tmp_path, tool_order)
    result, model, trace, sources = _execute(root, name, runtime, tool_order=tool_order)

    assert load_frozen_case("E03-D")["user_turns"] == [
        "我们要把回调 API 从 v1 升到 v2。请比较适用协议，说明配置影响、兼容风险和研发检查项。线上实际部署版本尚未核实。"
    ]
    assert [row["body"] for row in trace["messages"] if row["role"] == "USER"] == load_frozen_case("E03-D")["user_turns"]
    assert result["run_status"] == "SUCCEEDED"
    assert result["assessment_status"] == "UNVERIFIED"
    assert result["execution_mode"] == "FIXTURE"
    assert result["task_id"] is None
    assert result["provider_send_grants"] == 0
    assert result["provider_responses_received"] == 0
    assert result["unknown_requests"] == 0
    assert result["mcp_tools_call_count"] == 3
    assert result["mcp_tool_names"] == sorted(expected_order)
    assert result["fixture_model_dispatches"] == model.dispatch_count
    assert model.offered_tool_names
    assert set(expected_order).issubset(set(model.offered_tool_names))
    actual_order = [item["tool"] for item in model.decisions if item["action"] == "CALL"]
    assert actual_order == expected_order
    assert trace["task_bindings"] == []
    assert len(trace["runs"]) == 1 and trace["runs"][0]["task_id"] is None
    assert sources["current"] is True, sources
    assert all(item["result"] is not None for item in sources["items"])

    calls = trace["assistant_calls_actual_model_input_output"]
    tool_results = {
        row["request_json"]["name"]: row["result_json"]
        for row in calls if row["kind"] == "MCP"
    }
    discovery = tool_results["list_scoped_protocol_documents"]
    assert discovery["project_id"] == "orders-async-demo"
    refs = {row["document_id"]: row for row in discovery["protocol_documents"]}
    assert refs["callback-retry-contract"]["version"] == "1.0.0"
    assert refs["callback-retry-contract"]["source"] == "local:orders-async-demo/contract-v1"
    assert refs["callback-retry-contract"]["digest"] == "a5974f46bf50e2bfcd63ed1e6528d473560854204d12a50dfb3f82b9e61bc0c3"
    assert refs["callback-retry-contract-v2"]["version"] == "2.0.0"
    assert refs["callback-retry-contract-v2"]["source"] == "local:orders-async-demo/contract-v2"
    assert refs["callback-retry-contract-v2"]["digest"] == "9ad3f5a67a5f40da986769c66a78317027d3e57803371a0674d3b14fe412e238"
    comparison = tool_results["compare_scoped_protocols"]
    assert comparison["success"] is True and comparison["identical"] is False
    excerpt = tool_results["read_scoped_protocol_excerpt"]
    assert excerpt["success"] is True
    assert excerpt["source_refs"][0]["digest"] == refs["callback-retry-contract-v2"]["digest"]
    answer = next(row["body"] for row in trace["messages"] if row["role"] == "ASSISTANT")
    assert "attempt_count" in answer and "max_attempts" in answer
    assert "线上部署了哪个版本" in answer
    assert "不能确认" in answer
    assert "当前业务事实" not in answer


def test_e03_scoped_grant_does_not_expand_global_or_cross_tenant_access(tmp_path: Path):
    root, _name, runtime = _runtime(tmp_path, "isolation")
    database = runtime / "domain.sqlite3"
    e03_registry = runtime / "assistant-access.json"

    identity_a = trusted_identity(database, "support-a")
    session_a = create_session(database, identity_a)["session_id"]
    identity_b = trusted_identity(database, "support-b")
    session_b = create_session(database, identity_b)["session_id"]

    scoped = assistant_knowledge.list_scopes(database, identity_a, session_a, registry_path=e03_registry)
    assert [row["project_id"] for row in scoped["items"]] == ["orders-async-demo"]
    other_tenant_scope = assistant_knowledge.list_scopes(
        database, identity_b, session_b, registry_path=e03_registry,
    )
    assert other_tenant_scope["items"] == []
    assert other_tenant_scope["reason_code"] == "KNOWLEDGE_SCOPE_DENIED"
    with pytest.raises(assistant_knowledge.KnowledgeScopeDenied):
        list_scoped_protocols(
            database, identity_b, session_b, topic="callback retry",
            registry_path=e03_registry,
        )
    with pytest.raises(DocumentNotAuthorizedError):
        compare_scoped_protocols(
            database, identity_a, session_a,
            base_document_id="callback-retry-contract",
            target_document_id="api-scope-current",
            registry_path=e03_registry,
        )

    other_runtime = root / ".runtime" / "user-demo-r2-e03-other-runtime"
    initialize_user_demo(other_runtime, require_absent_directory=True)
    other_database = other_runtime / "domain.sqlite3"
    other_identity = trusted_identity(other_database, "support-a")
    other_session = create_session(other_database, other_identity)["session_id"]
    default = assistant_knowledge.list_scopes(other_database, other_identity, other_session)
    assert "orders-async-demo" not in {row["project_id"] for row in default["items"]}
    assert {row["project_id"] for row in default["items"]} == {"orders-callback"}


def test_e03_revocation_invalidates_old_sources_and_answer_projection(tmp_path: Path):
    root, name, runtime = _runtime(tmp_path, "revoke")
    _result, _model, _trace, sources = _execute(root, name, runtime)
    assert sources["current"] is True
    registry_path = runtime / "assistant-access.json"
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    registry["projects"][0]["active"] = False
    registry_path.write_text(json.dumps(registry, ensure_ascii=False), encoding="utf-8")

    app = _app(runtime, make_e03_fixture_model())
    with TestClient(app, base_url=ORIGIN, raise_server_exceptions=False) as client:
        login = client.post(
            "/api/auth/login", headers={"Origin": ORIGIN},
            json={"actor_id": "support-a", "password": PASSWORDS["support-a"]},
        )
        assert login.status_code == 200
        headers = {"Origin": ORIGIN, "X-CSRF-Token": login.json()["csrf_token"]}
        status = client.get(f"/api/runs/{_result['run_id']}/assistant-sources", headers=headers)
        assert status.status_code == 200
        assert status.json()["current"] is False
        assert all(item["result"] is None for item in status.json()["items"])
        messages = client.get(
            f"/api/sessions/{_result['session_id']}/messages", headers=headers,
        )
        answer = next(row for row in messages.json()["items"] if row["role"] == "ASSISTANT")
        assert "来源已失效" in answer["body"]


def test_e03_stored_document_digest_mismatch_invalidates_evidence(tmp_path: Path):
    root, name, runtime = _runtime(tmp_path, "digest")
    result, _model, _trace, _sources = _execute(root, name, runtime)
    with connect(runtime / "domain.sqlite3") as connection:
        rows = connection.execute(
            "SELECT call_id,request_json,result_json FROM assistant_calls WHERE run_id=? AND kind='MCP'",
            (result["run_id"],),
        ).fetchall()
        excerpt_call = next(
            row for row in rows
            if json.loads(row["request_json"])["name"] == "read_scoped_protocol_excerpt"
        )
        tampered = json.loads(excerpt_call["result_json"])
        tampered["document_ref"]["digest"] = "0" * 64
        tampered["source_refs"][0]["digest"] = "0" * 64
        connection.execute(
            "UPDATE assistant_calls SET result_json=? WHERE call_id=?",
            (json.dumps(tampered), excerpt_call["call_id"]),
        )

    app = _app(runtime, make_e03_fixture_model())
    with TestClient(app, base_url=ORIGIN, raise_server_exceptions=False) as client:
        login = client.post(
            "/api/auth/login", headers={"Origin": ORIGIN},
            json={"actor_id": "support-a", "password": PASSWORDS["support-a"]},
        )
        headers = {"Origin": ORIGIN, "X-CSRF-Token": login.json()["csrf_token"]}
        status = client.get(f"/api/runs/{result['run_id']}/assistant-sources", headers=headers)
        assert status.status_code == 200
        assert status.json()["current"] is False
        assert all(item["result"] is None for item in status.json()["items"])


def test_e03_registry_override_rejects_a_path_outside_runtime(tmp_path: Path):
    _root, _name, runtime = _runtime(tmp_path, "path-boundary")
    outside = ROOT / "knowledge" / "assistant-access.json"
    with pytest.raises(ValueError, match="ASSISTANT_KNOWLEDGE_REGISTRY_PATH_INVALID"):
        create_app(
            db_path=runtime / "domain.sqlite3",
            checkpoint_db_path=runtime / "checkpoint.sqlite3",
            start_worker=False,
            credentials=PASSWORDS,
            assistant_knowledge_registry_path=outside,
        )
