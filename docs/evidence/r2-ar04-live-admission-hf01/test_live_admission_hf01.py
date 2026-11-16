from __future__ import annotations

import asyncio
import gzip
import json
import sys
from pathlib import Path

import httpx
import pytest

EVIDENCE_DIR = Path(__file__).resolve().parent
ROOT = EVIDENCE_DIR.parents[2]
GATE_DIR = ROOT / "docs/evidence/r2-ar04-remaining-live-gate-01"
ABC_DIR = ROOT / "docs/evidence/abc-live-env-unblock-01"
for item in (str(ROOT), str(GATE_DIR), str(ABC_DIR), str(EVIDENCE_DIR)):
    if item not in sys.path:
        sys.path.insert(0, item)

import run_abc_eval as abc
import run_remaining_live_gate as gate


def _wire_payload() -> dict:
    return {
        "model": abc.MODEL,
        "thinking": {"type": "disabled"},
        "temperature": 0,
        "stream": False,
        "tool_choice": "none",
        "max_tokens": 512,
        "tools": [],
        "messages": [{"role": "user", "content": "MOCK_ONLY"}],
    }


def _validate(endpoint: str, request_url: str, *, host_header: str | None = None) -> tuple[dict, str]:
    payload = _wire_payload()
    headers = {"content-type": "application/json"}
    if host_header is not None:
        headers["host"] = host_header
    body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    request = httpx.Request("POST", request_url, headers=headers, content=body)
    transport = abc.BudgetedAsyncTransport(
        inner=httpx.MockTransport(lambda _request: (_ for _ in ()).throw(AssertionError("must not send"))),
        ledger=object(), case_id="Q02-B", mode="MOCK", trace_path=Path("unused.jsonl.gz"),
        expected_endpoint=endpoint,
    )
    return transport._validate_request(request, body)


@pytest.mark.parametrize(("endpoint", "request_url"), [
    ("https://api.deepseek.com", "https://api.deepseek.com/chat/completions"),
    ("https://api.deepseek.com/", "https://api.deepseek.com/chat/completions"),
    ("https://api.deepseek.com/v1", "https://api.deepseek.com/v1/chat/completions"),
    ("https://api.deepseek.com/v1/", "https://api.deepseek.com/v1/chat/completions"),
    ("https://api.deepseek.com:443/v1", "https://api.deepseek.com:443/v1/chat/completions"),
])
def test_provider_adapter_accepts_only_configured_root_or_v1_route(endpoint, request_url):
    payload, purpose = _validate(endpoint, request_url)
    assert payload["model"] == "deepseek-flash"
    assert purpose == "ANSWER"


@pytest.mark.parametrize(("endpoint", "request_url", "host_header"), [
    ("https://api.deepseek.com/v1", "https://api.deepseek.com/chat/completions", None),
    ("https://api.deepseek.com/v1", "https://api.deepseek.com/v2/chat/completions", None),
    ("https://api.deepseek.com/v1", "https://api.deepseek.com/v1/chat/completions/", None),
    ("https://api.deepseek.com/v1", "https://api.deepseek.com/v1%2fchat/completions", None),
    ("https://api.deepseek.com/v1", "https://api.deepseek.com/v1/chat%2fcompletions", None),
    ("https://api.deepseek.com/v1", "https://api.deepseek.com/v1/chat/completions?next=https://evil.test", None),
    ("https://api.deepseek.com/v1", "https://api.deepseek.com.attacker.test/v1/chat/completions", None),
    ("https://api.deepseek.com/v1", "https://api.deepseek.com:444/v1/chat/completions", None),
    ("https://api.deepseek.com/v1", "http://api.deepseek.com/v1/chat/completions", None),
    ("https://api.deepseek.com/v1", "https://user@api.deepseek.com/v1/chat/completions", None),
    ("https://api.deepseek.com/v1", "https://api.deepseek.com/v1/chat/completions#fragment", None),
    ("https://api.deepseek.com/v1", "https://api.deepseek.com/v1/chat/completions", "evil.test"),
    ("https://api.deepseek.com/v1?redirect=https://evil.test", "https://api.deepseek.com/v1/chat/completions", None),
    ("https://api.deepseek.com/private", "https://api.deepseek.com/private/chat/completions", None),
])
def test_provider_adapter_rejects_endpoint_path_and_authority_bypasses(endpoint, request_url, host_header):
    with pytest.raises(abc.RunnerStop, match="PROVIDER_ENDPOINT_OR_METHOD_MISMATCH"):
        _validate(endpoint, request_url, host_header=host_header)


@pytest.mark.parametrize(("base_url", "expected_path"), [
    ("https://api.deepseek.com", "/chat/completions"),
    ("https://api.deepseek.com/v1", "/v1/chat/completions"),
])
def test_openai_client_builds_the_guarded_path_from_configured_base(base_url, expected_path):
    from openai import AsyncOpenAI

    seen: list[httpx.Request] = []

    async def respond(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={
            "id": "mock-path-confirmation", "object": "chat.completion", "created": 1,
            "model": abc.MODEL,
            "choices": [{"index": 0, "message": {"role": "assistant", "content": "MOCK_ONLY"},
                         "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        })

    async def call() -> None:
        client_http = httpx.AsyncClient(transport=httpx.MockTransport(respond), trust_env=False)
        client = AsyncOpenAI(api_key="fixture-only", base_url=base_url, http_client=client_http, max_retries=0)
        try:
            await client.chat.completions.create(
                model=abc.MODEL, messages=[{"role": "user", "content": "MOCK_ONLY"}], max_tokens=1,
            )
        finally:
            await client.close()

    asyncio.run(call())
    assert len(seen) == 1
    assert seen[0].url.path == expected_path
    assert abc._request_matches_provider_endpoint(seen[0], base_url)


def test_provider_adapter_rejects_non_post_before_budget_or_inner_send():
    payload = _wire_payload()
    body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    request = httpx.Request("GET", "https://api.deepseek.com/v1/chat/completions", content=body)
    transport = abc.BudgetedAsyncTransport(
        inner=httpx.MockTransport(lambda _request: (_ for _ in ()).throw(AssertionError("must not send"))),
        ledger=object(), case_id="Q02-B", mode="MOCK", trace_path=Path("unused.jsonl.gz"),
        expected_endpoint="https://api.deepseek.com/v1",
    )
    with pytest.raises(abc.RunnerStop, match="PROVIDER_ENDPOINT_OR_METHOD_MISMATCH"):
        transport._validate_request(request, body)


def test_provider_redirect_is_rejected_before_httpx_can_follow_it(tmp_path: Path):
    payload = _wire_payload()
    body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    ledger = abc.GlobalBudgetLedger.create(
        tmp_path / "redirect-ledger.json", execution_id="redirect-block", mode="MOCK",
        hard_cap_usd_micro=gate.HARD_CAP_USD_MICRO, request_limit=6,
    )
    inner_calls: list[str] = []

    def respond(request: httpx.Request) -> httpx.Response:
        inner_calls.append(str(request.url))
        return httpx.Response(302, headers={"location": "https://evil.example/collect"})

    transport = abc.BudgetedAsyncTransport(
        inner=httpx.MockTransport(respond), ledger=ledger, case_id="Q02-B", mode="MOCK",
        trace_path=tmp_path / "redirect-trace.jsonl.gz", expected_endpoint="https://api.deepseek.com/v1",
    )

    async def send() -> None:
        client = httpx.AsyncClient(transport=transport, trust_env=False, follow_redirects=True)
        try:
            await client.post("https://api.deepseek.com/v1/chat/completions", content=body,
                              headers={"content-type": "application/json"})
        finally:
            await client.aclose()

    with pytest.raises(abc.RunnerStop, match="PROVIDER_REDIRECT_BLOCKED"):
        asyncio.run(send())
    assert inner_calls == ["https://api.deepseek.com/v1/chat/completions"]
    assert ledger.state["provider_requests_started"] == 1
    assert ledger.state["stop_reason"] == "PROVIDER_REDIRECT_BLOCKED"


@pytest.mark.parametrize(("response_body", "finish_reason", "expected_stop"), [
    (b"not-json", None, "PROVIDER_RESPONSE_INVALID"),
    (json.dumps({"id": "mock-invalid-choices", "model": abc.MODEL,
                 "choices": [], "usage": {"prompt_tokens": 1, "completion_tokens": 1,
                                           "total_tokens": 2}}).encode(), None, "PROVIDER_RESPONSE_INVALID"),
    (json.dumps({"id": "mock-length", "model": abc.MODEL,
                 "choices": [{"index": 0, "message": {"role": "assistant", "content": "partial"},
                             "finish_reason": "length"}],
                 "usage": {"prompt_tokens": 1, "completion_tokens": 512,
                           "total_tokens": 513}}).encode(), "length", "PROVIDER_OUTPUT_NOT_COMPLETE"),
])
def test_nonconforming_response_is_recorded_then_rejected_before_client_receives_it(
    tmp_path: Path, response_body: bytes, finish_reason: str | None, expected_stop: str,
):
    payload = _wire_payload()
    payload["max_tokens"] = 512
    body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    ledger = abc.GlobalBudgetLedger.create(
        tmp_path / "ledger.json", execution_id="invalid-response", mode="MOCK",
        hard_cap_usd_micro=gate.HARD_CAP_USD_MICRO, request_limit=6,
    )
    inner_calls = 0

    def respond(request: httpx.Request) -> httpx.Response:
        nonlocal inner_calls
        inner_calls += 1
        return httpx.Response(200, headers={"content-type": "application/json"}, content=response_body)

    transport = abc.BudgetedAsyncTransport(
        inner=httpx.MockTransport(respond), ledger=ledger, case_id="Q02-B", mode="MOCK",
        trace_path=tmp_path / "trace.jsonl.gz", expected_endpoint="https://api.deepseek.com/v1",
    )
    async def send() -> None:
        client = httpx.AsyncClient(transport=transport, trust_env=False)
        try:
            await client.post("https://api.deepseek.com/v1/chat/completions", content=body,
                              headers={"content-type": "application/json"})
        finally:
            await client.aclose()

    with pytest.raises(abc.RunnerStop, match=expected_stop):
        asyncio.run(send())
    assert inner_calls == 1
    assert ledger.state["stop_reason"] == expected_stop
    assert ledger.state["provider_requests_started"] == 1
    slot = next(row for row in ledger.state["slots"] if row["logical_id"] == "Q02-B:ANSWER:1")
    assert slot["request_digest"]
    if expected_stop == "PROVIDER_RESPONSE_INVALID" and response_body == b"not-json":
        assert slot["status"] == "USAGE_UNKNOWN"
        assert slot["error"] == "RESPONSE_BODY_INVALID"
    else:
        assert slot["settled_usd_micro"] is not None
        assert slot["finish_reason"] == finish_reason


@pytest.mark.parametrize("finish_reason", ["tool_calls", "stop"])
def test_full_assistant_path_rejects_tool_calls_before_dispatch_or_answer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, finish_reason: str,
):
    from opspilot.domain.context_engineering import estimate_messages_tokens, estimate_text_tokens
    from opspilot.domain.chat import get_chat_manifest
    from opspilot.domain.database import connect
    import opspilot.assistant as assistant_module

    assistant_events: list[dict] = []
    original_run_assistant = assistant_module.run_assistant

    async def capture_trace(*args, **kwargs):
        original_trace = kwargs.get("trace")

        def trace(event: str, **fields) -> None:
            assistant_events.append({"event": event, **fields})
            if original_trace is not None:
                original_trace(event, **fields)

        kwargs["trace"] = trace
        return await original_run_assistant(*args, **kwargs)

    monkeypatch.setattr(assistant_module, "run_assistant", capture_trace)

    with gate._task_contract():
        legacy, task_abc, *_ = gate.v2.build_runner()
        history, questions, history_digest, _questions_digest = task_abc.load_frozen_inputs()
        config = task_abc._mock_config()
        config["endpoint"] = "https://api.deepseek.com/v1"
        question = questions["Q02"]
        case_id = "Q02-B"
        setup = task_abc._setup_harness()
        ledger = task_abc.GlobalBudgetLedger.create(
            tmp_path / f"ledger-{finish_reason}.json", execution_id=f"hf01-{finish_reason}",
            mode="MOCK", hard_cap_usd_micro=gate.HARD_CAP_USD_MICRO, request_limit=gate.REQUEST_LIMIT,
        )
        sent: list[dict] = []
        case_db = tmp_path / f"case-{finish_reason}" / "domain.sqlite3"

        def respond(request: httpx.Request) -> httpx.Response:
            payload = json.loads(request.content.decode("utf-8"))
            systems = "\n".join(
                str(item.get("content", "")) for item in payload.get("messages", [])
                if item.get("role") == "system"
            )
            is_summary = systems.startswith("Compress only the supplied conversation")
            if is_summary:
                content = setup._summary_response(case_db, current_run_id[0])
                choice = {"index": 0, "message": {"role": "assistant", "content": content}, "finish_reason": "stop"}
            else:
                sent.append(payload)
                tool_call = {
                    "id": "call-mock-only", "type": "function",
                    "function": {"name": "memory_remember", "arguments": "{}"},
                }
                message = {"role": "assistant", "content": None, "tool_calls": [tool_call]}
                choice = {"index": 0, "message": message, "finish_reason": finish_reason}
            estimated = (
                estimate_messages_tokens(payload["messages"])
                + estimate_text_tokens(task_abc.canonical(payload.get("tools", []))) + 64
            )
            return httpx.Response(200, json={
                "id": f"hf01-{finish_reason}-{len(sent)}", "object": "chat.completion", "created": 1,
                "model": task_abc.MODEL, "choices": [choice],
                "usage": {"prompt_tokens": estimated, "completion_tokens": 1, "total_tokens": estimated + 1},
            })

        current_run_id: list[str] = []
        current_identity: list[dict] = []
        original_seed = setup._seed_domain

        def capture_seed(*args, **kwargs):
            seeded = original_seed(*args, **kwargs)
            current_run_id.append(seeded[1])
            current_identity.append(seeded[3])
            return seeded

        monkeypatch.setattr(setup, "_seed_domain", capture_seed)
        result = asyncio.run(task_abc._run_case(
            case_root=tmp_path / f"case-{finish_reason}", case_id=case_id,
            question_id="Q02", group="B", strategy="ROLLING_SUMMARY", question_row=question,
            history=history, history_digest=history_digest, config=config,
            api_key="fixture-only-not-a-provider-key", ledger=ledger,
            trace_path=tmp_path / f"trace-{finish_reason}.jsonl.gz", mode="MOCK",
            mock_transport=httpx.MockTransport(respond),
        ))

        answer_slot = next(row for row in ledger.state["slots"] if row["logical_id"] == "Q02-B:ANSWER:1")
        later_case_slots = [row for row in ledger.state["slots"] if row["case_id"] == "Q06-B"]
        assert result["status"] == "NOT_COMPLETED"
        assert result["answer_response"] is None
        assert result["local_tool_observations"] == 0
        assert result["external_mcp_calls"] == 0
        assert result["summary_calls"] == 2
        assert result["answer_calls"] == 1
        assert len(sent) == 1 and sent[0]["tool_choice"] == "none"
        assert ledger.state["stop_reason"] == "UNEXPECTED_TOOL_CALL"
        assert answer_slot["status"] == "TOOL_CALL_BLOCKED"
        assert answer_slot["error"] == "TOOL_CALL_NOT_EXECUTED"
        assert answer_slot["provider_request_id"] == f"hf01-{finish_reason}-1"
        assert answer_slot["usage"]["output_tokens"] == 1
        assert answer_slot["settled_usd_micro"] > 0
        assert all(row["request_digest"] is None for row in later_case_slots)
        assert not any(row.get("event") in {"tool_observation", "tool_error", "personal_memory_tool"}
                       for row in assistant_events)
        domain_manifest = get_chat_manifest(case_db, current_identity[0], current_run_id[0])
        assert domain_manifest["attempts"][-1]["status"] == "FAILED"
        assert domain_manifest["attempts"][-1]["error_class"] == "RunnerStop"

        trace_path = tmp_path / f"trace-{finish_reason}.jsonl.gz"
        with gzip.open(trace_path, "rt", encoding="utf-8") as stream:
            events = [json.loads(line) for line in stream if line.strip()]
        response = next(row for row in events if row.get("event") == "RESPONSE_RECEIVED" and row.get("purpose") == "ANSWER")
        assert response["finish_reason"] == finish_reason
        assert response["response_payload"]["choices"][0]["message"]["tool_calls"]
        assert case_db.is_file()
        with connect(case_db) as db:
            tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            write_tables = [name for name in (
                "d2_pending_tool_calls", "d2_tool_observations", "d2_tool_faults",
                "d3_approvals", "d3_action_permissions", "d3_action_intents", "d3_action_ledgers",
                "d3_delivery_records", "d5_memory_events", "personal_memory_events",
                "personal_memory_consolidation_jobs", "semantic_memory_events", "semantic_memory_commands",
            ) if name in tables]
            write_counts = {
                name: int(db.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0])
                for name in write_tables
            }
        assert all(count == 0 for count in write_counts.values())


def test_frozen_task_id_is_stable_and_review_task_is_audit_metadata():
    assert gate.TASK == "R2-AR04-REMAINING-LIVE-GATE-01"
    assert gate.REVIEW_TASK_ID == "R2-AR04-LIVE-ADMISSION-HF-01"
    for old_task in (
        "R2-AR04-LIVE-RECHECK-V2-FINAL-01",
        "R2-AR04-LIVE-RETENTION-RECHECK-01",
        "R2-AR04-REMAINING-LIVE-01",
        "R2-AR04-LIVE-ADMISSION-HF-01",
    ):
        with pytest.raises(gate.GateStop, match="NEW_TASK_SPECIFIC_LIVE_AUTHORIZATION_REQUIRED"):
            gate.validate_authorization_manifest({"task": old_task, "base_sha": gate.BASE_SHA})
    wrong_review = {key: None for key in gate.AUTH_FIELDS}
    wrong_review.update({
        "task": gate.TASK, "base_sha": gate.BASE_SHA,
        "review_task_id": "R2-AR04-REMAINING-LIVE-01",
    })
    with pytest.raises(gate.GateStop, match="AUTH_REVIEW_TASK_ID_MISMATCH"):
        gate.validate_authorization_manifest(wrong_review)


def test_authorization_proposal_is_non_executable():
    proposal = json.loads((EVIDENCE_DIR / "AUTHORIZATION_PROPOSAL.json").read_text(encoding="utf-8"))
    assert proposal["task"] == gate.TASK
    assert proposal["review_task_id"] == gate.REVIEW_TASK_ID
    assert proposal["authorization_id"] is None
    assert proposal["actual_live_send_authorized"] is False
    with pytest.raises(gate.GateStop, match="AUTH_MANIFEST_SCHEMA_MISMATCH"):
        gate.validate_authorization_manifest(proposal)


def test_adapter_source_is_pinned_and_only_task_scoped_paths_are_allowed():
    freeze = gate._task_assert_frozen()
    assert freeze["provider_adapter_blob"] == gate.ABC_RUNNER_BLOB
    assert freeze["review_task_id"] == gate.REVIEW_TASK_ID
    assert freeze["review_base_sha"] == gate.REVIEW_BASE_SHA
