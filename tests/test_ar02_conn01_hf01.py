"""Free-only regression tests for AR-02-CONN-01-HF-01 probe isolation."""

from __future__ import annotations

import asyncio
import importlib.util
import json
import shutil
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
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


def clear_proxy_environment(monkeypatch):
    for name in (
        "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY",
        "http_proxy", "https_proxy", "all_proxy", "no_proxy",
    ):
        monkeypatch.delenv(name, raising=False)


def test_offline_mock_is_explicitly_injected_into_openai_client(monkeypatch):
    import httpx2

    clear_proxy_environment(monkeypatch)
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
    assert result["request"]["method"] == "POST"
    assert result["request"]["body"]["model"] == "deepseek-flash"
    assert result["request"]["body"]["thinking"] == {"type": "disabled"}
    assert result["request"]["body"]["max_tokens"] == 64
    assert "tools" not in result["request"]["body"]
    assert "tool_choice" not in result["request"]["body"]
    assert result["request"]["authorization_present"] is True
    auth_header = next(
        value
        for name, value in result["request"]["headers_redacted"].items()
        if name.lower() == "authorization"
    )
    assert auth_header == "[REDACTED]"


@pytest.mark.parametrize(
    ("base_url", "expected"),
    [
        ("https://api.deepseek.com", "https://api.deepseek.com/chat/completions"),
        ("https://api.deepseek.com/v1", "https://api.deepseek.com/v1/chat/completions"),
    ],
)
def test_offline_mock_respects_base_path_without_external_requests(monkeypatch, base_url, expected):
    clear_proxy_environment(monkeypatch)
    probe = load_probe()
    result = asyncio.run(probe.local_mock_success(base_url))

    assert result["request"]["url"] == expected
    assert result["sdk"]["explicit_http_client_injected"] is True
    assert result["sdk"]["transport_type"] == "httpx2.MockTransport"
    assert result["sdk"]["trust_env"] is False
    assert result["provider_requests"] == 0


def test_missing_or_wrong_transport_fails_before_sdk_client_creation(monkeypatch):
    import httpx2

    clear_proxy_environment(monkeypatch)
    probe = load_probe()
    called = []

    def sdk_must_not_be_created(*_args, **_kwargs):
        called.append(True)
        raise AssertionError("SDK client creation was reached without a MockTransport")

    class ExtendedMockTransport(httpx2.MockTransport):
        pass

    monkeypatch.setattr(probe, "AsyncOpenAI", sdk_must_not_be_created)
    with pytest.raises(RuntimeError, match="HF01_NO_MOCK_TRANSPORT"):
        asyncio.run(probe.create_offline_client("https://api.deepseek.com/v1", None))
    with pytest.raises(RuntimeError, match="HF01_NO_MOCK_TRANSPORT"):
        asyncio.run(
            probe.create_offline_client(
                "https://api.deepseek.com/v1", httpx2.ASGITransport(app=None)
            )
        )
    with pytest.raises(RuntimeError, match="HF01_NO_MOCK_TRANSPORT"):
        asyncio.run(
            probe.create_offline_client(
                "https://api.deepseek.com/v1", ExtendedMockTransport(lambda _: None)
            )
        )
    assert called == []


def test_endpoint_and_proxy_mismatch_fail_before_sdk_client_creation(monkeypatch):
    import httpx2

    clear_proxy_environment(monkeypatch)
    probe = load_probe()
    called = []

    def sdk_must_not_be_created(*_args, **_kwargs):
        called.append(True)
        raise AssertionError("SDK client creation was reached after a failed precheck")

    monkeypatch.setattr(probe, "AsyncOpenAI", sdk_must_not_be_created)
    with pytest.raises(ValueError, match="allowlist"):
        asyncio.run(
            probe.create_offline_client(
                "https://api.deepseek.com.evil.invalid/v1", httpx2.MockTransport(lambda _: None)
            )
        )
    monkeypatch.setenv("HTTPS_PROXY", "https://user:secret@proxy.invalid:8443")
    with pytest.raises(RuntimeError, match="proxy environment") as error:
        asyncio.run(
            probe.create_offline_client(
                "https://api.deepseek.com/v1", httpx2.MockTransport(lambda _: None)
            )
        )
    assert called == []
    assert "secret" not in str(error.value)


def test_sdk_version_mismatch_fails_before_sdk_client_creation(monkeypatch):
    import httpx2

    clear_proxy_environment(monkeypatch)
    probe = load_probe()
    created = []
    monkeypatch.setattr(probe.openai, "__version__", "0.0-test-mismatch")
    monkeypatch.setattr(
        probe,
        "AsyncOpenAI",
        lambda *_args, **_kwargs: created.append(True),
    )

    with pytest.raises(RuntimeError, match="OpenAI SDK version mismatch"):
        asyncio.run(
            probe.create_offline_client(
                "https://api.deepseek.com/v1", httpx2.MockTransport(lambda _: None)
            )
        )
    assert created == []


def test_local_connect_error_is_captured_and_has_no_http_response(monkeypatch):
    clear_proxy_environment(monkeypatch)
    probe = load_probe()
    result = asyncio.run(probe.local_mock_connect_error("https://api.deepseek.com/v1"))

    assert result["status"] == "PASS"
    assert result["request"]["url"] == "https://api.deepseek.com/v1/chat/completions"
    assert "ConnectError" in result["exception_type_chain"]
    assert result["http_response"] is None
    assert result["http_responses"] == 0
    assert result["provider_requests"] == 0


def test_consumed_send_once_authorization_is_hard_stopped_without_marker_or_ledger(
    monkeypatch, tmp_path
):
    probe = load_probe()
    # Simulate a fresh copy with no repository STOP file; the spent authorization
    # must not be restored by copying or deleting local files.
    monkeypatch.setattr(probe, "__file__", str(tmp_path / "probe_once.py"))

    def config_read_is_forbidden(*_args, **_kwargs):
        pytest.fail("send-once must stop before reading credentials/configuration")

    monkeypatch.setattr(probe, "read_config", config_read_is_forbidden, raising=False)
    monkeypatch.setattr(
        probe,
        "AsyncOpenAI",
        lambda *_args, **_kwargs: pytest.fail("send-once must not create an SDK client"),
    )
    ledger = tmp_path / "fresh" / "single-use.sqlite3"
    trace = tmp_path / "fresh" / "trace.json"
    result = tmp_path / "fresh" / "result.json"

    with pytest.raises(RuntimeError, match="HF01_NO_REPLAY"):
        probe.send_once(tmp_path / ".env", ledger, trace, result)
    assert not ledger.exists()
    assert not trace.exists()
    assert not result.exists()


def test_cli_send_once_is_blocked_without_arguments_or_local_state(capsys):
    probe = load_probe()
    assert probe.main(["send-once"]) == 3
    output = json.loads(capsys.readouterr().out)
    assert output["status"] == "BLOCKED"
    assert output["provider_requests"] == 0
    assert "HF01_NO_REPLAY" in output["reason"]


def test_send_once_stays_blocked_with_copied_marker_and_existing_local_files(
    monkeypatch, tmp_path
):
    probe = load_probe()
    fake_checkout = tmp_path / "copied-checkout"
    trace_dir = fake_checkout / "TRACE"
    trace_dir.mkdir(parents=True)
    (trace_dir / "STOPPED_NO_RETRY.json").write_text(
        '{"status":"historical evidence only"}', encoding="utf-8"
    )
    ledger = fake_checkout / "ledger.sqlite3"
    ledger.write_bytes(b"not-opened")
    trace = fake_checkout / "trace.json"
    trace.write_text("prior trace", encoding="utf-8")
    result = fake_checkout / "result.json"
    result.write_text("prior result", encoding="utf-8")
    monkeypatch.setattr(probe, "__file__", str(fake_checkout / "probe_once.py"))

    with pytest.raises(RuntimeError, match="HF01_NO_REPLAY"):
        probe.send_once(fake_checkout / ".env", ledger, trace, result)

    assert trace.read_text(encoding="utf-8") == "prior trace"
    assert result.read_text(encoding="utf-8") == "prior result"
    assert ledger.read_bytes() == b"not-opened"


def test_probe_module_has_no_network_diagnostic_entrypoint():
    source = PROBE_PATH.read_text(encoding="utf-8")
    assert "import socket" not in source
    assert "import ssl" not in source
    assert "network-diagnostic" not in source
    assert "OPSPILOT_MODEL_API_KEY" not in source
    assert "load_dotenv" not in source


def test_preflight_ignores_user_provider_key_and_only_uses_local_mock(monkeypatch, tmp_path):
    clear_proxy_environment(monkeypatch)
    probe = load_probe()
    monkeypatch.setenv("OPSPILOT_MODEL_API_KEY", "must-not-be-read-or-emitted")
    output_path = tmp_path / "preflight.json"
    assert probe.main([
        "preflight",
        "--base-url",
        "https://api.deepseek.com",
        "--out",
        str(output_path),
    ]) == 0
    serialized = output_path.read_text(encoding="utf-8")
    assert "must-not-be-read-or-emitted" not in serialized
    assert json.loads(serialized)["provider_requests"] == 0


def test_simulated_ledger_replay_unknown_copy_and_digest_conflict(tmp_path):
    probe = load_probe()
    ledger = tmp_path / "ledger.sqlite3"

    # A crash before reservation leaves no permit.
    assert probe.ledger_snapshot(ledger) == []
    probe.simulate_reserve_once(ledger, "AUTH-LOCAL-1", "digest-a")
    assert probe.ledger_snapshot(ledger)[0]["state"] == "ATTEMPT_RESERVED"

    with pytest.raises(FileExistsError):
        probe.simulate_reserve_once(ledger, "AUTH-LOCAL-1", "digest-a")
    with pytest.raises(ValueError, match="different request digest"):
        probe.simulate_reserve_once(ledger, "AUTH-LOCAL-1", "digest-b")

    copied = tmp_path / "copied" / "ledger.sqlite3"
    copied.parent.mkdir()
    shutil.copy2(ledger, copied)
    with pytest.raises(FileExistsError):
        probe.simulate_reserve_once(copied, "AUTH-LOCAL-1", "digest-a")

    # A crash after reserve and an UNKNOWN result both remain consumed.
    probe.simulate_mark_unknown(ledger, "AUTH-LOCAL-1")
    assert probe.ledger_snapshot(ledger)[0]["state"] == "UNKNOWN"
    with pytest.raises(FileExistsError):
        probe.simulate_reserve_once(ledger, "AUTH-LOCAL-1", "digest-a")


def test_threads_cannot_reserve_same_simulated_permit(tmp_path):
    probe = load_probe()
    ledger = tmp_path / "thread-race.sqlite3"

    def reserve():
        try:
            probe.simulate_reserve_once(ledger, "AUTH-THREAD", "digest-thread")
            return "RESERVED"
        except FileExistsError:
            return "REPLAY_BLOCKED"

    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(lambda _index: reserve(), range(6)))

    assert results.count("RESERVED") == 1
    assert results.count("REPLAY_BLOCKED") == 5
    assert len(probe.ledger_snapshot(ledger)) == 1


def _spawn_reservation_process(script, ledger, authorization_id, request_digest, barrier_dir):
    code = f"""
import importlib.util
import sys
import time
from pathlib import Path

spec = importlib.util.spec_from_file_location("hf01_probe_once", {str(script)!r})
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
ledger = Path(sys.argv[1])
authorization_id = sys.argv[2]
barrier = Path(sys.argv[3])
request_digest = sys.argv[4]
Path(str(barrier) + ".ready").touch()
deadline = time.time() + 15
while not Path(str(barrier) + ".go").exists():
    if time.time() > deadline:
        raise TimeoutError("barrier")
    time.sleep(0.01)
try:
    module.simulate_reserve_once(ledger, authorization_id, request_digest)
    print("RESERVED")
except FileExistsError:
    print("REPLAY_BLOCKED")
"""
    return subprocess.Popen(
        [
            sys.executable, "-c", code, str(ledger), authorization_id,
            str(barrier_dir), request_digest,
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def test_two_processes_cannot_reserve_same_simulated_permit(tmp_path):
    probe = load_probe()
    probe_path = PROBE_PATH
    ledger = tmp_path / "shared.sqlite3"
    barrier = tmp_path / "barrier"
    barrier.mkdir()
    first = _spawn_reservation_process(
        probe_path, ledger, "AUTH-RACE", "digest-same", barrier / "first"
    )
    second = _spawn_reservation_process(
        probe_path, ledger, "AUTH-RACE", "digest-same", barrier / "second"
    )
    try:
        ready_deadline = time.time() + 20
        while time.time() < ready_deadline:
            if (barrier / "first.ready").exists() and (barrier / "second.ready").exists():
                break
            time.sleep(0.02)
        if not (barrier / "first.ready").exists() or not (barrier / "second.ready").exists():
            out1, err1 = first.communicate(timeout=5)
            out2, err2 = second.communicate(timeout=5)
            pytest.fail(f"reservation children did not reach the barrier: {out1} {err1} / {out2} {err2}")
        (barrier / "first.go").touch()
        (barrier / "second.go").touch()
        out1, err1 = first.communicate(timeout=20)
        out2, err2 = second.communicate(timeout=20)
        assert first.returncode == 0, err1
        assert second.returncode == 0, err2
        assert sorted([out1.strip(), out2.strip()]) == ["REPLAY_BLOCKED", "RESERVED"]
        rows = probe.ledger_snapshot(ledger)
        assert len(rows) == 1
        assert rows[0]["state"] == "ATTEMPT_RESERVED"
    finally:
        for process in (first, second):
            if process.poll() is None:
                process.kill()
                process.wait()
