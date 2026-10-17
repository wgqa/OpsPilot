from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from opspilot.domain.credentials import resolve_integration_credential
from opspilot.domain.database import get_integration_info


BUSINESS_ROUTE = "/api/orders/demo-order"


@dataclass(frozen=True)
class ProbeResult:
    status_code: int
    body: dict[str, object]
    request_id: str | None
    event_id: int | None
    tenant_id: str
    integration_id: str
    principal_id: str
    route: str
    credential_ref: str
    config_version: int

    def public_dict(self) -> dict[str, object]:
        return asdict(self)


def _local_business_url(base_url: str) -> str:
    parsed = urlsplit(base_url)
    if (
        parsed.scheme != "http"
        or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}
        or parsed.path not in {"", "/"}
        or parsed.username is not None
        or parsed.password is not None
    ):
        raise ValueError("The D1 probe only accepts the fixed loopback demo API.")
    return f"{base_url.rstrip('/')}{BUSINESS_ROUTE}"


def probe_orders(
    db_path: str | Path,
    base_url: str,
    tenant_id: str = "tenant-a",
    integration_id: str = "integration-a",
) -> ProbeResult:
    integration = get_integration_info(db_path, tenant_id, integration_id)
    credential_ref = str(integration["credential_ref"])
    secret = resolve_integration_credential(db_path, tenant_id, credential_ref)
    request = Request(
        _local_business_url(base_url),
        headers={
            "Accept": "application/json",
            "Authorization": f"Bearer {secret}",
            "X-Integration-ID": integration_id,
        },
        method="GET",
    )
    status_code = 0
    response_body: dict[str, object]
    try:
        with urlopen(request, timeout=3) as response:
            status_code = response.status
            response_body = json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        status_code = error.code
        try:
            response_body = json.loads(error.read().decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            response_body = {"error": "invalid_response"}
    except URLError as error:
        raise ConnectionError("Could not connect to the loopback OpsPilot demo API.") from error
    return ProbeResult(
        status_code=status_code,
        body=response_body,
        request_id=(
            str(response_body["request_id"])
            if isinstance(response_body.get("request_id"), str)
            else None
        ),
        event_id=(
            int(response_body["event_id"])
            if isinstance(response_body.get("event_id"), int)
            else None
        ),
        tenant_id=tenant_id,
        integration_id=integration_id,
        principal_id=str(integration["principal_id"]),
        route=BUSINESS_ROUTE,
        credential_ref=credential_ref,
        config_version=int(integration["config_version"]),
    )
