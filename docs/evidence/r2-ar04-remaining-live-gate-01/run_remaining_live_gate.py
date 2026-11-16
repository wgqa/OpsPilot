"""Version-bound AR-04 Q02-B/Q06-B live-gate runner.

The default modes are zero-cost.  The live path is present only behind a
fresh, exact-scope authorization manifest and re-runs Mock plus isolated Grant
preflight before any Provider transport can be constructed.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import gzip
import hashlib
import importlib.util
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

EVIDENCE_DIR = Path(__file__).resolve().parent
ROOT = EVIDENCE_DIR.parents[2]
V2_DIR = ROOT / "docs/evidence/r2-ar04-live-recheck-v2-prep-01"
if str(V2_DIR) not in sys.path:
    sys.path.insert(0, str(V2_DIR))
if str(EVIDENCE_DIR) not in sys.path:
    sys.path.insert(0, str(EVIDENCE_DIR))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import run_v2 as v2

TASK = "R2-AR04-REMAINING-LIVE-GATE-01"
BASE_SHA = "fa4cd8a7ea6dd36babccbbfc5fcdb7a179729fd3"
REVIEW_TASK_ID = "R2-AR04-LIVE-ADMISSION-HF-01"
REVIEW_BASE_SHA = "bf9e5d84f4aa2e57d1f195dbe7933d74c5586a3b"
CASE_MATRIX = ("Q02-B", "Q06-B")
SUMMARY_REQUEST_LIMIT = 4
ANSWER_REQUEST_LIMIT = 2
REQUEST_LIMIT = SUMMARY_REQUEST_LIMIT + ANSWER_REQUEST_LIMIT
MAX_INPUT_TOKENS = 12_000
SUMMARY_OUTPUT_TOKENS = 1_024
ANSWER_OUTPUT_TOKENS = 512
PERSISTED_SUMMARY_TOKENS = 512
HARD_CAP_USD_MICRO = 60_000
INPUT_RATE_MICRO_PER_MILLION = 300_000
OUTPUT_RATE_MICRO_PER_MILLION = 1_200_000
PRICE_URL = "https://api-docs.deepseek.com/quick_start/pricing/"
PRICE_VERSION = "deepseek-v4.1-flash-1017-peak-2026-11-15"
MODEL_VERSION = "DeepSeek-V4.1-Flash-1017"
CHAT_BLOB = "f78ff94586af56b94b9585c5e7f8abeb5b006ad6"
ASSISTANT_BLOB = "288559c6e9b77549939501f4cedb1a8097a79918"
ABC_RUNNER_PATH = ROOT / "docs/evidence/abc-live-env-unblock-01/run_abc_eval.py"
ABC_RUNNER_BLOB = "479c5f0e4724eea9dfa12ed025c438f3a9f9b85c"
MOCK_DIR = EVIDENCE_DIR / "mock_run_04"
MOCK_RESULTS_PATH = MOCK_DIR / "MOCK_RESULTS.json"
PREFLIGHT_PATH = EVIDENCE_DIR / "PREFLIGHT.json"
LIVE_RUN_PATH = EVIDENCE_DIR / "live_run_01"


class GateStop(RuntimeError):
    """A frozen input, budget or authorization boundary stopped the run."""


def _sha256(value: bytes | str) -> str:
    raw = value if isinstance(value, bytes) else value.encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _ceil_cost_micro(input_tokens: int, output_tokens: int) -> int:
    numerator = input_tokens * INPUT_RATE_MICRO_PER_MILLION + output_tokens * OUTPUT_RATE_MICRO_PER_MILLION
    return (numerator + 999_999) // 1_000_000


SUMMARY_REQUEST_RESERVE_USD_MICRO = _ceil_cost_micro(MAX_INPUT_TOKENS, SUMMARY_OUTPUT_TOKENS)
ANSWER_REQUEST_RESERVE_USD_MICRO = _ceil_cost_micro(MAX_INPUT_TOKENS, ANSWER_OUTPUT_TOKENS)
PURPOSE_MAX_RESERVE_USD_MICRO = (
    SUMMARY_REQUEST_LIMIT * SUMMARY_REQUEST_RESERVE_USD_MICRO
    + ANSWER_REQUEST_LIMIT * ANSWER_REQUEST_RESERVE_USD_MICRO
)
# A Grant with a 1024-token output ceiling reserves that envelope for each
# request, including answers.  This is the conservative shared Grant envelope.
GRANT_PER_CASE_RESERVE_USD_MICRO = 3 * SUMMARY_REQUEST_RESERVE_USD_MICRO
SHARED_GRANT_RESERVE_USD_MICRO = len(CASE_MATRIX) * GRANT_PER_CASE_RESERVE_USD_MICRO

PRICE_SNAPSHOT = {
    "evidence_level": "PRIOR_OFFICIAL_PROVIDER_DOCUMENTATION_SNAPSHOT",
    "provider": "DeepSeek",
    "model_alias": "deepseek-flash",
    "published_model_version": MODEL_VERSION,
    "pricing_url": PRICE_URL,
    "checked_on": "2026-11-15",
    "price_version": PRICE_VERSION,
    "input_cache_miss_usd_per_million": 0.30,
    "output_usd_per_million": 1.20,
    "pricing_must_be_rechecked_before_any_live_send": True,
}

FROZEN_SOURCE_FILES = {
    "questions": "docs/evidence/r2-ar04-long-context-journey-01/QUESTIONS.json",
    "history": "docs/evidence/r2-ar04-long-context-journey-01/HISTORY_SNAPSHOT.json",
    "gold_results": "docs/evidence/r2-ar04-long-context-journey-01/RESULTS.json",
    "abc_trace": "docs/evidence/abc-live-env-unblock-01/live_run_02/LIVE_REQUESTS.jsonl.gz",
    "q02b_truncated_trace": "docs/evidence/r2-ar04-live-recheck-v2-final-01/live_run_01/LIVE_REQUESTS.jsonl.gz",
}


def _git(*args: str) -> str:
    import subprocess
    return subprocess.check_output(
        ["git", "-c", "core.safecrlf=false", *args],
        cwd=ROOT, text=True, stderr=subprocess.STDOUT,
    ).strip()


def _task_assert_frozen() -> dict[str, Any]:
    if ROOT.resolve() != Path(v2.ROOT).resolve():
        raise GateStop("CHECKOUT_ROOT_DRIFT")
    try:
        _git("cat-file", "-e", f"{BASE_SHA}^{{commit}}")
        _git("merge-base", "--is-ancestor", BASE_SHA, "HEAD")
        _git("cat-file", "-e", f"{REVIEW_BASE_SHA}^{{commit}}")
        _git("merge-base", "--is-ancestor", REVIEW_BASE_SHA, "HEAD")
    except Exception as error:
        raise GateStop("TASK_BASE_MISSING_OR_NOT_ANCESTOR") from error
    if _git("rev-list", "--merges", f"{BASE_SHA}..HEAD"):
        raise GateStop("MERGE_AFTER_TASK_BASE_BLOCKED")
    allowed = f"docs/evidence/{EVIDENCE_DIR.name}/"
    review_evidence = "docs/evidence/r2-ar04-live-admission-hf01/"
    adapter_path = "docs/evidence/abc-live-env-unblock-01/run_abc_eval.py"
    for diff_args in (("diff", "--name-only", BASE_SHA, "--"),
                      ("diff", "--cached", "--name-only", BASE_SHA, "--")):
        changed = [p for p in _git(*diff_args).splitlines() if p]
        outside = [p for p in changed if not (
            p.startswith(allowed) or p.startswith(review_evidence) or p == adapter_path
        )]
        if outside:
            raise GateStop("TASK_DIFF_OUTSIDE_NEW_EVIDENCE:" + ",".join(outside))
    with _task_contract():
        freeze = v2.assert_frozen()
    if freeze["production_blobs"] != {
        "opspilot/domain/chat.py": CHAT_BLOB,
        "opspilot/assistant.py": ASSISTANT_BLOB,
    }:
        raise GateStop("CURRENT_PRODUCTION_BLOB_PIN_MISMATCH")
    actual_adapter_blob = _git("hash-object", f"--path={adapter_path}", adapter_path)
    if actual_adapter_blob != ABC_RUNNER_BLOB:
        raise GateStop("PROVIDER_ADAPTER_BLOB_DRIFT")
    governance = {
        "PROJECT_NORTH_STAR.md": "43dabda468506717c6956e676dfad4304c4f38e6",
        "AGENTS.md": "807b928686a4dd2cac7b15b3c354b9943c93c910",
        ".agents/skills/opspilot-slice-review/SKILL.md": "d405c8d413d633824b279202cc1503dab4cf0b03",
        "docs/baseline/v1.0-implementation-baseline.md": "30e18d7ddbade7cdf7712d035d6fd8488bcb9676",
    }
    actual = {path: _git("hash-object", f"--path={path}", path) for path in governance}
    if actual != governance:
        raise GateStop("GOVERNANCE_BLOB_DRIFT")
    return {
        "task_base_sha": BASE_SHA,
        "review_task_id": REVIEW_TASK_ID,
        "review_base_sha": REVIEW_BASE_SHA,
        "candidate_head_at_check": _git("rev-parse", "HEAD"),
        "production_blobs": freeze["production_blobs"],
        "provider_adapter_blob": actual_adapter_blob,
        "governance_blobs": actual,
        "frozen_input_sha256": freeze["frozen_input_sha256"],
        "protected_historical_files_match_base": all(
            row["matches_base"] for row in freeze["protected_historical_sha256"].values()
        ),
        "protected_paths_diff_from_base": freeze["protected_paths_diff_from_base"],
    }


@contextmanager
def _task_contract():
    names = (
        "BASE_SHA", "TASK", "CASE_MATRIX", "REQUEST_CAP", "MAX_OUTPUT_TOKENS",
        "SUMMARY_OUTPUT_CAP_TOKENS", "CHAT_BLOB", "ASSISTANT_BLOB", "FROZEN_REPLY_SOURCES",
        "_mock_matrix_passed", "build_runner", "PROTECTED_DIFF_PATHS",
    )
    previous = {name: getattr(v2, name) for name in names}
    adapter_scope = "docs/evidence/abc-live-env-unblock-01"
    if previous["PROTECTED_DIFF_PATHS"].count(adapter_scope) != 1:
        raise GateStop("V2_PROTECTED_PATH_LAYOUT_DRIFT")
    v2.BASE_SHA = BASE_SHA
    v2.TASK = TASK
    v2.CASE_MATRIX = CASE_MATRIX
    v2.REQUEST_CAP = REQUEST_LIMIT
    v2.MAX_OUTPUT_TOKENS = SUMMARY_OUTPUT_TOKENS
    v2.SUMMARY_OUTPUT_CAP_TOKENS = SUMMARY_OUTPUT_TOKENS
    v2.CHAT_BLOB = CHAT_BLOB
    v2.ASSISTANT_BLOB = ASSISTANT_BLOB
    v2.FROZEN_REPLY_SOURCES = {case: previous["FROZEN_REPLY_SOURCES"][case] for case in CASE_MATRIX}
    # The outer task gate permits only the exact adapter file in this directory;
    # remove the broad directory pathspec here so V2 can still enforce all other
    # protected paths and its pinned historical-file hashes.
    v2.PROTECTED_DIFF_PATHS = tuple(
        path for path in previous["PROTECTED_DIFF_PATHS"] if path != adapter_scope
    )
    v2._mock_matrix_passed = lambda result: _strict_mock_passed(
        result, require_task_metrics="request_caps" in result,
    )
    previous_builder = previous["build_runner"]

    def build_task_runner():
        legacy, abc, *rest = previous_builder()
        legacy.TASK = TASK
        legacy.BASE = BASE_SHA
        legacy.MATRIX = CASE_MATRIX
        legacy.REQUEST_CAP = REQUEST_LIMIT
        legacy.HARD_CAP_MICRO = HARD_CAP_USD_MICRO
        legacy.CHAT_BLOB = CHAT_BLOB
        abc.TASK = TASK
        abc.BASE_SHA = BASE_SHA
        abc.REQUEST_LIMIT = REQUEST_LIMIT
        abc.HARD_CAP_USD_MICRO = HARD_CAP_USD_MICRO
        abc.MAX_INPUT_TOKENS = MAX_INPUT_TOKENS
        abc.MAX_OUTPUT_TOKENS = SUMMARY_OUTPUT_TOKENS
        abc.REQUEST_RESERVE_USD_MICRO = SUMMARY_REQUEST_RESERVE_USD_MICRO
        abc.NON_SECRET_DEFAULTS.update({
            "OPSPILOT_MODEL_CONFIG_VERSION": "r2-ar04-remaining-live-gate-01-model-v1",
            "OPSPILOT_MODEL_PRICE_VERSION": PRICE_VERSION,
            "OPSPILOT_ASSISTANT_SERVICE_IDENTITY": "opspilot-isolated-r2-ar04-remaining-live-gate-01",
        })

        parent_transport = abc.BudgetedAsyncTransport
        class PurposeCappedTransport(parent_transport):
            def _validate_request(self, request, body):
                try:
                    payload = json.loads(body.decode("utf-8"))
                except Exception as error:
                    raise GateStop("REQUEST_BODY_INVALID_BEFORE_SEND") from error
                system = "\n".join(
                    str(item.get("content", "")) for item in payload.get("messages", [])
                    if isinstance(item, dict) and item.get("role") == "system"
                )
                is_summary = system.startswith("Compress only the supplied conversation")
                expected = SUMMARY_OUTPUT_TOKENS if is_summary else ANSWER_OUTPUT_TOKENS
                _assert_request_cap(payload, expected)
                _ACTIVE_METRICS["request_caps"].append({
                    "case_id": self.case_id,
                    "purpose": "SUMMARY" if is_summary else "ANSWER",
                    "max_tokens": expected,
                })
                if self.mode == "LIVE":
                    if _ACTIVE_AUTHORIZATION_PATH is None:
                        raise GateStop("TASK_SPECIFIC_AUTHORIZATION_NOT_BOUND")
                    load_authorization(_ACTIVE_AUTHORIZATION_PATH)
                    _task_assert_frozen()
                return super()._validate_request(request, body)

        abc.BudgetedAsyncTransport = PurposeCappedTransport
        original_grant = abc._grant_for_case
        def record_grant(*args, **kwargs):
            grant = original_grant(*args, **kwargs)
            _ACTIVE_METRICS["grants"].append({
                "case_id": args[2] if len(args) > 2 else kwargs["case_id"],
                "max_output_tokens": SUMMARY_OUTPUT_TOKENS,
                "total_limit_usd_micro": int(grant["total_limit_usd_micro"]),
                "grant_id_sha256": _sha256(str(grant["grant_id"])),
            })
            return grant
        abc._grant_for_case = record_grant

        # Runtime Grant grants 1024 to compression and the adapter keeps the
        # ordinary answer model at 512.  Production compression binds its own
        # 1024 cap in _compression_model.
        original_case = abc._run_case
        async def run_case_with_output_split(**kwargs):
            import opspilot.assistant as assistant_module
            original_factory = assistant_module.create_assistant_model
            def create_answer_512_model(*factory_args, **factory_kwargs):
                model = original_factory(*factory_args, **factory_kwargs)
                extra = getattr(model, "extra_body", None)
                if not isinstance(extra, dict) or extra.get("max_tokens") != SUMMARY_OUTPUT_TOKENS:
                    raise GateStop("RUNTIME_GRANT_MODEL_OUTPUT_CAP_NOT_1024")
                extra["max_tokens"] = ANSWER_OUTPUT_TOKENS
                return model
            assistant_module.create_assistant_model = create_answer_512_model
            try:
                return await original_case(**kwargs)
            finally:
                assistant_module.create_assistant_model = original_factory
        abc._run_case = run_case_with_output_split
        return (legacy, abc, *rest)

    v2.build_runner = build_task_runner
    try:
        yield
    finally:
        for name, value in previous.items():
            setattr(v2, name, value)


def _expected_source_manifest(freeze: dict[str, Any]) -> dict[str, Any]:
    with _task_contract():
        replies = v2.load_frozen_reply_sources()
    sources = {
        case: {key: value for key, value in replies[case].items() if key != "summary_text"}
        for case in CASE_MATRIX
    }
    return {
        "task": TASK,
        "base_sha": BASE_SHA,
        "production_blobs": freeze["production_blobs"],
        "case_reply_sources": sources,
        "q02b_truncated_negative_fixture": {
            "trace_path": FROZEN_SOURCE_FILES["q02b_truncated_trace"],
            "trace_sha256": "6c6d5b8d006c775a4393894b59ce5a8b722aa89a71c8ca427868a2b8c3db20e2",
            "provider_response_id": "9a2e0db7-153f-4419-91b2-416d2e7ef9ff",
            "content_sha256": "6c4da759c0c27112b4db6fa2984cd171c7e4420f7a006328be8a767c48e40f3d",
            "finish_reason": "length", "output_tokens": 512,
            "purpose": "negative_full_assistant_domain_replay_in_targeted_pytest",
        },
    }


def _assert_source_manifest(freeze: dict[str, Any] | None = None) -> str:
    freeze = freeze or _task_assert_frozen()
    path = EVIDENCE_DIR / "SOURCE_MANIFEST.json"
    if not path.is_file():
        raise GateStop("FROZEN_SOURCE_MANIFEST_MISSING")
    actual = json.loads(path.read_text(encoding="utf-8"))
    expected = _expected_source_manifest(freeze)
    if actual != expected:
        raise GateStop("FROZEN_SOURCE_MANIFEST_DRIFT")
    return _sha256(path.read_bytes())


_ACTIVE_METRICS: dict[str, list[dict[str, Any]]] = {"request_caps": [], "grants": []}
_ACTIVE_AUTHORIZATION_PATH: Path | None = None


def _target_fact_checks(result: dict[str, Any]) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    for row in result.get("cases", []):
        stages = row.get("provider_stage_and_prompt_visibility", {})
        final = stages.get("final_answer_summary", {})
        items = final.get("items", [])
        if row.get("case_id") == "Q02-B":
            matching = [item for item in items if 3 in item.get("source_sequences", [])
                        and "/callback" in str(item.get("text", ""))]
            passed = bool(matching and final.get("checks", {}).get("endpoint_seq3"))
            checks.append({"case_id": "Q02-B", "fact": "endpoint=/callback", "source_sequence": 3,
                           "present_in_final_prompt_with_source": passed})
        elif row.get("case_id") == "Q06-B":
            matching = [item for item in items if 11 in item.get("source_sequences", [])
                        and all(marker in str(item.get("text", ""))
                                 for marker in ("v1.2", "v1.3", "max_attempts", "3", "5"))]
            diag = row.get("fact_scope_diagnostics", {}).get("protocol_and_max_attempts_transition_seq11", {})
            passed = bool(matching and diag.get("status") == "COMPLETE_TEXT_WITH_SOURCE"
                          and final.get("checks", {}).get("explicit_ordered_transition_with_source"))
            checks.append({"case_id": "Q06-B", "facts": ["v1.2 -> v1.3", "max_attempts 3 -> 5"],
                           "source_sequence": 11, "present_in_final_prompt_with_source": passed,
                           "early_seq3_status": row.get("fact_scope_diagnostics", {}).get(
                               "max_attempts_early_value_seq3", {}).get("status")})
    if len(checks) != len(CASE_MATRIX) or not all(item["present_in_final_prompt_with_source"] for item in checks):
        raise GateStop("TARGET_FACTS_NOT_VISIBLE_WITH_VALID_SOURCE_IN_FINAL_PROMPT")
    return checks


def _persisted_summary_token_estimate(document: dict[str, Any]) -> int:
    from opspilot.domain.chat import _canonical
    from opspilot.domain.context_engineering import estimate_messages_tokens

    measured: dict[str, Any] = {}
    for key, value in document.items():
        if isinstance(value, dict):
            measured[key] = {item_key: item for item_key, item in value.items() if item_key != "sequence"}
        elif isinstance(value, list):
            measured[key] = [
                {item_key: item for item_key, item in entry.items() if item_key != "sequence"}
                if isinstance(entry, dict) else entry
                for entry in value
            ]
        else:
            measured[key] = value
    return estimate_messages_tokens([{"role": "system", "content": _canonical(measured)}])


def _strict_mock_passed(result: dict[str, Any], *, require_task_metrics: bool = True) -> bool:
    if result.get("status") != "COMPLETED":
        return False
    fact_checks = _target_fact_checks(result)
    if not fact_checks or not all(row["present_in_final_prompt_with_source"] for row in fact_checks):
        return False
    caps = result.get("request_caps", [])
    grants = result.get("runtime_grant_caps", [])
    expected = sorted(
        [(case, "SUMMARY", SUMMARY_OUTPUT_TOKENS) for case in CASE_MATRIX for _ in range(2)]
        + [(case, "ANSWER", ANSWER_OUTPUT_TOKENS) for case in CASE_MATRIX]
    )
    actual = sorted((item.get("case_id"), item.get("purpose"), item.get("max_tokens")) for item in caps)
    base_passed = bool(
        result.get("status") == "COMPLETED"
        and result.get("base_sha") == BASE_SHA
        and result.get("task") == TASK
        and tuple(row.get("case_id") for row in result.get("cases", [])) == CASE_MATRIX
        and result.get("recorded_requests") == REQUEST_LIMIT
        and result.get("summary_requests") == SUMMARY_REQUEST_LIMIT
        and result.get("answer_requests") == ANSWER_REQUEST_LIMIT
        and result.get("provider_requests_sent") == 0
        and result.get("external_provider_requests") == 0
        and result.get("external_mcp_calls") == 0
        and len(result.get("mock_reply_provenance", [])) == REQUEST_LIMIT
    )
    if not base_passed:
        return False
    if not require_task_metrics:
        return True
    return bool(
        actual == expected and result.get("review_task_id") == REVIEW_TASK_ID
        and len(grants) == len(CASE_MATRIX)
        and all(g.get("max_output_tokens") == SUMMARY_OUTPUT_TOKENS for g in grants)
        and sum(g.get("total_limit_usd_micro", 0) for g in grants) == SHARED_GRANT_RESERVE_USD_MICRO
        and result.get("runner_sha256") == _sha256(Path(__file__).read_bytes())
        and result.get("source_manifest_sha256") == _sha256((EVIDENCE_DIR / "SOURCE_MANIFEST.json").read_bytes())
        and all(len(row.get("persisted_summary_token_estimates", [])) == 2
                and all(0 <= tokens <= PERSISTED_SUMMARY_TOKENS
                        for tokens in row["persisted_summary_token_estimates"])
                for row in result.get("cases", []))
    )


def run_mock(output: Path = MOCK_DIR, *, scenario: dict[str, str] | None = None) -> dict[str, Any]:
    global _ACTIVE_METRICS
    freeze = _task_assert_frozen()
    source_manifest_sha256 = _assert_source_manifest(freeze)
    _ACTIVE_METRICS = {"request_caps": [], "grants": []}
    with _task_contract():
        result = v2.run_mock(output, scenario=scenario)
    if scenario:
        # Negative injections are validated by dedicated tests and are never
        # admitted as the preparation's success artifact.
        result["negative_injection_run"] = True
    else:
        result["target_fact_visibility"] = _target_fact_checks(result)
        for row in result.get("cases", []):
            row["persisted_summary_token_estimates"] = [
                _persisted_summary_token_estimate(summary["document"])
                for summary in row.get("persisted_summaries", [])
            ]
    result.update({
        "schema_version": 1,
        "task": TASK,
        "review_task_id": REVIEW_TASK_ID,
        "base_sha": BASE_SHA,
        "candidate_head_at_run": _git("rev-parse", "HEAD"),
        "runner_sha256": _sha256(Path(__file__).read_bytes()),
        "source_manifest_sha256": source_manifest_sha256,
        "request_caps": list(_ACTIVE_METRICS["request_caps"]),
        "runtime_grant_caps": list(_ACTIVE_METRICS["grants"]),
        "summary_generation_cap_tokens": SUMMARY_OUTPUT_TOKENS,
        "answer_request_cap_tokens": ANSWER_OUTPUT_TOKENS,
        "persisted_summary_cap_tokens": PERSISTED_SUMMARY_TOKENS,
        "shared_grant_reserve_usd_micro": SHARED_GRANT_RESERVE_USD_MICRO,
        "provider_requests_sent": 0,
        "provider_cost_usd": "0.00",
        "external_mcp_calls": 0,
        "live_dispatch_requires_fresh_task_authorization": True,
        "live_dispatch_performed": False,
        "live_semantic_assessment": "NOT_RUN_MOCK_DOES_NOT_PROVE_MODEL_MEMORY",
    })
    if not scenario:
        result["case_matrix_passed"] = _strict_mock_passed(result)
    out = output / "MOCK_RESULTS.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


AUTH_FIELDS = {
    "schema_version", "authorization_id", "task", "review_task_id", "base_sha", "actual_live_send_authorized",
    "authorized_at_utc", "expires_at_utc", "provider", "model_alias", "published_model_version",
    "case_order", "summary_request_limit", "answer_request_limit", "provider_request_limit",
    "hard_cap_usd_micro", "automatic_retries", "external_mcp", "tool_choice", "max_input_tokens_per_request",
    "summary_max_output_tokens_per_request", "answer_max_output_tokens_per_request",
    "runtime_grant_max_output_tokens", "persisted_summary_max_tokens", "price_snapshot", "artifact_pins",
}


def _parse_utc(value: Any, field: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise GateStop(f"AUTH_{field}_MUST_BE_UTC_ZULU")
    try:
        return datetime.fromisoformat(value[:-1] + "+00:00").astimezone(timezone.utc)
    except ValueError as error:
        raise GateStop(f"AUTH_{field}_INVALID") from error


def _validate_auth_hard_cap(value: Any) -> int:
    if type(value) is not int or not SHARED_GRANT_RESERVE_USD_MICRO <= value <= HARD_CAP_USD_MICRO:
        raise GateStop("AUTH_BUDGET_OUTSIDE_FROZEN_ENVELOPE")
    return value


def validate_authorization_manifest(manifest: dict[str, Any], *, now: datetime | None = None) -> dict[str, Any]:
    if not isinstance(manifest, dict):
        raise GateStop("TASK_SPECIFIC_LIVE_AUTHORIZATION_REQUIRED")
    if manifest.get("task") != TASK or manifest.get("base_sha") != BASE_SHA:
        raise GateStop("NEW_TASK_SPECIFIC_LIVE_AUTHORIZATION_REQUIRED")
    if set(manifest) != AUTH_FIELDS:
        raise GateStop("AUTH_MANIFEST_SCHEMA_MISMATCH")
    if manifest.get("review_task_id") != REVIEW_TASK_ID:
        raise GateStop("AUTH_REVIEW_TASK_ID_MISMATCH")
    if manifest.get("schema_version") != 1 or manifest.get("actual_live_send_authorized") is not True:
        raise GateStop("LIVE_SEND_CONSENT_REQUIRED")
    if not isinstance(manifest.get("authorization_id"), str) or not manifest["authorization_id"].strip():
        raise GateStop("AUTHORIZATION_ID_REQUIRED")
    if (manifest.get("provider") != "DeepSeek" or manifest.get("model_alias") != v2.MODEL
            or manifest.get("published_model_version") != MODEL_VERSION):
        raise GateStop("AUTH_PROVIDER_OR_MODEL_MISMATCH")
    if manifest.get("case_order") != list(CASE_MATRIX):
        raise GateStop("AUTH_CASE_MATRIX_MISMATCH")
    if (manifest.get("summary_request_limit") != SUMMARY_REQUEST_LIMIT
            or manifest.get("answer_request_limit") != ANSWER_REQUEST_LIMIT
            or manifest.get("provider_request_limit") != REQUEST_LIMIT):
        raise GateStop("AUTH_REQUEST_LIMIT_MISMATCH")
    if (manifest.get("automatic_retries") != 0 or manifest.get("external_mcp") is not False
            or manifest.get("tool_choice") != "none"):
        raise GateStop("AUTH_RETRY_MCP_OR_TOOL_BOUNDARY_MISMATCH")
    if (manifest.get("max_input_tokens_per_request") != MAX_INPUT_TOKENS
            or manifest.get("summary_max_output_tokens_per_request") != SUMMARY_OUTPUT_TOKENS
            or manifest.get("answer_max_output_tokens_per_request") != ANSWER_OUTPUT_TOKENS
            or type(manifest.get("runtime_grant_max_output_tokens")) is not int
            or manifest.get("runtime_grant_max_output_tokens") != SUMMARY_OUTPUT_TOKENS
            or manifest.get("persisted_summary_max_tokens") != PERSISTED_SUMMARY_TOKENS):
        raise GateStop("AUTH_TOKEN_LIMIT_MISMATCH")
    cap = _validate_auth_hard_cap(manifest.get("hard_cap_usd_micro"))
    now_utc = now or datetime.now(timezone.utc)
    authorized_at = _parse_utc(manifest.get("authorized_at_utc"), "AUTHORIZED_AT")
    expires_at = _parse_utc(manifest.get("expires_at_utc"), "EXPIRES_AT")
    if authorized_at > now_utc + timedelta(minutes=5) or now_utc - authorized_at > timedelta(hours=24):
        raise GateStop("AUTHORIZATION_EXPIRED_BY_AGE")
    if expires_at <= now_utc or expires_at <= authorized_at or expires_at - authorized_at > timedelta(hours=24):
        raise GateStop("AUTHORIZATION_EXPIRED_OR_VALIDITY_TOO_LONG")
    price = manifest.get("price_snapshot")
    if not isinstance(price, dict) or price.get("pricing_url") != PRICE_URL:
        raise GateStop("OFFICIAL_PRICE_SNAPSHOT_REQUIRED")
    checked = _parse_utc(price.get("checked_at_utc"), "PRICE_CHECKED_AT")
    if checked > now_utc + timedelta(minutes=5) or now_utc - checked > timedelta(hours=24):
        raise GateStop("OFFICIAL_PRICE_SNAPSHOT_STALE")
    if (price.get("provider") != "DeepSeek" or price.get("model_alias") != v2.MODEL
            or price.get("published_model_version") != MODEL_VERSION
            or not isinstance(price.get("price_version"), str) or not price["price_version"].strip()
            or float(price.get("input_cache_miss_usd_per_million", float("inf"))) > 0.30
            or float(price.get("output_usd_per_million", float("inf"))) > 1.20):
        raise GateStop("OFFICIAL_PRICE_EXCEEDS_RESERVED_ENVELOPE")
    pins = manifest.get("artifact_pins")
    if not isinstance(pins, dict) or set(pins) != {
        "runner_sha256", "mock_results_sha256", "source_manifest_sha256", "chat_blob", "assistant_blob",
        "provider_adapter_blob",
    }:
        raise GateStop("AUTH_ARTIFACT_PINS_SCHEMA_MISMATCH")
    current_pins = {
        "runner_sha256": _sha256(Path(__file__).read_bytes()),
        "mock_results_sha256": _sha256(MOCK_RESULTS_PATH.read_bytes()) if MOCK_RESULTS_PATH.is_file() else None,
        "source_manifest_sha256": _sha256((EVIDENCE_DIR / "SOURCE_MANIFEST.json").read_bytes())
        if (EVIDENCE_DIR / "SOURCE_MANIFEST.json").is_file() else None,
        "chat_blob": CHAT_BLOB,
        "assistant_blob": ASSISTANT_BLOB,
        "provider_adapter_blob": ABC_RUNNER_BLOB,
    }
    if pins != current_pins:
        raise GateStop("AUTH_ARTIFACT_OR_PRODUCTION_BLOB_DRIFT")
    return {
        "authorization_id_sha256": _sha256(manifest["authorization_id"]),
        "authorization_manifest_sha256": _sha256(json.dumps(manifest, sort_keys=True, ensure_ascii=False, separators=(",", ":"))),
        "valid_until_utc": expires_at.isoformat().replace("+00:00", "Z"),
        "hard_cap_usd_micro": cap,
        "shared_grant_worst_case_reserve_usd_micro": SHARED_GRANT_RESERVE_USD_MICRO,
        "price_checked_at_utc": checked.isoformat().replace("+00:00", "Z"),
    }


def load_authorization(path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    if not path.is_file():
        raise GateStop("NEW_TASK_SPECIFIC_LIVE_AUTHORIZATION_REQUIRED")
    manifest = json.loads(path.read_text(encoding="utf-8"))
    return manifest, validate_authorization_manifest(manifest)


def _mock_passed(path: Path) -> tuple[dict[str, Any], bool]:
    result = json.loads(path.read_text(encoding="utf-8"))
    valid = bool(result.get("case_matrix_passed") and _strict_mock_passed(result))
    valid = valid and result.get("task") == TASK and result.get("base_sha") == BASE_SHA
    valid = valid and result.get("review_task_id") == REVIEW_TASK_ID
    return result, valid


def run_preflight(mock_path: Path = MOCK_RESULTS_PATH, output_path: Path = PREFLIGHT_PATH) -> dict[str, Any]:
    freeze = _task_assert_frozen()
    _assert_source_manifest(freeze)
    mock, passed = _mock_passed(mock_path)
    if not passed:
        raise GateStop("FRESH_TWO_CASE_FULL_MOCK_REQUIRED_BEFORE_PREFLIGHT")
    import tempfile
    with tempfile.TemporaryDirectory(prefix="ar04-remaining-v2-preflight-") as temp:
        with _task_contract():
            raw = v2.run_preflight(mock_path, Path(temp) / "V2_PREFLIGHT_INTERNAL.json")
    env_ready = bool(raw.get("real_provider_send_condition"))
    budget_ready = PURPOSE_MAX_RESERVE_USD_MICRO <= SHARED_GRANT_RESERVE_USD_MICRO <= HARD_CAP_USD_MICRO
    legacy_probe = {"task": "R2-AR04-LIVE-RECHECK-V2-FINAL-01", "base_sha": "1f0b27b9f14686a4c33bd33c212bb5d7a007280e"}
    try:
        validate_authorization_manifest(legacy_probe)
    except GateStop as error:
        legacy_reuse_blocked = error.args[0] == "NEW_TASK_SPECIFIC_LIVE_AUTHORIZATION_REQUIRED"
        legacy_rejection = error.args[0]
    else:
        legacy_reuse_blocked = False
        legacy_rejection = "UNEXPECTEDLY_ACCEPTED"
    review_id_probe = {"task": REVIEW_TASK_ID, "base_sha": BASE_SHA}
    try:
        validate_authorization_manifest(review_id_probe)
    except GateStop as error:
        review_id_reuse_blocked = error.args[0] == "NEW_TASK_SPECIFIC_LIVE_AUTHORIZATION_REQUIRED"
        review_id_rejection = error.args[0]
    else:
        review_id_reuse_blocked = False
        review_id_rejection = "UNEXPECTEDLY_ACCEPTED"
    ready = bool(env_ready and budget_ready and legacy_reuse_blocked and review_id_reuse_blocked)
    report = {
        **raw,
        "schema_version": 1,
        "task": TASK,
        "review_task_id": REVIEW_TASK_ID,
        "base_sha": BASE_SHA,
        "status": "READY_FOR_NEW_LIVE_AUTHORIZATION" if ready else "BLOCKED_BEFORE_PROVIDER_SEND",
        "technical_preflight_passed": ready,
        "case_order": list(CASE_MATRIX),
        "request_limits": {"summary": SUMMARY_REQUEST_LIMIT, "answer": ANSWER_REQUEST_LIMIT, "total": REQUEST_LIMIT},
        "token_limits": {"input": MAX_INPUT_TOKENS, "summary_generation": SUMMARY_OUTPUT_TOKENS,
                         "answer": ANSWER_OUTPUT_TOKENS, "persisted_summary": PERSISTED_SUMMARY_TOKENS,
                         "runtime_grant_output": SUMMARY_OUTPUT_TOKENS},
        "budget": {
            "snapshot_evidence_level": PRICE_SNAPSHOT["evidence_level"],
            "price_snapshot": PRICE_SNAPSHOT,
            "summary_request_reserve_usd_micro": SUMMARY_REQUEST_RESERVE_USD_MICRO,
            "answer_request_reserve_usd_micro": ANSWER_REQUEST_RESERVE_USD_MICRO,
            "purpose_specific_total_usd_micro": PURPOSE_MAX_RESERVE_USD_MICRO,
            "grant_per_case_reserve_usd_micro": GRANT_PER_CASE_RESERVE_USD_MICRO,
            "shared_grant_reserve_usd_micro": SHARED_GRANT_RESERVE_USD_MICRO,
            "hard_cap_usd_micro": HARD_CAP_USD_MICRO,
            "headroom_usd_micro": HARD_CAP_USD_MICRO - SHARED_GRANT_RESERVE_USD_MICRO,
            "price_must_be_rechecked_before_live_send": True,
        },
        "mock_results_sha256": _sha256(mock_path.read_bytes()),
        "mock_case_matrix_passed": passed,
        "historical_authorization_reuse_blocked": legacy_reuse_blocked,
        "historical_authorization_rejection": legacy_rejection,
        "review_task_id_rejected_as_authorization_identity": review_id_reuse_blocked,
        "review_task_id_rejection": review_id_rejection,
        "new_authorization_created": False,
        "actual_provider_requests_sent": 0,
        "provider_requests_sent": 0,
        "provider_cost_usd": "0.00",
        "external_mcp_calls": 0,
        "production_database_writes": 0,
        "live_dispatch_performed": False,
        "authenticated_provider_check": "NOT_PERFORMED_ZERO_COST_PREFLIGHT",
        "current_official_price_rechecked_this_task": False,
        "evidence_level": "MOCK_RUNTIME_GRANT_PREFLIGHT_AND_FROZEN_PRIOR_PRICE_ARITHMETIC",
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def run_live(authorization_path: Path, *, mock_path: Path = MOCK_RESULTS_PATH,
             output_path: Path = LIVE_RUN_PATH) -> dict[str, Any]:
    global _ACTIVE_AUTHORIZATION_PATH, _ACTIVE_METRICS
    _task_assert_frozen()
    manifest, auth_summary = load_authorization(authorization_path)
    mock, passed = _mock_passed(mock_path)
    if manifest["artifact_pins"]["mock_results_sha256"] != _sha256(mock_path.read_bytes()):
        raise GateStop("AUTH_MOCK_RESULT_DIGEST_MISMATCH")
    if not passed:
        raise GateStop("FRESH_TWO_CASE_FULL_MOCK_REQUIRED_BEFORE_LIVE")
    if output_path.exists():
        raise GateStop("LIVE_OUTPUT_ALREADY_EXISTS_REFUSE_RESUME_OR_OVERWRITE")
    import tempfile
    with tempfile.TemporaryDirectory(prefix="ar04-remaining-preflight-") as temp:
        preflight = run_preflight(mock_path, Path(temp) / "PREFLIGHT.json")
    if not preflight.get("technical_preflight_passed"):
        raise GateStop("CURRENT_ZERO_COST_RUNTIME_PREFLIGHT_FAILED")
    load_authorization(authorization_path)
    _task_assert_frozen()
    _ACTIVE_AUTHORIZATION_PATH = authorization_path
    _ACTIVE_METRICS = {"request_caps": [], "grants": []}
    try:
        with _task_contract():
            legacy, abc, *_ = v2.build_runner()
            config = abc._case_config_from_env()
            result = legacy.run_cases(
                abc, output_path, mode="LIVE", config=config,
                api_key=os.environ["OPSPILOT_MODEL_API_KEY"],
                authorized_task=TASK,
                live_preflight={"technical_preflight_passed": True, **preflight},
            )
        result.update({
            "task": TASK, "review_task_id": REVIEW_TASK_ID, "base_sha": BASE_SHA,
            "authorization_manifest_sha256": auth_summary["authorization_manifest_sha256"],
            "request_caps": list(_ACTIVE_METRICS["request_caps"]),
            "runtime_grant_caps": list(_ACTIVE_METRICS["grants"]),
            "live_dispatch_performed": True,
            "semantic_assessment": "IMPLEMENTER_PRELIMINARY_REVIEW_PENDING",
            "independent_main_agent_review": "NOT_PERFORMED",
        })
        (output_path / "LIVE_RESULTS.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return result
    finally:
        _ACTIVE_AUTHORIZATION_PATH = None


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _assert_request_cap(payload: dict[str, Any], expected_tokens: int) -> None:
    if payload.get("max_tokens") != expected_tokens:
        raise GateStop("PURPOSE_OUTPUT_TOKEN_CAP_MISMATCH")


def prepare() -> dict[str, Any]:
    if MOCK_DIR.exists() or PREFLIGHT_PATH.exists():
        raise GateStop("PREPARATION_OUTPUT_EXISTS_REFUSE_OVERWRITE")
    freeze = _task_assert_frozen()
    _write_json(EVIDENCE_DIR / "SOURCE_MANIFEST.json", _expected_source_manifest(freeze))
    result = run_mock(MOCK_DIR)
    if not result.get("case_matrix_passed"):
        _write_json(EVIDENCE_DIR / "MOCK_RESULTS.json", result)
        raise GateStop("TWO_CASE_FULL_MOCK_DID_NOT_PASS")
    preflight = run_preflight(MOCK_RESULTS_PATH, PREFLIGHT_PATH)
    _write_json(EVIDENCE_DIR / "BUDGET.json", preflight["budget"])
    _write_json(EVIDENCE_DIR / "FREEZE.json", freeze)
    _write_json(EVIDENCE_DIR / "FAILURE_MATRIX.json", {
        "task": TASK, "provider_requests": 0, "cost_usd": "0.00",
        "cases": {
            "Q02-B": "FULL_MOCK_PASS; historical source reply; endpoint target visible with source",
            "Q06-B": "FULL_MOCK_PASS; historical source reply; version transition visible with source; early seq3 PARTIAL",
        },
        "truncation": "Historical finish_reason=length fixture must stop before persistence and answer; targeted pytest result recorded in TEST_RUN.txt.",
        "source_revocation": "Targeted failure-injection test must stop answer and following case.",
        "unknown_send": "Targeted failure-injection test must reserve UNKNOWN, never retry, never start next case.",
        "historical_authorization": "Rejected by exact new task/base check; no authorization file generated.",
        "unresolved": ["Current official price was not rechecked because this task performs no live send.",
                       "No real Provider response or L3 semantic score is produced."],
    })
    return {
        "status": preflight["status"], "mock_cases_passed": sum(
            row.get("status") == "SUCCEEDED" for row in result.get("cases", [])),
        "mock_requests": result.get("recorded_requests"), "provider_requests_sent": 0,
        "provider_cost_usd": "0.00", "new_authorization_created": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("mock", "preflight", "prepare", "live"))
    parser.add_argument("--output", type=Path)
    parser.add_argument("--mock-results", type=Path, default=MOCK_RESULTS_PATH)
    parser.add_argument("--authorization", type=Path)
    args = parser.parse_args(argv)
    if args.mode == "mock":
        result = run_mock(args.output or MOCK_DIR)
    elif args.mode == "preflight":
        result = run_preflight(args.mock_results, args.output or PREFLIGHT_PATH)
    elif args.mode == "prepare":
        result = prepare()
    else:
        if args.authorization is None:
            raise GateStop("NEW_TASK_SPECIFIC_LIVE_AUTHORIZATION_REQUIRED")
        result = run_live(args.authorization, mock_path=args.mock_results,
                          output_path=args.output or LIVE_RUN_PATH)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    if args.mode in {"prepare", "preflight"}:
        return 0 if result.get("status") == "READY_FOR_NEW_LIVE_AUTHORIZATION" else 1
    if args.mode == "mock":
        return 0 if result.get("case_matrix_passed") else 1
    return 0 if result.get("status") == "COMPLETED" else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except GateStop as error:
        print(json.dumps({"status": "BLOCKED", "reason": str(error)}))
        sys.exit(2)
