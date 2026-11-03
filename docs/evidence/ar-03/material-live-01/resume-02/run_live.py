"""RESUME-02 one-shot wrapper around the accepted frozen campaign runner."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import secrets
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[5]
EVIDENCE_ROOT = ROOT / "docs" / "evidence" / "ar-03" / "material-live-01" / "resume-02"
EVIDENCE = EVIDENCE_ROOT / "runs" / "AR-03-MATERIAL-LIVE-01-RESUME-02"
RUNTIME = ROOT / ".runtime" / "ar03-material-live-01-resume-02"
DOMAIN_DB = RUNTIME / "domain.sqlite3"
CHECKPOINT_DB = RUNTIME / "checkpoints.sqlite3"
BASE_RUNNER_PATH = ROOT / "docs" / "evidence" / "ar-03" / "material-live-01" / "run_live.py"
HISTORICAL_CLAIM = ROOT / "docs" / "evidence" / "ar-03" / "material-live-01" / "EXECUTION_CLAIM.json"
HISTORICAL_CLAIM_SHA256 = "db65416c9e361a064fe2bf29b0864793343e81d0d38edb637b89b4b8069d1e3a"
RESUME01_CLAIM = ROOT.parent.parent / ".runtime" / "ar03-material-live-01-resume-01-authorization" / "claim.json"
RESUME01_CLAIM_SHA256 = "f8f4b2618fa263c10e8ea85def4140218d62ccd571ad3a9e06b2bd1ebcd11458"
CASES_BLOB = "faf16fbb857278e98f8afbe179fe327855132967"
EXPERIMENT_ID = "AR-03-MATERIAL-LIVE-01-RESUME-02"
BRANCH = "codex/ar03-material-live-01-resume-02"
BASE_SHA = "d4addd403ba0722d4acb4c1a33d1cd655599c97c"
FREEZE_SHA = "434a8b027f0072036b46bc624d1defab8703b775"
AUTHORIZATION_ID = "AR03-MATERIAL-LIVE-01-RESUME-02-USER-AUTH-2026-11-04"
TOKEN_ENV = "OPSPILOT_AR03_MATERIAL_RESUME_02_ONE_SHOT_TOKEN"
PREPARED_CLAIM = EVIDENCE_ROOT / "PREPARED_CLAIM.json"
PAID_AUTHORIZATION = EVIDENCE_ROOT / "PAID_AUTHORIZATION.json"
AUTHORIZATION_CLAIM_DIR = ROOT.parent.parent / ".runtime" / "ar03-material-live-01-resume-02-authorization"
AUTHORIZATION_CLAIM = AUTHORIZATION_CLAIM_DIR / "claim.json"

_BASE_RUNNER = None


def _git(*args: str) -> str:
    result = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=False)
    if result.returncode:
        raise RuntimeError("GIT_PREFLIGHT_FAILED:" + " ".join(args))
    return result.stdout.strip()


def _bound_base_runner():
    global _BASE_RUNNER
    if _BASE_RUNNER is None:
        spec = importlib.util.spec_from_file_location("ar03_material_live_resume02_base_runner", BASE_RUNNER_PATH)
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


def _expected_prepared_claim() -> dict[str, Any]:
    return {
        "accepted_base_sha": BASE_SHA,
        "application_budget_usd_micro": 10_500_000,
        "authorization_id": AUTHORIZATION_ID,
        "branch": BRANCH,
        "claim_id": f"{EXPERIMENT_ID}:paid-one-shot",
        "experiment_id": EXPERIMENT_ID,
        "historical_resume01_claim_sha256": RESUME01_CLAIM_SHA256,
        "historical_root_claim_sha256": HISTORICAL_CLAIM_SHA256,
        "mcp_limit": 10,
        "one_shot_consumed": False,
        "paid_dispatch_authorized": True,
        "provider_limit": 16,
        "provider_reservation_usd_micro": 645_600,
        "status": "AUTHORIZED_NOT_YET_CONSUMED",
    }


def _validate_authorization() -> tuple[dict[str, Any], str]:
    try:
        raw = PAID_AUTHORIZATION.read_bytes()
        authorization = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RuntimeError("PAID_AUTHORIZATION_RECORD_INVALID") from error
    from opspilot.assistant import _resume02_expected_authorization
    if type(authorization) is not dict or authorization != _resume02_expected_authorization():
        raise RuntimeError("PAID_AUTHORIZATION_SCOPE_MISMATCH")
    return authorization, hashlib.sha256(raw).hexdigest()


def _validate_historical_claims() -> dict[str, str]:
    if not HISTORICAL_CLAIM.is_file() or hashlib.sha256(HISTORICAL_CLAIM.read_bytes()).hexdigest() != HISTORICAL_CLAIM_SHA256:
        raise RuntimeError("HISTORICAL_ROOT_CLAIM_CHANGED_OR_MISSING")
    if not RESUME01_CLAIM.is_file() or hashlib.sha256(RESUME01_CLAIM.read_bytes()).hexdigest() != RESUME01_CLAIM_SHA256:
        raise RuntimeError("RESUME01_CLAIM_CHANGED_OR_MISSING")
    return {
        "historical_root_claim_sha256": HISTORICAL_CLAIM_SHA256,
        "historical_resume01_claim_sha256": RESUME01_CLAIM_SHA256,
        "historical_claims_reused": "false",
    }


def _validate_prepared_claim() -> dict[str, Any]:
    try:
        claim = json.loads(PREPARED_CLAIM.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RuntimeError("PREPARED_CLAIM_INVALID") from error
    if claim != _expected_prepared_claim():
        raise RuntimeError("PREPARED_CLAIM_IDENTITY_OR_AUTHORIZATION_MISMATCH")
    return claim


def _validate_preflight() -> dict[str, Any]:
    _validate_prepared_claim()
    _, authorization_digest = _validate_authorization()
    historical = _validate_historical_claims()
    if os.environ.get(TOKEN_ENV):
        raise RuntimeError("ONE_SHOT_TOKEN_MUST_NOT_BE_PRESET")
    if AUTHORIZATION_CLAIM_DIR.exists() or AUTHORIZATION_CLAIM.exists():
        raise RuntimeError("ONE_SHOT_AUTHORIZATION_ALREADY_CONSUMED")
    if EVIDENCE.exists():
        raise RuntimeError("RUN_EVIDENCE_PATH_ALREADY_EXISTS")
    if _git("branch", "--show-current") != BRANCH:
        raise RuntimeError("MATERIAL_LIVE_BRANCH_MISMATCH")
    head = _git("rev-parse", "HEAD")
    for required_sha, code in ((BASE_SHA, "AUTHORIZED_BASELINE_NOT_IN_HISTORY"), (FREEZE_SHA, "FREEZE_COMMIT_NOT_IN_HISTORY")):
        result = subprocess.run(["git", "merge-base", "--is-ancestor", required_sha, "HEAD"], cwd=ROOT, capture_output=True, check=False)
        if result.returncode:
            raise RuntimeError(code)
    if _git("rev-parse", "HEAD:docs/evidence/ar-03/material-01/CASES.json") != CASES_BLOB:
        raise RuntimeError("FROZEN_CASES_BLOB_MISMATCH")
    base = _bound_base_runner()._validate_preflight()
    return {
        **base,
        "status": "PREFLIGHT_READY_AUTHORIZED_ONE_SHOT",
        "experiment_id": EXPERIMENT_ID,
        "authorization_id": AUTHORIZATION_ID,
        "authorization_record_sha256": authorization_digest,
        "claim_id": f"{EXPERIMENT_ID}:one-shot:{AUTHORIZATION_ID}",
        "claim_state": "AUTHORIZED_NOT_YET_CONSUMED",
        "one_shot_consumed": False,
        "head": head,
        "historical_claims": historical,
        "isolated_runtime": {
            "domain_db": str(DOMAIN_DB.relative_to(ROOT)),
            "checkpoint_db": str(CHECKPOINT_DB.relative_to(ROOT)),
            "raw_evidence": str(EVIDENCE.relative_to(ROOT)),
        },
        "provider_requests_before_execution": 0,
        "external_business_writes_before_execution": 0,
    }


def _claim_one_shot(authorization_digest: str) -> str:
    AUTHORIZATION_CLAIM_DIR.parent.mkdir(parents=True, exist_ok=True)
    try:
        AUTHORIZATION_CLAIM_DIR.mkdir(exist_ok=False)
    except FileExistsError as error:
        raise RuntimeError("ONE_SHOT_AUTHORIZATION_ALREADY_CONSUMED") from error
    token = secrets.token_urlsafe(32)
    from opspilot.assistant import _resume02_expected_claim
    payload = {
        **_resume02_expected_claim(authorization_digest),
        "claimed_at": datetime.now(timezone.utc).isoformat(),
        "token_sha256": hashlib.sha256(token.encode("utf-8")).hexdigest(),
    }
    fd = os.open(str(AUTHORIZATION_CLAIM), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")
        stream.flush()
        os.fsync(stream.fileno())
    return token


def _execute_once() -> int:
    preflight = _validate_preflight()
    token = _claim_one_shot(str(preflight["authorization_record_sha256"]))
    os.environ[TOKEN_ENV] = token
    try:
        EVIDENCE.mkdir(parents=True, exist_ok=False)
        _bound_base_runner()._write_json(EVIDENCE / "PREFLIGHT.json", preflight)
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
        result = _validate_preflight()
        if args.preflight_only:
            print(json.dumps(result, ensure_ascii=False, sort_keys=True))
            return 0
        return _execute_once()
    except BaseException as error:
        print(json.dumps({
            "status": "BLOCKED_BEFORE_PROVIDER_SEND",
            "error_type": type(error).__name__,
            "reason": str(error)[:300],
            "claim_consumed": AUTHORIZATION_CLAIM.exists(),
            "provider_requests": 0,
        }, ensure_ascii=False, sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
