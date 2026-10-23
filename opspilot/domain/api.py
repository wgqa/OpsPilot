from __future__ import annotations

import ipaddress
import json
import secrets
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

from opspilot.domain.database import authorize_business_request, connect, initialize


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
        from opspilot.domain.s3 import ROUTE as S3_ROUTE, SERVICE as S3_SERVICE, order_http_payload
        parsed = urlsplit(self.path)
        request_path = parsed.path
        query = parse_qs(parsed.query, keep_blank_values=True)
        if request_path not in {"/api/orders/demo-order", S3_ROUTE}:
            self._respond(404, {"error": "NOT_FOUND"})
            return

        db_path = self.server.db_path  # type: ignore[attr-defined]
        tenant_id = self.server.tenant_id  # type: ignore[attr-defined]
        request_id = secrets.token_hex(8)
        integration_id = self.headers.get("X-Integration-ID", "")
        authorization = self.headers.get("Authorization", "")
        decision = authorize_business_request(
            db_path,
            tenant_id=tenant_id,
            service_id=S3_SERVICE if request_path == S3_ROUTE else "orders-demo",
            route=request_path,
            integration_id=integration_id,
            authorization=authorization,
            request_id=request_id,
        )
        authn_event_id = decision.get("authn_event_id")
        if int(decision["http_status"]) == 401:
            payload: dict[str, object] = {"error": "UNAUTHORIZED", "request_id": request_id}
            if authn_event_id is not None:
                payload.update({"event_id": authn_event_id, "authn_event_id": authn_event_id})
            self._respond(401, payload)
            return
        if int(decision["http_status"]) == 403:
            self._respond(
                403,
                {
                    "error": "FORBIDDEN",
                    "request_id": request_id,
                    "authn_event_id": authn_event_id,
                    "authz_event_id": decision["authz_event_id"],
                },
            )
            return
        if request_path == S3_ROUTE:
            requested = query.get("order_id", ["async-order"])
            order_id = requested[0] if len(requested) == 1 else ""
            if not order_id or len(order_id) > 100:
                self._respond(404, {"error": "ORDER_NOT_FOUND"})
                return
            payload = order_http_payload(db_path, tenant_id, integration_id, request_id, authn_event_id, order_id)
            self._respond(200 if payload else 404, payload or {"error": "ORDER_NOT_FOUND"})
            return
        try:
            with connect(db_path) as connection:
                order = connection.execute(
                    "SELECT order_id, status FROM orders WHERE tenant_id = ? AND order_id = ?",
                    (tenant_id, "demo-order"),
                ).fetchone()
            if order is None:
                self._respond(
                    404,
                    {
                        "error": "NOT_FOUND",
                        "request_id": request_id,
                        "authn_event_id": authn_event_id,
                        "authz_event_id": decision["authz_event_id"],
                    },
                )
                return
            self._respond(
                200,
                {
                    "order_id": str(order["order_id"]),
                    "status": str(order["status"]),
                    "request_id": request_id,
                    "event_id": authn_event_id,
                    "authn_event_id": authn_event_id,
                    "authz_event_id": decision["authz_event_id"],
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
