"""One-shot authorized material-run entry point.

The frozen campaign Runner is reused, but execution requires this experiment's
exact authorization record and an atomically consumed private one-shot claim.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import secrets
import sys
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[5]
EVIDENCE_ROOT = ROOT / "docs" / "evidence" / "ar-03" / "material-live-01" / "resume-01"
EVIDENCE = EVIDENCE_ROOT / "runs" / "AR-03-MATERIAL-LIVE-01-RESUME-01"
RUNTIME = ROOT / ".runtime" / "ar03-material-live-01-resume-01"
DOMAIN_DB = RUNTIME / "domain.sqlite3"
CHECKPOINT_DB = RUNTIME / "checkpoints.sqlite3"
BASE_RUNNER_PATH = ROOT / "docs" / "evidence" / "ar-03" / "material-live-01" / "run_live.py"
HISTORICAL_CLAIM = ROOT / "docs" / "evidence" / "ar-03" / "material-live-01" / "EXECUTION_CLAIM.json"
HISTORICAL_CLAIM_SHA256 = "db65416c9e361a064fe2bf29b0864793343e81d0d38edb637b89b4b8069d1e3a"
CASES_BLOB = "faf16fbb857278e98f8afbe179fe327855132967"
EXPERIMENT_ID = "AR-03-MATERIAL-LIVE-01-RESUME-01"
BRANCH = "codex/ar03-material-live-01-exec-prep"
EXECUTION_BASE_SHA = "905e71e683d63299594211a07b86dcdf14e21602"
BASE_SHA = "ff956ea71b90448d40229c57b8f8619c997b5cbd"
FREEZE_SHA = "434a8b027f0072036b46bc624d1defab8703b775"
AUTHORIZATION_ID = "AR03-MATERIAL-LIVE-01-RESUME-01-USER-AUTH-2026-11-03"
TOKEN_ENV = "OPSPILOT_AR03_MATERIAL_RESUME_ONE_SHOT_TOKEN"
PREPARED_CLAIM = EVIDENCE_ROOT / "PREPARED_CLAIM.json"
PAID_AUTHORIZATION = EVIDENCE_ROOT / "PAID_AUTHORIZATION.json"
AUTHORIZATION_CLAIM_DIR = ROOT.parent.parent / ".runtime" / "ar03-material-live-01-resume-01-authorization"
AUTHORIZATION_CLAIM = AUTHORIZATION_CLAIM_DIR / "claim.json"

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


def _expected_paid_authorization() -> dict[str, Any]:
    return {
        "authorization_id": AUTHORIZATION_ID,
        "experiment_id": EXPERIMENT_ID,
        "status": "AUTHORIZED_ONE_SHOT",
        "authorized_on": "2026-11-03",
        "authorization_source": "Explicit user authorization in AR-03-MATERIAL-LIVE-01-RESUME-01 task card",
        "branch": BRANCH,
        "execution_base_sha": EXECUTION_BASE_SHA,
        "accepted_safe_base_sha": BASE_SHA,
        "freeze_commit": FREEZE_SHA,
        "frozen_cases_blob": CASES_BLOB,
        "provider": "DeepSeek",
        "model": "deepseek-flash",
        "thinking": "disabled",
        "max_tokens": 2048,
        "context_input_limit_tokens": 12000,
        "provider_limit": 16,
        "mcp_limit": 10,
        "application_budget_usd_micro": 10_500_000,
        "provider_reservation_usd_micro": 645_600,
        "request_timeout_seconds": 30,
        "provider_concurrency": 1,
        "automatic_retries": 0,
        "manual_retries": 0,
        "business_writes_allowed": False,
        "historical_claims_reusable": False,
    }


def _validate_paid_authorization() -> tuple[dict[str, Any], str]:
    if not PAID_AUTHORIZATION.is_file():
        raise RuntimeError("PAID_AUTHORIZATION_RECORD_MISSING")
    try:
        raw = PAID_AUTHORIZATION.read_bytes()
        authorization = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RuntimeError("PAID_AUTHORIZATION_RECORD_INVALID") from error
    if type(authorization) is not dict or authorization != _expected_paid_authorization():
        raise RuntimeError("PAID_AUTHORIZATION_SCOPE_MISMATCH")
    return authorization, hashlib.sha256(raw).hexdigest()


def _validate_preflight() -> dict[str, Any]:
    _validate_prepared_claim()
    _, authorization_digest = _validate_paid_authorization()
    if os.environ.get(TOKEN_ENV):
        raise RuntimeError("ONE_SHOT_TOKEN_MUST_NOT_BE_PRESET")
    if AUTHORIZATION_CLAIM_DIR.exists() or AUTHORIZATION_CLAIM.exists():
        raise RuntimeError("ONE_SHOT_AUTHORIZATION_ALREADY_CONSUMED")
    if EVIDENCE.exists():
        raise RuntimeError("RUN_EVIDENCE_PATH_ALREADY_EXISTS")
    baseline_check = subprocess.run(
        ["git", "merge-base", "--is-ancestor", EXECUTION_BASE_SHA, "HEAD"],
        cwd=ROOT, capture_output=True, check=False,
    )
    if baseline_check.returncode != 0:
        raise RuntimeError("EXECUTION_BASELINE_NOT_IN_HISTORY")
    base = _bound_base_runner()._validate_preflight()
    return {
        "status": "PREFLIGHT_READY_AUTHORIZED_ONE_SHOT",
        "experiment_id": EXPERIMENT_ID,
        "authorization_id": AUTHORIZATION_ID,
        "authorization_record_sha256": authorization_digest,
        "claim_id": f"{EXPERIMENT_ID}:one-shot:{AUTHORIZATION_ID}",
        "claim_state": "AUTHORIZED_NOT_YET_CONSUMED",
        "paid_dispatch_authorized": True,
        "one_shot_consumed": False,
        "branch": base["branch"],
        "head": base["head"],
        "execution_base_sha": EXECUTION_BASE_SHA,
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
            "raw_evidence_directory": str(EVIDENCE.relative_to(ROOT).as_posix()),
            "authorization_claim_private_path": str(AUTHORIZATION_CLAIM.relative_to(ROOT.parent.parent).as_posix()),
        },
        "historical_claim_sha256_verified": HISTORICAL_CLAIM_SHA256,
        "provider_requests_before_execution": 0,
        "mcp_calls_before_execution": 0,
        "business_write_tools_exposed": base["business_write_tools_exposed"],
        "remote_refs": base["remote_refs"],
    }


def _claim_one_shot(authorization_digest: str) -> str:
    """Atomically consume the sole paid execution identity before any network send."""
    AUTHORIZATION_CLAIM_DIR.parent.mkdir(parents=True, exist_ok=True)
    try:
        AUTHORIZATION_CLAIM_DIR.mkdir(exist_ok=False)
    except FileExistsError as error:
        raise RuntimeError("ONE_SHOT_AUTHORIZATION_ALREADY_CONSUMED") from error
    token = secrets.token_urlsafe(32)
    payload = {
        "claim_id": f"{EXPERIMENT_ID}:one-shot:{AUTHORIZATION_ID}",
        "authorization_id": AUTHORIZATION_ID,
        "experiment_id": EXPERIMENT_ID,
        "branch": BRANCH,
        "execution_base_sha": EXECUTION_BASE_SHA,
        "accepted_base_sha": BASE_SHA,
        "status": "CLAIMED_ONE_SHOT_NO_RETRY",
        "claimed_at": datetime.now(timezone.utc).isoformat(),
        "provider_limit": 16,
        "mcp_limit": 10,
        "application_budget_usd_micro": 10_500_000,
        "provider_reservation_usd_micro": 645_600,
        "request_timeout_seconds": 30,
        "automatic_retries": 0,
        "manual_retries": 0,
        "authorization_record_sha256": authorization_digest,
        "token_sha256": hashlib.sha256(token.encode("utf-8")).hexdigest(),
    }
    fd = os.open(str(AUTHORIZATION_CLAIM), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        try:
            os.close(fd)
        except OSError:
            pass
        raise
    return token


def _execute_once() -> int:
    preflight = _validate_preflight()
    token = _claim_one_shot(str(preflight["authorization_record_sha256"]))
    os.environ[TOKEN_ENV] = token
    try:
        EVIDENCE.mkdir(parents=True, exist_ok=False)
        return _bound_base_runner()._execute_once()
    finally:
        for name in (
            TOKEN_ENV,
            "OPSPILOT_ASSISTANT_PROVIDER_ENABLED",
            "OPSPILOT_ASSISTANT_EXPERIMENT_ID",
            "OPSPILOT_AR03_MATERIAL_SKILL_MODE",
        ):
            os.environ.pop(name, None)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--preflight-only", action="store_true")
    group.add_argument("--execute-once", action="store_true")
    args = parser.parse_args(argv)
    sys.path.insert(0, str(ROOT))
    try:
        if args.execute_once:
            return _execute_once()
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
