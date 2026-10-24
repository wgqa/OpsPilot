from __future__ import annotations

import json
import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[6]
RUN_ROOT = Path(__file__).resolve().parent / "web-e2e-04"
sys.path.insert(0, str(ROOT))

from opspilot.config import load_local_environment


env_file = Path(os.environ["OPSPILOT_LOCAL_ENV_FILE"])
load_local_environment(env_file)

from opspilot.domain.database import reset_fixture
from opspilot.domain.s3 import prepare_s3_fixture
from opspilot.web.app import create_app


RUN_ROOT.mkdir(parents=True, exist_ok=True)
db_path = RUN_ROOT / "domain.sqlite3"
checkpoint_path = RUN_ROOT / "checkpoints.sqlite3"
reset_fixture(db_path, "S1_POS")
fixture = prepare_s3_fixture(
    db_path,
    "DELIVERED_PENDING",
    contract_version=2,
    queue_age_seconds=60,
)
(RUN_ROOT / "fixture-preparation.json").write_text(
    json.dumps(fixture, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
    encoding="utf-8",
)

app = create_app(
    db_path=db_path,
    checkpoint_db_path=checkpoint_path,
    start_worker=True,
    credentials={"support-a": "support-test-password"},
    expected_origin="http://127.0.0.1:5175",
    heartbeat_seconds=0.2,
)
print(json.dumps({
    "event": "C1_WEB_E2E_READY",
    "db_path": str(db_path),
    "checkpoint_path": str(checkpoint_path),
    "scenario": "DELIVERED_PENDING",
    "fixture": fixture,
    "provider_key_loaded": bool(os.environ.get("OPSPILOT_MODEL_API_KEY")),
    "model_name": os.environ.get("OPSPILOT_MODEL_NAME"),
}, ensure_ascii=False, sort_keys=True), flush=True)

import uvicorn

uvicorn.run(app, host="127.0.0.1", port=8001, log_level="info")
