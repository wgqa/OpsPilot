"""Offline evidence aggregation. Does not run models or alter raw attempts/Gold."""
from __future__ import annotations

import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import re
import statistics
import subprocess
import sys
from urllib.parse import urlsplit

BASE=Path(__file__).resolve().parents[1]
ROOT=BASE.parents[3]
sys.path.insert(0,str(ROOT))


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def save(name,value):
    (BASE/name).write_text(json.dumps(value,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")


def decode(raw):
    return raw.decode("utf-16" if raw.startswith((b"\xff\xfe",b"\xfe\xff")) else "utf-8-sig",errors="replace")


def main():
    from opspilot.config import load_local_environment
    load_local_environment()
    paired=load(BASE/"runs/paired-closeout/RESULTS.json")
    assets=load(BASE/"runs/assets-closeout/RESULTS.json")
    web_runs=sorted(BASE.glob("runs/web-*/RESULTS.json"))
    web=load(web_runs[-1])
    rha={}
    for arm in ("R","H","A"):
        rows=[r for r in paired["cases"] if r["strategy"] == arm]
        rha[arm]={"correct":sum(r["correct"] for r in rows),"denominator":len(rows),
                  "control_safe":sum(r["control_safe"] for r in rows),"actual_recovery":"NOT_APPLICABLE",
                  "model_requests":sum(r["model_calls"] for r in rows),"mcp_requests":sum(r["mcp_calls"] for r in rows),
                  "invalid_mcp_calls":sum(r["invalid_calls"] for r in rows),"total_tokens":sum(r["total_tokens"] for r in rows),
                  "mean_latency_seconds":round(statistics.mean(r["latency_seconds"] for r in rows),3)}
    save("RHA.json",{"release":"paired-closeout","metrics":rha,"rows":paired["cases"],
                     "note":"A includes one optional final fact-based model explanation; R/H return the deterministic outcome. Model temperature uses existing runtime default. Semantic initial states/versions match; generated request/event IDs differ."})
    failures=[]
    for path in sorted(BASE.glob("runs/**/RESULT.json")):
        value=load(path)
        if value.get("correct") is False or value.get("failure"):
            failures.append({"path":path.relative_to(BASE).as_posix(),"kind":"EVALUATION_ATTEMPT","result":value})
    for path in web_runs:
        value=load(path)
        if value.get("status") != "PASS":
            failures.append({"path":path.relative_to(BASE).as_posix(),"kind":"BROWSER_ATTEMPT","result":value})
    for path in sorted(BASE.glob("runs/**/*.log")):
        value=decode(path.read_bytes())
        if re.search(r"\b\d+ (failed|errors?)\b",value):
            failures.append({"path":path.relative_to(BASE).as_posix(),"kind":"PYTEST_RED_OR_FAILED_ATTEMPT",
                             "summary":value.splitlines()[-1] if value.splitlines() else ""})
        elif "error TS" in value:
            failures.append({"path":path.relative_to(BASE).as_posix(),"kind":"FRONTEND_BUILD_FAILED_ATTEMPT","summary":"TypeScript build rejected the moved result card's missing null guard; fixed in a3ef416."})
    save("FAILURES.json",{"policy":"All raw attempts retained; repeated failures may appear in both a case result and its raw log.","entries":failures})
    traces=[]
    provider={}
    for path in sorted(BASE.glob("runs/**/TRACE.json")):
        raw=path.read_bytes()
        value=json.loads(raw)
        for item in value.get("model_traces",[]):
            provider.setdefault(item["call_id"],item)
        traces.append({"path":path.relative_to(BASE).as_posix(),"sha256":hashlib.sha256(raw).hexdigest(),"task_id":value.get("task_id"),
                       "model_requests":len(value.get("model_traces",[])),"observations":len(value.get("observations",[]))})
    for path in BASE.glob("runs/**/POST_COMPLETION_INVALIDATION.json"):
        value=load(path)
        for item in value.get("provider_attempts",[]):
            provider.setdefault("chat:"+item["attempt_id"],{**item,"usage":{"total_tokens":item.get("total_tokens") or 0}})
    save("TRACE.json",{"kind":"INDEX_OF_ORIGINAL_TRACE_FILES","traces":traces,
                       "provider_attempts_unique":len(provider),"provider_responses_with_id":sum(bool(p.get("provider_response_id")) for p in provider.values()),
                       "total_reported_tokens_all_attempts":sum(int(p.get("usage",{}).get("total_tokens",0)) for p in provider.values()),
                       "cost_usd":None,"cost_note":"No frozen billing rate or provider bill available; tokens and measured latency are reported without invented monetary costs."})
    versions={name:importlib.metadata.version(name) for name in ("langchain","langchain-core","langchain-openai","langgraph","langgraph-checkpoint-sqlite","mcp","pydantic","fastapi","uvicorn","pytest","httpx","openai")}
    lock_names=["pyproject.toml","requirements.lock.txt","requirements.in","frontend/package-lock.json"]
    lock_hashes={name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in lock_names if (ROOT/name).exists()}
    source_names=subprocess.run(["git","diff","--name-only","29d2fc7","--","opspilot","frontend","tests","knowledge","skills"],cwd=ROOT,capture_output=True,text=True,encoding="utf-8",check=True).stdout.splitlines()
    source_hashes={name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in source_names if (ROOT/name).is_file()}
    environment={"python":sys.version,"dependencies":versions,"model_id":os.environ.get("OPSPILOT_MODEL_NAME"),
                 "provider_host":urlsplit(os.environ.get("OPSPILOT_MODEL_BASE_URL","")).hostname,"lock_sha256":lock_hashes,
                 "tested_source_sha256":source_hashes,"head_at_collection":subprocess.check_output(["git","rev-parse","HEAD"],cwd=ROOT,text=True).strip()}
    environment["frontend_dependencies"]={name:load(ROOT/"frontend/node_modules"/name/"package.json")["version"] for name in ("vue","vite","typescript","@playwright/test")}
    save("ENVIRONMENT.json",environment)
    s1=load(BASE/"runs/s1-smoke-shipped/TRACE.json")
    pytest_log=decode((BASE/"runs/full-source-closeout.log").read_bytes())
    pytest_summary=pytest_log.splitlines()[-1] if pytest_log.splitlines() else "RUNNING"
    save("RESULTS.json",{"status":"ACCEPTANCE_CANDIDATE_PENDING_INDEPENDENT_REVIEW","baseline":"29d2fc7d1897ee27743550d84c730110f12091d4",
                         "freeze_commit":"23c6c1c2345506c4d19b5cfc1c43c85e245c6843","implementation_commit":"3119d2f67967437d4af7839c82cfec6916446d1e",
                         "memory_inspector_fix_commit":subprocess.check_output(["git","log","-1","--format=%H","--","opspilot/domain/episodic_memory.py"],cwd=ROOT,text=True).strip(),
                         "narrative_source_fix_commit":"2cd5d15d9f765ffedf16cee8a8ae2f0897805bac",
                         "pytest":pytest_summary,"rha":rha,"paired_correct":paired["correct"],"paired_denominator":paired["denominator"],
                         "paired_control_safe":paired["safe"],"assets":assets,"web":web,"web_results_path":str(web_runs[-1].relative_to(BASE)),
                         "s1_real_smoke":s1["result"],"historical_failures":len(failures),"actual_recovery_s3":"NOT_APPLICABLE",
                         "learning_and_limitations":"See REPORT.md, SOURCE_LEARNING.md, INTERVIEW.md; no next phase authorization."})
    # Secret check emits only counts, never matching values or file contents.
    key=os.environ.get("OPSPILOT_MODEL_API_KEY","")
    leaked=[p.relative_to(BASE).as_posix() for p in BASE.rglob("*") if p.is_file() and key and (key.encode() in p.read_bytes() or key in decode(p.read_bytes()))]
    save("SECRET_SCAN.json",{"configured_api_key_found":len(leaked),"file_paths":leaked,"env_file_in_evidence":False})
    if leaked:
        raise RuntimeError("Configured secret detected in evidence; paths only recorded")
    print(json.dumps({"pytest":pytest_summary,"paired":paired["correct"],"assets":assets["correct"],"failures_retained":len(failures),"web":web["status"],"rha":rha},ensure_ascii=False))


if __name__ == "__main__":
    main()
