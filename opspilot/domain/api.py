from __future__ import annotations

import hmac
import ipaddress
import json
import secrets
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from opspilot.domain.database import (
    get_credential_secret,
    get_service_info,
    initialize,
    record_auth_event,
)


class DemoAPIHandler(BaseHTTPRequestHandler):
    server_version = "OpsPilotDemo/1.0"
    sys_version = ""

    def log_message(self, format: str, *args: Any) -> None:
        # Default HTTP server logging is suppressed to keep request headers/secrets out of logs.
        return

    def _respond(self, status: int, payload: dict[str, object]) -> None:
        raw = json.dumps(payload, sort_keys=True).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self) -> None:
        if self.path != "/api/orders/demo-order":
            self._respond(404, {"error": "NOT_FOUND"})
            return

        db_path = self.server.db_path  # type: ignore[attr-defined]
        tenant_id = self.server.tenant_id  # type: ignore[attr-defined]
        request_id = secrets.token_hex(8)
        integration_id = self.headers.get("X-Integration-ID", "")
        authorization = self.headers.get("Authorization", "")
        try:
            service = get_service_info(db_path, tenant_id, "orders-demo")
            if integration_id != service["integration_id"]:
                raise LookupError("Integration is outside the registered service binding.")
            expected_secret = get_credential_secret(
                db_path, tenant_id, str(service["accepted_credential_ref"])
            )
            supplied_secret = authorization.removeprefix("Bearer ")
            authorized = (
                authorization.startswith("Bearer ")
                and hmac.compare_digest(supplied_secret, expected_secret)
                and service["principal_status"] == "ENABLED"
            )
            result_code = "AUTH_ACCEPTED" if authorized else "AUTH_REJECTED"
            event_id = record_auth_event(
                db_path,
                tenant_id,
                str(service["integration_id"]),
                str(service["principal_id"]),
                "orders-demo",
                str(service["route"]),
                result_code,
            )
            if not authorized:
                self._respond(
                    401,
                    {"error": "UNAUTHORIZED", "request_id": request_id, "event_id": event_id},
                )
                return
            from opspilot.domain.database import connect

            with connect(db_path) as connection:
                order = connection.execute(
                    "SELECT order_id, status FROM orders WHERE tenant_id = ? AND order_id = ?",
                    (tenant_id, "demo-order"),
                ).fetchone()
            if order is None:
                self._respond(
                    404,
                    {"error": "ORDER_NOT_FOUND", "request_id": request_id, "event_id": event_id},
                )
                return
            self._respond(
                200,
                {
                    "order_id": str(order["order_id"]),
                    "status": str(order["status"]),
                    "request_id": request_id,
                    "event_id": event_id,
                },
            )
        except LookupError:
            # Do not reveal whether a tenant, principal, or integration exists.
            self._respond(401, {"error": "UNAUTHORIZED", "request_id": request_id})


class DemoHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, server_address: tuple[str, int], db_path: Path, tenant_id: str):
        super().__init__(server_address, DemoAPIHandler)
        self.db_path = db_path
        self.tenant_id = tenant_id


def make_server(
    db_path: str | Path,
    tenant_id: str = "tenant-a",
    host: str = "127.0.0.1",
    port: int = 8000,
) -> DemoHTTPServer:
    if not ipaddress.ip_address(host).is_loopback:
        raise ValueError("D1 demo API must bind to a loopback address.")
    resolved_path = Path(db_path).resolve()
    initialize(resolved_path)
    return DemoHTTPServer((host, port), resolved_path, tenant_id)


def main() -> None:
    from opspilot.config import DEFAULT_DB_PATH, load_local_environment

    load_local_environment()
    import argparse

    parser = argparse.ArgumentParser(description="Serve the local OpsPilot business API.")
    parser.add_argument("--db", default=str(DEFAULT_DB_PATH))
    parser.add_argument("--tenant", default="tenant-a")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    server = make_server(args.db, args.tenant, args.host, args.port)
    print(json.dumps({"event": "api_listening", "host": args.host, "port": args.port, "tenant_id": args.tenant}))
    try:
        server.serve_forever(poll_interval=0.2)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
