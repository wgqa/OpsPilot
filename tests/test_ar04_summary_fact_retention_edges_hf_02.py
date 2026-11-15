"""Deterministic checks of source-linked text before and after compaction."""

import json
import uuid

import pytest

from opspilot.domain import chat
from opspilot.domain.context_engineering import estimate_messages_tokens


NEGATED_CONSTRAINT = "Callback delivery is permitted for the replay rehearsal only when the receiver is not disabled."


def _item(text, *references):
    return {"text": text, "source_sequences": list(references)}


def _document(**categories):
    return {
        "initial_goal": _item("Read-only audit of callback delivery and protocol history.", 1),
        **dict.fromkeys(("constraints", "corrections", "rejected_hypotheses", "unresolved_items",
                         "timeline", "user_assertions"), []),
        **categories,
    }


def _validated(document):
    items = [document["initial_goal"]]
    for entries in document.values():
        if isinstance(entries, list):
            items.extend(entries)
    sequences = {seq for item in items for seq in item["source_sequences"]}
    message_ids = {str(seq): f"message-{uuid.uuid5(uuid.NAMESPACE_URL, f'opspilot/hf02/{seq}')}"
                   for seq in sorted(sequences)}
    return chat._validate_summary_document(json.dumps(document), message_ids), message_ids


def _project(persisted, message_ids):
    sequence_by_message = {message_id: int(seq) for seq, message_id in message_ids.items()}
    return chat._compact_summary_document(chat._summary_prompt_projection(persisted, sequence_by_message))


def _tokens(document):
    return estimate_messages_tokens([{"role": "system", "content": chat._canonical(document)}])


@pytest.mark.parametrize(
    ("field", "text", "tail"),
    [
        ("timeline", "The callback contract changed after the delivery compatibility review from v4.2.7 to v4.3.1.",
         "v4.2.7 to v4.3.1."),
        ("corrections", "Formal correction to the archived intake report: replace mistyped Request ID req-312 with req-731.",
         "req-312 with req-731."),
        ("constraints", NEGATED_CONSTRAINT, "only when the receiver is not disabled."),
    ],
    ids=["version", "request-id", "negation"],
)
def test_tail_facts_with_headroom_survive_persistence_and_projection(field, text, tail):
    original, sources = _validated(_document(**{field: [_item(text, 3)]}))
    assert len(text) <= 100
    assert text.endswith(tail)
    assert _tokens(original) <= 512, "the whole validated document fits without clipping"

    persisted = chat._compact_summary_document(original)
    next_summary = _project(persisted, sources)
    stored_item, projected_item = persisted[field][0], next_summary[field][0]
    print(json.dumps({
        "category": field, "tail": tail, "source_sequence": 3,
        "validated_tokens": _tokens(original), "persisted_tokens": _tokens(persisted),
        "next_summary_tokens": _tokens(next_summary), "input": text,
        "stored": stored_item["text"], "projected": projected_item["text"],
    }, ensure_ascii=False))
    assert stored_item["source_message_ids"] == [sources["3"]]
    assert projected_item["source_sequences"] == [3]
    assert _tokens(persisted) <= 512 and _tokens(next_summary) <= 512
    assert stored_item["text"] == text
    assert projected_item["text"] == text


def test_four_same_category_facts_compete_without_merging_corrections():
    assertions = [
        _item("Initial Request ID: req-312.", 3),
        _item("The original read timeout was 90 ms.", 4),
        _item("The initial receiver topic was callback-test.", 5),
        _item("Later staging configuration used topic callback-canary.", 8),
    ]
    correction = _item("Formal correction: req-312 was mistyped. Use req-731.", 9)
    timeline = _item("Protocol v4.2.7 changed to v4.3.1 in the draft.", 11)
    unresolved = _item("The deployment version remains unknown.", 12)
    original, sources = _validated(_document(
        user_assertions=assertions, corrections=[correction], timeline=[timeline],
        unresolved_items=[unresolved],
    ))
    persisted = chat._compact_summary_document(original)
    projected = _project(persisted, sources)
    entries = projected["user_assertions"]
    print(json.dumps({
        "retained_assertions": entries, "omitted_sequence": 4,
        "correction": projected["corrections"], "timeline": projected["timeline"],
        "unresolved": projected["unresolved_items"],
        "validated_tokens": _tokens(original), "persisted_tokens": _tokens(persisted),
        "next_summary_tokens": _tokens(projected),
    }))
    assert _tokens(original) <= 512, "this omission is explained by the per-category cap"
    assert len(entries) == 3
    assert [(item["source_sequences"], item["text"]) for item in entries] == [
        (assertions[i]["source_sequences"], assertions[i]["text"]) for i in (0, 2, 3)
    ]
    for category, item in (("corrections", correction), ("timeline", timeline),
                           ("unresolved_items", unresolved)):
        assert projected[category][0]["source_sequences"] == item["source_sequences"]
        assert projected[category][0]["text"] == item["text"]


def test_redundant_sequence_metadata_removal_preserves_full_negated_constraint():
    original, sources = _validated(_document(
        constraints=[_item(NEGATED_CONSTRAINT, 2, 3, 4)],
        user_assertions=[_item("The request contained a callback replay identifier for the isolated webhook diagnostic.", 5)],
        corrections=[_item("Formal correction to the archived intake report: replace mistyped Request ID req-312 with req-731.", 8, 9, 10)],
        timeline=[_item("The callback contract changed after the delivery compatibility review from v4.2.7 to v4.3.1.", 11, 12)],
        unresolved_items=[_item("Deployment and release approval have yet to be researched in this audit.", 14, 15, 16)],
    ))
    persisted = chat._compact_summary_document(original)
    projected = _project(persisted, sources)
    stored = persisted["constraints"][0]
    next_item = projected["constraints"][0]
    with_full_constraint = {**persisted, "constraints": [{**stored, "text": NEGATED_CONSTRAINT}]}
    print(json.dumps({
        "fidelity": "FULL" if next_item["text"] == NEGATED_CONSTRAINT else "PARTIAL",
        "original_tokens": _tokens(original),
        "persisted_tokens": _tokens(persisted), "with_full_constraint_tokens": _tokens(with_full_constraint),
        "next_summary_tokens": _tokens(projected), "projected_constraint": next_item,
    }, ensure_ascii=False))
    assert chat.MAX_COMPRESSION_OUTPUT_TOKENS == 512
    assert _tokens(original) > 512 and _tokens(with_full_constraint) <= 512
    assert _tokens(persisted) <= 512 and _tokens(projected) <= 512
    assert stored["source_message_ids"] == [sources[str(seq)] for seq in (2, 3, 4)]
    assert next_item["source_sequences"] == [2, 3, 4]
    assert stored["text"] == next_item["text"] == NEGATED_CONSTRAINT
    assert "not disabled" in next_item["text"]
