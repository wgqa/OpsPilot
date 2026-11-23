"""Offline SDK fixture shared by the frozen-depth Python journey and browser."""
from __future__ import annotations

import gzip
import importlib.util
import json
from pathlib import Path

import httpx
from langchain_openai import ChatOpenAI

from opspilot.domain.context_engineering import estimate_messages_tokens, estimate_text_tokens


spec = importlib.util.spec_from_file_location(
    "frozen_p002", Path(__file__).resolve().parent.parent / "p0-02-red-design-01" / "repro.py",
)
frozen = importlib.util.module_from_spec(spec)
spec.loader.exec_module(frozen)

NAMES = ("event", "protocol", "time", "report")
HTTP_202 = "HTTP 202 是什么意思？"
EXPLANATION = "HTTP 202 表示请求已被接受处理；处理结果仍待确认。"


class BridgeWire(frozen.Wire):
    def review_factory(self):
        return ChatOpenAI(
            model="deepseek-flash", api_key="offline-bridge-key", base_url="https://api.deepseek.com",
            extra_body={"max_tokens": 640, "thinking": {"type": "disabled"}},
            max_retries=0, include_response_headers=True,
            http_async_client=httpx.AsyncClient(transport=httpx.MockTransport(self.respond), trust_env=False),
            http_client=httpx.Client(transport=httpx.MockTransport(self.reject_sync), trust_env=False),
        )

    @staticmethod
    def reject_sync(_request):
        raise AssertionError("The offline bridge harness only permits async MockTransport.")

    async def respond(self, request):
        body = json.loads(await request.aread())
        messages = body["messages"]
        if messages[0]["content"].startswith("Review current Task investigation requirements"):
            scope = json.loads(messages[1]["content"])
            active = {item["slot"] for item in scope["active"]}
            dictionary = {
                **{text: (slot, "ADD") for slot, text in zip(NAMES, frozen.CONDITIONS)},
                frozen.HYPOTHESIS: ("time", "HYPOTHESIS"),
                frozen.FULL_DAY: ("time", "REPLACE"),
                frozen.WITHDRAW: ("report", "REVOKE"),
                **{text: ("time", "CONFLICT") for text in frozen.UNCONFIRMED},
            }
            rows = []
            for source in scope["history"]:
                intent = dictionary.get(source["text"])
                if intent and source["exact"]:
                    slot, action = intent
                    if action != "ADD" and action in {"REPLACE", "REVOKE"} and slot not in active:
                        continue
                    rows.append({"slot": slot, "action": action, "sequence": source["sequence"]})
            result = {"rows": rows, "needs_review": any(item["action"] == "CONFLICT" for item in rows)}
            return self._reply(body, "discovery", result)
        if messages[-1]["content"] == HTTP_202:
            return self._reply(body, "answer", EXPLANATION)
        return await super().respond(request)

    def _reply(self, request, phase, value):
        text = json.dumps(value, ensure_ascii=False) if isinstance(value, dict) else value
        input_tokens = estimate_messages_tokens(request["messages"])
        output_tokens = estimate_text_tokens(text)
        row = {**self.target, "phase": phase, "request": request, "mock_response": value,
               "sdk_message_token_estimate": input_tokens, "returned_content_token_estimate": output_tokens}
        self.calls.append(row)
        with gzip.open(self.output / "wire.jsonl.gz", "at", encoding="utf-8") as stream:
            stream.write(json.dumps(row, ensure_ascii=False) + "\n")
        return httpx.Response(200, json={
            "id": f"bridge-local-{len(self.calls)}", "object": "chat.completion", "created": 1,
            "model": "deepseek-flash",
            "choices": [{"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": text}}],
            "usage": {"prompt_tokens": input_tokens, "completion_tokens": output_tokens,
                      "total_tokens": input_tokens + output_tokens},
        })
