"""Offline-only V2 adapter for the frozen AR-04 retention recheck matrix.

This module intentionally exposes only MOCK and PREFLIGHT modes.  It adapts the
accepted ABC Runtime Grant/Assistant harness to the current, explicitly pinned
production blobs and frozen inputs.  No live Provider dispatch path exists.
"""
from __future__ import annotations

import argparse
import asyncio
import gzip
import hashlib
import importlib.util
import json
import os
import re
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Any

import httpx


EVIDENCE_DIR = Path(__file__).resolve().parent
ROOT = EVIDENCE_DIR.parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
BASE_SHA = "d8a526daa9c811814a5e2463b34eb37037ae1a8e"
TASK = "R2-AR04-LIVE-RECHECK-V2-PREP-01"
CASE_MATRIX = ("Q02-A", "Q02-B", "Q06-B")
REQUEST_CAP = 9
MOCK_HARD_CAP_USD_MICRO = 60_000
MOCK_KEY = "offline-only-not-a-real-key"
MODEL = "deepseek-flash"
MODEL_VERSION = "DeepSeek-V4.1-Flash-1017"
ENDPOINT = "https://api.deepseek.com"
MAX_INPUT_TOKENS = 12_000
MAX_OUTPUT_TOKENS = 512
SUMMARY_OUTPUT_CAP_TOKENS = 512
TEMPERATURE = 0
THINKING = {"type": "disabled"}
TOOL_CHOICE = "none"
TOOL_SCHEMA_SHA256 = "555cd385857aadce03e567c27886a49b3f6db6734c25c310a3c5bb3a07dbcec7"
TRUSTED_PREFIX_SHA256 = "46267d783298bcb2c64957de58d4d117b760151323ae9e1bf5a5434b9a37163b"
CHAT_BLOB = "d10f495cadc4c2006504ecd87e5c02947f87e80b"
ASSISTANT_BLOB = "4fa1aaa7059cf6478fce4c262b8c1876df9a7dcb"

FROZEN_FILES = {
    "docs/evidence/r2-ar04-long-context-journey-01/QUESTIONS.json": "ea3d6554eafa433d1617dc5a5ba9f140471f3cb95f8ae10bcd25b807a4e7afe2",
    "docs/evidence/r2-ar04-long-context-journey-01/RESULTS.json": "4b04f3d574028099f13748091d4d421c7654b15bed4d25be13b40c413b8699c4",
    "docs/evidence/r2-ar04-long-context-journey-01/HISTORY_SNAPSHOT.json": "356512f611b046a04e33506a0fb1a88c6a08af93517b2134125dd6771b282c16",
    "docs/evidence/r2-ar04-long-context-journey-01/MODEL_REQUESTS.jsonl.gz": "96efd85b7d29d54938b1a4932321eff74bca7e8e56565c978f58a1e57d9a1792",
    "docs/evidence/abc-live-env-unblock-01/live_run_02/LIVE_REQUESTS.jsonl.gz": "80dab676295960017bf31ba25c1aef62657d0eb0c437aa0fa1f0f6f56a8da05c",
    "docs/evidence/abc-live-env-unblock-01/live_run_02/LIVE_RESULTS.json": "29ff36295398475699c767ec826dc94331b7299b527ae69b41c5e995cce4f55b",
    "docs/evidence/abc-live-env-unblock-01/IMPLEMENTER_PRELIMINARY_ASSESSMENT.json": "d89336e80191dd0771d83b42dcca1039d5f321a503c365d9b76ba9efbf88750f",
}
FROZEN_FIRST_SUMMARY_SHA256 = {
    "Q02-A": "815ce6e46122561c83ab227c6fbe1bb3322e99663d144fd5ccac84b483393a83",
    "Q02-B": "be035b0ff1894321a08a49dfbf9a934d163c2fcad62c409797281619221376ee",
    "Q06-B": "7d624dd829dbf786f749d08e4880f4df8a94906147dfc06d56c943fbff42b755",
}
PROTECTED_HISTORICAL_FILES = (
    "docs/evidence/r2-ar04-compaction-c06-hf01/RESULTS.json",
    "docs/evidence/r2-ar04-compaction-c06-hf01/RED_REPRO_TRACE.json",
    "docs/evidence/r2-ar04-compaction-c06-hf01/RED_REPRO.txt",
    "docs/evidence/r2-ar04-compaction-c06-hf01/TEST_RUN.txt",
    "docs/evidence/r2-ar04-base-diff-edge-gate-hf02/F01_RUN.txt",
    "docs/evidence/r2-ar04-live-retention-recheck-01/RESULTS.json",
    "docs/evidence/r2-ar04-live-retention-recheck-01/live_run_01/LIVE_RESULTS.json",
    "docs/evidence/r2-ar04-live-retention-recheck-01/live_run_01/LIVE_REQUESTS.jsonl.gz",
    "docs/evidence/r2-ar04-live-retention-recheck-01/live_run_01/COST_LEDGER.json",
)
PROTECTED_DIFF_PATHS = (
    "opspilot",
    "pyproject.toml",
    "requirements.lock.txt",
    "docs/evidence/abc-live-env-unblock-01",
    "docs/evidence/r2-ar04-live-eval-setup-hf01",
    "docs/evidence/r2-ar04-long-context-journey-01",
    "docs/evidence/r2-ar04-live-retention-recheck-01",
    "docs/evidence/r2-ar04-live-summary-persist-hf01",
    "docs/evidence/r2-ar04-compaction-c06-hf01",
    "docs/evidence/r2-ar04-base-diff-edge-gate-hf02",
    "docs/evidence/ar-04c/f01-context-currentness-01",
)


class V2Stop(RuntimeError):
    pass


def sha256(value: bytes | str) -> str:
    raw = value if isinstance(value, bytes) else value.encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True, stderr=subprocess.STDOUT).strip()


def _expect_digest(label: str, actual: str, expected: str) -> None:
    if actual != expected:
        raise V2Stop(f"FROZEN_DIGEST_DRIFT:{label}")


def assert_file_pins(root: Path, pins: dict[str, str]) -> dict[str, str]:
    actuals = {}
    for rel, expected in pins.items():
        path = root / rel
        actual = sha256(path.read_bytes()) if path.is_file() else "MISSING"
        _expect_digest(rel, actual, expected)
        actuals[rel] = actual
    return actuals


def assert_source_blob_pins(actual_blobs: dict[str, str]) -> None:
    for rel, expected in (
        ("opspilot/domain/chat.py", CHAT_BLOB),
        ("opspilot/assistant.py", ASSISTANT_BLOB),
    ):
        _expect_digest(rel, actual_blobs.get(rel, "MISSING"), expected)


def assert_model_parameters(payload: dict[str, Any]) -> None:
    if payload.get("model") != MODEL:
        raise V2Stop("MODEL_ID_DRIFT_BEFORE_SEND")
    if payload.get("thinking") != THINKING or payload.get("temperature") != TEMPERATURE:
        raise V2Stop("MODEL_PARAMETERS_DRIFT_BEFORE_SEND")
    if payload.get("stream") is True or type(payload.get("max_tokens")) is not int:
        raise V2Stop("MODEL_REQUEST_SHAPE_DRIFT_BEFORE_SEND")
    if not 0 < int(payload["max_tokens"]) <= MAX_OUTPUT_TOKENS:
        raise V2Stop("MODEL_OUTPUT_BUDGET_DRIFT_BEFORE_SEND")


def assert_answer_contract(payload: dict[str, Any]) -> None:
    messages = payload.get("messages", [])
    system = "\n".join(
        str(item.get("content", "")) for item in messages
        if isinstance(item, dict) and item.get("role") == "system"
    )
    if payload.get("tool_choice") != TOOL_CHOICE:
        raise V2Stop("HISTORY_RECALL_TOOL_CHOICE_DRIFT_BEFORE_SEND")
    if sha256(canonical(payload.get("tools", []))) != TOOL_SCHEMA_SHA256:
        raise V2Stop("TOOL_SCHEMA_DRIFT_BEFORE_SEND")
    prefix = system.split("\nWORK_CONTEXT\n", 1)[0]
    if sha256(prefix) != TRUSTED_PREFIX_SHA256:
        raise V2Stop("TRUSTED_PROMPT_PREFIX_DRIFT_BEFORE_SEND")


def assert_frozen(*, root: Path = ROOT) -> dict[str, Any]:
    root = root.resolve()
    if root != ROOT.resolve():
        raise V2Stop("PRODUCTION_CHECKOUT_ROOT_DRIFT")
    try:
        _git("cat-file", "-e", f"{BASE_SHA}^{{commit}}")
    except subprocess.CalledProcessError as error:
        raise V2Stop("FROZEN_BASE_COMMIT_MISSING") from error
    head = _git("rev-parse", "HEAD")
    try:
        _git("merge-base", "--is-ancestor", BASE_SHA, head)
    except subprocess.CalledProcessError as error:
        raise V2Stop("CANDIDATE_NOT_DESCENDED_FROM_FROZEN_BASE") from error
    if _git("rev-list", "--merges", f"{BASE_SHA}..{head}"):
        raise V2Stop("MERGE_COMMIT_AFTER_FROZEN_BASE_BLOCKED")

    source_blobs = {
        rel: _git("hash-object", rel)
        for rel in ("opspilot/domain/chat.py", "opspilot/assistant.py")
    }
    assert_source_blob_pins(source_blobs)
    input_hashes = assert_file_pins(root, FROZEN_FILES)

    changed = subprocess.run(
        ["git", "diff", "--quiet", BASE_SHA, "HEAD", "--", *PROTECTED_DIFF_PATHS],
        cwd=root,
    )
    if changed.returncode != 0:
        raise V2Stop("PRODUCTION_OR_HISTORICAL_EVIDENCE_DIFF_FROM_BASE")

    protected_hashes = {}
    for rel in PROTECTED_HISTORICAL_FILES:
        path = root / rel
        if not path.is_file():
            raise V2Stop(f"PROTECTED_HISTORICAL_FILE_MISSING:{rel}")
        # Compare Git-cleaned content blobs so Windows checkout line endings do
        # not look like edits to immutable LF-stored text artifacts.
        work_blob = _git("hash-object", f"--path={rel}", rel)
        base_blob = _git("rev-parse", f"{BASE_SHA}:{rel}")
        _expect_digest(f"protected:{rel}", work_blob, base_blob)
        protected_hashes[rel] = {
            "working_tree_sha256": sha256(path.read_bytes()),
            "git_blob": work_blob,
            "matches_base": True,
        }

    return {
        "base_sha": BASE_SHA,
        "candidate_head_at_check": head,
        "production_blobs": source_blobs,
        "frozen_input_sha256": input_hashes,
        "protected_historical_sha256": protected_hashes,
        "protected_paths_diff_from_base": False,
    }


def _legacy_modules():
    old_dir = ROOT / "docs/evidence/r2-ar04-live-retention-recheck-01"
    abc_dir = ROOT / "docs/evidence/abc-live-env-unblock-01"
    for path in (old_dir, abc_dir):
        if str(path) not in sys.path:
            sys.path.insert(0, str(path))
    spec = importlib.util.spec_from_file_location("ar04_v2_legacy_recheck", old_dir / "run_recheck.py")
    if spec is None or spec.loader is None:
        raise V2Stop("LEGACY_RECHECK_ADAPTER_LOAD_FAILED")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _fact_diagnostics(case_id: str, stages: dict[str, Any]) -> dict[str, Any]:
    if case_id != "Q06-B":
        return {}
    final = stages.get("final_answer_summary") or {}
    entries = final.get("items") or []
    seq3_items = [
        item for item in entries
        if 3 in item.get("source_sequences", []) and "max_attempts" in item.get("text", "")
    ]
    seq11_items = [
        item for item in entries
        if 11 in item.get("source_sequences", []) and "max_attempts" in item.get("text", "")
    ]
    seq11_complete = any(
        re.search(r"v1\.2.{0,50}(?:到|为|至|→|->|to).{0,20}v1\.3", item.get("text", ""), re.I)
        and re.search(r"max_attempts.{0,30}3.{0,12}(?:改为|到|为|至|→|->|to).{0,12}5", item.get("text", ""), re.I)
        for item in seq11_items
    )
    # A seq3 literal is evidence of the earlier value only.  The later seq11
    # transition is assessed independently and cannot upgrade seq3 to complete.
    seq3_status = "PARTIAL" if seq3_items else "MISSING"
    return {
        "max_attempts_early_value_seq3": {
            "status": seq3_status,
            "source_sequence": 3,
            "item_count": len(seq3_items),
            "meaning": "earlier value only; no transition relation attributed to seq3",
        },
        "protocol_and_max_attempts_transition_seq11": {
            "status": "COMPLETE_TEXT_WITH_SOURCE" if seq11_complete else "PARTIAL_OR_MISSING",
            "source_sequence": 11,
        },
    }


def build_runner():
    freeze = assert_frozen()
    legacy = _legacy_modules()
    legacy.TASK = TASK
    legacy.BASE = BASE_SHA
    legacy.MATRIX = CASE_MATRIX
    legacy.REQUEST_CAP = REQUEST_CAP
    legacy.CHAT_BLOB = CHAT_BLOB

    def checkout_evidence(abc):
        if Path(abc.ROOT).resolve() != ROOT.resolve():
            raise V2Stop("LEGACY_RUNNER_IMPORTED_FROM_WRONG_CHECKOUT")
        return {**assert_frozen(), "legacy_runner_sha256": sha256(
            (ROOT / "docs/evidence/abc-live-env-unblock-01/run_abc_eval.py").read_bytes()
        )}

    legacy.checkout_evidence = checkout_evidence
    abc = legacy.abc_runner()
    abc.BASE_SHA = BASE_SHA
    abc.TASK = TASK
    abc.NON_SECRET_DEFAULTS.update({
        "OPSPILOT_MODEL_CONFIG_VERSION": "r2-ar04-live-recheck-v2-prep-model-v1",
        "OPSPILOT_ASSISTANT_SERVICE_IDENTITY": "opspilot-isolated-ar04-live-recheck-v2-prep",
    })

    active_scenarios: dict[str, str] = {}
    reply_provenance: list[dict[str, Any]] = []
    summary_counts: dict[str, int] = {}

    base_transport = abc.BudgetedAsyncTransport

    class V2PinnedTransport(base_transport):
        def _validate_request(self, request, body):
            assert_frozen()
            try:
                payload = json.loads(body.decode("utf-8"))
            except Exception as error:
                raise V2Stop("REQUEST_BODY_INVALID_BEFORE_SEND") from error
            assert_model_parameters(payload)
            system = "\n".join(
                str(item.get("content", "")) for item in payload.get("messages", [])
                if isinstance(item, dict) and item.get("role") == "system"
            )
            summary_call = "Compress only the supplied conversation" in system
            if not summary_call:
                assert_answer_contract(payload)
            else:
                if payload.get("tools", []) != []:
                    raise V2Stop("SUMMARY_TOOL_SCHEMA_MUST_BE_EMPTY")
            case_id = self.case_id
            summary_counts[case_id] = summary_counts.get(case_id, 0) + int(summary_call)
            if active_scenarios.get(case_id) == "source_invalidated_between_rounds" and summary_call and summary_counts[case_id] == 2:
                from opspilot.domain.database import connect
                db_path = abc.recheck_case_databases.get(case_id)
                if db_path is None or not db_path.is_file():
                    raise V2Stop("SOURCE_INVALIDATION_CASE_DATABASE_MISSING")
                with connect(db_path) as db:
                    changed = db.execute(
                        "UPDATE messages SET body_digest=? WHERE sequence=3", ("0" * 64,),
                    )
                    if changed.rowcount != 1:
                        raise V2Stop("SOURCE_INVALIDATION_FIXTURE_MISMATCH")
            return super()._validate_request(request, body)

    abc.BudgetedAsyncTransport = V2PinnedTransport

    original_run_case = abc._run_case
    async def run_case_with_run_identity(**kwargs):
        result = await original_run_case(**kwargs)
        db_path = Path(kwargs["case_root"]) / "domain.sqlite3"
        if db_path.is_file() and result.get("status") == "SUCCEEDED":
            from opspilot.domain.database import connect
            with connect(db_path) as db:
                run_ids = [str(row[0]) for row in db.execute("SELECT run_id FROM assistant_runs")]
            if len(run_ids) != 1:
                raise V2Stop("ISOLATED_ASSISTANT_RUN_COUNT_MISMATCH")
            result["run_id_sha256"] = sha256(run_ids[0])
            result["answer_manifest_present"] = True
        return result
    abc._run_case = run_case_with_run_identity

    def mock_transport(_abc, case_id, first_summary):
        scenario = active_scenarios.get(case_id, "success")
        call_no = 0

        def respond(request):
            nonlocal call_no
            call_no += 1
            payload = json.loads(request.content.decode("utf-8"))
            from retention_evidence import summary_source
            source = summary_source(payload)
            if scenario == "unknown_first_send" and call_no == 1:
                raise httpx.ReadTimeout("fixture unknown result; no retry")
            if scenario == "summary_persist_failure" and call_no == 1:
                content = first_summary
                origin = "FROZEN_HISTORICAL_LIVE_SUMMARY"
            elif source:
                parent = source.get("previous_summary")
                content = canonical(parent) if parent is not None else first_summary
                origin = "SYNTHETIC_DETERMINISTIC_PARENT_PROJECTION" if parent is not None else "FROZEN_HISTORICAL_LIVE_SUMMARY"
            else:
                content = f"MOCK_ONLY::{case_id}"
                origin = "SYNTHETIC_MOCK_ANSWER"

            from opspilot.domain.context_engineering import estimate_messages_tokens, estimate_text_tokens
            estimated_input = (
                estimate_messages_tokens(payload["messages"])
                + estimate_text_tokens(canonical(payload.get("tools", []))) + 64
            )
            output_tokens = 513 if scenario == "oversized_first_summary" and call_no == 1 else 24
            response_id = f"ar04-v2-mock-{case_id}-{call_no}"
            reply_provenance.append({
                "case_id": case_id,
                "logical_sequence": call_no,
                "purpose": "SUMMARY" if source or "Compress only the supplied conversation" in "\n".join(
                    str(item.get("content", "")) for item in payload.get("messages", []) if item.get("role") == "system"
                ) else "ANSWER",
                "origin": origin,
                "historical_response_id": "c3435ff4-fc27-4ffb-b053-bbfcabc600e0" if case_id == "Q02-A" and call_no == 1 else None,
                "historical_content_sha256": sha256(content) if origin == "FROZEN_HISTORICAL_LIVE_SUMMARY" else None,
                "mock_response_id": response_id,
                "content_sha256": sha256(content),
            })
            return httpx.Response(200, json={
                "id": response_id,
                "object": "chat.completion",
                "created": 1,
                "model": MODEL,
                "choices": [{"index": 0, "message": {"role": "assistant", "content": content}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": estimated_input, "completion_tokens": output_tokens,
                          "total_tokens": estimated_input + output_tokens},
            })

        return httpx.MockTransport(respond)

    legacy.mock_transport = mock_transport
    return legacy, abc, freeze, active_scenarios, reply_provenance, summary_counts


def frozen_summary_for_case(legacy, case_id: str) -> str:
    from retention_evidence import response_text
    pairs = legacy.trace_index(legacy.OLD_TRACE)
    summary = response_text(pairs, f"{case_id}:SUMMARY:1")
    if not summary:
        raise V2Stop(f"FROZEN_LIVE_SUMMARY_MISSING:{case_id}")
    _expect_digest(f"historical_first_summary:{case_id}", sha256(summary), FROZEN_FIRST_SUMMARY_SHA256[case_id])
    return summary


def run_mock(output: Path, *, scenario: dict[str, str] | None = None) -> dict[str, Any]:
    legacy, abc, freeze, scenarios, replies, summary_counts = build_runner()
    scenarios.update(scenario or {})
    history, questions, history_digest, questions_digest = abc.load_frozen_inputs()
    first_summaries = {case: frozen_summary_for_case(legacy, case) for case in CASE_MATRIX}

    # The historical helper accepts one first-summary string per Case.  Bind it
    # through a closure so each response is read from its own frozen live trace.
    old_transport_factory = legacy.mock_transport
    def case_transport(inner_abc, case_id, _ignored):
        return old_transport_factory(inner_abc, case_id, first_summaries[case_id])
    legacy.mock_transport = case_transport

    result = legacy.run_cases(
        abc, output, mode="MOCK", config=abc._mock_config(), api_key=MOCK_KEY,
    )
    for row in result.get("cases", []):
        row["fact_scope_diagnostics"] = _fact_diagnostics(
            row.get("case_id", ""), row.get("provider_stage_and_prompt_visibility", {}),
        )
    result.update({
        "schema_version": 2,
        "task": TASK,
        "base_sha": BASE_SHA,
        "candidate_head_at_run": _git("rev-parse", "HEAD"),
        "mode": "MOCK",
        "evidence_level": "ACTUAL_ASSISTANT_RUNTIME_AND_DOMAIN_WITH_HTTPX_MOCKTRANSPORT",
        "mock_reply_provenance": replies,
        "mock_response_count": len(replies),
        "summary_attempts_per_case": summary_counts,
        "provider_requests_sent": 0,
        "provider_cost_usd": "0.00",
        "external_mcp_calls": 0,
        "frozen_history_rows_per_case": len(history),
        "frozen_history_digest_sha256": history_digest,
        "frozen_questions_file_sha256": questions_digest,
        "frozen_questions_count": len(questions),
        "production_blob_pins": freeze["production_blobs"],
        "live_dispatch_available": False,
        "live_semantic_assessment": "NOT_RUN_MOCK_DOES_NOT_PROVE_MODEL_MEMORY",
    })
    result["case_matrix_passed"] = _mock_matrix_passed(result)
    result_path = output / "MOCK_RESULTS.json"
    abc.atomic_json(result_path, result)
    if result["case_matrix_passed"]:
        _write_provenance_gzip(output / "MOCK_REPLY_PROVENANCE.jsonl.gz", replies)
    return result


def _write_provenance_gzip(path: Path, records: list[dict[str, Any]]) -> None:
    with path.open("wb") as raw:
        with gzip.GzipFile(fileobj=raw, mode="wb", mtime=0) as stream:
            for record in records:
                stream.write((canonical(record) + "\n").encode("utf-8"))


def _mock_matrix_passed(results: dict[str, Any]) -> bool:
    if results.get("status") != "COMPLETED" or results.get("case_ids") not in (None, list(CASE_MATRIX)):
        return False
    if results.get("recorded_requests") != REQUEST_CAP or results.get("summary_requests") != 6 or results.get("answer_requests") != 3:
        return False
    cases = results.get("cases", [])
    if tuple(row.get("case_id") for row in cases) != CASE_MATRIX:
        return False
    if results.get("provider_requests_sent") != 0 or results.get("external_provider_requests") != 0:
        return False
    if len(results.get("mock_reply_provenance", [])) != REQUEST_CAP:
        return False
    for key in ("domain_instance_sha256", "checkpoint_instance_sha256", "session_id_sha256",
                "run_id_sha256", "runtime_grant_id_sha256"):
        if len({row.get(key) for row in cases}) != len(CASE_MATRIX) or any(not row.get(key) for row in cases):
            return False
    for row in cases:
        if row.get("status") != "SUCCEEDED" or row.get("answer_tool_choice") != "none":
            return False
        if row.get("answer_manifest_present", True) is False or row.get("mcp_attempts") != 0:
            return False
        if not row.get("runtime_binding_database_identity_matches"):
            return False
        if row.get("gold_payload_serialized") is not False or row.get("scoring_rule_serialized") is not False:
            return False
        if row.get("configured_input_limit_tokens") != MAX_INPUT_TOKENS:
            return False
        if not 0 < int(row.get("effective_context_input_budget_tokens") or 0) <= MAX_INPUT_TOKENS:
            return False
        if row.get("summary_calls") != 2 or row.get("answer_calls") != 1:
            return False
        persisted = row.get("persisted_summaries", [])
        if (len(persisted) != 2 or persisted[-1].get("state") != "CURRENT"
                or any(summary.get("state") not in {"CURRENT", "SUPERSEDED"} for summary in persisted)):
            return False
        if len(row.get("recorded_compression_attempt_states", [])) != 2:
            return False
        if any(item.get("status") != "SUCCEEDED" for item in row["recorded_compression_attempt_states"]):
            return False
        stages = row.get("provider_stage_and_prompt_visibility", {})
        if any(stages.get(key, {}).get("visibility") != "COMPLETE_TEXT_WITH_SOURCE"
               for key in ("first_persisted_summary", "second_summary_input", "second_model_summary", "final_answer_summary")):
            return False
        if row.get("fact_scope_diagnostics", {}).get("max_attempts_early_value_seq3", {}).get("status") == "COMPLETE":
            return False
        if row.get("case_id") == "Q06-B" and row.get("fact_scope_diagnostics", {}).get(
            "protocol_and_max_attempts_transition_seq11", {}
        ).get("status") != "COMPLETE_TEXT_WITH_SOURCE":
            return False
    return True


def reject_live_dispatch(*_args: Any, **_kwargs: Any) -> None:
    raise V2Stop("LIVE_DISPATCH_NOT_IMPLEMENTED_REQUIRES_SEPARATE_AUTHORIZATION_AND_RUNNER")


def block_external_network() -> None:
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
        raise OSError("AR04_V2_OFFLINE_NETWORK_GUARD")

    sys.addaudithook(audit)


def run_preflight(mock_results_path: Path, output_path: Path) -> dict[str, Any]:
    results = json.loads(mock_results_path.read_text(encoding="utf-8"))
    if not results.get("case_matrix_passed") or not _mock_matrix_passed(results):
        raise V2Stop("MOCK_ACCEPTANCE_REQUIRED_BEFORE_PREFLIGHT")
    _legacy, abc, freeze, *_ = build_runner()
    report = abc.run_zero_cost_preflight(mock_runner_passed=True)
    ready = bool(report.get("real_provider_send_condition"))
    report.update({
        "schema_version": 2,
        "task": TASK,
        "base_sha": BASE_SHA,
        "status": "READY_FOR_AUTHORIZATION" if ready else "BLOCKED_BEFORE_PROVIDER_SEND",
        "production_blob_pins": freeze["production_blobs"],
        "mock_results_sha256": sha256(mock_results_path.read_bytes()),
        "actual_provider_requests_sent": 0,
        "provider_cost_usd": "0.00",
        "external_mcp_calls": 0,
        "production_database_writes": 0,
        "live_dispatch_available": False,
        "authenticated_provider_check": "NOT_PERFORMED_NO_NETWORK_CALL",
        "api_key_value_recorded": False,
    })
    abc.atomic_json(output_path, report)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    # No live mode by design. Old authorization tokens are never accepted here.
    parser.add_argument("mode", choices=("mock", "preflight"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--mock-results", type=Path)
    args = parser.parse_args(argv)
    from opspilot.config import ROOT as OPSPILOT_ROOT
    block_external_network()
    if args.mode == "mock":
        result = run_mock(args.output)
        print(json.dumps({
            "status": result.get("status"),
            "case_matrix_passed": result.get("case_matrix_passed"),
            "mock_requests": result.get("recorded_requests"),
            "provider_requests_sent": 0,
        }))
        return 0 if result.get("case_matrix_passed") else 1
    if args.mock_results is None:
        parser.error("preflight requires --mock-results")
    report = run_preflight(args.mock_results, args.output)
    print(json.dumps({"status": report["status"], "provider_requests_sent": 0}))
    return 0 if report["status"] == "READY_FOR_AUTHORIZATION" else 1


if __name__ == "__main__":
    sys.exit(main())
