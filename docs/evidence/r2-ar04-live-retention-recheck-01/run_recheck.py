"""Three-case AR-04 recheck over the existing bounded ABC Runner."""
from __future__ import annotations

import argparse
import asyncio
import copy
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path

import httpx


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT))

from retention_evidence import (
    OLD, OLD_TRACE, capture_case, historical_comparison, read_json, response_text, summary_source, trace_index,
)


TASK = "R2-AR04-LIVE-RETENTION-RECHECK-01"
BASE = "e68fd3cd924dbad6bda69b9b9d02519ff0f3a3d7"
MATRIX = ("Q02-A", "Q02-B", "Q06-B")
REQUEST_CAP = 9
HARD_CAP_MICRO = 60_000
OFFERED_TOOL_SCHEMA = "555cd385857aadce03e567c27886a49b3f6db6734c25c310a3c5bb3a07dbcec7"
TRUSTED_PREFIX = "46267d783298bcb2c64957de58d4d117b760151323ae9e1bf5a5434b9a37163b"
CHAT_BLOB = "1bbdfc878009729c625df89330f3c7e42ddae280"
MOCK_KEY = "offline-only-not-a-real-key"


def source_invalidated(db_path):
    from opspilot.domain.database import connect

    with connect(db_path) as db:
        return bool(db.execute(
            "SELECT EXISTS(SELECT 1 FROM context_compression_attempts WHERE status='INVALIDATED')"
            " OR EXISTS(SELECT 1 FROM context_summaries WHERE state='INVALID')"
            """ OR EXISTS (
                SELECT 1
                FROM context_compression_attempts a
                JOIN json_each(a.source_dependencies_json, '$.dependencies') d
                LEFT JOIN messages m ON m.message_id = json_extract(d.value, '$.ref')
                WHERE json_extract(d.value, '$.kind') IN ('MESSAGE', 'ASSISTANT_MESSAGE')
                AND (m.message_id IS NULL OR m.body_digest <> json_extract(d.value, '$.digest'))
            )"""
        ).fetchone()[0])


def abc_runner():
    # Configure only a private instance of the task-local module. The original
    # ABC Runner, its artifacts and the production Runtime Grant are unchanged.
    spec = importlib.util.spec_from_file_location("ar04_recheck_abc", OLD / "run_abc_eval.py")
    abc = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(abc)
    slots = [slot for slot in abc._planned_slots() if slot["case_id"] in MATRIX]
    assert len(slots) == REQUEST_CAP and tuple(dict.fromkeys(slot["case_id"] for slot in slots)) == MATRIX
    abc._planned_slots = lambda: copy.deepcopy(slots)
    abc.TASK = TASK
    abc.BASE_SHA = BASE
    abc.recheck_case_databases = {}
    abc.NON_SECRET_DEFAULTS.update({
        "OPSPILOT_MODEL_CONFIG_VERSION": "r2-ar04-retention-recheck-model-v1",
        "OPSPILOT_ASSISTANT_SERVICE_IDENTITY": "opspilot-isolated-ar04-retention-recheck-01",
    })

    class FrozenTransport(abc.BudgetedAsyncTransport):
        def _validate_request(self, request, body):
            db_path = abc.recheck_case_databases.get(self.case_id)
            if db_path is None and self.mode == "LIVE":
                raise abc.RunnerStop("RECHECK_CASE_DATABASE_MISSING")
            # Production can try a new compaction after invalidation. The
            # one-shot evaluation stops at the next outbound boundary instead.
            if db_path is not None and source_invalidated(db_path):
                raise abc.RunnerStop("RECHECK_SOURCE_INVALIDATED")
            payload, purpose = super()._validate_request(request, body)
            tools = payload.get("tools", [])
            if purpose == "SUMMARY":
                if tools:
                    raise abc.RunnerStop("RECHECK_SUMMARY_TOOL_SCHEMA_DRIFT")
            else:
                if abc.sha256(abc.canonical(tools)) != OFFERED_TOOL_SCHEMA:
                    raise abc.RunnerStop("RECHECK_ANSWER_TOOL_SCHEMA_DRIFT")
                system = "\n".join(str(row.get("content", "")) for row in payload["messages"]
                                   if row.get("role") == "system")
                if abc.sha256(system.split("\nWORK_CONTEXT\n", 1)[0]) != TRUSTED_PREFIX:
                    raise abc.RunnerStop("RECHECK_TRUSTED_PROMPT_PREFIX_DRIFT")
            return payload, purpose

    abc.BudgetedAsyncTransport = FrozenTransport
    return abc


def checkout_evidence(abc):
    from opspilot.domain import chat

    path = ROOT / "opspilot/domain/chat.py"
    if Path(chat.__file__).resolve() != path.resolve():
        raise abc.RunnerStop("PRODUCTION_CHAT_IMPORTED_FROM_ANOTHER_CHECKOUT")
    blob = subprocess.check_output(["git", "hash-object", str(path)], cwd=ROOT, text=True).strip()
    if blob != CHAT_BLOB:
        raise abc.RunnerStop("PRODUCTION_COMPACTOR_BLOB_DRIFT")
    # Only evidence can change in the candidate. Include the old Runner and
    # the setup harness in this check so a replay cannot silently edit inputs.
    checked = subprocess.run([
        "git", "diff", "--quiet", BASE, "--", "opspilot", "pyproject.toml", "requirements.lock.txt",
        "docs/evidence/abc-live-env-unblock-01", "docs/evidence/r2-ar04-live-eval-setup-hf01",
        "docs/evidence/r2-ar04-long-context-journey-01",
    ], cwd=ROOT)
    if checked.returncode != 0:
        raise abc.RunnerStop("PRODUCTION_OR_FROZEN_INPUT_DIFF_FROM_BASE")
    return {"base_sha": BASE, "production_chat_blob": blob,
            "legacy_runner_sha256": abc.sha256((OLD / "run_abc_eval.py").read_bytes())}


def mock_transport(abc, case_id, first_summary):
    """Replay the historical first summary, then echo the actual parent projection."""
    from opspilot.domain.context_engineering import estimate_messages_tokens, estimate_text_tokens

    call_no = 0

    def respond(request):
        nonlocal call_no
        call_no += 1
        payload = json.loads(request.content)
        source = summary_source(payload)
        if source:
            parent = source.get("previous_summary")
            content = abc.canonical(parent) if parent is not None else first_summary
        else:
            content = f"MOCK_ONLY::{case_id}"
        estimate = (
            estimate_messages_tokens(payload["messages"])
            + estimate_text_tokens(abc.canonical(payload.get("tools", []))) + 64
        )
        return httpx.Response(200, json={
            "id": f"retention-recheck-mock-{case_id}-{call_no}",
            "object": "chat.completion", "created": 1, "model": abc.MODEL,
            "choices": [{"index": 0, "message": {"role": "assistant", "content": content},
                         "finish_reason": "stop"}],
            "usage": {"prompt_tokens": estimate, "completion_tokens": 24, "total_tokens": estimate + 24},
        })

    return httpx.MockTransport(respond)


def run_cases(abc, output, *, mode, config, api_key, authorized_task=None, live_preflight=None):
    if mode == "LIVE":
        require_live_authorization(authorized_task)
        if not (live_preflight or {}).get("technical_preflight_passed"):
            raise abc.RunnerStop("RECHECK_TECHNICAL_PREFLIGHT_REQUIRED")
    elif mode != "MOCK":
        raise ValueError("RECHECK_UNKNOWN_RUN_MODE")
    checkout = checkout_evidence(abc)
    history, questions, history_digest, questions_digest = abc.load_frozen_inputs()
    before = historical_comparison(MATRIX)
    old_pairs = trace_index(OLD_TRACE) if mode == "MOCK" else {}
    output.mkdir(parents=True, exist_ok=False)
    if mode == "LIVE":
        abc.atomic_json(output / "PREFLIGHT.json", {
            **live_preflight, "actual_live_send_authorized": True,
            "status": "AUTHORIZED_FOR_BOUNDED_LIVE_EXECUTION",
        })
    prefix = "MOCK_" if mode == "MOCK" else ""
    trace_path = output / ("MOCK_TRACE.jsonl.gz" if mode == "MOCK" else "LIVE_REQUESTS.jsonl.gz")
    ledger = abc.GlobalBudgetLedger.create(
        output / f"{prefix}COST_LEDGER.json", execution_id=f"{TASK}:{mode}:{uuid.uuid4().hex[:12]}",
        mode=mode, request_limit=REQUEST_CAP, hard_cap_usd_micro=HARD_CAP_MICRO,
    )
    results_path = output / ("MOCK_RESULTS.json" if mode == "MOCK" else "LIVE_RESULTS.json")
    rows = [{"case_id": case_id, "status": "NOT_STARTED"} for case_id in MATRIX]
    result = {
        "task": TASK, **checkout, "mode": mode, "status": "IN_PROGRESS",
        "history_rows_per_case": len(history), "history_digest_sha256": history_digest,
        "questions_file_sha256": questions_digest, "execution_id": ledger.state["execution_id"], "cases": rows,
        "l3_scoring": "NOT_RUN" if mode == "MOCK" else "IMPLEMENTER_PRELIMINARY_REVIEW_PENDING",
    }
    abc.atomic_json(results_path, result)
    with tempfile.TemporaryDirectory(prefix="opspilot-ar04-recheck-") as scratch:
        for row in rows:
            case_id = row["case_id"]
            question_id, group = case_id.split("-")
            case_root = Path(scratch) / case_id
            db_path = case_root / "domain.sqlite3"
            abc.recheck_case_databases[case_id] = db_path
            row["status"] = "RUNNING"
            abc.atomic_json(results_path, result)
            try:
                transport = None
                if mode == "MOCK":
                    frozen = response_text(old_pairs, f"{case_id}:SUMMARY:1")
                    if frozen is None:
                        raise abc.RunnerStop("FROZEN_MOCK_SUMMARY_MISSING")
                    transport = mock_transport(abc, case_id, frozen)
                case = asyncio.run(abc._run_case(
                    case_root=case_root, case_id=case_id, question_id=question_id, group=group,
                    strategy=abc.STRATEGIES[group], question_row=questions[question_id],
                    history=history, history_digest=history_digest, config=config, api_key=api_key,
                    ledger=ledger, trace_path=trace_path, mode=mode, mock_transport=transport,
                ))
                row.update(case)
            except Exception as error:
                row.update(status="FAILED_OR_UNKNOWN", error=getattr(error, "code", None) or type(error).__name__)
            if db_path.is_file():
                try:
                    if source_invalidated(db_path):
                        ledger.stop("RECHECK_SOURCE_INVALIDATED")
                    row.update(capture_case(case_id, db_path, trace_path))
                    if row["mcp_attempts"]:
                        ledger.stop("RECHECK_UNEXPECTED_MCP_ATTEMPT")
                except Exception as error:
                    row["capture_error"] = type(error).__name__
                    ledger.stop("EVIDENCE_CAPTURE_FAILED")
            if row["status"] != "SUCCEEDED":
                ledger.stop(str(row.get("error") or row.get("reason") or "ASSISTANT_CASE_FAILED"))
            abc.atomic_json(results_path, result)
            if ledger.state["stop_reason"]:
                break
    ledger.finalize()
    sent = [slot for slot in ledger.state["slots"] if slot["request_digest"]]
    result.update({
        "status": "STOPPED" if ledger.state["stop_reason"] else "COMPLETED",
        "stop_reason": ledger.state["stop_reason"],
        "recorded_requests": len(sent),
        "summary_requests": sum(slot["purpose"] == "SUMMARY" for slot in sent),
        "answer_requests": sum(slot["purpose"] == "ANSWER" for slot in sent),
        "external_provider_requests": 0 if mode == "MOCK" else len(sent),
        "provider_conservative_cost_estimate_usd_micro": 0 if mode == "MOCK" else ledger.state["settled_usd_micro"],
        "remaining_unknown_reserve_usd_micro": ledger.state["currently_reserved_usd_micro"],
    })
    for comparison, row in zip(before, rows):
        if mode == "MOCK":
            comparison["after"]["mock_visibility"] = row.get("provider_stage_and_prompt_visibility")
        else:
            comparison["after"] = {
                "l2_live": row.get("provider_stage_and_prompt_visibility", "NOT_AVAILABLE"),
                "l3_live": "IMPLEMENTER_PRELIMINARY_REVIEW_PENDING" if row.get("answer_response") else "NOT_AVAILABLE",
                "answer": row.get("answer_response"), "run_status": row["status"],
            }
    abc.atomic_json(output / "COMPARISON.json", before)
    abc.atomic_json(results_path, result)
    return result


def mock_passed(results):
    cases = results.get("cases", [])
    return (
        results.get("task") == TASK and results.get("base_sha") == BASE
        and results.get("production_chat_blob") == CHAT_BLOB and results.get("mode") == "MOCK"
        and results.get("status") == "COMPLETED" and results.get("external_provider_requests") == 0
        and results.get("summary_requests") == 6 and results.get("answer_requests") == 3
        and tuple(row.get("case_id") for row in cases) == MATRIX
        and len({row.get("domain_instance_sha256") for row in cases}) == len(MATRIX)
        and len({row.get("checkpoint_instance_sha256") for row in cases}) == len(MATRIX)
        and len({row.get("session_id_sha256") for row in cases}) == len(MATRIX)
        and len({row.get("runtime_grant_id_sha256") for row in cases}) == len(MATRIX)
        and all(
            row.get("status") == "SUCCEEDED" and row.get("answer_tool_choice") == "none"
            and row.get("runtime_binding_database_identity_matches")
            and row.get("session_id_sha256") and row.get("runtime_grant_id_sha256")
            and row.get("mcp_attempts") == 0
            and row.get("second_input_matches_production_projection_of_first_persisted")
            and row.get("final_wire_summary_matches_current_persisted")
            and all(
                row.get("provider_stage_and_prompt_visibility", {}).get(phase, {}).get("visibility")
                == "COMPLETE_TEXT_WITH_SOURCE"
                for phase in ("first_persisted_summary", "second_summary_input", "final_answer_summary")
            )
            for row in cases
        )
    )


def preflight(abc, mock_path):
    checkout = checkout_evidence(abc)
    mock = read_json(mock_path)
    report = abc.run_zero_cost_preflight(mock_runner_passed=mock_passed(mock))
    technical_ready = report.pop("real_provider_send_condition")
    reserve = REQUEST_CAP * abc.REQUEST_RESERVE_USD_MICRO
    report.update({
        **checkout, "actual_live_send_authorized": False,
        "status": ("AWAITING_NEW_LIVE_PROVIDER_AUTHORIZATION" if technical_ready and reserve <= HARD_CAP_MICRO
                   else "BLOCKED_BEFORE_PROVIDER_SEND"),
        "technical_preflight_passed": technical_ready and reserve <= HARD_CAP_MICRO,
        "mock_results_sha256": abc.sha256(mock_path.read_bytes()),
        "case_order": MATRIX, "official_model_alias": abc.MODEL, "published_model_version": abc.MODEL_VERSION,
        "price_page": "https://api-docs.deepseek.com/quick_start/pricing/",
        "chat_completions_docs": "https://api-docs.deepseek.com/api/create-chat-completion/",
        "official_docs_checked_on": "2026-11-15",
        "requested_temperature": 0, "effective_temperature_documented_non_thinking": 1.0,
        "input_peak_cache_miss_usd_per_million": 0.30, "output_peak_usd_per_million": 1.20,
        "max_input_tokens_per_request": abc.MAX_INPUT_TOKENS, "max_output_tokens_per_request": abc.MAX_OUTPUT_TOKENS,
        "request_cap": REQUEST_CAP, "total_worst_case_reserved_usd_micro": reserve,
        "suggested_hard_cap_usd_micro": HARD_CAP_MICRO,
        "provider_key_verified_by_network": False,
    })
    return report


def require_live_authorization(approved_task):
    if approved_task != TASK:
        raise RuntimeError("NEW_LIVE_PROVIDER_AUTHORIZATION_REQUIRED")


def block_outbound_model_io():
    # This hook is only installed in the CLI's zero-cost processes. Loopback
    # is kept for asyncio on Windows. No DNS or connections to an external host.
    import ipaddress

    def audit(event, args):
        if event not in {"socket.getaddrinfo", "socket.connect"}:
            return
        host = args[1][0] if event == "socket.connect" else args[0]
        if host in (None, "localhost"):
            return
        try:
            if ipaddress.ip_address(host).is_loopback:
                return
        except ValueError:
            pass
        raise OSError("AR04_RECHECK_ZERO_COST_NETWORK_GUARD")

    sys.addaudithook(audit)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("mock", "preflight", "live"))
    parser.add_argument("--output", type=Path)
    parser.add_argument("--mock-results", type=Path)
    parser.add_argument("--authorized-task")
    args = parser.parse_args()
    if args.mode == "live":
        require_live_authorization(args.authorized_task)
        if args.output is not None:
            parser.error("live uses one fixed, non-reusable campaign directory")
    else:
        if args.output is None:
            parser.error("mock and preflight require --output")
        block_outbound_model_io()
    if args.mode != "mock" and args.mock_results is None:
        parser.error("preflight and live require --mock-results")
    os.environ.update(LANGSMITH_TRACING="false", LANGCHAIN_TRACING_V2="false")
    abc = abc_runner()
    if args.mode == "mock":
        config = abc._mock_config()
        result = run_cases(abc, args.output, mode="MOCK", config=config, api_key=MOCK_KEY)
        print(json.dumps({"mock_passed": mock_passed(result), "recorded_mock_requests": result["recorded_requests"]}))
        return 0 if mock_passed(result) else 1
    # Use the configured main repo .env, not a prior process's experiment flags.
    for key in abc.REQUIRED_ENV:
        os.environ.pop(key, None)
    report = preflight(abc, args.mock_results)
    if args.mode == "preflight":
        if args.output.exists():
            raise abc.RunnerStop("PREFLIGHT_EVIDENCE_ALREADY_EXISTS")
        abc.atomic_json(args.output, report)
        print(json.dumps({"status": report["status"], "provider_requests_sent": 0}))
        return 0 if report["technical_preflight_passed"] else 1

    # This invocation is reserved for an explicitly authorized future turn.
    if not report["technical_preflight_passed"]:
        print(json.dumps({"status": report["status"], "provider_requests_sent": 0}))
        return 1
    output = HERE / "live_run_01"
    config = abc._case_config_from_env()
    result = run_cases(
        abc, output, mode="LIVE", config=config, api_key=os.environ["OPSPILOT_MODEL_API_KEY"],
        authorized_task=args.authorized_task, live_preflight=report,
    )
    print(json.dumps({key: result[key] for key in ("status", "stop_reason", "external_provider_requests")}))
    return 0 if result["status"] == "COMPLETED" else 1


if __name__ == "__main__":
    sys.exit(main())
