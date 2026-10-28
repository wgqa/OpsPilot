"""Optional shared LangChain adapter. Paid transport is disabled by default.

Only experiments import this module. The loopback factory cannot target another
host. No automatic model switch, request retry, parameter repair or billing reset.
"""
from __future__ import annotations

import asyncio
from dataclasses import asdict, dataclass
import json
import os
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import messages_to_dict
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_openai import ChatOpenAI
from pydantic import Field

from experiments.ar01_free_agent.agent import sanitize
from experiments.ar01_free_agent.provider_budget import BudgetStop, ExperimentBudget, REQUEST_WIRE_V1
from opspilot.config import ROOT, MODEL_API_KEY
from opspilot.domain.d2 import digest_json


class ProviderStopped(RuntimeError):
    pass


@dataclass(frozen=True)
class ProviderConfig:
    model: str = "deepseek-flash"
    base_url: str = "https://api.deepseek.com"
    thinking: str = "disabled"
    max_tokens: int = 512
    max_retries: int = 0
    timeout: int = 30
    parallel_tool_calls: bool = False
    stream: bool = False

    def __post_init__(self):
        expected=("deepseek-flash","https://api.deepseek.com","disabled",512,0,30,False,False)
        if tuple(asdict(self).values())!=expected or any(type(getattr(self,k)) is not int for k in
            ("max_tokens","max_retries","timeout")) or type(self.parallel_tool_calls) is not bool or type(self.stream) is not bool:
            raise ValueError("FROZEN_PROVIDER_CONFIGURATION_CHANGED")


ORDER=(("AR01-01","material"),("AR01-03","acknowledged"),("AR01-03","failed"),
       ("AR01-04","different-event"),("AR01-06","scope"))


def selected_cases():
    cases=json.loads((ROOT/"docs/evidence/ar-01/CASES.json").read_text(encoding="utf-8"))["cases"]
    return [next(c for c in cases if (c["id"],c["variant"])==key) for key in ORDER]


def safe_response(value):
    """Record returned text/tools/Usage but do not collect hidden reasoning."""
    if isinstance(value,dict):
        return {k:safe_response(v) for k,v in value.items() if k not in {"reasoning_content","reasoning"}}
    if isinstance(value,list): return [safe_response(v) for v in value]
    return sanitize(value)


class MeteredModel(BaseChatModel):
    sdk: Any = Field(exclude=True)
    budget: Any = Field(exclude=True)
    trace: Any = Field(exclude=True)
    config: ProviderConfig
    group_label: str
    expected_specs: list[dict] = Field(exclude=True)
    # Shared by bound clones and httpx hooks; Pydantic must not copy this map.
    runtime: Any = Field(exclude=True)
    requests: list = Field(default_factory=list,exclude=True)
    bound_schemas: list = Field(default_factory=list,exclude=True)
    settings: dict = Field(default_factory=dict,exclude=True)

    @property
    def _llm_type(self): return "ar01-rm01-metered-openai-compatible"

    def bind_tools(self,tools,**kwargs):
        # Both callers supply the original MCP schema dicts; do not normalize them.
        self.trace.emit("provider_binding",tools=tools,settings=kwargs)
        if tools!=self.expected_specs and tools!=[]:
            raise ProviderStopped("ACTUAL_TOOL_SCHEMA_MISMATCH")
        self.bound_schemas[:]=tools
        # create_agent uses None for its unspecified tool policy. Resolve that
        # framework sentinel to the frozen auto policy, explicitly for both arms.
        if kwargs.get("tool_choice") is None:
            kwargs={**kwargs,"tool_choice":"auto"}
        return self.model_copy(update={"settings":{**kwargs,"tools":list(tools)}})

    def _generate(self,*args,**kwargs):
        raise ProviderStopped("SYNC_PROVIDER_CALL_DISABLED")

    async def _agenerate(self,messages,stop=None,run_manager=None,**kwargs):
        if stop is not None: raise ProviderStopped("UNFROZEN_STOP_PARAMETER")
        settings={**self.settings,**kwargs}
        self.trace.emit("provider_invoke_settings",settings=settings)
        if set(settings)-{"tools","tool_choice","parallel_tool_calls","max_tokens"}:
            raise ProviderStopped("UNFROZEN_PROVIDER_PARAMETER")
        if settings.get("max_tokens",512)!=512 or settings.get("parallel_tool_calls",False) is not False or settings.get("tool_choice","auto")!="auto":
            raise ProviderStopped("FROZEN_PROVIDER_PARAMETER_CHANGED")
        specs=settings.get("tools",[])
        if specs not in ([],self.expected_specs): raise ProviderStopped("ACTUAL_TOOL_SCHEMA_MISMATCH")
        # The wrapper's shared settings map to the vendor's documented max_tokens
        # via extra_body. Installed ChatOpenAI otherwise renames max_tokens.
        sdk_settings={"parallel_tool_calls":False}
        if specs: sdk_settings.update(tools=specs,tool_choice="auto")
        logical=f"{self.group_label}/{len(self.requests)+1}"
        payload={"messages":messages_to_dict(messages),"tools":specs,"config":asdict(self.config)}
        if self.budget.requestwise:
            # Installed SDK preparation, before I/O. Its extra_body is merged by
            # OpenAI's request builder; verify this exact semantic body again at
            # the HTTP edge. No heuristic tokenizer bound is used for pricing.
            payload=self.sdk._get_request_payload(messages,**sdk_settings)
            extra=payload.pop("extra_body",{})
            if set(extra)&set(payload): raise ProviderStopped("AMBIGUOUS_EXTRA_BODY_OVERRIDE")
            payload.update(extra)
            expected=self.runtime.get("authorized_wire_digest")
            if expected and digest_json(payload)!=expected:
                raise ProviderStopped("PROBE_AUTHORIZED_WIRE_CHANGED")
        key=self.budget.reserve(logical,payload)
        self.runtime.update(reservation=key,raw=None,request_id=None,expected_tools=specs)
        self.requests.append({"logical_key":logical,"reservation_id":key})
        try:
            ai=await asyncio.wait_for(self.sdk.ainvoke(messages,**sdk_settings),self.config.timeout)
            raw=self.runtime["raw"]
            if not isinstance(raw,dict): raise ProviderStopped("MISSING_RAW_PROVIDER_RESPONSE")
            # Preserve real Usage even when the response contract later fails.
            self.budget.settle(key,raw.get("usage"))
            if not isinstance(raw.get("id"),str) or not raw["id"] or (
                not self.budget.requestwise and not self.runtime["request_id"]):
                raise ProviderStopped("MISSING_COMPLETION_OR_REQUEST_ID")
            if raw.get("model") not in {self.config.model,"DeepSeek-V4.1-Flash-1017"}:
                raise ProviderStopped("UNEXPECTED_RESPONSE_MODEL")
            self.budget.pin_backend(raw.get("model"),raw.get("system_fingerprint"))
            choices=raw.get("choices")
            if not isinstance(choices,list) or len(choices)!=1 or choices[0].get("finish_reason") not in {"stop","tool_calls"}:
                raise ProviderStopped("INCOMPLETE_OR_INVALID_COMPLETION")
            if self.budget.requestwise and choices[0].get("message",{}).get("reasoning_content"):
                raise ProviderStopped("NON_THINKING_RESPONSE_MISMATCH")
            ai.response_metadata.update(id=raw["id"],provider_request_id=self.runtime["request_id"],
                provider_model=raw["model"],system_fingerprint=raw.get("system_fingerprint"))
            if self.budget.requestwise:
                ai.response_metadata.update(provider_correlation_id=self.runtime["request_id"] or raw["id"],
                    provider_correlation_kind="HTTP_REQUEST_ID" if self.runtime["request_id"] else "COMPLETION_ID")
            self.trace.emit("provider_settlement",reservation_id=key,logical_key=logical,
                sdk_usage=ai.usage_metadata,raw_usage=raw["usage"],ledger=self.budget.snapshot())
            return ChatResult(generations=[ChatGeneration(message=ai)])
        except BaseException as error:
            # Failure/timeout/cancellation and uncertain accounting are sticky.
            # Even a known successful bill with a protocol fault stops the batch.
            self.budget.unknown(key,type(error).__name__)
            self.trace.emit("provider_failure",reservation_id=key,error_class=type(error).__name__,
                reason=sanitize(str(error)),ledger=self.budget.snapshot())
            raise
        finally:
            self.runtime["reservation"]=None

    async def aclose(self):
        await self.runtime["http_async"].aclose()
        self.runtime["http_sync"].close()

    def assert_healthy(self):
        snapshot=self.budget.snapshot()
        if snapshot["halted"] or snapshot["unresolved"]:
            raise ProviderStopped("BATCH_STOPPED_"+str(snapshot["halted"] or "UNRESOLVED"))


def _model(*,budget,specs,trace,group_label,base_url,key,local=False):
    config=ProviderConfig()
    parsed=urlparse(base_url)
    if local:
        if parsed.scheme!="http" or parsed.hostname!="127.0.0.1" or not parsed.port or parsed.path not in {"","/"} or parsed.username or parsed.query or parsed.fragment:
            raise ProviderStopped("LOCAL_STUB_MUST_BE_LITERAL_LOOPBACK")
    elif base_url!=config.base_url: raise ProviderStopped("LIVE_ENDPOINT_CHANGED")
    runtime={"reservation":None,"raw":None,"request_id":None,"expected_tools":[],
        "evidence_level":"LOCAL_PROTOCOL_STUB_REAL_LOCAL_MCP_HTTP" if local else "REAL_PROVIDER_REAL_LOCAL_MCP_HTTP"}

    async def request_hook(request):
        if str(request.url)!=base_url.rstrip("/")+"/chat/completions":
            raise ProviderStopped("UNEXPECTED_REQUEST_DESTINATION")
        payload=json.loads(request.content)
        trace.emit("provider_pre_send_wire",reservation_id=runtime["reservation"],body=payload)
        allowed={"model","messages","stream","thinking","max_tokens","parallel_tool_calls","tools","tool_choice"}
        if set(payload)-allowed or payload.get("model")!=config.model or payload.get("max_tokens")!=512 or (
            payload.get("thinking")!={"type":"disabled"} or payload.get("stream") is not False
            or payload.get("parallel_tool_calls") is not False
            or payload.get("tools",[])!=runtime["expected_tools"]
            or (payload.get("tools") and payload.get("tool_choice")!="auto")):
            raise ProviderStopped("ACTUAL_WIRE_CONFIGURATION_MISMATCH")
        budget.sent(runtime["reservation"],payload=payload)
        trace.emit("provider_http_request",reservation_id=runtime["reservation"],
            endpoint=str(request.url),body=payload,transport="LOCAL_PROTOCOL_STUB" if local else "LIVE_PROVIDER")

    async def response_hook(response):
        await response.aread()
        try: raw=response.json()
        except ValueError: raw={"unparseable_response":True}
        runtime["raw"]=raw
        # Only whitelisted, nonsensitive request IDs; never log headers wholesale.
        runtime["request_id"]=response.headers.get("x-request-id") or response.headers.get("request-id")
        trace.emit("provider_http_response",reservation_id=runtime["reservation"],
            status=response.status_code,request_id=runtime["request_id"],body=safe_response(raw))

    client=httpx.AsyncClient(timeout=30,trust_env=False,follow_redirects=False,
        transport=httpx.AsyncHTTPTransport(retries=0),event_hooks={"request":[request_hook],"response":[response_hook]})
    sync=httpx.Client(timeout=30,trust_env=False,follow_redirects=False,transport=httpx.HTTPTransport(retries=0))
    runtime.update(http_async=client,http_sync=sync)
    sdk=ChatOpenAI(model=config.model,base_url=base_url,api_key=key,max_retries=0,timeout=30,
        temperature=None,streaming=False,http_async_client=client,http_client=sync,http_socket_options=(),
        extra_body={"thinking":{"type":"disabled"},"max_tokens":512})
    return MeteredModel(sdk=sdk,budget=budget,trace=trace,config=config,
        expected_specs=specs,group_label=group_label,runtime=runtime)


def build_local_model(*,base_url,budget,specs,trace,group_label):
    return _model(budget=budget,specs=specs,trace=trace,group_label=group_label,
        base_url=base_url,key="ar01-loopback-dummy-key",local=True)


def build_live_model(*,budget,specs,trace,group_label="unapproved",live=False,authorization=None,probe_wire=None):
    # No key lookup/client construction/network before both independent gates.
    config=ProviderConfig()
    if not live or not isinstance(authorization,dict) or authorization.get("authorized") is not True or not authorization.get("human_approval_reference"):
        raise ProviderStopped("PAID_AUTHORIZATION_REQUIRED")
    if budget.requestwise:
        # A new request-bound policy does not inherit authorization for the full
        # five-pair trial. This is a different, one-request scope, not P1.
        probe_expected={"scope":"ONE_REQUEST_PROTOCOL_PROBE","reservation_policy":REQUEST_WIRE_V1,
            "config_digest":digest_json(asdict(config)),"request_limit":1,"cost_cap_usd":"0.50"}
        if any(authorization.get(k)!=v for k,v in probe_expected.items()) or budget.cap!=500_000 or budget.limit!=1:
            raise ProviderStopped("PROBE_AUTHORIZATION_REQUIRED_OR_MISMATCHED")
        if not isinstance(probe_wire,dict) or authorization.get("wire_digest")!=digest_json(probe_wire) or probe_wire.get("tools",[])!=specs:
            raise ProviderStopped("PROBE_AUTHORIZATION_WIRE_MISMATCH")
        if not budget.preflight(probe_wire)["ready"]:
            raise ProviderStopped("COST_OR_UNRESOLVED_PREFLIGHT_BLOCKED")
        key=os.environ.get(MODEL_API_KEY)
        if not key: raise ProviderStopped("LOCAL_API_KEY_MISSING")
        model=_model(budget=budget,specs=specs,trace=trace,group_label=group_label,base_url=config.base_url,key=key)
        model.runtime["authorized_wire_digest"]=authorization["wire_digest"]
        return model
    expected={"config_digest":digest_json(asdict(config)),"request_limit":80,
        "cost_cap_usd":"0.50","cases":[list(k) for k in ORDER]}
    if any(authorization.get(k)!=v for k,v in expected.items()) or budget.cap!=500_000 or budget.limit!=80:
        raise ProviderStopped("AUTHORIZATION_CONFIGURATION_MISMATCH")
    if not budget.preflight()["ready"]:
        raise ProviderStopped("COST_OR_UNRESOLVED_PREFLIGHT_BLOCKED")
    key=os.environ.get(MODEL_API_KEY)
    if not key: raise ProviderStopped("LOCAL_API_KEY_MISSING")
    return _model(budget=budget,specs=specs,trace=trace,group_label=group_label,
        base_url=config.base_url,key=key)


async def batch(output,budget,model_factory):
    """Fixed initial-run sample. No repeats, adaptive sample changes or retries."""
    from experiments.ar01_free_agent.harness import run_pair
    output=Path(output)
    output.mkdir(parents=True,exist_ok=False)
    results=[]
    status="COMPLETED"
    try:
        for case in selected_cases():
            result=await run_pair(case,output/f"{case['id']}-{case['variant']}",
                model_factory=model_factory,model_id=ProviderConfig().model)
            results.append(result)
            # First material pair is the mandatory protocol gate for later pairs.
            if not all(g["model_dispatches"] and g["result"]["delivery_mode"]=="MODEL" for g in result["groups"]):
                raise ProviderStopped("PAIR_PROTOCOL_OR_DELIVERY_INCOMPLETE")
    except Exception as error:
        status="STOPPED"
        budget.halt(type(error).__name__)
        results.append({"incomplete_pair":True,"error_class":type(error).__name__,"reason":sanitize(str(error))})
    result={"status":status,"groups_completed":sum(len(r.get("groups",[])) for r in results),
        "results":results,"budget":budget.snapshot()}
    (output/"batch-results.json").write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
    return result


def main():
    import argparse
    parser=argparse.ArgumentParser(description="AR01 RM01: default is offline monetary preflight")
    parser.add_argument("--output",required=True,type=Path)
    parser.add_argument("--live",action="store_true")
    parser.add_argument("--authorization",type=Path)
    parser.add_argument("--request-bound",action="store_true",help="offline candidate preflight for one separately authorized probe")
    parser.add_argument("--wire-body",type=Path,help="actual prepared/observed JSON body; never a token estimate")
    args=parser.parse_args()
    budget=ExperimentBudget(args.output/"request-budget.sqlite3",**(
        {"reservation_policy":REQUEST_WIRE_V1,"request_limit":1} if args.request_bound else {}))
    wire=json.loads(args.wire_body.read_text(encoding="utf-8")) if args.wire_body else None
    preflight={"config":asdict(ProviderConfig()),"paid_authorized":False,
        "p1":"NOT_RUN","p2":"NOT_RUN",**budget.preflight(wire)}
    with (args.output/"preflight.json").open("x",encoding="utf-8") as f:
        f.write(json.dumps(preflight,indent=2))
    if not args.live:
        print(json.dumps(preflight,indent=2))
        return
    if args.request_bound:
        # Do not fall through to the existing P1 batch CLI. A separately approved
        # single probe can use build_live_model's exact-wire, one-call interface.
        raise ProviderStopped("P1_BLOCKED_SINGLE_PROBE_REQUIRES_SEPARATE_EXECUTION_AUTHORIZATION")
    auth=json.loads(args.authorization.read_text(encoding="utf-8")) if args.authorization else None
    # Enforce all gates before fixture/server setup. Default USD .50 stops here.
    model=build_live_model(budget=budget,specs=[],trace=None,live=True,authorization=auth)
    asyncio.run(model.aclose())
    def factory(group,task,specs,trace):
        label=f"{task['case_id']}/{group}"
        budget.claim_group(label)
        return build_live_model(budget=budget,specs=specs,trace=trace,group_label=label,live=True,authorization=auth)
    result=asyncio.run(batch(args.output/"batch",budget,factory))
    if result["status"]!="COMPLETED": raise SystemExit(2)


if __name__=="__main__": main()
