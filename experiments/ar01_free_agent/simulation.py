"""Deterministic TEST model, deliberately separate from the candidate loop.

This is a reactive simulation, not a real Provider, an intelligence metric, or
policy exposed to the production/candidate Agent. It never receives Gold labels.
"""
from __future__ import annotations

import asyncio
import json
import uuid
from typing import Any, Callable

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.utils.function_calling import convert_to_openai_tool
from pydantic import Field


def view(messages):
    question, facts, done, documents = "", [], [], []
    for message in messages:
        if isinstance(message, HumanMessage):
            try:
                body = json.loads(str(message.content))
            except ValueError:
                question = str(message.content)
                continue
            if "untrusted_user_inputs" in body:  # unchanged A prompt representation
                question = str(body["untrusted_user_inputs"][-1]["body"])
                facts = [{"type":e["type"],"facts":e["facts"],"id":e["id"]} for e in body["current_mcp_evidence"]]
                done = [a["tool_name"] for a in body["previous_actions"]]
                documents = body["retrieved_knowledge_method_only"]
        elif isinstance(message, ToolMessage):
            done.append(message.name)
            body = json.loads(str(message.content))
            value = body.get("tool_result", {})
            if "fact_type" in value:
                facts.append({"type":value["fact_type"],"facts":value["facts"],"id":body["observation"].get("evidence_id")})
            documents.extend(value.get("documents", []))
    return question, facts, done, documents


def answer(text, *, target=None, claim="NOT_APPLICABLE", partial=False, clarify=False):
    return AIMessage(content=json.dumps({"action":"clarify" if clarify else "answer",
        "result_state":"PARTIAL" if partial or clarify else "ANSWERED", "answer":text,
        "target_event_id":target,"processing_claim":claim}, ensure_ascii=False))


def call(tool_name, **args):
    return AIMessage(content="", tool_calls=[{"id":f"sim-tool-{uuid.uuid4()}",
        "name":tool_name,"args":{"reason":"deterministic test: resolve current user goal from observed facts",**args}}])


def reactive(messages):
    q, facts, done, documents = view(messages)
    by_type = {f["type"]:f for f in facts}
    source = " 来源：" + ", ".join(str(f["id"]) for f in facts) if facts else ""
    if "已知材料" in q or "刚才" in q:
        return answer("HTTP 202 只证明受理；处理完成需要同一事件当前接收处理事实。" + source)
    if "哪个" in q:
        return answer("请补充您所指的事件标识，我会在当前绑定订单内核对。", clarify=True)
    if "event-outside" in q:
        if "get_callback_transport_history" not in done:
            return call("get_callback_transport_history", event_id="event-outside")
        if "s3_order" not in by_type:
            return call("get_order_status")
        return answer("越域事件查询被可信工具拒绝，未取得该资源事实；本订单当前仍在处理中。"+source, partial=True)
    if "event-e1" in q:
        if "s3_transport_history" not in by_type:
            return call("get_callback_transport_history", event_id="event-e1")
        if "s3_receiver" not in by_type:
            return call("get_receiver_processing")
        receiver = by_type["s3_receiver"]["facts"]
        claim = receiver["status"] if receiver["event_id"] == "event-e1" else "UNKNOWN"
        return answer("同一事件的请求记录需分别核对；event-e1 当前处理状态为 " + claim + "，其他 Event 的成功不能替代它。"+source,
            target="event-e1",claim=claim)
    if "适用协议" in q:
        if "search_callback_knowledge" not in done:
            return call("search_callback_knowledge", query="202 receiver acknowledgement")
        if "s3_receiver" not in by_type:
            return call("get_receiver_processing")
        r = by_type["s3_receiver"]["facts"]
        refs = ",".join(f"{d['document_id']}@{d['version']}" for d in documents)
        return answer("协议只解释受理语义；实时接收状态是 " + r["status"] + "。协议来源：" + refs + source,
            target=r["event_id"],claim=r["status"])
    if "投递失败" in q:
        if "s3_delivery" not in by_type:
            return call("get_callback_delivery")
        d = by_type["s3_delivery"]["facts"]
        if d["receiver_http_status"] == 202:
            if "s3_receiver" not in by_type:
                return call("get_receiver_processing")
            r = by_type["s3_receiver"]["facts"]
            return answer("HTTP 202 排除了投递失败判断；当前同一事件仍是 " + r["status"] + "，不能称已完成。"+source,
                target=r["event_id"],claim=r["status"])
        if "load_callback_skill" not in done:
            return call("load_callback_skill", name="callback-delivery-triage")
        return answer("真实投递记录为 HTTP 503；排障方法可以指导后续核查，尚无本轮当前处理完成证据。"+source,
            target=d["event_id"],claim="UNKNOWN")
    if "s3_order" not in by_type:
        return call("get_order_status")
    return answer("订单当前状态为 " + by_type["s3_order"]["facts"]["body"]["status"] + "；HTTP 200 本身不表示处理完成。"+source)


class LocalModel(BaseChatModel):
    policy: Callable = Field(default=reactive, exclude=True)
    requests: list[Any] = Field(default_factory=list, exclude=True)
    bound_schemas: list[dict] = Field(default_factory=list, exclude=True)
    sleep_seconds: float = 0

    @property
    def _llm_type(self):
        return "ar01-deterministic-no-provider"

    def bind_tools(self, tools, **kwargs):
        self.bound_schemas = [convert_to_openai_tool(t) for t in tools]
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        self.requests.append(messages)
        return ChatResult(generations=[ChatGeneration(message=self.policy(messages))])

    async def _agenerate(self, messages, stop=None, run_manager=None, **kwargs):
        if self.sleep_seconds:
            await asyncio.sleep(self.sleep_seconds)
        return self._generate(messages, stop, run_manager, **kwargs)
