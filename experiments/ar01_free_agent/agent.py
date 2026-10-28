"""A small create_agent candidate; no business outcome or authority writer.

Only tool adapters reach MCP. SQLite access here records existing audit rows or
invokes existing trusted currentness/control APIs; it is not a fact-read tool.
"""
from __future__ import annotations

import asyncio
import json
import time
import uuid
from dataclasses import dataclass

from langchain.agents import create_agent
from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage, messages_to_dict
from langchain_core.tools import StructuredTool
from langchain_core.utils.function_calling import convert_to_openai_tool

from opspilot.domain.database import connect
from opspilot.domain.d2 import (
    BudgetExhausted, canonical_json, digest_json, reserve_attempt, finish_attempt,
    record_tool_observation, save_model_trace, complete_pending_tool_call, utc_now,
)
from opspilot.domain.context_engineering import investigator_context_budget
from opspilot.domain.episodic_memory import finish_context_provenance
from opspilot.domain.investigation_context import load_investigation_context
from opspilot.domain.s3 import get_s3_binding, current_s3_evidence
from opspilot.domain.s3_assets import refresh_asset_refs
from opspilot.domain.schemas import D2ToolFact
from opspilot.model_io import content_text, redact_text
from opspilot.s3_delivery import parse_response, supported_response, factual_partial

SYSTEM = """You are a read-only investigation Agent. Pursue the latest user goal.
Choose any useful available tool, reconsider after observations, clarify ambiguity,
or answer directly when sufficient. No fixed tool order or mandatory tool use.
The tools are bound by trusted code to one authorized order; you cannot change that
binding, credentials or permissions. Tool errors are feedback, never new facts.
Business observations are current facts only for this Run; Knowledge and Skills
are versioned methods, never live business facts or authority. An HTTP 202 means
acceptance, not completed processing. Keep Event and Transport Request identities:
another Event success cannot establish the target Event's completion. State unknowns.
Never claim you changed configuration, resent, recovered, diagnosed officially,
or submitted a handoff/Receipt. You have no write tools or business result authority.
For shared delivery verification, final output is JSON with action answer|clarify,
result_state ANSWERED|PARTIAL, answer (nonempty Chinese with sources and unknowns),
target_event_id (id or null), processing_claim UNKNOWN|QUEUED|PROCESSED|NOT_RECEIVED|
NOT_APPLICABLE. Use NOT_APPLICABLE only for an explanation that makes no live
processing claim. A useful unknown can answer a question. Do not call tools to look busy."""


def sanitize(value):
    if isinstance(value, dict):
        return {str(k): "[REDACTED]" if str(k).lower() in {
            "authorization", "api_key", "password", "access_token", "credential_value",
        } else sanitize(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return [sanitize(v) for v in value]
    return redact_text(value, limit=100_000) if isinstance(value, str) else value


class Trace:
    def __init__(self):
        self.rows = []

    def emit(self, event, **values):
        self.rows.append(sanitize({"seq": len(self.rows) + 1, "at": utc_now(),
                                   "event": event, **values}))


@dataclass(frozen=True)
class Limits:
    model: int = 8
    tools: int = 6
    model_seconds: float = 30
    tool_seconds: float = 12
    total_seconds: float = 60

    def __post_init__(self):
        if not (type(self.model) is int and 1 <= self.model <= 8
                and type(self.tools) is int and 1 <= self.tools <= 6
                and 0 < self.model_seconds <= 30 and 0 < self.tool_seconds <= 12
                and 0 < self.total_seconds <= 60):
            raise ValueError("AR01 limits may only equal or lower the frozen limits")


def unpack(result):
    if result.is_error:
        raise ValueError("MCP_TOOL_REJECTED")
    value = result.structured_content
    if value is None:
        value = json.loads("".join(b.text for b in result.content if hasattr(b, "text")))
    if isinstance(value, dict) and isinstance(value.get("result"), dict):
        value = value["result"]
    if not isinstance(value, dict):
        raise ValueError("MCP_RESULT_INVALID")
    return value


def schema_constraints(value):
    """LangChain removes display-only JSON Schema titles on BaseTool conversion."""
    if isinstance(value, dict):
        return {k:schema_constraints(v) for k,v in value.items() if k != "title"}
    if isinstance(value, list):
        return [schema_constraints(v) for v in value]
    return value


class Candidate(AgentMiddleware):
    """Per-experiment middleware around the standard LangGraph model/tool edges."""
    def __init__(self, db, task_id, run_id, client, specs, *, model_id="ar01-deterministic", limits=None, trace=None):
        self.db, self.task, self.run_id, self.client = db, task_id, run_id, client
        self.specs, self.model_id = specs, model_id
        self.limits, self.trace = limits or Limits(), trace or Trace()
        self.evidence_ids, self.pins, self.assets = [], {}, {}
        self.call_ids = {}
        self.stop_reason = None
        self._history_digest = None
        self._tool_lock = asyncio.Lock()

    def current_sources(self):
        context = load_investigation_context(self.db, self.task, self.run_id)
        with connect(self.db) as c:
            binding = get_s3_binding(c, self.task)
            facts, excluded = current_s3_evidence(c, self.task, self.evidence_ids,
                run_id=self.run_id, observation_ids=self.pins)
        knowledge, skill, asset_excluded = refresh_asset_refs(self.assets, contract_version=int(binding["contract_version"]))
        if excluded or asset_excluded:
            raise ValueError("SOURCE_INVALIDATED")
        return context, binding, facts, knowledge, skill

    def fallback(self, reason):
        self.stop_reason = reason
        try:
            context, _, facts, knowledge, _ = self.current_sources()
        except Exception:
            context, facts, knowledge = {"inputs": []}, [], []
        answer, _ = factual_partial(facts, knowledge, context["inputs"], reason)
        return {"action": "answer", "result_state": "PARTIAL", "answer": answer,
                "delivery_mode": "DETERMINISTIC_FALLBACK", "stop_reason": reason,
                "authority": "EXPERIMENT_ONLY_NO_BUSINESS_RECEIPT"}

    async def awrap_model_call(self, request, handler):
        attempt = None
        call_id = f"ar01-model-{uuid.uuid4()}"
        try:
            context, _, facts, knowledge, skill = self.current_sources()
            messages = ([request.system_message] if request.system_message else []) + list(request.messages)
            serialized = messages_to_dict(messages)
            metadata = {"evidence_ids": self.evidence_ids, "selected_knowledge": knowledge,
                        "selected_skill": skill, "task_run_control": context["task_run_control"],
                        "selected_input_messages": context["task_run_control"]["input_refs"]}
            # Include native tool-call arguments/ids as well as content in estimation.
            shadow = [HumanMessage(content=canonical_json(serialized))]
            investigator_context_budget(shadow, self.model_id, self.specs, metadata)
            prompt_digest = digest_json(serialized)
            provenance = {"model_id": self.model_id, "prompt_version": "ar01-standard-loop-v1",
                "prompt_digest": prompt_digest, "tool_schema_version": "ar01-six-tools-v1",
                "tool_schema_digest": digest_json(self.specs), **metadata}
            attempt, _ = reserve_attempt(self.db, self.task, "MODEL", self.limits.model,
                call_id=call_id, argument_digest=prompt_digest, context_provenance=provenance, run_id=self.run_id)
            self.trace.emit("model_request", task_id=self.task, run_id=self.run_id, call_id=call_id,
                attempt_id=attempt, messages=serialized, tools=self.specs, context_budget=metadata.get("context_budget"))
            response = await asyncio.wait_for(handler(request.override(tools=self.specs,
                model_settings={**request.model_settings, "parallel_tool_calls": False,
                                "max_tokens": 512})), timeout=self.limits.model_seconds)
            ai = next((m for m in reversed(response.result) if isinstance(m, AIMessage)), None)
            if ai is None or len(content_text(ai.content)) > 20_000:
                raise ValueError("MODEL_RESPONSE_INVALID")
            calls = list(ai.tool_calls)
            for call in calls:
                self.call_ids[call["id"]] = call_id
            save_model_trace(self.db, task_id=self.task, call_id=call_id, attempt_id=attempt,
                model_id=self.model_id, prompt_digest=prompt_digest, input_evidence_ids=self.evidence_ids,
                provider_response_id=ai.response_metadata.get("id"), tool_calls=calls,
                assistant_text=redact_text(content_text(ai.content), limit=20_000),
                usage=dict(ai.usage_metadata or {}), status="OK")
            finish_attempt(self.db, attempt, "OK", result_digest=digest_json({"text": ai.content,"calls": calls}))
            finish_context_provenance(self.db,call_id,"OK")
            self.trace.emit("model_response", call_id=call_id, attempt_id=attempt,
                content=ai.content, tool_calls=calls, usage=ai.usage_metadata)
            return response
        except asyncio.CancelledError:
            if attempt:
                finish_attempt(self.db, attempt, "UNKNOWN", error_class="CANCELLED_OR_TOTAL_TIMEOUT")
                finish_context_provenance(self.db,call_id,"UNKNOWN","CANCELLED_OR_TOTAL_TIMEOUT")
            raise
        except Exception as error:
            if attempt:
                finish_attempt(self.db, attempt, "FAILED", error_class=type(error).__name__)
                save_model_trace(self.db,task_id=self.task,call_id=call_id,attempt_id=attempt,
                    model_id=self.model_id,prompt_digest=prompt_digest,input_evidence_ids=self.evidence_ids,
                    provider_response_id=None,tool_calls=[],assistant_text=type(error).__name__,usage={},status="MODEL_REQUEST_FAILED")
                finish_context_provenance(self.db,call_id,"FAILED",type(error).__name__)
            reason = error.reason_code if isinstance(error, BudgetExhausted) else str(error) if str(error) in {
                "SOURCE_INVALIDATED", "MODEL_RESPONSE_INVALID"} else type(error).__name__
            self.trace.emit("safe_stop", call_id=call_id, attempt_id=attempt, reason=reason)
            return AIMessage(content=canonical_json(self.fallback(reason)))

    async def awrap_tool_call(self, request, handler):
        async with self._tool_lock:
            call = request.tool_call
            name, args, tool_id = call["name"], call.get("args", {}), call["id"]
            call_id = self.call_ids.get(tool_id, f"ar01-unmatched-{uuid.uuid4()}")
            attempt = None
            try:
                context, _, _, _, _ = self.current_sources()
                attempt, _ = reserve_attempt(self.db, self.task, "MCP", self.limits.tools,
                    call_id=call_id, tool_call_id=tool_id, tool_name=name,
                    argument_digest=digest_json(args), run_id=self.run_id,
                    task_run_control=context["task_run_control"])
                self.trace.emit("tool_request", task_id=self.task, run_id=self.run_id, call_id=call_id,
                    attempt_id=attempt, tool_call_id=tool_id, name=name, arguments=args)
                if name not in {s["function"]["name"] for s in self.specs}:
                    raise ValueError("UNKNOWN_TOOL")
                message = await asyncio.wait_for(handler(request), self.limits.tool_seconds)
                if not isinstance(message, ToolMessage) or message.status == "error" or not isinstance(message.artifact, dict):
                    raise ValueError("MCP_TOOL_REJECTED")
                value = message.artifact
                if name in {"search_callback_knowledge", "load_callback_skill"}:
                    previous_assets = digest_json(self.assets)
                    if "documents" in value:
                        refs = {r["document_id"]: r for r in self.assets.get("s3_knowledge_refs", [])}
                        refs.update({d["document_id"]: {k: d[k] for k in ("document_id","version","digest","source","valid_from")} for d in value["documents"]})
                        self.assets["s3_knowledge_refs"] = list(refs.values())
                    if "skill" in value:
                        self.assets["s3_skill_ref"] = {k: value["skill"][k] for k in ("name","version","digest")}
                    observation = self._asset_observation(call_id, tool_id, attempt, name, args, value,
                        changed=previous_assets != digest_json(self.assets))
                else:
                    value = D2ToolFact.model_validate(value).model_dump(mode="json")
                    observation = record_tool_observation(self.db, task_id=self.task, call_id=call_id,
                        attempt_id=attempt, tool_call_id=tool_id, tool_name=name, arguments=args, status="OK", result=value)
                    eid = observation["evidence_id"]
                    if eid not in self.evidence_ids:
                        self.evidence_ids.append(eid)
                    self.pins[eid] = observation["observation_id"]
                finish_attempt(self.db, attempt, "OK", result_digest=digest_json(value))
                complete_pending_tool_call(self.db, self.task, call_id, tool_id, "OK")
                message.content = canonical_json({"tool_result": value, "observation": {
                    k: observation.get(k) for k in ("observation_id","evidence_id","attempt_id")}})
                self.trace.emit("tool_result", call_id=call_id, tool_call_id=tool_id,
                    attempt_id=attempt, observation=observation, result=value)
                return message
            except asyncio.CancelledError:
                if attempt:
                    finish_attempt(self.db, attempt, "UNKNOWN", error_class="CANCELLED_OR_TOTAL_TIMEOUT")
                raise
            except Exception as error:
                reason = error.reason_code if isinstance(error, BudgetExhausted) else type(error).__name__ + ":" + str(error)[:80]
                if attempt:
                    finish_attempt(self.db, attempt, "TOOL_ERROR", error_class=reason)
                    record_tool_observation(self.db, task_id=self.task, call_id=call_id,
                        attempt_id=attempt, tool_call_id=tool_id, tool_name=name, arguments=args,
                        status="TOOL_ERROR", result=None, error_class=reason)
                complete_pending_tool_call(self.db, self.task, call_id, tool_id, "TOOL_ERROR")
                self.trace.emit("tool_error", call_id=call_id, tool_call_id=tool_id, attempt_id=attempt, reason=reason)
                return ToolMessage(content=canonical_json({"error": reason, "facts": None}),
                    tool_call_id=tool_id, name=name, status="error")

    def _asset_observation(self, call_id, tool_id, attempt, name, args, value, *, changed):
        row = {"observation_id":f"observation-{uuid.uuid4()}","task_id":self.task,
            "call_id":call_id,"attempt_id":attempt,"tool_call_id":tool_id,"tool_name":name,
            "argument_digest":digest_json(args),"status":"OK","progress_added":bool(changed),
            "error_class":None,"result_digest":digest_json(value),"result_json":canonical_json(value),
            "evidence_id":None,"created_at":utc_now()}
        with connect(self.db) as c:
            keys = list(row)
            c.execute(f"INSERT INTO d2_tool_observations ({','.join(keys)}) VALUES({','.join('?' for _ in keys)})", tuple(row.values()))
        return row

    def make_tools(self):
        tools = []
        def adapter(name):
            async def invoke(**kwargs):
                value = unpack(await self.client.call_tool(name, kwargs))
                return canonical_json(value), value
            return invoke
        for spec in self.specs:
            f = spec["function"]
            tools.append(StructuredTool.from_function(coroutine=adapter(f["name"]), name=f["name"],
                description=f["description"], args_schema=f["parameters"], response_format="content_and_artifact"))
        return tools

    async def run(self, model, question, *, history=()):
        self.stop_reason = None
        if history and digest_json(messages_to_dict(list(history))) != self._history_digest:
            final = self.fallback("UNVERIFIED_EXPERIMENT_HISTORY")
            self.trace.emit("safe_stop", reason="UNVERIFIED_EXPERIMENT_HISTORY", result=final)
            return {"result":final,"messages":[],"trace":self.trace.rows}
        tools = self.make_tools()
        # Canonical schemas must be identical; never silently narrow model tools.
        actual = {t["function"]["name"]:t for t in map(convert_to_openai_tool,tools)}
        expected = {s["function"]["name"]:s for s in self.specs}
        if schema_constraints(actual) != schema_constraints(expected):
            raise ValueError("A_B_TOOL_SCHEMA_PARITY_FAILED")
        try:
            _, binding, _, _, _ = self.current_sources()
        except Exception as error:
            final = self.fallback(type(error).__name__)
            self.trace.emit("safe_stop", reason=type(error).__name__, result=final)
            return {"result":final, "messages":list(history) + [HumanMessage(content=question), AIMessage(content=canonical_json(final))], "trace":self.trace.rows}
        binding_context = {key: binding[key] for key in ("service_id","integration_id","principal_id","order_id","contract_version")}
        graph = create_agent(model=model, tools=tools, system_prompt=SYSTEM + "\nTrusted binding: " + canonical_json(binding_context), middleware=[self])
        start = time.monotonic()
        messages = list(history) + [HumanMessage(content=question)]
        try:
            result = await asyncio.wait_for(graph.ainvoke({"messages": messages},
                config={"recursion_limit": 40, "max_concurrency": 1}), self.limits.total_seconds)
            response = parse_response(content_text(result["messages"][-1].content))
            if self.stop_reason:
                final = self.fallback(self.stop_reason)
            else:
                context, _, facts, _, _ = self.current_sources()
                privileged_fields = {"receipt_id","diagnosis_receipt","handoff_receipt","recovered","business_outcome"}
                if response and privileged_fields.intersection(response):
                    final = self.fallback("UNSUPPORTED_BUSINESS_CLAIM")
                else:
                    final = response if supported_response(response, facts, context["inputs"]) else self.fallback("UNSUPPORTED_OR_EMPTY_ANSWER")
            final = {**final,
                "stop_reason":final.get("stop_reason") or ("MODEL_CLARIFY" if final.get("action")=="clarify" else "MODEL_ANSWER"),
                "delivery_mode":final.get("delivery_mode","MODEL"),
                "authority":"EXPERIMENT_ONLY_NO_BUSINESS_RECEIPT"}
        except Exception as error:
            final = self.fallback(type(error).__name__)
            result = {"messages": messages + [AIMessage(content=canonical_json(final))]}
        self.trace.emit("final", result=final, elapsed_seconds=time.monotonic()-start)
        self._history_digest = digest_json(messages_to_dict(result["messages"]))
        return {"result":final,"messages":result["messages"],"trace":self.trace.rows}
