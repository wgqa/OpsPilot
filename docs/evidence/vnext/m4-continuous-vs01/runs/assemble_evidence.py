"""Read actual experiment records into an index; never manufacture observations."""
from __future__ import annotations
import hashlib
import importlib.metadata
import json
import platform
import re
import sqlite3
import subprocess
import sys
from pathlib import Path

from opspilot.domain.database import connect
from opspilot.smokes.m4_continuous import EVIDENCE,RUNTIME,export_trace,write_json
from opspilot.smokes.m4_02 import business_snapshot


def usage_totals(rows):
    known=[row for row in rows if isinstance(row,dict) and isinstance(row.get("input_tokens"),int) and isinstance(row.get("output_tokens"),int)]
    i=sum(row["input_tokens"] for row in known);o=sum(row["output_tokens"] for row in known)
    return {"input_tokens":i,"output_tokens":o,"total_tokens":i+o,"peak_estimated_usd":(i*.30+o*1.20)/1_000_000,"usage_known":len(known),"usage_unknown":len(rows)-len(known)}


def web_export(release):
    db=RUNTIME/release/"domain.sqlite3";directory=EVIDENCE/"runs"/release
    if not db.exists():return []
    results=[]
    with connect(db) as c:
        tasks=[row[0] for row in c.execute("SELECT task_id FROM s3_task_resources ORDER BY rowid")]
        for task in tasks:
            raw=export_trace(db,task)
            for table in ("chat_attempts","chat_context_manifests","investigation_update_assessments"):
                raw[table]=[dict(row) for row in c.execute(f"SELECT * FROM {table} WHERE task_id=? ORDER BY rowid",(task,))]
            raw["investigation_update_attempts"]=[dict(row) for row in c.execute("SELECT a.* FROM investigation_update_attempts a JOIN investigation_update_assessments s ON s.assessment_id=a.assessment_id WHERE s.task_id=? ORDER BY a.rowid",(task,))]
            raw["chat_answer_chunks"]=[dict(row) for row in c.execute("SELECT ch.* FROM chat_answer_chunks ch JOIN chat_attempts a ON a.attempt_id=ch.attempt_id WHERE a.task_id=? ORDER BY ch.rowid",(task,))]
            write_json(directory/(task+"-TRACE.json"),raw)
            answers=[json.loads(row["body_json"]) for row in raw["s3_run_answers"]]
            results.append({"release":release,"task_id":task,"runs":raw["task_runs"],"answers":answers,
                            "readonly_followups":raw["c1_readonly_followup_runs"],"classifications":raw["investigation_update_assessments"],
                            "business_model_attempts":len([r for r in raw["d2_attempts"] if r["kind"]=="MODEL"]),
                            "mcp_attempts":len([r for r in raw["d2_attempts"] if r["kind"]=="MCP"]),
                            "chat_provider_attempts":len(raw["chat_attempts"]),"classifier_provider_attempts":len(raw["investigation_update_attempts"]),
                            "writes":raw["write_counts"],"trace":str((directory/(task+"-TRACE.json")).relative_to(EVIDENCE))})
    after=business_snapshot(db);write_json(directory/"BUSINESS-AFTER.json",after)
    before_path=directory/("BUSINESS-BEFORE.json" if release=="web-03" else "BUSINESS-BEFORE-TASK2.json")
    if before_path.exists():
        before=json.loads(before_path.read_text(encoding="utf-8"));write_json(directory/"BUSINESS-COMPARISON.json",{"unchanged":before==after,"before":before_path.name,"after":"BUSINESS-AFTER.json"})
    write_json(directory/"JOURNEY.json",results)
    return results


def main():
    ledger=[json.loads(line) for line in (EVIDENCE/"PROVIDER_LEDGER.jsonl").read_text(encoding="utf-8").splitlines()]
    reservations=[row for row in ledger if row["event"]=="RESERVE"]
    completions=[row for row in ledger if row["event"]=="COMPLETE"]
    assert len(reservations)<=180 and len({row["request_id"] for row in reservations})==len(reservations)
    costs=usage_totals([row.get("usage") for row in completions])
    assert costs["peak_estimated_usd"]<3
    cases=[]
    for release in ("budget-01","controls-01","budget-02","controls-02","fact-gold-01","holdout-01"):
        root=EVIDENCE/"runs"/release
        for file in sorted(root.glob("*/RESULT.json")):
            result=json.loads(file.read_text(encoding="utf-8"));trace=json.loads((file.parent/"TRACE.json").read_text(encoding="utf-8"))
            traces=trace["d2_model_traces"]
            usage=usage_totals([json.loads(row["usage_json"]) for row in traces])
            answer=result["answer"]
            row={"release":release,"case_id":result["case_id"],"strategy":result["strategy"],"profile":result["profile"],
                 "task_id":result["task_id"],"run_id":result["run_id"],"source_trace":str((file.parent/"TRACE.json").relative_to(EVIDENCE)),
                 "delivery_mode":answer.get("result",{}).get("delivery_mode"),"result_state":answer.get("result_state"),
                 "answer_text":answer.get("answer_text"),"actual_tools":result["actual_tools"],"model_requests":len(traces),
                 "mcp_attempts":sum(a["kind"]=="MCP" for a in trace["d2_attempts"]),"invalid_observations":sum(o["status"]!="OK" for o in trace["d2_tool_observations"]),
                 "latency_seconds":result["elapsed_seconds"],"usage":usage,"criteria":result["criteria"],"failure":result["failure"],
                 "preparation_valid_for_formal_gate":release not in {"budget-01","controls-01"},
                 "current_final_source_independently_tested":False if release=="holdout-01" else None}
            if trace["s3_diagnoses"]:
                row["formal_gate"]=json.loads(trace["s3_diagnoses"][-1]["body_json"])["gate"]
            cases.append(row)
    webs=web_export("web-02")+web_export("web-03")
    tests=[]
    for directory in sorted((EVIDENCE/"runs").iterdir()):
        if not directory.is_dir():continue
        exit_path=directory/"exit-code.txt";log=directory/"pytest.log"
        if exit_path.exists() and log.exists():
            raw=log.read_text(encoding="utf-8",errors="replace")
            tests.append({"run":directory.name,"exit_code":int(exit_path.read_text(encoding="utf-8-sig").strip()),
                          "log":str(log.relative_to(EVIDENCE)),"summary":raw.strip().splitlines()[-1] if raw.strip() else "EMPTY_LOG",
                          "command":(directory/"command.txt").read_text(encoding="utf-8-sig").strip() if (directory/"command.txt").exists() else "See recorded tool execution and run name; no retroactive command inference"})
    final_sha=subprocess.check_output(["git","rev-parse","HEAD"],text=True).strip()
    results={"status":"ACCEPTANCE_CANDIDATE","main_agent_review":"NOT_PERFORMED","base_sha":"85be293342529de85b40507b9c90c75bc1a77b38",
             "freeze_sha":"dbb62337eac4e242f38659f940823522ac318ad5","initial_red_sha":"a25a354e58f52c6058d037ee62f7460899bbba71",
             "initial_source_sha":"209a3b7","final_source_sha":final_sha,
             "holdout_source_sha":"e42087ea0783eed10238b0ec820f377f76e60f87","holdout_repeats":1,
             "holdout_final_source_limit":"Response retention changed after first holdout, based on earlier Web development output. No holdout rerun or Prompt tuning; final independent holdout remains unproven.",
             "provider":{"requests":len(reservations),"completed":len(completions),"cap":180,"usd_cap":3,**costs,"accounting":"Peak no-cache estimate, not invoice; reasoning included in provider usage","ledger":"PROVIDER_LEDGER.jsonl"},
             "tests":tests,"experiments":cases,"web_journeys":webs,
             "known_limits":["Original pre-implementation C1 RED remains failing and unchanged; full-01 records the failure; active full regression excludes only that file.",
                             "First ten real experiments had a preparation contract defect and are retained separately.",
                             "Per-case RESULT.provider_requests was a cumulative repeated-label view. Do not sum it: costs here use actual d2 usage and the globally unique ledger requests.",
                             "H can select a focus that omits transport history; no claim A must beat R/H.",
                             "Visible Chat explanation preserved source continuity but added an incorrect SLA qualification; Domain authorization and Gate were unaffected. See web-03/02-followup-explanation.txt.",
                             "Gold P1-failed expects QUEUED while its two 503 preparation responses produce NOT_RECEIVED. Gold not rewritten; do not count that mismatch as a passing correctness assertion.",
                             "R-only public Gold fact runs do not prove full A/H six-pair performance or Knowledge/Memory value.",
                             "No new live S1 Provider approval cycle this slice; full safety regression covers S1/S2 contracts."]}
    write_json(EVIDENCE/"RESULTS.json",results)
    write_json(EVIDENCE/"RHA_RESULTS.json",[c for c in cases if c["release"] in {"budget-02","controls-02"}])
    env={"python":sys.version,"platform":platform.platform(),"sqlite":sqlite3.sqlite_version,
         "versions":{name:importlib.metadata.version(name) for name in ("langgraph","langchain-openai","mcp","pytest","fastapi","httpx")},
         "node":"24.16.0","npm":"11.13.0","dependency_changes":"No dependencies added; SQLite schema 15 -> 16"}
    write_json(EVIDENCE/"ENVIRONMENT.json",env)
    indexed=[]
    for file in sorted((EVIDENCE/"runs").rglob("*TRACE.json")):
        raw=json.loads(file.read_text(encoding="utf-8"));source=str(file.relative_to(EVIDENCE))
        for kind,key in (("MCP_OBSERVATION","d2_tool_observations"),("MODEL_ATTEMPT","d2_model_traces"),("HTTP_RESPONSE","http"),
                         ("TRANSPORT_HTTP_OBSERVATION","transport"),("TASK_CONTROL","task_controls"),("RUN","task_runs"),
                         ("CLASSIFIER","investigation_update_attempts"),("CHAT_PROVIDER","chat_attempts")):
            for row in raw.get(key,[]):indexed.append({"kind":kind,"source_file":source,"observed_record":row})
    (EVIDENCE/"TRACE.jsonl").write_text("".join(json.dumps(row,ensure_ascii=False,default=str)+"\n" for row in indexed),encoding="utf-8")
    print(json.dumps({"cases":len(cases),"web_tasks":len(webs),"provider":results["provider"],"indexed_real_records":len(indexed)},ensure_ascii=False))


if __name__=="__main__":main()
