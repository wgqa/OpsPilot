from __future__ import annotations

import argparse
import os

import uvicorn

from opspilot.web.app import create_app


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the single-instance local OpsPilot Web API.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--workers", type=int, default=1)
    args = parser.parse_args()
    if args.host != "127.0.0.1":
        parser.error("The local demo binds only to 127.0.0.1; do not expose it to a network.")
    if not 1 <= args.port <= 65535:
        parser.error("Port must be between 1 and 65535.")
    if args.workers != 1:
        parser.error("OpsPilot local execution requires exactly one Uvicorn worker process.")
    expected_origin = os.environ.get("OPSPILOT_WEB_ORIGIN", f"http://{args.host}:{args.port}")
    app = create_app(expected_origin=expected_origin)
    uvicorn.run(app, host=args.host, port=args.port, workers=1, reload=False, log_level="info")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
