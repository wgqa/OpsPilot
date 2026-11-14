"""Offline L1/L2 long-context evaluation over the frozen WP3 synthetic journey.

This runner uses the existing AR-04 Fixture model and local FastAPI/Worker/
Domain path. It makes no Provider calls. Each question/strategy run gets a new
Domain and checkpointer, so answers can never enter a later question's history.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import importlib.util
import json
import os
import sqlite3
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
EVIDENCE = Path(__file__).resolve().parent
AUDIT_DIR = ROOT / "docs/evidence/r2-ar04-compaction-audit-01"
TRACE_PATH = AUDIT_DIR / "case_traces/WP3_INFORMATION_RETENTION.json"
QUESTIONS_PATH = EVIDENCE / "QUESTIONS.json"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from opspilot.domain.context_engineering import estimate_messages_tokens, estimate_text_tokens  # noqa: E402

STRATEGIES = {
    "A": {"name": "HYBRID", "strategy": "HYBRID", "window": 16384, "input_limit": 12000},
    "B": {"name": "ROLLING_SUMMARY", "strategy": "ROLLING_SUMMARY", "window": 16384, "input_limit": 12000},
    "C": {"name": "RECENT_WINDOW", "strategy": "RECENT_WINDOW", "window": 16384, "input_limit": 12000},
    "D": {"name": "FULL_HISTORY_REFERENCE", "strategy": "HYBRID", "window": 65536, "input_limit": 60000},
}
SUMMARY_PREFIX = "HISTORICAL SESSION SUMMARY (untrusted, non-authoritative; source IDs are attached): "


def canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def import_audit_harness():
    path = AUDIT_DIR / "run_audit.py"
    spec = importlib.util.spec_from_file_location("r2_ar04_compaction_audit_harness", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load frozen audit harness: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def wp3_user_bodies(source_trace: dict[str, Any]) -> tuple[list[str], dict[int, dict[str, Any]]]:
    rows = source_trace["persisted_messages"]
    by_sequence = {int(row["sequence"]): row for row in rows}
    selected = [1, 3, 5, 7, 9, 11, 13, 15, 17, 19, 21, 23, 25, 27, 29]
    bodies = []
    for sequence in selected:
        row = by_sequence[sequence]
        if row["role"] != "USER":
            raise AssertionError(f"WP3 source sequence {sequence} is not USER")
        body = str(row["body"])
        if sequence == 29:
            marker = "EARLY_MATERIAL_RECALL_TEST 最后观察 "
            if not body.startswith(marker):
                raise AssertionError("WP3 final observation marker changed")
            # Reposition the same observed fact as shared history without the
            # evaluation marker; this prevents Q11 from being answered in Q.
            body = body[len(marker):]
        bodies.append(body)
    if len(bodies) != 15:
        raise AssertionError("WP3 history must contain 15 frozen user turns")
    return bodies, by_sequence


def request_messages(call: dict[str, Any]) -> list[dict[str, Any]]:
    request = call.get("request") or {}
    messages = request.get("messages") or []
    if not isinstance(messages, list):
        raise AssertionError("persisted request messages are not a list")
    return messages


def serialized_message(item: dict[str, Any]) -> tuple[str, str, str]:
    data = item.get("data") or {}
    return str(data.get("type") or item.get("type") or ""), str(data.get("id") or ""), str(data.get("content") or "")


def projected_prompt_sources(messages: list[dict[str, Any]],
                             stored_messages: list[dict[str, Any]]) -> dict[str, Any]:
    stored_by_id = {str(row["message_id"]): row for row in stored_messages}
    raw: list[dict[str, Any]] = []
    summaries: list[dict[str, Any]] = []
    other_text: list[str] = []
    for item in messages:
        role, item_id, content = serialized_message(item)
        if item_id.startswith("opspilot-history:"):
            message_id = item_id.split(":", 1)[1]
            row = stored_by_id.get(message_id)
            if row is None:
                raise AssertionError(f"selected history source missing from Domain rows: {message_id}")
            raw.append({
                "message_id": message_id,
                "sequence": int(row["sequence"]),
                "role": str(row["role"]),
                "body": content,
                "body_digest": str(row["body_digest"]),
            })
        elif item_id.startswith("opspilot-summary:"):
            if not content.startswith(SUMMARY_PREFIX):
                raise AssertionError("summary message has an unknown projection envelope")
            projected = json.loads(content[len(SUMMARY_PREFIX):])
            summaries.append({"summary_id": item_id.split(":", 1)[1], "document": projected})
        elif role == "system":
            other_text.append(content)
    return {"raw": raw, "summaries": summaries, "other_text": other_text}


def summary_entries(document: dict[str, Any], path: str | None = None,
                    path_prefix: str | None = None) -> list[dict[str, Any]]:
    values: list[dict[str, Any]] = []
    if path:
        current: Any = document
        for part in path.split("."):
            current = current.get(part) if isinstance(current, dict) else None
        if isinstance(current, str):
            values.append({"text": current, "source_message_ids": []})
        elif isinstance(current, dict):
            values.append(current)
        elif isinstance(current, list):
            values.extend(item for item in current if isinstance(item, dict))
    elif path_prefix:
        current = document.get(path_prefix)
        if isinstance(current, list):
            values.extend(item for item in current if isinstance(item, dict))
        elif isinstance(current, dict):
            values.append(current)
    return values


def clause_matches_raw(clause: dict[str, Any], raw: list[dict[str, Any]]) -> bool:
    allowed_sequences = {int(value) for value in clause.get("sequences", [])}
    needles = [str(value) for value in clause.get("all_needles", [])]
    for row in raw:
        if allowed_sequences and row["sequence"] not in allowed_sequences:
            continue
        if all(needle in row["body"] for needle in needles):
            return True
    return False


def clause_matches_summary(clause: dict[str, Any], summaries: list[dict[str, Any]]) -> bool:
    needles = [str(value) for value in clause.get("all_needles", [])]
    for summary in summaries:
        document = summary["document"]
        for entry in summary_entries(document, clause.get("path"), clause.get("path_prefix")):
            text = str(entry.get("text", ""))
            if all(needle in text for needle in needles):
                return True
    return False


def score_question(question: dict[str, Any], projected: dict[str, Any],
                   run_status: str) -> dict[str, Any]:
    if run_status != "SUCCEEDED":
        return {
            "status": "BLOCKED", "available_sources": [], "satisfied_fact_groups": [],
            "missing_fact_groups": [item["id"] for item in question["required_fact_groups"]],
            "policy_requirements_visible": False,
        }
    raw = projected["raw"]
    summaries = projected["summaries"]
    satisfied: list[str] = []
    missing: list[str] = []
    raw_satisfied: list[str] = []
    summary_satisfied: list[str] = []
    partial: list[str] = []
    for group in question["required_fact_groups"]:
        raw_ok = any(clause_matches_raw(clause, raw) for clause in group.get("raw_any", []))
        summary_ok = any(clause_matches_summary(clause, summaries) for clause in group.get("summary_any", []))
        if raw_ok or summary_ok:
            satisfied.append(group["id"])
            if raw_ok:
                raw_satisfied.append(group["id"])
            if summary_ok:
                summary_satisfied.append(group["id"])
        else:
            missing.append(group["id"])
            partial_texts: list[str] = []
            # Any selected source text may provide a clue, but only the
            # source-restricted clauses above can establish full availability.
            # This distinguishes an incomplete tool-result hint (PARTIAL) from
            # a complete, source-valid formal correction (AVAILABLE_*).
            partial_texts.extend(row["body"] for row in raw)
            for clause in group.get("summary_any", []):
                for summary in summaries:
                    partial_texts.extend(
                        str(entry.get("text", ""))
                        for entry in summary_entries(
                            summary["document"], clause.get("path"), clause.get("path_prefix"),
                        )
                    )
            possible = any(
                len(needle) > 2 and needle in text
                for text in partial_texts
                for clause in group.get("raw_any", []) + group.get("summary_any", [])
                for needle in clause.get("all_needles", [])
            )
            if possible:
                partial.append(group["id"])
    all_system = "\n".join(projected["other_text"])
    prompt_text = all_system + "\n" + "\n".join(row["body"] for row in raw)
    prompt_text += "\n" + "\n".join(json.dumps(item["document"], ensure_ascii=False) for item in summaries)
    policy_checks = {
        "read_only_or_trusted_receipt": any(term in prompt_text.lower() for term in ("只读", "read-only"))
            and any(term in prompt_text for term in ("可信", "回执", "receipt", "核验")),
        "no_business_write": any(term in prompt_text for term in ("禁止任何业务写入", "禁止业务写入", "不得业务写入")),
        "no_false_completion": any(term in prompt_text for term in ("不要把 HTTP 202 当成完成", "not proof of completion", "不证明下游处理完成")),
    }
    policy_ok = all(policy_checks.values()) if question.get("policy_requirements") else True
    sources = []
    if raw_satisfied:
        sources.append("RAW")
    if summary_satisfied:
        sources.append("SUMMARY")
    all_facts = not missing and policy_ok
    contradicted = False
    if question["id"] == "Q03":
        all_fact_text = "\n".join(row["body"] for row in raw) + "\n" + "\n".join(
            json.dumps(item["document"], ensure_ascii=False) for item in summaries
        )
        has_old_and_new = "req-482" in all_fact_text and "req-483" in all_fact_text
        has_formal_correction = "正式更正" in all_fact_text and "录入错误" in all_fact_text
        contradicted = has_old_and_new and not has_formal_correction
    if contradicted:
        status = "CONTRADICTED"
    elif not satisfied and not partial:
        status = "MISSING"
    elif all_facts and raw_satisfied and not summary_satisfied:
        status = "AVAILABLE_RAW"
    elif all_facts and summary_satisfied and not raw_satisfied:
        status = "AVAILABLE_SUMMARY"
    elif all_facts:
        status = "AVAILABLE_RAW"  # both contribute; counted once, recorded below.
    else:
        status = "PARTIAL"
    return {
        "status": status,
        "available_sources": sources,
        "satisfied_fact_groups": satisfied,
        "missing_fact_groups": missing,
        "partially_visible_fact_groups": partial,
        "policy_requirements_visible": policy_checks,
        "policy_requirements_satisfied": policy_ok,
        "contributed_by_raw": raw_satisfied,
        "contributed_by_summary": summary_satisfied,
    }


def score_l1_domain_history(question: dict[str, Any], rows: list[dict[str, Any]]) -> dict[str, Any]:
    raw = [{"sequence": int(row["sequence"]), "body": str(row["body"])} for row in rows]
    group_results = []
    missing = []
    for group in question.get("required_fact_groups", []):
        present = any(clause_matches_raw(clause, raw) for clause in group.get("raw_any", []))
        if not present:
            missing.append(group["id"])
        group_results.append({"id": group["id"], "present_in_domain_history": present})
    sequences = {int(row["sequence"]): str(row["body"]) for row in rows}
    requested = [int(value) for value in question.get("source_sequences", [])]
    missing_sequences = [value for value in requested if value not in sequences]
    constraint_text = sequences.get(5, "")
    return {
        "status": "COMPLETE" if not missing and not missing_sequences else "INCOMPLETE",
        "retained_fact_group_count": len(group_results) - len(missing),
        "required_fact_group_count": len(group_results),
        "fact_groups": group_results,
        "missing_fact_groups": missing,
        "required_source_sequences": requested,
        "missing_source_sequences": missing_sequences,
        "explicit_no_credential_change_and_no_business_write_source_present": (
            "禁止改凭证" in constraint_text and "禁止任何业务写入" in constraint_text
        ),
        "evidence_level": "FIXTURE_OFFLINE_ACTUAL_DOMAIN_ROWS_AND_BODY_DIGESTS",
    }


def source_citation_audit(result: dict[str, Any], projected: dict[str, Any]) -> dict[str, Any]:
    stored_by_id = {str(row["message_id"]): row for row in result["messages"]}
    cited_ids: set[str] = set()
    for summary in projected["summaries"]:
        document = summary["document"]
        nodes: list[Any] = [document.get("initial_goal", {})]
        for key in ("constraints", "user_assertions", "corrections", "rejected_hypotheses", "unresolved_items", "timeline"):
            nodes.extend(document.get(key, []) if isinstance(document.get(key), list) else [])
        for node in nodes:
            if not isinstance(node, dict):
                continue
            cited_ids.update(str(value) for value in node.get("source_message_ids", []))
    missing_ids = sorted(value for value in cited_ids if value not in stored_by_id)
    current_summary_ids = {str(row["summary_id"]) for row in result.get("summaries", [])
                           if str(row.get("state", "")).upper() in {"CURRENT", "ACTIVE", "VALID"}}
    projected_ids = {item["summary_id"] for item in projected["summaries"]}
    return {
        "cited_source_id_count": len(cited_ids),
        "cited_source_ids": sorted(cited_ids),
        "missing_source_ids": missing_ids,
        "all_cited_sources_exist_in_current_domain_history": not missing_ids,
        "projected_summary_ids": sorted(projected_ids),
        "domain_current_summary_ids": sorted(current_summary_ids),
        "all_projected_summaries_are_current": projected_ids.issubset(current_summary_ids),
    }


def context_summary(result: dict[str, Any], projected: dict[str, Any],
                    question: dict[str, Any], group_id: str, group: dict[str, Any],
                    request: dict[str, Any], citation_audit: dict[str, Any]) -> dict[str, Any]:
    wire_budget = request.get("context_budget", {})
    manifest = result.get("manifest", {}).get("body", {})
    prep_calls = result.get("instrumentation", {}).get("prep_calls", [])
    prep = prep_calls[0] if prep_calls else {}
    attempts = result.get("compression_attempts", [])
    model_calls = result.get("model_calls", [])
    compression_calls = [call for call in model_calls if str(call.get("logical_key", "")).startswith("context-compression:")]
    summary_docs = projected["summaries"]
    raw_sequences = sorted({int(row["sequence"]) for row in projected["raw"]})
    source_by_id = {str(row["message_id"]): int(row["sequence"]) for row in result["messages"]}
    excluded = []
    for entry in request.get("excluded_sources", []):
        source_id = str(entry.get("source_id", ""))
        excluded.append({**entry, "sequence": source_by_id.get(source_id)})
    full_history = [{"role": str(row["role"]).lower(), "content": str(row["body"])}
                    for row in result["messages"] if int(row["sequence"]) <= 29]
    raw_estimate = estimate_messages_tokens(full_history)
    final_estimate = wire_budget.get("estimated_input_tokens")
    summary_output_estimates = [
        estimate_text_tokens(canonical(item["document"])) for item in summary_docs
    ]
    latest_summary_rows = [row for row in result.get("summaries", [])
                           if str(row.get("summary_id")) in {item["summary_id"] for item in summary_docs}]
    summary_json_estimates = [estimate_text_tokens(str(row.get("summary_json", ""))) for row in latest_summary_rows]
    status = str(result.get("run", {}).get("status", "UNKNOWN"))
    evaluation = score_question(question, projected, status)
    critical_gaps = []
    if question["id"] == "Q03" and evaluation["status"] not in {"AVAILABLE_RAW", "AVAILABLE_SUMMARY"}:
        critical_gaps.append("formal_request_id_correction_not_fully_visible")
    if question["id"] == "Q08" and evaluation["status"] not in {"AVAILABLE_RAW", "AVAILABLE_SUMMARY"}:
        critical_gaps.append("deployment_version_unknown_not_visible")
    if question["id"] == "Q09" and evaluation["status"] not in {"AVAILABLE_RAW", "AVAILABLE_SUMMARY"}:
        critical_gaps.append("no_business_write_constraint_not_visible")
    if question["id"] == "Q10" and evaluation["status"] not in {"AVAILABLE_RAW", "AVAILABLE_SUMMARY"}:
        critical_gaps.append("http_202_not_completion_fact_not_visible")
    if not citation_audit["all_cited_sources_exist_in_current_domain_history"] or not citation_audit["all_projected_summaries_are_current"]:
        critical_gaps.append("summary_source_invalid_or_non_current")
    return {
        "question_id": question["id"],
        "group": group_id,
        "strategy": group["strategy"],
        "configured_input_limit_tokens": group["input_limit"],
        "window_tokens": wire_budget.get("context_window_tokens"),
        "input_budget_tokens": wire_budget.get("input_budget_tokens"),
        "reserved_tokens": prep.get("reserved_tokens", wire_budget.get("reserved_tokens")),
        "effective_input_budget_after_reserve": max(
            0,
            int(wire_budget.get("input_budget_tokens", 0))
            - int(prep.get("reserved_tokens", wire_budget.get("reserved_tokens", 0)) or 0),
        ),
        "estimated_before_tokens": prep.get("estimated_before"),
        "estimated_before_kind": prep.get("estimated_before_kind"),
        "original_history_token_estimate": raw_estimate,
        "final_prompt_estimated_tokens": final_estimate,
        "retained_raw_sequences": raw_sequences,
        "excluded_sources": excluded,
        "summary_ids": [item["summary_id"] for item in summary_docs],
        "summary_documents": [item["document"] for item in summary_docs],
        "summary_source_audit": citation_audit,
        "summary_output_estimated_tokens_projected": summary_output_estimates,
        "summary_output_estimated_tokens_domain_json": summary_json_estimates,
        "compression_attempts": attempts,
        "compression_call_count": len(compression_calls),
        "compression_attempt_count": len(attempts),
        "compression_success_count": sum(str(item.get("status")).upper() == "SUCCEEDED" for item in attempts),
        "compression_failure_count": sum(str(item.get("status")).upper() not in {"SUCCEEDED", "OK"} for item in attempts),
        "compression_input_estimated_tokens": [item.get("estimated_input_tokens") for item in attempts],
        "status": status,
        "blocked_reason": result.get("run_row", {}).get("blocked_reason"),
        "availability": evaluation,
        "critical_visibility_gaps": critical_gaps,
        "model_critical_error_rate": "NOT_EVALUATED_L3_FIXTURE_ONLY",
        "context_blocks": manifest.get("context_blocks", []),
        "context_budget": wire_budget,
        "provider_requests": 0,
        "evidence_level": "FIXTURE_OFFLINE_ACTUAL_PERSISTED_REQUEST_JSON_AND_DOMAIN_ROWS",
    }


def history_snapshot(first_result: dict[str, Any], source_by_sequence: dict[int, dict[str, Any]],
                     normalized_bodies: list[str]) -> dict[str, Any]:
    rows = [row for row in first_result["messages"] if int(row["sequence"]) <= 29]
    if len(rows) != 29:
        raise AssertionError(f"recreated pre-question WP3 history has {len(rows)} messages, expected 29")
    result_rows = []
    for row in rows:
        sequence = int(row["sequence"])
        source = source_by_sequence[sequence]
        original_digest = str(source["body_digest"])
        expected_same = sequence <= 28
        if expected_same and str(row["body_digest"]) != original_digest:
            raise AssertionError(f"frozen WP3 body digest changed at sequence {sequence}")
        if sequence == 29:
            if str(row["body"]) != normalized_bodies[-1]:
                raise AssertionError("normalized final observation differs from frozen fact body")
        result_rows.append({
            "sequence": sequence,
            "role": row["role"],
            "source_wp3_message_id": source["message_id"],
            "source_wp3_body_digest": original_digest,
            "recreated_body_digest": row["body_digest"],
            "matches_frozen_digest": str(row["body_digest"]) == original_digest,
            "normalization": "removed only EARLY_MATERIAL_RECALL_TEST marker" if sequence == 29 else None,
            "body": row["body"],
        })
    return {
        "source_trace": "../r2-ar04-compaction-audit-01/case_traces/WP3_INFORMATION_RETENTION.json",
        "evidence_level": "FIXTURE_OFFLINE_ACTUAL_DOMAIN_ROWS_AND_BODY_DIGESTS",
        "original_trace_total_rows": 30,
        "pre_question_source_rows": 29,
        "recreated_shared_history_rows": result_rows,
        "asserted_original_digests": "sequences 1-28 match; sequence 29 omits only the evaluation marker",
    }


def sqlite_backup(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(source) as source_db, sqlite3.connect(target) as target_db:
        source_db.backup(target_db)


def prepare_shared_history(harness, seed_bodies: list[str], temp_root: Path,
                           observation_created_at: str | None = None) -> dict[str, Any]:
    """Create the common WP3 pre-question state once through the real local path."""
    from fastapi.testclient import TestClient
    from opspilot.domain.database import connect, reset_fixture
    from opspilot.web.app import create_app

    case_root = temp_root / "shared-history"
    case_root.mkdir(parents=True, exist_ok=True)
    db_path = case_root / "shared-domain.sqlite3"
    checkpoint = case_root / "shared-checkpoint.sqlite3"
    reset_fixture(db_path, "S1_POS")
    os.environ["OPSPILOT_CONTEXT_STRATEGY"] = "HYBRID"
    harness._env_budget(context_window=50000, input_limit=45000)
    fixture_state = {"emit_long_tool_result": True}
    fixture_instances = []

    def model_factory():
        model = harness.AuditFixtureModel(
            mode="s01", emit_long_tool_result=fixture_state["emit_long_tool_result"],
        )
        fixture_instances.append(model)
        return model

    app = create_app(
        db_path=db_path,
        checkpoint_db_path=checkpoint,
        start_worker=True,
        credentials=harness.PASSWORDS,
        expected_origin=harness.ORIGIN,
        assistant_model_factory=model_factory,
    )
    result: dict[str, Any] = {}
    with TestClient(app) as client:
        headers = harness._login(client)
        session_id = client.post("/api/sessions", headers=headers).json()["session_id"]
        seeded = harness._seed_turns(
            client, headers, session_id, count=14, size_tokens=0, seed_bodies=seed_bodies[:14],
        )
        # The frozen WP3 trace ends at a user observation immediately before
        # Q11; it has no assistant reply yet. Stage that final source row in the
        # isolated Domain fixture so no extra answer enters the shared context.
        with connect(db_path) as connection:
            connection.execute("BEGIN IMMEDIATE")
            session = connection.execute(
                "SELECT tenant_id FROM sessions WHERE session_id=?", (session_id,),
            ).fetchone()
            sequence = int(connection.execute(
                "SELECT COALESCE(MAX(sequence),0)+1 FROM messages WHERE session_id=?", (session_id,),
            ).fetchone()[0])
            if session is None or sequence != 29:
                raise AssertionError(f"expected input-only fixture insertion at seq29, got {sequence}")
            fixture_message_id = "message-wp3-latest-observation-normalized"
            connection.execute(
                """INSERT INTO messages
                   (message_id,tenant_id,session_id,task_id,sequence,role,input_kind,body,
                    body_digest,command_id,created_at)
                   VALUES (?, ?, ?, NULL, ?, 'USER', 'CHAT_READONLY', ?, ?, ?, ?)""",
                (fixture_message_id, str(session["tenant_id"]), session_id, sequence,
                 seed_bodies[14], sha256(seed_bodies[14]),
                 "fixture-wp3-latest-observation-normalized",
                 observation_created_at or "2026-11-14T12:00:00+00:00"),
            )
        seeded.append({"source_message_id": fixture_message_id, "sequence": 29,
                       "status": "FIXTURE_USER_ONLY_SOURCE_ROW_NO_ASSISTANT_REPLY"})
        result.update({
            "session_id": session_id,
            "seed_runs": seeded,
            "messages": harness._messages(db_path, session_id),
            "domain_path": str(db_path),
            "checkpoint_path": str(checkpoint),
        })
    if len(result["messages"]) != 29:
        raise AssertionError(f"shared pre-question WP3 history has {len(result['messages'])} rows, expected 29")
    result["history_signature"] = [
        (int(row["sequence"]), str(row["message_id"]), str(row["body_digest"]))
        for row in result["messages"]
    ]
    return result


def run_independent_case(harness, case_id: str, group: dict[str, Any], prompt: str,
                         shared_history: dict[str, Any], temp_root: Path) -> dict[str, Any]:
    """Clone the common Domain/checkpoint state for one independent question."""
    from fastapi.testclient import TestClient
    from opspilot.domain.database import connect
    from opspilot.web.app import create_app

    case_root = temp_root / case_id
    case_root.mkdir(parents=True, exist_ok=True)
    db_path = case_root / "isolated-domain.sqlite3"
    checkpoint = case_root / "isolated-checkpoint.sqlite3"
    sqlite_backup(Path(shared_history["domain_path"]), db_path)
    sqlite_backup(Path(shared_history["checkpoint_path"]), checkpoint)
    os.environ["OPSPILOT_CONTEXT_STRATEGY"] = group["strategy"]
    harness._env_budget(context_window=group["window"], input_limit=group["input_limit"])
    fixture_instances = []

    def model_factory():
        model = harness.AuditFixtureModel(mode="s01", emit_long_tool_result=False)
        fixture_instances.append(model)
        return model

    app = create_app(
        db_path=db_path,
        checkpoint_db_path=checkpoint,
        start_worker=True,
        credentials=harness.PASSWORDS,
        expected_origin=harness.ORIGIN,
        assistant_model_factory=model_factory,
    )
    result: dict[str, Any] = {"case_id": case_id, "strategy": group["strategy"]}
    with TestClient(app) as client:
        headers = harness._login(client)
        session_id = str(shared_history["session_id"])
        (instrumentation, chat, assistant, worker, real_prepare, original_client,
         real_estimate, real_worker_error) = harness._patch_case_instrumentation(case_id)
        harness.ACTIVE_AUDIT["target_run_id"] = None
        try:
            item, run = harness._create_run(client, headers, session_id, f"{case_id}-question", prompt)
            target_run_id = str(item["run_id"])
            instrumentation["current_run_id"] = target_run_id
            instrumentation["status"] = run.get("status")
            result.update({
                "run": run,
                "run_id": target_run_id,
                "session_id": session_id,
                "seed_runs": shared_history["seed_runs"],
                "instrumentation": instrumentation,
                "fixture_model_inputs": [entry for model in fixture_instances for entry in model.captured_inputs],
                "case_config": {
                    "context_window_tokens": group["window"],
                    "configured_input_limit_tokens": group["input_limit"],
                    "strategy": group["strategy"],
                },
            })
            result["messages"] = harness._messages(db_path, session_id)
            signature = [
                (int(row["sequence"]), str(row["message_id"]), str(row["body_digest"]))
                for row in result["messages"] if int(row["sequence"]) <= 29
            ]
            if signature != shared_history["history_signature"]:
                raise AssertionError(f"shared pre-question Domain snapshot changed in {case_id}")
            result["model_calls"] = harness._wire_rows(db_path, target_run_id)
            result["compression_attempts"] = harness._attempts(db_path, target_run_id)
            manifest_response = client.get(f"/api/runs/{target_run_id}/context", headers=headers)
            result["manifest"] = {
                "http_status": manifest_response.status_code,
                "body": manifest_response.json() if manifest_response.headers.get("content-type", "").startswith("application/json") else manifest_response.text,
            }
            with connect(db_path) as connection:
                result["summaries"] = [dict(row) for row in connection.execute(
                    "SELECT summary_id,summary_version,state,strategy,summary_json,summary_digest,"
                    "covered_from_seq,covered_to_seq,source_attempt_id FROM context_summaries "
                    "WHERE session_id=? ORDER BY summary_version", (session_id,),
                )]
                result["run_row"] = dict(connection.execute(
                    "SELECT blocked_reason,status FROM task_runs WHERE run_id=?", (target_run_id,),
                ).fetchone())
        finally:
            harness._restore_instrumentation(
                chat, assistant, worker, real_prepare, original_client, real_estimate, real_worker_error,
            )
    return result


def run(args: argparse.Namespace) -> dict[str, Any]:
    source_trace = load_json(TRACE_PATH)
    question_doc = load_json(QUESTIONS_PATH)
    questions = question_doc["questions"][:args.question_limit or None]
    seed_bodies, source_by_sequence = wp3_user_bodies(source_trace)
    source_rows = source_trace["persisted_messages"]
    source_by_id = {str(row["message_id"]): row for row in source_rows}
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    results_path = output_dir / "RESULTS.json"
    if results_path.exists() and not args.overwrite:
        raise FileExistsError(f"refusing to overwrite existing results: {results_path}")
    harness = import_audit_harness()
    from opspilot.assistant import SYSTEM as STATIC_SYSTEM_PROMPT
    static_system_prompt_digest = sha256(STATIC_SYSTEM_PROMPT)
    original_result_dir = harness.RESULT_DIR
    tmp = tempfile.TemporaryDirectory(prefix="r2-ar04-long-context-")
    temp_root = Path(tmp.name)
    trace_temp = temp_root / "harness-traces"
    trace_temp.mkdir()
    harness.RESULT_DIR = trace_temp
    harness.ACTIVE_AUDIT.clear()
    harness.ACTIVE_AUDIT["tmp_root"] = str(temp_root / "isolated-runs")
    Path(harness.ACTIVE_AUDIT["tmp_root"]).mkdir()
    model_requests_path = output_dir / "MODEL_REQUESTS.jsonl.gz"
    run_details_path = output_dir / "RUN_DETAILS.jsonl.gz"
    existing_outputs = [path for path in (model_requests_path, run_details_path,
                                          output_dir / "HISTORY_SNAPSHOT.json") if path.exists()]
    if existing_outputs and not args.overwrite:
        raise FileExistsError(f"refusing to append to prior evidence output: {existing_outputs[0]}")
    request_mode = "wt"
    details_mode = "wt"
    all_run_results: list[dict[str, Any]] = []
    baseline = prepare_shared_history(
        harness, seed_bodies, Path(harness.ACTIVE_AUDIT["tmp_root"]),
        str(source_by_sequence[29].get("created_at") or ""),
    )
    shared_history = history_snapshot(baseline, source_by_sequence, seed_bodies)
    completed = 0
    try:
        with gzip.open(model_requests_path, request_mode, encoding="utf-8", compresslevel=6) as request_file, \
             gzip.open(run_details_path, details_mode, encoding="utf-8", compresslevel=6) as detail_file:
            for question in questions:
                for group_id, group in STRATEGIES.items():
                    case_id = f"{group_id}_{question['id']}"
                    prompt = str(question["prompt_text"])
                    if any(prompt in body for body in seed_bodies):
                        raise AssertionError(f"question leaks into shared history: {question['id']}")
                    result = run_independent_case(
                        harness, case_id, group, prompt, baseline,
                        Path(harness.ACTIVE_AUDIT["tmp_root"]),
                    )
                    answer_calls = [call for call in result["model_calls"]
                                    if not str(call.get("logical_key", "")).startswith("context-compression:")]
                    final_call = answer_calls[-1] if answer_calls else None
                    if final_call is None and str(result.get("run", {}).get("status")) == "SUCCEEDED":
                        raise AssertionError(f"successful run has no persisted answer request: {case_id}")
                    request = final_call["request"] if final_call else {}
                    prompt_messages = request_messages(final_call) if final_call else []
                    if final_call:
                        serialized_request = canonical(request)
                        if canonical(question["gold"]) in serialized_request:
                            raise AssertionError(f"Gold answer leaked into prompt for {case_id}")
                        if canonical(question.get("required_fact_groups", [])) in serialized_request:
                            raise AssertionError(f"scoring rubric leaked into prompt for {case_id}")
                        current_messages = [item for item in prompt_messages
                                            if serialized_message(item)[1].startswith("opspilot-current:")]
                        if len(current_messages) != 1 or serialized_message(current_messages[0])[2] != prompt:
                            raise AssertionError(f"model input did not contain only the fixed question for {case_id}")
                        actual_system = next((serialized_message(item)[2] for item in prompt_messages
                                              if serialized_message(item)[0] == "system"), "")
                        if not actual_system.startswith(STATIC_SYSTEM_PROMPT + "\nWORK_CONTEXT\n"):
                            raise AssertionError(f"static system prompt differs in {case_id}")
                    projected = projected_prompt_sources(prompt_messages, result["messages"])
                    citations = source_citation_audit(result, projected)
                    row = context_summary(result, projected, question, group_id, group, request, citations)
                    row["l1_domain_history"] = score_l1_domain_history(question, baseline["messages"])
                    row["static_system_prompt_sha256"] = static_system_prompt_digest
                    row["tool_schema_sha256"] = sha256(canonical(request.get("tools", [])))
                    row["wire_model_id"] = request.get("model_id")
                    row["fixture_model_configuration"] = {
                        "class": "AuditFixtureModel",
                        "parent": "JourneyFixtureModel",
                        "mode": "s01",
                        "query_emit_long_tool_result": False,
                        "provider": "NONE",
                    }
                    # This maps all source references in the final prompt to the
                    # recreated Domain rows and catches stale or fabricated IDs.
                    if not citations["all_cited_sources_exist_in_current_domain_history"]:
                        raise AssertionError(f"summary citations do not map to current Domain rows: {case_id}")
                    if not citations["all_projected_summaries_are_current"]:
                        raise AssertionError(f"invalidated/non-current summary entered model input: {case_id}")
                    all_run_results.append(row)
                    detail = {
                        "question_id": question["id"], "group": group_id, "case_id": case_id,
                        "run_id": result["run_id"], "session_id": result["session_id"],
                        "fixture_model": "AuditFixtureModel extending JourneyFixtureModel",
                        "local_path": "TestClient + FastAPI + Worker + Domain SQLite + SQLite checkpointer",
                        "manifest": result["manifest"],
                        "context_blocks": result["manifest"].get("body", {}).get("context_blocks", []),
                        "summaries": result["summaries"],
                        "compression_attempts": result["compression_attempts"],
                        "persisted_messages": [
                            {key: msg.get(key) for key in ("message_id", "sequence", "role", "input_kind", "body_digest")}
                            for msg in result["messages"]
                        ],
                        "availability": row["availability"],
                        "status": row["status"],
                    }
                    detail_file.write(json.dumps(detail, ensure_ascii=False, separators=(",", ":")) + "\n")
                    detail_file.flush()
                    for call in result["model_calls"]:
                        request_file.write(json.dumps({
                            "question_id": question["id"], "group": group_id,
                            "case_id": case_id, "call_id": call.get("call_id"),
                            "logical_key": call.get("logical_key"),
                            "kind": call.get("kind"), "status": call.get("status"),
                            "usage_json": call.get("usage_json"),
                            "request_json": call.get("request_json"),
                            "result_json": call.get("result_json"),
                            "evidence_level": "FIXTURE_OFFLINE_ACTUAL_PERSISTED_REQUEST_JSON",
                        }, ensure_ascii=False, separators=(",", ":")) + "\n")
                    request_file.flush()
                    completed += 1
                    print(f"completed {completed}/{len(questions) * len(STRATEGIES)} {case_id}: "
                          f"{row['status']} {row['availability']['status']} "
                          f"compress={row['compression_call_count']}", flush=True)
    finally:
        harness.RESULT_DIR = original_result_dir

    (output_dir / "HISTORY_SNAPSHOT.json").write_text(
        json.dumps(shared_history, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    aggregate: dict[str, Any] = {}
    for group_id, group in STRATEGIES.items():
        rows = [row for row in all_run_results if row["group"] == group_id]
        by_status: dict[str, int] = {}
        for row in rows:
            value = row["availability"]["status"]
            by_status[value] = by_status.get(value, 0) + 1
        aggregate[group_id] = {
            "name": group["name"], "strategy": group["strategy"],
            "window_tokens": group["window"], "configured_input_limit_tokens": group["input_limit"],
            "question_count": len(rows), "status_counts": by_status,
            "fully_available_count": sum(row["availability"]["status"] in {"AVAILABLE_RAW", "AVAILABLE_SUMMARY"} for row in rows),
            "l1_domain_history_complete_count": sum(row["l1_domain_history"]["status"] == "COMPLETE" for row in rows),
            "all_rows_have_actual_manifest": all(bool(row["context_blocks"]) for row in rows),
            "mean_original_history_token_estimate": round(sum(row["original_history_token_estimate"] for row in rows) / len(rows)),
            "mean_final_prompt_estimated_tokens": round(sum(int(row["final_prompt_estimated_tokens"] or 0) for row in rows) / len(rows)),
            "total_compression_calls": sum(row["compression_call_count"] for row in rows),
            "total_compression_attempts": sum(row["compression_attempt_count"] for row in rows),
            "total_compression_failures": sum(row["compression_failure_count"] for row in rows),
            "critical_visibility_gap_count": sum(len(row["critical_visibility_gaps"]) for row in rows),
            "critical_visibility_gaps": [
                {"question_id": row["question_id"], "gaps": row["critical_visibility_gaps"]}
                for row in rows if row["critical_visibility_gaps"]
            ],
        }
    artifact = {
        "schema_version": 1,
        "task": "R2-AR04-LONG-CONTEXT-JOURNEY-01",
        "phase_a_status": "COMPLETED_OFFLINE_FIXTURE_EVIDENCE",
        "phase_b_status": "NOT_RUN",
        "base_sha": "04b01d5c1e542910c4841bd12a065878f06456b4",
        "evidence_level": "FIXTURE_OFFLINE_ACTUAL_PERSISTED_REQUEST_JSON_AND_DOMAIN_ROWS",
        "provider_requests": 0,
        "external_business_writes": 0,
        "live_semantic_evaluation_l3": "NOT_EVALUATED",
        "l1_status": "COMPLETE_FOR_ALL_QUESTIONS" if all(
            row["l1_domain_history"]["status"] == "COMPLETE" for row in all_run_results
        ) else "INCOMPLETE_FACTS_RECORDED",
        "request_invariants": {
            "static_system_prompt_sha256": sorted({row["static_system_prompt_sha256"] for row in all_run_results}),
            "tool_schema_sha256": sorted({row["tool_schema_sha256"] for row in all_run_results}),
            "wire_model_ids": sorted({str(row["wire_model_id"]) for row in all_run_results}),
            "fixture_model_configuration": all_run_results[0]["fixture_model_configuration"] if all_run_results else {},
            "verified_identical_across_48_runs": (
                len({row["static_system_prompt_sha256"] for row in all_run_results}) == 1
                and len({row["tool_schema_sha256"] for row in all_run_results}) == 1
                and len({str(row["wire_model_id"]) for row in all_run_results}) == 1
            ),
            "note": "WORK_CONTEXT and context manifest vary by question/strategy; base system policy, tool schema, and fixture model id are invariant.",
        },
        "history": {"source_trace": "../r2-ar04-compaction-audit-01/case_traces/WP3_INFORMATION_RETENTION.json",
                    "shared_source_user_turn_count": len(seed_bodies),
                    "pre_question_history_message_count": 29,
                    "independent_domain_and_checkpoint_per_question_strategy": True,
                    "cross_question_answer_contamination": False,
                    "snapshot_file": "HISTORY_SNAPSHOT.json"},
        "groups": aggregate,
        "results": all_run_results,
        "evidence_files": ["HISTORY_SNAPSHOT.json", "MODEL_REQUESTS.jsonl.gz", "RUN_DETAILS.jsonl.gz"],
    }
    results_path.write_text(json.dumps(artifact, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.cleanup()
    return artifact


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--question-limit", type=int, default=None,
                        help="run only the first N questions for a smoke pass")
    parser.add_argument("--output-dir", type=Path, default=EVIDENCE,
                        help="directory for evidence outputs")
    parser.add_argument("--overwrite", action="store_true",
                        help="replace existing compressed traces/results")
    args = parser.parse_args()
    artifact = run(args)
    print(json.dumps({
        "results": str((args.output_dir.resolve() / "RESULTS.json")),
        "runs": len(artifact["results"]),
        "provider_requests": artifact["provider_requests"],
        "l3": artifact["live_semantic_evaluation_l3"],
        "groups": {key: value["status_counts"] for key, value in artifact["groups"].items()},
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
