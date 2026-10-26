"""Package only observed Stage-A results; never edit run logs or old evidence."""
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import xml.etree.ElementTree as ET
import zipfile

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[4]
BASE = "37df7236ae3ce6fe7125cda671d1a28a3409f830"
FREEZE = "9abc4898d9accce1819460d6d4cdce24afae34bc"
CODE = "27a96c1e7ffbb4e836cec15421d24b731dff13b0"
FINAL_TESTS = "fcfb8f99e8b9209d61a737ab1e7b4af696f58595"
RUN = OUT / "runs/full-active-02"


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT)


def sha(value):
    return hashlib.sha256(value).hexdigest()


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf8")


def relative(path):
    return path.relative_to(OUT).as_posix()


command = json.loads((RUN / "COMMAND.json").read_text(encoding="utf8"))
suite = ET.parse(RUN / "junit.xml").getroot()
test_cases = list(suite.iter("testcase"))
assert command["head_at_start"] == FINAL_TESTS and command["exit_code"] == 0
assert len(test_cases) == 399 and not list(suite.iter("failure")) and not list(suite.iter("error"))
new_cases = [t for t in test_cases if t.attrib["classname"].endswith("test_m4_cont_ux_stage_a")]
assert len(new_cases) == 25
records = [json.loads(x) for x in (RUN / "TRACE.jsonl").read_text(encoding="utf8").splitlines() if x.strip()]
journeys = [(i, r) for i, r in enumerate(records, 1) if r["case_id"] == "A08"]
assert len(journeys) == 2
for _, journey in journeys:
    assert len(journey["rounds"]) == 4
    assert journey["protected_before"] == journey["protected_after"]
    assert Counter(x["kind"] for x in journey["ledger"]["attempts"]) == {"MODEL": 9, "MCP": 6}
    explanation = journey["rounds"][2]["result"]["body"]
    doc = next(x for x in journey["rounds"][1]["result"]["source_refs"] if x["kind"] == "KNOWLEDGE")
    assert f"{doc['document_id']}@{doc['version']}" in explanation

# Root TRACE is an exact byte copy of an actual final test emission file.
(OUT / "TRACE.jsonl").write_bytes((RUN / "TRACE.jsonl").read_bytes())
trace_index = [{"line": i, "case_id": r["case_id"], "source": relative(RUN / "TRACE.jsonl"),
                "evidence_level": r["evidence_level"]} for i, r in enumerate(records, 1)]
write_json(OUT / "TRACE_INDEX.json", {"root_trace_sha256": sha((OUT / "TRACE.jsonl").read_bytes()),
                                     "copied_verbatim_from": relative(RUN / "TRACE.jsonl"), "rows": trace_index})

os_archives = []
for log in sorted((RUN / "basetemp").glob("test_a06_real_os_crash_restore*/*.log")):
    if log.parent.name.endswith("current"):
        continue
    target = RUN / "os" / log.parent.name / log.name
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        assert target.read_bytes() == log.read_bytes()
    else:
        shutil.copyfile(log, target)
    os_archives.append({"path": relative(target), "sha256": sha(target.read_bytes())})
assert len(os_archives) == 8

runs = []
for path in sorted((OUT / "runs").glob("*/COMMAND.json")):
    value = json.loads(path.read_text(encoding="utf8"))
    log = path.with_name("pytest.log")
    summary = log.read_text(encoding="utf8").splitlines()[-1]
    counts = {name: int(match.group(1)) if (match := re.search(rf"(\d+) {name}", summary)) else 0
              for name in ["passed", "failed", "deselected", "skipped"]}
    runs.append({"label": path.parent.name, "command_record": relative(path),
                 "command": value["command"], "head_at_start": value.get("head_at_start"),
                 "head_record_status": "RECORDED_AT_RUN_START" if value.get("head_at_start") else "NOT_CAPTURED_IN_EARLY_RUN_METADATA_DO_NOT_BACKFILL",
                 "working_file_sha256": value.get("working_file_sha256", {}),
                 "exit_code": value["exit_code"], "elapsed_seconds": value["elapsed_seconds"],
                 "summary": summary, "counts": counts, "raw_log": relative(log),
                 "raw_log_sha256": sha(log.read_bytes()),
                 "legacy_evidence_preserved": value.get("legacy_evidence_preserved", [])})

business_paths = git("diff", "--name-only", BASE, CODE, "--", "opspilot").decode("utf8").splitlines()
expected_paths = ["opspilot/domain/chat.py", "opspilot/domain/d2.py", "opspilot/domain/database.py",
                  "opspilot/domain/execution_budget.py", "opspilot/domain/investigation_updates.py",
                  "opspilot/domain/task_control.py", "opspilot/s3_investigation.py"]
assert business_paths == expected_paths
assert not git("diff", "--name-only", CODE, FINAL_TESTS, "--", "opspilot").strip()
protected = ["PROJECT_NORTH_STAR.md", "AGENTS.md", "frontend", "docs/baseline", "docs/handoff",
             "docs/evidence/vnext/m4-cont-ux-01/GOLD.json", "docs/evidence/vnext/m4-cont-ux-01/PLAN.md",
             "tests/test_m4_autonomy_c1_red.py", "docs/evidence/vnext/m4-autonomy-c1",
             "docs/evidence/vnext/m4-c1-hf-01", "docs/evidence/vnext/m4-continuous-vs01",
             "docs/evidence/vnext/m4-eg-01", "docs/evidence/vnext/m4-eg01-hf-01", "requirements.lock"]
assert not git("diff", "--name-only", BASE, FINAL_TESTS, "--", *protected).strip()
assert not git("diff", "--name-only", "--", "opspilot", "tests", *protected).strip()
git("diff", "--check", BASE, FINAL_TESTS)
diff = git("diff", BASE, CODE, "--", "opspilot")
(OUT / "SOURCE_DIFF.patch").write_bytes(diff)
write_json(OUT / "SCOPE_AUDIT.json", {
    "base_sha": BASE, "implementation_sha": CODE, "final_test_sha": FINAL_TESTS,
    "source_paths": business_paths, "source_diff_sha256": sha(diff), "protected_paths_unchanged": protected,
    "business_sources_changed_after_implementation": False,
    "check_method": "git diff base..target and tracked working tree; historical test append archives retained separately",
    "schema": {"from": 16, "to": 17, "added_table_columns": {"task_execution_budgets": ["policy_version", "aux_provider_limit"]},
               "live_user_database_opened_or_migrated": False},
    "user_primary_workspace": "D:/学习/agent新项目; no switch, reset, staging, file cleanup, or execution against its DB",
    "preexisting_untracked": "All seven preexisting cache/basetemp prefixes preserved; not staged",
    "os_log_archives": os_archives,
})

archive = next(Path("D:/学习/agent新项目/开发目录").glob("*Skill*20261024*.zip"))
with zipfile.ZipFile(archive) as z:
    entry = next(n for n in z.namelist() if n.endswith("opspilot-slice-review/SKILL.md"))
    skill_hash = sha(z.read(entry))
read_names = ["PROJECT_NORTH_STAR.md", "AGENTS.md", "docs/baseline/ACCESS_MATRIX.md",
              "docs/baseline/STATE_TRANSITIONS.md", "docs/baseline/EVENT_RECOVERY.md",
              "docs/evidence/vnext/m1-hf-01/ACCEPTANCE_PLAN.md"]
write_json(OUT / "DELIVERY_READ_RECORD.json", {
    "actual_review_target_sha": FINAL_TESTS, "source_target_sha": CODE,
    "read_stage": "Implementation-side pre-submission reread; not a main-Agent independent review",
    "actual_reads": [{"path": name, "blob": git("rev-parse", FINAL_TESTS + ":" + name).decode().strip(),
                      "method": "Actual text opened in this task; North Star and AGENTS fully reread before submission"}
                     for name in read_names],
    "skill": {"archive": str(archive), "entry": entry, "sha256": skill_hash,
              "checkout_skill_path_present": (ROOT / entry).exists(),
              "execution": "Manual archive Skill A/B and C submission checks; discovery is not execution or main-Agent acceptance"},
    "scope": "Stage A only; no frontend changes, paid Provider, J1-J4, Stage B, new permission or business write",
})

gold_status = {
    "01": ("STAGE_A_DETERMINISTIC", ["A01", "A02", "A08"]),
    "02": ("STAGE_A_REAL_OS_RECOVERY", ["A06", "A03"]),
    "03": ("STAGE_A_HTTP_REPLAY", ["A01", "A03-LOST-HTTP"]),
    "04": ("STAGE_A_DETERMINISTIC", ["A02-TASK-RACE", "A04-MIXED-RACE", "A05"]),
    "05": ("STAGE_A_DETERMINISTIC", ["A08"]),
    "06": ("EXISTING_REGRESSION_ONLY", []),
    "07": ("STAGE_A_DETERMINISTIC", ["A07"]),
    "08": ("STAGE_A_DETERMINISTIC", ["A08"]),
    "09": ("EXISTING_SLA_REGRESSION_PLUS_A08_QUEUED", ["A08"]),
    "10": ("EXISTING_EG01_HF_REGRESSION_ONLY", []),
    "11": ("EXISTING_CONTEXT_MEMORY_REGRESSION_PLUS_A08", ["A08"]),
    "12": ("NOT_RUN_STAGE_B", []), "13": ("NOT_RUN_STAGE_B", []),
    "14": ("EXISTING_SECURITY_REGRESSION_PLUS_NEW_RUN_SCOPE", ["A03"]),
    "15": ("STAGE_A_PROTECTED_SNAPSHOTS_AND_REGRESSION", ["A08", "A07-COMPOUND"]),
    "16": ("STAGE_A_SQLITE_AND_HTTP_NOT_TWO_TAB_BROWSER", ["A01", "A02-RUN-RACE", "A02-TASK-RACE", "A03-LOST-HTTP"]),
    "17": ("EXISTING_CONTEXT_REGRESSION_PLUS_DETERMINISTIC_PRONOUN", ["A08"]),
    "18": ("STAGE_A_AUXILIARY_AND_EXISTING_ROUTE_RECOVERY", ["A04", "A04-MIXED-RACE", "A05-CHAT-RETRY"]),
    "19": ("STAGE_A_DETERMINISTIC_PLUS_VS08_REGRESSION", ["A07-COMPOUND"]),
    "20": ("STAGE_A_IMPLEMENTER_RUBRIC_NOT_INDEPENDENT_ACCEPTANCE", ["A08", "A06", "A05"]),
}
modules = Counter(t.attrib["classname"] for t in test_cases)
write_json(OUT / "RESULTS.json", {
    "status": "ACCEPTANCE_CANDIDATE", "base_sha": BASE, "freeze_sha": FREEZE,
    "red_shas": ["476f0de36f994bca4d7aa86a045d31a9c14656ec", "4c836bb9700ac94e9049d7645176f985485b9ce1", "c45f6702e70e4c880eed567755f0c18d213fe62e"],
    "implementation_sha": CODE, "test_fixture_correction_sha": FINAL_TESTS,
    "final_evidence_commit": "The Git commit containing this file; final actual SHA is reported after commit/push",
    "generated_utc": datetime.now(timezone.utc).isoformat(),
    "final_suite": {"run": relative(RUN), "passed": 399, "failed": 0, "deselected": 1,
                    "new_stage_a_cases_passed": len(new_cases), "historical_red_excluded": "test_explicit_protocol_followup_is_accepted_as_same_task_readonly_run_before_ttl_fix"},
    "unfiltered_suite": {"run": "runs/full-unfiltered-01", "implementation_sha": CODE,
                         "passed": 399, "failed": 1, "failure_kind": "UNCHANGED_OBSOLETE_CLASSIFICATION_CONTRACT_RED"},
    "runs": runs, "final_suite_modules": dict(sorted(modules.items())),
    "new_stage_a_testcases": [{"id": t.attrib["name"], "seconds": float(t.attrib["time"])} for t in new_cases],
    "gold_applicability": [{"id": "CONTUX-" + k, "status": value[0], "new_observed_case_ids": value[1],
                            "paid_or_browser_journey": "NOT_RUN"} for k, value in gold_status.items()],
    "complete_deterministic_interface_journeys": [{"trace_line": n, "tool_order_variant": r["protocol_first"],
        "task_id": r["ledger"]["budget"]["task_id"], "user_requests": 4,
        "investigator_model_attempts": 9, "mcp_attempts": 6, "classifier_attempts": 3, "chat_attempts": 1,
        "actual_model_double_invocations": len(r["actual_model_double_inputs"]),
        "active_elapsed_ms": [rd["active_time"]["active_elapsed_ms"] for rd in r["rounds"]],
        "protected_snapshot_unchanged": r["protected_before"] == r["protected_after"]}
        for n, r in journeys],
    "recovery_goal_scoring": "Four OS contract checks pass with deliberate unknown reservations; their partial delivery is NOT a fully completed user goal",
    "provider": {"paid_calls": 0, "actual_paid_provider_test": "NOT_RUN", "token_usage": "NOT_AVAILABLE_FOR_DETERMINISTIC_DOUBLE",
                 "request_bound": "24 investigator + 8 auxiliary; no borrowing; not a Token or dollar bound"},
    "browser_and_frontend": "NOT_RUN / NOT_CHANGED; Stage B not authorized",
    "main_agent_independent_review": "NOT_PERFORMED_BY_IMPLEMENTER; await review",
    "stop": "No Stage B or paid J1-J4; no budget increase or new business writes",
})

lines = ["# 阶段 A 实际四请求旅程", "", "证据级别：确定性模型替身 + FastAPI TestClient 原 API + LangGraph/Worker + 真实 MCP stdio/本地 HTTP + SQLite。不是真实 Provider 或浏览器体验。", ""]
questions = ["订单返回 200，但下游回调还未完成，请核实。", "请按当前绑定协议核对 HTTP 202 的含义，给出能核对的来源。", "你刚才引用的那份，为什么不能证明已经处理完成？", "那现在这次回调完成了吗？请按新一轮事实核实。"]
for n, r in journeys:
    lines += [f"## 合法次序变体：{r['protocol_first']}", "", f"Task：`{r['ledger']['budget']['task_id']}`；完整记录 `TRACE.jsonl:{n}`。", ""]
    for i, (question, rd) in enumerate(zip(questions, r["rounds"]), 1):
        source = rd.get("source") or rd["message"]
        answer = rd["result"]
        text = answer.get("answer_text") or answer.get("body")
        lines += [f"{i}. 用户：{question}", "", f"   实际持久答复：{text}", "",
                  f"   source_message_id=`{source['message_id']}`；Run=`{rd.get('run_id') or source['run_id']}`；累计活跃时间 `{rd['active_time']['active_elapsed_ms']}ms`。", ""]
    lines += ["独立测试准备在第 4 次请求前将同 Event Receiver 从 QUEUED 改为 PROCESSED 并递增真实版本；该动作不是 Agent 工具或业务修复。Agent 本轮新 Observation 才支持 PROCESSED 回答。", "",
              "总计 9 Investigator MODEL + 6 MCP，辅助 3 分类 + 1 Chat；旧 Diagnosis/Task/Control/审批与业务写表快照不变。新策略 24/18、Run 8/6 或 4/3、辅助 8 全部有剩余，未触发 300000ms 时间限制。", ""]
(OUT / "JOURNEY.md").write_text("\n".join(lines), encoding="utf8")

artifacts = [p for p in OUT.rglob("*") if p.is_file() and "basetemp" not in p.parts
             and "__pycache__" not in p.parts and p.name != "RAW_ARTIFACT_INDEX.json"]
write_json(OUT / "RAW_ARTIFACT_INDEX.json", {"excludes": ["basetemp", "__pycache__", "this self-referential index"],
           "hash_basis": "sha256 is actual working file bytes; LF-normalized hash also supplied for Git autocrlf text checkouts; raw .log bytes use -text attributes",
           "files": [{"path": relative(p), "bytes": p.stat().st_size, "sha256": sha(p.read_bytes()),
                      "lf_normalized_sha256": sha(p.read_bytes().replace(b'\r\n', b'\n'))} for p in sorted(artifacts)]})
print(json.dumps({"final_suite": "399 passed / 1 historical RED deselected", "new_cases": len(new_cases),
                  "trace_rows": len(records), "os_log_archives": len(os_archives), "artifact_files": len(artifacts)}, ensure_ascii=False))
