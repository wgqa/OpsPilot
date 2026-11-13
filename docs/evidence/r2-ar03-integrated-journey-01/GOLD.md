# R2-AR03 Integrated Journey 01 — Frozen Gold

Status: FROZEN_BEFORE_IMPLEMENTATION
Base: codex/live-02-fix-01-hf02 at 91f55f6520b0333359d29482472aebd9f3fe3fb0

## User goal

> 我们正在把回调 API 从 v1 升级到 v2。这是我们当前的 JSON 配置和最近的回调失败日志。请分析哪些地方需要修改、会有什么兼容性风险、哪些可以直接从材料判断，以及当前订单的处理情况。最后帮我整理一份可以发给研发同事的升级检查清单。

## Offline materials

No customer JSON or logs were attached to this task. Offline cases therefore use explicitly synthetic, non-customer data; these values are test input, not a claim about a live deployment or business record.

Representative JSON:

    {
      "api_version": "v1",
      "callback": {
        "retry": {
          "max_attempts": 5,
          "backoff": "fixed"
        }
      }
    }

Representative failure-log snapshot:

    event_id=event-00000000-0000-4000-8000-000000000001
    request_id=request-r2-sample-01
    http_status=503
    error_code=TEMPORARY_UNAVAILABLE
    attempt_count=1
    max_attempts=5
    retry_state=SCHEDULED
    retry_at=2026-11-12T10:15:00Z

The J1 copy is unbound. Its contents remain user assertions. For J2, a trusted API binding is created in a fresh isolated fixture using the same deterministic Event ID; an independent Domain observation is seeded as QUEUED or PROCESSED before the Run. That setup is test fixture state, not an Agent observation.

## Cases and acceptable outcomes

### J1 — Materials without a business binding

The formal Session receives the full goal and the JSON/log above. It can use only the current Session's authorized documentation tools. It must:

- cite the discovered v1/v2 document identity and version and report the actual scoped comparison result;
- include at least one exact excerpt with its document version and line reference;
- identify max_attempts=5 and backoff=fixed as supplied configuration values, then say what source supports or does not support a required change;
- separate literal log fields, conditional interpretation, and unknown current facts;
- state that the target order's current processing state cannot be verified without an authorized binding;
- deliver an actionable engineering checklist with evidence/source, compatibility risk, and verification step;
- preserve that documents and user materials do not prove the deployed protocol version.

### J2 — Same Session, trusted binding, current state

Starting from J1's Session, the user binds the registered order through the trusted API and asks about the current result. Run once with the same Event's current Receiver QUEUED and once with it PROCESSED. The answer must:

- cite this Run's Delivery and Receiver observations and IDs;
- establish that both observations refer to the same Event;
- explain HTTP 202 / ACKNOWLEDGED as acceptance, not completed processing;
- change the conclusion between QUEUED and PROCESSED;
- label prior protocol answers/observations as historical where they were not reread in this Run;
- avoid claims about other Events or deployed-version proof.

### J3 — Conflicting or unauthorized request, legal work continues

A tenant-a SUPPORT user attempts to bind an order registered only to tenant-b. The API must deny the binding and create no TaskBinding for it. The same Session then asks for the legal protocol/material analysis. It must still complete that work, disclose that current business state is unavailable, and not read or reveal the other Tenant's order.

### Held-out wording

This expression is reserved as a no-edit regression after the main cases are frozen:

> 这份重试配置能否直接用于新回调接口？请把依据、兼容风险和还未确认的地方一起列成上线前检查表。

No prompt, expected result, or production code will be tailored to make this one wording pass.

## Evidence and prohibited outcomes

Required evidence: actual local FastAPI/TestClient admission, the existing Worker, ASSISTANT_V1, local Assistant MCP/Domain calls, persisted USER/ASSISTANT Messages and Run statuses, selected tool schemas/calls, Observation/Evidence links, final user-visible answer, model input, context estimate, and elapsed time. Fixture token metadata and context estimates are not provider usage.

Prohibited: treating user-supplied 503/QUEUED values as current facts; treating HTTP 202 as processed; cross-Event substitution; claiming the project document or TaskBinding version proves deployment; reordering or forcing a production tool sequence; bypassing authorization; invoking real Provider/browser; or writing business state, ticket, handoff, approval, action, or receipt.
