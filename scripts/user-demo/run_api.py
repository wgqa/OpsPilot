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


def request_graceful_shutdown(app, server: uvicorn.Server) -> None:
    """Signal active SSE generators before Uvicorn drains open connections."""
    app.state.shutdown_requested.set()
    server.should_exit = True


class UserDemoServer(uvicorn.Server):
    """Notify live SSE streams for both Stop-UserDemo and console signals."""

    def __init__(self, config: uvicorn.Config, app) -> None:
        self._opspilot_app = app
        super().__init__(config)

    def handle_exit(self, sig, frame) -> None:
        self._opspilot_app.state.shutdown_requested.set()
        super().handle_exit(sig, frame)


def watch_for_stop_request(stop_request: Path, app, server: uvicorn.Server) -> None:
    while not server.should_exit:
        if stop_request.is_file():
            request_graceful_shutdown(app, server)
            return
        time.sleep(0.25)


def main() -> int:
    host = "127.0.0.1"
    port = 8000
    expected_origin = os.environ.get("OPSPILOT_WEB_ORIGIN", f"http://{host}:{port}")
    app = create_app(expected_origin=expected_origin, assistant_model_factory=create_assistant_model)
    server = UserDemoServer(
        uvicorn.Config(app, host=host, port=port, workers=1, reload=False, log_level="info"), app
    )
    runtime = ROOT / ".runtime" / "user-demo"
    stop_request = runtime / "shutdown.request"

    threading.Thread(
        target=watch_for_stop_request, args=(stop_request, app, server),
        name="user-demo-stop-watch", daemon=True,
    ).start()
    server.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
