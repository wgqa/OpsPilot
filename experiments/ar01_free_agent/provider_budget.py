"""Finite experiment reservation ledger, separate from the business Domain.

No retry, reconciliation service, or authority to spend. All connections use
BEGIN IMMEDIATE; unresolved requests survive process death and stop continuation.
Rates are conservative peak/no-cache estimates, not a Provider billing receipt.
"""
from __future__ import annotations

from contextlib import contextmanager
from decimal import Decimal, ROUND_CEILING
import json
from pathlib import Path
import sqlite3
import time
import uuid

from opspilot.domain.d2 import canonical_json, digest_json


class BudgetStop(RuntimeError):
    pass


REQUEST_WIRE_V1 = "REQUEST_WIRE_V1"
LEGACY_MODEL_MAX = "LEGACY_MODEL_MAX"


def request_bound(payload):
    """Contract bound, not a tokenizer estimate or unconditional billing promise.

    Server context capacity bounds ALL input, including tools and private framing.
    Only the correctly serialized, documented output limit narrows the old bound.
    Keep the full payload for both arms; byte counts below are audit data only.
    """
    allowed={"model","messages","stream","thinking","max_tokens","parallel_tool_calls","tools","tool_choice"}
    if not isinstance(payload,dict) or set(payload)-allowed:
        raise BudgetStop("WIRE_UNKNOWN_FIELD")
    if payload.get("model")!="deepseek-flash" or payload.get("thinking")!={"type":"disabled"}:
        raise BudgetStop("WIRE_MODEL_OR_MODE_UNBOUNDED")
    if type(payload.get("max_tokens")) is not int or payload["max_tokens"]!=512:
        raise BudgetStop("WIRE_OUTPUT_LIMIT_UNBOUNDED")
    if payload.get("stream") is not False or payload.get("parallel_tool_calls") is not False:
        raise BudgetStop("WIRE_FROZEN_PARAMETERS_CHANGED")
    messages=payload.get("messages")
    if not isinstance(messages,list) or not messages:
        raise BudgetStop("WIRE_MESSAGES_INVALID")
    for m in messages:
        if not isinstance(m,dict) or set(m)-{"role","content","name","tool_calls","tool_call_id"}:
            raise BudgetStop("WIRE_MESSAGE_FIELDS_UNKNOWN")
        if m.get("role") not in {"system","user","assistant","tool"} or not (
            isinstance(m.get("content"),str) or (m.get("role")=="assistant" and m.get("content") is None and m.get("tool_calls"))):
            raise BudgetStop("WIRE_NON_TEXT_MESSAGE_UNBOUNDED")
    tools=payload.get("tools",[])
    if not isinstance(tools,list) or any(not isinstance(t,dict) or t.get("type")!="function" or
        not isinstance(t.get("function"),dict) or not isinstance(t["function"].get("name"),str) or
        not isinstance(t["function"].get("parameters"),dict) for t in tools):
        raise BudgetStop("WIRE_TOOL_SCHEMA_INVALID")
    if tools and payload.get("tool_choice")!="auto":
        raise BudgetStop("WIRE_TOOL_CHOICE_CHANGED")
    try:
        serialized=json.dumps(payload,ensure_ascii=False,sort_keys=True,allow_nan=False).encode("utf-8")
    except (ValueError,TypeError,UnicodeError) as error:
        raise BudgetStop("WIRE_SERIALIZATION_UNBOUNDED") from error
    return {"policy":REQUEST_WIRE_V1,"wire_semantic_digest":digest_json(payload),
        "input_upper_tokens":1_048_576,"output_upper_tokens":512,
        "reserve_micro":usage_cost({"prompt_tokens":1_048_576,"completion_tokens":512,"total_tokens":1_049_088}),
        "basis":"DOCUMENTED_CONTEXT_CAP_AND_ACTUAL_WIRE_OUTPUT_LIMIT",
        "input_includes":"messages + all tool schemas + server framing; no byte/token ratio assumed",
        "prepared_json_bytes_audit_only":len(serialized),"message_count":len(messages),"tool_count":len(tools),
        "tool_schema_digest":digest_json(tools),"absolute_billing_guarantee":False,
        "assumptions":["vendor enforces documented context and max_tokens limits",
            "disabled thinking and documented peak rates apply"],
        "sources":["https://api-docs.deepseek.com/quick_start/pricing/",
            "https://api-docs.deepseek.com/api/create-chat-completion/"]}


def micro(value):
    return int((Decimal(str(value))*1_000_000).to_integral_value(rounding=ROUND_CEILING))


def dollars(value):
    return format(Decimal(value)/1_000_000,".6f")


def usage_cost(usage):
    if not isinstance(usage,dict) or any(type(usage.get(k)) is not int or usage[k]<0
        for k in ("prompt_tokens","completion_tokens","total_tokens")):
        raise BudgetStop("USAGE_INVALID")
    if usage["total_tokens"] != usage["prompt_tokens"]+usage["completion_tokens"]:
        raise BudgetStop("USAGE_TOTAL_MISMATCH")
    for key in ("prompt_cache_hit_tokens","prompt_cache_miss_tokens"):
        if key in usage and (type(usage[key]) is not int or not 0<=usage[key]<=usage["prompt_tokens"]):
            raise BudgetStop("USAGE_CACHE_INVALID")
    if all(k in usage for k in ("prompt_cache_hit_tokens","prompt_cache_miss_tokens")) and (
        usage["prompt_cache_hit_tokens"]+usage["prompt_cache_miss_tokens"]!=usage["prompt_tokens"]):
        raise BudgetStop("USAGE_CACHE_TOTAL_MISMATCH")
    return int((Decimal(usage["prompt_tokens"])*Decimal("0.30")+
        Decimal(usage["completion_tokens"])*Decimal("1.20")).to_integral_value(rounding=ROUND_CEILING))


class ExperimentBudget:
    # Independent upper bounds deliberately overcount the joint context ceiling.
    worst_micro = usage_cost({"prompt_tokens":1_048_576,"completion_tokens":393_216,"total_tokens":1_441_792})

    def __init__(self,path,*,cost_cap_usd=Decimal("0.50"),request_limit=80,
                 reservation_policy=LEGACY_MODEL_MAX):
        self.path=Path(path)
        self.path.parent.mkdir(parents=True,exist_ok=True)
        if type(request_limit) is not int or not 1<=request_limit<=80 or not Decimal("0")<Decimal(str(cost_cap_usd))<=2:
            raise ValueError("INVALID_EXPERIMENT_LIMITS")
        self.cap, self.limit=micro(cost_cap_usd),request_limit
        if reservation_policy not in {LEGACY_MODEL_MAX,REQUEST_WIRE_V1}:
            raise ValueError("UNKNOWN_RESERVATION_POLICY")
        self.requestwise=reservation_policy==REQUEST_WIRE_V1
        self.policy={"release":"AR01-RM01-P0-V1","cap_micro":self.cap,"request_limit":self.limit,
            "input_peak_per_million":"0.30","output_peak_per_million":"1.20",
            "reservation_micro":self.worst_micro,"single_in_flight":True}
        if self.requestwise:
            self.policy.update(release="AR01-RM01-HF01-V1",reservation_policy=REQUEST_WIRE_V1,
                reservation_micro=None,input_context_ceiling=1_048_576,wire_max_tokens=512)
        with self.transaction() as c:
            c.execute("CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY,value TEXT NOT NULL)")
            c.execute("CREATE TABLE IF NOT EXISTS requests(id TEXT PRIMARY KEY,logical_key TEXT UNIQUE NOT NULL,"
                "payload_digest TEXT NOT NULL,status TEXT NOT NULL,reserved_micro INTEGER NOT NULL,"
                "charge_micro INTEGER,sends INTEGER NOT NULL DEFAULT 0,created REAL NOT NULL,finished REAL,"
                "usage_json TEXT,error TEXT)")
            c.execute("CREATE TABLE IF NOT EXISTS groups(label TEXT PRIMARY KEY,created REAL NOT NULL)")
            row=c.execute("SELECT value FROM meta WHERE key='policy'").fetchone()
            if row and row[0]!=canonical_json(self.policy):
                raise BudgetStop("LEDGER_POLICY_CHANGED")
            c.execute("INSERT OR IGNORE INTO meta VALUES('policy',?)",(canonical_json(self.policy),))
            if self.requestwise and "bound_json" not in {r[1] for r in c.execute("PRAGMA table_info(requests)")}:
                c.execute("ALTER TABLE requests ADD COLUMN bound_json TEXT")

    @contextmanager
    def transaction(self):
        c=sqlite3.connect(self.path,timeout=10)
        c.row_factory=sqlite3.Row
        try:
            c.execute("PRAGMA synchronous=FULL")
            c.execute("BEGIN IMMEDIATE")
            yield c
            c.commit()
        except BaseException:
            c.rollback()
            raise
        finally:
            c.close()

    def _snapshot(self,c):
        rows=[dict(r) for r in c.execute("SELECT * FROM requests ORDER BY created,id")]
        exposure=sum(r["charge_micro"] if r["charge_micro"] is not None else r["reserved_micro"] for r in rows)
        halted=c.execute("SELECT value FROM meta WHERE key='halted'").fetchone()
        return {"requests":len(rows),"exposure_usd":dollars(exposure),"exposure_micro":exposure,
            "halted":halted[0] if halted else None,"rows":rows,
            "unresolved":sum(r["charge_micro"] is None for r in rows),"policy":self.policy}

    def snapshot(self):
        with self.transaction() as c:
            return self._snapshot(c)

    def preflight(self,payload=None):
        s=self.snapshot()
        bound=None
        reason=None
        if self.requestwise:
            try: bound=request_bound(payload)
            except BudgetStop as error: reason=str(error)
        reserve=bound["reserve_micro"] if bound else None if self.requestwise else self.worst_micro
        return {"ready":not s["halted"] and not s["unresolved"] and s["requests"]<self.limit
            and reserve is not None and s["exposure_micro"]+reserve<=self.cap,
            "next_reservation_usd":dollars(reserve) if reserve is not None else None,"snapshot":s,
            "bound":bound,"bound_error":reason,
            "live_vendor_compliance":"NOT_VERIFIED","billing_guarantee":False}

    def claim_group(self,label):
        with self.transaction() as c:
            if c.execute("SELECT 1 FROM groups WHERE label=?",(label,)).fetchone():
                raise BudgetStop("GROUP_ALREADY_CLAIMED")
            c.execute("INSERT INTO groups VALUES(?,?)",(label,time.time()))

    def reserve(self,logical_key,payload):
        bound=request_bound(payload) if self.requestwise else None
        reserve=bound["reserve_micro"] if bound else self.worst_micro
        with self.transaction() as c:
            s=self._snapshot(c)
            if c.execute("SELECT 1 FROM requests WHERE logical_key=?",(logical_key,)).fetchone():
                raise BudgetStop("DUPLICATE_REQUEST_NO_RESEND")
            if s["halted"]: raise BudgetStop("LEDGER_HALTED_"+s["halted"])
            if s["unresolved"]: raise BudgetStop("REQUEST_IN_FLIGHT_OR_UNKNOWN")
            if s["requests"]>=self.limit: raise BudgetStop("REQUEST_CAP")
            if s["exposure_micro"]+reserve>self.cap: raise BudgetStop("COST_CAP")
            key=f"rm01-{uuid.uuid4()}"
            c.execute("INSERT INTO requests(id,logical_key,payload_digest,status,reserved_micro,created) VALUES(?,?,?,?,?,?)",
                (key,logical_key,digest_json(payload),"RESERVED",reserve,time.time()))
            if bound:
                c.execute("UPDATE requests SET bound_json=? WHERE id=?",(canonical_json(bound),key))
            return key

    def sent(self,key,*,payload=None):
        failure=None
        with self.transaction() as c:
            row=c.execute("SELECT * FROM requests WHERE id=?",(key,)).fetchone()
            if row is None: raise BudgetStop("UNKNOWN_RESERVATION")
            if row["sends"] or row["status"]!="RESERVED":
                c.execute("INSERT OR REPLACE INTO meta VALUES('halted','REPEAT_SEND')")
                failure="REPEAT_SEND"
            elif self.requestwise and (payload is None or digest_json(payload)!=row["payload_digest"]):
                c.execute("INSERT OR IGNORE INTO meta VALUES('halted','WIRE_BODY_CHANGED')")
                failure="WIRE_BODY_CHANGED"
            else:
                c.execute("UPDATE requests SET sends=1,status='SENT' WHERE id=?",(key,))
        if failure: raise BudgetStop(failure)

    def halt(self,reason):
        with self.transaction() as c:
            c.execute("INSERT OR IGNORE INTO meta VALUES('halted',?)",(reason,))

    def unknown(self,key,reason):
        with self.transaction() as c:
            c.execute("UPDATE requests SET status='UNKNOWN',error=?,finished=? WHERE id=? AND charge_micro IS NULL",
                (reason,time.time(),key))
            c.execute("INSERT OR IGNORE INTO meta VALUES('halted',?)",(reason,))

    def settle(self,key,usage):
        try:
            charge=usage_cost(usage)
        except BudgetStop as error:
            self.unknown(key,str(error))
            raise
        violation=None
        with self.transaction() as c:
            row=c.execute("SELECT * FROM requests WHERE id=?",(key,)).fetchone()
            if row is None or row["status"]!="SENT": raise BudgetStop("INVALID_SETTLEMENT")
            if charge>row["reserved_micro"]: violation="DOCUMENTED_COST_BOUND_EXCEEDED"
            if usage["completion_tokens"]>512: violation="REQUEST_MAX_TOKENS_NOT_HONORED"
            if self.requestwise:
                bound=json.loads(row["bound_json"])
                if usage["prompt_tokens"]>bound["input_upper_tokens"]:
                    violation="REQUEST_INPUT_BOUND_EXCEEDED"
                details=usage.get("completion_tokens_details")
                if details is not None and (not isinstance(details,dict) or
                    ("reasoning_tokens" in details and (type(details["reasoning_tokens"]) is not int or details["reasoning_tokens"]!=0))):
                    violation="NON_THINKING_USAGE_MISMATCH"
            c.execute("UPDATE requests SET status=?,charge_micro=?,usage_json=?,finished=?,error=? WHERE id=?",
                ("SETTLED_ERROR" if violation else "SETTLED",charge,canonical_json(usage),time.time(),violation,key))
            if violation: c.execute("INSERT OR IGNORE INTO meta VALUES('halted',?)",(violation,))
        if violation: raise BudgetStop(violation)

    def pin_backend(self,model,fingerprint):
        if not isinstance(model,str) or not model or not isinstance(fingerprint,str) or not fingerprint:
            self.halt("MISSING_MODEL_OR_FINGERPRINT")
            raise BudgetStop("MISSING_MODEL_OR_FINGERPRINT")
        changed=False
        with self.transaction() as c:
            pin=canonical_json({"model":model,"system_fingerprint":fingerprint})
            row=c.execute("SELECT value FROM meta WHERE key='backend'").fetchone()
            if row and row[0]!=pin:
                c.execute("INSERT OR IGNORE INTO meta VALUES('halted','MODEL_VERSION_DRIFT')")
                changed=True
            else: c.execute("INSERT OR IGNORE INTO meta VALUES('backend',?)",(pin,))
        if changed: raise BudgetStop("MODEL_VERSION_DRIFT")
