"""Uvicorn launcher with a filesystem-triggered graceful shutdown for Windows."""
from __future__ import annotations

import os
import sys
import threading
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

import uvicorn

from opspilot.assistant import create_assistant_model
from opspilot.web.app import create_app


def main() -> int:
    host = "127.0.0.1"
    port = 8000
    expected_origin = os.environ.get("OPSPILOT_WEB_ORIGIN", f"http://{host}:{port}")
    app = create_app(expected_origin=expected_origin, assistant_model_factory=create_assistant_model)
    server = uvicorn.Server(
        uvicorn.Config(app, host=host, port=port, workers=1, reload=False, log_level="info")
    )
    runtime = ROOT / ".runtime" / "user-demo"
    stop_request = runtime / "shutdown.request"

    def watch_for_stop() -> None:
        while not server.should_exit:
            if stop_request.is_file():
                server.should_exit = True
                return
            time.sleep(0.25)

    threading.Thread(target=watch_for_stop, name="user-demo-stop-watch", daemon=True).start()
    server.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
