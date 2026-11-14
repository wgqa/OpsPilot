"""Prepare or send the task-authorized D reference requests only.

The sender has no tool dispatcher. It writes the worst-case reservation and
logical request counter before each one-shot HTTPS call. No retries are made.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import pathlib
import re
import subprocess
import sys
import urllib.error
import urllib.request
from decimal import Decimal
from typing import Any
from urllib.parse import urlparse

from langchain_core.messages import messages_from_dict
from langchain_openai.chat_models.base import _convert_message_to_dict


ROOT = pathlib.Path(__file__).resolve().parents[3]
EVIDENCE = pathlib.Path(__file__).resolve().parent
PHASE_A = ROOT / "docs/evidence/r2-ar04-long-context-journey-01"
ENV_FILE = ROOT.parent.parent / ".env"
API_URL = "https://api.deepseek.com/chat/completions"
BASE_SHA = "fd941299966f6cc54ae35be3102f071d2be29acc"
BRANCH = "codex/r2-ar04-live-semantic-pilot-01"
MODEL_ALIAS = "deepseek-flash"
MODEL_IDENTITY_PREFIX = "deepseek-v4.1-flash"
EXPECTED_TOOL_DIGEST = "f6c75eaa3b2a807c95258e0df2428d046b4fe545d5a5a15a83384d3880415c12"
QUESTION_IDS = ["Q02", "Q03", "Q06", "Q07", "Q08", "Q10", "Q12"]
GROUPS = ["A", "B", "C", "D"]
INPUT_RATE = Decimal("0.30")
OUTPUT_RATE = Decimal("1.20")
HARD_CAP_USD = Decimal("0.50")
REQUEST_CAP = 56
DIRECT_D_CAP = 7
D_INPUT_CAP = 60000
MAX_OUTPUT = 512


def canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def digest(value: str | bytes) -> str:
    raw = value.encode("utf-8") if isinstance(value, str) else value
    return hashlib.sha256(raw).hexdigest()


def read_env_file(path: pathlib.Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        values[key.strip()] = value
    return values


def write_json(path: pathlib.Path, value: Any) -> None:
    temp = path.with_name(path.name + ".tmp")
    with temp.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temp, path)


def append_gzip_record(record: dict[str, Any]) -> None:
    with gzip.open(EVIDENCE / "LIVE_REQUESTS.jsonl.gz", "at", encoding="utf-8", newline="\n") as handle:
        handle.write(canonical(record) + "\n")


def load_d_inputs() -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    questions_doc = json.loads((PHASE_A / "QUESTIONS.json").read_text(encoding="utf-8"))
    questions = {item["id"]: item for item in questions_doc["questions"]}
    phase_rows = [json.loads(line) for line in gzip.open(PHASE_A / "MODEL_REQUESTS.jsonl.gz", "rt", encoding="utf-8")]
    inputs: dict[str, dict[str, Any]] = {}
    audit: dict[str, Any] = {}
    errors: list[str] = []
    for qid in QUESTION_IDS:
        question = questions.get(qid)
        matches = [row for row in phase_rows if row.get("group") == "D"
                   and row.get("question_id") == qid
                   and not str(row.get("logical_key", "")).startswith("context-compression:")]
        if question is None or len(matches) != 1:
            errors.append(f"{qid}: frozen prompt or unique D answer input is missing")
            continue
        source_row = matches[0]
        try:
            source_request = json.loads(source_row["request_json"])
            prompt = str(question["prompt_text"])
            gold_json = canonical(question["gold"])
            rules_json = canonical(question.get("required_fact_groups", []))
            current = [item["data"] for item in source_request.get("messages", [])
                       if str(item.get("data", {}).get("id") or "").startswith("opspilot-current:")]
            messages = [_convert_message_to_dict(message)
                        for message in messages_from_dict(source_request["messages"])]
            context_budget = source_request["context_budget"]
            tool_digest = digest(canonical(source_request["tools"]))
            has_summary = any(
                "opspilot-summary:" in str(item.get("data", {}).get("id", ""))
                or "HISTORICAL SESSION SUMMARY" in str(item.get("data", {}).get("content", ""))
                for item in source_request["messages"]
            )
            historical_tool_calls = sum(len(item.get("tool_calls", [])) for item in messages)
            if gold_json in source_row["request_json"] or rules_json in source_row["request_json"]:
                errors.append(f"{qid}: Gold or scoring groups appear in the frozen request")
            if len(current) != 1 or current[0].get("content") != prompt:
                errors.append(f"{qid}: current prompt does not exactly match frozen prompt")
            if has_summary:
                errors.append(f"{qid}: D input contains a summary")
            if len(messages) - 2 != 29:
                errors.append(f"{qid}: D input does not contain exactly 29 history messages")
            if historical_tool_calls:
                errors.append(f"{qid}: D input contains a pending historical tool call")
            if tool_digest != EXPECTED_TOOL_DIGEST:
                errors.append(f"{qid}: tool schema digest drift")
            if (context_budget.get("context_window_tokens") != 65536
                    or context_budget.get("input_budget_tokens") != 60000
                    or int(context_budget.get("estimated_input_tokens") or 0) > D_INPUT_CAP):
                errors.append(f"{qid}: D budget or estimate is outside the frozen envelope")
            provider_request = {
                "model": MODEL_ALIAS,
                "messages": messages,
                "tools": source_request["tools"],
                "tool_choice": "auto",
                "temperature": 0,
                "max_tokens": MAX_OUTPUT,
                "thinking": {"type": "disabled"},
                "stream": False,
            }
            manifest = {
                "source_request_sha256": digest(source_row["request_json"]),
                "selected_message_ids": source_request.get("selected_message_ids", []),
                "source_refs": source_request.get("source_refs", []),
                "context_blocks": source_request.get("context_blocks", []),
                "excluded_sources": source_request.get("excluded_sources", []),
                "tool_result_projections": source_request.get("tool_result_projections", []),
                "phase_a_fixture_status": source_row.get("status"),
                "evidence_level": source_row.get("evidence_level"),
            }
            inputs[qid] = {
                "question": question,
                "source_request": source_request,
                "provider_request": provider_request,
                "manifest": manifest,
                "estimated_input_tokens": int(context_budget["estimated_input_tokens"]),
                "request_sha256": digest(canonical(provider_request)),
                "prompt_sha256": digest(prompt),
                "gold_sha256": digest(gold_json),
                "tool_schema_sha256": tool_digest,
                "history_message_count": len(messages) - 2,
            }
            audit[qid] = {
                "source_fixture_request_sha256": manifest["source_request_sha256"],
                "provider_request_sha256": inputs[qid]["request_sha256"],
                "prompt_sha256": inputs[qid]["prompt_sha256"],
                "offline_gold_sha256": inputs[qid]["gold_sha256"],
                "estimated_input_tokens": inputs[qid]["estimated_input_tokens"],
                "input_limit_tokens": D_INPUT_CAP,
                "context_window_tokens": 65536,
                "message_count_including_system_and_question": len(messages),
                "history_message_count": len(messages) - 2,
                "gold_and_scoring_groups_absent": gold_json not in source_row["request_json"] and rules_json not in source_row["request_json"],
                "current_prompt_exact": len(current) == 1 and current[0].get("content") == prompt,
                "summary_present": has_summary,
                "tool_schema_sha256": tool_digest,
                "tool_schema_matches_frozen_phase_a": tool_digest == EXPECTED_TOOL_DIGEST,
                "prior_message_tool_calls": sum(len(item.get("tool_calls", [])) for item in messages),
            }
        except Exception as exc:
            errors.append(f"{qid}: offline input validation raised {type(exc).__name__}")
    if set(inputs) != set(QUESTION_IDS):
        errors.append("one or more D question inputs could not be prepared")
    return inputs, {"questions": audit, "errors": errors}


def blank_result_rows() -> list[dict[str, Any]]:
    rows = []
    for qid in QUESTION_IDS:
        for group in GROUPS:
            state = "BLOCKED_BEFORE_PROVIDER_SEND" if group in {"A", "B", "C"} else "NOT_STARTED"
            rows.append({
                "question_id": qid,
                "group": group,
                "strategy": {"A": "HYBRID", "B": "ROLLING_SUMMARY", "C": "RECENT_WINDOW", "D": "FULL_HISTORY_REFERENCE"}[group],
                "status": state,
                "evidence_level": "NO_LIVE_PROVIDER_EVIDENCE",
                "response": None,
                "score_category": None,
                "deterministic_checks": None,
                "manual_semantic_review": "NOT_REVIEWED_NO_RESPONSE",
                "provider_request_id": None,
                "response_model": None,
                "usage": None,
                "input_manifest_ref": None,
                "request_digest": None,
                "error": "Runtime Grant unavailable" if group in {"A", "B", "C"} else None,
            })
    return rows


def prepare() -> int:
    output_names = ["PREFLIGHT.json", "RESULTS.json", "COST_LEDGER.json", "LIVE_REQUESTS.jsonl.gz"]
    if any((EVIDENCE / name).exists() for name in output_names):
        print("REFUSED: evidence already exists; prepare never overwrites it")
        return 2
    phase_hashes = {
        "QUESTIONS.json": "ea3d6554eafa433d1617dc5a5ba9f140471f3cb95f8ae10bcd25b807a4e7afe2",
        "RESULTS.json": "4b04f3d574028099f13748091d4d421c7654b15bed4d25be13b40c413b8699c4",
        "HISTORY_SNAPSHOT.json": "356512f611b046a04e33506a0fb1a88c6a08af93517b2134125dd6771b282c16",
        "MODEL_REQUESTS.jsonl.gz": "96efd85b7d29d54938b1a4932321eff74bca7e8e56565c978f58a1e57d9a1792",
        "run_long_context_eval.py": "b2d5b1415c3759a5a8b1e0c1c33d406b61984e5914f8a7256b1ab25e3d89c2b0",
        "LIVE_EVAL_PROPOSAL.md": "729368f8a6b2e1d577bfbe1d0051878383ff9c7af7ecf6d4982299a8fd01c94e",
    }
    for name, expected in phase_hashes.items():
        actual = digest((PHASE_A / name).read_bytes())
        if actual != expected:
            print(f"REFUSED: frozen Phase A input digest changed: {name}")
            return 2
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    branch = subprocess.check_output(["git", "branch", "--show-current"], cwd=ROOT, text=True).strip()
    if head != BASE_SHA or branch != BRANCH:
        print("REFUSED: wrong Base or candidate branch")
        return 2
    inputs, input_audit = load_d_inputs()
    env = read_env_file(ENV_FILE)
    local_key = env.get("OPSPILOT_MODEL_API_KEY", "")
    if local_key:
        for qid, prepared in inputs.items():
            absent = local_key not in canonical(prepared["provider_request"])
            input_audit["questions"][qid]["local_credential_absent_from_request"] = absent
            if not absent:
                input_audit["errors"].append(f"{qid}: local credential appears in provider request body")
    endpoint = urlparse(env.get("OPSPILOT_MODEL_BASE_URL", ""))
    process_env_presence = {
        name: bool(os.environ.get(name)) for name in (
            "OPSPILOT_MODEL_API_KEY", "OPSPILOT_MODEL_NAME", "OPSPILOT_MODEL_BASE_URL",
            "OPSPILOT_MODEL_CONFIG_VERSION", "OPSPILOT_MODEL_PRICE_VERSION",
            "OPSPILOT_ASSISTANT_SERVICE_IDENTITY", "OPSPILOT_DB_PATH",
        )
    }
    no_d_errors = list(input_audit["errors"])
    d_ready = (
        bool(local_key)
        and env.get("OPSPILOT_MODEL_NAME") == MODEL_ALIAS
        and endpoint.scheme == "https" and endpoint.hostname == "api.deepseek.com"
        and not no_d_errors
    )
    preflight = {
        "schema_version": 1,
        "task": "R2-AR04-LIVE-SEMANTIC-PILOT-01",
        "status": "READY_DIRECT_EVAL_REFERENCE_ONLY" if d_ready else "BLOCKED_BEFORE_PROVIDER_SEND",
        "generated_before_any_provider_request": True,
        "provider_requests_at_preflight": 0,
        "base_sha": head,
        "required_base_sha": BASE_SHA,
        "branch": branch,
        "worktree_root_relative_to_repo": ".worktrees/ar04a-context-journey-01",
        "new_worktrees_created": 0,
        "preexisting_untracked_preserved": [".pytest-tmp/"],
        "phase_a_file_sha256": phase_hashes,
        "official_provider_check": {
            "provider": "DeepSeek official API",
            "api_host_verified_from_local_config": endpoint.scheme == "https" and endpoint.hostname == "api.deepseek.com",
            "model_alias_verified_from_local_config": env.get("OPSPILOT_MODEL_NAME") == MODEL_ALIAS,
            "model_alias": MODEL_ALIAS,
            "resolved_model_family_from_official_docs": "DeepSeek-V4.1-Flash-1017",
            "thinking": {"type": "disabled"},
            "temperature": 0,
            "max_tokens": MAX_OUTPUT,
            "verified_date": "2026-11-14",
            "sources": [
                "https://api-docs.deepseek.com/quick_start/pricing/",
                "https://api-docs.deepseek.com/api/create-chat-completion/",
                "https://api-docs.deepseek.com/guides/thinking_mode/",
                "https://api-docs.deepseek.com/api/list-models/",
            ],
        },
        "credential_handling": {
            "local_key_present_for_direct_d": bool(local_key),
            "key_value_read_into_evidence": False,
            "key_value_written_to_repository": False,
            "authorization_header_saved": False,
            "process_environment_presence": process_env_presence,
        },
        "runtime_grant_check": {
            "performed_for_abc": True,
            "grant_available_for_isolated_worktree": False,
            "worktree_env_file_present": (ROOT / ".env").is_file(),
            "worktree_default_runtime_db_present": (ROOT / ".runtime/opspilot.sqlite3").is_file(),
            "required_runtime_config_present_in_process": all(process_env_presence[name] for name in (
                "OPSPILOT_MODEL_NAME", "OPSPILOT_MODEL_BASE_URL", "OPSPILOT_MODEL_CONFIG_VERSION",
                "OPSPILOT_MODEL_PRICE_VERSION", "OPSPILOT_ASSISTANT_SERVICE_IDENTITY")),
            "grant_model_expiry_budget_tokens_permissions": "NOT_CHECKABLE_NO_BINDABLE_ISOLATED_GRANT",
            "abc_decision": "BLOCKED_BEFORE_PROVIDER_SEND",
            "grant_creation_attempted": False,
        },
        "input_checks": input_audit,
        "side_effect_controls": {
            "external_mcp_enabled": False,
            "business_action_enabled": False,
            "tool_dispatcher_in_direct_sender": False,
            "tool_call_response_policy": "record and stop; never execute",
            "live_answers_reused_as_history": False,
            "gold_or_scoring_rules_sent": False,
            "all_history_is_frozen_synthetic_wp3": True,
        },
        "request_limits": {
            "total_request_cap": REQUEST_CAP,
            "answer_request_cap": 28,
            "summary_request_cap": 28,
            "direct_d_reference_request_cap": DIRECT_D_CAP,
            "retry_policy": "none",
            "usd_hard_cap": float(HARD_CAP_USD),
            "input_token_upper_bound": 1008000,
            "output_token_upper_bound": 28672,
            "peak_no_cache_upper_cost_usd": 0.3368064,
            "peak_input_usd_per_million": float(INPUT_RATE),
            "peak_output_usd_per_million": float(OUTPUT_RATE),
            "direct_d_peak_upper_cost_usd": 0.1303008,
        },
        "direct_d_ready": d_ready,
        "direct_d_errors": no_d_errors,
    }
    write_json(EVIDENCE / "PREFLIGHT.json", preflight)
    with gzip.open(EVIDENCE / "LIVE_REQUESTS.jsonl.gz", "wt", encoding="utf-8", newline="\n"):
        pass
    ledger_requests = []
    for qid in QUESTION_IDS:
        for group in GROUPS:
            ledger_requests.append({
                "logical_request_id": f"{group}-{qid}-answer",
                "question_id": qid,
                "group": group,
                "kind": "answer",
                "status": "BLOCKED_BEFORE_PROVIDER_SEND" if group in {"A", "B", "C"} else "NOT_STARTED",
                "provider_send_count": 0,
                "reserved_usd": 0.0,
                "usage_cost_upper_bound_usd": 0.0,
                "request_digest": inputs[qid]["request_sha256"] if group == "D" and qid in inputs else None,
                "response_id": None,
                "response_model": None,
                "usage": None,
                "error": "no bindable Runtime Grant" if group in {"A", "B", "C"} else None,
            })
    ledger = {
        "schema_version": 1,
        "task": "R2-AR04-LIVE-SEMANTIC-PILOT-01",
        "status": "READY_DIRECT_EVAL_REFERENCE_ONLY" if d_ready else "BLOCKED_BEFORE_PROVIDER_SEND",
        "hard_usd_cap": float(HARD_CAP_USD),
        "peak_rates_usd_per_million": {"input_uncached": float(INPUT_RATE), "output": float(OUTPUT_RATE)},
        "authorized_request_cap": REQUEST_CAP,
        "summary_request_cap": 28,
        "answer_request_cap": 28,
        "direct_d_reference_request_cap": DIRECT_D_CAP,
        "theoretical_full_scope_token_upper_bound": {"input": 1008000, "output": 28672},
        "theoretical_full_scope_peak_cost_upper_bound_usd": 0.3368064,
        "direct_d_max_reserve_per_request_usd": 0.0186144,
        "direct_d_max_cost_upper_bound_usd": 0.1303008,
        "provider_requests_sent": 0,
        "provider_unknown_count": 0,
        "answer_requests_sent": 0,
        "summary_requests_sent": 0,
        "direct_d_requests_sent": 0,
        "actual_usage_cost_upper_bound_usd": 0.0,
        "active_reserved_usd": 0.0,
        "actual_billed_usd": None,
        "actual_billed_amount_source": "not available until account billing; usage-based upper estimate is maintained here",
        "requests": ledger_requests,
    }
    write_json(EVIDENCE / "COST_LEDGER.json", ledger)
    results = {
        "schema_version": 1,
        "task": "R2-AR04-LIVE-SEMANTIC-PILOT-01",
        "status": "READY_DIRECT_EVAL_REFERENCE_ONLY" if d_ready else "BLOCKED_BEFORE_PROVIDER_SEND",
        "base_sha": BASE_SHA,
        "phase_a_gold_source": "../r2-ar04-long-context-journey-01/QUESTIONS.json",
        "phase_a_history_source": "../r2-ar04-long-context-journey-01/HISTORY_SNAPSHOT.json",
        "planned_answer_slots": 28,
        "provider_requests_sent": 0,
        "live_semantic_answers_received": 0,
        "evidence_level": "NO_LIVE_PROVIDER_EVIDENCE_YET",
        "rows": blank_result_rows(),
    }
    write_json(EVIDENCE / "RESULTS.json", results)
    print(json.dumps({"preflight": preflight["status"], "direct_d_ready": d_ready,
                      "provider_requests": 0, "input_errors": no_d_errors}, ensure_ascii=True))
    return 0 if d_ready else 2


def current_request_row(results: dict[str, Any], qid: str) -> dict[str, Any]:
    return next(row for row in results["rows"] if row["group"] == "D" and row["question_id"] == qid)


def request_row(ledger: dict[str, Any], logical_id: str) -> dict[str, Any]:
    return next(row for row in ledger["requests"] if row["logical_request_id"] == logical_id)


def mark_later_d_not_sent(
    ledger: dict[str, Any], results: dict[str, Any], question_id: str, stop_reason: str,
) -> None:
    stop_index = QUESTION_IDS.index(question_id)
    for later_qid in QUESTION_IDS[stop_index + 1:]:
        slot = request_row(ledger, f"D-{later_qid}-answer")
        if slot["status"] == "NOT_STARTED":
            slot.update({"status": "BLOCKED_AFTER_STOP_CONDITION",
                         "error": f"not sent after {question_id}: {stop_reason}"})
        later_result = current_request_row(results, later_qid)
        if later_result["status"] == "NOT_STARTED":
            later_result.update({"status": "BLOCKED_AFTER_STOP_CONDITION",
                                 "error": f"not sent after {question_id}: {stop_reason}"})
    ledger["status"] = f"STOPPED_{stop_reason}"
    results["status"] = f"STOPPED_{stop_reason}_ABC_BLOCKED"
    results["stop_reason"] = stop_reason


def peak_cost(prompt_tokens: int, completion_tokens: int) -> Decimal:
    return (Decimal(prompt_tokens) * INPUT_RATE + Decimal(completion_tokens) * OUTPUT_RATE) / Decimal(1000000)


def send_direct_d() -> int:
    preflight = json.loads((EVIDENCE / "PREFLIGHT.json").read_text(encoding="utf-8"))
    if not preflight.get("direct_d_ready"):
        print("REFUSED: preflight did not clear D direct reference")
        return 2
    inputs, audit = load_d_inputs()
    if audit["errors"] or set(inputs) != set(QUESTION_IDS):
        print("REFUSED: frozen request checks no longer pass")
        return 2
    env = read_env_file(ENV_FILE)
    api_key = env.get("OPSPILOT_MODEL_API_KEY", "")
    endpoint = urlparse(env.get("OPSPILOT_MODEL_BASE_URL", ""))
    if (not api_key or env.get("OPSPILOT_MODEL_NAME") != MODEL_ALIAS
            or endpoint.scheme != "https" or endpoint.hostname != "api.deepseek.com"):
        print("REFUSED: local direct reference configuration is absent or mismatched")
        return 2
    results_path = EVIDENCE / "RESULTS.json"
    ledger_path = EVIDENCE / "COST_LEDGER.json"
    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    results = json.loads(results_path.read_text(encoding="utf-8"))
    if ledger["provider_requests_sent"] > REQUEST_CAP or ledger["direct_d_requests_sent"] > DIRECT_D_CAP:
        print("STOP: request counter already at cap")
        return 2
    observed_model: str | None = None
    for qid in QUESTION_IDS:
        logical_id = f"D-{qid}-answer"
        slot = request_row(ledger, logical_id)
        result_row = current_request_row(results, qid)
        if slot["status"] == "COMPLETE":
            observed_model = observed_model or slot.get("response_model")
            continue
        if slot["status"] != "NOT_STARTED":
            print(f"STOP: {logical_id} is already {slot['status']}; no retry")
            return 2
        if ledger["provider_requests_sent"] >= REQUEST_CAP or ledger["direct_d_requests_sent"] >= DIRECT_D_CAP:
            print("STOP: request cap reached")
            return 2
        reserve = peak_cost(D_INPUT_CAP, MAX_OUTPUT)
        current_estimate = Decimal(str(ledger["actual_usage_cost_upper_bound_usd"]))
        active_reserve = Decimal(str(ledger["active_reserved_usd"]))
        if current_estimate + active_reserve + reserve > HARD_CAP_USD:
            print("STOP: remaining hard budget cannot cover worst-case reservation")
            return 2
        source = inputs[qid]
        payload = source["provider_request"]
        payload_text = canonical(payload)
        if api_key in payload_text:
            print("STOP: local credential appeared in request body")
            return 2
        request_digest = digest(payload_text)
        if request_digest != slot["request_digest"]:
            print("STOP: logical request digest drift; no request sent")
            return 2

        # Persist the counter and worst-case reservation before the only send.
        slot.update({"status": "RESERVED_SENDING", "provider_send_count": 1,
                     "reserved_usd": float(reserve), "request_digest": request_digest})
        ledger["provider_requests_sent"] += 1
        ledger["answer_requests_sent"] += 1
        ledger["direct_d_requests_sent"] += 1
        ledger["active_reserved_usd"] = float(active_reserve + reserve)
        write_json(ledger_path, ledger)
        append_gzip_record({
            "event": "REQUEST_RESERVED_AND_SENT_ONCE",
            "logical_request_id": logical_id,
            "request_digest": request_digest,
            "request": payload,
            "source_manifest": source["manifest"],
            "provider_url": API_URL,
            "headers_saved": ["Content-Type"],
            "authorization_header_saved": False,
            "reservation_usd_peak_no_cache": float(reserve),
            "input_token_cap": D_INPUT_CAP,
            "output_token_cap": MAX_OUTPUT,
            "evidence_level": "DIRECT_EVAL_REFERENCE_PENDING_PROVIDER_RESPONSE",
        })
        http_request = urllib.request.Request(
            API_URL,
            data=payload_text.encode("utf-8"),
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(http_request, timeout=90) as response:
                status_code = response.status
                raw_body = response.read()
        except urllib.error.HTTPError as exc:
            status_code = exc.code
            raw_body = exc.read()
        except Exception as exc:
            # A transport exception after invoking urlopen has unknown send state.
            slot.update({"status": "UNKNOWN", "error": type(exc).__name__, "response_id": None})
            ledger["provider_unknown_count"] += 1
            write_json(ledger_path, ledger)
            result_row.update({"status": "UNKNOWN", "error": type(exc).__name__,
                               "evidence_level": "REAL_PROVIDER_SEND_STATE_UNKNOWN"})
            results["provider_requests_sent"] = ledger["provider_requests_sent"]
            mark_later_d_not_sent(ledger, results, qid, "UNKNOWN_SEND_STATE")
            write_json(results_path, results)
            write_json(ledger_path, ledger)
            append_gzip_record({"event": "UNKNOWN", "logical_request_id": logical_id,
                                "request_digest": request_digest, "error_class": type(exc).__name__,
                                "retry": False, "reserved_usd_retained": float(reserve)})
            print(f"STOP: {logical_id} has UNKNOWN send state; no retry or later request")
            return 3

        raw_text = raw_body.decode("utf-8", errors="replace")
        if api_key in raw_text:
            raw_text = raw_text.replace(api_key, "[REDACTED_LOCAL_API_KEY]")
            status_code = status_code
            security_echo = True
        else:
            security_echo = False
        try:
            response_json = json.loads(raw_text)
        except json.JSONDecodeError:
            response_json = None
        event = {
            "event": "PROVIDER_RESPONSE",
            "logical_request_id": logical_id,
            "request_digest": request_digest,
            "http_status": status_code,
            "response": response_json if response_json is not None else raw_text,
            "response_sha256": digest(raw_body),
            "api_key_echo_detected_and_redacted": security_echo,
            "evidence_level": "REAL_PROVIDER",
        }
        append_gzip_record(event)
        if status_code != 200 or response_json is None:
            slot.update({"status": "PROVIDER_ERROR", "error": f"HTTP_{status_code}", "response_id": None})
            # Keep the maximum reservation: error responses may have unknown billing.
            results["provider_requests_sent"] = ledger["provider_requests_sent"]
            mark_later_d_not_sent(ledger, results, qid, "PROVIDER_ERROR")
            write_json(ledger_path, ledger)
            result_row.update({"status": "PROVIDER_ERROR", "error": f"HTTP_{status_code}",
                               "evidence_level": "REAL_PROVIDER_ERROR"})
            write_json(results_path, results)
            print(f"STOP: provider error for {logical_id}; no retry or later request")
            return 3

        response_id = response_json.get("id")
        response_model = str(response_json.get("model") or "")
        usage = response_json.get("usage")
        choices = response_json.get("choices") or []
        if not isinstance(usage, dict) or not isinstance(usage.get("prompt_tokens"), int) or not isinstance(usage.get("completion_tokens"), int):
            slot.update({"status": "USAGE_INCOMPLETE", "response_id": response_id,
                         "response_model": response_model, "error": "provider usage missing required token counts"})
            write_json(ledger_path, ledger)
            result_row.update({"status": "USAGE_INCOMPLETE", "provider_request_id": response_id,
                               "response_model": response_model, "usage": usage,
                               "evidence_level": "REAL_PROVIDER_USAGE_INCOMPLETE"})
            results["provider_requests_sent"] = ledger["provider_requests_sent"]
            mark_later_d_not_sent(ledger, results, qid, "USAGE_INCOMPLETE")
            write_json(ledger_path, ledger)
            write_json(results_path, results)
            print(f"STOP: usage missing for {logical_id}; no later request")
            return 3
        usage_cost = peak_cost(usage["prompt_tokens"], usage["completion_tokens"])
        active_reserve = Decimal(str(ledger["active_reserved_usd"])) - reserve
        cumulative = Decimal(str(ledger["actual_usage_cost_upper_bound_usd"])) + usage_cost
        ledger["active_reserved_usd"] = float(max(active_reserve, Decimal("0")))
        ledger["actual_usage_cost_upper_bound_usd"] = float(cumulative)
        slot.update({"status": "RESPONSE_RECEIVED", "reserved_usd": 0.0,
                     "usage_cost_upper_bound_usd": float(usage_cost), "response_id": response_id,
                     "response_model": response_model, "usage": usage,
                     "estimated_input_tokens": usage["prompt_tokens"],
                     "estimated_output_tokens": usage["completion_tokens"]})
        result_row.update({"provider_request_id": response_id, "response_model": response_model,
                           "usage": usage, "evidence_level": "REAL_PROVIDER",
                           "request_digest": request_digest,
                           "input_manifest_ref": {"file": "LIVE_REQUESTS.jsonl.gz",
                                                   "source_manifest_digest": digest(canonical(source["manifest"]))},
                           "source_refs": source["manifest"]["source_refs"],
                           "selected_message_ids": source["manifest"]["selected_message_ids"],
                           "context_blocks": source["manifest"]["context_blocks"],
                           "estimated_input_tokens_fixture": source["estimated_input_tokens"]})
        stop_reason: str | None = None
        if observed_model and response_model.lower() != observed_model.lower():
            stop_reason = "RESPONSE_MODEL_CHANGED"
        elif response_model.lower() != MODEL_ALIAS and not response_model.lower().startswith(MODEL_IDENTITY_PREFIX):
            stop_reason = "RESPONSE_MODEL_IDENTITY_UNCONFIRMED"
        if not choices:
            stop_reason = stop_reason or "NO_CHOICE"
        else:
            choice = choices[0]
            message = choice.get("message") or {}
            finish_reason = choice.get("finish_reason")
            tool_calls = message.get("tool_calls") or []
            response_text = message.get("content")
            result_row["response"] = response_text
            result_row["finish_reason"] = finish_reason
            if security_echo:
                stop_reason = stop_reason or "CREDENTIAL_ECHO_SECURITY_ANOMALY"
            elif tool_calls or finish_reason == "tool_calls":
                stop_reason = stop_reason or "UNEXPECTED_TOOL_CALL"
                result_row["returned_tool_calls"] = tool_calls
            elif finish_reason == "length" or usage["completion_tokens"] > MAX_OUTPUT:
                stop_reason = stop_reason or "OUTPUT_TRUNCATED_OR_OVER_LIMIT"
            elif finish_reason != "stop" or not isinstance(response_text, str):
                stop_reason = stop_reason or "INCOMPLETE_RESPONSE"
        if usage["prompt_tokens"] > D_INPUT_CAP or usage["completion_tokens"] > MAX_OUTPUT:
            stop_reason = stop_reason or "TOKEN_LIMIT_EXCEEDED"
        if cumulative + Decimal(str(ledger["active_reserved_usd"])) > HARD_CAP_USD:
            stop_reason = stop_reason or "USD_HARD_CAP_REACHED"
        slot["status"] = stop_reason or "COMPLETE"
        slot["error"] = stop_reason
        ledger["actual_billed_usd"] = None
        ledger["last_provider_model"] = response_model
        ledger["last_provider_response_id"] = response_id
        result_row["status"] = slot["status"]
        result_row["error"] = stop_reason
        result_row["manual_semantic_review"] = "PENDING_MAIN_AGENT_REVIEW" if not stop_reason else "NOT_REVIEWED_STOP_CONDITION"
        results["provider_requests_sent"] = ledger["provider_requests_sent"]
        results["live_semantic_answers_received"] = sum(
            row.get("group") == "D" and row.get("status") == "COMPLETE"
            and isinstance(row.get("response"), str)
            for row in results["rows"]
        )
        results["evidence_level"] = "REAL_PROVIDER" if results["live_semantic_answers_received"] else "NO_LIVE_PROVIDER_EVIDENCE"
        if stop_reason:
            mark_later_d_not_sent(ledger, results, qid, stop_reason)
        write_json(ledger_path, ledger)
        write_json(results_path, results)
        if stop_reason:
            print(f"STOP: {logical_id} triggered {stop_reason}; no later request")
            return 3
        observed_model = response_model
        print(json.dumps({"logical_request_id": logical_id, "status": "COMPLETE",
                          "request_id": response_id, "model": response_model,
                          "prompt_tokens": usage["prompt_tokens"],
                          "completion_tokens": usage["completion_tokens"],
                          "peak_cost_upper_bound_usd": float(usage_cost)}, ensure_ascii=True))
    ledger["status"] = "D_DIRECT_REFERENCE_COMPLETED"
    results["status"] = "D_DIRECT_REFERENCE_COMPLETED_ABC_BLOCKED"
    write_json(ledger_path, ledger)
    write_json(results_path, results)
    print("D direct reference completed; A/B/C remain blocked and were not sent")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["prepare", "send-direct-d"])
    args = parser.parse_args()
    if args.command == "prepare":
        return prepare()
    return send_direct_d()


if __name__ == "__main__":
    raise SystemExit(main())
