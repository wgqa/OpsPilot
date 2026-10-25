"""Eight public Gold facts, real HTTP/MCP, R only: no additional paid tasks."""
import asyncio
import json
import os
import shutil
from opspilot.smokes.m4_continuous import EVIDENCE,RUNTIME,ProviderMeter,execute,write_json
from opspilot.config import load_local_environment,ROOT
from pathlib import Path


async def main():
    load_local_environment(Path("D:/学习/agent新项目/.env"))
    meter=ProviderMeter(EVIDENCE/"PROVIDER_LEDGER.jsonl")
    meter.install()
    before=len(meter.rows())
    cases=json.loads((EVIDENCE/"GOLD.json").read_text(encoding="utf-8"))["benchmark_cases"]
    results=[]
    for case in cases:
        copied=None
        if case.get("knowledge_state")=="expired":
            copied=RUNTIME/"fact-gold-01"/"expired-assets"
            shutil.copytree(ROOT/"knowledge/async-callback",copied)
            manifest=json.loads((copied/"manifest.json").read_text(encoding="utf-8"))
            for doc in manifest["documents"]: doc["expires_at"]="2000-01-01T00:00:00+00:00"
            write_json(copied/"manifest.json",manifest)
            os.environ["OPSPILOT_S3_KNOWLEDGE_DIRECTORY"]=str(copied)
        try:
            results.append(await execute(case,"R",(8,6),"fact-gold-01",meter))
        finally:
            os.environ.pop("OPSPILOT_S3_KNOWLEDGE_DIRECTORY",None)
        write_json(EVIDENCE/"runs/fact-gold-01/RESULTS.json",results)
    assert len(meter.rows())==before,"Rule arm must not call Provider"


asyncio.run(main())
