"""Isolated local server for AR-03-WEB-01 browser acceptance.

Replay mode never calls a model. Fixture mode injects the existing deterministic
AR-02/AR-03 integration fixture and still routes tools through the real Worker,
MCP and Domain path. This is not evidence of model autonomy.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("replay-a", "replay-b", "replay-revoked", "fixture"), required=True)
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--port", type=int, default=8173)
    parser.add_argument("--evidence", type=Path, required=True)
    args = parser.parse_args()
    args.evidence.mkdir(parents=True, exist_ok=True)
    args.db.parent.mkdir(parents=True, exist_ok=True)

    local_password = os.environ.get("AR03_WEB_LOCAL_PASSWORD")
    if not local_password:
        raise RuntimeError("AR03_WEB_LOCAL_PASSWORD is required for the local demo login")

    # These explicit values defeat any optional local .env configuration. The
    # injected factories below cannot construct a real Provider client.
    os.environ["OPSPILOT_ASSISTANT_PROVIDER_ENABLED"] = "0"
    os.environ["OPSPILOT_ASSISTANT_EXPERIMENT_ID"] = ""
    os.environ["OPSPILOT_MODEL_API_KEY"] = ""
    os.environ["OPSPILOT_WEB_ORIGIN"] = "http://127.0.0.1:5178"

    fixture_setup = None
    model = None
    factory_calls = 0
    if args.mode == "fixture":
        from opspilot.domain.database import reset_fixture
        from opspilot.domain.s3 import prepare_s3_fixture

        reset_fixture(args.db, "S1_POS")
        fixture_setup = prepare_s3_fixture(
            args.db, "DELIVERED_PENDING", order_id="ar03-order", contract_version=2,
        )
        from test_ar02_ar03_integration_01 import IntegrationFixtureModel

        model = IntegrationFixtureModel(mode="bound", receiver_state="QUEUED")
    else:
        # Refuse to replay from a snapshot that could cause worker recovery to
        # dispatch another task. Only already-terminal Runs are admissible.
        import sqlite3

        uri = f"file:{args.db.resolve().as_posix()}?mode=ro&immutable=1"
        with sqlite3.connect(uri, uri=True) as connection:
            active = connection.execute(
                "SELECT run_id,status FROM task_runs "
                "WHERE status NOT IN ('SUCCEEDED','FAILED','BLOCKED','CANCELLED')"
            ).fetchall()
            if active:
                raise RuntimeError(f"REPLAY_REFUSED_NONTERMINAL_RUNS:{active!r}")

    from opspilot.web.app import create_app

    def model_factory():
        nonlocal factory_calls
        factory_calls += 1
        if args.mode != "fixture":
            raise RuntimeError("AR03_WEB_REPLAY_PROVIDER_HARD_DISABLED")
        return model

    app = create_app(
        db_path=args.db,
        checkpoint_db_path=args.checkpoint,
        start_worker=True,
        credentials={"support-a": local_password},
        expected_origin="http://127.0.0.1:5178",
        assistant_model_factory=model_factory,
    )

    start = {
        "mode": args.mode,
        "database_paths": "local-only; omitted from published trace",
        "domain_sha256_before_server": sha256(args.db),
        "checkpoint_sha256_before_server": sha256(args.checkpoint) if args.checkpoint.exists() else None,
        "provider_enabled": False,
        "provider_api_key_present": False,
        "provider_factory_behavior": "raises_before_any_provider_client_in_replay; returns_existing_deterministic_fixture_in_fixture_mode",
        "fixture_prepared": fixture_setup is not None,
    }
    (args.evidence / "server-start.json").write_text(
        json.dumps(start, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
    )

    import uvicorn

    try:
        uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")
    finally:
        finish = {
            "mode": args.mode,
            "model_factory_calls": factory_calls,
            "real_provider_http_requests": 0,
            "fixture_offered_tool_names": getattr(model, "offered_tool_names", None),
        }
        (args.evidence / "server-finish.json").write_text(
            json.dumps(finish, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
