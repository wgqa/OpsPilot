from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(ROOT))

from opspilot.config import load_local_environment


RUN_ROOT = Path(os.environ.get(
    "OPSPILOT_HF01_RUN_ROOT",
    str(Path(__file__).resolve().parent / "web-e2e-hf01-01"),
)).resolve()
RUN_ROOT.mkdir(parents=True, exist_ok=True)
load_local_environment(Path(os.environ["OPSPILOT_LOCAL_ENV_FILE"]))
os.environ["OPSPILOT_DB_PATH"] = str((RUN_ROOT / "domain.sqlite3").resolve())

from opspilot.domain.database import reset_fixture
from opspilot.domain.s3 import prepare_s3_fixture
from opspilot.web.app import create_app


db_path = RUN_ROOT / "domain.sqlite3"
checkpoint_path = RUN_ROOT / "checkpoints.sqlite3"
reset_fixture(db_path, "S1_POS")
fixture = prepare_s3_fixture(
    db_path,
    "DELIVERED_PENDING",
    order_id="async-order",
    contract_version=2,
    queue_age_seconds=20,
    processing_sla_seconds=300,
)
app = create_app(
    db_path=db_path,
    checkpoint_db_path=checkpoint_path,
    start_worker=True,
    credentials={"support-a": "support-test-password"},
    expected_origin="http://127.0.0.1:5178",
    heartbeat_seconds=0.2,
)
print(json.dumps({
    "event": "M4_C1_HF01_WEB_READY",
    "db_path": str(db_path.resolve()),
    "checkpoint_path": str(checkpoint_path.resolve()),
    "scenario": "DELIVERED_PENDING",
    "fixture": fixture,
    "provider_key_loaded": bool(os.environ.get("OPSPILOT_MODEL_API_KEY")),
    "model_name": os.environ.get("OPSPILOT_MODEL_NAME"),
    "mcp_mode": "application MCP client with in-process local MCP server",
}, ensure_ascii=False, sort_keys=True), flush=True)

import uvicorn

uvicorn.run(app, host="127.0.0.1", port=8011, log_level="info")
