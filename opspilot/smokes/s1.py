from __future__ import annotations

import json
import tempfile
import threading
from pathlib import Path

from opspilot.domain.api import make_server
from opspilot.domain.client import probe_orders
from opspilot.domain.database import connect, reset_fixture
from opspilot.domain.test_fixtures import fixture_only_switch_ref


def emit(event: str, **fields: object) -> None:
    print(json.dumps({"event": event, **fields}, sort_keys=True, default=str))


def run_case(db_path: Path, scenario: str) -> tuple[dict[str, object], dict[str, object], list[str]]:
    reset_fixture(db_path, scenario)  # type: ignore[arg-type]
    server = make_server(db_path, "tenant-a", "127.0.0.1", 0)
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
    thread.start()
    host, port = server.server_address
    base_url = f"http://{host}:{port}"
    try:
        before = probe_orders(db_path, base_url)
        new_config_version = fixture_only_switch_ref(
            db_path, "tenant-a", "integration-a", "cred-v2"
        )
        after = probe_orders(db_path, base_url)
    finally:
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()
    with connect(db_path) as connection:
        event_codes = [
            str(row["result_code"])
            for row in connection.execute(
                "SELECT result_code FROM auth_events ORDER BY event_id"
            ).fetchall()
        ]
    if before.integration_id != after.integration_id or before.principal_id != after.principal_id or before.route != after.route:
        raise AssertionError("Caller identity or business route changed across the probe.")
    after_summary = after.public_dict()
    after_summary["fixture_config_version"] = new_config_version
    return before.public_dict(), after_summary, event_codes


def run_smoke() -> int:
    with tempfile.TemporaryDirectory(prefix="opspilot-s1-") as temporary:
        temp_path = Path(temporary)
        pos_before, pos_after, pos_events = run_case(temp_path / "pos.sqlite3", "S1_POS")
        emit("s1_pos_business_api", before=pos_before, after=pos_after, auth_events=pos_events)
        if pos_before["status_code"] != 401 or pos_after["status_code"] != 200:
            emit("s1_pos_failed")
            return 1
        if pos_after["body"].get("order_id") != "demo-order" or pos_after["body"].get("status") != "CONFIRMED":
            emit("s1_pos_business_assertion_failed")
            return 1

        disabled_before, disabled_after, disabled_events = run_case(
            temp_path / "disabled.sqlite3", "S1_DISABLED"
        )
        emit(
            "s1_disabled_negative",
            before=disabled_before,
            after=disabled_after,
            auth_events=disabled_events,
        )
        if disabled_before["status_code"] != 401 or disabled_after["status_code"] != 401:
            emit("s1_disabled_failed")
            return 1
        if disabled_after["body"].get("order_id") is not None:
            emit("s1_disabled_business_assertion_failed")
            return 1
        emit("s1_smoke_pass")
        return 0


if __name__ == "__main__":
    raise SystemExit(run_smoke())
