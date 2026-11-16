"""Measure the frozen second Live response with OpsPilot's local estimator."""

from __future__ import annotations

import copy
import gzip
import hashlib
import json
import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from opspilot.domain import chat
from opspilot.domain.context_engineering import estimate_messages_tokens, estimate_text_tokens
from opspilot.domain.task_control import TaskControlError


LIVE = ROOT / "docs/evidence/r2-ar04-remaining-live-gate-01/live_run_02"
DATASET = ROOT / "docs/evidence/r2-ar04-long-context-journey-01"
LOGICAL_ID = "Q02-B:SUMMARY:1"
TRACE_SHA256 = "6c5d60bce519aad6ce60af1b647845117ca754685320dbc4040c734087672e9a"
HISTORY_SHA256 = "356512f611b046a04e33506a0fb1a88c6a08af93517b2134125dd6771b282c16"
LEDGER_SHA256 = "16aff25f3b1d7adf8b176c9c9c332d01ade453949c7b8c94e15617769def08f4"
LIVE_RESULTS_LF_SHA256 = "12f651c3252b6ddc3256faa686a1822c6b24d83cb2b4d53edce1c3e550172d99"
RESPONSE_ID = "0c1b0cab-cd71-43e0-a9d9-5f36aaefa989"
RESPONSE_SHA256 = "c72295396dcf83670754f251d4be79aa59fb9d2d3b38aef6ef714892c182de82"


def sha(value: str | bytes) -> str:
    return hashlib.sha256(value.encode("utf-8") if isinstance(value, str) else value).hexdigest()


def load_replay():
    trace = (LIVE / "LIVE_REQUESTS.jsonl.gz").read_bytes()
    history_bytes = (DATASET / "HISTORY_SNAPSHOT.json").read_bytes()
    assert sha(trace) == TRACE_SHA256 and sha(history_bytes) == HISTORY_SHA256
    ledger_bytes = (LIVE / "COST_LEDGER.json").read_bytes().replace(b"\r\n", b"\n")
    results_bytes = (LIVE / "LIVE_RESULTS.json").read_bytes().replace(b"\r\n", b"\n")
    assert sha(ledger_bytes) == LEDGER_SHA256 and sha(results_bytes) == LIVE_RESULTS_LF_SHA256
    history = json.loads(history_bytes)["recreated_shared_history_rows"]
    assert len(history) == 29
    assert all(sha(row["body"]) == row["recreated_body_digest"] for row in history)
    request, response = [json.loads(line) for line in gzip.decompress(trace).splitlines()]
    slot = json.loads(ledger_bytes)["slots"][0]
    [attempt] = json.loads(results_bytes)["cases"][0]["compression_attempts"]
    assert request["event"] == "SEND_STARTED" and response["event"] == "RESPONSE_RECEIVED"
    assert request["logical_id"] == response["logical_id"] == slot["logical_id"] == LOGICAL_ID
    assert request["request_body_sha256"] == response["request_body_sha256"] == slot["request_digest"]
    assert response["provider_request_id"] == slot["provider_request_id"] == RESPONSE_ID
    assert response["response_body_sha256"] == RESPONSE_SHA256
    assert response["http_status"] == 200 and response["finish_reason"] == "stop"
    assert attempt["error_class"] == "CONTEXT_SUMMARY_FACT_RETENTION_BUDGET_EXCEEDED"
    messages = request["request_payload"]["messages"]
    assert sha(chat._canonical(messages)) == attempt["prompt_digest"]
    material = json.loads(messages[1]["content"].split("\n", 1)[1])
    assert material["previous_summary"] is None
    sent = material["new_messages"]
    cut = {row["sequence"]: row for row in material["truncated_sources"]}
    assert [row["sequence"] for row in sent] == list(range(1, 17)) and set(cut) == {16}
    assert len(set(attempt["allowed_message_ids"])) == len(sent)
    dependencies = {
        row["ref"]: row for row in attempt["source_dependencies"]
        if row["kind"] in {"MESSAGE", "ASSISTANT_MESSAGE"}
    }
    source_map = {}
    for actual, message_id in zip(sent, attempt["allowed_message_ids"], strict=True):
        seq = actual["sequence"]
        frozen = history[seq - 1]
        dependency = dependencies[message_id]
        assert frozen["sequence"] == seq and actual["role"] == frozen["role"].lower()
        assert dependency["digest"] == frozen["recreated_body_digest"]
        if actual["role"] == "assistant":
            assert dependency["kind"] == "ASSISTANT_MESSAGE" and dependency["version"] == str(seq)
        else:
            assert dependency["kind"] == "MESSAGE"
        if seq in cut:
            assert cut[seq]["message_id"] == message_id and cut[seq]["original_digest"] == dependency["digest"]
            head, tail = actual["body"].split("\n[historical assistant text omitted to fit the compression input budget]\n")
            assert actual["body"] == chat._assistant_history_excerpt(frozen["body"], len(head) + len(tail))
        else:
            assert actual["body"] == frozen["body"]
        source_map[str(seq)] = message_id
    assert set(source_map.values()) == set(dependencies)
    return history, source_map, messages, response


def entries(document):
    for field, value in document.items():
        for index, item in enumerate(value if isinstance(value, list) else [value]):
            yield field, index, item


def tokens(document):
    return estimate_messages_tokens([{"role": "system", "content": chat._canonical(document)}])


def breakdown(document, source_key):
    without_sources = copy.deepcopy(document)
    skeleton = copy.deepcopy(document)
    for _, _, item in entries(without_sources):
        item[source_key] = []
    for _, _, item in entries(skeleton):
        item[source_key] = []
        item["text"] = ""
    frame = tokens(document) - estimate_text_tokens(chat._canonical(document))
    return {
        "json_skeleton_tokens": tokens(skeleton) - frame,
        "text_marginal_tokens": tokens(without_sources) - tokens(skeleton),
        "source_values_marginal_tokens": tokens(document) - tokens(without_sources),
        "system_message_frame_tokens": frame,
        "total_tokens": tokens(document),
    }


def measure():
    _, source_map, messages, response = load_replay()
    summary = response["response_payload"]["choices"][0]["message"]["content"]
    validated = chat._validate_summary_document(summary, source_map)
    id_to_seq = {message_id: int(seq) for seq, message_id in source_map.items()}
    id_document = copy.deepcopy(validated)
    for _, _, item in entries(id_document):
        del item["sequence"]
    sequence_document = chat._summary_prompt_projection(id_document, id_to_seq)
    assert sequence_document == json.loads(summary)

    tried = []

    def observe(payload):
        total = estimate_messages_tokens(payload)
        tried.append((total, json.loads(payload[0]["content"])))
        return total

    with patch.object(chat, "estimate_messages_tokens", side_effect=observe):
        try:
            chat._compact_summary_document(validated)
        except TaskControlError as error:
            failure = {"code": error.code, "detail": str(error)}
        else:
            raise AssertionError("The existing ID-based compactor must reproduce the failure")

    trials = []
    previous = set()
    for total, candidate in tried:
        selected = {
            (field, tuple(id_to_seq[ref] for ref in item["source_message_ids"])): item["text"]
            for field, _, item in entries(candidate)
        }
        added = selected.keys() - previous
        assert len(added) <= 1
        trial = {"total_id_tokens": total, "total_sequence_tokens": tokens(
            chat._summary_prompt_projection(candidate, id_to_seq))}
        if added:
            field, seqs = next(iter(added))
            [index] = [index for key, index, item in entries(sequence_document)
                       if key == field and item["source_sequences"] == list(seqs)]
            trial.update(field=field, index=index, sequences=list(seqs), text_chars=len(selected[field, seqs]))
        if total <= chat.MAX_PERSISTED_SUMMARY_TOKENS:
            previous = set(selected)
        trials.append(trial)
    failing = tried[-1][1]
    required = copy.deepcopy(failing)
    for field, _, item in entries(required):
        [full] = [raw for key, _, raw in entries(id_document)
                  if key == field and raw["source_message_ids"] == item["source_message_ids"]]
        item["text"] = full["text"]
    return {
        "evidence_level": "SAVED_PROVIDER_RESPONSE_REPLAYED_WITH_ACTUAL_SOURCE_IDS",
        "provider_requests": 0,
        "trace_sha256": TRACE_SHA256,
        "response_id": RESPONSE_ID,
        "response_body_sha256": RESPONSE_SHA256,
        "summary_text_sha256": sha(summary),
        "history_sha256": HISTORY_SHA256,
        "source_sequence_to_message_id": source_map,
        "input_prompt_digest": sha(chat._canonical(messages)),
        "input_estimate_tokens": estimate_messages_tokens(messages),
        "provider_reported_output_tokens": response["usage"]["output_tokens"],
        "model_text_local_tokens": estimate_text_tokens(summary),
        "validated_with_derived_sequence_tokens": tokens(validated),
        "full_document_with_ids": breakdown(id_document, "source_message_ids"),
        "full_document_with_sequences": breakdown(sequence_document, "source_sequences"),
        "full_document_item_count": sum(1 for _ in entries(sequence_document)),
        "full_document_source_reference_count": sum(len(row["source_sequences"]) for _, _, row in entries(sequence_document)),
        "failed_shortest_candidate": breakdown(failing, "source_message_ids"),
        "required_anchors_full_text_with_ids": breakdown(required, "source_message_ids"),
        "required_anchors_full_text_with_sequences": breakdown(
            chat._summary_prompt_projection(required, id_to_seq), "source_sequences"),
        "persistence_cap_tokens": chat.MAX_PERSISTED_SUMMARY_TOKENS,
        "failure": failure,
        "anchor_trials": trials,
    }


def measure_candidate():
    diagnostic = measure()
    _, source_map, _, response = load_replay()
    summary = response["response_payload"]["choices"][0]["message"]["content"]
    validated = chat._validate_summary_document(summary, source_map)
    old_projection = chat._compact_summary_document(chat._summary_prompt_projection(
        validated, {message_id: int(seq) for seq, message_id in source_map.items()},
    ))
    candidate = chat._compact_summary_for_persistence(validated, source_map)
    assert candidate == json.loads(summary)
    assert tokens(candidate) <= chat.MAX_PERSISTED_SUMMARY_TOKENS
    goal_only = {key: [] for key in candidate}
    goal_only["initial_goal"] = {k: v for k, v in validated["initial_goal"].items() if k != "sequence"}
    more = copy.deepcopy(candidate)
    more["rejected_hypotheses"].append({
        "text": "Additional fixture detail preserves each original observation and cites its permitted source.",
        "source_sequences": [9],
    })
    assert tokens(more) > chat.MAX_PERSISTED_SUMMARY_TOKENS
    try:
        chat._compact_summary_for_persistence(
            chat._validate_summary_document(chat._canonical(more), source_map), source_map,
        )
    except TaskControlError as error:
        over_budget = {"tokens": tokens(more), "status": "REJECTED", "error_code": error.code}
    else:
        raise AssertionError("Over-budget full projection was accepted")
    return {
        "evidence_level": "SAVED_PROVIDER_RESPONSE_AND_LOCAL_PERSISTENCE_FUNCTION_REPLAY",
        "provider_requests": 0,
        "source_trace_sha256": diagnostic["trace_sha256"],
        "legacy_error": diagnostic["failure"],
        "initial_goal_with_empty_lists": breakdown(goal_only, "source_message_ids"),
        "legacy_recompaction_on_sequences": {
            "summary_tokens": tokens(old_projection),
            "items": sum(1 for _ in entries(old_projection)),
            "source_references": sum(len(row["source_sequences"]) for _, _, row in entries(old_projection)),
        },
        "candidate": {
            "representation": "source_sequences",
            "summary_tokens": tokens(candidate),
            "full_saved_reply_text_and_citations_unchanged": candidate == json.loads(summary),
            "items": sum(1 for _ in entries(candidate)),
            "source_references": sum(len(row["source_sequences"]) for _, _, row in entries(candidate)),
        },
        "over_budget_variant": over_budget,
        "l3_model_answer": "NOT_RUN_OFFLINE",
    }


if __name__ == "__main__":
    def block_network(event, _args):
        if event in {"socket.connect", "socket.getaddrinfo"}:
            raise RuntimeError("OFFLINE_REPLAY_NETWORK_BLOCKED")

    sys.addaudithook(block_network)
    sys.stdout.reconfigure(encoding="utf-8")
    report = measure_candidate() if sys.argv[1:] == ["--candidate"] else measure()
    print(json.dumps(report, ensure_ascii=False, indent=2))
