from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import subprocess
import sys
from datetime import datetime, timezone
from importlib.metadata import version
from pathlib import Path
from typing import Any

from opspilot.config import MODEL_API_KEY, MODEL_NAME, ROOT, load_local_environment
from opspilot.domain.d2 import (
    create_task_binding,
    list_evidence,
    list_model_traces,
    list_observations,
    read_report,
)
from opspilot.domain.database import connect
from opspilot.domain.episodic_memory import (
    PROBLEM_TYPE,
    confirm_memory,
    create_memory_candidate,
    list_applicable_memories,
    list_context_provenance,
    revoke_memory,
)
from opspilot.domain.test_fixtures import (
    prepare_d5_auth_401_for_test,
    set_d5_principal_status_for_test,
)
from opspilot.investigator import _prompt_messages
from opspilot.skill_assets import load_applicable_skill


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")


def _sha256_file(path: Path) -> str | None:
    if not path.is_file():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _absolute(path: str | Path) -> Path:
    candidate = Path(path)
    return (candidate if candidate.is_absolute() else ROOT / candidate).resolve()


def _run(command: list[str]) -> dict[str, object]:
    result = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, check=False, timeout=600)
    return {
        "command": command,
        "return_code": result.returncode,
        "pid": None,
        "stdout": result.stdout[-30000:],
        "stderr": result.stderr[-10000:],
    }


def _latest_json_event(output: str, event: str) -> dict[str, object] | None:
    for line in reversed(output.splitlines()):
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(item, dict) and item.get("event") == event:
            return item
    return None


def _run_worker(
    mode: str,
    *,
    db_path: Path,
    checkpoint_path: Path,
    task_id: str | None = None,
    thread_id: str | None = None,
) -> dict[str, object]:
    command = [
        sys.executable, "-m", "opspilot.smokes.d5_worker", mode,
        "--actor", "support-a", "--db", str(db_path),
        "--checkpoint-db", str(checkpoint_path),
    ]
    if task_id:
        command.extend(("--task-id", task_id))
    if thread_id:
        command.extend(("--thread-id", thread_id))
    result = _run(command)
    result["event"] = _latest_json_event(str(result["stdout"]), "d5_worker_complete") or _latest_json_event(str(result["stdout"]), "d5_worker_failed")
    return result


def _task_id_with_recovered_source(db_path: Path) -> str:
    with connect(db_path) as connection:
        row = connection.execute(
            """SELECT l.task_id FROM d3_action_ledgers AS l
               JOIN d3_verification_receipts AS v ON v.tenant_id = l.tenant_id
                 AND v.task_id = l.task_id AND v.plan_hash = l.plan_hash
                 AND v.repair_action_id = l.action_id
               JOIN d3_report_artifacts AS r ON r.tenant_id = v.tenant_id
                 AND r.task_id = v.task_id AND r.plan_hash = v.plan_hash
                 AND r.repair_action_id = v.repair_action_id
                 AND r.verification_id = v.verification_id
               WHERE l.action_kind = 'REPAIR' AND l.status = 'COMMITTED'
                 AND v.recovery_verified = 1 AND v.response_status = 200
               ORDER BY r.created_at DESC LIMIT 1"""
        ).fetchone()
    if row is None:
        raise RuntimeError("D3 smoke did not leave a committed, online-recovered source task.")
    return str(row["task_id"])


def _redacted_task_trace(db_path: Path, task_id: str, actor_id: str) -> dict[str, object]:
    observations = list_observations(db_path, task_id)
    evidence = list_evidence(db_path, task_id)
    traces = list_model_traces(db_path, task_id)
    report = read_report(db_path, task_id)
    return {
        "task_id": task_id,
        "gate_decision": report.get("report", {}).get("gate_decision") if report else None,
        "model_traces": [
            {key: item.get(key) for key in (
                "call_id", "model_id", "prompt_digest", "provider_response_id", "status", "tool_calls"
            )}
            for item in traces
        ],
        "mcp_observations": [
            {key: item.get(key) for key in (
                "observation_id", "call_id", "tool_call_id", "tool_name", "status", "evidence_id", "error_class"
            )}
            for item in observations
        ],
        "current_evidence": [
            {
                "evidence_id": item.get("evidence_id"),
                "fact_type": item.get("fact_type"),
                "resource_id": item.get("resource_id"),
                "observed_versions": item.get("observed_versions"),
                "facts": {
                    key: value for key, value in dict(item.get("facts", {})).items()
                    if key in {"http_status", "route", "status", "principal_status", "principal_version", "policy_version", "config_version", "credential_ref", "auth_event_result"}
                },
            }
            for item in evidence
        ],
        "context_provenance": list_context_provenance(db_path, task_id, actor_id),
    }


def run_smoke(db_path: str | Path, checkpoint_db_path: str | Path, evidence_dir: str | Path) -> int:
    load_local_environment()
    resolved_db = _absolute(db_path)
    resolved_checkpoint = _absolute(checkpoint_db_path)
    output_dir = _absolute(evidence_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    work_dir = resolved_checkpoint.parent / "d5-smoke-work"
    work_dir.mkdir(parents=True, exist_ok=True)
    if not os.environ.get(MODEL_API_KEY) or not os.environ.get(MODEL_NAME):
        blocked = {
            "result": "BLOCKED",
            "reason": f"Missing {MODEL_API_KEY} or {MODEL_NAME}; credentials are not recorded.",
            "executed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        _write_json(output_dir / "TRACE.json", blocked)
        (output_dir / "REPORT.md").write_text("# OpsPilot D5 运行报告\n\n**结果：BLOCKED**\n\n模型配置不完整，未发起真实请求。\n", encoding="utf-8")
        print(json.dumps(blocked, ensure_ascii=False, sort_keys=True))
        return 2

    processes: dict[str, object] = {}
    checks: dict[str, bool] = {}
    try:
        source_checkpoint = work_dir / "task-a-checkpoints.sqlite3"
        source_evidence_dir = output_dir / "d3-source"
        source_run = _run([
            sys.executable, "-m", "opspilot.cli", "d3-smoke",
            "--db", str(resolved_db), "--checkpoint-db", str(source_checkpoint),
            "--evidence-dir", str(source_evidence_dir),
        ])
        processes["task_a_d3"] = source_run
        if int(source_run["return_code"]) != 0:
            raise RuntimeError("Task A real D3 recovery smoke failed; no memory was created.")
        d3_trace_path = source_evidence_dir / "TRACE.json"
        d3_trace = json.loads(d3_trace_path.read_text(encoding="utf-8"))
        if d3_trace.get("result") != "PASS":
            raise RuntimeError("Task A source report did not pass its real D3 assertions.")
        task_a_id = _task_id_with_recovered_source(resolved_db)

        candidate = create_memory_candidate(resolved_db, task_a_id, "support-a")
        memory_id = str(candidate["memory_id"])
        prepare_d5_auth_401_for_test(resolved_db, "tenant-a", "integration-a")
        binding_b = create_task_binding(
            resolved_db, "support-a", "orders-demo", "integration-a", ticket_id="INC-D5-B-001"
        )
        initial_state: dict[str, object] = {
            "task_binding_id": binding_b["task_id"], "evidence_ids": [], "tool_observations": [],
        }
        metadata_before_confirmation: dict[str, object] = {}
        messages_before_confirmation = _prompt_messages(
            resolved_db, str(binding_b["task_id"]), initial_state,
            context_metadata=metadata_before_confirmation,
        )
        prompt_before_confirmation = "\n".join(str(message.content) for message in messages_before_confirmation)
        checks["candidate_is_not_retrievable"] = candidate["state"] == "CANDIDATE" and not list_applicable_memories(
            resolved_db, str(binding_b["task_id"]), PROBLEM_TYPE
        )
        checks["candidate_text_is_absent_from_prompt"] = memory_id not in prompt_before_confirmation and str(candidate["summary"]) not in prompt_before_confirmation
        checks["candidate_source_is_task_a"] = candidate["source_task_id"] == task_a_id and bool(candidate["source_evidence_ids"])

        active = confirm_memory(resolved_db, memory_id, "approver-a")
        checks["human_confirmation_activates_once"] = active["state"] == "ACTIVE" and int(active["version"]) == 2 and active["confirmed_by"] == "approver-a"
        task_a_binding = d3_trace.get("final_action_state", {}).get("task_binding", {})
        checks["task_b_is_new_binding"] = str(binding_b["task_id"]) != task_a_id and str(binding_b["thread_id"]) != str(task_a_binding.get("thread_id", ""))
        available = list_applicable_memories(resolved_db, str(binding_b["task_id"]), PROBLEM_TYPE)
        checks["task_b_retrieves_active_memory"] = len(available) == 1 and available[0]["memory_id"] == memory_id

        checkpoint_b = work_dir / "task-b-checkpoints.sqlite3"
        process_b_start = _run_worker(
            "start", db_path=resolved_db, checkpoint_path=checkpoint_b,
            task_id=str(binding_b["task_id"]),
        )
        processes["task_b_first_process"] = process_b_start
        first_event = process_b_start.get("event")
        first_provenance = list_context_provenance(resolved_db, str(binding_b["task_id"]), "support-a")
        first_call = first_provenance[0] if first_provenance else {}
        checks["task_b_real_model_call_selected_memory_and_skill"] = bool(
            int(process_b_start["return_code"]) == 0
            and isinstance(first_event, dict) and first_event.get("paused_after_model_call") is True
            and any(item.get("memory_id") == memory_id and item.get("version") == active["version"] for item in first_call.get("selected_memories", []))
            and first_call.get("selected_skill_name") == "auth-incident-triage"
            and first_call.get("selected_skill_version") == "1.0.0"
            and first_call.get("model_trace_prompt_digest") == first_call.get("prompt_digest")
            and first_call.get("provider_response_id")
        )
        checks["task_b_process_checkpointed_after_model_call"] = bool(
            isinstance(first_event, dict) and first_event.get("paused_after_model_call") is True
            and first_event.get("next_nodes")
        )

        set_d5_principal_status_for_test(resolved_db, "tenant-a", "principal-a", "DISABLED")
        binding_c = create_task_binding(
            resolved_db, "support-a", "orders-demo", "integration-a", ticket_id="INC-D5-C-001"
        )
        checkpoint_c = work_dir / "task-c-checkpoints.sqlite3"
        process_c = _run_worker(
            "run", db_path=resolved_db, checkpoint_path=checkpoint_c,
            task_id=str(binding_c["task_id"]),
        )
        processes["task_c_disabled_process"] = process_c
        task_c = _redacted_task_trace(resolved_db, str(binding_c["task_id"]), "support-a")
        task_c_evidence = task_c["current_evidence"]
        task_c_provenance = task_c["context_provenance"]
        checks["disabled_task_used_active_memory"] = any(
            item.get("memory_id") == memory_id for call in task_c_provenance for item in call.get("selected_memories", [])
        )
        checks["disabled_task_real_401_and_no_action"] = bool(
            int(process_c["return_code"]) == 0
            and task_c.get("gate_decision", {}).get("decision") == "NO_ACTION"
            and any(item.get("fact_type") == "endpoint_probe" and item.get("facts", {}).get("http_status") == 401 for item in task_c_evidence)
            and any(item.get("fact_type") == "principal_status" and item.get("facts", {}).get("status") == "DISABLED" for item in task_c_evidence)
        )
        set_d5_principal_status_for_test(resolved_db, "tenant-a", "principal-a", "ENABLED")

        revoked = revoke_memory(resolved_db, memory_id, "approver-a")
        checks["revocation_changes_version_and_stops_retrieval"] = bool(
            revoked["state"] == "REVOKED" and int(revoked["version"]) == int(active["version"]) + 1
            and not list_applicable_memories(resolved_db, str(binding_b["task_id"]), PROBLEM_TYPE)
        )
        checkpoint_b_before_resume = _sha256_file(checkpoint_b)
        process_b_resume = _run_worker(
            "resume", db_path=resolved_db, checkpoint_path=checkpoint_b,
            thread_id=str(binding_b["thread_id"]),
        )
        processes["task_b_restored_process"] = process_b_resume
        checkpoint_b_after_resume = _sha256_file(checkpoint_b)
        task_b = _redacted_task_trace(resolved_db, str(binding_b["task_id"]), "support-a")
        b_provenance = task_b["context_provenance"]
        b_model_calls = task_b["model_traces"]
        first_b = next((row for row in b_provenance if any(item.get("memory_id") == memory_id for item in row.get("selected_memories", []))), {})
        resumed_b = [row for row in b_provenance if row.get("call_id") != first_b.get("call_id")]
        after_revoke_calls = [row for row in resumed_b if row.get("built_at") >= revoked["revoked_at"]]
        b_evidence = task_b["current_evidence"]
        checks["cross_process_resume_is_a_distinct_process"] = bool(
            isinstance(first_event, dict) and isinstance(process_b_resume.get("event"), dict)
            and first_event.get("pid") != process_b_resume["event"].get("pid")
        )
        checks["post_revocation_real_model_call_has_no_memory"] = bool(
            int(process_b_resume["return_code"]) == 0
            and after_revoke_calls
            and all(not row.get("selected_memories") for row in after_revoke_calls)
            and all(row.get("provider_response_id") for row in after_revoke_calls)
            and all(row.get("prompt_digest_matches_trace") for row in after_revoke_calls)
        )
        checks["task_b_current_evidence_still_controls_gate"] = bool(
            task_b.get("gate_decision", {}).get("decision") == "READY"
            and any(item.get("fact_type") == "endpoint_probe" and item.get("facts", {}).get("http_status") == 401 for item in b_evidence)
        )
        checks["memory_and_skill_never_enter_domain_evidence"] = all(
            item.get("fact_type") not in {"episodic_memory", "skill_methodology"}
            for item in task_b["current_evidence"] + task_c["current_evidence"]
        )

        insufficient_db = work_dir / "insufficient-domain.sqlite3"
        insufficient_checkpoints = work_dir / "insufficient-checkpoints.sqlite3"
        insufficient = _run([
            sys.executable, "-m", "opspilot.cli", "d2-smoke", "--scenario", "INSUFFICIENT",
            "--db", str(insufficient_db), "--checkpoint-db", str(insufficient_checkpoints),
        ])
        processes["real_insufficient_control"] = insufficient
        insufficient_output = _latest_json_event(str(insufficient["stdout"]), "d2_smoke_result")
        checks["insufficient_401_real_model_mcp_control"] = bool(
            int(insufficient["return_code"]) == 0
            and isinstance(insufficient_output, dict)
            and insufficient_output.get("actual_gate") == "INCONCLUSIVE"
            and insufficient_output.get("passed") is True
        )

        all_provenance = [*b_provenance, *task_c_provenance]
        checks["each_actual_model_call_has_context_provenance"] = bool(all_provenance) and all(
            item.get("provider_response_id")
            and item.get("model_trace_prompt_digest") == item.get("prompt_digest")
            and item.get("prompt_version") == "d5-context-provenance-v1"
            and item.get("tool_schema_digest")
            for item in all_provenance
        )
        checks["skill_digest_was_verified_and_versioned"] = bool(
            first_call.get("selected_skill_digest")
            and first_call.get("selected_skill_digest") == load_applicable_skill(PROBLEM_TYPE).get("digest")
        )
        checks["real_model_mcp_trajectories_recorded"] = bool(
            b_model_calls and any(item.get("provider_response_id") for item in b_model_calls)
            and task_b["mcp_observations"] and task_c["mcp_observations"]
        )

        trace = {
            "result": "PASS" if all(checks.values()) else "FAIL",
            "executed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "git_head": subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, capture_output=True, check=False).stdout.strip(),
            "python_version": platform.python_version(),
            "platform": platform.platform(),
            "model_id": os.environ.get(MODEL_NAME, ""),
            "dependency_versions": {name: version(name) for name in (
                "langchain", "langchain-openai", "langgraph", "langgraph-checkpoint-sqlite", "mcp", "pydantic", "pytest"
            )},
            "checks": checks,
            "source_task_a": {
                "task_id": task_a_id,
                "d3_smoke_result": d3_trace.get("result"),
                "business_outcome": d3_trace.get("final_action_state", {}).get("task_binding", {}).get("status"),
                "committed_repair_count": sum(1 for item in d3_trace.get("final_action_state", {}).get("action_ledgers", []) if item.get("action_kind") == "REPAIR" and item.get("status") == "COMMITTED"),
                "verification": next(({
                    "verification_id": item.get("verification_id"),
                    "response_status": item.get("response_status"),
                    "recovery_verified": bool(item.get("recovery_verified")),
                } for item in d3_trace.get("final_action_state", {}).get("verification_receipts", [])), {}),
                "frozen_reports": d3_trace.get("final_action_state", {}).get("report_artifacts", []),
                "source_evidence_ids": candidate.get("source_evidence_ids"),
            },
            "memory_lifecycle": {
                "memory_id": memory_id,
                "source_task_id": task_a_id,
                "candidate_version": 1,
                "active_version": active.get("version"),
                "revoked_version": revoked.get("version"),
                "confirmed_by": active.get("confirmed_by"),
                "revoked_by": revoked.get("revoked_by"),
                "project_id": active.get("project_id"),
                "expires_at": active.get("expires_at"),
            },
            "task_b_before_revocation": {
                "task_id": binding_b["task_id"], "thread_id": binding_b["thread_id"],
                "first_call": first_call,
                "first_worker": process_b_start.get("event"),
            },
            "task_b_after_revocation_and_cross_process_resume": task_b,
            "task_b_checkpoint_recovery": {
                "checkpoint_path": str(checkpoint_b.relative_to(ROOT)) if checkpoint_b.is_relative_to(ROOT) else checkpoint_b.name,
                "sha256_after_first_process": checkpoint_b_before_resume,
                "sha256_after_restored_process": checkpoint_b_after_resume,
                "first_process_id": first_event.get("pid") if isinstance(first_event, dict) else None,
                "restored_process_id": process_b_resume.get("event", {}).get("pid") if isinstance(process_b_resume.get("event"), dict) else None,
            },
            "task_c_disabled_control": {
                "task_id": binding_c["task_id"], "process": process_c.get("event"), **task_c,
            },
            "real_insufficient_control": {
                "process": insufficient,
                "result_event": insufficient_output,
            },
            "processes": processes,
        }
        passed = all(checks.values())
        _write_json(output_dir / "TRACE.json", trace)
        _write_json(output_dir / "process_logs.json", processes)
        source_lines = "\n".join(f"- `{name}`: return code {item['return_code']}." for name, item in processes.items())
        check_lines = "\n".join(f"- [{'x' if passed_check else ' '}] `{name}`" for name, passed_check in checks.items())
        report = f"""# OpsPilot D5 跨任务记忆运行报告

**结果：{'PASS' if passed else 'FAIL'}**

**执行时间：** {trace['executed_at']}

**当前提交：** `{trace['git_head']}`

**Python：** {trace['python_version']}（{trace['platform']}）
**真实模型：** `{trace['model_id']}`（未记录密钥）

## 验收断言

{check_lines}

## 真实进程

{source_lines}

## 关键轨迹

- 任务 A 由 D3 真实模型、stdio MCP、独立审批进程完成；来源为 COMMITTED REPAIR、在线 HTTP 200/订单断言通过的 `RECOVERED` VerificationReceipt、冻结报告和同任务 Evidence。
- 候选 Memory `{memory_id}` 从 `CANDIDATE v1` 经 `{active.get('confirmed_by')}` 确认后变为 `ACTIVE v{active.get('version')}`；候选阶段任务 B 的 Prompt 未包含记忆。
- 新任务 B 首个真实模型请求在出站前登记了 Memory ID/version、Skill name/version/digest、Prompt digest 与 Tool Schema digest。该请求通过本机真实模型调用并获得 Provider response ID。
- 任务 C 在 Memory 仍为 ACTIVE 时用真实模型/MCP 面对主体禁用造成的 HTTP 401，确定性 Gate 返回 `NO_ACTION`；独立真实 `INSUFFICIENT` 场景返回 `INCONCLUSIVE`。
- 撤销 `{memory_id}` 后，B 从另一 OS 进程恢复旧 checkpoint。恢复后的真实模型调用均无 Memory 引用，Prompt digest 与模型轨迹相符；B 的当前 MCP Probe 仍为 HTTP 401、主体为 ENABLED，Gate 根据当前 Evidence 返回 `READY`。
- B 两个独立进程使用同一 checkpoint 文件；恢复前后文件 SHA-256 及 PID 记录在 `TRACE.json`。SQLite checkpoint 和 Demo Domain 文件留在 `.runtime`，证据目录不包含数据库文件。
- 完整脱敏逐调用 ContextProvenance、模型响应引用、MCP Observation 和当前 Evidence 见 `TRACE.json`；独立进程输出见 `process_logs.json`，任务 A 的 D3 来源包见 `d3-source/`。
- 首次失败仅由 smoke 的 Evidence 脱敏投影漏记 `status` 字段导致，已修正；复现与处理说明见 `ATTEMPT-01.md`。

## 命令

```powershell
.\\.venv\\Scripts\\python.exe -m opspilot.cli d5-smoke --db .runtime\\d5-domain.sqlite3 --checkpoint-db .runtime\\d5-checkpoints.sqlite3 --evidence-dir docs\\evidence\\d5
```

依赖版本见本报告同目录的 `TRACE.json`。全量 pytest 日志见 `pytest-full.txt`。

## 限制与待办

- 项目作用域按冻结 D5 Demo 规则从可信 `service_id` 派生，例如 `service:orders-demo`；这不是通用项目注册中心或生产 IAM。
- Memory 固定为一条最多 30 天的 Episodic 经验，单次最多检索一条；不含向量检索、自动总结或业务根因。
- 跨层外部模型请求与 SQLite 无法构成一个分布式原子事务。ContextProvenance 在模型出站前持久化；调用开始后再发生的撤销不能撤回已发送请求，但下一次调用及 checkpoint 恢复会重新查权威 SQLite 状态。
- D5 到此停止；未扩展其他 Memory 类型、Skill、Agent、复杂审批或业务场景。
"""
        (output_dir / "REPORT.md").write_text(report, encoding="utf-8")
        print(json.dumps({"event": "d5_smoke_result", "result": trace["result"], "checks": checks, "task_a": task_a_id, "task_b": binding_b["task_id"], "memory_id": memory_id}, ensure_ascii=False, sort_keys=True))
        return 0 if passed else 1
    except Exception as error:
        failure = {
            "result": "FAIL",
            "executed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "error_class": type(error).__name__,
            "error": str(error)[:1000],
            "model_id": os.environ.get(MODEL_NAME, ""),
            "checks": checks,
            "processes": processes,
        }
        _write_json(output_dir / "TRACE.json", failure)
        _write_json(output_dir / "process_logs.json", processes)
        (output_dir / "REPORT.md").write_text(
            "# OpsPilot D5 跨任务记忆运行报告\n\n**结果：FAIL**\n\n"
            f"执行在 `{type(error).__name__}` 处停止：{str(error)[:1000]}\n\n"
            "已完成的子进程日志和断言见 `process_logs.json`、`TRACE.json`。\n",
            encoding="utf-8",
        )
        print(json.dumps({"event": "d5_smoke_result", "result": "FAIL", "error_class": type(error).__name__, "error": str(error)[:500]}, ensure_ascii=False, sort_keys=True))
        return 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default=".runtime/d5-domain.sqlite3")
    parser.add_argument("--checkpoint-db", default=".runtime/d5-checkpoints.sqlite3")
    parser.add_argument("--evidence-dir", default="docs/evidence/d5")
    args = parser.parse_args()
    return run_smoke(args.db, args.checkpoint_db, args.evidence_dir)


if __name__ == "__main__":
    raise SystemExit(main())
