from __future__ import annotations

import json
import os
import secrets
import shutil
import subprocess
import traceback
from datetime import datetime, timezone

from opspilot.config import ROOT, load_local_environment
from opspilot.domain.database import reset_fixture
from opspilot.domain.s3 import prepare_s3_fixture
from opspilot.smokes.m1_03 import _kill, _server_environment
from opspilot.smokes.m4_01 import _free_port, _start_api, _start_vite
from opspilot.smokes.m4_02 import EVIDENCE, trace, write_json, business_snapshot


def main():
    load_local_environment()
    stamp=datetime.now(timezone.utc).strftime("web-%Y%m%dT%H%M%SZ")
    base=EVIDENCE/"runs"/stamp
    base.mkdir(parents=True,exist_ok=False)
    runtime=ROOT/".runtime/m4-02"/stamp
    runtime.mkdir(parents=True,exist_ok=False)
    db,checkpoint=runtime/"domain.sqlite3",runtime/"checkpoints.sqlite3"
    reset_fixture(db,"S1_POS")
    write_json(base/"PREPARATION.json",prepare_s3_fixture(db,"DELIVERED_PENDING"))
    before=business_snapshot(db)
    passwords={name:secrets.token_urlsafe(24) for name in ("support-a","approver-a","support-b","approver-b")}
    api_port,ui_port=_free_port(),_free_port()
    api_origin,ui_origin=f"http://127.0.0.1:{api_port}",f"http://127.0.0.1:{ui_port}"
    env=_server_environment(db,checkpoint,ui_origin,passwords)
    browser_env=os.environ.copy()
    browser_env.update({"OPSPILOT_M4_UI_URL":ui_origin,"OPSPILOT_M4_SUPPORT_PASSWORD":passwords["support-a"],
                        "OPSPILOT_M4_SCREENSHOTS":str(base/"screenshots"),"OPSPILOT_M4_RESULT_PATH":str(base/"JOURNEY.json")})
    api=vite=None
    result={"status":"FAIL"}
    def browser(mode):
        browser_env["OPSPILOT_M4_MODE"]=mode
        completed=subprocess.run([shutil.which("node"),str(ROOT/"frontend/e2e/m4-02-callback.mjs")],cwd=ROOT/"frontend",env=browser_env,
                                 capture_output=True,text=True,encoding="utf-8",timeout=420)
        output=completed.stdout+completed.stderr
        for value in passwords.values():
            output=output.replace(value,"[REDACTED]")
        (base/f"{mode}-browser.log").write_text(output,encoding="utf-8")
        if completed.returncode:
            raise RuntimeError(f"Real browser {mode} failed; see raw log")
        return json.loads(__import__('pathlib').Path(browser_env["OPSPILOT_M4_RESULT_PATH"]).read_text(encoding="utf-8"))
    try:
        api=_start_api(api_port,env,base/"api.log")
        vite=_start_vite(ui_port,api_origin,env,base/"vite.log")
        journey=browser("journey")
        task_id=journey["task_id"]
        old_pid=api.pid
        _kill(api)
        api=None
        api=_start_api(api_port,env,base/"api-restart.log")
        browser_env.update({"OPSPILOT_M4_TASK_ID":task_id,"OPSPILOT_M4_SESSION_ID":journey["session_id"],"OPSPILOT_M4_RESULT_PATH":str(base/"RESUME.json")})
        resumed=browser("resume")
        write_json(base/"TRACE.json",trace(db,task_id))
        after=business_snapshot(db)
        write_json(base/"NO_BUSINESS_WRITES.json",{"before":before,"after":after,"unchanged":before == after})
        if before != after:
            raise RuntimeError("S3 browser investigation mutated a business record")
        result={"status":"PASS","task_id":task_id,"session_id":journey["session_id"],"old_pid":old_pid,"new_pid":api.pid,
                "same_db":str(db.relative_to(ROOT)),"same_checkpoint":str(checkpoint.relative_to(ROOT)),"browser_journey":journey["status"],"after_restart":resumed["status"]}
    except Exception as error:
        (base/"FAILURE.txt").write_text("".join(traceback.format_exception(error)),encoding="utf-8")
        from opspilot.domain.database import connect
        with connect(db) as c:
            row=c.execute("SELECT task_id FROM task_bindings ORDER BY rowid DESC LIMIT 1").fetchone()
        if row:
            write_json(base/"TRACE.json",trace(db,row[0]))
        result={"status":"FAIL","failure":str(error)}
    finally:
        _kill(api)
        _kill(vite)
    write_json(base/"RESULTS.json",result)
    print(json.dumps({"evidence_dir":str(base.relative_to(ROOT)),**result},ensure_ascii=False))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
