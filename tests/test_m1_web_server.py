from __future__ import annotations

import sys

from opspilot.web import server


def _run_server_main(monkeypatch, *, configured_origin: str | None) -> dict[str, object]:
    captured: dict[str, object] = {}
    monkeypatch.setattr(sys, "argv", ["opspilot-server", "--host", "127.0.0.1", "--port", "8123"])
    if configured_origin is None:
        monkeypatch.delenv("OPSPILOT_WEB_ORIGIN", raising=False)
    else:
        monkeypatch.setenv("OPSPILOT_WEB_ORIGIN", configured_origin)
    monkeypatch.setattr(server, "create_app", lambda **kwargs: kwargs)
    monkeypatch.setattr(server.uvicorn, "run", lambda app, **kwargs: captured.update(app=app, **kwargs))
    assert server.main() == 0
    return captured


def test_server_uses_configured_vue_origin_for_exact_origin_guard(monkeypatch) -> None:
    captured = _run_server_main(monkeypatch, configured_origin="http://127.0.0.1:5173")

    assert captured["app"] == {"expected_origin": "http://127.0.0.1:5173"}
    assert captured["host"] == "127.0.0.1"
    assert captured["port"] == 8123
    assert captured["workers"] == 1


def test_server_defaults_origin_to_same_loopback_api_origin(monkeypatch) -> None:
    captured = _run_server_main(monkeypatch, configured_origin=None)

    assert captured["app"] == {"expected_origin": "http://127.0.0.1:8123"}
