"""Free deterministic OS child. Arguments refer only to an isolated test DB."""
import asyncio, os, sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from test_ar02_runtime import FixtureModel
from opspilot.assistant import run_assistant
from opspilot.domain.task_control import register_worker_owner,recover_running_task_runs,claim_task_run,trusted_identity
from opspilot.web.worker import SingleInstanceWorker

db,cp,run_id,phase=sys.argv[1:]
lease=SingleInstanceWorker(db);lease.acquire();lease.register()
owner=lease.owner_id
if phase=='after':asyncio.run(lease.recover_after_exclusive_start())
claim_task_run(db,trusted_identity(db,'support-a'),run_id)
if phase=='before':os.environ['OPSPILOT_AR02_TEST_CRASH_AFTER_OBSERVATION']='1'
result=asyncio.run(run_assistant(db,cp,owner,run_id,model=FixtureModel(mode='business')))
lease.release()
print(result,flush=True)
raise SystemExit(0 if result['status']=='SUCCEEDED' else 2)
