from __future__ import annotations

import hashlib
import json
import sqlite3
import sys
import runpy
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
USER_DEMO_DIR = ROOT / "scripts" / "user-demo"
if str(USER_DEMO_DIR) not in sys.path:
    sys.path.insert(0, str(USER_DEMO_DIR))

from initialize_demo import initialize_user_demo  # noqa: E402
from opspilot.domain.database import connect  # noqa: E402
from opspilot.domain.task_control import (  # noqa: E402
    create_session,
    create_task_with_initial_run,
    trusted_identity,
)
from runtime_paths import UserDemoRuntimePathError  # noqa: E402
import runtime_paths  # noqa: E402


EXPORTER_PATH = ROOT / "scripts" / "user-demo" / "export_live_evidence.py"
RAW_API_KEY = "sk-fixture-export-secret123456"
RAW_AUTH = "fixture-bearer-export-secret"
RAW_COOKIE = "fixture-cookie-export-secret"
RAW_PASSWORD = "fixture-password-export-secret"


def _fresh_runtime(root: Path, runtime_name: str) -> dict[str, object]:
    runtime_dir = root / ".runtime" / runtime_name
    initialize_user_demo(runtime_dir, require_absent_directory=True)
    db_path = runtime_dir / "domain.sqlite3"
    support = trusted_identity(db_path, "support-a")
    session_id = str(create_session(db_path, support)["session_id"])
    task = create_task_with_initial_run(
        db_path,
        support,
        session_id=session_id,
        service_id="orders-async-demo",
        integration_id="async-integration-a",
        s3_order_id="async-order",
        ticket_id=f"EXPORT-{runtime_name}",
        initial_message="Check the current receiver status for the authorized event.",
        idempotency_key=f"export-{runtime_name}",
        assistant_core=True,
    )
    return {
        "runtime_name": runtime_name,
        "runtime_dir": runtime_dir,
        "db_path": db_path,
        "session_id": session_id,
        "task": task,
    }


def _add_model_mcp_trace(runtime: dict[str, object], *, usage: bool = True) -> None:
    db_path = Path(runtime["db_path"])
    task = runtime["task"]
    run_id = str(task["run_id"])
    task_id = str(task["task_id"])
    session_id = str(runtime["session_id"])
    message_id = f"answer-{run_id}"
    model_call_id = f"model-call-{run_id}"
    mcp_call_id = f"mcp-call-{run_id}"
    observation_id = f"observation-{run_id}"
    evidence_id = f"evidence-{run_id}"
    attempt_id = f"attempt-{run_id}"
    context = {
        "model": "synthetic-fixture",
        "api_key": RAW_API_KEY,
        "messages": [{"role": "user", "content": f"Authorization: Bearer {RAW_AUTH}\nCookie: {RAW_COOKIE}"}],
        "tools": [],
    }
    provider_result = {"choices": [{"message": {"role": "assistant", "content": "The current Receiver observation is QUEUED."}}]}
    usage_json = json.dumps([{"input_tokens": 23, "output_tokens": 11, "total_tokens": 34}]) if usage else None
    now = "2026-11-14T12:00:00Z"
    answer = f"The current Receiver observation is QUEUED. password={RAW_PASSWORD}"
    answer_digest = hashlib.sha256(answer.encode("utf-8")).hexdigest()
    observation_result = {
        "event_id": "event-fixture-001",
        "status": "QUEUED",
        "observed_at": now,
    }
    result_digest = hashlib.sha256(json.dumps(observation_result, sort_keys=True).encode()).hexdigest()
    with connect(db_path) as connection:
        connection.execute(
            """INSERT INTO messages
               (message_id,tenant_id,session_id,task_id,sequence,role,input_kind,body,body_digest,
                command_id,created_at,application_state,applied_run_id)
               VALUES (?,?,?,?,?,'ASSISTANT','CHAT_READONLY',?,?,?,?,'APPLIED_TO_RUN',?)""",
            (message_id, "tenant-a", session_id, task_id, 2, answer, answer_digest,
             f"command-answer-{run_id}", now, run_id),
        )
        connection.execute(
            """INSERT INTO chat_attempts
               (attempt_id,tenant_id,actor_id,session_id,task_id,run_id,attempt_no,model_id,
                prompt_digest,status,provider_response_id,input_tokens,output_tokens,total_tokens,
                created_at,completed_at)
               VALUES (?,?,?,?,?,?,1,'synthetic-fixture','prompt-digest','SUCCEEDED',?,?,?,?,?,?)""",
            (attempt_id, "tenant-a", "support-a", session_id, task_id, run_id,
             f"response-{run_id}", 23 if usage else None, 11 if usage else None,
             34 if usage else None, now, now),
        )
        connection.execute(
            """INSERT INTO chat_context_manifests
               (manifest_id,attempt_id,run_id,tenant_id,session_id,task_id,
                selected_message_ids_json,evidence_refs_json,memory_refs_json,model_call_refs_json,
                excluded_sources_json,truncation_json,trusted_state_digest,prompt_digest,created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (f"manifest-{run_id}", attempt_id, run_id, "tenant-a", session_id, task_id,
             json.dumps([str(task["message_id"])]), json.dumps([evidence_id]), "[]",
             json.dumps([model_call_id]), "[]", "[]", "trusted-state-digest", "prompt-digest", now),
        )
        connection.execute(
            """INSERT INTO assistant_calls
               (call_id,run_id,kind,logical_key,request_json,request_digest,status,result_json,usage_json,created_at,completed_at)
               VALUES (?,?, 'MODEL','model:1',?,'request-digest','OK',?,?,?,?)""",
            (model_call_id, run_id, json.dumps(context), json.dumps(provider_result), usage_json, now, now),
        )
        connection.execute(
            """INSERT INTO assistant_calls
               (call_id,run_id,kind,logical_key,request_json,request_digest,status,result_json,
                observation_id,evidence_id,created_at,completed_at)
               VALUES (?,?, 'MCP','tool:1',?,'tool-request-digest','OK',?,?,?,?,?)""",
            (mcp_call_id, run_id, json.dumps({"name": "get_receiver_processing", "arguments": {}}),
             json.dumps(observation_result), observation_id, evidence_id, now, now),
        )
        connection.execute(
            """INSERT INTO d2_tool_observations
               (observation_id,task_id,call_id,attempt_id,tool_call_id,tool_name,argument_digest,
                status,progress_added,error_class,result_digest,result_json,evidence_id,created_at)
               VALUES (?,?,?,?,?,?,?,'SUCCEEDED',1,NULL,?,?,?,?)""",
            (observation_id, task_id, mcp_call_id, attempt_id, f"tool-call-{run_id}",
             "get_receiver_processing", "argument-digest", result_digest,
             json.dumps(observation_result), evidence_id, now),
        )
        connection.execute(
            """INSERT INTO d2_evidence
               (evidence_id,tenant_id,task_id,call_id,tool_call_id,resource_id,principal_id,
                data_source,fetched_at,observed_versions_json,fact_type,facts_json,original_result_ref,
                trust_class,digest)
               VALUES (?,?,?,?,?,?,?,'fixture-mcp',?,?, 's3_receiver',?,?,?,?)""",
            (evidence_id, "tenant-a", task_id, mcp_call_id, f"tool-call-{run_id}",
             "async-order", "principal-async-a", now, json.dumps({"receiver_version": 1}),
             json.dumps(observation_result), observation_id, "TRUSTED_DOMAIN_OBSERVATION", result_digest),
        )
        connection.execute(
            """INSERT INTO assistant_runtime_spends
               (dispatch_id,pool_id,authority_id,request_key,assistant_call_id,run_id,session_id,
                source_message_id,logical_key,request_digest,grant_id,grant_version,price_version,
                input_rate_micro_per_million,output_rate_micro_per_million,max_input_tokens,
                max_output_tokens,reserved_usd_micro,settled_usd_micro,status,response_status,
                usage_json,completion_id,created_at,send_granted_at,completed_at,updated_at)
               VALUES (?,'DEFAULT','synthetic-fixture-authority',?,?,?,?,?,?,?,'synthetic-fixture-grant',
                       1,'synthetic-fixture-price',0,0,4096,256,100,?,?,200,?, ?,?,?,?,?)""",
            (f"dispatch-{run_id}", f"request-{run_id}", model_call_id, run_id, session_id,
             str(task["message_id"]), "model:1", "request-digest", 42 if usage else None,
             "DELIVERED" if usage else "RESPONSE_STORED", usage_json,
             f"completion-{run_id}", now, now, now, now),
        )


def _add_other_session_spend(db_path: Path, session_id: str, run_id: str, source_message_id: str) -> None:
    with connect(db_path) as connection:
        connection.execute(
            """INSERT INTO assistant_runtime_spends
               (dispatch_id,pool_id,authority_id,request_key,assistant_call_id,run_id,session_id,
                source_message_id,logical_key,request_digest,grant_id,grant_version,price_version,
                input_rate_micro_per_million,output_rate_micro_per_million,max_input_tokens,
                max_output_tokens,reserved_usd_micro,settled_usd_micro,status,response_status,
                usage_json,completion_id,created_at,send_granted_at,completed_at,updated_at)
                VALUES ('other-dispatch','DEFAULT','synthetic-fixture-authority','other-request',
                        'other-call',?,?,?,'model:1','other-digest',
                        'synthetic-fixture-grant',1,'synthetic-fixture-price',0,0,4096,256,100,
                       999,'DELIVERED',200,'{\"input_tokens\":99,\"output_tokens\":9}',
                       'other-completion','2026-11-14T12:00:00Z','2026-11-14T12:00:00Z',
                       '2026-11-14T12:00:00Z','2026-11-14T12:00:00Z')""",
            (run_id, session_id, source_message_id),
        )


def _exporter():
    return runpy.run_path(str(EXPORTER_PATH))["export_session"]


def test_runtime_alias_isolation_and_default_user_demo_compatibility(tmp_path, monkeypatch):
    root = tmp_path / "repo"
    (root / ".runtime").mkdir(parents=True)
    first = _fresh_runtime(root, "user-demo-e01")
    second = _fresh_runtime(root, "user-demo-e03")
    _add_model_mcp_trace(first)
    _add_model_mcp_trace(second)
    first_db = Path(first["db_path"])
    other_session_id = str(create_session(first_db, trusted_identity(first_db, "support-a"))["session_id"])
    other_task = create_task_with_initial_run(
        first_db,
        trusted_identity(first_db, "support-a"),
        session_id=other_session_id,
        service_id="orders-async-demo",
        integration_id="async-integration-a",
        s3_order_id="async-order",
        ticket_id="EXPORT-OTHER-SESSION",
        initial_message="A distinct evaluation Session and Run.",
        idempotency_key="export-other-session",
        assistant_core=True,
    )
    _add_other_session_spend(first_db, other_session_id, str(other_task["run_id"]), str(other_task["message_id"]))
    export = _exporter()
    monkeypatch.setitem(export.__globals__, "_private_values", lambda: [])

    first_output = Path(first["runtime_dir"]) / "evidence" / "e01.json"
    result = export(str(first["session_id"]), first_output, runtime_name="user-demo-e01", root=root)
    first_doc = json.loads(first_output.read_text(encoding="utf-8"))
    assert result["runs"] == 1 and first_doc["session"]["session_id"] == first["session_id"]
    assert all(row["run_id"] == first["task"]["run_id"] for row in first_doc["runs"])
    assert "QUEUED" in json.dumps(first_doc["messages"])
    assert first_doc["task_bindings"][0]["task_id"] == first["task"]["task_id"]
    assert first_doc["observations"][0]["observation_id"] == f"observation-{first['task']['run_id']}"
    assert first_doc["evidence"][0]["evidence_id"] == f"evidence-{first['task']['run_id']}"
    assert first_doc["chat_attempts"][0]["input_tokens"] == 23
    assert first_doc["chat_attempts"][0]["output_tokens"] == 11
    assert first_doc["runtime_spends"][0]["usage_json"][0]["total_tokens"] == 34
    assert first_doc["runtime_spends"][0]["settled_usd_micro"] == 42
    assert len(first_doc["runtime_spends"]) == 1
    assert first_doc["session_spend_summary"]["responses_received_count"] == 1
    assert first_doc["session_spend_summary"]["scope"] == "SELECTED_SESSION_ONLY"

    with pytest.raises(RuntimeError, match="SESSION_SCOPE_DENIED"):
        export(str(second["session_id"]), first_output.parent / "wrong-runtime.json",
              runtime_name="user-demo-e01", root=root)
    with pytest.raises(RuntimeError, match="SESSION_SCOPE_DENIED"):
        export(str(first["session_id"]), first_output.parent / "wrong-actor.json",
              runtime_name="user-demo-e01", actor_id="support-b", root=root)

    default = _fresh_runtime(root, "user-demo")
    default_output = Path(default["runtime_dir"]) / "evidence" / "default.json"
    export(str(default["session_id"]), default_output, root=root)
    assert json.loads(default_output.read_text(encoding="utf-8"))["session"]["session_id"] == default["session_id"]


def test_usage_missing_is_null_and_secrets_are_redacted(tmp_path, monkeypatch):
    root = tmp_path / "repo"
    (root / ".runtime").mkdir(parents=True)
    runtime = _fresh_runtime(root, "user-demo-e01")
    _add_model_mcp_trace(runtime, usage=False)
    export = _exporter()
    monkeypatch.setitem(export.__globals__, "_private_values", lambda: [RAW_PASSWORD])
    output = Path(runtime["runtime_dir"]) / "evidence" / "trace.json"
    export(str(runtime["session_id"]), output, runtime_name="user-demo-e01", root=root)
    text = output.read_text(encoding="utf-8")
    doc = json.loads(text)

    assert doc["chat_attempts"][0]["input_tokens"] is None
    assert doc["chat_attempts"][0]["output_tokens"] is None
    model_call = next(row for row in doc["assistant_calls_actual_model_input_output"] if row["kind"] == "MODEL")
    assert model_call["usage_json"] is None
    assert doc["runtime_spends"][0]["usage_json"] is None
    assert doc["runtime_spends"][0]["settled_usd_micro"] is None
    assert doc["session_spend_summary"]["responses_missing_usage_count"] == 1
    assert doc["session_spend_summary"]["responses_missing_settlement_count"] == 1
    assert doc["session_spend_summary"]["scope"] == "SELECTED_SESSION_ONLY"
    assert all(secret not in text for secret in (RAW_API_KEY, RAW_AUTH, RAW_COOKIE, RAW_PASSWORD))
    assert "[REDACTED]" in text


def test_cli_runtime_name_exports_selected_alias(tmp_path, monkeypatch, capsys):
    root = tmp_path / "repo"
    (root / ".runtime").mkdir(parents=True)
    runtime = _fresh_runtime(root, "user-demo-e01")
    _add_model_mcp_trace(runtime)
    namespace = runpy.run_path(str(EXPORTER_PATH))
    monkeypatch.setitem(namespace["main"].__globals__, "ROOT", root)
    monkeypatch.setitem(namespace["main"].__globals__, "_private_values", lambda: [])
    output = Path(runtime["runtime_dir"]) / "evidence" / "cli.json"
    monkeypatch.setattr(sys, "argv", [
        str(EXPORTER_PATH), "--runtime-name", "user-demo-e01", "--actor-id", "support-a",
        "--session-id", str(runtime["session_id"]), "--output", str(output),
    ])
    assert namespace["main"]() == 0
    assert json.loads(output.read_text(encoding="utf-8"))["session"]["session_id"] == runtime["session_id"]
    assert "Secret values and authorization material" in capsys.readouterr().out


def test_export_rejects_missing_paths_traversal_and_output_escape(tmp_path):
    root = tmp_path / "repo"
    (root / ".runtime").mkdir(parents=True)
    export = _exporter()
    with pytest.raises(UserDemoRuntimePathError, match="RUNTIME_NAME_INVALID"):
        export("session", tmp_path / "outside.json", runtime_name="../user-demo", root=root)
    with pytest.raises(RuntimeError, match="USER_DEMO_RUNTIME_MISSING"):
        export("session", root / ".runtime" / "user-demo-missing" / "evidence" / "x.json",
               runtime_name="user-demo-missing", root=root)
    empty_runtime = root / ".runtime" / "user-demo-empty"
    empty_runtime.mkdir()
    with pytest.raises(RuntimeError, match="DATABASE_MISSING_OR_UNSAFE"):
        export("session", empty_runtime / "evidence" / "x.json", runtime_name="user-demo-empty", root=root)

    runtime = _fresh_runtime(root, "user-demo-e01")
    with pytest.raises(RuntimeError, match="EVIDENCE_OUTPUT_MUST_STAY_INSIDE_ISOLATED_RUNTIME"):
        export(str(runtime["session_id"]), tmp_path / "outside.json", runtime_name="user-demo-e01", root=root)


def test_export_rejects_runtime_and_domain_symlinks(tmp_path):
    root = tmp_path / "repo"
    runtime_root = root / ".runtime"
    runtime_root.mkdir(parents=True)
    outside = tmp_path / "outside"
    outside.mkdir()
    export = _exporter()

    runtime_link = runtime_root / "user-demo-linked"
    try:
        runtime_link.symlink_to(outside, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("Directory symlinks are unavailable in this Windows test environment.")
    with pytest.raises(UserDemoRuntimePathError, match="RUNTIME_REPARSE_POINT"):
        export("session", runtime_link / "evidence" / "x.json", runtime_name="user-demo-linked", root=root)

    runtime = _fresh_runtime(root, "user-demo-e01")
    db_path = Path(runtime["db_path"])
    original_db = tmp_path / "original.sqlite3"
    db_path.replace(original_db)
    try:
        db_path.symlink_to(original_db)
    except (OSError, NotImplementedError):
        pytest.skip("File symlinks are unavailable in this Windows test environment.")
    with pytest.raises(RuntimeError, match="DATABASE_MISSING_OR_UNSAFE"):
        export(str(runtime["session_id"]), Path(runtime["runtime_dir"]) / "evidence" / "x.json",
               runtime_name="user-demo-e01", root=root)


def test_export_rejects_evidence_output_symlink(tmp_path):
    root = tmp_path / "repo"
    (root / ".runtime").mkdir(parents=True)
    runtime = _fresh_runtime(root, "user-demo-e01")
    export = _exporter()
    outside = tmp_path / "outside"
    outside.mkdir()
    evidence_dir = Path(runtime["runtime_dir"]) / "evidence"
    evidence_dir.mkdir()
    try:
        (evidence_dir / "linked").symlink_to(outside, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("Directory symlinks are unavailable in this Windows test environment.")
    with pytest.raises(RuntimeError, match="EVIDENCE_OUTPUT_MUST_STAY_INSIDE_ISOLATED_RUNTIME|REPARSE_POINT"):
        export(str(runtime["session_id"]), evidence_dir / "linked" / "escape.json",
               runtime_name="user-demo-e01", root=root)


def test_export_reparse_guards_are_deterministically_exercised(tmp_path, monkeypatch):
    root = tmp_path / "repo"
    runtime_root = root / ".runtime"
    runtime_root.mkdir(parents=True)
    export = _exporter()
    runtime_link = runtime_root / "user-demo-linked"
    runtime_link.mkdir()
    original_runtime_check = runtime_paths._is_reparse_path
    monkeypatch.setattr(runtime_paths, "_is_reparse_path",
                        lambda path: Path(path) == runtime_link or original_runtime_check(path))
    with pytest.raises(UserDemoRuntimePathError, match="RUNTIME_REPARSE_POINT"):
        export("session", runtime_link / "evidence" / "x.json", runtime_name="user-demo-linked", root=root)
    monkeypatch.setattr(runtime_paths, "_is_reparse_path", original_runtime_check)

    runtime = _fresh_runtime(root, "user-demo-e01")
    db_path = Path(runtime["db_path"])
    monkeypatch.setitem(export.__globals__, "_is_reparse_path",
                        lambda path: Path(path) == db_path)
    with pytest.raises(RuntimeError, match="DATABASE_MISSING_OR_UNSAFE"):
        export(str(runtime["session_id"]), Path(runtime["runtime_dir"]) / "evidence" / "x.json",
               runtime_name="user-demo-e01", root=root)

    monkeypatch.setitem(export.__globals__, "_is_reparse_path", lambda path: False)
    evidence_dir = Path(runtime["runtime_dir"]) / "evidence"
    link_dir = evidence_dir / "linked"
    link_dir.mkdir(parents=True)
    monkeypatch.setitem(export.__globals__, "_is_reparse_path",
                        lambda path: Path(path) == link_dir)
    with pytest.raises(RuntimeError, match="EVIDENCE_OUTPUT_REPARSE_POINT"):
        export(str(runtime["session_id"]), link_dir / "x.json", runtime_name="user-demo-e01", root=root)


def test_export_connection_is_read_only_and_selected_runtime_db_is_unchanged(tmp_path, monkeypatch):
    root = tmp_path / "repo"
    (root / ".runtime").mkdir(parents=True)
    runtime = _fresh_runtime(root, "user-demo-e01")
    export = _exporter()
    monkeypatch.setitem(export.__globals__, "_private_values", lambda: [])
    db_path = Path(runtime["db_path"])
    before = hashlib.sha256(db_path.read_bytes()).hexdigest()
    real_connect = sqlite3.connect
    connect_calls: list[tuple[str, bool]] = []

    def read_only_connect(database, *args, **kwargs):
        connect_calls.append((str(database), bool(kwargs.get("uri"))))
        return real_connect(database, *args, **kwargs)

    monkeypatch.setattr(sqlite3, "connect", read_only_connect)
    output = Path(runtime["runtime_dir"]) / "evidence" / "readonly.json"
    export(str(runtime["session_id"]), output, runtime_name="user-demo-e01", root=root)
    after = hashlib.sha256(db_path.read_bytes()).hexdigest()
    assert before == after
    assert len(connect_calls) == 1 and connect_calls[0][1] is True
    assert "mode=ro" in connect_calls[0][0]
