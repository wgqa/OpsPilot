"""Version-bound AR-04 admission runner for Q02-B and Q06-B.

The implementation delegates to the already reviewed remaining-live gate and
V2 Assistant/Domain harness. This adapter changes only task and artifact pins;
it does not add a second runtime or authorization mechanism.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
EVIDENCE_DIR = Path(__file__).resolve().parent
BASE_SHA = "92c8823c9853a23f2cdb2fee7f0fec985d230399"
TASK = "R2-AR04-LIVE-RETEST-GATE-01"
REVIEW_TASK_ID = "R2-AR04-LIVE-RETEST-VERSION-ADMISSION-01"
CHAT_BLOB = "6a57360de6f5579fa65dc008de4fcf37148c43f0"
ASSISTANT_BLOB = "288559c6e9b77549939501f4cedb1a8097a79918"
MOCK_DIR = EVIDENCE_DIR / "mock_run_02"
MOCK_RESULTS_PATH = MOCK_DIR / "MOCK_RESULTS.json"
PREFLIGHT_PATH = EVIDENCE_DIR / "PREFLIGHT_RUN_02.json"
LIVE_RUN_PATH = EVIDENCE_DIR / "live_run_01"
SOURCE_MANIFEST_PATH = EVIDENCE_DIR / "SOURCE_MANIFEST.json"
REUSED_RUNNER_PATH = ROOT / "docs/evidence/r2-ar04-remaining-live-gate-01/run_remaining_live_gate.py"

_GATE: ModuleType | None = None


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_gate() -> ModuleType:
    """Load the accepted gate and pin it to this task without editing it."""
    global _GATE
    if _GATE is not None:
        return _GATE
    spec = importlib.util.spec_from_file_location(
        "ar04_live_retest_version_admission_gate", REUSED_RUNNER_PATH,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("REUSED_LIVE_GATE_LOAD_FAILED")
    gate = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = gate
    spec.loader.exec_module(gate)

    # The reused module's functions resolve these globals at call time. The
    # runner digest therefore binds to this new adapter, while old files and
    # old default paths remain untouched.
    gate.__file__ = str(Path(__file__).resolve())
    gate.ROOT = ROOT
    gate.EVIDENCE_DIR = EVIDENCE_DIR
    gate.TASK = TASK
    gate.BASE_SHA = BASE_SHA
    gate.REVIEW_TASK_ID = REVIEW_TASK_ID
    gate.REVIEW_BASE_SHA = BASE_SHA
    gate.CHAT_BLOB = CHAT_BLOB
    gate.ASSISTANT_BLOB = ASSISTANT_BLOB
    gate.MOCK_DIR = MOCK_DIR
    gate.MOCK_RESULTS_PATH = MOCK_RESULTS_PATH
    gate.PREFLIGHT_PATH = PREFLIGHT_PATH
    gate.LIVE_RUN_PATH = LIVE_RUN_PATH
    gate._ACTIVE_AUTHORIZATION_PATH = None
    _GATE = gate
    return gate


def assert_frozen() -> dict[str, Any]:
    return load_gate()._task_assert_frozen()


def prepare() -> dict[str, Any]:
    """Create one fresh frozen source manifest, full Mock, and zero-cost preflight."""
    gate = load_gate()
    if any(path.exists() for path in (MOCK_DIR, PREFLIGHT_PATH, SOURCE_MANIFEST_PATH)):
        raise gate.GateStop("PREPARATION_OUTPUT_EXISTS_REFUSE_OVERWRITE")
    # The source manifest is derived from the already pinned historical traces.
    # No historical response is rewritten or assigned a different identity.
    freeze = assert_frozen()
    gate._write_json(SOURCE_MANIFEST_PATH, gate._expected_source_manifest(freeze))
    mock = gate.run_mock(MOCK_DIR)
    if not mock.get("case_matrix_passed"):
        gate._write_json(EVIDENCE_DIR / "MOCK_FAILURE.json", mock)
        raise gate.GateStop("TWO_CASE_FULL_MOCK_DID_NOT_PASS")
    preflight = gate.run_preflight(MOCK_RESULTS_PATH, PREFLIGHT_PATH)
    gate._write_json(EVIDENCE_DIR / "FREEZE.json", freeze)
    gate._write_json(EVIDENCE_DIR / "BUDGET.json", preflight.get("budget", {}))
    return {
        "status": preflight.get("status"),
        "mock_case_matrix_passed": mock.get("case_matrix_passed"),
        "recorded_mock_requests": mock.get("recorded_requests"),
        "provider_requests_sent": 0,
        "provider_cost_usd": "0.00",
        "valid_authorization_created": False,
        "live_dispatch_performed": False,
    }


def run_preflight(mock_path: Path | None = None, output_path: Path = PREFLIGHT_PATH) -> dict[str, Any]:
    gate = load_gate()
    selected = MOCK_RESULTS_PATH if mock_path is None else Path(mock_path)
    return gate.run_preflight(selected, output_path)


def run_live(authorization_path: Path, *, mock_path: Path | None = None,
             output_path: Path = LIVE_RUN_PATH) -> dict[str, Any]:
    """Retain the existing strict future live path; this task never invokes it."""
    gate = load_gate()
    selected = MOCK_RESULTS_PATH if mock_path is None else Path(mock_path)
    return gate.run_live(authorization_path, mock_path=selected, output_path=output_path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("freeze", "mock", "preflight", "prepare", "live"))
    parser.add_argument("--output", type=Path)
    parser.add_argument("--mock-results", type=Path)
    parser.add_argument("--authorization", type=Path)
    args = parser.parse_args(argv)
    gate = load_gate()

    # All non-live commands are offline-only, even if an underlying adapter is
    # accidentally changed to use a network transport.
    if args.mode != "live":
        gate.v2.block_external_network()

    if args.mode == "freeze":
        freeze = assert_frozen()
        manifest = gate._expected_source_manifest(freeze)
        if SOURCE_MANIFEST_PATH.exists():
            current = json.loads(SOURCE_MANIFEST_PATH.read_text(encoding="utf-8"))
            if current != manifest:
                raise gate.GateStop("FROZEN_SOURCE_MANIFEST_DRIFT")
        else:
            gate._write_json(SOURCE_MANIFEST_PATH, manifest)
        result: dict[str, Any] = {"status": "FROZEN", "freeze": freeze,
                                  "source_manifest_sha256": _sha256(SOURCE_MANIFEST_PATH)}
    elif args.mode == "mock":
        output = args.output or MOCK_DIR
        result = gate.run_mock(output)
    elif args.mode == "preflight":
        mock_path = MOCK_RESULTS_PATH if args.mock_results is None else args.mock_results
        result = run_preflight(mock_path, args.output or PREFLIGHT_PATH)
    elif args.mode == "prepare":
        result = prepare()
    else:
        if args.authorization is None:
            raise gate.GateStop("NEW_TASK_SPECIFIC_LIVE_AUTHORIZATION_REQUIRED")
        mock_path = MOCK_RESULTS_PATH if args.mock_results is None else args.mock_results
        result = run_live(args.authorization, mock_path=mock_path,
                          output_path=args.output or LIVE_RUN_PATH)

    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    if args.mode in {"prepare", "preflight"}:
        return 0 if result.get("status") == "READY_FOR_NEW_LIVE_AUTHORIZATION" else 1
    if args.mode == "mock":
        return 0 if result.get("case_matrix_passed") else 1
    return 0


if __name__ == "__main__":
    gate = load_gate()
    try:
        sys.exit(main())
    except gate.GateStop as error:
        print(json.dumps({"status": "BLOCKED", "reason": str(error)}))
        sys.exit(2)
