from __future__ import annotations

import math
import os
from functools import lru_cache
from typing import Any

import tiktoken


ESTIMATOR_ID = "tiktoken:cl100k_base:0.14.0"
CONTEXT_POLICY_VERSION = "opspilot-context-budget-v1"
CONTEXT_STRATEGIES = {"RECENT_WINDOW", "ROLLING_SUMMARY", "HYBRID"}

# These are OpsPilot application budgets, not assertions about provider limits.
# A deployment may set the exact model profile through environment configuration.
_DEFAULT_PROFILE = {
    "context_window_tokens": 16_384,
    "input_limit_tokens": 12_000,
    "output_reserved_tokens": 512,
    "safety_margin_tokens": 1_024,
}
_MODEL_PROFILES = {
    "deepseek-flash": {
        "context_window_tokens": 16_384,
        "input_limit_tokens": 12_000,
        "output_reserved_tokens": 512,
        "safety_margin_tokens": 1_024,
    },
}


class ContextBudgetExceeded(RuntimeError):
    def __init__(self, code: str, *, required_tokens: int, input_budget_tokens: int) -> None:
        super().__init__(f"{code} ({required_tokens} > {input_budget_tokens} tokens)")
        self.code = code
        self.required_tokens = required_tokens
        self.input_budget_tokens = input_budget_tokens


@lru_cache(maxsize=1)
def _encoding() -> tiktoken.Encoding:
    return tiktoken.get_encoding("cl100k_base")


def estimate_text_tokens(text: str) -> int:
    """Local, reproducible estimate. Provider-reported usage is stored separately."""
    return len(_encoding().encode(text, disallowed_special=()))


def estimate_messages_tokens(messages: list[dict[str, Any]]) -> int:
    total = 2
    for message in messages:
        total += 4
        total += estimate_text_tokens(str(message.get("role", "")))
        content = message.get("content", "")
        if isinstance(content, str):
            total += estimate_text_tokens(content)
        else:
            total += estimate_text_tokens(_stable_content(content))
    return total


def _stable_content(value: Any) -> str:
    import json

    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def context_budget_for_model(
    model_id: str,
    *,
    overrides: dict[str, int] | None = None,
) -> dict[str, int | str]:
    profile = dict(_MODEL_PROFILES.get(model_id, _DEFAULT_PROFILE))
    if overrides:
        for key in profile:
            if key in overrides:
                profile[key] = int(overrides[key])
    env_map = {
        "context_window_tokens": "OPSPILOT_CONTEXT_WINDOW_TOKENS",
        "input_limit_tokens": "OPSPILOT_CONTEXT_INPUT_BUDGET_TOKENS",
        "output_reserved_tokens": "OPSPILOT_CONTEXT_OUTPUT_RESERVE_TOKENS",
        "safety_margin_tokens": "OPSPILOT_CONTEXT_SAFETY_MARGIN_TOKENS",
    }
    for key, env_name in env_map.items():
        raw = os.environ.get(env_name)
        if raw:
            try:
                profile[key] = int(raw)
            except ValueError as error:
                raise ValueError(f"{env_name} must be an integer.") from error
    if any(int(value) < 0 for value in profile.values()) or int(profile["context_window_tokens"]) < 1:
        raise ValueError("Context budget values must be non-negative and the context window positive.")
    available = max(
        0,
        int(profile["context_window_tokens"])
        - int(profile["output_reserved_tokens"])
        - int(profile["safety_margin_tokens"]),
    )
    input_budget = min(int(profile["input_limit_tokens"]), available)
    return {
        "policy_version": CONTEXT_POLICY_VERSION,
        "model_id": model_id,
        "estimator": ESTIMATOR_ID,
        "context_window_tokens": int(profile["context_window_tokens"]),
        "configured_input_limit_tokens": int(profile["input_limit_tokens"]),
        "output_reserved_tokens": int(profile["output_reserved_tokens"]),
        "safety_margin_tokens": int(profile["safety_margin_tokens"]),
        "input_budget_tokens": input_budget,
    }


def allocate_context_blocks(
    blocks: list[dict[str, Any]],
    *,
    budget: dict[str, Any],
    strategy: str = "HYBRID",
) -> dict[str, Any]:
    if strategy not in CONTEXT_STRATEGIES:
        raise ValueError("Unsupported Context strategy.")
    normalized: list[dict[str, Any]] = []
    for source in blocks:
        item = dict(source)
        messages = item.get("messages")
        if isinstance(messages, list):
            estimate = estimate_messages_tokens(messages)
        else:
            estimate = estimate_text_tokens(str(item.get("content", ""))) + 4
        item["estimated_tokens"] = estimate
        item["required"] = bool(item.get("required", False))
        item["priority"] = int(item.get("priority", 0))
        normalized.append(item)

    available = int(budget["input_budget_tokens"])
    required = [item for item in normalized if item["required"]]
    optional = sorted(
        (item for item in normalized if not item["required"]),
        key=lambda item: (-item["priority"], str(item.get("block_id", ""))),
    )
    required_total = sum(int(item["estimated_tokens"]) for item in required)
    if required_total > available:
        raise ContextBudgetExceeded(
            "REQUIRED_CONTEXT_EXCEEDS_BUDGET",
            required_tokens=required_total,
            input_budget_tokens=available,
        )
    selected = list(required)
    excluded: list[dict[str, Any]] = []
    used = required_total
    for item in optional:
        cost = int(item["estimated_tokens"])
        if used + cost <= available:
            selected.append(item)
            used += cost
        else:
            excluded.append({
                "block_id": item.get("block_id"),
                "category": item.get("category"),
                "source_refs": item.get("source_refs", []),
                "reason": "INPUT_TOKEN_BUDGET",
                "estimated_tokens": cost,
            })
    selected.sort(key=lambda item: (int(item.get("order", 0)), str(item.get("block_id", ""))))
    return {
        "strategy": strategy,
        "selected_blocks": selected,
        "excluded_blocks": excluded,
        "estimated_input_tokens": used,
        "input_budget_tokens": available,
        "utilization": round(used / available, 4) if available else 1.0,
    }


def bounded_recent_window(
    messages: list[dict[str, Any]],
    *,
    budget_tokens: int,
    required_message_id: str | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], int]:
    kept: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    used = 2
    for item in reversed(messages):
        cost = estimate_messages_tokens([item])
        if used + cost <= budget_tokens or str(item.get("message_id")) == required_message_id:
            kept.append(item)
            used += cost
        else:
            excluded.append({
                "source_id": item.get("message_id"),
                "reason": "RECENT_WINDOW_TOKEN_BUDGET",
                "estimated_tokens": cost,
            })
    kept.reverse()
    excluded.reverse()
    return kept, excluded, used


def investigator_context_budget(
    messages: list[Any], model_id: str,
    tool_specs: list[dict[str, object]], metadata: dict[str, object],
) -> dict[str, object]:
    from opspilot.domain.d2 import canonical_json

    serialized_messages = [
        {"role": str(message.type), "content": str(message.content)} for message in messages
    ]
    budget = context_budget_for_model(model_id)
    prompt_tokens = estimate_messages_tokens(serialized_messages)
    tool_tokens = estimate_text_tokens(canonical_json(tool_specs)) if tool_specs else 0
    estimated = prompt_tokens + tool_tokens + 8
    input_limit = int(budget["input_budget_tokens"])
    if estimated > input_limit:
        raise ContextBudgetExceeded(
            "INVESTIGATOR_CONTEXT_EXCEEDS_BUDGET",
            required_tokens=estimated, input_budget_tokens=input_limit,
        )
    input_refs = metadata.get("selected_input_messages", [])
    evidence_ids = metadata.get("evidence_ids", [])
    memories = metadata.get("selected_memories", [])
    knowledge = metadata.get("selected_knowledge", [])
    prior_followups = metadata.get("prior_readonly_followups", [])
    component_estimates = metadata.get("context_component_estimates", {})
    component_estimates = component_estimates if isinstance(component_estimates, dict) else {}
    selected_inputs = [
        str(item.get("message_id")) for item in input_refs
        if isinstance(item, dict) and item.get("message_id")
    ]
    task_run_control = metadata.get("task_run_control", {})
    task_state_refs = [
        str(task_run_control.get(key)) for key in ("run_id", "source_message_id")
        if isinstance(task_run_control, dict) and task_run_control.get(key)
    ]
    selected_skill = metadata.get("selected_skill")
    external_refs = [
        str(item.get("memory_id")) for item in memories
        if isinstance(item, dict) and item.get("memory_id")
    ] + [
        str(item.get("document_id")) for item in knowledge
        if isinstance(item, dict) and item.get("document_id")
    ]
    if isinstance(selected_skill, dict) and selected_skill.get("name"):
        external_refs.append(str(selected_skill["name"]))
    prior_followup_refs = [
        str(value)
        for item in prior_followups if isinstance(item, dict)
        for value in (item.get("run_id"), item.get("result_digest"), item.get("source_message_id"))
        if value
    ]
    blocks = [
        {
            "block_id": "investigator-trusted-control", "category": "TRUSTED_CONTROL",
            "authority": "APPLICATION_DEFINED_SAFETY_POLICY", "status": "SELECTED",
            "estimated_tokens": int(component_estimates.get("trusted_control", prompt_tokens)),
            "source_refs": [],
        },
        {
            "block_id": "investigator-current-task-state", "category": "CURRENT_TASK_STATE",
            "authority": "TRUSTED_TASK_BINDING_AND_RUN_CONTROL", "status": "SELECTED",
            "estimated_tokens": int(component_estimates.get("current_task_state", 0)),
            "source_refs": task_state_refs,
        },
        {
            "block_id": "investigator-current-facts", "category": "CURRENT_FACTS",
            "authority": "TASK_SCOPED_MCP_EVIDENCE_AND_OBSERVATIONS", "status": "SELECTED",
            "estimated_tokens": int(component_estimates.get("current_facts", 0)),
            "source_refs": [str(item) for item in evidence_ids],
        },
        {
            "block_id": "investigator-recent-interaction", "category": "RECENT_INTERACTION",
            "authority": "UNTRUSTED_USER_INPUT", "status": "SELECTED",
            "estimated_tokens": int(component_estimates.get("recent_interaction", 0)),
            "source_refs": selected_inputs,
        },
        {
            "block_id": "investigator-historical-summary", "category": "HISTORICAL_SUMMARY",
            "authority": "NONE_IN_INVESTIGATION_RUN", "status": "NOT_APPLICABLE",
            "estimated_tokens": 0, "source_refs": [],
        },
        {
            "block_id": "investigator-external-guidance", "category": "EXTERNAL_GUIDANCE",
            "authority": "HISTORICAL_METHOD_HINT_AND_VERSIONED_KNOWLEDGE",
            "status": "SELECTED" if external_refs else "EMPTY",
            "estimated_tokens": int(component_estimates.get("external_guidance", 0)),
            "source_refs": external_refs,
        },
        {
            "block_id": "investigator-prior-readonly-followups", "category": "PRIOR_READONLY_FOLLOWUP",
            "authority": "HISTORICAL_RESULT_ONLY",
            "status": "SELECTED" if prior_followup_refs else "EMPTY",
            "estimated_tokens": int(component_estimates.get("prior_readonly_followups", 0)),
            "source_refs": prior_followup_refs,
        },
        {
            "block_id": "read-only-mcp-tool-schemas", "category": "TOOL_SCHEMA",
            "authority": "APPLICATION_DEFINED_READ_ONLY_TOOLS", "status": "SELECTED",
            "estimated_tokens": tool_tokens, "source_refs": [],
        },
    ]
    result = {
        **budget, "strategy": "FAIL_CLOSED_NO_HISTORY_COMPRESSION",
        "estimated_input_tokens": estimated, "prompt_estimated_tokens": prompt_tokens,
        "tool_schema_estimated_tokens": tool_tokens,
        "input_budget_tokens": input_limit,
        "utilization": round(estimated / input_limit, 4) if input_limit else 1.0,
    }
    metadata["context_budget"] = result
    metadata["context_blocks"] = blocks
    metadata.setdefault("summary_refs", [])
    metadata.setdefault("excluded_sources", [])
    return result
