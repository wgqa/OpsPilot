from __future__ import annotations

import json
import os
import platform
import subprocess
import sys
from datetime import datetime, timezone
from importlib.metadata import version
from pathlib import Path
from typing import Any

from opspilot.config import MODEL_API_KEY, MODEL_NAME, ROOT, database_path, load_local_environment
from opspilot.domain.d2 import list_evidence, list_model_traces, list_observations
from opspilot.domain.database import get_integration_info, reset_fixture
from opspilot.domain.d3 import get_task_ticket_entries


def _redact(value: str) -> str:
    secret = os.environ.get(MODEL_API_KEY, "")
    if secret:
        value = value.replace(secret, "[REDACTED]")
    return value.replace("Bearer ", "Bearer [REDACTED]")


def _run_child(arguments: list[str]) -> dict[str, Any]:
    command = [sys.executable, "-m", "opspilot.cli", *arguments]
    completed = subprocess.run(
        command,
        cwd=ROOT,
        text=True,
        capture_output=True,
        timeout=360,
        check=False,
    )
    events: list[dict[str, Any]] = []
    for line in completed.stdout.splitlines():
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict) and isinstance(value.get("event"), str):
            events.append(value)
    return {
        "command": command,
        "return_code": completed.returncode,
        "events": events,
        "stdout_unparsed": _redact(completed.stdout) if not events else "",
        "stderr": _redact(completed.stderr),
        "pid": events[-1].get("process_id") if events else None,
    }


def _latest_event(process: dict[str, Any], event_name: str) -> dict[str, Any] | None:
    for event in reversed(process.get("events", [])):
        if event.get("event") == event_name:
            return event
    return None


def _write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")


def _build_report(trace: dict[str, Any], passed: bool, reason: str | None = None) -> str:
    start = trace.get("processes", {}).get("start", {})
    approve = trace.get("processes", {}).get("approval_resume", {})
    start_event = _latest_event(start, "d3_plan_waiting_approval") or _latest_event(start, "d3_investigation_complete") or {}
    completion = _latest_event(approve, "d3_approval_process_completed") or {}
    state = completion.get("action_state", {})
    repair = next((item for item in state.get("action_ledgers", []) if item.get("action_kind") == "REPAIR"), {})
    deliver = next((item for item in state.get("action_ledgers", []) if item.get("action_kind") == "DELIVER"), {})
    receipt = next(iter(state.get("verification_receipts", [])), {})
    report = next(iter(state.get("report_artifacts", [])), {})
    delivery = next(iter(state.get("delivery_records", [])), {})
    intents = state.get("action_intents", [])
    intent_text = "; ".join(
        f"{item.get('action_kind')}={item.get('action_id')} / key={item.get('idempotency_key')} / digest={item.get('request_digest')}"
        for item in intents
    )
    permissions = {item.get("action_kind"): item.get("state") for item in state.get("permissions", [])}
    entry_count = len(state.get("ticket_entries", []))
    initial = trace.get("initial_401_evidence", {})
    before = trace.get("before_approval", {})
    online_assertions = receipt.get("business_assertions", {})
    model_sequence = " → ".join(
        str(call.get("name"))
        for model_trace in trace.get("model_traces", [])
        for call in model_trace.get("tool_calls", [])
        if isinstance(call, dict)
    )
    mcp_sequence = " → ".join(str(item.get("tool_name")) for item in trace.get("mcp_observations", []))
    return f"""# OpsPilot D3 运行报告

**结果：** {'PASS' if passed else 'FAIL'}

**运行时间：** {trace.get('executed_at')}

**主提交：** {trace.get('git_head', '待提交后回填')}

**范围：** D3 E01 真实模型 / MCP / LangGraph HITL / REPAIR / 在线验证 / 冻结报告 / DELIVER

## 环境与运行命令

- Python：`{trace.get('python_version')}`（{trace.get('platform')}）
- 模型：`{trace.get('model_id')}`（密钥不记录）
- 依赖：`{json.dumps(trace.get('dependency_versions', {}), ensure_ascii=False, sort_keys=True)}`
- 复现命令：`{trace.get('smoke_command')}`
- 初始调查进程 PID：`{start.get('pid')}`；独立审批与恢复进程 PID：`{approve.get('pid')}`
- 初始进程命令：`{' '.join(start.get('command', []))}`
- 审批恢复命令：`{' '.join(approve.get('command', []))}`
- 真实模型 Function Calling 选择：`{model_sequence}`；对应 MCP Client/Server 调用：`{mcp_sequence}`（完整 Observation/Evidence 在 TRACE.json）。

## 运行结果

- 初始真实业务 Probe：HTTP `{initial.get('http_status')}`，请求 `{initial.get('request_id')}`，认证事件 `{initial.get('auth_event_id')}`；Gate=`{start_event.get('gate_decision', {}).get('decision')}`。
- 审批前状态：`{before.get('credential_ref')}` / config version `{before.get('config_version')}`，工单处置条目 `{before.get('ticket_resolution_entry_count')}`；受限写入为零。
- LangGraph 在 Plan `{start_event.get('plan_hash')}` 处等待人工审批；审批人为 `{completion.get('approval_id') and next((item.get('approver_id') for item in state.get('approvals', [])), '未知')}`，决定 `{completion.get('approval_decision')}`。
- 两种独立授权消费状态：`{permissions}`。持久 ActionIntent：`{intent_text}`。
- REPAIR ledger：`{repair.get('ledger_id')}`，状态 `{repair.get('status')}`，配置版本 `{repair.get('before_version')} → {repair.get('after_version')}`。
- 在线验证：HTTP `{receipt.get('response_status')}`，`order_id={online_assertions.get('response_body', {}).get('order_id')}`，`status={online_assertions.get('response_body', {}).get('status')}`，同 service/integration/principal/route 断言 `{all(online_assertions.get(key) is True for key in ('same_tenant', 'same_service', 'same_integration', 'same_principal', 'same_business_route', 'expected_post_repair_versions'))}`；request `{online_assertions.get('request_id')}` / auth event `{online_assertions.get('auth_event_id')}`；VerificationReceipt=`{receipt.get('verification_id')}`。
- 冻结报告：`{report.get('report_ref')}`，SHA-256=`{report.get('content_digest')}`。
- 独立 DELIVER ledger：`{deliver.get('ledger_id')}`，状态 `{deliver.get('status')}`；delivery receipt=`{delivery.get('delivery_receipt', {})}`；唯一工单处置条目数=`{entry_count}`。
- 最终业务状态：`{completion.get('business_outcome')}`；任务状态=`{state.get('task_binding', {}).get('status')}`。
{f'- 失败原因：{reason}' if reason else ''}

完整脱敏轨迹见 [`TRACE.json`](TRACE.json)，两个 OS 子进程输出见 [`process_logs.json`](process_logs.json)。

## 已知限制

本轮验证的是本地 SQLite Demo Domain 与固定订单路由；跨进程 HITL 由两个独立 CLI 进程完成。D4 的崩溃窗口/并发响应丢失故障矩阵不在本轮验收范围，不能据此声称生产级 IAM 或分布式 exactly-once。
"""


def run_smoke(db_path: str | Path, checkpoint_db_path: str | Path, evidence_dir: str | Path) -> int:
    load_local_environment()
    output_dir = Path(evidence_dir)
    if not output_dir.is_absolute():
        output_dir = ROOT / output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    prior_trace_path = output_dir / "TRACE.json"
    if prior_trace_path.exists():
        try:
            prior = json.loads(prior_trace_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            prior = {}
        if prior.get("result") not in {None, "PASS"}:
            _write_json(output_dir / "TRACE-attempt-01.json", prior)
            prior_logs_path = output_dir / "process_logs.json"
            if prior_logs_path.exists():
                _write_json(output_dir / "process_logs-attempt-01.json", json.loads(prior_logs_path.read_text(encoding="utf-8")))
    resolved_db = database_path(str(db_path))
    checkpoint_path = Path(checkpoint_db_path)
    if not checkpoint_path.is_absolute():
        checkpoint_path = ROOT / checkpoint_path
    if not os.environ.get(MODEL_API_KEY) or not os.environ.get(MODEL_NAME):
        blocked = {
            "result": "BLOCKED",
            "reason": f"Missing {MODEL_API_KEY} or {MODEL_NAME}; no credentials are emitted.",
            "executed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        _write_json(output_dir / "TRACE.json", blocked)
        (output_dir / "REPORT.md").write_text("# OpsPilot D3 运行报告\n\n**结果：BLOCKED**\n\n" + blocked["reason"] + "\n", encoding="utf-8")
        print(json.dumps(blocked, ensure_ascii=False, sort_keys=True))
        return 2

    reset_fixture(resolved_db, "S1_POS")
    start = _run_child([
        "d3-start", "--actor", "support-a", "--executor", "executor-a",
        "--db", str(resolved_db), "--checkpoint-db", str(checkpoint_path),
    ])
    start_event = _latest_event(start, "d3_plan_waiting_approval")
    start_fallback = _latest_event(start, "d3_investigation_complete")
    first = start_event or start_fallback or {}
    task_binding = first.get("task_binding", {}) if isinstance(first.get("task_binding"), dict) else {}
    plan_hash = first.get("plan_hash")
    thread_id = task_binding.get("thread_id")
    task_id = str(task_binding.get("task_id", ""))
    before_approval_integration = get_integration_info(resolved_db, "tenant-a", "integration-a")
    before_approval_ticket_entries = get_task_ticket_entries(resolved_db, task_id, "support-a") if task_id else []
    approval_resume: dict[str, Any] = {"command": [], "return_code": None, "events": [], "pid": None}
    if start["return_code"] == 0 and start_event is not None and plan_hash and thread_id:
        approval_resume = _run_child([
            "d3-approve", "--actor", "approver-a", "--thread-id", str(thread_id),
            "--plan-hash", str(plan_hash), "--decision", "APPROVED", "--executor", "executor-a",
            "--db", str(resolved_db), "--checkpoint-db", str(checkpoint_path),
        ])
    completion = _latest_event(approval_resume, "d3_approval_process_completed")
    state = completion.get("action_state", {}) if completion else {}
    repair = next((item for item in state.get("action_ledgers", []) if item.get("action_kind") == "REPAIR"), {})
    deliver = next((item for item in state.get("action_ledgers", []) if item.get("action_kind") == "DELIVER"), {})
    receipt = next(iter(state.get("verification_receipts", [])), {})
    report_artifact = next(iter(state.get("report_artifacts", [])), {})
    delivery = next(iter(state.get("delivery_records", [])), {})
    integration = get_integration_info(resolved_db, "tenant-a", "integration-a")
    evidence = list_evidence(resolved_db, task_id) if task_id else []
    initial_401 = next((item for item in evidence if item.get("fact_type") == "endpoint_probe" and item.get("facts", {}).get("http_status") == 401), None)
    traces = list_model_traces(resolved_db, task_id) if task_id else []
    observations = list_observations(resolved_db, task_id) if task_id else []
    initial_facts = initial_401.get("facts", {}) if initial_401 else {}
    online = receipt.get("business_assertions", {}).get("response_body", {}) if receipt else {}
    gate = first.get("gate_decision", {})
    checks = {
        "real_initial_401_evidence": bool(initial_401 and initial_facts.get("request_id") and initial_facts.get("auth_event_id")),
        "no_business_write_before_approval": int(before_approval_integration["config_version"]) == 7 and before_approval_integration["credential_ref"] == "cred-v1" and len(before_approval_ticket_entries) == 0,
        "gate_ready_and_plan_hash": gate.get("decision") == "READY" and bool(plan_hash),
        "graph_checkpoint_stores_references_only": bool(start_event.get("graph_only_plan_reference") and "canonical_request_json" not in completion.get("graph_signals", {})),
        "processes_are_distinct": bool(start.get("pid") and approval_resume.get("pid") and start["pid"] != approval_resume["pid"]),
        "independent_approver": completion is not None and completion.get("approval_decision") == "APPROVED" and any(item.get("approver_id") == "approver-a" for item in state.get("approvals", [])),
        "repair_committed_once": repair.get("status") == "COMMITTED" and int(integration["config_version"]) == 8 and integration["credential_ref"] == "cred-v2",
        "same_identity_online_200": bool(receipt.get("recovery_verified") and receipt.get("response_status") == 200 and online.get("order_id") == "demo-order" and online.get("status") == "CONFIRMED"),
        "frozen_report_before_delivery": bool(report_artifact.get("report_ref") and delivery.get("delivery_receipt", {}).get("report_ref") == report_artifact.get("report_ref")),
        "independent_deliver_committed_once": deliver.get("status") == "COMMITTED" and len(state.get("ticket_entries", [])) == 1 and len(state.get("delivery_records", [])) == 1,
        "both_action_intents_persisted": {item.get("action_kind") for item in state.get("action_intents", [])} == {"REPAIR", "DELIVER"},
        "business_outcome_recovered": bool(completion and completion.get("business_outcome") == "RECOVERED" and receipt.get("recovery_verified") is True),
        "model_and_mcp_trajectory_present": bool(traces and observations and any(item.get("tool_calls") for item in traces)),
    }
    passed = all(checks.values()) and start["return_code"] == 0 and approval_resume["return_code"] == 0
    trace = {
        "result": "PASS" if passed else "FAIL",
        "executed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "git_head": subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, capture_output=True, check=False).stdout.strip(),
        "python_version": platform.python_version(),
        "platform": platform.platform(),
        "model_id": os.environ.get(MODEL_NAME, ""),
        "dependency_versions": {name: version(name) for name in ("langchain", "langchain-openai", "langgraph", "langgraph-checkpoint-sqlite", "mcp", "pydantic")},
        "smoke_command": ".venv\\Scripts\\python.exe -m opspilot.cli d3-smoke --db .runtime\\d3-domain.sqlite3 --checkpoint-db .runtime\\d3-checkpoints.sqlite3",
        "checks": checks,
        "initial_401_evidence": {
            "evidence_id": initial_401.get("evidence_id") if initial_401 else None,
            "http_status": initial_facts.get("http_status"),
            "request_id": initial_facts.get("request_id"),
            "auth_event_id": initial_facts.get("auth_event_id"),
            "auth_event_result": initial_facts.get("auth_event_result"),
            "route": initial_facts.get("route"),
        },
        "before_approval": {
            "credential_ref": before_approval_integration["credential_ref"],
            "config_version": before_approval_integration["config_version"],
            "ticket_resolution_entry_count": len(before_approval_ticket_entries),
        },
        "processes": {"start": start, "approval_resume": approval_resume},
        "model_traces": traces,
        "mcp_observations": observations,
        "evidence": evidence,
        "final_action_state": state,
        "final_integration": {key: integration.get(key) for key in ("tenant_id", "integration_id", "principal_id", "credential_ref", "config_version", "principal_status", "principal_version")},
    }
    _write_json(output_dir / "TRACE.json", trace)
    process_logs = {"start": start, "approval_resume": approval_resume}
    _write_json(output_dir / "process_logs.json", process_logs)
    reason = None if passed else ", ".join(key for key, value in checks.items() if not value)
    report_markdown = _build_report(trace, passed, reason)
    (output_dir / "REPORT.md").write_text(report_markdown, encoding="utf-8")
    print(json.dumps({"event": "d3_smoke_result", "result": trace["result"], "checks": checks, "task_id": task_id, "plan_hash": plan_hash, "repair_ledger_id": repair.get("ledger_id"), "verification_id": receipt.get("verification_id"), "report_ref": report_artifact.get("report_ref"), "delivery_ledger_id": deliver.get("ledger_id"), "ticket_entry_count": len(state.get("ticket_entries", []))}, ensure_ascii=False, sort_keys=True))
    return 0 if passed else 1
