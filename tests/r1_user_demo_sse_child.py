from __future__ import annotations

import argparse
import importlib.util
import json
import os
import socket
import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import uvicorn
from opspilot.web.app import create_app


RUN_API = ROOT / "scripts" / "user-demo" / "run_api.py"
RUN_API_SPEC = importlib.util.spec_from_file_location("opspilot_user_demo_run_api", RUN_API)
assert RUN_API_SPEC is not None and RUN_API_SPEC.loader is not None
RUN_API_MODULE = importlib.util.module_from_spec(RUN_API_SPEC)
RUN_API_SPEC.loader.exec_module(RUN_API_MODULE)


PASSWORD = "sse-test-support-password"
ORIGIN = "http://testserver"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", required=True)
    parser.add_argument("--checkpoint", required=True)
    parser.add_argument("--ready", required=True)
    parser.add_argument("--stop-request", required=True)
    parser.add_argument("--no-worker", action="store_true")
    args = parser.parse_args()

    os.environ["OPSPILOT_DB_PATH"] = args.db
    os.environ["OPSPILOT_CHECKPOINT_DB_PATH"] = args.checkpoint
    os.environ["OPSPILOT_ASSISTANT_PROVIDER_ENABLED"] = "0"
    os.environ["OPSPILOT_ASSISTANT_RUNTIME_ENABLED"] = "0"
    os.environ["OPSPILOT_ASSISTANT_EXPERIMENT_ID"] = ""
    os.environ["OPSPILOT_MODEL_API_KEY"] = ""
    os.environ["OPSPILOT_LEGACY_PROVIDER_ENABLED"] = "0"

    app = create_app(
        db_path=args.db,
        checkpoint_db_path=args.checkpoint,
        start_worker=not args.no_worker,
        credentials={"support-a": PASSWORD, "support-b": "sse-test-support-b-password"},
        expected_origin=ORIGIN,
        heartbeat_seconds=0.1,
    )

    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind(("127.0.0.1", 0))
    listener.listen(128)
    port = int(listener.getsockname()[1])
    config = uvicorn.Config(app, host="127.0.0.1", port=port, workers=1,
                            reload=False, log_level="info", access_log=False)
    server = RUN_API_MODULE.UserDemoServer(config, app)

    Path(args.ready).write_text(json.dumps({"port": port}), encoding="utf-8")

    threading.Thread(
        target=RUN_API_MODULE.watch_for_stop_request,
        args=(Path(args.stop_request), app, server),
        name="test-stop-watch", daemon=True,
    ).start()
    server.run(sockets=[listener])
    print(json.dumps({"event": "server_exit", "exit_code": 0}), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
