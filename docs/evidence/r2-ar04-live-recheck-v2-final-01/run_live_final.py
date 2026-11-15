"""Final, authorization-gated AR-04 live recheck entry point.

The default preparation path is strictly zero-provider. Live mode is only
available with a fresh task-specific authorization manifest and re-runs the
Mock and zero-cost Runtime Grant preflight before creating a network transport.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import json
import os
import sys
import tempfile
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


TASK = "R2-AR04-LIVE-RECHECK-V2-FINAL-01"
TASK_BASE_SHA = "1f0b27b9f14686a4c33bd33c212bb5d7a007280e"
CASE_MATRIX = ("Q02-A", "Q02-B", "Q06-B")
REQUEST_LIMIT = 9
SUMMARY_LIMIT = 6
ANSWER_LIMIT = 3
HARD_CAP_USD_MICRO = 60_000
INPUT_RATE_USD_PER_MILLION = 0.30
OUTPUT_RATE_USD_PER_MILLION = 1.20
INPUT_RATE_USD_MICRO_PER_MILLION = 300_000
OUTPUT_RATE_USD_MICRO_PER_MILLION = 1_200_000
REQUEST_RESERVE_USD_MICRO = (
    v2.MAX_INPUT_TOKENS * INPUT_RATE_USD_MICRO_PER_MILLION
    + v2.MAX_OUTPUT_TOKENS * OUTPUT_RATE_USD_MICRO_PER_MILLION
    + 999_999
) // 1_000_000
TOTAL_WORST_CASE_RESERVE_USD_MICRO = REQUEST_LIMIT * REQUEST_RESERVE_USD_MICRO
PRICE_URL = "https://api-docs.deepseek.com/quick_start/pricing/"
PRICE_CHECKED_ON = "2026-11-15"
PRICE_VERSION = "deepseek-v4.1-flash-1017-peak-2026-11-15"
MODEL_VERSION = "DeepSeek-V4.1-Flash-1017"
MOCK_DIR = EVIDENCE_DIR / "mock_run_03"
MOCK_RESULTS_PATH = MOCK_DIR / "MOCK_RESULTS.json"
PREFLIGHT_PATH = EVIDENCE_DIR / "PREFLIGHT.json"
LIVE_RUN_PATH = EVIDENCE_DIR / "live_run_01"


class FinalRunnerStop(RuntimeError):
    """A frozen-contract or authorization boundary stopped the run."""


@contextmanager
def _final_v2_contract():
    """Bind the accepted V2 adapter to this task without editing its source."""
    previous_base = v2.BASE_SHA
    previous_task = v2.TASK
    previous_builder = v2.build_runner
    v2.BASE_SHA = TASK_BASE_SHA
    v2.TASK = TASK

    def build_final_runner():
        legacy, abc, *rest = previous_builder()
        legacy.TASK = TASK
        legacy.BASE = TASK_BASE_SHA
        legacy.MATRIX = CASE_MATRIX
        legacy.REQUEST_CAP = REQUEST_LIMIT
        legacy.CHAT_BLOB = v2.CHAT_BLOB
        abc.TASK = TASK
        abc.BASE_SHA = TASK_BASE_SHA
        abc.NON_SECRET_DEFAULTS.update({
            "OPSPILOT_MODEL_CONFIG_VERSION": "r2-ar04-live-recheck-v2-final-01-model-v1",
            "OPSPILOT_MODEL_PRICE_VERSION": PRICE_VERSION,
            "OPSPILOT_ASSISTANT_SERVICE_IDENTITY": "opspilot-isolated-ar04-live-recheck-v2-final-01",
        })
        return (legacy, abc, *rest)

    v2.build_runner = build_final_runner
    try:
        yield
    finally:
        v2.BASE_SHA = previous_base
        v2.TASK = previous_task
        v2.build_runner = previous_builder


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso_utc(value: datetime | None = None) -> str:
    return (value or _utc_now()).isoformat(timespec="seconds").replace("+00:00", "Z")


def _parse_utc(value: Any, label: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise FinalRunnerStop(f"AUTH_{label}_MUST_BE_UTC_ZULU")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as error:
        raise FinalRunnerStop(f"AUTH_{label}_INVALID") from error
    return parsed.astimezone(timezone.utc)


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha256(value: bytes | str) -> str:
    import hashlib

    raw = value if isinstance(value, bytes) else value.encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _git(*args: str) -> str:
    import subprocess

    return subprocess.check_output(
        ["git", *args], cwd=ROOT, text=True, stderr=subprocess.STDOUT,
    ).strip()


def _atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def assert_final_frozen() -> dict[str, Any]:
    """Require the exact task base ancestry and evidence-only task diff."""
    accepted = v2.assert_frozen()
    try:
        _git("cat-file", "-e", f"{TASK_BASE_SHA}^{{commit}}")
        _git("merge-base", "--is-ancestor", TASK_BASE_SHA, "HEAD")
    except Exception as error:
        raise FinalRunnerStop("FINAL_TASK_BASE_MISSING_OR_NOT_ANCESTOR") from error
    if _git("rev-list", "--merges", f"{TASK_BASE_SHA}..HEAD"):
        raise FinalRunnerStop("MERGE_COMMIT_AFTER_FINAL_TASK_BASE_BLOCKED")

    allowed_prefix = "docs/evidence/r2-ar04-live-recheck-v2-final-01/"
    changed = _git("diff", "--name-only", TASK_BASE_SHA, "--").splitlines()
    outside = [path for path in changed if path and not path.startswith(allowed_prefix)]
    if outside:
        raise FinalRunnerStop("FINAL_TASK_DIFF_OUTSIDE_EVIDENCE:" + ",".join(outside))

    governance = {
        "PROJECT_NORTH_STAR.md": "43dabda468506717c6956e676dfad4304c4f38e6",
        "AGENTS.md": "807b928686a4dd2cac7b15b3c354b9943c93c910",
        ".agents/skills/opspilot-slice-review/SKILL.md": "d405c8d413d633824b279202cc1503dab4cf0b03",
        "docs/baseline/v1.0-implementation-baseline.md": "30e18d7ddbade7cdf7712d035d6fd8488bcb9676",
    }
    actual = {}
    for rel, expected in governance.items():
        blob = _git("hash-object", f"--path={rel}", rel)
        if blob != expected:
            raise FinalRunnerStop(f"GOVERNANCE_BLOB_DRIFT:{rel}")
        actual[rel] = blob
    return {
        "task_base_sha": TASK_BASE_SHA,
        "head_sha": _git("rev-parse", "HEAD"),
        "accepted_v2_base_sha": accepted["base_sha"],
        "governance_blobs": actual,
        "production_blobs": accepted["production_blobs"],
        "protected_historical_paths_match": all(
            item["matches_base"] for item in accepted["protected_historical_sha256"].values()
        ),
        "merge_after_task_base": False,
        "changed_paths_outside_new_evidence": outside,
    }


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise FinalRunnerStop(f"JSON_OBJECT_REQUIRED:{path.name}")
    return value


def _price_snapshot() -> dict[str, Any]:
    return {
        "evidence_level": "OFFICIAL_PROVIDER_DOCUMENTATION_SNAPSHOT",
        "provider": "DeepSeek",
        "model_alias": v2.MODEL,
        "published_model_version": MODEL_VERSION,
        "pricing_url": PRICE_URL,
        "checked_on": PRICE_CHECKED_ON,
        "price_version": PRICE_VERSION,
        "input_cache_miss_usd_per_million": INPUT_RATE_USD_PER_MILLION,
        "output_usd_per_million": OUTPUT_RATE_USD_PER_MILLION,
        "pricing_must_be_rechecked_before_any_live_send": True,
    }


def _mock_passed(path: Path) -> tuple[dict[str, Any], bool]:
    result = _load_json(path)
    passed = bool(result.get("case_matrix_passed") and v2._mock_matrix_passed(result))
    if result.get("task") != TASK or result.get("base_sha") != TASK_BASE_SHA or result.get("mode") != "MOCK":
        passed = False
    if result.get("provider_requests_sent") != 0 or result.get("external_mcp_calls") != 0:
        passed = False
    return result, passed


def run_mock(output: Path = MOCK_DIR) -> dict[str, Any]:
    assert_final_frozen()
    with _final_v2_contract():
        result = v2.run_mock(output)
    result["final_task"] = TASK
    result["final_task_base_sha"] = TASK_BASE_SHA
    result["mock_only_not_live_acceptance"] = True
    result["live_semantic_result"] = "NOT_RUN"
    result["live_dispatch_available"] = True
    result["live_dispatch_requires_fresh_task_authorization"] = True
    result["live_dispatch_performed"] = False
    _atomic_json(output / "MOCK_RESULTS.json", result)
    return result


def _normalize_preflight(
    report: dict[str, Any], *, mock_results_sha256: str, checked_at: str,
) -> dict[str, Any]:
    ready = bool(report.get("real_provider_send_condition"))
    within_budget = TOTAL_WORST_CASE_RESERVE_USD_MICRO <= HARD_CAP_USD_MICRO
    normalized = {
        **report,
        "schema_version": 1,
        "task": TASK,
        "base_sha": TASK_BASE_SHA,
        "status": "READY_FOR_LIVE_AUTHORIZATION" if ready and within_budget else "BLOCKED_BEFORE_PROVIDER_SEND",
        "technical_preflight_passed": bool(ready and within_budget),
        "case_order": list(CASE_MATRIX),
        "provider": "DeepSeek",
        "model_alias": v2.MODEL,
        "published_model_version": MODEL_VERSION,
        "request_limits": {"summary": SUMMARY_LIMIT, "answer": ANSWER_LIMIT, "total": REQUEST_LIMIT},
        "hard_cap_usd_micro": HARD_CAP_USD_MICRO,
        "per_request_worst_case_reserve_usd_micro": REQUEST_RESERVE_USD_MICRO,
        "total_worst_case_reserve_usd_micro": TOTAL_WORST_CASE_RESERVE_USD_MICRO,
        "price_snapshot": _price_snapshot(),
        "mock_results_sha256": mock_results_sha256,
        "checked_at_utc": checked_at,
        "actual_provider_requests_sent": 0,
        "provider_requests_sent": 0,
        "provider_cost_usd": "0.00",
        "external_mcp_calls": 0,
        "production_database_writes": 0,
        "live_dispatch_performed": False,
        "authorization_gated_live_entry_available": True,
        "authenticated_provider_check": "NOT_PERFORMED_NO_NETWORK_CALL",
        "api_key_value_recorded": False,
    }
    normalized.pop("real_provider_send_condition", None)
    normalized.pop("live_dispatch_available", None)
    return normalized


def run_preflight(mock_path: Path = MOCK_RESULTS_PATH, output: Path = PREFLIGHT_PATH) -> dict[str, Any]:
    assert_final_frozen()
    mock, passed = _mock_passed(mock_path)
    if not passed:
        raise FinalRunnerStop("FRESH_FULL_MOCK_REQUIRED_BEFORE_PREFLIGHT")
    with _final_v2_contract():
        raw = v2.run_preflight(mock_path, output)
    report = _normalize_preflight(
        raw, mock_results_sha256=_sha256(mock_path.read_bytes()), checked_at=_iso_utc(),
    )
    _atomic_json(output, report)
    return report


AUTH_FIELDS = {
    "schema_version", "authorization_id", "task", "base_sha", "actual_live_send_authorized",
    "authorized_at_utc", "expires_at_utc", "provider", "model_alias", "published_model_version",
    "case_order", "summary_request_limit", "answer_request_limit", "provider_request_limit",
    "hard_cap_usd_micro", "automatic_retries", "external_mcp", "tool_choice",
    "max_input_tokens_per_request", "max_output_tokens_per_request", "price_snapshot",
}


def validate_authorization_manifest(
    manifest: dict[str, Any], *, now: datetime | None = None,
) -> dict[str, Any]:
    """Validate a fresh, exact-scope authorization without sending anything."""
    if set(manifest) != AUTH_FIELDS:
        raise FinalRunnerStop("AUTH_MANIFEST_SCHEMA_MISMATCH")
    if manifest.get("schema_version") != 1 or manifest.get("task") != TASK:
        raise FinalRunnerStop("NEW_TASK_SPECIFIC_LIVE_AUTHORIZATION_REQUIRED")
    if manifest.get("base_sha") != TASK_BASE_SHA or manifest.get("actual_live_send_authorized") is not True:
        raise FinalRunnerStop("AUTHORIZATION_BASE_OR_LIVE_CONSENT_MISMATCH")
    authorization_id = manifest.get("authorization_id")
    if not isinstance(authorization_id, str) or not authorization_id.strip():
        raise FinalRunnerStop("AUTHORIZATION_ID_REQUIRED")
    if manifest.get("provider") != "DeepSeek" or manifest.get("model_alias") != v2.MODEL:
        raise FinalRunnerStop("AUTHORIZATION_PROVIDER_OR_MODEL_MISMATCH")
    if manifest.get("published_model_version") != MODEL_VERSION:
        raise FinalRunnerStop("AUTHORIZATION_PUBLISHED_MODEL_VERSION_MISMATCH")
    if manifest.get("case_order") != list(CASE_MATRIX):
        raise FinalRunnerStop("AUTHORIZATION_CASE_MATRIX_MISMATCH")
    if (manifest.get("summary_request_limit") != SUMMARY_LIMIT
            or manifest.get("answer_request_limit") != ANSWER_LIMIT
            or manifest.get("provider_request_limit") != REQUEST_LIMIT):
        raise FinalRunnerStop("AUTHORIZATION_REQUEST_LIMIT_MISMATCH")
    if type(manifest.get("hard_cap_usd_micro")) is not int or not 0 < manifest["hard_cap_usd_micro"] <= HARD_CAP_USD_MICRO:
        raise FinalRunnerStop("AUTHORIZATION_HARD_CAP_EXCEEDS_TASK_LIMIT")
    if manifest.get("automatic_retries") != 0 or manifest.get("external_mcp") is not False:
        raise FinalRunnerStop("AUTHORIZATION_RETRY_OR_EXTERNAL_MCP_BOUNDARY_MISMATCH")
    if manifest.get("tool_choice") != "none":
        raise FinalRunnerStop("AUTHORIZATION_TOOL_CHOICE_MISMATCH")
    if (manifest.get("max_input_tokens_per_request") != v2.MAX_INPUT_TOKENS
            or manifest.get("max_output_tokens_per_request") != v2.MAX_OUTPUT_TOKENS):
        raise FinalRunnerStop("AUTHORIZATION_TOKEN_LIMIT_MISMATCH")

    price = manifest.get("price_snapshot")
    if not isinstance(price, dict) or set(price) != {
        "pricing_url", "checked_at_utc", "input_cache_miss_usd_per_million", "output_usd_per_million",
        "model_alias", "published_model_version",
    }:
        raise FinalRunnerStop("AUTHORIZATION_PRICE_SNAPSHOT_SCHEMA_MISMATCH")
    if (price.get("pricing_url") != PRICE_URL or price.get("model_alias") != v2.MODEL
            or price.get("published_model_version") != MODEL_VERSION
            or price.get("input_cache_miss_usd_per_million") != INPUT_RATE_USD_PER_MILLION
            or price.get("output_usd_per_million") != OUTPUT_RATE_USD_PER_MILLION):
        raise FinalRunnerStop("AUTHORIZATION_PRICE_SNAPSHOT_DRIFT")

    now_utc = (now or _utc_now()).astimezone(timezone.utc)
    authorized_at = _parse_utc(manifest.get("authorized_at_utc"), "AUTHORIZED_AT")
    expires_at = _parse_utc(manifest.get("expires_at_utc"), "EXPIRES_AT")
    price_checked_at = _parse_utc(price.get("checked_at_utc"), "PRICE_CHECKED_AT")
    if authorized_at > now_utc + timedelta(minutes=5):
        raise FinalRunnerStop("AUTHORIZATION_TIMESTAMP_IN_FUTURE")
    if now_utc - authorized_at > timedelta(hours=24):
        raise FinalRunnerStop("AUTHORIZATION_EXPIRED_BY_AGE")
    if expires_at <= now_utc or expires_at <= authorized_at or expires_at - authorized_at > timedelta(hours=24):
        raise FinalRunnerStop("AUTHORIZATION_EXPIRED_OR_VALIDITY_TOO_LONG")
    if price_checked_at > now_utc + timedelta(minutes=5) or now_utc - price_checked_at > timedelta(hours=24):
        raise FinalRunnerStop("OFFICIAL_PRICE_SNAPSHOT_STALE")
    worst_case = REQUEST_LIMIT * REQUEST_RESERVE_USD_MICRO
    if worst_case > manifest["hard_cap_usd_micro"]:
        raise FinalRunnerStop("AUTHORIZED_BUDGET_BELOW_WORST_CASE_RESERVE")
    return {
        "authorization_id_sha256": _sha256(authorization_id),
        "authorization_manifest_sha256": _sha256(_canonical(manifest)),
        "valid_until_utc": _iso_utc(expires_at),
        "price_checked_at_utc": _iso_utc(price_checked_at),
        "hard_cap_usd_micro": manifest["hard_cap_usd_micro"],
        "worst_case_reserve_usd_micro": worst_case,
    }


def load_authorization(path: Path, *, now: datetime | None = None) -> tuple[dict[str, Any], dict[str, Any]]:
    if not path.is_file():
        raise FinalRunnerStop("NEW_TASK_SPECIFIC_LIVE_AUTHORIZATION_REQUIRED")
    manifest = _load_json(path)
    return manifest, validate_authorization_manifest(manifest, now=now)


def bind_authorized_global_cap(legacy: Any, manifest: dict[str, Any]) -> int:
    """Apply the manifest's cap to the reused one-ledger live runner."""
    cap = manifest.get("hard_cap_usd_micro")
    if type(cap) is not int or not 0 < cap <= HARD_CAP_USD_MICRO:
        raise FinalRunnerStop("AUTHORIZATION_HARD_CAP_EXCEEDS_TASK_LIMIT")
    if TOTAL_WORST_CASE_RESERVE_USD_MICRO > cap:
        raise FinalRunnerStop("AUTHORIZED_BUDGET_BELOW_WORST_CASE_RESERVE")
    # run_recheck.run_cases passes its module HARD_CAP_MICRO to the shared
    # GlobalBudgetLedger. Bind it to this authorization before ledger creation.
    legacy.HARD_CAP_MICRO = cap
    return cap


def _fresh_zero_cost_preflight(
    mock_path: Path, *, output_path: Path,
) -> tuple[Any, Any, dict[str, Any]]:
    with _final_v2_contract():
        legacy, abc, freeze, *_ = v2.build_runner()
    for key in abc.REQUIRED_ENV:
        os.environ.pop(key, None)
    mock, passed = _mock_passed(mock_path)
    raw = abc.run_zero_cost_preflight(mock_runner_passed=passed)
    report = _normalize_preflight(
        raw, mock_results_sha256=_sha256(mock_path.read_bytes()), checked_at=_iso_utc(),
    )
    report["production_blob_pins"] = freeze["production_blobs"]
    report["final_task_freeze"] = assert_final_frozen()
    _atomic_json(output_path, report)
    return legacy, abc, report


def run_live(
    authorization_path: Path, *, mock_path: Path = MOCK_RESULTS_PATH,
    live_output: Path = LIVE_RUN_PATH,
) -> dict[str, Any]:
    """Run only with a fresh, exact-scope manifest; this function is not used in prep."""
    assert_final_frozen()
    manifest, auth_summary = load_authorization(authorization_path)
    mock, passed = _mock_passed(mock_path)
    if not passed:
        raise FinalRunnerStop("MOCK_ACCEPTANCE_REQUIRED_BEFORE_LIVE")
    if live_output.exists():
        raise FinalRunnerStop("LIVE_RUN_ALREADY_EXISTS_REFUSE_RESUME_OR_OVERWRITE")

    with tempfile.TemporaryDirectory(prefix="ar04-final-preflight-") as temporary:
        temp_report = Path(temporary) / "PREFLIGHT.json"
        legacy, abc, report = _fresh_zero_cost_preflight(mock_path, output_path=temp_report)
        if not report.get("technical_preflight_passed"):
            blocked = {
                **report, "status": "BLOCKED_BEFORE_PROVIDER_SEND",
                "live_dispatch_performed": False, "authorization": auth_summary,
            }
            _atomic_json(EVIDENCE_DIR / "LIVE_PREFLIGHT_BLOCKED.json", blocked)
            return blocked

    # Recheck auth and frozen code immediately before building the live transport.
    _manifest_again, auth_summary = load_authorization(authorization_path)
    assert_final_frozen()
    bind_authorized_global_cap(legacy, _manifest_again)
    parent_transport = abc.BudgetedAsyncTransport

    class FreshAuthorizedTransport(parent_transport):
        def _validate_request(self, request, body):
            load_authorization(authorization_path)
            assert_final_frozen()
            return super()._validate_request(request, body)

    abc.BudgetedAsyncTransport = FreshAuthorizedTransport
    live_preflight = {
        **report,
        "technical_preflight_passed": True,
        "status": "AUTHORIZED_FOR_BOUNDED_LIVE_EXECUTION",
        "actual_live_send_authorized": True,
        "authorization": auth_summary,
    }
    config = abc._case_config_from_env()
    result = legacy.run_cases(
        abc, live_output, mode="LIVE", config=config,
        api_key=os.environ["OPSPILOT_MODEL_API_KEY"],
        authorized_task=TASK, live_preflight=live_preflight,
    )
    result["authorization_manifest_sha256"] = auth_summary["authorization_manifest_sha256"]
    result["live_semantic_assessment"] = "IMPLEMENTER_PRELIMINARY_REVIEW_PENDING"
    result["independent_main_agent_review"] = "NOT_PERFORMED"
    _atomic_json(live_output / "LIVE_RESULTS.json", result)
    return result


def create_frozen_input_manifest(path: Path) -> dict[str, Any]:
    freeze = assert_final_frozen()
    source_hashes = v2.assert_frozen()["frozen_input_sha256"]
    reply_sources = {
        case_id: {key: value for key, value in row.items() if key != "summary_text"}
        for case_id, row in v2.load_frozen_reply_sources().items()
    }
    source_files = {
        "final_live_runner": "docs/evidence/r2-ar04-live-recheck-v2-final-01/run_live_final.py",
        "final_runner_tests": "docs/evidence/r2-ar04-live-recheck-v2-final-01/test_live_final.py",
        "accepted_v2_runner": "docs/evidence/r2-ar04-live-recheck-v2-prep-01/run_v2.py",
        "accepted_v2_tests": "docs/evidence/r2-ar04-live-recheck-v2-prep-01/test_runner_v2.py",
        "runtime_runner": "docs/evidence/abc-live-env-unblock-01/run_abc_eval.py",
        "recheck_adapter": "docs/evidence/r2-ar04-live-retention-recheck-01/run_recheck.py",
        "source_correction": "docs/evidence/r2-ar04-v2-provenance-hf01/CORRECTION.md",
        "source_manifest": "docs/evidence/r2-ar04-v2-provenance-hf01/FROZEN_REPLY_SOURCES.json",
    }
    supporting = {
        rel: _sha256((ROOT / rel).read_bytes()) for rel in source_files.values()
    }
    result = {
        "schema_version": 1,
        "task": TASK,
        "task_base_sha": TASK_BASE_SHA,
        "candidate_branch": "codex/r2-ar04-live-recheck-v2-final-01",
        "freeze": freeze,
        "frozen_input_sha256": source_hashes,
        "supporting_source_sha256": supporting,
        "supporting_sources": source_files,
        "corrected_first_summary_sources": reply_sources,
        "matrix": [
            {"case": "Q02-A", "strategy": "HYBRID", "question": "Q02", "target_fact": "endpoint=/callback"},
            {"case": "Q02-B", "strategy": "ROLLING_SUMMARY", "question": "Q02", "target_fact": "endpoint=/callback"},
            {"case": "Q06-B", "strategy": "ROLLING_SUMMARY", "question": "Q06", "target_facts": ["v1.2 -> v1.3", "max_attempts 3 -> 5"]},
        ],
        "request_contract": {
            "provider": "DeepSeek", "model_alias": v2.MODEL, "published_model_version": MODEL_VERSION,
            "thinking": v2.THINKING, "temperature": v2.TEMPERATURE, "tool_choice": "none",
            "input_tokens_per_request": v2.MAX_INPUT_TOKENS, "output_tokens_per_request": v2.MAX_OUTPUT_TOKENS,
            "summary_requests": SUMMARY_LIMIT, "answer_requests": ANSWER_LIMIT,
            "total_requests": REQUEST_LIMIT, "automatic_retries": 0, "external_mcp": False,
            "stop_on_first_case_failure": True,
        },
        "budget": {
            "input_peak_cache_miss_usd_per_million": INPUT_RATE_USD_PER_MILLION,
            "output_peak_usd_per_million": OUTPUT_RATE_USD_PER_MILLION,
            "per_request_worst_case_reserve_usd_micro": REQUEST_RESERVE_USD_MICRO,
            "all_requests_worst_case_reserve_usd_micro": TOTAL_WORST_CASE_RESERVE_USD_MICRO,
            "hard_cap_usd_micro": HARD_CAP_USD_MICRO,
        },
        "price_snapshot": _price_snapshot(),
        "gold_and_rubric": "Frozen in the hashed Phase A question/evaluation inputs; never serialized into provider request.",
    }
    _atomic_json(path, result)
    _atomic_json(EVIDENCE_DIR / "PRICE_SNAPSHOT.json", _price_snapshot())
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("mock", "preflight", "prepare", "live"))
    parser.add_argument("--authorization", type=Path)
    parser.add_argument("--mock-results", type=Path, default=MOCK_RESULTS_PATH)
    args = parser.parse_args(argv)
    assert_final_frozen()

    if args.mode in {"mock", "preflight", "prepare"}:
        v2.block_external_network()
    if args.mode == "mock":
        result = run_mock()
    elif args.mode == "preflight":
        result = run_preflight(args.mock_results)
    elif args.mode == "prepare":
        EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
        if MOCK_DIR.exists() or LIVE_RUN_PATH.exists():
            raise FinalRunnerStop("PREPARATION_OUTPUT_EXISTS_REFUSE_OVERWRITE")
        create_frozen_input_manifest(EVIDENCE_DIR / "FROZEN_INPUTS.json")
        result = run_mock(MOCK_DIR)
        mock, passed = _mock_passed(MOCK_RESULTS_PATH)
        if not passed:
            raise FinalRunnerStop("FRESH_FULL_MOCK_DID_NOT_PASS")
        result = run_preflight(MOCK_RESULTS_PATH)
        # A zero-cost live Runner preparation is not a provider evaluation.
        result["candidate_status"] = result["status"]
        result["status"] = "READY_FOR_LIVE_AUTHORIZATION" if result["technical_preflight_passed"] else "BLOCKED_BEFORE_PROVIDER_SEND"
        _atomic_json(PREFLIGHT_PATH, result)
        _atomic_json(EVIDENCE_DIR / "MOCK_RESULTS.json", mock)
        result = {
            "status": result["status"],
            "provider_requests_sent": 0,
            "provider_cost_usd": "0.00",
            "mock_cases_passed": 3 if mock.get("case_matrix_passed") else 0,
            "mock_requests": mock.get("recorded_requests", 0),
        }
    else:
        if args.authorization is None:
            raise FinalRunnerStop("NEW_TASK_SPECIFIC_LIVE_AUTHORIZATION_REQUIRED")
        result = run_live(args.authorization, mock_path=args.mock_results)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    status = result.get("status")
    if args.mode == "prepare":
        return 0 if status == "READY_FOR_LIVE_AUTHORIZATION" else 1
    if args.mode == "live":
        return 0 if status == "COMPLETED" else 1
    return 0 if status in {"COMPLETED", "READY_FOR_LIVE_AUTHORIZATION"} else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except FinalRunnerStop as error:
        print(json.dumps({"status": "BLOCKED_BEFORE_PROVIDER_SEND", "reason": str(error), "provider_requests_sent": 0}))
        sys.exit(2)
