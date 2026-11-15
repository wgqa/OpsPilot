from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "user-demo"))
sys.path.insert(0, str(ROOT / "tests"))

from opspilot.domain import assistant_knowledge  # noqa: E402
from opspilot.domain.database import connect  # noqa: E402
from opspilot.domain.scoped_protocol_comparison import (  # noqa: E402
    DocumentNotAuthorizedError,
    list_scoped_protocols,
    compare_scoped_protocols,
)
from opspilot.domain.task_control import create_session, trusted_identity  # noqa: E402
from opspilot.web.app import create_app  # noqa: E402
import run_r2_ar06_case as runner  # noqa: E402
from run_r2_ar06_case import (  # noqa: E402
    EvaluationPreflightError,
    E04_FIXTURE_MANIFEST_PATH,
    _e04_fixture_manifest,
    _e04_runtime_registry,
    execute_case,
    initialize_case_runtime,
    load_frozen_case,
    make_e04_fixture_model,
)

ORIGIN = "http://127.0.0.1"
PASSWORDS = {"support-a": "isolated-fixture-password", "support-b": "isolated-fixture-password-b"}


def _runtime(tmp_path: Path, suffix: str):
    root = tmp_path / "repo"
    (root / ".runtime").mkdir(parents=True)
    name = f"user-demo-r2-e04-{suffix.replace('_', '-')}"
    runtime = initialize_case_runtime("E04-H", name, root=root)
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


def _execute(root: Path, name: str, runtime: Path, *, decision_path="compare_available"):
    model = make_e04_fixture_model(decision_path=decision_path)
    with TestClient(_app(runtime, model), base_url=ORIGIN, raise_server_exceptions=False) as client:
        result = execute_case(
            client,
            case_id="E04-H",
            runtime_name=name,
            root=root,
            support_password=PASSWORDS["support-a"],
            api_origin=ORIGIN,
            web_origin=ORIGIN,
            execution_mode="FIXTURE",
            timeout_seconds=30,
        )
        sources = client.get(f"/api/runs/{result['run_id']}/assistant-sources")
        assert sources.status_code == 200, sources.text
        return result, model, json.loads(Path(result["trace_path"]).read_text(encoding="utf-8")), sources.json()


@pytest.mark.parametrize(
    ("decision_path", "expected_tools"),
    [
        ("compare_available", [
            "list_scoped_protocol_documents", "compare_scoped_protocols", "read_scoped_protocol_excerpt",
        ]),
        ("request_missing_materials", ["list_scoped_protocol_documents"]),
    ],
)
def test_e04_formal_api_runs_frozen_question_with_scoped_docs_and_no_task(
    tmp_path: Path, decision_path: str, expected_tools: list[str],
):
    root, name, runtime = _runtime(tmp_path, decision_path)
    result, model, trace, sources = _execute(root, name, runtime, decision_path=decision_path)

    question = load_frozen_case("E04-H")["user_turns"][0]
    assert question == "我的发布记录说使用 v1.4，项目文档目录只有 v1 和 v2，而且两份迁移说明对 retry 字段的解释不一致。请先指出能确定的内容和缺口。"
    assert [row["body"] for row in trace["messages"] if row["role"] == "USER"] == [question]
    assert result["run_status"] == "SUCCEEDED"
    assert result["assessment_status"] == "UNVERIFIED"
    assert result["execution_mode"] == "FIXTURE"
    assert result["split"] == "H"
    assert result["fixture_specification_status"] == "POST_FREEZE_FIXTURE_SPECIFIED"
    assert result["task_id"] is None and trace["task_bindings"] == []
    assert result["provider_send_grants"] == 0
    assert result["provider_responses_received"] == 0
    assert result["unknown_requests"] == 0
    assert result["observation_count"] == 0 and result["evidence_count"] == 0
    assert result["fixture_model_dispatches"] == model.dispatch_count
    assert result["mcp_tool_names"] == sorted(expected_tools)
    assert set(expected_tools).issubset(set(model.offered_tool_names))
    assert sources["current"] is True
    assert len(trace["runs"]) == 1 and trace["runs"][0]["task_id"] is None
    assert result["knowledge_scope"]["project_id"] == "orders-e04-absence"
    assert result["knowledge_scope"]["registered_versions"] == ["1.0.0", "2.0.0"]
    assert result["absence_claim_scope"] == "AUTHORIZED_RUNTIME_PROJECT_ONLY"
    answer = next(row["body"] for row in trace["messages"] if row["role"] == "ASSISTANT")
    assert "不能证明其他环境或线上不存在 v1.4" in answer
    assert "没有随本轮提供可核验原文" in answer
    assert "实际部署版本" in answer
    assert "Gold" not in answer and "Rubric" not in answer

    calls = trace["assistant_calls_actual_model_input_output"]
    tool_results = {
        row["request_json"]["name"]: row["result_json"]
        for row in calls if row["kind"] == "MCP"
    }
    discovery = tool_results["list_scoped_protocol_documents"]
    assert discovery["project_id"] == "orders-e04-absence"
    docs = {row["document_id"]: row for row in discovery["protocol_documents"]}
    assert set(docs) == {"callback-retry-contract", "callback-retry-contract-v2"}
    assert docs["callback-retry-contract"]["version"] == "1.0.0"
    assert docs["callback-retry-contract"]["digest"] == "a5974f46bf50e2bfcd63ed1e6528d473560854204d12a50dfb3f82b9e61bc0c3"
    assert docs["callback-retry-contract-v2"]["version"] == "2.0.0"
    assert docs["callback-retry-contract-v2"]["digest"] == "9ad3f5a67a5f40da986769c66a78317027d3e57803371a0674d3b14fe412e238"
    assert all(row.get("document_id") != "callback-retry-contract-v1-4" for row in docs.values())
    assert all("POST_FREEZE_FIXTURE_SPECIFIED" not in str(messages) for messages in model.seen)
    if decision_path == "compare_available":
        comparison = tool_results["compare_scoped_protocols"]
        assert comparison["success"] is True and comparison["identical"] is False
        excerpt = tool_results["read_scoped_protocol_excerpt"]
        assert excerpt["success"] is True
        assert excerpt["source_refs"][0]["digest"] == docs["callback-retry-contract-v2"]["digest"]
    else:
        assert "compare_scoped_protocols" not in tool_results


def test_e04_manifest_is_post_freeze_and_runtime_scope_does_not_change_shared_grants(tmp_path: Path):
    manifest, manifest_sha = _e04_fixture_manifest()
    assert manifest["fixture_specification_status"] == "POST_FREEZE_FIXTURE_SPECIFIED"
    assert manifest["evaluation_boundary"]["real_provider_authorized_by_this_manifest"] is False
    assert manifest["evaluation_boundary"]["expected_answer_in_model_context"] is False
    assert manifest["authorization_fixture"]["allowed_document_ids"] == [
        "callback-retry-contract", "callback-retry-contract-v2",
    ]
    registry = _e04_runtime_registry()
    assert registry["projects"][0]["project_id"] == "orders-e04-absence"
    assert registry["projects"][0]["evaluation_fixture"]["manifest_sha256"] == manifest_sha
    shared = json.loads((ROOT / "knowledge" / "assistant-access.json").read_text(encoding="utf-8"))
    assert "orders-e04-absence" not in {row["project_id"] for row in shared["projects"]}
    assert Path(E04_FIXTURE_MANIFEST_PATH).is_file()


def test_e04_modified_fixture_manifest_fails_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    manifest = json.loads(E04_FIXTURE_MANIFEST_PATH.read_text(encoding="utf-8"))
    manifest["documents"][1]["sha256"] = "0" * 64
    altered = tmp_path / "altered-manifest.json"
    altered.write_text(json.dumps(manifest), encoding="utf-8")
    monkeypatch.setattr(runner, "E04_FIXTURE_MANIFEST_PATH", altered)
    with pytest.raises(EvaluationPreflightError, match="E04_TRUSTED_DOCUMENT_DIGEST_MISMATCH"):
        runner._e04_fixture_manifest()


@pytest.mark.parametrize("unauthorized_document", ["callback-ack-contract", "callback-retry-contract-v1-4"])
def test_e04_scope_is_owner_tenant_and_runtime_isolated(tmp_path: Path, unauthorized_document: str):
    root, _name, runtime = _runtime(tmp_path, "isolation")
    database = runtime / "domain.sqlite3"
    registry_path = runtime / "assistant-access.json"
    identity_a = trusted_identity(database, "support-a")
    session_a = create_session(database, identity_a)["session_id"]
    identity_b = trusted_identity(database, "support-b")
    session_b = create_session(database, identity_b)["session_id"]

    docs = list_scoped_protocols(
        database, identity_a, session_a, topic="callback retry", registry_path=registry_path,
    )
    assert docs["project_id"] == "orders-e04-absence"
    assert {row["document_id"] for row in docs["protocol_documents"]} == {
        "callback-retry-contract", "callback-retry-contract-v2",
    }
    other_scope = assistant_knowledge.list_scopes(
        database, identity_b, session_b, registry_path=registry_path,
    )
    assert other_scope["items"] == []
    assert other_scope["reason_code"] == "KNOWLEDGE_SCOPE_DENIED"
    with pytest.raises(DocumentNotAuthorizedError):
        compare_scoped_protocols(
            database, identity_a, session_a,
            base_document_id="callback-retry-contract",
            target_document_id=unauthorized_document,
            registry_path=registry_path,
        )

    other_runtime = root / ".runtime" / "user-demo-r2-e04-other-runtime"
    from initialize_demo import initialize_user_demo
    initialize_user_demo(other_runtime, require_absent_directory=True)
    other_database = other_runtime / "domain.sqlite3"
    other_identity = trusted_identity(other_database, "support-a")
    other_session = create_session(other_database, other_identity)["session_id"]
    default = assistant_knowledge.list_scopes(other_database, other_identity, other_session)
    assert "orders-e04-absence" not in {row["project_id"] for row in default["items"]}


def test_e04_revocation_invalidates_persisted_sources_and_answer_projection(tmp_path: Path):
    root, name, runtime = _runtime(tmp_path, "revoke")
    result, _model, _trace, sources = _execute(root, name, runtime)
    assert sources["current"] is True
    registry_path = runtime / "assistant-access.json"
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    registry["projects"][0]["active"] = False
    registry_path.write_text(json.dumps(registry, ensure_ascii=False), encoding="utf-8")

    with TestClient(_app(runtime, make_e04_fixture_model()), base_url=ORIGIN, raise_server_exceptions=False) as client:
        login = client.post(
            "/api/auth/login", headers={"Origin": ORIGIN},
            json={"actor_id": "support-a", "password": PASSWORDS["support-a"]},
        )
        assert login.status_code == 200
        headers = {"Origin": ORIGIN, "X-CSRF-Token": login.json()["csrf_token"]}
        current = client.get(f"/api/runs/{result['run_id']}/assistant-sources", headers=headers)
        assert current.status_code == 200 and current.json()["current"] is False
        messages = client.get(f"/api/sessions/{result['session_id']}/messages", headers=headers)
        answer = next(row for row in messages.json()["items"] if row["role"] == "ASSISTANT")
        assert "来源已失效" in answer["body"]


def test_e04_stored_digest_mismatch_invalidates_source(tmp_path: Path):
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
    with TestClient(_app(runtime, make_e04_fixture_model()), base_url=ORIGIN, raise_server_exceptions=False) as client:
        login = client.post(
            "/api/auth/login", headers={"Origin": ORIGIN},
            json={"actor_id": "support-a", "password": PASSWORDS["support-a"]},
        )
        headers = {"Origin": ORIGIN, "X-CSRF-Token": login.json()["csrf_token"]}
        current = client.get(f"/api/runs/{result['run_id']}/assistant-sources", headers=headers)
        assert current.status_code == 200
        assert current.json()["current"] is False
        assert all(item["result"] is None for item in current.json()["items"])
