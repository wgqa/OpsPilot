"""Explicit synthetic acceptance actions through normal authenticated Web APIs.

Uses Origin, cookie sessions, CSRF and stable per-action idempotency keys. No
Domain write shortcut. Authentication material is never written to evidence.
"""
from __future__ import annotations
import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
import httpx

ROOT = Path.cwd()
BASE = Path(__file__).resolve().parent
RUNTIME = ROOT / ".runtime/m3-hf-02/journey-01"
OUT = BASE / "runs/journey-01"


def record(value):
    with (OUT / "web-commands.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps({"at": datetime.now(timezone.utc).isoformat(), "channel": "AUTHENTICATED_WEB_HTTP_API_NOT_BROWSER_CLICK", **value}, ensure_ascii=False) + "\n")


class WebClient:
    def __init__(self, actor):
        passwords = json.loads((RUNTIME / "test-passwords.json").read_text(encoding="utf-8"))
        self.actor = actor
        self.client = httpx.Client(base_url="http://127.0.0.1:8003", headers={"Origin": "http://127.0.0.1:5176"}, timeout=20)
        response = self.client.post("/api/auth/login", json={"actor_id": actor, "password": passwords[actor]})
        response.raise_for_status()
        self.client.headers["X-CSRF-Token"] = response.json()["csrf_token"]
        record({"actor": actor, "method": "POST", "path": "/api/auth/login", "http_status": response.status_code, "authentication_values_omitted": True})

    def request(self, method, path, payload=None, operation_id=None):
        if not path.startswith("/api/") or path.startswith("/api/auth/"):
            raise ValueError("Only explicit non-auth local Web API actions accepted.")
        operation = operation_id or "hf02-operation-" + str(uuid.uuid4())
        response = self.client.request(method, path, json=payload, headers={"Idempotency-Key": operation} if method != "GET" else {})
        result = response.json()
        record({"actor": self.actor, "method": method, "path": path, "operation_id": operation, "http_status": response.status_code, "request": payload, "response": result})
        if response.is_error:
            raise RuntimeError(f"Web action rejected: {response.status_code}, {result.get('error', result.get('detail', 'unknown'))}")
        return result


if __name__ == "__main__":
    actor, method, path = sys.argv[1:4]
    payload = json.loads(Path(sys.argv[4]).read_text(encoding="utf-8")) if len(sys.argv) > 4 else None
    value = WebClient(actor).request(method, path, payload)
    print(json.dumps(value, ensure_ascii=False))
