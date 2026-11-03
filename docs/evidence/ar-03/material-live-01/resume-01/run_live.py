"""Isolated preparation entry point for a separately authorized material run.

This entry point reuses the frozen campaign Runner's offline preflight binding.
It cannot execute a paid campaign; a later, distinct authorization must enable
and consume a fresh one-shot claim before any Provider send is possible.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[5]
EVIDENCE = ROOT / "docs" / "evidence" / "ar-03" / "material-live-01" / "resume-01"
RUNTIME = ROOT / ".runtime" / "ar03-material-live-01-resume-01"
DOMAIN_DB = RUNTIME / "domain.sqlite3"
CHECKPOINT_DB = RUNTIME / "checkpoints.sqlite3"
BASE_RUNNER_PATH = ROOT / "docs" / "evidence" / "ar-03" / "material-live-01" / "run_live.py"
HISTORICAL_CLAIM = ROOT / "docs" / "evidence" / "ar-03" / "material-live-01" / "EXECUTION_CLAIM.json"
HISTORICAL_CLAIM_SHA256 = "db65416c9e361a064fe2bf29b0864793343e81d0d38edb637b89b4b8069d1e3a"
CASES_BLOB = "faf16fbb857278e98f8afbe179fe327855132967"
EXPERIMENT_ID = "AR-03-MATERIAL-LIVE-01-RESUME-01"
BRANCH = "codex/ar03-material-live-01-exec-prep"
BASE_SHA = "ff956ea71b90448d40229c57b8f8619c997b5cbd"
FREEZE_SHA = "434a8b027f0072036b46bc624d1defab8703b775"
PREPARED_CLAIM = EVIDENCE / "PREPARED_CLAIM.json"

_BASE_RUNNER = None


def _bound_base_runner():
    """Load the accepted runner and bind it to this frozen execution identity."""
    global _BASE_RUNNER
    if _BASE_RUNNER is None:
        spec = importlib.util.spec_from_file_location("ar03_material_live_base_runner", BASE_RUNNER_PATH)
        if spec is None or spec.loader is None:
            raise RuntimeError("ACCEPTED_BASE_RUNNER_NOT_LOADABLE")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        module.ROOT = ROOT
        module.EVIDENCE = EVIDENCE
        module.CASES_PATH = ROOT / "docs" / "evidence" / "ar-03" / "material-01" / "CASES.json"
        module.RUNTIME = RUNTIME
        module.DOMAIN_DB = DOMAIN_DB
        module.CHECKPOINT_DB = CHECKPOINT_DB
        module.BRANCH = BRANCH
        module.BASE_SHA = BASE_SHA
        module.FREEZE_SHA = FREEZE_SHA
        module.CASES_BLOB = CASES_BLOB
        module.EXPERIMENT_ID = EXPERIMENT_ID
        _BASE_RUNNER = module
    return _BASE_RUNNER


def _validate_prepared_claim() -> dict[str, Any]:
    if not PREPARED_CLAIM.is_file():
        raise RuntimeError("PREPARED_CLAIM_MISSING")
    try:
        claim = json.loads(PREPARED_CLAIM.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RuntimeError("PREPARED_CLAIM_INVALID") from error
    expected = {
        "claim_id": f"{EXPERIMENT_ID}:paid-one-shot",
        "experiment_id": EXPERIMENT_ID,
        "branch": BRANCH,
        "accepted_base_sha": BASE_SHA,
        "status": "WAITING_FOR_EXPLICIT_PAID_AUTHORIZATION",
        "paid_dispatch_authorized": False,
        "one_shot_consumed": False,
        "provider_limit": 16,
        "mcp_limit": 10,
        "application_budget_usd_micro": 10_500_000,
        "provider_reservation_usd_micro": 645_600,
        "historical_claim_sha256": HISTORICAL_CLAIM_SHA256,
    }
    if claim != expected:
        raise RuntimeError("PREPARED_CLAIM_IDENTITY_OR_AUTHORIZATION_MISMATCH")
    if not HISTORICAL_CLAIM.is_file():
        raise RuntimeError("HISTORICAL_CLAIM_MISSING")
    digest = hashlib.sha256(HISTORICAL_CLAIM.read_bytes()).hexdigest()
    if digest != HISTORICAL_CLAIM_SHA256:
        raise RuntimeError("HISTORICAL_CLAIM_CHANGED")
    return claim


def _validate_preflight() -> dict[str, Any]:
    _validate_prepared_claim()
    base = _bound_base_runner()._validate_preflight()
    return {
        "status": "PREFLIGHT_READY_AWAITING_PAID_AUTHORIZATION",
        "experiment_id": EXPERIMENT_ID,
        "claim_id": f"{EXPERIMENT_ID}:paid-one-shot",
        "claim_state": "WAITING_FOR_EXPLICIT_PAID_AUTHORIZATION",
        "paid_dispatch_authorized": False,
        "one_shot_consumed": False,
        "branch": base["branch"],
        "head": base["head"],
        "accepted_base_sha": BASE_SHA,
        "freeze_commit": FREEZE_SHA,
        "frozen_cases_blob": CASES_BLOB,
        "model": base["model"],
        "credential_configured": bool(base["credential_present"]),
        "provider_opt_in_before_runner": base["provider_opt_in_before_runner"],
        "request_parameters": base["request_parameters"],
        "context_input_limit_tokens": base["context_input_limit_tokens"],
        "budget": base["budget"],
        "case_count": base["case_count"],
        "cases": base["cases"],
        "independent_runtime_paths": {
            "domain_db": str(DOMAIN_DB.name),
            "checkpoint_db": str(CHECKPOINT_DB.name),
            "runtime_exists": RUNTIME.exists(),
        },
        "historical_claim_sha256_verified": HISTORICAL_CLAIM_SHA256,
        "provider_requests_before_execution": 0,
        "mcp_calls_before_execution": 0,
        "business_write_tools_exposed": base["business_write_tools_exposed"],
        "remote_refs": base["remote_refs"],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--preflight-only", action="store_true")
    group.add_argument("--execute-once", action="store_true")
    args = parser.parse_args(argv)
    if args.execute_once:
        print(json.dumps({
            "status": "BLOCKED_BEFORE_PROVIDER_SEND",
            "reason": "PAID_EXECUTION_REQUIRES_SEPARATE_EXPLICIT_AUTHORIZATION",
            "provider_requests": 0,
        }, sort_keys=True))
        return 2
    sys.path.insert(0, str(ROOT))
    try:
        result = _validate_preflight()
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0
    except BaseException as error:
        print(json.dumps({
            "status": "BLOCKED_BEFORE_PROVIDER_SEND",
            "error_type": type(error).__name__,
            "reason": str(error)[:300],
            "provider_requests": 0,
        }, ensure_ascii=False, sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
