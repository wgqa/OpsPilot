"""Replay the frozen live summary through isolated Domain persistence attempts."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
import uuid
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "docs/evidence/r2-ar04-live-retention-recheck-01"))

from retention_evidence import response_text, trace_index  # noqa: E402
from opspilot.domain import chat  # noqa: E402
from opspilot.domain.context_engineering import estimate_messages_tokens, estimate_text_tokens  # noqa: E402
from opspilot.domain.database import connect  # noqa: E402


LIVE_TRACE = ROOT / "docs/evidence/r2-ar04-live-retention-recheck-01/live_run_01/LIVE_REQUESTS.jsonl.gz"
LIVE_CASE = "Q02-A:SUMMARY:1"


def _token_count(document: dict[str, Any]) -> int:
    return estimate_messages_tokens([{"role": "system", "content": chat._canonical(document)}])


def _load_frozen_summary() -> str:
    summary = response_text(trace_index(LIVE_TRACE), LIVE_CASE)
    if not summary:
        raise RuntimeError("FROZEN_LIVE_SUMMARY_NOT_FOUND")
    return summary


def _domain_record(path: Path, run_id: str, source_map: dict[str, str]) -> dict[str, Any]:
    with connect(path) as db:
        attempt = db.execute(
            "SELECT attempt_no, status, error_class, summary_id FROM context_compression_attempts "
            "WHERE run_id = ? ORDER BY attempt_no DESC LIMIT 1",
            (run_id,),
        ).fetchone()
        run = db.execute(
            "SELECT status, blocked_reason FROM task_runs WHERE run_id = ?",
            (run_id,),
        ).fetchone()
        summary = db.execute(
            "SELECT summary_json FROM context_summaries ORDER BY summary_version DESC LIMIT 1",
        ).fetchone()
        summary_document = json.loads(str(summary["summary_json"])) if summary else None
        source_sequence_by_id = {message_id: int(sequence) for sequence, message_id in source_map.items()}
        projected_items = []
        summary_items = []
        derived_sequence_present = False
        if isinstance(summary_document, dict):
            for field, value in summary_document.items():
                items = [value] if isinstance(value, dict) else value if isinstance(value, list) else []
                for item in items:
                    if not isinstance(item, dict):
                        continue
                    derived_sequence_present = derived_sequence_present or "sequence" in item
                    message_ids = item.get("source_message_ids", [])
                    projected_items.append({
                        "field": field,
                        "source_sequences": [source_sequence_by_id[message_id] for message_id in message_ids
                                             if message_id in source_sequence_by_id],
                        "all_source_ids_resolve": bool(message_ids) and all(
                            message_id in source_sequence_by_id for message_id in message_ids
                        ),
                    })
                    summary_items.append({
                        "field": field,
                        "text": str(item.get("text", "")),
                        "source_sequences": [source_sequence_by_id[message_id] for message_id in message_ids
                                             if message_id in source_sequence_by_id],
                    })
        not_marker = chr(0x4e0d)
        unknown_version = "".join(chr(value) for value in (0x90e8, 0x7f72, 0x7248, 0x672c, 0x672a, 0x77e5))
        fact_specs = {
            "callback_endpoint_seq3": ({"/callback"}, {"user_assertions"}, {3}),
            "early_retry_value_seq3": ({"max_attempts=3"}, {"user_assertions"}, {3}),
            "formal_request_correction": ({"req-482", "req-483"}, {"corrections"}, {7}),
            "protocol_version_change": ({"v1.2", "v1.3"}, {"timeline", "unresolved_items"}, {11}),
            "retry_limit_change": ({"max_attempts", "3", "5"}, {"timeline"}, {11}),
            "deployment_version_unknown": ({unknown_version}, {"constraints", "unresolved_items"}, {11}),
            "http_202_negation_marker": ({"HTTP 202", not_marker}, {"initial_goal"}, {1}),
            "receiver_completion_unresolved": ({"unresolved_receiver_completion=true"}, {"unresolved_items"}, {14, 16}),
        }
        fact_evidence = {}
        for name, (needles, allowed_fields, required_sequences) in fact_specs.items():
            candidate_rows = [
                item for item in summary_items
                if item["field"] in allowed_fields
                and required_sequences.issubset(set(item["source_sequences"]))
            ]
            matches = [
                {"field": item["field"], "source_sequences": item["source_sequences"]}
                for item in candidate_rows
                if all(needle in item["text"] for needle in needles)
            ]
            partial = any(
                "…" in item["text"] and any(needle.split("=", 1)[0] in item["text"] for needle in needles)
                for item in candidate_rows
            )
            fact_evidence[name] = {
                "status": "PRESENT" if matches else "PARTIAL" if partial else "MISSING",
                "visible_with_expected_source": bool(matches),
                "matches": matches,
            }
        return {
            "attempt": dict(attempt) if attempt else None,
            "run": dict(run) if run else None,
            "persisted_summary_count": int(db.execute("SELECT COUNT(*) FROM context_summaries").fetchone()[0]),
            "persisted_summary_tokens": _token_count(summary_document) if summary_document else None,
            "persisted_summary_document": summary_document,
            "persisted_fact_evidence": fact_evidence,
            "derived_sequence_fields_present": derived_sequence_present,
            "source_id_projection": projected_items,
        }


def _run_sample(abc, history, question: str, raw_summary: str, sample: int) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="ar04-live-summary-domain-") as scratch:
        db_path = Path(scratch) / "domain.sqlite3"
        owner = f"ar04-summary-persist-offline-replay-{sample}"
        saved_uuid4 = uuid.uuid4
        counter = 0

        def deterministic_uuid4():
            nonlocal counter
            counter += 1
            return uuid.uuid5(
                uuid.NAMESPACE_URL,
                f"opspilot-live-summary-persist/{sample}/{counter}",
            )

        uuid.uuid4 = deterministic_uuid4
        try:
            session_id, run_id, _, identity = abc._setup_harness()._seed_domain(
                db_path, owner, history, question,
            )
        finally:
            uuid.uuid4 = saved_uuid4

        os.environ["OPSPILOT_CONTEXT_STRATEGY"] = "HYBRID"
        os.environ["OPSPILOT_CONTEXT_INPUT_BUDGET_TOKENS"] = "12000"
        prepared = chat.prepare_chat_compression_attempt(
            db_path, run_id, owner, "deepseek-flash",
        )
        if prepared is None:
            raise RuntimeError("ISOLATED_DOMAIN_DID_NOT_REQUIRE_COMPRESSION")

        with connect(db_path) as db:
            reserved = db.execute(
                "SELECT source_dependencies_json FROM context_compression_attempts WHERE attempt_id = ?",
                (prepared["attempt_id"],),
            ).fetchone()
        dependencies = json.loads(str(reserved["source_dependencies_json"]))
        source_map = {str(key): str(value) for key, value in dependencies["source_sequence_map"].items()}
        validated = chat._validate_summary_document(raw_summary, source_map)
        row: dict[str, Any] = {
            "sample": sample,
            "session_id_sha256": hashlib.sha256(session_id.encode()).hexdigest(),
            "run_id_sha256": hashlib.sha256(run_id.encode()).hexdigest(),
            "attempt_id_sha256": hashlib.sha256(str(prepared["attempt_id"]).encode()).hexdigest(),
            "input_estimate_tokens": prepared["estimated_input_tokens"],
            "input_budget_tokens": prepared["input_budget_tokens"],
            "validated_before_compaction_tokens": _token_count(validated),
            "message_id_policy": "synthetic deterministic IDs generated as message-{UUID} by the isolated Domain fixture",
            "source_sequence_to_message_id": {key: source_map[key] for key in sorted(source_map, key=int)},
            "source_message_id_token_counts": {
                key: estimate_text_tokens(value) for key, value in source_map.items()
            },
        }

        compaction = {"before_tokens": _token_count(validated)}
        original_compactor = chat._compact_summary_document
        previous_trace = sys.gettrace()
        observed_anchor_states: set[tuple[tuple[str, tuple[int, ...]], ...]] = set()

        def observe_compactor(frame, event, argument):
            if frame.f_code is not original_compactor.__code__:
                return observe_compactor
            if event == "line":
                local = frame.f_locals
                if "selected_by_index" in local and "anchor_candidates" in local and "fill_order" not in local:
                    signature = tuple(
                        (field, tuple(sorted(indices)))
                        for field, indices in local["selected_by_index"].items()
                    )
                    if signature not in observed_anchor_states:
                        observed_anchor_states.add(signature)
                        tokens = local["token_count"](local["result"])
                        trace = compaction.setdefault("anchor_selection_trace", [])
                        trace.append({
                            "selected_items": sum(len(indices) for _, indices in signature),
                            "estimated_tokens": tokens,
                        })
                        compaction["anchor_selection_peak_tokens"] = max(
                            tokens, compaction.get("anchor_selection_peak_tokens", 0),
                        )
            if event == "exception":
                error = argument[1]
                if getattr(error, "code", None) == "CONTEXT_SUMMARY_FACT_RETENTION_BUDGET_EXCEEDED":
                    local = frame.f_locals
                    field = local["field"]
                    index = local["index"]
                    compaction["failed_field"] = field
                    compaction["failed_index"] = index
                    compaction["selected_tokens_before_failed_anchor"] = _token_count(local["result"])
                    compaction["selected_anchor_text_lengths"] = {
                        name: [len(item["text"]) for item in local["result"][name]]
                        for name in local["fields"] if local["result"][name]
                    }
                    for max_chars in (48, 24):
                        candidate = local["normalized"](
                            local["candidates_by_field"][field][index], max_chars,
                        )
                        if candidate is None:
                            continue
                        trial_selection = {**local["selected_by_index"][field], index: candidate}
                        trial = {
                            **local["result"],
                            field: [trial_selection[key] for key in sorted(trial_selection)],
                        }
                        compaction[f"trial_{max_chars}_char_anchor_tokens"] = _token_count(trial)
                        without_derived_sequence = json.loads(json.dumps(trial))
                        derived_sequence_count = 0
                        for key, value in without_derived_sequence.items():
                            items = [value] if isinstance(value, dict) else value if isinstance(value, list) else []
                            for item in items:
                                if isinstance(item, dict) and "sequence" in item:
                                    item.pop("sequence")
                                    derived_sequence_count += 1
                        compaction["derived_sequence_fields_removed"] = derived_sequence_count
                        compaction[f"trial_{max_chars}_char_without_sequence_tokens"] = _token_count(
                            without_derived_sequence,
                        )
            return observe_compactor

        def measure_compaction(document):
            try:
                compacted = original_compactor(document)
            except chat.TaskControlError as error:
                compaction["error_code"] = error.code
                compaction["safe_detail"] = str(error)
                if error.code == "CONTEXT_SUMMARY_FACT_RETENTION_BUDGET_EXCEEDED":
                    parts = str(error).split(":")
                    if len(parts) >= 3:
                        compaction["failed_field"] = parts[-2]
                        try:
                            compaction["failed_index"] = int(parts[-1])
                        except ValueError:
                            pass
                raise
            compaction["after_tokens"] = _token_count(compacted)
            return compacted

        chat._compact_summary_document = measure_compaction
        try:
            sys.settrace(observe_compactor)
            result = chat.complete_chat_compression_attempt(
                db_path, owner, str(prepared["attempt_id"]), raw_summary,
                provider_response_id="FROZEN_LIVE_RESPONSE_OFFLINE_REPLAY",
                input_tokens=4106, output_tokens=481, total_tokens=4587,
            )
            row["completion_result"] = {
                "status": result["status"],
                "summary_version": result.get("summary_version"),
                "summary_digest": result.get("summary_digest"),
            }
        except chat.TaskControlError as error:
            row["completion_error"] = {
                "code": error.code,
                "safe_detail": str(error),
                "detail_is_safe": str(error).startswith(error.code + ":") or str(error) == error.code,
            }
            chat.fail_chat_compression_attempt(
                db_path, owner, str(prepared["attempt_id"]), error.code,
            )
        finally:
            sys.settrace(previous_trace)
            chat._compact_summary_document = original_compactor

        if row.get("completion_error", {}).get("code") == "CONTEXT_SUMMARY_FACT_RETENTION_BUDGET_EXCEEDED":
            capacity_trials = {}
            for cap in (512, 768, 1024):
                previous_cap = chat.MAX_COMPRESSION_OUTPUT_TOKENS
                chat.MAX_COMPRESSION_OUTPUT_TOKENS = cap
                try:
                    compacted = original_compactor(json.loads(json.dumps(validated)))
                except chat.TaskControlError as error:
                    capacity_trials[str(cap)] = {"status": "REJECTED", "error_code": error.code}
                else:
                    capacity_trials[str(cap)] = {
                        "status": "FITS",
                        "compacted_tokens": _token_count(compacted),
                        "selected_items_by_field": {
                            field: len(items) for field, items in compacted.items()
                            if isinstance(items, list) and items
                        },
                    }
                finally:
                    chat.MAX_COMPRESSION_OUTPUT_TOKENS = previous_cap
            row["capacity_trials"] = capacity_trials

        row["compaction"] = compaction
        row["domain_after_completion"] = _domain_record(db_path, run_id, source_map)
        row["answer_manifest_count"] = len(chat.get_chat_manifest(db_path, identity, run_id)["attempts"])
        row["provider_answer_dispatches"] = 0
        row["later_dispatch_blocked_by_harness"] = True
        return row


def run(samples: int = 5) -> dict[str, Any]:
    from run_recheck import abc_runner

    abc = abc_runner()
    history, questions, history_digest, _ = abc.load_frozen_inputs()
    raw_summary = _load_frozen_summary()
    previous_strategy = os.environ.get("OPSPILOT_CONTEXT_STRATEGY")
    previous_budget = os.environ.get("OPSPILOT_CONTEXT_INPUT_BUDGET_TOKENS")
    try:
        rows = [
            _run_sample(abc, history, questions["Q02"]["prompt_text"], raw_summary, index)
            for index in range(samples)
        ]
    finally:
        if previous_strategy is None:
            os.environ.pop("OPSPILOT_CONTEXT_STRATEGY", None)
        else:
            os.environ["OPSPILOT_CONTEXT_STRATEGY"] = previous_strategy
        if previous_budget is None:
            os.environ.pop("OPSPILOT_CONTEXT_INPUT_BUDGET_TOKENS", None)
        else:
            os.environ["OPSPILOT_CONTEXT_INPUT_BUDGET_TOKENS"] = previous_budget
    return {
        "evidence": "FROZEN_REAL_PROVIDER_RESPONSE_REPLAYED_THROUGH_ISOLATED_DOMAIN",
        "provider_requests": 0,
        "history_rows": len(history),
        "history_digest_sha256": history_digest,
        "case_id": "Q02-A",
        "strategy": "HYBRID",
        "output_cap_tokens": chat.MAX_COMPRESSION_OUTPUT_TOKENS,
        "raw_summary_estimated_tokens": estimate_messages_tokens([{"role": "system", "content": raw_summary}]),
        "sample_count": samples,
        "message_id_policy": "deterministic production-format message-{UUID} IDs in an isolated Domain seed",
        "samples": rows,
        "result_counts": {
            "SUCCEEDED": sum(row.get("completion_result", {}).get("status") == "SUCCEEDED" for row in rows),
            "FAILED": sum("completion_error" in row for row in rows),
        },
        "live_source_map_recoverable": False,
        "note": "Every sequence-to-message map below is synthetic. None is the original live map.",
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--samples", type=int, default=5)
    args = parser.parse_args()
    result = run(samples=args.samples)
    rendered = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
