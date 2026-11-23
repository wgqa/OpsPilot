"""Loopback-only browser fixture. Production API and Assistant, offline model transport."""
from __future__ import annotations

import argparse
import asyncio
from contextlib import asynccontextmanager, suppress
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path.cwd()))

import uvicorn
from fastapi.staticfiles import StaticFiles

from offline import BridgeWire, frozen
from opspilot.domain import task_control as tc
from opspilot.domain.database import connect, reset_fixture
from opspilot.domain.s3 import prepare_s3_fixture
from opspilot.web.app import create_app
from opspilot.web.worker import _dispatch_run


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--port", type=int, default=8875)
    args = parser.parse_args()
    args.state.mkdir(parents=True, exist_ok=False)
    args.output.mkdir(parents=True, exist_ok=True)
    frozen.configure("HYBRID")
    db, checkpoint = args.state / "domain.sqlite", args.state / "checkpoint.sqlite"
    reset_fixture(db, "S1_POS")
    prepare_s3_fixture(db, "DELIVERED_PENDING", order_id="p002-order", contract_version=2)
    epoch = tc.register_worker_owner(db, frozen.WORKER, os.getpid())
    owner = tc.trusted_identity(db, "support-a")
    wire = BridgeWire(args.output)
    # Browser review requests can overlap polling; the active transport only
    # records its request and does not use case metadata as input.
    wire.target = {"case": "browser"}
    app = create_app(
        db_path=db, start_worker=False, expected_origin=f"http://127.0.0.1:{args.port}",
        credentials={"support-a": "p002-browser-fixture"}, condition_model_factory=wire.review_factory,
    )
    app.mount("/", StaticFiles(directory="frontend/dist", html=True), name="workbench")
    original_lifespan = app.router.lifespan_context

    async def dispatch_offline():
        while True:
            with connect(db) as connection:
                row = connection.execute(
                    """SELECT r.*, a.run_id AS assistant_id FROM task_runs r
                       LEFT JOIN assistant_runs a ON a.run_id=r.run_id
                       WHERE r.status='QUEUED' ORDER BY r.created_at LIMIT 1""",
                ).fetchone()
            if row is None:
                await asyncio.sleep(0.07)
                continue
            if row["assistant_id"]:
                await _dispatch_run(db, checkpoint, frozen.WORKER, "executor-a", dict(row),
                                    epoch, assistant_model_factory=wire.factory)
            elif row["kind"] == "INVESTIGATE":
                # Exercise real formal admission/application, leaving the
                # legacy business investigation paused without a paid model.
                tc.claim_task_run(db, owner, row["run_id"])
                tc.apply_pending_critical_inputs(db, owner, row["run_id"])
                tc.finish_task_run(db, owner, row["run_id"], "WAITING_INPUT")
            else:
                raise RuntimeError("Unexpected unmocked Run in browser fixture.")

    @asynccontextmanager
    async def lifespan(current_app):
        async with original_lifespan(current_app):
            task = asyncio.create_task(dispatch_offline())
            try:
                yield
            finally:
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task

    app.router.lifespan_context = lifespan
    uvicorn.run(app, host="127.0.0.1", port=args.port, access_log=False)


if __name__ == "__main__":
    main()
