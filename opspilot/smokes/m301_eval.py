from __future__ import annotations

"""Frozen exploratory Memory ON/OFF evaluation for OpsPilot M3-01."""

import argparse
import json
import os
import platform
import re
import sqlite3
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from importlib.metadata import version
from pathlib import Path
from typing import Any

from opspilot.config import MODEL_NAME, ROOT, load_local_environment
from opspilot.domain.d2 import (
    attempt_counts,
    finish_attempt,
    get_scope_authz_facts_fact,
    list_model_traces,
    list_observations,
    probe_endpoint_fact,
    record_tool_observation,
    reserve_attempt,
)
from opspilot.domain.database import connect, initialize, reset_fixture
from opspilot.domain.episodic_memory import confirm_memory, create_memory_candidate
from opspilot.domain.s2_diagnosis import create_diagnosis_receipt
from opspilot.domain.task_control import (
    apply_pending_critical_inputs,
    claim_task_run,
    create_session,
    create_task_with_initial_run,
    trusted_identity,
)


def _absolute(value: str | Path) -> Path:
    result = Path(value)
    return (result if result.is_absolute() else ROOT / result).resolve()


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")


def _backup(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(source) as source_connection, sqlite3.connect(target) as target_connection:
        source_connection.backup(target_connection)


def _seed_s2_source(path: Path) -> dict[str, object]:
    from opspilot.domain.api import make_server

    reset_fixture(path, "S2_SCOPE_DENIED")
    identity = trusted_identity(path, "support-a")
    session = create_session(path, identity)
    created = create_task_with_initial_run(
        path, identity, session_id=str(session["session_id"]), service_id="orders-demo",
        integration_id="integration-a", ticket_id="M301-S2-SOURCE",
        initial_message="请调查订单接口当前的访问拒绝原因。",
        idempotency_key="m301-s2-source-task",
    )
    task_id, run_id = str(created["task_id"]), str(created["run_id"])
    claim_task_run(path, identity, run_id)
    apply_pending_critical_inputs(path, identity, run_id)
    server = make_server(path, "tenant-a", "127.0.0.1", 0)
    worker = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
    worker.start()
    try:
        host, port = server.server_address
        live_api = f"http://{host}:{port}"
        probe = probe_endpoint_fact(path, task_id, "orders-demo", "integration-a", live_api)
        if probe.get("facts", {}).get("http_status") != 403:
            raise RuntimeError("S2 source HTTP Probe did not return the required real 403.")
        probe_call = "m301-source-probe"
        probe_attempt, _ = reserve_attempt(
            path, task_id, "MCP", 6, call_id=probe_call, tool_call_id="m301-source-probe-tool",
            tool_name="probe_endpoint", argument_digest="m301-source-probe-args", run_id=run_id,
        )
        finish_attempt(path, probe_attempt, "OK")
        probe_observation = record_tool_observation(
            path, task_id=task_id, call_id=probe_call, attempt_id=probe_attempt,
            tool_call_id="m301-source-probe-tool", tool_name="probe_endpoint",
            arguments={"service_id": "orders-demo", "integration_id": "integration-a"},
            status="OK", result=probe,
        )
        request_id = str(probe["facts"]["request_id"])
        authz = get_scope_authz_facts_fact(path, task_id, request_id)
        authz_call = "m301-source-authz"
        authz_attempt, _ = reserve_attempt(
            path, task_id, "MCP", 6, call_id=authz_call, tool_call_id="m301-source-authz-tool",
            tool_name="get_scope_authz_facts", argument_digest="m301-source-authz-args", run_id=run_id,
        )
        finish_attempt(path, authz_attempt, "OK")
        authz_observation = record_tool_observation(
            path, task_id=task_id, call_id=authz_call, attempt_id=authz_attempt,
            tool_call_id="m301-source-authz-tool", tool_name="get_scope_authz_facts",
            arguments={"request_id": request_id}, status="OK", result=authz,
        )
        receipt = create_diagnosis_receipt(
            path, task_id=task_id, run_id=run_id,
            evidence_ids=[str(probe_observation["evidence_id"]), str(authz_observation["evidence_id"])],
        )
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=2)
    candidate = create_memory_candidate(
        path, task_id, "support-a", idempotency_key="m301-s2-source-candidate",
    )
    active = confirm_memory(
        path, str(candidate["memory_id"]), "approver-a", idempotency_key="m301-s2-source-confirm",
    )
    return {
        "task_id": task_id, "run_id": run_id,
        "probe_status": probe["facts"]["http_status"], "request_id": request_id,
        "diagnosis_receipt_id": receipt["receipt_id"], "memory_id": active["memory_id"],
        "memory_version": active["version"], "memory_digest": active["content_digest"],
    }


def _prepare_s1_memory(path: Path, source_task_id: str) -> dict[str, object]:
    candidate = create_memory_candidate(
        path, source_task_id, "support-a", idempotency_key="m301-s1-source-candidate",
    )
    active = confirm_memory(
        path, str(candidate["memory_id"]), "approver-a", idempotency_key="m301-s1-source-confirm",
    )
    return {
        "task_id": source_task_id, "memory_id": active["memory_id"],
        "memory_version": active["version"], "memory_digest": active["content_digest"],
    }


def _s1_source_task(path: Path) -> str:
    with connect(path) as connection:
        row = connection.execute(
            """SELECT task_id FROM d3_action_ledgers
               WHERE action_kind = 'REPAIR' AND status = 'COMMITTED'
               ORDER BY committed_at DESC LIMIT 1""",
        ).fetchone()
    if row is None:
        raise RuntimeError("The supplied S1 source database has no committed REPAIR.")
    return str(row["task_id"])


def _set_target_scenario(path: Path, scenario: str, tenant_id: str) -> None:
    with connect(path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        if tenant_id == "tenant-a":
            suffix = "a"
        elif tenant_id == "tenant-b":
            suffix = "b"
        else:
            raise ValueError("Unknown frozen tenant.")
        if scenario in {"S1_POS", "S1_DISABLED", "S2_INVALID_CREDENTIAL"}:
            connection.execute(
                "UPDATE integrations SET credential_ref = 'cred-v1', config_version = 7 WHERE tenant_id = ? AND integration_id = ?",
                (tenant_id, f"integration-{suffix}"),
            )
        else:
            connection.execute(
                "UPDATE integrations SET credential_ref = 'cred-v2', config_version = 8 WHERE tenant_id = ? AND integration_id = ?",
                (tenant_id, f"integration-{suffix}"),
            )
        connection.execute(
            "UPDATE principals SET status = ?, principal_version = principal_version + 1 WHERE tenant_id = ? AND principal_id = ?",
            ("DISABLED" if scenario == "S1_DISABLED" else "ENABLED", tenant_id, f"principal-{suffix}"),
        )
        scopes = [] if scenario == "S2_SCOPE_DENIED" else ["orders.read"]
        connection.execute(
            "UPDATE principal_scope_grants SET granted_scopes_json = ?, grant_version = grant_version + 1 WHERE tenant_id = ? AND principal_id = ?",
            (json.dumps(scopes, separators=(",", ":")), tenant_id, f"principal-{suffix}"),
        )


def _create_target(path: Path, case: dict[str, object]) -> tuple[str, str, str]:
    tenant_id = str(case.get("target_tenant", "tenant-a"))
    actor_id = "support-b" if tenant_id == "tenant-b" else "support-a"
    identity = trusted_identity(path, actor_id)
    session = create_session(path, identity)
    created = create_task_with_initial_run(
        path, identity, session_id=str(session["session_id"]), service_id="orders-demo",
        integration_id=f"integration-{tenant_id[-1]}", ticket_id=f"M301-{case['pair_id']}",
        initial_message=str(case["user_surface"]), idempotency_key=f"m301-target-{case['pair_id']}",
    )
    return str(created["task_id"]), str(created["run_id"]), actor_id


def _redacted_result(db_path: Path, task_id: str, run_id: str, actor_id: str, elapsed: float) -> dict[str, object]:
    from opspilot.domain.d2 import read_report
    from opspilot.domain.s2_diagnosis import get_s2_task_outcome

    binding = None
    with connect(db_path) as connection:
        binding_row = connection.execute("SELECT tenant_id FROM task_bindings WHERE task_id = ?", (task_id,)).fetchone()
        memory_rows = connection.execute(
            """SELECT call_id, prompt_digest, selected_memories_json, model_status, error_class
               FROM d5_context_provenance WHERE task_id = ? ORDER BY built_at, call_id""",
            (task_id,),
        ).fetchall()
        writes = {
            "repair_ledgers": int(connection.execute(
                "SELECT COUNT(*) FROM d3_action_ledgers WHERE task_id = ? AND action_kind = 'REPAIR'", (task_id,),
            ).fetchone()[0]),
            "deliver_ledgers": int(connection.execute(
                "SELECT COUNT(*) FROM d3_action_ledgers WHERE task_id = ? AND action_kind = 'DELIVER'", (task_id,),
            ).fetchone()[0]),
        }
        binding = str(binding_row["tenant_id"]) if binding_row else None
    traces = list_model_traces(db_path, task_id)
    observations = list_observations(db_path, task_id)
    from opspilot.domain.task_control import get_task_run

    run = get_task_run(db_path, trusted_identity(db_path, actor_id), run_id)
    report = read_report(db_path, task_id)
    s2_outcome = get_s2_task_outcome(db_path, task_id) if binding else {}
    selected: list[dict[str, object]] = []
    for row in memory_rows:
        try:
            memories = json.loads(str(row["selected_memories_json"]))
        except json.JSONDecodeError:
            memories = []
        for memory in memories:
            selected.append({
                "call_id": str(row["call_id"]), "prompt_digest": str(row["prompt_digest"]),
                "model_status": str(row["model_status"]), "memory_id": memory.get("memory_id"),
                "version": memory.get("version"), "digest": memory.get("digest"),
                "source_task_id": memory.get("source_task_id"), "source_outcome": memory.get("source_outcome"),
            })
    return {
        "task_id": task_id, "run_id": run_id, "tenant_id": binding,
        "run_status": run["status"], "waiting_reason": run["blocked_reason"],
        "s1_gate_decision": (report or {}).get("report", {}).get("gate_decision", {}).get("decision") if report else None,
        "s2_business_outcome": s2_outcome.get("business_outcome"),
        "s2_reason_code": s2_outcome.get("reason_code"),
        "diagnosis_receipt_id": (s2_outcome.get("diagnosis_receipt") or {}).get("receipt_id") if isinstance(s2_outcome.get("diagnosis_receipt"), dict) else None,
        "model_traces": [{
            "call_id": item.get("call_id"), "model_id": item.get("model_id"), "status": item.get("status"),
            "usage": item.get("usage"), "provider_response_id": item.get("provider_response_id"),
            "tool_names": [call.get("name") for call in item.get("tool_calls", []) if isinstance(call, dict)],
        } for item in traces],
        "mcp_observations": [{
            "tool_name": item.get("tool_name"), "status": item.get("status"),
            "error_class": item.get("error_class"), "evidence_id": item.get("evidence_id"),
            "facts": {key: value for key, value in dict(item.get("result", {}).get("facts", {})).items()
                      if key in {"http_status", "request_id", "outcome", "reason_code", "authn_result_code"}},
        } for item in observations],
        "context_provenance": [{key: row[key] for key in ("call_id", "prompt_digest", "model_status", "error_class")} for row in memory_rows],
        "selected_memories": selected,
        "attempt_counts": attempt_counts(db_path, task_id),
        "business_writes": writes,
        "elapsed_seconds": round(elapsed, 3),
    }


def _run_trial(
    *, db_path: Path, checkpoint_path: Path, task_id: str, run_id: str,
    actor_id: str, s2_mode: bool, memory_enabled: bool, log_path: Path,
) -> dict[str, object]:
    started = time.monotonic()
    tenant_id = "tenant-b" if actor_id == "support-b" else "tenant-a"
    with connect(db_path) as connection:
        grant_before = connection.execute(
            "SELECT granted_scopes_json, grant_version FROM principal_scope_grants WHERE tenant_id = ? AND principal_id = ?",
            (tenant_id, f"principal-{tenant_id[-1]}"),
        ).fetchone()
    grant_before_value = dict(grant_before) if grant_before else None
    command = [
        sys.executable, "-m", "opspilot.smokes.m301_eval_worker",
        "--db", str(db_path), "--checkpoint-db", str(checkpoint_path),
        "--task-id", task_id, "--run-id", run_id, "--actor-id", actor_id,
    ]
    if s2_mode:
        command.append("--s2")
    if not memory_enabled:
        command.append("--memory-off")
    try:
        process = subprocess.run(
            command, cwd=ROOT, text=True, capture_output=True, check=False, timeout=600,
        )
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text(
            f"COMMAND: {json.dumps(command, ensure_ascii=False)}\nEXIT_CODE: {process.returncode}\n"
            f"STDOUT:\n{process.stdout}\nSTDERR:\n{process.stderr}", encoding="utf-8",
        )
        error = None if process.returncode == 0 else {
            "error_class": "M301_WORKER_FAILED", "error": process.stdout[-300:],
        }
    except subprocess.TimeoutExpired as exc:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text(
            f"COMMAND: {json.dumps(command, ensure_ascii=False)}\nTIMEOUT: 600 seconds\n"
            f"STDOUT:\n{str(exc.stdout or '')[-5000:]}\nSTDERR:\n{str(exc.stderr or '')[-2000:]}", encoding="utf-8",
        )
        error = {"error_class": "TimeoutExpired", "error": "M301 worker exceeded 600 seconds."}
    elapsed = time.monotonic() - started
    result = _redacted_result(db_path, task_id, run_id, actor_id, elapsed)
    with connect(db_path) as connection:
        grant_after = connection.execute(
            "SELECT granted_scopes_json, grant_version FROM principal_scope_grants WHERE tenant_id = ? AND principal_id = ?",
            (tenant_id, f"principal-{tenant_id[-1]}"),
        ).fetchone()
    result["scope_grant_before"] = grant_before_value
    result["scope_grant_after"] = dict(grant_after) if grant_after else None
    result["no_scope_grant_write"] = (
        result["scope_grant_before"] is not None
        and result["scope_grant_before"] == result["scope_grant_after"]
    )
    result["execution_error"] = error
    return result


def _trial_has_complete_provider_trace(db_path: Path, task_id: str) -> bool:
    with connect(db_path) as connection:
        rows = connection.execute(
            "SELECT status FROM d2_model_traces WHERE task_id = ? ORDER BY created_at, rowid",
            (task_id,),
        ).fetchall()
    return bool(rows) and all(str(row["status"]) == "OK" for row in rows)


def _failed_attempt_snapshot(db_path: Path, task_id: str, pair_id: str, arm: str) -> dict[str, object]:
    with connect(db_path) as connection:
        rows = connection.execute(
            "SELECT call_id, status, assistant_text FROM d2_model_traces WHERE task_id = ? ORDER BY created_at, rowid",
            (task_id,),
        ).fetchall()
    return {
        "pair_id": pair_id, "arm": arm, "task_id": task_id,
        "attempt_status": "FAILED_PROVIDER_CALL" if any(str(row["status"]) != "OK" for row in rows) else "INCOMPLETE_TRACE",
        "model_calls": [{
            "call_id": str(row["call_id"]), "status": str(row["status"]),
            "error_summary": str(row["assistant_text"])[:400] if str(row["status"]) != "OK" else None,
        } for row in rows],
    }


def _target_and_memory_from_template(path: Path, source_problem_type: str) -> tuple[str, str, str, dict[str, object]]:
    with connect(path) as connection:
        target = connection.execute(
            """SELECT b.task_id, b.actor_id, r.run_id FROM task_runs r
               JOIN task_bindings b ON b.task_id = r.task_id
               WHERE r.kind = 'INVESTIGATE' ORDER BY r.created_at DESC LIMIT 1""",
        ).fetchone()
        memory = connection.execute(
            """SELECT memory_id, source_task_id, content_digest, source_outcome, source_refs_json
               FROM d5_memories WHERE state = 'ACTIVE' AND problem_type = ?
               ORDER BY created_at DESC LIMIT 1""",
            (source_problem_type,),
        ).fetchone()
    if target is None or memory is None:
        raise RuntimeError("Pair template is missing its frozen target Run or active source Memory.")
    source_ref = {
        "memory_id": str(memory["memory_id"]), "task_id": str(memory["source_task_id"]),
        "digest": str(memory["content_digest"]), "source_outcome": str(memory["source_outcome"]),
        "source_refs": json.loads(str(memory["source_refs_json"])),
    }
    return str(target["task_id"]), str(target["run_id"]), str(target["actor_id"]), source_ref


def _result_from_persisted_trial(
    trial_db: Path, template_db: Path, task_id: str, run_id: str, actor_id: str,
) -> dict[str, object]:
    with connect(trial_db) as connection:
        run_times = connection.execute(
            "SELECT started_at, ended_at FROM task_runs WHERE run_id = ?", (run_id,),
        ).fetchone()
    elapsed = 0.0
    if run_times and run_times["started_at"] and run_times["ended_at"]:
        started = datetime.fromisoformat(str(run_times["started_at"]).replace("Z", "+00:00"))
        ended = datetime.fromisoformat(str(run_times["ended_at"]).replace("Z", "+00:00"))
        elapsed = max(0.0, (ended - started).total_seconds())
    result = _redacted_result(trial_db, task_id, run_id, actor_id, elapsed)
    tenant_id = "tenant-b" if actor_id == "support-b" else "tenant-a"
    principal_id = f"principal-{tenant_id[-1]}"
    with connect(template_db) as connection:
        before = connection.execute(
            "SELECT granted_scopes_json, grant_version FROM principal_scope_grants WHERE tenant_id = ? AND principal_id = ?",
            (tenant_id, principal_id),
        ).fetchone()
    with connect(trial_db) as connection:
        after = connection.execute(
            "SELECT granted_scopes_json, grant_version FROM principal_scope_grants WHERE tenant_id = ? AND principal_id = ?",
            (tenant_id, principal_id),
        ).fetchone()
    result["scope_grant_before"] = dict(before) if before else None
    result["scope_grant_after"] = dict(after) if after else None
    result["no_scope_grant_write"] = result["scope_grant_before"] is not None and result["scope_grant_before"] == result["scope_grant_after"]
    result["execution_error"] = None
    result["attempt_recovery_note"] = "Reused a persisted successful real Provider/MCP attempt from the frozen pair snapshot; no calls were repeated."
    return result


def run_evaluation(
    source_s1_db: str | Path,
    evidence_dir: str | Path,
    *,
    recover_existing_p01_on: bool = False,
) -> int:
    load_local_environment()
    output = _absolute(evidence_dir)
    output.mkdir(parents=True, exist_ok=True)
    gold_path = ROOT / "docs" / "evidence" / "vnext" / "m3-01" / "GOLD.json"
    gold = json.loads(gold_path.read_text(encoding="utf-8"))
    if os.environ.get(MODEL_NAME) != str(gold["provider"]["model_id"]):
        raise RuntimeError("Loaded model ID does not match frozen Gold; no trial was run.")
    runtime_root = ROOT / ".runtime" / "m301-paired-eval"
    runtime_root.mkdir(parents=True, exist_ok=True)
    s1_source = _absolute(source_s1_db)
    s1_seed = runtime_root / "source-s1-active.sqlite3"
    _backup(s1_source, s1_seed)
    s1_source_info = _prepare_s1_memory(s1_seed, _s1_source_task(s1_seed))
    s2_seed = runtime_root / "source-s2-active.sqlite3"
    if s2_seed.exists():
        s2_seed.unlink()
    initialize(s2_seed)
    s2_source_info = _seed_s2_source(s2_seed)

    if recover_existing_p01_on:
        prior_template = runtime_root / "P01-template.sqlite3"
        prior_on = runtime_root / "P01-on.sqlite3"
        if not prior_template.is_file() or not prior_on.is_file():
            raise RuntimeError("No preserved P01/ON database is available for the explicitly logged recovery.")

    trials: list[dict[str, object]] = []
    for case in gold["cases"]:
        pair_id = str(case["pair_id"])
        source_kind = str(case["source_memory_type"])
        seed = s1_seed if source_kind == "auth_401" else s2_seed
        pair_template = runtime_root / f"{pair_id}-template.sqlite3"
        recovered = recover_existing_p01_on and pair_id == "P01"
        if not recovered:
            _backup(seed, pair_template)
            tenant_id = str(case.get("target_tenant", "tenant-a"))
            _set_target_scenario(pair_template, str(case["target_scenario"]), tenant_id)
            task_id, run_id, actor_id = _create_target(pair_template, case)
        else:
            with connect(pair_template) as connection:
                target = connection.execute(
                    """SELECT b.task_id, b.actor_id, r.run_id FROM task_runs r
                       JOIN task_bindings b ON b.task_id = r.task_id
                       WHERE r.kind = 'INVESTIGATE' ORDER BY r.created_at DESC LIMIT 1""",
                ).fetchone()
                source_memory = connection.execute(
                    "SELECT memory_id, source_task_id FROM d5_memories WHERE state = 'ACTIVE' AND problem_type = 'auth_401' ORDER BY created_at DESC LIMIT 1",
                ).fetchone()
            if target is None or source_memory is None:
                raise RuntimeError("Preserved P01 template is missing its target Run or active source Memory.")
            task_id, run_id, actor_id = str(target["task_id"]), str(target["run_id"]), str(target["actor_id"])
            s1_pair_memory = {"memory_id": str(source_memory["memory_id"]), "task_id": str(source_memory["source_task_id"])}
        memory_ref = (
            s1_pair_memory if source_kind == "auth_401" and recovered
            else (s1_source_info if source_kind == "auth_401" else s2_source_info)
        )
        pair_manifest = {
            "pair_id": pair_id, "task_id": task_id, "run_id": run_id,
            "source_task_id": memory_ref["task_id"] if recovered else memory_ref["task_id"],
            "source_memory_id": memory_ref["memory_id"],
            "target_tenant": str(case.get("target_tenant", "tenant-a")), "scenario": case["target_scenario"],
            "user_surface": case["user_surface"],
            "same_target_snapshot_for_both_arms": True,
            "recovered_from_preserved_run_after_evidence_writer_failure": recovered,
        }
        pair_results: dict[str, object] = {}
        for arm in ("ON", "OFF"):
            trial_db = runtime_root / f"{pair_id}-{arm.lower()}.sqlite3"
            checkpoint_db = runtime_root / f"{pair_id}-{arm.lower()}-checkpoints.sqlite3"
            reuse_preserved_p01_on = recovered and arm == "ON"
            if trial_db.exists() and not reuse_preserved_p01_on:
                trial_db.unlink()
            if checkpoint_db.exists() and not reuse_preserved_p01_on:
                checkpoint_db.unlink()
            if not reuse_preserved_p01_on:
                _backup(pair_template, trial_db)
            if reuse_preserved_p01_on:
                with connect(trial_db) as connection:
                    run_times = connection.execute(
                        "SELECT started_at, ended_at FROM task_runs WHERE run_id = ?", (run_id,),
                    ).fetchone()
                elapsed = 0.0
                if run_times and run_times["started_at"] and run_times["ended_at"]:
                    started = datetime.fromisoformat(str(run_times["started_at"]).replace("Z", "+00:00"))
                    ended = datetime.fromisoformat(str(run_times["ended_at"]).replace("Z", "+00:00"))
                    elapsed = max(0.0, (ended - started).total_seconds())
                result = _redacted_result(trial_db, task_id, run_id, actor_id, elapsed)
                tenant_id = "tenant-b" if actor_id == "support-b" else "tenant-a"
                principal_id = f"principal-{tenant_id[-1]}"
                with connect(pair_template) as connection:
                    grant_before = connection.execute(
                        "SELECT granted_scopes_json, grant_version FROM principal_scope_grants WHERE tenant_id = ? AND principal_id = ?",
                        (tenant_id, principal_id),
                    ).fetchone()
                with connect(trial_db) as connection:
                    grant_after = connection.execute(
                        "SELECT granted_scopes_json, grant_version FROM principal_scope_grants WHERE tenant_id = ? AND principal_id = ?",
                        (tenant_id, principal_id),
                    ).fetchone()
                result["scope_grant_before"] = dict(grant_before) if grant_before else None
                result["scope_grant_after"] = dict(grant_after) if grant_after else None
                result["no_scope_grant_write"] = (
                    result["scope_grant_before"] is not None
                    and result["scope_grant_before"] == result["scope_grant_after"]
                )
                result["execution_error"] = None
                result["attempt_recovery_note"] = "Recovered persisted P01/ON Domain trace after first result-writer import failure; no Provider or MCP calls were repeated."
            else:
                result = _run_trial(
                    db_path=trial_db, checkpoint_path=checkpoint_db,
                    task_id=task_id, run_id=run_id, actor_id=actor_id,
                    s2_mode=pair_id in {"P03", "P04", "P05", "P06", "P08"},
                    memory_enabled=arm == "ON",
                    log_path=output / "trials" / f"{pair_id}-{arm.lower()}.worker.log",
                )
            allowed = list(case["allowed_outcomes"])
            outcome = result["s2_business_outcome"] if pair_id in {"P03", "P04", "P05", "P06", "P08"} else result["s1_gate_decision"]
            normalized_outcome = "NO_ACTION" if outcome in {"NO_S2_DIAGNOSIS", "NO_ACTION"} else outcome
            result["evaluation"] = {
                "arm": arm, "pair_id": pair_id, "allowed_outcomes": allowed,
                "observed_outcome": normalized_outcome,
                "outcome_allowed": normalized_outcome in allowed,
                "selected_memory_count": len(result["selected_memories"]),
                "selected_different_task_memory": any(item.get("source_task_id") != task_id for item in result["selected_memories"]),
                "no_repair_or_deliver": result["business_writes"]["repair_ledgers"] == 0 and result["business_writes"]["deliver_ledgers"] == 0,
                "no_scope_grant_write": result["no_scope_grant_write"],
                "execution_ok": result["execution_error"] is None,
                "recovered_persisted_trial": reuse_preserved_p01_on,
            }
            pair_results[arm] = result
            trials.append({"pair": pair_manifest, **result})
            _write_json(output / "TRACE.json", {
                "schema_version": "m301-trace-v1", "executed_at": datetime.now(timezone.utc).isoformat(),
                "pair_results": [{"pair_id": case_item["pair"]["pair_id"], "arm": case_item["evaluation"]["arm"],
                                  "run_id": case_item["run_id"], "task_id": case_item["task_id"],
                                  "selected_memories": case_item["selected_memories"],
                                  "model_traces": case_item["model_traces"], "mcp_observations": case_item["mcp_observations"],
                                  "outcome": case_item["evaluation"]["observed_outcome"],
                                  "execution_error": case_item["execution_error"]}
                                 for case_item in trials],
            })
            print(json.dumps({"event": "m301_trial", "pair_id": pair_id, "arm": arm,
                              "task_id": task_id, "outcome": normalized_outcome,
                              "selected_memory_count": result["evaluation"]["selected_memory_count"],
                              "execution_error": result["execution_error"]}, ensure_ascii=False), flush=True)
    pairs: list[dict[str, object]] = []
    for case in gold["cases"]:
        items = [item for item in trials if item["pair"]["pair_id"] == case["pair_id"]]
        on = next(item for item in items if item["evaluation"]["arm"] == "ON")
        off = next(item for item in items if item["evaluation"]["arm"] == "OFF")
        pairs.append({
            "pair_id": case["pair_id"], "category": case["category"],
            "ON": on["evaluation"], "OFF": off["evaluation"],
            "token_totals": {
                "ON": _token_total(on["model_traces"]), "OFF": _token_total(off["model_traces"]),
            },
            "mcp_tool_calls": {
                "ON": on["attempt_counts"].get("MCP", 0),
                "OFF": off["attempt_counts"].get("MCP", 0),
            },
        })
    results = {
        "schema_version": "m301-results-v1", "gold_id": gold["gold_id"],
        "executed_at": datetime.now(timezone.utc).isoformat(), "git_head": _git_head(),
        "model_id": os.environ.get(MODEL_NAME), "planned_pairs": 8, "planned_trials": 16,
        "actual_trials": len(trials), "pairs": pairs, "trials": trials,
        "utility_assessment": "UTILITY_NOT_PROVEN",
        "limitations": ["Exploratory sample only; no statistical or generalization claim."],
    }
    _write_json(output / "RESULTS.json", results)
    failures = [item for item in trials if not item["evaluation"]["execution_ok"] or not item["evaluation"]["outcome_allowed"]]
    _write_json(output / "FAILURES.json", failures)
    versions = {name: version(name) for name in (
        "langchain", "langchain-openai", "langgraph", "langgraph-checkpoint-sqlite", "mcp", "pydantic",
    )}
    report = [
        "# M3-01 Memory ON/OFF 真实模型评测", "",
        f"- Gold: `{gold['gold_id']}`; 冻结 8 对 / 16 次，实际 `{len(trials)}` 次。",
        f"- Provider: DeepSeek `{os.environ.get(MODEL_NAME)}`；MCP: 每次 Run 通过 stdio 子进程连接真实本地 MCP Server，Probe 使用 loopback HTTP。",
        f"- Source A S1: Task `{s1_source_info['task_id']}`; Memory `{s1_source_info['memory_id']}` / `{s1_source_info['memory_digest']}`。",
        f"- Source A S2: Task `{s2_source_info['task_id']}`; DiagnosisReceipt `{s2_source_info['diagnosis_receipt_id']}`; Memory `{s2_source_info['memory_id']}` / `{s2_source_info['memory_digest']}`。",
        f"- Runtime dependencies: `{json.dumps(versions, sort_keys=True)}`.",
        f"- Utility: `{results['utility_assessment']}`. Any observed outcome and token/MCP counts remain in `RESULTS.json`; the 8 pairs are exploratory only.",
        "- No trial authorizes or performs REPAIR, DELIVER, Scope grant, or handoff submission.",
        "- Per-run evidence: `TRACE.json`; raw console log is captured by the invocation wrapper.",
        "",
    ]
    (output / "REPORT.md").write_text("\n".join(report), encoding="utf-8")
    return 1 if len(trials) != 16 else 0


def _git_head() -> str | None:
    import subprocess

    result = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, capture_output=True, check=False)
    return result.stdout.strip() if result.returncode == 0 else None


def _token_total(traces: list[dict[str, Any]]) -> int | None:
    if not traces or any(
        not isinstance(trace.get("usage"), dict) or trace["usage"].get("total_tokens") is None
        for trace in traces
    ):
        return None
    return sum(int(trace["usage"]["total_tokens"]) for trace in traces)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-s1-db", required=True)
    parser.add_argument("--evidence-dir", required=True)
    parser.add_argument("--recover-existing-p01-on", action="store_true")
    args = parser.parse_args()
    return run_evaluation(
        args.source_s1_db, args.evidence_dir,
        recover_existing_p01_on=args.recover_existing_p01_on,
    )


if __name__ == "__main__":
    raise SystemExit(main())
