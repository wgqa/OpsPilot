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

    def __init__(self,path,*,cost_cap_usd=Decimal("0.50"),request_limit=80):
        self.path=Path(path)
        self.path.parent.mkdir(parents=True,exist_ok=True)
        if type(request_limit) is not int or not 1<=request_limit<=80 or not Decimal("0")<Decimal(str(cost_cap_usd))<=2:
            raise ValueError("INVALID_EXPERIMENT_LIMITS")
        self.cap, self.limit=micro(cost_cap_usd),request_limit
        self.policy={"release":"AR01-RM01-P0-V1","cap_micro":self.cap,"request_limit":self.limit,
            "input_peak_per_million":"0.30","output_peak_per_million":"1.20",
            "reservation_micro":self.worst_micro,"single_in_flight":True}
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

    def preflight(self):
        s=self.snapshot()
        return {"ready":not s["halted"] and not s["unresolved"] and s["requests"]<self.limit
            and s["exposure_micro"]+self.worst_micro<=self.cap,
            "next_reservation_usd":dollars(self.worst_micro),"snapshot":s,
            "live_vendor_compliance":"NOT_VERIFIED","billing_guarantee":False}

    def claim_group(self,label):
        with self.transaction() as c:
            if c.execute("SELECT 1 FROM groups WHERE label=?",(label,)).fetchone():
                raise BudgetStop("GROUP_ALREADY_CLAIMED")
            c.execute("INSERT INTO groups VALUES(?,?)",(label,time.time()))

    def reserve(self,logical_key,payload):
        with self.transaction() as c:
            s=self._snapshot(c)
            if c.execute("SELECT 1 FROM requests WHERE logical_key=?",(logical_key,)).fetchone():
                raise BudgetStop("DUPLICATE_REQUEST_NO_RESEND")
            if s["halted"]: raise BudgetStop("LEDGER_HALTED_"+s["halted"])
            if s["unresolved"]: raise BudgetStop("REQUEST_IN_FLIGHT_OR_UNKNOWN")
            if s["requests"]>=self.limit: raise BudgetStop("REQUEST_CAP")
            if s["exposure_micro"]+self.worst_micro>self.cap: raise BudgetStop("COST_CAP")
            key=f"rm01-{uuid.uuid4()}"
            c.execute("INSERT INTO requests(id,logical_key,payload_digest,status,reserved_micro,created) VALUES(?,?,?,?,?,?)",
                (key,logical_key,digest_json(payload),"RESERVED",self.worst_micro,time.time()))
            return key

    def sent(self,key):
        duplicate=False
        with self.transaction() as c:
            row=c.execute("SELECT * FROM requests WHERE id=?",(key,)).fetchone()
            if row is None: raise BudgetStop("UNKNOWN_RESERVATION")
            if row["sends"] or row["status"]!="RESERVED":
                c.execute("INSERT OR REPLACE INTO meta VALUES('halted','REPEAT_SEND')")
                duplicate=True
            else:
                c.execute("UPDATE requests SET sends=1,status='SENT' WHERE id=?",(key,))
        if duplicate: raise BudgetStop("REPEAT_SEND")

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
