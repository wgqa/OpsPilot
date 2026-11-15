"""Prepare or run one frozen R2 evaluation case in an isolated User Demo runtime.

The CLI is deliberately inert by default. Fixture execution is exercised by the
tests through the same Web API helper. Live execution requires an exact case
acknowledgement, an explicit application-budget ceiling, a fresh runtime, a
matching managed Live process, and a valid pre-existing Runtime Grant.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import sys
import time
import uuid
from decimal import Decimal, InvalidOperation
from pathlib import Path
from urllib.parse import urlparse
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
USER_DEMO_DIR = ROOT / "scripts" / "user-demo"
EVAL_DIR = ROOT / "docs" / "evidence" / "r2-ar06-eval-01"
CASES_PATH = EVAL_DIR / "CASES.json"
FROZEN_HASHES_PATH = EVAL_DIR / "FROZEN_HASHES.json"
E04_FIXTURE_MANIFEST_PATH = EVAL_DIR / "e04-h-absence-20261115" / "E04_FIXTURE_MANIFEST.json"
OBSERVATION_CONTRAST_CASE_ID = "OBSERVATION-CONTRAST-PROCESSED"
OBSERVATION_CONTRAST_TARGET_EVENT_ID = "event-00000000-0000-4000-8000-000000000101"
OBSERVATION_CONTRAST_DECOY_EVENT_ID = "event-00000000-0000-4000-8000-000000000102"
SUPPORTED_CASES = {
    "E02-H", "E03-D", "E04-H", "E05-D", "E06-H", "E07-D", OBSERVATION_CONTRAST_CASE_ID,
}
EXPLORATORY_CASE_SOURCES = {OBSERVATION_CONTRAST_CASE_ID: "E07-D"}
CASE_S3_PROFILES = {
    "E02-H": "standard",
    "E05-D": "standard",
    "E06-H": "standard",
    "E07-D": "r2-e07-queued",
    OBSERVATION_CONTRAST_CASE_ID: "r2-e08-processed-decoy",
}
E07_ORDER_ID = "async-order"
E07_EVENT_ID = "event-00000000-0000-4000-8000-000000000001"
S3_FIXTURE_EXPECTATIONS = {
    "E07-D": {
        "target_order_id": E07_ORDER_ID,
        "target_event_id": E07_EVENT_ID,
        "target_receiver_status": "QUEUED",
    },
    OBSERVATION_CONTRAST_CASE_ID: {
        "target_order_id": E07_ORDER_ID,
        "target_event_id": OBSERVATION_CONTRAST_TARGET_EVENT_ID,
        "target_receiver_status": "PROCESSED",
        "decoy_order_id": "async-order-decoy",
        "decoy_event_id": OBSERVATION_CONTRAST_DECOY_EVENT_ID,
        "decoy_receiver_status": "QUEUED",
    },
}
DEFAULT_API_ORIGIN = "http://127.0.0.1:8000"
DEFAULT_WEB_ORIGIN = "http://127.0.0.1:5173"
DEFAULT_RUN_TIMEOUT_SECONDS = 600
DEFAULT_MAX_RUN_MODEL_DISPATCHES = 8

for path in (ROOT, USER_DEMO_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))


class EvaluationPreflightError(RuntimeError):
    """A safe, non-secret reason a case cannot be prepared or run."""


def load_frozen_case(case_id: str) -> dict[str, Any]:
    """Return only an explicitly prepared, single-turn development case.

    The case text is read verbatim from the frozen Gold. Expected answers,
    forbidden conditions and rubric labels are never returned to the caller.
    """
    if case_id not in SUPPORTED_CASES:
        raise ValueError("LIVE_CASE_NOT_PREPARED:" + str(case_id))
    cases_bytes = CASES_PATH.read_bytes()
    freeze = json.loads(FROZEN_HASHES_PATH.read_text(encoding="utf-8"))
    expected_hash = freeze["files"]["CASES.json"]["sha256"]
    actual_hash = hashlib.sha256(cases_bytes).hexdigest()
    if actual_hash != expected_hash:
        raise EvaluationPreflightError("FROZEN_CASES_DIGEST_MISMATCH")
    document = json.loads(cases_bytes.decode("utf-8"))
    source_case_id = EXPLORATORY_CASE_SOURCES.get(case_id, case_id)
    matches = [item for item in document["cases"] if item.get("case_id") == source_case_id]
    if len(matches) != 1:
        raise EvaluationPreflightError("FROZEN_CASE_ID_NOT_UNIQUE")
    case = matches[0]
    turns = case.get("user_turns")
    split = case.get("split")
    if split not in {"D", "H"} or not isinstance(turns, list) or len(turns) != 1:
        raise EvaluationPreflightError("CASE_REQUIRES_ONE_FROZEN_TURN")
    if not isinstance(turns[0], str) or not turns[0].strip():
        raise EvaluationPreflightError("FROZEN_CASE_INPUT_INVALID")
    # Keep the fields the executor needs; Gold outcomes never enter Context.
    result = {
        "case_id": case_id,
        "split": split,
        "user_turns": list(turns),
        "gold_sha256": actual_hash,
    }
    if case_id in EXPLORATORY_CASE_SOURCES:
        result.update({
            "source_case_id": source_case_id,
            "split": "EXPLORATORY",
            "experiment_class": "EXPLORATORY_COUNTERFACTUAL_NOT_FROZEN_CASE",
        })
    return result


def initialize_case_runtime(
    case_id: str,
    runtime_name: str,
    *,
    root: str | Path | None = None,
) -> Path:
    """Create a new runtime using the existing User Demo initializer only."""
    from initialize_demo import initialize_user_demo
    from runtime_paths import resolve_user_demo_runtime

    load_frozen_case(case_id)
    repo_root = Path(root or ROOT).resolve()
    if runtime_name == "user-demo":
        raise EvaluationPreflightError("EVALUATION_REQUIRES_NAMED_ISOLATED_RUNTIME")
    try:
        runtime_dir = resolve_user_demo_runtime(runtime_name, root=repo_root)
    except ValueError as error:
        raise EvaluationPreflightError("USER_DEMO_RUNTIME_NAME_INVALID") from error
    runtime_registry = (
        _e03_runtime_registry() if case_id == "E03-D" else
        _e04_runtime_registry() if case_id == "E04-H" else None
    )
    initialize_user_demo(
        runtime_dir,
        require_absent_directory=True,
        s3_fixture_profile=CASE_S3_PROFILES.get(case_id, "standard"),
    )
    if runtime_registry is not None:
        registry_path = runtime_dir / "assistant-access.json"
        try:
            with registry_path.open("x", encoding="utf-8", newline="\n") as stream:
                json.dump(runtime_registry, stream, ensure_ascii=False, indent=2)
                stream.write("\n")
        except FileExistsError as error:
            raise EvaluationPreflightError("CASE_RUNTIME_REGISTRY_ALREADY_EXISTS") from error
    return runtime_dir


def _e03_runtime_registry() -> dict[str, Any]:
    """Derive the literal Gold project grant from the checked-in trusted catalog."""
    catalog = ROOT / "knowledge" / "async-callback"
    manifest_path = catalog / "manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise EvaluationPreflightError("E03_TRUSTED_MANIFEST_UNAVAILABLE") from error
    required = {
        "callback-retry-contract": ("1.0.0", "local:orders-async-demo/contract-v1"),
        "callback-retry-contract-v2": ("2.0.0", "local:orders-async-demo/contract-v2"),
    }
    items = manifest.get("documents") if isinstance(manifest, dict) else None
    if not isinstance(items, list):
        raise EvaluationPreflightError("E03_TRUSTED_MANIFEST_INVALID")
    refs: list[dict[str, str]] = []
    for document_id, (version, source) in required.items():
        rows = [row for row in items if isinstance(row, dict) and row.get("document_id") == document_id]
        if len(rows) != 1:
            raise EvaluationPreflightError("E03_TRUSTED_DOCUMENT_NOT_UNIQUE")
        row = rows[0]
        content_path = catalog / str(row.get("file", ""))
        try:
            actual_digest = hashlib.sha256(content_path.read_bytes()).hexdigest()
        except OSError as error:
            raise EvaluationPreflightError("E03_TRUSTED_DOCUMENT_UNAVAILABLE") from error
        if (
            row.get("version") != version
            or row.get("source") != source
            or row.get("digest") != actual_digest
            or row.get("active") is not True
        ):
            raise EvaluationPreflightError("E03_TRUSTED_DOCUMENT_MANIFEST_MISMATCH")
        refs.append({
            "document_id": document_id,
            "version": version,
            "digest": actual_digest,
            "source": source,
        })
    return {
        "schema_version": 1,
        "projects": [{
            "project_id": "orders-async-demo",
            "title": "E03 isolated protocol evaluation",
            "tenant_id": "tenant-a",
            "actor_ids": ["support-a"],
            "roles": ["SUPPORT"],
            "active": True,
            "grant_version": 1,
            "configured_contract_version": 2,
            "document_ids": [row["document_id"] for row in refs],
            "evaluation_fixture": {
                "case_id": "E03-D",
                "manifest": "knowledge/async-callback/manifest.json",
                "documents": refs,
            },
        }],
    }


def _e04_fixture_manifest() -> tuple[dict[str, Any], str]:
    """Validate the post-freeze absence fixture against the locked source files."""
    path = E04_FIXTURE_MANIFEST_PATH
    if path.is_symlink() or not path.is_file():
        raise EvaluationPreflightError("E04_FIXTURE_MANIFEST_UNAVAILABLE")
    try:
        raw = path.read_bytes()
        manifest = json.loads(raw.decode("utf-8"))
        trusted_path = ROOT / "knowledge" / "async-callback" / "manifest.json"
        trusted_raw = trusted_path.read_bytes()
        trusted = json.loads(trusted_raw.decode("utf-8"))
        freeze = json.loads(FROZEN_HASHES_PATH.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise EvaluationPreflightError("E04_FIXTURE_MANIFEST_INVALID") from error
    actual_fixture_sha = hashlib.sha256(raw).hexdigest()
    allowed_ids = ["callback-retry-contract", "callback-retry-contract-v2"]
    if not isinstance(manifest, dict) or not isinstance(trusted, dict):
        raise EvaluationPreflightError("E04_FIXTURE_MANIFEST_INVALID")
    if (
        manifest.get("schema_version") != 1
        or manifest.get("case_id") != "E04-H"
        or manifest.get("fixture_specification_status") != "POST_FREEZE_FIXTURE_SPECIFIED"
        or manifest.get("base_sha") != "9dd9bb1366bdeaf601f0023f66a443c9f8b6f38a"
        or manifest.get("trusted_source_manifest", {}).get("relative_path")
        != "knowledge/async-callback/manifest.json"
        or manifest.get("trusted_source_manifest", {}).get("sha256")
        != hashlib.sha256(trusted_raw).hexdigest()
        or manifest.get("frozen_gold", {}).get("cases_sha256") != freeze["files"]["CASES.json"]["sha256"]
        or manifest.get("frozen_gold", {}).get("rubric_sha256") != freeze["files"]["RUBRIC.json"]["sha256"]
        or manifest.get("frozen_gold", {}).get("eval_protocol_sha256") != freeze["files"]["EVAL_PROTOCOL.md"]["sha256"]
    ):
        raise EvaluationPreflightError("E04_FIXTURE_MANIFEST_BASE_OR_FREEZE_MISMATCH")
    authorization = manifest.get("authorization_fixture", {})
    if (
        authorization.get("tenant_id") != "tenant-a"
        or authorization.get("actor_id") != "support-a"
        or authorization.get("role") != "SUPPORT"
        or authorization.get("project_id") != "orders-e04-absence"
        or authorization.get("allowed_document_ids") != allowed_ids
        or authorization.get("grant_version") != 1
        or authorization.get("configured_contract_version") != 2
        or authorization.get("configured_contract_version_semantics")
        != "Synthetic retrieval default required by the existing registry schema; not a claim about a real project or deployed version."
    ):
        raise EvaluationPreflightError("E04_FIXTURE_SCOPE_INVALID")
    rows = manifest.get("documents")
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows) or [
        row.get("document_id") for row in rows
    ] != allowed_ids:
        raise EvaluationPreflightError("E04_FIXTURE_DOCUMENT_SET_INVALID")
    trusted_rows = trusted.get("documents")
    if not isinstance(trusted_rows, list):
        raise EvaluationPreflightError("E04_TRUSTED_SOURCE_MANIFEST_INVALID")
    expected_specs = {
        "callback-retry-contract": ("1.0.0", "local:orders-async-demo/contract-v1", "callback-retry-contract.md"),
        "callback-retry-contract-v2": ("2.0.0", "local:orders-async-demo/contract-v2", "callback-retry-contract-v2.md"),
    }
    for item in rows:
        document_id = item["document_id"]
        version, source, filename = expected_specs[document_id]
        trusted_matches = [
            row for row in trusted_rows if isinstance(row, dict) and row.get("document_id") == document_id
        ]
        if len(trusted_matches) != 1:
            raise EvaluationPreflightError("E04_TRUSTED_DOCUMENT_NOT_UNIQUE")
        trusted_row = trusted_matches[0]
        content_path = ROOT / "knowledge" / "async-callback" / filename
        try:
            content = content_path.read_bytes()
            manifest_content = base64.b64decode(item.get("content_base64_exact_bytes", ""), validate=True)
        except (OSError, ValueError) as error:
            raise EvaluationPreflightError("E04_TRUSTED_DOCUMENT_UNAVAILABLE") from error
        digest = hashlib.sha256(content).hexdigest()
        if (
            item.get("relative_path") != content_path.relative_to(ROOT).as_posix()
            or item.get("version") != version
            or item.get("contract_versions") != [1 if document_id == "callback-retry-contract" else 2]
            or item.get("source") != source
            or item.get("sha256") != digest
            or item.get("content_sha256", digest) != digest
            or item.get("byte_length") != len(content)
            or item.get("content_utf8") != content.decode("utf-8")
            or manifest_content != content
            or trusted_row.get("version") != version
            or trusted_row.get("source") != source
            or trusted_row.get("file") != filename
            or trusted_row.get("digest") != digest
            or trusted_row.get("active") is not True
        ):
            raise EvaluationPreflightError("E04_TRUSTED_DOCUMENT_DIGEST_MISMATCH")
    absence = manifest.get("absence_and_claim_boundary", {})
    if (
        absence.get("authorized_scope_versions") != ["1.0.0", "2.0.0"]
        or absence.get("v1_4_document_registered_in_this_fixture") is not False
        or absence.get("two_conflicting_migration_notes_provided") is not False
        or absence.get("user_claim_about_conflicting_notes") != "UNVERIFIED_USER_ASSERTION_ONLY"
    ):
        raise EvaluationPreflightError("E04_ABSENCE_BOUNDARY_INVALID")
    evaluation_boundary = manifest.get("evaluation_boundary", {})
    if not isinstance(evaluation_boundary, dict) or any(
        evaluation_boundary.get(key) is not False
        for key in (
            "frozen_question_modified", "gold_or_rubric_in_model_context",
            "expected_answer_in_model_context", "tool_order_forced",
            "real_provider_authorized_by_this_manifest", "fixture_outputs_are_real_model_scores",
        )
    ):
        raise EvaluationPreflightError("E04_EVALUATION_BOUNDARY_INVALID")
    if any("1.4" in str(row.get("version", "")) for row in rows):
        raise EvaluationPreflightError("E04_V1_4_MUST_NOT_BE_IN_FIXTURE")
    return manifest, actual_fixture_sha


def _e04_runtime_registry() -> dict[str, Any]:
    """Reuse E03's verified document references under a new runtime-local project grant."""
    fixture, manifest_sha = _e04_fixture_manifest()
    registry = _e03_runtime_registry()
    project = json.loads(json.dumps(registry["projects"][0]))
    project.update({
        "project_id": "orders-e04-absence",
        "title": "E04-H isolated callback retry document scope",
        "evaluation_fixture": {
            "case_id": "E04-H",
            "fixture_specification_status": "POST_FREEZE_FIXTURE_SPECIFIED",
            "manifest_path": E04_FIXTURE_MANIFEST_PATH.relative_to(ROOT).as_posix(),
            "manifest_sha256": manifest_sha,
            "documents": [
                {"document_id": row["document_id"], "version": row["version"],
                 "digest": row["sha256"], "source": row["source"]}
                for row in fixture["documents"]
            ],
        },
    })
    return {"schema_version": 1, "projects": [project]}


def _table_exists(connection, name: str) -> bool:
    return connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,),
    ).fetchone() is not None


def _count(connection, table: str) -> int:
    if not _table_exists(connection, table):
        return 0
    return int(connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0])


def inspect_case_runtime(
    case_id: str,
    runtime_name: str,
    *,
    root: str | Path | None = None,
) -> dict[str, Any]:
    """Inspect an isolated runtime without opening it for writes."""
    import sqlite3

    from runtime_paths import resolve_user_demo_database_paths, resolve_user_demo_runtime

    load_frozen_case(case_id)
    repo_root = Path(root or ROOT).resolve()
    try:
        runtime_dir = resolve_user_demo_runtime(runtime_name, root=repo_root)
        domain_path, checkpoint_path = resolve_user_demo_database_paths(runtime_name, root=repo_root)
    except ValueError as error:
        raise EvaluationPreflightError("USER_DEMO_RUNTIME_PATH_REJECTED") from error
    if not runtime_dir.is_dir() or not domain_path.is_file() or not checkpoint_path.is_file():
        raise EvaluationPreflightError("ISOLATED_RUNTIME_INCOMPLETE")
    for path in (runtime_dir, domain_path, checkpoint_path):
        if path.is_symlink() or (getattr(path, "is_junction", None) and path.is_junction()):
            raise EvaluationPreflightError("ISOLATED_RUNTIME_REPARSE_POINT")

    connection = sqlite3.connect(domain_path.resolve().as_uri() + "?mode=ro", uri=True)
    connection.execute("PRAGMA query_only = ON")
    connection.row_factory = sqlite3.Row
    try:
        counts = {
            "sessions": _count(connection, "sessions"),
            "messages": _count(connection, "messages"),
            "task_bindings": _count(connection, "task_bindings"),
            "task_runs": _count(connection, "task_runs"),
            "personal_memories": _count(connection, "personal_memories"),
            "assistant_calls": _count(connection, "assistant_calls"),
            "provider_spends": _count(connection, "assistant_runtime_spends"),
            "provider_send_grants": _count(connection, "assistant_runtime_spends") and int(
                connection.execute(
                    "SELECT COUNT(*) FROM assistant_runtime_spends WHERE send_granted_at IS NOT NULL",
                ).fetchone()[0]
            ) or 0,
            "unknown_requests": _count(connection, "assistant_runtime_spends") and int(
                connection.execute(
                    "SELECT COUNT(*) FROM assistant_runtime_spends WHERE status='UNKNOWN'",
                ).fetchone()[0]
            ) or 0,
        }
        grant_present = any(
            _count(connection, table) > 0 for table in (
                "assistant_runtime_authority", "assistant_runtime_pools",
                "assistant_runtime_default_grant",
            )
        )
        result: dict[str, Any] = {
            "runtime_name": runtime_name,
            "domain_path": str(domain_path),
            "checkpoint_path": str(checkpoint_path),
            **counts,
            "runtime_grant_present": grant_present,
        }
        if case_id in {"E03-D", "E04-H"}:
            registry_path = runtime_dir / "assistant-access.json"
            if registry_path.is_symlink() or not registry_path.is_file():
                result["assistant_knowledge_registry"] = {"present": False, "valid": False}
            else:
                try:
                    actual_registry = json.loads(registry_path.read_text(encoding="utf-8"))
                    expected_registry = (
                        _e03_runtime_registry() if case_id == "E03-D" else _e04_runtime_registry()
                    )
                    valid_registry = actual_registry == expected_registry
                except (OSError, json.JSONDecodeError, EvaluationPreflightError):
                    actual_registry = {}
                    valid_registry = False
                result["assistant_knowledge_registry"] = {
                    "present": True,
                    "valid": valid_registry,
                    "projects": [
                        {"tenant_id": item.get("tenant_id"), "project_id": item.get("project_id"),
                         "document_ids": item.get("document_ids", [])}
                        for item in actual_registry.get("projects", [])
                        if isinstance(item, dict)
                    ] if isinstance(actual_registry, dict) else [],
                }
                if case_id == "E04-H":
                    try:
                        _manifest, manifest_sha = _e04_fixture_manifest()
                    except EvaluationPreflightError:
                        manifest_sha = None
                    result["assistant_knowledge_registry"].update({
                        "fixture_specification_status": "POST_FREEZE_FIXTURE_SPECIFIED",
                        "fixture_manifest_sha256": manifest_sha,
                        "v1_4_absent_in_authorized_scope": bool(
                            valid_registry and manifest_sha and
                            "callback-retry-contract-v1-4" not in actual_registry["projects"][0].get("document_ids", [])
                        ),
                    })
        result["fresh"] = all(
            counts[key] == 0 for key in (
                "sessions", "messages", "task_bindings", "task_runs",
                "personal_memories", "assistant_calls", "provider_spends",
            )
        )
        fixture = S3_FIXTURE_EXPECTATIONS.get(case_id)
        if fixture:
            row = connection.execute(
                """SELECT d.status AS delivery_status,d.event_id AS delivery_event_id,
                          d.receiver_http_status,r.status AS receiver_status,
                          r.event_id AS receiver_event_id
                   FROM s3_deliveries d JOIN s3_receivers r
                     ON r.tenant_id=d.tenant_id AND r.service_id=d.service_id AND r.order_id=d.order_id
                   WHERE d.tenant_id='tenant-a' AND d.order_id=?""",
                (fixture["target_order_id"],),
            ).fetchone()
            if row is not None:
                result.update({
                    "s3_order_id": fixture["target_order_id"],
                    "delivery_status": str(row["delivery_status"]),
                    "receiver_http_status": row["receiver_http_status"],
                    "receiver_status": str(row["receiver_status"]),
                    "delivery_event_id": str(row["delivery_event_id"]),
                    "receiver_event_id": str(row["receiver_event_id"]),
                })
            else:
                result["s3_order_id"] = None
            if fixture.get("decoy_order_id"):
                decoy = connection.execute(
                    """SELECT d.status AS delivery_status,d.event_id AS delivery_event_id,
                              d.receiver_http_status,r.status AS receiver_status,
                              r.event_id AS receiver_event_id
                       FROM s3_deliveries d JOIN s3_receivers r
                         ON r.tenant_id=d.tenant_id AND r.service_id=d.service_id AND r.order_id=d.order_id
                       WHERE d.tenant_id='tenant-a' AND d.order_id=?""",
                    (fixture["decoy_order_id"],),
                ).fetchone()
                if decoy is not None:
                    result.update({
                        "decoy_order_id": fixture["decoy_order_id"],
                        "decoy_delivery_status": str(decoy["delivery_status"]),
                        "decoy_receiver_http_status": decoy["receiver_http_status"],
                        "decoy_receiver_status": str(decoy["receiver_status"]),
                        "decoy_delivery_event_id": str(decoy["delivery_event_id"]),
                        "decoy_receiver_event_id": str(decoy["receiver_event_id"]),
                    })
        return result
    finally:
        connection.close()


def _s3_fixture_mismatch(case_id: str, state: dict[str, Any]) -> str | None:
    """Validate the target and, when present, the separate decoy Event fixture."""
    fixture = S3_FIXTURE_EXPECTATIONS.get(case_id)
    if fixture is None:
        return None
    target_matches = (
        state.get("delivery_status") == "ACKNOWLEDGED"
        and state.get("receiver_http_status") == 202
        and state.get("receiver_status") == fixture["target_receiver_status"]
        and state.get("delivery_event_id") == fixture["target_event_id"]
        and state.get("receiver_event_id") == fixture["target_event_id"]
    )
    if not target_matches:
        return (
            "OBSERVATION_CONTRAST_FIXTURE_MISMATCH"
            if case_id == OBSERVATION_CONTRAST_CASE_ID
            else "E07_TRUSTED_FIXTURE_MISMATCH"
        )
    if fixture.get("decoy_order_id"):
        decoy_matches = (
            state.get("decoy_order_id") == fixture["decoy_order_id"]
            and state.get("decoy_delivery_status") == "ACKNOWLEDGED"
            and state.get("decoy_receiver_http_status") == 202
            and state.get("decoy_receiver_status") == fixture["decoy_receiver_status"]
            and state.get("decoy_delivery_event_id") == fixture["decoy_event_id"]
            and state.get("decoy_receiver_event_id") == fixture["decoy_event_id"]
            and fixture["decoy_event_id"] != fixture["target_event_id"]
            and fixture["decoy_order_id"] != fixture["target_order_id"]
        )
        if not decoy_matches:
            return "OBSERVATION_CONTRAST_FIXTURE_MISMATCH"
    return None


def _s3_fixture_summary(case_id: str, state: dict[str, Any]) -> dict[str, Any] | None:
    if case_id not in S3_FIXTURE_EXPECTATIONS:
        return None
    summary = {
        "target_order_id": state.get("s3_order_id"),
        "target_event_id": state.get("delivery_event_id"),
        "target_delivery_status": state.get("delivery_status"),
        "target_receiver_status": state.get("receiver_status"),
    }
    if case_id == OBSERVATION_CONTRAST_CASE_ID:
        summary.update({
            "decoy_order_id": state.get("decoy_order_id"),
            "decoy_event_id": state.get("decoy_delivery_event_id"),
            "decoy_delivery_status": state.get("decoy_delivery_status"),
            "decoy_receiver_status": state.get("decoy_receiver_status"),
        })
    return summary


def _read_s3_task_binding_scope(runtime_dir: Path, task_id: str) -> dict[str, Any]:
    """Read the post-API binding through the Domain validator, without writes."""
    import sqlite3

    from opspilot.domain.s3 import get_s3_binding

    database = runtime_dir / "domain.sqlite3"
    connection = sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True)
    connection.execute("PRAGMA query_only = ON")
    connection.row_factory = sqlite3.Row
    try:
        binding = get_s3_binding(connection, task_id)
        return {
            key: binding.get(key)
            for key in (
                "task_id", "tenant_id", "actor_id", "service_id", "integration_id",
                "principal_id", "order_id",
            )
        }
    finally:
        connection.close()


def _loopback_url(value: str, *, label: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost"}:
        raise EvaluationPreflightError(label + "_MUST_USE_LOCAL_LOOPBACK")
    return value.rstrip("/")


def _manifest_matches(runtime_name: str, runtime_dir: Path, root: Path) -> dict[str, Any]:
    manifest_path = runtime_dir / "processes.json"
    if not manifest_path.is_file():
        raise EvaluationPreflightError("MANAGED_LIVE_SERVICES_NOT_RUNNING")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as error:
        raise EvaluationPreflightError("MANAGED_PROCESS_MANIFEST_INVALID") from error
    expected = {
        "root": root,
        "domainDb": runtime_dir / "domain.sqlite3",
        "checkpointDb": runtime_dir / "checkpoint.sqlite3",
    }
    if manifest.get("runtimeName") != runtime_name:
        raise EvaluationPreflightError("MANAGED_PROCESS_RUNTIME_MISMATCH")
    for field, path in expected.items():
        recorded = manifest.get(field)
        if not isinstance(recorded, str) or Path(recorded).resolve() != path.resolve():
            raise EvaluationPreflightError("MANAGED_PROCESS_PATH_MISMATCH")
    if manifest.get("mode") != "Live":
        raise EvaluationPreflightError("MANAGED_PROCESS_NOT_STARTED_IN_LIVE_MODE")
    return manifest


def _budget_micro(value: str | Decimal) -> int:
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError) as error:
        raise EvaluationPreflightError("AUTHORIZED_BUDGET_INVALID") from error
    if not amount.is_finite() or amount <= 0:
        raise EvaluationPreflightError("AUTHORIZED_BUDGET_INVALID")
    micro = amount * Decimal(1_000_000)
    if micro != micro.to_integral_value():
        raise EvaluationPreflightError("AUTHORIZED_BUDGET_PRECISION_INVALID")
    return int(micro)


def live_preflight(
    case_id: str,
    runtime_name: str,
    *,
    authorized_max_cost_usd: str,
    api_origin: str = DEFAULT_API_ORIGIN,
    root: str | Path | None = None,
    client: Any | None = None,
) -> dict[str, Any]:
    """Check one fresh Live runtime and existing grant before any chat POST."""
    import httpx

    from runtime_admin import preflight as grant_preflight, read_env
    from runtime_paths import resolve_user_demo_runtime

    repo_root = Path(root or ROOT).resolve()
    api_origin = _loopback_url(api_origin, label="API_ORIGIN")
    state = inspect_case_runtime(case_id, runtime_name, root=repo_root)
    if not state["fresh"]:
        raise EvaluationPreflightError("CASE_RUNTIME_ALREADY_CONTAINS_SESSION_OR_RUN_DATA")
    if state["provider_send_grants"] or state["unknown_requests"]:
        raise EvaluationPreflightError("CASE_RUNTIME_ALREADY_HAS_PROVIDER_ACTIVITY")
    mismatch = _s3_fixture_mismatch(case_id, state)
    if mismatch:
        raise EvaluationPreflightError(mismatch)
    if case_id in {"E03-D", "E04-H"} and not state.get("assistant_knowledge_registry", {}).get("valid"):
        raise EvaluationPreflightError(f"{case_id.replace('-', '_')}_ISOLATED_KNOWLEDGE_REGISTRY_INVALID")

    runtime_dir = resolve_user_demo_runtime(runtime_name, root=repo_root)
    _manifest_matches(runtime_name, runtime_dir, repo_root)
    domain_path = Path(state["domain_path"])
    grant = grant_preflight(domain_path, read_env())
    if int(grant["provider_sends"]) != 0 or int(grant["unknown_requests"]) != 0:
        raise EvaluationPreflightError("CASE_RUNTIME_PROVIDER_HISTORY_NOT_EMPTY")
    authorized_cap = _budget_micro(authorized_max_cost_usd)
    if int(grant["total_limit_usd_micro"]) > authorized_cap:
        raise EvaluationPreflightError("RUNTIME_GRANT_EXCEEDS_CASE_AUTHORIZED_CAP")
    # The default Assistant Run contract durably permits at most eight model
    # dispatches. Require enough unused pool for eight worst-case reservations.
    maximum_dispatch_reserve = (
        int(grant["one_max_request_reserve_usd_micro"])
        * DEFAULT_MAX_RUN_MODEL_DISPATCHES
    )
    if int(grant["remaining_usd_micro"]) < maximum_dispatch_reserve:
        raise EvaluationPreflightError("CASE_BUDGET_BELOW_EIGHT_REQUEST_RESERVES")

    owns_client = client is None
    check_client = client or httpx.Client(timeout=5.0, follow_redirects=False)
    try:
        response = check_client.get(api_origin + "/api/health")
    except Exception as error:
        raise EvaluationPreflightError("LOCAL_API_UNAVAILABLE") from error
    finally:
        if owns_client:
            check_client.close()
    if response.status_code != 200:
        raise EvaluationPreflightError("LOCAL_API_HEALTHCHECK_FAILED")
    health = response.json()
    if health.get("status") != "ok" or (health.get("worker") or {}).get("ready") is not True:
        raise EvaluationPreflightError("LOCAL_API_WORKER_NOT_READY")
    result = {
        "status": "READY_FOR_EXPLICIT_CASE_RUN",
        "case_id": case_id,
        "runtime_name": runtime_name,
        "api_origin": api_origin,
        "provider_requests_so_far": 0,
        "unknown_requests": 0,
        "grant_remaining_usd_micro": int(grant["remaining_usd_micro"]),
        "grant_limit_usd_micro": int(grant["total_limit_usd_micro"]),
        "authorized_cap_usd_micro": authorized_cap,
        "maximum_provider_dispatches_per_run": DEFAULT_MAX_RUN_MODEL_DISPATCHES,
        "worst_case_run_reserve_usd_micro": maximum_dispatch_reserve,
        "task_binding_created": False,
    }
    fixture_summary = _s3_fixture_summary(case_id, state)
    if fixture_summary is not None:
        result["s3_fixture"] = fixture_summary
    if case_id in EXPLORATORY_CASE_SOURCES:
        result["experiment_class"] = "EXPLORATORY_COUNTERFACTUAL_NOT_FROZEN_CASE"
        result["source_question_case_id"] = EXPLORATORY_CASE_SOURCES[case_id]
    return result


def _raise_for_status(response: Any, expected: set[int], label: str) -> dict[str, Any]:
    if response.status_code not in expected:
        raise EvaluationPreflightError(f"{label}_HTTP_{response.status_code}")
    try:
        value = response.json()
    except Exception as error:
        raise EvaluationPreflightError(label + "_INVALID_JSON") from error
    if not isinstance(value, dict):
        raise EvaluationPreflightError(label + "_INVALID_RESPONSE")
    return value


def _wait_for_terminal(client: Any, run_id: str, *, timeout_seconds: float) -> tuple[dict[str, Any], bool]:
    terminal = {"SUCCEEDED", "FAILED", "BLOCKED", "WAITING_INPUT", "WAITING_APPROVAL"}
    deadline = time.monotonic() + timeout_seconds
    while True:
        try:
            response = client.get(f"/api/runs/{run_id}")
        except Exception as error:
            raise EvaluationPreflightError("RUN_STATUS_READ_FAILED_NO_RESUBMIT") from error
        run = _raise_for_status(response, {200}, "RUN_STATUS")
        status = str(run.get("status", ""))
        if status in terminal:
            return run, False
        if time.monotonic() >= deadline:
            return run, True
        time.sleep(0.2)


def _token_values(value: Any) -> dict[str, int] | None:
    if isinstance(value, list):
        value = value[0] if value else None
    if not isinstance(value, dict):
        return None
    aliases = {
        "input_tokens": ("input_tokens", "prompt_tokens"),
        "output_tokens": ("output_tokens", "completion_tokens"),
        "total_tokens": ("total_tokens",),
    }
    result: dict[str, int] = {}
    for target, keys in aliases.items():
        number = next((value[key] for key in keys if value.get(key) is not None), None)
        if not isinstance(number, int):
            return None
        result[target] = number
    return result


def _result_metrics(trace: dict[str, Any], execution_mode: str) -> dict[str, Any]:
    spends = trace.get("runtime_spends", [])
    summary = trace.get("session_spend_summary", {})
    known_usage = [_token_values(row.get("usage_json")) for row in spends]
    received_spends = [row for row in spends if row.get("response_status") is not None]
    usage_complete = all(value is not None for value in (
        _token_values(row.get("usage_json")) for row in received_spends
    ))
    input_tokens = sum(item["input_tokens"] for item in known_usage if item is not None)
    output_tokens = sum(item["output_tokens"] for item in known_usage if item is not None)
    total_tokens = sum(item["total_tokens"] for item in known_usage if item is not None)
    settlement_complete = all(row.get("settled_usd_micro") is not None for row in spends)
    settled = sum(int(row["settled_usd_micro"]) for row in spends if row.get("settled_usd_micro") is not None)
    calls = trace.get("assistant_calls_actual_model_input_output", [])
    model_calls = [row for row in calls if row.get("kind") == "MODEL"]
    mcp_calls = [row for row in calls if row.get("kind") == "MCP"]
    fixture_usage = [_token_values(row.get("usage_json")) for row in model_calls]
    fixture_usage_complete = all(value is not None for value in fixture_usage)
    fixture_total = {
        "input_tokens": sum(row["input_tokens"] for row in fixture_usage if row is not None),
        "output_tokens": sum(row["output_tokens"] for row in fixture_usage if row is not None),
        "total_tokens": sum(row["total_tokens"] for row in fixture_usage if row is not None),
    } if fixture_usage_complete and execution_mode == "FIXTURE" else None
    return {
        "provider_send_grants": int(summary.get("send_granted_count", 0)),
        "provider_responses_received": int(summary.get("responses_received_count", 0)),
        "unknown_requests": int(summary.get("unknown_count", 0)),
        "provider_usage_complete": usage_complete,
        "provider_input_tokens": input_tokens if usage_complete and received_spends else None,
        "provider_output_tokens": output_tokens if usage_complete and received_spends else None,
        "provider_total_tokens": total_tokens if usage_complete and received_spends else None,
        "settled_usd_micro": settled if settlement_complete and spends else None,
        "provider_cost_usd": f"{Decimal(settled) / Decimal(1_000_000):.6f}"
        if settlement_complete and spends else None,
        "mcp_tools_call_count": len(mcp_calls),
        "mcp_tool_names": sorted(str(row.get("request_json", {}).get("name", "")) for row in mcp_calls),
        "observation_count": len(trace.get("observations", [])),
        "evidence_count": len(trace.get("evidence", [])),
        "fixture_model_dispatches": len(model_calls) if execution_mode == "FIXTURE" else 0,
        "fixture_token_metadata": fixture_total,
    }


def _observation_contrast_audit(
    trace: dict[str, Any], *, run_id: str, task_id: str | None,
) -> dict[str, Any]:
    """Summarize only task-scoped Receiver observations issued by this Run."""
    fixture = S3_FIXTURE_EXPECTATIONS[OBSERVATION_CONTRAST_CASE_ID]
    task_calls = {
        row.get("call_id"): row
        for row in trace.get("assistant_calls_actual_model_input_output", [])
        if row.get("run_id") == run_id and row.get("kind") == "MCP"
    }
    receiver_observations: list[dict[str, Any]] = []
    if task_id:
        for observation in trace.get("observations", []):
            call = task_calls.get(observation.get("call_id"))
            result = observation.get("result_json")
            if (
                observation.get("task_id") != task_id
                or not call
                or call.get("status") != "OK"
                or observation.get("status") != "OK"
                or not isinstance(result, dict)
                or result.get("fact_type") != "s3_receiver"
                or result.get("tenant_id") != "tenant-a"
            ):
                continue
            facts = result.get("facts")
            if not isinstance(facts, dict) or facts.get("tenant_id") != "tenant-a":
                continue
            receiver_observations.append({
                "observation_id": observation.get("observation_id"),
                "run_id": run_id,
                "task_id": task_id,
                "tenant_id": result.get("tenant_id"),
                "order_id": facts.get("order_id"),
                "event_id": facts.get("event_id"),
                "receiver_status": facts.get("status"),
                "observed_at": result.get("observed_at"),
                "original_result_ref": result.get("original_result_ref"),
                "evidence_id": observation.get("evidence_id"),
                "trust_class": result.get("trust_class"),
            })
    target_observations = [
        row for row in receiver_observations
        if row.get("order_id") == fixture["target_order_id"]
        and row.get("event_id") == fixture["target_event_id"]
    ]
    supported = any(
        row.get("receiver_status") == "PROCESSED"
        and row.get("evidence_id")
        and row.get("original_result_ref")
        for row in target_observations
    )
    return {
        "experiment_class": "EXPLORATORY_COUNTERFACTUAL_NOT_FROZEN_E08_H",
        "source_question_case_id": "E07-D",
        "task_binding_id": task_id,
        "target_order_id": fixture["target_order_id"],
        "target_event_id": fixture["target_event_id"],
        "decoy_order_id": fixture["decoy_order_id"],
        "decoy_event_id": fixture["decoy_event_id"],
        "current_run_task_scoped_receiver_observations": receiver_observations,
        "target_receiver_observation_ids": [row.get("observation_id") for row in target_observations],
        "supports_target_processed_conclusion": supported,
    }


def _execute_case_once(
    client: Any,
    *,
    case_id: str,
    runtime_name: str,
    support_password: str,
    api_origin: str,
    web_origin: str,
    root: str | Path | None = None,
    execution_mode: str = "LIVE",
    timeout_seconds: float = DEFAULT_RUN_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """Submit exactly one frozen user turn through the formal Web API.

    This function never retries login/session/message POSTs. If a submission
    response is ambiguous, the caller must inspect the same runtime instead of
    posting the case again.
    """
    if execution_mode not in {"LIVE", "FIXTURE"}:
        raise ValueError("EXECUTION_MODE_INVALID")
    case = load_frozen_case(case_id)
    repo_root = Path(root or ROOT).resolve()
    from runtime_paths import resolve_user_demo_runtime

    runtime_dir = resolve_user_demo_runtime(runtime_name, root=repo_root)
    pre_state = inspect_case_runtime(case_id, runtime_name, root=repo_root)
    if not pre_state["fresh"]:
        raise EvaluationPreflightError("CASE_RUNTIME_ALREADY_CONTAINS_SESSION_OR_RUN_DATA")
    if pre_state["provider_send_grants"] or pre_state["unknown_requests"]:
        raise EvaluationPreflightError("CASE_RUNTIME_ALREADY_HAS_PROVIDER_ACTIVITY")
    mismatch = _s3_fixture_mismatch(case_id, pre_state)
    if mismatch:
        raise EvaluationPreflightError(mismatch)
    if case_id in {"E03-D", "E04-H"} and not pre_state.get("assistant_knowledge_registry", {}).get("valid"):
        raise EvaluationPreflightError(f"{case_id.replace('-', '_')}_ISOLATED_KNOWLEDGE_REGISTRY_INVALID")
    output = runtime_dir / "evidence" / f"{case_id}.json"
    result_output = runtime_dir / "evidence" / f"{case_id}.result.json"
    if output.exists() or result_output.exists():
        raise EvaluationPreflightError("CASE_EVIDENCE_OUTPUT_ALREADY_EXISTS")
    api_origin = _loopback_url(api_origin, label="API_ORIGIN")
    web_origin = _loopback_url(web_origin, label="WEB_ORIGIN")
    started = time.monotonic()
    login_response = client.post(
        api_origin + "/api/auth/login",
        headers={"Origin": web_origin},
        json={"actor_id": "support-a", "password": support_password},
    )
    identity = _raise_for_status(login_response, {200}, "LOGIN")
    if identity.get("actor_id") != "support-a" or identity.get("tenant_id") != "tenant-a":
        raise EvaluationPreflightError("SUPPORT_IDENTITY_SCOPE_MISMATCH")
    csrf = str(identity.get("csrf_token", ""))
    if not csrf:
        raise EvaluationPreflightError("CSRF_TOKEN_MISSING")
    write_headers = {"Origin": web_origin, "X-CSRF-Token": csrf}
    session_response = client.post(api_origin + "/api/sessions", headers=write_headers)
    session = _raise_for_status(session_response, {201}, "SESSION_CREATE")
    session_id = str(session.get("session_id", ""))
    if not session_id:
        raise EvaluationPreflightError("SESSION_ID_MISSING")

    knowledge_scope: dict[str, Any] | None = None
    if case_id in {"E03-D", "E04-H"}:
        project_id = "orders-async-demo" if case_id == "E03-D" else "orders-e04-absence"
        scope_response = client.get(f"{api_origin}/api/sessions/{session_id}/assistant/scopes")
        scope = _raise_for_status(scope_response, {200}, f"{case_id.replace('-', '_')}_SCOPE_DISCOVERY")
        items = scope.get("items")
        if (
            not isinstance(items, list)
            or [item.get("project_id") for item in items if isinstance(item, dict)] != [project_id]
            or scope.get("selected_project") != project_id
            or items[0].get("configured_contract_version") != 2
        ):
            raise EvaluationPreflightError(f"{case_id.replace('-', '_')}_ISOLATED_PROJECT_SCOPE_MISMATCH")
        selected_scope = client.put(
            f"{api_origin}/api/sessions/{session_id}/assistant/scopes",
            headers=write_headers,
            json={"project_id": project_id},
        )
        selected = _raise_for_status(selected_scope, {200}, f"{case_id.replace('-', '_')}_SCOPE_SELECTION")
        if selected.get("selected_project") != project_id:
            raise EvaluationPreflightError(f"{case_id.replace('-', '_')}_ISOLATED_PROJECT_SCOPE_SELECTION_FAILED")
        try:
            runtime_registry = json.loads(
                (runtime_dir / "assistant-access.json").read_text(encoding="utf-8")
            )
            scoped_project = runtime_registry["projects"][0]
        except (OSError, json.JSONDecodeError, KeyError, IndexError, TypeError) as error:
            raise EvaluationPreflightError(f"{case_id.replace('-', '_')}_RUNTIME_REGISTRY_INVALID") from error
        knowledge_scope = {
            "project_id": project_id,
            "configured_contract_version": 2,
            "grant_version": items[0].get("grant_version"),
            "document_ids": list(scoped_project.get("document_ids", [])),
        }
        if case_id == "E04-H":
            fixture = scoped_project.get("evaluation_fixture", {})
            knowledge_scope.update({
                "fixture_specification_status": "POST_FREEZE_FIXTURE_SPECIFIED",
                "fixture_manifest_sha256": fixture.get("manifest_sha256"),
                "registered_versions": [row.get("version") for row in fixture.get("documents", [])],
                "v1_4_absence_claim_scope": "AUTHORIZED_RUNTIME_PROJECT_ONLY",
            })

    question = case["user_turns"][0]
    task_id: str | None = None
    if case_id in S3_FIXTURE_EXPECTATIONS:
        response = client.post(
            f"{api_origin}/api/sessions/{session_id}/assistant/order",
            headers={
                **write_headers,
                "Idempotency-Key": (
                    "r2-ar06-e07-" if case_id == "E07-D"
                    else "r2-ar06-observation-contrast-"
                ) + uuid.uuid4().hex,
            },
            json={"order_id": E07_ORDER_ID, "initial_message": question},
        )
        accepted = _raise_for_status(response, {200, 202}, "S3_TASK_BINDING_AND_RUN")
        task_id = str(accepted.get("task_id", "")) or None
    else:
        key_prefix = "r2-ar06-e05-" if case_id == "E05-D" else (
            "r2-ar06-" + case_id.lower().replace("-", "") + "-"
        )
        response = client.post(
            f"{api_origin}/api/sessions/{session_id}/assistant/messages",
            headers={
                **write_headers,
                "Idempotency-Key": key_prefix + uuid.uuid4().hex,
            },
            json={"body": question},
        )
        label = (
            "E05_MESSAGE_AND_RUN" if case_id == "E05-D" else
            "E03_MESSAGE_AND_RUN" if case_id == "E03-D" else
            "E04_MESSAGE_AND_RUN" if case_id == "E04-H" else
            "HOLDOUT_MESSAGE_AND_RUN"
        )
        accepted = _raise_for_status(response, {202}, label)
    run_id = str(accepted.get("run_id", ""))
    if not run_id:
        raise EvaluationPreflightError("RUN_ID_MISSING_AFTER_ACCEPTANCE")

    run, timed_out = _wait_for_terminal(client, run_id, timeout_seconds=timeout_seconds)
    elapsed_ms = max(0, round((time.monotonic() - started) * 1000))
    from export_live_evidence import export_session

    export_session(session_id, output, runtime_name=runtime_name, actor_id="support-a", root=repo_root)
    trace = json.loads(output.read_text(encoding="utf-8"))
    submitted = [row for row in trace["messages"] if row.get("role") == "USER"]
    if len(submitted) != 1 or submitted[0].get("body") != question:
        raise EvaluationPreflightError("EXPORTED_INPUT_DOES_NOT_MATCH_FROZEN_GOLD")
    exported_run = next((row for row in trace["runs"] if row.get("run_id") == run_id), None)
    if exported_run is None or exported_run.get("source_message_id") != submitted[0].get("message_id"):
        raise EvaluationPreflightError("EXPORTED_RUN_SOURCE_LINK_MISMATCH")
    if task_id and not any(row.get("task_id") == task_id for row in trace.get("task_bindings", [])):
        raise EvaluationPreflightError("EXPORTED_TRUSTED_TASK_BINDING_MISSING")
    if case_id in {"E03-D", "E04-H"} and (task_id is not None or trace.get("task_bindings")):
        raise EvaluationPreflightError(f"{case_id.replace('-', '_')}_MUST_NOT_CREATE_TASK_BINDING")
    if task_id:
        binding = next(
            (row for row in trace.get("task_bindings", []) if row.get("task_id") == task_id),
            None,
        )
        if not binding or binding.get("tenant_id") != "tenant-a" or binding.get("service_id") != "orders-async-demo":
            raise EvaluationPreflightError("EXPORTED_TRUSTED_TASK_BINDING_SCOPE_MISMATCH")
    if case_id in S3_FIXTURE_EXPECTATIONS:
        if not task_id:
            raise EvaluationPreflightError("S3_TRUSTED_TASK_BINDING_MISSING")
        task_binding_scope = _read_s3_task_binding_scope(runtime_dir, task_id)
        if (
            task_binding_scope.get("tenant_id") != "tenant-a"
            or task_binding_scope.get("order_id") != S3_FIXTURE_EXPECTATIONS[case_id]["target_order_id"]
            or task_binding_scope.get("service_id") != "orders-async-demo"
        ):
            raise EvaluationPreflightError("S3_TASK_BINDING_TARGET_MISMATCH")

    result_record: dict[str, Any] = {
        "schema": "r2-ar06-auto-live-case-result-v1",
        "case_id": case_id,
        "split": case["split"],
        "execution_mode": execution_mode,
        "assessment_status": "UNVERIFIED",
        "assessor_note": "Structured evidence only; independent Rubric scoring is pending.",
        "gold_sha256": case["gold_sha256"],
        "frozen_input_sha256": hashlib.sha256(question.encode("utf-8")).hexdigest(),
        "runtime_name": runtime_name,
        "session_id": session_id,
        "task_id": task_id,
        "run_id": run_id,
        "knowledge_scope": knowledge_scope,
        "run_status": str(run.get("status", "UNKNOWN")),
        "run_failure_code": run.get("waiting_reason") if run.get("status") != "SUCCEEDED" else None,
        "terminal_timeout": timed_out,
        "elapsed_ms": elapsed_ms,
        "trace_path": str(output),
        **_result_metrics(trace, execution_mode),
    }
    if case_id == OBSERVATION_CONTRAST_CASE_ID:
        result_record["source_question_case_id"] = case["source_case_id"]
        result_record["experiment_class"] = case["experiment_class"]
        result_record["task_binding_scope"] = task_binding_scope
        result_record["observation_contrast"] = _observation_contrast_audit(
            trace, run_id=run_id, task_id=task_id,
        )
    if case_id == "E04-H":
        result_record.update({
            "fixture_specification_status": "POST_FREEZE_FIXTURE_SPECIFIED",
            "fixture_manifest_sha256": knowledge_scope.get("fixture_manifest_sha256"),
            "absence_claim_scope": "AUTHORIZED_RUNTIME_PROJECT_ONLY",
            "real_model_semantic_score": "NOT_ESTABLISHED_BY_FIXTURE",
        })
    result_output.write_text(json.dumps(result_record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result_record


def execute_case(client: Any, **kwargs: Any) -> dict[str, Any]:
    """Serialize one case per isolated runtime and execute it at most once."""
    from runtime_paths import resolve_user_demo_runtime

    root = Path(kwargs.get("root") or ROOT).resolve()
    runtime_name = kwargs.get("runtime_name")
    if not isinstance(runtime_name, str):
        raise ValueError("USER_DEMO_RUNTIME_NAME_REQUIRED")
    runtime_dir = resolve_user_demo_runtime(runtime_name, root=root)
    lock_path = runtime_dir / ".r2-ar06-case-run.lock"
    try:
        descriptor = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as error:
        raise EvaluationPreflightError("CASE_RUN_ALREADY_ACTIVE_OR_REQUIRES_INSPECTION") from error
    try:
        os.write(descriptor, json.dumps({"pid": os.getpid(), "case_id": kwargs.get("case_id")}).encode("utf-8"))
        os.close(descriptor)
        descriptor = -1
        return _execute_case_once(client, **kwargs)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        try:
            lock_path.unlink()
        except FileNotFoundError:
            pass


def _local_support_password() -> str:
    from runtime_admin import read_env

    value = os.environ.get("OPSPILOT_WEB_SUPPORT_PASSWORD", "").strip()
    if value:
        return value
    return read_env().get("OPSPILOT_WEB_SUPPORT_PASSWORD", "").strip()


def make_e03_fixture_model(*, tool_order: str = "compare_then_excerpt"):
    """Create a deterministic offline model that chooses legal tools from results."""
    from langchain_core.language_models import BaseChatModel
    from langchain_core.messages import AIMessage, ToolMessage
    from langchain_core.outputs import ChatGeneration, ChatResult
    from pydantic import Field

    if tool_order not in {"compare_then_excerpt", "excerpt_then_compare"}:
        raise ValueError("E03_FIXTURE_TOOL_ORDER_INVALID")

    class E03ProtocolFixtureModel(BaseChatModel):
        tool_order: str = "compare_then_excerpt"
        dispatch_count: int = 0
        offered_tool_names: list[str] = Field(default_factory=list)
        decisions: list[dict[str, Any]] = Field(default_factory=list)
        seen: list[list[Any]] = Field(default_factory=list)

        @property
        def _llm_type(self) -> str:
            return "R2_AR06_E03_PROTOCOL_FIXTURE"

        def bind_tools(self, tools, **kwargs):
            self.offered_tool_names = [tool.name for tool in tools]
            return self

        @staticmethod
        def _payload(message):
            value = message.content
            if isinstance(value, str):
                try:
                    value = json.loads(value)
                except json.JSONDecodeError:
                    return {}
            while isinstance(value, dict) and set(value) == {"result"}:
                value = value["result"]
            return value if isinstance(value, dict) else {}

        @classmethod
        def _tool_results(cls, messages):
            names_by_id = {
                str(call.get("id")): str(call.get("name"))
                for message in messages
                for call in (getattr(message, "tool_calls", None) or [])
            }
            results = {}
            for message in messages:
                if isinstance(message, ToolMessage):
                    name = getattr(message, "name", None) or names_by_id.get(str(message.tool_call_id))
                    if name:
                        results[str(name)] = cls._payload(message)
            return results

        def _tool(self, name: str, args: dict[str, Any]) -> ChatResult:
            if name not in self.offered_tool_names:
                raise AssertionError("Fixture selected a tool that was not offered by the Assistant MCP server.")
            self.decisions.append({"action": "CALL", "tool": name, "args": args})
            message = AIMessage(content="", tool_calls=[{
                "name": name, "args": args,
                "id": f"e03-fixture-{len(self.decisions)}",
            }])
            message.usage_metadata = {"input_tokens": 24, "output_tokens": 11, "total_tokens": 35}
            return ChatResult(generations=[ChatGeneration(message=message)])

        def _answer(self, payloads: dict[str, Any]) -> ChatResult:
            discovery = payloads["list_scoped_protocol_documents"]
            comparison = payloads["compare_scoped_protocols"]
            excerpt_result = payloads["read_scoped_protocol_excerpt"]
            base = comparison.get("base_ref", {})
            target = comparison.get("target_ref", {})
            source_ref = next(iter(excerpt_result.get("source_refs", [])), {})
            excerpt = next(iter(excerpt_result.get("excerpts", [])), {})
            document_map = {
                row.get("document_id"): row
                for row in discovery.get("protocol_documents", [])
                if isinstance(row, dict)
            }
            if (
                discovery.get("project_id") != "orders-async-demo"
                or base.get("document_id") not in document_map
                or target.get("document_id") not in document_map
                or not source_ref.get("digest")
                or source_ref.get("document_id") != target.get("document_id")
            ):
                raise AssertionError("Fixture answer lacks current authorized E03 document evidence.")
            answer = (
                "## 协议版本与原文依据\n"
                f"授权资料项目为 {discovery['project_id']}。比较结果引用 "
                f"{base['document_id']} v{base['version']}（{base['source']}，Digest {base['digest']}）与 "
                f"{target['document_id']} v{target['version']}（{target['source']}，Digest {target['digest']}）。"
                f"比较摘要：{comparison.get('summary')}。"
                f"v2 原文摘录（{source_ref['document_id']} v{source_ref['version']}，"
                f"{source_ref['source']}，行 {source_ref['line_start']}-{source_ref['line_end']}）："
                f"“{excerpt.get('text', '')}”\n\n"
                "## 升级影响与兼容风险\n"
                "v1 将 503 与 TEMPORARY_UNAVAILABLE 视为可重试，并把 SCHEDULED 与 retry_at 解释为等待后续尝试；"
                "v2 要求依据服务端记录的 retryable failure code 和当前 retry policy 判断，且只有 attempt_count 达到 max_attempts、"
                "响应 digest/event/request 与当前 delivery row 匹配时，EXHAUSTED 才可作为处理依据。"
                "兼容风险是旧客户端、错误分类、重试策略和重试耗尽条件的语义可能不同。"
                "本题没有提供当前 JSON 配置或线上日志，因此不能断言某个线上字段需要怎样改值，也不能确认线上部署了哪个版本。\n\n"
                "## 研发检查清单\n"
                "1. 从可信发布环境确认线上实际 API 版本和当前 retry policy；本文档本身不能证明部署版本。\n"
                "2. 对照 v2 明确 retryable failure code 与可重试错误映射，并测试 503 与不可重试错误。\n"
                "3. 验证 attempt_count/max_attempts 边界及 SCHEDULED、retry_at、EXHAUSTED 的状态迁移。\n"
                "4. 校验响应 digest、event、request 与当前 delivery row 的关联，覆盖错配负例。\n"
                "5. 对旧、新客户端进行契约和回滚测试；未从线上环境核验前，将部署版本保持为未知。"
            )
            self.decisions.append({"action": "ANSWER"})
            message = AIMessage(content=answer)
            message.usage_metadata = {"input_tokens": 38, "output_tokens": 44, "total_tokens": 82}
            return ChatResult(generations=[ChatGeneration(message=message)])

        def _generate(self, messages, stop=None, run_manager=None, **kwargs):
            self.dispatch_count += 1
            self.seen.append(list(messages))
            payloads = self._tool_results(messages)
            discovery = payloads.get("list_scoped_protocol_documents")
            if discovery is None:
                return self._tool("list_scoped_protocol_documents", {"topic": "callback retry"})
            documents = discovery.get("protocol_documents", [])
            old = next((row for row in documents if str(row.get("version", "")).startswith("1.")), None)
            new = next((row for row in documents if str(row.get("version", "")).startswith("2.")), None)
            if old is None or new is None:
                raise AssertionError("Authorized callback retry v1/v2 documents were not discovered.")
            comparison = payloads.get("compare_scoped_protocols")
            excerpt = payloads.get("read_scoped_protocol_excerpt")
            if self.tool_order == "excerpt_then_compare" and excerpt is None:
                return self._tool("read_scoped_protocol_excerpt", {
                    "document_id": new["document_id"], "version": new["version"],
                    "query": "attempt_count",
                })
            if comparison is None:
                return self._tool("compare_scoped_protocols", {
                    "base_document_id": old["document_id"],
                    "target_document_id": new["document_id"],
                    "base_version": old["version"],
                    "target_version": new["version"],
                })
            if excerpt is None:
                return self._tool("read_scoped_protocol_excerpt", {
                    "document_id": new["document_id"], "version": new["version"],
                    "query": "attempt_count",
                })
            return self._answer(payloads)

    return E03ProtocolFixtureModel(tool_order=tool_order)


def run_e03_fixture(
    runtime_name: str,
    *,
    api_origin: str = DEFAULT_API_ORIGIN,
    web_origin: str = DEFAULT_WEB_ORIGIN,
    timeout_seconds: float = 60,
    tool_order: str = "compare_then_excerpt",
) -> dict[str, Any]:
    """Run E03 once through the formal Web API using only the local Fixture Model."""
    from fastapi.testclient import TestClient
    from runtime_paths import resolve_user_demo_runtime
    from opspilot.web.app import create_app

    case_id = "E03-D"
    root = ROOT.resolve()
    runtime_dir = resolve_user_demo_runtime(runtime_name, root=root)
    preflight = _case_preflight_cli(argparse.Namespace(case_id=case_id, runtime_name=runtime_name), root=root)
    registry_path = runtime_dir / "assistant-access.json"
    password = _local_support_password()
    if not password:
        raise EvaluationPreflightError("SUPPORT_PASSWORD_NOT_CONFIGURED_LOCALLY")
    api_origin = _loopback_url(api_origin, label="API_ORIGIN")
    web_origin = _loopback_url(web_origin, label="WEB_ORIGIN")
    model = make_e03_fixture_model(tool_order=tool_order)
    app = create_app(
        db_path=runtime_dir / "domain.sqlite3",
        checkpoint_db_path=runtime_dir / "checkpoint.sqlite3",
        start_worker=True,
        credentials={"support-a": password},
        expected_origin=web_origin,
        assistant_model_factory=lambda: model,
        assistant_runtime_enabled=False,
        assistant_knowledge_registry_path=registry_path,
    )
    with TestClient(app, base_url=api_origin, raise_server_exceptions=False) as client:
        result = execute_case(
            client, case_id=case_id, runtime_name=runtime_name,
            support_password=password, api_origin=api_origin, web_origin=web_origin,
            root=root, execution_mode="FIXTURE", timeout_seconds=timeout_seconds,
        )
    return {"preflight": preflight, "result": result}


def make_e04_fixture_model(*, decision_path: str = "compare_available"):
    """Offline lookup fixture; its output proves wiring, not semantic model quality."""
    from langchain_core.language_models import BaseChatModel
    from langchain_core.messages import AIMessage, ToolMessage
    from langchain_core.outputs import ChatGeneration, ChatResult
    from pydantic import Field

    if decision_path not in {"compare_available", "request_missing_materials"}:
        raise ValueError("E04_FIXTURE_DECISION_PATH_INVALID")

    class E04AbsenceFixtureModel(BaseChatModel):
        decision_path: str = "compare_available"
        dispatch_count: int = 0
        offered_tool_names: list[str] = Field(default_factory=list)
        decisions: list[dict[str, Any]] = Field(default_factory=list)
        seen: list[list[Any]] = Field(default_factory=list)

        @property
        def _llm_type(self) -> str:
            return "R2_AR06_E04_ABSENCE_FIXTURE"

        def bind_tools(self, tools, **kwargs):
            self.offered_tool_names = [tool.name for tool in tools]
            return self

        @staticmethod
        def _payload(message):
            value = message.content
            if isinstance(value, str):
                try:
                    value = json.loads(value)
                except json.JSONDecodeError:
                    return {}
            while isinstance(value, dict) and set(value) == {"result"}:
                value = value["result"]
            return value if isinstance(value, dict) else {}

        @classmethod
        def _tool_results(cls, messages):
            names_by_id = {
                str(call.get("id")): str(call.get("name"))
                for message in messages
                for call in (getattr(message, "tool_calls", None) or [])
            }
            results = {}
            for message in messages:
                if isinstance(message, ToolMessage):
                    name = getattr(message, "name", None) or names_by_id.get(str(message.tool_call_id))
                    if name:
                        results[str(name)] = cls._payload(message)
            return results

        def _tool(self, name: str, args: dict[str, Any]) -> ChatResult:
            if name not in self.offered_tool_names:
                raise AssertionError("E04 Fixture selected a tool not offered by the Assistant MCP server.")
            self.decisions.append({"action": "CALL", "tool": name, "args": args})
            message = AIMessage(content="", tool_calls=[{
                "name": name, "args": args, "id": f"e04-fixture-{len(self.decisions)}",
            }])
            message.usage_metadata = {"input_tokens": 22, "output_tokens": 8, "total_tokens": 30}
            return ChatResult(generations=[ChatGeneration(message=message)])

        def _answer(self, discovery: dict[str, Any], comparison: dict[str, Any] | None = None,
                    excerpt_result: dict[str, Any] | None = None) -> ChatResult:
            documents = discovery.get("protocol_documents", [])
            by_id = {row.get("document_id"): row for row in documents if isinstance(row, dict)}
            if discovery.get("project_id") != "orders-e04-absence":
                raise AssertionError("Fixture received an unexpected project scope.")
            if set(by_id) != {"callback-retry-contract", "callback-retry-contract-v2"}:
                raise AssertionError("Fixture did not receive exactly the authorized v1/v2 documents.")
            if any("1.4" in str(row.get("version", "")) for row in documents):
                raise AssertionError("The isolated document list unexpectedly contains v1.4.")
            old = by_id["callback-retry-contract"]
            new = by_id["callback-retry-contract-v2"]
            if old.get("version") != "1.0.0" or new.get("version") != "2.0.0":
                raise AssertionError("Unexpected protocol versions in scoped tool result.")
            sections = [
                "在本次授权项目 orders-e04-absence 返回的目录中，可见 callback-retry-contract v1.0.0 和 "
                "callback-retry-contract-v2 v2.0.0；未列出 v1.4。这只说明本次授权目录，不能证明其他环境或线上不存在 v1.4。",
                "你提到的两份迁移说明没有随本轮提供可核验原文或来源，因此我还不能确认它们的内容或相互冲突。",
            ]
            if comparison is not None:
                if comparison.get("success") is not True or comparison.get("identical") is True:
                    raise AssertionError("The available v1/v2 comparison did not return a supported difference.")
                base = comparison.get("base_ref", {})
                target = comparison.get("target_ref", {})
                if (base.get("document_id"), target.get("document_id")) != (
                    "callback-retry-contract", "callback-retry-contract-v2",
                ):
                    raise AssertionError("Comparison references are not the authorized v1/v2 pair.")
                sections.append(
                    "对实际读取到的 v1/v2 协议比较结果显示：v1 将 503 与 TEMPORARY_UNAVAILABLE 视为可重试；"
                    "v2 还要求服务端记录可重试 failure code 和当前 retry policy，并以匹配当前 delivery row 的响应摘要、"
                    "event、request 及 attempt_count/max_attempts 作为 EXHAUSTED 判定条件。"
                    f"比较工具摘要：{comparison.get('summary')}。"
                )
            if excerpt_result is not None:
                refs = excerpt_result.get("source_refs", [])
                excerpts = excerpt_result.get("excerpts", [])
                if (excerpt_result.get("success") is not True or not refs or not excerpts
                        or refs[0].get("document_id") != "callback-retry-contract-v2"
                        or refs[0].get("digest") != new.get("digest")):
                    raise AssertionError("Excerpt does not match the authorized current v2 source.")
                sections.append(
                    f"原文摘录来自 {refs[0]['document_id']} v{refs[0]['version']}，"
                    f"{refs[0]['source']}，行 {refs[0]['line_start']}-{refs[0]['line_end']}："
                    f"“{excerpts[0].get('text', '')}”"
                )
            sections.append(
                "当前材料不足以判断实际部署版本、项目配置或线上 retry 行为。请补充所称两份迁移说明的原文/版本/来源，"
                "以及可核对的发布记录；在此之前不把用户陈述当作已验证文档或业务观察。"
            )
            self.decisions.append({"action": "ANSWER"})
            message = AIMessage(content="\n\n".join(sections))
            message.usage_metadata = {"input_tokens": 52, "output_tokens": 57, "total_tokens": 109}
            return ChatResult(generations=[ChatGeneration(message=message)])

        def _generate(self, messages, stop=None, run_manager=None, **kwargs):
            self.dispatch_count += 1
            self.seen.append(list(messages))
            payloads = self._tool_results(messages)
            discovery = payloads.get("list_scoped_protocol_documents")
            if discovery is None:
                return self._tool("list_scoped_protocol_documents", {"topic": "callback retry"})
            if self.decision_path == "request_missing_materials":
                return self._answer(discovery)
            documents = discovery.get("protocol_documents", [])
            old = next((row for row in documents if row.get("document_id") == "callback-retry-contract"), None)
            new = next((row for row in documents if row.get("document_id") == "callback-retry-contract-v2"), None)
            if old is None or new is None:
                raise AssertionError("Authorized v1/v2 documents were not returned by the current scope.")
            comparison = payloads.get("compare_scoped_protocols")
            if comparison is None:
                return self._tool("compare_scoped_protocols", {
                    "base_document_id": old["document_id"], "target_document_id": new["document_id"],
                    "base_version": old["version"], "target_version": new["version"],
                })
            excerpt_result = payloads.get("read_scoped_protocol_excerpt")
            if excerpt_result is None:
                return self._tool("read_scoped_protocol_excerpt", {
                    "document_id": new["document_id"], "version": new["version"],
                    "query": "retry policy attempt_count max_attempts",
                })
            return self._answer(discovery, comparison, excerpt_result)

    return E04AbsenceFixtureModel(decision_path=decision_path)


def run_e04_fixture(
    runtime_name: str,
    *,
    api_origin: str = DEFAULT_API_ORIGIN,
    web_origin: str = DEFAULT_WEB_ORIGIN,
    timeout_seconds: float = 60,
    decision_path: str = "compare_available",
) -> dict[str, Any]:
    """Run E04-H once via the formal Web API using only a local Fixture Model."""
    from fastapi.testclient import TestClient
    from runtime_paths import resolve_user_demo_runtime
    from opspilot.web.app import create_app

    case_id = "E04-H"
    root = ROOT.resolve()
    runtime_dir = resolve_user_demo_runtime(runtime_name, root=root)
    preflight = _case_preflight_cli(argparse.Namespace(case_id=case_id, runtime_name=runtime_name), root=root)
    password = _local_support_password()
    if not password:
        raise EvaluationPreflightError("SUPPORT_PASSWORD_NOT_CONFIGURED_LOCALLY")
    api_origin = _loopback_url(api_origin, label="API_ORIGIN")
    web_origin = _loopback_url(web_origin, label="WEB_ORIGIN")
    model = make_e04_fixture_model(decision_path=decision_path)
    app = create_app(
        db_path=runtime_dir / "domain.sqlite3",
        checkpoint_db_path=runtime_dir / "checkpoint.sqlite3",
        start_worker=True,
        credentials={"support-a": password},
        expected_origin=web_origin,
        assistant_model_factory=lambda: model,
        assistant_runtime_enabled=False,
        assistant_knowledge_registry_path=runtime_dir / "assistant-access.json",
    )
    with TestClient(app, base_url=api_origin, raise_server_exceptions=False) as client:
        result = execute_case(
            client, case_id=case_id, runtime_name=runtime_name,
            support_password=password, api_origin=api_origin, web_origin=web_origin,
            root=root, execution_mode="FIXTURE", timeout_seconds=timeout_seconds,
        )
    return {"preflight": preflight, "result": result, "fixture_decisions": model.decisions}


def _case_preflight_cli(args: argparse.Namespace, *, root: str | Path | None = None) -> dict[str, Any]:
    state = inspect_case_runtime(args.case_id, args.runtime_name, root=root)
    if not state["fresh"]:
        raise EvaluationPreflightError("CASE_RUNTIME_ALREADY_CONTAINS_SESSION_OR_RUN_DATA")
    if state["runtime_grant_present"]:
        raise EvaluationPreflightError("OFFLINE_PREFLIGHT_REQUIRES_NO_RUNTIME_GRANT")
    if state["provider_send_grants"] or state["unknown_requests"]:
        raise EvaluationPreflightError("CASE_RUNTIME_ALREADY_HAS_PROVIDER_ACTIVITY")
    mismatch = _s3_fixture_mismatch(args.case_id, state)
    if mismatch:
        raise EvaluationPreflightError(mismatch)
    if args.case_id in {"E03-D", "E04-H"} and not state.get("assistant_knowledge_registry", {}).get("valid"):
        raise EvaluationPreflightError(f"{args.case_id.replace('-', '_')}_ISOLATED_KNOWLEDGE_REGISTRY_INVALID")
    result = {
        "status": "OFFLINE_READY",
        "case_id": args.case_id,
        "runtime_name": args.runtime_name,
        "fresh": state["fresh"],
        "runtime_grant_present": state["runtime_grant_present"],
        "provider_requests": 0,
        "unknown_requests": 0,
        "event_id": state.get("delivery_event_id"),
        "delivery_status": state.get("delivery_status"),
        "receiver_status": state.get("receiver_status"),
        "assistant_knowledge_registry": state.get("assistant_knowledge_registry"),
    }
    fixture_summary = _s3_fixture_summary(args.case_id, state)
    if fixture_summary is not None:
        result["s3_fixture"] = fixture_summary
    if args.case_id in EXPLORATORY_CASE_SOURCES:
        result["experiment_class"] = "EXPLORATORY_COUNTERFACTUAL_NOT_FROZEN_CASE"
        result["source_question_case_id"] = EXPLORATORY_CASE_SOURCES[args.case_id]
    if args.case_id == "E04-H":
        result["fixture_specification_status"] = "POST_FREEZE_FIXTURE_SPECIFIED"
        result["fixture_manifest_sha256"] = state["assistant_knowledge_registry"].get("fixture_manifest_sha256")
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    prepare = sub.add_parser("prepare", help="Create a new named isolated runtime; never reuses one.")
    prepare.add_argument("--case-id", required=True, choices=sorted(SUPPORTED_CASES))
    prepare.add_argument("--runtime-name", required=True)

    preflight = sub.add_parser("preflight", help="Offline or explicit Live readiness checks; sends no chat message.")
    preflight.add_argument("--case-id", required=True, choices=sorted(SUPPORTED_CASES))
    preflight.add_argument("--runtime-name", required=True)
    preflight.add_argument("--mode", choices=("offline", "live"), default="offline")
    preflight.add_argument("--authorized-max-cost-usd")
    preflight.add_argument("--api-origin", default=DEFAULT_API_ORIGIN)

    live = sub.add_parser("run-live", help="Submit exactly one frozen turn; no automatic replay or retry.")
    live.add_argument("--case-id", required=True, choices=sorted(SUPPORTED_CASES))
    live.add_argument("--runtime-name", required=True)
    live.add_argument("--authorized-case-id", required=True)
    live.add_argument("--authorized-max-cost-usd", required=True)
    live.add_argument("--api-origin", default=DEFAULT_API_ORIGIN)
    live.add_argument("--web-origin", default=DEFAULT_WEB_ORIGIN)
    live.add_argument("--timeout-seconds", type=float, default=DEFAULT_RUN_TIMEOUT_SECONDS)

    fixture = sub.add_parser("run-fixture", help="Run an offline case through the formal API with a local Fixture Model; no Provider call.")
    fixture.add_argument("--case-id", required=True, choices=("E03-D", "E04-H"))
    fixture.add_argument("--runtime-name", required=True)
    fixture.add_argument("--api-origin", default=DEFAULT_API_ORIGIN)
    fixture.add_argument("--web-origin", default=DEFAULT_WEB_ORIGIN)
    fixture.add_argument("--timeout-seconds", type=float, default=60)
    fixture.add_argument("--tool-order", choices=("compare_then_excerpt", "excerpt_then_compare"), default="compare_then_excerpt")
    fixture.add_argument("--decision-path", choices=("compare_available", "request_missing_materials"), default="compare_available")
    args = parser.parse_args(argv)

    try:
        load_frozen_case(args.case_id)
        if args.command == "prepare":
            runtime_dir = initialize_case_runtime(args.case_id, args.runtime_name)
            state = inspect_case_runtime(args.case_id, args.runtime_name)
            result = {
                "status": "ISOLATED_RUNTIME_CREATED",
                "case_id": args.case_id,
                "runtime_name": args.runtime_name,
                "runtime_dir": str(runtime_dir),
                "fresh": state["fresh"],
                "runtime_grant_present": state["runtime_grant_present"],
                "provider_requests": 0,
            }
            if args.case_id in EXPLORATORY_CASE_SOURCES:
                result["experiment_class"] = "EXPLORATORY_COUNTERFACTUAL_NOT_FROZEN_CASE"
                result["source_question_case_id"] = EXPLORATORY_CASE_SOURCES[args.case_id]
            print(json.dumps(result, ensure_ascii=False))
            return 0
        if args.command == "preflight" and args.mode == "offline":
            print(json.dumps(_case_preflight_cli(args), ensure_ascii=False))
            return 0
        if args.command == "preflight":
            if not args.authorized_max_cost_usd:
                raise EvaluationPreflightError("LIVE_PREFLIGHT_REQUIRES_CASE_COST_AUTHORIZATION")
            import httpx

            with httpx.Client(timeout=5.0, follow_redirects=False) as client:
                result = live_preflight(
                    args.case_id, args.runtime_name,
                    authorized_max_cost_usd=args.authorized_max_cost_usd,
                    api_origin=args.api_origin, client=client,
                )
            print(json.dumps(result, ensure_ascii=False))
            return 0

        if args.command == "run-fixture":
            if args.case_id == "E03-D":
                result = run_e03_fixture(
                    args.runtime_name,
                    api_origin=args.api_origin,
                    web_origin=args.web_origin,
                    timeout_seconds=args.timeout_seconds,
                    tool_order=args.tool_order,
                )
            else:
                result = run_e04_fixture(
                    args.runtime_name,
                    api_origin=args.api_origin,
                    web_origin=args.web_origin,
                    timeout_seconds=args.timeout_seconds,
                    decision_path=args.decision_path,
                )
            print(json.dumps(result, ensure_ascii=False))
            return 0 if not result["result"]["terminal_timeout"] else 3

        if args.authorized_case_id != args.case_id:
            raise EvaluationPreflightError("LIVE_AUTHORIZATION_CASE_MISMATCH")
        import httpx

        password = _local_support_password()
        if not password:
            raise EvaluationPreflightError("SUPPORT_PASSWORD_NOT_CONFIGURED_LOCALLY")
        api_origin = _loopback_url(args.api_origin, label="API_ORIGIN")
        web_origin = _loopback_url(args.web_origin, label="WEB_ORIGIN")
        with httpx.Client(base_url=api_origin, timeout=15.0, follow_redirects=False) as client:
            preflight_result = live_preflight(
                args.case_id, args.runtime_name,
                authorized_max_cost_usd=args.authorized_max_cost_usd,
                api_origin=api_origin, root=ROOT, client=client,
            )
            result = execute_case(
                client, case_id=args.case_id, runtime_name=args.runtime_name,
                support_password=password, api_origin=api_origin, web_origin=web_origin,
                root=ROOT, execution_mode="LIVE", timeout_seconds=args.timeout_seconds,
            )
        print(json.dumps({"preflight": preflight_result, "result": result}, ensure_ascii=False))
        return 0 if not result["terminal_timeout"] else 3
    except EvaluationPreflightError as error:
        code = str(error)
        if not code or len(code) > 160:
            code = type(error).__name__
        print(json.dumps({"status": "STOPPED", "reason": code}, ensure_ascii=False), file=sys.stderr)
        return 2
    except (RuntimeError, ValueError, OSError) as error:
        code = getattr(error, "code", None) or type(error).__name__
        print(json.dumps({"status": "STOPPED", "reason": str(code)[:160]}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
