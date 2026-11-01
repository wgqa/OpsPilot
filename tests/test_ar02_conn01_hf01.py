"""Free-only regression tests for AR-02-CONN-01-HF-01 probe isolation."""

from __future__ import annotations

import asyncio
import importlib.util
import sys
from pathlib import Path

import pytest


PROBE_PATH = (
    Path(__file__).resolve().parents[1]
    / "docs"
    / "evidence"
    / "ar-02"
    / "connect-01"
    / "probe_once.py"
)


def load_probe():
    name = "opspilot_ar02_conn01_probe_once"
    spec = importlib.util.spec_from_file_location(name, PROBE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def test_offline_mock_is_explicitly_injected_into_openai_client(monkeypatch):
    import httpx2

    probe = load_probe()
    real_async_openai = probe.AsyncOpenAI
    captured = []

    def require_injected_client(*args, **kwargs):
        client = kwargs.get("http_client")
        assert isinstance(client, httpx2.AsyncClient), (
            "offline preflight tried to construct the SDK default HTTP client"
        )
        captured.append(client)
        return real_async_openai(*args, **kwargs)

    monkeypatch.setattr(probe, "AsyncOpenAI", require_injected_client)
    result = asyncio.run(probe.local_mock_success("https://api.deepseek.com/v1"))

    assert len(captured) == 1
    assert result["actual_network"] is False
    assert result["provider_requests"] == 0
    assert result["request"]["url"] == "https://api.deepseek.com/v1/chat/completions"


def test_consumed_send_once_authorization_is_hard_stopped_without_marker_or_ledger(
    monkeypatch, tmp_path
):
    probe = load_probe()
    # Simulate a fresh copy with no repository STOP file; the spent authorization
    # must not be restored by copying or deleting local files.
    monkeypatch.setattr(probe, "__file__", str(tmp_path / "probe_once.py"))

    def config_read_is_forbidden(*_args, **_kwargs):
        pytest.fail("send-once must stop before reading credentials/configuration")

    monkeypatch.setattr(probe, "read_config", config_read_is_forbidden)
    ledger = tmp_path / "fresh" / "single-use.sqlite3"
    trace = tmp_path / "fresh" / "trace.json"
    result = tmp_path / "fresh" / "result.json"

    with pytest.raises(RuntimeError, match="HF01_NO_REPLAY"):
        asyncio.run(probe.send_once(tmp_path / ".env", ledger, trace, result))
