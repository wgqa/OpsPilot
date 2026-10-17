from __future__ import annotations

import json
import os
import re
import sys
from importlib.metadata import version

from langchain_openai import ChatOpenAI

from opspilot.config import DEFAULT_DB_PATH, MODEL_API_KEY, MODEL_BASE_URL, MODEL_NAME, database_path
from opspilot.domain.database import reset_fixture
from opspilot.tools.model_tools import get_demo_service_info


def emit(event: str, **fields: object) -> None:
    print(json.dumps({"event": event, **fields}, sort_keys=True, default=str))


def safe_error_details(error: Exception) -> dict[str, object]:
    details: dict[str, object] = {"exception_type": type(error).__name__}
    for name in ("status_code", "code", "type", "param"):
        value = getattr(error, name, None)
        if value is not None and isinstance(value, (str, int, float, bool)):
            details[name] = value

    body = getattr(error, "body", None)
    if isinstance(body, dict):
        provider_error = body.get("error", body)
        if isinstance(provider_error, dict):
            for name in ("code", "type", "param", "message"):
                value = provider_error.get(name)
                if value is not None and isinstance(value, (str, int, float, bool)):
                    details.setdefault(name, value)

    message = getattr(error, "message", None)
    if isinstance(message, str) and message:
        details.setdefault("message", message)
    else:
        error_text = str(error)
        if error_text:
            details.setdefault("message", error_text)

    api_key = os.environ.get(MODEL_API_KEY, "")
    base_url = os.environ.get(MODEL_BASE_URL, "")
    for secret in (api_key, base_url):
        if secret:
            details = {
                key: value.replace(secret, "[REDACTED]") if isinstance(value, str) else value
                for key, value in details.items()
            }
    if isinstance(details.get("message"), str):
        details["message"] = re.sub(
            r"(?i)(bearer\s+)[^\s'\",}]+|sk-[A-Za-z0-9_-]{8,}",
            "[REDACTED]",
            details["message"],
        )[:300]
    nested = getattr(error, "exceptions", None)
    if isinstance(nested, tuple) and nested:
        details["causes"] = [safe_error_details(item) for item in nested[:4] if isinstance(item, Exception)]
    return details


def run_smoke() -> int:
    api_key = os.environ.get(MODEL_API_KEY, "")
    model_name = os.environ.get(MODEL_NAME, "")
    base_url = os.environ.get(MODEL_BASE_URL, "")
    if not api_key or not model_name:
        missing = [name for name, value in ((MODEL_API_KEY, api_key), (MODEL_NAME, model_name)) if not value]
        emit("blocked_missing_model_configuration", missing_variables=missing)
        return 2

    db_path = database_path(os.environ.get("OPSPILOT_DB_PATH", str(DEFAULT_DB_PATH)))
    reset_fixture(db_path, "S1_POS")
    llm = ChatOpenAI(
        model=model_name,
        api_key=api_key,
        base_url=base_url or None,
        timeout=30,
        max_retries=0,
    )
    llm_with_tool = llm.bind_tools(
        [get_demo_service_info],
        tool_choice="auto",
        parallel_tool_calls=False,
    )
    try:
        response = llm_with_tool.invoke(
            "You must call get_demo_service_info exactly once with service_id='orders-demo'. "
            "Do not answer from memory; use the tool and return its non-secret observation."
        )
    except Exception as error:
        emit("model_request_failed", provider="openai-compatible-chat-completions",
             endpoint_category="OpenAI-compatible endpoint", model_id=model_name,
             error=safe_error_details(error))
        return 1

    calls = response.tool_calls
    if len(calls) != 1 or calls[0].get("name") != "get_demo_service_info":
        emit("model_tool_call_contract_failed", call_count=len(calls), tool_names=[c.get("name") for c in calls])
        return 1

    call = calls[0]
    try:
        observation_text = get_demo_service_info.invoke(call["args"])
        observation = json.loads(observation_text) if isinstance(observation_text, str) else observation_text
    except Exception as error:
        emit(
            "model_tool_execution_failed",
            tool_call_id=call.get("id"),
            tool_name=call.get("name"),
            error=safe_error_details(error),
        )
        return 1

    if not isinstance(observation, dict) or observation.get("service_id") != "orders-demo":
        emit("model_tool_observation_invalid", tool_call_id=call.get("id"), tool_name=call.get("name"))
        return 1

    emit(
        "model_tool_call_pass",
        provider="openai-compatible-chat-completions",
        endpoint_category="OpenAI-compatible endpoint",
        model_id=model_name,
        versions={
            "langchain": version("langchain"),
            "langchain-openai": version("langchain-openai"),
        },
        tool_call_id=call.get("id"),
        tool_name=call["name"],
        tool_arguments=call["args"],
        argument_schema=get_demo_service_info.args_schema.model_json_schema(),
        observation=observation,
    )
    return 0


def main() -> int:
    return run_smoke()


if __name__ == "__main__":
    raise SystemExit(main())
